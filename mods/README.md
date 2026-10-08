# Project mods (source)

`mods/DZDS/` is the source for **@DZDS**, this project's own small mod (client + server).

| Part | Status |
|---|---|
| Custom factions (`Scripts/3_Game/DZDS/Factions/DZDSFactions.c`) | **compiles and registers on the GSP (2026-10-07)** |
| Runtime diplomacy overrides (`DZDSDiplomacy.c`, reads `$profile:DZDS/diplomacy.json`) | compiles; untested in play |
| Per-player tolerance (`4_World/DZDS/DZDSTolerance.c`): Karkas/Rust spare players with enough Hardline reputation. Registered through `DZDSToleranceHook` (3_Game), because 4_World cannot `modded class` a 3_Game class | compiles and registers; untested in play |
| World layer (`4_World/DZDS/DZDSWorld.c`): site markers at start + GM command queue (`$profile:DZDS/queue/*.json`, allowlisted spawns) | starts on the GSP; 0 markers until `presets/world.yaml` names marker classes |
| Radio-only GM audio clips | planned (docs/IMMERSION.md) |
| Extra telemetry (vehicle crashes, site entries) | planned |

## Building
DayZ loads mods as signed PBOs:
```
@DZDS/
  addons/dzds_scripts.pbo        <- packed from mods/DZDS (prefix "DZDS")
  addons/dzds_scripts.pbo.dzds.bisign
  keys/dzds.bikey                <- copy to the server's keys/
```
1. **Pack + sign: `scripts/build_dzds.sh`** (2026-10-07). Packs with `tools/pack_pbo.py`
   (Addon Builder hangs at a first-run window under Proton) and signs with DayZ Tools'
   `DSSignFile.exe` under Proton Experimental, writing a v3 `.bisign`. Output: `build/@DZDS`.
2. **Keys**: made once with `DSCreateKey.exe dzds` into `build/keys/` (gitignored).
   `dzds.biprivatekey` is mode 600 and never leaves this PC; `dzds.bikey` ships with the mod.
   Lose the private key and every future build needs a new key on the server and clients.
3. Put the packed mod in `build/@DZDS` (local test server links it from there). Copy `@DZDS` to the server and to each player's DayZ folder (or publish it to the Workshop
   as unlisted/friends-only so the launcher fetches it).
4. Enable `DZDS (local)` in `config/mods.yaml`.

First compile check: start the local test server with @DZDS and look for script errors in
the `.RPT` (`make logs`). Expansion logs "Registering faction type eAIFactionDZDS..." on success.
