#!/usr/bin/env python3
"""Compile presets/vehicle_events.yaml into CE vehicle events placed by role and holder.

Usage: tools/vehicle_events.py [--mission DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import math
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402

FOLDER, FILE, PREFIX = "dzds", "events_dzds.xml", "DZDS_"


def sites_for(ev: dict, led: WarLedger) -> list[str]:
    out = []
    for site, holder in sorted(led.s.control.items()):
        if holder in ev.get("holders", [holder]) and set(ev["roles"]) & led.site_roles(site):
            out.append(site)
    return out


def build(cfg: dict, led: WarLedger) -> tuple[ET.Element, dict[str, list[tuple[float, float, float]]]]:
    d = cfg["defaults"]
    events_root = ET.Element("events")
    spawns: dict[str, list[tuple[float, float, float]]] = {}
    locs = led.locations()
    for ev in cfg["events"]:
        if not ev.get("children"):
            continue
        sites = sites_for(ev, led)
        if not sites:
            continue
        e = ET.SubElement(events_root, "event", name=ev["name"])
        nominal = int(ev["nominal"])
        for tag, val in (("nominal", nominal), ("min", max(0, nominal - 1)), ("max", nominal),
                         ("lifetime", d["lifetime"]), ("restock", d["restock"]),
                         ("saferadius", d["saferadius"]), ("distanceradius", d["distanceradius"]),
                         ("cleanupradius", d["cleanupradius"])):
            ET.SubElement(e, tag).text = str(val)
        ET.SubElement(e, "flags", deletable="0", init_random="0", remove_damaged="1")
        ET.SubElement(e, "position").text = "fixed"
        ET.SubElement(e, "limit").text = "mixed"
        ET.SubElement(e, "active").text = "1"
        children = ET.SubElement(e, "children")
        for c in ev["children"]:
            ET.SubElement(children, "child", lootmax="0", lootmin="0", max="1", min="0", type=c)
        pts = []
        for i, site in enumerate(sites):
            x, z = locs[site][:2]
            for k in range(2):  # two candidate positions per site
                a = (i * 2.4 + k * math.pi) % (2 * math.pi)
                pts.append((round(x + d["radius_m"] * math.cos(a), 1), round(z + d["radius_m"] * math.sin(a), 1),
                            round(math.degrees(a) % 360, 1)))
        spawns[ev["name"]] = pts
    ET.indent(events_root, space="    ")
    return events_root, spawns


def merge_spawns(path: Path, spawns: dict) -> None:
    tree = ET.parse(path)
    root = tree.getroot()
    for old in [e for e in root.findall("event") if e.get("name", "").startswith(PREFIX)]:
        root.remove(old)
    for name, pts in spawns.items():
        e = ET.SubElement(root, "event", name=name)
        for x, z, a in pts:
            ET.SubElement(e, "pos", x=str(x), z=str(z), a=str(a))
    ET.indent(root, space="    ")
    shutil.copy2(path, path.with_suffix(".xml.bak"))
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mission", default=str(ROOT / "server" / "mpmissions" /
                                             os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load((ROOT / "presets" / "vehicle_events.yaml").read_text())
    map_name = os.environ.get("GM_MAP", "chernarusplus")
    led = WarLedger.load(map_name) if STATE.exists() else WarLedger.new(map_name)
    events, spawns = build(cfg, led)
    for name, pts in spawns.items():
        print(f"  {name:<24} {len(pts)} position(s)")
    skipped = [ev["name"] for ev in cfg["events"] if not ev.get("children")]
    if skipped:
        print(f"  skipped (classnames not verified yet): {', '.join(skipped)}")
    mission = Path(a.mission)
    if a.dry_run or not (mission / "cfgeventspawns.xml").exists():
        if not a.dry_run:
            print("(no mission files yet; nothing written)")
        return 0
    (mission / FOLDER).mkdir(exist_ok=True)
    ET.ElementTree(events).write(mission / FOLDER / FILE, encoding="UTF-8", xml_declaration=True)
    merge_spawns(mission / "cfgeventspawns.xml", spawns)
    core = mission / "cfgeconomycore.xml"
    text = core.read_text()
    if f'name="{FILE}"' not in text:
        shutil.copy2(core, core.with_suffix(".xml.bak"))
        block = f'<ce folder="{FOLDER}">'
        entry = f'        <file name="{FILE}" type="events" />\n'
        if block in text:
            text = text.replace(block, block + "\n" + entry, 1)
        else:
            text = text.replace("</economycore>", f'    {block}\n{entry}    </ce>\n</economycore>', 1)
        core.write_text(text)
    print(f"Wrote {FOLDER}/{FILE}, updated cfgeventspawns.xml and cfgeconomycore.xml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
