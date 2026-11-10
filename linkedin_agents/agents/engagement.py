"""Agent 9 — Engagement : réponses aux commentaires et commentaires à laisser.

Entrée : `data/comments.json` (liste de {author, text, post}) ou `payload["comments"]`.
Sortie : réponses suggérées (ton de la marque), priorisation, et 3 commentaires utiles
à laisser chez d'autres.
"""
from __future__ import annotations

from typing import Any

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

    replies = sorted((suggest_reply(c, ctx.brand) for c in comments),
                     key=lambda r: -r["priority"])
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
