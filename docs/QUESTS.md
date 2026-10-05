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

## Where players stand: resolved through quests
This replaces open decision 1 in LIVING_WORLD.md:
- **Everyone starts unaligned.**
- **Enlistment chains**: a CDF quartermaster at a CDF-held base and a ChDKZ contact in the
  industrial north each offer a short chain (prove yourself → deliver supplies → small op).
  The last quest's `FactionReward` makes you a member. **Joining a side is a choice made in
  the world, not a menu**, and it has consequences: the other army now shoots on sight.
- Faction-only quests (`RequiredFaction`) unlock after enlisting, gated by reputation.
- Survivors offer neutral quests to anyone, so you can stay out of the war.
- **[test]** How each army treats unaligned players (Expansion targeting); how switching
  sides behaves (a "defector" quest with a `FactionReward` to the other army).

## Quest catalogue (mapped to the war)
| Quest | Type(s) | Giver | Effect on the war ledger |
|---|---|---|---|
| Fuel run | DELIVERY (jerrycans) | quartermaster of either army | +fuel for that faction |
| Medical supplies | COLLECT → DELIVERY | Survivor doctor in a coastal town | +medicine for Survivors / reputation |
| Clear the bandit camp | AICAMP (Raiders) | Survivor elder | Raiders lose a site |
| Convoy escort | AIESCORT | army logistics officer | convoy arrives → +supplies |
| Recon | TRAVEL to a contested site | army scout | reveals enemy strength (GM radio report) |
| Break the siege | AIPATROL at a contested site | army officer | site flips at next restart |
| Lost cache | TREASUREHUNT | rumour from a Survivor | loot, no war effect |
| Field repairs | CRAFTING / ACTION | mechanic NPC | vehicle parts reward (fits Vehicles module) |

## Making quests follow the war (war-ledger integration)
Quests are JSON in `$profile:`, like the patrols, so the war ledger can **regenerate them each
restart**:
1. **Quest givers move with the front.** A quartermaster spawns at sites their faction
   currently holds. If the site falls, he's gone (or a ChDKZ officer is there instead).
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
