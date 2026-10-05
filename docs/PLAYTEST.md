# Playtest Checklist (Phase 4: everything that needs the game)

Everything that could be built and tested offline is done (see the tests in `tests/`). What's
left can only be confirmed in a running game. Work top to bottom on the **local test server**
(`docs/PRE_PURCHASE.md` §4), then repeat the short "smoke" section on the GSP. Tick boxes in a
branch per session; file anything that fails as a follow-up.

## 0. One-time setup
- [ ] `make setup`; subscribe to every enabled mod (`scripts/local_server.sh mods` lists missing ones)
- [ ] `make verify-mods` and `.venv/bin/python tools/verify_mods.py --deps`: no missing dependencies
- [ ] Build and sign **@DZDS** (`mods/README.md`), put it in `build/@DZDS`, enable `DZDS (local)` in mods.yaml
- [ ] `scripts/local_server.sh install && scripts/local_server.sh start` (first boot generates Expansion's files)

## 1. Boot and load order
- [ ] Server boots with `make modstring` order; no script errors in the `.RPT` (`make logs`)
- [ ] Client joins via Proton/BattlEye; first person forced, no crosshair, no personal light
- [ ] RPT shows `Registering faction type eAIFactionDZDS...` ×5 (@DZDS compiled)
- [ ] RPT shows `[DZDS] World layer started` and `[DZDS] Spawned N site marker(s)`
- [ ] No mod complains about Expansion-Animations being missing (DayZ Horse incompatibility)

## 2. Generated configs land correctly (run `make prepare-restart`, restart, check)
- [ ] `make overlays`: no "not in file" warnings for cfggameplay, Quest, Hardline, Market, Vehicle, AI settings
- [ ] `make calibrate`: AISettings + AIPatrolSettings values applied (AI no longer laser-accurate)
- [ ] `make economy`: CE loads the regenerated types.xml (and modded types files); loot appears
- [ ] `make loadouts-check`: zero unknown classnames (fix UN helmet/beret, WeldingMask etc. in presets/loadouts.yaml)
- [ ] `make patrols`: patrols appear at their sites; waypoints with y=0 land on the ground; HALT/ROAMING/ALTERNATE behave
- [ ] `make vehicle-events`: vehicles spawn at generated positions (move any that clip into buildings; refine with VPP)
- [ ] Map needs a physical map; compass info needs a compass; no player position on the map

## 3. Factions
- [ ] Players join DZDSSettlers on connect (`PlayerFactions`)
- [ ] UN Peacekeepers ignore players with lowered weapons; aiming at/hitting them makes them fight
- [ ] Jackals, Karkas, Rust attack players and each other; Settlers never start fights
- [ ] Karkas are ignored by wildlife
- [ ] Rare leaders (officer, elder, foreman, warlord) spawn with their variant loadouts and don't respawn when killed
- [ ] Each faction looks like itself (blueprint apparel)
- [ ] Recruiting: settlers recruitable (come-here gesture), UN not, tribes never; max 4 per player
- [ ] Recruits: equip via inventory, command menu, get in vehicles; **do they persist across restarts?**
- [ ] Diplomacy: add a test override (presets/diplomacy.yaml), `make diplomacy`, restart → RPT
      `[DZDS] Loaded N diplomacy override(s)` and the behaviour changes
- [ ] Tolerance: give a player Karkas reputation ≥ `tolerance_reputation` (quest reward) → Karkas
      AI ignore them but not their friend; aiming at the Karkas still provokes them
- [ ] AI budget: server FPS with ~60 active AI near players; tune LoadBalancing / templates

## 4. Telemetry → GM → world
- [ ] `.ADM` contains `AI "..." (... faction="DZDS...")` hit/kill lines (LogAIHitBy/LogAIKilled)
- [ ] `GM_TELEMETRY=file GM_ADM_FILE=server/profiles make gm` follows the newest ADM
- [ ] GM digest shows "X killed N Y near Z" with display names
- [ ] Real RCON: `beserver_x64.cfg` with RConPassword/RConPort, `GM_DRY_RUN=0` → radio broadcast in game
- [ ] GM world action → queue file → `[DZDS] Spawned 1 x Wreck_Mi8_Crashed` (verify the classname) → wreck in world
- [ ] Non-allowlisted classname in a queue file is refused and logged
- [ ] Session opens with a radio war report after a `make war-turn`

## 5. War ledger in play
- [ ] Clear Jackals at Gorka (8+ kills) → `make war-turn` → Settlers hold Gorka; restart → Settler farm watch there
- [ ] Site radius (600 m) attributes kills to the right site
- [ ] Shoot the UN repeatedly → lockdown event → UN hostile next restart; expires after 7 days
- [ ] Claim a homestead → Settler patrol there; a scheduled raid arrives (`make war-status` shows it)
- [ ] `make front-plan`: closed/relocated traders and live quests make sense after control changes
- [ ] Restart cadence vs `min_hours_between_turns` (no double turns, no skipped turns)

## 6. Economy and traders
- [ ] Phase feel: walk a military base in Landfall vs Long War (`make economy PHASE=...`)
- [ ] Hoarding: stashed Tier4 weapons reduce world spawns
- [ ] Market on, ATMs off; traders reachable and voiced (Zens AI Audio, Dialogue Framework)
- [ ] Stackable ammo and nails work as trader currencies
- [ ] Trader stock persists across restarts; tune min/max stock and prices
- [ ] Quest-gated traders open after their quest (UN intro, water rights)

## 7. Quests
- [ ] Expansion generated example quests/NPCs/objectives (gives us the exact JSON schema)
- [ ] Quest NPC markers and "!" indicators are off; quest log works
- [ ] Faction reputation rewards apply (Hardline UseFactionReputation)
- [ ] Where quest completions are logged (needed to feed the ledger)

## 8. Vehicles, aircraft, mounts, trains (docs/VEHICLES.md)
- [ ] Expansion keys required to start; lockpicking; car-to-car towing; CarCover tarps
- [ ] Towing Service flatbed recovery; Simply's Car Trailer hitching
- [ ] Expansion An-2 / C-130J flyable?; RedFalcon MH-6; Arma 2 helis (do Hind/Ka-52 keep weapons?)
- [ ] LMs Planes Cessna: server load acceptable
- [ ] DayZ Horse: saddle + bridle, ride, jump, swim; Horse Expansion crafting
- [ ] HypeTrain on Chernarus rails; barrels on wagons; persistence; no derailment chaos
- [ ] TP_Apoc_M1025 mounted gun works with its ammo; BMP-3 gunner works (and VPP camera glitch)
- [ ] Vehicle Shooting from passenger seats
- [ ] ArmA2 Trucks tanker fills with water/fuel

## 9. Bases, crafting, gear
- [ ] RaG building kits and BBP both work (decide which to keep: docs/PRUNING.md)
- [ ] RaG Hunting Cabin with Code Lock; MMG storage; Zens Car Workbench recipe
- [ ] Leather Crafting from tanned hides; CookZ recipes
- [ ] Zombies bash unlocked doors (PvZmoD), day/night difference noticeable

## 10. Immersion
- [ ] Voice: proximity VON levels, radios with batteries, mask muffling; WalkieTalkie PTT
- [ ] Ambient animals, flying birds, blood trails fade within ~1 h
- [ ] Zens Immersive Login wake-up; Dark-Ish Nights lighting (lightingConfig = 2)
- [ ] No HUD markers anywhere (convoy/horde/airborne notifications disabled in their configs)

## 11. After testing
- [ ] Apply the pruning decisions (docs/PRUNING.md), rerun `make test` and this checklist's §1
- [ ] Measure server FPS/start time before and after pruning
- [ ] Choose site-marker objects in presets/world.yaml (VPP object spawner) and airdrop/hacked-crate classnames
- [ ] Set `campaign_start` (presets/economy.yaml) and run `tools/war.py reset` on day one
