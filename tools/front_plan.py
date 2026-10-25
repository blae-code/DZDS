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
import sys
from pathlib import Path

import yaml

import active

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402


def load(rel: str):
    return active.load_yaml(rel)


def plan_traders(led: WarLedger, traders: dict) -> list[dict]:
    out = []
    for tid, t in traders["traders"].items():
        preferred = (t.get("sites") or {}).get(led.s.map)
        faction = t["faction"]
        candidates = sorted(s for s, h in led.s.control.items() if t["role"] in led.site_roles(s)
                            and (h == faction or (faction == "none" and h != "contested")))
        if faction == "none":
            # the smuggler only needs somewhere nobody is actively fighting over
            pref_ok = preferred and t["role"] in led.site_roles(preferred) and led.s.control.get(preferred) != "contested"
            status, site = ("open", preferred) if pref_ok else \
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
    wp = led.s.war_party
    raid_targets = {wp["target"]} if wp and wp["kind"] == "raid" else set()
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
        elif tgt.startswith("role:"):
            r = tgt.split(":", 1)[1]
            sites = [s for s in led.s.control.keys() if r in led.site_roles(s)]
        else:
            raise ValueError(f"unknown target {tgt}")
        if q.get("role"):
            sites = [s for s in sites if q["role"] in led.site_roles(s)]
        if q["giver"] == "none":
            giver_sites = [s for s, h in led.s.control.items() if "remote" in led.site_roles(s)] or sorted(led.s.control.keys())[:1]
        else:
            giver_sites = [s for s, h in led.s.control.items() if h == q["giver"]]
        if not giver_sites:
            continue  # the giving faction holds nothing: no quest giver exists
        locs = led.locations()
        for site in sorted(sites):
            if site not in locs:
                continue
            gx, gz = locs[site][:2]
            giver_at = min(giver_sites, key=lambda s: (locs[s][0] - gx) ** 2 + (locs[s][1] - gz) ** 2)
            title = q.get("title", qid.replace("_", " ").title()).format(site=site)
            desc = [d.format(site=site) for d in q.get("descriptions", [q["text"].format(site=site)])]
            out.append({"quest": qid, "id": q.get("id", 100), "title": title, "objective": q["objective"],
                        "site": site, "giver": q["giver"], "giver_site": giver_at,
                        "text": q["text"].format(site=site), "descriptions": desc,
                        "rewards": q.get("rewards", []),
                        "reputation_rewards": q.get("reputation_rewards", {}),
                        "unlocks_trader": q.get("unlocks_trader", ""),
                        "ledger_impact": q.get("ledger_impact", {}),
                        "items_required": q.get("items_required", []),
                        "cancel_on_death": q.get("cancel_on_death", True),
                        "repeatable": q.get("repeatable", True),
                        "daily": q.get("daily", False)})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=active.map_name())
    ap.add_argument("--initial", action="store_true", help="ignore the ledger state")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--color", action="store_true", help="force rich ANSI output")
    ap.add_argument("--plain", action="store_true", help="force plain output")
    a = ap.parse_args()
    import ui
    rich = True if a.color else False if a.plain else ui.use_color()
    led = WarLedger.load_or_new(a.map, initial=a.initial)
    plan = {"turn": led.s.turn, "traders": plan_traders(led, load("presets/traders.yaml")),
            "quests": plan_quests(led, load("presets/quests.yaml"))}
    if rich:
        print(ui.banner(f"FRONT PLAN · {a.map.upper()}", subtitle=f"Barter Traders & Front-Line Quests  │  Turn {led.s.turn}", right=f"{len(plan['quests'])} QUESTS", width=96, enabled=True))
        t_rows = [[ui.badge(t["status"].upper(), t["status"].upper(), enabled=True), t["display"], t["site"] or "—"] for t in plan["traders"]]
        print(ui.table(["STATUS", "TRADER", "CURRENT SITE"], t_rows, title="FACTION BARTER TRADERS", enabled=True))
        q_rows = [[ui.fg(q["quest"], "bone", bold=True, enabled=True), q["site"], ui.faction_tag(q["giver"], enabled=True), q["giver_site"], q["text"][:46] + ("…" if len(q["text"]) > 46 else "")] for q in plan["quests"]]
        print(ui.table(["QUEST", "TARGET SITE", "GIVER", "AT SITE", "BRIEFING"], q_rows, title=f"LIVE QUESTS ({len(plan['quests'])})", enabled=True))
    else:
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
        import campaign_gen
        c_stats = campaign_gen.compile_campaign(a.map, led, plan, dry_run=False)
        print(f"  compiled campaign: {c_stats['quests']} quest(s), {c_stats['npcs']} NPC(s), "
              f"{c_stats['traders']} trader(s), {c_stats['dialogues']} dialogue(s)")
    else:
        import campaign_gen
        c_stats = campaign_gen.compile_campaign(a.map, led, plan, dry_run=True)
        print(f"  [dry-run] campaign: {c_stats['quests']} quest(s), {c_stats['npcs']} NPC(s), "
              f"{c_stats['traders']} trader(s), {c_stats['dialogues']} dialogue(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
