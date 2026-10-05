#!/usr/bin/env python3
"""Apply the Expansion AI calibration overlay onto the mirrored server config.

Edits only the keys listed in presets/expansion_ai_calibration.yaml, refuses values
outside the spec bounds, and writes a .bak first. Keys are matched anywhere in the
JSON tree, so the overlay keeps working if Expansion nests them differently.

Usage: tools/apply_ai_calibration.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "expansion_ai_calibration.yaml"
PROFILES = ROOT / "server" / "profiles"

BOUNDS = {
    "AccuracyMin": (0.25, 0.32),
    "AccuracyMax": (0.45, 0.52),
    "ThreatDistanceLimit": (0.0, 300.0),
}


def check_bounds(values: dict) -> list[str]:
    errs = []
    for key, val in values.items():
        if key in BOUNDS:
            lo, hi = BOUNDS[key]
            if not (lo <= float(val) <= hi):
                errs.append(f"{key}={val} outside [{lo}, {hi}]")
    if values.get("AccuracyMin", 0) > values.get("AccuracyMax", 1):
        errs.append("AccuracyMin must be <= AccuracyMax")
    return errs


def apply(node, values: dict, changes: list, seen: set) -> None:
    if isinstance(node, dict):
        for k in node:
            if k in values and not isinstance(node[k], (dict, list)):
                seen.add(k)
                if node[k] != values[k]:
                    changes.append((k, node[k], values[k]))
                node[k] = values[k]
            else:
                apply(node[k], values, changes, seen)
    elif isinstance(node, list):
        for item in node:
            apply(item, values, changes, seen)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    preset = yaml.safe_load(PRESET.read_text())
    values = preset["values"]
    errs = check_bounds(values)
    if errs:
        print("Preset violates calibration bounds:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 1

    target = PROFILES / preset["target"]
    if not target.exists():
        print(f"{target} not found. Run `make pull` first.", file=sys.stderr)
        return 2
    data = json.loads(target.read_text())
    changes: list = []
    seen: set = set()
    apply(data, values, changes, seen)
    for k in values:
        if k not in seen:
            print(f"WARNING: key {k} not present in {target.name}; not added", file=sys.stderr)
    for k, old, new in changes:
        print(f"{k}: {old} -> {new}")
    if not changes:
        print("Already calibrated; no changes.")
        return 0
    if args.dry_run:
        print("(dry run, nothing written)")
        return 0
    shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
    target.write_text(json.dumps(data, indent=4) + "\n")
    print(f"Wrote {target} (backup: {target.name}.bak)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
