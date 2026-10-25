"""Tests for the Survival Quests and Campaign Generation system."""
import json
import re
from pathlib import Path

import pytest
import yaml

import active
import campaign_gen
import front_plan
from gamemaster.ledger import WarLedger
from gamemaster.survival_goals import get_manager

ROOT = Path(__file__).resolve().parent.parent
EXPANSION_QUESTS_DIR = ROOT / "server" / "profiles" / "ExpansionMod" / "Quests"
INIT_C = ROOT / "server" / "mpmissions" / "dayzOffline.nasdara" / "init.c"


@pytest.fixture
def compiled_campaign(tmp_path):
    led = WarLedger.load_or_new("nasdara", initial=True)
    quests_cfg = active.load_yaml("presets/quests.yaml")
    traders_cfg = active.load_yaml("presets/traders.yaml")
    plan = {
        "turn": led.s.turn,
        "traders": front_plan.plan_traders(led, traders_cfg),
        "quests": front_plan.plan_quests(led, quests_cfg),
    }
    stats = campaign_gen.compile_campaign("nasdara", led, plan, dry_run=False)
    return plan, stats


def test_survival_quests_are_compiled(compiled_campaign):
    plan, stats = compiled_campaign
    assert stats["quests"] >= 12
    assert stats["npcs"] >= 5
    assert stats["traders"] >= 4

    quest_names = {q["quest"] for q in plan["quests"]}
    # Verify core survival & non-mob depth quests are active
    assert "water_purification" in quest_names
    assert "desert_harvest" in quest_names
    assert "leatherwork_tack" in quest_names
    assert "fortify_compound" in quest_names
    assert "comms_relay_grid" in quest_names
    assert "medical_relief" in quest_names


def test_expansion_quest_json_schema(compiled_campaign):
    plan, stats = compiled_campaign
    quests_dir = EXPANSION_QUESTS_DIR / "Quests"
    assert quests_dir.exists()

    quest_files = list(quests_dir.glob("Quest_*.json"))
    assert len(quest_files) >= 12

    for qf in quest_files:
        data = json.loads(qf.read_text())
        assert data["ConfigVersion"] == 22
        assert isinstance(data["ID"], int)
        assert len(data["Title"]) > 0
        assert len(data["Descriptions"]) >= 3
        assert len(data["Objectives"]) >= 1
        assert len(data["QuestGiverIDs"]) >= 1
        assert len(data["QuestTurnInIDs"]) >= 1
        # Hardcore survival incentive: death cancels quest
        assert data["CancelQuestOnPlayerDeath"] == 1
        assert data["Active"] == 1


def test_expansion_objective_json_schema(compiled_campaign):
    plan, stats = compiled_campaign
    objs_dir = EXPANSION_QUESTS_DIR / "Objectives"
    assert objs_dir.exists()

    for folder in ("Delivery", "Collection", "Travel", "AIPatrol", "AICamp"):
        sub = objs_dir / folder
        if not sub.exists():
            continue
        for of in sub.glob("Objective_*.json"):
            data = json.loads(of.read_text())
            assert data["ConfigVersion"] == 28
            assert isinstance(data["ID"], int)
            assert data["Active"] == 1
            assert len(data["ObjectiveText"]) > 0

            # If delivery or collection, check collections list
            if folder in ("Delivery", "Collection"):
                assert "Collections" in data
                assert len(data["Collections"]) >= 1
                for c in data["Collections"]:
                    assert c["Amount"] >= 1
                    assert len(c["ClassName"]) > 0

            # If travel, check position is within Nasdara map bounds
            if folder == "Travel":
                assert "Position" in data
                pos = data["Position"]
                assert 0.0 <= pos[0] <= 16384.0
                assert 0.0 <= pos[2] <= 16384.0


def test_quest_npcs_are_stationed_properly(compiled_campaign):
    plan, stats = compiled_campaign
    npcs_dir = EXPANSION_QUESTS_DIR / "NPCs"
    assert npcs_dir.exists()

    npc_files = list(npcs_dir.glob("QuestNPC_*.json"))
    assert len(npc_files) >= 5

    for nf in npc_files:
        data = json.loads(nf.read_text())
        assert data["ConfigVersion"] == 6
        assert isinstance(data["ID"], int)
        assert len(data["NPCName"]) > 0
        assert data["NPCType"] == 2
        assert data["Active"] == 1
        pos = data["Position"]
        assert 0.0 <= pos[0] <= 16384.0
        assert 0.0 <= pos[2] <= 16384.0


def test_dialogue_framework_trees_generated(compiled_campaign):
    plan, stats = compiled_campaign
    dialog_dir = ROOT / "server" / "profiles" / "DialogFramework" / "Dialogues"
    assert dialog_dir.exists()

    for npc_id in (1, 2, 3, 4):
        dfile = dialog_dir / f"NPC_{npc_id}" / "Dialogue.json"
        assert dfile.exists(), f"Dialogue file missing for NPC {npc_id}"
        data = json.loads(dfile.read_text())
        assert data["ID"] == npc_id
        assert len(data["Nodes"]) >= 2


def test_init_c_gives_survivor_directive():
    src = INIT_C.read_text()
    give_start = re.search(r"static void GiveStartKit\(PlayerBase player,.*?\n\t\}", src, re.S).group(0)
    assert 'player.GetInventory().CreateInInventory("Paper");' in give_start
    assert "[DZDS Arrivals] Issued Survivor Field Directive" in give_start


def test_survival_goals_api_integration():
    mgr = get_manager()
    summary = mgr.get_summary()
    assert "projects" in summary
    assert "personal_milestones" in summary
    assert len(summary["projects"]) >= 5
    project_ids = {p["id"] for p in summary["projects"]}
    assert "water_reserves" in project_ids
    assert "medical_stockpile" in project_ids
    assert "fortification" in project_ids
    assert "fuel_depot" in project_ids
    assert "comms_grid" in project_ids
