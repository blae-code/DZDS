/**
 * Reputation-aware tolerance (docs/FACTIONS.md §3, layer 5): Karkas and Rust AI leave alone a
 * PLAYER whose Hardline faction reputation with them reaches settings.json ToleranceReputation
 * (0 = off). Per player: one trusted settler may cross the ridge while their friend gets shot.
 * Reputation comes from Expansion Quests (FactionReputationRewards). Provocation still works:
 * Expansion's threat system makes tolerated players targets again if they aim at or hit the AI.
 * The Jackals never tolerate anyone.
 *
 * Expansion asks the AI's faction IsFriendlyEntity(player) when deciding whether a player is an
 * enemy (eAIBase.PlayerIsEnemy). The Karkas and Rust factions (3_Game) forward that question to
 * DZDSToleranceHook; this 4_World class answers it and is registered in MissionServer.OnInit.
 * Hardline's per-faction reputation API is guarded by these defines.
 */
#ifdef EXPANSIONMODHARDLINE
#ifdef EXPANSIONMODAI
class DZDSTolerance : DZDSToleranceHook
{
	override bool Check(eAIFaction faction, EntityAI other)
	{
		if (!DZDSWorld.s_Settings || DZDSWorld.s_Settings.ToleranceReputation <= 0)
			return false;

		PlayerBase player;
		if (!Class.CastTo(player, other) || player.IsAI())
			return false;

		return player.Expansion_GetFactionReputation(faction.GetTypeID()) >= DZDSWorld.s_Settings.ToleranceReputation;
	}
};
#endif
#endif
