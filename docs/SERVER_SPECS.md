# Recommended Server Specs

Calculated 2026-10-05 from the enabled mod list (`make specs` reruns it after pruning).
Mod sizes are **real** Workshop download sizes from the Steam API; RAM figures are
**estimates** from the heuristics in §2. Confirm with the measurements in §4 on the local
test server before buying a plan.

## 1. Summary

| Loadout | Mods | Mod download | Server RAM | Server disk | Per-player disk |
|---|---|---|---|---|---|
| Everything enabled today | 96 | 24.7 GB | **~14 GB** | ~50 GB | ~50 GB |
| After Tier 1 pruning (docs/PRUNING.md) | 87 | 16.0 GB | **~11 GB** | ~36 GB | ~41 GB |
| After Tier 1 + Tier 2 | 80 | 11.7 GB | **~10 GB** | ~30 GB | ~37 GB |

**Recommendation: rent 12 GB RAM** on a high-clock CPU and prune Tier 1 before launch. The full
list fits in 14–16 GB; 8 GB (the spec's lower bound) is too tight for this mod count with ~60 AI.

### GSP plan to ask for
| Item | Recommendation | Why |
|---|---|---|
| **CPU** | Newest high-clock desktop chip: Ryzen 7000/9000 (e.g. 7950X/9950X) or Intel 13th/14th gen, ≥ 5 GHz boost | DayZ's simulation runs mostly on one thread; Expansion AI (each bot simulated like a player), ~60 active, plus vehicles, trains and planes make single-thread speed the bottleneck |
| **RAM** | **12 GB** (14–16 GB if you keep all 96 mods) | §2 estimate; Badlands' bigger map adds a little |
| **Disk** | NVMe, ≥ 50 GB | install + mods + persistence + on-box backups; NVMe shortens the long modded start |
| **Slots** | 10 | AI don't use slots; 1–4 players + spare for friends of friends |
| **Network** | ≥ 100 Mbps, location close to you and your friends | latency matters more than bandwidth at 4 players |
| **Access** | SFTP, RCON, custom `-mod`/`-serverMod`, startup params, scheduled restarts | docs/GSP_CHECKLIST.md |
| **Restarts** | every 4 h (6 war turns/day) or 6 h | clears memory growth from AI; each restart is a war turn |

## 2. How the numbers are calculated (`tools/specs.py`)
```
server RAM  = (3.0 GB vanilla base
               + 0.25 × mod download GB      # resident configs, geometry, scripts
               + 1.5 GB ~60 AI, 4 players, vehicles, persistence) × 1.25 headroom
server disk = (3 GB install + mod GB + 5 GB persistence/logs/backups) × 1.5
client disk = ~25 GB DayZ + DLC + mod GB
```
The constants are deliberately conservative rules of thumb for heavily modded DayZ servers,
not measurements of *this* server. Replace them with measured values (§4) and `make specs`
gives real figures.

**CPU** isn't a formula: what matters is **server FPS** under load (§4). The budget lever is the
AI count, not the hardware: `LoadBalancingCategories`, patrol template sizes and chances
(`presets/factions.yaml`), War Zone and convoy caps (docs/LIVING_WORLD.md §5).

## 3. Your PC (local test server + client + GM)
Ryzen 7 7800X3D, RX 7900 XTX 24 GB, 32 GB RAM:

| Running | RAM | VRAM | Verdict |
|---|---|---|---|
| DayZ client (heavily modded) | ~10–14 GB | ~8–12 GB | fine |
| Ollama Gemma 4 E4B (ROCm) | ~1 GB | ~3–3.5 GB | fine (spec §3) |
| GM daemon | < 0.5 GB | – | fine |
| **Local test server** (all mods) | ~11–14 GB | – | **tight**: client + server + OS ≈ 25–30 GB of 32 |

For playtesting with everything enabled, close browsers and other apps. After Tier 1 pruning it's
comfortable. If you test often with the full list, **64 GB** removes the squeeze. Once the GSP
runs the server, your PC only runs the client, Ollama and the GM: no constraints.

## 4. Measure before you buy (local server, docs/PLAYTEST.md)
| Measure | How | Target |
|---|---|---|
| Server RAM after 2 h with players + AI | `htop` / `ps -o rss -C DayZServer` | ≤ 75% of the plan you'll rent |
| Server FPS under load | the server's FPS lines in the `.RPT` (`make logs`) during a War Zone fight + convoy + 4 players | stays ≥ 30; investigate below 20 |
| Start time | boot to "joinable" | informational (modded servers take minutes) |
| Client download | Workshop sizes (`make specs`) | what friends must download |

Update the constants in `tools/specs.py` with what you measure; the summary table above is
then reproducible with `make specs`.

## 5. For your friends' PCs
- **Disk**: ~41–50 GB free for DayZ + mods (more with all 96 mods).
- **RAM**: 16 GB recommended (DayZ's 8 GB minimum is not enough with this many mods).
- **GPU**: DayZ's recommended tier (e.g. GTX 1060 6 GB / RX 580 8 GB) or better.
- **Badlands**: players need the DLC to join if the server runs Nasdara.
