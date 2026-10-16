#!/usr/bin/env bash
# Write @DZDS's mod.cpp and meta.cpp into a content folder (default build/@DZDS).
#
#   scripts/dzds_meta.sh [folder]
#
# meta.cpp carries the Workshop ID. The server advertises each mod's ID from it; without it
# @DZDS is advertised as ID 0, and one 0 makes Steam reject launchers' whole batch lookup
# (HTTP 400), so DZGUI marks mods "Invalid". DayZ Tools' Publisher writes this file; steamcmd
# does not. It lived only in publish_dzds.sh, so a build uploaded straight from build_dzds.sh
# shipped without it twice (2026-10-08, 2026-10-16); build_dzds.sh now calls this.
# Timestamp is a Windows FILETIME, like the launcher's.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W="$ROOT/mods/workshop"
OUT="${1:-$ROOT/build/@DZDS}"

cp "$W/mod.cpp" "$OUT/mod.cpp"
id=$(cat "$W/publishedfileid" 2>/dev/null || echo 0)
if [[ "$id" != "0" ]]; then
  printf 'protocol = 1;\npublishedid = %s;\nname = "Ad Aspera Factions (DZDS)";\ntimestamp = %s;\n' \
    "$id" "$(( ($(date +%s) + 11644473600) * 10000000 ))" > "$OUT/meta.cpp"
fi
