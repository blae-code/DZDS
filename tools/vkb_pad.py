#!/usr/bin/env python3
"""Fly DayZ helicopters with VKB Gladiator NXT sticks: present them as one virtual Xbox pad.

DayZ only reads keyboard, mouse and an Xbox (XInput) controller, so this maps the sticks onto
a uinput "Microsoft X-Box 360 pad" that Proton exposes as XInput. HOSAS layout (Blae,
2026-10-23: "Right stick is pitch, roll, and twist is yaw. Left stick is forward/backward and
side strafing with the twist being throttle, twist in being up and twist out being down"):

  right stick X/Y   -> left thumbstick     cyclic: roll / pitch     (Expansion + RedFalcon helis)
  left stick X/Y    -> left thumbstick     ALSO cyclic: strafe / forward-back. A helicopter has
                                           no separate translation input: it moves by tilting
                                           the rotor, so both sticks add into one cyclic.
  right stick twist -> right thumbstick X  pedals / yaw
  left stick twist  -> triggers            collective: twist in raises, out lowers, centre holds
  right hat         -> D-pad               trim set/release, landing lights, HUD
  right mini-stick  -> Left Alt + mouse    free look: deflect to look around (speed follows
                                           deflection, push up to look up), let go and Numpad 5
                                           (Expansion's centre camera) brings the view forward.
                                           A small virtual mouse/keyboard, because the pad's
                                           right stick is already the pedals.
  right buttons 1-4 -> A, B, X, Y          (Y auto-hover, X free look)

The pad exists only while DayZ_x64.exe runs, so Star Citizen (which reads the sticks
directly) never sees a second, gamepad copy of them. The sticks are not grabbed.

  vkb_pad.py run     # the loop (dzds-vkb-pad.service runs this)
  vkb_pad.py learn   # print stick events, to find which physical control is which
  vkb_pad.py bind    # write the helicopter bindings into DayZ's preset (DayZ must be closed)

Needs the system python-evdev (/usr/bin/python3), not the repo venv, and the input group.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

RIGHT = "Gladiator NXT R"
LEFT = "Gladiator NXT L"
GAME = "DayZ_x64.exe"
PRESET = (Path.home() / ".local/share/Steam/steamapps/compatdata/221100/pfx/drive_c/users/steamuser"
          / "Documents/DayZ/steamuser.dayz_preset_User.xml")

STICK_MAX = 4095      # NXT X/Y are 12-bit, centred
TWIST_MAX = 2047      # NXT twist (ABS_RZ) is 11-bit, centred
DEADZONE = 0.04       # fraction of half-travel ignored around the centre
CYCLIC_EXPO = 0.3     # 0 = linear; more = softer near the centre, full at the stops
TWIST_DEADZONE = 0.08 # twists drift more than the stick axes
# Left twist "in" (top of the grip turned toward the right, clockwise from above) raises the
# collective. VKB twist reads higher clockwise; if up and down come out swapped, flip this.
COLLECTIVE_TWIST_SIGN = 1
MINI_MAX = 1023       # NXT analog mini-stick (ABS_RX / ABS_RY) is 10-bit, centred
LOOK_DEADZONE = 0.15  # mini-sticks drift; inside this the view is released
LOOK_EXPO = 0.4
LOOK_SPEED = 1400.0   # mouse counts per second at full deflection (raise if looking is slow)
LOOK_HZ = 100
# Blae 2026-10-23: the view's Y was inverted. Flip back to 1 if up and down come out swapped.
LOOK_Y_SIGN = -1
# Expansion helicopters keep free look on whenever mouse flight is off (and Left Alt only
# toggles it when mouse flight is on), so letting go of the mouse leaves the view where it is.
# UAExpansionVehicleCenterCamera (Numpad 5 by default) smoothly re-centres it: tapped on release.
CENTRE_KEY = "KEY_KP5"
CENTRE_HOLD = 0.05    # seconds the centre key is held
PAD_MAX = 32767
TRIGGER_MAX = 255

# Right-stick buttons (evdev codes; BTN_TRIGGER=288 upward) -> Xbox buttons. `learn` shows codes.
BUTTONS = {288: "BTN_A", 289: "BTN_B", 290: "BTN_X", 291: "BTN_Y"}

# DayZ preset bindings for the virtual pad, per action (keyboard/mouse bindings are kept).
HELI_BINDINGS = {
    "UAExpansionHeliCyclicForward": ["x1LeftThumbUp"],
    "UAExpansionHeliCyclicBackward": ["x1LeftThumbDown"],
    "UAExpansionHeliCyclicLeft": ["x1LeftThumbLeft"],
    "UAExpansionHeliCyclicRight": ["x1LeftThumbRight"],
    "UAExpansionHeliAntiTorqueLeft": ["x1RightThumbLeft"],
    "UAExpansionHeliAntiTorqueRight": ["x1RightThumbRight"],
    "UAExpansionHeliCollectiveUp": ["x1TriggerRight"],
    "UAExpansionHeliCollectiveDown": ["x1TriggerLeft"],
    "UAExpansionHeliAutoHover": ["x1Y"],
    "UAExpansionHeliFreeLook": ["x1X"],
    "UAExpansionHeliTrimSet": ["x1PadLeft"],
    "UAExpansionHeliTrimRelease": ["x1PadRight"],
    "UARFFSCyclicForward": ["x1LeftThumbUp"],
    "UARFFSCyclicBack": ["x1LeftThumbDown"],
    "UARFFSCyclicLeft": ["x1LeftThumbLeft"],
    "UARFFSCyclicRight": ["x1LeftThumbRight"],
    "UARFFSPedalLeft": ["x1RightThumbLeft"],
    "UARFFSPedalRight": ["x1RightThumbRight"],
    "UARFFSCollectiveUp": ["x1TriggerRight"],
    "UARFFSCollectiveDown": ["x1TriggerLeft"],
    "UARFFSLandingLights": ["x1PadUp"],
    "UARFFSToggleHUD": ["x1PadDown"],
}


# ---- mapping (pure, tested) ----------------------------------------------------------------

def centred(raw: int, top: int, deadzone: float = DEADZONE, expo: float = 0.0) -> float:
    """Raw 0..top axis -> -1..1 around the centre, with a deadzone and optional expo curve."""
    half = top / 2
    v = max(-1.0, min(1.0, (raw - half) / half))
    if abs(v) <= deadzone:
        return 0.0
    v = (abs(v) - deadzone) / (1 - deadzone) * (1 if v > 0 else -1)
    return (1 - expo) * v + expo * v ** 3


def to_stick(v: float) -> int:
    return int(round(max(-1.0, min(1.0, v)) * PAD_MAX))


def collective(raw_twist: int, sign: int = COLLECTIVE_TWIST_SIGN) -> tuple[int, int]:
    """Left twist -> (left trigger, right trigger): twist in raises the collective (RT), out
    lowers it (LT), centre holds (both helicopter systems read collective as a rate)."""
    v = sign * centred(raw_twist, TWIST_MAX, deadzone=TWIST_DEADZONE)
    up = int(round(max(0.0, v) * TRIGGER_MAX))
    down = int(round(max(0.0, -v) * TRIGGER_MAX))
    return down, up


def cyclic(right: float, left: float) -> int:
    """Both sticks' contribution on one cyclic axis (each -1..1, already curved), clamped."""
    return to_stick(right + left)


def look_axis(raw: int, vertical: bool, y_sign: int = LOOK_Y_SIGN) -> float:
    """Mini-stick axis -> view deflection (-1..1, curved); `y_sign` sets which way is up."""
    v = centred(raw, MINI_MAX, deadzone=LOOK_DEADZONE, expo=LOOK_EXPO)
    return y_sign * v if vertical else v


def look_step(x: float, y: float, dt: float, carry: list[float]) -> tuple[int, int]:
    """Mini-stick deflection (-1..1, curved) over `dt` seconds -> whole mouse counts, carrying
    the fraction in `carry` so slow looks don't stall at zero."""
    carry[0] += x * LOOK_SPEED * dt
    carry[1] += y * LOOK_SPEED * dt
    dx, dy = int(carry[0]), int(carry[1])
    carry[0] -= dx
    carry[1] -= dy
    return dx, dy


def rewrite_preset(root: ET.Element, bindings: dict[str, list[str]] = HELI_BINDINGS) -> tuple[int, int]:
    """Bind the helicopter actions to the virtual pad; drop every other x1 (Xbox) binding so
    the sticks never walk, steer a car or turn the camera. Returns (bound, stripped)."""
    stripped = 0
    seen = set()
    for inp in root.findall("input"):
        name = inp.get("name")
        for btn in list(inp.findall("btn")):
            if (btn.get("name") or "").startswith("x1"):
                inp.remove(btn)
                if name not in bindings:
                    stripped += 1
        if name in bindings:
            seen.add(name)
            for b in bindings[name]:
                ET.SubElement(inp, "btn", name=b)
    for name in bindings:
        if name not in seen:
            inp = ET.SubElement(root, "input", name=name)
            for b in bindings[name]:
                ET.SubElement(inp, "btn", name=b)
    return len(bindings), stripped


# ---- runtime ------------------------------------------------------------------------------

def is_game(cmdline: bytes) -> bool:
    """The process's PROGRAM is DayZ, not merely a command line that mentions it (a shell
    running `pgrep DayZ_x64.exe` would otherwise count). Proton passes a Windows path."""
    prog = cmdline.split(b"\0", 1)[0].decode("latin1").replace("\\", "/")
    return prog.lower().rsplit("/", 1)[-1] == GAME.lower()


def game_running() -> bool:
    for pid in os.listdir("/proc"):
        if pid.isdigit():
            try:
                if is_game(Path(f"/proc/{pid}/cmdline").read_bytes()):
                    return True
            except OSError:
                pass
    return False


def find_sticks():
    import evdev
    found = {}
    for path in evdev.list_devices():
        d = evdev.InputDevice(path)
        for key in (RIGHT, LEFT):
            if key in d.name and key not in found:
                found[key] = d
    return found


def make_pad():
    from evdev import AbsInfo, UInput, ecodes as e
    stick = AbsInfo(0, -32768, PAD_MAX, 16, 128, 0)
    trig = AbsInfo(0, 0, TRIGGER_MAX, 0, 0, 0)
    hat = AbsInfo(0, -1, 1, 0, 0, 0)
    caps = {
        e.EV_KEY: [e.BTN_A, e.BTN_B, e.BTN_X, e.BTN_Y, e.BTN_TL, e.BTN_TR, e.BTN_SELECT, e.BTN_START,
                   e.BTN_MODE, e.BTN_THUMBL, e.BTN_THUMBR],
        e.EV_ABS: [(e.ABS_X, stick), (e.ABS_Y, stick), (e.ABS_RX, stick), (e.ABS_RY, stick),
                   (e.ABS_Z, trig), (e.ABS_RZ, trig), (e.ABS_HAT0X, hat), (e.ABS_HAT0Y, hat)],
    }
    # The kernel xpad driver's identity, so SDL/Proton use their stock Xbox 360 mapping.
    return UInput(caps, name="Microsoft X-Box 360 pad", vendor=0x045E, product=0x028E,
                  version=0x110, bustype=e.BUS_USB)


def make_look():
    """The free-look mouse + Left Alt (DayZ's hold-to-look key in both helicopter systems)."""
    from evdev import UInput, ecodes as e
    caps = {e.EV_REL: [e.REL_X, e.REL_Y],
            e.EV_KEY: [e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.KEY_LEFTALT, e.ecodes[CENTRE_KEY]]}
    return UInput(caps, name="DZDS VKB free look")


def run() -> int:
    import selectors
    from evdev import ecodes as e
    pad = None
    sticks = {}
    cyc = {"rx": 0.0, "ry": 0.0, "lx": 0.0, "ly": 0.0}
    look = None
    view = [0.0, 0.0]     # mini-stick deflection, curved
    carry = [0.0, 0.0]
    alt = False
    centre_up = 0.0       # when to release the centre key (0 = not held)
    last_look = time.monotonic()
    sel = selectors.DefaultSelector()
    last_check = 0.0
    print("vkb_pad: waiting for", GAME, flush=True)
    while True:
        now = time.monotonic()
        if now - last_check >= 2:
            last_check = now
            running = game_running()
            if running and not sticks:
                sticks = find_sticks()
                for d in sticks.values():
                    sel.register(d, selectors.EVENT_READ)
                if RIGHT not in sticks:
                    print("vkb_pad: right stick not found", flush=True)
            if running and pad is None and RIGHT in sticks:
                pad = make_pad()
                look = make_look()
                print("vkb_pad: virtual pad up for", ", ".join(sticks), flush=True)
            if not running and pad is not None:
                pad.close()
                pad = None
                if alt or centre_up:
                    look.write(e.EV_KEY, e.KEY_LEFTALT, 0)
                    look.write(e.EV_KEY, e.ecodes[CENTRE_KEY], 0)
                    look.syn()
                    alt = False
                    centre_up = 0.0
                look.close()
                look = None
                for d in sticks.values():
                    sel.unregister(d)
                    d.close()
                sticks = {}
                print("vkb_pad: game closed, pad removed", flush=True)
        if not sticks:
            time.sleep(1)
            continue
        looking = view[0] != 0.0 or view[1] != 0.0
        for key, _ in sel.select(timeout=1 / LOOK_HZ if looking or centre_up else 0.5):
            dev = key.fileobj
            try:
                events = list(dev.read())
            except OSError:   # unplugged: rediscover on the next check
                for d in sticks.values():
                    try:
                        sel.unregister(d)
                    except (KeyError, ValueError):
                        pass
                sticks = {}
                break
            right = RIGHT in dev.name
            for ev in events:
                if pad is None:
                    continue
                if ev.type == e.EV_ABS and ev.code in (e.ABS_X, e.ABS_Y):
                    side = ("r" if right else "l") + ("x" if ev.code == e.ABS_X else "y")
                    cyc[side] = centred(ev.value, STICK_MAX, expo=CYCLIC_EXPO)
                    axis = side[1]
                    pad.write(e.EV_ABS, ev.code, cyclic(cyc["r" + axis], cyc["l" + axis]))
                elif ev.type == e.EV_ABS and right:
                    if ev.code == e.ABS_RZ:
                        pad.write(e.EV_ABS, e.ABS_RX, to_stick(centred(ev.value, TWIST_MAX, deadzone=TWIST_DEADZONE)))
                    elif ev.code in (e.ABS_HAT0X, e.ABS_HAT0Y):
                        pad.write(e.EV_ABS, ev.code, ev.value)
                    elif ev.code in (e.ABS_RX, e.ABS_RY):
                        view[0 if ev.code == e.ABS_RX else 1] = look_axis(ev.value, ev.code == e.ABS_RY)
                elif ev.type == e.EV_ABS and not right and ev.code == e.ABS_RZ:
                    down, up = collective(ev.value)
                    pad.write(e.EV_ABS, e.ABS_Z, down)
                    pad.write(e.EV_ABS, e.ABS_RZ, up)
                elif ev.type == e.EV_KEY and right and ev.code in BUTTONS:
                    pad.write(e.EV_KEY, e.ecodes[BUTTONS[ev.code]], ev.value)
                elif ev.type == e.EV_SYN:
                    pad.syn()
        # Free look: hold Left Alt while the mini-stick is deflected and turn the view.
        now = time.monotonic()
        if look is not None:
            looking = view[0] != 0.0 or view[1] != 0.0
            if looking and not alt:
                look.write(e.EV_KEY, e.KEY_LEFTALT, 1)
                alt = True
                carry = [0.0, 0.0]
            if looking:
                dx, dy = look_step(view[0], view[1], min(now - last_look, 0.05), carry)
                if dx:
                    look.write(e.EV_REL, e.REL_X, dx)
                if dy:
                    look.write(e.EV_REL, e.REL_Y, dy)
            if not looking and alt:
                look.write(e.EV_KEY, e.KEY_LEFTALT, 0)
                alt = False
                look.syn()
                # Held a few frames: a press and release in one frame can be missed.
                look.write(e.EV_KEY, e.ecodes[CENTRE_KEY], 1)
                centre_up = now + CENTRE_HOLD
            if centre_up and now >= centre_up:
                look.write(e.EV_KEY, e.ecodes[CENTRE_KEY], 0)
                centre_up = 0.0
            look.syn()
        last_look = now


def learn() -> int:
    from evdev import ecodes as e
    sticks = find_sticks()
    if not sticks:
        print("no Gladiator NXT found")
        return 1
    print("move a control; Ctrl-C to stop")
    import selectors
    sel = selectors.DefaultSelector()
    for d in sticks.values():
        sel.register(d, selectors.EVENT_READ)
    while True:
        for key, _ in sel.select():
            for ev in key.fileobj.read():
                if ev.type == e.EV_KEY:
                    print(f"{key.fileobj.name.strip()[-15:]}  button {ev.code} {'down' if ev.value else 'up'}")
                elif ev.type == e.EV_ABS:
                    name = e.ABS.get(ev.code, ev.code)
                    print(f"{key.fileobj.name.strip()[-15:]}  {name} = {ev.value}")


def bind(preset: Path = PRESET) -> int:
    if game_running():
        print("DayZ is running: it rewrites this file on exit. Quit DayZ, then run bind again.")
        return 1
    tree = ET.parse(preset)
    bound, stripped = rewrite_preset(tree.getroot())
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = preset.with_name(preset.name + f".bak-{stamp}")
    backup.write_bytes(preset.read_bytes())
    ET.indent(tree, space="    ")
    body = ET.tostring(tree.getroot(), encoding="unicode")
    preset.write_text('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n' + body + "\n", encoding="utf-8")
    print(f"bound {bound} helicopter action(s), removed {stripped} other Xbox binding(s); backup {backup.name}")
    return 0


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("command", choices=["run", "learn", "bind"])
    args = a.parse_args()
    return {"run": run, "learn": learn, "bind": bind}[args.command]()


if __name__ == "__main__":
    sys.exit(main())
