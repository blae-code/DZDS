void main()
{
	//INIT ECONOMY--------------------------------------
	Hive ce = CreateHive();
	if ( ce )
		ce.InitOffline();

	//DATE RESET AFTER ECONOMY INIT-------------------------
	int year, month, day, hour, minute;
	int reset_month = 4, reset_day = 30;
	GetGame().GetWorld().GetDate(year, month, day, hour, minute);

	if ((month == reset_month) && (day < reset_day))
	{
		GetGame().GetWorld().SetDate(year, reset_month, reset_day, hour, minute);
	}
	else
	{
		if ((month == reset_month + 1) && (day > reset_day))
		{
			GetGame().GetWorld().SetDate(year, reset_month, reset_day, hour, minute);
		}
		else
		{
			if ((month < reset_month) || (month > reset_month + 1))
			{
				GetGame().GetWorld().SetDate(year, reset_month, reset_day, hour, minute);
			}
		}
	}
}

// ===================================================================================
// DZDS refugee arrivals (Blae, 2026-10-12). Data: $profile:DZDS\arrivals.json, compiled
// from presets/arrivals.yaml by tools/arrivals.py. Ledger: $profile:DZDS\arrivals_ledger.json.
// - First character: a refugee arrival site, in the look the player chose.
// - Every later character: a random survivor, waking on a road.
// - Both: Zen's campfire, plus (once per CooldownHours per player) a worn vehicle with its
//   paired key in the pocket and one archetype's road-scavenged kit and a themed firearm in the cargo.
// Missing or disabled config = vanilla spawning, unchanged.
// ===================================================================================
class RefugeeArrivalPoint
{
	string Name;
	float X;
	float Z;
	float A;
}

class RefugeeArrivalVehicle
{
	string ClassName;
	float Weight;
	ref TStringArray Parts;
	int Trailer;          // 1 = park a trailer behind it, if the trailer mod says it can tow
	int Aircraft;         // 1 = its cargo is a pilot profile, and it gets AircraftFuel
}

// A player whose vehicle is always drawn from Vehicles (Blae, 2026-10-21: the owner gets an
// aircraft). Changes which vehicle, never whether: the cooldown still applies.
class RefugeeArrivalFavored
{
	string Id;
	string Name;
	ref TStringArray Vehicles;
}

class RefugeeArrivalSlot
{
	string Name;
	int Min;
	int Max;
	int MaxEach;
	ref TStringArray Items;
}

class RefugeeArrivalFirearm
{
	string WeaponClass;
	string MagazineClass;
	string Ammo;
	int RoundsMin;
	int RoundsMax;
	int SpareMin;
	int SpareMax;
}

class RefugeeArrivalArchetype
{
	string Name;
	float Weight;
	int Aircraft;         // 1 = pilot profile: only for aircraft, which only get these
	ref array<ref RefugeeArrivalSlot> Slots;
	ref array<ref RefugeeArrivalFirearm> Firearms;
}

class RefugeeArrivalConfig
{
	int Enabled;
	int CooldownHours;
	int RandomCharacterOnRespawn;
	float PlayerOffset;
	int RadioFrequencyIndex;
	int GiveRoadflare;
	int NavKitHours;
	ref TStringArray NavKit;
	string TrailerClass;
	ref TStringArray TrailerParts;
	ref TStringArray ColumnSites;
	int ColumnDayStartUtcHour;
	float RespawnNearMin;
	float RespawnNearMax;
	float RespawnNearFallback;
	float CampRespawnRadius;
	float CampPlayerOffset;
	float FuelMin;
	float FuelMax;
	float AircraftFuelMin;
	float AircraftFuelMax;
	ref TStringArray FuelCans;          // filled with gasoline wherever they spawn
	ref TStringArray UnfillableSlots;   // no item exists for these: the self-test ignores them
	float HealthMin;
	float HealthMax;
	float ItemHealthMin;
	float ItemHealthMax;
	ref array<ref RefugeeArrivalPoint> ArrivalSites;
	ref array<ref RefugeeArrivalPoint> RoadPoints;
	ref array<ref RefugeeArrivalVehicle> Vehicles;
	ref array<ref RefugeeArrivalFavored> Favored;
	ref array<ref RefugeeArrivalArchetype> Archetypes;
	float FirearmHealthMin;
	float FirearmHealthMax;
}

class RefugeeArrivalRecord
{
	string Id;
	int FirstSeen;
	int LastVehicle;
	int LastNavKit;
	int Lives;
	float DeathX;
	float DeathZ;
	int HasDeath;
}

class RefugeeArrivalLedger
{
	ref array<ref RefugeeArrivalRecord> Players;
}

// Local spot check (plane parking, 2026-10-16): candidate spots and the classes to fit.
class DZDSSpotCandidate
{
	float X;
	float Z;
	float A;
}

class DZDSSpotTestConfig
{
	ref TStringArray Classes;
	ref array<ref DZDSSpotCandidate> Spots;
}

class RefugeeArrivalPlan
{
	string Uid;
	bool FirstArrival;
	bool RandomCharacter;
	bool GrantVehicle;
	bool AtCamp;
	string Where;
	ref RefugeeArrivalVehicle Vehicle;
	vector CarPos;
	vector CarOri;
	vector PlayerPos;
}

class RefugeeArrivals
{
	static const string DIR = "$profile:DZDS";
	static const string CONFIG = "$profile:DZDS\\arrivals.json";
	static const string LEDGER = "$profile:DZDS\\arrivals_ledger.json";
	static const int PICK_TRIES = 12;
	static const int VEHICLE_REDRAWS = 4;
	static const float TRAILER_SETBACK = 3.0;   // trailer centre behind the hitch, before alignment
	static const float COUPLER_GAP = 0.3;       // coupler this far behind the hitch once aligned
	static const string SELFTEST = DIR + "\\vehicle_selftest";
	static const string SPOTTEST = DIR + "\\spot_selftest.json";

	ref RefugeeArrivalConfig m_Config;
	ref RefugeeArrivalLedger m_Ledger;

	void RefugeeArrivals()
	{
		if (!FileExist(CONFIG))
		{
			Print("[DZDS Arrivals] no " + CONFIG + ": vanilla spawning");
			return;
		}
		m_Config = new RefugeeArrivalConfig;
		JsonFileLoader<RefugeeArrivalConfig>.JsonLoadFile(CONFIG, m_Config);
		if (!m_Config.RoadPoints || m_Config.RoadPoints.Count() == 0 || !m_Config.Vehicles || m_Config.Vehicles.Count() == 0 || !m_Config.Archetypes || m_Config.Archetypes.Count() == 0)
		{
			Print("[DZDS Arrivals] " + CONFIG + " incomplete: vanilla spawning");
			m_Config = null;
			return;
		}
		if (!m_Config.ArrivalSites)
			m_Config.ArrivalSites = new array<ref RefugeeArrivalPoint>;

		m_Ledger = new RefugeeArrivalLedger;
		if (FileExist(LEDGER))
			JsonFileLoader<RefugeeArrivalLedger>.JsonLoadFile(LEDGER, m_Ledger);
		if (!m_Ledger.Players)
			m_Ledger.Players = new array<ref RefugeeArrivalRecord>;
		if (!m_Config.Favored)
			m_Config.Favored = new array<ref RefugeeArrivalFavored>;
		if (!m_Config.FuelCans)
			m_Config.FuelCans = new TStringArray;
		if (!m_Config.UnfillableSlots)
			m_Config.UnfillableSlots = new TStringArray;
		if (m_Config.AircraftFuelMax <= 0)
		{
			// Older arrivals.json without aircraft fuel: aircraft get the ground range.
			m_Config.AircraftFuelMin = m_Config.FuelMin;
			m_Config.AircraftFuelMax = m_Config.FuelMax;
		}

		Print("[DZDS Arrivals] enabled=" + m_Config.Enabled + " sites=" + m_Config.ArrivalSites.Count() + " road=" + m_Config.RoadPoints.Count() + " vehicles=" + m_Config.Vehicles.Count() + " archetypes=" + m_Config.Archetypes.Count() + " favored=" + m_Config.Favored.Count() + " known players=" + m_Ledger.Players.Count());
#ifdef DZDS_CAMPS
		Print("[DZDS Arrivals] camp respawn within " + m_Config.CampRespawnRadius.ToString() + " m, pitched tents=" + DZDSCamps.PitchedCount().ToString());
#endif
	}

	bool IsActive()
	{
		if (!m_Config)
			return false;
		return m_Config.Enabled == 1;
	}

	// Every new character: a radio with a battery, tuned to the Settler net, switched off
	// (vanilla items spawn off), plus one road flare (Blae, 2026-10-15).
	static void GiveStartKit(PlayerBase player, int radioIndex, bool flare)
	{
		EntityAI radio = player.GetInventory().CreateInInventory("PersonalRadio");
		if (!radio)
		{
			radio = player.GetHumanInventory().CreateInHands("PersonalRadio");
			if (radio)
				Print("[DZDS Arrivals] radio in hands (inventory full)");
		}
		if (!radio)
		{
			radio = EntityAI.Cast(GetGame().CreateObjectEx("PersonalRadio", player.GetPosition(), ECE_PLACE_ON_SURFACE));
			if (radio)
				Print("[DZDS Arrivals] radio on ground (inventory and hands full)");
		}
		if (!radio)
			Print("[DZDS Arrivals] radio NOT created for new character");
		if (radio)
		{
			radio.GetInventory().CreateAttachment("Battery9V");
			TransmitterBase tx = TransmitterBase.Cast(radio);
			if (tx)
				tx.SetFrequencyByIndex(radioIndex);
		}
		if (flare)
			player.GetInventory().CreateInInventory("Roadflare");
	}

	int RadioIndex()
	{
		if (!m_Config)
			return 0;
		return m_Config.RadioFrequencyIndex;
	}

	bool Roadflare()
	{
		if (!m_Config)
			return true;
		return m_Config.GiveRoadflare == 1;
	}

	// Seconds since 1970 (UTC), from the civil date (H. Hinnant's days_from_civil).
	static int NowSeconds()
	{
		int y, mo, d, h, mi, s;
		GetYearMonthDayUTC(y, mo, d);
		GetHourMinuteSecondUTC(h, mi, s);
		if (mo <= 2)
			y = y - 1;
		int era = y / 400;
		int yoe = y - era * 400;
		int mp;
		if (mo > 2)
			mp = mo - 3;
		else
			mp = mo + 9;
		int doy = (153 * mp + 2) / 5 + d - 1;
		int doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
		int days = era * 146097 + doe - 719468;
		return days * 86400 + h * 3600 + mi * 60 + s;
	}

	RefugeeArrivalRecord FindRecord(string uid)
	{
		foreach (RefugeeArrivalRecord r : m_Ledger.Players)
		{
			if (r.Id == uid)
				return r;
		}
		return null;
	}

	// The favored player's vehicle list, or null for everyone else.
	TStringArray FavoredVehicles(string uid)
	{
		foreach (RefugeeArrivalFavored f : m_Config.Favored)
		{
			if (f.Id == uid && f.Vehicles && f.Vehicles.Count() > 0)
				return f.Vehicles;
		}
		return null;
	}

	// Weighted draw from the pool, or only from the classes in `only` when given.
	RefugeeArrivalVehicle PickVehicle(TStringArray only = null)
	{
		float total = 0;
		foreach (RefugeeArrivalVehicle v : m_Config.Vehicles)
		{
			if (!only || only.Find(v.ClassName) >= 0)
				total += v.Weight;
		}
		if (total <= 0)
		{
			// No configured vehicle matches the list: draw from the whole pool instead.
			only = null;
			foreach (RefugeeArrivalVehicle a : m_Config.Vehicles)
			{
				total += a.Weight;
			}
		}
		float roll = Math.RandomFloat(0, total);
		RefugeeArrivalVehicle last = m_Config.Vehicles[m_Config.Vehicles.Count() - 1];
		foreach (RefugeeArrivalVehicle w : m_Config.Vehicles)
		{
			if (only && only.Find(w.ClassName) < 0)
				continue;
			last = w;
			roll -= w.Weight;
			if (roll <= 0)
				return w;
		}
		return last;
	}

	// Weighted draw among the pilot profiles (aircraft) or the ground ones (everything else).
	// A config with none of the wanted kind draws from all of them.
	RefugeeArrivalArchetype PickArchetype(bool aircraft)
	{
		int want = 0;
		if (aircraft)
			want = 1;
		float total = 0;
		foreach (RefugeeArrivalArchetype a : m_Config.Archetypes)
		{
			if (a.Aircraft == want)
				total += a.Weight;
		}
		bool any = total <= 0;
		if (any)
		{
			foreach (RefugeeArrivalArchetype c : m_Config.Archetypes)
			{
				total += c.Weight;
			}
		}
		float roll = Math.RandomFloat(0, total);
		RefugeeArrivalArchetype last = m_Config.Archetypes[m_Config.Archetypes.Count() - 1];
		foreach (RefugeeArrivalArchetype b : m_Config.Archetypes)
		{
			if (!any && b.Aircraft != want)
				continue;
			last = b;
			roll -= b.Weight;
			if (roll <= 0)
				return b;
		}
		return last;
	}

	// Kit the cargo can't take (small cargo: gyrocopter, tractor) lands on the ground beside
	// the vehicle, as if spilled from it, instead of being lost.
	EntityAI SpillBeside(CarScript car, string cls)
	{
		vector pos = car.GetPosition() + Vector(Math.RandomFloatInclusive(-2.5, 2.5), 0, Math.RandomFloatInclusive(-2.5, 2.5));
		pos[1] = GetGame().SurfaceY(pos[0], pos[2]);
		return EntityAI.Cast(GetGame().CreateObjectEx(cls, pos, ECE_PLACE_ON_SURFACE));
	}

	// The vehicle's own cargo first, then the cargo of anything attached to it: a RedFalcon
	// heli's flight storage case is its inventory (the R22's own cargo is 0x0).
	static EntityAI CreateInVehicle(CarScript car, string cls)
	{
		EntityAI item = null;
		if (car.GetInventory().GetCargo())
			item = car.GetInventory().CreateEntityInCargo(cls);
		for (int i = 0; !item && i < car.GetInventory().AttachmentCount(); i++)
		{
			EntityAI att = car.GetInventory().GetAttachmentFromIndex(i);
			if (att && att.GetInventory().GetCargo())
				item = att.GetInventory().CreateEntityInCargo(cls);
		}
		return item;
	}

	// A fuel can (FuelCans) arrives full of gasoline, wherever it spawned.
	void TopUp(EntityAI item)
	{
		ItemBase can = ItemBase.Cast(item);
		if (!can || m_Config.FuelCans.Find(item.GetType()) < 0)
			return;
		can.SetLiquidType(LIQUID_GASOLINE);
		can.SetQuantityMax();
	}

	// Fill the fuel cans the vehicle carries in its own slots (an Expansion heli's jerrycan).
	int TopUpAttached(CarScript car)
	{
		int n = 0;
		for (int i = 0; i < car.GetInventory().AttachmentCount(); i++)
		{
			EntityAI att = car.GetInventory().GetAttachmentFromIndex(i);
			if (att && m_Config.FuelCans.Find(att.GetType()) >= 0)
			{
				TopUp(att);
				n++;
			}
		}
		return n;
	}

	EntityAI Spawn(CarScript car, string cls, float hmin, float hmax)
	{
		EntityAI item = CreateInVehicle(car, cls);
		if (!item)
			item = SpillBeside(car, cls);
		if (item)
		{
			item.SetHealth01("", "", Math.RandomFloatInclusive(hmin, hmax));
			TopUp(item);
		}
		return item;
	}

	// Draw Min..Max items WITHOUT replacement (an item leaves the pool after MaxEach draws).
	int FillSlot(CarScript car, RefugeeArrivalSlot s, TStringArray got)
	{
		TStringArray pool = new TStringArray;
		pool.Copy(s.Items);
		map<string, int> used = new map<string, int>;
		int want = Math.RandomIntInclusive(s.Min, s.Max);
		int added = 0;
		for (int i = 0; i < want && pool.Count() > 0; i++)
		{
			int idx = Math.RandomInt(0, pool.Count());
			string cls = pool[idx];
			if (Spawn(car, cls, m_Config.ItemHealthMin, m_Config.ItemHealthMax))
			{
				added++;
				got.Insert(cls);
			}
			used.Set(cls, used.Get(cls) + 1);
			if (used.Get(cls) >= s.MaxEach)
				pool.Remove(idx);
		}
		return added;
	}

	// Put a magazine or a pile of loose rounds in the cargo, holding `rounds`.
	void GiveRounds(CarScript car, string cls, int rounds, TStringArray got)
	{
		if (rounds <= 0)
			return;
		Magazine m = Magazine.Cast(CreateInVehicle(car, cls));
		if (!m)
			m = Magazine.Cast(SpillBeside(car, cls));
		if (!m)
		{
			got.Insert(cls + " (FAILED)");
			return;
		}
		m.ServerSetAmmoCount(rounds);
		got.Insert(cls + " x" + rounds);
	}

	// One worn firearm. A pistol's magazine goes in the cargo partly filled, plus spare loose
	// rounds; a gun without a magazine gets loose rounds only. Not attached to the gun: on the
	// first live arrival (2026-10-16) the attached magazine never reached the player.
	void GiveFirearm(CarScript car, RefugeeArrivalArchetype a)
	{
		RefugeeArrivalFirearm f = a.Firearms.GetRandomElement();
		TStringArray got = new TStringArray;
		if (Spawn(car, f.WeaponClass, m_Config.FirearmHealthMin, m_Config.FirearmHealthMax))
		{
			int rounds = Math.RandomIntInclusive(f.RoundsMin, f.RoundsMax);
			if (f.MagazineClass != "")
			{
				GiveRounds(car, f.MagazineClass, rounds, got);
				rounds = Math.RandomIntInclusive(f.SpareMin, f.SpareMax);
			}
			GiveRounds(car, f.Ammo, rounds, got);
		}
		else
		{
			got.Insert("NO ROOM for the weapon");
		}
		Print("[DZDS Arrivals] firearm " + f.WeaponClass + ": " + got.ToString());
	}

	// The engine's own sea and pond test. The old surface-name check ("water" in the name)
	// misfired on Nasdara: on 2026-10-22 both respawns stood the player ON the vehicle's spot
	// (PlacePlayer's fallback), and Blae's R22 hit him as it spawned.
	static bool IsWater(float x, float z)
	{
		return GetGame().SurfaceIsSea(x, z) || GetGame().SurfaceIsPond(x, z);
	}

	// Attachment slots the vehicle has and nothing fills (for the delivery log).
	static int EmptySlots(EntityAI e)
	{
		int n = 0;
		for (int s = 0; s < e.GetInventory().GetAttachmentSlotsCount(); s++)
		{
			if (!e.GetInventory().FindAttachment(e.GetInventory().GetAttachmentSlotId(s)))
				n++;
		}
		return n;
	}

	// Pick a spot from `points`. With a vehicle, the spot must be free for that vehicle class.
	// The site for today's column, or `offset` sites further along the rotation.
	string ColumnSiteFor(int offset)
	{
		if (!m_Config.ColumnSites || m_Config.ColumnSites.Count() == 0)
			return "";
		int day = (NowSeconds() - m_Config.ColumnDayStartUtcHour * 3600) / 86400;
		int n = m_Config.ColumnSites.Count();
		return m_Config.ColumnSites[(day + offset) % n];
	}

	// Today's site first; if every spot there is taken, the next site in the rotation.
	bool PickColumnPoint(RefugeeArrivalPlan plan)
	{
		if (!m_Config.ColumnSites)
			return false;
		for (int o = 0; o < m_Config.ColumnSites.Count(); o++)
		{
			string site = ColumnSiteFor(o);
			array<ref RefugeeArrivalPoint> pts = new array<ref RefugeeArrivalPoint>;
			foreach (RefugeeArrivalPoint p : m_Config.ArrivalSites)
			{
				if (p.Name == site)
					pts.Insert(p);
			}
			if (PickPoint(pts, plan))
				return true;
		}
		return false;
	}

	// Blae 2026-10-17: a vehicle that can tow gets Simply's utility trailer parked behind it,
	// unhitched, its coupler just behind the hitch, so "Attach trailer to car" works at once.
	// What can tow is the trailer mod's own rule (DZT_HitchProfile: 4+ wheels, not a
	// helicopter or boat). This makes init.c need Simply's Car Trailer, as @DZDS already does.
	string GiveTrailer(CarScript car, RefugeeArrivalVehicle v, out Object trailerObj)
	{
		trailerObj = null;
		if (v.Trailer != 1 || m_Config.TrailerClass == "")
			return "";
		vector hitch;
		if (!DZT_HitchProfile.Get(car, hitch))
			return ", no trailer (cannot tow)";
		vector ori = car.GetOrientation();
		vector back = car.GetDirection() * -1;
		vector hitchWorld = car.ModelToWorld(hitch);
		vector pos = hitchWorld + back * TRAILER_SETBACK;
		pos[1] = GetGame().SurfaceY(pos[0], pos[2]);
		Object blocking;
		if (!ExpansionItemSpawnHelper.IsSpawnPositionFree(pos, ori, m_Config.TrailerClass, blocking) && blocking != car)
		{
			string by = "?";
			if (blocking)
				by = blocking.GetType();
			return ", no trailer (spot blocked by " + by + ")";
		}
		EntityAI parent = null;
		int remaining = 1;
		bool notAttached = false;
		// No player passed: attach the parts ourselves (see VehicleSelfTest).
		trailerObj = ExpansionItemSpawnHelper.SpawnVehicle(m_Config.TrailerClass, null, parent, pos, ori, remaining, NULL, -1, "", notAttached);
		CarScript trailer = CarScript.Cast(trailerObj);
		if (!trailer)
			return ", trailer spawn FAILED";
		int parts = 0;
		foreach (string part : m_Config.TrailerParts)
		{
			if (trailer.GetInventory().CreateAttachment(part))
				parts++;
		}
		vector shift = hitchWorld + back * COUPLER_GAP - trailer.ModelToWorld(trailer.GetMemoryPointPos("dzt_coupler"));
		shift[1] = 0;
		trailer.SetPosition(trailer.GetPosition() + shift);
		trailer.SetHealth01("", "", Math.RandomFloatInclusive(m_Config.HealthMin, m_Config.HealthMax));
		return ", " + m_Config.TrailerClass + " (" + parts + "/" + m_Config.TrailerParts.Count() + " parts)";
	}

	// Blae 2026-10-17: a paper map and a working GPS, once per NavKitHours per player. On the
	// body if it fits, else in the vehicle's cargo, else on the ground. Anything that takes a
	// 9V battery (the GPS) gets one and is switched on.
	string GiveNavKit(PlayerBase player, CarScript car)
	{
		TStringArray got = new TStringArray;
		foreach (string cls : m_Config.NavKit)
		{
			string where = "";
			EntityAI item = player.GetInventory().CreateInInventory(cls);
			if (!item && car)
			{
				item = CreateInVehicle(car, cls);
				where = " (vehicle)";
			}
			if (!item)
			{
				item = EntityAI.Cast(GetGame().CreateObjectEx(cls, player.GetPosition(), ECE_PLACE_ON_SURFACE));
				where = " (ground)";
			}
			if (!item)
			{
				got.Insert(cls + " FAILED");
				continue;
			}
			if (item.GetInventory().CreateAttachment("Battery9V") && item.GetCompEM())
			{
				item.GetCompEM().SwitchOn();
				where = where + " on";
			}
			got.Insert(cls + where);
		}
		return got.ToString();
	}

	// Local check (2026-10-16): with $profile:DZDS\vehicle_selftest present, spawn every
	// configured vehicle through the same SpawnVehicle + FillCargo path a respawn uses, log
	// any part that didn't attach, empty slots and the kit size, then delete it.
	void VehicleSelfTest()
	{
		if (!IsActive())
			return;
		int n = m_Config.Vehicles.Count();
		int bad = 0;
		for (int i = 0; i < n; i++)
		{
			RefugeeArrivalVehicle v = m_Config.Vehicles[i];
			RefugeeArrivalPoint p = m_Config.RoadPoints[(i * 7) % m_Config.RoadPoints.Count()];
			vector pos = Vector(p.X, GetGame().SurfaceY(p.X, p.Z), p.Z);
			EntityAI parent = null;
			int remaining = 1;
			bool notAttached = false;
			// No player here, so attach the parts ourselves (SpawnVehicle's own path needs one).
			Object obj = ExpansionItemSpawnHelper.SpawnVehicle(v.ClassName, null, parent, pos, Vector(p.A, 0, 0), remaining, NULL, -1, "", notAttached);
			EntityAI e = EntityAI.Cast(obj);
			if (!e)
			{
				bad++;
				Print("[DZDS VehicleTest] FAIL " + v.ClassName + ": not spawned");
				continue;
			}
			TStringArray failed = new TStringArray;
			foreach (string part : v.Parts)
			{
				if (!e.GetInventory().CreateAttachment(part))
					failed.Insert(part);
			}
			if (failed.Count() > 0)
				notAttached = true;
			TStringArray empty = new TStringArray;
			int missing = 0;
			for (int s = 0; s < e.GetInventory().GetAttachmentSlotsCount(); s++)
			{
				int slotId = e.GetInventory().GetAttachmentSlotId(s);
				if (!e.GetInventory().FindAttachment(slotId))
				{
					string slotName = InventorySlots.GetSlotName(slotId);
					empty.Insert(slotName);
					if (m_Config.UnfillableSlots.Find(slotName) < 0)
						missing++;
				}
			}
			int items = -1;
			int cans = 0;
			string trailerNote = "";
			Object trailerObj = null;
			CarScript car = CarScript.Cast(obj);
			if (car)
			{
				cans = TopUpAttached(car);
				items = FillCargo(car, v.Aircraft == 1);
				trailerNote = GiveTrailer(car, v, trailerObj);
			}
			string verdict = "OK";
			// An aircraft must arrive with every fillable slot filled (Blae, 2026-10-22).
			if (notAttached || items < 12 || trailerNote.Contains("FAILED") || (v.Aircraft == 1 && missing > 0))
			{
				verdict = "CHECK";
				bad++;
			}
			Print("[DZDS VehicleTest] " + verdict + " " + v.ClassName + ": " + v.Parts.Count() + " part(s), failed " + failed.ToString() + ", kit item(s)=" + items + ", full cans=" + cans + trailerNote + ", " + missing + " fillable slot(s) empty");
			foreach (string slot : empty)
			{
				Print("[DZDS VehicleTest]   empty slot " + v.ClassName + "." + slot);
			}
			if (trailerObj)
				GetGame().ObjectDelete(trailerObj);
			GetGame().ObjectDelete(obj);
		}
		Print("[DZDS VehicleTest] done: " + n + " vehicle(s), " + bad + " to check");
	}

	// Local check: with $profile:DZDS\spot_selftest.json present, test every candidate spot
	// for every class with Expansion's collision-box check, plus the terrain slope across
	// the vehicle's footprint. Nothing is spawned.
	void SpotSelfTest()
	{
		DZDSSpotTestConfig t = new DZDSSpotTestConfig;
		JsonFileLoader<DZDSSpotTestConfig>.JsonLoadFile(SPOTTEST, t);
		if (!t.Classes || !t.Spots)
			return;
		foreach (string cls : t.Classes)
		{
			vector box[2];
			if (!ExpansionStatic.GetCollisionBox(cls, box))
			{
				Print("[DZDS SpotTest] " + cls + ": no collision box");
				continue;
			}
			for (int i = 0; i < t.Spots.Count(); i++)
			{
				DZDSSpotCandidate c = t.Spots[i];
				vector pos = Vector(c.X, GetGame().SurfaceY(c.X, c.Z), c.Z);
				vector ori = Vector(c.A, 0, 0);
				Object blocking;
				bool free = ExpansionItemSpawnHelper.IsSpawnPositionFree(pos, ori, cls, blocking);
				float rad = c.A * Math.DEG2RAD;
				float lo = 10000;
				float hi = -10000;
				for (int k = 0; k < 4; k++)
				{
					float bx = box[k % 2][0];
					float bz = box[k / 2][2];
					float wx = c.X + bx * Math.Cos(rad) + bz * Math.Sin(rad);
					float wz = c.Z - bx * Math.Sin(rad) + bz * Math.Cos(rad);
					float y = GetGame().SurfaceY(wx, wz);
					lo = Math.Min(lo, y);
					hi = Math.Max(hi, y);
				}
				string by = "";
				if (blocking)
					by = " blocked by " + blocking.GetType();
				Print("[DZDS SpotTest] " + cls + " #" + i + " free=" + free.ToString() + " slope=" + (hi - lo).ToString() + by);
			}
		}
		Print("[DZDS SpotTest] done");
	}

	void RecordDeath(string uid, vector pos)
	{
		if (!IsActive())
			return;
		RefugeeArrivalRecord rec = FindRecord(uid);
		if (!rec)
			return;
		rec.DeathX = pos[0];
		rec.DeathZ = pos[2];
		rec.HasDeath = 1;
		MakeDirectory(DIR);
		JsonFileLoader<RefugeeArrivalLedger>.JsonSaveFile(LEDGER, m_Ledger);
	}

	// Road points between lo and hi metres from the last death.
	array<ref RefugeeArrivalPoint> RingPoints(RefugeeArrivalRecord rec, float lo, float hi)
	{
		array<ref RefugeeArrivalPoint> ring = new array<ref RefugeeArrivalPoint>;
		foreach (RefugeeArrivalPoint p : m_Config.RoadPoints)
		{
			float dx = p.X - rec.DeathX;
			float dz = p.Z - rec.DeathZ;
			float d = Math.Sqrt(dx * dx + dz * dz);
			if (d >= lo && d <= hi)
				ring.Insert(p);
		}
		return ring;
	}

	// Blae 2026-10-16: wake beside the pitched tent nearest the last death, without a car.
	bool PickCamp(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec)
	{
		if (!rec || !rec.HasDeath || m_Config.CampRespawnRadius <= 0)
			return false;
#ifdef DZDS_CAMPS
		vector death = Vector(rec.DeathX, GetGame().SurfaceY(rec.DeathX, rec.DeathZ), rec.DeathZ);
		TentBase tent = DZDSCamps.Nearest(death, m_Config.CampRespawnRadius);
		if (!tent || tent.GetState() != TentBase.PITCHED)
			return false;
		plan.GrantVehicle = false;
		plan.AtCamp = true;
		plan.CarPos = tent.GetPosition();
		plan.CarOri = tent.GetOrientation();
		plan.Where = "camp (" + tent.GetType() + " " + Math.Round(vector.Distance(death, plan.CarPos)).ToString() + " m from death)";
		return true;
#else
		return false; // @DZDS without camp tracking (pre 2026-10-16): road respawn as before
#endif
	}

	bool PickNearDeath(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec)
	{
		if (!rec || rec.HasDeath != 1)
			return false;
		if (PickPoint(RingPoints(rec, m_Config.RespawnNearMin, m_Config.RespawnNearMax), plan))
			return true;
		return PickPoint(RingPoints(rec, 1000, m_Config.RespawnNearFallback), plan);
	}

	bool PickPoint(array<ref RefugeeArrivalPoint> points, RefugeeArrivalPlan plan)
	{
		if (!points || points.Count() == 0)
			return false;
		for (int t = 0; t < PICK_TRIES; t++)
		{
			RefugeeArrivalPoint p = points.GetRandomElement();
			vector pos = Vector(p.X, GetGame().SurfaceY(p.X, p.Z), p.Z);
			vector ori = Vector(p.A, 0, 0);
			if (plan.GrantVehicle)
			{
				Object blocking;
				if (!ExpansionItemSpawnHelper.IsSpawnPositionFree(pos, ori, plan.Vehicle.ClassName, blocking))
					continue;
			}
			plan.CarPos = pos;
			plan.CarOri = ori;
			plan.Where = p.Name;
			if (plan.Where == "")
				plan.Where = "road " + p.X.ToString() + "," + p.Z.ToString();
			return true;
		}
		return false;
	}

	// Player wakes beside the car, off the road (perpendicular to its heading), not in water.
	void PlacePlayer(RefugeeArrivalPlan plan)
	{
		float rad = plan.CarOri[0] * Math.DEG2RAD;
		float rx = Math.Cos(rad);
		float rz = -Math.Sin(rad);
		float side = 1;
		if (Math.RandomInt(0, 2) == 0)
			side = -1;
		float offset = m_Config.PlayerOffset;
		if (plan.AtCamp)
			offset = m_Config.CampPlayerOffset;
		for (int i = 0; i < 2; i++)
		{
			float x = plan.CarPos[0] + rx * offset * side;
			float z = plan.CarPos[2] + rz * offset * side;
			if (!IsWater(x, z))
			{
				plan.PlayerPos = Vector(x, GetGame().SurfaceY(x, z), z);
				return;
			}
			side = -side;
		}
		// Water on both sides: still beside the vehicle, never on its spot (a spawning
		// vehicle hits whoever stands there).
		float wx = plan.CarPos[0] + rx * offset * side;
		float wz = plan.CarPos[2] + rz * offset * side;
		plan.PlayerPos = Vector(wx, GetGame().SurfaceY(wx, wz), wz);
	}

	RefugeeArrivalPlan Plan(PlayerIdentity identity)
	{
		if (!IsActive() || !identity)
			return null;

		RefugeeArrivalPlan plan = new RefugeeArrivalPlan;
		plan.Uid = identity.GetId();
		RefugeeArrivalRecord rec = FindRecord(plan.Uid);
		plan.FirstArrival = false;
		if (rec == null)
			plan.FirstArrival = true;
		plan.RandomCharacter = !plan.FirstArrival && m_Config.RandomCharacterOnRespawn == 1;
		plan.GrantVehicle = true;
		if (rec && rec.LastVehicle > 0 && NowSeconds() - rec.LastVehicle < m_Config.CooldownHours * 3600)
			plan.GrantVehicle = false;
		TStringArray only = FavoredVehicles(plan.Uid);
		if (plan.GrantVehicle)
			plan.Vehicle = PickVehicle(only);

		bool placed = false;
		if (plan.FirstArrival)
			placed = PickColumnPoint(plan);
		if (!placed && !plan.FirstArrival)
			placed = PickCamp(plan, rec);
		if (!placed && !plan.FirstArrival)
			placed = PickNearDeath(plan, rec);
		if (!placed)
			placed = PickPoint(m_Config.RoadPoints, plan);
		for (int r = 0; r < VEHICLE_REDRAWS && !placed && plan.GrantVehicle; r++)
		{
			// A big vehicle (transport helicopter, semi) may fit no spot here: draw another.
			plan.Vehicle = PickVehicle(only);
			if (!plan.FirstArrival)
				placed = PickNearDeath(plan, rec);
			if (!placed)
				placed = PickPoint(m_Config.RoadPoints, plan);
		}
		if (!placed && plan.GrantVehicle)
		{
			// Every candidate was blocked: still wake on a road, just without a vehicle.
			plan.GrantVehicle = false;
			placed = PickPoint(m_Config.RoadPoints, plan);
		}
		if (!placed)
			return null;

		PlacePlayer(plan);
		return plan;
	}

	int FillCargo(CarScript car, bool aircraft)
	{
		RefugeeArrivalArchetype a = PickArchetype(aircraft);
		// Firearm first, so a crowded trunk can't push it out.
		GiveFirearm(car, a);
		TStringArray got = new TStringArray;
		int added = 0;
		foreach (RefugeeArrivalSlot s : a.Slots)
		{
			added += FillSlot(car, s, got);
		}
		Print("[DZDS Arrivals] cargo " + a.Name + ": " + added + " item(s) " + got.ToString());
		return added;
	}

	void Deliver(PlayerBase player, RefugeeArrivalPlan plan)
	{
		if (!player || !plan)
			return;

		string got = "no vehicle (cooldown)";
		if (plan.AtCamp)
			got = "no vehicle (camp)";
		int now = NowSeconds();
		bool granted = false;
		CarScript car = null;
		if (plan.GrantVehicle)
		{
			EntityAI parent = player;
			int remaining = 1;
			Object obj = ExpansionItemSpawnHelper.SpawnVehicle(plan.Vehicle.ClassName, player, parent, plan.CarPos, plan.CarOri, remaining, plan.Vehicle.Parts, -1, "ExpansionCarKey");
			car = CarScript.Cast(obj);
			if (car)
			{
				bool aircraft = plan.Vehicle.Aircraft == 1;
				float fuelCap = car.GetFluidCapacity(CarFluid.FUEL);
				float fuel = Math.RandomFloatInclusive(m_Config.FuelMin, m_Config.FuelMax);
				if (aircraft)
					fuel = Math.RandomFloatInclusive(m_Config.AircraftFuelMin, m_Config.AircraftFuelMax);
				car.Leak(CarFluid.FUEL, fuelCap * (1 - fuel));
				car.SetHealth01("", "", Math.RandomFloatInclusive(m_Config.HealthMin, m_Config.HealthMax));
				int cans = TopUpAttached(car);
				int items = FillCargo(car, aircraft);
				Object trailerObj;
				got = plan.Vehicle.ClassName + " with " + items + " item(s), fuel " + Math.Round(fuel * 100).ToString() + "%, " + cans + " full can(s) attached, " + EmptySlots(car).ToString() + " empty slot(s)" + GiveTrailer(car, plan.Vehicle, trailerObj);
				granted = true;
			}
			else
			{
				got = "vehicle spawn FAILED (" + plan.Vehicle.ClassName + ")";
			}
		}

		RefugeeArrivalRecord rec = FindRecord(plan.Uid);
		string nav = "no nav kit (cooldown)";
		bool navGiven = false;
		if (m_Config.NavKit && m_Config.NavKit.Count() > 0 && (!rec || rec.LastNavKit <= 0 || now - rec.LastNavKit >= m_Config.NavKitHours * 3600))
		{
			nav = "nav kit " + GiveNavKit(player, car);
			navGiven = true;
		}
		if (!rec)
		{
			rec = new RefugeeArrivalRecord;
			rec.Id = plan.Uid;
			rec.FirstSeen = now;
			m_Ledger.Players.Insert(rec);
		}
		rec.Lives++;
		rec.HasDeath = 0;
		if (granted)
			rec.LastVehicle = now;
		if (navGiven)
			rec.LastNavKit = now;
		MakeDirectory(DIR);
		JsonFileLoader<RefugeeArrivalLedger>.JsonSaveFile(LEDGER, m_Ledger);

		string kind = "respawn";
		if (plan.FirstArrival)
			kind = "first arrival";
		string beside = "";
		if (car)
			beside = ", player " + Math.Round(vector.Distance(player.GetPosition(), car.GetPosition())).ToString() + " m from it";
		Print("[DZDS Arrivals] " + kind + " at " + plan.Where + ", random=" + plan.RandomCharacter.ToString() + ", " + got + beside + ", " + nav + ", life " + rec.Lives);
	}
}

class CustomMission: MissionServer
{
	ref RefugeeArrivals m_RefugeeArrivals;
	ref RefugeeArrivalPlan m_ArrivalPlan;

	override void OnInit()
	{
		super.OnInit();
		if (FileExist(RefugeeArrivals.SELFTEST))
			GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(RunVehicleSelfTest, 60000, false);
		if (FileExist(RefugeeArrivals.SPOTTEST))
			GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(RunSpotSelfTest, 45000, false);
		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(ClearTrailers, 20000, false);
		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(ClearTrailers, 120000, true);
	}

	// Blae 2026-10-17: trailers crash the server. Simply's trailer is a driverless CarScript,
	// and Expansion AI's eAIDamageHandler.OnDamageCalculated calls CrewMember(DRIVER) on any
	// Transport that hits an infected, unchecked: the first zombie a trailer touches takes the
	// engine down (crash logs 23:49 and 23:55 UTC, both RegisterTransportHit -> line 162).
	// Until that is patched, every trailer in the world is removed, its cargo and parts
	// dropped on the ground beside it. Arrivals stop handing them out (arrivals.yaml).
	void ClearTrailers()
	{
		int cleared = 0;
		auto node = CarScript.s_Expansion_AllVehicles.m_Head;
		while (node)
		{
			DZT_UtilityTrailer trailer = DZT_UtilityTrailer.Cast(node.m_Value);
			node = node.m_Next;
			if (!trailer)
				continue;
			trailer.DZT_Detach();
			MiscGameplayFunctions.ThrowAllItemsInInventory(trailer, ThrowEntityFlags.SPLIT);
			Print("[DZDS] Trailer removed at " + trailer.GetPosition().ToString());
			GetGame().ObjectDelete(trailer);
			cleared++;
		}
		if (cleared > 0)
			Print("[DZDS] Trailers removed: " + cleared);
	}

	void RunSpotSelfTest()
	{
		if (!m_RefugeeArrivals)
			m_RefugeeArrivals = new RefugeeArrivals();
		m_RefugeeArrivals.SpotSelfTest();
	}

	void RunVehicleSelfTest()
	{
		if (!m_RefugeeArrivals)
			m_RefugeeArrivals = new RefugeeArrivals();
		m_RefugeeArrivals.VehicleSelfTest();
	}

	void SetRandomHealth(EntityAI itemEnt)
	{
		if ( itemEnt )
		{
			float rndHlt = Math.RandomFloat( 0.45, 0.65 );
			itemEnt.SetHealth01( "", "", rndHlt );
		}
	}

	override void OnClientRespawnEvent(PlayerIdentity identity, PlayerBase player)
	{
		if (m_RefugeeArrivals && identity && player)
			m_RefugeeArrivals.RecordDeath(identity.GetId(), player.GetPosition());
		super.OnClientRespawnEvent(identity, player);
	}

	override void PlayerDisconnected(PlayerBase player, PlayerIdentity identity, string uid)
	{
		if (m_RefugeeArrivals && player && !player.IsAlive())
			m_RefugeeArrivals.RecordDeath(uid, player.GetPosition());
		super.PlayerDisconnected(player, identity, uid);
	}

	override PlayerBase OnClientNewEvent(PlayerIdentity identity, vector pos, ParamsReadContext ctx)
	{
		if (!m_RefugeeArrivals)
			m_RefugeeArrivals = new RefugeeArrivals();
		m_ArrivalPlan = m_RefugeeArrivals.Plan(identity);
		PlayerBase player = super.OnClientNewEvent(identity, pos, ctx);
		m_ArrivalPlan = null;
		return player;
	}

	override void EquipCharacter(MenuDefaultCharacterData char_data)
	{
		if (m_ArrivalPlan && m_ArrivalPlan.RandomCharacter)
			char_data.GenerateRandomEquip();
		super.EquipCharacter(char_data);
		if (m_ArrivalPlan)
			m_RefugeeArrivals.Deliver(m_player, m_ArrivalPlan);
	}

	override PlayerBase CreateCharacter(PlayerIdentity identity, vector pos, ParamsReadContext ctx, string characterName)
	{
		if (m_ArrivalPlan)
		{
			pos = m_ArrivalPlan.PlayerPos;
			if (m_ArrivalPlan.RandomCharacter)
				characterName = GetGame().CreateRandomPlayer();
		}

		Entity playerEnt;
		playerEnt = GetGame().CreatePlayer( identity, characterName, pos, 0, "NONE" );
		Class.CastTo( m_player, playerEnt );

		GetGame().SelectPlayer( identity, m_player );

		return m_player;
	}

	override void StartingEquipSetup(PlayerBase player, bool clothesChosen)
	{
		player.RemoveAllItems();
		
		EntityAI itemClothing;
		EntityAI itemEnt;
		ItemBase itemBs;
		float rand;

		string bodyArray[] = { "KameezShirt_Beige", "KameezShirt_Black", "KameezShirt_BlueFlowers", "KameezShirt_Brown", "KameezShirt_Grey", "KameezShirt_NavyBlue", "KameezShirt_Olive", "KameezShirt_Orange", "KameezShirt_Pink", "KameezShirt_Purple", "KameezShirt_Red", "KameezShirt_SkyBlue", "KameezShirt_White", "KameezShirt_Yellow" };
		int rndBodyIndex = Math.RandomInt( 0, 14 );
		itemEnt = player.GetInventory().CreateInInventory( bodyArray[rndBodyIndex] );
		SetRandomHealth( itemEnt );
		
		string legsArray[] = { "MensShalwarPants_Beige", "MensShalwarPants_Black", "MensShalwarPants_Brown", "MensShalwarPants_Grey", "MensShalwarPants_NavyBlue", "MensShalwarPants_SkyBlue", "MensShalwarPants_White", "WomensShalwarPants_NavyBlue", "WomensShalwarPants_Olive", "WomensShalwarPants_Orange", "WomensShalwarPants_Pink", "WomensShalwarPants_Purple", "WomensShalwarPants_Red" };
		int rndLegsIndex = Math.RandomInt( 0, 13 );
		itemEnt = player.GetInventory().CreateInInventory( legsArray[rndLegsIndex] );
		SetRandomHealth( itemEnt );
		
		string feetArray[] = { "SandalsShoes_Black", "SandalsShoes_BlueNavy", "SandalsShoes_Brown", "SandalsShoes_Grey", "TraditionalSandalShoes_Black", "TraditionalSandalShoes_Brown", "TraditionalSandalShoes_LightBrown", "TraditionalSandalShoes_NavyBlue" };
		int rndFeetIndex = Math.RandomInt( 0, 8 );
		itemEnt = player.GetInventory().CreateInInventory( feetArray[rndFeetIndex] );
		SetRandomHealth( itemEnt );
		
		string chemlightArray[] = { "Chemlight_White", "Chemlight_Yellow", "Chemlight_Green", "Chemlight_Red" };
		int rndChemIndex = Math.RandomInt( 0, 4 );
		itemEnt = player.GetInventory().CreateInInventory( chemlightArray[rndChemIndex] );
		player.SetQuickBarEntityShortcut(itemEnt, 1);
		SetRandomHealth( itemEnt );

		string sodaArray[] = { "SodaCan_Pipsi", "SodaCan_Spite", "SodaCan_Cola", "SodaCan_Fronta" };
		int rndSodaIndex = Math.RandomInt( 0, 4 );
		itemEnt = player.GetInventory().CreateInInventory( sodaArray[rndSodaIndex] );
		SetRandomHealth( itemEnt );
		
		itemEnt = player.GetInventory().CreateInInventory( "Figs" );
		itemEnt = player.GetInventory().CreateInInventory( "BandageDressing" );
		player.SetQuickBarEntityShortcut(itemEnt, 2);
		
		player.GetStatWater().Set( 1000 );
		player.GetStatEnergy().Set( 800 );
		if (!m_RefugeeArrivals)
			m_RefugeeArrivals = new RefugeeArrivals();
		RefugeeArrivals.GiveStartKit(player, m_RefugeeArrivals.RadioIndex(), m_RefugeeArrivals.Roadflare());
	}
};

Mission CreateCustomMission(string path)
{
	return new CustomMission();
}