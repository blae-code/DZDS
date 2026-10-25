# CLAUDE.md — DZDS (DayZ PvE Living Sandbox)

Authoritative design spec: `docs/SPEC.md`. Read it before any non-trivial change. **Since
the Badlands relaunch, `docs/superpowers/specs/2026-10-15-badlands-relaunch-design.md`
overrides SPEC.md where they disagree** (map, loot, campaign phases, zones).
This file holds the rules you must follow when working in this repo.

## Working environment
- **Repo:** `~/Documents/Code/DayZ` (renamed from `~/Documents/Code/DZDS` on 2026-10-21;
  the GitHub repo, the `@DZDS` mod, the `dzds-gm` entry point and the Python package keep
  the DZDS name, which is a mod name, not a path). Outside the Obsidian vault on purpose.
- **VS Code:** open `DayZ.code-workspace` (`code ~/Documents/Code/DayZ/DayZ.code-workspace`).
  It points Python at `.venv` and pytest at `tests/`, and keeps `backups/`, `build/` and
  `.venv` out of search and file watching.
- **Python:** always the repo venv: `make <target>` or `.venv/bin/python`, never the system
  `python3` (which lacks the deps). If the venv breaks (it bakes in absolute paths, so it
  breaks whenever the repo moves): move `.venv` aside, run `make setup`, run `make test`.
- **Shells:** the operator's interactive shell is **fish** (`source .venv/bin/activate.fish`);
  the Makefile and `scripts/*.sh` are **bash** on purpose (`SHELL := /bin/bash`). Don't write
  bash-isms into fish snippets you hand Blae, or the reverse.
- **Credentials:** `.env` only (mode 600, gitignored). Never print a value. Compare by hash.
- **Branch:** work happens on `badlands-relaunch` (well ahead of `main`). Commit there and
  end messages with the Co-Authored-By trailer. **Don't push to GitHub, merge to `main`, or
  touch the `origin/ccr-*` branches without asking.**

## Who does what: the boundary with the live server
Claude can reach the server **only over SFTP** (the `.env` credentials) and the public
Workshop API. Claude **cannot** reach the Godlike panel, and RCON doesn't work (see Current
stage). So:

| Claude does freely (read-only or local) | Ask Blae first (writes to something live or public) | Only Blae can do (panel) |
|---|---|---|
| `make mod-drift`, `verify-mods`, `specs`, `logs`, `test`, `validate` | `make push` (writes the live server; it prompts, so use `DRY_RUN=1 make push` to preview) | Restart / stop / start the server |
| `make pull` (overwrites the local `server/` mirror: **commit or stash local edits under `server/` first**) | `scripts/publish_dzds.sh` (public Workshop item every player downloads) | File Manager: rename `/@<id>` aside so the panel re-downloads it |
| Edit `presets/`, `config/`, `tools/`, `mods/DZDS` source, tests, docs | Adding, removing or pruning a mod in `config/mods.yaml` (a design decision: pillar rule 6) | Startup Variables: "Additional Mods" / "Server-Side Only Mods" |
| `scripts/build_dzds.sh` (local build only) | Any SFTP write outside `make push`, e.g. renaming `/@<id>` over SFTP | Anything in the panel's settings |

When a fix needs a panel action, **hand Blae the exact list** (mod name + `@<id>`) and the
order of operations. Don't describe it vaguely and stop there.

## When the server is down: triage runbook
This happens again and again: Workshop mods update with no notice, and the panel never
refreshes an installed mod. **Work through the steps in order, and don't guess the cause
before step 1 has run.**

1. **`make mod-drift`** (read-only, ~1 min). Exit **0** = all mods match, so go to step 2.
   Exit **1** = drift: every `STALE`/`DIFFERS` row is a mod the panel must re-download.
   Hand Blae the list (fix: rename each `/@<id>` aside in File Manager, then restart).
   Exit **2** = it couldn't read the server: that is **not** a clean result. Check `.env`
   and SFTP reachability before anything else.
2. **`make logs`** pulls the last day's `*.ADM` / `*.RPT` into `server/profiles/`. It does
   **not** pull `crash_*.log`. Get those from the same SFTP profiles directory by hand
   (read-only) when the engine crashed rather than refused to boot.
3. **Read the newest `.RPT` from the bottom up.** Look for: `SCRIPT (E)`,
   `Can't compile "...World" script module` (a mod's API changed, or a load-order or
   dependency problem), `Unhandled exception` / crash logs (runtime crash, so correlate
   crash times with boot times), and missing-class errors naming our overlays (an overlay
   points at a class a pruned or updated mod no longer has; see `requires_mod`).
   **Also check the RPT's `Version` line against the last good boot, and grep for
   `Error decoding <file> from <mod>`.** A DayZ patch can stop the engine decoding an
   obfuscated mod's scripts. The missing file then shows up as an unrelated compile error in
   another file (2026-10-21: BuildAnywhere's `m_Trader_IsInSafezone`, CnG's
   `WorldEditorTool`). The fix is to disable the mod named in the decode line, not the one
   named in the compile error.
4. **Classify, then fix the right layer:**
   - *A mod updated and broke another* (e.g. Code Lock's rename broke RaG_BaseBuilding,
     2026-10-15): propose prune or replace in `config/mods.yaml`. Blae decides.
   - *A mod interaction crashes at runtime* (e.g. trailers vs Expansion AI's
     `eAIDamageHandler`, 2026-10-17): contain it in our config, `init.c` or `@DZDS`, add a
     test that pins it, and record the re-enable condition in the commit message.
   - *Our generated config is wrong*: fix the preset/tool and regenerate, never hand-edit
     the output (rule 13).
5. **After any mod-list change:** `make panel-mods` (regenerates
   `config/panel_additional_mods.txt`) → Blae updates the panel (**the paste REPLACES the
   list**) → restart → `make pull` → `make overlays calibrate validate` → `make push`.
6. **Verify. Never declare it fixed on inference:** `make mod-drift` exits 0, and the fresh
   `.RPT` shows `[DZDS] World layer started` with zero `SCRIPT (E)` lines after the boot.
7. **Record it:** one dated line under "Current stage" (cause → fix), and a commit.

## Topology (short version)
- **Remote**: DayZ dedicated server **"Ad Aspera" on Godlike** (rented 2026-10-06; "Rampage"
  Budget plan: 12 GB RAM, 4 vCores AMD EPYC 7543, 70 GB, Canada). Pterodactyl-style panel
  (`ghcr.io/parkervcp/games:dayz` egg). We touch it only via SFTP (`profiles/`, `mpmissions/`
  at the SFTP root) and BattlEye RCON. Ports: **game 26091, query 26092, RCON 26093**,
  host `srv7002.godlike.club`; SFTP `wing7002.panel.godlike.host:2022`. Host/user live in
  `.env`. **Mods are set in the panel by Workshop ID**: Config → Startup Variables →
  "Additional Mods" / "Server-Side Only Mods", value from `make panel-mods`. The panel
  auto-installs `@<id>` entries (lowercasing every file name) and rejects capitals/spaces in
  folder names, so the folder-name string from `make modstring` is for local/other hosts only.
  **It installs only MISSING folders and never updates an installed mod** (proven
  2026-10-08 from the server's `Steam/logs/workshop_log.txt`; a restart does not help). When
  a mod updates on the Workshop, players are kicked after the password prompt ("mod updated
  on the client but not the server"). **`make mod-drift`** finds it (server vs Workshop vs
  this machine's client copy; exit 1 on drift, 2 if it could not read the server). Fix: rename
  `/@<id>` aside in the File Manager and restart, so the panel re-downloads it.
- **Local**: CachyOS host (7800X3D, RX 7900 XTX, 32 GB). Runs the DayZ client under Proton,
  the GM daemon, and the Sovereign stack's headless LM Studio (`127.0.0.1:1234`). The GM uses
  Gemma 4 E4B (the POD gear) only when it is the loaded gear, and never names a model itself.

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
| `src/gamemaster/` | Async GM daemon (ADM tail → LM Studio → RCON) |

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
     `profiles/ExpansionMod/AI/Factions/` doesn't exist). The user's Faction Blueprint
     (Settlers = players, UN Peacekeepers, Jackals, Karkas, Rust) is implemented as custom
     classes in our @DZDS mod (`mods/DZDS`), designed in `presets/factions.yaml`; tests check
     the preset against that source. Per-patrol accuracy may range 0.20–0.35 / 0.35–0.52
     so factions differ. Design: `docs/FACTIONS.md`.
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
    **Nights: dark AND short** (Blae, 2026-10-07): `lightingConfig = 1` (panel "Darker
    Nights" = 1), time multiplier 4, night multiplier 8 → nights ~15–20 min real time,
    24 h in-game = 6 h. Persistent time on. Keep `config/local_serverDZ.cfg` and the GSP
    panel in sync.
11. **Expansion file locations** (from its source): `$profile:ExpansionMod/Settings/` (AI,
    Quest settings), `$profile:ExpansionMod/Quests/` (quests, NPCs, objectives),
    `$mission:expansion/settings/` (AIPatrolSettings, AILocationSettings, HardlineSettings).
12. **One system per job** (docs/VEHICLES.md): Expansion keys + towing (MuchCarKey and rope
    towing off), CarCover for tarps (Expansion covers off). **Never enable
    DayZ-Expansion-Animations or the Expansion Bundle**: it breaks DayZ Horse (test enforced).
13. **Economy = vanilla CE + faction barter traders** (docs/ECONOMY.md, presets/traders.yaml):
    ammo/nails/UN scrip as currencies, quest-gated traders, ATMs off.
    Never hand-edit `db/types.xml`; edit `presets/economy.yaml` and run `make economy`, which
    regenerates it from `db/types.xml.vanilla`. Our own items go in `presets/types_dzds.yaml`.
14. **Content keyed by map role.** Faction territories, mission placement and GM logic use the
    roles in `maps/_roles.yaml`, so Nasdara (Badlands, 1.30) is a data change. `make maps-check`.

## Current stage
**Now (2026-10-21): live on Nasdara (Badlands, game 1.30) since 2026-10-16 19:09 UTC**, with
a fresh start and the war ledger at turn 0. That launch booted all **70** mods with 0 script
errors. Don't trust that number: `config/mods.yaml` is the source and `make mod-drift`
prints the live count. Since the launch:
- 2026-10-15: Code Lock pruned for 1.30's vanilla DigitalCodeLock (its rename broke
  RaG_BaseBuilding).
- 2026-10-17: trailers disabled. A driverless trailer touching an infected crashes the engine
  via Expansion AI's `eAIDamageHandler`. Re-enable once @DZDS patches that.
- 2026-10-21: server down again with 13 mods drifted (2 STALE: AI War Zones and Arma 2
  Helicopters Remastered, both updated on the Workshop that morning; 11 DIFFERS). The fix
  (panel re-download) was handed to Blae, and drift was 70/70 OK by evening. The boot still
  failed because of the same day's **DayZ patch (server 1.30.164078 → 1.30.164200)**, which
  can't decode scripts in BuildAnywhere_v3, [CnG]Core_Bundle and both CnG UAZs (`Error
  decoding` in the RPT). All four disabled (67 mods), and the CnG UAZs were commented out of
  `presets/arrivals.yaml`. The 67-mod boot then compiled clean, but crashed restoring the
  10-18 world save (`Weather::Load … WeatherProperty`, then the first item). **Fixed
  2026-10-22 by a full wipe** (Blae): `storage_1` backed up to
  `backups/storage_1-nasdara-20261022T0157Z` and renamed `storage_1.old-20261022` on the
  server. Boot 02:00 UTC: 0 decode errors, 0 `SCRIPT (E)`, World layer started, no crash.
- 2026-10-22: favored players (`favored:` in `presets/arrivals.yaml`): Blae's respawn vehicle
  is always one of the 9 aircraft. The 24 h cooldown still applies.
  `make reset-respawns` (server STOPPED) clears everyone's cooldown and resets characters.
- 2026-10-22: players kicked again for a version mismatch. 4 mods DIFFERS (RaG_Core,
  RaG_Hunting_Cabin, Ambient Animals Pack, Asmond Vanilla Weapons). Each `/@<id>` was renamed
  to `/@<id>.old-20261022` over SFTP (Blae approved) and the panel re-downloaded them on
  restart. Drift 67/67 OK; the 23:17 UTC boot shows 0 `SCRIPT (E)`, 0 decode errors, and World
  layer started. The `.old-20261022` folders can go once a client joins cleanly.
- 2026-10-22: aircraft arrive fully kitted (Blae). Every attachment slot an aircraft declares
  is filled. Expansion helis get a desert camo net, key chain, wrench and a FULL jerrycan, and
  RedFalcon helis get the flight storage case, which is where their kit goes (the R22's own
  cargo is 0x0). `Tac_Radio` stays empty because no loaded mod makes an item for it.
  Aircraft get 60-90 % fuel and a pilot profile kit: `bush_pilot` or `combat_pilot`, both
  with a full jerrycan and signalling gear. Blae's favored pool drops the gyrocopter (5x2
  cargo). Also fixed: respawns woke ON the vehicle's spot (the R22 hit Blae as it spawned).
  `make reset-respawns PLAYER=blae` resets one player. A local boot (old 164078 server)
  compiled the mission cleanly, but then crashed in a mod animal, so the vehicle self-test
  didn't run; verify on the live RPT's `[DZDS Arrivals]` line. Deployed 23:47 UTC (only
  `init.c`, `dzds/types_dzds.xml` and `DZDS/arrivals.json`; a full `make push` would also have
  sent a dozen unrelated files newer only by mtime). Server-side backups are in
  `backups/aircraft-kit-20261022T234655Z`. Blae was reset with the server stopped (players.db
  kept as `players.db.old-20261022T234754Z`). The panel's SFTP refuses posix-rename, so
  remote writes overwrite in place.
- 2026-10-23 01:34 UTC: pilot kits add a pack and a survival kit (bush: rod and hook, snare,
  shovel; combat: survival vest, splint, rangefinder). Respawns now wake within 1 km (else
  2 km) of another living player online, BEFORE base/camp/near-death (Blae: "friend first").
  Base respawn (beside the raised territory flag nearest the death, no car) is in init.c
  behind `#ifdef DZDS_BASES` and needs the new @DZDS (`DZDSBases.c`). That build is **not
  published yet**: Blae uploads it, then the server re-downloads `/@3815870621`. Planes: none
  usable. Expansion's An-2/C-130J are `Vehicle_*` classes at scope 0, and LMs Planes was
  pruned. Deployed `init.c` + `DZDS/arrivals.json` only (a full push would have overwritten
  live quest state); backups in `backups/kits-grouping-20261023T013342Z`. Blae reset again
  (`players.db.old-20261023T013358Z`). Local boot: mission + new @DZDS compiled, then the
  local CE crashed loading its own `storage_1`.
- 2026-10-23 02:08 UTC: Blae respawned INSIDE the EXT_MH6. The ADM log put him on the road
  point itself, not 9 m beside it, and the 10-22 respawn did the same, so that fix never
  worked. Cause not found (nothing in init.c, @DZDS, CF, Zen Login/Sleep or vanilla moves the
  player). Deliver now puts a player within 4 m of the spot back beside it, then re-checks at
  3 s; check the RPT for `was N m from the vehicle spot` to find the cause. Deployed `init.c`
  only (`backups/spawn-beside-20261023T020758Z`); Blae reset (`players.db.old-20261023T020808Z`).
  The stuck MH-6 stays in the world.
- 2026-10-23 02:31 UTC: FIXED. The plan's own PlayerPos had been ON the spot ("moved to 0 m");
  after the rework (`BesideSpot`, plain-if `RandomCharacter`) the log reads `place: ... offset 9
  -> player (9 m)`, `random=true`, and the ADM has Blae 9 m beside an EXT_UH1Y. The old loop
  in `PlacePlayer` and the `!a && b == 1` expression both misbehaved in Enforce; the cause of
  each wasn't pinned down. Open: every road/arrival point has heading `A = 0.0`, so all spawned
  vehicles face north. Live cooldown resets: `make reset-respawns LIVE=1 PLAYER=..`.
- 2026-10-23 ~20:00 UTC: DZGUI refused to connect because ArmA2 Trucks (3593276829) was
  deleted from the Workshop (Steam result 9). `make mod-drift` had read it as OK, and now flags
  REMOVED. It was pruned (66 mods), and the 19:55 UTC boot was clean with drift 66/66 OK. Then the
  server disk hit its quota ("Quota Exceeded" on SFTP writes). It was full of `/@<id>.old-<date>`
  folders, which the panel never cleans up. 49 of them (~7.9 GB) and the orphaned `/@3593276829` were
  deleted. **After each re-download, delete the `.old-*` folder once a client has joined.**
  17 pruned mods (`enabled: false`) still have `/@<id>` folders at the root. Blae's character was
  reset (`players.db.old-20261023T205644Z`). reset_respawns now uploads before it renames.
- 2026-10-23: outfits (`outfits:` in `presets/arrivals.yaml`): a starting archetype WORN on the
  body. Soviet Special Forces (TTsKO or Gorka with a Smersh vest and bag, AKS-74U or AS Val with 3
  full mags, a Makarov, an RGD-5) has a 3 % chance per respawn for anyone, and Blae always gets it. Blae's 24 h
  cooldown now covers only his helicopter (cargo `combat_pilot`). Inside it he gets a Soviet land
  vehicle (UAZ/Vodnik/GAZ) carrying the outfit's `land_cargo`, which starts no cooldown, and he
  skips base/camp respawns. Verified live 2026-10-24: 02:27 and 02:56 UTC spawns in the outfit
  (9/9 worn, empty notes) beside a Little Bird, then an MH-6. At 04:08 a death inside the
  cooldown gave the outfit plus an ExpansionVodnik "(no cooldown)", and the ledger's LastVehicle
  stayed at the MH-6. Blae's heli pool is Expansion-framework only (`9204f18`): RedFalcon helis
  read inputs with SyncedValue, so his VKB sticks stutter in them. The vkb_pad bridge itself
  forwards in 0.03 ms (median).
- 2026-10-24 02:00 UTC: Zens Core Mod (3702420204) updated on the Workshop (DIFFERS in
  `zenmodcore.pbo`). `/@3702420204` was renamed to `/@3702420204.old-20261023` over SFTP (Blae
  approved), and the restart re-downloaded it. Drift 66/66 OK. The 02:00 boot shows 0 `SCRIPT (E)`,
  0 decode errors, and World layer started. Delete the `.old-20261023` folder once a client joins.

*Everything below in this section is the Chernarus+ history (2026-10-07 → 10-12). Its
lessons (panel trap, RCON, DZGUI, crash watch) still apply. Its mod counts and map don't.*

**First modded boot 2026-10-07 20:23: all 82 mods loaded, server up.** It threw one VM
exception (Expansion airdrop loot named BaseBuilding items we don't run); fixed by the
`expansion_airdrops`/`expansion_missions` overlays. Expansion ships the virtual Garage and
the P2P Market ON; both are off via overlays (P2P: Blae, 2026-10-07, not wanted). **Generated configs only exist after
a boot: after any mod change, `make pull` → `make overlays calibrate validate` → `make push`.**
**@DZDS is LIVE in `-mod` as Workshop 3815870621 (Public since 2026-10-08)**; the server log
of 2026-10-10 shows it in `-mod=` and only `@2874589934` (Spatial AI) in `-serverMod=`. Build:
`scripts/build_dzds.sh`, publish: `scripts/publish_dzds.sh`. DZDS* faction patrols are real,
so `make patrols` / `make prepare-restart` run without `INTERIM=1`. **Panel trap:** pasting
into "Additional Mods" REPLACES the mod list; the server then crash-loops on compile errors.
Overlays naming @DZDS classes carry `requires_mod: "@DZDS"`.
**AI pressure tuning (Blae, 2026-10-12):** human NPCs only in home territory, conflict sites
and drop sites; food at VANILLA scarcity (no boost, but no AI eating into it either).
Spatial AI off (`overlays/spatial_ai.yaml`, MaxAI 0); no patrol loots food and none roams
map-wide (`presets/factions.yaml`, pinned by tests); KAN camp roamers 0
(`presets/kan_camps.yaml`, `make kan-camps` with the server STOPPED, since the mod rewrites
camps.json); horde rarer and 120-200 m out (`overlays/zombie_horde.yaml`; its on-screen
warnings stay). Horde spawn-in-the-open (code override) is deferred until the distance is tested.
**RCON is DEFERRED (Blae, 2026-10-07: don't pursue RCON features for now)**, so the GM
daemon's RCON path stays offline. Findings kept for later: **RCON (26093) gives no reply even with the server's own password** (BattlEye active
cfg in `/battleye/`, RConPort 26093), while A2S on 26092 answers: a Godlike UDP/port issue,
ask support. Also, `.env`'s RCON_PASSWORD differs from the server's (compared by hash).
Panel: first person + no crosshair set 2026-10-07.
**Crash watch:** 2026-10-07 21:25 the engine crashed ("Unhandled exception, Reason: Unknown",
crash_2026-10-08_04-05-58.log) ~20 min after boot; the panel auto-restarted it. Not an OOM kill
(a SIGKILL writes no crash log). The next boot ran 10.5 h clean. If it recurs, compare crash
times against boot times and the script log's last lines before each.
**Joining: the official DayZ Launcher can't read our mod list** (A2S_RULES is one capped
3 KB reply, 32 rules, mod list truncated: "Server can't transmit all data"). The DZSA
Launcher API sees all 81 client mods, so players join via DZSA (Windows) or DZGUI (Linux).
Server is password-protected. **DZGUI: add by IP with the QUERY port, 23.229.49.100:26092**
(26091 is the game port and ignores queries, so DZGUI times out). Installed at ~/Applications/dzgui. **Pruned 2026-10-07 to fit: 82 Workshop
mods, 11.8 GB, ~10 GB RAM est.** (docs/PRUNING.md, top).
Badlands releases Oct 2026: `docs/BADLANDS_PREP.md`.

## Common commands
```bash
make setup            # venv + deps (Python >= 3.11)
make pull             # mirror remote profiles/ + mpmissions/ into server/
make validate         # JSON/XML syntax check of server/ and presets/
make push             # validate → backup remote → upload (prompts; DRY_RUN=1 to preview)
make modstring        # print -mod= / -serverMod= folder strings (local server)
make panel-mods       # Godlike "Additional Mods" / "Server-Side Only Mods" (@workshopID;)
make keys             # check every mod has a .bikey (needs DAYZ_WORKSHOP_DIR)
make test             # pytest
make gm               # run the GM daemon (dry-run unless GM_DRY_RUN=0)
make calibrate        # AI accuracy bounds + kill logging (needs pulled/generated configs)
make overlays         # presets/overlays/*.yaml onto real configs (existing keys only)
make verify-mods      # check every mod ID/title/staleness on the Steam Workshop
make mod-drift        # server's installed mods vs Workshop + client copy (ALL=1 lists OK too)
make specs            # server RAM/disk + client download estimate from enabled mods
make find-mod Q=...   # search the Workshop
make maps-check       # map role coverage (nasdara is TODO until release)
make types            # compile presets/types_dzds.yaml into a CE custom types file
make economy          # population + campaign-phase loot scaling (PHASE=... to force)
make patrols          # faction squad templates -> AIPatrolSettings.json (INTERIM=1 before @DZDS)
make kan-camps        # presets/kan_camps.yaml -> KAN camps.json roles (server STOPPED, after pull)
make arrivals         # refugee arrivals: presets/arrivals.yaml -> profiles/DZDS/arrivals.json (read by init.c)
make reset-respawns   # server STOPPED: clear arrivals cooldowns + reset characters (DRY_RUN=1 / YES=1 / PLAYER=blae)
make diplomacy        # presets/diplomacy.yaml -> profiles/DZDS/diplomacy.json (truces etc.)
make war-status       # war ledger: front line, strength, standing, diplomacy
make war-turn         # advance one war turn (docs/WAR_LEDGER.md)
make front-plan       # traders open/relocated/closed + live quests from the ledger
make loadouts         # faction loadouts -> profiles/ExpansionMod/Loadouts (loadouts-check vs types)
make dzds-profile     # @DZDS settings (spawn allowlist) + site markers from the ledger
make vehicle-events   # vehicle spawns by role + holder (events + cfgeventspawns)
make prepare-restart  # war-turn, economy, diplomacy, patrols, vehicle-events, front-plan, loadouts, dzds-profile, arrivals,
                      # overlays, calibrate, validate
make fake-rcon / sim / gm-sim   # offline GM loop (three terminals)
make gm-probe         # one-shot LM Studio gear + prompt check (exit 2 = wrong gear)
scripts/local_server.sh install|mods|start   # optional local dedicated server
/usr/bin/python3 tools/vkb_pad.py learn|bind   # VKB sticks -> virtual Xbox pad for helis; the
                      # dzds-vkb-pad user service runs it only while DayZ runs (bind: DayZ closed)
```

## Where things stand
Live status is "Current stage" above. Offline work stays green under `make test`, so run it
before every commit. Playtest procedure: `docs/PLAYTEST.md`. Pruning decisions:
`docs/PRUNING.md`. Relaunch plan: `docs/superpowers/plans/2026-10-15-badlands-relaunch.md`.

## Workflow phases (spec §7)
1. GSP staging: sync, key + dependency checks, mod string. **(done)**
2. Config harmonization: calibration, @DZDS factions, patrols, loadouts, economy, traders,
   vehicle events, overlays. **(done offline; needs in-game verification)**
3. GM daemon: ADM → Gemma → RCON radio + @DZDS command queue, war ledger. **(done offline)**
4. ChernarusPlus validation & playtest: `docs/PLAYTEST.md`. **(superseded by the relaunch)**
5. Nasdara porting: role-based maps, `maps/nasdara.yaml`. **(done: live 2026-10-16;
   relaunch spec + plan under `docs/superpowers/`)**
