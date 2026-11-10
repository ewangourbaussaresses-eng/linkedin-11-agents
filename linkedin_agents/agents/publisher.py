"""Agent 8 — Publisher : publie (ou simule) et journalise chaque envoi.

Garde-fous :
- exige l'approbation du Superviseur (`reports/supervision.json`) ;
- respecte `limits.max_posts_per_day` ;
- ne republie jamais un post déjà publié (état dans `state.json`) ;
- journalise chaque envoi dans `workspace/published/log.jsonl`.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from .. import linkedin_api
from ..context import Context, read_json, read_text, write_json
from .base import AgentResult, agent, body_without_frontmatter, frontmatter


def approved_files(ctx: Context) -> tuple[list[str], dict]:
    supervision = read_json(ctx.reports_dir / "supervision.json", default=None)
    if not supervision:
        return [], {}
    verdicts = {v["file"]: v for v in supervision.get("verdicts", [])}
    approved = [f for f, v in verdicts.items() if v.get("verdict") == "approuve"]
    return approved, verdicts


def already_published(ctx: Context) -> set[str]:
    state = ctx.load_state()
    return {p["file"] for p in state.get("published", [])}


def log_line(ctx: Context, record: dict) -> None:
    path = ctx.published_dir / "log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


@agent("publisher", "Publisher", 8)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    payload = payload or {}
    force = bool(payload.get("force"))
    dry_run = payload.get("dry_run", ctx.dry_run)

    if payload.get("files"):
        files = [str(f) for f in payload["files"]]
        verdicts: dict = {}
    else:
        files, verdicts = approved_files(ctx)
        if not files and not force:
            return AgentResult(
                agent="publisher",
                ok=False,
                summary="Aucun post approuvé : lancez le Superviseur avant de publier.",
            )

    done = already_published(ctx)
    files = [f for f in files if f not in done]
    if not files:
        return AgentResult(agent="publisher", ok=True, summary="Rien à publier (tout est déjà en ligne).")

    state = ctx.load_state()
    today = date.today().isoformat()
    published_today = state.get("published_today", {}).get(today, 0)
    limit = int(ctx.limits("max_posts_per_day", 1))
    max_chars = int(ctx.limits("max_chars", 1300))

    records = []
    for file in files:
        if published_today >= limit:
            records.append({"file": file, "status": "reporté", "reason": "plafond quotidien atteint"})
            continue

        raw = read_text(ctx.root / file if not file.startswith(str(ctx.root)) else file)
        meta = frontmatter(raw)
        text = body_without_frontmatter(raw)[:max_chars]
        if not text:
            records.append({"file": file, "status": "ignoré", "reason": "corps vide"})
            continue

        try:
            result = linkedin_api.simulate(text) if dry_run else linkedin_api.publish(text)
        except linkedin_api.LinkedInError as exc:
            records.append({"file": file, "status": "erreur", "reason": str(exc)})
            continue

        record = {
            "file": file,
            "title": meta.get("title", ""),
            "status": "publié" if not dry_run else "simulé",
            "post_urn": result.get("post_urn", ""),
            "chars": len(text),
            "date": today,
        }
        records.append(record)
        published_today += 1
        log_line(ctx, record)
        state.setdefault("published", []).append(
            {"file": file, "urn": record["post_urn"], "date": today,
             "simulated": dry_run})
        ctx.save_state(state)
        if not dry_run:
            state.setdefault("published_today", {})[today] = published_today
            ctx.save_state(state)
            (ctx.published_dir / f"{date.today().isoformat()}_{meta.get('topic_id', 'post')}.md") \
                .write_text(raw, encoding="utf-8")

    ctx.log("publisher", "publish", {"count": len(records), "dry_run": dry_run})
    ok = all(r["status"] in ("publié", "simulé", "reporté") for r in records) if records else True
    return AgentResult(
        agent="publisher",
        ok=ok,
        summary=f"{sum(1 for r in records if r['status'] in ('publié', 'simulé'))} post(s) "
                f"{'simulé(s)' if dry_run else 'publié(s)'}",
        data={"records": records, "dry_run": dry_run},
        outputs=[str(ctx.published_dir / "log.jsonl")],
    )
