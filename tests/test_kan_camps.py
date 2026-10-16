import pytest
import yaml

import kan_camps


def test_preset_roles_are_complete_and_unclamped():
    preset = yaml.safe_load(kan_camps.PRESET.read_text())
    for camp_id, roles in preset["camps"].items():
        kan_camps.check(camp_id, roles)


def test_no_camp_roamers():
    """Blae, 2026-10-12: KAN roamers do unrestricted world roaming; keep them off."""
    preset = yaml.safe_load(kan_camps.PRESET.read_text())
    assert all(r["Roamers"] == 0 for r in preset["camps"].values())


def test_apply_sets_full_override_and_is_idempotent():
    data = {"Camps": [{"Id": "C", "RoleOverrides": {}}]}
    preset = {"camps": {"C": dict.fromkeys(kan_camps.ROLES, 1) | {"Roamers": 0}}}
    assert kan_camps.apply(data, preset)
    assert data["Camps"][0]["RoleOverrides"]["Roamers"] == 0
    assert kan_camps.apply(data, preset) == []


@pytest.mark.parametrize("bad", [{"Attackers": 0}, {"Guards": 13}])
def test_values_the_mod_would_clamp_are_rejected(bad):
    roles = dict.fromkeys(kan_camps.ROLES, 1) | bad
    with pytest.raises(SystemExit):
        kan_camps.check("C", roles)


def test_unknown_camp_is_an_error():
    with pytest.raises(SystemExit):
        kan_camps.apply({"Camps": []}, {"camps": {"Nope": dict.fromkeys(kan_camps.ROLES, 1)}})


def test_camps_move_to_their_site_and_unlisted_camps_go():
    data = {"Camps": [{"Id": "A", "Position": [1.0, 0.0, 1.0], "RoleOverrides": {}},
                      {"Id": "B", "Position": [2.0, 0.0, 2.0], "RoleOverrides": {}}]}
    roles = {"Roamers": 0, "Looters": 2, "Builders": 1, "Guards": 3, "Attackers": 1, "Snipers": 0}
    preset = {"camps": {"A": {"site": "Settlement", **roles}}}
    changes = kan_camps.apply(data, preset, {"Settlement": [5000.0, 6000.0]})
    assert [c["Id"] for c in data["Camps"]] == ["A"]
    assert data["Camps"][0]["Position"] == [5015.0, 0.0, 6015.0]
    assert any("removed B" in c for c in changes)
