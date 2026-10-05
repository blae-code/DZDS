#!/usr/bin/env bash
# EXPERIMENTAL: run a DayZ dedicated server on this PC to test mods/configs before
# renting a GSP. Uses Bohemia's Linux server build (steamcmd app 223350).
#
#   scripts/local_server.sh install   # steamcmd download (needs a Steam login that owns DayZ)
#   scripts/local_server.sh mods      # symlink subscribed workshop mods + copy .bikeys
#   scripts/local_server.sh start     # run with the mods.yaml load order
#
# Profiles are written to the repo's server/profiles, and the mission is linked from
# server/mpmissions, so configs you tune here (e.g. Expansion AI files generated on first
# boot) carry straight over to the GSP with `make push`.
#
# Known caveats (see docs/PRE_PURCHASE.md): the Linux server is less battle-tested
# than Windows, some mods misbehave on it (often filename case), and it competes with the
# DayZ client for RAM. If a mod fails only here, retest it on the GSP before dropping it.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ -f .env ]] && { set -a; source .env; set +a; }

SERVER_DIR="${LOCAL_SERVER_DIR:-$HOME/dayz-server}"
WORKSHOP="${DAYZ_WORKSHOP_DIR:-$HOME/.local/share/Steam/steamapps/workshop/content/221100}"
MISSION="${MISSION_NAME:-dayzOffline.chernarusplus}"
PY="$ROOT/.venv/bin/python"

install() {
  command -v steamcmd >/dev/null || { echo "Install steamcmd: yay -S steamcmd (AUR)"; exit 2; }
  : "${STEAM_USER:?set STEAM_USER in .env (account must own DayZ; Steam Guard will prompt)}"
  steamcmd +force_install_dir "$SERVER_DIR" +login "$STEAM_USER" +app_update 223350 validate +quit
}

mods() {
  [[ -d "$WORKSHOP" ]] || { echo "Workshop dir not found: $WORKSHOP"; exit 2; }
  mkdir -p "$SERVER_DIR/keys"
  local missing=0
  while read -r side id folder; do
    if [[ ! -d "$WORKSHOP/$id" ]]; then
      echo "NOT SUBSCRIBED  $folder ($id): https://steamcommunity.com/sharedfiles/filedetails/?id=$id"
      missing=1; continue
    fi
    ln -sfn "$WORKSHOP/$id" "$SERVER_DIR/@$id"
    find "$WORKSHOP/$id" -iname '*.bikey' -exec cp -f {} "$SERVER_DIR/keys/" \;
  done < <("$PY" tools/modstring.py ids)
  echo "Linked mods into $SERVER_DIR as @<workshop id>; keys copied to $SERVER_DIR/keys"
  return $missing
}

start() {
  [[ -x "$SERVER_DIR/DayZServer" ]] || { echo "Server not installed; run: $0 install"; exit 2; }
  # Seed the repo mission from the vanilla one on first run, then link it in.
  if [[ ! -d "server/mpmissions/$MISSION" ]]; then
    echo "Seeding server/mpmissions/$MISSION from the server install"
    cp -r "$SERVER_DIR/mpmissions/$MISSION" "server/mpmissions/"
  fi
  if [[ ! -L "$SERVER_DIR/mpmissions/$MISSION" ]]; then
    mv "$SERVER_DIR/mpmissions/$MISSION" "$SERVER_DIR/mpmissions/$MISSION.vanilla" 2>/dev/null || true
    ln -sfn "$ROOT/server/mpmissions/$MISSION" "$SERVER_DIR/mpmissions/$MISSION"
  fi
  sed "s/__MISSION__/$MISSION/" config/local_serverDZ.cfg > "$SERVER_DIR/serverDZ.cfg"

  local client="" server=""
  while read -r side id folder; do
    [[ -d "$SERVER_DIR/@$id" ]] || { echo "skip $folder (not linked; run: $0 mods)"; continue; }
    if [[ "$side" == "server" ]]; then server+="@$id;"; else client+="@$id;"; fi
  done < <("$PY" tools/modstring.py ids)

  mkdir -p server/profiles
  cd "$SERVER_DIR"
  echo "Starting DayZ server: connect from the DayZ launcher to 127.0.0.1:2302"
  exec ./DayZServer -config=serverDZ.cfg -port=2302 -profiles="$ROOT/server/profiles" \
       -dologs -adminlog -netlog -freezecheck "-mod=$client" "-serverMod=$server"
}

case "${1:-}" in
  install) install ;;
  mods) mods ;;
  start) start ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
