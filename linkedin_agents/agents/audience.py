"""Agent 2 — Audience : personas, créneaux et formats qui fonctionnent.

Entrée attendue : un CSV d'export LinkedIn (ou de données d'engagement) avec au moins
une colonne `role`, `seniority`, `industry`, `hour`, `likes`, `comments`, `impressions`.
Les colonnes manquantes sont ignorées.
"""
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from typing import Any

from ..context import Context, write_json
from .base import AgentResult, agent


def read_csv_rows(path) -> list[dict[str, str]]:
    try:
        with open(path, encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))
    except OSError:
        return []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def analyse_rows(rows: list[dict[str, str]]) -> dict[str, Any]:
    roles = Counter(r.get("role", "").strip() for r in rows if r.get("role", "").strip())
    seniority = Counter(r.get("seniority", "").strip() for r in rows if r.get("seniority", "").strip())
    industries = Counter(r.get("industry", "").strip() for r in rows if r.get("industry", "").strip())

    engagement_by_hour: dict[str, dict[str, int]] = defaultdict(lambda: {"posts": 0, "engagement": 0})
    for row in rows:
        hour = (row.get("hour") or "").strip()[:2]
        if not hour.isdigit():
            continue
        bucket = engagement_by_hour[hour]
        bucket["posts"] += 1
        bucket["engagement"] += _int(row.get("likes")) + 2 * _int(row.get("comments"))

    hours = sorted(
        (
            {"hour": f"{hour}:00", "posts": v["posts"],
             "engagement": v["engagement"],
             "avg": round(v["engagement"] / max(v["posts"], 1), 1)}
            for hour, v in engagement_by_hour.items()
        ),
        key=lambda h: h["avg"],
        reverse=True,
    )

    formats = Counter(r.get("format", "").strip() for r in rows if r.get("format", "").strip())

    personas = [
        {
            "name": f"{role} · {industry or 'tous secteurs'}",
            "role": role,
            "industry": industry or "—",
            "share": round(count / max(len(rows), 1) * 100, 1),
            "pain_point": f"Manque de temps pour traiter les sujets {industry or 'métier'}",
        }
        for (role, industry), count in Counter(
            (r.get("role", "").strip() or "Inconnu", r.get("industry", "").strip())
            for r in rows
        ).most_common(4)
    ]

    return {
        "rows": len(rows),
        "roles": roles.most_common(8),
        "seniority": seniority.most_common(6),
        "industries": industries.most_common(6),
        "best_hours": hours[:5],
        "formats": formats.most_common(6),
        "personas": personas,
    }


@agent("audience", "Audience", 2)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    rows: list[dict[str, str]] = []
    source = None

    if payload and payload.get("rows"):
        rows = list(payload["rows"])
    else:
        candidates = [ctx.data_dir / "audience.csv", ctx.data_dir / "audience.example.csv"]
        for path in candidates:
            if path.exists():
                rows = read_csv_rows(path)
                source = str(path)
                break

    analysis = analyse_rows(rows)
    analysis["source"] = source
    output = write_json(ctx.reports_dir / "audience.json", analysis)
    ctx.log("audience", "analyse", {"rows": len(rows)})

    best = analysis["best_hours"][0]["hour"] if analysis["best_hours"] else "n/a"
    return AgentResult(
        agent="audience",
        ok=bool(rows),
        summary=f"{len(rows)} profil(s) analysé(s), meilleur créneau : {best}",
        data=analysis,
        outputs=[str(output)],
    )
