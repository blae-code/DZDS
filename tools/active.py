#!/usr/bin/env python3
"""Which map and mission the tools act on.

GM_MAP / MISSION_NAME in the environment (or .env, which the Makefile exports) override the
repo default below. Change DEFAULT_MAP when the live server changes map.

Usage: tools/active.py map|mission
"""
from __future__ import annotations

import copy
import os
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAP = "nasdara"   # flipped from chernarusplus 2026-10-15 (Task 4, Badlands relaunch)

_YAML_CACHE: dict[Path, tuple[int, int, object]] = {}


def load_yaml(rel_or_path: str | Path):
    """Mtime-cached YAML loader returning a fresh copy so callers may mutate safely."""
    path = Path(rel_or_path)
    if not path.is_absolute():
        path = ROOT / path
    st = path.stat()
    hit = _YAML_CACHE.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return copy.deepcopy(hit[2])
    parsed = yaml.safe_load(path.read_text())
    _YAML_CACHE[path] = (st.st_mtime_ns, st.st_size, parsed)
    return copy.deepcopy(parsed)


def register_ce_file(core: Path, file_name: str, file_type: str, folder: str = "dzds") -> bool:
    """Register `<file name="..." type="..." />` inside `<ce folder="...">` in cfgeconomycore.xml.

    Creates a `.xml.bak` backup when modifying `core`. Returns True if modified, False if already present.
    """
    text = core.read_text()
    if f'name="{file_name}"' in text:
        return False
    snippet = f'    <ce folder="{folder}">\n        <file name="{file_name}" type="{file_type}" />\n    </ce>\n'
    if "</economycore>" not in text:
        raise SystemExit(f"{core} has no </economycore>; add manually:\n{snippet}")
    shutil.copy2(core, core.with_suffix(".xml.bak"))
    block = f'<ce folder="{folder}">'
    if block in text:
        text = text.replace(block, block + f'\n        <file name="{file_name}" type="{file_type}" />', 1)
    else:
        text = text.replace("</economycore>", snippet + "</economycore>", 1)
    core.write_text(text)
    return True


def map_name() -> str:
    return os.environ.get("GM_MAP") or DEFAULT_MAP


def map_data(name: str | None = None) -> dict:
    return load_yaml(ROOT / "maps" / f"{name or map_name()}.yaml")


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
