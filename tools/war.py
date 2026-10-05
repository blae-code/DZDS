#!/usr/bin/env python3
"""War ledger CLI (docs/WAR_LEDGER.md).

  tools/war.py status                     # who holds what, strength, standing, diplomacy
  tools/war.py turn [--force] [--date D]  # advance one war turn (run once per restart)
  tools/war.py claim "Host's Homestead" X Z [--roles inland_town] [--faction Settlers]
  tools/war.py reset                      # start over from initial_control
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=os.environ.get("GM_MAP", "chernarusplus"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    t = sub.add_parser("turn")
    t.add_argument("--force", action="store_true")
    t.add_argument("--date")
    c = sub.add_parser("claim")
    c.add_argument("name")
    c.add_argument("x", type=float)
    c.add_argument("z", type=float)
    c.add_argument("--roles", nargs="+", default=["inland_town"])
    c.add_argument("--faction")
    sub.add_parser("reset")
    a = ap.parse_args()

    if a.cmd == "reset":
        if STATE.exists():
            STATE.rename(STATE.with_suffix(".json.bak"))
        led = WarLedger.new(a.map)
        led.save()
        print("Ledger reset (previous saved as .bak)")
        print(led.report())
        return 0

    led = WarLedger.load(a.map)
    if a.cmd == "turn":
        today = dt.date.fromisoformat(a.date) if a.date else None
        events = led.turn(today=today, force=a.force)
        if not events and not a.force and led.s.last_turn_at:
            print(f"(turn {led.s.turn}: quiet, or already advanced within the last "
                  f"{led.rules['min_hours_between_turns']}h; --force to override)")
        for e in events:
            print(f"  * {e}")
    elif a.cmd == "claim":
        led.claim(a.name, [a.x, a.z], a.roles, a.faction)
        print(f"Claimed {a.name} at ({a.x:.0f}, {a.z:.0f}) for {led.s.control[a.name]}")
    led.save()
    print(led.report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
