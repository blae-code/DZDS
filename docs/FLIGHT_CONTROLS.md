# HOSAS Helicopter Controls

Client-side setup notes for left/right VKB Gladiator NXT sticks. The goal is predictable
transport flight and controlled landings, not maximum agility.

## 1. Verified input state

On this CachyOS machine (2026-10-23), Linux enumerates the right and left NXT separately as
`/dev/input/js0` and `/dev/input/js1`; each reports 10 axes and 30 buttons. DayZ and the enabled
helicopter mods are installed. The active DayZ user preset currently binds aircraft controls to
keyboard and X1 gamepad inputs, but contains no VKB joystick-axis bindings.

The existing action bindings are:

- **RedFalcon:** cyclic is `W/S/A/D` plus the X1 left stick; pedals are `Q/E` plus X1 right-stick
  directions; collective is `Left Shift/Z`, mouse wheel, or X1 triggers.
- **Expansion:** cyclic is `W/S/A/D` plus the X1 left stick; anti-torque is `Q/E` plus X1
  right-stick directions; collective is `Left Shift/Z` or X1 triggers.
- The Expansion `CollectiveAnalogueUp` and `CollectiveAnalogueDown` actions are currently
  unbound in the preset.

This confirms the game action names and keyboard/gamepad fallback, but does **not** confirm
direct analog HOSAS support. A stick appearing in Linux is not proof that DayZ or a mod accepts
its raw axes. No game, Steam Input, or VKB firmware settings have been changed.

## 2. Intended HOSAS layout (only if the game accepts raw axes)

Use this as the desired layout only when the active flight model accepts analog axes:

| Stick / control | Suggested helicopter function | Notes |
|---|---|---|
| Right stick X | Roll / cyclic left-right | Keep the direction intuitive and consistent in the in-game axis test. |
| Right stick Y | Pitch / cyclic forward-back | Verify which physical direction makes the nose pitch down; invert only if needed. |
| Left stick twist | Yaw / anti-torque | Use this as the rudder axis if the selected flight model exposes one. |
| Left stick Y | Collective up/down | Use if no suitable non-centering axis is available. A spring-centered stick makes its physical center the middle of the collective range. |
| Available analog throttle/slider | Collective, if supported | Prefer this over a spring-centered axis when the game exposes and accepts it. Do not bind both controls to collective. |
| Unused axes | Unassigned | Avoid duplicate bindings and unintended camera or vehicle inputs. |

Use the helicopter-specific axis/action names actually shown by the active mod and game.
Do not assume RedFalcon and Expansion expose identical controls. Keep engine start/stop,
lights, view, and emergency/exit actions on accessible keyboard or button bindings rather
than consuming another flight axis.

If the Controls menu does not detect an NXT axis directly, do not add guessed `js0`/`js1`
bindings to the DayZ preset. Steam Input or another remapper may translate a stick into the
existing keyboard/gamepad actions, but keyboard emulation is digital and is not equivalent to
an analog axis. Do not use repeated key output for cyclic or collective until it has been
tested safely; it can produce abrupt, sustained control input.

## 3. Configure only after confirming axis support

1. Back up the active DayZ user preset before changing any in-game bindings.
2. In DayZ's Controls menu, inspect the RedFalcon and Expansion helicopter sections separately.
   Try binding one axis, then confirm the on-screen input responds through center and both
   directions. Cancel without saving if the axis is not detected.
3. If the game accepts raw axes, keep left/right sticks separate, calibrate each NXT in its
   supported VKB utility, use a linear response, and start with the smallest deadzone that
   removes center noise. Adjust only one axis at a time.
4. If using Steam Input or another remapper, first verify that its output type is accepted by
   DayZ. Check for duplicate input and test whether the output is analog or digital before
   flying; do not layer a Steam Input curve over a second game-side curve.

## 4. Validate each flight model separately

Use a safe, open area with a serviceable helicopter. Test one model at a time.

1. With the engine off, verify each mapped axis separately: neutral center, direction, full
   travel, and whether the game responds proportionally or only as on/off.
2. Lift gently, establish a steady hover, make small corrections, then try a slow approach and
   touchdown. Do not use a remapped digital control for flight if it is too abrupt to land
   predictably.
3. Repeat for RedFalcon MH-6 and an Expansion helicopter. Record differences; do not assume
   one model's bindings or response carry over to the other.

Until these in-game checks pass, the sticks are detected by Linux but the DayZ HOSAS mapping
is **not yet configured or verified**. Flight-control settings are client-local and must not
be deployed as server configuration.
