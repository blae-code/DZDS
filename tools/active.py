#!/usr/bin/env python3
"""Which map and mission the tools act on.

GM_MAP / MISSION_NAME in the environment (or .env, which the Makefile exports) override the
repo default below. Change DEFAULT_MAP when the live server changes map.

Usage: tools/active.py map|mission
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAP = "chernarusplus"   # flipped to "nasdara" in Task 4, once maps/nasdara.yaml is complete


def map_name() -> str:
    return os.environ.get("GM_MAP") or DEFAULT_MAP


def map_data(name: str | None = None) -> dict:
    return yaml.safe_load((ROOT / "maps" / f"{name or map_name()}.yaml").read_text())


def mission_name(name: str | None = None) -> str:
    env = os.environ.get("MISSION_NAME")
    if env and name is None:
        return env
    return map_data(name)["mission"]


def mission_dir(name: str | None = None) -> Path:
    return ROOT / "server" / "mpmissions" / mission_name(name)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "map"
    print(map_name() if what == "map" else mission_name())
