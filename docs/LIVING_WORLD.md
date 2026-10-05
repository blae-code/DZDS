# Living World Design: Factional War Over Resources

Goal (spec pillar 1): the map is never empty or static. Armed factions fight each other over
fuel, arms, food and medicine whether or not players are watching. Players can stay out of
it, profit from it, or tip it.

This doc is grounded in Expansion AI's actual source code (`salutesh/DayZ-Expansion-Scripts`,
read 2026-10-05) and the Workshop pages of every mod named. Unverified assumptions are marked
**[test]** and belong on the local-server checklist.

---

## 1. Engine facts that shape the design

| Fact (from source) | Consequence |
|---|---|
| Factions are compiled classes; relations are hard-coded in `IsFriendly()`. No JSON faction config. | We **map** our factions onto built-ins (West/East/Raiders/Civilian). Custom relations need our own small script mod (§6). |
| Built-in relations: West↔East hostile, both friendly to Civilian; Raiders hostile to all; Civilian friendly to all. | West vs East is a ready-made two-army war, with Raiders as a third party and Civilians as bystanders. |
| Patrols choose a faction by name, with waypoints, `Persist`, `RespawnTime`, `Chance`, `NumberOfAI(Max)`, loadout, loot-on-death, per-patrol accuracy. | Every garrison and offensive is just a generated `AIPatrolSettings.json` entry. |
| Patrols spawn only when a player is within `MaxDistRadius` (default 1000 m) and despawn after `DespawnTime`. | **Nothing simulates the war off-screen.** We need an abstract layer that does (§3, war ledger). |
| `LoadBalancingCategories` cap concurrent AI per category. | A hard AI budget is enforceable in config. |
| `LogAIHitBy` / `LogAIKilled` write AI hits and kills into the vanilla `.ADM`, with `faction="..."` in the prefix. | The GM can read who killed whom, and where, from the logs it already tails. Parser done. |
| `AISettings.PlayerFactions` assigns players a faction on connect. | Players can be aligned with a side (decision 1). |
| Defaults: `AccuracyMin 0.35`, `AccuracyMax 0.95`, `ThreatDistanceLimit 1000`. | Calibration matters; `make calibrate` sets global values and clamps per-patrol overrides. |
| Vanilla zombies aren't in the faction system; they attack every human. Expansion's "Infected" faction is a separate human-AI faction. | Zombies stay the universal enemy, as the spec wants. |

---

## 2. The factions

*Updated 2026-10-05 to the user's Faction Blueprint. Full detail: `docs/FACTIONS.md`.*

| Faction | Holds (map roles) | Character |
|---|---|---|
| **Frontier Settlers** (players) | inland towns, player bases | The player's settlement network; recruitable |
| **UN Peacekeepers** | airfields, military, towers | Armed neutrality; defend Green Zones |
| **Jackal Cohort** | road junctions (nomadic) | Highway raiders; push and flank |
| **Karkas Clan** | high ground, remote | Patient mountain marksmen; wildlife ignores them |
| **Rust Syndicate** | industry, water | Cartel guarding wells, fuel, rail |
| Infected | everywhere | Drawn by gunfire; punish long firefights |

The three tribes fight each other (blood feud), the UN fight the tribes, and everyone fights
zombies. Custom classes in @DZDS (`mods/DZDS`); tests check `presets/factions.yaml` against them.

---

## 3. Three timescales

```
 CAMPAIGN (each restart, 4–6 h)         SESSION (minutes)              MOMENT (seconds)
 ┌────────────────────────────┐   ┌──────────────────────────┐   ┌──────────────────────────┐
 │ War ledger (GM, local PC)  │   │ GM daemon                │   │ Mods on the server       │
 │ - who holds which site     │   │ - tails .ADM (+factions) │   │ - Expansion patrols      │
 │ - faction strength/stocks  │──▶│ - radio chatter about    │   │ - AI War Zones battles   │
 │ - resolve off-screen fights│   │   fights near players    │   │ - convoys on roads       │
 │ - regenerate configs  ─────┼─┐ │ - later: trigger events  │   │ - heli crash, airdrops,  │
 └────────────▲───────────────┘ │ └────────────▲─────────────┘   │   hacked crates          │
              │ kills/losses     │ SFTP push before restart │    │ - zombies, birds, blood  │
              │ from .ADM        └──────────────────────────┼───▶└────────────┬─────────────┘
              └─────────────────────────────────────────────┴─────────────────┘
```

### 3a. Moment: what you see and hear (mods)
- **Garrisons**: `Persist: true` patrols with `Behaviour: HALT`/`ALTERNATE` at sites a faction
  holds, plus `RespawnTime: -1` so a wiped garrison stays wiped until the ledger reinforces it.
- **Offensives**: patrols with `LOOP`/`ONCE` waypoints from a faction's site toward a contested
  or enemy site, so they meet rival patrols on the road.
- **Front-line battles**: **AI War Zones** at contested sites. Two teams per zone (our two
  disputing factions), "domination" lets the stronger side push, smoke and explosions show the
  battle's movement from a distance, and players can capture spawn points to tip it.
- **Logistics**: **Moving AI Convoy**. The holder of fuel and industry runs supply convoys
  between its sites. Players (only players) can stop one and loot the cargo. Turn the
  on-screen pop-ups and map markers off; the GM's radio carries the news instead.
- **Contested loot**: AnimatedDynamicHelicopters crash sites (with Expansion `EventCrashPatrol`
  guards), BS HackedCrate (alarm and AI waves), Airdrop-Upgraded.
- **Ambient life**: DayZ-Dynamic-AI-Addon (the spec's Spatial AI, renamed) for a few
  wanderers near players; Survivor patrols in towns; Flying Birds scatter at gunfire; Zens Blood
  Trail lets you track the wounded; zombies bang doors and converge on firefights.

### 3b. Session: the GM daemon (exists, extended today)
- Digest now includes "*West killed 2 East near Gorka*" tallies from AI kill logs.
- Radio chatter (`say -1`) reacts to fights near players and summarises distant ones:
  *"...UN checkpoint at Gorka reports Jackal vehicles on the north road..."*.
- Later, with the @DZDS mod (§6): spawn reinforcements and events right away instead of
  waiting for a restart.

### 3c. Campaign: the war ledger (next build step)
A persistent state file on your PC (`gm_state/war_ledger.json`), advanced once per restart:

1. **Read outcomes** of the last cycle from `.ADM`: kills by faction pair and place, which
   garrisons were wiped, convoys stopped, sites where players killed defenders.
2. **Resolve off-screen fighting**: for contested sites no player went near, roll an outcome
   weighted by each side's strength (patrols despawn without players, so this is how the war
   keeps moving while you're offline).
3. **Update control**: a site whose garrison was wiped flips to the attacker, or becomes
   contested if nobody holds the ground.
4. **Income**: held sites yield resources by role (`presets/factions.yaml: resources`):
   fuel → more convoys and vehicle patrols; arms → better loadouts (accuracy stays in
   bounds); food → bigger squads and faster reinforcement; medicine → tougher garrisons.
5. **Regenerate configs** from the new state: `AIPatrolSettings.json` (garrisons and
   offensives), AI War Zones zones (contested sites, sides, domination), convoy routes and crews.
6. **Push** via `sync.sh` a few minutes before the GSP's scheduled restart (configs load at
   startup). After the restart, the GM broadcasts a morning war report.

Why per restart: it needs **no custom server code**, only Expansion's existing config files.
Real-time control can come later.

**How players move the war**: wipe a Rust Syndicate well crew and the well flips at the next
restart. Ambush a Jackal raiding convoy and the Jackals lose supplies. Ignore the map for a week and you come
back to a different front line.

---

## 4. Diegetic presentation (pillar 3)
The war is never shown on a HUD:
- **Radio**: GM broadcasts are the news source. Note that `say -1` appears as on-screen chat.
  @DZDS could later deliver it only to players holding a powered radio.
- **The world itself**: bodies, burnt vehicles, smoke columns over contested towns, birds
  scattering, distant gunfire, blood trails, changed garrison uniforms after a site flips.
- **Disable** every mod's notification and marker features (convoy, KOTH, horde, airborne
  warnings) wherever the config allows.

---

## 5. Performance budget (1–4 players, GSP CPU)
Expansion AI is server-CPU heavy (each bot is a simulated player). Starting budget, to tune
on the local server:

| Category | Max concurrent AI | Mechanism |
|---|---|---|
| Garrisons + offensives near players | 24 | `LoadBalancingCategories` |
| War Zones (1 active zone) | 16 | War Zones' max concurrent zones, spawn caps |
| Convoy crew | 8 | one convoy at a time |
| Event guards (crash, crate) | 8 | per-event counts |
| Ambient wanderers (Dynamic-AI-Addon) | 4 | its config |
| **Total** | **~60** | adjust after measuring server FPS |

---

## 6. The @DZDS mod (later, small, our own)
A ~200-line Enforce Script mod would unlock what config can't do:
1. **Custom factions** with exact relations, e.g. players as `DZDSSurvivors`: armies tolerate
   you until you shoot them or trespass, Raiders always hostile (`eAIRegisterFaction` + `IsFriendly`).
2. **GM command queue**: the server polls a JSON file in `$profile:` (uploaded via SFTP) and
   spawns patrols or events right away, replacing the spec's undefined "Enforce RestApi".
3. **Extra telemetry**: vehicle crashes, site entries, convoy status into the `.ADM` or a log.
4. **Radio-only broadcasts**: deliver GM messages only to players holding a powered radio.

Requires DayZ Tools to pack and sign. Worth building after the per-restart loop works.

---

## 7. Open decisions

1. **Where do players stand?** *Resolved 2026-10-05 (Faction Blueprint):* players are the
   Frontier Settlers (`PlayerFactions: [DZDSSettlers]`), with reputation to earn with the UN
   and tribes. See `docs/FACTIONS.md`. Original options, superseded:
   a) Unaligned (default). Expansion's targeting of factionless players needs testing **[test]**.
   b) `PlayerFactions: ["West"]`: you're CDF-aligned, ChDKZ and Raiders hunt you. Strong
      story, less neutral.
   c) Custom player faction via @DZDS: neutral until provoked. Best fit for PvE, needs the mod.
   *Recommendation*: start with (a) and test; move to (c) when @DZDS exists.
2. **Expansion Quests for faction tasks**: *Resolved: yes* (with Hardline for faction
   reputation, markers and HUD off). Design: `docs/QUESTS.md`.
3. **Escalation assets**: when a faction dominates, unlock Airborne AI (paratroopers) or BS
   Patrol Tank (BTR) for it? Heavy and dramatic; optional.
4. **Airdrops**: keep Airdrop-Upgraded, or move to Expansion-Missions (same ecosystem, fewer
   authors to wait on after 1.30)?
5. **Restart cadence**: every 4 h means 6 war turns a day; every 6 h means 4.

---

## 8. Build order
1. Calibrate and enable AI logging (done in presets; `make calibrate` on first real config).
2. Faction-aware telemetry in the GM (done).
3. **War ledger + config generators** (`AIPatrolSettings.json`, War Zones, convoy routes),
   testable offline against the ADM simulator extended with AI faction lines.
4. Local-server test: AI budget, faction behaviour toward players **[test]**, War Zones and
   convoy configs, then the whole Phase 4 checklist.
5. @DZDS mod.
