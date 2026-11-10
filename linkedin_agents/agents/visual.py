"""Agent 6 — Visuel : brief d'image / carrousel et texte alternatif accessible."""
from __future__ import annotations

from typing import Any

from ..context import Context, read_text, slugify
from .base import AgentResult, agent, body_without_frontmatter, frontmatter

PALETTES = [
    {"name": "bleu nuit", "bg": "#0B1220", "fg": "#E8EEF9", "accent": "#4C8DFF"},
    {"name": "sable", "bg": "#F6F1E7", "fg": "#1F1B16", "accent": "#C2673A"},
    {"name": "vert profond", "bg": "#0E1F1A", "fg": "#E6F4EC", "accent": "#38E07B"},
]


def split_slides(body: str, max_slides: int = 8) -> list[str]:
    """Découpe le corps en slides : paragraphes, puis phrases longues."""
    body = "\n\n".join(block for block in body.split("\n\n")
                        if block.strip() and not block.strip().startswith("#"))
    blocks = [b.strip() for b in body.split("\n\n") if b.strip()]
    slides: list[str] = []
    for block in blocks:
        if len(block) <= 180:
            slides.append(block)
        else:
            slides.extend(s.strip() for s in block.split(". ") if s.strip())
    return slides[:max_slides] or [body[:180]]


def build_brief(path, index: int) -> dict[str, Any]:
    raw = read_text(path)
    meta = frontmatter(raw)
    body = body_without_frontmatter(raw)
    palette = PALETTES[index % len(PALETTES)]
    fmt = meta.get("format", "text")
    slides = split_slides(body) if fmt == "carrousel" else []
    title = meta.get("title", path.stem)

    alt = f"Visuel pour le post « {title} ». " + (
        f"Carrousel de {len(slides)} slides résumant : {slides[0][:120]}…"
        if slides else "Image d'illustration sobre avec le titre du post."
    )

    return {
        "file": str(path),
        "format": fmt,
        "title": title,
        "palette": palette,
        "headline": title[:90],
        "subline": ((slides[1].replace("\n", " ")[:110] if len(slides) > 1
                     else "Un conseil concret, sans jargon.")),
        "slides": [{"n": i + 1, "text": s[:180]} for i, s in enumerate(slides)],
        "alt_text": alt,
        "prompt": (
            f"Visuel LinkedIn {fmt}, palette {palette['name']} "
            f"(fond {palette['bg']}, texte {palette['fg']}, accent {palette['accent']}), "
            f"titre « {title[:80]} », typographie sans-serif épaisse, composition minimaliste, "
            "aucun logo inventé, aucun visage réel."
        ),
    }


@agent("visual", "Visuel", 6)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    payload = payload or {}
    if payload.get("file"):
        from pathlib import Path
        files = [Path(payload["file"])]
        if not files[0].is_absolute():
            files[0] = ctx.root / files[0]
    else:
        files = sorted(ctx.drafts_dir.glob("*.md"))

    if not files:
        return AgentResult(agent="visual", ok=False, summary="Aucun brouillon à illustrer.")

    briefs = [build_brief(path, i) for i, path in enumerate(files)]
    out = ctx.reports_dir / "visuels.json"
    import json
    out.write_text(json.dumps(briefs, ensure_ascii=False, indent=2), encoding="utf-8")
    ctx.log("visual", "briefs", {"count": len(briefs)})

    return AgentResult(
        agent="visual",
        ok=True,
        summary=f"{len(briefs)} brief(s) visuel(s) généré(s)",
        data={"briefs": briefs},
        outputs=[str(out)],
    )
