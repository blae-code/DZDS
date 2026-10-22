# Badlands Relaunch + Zone-Bound Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relaunch Ad Aspera on Nasdara (Badlands, DayZ 1.30). Loot stays pure vanilla, every human NPC and event stays inside faction strongholds and warzones apart from one rare war party, and arrivals get a pre-tuned radio, a road flare, a same-day refugee column, respawns near where the last character died, and archetype cargo carrying one themed firearm.

**Architecture:** One active-map selector feeds the existing role-based generators. A new zone model (`tools/zones.py`) is the single source for "where things may happen". The war ledger picks at most one war party per restart. A new `tools/zone_events.py` rewrites every event mod's positions from the zones, and pytest proves every generated position lies inside a zone. Arrivals stay in the mission `init.c` (Enforce Script), compiled from `presets/arrivals.yaml` by `tools/arrivals.py`, with a Python mirror of the cargo algorithm for tests.

**Tech Stack:** Python ≥ 3.11 (pyyaml, pytest), DayZ Enforce Script (mission `init.c`), bash (`scripts/`), Make, SFTP via `scripts/sync.sh`.

**Spec:** `docs/superpowers/specs/2026-10-15-badlands-relaunch-design.md`. Read it before any task.

## Global Constraints

- Hard rules in `CLAUDE.md` apply to every task. In particular: `make validate` before any push (rule 1); pushes back up first (rule 2); no secrets in git and never print `.env` values (rule 3); AI `AccuracyMin` ∈ [0.25, 0.32], `AccuracyMax` ∈ [0.45, 0.52], `ThreatDistanceLimit` ≤ 300 (rule 5); diegetic only, so no 3D/map markers, HUD event notifications or spawn menus (rule 6).
- Loot: Nasdara's vanilla `types.xml`, unchanged except the arrival-vehicle lifetime (`script_vehicle_lifetime: 3888000`).
- Zone radius default **400 m**. Strongholds **6–9** held sites, **1–2** contested at launch. Each of the five factions holds 1–2.
- War party: chance **0.35** per restart, **at most one** active map-wide. It is the only generated position allowed outside a zone.
- Encounter target: **≤ 1 AI encounter outside zones per player per ~3 sessions**.
- Body kit: vanilla default + `PersonalRadio` with a `Battery9V` attached, tuned to the Settler net index and **switched off**, + one `Roadflare`.
- `vonCodecQuality = 30` in `config/local_serverDZ.cfg` **and** the panel.
- Arrival sites: 3–5 km from the starting Settler stronghold; `points_per_site` ≥ 8.
- Respawn: road point 2–5 km from the previous death; widen to 8 km; then any road point.
- Cargo: one archetype (Deserter 30 / Trucker 25 / Nomad 25 / Townie 20). Draws are without replacement, max 1 each (food 2), ≈ 10–16 items + exactly one firearm. Firearm health 0.45–0.70; ammo is a partly filled magazine (2–5) **or** 3–8 loose rounds; no spare magazines.
- Panel changes, service restarts and deletions on the server are **Blae's**. Prepare the exact values and hand them over.
- Never `cp -a` anything into `~/Documents/ROOT` (unrelated to this repo; listed because the operator's global rules forbid it).
- Run Python via `.venv/bin/python`. Tests: `make test` (pytest, `pythonpath = src tools tests`).
- Work on branch `badlands-relaunch` (created in Task 1). Commit after every task.

## Review Focus

1. **More same-day arrivals than free spots at the column site.** A busy launch night must spill to the next site in the rotation, never fall back to vanilla spawning. Pinned in Task 16 (every site ≥ 8 points; the compiled `ColumnSites` order covers every site).
2. **A turn with no contested site, or every faction too weak.** There's no war party, War Zones is disabled (`Enabled 0`, `maxConcurrentZones 0`, its template entry kept), and nothing crashes. Pinned in Tasks 8 and 10.
3. **A player-claimed settlement out in open country.** It must become a Settler zone (so raids and garrisons there are legal) rather than trip the placement test. Pinned in Task 7.
4. **Running `make prepare-restart` twice.** Event configs and convoy route files must be identical after the second run (no duplicate routes, no second war party). Pinned in Task 10.
5. **A firearm with no detachable magazine** (Mosin, SKS, shotguns, revolvers). It gets loose rounds and never an empty `Magazine` field the Enforce side would try to spawn. Pinned in Task 18.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `tools/active.py` (new) | Active map + mission resolution (env override, repo default) | 2 |
| `tools/map_survey.py` (new) | Candidate sites per role from a mission's `mapgrouppos.xml` | 3 |
| `maps/nasdara.yaml` | Nasdara locations, roles, zone radii, arrival sites | 4 |
| `tools/maps_check.py` | + per-map `role_min` overrides | 4 |
| `config/mods.yaml`, `presets/overlays/*` | Pruned loadout | 5 |
| `tools/economy.py`, `presets/economy.yaml`, `presets/types_dzds.yaml` | Pure vanilla economy | 6 |
| `tools/zones.py` (new) | Zone model: build from control, inside/zone_of | 7 |
| `src/gamemaster/ledger.py`, `presets/ledger.yaml`, `presets/convoys.yaml` (new) | War party (≤ 1) replaces raids | 8 |
| `tools/front_plan.py` | Raid quest target from the war party | 8 |
| `tools/patrol_gen.py`, `presets/factions.yaml` | Patrols stay inside zones; war-party patrol | 9 |
| `tools/zone_events.py` (new), `presets/zone_events.yaml` (new) | Airdrop / heli / crate / War Zones / convoy configs from zones | 10 |
| `tools/kan_camps.py`, `presets/kan_camps.yaml` | KAN camps placed at Settler sites | 11 |
| `tests/test_zone_placement.py` (new), `Makefile` | Placement invariant; `prepare-restart` wiring | 12 |
| `tools/encounter_audit.py` (new) | Encounters outside zones per player-session from `.ADM` | 13 |
| `server/mpmissions/<nasdara>/init.c` | Arrivals port, start kit, column, respawn-near-death, archetype cargo | 14–18 |
| `presets/arrivals.yaml`, `tools/arrivals.py` | Arrival config + compile + Python cargo mirror | 15–18 |
| `docs/*`, `CLAUDE.md` | Docs follow the change | 20 |

---

## Phase A: Foundation

### Task 1: Archive Chernarus, install 1.30, seed the Nasdara mission

Operational task, with no new code. Produces the archive, the branch and the vanilla Nasdara mission files every later task reads.

**Files:**
- Create: `backups/chernarus-final-<ts>/` (gitignored)
- Create: `server/mpmissions/<nasdara mission>/` (vanilla copy, committed)

- [ ] **Step 1: Branch**

```bash
cd ~/Documents/Code/DayZ
git switch -c badlands-relaunch
```

- [ ] **Step 2: Pull and archive the live Chernarus state**

```bash
make pull
TS=$(date +%Y%m%d-%H%M%S); mkdir -p backups/chernarus-final-$TS
tar -czf backups/chernarus-final-$TS/server-mirror.tar.gz server/
cp -r gm_state backups/chernarus-final-$TS/ 2>/dev/null || true
du -sh backups/chernarus-final-$TS server/
```
Expected: the tarball exists, and its compressed size is plausible against `du -sh server/` (≥ 10% of it).

- [ ] **Step 3: Tag**

```bash
git add -A server/ && git commit -m "server/: final Chernarus mirror before the Badlands relaunch" || true
git tag chernarus-final
```

- [ ] **Step 4: Install the 1.30 dedicated server locally**

```bash
scripts/local_server.sh install
ls ~/dayz-server/mpmissions/
```
Expected: a Nasdara mission folder is listed (e.g. `dayzOffline.nasdara`). **Record its exact name**; every later task uses it as `<NASDARA>`. If no Nasdara folder appears, stop and tell Blae (the server build hasn't shipped the map).

- [ ] **Step 5: Seed the vanilla mission into the repo**

```bash
N=<NASDARA>   # the exact folder name from Step 4
cp -r ~/dayz-server/mpmissions/$N server/mpmissions/
cp server/mpmissions/$N/init.c server/mpmissions/$N/init.c.vanilla
ls server/mpmissions/$N/db/types.xml server/mpmissions/$N/mapgrouppos.xml server/mpmissions/$N/cfgeventspawns.xml
```
Expected: all three files exist.

- [ ] **Step 6: Commit**

```bash
git add server/mpmissions/$N
git commit -m "server/: seed vanilla Nasdara mission from the 1.30 server"
```

---

### Task 2: Active-map selector

Every tool currently defaults to `chernarusplus` in a dozen places. Replace them with one module.

**Files:**
- Create: `tools/active.py`
- Modify: `tools/arrivals.py`, `tools/vehicle_events.py`, `tools/loadouts.py`, `tools/dzds_profile.py`, `tools/apply_overlays.py`, `tools/economy.py`, `tools/apply_ai_calibration.py`, `tools/types_gen.py`, `tools/front_plan.py`, `tools/patrol_gen.py`, `tools/war.py`, `tools/gm_probe.py`, `scripts/local_server.sh`, `Makefile`, `.env.example`
- Test: `tests/test_active.py`

**Interfaces:**
- Produces: `active.map_name() -> str`, `active.map_data(name: str | None = None) -> dict`, `active.mission_name(name: str | None = None) -> str`, `active.mission_dir(name: str | None = None) -> Path`, `active.DEFAULT_MAP: str`, `active.ROOT: Path`. CLI: `python tools/active.py map|mission`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_active.py
"""One place decides which map the tools act on (Badlands relaunch, 2026-10-15)."""
import re

import active


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("GM_MAP", "chernarusplus")
    monkeypatch.delenv("MISSION_NAME", raising=False)
    assert active.map_name() == "chernarusplus"
    assert active.mission_name() == "dayzOffline.chernarusplus"
    assert active.mission_dir() == active.ROOT / "server" / "mpmissions" / "dayzOffline.chernarusplus"


def test_default_map_has_a_map_file(monkeypatch):
    monkeypatch.delenv("GM_MAP", raising=False)
    assert (active.ROOT / "maps" / f"{active.DEFAULT_MAP}.yaml").exists()
    assert active.map_name() == active.DEFAULT_MAP


def test_mission_name_env_wins_only_for_the_active_map(monkeypatch):
    monkeypatch.setenv("GM_MAP", "chernarusplus")
    monkeypatch.setenv("MISSION_NAME", "custom.mission")
    assert active.mission_name() == "custom.mission"
    assert active.mission_name("chernarusplus") == "dayzOffline.chernarusplus"


def test_no_tool_hardcodes_a_default_map():
    pat = re.compile(r"""environ\.get\(\s*["'](GM_MAP|MISSION_NAME)["']\s*,""")
    offenders = [p.name for p in (active.ROOT / "tools").glob("*.py")
                 if p.name != "active.py" and pat.search(p.read_text())]
    assert offenders == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_active.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'active'`.

- [ ] **Step 3: Implement `tools/active.py`**

```python
#!/usr/bin/env python3
"""Which map and mission the tools act on.

GM_MAP / MISSION_NAME in the environment (or .env, which the Makefile exports) override the
repo default below. Change DEFAULT_MAP when the live server changes map.

Usage: tools/active.py map|mission
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MAP = "chernarusplus"   # flipped to "nasdara" in Task 4, once maps/nasdara.yaml is complete


def map_name() -> str:
    return os.environ.get("GM_MAP") or DEFAULT_MAP


def map_data(name: str | None = None) -> dict:
    return yaml.safe_load((ROOT / "maps" / f"{name or map_name()}.yaml").read_text())


def mission_name(name: str | None = None) -> str:
    env = os.environ.get("MISSION_NAME")
    if env and name is None:
        return env
    return map_data(name)["mission"]


def mission_dir(name: str | None = None) -> Path:
    return ROOT / "server" / "mpmissions" / mission_name(name)


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "map"
    print(map_name() if what == "map" else mission_name())
```

- [ ] **Step 4: Replace every hardcoded default**

In each tool listed under **Files**, replace the default lookups:

- `os.environ.get("GM_MAP", "chernarusplus")` → `active.map_name()`
- `os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")` → `active.mission_name()`
- `ROOT / "server" / "mpmissions" / os.environ.get("MISSION_NAME", "dayzOffline.chernarusplus")` → `active.mission_dir()`

Then add `import active` to each file's imports. `tools/` is on `sys.path` when a tool runs as `python tools/x.py` and under pytest. Find every site with:

```bash
grep -n -E 'environ\.get\("(GM_MAP|MISSION_NAME)", ' tools/*.py
```
Expected after editing: no output.

In `scripts/local_server.sh`, change the `MISSION=` line to:

```bash
MISSION="${MISSION_NAME:-$("$PY" "$ROOT/tools/active.py" mission)}"
```
(`PY` is defined two lines below it, so move `PY="$ROOT/.venv/bin/python"` above `MISSION=`.)

In `.env.example`, replace `MISSION_NAME=dayzOffline.chernarusplus` and `GM_MAP=chernarusplus` with:

```bash
# Map/mission default comes from tools/active.py DEFAULT_MAP; set these only to override it.
# MISSION_NAME=
# GM_MAP=
```

- [ ] **Step 5: Make every Make target see `.env`**

In `Makefile`, after `SHELL := /bin/bash`, add:

```make
ENV := set -a; [ -f .env ] && source .env; set +a;
```
Then prefix the recipe lines of `arrivals`, `kan-camps`, `patrols`, `diplomacy`, `war-status`, `war-turn`, `front-plan`, `loadouts`, `dzds-profile` and `maps-check` with `$(ENV) ` (the others already source `.env` inline).

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_active.py -v && make test`
Expected: PASS. Existing tests still run against Chernarus, because `DEFAULT_MAP` is still `chernarusplus`.

- [ ] **Step 7: Commit**

```bash
git add tools/active.py tools/*.py scripts/local_server.sh Makefile .env.example tests/test_active.py
git commit -m "tools: one active-map selector instead of a dozen chernarusplus defaults"
```

---

### Task 3: Map survey tool

Turns the 13,700 building placements in Nasdara's `mapgrouppos.xml` into candidate sites per role, so the map data in Task 4 comes from the map rather than from guesses.

**Files:**
- Create: `tools/map_survey.py`
- Test: `tests/test_map_survey.py`
- Modify: `Makefile` (target `survey`)

**Interfaces:**
- Consumes: `active.mission_dir()` (Task 2)
- Produces: `map_survey.load_groups(path: Path) -> list[tuple[str, float, float, float]]` (name, x, y, z); `map_survey.survey(groups, cell: float = 600.0) -> dict[str, list[dict]]`, where each cluster dict is `{"x": float, "z": float, "y": float, "count": int}` sorted by count desc; `map_survey.bounds(groups) -> list[int]`; `map_survey.ground_y(groups, x, z, within=150.0) -> float`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_map_survey.py
import map_survey

XML = """<?xml version="1.0"?><map>
<group name="Land_Mil_Barracks4" pos="1000.0 50.0 1000.0" a="0"/>
<group name="Land_Mil_GuardShed" pos="1010.0 51.0 1020.0" a="0"/>
<group name="Land_Mil_Guardhouse1" pos="1030.0 52.0 990.0" a="0"/>
<group name="Land_HBarrierTower_TK" pos="1050.0 53.0 1050.0" a="0"/>
<group name="Land_Mil_ContainerWatchTower" pos="1060.0 54.0 1040.0" a="0"/>
<group name="Land_Mil_Tent_Big1_1_Desert" pos="1070.0 55.0 1010.0" a="0"/>
<group name="Land_Water_Station" pos="5000.0 10.0 5000.0" a="0"/>
<group name="Land_House_1W01" pos="9000.0 300.0 9000.0" a="0"/>
</map>"""


def groups(tmp_path):
    p = tmp_path / "mapgrouppos.xml"
    p.write_text(XML)
    return map_survey.load_groups(p)


def test_load_groups_reads_name_and_xyz(tmp_path):
    g = groups(tmp_path)
    assert g[0] == ("Land_Mil_Barracks4", 1000.0, 50.0, 1000.0)
    assert len(g) == 8


def test_survey_clusters_by_role_with_min_count(tmp_path):
    s = map_survey.survey(groups(tmp_path))
    assert len(s["military"]) == 1 and s["military"][0]["count"] == 6
    assert 1000 <= s["military"][0]["x"] <= 1070
    assert s["water"][0]["count"] == 1                  # water needs only one structure
    assert s["town"] == []                              # one house is not a town


def test_high_ground_is_highest_cells_first(tmp_path):
    s = map_survey.survey(groups(tmp_path))
    assert s["high_ground"][0]["y"] == 300.0


def test_bounds_round_up_to_1024(tmp_path):
    assert map_survey.bounds(groups(tmp_path)) == [0, 0, 9216, 9216]


def test_ground_y_uses_nearest_structure(tmp_path):
    g = groups(tmp_path)
    assert map_survey.ground_y(g, 1001.0, 1001.0) == 50.0
    assert map_survey.ground_y(g, 3000.0, 3000.0) == 0.0     # nothing within 150 m
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_map_survey.py -v`
Expected: FAIL, `No module named 'map_survey'`.

- [ ] **Step 3: Implement `tools/map_survey.py`**

```python
#!/usr/bin/env python3
"""Candidate sites per map role from a mission's mapgrouppos.xml (every placed building).

Buckets buildings into a grid, counts the ones whose classname matches a role, and lists the
densest cells per role with their centroid. A human picks and names the sites in
maps/<map>.yaml from this list; the tool never writes the map file.

Usage: tools/map_survey.py [--cell 600] [--top 12]
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import active

ROLE_PATTERNS = {
    "military": re.compile(r"^Land_(Mil_|HBarrierTower|RocketBase|Bunker)", re.I),
    "airfield": re.compile(r"^Land_(Airfield|Mil_ATC|Mil_Hangar|Hangar|Runway)", re.I),
    "industrial": re.compile(r"^Land_(Factory|Workshop|Garage_Row|CementWorks|Oil_|Sawmill|Power|Industrial|Warehouse)", re.I),
    "water": re.compile(r"^Land_(Water_Station|WaterTower|Well|Pump|Dam)", re.I),
    "town": re.compile(r"^Land_(House|HouseBlock|Slum|Store)", re.I),
    "refugee": re.compile(r"^Land_Refugee", re.I),
    "rail": re.compile(r"^Land_(Rail|Track)_", re.I),
}
MIN_COUNT = {"military": 6, "airfield": 3, "industrial": 4, "water": 1, "town": 25,
             "refugee": 3, "rail": 10}
_GROUP = re.compile(r'<group name="([^"]+)" pos="(-?[\d.]+) (-?[\d.]+) (-?[\d.]+)"')


def load_groups(path: Path) -> list[tuple[str, float, float, float]]:
    return [(m[1], float(m[2]), float(m[3]), float(m[4])) for m in _GROUP.finditer(path.read_text())]


def survey(groups, cell: float = 600.0) -> dict[str, list[dict]]:
    cells: dict[str, dict[tuple[int, int], list]] = {r: defaultdict(list) for r in ROLE_PATTERNS}
    every: dict[tuple[int, int], list] = defaultdict(list)
    for name, x, y, z in groups:
        key = (int(x // cell), int(z // cell))
        every[key].append((x, y, z))
        for role, pat in ROLE_PATTERNS.items():
            if pat.search(name):
                cells[role][key].append((x, y, z))

    def cluster(pts):
        n = len(pts)
        return {"x": round(sum(p[0] for p in pts) / n, 1), "z": round(sum(p[2] for p in pts) / n, 1),
                "y": round(sum(p[1] for p in pts) / n, 1), "count": n}

    out = {role: sorted((cluster(p) for p in c.values() if len(p) >= MIN_COUNT[role]),
                        key=lambda c: -c["count"]) for role, c in cells.items()}
    out["high_ground"] = sorted((cluster(p) for p in every.values()), key=lambda c: -c["y"])
    return out


def bounds(groups) -> list[int]:
    top = max(max(x, z) for _, x, _, z in groups)
    side = int(math.ceil(top / 1024.0) * 1024)
    return [0, 0, side, side]


def ground_y(groups, x: float, z: float, within: float = 150.0) -> float:
    best, best_d = 0.0, within
    for _, gx, gy, gz in groups:
        d = math.hypot(gx - x, gz - z)
        if d <= best_d:
            best, best_d = gy, d
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--cell", type=float, default=600.0)
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    path = active.mission_dir() / "mapgrouppos.xml"
    if not path.exists():
        print(f"{path} not found (seed the mission first: Task 1)", file=sys.stderr)
        return 2
    g = load_groups(path)
    print(f"{len(g)} placed structures; bounds {bounds(g)}")
    for role, clusters in survey(g, a.cell).items():
        print(f"\n{role}: {len(clusters)} cell(s)")
        for c in clusters[: a.top]:
            print(f"  [{c['x']:.0f}, {c['z']:.0f}]  y={c['y']:.0f}  n={c['count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Add the Make target**

```make
.PHONY: survey
survey:         # candidate sites per role from the active mission's mapgrouppos.xml
	$(ENV) $(PY) tools/map_survey.py
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_map_survey.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add tools/map_survey.py tests/test_map_survey.py Makefile
git commit -m "tools: map_survey: candidate role sites from mapgrouppos.xml"
```

---

### Task 4: Nasdara map data, initial control, traders, and flipping the default

A data task gated by tests. The tests encode the spec's footprint, so any pick that satisfies them is valid. **Blae approves the picks before commit.**

**Files:**
- Modify: `maps/nasdara.yaml`, `maps/_roles.yaml` (comment only), `tools/maps_check.py`, `presets/factions.yaml` (`initial_control.nasdara`), `presets/traders.yaml` (`sites.nasdara`), `tools/active.py` (`DEFAULT_MAP`), `.env` (two keys)
- Test: `tests/test_nasdara_map.py`

**Interfaces:**
- Produces (`maps/nasdara.yaml` keys every later task reads): `name`, `mission`, `bounds: [xmin, zmin, xmax, zmax]`, `locations: {Name: [x, z]}`, `roles: {role: [Name, ...]}`, `role_min: {role: int}` (optional per-map overrides), `zone_radius_m: 400`, `zone_radius: {Name: metres}` (optional overrides), `arrival_sites: {Name: [x, z]}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_nasdara_map.py
"""Nasdara footprint (spec §4.1, §6.3): compact strongholds, a few warzones, arrival ring."""
import math

import yaml

import maps_check
from active import ROOT

MAP = yaml.safe_load((ROOT / "maps" / "nasdara.yaml").read_text())
ROLES = yaml.safe_load((ROOT / "maps" / "_roles.yaml").read_text())["roles"]
FACTIONS = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())
CONTROL = FACTIONS["initial_control"]["nasdara"]
TRADERS = yaml.safe_load((ROOT / "presets" / "traders.yaml").read_text())["traders"]


def radius(site):
    return float((MAP.get("zone_radius") or {}).get(site, MAP["zone_radius_m"]))


def test_map_passes_maps_check():
    assert maps_check.check(MAP, ROLES) == []


def test_zone_radius_default_is_400():
    assert MAP["zone_radius_m"] == 400


def test_compact_strongholds_and_one_or_two_warzones():
    held = [s for f, sites in CONTROL.items() if f != "contested" for s in sites]
    assert 6 <= len(held) <= 9
    assert 1 <= len(CONTROL.get("contested", [])) <= 2
    for f in ("Peacekeepers", "Rust", "Karkas", "Jackals", "Settlers"):
        assert 1 <= len(CONTROL.get(f, [])) <= 2, f


def test_zones_do_not_overlap():
    sites = [s for sites in CONTROL.values() for s in sites]
    for i, a in enumerate(sites):
        for b in sites[i + 1:]:
            d = math.dist(MAP["locations"][a], MAP["locations"][b])
            assert d >= radius(a) + radius(b), (a, b, round(d))


def test_arrival_sites_ring_the_settler_stronghold():
    settler = [MAP["locations"][s] for s in CONTROL["Settlers"]]
    others = [(MAP["locations"][s], radius(s)) for f, sites in CONTROL.items()
              if f != "Settlers" for s in sites]
    sites = MAP["arrival_sites"]
    assert 3 <= len(sites) <= 8
    for name, xy in sites.items():
        assert 3000 <= min(math.dist(xy, s) for s in settler) <= 5000, name
        for pos, r in others:
            assert math.dist(xy, pos) >= r + 500, (name, pos)
    assert not set(sites) & set(MAP["locations"])     # arrivals never feed the war ledger


def test_every_trader_prefers_a_site_its_faction_holds():
    for tid, t in TRADERS.items():
        site = (t.get("sites") or {}).get("nasdara")
        assert site, tid
        if t["faction"] != "none":
            assert site in CONTROL.get(t["faction"], []), (tid, site)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_nasdara_map.py -v`
Expected: FAIL (`KeyError: 'nasdara'` in `initial_control`, or `zone_radius_m`).

- [ ] **Step 3: Add per-map `role_min` to `tools/maps_check.py`**

In `check()`, replace the minimum line:

```python
        need = (data.get("role_min") or {}).get(role, rule.get("min", 1))
        if len(names) < need:
            problems.append(f"role '{role}' needs >= {need} location(s), has {len(names)}")
```
In `maps/_roles.yaml`, append this comment line under `roles:`:

```yaml
# A map may lower a minimum with `role_min: {role: n}` (e.g. a desert map with no coast).
```

- [ ] **Step 4: Survey and pick the sites**

```bash
GM_MAP=nasdara MISSION_NAME=<NASDARA> make survey > build/survey.nasdara.txt
grep -c "" build/survey.nasdara.txt; sed -n '/^rail:/,/^$/p' build/survey.nasdara.txt
```
Pick sites from the survey with these rules, and name each one after the nearest town label on the iZurvive Nasdara map (izurvive.com):

| Role | Pick | Rule |
|---|---|---|
| airfield | 1–2 | `airfield` cells |
| military | 2–3 | `military` cells with n ≥ 15 |
| industrial | 1–3 | `industrial` cells |
| water | 1–3 | `water` cells, preferring stations/towers outside towns |
| inland_town | 3–5 | `town` cells. One becomes the **Settler settlement**, ideally near a `refugee` cell |
| coastal_town | 0–2 | only if a town sits on the coast. Otherwise set `role_min: {coastal_town: 0}` and move the `medicine` resource (Step 6) |
| high_ground | 2–3 | top `high_ground` cells at least 1 km from any town |
| remote | 1–2 | a structure cell ≥ 3 km from any town |
| road_junction | 1–2 | a junction of two main roads ≥ 2 km from towns, read off iZurvive |

Then choose `initial_control.nasdara`: 6–9 held sites (1–2 per faction, each on a role that faction `holds_roles`) plus 1–2 `contested` sites, with no two zones within `r1 + r2` (800 m at defaults). Choose 4–6 `arrival_sites` on roads 3–5 km from the Settler settlement, avoiding other zones by ≥ 900 m.

- [ ] **Step 5: Write `maps/nasdara.yaml`**

Use this structure. Every value comes from Step 4.

```yaml
# Nasdara (Badlands DLC, game 1.30). Sites picked 2026-10-15 from tools/map_survey.py
# (build/survey.nasdara.txt) and named after iZurvive labels. Approved by Blae <date>.
name: nasdara
mission: <NASDARA>
bounds: <from the survey header>
zone_radius_m: 400
zone_radius: {}            # per-site override, e.g. { "Big Airfield": 550 }
role_min: {}               # e.g. { coastal_town: 0 } if Nasdara has no coastal town
locations:
  <Site Name>: [<x>, <z>]
roles:
  airfield: [<Site Name>]
  military: []
  coastal_town: []
  inland_town: []
  industrial: []
  road_junction: []
  remote: []
  high_ground: []
  water: []
arrival_sites:             # NOT war locations; tools/arrivals.py snaps them to roadside spots
  <Village Name>: [<x>, <z>]
```

- [ ] **Step 6: `initial_control.nasdara`, the resource fallback, and traders**

In `presets/factions.yaml` under `initial_control:` add:

```yaml
  nasdara:
    Peacekeepers: [<1-2 airfield/military sites>]
    Rust: [<1-2 industrial/water sites>]
    Karkas: [<1-2 high_ground/remote sites>]
    Jackals: [<1 road_junction site>]
    Settlers: [<1-2 inland_town sites; the first is the settlement>]
    contested: [<1-2 sites>]
```
If `coastal_town` has no sites, change `resources.medicine.from_roles` to `[military]` and leave a dated comment saying why.

In `presets/traders.yaml`, add `nasdara: <site>` to every trader's `sites:` map. Each one must be a site its faction holds in `initial_control.nasdara` (for the `none` faction, any non-contested site of its role).

- [ ] **Step 7: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_nasdara_map.py -v`
Expected: PASS (6 tests). Fix the data, not the tests.

- [ ] **Step 8: Blae approves the picks**

Show Blae a table of site → role → holder → coordinates, plus the arrival sites, and wait for his yes. He may move sites. Re-run Step 7 after any change.

- [ ] **Step 9: Flip the default map**

In `tools/active.py`: `DEFAULT_MAP = "nasdara"`. In `.env`, comment out the two override keys **without printing the file** (it holds secrets):

```bash
sed -i -E 's/^(GM_MAP|MISSION_NAME)=/# \1=/' .env
grep -c -E '^(GM_MAP|MISSION_NAME)=' .env   # expect 0
```

Then start the Nasdara war ledger (the Chernarus one was archived in Task 1):

```bash
.venv/bin/python tools/war.py reset
```
Expected: a report listing the Nasdara holders from `initial_control.nasdara`.

- [ ] **Step 10: Run the whole suite**

Run: `make test`
Expected: PASS. Tests that hardcode `chernarusplus` keep using the archived Chernarus data; nothing else should change.

- [ ] **Step 11: Commit**

```bash
git add maps/ tools/maps_check.py tools/active.py presets/factions.yaml presets/traders.yaml tests/test_nasdara_map.py
git commit -m "maps: Nasdara sites, roles, zones and arrival ring; active map is now nasdara"
```

---

## Phase B: Prune and pure vanilla

### Task 5: Prune the mod list

**Files:**
- Modify: `config/mods.yaml`, `docs/PRUNING.md`
- Delete: `presets/overlays/zombie_horde.yaml`, `presets/overlays/spatial_ai.yaml`, `presets/overlays/expansion_missions.yaml`
- Test: `tests/test_presets.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_presets.py`:

```python
PRUNED_BADLANDS = {
    3689174025: "SF Zombie Horde Event",       # targets players anywhere; can't respect zones
    2874589934: "DayZ-Dynamic-AI-Addon",       # Spatial AI already at MaxAI 0
    2792984177: "DayZ-Expansion-Missions",     # every feature off
    2147610525: "Armored Vehicle Pack", 1912237302: "IRP-Land-Rover-Defender-110",
    2757080411: "Crocos Quadbike", 2298127647: "Arma 2 Clothing Pack",
    2074403068: "Unknown Ghillie Mod", 2361330944: "InventoryInCar",
}


def test_badlands_pruned_mods_are_disabled():
    by_id = {m["id"]: m for m in modstring.load_mods()}
    for mid, name in PRUNED_BADLANDS.items():
        assert by_id[mid]["enabled"] is False, name
        assert "PRUNED 2026-10-15 (Badlands)" in by_id[mid].get("note", ""), name


def test_no_overlay_left_for_pruned_mods():
    import apply_overlays as ov
    names = {f.name for f in ov.OVERLAYS.glob("*.yaml")}
    assert not names & {"zombie_horde.yaml", "spatial_ai.yaml", "expansion_missions.yaml"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_presets.py -k badlands -v`
Expected: FAIL (`enabled` is `True`).

- [ ] **Step 3: Decide HypeTrain from the survey**

```bash
sed -n '/^rail:/,/^$/p' build/survey.nasdara.txt
```
If the `rail:` section lists **0 cells**, HypeTrain (3115714092) is pruned too: add it to `PRUNED_BADLANDS` in the test with the comment `# no rail on Nasdara (map_survey)`. If it lists cells, keep it enabled and note the cell count in `docs/PRUNING.md`.

- [ ] **Step 4: Edit `config/mods.yaml`**

For each pruned entry, set `enabled: false` and put `PRUNED 2026-10-15 (Badlands): <reason>. ` at the start of its `note` (create `note` if it's missing). Use the reasons in the test's comments, or for the stale ones `abandoned since <year>, duplicated by remaining mods`. Example:

```yaml
  - { name: SF Zombie Horde Event, folder: "@SF_ZombieHorde", id: 3689174025, tier: 2, module: world, side: both, enabled: false, verified: true, tested: false, note: "PRUNED 2026-10-15 (Badlands): targets players anywhere and only supports exclusion zones; events must stay in zones (spec §4)." }
```
(Keep each entry's existing `folder`; only `enabled` and `note` change.)

- [ ] **Step 5: Delete the three overlays and log it**

```bash
git rm presets/overlays/zombie_horde.yaml presets/overlays/spatial_ai.yaml presets/overlays/expansion_missions.yaml
```
At the top of `docs/PRUNING.md`, add a dated section listing every pruned mod and its reason, and the "keep if they boot clean" list from spec §3, marked `pending stage-3 boot`.

- [ ] **Step 6: Find loadout and trader items from pruned mods**

```bash
make mod-types >/dev/null 2>&1; .venv/bin/python tools/loadouts.py check
```
Expected: `OK`, or a list of unknown classnames. Replace each unknown classname in `presets/loadouts.yaml` / `presets/traders.yaml` with a vanilla Nasdara item of the same kind (`grep -i <kind> server/mpmissions/<NASDARA>/db/types.xml`), then re-run until it prints OK.

- [ ] **Step 7: Run tests and commit**

Run: `make test` → PASS

```bash
git add config/mods.yaml docs/PRUNING.md presets/ tests/test_presets.py
git commit -m "mods: prune 9-10 mods for Badlands (design + stale/redundant)"
```

---

### Task 6: Pure vanilla economy

**Files:**
- Modify: `tools/economy.py` (rewrite), `presets/economy.yaml` (rewrite), `presets/types_dzds.yaml` (`items: []`), `Makefile` (`economy` target), `tests/test_economy.py` (rewrite)

**Interfaces:**
- Produces: `economy.process(path: Path, cfg: dict, dry_run: bool) -> Counter | None`; `economy.lifetime_overrides(cfg) -> dict[str, int]` and `economy.apply_lifetimes(root, overrides) -> int` (unchanged); `economy.types_files(mission) -> list[Path]` (unchanged).

- [ ] **Step 1: Rewrite the test**

Replace `tests/test_economy.py` with:

```python
"""Loot is Nasdara's vanilla economy (Blae, 2026-10-15). Only arrival-car lifetimes change."""
import subprocess
import sys
import xml.etree.ElementTree as ET

import yaml

import economy

TYPES = """<types>
  <type name="AKM"><nominal>10</nominal><lifetime>1</lifetime><restock>0</restock><min>5</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/><value name="Tier4"/></type>
  <type name="OffroadHatchback"><nominal>0</nominal><lifetime>3</lifetime><restock>1800</restock><min>0</min>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/></type>
</types>"""
DAY = 86400


def cfg():
    return yaml.safe_load(economy.PRESET.read_text())


def test_preset_has_no_phase_or_scaling_keys():
    c = cfg()
    for k in ("phases", "campaign_start", "expected_players", "population_brackets",
              "protected_categories", "war", "hoarding"):
        assert k not in c, k


def mission(tmp_path):
    (tmp_path / "db").mkdir()
    (tmp_path / "snafu").mkdir()
    (tmp_path / "db" / "types.xml").write_text(TYPES)
    (tmp_path / "db" / "globals.xml").write_text('<variables><var name="X" type="0" value="1"/></variables>')
    (tmp_path / "snafu" / "types.xml").write_text(TYPES)
    (tmp_path / "cfgeconomycore.xml").write_text(
        '<economycore><ce folder="snafu"><file name="types.xml" type="types"/></ce></economycore>')
    return tmp_path


def run(m):
    subprocess.run([sys.executable, str(economy.ROOT / "tools" / "economy.py"), "--mission", str(m)],
                   check=True, capture_output=True)


def test_output_equals_vanilla_except_arrival_lifetime(tmp_path):
    m = mission(tmp_path)
    run(m)
    out = {t.get("name"): t for t in ET.parse(m / "db" / "types.xml").getroot().findall("type")}
    assert out["AKM"].find("nominal").text == "10" and out["AKM"].find("min").text == "5"
    assert out["AKM"].find("flags").get("count_in_hoarder") == "0"
    assert int(out["OffroadHatchback"].find("lifetime").text) >= 7 * DAY


def test_rerun_is_identical_and_modded_types_untouched(tmp_path):
    m = mission(tmp_path)
    run(m)
    first = (m / "db" / "types.xml").read_text()
    run(m)
    assert (m / "db" / "types.xml").read_text() == first
    akm = ET.parse(m / "snafu" / "types.xml").getroot().find("type[@name='AKM']")
    assert akm.find("nominal").text == "10"


def test_lifetime_override_touches_only_named_types():
    root = ET.fromstring(TYPES)
    n = economy.apply_lifetimes(root, {"OffroadHatchback": 3888000, "NotInThisFile": 5})
    assert n == 1
    assert root.find("type[@name='AKM']/lifetime").text == "1"


def test_every_arrival_vehicle_gets_a_lifetime_override():
    arrivals = yaml.safe_load((economy.ROOT / "presets" / "arrivals.yaml").read_text())
    over = economy.lifetime_overrides(cfg())
    for v in arrivals["vehicles"]:
        assert over.get(v["class"], 0) >= 7 * DAY, v["class"]


def test_no_vanilla_loot_boosts_in_custom_types():
    t = yaml.safe_load((economy.ROOT / "presets" / "types_dzds.yaml").read_text())
    assert t["items"] == []
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_economy.py -v`
Expected: FAIL (`phases` is in the preset; `types_dzds` items aren't empty).

- [ ] **Step 3: Rewrite `presets/economy.yaml`**

```yaml
# Economy (Blae, 2026-10-15): PURE VANILLA. Nasdara's db/types.xml exactly as Bohemia ships it:
# no campaign phases, no population scaling, no loot-follows-control, no hoarding rule.
# Applied by tools/economy.py (`make economy`), which regenerates types.xml from the pristine
# db/types.xml.vanilla so the result never drifts. Modded types stay at their authors' defaults.

# ---- Lifetime of vehicles our scripts spawn ---------------------------------------------
# Vanilla vehicle classes have <lifetime>3</lifetime>: the CE spawns cars through events, which
# carry their own lifetime. A refugee-arrival car (init.c) gets the 3 s instead, so the CE
# deleted it, cargo and all, as soon as the player walked away (2026-10-12). Applied to every
# vehicle class in presets/arrivals.yaml. 3888000 s = 45 days, vanilla's lifetime for player
# property (tents); the CE refreshes it whenever someone uses the car. This is a fix, not loot.
script_vehicle_lifetime: 3888000

# ---- globals.xml ----------------------------------------------------------------------
# Vanilla values kept. The tool can set any EXISTING <var name="..."> here.
globals: {}
```

- [ ] **Step 4: Rewrite `tools/economy.py`**

```python
#!/usr/bin/env python3
"""Keep the mission's loot economy at vanilla (Blae, 2026-10-15: no phases, no scaling).

Regenerates <mission>/db/types.xml AND every modded types file registered in
cfgeconomycore.xml from pristine baselines (<file>.vanilla, created on first run), changing
only the lifetime of vehicle classes init.c spawns (refugee arrivals), and applies `globals:`
to db/globals.xml. Our own items (the "dzds" folder from tools/types_gen.py) are never touched.

Usage: tools/economy.py [--mission DIR] [--dry-run]
"""
from __future__ import annotations

import argparse
import shutil
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

import yaml

import active

ROOT = active.ROOT
PRESET = ROOT / "presets" / "economy.yaml"
ARRIVALS = ROOT / "presets" / "arrivals.yaml"
SKIP_FOLDERS = {"dzds"}


def lifetime_overrides(cfg: dict) -> dict[str, int]:
    """Type name -> lifetime (s) for vehicles init.c spawns outside the CE's events."""
    life = cfg.get("script_vehicle_lifetime")
    if not life or not ARRIVALS.exists():
        return {}
    vehicles = yaml.safe_load(ARRIVALS.read_text()).get("vehicles") or []
    return {v["class"]: int(life) for v in vehicles}


def apply_lifetimes(root: ET.Element, overrides: dict[str, int]) -> int:
    """Set <lifetime> on the named types present in this file. Returns how many were set."""
    n = 0
    for t in root.findall("type"):
        life = overrides.get(t.get("name"))
        el = t.find("lifetime")
        if life is not None and el is not None:
            el.text = str(life)
            n += 1
    return n


def types_files(mission: Path) -> list[Path]:
    """db/types.xml plus modded types files registered in cfgeconomycore.xml."""
    files = [mission / "db" / "types.xml"]
    core = mission / "cfgeconomycore.xml"
    if core.exists():
        for ce in ET.parse(core).getroot().iter("ce"):
            folder = ce.get("folder", "")
            if folder in SKIP_FOLDERS:
                continue
            for f in ce.findall("file"):
                if f.get("type") == "types":
                    files.append(mission / folder / f.get("name"))
    return files


def process(path: Path, cfg: dict, dry_run: bool) -> Counter | None:
    baseline = path.with_name(path.name + ".vanilla")
    if not path.exists():
        print(f"  (missing {path}; skipped)")
        return None
    if not baseline.exists() and not dry_run:
        shutil.copy2(path, baseline)
        print(f"  saved pristine baseline {baseline.name} (commit it)")
    tree = ET.parse(baseline if baseline.exists() else path)
    stats: Counter = Counter()
    stats["lifetime"] = apply_lifetimes(tree.getroot(), lifetime_overrides(cfg))
    if not dry_run:
        ET.indent(tree, space="    ")
        tree.write(path, encoding="UTF-8", xml_declaration=True)
    return stats


def apply_globals(path: Path, values: dict) -> list[str]:
    """Set existing <var name=... value=...> entries; returns warnings for unknown names."""
    if not values:
        return []
    tree = ET.parse(path)
    found = {v.get("name"): v for v in tree.getroot().iter("var")}
    warnings = []
    for k, v in values.items():
        if k in found:
            found[k].set("value", str(v))
        else:
            warnings.append(f"globals.xml has no var '{k}'; not added")
    tree.write(path, encoding="UTF-8", xml_declaration=True)
    return warnings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mission")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    cfg = yaml.safe_load(PRESET.read_text())
    mission = Path(a.mission) if a.mission else active.mission_dir()
    if not (mission / "db" / "types.xml").exists():
        print(f"{mission / 'db' / 'types.xml'} not found.", file=sys.stderr)
        return 2
    total: Counter = Counter()
    for path in types_files(mission):
        print(f"- {path.relative_to(mission)}")
        stats = process(path, cfg, a.dry_run)
        if stats:
            total.update(stats)
    over = lifetime_overrides(cfg)
    print(f"vanilla economy; script-spawned vehicle lifetime set on {total['lifetime']} type(s) "
          f"for {len(over)} arrival class(es)")
    if total["lifetime"] < len(over):
        print("WARNING: an arrival vehicle is in no types file; the CE will not keep it")
    if a.dry_run:
        print("(dry run, nothing written)")
        return 0
    for w in apply_globals(mission / "db" / "globals.xml", cfg.get("globals") or {}):
        print("WARNING:", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Empty the custom loot boosts and fix Make**

In `presets/types_dzds.yaml`, replace the whole `items:` list with:

```yaml
# Vehicle-part boosts removed 2026-10-15 (Blae: pure vanilla loot). Our own designed items
# go here when there are any.
items: []
```
In `Makefile`, change the `economy` recipe to:

```make
economy:
	$(ENV) $(PY) tools/economy.py
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_economy.py tests/test_presets.py -v`
Expected: PASS. (`types_gen.build` on an empty list returns an empty `<types/>` with no warnings.)

- [ ] **Step 7: Generate the real mission and commit**

```bash
make economy
git add tools/economy.py presets/economy.yaml presets/types_dzds.yaml Makefile tests/test_economy.py server/mpmissions/<NASDARA>/db/
git commit -m "economy: pure vanilla Nasdara loot; phases, scaling and boosts removed"
```

---

## Phase C: Zones

### Task 7: Zone model

**Files:**
- Create: `tools/zones.py`
- Test: `tests/test_zones.py`

**Interfaces:**
- Consumes: map dict keys `locations`, `zone_radius_m`, `zone_radius` (Task 4)
- Produces:
  - `@dataclass(frozen=True) class Zone: name: str; x: float; z: float; radius: float; state: str; holder: str` where `state` is `"stronghold"` or `"warzone"` and `holder` is the faction name, or `"contested"` for a warzone
  - `zones.build(map_data: dict, control: dict[str, str], locs: dict[str, list[float]] | None = None) -> list[Zone]`. `control` maps site → holder (`WarLedger.s.control` shape); `locs` defaults to `map_data["locations"]` and must include claimed sites when given
  - `zones.inside(x: float, z: float, zs: list[Zone], margin: float = 0.0) -> bool`
  - `zones.zone_of(name: str, zs: list[Zone]) -> Zone | None`
  - `zones.control_from_initial(initial: dict[str, list[str]]) -> dict[str, str]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_zones.py
import zones

MAP = {"zone_radius_m": 400, "zone_radius": {"Big Base": 600},
       "locations": {"Big Base": [1000.0, 1000.0], "Well": [5000.0, 5000.0], "Town": [9000.0, 9000.0]}}
CONTROL = {"Big Base": "Peacekeepers", "Well": "contested"}


def test_build_states_and_radii():
    zs = zones.build(MAP, CONTROL)
    base, well = zones.zone_of("Big Base", zs), zones.zone_of("Well", zs)
    assert base.state == "stronghold" and base.holder == "Peacekeepers" and base.radius == 600
    assert well.state == "warzone" and well.radius == 400
    assert zones.zone_of("Town", zs) is None              # uncontrolled = open country


def test_inside_respects_radius_and_margin():
    zs = zones.build(MAP, CONTROL)
    assert zones.inside(1500.0, 1000.0, zs)               # 500 m < 600 m
    assert not zones.inside(5450.0, 5000.0, zs)           # 450 m > 400 m
    assert not zones.inside(1550.0, 1000.0, zs, margin=100.0)


def test_claimed_settlement_is_a_settler_zone():
    """Review focus 3: a player settlement in open country must be a legal zone."""
    locs = dict(MAP["locations"], **{"Host's Homestead": [7000.0, 2000.0]})
    zs = zones.build(MAP, dict(CONTROL, **{"Host's Homestead": "Settlers"}), locs)
    home = zones.zone_of("Host's Homestead", zs)
    assert home.state == "stronghold" and home.holder == "Settlers"
    assert zones.inside(7100.0, 2000.0, zs)


def test_control_from_initial():
    c = zones.control_from_initial({"Rust": ["Well"], "contested": ["Town"]})
    assert c == {"Well": "Rust", "Town": "contested"}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_zones.py -v`
Expected: FAIL, `No module named 'zones'`.

- [ ] **Step 3: Implement `tools/zones.py`**

```python
"""Zones: the only places human NPCs and events may appear (spec §4.1).

A zone is a controlled site plus a radius. Held sites are strongholds; contested sites are
warzones. Everything else on the map is open country, where only the single war party
(gamemaster.ledger) may travel.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Zone:
    name: str
    x: float
    z: float
    radius: float
    state: str      # "stronghold" | "warzone"
    holder: str     # faction name, or "contested"


def control_from_initial(initial: dict[str, list[str]]) -> dict[str, str]:
    return {site: holder for holder, sites in initial.items() for site in sites}


def build(map_data: dict, control: dict[str, str], locs: dict | None = None) -> list[Zone]:
    locs = locs if locs is not None else map_data["locations"]
    default = float(map_data["zone_radius_m"])
    overrides = map_data.get("zone_radius") or {}
    out = []
    for site, holder in sorted(control.items()):
        x, z = locs[site][:2]
        out.append(Zone(site, float(x), float(z), float(overrides.get(site, default)),
                        "warzone" if holder == "contested" else "stronghold", holder))
    return out


def inside(x: float, z: float, zs: list[Zone], margin: float = 0.0) -> bool:
    return any(math.hypot(x - zn.x, z - zn.z) <= zn.radius - margin for zn in zs)


def zone_of(name: str, zs: list[Zone]) -> Zone | None:
    return next((zn for zn in zs if zn.name == name), None)
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_zones.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add tools/zones.py tests/test_zones.py
git commit -m "zones: one zone model (strongholds + warzones) for every generator"
```

---

### Task 8: The war party replaces raids in the ledger

At most one movement per turn (raid, offensive or convoy), with chance 0.35.

**Files:**
- Modify: `src/gamemaster/ledger.py`, `presets/ledger.yaml`, `tools/front_plan.py:52`
- Create: `presets/convoys.yaml`
- Test: `tests/test_ledger.py` (replace the two raid tests), `tests/test_front_plan.py:45`

**Interfaces:**
- Produces: `LedgerState.war_party: dict | None` with keys `kind` (`"raid" | "offensive" | "convoy"`), `faction`, `origin`, `target`, `size: [int, int]`, and for convoys `route: str`. `LedgerState.raids` is **removed**. `WarLedger.war_party_candidates() -> list[dict]`. `WarLedger.convoy_routes: list[dict]`, each `{"from": str, "to": str, "route": str}`.

- [ ] **Step 1: Replace the raid tests**

In `tests/test_ledger.py`, delete `test_hostile_strong_faction_raids_settlement` and `test_no_raids_when_raiders_are_weak_or_friendly`, and append:

```python
def test_at_most_one_war_party_and_only_with_chance():
    led = fresh()
    led.rules["war_party"]["chance"] = 1.0
    led.turn(now=T0)
    assert led.s.war_party is not None
    assert led.s.war_party["kind"] in {"raid", "offensive", "convoy"}
    led.rules["war_party"]["chance"] = 0.0
    led.turn(now=T0 + dt.timedelta(hours=3))
    assert led.s.war_party is None


def test_offensive_heads_for_a_contested_site_the_faction_could_hold():
    led = fresh()
    for c in led.war_party_candidates():
        if c["kind"] == "offensive":
            assert led.s.control[c["target"]] == "contested"
            assert led.s.control[c["origin"]] == c["faction"]


def test_strong_hostile_faction_can_raid_a_settlement():
    led = fresh()
    led.claim("Host's Homestead", [5200.0, 8600.0], ["inland_town"])
    led.s.strength["Jackals"] = 90
    raids = [c for c in led.war_party_candidates() if c["kind"] == "raid"]
    assert raids and all(r["target"] == "Host's Homestead" for r in raids)


def test_no_candidates_when_everyone_is_weak_and_nothing_contested():
    """Review focus 2: an empty turn is quiet, not an error."""
    led = fresh()
    for s in list(led.s.control):
        if led.s.control[s] == "contested":
            led.s.control[s] = "Rust"
    for f in led.s.strength:
        led.s.strength[f] = 0
    led.rules["war_party"]["chance"] = 1.0
    assert led.war_party_candidates() == []
    led.turn(now=T0)
    assert led.s.war_party is None


def test_convoy_only_on_a_recorded_route_between_two_held_sites():
    led = fresh()
    led.convoy_routes = [{"from": "Chernogorsk", "to": "Elektrozavodsk", "route": "rust_coast.json"}]
    convoys = [c for c in led.war_party_candidates() if c["kind"] == "convoy"]
    assert convoys == [{"kind": "convoy", "faction": "Rust", "origin": "Chernogorsk",
                        "target": "Elektrozavodsk", "route": "rust_coast.json", "size": [0, 0]}]
    led.s.control["Elektrozavodsk"] = "Jackals"
    assert not [c for c in led.war_party_candidates() if c["kind"] == "convoy"]
```
In `tests/test_front_plan.py`, replace line 45 (`led.s.raids = [...]`) with:

```python
    led.s.war_party = {"kind": "raid", "faction": "Jackals", "target": "Host's Homestead",
                       "origin": "Gorka", "size": [4, 7]}
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_ledger.py tests/test_front_plan.py -v`
Expected: FAIL (`war_party` / `war_party_candidates` missing).

- [ ] **Step 3: Rules and convoy routes**

In `presets/ledger.yaml`, replace the `raids:` block with:

```yaml
# The war party (spec §4.3): the ONLY thing that moves through open country. Each turn,
# with `chance`, ONE movement is picked from the candidates (raid / offensive / convoy).
war_party:
  chance: 0.35
  min_strength: 40          # a faction needs this much fight left to go on the offensive
  size: [4, 6]

raids:                      # eligibility of the "raid" kind (a hostile faction hits a player settlement)
  min_strength: 55
  max_standing: -20
  size: [4, 7]
```
Create `presets/convoys.yaml`:

```yaml
# Convoy war parties drive ONLY routes recorded in-game with Moving AI Convoy's route recorder
# (Task 19), between two sites one faction holds. Each recorded file is copied into
# presets/convoy_routes/<map>/<route>. Empty until routes are recorded: no convoys until then.
routes:
  nasdara: []
  # - { from: <site>, to: <site>, route: <file>.json }
```

- [ ] **Step 4: Implement in `src/gamemaster/ledger.py`**

In `LedgerState`, replace `raids: list[dict] = field(default_factory=list)` with:

```python
    war_party: dict | None = None                                       # the one movement this restart
```
In `WarLedger.__init__`, after `self.map = ...`, add:

```python
        convoys = ROOT / "presets" / "convoys.yaml"
        self.convoy_routes = ((yaml.safe_load(convoys.read_text()) or {}).get("routes") or {}).get(
            state.map) or [] if convoys.exists() else []
```
In `turn()`, replace `events += self._schedule_raids(rng)` with `events += self._schedule_war_party(rng)`.

Delete `_schedule_raids` and add:

```python
    def war_party_candidates(self) -> list[dict]:
        us = self.rules["players_fight_for"]
        cfg, r = self.rules["war_party"], self.rules["raids"]
        out: list[dict] = []
        for site, holder in sorted(self.s.control.items()):
            if site in self.s.extra_sites and holder == us:
                for f in sorted(self.fspec):
                    if (self.hostile(f, us) and self.s.strength.get(f, 0) >= r["min_strength"]
                            and self.s.standing.get(f, 0) <= r["max_standing"]):
                        origin = self._nearest_held(f, site)
                        if origin:
                            out.append({"kind": "raid", "faction": f, "origin": origin,
                                        "target": site, "size": list(r["size"])})
        for site, holder in sorted(self.s.control.items()):
            if holder != "contested":
                continue
            roles = self.site_roles(site)
            for f, spec in sorted(self.fspec.items()):
                if not roles & set(spec.get("holds_roles", [])):
                    continue
                if self.s.strength.get(f, 0) < cfg["min_strength"]:
                    continue
                origin = self._nearest_held(f, site)
                if origin:
                    out.append({"kind": "offensive", "faction": f, "origin": origin,
                                "target": site, "size": list(cfg["size"])})
        for rt in self.convoy_routes:
            f = self.s.control.get(rt["from"])
            if f in self.fspec and self.s.control.get(rt["to"]) == f:
                out.append({"kind": "convoy", "faction": f, "origin": rt["from"],
                            "target": rt["to"], "route": rt["route"], "size": [0, 0]})
        return out

    def _schedule_war_party(self, rng: random.Random) -> list[str]:
        self.s.war_party = None
        cands = self.war_party_candidates()
        if not cands or rng.random() >= self.rules["war_party"]["chance"]:
            return []
        wp = cands[rng.randrange(len(cands))]
        self.s.war_party = wp
        who = self._display(wp["faction"])
        if wp["kind"] == "raid":
            return [f"Radio intercepts suggest {who} are massing near {wp['origin']} to hit {wp['target']}"]
        if wp["kind"] == "convoy":
            return [f"{who} trucks are moving between {wp['origin']} and {wp['target']}"]
        return [f"{who} are moving out of {wp['origin']} toward {wp['target']}"]
```
Make `load()` refuse a ledger from another map and ignore retired keys (an old file still has `raids`):

```python
    @classmethod
    def load(cls, map_name: str, path: Path = STATE, **kw) -> "WarLedger":
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("map") != map_name:
                raise SystemExit(f"{path} is the {data.get('map')} ledger; run tools/war.py reset for {map_name}")
            known = LedgerState.__dataclass_fields__
            return cls(LedgerState(**{k: v for k, v in data.items() if k in known}), **kw)
        return cls.new(map_name, **kw)
```
and add to `tests/test_ledger.py`:

```python
def test_ledger_from_another_map_is_refused(tmp_path):
    import json
    import pytest
    p = tmp_path / "war_ledger.json"
    p.write_text(json.dumps({"map": "chernarusplus", "raids": []}))
    with pytest.raises(SystemExit, match="reset"):
        WarLedger.load("nasdara", path=p)
    assert WarLedger.load("chernarusplus", path=p).s.war_party is None
```

In `report()`, replace the `for r in self.s.raids:` lines with:

```python
        if self.s.war_party:
            wp = self.s.war_party
            lines.append(f"  War party: {wp['kind']} {wp['faction']} {wp['origin']} -> {wp['target']}")
```

- [ ] **Step 5: `tools/front_plan.py:52`**

Replace `raid_targets = {r["target"] for r in led.s.raids}` with:

```python
    wp = led.s.war_party
    raid_targets = {wp["target"]} if wp and wp["kind"] == "raid" else set()
```

- [ ] **Step 6: Fix `tools/patrol_gen.py` until Task 9 replaces it**

In `main()`, replace the three `led.s.raids` lines with:

```python
    if control is not None and led.s.war_party and led.s.war_party["kind"] in ("raid", "offensive"):
        patrols += war_party_patrols(led.s.war_party, locs, a.interim)
        print(f"+ war party: {led.s.war_party}")
```
and rename `raid_patrols(raids, ...)` to the single-movement form (Task 9 owns its test):

```python
def war_party_patrols(wp: dict | None, locs: dict, interim: bool = False) -> list[dict]:
    """The one open-country patrol (ledger war party); convoys are zone_events' job."""
    if not wp or wp["kind"] not in ("raid", "offensive"):
        return []
    spec = load("presets/factions.yaml")["factions"][wp["faction"]]
    engine = spec["interim_faction"] if interim else spec["custom_faction"]
    tx, tz = locs[wp["target"]][:2]
    ox, oz = locs[wp["origin"]][:2]
    p = dict(BASE)
    p.update(spec.get("behaviour", {}))
    p.update({
        "Name": f"WAR PARTY {wp['faction']} {wp['kind']}: {wp['origin']} -> {wp['target']}",
        "Faction": engine, "Persist": False, "Loadout": f"DZDS_{wp['faction']}",
        "NumberOfAI": int(wp["size"][0]), "NumberOfAIMax": int(wp["size"][1]),
        "Behaviour": "ONCE", "Speed": "JOG", "UnderThreatSpeed": "SPRINT",
        "EnableFlankingOutsideCombat": 1, "Chance": 1.0, "RespawnTime": -1.0,
        "Waypoints": [vec(ox, oz), vec((ox + tx) / 2, (oz + tz) / 2), vec(tx, tz)],
    })
    return [p]
```

- [ ] **Step 7: Run the tests**

Run: `make test`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/gamemaster/ledger.py presets/ledger.yaml presets/convoys.yaml tools/front_plan.py tools/patrol_gen.py tests/test_ledger.py tests/test_front_plan.py
git commit -m "ledger: at most one war party per restart (raid/offensive/convoy) replaces raids"
```

---

### Task 9: Patrols stay inside their zones

**Files:**
- Modify: `tools/patrol_gen.py` (new `perimeter` kind; `route` is rejected), `presets/factions.yaml` (templates)
- Test: `tests/test_nuance.py` (update the route test), `tests/test_presets.py` (append)

**Interfaces:**
- Consumes: `zones.build`, `zones.zone_of` (Task 7); `war_party_patrols` (Task 8)
- Produces: `patrol_gen.PERIMETER_RADIUS = 150.0`; template kinds are `garrison | perimeter | roam | ambush`; `waypoints()` raises `ValueError` for `route`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_presets.py`:

```python
def test_no_open_country_patrol_templates():
    """Spec §4.3: only the ledger's war party crosses open country."""
    for name, spec in load("presets/factions.yaml")["factions"].items():
        for tname, t in (spec.get("patrol_templates") or {}).items():
            assert t["kind"] in {"garrison", "perimeter", "roam", "ambush"}, (name, tname)


def test_generated_patrols_stay_inside_their_zone():
    import patrol_gen
    import zones
    mp = load("maps/nasdara.yaml")
    control = zones.control_from_initial(load("presets/factions.yaml")["initial_control"]["nasdara"])
    zs = zones.build(mp, control)
    for p in patrol_gen.generate("nasdara"):
        site = p["Name"].split(" @ ")[1]
        zn = zones.zone_of(site, zs)
        for x, _, z in p["Waypoints"]:
            assert zones.inside(x, z, [zn]), (p["Name"], x, z)
```
In `tests/test_nuance.py`, replace `test_routes_go_to_another_held_site_and_ranks_get_variant_loadouts` with:

```python
def test_perimeter_loops_the_site_and_ranks_get_variant_loadouts():
    patrols = {p["Name"]: p for p in patrol_gen.generate("chernarusplus")}
    per = patrols["Rust enforcer_patrol @ Chernogorsk"]
    assert len(per["Waypoints"]) == 6
    assert patrols["Karkas elder_marksman @ Altar"]["Loadout"] == "DZDS_Karkas_elder"
    assert patrols["Karkas ridge_watch @ Altar"]["DefaultStance"] == "PRONE"


def test_route_kind_is_rejected():
    import pytest
    with pytest.raises(ValueError, match="route"):
        patrol_gen.waypoints("route", "Gorka", ["Gorka"], LOCS_CH, [0, 0, 15360, 15360])


def test_war_party_patrol_is_single_and_named():
    wp = {"kind": "offensive", "faction": "Rust", "origin": "Chernogorsk",
          "target": "Stary Sobor", "size": [4, 6]}
    ps = patrol_gen.war_party_patrols(wp, LOCS_CH)
    assert len(ps) == 1 and ps[0]["Name"].startswith("WAR PARTY ")
    assert ps[0]["Behaviour"] == "ONCE"
    assert patrol_gen.war_party_patrols({**wp, "kind": "convoy"}, LOCS_CH) == []
    assert patrol_gen.war_party_patrols(None, LOCS_CH) == []
```
And near the top of `tests/test_nuance.py` (after the imports), add:

```python
LOCS_CH = yaml.safe_load((patrol_gen.ROOT / "maps" / "chernarusplus.yaml").read_text())["locations"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_presets.py tests/test_nuance.py -v`
Expected: FAIL (templates still use `route`; no `perimeter` kind).

- [ ] **Step 3: Implement the perimeter kind**

In `tools/patrol_gen.py`, under `GARRISON_RADIUS = 35.0` add `PERIMETER_RADIUS = 150.0`, and replace `waypoints()` with:

```python
def waypoints(kind: str, site: str, sites_of_faction: list[str], locs: dict, bounds) -> list[list[float]]:
    x, z = locs[site][:2]
    if kind in ("garrison", "perimeter"):
        r, n = (GARRISON_RADIUS, 4) if kind == "garrison" else (PERIMETER_RADIUS, 6)
        pts = [clamp(x + r * math.cos(2 * math.pi * i / n), z + r * math.sin(2 * math.pi * i / n), bounds)
               for i in range(n)]
        return [vec(*p) for p in pts]
    if kind in ("roam", "ambush"):
        return [vec(x, z)]
    raise ValueError(f"patrol kind '{kind}' leaves the zone; only the ledger war party may (spec §4.3)")
```

- [ ] **Step 4: Retarget the templates in `presets/factions.yaml`**

| Template | Change |
|---|---|
| Settlers `scavenger_party` | `kind: route` → `kind: perimeter` |
| Peacekeepers `patrol_route` | `kind: route` → `kind: perimeter` |
| Jackals `warband` | **delete** (its role is now the war party) |
| Jackals `ambush` | `at: held` → `at: contested` (ambushes belong to warzone approaches, spec §4.2) |
| Jackals (new) | add `camp_guard: { at: held, kind: garrison, size: [2, 3], chance: 1.0, persist: true, respawn: 2400 }`, so their camp is still defended (`test_every_held_site_is_defended`) |
| Rust `enforcer_patrol` | `kind: route` → `kind: perimeter` |
| Jackals `raid_party`, Karkas `hunting_party` | `roam` stays (single anchor; `ROAMING_LOCAL` keeps them among nearby buildings) |

Above `patrol_templates` in the file's header comment, add:

```yaml
# 2026-10-15 (Badlands): every template stays inside its site's zone (garrison 35 m, perimeter
# 150 m, roam/ambush anchored on the site). Crossing open country is the ledger's war party
# only (presets/ledger.yaml war_party; spec §4.3). `route` is rejected by tools/patrol_gen.py.
```

- [ ] **Step 5: Run the tests**

Run: `make test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tools/patrol_gen.py presets/factions.yaml tests/test_presets.py tests/test_nuance.py
git commit -m "patrols: every template stays inside its zone; war party is the only traveller"
```

---

### Task 10: Zone events generator

Rewrites Airdrop-Upgraded, Animated Helicopters, BS Hacked Crate, AI War Zones and Moving AI Convoy configs so they act only inside zones, with no markers or notifications.

**Files:**
- Create: `tools/zone_events.py`, `presets/zone_events.yaml`, `presets/convoy_routes/nasdara/.gitkeep`
- Modify: `Makefile` (target `zone-events`)
- Test: `tests/test_zone_events.py`

**Interfaces:**
- Consumes: `zones.Zone`, `zones.build` (Task 7); the ledger's `war_party` (Task 8); `map_survey.load_groups`/`ground_y` (Task 3)
- Produces (pure functions; each returns a new object and never mutates its input):
  - `airdrop(settings: dict, zs: list[Zone], cfg: dict, y=lambda x, z: 0.0) -> dict`
  - `heli(settings: dict, zs, cfg, y=...) -> dict`
  - `crates(dynamic: list[dict], zs, cfg, y=...) -> list[dict]`
  - `warzones(settings: dict, zs, ledger_strength: dict[str, float], factions: dict, map_roles: dict[str, set[str]], cfg, y=...) -> dict`
  - `convoy(settings: dict, war_party: dict | None, cfg) -> dict`
  - `convoy_route_files(war_party: dict | None, recorded_dir: Path) -> dict[str, dict]` (filename → route JSON)
  - `positions(kind: str, obj) -> list[tuple[float, float]]`, used by the placement test (Task 12)

- [ ] **Step 1: The preset**

`presets/zone_events.yaml`:

```yaml
# Event mods act ONLY inside zones (spec §4.2). Written by tools/zone_events.py from the zone
# model (tools/zones.py) and the war ledger. Every marker and HUD notification is off (rule 6).
airdrop:
  interval_minutes: 180       # Airdrop-Upgraded Controls.Interval (was 60: one an hour, anywhere)
  variance_minutes: 30
  drop_radius_m: 120          # must stay below every zone radius
  zombies: 6
  stronghold_holders: [Peacekeepers]   # UN strongholds also receive (rarer) drops
heli:
  min_delay_s: 3600
  max_delay_s: 7200
  max_helicopters: 1
crates:
  refresh_s: 3600
  active: 1
  holders: [Peacekeepers]     # military strongholds also host hacked crates
warzones:
  zone_radius_m: 150
  ai_max: 6
  accuracy: [0.28, 0.48]      # inside rule 5 bounds
  spawn_offset_m: 120         # team spawns this far from the centre, opposite sides
  reset_s: 900
convoy:
  min_interval_s: 3600
  max_interval_s: 7200
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_zone_events.py
import copy
import json

import pytest

import zone_events as ze
import zones

CFG = ze.load_cfg()
MAP = {"zone_radius_m": 400, "locations": {"Base": [1000.0, 1000.0], "Well": [5000.0, 5000.0],
                                           "Camp": [9000.0, 2000.0]}}
ZS = zones.build(MAP, {"Base": "Peacekeepers", "Well": "contested", "Camp": "Jackals"})
FACTIONS = {"Peacekeepers": {"custom_faction": "DZDSPeacekeepers", "holds_roles": ["military"],
                             "stance": {"Rust": "hostile", "Jackals": "hostile"}},
            "Rust": {"custom_faction": "DZDSRust", "holds_roles": ["water"],
                     "stance": {"Peacekeepers": "hostile", "Jackals": "hostile"}},
            "Jackals": {"custom_faction": "DZDSJackals", "holds_roles": ["road_junction"],
                        "stance": {"Peacekeepers": "hostile", "Rust": "hostile"}}}
ROLES = {"Base": {"military"}, "Well": {"water"}, "Camp": {"road_junction"}}
STRENGTH = {"Peacekeepers": 60, "Rust": 70, "Jackals": 50}

AIRDROP = {"Controls": {"Interval": 60, "Variance": 5}, "Messages": {"Mode": 3},
           "VPP_Map": {"IsActive": 1, "Is3DActive": 0, "ExportMap": 1},
           "DropZones": [{"Title": "Player Called", "Location": "RANDOM", "DropType": "RANDOM",
                          "X": 0.0, "Z": 0.0, "Zombies": 10, "Radius": 50, "DropAccuracy": 100}]}
HELI = {"Notifications": 1, "Use_Random_Generated_Crash_Sites": 1, "Use_World_Generated_Locations": 1,
        "CRASH_POSITIONS_LIST": ["4000 0 4000"], "Minimum_Delay_In_Seconds_Until_Next_Event": 1200.0,
        "Maximum_Delay_In_Seconds_Until_Next_Event": 2400.0, "Max_Count_Of_Helicopters": 4}
CRATE = {"ConfigUniqueID": "x", "UseExpansionMapMarker": 1, "UseAdvancedGroupsMapMarker": 1,
         "UseBasicMapMarker": 1, "UseVPPMapMarker": 1, "MarkerEnable2D": 1, "MarkerEnable3D": 1,
         "UseCrateNotifications": 1, "ActiveCrateCount": 2, "RefreshInterval": 600,
         "CrateLocations": [{"Position": "4732 338 10350", "Rotation": "0 0 0",
                             "LocationName": "Airfield", "AISpawnPositions": []}]}
WZ = {"maxConcurrentZones": 3, "WarZones": [{"zoneName": "The Battle Of Berezino",
      "zonePosition": "12001.6 54.1 9069.1", "zoneAIMaxAccuracy": 0.9, "zoneAIMinAccuracy": 0.6,
      "zoneShowOnEnter": 1, "zoneShowOnWin": 1, "aTeamFaction": "West", "bTeamFaction": "East"}]}
CONVOY = {"Enabled": 1, "NotifyOnSpawn": 1, "NotifyOnAmbush": 1, "MarkerEnabled": 1, "Marker3D": 1,
          "MaxActiveConvoys": 3, "MinIntervalSeconds": 600, "MaxIntervalSeconds": 600}


def every_inside(pts):
    return all(zones.inside(x, z, ZS) for x, z in pts)


def test_airdrop_drops_only_in_warzones_and_un_strongholds():
    out = ze.airdrop(AIRDROP, ZS, CFG)
    titles = {d["Title"] for d in out["DropZones"]}
    assert titles == {"Well", "Base"}                      # no "Player Called", no Jackal camp
    assert every_inside(ze.positions("airdrop", out))
    assert out["Controls"]["Interval"] == 180
    assert out["VPP_Map"]["IsActive"] == 0 and out["VPP_Map"]["Is3DActive"] == 0
    assert AIRDROP["DropZones"][0]["Title"] == "Player Called"   # input untouched


def test_heli_crashes_only_at_warzones():
    out = ze.heli(HELI, ZS, CFG)
    assert out["Use_Random_Generated_Crash_Sites"] == 0 and out["Use_World_Generated_Locations"] == 0
    assert out["Notifications"] == 0 and out["Max_Count_Of_Helicopters"] == 1
    assert len(out["CRASH_POSITIONS_LIST"]) == 1 and every_inside(ze.positions("heli", out))


def test_crates_no_markers_and_inside_zones():
    out = ze.crates([CRATE], ZS, CFG)
    assert len(out) == 1
    c = out[0]
    for k in ("UseExpansionMapMarker", "UseAdvancedGroupsMapMarker", "UseBasicMapMarker",
              "UseVPPMapMarker", "MarkerEnable2D", "MarkerEnable3D", "UseCrateNotifications"):
        assert c[k] == 0, k
    assert {l["LocationName"] for l in c["CrateLocations"]} == {"Well", "Base"}
    assert every_inside(ze.positions("crates", out))


def test_warzones_one_per_contested_site_with_hostile_dzds_teams():
    out = ze.warzones(WZ, ZS, STRENGTH, FACTIONS, ROLES, CFG)
    assert out["maxConcurrentZones"] == 1
    z = out["WarZones"][0]
    assert z["zoneName"] == "Well" and z["aTeamFaction"] == "DZDSRust"
    assert z["bTeamFaction"] in {"DZDSPeacekeepers", "DZDSJackals"}
    assert 0.25 <= z["zoneAIMinAccuracy"] <= 0.32 and 0.45 <= z["zoneAIMaxAccuracy"] <= 0.52
    assert z["zoneShowOnEnter"] == 0 and z["zoneShowOnWin"] == 0
    assert every_inside(ze.positions("warzones", out))


def test_no_contested_site_means_no_war_zones():
    """Review focus 2. The list is kept (it is the mod's only template) but disabled."""
    zs = zones.build(MAP, {"Base": "Peacekeepers"})
    out = ze.warzones(WZ, zs, STRENGTH, FACTIONS, ROLES, CFG)
    assert out["Enabled"] == 0 and out["maxConcurrentZones"] == 0
    assert ze.positions("warzones", out) == []


def test_convoy_enabled_only_for_a_convoy_war_party(tmp_path):
    off = ze.convoy(CONVOY, None, CFG)
    assert off["Enabled"] == 0 and off["NotifyOnSpawn"] == 0 and off["MarkerEnabled"] == 0
    wp = {"kind": "convoy", "faction": "Rust", "origin": "Well", "target": "Base",
          "route": "rust_run.json", "size": [0, 0]}
    on = ze.convoy(CONVOY, wp, CFG)
    assert on["Enabled"] == 1 and on["MaxActiveConvoys"] == 1
    (tmp_path / "rust_run.json").write_text(json.dumps({"Name": "rust run", "Enabled": 0, "Waypoints": []}))
    files = ze.convoy_route_files(wp, tmp_path)
    assert list(files) == ["rust_run.json"] and files["rust_run.json"]["Enabled"] == 1
    assert ze.convoy_route_files(None, tmp_path) == {}


def test_rerun_is_identical():
    """Review focus 4: prepare-restart twice changes nothing the second time."""
    once = ze.airdrop(AIRDROP, ZS, CFG)
    assert ze.airdrop(copy.deepcopy(once), ZS, CFG) == once
    w1 = ze.warzones(WZ, ZS, STRENGTH, FACTIONS, ROLES, CFG)
    assert ze.warzones(copy.deepcopy(w1), ZS, STRENGTH, FACTIONS, ROLES, CFG) == w1


def test_drop_radius_fits_every_zone():
    assert CFG["airdrop"]["drop_radius_m"] < 400 and CFG["warzones"]["zone_radius_m"] < 400
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_zone_events.py -v`
Expected: FAIL, `No module named 'zone_events'`.

- [ ] **Step 4: Implement `tools/zone_events.py`**

```python
#!/usr/bin/env python3
"""Point every event mod at the zones (spec §4.2) and turn its markers/notifications off.

Reads the zone model (tools/zones.py) from the war ledger (or initial control) and rewrites,
in server/profiles: Airdrop-Upgraded AirdropSettings.json, Animated Dynamic Helicopters
DynamicHelicopterConfig.json, BS Hacked Crate BS_Dynamic_crates.json (+ empties the stock
static crates), AI War Zones AIWarZones_Settings.json, and Moving AI Convoy
AIConvoySettings.json + Routes/. Files that don't exist yet (no boot since a mod change) are
skipped with a note. Idempotent: running it twice gives the same files.

Usage: tools/zone_events.py [--initial] [--dry-run]
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

import yaml

import active
import map_survey
import zones as zmod

ROOT = active.ROOT
PROFILES = ROOT / "server" / "profiles"
FLAT = lambda x, z: 0.0  # noqa: E731


def load_cfg() -> dict:
    return yaml.safe_load((ROOT / "presets" / "zone_events.yaml").read_text())


def _xyz(x: float, z: float, y) -> str:
    return f"{x:.1f} {y(x, z):.1f} {z:.1f}"


def _drop_sites(zs, holders) -> list:
    return [zn for zn in zs if zn.state == "warzone" or zn.holder in holders]


def airdrop(settings: dict, zs, cfg: dict, y=FLAT) -> dict:
    a, out = cfg["airdrop"], copy.deepcopy(settings)
    out["Controls"]["Interval"] = a["interval_minutes"]
    out["Controls"]["Variance"] = a["variance_minutes"]
    out["Messages"]["Mode"] = 0
    out["VPP_Map"].update({"IsActive": 0, "Is3DActive": 0, "ExportMap": 0})
    out["DropZones"] = [{"Title": zn.name, "Location": "Military", "DropType": "RANDOM",
                         "X": round(zn.x, 1), "Z": round(zn.z, 1), "Zombies": a["zombies"],
                         "Radius": a["drop_radius_m"], "DropAccuracy": 100}
                        for zn in _drop_sites(zs, a["stronghold_holders"])]
    return out


def heli(settings: dict, zs, cfg: dict, y=FLAT) -> dict:
    h, out = cfg["heli"], copy.deepcopy(settings)
    out.update({"Notifications": 0, "Use_Random_Generated_Crash_Sites": 0,
                "Use_World_Generated_Locations": 0, "Max_Count_Of_Helicopters": h["max_helicopters"],
                "Minimum_Delay_In_Seconds_Until_Next_Event": float(h["min_delay_s"]),
                "Maximum_Delay_In_Seconds_Until_Next_Event": float(h["max_delay_s"]),
                "CRASH_POSITIONS_LIST": [_xyz(zn.x, zn.z, y) for zn in zs if zn.state == "warzone"]})
    return out


MARKER_KEYS = ("UseExpansionMapMarker", "UseAdvancedGroupsMapMarker", "UseBasicMapMarker",
               "UseVPPMapMarker", "MarkerEnable2D", "MarkerEnable3D", "UseCrateNotifications",
               "EnableMarkerHackingProgress", "EnableMarkerUnlockedStatus")


def crates(dynamic: list[dict], zs, cfg: dict, y=FLAT) -> list[dict]:
    c = cfg["crates"]
    if not dynamic:
        return []
    out = copy.deepcopy(dynamic[:1])
    ev = out[0]
    for k in MARKER_KEYS:
        if k in ev:
            ev[k] = 0
    ev.update({"ActiveCrateCount": c["active"], "RefreshInterval": c["refresh_s"], "StaticSpawns": 0,
               "CrateLocations": [{"Position": _xyz(zn.x, zn.z, y), "Rotation": "0.0 0.0 0.0",
                                   "LocationName": zn.name, "AISpawnPositions": []}
                                  for zn in _drop_sites(zs, c["holders"])]})
    return out


def _teams(site: str, strength: dict, factions: dict, roles: set[str]) -> tuple[str, str] | None:
    fits = sorted((f for f, s in factions.items() if s.get("custom_faction") and roles & set(s.get("holds_roles", []))),
                  key=lambda f: (-strength.get(f, 0), f))
    if not fits:
        return None
    a = fits[0]
    rivals = sorted((f for f, s in factions.items() if s.get("custom_faction") and f != a
                     and factions[a].get("stance", {}).get(f) == "hostile"),
                    key=lambda f: (f not in fits, -strength.get(f, 0), f))
    return (a, rivals[0]) if rivals else None


def _ring(zn, offset: float, start: float, y) -> str:
    pts = [(zn.x + offset * math.cos(start + d), zn.z + offset * math.sin(start + d)) for d in (-0.3, 0.0, 0.3)]
    return ", ".join(_xyz(px, pz, y) for px, pz in pts)


def warzones(settings: dict, zs, strength: dict, factions: dict, roles: dict, cfg: dict, y=FLAT) -> dict:
    w, out = cfg["warzones"], copy.deepcopy(settings)
    template = copy.deepcopy(settings["WarZones"][0]) if settings.get("WarZones") else {}
    made = []
    for zn in zs:
        if zn.state != "warzone":
            continue
        teams = _teams(zn.name, strength, factions, roles.get(zn.name, set()))
        if not teams:
            continue
        a, b = teams
        z = copy.deepcopy(template)
        z.update({"zoneName": zn.name, "zoneChance": 100.0, "zonePosition": _xyz(zn.x, zn.z, y),
                  "zoneRadius": float(w["zone_radius_m"]), "zoneRadiusFX": float(w["zone_radius_m"]) * 0.65,
                  "zoneAIMax": w["ai_max"], "zoneAIMinAccuracy": w["accuracy"][0],
                  "zoneAIMaxAccuracy": w["accuracy"][1], "zoneAIThreatDetectionRange": 300.0,
                  "zoneResetTime": float(w["reset_s"]), "zoneShowOnEnter": 0, "zoneShowOnWin": 0,
                  "zoneEnableAirborneAIAircraft": 0,
                  "aTeamFaction": factions[a]["custom_faction"], "aTeamLoadout": f"DZDS_{a}",
                  "aTeamSpawnPosition": _ring(zn, w["spawn_offset_m"], 0.0, y),
                  "bTeamFaction": factions[b]["custom_faction"], "bTeamLoadout": f"DZDS_{b}",
                  "bTeamSpawnPosition": _ring(zn, w["spawn_offset_m"], math.pi, y)})
        made.append(z)
    if made:
        out["WarZones"] = made
    out["Enabled"] = int(bool(made))
    out["maxConcurrentZones"] = len(made)
    return out


def convoy(settings: dict, war_party: dict | None, cfg: dict) -> dict:
    c, out = cfg["convoy"], copy.deepcopy(settings)
    on = bool(war_party and war_party["kind"] == "convoy")
    out.update({"Enabled": int(on), "NotifyOnSpawn": 0, "NotifyOnAmbush": 0, "MarkerEnabled": 0,
                "Marker3D": 0, "MaxActiveConvoys": 1, "MinIntervalSeconds": c["min_interval_s"],
                "MaxIntervalSeconds": c["max_interval_s"]})
    return out


def convoy_route_files(war_party: dict | None, recorded_dir: Path) -> dict[str, dict]:
    if not war_party or war_party["kind"] != "convoy":
        return {}
    route = json.loads((recorded_dir / war_party["route"]).read_text())
    route["Enabled"] = 1
    return {war_party["route"]: route}


def _split(xyz: str) -> tuple[float, float]:
    p = xyz.replace(",", " ").split()
    return float(p[0]), float(p[2])


def positions(kind: str, obj) -> list[tuple[float, float]]:
    if kind == "airdrop":
        return [(d["X"], d["Z"]) for d in obj["DropZones"]]
    if kind == "heli":
        return [_split(p) for p in obj["CRASH_POSITIONS_LIST"]]
    if kind == "crates":
        return [_split(l["Position"]) for ev in obj for l in ev["CrateLocations"]]
    if kind == "warzones":
        if obj.get("Enabled", 1) == 0:
            return []
        pts = []
        for z in obj["WarZones"]:
            pts.append(_split(z["zonePosition"]))
            for key in ("aTeamSpawnPosition", "bTeamSpawnPosition"):
                pts += [_split(s) for s in z[key].split(", ")]
        return pts
    raise ValueError(kind)


def _rw(path: Path, fn, dry: bool) -> None:
    if not path.exists():
        print(f"  skip {path.relative_to(ROOT)} (not generated yet: boot once with the mod)")
        return
    before = json.loads(path.read_text())
    after = fn(before)
    if after != before and not dry:
        path.write_text(json.dumps(after, indent=4) + "\n")
    print(f"  {'changed' if after != before else 'same   '} {path.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--initial", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, str(ROOT / "src"))
    from gamemaster.ledger import STATE, WarLedger
    cfg, mp = load_cfg(), active.map_data()
    if STATE.exists() and not a.initial:
        led = WarLedger.load(active.map_name())
    else:
        led = WarLedger.new(active.map_name())
    zs = zmod.build(mp, led.s.control, led.locations())
    groups_file = active.mission_dir() / "mapgrouppos.xml"
    groups = map_survey.load_groups(groups_file) if groups_file.exists() else []
    y = (lambda x, z: map_survey.ground_y(groups, x, z)) if groups else FLAT
    roles = {s: led.site_roles(s) for s in led.s.control}
    d = a.dry_run
    _rw(PROFILES / "Airdrop" / "AirdropSettings.json", lambda s: airdrop(s, zs, cfg, y), d)
    _rw(PROFILES / "_DynamicHelicopters" / "DynamicHelicopterConfig.json", lambda s: heli(s, zs, cfg, y), d)
    _rw(PROFILES / "Bastardo_HC" / "BS_Dynamic_crates.json", lambda s: crates(s, zs, cfg, y), d)
    _rw(PROFILES / "Bastardo_HC" / "BS_Static_crates.json", lambda s: [], d)
    _rw(PROFILES / "AIWarZones" / "AIWarZones_Settings.json",
        lambda s: warzones(s, zs, led.s.strength, led.fspec, roles, cfg, y), d)
    _rw(PROFILES / "AIConvoy" / "AIConvoySettings.json", lambda s: convoy(s, led.s.war_party, cfg), d)
    routes_dir = PROFILES / "AIConvoy" / "Routes"
    if routes_dir.exists():
        want = convoy_route_files(led.s.war_party, ROOT / "presets" / "convoy_routes" / active.map_name())
        for f in routes_dir.glob("*.json"):
            if f.name not in want and not d:
                f.unlink()
                print(f"  removed {f.relative_to(ROOT)}")
        for name, body in want.items():
            if not d:
                (routes_dir / name).write_text(json.dumps(body, indent=4) + "\n")
            print(f"  convoy route {name} enabled")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Make target and the routes folder**

```bash
mkdir -p presets/convoy_routes/nasdara && touch presets/convoy_routes/nasdara/.gitkeep
```
```make
.PHONY: zone-events
zone-events:    # event mods act only inside zones (presets/zone_events.yaml)
	$(ENV) $(PY) tools/zone_events.py
```

- [ ] **Step 6: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_zone_events.py -v`
Expected: PASS (8 tests).

- [ ] **Step 7: Commit**

```bash
git add tools/zone_events.py presets/zone_events.yaml presets/convoy_routes tests/test_zone_events.py Makefile
git commit -m "zone_events: airdrops, heli crashes, crates, war zones and convoys only inside zones"
```

---

### Task 11: KAN camps at the Settler settlement

**Files:**
- Modify: `tools/kan_camps.py`, `presets/kan_camps.yaml`
- Test: `tests/test_kan_camps.py` (append)

**Interfaces:**
- Produces: preset camps take an optional `site: <location name>`. `kan_camps.apply(data, preset, locs: dict | None = None) -> list[str]` sets `Position = [x + 15, 0.0, z + 15]` for camps with a `site`, and **removes** camps that aren't in the preset.

- [ ] **Step 1: Write the failing test**

```python
def test_camps_move_to_their_site_and_unlisted_camps_go():
    data = {"Camps": [{"Id": "A", "Position": [1.0, 0.0, 1.0], "RoleOverrides": {}},
                      {"Id": "B", "Position": [2.0, 0.0, 2.0], "RoleOverrides": {}}]}
    roles = {"Roamers": 0, "Looters": 2, "Builders": 1, "Guards": 3, "Attackers": 1, "Snipers": 0}
    preset = {"camps": {"A": {"site": "Settlement", **roles}}}
    changes = kan_camps.apply(data, preset, {"Settlement": [5000.0, 6000.0]})
    assert [c["Id"] for c in data["Camps"]] == ["A"]
    assert data["Camps"][0]["Position"] == [5015.0, 0.0, 6015.0]
    assert any("removed B" in c for c in changes)
```
(Add `import kan_camps` at the top if it's missing.)

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_kan_camps.py -v`
Expected: FAIL (`apply()` takes 2 positional arguments).

- [ ] **Step 3: Implement**

In `tools/kan_camps.py`:
- Change `check()` to ignore the `site` key: `roles = {k: v for k, v in roles.items() if k != "site"}` as its first line.
- Replace `apply()` with:

```python
def apply(data: dict, preset: dict, locs: dict | None = None) -> list[str]:
    camps = {c["Id"]: c for c in data["Camps"]}
    changes = []
    for camp_id in [c for c in camps if c not in preset["camps"]]:
        data["Camps"] = [c for c in data["Camps"] if c["Id"] != camp_id]
        changes.append(f"removed {camp_id} (not in presets/kan_camps.yaml)")
    for camp_id, spec in preset["camps"].items():
        roles = {k: v for k, v in spec.items() if k != "site"}
        check(camp_id, roles)
        if camp_id not in camps:
            raise SystemExit(f"camp {camp_id} not in camps.json (have {sorted(camps)})")
        camp = camps[camp_id]
        want = {r: int(roles[r]) for r in ROLES}
        if camp.get("RoleOverrides") != want:
            changes.append(f"{camp_id}: {camp.get('RoleOverrides')} -> {want}")
            camp["RoleOverrides"] = want
        if spec.get("site") and locs:
            x, z = locs[spec["site"]][:2]
            pos = [float(x) + 15.0, 0.0, float(z) + 15.0]
            if camp.get("Position") != pos:
                changes.append(f"{camp_id}: Position -> {pos} ({spec['site']})")
                camp["Position"] = pos
    return changes
```
- In `main()`, pass the active map's locations: `changes = apply(data, yaml.safe_load(PRESET.read_text()), active.map_data()["locations"])`, and add `import active`.

- [ ] **Step 4: Run the tests and commit**

Run: `.venv/bin/python -m pytest tests/test_kan_camps.py -v` → PASS

```bash
git add tools/kan_camps.py tests/test_kan_camps.py
git commit -m "kan_camps: place camps at a named site; drop camps the preset doesn't list"
```
(`presets/kan_camps.yaml` gets its Nasdara camp Ids and `site:` after the first local boot, in Task 19.)

---

### Task 12: Placement invariant and `prepare-restart` wiring

**Files:**
- Create: `tests/test_zone_placement.py`
- Modify: `Makefile` (`prepare-restart`)

- [ ] **Step 1: Write the test**

```python
# tests/test_zone_placement.py
"""Spec §4.4: every generated NPC/event position is inside a zone, except ONE war party."""
import pytest
import yaml

import active
import patrol_gen
import zone_events as ze
import zones
from gamemaster.ledger import WarLedger

ROOT = active.ROOT
SKEL = {
    "airdrop": {"Controls": {"Interval": 60, "Variance": 5}, "Messages": {"Mode": 3},
                "VPP_Map": {"IsActive": 1, "Is3DActive": 0, "ExportMap": 1}, "DropZones": []},
    "heli": {"CRASH_POSITIONS_LIST": []},
    "crates": [{"CrateLocations": []}],
    "warzones": {"WarZones": [{"zoneName": "x"}], "maxConcurrentZones": 3},
}


def world(turns: int):
    led = WarLedger.new("nasdara")
    led.rules["war_party"]["chance"] = 1.0
    import datetime as dt
    for i in range(turns):
        led.turn(now=dt.datetime(2026, 10, 16) + dt.timedelta(hours=3 * i))
    return led


def test_everything_is_inside_a_zone_except_one_war_party():
    for turns in (0, 1, 5, 12):
        led = world(turns)
        mp = active.map_data("nasdara")
        zs = zones.build(mp, led.s.control, led.locations())
        cfg = ze.load_cfg()
        roles = {s: led.site_roles(s) for s in led.s.control}
        pts = []
        pts += ze.positions("airdrop", ze.airdrop(SKEL["airdrop"], zs, cfg))
        pts += ze.positions("heli", ze.heli(SKEL["heli"], zs, cfg))
        pts += ze.positions("crates", ze.crates(SKEL["crates"], zs, cfg))
        pts += ze.positions("warzones", ze.warzones(SKEL["warzones"], zs, led.s.strength, led.fspec, roles, cfg))
        patrols = patrol_gen.generate("nasdara", control=led.holders(), locs=led.locations())
        for p in patrols:
            pts += [(x, z) for x, _, z in p["Waypoints"]]
        outside = [pt for pt in pts if not zones.inside(*pt, zs)]
        assert outside == [], (turns, outside[:5])
        wp = patrol_gen.war_party_patrols(led.s.war_party, led.locations())
        assert len(wp) <= 1


@pytest.mark.xfail(reason="Nasdara KAN camp Ids exist only after the first local boot (Task 19)", strict=True)
def test_kan_camps_sit_in_settler_zones():
    preset = yaml.safe_load((ROOT / "presets" / "kan_camps.yaml").read_text())
    mp = active.map_data("nasdara")
    control = zones.control_from_initial(yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())
                                         ["initial_control"]["nasdara"])
    zs = [z for z in zones.build(mp, control) if z.holder == "Settlers"]
    for cid, spec in preset["camps"].items():
        x, z = mp["locations"][spec["site"]]
        assert zones.inside(x + 15, z + 15, zs), cid
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/test_zone_placement.py -v`
Expected: the first test PASSES. The KAN test reports XFAIL: Nasdara camp Ids only exist after the first boot. `strict=True` makes it fail loudly once Task 19 fills the preset, which is when the marker is removed.

- [ ] **Step 3: Wire `prepare-restart`**

```make
prepare-restart: war-turn economy diplomacy patrols zone-events vehicle-events front-plan loadouts dzds-profile arrivals overlays calibrate validate
```

- [ ] **Step 4: Run all tests and commit**

Run: `make test` → PASS (one expected xfail)

```bash
git add tests/test_zone_placement.py Makefile
git commit -m "test: placement invariant across every generator; zone-events in prepare-restart"
```

---

### Task 13: Encounter audit

**Files:**
- Create: `tools/encounter_audit.py`
- Modify: `Makefile` (target `encounter-audit`)
- Test: `tests/test_encounter_audit.py`

**Interfaces:**
- Consumes: `gamemaster.adm.parse_line`; `zones.build`
- Produces: `encounter_audit.audit(lines: list[str], zs: list[Zone], window_s: int = 300) -> dict[str, dict]` → `{player: {"sessions": int, "outside": int, "inside": int}}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_encounter_audit.py
import encounter_audit as ea
import zones

ZS = zones.build({"zone_radius_m": 400, "locations": {"Base": [1000.0, 1000.0]}}, {"Base": "Rust"})
LINES = [
    '10:00:00 | Player "Host" (id=a=) is connected',
    '10:05:00 | Player "Host" (id=a= pos=<5000.0, 10.0, 5000.0>)[HP: 80] hit by AI "J1" (group=1:"x" faction="DZDSJackals") into Torso',
    '10:06:00 | Player "Host" (id=a= pos=<5001.0, 10.0, 5001.0>)[HP: 60] hit by AI "J1" (group=1:"x" faction="DZDSJackals") into Torso',
    '10:30:00 | Player "Host" (id=a= pos=<1100.0, 10.0, 1000.0>)[HP: 70] hit by AI "R1" (group=2:"y" faction="DZDSRust") into Torso',
    '11:00:00 | Player "Host" (id=a=) has been disconnected',
    '12:00:00 | Player "Host" (id=a=) is connected',
]


def test_counts_sessions_and_groups_hits_into_encounters():
    out = ea.audit(LINES, ZS)
    assert out["Host"] == {"sessions": 2, "outside": 1, "inside": 1}


def test_ai_vs_ai_is_not_a_player_encounter():
    line = ('10:05:00 | AI "J1" (group=1:"x" faction="DZDSJackals" pos=<5000.0, 10.0, 5000.0>)'
            '[HP: 50] hit by AI "R1" (group=2:"y" faction="DZDSRust")')
    assert ea.audit([line], ZS) == {}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_encounter_audit.py -v`
Expected: FAIL, `No module named 'encounter_audit'`.

- [ ] **Step 3: Implement `tools/encounter_audit.py`**

```python
#!/usr/bin/env python3
"""How often players meet human AI OUTSIDE the zones (spec §4.4 target: <= 1 per player per ~3 sessions).

An encounter = a player hit by AI, or a player hitting/killing AI, grouped per player into
windows of `--window` seconds. Sessions = 'is connected' lines. Zones come from the current
war ledger (or initial control).

Usage: tools/encounter_audit.py [ADM files...]   (default: server/profiles/*.ADM)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import active
import zones as zmod

sys.path.insert(0, str(active.ROOT / "src"))
from gamemaster.adm import parse_line  # noqa: E402


def _secs(t: str) -> int:
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def audit(lines: list[str], zs, window_s: int = 300) -> dict[str, dict]:
    out: dict[str, dict] = {}
    last: dict[tuple[str, bool], int] = {}
    for line in lines:
        ev = parse_line(line)
        if not ev:
            continue
        if ev.kind == "connect" and not ev.is_ai:
            out.setdefault(ev.player, {"sessions": 0, "outside": 0, "inside": 0})["sessions"] += 1
            continue
        if ev.kind not in ("hit", "death") or not ev.pos:
            continue
        if not ev.is_ai and ev.by_is_ai:
            player = ev.player
        elif ev.is_ai and ev.by and ev.by.startswith('Player "'):
            player = ev.by.split('"')[1]
        else:
            continue
        where = zmod.inside(ev.pos[0], ev.pos[1], zs)
        rec = out.setdefault(player, {"sessions": 0, "outside": 0, "inside": 0})
        t = _secs(ev.time)
        key = (player, where)
        if key not in last or t - last[key] > window_s or t < last[key]:
            rec["inside" if where else "outside"] += 1
        last[key] = t
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--window", type=int, default=300)
    a = ap.parse_args()
    files = [Path(f) for f in a.files] or sorted((active.ROOT / "server" / "profiles").glob("*.ADM"))
    from gamemaster.ledger import STATE, WarLedger
    led = WarLedger.load(active.map_name()) if STATE.exists() else WarLedger.new(active.map_name())
    zs = zmod.build(active.map_data(), led.s.control, led.locations())
    lines = [ln for f in files for ln in f.read_text(errors="replace").splitlines()]
    res = audit(lines, zs, a.window)
    print(f"{len(files)} ADM file(s); target <= 0.33 outside encounters per session")
    worst = 0.0
    for p, r in sorted(res.items()):
        rate = r["outside"] / max(1, r["sessions"])
        worst = max(worst, rate)
        print(f"  {p:<24} sessions {r['sessions']:>3}  outside {r['outside']:>3}  inside {r['inside']:>3}  "
              f"rate {rate:.2f} {'OVER' if rate > 1 / 3 else 'ok'}")
    return 1 if worst > 1 / 3 else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Make target, tests, commit**

```make
.PHONY: encounter-audit
encounter-audit: # AI encounters outside zones per player-session (target <= 1 per 3)
	$(ENV) $(PY) tools/encounter_audit.py
```
Run: `.venv/bin/python -m pytest tests/test_encounter_audit.py -v` → PASS

```bash
git add tools/encounter_audit.py tests/test_encounter_audit.py Makefile
git commit -m "encounter-audit: AI encounters outside zones per player-session from the ADM"
```

---

## Phase D: Arrivals

All Enforce changes go into `server/mpmissions/<NASDARA>/init.c`. Python tests cover the compiled JSON and the static contract with `init.c`. Behaviour in-game is checked in Task 19.

### Task 14: Port `init.c` to Nasdara

**Files:**
- Modify: `server/mpmissions/<NASDARA>/init.c`
- Modify: `tests/test_arrivals.py` (`INIT_C` and the fixture use the active map)

- [ ] **Step 1: Point the arrival tests at the active mission**

At the top of `tests/test_arrivals.py`, replace the `INIT_C` line and the fixture's map file:

```python
import active

INIT_C = active.mission_dir("nasdara") / "init.c"


@pytest.fixture(scope="module")
def built():
    cfg = yaml.safe_load(arrivals.PRESET.read_text())
    map_data = active.map_data("nasdara")
    return cfg, map_data, arrivals.build(cfg, map_data, arrivals.mission_dir(map_data))
```
In `test_arrival_sites_stay_out_of_war_locations`, read `active.map_data("nasdara")`. Add:

```python
def test_init_main_is_vanilla():
    """Our block must not change Bohemia's main() (economy init, date reset)."""
    ours, vanilla = INIT_C.read_text(), (INIT_C.parent / "init.c.vanilla").read_text()
    grab = lambda s: re.search(r"void main\(\)\s*\{.*?\n\}", s, re.S).group(0)  # noqa: E731
    assert grab(ours) == grab(vanilla)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_arrivals.py -v`
Expected: FAIL (`class RefugeeArrivalConfig` isn't in the vanilla Nasdara `init.c`).

- [ ] **Step 3: Port**

Write `server/mpmissions/<NASDARA>/init.c` as:
1. the vanilla Nasdara `void main() { ... }` copied **verbatim** from `init.c.vanilla`;
2. the whole block from `server/mpmissions/dayzOffline.chernarusplus/init.c` from the `// ====` header line before `class RefugeeArrivalPoint` through the end of `class RefugeeArrivals`;
3. `class CustomMission: MissionServer` from the Chernarus file, **except** that the body of `StartingEquipSetup` is replaced by the vanilla Nasdara `StartingEquipSetup` body from `init.c.vanilla`;
4. the `Mission CreateCustomMission(string path)` function from `init.c.vanilla`.

- [ ] **Step 4: Nasdara exclusions in `presets/arrivals.yaml`**

`exclude_points` holds a Chernarus coordinate (Gorka). Replace it with a role:

```yaml
exclude_roles: [airfield, military, road_junction]   # no respawns beside UN bases or the Jackal camp
exclude_radius_m: 500
exclude_points: []              # extra no-respawn zones [x, z, radius]
```

- [ ] **Step 5: Run the tests and commit**

Run: `.venv/bin/python -m pytest tests/test_arrivals.py -v` → PASS

```bash
git add presets/arrivals.yaml server/mpmissions/<NASDARA>/init.c tests/test_arrivals.py
git commit -m "mission: port refugee arrivals to the Nasdara init.c (vanilla main kept)"
```

---

### Task 15: Start kit (radio + flare) and voice quality

**Files:**
- Modify: `presets/arrivals.yaml`, `tools/arrivals.py`, `server/mpmissions/<NASDARA>/init.c`, `config/local_serverDZ.cfg`
- Test: `tests/test_arrivals.py` (append)

**Interfaces:**
- Produces: arrivals JSON keys `RadioFrequencyIndex: int`, `GiveRoadflare: int`. `init.c`: `static void RefugeeArrivals.GiveStartKit(PlayerBase player, int radioIndex, bool flare)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_start_kit_is_compiled(built):
    cfg, _, out = built
    assert out["RadioFrequencyIndex"] == cfg["radio"]["settler_net_index"] >= 0
    assert out["GiveRoadflare"] == 1


def test_init_c_gives_radio_battery_and_flare():
    src = INIT_C.read_text()
    kit = re.search(r"static void GiveStartKit\(.*?\n\t\}", src, re.S).group(0)
    for needle in ('"PersonalRadio"', '"Battery9V"', "SetFrequencyByIndex", '"Roadflare"'):
        assert needle in kit, needle
    assert "SwitchOn" not in kit                       # ships switched OFF (spec §6.1)
    setup = re.search(r"override void StartingEquipSetup\(.*?\n\t\}", src, re.S).group(0)
    assert "GiveStartKit" in setup


def test_voice_quality_max():
    cfg = (arrivals.ROOT / "config" / "local_serverDZ.cfg").read_text()
    assert re.search(r"^vonCodecQuality\s*=\s*30;", cfg, re.M)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_arrivals.py -v`
Expected: FAIL (`KeyError: 'radio'`).

- [ ] **Step 3: Preset and compiler**

Append to `presets/arrivals.yaml`:

```yaml
# Body kit (Blae, 2026-10-15): every new character also gets a PersonalRadio with a 9V battery,
# tuned to the Settler net and switched OFF, plus one road flare. Index 0 = the first channel
# in vanilla's list; the MHz value is read in-game (Task 19) and printed on the player page.
radio:
  settler_net_index: 0
give_roadflare: true
```
In `tools/arrivals.py` `build()`, add to the returned dict:

```python
        "RadioFrequencyIndex": int(cfg["radio"]["settler_net_index"]),
        "GiveRoadflare": int(bool(cfg["give_roadflare"])),
```

- [ ] **Step 4: Enforce**

In `init.c`, add to `class RefugeeArrivalConfig`:

```c
	int RadioFrequencyIndex;
	int GiveRoadflare;
```
Add to `class RefugeeArrivals` (after `IsActive()`):

```c
	// Every new character: a radio with a battery, tuned to the Settler net, switched off
	// (vanilla items spawn off), plus one road flare (Blae, 2026-10-15).
	static void GiveStartKit(PlayerBase player, int radioIndex, bool flare)
	{
		EntityAI radio = player.GetInventory().CreateInInventory("PersonalRadio");
		if (radio)
		{
			radio.GetInventory().CreateAttachment("Battery9V");
			TransmitterBase tx = TransmitterBase.Cast(radio);
			if (tx)
				tx.SetFrequencyByIndex(radioIndex);
		}
		if (flare)
			player.GetInventory().CreateInInventory("Roadflare");
	}

	int RadioIndex()
	{
		if (!m_Config)
			return 0;
		return m_Config.RadioFrequencyIndex;
	}

	bool Roadflare()
	{
		if (!m_Config)
			return true;
		return m_Config.GiveRoadflare == 1;
	}
```
In `CustomMission.StartingEquipSetup`, append as the **last statement** of the method:

```c
		if (!m_RefugeeArrivals)
			m_RefugeeArrivals = new RefugeeArrivals();
		RefugeeArrivals.GiveStartKit(player, m_RefugeeArrivals.RadioIndex(), m_RefugeeArrivals.Roadflare());
```

- [ ] **Step 5: Voice quality**

In `config/local_serverDZ.cfg`: `vonCodecQuality = 30;`. Record for Task 21 that the panel needs the same value.

- [ ] **Step 6: Run the tests and commit**

Run: `make arrivals && .venv/bin/python -m pytest tests/test_arrivals.py -v` → PASS

```bash
git add presets/arrivals.yaml tools/arrivals.py server/mpmissions/<NASDARA>/init.c config/local_serverDZ.cfg tests/test_arrivals.py server/profiles/DZDS/arrivals.json
git commit -m "arrivals: pre-tuned radio + road flare for every new character; VON quality 30"
```

---

### Task 16: The refugee column

Everyone whose first arrival falls on the same real-world day wakes at the same arrival site, and the site rotates daily. The day starts at 11:00 UTC (≈ 06:00 Central), so a single evening session never straddles two days.

**Files:**
- Modify: `presets/arrivals.yaml`, `tools/arrivals.py`, `server/mpmissions/<NASDARA>/init.c`
- Test: `tests/test_arrivals.py` (append)

**Interfaces:**
- Produces: arrivals JSON `ColumnSites: [str]` (site names, rotation order) and `ColumnDayStartUtcHour: int`. `init.c`: `string RefugeeArrivals.ColumnSiteFor(int offset)` and `bool PickColumnPoint(RefugeeArrivalPlan plan)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_column_rotation_covers_every_site_with_room(built):
    """Review focus 1: every site in the rotation has >= 8 roadside spots."""
    cfg, map_data, out = built
    assert sorted(out["ColumnSites"]) == sorted(map_data["arrival_sites"])
    assert cfg["points_per_site"] >= 8
    for site in out["ColumnSites"]:
        assert sum(p["Name"] == site for p in out["ArrivalSites"]) >= 8, site
    assert 0 <= out["ColumnDayStartUtcHour"] <= 23


def test_init_c_column_spills_to_the_next_site():
    src = INIT_C.read_text()
    pick = re.search(r"bool PickColumnPoint\(.*?\n\t\}", src, re.S).group(0)
    assert "ColumnSiteFor(" in pick and "for (" in pick      # tries following sites in order
    plan = re.search(r"RefugeeArrivalPlan Plan\(.*?\n\t\}", src, re.S).group(0)
    assert "PickColumnPoint(plan)" in plan
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_arrivals.py -k column -v`
Expected: FAIL (`KeyError: 'ColumnSites'`).

- [ ] **Step 3: Preset and compiler**

In `presets/arrivals.yaml`: set `points_per_site: 8` and add:

```yaml
# Refugee column (Blae, 2026-10-15): all FIRST arrivals on the same day wake at the same
# arrival site; the site rotates daily in this order. A "day" starts at this UTC hour
# (11 = 06:00 US Central) so one evening's session never splits across two sites.
column_day_start_utc_hour: 11
```
In `tools/arrivals.py` `build()`, add:

```python
        "ColumnSites": list((map_data.get("arrival_sites") or {}).keys()),
        "ColumnDayStartUtcHour": int(cfg["column_day_start_utc_hour"]),
```

- [ ] **Step 4: Enforce**

Add to `RefugeeArrivalConfig`:

```c
	ref TStringArray ColumnSites;
	int ColumnDayStartUtcHour;
```
Add to `RefugeeArrivals`:

```c
	// The site for today's column, or `offset` sites further along the rotation.
	string ColumnSiteFor(int offset)
	{
		if (!m_Config.ColumnSites || m_Config.ColumnSites.Count() == 0)
			return "";
		int day = (NowSeconds() - m_Config.ColumnDayStartUtcHour * 3600) / 86400;
		int n = m_Config.ColumnSites.Count();
		return m_Config.ColumnSites[(day + offset) % n];
	}

	// Today's site first; if every spot there is taken, the next site in the rotation.
	bool PickColumnPoint(RefugeeArrivalPlan plan)
	{
		if (!m_Config.ColumnSites)
			return false;
		for (int o = 0; o < m_Config.ColumnSites.Count(); o++)
		{
			string site = ColumnSiteFor(o);
			array<ref RefugeeArrivalPoint> pts = new array<ref RefugeeArrivalPoint>;
			foreach (RefugeeArrivalPoint p : m_Config.ArrivalSites)
			{
				if (p.Name == site)
					pts.Insert(p);
			}
			if (PickPoint(pts, plan))
				return true;
		}
		return false;
	}
```
In `Plan()`, replace:

```c
		if (plan.FirstArrival)
			placed = PickPoint(m_Config.ArrivalSites, plan);
```
with:

```c
		if (plan.FirstArrival)
			placed = PickColumnPoint(plan);
```

- [ ] **Step 5: Run the tests and commit**

Run: `make arrivals && .venv/bin/python -m pytest tests/test_arrivals.py -v` → PASS

```bash
git add presets/arrivals.yaml tools/arrivals.py server/mpmissions/<NASDARA>/init.c tests/test_arrivals.py server/profiles/DZDS/arrivals.json
git commit -m "arrivals: same-day refugee column at one rotating site, spilling to the next"
```

---

### Task 17: Respawn near where you died

**Files:**
- Modify: `presets/arrivals.yaml`, `tools/arrivals.py`, `server/mpmissions/<NASDARA>/init.c`
- Test: `tests/test_arrivals.py` (append)

**Interfaces:**
- Produces: arrivals JSON `RespawnNearMin: float`, `RespawnNearMax: float`, `RespawnNearFallback: float`. Ledger record fields `float DeathX; float DeathZ; int HasDeath;`. `init.c`: `void RefugeeArrivals.RecordDeath(string uid, vector pos)` and `bool PickNearDeath(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_respawn_ring_is_compiled(built):
    _, _, out = built
    assert (out["RespawnNearMin"], out["RespawnNearMax"], out["RespawnNearFallback"]) == (2000.0, 5000.0, 8000.0)


def test_init_c_records_death_on_respawn_and_on_disconnect():
    src = INIT_C.read_text()
    assert re.search(r"override void OnClientRespawnEvent\(PlayerIdentity identity, PlayerBase player\)", src)
    assert re.search(r"override void PlayerDisconnected\(PlayerBase player, PlayerIdentity identity, string uid\)", src)
    assert src.count("RecordDeath(") >= 3                    # definition + two hooks
    rec = re.search(r"class RefugeeArrivalRecord\s*\{(.*?)\n\}", src, re.S).group(1)
    for f in ("DeathX", "DeathZ", "HasDeath"):
        assert f in rec


def test_init_c_respawn_tries_ring_then_fallback_then_anywhere():
    src = INIT_C.read_text()
    plan = re.search(r"RefugeeArrivalPlan Plan\(.*?\n\t\}", src, re.S).group(0)
    assert plan.index("PickNearDeath(") < plan.index("PickPoint(m_Config.RoadPoints")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_arrivals.py -k "respawn or death" -v`
Expected: FAIL.

- [ ] **Step 3: Preset and compiler**

`presets/arrivals.yaml`:

```yaml
# Respawn near where you died (Blae, 2026-10-15): a later character wakes on a road point
# 2-5 km from the previous character's death, else within 8 km, else anywhere (exclusions
# still apply). No recorded death (e.g. the server restarted mid-death) = anywhere, as before.
respawn_near_m: [2000, 5000]
respawn_near_fallback_m: 8000
```
`tools/arrivals.py` `build()`:

```python
        "RespawnNearMin": float(cfg["respawn_near_m"][0]),
        "RespawnNearMax": float(cfg["respawn_near_m"][1]),
        "RespawnNearFallback": float(cfg["respawn_near_fallback_m"]),
```

- [ ] **Step 4: Enforce**

`RefugeeArrivalConfig` gets `float RespawnNearMin; float RespawnNearMax; float RespawnNearFallback;`, and `RefugeeArrivalRecord` gets `float DeathX; float DeathZ; int HasDeath;`.

Add to `RefugeeArrivals`:

```c
	void RecordDeath(string uid, vector pos)
	{
		if (!IsActive())
			return;
		RefugeeArrivalRecord rec = FindRecord(uid);
		if (!rec)
			return;
		rec.DeathX = pos[0];
		rec.DeathZ = pos[2];
		rec.HasDeath = 1;
		MakeDirectory(DIR);
		JsonFileLoader<RefugeeArrivalLedger>.JsonSaveFile(LEDGER, m_Ledger);
	}

	// Road points between lo and hi metres from the last death.
	array<ref RefugeeArrivalPoint> RingPoints(RefugeeArrivalRecord rec, float lo, float hi)
	{
		array<ref RefugeeArrivalPoint> out = new array<ref RefugeeArrivalPoint>;
		foreach (RefugeeArrivalPoint p : m_Config.RoadPoints)
		{
			float dx = p.X - rec.DeathX;
			float dz = p.Z - rec.DeathZ;
			float d = Math.Sqrt(dx * dx + dz * dz);
			if (d >= lo && d <= hi)
				out.Insert(p);
		}
		return out;
	}

	bool PickNearDeath(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec)
	{
		if (!rec || rec.HasDeath != 1)
			return false;
		if (PickPoint(RingPoints(rec, m_Config.RespawnNearMin, m_Config.RespawnNearMax), plan))
			return true;
		return PickPoint(RingPoints(rec, 1000, m_Config.RespawnNearFallback), plan);
	}
```
In `Plan()`, replace:

```c
		if (!placed)
			placed = PickPoint(m_Config.RoadPoints, plan);
```
(the first occurrence, right after the first-arrival line) with:

```c
		if (!placed && !plan.FirstArrival)
			placed = PickNearDeath(plan, rec);
		if (!placed)
			placed = PickPoint(m_Config.RoadPoints, plan);
```
In `Deliver()`, after `rec.Lives++;` add `rec.HasDeath = 0;` (a new life starts with no recorded death).

Add to `CustomMission`:

```c
	override void OnClientRespawnEvent(PlayerIdentity identity, PlayerBase player)
	{
		if (m_RefugeeArrivals && identity && player)
			m_RefugeeArrivals.RecordDeath(identity.GetId(), player.GetPosition());
		super.OnClientRespawnEvent(identity, player);
	}

	override void PlayerDisconnected(PlayerBase player, PlayerIdentity identity, string uid)
	{
		if (m_RefugeeArrivals && player && !player.IsAlive())
			m_RefugeeArrivals.RecordDeath(uid, player.GetPosition());
		super.PlayerDisconnected(player, identity, uid);
	}
```

- [ ] **Step 5: Run the tests and commit**

Run: `make arrivals && .venv/bin/python -m pytest tests/test_arrivals.py -v` → PASS

```bash
git add presets/arrivals.yaml tools/arrivals.py server/mpmissions/<NASDARA>/init.c tests/test_arrivals.py server/profiles/DZDS/arrivals.json
git commit -m "arrivals: respawn 2-5 km from the last death (8 km fallback, then anywhere)"
```

---

### Task 18: Archetype cargo with a themed firearm

**Files:**
- Modify: `presets/arrivals.yaml` (`gear:` → `archetypes:`), `tools/arrivals.py`, `server/mpmissions/<NASDARA>/init.c` (`FillCargo`)
- Test: `tests/test_arrivals.py` (replace the gear tests; append)

**Interfaces:**
- Produces: arrivals JSON `Archetypes: [ {Name, Weight, Slots: [{Name, Min, Max, MaxEach, Items: [str]}], Firearms: [{Weapon, Magazine, Ammo, RoundsMin, RoundsMax}]} ]`, `FirearmHealthMin`, `FirearmHealthMax`. The `Gear` key is **removed**. Python: `arrivals.simulate_kit(arch: dict, rng: random.Random) -> list[str]`, which mirrors `init.c` exactly.

- [ ] **Step 1: Write the failing tests**

In `tests/test_arrivals.py`, delete `test_unknown_classname_is_rejected` and `test_gear_weights_keep_category_shares`, then append:

```python
import random
import xml.etree.ElementTree as ET


def test_unknown_classname_is_rejected(built):
    cfg, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    bad["archetypes"]["deserter"]["slots"]["food"]["items"].append("NotARealItem")
    with pytest.raises(SystemExit, match="NotARealItem"):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_archetype_weights(built):
    _, _, out = built
    assert {a["Name"]: a["Weight"] for a in out["Archetypes"]} == \
        {"deserter": 30.0, "trucker": 25.0, "nomad": 25.0, "townie": 20.0}


def test_simulated_kits_meet_the_spec(built):
    _, _, out = built
    rng = random.Random(7)
    for arch in out["Archetypes"]:
        food = set(next(s for s in arch["Slots"] if s["Name"] == "food")["Items"])
        camp = set(next(s for s in arch["Slots"] if s["Name"] == "camp")["Items"])
        weapons = {f["Weapon"] for f in arch["Firearms"]}
        for _ in range(1000):
            kit = arrivals.simulate_kit(arch, rng)
            items = [k for k in kit if k not in weapons and not k.startswith(("Ammo_", "Mag_"))]
            assert 10 <= len(items) <= 16, (arch["Name"], kit)
            for name in set(items):
                cap = 2 if name in food else 1
                assert items.count(name) <= cap, (arch["Name"], name)
            assert sum(k in weapons for k in kit) == 1
            assert sum(k in camp for k in kit) <= 1


def test_firearms_without_magazine_get_loose_rounds(built):
    """Review focus 5."""
    _, map_data, out = built
    spawn = ET.parse(arrivals.mission_dir(map_data) / "cfgspawnabletypes.xml").getroot()
    for arch in out["Archetypes"]:
        for f in arch["Firearms"]:
            assert f["Ammo"], f
            assert 1 <= f["RoundsMin"] <= f["RoundsMax"] <= 8, f
            if f["Magazine"]:
                assert f["RoundsMax"] <= 5, f
                t = spawn.find(f"type[@name='{f['Weapon']}']")
                if t is not None:
                    mags = {i.get("name") for i in t.iter("item")}
                    assert f["Magazine"] in mags, f


def test_init_c_fill_cargo_uses_archetypes():
    src = INIT_C.read_text()
    fill = re.search(r"int FillCargo\(CarScript car\).*?\n\t\}", src, re.S).group(0)
    for needle in ("PickArchetype()", "SpawnAttachedMagazine(", "WeaponWithAmmoFlags.NONE",
                   "ServerSetAmmoCount("):
        assert needle in src, needle
    assert "PickGear()" not in src
    assert "FillSlot(" in fill and "GiveFirearm(" in fill
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_arrivals.py -v`
Expected: FAIL (`KeyError: 'archetypes'`).

- [ ] **Step 3: Replace `gear:` in `presets/arrivals.yaml`**

Delete the `gear:` block and add the following. Every classname was checked against Nasdara's `db/types.xml` on 2026-10-15; the compiler re-checks them on every build.

```yaml
# Arrival cargo (Blae, 2026-10-15): ONE archetype per car, slots drawn WITHOUT replacement
# (max_each 1, food 2), ~10-16 items + exactly one themed firearm with meagre ammo:
# a partly filled magazine (2-5) OR 3-8 loose rounds, never a spare magazine.
firearm_health: [0.45, 0.70]
archetypes:
  deserter:
    weight: 30
    slots:
      clothing: { count: [2, 3], items: [USMCJacket_Desert, USMCPants_Desert, BoonieHat_Desert, MilitaryBoots_Beige, M65Jacket_Tan, CargoPants_Beige, AssaultBag_Desert, Keffiyeh_LightBrown] }
      water:    { count: [1, 2], items: [Canteen, WaterBottle] }
      food:     { count: [2, 3], max_each: 2, items: [TunaCan, SardinesCan, BakedBeansCan, Crackers] }
      medical:  { count: [2, 2], items: [BandageDressing, PainkillerTablets, CharcoalTablets, TetracyclineAntibiotics] }
      tools:    { count: [2, 3], items: [CombatKnife, Compass, Matchbox, DuctTape, Binoculars] }
      extra:    { count: [1, 2], items: [Flashlight, Battery9V, Rope] }
      camp:     { count: [0, 1], items: [PortableGasStove, Pot] }
    firearms:
      - { weapon: MakarovIJ70, magazine: Mag_IJ70_8Rnd, ammo: Ammo_380, rounds: [2, 5] }
      - { weapon: CZ75, magazine: Mag_CZ75_15Rnd, ammo: Ammo_9x19, rounds: [2, 5] }
      - { weapon: SKS, magazine: null, ammo: Ammo_762x39, rounds: [3, 8] }
  trucker:
    weight: 25
    slots:
      clothing: { count: [2, 3], items: [WorkingBoots_Brown, CargoPants_Green, Hoodie_Grey, WorkingGloves_Brown, TaloonBag_Blue, BeanieHat_Grey] }
      water:    { count: [1, 2], items: [WaterBottle, Canteen] }
      food:     { count: [2, 3], max_each: 2, items: [BakedBeansCan, Crackers, Rice, BrisketSpread] }
      medical:  { count: [2, 2], items: [BandageDressing, Rag, PainkillerTablets] }
      tools:    { count: [2, 3], items: [Wrench, Screwdriver, Pliers, KitchenKnife, DuctTape] }
      extra:    { count: [1, 2], items: [TireRepairKit, CanisterGasoline, EpoxyPutty] }
      camp:     { count: [0, 1], items: [PortableGasStove, SmallGasCanister] }
    firearms:
      - { weapon: Mp133Shotgun, magazine: null, ammo: Ammo_12gaPellets, rounds: [3, 6] }
      - { weapon: SawedoffIzh43Shotgun, magazine: null, ammo: Ammo_12gaPellets, rounds: [3, 6] }
  nomad:
    weight: 25
    slots:
      clothing: { count: [2, 3], items: [TurbanHat_Beige, TurbanHat_Brown, Keffiyeh_Brown, HuntingJacket_Desert, HunterPants_Desert, CoyoteBag_Desert] }
      water:    { count: [1, 2], items: [WaterBottle, Canteen] }
      food:     { count: [2, 3], max_each: 2, items: [Pajka, Pate, Rice, SardinesCan] }
      medical:  { count: [2, 2], items: [Rag, BandageDressing, CharcoalTablets] }
      tools:    { count: [2, 3], items: [HuntingKnife, Rope, SewingKit, Whetstone, Matchbox] }
      extra:    { count: [1, 2], items: [Compass, Hatchet] }
      camp:     { count: [0, 1], items: [Pot] }
    firearms:
      - { weapon: Mosin9130, magazine: null, ammo: Ammo_762x54, rounds: [3, 6] }
      - { weapon: Izh18, magazine: null, ammo: Ammo_762x39, rounds: [3, 6] }
  townie:
    weight: 20
    slots:
      clothing: { count: [2, 3], items: [Hoodie_Grey, TShirt_Grey, Jeans_Blue, BeanieHat_Grey, TaloonBag_Blue, Keffiyeh_Gray] }
      water:    { count: [1, 2], items: [WaterBottle] }
      food:     { count: [2, 3], max_each: 2, items: [BakedBeansCan, TunaCan, Crackers, Rice] }
      medical:  { count: [2, 2], items: [PainkillerTablets, BandageDressing, DisinfectantSpray, CharcoalTablets] }
      tools:    { count: [2, 3], items: [KitchenKnife, Flashlight, Battery9V, DuctTape] }
      extra:    { count: [1, 2], items: [Matchbox, SewingKit] }
      camp:     { count: [0, 1], items: [PortableGasStove] }
    firearms:
      - { weapon: Magnum, magazine: null, ammo: Ammo_357, rounds: [3, 6] }
      - { weapon: Derringer_Black, magazine: null, ammo: Ammo_357, rounds: [3, 6] }
```
Totals per archetype: minimum 2+1+2+2+2+1+0 = **10**, maximum 3+2+3+2+3+2+1 = **16**. Every pool is at least as large as its slot's `Min`, so the minimum is always reached. If you change a list, `test_simulated_kits_meet_the_spec` is the arbiter: it names the archetype and kit that broke the bounds.

- [ ] **Step 4: Compiler and Python mirror in `tools/arrivals.py`**

Add `import random` at the top. Replace `gear()` with:

```python
SLOT_ORDER = ["clothing", "water", "food", "medical", "tools", "extra", "camp"]


def archetypes(cfg: dict) -> list[dict]:
    out = []
    for name, a in cfg["archetypes"].items():
        slots = [{"Name": s, "Min": int(a["slots"][s]["count"][0]), "Max": int(a["slots"][s]["count"][1]),
                  "MaxEach": int(a["slots"][s].get("max_each", 1)), "Items": list(a["slots"][s]["items"])}
                 for s in SLOT_ORDER]
        guns = [{"Weapon": f["weapon"], "Magazine": f["magazine"] or "", "Ammo": f["ammo"],
                 "RoundsMin": int(f["rounds"][0]), "RoundsMax": int(f["rounds"][1])} for f in a["firearms"]]
        out.append({"Name": name, "Weight": float(a["weight"]), "Slots": slots, "Firearms": guns})
    return out


def simulate_kit(arch: dict, rng: random.Random) -> list[str]:
    """Python mirror of init.c FillCargo/FillSlot/GiveFirearm (same algorithm, for tests)."""
    kit = []
    for s in arch["Slots"]:
        pool = list(s["Items"])
        used: dict[str, int] = {}
        for _ in range(rng.randint(s["Min"], s["Max"])):
            if not pool:
                break
            name = pool[rng.randrange(len(pool))]
            kit.append(name)
            used[name] = used.get(name, 0) + 1
            if used[name] >= s["MaxEach"]:
                pool.remove(name)
    gun = arch["Firearms"][rng.randrange(len(arch["Firearms"]))]
    kit.append(gun["Weapon"])
    kit.append(gun["Magazine"] or gun["Ammo"])
    return kit
```
In `validate()`, replace the gear line with:

```python
    for a in cfg["archetypes"].values():
        names += [c for s in a["slots"].values() for c in s["items"]]
        names += [f[k] for f in a["firearms"] for k in ("weapon", "magazine", "ammo") if f.get(k)]
```
and add `"firearm_health"` to the `for key in (...)` health-range loop. In `build()`, replace `"Gear": gear(cfg),` with:

```python
        "Archetypes": archetypes(cfg),
        "FirearmHealthMin": float(cfg["firearm_health"][0]),
        "FirearmHealthMax": float(cfg["firearm_health"][1]),
```
In `main()`, replace `f"{len(out['Gear'])} gear item(s)"` with `f"{len(out['Archetypes'])} archetype(s)"`.

- [ ] **Step 5: Enforce**

Replace `class RefugeeArrivalItem` with:

```c
class RefugeeArrivalSlot
{
	string Name;
	int Min;
	int Max;
	int MaxEach;
	ref TStringArray Items;
}

class RefugeeArrivalFirearm
{
	string Weapon;
	string Magazine;
	string Ammo;
	int RoundsMin;
	int RoundsMax;
}

class RefugeeArrivalArchetype
{
	string Name;
	float Weight;
	ref array<ref RefugeeArrivalSlot> Slots;
	ref array<ref RefugeeArrivalFirearm> Firearms;
}
```
In `RefugeeArrivalConfig`, replace `ref array<ref RefugeeArrivalItem> Gear;` with:

```c
	ref array<ref RefugeeArrivalArchetype> Archetypes;
	float FirearmHealthMin;
	float FirearmHealthMax;
```
In the constructor's "incomplete" check, replace `!m_Config.Gear` with `!m_Config.Archetypes || m_Config.Archetypes.Count() == 0`, and in the Print replace `" gear=" + m_Config.Gear.Count()` with `" archetypes=" + m_Config.Archetypes.Count()`.

Delete `PickGear()`. Add:

```c
	RefugeeArrivalArchetype PickArchetype()
	{
		float total = 0;
		foreach (RefugeeArrivalArchetype a : m_Config.Archetypes)
		{
			total += a.Weight;
		}
		float roll = Math.RandomFloat(0, total);
		foreach (RefugeeArrivalArchetype b : m_Config.Archetypes)
		{
			roll -= b.Weight;
			if (roll <= 0)
				return b;
		}
		return m_Config.Archetypes[m_Config.Archetypes.Count() - 1];
	}

	EntityAI Spawn(CarScript car, string cls, float hmin, float hmax)
	{
		EntityAI item = car.GetInventory().CreateEntityInCargo(cls);
		if (item)
			item.SetHealth01("", "", Math.RandomFloatInclusive(hmin, hmax));
		return item;
	}

	// Draw Min..Max items WITHOUT replacement (an item leaves the pool after MaxEach draws).
	int FillSlot(CarScript car, RefugeeArrivalSlot s, TStringArray got)
	{
		TStringArray pool = new TStringArray;
		pool.Copy(s.Items);
		map<string, int> used = new map<string, int>;
		int want = Math.RandomIntInclusive(s.Min, s.Max);
		int added = 0;
		for (int i = 0; i < want && pool.Count() > 0; i++)
		{
			int idx = Math.RandomInt(0, pool.Count());
			string cls = pool[idx];
			if (Spawn(car, cls, m_Config.ItemHealthMin, m_Config.ItemHealthMax))
			{
				added++;
				got.Insert(cls);
			}
			used.Set(cls, used.Get(cls) + 1);
			if (used.Get(cls) >= s.MaxEach)
				pool.Remove(idx);
		}
		return added;
	}

	// One worn firearm; a partly filled magazine attached, or loose rounds (no spare magazine).
	void GiveFirearm(CarScript car, RefugeeArrivalArchetype a, TStringArray got)
	{
		RefugeeArrivalFirearm f = a.Firearms.GetRandomElement();
		Weapon_Base gun = Weapon_Base.Cast(Spawn(car, f.Weapon, m_Config.FirearmHealthMin, m_Config.FirearmHealthMax));
		if (!gun)
			return;
		got.Insert(f.Weapon);
		int rounds = Math.RandomIntInclusive(f.RoundsMin, f.RoundsMax);
		if (f.Magazine != "")
		{
			Magazine mag = gun.SpawnAttachedMagazine(f.Magazine, WeaponWithAmmoFlags.NONE);
			if (mag)
			{
				mag.ServerSetAmmoCount(rounds);
				got.Insert(f.Magazine + " x" + rounds);
				return;
			}
		}
		Magazine pile = Magazine.Cast(car.GetInventory().CreateEntityInCargo(f.Ammo));
		if (pile)
		{
			pile.ServerSetAmmoCount(rounds);
			got.Insert(f.Ammo + " x" + rounds);
		}
	}
```
Replace `FillCargo` with:

```c
	int FillCargo(CarScript car)
	{
		if (!car.GetInventory().GetCargo())
			return 0;
		RefugeeArrivalArchetype a = PickArchetype();
		TStringArray got = new TStringArray;
		int added = 0;
		foreach (RefugeeArrivalSlot s : a.Slots)
		{
			added += FillSlot(car, s, got);
		}
		GiveFirearm(car, a, got);
		Print("[DZDS Arrivals] cargo " + a.Name + ": " + got.Count() + " " + got.ToString());
		return added;
	}
```
`MaxCargoItems` and `CargoFill` are no longer read by `FillCargo`. Remove them from `RefugeeArrivalConfig`, from `build()` (`"CargoFill"`, `"MaxCargoItems"`) and from `validate()` (`cargo_fill`), and delete `cargo_fill:` / `max_cargo_items:` from `presets/arrivals.yaml`, since the slots now bound the cargo.

- [ ] **Step 6: Run the tests**

Run: `make arrivals && .venv/bin/python -m pytest tests/test_arrivals.py -v`
Expected: PASS. If `test_simulated_kits_meet_the_spec` fails, tune slot counts in the preset (Step 3), never the test bounds.

- [ ] **Step 7: Commit**

```bash
git add presets/arrivals.yaml tools/arrivals.py server/mpmissions/<NASDARA>/init.c tests/test_arrivals.py server/profiles/DZDS/arrivals.json
git commit -m "arrivals: archetype cargo (no duplicates) with one themed firearm and meagre ammo"
```

---

## Phase E: Verify and launch

### Task 19: Local boot test (two boots)

The first boot generates the mods' configs for Nasdara. `prepare-restart` then rewrites them, and the second boot proves the result. Blae does the in-game walk-through; the agent reads the logs.

**Files:**
- Modify: `presets/kan_camps.yaml` (Nasdara camp Ids + `site:`), `tests/test_zone_placement.py` (remove the xfail), `presets/convoys.yaml` and `presets/convoy_routes/nasdara/*.json` (if routes are recorded), `docs/PRUNING.md` (boot results)

- [ ] **Step 1: First boot**

```bash
scripts/local_server.sh mods
scripts/local_server.sh start    # in a second terminal; wait for "Mission read" in the RPT, then stop it (Ctrl-C)
ls -t server/profiles/*.RPT | head -1 | xargs grep -n -i -E "SCRIPT +\(E\)|Can't compile|Unhandled exception" | head -40
```
Expected: no `SCRIPT (E)` or compile errors. For each error, name the mod from its path. A non-core mod gets pruned (mark it in `config/mods.yaml` like Task 5, with reason `script errors on 1.30 boot`) and the boot is repeated. A core mod (CF, Dabs, Expansion Core/AI, VPP, @DZDS) **stops the launch**: tell Blae.

- [ ] **Step 2: Fill the KAN preset from the generated camps**

```bash
.venv/bin/python -c "import json;print([c['Id'] for c in json.load(open('server/profiles/KANSurvivorNPC/camps.json'))['Camps']])"
```
In `presets/kan_camps.yaml`, replace the Chernarus camp entries with one entry per camp to **keep** (1–2), each with `site: <a Settlers site from initial_control.nasdara>` plus the six role counts (Roamers 0, Attackers 1). Camps not listed get removed by the tool. Remove the `xfail` marker in `tests/test_zone_placement.py`, then run `make test` → PASS.

- [ ] **Step 3: Generate everything**

```bash
make kan-camps && make prepare-restart
git diff --stat server/profiles
```
Expected: `zone-events` reports `changed` for every event file. `validate` passes.

- [ ] **Step 4: Second boot and log checks**

Start the server again and let it run for 10 minutes. Then:

```bash
R=$(ls -t server/profiles/*.RPT | head -1)
grep -n -E "SCRIPT +\(E\)" "$R" | head
grep -n "\[DZDS Arrivals\]" "$R" | head
```
Expected: no script errors, and an `[DZDS Arrivals] enabled=1 ... archetypes=4` line.

- [ ] **Step 5: Blae's in-game walk-through (local server, ~30 min)**

Hand Blae this checklist and record each answer in `docs/PLAYTEST.md` under a dated "Badlands local boot" section:

| # | Check | Pass |
|---|---|---|
| 1 | Fresh character wakes at a campfire beside a car, at the column site for today | yes/no |
| 2 | Inventory has a PersonalRadio with a battery, switched off. Switching it on shows a frequency (record the MHz) | yes/no + MHz |
| 3 | A road flare is in the inventory | yes/no |
| 4 | Car cargo looks like one archetype, with no duplicates beyond two food cans and one firearm with a few rounds. RPT `cargo` line matches | yes/no |
| 5 | Die, respawn: the new character wakes 2–5 km away (measure on the map) | yes/no + km |
| 6 | A second character on the same day (second account or wiped ledger entry) wakes at the same site | yes/no |
| 7 | Garrisons visible at a stronghold. Site marker objects present | yes/no |
| 8 | 20 min in open country: no AI, no airdrop, no horde, no crate. Note any HUD notifications | yes/no |
| 9 | Handheld radio range: two radios on the same channel, walk apart until voice drops (record metres) | metres |
| 10 | Expansion war-party patrol: force one (`.venv/bin/python tools/war.py turn --force` with `war_party.chance: 1.0` temporarily) and confirm it spawns near the origin and walks toward the target | yes/no |

If check 10 fails (route patrols don't spawn the way war parties need), set the ledger to convoy-only war parties: in `war_party_candidates()`, wrap the raid and offensive loops in `if self.rules["war_party"].get("patrols", True):`, set `war_party.patrols: false` in `presets/ledger.yaml`, and add a test for it.

- [ ] **Step 6: Record convoy routes (optional, needs Blae driving)**

For each pair of same-faction strongholds Blae wants convoys between, add his Steam64 ID to `RouteRecorderPlayers` in `AIConvoySettings.json`, have him drive the road between them, then copy the recorded `Routes/*.json` into `presets/convoy_routes/nasdara/` and list it in `presets/convoys.yaml`. With no routes recorded, convoys simply never run.

- [ ] **Step 7: Commit**

```bash
git add presets/ tests/test_zone_placement.py docs/PLAYTEST.md docs/PRUNING.md config/mods.yaml server/
git commit -m "Badlands: local 1.30 boot verified; KAN camps placed; generated configs"
```

---

### Task 20: Docs follow the change

**Files:**
- Modify: `CLAUDE.md` (Current stage, rules 13–14, commands), `docs/ECONOMY.md`, `docs/LIVING_WORLD.md`, `docs/BADLANDS_PREP.md`, `docs/SPEC.md` (phase references)

- [ ] **Step 1: Update `CLAUDE.md`**
  - Rule 13: "Economy = **pure vanilla** CE (Blae, 2026-10-15) + faction barter traders… `make economy` regenerates types.xml from `db/types.xml.vanilla` changing only arrival-car lifetimes."
  - Add rule 15: "**Zones (2026-10-15).** NPCs and events only inside strongholds/warzones (`tools/zones.py`); `make zone-events` writes event-mod configs; only the ledger's single war party crosses open country; `tests/test_zone_placement.py` enforces it; `make encounter-audit` measures it (target ≤ 1 per player per 3 sessions)."
  - Replace "Current stage" with the Badlands state: map Nasdara, mission `<NASDARA>`, mod count from `make specs`, the arrival features, the radio MHz from Task 19, and what's still pending (the radio bulletin follow-up).
  - Commands: drop the `PHASE=` note on `economy`; add `survey`, `zone-events`, `encounter-audit`.
- [ ] **Step 2: `docs/ECONOMY.md`, `docs/LIVING_WORLD.md`, `docs/SPEC.md`:** remove phase pacing, and describe zones and the war party as the clock (spec §5.2). `docs/BADLANDS_PREP.md`: mark it done and link the spec.
- [ ] **Step 3: Update the player page**

Read the player-facing artifact `https://claude.ai/artifact/4egYhN9vK3xqVYYQxMCu9C` (Artifact tool, `action: read`), then republish it to the same URL. The new version covers: map Nasdara and the Badlands DLC requirement; DZSA/DZGUI join via query port 26092; the Settler net (MHz from Task 19); the refugee column (first arrivals on the same day start together; the day turns over at 06:00 Central); respawns near where you died; NPCs and events living at strongholds and warzones only.

- [ ] **Step 4: Check nothing still mentions phases**

```bash
grep -rn -i -E "campaign phase|landfall|scavenger phase|long_war|PHASE=" --include=*.md --include=*.yaml --include=*.py . | grep -v docs/superpowers | grep -v backups/
```
Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "docs: Badlands relaunch (zones, pure vanilla, arrivals); phases removed"
```

---

### Task 21: Go live (Blae runs the panel)

**Files:** none (handoff). The agent prepares the values; Blae applies them.

- [ ] **Step 1: Prepare the values**

```bash
make panel-mods > build/panel-mods.txt && wc -c build/panel-mods.txt
grep -E "^(vonCodecQuality|lightingConfig)" config/local_serverDZ.cfg
.venv/bin/python tools/active.py mission
```

- [ ] **Step 2: Confirm DLC ownership**

Ask Blae whether every player owns Badlands, or whether that's confirmed unnecessary. Don't proceed without his answer.

- [ ] **Step 3: Fresh-start state (spec: characters, ledger and Hardline reputation reset)**

```bash
TS=$(date +%Y%m%d-%H%M%S); mkdir -p backups/fresh-start-$TS
grep -rl -i -E "reputation" server/profiles/ExpansionMod 2>/dev/null | grep -v -i settings | head -20
ls server/profiles/DZDS/arrivals_ledger.json
```
Show Blae the list: per-player Hardline reputation files, plus `arrivals_ledger.json`. The latter must go, or players who arrived on Chernarus aren't "first arrivals" and miss the column. With his yes, **move** (never delete) them into `backups/fresh-start-$TS/`, locally and (as part of the push in Step 4) on the server via the SFTP File Manager. He does the remote move.

- [ ] **Step 4: Hand Blae the steps, in this order**

1. Panel → stop the server.
2. Panel → Startup → mission/template = `<NASDARA>`.
3. Panel → Startup → "Additional Mods": select all, delete, then paste the **whole** "Additional Mods" line from `build/panel-mods.txt` (the field REPLACES; never append). Do the same for "Server-Side Only Mods".
4. Panel → VON codec quality = 30 (and "Darker Nights" = 1, unchanged).
5. Tell the agent "panel done". The agent then runs `DRY_RUN=1 make push` → shows Blae the file list → `make push`.
6. Panel → start. Wait for the first full boot.
7. The agent runs `make pull && make overlays calibrate zone-events validate && make push` (configs regenerate for the real server's first boot). Blae restarts once more.

- [ ] **Step 5: Verify**

```bash
make mod-drift
make logs && grep -c "SCRIPT    (E)" "$(ls -t server/profiles/*.RPT | head -1)"
```
Expected: no drift, and `0` script errors. Then Blae and one friend join through DZSA/DZGUI (query port 26092) and repeat checks 1–4 of the Task 19 table.

- [ ] **Step 6: Commit and merge**

```bash
git add -A server/ && git commit -m "server/: Nasdara live mirror after go-live"
git switch main && git merge --no-ff badlands-relaunch -m "Badlands relaunch"
```

---

### Task 22: First-week watch

Operational, no code.

- [ ] **Step 1: Before each play session:** `make mod-drift`. On drift, Blae renames `/@<id>` aside and restarts (see `CLAUDE.md`).
- [ ] **Step 2: Each restart:** `make pull && make prepare-restart && make push`.
- [ ] **Step 3: After 3+ sessions:** `make encounter-audit`. If any player reads `OVER`, lower `war_party.chance` in `presets/ledger.yaml` by 0.1 (floor 0.1), commit with the audit output in the message, and re-audit after three more sessions.
- [ ] **Step 4: Crash watch:** compare `crash_*.log` times with boot times, as in `CLAUDE.md`'s Crash watch note.
- [ ] **Step 5: Week-one follow-up:** start a new brainstorming → spec cycle for the @DZDS radio bulletin (spec §6.1). It's out of scope here.
