"""Agent 7 — Programmateur : cale chaque brouillon sur un créneau et produit la file."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..context import Context, read_json, read_text, write_json
from .base import AgentResult, agent, frontmatter

WEEKDAYS = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3, "vendredi": 4,
    "samedi": 5, "dimanche": 6,
}


def parse_slot(slot: str) -> tuple[int | None, int, int]:
    """'mardi 08:30' -> (1, 8, 30). '08:30' -> (None, 8, 30)."""
    day, _, hour = slot.partition(" ")
    if not hour:
        day, hour = "", slot
    weekday = WEEKDAYS.get(day.strip().lower())
    hh, _, mm = hour.strip().partition(":")
    return weekday, int(hh or 8), int(mm or 0)


def queue_entries(ctx: Context, payload: dict[str, Any] | None) -> dict[str, Any]:
    payload = payload or {}
    plan = payload.get("plan") or read_json(ctx.plan_path, default={}) or {}
    slots = plan.get("slots") or ["mardi 08:30"]
    plan_topics = {t["id"]: t for t in plan.get("topics", [])}

    raw_drafts = payload.get("drafts") or []
    drafts = raw_drafts.get("files") if isinstance(raw_drafts, dict) else raw_drafts
    files = ([d["file"] if isinstance(d, dict) else str(d) for d in drafts]
             if drafts else [str(p) for p in sorted(ctx.drafts_dir.glob("*.md"))])

    queue = []
    for index, file in enumerate(files):
        meta = frontmatter(read_text(file))
        topic = plan_topics.get(meta.get("topic_id", ""), {})
        slot = topic.get("slot") or meta.get("slot") or slots[index % len(slots)]
        date_str = topic.get("date") or meta.get("date") or datetime.now().date().isoformat()
        weekday, hh, mm = parse_slot(slot)

        try:
            day = datetime.fromisoformat(date_str)
        except ValueError:
            day = datetime.now()
        day = day.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if weekday is not None:
            day = day + timedelta(days=(weekday - day.weekday()) % 7)

        queue.append({
            "file": file,
            "title": meta.get("title", ""),
            "format": meta.get("format", "text"),
            "status": meta.get("status", "draft"),
            "slot": slot,
            "scheduled_at": day.isoformat(timespec="minutes"),
        })

    queue.sort(key=lambda e: e["scheduled_at"])
    return {"queue": queue, "slots": slots}


@agent("scheduler", "Programmateur", 7)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    result = queue_entries(ctx, payload)
    out = write_json(ctx.workspace / "queue.json", result)
    ctx.log("scheduler", "queue", {"count": len(result["queue"])})

    first = result["queue"][0]["scheduled_at"] if result["queue"] else "—"
    return AgentResult(
        agent="scheduler",
        ok=bool(result["queue"]),
        summary=f"{len(result['queue'])} post(s) programmé(s), premier : {first}",
        data=result,
        outputs=[str(out)],
    )
