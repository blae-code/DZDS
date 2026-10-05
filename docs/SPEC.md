# Master Operational Specification: DayZ PvE Persistent Living Sandbox

> **Note (2026-10-05):** Most Workshop IDs in §4 below are incorrect. The verified list lives in
> `config/mods.yaml`; see `docs/MOD_AUDIT.md`. Badlands releases 15 Oct 2026 with game update 1.30.

This document is the definitive architectural specification and operating blueprint for Claude Code. It details the project intent, remote server infrastructure, local machine environment, modular mod taxonomy, telemetry pipelines, and configuration heuristics required to build, automate, and maintain this private DayZ ecosystem.

---

## 1. Project Vision & Core Intent

The objective is to establish an **autonomous, persistent, highly immersive PvE survival sandbox** optimized for a dedicated solo host, with seamless drop-in co-op support for 1–3 casual companions. Initial deployment and mechanical validation take place on **ChernarusPlus**, with clean architectural portability to **Nasdara (*Badlands*)** upon release.

### Gameplay Pillars
1. **The Living World:** The map is never empty or static. Emergent conflict between competing human AI factions and the infected creates ambient gunfights, territorial clashes, and dynamic objectives that occur independently of player interaction.
2. **Asymmetric Player Dynamic:**
   * **Solo Depth:** Granular survival, mechanical salvage, vehicle rebuilding, wilderness navigation, compound construction, and tactical scouting.
   * **Low-Friction Co-op:** When casual companions connect, the host must be able to deploy them into prepared compounds, fueled vehicles, and active world missions without hours of preliminary scavenging.
3. **Tactile & Diegetic Immersion:** Mechanics prioritize tangible, in-world physical items over abstract UI elements.
   * *Allowed:* Physical keys, digital keypads, canvas vehicle tarps, physical tow cables, handheld tourist maps, compasses, and radio broadcasts.
   * *Prohibited:* Virtual garage terminals, floating 3D HUD markers, magical map fast-travel, and immersion-breaking modern supercars.
   * *Tedium Boundary:* Avoid over-engineered micro-management (e.g., fluid dipsticks, blown fuse mechanics, manual lug-nut torquing). Stick to native DayZ mechanical loops (spark plugs, batteries, radiators, fuel, and blowtorches).
4. **Nomadism to Homesteading:** Progression moves organically from mobile overland survival (campers, utility 4x4s, trailers, scout helicopters) to fortified base compounds.

---

## 2. Infrastructure Architecture & Separation of Concerns

The environment is split into a **Remote 24/7 Dedicated Server** and a **Local Client + AI Orchestrator**:

```
┌────────────────────────────────────────────────────────────────────────┐
│             Third-Party Game Server Provider (GTXGaming / Host Havoc)  │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │ DayZ Dedicated Server Process                                  │   │
│   │  * High-clock AMD Ryzen 7000/9000 or Intel 13th/14th Gen       │   │
│   │  * 8 GB – 12 GB Dedicated RAM                                  │   │
│   │  * Persistent World (runs 24/7 for casual companions)         │   │
│   │  * Public Game UDP: 2302 | Steam Query UDP: 2303               │   │
│   │  * BattlEye RCON UDP: 2310 (Protected by strong password)      │   │
│   │  * Secure SFTP / FTP access to /profiles/ and /mpmissions/     │   │
│   └──────────────▲─────────────────────────────────▲───────────────┘   │
└──────────────────┼─────────────────────────────────┼───────────────────┘
                   │                                 │
                   │ Connect: GSP_IP:2302            │ Remote BattlEye RCON (UDP:2310)
                   │                                 │ & SFTP Log Polling (.ADM)
┌──────────────────┼─────────────────────────────────┼───────────────────┐
│ Local Host Rig   │                                 │                   │
│ (CachyOS Linux)  │                                 │                   │
│                  ▼                                 │                   │
│   ┌─────────────────────────────┐                  │                   │
│   │ DayZ Game Client            │                  ▼                   │
│   │  * Proton BattlEye Runtime  │    ┌─────────────────────────────┐   │
│   │  * 1440p / 4K Extreme       │    │ GM Python Orchestrator      │   │
│   │  * Full GPU/VRAM allocation │    │  * Tails remote .ADM logs   │   │
│   └─────────────────────────────┘    │  * Dispatches RCON commands │   │
│                                      └──────────────▲──────────────┘   │
│                                                     │ Localhost HTTP   │
│                                                     │ (Port 11434)     │
│   ┌─────────────────────────────┐                   ▼                   │
│   │ External Friends (1–3)      │    ┌─────────────────────────────┐   │
│   │  * Connect: GSP_IP:2302     │    │ Ollama ROCm Engine          │   │
│   └─────────────────────────────┘    │  * Gemma 4 E4B              │   │
│                                      │  * RDNA3 (RX 7900 XTX)      │   │
│                                      └─────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Local Machine Specification & Environment

* **Operating System:** CachyOS Linux (Rolling Release, Kernel with BORE / EEVDF schedulers).
* **CPU:** AMD Ryzen 7 7800X3D (8 Cores / 16 Threads, 96 MB 3D V-Cache).
* **GPU:** AMD Radeon RX 7900 XTX (24 GB GDDR6 VRAM, Navi 31 architecture).
* **System RAM:** 32 GB DDR5 6000MHz.
* **LLM Engine:** Ollama running **Gemma 4 E4B**.
  * Configured via ROCm: `export HSA_OVERRIDE_GFX_VERSION=11.0.0`
  * Memory footprint: $\approx 2.8\text{ GB} - 3.5\text{ GB}$ VRAM.
  * Headroom: $\approx 12\text{ GB}+$ VRAM unburdened for the DayZ client running under Proton.

---

## 4. Modular Mod Taxonomy & Exemplars

Mods are modular and categorized by functional intent. Exemplars represent the target loadout, but Claude Code may substitute or prune items provided dependencies and design pillars remain intact.

```
                         Modular Functional Taxonomy
 ┌──────────────────────────────────┬──────────────────────────────────┐
 │ 1. Engine Core & Frameworks      │ Mandatory API & script hooks     │
 │ 2. Dynamic World & Living AI     │ Living ecosystem & factions      │
 │ 3. Overland Mobility & Flight    │ Ground/air mobility & recovery   │
 │ 4. Homesteading & Fortifications │ Building, storage, and shelter   │
 │ 5. Telemetry, Admin & GM Hooks   │ Observability & command pipes    │
 └──────────────────────────────────┴──────────────────────────────────┘
```

### Module 1: Core Frameworks (Infrastructure)
* **Requirement:** Base libraries required for script interception, network RPC propagation, and UI management.
* **Exemplars:**
  * `@CF` (Community Framework - Workshop ID: `1559212036`)
  * `@Dabs Framework` (Workshop ID: `2545327648`)
  * `@DayZ-Expansion-Core` (Workshop ID: `2115602332`)

### Module 2: Dynamic World, Factions & Living AI
* **Requirement:** Eliminates the empty-world feeling via autonomous human AI, spatial spawns, multi-way factional wars, dynamic events, and physical tracking cues.
* **Exemplars:**
  * `@DayZ-Expansion-AI` (`2792982064`): Human combatants, patrol routes, guards, recruitable followers.
  * `@Spatial AI` (`2960682287`): Dynamic, context-aware AI spawns relative to player position.
  * `@Dynamic AI Missions` (`2824688047`): Random timed world objectives (convoys, camps, supply drops).
  * `@Animated Dynamic Helicopters` (`2840742469`): Dynamic flying AI helis that crash in real time.
  * `@Bastardos Hacked Crate` (`2713769268`): Encrypted drop crates with alarm wave-defense timers.
  * `@Airdrop-Upgraded` (`1870524790`): Server-wide cargo planes dropping contested loot crates.
  * `@PvZ MOAR Door Bashing` (`2542456482`): Zombies and AI physically breach wooden doors.
  * `@Flying Birds!` (`2855146034`): Flocks react to gunfire and loud engines as diegetic sound cues.
  * `@BleedTrail` (`2521992015`): Blood trails from injured entities enable tracking.

### Module 3: Overland Mobility, Flight & Logistics
* **Requirement:** Rugged, lore-friendly vehicles and helicopters utilizing native DayZ maintenance rules (plugs, batteries, fuel), avoiding micro-tedium while providing high cargo and recovery utility.
* **Exemplars:**
  * `@InventoryInCar` (`2288301548`): Access backpacks and drink/eat while seated.
  * `@EarPlugs` (`1819514788`): One-key engine/rotor noise reduction.
  * `@MuchCarKeys` (`2049619524`): Physical brass keys and lockpicking mechanics.
  * `@TowingMod` (`2414264762`): Physical tow lines to haul trailers or recover stuck vehicles.
  * `@CarCover` (`2303494793`): Physical camo nets/tarps to conceal vehicles and freeze physics.
  * `@IRP-Land-Rover-Defender-110` (`2443003051`): Weathered expedition 4x4 with exterior gear slots.
  * `@CrSk_Beaters` (`2782352822`): Authentic 1980s rusted utility trucks and sedans.
  * `@Crocos Quadbikes` (`2830849472`): Light, agile ATVs for rocky canyon navigation.
  * `@Hunterz DayZ Bicycles` (`2873099951`): Silent, human-powered pedal transport.
  * `@RedFalcon Flight System Heliz` (`2692979668`): Accessible, high-polish aviation (MH-6 Little Bird).

### Module 4: Base Engineering, Storage & Survival
* **Requirement:** Freeform construction on uneven terrain, streamlined access security, and functional rest loops.
* **Exemplars:**
  * `@BaseBuildingPlus` (`1710977258`): Multi-tier walls, roofs, stairs, and watchtowers.
  * `@BuildAnywhere_v3` (`1579262963`): Removes terrain clipping limits for canyon/cliff builds.
  * `@CodeLock` (`1646187814`): Digital keypad entry for gates and heavy storage.
  * `@MuchStuffPack` (`1991566648`): Lore-friendly craftable base furniture, gun racks, and lockers.
  * `@ZenSleep` (`2840048119`): Fatigue and exhaustion loop; rest clears debuffs.
  * `@BetterHarvest` (`2434005084`): Balanced horticulture yield and seed harvest configurations.

### Module 5: Telemetry, Administration & Local LLM Hooks
* **Requirement:** Out-of-band administration, map navigation, and hooks for external Game Master orchestration.
* **Exemplars:**
  * `@BasicMap` (`2270217596`) or `@DayZ-Expansion-Navigation`: Configured without 3D HUD markers; requires holding a physical map.
  * `@VPPAdminTools` (`1828463903`): Coordinate inspection, waypoint tuning, and freecam.
  * Native BattlEye RCON (Port `2310` UDP): Out-of-band command execution.
  * Enforce `RestApi`: In-engine HTTP webhooks and command queue polling.

---

## 5. Local LLM Game Master Integration Architecture

The **Game Master** is an asynchronous Python daemon running locally on the CachyOS host. It translates remote server telemetry into context-aware in-game events using **Gemma 4 E4B**.

$$\text{Telemetry (.ADM / RestApi)} \longrightarrow \text{Event Aggregator} \longrightarrow \text{Gemma 4 E4B (Ollama)} \longrightarrow \text{Action Dispatcher (RCON)}$$

### GM Operational Workflow
1. **Telemetry Ingestion:**
   * The Python daemon monitors `DayZServer_*.ADM` over SFTP or receives Enforce `RestApi` webhooks.
   * Tracks player health drops ($>40\%$), AI combat encounters, vehicle crashes, and spatial transitions.
2. **Cognition Loop (Gemma 4 E4B):**
   * Triggered on significant events or a periodic 10–15 minute heartbeat.
   * Model operates in strict JSON mode via Ollama (`http://127.0.0.1:11434`).
   * Strips internal deliberation channels (`<|channel>thought`) to ensure clean payloads.
3. **Structured Payload Schema:**
```json
{
  "narrative_broadcast": "Static crackles over the radio: '...unidentified cargo bird down near the western ridge...'",
  "world_actions": [
    {
      "type": "trigger_event",
      "target": "spawn_airdrop",
      "coords": [4512.0, 10240.0],
      "delay_seconds": 30
    }
  ]
}
```
4. **World Injection:**
   * Text broadcasts dispatched via remote BattlEye RCON: `say -1 <message>`.
   * World spawns dispatched via Enforce `RestApi` queue or administrative triggers.

---

## 6. Operational Guidelines for Claude Code

When generating scripts, modifying configs, or interacting with the server over SFTP:

### A. AI Calibration Rules
DayZ Expansion AI defaults are excessively lethal. Always calibrate AI settings to encourage suppression and tactical fire over instant headshots:
* Set `AccuracyMin` between `0.25` and `0.32`.
* Set `AccuracyMax` between `0.45` and `0.52`.
* Bound engagement ranges: `ThreatDistanceLimit <= 300.0`.
* Ensure AI belongs to structured factions in `profiles/ExpansionMod/AI/Factions/`:
  * `Survivors`: Neutral / Friendly to players.
  * `Raiders` & `Guards`: Mutually hostile (generates ambient world warfare).
  * `Infected`: Universal enemy to all human AI factions.

### B. Configuration Validation Protocols
Always run syntax checks on configurations before deploying to the server:
* Validate JSON: `python3 -m json.tool <file> > /dev/null`
* Validate XML: `xmllint --noout <file>`
* Maintain local backups (`.bak`) before modifying remote `profiles/` or `mpmissions/` files.

### C. Mod Loading & Ordering Directives
Preserve strict mod initialization order in the server startup parameters:
1. Core Frameworks (`@CF`, `@Dabs Framework`, `@DayZ-Expansion-Core`) must load first.
2. Gameplay mechanics and AI mods load second.
3. Vehicle and base building content packs load third.
4. UI, administrative, and local utility mods load last.
5. All `.bikey` files from mod directories must be copied to the server's `keys/` directory.

---

## 7. Immediate Execution Tasks for Claude Code

Claude Code should execute the following phases in sequence:

1. **Phase 1: GSP Environment Staging**
   * Generate an automated SFTP synchronization script to pull and push `profiles/` and `mpmissions/`.
   * Validate mod keys and generate the exact `-mod=` launch parameter string for the GSP control panel.
2. **Phase 2: Configuration Harmonization**
   * Create balanced `ExpansionAI` and `SpatialAI` preset configs with calibrated accuracy and tripartite faction conflict.
   * Configure `types.xml` to include modded vehicle parts, helicopter assemblies, and CodeLocks in military and industrial zones.
3. **Phase 3: Python Game Master Daemon Build**
   * Write `gm_orchestrator.py`: an asynchronous Python script that connects to the remote BattlEye RCON port, tails `.ADM` logs, and interfaces with Ollama's Gemma 4 E4B endpoint.
4. **Phase 4: Chernarus Validation & Playtesting**
   * Verify all 5 functional modules on ChernarusPlus. Conduct test flights, trailer hitches, and AI skirmishes.
5. **Phase 5: Nasdara (*Badlands*) Porting Preparation**
   * Structure waypoint and mission files so that coordinates can be swapped to Nasdara positions immediately upon the DLC map's release.