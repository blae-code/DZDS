#!/usr/bin/env python3
"""Inspect, manage, and simulate Settlement Survival Goals and Milestones.

Usage:
  tools/survival_goals.py [--status] [--plain] [--color]
  tools/survival_goals.py --contribute water_reserves 20 --by "Blae"
  tools/survival_goals.py --advance-turn 1
  tools/survival_goals.py --json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import ui  # noqa: E402
from gamemaster.survival_goals import get_manager  # noqa: E402


def format_progress_bar(pct: float, width: int = 24) -> str:
    filled = int(round((pct / 100.0) * width))
    filled = max(0, min(width, filled))
    empty = width - filled
    return "█" * filled + "░" * empty


def print_status(mgr, rich: bool = True) -> None:
    summary = mgr.get_summary()
    turn = summary["turn"]

    if rich:
        print(ui.banner(
            "SETTLEMENT SURVIVAL PROJECTS · QALAT-E LUT",
            subtitle=f"Frontier Settlers Compound Infrastructure  │  War Turn {turn}",
            right=f"{len(summary['projects'])} ACTIVE PROJECTS",
            width=96,
            enabled=True,
        ))

        rows = []
        for p in summary["projects"]:
            bar = format_progress_bar(p["percent"], 16)
            progress_str = f"{bar} {p['current']}/{p['target']} {p['unit']} ({p['percent']}%)"
            perk_desc = p["active_perk_text"]
            if len(perk_desc) > 42:
                perk_desc = perk_desc[:39] + "..."
            rows.append([
                ui.fg(p["name"], "bone", bold=True, enabled=True),
                p["category"],
                progress_str,
                ui.fg(perk_desc, "sand", enabled=True),
            ])

        print(ui.table(["PROJECT", "CATEGORY", "PROGRESS", "ACTIVE PERK EFFECT"], rows, title="SETTLEMENT INFRASTRUCTURE PROJECTS", enabled=True))

        m_rows = []
        for m in summary["personal_milestones"]:
            m_rows.append([
                ui.fg(m["title"], "cyan", bold=True, enabled=True),
                m["category"],
                m["criterion"],
                ui.fg(m["reward"], "green", enabled=True),
            ])
        print(ui.table(["MILESTONE", "CATEGORY", "CRITERION", "SURVIVAL REWARD"], m_rows, title="PERSISTENT SURVIVAL MILESTONES", enabled=True))

        if summary["recent_activity"]:
            print(f"\n{ui.fg('RECENT SETTLEMENT ACTIVITY:', 'sand', bold=True, enabled=True)}")
            for a in summary["recent_activity"][:5]:
                print(f"  • {ui.fg(a['timestamp'][:19].replace('T', ' '), 'muted', enabled=True)}: {a['text']}")
            print()
    else:
        print(f"=== Settlement Survival Projects (Turn {turn}) ===")
        for p in summary["projects"]:
            print(f"[{p['category']}] {p['name']}: {p['current']}/{p['target']} {p['unit']} ({p['percent']}%)")
            print(f"  Active Perk: {p['active_perk_text']}")
        print("\n=== Personal Survival Milestones ===")
        for m in summary["personal_milestones"]:
            print(f"  {m['title']} ({m['category']}): {m['criterion']} -> {m['reward']}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true", help="display live survival projects status")
    ap.add_argument("--contribute", nargs=2, metavar=("PROJECT", "AMOUNT"), help="record a contribution to a project")
    ap.add_argument("--by", default="Survivor", help="contributor name for the log")
    ap.add_argument("--advance-turn", type=int, help="simulate turn effects for turn N")
    ap.add_argument("--json", action="store_true", help="output status in JSON format")
    ap.add_argument("--color", action="store_true", help="force rich ANSI formatting")
    ap.add_argument("--plain", action="store_true", help="force plain text formatting")
    a = ap.parse_args()

    mgr = get_manager()

    if a.contribute:
        pid, amt_str = a.contribute
        try:
            amt = float(amt_str)
        except ValueError:
            print(f"Error: invalid amount {amt_str}", file=sys.stderr)
            return 1
        res = mgr.record_contribution(pid, amt, contributor=a.by)
        print(f"Recorded contribution of {amt} to {pid}. Current: {res['current']}/{res['target']}")
        return 0

    if a.advance_turn is not None:
        mgr.advance_turn(a.advance_turn)
        print(f"Advanced survival goals to turn {a.advance_turn}.")
        return 0

    if a.json:
        print(json.dumps(mgr.get_summary(), indent=2))
        return 0

    rich = True if a.color else False if a.plain else ui.use_color()
    print_status(mgr, rich=rich)
    return 0


if __name__ == "__main__":
    sys.exit(main())
