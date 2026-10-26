#!/usr/bin/env python3
"""Compile dynamic campaign files: Expansion Quests, Barter Traders, and Dialogue Framework.

Instantiates live front-line quests, fixed story progression arcs, barter traders,
and interactive dialogue trees from the War Ledger and presets:
  - server/profiles/ExpansionMod/Quests/Quests/Quest_<ID>.json
  - server/profiles/ExpansionMod/Quests/NPCs/QuestNPC_<ID>.json
  - server/profiles/ExpansionMod/Quests/Objectives/<Type>/Objective_<Prefix>_<ID>.json
  - server/profiles/ExpansionMod/Traders/<Name>.json
  - server/mpmissions/<mission>/expansion/traders/Trader_<ID>.json
  - server/profiles/DialogFramework/Dialogues/NPC_<ID>/Dialogue.json

Usage:
  tools/campaign_gen.py [--map nasdara] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from typing import Any

import active
import ground
import map_survey

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import WarLedger  # noqa: E402
from gamemaster import survival_goals  # noqa: E402

log = logging.getLogger("campaign_gen")

# Type mappings for Expansion Quests ConfigVersion 28
OBJ_TYPE_TARGET = 2
OBJ_TYPE_TRAVEL = 3
OBJ_TYPE_COLLECTION = 4
OBJ_TYPE_DELIVERY = 5
OBJ_TYPE_TREASURE = 6
OBJ_TYPE_AIPATROL = 7
OBJ_TYPE_AICAMP = 8
OBJ_TYPE_AIESCORT = 9

OBJ_MAP = {
    "TARGET": OBJ_TYPE_TARGET,
    "TRAVEL": OBJ_TYPE_TRAVEL,
    "COLLECTION": OBJ_TYPE_COLLECTION,
    "DELIVERY": OBJ_TYPE_DELIVERY,
    "TREASUREHUNT": OBJ_TYPE_TREASURE,
    "AIPATROL": OBJ_TYPE_AIPATROL,
    "AICAMP": OBJ_TYPE_AICAMP,
    "AIESCORT": OBJ_TYPE_AIESCORT,
}

DIR_MAP = {
    OBJ_TYPE_TARGET: ("Target", "TA"),
    OBJ_TYPE_TRAVEL: ("Travel", "T"),
    OBJ_TYPE_COLLECTION: ("Collection", "C"),
    OBJ_TYPE_DELIVERY: ("Delivery", "D"),
    OBJ_TYPE_TREASURE: ("TreasureHunt", "TH"),
    OBJ_TYPE_AIPATROL: ("AIPatrol", "AIP"),
    OBJ_TYPE_AICAMP: ("AICamp", "AIC"),
    OBJ_TYPE_AIESCORT: ("AIVIP", "AIESCORT"),
}

# Canonical NPC Profiles for Faction Representatives & Living World Contacts
NPC_PROFILES: dict[str, dict[str, Any]] = {
    "1": {
        "id": 1,
        "name": "Elder Tariq",
        "title": "Frontier Settlers Elder & Quartermaster",
        "faction": "Settlers",
        "class": "ExpansionQuestNPCAIDenis",
        "loadout": "DZDS_Settlers",
        "role_site": "Qalat-e Lut",
        "pos": [14837.0, 0.0, 7855.0],
        "heading": 180.0,
        "greeting": "Welcome to Qalat-e Lut fortress. Out here in the badlands, water is life, unity is survival, and carelessness is suicide.",
        "lore": "The Frontier Settlers established Qalat-e Lut inside an ancient citadel. We farm irrigation plots in the fortress shadow, maintain the deep aquifer cistern, and stand together against highway raiders and syndicate monopolies.",
        "standing_info": "We trust survivors who contribute to our community projects and defend our homesteads. Helping break sieges or delivering clean water earns immediate standing and access to better recruits.",
        "survival_tip": "Never drink untreated surface or well water without boiling it or adding purification tablets; cholera kills within hours in the desert heat. Tune your personal radio to Settler Net 87.8 MHz for emergency broadcasts.",
        "politics": "We maintain armed neutrality with Task Force Blue Shield. We despise the Jackal raiders who prey on our roads. The Rust Syndicate charges extortionate rates for water, while the Karkas keep to their mountain ridges.",
    },
    "2": {
        "id": 2,
        "name": "Capt. Miller",
        "title": "Task Force Blue Shield Commander",
        "faction": "Peacekeepers",
        "class": "ExpansionQuestNPCAIElias",
        "loadout": "DZDS_Peacekeepers_officer",
        "role_site": "Eastern Airfield",
        "pos": [12030.0, 0.0, 10850.0],
        "heading": 90.0,
        "greeting": "Task Force Blue Shield Command. State your identity and business within the humanitarian corridor.",
        "lore": "Task Force Blue Shield operates under United Nations humanitarian mandates. We defend the Green Zones, escort aid convoys, and secure airfield transit corridors. We maintain armed neutrality unless fired upon.",
        "standing_info": "Sign the Blue Shield Charter to unlock our Quartermaster depot. If your standing with the UN drops below -30 due to hostile acts, our sentries will initiate immediate lethal perimeter defense.",
        "survival_tip": "Identify factions by silhouette and uniform before engaging: blue helmets and berets are UN Peacekeepers; hi-vis and welding visors are Rust Syndicate; gas masks and skull bandanas are hostile Jackals.",
        "politics": "We provide humanitarian aid to the Frontier Settlers. We regard the Jackals as outlaw combatants. The Rust Syndicate operates an unauthorized resource monopoly, but we avoid open conflict unless aid lines are threatened.",
    },
    "3": {
        "id": 3,
        "name": "Dr. Al-Mansoor",
        "title": "UN Field Surgeon & Clinic Director",
        "faction": "Peacekeepers",
        "class": "ExpansionQuestNPCAIHassan",
        "loadout": "DZDS_Peacekeepers",
        "role_site": "Southwest Base",
        "pos": [3250.0, 0.0, 4630.0],
        "heading": 0.0,
        "greeting": "Blue Shield Field Clinic. If you are hemorrhaging or burning with wound fever, sit down. If you have medical supplies, hand them over.",
        "lore": "I oversee surgical trauma care and disease containment across the western basin. Sepsis, cholera, and gunshot wounds are our daily routine.",
        "standing_info": "Deliver sterile bandages, saline bags, and broad-spectrum antibiotics to support our clinic. Medical service guarantees UN standing.",
        "survival_tip": "Disinfect dirty wounds immediately with alcohol tincture or iodine. Once wound fever sets in, only full courses of Tetracycline will stop the sepsis.",
        "politics": "I treat anyone who doesn't pull a weapon in my triage tent. Even wounded raiders receive treatment if they disarm, though command frowns upon it.",
    },
    "4": {
        "id": 4,
        "name": "Broker Koval",
        "title": "Rust Syndicate Water Master & Broker",
        "faction": "Rust",
        "class": "ExpansionQuestNPCAIBoris",
        "loadout": "DZDS_Rust_foreman",
        "role_site": "Hilltop Water Station",
        "pos": [8290.0, 0.0, 6510.0],
        "heading": 270.0
,        "greeting": "The Syndicate runs the turbine pumps. No diesel, no maintenance, no water. Everything has a price in the sands.",
        "lore": "The Rust Syndicate controls the industrial refineries, turbine wells, and pipeline valves across Nasdara. The towns collapsed because they couldn't keep machines running. We keep them running.",
        "standing_info": "Pay your maintenance parts toll to secure legal drawing rights. Once verified, our broker trades clean water, fuel canisters, and vehicle spare parts.",
        "survival_tip": "Keep your vehicles topped with clean coolant water. A blown radiator gasket in the dune wastes is a death sentence. Always carry spare spark plugs and tire repair kits.",
        "politics": "Settlers complain about our tolls, but they'd die of thirst in three days without our turbine pumps. Jackals try to dynamite our lines, and we hang them from the towers.",
    },
    "5": {
        "id": 5,
        "name": "Elder Soroush",
        "title": "Karkas Clan Ridge Patriarch",
        "faction": "Karkas",
        "class": "ExpansionQuestNPCAIKaito",
        "loadout": "DZDS_Karkas_elder",
        "role_site": "Missile Base Ridge",
        "pos": [2840.0, 0.0, 9170.0],
        "heading": 45.0,
        "greeting": "The desert wind strips flesh from bone. Only those who honor the mountain walk these heights unmolested.",
        "lore": "We have walked the crags and rock spires of Nasdara for centuries. The valley cities built of steel crumbled into dust, but the mountain provides for those who know how to hunt.",
        "standing_info": "Bring wild game and hunting tribute. Reach 50 clan reputation and our ridge scouts will grant you safe passage across the high country.",
        "survival_tip": "Always hunt downwind of wild game. Cure animal pelts with garden lime to craft durable desert clothing and horse tack that never rots under the sun.",
        "politics": "The valley tribes kill each other over rusted iron and poisoned puddles. We keep to the high ground. Step onto our holy ridges uninvited, and our marksmen will put lead through your skull.",
    },
    "6": {
        "id": 6,
        "name": "Scout Farid",
        "title": "Frontier Desert Scout & Road Watcher",
        "faction": "Settlers",
        "class": "ExpansionQuestNPCAIDenis",
        "loadout": "DZDS_Settlers",
        "role_site": "Settler Haven",
        "pos": [7560.0, 0.0, 8720.0],
        "heading": 135.0,
        "greeting": "Keep low. I watch the northern highway approaches. Jackal war parties have been probing our outer perimeter all morning.",
        "lore": "I scout the nomad trails and road junctions between Settler Haven and the airfields. If there's an ambush or roadblock ahead, I usually spot the dust trail first.",
        "standing_info": "Clear raider camps and complete route reconnaissance contracts to keep our supply lines open. Good scouts earn respect and gear.",
        "survival_tip": "Never travel the dunes without a working compass and binoculars. Keep your personal radio battery charged so you can hear patrol warnings before you walk into an ambush.",
        "politics": "The Jackals are predators who take whatever isn't nailed down. The UN helps with medical convoys, but when the shooting starts, you have to rely on your own rifle.",
    },
    "7": {
        "id": 7,
        "name": "The Smuggler",
        "title": "Desert Black Market Fence",
        "faction": "none",
        "class": "ExpansionQuestNPCAIElias",
        "loadout": "DZDS_Settlers",
        "role_site": "Eastern Caravanserai",
        "pos": [14840.0, 0.0, 7910.0],
        "heading": 315.0,
        "greeting": "Keep it quiet and keep your hands off the merchandise. No flags, no politics out here. Just honest barter in cold hard steel.",
        "lore": "I deal with everyone: Settlers, Blue Shield officers, tribal deserters. If it's scarce, locked, or forbidden, I find a way to move it across the sands.",
        "standing_info": "I deal strictly in hard currency: ammunition and valuable salvage. No questions asked, no faction oaths required.",
        "survival_tip": "Lock your compound gates with digital keypads and never leave a vehicle parked without removing the spark plug or locking the doors with a pick-resistant cylinder.",
        "politics": "Governments fall, armies disband, but trade never stops. The UN preaches, the Syndicate bullies, and the Jackals steal. I just provide goods to survivors who can pay.",
    },
}

# Faction name mapping for backward compatibility
FACTION_NPC_KEY_MAP = {
    "Settlers": "1",
    "Peacekeepers": "2",
    "Rust": "4",
    "Karkas": "5",
    "none": "7",
}

# Verified Expansion Market Category Mappings
TRADER_DEFS = {
    "frontier_exchange": {
        "id": 1,
        "file": "Frontier_Exchange.json",
        "display": "Frontier Exchange (Settlers Barter)",
        "npc_id": 1,
        "npc_name": "Elder Tariq",
        "icon": "Deliver",
        "faction": "DZDSSettlers",
        "required_quest": -1,
        "currencies": ["nail", "expansionbanknotehryvnia", "ammo_22", "ammo_9x19", "ammo_545x39", "ammo_762x39", "ammo_556x45"],
        "categories": [
            "Food",
            "Drinks",
            "Tools",
            "Supplies",
            "Backpacks",
            "Boots_And_Shoes",
            "Coats_And_Jackets",
            "Gardening",
            "Fruit_And_Vegetables",
            "Containers",
        ],
    },
    "un_quartermaster": {
        "id": 2,
        "file": "UN_Quartermaster.json",
        "display": "UN Quartermaster (Task Force Blue Shield)",
        "npc_id": 2,
        "npc_name": "Capt. Miller",
        "icon": "Medic Box",
        "faction": "",
        "required_quest": 503,  # un_intro in templates
        "currencies": ["expansionbanknotehryvnia", "ammo_556x45", "ammo_9x19"],
        "categories": [
            "Medical",
            "Navigation",
            "Electronics",
            "Food",
            "Drinks",
            "Kits",
            "Helmets",
            "Vests",
        ],
    },
    "rust_broker": {
        "id": 3,
        "file": "Rust_Broker.json",
        "display": "Rust Syndicate Water Broker",
        "npc_id": 4,
        "npc_name": "Broker Koval",
        "icon": "Car",
        "faction": "",
        "required_quest": 504,  # water_rights in templates
        "currencies": ["ammo_762x39", "ammo_545x39", "ammo_9x19", "nail"],
        "categories": [
            "Vehicle_Parts",
            "Liquids",
            "Supplies",
            "Tools",
            "Batteries",
        ],
    },
    "smuggler": {
        "id": 4,
        "file": "The_Smuggler.json",
        "display": "The Smuggler (Black Market Fence)",
        "npc_id": 7,
        "npc_name": "The Smuggler",
        "icon": "Pistol",
        "faction": "",
        "required_quest": -1,
        "currencies": ["ammo_762x39", "ammo_545x39", "ammo_556x45", "ammo_9x19", "ammo_22"],
        "categories": [
            "Pistols",
            "Rifles",
            "Shotguns",
            "Optics",
            "Magazines",
            "Muzzles",
            "Locks",
            "Explosives_And_Grenades",
        ],
    },
}


def get_ground_sampler(map_name: str) -> ground.Ground:
    """Build a terrain altitude sampler for the map."""
    mission_dir = active.mission_dir(map_name)
    map_groups = mission_dir / "mapgrouppos.xml"
    if map_groups.exists():
        return ground.Ground(map_survey.load_groups(map_groups))
    return ground.Ground()


def load_npc_profiles(quests_cfg: dict) -> dict[str, dict[str, Any]]:
    """Merge configured fixed_npcs with rich lore profiles."""
    out = dict(NPC_PROFILES)
    fixed = quests_cfg.get("fixed_npcs", {})
    for nid_str, ncfg in fixed.items():
        k = str(nid_str)
        if k in out:
            out[k]["name"] = ncfg.get("name", out[k]["name"])
            out[k]["faction"] = ncfg.get("faction", out[k]["faction"])
            out[k]["role_site"] = ncfg.get("role_site", out[k]["role_site"])
            if "position" in ncfg:
                out[k]["pos"] = list(ncfg["position"])
            out[k]["heading"] = float(ncfg.get("heading", out[k].get("heading", 0.0)))
            out[k]["class"] = ncfg.get("classname", out[k]["class"])
            out[k]["loadout"] = ncfg.get("loadout", out[k]["loadout"])
            out[k]["greeting"] = ncfg.get("greeting", out[k]["greeting"])
    return out


def build_quest_npc(npc_info: dict, pos: list[float], yaw: float = 0.0) -> dict:
    """Expansion Quest NPC JSON (ConfigVersion 6)."""
    return {
        "ConfigVersion": 6,
        "ID": npc_info["id"],
        "ClassName": npc_info["class"],
        "Position": [round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)],
        "Orientation": [round(yaw, 1), 0.0, 0.0],
        "NPCName": npc_info["name"],
        "DefaultNPCText": npc_info["greeting"],
        "Waypoints": [[round(pos[0], 2), round(pos[1], 2), round(pos[2], 2)]],
        "NPCEmoteID": 46,
        "NPCEmoteIsStatic": 1,
        "NPCLoadoutFile": npc_info["loadout"],
        "NPCInteractionEmoteID": 1,
        "NPCQuestCancelEmoteID": 60,
        "NPCQuestStartEmoteID": 58,
        "NPCQuestCompleteEmoteID": 39,
        "NPCFaction": "InvincibleObservers",
        "NPCType": 2,
        "Active": 1,
    }


def build_objective(obj_type: int, obj_id: int, text: str, pos: list[float],
                    site_name: str, faction_name: str = "DZDSJackals",
                    qspec: dict | None = None) -> dict:
    """Expansion Objective JSON (ConfigVersion 28)."""
    x, y, z = pos
    qspec = qspec or {}

    if obj_type == OBJ_TYPE_AIPATROL:
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_AIPATROL,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "MaxDistance": -1.0,
            "MinDistance": -1.0,
            "AllowedWeapons": [],
            "AllowedDamageZones": [],
            "AISpawn": {
                "Name": f"Hostiles_{site_name.replace(' ', '_')}",
                "Persist": 0,
                "Faction": faction_name,
                "Formation": "Vee",
                "FormationScale": 1.5,
                "FormationLooseness": 0.0,
                "Loadout": "DZDS_Jackals" if "Jackal" in faction_name else "DZDS_Rust",
                "Units": [
                    "eAI_SurvivorM_Denis",
                    "eAI_SurvivorM_Boris",
                    "eAI_SurvivorF_Eva",
                ],
                "NumberOfAI": 3,
                "Behaviour": 0,
                "Speed": 1.0,
                "UnderThreatSpeed": 2.0,
                "CanBeLooted": 1,
                "UnlimitedReload": 1,
                "SniperProneDistanceThreshold": 100.0,
                "AccuracyMin": 0.35,
                "AccuracyMax": 0.55,
                "Headshots": 1,
                "RespawnTime": -1,
                "DespawnTime": 120,
                "MinDistRadius": 50.0,
                "MaxDistRadius": 800.0,
                "DespawnRadius": 1000.0,
                "Waypoints": [
                    [round(x, 2), round(y, 2), round(z, 2)],
                    [round(x + 25, 2), round(y, 2), round(z + 20, 2)],
                    [round(x - 20, 2), round(y, 2), round(z + 30, 2)],
                ],
            },
            "MaxDistance": 250.0,
            "MinDistance": -1.0,
            "MarkerName": site_name,
            "ShowDistance": 1,
        }

    if obj_type == OBJ_TYPE_AICAMP:
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_AICAMP,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "MaxDistance": 300.0,
            "MinDistance": -1.0,
            "AllowedWeapons": [],
            "AllowedDamageZones": [],
            "AISpawn": {
                "Name": f"Camp_{site_name.replace(' ', '_')}",
                "Persist": 0,
                "Faction": faction_name,
                "Formation": "Column",
                "FormationScale": 1.0,
                "FormationLooseness": 0.0,
                "Loadout": "DZDS_Jackals",
                "Units": [
                    "eAI_SurvivorM_Denis",
                    "eAI_SurvivorM_Boris",
                    "eAI_SurvivorF_Eva",
                    "eAI_SurvivorM_Hassan",
                ],
                "NumberOfAI": 4,
                "Behaviour": 0,
                "Speed": 1.0,
                "UnderThreatSpeed": 2.0,
                "CanBeLooted": 1,
                "UnlimitedReload": 1,
                "AccuracyMin": 0.30,
                "AccuracyMax": 0.50,
                "Headshots": 1,
                "RespawnTime": -1,
                "DespawnTime": 120,
                "MinDistRadius": 40.0,
                "MaxDistRadius": 600.0,
                "DespawnRadius": 800.0,
                "Waypoints": [
                    [round(x, 2), round(y, 2), round(z, 2)],
                    [round(x + 15, 2), round(y, 2), round(z - 15, 2)],
                ],
            },
            "InfectedCamp": 0,
            "MarkerName": site_name,
            "ShowDistance": 1,
        }

    if obj_type == OBJ_TYPE_AIESCORT:
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_AIESCORT,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "MaxDistance": 25.0,
            "MinDistance": -1.0,
            "AllowedWeapons": [],
            "AllowedDamageZones": [],
            "AISpawn": {
                "Name": f"Escort_{site_name.replace(' ', '_')}",
                "Persist": 0,
                "Faction": "DZDSPeacekeepers",
                "Formation": "SingleFile",
                "FormationScale": 1.0,
                "FormationLooseness": 0.0,
                "Loadout": "DZDS_Peacekeepers",
                "Units": ["eAI_SurvivorM_Denis"],
                "NumberOfAI": 1,
                "Behaviour": 0,
                "Speed": 1.0,
                "UnderThreatSpeed": 2.0,
                "CanBeLooted": 0,
                "UnlimitedReload": 1,
                "AccuracyMin": 0.40,
                "AccuracyMax": 0.60,
                "Headshots": 1,
                "RespawnTime": -1,
                "DespawnTime": 120,
                "MinDistRadius": 50.0,
                "MaxDistRadius": 1000.0,
                "DespawnRadius": 1200.0,
                "Waypoints": [[round(x, 2), round(y, 2), round(z, 2)]],
            },
            "Positions": [[round(x, 2), round(y, 2), round(z, 2)]],
            "MarkerName": site_name,
            "ShowDistance": 1,
            "CanBeInjured": 1,
        }

    if obj_type == OBJ_TYPE_DELIVERY:
        req = qspec.get("items_required")
        if req:
            colls = [{
                "Amount": int(it.get("amount", it.get("Amount", 1))),
                "ClassName": it.get("class", it.get("ClassName", "WaterBottle")),
                "QuantityPercent": -1,
                "MinQuantityPercent": -1,
            } for it in req]
        else:
            del_item = qspec.get("delivery_item", "ExpansionBanknoteHryvnia")
            colls = [{"Amount": 1, "ClassName": del_item, "QuantityPercent": -1, "MinQuantityPercent": -1}]
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_DELIVERY,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "Collections": colls,
            "ShowDistance": 1,
            "AddItemsToNearbyMarketZone": 0,
            "MaxDistance": 35.0,
            "MarkerName": site_name,
        }

    if obj_type == OBJ_TYPE_COLLECTION:
        req = qspec.get("items_required")
        if req:
            colls = [{
                "Amount": int(it.get("amount", it.get("Amount", 1))),
                "ClassName": it.get("class", it.get("ClassName", "Tomato")),
                "QuantityPercent": -1,
                "MinQuantityPercent": -1,
            } for it in req]
        else:
            colls = [{"Amount": 1, "ClassName": "SparkPlug", "QuantityPercent": -1, "MinQuantityPercent": -1}]
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_COLLECTION,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "Collections": colls,
            "ShowDistance": 1,
            "AddItemsToNearbyMarketZone": 0,
            "NeedAnyCollection": 0,
        }

    if obj_type == OBJ_TYPE_TREASURE:
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_TREASURE,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "Position": [round(x, 2), round(y, 2), round(z, 2)],
            "MaxDistance": 50.0,
            "MarkerName": site_name,
            "ShowDistance": 1,
            "ContainerClass": "ExpansionSeaChest",
            "LootItems": [
                {"Amount": 1, "ClassName": "SalineBagIV", "Chance": 1.0},
                {"Amount": 1, "ClassName": "Compass", "Chance": 1.0},
                {"Amount": 2, "ClassName": "BandageDressing", "Chance": 1.0},
            ],
        }

    # Default fallback: travel objective
    return {
        "ConfigVersion": 28,
        "ID": obj_id,
        "ObjectiveType": OBJ_TYPE_TRAVEL,
        "ObjectiveText": text,
        "TimeLimit": -1,
        "Active": 1,
        "Position": [round(x, 2), round(y, 2), round(z, 2)],
        "MaxDistance": 40.0,
        "MarkerName": site_name,
        "ShowDistance": 1,
        "TriggerOnEnter": 1,
        "TriggerOnExit": 0,
    }


def build_quest_json(quest_id: int, qspec: dict, obj_id: int, obj_type: int,
                     giver_npc_id: int, turn_in_npc_id: int) -> dict:
    """Expansion Quest JSON (ConfigVersion 22)."""
    rewards = []
    raw_rewards = qspec.get("rewards", [])
    for r in raw_rewards:
        cls_name = r.get("ClassName", r.get("class", "BandageDressing"))
        amt = int(r.get("Amount", r.get("amount", 1)))
        rewards.append({
            "ClassName": cls_name,
            "Amount": amt,
            "Attachments": [],
            "DamagePercent": 0,
            "HealthPercent": 100,
            "QuestID": -1,
            "Chance": 1.0,
        })
    rep_rewards = qspec.get("reputation_rewards", qspec.get("reputation", {}))
    pre_quests = [int(qspec["pre_quest"])] if "pre_quest" in qspec and int(qspec["pre_quest"]) > 0 else []

    descriptions = qspec.get("descriptions")
    if not descriptions or len(descriptions) < 3:
        briefing = qspec.get("briefing", qspec.get("text", ""))
        in_prog = qspec.get("in_progress", "Follow the parameters logged in your mission journal.")
        comp = qspec.get("completion", "Objective complete. Report back for debriefing and reward.")
        descriptions = [briefing, in_prog, comp]

    return {
        "ConfigVersion": 22,
        "ID": quest_id,
        "Type": 1,
        "Title": qspec["title"],
        "Descriptions": descriptions,
        "ObjectiveText": qspec.get("objective_text", qspec.get("text", "")),
        "FollowUpQuest": int(qspec.get("follow_up", -1)),
        "Repeatable": 1 if qspec.get("repeatable", False) else 0,
        "IsDailyQuest": 1 if qspec.get("daily", False) else 0,
        "IsWeeklyQuest": 0,
        "CancelQuestOnPlayerDeath": 1 if qspec.get("cancel_on_death", True) else 0,
        "Autocomplete": 0,
        "IsGroupQuest": 0,
        "ObjectSetFileName": "",
        "QuestItems": [],
        "Rewards": rewards,
        "NeedToSelectReward": 0,
        "RandomReward": 0,
        "RandomRewardAmount": -1,
        "RewardsForGroupOwnerOnly": 1,
        "RewardBehavior": 0,
        "QuestGiverIDs": [giver_npc_id],
        "QuestTurnInIDs": [turn_in_npc_id],
        "IsAchievement": 0,
        "Objectives": [
            {
                "ConfigVersion": 28,
                "ID": obj_id,
                "ObjectiveType": obj_type,
            }
        ],
        "QuestColor": 0,
        "ReputationReward": 0,
        "ReputationRequirement": -1,
        "PreQuestIDs": pre_quests,
        "RequiredFaction": "",
        "FactionReward": "",
        "PlayerNeedQuestItems": 1,
        "DeleteQuestItems": 1 if obj_type == OBJ_TYPE_DELIVERY else 0,
        "SequentialObjectives": 1,
        "FactionReputationRequirements": {},
        "FactionReputationRewards": rep_rewards,
        "SuppressQuestLogOnCompetion": 0,
        "Active": 1,
    }


def build_dialogue_json(npc_info: dict, trader_id: int = 0,
                        recent_events: list[str] | None = None,
                        contested_sites: list[str] | None = None,
                        goals_summary: dict | None = None) -> dict:
    """Dialogue Framework branching dialogue tree for an NPC."""
    npc_id = npc_info["id"]
    name = npc_info["name"]

    # Dynamic War Intel
    event_summary = " ".join(recent_events[:2]) if recent_events else "The front lines remain contested across the desert basin."
    front_text = f"Contested strongholds: {', '.join(contested_sites)}." if contested_sites else "No major pitched sieges reported this hour."
    intel_text = f"{npc_info.get('lore', '')} Currently: {event_summary} {front_text}"

    # Standing & Rules of Engagement
    standing_text = f"{npc_info.get('standing_info', '')} Remember: maintaining 50+ reputation ensures safe conduct and unlocks trusted barter."

    # Regional Survival Advice
    survival_text = npc_info.get("survival_tip", "Stay hydrated, watch the high ridges, and never travel without a working compass.")

    # Community Goals Status (for Settler contacts)
    goals_text = "The settlement infrastructure relies on collective player contributions."
    if goals_summary and goals_summary.get("projects"):
        projs = goals_summary["projects"]
        status_bits = [f"{p['name']}: {p['current']}/{p['target']} {p['unit']} ({p['percent']}%)" for p in projs[:3]]
        goals_text = f"Qalat-e Lut Compound Status: {'; '.join(status_bits)}. Delivering water, lumber, and medicine unlocks permanent compound perks."

    # Inter-faction Politics & Lore
    politics_text = npc_info.get("politics", "Out here, each faction fights for its own survival. Mind your allegiances.")

    # Response options from Root Node (Node 1)
    root_responses = [
        {
            "Text": "What tasks or contracts do you have available?",
            "NextNodeID": 0,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "SHOW_QUEST_LIST",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        },
    ]

    if trader_id > 0:
        root_responses.append({
            "Text": "I'd like to see what goods you have to barter.",
            "NextNodeID": 0,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "OPEN_TRADER_MENU",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        })

    root_responses.extend([
        {
            "Text": "What is the tactical situation across the Badlands?",
            "NextNodeID": 2,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "NONE",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        },
        {
            "Text": "Can you share any survival advice for this region?",
            "NextNodeID": 4,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "NONE",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        },
        {
            "Text": "How does your faction view the other groups in the sector?",
            "NextNodeID": 3,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "NONE",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        },
    ])

    if npc_info.get("faction") == "Settlers":
        root_responses.append({
            "Text": "How are the settlement survival reserves holding up?",
            "NextNodeID": 5,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "NONE",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        })
        root_responses.append({
            "Text": "Who can I hire or recruit to join my expedition squad?",
            "NextNodeID": 6,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "NONE",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        })

    root_responses.append({
        "Text": "Safe travels.",
        "NextNodeID": 0,
        "RequiredQuestID": -1,
        "HideAfterQuestID": -1,
        "QuestID": -1,
        "ShowWhileQuestID": -1,
        "ShowWhileQuestState": "",
        "ActionType": "END_CONVERSATION",
        "RequiredVars": [],
        "SetVars": [],
        "RequiredItems": [],
        "ShowFromHour": -1,
        "ShowToHour": -1,
        "MaxUses": 0,
        "UsesKey": "",
    })

    def back_to_root():
        return {
            "Text": "Understood. Let us return to other matters.",
            "NextNodeID": 1,
            "RequiredQuestID": -1,
            "HideAfterQuestID": -1,
            "QuestID": -1,
            "ShowWhileQuestID": -1,
            "ShowWhileQuestState": "",
            "ActionType": "NONE",
            "RequiredVars": [],
            "SetVars": [],
            "RequiredItems": [],
            "ShowFromHour": -1,
            "ShowToHour": -1,
            "MaxUses": 0,
            "UsesKey": "",
        }

    nodes = [
        # Node 1: Greeting & Main Menu
        {
            "ID": 1,
            "Type": "STANDARD",
            "SpeakerText": npc_info["greeting"],
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": root_responses,
        },
        # Node 2: Tactical Intelligence
        {
            "ID": 2,
            "Type": "STANDARD",
            "SpeakerText": intel_text,
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
                {
                    "Text": "Let me see the contracts for these sectors.",
                    "NextNodeID": 0,
                    "RequiredQuestID": -1,
                    "HideAfterQuestID": -1,
                    "QuestID": -1,
                    "ShowWhileQuestID": -1,
                    "ShowWhileQuestState": "",
                    "ActionType": "SHOW_QUEST_LIST",
                    "RequiredVars": [],
                    "SetVars": [],
                    "RequiredItems": [],
                    "ShowFromHour": -1,
                    "ShowToHour": -1,
                    "MaxUses": 0,
                    "UsesKey": "",
                },
                back_to_root(),
            ],
        },
        # Node 3: Standing, Rules & Politics
        {
            "ID": 3,
            "Type": "STANDARD",
            "SpeakerText": f"{standing_text} {politics_text}",
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
                {
                    "Text": "How can I earn standing with you?",
                    "NextNodeID": 0,
                    "RequiredQuestID": -1,
                    "HideAfterQuestID": -1,
                    "QuestID": -1,
                    "ShowWhileQuestID": -1,
                    "ShowWhileQuestState": "",
                    "ActionType": "SHOW_QUEST_LIST",
                    "RequiredVars": [],
                    "SetVars": [],
                    "RequiredItems": [],
                    "ShowFromHour": -1,
                    "ShowToHour": -1,
                    "MaxUses": 0,
                    "UsesKey": "",
                },
                back_to_root(),
            ],
        },
        # Node 4: Regional Survival Knowledge
        {
            "ID": 4,
            "Type": "STANDARD",
            "SpeakerText": survival_text,
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [back_to_root()],
        },
        # Node 5: Settlement Community Projects
        {
            "ID": 5,
            "Type": "STANDARD",
            "SpeakerText": goals_text,
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
                {
                    "Text": "I'm ready to contribute supplies.",
                    "NextNodeID": 0,
                    "RequiredQuestID": -1,
                    "HideAfterQuestID": -1,
                    "QuestID": -1,
                    "ShowWhileQuestID": -1,
                    "ShowWhileQuestState": "",
                    "ActionType": "SHOW_QUEST_LIST",
                    "RequiredVars": [],
                    "SetVars": [],
                    "RequiredItems": [],
                    "ShowFromHour": -1,
                    "ShowToHour": -1,
                    "MaxUses": 0,
                    "UsesKey": "",
                },
                back_to_root(),
            ],
        },
        # Node 6: Hirable Companions & Specialists
        {
            "ID": 6,
            "Type": "STANDARD",
            "SpeakerText": "We have four specialists stationed here at Qalat-e Lut ready to join your squad: Soran the Scout (North Watchtower), Kaveh the Sentinel (South Gate), Dr. Yasmin (Clinic), and Rostam the Scavenger (West Workshop). Bring them provisions or complete their enlistment contracts, and they'll follow your command across the badlands. If dismissed, they return here to defend our walls.",
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
                {
                    "Text": "Let me see the enlistment contracts.",
                    "NextNodeID": 0,
                    "RequiredQuestID": -1,
                    "HideAfterQuestID": -1,
                    "QuestID": -1,
                    "ShowWhileQuestID": -1,
                    "ShowWhileQuestState": "",
                    "ActionType": "SHOW_QUEST_LIST",
                    "RequiredVars": [],
                    "SetVars": [],
                    "RequiredItems": [],
                    "ShowFromHour": -1,
                    "ShowToHour": -1,
                    "MaxUses": 0,
                    "UsesKey": "",
                },
                back_to_root(),
            ],
        },
    ]

    return {
        "ID": npc_id,
        "NPCIDs": [npc_id],
        "TraderIDs": [trader_id] if trader_id > 0 else [],
        "TraderClassNames": [],
        "TraderPositions": [],
        "TraderPositionRadius": 8.0,
        "TraderMinKeyMatches": 1,
        "P2PTraderIDs": [],
        "AIPatrolID": 0,
        "AIPatrolSubID": 0,
        "SpeakerName": name,
        "ReputationVar": "",
        "ReputationMax": 0,
        "ReputationTiers": [],
        "LocKey": "",
        "RootNodeID": 1,
        "GreetingVoiceLineIDs": ["Example_Greeting_1"],
        "FarewellVoiceLineIDs": ["Example_Farewell_1"],
        "QuestListTexts": [],
        "NoQuestsTexts": [],
        "NoQuestsBackTexts": [],
        "NoQuestsLeaveTexts": [],
        "NoQuestsVoiceLineIDs": [],
        "QuestListBackTexts": [],
        "OfferBackTexts": [],
        "InProgressBackTexts": [],
        "TurnInBackTexts": [],
        "Stages": [],
        "Nodes": nodes,
    }


def compile_campaign(map_name: str, led: WarLedger, plan: dict,
                     dry_run: bool = False) -> dict[str, int]:
    """Compile and write all live Quests, Objectives, NPCs, Traders, and Dialogues."""
    mission_dir = active.mission_dir(map_name)
    prof_dir = ROOT / "server" / "profiles"
    exp_quests_dir = prof_dir / "ExpansionMod" / "Quests"
    exp_traders_dir = prof_dir / "ExpansionMod" / "Traders"
    mission_traders_dir = mission_dir / "expansion" / "traders"
    dialog_dir = prof_dir / "DialogFramework" / "Dialogues"

    locs = led.locations()
    sampler = get_ground_sampler(map_name)

    stats = {"quests": 0, "objectives": 0, "npcs": 0, "traders": 0, "dialogues": 0}

    # 1. Clean existing generated quest & dialogue directories
    quests_out = exp_quests_dir / "Quests"
    npcs_out = exp_quests_dir / "NPCs"
    objs_root = exp_quests_dir / "Objectives"

    if not dry_run:
        quests_out.mkdir(parents=True, exist_ok=True)
        npcs_out.mkdir(parents=True, exist_ok=True)
        objs_root.mkdir(parents=True, exist_ok=True)
        exp_traders_dir.mkdir(parents=True, exist_ok=True)
        mission_traders_dir.mkdir(parents=True, exist_ok=True)
        dialog_dir.mkdir(parents=True, exist_ok=True)

        # Clear old generated quest and npc files to prevent orphans
        for old in quests_out.glob("Quest_*.json"):
            old.unlink(missing_ok=True)
        for old in npcs_out.glob("QuestNPC_*.json"):
            old.unlink(missing_ok=True)
        for old in mission_traders_dir.glob("Trader_*.json"):
            old.unlink(missing_ok=True)

    # 2. Load configured NPCs and deploy all 7 fixed contacts
    quests_cfg = active.load_yaml("presets/quests.yaml")
    all_npcs = load_npc_profiles(quests_cfg)

    deployed_npcs: dict[int, dict] = {}
    for nid_str, prof in all_npcs.items():
        nid = int(prof["id"])
        pos_raw = prof.get("pos", [7560.0, 0.0, 8720.0])
        px, pz = pos_raw[0], pos_raw[2]
        py = sampler(px, pz)
        if py <= 0.0:
            py = 180.0
        pos = [round(px, 2), round(py, 2), round(pz, 2)]
        deployed_npcs[nid] = {
            "prof": prof,
            "pos": pos,
            "site": prof.get("role_site", "Settler Haven"),
            "yaw": prof.get("heading", 0.0),
        }

    # 3. Compile Fixed Story Progression Quests
    fixed_quests_cfg = quests_cfg.get("fixed_quests", {})
    for qid_raw, q in fixed_quests_cfg.items():
        qid = int(qid_raw)
        obj_type_str = q.get("objective_type", "DELIVERY")
        obj_type = OBJ_MAP.get(obj_type_str, OBJ_TYPE_DELIVERY)
        dir_name, prefix = DIR_MAP[obj_type]

        giver_id = int(q.get("npc_giver", 1))
        turnin_id = int(q.get("npc_turnin", giver_id))
        giver_info = deployed_npcs.get(giver_id, deployed_npcs[1])

        # Target coordinates: specific target_pos or target_site or giver position
        if "target_pos" in q:
            tx, tz = q["target_pos"][0], q["target_pos"][2]
        elif "target_site" in q and q["target_site"] in locs:
            tx, tz = locs[q["target_site"]][:2]
        else:
            tx, tz = giver_info["pos"][0], giver_info["pos"][2]
        ty = sampler(tx, tz)
        if ty <= 0.0:
            ty = 180.0
        target_pos = [round(tx, 2), round(ty, 2), round(tz, 2)]
        target_site = q.get("target_site", giver_info["site"])

        obj_id = qid
        obj_json = build_objective(
            obj_type=obj_type,
            obj_id=obj_id,
            text=q.get("objective_text", q.get("title", "")),
            pos=target_pos,
            site_name=target_site,
            faction_name="DZDSJackals",
            qspec=q,
        )

        quest_json = build_quest_json(
            quest_id=qid,
            qspec=q,
            obj_id=obj_id,
            obj_type=obj_type,
            giver_npc_id=giver_id,
            turn_in_npc_id=turnin_id,
        )

        if not dry_run:
            obj_dir = objs_root / dir_name
            obj_dir.mkdir(parents=True, exist_ok=True)
            (obj_dir / f"Objective_{prefix}_{obj_id}.json").write_text(json.dumps(obj_json, indent=4) + "\n")
            (quests_out / f"Quest_{qid}.json").write_text(json.dumps(quest_json, indent=4) + "\n")

        stats["quests"] += 1
        stats["objectives"] += 1

    # 4. Compile Live Dynamic Front-Line Quests
    live_quests = plan.get("quests", [])
    seen_qids = set(int(k) for k in fixed_quests_cfg.keys())
    for idx, q in enumerate(live_quests):
        base_id = q.get("id", 501)
        qid = base_id
        while qid in seen_qids:
            qid += 1
        seen_qids.add(qid)

        obj_type_str = q.get("objective", "TRAVEL")
        obj_type = OBJ_MAP.get(obj_type_str, OBJ_TYPE_TRAVEL)
        dir_name, prefix = DIR_MAP[obj_type]

        target_site = q["site"]
        giver = q.get("giver", "Settlers")
        giver_site = q.get("giver_site", target_site)

        # Map giver faction to canonical deployed NPC
        giver_npc_key = FACTION_NPC_KEY_MAP.get(giver, "1")
        if giver == "Peacekeepers" and ("Base" in giver_site or "Southwest" in giver_site):
            giver_npc_key = "3"  # Dr. Al-Mansoor at Southwest Base
        elif giver == "Settlers" and "Haven" in giver_site:
            giver_npc_key = "6"  # Scout Farid at Settler Haven

        npc_id = int(giver_npc_key)
        giver_info = deployed_npcs.get(npc_id, deployed_npcs[1])

        tx, tz = locs.get(target_site, [7560.0, 8720.0])[:2]
        ty = sampler(tx, tz)
        if ty <= 0.0:
            ty = 180.0
        target_pos = [round(tx, 2), round(ty, 2), round(tz, 2)]

        obj_id = qid
        obj_json = build_objective(
            obj_type=obj_type,
            obj_id=obj_id,
            text=q["text"],
            pos=target_pos,
            site_name=target_site,
            faction_name="DZDSJackals" if "Jackal" in target_site or "Pileup" in target_site else "DZDSRust" if "Rust" in target_site or "Cement" in target_site else "DZDSJackals",
            qspec=q,
        )

        quest_json = build_quest_json(
            quest_id=qid,
            qspec=q,
            obj_id=obj_id,
            obj_type=obj_type,
            giver_npc_id=npc_id,
            turn_in_npc_id=npc_id,
        )

        if not dry_run:
            obj_dir = objs_root / dir_name
            obj_dir.mkdir(parents=True, exist_ok=True)
            (obj_dir / f"Objective_{prefix}_{obj_id}.json").write_text(json.dumps(obj_json, indent=4) + "\n")
            (quests_out / f"Quest_{qid}.json").write_text(json.dumps(quest_json, indent=4) + "\n")

        stats["quests"] += 1
        stats["objectives"] += 1

    # 5. Compile Traders and Deployed Trader Spawns
    trader_plan = plan.get("traders", [])

    for t in trader_plan:
        tid = t["trader"]
        t_def = TRADER_DEFS.get(tid)
        if not t_def:
            continue

        site = t.get("site")
        is_open = t.get("status") in ("open", "relocated") and bool(site)

        # Profile trader definition
        trader_json = {
            "m_Version": 13,
            "DisplayName": t_def["display"],
            "MinRequiredReputation": 0,
            "MaxRequiredReputation": 2147483647,
            "RequiredFaction": t_def.get("faction", ""),
            "RequiredCompletedQuestID": t_def.get("required_quest", -1),
            "TraderIcon": t_def["icon"],
            "Currencies": t_def["currencies"],
            "DisplayCurrencyValue": 1,
            "DisplayCurrencyName": "",
            "UseCategoryOrder": 0,
            "Categories": t_def["categories"],
            "Items": {},
        }

        if not dry_run:
            (exp_traders_dir / t_def["file"]).write_text(json.dumps(trader_json, indent=4) + "\n")

        # In-world spawn if open
        if is_open and site in locs:
            npc_id = t_def.get("npc_id", t_def["id"])
            if npc_id in deployed_npcs:
                deployed_npcs[npc_id]["trader_id"] = t_def["id"]
                trader_pos = list(deployed_npcs[npc_id]["pos"])
                sx, sz = trader_pos[0], trader_pos[2]
                sy = trader_pos[1]
            else:
                sx, sz = locs[site][:2]
                sox, soz = 10.0, 10.0
                sy = sampler(sx + sox, sz + soz)
                if sy <= 0.0:
                    sy = 180.0
                trader_pos = [round(sx + sox, 2), round(sy, 2), round(sz + soz, 2)]

            trader_spawn = {
                "m_Version": 8,
                "m_TraderID": t_def["id"],
                "m_ClassName": "ExpansionTraderAIIrena" if t_def["id"] % 2 == 1 else "ExpansionTraderAIDenis",
                "m_Position": trader_pos,
                "m_Orientation": [45.0, 0.0, 0.0],
                "m_LoadoutFile": "DZDS_Settlers" if t_def["id"] in (1, 4) else "DZDS_Peacekeepers" if t_def["id"] == 2 else "DZDS_Rust",
                "m_VehicleSpawnPosition": [round(sx + 20, 2), round(sy, 2), round(sz + 20, 2)],
                "m_WatercraftSpawnPosition": [0.0, 0.0, 0.0],
                "m_AircraftSpawnPosition": [0.0, 0.0, 0.0],
                "m_DisplayName": t_def["display"],
                "m_DisplayIcon": t_def["icon"],
                "m_Faction": "InvincibleObservers",
                "m_Waypoints": [],
                "m_EmoteID": 46,
                "m_EmoteIsStatic": 1,
                "m_RequiredFaction": t_def.get("faction", ""),
                "m_UseReputation": 0,
                "m_MinRequiredReputation": 0,
                "m_MaxRequiredReputation": 2147483647,
                "m_RequiredCompletedQuestID": t_def.get("required_quest", -1),
                "m_IsGlobalTrader": 0,
                "m_Currencies": t_def["currencies"],
                "m_DisplayCurrencyValue": 1,
                "m_DisplayCurrencyName": "",
            }

            if not dry_run:
                (mission_traders_dir / f"Trader_{t_def['id']}.json").write_text(json.dumps(trader_spawn, indent=4) + "\n")

            # Link trader to deployed NPC
            npc_id = t_def.get("npc_id", t_def["id"])
            if npc_id in deployed_npcs:
                deployed_npcs[npc_id]["trader_id"] = t_def["id"]

        stats["traders"] += 1

    # 6. Compile Quest NPCs & Branching Dialogue Framework Trees
    recent_events = led.recent_events(4)
    contested_sites = [s for s, h in led.s.control.items() if h == "contested"]
    goals_mgr = survival_goals.get_manager()
    goals_summary = goals_mgr.get_summary()

    for npc_id, info in deployed_npcs.items():
        prof = info["prof"]
        pos = info["pos"]
        yaw = info.get("yaw", 0.0)
        trader_id = info.get("trader_id", 0)

        npc_json = build_quest_npc(prof, pos, yaw=yaw)
        dialogue_json = build_dialogue_json(
            prof,
            trader_id=trader_id,
            recent_events=recent_events,
            contested_sites=contested_sites,
            goals_summary=goals_summary,
        )

        if not dry_run:
            # Write Quest NPC
            (npcs_out / f"QuestNPC_{npc_id}.json").write_text(json.dumps(npc_json, indent=4) + "\n")

            # Write Dialogue Framework
            npc_dlg_dir = dialog_dir / f"NPC_{npc_id}"
            npc_dlg_dir.mkdir(parents=True, exist_ok=True)
            (npc_dlg_dir / "Dialogue.json").write_text(json.dumps(dialogue_json, indent=4) + "\n")

        stats["npcs"] += 1
        stats["dialogues"] += 1

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=active.map_name())
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    import front_plan

    led = WarLedger.load_or_new(a.map)
    traders_cfg = front_plan.load("presets/traders.yaml")
    quests_cfg = front_plan.load("presets/quests.yaml")

    plan = {
        "turn": led.s.turn,
        "traders": front_plan.plan_traders(led, traders_cfg),
        "quests": front_plan.plan_quests(led, quests_cfg),
    }

    stats = compile_campaign(a.map, led, plan, dry_run=a.dry_run)
    prefix = "[DRY RUN] " if a.dry_run else ""
    print(f"{prefix}Campaign Compiled ({a.map}): {stats['quests']} live quest(s), {stats['objectives']} objective(s), "
          f"{stats['npcs']} quest NPC(s), {stats['traders']} barter trader(s), {stats['dialogues']} dialogue tree(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
