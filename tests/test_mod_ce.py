"""Modded CE content: registered under presets/mod_loot.yaml's policy, never over vanilla/dzds."""
import xml.etree.ElementTree as ET
from pathlib import Path

import active
import mod_ce

TYPES = """<?xml version="1.0"?>
<types>
  <type name="MilGear"><nominal>4</nominal><min>2</min><usage name="Military"/><usage name="Town"/>
    <value name="Tier2"/><value name="Tier3"/></type>
  <type name="TownOnly"><nominal>3</nominal><min>1</min><usage name="Town"/></type>
  <type name="Crafted"><nominal>0</nominal><min>0</min></type>
  <type name="AdminVest"><nominal>1</nominal><usage name="Military"/></type>
  <type name="Apple"><nominal>9</nominal><usage name="Farm"/></type>
</types>
<types><type name="SecondRoot"><nominal>1</nominal></type></types>"""
SPAWNABLE = """<spawnabletypes><type name="MilGear"><cargo preset="x"/></type>
<type name="TownOnly"><cargo preset="y"/></type></spawnabletypes>"""


def _mod(tmp_path, mod_id=1):
    d = tmp_path / str(mod_id)
    d.mkdir()
    (d / "types.xml").write_text(TYPES)
    (d / "spawn.xml").write_text(SPAWNABLE)
    return {mod_id: {"id": mod_id, "enabled": True}}


def test_read_entries_tolerates_several_roots(tmp_path):
    _mod(tmp_path)
    names = [t.get("name") for t in mod_ce.read_entries(tmp_path / "1" / "types.xml", "types")]
    assert names == ["MilGear", "TownOnly", "Crafted", "AdminVest", "Apple", "SecondRoot"]


def test_curated_filters_scale_and_reserve(tmp_path):
    mods = _mod(tmp_path)
    preset = {"mods": {1: {"name": "Gear", "policy": "curated", "types": ["types.xml"],
                           "spawnabletypes": ["spawn.xml"], "exclude": ["Admin*"],
                           "usages": ["Military"], "min_tier": "Tier3", "nominal_scale": 0.5}}}
    (res,) = mod_ce.build(preset, mods, tmp_path, reserved={"Apple"})
    got = {t.get("name"): t for t in res.types}
    assert set(got) == {"MilGear", "Crafted", "SecondRoot"}   # TownOnly loses its only usage
    mil = got["MilGear"]
    assert [u.get("name") for u in mil.findall("usage")] == ["Military"]
    assert [v.get("name") for v in mil.findall("value")] == ["Tier3"]
    assert mil.findtext("nominal") == "2" and mil.findtext("min") == "1"
    assert got["SecondRoot"].findtext("nominal") == "1"        # scaled, but never to 0
    assert res.skipped == {"excluded": 1, "defined by vanilla or dzds": 1, "filtered by policy": 1}
    assert [t.get("name") for t in res.spawnable] == ["MilGear"]


def test_none_disabled_and_duplicates(tmp_path):
    mods = _mod(tmp_path, 1)
    d2 = tmp_path / "2"
    d2.mkdir()
    (d2 / "types.xml").write_text(TYPES)
    mods[2] = {"id": 2, "enabled": True}
    mods[3] = {"id": 3, "enabled": False}
    preset = {"mods": {1: {"policy": "author", "types": ["types.xml"]},
                       2: {"policy": "author", "types": ["types.xml"]},
                       3: {"policy": "author", "types": ["types.xml"]},
                       4: {"policy": "none", "reason": "why"}}}
    r1, r2, r3, r4 = mod_ce.build(preset, mods, tmp_path, reserved=set())
    assert len(r1.types) == 6 and not r2.types and r2.skipped == {"duplicate": 6}
    assert r3.policy == "none" and "not enabled" in r3.note and r4.note == "why"


def test_register_owns_only_its_block(tmp_path):
    core = tmp_path / "cfgeconomycore.xml"
    core.write_text('<economycore>\n    <ce folder="dzds">\n        <file name="types_dzds.xml" type="types" />\n'
                    '    </ce>\n</economycore>\n')
    once = mod_ce.register(core, [("a_types.xml", "types"), ("a_spawnabletypes.xml", "spawnabletypes")])
    core.write_text(once)
    assert mod_ce.register(core, [("a_types.xml", "types"), ("a_spawnabletypes.xml", "spawnabletypes")]) == once
    ET.fromstring(once)
    gone = mod_ce.register(core, [])
    assert 'folder="dzds_mods"' not in gone and 'folder="dzds"' in gone


def test_preset_covers_every_enabled_mod_that_ships_ce_files():
    """A mod with a types file in its Workshop folder must be in mod_loot.yaml (author, curated
    or none with a reason), so new mods can't silently go unregistered again."""
    preset = active.load_yaml("presets/mod_loot.yaml")["mods"]
    for mod_id, spec in preset.items():
        assert spec.get("policy") in {"author", "curated", "none"}, mod_id
        if spec["policy"] == "none":
            assert spec.get("reason"), mod_id
        else:
            assert spec.get("types"), mod_id
    ws = mod_ce.workshop_dir()
    if not ws.is_dir():
        return
    for m in active.load_yaml("config/mods.yaml")["mods"]:
        if not m.get("enabled", True) or not (ws / str(m["id"])).is_dir() or m["id"] == 3815870621:
            continue
        ships = any("<types" in p.read_text(errors="replace")[:4000] for p in (ws / str(m["id"])).rglob("*.xml"))
        if ships:
            assert m["id"] in preset or str(m["id"]) in preset, f"{m['name']} ({m['id']}) ships CE types"


def test_generated_files_are_registered_and_parse():
    mission = active.mission_dir()
    core = (mission / "cfgeconomycore.xml").read_text()
    folder = mission / mod_ce.FOLDER
    if not folder.exists():
        return
    for f in folder.glob("*.xml"):
        assert f'name="{f.name}"' in core, f.name
        ET.parse(f)
