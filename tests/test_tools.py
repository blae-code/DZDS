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
    assert data["Patrols"][1]["AccuracyMin"] == 0.25
    assert len(changes) == 3
