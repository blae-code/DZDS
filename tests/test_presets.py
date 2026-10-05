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


def test_faction_rules_from_spec():
    f = load("presets/factions.yaml")["factions"]
    assert f["Survivors"]["stance"]["Players"] in {"neutral", "friendly"}
    assert f["Raiders"]["stance"]["Guards"] == "hostile"
    assert f["Guards"]["stance"]["Raiders"] == "hostile"
    for name in ("Survivors", "Raiders", "Guards"):
        assert f[name]["stance"]["Infected"] == "hostile"
        assert f["Infected"]["stance"][name] == "hostile"


def test_faction_combat_within_bounds_and_territories_are_roles():
    p = load("presets/factions.yaml")
    assert check_bounds(p["combat"]) == []
    roles = load("maps/_roles.yaml")["roles"]
    for faction, rs in p["territories"].items():
        assert set(rs) <= set(roles), faction


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
