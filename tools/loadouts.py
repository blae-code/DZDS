#!/usr/bin/env python3
"""Compile presets/loadouts.yaml into Expansion AI loadout JSON, or check classnames.

  tools/loadouts.py build   # -> server/profiles/ExpansionMod/Loadouts/DZDS_*.json
  tools/loadouts.py check   # every classname vs the mission's types files (needs the server files)

Format from Expansion's ExpansionPrefabObject (DayZExpansion/Core/.../Prefab).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "loadouts.yaml"
OUT = ROOT / "server" / "profiles" / "ExpansionMod" / "Loadouts"


def item(classname: str, health: list[float], qmin: float = 0, qmax: float = 0) -> dict:
    return {
        "ClassName": classname,
        "Include": "",
        "Chance": 1.0,
        "Quantity": {"Min": float(qmin), "Max": float(qmax)},
        "Health": [{"Min": health[0], "Max": health[1], "Zone": ""}],
        "InventoryAttachments": [],
        "InventoryCargo": [],
        "ConstructionPartsBuilt": [],
        "Sets": [],
    }


def build_loadout(slots: dict[str, list[str]], cargo: list, health: list[float]) -> dict:
    root = item("", health)
    root["Health"] = []
    for slot, classes in slots.items():
        root["InventoryAttachments"].append({
            "SlotName": slot,
            "Items": [{**item(c, health), "Chance": round(1.0 / len(classes), 3)} for c in classes],
        })
    for classname, lo, hi in cargo:
        for _ in range(int(hi)):
            entry = item(classname, health)
            entry["Chance"] = 1.0 if _ < int(lo) else 0.5   # min guaranteed, the rest 50/50
            root["InventoryCargo"].append(entry)
    return root


def compile_all(cfg: dict) -> dict[str, dict]:
    out = {}
    for faction, spec in cfg["factions"].items():
        out[f"DZDS_{faction}"] = build_loadout(spec["slots"], spec.get("cargo", []), cfg["health"])
        for variant, overrides in (spec.get("variants") or {}).items():
            out[f"DZDS_{faction}_{variant}"] = build_loadout({**spec["slots"], **overrides},
                                                             spec.get("cargo", []), cfg["health"])
    return out


def classnames(cfg: dict) -> set[str]:
    names = set()
    for spec in cfg["factions"].values():
        for slot_items in [*spec["slots"].values(), *[v for var in (spec.get("variants") or {}).values()
                                                      for v in var.values()]]:
            names.update(slot_items)
        names.update(c[0] for c in spec.get("cargo", []))
    return names


def known_types(mission: Path) -> set[str]:
    sys.path.insert(0, str(ROOT / "tools"))
    from economy import types_files
    found = set()
    for f in types_files(mission):
        src = f.with_name(f.name + ".vanilla") if f.with_name(f.name + ".vanilla").exists() else f
        if src.exists():
            found |= {t.get("name") for t in ET.parse(src).getroot().findall("type")}
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "check"])
    ap.add_argument("--mission", default=str(ROOT / "server" / "mpmissions" /
                                             os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")))
    a = ap.parse_args()
    cfg = yaml.safe_load(PRESET.read_text())
    if a.cmd == "build":
        OUT.mkdir(parents=True, exist_ok=True)
        for name, data in compile_all(cfg).items():
            (OUT / f"{name}.json").write_text(json.dumps(data, indent=4) + "\n")
            print(f"  wrote {name}.json")
        print(f"{len(compile_all(cfg))} loadouts in {OUT.relative_to(ROOT)}")
        return 0
    known = known_types(Path(a.mission))
    if not known:
        print("No types files found: pull the server or start the local server once.", file=sys.stderr)
        return 2
    unknown = sorted(classnames(cfg) - known)
    for u in unknown:
        print(f"  UNKNOWN {u}")
    print(f"{len(classnames(cfg)) - len(unknown)} ok, {len(unknown)} unknown "
          f"(fix in presets/loadouts.yaml; `make mod-types --grep` helps)")
    return 1 if unknown else 0


if __name__ == "__main__":
    sys.exit(main())
