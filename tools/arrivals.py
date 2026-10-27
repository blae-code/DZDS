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


_TYPES_CACHE: dict[Path, tuple[int, int, set[str]]] = {}
_SPOTS_CACHE: dict[tuple[Path, int, int, tuple[str, ...]], list[tuple[float, float, float]]] = {}


def mission_dir(map_data: dict) -> Path:
    return ROOT / "server" / "mpmissions" / map_data["mission"]


def _types_in_file(path: Path) -> set[str]:
    st = path.stat()
    hit = _TYPES_CACHE.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return hit[2]
    names = {t.get("name") for t in ET.parse(path).getroot().findall("type")}
    _TYPES_CACHE[path] = (st.st_mtime_ns, st.st_size, names)
    return names


def known_types(mission: Path) -> set[str]:
    """Vanilla types plus our own types file (tools/types_gen.py registers modded respawn
    vehicles and parts there; run `make types` before `make arrivals`). Also includes
    all modded types declared in dzds_mods/."""
    names: set[str] = set()
    for f in (mission / "db" / "types.xml", mission / "dzds" / "types_dzds.xml"):
        if f.exists():
            names |= _types_in_file(f)
    mods_dir = mission / "dzds_mods"
    if mods_dir.is_dir():
        for f in mods_dir.glob("*.xml"):
            names |= _types_in_file(f)
    return names


def road_spots(mission: Path, events: list[str]) -> list[tuple[float, float, float]]:
    spawns_path = mission / "cfgeventspawns.xml"
    st = spawns_path.stat()
    key = (spawns_path, st.st_mtime_ns, st.st_size, tuple(events))
    if key in _SPOTS_CACHE:
        return list(_SPOTS_CACHE[key])
    ev_set = set(events)
    root = ET.parse(spawns_path).getroot()
    out = []
    for ev in root.findall("event"):
        if ev.get("name") in ev_set:
            for p in ev.findall("pos"):
                out.append((float(p.get("x")), float(p.get("z")), float(p.get("a") or 0.0)))
    _SPOTS_CACHE[key] = out
    return list(out)


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
OPTIONAL_SLOTS = ["pack", "vest", "survival", "fishing", "fuel", "signal"]   # pilot profiles add these


def _archetype(name: str, a: dict) -> dict:
    slots = [{"Name": s, "Min": int(a["slots"][s]["count"][0]), "Max": int(a["slots"][s]["count"][1]),
              "MaxEach": int(a["slots"][s].get("max_each", 1)), "Items": list(a["slots"][s]["items"])}
             for s in SLOT_ORDER + [o for o in OPTIONAL_SLOTS if o in a["slots"]]]
    guns = [{"WeaponClass": f["weapon"], "MagazineClass": f["magazine"] or "", "Ammo": f["ammo"],
             "RoundsMin": int(f["rounds"][0]), "RoundsMax": int(f["rounds"][1]),
             "SpareMin": int(f.get("spare", [0, 0])[0]), "SpareMax": int(f.get("spare", [0, 0])[1])}
            for f in a["firearms"]]
    return {"Name": name, "Weight": float(a.get("weight", 0)), "Aircraft": int(bool(a.get("aircraft"))),
            "Slots": slots, "Firearms": guns}


def archetypes(cfg: dict) -> list[dict]:
    return [_archetype(name, a) for name, a in cfg["archetypes"].items()]


def _worn(entry) -> dict:
    if isinstance(entry, str):
        return {"ClassName": entry, "Attach": []}
    return {"ClassName": entry["class"], "Attach": list(entry.get("attach") or [])}


def _kit_weapon(w: dict) -> dict:
    return {"WeaponClass": w["weapon"], "Attach": list(w.get("attach") or []), "MagazineClass": w["magazine"],
            "Magazines": int(w["magazines"]), "Rounds": int(w["rounds"])}


def outfits(cfg: dict) -> list[dict]:
    """Worn outfits (Blae, 2026-10-23). LandCargo is a ground archetype used only by its outfit."""
    out = []
    for name, o in (cfg.get("outfits") or {}).items():
        out.append({
            "Name": name, "Chance": float(o["chance"]),
            "HealthMin": float(o["health"][0]), "HealthMax": float(o["health"][1]),
            "Variants": [{"Name": v, "Worn": [_worn(e) for e in worn]} for v, worn in o["variants"].items()],
            "Carried": list(o["carried"]),
            "Primary": [_kit_weapon(w) for w in o["primary"]],
            "Sidearm": _kit_weapon(o["sidearm"]),
            "AircraftCargo": o["aircraft_cargo"],
            "LandCargo": _archetype(name, o["land_cargo"]),
        })
    return out


def outfit_classnames(o: dict) -> list[str]:
    names = []
    for worn in o["variants"].values():
        for w in map(_worn, worn):
            names += [w["ClassName"], *w["Attach"]]
    names += o["carried"]
    for w in [*o["primary"], o["sidearm"]]:
        names += [w["weapon"], w["magazine"], *(w.get("attach") or [])]
    lc = o["land_cargo"]
    names += [c for s in lc["slots"].values() for c in s["items"]]
    names += [f[k] for f in lc["firearms"] for k in ("weapon", "magazine", "ammo") if f.get(k)]
    return names


def simulate_dress(outfit: dict, rng: random.Random) -> list[str]:
    """Python mirror of init.c Dress: one variant worn (attachments after their carrier), the
    carried items, one primary and the sidearm, each followed by its full magazines."""
    variant = outfit["Variants"][rng.randrange(len(outfit["Variants"]))]
    kit = []
    for w in variant["Worn"]:
        kit += [w["ClassName"], *w["Attach"]]
    kit += outfit["Carried"]
    for w in (outfit["Primary"][rng.randrange(len(outfit["Primary"]))], outfit["Sidearm"]):
        kit += [w["WeaponClass"], *w["Attach"]] + [w["MagazineClass"]] * w["Magazines"]
    return kit


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
    for lv in cfg.get("light_vehicles", []):
        names.append(lv["class"])
        names += lv.get("parts", [])
    for a in cfg["archetypes"].values():
        names += [c for s in a["slots"].values() for c in s["items"]]
        names += [f[k] for f in a["firearms"] for k in ("weapon", "magazine", "ammo") if f.get(k)]
    names += [cfg["trailer"]["class"]] + cfg["trailer"]["parts"] + cfg["nav_kit"]["items"]
    names += cfg.get("fuel_cans", [])
    comp = cfg.get("companion") or {}
    removed = sorted(k for k in comp if k.startswith(("dog_", "horse_")))
    if removed or {"dog", "horse"} & set(comp.get("weights") or {}):
        raise SystemExit(f"dog/horse companions were removed 2026-10-27 (mods pruned): {removed or 'weights'}")
    for o in (cfg.get("outfits") or {}).values():
        names += outfit_classnames(o)
    missing = sorted({n for n in names if n not in types})
    if missing:
        raise SystemExit(f"not in db/types.xml (typo or modded type not registered): {missing}")
    stray = set(cfg.get("aircraft", [])) - {v["class"] for v in cfg["vehicles"]}
    if stray:
        raise SystemExit(f"aircraft names no configured vehicle: {sorted(stray)}")
    for name, a in cfg["archetypes"].items():
        unknown = set(a["slots"]) - set(SLOT_ORDER) - set(OPTIONAL_SLOTS)
        if unknown:   # archetypes() compiles only known slots: an unknown one would vanish
            raise SystemExit(f"archetype {name}: unknown slot(s) {sorted(unknown)}")
    kinds = {bool(a.get("aircraft")) for a in cfg["archetypes"].values()}
    if False not in kinds or (cfg.get("aircraft") and True not in kinds):
        raise SystemExit("archetypes need at least one ground profile, and one pilot profile "
                         "(aircraft: true) when any aircraft is configured")
    for key in ("fuel", "aircraft_fuel", "vehicle_health", "item_health", "firearm_health"):
        lo, hi = cfg[key]
        if not 0 <= lo <= hi <= 1:
            raise SystemExit(f"{key} must be 0 <= min <= max <= 1, got {cfg[key]}")
    lo, hi = cfg["respawn_near_players_m"]
    if not 0 < lo <= hi:
        raise SystemExit(f"respawn_near_players_m must be 0 < min <= max, got {[lo, hi]}")
    stray = set(cfg["trailer"]["skip"]) - {v["class"] for v in cfg["vehicles"]}
    if stray:
        raise SystemExit(f"trailer.skip names no configured vehicle: {sorted(stray)}")
    for f in cfg.get("favored", []):
        stray = set(f["vehicles"]) - {v["class"] for v in cfg["vehicles"]}
        if stray or not f["vehicles"]:
            raise SystemExit(f"favored {f['name']} names no configured vehicle: {sorted(stray)}")
        if f.get("outfit") and f["outfit"] not in (cfg.get("outfits") or {}):
            raise SystemExit(f"favored {f['name']}: no outfit named {f['outfit']!r}")
        cooldown = set(f.get("cooldown_vehicles") or [])
        all_allowed_vehicles = {v["class"] for v in cfg["vehicles"]} | {v["class"] for v in cfg.get("light_vehicles", [])}
        stray = cooldown - all_allowed_vehicles
        if stray:
            raise SystemExit(f"favored {f['name']} cooldown_vehicles names no configured vehicle: {sorted(stray)}")
        if cooldown & set(cfg.get("aircraft", [])):
            raise SystemExit(f"favored {f['name']} cooldown_vehicles must be land vehicles, got "
                             f"{sorted(cooldown & set(cfg.get('aircraft', [])))}")
    pilots = {n for n, a in cfg["archetypes"].items() if a.get("aircraft")}
    for name, o in (cfg.get("outfits") or {}).items():
        if o["aircraft_cargo"] not in pilots:
            raise SystemExit(f"outfit {name}: aircraft_cargo {o['aircraft_cargo']!r} is not a pilot profile")
        unknown = set(o["land_cargo"]["slots"]) - set(SLOT_ORDER)
        missing_slots = set(SLOT_ORDER) - set(o["land_cargo"]["slots"])
        if unknown or missing_slots:
            raise SystemExit(f"outfit {name}: land_cargo needs exactly the slots {SLOT_ORDER}")
        lo, hi = o["health"]
        if not 0 <= o["chance"] <= 1 or not 0 <= lo <= hi <= 1:
            raise SystemExit(f"outfit {name}: chance and health must lie in [0, 1]")
        if not o["variants"] or not o["primary"]:
            raise SystemExit(f"outfit {name}: needs at least one variant and one primary")


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
        "RespawnNearPlayersMin": float(cfg["respawn_near_players_m"][0]),
        "RespawnNearPlayersMax": float(cfg["respawn_near_players_m"][1]),
        "BaseRespawn": int(bool(cfg["base_respawn"])),
        "BasePlayerOffset": float(cfg["base_player_offset_m"]),
        "RespawnAtHq": int(bool(cfg.get("respawn_at_hq", False))),
        "HqPoints": [point(s, "Qalat-e Lut") for s in cfg.get("hq_points", [])],
        "CompanionEnabled": int(bool((cfg.get("companion") or {}).get("enabled", True))),
        "CompanionChance": float((cfg.get("companion") or {}).get("chance", 0.05)),
        "ArrivalSites": arrival_points(cfg, map_data, spots),
        "RoadPoints": road,
        "Vehicles": [{"ClassName": v["class"], "Weight": float(v["weight"]), "Parts": list(v["parts"]),
                      "Trailer": int(v["class"] not in cfg["trailer"]["skip"]),
                      "Aircraft": int(v["class"] in cfg.get("aircraft", []))}
                     for v in cfg["vehicles"]],
        "LightVehicles": [{"ClassName": v["class"], "Weight": float(v["weight"]), "Parts": list(v.get("parts", [])),
                           "Trailer": 0, "Aircraft": 0}
                          for v in cfg.get("light_vehicles", [])],
        "Favored": [{"Id": f["id"], "Name": f["name"], "Vehicles": list(f["vehicles"]),
                     "Outfit": f.get("outfit") or "", "CooldownVehicles": list(f.get("cooldown_vehicles") or []),
                     "CompanionChance": float(f.get("companion_chance", 0.0))}
                    for f in cfg.get("favored", [])],
        "Archetypes": archetypes(cfg),
        "Outfits": outfits(cfg),
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
          f"{len(out['Archetypes'])} archetype(s), {len(out['Outfits'])} outfit(s)")
    if not args.dry_run:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(out, indent=4) + "\n")
        print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
