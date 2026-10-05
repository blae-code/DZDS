#!/usr/bin/env bash
# Syntax-check every JSON and XML config under server/ and presets/ (spec §6B).
# Exits non-zero if anything fails. Usage: scripts/validate.sh [paths...]
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ $# -eq 0 ]] && set -- server presets

command -v xmllint >/dev/null || { echo "xmllint missing: sudo pacman -S libxml2"; exit 2; }

fail=0; count=0
while IFS= read -r -d '' f; do
  count=$((count + 1))
  case "${f,,}" in
    *.json)
      if ! err=$(python3 -m json.tool "$f" 2>&1 >/dev/null); then
        echo "JSON FAIL  $f"; echo "  $err"; fail=$((fail + 1))
      fi ;;
    *.xml)
      if ! err=$(xmllint --noout "$f" 2>&1); then
        echo "XML  FAIL  $f"; echo "$err" | sed 's/^/  /'; fail=$((fail + 1))
      fi ;;
  esac
done < <(find "$@" -type f \( -iname '*.json' -o -iname '*.xml' \) \
           -not -path '*/storage_*/*' -print0 2>/dev/null)

echo "Checked $count file(s), $fail failure(s)."
[[ $fail -eq 0 ]]
