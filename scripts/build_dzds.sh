#!/usr/bin/env bash
# Build @DZDS: pack mods/DZDS into a PBO (tools/pack_pbo.py), sign it with DayZ Tools'
# DSSignFile under Proton, and verify with DSCheckSignatures against our public key.
#
#   scripts/build_dzds.sh     -> build/@DZDS/{addons/dzds_scripts.pbo(.dzds.bisign), keys/dzds.bikey}
#
# Needs DayZ Tools (Steam app 830640) and build/keys/dzds.biprivatekey (made once with
# DSCreateKey; private, gitignored). Addon Builder is not used: it hangs under Proton.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STEAM="${STEAM_ROOT:-$HOME/.local/share/Steam}"
TOOLS="$STEAM/steamapps/common/DayZ Tools/Bin/DsUtils"
PROTON="${PROTON:-$STEAM/steamapps/common/Proton - Experimental/proton}"
KEY="$ROOT/build/keys/dzds.biprivatekey"
OUT="$ROOT/build/@DZDS"

[[ -f "$KEY" ]] || { echo "Missing $KEY (create once: DSCreateKey.exe dzds)"; exit 2; }
[[ -x "$PROTON" ]] || { echo "Proton not found: $PROTON"; exit 2; }

export STEAM_COMPAT_CLIENT_INSTALL_PATH="$STEAM"
export STEAM_COMPAT_DATA_PATH="$STEAM/steamapps/compatdata/830640"
mkdir -p "$STEAM_COMPAT_DATA_PATH"
win() { echo "Z:${1//\//\\}"; }
run() { timeout 120 "$PROTON" run "$@" 2>&1 | grep -viE '^(wine|fsync|esync|ntsync|ProtonFixes|pid|Proton:)|fixme' || true; }

rm -rf "$OUT"
mkdir -p "$OUT/addons" "$OUT/keys"
"$ROOT/.venv/bin/python" "$ROOT/tools/pack_pbo.py" "$ROOT/mods/DZDS" "$OUT/addons/dzds_scripts.pbo" --prefix DZDS
cp "$ROOT/build/keys/dzds.bikey" "$OUT/keys/"

echo ">> Signing"
run "$TOOLS/DSSignFile.exe" "$(win "$KEY")" "$(win "$OUT/addons/dzds_scripts.pbo")"
[[ -f "$OUT/addons/dzds_scripts.pbo.dzds.bisign" ]] || { echo "Signing failed: no .bisign written"; exit 1; }

# DSCheckSignatures prints nothing under Proton, for good AND tampered PBOs, so it proves
# nothing here. Check the .bisign structure instead; real acceptance shows when a client joins
# a server with verifySignatures = 2.
echo ">> Checking signature structure"
python3 -I -c '
import struct, sys
b = open(sys.argv[1], "rb").read(); p = b.index(b"\0") + 1
def blob():
    global p
    n = struct.unpack_from("<I", b, p)[0]; p += 4 + n
blob(); blob(); ver = struct.unpack_from("<I", b, p)[0]; p += 4; blob(); blob()
assert b.startswith(b"dzds\0") and ver == 3 and p == len(b), "malformed .bisign"
print("   ok: key dzds, signature v3")
' "$OUT/addons/dzds_scripts.pbo.dzds.bisign"
find "$OUT" -type f -printf '%10s  %P\n'
