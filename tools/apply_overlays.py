#!/usr/bin/env python3
"""Apply settings overlays (presets/overlays/*.yaml) onto mirrored server JSON configs.

Each overlay:
    root: profiles | mission           # server/profiles  or  server/mpmissions/<MISSION_NAME>
    target: relative/path/file.json
    values: { nested: { keys: value } }  # deep-merged; only keys that already exist are set

Keys missing from the target are reported, not added: the game/mod writes the real
schema on first start, and we don't want to invent fields. Writes a .bak first.

Usage: tools/apply_overlays.py [--dry-run] [overlay names...]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OVERLAYS = ROOT / "presets" / "overlays"


def merge(node: dict, values: dict, path: str = "") -> tuple[list, list]:
    """Deep-merge values into node in place. Returns (changes, missing_keys)."""
    changes, missing = [], []
    for k, v in values.items():
        here = f"{path}.{k}" if path else k
        if k not in node:
            missing.append(here)
        elif isinstance(v, dict) and isinstance(node[k], dict):
            c, m = merge(node[k], v, here)
            changes += c
            missing += m
        elif node[k] != v:
            changes.append((here, node[k], v))
            node[k] = v
    return changes, missing


def resolve(root: str) -> Path:
    if root == "profiles":
        return ROOT / "server" / "profiles"
    if root == "mission":
        return ROOT / "server" / "mpmissions" / os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")
    raise SystemExit(f"unknown root '{root}'")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    files = [OVERLAYS / f"{n}.yaml" for n in a.names] or sorted(OVERLAYS.glob("*.yaml"))
    for f in files:
        ov = yaml.safe_load(f.read_text())
        target = resolve(ov["root"]) / ov["target"]
        print(f"== {f.stem} -> {target.relative_to(ROOT)}")
        if not target.exists():
            print("   (not present yet; start the server once or `make pull`)")
            continue
        data = json.loads(target.read_text())
        changes, missing = merge(data, ov["values"])
        for k in missing:
            print(f"   WARNING: {k} not in file; not added (check name against the real file)")
        for k, old, new in changes:
            print(f"   {k}: {old} -> {new}")
        if changes and not a.dry_run:
            shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
            target.write_text(json.dumps(data, indent=4) + "\n")
        if not changes:
            print("   already applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
