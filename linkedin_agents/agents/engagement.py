"""Agent 9 — Engagement : réponses aux commentaires et commentaires à laisser.

Entrée : `data/comments.json` (liste de {author, text, post}) ou `payload["comments"]`.
Sortie : réponses suggérées (ton de la marque), priorisation, et 3 commentaires utiles
à laisser chez d'autres.
"""
from __future__ import annotations

import json
from typing import Any

from .. import llm
from ..context import Context, read_json, write_json
from .base import AgentResult, agent

QUESTION_MARKERS = ("?", "comment", "pourquoi", "quel", "quelle", "est-ce")
NEGATIVE = ("non", "faux", "d'accord mais", "pas convaincu", "erreur", "problème")


def classify(comment: str) -> str:
    low = comment.lower()
    if any(m in low for m in QUESTION_MARKERS):
        return "question"
    if any(m in low for m in NEGATIVE):
        return "objection"
    if any(w in low for w in ("merci", "bravo", "excellent", "super")):
        return "félicitation"
    return "réaction"


def suggest_reply(comment: dict, brand: dict) -> dict[str, Any]:
    kind = classify(comment.get("text", ""))
    author = comment.get("author", "vous").strip()
    # « Sophie L. » -> « Sophie » (un prénom suffit, plus naturel)
    author = author.split()[0] if author.split() else "vous"
    author = author.rstrip(".,")
    theme = comment.get("theme") or "le sujet"

    replies = {
        "question": f"Bonne question {author}. En pratique, on commence par mesurer {theme} "
                    "sur deux semaines, puis on décide. Je détaille la méthode si ça vous intéresse.",
        "objection": f"Point pris {author}. Notre expérience diffère sur un point : {theme} dépend "
                     "beaucoup du contexte. Qu'est-ce qui s'est passé de votre côté ?",
        "félicitation": f"Merci {author} ! Si vous voulez la version détaillée, dites-le, je partage.",
        "réaction": f"Merci pour ce retour {author}. Ça rejoint ce qu'on observe sur {theme}.",
    }
    return {
        "author": author,
        "type": kind,
        "priority": {"question": 3, "objection": 2, "réaction": 1, "félicitation": 0}[kind],
        "reply": replies[kind],
    }


ENGAGEMENT_SYSTEM = (
    "Tu es responsable community management d'une PME française. Tu réponds aux "
    "commentaires LinkedIn avec tact : court, utile, jamais commercial à outrance, "
    "jamais agressif envers une objection. Tu réponds UNIQUEMENT en JSON."
)


def suggest_replies_with_llm(comments: list[dict], brand: dict) -> list[dict] | None:
    """Réponses personnalisées via Claude. None si le LLM est indisponible."""
    if not comments:
        return None
    payload = [{"author": c.get("author", ""), "text": c.get("text", ""),
                "theme": c.get("theme", "")} for c in comments[:10]]
    prompt = f"""Voici des commentaires reçus sur des posts LinkedIn.
Voix de marque : {brand.get('voice', 'directe, concrète')}
Termes interdits : {', '.join(brand.get('forbidden', [])) or 'aucun'}

Commentaires :
{json.dumps(payload, ensure_ascii=False, indent=2)}

Pour CHACUN, écris une réponse de 1 à 3 phrases, prête à publier.
Réponds uniquement avec ce JSON :
[{{"author": "...", "type": "question|objection|félicitation|réaction", "reply": "..."}}]"""

    response = llm.complete_or_none(prompt, system=ENGAGEMENT_SYSTEM,
                                    max_tokens=900, temperature=0.7)
    if response is None:
        return None
    try:
        data = llm.extract_json(response.text)
    except llm.LLMError:
        return None
    if not isinstance(data, list):
        return None

    priority = {"question": 3, "objection": 2, "réaction": 1, "félicitation": 0}
    results = []
    for item in data:
        if not isinstance(item, dict) or not item.get("reply"):
            continue
        kind = item.get("type") if item.get("type") in priority else classify(str(item["reply"]))
        results.append({
            "author": str(item.get("author", "")),
            "type": kind,
            "priority": priority[kind],
            "reply": str(item["reply"]).strip(),
            "generated_by": f"llm:{response.provider}",
        })
    return results or None


def build_outreach(brand: dict) -> list[dict[str, str]]:
    pillars = brand.get("pillars", ["Expertise métier"])
    return [
        {"target": "post d'un confrère du secteur",
         "comment": f"Très juste sur {pillars[0].lower()}. On a vu le même effet côté PME."},
        {"target": "post d'un client ou partenaire",
         "comment": "Merci pour ce partage, ça complète bien ce qu'on observe sur le terrain."},
        {"target": "post d'un média spécialisé",
         "comment": f"Article utile. Une nuance : {pillars[-1].lower()} demande souvent plus de temps qu'annoncé."},
    ]


@agent("engagement", "Engagement", 9)
def run(ctx: Context, payload: dict[str, Any] | None = None) -> AgentResult:
    payload = payload or {}
    comments = payload.get("comments")
    if comments is None:
        comments = read_json(ctx.data_dir / "comments.json", default=[]) or []

    replies = None
    if payload.get("use_llm", True) and llm.is_available():
        replies = suggest_replies_with_llm(comments, ctx.brand)
    if replies is None:
        replies = [suggest_reply(c, ctx.brand) for c in comments]
    replies = sorted(replies, key=lambda r: -r["priority"])
    result = {
        "comments": len(comments),
        "replies": replies,
        "outreach": build_outreach(ctx.brand),
    }
    out = write_json(ctx.reports_dir / "engagement.json", result)
    ctx.log("engagement", "replies", {"comments": len(comments)})

    return AgentResult(
        agent="engagement",
        ok=True,
        summary=f"{len(replies)} réponse(s) préparée(s), {len(result['outreach'])} commentaire(s) de prospection",
        data=result,
        outputs=[str(out)],
    )
