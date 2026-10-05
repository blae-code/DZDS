#!/usr/bin/env python3
"""Check every mod in config/mods.yaml against the public Steam Workshop API.

Reports, per mod: whether the ID exists, is a DayZ (app 221100) item, isn't banned,
its Workshop title (to catch wrong IDs) and when it was last updated (to catch
abandoned mods that may break on game updates). No API key needed.

With --deps it also reads each mod's Workshop page "Required items" and reports any
dependency that isn't enabled in mods.yaml.

Usage: tools/verify_mods.py [--stale-months 18] [--all] [--deps]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from modstring import load_mods

PAGE = "https://steamcommunity.com/sharedfiles/filedetails/?id="
API = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
DAYZ_APP = 221100


def fetch(ids: list[int]) -> dict[str, dict]:
    form = {"itemcount": str(len(ids))}
    form.update({f"publishedfileids[{i}]": str(x) for i, x in enumerate(ids)})
    req = urllib.request.Request(API, data=urllib.parse.urlencode(form).encode())
    with urllib.request.urlopen(req, timeout=30) as r:
        details = json.load(r)["response"]["publishedfiledetails"]
    return {d["publishedfileid"]: d for d in details}


CACHE = Path(__file__).resolve().parent.parent / "build" / "workshop_deps.json"
CACHE_TTL = 86400


def _get_page(mod_id: int) -> str:
    """Fetch a Workshop page politely: pause between requests, back off on HTTP 429."""
    for attempt in range(5):
        time.sleep(4)
        try:
            with urllib.request.urlopen(PAGE + str(mod_id), timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 4:
                raise
            wait = 30 * 2 ** attempt
            print(f"  (Steam rate limit; waiting {wait}s)", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError("unreachable")


def required_items(mod_id: int) -> list[int]:
    """Workshop 'Required items' for a mod (scraped from its page; cached for a day)."""
    try:
        cache = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    hit = cache.get(str(mod_id))
    if hit and time.time() - hit["at"] < CACHE_TTL:
        return hit["deps"]
    html = _get_page(mod_id)
    start = html.find('id="RequiredItems"')
    if start == -1:
        cache[str(mod_id)] = {"at": time.time(), "deps": []}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, indent=1))
        return []
    # The container holds only <a href=...id=N><div class="requiredItem">; stop at the
    # next section so links elsewhere on the page (e.g. "more from author") aren't counted.
    block = html[start:start + 8000]
    end = re.search(r'class="(rightSectionTopTitle|rightDetailsBlock|detailBox)', block)
    block = block[:end.start()] if end else block
    out: list[int] = []
    for m in re.finditer(r"filedetails/\?id=(\d+)", block):
        i = int(m.group(1))
        if i not in out and i != mod_id:
            out.append(i)
    cache[str(mod_id)] = {"at": time.time(), "deps": out}
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache, indent=1))
    return out


def check_deps(mods: list[dict]) -> int:
    mods = [m for m in mods if not m.get("local")]
    enabled = {m["id"] for m in mods if m.get("enabled", True)}
    by_id = {m["id"]: m for m in mods}
    missing: dict[int, list[str]] = {}
    unchecked: list[str] = []
    for m in mods:
        if not m.get("enabled", True):
            continue
        try:
            deps = required_items(m["id"])
        except (urllib.error.URLError, TimeoutError) as e:
            unchecked.append(f"{m['name']} ({e})")
            continue
        for dep in deps:
            if dep not in enabled:
                missing.setdefault(dep, []).append(m["name"])
    if unchecked:
        print(f"Dependencies: {len(unchecked)} mod(s) not checked (Steam rate limit); rerun later "
              f"to fill the cache:\n  " + "\n  ".join(unchecked))
    if not missing:
        print("Dependencies: all required Workshop items (of those checked) are enabled.")
        return 0
    titles = fetch(list(missing))
    print("Dependencies NOT enabled in mods.yaml:")
    for dep, needed_by in missing.items():
        title = titles.get(str(dep), {}).get("title", "?")
        state = " (listed but disabled)" if dep in by_id else ""
        print(f"  {dep:<11} {title[:40]:<40}{state}  <- {', '.join(needed_by)}")
    return 1


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
    p.add_argument("--deps", action="store_true", help="check Workshop 'Required items'")
    args = p.parse_args()

    mods = [m for m in load_mods() if (args.all or m.get("enabled", True)) and not m.get("local")]
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
    if args.deps:
        print()
        worst = max(worst, 2 * check_deps(load_mods()))
    return 1 if worst == 2 else 0


if __name__ == "__main__":
    sys.exit(main())
