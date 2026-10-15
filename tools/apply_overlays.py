#!/usr/bin/env python3
"""Apply settings overlays (presets/overlays/*.yaml) onto mirrored server JSON configs.

Each overlay:
    root: profiles | mission           # server/profiles  or  server/mpmissions/<MISSION_NAME>
    target: relative/path/file.json    # or a glob (e.g. expansion/missions/Airdrop_*.json)
    values: { nested: { keys: value } }  # deep-merged; only keys that already exist are set
    remove_classnames: [Name, ...]     # optional: drop these items from every list in the file
                                       # (loot entries, attachments, variants), e.g. items whose
                                       # mod is not loaded, which crash Expansion's loot spawner
    requires_mod: "@Folder"            # optional: skip unless that mod is enabled in mods.yaml

Keys missing from the target are reported, not added: the game/mod writes the real
schema on first start, and we don't want to invent fields. Writes a .bak first.

Usage: tools/apply_overlays.py [--dry-run] [overlay names...]
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import yaml

import active

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
        else:
            if isinstance(v, bool) and type(node[k]) is int:
                v = int(v)                 # Expansion stores flags as 0/1: keep the file's type
            if node[k] == v and isinstance(node[k], bool) == isinstance(v, bool):
                continue
            changes.append((here, node[k], v))
            node[k] = v
    return changes, missing


def remove_classnames(node, names: set) -> list:
    """Drop every list element that is, or is a dict named (Name/ClassName), one of names.
    Recurses through the whole document. Returns the removed names."""
    removed = []
    if isinstance(node, dict):
        for v in node.values():
            removed += remove_classnames(v, names)
    elif isinstance(node, list):
        keep = []
        for e in node:
            if isinstance(e, str):
                name = e
            elif isinstance(e, dict):
                name = e.get("Name") or e.get("ClassName")
            else:
                name = None
            if name in names:
                removed.append(name)
            else:
                removed += remove_classnames(e, names)
                keep.append(e)
        node[:] = keep
    return removed


def mod_enabled(folder: str, mods: list[dict] | None = None) -> bool:
    """Whether config/mods.yaml has this mod folder enabled."""
    if mods is None:
        mods = yaml.safe_load((ROOT / "config" / "mods.yaml").read_text())["mods"]
    return any(m.get("folder") == folder and m.get("enabled") for m in mods)


def resolve(root: str) -> Path:
    if root == "profiles":
        return ROOT / "server" / "profiles"
    if root == "mission":
        return active.mission_dir()
    raise SystemExit(f"unknown root '{root}'")


def targets(ov: dict) -> list[Path]:
    """The overlay's target file, or every file its glob matches (sorted)."""
    base = resolve(ov["root"])
    if any(c in ov["target"] for c in "*?["):
        return sorted(base.glob(ov["target"]))
    return [base / ov["target"]]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("names", nargs="*")
    a = ap.parse_args()
    files = [OVERLAYS / f"{n}.yaml" for n in a.names] or sorted(OVERLAYS.glob("*.yaml"))
    for f in files:
        ov = yaml.safe_load(f.read_text())
        print(f"== {f.stem} -> {ov['target']}")
        if ov.get("requires_mod") and not mod_enabled(ov["requires_mod"]):
            print(f"   skipped: {ov['requires_mod']} not enabled in config/mods.yaml")
            continue
        paths = targets(ov)
        if not paths or not paths[0].exists():
            print("   (not present yet; start the server once or `make pull`)")
            continue
        drop = set(ov.get("remove_classnames") or [])
        for target in paths:
            data = json.loads(target.read_text())
            changes, missing = merge(data, ov.get("values") or {})
            removed = remove_classnames(data, drop) if drop else []
            label = f"   {target.relative_to(ROOT)}" if len(paths) > 1 else "  "
            for k in missing:
                print(f"{label} WARNING: {k} not in file; not added (check name against the real file)")
            for k, old, new in changes:
                print(f"{label} {k}: {old} -> {new}")
            if removed:
                print(f"{label} removed {len(removed)} item(s): {', '.join(sorted(set(removed)))}")
            if (changes or removed) and not a.dry_run:
                shutil.copy2(target, target.with_suffix(target.suffix + ".bak"))
                target.write_text(json.dumps(data, indent=4) + "\n")
            if not changes and not removed:
                print(f"{label} already applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
