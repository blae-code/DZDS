/**
 * AI War Zones (3521304609) resolves a team's faction with a switch over Expansion's built-in
 * factions and turns every other name into West. With our DZDSJackals/DZDSRust/... both teams of
 * every zone were West: friendly to each other, so no battle, and hostile to the tribal patrols
 * nearby (live ADM 2026-10-23, Southern Barracks). Its author left AYSAsetFaction overridable for
 * exactly this. The mod also spawns AI at the y the config gives, and an estimated y put teams in
 * mid-air (12 m at Southern Barracks, 100 m on Northern Dam): they fell, broke legs and looped
 * unconscious. Spawns now drop to the first floor below the configured point.
 * config.cpp requires "AIWarZones" so this compiles after it; drop both if the mod is removed
 * (tests/test_dzds_contract.py checks both ways). presets/zone_events.yaml `faction_names: custom`
 * once this build is live.
 */
modded class AIWarZoneInstance
{
	override void AYSAsetFaction(string faction, eAIBase expansionAI)
	{
		eAIFaction f;
		switch (faction)
		{
			case "dzdssettlers":     f = new eAIFactionDZDSSettlers(); break;
			case "dzdspeacekeepers": f = new eAIFactionDZDSPeacekeepers(); break;
			case "dzdsjackals":      f = new eAIFactionDZDSJackals(); break;
			case "dzdskarkas":       f = new eAIFactionDZDSKarkas(); break;
			case "dzdsrust":         f = new eAIFactionDZDSRust(); break;
		}
		if (f)
		{
			expansionAI.GetGroup().SetFaction(f);
			return;
		}
		super.AYSAsetFaction(faction, expansionAI);
	}

	override eAIBase AYSAspawnEAI(string loadout, vector position, string faction, int activity, vector targetPos, bool team)
	{
		return super.AYSAspawnEAI(loadout, DZDSWorld.Floor(position), faction, activity, targetPos, team);
	}
}
