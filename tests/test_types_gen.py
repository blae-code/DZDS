"""Respawn vehicles and their parts must be known to the CE (types), or they don't persist.

Blae 2026-10-16: modded respawn vehicles. Vanilla registers its own vehicles with nominal 0 and
a 45-day lifetime (the CE never spawns them, but keeps them); types_gen does the same for every
arrivals.yaml vehicle and part that vanilla types.xml doesn't already have.
"""
import xml.etree.ElementTree as ET

import yaml

import active
import arrivals
import types_gen


def _built():
    mission = arrivals.mission_dir(active.map_data("nasdara"))
    vanilla = {t.get("name") for t in ET.parse(mission / "db" / "types.xml").getroot().findall("type")}
    preset = yaml.safe_load(types_gen.PRESET.read_text())
    cfg = yaml.safe_load(arrivals.PRESET.read_text())
    root, _ = types_gen.build(preset, vanilla=vanilla, arrival_cfg=cfg)
    return vanilla, cfg, {t.get("name"): t for t in root.findall("type")}


def test_every_arrival_vehicle_and_part_is_registered():
    vanilla, cfg, types = _built()
    for v in cfg["vehicles"]:
        for name in [v["class"]] + v["parts"]:
            assert name in vanilla or name in types, name


def test_registered_vehicles_follow_vanillas_vehicle_entry():
    vanilla, cfg, types = _built()
    modded = [v["class"] for v in cfg["vehicles"] if v["class"] not in vanilla]
    assert modded, "the roster has modded vehicles"
    for name in modded:
        t = types[name]
        assert (t.findtext("nominal"), t.findtext("min"), t.findtext("lifetime")) == ("0", "0", "3888000"), name
        assert t.find("category") is None and t.find("usage") is None, name


def test_registered_parts_never_spawn_as_loot():
    vanilla, cfg, types = _built()
    parts = {p for v in cfg["vehicles"] for p in v["parts"]} - vanilla
    assert parts
    for name in parts:
        t = types[name]
        assert (t.findtext("nominal"), t.findtext("min")) == ("0", "0"), name
        assert t.find("usage") is None, f"{name} has a usage, so the CE could place it as loot"


def test_vanilla_entries_are_not_overridden():
    vanilla, _, types = _built()
    assert not (set(types) & vanilla)


def test_arrivals_accepts_classnames_from_our_types_file(tmp_path):
    mission = tmp_path
    (mission / "db").mkdir()
    (mission / "db" / "types.xml").write_text('<types><type name="CarBattery"/></types>')
    (mission / "dzds").mkdir()
    (mission / "dzds" / "types_dzds.xml").write_text('<types><type name="CrSk_VAZ_2107"/></types>')
    assert {"CarBattery", "CrSk_VAZ_2107"} <= arrivals.known_types(mission)
