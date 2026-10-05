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

## Next ways to make it more tangible
1. **Traders follow control**: a trader only exists while its faction holds its site (presets/traders.yaml).
2. **Quests from the front**: "break the siege" targets the site contested *now*; quest givers move with control.
3. **Loot follows control**: military loot at a site depends on who holds it (UN-held = guarded but
   intact; Jackal-held = picked over).
4. **Physical markers via @DZDS**: faction flags or banners at held sites, burnt wrecks and bodies
   at sites that changed hands, so you *see* the war turn when you arrive.
5. **AI raids on player settlements**: when a hostile faction is strong and its standing with you is
   low, the ledger schedules a raid patrol against your homestead.
6. **Named deeds**: the GM can name the players in war reports ("Host's militia drove the Jackals
   out of Gorka"), so the world remembers who did it.

## To verify on the local server
- [test] Kill attribution: `LogAIKilled` lines carry `faction="…"` for both sides as parsed.
- [test] Site radius (600 m) feels right for Chernarus towns; tune per map.
- [test] Restart cadence vs `min_hours_between_turns`.
