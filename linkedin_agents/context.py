"""Contexte partagé : chemins de l'espace de travail, profil de marque, état.

Tous les agents reçoivent un `Context` et n'écrivent que dans `workspace/`.
"""
from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BRAND: dict[str, Any] = {
    "name": "Mon entreprise",
    "voice": "direct, concret, sans jargon",
    "audience": "dirigeants de PME francophones",
    "pillars": ["Expertise métier", "Coulisses", "Conseils actionnables", "Actualité du secteur"],
    "forbidden": ["garantie de résultat", "révolutionnaire", "incroyable opportunité"],
    "hashtags": ["#PME", "#Entrepreneuriat", "#Conseil"],
    "language": "fr",
    "limits": {"max_posts_per_day": 1, "max_chars": 1300, "min_score_supervisor": 70},
}

DEFAULT_STRATEGY: dict[str, Any] = {
    "weeks": 4,
    "per_week": 3,
    "formats": ["text", "carrousel", "image"],
    "slots": ["mardi 08:30", "mercredi 12:15", "jeudi 18:00"],
}


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("[%(levelname)-7s] %(name)s: %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def slugify(text: str, limit: int = 48) -> str:
    keep = []
    for char in text.lower():
        if char.isalnum():
            keep.append(char)
        elif char in " -_'":
            keep.append("-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return (slug or "post")[:limit].strip("-")


@dataclass
class Context:
    """Chemins + configuration + état partagés par les 11 agents."""

    root: Path = field(default_factory=lambda: Path.cwd())
    dry_run: bool = True
    verbose: bool = False
    _brand: dict[str, Any] | None = None

    # ------------------------------------------------------------------ #
    # Chemins
    # ------------------------------------------------------------------ #
    @property
    def workspace(self) -> Path:
        return self.root / "workspace"

    @property
    def drafts_dir(self) -> Path:
        return self.workspace / "drafts"

    @property
    def reports_dir(self) -> Path:
        return self.workspace / "reports"

    @property
    def published_dir(self) -> Path:
        return self.workspace / "published"

    @property
    def state_path(self) -> Path:
        return self.workspace / "state.json"

    @property
    def brand_path(self) -> Path:
        return self.workspace / "brand.json"

    @property
    def plan_path(self) -> Path:
        return self.workspace / "plan.json"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    def ensure_dirs(self) -> None:
        for path in (self.workspace, self.drafts_dir, self.reports_dir, self.published_dir):
            path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Profil de marque
    # ------------------------------------------------------------------ #
    @property
    def brand(self) -> dict[str, Any]:
        if self._brand is None:
            data = read_json(self.brand_path, default=None)
            self._brand = {**DEFAULT_BRAND, **(data or {})}
            if data:
                # fusion profonde des sous-dicts connus
                self._brand["limits"] = {**DEFAULT_BRAND["limits"], **data.get("limits", {})}
        return self._brand

    def limits(self, key: str, default: Any = None) -> Any:
        return self.brand.get("limits", {}).get(key, default)

    # ------------------------------------------------------------------ #
    # État (historique, compteurs, apprentissages)
    # ------------------------------------------------------------------ #
    def load_state(self) -> dict[str, Any]:
        return read_json(self.state_path, default=None) or {
            "created": now_utc().isoformat(timespec="seconds"),
            "published": [],
            "published_today": {},
            "history": [],
            "learnings": [],
        }

    def save_state(self, state: dict[str, Any]) -> None:
        write_json(self.state_path, state)

    def log(self, agent: str, action: str, detail: Any = None) -> None:
        state = self.load_state()
        state["history"].append({
            "at": now_utc().isoformat(timespec="seconds"),
            "agent": agent,
            "action": action,
            "detail": detail,
        })
        state["history"] = state["history"][-500:]
        self.save_state(state)


# --------------------------------------------------------------------------- #
# I/O utilitaires
# --------------------------------------------------------------------------- #
def read_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def read_text(path: Path, default: str = "") -> str:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return default
