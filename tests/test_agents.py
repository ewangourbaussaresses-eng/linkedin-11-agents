"""Tests des 11 agents et de l'orchestrateur (hors réseau)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from linkedin_agents.agents import (  # noqa: E402
    analyst, audience, editor, engagement, publisher, scheduler, strategist,
    supervisor, visual, watch, writer,
)
from linkedin_agents.agents.base import readability  # noqa: E402
from linkedin_agents.context import Context  # noqa: E402
from linkedin_agents.orchestrator import PIPELINE, agents_list, run_agent, run_pipeline  # noqa: E402


@pytest.fixture()
def ctx(tmp_path: Path) -> Context:
    """Contexte isolé : copie des données d'exemple dans un dossier temporaire."""
    (tmp_path / "data").mkdir()
    for name in ("sources.json", "audience.example.csv", "comments.json", "metrics.csv"):
        (tmp_path / "data" / name).write_text(
            (ROOT / "data" / name).read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "data" / "audience.csv").write_text(
        (ROOT / "data" / "audience.example.csv").read_text(encoding="utf-8"), encoding="utf-8")
    context = Context(root=tmp_path, dry_run=True)
    context.ensure_dirs()
    return context


# --------------------------------------------------------------------------- #
# Registre & structure
# --------------------------------------------------------------------------- #
def test_onze_agents_enregistres():
    rows = agents_list()
    assert len(rows) == 11
    assert [r["order"] for r in rows] == list(range(1, 12))
    assert set(PIPELINE) == {r["key"] for r in rows}


def test_agent_inconnu_leve():
    with pytest.raises(KeyError):
        run_agent(Context(root=Path(".")), "inexistant")


# --------------------------------------------------------------------------- #
# Agent 1 — Veille
# --------------------------------------------------------------------------- #
def test_veille_angles(ctx: Context):
    result = watch.run(ctx, {})
    assert result.ok
    titles = [a["theme"] for a in result.data["angles"]]
    assert any("IA" in t for t in titles)
    assert (ctx.reports_dir / "veille.json").exists()


def test_veille_parse_rss():
    xml = """<?xml version="1.0"?><rss><channel><item><title>Titre A</title>
             <link>https://a</link><description>Desc</description></item></channel></rss>"""
    items = watch._parse_feed(xml)
    assert items[0]["title"] == "Titre A"


def test_veille_normalize_title():
    assert watch.normalize_title("  — Le grand sujet ! ") == "Le grand sujet"
    assert watch.normalize_title("La méthode simple") == "méthode simple"


# --------------------------------------------------------------------------- #
# Agent 2 — Audience
# --------------------------------------------------------------------------- #
def test_audience_personas_et_creneaux(ctx: Context):
    result = audience.run(ctx, {})
    assert result.ok
    assert result.data["rows"] == 14
    assert result.data["personas"]
    assert result.data["best_hours"]


def test_audience_sans_donnees(ctx: Context):
    (ctx.data_dir / "audience.csv").unlink()
    (ctx.data_dir / "audience.example.csv").unlink()
    result = audience.run(ctx, {})
    assert result.ok is False
    assert result.data["rows"] == 0


# --------------------------------------------------------------------------- #
# Agent 3 — Stratège
# --------------------------------------------------------------------------- #
def test_strategie_calendrier(ctx: Context):
    angles = watch.run(ctx, {}).data["angles"]
    plan = strategist.run(ctx, {"angles": angles, "audience": {}})
    assert len(plan.data["topics"]) == 12
    assert (ctx.workspace / "calendar.md").exists()
    assert ctx.plan_path.exists()


def test_strategie_couvre_les_piliers(ctx: Context):
    plan = strategist.build_plan([], {}, ctx.brand)
    assert sum(plan["coverage"].values()) == 12
    assert plan["gaps"] == [] or len(plan["gaps"]) < len(plan["piliers"]) if "piliers" in plan else True


# --------------------------------------------------------------------------- #
# Agent 4 — Rédacteur
# --------------------------------------------------------------------------- #
def test_redacteur_sans_plan_echoue(ctx: Context):
    assert writer.run(ctx, {}).ok is False


def test_redacteur_produit_des_brouillons(ctx: Context):
    result = writer.run(ctx, {"topic": "Cybersécurité : les PME sont la cible"})
    assert result.ok
    text = Path(result.data["drafts"][0]["file"]).read_text(encoding="utf-8")
    assert text.startswith("---")
    assert "#Coulisses" in text or "#" in text


def test_theme_naturel():
    assert writer.natural_theme("Cybersécurité : les PME sont la cible") == "la cybersécurité"
    assert writer.natural_theme("L'IA générative entre dans les PME") == "l'IA générative"
    assert writer.natural_theme("Recrutement : les compétences") == "le recrutement"
    assert writer.natural_theme("") == "ce sujet"


# --------------------------------------------------------------------------- #
# Agent 5 — Éditeur
# --------------------------------------------------------------------------- #
def test_editeur_corrige_le_style(ctx: Context):
    path = ctx.drafts_dir / "t.md"
    path.write_text("---\ntitle: T\n---\n\nAfin de gagner du temps, il est possible de mesurer !! #PME\n",
                    encoding="utf-8")
    result = editor.run(ctx, {"file": str(path)})
    text = path.read_text(encoding="utf-8")
    assert "pour gagner du temps" in text
    assert "on peut" in text
    assert "!!" not in text
    assert result.ok


def test_readability_penalise_les_phrases_longues():
    short = readability("Une phrase courte. Une autre phrase courte.")
    long_text = readability(" ".join(["mot"] * 40) + ".")
    assert short["readability"] > long_text["readability"]


# --------------------------------------------------------------------------- #
# Agent 6 — Visuel
# --------------------------------------------------------------------------- #
def test_visuel_briefs(ctx: Context):
    writer.run(ctx, {"topic": "l'automatisation", "format": "carrousel"})
    result = visual.run(ctx, {})
    brief = result.data["briefs"][0]
    assert brief["alt_text"]
    assert brief["prompt"]
    assert "#" not in brief["subline"]


# --------------------------------------------------------------------------- #
# Agent 7 — Programmateur
# --------------------------------------------------------------------------- #
def test_programmateur_trie_la_file(ctx: Context):
    strategist.run(ctx, {"angles": [], "audience": {}})
    writer.run(ctx, {"limit": 3})
    result = scheduler.run(ctx, {})
    queue = result.data["queue"]
    assert len(queue) == 3
    assert [q["scheduled_at"] for q in queue] == sorted(q["scheduled_at"] for q in queue)
    # l'heure du créneau doit être respectée (« mardi 08:30 » -> T08:30)
    assert all(q["slot"].split()[-1] in q["scheduled_at"] for q in queue)


def test_parse_slot():
    assert scheduler.parse_slot("mardi 08:30") == (1, 8, 30)
    assert scheduler.parse_slot("18:00") == (None, 18, 0)


# --------------------------------------------------------------------------- #
# Agent 10 — Superviseur
# --------------------------------------------------------------------------- #
def test_superviseur_bloque_terme_interdit(ctx: Context):
    path = ctx.drafts_dir / "mauvais.md"
    path.write_text("---\ntitle: T\n---\n\nUne solution révolutionnaire avec garantie de résultat. #PME",
                    encoding="utf-8")
    result = supervisor.run(ctx, {"files": [str(path)]})
    verdict = result.data["verdicts"][0]
    assert verdict["verdict"] == "bloque"
    assert any("interdit" in i for i in verdict["issues"])


def test_superviseur_detecte_doublon(ctx: Context):
    body = ("Nous avons appris sur le terrain que mesurer avant de décider change tout "
            "pour les équipes marketing et commerciales. #PME #Conseil " * 2)
    a = ctx.drafts_dir / "a.md"
    b = ctx.drafts_dir / "b.md"
    a.write_text(f"---\ntitle: A\n---\n\n{body}", encoding="utf-8")
    b.write_text(f"---\ntitle: B\n---\n\n{body}", encoding="utf-8")
    result = supervisor.run(ctx, {"files": [str(a), str(b)]})
    assert any("doublon" in i for v in result.data["verdicts"] for i in v["issues"])


# --------------------------------------------------------------------------- #
# Agent 8 — Publisher
# --------------------------------------------------------------------------- #
def test_publisher_refuse_sans_approbation(ctx: Context):
    assert publisher.run(ctx, {"dry_run": True}).ok is False


def test_publisher_simule_apres_approbation(ctx: Context):
    writer.run(ctx, {"topic": "l'automatisation"})
    supervisor.run(ctx, {})
    result = publisher.run(ctx, {"dry_run": True})
    assert result.ok
    assert result.data["records"][0]["status"] == "simulé"
    assert (ctx.published_dir / "log.jsonl").exists()


def test_publisher_ne_republie_pas(ctx: Context):
    writer.run(ctx, {"topic": "l'automatisation"})
    supervisor.run(ctx, {})
    publisher.run(ctx, {"dry_run": True})
    second = publisher.run(ctx, {"dry_run": True})
    assert "déjà" in second.summary.lower()


# --------------------------------------------------------------------------- #
# Agent 9 — Engagement
# --------------------------------------------------------------------------- #
def test_engagement_classe_et_repond(ctx: Context):
    result = engagement.run(ctx, {})
    types = {r["type"] for r in result.data["replies"]}
    assert "question" in types
    assert "objection" in types
    assert len(result.data["outreach"]) == 3


# --------------------------------------------------------------------------- #
# Agent 11 — Analyste
# --------------------------------------------------------------------------- #
def test_analyste_classe_et_apprend(ctx: Context):
    result = analyst.run(ctx, {})
    assert result.ok
    ranking = result.data["ranking"]
    assert ranking[0]["rate"] >= ranking[-1]["rate"]
    assert result.data["learnings"]
    assert ctx.load_state()["learnings"]


# --------------------------------------------------------------------------- #
# Pipeline complet
# --------------------------------------------------------------------------- #
def test_pipeline_complet(ctx: Context):
    report = run_pipeline(ctx, dry_run=True)
    steps = {s["agent"]: s for s in report["steps"]}
    assert len(steps) == 11
    assert steps["writer"]["ok"] and steps["supervisor"]["ok"] and steps["publisher"]["ok"]
    assert (ctx.workspace / "calendar.md").exists()
    assert list(ctx.drafts_dir.glob("*.md"))


def test_pipeline_sans_publication(ctx: Context):
    report = run_pipeline(ctx, dry_run=True, publish=False)
    assert "publisher" not in [s["agent"] for s in report["steps"]]
