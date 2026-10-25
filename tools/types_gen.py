#!/usr/bin/env python3
"""Compile presets/types_dzds.yaml into a custom CE types file + cfgeconomycore entry.

With a mission folder present (after `make pull` or a local test server), writes
  <mission>/dzds/types_dzds.xml  and registers it in <mission>/cfgeconomycore.xml.
Without one (no server yet), writes build/dzds/types_dzds.xml and prints the snippet.

Usage: tools/types_gen.py [--mission server/mpmissions/dayzOffline.chernarusplus]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

import active

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "types_dzds.yaml"
ARRIVALS = ROOT / "presets" / "arrivals.yaml"
FOLDER, FILE = "dzds", "types_dzds.xml"
CE_SNIPPET = f'    <ce folder="{FOLDER}">\n        <file name="{FILE}" type="types" />\n    </ce>\n'
VALID_USAGE = {"Military", "Police", "Medic", "Firefighter", "Industrial", "Farm", "Coast",
               "Town", "Village", "Hunting", "Office", "School", "Prison", "Lunapark",
               "SeasonalEvent", "ContaminatedArea", "Historical"}
VALID_VALUE = {"Tier1", "Tier2", "Tier3", "Tier4", "Unique"}


def arrival_items(preset: dict, vanilla: set[str], arrival_cfg: dict | None) -> list[dict]:
    """Every arrivals.yaml vehicle and part vanilla types.xml lacks, as registration-only
    entries (nominal 0: the CE keeps them, never spawns them)."""
    rules = preset.get("arrival_vehicles")
    if not rules or not arrival_cfg:
        return []
    out, seen = [], set(vanilla)
    vehicles = list(arrival_cfg.get("vehicles", []))
    if arrival_cfg.get("trailer"):   # the trailer parked behind a towing arrival vehicle
        vehicles.append({"class": arrival_cfg["trailer"]["class"], "parts": arrival_cfg["trailer"]["parts"]})
    for v in vehicles:
        for name, profile in [(v["class"], rules["vehicle_profile"])] + [(p, rules["part_profile"]) for p in v["parts"]]:
            if name not in seen:
                seen.add(name)
                out.append({"name": name, "profile": profile})
    comp = arrival_cfg.get("companion") or {}
    for part in (comp.get("horse_tack") or []) + (comp.get("dog_vests") or []):
        if part not in seen:
            seen.add(part)
            out.append({"name": part, "profile": rules["part_profile"]})
    for entity in (comp.get("horse_breeds") or []) + (comp.get("dog_classes") or []):
        if entity not in seen:
            seen.add(entity)
            out.append({"name": entity, "profile": rules["vehicle_profile"]})
    return out


def build(preset: dict, vanilla: set[str] | None = None,
          arrival_cfg: dict | None = None) -> tuple[ET.Element, list[str]]:
    root = ET.Element("types")
    warnings = []
    for item in preset["items"] + arrival_items(preset, vanilla or set(), arrival_cfg):
        if not item.get("enabled", True):
            continue
        spec = {**preset["profiles"].get(item.get("profile"), {}), **item}
        name = spec["name"]
        if name.startswith("TODO"):
            warnings.append(f"{name}: placeholder classname enabled, skipped")
            continue
        bad = set(spec.get("usage", [])) - VALID_USAGE | set(spec.get("value", [])) - VALID_VALUE
        if bad:
            warnings.append(f"{name}: unknown usage/value {sorted(bad)}")
        if spec.get("min", 0) > spec.get("nominal", 0):
            warnings.append(f"{name}: min > nominal")
        t = ET.SubElement(root, "type", name=name)
        for tag, default in (("nominal", 0), ("lifetime", 7200), ("restock", 0), ("min", 0),
                             ("quantmin", -1), ("quantmax", -1), ("cost", 100)):
            ET.SubElement(t, tag).text = str(spec.get(tag, default))
        ET.SubElement(t, "flags", count_in_cargo="0", count_in_hoarder="0", count_in_map="1",
                      count_in_player="0", crafted="0", deloot="0")
        if spec.get("category"):
            ET.SubElement(t, "category", name=spec["category"])
        for u in spec.get("usage", []):
            ET.SubElement(t, "usage", name=u)
        for v in spec.get("value", []):
            ET.SubElement(t, "value", name=v)
    ET.indent(root, space="    ")
    return root, warnings


def register(core: Path) -> bool:
    """Add our types file to cfgeconomycore.xml once (inside an existing dzds block if
    another tool, e.g. tools/vehicle_events.py, created it). Returns True if changed."""
    return active.register_ce_file(core, FILE, "types", FOLDER)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mission", default=str(active.mission_dir()))
    a = ap.parse_args()

    mission = Path(a.mission)
    has_mission = (mission / "cfgeconomycore.xml").exists()
    vanilla = set()
    if (mission / "db" / "types.xml").exists():
        vanilla = {t.get("name") for t in ET.parse(mission / "db" / "types.xml").getroot().findall("type")}
    arrival_cfg = yaml.safe_load(ARRIVALS.read_text()) if ARRIVALS.exists() else None
    root, warnings = build(yaml.safe_load(PRESET.read_text()), vanilla, arrival_cfg)
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)
    out_dir = (mission if has_mission else ROOT / "build") / FOLDER
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / FILE
    ET.ElementTree(root).write(out, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {len(root)} type(s) to {out}")
    if has_mission:
        changed = register(mission / "cfgeconomycore.xml")
        print("Registered in cfgeconomycore.xml" if changed else "cfgeconomycore.xml already registered")
    else:
        print(f"No mission at {mission} yet. When there is one, rerun, or add to cfgeconomycore.xml:\n{CE_SNIPPET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
