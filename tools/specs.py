#!/usr/bin/env python3
"""Estimate server / client requirements from the enabled mod list (docs/SERVER_SPECS.md).

Uses real Workshop download sizes (Steam API) for every enabled mod, then applies the sizing
heuristics documented in docs/SERVER_SPECS.md. Rerun after pruning: `make specs`.
These are ESTIMATES; confirm with the measurements in docs/SERVER_SPECS.md §4.
"""
from __future__ import annotations

import math
import sys

from modstring import load_mods
from verify_mods import fetch

# Heuristics (docs/SERVER_SPECS.md §2). Tune after measuring on the local server.
SERVER_BASE_GB = 3.0          # vanilla DayZ server on Chernarus/Nasdara, idle world
SERVER_PER_MOD_GB = 0.25      # resident server RAM per GB of mod download (configs, geometry, scripts)
SERVER_AI_PLAYERS_GB = 1.5    # ~60 active Expansion AI + 4 players + vehicles/persistence
HEADROOM = 1.25               # leak/growth between restarts, Badlands' bigger map
SERVER_INSTALL_GB = 3.0
PERSIST_LOGS_GB = 5.0         # storage_*, .ADM/.RPT logs, backups on the box
CLIENT_DAYZ_GB = 25.0         # DayZ + DLC install, approximate


def estimate(mod_gb: float) -> dict:
    ram = (SERVER_BASE_GB + SERVER_PER_MOD_GB * mod_gb + SERVER_AI_PLAYERS_GB) * HEADROOM
    return {
        "mod_download_gb": round(mod_gb, 1),
        "server_ram_gb": math.ceil(ram),
        "server_disk_gb": math.ceil((SERVER_INSTALL_GB + mod_gb + PERSIST_LOGS_GB) * 1.5),
        "client_disk_gb": math.ceil(CLIENT_DAYZ_GB + mod_gb),
    }


def main() -> int:
    mods = [m for m in load_mods() if m.get("enabled", True) and not m.get("local")]
    d = fetch([m["id"] for m in mods])
    sizes = {m["name"]: int(d.get(str(m["id"]), {}).get("file_size") or 0) / 1e9 for m in mods}
    e = estimate(sum(sizes.values()))
    print(f"{len(mods)} enabled Workshop mods, {e['mod_download_gb']} GB download")
    print(f"  server RAM  ~{e['server_ram_gb']} GB   (dedicated, incl. {int((HEADROOM - 1) * 100)}% headroom)")
    print(f"  server disk ~{e['server_disk_gb']} GB   (install + mods + persistence/logs, x1.5)")
    print(f"  client disk ~{e['client_disk_gb']} GB   (DayZ + DLC + mods, per player)")
    print("  largest mods:")
    for name, gb in sorted(sizes.items(), key=lambda kv: kv[1], reverse=True)[:8]:
        print(f"    {gb:5.2f} GB  {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
