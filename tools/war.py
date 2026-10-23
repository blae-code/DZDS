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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402
import active  # noqa: E402
import ui  # noqa: E402


def render_rich_report(led: WarLedger, events: list[str] | None = None, color: bool | None = None) -> str:
    out = [
        ui.banner(
            f"WAR LEDGER · {led.s.map.upper()}",
            subtitle=f"Last turn: {led.s.last_turn_at or 'initial state'}  │  Contested warzones: {sum(1 for h in led.s.control.values() if h == 'contested')}",
            right=f"TURN {led.s.turn}",
            width=96,
            enabled=color,
        )
    ]
    if events:
        ev_lines = [f"{ui.fg('★', 'coral', bold=True, enabled=color)} {e}" for e in events]
        out.append(ui.panel("\n".join(ev_lines), title=f"TURN {led.s.turn} DISPATCHES", border_color="coral", width=96, enabled=color))

    holders = led.holders()
    rows = []
    for f in (*ui.FACTION_ORDER, "contested"):
        sites = sorted(holders.get(f, []))
        if f == "contested":
            rows.append([
                ui.faction_tag("contested", "Contested Warzone", enabled=color),
                "—",
                "—",
                ", ".join(ui.fg(s, "contested", bold=True, enabled=color) for s in sites) or "—",
            ])
        else:
            rows.append([
                ui.faction_tag(f, led._display(f), enabled=color),
                ui.meter(led.s.strength.get(f, 0), 100, width=10, color=f, enabled=color),
                ui.standing_bar(led.s.standing.get(f, 0), width=12, enabled=color),
                ", ".join(sites) or "—",
            ])
    out.append(ui.table(
        ["FACTION / ZONE", "STRENGTH", "PLAYER STANDING", "CONTROLLED SITES"],
        rows,
        title="FRONT LINE & FACTION STANDING",
        enabled=color,
    ))
    extras = []
    if led.s.war_party:
        wp = led.s.war_party
        extras.append(f"{ui.badge('WAR PARTY', 'warn', enabled=color)} {wp['kind'].upper()} · "
                      f"{ui.faction_tag(wp['faction'], enabled=color)} moving {wp['origin']} → {wp['target']}")
    for d in led.s.auto_diplomacy:
        extras.append(f"{ui.badge('DIPLOMACY', 'cyan', enabled=color)} Until {d['until']}: "
                      f"{d['from']} → {d['to']} [{d['stance'].upper()}] ({d['why']})")
    if extras:
        out.append(ui.panel("\n".join(extras), title="ACTIVE MOVEMENTS & DIPLOMACY OVERRIDES", width=96, enabled=color))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=active.map_name())
    ap.add_argument("--color", action="store_true", help="force rich ANSI output")
    ap.add_argument("--plain", action="store_true", help="force plain text output")
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
    rich = True if a.color else False if a.plain else ui.use_color()

    if a.cmd == "reset":
        if STATE.exists():
            STATE.rename(STATE.with_suffix(".json.bak"))
        led = WarLedger.new(a.map)
        led.save()
        print("Ledger reset (previous saved as .bak)")
        print(render_rich_report(led, color=True) if rich else led.report())
        return 0

    led = WarLedger.load(a.map)
    events: list[str] = []
    if a.cmd == "turn":
        today = dt.date.fromisoformat(a.date) if a.date else None
        events = led.turn(today=today, force=a.force)
        if not events and not a.force and led.s.last_turn_at:
            print(f"(turn {led.s.turn}: quiet, or already advanced within the last "
                  f"{led.rules['min_hours_between_turns']}h; --force to override)")
        if not rich:
            for e in events:
                print(f"  * {e}")
    elif a.cmd == "claim":
        led.claim(a.name, [a.x, a.z], a.roles, a.faction)
        print(f"Claimed {a.name} at ({a.x:.0f}, {a.z:.0f}) for {led.s.control[a.name]}")
    led.save()
    print(render_rich_report(led, events=events, color=True) if rich else led.report())
    return 0


if __name__ == "__main__":
    sys.exit(main())
