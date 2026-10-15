# Badlands Relaunch + Zone-Bound Campaign: Design

**Date:** 2026-10-15 (Badlands DLC / game update 1.30 release day)
**Status:** approved in conversation section by section; awaiting review of this written spec
**Decisions by:** Blae

## 1. Intent

Relaunch Ad Aspera on **Nasdara (Badlands)** instead of Chernarus+, and reshape the PvE
campaign so that **most of the map plays like vanilla DayZ**. Human NPCs, airdrops and other
events belong to known places (faction strongholds and active warzones). The world still
changes over time and players still make progress. The game is hard enough without being
bombarded by events.

### What Blae said (the brief)
| # | Requirement |
|---|---|
| R1 | Relaunch on Nasdara. Prune mods that break or don't fit. |
| R2 | Remove the early/mid/late campaign phases entirely. |
| R3 | Default loot levels (**option A: pure vanilla**). |
| R4 | Airdrops, hordes and roaming human NPCs **extremely rare outside settlements and warzones**; normal inside them. |
| R5 | Keep progress and a living world. |
| R6 | Rely on immersive in-game voice rather than Discord. |
| R7 | Arrivals keep the random vehicle once per 24 h and the default body kit, **plus a powered radio** (and a road flare). |
| R8 | Help players find each other on a huge map without cheating or breaking immersion. |
| R9 | Arrival cargo: random but coherent, military + civilian survival gear for someone who has lived on desert roads for weeks. No piles of pots and firewood. **Includes a random, thematic firearm with meagre ammo.** |

### Decisions taken during design
| Topic | Decision |
|---|---|
| Loot | Pure vanilla Nasdara `types.xml` (option A) |
| Zone footprint | **Compact strongholds**: ~6–9 held sites + 1–2 active warzones; most towns stay vanilla |
| Outside zones | **Humans only**: no hordes, no airdrops, no crates; a rare war party is the only encounter |
| Progress | **Both**: the war ledger is the clock, Hardline reputation is the personal thread |
| Architecture | **Config containment + prune**: no new script code on the launch path except `init.c` arrivals |
| Rollout | No partial launch; hold Nasdara until the local 1.30 boot test passes |
| Start | Fresh: characters, bases, ledger **and Hardline reputation** reset |
| Radio broadcasts | Not at launch (RCON deferred). @DZDS radio bulletin is a week-one follow-up |
| Road flare | Yes, in the body kit |
| Firearm in cargo | Yes: themed, worn, meagre ammo |

### Success criteria
1. The server boots on Nasdara 1.30 with no script errors from any enabled mod (RPT clean).
2. `make test` proves every generated event/NPC position lies inside a zone, except the
   single active war-party route.
3. `make encounter-audit` over the first week shows **≤ 1 AI encounter outside zones per
   player per ~3 play sessions**.
4. `db/types.xml` on the server equals Nasdara's vanilla file except for the arrival-vehicle
   lifetime fix (and our own items from `types_dzds`, if any remain).
5. Every fresh character holds a radio with a battery fitted, tuned to the Settler net and
   switched off, plus a road flare. Players arriving on the same day wake at the same arrival site.
6. No arrival cargo holds more than one of any item (food cans: two), and every cargo has
   exactly one firearm whose ammo fits it.

---

## 2. Rollout

Clients move to 1.30 today and the server enforces the same build, so Chernarus cannot stay
playable without also moving. It is **archived, not run in parallel**.

| Stage | Work | Gate |
|---|---|---|
| **0 Archive** | SFTP snapshot of Chernarus `mpmissions/` storage, `profiles/`, `gm_state/war_ledger.json`, KAN `camps.json` into `backups/chernarus-final-<ts>/`; `git tag chernarus-final` | Archive lists and its size matches the remote |
| **1 Map data** | Read the mission folder name and world bounds from 1.30 server files; fill `maps/nasdara.yaml` (locations, roles, zone radii, `arrival_sites`); confirm there's no usable rail line (decides HypeTrain) | `make maps-check` OK |
| **2 Rebuild offline** | Sections 3–7 below; tests updated | `make test`, `make validate` |
| **3 Local boot test** | `scripts/local_server.sh install|mods|start` on Nasdara with the pruned mod list | Clean RPT; garrisons and markers at strongholds; nothing firing in the open over a ~30 min walk-through; radio range measured |
| **4 Go live** | Panel: mission → Nasdara, **whole** mod list pasted (panel trap), `vonCodecQuality 30`; `make push`; Blae restarts | Blae + one friend join via DZSA/DZGUI |
| **5 First week** | `make mod-drift` before sessions; crash watch; `make encounter-audit` | Encounter target met, or war-party chance lowered |

Panel and service actions are Blae's. Claude prepares the exact values.

**Player prerequisite:** every player probably needs to **own Badlands** to join (as with
Sakhal; not officially confirmed on release day). Blae confirms with the group before stage 4.

---

## 3. Mod pruning

A fresh start makes pruning free: no persistent item can turn into an orphan.

| Bucket | Mods | Reason |
|---|---|---|
| **Remove: design** | SF Zombie Horde Event (3689174025), DayZ-Dynamic-AI-Addon / Spatial AI (2874589934), DayZ-Expansion-Missions (2792984177) | The horde targets players anywhere and only supports exclusion zones. Spatial AI already runs at MaxAI 0. Every Expansion-Missions feature is off. |
| **Remove: stale + redundant** | Armored Vehicle Pack (2147610525), IRP Land Rover (1912237302), Crocos Quadbike (2757080411), Arma 2 Clothing Pack (2298127647), Unknown Ghillie (2074403068), InventoryInCar (2361330944) | Abandoned 2–6 years and duplicated by what remains; 1.30 adds vanilla motorbikes |
| **Conditional** | HypeTrain (3115714092) | Removed unless stage 1 finds usable rail. No rail-track objects were found in Nasdara's addons on 2026-10-15. |
| **Keep if they boot clean** | CarCover, Code Lock, BuildAnywhere_v3, Flying Birds, Leather Crafting, MMG Military Gear, MBM DuneBuggy, Horse Expansion, Ear-Plugs | Stale but each does a job; any RPT script error in stage 3 removes it |
| **Keep** | everything else | Current; core frameworks (CF, Expansion, Dabs, VPP) already have 1.30-era updates |

Rule for stage 3: a non-core mod that throws script errors is pruned. A **core** mod
(CF, Dabs, Expansion Core/AI, VPP, @DZDS) that breaks blocks the launch instead.

Expected result: 83 → ~73 mods (≤ 70 if the conditional ones go). `config/mods.yaml` entries
are set `enabled: false` with a dated `PRUNED 2026-10-15 (Badlands): <reason>` note, matching
the existing convention. Overlays for removed mods are deleted
(`zombie_horde.yaml`, `spatial_ai.yaml`, `expansion_missions.yaml`). Loadouts, traders and
types that reference removed mods' items are fixed until `make loadouts-check` passes.

---

## 4. Zones and events

### 4.1 Zone model (one source)
A **zone** = a `locations` entry in `maps/nasdara.yaml` + a radius (`zone_radius_m`, default
**400**, overridable per site). The war ledger gives each zone a state:

| State | At launch | Roles |
|---|---|---|
| **Stronghold** (held) | ~6–9 | UN: airfield/military · Rust: water/industrial · Karkas: high_ground/remote · Jackals: one road_junction camp · Settlers: 1–2 inland_town settlements (traders, KAN camps) |
| **Warzone** (contested) | 1–2 active | picked by the ledger from the front line |
| **Open country** | the rest | vanilla |

`presets/factions.yaml` gains `initial_control.nasdara` with that footprint. The existing
role minimums in `maps/_roles.yaml` still apply to *locations*. The zone count is a property of
`initial_control`, not of roles. If Nasdara has no usable coast, `coastal_town`'s minimum is
lowered per map and the `medicine` resource moves to another role (decided in stage 1).

### 4.2 Event placement

| System | Stronghold | Warzone | Open country | Config lever |
|---|---|---|---|---|
| Expansion garrisons | ✅ persistent | — | ❌ | `make patrols` (garrison templates) |
| AI War Zones | — | ✅ | ❌ | zones from ledger contested sites |
| Airdrop-Upgraded | perimeter, rare | ✅ main target | ❌ | `AirdropSettings.json` `DropZones` / `Locations` generated from zones; interval set to roughly one per ~3 h (tuned in week one) |
| Animated heli crashes | — | ✅ | ❌ | `Use_World_Generated_Locations 0`, `Use_Random_Generated_Crash_Sites 0`, `CRASH_POSITIONS_LIST` = warzone points; delay 3600–7200 s |
| Vanilla CE heli crashes | vanilla | vanilla | vanilla | untouched: vanilla behaviour |
| BS Hacked Crate | military strongholds | ✅ | ❌ | static/dynamic crate lists from zones; tick 3600 s |
| KAN camps | Settler settlements | — | ❌ | `presets/kan_camps.yaml` (roamers stay 0) |
| Jackal ambush / roam | ❌ | ✅ (ambush on warzone approaches, inside radius) | ❌ | `presets/factions.yaml` templates |
| Moving AI Convoy | departs/arrives | departs/arrives | **only as a war party** | routes = stronghold ↔ stronghold, enabled only when the ledger picks a convoy |
| Zombie horde | — | gunfire draws vanilla infected | vanilla infected | mod removed |

### 4.3 War parties: the only open-country encounter
- `make war-turn` (each restart) picks **zero or one** movement with chance
  `war_party_chance` (start **0.35**): a patrol from a stronghold toward a warzone, or a convoy
  between two strongholds of the fuel/industry holder.
- **At most one active map-wide.** Its route is the only generated position allowed outside a
  zone. Patrol templates of kind `roam`/`ambush` outside zones are removed; `route` templates
  become war-party candidates instead of always-on patrols.
- Intercepting a war party counts against that faction's strength in the ledger.
- Once the bulletin exists, the next morning's report hints at the movement (section 6.1).

### 4.4 Guards
- **Placement test** (pytest): every position emitted by every generator (drop zones, crash
  list, crate sites, KAN camps, garrison waypoints, War Zones spawns, convoy endpoints) is
  within its zone radius. The single war-party route is the only allowed exception, and the
  test asserts there is at most one.
- **`make encounter-audit`** (new tool): reads `.ADM` AI hit/kill lines and player positions,
  counts AI encounters outside every zone, and reports them per player per play-hour. Target
  ≤ 1 per player per ~3 sessions. When it's over target, lower `war_party_chance`.

---

## 5. Economy and progress

### 5.1 Economy: pure vanilla
| Item | Change |
|---|---|
| `presets/economy.yaml` | delete `campaign_start`, `phases`, `expected_players`, `population_brackets`, `protected_categories`, `war`, `hoarding`. Keep `script_vehicle_lifetime` and `globals: {}` |
| `tools/economy.py` | remove phase, population, war and hoarding scaling. What's left: copy `db/types.xml.vanilla` → `db/types.xml`, apply the arrival-vehicle lifetime, merge `types_dzds` |
| `Makefile` | drop `PHASE=` |
| `presets/types_dzds.yaml` | **remove the vehicle-part boosts** (SparkPlug, batteries, radiator, H7, tire kit, blowtorch): they're above-vanilla loot. Keep the mechanism for our own items |
| Modded items | author defaults (unchanged) |
| Docs | `docs/ECONOMY.md`, `docs/LIVING_WORLD.md`, `docs/SPEC.md` phase references updated |

### 5.2 Progress
| Thread | Mechanism (existing, retargeted) |
|---|---|
| The front line moves | `make war-turn` each restart: off-screen fights resolve, sites flip, warzones move |
| The world shows it | site markers per holder (`make dzds-profile`), garrison loadouts per holder, traders open/move/close (`make front-plan`) |
| Players tip it | wipe a garrison or win a warzone → the site flips; intercept a war party → that faction loses strength |
| Personal standing | Hardline reputation (reset) unlocks faction traders/quests; ≥ 50 = tolerance (`tolerance_reputation`) |

`make prepare-restart` no longer runs economy phase logic. Everything else in it stays.

---

## 6. In-game voice and finding each other

### 6.1 Voice
| Change | Where |
|---|---|
| Every new character gets a **PersonalRadio** with a **Battery9V** attached, tuned with `SetFrequencyByIndex(settler_net_index)`, **switched off** | `init.c` arrivals, after vanilla `StartingEquipSetup` |
| `vonCodecQuality` 20 → **30** | `config/local_serverDZ.cfg` **and** the panel (rule 10) |
| Settler net = one documented frequency index; other channels free for private groups | `presets/arrivals.yaml: radio.settler_net_index` + player page |
| Measure vanilla handheld range in stage 3 and document it | `docs/` + player page |
| **Week-one follow-up (not launch):** @DZDS radio bulletin. `war-turn` writes `profiles/DZDS/bulletin.json`; at restart @DZDS delivers it only to players holding a powered radio, with no RCON | separate spec |

WalkieTalkie Push-To-Talk (already enabled) gives the radio its own talk key and click sounds.
The base radio (vanilla loot, car battery) is the long-range set.

### 6.2 Body kit
Vanilla default kit **+ the radio above + one Roadflare**, for every new character,
whether or not the vehicle cooldown allows a car.

### 6.3 Finding each other (all diegetic)
| Mechanism | Rule |
|---|---|
| **Refugee column** | All **first arrivals on the same real-world day** (server-local date) use the **same arrival site**, picked deterministically from the date. `points_per_site` rises to ≥ 8 so several cars fit. |
| **Arrival sites ring the Settler settlement** | `arrival_sites` within ~3–5 km of the starting Settler stronghold, on roads, outside every non-Settler zone |
| **Respawn near where you died** | Later characters wake at a road point **2–5 km** from the previous character's death position. If none is free, widen to 8 km, then fall back to any road point. Military, airfield and Jackal exclusions still apply. The death position is recorded in the arrivals ledger. |
| Radio + landmarks | open Settler net |

**Ruled out (pillar 6):** map markers, spawn-selection menus, teleport-to-friend, showing your
position on the map.

---

## 7. Arrival cargo: archetype kits

Replaces `PickGear()`'s up-to-40 weighted draws with replacement.

### 7.1 Model
- Each car-granting arrival rolls **one archetype**. The archetype fills **slots**. Within a
  slot, items are drawn **without replacement** (`max_per_item` 1; food cans 2).
- Total ≈ **10–16 items** plus the firearm and its ammo. `max_cargo_items` stays as a hard cap.
- Item health stays road-worn (`item_health` 0.45–0.85); firearm health 0.45–0.70.

| Archetype (weight) | Flavour |
|---|---|
| Deserter (30) | military clothing pieces, canteen, compass, field dressing, combat knife |
| Trucker (25) | work clothing, wrench + tire kit, part-full jerrycan, duct tape, large water container |
| Nomad / herder (25) | head wrap, rope, knife, sewing kit, dried food, water bottles |
| Townie on the run (20) | civilian clothing, flashlight + battery, painkillers, canned food, backpack |

| Slot | Count |
|---|---|
| clothing / bag | 2–3 |
| water | 1–2 |
| food | 2–4 |
| medical | 1–3 |
| tools | 2–3 (always one cutting tool) |
| archetype extra | 1–2 |
| camp | 0–1 (at most one cooking or fire item) |
| **firearm** | **exactly 1** |

### 7.2 Firearm
- One weapon from the archetype's list, using vanilla low-tier weapons only (Tier 1–2 usage;
  no military rifles). Examples, to be confirmed against Nasdara's `types.xml` in stage 1:
  Deserter → Makarov / CR-75 / worn SKS · Trucker → BK-133 / sawn-off IZH-43 ·
  Nomad → Mosin / BK-18 / crossbow · Townie → revolver / Derringer.
- **Meagre ammo:** either the weapon's magazine **partly filled** (2–5 rounds) **or** 3–8 loose
  rounds. **No spare magazines.**
- Only with a granted car, so the 24 h cooldown bounds it.

### 7.3 Config shape
`presets/arrivals.yaml` replaces `gear:` with `archetypes:` (weight, slot lists, firearm list
with per-weapon ammo and magazine classnames). `tools/arrivals.py` compiles it, and `init.c`'s
`FillCargo` is rewritten to the slot model.

### 7.4 Tests
- Every classname exists in Nasdara's vanilla `types.xml` or an enabled mod's types.
- Each firearm's ammo/magazine is compatible (checked against a curated compatibility table in
  the preset, since config.bin compatibility is not readable offline).
- A simulated fill of N = 1000 kits: no item over its cap, slot counts in range, exactly one
  firearm per kit, at most one camp item.

---

## 8. Testing summary
| Layer | What |
|---|---|
| Unit (pytest) | zone placement invariant; war-party ≤ 1; economy output == vanilla + lifetime; kit simulation; classname existence; firearm–ammo table; maps-check for Nasdara |
| Config | `make validate` (JSON/XML) |
| Local boot (stage 3) | clean RPT; garrisons/markers present; no events in open country over ~30 min; radio tuned + powered on spawn; two test arrivals on one date share a site; respawn lands 2–5 km from death |
| Live (week one) | `make encounter-audit`, `make mod-drift`, crash watch |

## 9. Out of scope
- RCON and the GM radio path (deferred by Blae).
- @DZDS radio bulletin (week-one follow-up, own spec).
- Horde spawn-position code override (moot: the mod is removed).
- Base-respawn (bed/flag) mechanics.
- Any change to AI accuracy bounds (rule 5 unchanged).

## 10. Risks
| Risk | Mitigation |
|---|---|
| Badlands DLC ownership required to join | Blae confirms with players before stage 4 |
| Core mod breaks on 1.30 | Stage 3 blocks the launch; `make verify-mods` daily |
| Expansion route patrols spawn behaviour near players is unverified on the war-party model | [test] in stage 3; fall back to convoy-only war parties |
| Too few free road points for the refugee column | `points_per_site ≥ 8`; spill to the next-nearest site |
| Archetype item names differ on Nasdara | classname-existence test against Nasdara `types.xml` |
