import math
import random
import re
import xml.etree.ElementTree as ET

import pytest
import yaml

import active
import arrivals

INIT_C = active.mission_dir("nasdara") / "init.c"
ROOT = active.ROOT


@pytest.fixture(scope="module")
def built():
    cfg = yaml.safe_load(arrivals.PRESET.read_text())
    map_data = active.map_data("nasdara")
    return cfg, map_data, arrivals.build(cfg, map_data, arrivals.mission_dir(map_data))


def test_every_arrival_site_snaps_to_a_road_spot(built):
    cfg, map_data, out = built
    for name, (x, z) in map_data["arrival_sites"].items():
        pts = [p for p in out["ArrivalSites"] if p["Name"] == name]
        assert pts, name
        assert all(math.dist((p["X"], p["Z"]), (x, z)) <= cfg["snap_radius_m"] for p in pts), name


def test_no_road_respawn_inside_an_exclusion_zone(built):
    cfg, map_data, out = built
    zones = arrivals.exclusion_zones(cfg, map_data)
    assert zones
    for p in out["RoadPoints"]:
        assert not arrivals.excluded((p["X"], p["Z"]), zones), p


def test_arrival_sites_stay_out_of_war_locations():
    """Arrival villages must not leak into the war ledger, site markers or the GM."""
    map_data = active.map_data("nasdara")
    assert not set(map_data["arrival_sites"]) & set(map_data["locations"])


def test_json_keys_match_init_c_classes(built):
    """init.c deserialises arrivals.json into RefugeeArrival* classes; a renamed key would
    silently load as 0/null in game, so every emitted key must be a field there."""
    _, _, out = built
    src = INIT_C.read_text()
    body = re.search(r"class RefugeeArrivalConfig\s*\{(.*?)\n\}", src, re.S).group(1)
    fields = set(re.findall(r"\b(\w+);", body))
    assert set(out) <= fields, set(out) - fields
    point = re.search(r"class RefugeeArrivalPoint\s*\{(.*?)\n\}", src, re.S).group(1)
    assert set(out["RoadPoints"][0]) <= set(re.findall(r"\b(\w+);", point))


def test_init_main_is_vanilla():
    """Our block must not change Bohemia's main() (economy init, date reset)."""
    ours, vanilla = INIT_C.read_text(), (INIT_C.parent / "init.c.vanilla").read_text()
    grab = lambda s: re.search(r"void main\(\)\s*\{.*?\n\}", s, re.S).group(0)  # noqa: E731
    assert grab(ours) == grab(vanilla)


def test_start_kit_is_compiled(built):
    cfg, _, out = built
    assert out["RadioFrequencyIndex"] == cfg["radio"]["settler_net_index"] >= 0
    assert out["GiveRoadflare"] == 1


def test_init_c_gives_radio_battery_and_flare():
    src = INIT_C.read_text()
    kit = re.search(r"static void GiveStartKit\(.*?\n\t\}", src, re.S).group(0)
    for needle in ('"PersonalRadio"', '"Battery9V"', "SetFrequencyByIndex", '"Roadflare"'):
        assert needle in kit, needle
    assert "CreateInHands" in kit and "radio NOT created" in kit
    assert "SwitchOn" not in kit                       # ships switched OFF (spec §6.1)
    setup = re.search(r"override void StartingEquipSetup\(.*?\n\t\}", src, re.S).group(0)
    assert "GiveStartKit" in setup


def test_voice_quality_max():
    cfg = (arrivals.ROOT / "config" / "local_serverDZ.cfg").read_text()
    assert re.search(r"^vonCodecQuality\s*=\s*30;", cfg, re.M)


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


def test_unknown_classname_is_rejected(built):
    cfg, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    bad["archetypes"]["deserter"]["slots"]["food"]["items"].append("NotARealItem")
    with pytest.raises(SystemExit, match="NotARealItem"):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_archetype_weights(built):
    _, _, out = built
    ground = {a["Name"]: a["Weight"] for a in out["Archetypes"] if not a["Aircraft"]}
    pilots = {a["Name"]: a["Weight"] for a in out["Archetypes"] if a["Aircraft"]}
    assert ground == {"deserter": 30.0, "trucker": 25.0, "nomad": 25.0, "townie": 20.0}
    assert pilots == {"bush_pilot": 60.0, "combat_pilot": 40.0}


CUTTING = {
    "CombatKnife", "KitchenKnife", "HuntingKnife",
    "FangeKnife", "M9A1_Bayonet", "AK_Bayonet", "SKS_Bayonet",
    "SteakKnife", "Cleaver", "KukriKnife", "Jambiya", "DonerKnife",
}
CAR = {
    "TireRepairKit", "Wrench", "Screwdriver", "Pliers", "SparkPlug", "EpoxyPutty",
    "LugWrench", "GlowPlug", "HeadlightH7_Box", "ElectronicRepairKit",
}
CAMP = {
    "Matchbox", "PetrolLighter", "Pot", "FryingPan", "PortableGasStove",
    "SmallGasCanister", "MediumGasCanister", "PortableGasLamp", "Rope", "Tripod",
    "CeramicPot_White", "CeramicPot_Gray", "CeramicPot_Black", "CeramicPot_Natural",
}
AIRFRAME = {
    "EpoxyPutty", "DuctTape", "TireRepairKit", "Pliers", "Screwdriver", "Wrench", "ElectronicRepairKit",
}   # a pilot's "car" slot


def _slot(arch, name):
    return next(s for s in arch["Slots"] if s["Name"] == name)


def test_simulated_kits_meet_the_spec(built):
    """Blae 2026-10-16: every kit has a knife, one car item and one camp item."""
    _, _, out = built
    rng = random.Random(7)
    for arch in out["Archetypes"]:
        food = set(_slot(arch, "food")["Items"])
        weapons = {f["WeaponClass"] for f in arch["Firearms"]}
        for _ in range(1000):
            kit = arrivals.simulate_kit(arch, rng)
            assert kit[0] in weapons, "the firearm spawns first, so a full trunk can't crowd it out"
            items = [k for k in kit if k not in weapons and not k.startswith(("Ammo_", "Mag_"))]
            lo, hi = (18, 26) if arch["Aircraft"] else (12, 17)   # pilots add pack, survival, fuel, signal...
            assert lo <= len(items) <= hi, (arch["Name"], kit)
            for name in set(items):
                cap = 2 if name in food else 1
                assert items.count(name) <= cap, (arch["Name"], name)
            assert sum(k in weapons for k in kit) == 1
            assert sum(k in CUTTING for k in items) == 1, (arch["Name"], kit)
            assert sum(k in (AIRFRAME if arch["Aircraft"] else CAR) for k in items) >= 1, (arch["Name"], kit)
            assert sum(k in CAMP for k in items) >= 1, (arch["Name"], kit)


def test_knife_car_and_camp_slots_are_guaranteed(built):
    _, _, out = built
    for arch in out["Archetypes"]:
        car = AIRFRAME if arch["Aircraft"] else CAR
        for name, pool in (("knife", CUTTING), ("car", car), ("camp", CAMP)):
            s = _slot(arch, name)
            assert s["Min"] == s["Max"] == 1, (arch["Name"], name)
            assert set(s["Items"]) <= pool, (arch["Name"], name, set(s["Items"]) - pool)


def test_firearms_get_magazine_and_spare_rounds(built):
    """Blae 2026-10-16: a pistol arrives with its magazine (3-6 rounds) plus 4-8 spare rounds;
    a gun without a magazine gets 6-12 loose rounds."""
    _, map_data, out = built
    spawn = ET.parse(arrivals.mission_dir(map_data) / "cfgspawnabletypes.xml").getroot()
    for arch in out["Archetypes"]:
        for f in arch["Firearms"]:
            assert f["Ammo"], f
            if f["MagazineClass"]:
                assert (f["RoundsMin"], f["RoundsMax"]) == (3, 6), f
                assert (f["SpareMin"], f["SpareMax"]) == (4, 8), f
                t = spawn.find(f"type[@name='{f['WeaponClass']}']")
                if t is not None:
                    mags = {i.get("name") for i in t.iter("item")}
                    assert f["MagazineClass"] in mags, f
            else:
                assert (f["RoundsMin"], f["RoundsMax"]) == (6, 12), f
                assert f["SpareMax"] == 0, f


def test_init_c_fill_cargo_uses_archetypes():
    src = INIT_C.read_text()
    fill = re.search(r"int FillCargo\(CarScript car, bool aircraft, RefugeeArrivalArchetype forced = null\).*?\n\t\}", src, re.S).group(0)
    for needle in ("PickArchetype(aircraft)", "ServerSetAmmoCount(", "SpareMin", "SpareMax"):
        assert needle in src, needle
    assert "PickGear()" not in src
    assert "FillSlot(" in fill and "GiveFirearm(" in fill
    assert fill.index("GiveFirearm(") < fill.index("FillSlot("), "firearm must spawn before the slots"


def test_init_c_puts_the_magazine_in_cargo_not_on_the_gun():
    """2026-10-16 first live arrival: the Makarov's attached magazine never reached the player.
    The magazine now goes in the cargo like every other item, and the firearm line is logged
    on its own (the one-line kit list is truncated by the engine)."""
    src = INIT_C.read_text()
    assert "SpawnAttachedMagazine(" not in src
    assert '"[DZDS Arrivals] firearm "' in src


def test_firearm_fields_do_not_shadow_engine_types(built):
    """1.30 boot: `string Weapon;` in init.c is a compile error ("Variable name 'Weapon' already
    used as type name"), and so is `Magazine`. JsonFileLoader maps keys to field names, so the
    JSON keys must avoid engine type names too."""
    _, _, out = built
    for arch in out["Archetypes"]:
        for f in arch["Firearms"]:
            assert set(f) == {"WeaponClass", "MagazineClass", "Ammo", "RoundsMin", "RoundsMax",
                              "SpareMin", "SpareMax"}, f
    init = (arrivals.mission_dir(built[1]) / "init.c").read_text()
    for engine_type in ("Weapon", "Magazine", "Ammunition_Base", "Weapon_Base", "ItemBase", "Car"):
        assert not re.search(rf"^\s*(?:ref\s+)?\w+(?:<[^>]*>)?\s+{engine_type}\s*;", init, re.M), engine_type


def test_firearm_json_keys_are_init_c_fields(built):
    """JsonFileLoader fills fields by name and silently skips unknown keys, so a key init.c
    doesn't declare would arrive empty in game (the line only prints once a player joins)."""
    _, map_data, out = built
    init = (arrivals.mission_dir(map_data) / "init.c").read_text()
    body = re.search(r"class RefugeeArrivalFirearm\s*\{(.*?)\}", init, re.S).group(1)
    fields = set(re.findall(r"\b(?:string|int|float)\s+(\w+)\s*;", body))
    for arch in out["Archetypes"]:
        for f in arch["Firearms"]:
            assert set(f) == fields, (set(f) ^ fields)


def test_camp_respawn_is_compiled(built):
    """Blae 2026-10-16: a respawn wakes at the pitched tent nearest the death, within range."""
    cfg, _, out = built
    assert out["CampRespawnRadius"] == float(cfg["camp_respawn_m"]) == 5000.0
    assert 2.0 <= out["CampPlayerOffset"] <= 6.0


def test_dzds_mod_registers_pitched_tents():
    """Tents register on EEInit (pitch, or load from persistence) and leave on EEDelete, so a
    respawn never scans the world. This lives in @DZDS: init.c cannot mod a 4_World class
    (1.30 local boot: "Unknown type 'TentBase'")."""
    mod = ROOT / "mods" / "DZDS"
    src = (mod / "Scripts" / "4_World" / "DZDS" / "DZDSCamps.c").read_text()
    tent = re.search(r"modded class TentBase\s*\{(.*?)\n\}", src, re.S)
    assert tent, "@DZDS must mod TentBase to keep the camp list"
    assert re.search(r"void EEInit\(\).*?DZDSCamps\.Add\(this\)", tent.group(1), re.S)
    assert re.search(r"void EEDelete\(EntityAI parent\).*?DZDSCamps\.Remove\(this\)", tent.group(1), re.S)
    assert re.search(r'defines\[\]\s*=\s*\{\s*"DZDS_CAMPS"', (mod / "config.cpp").read_text())
    init = INIT_C.read_text()
    assert "modded class" not in init
    assert "GetObjectsAtPosition" not in init
    # init.c must still compile against an @DZDS without camps (upload lag): every use is guarded.
    for m in re.finditer(r"DZDSCamps\.", init):
        before = init[:m.start()]
        assert before.rfind("#ifdef DZDS_CAMPS") > before.rfind("#endif"), "unguarded DZDSCamps use"


def test_init_c_camp_respawn_comes_first_and_grants_no_car():
    src = INIT_C.read_text()
    plan = re.search(r"RefugeeArrivalPlan Plan\(PlayerIdentity identity\).*?\n\t\}", src, re.S).group(0)
    assert "PickCamp(plan, rec)" in plan
    assert plan.index("PickCamp(plan, rec)") < plan.index("PickNearDeath(plan, rec)")
    camp = re.search(r"bool PickCamp\(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec\).*?\n\t\}", src, re.S)
    assert camp, "PickCamp missing"
    body = camp.group(0)
    for needle in ("rec.HasDeath", "TentBase.PITCHED", "m_Config.CampRespawnRadius", "plan.GrantVehicle = false",
                   "plan.AtCamp = true"):
        assert needle in body, needle


def test_init_c_redraws_a_vehicle_that_fits_nowhere():
    """Blae 2026-10-16: transport helicopters are in the pool; one that fits no spot near the
    respawn must not cost the player their vehicle, so Plan draws again before giving up."""
    src = INIT_C.read_text()
    plan = re.search(r"RefugeeArrivalPlan Plan\(PlayerIdentity identity\).*?\n\t\}", src, re.S).group(0)
    redraw = re.search(r"for \(int r = 0; r < VEHICLE_REDRAWS && !placed && plan\.GrantVehicle; r\+\+\)(.*?)\n\t\t\}", plan, re.S)
    assert redraw, "no vehicle re-draw loop in Plan"
    assert "plan.Vehicle = PickVehicle(only);" in redraw.group(1)
    assert plan.index("VEHICLE_REDRAWS") < plan.rindex("plan.GrantVehicle = false;"), "re-draw before giving up"


def test_init_c_vehicle_selftest_is_local_only():
    """The self-test spawns every configured vehicle through the real SpawnVehicle + FillCargo
    path, but only when $profile:DZDS/vehicle_selftest exists (never on the live server)."""
    src = INIT_C.read_text()
    body = re.search(r"void VehicleSelfTest\(\).*?\n\t\}", src, re.S)
    assert body, "VehicleSelfTest missing"
    for needle in ("ExpansionItemSpawnHelper.SpawnVehicle(", "FillCargo(", "ObjectDelete(", "[DZDS VehicleTest]"):
        assert needle in body.group(0), needle
    assert re.search(r'SELFTEST\s*=\s*DIR \+ "\\\\vehicle_selftest"', src)
    mission = re.search(r"class CustomMission: MissionServer.*", src, re.S).group(0)
    assert re.search(r"if \(FileExist\(RefugeeArrivals\.SELFTEST\)\)", mission)
    gi = (ROOT / ".gitignore").read_text()
    assert "server/profiles/DZDS/vehicle_selftest" in gi


def test_init_c_spills_kit_that_does_not_fit_beside_the_vehicle():
    """2026-10-16 self-test: the gyrocopter and R22 have no cargo, the tractor holds ~10 items.
    Whatever the cargo can't take is placed on the ground beside the vehicle, never lost."""
    src = INIT_C.read_text()
    spawn = re.search(r"EntityAI Spawn\(CarScript car, string cls, float hmin, float hmax\).*?\n\t\}", src, re.S).group(0)
    assert "SpillBeside(car, cls)" in spawn
    rounds = re.search(r"void GiveRounds\(CarScript car, string cls, int rounds, TStringArray got\).*?\n\t\}", src, re.S).group(0)
    assert "SpillBeside(car, cls)" in rounds
    fill = re.search(r"int FillCargo\(CarScript car, bool aircraft, RefugeeArrivalArchetype forced = null\).*?\n\t\}", src, re.S).group(0)
    assert "if (!car.GetInventory().GetCargo())" not in fill, "a vehicle without cargo must still get its kit"


def test_vehicle_selftest_attaches_parts_one_by_one():
    """The first self-test passed no player to SpawnVehicle, so Expansion never attached the
    parts (617 VM exceptions). Parts are now attached one by one and each failure is named."""
    src = INIT_C.read_text()
    body = re.search(r"void VehicleSelfTest\(\).*?\n\t\}", src, re.S).group(0)
    assert "GetInventory().CreateAttachment(" in body
    assert re.search(r"SpawnVehicle\([^;]*, NULL, -1, \"\", notAttached\)", body), "spawn without parts, then attach"


def test_init_c_spot_selftest_is_local_only():
    """Plane parking at the airfield (Blae 2026-10-16) is validated on the local server:
    $profile:DZDS/spot_selftest.json lists candidate spots and classes; each is checked with
    Expansion's collision-box test and a slope check. Never present on the live server."""
    src = INIT_C.read_text()
    body = re.search(r"void SpotSelfTest\(\).*?\n\t\}", src, re.S)
    assert body, "SpotSelfTest missing"
    for needle in ("IsSpawnPositionFree(", "GetCollisionBox(", "[DZDS SpotTest]", "SPOTTEST"):
        assert needle in src, needle
    assert re.search(r'SPOTTEST\s*=\s*DIR \+ "\\\\spot_selftest\.json"', src)
    mission = re.search(r"class CustomMission: MissionServer.*", src, re.S).group(0)
    assert "FileExist(RefugeeArrivals.SPOTTEST)" in mission
    assert "server/profiles/DZDS/spot_selftest.json" in (ROOT / ".gitignore").read_text()


AIRCRAFT = {"ExpansionMh6", "ExpansionGyrocopter", "EXT_MH6", "RFFSHeli_R22", "RFFSHeli_LittleBird",
            "ExpansionUh1h", "EXT_Mi8_Civilian", "EXT_UH1Y", "RFFSHeli_UH1H"}


def test_trailer_and_nav_kit_are_compiled(built):
    """Blae 2026-10-17: a towing vehicle comes with a trailer; every 24 h a new character gets a
    paper map and a working GPS (the walkie-talkie already comes with every character)."""
    cfg, _, out = built
    assert out["NavKitHours"] == 24
    assert {"ChernarusMap", "GPSReceiver"} <= set(out["NavKit"])
    assert cfg["trailer"]["class"] == "DZT_UtilityTrailer"   # TrailerClass is "" while trailers are off"
    assert out["TrailerParts"].count("HatchbackWheel") == 2
    flags = {v["ClassName"]: v["Trailer"] for v in out["Vehicles"]}
    assert {c for c, f in flags.items() if f == 0} == AIRCRAFT
    point = re.search(r"class RefugeeArrivalVehicle\s*\{(.*?)\n\}", INIT_C.read_text(), re.S).group(1)
    assert set(out["Vehicles"][0]) <= set(re.findall(r"\b(\w+);", point))


def test_trailer_skip_must_name_a_vehicle(built):
    cfg, map_data, _ = built
    bad = {**cfg, "trailer": {**cfg["trailer"], "skip": ["NoSuchHeli"]}}
    with pytest.raises(SystemExit, match="NoSuchHeli"):
        arrivals.validate(bad, arrivals.known_types(arrivals.mission_dir(map_data)))


def test_init_c_trailer_follows_the_trailer_mods_hitch_rule():
    src = INIT_C.read_text()
    body = re.search(r"string GiveTrailer\(CarScript car, RefugeeArrivalVehicle v, out Object trailerObj\).*?\n\t\}", src, re.S).group(0)
    for needle in ("v.Trailer != 1", "DZT_HitchProfile.Get(car, hitch)", "IsSpawnPositionFree(",
                   '"dzt_coupler"', "GetInventory().CreateAttachment(part)", "SetPosition("):
        assert needle in body, needle
    assert re.search(r'SpawnVehicle\(m_Config\.TrailerClass, null, [^;]*NULL, -1, "", notAttached\)', body)
    deliver = re.search(r"void Deliver\(PlayerBase player, RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    assert "GiveTrailer(car, plan.Vehicle, trailerObj)" in deliver
    test = re.search(r"void VehicleSelfTest\(\).*?\n\t\}", src, re.S).group(0)
    assert "GiveTrailer(car, v, trailerObj)" in test and "ObjectDelete(trailerObj)" in test


def test_init_c_nav_kit_once_per_cooldown():
    src = INIT_C.read_text()
    kit = re.search(r"string GiveNavKit\(PlayerBase player, CarScript car\).*?\n\t\}", src, re.S).group(0)
    for needle in ("CreateInInventory(cls)", "CreateInVehicle(car, cls)", "ECE_PLACE_ON_SURFACE",
                   '"Battery9V"', "SwitchOn()"):
        assert needle in kit, needle
    deliver = re.search(r"void Deliver\(PlayerBase player, RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    assert "now - rec.LastNavKit >= m_Config.NavKitHours * 3600" in deliver
    assert "rec.LastNavKit = now;" in deliver and "GiveNavKit(player, car)" in deliver
    record = re.search(r"class RefugeeArrivalRecord\s*\{(.*?)\n\}", src, re.S).group(1)
    assert "int LastNavKit;" in record


def test_trailers_are_off_and_cleared_from_the_world(built):
    """Blae 2026-10-17: trailers crash the server (Expansion AI's eAIDamageHandler calls
    CrewMember(DRIVER) on the driverless trailer when it hits an infected). Arrivals hand out
    none (an empty TrailerClass makes GiveTrailer return early) and init.c removes any left."""
    cfg, _, out = built
    assert cfg["trailer"]["enabled"] is False and out["TrailerClass"] == ""
    src = INIT_C.read_text()
    assert 'm_Config.TrailerClass == ""' in src
    assert "CallLater(ClearTrailers, 20000, false)" in src and "CallLater(ClearTrailers, 120000, true)" in src
    body = re.search(r"void ClearTrailers\(\).*?\n\t\}", src, re.S).group(0)
    for needle in ("DZT_UtilityTrailer.Cast(", "node = node.m_Next;", "ThrowAllItemsInInventory(trailer",
                   "ObjectDelete(trailer)"):
        assert needle in body, needle
    assert body.index("node = node.m_Next;") < body.index("ObjectDelete(trailer)")   # advance before delete


AIRCRAFT = {"ExpansionMh6", "ExpansionGyrocopter", "EXT_MH6", "RFFSHeli_R22", "RFFSHeli_LittleBird",
            "ExpansionUh1h", "EXT_Mi8_Civilian", "EXT_UH1Y", "RFFSHeli_UH1H"}
BLAE_ID = "eEbDg86Qv3w5T_ZJj-9b9BriMPuvigsufukc_oCLOAQ="


def test_blae_is_favored_with_every_aircraft_that_holds_a_kit(built):
    """Blae 2026-10-21: the server owner's vehicle is always an aircraft. 2026-10-22: one whose
    inventory holds the pilot kit, so not the gyrocopter (5x2 cargo, no flight-case slot).
    2026-10-24: and not a RedFalcon heli, whose SyncedValue inputs make his VKB sticks stutter."""
    _, _, out = built
    fav = {f["Id"]: f for f in out["Favored"]}
    assert set(fav[BLAE_ID]["Vehicles"]) == EXPANSION_HELIS - {"ExpansionGyrocopter"}
    assert AIRCRAFT <= {v["ClassName"] for v in out["Vehicles"]}


def test_favored_vehicle_must_be_in_the_pool(built):
    _, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    bad["favored"][0]["vehicles"].append("UAZ_452")
    with pytest.raises(SystemExit, match="UAZ_452"):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_favored_json_keys_are_init_c_fields(built):
    _, _, out = built
    body = re.search(r"class RefugeeArrivalFavored\s*\{(.*?)\n\}", INIT_C.read_text(), re.S).group(1)
    assert set(out["Favored"][0]) <= set(re.findall(r"\b(\w+);", body))


def test_init_c_favored_pool_on_every_draw_and_cooldown_unchanged():
    """Blae 2026-10-21: the favored pool restricts WHICH vehicle, never WHETHER: the 24 h
    cooldown still applies, and the redraw loop keeps drawing from the same pool."""
    src = INIT_C.read_text()
    plan = re.search(r"RefugeeArrivalPlan Plan\(PlayerIdentity identity\).*?\n\t\}", src, re.S).group(0)
    assert "TStringArray only = FavoredVehicles(plan.Uid);" in plan
    assert plan.count("PickVehicle(only)") == 2 and "PickVehicle()" not in plan
    assert "NowSeconds() - rec.LastVehicle < m_Config.CooldownHours * 3600)\n\t\t\tplan.GrantVehicle = false;" in plan
    pick = re.search(r"RefugeeArrivalVehicle PickVehicle\(TStringArray only = null\).*?\n\t\}", src, re.S).group(0)
    assert "only.Find(v.ClassName)" in pick and "only.Find(w.ClassName)" in pick
    assert "if (total <= 0)" in pick, "an unmatched list must fall back to the whole pool"
    assert "!m_Config.Favored" in src, "older arrivals.json without Favored must still load"


# Slot -> item for every attachment slot each aircraft's config.bin declares (read from the
# mods 2026-10-22), beyond the flight parts it already had. Tac_Radio has no item in any
# loaded mod, so it is the one slot left empty.
EXPANSION_HELIS = {"ExpansionMh6", "ExpansionGyrocopter", "EXT_MH6", "ExpansionUh1h", "EXT_Mi8_Civilian", "EXT_UH1Y"}
EXPANSION_SLOT_GEAR = {"CamoNetDesert", "ExpansionKeyChain_Black", "Wrench", "CanisterGasoline"}
RFFS_HELIS = {"RFFSHeli_R22", "RFFSHeli_LittleBird", "RFFSHeli_UH1H"}


def test_aircraft_arrive_with_every_slot_filled(built):
    """Blae 2026-10-22: an aircraft comes "with the requisite gear in all attachments": camo net,
    key chain, wrench and jerrycan in an Expansion heli's own slots; the flight storage case
    (its inventory) on a RedFalcon heli."""
    cfg, _, out = built
    assert EXPANSION_HELIS | RFFS_HELIS == AIRCRAFT == set(cfg["aircraft"])
    parts = {v["ClassName"]: v["Parts"] for v in out["Vehicles"]}
    for cls in EXPANSION_HELIS:
        assert EXPANSION_SLOT_GEAR <= set(parts[cls]), cls
    for cls in RFFS_HELIS:
        assert parts[cls].count("RFFSHeli_flight_case_red") == 1, cls
    assert out["UnfillableSlots"] == ["Tac_Radio"]
    assert out["FuelCans"] == ["CanisterGasoline"]


def test_aircraft_flag_and_fuel_are_compiled(built):
    cfg, _, out = built
    for v in out["Vehicles"]:
        assert v["Aircraft"] == int(v["ClassName"] in AIRCRAFT), v["ClassName"]
    assert out["FuelMax"] < out["AircraftFuelMin"] <= out["AircraftFuelMax"] <= 1


def test_pilot_profiles_carry_fuel_signal_and_a_firearm(built):
    """Every pilot kit has exactly one full jerrycan, one signal item and one firearm."""
    _, _, out = built
    rng = random.Random(11)
    pilots = [a for a in out["Archetypes"] if a["Aircraft"]]
    assert {a["Name"] for a in pilots} == {"bush_pilot", "combat_pilot"}
    for arch in pilots:
        signal = set(_slot(arch, "signal")["Items"])
        for _ in range(500):
            kit = arrivals.simulate_kit(arch, rng)
            assert kit.count("CanisterGasoline") == 1, kit
            assert sum(k in signal for k in kit) == 1, kit
    ground = [a for a in out["Archetypes"] if not a["Aircraft"]]
    assert all({s["Name"] for s in a["Slots"]} == set(arrivals.SLOT_ORDER) for a in ground)


def test_aircraft_without_a_pilot_profile_is_rejected(built):
    _, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    for name in ("bush_pilot", "combat_pilot"):
        del bad["archetypes"][name]
    with pytest.raises(SystemExit, match="pilot profile"):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_vehicle_and_archetype_json_keys_are_init_c_fields(built):
    _, _, out = built
    src = INIT_C.read_text()
    for cls, rows in (("RefugeeArrivalVehicle", out["Vehicles"]), ("RefugeeArrivalArchetype", out["Archetypes"])):
        body = re.search(rf"class {cls}\s*\{{(.*?)\n\}}", src, re.S).group(1)
        assert set(rows[0]) <= set(re.findall(r"\b(\w+);", body)), cls


def test_init_c_aircraft_get_pilot_profiles_fuel_and_full_cans():
    src = INIT_C.read_text()
    pick = re.search(r"RefugeeArrivalArchetype PickArchetype\(bool aircraft\).*?\n\t\}", src, re.S).group(0)
    assert "a.Aircraft == want" in pick and "b.Aircraft != want" in pick
    deliver = re.search(r"void Deliver\(PlayerBase player, RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    for needle in ("AircraftFuelMin", "TopUpAttached(car)", "FillCargo(car, aircraft, OutfitCargo(plan.Outfit, aircraft))"):
        assert needle in deliver, needle
    test = re.search(r"void VehicleSelfTest\(\).*?\n\t\}", src, re.S).group(0)
    assert "FillCargo(car, v.Aircraft == 1)" in test and "UnfillableSlots" in test
    top = re.search(r"void TopUp\(EntityAI item\).*?\n\t\}", src, re.S).group(0)
    assert "SetLiquidType(LIQUID_GASOLINE)" in top and "SetQuantityMax()" in top


def test_init_c_kit_goes_into_attached_cargo_before_the_ground():
    """The R22's own cargo is 0x0: its kit belongs in the flight storage case attached to it."""
    src = INIT_C.read_text()
    inv = re.search(r"static EntityAI CreateInVehicle\(CarScript car, string cls\).*?\n\t\}", src, re.S).group(0)
    assert "GetAttachmentFromIndex(i)" in inv and "att.GetInventory().CreateEntityInCargo(cls)" in inv
    for fn in (r"EntityAI Spawn\(CarScript car, string cls, float hmin, float hmax\)",
               r"void GiveRounds\(CarScript car, string cls, int rounds, TStringArray got\)",
               r"string GiveNavKit\(PlayerBase player, CarScript car\)"):
        body = re.search(fn + r".*?\n\t\}", src, re.S).group(0)
        assert "CreateInVehicle(car, cls)" in body, fn
        assert "car.GetInventory().CreateEntityInCargo(" not in body, fn


def test_init_c_player_never_wakes_on_the_vehicle_spot():
    """2026-10-22: both respawns stood the player ON the vehicle's spot and Blae's R22 hit him.
    Water is the engine's sea/pond test, and no path puts the player at CarPos."""
    src = INIT_C.read_text()
    water = re.search(r"static bool IsWater\(float x, float z\).*?\n\t\}", src, re.S).group(0)
    assert "SurfaceIsSea(x, z)" in water and "SurfaceIsPond(x, z)" in water
    assert "SurfaceGetType" not in water
    place = re.search(r"void PlacePlayer\(RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    assert "plan.PlayerPos = plan.CarPos" not in place


PACKS = {
    "MountainBag_Green", "MountainBag_Orange", "MountainBag_Blue", "MountainBag_Red",
    "HuntingBag", "DryBag_Orange", "DryBag_Yellow", "DryBag_Green", "CanvasBag_Olive",
    "AssaultBag_Desert", "AssaultBag_Ttsko", "AssaultBag_Black", "AssaultBag_Green",
    "CoyoteBag_Desert", "CoyoteBag_Brown", "CoyoteBag_Green", "TortillaBag_Desert", "AliceBag_Camo",
}


def test_pilots_carry_a_pack_and_survival_kit(built):
    """Blae 2026-10-22: pilots get "packs and survival equipment they would have access to
    because of their profession": exactly one pack, 2-3 survival items, the bush pilot a rod
    AND its hook, the combat pilot a survival vest. Ground kits are unchanged."""
    _, _, out = built
    rng = random.Random(5)
    pilots = {a["Name"]: a for a in out["Archetypes"] if a["Aircraft"]}
    for arch in pilots.values():
        names = [s["Name"] for s in arch["Slots"]]
        assert names[:len(arrivals.SLOT_ORDER)] == arrivals.SLOT_ORDER, "standard slots first"
        survival = set(_slot(arch, "survival")["Items"])
        assert "FirstAidKit" in survival and "PurificationTablets" in survival, arch["Name"]
        for _ in range(500):
            kit = arrivals.simulate_kit(arch, rng)
            assert sum(k in PACKS for k in kit) == 1, kit
            assert 2 <= sum(k in survival for k in kit) <= 3, kit
            if arch["Name"] == "bush_pilot":
                assert "FishingRod" in kit and "Hook" in kit, kit
            if arch["Name"] == "combat_pilot":
                assert sum(k in set(_slot(arch, "vest")["Items"]) for k in kit) == 1, kit
    ground = [a for a in out["Archetypes"] if not a["Aircraft"]]
    assert ground and all(not {"pack", "vest", "survival", "fishing"} & {s["Name"] for s in a["Slots"]} for a in ground)


def test_pilot_item_pools_are_disjoint(built):
    """No item appears in two slots of one archetype, so a kit never holds a duplicate."""
    cfg, _, _ = built
    for name, a in cfg["archetypes"].items():
        seen: dict[str, str] = {}
        for slot, s in a["slots"].items():
            for item in s["items"]:
                assert item not in seen, (name, item, seen.get(item), slot)
                seen[item] = slot


def test_unknown_slot_is_rejected(built):
    """archetypes() compiles only known slot names: a typo'd slot must fail, not vanish."""
    _, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    bad["archetypes"]["bush_pilot"]["slots"]["survivl"] = {"count": [1, 1], "items": ["Heatpack"]}
    with pytest.raises(SystemExit, match="unknown slot"):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_near_players_and_base_respawn_are_compiled(built):
    """Blae 2026-10-22: respawn within 1 km of the others (else 2 km), and at the base."""
    _, _, out = built
    assert (out["RespawnNearPlayersMin"], out["RespawnNearPlayersMax"]) == (1000.0, 2000.0)
    assert out["BaseRespawn"] == 1 and out["BasePlayerOffset"] > 0


def test_init_c_respawn_order_is_friends_base_camp_death():
    """Blae chose "friend first": near players, then base, then camp, then near the death."""
    src = INIT_C.read_text()
    plan = re.search(r"RefugeeArrivalPlan Plan\(PlayerIdentity identity\).*?\n\t\}", src, re.S).group(0)
    order = [plan.index(f) for f in ("PickColumnPoint(plan)", "PickNearPlayers(plan)", "PickBase(plan, rec)",
                                     "PickCamp(plan, rec)", "PickNearDeath(plan, rec)")]
    assert order == sorted(order), order
    redraw = plan[plan.index("VEHICLE_REDRAWS"):]
    assert redraw.index("PickNearPlayers(plan)") < redraw.index("PickNearDeath(plan, rec)"), \
        "a big heli that fits nowhere near the others must be redrawn near them first"
    near = re.search(r"bool PickNearPlayers\(RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    for needle in ("GetGame().GetPlayers(", "IsAlive()", "GetId() == plan.Uid", "RespawnNearPlayersMin", "RespawnNearPlayersMax"):
        assert needle in near, needle
    base = re.search(r"bool PickBase\(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec\).*?\n\t\}", src, re.S).group(0)
    assert "#ifdef DZDS_BASES" in base and "plan.GrantVehicle = false" in base


def test_dzds_mod_tracks_territory_flags():
    """init.c's base respawn needs @DZDS's DZDSBases registry and the DZDS_BASES define."""
    mod = ROOT / "mods" / "DZDS"
    assert '"DZDS_BASES"' in (mod / "config.cpp").read_text()
    src = (mod / "Scripts" / "4_World" / "DZDS" / "DZDSBases.c").read_text()
    for needle in ("modded class TerritoryFlag", "DZDSBases.Add(this)", "DZDSBases.Remove(this)",
                   'IsPartConstructed("pole")', '"Material_FPole_Flag"', 'GetAnimationPhase("flag_mast") < 1',
                   "static TerritoryFlag NearestRaised(vector pos)", "static int RaisedCount()", "static int Count()"):
        assert needle in src, needle


def test_player_is_put_back_beside_the_vehicle():
    """Blae 2026-10-23: respawns woke ON the vehicle's spot (stuck in the MH-6, then killed by
    the spawn campfire beside it), and the plan's own PlayerPos was on the spot too. Deliver
    moves the player off the spot BEFORE the vehicle spawns, again after, and at a 3 s recheck;
    the target is recomputed when the plan's is on the spot. Positions go by value."""
    src = INIT_C.read_text()
    deliver = re.search(r"void Deliver\(PlayerBase player, RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    assert deliver.index('"before vehicle"') < deliver.index("ExpansionItemSpawnHelper.SpawnVehicle(")
    assert '"after vehicle"' in deliver
    assert "CallLater(KeepBesideLater, BESIDE_RECHECK_MS, false, player, plan.CarPos, plan.PlayerPos, plan.CarOri[0])" in deliver
    keep = re.search(r"string KeepBeside\(PlayerBase player, vector carPos, vector playerPos, float heading, string when\).*?\n\t\}", src, re.S).group(0)
    assert "BesideSpot(carPos, heading, m_Config.PlayerOffset)" in keep and "player.SetPosition(target)" in keep
    spot = re.search(r"static vector BesideSpot\(vector spot, float heading, float offset\).*?\n\t\}", src, re.S).group(0)
    assert "if (offset < BESIDE_MIN_M)" in spot and "offset = BESIDE_FALLBACK_M" in spot
    place = re.search(r"void PlacePlayer\(RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    assert "BesideSpot(plan.CarPos, plan.CarOri[0], offset)" in place and "[DZDS Arrivals] place:" in place


def test_random_character_is_plain_ifs():
    """`!plan.FirstArrival && cfg == 1` logged random=false on every respawn: plain ifs now."""
    src = INIT_C.read_text()
    assert "plan.RandomCharacter = !plan.FirstArrival" not in src
    plan = re.search(r"RefugeeArrivalPlan Plan\(PlayerIdentity identity\).*?\n\t\}", src, re.S).group(0)
    assert "if (m_Config.RandomCharacterOnRespawn == 1)\n\t\t\t\tplan.RandomCharacter = true;" in plan
    assert plan.index("ApplyLiveResets();") < plan.index("FindRecord(plan.Uid)"), "a live reset applies before the record is read"


# Soviet Special Forces (Blae, 2026-10-23): a starting archetype worn on the body, rare for
# everyone, always for Blae; his helicopter keeps the 24 h cooldown, a land vehicle comes inside it.
SOVIET_LAND = {"ExpansionUAZCargo_Green", "ExpansionUAZ", "ExpansionUAZRoofless_Black", "ExpansionVodnik",
               "CrSk_GAZ_3309_Cargo_Green"}
# Body slot -> the classes that fill it, across the outfit's variants.
SSF_SLOTS = {
    "headgear": {"Ssh68Helmet", "MilitaryBeret_Red"},
    "mask": {"BalaclavaMask_Green", "BalaclavaMask_Beige"},
    "body": {"TTsKOJacket_Camo", "GorkaEJacket_Summer", "GorkaEJacket_Flat"},
    "legs": {"TTSKOPants", "GorkaPants_Summer", "GorkaPants_Flat"},
    "feet": {"TTSKOBoots", "MilitaryBoots_Black", "MilitaryBoots_Brown"},
    "gloves": {"TacticalGloves_Green", "TacticalGloves_Beige"},
    "vest": {"SmershVest"},
    "back": {"AssaultBag_Ttsko"},
    "belt": {"MilitaryBelt"},
}


def _ssf(out):
    return next(o for o in out["Outfits"] if o["Name"] == "soviet_special_forces")


def test_blae_is_always_soviet_special_forces(built):
    """Blae always wakes as Soviet Special Forces; inside the helicopter cooldown he gets a
    Soviet land vehicle from the pool, never an aircraft."""
    cfg, _, out = built
    fav = {f["Id"]: f for f in out["Favored"]}[BLAE_ID]
    assert fav["Outfit"] == "soviet_special_forces"
    assert set(fav["CooldownVehicles"]) == SOVIET_LAND
    assert SOVIET_LAND <= {v["ClassName"] for v in out["Vehicles"]}
    assert not SOVIET_LAND & set(cfg["aircraft"])


def test_soviet_special_forces_is_rare_and_a_full_uniform(built):
    _, _, out = built
    ssf = _ssf(out)
    assert ssf["Chance"] == 0.03
    assert 0.5 <= ssf["HealthMin"] <= ssf["HealthMax"] <= 1
    assert {v["Name"] for v in ssf["Variants"]} == {"ttsko", "gorka_summer", "gorka_flat"}
    for v in ssf["Variants"]:
        worn = [w["ClassName"] for w in v["Worn"]]
        for slot, classes in SSF_SLOTS.items():
            assert sum(c in classes for c in worn) == 1, (v["Name"], slot)
        assert len(worn) == len(SSF_SLOTS), v["Name"]
        vest = next(w for w in v["Worn"] if w["ClassName"] == "SmershVest")
        assert vest["Attach"] == ["SmershBag"], v["Name"]
    assert ssf["AircraftCargo"] == "combat_pilot"


def test_soviet_special_forces_carries_a_rifle_a_pistol_and_full_mags(built):
    _, _, out = built
    ssf = _ssf(out)
    primaries = {w["WeaponClass"]: w for w in ssf["Primary"]}
    assert set(primaries) == {"AKS74U", "ASVAL"}
    assert ssf["Sidearm"]["WeaponClass"] == "MakarovIJ70"
    full = {"Mag_AK74_30Rnd": 30, "Mag_VAL_20Rnd": 20, "Mag_IJ70_8Rnd": 8}
    for w in [*ssf["Primary"], ssf["Sidearm"]]:
        assert w["Rounds"] == full[w["MagazineClass"]], w
    assert primaries["AKS74U"]["Magazines"] == primaries["ASVAL"]["Magazines"] == 3
    assert ssf["Sidearm"]["Magazines"] == 2
    rng = random.Random(3)
    for _ in range(200):
        kit = arrivals.simulate_dress(ssf, rng)
        assert sum(k in primaries for k in kit) == 1 and kit.count("MakarovIJ70") == 1, kit
        assert "SmershBag" in kit and "RGD5Grenade" in kit and "CombatKnife" in kit, kit


def test_soviet_special_forces_land_cargo_meets_the_kit_spec(built):
    """The land vehicle's kit follows the ground rules: 12-17 items, one knife, one car item, one
    camp item, one worn firearm with a partial magazine and spare rounds."""
    _, _, out = built
    cargo = _ssf(out)["LandCargo"]
    assert [s["Name"] for s in cargo["Slots"]] == arrivals.SLOT_ORDER and not cargo["Aircraft"]
    for name, pool in (("knife", CUTTING | {"AK_Bayonet"}), ("car", CAR), ("camp", CAMP)):
        s = _slot(cargo, name)
        assert s["Min"] == s["Max"] == 1 and set(s["Items"]) <= pool, name
    for f in cargo["Firearms"]:
        assert (f["RoundsMin"], f["RoundsMax"], f["SpareMin"], f["SpareMax"]) == (3, 6, 4, 8), f
    rng = random.Random(9)
    weapons = {f["WeaponClass"] for f in cargo["Firearms"]}
    for _ in range(500):
        kit = arrivals.simulate_kit(cargo, rng)
        items = [k for k in kit if k not in weapons and not k.startswith(("Ammo_", "Mag_"))]
        assert 12 <= len(items) <= 17, kit
        assert sum(k in weapons for k in kit) == 1, kit


def test_outfit_json_keys_are_init_c_fields(built):
    _, _, out = built
    src = INIT_C.read_text()

    def fields(cls):
        return set(re.findall(r"\b(\w+);", re.search(rf"class {cls}\s*\{{(.*?)\n\}}", src, re.S).group(1)))

    ssf = _ssf(out)
    assert set(ssf) <= fields("RefugeeArrivalOutfit")
    assert set(ssf["Variants"][0]) <= fields("RefugeeArrivalOutfitVariant")
    assert set(ssf["Variants"][0]["Worn"][0]) <= fields("RefugeeArrivalWorn")
    assert set(ssf["Sidearm"]) <= fields("RefugeeArrivalKitWeapon")
    assert set(ssf["LandCargo"]) <= fields("RefugeeArrivalArchetype")
    assert set(out["Favored"][0]) <= fields("RefugeeArrivalFavored")
    for engine_type in ("Cargo", "Weapon", "Magazine"):
        assert engine_type not in fields("RefugeeArrivalOutfit") | fields("RefugeeArrivalKitWeapon")


@pytest.mark.parametrize("break_it, match", [
    (lambda c: c["outfits"]["soviet_special_forces"]["carried"].append("Kalashnikov_Typo"), "Kalashnikov_Typo"),
    (lambda c: c["favored"][0].update(outfit="nope"), "no outfit named"),
    (lambda c: c["favored"][0]["cooldown_vehicles"].append("ExpansionMh6"), "land vehicles"),
    (lambda c: c["favored"][0]["cooldown_vehicles"].append("UAZ_452"), "UAZ_452"),
    (lambda c: c["outfits"]["soviet_special_forces"].update(aircraft_cargo="deserter"), "pilot profile"),
    (lambda c: c["outfits"]["soviet_special_forces"].update(chance=3), r"\[0, 1\]"),
])
def test_bad_outfit_config_is_rejected(built, break_it, match):
    _, map_data, _ = built
    bad = yaml.safe_load(arrivals.PRESET.read_text())
    break_it(bad)
    with pytest.raises(SystemExit, match=match):
        arrivals.build(bad, map_data, arrivals.mission_dir(map_data))


def test_init_c_outfit_and_helicopter_only_cooldown():
    """The outfit is rolled only for a random (respawn) character unless favored; a favored
    player's CooldownVehicles come inside the cooldown, start none, and skip base and camp."""
    src = INIT_C.read_text()
    pick = re.search(r"RefugeeArrivalOutfit PickOutfit\(RefugeeArrivalPlan plan, RefugeeArrivalFavored fav\).*?\n\t\}", src, re.S).group(0)
    assert pick.index("fav.Outfit") < pick.index("if (!plan.RandomCharacter)") < pick.index("o.Chance")
    plan = re.search(r"RefugeeArrivalPlan Plan\(PlayerIdentity identity\).*?\n\t\}", src, re.S).group(0)
    for needle in ("plan.StartsCooldown = false;", "only = fav.CooldownVehicles;", "plan.Outfit = PickOutfit(plan, fav);",
                   "if (!placed && baseCamp)\n\t\t\tplaced = PickBase(plan, rec);",
                   "if (!placed && baseCamp)\n\t\t\tplaced = PickCamp(plan, rec);",
                   "if (plan.AlwaysVehicle)\n\t\t\tbaseCamp = false;"):
        assert needle in plan, needle
    assert plan.index("plan.Outfit = PickOutfit") > plan.index("plan.RandomCharacter = true"), "roll after RandomCharacter is known"
    deliver = re.search(r"void Deliver\(PlayerBase player, RefugeeArrivalPlan plan\).*?\n\t\}", src, re.S).group(0)
    assert "if (plan.StartsCooldown)\n\t\t\t\trec.LastVehicle = now;" in deliver
    assert deliver.count("rec.LastVehicle = now") == 1
    cargo = re.search(r"RefugeeArrivalArchetype OutfitCargo\(RefugeeArrivalOutfit o, bool aircraft\).*?\n\t\}", src, re.S).group(0)
    assert "FindArchetype(o.AircraftCargo)" in cargo and "return o.LandCargo;" in cargo
    fill = re.search(r"int FillCargo\(CarScript car, bool aircraft, RefugeeArrivalArchetype forced = null\).*?\n\t\}", src, re.S).group(0)
    assert "a = PickArchetype(aircraft);" in fill and "RefugeeArrivalArchetype a = forced;" in fill


def test_init_c_dresses_the_outfit_instead_of_civilian_clothes():
    src = INIT_C.read_text()
    setup = re.search(r"override void StartingEquipSetup\(PlayerBase player, bool clothesChosen\).*?\n\t\}", src, re.S).group(0)
    assert setup.index("player.RemoveAllItems();") < setup.index("Dress(player, m_ArrivalPlan.Outfit)") < setup.index("KameezShirt_Beige")
    dressed = setup[setup.index("Dress(player, m_ArrivalPlan.Outfit)"):setup.index("KameezShirt_Beige")]
    assert "GiveStartKit(" in dressed and "return;" in dressed
    dress = re.search(r"string Dress\(PlayerBase p, RefugeeArrivalOutfit o, int variant = -1\).*?\n\t\}", src, re.S).group(0)
    for needle in ("GiveAttachments(p, item, w.Attach, o, notes)", "o.Primary.GetRandomElement()", "o.Sidearm"):
        assert needle in dress, needle
    weapon = re.search(r"string GiveKitWeapon\(.*?\n\t\}", src, re.S).group(0)
    assert "ServerSetAmmoCount(w.Rounds)" in weapon and "CreateAttachment" not in weapon.split("GiveAttachments")[0]
    attach = re.search(r"void GiveAttachments\(.*?\n\t\}", src, re.S).group(0)
    assert "carrier.GetInventory().CreateAttachment(cls)" in attach and "DressItem(p, cls, o, notes)" in attach
    test = re.search(r"void OutfitSelfTest\(\).*?\n\t\}", src, re.S).group(0)
    assert "Dress(dummy, o, v)" in test and "ObjectDelete(dummy)" in test
    assert "OutfitSelfTest();" in re.search(r"void VehicleSelfTest\(\).*?\n\t\}", src, re.S).group(0)
