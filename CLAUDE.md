# CLAUDE.md — DZDS (DayZ PvE Living Sandbox)

Authoritative design spec: `docs/SPEC.md`. Read it before any non-trivial change.
This file holds the rules you must follow when working in this repo.

## Topology (short version)
- **Remote**: DayZ dedicated server on a GSP (GTXGaming / Host Havoc). We touch it only via
  SFTP (`profiles/`, `mpmissions/`) and BattlEye RCON (UDP 2310). Game 2302, query 2303.
- **Local**: CachyOS host (7800X3D, RX 7900 XTX, 32 GB). Runs the DayZ client under Proton,
  Ollama (ROCm, `HSA_OVERRIDE_GFX_VERSION=11.0.0`) with Gemma 4 E4B, and the GM daemon.

## Repo map
| Path | Purpose |
|---|---|
| `config/mods.yaml` | Single source of truth for the mod loadout, load tier, workshop IDs |
| `server/` | Local mirror of remote `profiles/` + `mpmissions/` (pulled via `scripts/sync.sh`) |
| `backups/` | Timestamped `.tar.gz` snapshots taken automatically before every push (gitignored) |
| `presets/` | AI calibration, faction intent, loot (types) additions: format-independent sources |
| `maps/` | Named coordinates + role assignments per map; `_roles.yaml` defines the roles |
| `tools/` | Python CLIs: mod string, AI calibration, etc. |
| `scripts/` | Shell entry points: sync, validate |
| `src/gamemaster/` | Async GM daemon (ADM tail → Ollama → RCON) |

## Hard rules
1. **Validate before deploy.** `make validate` must pass before any push to the server
   (`python3 -m json.tool` for JSON, `xmllint --noout` for XML). `scripts/sync.sh push`
   enforces this. Never bypass it.
2. **Backup before modify.** Pushes snapshot the remote state into `backups/` first. When
   hand-editing a file under `server/`, keep a `.bak` sibling if the change is risky.
3. **Never commit secrets.** Credentials live only in `.env` (gitignored). `.env.example` is
   the template.
4. **Mod load order** (enforced by `tools/modstring.py` via `tier` in `config/mods.yaml`):
   1 core frameworks (`@CF`, `@Dabs Framework`, `@DayZ-Expansion-Core`) → 2 gameplay/AI →
   3 vehicles/base content → 4 UI/admin/utility. Every mod's `.bikey` goes into server `keys/`.
5. **AI calibration bounds** (Expansion AI defaults are too lethal):
   - `AccuracyMin` ∈ [0.25, 0.32], `AccuracyMax` ∈ [0.45, 0.52], `ThreatDistanceLimit` ≤ 300.0
   - Apply with `make calibrate`: it sets the global values (and AI kill logging) and clamps
     per-patrol overrides in AIPatrolSettings.json. It refuses values outside these bounds.
   - **Factions are compiled into Expansion, with no JSON config** (the spec's
     `profiles/ExpansionMod/AI/Factions/` doesn't exist). Our factions map onto built-ins
     (CDF=West, ChDKZ=East, Raiders, Survivors=Civilian) in `presets/factions.yaml`; tests
     check them against the engine's real relations. Design: `docs/LIVING_WORLD.md`.
6. **Design pillars.** Diegetic only: physical keys, keypads, tarps, tow cables, paper maps,
   radio broadcasts. **No** virtual garages, 3D HUD markers, map fast-travel, supercars,
   or micro-tedium (dipsticks, fuses, lug nuts). Reject or flag mods that violate this.
7. **Map portability.** Missions/waypoints reference named locations from `maps/<map>.yaml`,
   so porting to Nasdara is a data swap, not a code change.
8. **GM daemon safety.** It runs `dry_run: true` by default. LLM output is untrusted: it is
   schema-validated, action types are whitelisted, coords are clamped to map bounds, and
   broadcasts are length-limited and sanitized before reaching RCON.

9. **Never trust a Workshop ID without checking.** The spec's IDs were mostly wrong
   (`docs/MOD_AUDIT.md`). Any mod added or changed in `config/mods.yaml` must pass
   `make verify-mods`; use `make find-mod Q="..."` to look up IDs.
10. **Server feel (decided):** first-person only, no HUD crosshair, no personal light, physical
    map/compass with no player position, Expansion quest markers and Hardline HUD off.
    Keep `config/local_serverDZ.cfg` and the GSP panel in sync.
11. **Expansion file locations** (from its source): `$profile:ExpansionMod/Settings/` (AI,
    Quest settings), `$profile:ExpansionMod/Quests/` (quests, NPCs, objectives),
    `$mission:expansion/settings/` (AIPatrolSettings, AILocationSettings, HardlineSettings).
12. **Content keyed by map role.** Faction territories, mission placement and GM logic use the
    roles in `maps/_roles.yaml`, so Nasdara (Badlands, 1.30) is a data change. `make maps-check`.

## Current stage
No GSP rented yet. Work proceeds offline (`docs/PRE_PURCHASE.md`): GM against the ADM
simulator + fake RCON, Phase 2 presets, optional local test server whose profiles are the
repo's `server/` mirror. Badlands releases Oct 2026: `docs/BADLANDS_PREP.md`.

## Common commands
```bash
make setup            # venv + deps (Python >= 3.11)
make pull             # mirror remote profiles/ + mpmissions/ into server/
make validate         # JSON/XML syntax check of server/ and presets/
make push             # validate → backup remote → upload (prompts; DRY_RUN=1 to preview)
make modstring        # print -mod= / -serverMod= strings for the GSP panel
make keys             # check every mod has a .bikey (needs DAYZ_WORKSHOP_DIR)
make test             # pytest
make gm               # run the GM daemon (dry-run unless GM_DRY_RUN=0)
make calibrate        # AI accuracy bounds + kill logging (needs pulled/generated configs)
make overlays         # presets/overlays/*.yaml onto real configs (existing keys only)
make verify-mods      # check every mod ID/title/staleness on the Steam Workshop
make find-mod Q=...   # search the Workshop
make maps-check       # map role coverage (nasdara is TODO until release)
make types            # compile presets/types_dzds.yaml into a CE custom types file
make fake-rcon / sim / gm-sim   # offline GM loop (three terminals)
make gm-probe         # one-shot Ollama/prompt check
scripts/local_server.sh install|mods|start   # optional local dedicated server
```

## Workflow phases (spec §7)
1. GSP staging: sync script, key validation, mod string. **(scaffolded)**
2. Config harmonization: Expansion AI / Spatial AI presets, `types.xml` additions. **(calibration tool scaffolded)**
3. GM daemon. **(skeleton runs; world_actions dispatch to RestApi is TODO)**
4. ChernarusPlus validation & playtest (checklist in `docs/PLAYTEST.md`).
5. Nasdara porting prep (`maps/nasdara.yaml` placeholder).
