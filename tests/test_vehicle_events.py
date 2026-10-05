import subprocess
import sys
import xml.etree.ElementTree as ET

import types_gen
import vehicle_events
import yaml
from gamemaster.ledger import WarLedger

CFG = yaml.safe_load((vehicle_events.ROOT / "presets" / "vehicle_events.yaml").read_text())


def test_events_follow_holders_and_skip_unverified():
    led = WarLedger.new("chernarusplus")
    events, spawns = vehicle_events.build(CFG, led)
    names = {e.get("name") for e in events.findall("event")}
    assert "DZDS_VehicleIndustry" in names and "DZDS_VehicleRaiders" not in names
    led.s.control["Topolka Dam"] = "Karkas"                       # Rust lose the dam
    _, spawns2 = vehicle_events.build(CFG, led)
    assert len(spawns2["DZDS_VehicleIndustry"]) == len(spawns["DZDS_VehicleIndustry"]) - 2


def test_mission_merge_is_idempotent_and_coexists_with_types(tmp_path):
    (tmp_path / "cfgeventspawns.xml").write_text('<eventposdef><event name="VehicleCivilianSedan">'
                                                 '<pos x="1" z="2" a="0"/></event></eventposdef>')
    (tmp_path / "cfgeconomycore.xml").write_text("<economycore>\n</economycore>\n")
    cmd = [sys.executable, str(vehicle_events.ROOT / "tools" / "vehicle_events.py"), "--mission", str(tmp_path)]
    subprocess.run(cmd, check=True, capture_output=True)
    first = (tmp_path / "cfgeventspawns.xml").read_text()
    subprocess.run(cmd, check=True, capture_output=True)
    assert (tmp_path / "cfgeventspawns.xml").read_text() == first
    root = ET.parse(tmp_path / "cfgeventspawns.xml").getroot()
    assert root.find("event[@name='VehicleCivilianSedan']") is not None          # vanilla kept
    assert len(root.findall("event[@name='DZDS_VehicleIndustry']")) == 1
    types_gen.register(tmp_path / "cfgeconomycore.xml")
    core = (tmp_path / "cfgeconomycore.xml").read_text()
    assert core.count('<ce folder="dzds">') == 1
    assert 'name="events_dzds.xml" type="events"' in core and 'name="types_dzds.xml" type="types"' in core
    ET.fromstring(core)
