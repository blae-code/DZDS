#!/usr/bin/env bash
# SFTP sync between the GSP and the local mirror in server/.
#
#   scripts/sync.sh pull            # remote profiles/ + mpmissions/ -> server/
#   scripts/sync.sh push            # validate -> snapshot remote to backups/ -> upload
#   scripts/sync.sh push-files LIST # validate -> back up those remote files -> upload exactly them
#   scripts/sync.sh logs            # pull only *.ADM / *.RPT into server/profiles (for debugging)
#   scripts/sync.sh push-excludes   # print what push leaves out (everything git ignores under server/)
#   DRY_RUN=1 scripts/sync.sh push  # show what would change, upload nothing
#
# Requires: lftp (CachyOS: sudo pacman -S lftp). Credentials come from .env.
# Push never deletes remote files and only uploads files newer than the remote copy.
# Push uploads only the active mission and never anything .gitignore marks as runtime
# (ATM balances, player data, admin logs, the server's own users/ profile, arrival ledger):
# a local test boot rewrites those, and uploading them would overwrite live player state.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

[[ -f .env ]] || { echo "Missing .env (copy .env.example)"; exit 2; }
set -a; source .env; set +a
command -v lftp >/dev/null || { echo "lftp not installed: sudo pacman -S lftp"; exit 2; }

: "${SFTP_HOST:?}" "${SFTP_USER:?}" "${SFTP_PASSWORD:?}"
SFTP_PORT="${SFTP_PORT:-22}"
REMOTE_ROOT="${SFTP_REMOTE_ROOT:-/}"
R_PROFILES="${REMOTE_ROOT%/}/${REMOTE_PROFILES_DIR:-profiles}"
R_MISSIONS="${REMOTE_ROOT%/}/${REMOTE_MPMISSIONS_DIR:-mpmissions}"
L_PROFILES="server/profiles"
L_MISSIONS="server/mpmissions"
DRY="${DRY_RUN:-0}"

# Runtime/persistence data we never sync as config.
# Kept as a single string so the quotes survive into the lftp script.
EXCLUDES="--exclude-glob '*.ADM' --exclude-glob '*.RPT' --exclude-glob '*.log' \
--exclude-glob '*.mdmp' --exclude-glob 'storage_*/' --exclude-glob '*.bak'"

export LFTP_PASSWORD="$SFTP_PASSWORD"
run_lftp() {
  lftp -c "
    set sftp:connect-program 'ssh -F /dev/null -o StrictHostKeyChecking=no'
    set sftp:auto-confirm yes
    set net:max-retries 3
    set net:timeout 20
    open --env-password -u '$SFTP_USER' -p '$SFTP_PORT' 'sftp://$SFTP_HOST'
    $1
  "
}

active_mission() {
  echo "${MISSION_NAME:-$("$ROOT/.venv/bin/python" "$ROOT/tools/active.py" mission)}"
}

# Gitignored paths under a local dir, relative to it, as lftp exclude globs
# (glob characters escaped; ignored directories end in "/", which lftp matches as a directory).
runtime_excludes() {
  local dir="$1"
  git -C "$ROOT" ls-files --others --ignored --exclude-standard --directory -- "$dir" \
    | sed -e "s|^$dir/||" -e 's/[][*?\\]/\\&/g'
}

dry_flag() { [[ "$DRY" == "1" ]] && echo "--dry-run" || true; }

pull() {
  # Only the live mission: the GSP install also ships enoch/sakhal, which we don't run.
  local mission; mission="$(active_mission)"
  local r_mission="$R_MISSIONS/$mission" l_mission="$L_MISSIONS/$mission"
  mkdir -p "$L_PROFILES" "$l_mission"
  echo ">> Pulling $R_PROFILES and $r_mission"
  run_lftp "
    mirror --verbose --no-perms --parallel=4 $(dry_flag) $EXCLUDES '$R_PROFILES' '$L_PROFILES'
    mirror --verbose --no-perms --parallel=4 $(dry_flag) $EXCLUDES '$r_mission' '$l_mission'
  "
}

snapshot_remote() {
  local ts dir
  ts="$(date +%Y%m%d-%H%M%S)"
  dir="backups/remote-$ts"
  mkdir -p "$dir/profiles" "$dir/mpmissions"
  echo ">> Snapshotting remote state to $dir.tar.gz"
  run_lftp "
    mirror --parallel=4 $EXCLUDES '$R_PROFILES' '$dir/profiles'
    mirror --parallel=4 $EXCLUDES '$R_MISSIONS' '$dir/mpmissions'
  "
  tar -czf "$dir.tar.gz" -C backups "remote-$ts" && rm -rf "$dir"
}

push() {
  echo ">> Validating local configs"
  "$ROOT/scripts/validate.sh"
  if [[ "$DRY" != "1" ]]; then
    snapshot_remote
    read -r -p "Upload server/ to $SFTP_HOST? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
  fi
  local mission; mission="$(active_mission)"
  local l_mission="$L_MISSIONS/$mission" r_mission="$R_MISSIONS/$mission"
  local xp xm
  xp="$(mktemp)"; xm="$(mktemp)"; trap 'rm -f "$xp" "$xm"' RETURN
  runtime_excludes "$L_PROFILES" > "$xp"
  runtime_excludes "$l_mission" > "$xm"
  echo ">> Pushing $mission (newer files only, no remote deletes; $(wc -l < "$xp")+$(wc -l < "$xm") gitignored paths skipped)"
  run_lftp "
    mirror -R --only-newer --verbose --parallel=4 $(dry_flag) $EXCLUDES --exclude-glob-from='$xp' '$L_PROFILES' '$R_PROFILES'
    mirror -R --only-newer --verbose --parallel=4 $(dry_flag) $EXCLUDES --exclude-glob-from='$xm' '$l_mission' '$r_mission'
  "
  echo ">> Done. Restart the server from the GSP panel for changes to take effect."
}

# Upload exactly the files in LIST (repo-relative paths under server/, one per line), e.g.
# build/changed.txt from tools/cycle.py. Each remote copy is downloaded to backups/ first.
push_files() {
  local list="${1:?usage: sync.sh push-files LIST}"
  [[ -s "$list" ]] || { echo ">> Nothing to push ($list is empty)"; return 0; }
  echo ">> Validating local configs"
  "$ROOT/scripts/validate.sh"
  local mission; mission="$(active_mission)"
  local ts dir cmds="" backup="" rel remote rdir
  ts="$(date -u +%Y%m%dT%H%M%SZ)"; dir="backups/cycle-$ts"
  while IFS= read -r rel; do
    [[ -n "$rel" ]] || continue
    case "$rel" in
      server/profiles/*) remote="$R_PROFILES/${rel#server/profiles/}" ;;
      "$L_MISSIONS/$mission/"*) remote="$R_MISSIONS/$mission/${rel#"$L_MISSIONS/$mission/"}" ;;
      *) echo "refusing $rel: not under server/profiles or the active mission"; exit 2 ;;
    esac
    [[ -f "$rel" ]] || { echo "missing local file $rel"; exit 2; }
    rdir="$(dirname "$remote")"
    mkdir -p "$dir/$(dirname "$rel")"
    backup+="get1 -o '$dir/$rel' '$remote'
"
    cmds+="mkdir -p -f '$rdir'
put -O '$rdir' '$rel'
"
    echo "  $rel -> $remote"
  done < "$list"
  if [[ "$DRY" == "1" ]]; then echo ">> DRY RUN: nothing uploaded"; return 0; fi
  echo ">> Backing up the remote copies to $dir (files new on the server are skipped)"
  run_lftp "set cmd:fail-exit no
$backup" || true
  read -r -p "Upload $(grep -c . "$list") file(s) to $SFTP_HOST? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 1; }
  run_lftp "$cmds"
  echo ">> Done. Restart the server from the GSP panel for changes to take effect."
}

logs() {
  mkdir -p "$L_PROFILES"
  run_lftp "mirror --verbose --newer-than=now-1days --include-glob '*.ADM' --include-glob '*.RPT' '$R_PROFILES' '$L_PROFILES'"
}

case "${1:-}" in
  pull) pull ;;
  push) push ;;
  push-files) push_files "${2:-}" ;;
  logs) logs ;;
  push-excludes) runtime_excludes "$L_PROFILES"; runtime_excludes "$L_MISSIONS/$(active_mission)" ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
