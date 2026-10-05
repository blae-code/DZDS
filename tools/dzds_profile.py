#!/usr/bin/env python3
"""Write @DZDS profile files from presets/world.yaml and the war ledger.

  server/profiles/DZDS/settings.json  spawn allowlist + poll interval
  server/profiles/DZDS/markers.json   site markers by current holder (null classnames skipped)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "server" / "profiles" / "DZDS"
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import STATE, WarLedger  # noqa: E402


def settings(world: dict) -> dict:
    allowed = sorted({c for a in world["gm_actions"].values() for c in a.get("classnames") or []})
    return {"AllowedClassNames": allowed, "PollSeconds": int(world.get("poll_seconds", 10)),
            "ToleranceReputation": int(world.get("tolerance_reputation", 0))}


def markers(world: dict, led: WarLedger) -> list[dict]:
    m = world["markers"]
    dx, dz = m["offset"]
    locs = led.locations()
    out = []
    for site, holder in sorted(led.s.control.items()):
        cls = (m["by_holder"] or {}).get(holder)
        if not cls or site not in locs:
            continue
        x, z = locs[site][:2]
        out.append({"ClassName": cls, "X": float(x + dx), "Z": float(z + dz), "Yaw": 0.0})
    return out


def main() -> int:
    world = yaml.safe_load((ROOT / "presets" / "world.yaml").read_text())
    map_name = os.environ.get("GM_MAP", "chernarusplus")
    led = WarLedger.load(map_name) if STATE.exists() else WarLedger.new(map_name)
    OUT.mkdir(parents=True, exist_ok=True)
    s, mk = settings(world), markers(world, led)
    (OUT / "settings.json").write_text(json.dumps(s, indent=4) + "\n")
    (OUT / "markers.json").write_text(json.dumps({"Markers": mk}, indent=4) + "\n")
    print(f"@DZDS profile: {len(s['AllowedClassNames'])} allowlisted classname(s), {len(mk)} marker(s)"
          + ("" if mk else " (marker classnames not chosen yet: presets/world.yaml)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
