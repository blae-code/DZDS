"""Loot is Nasdara's vanilla economy (Blae, 2026-10-15). Only arrival-car lifetimes change."""
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

import economy

TYPES = """<types>
  <type name="AKM"><nominal>10</nominal><lifetime>1</lifetime><restock>0</restock><min>5</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/><value name="Tier4"/></type>
  <type name="OffroadHatchback"><nominal>0</nominal><lifetime>3</lifetime><restock>1800</restock><min>0</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/></type>
</types>"""
DAY = 86400


def cfg():
    return yaml.safe_load(economy.PRESET.read_text())


def test_preset_has_no_phase_or_scaling_keys():
    c = cfg()
    for k in ("phases", "campaign_start", "expected_players", "population_brackets",
              "protected_categories", "war", "hoarding"):
        assert k not in c, k


def mission(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "snafu").mkdir()
    (tmp_path / "db" / "types.xml").write_text(TYPES)
    (tmp_path / "db" / "globals.xml").write_text('<variables><var name="X" type="0" value="1"/></variables>')
    (tmp_path / "snafu" / "types.xml").write_text(TYPES)
    (tmp_path / "cfgeconomycore.xml").write_text(
        '<economycore><ce folder="snafu"><file name="types.xml" type="types"/></ce></economycore>')
    return tmp_path


def run(m):
    subprocess.run([sys.executable, str(economy.ROOT / "tools" / "economy.py"), "--mission", str(m)],
                   check=True, capture_output=True)


def test_output_equals_vanilla_except_arrival_lifetime(tmp_path):
    m = mission(tmp_path)
    run(m)
    out = {t.get("name"): t for t in ET.parse(m / "db" / "types.xml").getroot().findall("type")}
    assert out["AKM"].find("nominal").text == "10" and out["AKM"].find("min").text == "5"
    assert out["AKM"].find("flags").get("count_in_hoarder") == "0"
    assert int(out["OffroadHatchback"].find("lifetime").text) >= 7 * DAY


def test_rerun_is_identical_and_modded_types_untouched(tmp_path):
    m = mission(tmp_path)
    run(m)
    first = (m / "db" / "types.xml").read_text()
    run(m)
    assert (m / "db" / "types.xml").read_text() == first
    akm = ET.parse(m / "snafu" / "types.xml").getroot().find("type[@name='AKM']")
    assert akm.find("nominal").text == "10"


def test_lifetime_override_touches_only_named_types():
    root = ET.fromstring(TYPES)
    n = economy.apply_lifetimes(root, {"OffroadHatchback": 3888000, "NotInThisFile": 5})
    assert n == 1
    assert root.find("type[@name='AKM']/lifetime").text == "1"


def test_every_arrival_vehicle_gets_a_lifetime_override():
    arrivals = yaml.safe_load((economy.ROOT / "presets" / "arrivals.yaml").read_text())
    over = economy.lifetime_overrides(cfg())
    for v in arrivals["vehicles"]:
        assert over.get(v["class"], 0) >= 7 * DAY, v["class"]


def test_no_vanilla_loot_boosts_in_custom_types():
    t = yaml.safe_load((economy.ROOT / "presets" / "types_dzds.yaml").read_text())
    assert t["items"] == []
