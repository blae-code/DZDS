#!/usr/bin/env python3
"""Compile presets/diplomacy.yaml + the war ledger's automatic overrides into
server/profiles/DZDS/diplomacy.json for @DZDS.

Hand-written entries win over ledger entries for the same direction. Drops expired entries, translates preset faction names to @DZDS class names, and refuses
unknown factions. Usage: tools/diplomacy.py [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "server" / "profiles" / "DZDS" / "diplomacy.json"


def compile_overrides(diplomacy: dict, factions: dict, today: dt.date) -> list[dict]:
    names = {n: s["custom_faction"] for n, s in factions.items() if s.get("custom_faction")}
    out = []
    for e in diplomacy.get("overrides") or []:
        for side in ("from", "to"):
            if e[side] not in names:
                raise SystemExit(f"unknown faction '{e[side]}' (have {sorted(names)})")
        if e["stance"] not in ("friendly", "hostile"):
            raise SystemExit(f"stance must be friendly|hostile, got {e['stance']}")
        until = e.get("until")
        if until and dt.date.fromisoformat(str(until)) < today:
            continue
        out.append({"From": names[e["from"]], "To": names[e["to"]], "Friendly": e["stance"] == "friendly"})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    today = dt.date.fromisoformat(a.date) if a.date else dt.date.today()
    dip = yaml.safe_load((ROOT / "presets" / "diplomacy.yaml").read_text())
    factions = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())["factions"]
    manual = list(dip.get("overrides") or [])
    ledger_file = ROOT / "gm_state" / "war_ledger.json"
    auto = json.loads(ledger_file.read_text()).get("auto_diplomacy", []) if ledger_file.exists() else []
    taken = {(e["from"], e["to"]) for e in manual}
    merged = manual + [e for e in auto if (e["from"], e["to"]) not in taken]
    if auto:
        print(f"{len(auto)} override(s) from the war ledger")
    overrides = compile_overrides({"overrides": merged}, factions, today)
    for o in overrides:
        print(f"  {o['From']} -> {o['To']}: {'friendly' if o['Friendly'] else 'hostile'}")
    print(f"{len(overrides)} active override(s)")
    if not a.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"Overrides": overrides}, indent=4) + "\n")
        print(f"Wrote {OUT.relative_to(ROOT)} (push it; applies at next restart)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
