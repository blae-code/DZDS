# Quests: Tied to the Faction War

Decision (2026-10-05): quests are in, if polished. Choice: **DayZ-Expansion-Quests**
(1.1M users, maintained by the Expansion team, built on the same AI we use) +
**DayZ-Expansion-Hardline** (needed for per-faction reputation). Facts below are from the
Expansion source (`DayZExpansion/Quests`, `DayZExpansion/Hardline`).

## What Expansion Quests can do (from source)
- **Objective types**: TARGET (kill), TRAVEL, COLLECT, DELIVERY, TREASUREHUNT,
  **AIPATROL** (defeat a patrol), **AICAMP** (clear a camp), **AIESCORT** (escort an NPC),
  ACTION, CRAFTING. Objectives can be sequential.
- **Faction hooks**:
  - `RequiredFaction`: only members of a faction see the quest.
  - **`FactionReward`: completing the quest moves the player into a faction.**
  - `FactionReputationRequirements` / `FactionReputationRewards`: per-faction reputation
    gates and rewards (needs Hardline's `UseFactionReputation`, and AI loaded).
- **Structure**: pre-quests, follow-up chains, repeatable/daily/weekly, group quests,
  cancel on death, item rewards (pick one / random), quest items handed out at start.
- **Quest givers**: NPCs (optionally Expansion AI with a loadout and waypoints) or objects.
- **Files**: quests, objectives and NPCs live in `$profile:ExpansionMod/Quests/`
  (`Quests/`, `Objectives/<Type>/`, `NPCs/`) as JSON. Quest settings are in
  `$profile:ExpansionMod/Settings/QuestSettings.json`; Hardline settings are in
  `$mission:expansion/settings/HardlineSettings.json`.

## Keeping it diegetic (`presets/overlays/`, `make overlays`)
| Setting | Value | Why |
|---|---|---|
| `CreateQuestNPCMarkers` | false | No map pins on quest givers; you hear about them |
| `UseQuestNPCIndicators` | false | No "!" over heads |
| `EnableQuestLogTab` | true | The quest log works as your journal |
| `ShowHardlineHUD` | false | No reputation HUD |
| `EnableItemRarity` | false | No rarity colours |
| `UseReputation` | false | No generic humanity score; faction reputation only |

Accepting and turning in quests still uses Expansion's quest menu. That's the one UI
concession. Dialogue Framework (later, needs Market) could turn it into conversation.

## Where players stand (Faction Blueprint, docs/FACTIONS.md)
- Players **are** the Frontier Settlers (`PlayerFactions: [DZDSSettlers]` once @DZDS is built).
  No enlistment needed; quests build **reputation** instead.
- **UN reputation** (humanitarian quests): unlocks Green Zone services, UN quest lines and
  better standing at checkpoints.
- **Settler reputation**: settlers' quests (defend the farm, find the missing caravan) unlock
  better recruits and settlement upgrades.
- **Tribe reputation** through risky neutral deals (trade water with the Rust Syndicate,
  return a Karkas hunter's remains): opens tribe quests and, later, reputation-aware
  tolerance in @DZDS (FACTIONS.md §3 layer 5).
- `FactionReward` stays available for story beats (e.g. a Settler defecting to the UN).

## Quest catalogue (mapped to the war)
| Quest | Type(s) | Giver | Effect on the war ledger |
|---|---|---|---|
| Fuel run | DELIVERY (jerrycans) | UN quartermaster | +fuel for the UN; UN reputation |
| Medical supplies | COLLECT → DELIVERY | UN field medic | +medicine; UN reputation |
| Clear the Jackal camp | AICAMP (Jackals) | Settler elder | Jackals lose a site; recruits join |
| Aid convoy escort | AIESCORT | UN logistics officer | convoy arrives → +supplies; Jackals lose a raid |
| Recon | TRAVEL to a contested site | UN radio operator | reveals tribal strength (GM radio report) |
| Break the siege | AIPATROL at a contested well/site | Settler or UN officer | site flips at next restart |
| Lost cache | TREASUREHUNT | rumour from a Settler | loot, no war effect |
| Water rights | DELIVERY (trade goods) | Rust Syndicate broker | Rust reputation; settlement water access |
| Field repairs | CRAFTING / ACTION | mechanic NPC | vehicle parts reward (fits Vehicles module) |

## Making quests follow the war (war-ledger integration)
Quests are JSON in `$profile:`, like the patrols, so the war ledger can **regenerate them each
restart**:
1. **Quest givers move with the front.** A quartermaster spawns at sites their faction
   currently holds. If the Green Zone falls, the UN quartermaster is gone (and a Jackal
   fence may be there instead).
2. **Objectives point at the current front.** "Break the siege" always targets a site that is
   contested right now. Recon targets whatever the enemy just took.
3. **Completions feed back.** Expansion logs quest events. The GM reads completed quests
   (deliveries, escorts, cleared camps) and applies their effects to the ledger.
   **[test]** where and in what format quest completions are logged.

## Build order
1. On the local server, let Expansion generate its example quests, NPCs and objectives. That
   gives us the exact JSON schema to target (no guessing field layouts).
2. Hand-write the two enlistment chains and two Survivor quests; playtest.
3. Then generate quests from the war ledger (same generator pattern as the patrols).
