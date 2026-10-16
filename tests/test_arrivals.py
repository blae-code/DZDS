import math
import random
import re
import xml.etree.ElementTree as ET

import pytest
import yaml

import active
import arrivals

INIT_C = active.mission_dir("nasdara") / "init.c"


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
    assert {a["Name"]: a["Weight"] for a in out["Archetypes"]} == \
        {"deserter": 30.0, "trucker": 25.0, "nomad": 25.0, "townie": 20.0}


CUTTING = {"CombatKnife", "KitchenKnife", "HuntingKnife"}
CAR = {"TireRepairKit", "Wrench", "Screwdriver", "Pliers", "SparkPlug", "EpoxyPutty"}
CAMP = {"Matchbox", "Pot", "PortableGasStove", "SmallGasCanister", "Rope"}


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
            assert 12 <= len(items) <= 17, (arch["Name"], kit)
            for name in set(items):
                cap = 2 if name in food else 1
                assert items.count(name) <= cap, (arch["Name"], name)
            assert sum(k in weapons for k in kit) == 1
            assert sum(k in CUTTING for k in items) == 1, (arch["Name"], kit)
            assert sum(k in CAR for k in items) >= 1, (arch["Name"], kit)
            assert sum(k in CAMP for k in items) >= 1, (arch["Name"], kit)


def test_knife_car_and_camp_slots_are_guaranteed(built):
    _, _, out = built
    for arch in out["Archetypes"]:
        for name, pool in (("knife", CUTTING), ("car", CAR), ("camp", CAMP)):
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
    fill = re.search(r"int FillCargo\(CarScript car\).*?\n\t\}", src, re.S).group(0)
    for needle in ("PickArchetype()", "ServerSetAmmoCount(", "SpareMin", "SpareMax"):
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
