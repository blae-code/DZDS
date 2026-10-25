#!/usr/bin/env python3
"""Keep the mission's loot economy at vanilla (Blae, 2026-10-15: no phases, no scaling).

Regenerates <mission>/db/types.xml AND every modded types file registered in
cfgeconomycore.xml from pristine baselines (<file>.vanilla, created on first run), changing
only the lifetime of vehicle classes init.c spawns (refugee arrivals), and applies `globals:`
to db/globals.xml. Our own items (the "dzds" folder from tools/types_gen.py) are never touched.

Usage: tools/economy.py [--mission DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import yaml

import active

ROOT = active.ROOT
PRESET = ROOT / "presets" / "economy.yaml"
ARRIVALS = ROOT / "presets" / "arrivals.yaml"
SKIP_FOLDERS = {"dzds", "dzds_mods"}   # ours: types_gen.py and mod_ce.py regenerate them


def lifetime_overrides(cfg: dict) -> dict[str, int]:
    """Type name -> lifetime (s) for vehicles init.c spawns outside the CE's events."""
    life = cfg.get("script_vehicle_lifetime")
    if not life or not ARRIVALS.exists():
        return {}
    vehicles = yaml.safe_load(ARRIVALS.read_text()).get("vehicles") or []
    return {v["class"]: int(life) for v in vehicles}


def apply_lifetimes(root: ET.Element, overrides: dict[str, int]) -> int:
    """Set <lifetime> on the named types present in this file. Returns how many were set."""
    n = 0
    for t in root.findall("type"):
        life = overrides.get(t.get("name"))
        el = t.find("lifetime")
        if life is not None and el is not None:
            el.text = str(life)
            n += 1
    return n


def types_files(mission: Path) -> list[Path]:
    """db/types.xml plus modded types files registered in cfgeconomycore.xml."""
    files = [mission / "db" / "types.xml"]
    core = mission / "cfgeconomycore.xml"
    if core.exists():
        for ce in ET.parse(core).getroot().iter("ce"):
            folder = ce.get("folder", "")
            if folder in SKIP_FOLDERS:
                continue
            for f in ce.findall("file"):
                if f.get("type") == "types":
                    files.append(mission / folder / f.get("name"))
    return files


def canonical(path: Path) -> str:
    return ET.canonicalize(from_file=str(path), strip_text=True)


def is_fresh_vanilla(path: Path, baseline: Path, overrides: dict[str, int]) -> bool:
    """True when `path` is a vanilla types file newer than our baseline: it carries none of our
    lifetimes and differs from the baseline. A DayZ update replaces the mission's db/types.xml
    with its own (2026-10-21, 1.30.164200: live had Ayran nominal 50 and vehicle lifetime 3 again),
    and the pull brings that file down."""
    root = ET.parse(path).getroot()
    ours = [t for t in root.findall("type") if t.get("name") in overrides]
    if not ours or any((t.findtext("lifetime") or "").strip() == str(overrides[t.get("name")]) for t in ours):
        return False
    return canonical(path) != canonical(baseline)


def process(path: Path, cfg: dict, dry_run: bool) -> Counter | None:
    baseline = path.with_name(path.name + ".vanilla")
    if not path.exists():
        print(f"  (missing {path}; skipped)")
        return None
    if not baseline.exists() and not dry_run:
        shutil.copy2(path, baseline)
        print(f"  saved pristine baseline {baseline.name} (commit it)")
    elif baseline.exists() and is_fresh_vanilla(path, baseline, lifetime_overrides(cfg)):
        print(f"  {path.name} is a newer vanilla file (game update): adopted as {baseline.name} (commit it)")
        if not dry_run:
            shutil.copy2(path, baseline)
    tree = ET.parse(baseline if baseline.exists() else path)
    stats: Counter = Counter()
    stats["lifetime"] = apply_lifetimes(tree.getroot(), lifetime_overrides(cfg))
    if not dry_run:
        ET.indent(tree, space="    ")
        tree.write(path, encoding="UTF-8", xml_declaration=True)
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
    ap.add_argument("--mission")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load(PRESET.read_text())
    mission = Path(a.mission) if a.mission else active.mission_dir()
    if not (mission / "db" / "types.xml").exists():
        print(f"{mission / 'db' / 'types.xml'} not found.", file=sys.stderr)
        return 2
    total: Counter = Counter()
    for path in types_files(mission):
        print(f"- {path.relative_to(mission)}")
        stats = process(path, cfg, a.dry_run)
        if stats:
            total.update(stats)
    over = lifetime_overrides(cfg)
    print(f"vanilla economy; script-spawned vehicle lifetime set on {total['lifetime']} type(s) "
          f"for {len(over)} arrival class(es)")
    # Modded arrival vehicles live in dzds/types_dzds.xml (tools/types_gen.py), not here.
    known = set()
    for f in [*types_files(mission), *sorted((mission / "dzds").glob("types*.xml"))]:
        if f.exists():
            known |= {t.get("name") for t in ET.parse(f).getroot().findall("type")}
    missing = sorted(set(over) - known)
    if missing:
        print(f"WARNING: arrival vehicle(s) in no types file; the CE will not keep them: {', '.join(missing)}")
    if a.dry_run:
        print("(dry run, nothing written)")
        return 0
    for w in apply_globals(mission / "db" / "globals.xml", cfg.get("globals") or {}):
        print("WARNING:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
