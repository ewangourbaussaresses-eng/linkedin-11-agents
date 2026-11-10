.PHONY: help init test demo serve live clean

help:
	@echo "make init   — créer workspace/ (profil de marque par défaut)"
	@echo "make test   — lancer les 26 tests"
	@echo "make demo   — pipeline complet en simulation"
	@echo "make serve  — interface web locale (http://localhost:8765)"
	@echo "make live   — pipeline avec publication réelle (secrets requis)"

init:
	python -m linkedin_agents init

test:
	python -m pytest -q

demo:
	python -m linkedin_agents pipeline

serve:
	python -m linkedin_agents serve

live:
	python -m linkedin_agents pipeline --live

clean:
	rm -rf workspace/reports workspace/drafts workspace/queue.json
