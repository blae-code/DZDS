#!/usr/bin/env python3
"""CLI tool for inspecting and managing Qalat-e Lut hirable NPC companions.

Usage:
  tools/companions.py --status
  tools/companions.py --hire soran_scout --player "Blae"
  tools/companions.py --dismiss soran_scout
  tools/companions.py --validate
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from gamemaster.companions import get_manager, load_config


def print_status() -> int:
    mgr = get_manager()
    summary = mgr.get_summary()

    print("\n" + "=" * 80)
    print("  QALAT-E LUT COMPANION GARRISON & HIRABLE SPECIALISTS")
    print("=" * 80)
    print(f"Settlement: {summary['settlement'].get('name', 'Qalat-e Lut')} (HQ: {summary['settlement'].get('hq_coordinates')})")
    print(f"Available: {summary['available_count']} | On Expedition: {summary['hired_count']} | Squad Limit: {summary['max_squad_size']}")
    print("-" * 80)

    for c in summary["roster"]:
        status_str = f"[{c['status'].upper()}]"
        if c["status"] == "Hired":
            status_str += f" (with {c['hired_by']})"
        print(f"\n* {c['name']} - {c['title']} {status_str}")
        print(f"  Station:        {c['station']} @ {c['position']}")
        print(f"  Primary Weapon: {c['primary_weapon']}")
        print(f"  Loadout File:   {c['loadout']}.json")
        print(f"  Specialization: {c['specialization']}")
        print(f"  Voice Bark:     \"{c['bark']}\"")
        costs = ", ".join(f"{r['amount']}x {r['item']} ({r['desc']})" for r in c.get("retainer_cost", []))
        print(f"  Retainer Cost:  {costs}")
        print("  Role Perks:")
        for perk in c.get("role_perks", []):
            print(f"    - {perk}")

    print("\n" + "-" * 80)
    print("Recent Garrison Log:")
    for l in summary["hire_log"]:
        print(f"  [{l.get('timestamp', '')[:19]}] {l.get('text', '')}")
    print("=" * 80 + "\n")
    return 0


def validate_all() -> int:
    cfg = load_config()
    comps = cfg.get("companions", {})
    if not comps:
        print("FAIL: No companions defined in presets/companions.yaml", file=sys.stderr)
        return 1

    loadouts_dir = ROOT / "server" / "profiles" / "ExpansionMod" / "Loadouts"
    errors = 0

    for cid, spec in comps.items():
        loadout_file = loadouts_dir / f"{spec['loadout']}.json"
        if not loadout_file.exists():
            print(f"FAIL: Missing loadout file for {cid}: {loadout_file.name}", file=sys.stderr)
            errors += 1
        pos = spec.get("position", [])
        if len(pos) != 3 or not all(isinstance(v, (int, float)) for v in pos):
            print(f"FAIL: Invalid position vector for {cid}: {pos}", file=sys.stderr)
            errors += 1

    if errors:
        print(f"Validation failed with {errors} error(s).", file=sys.stderr)
        return 1
    print(f"OK: All {len(comps)} companions validated with valid positions and compiled loadouts.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="Print companion roster status")
    parser.add_argument("--validate", action="store_true", help="Validate companion presets and loadouts")
    parser.add_argument("--hire", type=str, metavar="COMPANION_ID", help="Hire a companion")
    parser.add_argument("--player", type=str, default="Survivor", help="Survivor name when hiring")
    parser.add_argument("--dismiss", type=str, metavar="COMPANION_ID", help="Dismiss a companion back to HQ")

    args = parser.parse_args()
    mgr = get_manager()

    if args.validate:
        return validate_all()
    if args.hire:
        try:
            res = mgr.hire_companion(args.hire, args.player)
            print(f"Successfully hired {res.get('name', args.hire)} for {args.player}.")
            return 0
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    if args.dismiss:
        try:
            res = mgr.dismiss_companion(args.dismiss)
            print(f"Successfully dismissed {res.get('name', args.dismiss)} back to Qalat-e Lut.")
            return 0
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    return print_status()


if __name__ == "__main__":
    sys.exit(main())
