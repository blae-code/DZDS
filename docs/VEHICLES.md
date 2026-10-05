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

Also enabled (2026-10-05, "pack in everything"): RUSForma vehicles + motorcycles (large
Soviet-era packs; Lada/UAZ/ZIL/Ural/Dnepr-style), HypeTrain Expansion (AI rail traffic).
Rejected: server repack "packs" (TridentGaming), static-only planes, supercar/meme vehicles,
RaG Immersive Vehicles (oil/wheel wear tedium).

## 3. Military and utility vehicles

### What exists and what we took
| Mod | What it is | Weapons? | Verdict |
|---|---|---|---|
| **ArmA2 Trucks** (3593276829) | KamAZ, MTVR, T810 from Arma 2 (28 variants) | 2 armoured versions, unarmed | **Yes.** Its **tankers can be filled with water or fuel**, perfect for the Rust Syndicate's water/fuel economy and settler logistics |
| **Kamaz_Truck** (1895398348, 157k) | KamAZ cargo, covered, fuel | no | **Yes**: common heavy truck |
| **TP_Apoc_M1025** (3737385977, 2026-08) | Apocalypse Humvee: **working mounted gun** (own ammo item) plus no-gun and static-gun variants | **yes** | **Yes**: the "technical". Spawn the armed variant rarely; ammo scarce |
| **MaharlikaPH MilitaryPack** (3529074158) | **BMP-3 IFV** and **M1 Abrams**, with working gunner seats and gunner camera | **yes** | **Yes, with a rule**: the BMP-3 exists only as a single endgame wreck to restore; the Abrams never spawns (a US tank in post-Soviet Chernarus breaks tone). Known issue: VPPAdminTools glitches the gunner camera |
| **Armored Vehicle Pack** (2147610525, 145k) | Cougar MRAP, LAPV | no | **Yes**: UN armoured transports. Stale (2022), high 1.30 risk |
| **MBM Dune Buggy** (3166659854) | AWD buggy | no | **Yes**: Jackal raiders; perfect for Nasdara |
| **FairPlay Ambulance** (3057052159) | Ambulance with stretcher storage | no | **Yes**: UN medical stations |
| BS Patrol Tank (already on) | **AI-driven** BTR-82A that patrols and fights | yes (AI) | Enemy armour, not drivable. Natural Rust Syndicate asset |
| Arma 2 Helicopters (already on) | Mi-24 Hind, Ka-52, Mi-8, UH-1H... | **[test]** whether ports keep weapons | Attack helis never spawn as loot regardless |
| Automated Turrets (2851374375, 119k) | Base-mounted M60/M134/M2 auto-turrets | yes | Belongs to **base building** (next topic) |
| FULLmoon Technical | armed pickups | | **Can't use**: author forbids use outside their server |
| Drones (2988099206) | recon/cargo/explosive drones via tablet | | **Reject**: abandoned by author; tablet UI is non-diegetic |
| Savage Snowmobiles | snowmobiles | | Skip: no snow on Chernarus or Nasdara (Sakhal only) |
| Savage BTR Half-track, Humvee M1151 | | | Skip: stale (2020/2023), overlap |

### Rules for armed vehicles (PvE balance)
Working guns are fun in co-op against AI factions, but they can flatten the game. So:
1. **Earned, not found**: armed variants appear as wrecks needing major parts (from military
   sites) rather than drivable spawns.
2. **Ammo is the throttle**: mounted-gun ammo is rare loot (`presets/types_dzds.yaml`, once the
   classnames are confirmed with `make mod-types`).
3. **Factions fight back**: UN and Rust patrols near armour use launchers if their loadouts allow
   **[test]** Expansion AI with LAW/RPG; the BS Patrol Tank is the enemy counterpart.
4. **One of each** at most in the world at a time (events.xml `nominal`).

### Other categories considered
Ambulances (taken), fuel/water tankers (taken), buggies (taken), snowmobiles (no snow),
drones (rejected), wheelbarrows/forklifts (base-building assets, not vehicles; next topic),
jets (off-tone; not considered). Boats are covered by Expansion.

## 4. Spawning: vehicles follow factions and roles
Vehicles spawn through the mission's **events.xml** (dynamic events), not types.xml. Plan,
keyed by map role so it ports to Nasdara:

| Role (holder) | What spawns there |
|---|---|
| airfield / military (UN) | UN Mi-8 (rare), Cessna/An-2 (rare), UAZ, Land Rover, MRAP/LAPV, ambulance, BMP-3 wreck (one, endgame) |
| industrial / water (Rust) | semi truck, KamAZ/MTVR/T810, water/fuel tankers, trailers, HypeTrain wagons at rail yards |
| inland_town (Settlers) | tractor, beaters, bicycles, horses in fields |
| road_junction (Jackals) | wrecked beaters (parts), UAZ 452, dune buggies, armed M1025 (rare wreck) |
| high_ground / remote (Karkas) | horses, quadbikes |

Helicopters and planes should be **rare and earned**: wrecks to repair (parts from military loot),
not ready-to-fly spawns. The war ledger can shift spawns when a site changes hands.
Co-op friends get a prepared keyed vehicle from the host (low-friction pillar).

## 5. Watch-outs
- **Mod count**: now ~80 enabled. Expect longer server start and client downloads; measure
  server FPS on the local server and cut what doesn't earn its place.
- **Planes are server-heavy** (LM's own warning). Keep 1–2 in the world.
- **Trains are beta**: test derailments and persistence before trusting a mobile base to one.
- **Horse ↔ Expansion-Animations** incompatibility: never add Expansion-Animations or the
  Expansion Bundle (which includes it). The test suite enforces this.
- **Nasdara**: rail lines and horse territories need checking on release; HypeTrain needs track
  data per map.

## 6. Next
1. Local server: confirm Expansion An-2/C-130J flyability, horse riding, trailer hitching, a
   HypeTrain run, and the Phase 4 checklist items for vehicles.
2. Write the vehicle `events.xml` plan as a generator keyed by role (like `make types`).
3. Tune rarity: helis/planes as repairable wrecks; trailers and campers uncommon.
