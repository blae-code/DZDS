#!/usr/bin/env python3
"""Compile dynamic campaign files: Expansion Quests, Barter Traders, and Dialogue Framework.

Instantiates live front-line quests, barter traders, and interactive dialogue trees
from the war ledger and presets:
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

import active
import ground
import map_survey

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from gamemaster.ledger import WarLedger  # noqa: E402

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

# Standard NPC profiles for faction representatives
NPC_PROFILES = {
    "Settlers": {
        "id": 1,
        "name": "Elder David",
        "title": "Frontier Settler Elder",
        "class": "ExpansionQuestNPCAIDenis",
        "loadout": "DZDS_Settlers",
        "greeting": "Welcome to Settler Haven, traveler. The frontier is harsh, but we stand together.",
        "lore": "The Frontier Settlers came together from survivors of the old towns. We farm, repair, and hold our ground against highway raiders and the Syndicate.",
        "standing_info": "We trust survivors who defend our homesteads and trade fairly. Bring supplies or help break sieges to earn our trust.",
    },
    "Peacekeepers": {
        "id": 2,
        "name": "Commander Vance",
        "title": "Task Force Blue Shield Commander",
        "class": "ExpansionQuestNPCAIElias",
        "loadout": "DZDS_Peacekeepers_officer",
        "greeting": "Task Force Blue Shield Command. State your identity and business within the demilitarized zone.",
        "lore": "We operate under United Nations humanitarian mandates. We defend the Green Zones, escort aid, and maintain neutrality unless fired upon.",
        "standing_info": "Sign the Blue Shield Charter to unlock our Quartermaster. If standing drops below -30, we initiate a total lockdown.",
    },
    "Rust": {
        "id": 3,
        "name": "Foreman Grigori",
        "title": "Rust Syndicate Water Master",
        "class": "ExpansionQuestNPCAIElias",
        "loadout": "DZDS_Rust_foreman",
        "greeting": "Syndicate pump head. Water has a price in the Badlands. Keep your hands where I can see them.",
        "lore": "The Rust Syndicate controls the wells, the dams, and the fuel refineries. Out here, nothing runs without our blessing.",
        "standing_info": "Pay your maintenance parts toll to secure water rights. Once verified, our broker will trade fuel and clean water.",
    },
    "Karkas": {
        "id": 4,
        "name": "Elder Tariq",
        "title": "Karkas Clan Ridge Elder",
        "class": "ExpansionQuestNPCAIDenis",
        "loadout": "DZDS_Karkas_elder",
        "greeting": "The Karkas hold the heights. Only those who honor the mountain walk these ridges unmolested.",
        "lore": "We have lived in these mountain crags long before the collapse. The high ground is sacred, and our marksmen do not miss.",
        "standing_info": "Bring wild game and hunting tribute. Reach 50 clan reputation and our scouts will grant you safe passage across the ridges.",
    },
    "none": {
        "id": 5,
        "name": "The Smuggler",
        "title": "Desert Contraband Fence",
        "class": "ExpansionQuestNPCAIElias",
        "loadout": "DZDS_Settlers",
        "greeting": "Keep it quiet and keep it clean. No factions, no flags out here. Just honest trade.",
        "lore": "I trade with everyone: Settlers, Blue Shield, tribesmen. Gold, ammo, keys. If it's scarce, I find it.",
        "standing_info": "I deal in hard currency: ammunition. No questions asked, no allegiances required.",
    },
    "Peacekeepers_field": {
        "id": 6,
        "name": "Lieutenant Miller",
        "title": "Task Force Blue Shield Field Officer",
        "class": "ExpansionQuestNPCAIDenis",
        "loadout": "DZDS_Peacekeepers",
        "greeting": "Blue Shield Field Outpost. We monitor desert movements and coordinate supply runs.",
        "lore": "Our forward outposts maintain radar surveillance over the road junctions and track tribal war parties.",
        "standing_info": "Complete reconnaissance and escort contracts to support our peacekeeping presence.",
    },
    "Rust_works": {
        "id": 7,
        "name": "Overseer Radim",
        "title": "Syndicate Industrial Overseer",
        "class": "ExpansionQuestNPCAIDenis",
        "loadout": "DZDS_Rust",
        "greeting": "Syndicate Industrial Works. Scavenge or trade, but don't interfere with the machinery.",
        "lore": "We salvage cement, metals, and fuel from industrial wrecks. Heavy industry is the foundation of power.",
        "standing_info": "Supply our generators with spark plugs and wiring to maintain standing with the Syndicate.",
    },
}

TRADER_DEFS = {
    "frontier_exchange": {
        "id": 1,
        "file": "Frontier_Exchange.json",
        "display": "Frontier Exchange (Settlers Barter)",
        "npc_name": "Elder David",
        "icon": "Deliver",
        "faction": "DZDSSettlers",
        "required_quest": -1,
        "currencies": ["nail", "expansionbanknotehryvnia", "ammo_22", "ammo_9x19", "ammo_545x39", "ammo_762x39", "ammo_556x45"],
        "categories": ["Food", "Tools", "Supplies", "Backpacks", "Boots_And_Shoes", "Coats_And_Jackets"],
    },
    "un_quartermaster": {
        "id": 2,
        "file": "UN_Quartermaster.json",
        "display": "UN Quartermaster (Task Force Blue Shield)",
        "npc_name": "Commander Vance",
        "icon": "Medic Box",
        "faction": "",
        "required_quest": 101,  # un_intro
        "currencies": ["expansionbanknotehryvnia", "ammo_556x45", "ammo_9x19"],
        "categories": ["Medical", "Navigation", "Electronics", "Consumables", "Helmets", "Vests"],
    },
    "rust_broker": {
        "id": 3,
        "file": "Rust_Broker.json",
        "display": "Rust Syndicate Water & Parts Broker",
        "npc_name": "Foreman Grigori",
        "icon": "Car",
        "faction": "",
        "required_quest": 102,  # water_rights
        "currencies": ["ammo_762x39", "ammo_545x39", "ammo_9x19", "nail"],
        "categories": ["Vehicle_Parts", "Liquids", "Supplies", "Tools", "Batteries"],
    },
    "smuggler": {
        "id": 4,
        "file": "The_Smuggler.json",
        "display": "The Smuggler (Black Market Fence)",
        "npc_name": "The Smuggler",
        "icon": "Pistol",
        "faction": "",
        "required_quest": -1,
        "currencies": ["ammo_762x39", "ammo_545x39", "ammo_556x45", "ammo_9x19", "ammo_22"],
        "categories": ["Weapons", "Optics", "Magazines", "Muzzles", "Locks", "Special"],
    },
}


def get_ground_sampler(map_name: str) -> ground.Ground:
    """Build a terrain altitude sampler for the map."""
    mission_dir = active.mission_dir(map_name)
    map_groups = mission_dir / "mapgrouppos.xml"
    if map_groups.exists():
        return ground.Ground(map_survey.load_groups(map_groups))
    return ground.Ground()


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
                    "eAI_SurvivorM_Mirek",
                ],
                "NumberOfAI": 4,
                "Behaviour": 0,
                "Speed": 1,
                "UnderThreatSpeed": 2,
                "CanBeLooted": 1,
                "UnlimitedReload": 1,
                "SniperProneDistanceThreshold": 0.0,
                "AccuracyMin": 0.28,
                "AccuracyMax": 0.48,
                "ThreatDistanceLimit": 300.0,
                "DamageMultiplier": 1.0,
                "DamageReceivedMultiplier": 1.0,
                "MinDistRadius": 50.0,
                "MaxDistRadius": 400.0,
                "DespawnTime": 0.0,
                "RespawnTime": -1.0,
                "Waypoints": [
                    [round(x, 2), round(y, 2), round(z, 2)],
                    [round(x + 35, 2), round(y, 2), round(z + 35, 2)],
                    [round(x - 35, 2), round(y, 2), round(z - 35, 2)],
                ],
            },
        }

    if obj_type == OBJ_TYPE_AICAMP:
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_AICAMP,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "InfectedDeletionRadius": 300.0,
            "MaxDistance": -1.0,
            "MinDistance": -1.0,
            "AllowedWeapons": [],
            "AllowedDamageZones": [],
            "AISpawns": [
                {
                    "Name": f"Camp_{site_name.replace(' ', '_')}",
                    "Persist": 0,
                    "Faction": faction_name,
                    "Formation": "RANDOM",
                    "FormationScale": 1.5,
                    "FormationLooseness": 0.0,
                    "Loadout": "DZDS_Jackals",
                    "Units": [
                        "eAI_SurvivorM_Jose",
                        "eAI_SurvivorM_Hassan",
                        "eAI_SurvivorF_Helga",
                        "eAI_SurvivorM_Quinn",
                    ],
                    "NumberOfAI": 4,
                    "Behaviour": 0,
                    "Speed": 1,
                    "UnderThreatSpeed": 2,
                    "CanBeLooted": 1,
                    "UnlimitedReload": 1,
                    "SniperProneDistanceThreshold": 0.0,
                    "AccuracyMin": 0.28,
                    "AccuracyMax": 0.48,
                    "ThreatDistanceLimit": 300.0,
                    "DamageMultiplier": 1.0,
                    "DamageReceivedMultiplier": 1.0,
                    "MinDistRadius": 50.0,
                    "MaxDistRadius": 400.0,
                    "DespawnTime": 0.0,
                    "RespawnTime": -1.0,
                    "Waypoints": [[round(x, 2), round(y, 2), round(z, 2)]],
                }
            ],
        }

    if obj_type == OBJ_TYPE_TRAVEL:
        return {
            "ConfigVersion": 28,
            "ID": obj_id,
            "ObjectiveType": OBJ_TYPE_TRAVEL,
            "ObjectiveText": text,
            "TimeLimit": -1,
            "Active": 1,
            "Position": [round(x, 2), round(y, 2), round(z, 2)],
            "MaxDistance": 45.0,
            "MarkerName": site_name,
            "ShowDistance": 1,
            "TriggerOnEnter": 1,
            "TriggerOnExit": 0,
        }

    if obj_type == OBJ_TYPE_DELIVERY:
        req = (qspec or {}).get("items_required")
        if req:
            colls = [{"Amount": int(it.get("amount", it.get("Amount", 1))),
                      "ClassName": it.get("class", it.get("ClassName", "WaterBottle")),
                      "QuantityPercent": -1, "MinQuantityPercent": -1} for it in req]
        else:
            del_item = "SparkPlug" if "water" in text.lower() else "ExpansionBanknoteHryvnia" if "charter" in text.lower() or "dispatch" in text.lower() else "Ammo_762x54" if "karkas" in text.lower() or "tribute" in text.lower() else "BandageDressing"
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
            "MaxDistance": 30.0,
            "MarkerName": site_name,
        }

    if obj_type == OBJ_TYPE_COLLECTION:
        req = (qspec or {}).get("items_required")
        if req:
            colls = [{"Amount": int(it.get("amount", it.get("Amount", 1))),
                      "ClassName": it.get("class", it.get("ClassName", "Tomato")),
                      "QuantityPercent": -1, "MinQuantityPercent": -1} for it in req]
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
    for r in qspec.get("rewards", []):
        rewards.append({
            "ClassName": r["ClassName"],
            "Amount": int(r.get("Amount", 1)),
            "Attachments": [],
            "DamagePercent": 0,
            "HealthPercent": 100,
            "QuestID": -1,
            "Chance": 1.0,
        })
    rep_rewards = qspec.get("reputation_rewards", {})

    return {
        "ConfigVersion": 22,
        "ID": quest_id,
        "Type": 1,
        "Title": qspec["title"],
        "Descriptions": qspec["descriptions"] if len(qspec.get("descriptions", [])) >= 3 else [
            qspec.get("text", ""),
            "Follow the mission parameters in your tactical log.",
            "Objective complete. Report back for debriefing and reward.",
        ],
        "ObjectiveText": qspec["text"],
        "FollowUpQuest": int(qspec.get("follow_up", -1)),
        "Repeatable": 1 if qspec.get("repeatable", True) else 0,
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
        "PreQuestIDs": [],
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
                        recent_events: list[str] | None = None) -> dict:
    """Dialogue Framework Dialogue JSON for an NPC."""
    npc_id = npc_info["id"]
    name = npc_info["name"]
    event_summary = " ".join(recent_events[:2]) if recent_events else "The front lines remain contested across the central desert."
    intel_text = f"{npc_info['lore']} Currently: {event_summary}"

    nodes = [
        {
            "ID": 1,
            "Type": "STANDARD",
            "SpeakerText": f"{npc_info['greeting']}",
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
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
                {
                    "Text": "I'd like to see what goods you have to barter.",
                    "NextNodeID": 0,
                    "RequiredQuestID": -1,
                    "HideAfterQuestID": -1,
                    "QuestID": -1,
                    "ShowWhileQuestID": -1,
                    "ShowWhileQuestState": "",
                    "ActionType": "OPEN_TRADER_MENU" if trader_id > 0 else "NONE",
                    "RequiredVars": [],
                    "SetVars": [],
                    "RequiredItems": [],
                    "ShowFromHour": -1,
                    "ShowToHour": -1,
                    "MaxUses": 0,
                    "UsesKey": "",
                } if trader_id > 0 else {
                    "Text": "Where can I find the nearest barter post?",
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
                    "Text": "How does your faction view the Frontier Settlers?",
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
                {
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
                },
            ],
        },
        {
            "ID": 2,
            "Type": "STANDARD",
            "SpeakerText": intel_text,
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
                {
                    "Text": "Tell me more about how we can work together.",
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
                {
                    "Text": "Back to our discussion.",
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
                },
            ],
        },
        {
            "ID": 3,
            "Type": "STANDARD",
            "SpeakerText": npc_info["standing_info"],
            "SpeakerTextMore": [],
            "VoiceLineIDs": [],
            "SpeakerLines": [],
            "Responses": [
                {
                    "Text": "Let me see those contracts.",
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
                {
                    "Text": "Understood. I will keep that in mind.",
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
                },
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

    # Map giver faction & site to NPC profile and position
    deployed_npcs: dict[int, dict] = {}

    def get_npc_for_giver(giver: str, giver_site: str) -> tuple[int, dict, list[float]]:
        prof_key = giver
        if giver == "Peacekeepers" and "Base" in giver_site:
            prof_key = "Peacekeepers_field"
        elif giver == "Rust" and "Cement" in giver_site:
            prof_key = "Rust_works"
        prof = NPC_PROFILES.get(prof_key, NPC_PROFILES["Settlers"])
        npc_id = prof["id"]

        gx, gz = locs.get(giver_site, [7560.0, 8720.0])[:2]
        # Offset NPC slightly from site centroid
        ox, oz = 6.0, 6.0
        gy = sampler(gx + ox, gz + oz)
        pos = [round(gx + ox, 2), round(gy, 2), round(gz + oz, 2)]
        return npc_id, prof, pos

    # 2. Compile Live Quests & Objectives
    live_quests = plan.get("quests", [])
    seen_qids = set()
    for idx, q in enumerate(live_quests):
        qid = q.get("id", 100 + idx)
        if qid in seen_qids:
            qid = qid + 500 + idx
        seen_qids.add(qid)
        obj_type_str = q.get("objective", "TRAVEL")
        obj_type = OBJ_MAP.get(obj_type_str, OBJ_TYPE_TRAVEL)
        dir_name, prefix = DIR_MAP[obj_type]

        target_site = q["site"]
        giver = q.get("giver", "Settlers")
        giver_site = q.get("giver_site", target_site)

        npc_id, npc_prof, npc_pos = get_npc_for_giver(giver, giver_site)
        deployed_npcs[npc_id] = {"prof": npc_prof, "pos": npc_pos, "site": giver_site}

        tx, tz = locs.get(target_site, [7560.0, 8720.0])[:2]
        ty = sampler(tx, tz)
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
            # Write objective
            obj_dir = objs_root / dir_name
            obj_dir.mkdir(parents=True, exist_ok=True)
            (obj_dir / f"Objective_{prefix}_{obj_id}.json").write_text(json.dumps(obj_json, indent=4) + "\n")

            # Write quest
            (quests_out / f"Quest_{qid}.json").write_text(json.dumps(quest_json, indent=4) + "\n")

        stats["quests"] += 1
        stats["objectives"] += 1

    # 3. Compile Traders and Deployed Trader Spawns
    trader_plan = plan.get("traders", [])
    trader_npc_map: dict[str, int] = {
        "frontier_exchange": 1,
        "un_quartermaster": 2,
        "rust_broker": 3,
        "smuggler": 5,
    }

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
            sx, sz = locs[site][:2]
            sox, soz = 10.0, 10.0
            sy = sampler(sx + sox, sz + soz)
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

            # Associate deployed NPC
            npc_id = trader_npc_map.get(tid, t_def["id"])
            npc_prof = NPC_PROFILES.get("Settlers" if tid == "frontier_exchange" else "Peacekeepers" if tid == "un_quartermaster" else "Rust" if tid == "rust_broker" else "none")
            if npc_prof:
                deployed_npcs[npc_id] = {"prof": npc_prof, "pos": trader_pos, "site": site, "trader_id": t_def["id"]}

        stats["traders"] += 1

    # 4. Compile Quest NPCs & Dialogue Framework trees
    recent_events = led.recent_events(4)

    for npc_id, info in deployed_npcs.items():
        prof = info["prof"]
        pos = info["pos"]
        trader_id = info.get("trader_id", 0)

        npc_json = build_quest_npc(prof, pos)
        dialogue_json = build_dialogue_json(prof, trader_id=trader_id, recent_events=recent_events)

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
