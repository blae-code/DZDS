#!/usr/bin/env python3
"""List classnames from types XML files that downloaded mods ship, to fill presets/types_dzds.yaml.

Many mods include a types.xml (often under an Extras/ or ServerFiles/ folder). This scans
each enabled mod in DAYZ_WORKSHOP_DIR/<id>/ and prints the <type name="..."> entries,
marking ones already in the preset. Subscribe to the mods in Steam first.

Usage: tools/collect_mod_types.py [--grep Heli]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

import yaml

from modstring import ROOT, ordered, load_mods

TYPE_RE = re.compile(r'<type\s+name="([^"]+)"')


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grep", help="only show classnames containing this (case-insensitive)")
    a = ap.parse_args()
    workshop = Path(os.path.expandvars(os.path.expanduser(os.environ.get("DAYZ_WORKSHOP_DIR", ""))))
    if not workshop.is_dir():
        print("Set DAYZ_WORKSHOP_DIR (see .env.example)", file=sys.stderr)
        return 2
    preset = yaml.safe_load((ROOT / "presets" / "types_dzds.yaml").read_text())
    known = {i["name"] for i in preset["items"]}
    for m in ordered(load_mods()):
        d = workshop / str(m["id"])
        if not d.is_dir():
            continue
        names: set[str] = set()
        for f in d.rglob("*.xml"):
            txt = f.read_text(errors="replace")
            if "<types" in txt:
                names |= set(TYPE_RE.findall(txt))
        if a.grep:
            names = {n for n in names if a.grep.lower() in n.lower()}
        if names:
            print(f"== {m['name']} ({len(names)})")
            for n in sorted(names):
                print(f"   {'*' if n in known else ' '} {n}")
    print("\n* = already in presets/types_dzds.yaml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
