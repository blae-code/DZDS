# Base Building, Crafting and Gear

Spec module 4 (homesteading) and pillar 4 (nomadism to homesteading), within the tedium
boundary. Mods checked on the Workshop 2026-10-05. **[test]** = confirm on the local server.
**PRUNE** marks overlaps to resolve in the pruning pass.

## 1. The progression arc
| Stage | What you have | Enabled by |
|---|---|---|
| **Camp** | tent, fire, a stash | vanilla |
| **Home on wheels** | loaf van, apocalypse truck, trailer, even a train wagon with barrels on it | docs/VEHICLES.md |
| **First shelter** | a few walls and a door on a cliff edge | RaG_BaseBuilding + Immersive Placing |
| **The cabin** | a lockable hunting cabin with fireplace and lights: the homestead milestone | **RaG_Hunting_Cabin** |
| **Compound** | multi-tier walls, gates with keypads, watchtowers, lockers, gun racks, a car workbench | RaG, vanilla DigitalCodeLock (1.30), MMG Base Storage, Zens Car Workbench |
| **Settlement network** | recruited Settlers garrisoning your towers; KAN NPC camps nearby | docs/FACTIONS.md |

## 2. Systems (one per job, with overlaps flagged)
| Job | Using | Notes |
|---|---|---|
| Modular building | **RaG_BaseBuilding** (maintained, 21 kits, snap points) | BaseBuildingPlus pruned 2026-10-07 |
| Build on rough terrain | Immersive Placing Update | BuildAnywhere_v3 disabled 2026-10-21: 1.30.164200 can't decode its scripts |
| Locks | **vanilla `DigitalCodeLock`** (1.30, fence gates; Code Lock mod pruned 2026-10-15) | Expansion BaseBuilding stays off: it would add a second code-lock system |
| Storage & furniture | **MMG Base Storage** (maintained) | MuchStuffPack pruned 2026-10-07 |
| Vehicle work | **Zens Car Workbench** (60 nails + 5 sheet metal; holds tyres, batteries, plugs, tools) | |

**PvE base safety**: AI don't demolish walls; zombies bash *unlocked* doors (PvZmoD). Your
threats at home are AI patrols and raids on you, not your walls. Vanilla base damage stays on
(friends-only server); `disableBaseDamage = 1` is available if you'd rather never lose a wall.
Upkeep: the vanilla flag refresh (40 days) suits a casual group (docs/ECONOMY.md section 7).

## 3. Crafting: decisions, not chores
- **Leather Crafting**: hunting → tanned hides → leather clothes, bags, water pouch; pairs
  with horse tack (Horse Expansion) and the Karkas aesthetic.
- **CookZ**: optional pot/pan recipes; normal cooking still works, so it's a bonus, not a gate.
- **Zens Crafting Sounds**: audio for crafting actions; pure immersion.
- **Native repair loops** stay (sewing kits, epoxy, weapon cleaning, car parts).
- **No ammo crafting** (Simple Ammo Crafting rejected): ammunition is the barter currency
  (docs/ECONOMY.md section 4); printing money would break it.

## 4. Gear: vanilla first, factions recognisable
Most of the Faction Blueprint's weapons are **vanilla DayZ** (M16A2, FAL, SG5-K, Mosin,
CR-527, Blaze, Repeater, BK-133, SKS, IJ-70, Saiga, Vaiga, Bizon, AK-74, Winchester 70,
Glock). Faction looks come from vanilla clothing plus a few packs:

| Mod | Adds | Used for |
|---|---|---|
| **MMG Mightys Military Gear** (1.4M users, stale 2023-10) | plate carriers, pouches, helmets | UN plate carriers, Rust armoured vests |
| **Arma 2 Clothing Pack** (stale 2020) | Chernarus-era clothing, 3-piece ghillies | Karkas, Settlers |
| **Unknown Ghillie Mod** (stale 2021) | ghillies on the belt slot, craftable camo-net ponchos | Karkas, player snipers |
| **Gas Mask Overhaul** | 18 masks, filter tiers, charcoal refills | Jackal look; contaminated zones (Expansion-Missions). Watch the tedium line |
| **Mounts & Sights** | vanilla-compatible mounts and optics | everyone |
| **Asmond Vanilla Weapons** | vanilla-style extra weapons | variety without changing the feel |
| **SNAFU Weapons** (1.6M users) | a very large weapon pack | **PRUNE candidate**: power creep against the vanilla feel. If kept, only lore-fitting guns get spawn entries |

[verify] UN-specific items (blue helmet/beret) and welding masks: confirm vanilla or modded
classnames with `make mod-types` before writing loadouts.

## 5. How new items enter the economy
Each mod ships its own types file, and **as of 2026-10-24 none is registered**: the Nasdara CE
loads only vanilla `db/types.xml` and our `dzds/` folder, whose modded entries are arrival
vehicles at nominal 0. So no modded item spawns as loot. Registering them under a per-mod policy
is milestone 1 of the living-world plan (`make mod-ce`). `make economy` regenerates every
registered types file from its `.vanilla` baseline, changing only arrival-vehicle lifetimes (no
scaling since the 2026-10-15 relaunch), and adopts a newer vanilla file a game update leaves
behind as the new baseline.

## 6. Considered and off
| Mod | Why off |
|---|---|
| DayZ-Expansion-BaseBuilding | third building system + second code-lock system |
| RA Base Building | another building system; stale |
| **Automated Turrets** | auto-aiming sentry guns break the low-tech tone and trivialise AI raids. Easy to flip on if you want them |
| zm workbench | beta |
| Simple Ammo Crafting | would break the ammo currency |
| Paragon Storage | author ended support |
| Kerberos Gear | anime sci-fi; wrong tone |
| Storage Containers | redundant with MMG Base Storage |

## 7. Pruning candidates (for the pass you planned)
BBP vs RaG_BaseBuilding · MuchStuffPack vs MMG Base Storage · SNAFU Weapons · stale mods
(BuildAnywhere_v3, Basic Map, InventoryInCar, IRP Defender, Arma 2 Clothing, Unknown Ghillie,
Armored Vehicle Pack, Flying Birds) · duplicate vehicle packs (RUSForma vs CnG/Kamaz/ArmA2 Trucks).
