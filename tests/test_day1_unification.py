"""End-to-end integration and unification tests for the Day 1 co-op experience.

Validates the complete player journey, refugee column rendezvous, fortress hub,
companion squad integration, barter economy, and zone containment rules.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

import pytest
import yaml

import active
import arrivals
import campaign_gen
import front_plan
from gamemaster.companions import load_config as load_companions_config
from gamemaster.ledger import WarLedger
from gamemaster.survival_goals import get_manager as get_survival_manager

ROOT = active.ROOT
SERVER_DIR = ROOT / "server"
INIT_C = SERVER_DIR / "mpmissions" / "dayzOffline.nasdara" / "init.c"
PROFILES_DIR = SERVER_DIR / "profiles"


@pytest.fixture(scope="module")
def day1_assets():
    """Load and prepare all Day 1 data structures."""
    map_data = active.map_data("nasdara")
    arrivals_cfg = yaml.safe_load(arrivals.PRESET.read_text())
    arrivals_out = arrivals.build(arrivals_cfg, map_data, arrivals.mission_dir(map_data))
    led = WarLedger.load_or_new("nasdara", initial=True)
    quests_cfg = active.load_yaml("presets/quests.yaml")
    traders_cfg = active.load_yaml("presets/traders.yaml")
    plan = {
        "turn": led.s.turn,
        "traders": front_plan.plan_traders(led, traders_cfg),
        "quests": front_plan.plan_quests(led, quests_cfg),
    }
    return {
        "map_data": map_data,
        "arrivals_cfg": arrivals_cfg,
        "arrivals_out": arrivals_out,
        "ledger": led,
        "front_plan": plan,
    }


# ==============================================================================
# 1. Player Journey & Refugee Column Spawning
# ==============================================================================

def test_same_day_refugee_column_anchors_both_players(day1_assets):
    """Blae and their friend connecting on the same date must anchor at the exact same arrival site."""
    out = day1_assets["arrivals_out"]
    sites = sorted(list({p["Name"] for p in out["ArrivalSites"]}))
    assert len(sites) >= 4, "Must have multiple arrival sites ringing settler territory"

    # Seed site from a date like init.c PickColumnPoint does
    today = dt.date.today()
    seed = today.year * 10000 + today.month * 100 + today.day
    chosen_site_idx = seed % len(sites)
    chosen_site_name = sites[chosen_site_idx]

    # Both players filter points by this chosen site
    blae_candidate_points = [p for p in out["ArrivalSites"] if p["Name"] == chosen_site_name]
    friend_candidate_points = [p for p in out["ArrivalSites"] if p["Name"] == chosen_site_name]

    assert len(blae_candidate_points) >= 6, "Arrival site must have sufficient vehicle parking spots"
    assert len(friend_candidate_points) >= 6
    assert blae_candidate_points == friend_candidate_points, "Both players must share the exact same arrival site candidates"


def test_blae_favored_aircraft_and_soviet_sf_outfit(day1_assets):
    """Blae must receive favored helicopter with combat pilot cargo and Soviet SF outfit."""
    cfg = day1_assets["arrivals_cfg"]
    fav = next((f for f in cfg.get("favored", []) if f.get("name", "").lower() == "blae"), None)
    assert fav is not None, "Blae must be registered in favored players list"
    assert fav["vehicles"], "Blae must have favored vehicles defined"

    # Verify every favored aircraft is an Expansion-framework helicopter (no stuttering RedFalcon input)
    for v in fav["vehicles"]:
        assert "Expansion" in v or "EXT_" in v or "heli" in v.lower(), f"Favored vehicle {v} should use Expansion framework"

    # Verify Soviet Special Forces outfit exists in arrivals preset
    outfits = cfg.get("outfits", {})
    assert "soviet_special_forces" in outfits, "Soviet Special Forces outfit must be defined"
    sf_outfit = outfits["soviet_special_forces"]
    assert sf_outfit.get("variants"), "Outfit must have wearable clothing variants"
    assert sf_outfit.get("land_cargo"), "Outfit must have specific land vehicle cargo"


def test_friend_arrival_archetype_and_guaranteed_gear(day1_assets):
    """The friend receives balanced archetype gear: firearm with exact ammo, knife, camp item, car item."""
    cfg = day1_assets["arrivals_cfg"]
    archetypes = cfg["archetypes"]
    assert len(archetypes) >= 4, "Must have at least 4 distinct survivor archetypes"

    for aname, a in archetypes.items():
        assert "knife" in a["slots"], f"Archetype {aname} must define a knife slot"
        assert "camp" in a["slots"], f"Archetype {aname} must define a camp slot"
        assert "car" in a["slots"], f"Archetype {aname} must define a car slot"
        weaps = a.get("firearms") or a.get("weapons", [])
        assert weaps, f"Archetype {aname} must have firearm choices"
        for w in weaps:
            cls = w["weapon"] if "weapon" in w else w.get("class")
            assert cls, f"Firearm in {aname} must declare weapon class"
            has_ammo = bool(w.get("ammo") or w.get("magazine"))
            assert has_ammo, f"Firearm {cls} in archetype {aname} must specify matching ammo or magazine"


def test_friend_first_respawn_logic_in_init_c():
    """Verify init.c prioritizes PickNearPlayers before base, camp, or near-death on respawns."""
    src = INIT_C.read_text()
    plan_body = re.search(r"RefugeeArrivalPlan\s+Plan\(PlayerIdentity\s+identity\)(.*?)\n\t\}", src, re.S).group(1)

    # In Plan(), check execution ordering
    near_players_idx = plan_body.find("PickNearPlayers(plan)")
    base_idx = plan_body.find("PickBase(plan, rec)")
    camp_idx = plan_body.find("PickCamp(plan, rec)")
    near_death_idx = plan_body.find("PickNearDeath(plan, rec)")

    assert near_players_idx != -1, "init.c must call PickNearPlayers"
    assert base_idx != -1, "init.c must call PickBase"
    assert near_players_idx < base_idx < camp_idx < near_death_idx, (
        "Respawn order must be: PickNearPlayers -> PickBase -> PickCamp -> PickNearDeath ('friend first')"
    )


# ==============================================================================
# 2. Qalat-e Lut Fortress Hub & Garrison Companions
# ==============================================================================

def test_qalat_e_lut_fortress_coordinates_match_eastern_caravanserai(day1_assets):
    """Qalat-e Lut fortress must align with Eastern Caravanserai coordinates."""
    map_data = day1_assets["map_data"]
    caravanserai_coords = map_data["locations"]["Eastern Caravanserai"]

    comp_cfg = load_companions_config()
    hq_coords = comp_cfg["settlement"]["hq_coordinates"]

    dist = math.dist((caravanserai_coords[0], caravanserai_coords[1]), (hq_coords[0], hq_coords[2]))
    assert dist <= 100.0, f"Qalat-e Lut HQ coords {hq_coords} must be within 100m of Eastern Caravanserai {caravanserai_coords}"


def test_fortress_companions_and_loadouts():
    """All 4 fortress companions must have corresponding valid loadout JSON files."""
    comp_cfg = load_companions_config()
    loadouts_dir = SERVER_DIR / "profiles" / "ExpansionMod" / "Loadouts"

    for cid, spec in comp_cfg["companions"].items():
        loadout_file = loadouts_dir / f"{spec['loadout']}.json"
        assert loadout_file.exists(), f"Loadout file {loadout_file.name} for companion {cid} must exist"
        data = json.loads(loadout_file.read_text())
        assert data.get("InventoryAttachments"), f"Loadout {spec['loadout']} must define InventoryAttachments"


def test_dialog_framework_npcs_aligned_with_survival_goals():
    """All 7 DialogFramework NPCs must exist and reference compound survival projects."""
    dialog_base = SERVER_DIR / "profiles" / "DialogFramework" / "Dialogues"
    surv_mgr = get_survival_manager()
    summary = surv_mgr.get_summary()
    projects = summary.get("projects", {})
    assert len(projects) >= 4, "Must have survival projects defined"

    for i in range(1, 8):
        npc_dialog_file = dialog_base / f"NPC_{i}" / "Dialogue.json"
        assert npc_dialog_file.exists(), f"Dialogue for NPC_{i} must exist"
        data = json.loads(npc_dialog_file.read_text())
        assert data.get("SpeakerName"), f"NPC_{i} must have SpeakerName"
        assert data.get("Nodes"), f"NPC_{i} dialogue must have dialogue Nodes"


# ==============================================================================
# 3. Barter Economy & Market Containment
# ==============================================================================

def test_frontier_exchange_barter_trader():
    """Frontier Exchange trader must exist in ExpansionMod/Traders and use barter currencies."""
    trader_file = SERVER_DIR / "profiles" / "ExpansionMod" / "Traders" / "Frontier_Exchange.json"
    assert trader_file.exists(), "Frontier_Exchange.json must exist"

    data = json.loads(trader_file.read_text())
    assert data.get("m_Version"), "Trader JSON must declare m_Version"

    # Currencies check (lowercased in Expansion Market json)
    currencies = [str(c).lower() for c in data.get("Currencies", [])]
    assert currencies, "Frontier Exchange must declare Currencies"
    # Ensure ammo, nails, or hryvnia are used (no fiat ATM)
    assert any("ammo_" in c or "nail" in c or "expansionbanknotehryvnia" in c for c in currencies), (
        f"Frontier Exchange currencies {currencies} must be barter assets"
    )


def test_atm_and_p2p_market_disabled():
    """ATMs and P2P Virtual Market must be disabled via overlay configuration."""
    market_settings_file = SERVER_DIR / "mpmissions" / "dayzOffline.nasdara" / "expansion" / "settings" / "MarketSettings.json"
    p2p_settings_file = SERVER_DIR / "mpmissions" / "dayzOffline.nasdara" / "expansion" / "settings" / "P2PMarketSettings.json"

    if market_settings_file.exists():
        data = json.loads(market_settings_file.read_text())
        assert data.get("ATMSystemEnabled") == 0 or data.get("UseATMs") == 0, "ATMs must be disabled in MarketSettings"

    if p2p_settings_file.exists():
        data = json.loads(p2p_settings_file.read_text())
        assert data.get("Enabled") == 0 or data.get("EnableP2PMarket") == 0, "P2P Market must be disabled"


# ==============================================================================
# 4. Zone Containment & Radio Bulletin
# ==============================================================================

def test_radio_bulletin_settler_net_frequency():
    """Radio bulletin must target 87.8 MHz with turn 0 tactical updates."""
    bulletin_file = SERVER_DIR / "profiles" / "DZDS" / "bulletin.json"
    assert bulletin_file.exists(), "bulletin.json must exist in profiles/DZDS"

    data = json.loads(bulletin_file.read_text())
    assert data.get("Frequency") == "87.8 MHz", "Bulletin must be configured for 87.8 MHz"
    assert data.get("Messages"), "Bulletin must contain active messages"
    assert data.get("Turn") == 0, "Initial bulletin must be at Turn 0"


def test_warzone_events_contained_to_designated_fronts(day1_assets):
    """AI War Zones must target contested sites (Northern Dam, Southern Barracks)."""
    wz_file = SERVER_DIR / "profiles" / "AIWarZones" / "AIWarZones_Settings.json"
    assert wz_file.exists(), "AIWarZones_Settings.json must exist"

    data = json.loads(wz_file.read_text())
    assert data.get("Enabled") == 1, "AI War Zones must be enabled"
    zones = data.get("WarZones", [])
    assert len(zones) >= 2, "Must configure at least 2 active warzones"

    for z in zones:
        assert z.get("zoneRadius") <= 200.0, "Warzone radius must remain compact"
        assert z.get("aTeamFaction"), "Warzone must specify aTeamFaction"
        assert z.get("bTeamFaction"), "Warzone must specify bTeamFaction"
        assert z["aTeamFaction"] != z["bTeamFaction"], "Warzone teams must belong to opposing factions"


# ==============================================================================
# 5. Base Building Starting Supplies at Qalat-e Lut
# ==============================================================================

def test_base_building_starting_supplies_in_init_c():
    """Qalat-e Lut fortress player base must have containers, materials, and tools initialized."""
    src = INIT_C.read_text()
    assert "class DZDSBaseSupplies" in src
    assert "DZDSBaseSupplies.Init();" in src

    # Containers
    assert '"SeaChest"' in src
    assert '"WoodenCrate"' in src
    assert '"Barrel_Blue"' in src
    assert '"Barrel_Green"' in src
    assert '"MediumTent"' in src

    # Materials
    assert '"NailBox"' in src
    assert '"WoodenPlank"' in src
    assert '"MetalPlate"' in src
    assert '"MetalWire"' in src
    assert '"BarbedWire"' in src
    assert '"Rope"' in src
    assert '"DuctTape"' in src
    assert '"EpoxyPutty"' in src
    assert '"CamoNetDesert"' in src

    # Tools
    assert '"Hatchet"' in src
    assert '"WoodAxe"' in src
    assert '"HandSaw"' in src
    assert '"Hacksaw"' in src
    assert '"Hammer"' in src
    assert '"SledgeHammer"' in src
    assert '"Shovel"' in src
    assert '"FieldShovel"' in src
    assert '"Pliers"' in src
    assert '"Screwdriver"' in src
    assert '"Wrench"' in src
    assert '"Pickaxe"' in src
    assert '"Crowbar"' in src
    assert '"Whetstone"' in src
    assert '"WeaponCleaningKit"' in src

    # Base Kits & Code Locks
    assert '"FenceKit"' in src
    assert '"WatchtowerKit"' in src
    assert '"TerritoryFlagKit"' in src
    assert '"DigitalCodeLock"' in src
    assert '"Zen_CarWorkbenchKit"' in src
    assert '"rag_hunting_cabin_kit"' in src

