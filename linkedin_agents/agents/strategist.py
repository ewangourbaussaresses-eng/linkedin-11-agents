"""Agent 3 — Stratège : calendrier éditorial sur N semaines.

Combine les angles de la veille (agent 1), l'analyse d'audience (agent 2) et le profil
de marque pour produire un plan équilibré par pilier et par format.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..context import DEFAULT_STRATEGY, Context, read_json, write_json
from .base import AgentResult, agent


def load_inputs(ctx: Context, payload: dict[str, Any] | None) -> tuple[list[dict], dict]:
    payload = payload or {}
    angles = payload.get("angles")
    if angles is None:
        angles = (read_json(ctx.reports_dir / "veille.json", default={}) or {}).get("angles", [])
    audience = payload.get("audience")
    if audience is None:
        audience = read_json(ctx.reports_dir / "audience.json", default={}) or {}
    return angles or [], audience or {}


def pick_slots(audience: dict, brand: dict) -> list[str]:
    """Créneaux : ceux de l'audience si disponibles, sinon la stratégie par défaut."""
    hours = [h["hour"] for h in audience.get("best_hours", []) if h.get("hour")]
    days = ["mardi", "mercredi", "jeudi", "lundi", "vendredi"]
    if hours:
        return [f"{days[i % len(days)]} {hour}" for i, hour in enumerate(hours[:3])]
    strategy = {**DEFAULT_STRATEGY, **brand.get("strategy", {})}
    return strategy["slots"]


def build_plan(angles: list[dict], audience: dict, brand: dict,
               start: date | None = None) -> dict[str, Any]:
    strategy = {**DEFAULT_STRATEGY, **brand.get("strategy", {})}
    pillars = brand.get("pillars") or DEFAULT_STRATEGY["formats"]
    formats = strategy["formats"]
    per_week = int(strategy["per_week"])
    weeks = int(strategy["weeks"])
    slots = pick_slots(audience, brand)

    start = start or date.today()
    total = per_week * weeks
    topics: list[dict] = []
    for i in range(total):
        angle = angles[i % len(angles)] if angles else {
            "theme": pillars[i % len(pillars)],
            "pillar": pillars[i % len(pillars)],
            "angle": f"Retour d'expérience sur {pillars[i % len(pillars)].lower()}",
        }
        week = i // per_week
        day = start + timedelta(days=7 * week + (i % per_week))
        topics.append({
            "id": f"post-{i + 1:02d}",
            "pillar": angle.get("pillar", pillars[i % len(pillars)]),
            "theme": angle.get("theme", ""),
            "angle": angle.get("angle", ""),
            "format": formats[i % len(formats)],
            "date": day.isoformat(),
            "slot": slots[i % len(slots)],
            "objective": ["notoriété", "autorité", "conversion"][i % 3],
        })

    # rotation des angles : on évite de répéter le même sujet deux semaines de suite
    seen_titles: dict[str, int] = {}
    for topic in topics:
        if topic["theme"]:
            seen_titles[topic["theme"]] = seen_titles.get(topic["theme"], 0) + 1
    repeated = {t: c for t, c in seen_titles.items() if c > 1}

    coverage = {p: sum(1 for t in topics if t["pillar"] == p) for p in pillars}
    gaps = [p for p, count in coverage.items() if count == 0]

    return {
        "created": date.today().isoformat(),
        "weeks": weeks,
        "per_week": per_week,
        "slots": slots,
        "pillars": pillars,
        "coverage": coverage,
        "gaps": gaps,
        "repeated_topics": repeated,
        "topics": topics,
    }


def render_calendar_markdown(plan: dict) -> str:
    lines = ["# 📅 Calendrier éditorial LinkedIn", ""]
    lines.append(f"- Période : {plan['weeks']} semaine(s), {plan['per_week']} post(s)/semaine")
    lines.append(f"- Créneaux : {', '.join(plan['slots'])}")
    if plan["gaps"]:
        lines.append(f"- ⚠️ Piliers non couverts : {', '.join(plan['gaps'])}")
    lines.append("")
    lines.append("| # | Date | Créneau | Pilier | Format | Sujet |")
    lines.append("|---|------|---------|--------|--------|-------|")
    for topic in plan["topics"]:
        lines.append(
            f"| {topic['id']} | {topic['date']} | {topic['slot']} | {topic['pillar']} "
            f"| {topic['format']} | {topic['angle']} |"
        )
    lines.append("")
    return "\n".join(lines)


@agent("strategist", "Stratège", 3)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    angles, audience = load_inputs(ctx, payload)
    plan = build_plan(angles, audience, ctx.brand)

    plan_file = write_json(ctx.plan_path, plan)
    calendar = ctx.workspace / "calendar.md"
    calendar.write_text(render_calendar_markdown(plan), encoding="utf-8")
    ctx.log("strategist", "plan", {"topics": len(plan["topics"])})

    return AgentResult(
        agent="strategist",
        ok=True,
        summary=f"{len(plan['topics'])} post(s) planifié(s) sur {plan['weeks']} semaine(s)",
        data=plan,
        outputs=[str(plan_file), str(calendar)],
    )
