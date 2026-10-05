import datetime as dt
import xml.etree.ElementTree as ET

import yaml

import economy

TYPES = """<types>
  <type name="AKM"><nominal>10</nominal><lifetime>1</lifetime><restock>0</restock><min>5</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/><value name="Tier3"/><value name="Tier4"/></type>
  <type name="Apple"><nominal>40</nominal><lifetime>1</lifetime><restock>0</restock><min>20</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="food"/><value name="Tier4"/></type>
  <type name="Rag"><nominal>30</nominal><lifetime>1</lifetime><restock>0</restock><min>10</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="tools"/><value name="Tier1"/></type>
  <type name="HeliPart"><nominal>0</nominal><lifetime>1</lifetime><restock>0</restock><min>0</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="tools"/><value name="Tier4"/></type>
  <type name="NVG"><nominal>1</nominal><lifetime>1</lifetime><restock>0</restock><min>1</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="tools"/><value name="Tier4"/></type>
</types>"""


def cfg():
    return yaml.safe_load(economy.PRESET.read_text())


def run(phase_name):
    root = ET.fromstring(TYPES)
    c = cfg()
    economy.scale_types(root, c, economy.pick_phase(c, phase_name, dt.date.today()))
    return {t.get("name"): t for t in root.findall("type")}


def nominal(t):
    return int(t.find("nominal").text)


def test_landfall_scarcer_than_long_war_and_protected_food():
    landfall, long_war = run("landfall"), run("long_war")
    assert nominal(landfall["AKM"]) < nominal(long_war["AKM"]) < 10   # top tier Tier4 used
    assert nominal(landfall["Apple"]) == 40                             # food protected
    assert nominal(landfall["Rag"]) == 30                               # Tier1 untouched


def test_never_zeroes_and_skips_event_items():
    t = run("landfall")
    assert nominal(t["NVG"]) == 1 and int(t["NVG"].find("min").text) == 1
    assert nominal(t["HeliPart"]) == 0
    for x in t.values():
        assert int(x.find("min").text) <= nominal(x)


def test_hoarding_flags():
    t = run("long_war")
    assert t["AKM"].find("flags").get("count_in_hoarder") == "1"     # weapons category
    assert t["NVG"].find("flags").get("count_in_hoarder") == "1"     # Tier4
    assert t["Rag"].find("flags").get("count_in_hoarder") == "0"


def test_phase_by_date():
    c = cfg()
    start = dt.date.fromisoformat(str(c["campaign_start"]))
    assert economy.pick_phase(c, None, start)["name"] == "landfall"
    assert economy.pick_phase(c, None, start + dt.timedelta(weeks=8))["name"] == "escalation"
    assert economy.pick_phase(c, None, start + dt.timedelta(weeks=52))["name"] == "long_war"


def test_population_brackets_scale_up():
    c = cfg()
    c["expected_players"] = 40
    assert economy.population_factors(c)["Tier4"] == 1.0


def test_end_to_end_mission_with_modded_types(tmp_path):
    import subprocess
    import sys

    (tmp_path / "db").mkdir()
    (tmp_path / "snafu").mkdir()
    (tmp_path / "dzds").mkdir()
    (tmp_path / "db" / "types.xml").write_text(TYPES)
    (tmp_path / "snafu" / "types.xml").write_text(TYPES)
    (tmp_path / "dzds" / "types_dzds.xml").write_text(TYPES)
    (tmp_path / "cfgeconomycore.xml").write_text(
        '<economycore><ce folder="snafu"><file name="types.xml" type="types"/></ce>'
        '<ce folder="dzds"><file name="types_dzds.xml" type="types"/></ce></economycore>')
    cmd = [sys.executable, str(economy.ROOT / "tools" / "economy.py"), "--mission", str(tmp_path),
           "--phase", "landfall"]
    subprocess.run(cmd, check=True, capture_output=True)
    first = (tmp_path / "snafu" / "types.xml").read_text()
    subprocess.run(cmd, check=True, capture_output=True)           # rerun: no compounding
    assert (tmp_path / "snafu" / "types.xml").read_text() == first
    assert (tmp_path / "db" / "types.xml.vanilla").exists()
    assert (tmp_path / "snafu" / "types.xml.vanilla").exists()
    assert not (tmp_path / "dzds" / "types_dzds.xml.vanilla").exists()   # our items untouched
    akm = ET.fromstring(first).find("type[@name='AKM']")
    assert int(akm.find("nominal").text) < 10
