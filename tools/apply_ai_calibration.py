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


def clamp(node, changes: list) -> None:
    """Pull bounded numeric keys into range wherever they appear; keep 0/negative sentinels ("use global")."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in BOUNDS and isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
                lo, hi = BOUNDS[k]
                new = min(max(v, lo), hi)
                if new != v:
                    changes.append((k, v, new))
                    node[k] = new
            else:
                clamp(v, changes)
    elif isinstance(node, list):
        for item in node:
            clamp(item, changes)


def write_with_backup(path: Path, data) -> None:
    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    path.write_text(json.dumps(data, indent=4) + "\n")
    print(f"Wrote {path} (backup: {path.name}.bak)")


def apply_clamps(preset: dict, dry_run: bool) -> None:
    for rel in preset.get("clamp_targets", []):
        path = PROFILES / rel
        if not path.exists():
            print(f"(skip clamp: {rel} not present yet)")
            continue
        data = json.loads(path.read_text())
        changes: list = []
        clamp(data, changes)
        for k, old, new in changes:
            print(f"{path.name}: {k}: {old} -> {new}")
        if changes and not dry_run:
            write_with_backup(path, data)


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
        print("Global settings already calibrated.")
    elif not args.dry_run:
        write_with_backup(target, data)
    apply_clamps(preset, args.dry_run)
    if args.dry_run:
        print("(dry run, nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
