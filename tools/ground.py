#!/usr/bin/env python3
"""Ground height (y) at a map point, for configs whose mods spawn things at the y we give them.

Nasdara's terrain can't be read offline, so this is the best evidence on disk:
1. real ground samples from .ADM lines (a player or AI standing there: hit, unconscious,
   regained), the lowest within `sample_radius`; else
2. the LOWEST placed-building origin within `building_radius` (mapgrouppos.xml). An origin is
   the model's centre, metres above the ground for big buildings, so the lowest nearby one
   (walls, sheds) is the closest to the ground; never the nearest, which put a War Zones team
   on top of Northern Dam at y=400 (2026-10-23); else
3. 0.0, and the mod snaps it (spawn in @DZDS) or the object falls.

Measured on 60 ADM samples (2026-10-24): nearest building was off by a median 6 m and up to 87 m,
lowest building by a median 5.6 m and at most 10.7 m. The @DZDS terrain sampler will replace both.
"""
from __future__ import annotations

import re
from pathlib import Path

_POS = re.compile(r"pos=<(-?[\d.]+), (-?[\d.]+), (-?[\d.]+)>")
_STANDING = ("hit by", "is unconscious", "regained consciousness")


def adm_samples(paths) -> list[tuple[float, float, float]]:
    """(x, z, y) where someone stood, from .ADM lines that log a body on the ground."""
    out = []
    for p in paths:
        for line in Path(p).read_text(errors="replace").splitlines():
            if not any(s in line for s in _STANDING):
                continue
            m = _POS.search(line)
            if m:
                x, z, y = (float(v) for v in m.groups())   # DayZ: pos=<x, z, altitude>
                if abs(x) < 1e6 and abs(z) < 1e6:
                    out.append((x, z, y))
    return out


class Ground:
    def __init__(self, groups=(), samples=(), sample_radius: float = 30.0,
                 building_radius: float = 100.0) -> None:
        self.groups = list(groups)          # map_survey.load_groups: (name, x, y, z)
        self.samples = list(samples)        # (x, z, y)
        self.sr, self.br = sample_radius, building_radius

    def __call__(self, x: float, z: float) -> float:
        near = [y for sx, sz, y in self.samples if (sx - x) ** 2 + (sz - z) ** 2 <= self.sr ** 2]
        if near:
            return min(near)
        for r in (self.br, self.br * 1.5):
            ys = [gy for _, gx, gy, gz in self.groups
                  if abs(gx - x) <= r and abs(gz - z) <= r and (gx - x) ** 2 + (gz - z) ** 2 <= r * r]
            if ys:
                return min(ys)
        return 0.0
