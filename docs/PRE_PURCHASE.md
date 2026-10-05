# Pre-Purchase Work Plan

Everything here runs on your CachyOS PC with no rented server. Work done now carries over
unchanged once a GSP is bought.

## 1. Lock the mod list (no game needed)
```bash
make verify-mods            # every ID resolves on the Workshop, flags stale mods
make find-mod Q="towing"    # search for alternatives
```
Edit `config/mods.yaml`, rerun `make verify-mods`. See `docs/MOD_AUDIT.md` for decisions still open.

## 2. Develop the Game Master offline
Three terminals, no server needed:
```bash
make fake-rcon     # 1: pretend BattlEye RCON; prints every radio broadcast
make sim           # 2: writes synthetic .ADM lines to gm_state/sim.ADM
make gm-sim        # 3: GM reads the sim log, asks Ollama, broadcasts to the fake RCON
```
Before that, check Ollama/ROCm and the prompt in isolation:
```bash
make gm-probe                 # one canned digest → validated JSON + latency
.venv/bin/python tools/gm_probe.py --runs 5   # consistency check
```
Things worth doing in this phase: tune `SYSTEM_PROMPT` in `src/gamemaster/llm.py`, the
cooldown/heartbeat in `config/gm.yaml`, and what counts as significant in
`EventAggregator.SIGNIFICANT`.

## 3. Draft Phase 2 configs
- `presets/factions.yaml`: faction stance matrix + territories by map role (tests enforce spec rules)
- `presets/types_dzds.yaml` → `make types` compiles to a custom CE file (in `build/` until a mission exists)
- Subscribe to the mods in Steam, then `make mod-types` lists the classnames they ship, so you can
  fill in the `TODO_*` placeholders in the types preset.

## 4. Optional: local test server (experimental)
Run a real dedicated server on this PC to boot-test the mod stack and generate Expansion's
default config files (the real schema the faction/AI presets must be translated into).
```bash
yay -S steamcmd
# .env: STEAM_USER=<account that owns DayZ>
scripts/local_server.sh install   # ~3 GB
# subscribe to every mod in mods.yaml in Steam (links printed by the next command)
scripts/local_server.sh mods
scripts/local_server.sh start     # join 127.0.0.1:2302 from the DayZ launcher
```
- Profiles go to `server/profiles` and the mission is linked from `server/mpmissions`, so
  anything tuned here is what `make push` later uploads to the GSP.
- After the first boot: `make calibrate` (now that AISettings.json exists), `make types`.
- Real logs: `GM_TELEMETRY=file GM_ADM_FILE=server/profiles make gm` follows the newest `.ADM`.
- Real RCON: create `<server>/battleye/beserver_x64.cfg` with `RConPassword <pw>` and
  `RConPort 2310`, then run the GM with `RCON_HOST=127.0.0.1`.
- Caveats: Bohemia's Linux server build is less battle-tested than Windows; some mods
  fail on case-sensitive filenames. A mod failing only locally isn't proof it's broken.
  Running server + client together on 32 GB is tight with ~35 mods; close other apps.

## 5. Choose a host
Work through `docs/GSP_CHECKLIST.md` before paying.

## 6. Badlands
Release-day runbook: `docs/BADLANDS_PREP.md`. Don't buy a server for Nasdara until mods
have updated for game version 1.30.
