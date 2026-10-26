"""Hirable NPC Companions Manager for Qalat-e Lut Fortress.

Tracks companion roster, recruitment status, station assignments,
and hiring transactions for the Frontier Settlers.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger("gamemaster.companions")
ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = ROOT / "presets" / "companions.yaml"
STATE_DIR = ROOT / "gm_state"
STATE_FILE = STATE_DIR / "companions.json"


def load_config() -> dict[str, Any]:
    """Loads companion presets config."""
    if not CONFIG_PATH.exists():
        LOGGER.warning(f"Companion preset not found: {CONFIG_PATH}")
        return {}
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}


class CompanionsManager:
    """Manages the Qalat-e Lut companion roster and player squad hiring."""

    def __init__(self, state_path: Path | None = None, config: dict[str, Any] | None = None):
        self.state_path = state_path or STATE_FILE
        self.config = config if config is not None else load_config()
        self.state = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        comps = self.config.get("companions", {})
        roster = {}
        for cid, spec in comps.items():
            roster[cid] = {
                "id": cid,
                "name": spec.get("name", cid),
                "title": spec.get("title", ""),
                "status": "Available",  # "Available" (garrison at HQ), "Hired" (with player), "Down" (recovering)
                "hired_by": None,
                "hired_at": None,
                "station": spec.get("station", "Qalat-e Lut"),
                "position": spec.get("position", [14837.0, 0.0, 7855.0]),
                "health": 100.0,
                "deployments": 0,
            }
        return {
            "version": 1,
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "roster": roster,
            "hire_log": [
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "text": "Frontier Settlers garrison stationed at Qalat-e Lut fortress.",
                }
            ],
        }

    def _load_state(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text(encoding="utf-8"))
                # Merge with config in case new companions were added
                defaults = self._default_state()
                for cid, cdef in defaults["roster"].items():
                    if cid not in data.get("roster", {}):
                        data.setdefault("roster", {})[cid] = cdef
                return data
            except Exception as e:
                LOGGER.error(f"Failed to read companion state: {e}; resetting")
        state = self._default_state()
        self._save_state(state)
        return state

    def _save_state(self, state: dict[str, Any] | None = None) -> None:
        if state is None:
            state = self.state
        state["last_updated"] = datetime.now(timezone.utc).isoformat()
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def get_summary(self) -> dict[str, Any]:
        """Returns structured summary for API, web UI, and Player Portal."""
        cfg_comps = self.config.get("companions", {})
        settlement = self.config.get("settlement", {})
        command_guide = self.config.get("command_guide", {})

        roster_list = []
        for cid, spec in cfg_comps.items():
            st = self.state.get("roster", {}).get(cid, {})
            roster_list.append({
                "id": cid,
                "name": spec.get("name", cid),
                "title": spec.get("title", ""),
                "gender": spec.get("gender", "unknown"),
                "entity_class": spec.get("entity_class", "SurvivorM_Mirek"),
                "loadout": spec.get("loadout", "DZDS_Settlers"),
                "position": spec.get("position", [14837.0, 0.0, 7855.0]),
                "station": spec.get("station", "Qalat-e Lut"),
                "specialization": spec.get("specialization", ""),
                "description": spec.get("description", ""),
                "bark": spec.get("bark", ""),
                "primary_weapon": spec.get("primary_weapon", ""),
                "secondary_weapon": spec.get("secondary_weapon", ""),
                "role_perks": spec.get("role_perks", []),
                "retainer_cost": spec.get("retainer_cost", []),
                # Live dynamic state
                "status": st.get("status", "Available"),
                "hired_by": st.get("hired_by"),
                "hired_at": st.get("hired_at"),
                "health": st.get("health", 100.0),
                "deployments": st.get("deployments", 0),
            })

        return {
            "settlement": settlement,
            "max_squad_size": settlement.get("max_squad_size", 4),
            "command_guide": command_guide,
            "roster": roster_list,
            "available_count": sum(1 for c in roster_list if c["status"] == "Available"),
            "hired_count": sum(1 for c in roster_list if c["status"] == "Hired"),
            "hire_log": self.state.get("hire_log", [])[-10:],
            "last_updated": self.state.get("last_updated"),
        }

    def hire_companion(self, cid: str, player_name: str, notes: str = "") -> dict[str, Any]:
        """Hires a companion for a player."""
        if cid not in self.config.get("companions", {}):
            raise ValueError(f"Unknown companion ID: {cid}")

        roster = self.state.setdefault("roster", {})
        comp = roster.setdefault(cid, {
            "id": cid,
            "name": self.config["companions"][cid].get("name", cid),
            "status": "Available",
            "deployments": 0,
        })

        comp["status"] = "Hired"
        comp["hired_by"] = player_name
        comp["hired_at"] = datetime.now(timezone.utc).isoformat()
        comp["deployments"] = comp.get("deployments", 0) + 1

        log_entry = {
            "timestamp": comp["hired_at"],
            "text": f"{comp.get('name', cid)} enlisted with survivor {player_name}. {notes}".strip(),
            "companion_id": cid,
            "player": player_name,
        }
        self.state.setdefault("hire_log", []).insert(0, log_entry)
        self._save_state()
        return comp

    def dismiss_companion(self, cid: str, reason: str = "") -> dict[str, Any]:
        """Dismisses a companion back to Qalat-e Lut garrison."""
        if cid not in self.config.get("companions", {}):
            raise ValueError(f"Unknown companion ID: {cid}")

        roster = self.state.setdefault("roster", {})
        comp = roster.setdefault(cid, {"id": cid, "status": "Available"})
        prev_owner = comp.get("hired_by", "Expedition Leader")

        comp["status"] = "Available"
        comp["hired_by"] = None
        comp["hired_at"] = None

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": f"{comp.get('name', cid)} returned to Qalat-e Lut garrison from {prev_owner}. {reason}".strip(),
            "companion_id": cid,
        }
        self.state.setdefault("hire_log", []).insert(0, log_entry)
        self._save_state()
        return comp


_GLOBAL_MGR: CompanionsManager | None = None


def get_manager() -> CompanionsManager:
    global _GLOBAL_MGR
    if _GLOBAL_MGR is None:
        _GLOBAL_MGR = CompanionsManager()
    return _GLOBAL_MGR
