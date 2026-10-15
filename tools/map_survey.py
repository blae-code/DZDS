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
