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
    bul = dzds_profile.build_bulletin(WarLedger.new("nasdara"), world=WORLD)
    assert set(bul) == fields("DZDSBulletinData")
    assert bul["Messages"] and bul["Frequency"] == "87.8 MHz"
    src_bul = (ROOT / "mods" / "DZDS" / "Scripts" / "4_World" / "DZDS" / "DZDSBulletin.c").read_text()
    assert "TransmitterBase.Cast(" in src_bul and "GetCompEM().IsWorking()" in src_bul
    src_world = (ROOT / "mods" / "DZDS" / "Scripts" / "4_World" / "DZDS" / "DZDSWorld.c").read_text()
    assert "DZDSBulletin.Start();" in src_world


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


def test_mod_config_repairs_trailer_headlight():
    """Simply's Car Trailer declares `class HeadlightH7 {};` (no parent), which strips its
    Inventory_Base base: the engine then refuses to create headlights anywhere (2026-10-12).
    @DZDS re-parents it, and must load after the trailer for that to win the config merge."""
    mods = yaml.safe_load((ROOT / "config" / "mods.yaml").read_text())
    trailer = [m for m in mods["mods"] if m.get("id") == 3811085358]
    cfg = (ROOT / "mods" / "DZDS" / "config.cpp").read_text()
    required = re.search(r"requiredAddons\[\]\s*=\s*\{(.*?)\}", cfg, re.S).group(1)
    if trailer and trailer[0].get("enabled"):
        assert '"DZT_UtilityTrailer"' in required
        assert re.search(r"class\s+Inventory_Base\s*;", cfg)
        assert re.search(r"class\s+HeadlightH7\s*:\s*Inventory_Base\s*\{", cfg)
    else:                       # trailer gone: requiring it would stop @DZDS loading
        assert "DZT_UtilityTrailer" not in required


def test_survivor_anims_ai_guard():
    """1.30 boot (2026-10-15): Survivor Animations' per-frame UpdateSAItemInHandsType crashes the
    engine (Unhandled exception) on every Expansion AI, so @DZDS skips it for eAIBase. Requiring
    the addon makes the override compile after SA's method; it must go if SA is ever removed."""
    mods = yaml.safe_load((ROOT / "config" / "mods.yaml").read_text())
    sa = [m for m in mods["mods"] if m.get("id") == 2918418331]
    cfg = (ROOT / "mods" / "DZDS" / "config.cpp").read_text()
    required = re.search(r"requiredAddons\[\]\s*=\s*\{(.*?)\}", cfg, re.S).group(1)
    guard = (ROOT / "mods" / "DZDS" / "Scripts" / "4_World" / "DZDS" / "DZDSSurvivorAnimsAI.c").read_text()
    assert "#ifdef SURVIVOR_ANIMS" in guard
    assert re.search(r"modded\s+class\s+eAIBase\b", guard)
    assert re.search(r"override\s+void\s+UpdateSAItemInHandsType\s*\(\s*\)", guard)
    if sa and sa[0].get("enabled"):
        assert '"SurvivorAnims"' in required
    else:
        assert "SurvivorAnims" not in required


def test_warzones_factions_and_floor_guard():
    """AI War Zones turns unknown factions into West and spawns at the configured y (2026-10-23:
    both teams West, AI falling from mid-air). DZDSWarZones.c maps our factions and floors spawns;
    it needs War Zones compiled first, and must go if War Zones is ever removed (no #ifdef exists)."""
    mods = yaml.safe_load((ROOT / "config" / "mods.yaml").read_text())
    wz = [m for m in mods["mods"] if m.get("id") == 3521304609]
    cfg = (ROOT / "mods" / "DZDS" / "config.cpp").read_text()
    required = re.search(r"requiredAddons\[\]\s*=\s*\{(.*?)\}", cfg, re.S).group(1)
    path = ROOT / "mods" / "DZDS" / "Scripts" / "4_World" / "DZDS" / "DZDSWarZones.c"
    if wz and wz[0].get("enabled"):
        assert '"AIWarZones"' in required and path.exists()
        src = path.read_text()
        assert re.search(r"modded\s+class\s+AIWarZoneInstance\b", src)
        factions = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())["factions"]
        for spec in factions.values():          # every custom faction has a lowercase case label
            if spec.get("custom_faction"):
                c = spec["custom_faction"]
                assert f'case "{c.lower()}"' in src and f"new eAIFaction{c}()" in src
        assert "DZDSWorld.Floor(position)" in src
    else:
        assert "AIWarZones" not in required and not path.exists()
