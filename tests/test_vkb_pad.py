import xml.etree.ElementTree as ET

import vkb_pad


def test_centre_and_stops():
    assert vkb_pad.centred(2048, 4095) == 0.0
    assert vkb_pad.centred(0, 4095) == -1.0
    assert vkb_pad.centred(4095, 4095) == 1.0
    assert vkb_pad.centred(1024, 2047) == 0.0   # twist centre


def test_deadzone_and_expo():
    small = 2048 + int(0.03 * 2047)              # inside the 4 % deadzone
    assert vkb_pad.centred(small, 4095) == 0.0
    half = 2048 + 1024
    linear = vkb_pad.centred(half, 4095)
    curved = vkb_pad.centred(half, 4095, expo=0.3)
    assert 0 < curved < linear, "expo softens mid-travel"
    assert vkb_pad.centred(4095, 4095, expo=0.3) == 1.0, "full deflection stays full"


def test_stick_range():
    assert vkb_pad.to_stick(1.0) == 32767
    assert vkb_pad.to_stick(-1.0) == -32767
    assert vkb_pad.to_stick(2.0) == 32767


def test_collective_on_left_twist_in_raises_out_lowers_centre_holds():
    """Blae 2026-10-23: left twist is the throttle, twist in = up, twist out = down."""
    assert vkb_pad.collective(1024) == (0, 0)
    assert vkb_pad.collective(1024 + 60) == (0, 0), "inside the twist deadzone"
    assert vkb_pad.collective(2047) == (0, 255)   # twisted in (clockwise): raise
    assert vkb_pad.collective(0) == (255, 0)      # twisted out: lower
    assert vkb_pad.collective(2047, sign=-1) == (255, 0), "one flag swaps the direction"


def test_both_sticks_add_into_one_cyclic():
    """Right = pitch/roll, left = forward-back/strafe: a heli moves by tilting the rotor, so
    both feed the cyclic, summed and clamped to the stick range."""
    assert vkb_pad.cyclic(0.5, 0.0) == vkb_pad.to_stick(0.5)
    assert vkb_pad.cyclic(0.0, -0.5) == vkb_pad.to_stick(-0.5)
    assert vkb_pad.cyclic(0.4, 0.4) == vkb_pad.to_stick(0.8)
    assert vkb_pad.cyclic(1.0, 1.0) == 32767
    assert vkb_pad.cyclic(0.6, -0.6) == 0, "opposed inputs cancel"


PRESET = """<preset>
    <input name="UAMoveForward"><btn name="kW" /><btn name="x1LeftThumbUp" /></input>
    <input name="UAAimRight"><btn name="x1RightThumbRight" /></input>
    <input name="UAExpansionHeliCyclicForward"><btn name="kW" /><btn name="x1LeftThumbUp" /></input>
    <input name="UARFFSCyclicForward"><btn name="kW" /><btn name="ps4LeftThumbUp" /></input>
    <input name="UAExpansionHeliCollectiveUp"><btn name="kLShift" /><btn name="x1TriggerRight" /></input>
</preset>"""


def _btns(root, action):
    inp = next(i for i in root.findall("input") if i.get("name") == action)
    return [b.get("name") for b in inp.findall("btn")]


def test_rewrite_binds_helis_and_strips_other_xbox_bindings():
    root = ET.fromstring(PRESET)
    bound, stripped = vkb_pad.rewrite_preset(root)
    assert bound == len(vkb_pad.HELI_BINDINGS)
    assert stripped == 2, "walking and camera lose their Xbox bindings"
    assert _btns(root, "UAMoveForward") == ["kW"]
    assert _btns(root, "UAAimRight") == []
    assert _btns(root, "UAExpansionHeliCyclicForward") == ["kW", "x1LeftThumbUp"]
    assert _btns(root, "UARFFSCyclicForward") == ["kW", "ps4LeftThumbUp", "x1LeftThumbUp"]
    assert _btns(root, "UAExpansionHeliCollectiveUp") == ["kLShift", "x1TriggerRight"]
    assert _btns(root, "UAExpansionHeliAutoHover") == ["x1Y"], "missing actions are created"


def test_rewrite_is_idempotent():
    root = ET.fromstring(PRESET)
    vkb_pad.rewrite_preset(root)
    once = ET.tostring(root)
    vkb_pad.rewrite_preset(root)
    assert ET.tostring(root) == once


def test_every_binding_is_a_dayz_xbox_name():
    names = {"x1LeftThumbUp", "x1LeftThumbDown", "x1LeftThumbLeft", "x1LeftThumbRight",
             "x1RightThumbLeft", "x1RightThumbRight", "x1TriggerLeft", "x1TriggerRight",
             "x1A", "x1B", "x1X", "x1Y", "x1PadUp", "x1PadDown", "x1PadLeft", "x1PadRight"}
    for action, btns in vkb_pad.HELI_BINDINGS.items():
        assert set(btns) <= names, (action, btns)


def test_only_the_game_process_counts():
    assert vkb_pad.is_game(b"Z:\\home\\blae\\.local\\share\\Steam\\steamapps\\common\\DayZ\\DayZ_x64.exe\0-connect=1.2.3.4\0")
    assert not vkb_pad.is_game(b"/usr/bin/zsh\0-c\0pgrep -f DayZ_x64.exe\0")
    assert not vkb_pad.is_game(b"")


def test_free_look_speed_follows_deflection_and_keeps_fractions():
    carry = [0.0, 0.0]
    full = vkb_pad.look_step(1.0, 0.0, 0.01, carry)
    assert full == (int(vkb_pad.LOOK_SPEED * 0.01), 0)
    carry = [0.0, 0.0]
    slow = [vkb_pad.look_step(0.01, -0.01, 0.01, carry) for _ in range(100)]
    assert sum(d[0] for d in slow) > 0 and sum(d[1] for d in slow) < 0, "slow looks still move"


def test_mini_stick_centre_releases_the_view():
    assert vkb_pad.centred(512, vkb_pad.MINI_MAX, deadzone=vkb_pad.LOOK_DEADZONE) == 0.0
    assert vkb_pad.centred(512 + 60, vkb_pad.MINI_MAX, deadzone=vkb_pad.LOOK_DEADZONE) == 0.0
    assert vkb_pad.centred(1023, vkb_pad.MINI_MAX, deadzone=vkb_pad.LOOK_DEADZONE, expo=vkb_pad.LOOK_EXPO) == 1.0


def test_mini_stick_y_is_flipped_and_x_is_not():
    """Blae 2026-10-23: free-look Y was inverted. One flag sets which way is up."""
    full = vkb_pad.centred(1023, vkb_pad.MINI_MAX, deadzone=vkb_pad.LOOK_DEADZONE, expo=vkb_pad.LOOK_EXPO)
    assert vkb_pad.look_axis(1023, vertical=False) == full
    assert vkb_pad.look_axis(1023, vertical=True) == vkb_pad.LOOK_Y_SIGN * full
    assert vkb_pad.look_axis(1023, vertical=True, y_sign=1) == full
    assert vkb_pad.look_axis(512, vertical=True) == 0.0



class _Dev:
    closed = False

    def close(self):
        self.closed = True


class _Sel:
    def __init__(self):
        self.registered = []

    def register(self, dev, _events):
        self.registered.append(dev)


def test_a_stick_that_enumerates_late_is_picked_up_not_stuck_missing():
    """2026-10-26: the left stick alone was found at game start and the right was never
    retried, so no pad was ever made. Missing sticks must be added on later checks."""
    left, right = _Dev(), _Dev()
    sticks, sel = {}, _Sel()
    assert vkb_pad.add_missing_sticks(sticks, sel, find=lambda: {vkb_pad.LEFT: left}) == [vkb_pad.LEFT]
    both = {vkb_pad.LEFT: _Dev(), vkb_pad.RIGHT: right}
    assert vkb_pad.add_missing_sticks(sticks, sel, find=lambda: both) == [vkb_pad.RIGHT]
    assert sticks == {vkb_pad.LEFT: left, vkb_pad.RIGHT: right}
    assert sel.registered == [left, right]
    assert both[vkb_pad.LEFT].closed        # the duplicate handle is released, not leaked
    assert vkb_pad.add_missing_sticks(sticks, sel, find=lambda: both) == []
