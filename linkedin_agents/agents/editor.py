"""Agent 5 — Éditeur : resserre, corrige et note la lisibilité des brouillons."""
from __future__ import annotations

import re
from typing import Any

from ..context import Context, read_text
from .base import AgentResult, agent, body_without_frontmatter, frontmatter, readability

CLICHES = [
    "révolutionnaire", "game changer", "disruptif", "synergie", "best practice",
    "il est important de noter", "dans un monde où", "à l'ère du numérique",
    "force est de constater", "clé de voûte",
]

REPLACEMENTS = {
    r"\bafin de\b": "pour",
    r"\bde manière à\b": "pour",
    r"\bpar conséquent\b": "donc",
    r"\bil est possible de\b": "on peut",
    r"\bdans le but de\b": "pour",
    r"\bactuellement\b": "aujourd'hui",
}


def tighten(text: str) -> tuple[str, list[str]]:
    """Applique les substitutions de style et retire les répétitions de ponctuation."""
    changes: list[str] = []
    result = text
    for pattern, replacement in REPLACEMENTS.items():
        new = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        if new != result:
            changes.append(f"{pattern} → {replacement}")
            result = new
    cleaned = re.sub(r"\s+([,.;!?])", r"\1", result)
    cleaned = re.sub(r"[!?]{2,}", "!", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned != result:
        changes.append("ponctuation et espaces normalisés")
    return cleaned, changes


def find_issues(text: str, forbidden: list[str]) -> list[str]:
    issues: list[str] = []
    low = text.lower()
    for word in forbidden:
        if word.lower() in low:
            issues.append(f"terme interdit : « {word} »")
    for cliche in CLICHES:
        if cliche in low:
            issues.append(f"cliché : « {cliche} »")
    stats = readability(text)
    if stats["avg_sentence_words"] > 22:
        issues.append(f"phrases longues (moyenne {stats['avg_sentence_words']} mots)")
    if stats["words"] > 220:
        issues.append(f"post trop long ({stats['words']} mots)")
    if not re.search(r"[#@]\w+", text):
        issues.append("aucun hashtag")
    return issues


def edit_file(path, forbidden: list[str]) -> dict[str, Any]:
    raw = read_text(path)
    meta = frontmatter(raw)
    body = body_without_frontmatter(raw)
    new_body, changes = tighten(body)
    issues = find_issues(new_body, forbidden)

    header = "\n".join(f"{k}: {v}" for k, v in meta.items())
    final = f"---\n{header}\n---\n\n{new_body}\n" if header else new_body + "\n"
    path.write_text(final, encoding="utf-8")

    return {
        "file": str(path),
        "changes": changes,
        "issues": issues,
        "stats": readability(new_body),
        "chars": len(new_body),
    }


@agent("editor", "Éditeur", 5)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    payload = payload or {}
    forbidden = ctx.brand.get("forbidden", [])

    if payload.get("file"):
        files = [ctx.root / payload["file"] if not str(payload["file"]).startswith(str(ctx.root))
                 else payload["file"]]
        files = [type(ctx.drafts_dir)(f) for f in files]
    elif payload.get("files"):
        files = [type(ctx.drafts_dir)(f) for f in payload["files"]]
    else:
        files = sorted(ctx.drafts_dir.glob("*.md"))

    if not files:
        return AgentResult(agent="editor", ok=False,
                           summary="Aucun brouillon à éditer (lancez l'agent Rédacteur).")

    results = [edit_file(f, forbidden) for f in files]
    total_issues = sum(len(r["issues"]) for r in results)
    ctx.log("editor", "edit", {"files": len(results), "issues": total_issues})

    return AgentResult(
        agent="editor",
        ok=True,
        summary=f"{len(results)} brouillon(s) édité(s), {total_issues} point(s) à corriger",
        data={"results": results},
        outputs=[r["file"] for r in results],
    )
