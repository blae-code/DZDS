/**
 * Base respawns (Blae, 2026-10-22): every territory flag in the world, so the mission's
 * arrivals code (init.c PickBase) can wake a respawning player at their base without scanning
 * the map. Flags add themselves on EEInit (built or loaded from persistence) and leave on
 * EEDelete; whether one is raised is checked when the list is read.
 * Not vanilla's Mission.m_ActiveRefresherLocations: after a restart a raised flag loads with
 * m_RefresherActive already true, so it never re-enters that list on the server.
 * config.cpp defines DZDS_BASES so init.c can tell whether this version of @DZDS is loaded.
 */
class DZDSBases
{
	static ref array<TerritoryFlag> s_Flags = new array<TerritoryFlag>;

	static void Add(TerritoryFlag f)
	{
		if (f && s_Flags.Find(f) == -1)
			s_Flags.Insert(f);
	}

	static void Remove(TerritoryFlag f)
	{
		int i = s_Flags.Find(f);
		if (i != -1)
			s_Flags.Remove(i);
	}

	// Pole built, a flag on it, raised at least partway. "flag_mast" is 0 at the top and 1 at
	// the bottom; vanilla lowers it as the refresh time runs out, so an abandoned base drops out.
	static bool IsRaised(TerritoryFlag f)
	{
		if (!f || f.IsRuined() || !f.GetConstruction() || !f.GetConstruction().IsPartConstructed("pole"))
			return false;
		if (!f.FindAttachmentBySlotName("Material_FPole_Flag"))
			return false;
		return f.GetAnimationPhase("flag_mast") < 1;
	}

	// The raised flag nearest `pos` on the ground plane, or null.
	static TerritoryFlag NearestRaised(vector pos)
	{
		TerritoryFlag best = null;
		float bestDist = -1;
		foreach (TerritoryFlag f : s_Flags)
		{
			if (!IsRaised(f))
				continue;
			vector fp = f.GetPosition();
			float dx = fp[0] - pos[0];
			float dz = fp[2] - pos[2];
			float d = dx * dx + dz * dz;
			if (bestDist < 0 || d < bestDist)
			{
				best = f;
				bestDist = d;
			}
		}
		return best;
	}

	static int Count()
	{
		return s_Flags.Count();
	}

	static int RaisedCount()
	{
		int n = 0;
		foreach (TerritoryFlag f : s_Flags)
		{
			if (IsRaised(f))
				n++;
		}
		return n;
	}
}

modded class TerritoryFlag
{
	override void EEInit()
	{
		super.EEInit();
		if (GetGame().IsServer())
			DZDSBases.Add(this);
	}

	override void EEDelete(EntityAI parent)
	{
		DZDSBases.Remove(this);
		super.EEDelete(parent);
	}
}
