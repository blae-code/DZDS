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
