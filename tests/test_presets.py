"""Guards on design intent: spec rules encoded in presets/ and maps/ can't silently drift."""
import subprocess
import xml.etree.ElementTree as ET

import yaml

import maps_check
import modstring
import types_gen
from apply_ai_calibration import check_bounds

ROOT = modstring.ROOT


def load(rel):
    return yaml.safe_load((ROOT / rel).read_text())


# IsFriendly() relations transcribed from Expansion's source (Factions/*.c, 2026-10).
# "Passive"/"Observers" omitted. Update this if Expansion changes its factions.
ENGINE_FRIENDLY = {
    "West": {"West", "Civilian"},
    "East": {"East", "Civilian"},
    "Raiders": {"Raiders"},  # literally IsPassive() only, but never fights its own groups
    "Civilian": {"West", "East", "Raiders", "Civilian", "Infected"},
    "Infected": {"Infected"},
    "Guards": {"Guards"},
    "Mercenaries": {"Mercenaries"},
}


def test_faction_stances_match_engine():
    f = load("presets/factions.yaml")["factions"]
    engine = {name: spec["engine_faction"] for name, spec in f.items()}
    for name, spec in f.items():
        if engine[name] is None:  # vanilla Infected: not an Expansion faction
            continue
        for other, stance in spec["stance"].items():
            if engine[other] is None:
                continue  # zombies attack everyone regardless of faction
            friendly = engine[other] in ENGINE_FRIENDLY[spec["engine_faction"]]
            assert (stance == "friendly") == friendly, f"{name} -> {other}: preset says {stance}"


def test_faction_rules_from_spec():
    f = load("presets/factions.yaml")["factions"]
    # Survivors never initiate; the two armies are at war; Raiders hostile to all humans;
    # Infected are the universal enemy.
    assert all(v == "friendly" for k, v in f["Survivors"]["stance"].items() if k != "Infected")
    assert f["CDF"]["stance"]["ChDKZ"] == f["ChDKZ"]["stance"]["CDF"] == "hostile"
    assert all(v == "hostile" for k, v in f["Raiders"]["stance"].items() if k != "Raiders")
    for name in ("CDF", "ChDKZ", "Raiders", "Survivors"):
        assert f[name]["stance"]["Infected"] == "hostile"


def test_faction_combat_within_bounds_and_roles_valid():
    p = load("presets/factions.yaml")
    assert check_bounds(p["combat"]) == []
    roles = set(load("maps/_roles.yaml")["roles"])
    for name, spec in p["factions"].items():
        assert set(spec.get("holds_roles", [])) <= roles, name
    for res, spec in p["resources"].items():
        assert set(spec["from_roles"]) <= roles, res


def test_initial_control_uses_known_locations_once():
    p = load("presets/factions.yaml")
    for map_name, control in p["initial_control"].items():
        locs = set(load(f"maps/{map_name}.yaml")["locations"])
        seen = [loc for holders in control.values() for loc in holders]
        assert set(seen) <= locs
        assert len(seen) == len(set(seen)), "a location is assigned twice"


def test_chernarus_map_complete():
    assert maps_check.check(load("maps/chernarusplus.yaml"), load("maps/_roles.yaml")["roles"]) == []


def test_types_preset_compiles_to_valid_xml(tmp_path):
    root, warnings = types_gen.build(load("presets/types_dzds.yaml"))
    assert warnings == []
    out = tmp_path / "t.xml"
    ET.ElementTree(root).write(out, encoding="UTF-8", xml_declaration=True)
    subprocess.run(["xmllint", "--noout", str(out)], check=True)
    assert root.find("type[@name='SparkPlug']/nominal").text == "20"


def test_types_register_is_idempotent(tmp_path):
    core = tmp_path / "cfgeconomycore.xml"
    core.write_text("<economycore>\n</economycore>\n")
    assert types_gen.register(core) is True
    assert types_gen.register(core) is False
    assert core.read_text().count('folder="dzds"') == 1


def test_every_enabled_mod_verified_and_one_map_mod():
    mods = modstring.ordered(modstring.load_mods())
    assert all(m.get("verified") for m in mods)
    map_mods = [m for m in mods if m["name"] in {"Basic Map", "DayZ-Expansion-Navigation"}]
    assert len(map_mods) == 1
