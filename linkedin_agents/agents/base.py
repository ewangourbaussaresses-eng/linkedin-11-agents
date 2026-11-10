"""Socle commun des agents : résultat standardisé, registre, helpers texte."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from ..context import Context


@dataclass
class AgentResult:
    agent: str
    ok: bool = True
    summary: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    outputs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "ok": self.ok,
            "summary": self.summary,
            "data": self.data,
            "outputs": self.outputs,
        }


AgentFn = Callable[[Context, dict[str, Any] | None], AgentResult]
registry: dict[str, dict[str, Any]] = {}


def agent(key: str, label: str, order: int) -> Callable[[AgentFn], AgentFn]:
    """Décorateur d'enregistrement d'un agent."""

    def decorator(fn: AgentFn) -> AgentFn:
        registry[key] = {"key": key, "label": label, "order": order, "fn": fn}
        return fn

    return decorator


# --------------------------------------------------------------------------- #
# Helpers texte partagés
# --------------------------------------------------------------------------- #
STOPWORDS = {
    "le", "la", "les", "un", "une", "des", "de", "du", "et", "ou", "à", "au", "aux",
    "en", "dans", "sur", "pour", "par", "avec", "sans", "que", "qui", "est", "sont",
    "ce", "cette", "ces", "il", "elle", "on", "nous", "vous", "ils", "pas", "plus",
    "the", "and", "for", "with", "from", "this", "that",
}


def words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Zà-ÿ0-9']+", text.lower())


def keywords(text: str, top: int = 8) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for word in words(text):
        if len(word) < 4 or word in STOPWORDS:
            continue
        counts[word] = counts.get(word, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def readability(text: str) -> dict[str, float]:
    """Indicateurs simples : longueur moyenne de phrase et de mot, lisibilité."""
    sents = sentences(text) or [""]
    wds = words(text)
    avg_sentence = len(wds) / max(len(sents), 1)
    avg_word = (sum(len(w) for w in wds) / len(wds)) if wds else 0.0
    # score 0-100 : plus c'est haut, plus c'est lisible
    score = 100.0
    score -= max(0.0, avg_sentence - 15) * 2.5
    score -= max(0.0, avg_word - 5) * 8
    return {
        "sentences": len(sents),
        "words": len(wds),
        "avg_sentence_words": round(avg_sentence, 1),
        "avg_word_length": round(avg_word, 2),
        "readability": round(max(0.0, min(100.0, score)), 1),
    }


def hashtags_in(text: str) -> list[str]:
    return re.findall(r"#\w+", text)


def body_without_frontmatter(text: str) -> str:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            return parts[2].strip()
    return text.strip()


def frontmatter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) == 3:
            for line in parts[1].splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
    return meta
