"""Survival Goals & Community Settlement Projects Engine (docs/SPEC.md, docs/LIVING_WORLD.md).

Manages community survival projects for the Frontier Settlers at Qalat-e Lut:
  - Aquifer & Community Water Reserves
  - Field Hospital & Trauma Supplies
  - Perimeter Fortifications & Barricades
  - Settlement Fuel Depot & Generator
  - Emergency Broadcast Comms Grid

Tracks live progress, unlocked tiers, personal survival milestones, and contributions.
Persists state in gm_state/survival_goals.json.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE_FILE = ROOT / "gm_state" / "survival_goals.json"
CONFIG_FILE = ROOT / "presets" / "survival_goals.yaml"


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {"settlement_projects": {}, "personal_milestones": []}
    return yaml.safe_load(CONFIG_FILE.read_text()) or {}


class SurvivalGoalsManager:
    def __init__(self, state_path: Path = STATE_FILE, config: dict | None = None) -> None:
        self.state_path = state_path
        self.cfg = config or load_config()
        self.state = self._load_or_init()

    def _load_or_init(self) -> dict[str, Any]:
        if self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text())
                # Ensure all configured projects exist in state
                projects = data.get("projects", {})
                for pid, pcfg in self.cfg.get("settlement_projects", {}).items():
                    if pid not in projects:
                        projects[pid] = {
                            "current": pcfg.get("initial", 0),
                            "target": pcfg.get("target", 100),
                            "contributions": 0,
                            "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(),
                        }
                data["projects"] = projects
                return data
            except Exception:
                pass

        # Fresh state
        projects = {}
        for pid, pcfg in self.cfg.get("settlement_projects", {}).items():
            projects[pid] = {
                "current": pcfg.get("initial", 0),
                "target": pcfg.get("target", 100),
                "contributions": 0,
                "last_updated": dt.datetime.now(dt.timezone.utc).isoformat(),
            }
        fresh = {
            "version": 1,
            "turn": 0,
            "last_turn_advancement": dt.datetime.now(dt.timezone.utc).isoformat(),
            "projects": projects,
            "activity_log": [
                {
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                    "text": "Frontier Settlers HQ established at Qalat-e Lut fortress.",
                    "kind": "settlement",
                }
            ],
        }
        self.save(fresh)
        return fresh

    def save(self, data: dict | None = None) -> None:
        payload = data or self.state
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2) + "\n")

    def record_contribution(self, project_id: str, amount: float, contributor: str = "Survivor") -> dict[str, Any]:
        projects = self.state.get("projects", {})
        if project_id not in projects:
            pcfg = self.cfg.get("settlement_projects", {}).get(project_id, {})
            projects[project_id] = {
                "current": pcfg.get("initial", 0),
                "target": pcfg.get("target", 100),
                "contributions": 0,
            }
        p = projects[project_id]
        p["current"] = min(p["target"], round(p["current"] + amount, 1))
        p["contributions"] = p.get("contributions", 0) + 1
        p["last_updated"] = dt.datetime.now(dt.timezone.utc).isoformat()

        pname = self.cfg.get("settlement_projects", {}).get(project_id, {}).get("name", project_id)
        unit = self.cfg.get("settlement_projects", {}).get(project_id, {}).get("unit", "")
        log_entry = {
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "text": f"{contributor} contributed {amount} {unit} to {pname}.",
            "kind": "contribution",
            "project": project_id,
        }
        self.state.setdefault("activity_log", []).insert(0, log_entry)
        self.state["activity_log"] = self.state["activity_log"][:50]
        self.save()
        return p

    def advance_turn(self, turn: int, water_held: bool = False, fuel_held: bool = False) -> None:
        self.state["turn"] = turn
        self.state["last_turn_advancement"] = dt.datetime.now(dt.timezone.utc).isoformat()
        projects = self.state.get("projects", {})

        # Turn simulation effects
        # 1. Water: consumption -10 L per turn, replenishment +25 L if Settlers hold a water site
        if "water_reserves" in projects:
            delta = 15 if water_held else -8
            w = projects["water_reserves"]
            w["current"] = max(10, min(w["target"], w["current"] + delta))

        # 2. Fuel: consumption -5 L per turn, replenishment +15 if fuel/industrial held
        if "fuel_depot" in projects:
            delta = 10 if fuel_held else -4
            f = projects["fuel_depot"]
            f["current"] = max(10, min(f["target"], f["current"] + delta))

        self.save()

    def get_summary(self) -> dict[str, Any]:
        projects_cfg = self.cfg.get("settlement_projects", {})
        projects_out = []
        for pid, pcfg in projects_cfg.items():
            st = self.state.get("projects", {}).get(pid, {})
            curr = st.get("current", pcfg.get("initial", 0))
            tgt = pcfg.get("target", 100)
            pct = round(min(100.0, (curr / tgt) * 100.0), 1) if tgt > 0 else 0.0

            # Determine unlocked perks
            perks_cfg = pcfg.get("perks", {})
            unlocked_perks = []
            next_perk = None
            for tk, tdata in sorted(perks_cfg.items(), key=lambda x: x[1].get("threshold", 0)):
                thresh = tdata.get("threshold", 0)
                entry = {
                    "tier": tk,
                    "threshold": thresh,
                    "name": tdata.get("name", ""),
                    "effect": tdata.get("effect", ""),
                    "unlocked": curr >= thresh,
                }
                if curr >= thresh:
                    unlocked_perks.append(entry)
                elif next_perk is None:
                    next_perk = entry

            projects_out.append({
                "id": pid,
                "name": pcfg.get("name", pid),
                "category": pcfg.get("category", "General"),
                "current": curr,
                "target": tgt,
                "unit": pcfg.get("unit", ""),
                "percent": pct,
                "icon": pcfg.get("icon", "box"),
                "color": pcfg.get("color", "#d8bd79"),
                "description": pcfg.get("description", ""),
                "unlocked_perks": unlocked_perks,
                "next_perk": next_perk,
                "active_perk_text": unlocked_perks[-1]["effect"] if unlocked_perks else "No perks active yet.",
            })

        return {
            "turn": self.state.get("turn", 0),
            "projects": projects_out,
            "personal_milestones": self.cfg.get("personal_milestones", []),
            "recent_activity": self.state.get("activity_log", [])[:10],
        }


_GLOBAL_MANAGER: SurvivalGoalsManager | None = None


def get_manager() -> SurvivalGoalsManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = SurvivalGoalsManager()
    return _GLOBAL_MANAGER
