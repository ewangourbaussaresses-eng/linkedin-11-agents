"""Tests du connecteur LLM (aucun appel réseau : tout est simulé)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from linkedin_agents import llm  # noqa: E402
from linkedin_agents.agents import engagement, writer  # noqa: E402
from linkedin_agents.context import Context  # noqa: E402


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER",
                "ANTHROPIC_MODEL", "OPENAI_MODEL"):
        monkeypatch.delenv(var, raising=False)
    yield


# --------------------------------------------------------------------------- #
# Détection du fournisseur
# --------------------------------------------------------------------------- #
def test_sans_cle_provider_off():
    assert llm.active_provider() == "off"
    assert llm.is_available() is False
    assert llm.status()["available"] is False


def test_cle_claude_detectee(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert llm.active_provider() == "claude"
    assert llm.status()["model"] == llm.DEFAULT_ANTHROPIC_MODEL


def test_openai_en_repli(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    assert llm.active_provider() == "openai"


def test_provider_force(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-a")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-o")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    assert llm.active_provider() == "openai"
    monkeypatch.setenv("LLM_PROVIDER", "off")
    assert llm.active_provider() == "off"


def test_modele_personnalise(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-a")
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
    assert llm.status()["model"] == "claude-haiku-4-5"


# --------------------------------------------------------------------------- #
# Appels (réseau simulé)
# --------------------------------------------------------------------------- #
def test_call_claude_parse_la_reponse(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def fake_post(url, payload, headers, timeout):
        assert url == llm.ANTHROPIC_URL
        assert headers["x-api-key"] == "sk-test"
        assert headers["anthropic-version"] == llm.ANTHROPIC_VERSION
        assert payload["model"] == llm.DEFAULT_ANTHROPIC_MODEL
        return {"content": [{"type": "text", "text": "Bonjour LinkedIn"}],
                "usage": {"input_tokens": 12, "output_tokens": 7}}

    monkeypatch.setattr(llm, "_post", fake_post)
    response = llm.complete("Salut", system="Tu es rédacteur")
    assert response.text == "Bonjour LinkedIn"
    assert response.provider == "claude"
    assert (response.input_tokens, response.output_tokens) == (12, 7)


def test_call_claude_erreur_http(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def boom(*args, **kwargs):
        raise llm.LLMError("HTTP 401 : clé invalide")

    monkeypatch.setattr(llm, "_post", boom)
    with pytest.raises(llm.LLMError):
        llm.complete("Salut")
    assert llm.complete_or_none("Salut") is None


def test_reponse_vide_leve(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "_post", lambda *a, **k: {"content": []})
    with pytest.raises(llm.LLMError):
        llm.complete("Salut")


def test_complete_sans_provider_leve():
    with pytest.raises(llm.LLMError):
        llm.complete("Salut")


# --------------------------------------------------------------------------- #
# Extraction JSON
# --------------------------------------------------------------------------- #
def test_extract_json_simple():
    assert llm.extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_dans_markdown():
    text = 'Voici le résultat :\n```json\n{"body": "post", "hashtags": ["#PME"]}\n```'
    assert llm.extract_json(text)["body"] == "post"


def test_extract_json_liste():
    assert llm.extract_json('blabla [{"reply": "ok"}] fin') == [{"reply": "ok"}]


def test_extract_json_impossible():
    with pytest.raises(llm.LLMError):
        llm.extract_json("pas de json ici")


# --------------------------------------------------------------------------- #
# Agent 4 — Rédacteur avec Claude
# --------------------------------------------------------------------------- #
@pytest.fixture()
def ctx(tmp_path: Path) -> Context:
    (tmp_path / "data").mkdir()
    for name in ("sources.json", "comments.json"):
        (tmp_path / "data" / name).write_text(
            (ROOT / "data" / name).read_text(encoding="utf-8"), encoding="utf-8")
    context = Context(root=tmp_path, dry_run=True)
    context.ensure_dirs()
    return context


def test_writer_utilise_claude(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def fake_complete(prompt, system="", **kwargs):
        assert "Cybersécurité" in prompt or "cybersécurité" in prompt
        return llm.LLMResponse(
            text=json.dumps({
                "title": "La cybersécurité en PME",
                "hook": "Votre PME est une cible. Voilà pourquoi.",
                "body": "Votre PME est une cible. Voilà pourquoi.\n\n"
                        "Trois gestes suffisent : MFA, sauvegardes, sensibilisation.\n\n"
                        "#Cybersécurité #PME",
                "cta": "Et chez vous, par où commencez-vous ?",
                "hashtags": ["#Cybersécurité", "#PME"],
            }),
            provider="claude", model="claude-sonnet-4-5")

    monkeypatch.setattr(llm, "complete", fake_complete)
    result = writer.run(ctx, {"topic": "Cybersécurité : les PME sont la cible"})
    draft = result.data["drafts"][0]
    assert draft["generated_by"].startswith("llm:claude")
    assert "MFA" in draft["body"]
    assert "Claude" in result.summary


def test_writer_repli_si_llm_echoue(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: (_ for _ in ()).throw(
        llm.LLMError("quota dépassé")))
    result = writer.run(ctx, {"topic": "l'automatisation"})
    assert result.data["drafts"][0]["generated_by"] == "template"
    assert "gabarits" in result.summary


def test_writer_sans_cle_reste_hors_ligne(ctx):
    result = writer.run(ctx, {"topic": "l'automatisation"})
    assert result.data["drafts"][0]["generated_by"] == "template"


def test_writer_force_gabarits(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: pytest.fail("ne doit pas être appelé"))
    result = writer.run(ctx, {"topic": "l'automatisation", "use_llm": False})
    assert result.data["drafts"][0]["generated_by"] == "template"


def test_writer_tronque_au_max_chars(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "complete", lambda *a, **k: llm.LLMResponse(
        text=json.dumps({"title": "T", "body": "x" * 5000, "hashtags": ["#A"]}),
        provider="claude", model="m"))
    result = writer.run(ctx, {"topic": "sujet"})
    assert len(result.data["drafts"][0]["body"]) <= ctx.limits("max_chars", 1300)


# --------------------------------------------------------------------------- #
# Agent 9 — Engagement avec Claude
# --------------------------------------------------------------------------- #
def test_engagement_utilise_claude(ctx, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    def fake_complete(prompt, system="", **kwargs):
        return llm.LLMResponse(text=json.dumps([
            {"author": "Sophie", "type": "question", "reply": "On mesure sur deux semaines."},
            {"author": "Marc", "type": "objection", "reply": "Qu'est-ce qui a coincé chez vous ?"},
        ]), provider="claude", model="m")

    monkeypatch.setattr(llm, "complete", fake_complete)
    result = engagement.run(ctx, {})
    replies = result.data["replies"]
    assert len(replies) == 2
    assert replies[0]["priority"] >= replies[1]["priority"]
    assert replies[0]["generated_by"].startswith("llm:")


def test_engagement_repli_gabarits(ctx):
    result = engagement.run(ctx, {})
    assert all("generated_by" not in r for r in result.data["replies"])
    assert len(result.data["replies"]) == 4
