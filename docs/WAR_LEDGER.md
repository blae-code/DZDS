# The War Ledger: Making Player Actions Matter

The ledger is the world's memory. It records who killed whom and where, then once per
restart advances a **war turn** that changes who holds what, how strong each faction is, and
how each faction regards the players. Everything downstream (patrols, diplomacy, radio, and
later quests, traders and loot) reads from it, so player actions show up in the world.

Code: `src/gamemaster/ledger.py` · rules: `presets/ledger.yaml` · CLI: `tools/war.py` ·
state: `gm_state/war_ledger.json` (local, not in git).

## The loop
```
 play session                  between sessions                    next session
 ─────────────                 ────────────────                    ────────────
 Players & AI fight  ──► .ADM (LogAIKilled, faction="…")
                     ──► GM daemon records each AI death at the nearest site (≤600 m)
                                 make prepare-restart
                                 ├─ war-turn:  pressure → sites contested / taken
                                 │             strength, resources, off-screen fighting
                                 │             standing → thresholds → timed diplomacy
                                 ├─ diplomacy: ledger overrides → @DZDS diplomacy.json
                                 ├─ patrols:   garrisons follow the new front line
                                 └─ economy, overlays, calibrate, validate → make push
                                                                 ──► new patrols where sites changed hands
                                                                 ──► truces / lockdowns in effect
                                                                 ──► GM opens with a radio war report
```

## What players can do, and what happens
| Player action | Ledger effect | What you see next restart |
|---|---|---|
| **Clear a faction site** (e.g. kill 8+ Jackals at Gorka) | Players fight *for the Settlers*: their kills are Settler pressure → site contested → **taken for the Settlers** | Jackal ambush gone; a Settler **farm watch** holds Gorka; radio: "settlers took Gorka" |
| **Hunt one faction** | Its strength drops (fewer resources, sites start falling off-screen); its enemies like you more | Its patrols thin; rivals push into its land |
| **Shoot the UN** | UN standing falls; below −30 → **UN lockdown** for 7 days (UN treat settlers as hostile) | UN checkpoints open fire; quartermaster closed; radio advisory |
| **Kill tribesmen the others hate** | "Enemy of my enemy": each hostile faction gains standing | Above +40: **Karkas grant passage** / **Rust extend water rights** (timed truces) |
| **Kill settlers** (or recruits) | Settler standing falls; below 0 → `settlers_distrust` flag | (design) recruits refuse, settler quests close |
| **Claim a homestead** (`tools/war.py claim "Host's Homestead" X Z`) | Becomes a Settler site; never falls off-screen, only to real fighting | A Settler farm watch garrisons your homestead |
| **Stay away for a week** | Off-screen fighting resolves by strength (seeded, reproducible) | The front has moved; the GM tells you how |
| **Watch AI fight AI** | Their kills count too (Rust vs Karkas at the dam) | The dam changes hands without you firing a shot |

Standing also **drifts back** toward each faction's baseline (2 points per turn), so old grudges
fade unless you keep them alive, and timed diplomacy expires on its own.

## Commands
```bash
make war-status                                   # front line, strength, standing, active diplomacy
make war-turn                                     # advance one turn (guarded: once per 2 h)
.venv/bin/python tools/war.py turn --force        # advance anyway (testing)
.venv/bin/python tools/war.py claim "Host's Homestead" 5200 8600 --roles inland_town
.venv/bin/python tools/war.py reset               # back to initial_control (old state kept as .bak)
make prepare-restart                              # war-turn → economy → diplomacy → patrols → ...
```

## Tuning (`presets/ledger.yaml`)
Pressure needed to contest or take a site, strength regen and losses, off-screen chances,
standing per kill, "enemy of my enemy" bonus, decay, and the threshold events (each with its
diplomacy overrides and duration). Tests in `tests/test_ledger.py` pin the *behaviour*
(liberation, lockdown, expiry, AI-vs-AI front moves, determinism), not the numbers.

## Built on top of the ledger
| Feature | How | Where |
|---|---|---|
| **Traders follow control** | open / relocated / closed by who holds their role's sites | `make front-plan` (tools/front_plan.py) |
| **Quests from the front** | templates instantiate at contested, held, water and raid-target sites; givers at the faction's nearest site; standing gates | presets/quests.yaml, `make front-plan` |
| **Loot follows control** | Military/Industrial spawn factors from who holds those sites (contested counts half) | presets/economy.yaml `war:`, `make economy` |
| **Physical markers** | @DZDS places a marker object per site by holder at server start (non-persistent) | presets/world.yaml, `make dzds-profile` |
| **Raids on settlements** | strong, hostile faction → one-restart ONCE raid patrol at a claimed homestead | presets/ledger.yaml `raids:`, `make patrols` |
| **Named deeds** | the top player at a liberation is named in the war report | presets/ledger.yaml `deeds:` |
| **Vehicles follow control** | vehicle events placed at sites by role + holder | presets/vehicle_events.yaml, `make vehicle-events` |

Remaining in-game work: choose the marker objects, write Expansion quest/trader JSON once its
example files exist (front_plan already decides what should exist where), and the checks in
docs/PLAYTEST.md.

## To verify on the local server
- [test] Kill attribution: `LogAIKilled` lines carry `faction="…"` for both sides as parsed.
- [test] Site radius (600 m) feels right for Chernarus towns; tune per map.
- [test] Restart cadence vs `min_hours_between_turns`.
