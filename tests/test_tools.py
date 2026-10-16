from pathlib import Path

import apply_ai_calibration as cal
import modstring


def test_mods_yaml_loads_and_core_first():
    mods = modstring.load_mods()
    client, _ = modstring.build_strings(mods)
    order = client.split(";")
    assert order[:3] == ["@CF", "@Dabs Framework", "@DayZ-Expansion-Core"]
    tiers = [m["tier"] for m in modstring.ordered(mods)]
    assert tiers == sorted(tiers)


def test_panel_fields_use_workshop_ids_in_load_order():
    mods = [
        {"name": "B", "folder": "@B Mod", "id": 2, "tier": 2, "side": "both"},
        {"name": "A", "folder": "@A", "id": 1, "tier": 1, "side": "both"},
        {"name": "S", "folder": "@S", "id": 3, "tier": 2, "side": "server"},
        {"name": "Off", "folder": "@Off", "id": 4, "tier": 1, "enabled": False},
        {"name": "Ours", "folder": "@DZDS", "id": 0, "tier": 2, "local": True},
    ]
    client, server, local = modstring.build_panel_fields(mods)
    assert client == "@1;@2;"
    assert server == "@3;"
    assert local == ["@DZDS"]


def test_panel_fields_real_list_has_no_capitals_or_spaces():
    client, server, _ = modstring.build_panel_fields(modstring.load_mods())
    for field in (client, server):
        assert field == field.lower() and " " not in field
        assert all(e.startswith("@") and e[1:].isdigit() for e in field.split(";") if e)


def test_find_bikeys(tmp_path: Path):
    (tmp_path / "Keys").mkdir()
    (tmp_path / "Keys" / "CF.bikey").write_text("k")
    assert [p.name for p in modstring.find_bikeys(tmp_path)] == ["CF.bikey"]


def test_calibration_bounds():
    assert cal.check_bounds({"AccuracyMin": 0.28, "AccuracyMax": 0.48, "ThreatDistanceLimit": 280}) == []
    assert cal.check_bounds({"AccuracyMin": 0.9})
    assert cal.check_bounds({"ThreatDistanceLimit": 1000})


def test_calibration_apply_nested():
    data = {"Groups": [{"AccuracyMin": 0.5, "Other": 1}], "AccuracyMax": 0.9}
    changes, seen = [], set()
    cal.apply(data, {"AccuracyMin": 0.28, "AccuracyMax": 0.48}, changes, seen)
    assert data == {"Groups": [{"AccuracyMin": 0.28, "Other": 1}], "AccuracyMax": 0.48}
    assert seen == {"AccuracyMin", "AccuracyMax"}


def test_shipped_preset_within_bounds():
    import yaml
    preset = yaml.safe_load(cal.PRESET.read_text())
    assert cal.check_bounds(preset["values"]) == []


def test_clamp_respects_sentinels_and_bounds():
    data = {"Patrols": [{"AccuracyMax": 0.95, "AccuracyMin": -1, "ThreatDistanceLimit": 800.0},
                        {"AccuracyMin": 0.1, "LogAIKilled": True}]}
    changes = []
    cal.clamp(data, changes)
    assert data["Patrols"][0] == {"AccuracyMax": 0.52, "AccuracyMin": -1, "ThreatDistanceLimit": 300.0}
    assert data["Patrols"][1]["AccuracyMin"] == 0.20   # per-patrol floor
    assert len(changes) == 3


def test_overlay_merge_only_existing_keys():
    import apply_overlays as ov
    data = {"MapData": {"displayPlayerPosition": True, "ignoreMapOwnership": False}, "Other": 1}
    changes, missing = ov.merge(data, {"MapData": {"displayPlayerPosition": False, "madeUp": 1}})
    assert data["MapData"]["displayPlayerPosition"] is False
    assert "madeUp" not in data["MapData"]
    assert changes == [("MapData.displayPlayerPosition", True, False)]
    assert missing == ["MapData.madeUp"]


def test_overlay_bool_keeps_int_type_of_real_file():
    # Expansion writes flags as 0/1; a YAML true/false must not turn them into JSON booleans
    import apply_overlays as ov
    data = {"ShowHardlineHUD": 1, "UseReputation": 0, "enabled": True}
    changes, _ = ov.merge(data, {"ShowHardlineHUD": False, "UseReputation": True, "enabled": False})
    assert data == {"ShowHardlineHUD": 0, "UseReputation": 1, "enabled": False}
    assert type(data["ShowHardlineHUD"]) is int and type(data["UseReputation"]) is int
    assert ov.merge(data, {"ShowHardlineHUD": False}) == ([], [])     # 0 == False: no-op


def test_overlay_requires_mod_gates_on_mods_yaml():
    # values naming @DZDS classes must not be written while @DZDS isn't loaded: Expansion
    # logs "Invalid faction name" on every connect and the setting does nothing
    import apply_overlays as ov
    mods = [{"folder": "@DZDS", "enabled": False}, {"folder": "@CF", "enabled": True}]
    assert ov.mod_enabled("@CF", mods) and not ov.mod_enabled("@DZDS", mods)
    assert not ov.mod_enabled("@Nope", mods)


def test_dzds_class_overlays_are_gated():
    import yaml
    import apply_overlays as ov
    for f in ov.OVERLAYS.glob("*.yaml"):
        o = yaml.safe_load(f.read_text())
        if "DZDS" in yaml.safe_dump(o.get("values") or {}):
            assert o.get("requires_mod") == "@DZDS", f


def test_overlay_remove_classnames_everywhere():
    import apply_overlays as ov
    data = {"Containers": [
        {"Container": "Box", "Loot": [
            {"Name": "SewingKit", "Attachments": ["ExpansionBoltCutters"], "Variants": []},
            {"Name": "ExpansionBoltCutters", "Attachments": [], "Variants": []},
            {"Name": "Rope", "Attachments": [], "Variants": [{"Name": "ExpansionPropaneTorch"}]},
        ]},
    ]}
    removed = ov.remove_classnames(data, {"ExpansionBoltCutters", "ExpansionPropaneTorch"})
    loot = data["Containers"][0]["Loot"]
    assert [e["Name"] for e in loot] == ["SewingKit", "Rope"]
    assert loot[0]["Attachments"] == [] and loot[1]["Variants"] == []
    assert sorted(removed) == ["ExpansionBoltCutters", "ExpansionBoltCutters", "ExpansionPropaneTorch"]
    assert data["Containers"][0]["Container"] == "Box"     # non-list values untouched


def test_overlay_glob_target_hits_every_match(tmp_path, monkeypatch):
    import apply_overlays as ov
    for n in ("Airdrop_A", "Airdrop_B", "ContaminatedArea_C"):
        (tmp_path / f"{n}.json").write_text('{"Enabled": 1}')
    monkeypatch.setattr(ov, "resolve", lambda root: tmp_path)
    assert [p.name for p in ov.targets({"root": "mission", "target": "Airdrop_*.json"})] == \
        ["Airdrop_A.json", "Airdrop_B.json"]


def test_overlay_presets_well_formed():
    import yaml
    import apply_overlays as ov
    for f in ov.OVERLAYS.glob("*.yaml"):
        o = yaml.safe_load(f.read_text())
        assert o["root"] in {"profiles", "mission"} and o["target"].endswith(".json"), f
        assert o.get("values") or o.get("remove_classnames"), f


def test_spec_estimate_scales_with_mod_size():
    import specs
    small, big = specs.estimate(11.7), specs.estimate(24.7)
    assert small["server_ram_gb"] < big["server_ram_gb"]
    assert big["server_ram_gb"] >= 12            # full list needs more than the spec's 8 GB
    assert small["client_disk_gb"] > specs.CLIENT_DAYZ_GB


def test_panel_file_matches_mods_yaml():
    """config/panel_additional_mods.txt is what Blae pastes into the panel's Additional Mods
    field (2026-10-16). It must equal the generated line exactly; regenerate with
    `make panel-mods` after any change to mods.yaml."""
    client, _, _ = modstring.build_panel_fields(modstring.load_mods())
    assert modstring.PANEL_FILE.read_text() == client, "stale: run `make panel-mods`"
    assert "\n" not in client
