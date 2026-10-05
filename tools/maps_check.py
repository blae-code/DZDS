#!/usr/bin/env python3
"""Check maps/*.yaml against maps/_roles.yaml: bounds, coords in range, role coverage.

Usage: tools/maps_check.py [map ...]     (default: all maps; exit 1 if any map incomplete)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

MAPS = Path(__file__).resolve().parent.parent / "maps"


def check(data: dict, roles: dict) -> list[str]:
    problems = []
    xmin, zmin, xmax, zmax = data.get("bounds", [0, 0, 0, 0])
    if xmax <= xmin or zmax <= zmin:
        problems.append("bounds not set")
    if not data.get("mission") or data["mission"] == "TBD":
        problems.append("mission folder name not set")
    locs = data.get("locations") or {}
    for name, xy in locs.items():
        if not (xmin <= xy[0] <= xmax and zmin <= xy[1] <= zmax):
            problems.append(f"location '{name}' {xy} outside bounds")
    assigned = data.get("roles") or {}
    for role, rule in roles.items():
        names = assigned.get(role) or []
        unknown = [n for n in names if n not in locs]
        if unknown:
            problems.append(f"role '{role}' references unknown location(s) {unknown}")
        if len(names) < rule.get("min", 1):
            problems.append(f"role '{role}' needs >= {rule.get('min', 1)} location(s), has {len(names)}")
    for role in assigned:
        if role not in roles:
            problems.append(f"role '{role}' not defined in _roles.yaml")
    return problems


def main(argv: list[str]) -> int:
    roles = yaml.safe_load((MAPS / "_roles.yaml").read_text())["roles"]
    files = [MAPS / f"{m}.yaml" for m in argv] or sorted(p for p in MAPS.glob("*.yaml") if not p.name.startswith("_"))
    bad = 0
    for f in files:
        problems = check(yaml.safe_load(f.read_text()), roles)
        print(f"{'OK  ' if not problems else 'TODO'} {f.stem}")
        for p in problems:
            print(f"     - {p}")
        bad += bool(problems)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
