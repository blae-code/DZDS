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
