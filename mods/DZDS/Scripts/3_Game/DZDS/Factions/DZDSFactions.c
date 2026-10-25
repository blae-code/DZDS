/**
 * DZDS custom factions for DayZ Expansion AI (docs/FACTIONS.md).
 *
 * Modelled on Expansion's built-in factions (DayZExpansion/AI/Scripts/3_Game/.../Factions).
 * Patrols reference these by name without the "eAIFaction" prefix, e.g. "Faction": "DZDSJackals".
 * Players join DZDSSettlers via AISettings.json "PlayerFactions": ["DZDSSettlers"].
 *
 * How Expansion uses these (from its source):
 *  - An AI decides a PLAYER is friendly by asking the player's faction:
 *    playerFaction.IsFriendly(aiFaction). So DZDSSettlers.IsFriendly() defines who leaves
 *    players alone.
 *  - Friendly is not unconditional: aiming at, hitting or shooting an AI raises its threat
 *    and it fights back (that's the UN's "armed neutrality").
 *  - m_IsGuard lowers threat perception (reacts to close/strong stimuli) and makes the
 *    faction recruitable only if AISettings.CanRecruitGuards is on.
 *  - Recruiting requires AISettings.CanRecruitFriendly and that the AI doesn't see you as an
 *    enemy, so Settlers (same faction as players) are recruitable; tribes never are.
 *  - tests/test_presets.py checks presets/factions.yaml stances against this file.
 *  - Every IsFriendly() first consults DZDSDiplomacy (runtime overrides written by the war
 *    ledger), then falls back to the blueprint relations below.
 */

//! Frontier Settlers: the players' faction and recruitable settler AI.
[eAIRegisterFaction(eAIFactionDZDSSettlers)]
class eAIFactionDZDSSettlers : eAIFaction
{
	void eAIFactionDZDSSettlers()
	{
		m_Loadout = "DZDS_Settlers";
	}

	override string GetDisplayName()
	{
		return "Frontier Settlers";
	}

	override bool IsFriendly(notnull eAIFaction other)
	{
		int o = DZDSDiplomacy.Get(GetName(), other.GetName());
		if (o >= 0)
			return o == 1;

		if (other.IsInherited(eAIFactionDZDSSettlers)) return true;
		if (other.IsInherited(eAIFactionDZDSPeacekeepers)) return true;
		if (other.IsPassive()) return true;
		return false;
	}
};

//! UN Peacekeeping Remnants (Task Force Blue Shield): disciplined, conditional neutrality.
[eAIRegisterFaction(eAIFactionDZDSPeacekeepers)]
class eAIFactionDZDSPeacekeepers : eAIFaction
{
	void eAIFactionDZDSPeacekeepers()
	{
		m_Loadout = "DZDS_Peacekeepers";
		m_IsGuard = true;
	}

	override string GetDisplayName()
	{
		return "UN Peacekeeping Remnants";
	}

	override bool IsFriendly(notnull eAIFaction other)
	{
		int o = DZDSDiplomacy.Get(GetName(), other.GetName());
		if (o >= 0)
			return o == 1;

		if (other.IsInherited(eAIFactionDZDSPeacekeepers)) return true;
		if (other.IsInherited(eAIFactionDZDSSettlers)) return true;
		if (other.IsPassive()) return true;
		return false;
	}
};

//! Tribe 1: the Jackal Cohort, lowland nomads and highway raiders.
[eAIRegisterFaction(eAIFactionDZDSJackals)]
class eAIFactionDZDSJackals : eAIFaction
{
	void eAIFactionDZDSJackals()
	{
		m_Loadout = "DZDS_Jackals";
	}

	override string GetDisplayName()
	{
		return "The Jackal Cohort";
	}

	override bool IsFriendly(notnull eAIFaction other)
	{
		int o = DZDSDiplomacy.Get(GetName(), other.GetName());
		if (o >= 0)
			return o == 1;

		if (other.IsInherited(eAIFactionDZDSJackals)) return true;
		if (other.IsPassive()) return true;
		return false;
	}
};

//! Tribe 2: the Karkas Clan, mountain hunters. Like Expansion's Shamans, wildlife leaves
//! them alone: they belong to the high country.
[eAIRegisterFaction(eAIFactionDZDSKarkas)]
class eAIFactionDZDSKarkas : eAIFaction
{
	void eAIFactionDZDSKarkas()
	{
		m_Loadout = "DZDS_Karkas";
	}

	override string GetDisplayName()
	{
		return "Karkas Mountain Clan";
	}

	override bool IsFriendly(notnull eAIFaction other)
	{
		int o = DZDSDiplomacy.Get(GetName(), other.GetName());
		if (o >= 0)
			return o == 1;

		if (other.IsInherited(eAIFactionDZDSKarkas)) return true;
		if (other.IsPassive()) return true;
		return false;
	}

	override bool IsFriendlyEntity(EntityAI other, DayZPlayer factionMember = null)
	{
		if (other.IsInherited(DayZCreatureAI))
			return true;
		return DZDSToleranceHook.Tolerates(this, other);
	}
};

//! Tribe 3: the Rust Syndicate, industrial cartel holding wells, fuel and rail.
[eAIRegisterFaction(eAIFactionDZDSRust)]
class eAIFactionDZDSRust : eAIFaction
{
	void eAIFactionDZDSRust()
	{
		m_Loadout = "DZDS_Rust";
	}

	override string GetDisplayName()
	{
		return "The Rust Syndicate";
	}

	override bool IsFriendly(notnull eAIFaction other)
	{
		int o = DZDSDiplomacy.Get(GetName(), other.GetName());
		if (o >= 0)
			return o == 1;

		if (other.IsInherited(eAIFactionDZDSRust)) return true;
		if (other.IsPassive()) return true;
		return false;
	}

	override bool IsFriendlyEntity(EntityAI other, DayZPlayer factionMember = null)
	{
		if (super.IsFriendlyEntity(other, factionMember))
			return true;
		return DZDSToleranceHook.Tolerates(this, other);
	}
};

//! Per-player tolerance (Karkas, Rust) needs PlayerBase and Hardline reputation, which live in
//! 4_World. A 4_World class cannot `modded class` these 3_Game factions (server compile error
//! "Unknown type", 2026-10-07), so 4_World registers an implementation here instead
//! (DZDSTolerance.c). No implementation registered = nobody is tolerated.
class DZDSToleranceHook
{
	static ref DZDSToleranceHook s_Impl;

	static bool Tolerates(eAIFaction faction, EntityAI other)
	{
		if (!s_Impl)
			return false;
		return s_Impl.Check(faction, other);
	}

	bool Check(eAIFaction faction, EntityAI other)
	{
		return false;
	}
};
