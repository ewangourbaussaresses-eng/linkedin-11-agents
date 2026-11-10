"""Agent 10 — Superviseur : contrôle qualité et garde-fou avant publication.

Note chaque brouillon sur 100 et rend un verdict `approuve` / `bloque`.
Critères : termes interdits, clichés, longueur, hashtags, doublons, promesses non
prouvées, cohérence avec les piliers de marque.
"""
from __future__ import annotations

import re
from typing import Any

from ..context import Context, read_text, write_json
from .base import AgentResult, agent, body_without_frontmatter, frontmatter, readability

PROMISES = ("garantie", "garanti", "100 %", "100%", "assuré", "résultat garanti",
            "en 24h", "sans effort", "à coup sûr")


def similarity(a: str, b: str) -> float:
    """Jaccard sur les mots : 1.0 = identique."""
    wa = {w for w in re.findall(r"[a-zà-ÿ]{4,}", a.lower())}
    wb = {w for w in re.findall(r"[a-zà-ÿ]{4,}", b.lower())}
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def evaluate(body: str, brand: dict, others: list[str]) -> dict[str, Any]:
    issues: list[str] = []
    score = 100.0
    low = body.lower()

    for word in brand.get("forbidden", []):
        if word.lower() in low:
            issues.append(f"terme interdit : « {word} »")
            score -= 25

    for promise in PROMISES:
        if promise in low:
            issues.append(f"promesse non prouvée : « {promise} »")
            score -= 15

    if not re.search(r"#\w+", body):
        issues.append("aucun hashtag")
        score -= 10

    stats = readability(body)
    if stats["words"] < 30:
        issues.append("post trop court (moins de 30 mots)")
        score -= 15
    if stats["words"] > 220:
        issues.append("post trop long")
        score -= 10
    if stats["avg_sentence_words"] > 22:
        issues.append("phrases trop longues")
        score -= 10

    if len(body) > 1300:
        issues.append("dépasse la limite LinkedIn de 1300 caractères")
        score -= 20

    for other in others:
        if similarity(body, other) > 0.7:
            issues.append("trop proche d'un autre post du lot (doublon)")
            score -= 20
            break

    pillar = None
    for candidate in brand.get("pillars", []):
        if candidate.lower() in low:
            pillar = candidate
            break
    if not pillar and brand.get("pillars"):
        issues.append("pilier de marque non identifiable")
        score -= 5

    score = max(0.0, min(100.0, score))
    threshold = int(brand.get("limits", {}).get("min_score_supervisor", 70))
    verdict = "approuve" if score >= threshold and not any(
        i.startswith(("terme interdit", "promesse")) for i in issues) else "bloque"

    return {"score": round(score, 1), "verdict": verdict, "issues": issues}


@agent("supervisor", "Superviseur", 10)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    payload = payload or {}
    files = payload.get("files") or [str(p) for p in sorted(ctx.drafts_dir.glob("*.md"))]
    if not files:
        return AgentResult(agent="supervisor", ok=False, summary="Aucun brouillon à superviser.")

    from pathlib import Path
    paths = [Path(f) if Path(f).is_absolute() else ctx.root / f for f in files]
    bodies = [body_without_frontmatter(read_text(p)) for p in paths]

    verdicts = []
    for i, (path, body) in enumerate(zip(paths, bodies)):
        others = [b for j, b in enumerate(bodies) if j != i]
        verdict = evaluate(body, ctx.brand, others)
        meta = frontmatter(read_text(path))
        verdicts.append({"file": str(path), "title": meta.get("title", path.stem), **verdict})

    approved = sum(1 for v in verdicts if v["verdict"] == "approuve")
    out = write_json(ctx.reports_dir / "supervision.json", {
        "approved": approved,
        "blocked": len(verdicts) - approved,
        "verdicts": verdicts,
    })
    ctx.log("supervisor", "verdicts", {"approved": approved, "total": len(verdicts)})

    return AgentResult(
        agent="supervisor",
        ok=approved > 0,
        summary=f"{approved}/{len(verdicts)} post(s) approuvé(s)",
        data={"approved": approved, "blocked": len(verdicts) - approved, "verdicts": verdicts},
        outputs=[str(out)],
    )
