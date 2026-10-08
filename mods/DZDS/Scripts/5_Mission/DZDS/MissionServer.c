modded class MissionServer
{
	override void OnInit()
	{
		super.OnInit();
		DZDSWorld.Start();
#ifdef EXPANSIONMODHARDLINE
#ifdef EXPANSIONMODAI
		DZDSToleranceHook.s_Impl = new DZDSTolerance();
		Print("[DZDS] Reputation tolerance registered");
#endif
#endif
	}
};
