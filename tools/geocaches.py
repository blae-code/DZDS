#!/usr/bin/env python3
"""Compile presets/geocaches.yaml into server/profiles/DZDS/geocaches.json for init.c.

Validates that:
- Exactly 20 geocache sites are defined.
- Coordinates are within Nasdara bounds [0, 16384].
- Every container and loot item classname is known in mission types XML files.

Usage: tools/geocaches.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import yaml

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "geocaches.yaml"
OUT = ROOT / "server" / "profiles" / "DZDS" / "geocaches.json"
MISSION = ROOT / "server" / "mpmissions" / "dayzOffline.nasdara"


def load_all_known_types(mission_dir: Path) -> set[str]:
    known = set()
    for xml_file in mission_dir.rglob("*.xml"):
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()
            for t in root.findall(".//type"):
                name = t.get("name")
                if name:
                    known.add(name)
        except Exception:
            continue
    return known


def compile_geocaches(dry_run: bool = False) -> dict:
    if not PRESET.exists():
        raise SystemExit(f"Preset not found: {PRESET}")

    data = yaml.safe_load(PRESET.read_text(encoding="utf-8"))
    caches = data.get("geocaches", [])

    if len(caches) != 20:
        raise SystemExit(f"Expected exactly 20 geocaches, found {len(caches)}")

    known = load_all_known_types(MISSION)
    compiled = []

    for c in caches:
        cid = c.get("id")
        landmark = c.get("landmark")
        pos_str = c.get("pos", "")
        parts = [float(x) for x in pos_str.split()]
        if len(parts) != 3:
            raise SystemExit(f"Invalid position in cache {cid}: {pos_str}")
        x, y, z = parts
        if not (0 <= x <= 16384 and 0 <= z <= 16384):
            raise SystemExit(f"Coordinates out of bounds in cache {cid}: {pos_str}")

        container = c.get("container", "SeaChest")
        if container not in known:
            raise SystemExit(f"Unknown container class in cache {cid}: {container}")

        items = c.get("items", [])
        for item in items:
            if item not in known:
                raise SystemExit(f"Unknown item class in cache {cid} ({landmark}): {item}")

        compiled.append({
            "Id": cid,
            "Landmark": landmark,
            "Pos": pos_str,
            "Container": container,
            "Danger": c.get("danger", "Unknown"),
            "Items": items
        })

    result = {"Geocaches": compiled}

    if not dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"Compiled {len(compiled)} geocaches to {OUT.relative_to(ROOT)}")
    else:
        print(f"Dry-run: verified {len(compiled)} geocaches successfully")

    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="validate without writing output file")
    args = parser.parse_args()
    compile_geocaches(args.dry_run)


if __name__ == "__main__":
    main()

