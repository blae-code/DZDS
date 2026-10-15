"""Nasdara footprint (spec §4.1, §6.3): compact strongholds, a few warzones, arrival ring."""
import math

import yaml

import maps_check
from active import ROOT

MAP = yaml.safe_load((ROOT / "maps" / "nasdara.yaml").read_text())
ROLES = yaml.safe_load((ROOT / "maps" / "_roles.yaml").read_text())["roles"]
FACTIONS = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())
CONTROL = FACTIONS["initial_control"]["nasdara"]
TRADERS = yaml.safe_load((ROOT / "presets" / "traders.yaml").read_text())["traders"]


def radius(site):
    return float((MAP.get("zone_radius") or {}).get(site, MAP["zone_radius_m"]))


def test_map_passes_maps_check():
    assert maps_check.check(MAP, ROLES) == []


def test_zone_radius_default_is_400():
    assert MAP["zone_radius_m"] == 400


def test_compact_strongholds_and_one_or_two_warzones():
    held = [s for f, sites in CONTROL.items() if f != "contested" for s in sites]
    assert 6 <= len(held) <= 9
    assert 1 <= len(CONTROL.get("contested", [])) <= 2
    for f in ("Peacekeepers", "Rust", "Karkas", "Jackals", "Settlers"):
        assert 1 <= len(CONTROL.get(f, [])) <= 2, f


def test_zones_do_not_overlap():
    sites = [s for sites in CONTROL.values() for s in sites]
    for i, a in enumerate(sites):
        for b in sites[i + 1:]:
            d = math.dist(MAP["locations"][a], MAP["locations"][b])
            assert d >= radius(a) + radius(b), (a, b, round(d))


def test_arrival_sites_ring_the_settler_stronghold():
    settler = [MAP["locations"][s] for s in CONTROL["Settlers"]]
    others = [(MAP["locations"][s], radius(s)) for f, sites in CONTROL.items()
              if f != "Settlers" for s in sites]
    sites = MAP["arrival_sites"]
    assert 3 <= len(sites) <= 8
    for name, xy in sites.items():
        assert 3000 <= min(math.dist(xy, s) for s in settler) <= 5000, name
        for pos, r in others:
            assert math.dist(xy, pos) >= r + 500, (name, pos)
    assert not set(sites) & set(MAP["locations"])     # arrivals never feed the war ledger


def test_every_trader_prefers_a_site_its_faction_holds():
    for tid, t in TRADERS.items():
        site = (t.get("sites") or {}).get("nasdara")
        assert site, tid
        if t["faction"] != "none":
            assert site in CONTROL.get(t["faction"], []), (tid, site)
