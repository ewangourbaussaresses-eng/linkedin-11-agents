"""Connecteur LLM : Claude (API Anthropic) en priorité, OpenAI en option.

Le reste du système ne dépend d'aucun fournisseur : les agents appellent
`llm.complete(...)` et retombent automatiquement sur leurs gabarits locaux
si aucune clé n'est configurée (mode hors ligne, CI, tests).

Configuration (variables d'environnement) :
    ANTHROPIC_API_KEY   clé API Claude — active le connecteur Claude
    ANTHROPIC_MODEL     optionnel, défaut claude-sonnet-4-5
    OPENAI_API_KEY      optionnel, utilisé si aucune clé Claude n'est présente
    OPENAI_MODEL        optionnel, défaut gpt-4o-mini
    LLM_PROVIDER        "claude" | "openai" | "auto" (défaut) | "off"

Aucune clé n'est jamais écrite dans le dépôt : elle ne vit que dans
l'environnement (ou les secrets GitHub Actions).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
OPENAI_URL = "https://api.openai.com/v1/chat/completions"
ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-5"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class LLMError(RuntimeError):
    """Erreur d'appel au fournisseur (réseau, quota, clé invalide…)."""


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


# --------------------------------------------------------------------------- #
# Détection du fournisseur
# --------------------------------------------------------------------------- #
def anthropic_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def openai_key() -> str | None:
    return os.environ.get("OPENAI_API_KEY") or None


def active_provider() -> str:
    """Retourne 'claude', 'openai' ou 'off' selon l'environnement."""
    forced = (os.environ.get("LLM_PROVIDER") or "auto").strip().lower()
    if forced in ("off", "none", "aucun", "false", "0"):
        return "off"
    if forced == "claude":
        return "claude" if anthropic_key() else "off"
    if forced == "openai":
        return "openai" if openai_key() else "off"
    if anthropic_key():
        return "claude"
    if openai_key():
        return "openai"
    return "off"


def is_available() -> bool:
    return active_provider() != "off"


def status() -> dict[str, Any]:
    provider = active_provider()
    return {
        "provider": provider,
        "available": provider != "off",
        "anthropic_key": bool(anthropic_key()),
        "openai_key": bool(openai_key()),
        "model": (os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL)
        if provider == "claude"
        else (os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL)
        if provider == "openai" else None,
    }


# --------------------------------------------------------------------------- #
# Appels HTTP
# --------------------------------------------------------------------------- #
def _post(url: str, payload: dict, headers: dict[str, str], timeout: int) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", **headers},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise LLMError(f"HTTP {exc.code} ({url}) : {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"réseau indisponible : {exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise LLMError("réponse du fournisseur illisible") from exc


def call_claude(prompt: str, system: str = "", max_tokens: int = 1200,
                temperature: float = 0.7, timeout: int = 60) -> LLMResponse:
    key = anthropic_key()
    if not key:
        raise LLMError("ANTHROPIC_API_KEY absente")
    model = os.environ.get("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
    payload: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system

    data = _post(ANTHROPIC_URL, payload, {
        "x-api-key": key,
        "anthropic-version": ANTHROPIC_VERSION,
    }, timeout)

    blocks = data.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
    if not text:
        raise LLMError("réponse vide de Claude")
    usage = data.get("usage") or {}
    return LLMResponse(text=text, provider="claude", model=model,
                       input_tokens=int(usage.get("input_tokens", 0)),
                       output_tokens=int(usage.get("output_tokens", 0)))


def call_openai(prompt: str, system: str = "", max_tokens: int = 1200,
                temperature: float = 0.7, timeout: int = 60) -> LLMResponse:
    key = openai_key()
    if not key:
        raise LLMError("OPENAI_API_KEY absente")
    model = os.environ.get("OPENAI_MODEL") or DEFAULT_OPENAI_MODEL
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    data = _post(OPENAI_URL, {
        "model": model, "messages": messages,
        "max_tokens": max_tokens, "temperature": temperature,
    }, {"Authorization": f"Bearer {key}"}, timeout)

    try:
        text = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError) as exc:
        raise LLMError("réponse inattendue d'OpenAI") from exc
    usage = data.get("usage") or {}
    return LLMResponse(text=text, provider="openai", model=model,
                       input_tokens=int(usage.get("prompt_tokens", 0)),
                       output_tokens=int(usage.get("completion_tokens", 0)))


def complete(prompt: str, system: str = "", max_tokens: int = 1200,
             temperature: float = 0.7, timeout: int = 60) -> LLMResponse:
    """Appelle le fournisseur actif. Lève LLMError en cas d'échec."""
    provider = active_provider()
    if provider == "claude":
        return call_claude(prompt, system, max_tokens, temperature, timeout)
    if provider == "openai":
        return call_openai(prompt, system, max_tokens, temperature, timeout)
    raise LLMError("aucun fournisseur configuré (ANTHROPIC_API_KEY ou OPENAI_API_KEY)")


def complete_or_none(prompt: str, system: str = "", **kwargs: Any) -> LLMResponse | None:
    """Comme `complete`, mais retourne None au lieu de lever (repli sur gabarits)."""
    try:
        return complete(prompt, system=system, **kwargs)
    except LLMError:
        return None


def extract_json(text: str) -> Any:
    """Extrait le premier objet/tableau JSON d'une réponse LLM (tolère le markdown)."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text
        text = text.lstrip("json").strip()
    candidates = [(text.find("["), text.rfind("]"), "[", "]"),
                  (text.find("{"), text.rfind("}"), "{", "}")]
    # on essaie d'abord le délimiteur qui apparaît en premier dans la réponse
    candidates.sort(key=lambda c: c[0] if c[0] != -1 else 10**9)
    for start, end, _opener, _closer in candidates:
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("aucun JSON exploitable dans la réponse")
