# Mod Audit: 2026-10-05

Every Workshop ID in `docs/SPEC.md` was checked against the Steam Workshop API
(`make verify-mods`). Only **4 of 30 were correct**; most were off by a few digits or
named mods that don't exist. `config/mods.yaml` now holds the corrected list.

## Corrected IDs (same mod, wrong ID in spec)
| Mod | Spec ID | Correct ID |
|---|---|---|
| DayZ-Expansion-Core | 2115602332 (SchanaModGlobalChat) | 2291785308 |
| DayZ-Expansion-AI | 2792982064 | 2792982069 |
| AnimatedDynamicHelicopters | 2840742469 | 3382463948 |
| Bastardos Hacked Crate ("BS HackedCrate") | 2713769268 | 3482229348 |
| Dynamic AI Missions | 2824688047 | 3277130230 (server-side) |
| Flying Birds! | 2855146034 | 2501812949 |
| InventoryInCar | 2288301548 | 2361330944 |
| MuchCarKey | 2049619524 | 2049002856 |
| CarCover | 2303494793 (a different game) | 2303483532 |
| IRP-Land-Rover-Defender-110 | 2443003051 | 1912237302 |
| Crocos Quadbike | 2830849472 | 2757080411 |
| BaseBuildingPlus | 1710977258 | 1710977250 |
| BuildAnywhere_v3 | 1579262963 | 1854626456 |
| Code Lock | 1646187814 | 1646187754 |
| MuchStuffPack | 1991566648 | 1991570984 |
| Basic Map | 2270217596 | 2270215132 |
| VPPAdminTools | 1828463903 | 1828439124 |
| BetterHarvest | 2434005084 | 3495536882 |

## Substitutions (spec mod not found, or a maintained replacement exists)
| Spec | Replacement | Trade-off |
|---|---|---|
| Spatial AI | DayZ-Dynamic-AI-Addon (2874589934) | **Same mod, renamed** (its description: "mod version = Spatial AI"). Server-side only |
| PvZ MOAR Door Bashing | Zens Zombie Door Bangers (2932842394) | Zombies only; AI door breaching not covered |
| BleedTrail (2019) | Zens Blood Trail (3412155287) | Maintained, persists across restarts |
| ZenSleep V1 | Zens Sleeping Mod (3468961047) | Author's rewrite for 1.28+ |
| TowingMod | Towing Service (3004707934) | Flatbed recovery truck, **not tow ropes**. Rope alternative: "Unpleme \| Rope Car Towing" (3745963420, small user base) |
| CrSk_Beaters | [CrSk] VAZ-2107, GAZ-3309 (BMW E34 optional) | Individual 80s vehicles |
| Hunterz DayZ Bicycles | DayZ-Bicycle (2971190303) | Needs Survivor Animations |

Added dependencies: **Zens Core Mod** (3702420204) for the Zen mods, **Survivor
Animations** (2918418331) for DayZ-Bicycle.

## Open decisions
- **Stale mods** (no update in 18+ months): InventoryInCar, IRP Defender, BuildAnywhere_v3,
  Basic Map, Crocos Quadbike, Flying Birds. Highest risk of breaking on 1.30. Test first.
- **Basic Map vs Expansion-Navigation**: Basic Map is stale; Expansion-Navigation is maintained
  and already in the Expansion ecosystem. Make sure HUD markers are disabled either way (design pillar).
- **Code Lock vs Expansion's own code locks / base building**: Expansion ships alternatives;
  a "CodeLock to ExpansionCodeLock Bridge" mod exists, which suggests overlap is common.
- **MuchStuffPack**: community `_Fix` uploads exist for 1.28; check whether the base mod works.
- **Dynamic AI Missions**: last updated 2024-12; candidate for replacement if it breaks.

## Living-world additions (2026-10-05, see docs/LIVING_WORLD.md)
- Added: **AI War Zones** (3521304609, front-line battles), **Moving AI Convoy** (3767913539, faction logistics).
- Disabled: Dynamic AI Missions (stale, overlaps War Zones/crates/crashes).
- Listed as optional (disabled): Airborne AI, BS Patrol Tank, Expansion-Missions, Expansion-Quests, SF Zombie Horde.
- Rejected: AI Voice Broadcast (author: broken since 1.29), King of the Hill (now private),
  AI Bandits (separate AI framework, wouldn't join the faction war).
