# tests/test_dynamic_world.py
"""End-to-end conditions for the dynamic world (SPEC pillar 1, Badlands spec R4/R5, §4, §5.2).

Runs many war turns on Nasdara and checks, turn by turn, that the world MOVES (control flips,
the front never freezes, one war party at a time) while everything it generates stays inside
a zone, within calibration bounds, and deterministic.
"""
import datetime as dt

import active
import patrol_gen
import zone_events as ze
import zones
from gamemaster.ledger import WarLedger
from test_zone_placement import SKEL

TURNS = 40
T0 = dt.datetime(2026, 10, 16, 19, 0)


def simulate(turns=TURNS, chance=0.35):
    led = WarLedger.new("nasdara")
    led.rules["war_party"]["chance"] = chance
    snaps = []
    for i in range(turns):
        led.turn(now=T0 + dt.timedelta(hours=4 * i))
        snaps.append((dict(led.s.control), dict(led.s.strength), led.s.war_party))
    return led, snaps


def test_the_world_actually_moves():
    _, snaps = simulate()
    controls = [tuple(sorted(c.items())) for c, _, _ in snaps]
    assert len(set(controls)) > 3, "front line barely changed in 40 turns"
    flips = sum(1 for a, b in zip(snaps, snaps[1:]) for s in a[0] if a[0][s] != b[0][s])
    assert flips >= 5


def test_the_front_never_freezes_or_floods():
    _, snaps = simulate()
    for control, _, _ in snaps:
        contested = sum(1 for h in control.values() if h == "contested")
        assert 1 <= contested <= 2, control


def test_strength_stays_bounded_and_no_faction_is_wiped_off_the_map():
    led, snaps = simulate()
    for _, strength, _ in snaps:
        assert all(0 <= v <= 100 for v in strength.values()), strength
    # Every faction still holds ground or can recover; the war never ends in a single winner.
    held = {h for h in led.s.control.values() if h != "contested"}
    assert len(held) >= 3, held


def test_a_claimed_player_settlement_never_falls_off_screen():
    led = WarLedger.new("nasdara")
    x, z = led.locations()["Eastern Caravanserai"]
    led.claim("Host's Homestead", [x + 3000.0, z + 3000.0], ["inland_town"])
    for i in range(TURNS):
        led.turn(now=T0 + dt.timedelta(hours=4 * i))
        assert led.s.control["Host's Homestead"] == "Settlers", i


def test_one_war_party_at_a_time_even_at_certain_chance():
    led, snaps = simulate(chance=1.0)
    assert any(wp for _, _, wp in snaps), "war party never scheduled at chance 1.0"
    for _, _, wp in snaps:
        assert wp is None or isinstance(wp, dict)
        assert len(patrol_gen.war_party_patrols(wp, led.locations())) <= 1


def test_no_war_party_at_zero_chance():
    _, snaps = simulate(chance=0.0)
    assert all(wp is None for _, _, wp in snaps)


def test_every_generated_position_stays_in_a_zone_on_every_turn():
    led = WarLedger.new("nasdara")
    led.rules["war_party"]["chance"] = 1.0
    mp = active.map_data("nasdara")
    cfg = ze.load_cfg()
    for i in range(TURNS):
        led.turn(now=T0 + dt.timedelta(hours=4 * i))
        zs = zones.build(mp, led.s.control, led.locations())
        roles = {s: led.site_roles(s) for s in led.s.control}
        pts = []
        pts += ze.positions("airdrop", ze.airdrop(SKEL["airdrop"], zs, cfg))
        pts += ze.positions("heli", ze.heli(SKEL["heli"], zs, cfg))
        pts += ze.positions("crates", ze.crates(SKEL["crates"], zs, cfg))
        pts += ze.positions("warzones", ze.warzones(SKEL["warzones"], zs, led.s.strength,
                                                    led.fspec, roles, cfg))
        for p in patrol_gen.generate("nasdara", control=led.holders(), locs=led.locations()):
            pts += [(x, z) for x, _, z in p["Waypoints"]]
        outside = [pt for pt in pts if not zones.inside(*pt, zs)]
        assert outside == [], (i, outside[:3])


def test_generated_patrols_respect_calibration_bounds():
    led, _ = simulate(chance=1.0)
    for p in patrol_gen.generate("nasdara", control=led.holders(), locs=led.locations()):
        assert 0.20 <= p["AccuracyMin"] <= 0.35, p["Name"]
        assert 0.35 <= p["AccuracyMax"] <= 0.52, p["Name"]
        assert 1 <= p["NumberOfAI"] <= p["NumberOfAIMax"]


def test_garrisons_sit_at_held_sites_and_follow_the_front():
    led, snaps = simulate()
    patrols = patrol_gen.generate("nasdara", control=led.holders(), locs=led.locations())
    garrisons = [p for p in patrols if p["Persist"]]
    assert garrisons, "no persistent garrison patrols generated"
    held = {s for s, h in led.s.control.items() if h != "contested"}
    for p in garrisons:
        assert p["Name"].split(" @ ", 1)[1] in held, p["Name"]
    # The garrison set changes as the front moves (the world shows the war).
    first = patrol_gen.generate("nasdara", control=WarLedger.new("nasdara").holders(),
                                locs=led.locations())
    assert {p["Name"] for p in first} != {p["Name"] for p in patrols}


def test_simulation_is_deterministic_per_turn_number():
    a, sa = simulate()
    b, sb = simulate()
    assert sa == sb
    assert a.s.history == b.s.history


def test_players_can_tip_the_war():
    base = WarLedger.new("nasdara")
    base.turn(now=T0)
    tipped = WarLedger.new("nasdara")
    site = "North Highway Pileup"
    assert tipped.s.control[site] == "Jackals"
    x, z = tipped.locations()[site]
    for _ in range(9):
        tipped.record_death("DZDSJackals", "Players", (x + 20, z - 15), "blae")
    events = tipped.turn(now=T0)
    assert tipped.s.control[site] == "Settlers", events
    assert base.s.control[site] != "Settlers"
    assert tipped.s.strength["Jackals"] < base.s.strength["Jackals"]
    assert any("blae" in e for e in events)
