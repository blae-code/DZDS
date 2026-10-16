#!/usr/bin/env bash
# Prepare a Steam Workshop upload of @DZDS (Public) and print the steamcmd command to run.
#
#   scripts/publish_dzds.sh "first release"     # rebuild, write build/workshop_dzds.vdf
#   ~/steamcmd/steamcmd.sh +login <you> +workshop_build_item <vdf> +quit   # Blae: his login
#   scripts/publish_dzds.sh --record            # after the first upload: save the item ID
#
# steamcmd is Valve's tarball in ~/steamcmd (no AUR package needed). It writes the new item's ID back into the .vdf on the first upload; --record copies it
# to mods/workshop/publishedfileid (tracked), so later uploads update the same item.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
W="$ROOT/mods/workshop"
VDF="$ROOT/build/workshop_dzds.vdf"
IDFILE="$W/publishedfileid"

if [[ "${1:-}" == "--record" ]]; then
  id=$(grep -oP '"publishedfileid"\s*"\K[0-9]+' "$VDF")
  [[ "$id" != "0" ]] || { echo "No ID in $VDF yet: did the upload succeed?"; exit 1; }
  echo "$id" > "$IDFILE"
  echo "Recorded Workshop item $id in $IDFILE"
  exit 0
fi

note="${1:?usage: scripts/publish_dzds.sh \"change note\" | --record}"
"$ROOT/scripts/build_dzds.sh"
id=$(cat "$IDFILE" 2>/dev/null || echo 0)   # build_dzds.sh already wrote mod.cpp + meta.cpp
desc=$(sed 's/"/'"'"'/g' "$W/description.txt")
{
  printf '"workshopitem"\n{\n'
  printf '\t"appid"\t\t"221100"\n'
  printf '\t"publishedfileid"\t"%s"\n' "$id"
  printf '\t"contentfolder"\t"%s"\n' "$ROOT/build/@DZDS"
  printf '\t"previewfile"\t"%s"\n' "$W/preview.png"
  printf '\t"visibility"\t"0"\n'            # 0 public (Blae 2026-10-08: DZGUI cannot see unlisted), 3 unlisted
  printf '\t"title"\t\t"Ad Aspera Factions (DZDS)"\n'
  printf '\t"description"\t"%s"\n' "$desc"
  printf '\t"changenote"\t"%s"\n' "${note//\"/\'}"
  printf '}\n'
} > "$VDF"

# The private key must never be in the uploaded folder.
if find "$ROOT/build/@DZDS" -name '*.biprivatekey' | grep -q .; then echo "ABORT: private key in content folder"; exit 1; fi

echo
echo "Upload folder:"; find "$ROOT/build/@DZDS" -type f -printf '  %P\n'
echo
echo "Run (logs in as you; Steam Guard may ask for a code). It knocks your desktop Steam client"
echo "offline (one session per account): use Steam > Go Online, or restart Steam, afterwards."
echo "  ~/steamcmd/steamcmd.sh +login <your steam username> +workshop_build_item $VDF +quit"
[[ "$id" == "0" ]] && echo "Then: scripts/publish_dzds.sh --record"
