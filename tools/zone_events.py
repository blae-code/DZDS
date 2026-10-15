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
