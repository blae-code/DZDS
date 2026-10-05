#!/usr/bin/env python3
"""Compile presets/types_dzds.yaml into a custom CE types file + cfgeconomycore entry.

With a mission folder present (after `make pull` or a local test server), writes
  <mission>/dzds/types_dzds.xml  and registers it in <mission>/cfgeconomycore.xml.
Without one (no server yet), writes build/dzds/types_dzds.xml and prints the snippet.

Usage: tools/types_gen.py [--mission server/mpmissions/dayzOffline.chernarusplus]
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "types_dzds.yaml"
FOLDER, FILE = "dzds", "types_dzds.xml"
CE_SNIPPET = f'    <ce folder="{FOLDER}">\n        <file name="{FILE}" type="types" />\n    </ce>\n'
VALID_USAGE = {"Military", "Police", "Medic", "Firefighter", "Industrial", "Farm", "Coast",
               "Town", "Village", "Hunting", "Office", "School", "Prison", "Lunapark",
               "SeasonalEvent", "ContaminatedArea", "Historical"}
VALID_VALUE = {"Tier1", "Tier2", "Tier3", "Tier4", "Unique"}


def build(preset: dict) -> tuple[ET.Element, list[str]]:
    root = ET.Element("types")
    warnings = []
    for item in preset["items"]:
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
    text = core.read_text()
    if f'name="{FILE}"' in text:
        return False
    if "</economycore>" not in text:
        raise SystemExit(f"{core} has no </economycore>; add manually:\n{CE_SNIPPET}")
    shutil.copy2(core, core.with_suffix(".xml.bak"))
    block = f'<ce folder="{FOLDER}">'
    if block in text:
        text = text.replace(block, block + f'\n        <file name="{FILE}" type="types" />', 1)
    else:
        text = text.replace("</economycore>", CE_SNIPPET + "</economycore>", 1)
    core.write_text(text)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    mission_name = os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")
    ap.add_argument("--mission", default=str(ROOT / "server" / "mpmissions" / mission_name))
    a = ap.parse_args()

    root, warnings = build(yaml.safe_load(PRESET.read_text()))
    for w in warnings:
        print("WARNING:", w, file=sys.stderr)
    mission = Path(a.mission)
    has_mission = (mission / "cfgeconomycore.xml").exists()
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
