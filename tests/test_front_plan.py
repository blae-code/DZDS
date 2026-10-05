import datetime as dt

import front_plan
from gamemaster.ledger import WarLedger

TRADERS = front_plan.load("presets/traders.yaml")
QUESTS = front_plan.load("presets/quests.yaml")


def status(led, tid):
    return next(t for t in front_plan.plan_traders(led, TRADERS) if t["trader"] == tid)


def test_traders_open_relocate_and_close_with_control():
    led = WarLedger.new("chernarusplus")
    assert status(led, "un_quartermaster") == {"trader": "un_quartermaster", "status": "open",
                                               "site": "Northwest Airfield",
                                               "display": TRADERS["traders"]["un_quartermaster"]["display"]}
    led.s.control["Northwest Airfield"] = "Jackals"
    st = status(led, "un_quartermaster")
    assert st["status"] == "relocated" and st["site"] == "Balota Airfield"
    for s in ("Balota Airfield", "Krasnostav"):
        led.s.control[s] = "Jackals"
    assert status(led, "un_quartermaster")["status"] == "closed"
    led.s.control["Topolka Dam"] = "Karkas"
    assert status(led, "rust_broker")["status"] == "closed"   # Rust hold no other water site


def test_quests_follow_the_front():
    led = WarLedger.new("chernarusplus")
    q = front_plan.plan_quests(led, QUESTS)
    sieges = {x["site"] for x in q if x["quest"] == "break_the_siege"}
    assert sieges == {"Krasnostav", "Severograd", "Stary Sobor"}
    assert {x["site"] for x in q if x["quest"] == "water_rights"} == {"Topolka Dam"}
    led.s.control["Gorka"] = "Settlers"                       # liberated
    q2 = front_plan.plan_quests(led, QUESTS)
    assert not any(x["quest"] == "clear_jackal_camp" for x in q2)


def test_standing_gate_and_raid_quest():
    led = WarLedger.new("chernarusplus")
    led.s.standing["Rust"] = -80
    assert not any(x["quest"] == "water_rights" for x in front_plan.plan_quests(led, QUESTS))
    led.claim("Host's Homestead", [5200.0, 8600.0], ["inland_town"])
    led.s.raids = [{"faction": "Jackals", "target": "Host's Homestead", "origin": "Gorka", "size": [4, 7]}]
    assert any(x["quest"] == "defend_homestead" and x["site"] == "Host's Homestead"
               for x in front_plan.plan_quests(led, QUESTS))
