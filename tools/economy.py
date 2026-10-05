#!/usr/bin/env python3
"""Scale the mission's vanilla loot economy for population and campaign phase.

Regenerates <mission>/db/types.xml from a pristine baseline (db/types.xml.vanilla, created
on first run) using presets/economy.yaml, and applies `globals:` to db/globals.xml.

Usage:
  tools/economy.py                      # phase from today's date
  tools/economy.py --phase landfall     # force a phase
  tools/economy.py --dry-run            # report only
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "economy.yaml"
TIER_ORDER = ["Tier1", "Tier2", "Tier3", "Tier4", "Unique"]


def pick_phase(cfg: dict, name: str | None, today: dt.date) -> dict:
    phases = sorted(cfg["phases"], key=lambda p: p["from_week"])
    if name:
        for p in phases:
            if p["name"] == name:
                return p
        raise SystemExit(f"unknown phase '{name}'; have {[p['name'] for p in phases]}")
    start = cfg["campaign_start"]
    start = start if isinstance(start, dt.date) else dt.date.fromisoformat(str(start))
    week = max(0, (today - start).days // 7)
    current = phases[0]
    for p in phases:
        if week >= p["from_week"]:
            current = p
    return current


def population_factors(cfg: dict) -> dict:
    n = cfg["expected_players"]
    for b in sorted(cfg["population_brackets"], key=lambda b: b["max"]):
        if n <= b["max"]:
            return b["factors"]
    return {}


def top_tier(t: ET.Element) -> str | None:
    tiers = [v.get("name") for v in t.findall("value")]
    ranked = [x for x in TIER_ORDER if x in tiers]
    return ranked[-1] if ranked else None


def scale_types(root: ET.Element, cfg: dict, phase: dict) -> Counter:
    """Scale nominal/min in place. Returns before/after nominal totals per tier."""
    pop = population_factors(cfg)
    protected = set(cfg.get("protected_categories", []))
    hoard_tiers = set(cfg.get("hoarding", {}).get("count_in_hoarder_for_tiers", []))
    hoard_cats = set(cfg.get("hoarding", {}).get("count_in_hoarder_for_categories", []))
    stats: Counter = Counter()
    for t in root.findall("type"):
        nom_el, min_el = t.find("nominal"), t.find("min")
        if nom_el is None or min_el is None:
            continue
        nominal, minimum = int(nom_el.text), int(min_el.text)
        cat_el = t.find("category")
        cat = cat_el.get("name") if cat_el is not None else None
        tier = top_tier(t)
        label = tier or "untiered"
        stats[f"{label}:before"] += nominal

        flags = t.find("flags")
        if flags is not None and (tier in hoard_tiers or cat in hoard_cats):
            flags.set("count_in_hoarder", "1")

        if nominal > 0 and cat not in protected:
            f = pop.get(tier, 1.0) * phase.get("tiers", {}).get(tier, 1.0)
            f *= phase.get("categories", {}).get(cat, 1.0)
            new_nominal = max(1, round(nominal * f))
            new_min = min(new_nominal, max(0, round(minimum * f)))
            if minimum > 0:
                new_min = max(1, new_min)
            nom_el.text, min_el.text = str(new_nominal), str(new_min)
        stats[f"{label}:after"] += int(nom_el.text)
    return stats


def apply_globals(path: Path, values: dict) -> list[str]:
    """Set existing <var name=... value=...> entries; returns warnings for unknown names."""
    if not values:
        return []
    tree = ET.parse(path)
    found = {v.get("name"): v for v in tree.getroot().iter("var")}
    warnings = []
    for k, v in values.items():
        if k in found:
            found[k].set("value", str(v))
        else:
            warnings.append(f"globals.xml has no var '{k}'; not added")
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase")
    ap.add_argument("--date", help="pretend today is YYYY-MM-DD")
    ap.add_argument("--mission", default=str(ROOT / "server" / "mpmissions" /
                                             os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    cfg = yaml.safe_load(PRESET.read_text())
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    phase = pick_phase(cfg, a.phase, today)
    db = Path(a.mission) / "db"
    types, baseline = db / "types.xml", db / "types.xml.vanilla"
    if not types.exists():
        print(f"{types} not found: pull the server or start the local server once.", file=sys.stderr)
        return 2
    if not baseline.exists() and not a.dry_run:
        shutil.copy2(types, baseline)
        print(f"Saved pristine baseline {baseline.name} (commit it; it's the source of truth)")
    source = baseline if baseline.exists() else types

    tree = ET.parse(source)
    stats = scale_types(tree.getroot(), cfg, phase)
    print(f"Phase: {phase['name']} ({phase.get('story', '')})")
    print(f"Population factors for {cfg['expected_players']} players: {population_factors(cfg)}")
    for label in TIER_ORDER + ["untiered"]:
        b, af = stats[f"{label}:before"], stats[f"{label}:after"]
        if b:
            print(f"  {label:<9} nominal {b:>6} -> {af:>6} ({af / b:.0%})")
    if a.dry_run:
        print("(dry run, nothing written)")
        return 0
    ET.indent(tree, space="    ")
    tree.write(types, encoding="UTF-8", xml_declaration=True)
    print(f"Wrote {types}")
    for w in apply_globals(db / "globals.xml", cfg.get("globals") or {}):
        print("WARNING:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
