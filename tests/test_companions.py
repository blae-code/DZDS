"""Unit and integration tests for the Hirable NPC Companions and Qalat-e Lut Garrison system."""
import json
import re
from pathlib import Path

import pytest
import yaml

import active
from gamemaster import web
from gamemaster.companions import CompanionsManager, get_manager, load_config

ROOT = Path(__file__).resolve().parent.parent
INIT_C = ROOT / "server" / "mpmissions" / "dayzOffline.nasdara" / "init.c"
LOADOUTS_DIR = ROOT / "server" / "profiles" / "ExpansionMod" / "Loadouts"
PORTAL_HTML = ROOT / "src" / "gamemaster" / "player_portal.html"
QUESTS_YAML = ROOT / "presets" / "quests.yaml"
DIALOGUE_NPC1 = ROOT / "server" / "profiles" / "DialogFramework" / "Dialogues" / "NPC_1" / "Dialogue.json"


def test_companions_yaml_integrity():
    cfg = load_config()
    assert "settlement" in cfg
    assert "command_guide" in cfg
    assert "companions" in cfg

    settlement = cfg["settlement"]
    assert settlement["id"] == "qalat_e_lut"
    assert settlement["hq_coordinates"] == [14837.0, 0.0, 7855.0]
    assert settlement["max_squad_size"] == 4

    comps = cfg["companions"]
    assert len(comps) == 4
    assert "soran_scout" in comps
    assert "kaveh_guard" in comps
    assert "yasmin_medic" in comps
    assert "rostam_scavenger" in comps

    for cid, spec in comps.items():
        assert len(spec["name"]) > 0
        assert len(spec["title"]) > 0
        assert spec["loadout"].startswith("DZDS_Settlers_")
        assert len(spec["position"]) == 3
        # Ensure within Nasdara bounds
        assert 0.0 <= spec["position"][0] <= 16384.0
        assert 0.0 <= spec["position"][2] <= 16384.0
        assert len(spec["retainer_cost"]) >= 1
        assert len(spec["role_perks"]) >= 1


def test_compiled_loadouts_exist_and_valid():
    for variant in ("scout", "guard", "medic", "scavenger"):
        lf = LOADOUTS_DIR / f"DZDS_Settlers_{variant}.json"
        assert lf.exists(), f"Missing loadout JSON: {lf.name}"
        data = json.loads(lf.read_text())
        assert "InventoryAttachments" in data
        assert len(data["InventoryAttachments"]) >= 5
        slot_names = {s["SlotName"] for s in data["InventoryAttachments"]}
        assert "Shoulder" in slot_names
        assert "Body" in slot_names
        assert "Feet" in slot_names


def test_companions_manager_lifecycle(tmp_path):
    state_file = tmp_path / "companions.json"
    mgr = CompanionsManager(state_path=state_file)
    summary = mgr.get_summary()

    assert summary["available_count"] == 4
    assert summary["hired_count"] == 0
    assert len(summary["roster"]) == 4

    # Test hiring Soran
    hired = mgr.hire_companion("soran_scout", "CommanderBlae", notes="Leading northern sweep")
    assert hired["status"] == "Hired"
    assert hired["hired_by"] == "CommanderBlae"
    assert hired["deployments"] == 1

    summary2 = mgr.get_summary()
    assert summary2["available_count"] == 3
    assert summary2["hired_count"] == 1
    soran = next(c for c in summary2["roster"] if c["id"] == "soran_scout")
    assert soran["status"] == "Hired"
    assert soran["hired_by"] == "CommanderBlae"
    assert "CommanderBlae" in summary2["hire_log"][0]["text"]

    # Test dismissing Soran back to Qalat-e Lut
    dismissed = mgr.dismiss_companion("soran_scout", reason="Expedition completed")
    assert dismissed["status"] == "Available"
    assert dismissed["hired_by"] is None

    summary3 = mgr.get_summary()
    assert summary3["available_count"] == 4
    assert summary3["hired_count"] == 0
    assert "returned to Qalat-e Lut" in summary3["hire_log"][0]["text"]

    # Test invalid companion ID
    with pytest.raises(ValueError):
        mgr.hire_companion("nonexistent_id", "Nobody")


def test_companions_api_endpoints():
    mgr = get_manager()

    # GET /api/companions
    status, res = web.handle_api("GET", "/api/companions", {}, {})
    assert status == 200
    assert "roster" in res
    assert "settlement" in res
    assert len(res["roster"]) == 4

    # POST /api/companions/hire
    body_hire = {"companion_id": "kaveh_guard", "player": "TestSurvivor"}
    status, res = web.handle_api("POST", "/api/companions/hire", {}, body_hire)
    assert status == 200
    assert res["status"] == "ok"
    assert res["companion"]["status"] == "Hired"
    assert res["companion"]["hired_by"] == "TestSurvivor"

    # POST /api/companions/dismiss
    body_dismiss = {"companion_id": "kaveh_guard", "reason": "Resting at HQ"}
    status, res = web.handle_api("POST", "/api/companions/dismiss", {}, body_dismiss)
    assert status == 200
    assert res["status"] == "ok"
    assert res["companion"]["status"] == "Available"

    # POST /api/companions/hire with invalid ID
    bad_hire = {"companion_id": "invalid_id", "player": "Ghost"}
    status, res = web.handle_api("POST", "/api/companions/hire", {}, bad_hire)
    assert status == 400
    assert "error" in res


def test_init_c_companion_integration():
    src = INIT_C.read_text()
    assert "class DZDSCompanionDef" in src
    assert "class DZDSCompanionManager" in src
    assert "DZDSCompanionManager.Init();" in src
    assert "DZDSCompanionManager.EquipRecruitCompanion(ai);" in src
    assert 's_Roster.Insert(new DZDSCompanionDef("Soran the Scout"' in src
    assert 's_Roster.Insert(new DZDSCompanionDef("Kaveh the Sentinel"' in src
    assert 's_Roster.Insert(new DZDSCompanionDef("Dr. Yasmin"' in src
    assert 's_Roster.Insert(new DZDSCompanionDef("Rostam the Scavenger"' in src
    assert "ExpansionHumanLoadout.Apply(ai, def.Loadout, false);" in src


def test_player_portal_companions_section():
    html = PORTAL_HTML.read_text()

    # Static portal constraints
    assert "<script" not in html, "player_portal.html must never contain <script> tags"
    assert "/api/" not in html, "player_portal.html must never contain /api/ references"

    # Navigation & Section
    assert '<a href="#companions">Companions &amp; Recruits</a>' in html
    assert '<section id="companions"' in html
    assert "Soran the Scout" in html
    assert "Kaveh the Sentinel" in html
    assert "Dr. Yasmin" in html
    assert "Rostam the Scavenger" in html
    assert "Squad Command &amp; Enlistment Field Manual" in html


def test_enlistment_contracts_and_dialogue():
    qdata = yaml.safe_load(QUESTS_YAML.read_text())
    fq = qdata["fixed_quests"]

    assert 106 in fq
    assert 107 in fq
    assert 108 in fq
    assert 109 in fq

    assert "Soran" in fq[106]["title"]
    assert "Kaveh" in fq[107]["title"]
    assert "Yasmin" in fq[108]["title"]
    assert "Rostam" in fq[109]["title"]

    for qid in (106, 107, 108, 109):
        assert fq[qid]["npc_giver"] == 1
        assert fq[qid]["npc_turnin"] == 1
        assert fq[qid]["cancel_on_death"] is True
        assert len(fq[qid]["items_required"]) >= 1

    # Check Dialogue for NPC 1 has Node 6 for companion enlistment
    ddata = json.loads(DIALOGUE_NPC1.read_text())
    node_ids = {n["ID"] for n in ddata["Nodes"]}
    assert 6 in node_ids
    node6 = next(n for n in ddata["Nodes"] if n["ID"] == 6)
    assert "Soran the Scout" in node6["SpeakerText"]
    assert "Kaveh the Sentinel" in node6["SpeakerText"]
    assert "Dr. Yasmin" in node6["SpeakerText"]
    assert "Rostam the Scavenger" in node6["SpeakerText"]
