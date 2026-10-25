"""Unit tests for the Settlement Survival Goals and Milestones system."""
import json
import tempfile
from pathlib import Path

import pytest
import yaml

from gamemaster.survival_goals import SurvivalGoalsManager, load_config


@pytest.fixture
def temp_manager(tmp_path):
    state_file = tmp_path / "survival_goals.json"
    cfg = {
        "settlement_projects": {
            "water_reserves": {
                "id": "water_reserves",
                "name": "Aquifer & Community Water Reserves",
                "category": "Sustenance",
                "target": 500,
                "unit": "Liters",
                "initial": 150,
                "icon": "water",
                "color": "#68b5e8",
                "description": "Purified water stored in cisterns.",
                "perks": {
                    "tier1": {"threshold": 100, "name": "Basic Allotment", "effect": "Daily ration active"},
                    "tier2": {"threshold": 300, "name": "Clean Cistern", "effect": "Zero cholera risk"},
                },
            },
            "fortification": {
                "id": "fortification",
                "name": "Perimeter Fortifications",
                "category": "Defense",
                "target": 200,
                "unit": "Materials",
                "initial": 50,
                "icon": "shield",
                "color": "#d8bd79",
                "description": "Gate timber and sandbags.",
                "perks": {
                    "tier1": {"threshold": 60, "name": "Gate Bastion", "effect": "Outer gate held"},
                },
            },
        },
        "personal_milestones": [
            {
                "id": "desert_nomad",
                "title": "Desert Nomad",
                "category": "Survival",
                "criterion": "Survive 24 real-time hours without dying",
                "reward": "+10% stamina regen",
            }
        ],
    }
    return SurvivalGoalsManager(state_path=state_file, config=cfg)


def test_initial_state_and_summary(temp_manager):
    summary = temp_manager.get_summary()
    assert summary["turn"] == 0
    assert len(summary["projects"]) == 2
    assert len(summary["personal_milestones"]) == 1

    water = next(p for p in summary["projects"] if p["id"] == "water_reserves")
    assert water["current"] == 150
    assert water["target"] == 500
    assert water["percent"] == 30.0
    assert len(water["unlocked_perks"]) == 1
    assert water["unlocked_perks"][0]["tier"] == "tier1"
    assert water["active_perk_text"] == "Daily ration active"
    assert water["next_perk"]["tier"] == "tier2"


def test_record_contribution(temp_manager):
    res = temp_manager.record_contribution("water_reserves", 50.0, contributor="TestSurvivor")
    assert res["current"] == 200.0
    assert res["contributions"] == 1

    summary = temp_manager.get_summary()
    water = next(p for p in summary["projects"] if p["id"] == "water_reserves")
    assert water["current"] == 200.0
    assert water["percent"] == 40.0

    # Test activity log entry
    assert len(summary["recent_activity"]) >= 1
    recent = summary["recent_activity"][0]
    assert "TestSurvivor" in recent["text"]
    assert "50.0" in recent["text"]


def test_perk_unlock_on_reaching_threshold(temp_manager):
    # Currently 150, tier2 threshold is 300
    temp_manager.record_contribution("water_reserves", 160.0)
    summary = temp_manager.get_summary()
    water = next(p for p in summary["projects"] if p["id"] == "water_reserves")
    assert water["current"] == 310.0
    assert len(water["unlocked_perks"]) == 2
    assert water["active_perk_text"] == "Zero cholera risk"
    assert water["next_perk"] is None


def test_advance_turn_consumption_and_replenishment(temp_manager):
    # Without water holding, water decreases slightly
    temp_manager.advance_turn(1, water_held=False)
    summary = temp_manager.get_summary()
    water = next(p for p in summary["projects"] if p["id"] == "water_reserves")
    assert water["current"] == 142.0

    # With water holding, water replenishes
    temp_manager.advance_turn(2, water_held=True)
    summary2 = temp_manager.get_summary()
    water2 = next(p for p in summary2["projects"] if p["id"] == "water_reserves")
    assert water2["current"] == 157.0


def test_presets_survival_goals_yaml_validity():
    cfg = load_config()
    assert "settlement_projects" in cfg
    assert "personal_milestones" in cfg
    projects = cfg["settlement_projects"]
    assert "water_reserves" in projects
    assert "medical_stockpile" in projects
    assert "fortification" in projects
    assert "fuel_depot" in projects
    assert "comms_grid" in projects

    for pid, p in projects.items():
        assert p["target"] > 0
        assert p["initial"] >= 0
        assert len(p.get("perks", {})) >= 1
