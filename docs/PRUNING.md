# Pruning Report

## Applied 2026-10-15 (Badlands relaunch, Nasdara)
**11 mods disabled** (each stays in `config/mods.yaml` with `enabled: false` and a `PRUNED 2026-10-15 (Badlands)` note).

| Mod | Workshop ID | Reason |
|---|---|---|
| SF Zombie Horde Event | 3689174025 | targets players anywhere, only supports exclusion zones; events must stay in zones |
| DayZ-Dynamic-AI-Addon | 2874589934 | Spatial AI already at MaxAI 0 |
| DayZ-Expansion-Missions | 2792984177 | every feature off |
| Armored Vehicle Pack | 2147610525 | abandoned since 2022, duplicated by remaining mods |
| IRP-Land-Rover-Defender-110 | 1912237302 | abandoned since 2021, duplicated |
| Crocos Quadbike | 2757080411 | abandoned, duplicated |
| Arma 2 Clothing Pack | 2298127647 | abandoned since 2020, duplicated |
| Unknown Ghillie Mod | 2074403068 | abandoned since 2021, duplicated |
| InventoryInCar | 2361330944 | abandoned since 2021, duplicated |
| HypeTrain | 3115714092 | Blae's decision; rail on Nasdara can't be verified offline |
| Leather Crafting | 3430034381 | first local 1.30 boot: `Can't compile "World"`, `CraftLeatherBelt` declared twice (1.30 ships its own) |

Overlays removed with their mods: `zombie_horde.yaml`, `spatial_ai.yaml`, `expansion_missions.yaml`.

**Keep if they boot clean** (`pending stage-3 boot`): CarCover, Code Lock, BuildAnywhere_v3,
Flying Birds, MMG Military Gear, MBM DuneBuggy, Horse Expansion, Ear-Plugs.

---

## Earlier report (prepared 2026-10-05; APPLIED 2026-10-07)

## Applied 2026-10-07 (to fit the Godlike plan: 12 GB RAM, 4 vCores, 70 GB)
**95 → 82 Workshop mods, 24.7 → 11.8 GB download, RAM estimate ~14 → ~10 GB.**
- **All of Tier 1** (9 mods, 8.7 GB). BBP vs RaG resolved in favour of RaG_BaseBuilding.
- **Tier 2, the four with a load cost** (4 mods, 4.2 GB): SNAFU Weapons (3.7 GB), LMs Planes
  (author warns it's server-heavy), Airborne AI and BS Patrol Tank (AI/CPU on 4 vCores).
- **Kept from Tier 2** (feel only, negligible load): MaharlikaPH MilitaryPack, Gas Mask Overhaul.
  Dark-Ish Nights was already off (vanilla dark nights chosen).
- Each pruned entry stays in `config/mods.yaml` with `enabled: false` and a `PRUNED` note.
- Measured vanilla base on the GSP is ~6 GB (the formula assumes 3), so the honest RAM
  range for 82 mods is ~7.5–10.5 GB before headroom. Confirm on first modded boot.


~95 mods are enabled. Every one costs client download size, server start time, server FPS
(scripts tick), and breakage risk on game updates (1.30 ships with Badlands on Oct 15). This
report ranks candidates; the final call is yours, ideally after the local-server test.

**Criteria**: (1) does another enabled mod already do the job? (2) when was it last updated
(`make verify-mods`; STALE = 18+ months)? (3) does it serve a design pillar (living world,
diegetic, low tedium, factions)? (4) does it carry risk (beta, heavy, conflicts)?

## Tier 1: cut first (redundant, and the survivor is maintained)
| Cut | Because | Keep instead |
|---|---|---|
| BaseBuildingPlus (stale 2025-03) **or** RaG_BaseBuilding | two modular building systems | RaG_BaseBuilding (maintained 2026-09), unless BBP's tiered walls/watchtowers win the playtest |
| MuchStuffPack (stale 2025-02, has 1.28 "fix" forks) + its dependency MuchFramework | overlaps MMG Base Storage | MMG Base Storage |
| RUSForma_vehicles + RUSForma_Motorcycles | large packs overlapping CnG UAZ, KamAZ, ArmA2 Trucks, Expansion motorbikes | the smaller targeted packs |
| Kamaz_Truck | ArmA2 Trucks already has KamAZ incl. tankers | ArmA2 Trucks |
| HypeTrain Expansion (tiny user base) | AI rail traffic is a nice-to-have on a beta train mod | HypeTrain alone |
| Dynamic AI Missions (stale 2024-12) | overlaps War Zones, hacked crates, heli crashes, GM actions | War Zones + GM |
| Basic Map (stale 2021) | the vanilla map with `displayPlayerPosition: false` already gives the diegetic paper map | vanilla map (+ Expansion-Navigation stays off) |

## Tier 2: decide on feel (power creep / tone)
| Mod | Question |
|---|---|
| SNAFU Weapons | A huge arsenal vs the "vanilla as intended" goal. Most blueprint weapons are vanilla. Keep only if you want variety; restrict spawns either way |
| MaharlikaPH MilitaryPack | The BMP-3 endgame wreck is great; the Abrams never spawns. Is one restorable IFV worth a whole mod? |
| Airborne AI | Paratrooper hunters are dramatic but heavy; escalation-only |
| BS Patrol Tank | Enemy armour; strong set piece, CPU cost |
| Gas Mask Overhaul | Filter tiers sit near the tedium line |
| Dark-Ish Nights (stale) | **Disabled 2026-10-07**: vanilla dark nights (lightingConfig = 1) chosen; re-enable only if those prove too dark in testing |
| LMs Planes | Planes are server-heavy (author's warning); one Cessna might not justify it next to the Expansion An-2 |

## Tier 3: stale but load-bearing (test first, replace if broken on 1.30)
InventoryInCar, IRP Land Rover Defender, Crocos Quadbike, CarCover, BuildAnywhere_v3,
Code Lock, Ear-Plugs, Flying Birds, Arma 2 Clothing Pack, Unknown Ghillie Mod, MMG Military
Gear, Armored Vehicle Pack, MBM Dune Buggy, Horse Expansion, Leather Crafting, Arma 2
Helicopters Remastered. If one breaks, look for a maintained fork (`make find-mod Q=...`)
before dropping the feature.

## Keep (core to the design)
CF, Dabs, Expansion Core/AI/Quests/Hardline/Market/Vehicles/Licensed, Zens Core, Survivor
Animations, AI War Zones, Moving AI Convoy, DayZ-Dynamic-AI-Addon, PvZmoD, Zens mods, KAN
camps, Dialogue Framework, VPPAdminTools, Ambient Animals, DayZ-Dog, DayZ Horse, HypeTrain,
Vehicle Shooting, Zens ExpansionAI Audio, RaG Core/Building/Cabin/Wells, MMG Base Storage,
@DZDS.

## Estimated effect
Tier 1 alone removes ~9 mods (to ~86) with no lost features. Tier 2 decisions could remove up
to 7 more. (Applied: see the top of this file.) Measure server FPS and start time on the local server before and after.

## How to apply
Set `enabled: false` in `config/mods.yaml` (keep the entry and note why), then
`make test && make modstring && make keys`. `tests/test_presets.py` guards that no enabled mod
conflicts with another.
