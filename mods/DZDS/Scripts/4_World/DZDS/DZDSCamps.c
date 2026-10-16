/**
 * Camp respawns (Blae, 2026-10-16): every tent in the world, so the mission's arrivals code
 * (init.c PickCamp) can wake a respawning player beside the pitched tent nearest their death
 * without scanning the map. Tents add themselves on EEInit (spawned, crafted or loaded from
 * persistence) and leave on EEDelete; the pitched state is checked when the list is read.
 * Lives here, not in init.c: a mission script cannot mod a 4_World class ("Unknown type").
 * config.cpp defines DZDS_CAMPS so init.c can tell whether this version of @DZDS is loaded.
 */
class DZDSCamps
{
	static ref array<TentBase> s_Tents = new array<TentBase>;

	static void Add(TentBase t)
	{
		if (t && s_Tents.Find(t) == -1)
			s_Tents.Insert(t);
	}

	static void Remove(TentBase t)
	{
		int i = s_Tents.Find(t);
		if (i != -1)
			s_Tents.Remove(i);
	}

	// The pitched tent nearest `pos` within `radius` metres, or null.
	static TentBase Nearest(vector pos, float radius)
	{
		TentBase best = null;
		float bestDist = radius;
		foreach (TentBase t : s_Tents)
		{
			if (!t || t.IsRuined() || t.GetState() != TentBase.PITCHED)
				continue;
			float d = vector.Distance(pos, t.GetPosition());
			if (d <= bestDist)
			{
				best = t;
				bestDist = d;
			}
		}
		return best;
	}

	static int PitchedCount()
	{
		int n = 0;
		foreach (TentBase t : s_Tents)
		{
			if (t && t.GetState() == TentBase.PITCHED)
				n++;
		}
		return n;
	}
}

modded class TentBase
{
	override void EEInit()
	{
		super.EEInit();
		if (GetGame().IsServer())
			DZDSCamps.Add(this);
	}

	override void EEDelete(EntityAI parent)
	{
		DZDSCamps.Remove(this);
		super.EEDelete(parent);
	}
}
