/**
 * DZDS world layer (docs/WAR_LEDGER.md, "Physical markers"; docs/LIVING_WORLD.md §6).
 *
 * Server only. Files live in $profile:DZDS\ and are written by the repo's tools:
 *   settings.json  AllowedClassNames (spawn allowlist), PollSeconds     (tools/dzds_profile.py)
 *   markers.json   objects marking who holds each site, placed at start  (tools/dzds_profile.py)
 *   queue\*.json   GM command files, executed then deleted               (src/gamemaster/dispatch.py)
 *
 * Markers are created without world persistence, so they are not duplicated across restarts.
 * Commands may only spawn allowlisted classnames; anything else is logged and ignored.
 */

class DZDSMarker
{
	string ClassName;
	float X;
	float Z;
	float Yaw;
};

class DZDSMarkerData
{
	ref array<ref DZDSMarker> Markers;
};

class DZDSCommand
{
	string Type;        //! "spawn" (more types later)
	string ClassName;
	float X;
	float Z;
	int Count;
};

class DZDSCommandFile
{
	ref array<ref DZDSCommand> Commands;
};

class DZDSSettings
{
	ref array<string> AllowedClassNames;
	int PollSeconds;
	int ToleranceReputation;   //! DZDSTolerance.c: 0 = off
};

class DZDSWorld
{
	static const string DIR = "$profile:DZDS\\";
	static ref DZDSSettings s_Settings;

	static void Start()
	{
		if (!GetGame().IsDedicatedServer())
			return;

		LoadSettings();
		SpawnMarkers();
		GetGame().GetCallQueue(CALL_CATEGORY_SYSTEM).CallLater(PollQueue, s_Settings.PollSeconds * 1000, true);
		Print("[DZDS] World layer started; polling " + DIR + "queue every " + s_Settings.PollSeconds + "s");
	}

	static void LoadSettings()
	{
		s_Settings = new DZDSSettings;
		string path = DIR + "settings.json";
		if (FileExist(path))
			JsonFileLoader<DZDSSettings>.JsonLoadFile(path, s_Settings);
		if (!s_Settings.AllowedClassNames)
			s_Settings.AllowedClassNames = new array<string>;
		if (s_Settings.PollSeconds < 2)
			s_Settings.PollSeconds = 10;
	}

	static vector Ground(float x, float z)
	{
		return Vector(x, GetGame().SurfaceY(x, z), z);
	}

	static void SpawnMarkers()
	{
		string path = DIR + "markers.json";
		if (!FileExist(path))
			return;

		DZDSMarkerData data = new DZDSMarkerData;
		JsonFileLoader<DZDSMarkerData>.JsonLoadFile(path, data);
		if (!data.Markers)
			return;

		int flags = ECE_PLACE_ON_SURFACE | ECE_CREATEPHYSICS | ECE_UPDATEPATHGRAPH | ECE_NOLIFETIME | ECE_NOPERSISTENCY_WORLD;
		int spawned = 0;
		foreach (DZDSMarker m : data.Markers)
		{
			Object obj = GetGame().CreateObjectEx(m.ClassName, Ground(m.X, m.Z), flags);
			if (!obj)
			{
				Print("[DZDS] Marker class not found: " + m.ClassName);
				continue;
			}
			obj.SetOrientation(Vector(m.Yaw, 0, 0));
			spawned++;
		}
		Print("[DZDS] Spawned " + spawned + " site marker(s)");
	}

	static void PollQueue()
	{
		string pattern = DIR + "queue\\*.json";
		string fileName;
		FileAttr attr;
		array<string> files = new array<string>;

		FindFileHandle handle = FindFile(pattern, fileName, attr, 0);
		if (handle)
		{
			files.Insert(fileName);
			while (FindNextFile(handle, fileName, attr))
				files.Insert(fileName);
			CloseFindFile(handle);
		}

		foreach (string name : files)
		{
			string path = DIR + "queue\\" + name;
			DZDSCommandFile cmds = new DZDSCommandFile;
			JsonFileLoader<DZDSCommandFile>.JsonLoadFile(path, cmds);
			DeleteFile(path);
			if (!cmds.Commands)
				continue;
			foreach (DZDSCommand c : cmds.Commands)
				Execute(c);
		}
	}

	static void Execute(DZDSCommand c)
	{
		if (c.Type != "spawn")
		{
			Print("[DZDS] Unsupported command type: " + c.Type);
			return;
		}
		if (s_Settings.AllowedClassNames.Find(c.ClassName) == -1)
		{
			Print("[DZDS] Refused (not allowlisted): " + c.ClassName);
			return;
		}
		int count = Math.Clamp(c.Count, 1, 10);
		int flags = ECE_PLACE_ON_SURFACE | ECE_CREATEPHYSICS | ECE_UPDATEPATHGRAPH;
		for (int i = 0; i < count; i++)
		{
			float x = c.X + Math.RandomFloatInclusive(-8, 8);
			float z = c.Z + Math.RandomFloatInclusive(-8, 8);
			GetGame().CreateObjectEx(c.ClassName, Ground(x, z), flags);
		}
		Print("[DZDS] Spawned " + count + " x " + c.ClassName + " at " + c.X + ", " + c.Z);
	}
};
