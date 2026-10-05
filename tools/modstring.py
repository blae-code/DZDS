#!/usr/bin/env python3
"""Generate DayZ launch mod strings and validate .bikey files from config/mods.yaml.

Usage:
  tools/modstring.py string                 # print -mod= / -serverMod= for the GSP panel
  tools/modstring.py keys [--copy-to DIR]   # check each mod ships a .bikey (local workshop dir)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
MODS_FILE = ROOT / "config" / "mods.yaml"
TIER_NAMES = {1: "core", 2: "gameplay/AI", 3: "vehicles/base", 4: "UI/admin"}


def load_mods(path: Path = MODS_FILE) -> list[dict]:
    data = yaml.safe_load(path.read_text())
    mods = data.get("mods", [])
    errors = []
    seen_ids, seen_folders = set(), set()
    for m in mods:
        for key in ("name", "folder", "id", "tier"):
            if key not in m:
                errors.append(f"{m.get('name', m)}: missing '{key}'")
        if m.get("tier") not in TIER_NAMES:
            errors.append(f"{m.get('name')}: tier must be one of {sorted(TIER_NAMES)}")
        if m.get("id") in seen_ids:
            errors.append(f"duplicate workshop id {m.get('id')}")
        if m.get("folder") in seen_folders:
            errors.append(f"duplicate folder {m.get('folder')}")
        seen_ids.add(m.get("id"))
        seen_folders.add(m.get("folder"))
    if errors:
        raise SystemExit("mods.yaml invalid:\n  " + "\n  ".join(errors))
    return mods


def ordered(mods: list[dict]) -> list[dict]:
    """Enabled mods, stably sorted by tier (spec §6C)."""
    return sorted((m for m in mods if m.get("enabled", True)), key=lambda m: m["tier"])


def build_strings(mods: list[dict]) -> tuple[str, str]:
    active = ordered(mods)
    client = ";".join(m["folder"] for m in active if m.get("side", "both") == "both")
    server = ";".join(m["folder"] for m in active if m.get("side") == "server")
    return client, server


def find_bikeys(mod_dir: Path) -> list[Path]:
    return sorted(p for p in mod_dir.rglob("*") if p.suffix.lower() == ".bikey")


def cmd_string(args: argparse.Namespace) -> int:
    mods = load_mods()
    client, server = build_strings(mods)
    if args.verbose:
        for m in ordered(mods):
            flag = "" if m.get("verified") else "  [unverified]"
            print(f"# tier {m['tier']} ({TIER_NAMES[m['tier']]}): {m['folder']} ({m['id']}){flag}",
                  file=sys.stderr)
    print(f'-mod="{client};"' if client else "# no client mods")
    if server:
        print(f'-serverMod="{server};"')
    unverified = [m["name"] for m in ordered(mods) if not m.get("verified")]
    if unverified:
        print(f"# WARNING: {len(unverified)} enabled mod(s) not yet verified in mods.yaml",
              file=sys.stderr)
    return 0


def cmd_ids(args: argparse.Namespace) -> int:
    """Machine-readable '<side> <id> <folder>' lines, in load order (used by local_server.sh)."""
    for m in ordered(load_mods()):
        print(m.get("side", "both"), m["id"], m["folder"])
    return 0


def cmd_keys(args: argparse.Namespace) -> int:
    workshop = Path(os.path.expandvars(os.path.expanduser(
        args.workshop or os.environ.get("DAYZ_WORKSHOP_DIR", ""))))
    if not str(workshop) or not workshop.is_dir():
        print(f"Workshop dir not found: '{workshop}'. Set DAYZ_WORKSHOP_DIR.", file=sys.stderr)
        return 2
    missing = 0
    collected: list[Path] = []
    for m in ordered(load_mods()):
        if m.get("local"):
            print(f"LOCAL    {m['folder']:<40} built from mods/ (key: see mods/README.md)")
            continue
        mod_dir = workshop / str(m["id"])
        if not mod_dir.is_dir():
            print(f"MISSING  {m['folder']:<40} not downloaded ({mod_dir})")
            missing += 1
            continue
        keys = find_bikeys(mod_dir)
        if not keys:
            print(f"NOKEY    {m['folder']:<40} no .bikey found")
            missing += 1
        else:
            print(f"OK       {m['folder']:<40} {', '.join(k.name for k in keys)}")
            collected.extend(keys)
    if args.copy_to:
        dest = Path(args.copy_to)
        dest.mkdir(parents=True, exist_ok=True)
        for k in collected:
            shutil.copy2(k, dest / k.name)
        print(f"Copied {len(collected)} key(s) to {dest}")
    return 1 if missing else 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("string", help="print launch parameter strings")
    s.add_argument("-v", "--verbose", action="store_true")
    s.set_defaults(func=cmd_string)
    i = sub.add_parser("ids", help="print '<side> <id> <folder>' per enabled mod")
    i.set_defaults(func=cmd_ids)
    k = sub.add_parser("keys", help="validate .bikey presence")
    k.add_argument("--workshop", help="override DAYZ_WORKSHOP_DIR")
    k.add_argument("--copy-to", help="copy all found .bikey files here (e.g. server/keys)")
    k.set_defaults(func=cmd_keys)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
