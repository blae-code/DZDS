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


def test_collective_forward_raises_back_lowers_centre_holds():
    assert vkb_pad.collective(2048) == (0, 0)
    down, up = vkb_pad.collective(0)             # stick fully forward (low raw value)
    assert (down, up) == (0, 255)
    down, up = vkb_pad.collective(4095)
    assert (down, up) == (255, 0)


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
