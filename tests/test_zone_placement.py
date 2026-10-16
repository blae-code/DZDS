# tests/test_zone_placement.py
"""Spec §4.4: every generated NPC/event position is inside a zone, except ONE war party."""
import pytest
import yaml

import active
import patrol_gen
import zone_events as ze
import zones
from gamemaster.ledger import WarLedger

ROOT = active.ROOT
SKEL = {
    "airdrop": {"Controls": {"Interval": 60, "Variance": 5}, "Messages": {"Mode": 3},
                "VPP_Map": {"IsActive": 1, "Is3DActive": 0, "ExportMap": 1}, "DropZones": []},
    "heli": {"CRASH_POSITIONS_LIST": []},
    "crates": [{"CrateLocations": []}],
    "warzones": {"WarZones": [{"zoneName": "x"}], "maxConcurrentZones": 3},
}


def world(turns: int):
    led = WarLedger.new("nasdara")
    led.rules["war_party"]["chance"] = 1.0
    import datetime as dt
    for i in range(turns):
        led.turn(now=dt.datetime(2026, 10, 16) + dt.timedelta(hours=3 * i))
    return led


def test_everything_is_inside_a_zone_except_one_war_party():
    for turns in (0, 1, 5, 12):
        led = world(turns)
        mp = active.map_data("nasdara")
        zs = zones.build(mp, led.s.control, led.locations())
        cfg = ze.load_cfg()
        roles = {s: led.site_roles(s) for s in led.s.control}
        pts = []
        pts += ze.positions("airdrop", ze.airdrop(SKEL["airdrop"], zs, cfg))
        pts += ze.positions("heli", ze.heli(SKEL["heli"], zs, cfg))
        pts += ze.positions("crates", ze.crates(SKEL["crates"], zs, cfg))
        pts += ze.positions("warzones", ze.warzones(SKEL["warzones"], zs, led.s.strength, led.fspec, roles, cfg))
        patrols = patrol_gen.generate("nasdara", control=led.holders(), locs=led.locations())
        for p in patrols:
            pts += [(x, z) for x, _, z in p["Waypoints"]]
        outside = [pt for pt in pts if not zones.inside(*pt, zs)]
        assert outside == [], (turns, outside[:5])
        wp = patrol_gen.war_party_patrols(led.s.war_party, led.locations())
        assert len(wp) <= 1


@pytest.mark.xfail(reason="Nasdara KAN camp Ids exist only after the first local boot (Task 19)", strict=True)
def test_kan_camps_sit_in_settler_zones():
    preset = yaml.safe_load((ROOT / "presets" / "kan_camps.yaml").read_text())
    mp = active.map_data("nasdara")
    control = zones.control_from_initial(yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())
                                         ["initial_control"]["nasdara"])
    zs = [z for z in zones.build(mp, control) if z.holder == "Settlers"]
    for cid, spec in preset["camps"].items():
        x, z = mp["locations"][spec["site"]]
        assert zones.inside(x + 15, z + 15, zs), cid
