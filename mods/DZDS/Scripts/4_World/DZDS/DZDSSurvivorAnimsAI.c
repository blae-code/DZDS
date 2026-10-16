/**
 * Survivor Animations (2918418331), as updated for 1.30 on 2026-10-15, calls
 * UpdateSAItemInHandsType() from CommandHandler every frame, and its AnimSetInt crashes the engine
 * ("Unhandled exception", Reason: Unknown) for every Expansion AI: quest NPCs, traders, patrols.
 * Proven on the local 1.30 server: deactivating the first NPC moved the crash to the next one.
 * AI never use SA's item-in-hands animation variable, so skip it for them. Players are untouched.
 * Remove once SA or Expansion AI fix it upstream (config.cpp requires SurvivorAnims for this).
 */
#ifdef SURVIVOR_ANIMS
modded class eAIBase
{
	override void UpdateSAItemInHandsType()
	{
	}
}
#endif
