import math
import re

import pytest
import yaml

import arrivals

INIT_C = arrivals.ROOT / "server" / "mpmissions" / "dayzOffline.chernarusplus" / "init.c"


@pytest.fixture(scope="module")
def built():
    cfg = yaml.safe_load(arrivals.PRESET.read_text())
    map_data = yaml.safe_load((arrivals.ROOT / "maps" / "chernarusplus.yaml").read_text())
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
    map_data = yaml.safe_load((arrivals.ROOT / "maps" / "chernarusplus.yaml").read_text())
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
