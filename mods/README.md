# Project mods (source)

`mods/DZDS/` is the source for **@DZDS**, this project's own small mod (client + server).

| Part | Status |
|---|---|
| Custom factions (`Scripts/3_Game/DZDS/Factions/DZDSFactions.c`) | written, not yet compiled |
| Runtime diplomacy overrides (`DZDSDiplomacy.c`, reads `$profile:DZDS/diplomacy.json`) | written, not yet compiled |
| World layer (`4_World/DZDS/DZDSWorld.c`): site markers at start + GM command queue (`$profile:DZDS/queue/*.json`, allowlisted spawns) | written, not yet compiled |
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
1. **Pack**: DayZ Tools' Addon Builder (Steam, free; Windows, or try it under Proton), with
   the source `mods/DZDS` and prefix `DZDS`. Linux-native PBO packers exist but are untested here.
2. **Sign**: DayZ Tools' DS Utils: create a key pair once (`dzds.biprivatekey` stays private,
   gitignored; `dzds.bikey` is public), then sign the PBO.
3. Put the packed mod in `build/@DZDS` (local test server links it from there). Copy `@DZDS` to the server and to each player's DayZ folder (or publish it to the Workshop
   as unlisted/friends-only so the launcher fetches it).
4. Enable `DZDS (local)` in `config/mods.yaml`.

First compile check: start the local test server with @DZDS and look for script errors in
the `.RPT` (`make logs`). Expansion logs "Registering faction type eAIFactionDZDS..." on success.
