# Immersion: Voice, NPCs, and Atmosphere Without Tedium

Companion to `docs/LIVING_WORLD.md`. Mods named here were checked on the Workshop
(2026-10-05) and added to `config/mods.yaml` as **disabled candidates** unless noted.
**[test]** = behaviour to confirm on the local server.

---

## 1. Voice comms

### Is vanilla voice immersive?
Mostly yes. It's one of DayZ's strengths:
- **Proximity voice is 3D-positional**, with whisper / normal / shout levels. Someone shouting
  in the next building sounds like it.
- **Radios are physical items.** The Personal Radio needs a 9V battery and a tuned
  frequency; voice through it gets a radio filter, and a receiving radio's speaker plays into
  the world, so people standing near it hear the transmission too. A Base Radio (field
  transceiver, car battery) and a **megaphone** also exist.
- **Masks muffle your voice** (gas masks etc.).
- Server setting `vonCodecQuality` controls voice quality; with 1–4 players bandwidth isn't a
  concern, so set it high (the local config uses 20; try up to 30).

Weak spots:
- **Discord bypasses all of it.** The biggest immersion leak isn't the engine, it's
  out-of-game voice.
- A switched-on vanilla radio transmits whenever you talk (no separate push-to-talk) **[test]**.
  That's why the WalkieTalkie PTT mod exists.

### Recommendations (cheapest first)
1. **House rule: in-game voice only once you've spawned.** Separated players must find,
   power and tune radios to coordinate. This costs nothing and does more than any mod.
2. **Make radios part of co-op kits.** The low-friction pillar: when friends join, their
   prepared kit includes a radio pair, spare 9V batteries and an agreed frequency. A base
   radio at the compound gives the base a "comms room".
3. **Radio loot tuning** (`presets/types_dzds.yaml`): 9V batteries and radios common enough
   that comms are a short task, not a quest.
4. **A frequency plan that means something** (needs @DZDS, see 5):
   | Freq | What you hear |
   |---|---|
   | your group's channel | each other |
   | civil emergency | GM broadcasts: warnings, rumours, war reports |
   | CDF / ChDKZ channels | **intercepted faction chatter** when their patrols are near |
5. **Make GM broadcasts actual radio audio** (via the @DZDS mod in LIVING_WORLD §6).
   Today the GM uses RCON `say -1`, which shows as on-screen text for everyone, with no
   radio needed. DayZ can't synthesize speech at runtime, but the mod can ship a **library of
   pre-made clips**: generate them on your PC with a local TTS engine (e.g. Piper), add a radio
   filter (sox), and pack them into @DZDS. The GM then picks clips by tag
   (faction × event × place) and the server plays them only on radios tuned to the right
   frequency. This also replaces AI Voice Broadcast, which its author says has been broken
   since 1.29.

### Voice mods considered
| Mod | Verdict |
|---|---|
| WalkieTalkie Push-To-Talk (3788057652) | **Maybe.** Real PTT for radios is a big usability win, but only 74 users; test it |
| Psyern's Radio Show (3627848296) | Optional flavour: 7 music stations on radios/car/base radios. Mood can work in a ruined world, but it's music, not news |
| OMD_Radio (3410416232) | Skip: synced cassette/car music, Russian UI |
| NoVoiceMuffle / NoMuffle | **Reject**: removes the vanilla mask muffling, which is good immersion |
| Zens Immersive Chat HUD | Skip: text bubbles; you'll all have mics |
| Muffled Unconscious (3667280991) | Nice idea (hear the world faintly while knocked out); 35 users, test first |

---

## 2. NPC depth and polish

### Strong candidates
| Mod | What it adds | Notes |
|---|---|---|
| **PvZmoD Customisable Zombies** (2051775667, 604k users, updated 2026-07) | Per-category zombie health, speed, strength and vision, **separately for day and night**; zombies break unlocked doors; every feature can be switched off on its own | Almost certainly the spec's "PvZ MOAR Door Bashing". **Recommend it over Zen's Door Bangers**: day/night behaviour (night is dangerous) is a huge atmosphere lever. Pick one, not both |
| **KAN Survivor NPC – Expansion AI Camps** (3783303198) | Persistent NPC camps with roles (builders, looters, guards, snipers), construction, storage, equipment progression, relations with players, **raids between camps** | Exactly the "living world" idea, on Expansion AI. But brand new (Sep 2026, ~600 users). Has an admin build UI. **Top candidate for the local test server** |
| **Dialogue Framework for Expansion** (3767910705) | Branching conversations: Survivor NPCs greet you, trade rumours, give and take quests through dialogue | Requires Expansion Quests **and Market**, so it pulls in a trader economy. Decide with the Quests question (LIVING_WORLD decision 2) |
| **DayZ-Dog** (2471347750, 489k users) | A dog companion that follows, attacks infected and waits; tame wild dogs with meat or bones | Great for solo depth. Diegetic: you earn it in-world |
| **Ambient Animals Pack** (3114410963, 250k users) | Rabbits, squirrels, ravens, rats, seagulls, otters with their own AI and sounds | Makes the world feel inhabited at very low cost. Pairs with Flying Birds |
| Doc's Animals (2886393751) | Trophy mounts, skin rugs, more species | Optional: nice for homesteading |

### Polish we do ourselves (no mods)
- **Faction loadouts.** Expansion loadout JSONs give each faction a recognisable look: CDF
  in woodland camo with Western kit, ChDKZ in mixed Soviet gear and armbands, Raiders in
  civilian clothes with mismatched gear, Survivors in plain civilian clothes. **Identifying friend
  or foe by uniform is diegetic** and needs no markers.
- **Loot-on-death per faction** (`LootDropOnDeath`): soldiers drop military scraps, Survivors drop food.
  What you find on a body tells you who fought there.
- **Patrol behaviour variety**: `Formation`, `Speed`/`UnderThreatSpeed`, `DefaultStance`,
  `LootingBehaviour` per faction, so CDF move in disciplined files and Raiders straggle.

### Rejected
TalkingNPC (stale since 2024; trigger-based lines), AI Bandit Voices (only for the AI Bandits
framework, which we don't use), novelty zombie packs (break tone).

---

## 3. Immersion without tedium

**The test for every mechanic:** does it create a *decision* or a *story*, or just a repeated
chore? Keep the first; automate or cut the second.

| Immersive (keep) | Tedious (avoid) |
|---|---|
| Night is genuinely dark, so light is a choice (stealth vs safety) | Engine oil, wheel wear, dipsticks (e.g. RaG Immersive Vehicles: **rejected** by spec pillar) |
| Weather that changes plans (fog mornings, storms) | Long fixed action timers with no risk |
| Wildlife and birds that react to you | Frequent micro-needs (sleep every 30 min) |
| Bodies and wrecks that tell you what happened | Mandatory multi-step crafting for basics |
| Radios needing batteries (one cheap step) | Item decay that forces constant re-crafting |

### Zero-mod levers (server config), the biggest wins
| Setting | File | Suggestion |
|---|---|---|
| Map shows no player position | `cfggameplay.json` → `MapData.displayPlayerPosition: false` | Find yourself with landmarks and a compass |
| Map/compass must be held (applied by `make overlays`, needs `enableCfgGameplayFile = 1`) | `MapData.ignoreMapOwnership: false`, `ignoreNavItemsOwnership: false` | Paper map + compass, as the spec wants. **This may make BasicMap unnecessary**, which removes a stale mod |
| Darker nights | `serverDZ.cfg lightingConfig` (or Dark-Ish Nights mod for a middle setting) | Dark enough that light matters, not black-screen |
| Day/night length | `serverTimeAcceleration`, `serverNightTimeAcceleration` | Long evenings, short-ish nights |
| Weather | mission `cfgweather.xml` | More fog and rain fronts; no mod needed |
| Crosshair / 3rd person | `disableCrosshair`, `disable3rdPerson` | **Decided: first-person only, no HUD crosshair** (set in `config/local_serverDZ.cfg`; mirror on the GSP panel). Optional mod for later: Generic_Gunplay's barrel-aligned crosshair (brand new, evaluate) |
| Personal light | `disablePersonalLight = 1` | Removes the invisible glow around players at night; real light sources matter |

### Low-cost immersion mods
| Mod | Why |
|---|---|
| **Zens Immersive Login** (2924719512) | You wake up lying down and open your eyes; fresh spawns get a campfire. Free immersion, no chore |
| **Immersive Placing Update** (3753472356) | Place items exactly where you aim. Makes base dressing satisfying; verified on 1.29 |
| RaG Immersive Wells (3406196859) | Pump animation, splashes; optionally wells can run dry. Fits **arid Nasdara**; keep cholera off |
| Dark-Ish Nights (3346147359) | Only if vanilla bright/dark nights are both wrong; stale (2024) |

### Tuning existing mods against tedium
- **Zens Sleeping Mod**: set fatigue slow, so sleep is a once-per-evening ritual at camp, not an interruption.
- **PvZmoD**: harder zombies at night, easier by day, so time of day becomes a strategic choice.
- **Zens Blood Trail**: drips that fade within an hour or so; tracking stays possible but the world doesn't fill with stains.
- **Vehicles**: stay on native parts (plugs, battery, radiator, fuel); no wear mods.
- **Co-op friends**: prepared kits (radio, map, compass, food, a keyed vehicle) so they play the world, not the menus.

---

## 4. Suggested shortlist
Enable for the first local-server test:
1. PvZmoD Customisable Zombies (instead of Zens Zombie Door Bangers)
2. Ambient Animals Pack
3. Zens Immersive Login
4. Immersive Placing Update
5. DayZ-Dog

Evaluate next: KAN Survivor NPC camps, WalkieTalkie PTT, Dialogue Framework (with the Quests decision).
Config: vanilla paper map with `displayPlayerPosition: false`, and consider dropping BasicMap.
