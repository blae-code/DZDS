from pathlib import Path
import xml.etree.ElementTree as ET
from tools.export_preset import generate_html, generate_xml, load_active_mods

def test_load_active_mods():
    mods = load_active_mods()
    assert len(mods) > 0
    for m in mods:
        assert m.get("enabled", True) is True
        assert "id" in m
        assert "name" in m

def test_generate_html():
    mods = [
        {"name": "CF", "id": 1559212036, "tier": 1},
        {"name": "Dabs Framework", "id": 2545327648, "tier": 1},
    ]
    html = generate_html(mods, preset_name="Test Preset")
    assert "Created by DayZ Launcher" in html
    assert 'meta name="DayZ-Mods-Preset" content="Test Preset"' in html
    assert "https://steamcommunity.com/sharedfiles/filedetails/?id=1559212036" in html
    assert "https://steamcommunity.com/sharedfiles/filedetails/?id=2545327648" in html
    assert 'data-type="ModContainer"' in html
    assert 'data-type="DisplayName"' in html

def test_generate_xml():
    mods = [
        {"name": "CF", "id": 1559212036, "tier": 1},
        {"name": "Dabs Framework", "id": 2545327648, "tier": 1},
    ]
    xml_str = generate_xml(mods)
    root = ET.fromstring(xml_str)
    assert root.tag == "addons-presets"
    pub_ids = root.find("published-ids")
    assert pub_ids is not None
    ids = [elem.text for elem in pub_ids.findall("id")]
    assert ids == ["steam:1559212036", "steam:2545327648"]
