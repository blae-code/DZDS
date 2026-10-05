# Pruning Report (prepared 2026-10-05, nothing removed yet)

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
| Dark-Ish Nights (stale) | Only if vanilla bright/dark nights both feel wrong after testing |
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
to 7 more. Measure server FPS and start time on the local server before and after.

## How to apply
Set `enabled: false` in `config/mods.yaml` (keep the entry and note why), then
`make test && make modstring && make keys`. `tests/test_presets.py` guards that no enabled mod
conflicts with another.
