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
import ground as ground_mod
import map_survey
import zones as zmod

ROOT = active.ROOT
PROFILES = ROOT / "server" / "profiles"
FLAT = lambda x, z: 0.0  # noqa: E731


def load_cfg() -> dict:
    return active.load_yaml("presets/zone_events.yaml")


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
    for k in list(ev):
        if k in MARKER_KEYS or k == "ShowLocationInNotifications" or (
                k.startswith("Enable") and k.endswith("Notification")):
            ev[k] = 0
    ev.update({"ActiveCrateCount": c["active"], "RefreshInterval": c["refresh_s"], "StaticSpawns": 0,
               "CrateLocations": [{"Position": _xyz(zn.x, zn.z, y), "Rotation": "0.0 0.0 0.0",
                                   "LocationName": zn.name, "AISpawnPositions": []}
                                  for zn in _drop_sites(zs, c["holders"])]})
    return out


def team_faction(spec: dict, names: str) -> str:
    """The faction string War Zones gets. Its code only knows Expansion's built-in factions and
    turns anything else into West (both teams of every zone were West until 2026-10-24), so our
    @DZDS classes work only with the @DZDS build that teaches it them (DZDSWarZones.c)."""
    return spec["custom_faction"] if names == "custom" else spec["interim_faction"]


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
    extra = set(w.get("extra_warzones", []))
    for zn in zs:
        if zn.state != "warzone" and zn.name not in extra:
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
                  "zoneAINoiseInvestigationRange": 300.0,
                  "zoneResetTime": float(w["reset_s"]), "zoneShowOnEnter": 0, "zoneShowOnWin": 0,
                  "zoneEnableAirborneAIAircraft": 0,
                  "aTeamFaction": team_faction(factions[a], w.get("faction_names", "interim")),
                  "aTeamLoadout": f"DZDS_{a}",
                  "aTeamSpawnPosition": _ring(zn, w["spawn_offset_m"], 0.0, y),
                  "bTeamFaction": team_faction(factions[b], w.get("faction_names", "interim")),
                  "bTeamLoadout": f"DZDS_{b}",
                  "bTeamSpawnPosition": _ring(zn, w["spawn_offset_m"], math.pi, y)})
        for k, v in z.items():
            if k.startswith("zone") and "Message" in k and isinstance(v, str):
                z[k] = ""
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


def route_plan(war_party: dict | None, recorded_dir: Path,
               existing: dict[str, dict], routes_dir_exists: bool = True) -> tuple[bool, dict[str, dict]]:
    """(convoy_enabled, files_to_write). Never deletes: stock routes are rewritten Enabled 0."""
    want: dict[str, dict] = {}
    if war_party and war_party["kind"] == "convoy" and not routes_dir_exists:
        print("ERROR: Routes/ folder missing on the server mirror; convoys stay off")
        return False, {}
    if war_party and war_party["kind"] == "convoy":
        src = recorded_dir / war_party["route"]
        if src.exists():
            route = json.loads(src.read_text())
            route["Enabled"] = 1
            want[war_party["route"]] = route
        else:
            print(f"ERROR: convoy route {war_party['route']} not recorded; convoys stay off")
    writes = {}
    for name, body in existing.items():
        if name not in want and body.get("Enabled") != 0:
            writes[name] = {**body, "Enabled": 0}
    for name, body in want.items():
        if existing.get(name) != body:
            writes[name] = body
    return bool(want), writes


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
    from gamemaster.ledger import WarLedger
    cfg, mp = load_cfg(), active.map_data()
    led = WarLedger.load_or_new(active.map_name(), initial=a.initial)
    zs = zmod.build(mp, led.s.control, led.locations())
    groups_file = active.mission_dir() / "mapgrouppos.xml"
    groups = map_survey.load_groups(groups_file) if groups_file.exists() else []
    y = ground_mod.Ground(groups, ground_mod.adm_samples(sorted(PROFILES.glob("*.ADM"))))
    roles = {s: led.site_roles(s) for s in led.s.control}
    d = a.dry_run
    _rw(PROFILES / "Airdrop" / "AirdropSettings.json", lambda s: airdrop(s, zs, cfg, y), d)
    _rw(PROFILES / "_DynamicHelicopters" / "DynamicHelicopterConfig.json", lambda s: heli(s, zs, cfg, y), d)
    _rw(PROFILES / "Bastardo_HC" / "BS_Dynamic_crates.json", lambda s: crates(s, zs, cfg, y), d)
    _rw(PROFILES / "Bastardo_HC" / "BS_Static_crates.json", lambda s: [], d)
    _rw(PROFILES / "AIWarZones" / "AIWarZones_Settings.json",
        lambda s: warzones(s, zs, led.s.strength, led.fspec, roles, cfg, y), d)
    routes_dir = PROFILES / "AIConvoy" / "Routes"
    existing = {f.name: json.loads(f.read_text()) for f in sorted(routes_dir.glob("*.json"))} \
        if routes_dir.exists() else {}
    if not routes_dir.exists():
        print(f"  WARNING: {routes_dir.relative_to(ROOT)} missing; stock routes cannot be disabled")
    on, writes = route_plan(led.s.war_party, ROOT / "presets" / "convoy_routes" / active.map_name(), existing,
                        routes_dir.exists())
    _rw(PROFILES / "AIConvoy" / "AIConvoySettings.json",
        lambda s: convoy(s, led.s.war_party if on else None, cfg), d)
    for name, body in writes.items():
        if not d:
            (routes_dir / name).write_text(json.dumps(body, indent=4) + "\n")
        print(f"  route {name} Enabled={body['Enabled']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
