"""Guards on design intent: spec rules encoded in presets/ and maps/ can't silently drift."""
import subprocess
import xml.etree.ElementTree as ET

import yaml

import maps_check
import modstring
import types_gen
from apply_ai_calibration import check_bounds

ROOT = modstring.ROOT


def load(rel):
    return yaml.safe_load((ROOT / rel).read_text())


import re

from apply_ai_calibration import PATROL_BOUNDS

DZDS_FACTIONS = ROOT / "mods" / "DZDS" / "Scripts" / "3_Game" / "DZDS" / "Factions" / "DZDSFactions.c"

# Built-in IsFriendly() relations transcribed from Expansion's source (Factions/*.c, 2026-10),
# for the interim mapping used before @DZDS is built.
ENGINE_FRIENDLY = {
    "West": {"West", "Civilian"},
    "East": {"East", "Civilian"},
    "Raiders": {"Raiders"},
    "Civilian": {"West", "East", "Raiders", "Civilian", "Guards", "Mercenaries", "Shamans"},
    "Guards": {"Guards"},
    "Mercenaries": {"Mercenaries"},
    "Shamans": {"Shamans"},
}
BEHAVIOURS = {"HALT", "LOOP", "ALTERNATE", "ONCE", "HALT_OR_LOOP", "HALT_OR_ALTERNATE",
              "LOOP_OR_ALTERNATE", "ROAMING", "ROAMING_LOCAL"}
SPEEDS = {"WALK", "JOG", "SPRINT", "RANDOM", "RANDOM_NONSTATIC"}
STANCES = {"STANDING", "CROUCHED", "PRONE"}
FORMATIONS = {"Column", "File", "Vee", "Wall", "RANDOM"}


def dzds_relations() -> dict[str, set[str]]:
    """Parse IsFriendly() in our @DZDS faction source: class -> friendly class names."""
    src = DZDS_FACTIONS.read_text()
    rel = {}
    for m in re.finditer(r"class eAIFaction(DZDS\w+) : eAIFaction\s*\{(.*?)\n\};", src, re.S):
        body = m.group(2)
        fn = re.search(r"bool IsFriendly\(.*?\{(.*?)\n\t\}", body, re.S).group(1)
        rel[m.group(1)] = set(re.findall(r"IsInherited\(eAIFaction(DZDS\w+)\)\) return true", fn))
    return rel


def test_preset_stances_match_dzds_source():
    f = load("presets/factions.yaml")["factions"]
    rel = dzds_relations()
    custom = {name: spec["custom_faction"] for name, spec in f.items()}
    assert {c for c in custom.values() if c} == set(rel), "preset and DZDSFactions.c disagree on factions"
    for name, spec in f.items():
        if not custom[name]:
            continue
        for other, stance in spec["stance"].items():
            if not custom[other]:
                continue  # vanilla zombies attack everyone regardless of faction
            friendly = custom[other] in rel[custom[name]]
            assert (stance in {"friendly", "neutral"}) == friendly, f"{name} -> {other}: preset says {stance}"


def test_blueprint_rules():
    f = load("presets/factions.yaml")["factions"]
    tribes = ["Jackals", "Karkas", "Rust"]
    for a in tribes:                      # three-way blood feud
        for b in tribes:
            if a != b:
                assert f[a]["stance"][b] == "hostile"
        assert f[a]["stance"]["Settlers"] == "hostile"
        assert f[a]["stance"]["Peacekeepers"] == "hostile"
    assert f["Peacekeepers"]["stance"]["Settlers"] == "neutral"   # UN armed neutrality
    assert f["Settlers"]["recruitable"] and not any(f[t]["recruitable"] for t in tribes)
    for name in ("Settlers", "Peacekeepers", *tribes):
        assert f[name]["stance"]["Infected"] == "hostile"


def test_interim_factions_exist_in_engine():
    for name, spec in load("presets/factions.yaml")["factions"].items():
        if spec["interim_faction"]:
            assert spec["interim_faction"] in ENGINE_FRIENDLY, name


def test_behaviour_profiles_use_real_values_and_bounds():
    for name, spec in load("presets/factions.yaml")["factions"].items():
        b = spec.get("behaviour")
        if not b:
            continue
        assert b["Behaviour"] in BEHAVIOURS, name
        assert b["Speed"] in SPEEDS and b["UnderThreatSpeed"] in SPEEDS, name
        assert b["DefaultStance"] in STANCES and b["Formation"] in FORMATIONS, name
        assert check_bounds(b, PATROL_BOUNDS) == [], name


def test_roles_and_resources_valid():
    p = load("presets/factions.yaml")
    roles = set(load("maps/_roles.yaml")["roles"])
    for name, spec in p["factions"].items():
        assert set(spec.get("holds_roles", [])) <= roles, name
    for res, spec in p["resources"].items():
        assert set(spec["from_roles"]) <= roles, res


def test_initial_control_uses_known_locations_once():
    p = load("presets/factions.yaml")
    for map_name, control in p["initial_control"].items():
        locs = set(load(f"maps/{map_name}.yaml")["locations"])
        seen = [loc for holders in control.values() for loc in holders]
        assert set(seen) <= locs
        assert len(seen) == len(set(seen)), "a location is assigned twice"


def test_chernarus_map_complete():
    assert maps_check.check(load("maps/chernarusplus.yaml"), load("maps/_roles.yaml")["roles"]) == []


def test_types_generator_compiles_valid_xml(tmp_path):
    preset = {"profiles": {"p": {"category": "tools", "usage": ["Industrial"], "value": ["Tier1"],
                                 "lifetime": 10800, "nominal": 12, "min": 6}},
              "items": [{"name": "SparkPlug", "profile": "p", "nominal": 20, "min": 10, "enabled": True}]}
    root, warnings = types_gen.build(preset)
    assert warnings == []
    out = tmp_path / "t.xml"
    ET.ElementTree(root).write(out, encoding="UTF-8", xml_declaration=True)
    subprocess.run(["xmllint", "--noout", str(out)], check=True)
    assert root.find("type[@name='SparkPlug']/nominal").text == "20"


def test_shipped_custom_types_add_no_loot():
    """Pure vanilla loot (Blae, 2026-10-15): our custom types file boosts nothing."""
    root, warnings = types_gen.build(load("presets/types_dzds.yaml"))
    assert warnings == [] and root.findall("type") == []


def test_types_register_is_idempotent(tmp_path):
    core = tmp_path / "cfgeconomycore.xml"
    core.write_text("<economycore>\n</economycore>\n")
    assert types_gen.register(core) is True
    assert types_gen.register(core) is False
    assert core.read_text().count('folder="dzds"') == 1


def test_every_enabled_mod_verified_and_at_most_one_map_mod():
    # Zero is valid: Basic Map was pruned 2026-10-07 in favour of the vanilla paper map
    # (displayPlayerPosition false). Two would conflict.
    mods = modstring.ordered(modstring.load_mods())
    assert all(m.get("verified") for m in mods)
    map_mods = [m for m in mods if m["name"] in {"Basic Map", "DayZ-Expansion-Navigation"}]
    assert len(map_mods) <= 1


def test_no_enabled_mod_conflicts():
    """incompatible_with lists Workshop IDs that must never be enabled alongside the mod."""
    mods = modstring.load_mods()
    enabled = {m["id"] for m in mods if m.get("enabled", True)}
    for m in mods:
        if m.get("enabled", True):
            clash = set(m.get("incompatible_with", [])) & enabled
            assert not clash, f"{m['name']} is incompatible with enabled mod(s) {clash}"
    assert 2793893086 not in enabled, "DayZ-Expansion-Animations breaks DayZ Horse"


def test_traders_reference_real_factions_roles_and_currencies():
    t = load("presets/traders.yaml")
    factions = load("presets/factions.yaml")["factions"]
    roles = set(load("maps/_roles.yaml")["roles"])
    customs = {s["custom_faction"] for s in factions.values() if s["custom_faction"]}
    for name, tr in t["traders"].items():
        assert tr["faction"] in factions or tr["faction"] == "none", name
        assert tr["role"] in roles, name
        assert set(tr["currencies"]) <= set(t["currencies"]), name
        if tr.get("required_faction"):
            assert tr["required_faction"] in customs, name


def test_all_repo_yaml_parses():
    for folder in ("config", "presets", "maps"):
        for f in (ROOT / folder).rglob("*.yaml"):
            yaml.safe_load(f.read_text())


def test_no_patrol_loots_food():
    """Food stays at vanilla scarcity (Blae, 2026-10-12): AI must not pick it up.
    ALL includes FOOD in Expansion's eAILootingBehavior, so it is banned too."""
    for name, spec in load("presets/factions.yaml")["factions"].items():
        behaviours = [("faction", spec.get("behaviour") or {})]
        for tname, tpl in (spec.get("patrol_templates") or {}).items():
            behaviours.append((tname, tpl.get("behaviour") or {}))
        for where, b in behaviours:
            flags = set(str(b.get("LootingBehaviour", "")).split("|"))
            assert not flags & {"FOOD", "ALL"}, f"{name}/{where}: {b['LootingBehaviour']}"


def test_no_map_wide_roaming():
    """Human NPCs stay near their own sites (Blae, 2026-10-12): ROAMING sends a group to a
    new map location every 5-10 min; ROAMING_LOCAL keeps it among nearby buildings."""
    for name, spec in load("presets/factions.yaml")["factions"].items():
        behaviours = [spec.get("behaviour") or {}]
        behaviours += [t.get("behaviour") or {} for t in (spec.get("patrol_templates") or {}).values()]
        assert all(b.get("Behaviour") != "ROAMING" for b in behaviours), name


PRUNED_BADLANDS = {
    3689174025: "SF Zombie Horde Event",       # targets players anywhere; can't respect zones
    2874589934: "DayZ-Dynamic-AI-Addon",       # Spatial AI already at MaxAI 0
    2792984177: "DayZ-Expansion-Missions",     # every feature off
    2147610525: "Armored Vehicle Pack", 1912237302: "IRP-Land-Rover-Defender-110",
    2757080411: "Crocos Quadbike", 2298127647: "Arma 2 Clothing Pack",
    2074403068: "Unknown Ghillie Mod", 2361330944: "InventoryInCar",
    3115714092: "HypeTrain",  # Blae, 2026-10-15: ditched (rail on Nasdara unverifiable)
    3430034381: "Leather Crafting",  # 1.30 boot: duplicate CraftLeatherBelt, World won't compile
}


def test_badlands_pruned_mods_are_disabled():
    by_id = {m["id"]: m for m in modstring.load_mods()}
    for mid, name in PRUNED_BADLANDS.items():
        assert by_id[mid]["enabled"] is False, name
        assert "PRUNED 2026-10-15 (Badlands)" in by_id[mid].get("note", ""), name


def test_no_overlay_left_for_pruned_mods():
    import apply_overlays as ov
    names = {f.name for f in ov.OVERLAYS.glob("*.yaml")}
    assert not names & {"zombie_horde.yaml", "spatial_ai.yaml", "expansion_missions.yaml"}


def test_no_open_country_patrol_templates():
    """Spec §4.3: only the ledger's war party crosses open country."""
    for name, spec in load("presets/factions.yaml")["factions"].items():
        for tname, t in (spec.get("patrol_templates") or {}).items():
            assert t["kind"] in {"garrison", "perimeter", "roam", "ambush"}, (name, tname)


def test_generated_patrols_stay_inside_their_zone():
    import patrol_gen
    import zones
    mp = load("maps/nasdara.yaml")
    control = zones.control_from_initial(load("presets/factions.yaml")["initial_control"]["nasdara"])
    zs = zones.build(mp, control)
    for p in patrol_gen.generate("nasdara"):
        site = p["Name"].split(" @ ")[1]
        zn = zones.zone_of(site, zs)
        for x, _, z in p["Waypoints"]:
            assert zones.inside(x, z, [zn]), (p["Name"], x, z)
