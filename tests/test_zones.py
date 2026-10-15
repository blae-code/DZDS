# tests/test_zones.py
import zones

MAP = {"zone_radius_m": 400, "zone_radius": {"Big Base": 600},
       "locations": {"Big Base": [1000.0, 1000.0], "Well": [5000.0, 5000.0], "Town": [9000.0, 9000.0]}}
CONTROL = {"Big Base": "Peacekeepers", "Well": "contested"}


def test_build_states_and_radii():
    zs = zones.build(MAP, CONTROL)
    base, well = zones.zone_of("Big Base", zs), zones.zone_of("Well", zs)
    assert base.state == "stronghold" and base.holder == "Peacekeepers" and base.radius == 600
    assert well.state == "warzone" and well.radius == 400
    assert zones.zone_of("Town", zs) is None              # uncontrolled = open country


def test_inside_respects_radius_and_margin():
    zs = zones.build(MAP, CONTROL)
    assert zones.inside(1500.0, 1000.0, zs)               # 500 m < 600 m
    assert not zones.inside(5450.0, 5000.0, zs)           # 450 m > 400 m
    assert not zones.inside(1550.0, 1000.0, zs, margin=100.0)


def test_claimed_settlement_is_a_settler_zone():
    """Review focus 3: a player settlement in open country must be a legal zone."""
    locs = dict(MAP["locations"], **{"Host's Homestead": [7000.0, 2000.0]})
    zs = zones.build(MAP, dict(CONTROL, **{"Host's Homestead": "Settlers"}), locs)
    home = zones.zone_of("Host's Homestead", zs)
    assert home.state == "stronghold" and home.holder == "Settlers"
    assert zones.inside(7100.0, 2000.0, zs)


def test_control_from_initial():
    c = zones.control_from_initial({"Rust": ["Well"], "contested": ["Town"]})
    assert c == {"Well": "Rust", "Town": "contested"}
