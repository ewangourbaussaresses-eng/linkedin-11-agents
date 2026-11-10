"""Les 11 agents. Chacun expose `run(ctx, payload=None) -> dict`.

Contrat commun :
- l'agent lit ses entrées dans `payload` ou dans `workspace/` ;
- il écrit ses sorties dans `workspace/` (jamais ailleurs) ;
- il retourne un dict sérialisable en JSON, avec au moins `agent`, `ok`, `summary`.
"""
from __future__ import annotations

from .base import AgentResult, registry, agent

__all__ = ["AgentResult", "registry", "agent"]
