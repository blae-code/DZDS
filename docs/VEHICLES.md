# Vehicles, Aircraft, Mounts and Trains

Spec module 3 (Overland Mobility, Flight & Logistics): rugged, lore-friendly transport on
**native maintenance** (plugs, batteries, radiators, fuel), high cargo and recovery utility,
no supercars, no virtual garages. Mods checked on the Workshop 2026-10-05; Expansion facts
from its source. **[test]** = confirm on the local server.

## 1. The backbone: DayZ-Expansion-Vehicles
One maintained framework (1.6M users, same team as our AI/Quests) instead of many small packs.
From its source it contains:

| Type | Vehicles |
|---|---|
| Ground | UAZ (transport/cargo), Tractor, Bus, Vodnik (amphibious), Land Rover, 2 motorbikes (250N, TT650), old bicycle, extra truck/sedan variants |
| Air | MH-6, UH-1H, Merlin, gyrocopter, **An-2 biplane**, C-130J **[test: flyable in the release build?]** |
| Water | Zodiac, utility boat (RHIB), boats |
| Systems | physical **keys** (master-key pairing, lockpicking, lock changing), **car-to-car towing**, covers, rotor damage, wind |

Requires **DayZ-Expansion-Licensed** (models). It does **not** require Expansion-Animations,
which matters because DayZ Horse is incompatible with that (guarded by a test).

### Consolidation (one system per job)
| Job | Using | Turned off |
|---|---|---|
| Keys & locks | Expansion keys (`VehicleRequireKeyToStart: 1`, lockpicking on) | MuchCarKey (stale; two key systems would conflict) |
| Car-to-car towing | Expansion towing | Rope Car Towing |
| Recovery of wrecks/stuck vehicles | **Towing Service** flatbed truck (kept: different job) | |
| Tarps/camouflage | **CarCover** (kept; Crocos Quadbike links to it) | Expansion covers |
| Helicopter flight | RedFalcon (MH-6, accessible) **and** Expansion flight model (Expansion + Arma 2 helis) | |

Two helicopter flight models feel different. That's acceptable if RedFalcon is the "common"
light heli and Expansion/Arma 2 helis are rarer and heavier. If it bothers you, keep one family.

Settings: `presets/overlays/expansion_vehicles.yaml` (`make overlays`). Also sets
`RevvingOverMaxRPMRuinsEngineInstantly: false` (tedium boundary) and `ShowVehicleOwners: false`.

## 2. The fleet by category

| Category | Mods | Role in the world |
|---|---|---|
| **Utility 4x4s** | IRP Land Rover Defender 110, [CnG] UAZ 31514, Expansion UAZ/Land Rover | Early-to-mid game workhorses; expedition gear slots |
| **Campers / home on wheels** | **[CnG] UAZ 452 "loaf" van**, **MBM Apocalypse Truck** (huge cargo, roof access) | The nomad phase (pillar 4): live out of a van, then a truck |
| **Old beaters** | CrSk VAZ-2107, GAZ-3309, BMW E34 | Common, cheap, 80s Chernarus |
| **Heavy logistics** | **LMs Semi Truck & Trailer**, Expansion Bus, GAZ-3309 | Late game hauling; Rust Syndicate convoys |
| **Trailers** | **Simply's Car Trailer** (towable storage behind any vehicle) | Spec's trailer pillar. The Workshop is thin here; this one is brand new, so **test first** |
| **Farm** | Expansion Tractor | Settler farmsteads |
| **Light / off-road** | Crocos Quadbike, Expansion motorbikes | Canyons, ridges, scouting |
| **Bikes** | DayZ-Bicycle (+ Expansion old bike) | Silent travel |
| **Mounts** | **DayZ Horse** + **Horse Expansion** | Saddle + bridle are physical items (craftable/repairable). Walk, trot, gallop, jump fences, swim. Fits the Karkas clan and arid Nasdara |
| **Helicopters** | RedFalcon MH-6; Expansion MH-6/UH-1H/Merlin/gyro; **Arma 2 Helicopters Remastered** (Mi-8 etc.) | Arma 2 *is* Chernarus; UN can field white Mi-8s. Attack helis (Mi-24, Ka-52) are never loot |
| **Planes** | **LMs Planes** (Cessna; standalone flight, stall warnings), Expansion An-2 | Airfields matter (UN-held). Spitfire excluded from spawns (wrong era/tone) |
| **Trains** | **HypeTrain** (player-driven, cargo wagons, walk between cars, put barrels/base items on wagons = mobile base) | Rust Syndicate rail yards become strategic. **Beta**, last update 2025-06; ships a Chernarus example mission |
| **Boats** | Expansion Zodiac/RHIB | Coast and lakes |
| **Co-op** | **Vehicle Shooting** (passengers can shoot) | Drive-and-gun with friends |

Optional, off: RUSForma vehicles/motorcycles (big Soviet packs, overlap), HypeTrain Expansion
(AI trains, tiny user base). Rejected: server repack "packs" (TridentGaming), static-only planes,
supercar/meme vehicles, RaG Immersive Vehicles (oil/wheel wear tedium).

## 3. Spawning: vehicles follow factions and roles
Vehicles spawn through the mission's **events.xml** (dynamic events), not types.xml. Plan,
keyed by map role so it ports to Nasdara:

| Role (holder) | What spawns there |
|---|---|
| airfield / military (UN) | UN Mi-8 (rare), Cessna/An-2 (rare), UAZ, Land Rover |
| industrial / water (Rust) | semi truck, GAZ-3309, trailers, HypeTrain wagons at rail yards |
| inland_town (Settlers) | tractor, beaters, bicycles, horses in fields |
| road_junction (Jackals) | wrecked beaters (parts), UAZ 452 |
| high_ground / remote (Karkas) | horses, quadbikes |

Helicopters and planes should be **rare and earned**: wrecks to repair (parts from military loot),
not ready-to-fly spawns. The war ledger can shift spawns when a site changes hands.
Co-op friends get a prepared keyed vehicle from the host (low-friction pillar).

## 4. Watch-outs
- **Mod count**: now ~70 enabled. Expect longer server start and client downloads; measure
  server FPS on the local server and cut what doesn't earn its place.
- **Planes are server-heavy** (LM's own warning). Keep 1–2 in the world.
- **Trains are beta**: test derailments and persistence before trusting a mobile base to one.
- **Horse ↔ Expansion-Animations** incompatibility: never add Expansion-Animations or the
  Expansion Bundle (which includes it). The test suite enforces this.
- **Nasdara**: rail lines and horse territories need checking on release; HypeTrain needs track
  data per map.

## 5. Next
1. Local server: confirm Expansion An-2/C-130J flyability, horse riding, trailer hitching, a
   HypeTrain run, and the Phase 4 checklist items for vehicles.
2. Write the vehicle `events.xml` plan as a generator keyed by role (like `make types`).
3. Tune rarity: helis/planes as repairable wrecks; trailers and campers uncommon.
