"""Interface de commande : python -m linkedin_agents <commande> [options]."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .context import DEFAULT_BRAND, DEFAULT_STRATEGY, Context, write_json
from .orchestrator import agents_list, format_report, run_agent, run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linkedin_agents",
        description="11 agents LinkedIn : analyse, rédaction, publication, supervision.",
    )
    parser.add_argument("--root", default=".", help="Racine du projet (défaut : dossier courant)")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Simulation (activé par défaut)")
    parser.add_argument("--live", action="store_true",
                        help="Désactive la simulation (publication réelle si configurée)")
    parser.add_argument("--json", action="store_true", help="Sortie JSON machine")
    parser.add_argument("-v", "--verbose", action="store_true")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="Lister les 11 agents")
    sub.add_parser("init", help="Créer workspace/ avec un profil de marque par défaut")

    for name, label in [
        ("watch", "Agent 1 — Veille"),
        ("audience", "Agent 2 — Analyse d'audience"),
        ("strategist", "Agent 3 — Stratège"),
        ("scheduler", "Agent 7 — Programmateur"),
        ("supervise", "Agent 10 — Superviseur"),
        ("engagement", "Agent 9 — Engagement"),
        ("analyze", "Agent 11 — Analyste"),
    ]:
        sub.add_parser(name, help=label)

    writer = sub.add_parser("writer", help="Agent 4 — Rédacteur")
    writer.add_argument("--topic", help="Sujet ad hoc (sinon utilise le plan)")
    writer.add_argument("--pillar", help="Pilier de marque imposé")
    writer.add_argument("--limit", type=int, default=None, help="Nombre de posts à rédiger")

    for name, label in [("editor", "Agent 5 — Éditeur"), ("visual", "Agent 6 — Visuel")]:
        cmd = sub.add_parser(name, help=label)
        cmd.add_argument("--file", help="Fichier précis à traiter")

    publish = sub.add_parser("publish", help="Agent 8 — Publisher")
    publish.add_argument("--file", action="append", help="Fichier à publier (répétable)")
    publish.add_argument("--force", action="store_true", help="Publier sans approbation du superviseur")

    pipeline = sub.add_parser("pipeline", help="Les 11 agents à la chaîne")
    pipeline.add_argument("--steps", help="Liste d'agents séparés par des virgules")
    pipeline.add_argument("--no-publish", action="store_true", help="S'arrêter avant la publication")

    serve = sub.add_parser("serve", help="Interface web locale")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--host", default="127.0.0.1")

    return parser


def command_init(ctx: Context) -> int:
    ctx.ensure_dirs()
    if not ctx.brand_path.exists():
        write_json(ctx.brand_path, DEFAULT_BRAND)
    if not ctx.plan_path.exists():
        write_json(ctx.plan_path, {"topics": [], "strategy": DEFAULT_STRATEGY})
    if not ctx.state_path.exists():
        ctx.save_state(ctx.load_state())
    (ctx.workspace / ".gitkeep").touch()
    print(f"✔ workspace initialisé : {ctx.workspace}")
    print(f"  → personnalisez {ctx.brand_path} (voix, piliers, interdits)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = Context(root=Path(args.root).resolve(), dry_run=not args.live, verbose=args.verbose)
    ctx.ensure_dirs()

    if args.command == "list":
        rows = agents_list()
        if args.json:
            print(json.dumps(rows, ensure_ascii=False, indent=2))
        else:
            print(f"{'#':<3}{'agent':<14}{'libellé'}")
            for row in rows:
                print(f"{row['order']:<3}{row['key']:<14}{row['label']}")
        return 0

    if args.command == "init":
        return command_init(ctx)

    if args.command == "serve":
        from .web import serve
        serve(ctx, host=args.host, port=args.port)
        return 0

    if args.command == "pipeline":
        steps = [s.strip() for s in args.steps.split(",")] if args.steps else None
        report = run_pipeline(ctx, steps=steps, dry_run=ctx.dry_run,
                              publish=not args.no_publish)
        print(report_json(report) if args.json else format_report(report))
        return 0

    payload: dict = {}
    if args.command == "writer":
        if args.topic:
            payload["topic"] = args.topic
        if args.pillar:
            payload["pillar"] = args.pillar
        if args.limit:
            payload["limit"] = args.limit
    elif args.command in ("editor", "visual") and args.file:
        payload["file"] = args.file
    elif args.command == "publish":
        if args.file:
            payload["files"] = args.file
        payload["force"] = args.force
        payload["dry_run"] = ctx.dry_run

    key = {"supervise": "supervisor", "analyze": "analyst"}.get(args.command, args.command)
    result = run_agent(ctx, key, payload)

    if args.json:
        print(json.dumps(result.as_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"{'✔' if result.ok else '✖'} {key} — {result.summary}")
        for out in result.outputs:
            print(f"  → {out}")
    return 0 if result.ok else 1


def report_json(report: dict) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    sys.exit(main())
