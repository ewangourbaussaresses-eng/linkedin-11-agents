"""Agent 4 — Rédacteur : produit des posts dans la voix de la marque.

Il utilise des gabarits structurés (accroche → tension → preuve → action → CTA) et les
angles du plan. Le texte reste du Markdown avec front-matter, prêt pour l'éditeur.
"""
from __future__ import annotations

import re
from typing import Any

from .. import llm
from ..context import Context, read_json, slugify
from .base import AgentResult, agent, keywords

HOOKS = {
    "notoriété": "Personne ne parle de {theme}. C'est bien le problème.",
    "autorité": "J'ai vu {theme} échouer trois fois cette année. Voici pourquoi.",
    "conversion": "Si {theme} vous coûte du temps, cette méthode change tout.",
}

BODIES = {
    "Expertise métier": [
        "Sur le terrain, {theme} se joue rarement là où on l'attend.",
        "Trois choses que nous avons apprises :",
        "1. Mesurer avant de décider.",
        "2. Documenter ce qui fonctionne.",
        "3. Revoir le processus tous les trimestres.",
    ],
    "Coulisses": [
        "Voici à quoi ressemble vraiment {theme} de l'intérieur.",
        "Les outils, les erreurs, les arbitrages : rien n'est linéaire.",
        "Ce que nous gardons : la simplicité.",
    ],
    "Conseils actionnables": [
        "Une méthode simple pour {theme} :",
        "1. Listez les 3 tâches qui vous coûtent le plus de temps.",
        "2. Automatisez la plus répétitive.",
        "3. Mesurez le gain sur deux semaines.",
    ],
    "Actualité du secteur": [
        "{theme} revient dans toutes les conversations.",
        "Ce qui change concrètement pour votre équipe :",
        "les priorités, les compétences, les outils.",
        "Le reste est du bruit.",
    ],
}

CTAS = {
    "notoriété": "Quel est votre point de vue ? Dites-le en commentaire.",
    "autorité": "Si vous voulez la checklist complète, écrivez « checklist » en commentaire.",
    "conversion": "Prenez 15 minutes cette semaine pour l'appliquer. Dites-moi ce que ça change.",
}


FEMININE_SUFFIXES = ("té", "tion", "sion", "ance", "ence", "ure", "ique", "ie", "esse")


def natural_theme(raw: str) -> str:
    """Transforme un titre d'article en groupe nominal naturel pour un post.

    « Cybersécurité : les PME sont la cible » -> « la cybersécurité »
    « L'IA générative entre dans les PME »     -> « l'IA générative »
    « Recrutement : les compétences IA »       -> « le recrutement »
    """
    theme = re.split(r"\s*[:—–]\s*", raw)[0].strip()
    theme = re.sub(r"\s+(entre|revient|change|devient|sont|est|dans|pour|avec|sur)\b.*$",
                   "", theme, flags=re.IGNORECASE).strip()
    words = theme.split()
    theme = " ".join(words[:3] if words and words[0][:2] in ("L'", "l'") else words[:2])
    if not theme:
        return "ce sujet"
    if theme[:2] in ("L'", "l'"):
        return "l'" + theme[2:]
    if theme.startswith(("le ", "la ", "les ", "l'", "un ", "une ", "des ")):
        return theme

    theme = theme[0].lower() + theme[1:]
    first = theme.split()[0]
    if theme[0] in "aeiouéèêàh":
        article = "l'"
    elif first.endswith(FEMININE_SUFFIXES) or first == "données":
        article = "la "
    else:
        article = "le "
    return f"{article}{theme}"


WRITER_SYSTEM = (
    "Tu es rédacteur LinkedIn senior pour une PME française. Tu écris des posts courts, "
    "concrets, sans jargon creux ni superlatif. Style : phrases courtes, exemples concrets, "
    "une seule idée par post. Jamais de promesse de résultat. Tu réponds UNIQUEMENT en JSON."
)


def build_post_with_llm(topic: dict, brand: dict) -> dict[str, Any] | None:
    """Rédige un post via Claude (ou OpenAI). Retourne None si le LLM est indisponible."""
    theme = topic.get("theme") or topic.get("pillar", "ce sujet")
    pillar = topic.get("pillar", "Expertise métier")
    objective = topic.get("objective", "notoriété")
    forbidden = ", ".join(brand.get("forbidden", [])) or "aucun"
    hashtags = " ".join(brand.get("hashtags", []))

    prompt = f"""Écris un post LinkedIn en français.

Sujet / angle : {theme}
Pilier de marque : {pillar}
Objectif : {objective}
Audience : {brand.get('audience', 'dirigeants de PME')}
Voix de marque : {brand.get('voice', 'directe, concrète')}
Hashtags imposés : {hashtags or "libre"}
Termes INTERDITS : {forbidden}
Contrainte : 600 à 1300 caractères, 4 à 7 lignes, une seule idée directrice.

Réponds avec ce JSON exact, sans texte autour :
{{"title": "titre court du post (max 80 caractères)",
  "hook": "première ligne accrocheuse",
  "body": "le post complet prêt à publier, avec hashtags à la fin",
  "cta": "la question ou l'appel à l'action final",
  "hashtags": ["#Exemple"]}}"""

    response = llm.complete_or_none(prompt, system=WRITER_SYSTEM,
                                    max_tokens=900, temperature=0.8)
    if response is None:
        return None

    try:
        data = llm.extract_json(response.text)
    except llm.LLMError:
        return None
    if not isinstance(data, dict) or not str(data.get("body", "")).strip():
        return None

    body = str(data["body"]).strip()[: int(brand.get("limits", {}).get("max_chars", 1300))]
    tags = [t for t in (data.get("hashtags") or []) if isinstance(t, str) and t.startswith("#")]
    if not tags:
        tags = [t for t in brand.get("hashtags", [])][:3]
        body += "\n\n" + " ".join(tags)

    return {
        "title": str(data.get("title") or theme)[:90],
        "pillar": pillar,
        "format": topic.get("format", "text"),
        "objective": objective,
        "hook": str(data.get("hook") or body.splitlines()[0]),
        "body": body,
        "cta": str(data.get("cta") or ""),
        "hashtags": tags[:5],
        "chars": len(body),
        "topic_id": topic.get("id", ""),
        "date": topic.get("date", ""),
        "slot": topic.get("slot", ""),
        "generated_by": f"llm:{response.provider}/{response.model}",
    }


def build_post(topic: dict, brand: dict) -> dict[str, Any]:
    theme = natural_theme(topic.get("theme") or topic.get("pillar", "ce sujet"))
    pillar = topic.get("pillar", "Expertise métier")
    objective = topic.get("objective", "notoriété")

    hook = HOOKS.get(objective, HOOKS["notoriété"]).format(theme=theme)
    body_lines = [line.format(theme=theme) for line in BODIES.get(pillar, BODIES["Expertise métier"])]
    cta = CTAS.get(objective, CTAS["notoriété"])
    # Hashtag du pilier en tête, puis les hashtags de marque (max 4 au total).
    pillar_tag = "#" + "".join(c for c in pillar.title() if c.isalpha())
    tags = [pillar_tag] + [t for t in brand.get("hashtags", []) if t != pillar_tag][:3]

    # Le pilier est rappelé en fin de post : cohérence de marque lisible par le superviseur.
    body = "\n\n".join([hook, "\n".join(body_lines), cta])
    if tags:
        body += "\n\n" + " ".join(tags)

    return {
        "title": theme if len(theme) < 90 else theme[:87] + "…",
        "pillar": pillar,
        "format": topic.get("format", "text"),
        "objective": objective,
        "hook": hook,
        "body": body,
        "cta": cta,
        "hashtags": tags,
        "chars": len(body),
        "topic_id": topic.get("id", ""),
        "date": topic.get("date", ""),
        "slot": topic.get("slot", ""),
        "generated_by": "template",
    }


def render_markdown(post: dict) -> str:
    return "\n".join([
        "---",
        f"title: {post['title']}",
        f"pillar: {post['pillar']}",
        f"format: {post['format']}",
        "status: draft",
        f"topic_id: {post['topic_id']}",
        f"date: {post['date']}",
        f"slot: {post['slot']}",
        "---",
        "",
        post["body"],
        "",
    ])


@agent("writer", "Rédacteur", 4)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    payload = payload or {}
    brand = ctx.brand

    if payload.get("topic"):
        topics = [{
            "id": "ad-hoc",
            "theme": payload["topic"],
            "angle": payload["topic"],
            "pillar": payload.get("pillar", (brand.get("pillars") or ["Expertise métier"])[0]),
            "format": payload.get("format", "text"),
            "objective": payload.get("objective", "notoriété"),
        }]
    else:
        plan = payload.get("plan") or read_json(ctx.plan_path, default=None)
        if not plan:
            return AgentResult(agent="writer", ok=False,
                               summary="Aucun plan : lancez d'abord l'agent Stratège.")
        topics = plan.get("topics", [])
        limit = int(payload.get("limit", len(topics)))
        topics = topics[:limit]

    use_llm = payload.get("use_llm", True) and llm.is_available()
    created = []
    for topic in topics:
        post = (build_post_with_llm(topic, brand) if use_llm else None) or build_post(topic, brand)
        name = f"{post['topic_id'] or slugify(post['title'])}.md"
        path = ctx.drafts_dir / name
        path.write_text(render_markdown(post), encoding="utf-8")
        created.append({"file": str(path), **post})

    ctx.log("writer", "drafts", {"count": len(created), "llm": use_llm})
    generated = sum(1 for c in created if c.get("generated_by", "").startswith("llm:"))
    if generated:
        provider = llm.active_provider()
        engine = "Claude" if provider == "claude" else provider
        if generated < len(created):
            engine += f" ({len(created) - generated} en gabarits)"
    else:
        engine = "gabarits locaux"
    return AgentResult(
        agent="writer",
        ok=bool(created),
        summary=f"{len(created)} brouillon(s) rédigé(s) — {engine}",
        data={"drafts": created},
        outputs=[c["file"] for c in created],
    )
