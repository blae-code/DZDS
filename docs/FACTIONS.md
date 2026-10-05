# Factions: Blueprint, Engine Reality, Nuance, Recruitment

Source of design: the user's *Faction Architecture & Configuration Blueprint* (2026-10-05).
Implementation: `presets/factions.yaml` (intent + behaviour profiles, tested) and
`mods/DZDS/Scripts/3_Game/DZDS/Factions/DZDSFactions.c` (the actual faction classes).
Engine facts are from reading Expansion AI's source; **[test]** = confirm on the local server.

---

## 1. The factions

| Faction | Class (@DZDS) | Interim built-in | Players | Recruitable | Holds |
|---|---|---|---|---|---|
| **Frontier Settlers** (players + settler AI) | `DZDSSettlers` | Civilian | members | **yes** | farms, villages, player bases |
| **UN Peacekeepers** (Task Force Blue Shield) | `DZDSPeacekeepers` | Guards | armed neutrality | no | airfields, radar/relay towers, Green Zones |
| **Jackal Cohort** | `DZDSJackals` | Raiders | hostile | no | road junctions (nomadic) |
| **Karkas Mountain Clan** | `DZDSKarkas` | Shamans | territorial hostile | no | ridges, high ground, remote passes |
| **Rust Syndicate** | `DZDSRust` | Mercenaries | hostile | no | industry, wells, dams, refineries |
| Infected | (vanilla) | – | hostile | – | everywhere |

The three tribes are mutually hostile (the blood feud). The UN are hostile to the tribes and
neutral to Settlers. Zombies attack everyone.

---

## 2. What changed from the blueprint, and why

| Blueprint | Reality in Expansion | What we do |
|---|---|---|
| `profiles/ExpansionMod/AI/Factions/Faction_*.json` with `HostileFactions` lists | **Doesn't exist.** Factions are compiled script classes; relations live in `IsFriendly()` | Our own small mod **@DZDS** defines the five factions as real classes with exactly the blueprint's relations |
| System identifiers `Survivors`, `Bandits` | No such built-in factions | Custom names `DZDSSettlers`, `DZDSKarkas`, ... (until @DZDS is built, the closest built-ins stand in: see the table) |
| `PlayerIsFriendly`, `CanBeRecruited` per faction | Player standing comes from the **player's** faction relations; recruitment is global settings + "doesn't see you as an enemy" | Players join `DZDSSettlers` (`PlayerFactions`); `CanRecruitFriendly` on, `CanRecruitGuards` off: exactly Settlers recruitable, UN not, tribes never |
| `SightRange`, `SightAngle`, `HearingRange`, `HeadshotDamageMultiplier`, `CanClimbLadders`, `DisallowedWeapons` | Not Expansion settings | Closest real knobs: `ThreatDistanceLimit`, `NoiseInvestigationDistanceLimit` (≈ hearing), per-patrol `HeadshotResistance`, `PreventClimb`, loadouts |
| Per-faction accuracy (e.g. Settlers 0.22–0.38) | Fine, set per patrol | Kept. Added separate **per-patrol bounds** (0.20–0.35 / 0.35–0.52) next to the global ones, so factions can differ while nobody becomes a sniper |
| Global AISettings §4E | Real keys kept: AccuracyMin/Max, ThreatDistanceLimit, DamageMultiplier, SniperProneDistanceThreshold, Vaulting | `presets/expansion_ai_calibration.yaml` |

**Interim mode** (before @DZDS exists) is close but not exact. Civilians never start fights
(the blueprint's Settlers would), there's no player faction yet (every AI treats unaligned
players as hostile; UN Guards only react to close threats), and Guards are hostile to Civilians.

---

## 3. Adding nuance: five layers, from cheapest to deepest

### Layer 1: Behaviour profiles (config only, done)
Each faction gets its own patrol profile in `presets/factions.yaml`, using real Expansion
patrol fields:

| | Movement | Combat | Personality |
|---|---|---|---|
| **Jackals** | `ROAMING`, jog, loose random formation | come to gunfire (300 m), **flank outside combat**, low accuracy | strip bodies (`LootingBehaviour: ALL`) |
| **Karkas** | `HALT` on ridges, crouched, walk even under fire | patient long shots, go prone over 120 m | take weapons only |
| **Rust** | `ALTERNATE` along perimeters, tight wall formation | hold the line, armoured (takes 10% less damage) | standard |
| **UN** | `HALT_OR_ALTERNATE` at checkpoints, disciplined column | best accuracy, react only to close/strong threats (Guard trait) | **can't be looted** |
| **Settlers** | `HALT_OR_LOOP` around farms, sprint when threatened | poor marksmanship, short engagement range | scavenge food |

### Layer 2: Identity you can see (config)
Faction loadouts from the blueprint's apparel/weapon lists: UN blue helmets, Rust hi-vis
and welder masks, Karkas fur and ghillie, Jackal gas masks and skull bandanas. You identify
friend or foe by **looking**, with no markers. Also per-faction `LootDropOnDeath`: Rust bodies
carry tools and fuel, Karkas carry hides and arrows. (Loadout JSON is authored once
Expansion generates its example loadouts on the local server.)

### Layer 3: Places and schedules (config + war ledger)
- **Where** each faction appears follows its archetypes: Karkas on `high_ground`, Rust on
  `water`/`industrial`, Jackals on `road_junction` ambush routes, UN at airfields and towers.
- **When**: the ledger can vary patrol `Chance` and size by restart (e.g. Jackals raid more at night
  if a night-time restart cycle exists; Rust reinforce wells when water is contested).
- Jackals crew the **Moving AI Convoy** raiders; UN crew aid convoys that Jackals hunt.

### Layer 4: Reputation (Expansion Quests + Hardline)
Per-faction reputation already exists (`FactionReputationRewards`). Use it to make
relationships feel earned:
- UN reputation unlocks Green Zone services (trader/medic NPCs, safe storage) and UN quests.
- Settler reputation unlocks better recruits (veterans with better gear).
- Tribe reputation via "neutral" deals: trading water with the Rust Syndicate, or returning a Karkas
  hunter's remains, lowers hostility **in story and quest access**.

### Layer 5: Reputation-aware hostility (@DZDS: built, `DZDSTolerance.c`)
`IsFriendlyEntity(other, factionMember)` is evaluated per player, so @DZDS can make a faction
tolerate **specific players**: e.g. the Karkas let a player pass their ridges once that player's
Karkas reputation is high enough, or the Rust Syndicate stops shooting players who paid their
"water tax" this restart. The stub is in the design, not in code yet. The Hardline reputation API
needs reading first, so the faction file stays compile-safe.

**Also adds nuance for free:** gunfire draws zombies (PvZmoD, day/night), so long tribal
firefights turn into three-way battles exactly as the blueprint describes.

---

## 4. Recruiting friendly AI (exists in Expansion)
From Expansion's source:
- **Recruit**: look at a friendly AI and use "Recruit" (your character does the *come here*
  gesture). Conditions: `CanRecruitFriendly`, under `MaxRecruitableAI`, the AI isn't passive or
  invincible, doesn't belong to another player, and doesn't consider you an enemy.
  Guards-type (UN) need `CanRecruitGuards` (off).
- **Equip**: open a recruit's inventory to hand over gear.
- **Dismiss**: release them.
- **Command menu**: formations (column, file, vee, wall, circle, star...), follow / go to /
  waypoints / hold / roam / flank, stance (erect, crouch, prone), pace (walk, jog, sprint),
  **get in vehicle**, and loot. It's a menu (UI), the one non-diegetic part.
- **Settings**: `CanRecruitFriendly: true`, `CanRecruitGuards: false`, `MaxRecruitableAI: 4`
  per player (`presets/overlays/expansion_ai.yaml`). Four recruits per player keeps the AI
  budget sane with 1–4 players.

### Making recruitment meaningful
- **Where recruits come from** (blueprint): wanderers at neutral water points, settlers rescued
  from tribal ambushes, deserters. Implement as Settler patrols spawned in those situations
  (Jackal ambush on a settler group = rescue opportunity).
- **Quests as the gate**: "prove yourself" quests before a settler camp's veterans follow you.
- **Garrisons**: tell recruits to hold position on your watchtowers (command menu waypoint/hold).
  [test] whether recruits persist across restarts. Expansion patrols have `Persist`, but
  recruited groups may not. If they don't, @DZDS or KAN Survivor NPC camps (persistent camps
  with guards and builders) fill the "settlement garrison" role.
- **KAN Survivor NPC Camps** (enabled) may give settlements builders, looters and guards that
  persist and get raided, which is the blueprint's settlement network. Evaluate how its camps'
  factions map to `DZDSSettlers`.

---

## 5. Nuance toolkit (built 2026-10-05)

### a) Squad types per faction (`patrol_templates`, `make patrols`)
Each faction has 2–3 squad templates with their own size, chance, respawn and behaviour
overrides, placed at the sites the faction holds (or contested sites):

| Faction | Squads |
|---|---|
| Settlers | **farm watch** (2–3, guards the homestead), **scavenger party** (2–4, walks to the next settler town and back, loots everything) |
| UN | **checkpoint** (3–4, HALT), **patrol route** (4–6, between UN sites), **officer detail** (2, rare, never respawns, better aim, officer loadout) |
| Jackals | **raid party** (4–7, roams contested ground), **ambush** (3–5, crouched at road junctions), **warband** (5–7, rare, warlord loadout) |
| Karkas | **ridge watch** (2–3, PRONE overwatch), **hunting party** (2–4, roams locally, takes food), **elder marksman** (1, rare, best long-range shot) |
| Rust | **well crew** (3–5), **enforcer patrol** (4–6, between Rust sites), **foreman** (1–2, rare, armoured) |

Rare leaders with `respawn: -1` matter: kill the Karkas elder and that ridge stays leaderless
until the war ledger decides otherwise. `tools/patrol_gen.py` writes them into
`AIPatrolSettings.json` using only Expansion's own field names and sentinels (or with
`INTERIM=1`, the built-in factions until @DZDS is built). Loadout variants follow the pattern
`DZDS_<Faction>_<rank>` (e.g. `DZDS_Karkas_elder`). The loadouts get written once Expansion has
generated its example files.

### b) Dynamic diplomacy (`presets/diplomacy.yaml`, `make diplomacy`)
@DZDS now reads `$profile:DZDS/diplomacy.json` at server start, and every faction's
`IsFriendly()` checks it before the blueprint defaults. Relationships can now **change over
the campaign**:
- **Truces**: Karkas and Rust stop shooting each other to push the Jackals off a pass.
- **Betrayal**: the truce expires (`until:`), or the ledger breaks it after an incident.
- **UN lockdown**: after a shooting near a Green Zone, override Settlers→UN to hostile for a
  week. (For players, Expansion asks the player's faction, so that's the direction to flip.)
- **Earned tolerance**: a Settlers→Karkas override (friendly) after a reputation quest chain
  lets players cross Karkas ridges for good. This is a whole-group version of layer 5.

Entries expire automatically; the GM can announce each change by radio.

### c) Faction radio voices
`radio_voice` (tone + sample line, from the blueprint's section 5 broadcasts) is fed into the GM's
system prompt, so intercepted chatter sounds like the faction it came from: UN procedural, Jackals
jeering, Karkas sparse and proverbial, Rust corporate-menacing, Settlers frightened and neighbourly.

### d) One command between restarts
`make prepare-restart` runs economy → diplomacy → patrols → overlays → calibrate → validate.
Review `git diff`, then `make push`.

## 6. GM radio identities (blueprint §5)
The GM prompt (`src/gamemaster/llm.py`) now knows all five factions. The blueprint's sample
broadcasts (UN checkpoint advisory, Jackal raid intercept, Karkas warning, Rust incident) are
the style target, and also the first scripts to record as radio clips for the @DZDS audio library
(docs/IMMERSION.md §1).

## 7. Next steps
1. Pack + sign @DZDS (`mods/README.md`), boot the local server, confirm the five factions
   register and the diplomacy file loads ("[DZDS] Loaded N diplomacy override(s)" in the RPT).
2. Let Expansion generate example loadouts; author `DZDS_<Faction>` + rank variants.
3. [test] generated patrols: ground placement of y=0 waypoints, HALT/ROAMING behaviour, budget.
4. Playtest recruitment: persistence, vehicles, garrisons [test].
5. ~~War ledger~~ built: live control drives patrols and diplomacy (docs/WAR_LEDGER.md).
6. ~~Per-player reputation-aware hostility~~ built (`DZDSTolerance.c`, Hardline
   `Expansion_GetFactionReputation`; threshold `tolerance_reputation` in presets/world.yaml) [test].
