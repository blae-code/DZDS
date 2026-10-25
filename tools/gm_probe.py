#!/usr/bin/env python3
"""One-shot check that LM Studio + the GM prompt produce a valid payload.

Feeds a canned telemetry digest (or --digest FILE) to the model and prints the
validated JSON plus how long it took. It uses whichever gear LM Studio has loaded and
refuses (exit 2) unless that's the expected one (`pod.fish` loads Gemma 4 E4B): it never
names a model, so it can't make LM Studio load or evict anything.

Usage: tools/gm_probe.py [--expect gemma-4-e4b] [--digest FILE] [--runs 3]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import yaml

import active
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.llm import LMStudioGM  # noqa: E402

SAMPLE = """Players online: Buddy, Host
- Host last seen near Palace Town
- Buddy last seen near Palace Town
Faction fighting since last report:
- The Jackal Cohort killed 2 UN Peacekeeping Remnants near Southern Barracks
Recent events:
21:14:02 hit Host hp=71 by AI "Jackal" near Palace Town [ai_combat]
21:14:09 hit Host hp=38 by AI "Jackal" near Palace Town [ai_combat,health_drop]
21:14:30 hit Buddy hp=64 by Infected near Palace Town [infected]
21:15:11 unconscious Host near Palace Town"""


async def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--expect", default=os.environ.get("GM_LLM_EXPECT", "gemma-4-e4b"),
                    help="model key the loaded gear must match")
    ap.add_argument("--url", default=os.environ.get("LMSTUDIO_URL", "http://127.0.0.1:1234"))
    ap.add_argument("--digest", help="file containing a digest to send instead of the sample")
    ap.add_argument("--map", default=active.map_name())
    ap.add_argument("--runs", type=int, default=1)
    a = ap.parse_args()

    digest = Path(a.digest).read_text() if a.digest else SAMPLE
    locations = list(yaml.safe_load((ROOT / "maps" / f"{a.map}.yaml").read_text())["locations"])
    gm = LMStudioGM(a.url, expect=a.expect, timeout=180)
    failures = 0
    try:
        gear = await gm.resolve_gear()
        print(f"gear: {gm.gear_reason}")
        if not gear:
            return 2
        for i in range(a.runs):
            t0 = time.perf_counter()
            payload = await gm.decide(digest, locations)
            dt = time.perf_counter() - t0
            if payload is None:
                failures += 1
                print(f"run {i + 1}: FAILED after {dt:.1f}s (see warning above)")
            else:
                print(f"run {i + 1}: {dt:.1f}s\n{payload.model_dump_json(indent=2)}")
    finally:
        await gm.aclose()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
