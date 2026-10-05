#!/usr/bin/env bash
# SFTP sync between the GSP and the local mirror in server/.
#
#   scripts/sync.sh pull            # remote profiles/ + mpmissions/ -> server/
#   scripts/sync.sh push            # validate -> snapshot remote to backups/ -> upload
#   scripts/sync.sh logs            # pull only *.ADM / *.RPT into server/profiles (for debugging)
#   DRY_RUN=1 scripts/sync.sh push  # show what would change, upload nothing
#
# Requires: lftp (CachyOS: sudo pacman -S lftp). Credentials come from .env.
# Push never deletes remote files and only uploads files newer than the remote copy.
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
    set sftp:auto-confirm yes
    set net:max-retries 3
    set net:timeout 20
    open --env-password -u '$SFTP_USER' -p '$SFTP_PORT' 'sftp://$SFTP_HOST'
    $1
  "
}

dry_flag() { [[ "$DRY" == "1" ]] && echo "--dry-run" || true; }

pull() {
  mkdir -p "$L_PROFILES" "$L_MISSIONS"
  echo ">> Pulling $R_PROFILES and $R_MISSIONS"
  run_lftp "
    mirror --verbose --parallel=4 $(dry_flag) $EXCLUDES '$R_PROFILES' '$L_PROFILES'
    mirror --verbose --parallel=4 $(dry_flag) $EXCLUDES '$R_MISSIONS' '$L_MISSIONS'
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
  echo ">> Pushing (newer files only, no remote deletes)"
  run_lftp "
    mirror -R --only-newer --verbose --parallel=4 $(dry_flag) $EXCLUDES '$L_PROFILES' '$R_PROFILES'
    mirror -R --only-newer --verbose --parallel=4 $(dry_flag) $EXCLUDES '$L_MISSIONS' '$R_MISSIONS'
  "
  echo ">> Done. Restart the server from the GSP panel for changes to take effect."
}

logs() {
  mkdir -p "$L_PROFILES"
  run_lftp "mirror --verbose --newer-than=now-1days --include-glob '*.ADM' --include-glob '*.RPT' '$R_PROFILES' '$L_PROFILES'"
}

case "${1:-}" in
  pull) pull ;;
  push) push ;;
  logs) logs ;;
  *) sed -n '2,10p' "$0"; exit 1 ;;
esac
