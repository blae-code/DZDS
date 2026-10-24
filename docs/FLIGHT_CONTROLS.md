# HOSAS Helicopter Controls

Client-side setup notes for left/right VKB Gladiator NXT sticks. The goal is predictable
transport flight and controlled landings, not maximum agility.

## 1. Installed configuration

DayZ does not receive the VKB devices as raw axes. The local bridge in
[`tools/vkb_pad.py`](../tools/vkb_pad.py) reads the left and right sticks and exposes one
virtual Xbox 360/XInput controller through Linux `uinput`. Proton presents that controller to
DayZ, whose active user preset has the corresponding `x1` bindings for the RedFalcon and
Expansion helicopter actions.

On this CachyOS setup (2026-10-23), both physical sticks enumerate separately (10 axes and 30
buttons each). The `dzds-vkb-pad.service` user service is enabled and running. It waits for the
DayZ process, creates the virtual controller only while the game is running, and removes it
when the game exits. Its log confirmed both sticks were found and the virtual pad was exposed
on the last observed game launch. The game is currently closed, so no virtual pad is expected
to exist until DayZ starts.

## 2. Stick layout

The bridge applies center deadzones and a soft cyclic response curve, then maps controls as
follows:

| Physical control | Virtual Xbox control | Helicopter function |
|---|---|---|
| Right stick X/Y | Left thumbstick X/Y | Primary roll and pitch cyclic |
| Left stick X/Y | Added to left thumbstick X/Y | Extra cyclic input; both sticks combine into one cyclic, not independent translation axes |
| Right stick twist | Right thumbstick horizontal | Yaw / anti-torque |
| Left stick twist | Left/right triggers | Twist in raises collective; twist out lowers it; centered twist holds |
| Right hat | D-pad | Trim on Expansion; landing lights/HUD on RedFalcon |
| Right stick buttons 1–4 | A/B/X/Y | Expansion auto-hover/free-look use Y/X |
| Right analog mini-stick | Mouse movement while holding Left Alt, then Numpad 5 on release | Free-look (push up to look up). Releasing it taps Numpad 5, Expansion's "centre camera", because an Expansion heli otherwise leaves the view where you left it. `LOOK_Y_SIGN` flips the vertical. |

Engine start/stop, lights, view, and exit remain on their normal keyboard or in-game controls.
The bridge keeps the physical sticks available to other applications and only publishes the
virtual pad while DayZ runs.

## 3. Check the local setup

From the repository root:

```sh
systemctl --user status dzds-vkb-pad.service
/usr/bin/python3 tools/vkb_pad.py learn
```

The service should be `active`; `learn` prints raw events while you move each stick, hat, and
button. Stop `learn` with Ctrl-C. If the control mapping has changed, close DayZ first, then
run:

```sh
/usr/bin/python3 tools/vkb_pad.py bind
```

`bind` backs up the current DayZ preset before writing the helicopter X1 bindings. Do not run
it while DayZ is open, because the game may overwrite the preset on exit. Restart DayZ after
binding so the controller mapping is loaded.

## 4. Validate each flight model separately

Use a safe, open area with a serviceable helicopter. Test one model at a time.

1. Start DayZ and check the service log for `virtual pad up for` followed by both Gladiator
   sticks. If either is missing, stop and troubleshoot device access before flying.
2. With the engine off, move one control at a time. Check neutral center, direction, and full
   travel; confirm cyclic/yaw respond proportionally and collective increases/decreases
   smoothly. Use `learn` if the physical control does not match the expected one.
3. Lift gently, establish a steady hover, make small corrections, then try a slow approach and
   touchdown. Adjust only the bridge's deadzone/expo constants if the sticks drift or feel too
   sharp, and retest before changing another value.
4. Repeat for RedFalcon MH-6 and an Expansion helicopter. Record differences; do not assume
   one model's bindings or flight response carry over to the other.

This is a client-local setup. Do not deploy the bridge, virtual-device configuration, or DayZ
input preset to the game server.
