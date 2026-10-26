#!/usr/bin/env python3
"""Write @DZDS profile files from presets/world.yaml and the war ledger.

  server/profiles/DZDS/settings.json  spawn allowlist + poll interval
  server/profiles/DZDS/markers.json   site markers by current holder (null classnames skipped)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

import active

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "server" / "profiles" / "DZDS"
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402


def settings(world: dict) -> dict:
    allowed = sorted({c for a in world["gm_actions"].values() for c in a.get("classnames") or []})
    return {"AllowedClassNames": allowed, "PollSeconds": int(world.get("poll_seconds", 10)),
            "ToleranceReputation": int(world.get("tolerance_reputation", 0))}


def markers(world: dict, led: WarLedger) -> list[dict]:
    m = world["markers"]
    dx, dz = m["offset"]
    locs = led.locations()
    out = []
    for site, holder in sorted(led.s.control.items()):
        cls = (m["by_holder"] or {}).get(holder)
        if not cls or site not in locs:
            continue
        x, z = locs[site][:2]
        out.append({"ClassName": cls, "X": float(x + dx), "Z": float(z + dz), "Yaw": 0.0})
    return out


def build_bulletin(led: WarLedger, traders: list[dict] | None = None,
                   quests: list[dict] | None = None, world: dict | None = None) -> dict:
    """Compile diegetic radio dispatches for $profile:DZDS/bulletin.json (DZDSBulletin.c)."""
    world = world or active.load_yaml("presets/world.yaml")
    bul_cfg = world.get("bulletin") or {}
    msgs: list[str] = list(led.recent_events(6))
    contested = sorted(s for s, h in led.s.control.items() if h == "contested")
    if contested:
        msgs.append(f"Heavy fighting reported around {', '.join(contested)}. Keep off the approaches.")
    if led.s.war_party:
        wp = led.s.war_party
        who = led._display(wp["faction"])
        msgs.append(f"Spotters report {who} ({wp['kind']}) moving from {wp['origin']} toward {wp['target']}.")
    if traders:
        open_t = [f"{t['display'].split(' (')[0]} at {t['site']}" for t in traders if t["status"] in ("open", "relocated") and t["site"]]
        if open_t:
            msgs.append("Active barter posts: " + "; ".join(open_t[:3]) + ".")

    # Dynamic cross-faction tactical intercepts
    for d in (getattr(led.s, "auto_diplomacy", []) or []):
        why = d.get("why")
        if why and why not in msgs:
            msgs.append(f"[DISPATCH] {d.get('from')} - {d.get('to')} directive: {why}.")

    if any(h == "Peacekeepers" for h in led.s.control.values()):
        msgs.append("[TF BLUE SHIELD] Green Zone status operational. Blue Helmets authorized for triage at Eastern Airfield.")
    if any(h == "Rust" for h in led.s.control.values()):
        msgs.append("[SYNDICATE NET] Hilltop Water Station pressure nominal. Unauthorized siphon attempts will draw lethal fire.")
    if any(h == "Jackals" for h in led.s.control.values()):
        msgs.append("[JACKAL CB INTERCEPT] Heavy trucks spotted on the northern bitumen. Keep the heavy iron hot.")
    if any(h == "Karkas" for h in led.s.control.values()):
        msgs.append("[KARKAS BEACON] High ridges are closed to outsiders. Turn back or draw fire from the heights.")

    if not msgs:
        msgs.append(f"Settler Net check-in (Turn {led.s.turn}): Stronghold perimeters holding steady.")
    return {
        "Turn": int(led.s.turn),
        "IntervalSeconds": int(bul_cfg.get("interval_seconds", 600)),
        "Frequency": str(bul_cfg.get("frequency", "87.8 MHz")),
        "Messages": msgs[:12],
    }


def main() -> int:
    world = active.load_yaml("presets/world.yaml")
    map_name = active.map_name()
    led = WarLedger.load_or_new(map_name)
    OUT.mkdir(parents=True, exist_ok=True)
    import front_plan
    traders = front_plan.plan_traders(led, front_plan.load("presets/traders.yaml"))
    s, mk, bul = settings(world), markers(world, led), build_bulletin(led, traders, world=world)
    (OUT / "settings.json").write_text(json.dumps(s, indent=4) + "\n")
    (OUT / "markers.json").write_text(json.dumps({"Markers": mk}, indent=4) + "\n")
    (OUT / "bulletin.json").write_text(json.dumps(bul, indent=4) + "\n")
    print(f"@DZDS profile: {len(s['AllowedClassNames'])} allowlisted classname(s), {len(mk)} marker(s), "
          f"{len(bul['Messages'])} radio bulletin(s)"
          + ("" if mk else " (marker classnames not chosen yet: presets/world.yaml)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
