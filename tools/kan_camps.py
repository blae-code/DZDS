#!/usr/bin/env python3
"""Apply presets/kan_camps.yaml role counts to profiles/KANSurvivorNPC/camps.json.

camps.json is live state the KAN mod rewrites every ~10 min and at shutdown, so run this with
the server stopped, after a fresh `make pull`, right before `make push`.

Usage: tools/kan_camps.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

import active

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "kan_camps.yaml"
CAMPS = ROOT / "server" / "profiles" / "KANSurvivorNPC" / "camps.json"
ROLES = ["Roamers", "Looters", "Builders", "Guards", "Attackers", "Snipers"]
FLOOR = {"Roamers": 0, "Looters": 0, "Snipers": 0, "Builders": 1, "Guards": 1, "Attackers": 1}
MAX_ROLE = 12  # KAN_CampRoleCounts.MAX_ROLE_COUNT


def check(camp_id: str, roles: dict) -> None:
    roles = {k: v for k, v in roles.items() if k != "site"}
    if sorted(roles) != sorted(ROLES):
        raise SystemExit(f"{camp_id}: give exactly {ROLES} (an all-zero or partial override is ignored)")
    for r, n in roles.items():
        if not FLOOR[r] <= n <= MAX_ROLE:
            raise SystemExit(f"{camp_id}.{r}={n}: the mod clamps it to [{FLOOR[r]}, {MAX_ROLE}]")


def apply(data: dict, preset: dict, locs: dict | None = None) -> list[str]:
    camps = {c["Id"]: c for c in data["Camps"]}
    changes = []
    for camp_id in [c for c in camps if c not in preset["camps"]]:
        data["Camps"] = [c for c in data["Camps"] if c["Id"] != camp_id]
        changes.append(f"removed {camp_id} (not in presets/kan_camps.yaml)")
    for camp_id, spec in preset["camps"].items():
        roles = {k: v for k, v in spec.items() if k != "site"}
        check(camp_id, roles)
        if camp_id not in camps:
            raise SystemExit(f"camp {camp_id} not in camps.json (have {sorted(camps)})")
        camp = camps[camp_id]
        want = {r: int(roles[r]) for r in ROLES}
        if camp.get("RoleOverrides") != want:
            changes.append(f"{camp_id}: {camp.get('RoleOverrides')} -> {want}")
            camp["RoleOverrides"] = want
        if spec.get("site") and locs:
            x, z = locs[spec["site"]][:2]
            pos = [float(x) + 15.0, 0.0, float(z) + 15.0]
            if camp.get("Position") != pos:
                changes.append(f"{camp_id}: Position -> {pos} ({spec['site']})")
                camp["Position"] = pos
    return changes


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--dry-run", action="store_true")
    args = a.parse_args()
    data = json.loads(CAMPS.read_text())
    changes = apply(data, yaml.safe_load(PRESET.read_text()), active.map_data()["locations"])
    for c in changes:
        print("  " + c)
    if not changes:
        print("  camps.json already matches presets/kan_camps.yaml")
    elif not args.dry_run:
        CAMPS.write_text(json.dumps(data, indent=4))  # the mod writes no trailing newline
    return 0


if __name__ == "__main__":
    sys.exit(main())
