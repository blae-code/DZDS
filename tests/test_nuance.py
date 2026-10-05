"""Faction nuance tooling: patrol generation and dynamic diplomacy."""
import datetime as dt

import pytest
import yaml

import diplomacy
import patrol_gen
from apply_ai_calibration import PATROL_BOUNDS, check_bounds
from test_presets import BEHAVIOURS, ENGINE_FRIENDLY, FORMATIONS, SPEEDS, STANCES, dzds_relations


def test_generated_patrols_are_valid_expansion_values():
    patrols = patrol_gen.generate("chernarusplus")
    assert patrols
    customs = {f"{c}" for c in dzds_relations()}
    bounds = yaml.safe_load((patrol_gen.ROOT / "maps" / "chernarusplus.yaml").read_text())["bounds"]
    for p in patrols:
        assert p["Faction"] in customs, p["Name"]
        assert p["Behaviour"] in BEHAVIOURS and p["Speed"] in SPEEDS and p["UnderThreatSpeed"] in SPEEDS
        assert p["DefaultStance"] in STANCES and p["Formation"] in FORMATIONS
        assert check_bounds(p, PATROL_BOUNDS) == [], p["Name"]
        assert 1 <= p["NumberOfAI"] <= p["NumberOfAIMax"]
        assert 0 < p["Chance"] <= 1
        for x, y, z in p["Waypoints"]:
            assert bounds[0] <= x <= bounds[2] and bounds[1] <= z <= bounds[3]


def test_interim_mode_uses_builtin_factions():
    for p in patrol_gen.generate("chernarusplus", interim=True):
        assert p["Faction"] in ENGINE_FRIENDLY


def test_every_held_site_is_defended():
    f = yaml.safe_load((patrol_gen.ROOT / "presets" / "factions.yaml").read_text())
    control = f["initial_control"]["chernarusplus"]
    names = [p["Name"] for p in patrol_gen.generate("chernarusplus")]
    for faction, sites in control.items():
        if faction == "contested":
            continue
        for site in sites:
            assert any(n.startswith(faction) and n.endswith(f"@ {site}") for n in names), (faction, site)


def test_routes_go_to_another_held_site_and_ranks_get_variant_loadouts():
    patrols = {p["Name"]: p for p in patrol_gen.generate("chernarusplus")}
    route = patrols["Rust enforcer_patrol @ Chernogorsk"]
    assert len(route["Waypoints"]) == 2 and route["Waypoints"][0] != route["Waypoints"][1]
    assert patrols["Karkas elder_marksman @ Altar"]["Loadout"] == "DZDS_Karkas_elder"
    assert patrols["Karkas ridge_watch @ Altar"]["DefaultStance"] == "PRONE"


FACTIONS = yaml.safe_load((patrol_gen.ROOT / "presets" / "factions.yaml").read_text())["factions"]


def test_diplomacy_translates_names_and_expires():
    dip = {"overrides": [
        {"from": "Karkas", "to": "Rust", "stance": "friendly", "until": "2026-12-01"},
        {"from": "Settlers", "to": "Peacekeepers", "stance": "hostile", "until": "2026-01-01"},
    ]}
    out = diplomacy.compile_overrides(dip, FACTIONS, dt.date(2026, 11, 1))
    assert out == [{"From": "DZDSKarkas", "To": "DZDSRust", "Friendly": True}]


def test_diplomacy_rejects_unknown_faction():
    with pytest.raises(SystemExit):
        diplomacy.compile_overrides({"overrides": [{"from": "CDF", "to": "Rust", "stance": "hostile"}]},
                                    FACTIONS, dt.date.today())


def test_every_dzds_isfriendly_consults_diplomacy():
    src = (patrol_gen.ROOT / "mods/DZDS/Scripts/3_Game/DZDS/Factions/DZDSFactions.c").read_text()
    assert src.count("bool IsFriendly(") == src.count("DZDSDiplomacy.Get(GetName(), other.GetName())") == 5
