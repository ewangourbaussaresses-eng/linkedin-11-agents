"""Orchestrateur : enchaîne les 11 agents et produit un rapport de run."""
from __future__ import annotations

import json
from typing import Any, Callable

from .agents import registry
from .agents import analyst, audience, editor, engagement, publisher  # noqa: F401
from .agents import scheduler, strategist, supervisor, visual, watch, writer  # noqa: F401
from .context import Context, now_utc, write_json
from .agents.base import AgentResult

#: Ordre nominal du pipeline (les agents 8 et 9 sont optionnels en pipeline).
PIPELINE = ["watch", "audience", "strategist", "writer", "editor", "visual",
            "scheduler", "supervisor", "publisher", "engagement", "analyst"]


def agents_list() -> list[dict[str, Any]]:
    return [
        {"key": key, "label": meta["label"], "order": meta["order"]}
        for key, meta in sorted(registry.items(), key=lambda kv: kv[1]["order"])
    ]


def run_agent(ctx: Context, key: str, payload: dict[str, Any] | None = None) -> AgentResult:
    if key not in registry:
        raise KeyError(f"Agent inconnu : {key}. Disponibles : {', '.join(registry)}")
    ctx.ensure_dirs()
    return registry[key]["fn"](ctx, payload or {})


def run_pipeline(ctx: Context, steps: list[str] | None = None,
                 dry_run: bool = True, publish: bool = True,
                 on_step: Callable[[str, AgentResult], None] | None = None) -> dict[str, Any]:
    """Exécute les agents dans l'ordre et propage les sorties utiles."""
    ctx.dry_run = dry_run
    steps = steps or [s for s in PIPELINE if publish or s != "publisher"]
    results: list[AgentResult] = []
    carry: dict[str, Any] = {}

    for key in steps:
        payload: dict[str, Any] = {}
        if key == "strategist":
            payload = {"angles": carry.get("watch", {}).get("angles"),
                       "audience": carry.get("audience", {})}
        elif key == "writer":
            payload = {"plan": carry.get("strategist")}
        elif key in ("editor", "visual", "supervisor"):
            payload = {"files": carry.get("writer", {}).get("files")}
        elif key == "scheduler":
            payload = {"plan": carry.get("strategist"), "drafts": carry.get("writer")}
        elif key == "publisher":
            payload = {"dry_run": dry_run, "files": carry.get("supervisor", {}).get("approved_files")}

        result = run_agent(ctx, key, payload)
        results.append(result)

        data = result.data or {}
        if key == "watch":
            carry["watch"] = data
        elif key == "audience":
            carry["audience"] = data
        elif key == "strategist":
            carry["strategist"] = data
        elif key == "writer":
            carry["writer"] = {"drafts": data.get("drafts", []),
                               "files": [d["file"] for d in data.get("drafts", [])]}
        elif key == "supervisor":
            carry["supervisor"] = {
                "approved_files": [v["file"] for v in data.get("verdicts", [])
                                   if v.get("verdict") == "approuve"],
            }
        elif key == "publisher":
            carry["publisher"] = data

        if on_step:
            on_step(key, result)

    report = {
        "run_at": now_utc().isoformat(timespec="seconds"),
        "dry_run": dry_run,
        "steps": [r.as_dict() for r in results],
    }
    write_json(ctx.workspace / "reports" / f"run_{now_utc():%Y%m%d_%H%M%S}.json", report)
    ctx.log("pipeline", "run", {"steps": len(results), "dry_run": dry_run})
    return report


def format_report(report: dict[str, Any]) -> str:
    lines = ["", "═" * 62,
             f"  PIPELINE LINKEDIN — {report['run_at']}"
             f" {'(simulation)' if report['dry_run'] else '(réel)'}",
             "═" * 62]
    for step in report["steps"]:
        mark = "✔" if step["ok"] else "✖"
        lines.append(f" {mark} {step['agent']:<12} {step['summary']}")
    lines.append("═" * 62)
    return "\n".join(lines)


def report_json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2)
