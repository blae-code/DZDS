import json
import re
from pathlib import Path

import active
import campaign_gen
import front_plan
from gamemaster.ledger import WarLedger

ROOT = Path(__file__).resolve().parent.parent


def test_campaign_compiler_produces_valid_expansion_and_dialogue_files(tmp_path):
    """Verify that campaign_gen emits fully conformant Expansion Quests, Traders and Dialogues."""
    map_name = "nasdara"
    led = WarLedger.new(map_name)
    traders_cfg = front_plan.load("presets/traders.yaml")
    quests_cfg = front_plan.load("presets/quests.yaml")

    plan = {
        "turn": led.s.turn,
        "traders": front_plan.plan_traders(led, traders_cfg),
        "quests": front_plan.plan_quests(led, quests_cfg),
    }

    stats = campaign_gen.compile_campaign(map_name, led, plan, dry_run=False)
    assert stats["quests"] >= 6
    assert stats["objectives"] >= 6
    assert stats["npcs"] >= 4
    assert stats["traders"] >= 4
    assert stats["dialogues"] >= 4

    # 1. Validate Quests
    quests_dir = ROOT / "server" / "profiles" / "ExpansionMod" / "Quests" / "Quests"
    quest_files = list(quests_dir.glob("Quest_*.json"))
    assert len(quest_files) == stats["quests"]

    for qf in quest_files:
        data = json.loads(qf.read_text())
        assert data["ConfigVersion"] == 22
        assert data["ID"] >= 100
        assert data["Title"]
        assert len(data["Descriptions"]) >= 3
        assert data["Objectives"]
        assert data["QuestGiverIDs"]
        assert data["QuestTurnInIDs"]
        assert data["Active"] == 1

        # Verify referenced objective file exists
        for obj_ref in data["Objectives"]:
            otype = obj_ref["ObjectiveType"]
            oid = obj_ref["ID"]
            dname, pfx = campaign_gen.DIR_MAP[otype]
            obj_path = ROOT / "server" / "profiles" / "ExpansionMod" / "Quests" / "Objectives" / dname / f"Objective_{pfx}_{oid}.json"
            assert obj_path.exists(), f"Missing objective file {obj_path}"
            obj_data = json.loads(obj_path.read_text())
            assert obj_data["ConfigVersion"] == 28
            assert obj_data["ID"] == oid

    # 2. Validate Quest NPCs
    npcs_dir = ROOT / "server" / "profiles" / "ExpansionMod" / "Quests" / "NPCs"
    npc_files = list(npcs_dir.glob("QuestNPC_*.json"))
    assert len(npc_files) >= stats["npcs"]

    loadouts_dir = ROOT / "server" / "profiles" / "ExpansionMod" / "Loadouts"
    for nf in npc_files:
        data = json.loads(nf.read_text())
        assert data["ConfigVersion"] == 6
        assert data["ID"] > 0
        assert data["NPCName"]
        assert len(data["Position"]) == 3
        x, y, z = data["Position"]
        assert 0 <= x <= 16384 and 0 <= z <= 16384
        assert y > 0, "NPC altitude should be above sea level"
        # Verify loadout file exists if specified
        if data["NPCLoadoutFile"]:
            loadout_file = loadouts_dir / f"{data['NPCLoadoutFile']}.json"
            assert loadout_file.exists(), f"Loadout {loadout_file} missing for NPC {data['NPCName']}"

    # 3. Validate Traders
    exp_traders_dir = ROOT / "server" / "profiles" / "ExpansionMod" / "Traders"
    for t_def in campaign_gen.TRADER_DEFS.values():
        t_file = exp_traders_dir / t_def["file"]
        assert t_file.exists()
        t_data = json.loads(t_file.read_text())
        assert t_data["m_Version"] == 13
        assert t_data["DisplayName"]
        assert t_data["Currencies"]

    # 4. Validate Dialogue Framework
    dialog_dir = ROOT / "server" / "profiles" / "DialogFramework" / "Dialogues"
    for npc_id in [1, 2, 3, 4, 5]:
        dlg_file = dialog_dir / f"NPC_{npc_id}" / "Dialogue.json"
        assert dlg_file.exists()
        dlg_data = json.loads(dlg_file.read_text())
        assert dlg_data["ID"] == npc_id
        assert dlg_data["SpeakerName"]
        assert dlg_data["Nodes"]
        root = next(n for n in dlg_data["Nodes"] if n["ID"] == dlg_data["RootNodeID"])
        actions = {r["ActionType"] for r in root["Responses"]}
        assert "SHOW_QUEST_LIST" in actions
        assert "END_CONVERSATION" in actions


def test_war_ledger_quest_completion_and_liberation():
    """Verify that completing contracts feeds into the war ledger, liberating territory."""
    led = WarLedger.new("nasdara")
    assert led.s.control["Northern Dam"] == "contested"

    # Maintain pressure at Southern Barracks so off-screen resolution doesn't resolve it
    led.s.pressure["Southern Barracks"] = {"Peacekeepers": 2}

    # Player 'Blae' completes the 'Break the Siege' contract at Northern Dam
    events = led.record_quest_completion("break_the_siege", "Blae", site="Northern Dam")
    assert any("applied 8 liberation pressure" in e for e in events)
    assert led.s.pressure["Northern Dam"]["Settlers"] >= 8
    assert led.s.deeds["Northern Dam"]["Blae"] >= 3

    # Advance the war turn: Settlers now have dominant pressure to take the site
    turn_events = led.turn(force=True)
    assert led.s.control["Northern Dam"] == "Settlers"
    assert any("militia drove the defenders out of Northern Dam" in e for e in turn_events)


def test_quest_impact_on_tribal_strength_and_standing():
    """Wiping out the Jackals camp lowers their strength and raises Settler standing."""
    led = WarLedger.new("nasdara")
    initial_jackal_strength = led.s.strength["Jackals"]
    initial_settler_standing = led.s.standing["Settlers"]

    events = led.record_quest_completion("clear_jackal_camp", "Host", site="North Highway Pileup")
    assert any("completed campaign contract" in e for e in events)
    assert led.s.strength["Jackals"] < initial_jackal_strength
    assert led.s.standing["Settlers"] > initial_settler_standing


def test_water_rights_and_charter_unlocks():
    """Completing water rights and UN intro adjusts standings and unlocks traders."""
    led = WarLedger.new("nasdara")
    initial_rust_standing = led.s.standing["Rust"]
    initial_pk_standing = led.s.standing["Peacekeepers"]

    led.record_quest_completion("water_rights", "Blae", site="Hilltop Water Station")
    assert led.s.standing["Rust"] > initial_rust_standing

    led.record_quest_completion("un_intro", "Blae", site="Eastern Airfield")
    assert led.s.standing["Peacekeepers"] > initial_pk_standing
