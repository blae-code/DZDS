"""War ledger: player actions change control, strength, standing and diplomacy."""
import datetime as dt

import diplomacy
import patrol_gen
import yaml
from gamemaster.adm import parse_line
from gamemaster.ledger import WarLedger

T0 = dt.datetime(2026, 11, 1, 12, 0)
LOCS = yaml.safe_load((patrol_gen.ROOT / "maps" / "chernarusplus.yaml").read_text())["locations"]


def at(site):
    x, z = LOCS[site]
    return (x + 20, z - 15)


def fresh():
    return WarLedger.new("chernarusplus")


def test_starts_from_initial_control():
    led = fresh()
    assert led.s.control["Gorka"] == "Jackals"
    assert led.s.control["Stary Sobor"] == "contested"
    assert led.s.strength["Rust"] == 60


def test_players_liberate_a_site_for_the_settlers():
    led = fresh()
    for _ in range(9):
        led.record_death("DZDSJackals", "Players", at("Gorka"))
    events = led.turn(now=T0)
    assert led.s.control["Gorka"] == "Settlers"
    assert any("Gorka" in e for e in events)
    assert led.s.strength["Jackals"] < 60 + 3          # losses outweigh regen


def test_interim_engine_names_count_too():
    led = fresh()
    led.record_death("Raiders", "Players", at("Gorka"))   # interim Jackals
    assert led.s.player_kills == {"Jackals": 1}


def test_killing_the_un_triggers_lockdown_and_pleases_their_enemies():
    led = fresh()
    for _ in range(8):
        led.record_death("DZDSPeacekeepers", "Players", at("Balota Airfield"))
    events = led.turn(now=T0)
    assert led.s.standing["Peacekeepers"] < -30
    assert led.s.standing["Jackals"] > -60                # enemy of my enemy
    assert any("lockdown" in e for e in events)
    assert {"from": "Settlers", "to": "Peacekeepers", "stance": "hostile"}.items() <= led.s.auto_diplomacy[0].items()
    factions = yaml.safe_load((patrol_gen.ROOT / "presets" / "factions.yaml").read_text())["factions"]
    out = diplomacy.compile_overrides({"overrides": led.s.auto_diplomacy}, factions, T0.date())
    assert out == [{"From": "DZDSSettlers", "To": "DZDSPeacekeepers", "Friendly": False}]


def test_lockdown_expires():
    led = fresh()
    for _ in range(8):
        led.record_death("DZDSPeacekeepers", "Players", at("Balota Airfield"))
    led.turn(now=T0)
    led.turn(now=T0 + dt.timedelta(days=8), force=True)
    assert led.s.auto_diplomacy == []


def test_ai_vs_ai_fighting_moves_the_front():
    led = fresh()
    for _ in range(10):
        led.record_death("DZDSRust", "DZDSKarkas", at("Topolka Dam"))
    led.turn(now=T0)
    assert led.s.control["Topolka Dam"] == "Karkas"


def test_turn_guard_and_determinism():
    a, b = fresh(), fresh()
    ea = a.turn(now=T0)
    eb = b.turn(now=T0)
    assert ea == eb and a.s.control == b.s.control           # seeded by turn number
    assert a.turn(now=T0 + dt.timedelta(minutes=30)) == []   # guard: no double advance
    assert a.s.turn == 1


def test_claimed_settlement_gets_settler_patrols_and_never_falls_offscreen():
    led = fresh()
    led.claim("Host's Homestead", [5200.0, 8600.0], ["inland_town"])
    for i in range(30):
        led.turn(now=T0 + dt.timedelta(hours=3 * i))
    assert led.s.control["Host's Homestead"] == "Settlers"
    names = [p["Name"] for p in patrol_gen.generate("chernarusplus", control=led.holders(),
                                                     locs=led.locations())]
    assert "Settlers farm_watch @ Host's Homestead" in names


def test_adm_line_feeds_the_ledger():
    line = ('14:10:02 | AI "Hunter" (DEAD) (group=3:"Ridge" faction="DZDSKarkas" '
            f'pos=<{at("Altar")[0]}, 300.0, {at("Altar")[1]}>) killed by Player "Host" (id=x= pos=<0, 0, 0>) with Mosin')
    ev = parse_line(line)
    led = fresh()
    killer = ev.by_faction or ("Players" if ev.by and ev.by.startswith("Player") else None)
    led.record_death(ev.faction, killer, ev.pos)
    assert led.s.player_kills == {"Karkas": 1}
    assert led.s.pressure["Altar"] == {"Settlers": 1}


def test_named_deeds_in_liberation_report():
    led = fresh()
    for i in range(9):
        led.record_death("DZDSJackals", "Players", at("Gorka"), killer_name="Host" if i < 6 else "Buddy")
    events = led.turn(now=T0)
    assert any(e.startswith("Host's militia drove the defenders out of Gorka") for e in events)
    assert led.s.deeds == {}  # reset each turn


def test_at_most_one_war_party_and_only_with_chance():
    led = fresh()
    led.rules["war_party"]["chance"] = 1.0
    led.turn(now=T0)
    assert led.s.war_party is not None
    assert led.s.war_party["kind"] in {"raid", "offensive", "convoy"}
    led.rules["war_party"]["chance"] = 0.0
    led.turn(now=T0 + dt.timedelta(hours=3))
    assert led.s.war_party is None


def test_offensive_heads_for_a_contested_site_the_faction_could_hold():
    led = fresh()
    for c in led.war_party_candidates():
        if c["kind"] == "offensive":
            assert led.s.control[c["target"]] == "contested"
            assert led.s.control[c["origin"]] == c["faction"]


def test_strong_hostile_faction_can_raid_a_settlement():
    led = fresh()
    led.claim("Host's Homestead", [5200.0, 8600.0], ["inland_town"])
    led.s.strength["Jackals"] = 90
    raids = [c for c in led.war_party_candidates() if c["kind"] == "raid"]
    assert raids and all(r["target"] == "Host's Homestead" for r in raids)


def test_no_candidates_when_everyone_is_weak_and_nothing_contested():
    """Review focus 2: an empty turn is quiet, not an error."""
    led = fresh()
    for s in list(led.s.control):
        if led.s.control[s] == "contested":
            led.s.control[s] = "Rust"
    for f in led.s.strength:
        led.s.strength[f] = 0
    led.rules["war_party"]["chance"] = 1.0
    assert led.war_party_candidates() == []
    led.turn(now=T0)
    assert led.s.war_party is None


def test_convoy_only_on_a_recorded_route_between_two_held_sites():
    led = fresh()
    led.convoy_routes = [{"from": "Chernogorsk", "to": "Elektrozavodsk", "route": "rust_coast.json"}]
    convoys = [c for c in led.war_party_candidates() if c["kind"] == "convoy"]
    assert convoys == [{"kind": "convoy", "faction": "Rust", "origin": "Chernogorsk",
                        "target": "Elektrozavodsk", "route": "rust_coast.json", "size": [0, 0]}]
    led.s.control["Elektrozavodsk"] = "Jackals"
    assert not [c for c in led.war_party_candidates() if c["kind"] == "convoy"]


def test_ledger_from_another_map_is_refused(tmp_path):
    import json
    import pytest
    p = tmp_path / "war_ledger.json"
    p.write_text(json.dumps({"map": "chernarusplus", "raids": []}))
    with pytest.raises(SystemExit, match="reset"):
        WarLedger.load("nasdara", path=p)
    assert WarLedger.load("chernarusplus", path=p).s.war_party is None


# ---- the front never freezes (Task 12b, spec §4.1 / §5.2) ----------------------------------
def _contested(led):
    return sorted(s for s, h in led.s.control.items() if h == "contested")


def _advance(led, n):
    t = T0
    for _ in range(n):
        t += dt.timedelta(hours=3)
        led.turn(now=t, force=True)
        yield led


def test_front_never_freezes_on_nasdara():
    led = WarLedger.new("nasdara")
    led.rules["war_party"]["chance"] = 1.0
    for _ in _advance(led, 40):
        assert 1 <= len(_contested(led)) <= 2, (led.s.turn, _contested(led))


def test_front_caps_contested_sites():
    led = fresh()
    held = [s for s, h in sorted(led.s.control.items()) if h != "contested" and s not in led.s.extra_sites][:4]
    for s in held:
        led.s.control[s] = "contested"
    led.turn(now=T0, force=True)
    assert len(_contested(led)) <= 2


def test_front_never_contests_player_settlements():
    led = fresh()
    led.claim("Camp Hope", [7000.0, 7000.0], ["settlement"])
    for _ in _advance(led, 40):
        assert led.s.control["Camp Hope"] == "Settlers"


def test_front_is_deterministic():
    a, b = WarLedger.new("nasdara"), WarLedger.new("nasdara")
    for led in (a, b):
        for _ in _advance(led, 20):
            pass
    assert a.s.control == b.s.control
    assert a.s.history == b.s.history


def test_contested_sites_always_make_a_warzone():
    import zone_events
    led = WarLedger.new("nasdara")
    led.rules["war_party"]["chance"] = 1.0
    for _ in _advance(led, 40):
        for site in _contested(led):
            assert zone_events._teams(site, led.s.strength, led.fspec, led.site_roles(site)), (led.s.turn, site)
