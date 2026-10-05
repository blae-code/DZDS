#!/usr/bin/env python3
"""One-shot check that Ollama + the GM prompt produce a valid payload.

Feeds a canned telemetry digest (or --digest FILE) to the model and prints the
validated JSON plus how long it took. Use it to compare models, tune the prompt, and
confirm ROCm is working before anything else is wired up.

Usage: tools/gm_probe.py [--model gemma4:e4b] [--digest FILE] [--runs 3]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.llm import OllamaGM  # noqa: E402

SAMPLE = """Players online: Buddy, Host
- Host last seen near Stary Sobor
- Buddy last seen near Stary Sobor
Recent events:
21:14:02 hit Host hp=71 by Player "eAI Raider" near Stary Sobor [ai_combat]
21:14:09 hit Host hp=38 by Player "eAI Raider" near Stary Sobor [ai_combat,health_drop]
21:14:30 hit Buddy hp=64 by Infected near Stary Sobor [infected]
21:15:11 unconscious Host near Stary Sobor"""


async def main() -> int:
    load_dotenv(ROOT / ".env")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "gemma4:e4b"))
    ap.add_argument("--url", default=os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"))
    ap.add_argument("--digest", help="file containing a digest to send instead of the sample")
    ap.add_argument("--map", default=os.environ.get("GM_MAP", "chernarusplus"))
    ap.add_argument("--runs", type=int, default=1)
    a = ap.parse_args()

    digest = Path(a.digest).read_text() if a.digest else SAMPLE
    locations = list(yaml.safe_load((ROOT / "maps" / f"{a.map}.yaml").read_text())["locations"])
    gm = OllamaGM(a.url, a.model, timeout=180)
    failures = 0
    try:
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
