import math
import re

import pytest
import yaml

import active
import arrivals

INIT_C = active.mission_dir("nasdara") / "init.c"


@pytest.fixture(scope="module")
def built():
    cfg = yaml.safe_load(arrivals.PRESET.read_text())
    map_data = active.map_data("nasdara")
    return cfg, map_data, arrivals.build(cfg, map_data, arrivals.mission_dir(map_data))


def test_every_arrival_site_snaps_to_a_road_spot(built):
    cfg, map_data, out = built
    for name, (x, z) in map_data["arrival_sites"].items():
        pts = [p for p in out["ArrivalSites"] if p["Name"] == name]
        assert pts, name
        assert all(math.dist((p["X"], p["Z"]), (x, z)) <= cfg["snap_radius_m"] for p in pts), name


def test_no_road_respawn_inside_an_exclusion_zone(built):
    cfg, map_data, out = built
    zones = arrivals.exclusion_zones(cfg, map_data)
    assert zones
    for p in out["RoadPoints"]:
        assert not arrivals.excluded((p["X"], p["Z"]), zones), p


def test_arrival_sites_stay_out_of_war_locations():
    """Arrival villages must not leak into the war ledger, site markers or the GM."""
    map_data = active.map_data("nasdara")
    assert not set(map_data["arrival_sites"]) & set(map_data["locations"])


def test_unknown_classname_is_rejected(built):
    cfg, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    bad["gear"]["food"]["items"].append("NotARealItem")
    with pytest.raises(SystemExit, match="NotARealItem"):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_gear_weights_keep_category_shares(built):
    cfg, _, out = built
    total = sum(g["Weight"] for g in out["Gear"])
    assert total == pytest.approx(sum(c["weight"] for c in cfg["gear"].values()), rel=1e-3)


def test_json_keys_match_init_c_classes(built):
    """init.c deserialises arrivals.json into RefugeeArrival* classes; a renamed key would
    silently load as 0/null in game, so every emitted key must be a field there."""
    _, _, out = built
    src = INIT_C.read_text()
    body = re.search(r"class RefugeeArrivalConfig\s*\{(.*?)\n\}", src, re.S).group(1)
    fields = set(re.findall(r"\b(\w+);", body))
    assert set(out) <= fields, set(out) - fields
    point = re.search(r"class RefugeeArrivalPoint\s*\{(.*?)\n\}", src, re.S).group(1)
    assert set(out["RoadPoints"][0]) <= set(re.findall(r"\b(\w+);", point))


def test_init_main_is_vanilla():
    """Our block must not change Bohemia's main() (economy init, date reset)."""
    ours, vanilla = INIT_C.read_text(), (INIT_C.parent / "init.c.vanilla").read_text()
    grab = lambda s: re.search(r"void main\(\)\s*\{.*?\n\}", s, re.S).group(0)  # noqa: E731
    assert grab(ours) == grab(vanilla)


def test_start_kit_is_compiled(built):
    cfg, _, out = built
    assert out["RadioFrequencyIndex"] == cfg["radio"]["settler_net_index"] >= 0
    assert out["GiveRoadflare"] == 1


def test_init_c_gives_radio_battery_and_flare():
    src = INIT_C.read_text()
    kit = re.search(r"static void GiveStartKit\(.*?\n\t\}", src, re.S).group(0)
    for needle in ('"PersonalRadio"', '"Battery9V"', "SetFrequencyByIndex", '"Roadflare"'):
        assert needle in kit, needle
    assert "CreateInHands" in kit and "radio NOT created" in kit
    assert "SwitchOn" not in kit                       # ships switched OFF (spec §6.1)
    setup = re.search(r"override void StartingEquipSetup\(.*?\n\t\}", src, re.S).group(0)
    assert "GiveStartKit" in setup


def test_voice_quality_max():
    cfg = (arrivals.ROOT / "config" / "local_serverDZ.cfg").read_text()
    assert re.search(r"^vonCodecQuality\s*=\s*30;", cfg, re.M)
