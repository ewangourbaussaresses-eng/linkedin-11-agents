"""Interface web locale (stdlib uniquement) : http://localhost:8765

Pages :
  /                 tableau de bord (agents, état, derniers rapports)
  /run?agent=key    exécute un agent et affiche le résultat
  /pipeline         exécute le pipeline complet en simulation
  /file?path=...    affiche un fichier du workspace
"""
from __future__ import annotations

import html
import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import llm
from .context import Context, read_json
from .orchestrator import agents_list, format_report, run_agent, run_pipeline

STYLE = """
:root{--bg:#0b1220;--card:#131c2e;--fg:#e8eef9;--muted:#93a4bf;--accent:#4c8dff;--ok:#38e07b;--warn:#ffb02e}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,sans-serif;background:var(--bg);color:var(--fg)}
header{padding:22px 28px;border-bottom:1px solid #1e2a42;display:flex;gap:16px;align-items:baseline}
h1{font-size:19px;margin:0}
.sub{color:var(--muted);font-size:13px}
main{padding:24px 28px;max-width:1100px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:14px}
.card{background:var(--card);border:1px solid #1e2a42;border-radius:12px;padding:16px}
.card h3{margin:0 0 6px;font-size:15px}
.card p{margin:0 0 12px;color:var(--muted);font-size:13px}
a.btn,button{background:var(--accent);color:#fff;border:0;border-radius:8px;padding:8px 12px;
 font-size:13px;text-decoration:none;cursor:pointer;display:inline-block}
a.btn.ghost{background:transparent;border:1px solid #2a3a58;color:var(--fg)}
pre{background:#0e1626;border:1px solid #1e2a42;border-radius:10px;padding:14px;overflow:auto;
 font-size:12.5px;line-height:1.5;white-space:pre-wrap}
.ok{color:var(--ok)}.warn{color:var(--warn)}
.tag{font-size:11px;color:var(--muted);border:1px solid #2a3a58;border-radius:999px;padding:2px 8px}
table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border-bottom:1px solid #1e2a42;padding:8px;text-align:left}
"""


def page(title: str, body: str) -> bytes:
    return f"""<!doctype html><html lang="fr"><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>{STYLE}</style></head><body>
<header><h1>🧠 LinkedIn 11 Agents</h1><span class="sub">{html.escape(title)}</span></header>
<main>{body}</main></body></html>""".encode("utf-8")


def dashboard(ctx: Context) -> bytes:
    state = ctx.load_state()
    cards = []
    for row in agents_list():
        cards.append(f"""<div class="card"><h3>{row['order']}. {html.escape(row['label'])}</h3>
<p><span class="tag">{row['key']}</span></p>
<a class="btn" href="/run?agent={row['key']}">Exécuter</a></div>""")
    history = state.get("history", [])[-8:][::-1]
    rows = "".join(
        f"<tr><td>{html.escape(h['at'][11:16])}</td><td>{html.escape(h['agent'])}</td>"
        f"<td>{html.escape(h['action'])}</td></tr>" for h in history) or "<tr><td colspan=3>—</td></tr>"
    body = f"""
<p class="sub">Mode : {'<span class="warn">simulation</span>' if ctx.dry_run else '<span class="ok">réel</span>'}
 · rédaction : <span class="{'ok' if llm.is_available() else 'warn'}">{html.escape(
    {'claude': 'Claude connecté', 'openai': 'OpenAI connecté'}.get(
        llm.active_provider(), 'gabarits locaux (aucune clé)'))}</span>
 · espace de travail : {html.escape(str(ctx.workspace))}</p>
<p><a class="btn" href="/pipeline">▶ Lancer le pipeline complet (simulation)</a>
 <a class="btn ghost" href="/file?path=workspace/calendar.md">📅 Calendrier</a>
 <a class="btn ghost" href="/file?path=workspace/reports/supervision.json">🛡️ Supervision</a></p>
<div class="grid">{''.join(cards)}</div>
<h2 style="font-size:16px;margin-top:28px">Activité récente</h2>
<table><tr><th>heure</th><th>agent</th><th>action</th></tr>{rows}</table>
"""
    return page("Tableau de bord", body)


def result_page(title: str, text: str) -> bytes:
    body = f"""<p><a class="btn ghost" href="/">← Retour</a></p>
<pre>{html.escape(text)}</pre>"""
    return page(title, body)


def make_handler(ctx: Context):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, payload: bytes, status: int = 200, ctype="text/html; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):  # noqa: N802
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            if parsed.path == "/":
                return self._send(dashboard(ctx))

            if parsed.path == "/run":
                key = (query.get("agent") or [""])[0]
                try:
                    result = run_agent(ctx, key)
                    text = json.dumps(result.as_dict(), ensure_ascii=False, indent=2)
                except KeyError as exc:
                    text = str(exc)
                return self._send(result_page(f"Agent {key}", text))

            if parsed.path == "/pipeline":
                report = run_pipeline(ctx, dry_run=True)
                return self._send(result_page("Pipeline", format_report(report)))

            if parsed.path == "/file":
                target = (query.get("path") or [""])[0]
                path = (ctx.root / target).resolve()
                if not str(path).startswith(str(ctx.root.resolve())) or not path.is_file():
                    return self._send(page("Fichier", "<p>Fichier introuvable.</p>"), 404)
                content = path.read_text(encoding="utf-8", errors="replace")
                return self._send(result_page(path.name, content))

            if parsed.path == "/api/state":
                return self._send(json.dumps(ctx.load_state(), ensure_ascii=False).encode(),
                                  ctype="application/json")

            return self._send(page("404", "<p>Page introuvable.</p>"), 404)

        def log_message(self, fmt, *args):  # silence
            pass

    return Handler


def serve(ctx: Context, host: str = "127.0.0.1", port: int = 8765) -> None:
    ctx.ensure_dirs()
    server = ThreadingHTTPServer((host, port), make_handler(ctx))
    print(f"LinkedIn 11 Agents → http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
