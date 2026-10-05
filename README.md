# DZDS — DayZ PvE Living Sandbox

Tooling and Game Master daemon for a private, persistent DayZ PvE server (GSP-hosted),
driven from a local CachyOS rig with a local LLM (Gemma 4 E4B via Ollama/ROCm).

- **Design spec:** [`docs/SPEC.md`](docs/SPEC.md)
- **Rules for Claude Code / contributors:** [`CLAUDE.md`](CLAUDE.md)
- **Playtest checklist:** [`docs/PLAYTEST.md`](docs/PLAYTEST.md)
- **No server yet?** Start with [`docs/PRE_PURCHASE.md`](docs/PRE_PURCHASE.md), then
  [`docs/GSP_CHECKLIST.md`](docs/GSP_CHECKLIST.md)
- **Living world / faction war design:** [`docs/LIVING_WORLD.md`](docs/LIVING_WORLD.md)
- **Mod list audit:** [`docs/MOD_AUDIT.md`](docs/MOD_AUDIT.md) · **Badlands:** [`docs/BADLANDS_PREP.md`](docs/BADLANDS_PREP.md)

## First-time setup on the CachyOS PC

```bash
sudo pacman -S --needed git python lftp libxml2   # libxml2 provides xmllint
git clone <this repo> ~/DZDS && cd ~/DZDS
make setup             # creates .venv, installs deps, copies .env.example -> .env
make test && make verify-mods

# Once you have a GSP:
$EDITOR .env           # SFTP + RCON credentials from your GSP panel
make pull              # mirror remote profiles/ + mpmissions/ into server/
git add server && git commit -m "Baseline server config"   # version your live config
```

### Without a server (offline)
```bash
make gm-probe                       # Ollama + prompt sanity check
make fake-rcon   # terminal 1
make sim         # terminal 2
make gm-sim      # terminal 3: watch radio broadcasts appear in terminal 1
```

### Ollama (ROCm) for the GM
```bash
sudo pacman -S ollama-rocm
sudo systemctl edit ollama   # add: [Service]\nEnvironment=HSA_OVERRIDE_GFX_VERSION=11.0.0
sudo systemctl enable --now ollama
ollama pull gemma4:e4b       # confirm the exact tag with `ollama list` / ollama.com
```

## Daily workflow

| Task | Command |
|---|---|
| Pull live configs | `make pull` |
| Edit configs | edit files in `server/`, then `git diff` |
| Validate | `make validate` |
| Preview upload | `DRY_RUN=1 make push` |
| Upload (auto-backup + confirm) | `make push`, then restart from the GSP panel |
| Launch string for GSP panel | `make modstring` |
| Check mod `.bikey`s | `make keys` (copy with `.venv/bin/python tools/modstring.py keys --copy-to <dir>`) |
| Apply AI calibration | `make calibrate` |
| Pull recent logs | `make logs` |
| Run GM (dry run) | `make gm` |
| Run GM live | `GM_DRY_RUN=0 make gm` |
| Verify / search mods | `make verify-mods`, `make find-mod Q="..."` |
| Map role coverage | `make maps-check` |
| Build custom loot types | `make types` (list mod classnames: `make mod-types`) |
| Local test server | `scripts/local_server.sh install \| mods \| start` |

## Layout
```
config/mods.yaml        mod loadout, tiers, verified workshop IDs (source of truth)
config/local_serverDZ.cfg  serverDZ.cfg for the optional local test server
config/gm.yaml          GM tuning (heartbeat, cooldown)
presets/                calibration overlays applied onto server/ configs
maps/                   named coordinates + roles per map (_roles.yaml = shared role list)
scripts/                sync.sh (SFTP), validate.sh (JSON/XML), local_server.sh
tools/                  mod verify/search/strings, calibration, types_gen, maps_check,
                        adm_simulator, fake_rcon, gm_probe
src/gamemaster/         GM daemon: adm.py, rcon.py, llm.py, schema.py, gm_orchestrator.py
server/                 local mirror of remote profiles/ + mpmissions/
backups/                remote snapshots taken before each push (gitignored)
```

## Status vs. spec §7
- [x] Mod list verified against the Workshop (`docs/MOD_AUDIT.md`)
- [x] Phase 1: SFTP sync, `-mod=` generator, `.bikey` checker
- [~] Phase 2: calibration tool, faction stance matrix, custom types generator. Translating into Expansion's real file format needs its generated configs (local server or GSP)
- [~] Phase 3: GM daemon runs end to end (ADM → Gemma → RCON `say`), testable offline with simulator + fake RCON. `world_actions` are logged only until an Enforce RestApi hook exists
- [ ] Phase 4: ChernarusPlus playtest (`docs/PLAYTEST.md`)
- [~] Phase 5: role-based maps + `make maps-check`; Nasdara data on release (`docs/BADLANDS_PREP.md`)
