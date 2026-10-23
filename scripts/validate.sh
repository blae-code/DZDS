#!/usr/bin/env bash
# Syntax-check every JSON and XML config under server/ and presets/ (spec §6B).
# Exits non-zero if anything fails. Usage: scripts/validate.sh [paths...]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ $# -eq 0 ]] && set -- server presets

command -v xmllint >/dev/null || { echo "xmllint missing: sudo pacman -S libxml2"; exit 2; }
PY="$ROOT/.venv/bin/python"
[[ -x "$PY" ]] || PY="python3"

# VPPMapAirdrop.json: written by VPPAdminTools in its own non-JSON format ("{...},{...}" with
# no enclosing array, bare backslash paths). Mod-owned admin-map data; we never edit or push it.
find "$@" -type f \( -iname '*.json' -o -iname '*.xml' \) \
  -not -path '*/storage_*/*' \
  -not -name 'VPPMapAirdrop.json' \
  -print0 2>/dev/null | "$PY" -c '
import json, subprocess, sys
from pathlib import Path

raw = sys.stdin.buffer.read().split(b"\0")
files = [f.decode("utf-8", "surrogateescape") for f in raw if f]
count = len(files)
fail = 0
xml_files = []

for f in files:
    low = f.lower()
    if low.endswith(".json"):
        try:
            with open(f, "rb") as fp:
                json.load(fp)
        except Exception as exc:
            print(f"JSON FAIL  {f}")
            print(f"  {exc}")
            fail += 1
    elif low.endswith(".xml"):
        xml_files.append(f)

if xml_files:
    res = subprocess.run(["xmllint", "--noout", *xml_files], capture_output=True, text=True)
    if res.returncode != 0:
        for f in xml_files:
            r = subprocess.run(["xmllint", "--noout", f], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"XML  FAIL  {f}")
                for ln in (r.stderr or r.stdout).splitlines():
                    print(f"  {ln}")
                fail += 1

print(f"Checked {count} file(s), {fail} failure(s).")
sys.exit(0 if fail == 0 else 1)
'
