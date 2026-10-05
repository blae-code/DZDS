# Game Server Provider Checklist

Ask sales/support or check the panel demo before buying. Every "no" breaks part of this repo.

| Requirement | Why | Breaks if missing |
|---|---|---|
| **SFTP** (not just FTP) access to `profiles/` and `mpmissions/` | `scripts/sync.sh`, GM log tailing | sync + GM telemetry (FTP-only would need code changes) |
| **BattlEye RCON** enabled, port + password configurable, reachable from your home IP | GM broadcasts | GM output |
| Upload / auto-install Workshop mods by ID, custom `-mod=` / `-serverMod=` | 35-mod loadout | the loadout |
| Edit startup params (`-dologs -adminlog`) | `.ADM` logging the GM reads | GM telemetry |
| High-clock CPU (Ryzen 7000/9000, Intel 13/14th gen) | DayZ server is mostly single-threaded; Expansion AI is CPU-heavy | AI-heavy world stutters |
| 8–12 GB RAM | spec target with this mod count | crashes, desync |
| Server region close to you + friends | latency | |
| Supports Badlands/Nasdara (1.30) at launch, or soon after | Phase 5 | |
| Scheduled restarts configurable (e.g. every 4–6 h) | AI/loot cleanup, memory | |
| Monthly billing, no long contract | mods may force changes | |

Notes:
- Nasdara is a paid DLC: **players** need to own it; the server doesn't.
- Note the SFTP port and the remote root path the panel uses; they go into `.env`.
- Spec candidates: GTXGaming, Host Havoc. Confirm the SFTP and RCON rows specifically;
  some budget hosts lock RCON or offer FTP only.
