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
