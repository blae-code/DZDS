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
//   paired key in the pocket and the cargo about half full of road-scavenged gear.
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
}

class RefugeeArrivalItem
{
	string ClassName;
	float Weight;
}

class RefugeeArrivalConfig
{
	int Enabled;
	int CooldownHours;
	int RandomCharacterOnRespawn;
	float PlayerOffset;
	float CargoFill;
	int MaxCargoItems;
	float FuelMin;
	float FuelMax;
	float HealthMin;
	float HealthMax;
	float ItemHealthMin;
	float ItemHealthMax;
	ref array<ref RefugeeArrivalPoint> ArrivalSites;
	ref array<ref RefugeeArrivalPoint> RoadPoints;
	ref array<ref RefugeeArrivalVehicle> Vehicles;
	ref array<ref RefugeeArrivalItem> Gear;
}

class RefugeeArrivalRecord
{
	string Id;
	int FirstSeen;
	int LastVehicle;
	int Lives;
}

class RefugeeArrivalLedger
{
	ref array<ref RefugeeArrivalRecord> Players;
}

class RefugeeArrivalPlan
{
	string Uid;
	bool FirstArrival;
	bool RandomCharacter;
	bool GrantVehicle;
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
		if (!m_Config.RoadPoints || m_Config.RoadPoints.Count() == 0 || !m_Config.Vehicles || m_Config.Vehicles.Count() == 0 || !m_Config.Gear)
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

		Print("[DZDS Arrivals] enabled=" + m_Config.Enabled + " sites=" + m_Config.ArrivalSites.Count() + " road=" + m_Config.RoadPoints.Count() + " vehicles=" + m_Config.Vehicles.Count() + " gear=" + m_Config.Gear.Count() + " known players=" + m_Ledger.Players.Count());
	}

	bool IsActive()
	{
		if (!m_Config)
			return false;
		return m_Config.Enabled == 1;
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

	RefugeeArrivalVehicle PickVehicle()
	{
		float total = 0;
		foreach (RefugeeArrivalVehicle v : m_Config.Vehicles)
		{
			total += v.Weight;
		}
		float roll = Math.RandomFloat(0, total);
		foreach (RefugeeArrivalVehicle w : m_Config.Vehicles)
		{
			roll -= w.Weight;
			if (roll <= 0)
				return w;
		}
		return m_Config.Vehicles[m_Config.Vehicles.Count() - 1];
	}

	string PickGear()
	{
		float total = 0;
		foreach (RefugeeArrivalItem g : m_Config.Gear)
		{
			total += g.Weight;
		}
		float roll = Math.RandomFloat(0, total);
		foreach (RefugeeArrivalItem i : m_Config.Gear)
		{
			roll -= i.Weight;
			if (roll <= 0)
				return i.ClassName;
		}
		return m_Config.Gear[m_Config.Gear.Count() - 1].ClassName;
	}

	static bool IsWater(float x, float z)
	{
		string surface;
		GetGame().SurfaceGetType(x, z, surface);
		surface.ToLower();
		return surface.Contains("water");
	}

	// Pick a spot from `points`. With a vehicle, the spot must be free for that vehicle class.
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
		for (int i = 0; i < 2; i++)
		{
			float x = plan.CarPos[0] + rx * m_Config.PlayerOffset * side;
			float z = plan.CarPos[2] + rz * m_Config.PlayerOffset * side;
			if (!IsWater(x, z))
			{
				plan.PlayerPos = Vector(x, GetGame().SurfaceY(x, z), z);
				return;
			}
			side = -side;
		}
		plan.PlayerPos = plan.CarPos;
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
		if (plan.GrantVehicle)
			plan.Vehicle = PickVehicle();

		bool placed = false;
		if (plan.FirstArrival)
			placed = PickPoint(m_Config.ArrivalSites, plan);
		if (!placed)
			placed = PickPoint(m_Config.RoadPoints, plan);
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

	static int UsedCells(CargoBase cargo)
	{
		int used = 0;
		for (int i = 0; i < cargo.GetItemCount(); i++)
		{
			int w, h;
			if (cargo.GetItemSize(i, w, h))
				used += w * h;
		}
		return used;
	}

	int FillCargo(CarScript car)
	{
		CargoBase cargo = car.GetInventory().GetCargo();
		if (!cargo)
			return 0;
		float targetF = cargo.GetWidth() * cargo.GetHeight() * m_Config.CargoFill;
		int target = targetF;
		int added = 0;
		int tries = 0;
		while (UsedCells(cargo) < target && added < m_Config.MaxCargoItems && tries < m_Config.MaxCargoItems * 3)
		{
			tries++;
			EntityAI item = car.GetInventory().CreateEntityInCargo(PickGear());
			if (!item)
				continue;
			item.SetHealth01("", "", Math.RandomFloatInclusive(m_Config.ItemHealthMin, m_Config.ItemHealthMax));
			added++;
		}
		return added;
	}

	void Deliver(PlayerBase player, RefugeeArrivalPlan plan)
	{
		if (!player || !plan)
			return;

		string got = "no vehicle (cooldown)";
		int now = NowSeconds();
		bool granted = false;
		if (plan.GrantVehicle)
		{
			EntityAI parent = player;
			int remaining = 1;
			Object obj = ExpansionItemSpawnHelper.SpawnVehicle(plan.Vehicle.ClassName, player, parent, plan.CarPos, plan.CarOri, remaining, plan.Vehicle.Parts, -1, "ExpansionCarKey");
			CarScript car = CarScript.Cast(obj);
			if (car)
			{
				float fuelCap = car.GetFluidCapacity(CarFluid.FUEL);
				float fuel = Math.RandomFloatInclusive(m_Config.FuelMin, m_Config.FuelMax);
				car.Leak(CarFluid.FUEL, fuelCap * (1 - fuel));
				car.SetHealth01("", "", Math.RandomFloatInclusive(m_Config.HealthMin, m_Config.HealthMax));
				int items = FillCargo(car);
				got = plan.Vehicle.ClassName + " with " + items + " item(s)";
				granted = true;
			}
			else
			{
				got = "vehicle spawn FAILED (" + plan.Vehicle.ClassName + ")";
			}
		}

		RefugeeArrivalRecord rec = FindRecord(plan.Uid);
		if (!rec)
		{
			rec = new RefugeeArrivalRecord;
			rec.Id = plan.Uid;
			rec.FirstSeen = now;
			m_Ledger.Players.Insert(rec);
		}
		rec.Lives++;
		if (granted)
			rec.LastVehicle = now;
		MakeDirectory(DIR);
		JsonFileLoader<RefugeeArrivalLedger>.JsonSaveFile(LEDGER, m_Ledger);

		string kind = "respawn";
		if (plan.FirstArrival)
			kind = "first arrival";
		Print("[DZDS Arrivals] " + kind + " at " + plan.Where + ", random=" + plan.RandomCharacter.ToString() + ", " + got + ", life " + rec.Lives);
	}
}

class CustomMission: MissionServer
{
	ref RefugeeArrivals m_RefugeeArrivals;
	ref RefugeeArrivalPlan m_ArrivalPlan;

	void SetRandomHealth(EntityAI itemEnt)
	{
		if ( itemEnt )
		{
			float rndHlt = Math.RandomFloat( 0.45, 0.65 );
			itemEnt.SetHealth01( "", "", rndHlt );
		}
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
	}
};

Mission CreateCustomMission(string path)
{
	return new CustomMission();
}