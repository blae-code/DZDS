#!/usr/bin/env python3
"""Search the DayZ Steam Workshop and show candidate IDs with title, subscribers, last update.

Usage: tools/find_mod.py "DayZ-Expansion-AI" [-n 8]
"""
from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.parse
import urllib.request

from verify_mods import fetch

SEARCH = "https://steamcommunity.com/workshop/browse/?appid=221100&browsesort=textsearch&searchtext="


def search(query: str, n: int = 8) -> list[dict]:
    with urllib.request.urlopen(SEARCH + urllib.parse.quote(query), timeout=30) as r:
        html = r.read().decode("utf-8", "replace")
    ids: list[int] = []
    for m in re.finditer(r"filedetails/\?id=(\d+)", html):
        i = int(m.group(1))
        if i not in ids:
            ids.append(i)
    if not ids:
        return []
    details = fetch(ids[:n])
    out = [details[str(i)] for i in ids[:n] if details.get(str(i), {}).get("result") == 1]
    return sorted(out, key=lambda d: d.get("subscriptions", 0), reverse=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query")
    p.add_argument("-n", type=int, default=8)
    args = p.parse_args()
    for d in search(args.query, args.n):
        upd = time.strftime("%Y-%m-%d", time.gmtime(d.get("time_updated", 0)))
        print(f"{d['publishedfileid']:<11} {upd}  subs={d.get('subscriptions', 0):>9,}  {d.get('title', '')[:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
