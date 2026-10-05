/**
 * Runtime diplomacy overrides for DZDS factions (docs/FACTIONS.md, "Dynamic diplomacy").
 *
 * The war ledger writes $profile:DZDS/diplomacy.json between restarts (tools/diplomacy.py);
 * it is read once, on first use after the server starts. Each entry overrides one direction of
 * IsFriendly(), e.g. a Karkas/Rust truce, or the UN treating Settlers as hostile after an
 * incident. Remember: for PLAYERS, Expansion asks the player's faction (DZDSSettlers).
 * No file (or on clients) = no overrides: the blueprint relations in DZDSFactions.c apply.
 */

class DZDSRelation
{
	string From;
	string To;
	bool Friendly;
};

class DZDSDiplomacyData
{
	ref array<ref DZDSRelation> Overrides;
};

class DZDSDiplomacy
{
	static const string PATH = "$profile:DZDS\\diplomacy.json";
	static ref map<string, bool> s_Overrides;

	//! -1 = no override, 0 = hostile, 1 = friendly
	static int Get(string from, string to)
	{
		if (!s_Overrides)
			Load();

		bool friendly;
		if (s_Overrides.Find(from + ">" + to, friendly))
		{
			if (friendly)
				return 1;
			return 0;
		}
		return -1;
	}

	static void Load()
	{
		s_Overrides = new map<string, bool>;
		if (!FileExist(PATH))
			return;

		DZDSDiplomacyData data = new DZDSDiplomacyData;
		JsonFileLoader<DZDSDiplomacyData>.JsonLoadFile(PATH, data);
		if (!data.Overrides)
			return;

		foreach (DZDSRelation r : data.Overrides)
		{
			s_Overrides.Set(r.From + ">" + r.To, r.Friendly);
		}
		Print("[DZDS] Loaded " + s_Overrides.Count() + " diplomacy override(s) from " + PATH);
	}
};
