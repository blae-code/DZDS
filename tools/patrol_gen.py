#!/usr/bin/env python3
"""Generate Expansion AI patrols from faction templates, map roles and site control.

Inputs: presets/factions.yaml (behaviour profiles + patrol_templates + initial_control),
maps/<map>.yaml (locations, bounds). Later the war ledger replaces initial_control.

Output: build/patrols.<map>.json (preview). If the mission's
expansion/settings/AIPatrolSettings.json exists, its "Patrols" list is replaced (with .bak).

Field names and sentinels come from Expansion's source (ExpansionAIPatrolBase.c):
  MinDistRadius/MaxDistRadius/DespawnRadius -2 = general setting; DespawnTime -1 = general;
  RespawnTime -1 = never, -2 = general.

Usage: tools/patrol_gen.py [--map chernarusplus] [--interim] [--dry-run]
  --interim  use Expansion built-in factions (before @DZDS is built)
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
GARRISON_RADIUS = 35.0
GENERAL = -2

# Defaults for every generated patrol. Behaviour profile and template overrides go on top.
BASE = {
    "Persist": False,
    "Formation": "Column",
    "FormationScale": 1.5,
    "FormationLooseness": 0.0,
    "Loadout": "",
    "Units": [],
    "Behaviour": "LOOP",
    "LootingBehaviour": "DEFAULT",
    "Speed": "WALK",
    "UnderThreatSpeed": "JOG",
    "DefaultStance": "STANDING",
    "DefaultLookAngle": 0.0,
    "CanBeLooted": True,
    "LootDropOnDeath": "",
    "UnlimitedReload": 0,
    "SniperProneDistanceThreshold": 0.0,
    "AccuracyMin": -1.0,
    "AccuracyMax": -1.0,
    "ThreatDistanceLimit": -1.0,
    "NoiseInvestigationDistanceLimit": -1.0,
    "MaxFlankingDistance": -1.0,
    "EnableFlankingOutsideCombat": -1,
    "DamageMultiplier": 1.0,
    "DamageReceivedMultiplier": 1.0,
    "HeadshotResistance": 0.0,
    "CanSpawnInContaminatedArea": False,
    "CanBeTriggeredByAI": False,
    "MinDistRadius": GENERAL,
    "MaxDistRadius": GENERAL,
    "DespawnRadius": GENERAL,
    "MinSpreadRadius": 1.0,
    "MaxSpreadRadius": 20.0,
    "Chance": 1.0,
    "DespawnTime": -1.0,
    "RespawnTime": GENERAL,
    "LoadBalancingCategory": "",
    "ObjectClassName": "",
    "WaypointInterpolation": "",
    "UseRandomWaypointAsStartPoint": False,
}


def load(rel: str):
    return yaml.safe_load((ROOT / rel).read_text())


def vec(x: float, z: float) -> list[float]:
    # [x, y, z]; y=0, Expansion places units on the ground [test]
    return [round(x, 1), 0.0, round(z, 1)]


def clamp(x: float, z: float, bounds) -> tuple[float, float]:
    xmin, zmin, xmax, zmax = bounds
    return min(max(x, xmin), xmax), min(max(z, zmin), zmax)


def waypoints(kind: str, site: str, sites_of_faction: list[str], locs: dict, bounds) -> list[list[float]]:
    x, z = locs[site][:2]
    if kind == "garrison":
        pts = [clamp(x + GARRISON_RADIUS * math.cos(a), z + GARRISON_RADIUS * math.sin(a), bounds)
               for a in (0, math.pi / 2, math.pi, 3 * math.pi / 2)]
        return [vec(*p) for p in pts]
    if kind == "route":
        others = [s for s in sites_of_faction if s != site]
        if not others:
            return [vec(x, z)]
        dest = min(others, key=lambda s: (locs[s][0] - x) ** 2 + (locs[s][1] - z) ** 2)
        return [vec(x, z), vec(*locs[dest][:2])]
    return [vec(x, z)]  # roam / ambush: a single anchor point


def sites_for(at: str, faction: str, control: dict) -> list[str]:
    if at == "held":
        return list(control.get(faction, []))
    if at == "contested":
        return list(control.get("contested", []))
    raise ValueError(f"unknown 'at': {at}")


def generate(map_name: str, interim: bool = False) -> list[dict]:
    factions = load("presets/factions.yaml")
    mp = load(f"maps/{map_name}.yaml")
    control = factions["initial_control"][map_name]
    locs, bounds = mp["locations"], mp["bounds"]
    patrols = []
    for name, spec in factions["factions"].items():
        engine = spec["interim_faction"] if interim else spec["custom_faction"]
        if not engine:
            continue
        for tname, t in (spec.get("patrol_templates") or {}).items():
            for site in sites_for(t["at"], name, control):
                p = dict(BASE)
                p.update(spec.get("behaviour", {}))
                p.update(t.get("behaviour", {}))
                variant = t.get("loadout_variant")
                p.update({
                    "Name": f"{name} {tname} @ {site}",
                    "Faction": engine,
                    "Persist": bool(t.get("persist", False)),
                    "Loadout": f"DZDS_{name}_{variant}" if variant else f"DZDS_{name}",
                    "NumberOfAI": int(t["size"][0]),
                    "NumberOfAIMax": int(t["size"][1]),
                    "Chance": float(t.get("chance", 1.0)),
                    "RespawnTime": float(t.get("respawn", GENERAL)),
                    "Waypoints": waypoints(t["kind"], site, control.get(name, []), locs, bounds),
                })
                p["CanBeLooted"] = bool(p["CanBeLooted"])
                patrols.append(p)
    return patrols


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=os.environ.get("GM_MAP", "chernarusplus"))
    ap.add_argument("--interim", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    patrols = generate(a.map, a.interim)
    max_ai = sum(p["NumberOfAIMax"] for p in patrols)
    print(f"{len(patrols)} patrols, up to {max_ai} AI if every one spawned "
          f"(they only spawn near players; docs/LIVING_WORLD.md budget ~60 concurrent)")
    for p in patrols:
        print(f"  {p['Faction']:<17} {p['Name']:<48} {p['NumberOfAI']}-{p['NumberOfAIMax']} "
              f"{p['Behaviour']:<17} chance {p['Chance']}")
    if a.dry_run:
        return 0
    out = ROOT / "build" / f"patrols.{a.map}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"Patrols": patrols}, indent=4) + "\n")
    print(f"Wrote preview {out.relative_to(ROOT)}")
    mission = load(f"maps/{a.map}.yaml")["mission"]
    target = ROOT / "server" / "mpmissions" / mission / "expansion" / "settings" / "AIPatrolSettings.json"
    if target.exists():
        data = json.loads(target.read_text())
        shutil.copy2(target, target.with_suffix(".json.bak"))
        data["Patrols"] = patrols
        target.write_text(json.dumps(data, indent=4) + "\n")
        print(f"Replaced Patrols in {target.relative_to(ROOT)} (backup .bak). Run `make calibrate` after.")
    else:
        print("(no AIPatrolSettings.json yet: start the local server once to generate it)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
