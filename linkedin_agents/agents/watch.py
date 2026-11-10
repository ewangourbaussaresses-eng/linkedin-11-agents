"""Agent 1 — Veille : tendances, sources d'inspiration et angles possibles."""
from __future__ import annotations

import re
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

from ..context import Context, read_json, write_json
from .base import AgentResult, agent, keywords

USER_AGENT = "linkedin-11-agents/1.0"


def _parse_feed(xml_text: str) -> list[dict[str, str]]:
    """Parseur RSS/Atom minimal, sans dépendance."""
    items: list[dict[str, str]] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items

    atom = "{http://www.w3.org/2005/Atom}"
    if root.tag == atom + "feed":
        for entry in root.findall(atom + "entry"):
            link = entry.find(atom + "link")
            items.append({
                "title": (entry.findtext(atom + "title") or "").strip(),
                "link": (link.get("href") if link is not None else ""),
                "summary": (entry.findtext(atom + "summary") or "").strip(),
            })
        return items

    channel = root.find("channel")
    if channel is None:
        channel = root
    for item in channel.findall("item"):
        items.append({
            "title": (item.findtext("title") or "").strip(),
            "link": (item.findtext("link") or "").strip(),
            "summary": (item.findtext("description") or "").strip(),
        })
    return items


def fetch_source(url: str, timeout: int = 10) -> list[dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return _parse_feed(response.read().decode("utf-8", errors="replace"))


def load_sources(ctx: Context, payload: dict[str, Any] | None) -> list[dict[str, str]]:
    """Sources : payload > data/sources.json > flux réseau listés dans ce fichier."""
    if payload and payload.get("items"):
        return list(payload["items"])

    raw = read_json(ctx.data_dir / "sources.json", default=None)
    if isinstance(raw, list):
        return raw

    items: list[dict[str, str]] = []
    for url in (raw or {}).get("feeds", []):
        try:
            items.extend(fetch_source(url))
        except Exception:  # noqa: BLE001 - une source cassée ne bloque pas la veille
            continue
    return items


def normalize_title(title: str) -> str:
    """Retire le bruit typographique des titres d'articles."""
    title = re.sub(r"^(le|la|les|l')\s+", "", title.strip(), flags=re.IGNORECASE)
    title = re.sub(r"^[\W_]+|[\W_]+$", "", title)
    return title.strip()


def build_angles(items: list[dict[str, str]], pillars: list[str], top: int = 8) -> list[dict[str, Any]]:
    """Transforme les titres en angles éditoriaux classés par pilier.

    L'angle reprend le titre nettoyé (lisible, sans calcul de fréquence) et le relie
    au pilier de marque correspondant par rotation.
    """
    angles: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        title = normalize_title(item.get("title", ""))
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        pillar = pillars[len(angles) % len(pillars)] if pillars else "Général"
        angles.append({
            "theme": title,
            "pillar": pillar,
            "relevance": 1,
            "angle": f"{title} — ce que ça change concrètement",
            "source": item.get("link", ""),
        })
        if len(angles) >= top:
            break

    if not angles:  # repli : mots-clés du corpus
        corpus = " ".join(f"{i.get('title', '')} {i.get('summary', '')}" for i in items)
        for index, (theme, score) in enumerate(keywords(corpus, top=top)):
            pillar = pillars[index % len(pillars)] if pillars else "Général"
            angles.append({"theme": theme, "pillar": pillar, "relevance": score,
                           "angle": f"{theme.capitalize()} : ce que ça change concrètement"})
    return angles


@agent("watch", "Veille", 1)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    items = load_sources(ctx, payload)
    pillars = ctx.brand.get("pillars", [])
    angles = build_angles(items, pillars)

    output = write_json(ctx.reports_dir / "veille.json", {"items": items, "angles": angles})
    ctx.log("watch", "veille", {"items": len(items), "angles": len(angles)})

    return AgentResult(
        agent="watch",
        ok=bool(angles),
        summary=f"{len(items)} source(s) analysée(s), {len(angles)} angle(s) retenu(s)",
        data={"items": items, "angles": angles},
        outputs=[str(output)],
    )
