#!/usr/bin/env python3
"""Compile presets/arrivals.yaml into server/profiles/DZDS/arrivals.json for the mission init.c.

Arrival sites come from maps/<map>.yaml `arrival_sites`, snapped to the nearest vanilla roadside
vehicle spots; respawn road points are every vanilla vehicle spot (cfgeventspawns.xml) outside
the excluded zones. Every vehicle, part, item and firearm classname must exist in the mission's
db/types.xml, so a typo fails here instead of silently spawning nothing in game.

Usage: tools/arrivals.py [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

import active

ROOT = Path(__file__).resolve().parent.parent
PRESET = ROOT / "presets" / "arrivals.yaml"
OUT = ROOT / "server" / "profiles" / "DZDS" / "arrivals.json"


def mission_dir(map_data: dict) -> Path:
    return ROOT / "server" / "mpmissions" / map_data["mission"]


def known_types(mission: Path) -> set[str]:
    """Vanilla types plus our own types file (tools/types_gen.py registers modded respawn
    vehicles and parts there; run `make types` before `make arrivals`)."""
    names = set()
    for f in (mission / "db" / "types.xml", mission / "dzds" / "types_dzds.xml"):
        if f.exists():
            names |= {t.get("name") for t in ET.parse(f).getroot().findall("type")}
    return names


def road_spots(mission: Path, events: list[str]) -> list[tuple[float, float, float]]:
    root = ET.parse(mission / "cfgeventspawns.xml").getroot()
    out = []
    for ev in root.findall("event"):
        if ev.get("name") in events:
            for p in ev.findall("pos"):
                out.append((float(p.get("x")), float(p.get("z")), float(p.get("a") or 0.0)))
    return out


def excluded(spot, zones) -> bool:
    return any(math.dist(spot[:2], (x, z)) <= r for x, z, r in zones)


def exclusion_zones(cfg: dict, map_data: dict) -> list[tuple[float, float, float]]:
    zones = [tuple(map(float, p)) for p in cfg.get("exclude_points") or []]
    locs, roles = map_data["locations"], map_data.get("roles") or {}
    for role in cfg.get("exclude_roles") or []:
        for site in roles.get(role) or []:
            x, z = locs[site][:2]
            zones.append((float(x), float(z), float(cfg["exclude_radius_m"])))
    return zones


def point(spot, name: str = "") -> dict:
    return {"Name": name, "X": round(spot[0], 2), "Z": round(spot[1], 2), "A": round(spot[2], 2)}


def arrival_points(cfg: dict, map_data: dict, spots: list) -> list[dict]:
    sites = map_data.get("arrival_sites") or {}
    if not sites:
        raise SystemExit(f"maps: no arrival_sites for {map_data['name']}")
    out = []
    for name, (x, z) in sites.items():
        near = sorted(spots, key=lambda s: math.dist(s[:2], (x, z)))[: cfg["points_per_site"]]
        if not near or math.dist(near[0][:2], (x, z)) > cfg["snap_radius_m"]:
            raise SystemExit(f"arrival site {name}: no vehicle spot within {cfg['snap_radius_m']} m")
        out += [point(s, name) for s in near if math.dist(s[:2], (x, z)) <= cfg["snap_radius_m"]]
    return out


SLOT_ORDER = ["clothing", "water", "food", "medical", "knife", "tools", "extra", "camp", "car"]
OPTIONAL_SLOTS = ["fuel", "signal"]   # pilot profiles (aircraft: true) add these


def archetypes(cfg: dict) -> list[dict]:
    out = []
    for name, a in cfg["archetypes"].items():
        slots = [{"Name": s, "Min": int(a["slots"][s]["count"][0]), "Max": int(a["slots"][s]["count"][1]),
                  "MaxEach": int(a["slots"][s].get("max_each", 1)), "Items": list(a["slots"][s]["items"])}
                 for s in SLOT_ORDER + [o for o in OPTIONAL_SLOTS if o in a["slots"]]]
        guns = [{"WeaponClass": f["weapon"], "MagazineClass": f["magazine"] or "", "Ammo": f["ammo"],
                 "RoundsMin": int(f["rounds"][0]), "RoundsMax": int(f["rounds"][1]),
                 "SpareMin": int(f.get("spare", [0, 0])[0]), "SpareMax": int(f.get("spare", [0, 0])[1])}
                for f in a["firearms"]]
        out.append({"Name": name, "Weight": float(a["weight"]), "Aircraft": int(bool(a.get("aircraft"))),
                    "Slots": slots, "Firearms": guns})
    return out


def simulate_kit(arch: dict, rng: random.Random) -> list[str]:
    """Python mirror of init.c FillCargo/FillSlot/GiveFirearm (same algorithm, for tests)."""
    gun = arch["Firearms"][rng.randrange(len(arch["Firearms"]))]
    kit = [gun["WeaponClass"]]
    if gun["MagazineClass"]:
        kit.append(gun["MagazineClass"])
    if not gun["MagazineClass"] or gun["SpareMax"] > 0:
        kit.append(gun["Ammo"])
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
    return kit


def validate(cfg: dict, types: set[str]) -> None:
    names = [v["class"] for v in cfg["vehicles"]]
    names += [p for v in cfg["vehicles"] for p in v["parts"]]
    for a in cfg["archetypes"].values():
        names += [c for s in a["slots"].values() for c in s["items"]]
        names += [f[k] for f in a["firearms"] for k in ("weapon", "magazine", "ammo") if f.get(k)]
    names += [cfg["trailer"]["class"]] + cfg["trailer"]["parts"] + cfg["nav_kit"]["items"]
    names += cfg.get("fuel_cans", [])
    missing = sorted({n for n in names if n not in types})
    if missing:
        raise SystemExit(f"not in db/types.xml (typo or modded type not registered): {missing}")
    stray = set(cfg.get("aircraft", [])) - {v["class"] for v in cfg["vehicles"]}
    if stray:
        raise SystemExit(f"aircraft names no configured vehicle: {sorted(stray)}")
    kinds = {bool(a.get("aircraft")) for a in cfg["archetypes"].values()}
    if False not in kinds or (cfg.get("aircraft") and True not in kinds):
        raise SystemExit("archetypes need at least one ground profile, and one pilot profile "
                         "(aircraft: true) when any aircraft is configured")
    for key in ("fuel", "aircraft_fuel", "vehicle_health", "item_health", "firearm_health"):
        lo, hi = cfg[key]
        if not 0 <= lo <= hi <= 1:
            raise SystemExit(f"{key} must be 0 <= min <= max <= 1, got {cfg[key]}")
    stray = set(cfg["trailer"]["skip"]) - {v["class"] for v in cfg["vehicles"]}
    if stray:
        raise SystemExit(f"trailer.skip names no configured vehicle: {sorted(stray)}")
    for f in cfg.get("favored", []):
        stray = set(f["vehicles"]) - {v["class"] for v in cfg["vehicles"]}
        if stray or not f["vehicles"]:
            raise SystemExit(f"favored {f['name']} names no configured vehicle: {sorted(stray)}")


def build(cfg: dict, map_data: dict, mission: Path) -> dict:
    validate(cfg, known_types(mission))
    spots = road_spots(mission, cfg["road_events"])
    zones = exclusion_zones(cfg, map_data)
    road = [point(s) for s in spots if not excluded(s, zones)]
    if not road:
        raise SystemExit("no road spots left after exclusions")
    return {
        "Enabled": int(bool(cfg["enabled"])),
        "CooldownHours": int(cfg["cooldown_hours"]),
        "RandomCharacterOnRespawn": int(bool(cfg["random_character_on_respawn"])),
        "PlayerOffset": float(cfg["player_offset_m"]),
        "FuelMin": float(cfg["fuel"][0]), "FuelMax": float(cfg["fuel"][1]),
        "AircraftFuelMin": float(cfg["aircraft_fuel"][0]), "AircraftFuelMax": float(cfg["aircraft_fuel"][1]),
        "FuelCans": list(cfg.get("fuel_cans", [])),
        "UnfillableSlots": list(cfg.get("unfillable_slots", [])),
        "HealthMin": float(cfg["vehicle_health"][0]), "HealthMax": float(cfg["vehicle_health"][1]),
        "ItemHealthMin": float(cfg["item_health"][0]), "ItemHealthMax": float(cfg["item_health"][1]),
        "RadioFrequencyIndex": int(cfg["radio"]["settler_net_index"]),
        "GiveRoadflare": int(bool(cfg["give_roadflare"])),
        "NavKitHours": int(cfg["nav_kit"]["cooldown_hours"]),
        "NavKit": list(cfg["nav_kit"]["items"]),
        "TrailerClass": cfg["trailer"]["class"] if cfg["trailer"].get("enabled", True) else "",
        "TrailerParts": list(cfg["trailer"]["parts"]),
        "ColumnSites": list((map_data.get("arrival_sites") or {}).keys()),
        "ColumnDayStartUtcHour": int(cfg["column_day_start_utc_hour"]),
        "RespawnNearMin": float(cfg["respawn_near_m"][0]),
        "RespawnNearMax": float(cfg["respawn_near_m"][1]),
        "RespawnNearFallback": float(cfg["respawn_near_fallback_m"]),
        "CampRespawnRadius": float(cfg["camp_respawn_m"]),
        "CampPlayerOffset": float(cfg["camp_player_offset_m"]),
        "ArrivalSites": arrival_points(cfg, map_data, spots),
        "RoadPoints": road,
        "Vehicles": [{"ClassName": v["class"], "Weight": float(v["weight"]), "Parts": list(v["parts"]),
                      "Trailer": int(v["class"] not in cfg["trailer"]["skip"]),
                      "Aircraft": int(v["class"] in cfg.get("aircraft", []))}
                     for v in cfg["vehicles"]],
        "Favored": [{"Id": f["id"], "Name": f["name"], "Vehicles": list(f["vehicles"])}
                    for f in cfg.get("favored", [])],
        "Archetypes": archetypes(cfg),
        "FirearmHealthMin": float(cfg["firearm_health"][0]),
        "FirearmHealthMax": float(cfg["firearm_health"][1]),
    }


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--dry-run", action="store_true")
    args = a.parse_args()
    cfg = yaml.safe_load(PRESET.read_text())
    map_name = active.map_name()
    map_data = yaml.safe_load((ROOT / "maps" / f"{map_name}.yaml").read_text())
    out = build(cfg, map_data, mission_dir(map_data))
    sites = sorted({p["Name"] for p in out["ArrivalSites"]})
    print(f"arrivals: {len(out['ArrivalSites'])} arrival spot(s) at {len(sites)} site(s) {sites}, "
          f"{len(out['RoadPoints'])} road respawn spot(s), {len(out['Vehicles'])} vehicle(s), "
          f"{len(out['Archetypes'])} archetype(s)")
    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, indent=4) + "\n")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
