# Economy: Vanilla Loot + Faction Barter, Paced Over Months

Goal (user, 2026-10-05): the default DayZ experience (scavenging the world), built to stay
interesting for a small group over months, **plus traders and a barter economy** (updated
the same day: traders welcome).

## 1. What stays vanilla
- **The Central Economy (CE)** decides all loot: each item type has a `nominal` (target count
  in the world), `min` (restock threshold), `lifetime` and `restock`, spawned at map
  locations by `usage` (Military, Industrial, Farm...) and `value` tiers (Tier1 coast → Tier4
  far north / military).
- **Scavenging stays the main source of loot.** Traders (section 4) are a place to swap
  what you found, not a shop that replaces exploring. No ATMs or banking. Hardline item
  rarity is off.
- **Vanilla sinks** do the rest: wear and ruin, food decay, ammo use, base upkeep (flag
  refresh), vehicle parts breaking.
- `globals.xml` stays at vanilla values; the tool can change any existing var if testing shows
  a need (candidates listed in `presets/economy.yaml`).

## 2. Why vanilla alone doesn't last months with 1–4 players
1. **Population**: vanilla nominals assume ~60 players emptying the map. With 4, loot piles up
   and everyone is fully geared within a week.
2. **Stockpiling**: by default items in tents and stashes don't count toward nominal, so the
   world keeps respawning gear while your base fills. Over months that removes all scarcity.
3. **Time away**: when nobody is online the CE idles; the world doesn't move on by itself.

## 3. What we add (`presets/economy.yaml`, `make economy`)
`tools/economy.py` saves the mission's pristine `db/types.xml` as `db/types.xml.vanilla` the
first time, then always **regenerates** `types.xml` from it. Scaling never compounds and is
fully reversible.

### a) Population scaling
Valuable tiers are scaled by expected player count. Change `expected_players` as the group
grows and rerun:

| Players | Tier1 | Tier2 | Tier3 | Tier4 |
|---|---|---|---|---|
| 1–4 | 100% | 85% | 70% | 60% |
| 5–10 | 100% | 90% | 80% | 75% |
| 11–30 | 100% | 95% | 90% | 90% |
| 31+ | vanilla | | | |

**Food is protected** (never scaled down). Items that spawn via events (nominal 0, like vehicle
parts on wrecks) are untouched, and nothing that spawned before is reduced to zero.

### b) Campaign phases (pacing in real weeks)
| Phase | From week | Story | Military loot |
|---|---|---|---|
| **Landfall** | 0 | Fresh arrivals; UN still holds the bases | Tier3 60%, Tier4 40%, weapons 70% |
| **Scavenger** | 3 | Settlements form; tribal feud heats up | Tier3 80%, Tier4 60% |
| **Escalation** | 7 | Open faction war; convoys and contested sites | Tier3 95%, Tier4 85% |
| **Long War** | 13 | The long haul; endgame wrecks | population-scaled baseline |

These stack with population scaling. The phase is chosen from `campaign_start` and today's
date (`--phase` overrides). The same phase names can drive the war ledger and AI density
later, so the whole world escalates together.

### c) Hoarding counts
For Tier4, Unique and the weapons category, `count_in_hoarder=1`: a gun in your stash counts
toward the world's total, so a stockpile makes the world thinner instead of being free. Food,
tools and building materials stay vanilla, so homesteading isn't punished.

## 4. Traders and barter (Expansion-Market)
Design: `presets/traders.yaml`. Facts from Expansion-Market's source:
- **Barter, not money**: each trader has its own `Currencies` list, and any item can be
  currency. We use **ammunition as hard currency** (.22 up to 7.62), **boxes of nails** at the
  settler market, and **UN aid scrip** (an Expansion banknote standing in until @DZDS adds a
  voucher item) earned from UN quests.
- **Supply and demand**: prices float between min/max with stock. Dump 50 AKs on the
  smuggler and AKs get cheap there. Over months, trader stock reflects what the group actually
  found and sold, so the economy scales itself.
- **Gating**: `RequiredFaction` and `RequiredCompletedQuestID`. Trade is earned:
  the UN quartermaster opens after the UN intro quest; the Rust water broker after a
  "water rights" deal.

| Trader | Faction / place | Takes | Sells |
|---|---|---|---|
| Frontier Exchange | Settlers, a settler town | nails, ammo, scrip | food, tools, building materials, clothing, tack |
| UN Quartermaster | UN, airfield Green Zone | scrip, ammo | medical, radios + batteries, maps/compasses, rations, NBC |
| Rust Water Broker | Rust, a dam/well "truce gate" | ammo | fuel, water, vehicle parts, trailers, tankers |
| The Smuggler | nobody's, remote | ammo | weapons, optics, rare parts, lockpicks; pays only 25% |

Jackals and Karkas don't trade (raiders / isolationists); a Karkas trapper may open through a
quest chain.

**Guardrails so traders don't replace scavenging**: player-driven stock (traders mostly resell
what players sold them), modest max stock, low sell-back percentages, top-tier gear only
via the smuggler at high prices. Traders talk first via **Dialogue Framework** and are voiced
by **Zens ExpansionAI Audio**.

**Green Zone protection**: Expansion has safe zones (no-damage areas). Recommended *not* to
use them: armed UN guards protecting the compound is the diegetic version. Revisit if AI
raids keep killing traders.

## 5. The economy is the war
The factions do the rest without touching loot tables:
- **Access, not spawns**: military loot at UN-held airfields is behind armed neutrality;
  Rust Syndicate wells and refineries are behind exclusion perimeters. Taking or negotiating
  for a site **is** the economy.
- **Quests feed trade**: quests pay in scrip and goods and unlock traders (fuel runs, medical
  deliveries, water rights).
- **Traders follow the front** (war ledger, later): a trader is gone while its site is lost;
  fuel and water prices rise when the Rust Syndicate loses wells; UN stock thins when aid
  convoys are ambushed.
- **AI as a sink**: Jackals strip bodies (`LootingBehaviour: ALL`), and firefights burn ammo.
- **Big-ticket items are earned**: helicopters, planes and armed vehicles are wrecks to
  restore (docs/VEHICLES.md), not loot.
- **Offline time**: the CE idles when empty, but the war ledger keeps the front moving between
  sessions, so the world has changed when you come back.

## 6. Running it
```bash
make economy              # phase from today's date
make economy PHASE=landfall
.venv/bin/python tools/economy.py --dry-run --date 2027-01-15   # preview a future phase
make validate && make push
```
Run it when the phase changes (weekly is plenty) or when `expected_players` changes. Restart
the server afterwards; the CE reads types.xml at startup.

## 7. Months-long persistence
- **No routine wipes.** Back up `storage_*/` (the world's persistence) before game updates.
  `sync.sh` excludes it from config sync on purpose, so add a separate backup step on the GSP
  (most panels have scheduled backups).
- **Base upkeep**: vanilla flag refresh (base persists 40 days without refresh) suits a
  casual group; revisit if friends drop out for long stretches.
- **Game updates** (e.g. 1.30 with Badlands) can force a wipe on official content changes;
  treat Nasdara as **season two** (an exodus story beat) rather than a forced reset.

## 8. To verify on the local server
- [test] CE loads the regenerated types.xml (formatting/comments are stripped; that's fine for the CE).
- [test] Stackable ammo and nails work as Expansion currencies (quantity-based value).
- [test] Trader stock persistence across restarts; tune min/max stock and prices.
- [test] Loot feel per phase: walk a military base in Landfall vs Long War.
