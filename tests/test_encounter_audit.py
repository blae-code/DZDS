# tests/test_encounter_audit.py
import encounter_audit as ea
import zones

ZS = zones.build({"zone_radius_m": 400, "locations": {"Base": [1000.0, 1000.0]}}, {"Base": "Rust"})
LINES = [
    '10:00:00 | Player "Host" (id=a=) is connected',
    '10:05:00 | Player "Host" (id=a= pos=<5000.0, 10.0, 5000.0>)[HP: 80] hit by AI "J1" (group=1:"x" faction="DZDSJackals") into Torso',
    '10:06:00 | Player "Host" (id=a= pos=<5001.0, 10.0, 5001.0>)[HP: 60] hit by AI "J1" (group=1:"x" faction="DZDSJackals") into Torso',
    '10:30:00 | Player "Host" (id=a= pos=<1100.0, 10.0, 1000.0>)[HP: 70] hit by AI "R1" (group=2:"y" faction="DZDSRust") into Torso',
    '11:00:00 | Player "Host" (id=a=) has been disconnected',
    '12:00:00 | Player "Host" (id=a=) is connected',
]


def test_counts_sessions_and_groups_hits_into_encounters():
    out = ea.audit(LINES, ZS)
    assert out["Host"] == {"sessions": 2, "outside": 1, "inside": 1}


def test_ai_vs_ai_is_not_a_player_encounter():
    line = ('10:05:00 | AI "J1" (group=1:"x" faction="DZDSJackals" pos=<5000.0, 10.0, 5000.0>)'
            '[HP: 50] hit by AI "R1" (group=2:"y" faction="DZDSRust")')
    assert ea.audit([line], ZS) == {}
