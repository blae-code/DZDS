# DZDS — DayZ PvE Living Sandbox

Tooling and Game Master daemon for a private, persistent DayZ PvE server (GSP-hosted),
driven from a local CachyOS rig with a local LLM (Gemma 4 E4B via Ollama/ROCm).

- **Design spec:** [`docs/SPEC.md`](docs/SPEC.md)
- **Rules for Claude Code / contributors:** [`CLAUDE.md`](CLAUDE.md)
- **Playtest checklist:** [`docs/PLAYTEST.md`](docs/PLAYTEST.md)

## First-time setup on the CachyOS PC

```bash
sudo pacman -S --needed git python lftp libxml2   # libxml2 provides xmllint
git clone <this repo> ~/DZDS && cd ~/DZDS
make setup             # creates .venv, installs deps, copies .env.example -> .env
$EDITOR .env           # SFTP + RCON credentials from your GSP panel
make pull              # mirror remote profiles/ + mpmissions/ into server/
git add server && git commit -m "Baseline server config"   # version your live config
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

## Layout
```
config/mods.yaml        mod loadout, tiers, workshop IDs (source of truth)
config/gm.yaml          GM tuning (heartbeat, cooldown)
presets/                calibration overlays applied onto server/ configs
maps/                   named coordinates per map (Chernarus now, Nasdara later)
scripts/                sync.sh (SFTP), validate.sh (JSON/XML)
tools/                  modstring.py, apply_ai_calibration.py
src/gamemaster/         GM daemon: adm.py, rcon.py, llm.py, schema.py, gm_orchestrator.py
server/                 local mirror of remote profiles/ + mpmissions/
backups/                remote snapshots taken before each push (gitignored)
```

## Status vs. spec §7
- [x] Phase 1: SFTP sync, `-mod=` generator, `.bikey` checker
- [~] Phase 2: AI accuracy/range calibration tool. Factions, Spatial AI preset and `types.xml` still to do once real configs are pulled
- [~] Phase 3: GM daemon runs end to end (ADM → Gemma → RCON `say`). `world_actions` are logged only until an Enforce RestApi hook exists
- [ ] Phase 4: ChernarusPlus playtest (`docs/PLAYTEST.md`)
- [ ] Phase 5: Nasdara coordinates (`maps/nasdara.yaml`)
