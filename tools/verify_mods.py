#!/usr/bin/env python3
"""Check every mod in config/mods.yaml against the public Steam Workshop API.

Reports, per mod: whether the ID exists, is a DayZ (app 221100) item, isn't banned,
its Workshop title (to catch wrong IDs) and when it was last updated (to catch
abandoned mods that may break on game updates). No API key needed.

Usage: tools/verify_mods.py [--stale-months 18] [--all]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request

from modstring import load_mods

API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
DAYZ_APP = 221100


def fetch(ids: list[int]) -> dict[str, dict]:
    form = {"itemcount": str(len(ids))}
    form.update({f"publishedfileids[{i}]": str(x) for i, x in enumerate(ids)})
    req = urllib.request.Request(API, data=urllib.parse.urlencode(form).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        details = json.load(r)["response"]["publishedfiledetails"]
    return {d["publishedfileid"]: d for d in details}


def assess(mod: dict, d: dict | None, stale_s: float, now: float) -> tuple[str, str]:
    """Return (status, note). status: OK | STALE | CHECK | FAIL."""
    if not d or d.get("result") != 1:
        return "FAIL", "ID not found / private / removed"
    if d.get("consumer_app_id") != DAYZ_APP:
        return "FAIL", f"not a DayZ item (app {d.get('consumer_app_id')})"
    if d.get("banned"):
        return "FAIL", f"banned: {d.get('ban_reason')}"
    title = d.get("title", "")
    norm = lambda s: "".join(c for c in s.lower() if c.isalnum())  # noqa: E731
    if norm(mod["name"])[:6] not in norm(title) and norm(title)[:6] not in norm(mod["name"]):
        return "CHECK", f"title mismatch: Workshop says '{title}'"
    if now - d.get("time_updated", 0) > stale_s:
        return "STALE", "may be abandoned; test on current game version"
    return "OK", ""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stale-months", type=int, default=18)
    p.add_argument("--all", action="store_true", help="include disabled mods")
    args = p.parse_args()

    mods = [m for m in load_mods() if args.all or m.get("enabled", True)]
    details = fetch([m["id"] for m in mods])
    now, stale_s = time.time(), args.stale_months * 30 * 86400
    worst = 0
    rank = {"OK": 0, "STALE": 1, "CHECK": 1, "FAIL": 2}
    for m in mods:
        d = details.get(str(m["id"]))
        status, note = assess(m, d, stale_s, now)
        worst = max(worst, rank[status])
        updated = time.strftime("%Y-%m-%d", time.gmtime(d["time_updated"])) if d and d.get("time_updated") else "?"
        title = (d or {}).get("title", "?")
        print(f"{status:<6} {m['id']:<11} {updated}  {m['name'][:30]:<30} | {title[:40]:<40} {note}")
    print("\nOK = fine | STALE = not updated in a while | CHECK = verify by hand | FAIL = fix mods.yaml")
    return 1 if worst == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
