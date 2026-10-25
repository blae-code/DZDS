#!/usr/bin/env python3
"""Which server/ files a restart cycle changed, by content (not mtime).

`make cycle` pulls the live server into server/, snapshots every config file's hash, runs
`make prepare-restart`, then pushes exactly the files whose content changed. A full `make push`
uploads every file newer than the server's copy, which on 2026-10-22/23 included a dozen files
newer only by mtime and would have overwritten live quest state.

Usage:
  tools/cycle.py snapshot [--out build/cycle_before.json]
  tools/cycle.py changed  [--before build/cycle_before.json] [--out build/changed.txt]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import active

ROOT = active.ROOT
SKIP_SUFFIXES = {".ADM", ".RPT", ".log", ".mdmp", ".bak"}


def config_files() -> list[Path]:
    """Config files of the active mission and profiles: tracked or new, never gitignored runtime."""
    roots = [ROOT / "server" / "profiles", active.mission_dir()]
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "--cached", "--others", "--exclude-standard",
                          "-z", "--", *[str(r.relative_to(ROOT)) for r in roots]],
                         capture_output=True, check=True).stdout.decode()
    files = []
    for rel in filter(None, out.split("\0")):
        p = ROOT / rel
        if p.is_file() and p.suffix not in SKIP_SUFFIXES and not p.name.endswith(".bak"):
            files.append(p)
    return sorted(files)


def digest(p: Path) -> str:
    """Content hash. XML is canonicalised first: the server rewrites some files at every boot
    (save_types_startup) with other quoting and spacing, which is not a change worth a push."""
    data = p.read_bytes()
    if p.suffix == ".xml":
        try:
            data = ET.canonicalize(data.decode("utf-8-sig"), strip_text=True).encode()
        except (ET.ParseError, UnicodeDecodeError):
            pass
    return hashlib.sha256(data).hexdigest()


def snapshot() -> dict[str, str]:
    return {str(p.relative_to(ROOT)): digest(p) for p in config_files()}


def changed(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """New or modified files. Deletions are never pushed (push never deletes remotely)."""
    return sorted(rel for rel, h in after.items() if before.get(rel) != h)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("what", choices=["snapshot", "changed"])
    ap.add_argument("--before", default="build/cycle_before.json")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    if a.what == "snapshot":
        out = ROOT / (a.out or a.before)
        out.parent.mkdir(parents=True, exist_ok=True)
        snap = snapshot()
        out.write_text(json.dumps(snap, indent=1, sort_keys=True) + "\n")
        print(f"snapshot: {len(snap)} config files -> {out.relative_to(ROOT)}")
        return 0
    before = json.loads((ROOT / a.before).read_text())
    files = changed(before, snapshot())
    out = ROOT / (a.out or "build/changed.txt")
    out.write_text("".join(f + "\n" for f in files))
    print(f"{len(files)} changed file(s) -> {out.relative_to(ROOT)}")
    for f in files:
        print(f"  {f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
