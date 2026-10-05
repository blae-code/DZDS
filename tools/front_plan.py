#!/usr/bin/env python3
"""Plan which traders are open and which quests are live, from the war ledger.

Writes build/front_plan.<map>.json:
  traders: open / relocated / closed, with their current site
  quests:  live instances of presets/quests.yaml templates at current front-line sites

Usage: tools/front_plan.py [--map chernarusplus] [--initial] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402


def load(rel: str):
    return yaml.safe_load((ROOT / rel).read_text())


def plan_traders(led: WarLedger, traders: dict) -> list[dict]:
    out = []
    for tid, t in traders["traders"].items():
        preferred = (t.get("sites") or {}).get(led.s.map)
        faction = t["faction"]
        candidates = sorted(s for s, h in led.s.control.items() if t["role"] in led.site_roles(s)
                            and (h == faction or (faction == "none" and h != "contested")))
        if faction == "none":
            # the smuggler only needs somewhere nobody is actively fighting over
            status, site = ("open", preferred) if preferred in candidates else \
                           ("relocated", candidates[0]) if candidates else ("closed", None)
        elif preferred and led.s.control.get(preferred) == faction:
            status, site = "open", preferred
        elif candidates:
            status, site = "relocated", candidates[0]
        else:
            status, site = "closed", None
        out.append({"trader": tid, "display": t["display"], "status": status, "site": site})
    return out


def plan_quests(led: WarLedger, quests: dict) -> list[dict]:
    out = []
    raid_targets = {r["target"] for r in led.s.raids}
    for qid, q in quests["templates"].items():
        req = q.get("requires_standing") or {}
        if any(led.s.standing.get(f, 0) < v for f, v in req.items()):
            continue
        tgt = q["target"]
        if tgt == "contested":
            sites = [s for s, h in led.s.control.items() if h == "contested"]
        elif tgt == "raid_target":
            sites = sorted(raid_targets)
        elif tgt.startswith("held_by:"):
            sites = [s for s, h in led.s.control.items() if h == tgt.split(":", 1)[1]]
        else:
            raise ValueError(f"unknown target {tgt}")
        if q.get("role"):
            sites = [s for s in sites if q["role"] in led.site_roles(s)]
        giver_sites = [s for s, h in led.s.control.items() if h == q["giver"]]
        if not giver_sites:
            continue  # the giving faction holds nothing: no quest giver exists
        locs = led.locations()
        for site in sorted(sites):
            if site not in locs:
                continue
            gx, gz = locs[site][:2]
            giver_at = min(giver_sites, key=lambda s: (locs[s][0] - gx) ** 2 + (locs[s][1] - gz) ** 2)
            out.append({"quest": qid, "objective": q["objective"], "site": site,
                        "giver": q["giver"], "giver_site": giver_at, "text": q["text"].format(site=site)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=os.environ.get("GM_MAP", "chernarusplus"))
    ap.add_argument("--initial", action="store_true", help="ignore the ledger state")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    led = WarLedger.new(a.map) if a.initial or not STATE.exists() else WarLedger.load(a.map)
    plan = {"turn": led.s.turn, "traders": plan_traders(led, load("presets/traders.yaml")),
            "quests": plan_quests(led, load("presets/quests.yaml"))}
    for t in plan["traders"]:
        print(f"  trader {t['display']:<42} {t['status']:<9} {t['site'] or '-'}")
    print(f"  {len(plan['quests'])} live quest(s)")
    for q in plan["quests"]:
        print(f"    {q['quest']:<20} at {q['site']:<20} from {q['giver']} @ {q['giver_site']}")
    if not a.dry_run:
        out = ROOT / "build" / f"front_plan.{a.map}.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps(plan, indent=2) + "\n")
        print(f"Wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
