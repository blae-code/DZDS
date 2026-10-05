"""Contract tests: JSON written by our tools matches the fields @DZDS's Enforce classes read."""
import asyncio
import datetime as dt
import re

import diplomacy
import dzds_profile
import yaml
from gamemaster import dispatch
from gamemaster.ledger import WarLedger
from gamemaster.schema import WorldAction

ROOT = dzds_profile.ROOT
SRC = "\n".join(p.read_text() for p in (ROOT / "mods" / "DZDS" / "Scripts").rglob("*.c"))


def fields(cls: str) -> set[str]:
    body = re.search(rf"class {cls}\s*\{{(.*?)\n\}};", SRC, re.S).group(1)
    return set(re.findall(r"^\s*(?:ref\s+)?[\w<>\s]+?\s+(\w+);", body, re.M))


WORLD = yaml.safe_load((ROOT / "presets" / "world.yaml").read_text())


def test_settings_and_markers_match_enforce_classes():
    assert set(dzds_profile.settings(WORLD)) == fields("DZDSSettings")
    world = {**WORLD, "markers": {**WORLD["markers"], "by_holder": {"Jackals": "SomeObject"}}}
    mk = dzds_profile.markers(world, WarLedger.new("chernarusplus"))
    assert mk and set(mk[0]) == fields("DZDSMarker")
    assert {m["ClassName"] for m in mk} == {"SomeObject"}           # null holders skipped


def test_commands_match_enforce_class_and_respect_allowlist():
    actions = dispatch.load_actions()
    cmds = dispatch.to_commands(WorldAction(target="spawn_heli_crash"), (4500.0, 2500.0), actions)
    assert cmds and set(cmds[0]) == fields("DZDSCommand")
    assert cmds[0]["ClassName"] in dzds_profile.settings(WORLD)["AllowedClassNames"]
    assert dispatch.to_commands(WorldAction(target="spawn_airdrop"), (1.0, 1.0), actions) == []
    assert dispatch.to_commands(WorldAction(target="spawn_heli_crash"), None, actions) == []


def test_diplomacy_output_matches_enforce_class():
    factions = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())["factions"]
    out = diplomacy.compile_overrides({"overrides": [{"from": "Karkas", "to": "Rust", "stance": "friendly"}]},
                                      factions, dt.date.today())
    assert set(out[0]) == fields("DZDSRelation")


def test_local_queue_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("GM_TELEMETRY", "file")
    w = dispatch.QueueWriter()
    w.local_dir = tmp_path
    path = asyncio.run(w.write([{"Type": "spawn", "ClassName": "X", "X": 1.0, "Z": 2.0, "Count": 1}]))
    assert path and (tmp_path / path.split("/")[-1]).exists()
    assert asyncio.run(w.write([])) is None


def test_mod_config_registers_all_script_modules():
    cfg = (ROOT / "mods" / "DZDS" / "config.cpp").read_text()
    for mod, folder in (("gameScriptModule", "3_Game"), ("worldScriptModule", "4_World"),
                        ("missionScriptModule", "5_Mission")):
        assert re.search(rf"class {mod}.*?\"DZDS/Scripts/{folder}\"", cfg, re.S), mod
