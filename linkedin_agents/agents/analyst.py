"""Agent 11 — Analyste : mesure, compare et met à jour les apprentissages.

Entrée : `data/metrics.csv` (ou `payload["metrics"]`) avec
`topic_id, impressions, likes, comments, shares, clicks`.
Sortie : taux d'engagement par post, classement, apprentissages, recommandations
stockées dans `state.json` (`learnings`) pour nourrir la prochaine stratégie.
"""
from __future__ import annotations

import csv
from typing import Any

from ..context import Context, write_json
from .base import AgentResult, agent


def _num(value: Any) -> float:
    try:
        return float(str(value).strip().replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


def load_metrics(ctx: Context, payload: dict[str, Any] | None) -> list[dict[str, str]]:
    payload = payload or {}
    if payload.get("metrics"):
        return list(payload["metrics"])
    path = ctx.data_dir / "metrics.csv"
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def score_metrics(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    scored = []
    for row in rows:
        impressions = max(_num(row.get("impressions")), 1.0)
        likes = _num(row.get("likes"))
        comments = _num(row.get("comments"))
        shares = _num(row.get("shares"))
        clicks = _num(row.get("clicks"))
        engagement = likes + 3 * comments + 4 * shares + 2 * clicks
        scored.append({
            "topic_id": row.get("topic_id", ""),
            "title": row.get("title", ""),
            "format": row.get("format", "text"),
            "impressions": int(impressions),
            "engagement": int(engagement),
            "rate": round(engagement / impressions * 100, 2),
        })
    scored.sort(key=lambda r: -r["rate"])
    return scored


def derive_learnings(scored: list[dict[str, Any]]) -> list[str]:
    if not scored:
        return ["Pas encore assez de données : publier au moins 5 posts pour conclure."]
    best, worst = scored[0], scored[-1]
    learnings = [
        f"Le format « {best['format']} » performe le mieux (taux {best['rate']} %).",
        f"Le post « {best['title'] or best['topic_id']} » est la référence à répliquer.",
    ]
    if len(scored) > 1:
        learnings.append(
            f"Écart de performance x{round((best['rate'] or 0.01) / max(worst['rate'], 0.01), 1)} "
            f"entre le meilleur et le moins bon post."
        )
    average = sum(s["rate"] for s in scored) / len(scored)
    learnings.append(f"Taux d'engagement moyen : {round(average, 2)} %.")
    return learnings


def recommendations(scored: list[dict[str, Any]]) -> list[str]:
    recos = ["Doubler la fréquence du format le plus performant."]
    if scored:
        best_format = scored[0]["format"]
        recos.append(f"Réutiliser la structure du post « {scored[0]['title'] or scored[0]['topic_id']} » "
                     f"dans les prochains contenus {best_format}.")
    low = [s for s in scored if s["rate"] < 1.0]
    if low:
        recos.append(f"{len(low)} post(s) sous 1 % d'engagement : retravailler l'accroche.")
    return recos


@agent("analyst", "Analyste", 11)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    rows = load_metrics(ctx, payload)
    scored = score_metrics(rows)
    learnings = derive_learnings(scored)
    recos = recommendations(scored)

    result = {"posts": len(scored), "ranking": scored,
              "learnings": learnings, "recommendations": recos}
    out = write_json(ctx.reports_dir / "analyse.json", result)

    state = ctx.load_state()
    state["learnings"] = learnings[-20:]
    ctx.save_state(state)
    ctx.log("analyst", "analyse", {"posts": len(scored)})

    return AgentResult(
        agent="analyst",
        ok=bool(scored),
        summary=f"{len(scored)} post(s) analysé(s), {len(learnings)} apprentissage(s)",
        data=result,
        outputs=[str(out)],
    )
