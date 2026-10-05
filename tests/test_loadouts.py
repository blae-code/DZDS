import xml.etree.ElementTree as ET

import loadouts
import patrol_gen
import yaml

CFG = yaml.safe_load(loadouts.PRESET.read_text())


def test_every_patrol_loadout_name_is_compiled():
    compiled = loadouts.compile_all(CFG)
    for p in patrol_gen.generate("chernarusplus"):
        assert p["Loadout"] in compiled, p["Loadout"]


def test_loadout_structure_matches_expansion_prefab():
    data = loadouts.compile_all(CFG)["DZDS_Karkas_elder"]
    keys = {"ClassName", "Include", "Chance", "Quantity", "Health", "InventoryAttachments",
            "InventoryCargo", "ConstructionPartsBuilt", "Sets"}
    assert set(data) == keys
    slots = {s["SlotName"]: s for s in data["InventoryAttachments"]}
    assert [i["ClassName"] for i in slots["Body"]["Items"]] == ["GhillieSuit_Woodland"]
    assert all(set(i) == keys for s in data["InventoryAttachments"] for i in s["Items"])
    assert all(i["Quantity"].keys() == {"Min", "Max"} for i in data["InventoryCargo"])


def test_check_reports_unknown_classnames(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "types.xml").write_text('<types><type name="CZ527"/><type name="Apple"/></types>')
    known = loadouts.known_types(tmp_path)
    unknown = loadouts.classnames(CFG) - known
    assert "CZ527" not in unknown and "Mosin9130" in unknown
