# Phase 4: ChernarusPlus Validation Checklist

Run after every loadout change. Tick boxes in a branch/PR per test session.

## Boot
- [ ] Server boots with `make modstring` output; no missing-mod or signature errors in `.RPT` (`make logs`)
- [ ] All `.bikey`s present in server `keys/` (`make keys`)
- [ ] Client joins via Proton with BattlEye; friends can join `GSP_IP:2302`

## Module 1: Core
- [ ] CF / Dabs / Expansion-Core load without script errors in `.RPT`

## Module 2: Living world
- [ ] Expansion AI patrols spawn; hit rate feels suppressive, not instant headshots
- [ ] Raiders vs Guards fight each other unprompted; Survivors are neutral to players
- [ ] Dynamic AI Missions, heli crash, airdrop, hacked crate events all fire at least once
- [ ] Zombies/AI bash wooden doors; birds scatter on gunfire; blood trails visible

## Module 3: Mobility
- [ ] Land Rover / beater spawn, repair with native parts (plug, battery, radiator), drive
- [ ] Keys lock/unlock; lockpick works
- [ ] Tow a vehicle/trailer; car cover hides and freezes a vehicle
- [ ] Little Bird: assemble/fuel, take off, land; quad and bicycle ride
- [ ] Inventory access while seated; earplugs toggle

## Module 4: Base
- [ ] BBP walls/gate/tower on uneven terrain (BuildAnywhere); code lock on gate
- [ ] MuchStuffPack furniture crafts and stores; ZenSleep fatigue loop; harvest yields sane

## Module 5: Telemetry / GM
- [ ] Map only via physical item; no 3D HUD markers
- [ ] VPP admin works for host only
- [ ] `make gm` (dry run) prints a digest and a sensible JSON decision
- [ ] `GM_DRY_RUN=0 make gm` delivers a radio broadcast in-game via RCON
