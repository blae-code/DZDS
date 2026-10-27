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
// aircraft). Changes which vehicle, never whether: the cooldown still applies to Vehicles.
// 2026-10-23: Outfit dresses every character of theirs; inside the cooldown they get one of
// CooldownVehicles instead, which starts no cooldown (Blae: "just helicopters").
class RefugeeArrivalFavored
{
	string Id;
	string Name;
	ref TStringArray Vehicles;
	string Outfit;
	ref TStringArray CooldownVehicles;
	float CompanionChance;
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

// Outfits (Blae, 2026-10-23): a starting archetype worn on the body. One variant per character.
class RefugeeArrivalWorn
{
	string ClassName;
	ref TStringArray Attach;   // carried on this item (the Smersh bag on its vest)
}

class RefugeeArrivalOutfitVariant
{
	string Name;
	ref array<ref RefugeeArrivalWorn> Worn;
}

class RefugeeArrivalKitWeapon
{
	string WeaponClass;
	ref TStringArray Attach;
	string MagazineClass;
	int Magazines;             // this many FULL magazines, loose in the inventory
	int Rounds;
}

class RefugeeArrivalOutfit
{
	string Name;
	float Chance;              // per respawn (random character); a favored Outfit always applies
	float HealthMin;
	float HealthMax;
	ref array<ref RefugeeArrivalOutfitVariant> Variants;
	ref TStringArray Carried;
	ref array<ref RefugeeArrivalKitWeapon> Primary;   // one drawn
	ref RefugeeArrivalKitWeapon Sidearm;
	string AircraftCargo;      // an aircraft's cargo: this pilot profile
	ref RefugeeArrivalArchetype LandCargo;            // any other vehicle's cargo
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
	float RespawnNearPlayersMin;   // wake this close to another living player online...
	float RespawnNearPlayersMax;   // ...else this close (0 = off, e.g. an older arrivals.json)
	int BaseRespawn;               // 1 = wake at the raised territory flag nearest the death
	float BasePlayerOffset;
	int RespawnAtHq;               // 1 = wake at Qalat-e Lut player faction HQ
	ref array<ref RefugeeArrivalPoint> HqPoints;
	ref array<ref RefugeeArrivalVehicle> LightVehicles;
	int CompanionEnabled;
	float CompanionChance;
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
	ref array<ref RefugeeArrivalOutfit> Outfits;
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

// A live cooldown reset (tools/reset_respawns.py --live): the player ids to clear.
class RefugeeArrivalReset
{
	ref TStringArray Ids;
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
	bool StartsCooldown;    // false for a favored player's CooldownVehicles or light vehicles
	bool AlwaysVehicle;     // favored with CooldownVehicles: base and camp (no vehicle) are skipped
	bool IsLightVehicle;    // inside cooldown: granted a light personal vehicle (dirtbike, moped)
	ref RefugeeArrivalArchetype Archetype;
	ref RefugeeArrivalOutfit Outfit;
	bool GrantCompanion;
	string CompanionType;
	bool AtCamp;
	bool AtBase;
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
	static const float BESIDE_MIN_M = 4.0;      // closer to the vehicle's spot than this = inside it
	static const float BESIDE_FALLBACK_M = 9.0; // used when the configured offset reads below that
	static const int BESIDE_RECHECK_MS = 3000;  // and look again once the login has settled
	static const float TRAILER_SETBACK = 3.0;   // trailer centre behind the hitch, before alignment
	static const float COUPLER_GAP = 0.3;       // coupler this far behind the hitch once aligned
	static const string SELFTEST = DIR + "\\vehicle_selftest";
	static const string SPOTTEST = DIR + "\\spot_selftest.json";
	static const string RESET = DIR + "\\reset_cooldowns.json";

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
		if (!m_Config.HqPoints)
			m_Config.HqPoints = new array<ref RefugeeArrivalPoint>;
		if (!m_Config.LightVehicles)
			m_Config.LightVehicles = new array<ref RefugeeArrivalVehicle>;

		m_Ledger = new RefugeeArrivalLedger;
		if (FileExist(LEDGER))
			JsonFileLoader<RefugeeArrivalLedger>.JsonLoadFile(LEDGER, m_Ledger);
		if (!m_Ledger.Players)
			m_Ledger.Players = new array<ref RefugeeArrivalRecord>;
		if (!m_Config.Favored)
			m_Config.Favored = new array<ref RefugeeArrivalFavored>;
		if (!m_Config.Outfits)
			m_Config.Outfits = new array<ref RefugeeArrivalOutfit>;
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

		Print("[DZDS Arrivals] enabled=" + m_Config.Enabled + " sites=" + m_Config.ArrivalSites.Count() + " road=" + m_Config.RoadPoints.Count() + " vehicles=" + m_Config.Vehicles.Count() + " archetypes=" + m_Config.Archetypes.Count() + " favored=" + m_Config.Favored.Count() + " outfits=" + m_Config.Outfits.Count() + " known players=" + m_Ledger.Players.Count());
#ifdef DZDS_CAMPS
		Print("[DZDS Arrivals] camp respawn within " + m_Config.CampRespawnRadius.ToString() + " m, pitched tents=" + DZDSCamps.PitchedCount().ToString());
#endif
		Print("[DZDS Arrivals] near players within " + m_Config.RespawnNearPlayersMin.ToString() + "/" + m_Config.RespawnNearPlayersMax.ToString() + " m, base respawn=" + m_Config.BaseRespawn.ToString());
#ifdef DZDS_BASES
		Print("[DZDS Arrivals] territory flags=" + DZDSBases.Count().ToString() + " raised=" + DZDSBases.RaisedCount().ToString());
#else
		Print("[DZDS Arrivals] base respawn needs @DZDS with DZDSBases: skipped");
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

		// Blae (Survival Incentives, 2026-10-25): Diegetic Survivor Directive note with emergency
		// frequencies (Settler Net 87.8 MHz), HQ sanctuary coordinates, and mission journal prompt.
		EntityAI directive = player.GetInventory().CreateInInventory("Paper");
		if (directive)
			Print("[DZDS Arrivals] Issued Survivor Field Directive to " + player.GetIdentity().GetName());

		DZDSGeocacheManager.AssignGeocaches(player);
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

	RefugeeArrivalFavored FindFavored(string uid)
	{
		foreach (RefugeeArrivalFavored f : m_Config.Favored)
		{
			if (f.Id == uid)
				return f;
		}
		return null;
	}

	RefugeeArrivalOutfit FindOutfit(string name)
	{
		foreach (RefugeeArrivalOutfit o : m_Config.Outfits)
		{
			if (o.Name == name)
				return o;
		}
		return null;
	}

	RefugeeArrivalArchetype FindArchetype(string name)
	{
		foreach (RefugeeArrivalArchetype a : m_Config.Archetypes)
		{
			if (a.Name == name)
				return a;
		}
		return null;
	}

	// Blae 2026-10-23: a favored player's outfit always; anyone else rolls each outfit's Chance
	// once per respawn (random character). A first arrival keeps the look the player chose.
	RefugeeArrivalOutfit PickOutfit(RefugeeArrivalPlan plan, RefugeeArrivalFavored fav)
	{
		if (fav)
		{
			if (fav.Outfit != "")
				return FindOutfit(fav.Outfit);
		}
		if (!plan.RandomCharacter)
			return null;
		foreach (RefugeeArrivalOutfit o : m_Config.Outfits)
		{
			if (Math.RandomFloat01() < o.Chance)
				return o;
		}
		return null;
	}

	// A dressed character's vehicle cargo: the outfit's pilot profile in an aircraft, its land
	// kit in anything else. null = the usual weighted draw.
	RefugeeArrivalArchetype OutfitCargo(RefugeeArrivalOutfit o, bool aircraft)
	{
		if (!o)
			return null;
		if (aircraft)
			return FindArchetype(o.AircraftCargo);
		return o.LandCargo;
	}

	// One outfit item on the body, else on the ground at the player's feet (logged).
	EntityAI DressItem(PlayerBase p, string cls, RefugeeArrivalOutfit o, TStringArray notes)
	{
		EntityAI item = p.GetInventory().CreateInInventory(cls);
		if (!item)
		{
			item = EntityAI.Cast(GetGame().CreateObjectEx(cls, p.GetPosition(), ECE_PLACE_ON_SURFACE));
			if (item)
				notes.Insert(cls + " (ground)");
			else
				notes.Insert(cls + " FAILED");
		}
		if (!item)
			return null;
		float hMin = 0.55;
		float hMax = 0.90;
		if (o)
		{
			hMin = o.HealthMin;
			hMax = o.HealthMax;
		}
		item.SetHealth01("", "", Math.RandomFloatInclusive(hMin, hMax));
		Bottle_Base bottle = Bottle_Base.Cast(item);
		if (bottle)
		{
			bottle.SetLiquidType(LIQUID_WATER);
			bottle.SetQuantityMax();
		}
		return item;
	}

	// Lightly equip a player on respawn (inside rare vehicle cooldown) according to their archetype.
	string EquipLightArchetype(PlayerBase p, RefugeeArrivalArchetype a)
	{
		if (!p || !a)
			return "no light archetype";

		p.RemoveAllItems();
		TStringArray notes = new TStringArray;

		foreach (RefugeeArrivalSlot slot : a.Slots)
		{
			if (slot.Name == "clothing" && slot.Items && slot.Items.Count() > 0)
			{
				string top = "";
				string pants = "";
				string shoes = "";
				string hat = "";
				foreach (string cls : slot.Items)
				{
					string clsLower = cls;
					clsLower.ToLower();
					if (top == "" && (clsLower.Contains("jacket") || clsLower.Contains("shirt") || clsLower.Contains("vest")))
						top = cls;
					else if (pants == "" && (clsLower.Contains("pants") || clsLower.Contains("shalwar")))
						pants = cls;
					else if (shoes == "" && (clsLower.Contains("boots") || clsLower.Contains("shoes")))
						shoes = cls;
					else if (hat == "" && (clsLower.Contains("hat") || clsLower.Contains("cap") || clsLower.Contains("shemag") || clsLower.Contains("keffiyeh")))
						hat = cls;
				}
				if (top != "") DressItem(p, top, null, notes);
				if (pants != "") DressItem(p, pants, null, notes);
				if (shoes != "") DressItem(p, shoes, null, notes);
				if (hat != "") DressItem(p, hat, null, notes);
			}
			else if (slot.Name == "water" && slot.Items && slot.Items.Count() > 0)
			{
				string wItem = slot.Items.GetRandomElement();
				EntityAI wObj = DressItem(p, wItem, null, notes);
				Bottle_Base bottle = Bottle_Base.Cast(wObj);
				if (bottle)
				{
					bottle.SetLiquidType(LIQUID_WATER);
					bottle.SetQuantityMax();
				}
			}
			else if (slot.Name == "food" && slot.Items && slot.Items.Count() > 0)
			{
				DressItem(p, slot.Items.GetRandomElement(), null, notes);
			}
			else if (slot.Name == "medical" && slot.Items && slot.Items.Count() > 0)
			{
				DressItem(p, "BandageDressing", null, notes);
			}
			else if (slot.Name == "knife" && slot.Items && slot.Items.Count() > 0)
			{
				DressItem(p, slot.Items.GetRandomElement(), null, notes);
			}
		}

		if (a.Firearms && a.Firearms.Count() > 0)
		{
			RefugeeArrivalFirearm f = a.Firearms.GetRandomElement();
			if (f && f.WeaponClass != "")
			{
				EntityAI gun = DressItem(p, f.WeaponClass, null, notes);
				if (gun && f.MagazineClass != "")
				{
					Magazine mag = Magazine.Cast(DressItem(p, f.MagazineClass, null, notes));
					if (mag)
						mag.ServerSetAmmoCount(f.RoundsMax);
				}
			}
		}

		return "light archetype " + a.Name + " equipped: " + notes.ToString();
	}

	// Each attachment on its carrier; one that won't fit there goes into the inventory instead.
	void GiveAttachments(PlayerBase p, EntityAI carrier, TStringArray attach, RefugeeArrivalOutfit o, TStringArray notes)
	{
		if (!attach)
			return;
		foreach (string cls : attach)
		{
			EntityAI att = carrier.GetInventory().CreateAttachment(cls);
			if (att)
			{
				att.SetHealth01("", "", Math.RandomFloatInclusive(o.HealthMin, o.HealthMax));
				continue;
			}
			notes.Insert(cls + " not on " + carrier.GetType());
			DressItem(p, cls, o, notes);
		}
	}

	// A weapon with its attachments, plus Magazines full magazines loose in the inventory (not
	// attached: on 2026-10-16 an attached magazine never reached the player).
	string GiveKitWeapon(PlayerBase p, RefugeeArrivalKitWeapon w, RefugeeArrivalOutfit o, TStringArray notes)
	{
		if (!w || w.WeaponClass == "")
			return "no weapon";
		EntityAI gun = DressItem(p, w.WeaponClass, o, notes);
		if (!gun)
			return w.WeaponClass + " FAILED";
		GiveAttachments(p, gun, w.Attach, o, notes);
		int mags = 0;
		for (int i = 0; i < w.Magazines; i++)
		{
			Magazine m = Magazine.Cast(DressItem(p, w.MagazineClass, o, notes));
			if (!m)
				continue;
			m.ServerSetAmmoCount(w.Rounds);
			mags++;
		}
		return w.WeaponClass + " + " + mags + "x " + w.MagazineClass + " (" + w.Rounds + ")";
	}

	// Blae 2026-10-23: dress `p` in the outfit (variant -1 = a random one): worn items, what rides
	// on them, carried items, one primary and the sidearm. Returns the log line.
	string Dress(PlayerBase p, RefugeeArrivalOutfit o, int variant = -1)
	{
		if (!o.Variants || o.Variants.Count() == 0)
			return "outfit " + o.Name + ": no variants";
		if (variant < 0)
			variant = Math.RandomInt(0, o.Variants.Count());
		RefugeeArrivalOutfitVariant v = o.Variants[variant];
		TStringArray notes = new TStringArray;
		int worn = 0;
		foreach (RefugeeArrivalWorn w : v.Worn)
		{
			EntityAI item = DressItem(p, w.ClassName, o, notes);
			if (!item)
				continue;
			worn++;
			GiveAttachments(p, item, w.Attach, o, notes);
		}
		int carried = 0;
		if (o.Carried)
		{
			foreach (string cls : o.Carried)
			{
				if (DressItem(p, cls, o, notes))
					carried++;
			}
		}
		string weapons = "no primary";
		if (o.Primary && o.Primary.Count() > 0)
			weapons = GiveKitWeapon(p, o.Primary.GetRandomElement(), o, notes);
		weapons = weapons + ", " + GiveKitWeapon(p, o.Sidearm, o, notes);
		return "outfit " + o.Name + "/" + v.Name + ": " + worn + "/" + v.Worn.Count() + " worn, " + carried + " carried, " + weapons + ", notes " + notes.ToString();
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

	RefugeeArrivalVehicle PickLightVehicle()
	{
		if (!m_Config.LightVehicles || m_Config.LightVehicles.Count() == 0)
			return null;
		float total = 0;
		foreach (RefugeeArrivalVehicle v : m_Config.LightVehicles)
			total += v.Weight;
		if (total <= 0)
			return m_Config.LightVehicles[0];
		float roll = Math.RandomFloat(0, total);
		RefugeeArrivalVehicle last = m_Config.LightVehicles[m_Config.LightVehicles.Count() - 1];
		foreach (RefugeeArrivalVehicle w : m_Config.LightVehicles)
		{
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
		OutfitSelfTest();
	}

	// Blae 2026-10-23: dress a stand-in survivor in every outfit variant through the same Dress
	// a spawn uses, log what attached and what didn't, then delete it.
	void OutfitSelfTest()
	{
		RefugeeArrivalPoint p = m_Config.RoadPoints[0];
		vector pos = Vector(p.X, GetGame().SurfaceY(p.X, p.Z), p.Z);
		foreach (RefugeeArrivalOutfit o : m_Config.Outfits)
		{
			for (int v = 0; v < o.Variants.Count(); v++)
			{
				PlayerBase dummy = PlayerBase.Cast(GetGame().CreateObjectEx("SurvivorM_Mirek", pos, ECE_PLACE_ON_SURFACE));
				if (!dummy)
				{
					Print("[DZDS VehicleTest] FAIL outfit " + o.Name + ": no stand-in survivor");
					return;
				}
				Print("[DZDS VehicleTest] " + Dress(dummy, o, v));
				GetGame().ObjectDelete(dummy);
			}
		}
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

	// Blae 2026-10-22: wake near the others, not across the map from them. Road and arrival
	// spots within RespawnNearPlayersMin metres of any other living player online, else
	// within RespawnNearPlayersMax. Nobody else online: false, and the usual order applies.
	bool PickNearPlayers(RefugeeArrivalPlan plan)
	{
		if (m_Config.RespawnNearPlayersMax <= 0)
			return false;
		array<Man> men = new array<Man>;
		GetGame().GetPlayers(men);
		array<vector> others = new array<vector>;
		foreach (Man m : men)
		{
			if (!m || !m.IsAlive() || !m.GetIdentity() || m.GetIdentity().GetId() == plan.Uid)
				continue;
			others.Insert(m.GetPosition());
		}
		if (others.Count() == 0)
			return false;
		bool picked = PickPoint(PointsNear(others, m_Config.RespawnNearPlayersMin), plan);
		if (!picked)
			picked = PickPoint(PointsNear(others, m_Config.RespawnNearPlayersMax), plan);
		if (picked)
			plan.Where = plan.Where + " (near " + others.Count().ToString() + " player(s))";
		return picked;
	}

	// Road and arrival spots within `radius` metres (on the ground plane) of any centre.
	array<ref RefugeeArrivalPoint> PointsNear(array<vector> centres, float radius)
	{
		array<ref RefugeeArrivalPoint> near = new array<ref RefugeeArrivalPoint>;
		foreach (RefugeeArrivalPoint p : m_Config.RoadPoints)
		{
			if (NearAny(p, centres, radius))
				near.Insert(p);
		}
		foreach (RefugeeArrivalPoint site : m_Config.ArrivalSites)
		{
			if (NearAny(site, centres, radius))
				near.Insert(site);
		}
		return near;
	}

	static bool NearAny(RefugeeArrivalPoint p, array<vector> centres, float radius)
	{
		foreach (vector c : centres)
		{
			float dx = p.X - c[0];
			float dz = p.Z - c[2];
			if (dx * dx + dz * dz <= radius * radius)
				return true;
		}
		return false;
	}

	// Blae 2026-10-22: wake at the base, beside the raised territory flag nearest the last
	// death (any distance; with no recorded death, any raised flag), without a car.
	bool PickBase(RefugeeArrivalPlan plan, RefugeeArrivalRecord rec)
	{
		if (m_Config.BaseRespawn != 1)
			return false;
#ifdef DZDS_BASES
		vector from = "0 0 0";
		if (rec && rec.HasDeath == 1)
			from = Vector(rec.DeathX, 0, rec.DeathZ);
		TerritoryFlag flag = DZDSBases.NearestRaised(from);
		if (!flag)
			return false;
		plan.GrantVehicle = false;
		plan.AtBase = true;
		plan.CarPos = flag.GetPosition();
		plan.CarOri = flag.GetOrientation();
		plan.Where = "base (flag at " + Math.Round(plan.CarPos[0]).ToString() + "," + Math.Round(plan.CarPos[2]).ToString() + ")";
		return true;
#else
		return false; // @DZDS without base tracking (pre 2026-10-22): camp/road respawn as before
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
		float offset = m_Config.PlayerOffset;
		if (plan.AtCamp)
			offset = m_Config.CampPlayerOffset;
		if (plan.AtBase)
			offset = m_Config.BasePlayerOffset;
		plan.PlayerPos = BesideSpot(plan.CarPos, plan.CarOri[0], offset);
		// 2026-10-23: respawns kept landing ON the vehicle's spot; this line shows the inputs.
		Print("[DZDS Arrivals] place: spot " + Math.Round(plan.CarPos[0]).ToString() + "," + Math.Round(plan.CarPos[2]).ToString() + " heading " + plan.CarOri[0].ToString() + " offset " + offset.ToString() + " camp=" + plan.AtCamp.ToString() + " base=" + plan.AtBase.ToString() + " -> player " + Math.Round(plan.PlayerPos[0]).ToString() + "," + Math.Round(plan.PlayerPos[2]).ToString() + " (" + Math.Round(Dist2D(plan.PlayerPos, plan.CarPos)).ToString() + " m)");
	}

	// `offset` metres to one side of `spot`, perpendicular to `heading` (degrees), not in
	// water. Never closer than BESIDE_MIN_M: a spawning vehicle hits whoever stands on it.
	static vector BesideSpot(vector spot, float heading, float offset)
	{
		if (offset < BESIDE_MIN_M)
			offset = BESIDE_FALLBACK_M;
		float rad = heading * Math.DEG2RAD;
		float rx = Math.Cos(rad);
		float rz = -Math.Sin(rad);
		float side = 1;
		if (Math.RandomInt(0, 2) == 0)
			side = -1;
		float x = spot[0] + rx * offset * side;
		float z = spot[2] + rz * offset * side;
		if (IsWater(x, z))
		{
			x = spot[0] - rx * offset * side;
			z = spot[2] - rz * offset * side;
		}
		return Vector(x, GetGame().SurfaceY(x, z), z);
	}

	// Blae 2026-10-23: clear cooldowns WITHOUT a restart. The server holds the ledger in memory
	// and writes it on every spawn and death, so editing arrivals_ledger.json under a running
	// server is lost; `make reset-respawns LIVE=1 PLAYER=...` drops RESET instead, and the next
	// spawn applies and deletes it.
	void ApplyLiveResets()
	{
		if (!FileExist(RESET))
			return;
		RefugeeArrivalReset req = new RefugeeArrivalReset;
		JsonFileLoader<RefugeeArrivalReset>.JsonLoadFile(RESET, req);
		DeleteFile(RESET);
		if (!req.Ids)
			return;
		int n = 0;
		foreach (string id : req.Ids)
		{
			RefugeeArrivalRecord rec = FindRecord(id);
			if (!rec)
				continue;
			rec.LastVehicle = 0;
			rec.LastNavKit = 0;
			rec.HasDeath = 0;
			n++;
		}
		MakeDirectory(DIR);
		JsonFileLoader<RefugeeArrivalLedger>.JsonSaveFile(LEDGER, m_Ledger);
		Print("[DZDS Arrivals] live reset: cleared cooldowns for " + n.ToString() + " of " + req.Ids.Count().ToString() + " player(s)");
	}

	// A respawn may bring a Settler recruit (Expansion AI): CompanionChance, or the favored
	// player's own. Dog and horse companions were removed 2026-10-27 with their mods.
	void PickCompanion(RefugeeArrivalPlan plan, RefugeeArrivalFavored fav)
	{
		plan.GrantCompanion = false;
		plan.CompanionType = "";
		if (m_Config.CompanionEnabled != 1)
			return;

		float chance = m_Config.CompanionChance;
		if (fav)
		{
			if (fav.CompanionChance > 0)
				chance = fav.CompanionChance;
		}

		float roll = Math.RandomFloat01();
		if (roll >= chance)
			return;

		// Dog and horse companions were removed 2026-10-27 with their mods: only the Settler recruit.
		plan.GrantCompanion = true;
		plan.CompanionType = "npc";
	}

	RefugeeArrivalPlan Plan(PlayerIdentity identity)
	{
		if (!IsActive() || !identity)
			return null;
		ApplyLiveResets();

		RefugeeArrivalPlan plan = new RefugeeArrivalPlan;
		plan.Uid = identity.GetId();
		RefugeeArrivalRecord rec = FindRecord(plan.Uid);
		plan.FirstArrival = false;
		if (rec == null)
			plan.FirstArrival = true;
		// Plain ifs: `!plan.FirstArrival && m_Config.RandomCharacterOnRespawn == 1` logged
		// random=false on every respawn (2026-10-22/23) with the setting at 1.
		plan.RandomCharacter = false;
		if (!plan.FirstArrival)
		{
			if (m_Config.RandomCharacterOnRespawn == 1)
				plan.RandomCharacter = true;
		}
		plan.GrantVehicle = true;
		plan.StartsCooldown = true;
		plan.IsLightVehicle = false;
		if (rec && rec.LastVehicle > 0 && NowSeconds() - rec.LastVehicle < m_Config.CooldownHours * 3600)
			plan.GrantVehicle = false;
		TStringArray only = FavoredVehicles(plan.Uid);
		RefugeeArrivalFavored fav = FindFavored(plan.Uid);
		plan.AlwaysVehicle = false;
		if (fav)
		{
			if (fav.CooldownVehicles)
			{
				if (fav.CooldownVehicles.Count() > 0)
					plan.AlwaysVehicle = true;
			}
		}
		if (plan.AlwaysVehicle)
		{
			// Blae 2026-10-23: the cooldown covers the favored Vehicles (helicopters) only. Inside
			// it, a land vehicle that starts no cooldown of its own.
			if (!plan.GrantVehicle)
			{
				plan.GrantVehicle = true;
				plan.StartsCooldown = false;
				plan.IsLightVehicle = true;
				only = fav.CooldownVehicles;
			}
		}
		else if (!plan.GrantVehicle)
		{
			// Blae 2026-10-25: players who do not qualify for a fully-equipped vehicle receive a
			// light personal vehicle (dirtbike, moped, ATV) with operating supplies.
			// Starts no cooldown so they always have transport while their cooldown clock ticks.
			plan.GrantVehicle = true;
			plan.StartsCooldown = false;
			plan.IsLightVehicle = true;
		}

		plan.Archetype = PickArchetype(false);
		plan.Outfit = PickOutfit(plan, fav);
		PickCompanion(plan, fav);
		if (plan.GrantVehicle)
		{
			if (plan.IsLightVehicle)
			{
				plan.Vehicle = PickLightVehicle();
			}
			else
			{
				plan.Vehicle = PickVehicle(only);
			}
		}

		// Base and camp give no vehicle, so a player who always gets one skips them.
		bool baseCamp = !plan.FirstArrival;
		if (plan.AlwaysVehicle)
			baseCamp = false;
		bool placed = false;
		if (m_Config.RespawnAtHq == 1)
			placed = PickPoint(m_Config.HqPoints, plan);
		if (!placed && plan.FirstArrival)
			placed = PickColumnPoint(plan);
		if (!placed && !plan.FirstArrival)
			placed = PickNearPlayers(plan);
		if (!placed && baseCamp)
			placed = PickBase(plan, rec);
		if (!placed && baseCamp)
			placed = PickCamp(plan, rec);
		if (!placed && !plan.FirstArrival)
			placed = PickNearDeath(plan, rec);
		if (!placed)
			placed = PickPoint(m_Config.RoadPoints, plan);
		for (int r = 0; r < VEHICLE_REDRAWS && !placed && plan.GrantVehicle; r++)
		{
			// A big vehicle (transport helicopter, semi) may fit no spot here: draw another.
			if (plan.IsLightVehicle)
			{
				plan.Vehicle = PickLightVehicle();
			}
			else
			{
				plan.Vehicle = PickVehicle(only);
			}
			if (m_Config.RespawnAtHq == 1)
				placed = PickPoint(m_Config.HqPoints, plan);
			if (!placed && !plan.FirstArrival)
				placed = PickNearPlayers(plan);
			if (!placed && !plan.FirstArrival)
				placed = PickNearDeath(plan, rec);
			if (!placed)
				placed = PickPoint(m_Config.RoadPoints, plan);
		}
		if (!placed && plan.GrantVehicle)
		{
			// Every candidate was blocked: still wake at HQ/road, just without a vehicle.
			plan.GrantVehicle = false;
			if (m_Config.RespawnAtHq == 1)
				placed = PickPoint(m_Config.HqPoints, plan);
			if (!placed)
				placed = PickPoint(m_Config.RoadPoints, plan);
		}
		if (!placed)
		{
			if (m_Config.RespawnAtHq == 1)
			{
				plan.PlayerPos = Vector(14837.0, GetGame().SurfaceY(14837.0, 7855.0), 7855.0);
				plan.CarPos = BesideSpot(plan.PlayerPos, 0, m_Config.PlayerOffset);
				plan.CarOri = "0 0 0";
				plan.Where = "Qalat-e Lut HQ";
				placed = true;
			}
			else
			{
				return null;
			}
		}

		PlacePlayer(plan);
		return plan;
	}

	// `forced` (a dressed character's OutfitCargo) replaces the weighted draw.
	int FillCargo(CarScript car, bool aircraft, RefugeeArrivalArchetype forced = null)
	{
		RefugeeArrivalArchetype a = forced;
		if (!a)
			a = PickArchetype(aircraft);
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

	// Blae 2026-10-23: two respawns in a row woke ON the vehicle's spot, stuck inside the MH-6,
	// though CreateCharacter places the player PlayerOffset metres beside it (the ADM log has
	// them at the road point itself). Nothing found in the mission or the mods moves them, so
	// whatever does it, put them back on their planned spot and log where they were.
	static float Dist2D(vector a, vector b)
	{
		float dx = a[0] - b[0];
		float dz = a[2] - b[2];
		return Math.Sqrt(dx * dx + dz * dz);
	}

	// Positions by value: the call queue holds its arguments weakly, and the plan is released
	// as soon as the login finishes.
	string KeepBeside(PlayerBase player, vector carPos, vector playerPos, float heading, string when)
	{
		if (!player || !player.IsAlive())
			return "";
		vector was = player.GetPosition();
		if (Dist2D(was, carPos) >= BESIDE_MIN_M)
			return "";
		vector target = playerPos;
		if (Dist2D(target, carPos) < BESIDE_MIN_M)   // the plan itself put them on the spot
			target = BesideSpot(carPos, heading, m_Config.PlayerOffset);
		player.SetPosition(target);
		return " (" + when + ": was " + Math.Round(Dist2D(was, carPos)).ToString() + " m from the vehicle spot at " + Math.Round(was[0]).ToString() + "," + Math.Round(was[2]).ToString() + ", planned " + Math.Round(Dist2D(playerPos, carPos)).ToString() + " m, moved to " + Math.Round(Dist2D(target, carPos)).ToString() + " m beside it)";
	}

	void KeepBesideLater(PlayerBase player, vector carPos, vector playerPos, float heading)
	{
		string moved = KeepBeside(player, carPos, playerPos, heading, "recheck");
		if (moved != "")
			Print("[DZDS Arrivals] player back beside the vehicle" + moved);
	}

	void GiveNpcCompanion(PlayerBase player, vector spawnPos)
	{
#ifdef EXPANSIONMODAI
		TStringArray models = new TStringArray;
		models.Insert("SurvivorM_Mirek");
		models.Insert("SurvivorM_Boris");
		models.Insert("SurvivorF_Eva");
		models.Insert("SurvivorM_Denis");
		string charModel = models.GetRandomElement();

		eAIBase ai = eAIBase.Cast(GetGame().CreateObjectEx(charModel, spawnPos, ECE_INITAI));
		if (ai)
		{
			ai.SetFaction(new eAIFactionDZDSSettlers());
			DZDSCompanionManager.EquipRecruitCompanion(ai);
			eAIGroup grp = player.GetGroup();
			if (!grp)
				grp = eAIGroup.GetGroupByLeader(player);
			if (grp)
				grp.AddMember(ai);
			Print("[DZDS Arrivals] Spawned equipped Settler companion (" + charModel + ") for " + player.GetIdentity().GetName());
		}
#endif
	}

	string GiveCompanion(PlayerBase player, RefugeeArrivalPlan plan)
	{
		if (!player || !plan || !plan.GrantCompanion || plan.CompanionType == "")
			return "no companion";

		vector pPos = player.GetPosition();
		vector spawnPos = BesideSpot(pPos, player.GetOrientation()[0], 2.5);

		if (plan.CompanionType == "npc")
		{
			GiveNpcCompanion(player, spawnPos);
			return "companion (npc recruit)";
		}
		return "no companion";
	}

	void Deliver(PlayerBase player, RefugeeArrivalPlan plan)
	{
		if (!player || !plan)
			return;

		string got = "no vehicle (cooldown)";
		if (plan.AtCamp)
			got = "no vehicle (camp)";
		if (plan.AtBase)
			got = "no vehicle (base)";
		int now = NowSeconds();
		bool granted = false;
		CarScript car = null;
		string before = "";
		if (plan.GrantVehicle)
			before = KeepBeside(player, plan.CarPos, plan.PlayerPos, plan.CarOri[0], "before vehicle");
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
				int items = FillCargo(car, aircraft, OutfitCargo(plan.Outfit, aircraft));
				if (plan.IsLightVehicle)
				{
					// Operating supplies for light motor vehicles (dirtbike / moped / atv)
					if (plan.Vehicle.ClassName.Contains("Motorbike_01"))
						player.GetInventory().CreateInInventory("DirtBikeHelmet_Black");
					else if (plan.Vehicle.ClassName.Contains("Motorbike_02"))
						player.GetInventory().CreateInInventory("DirtBikeHelmet_Red");
					else if (plan.Vehicle.ClassName.Contains("Croco_QuadBike"))
						player.GetInventory().CreateInInventory("DirtBikeHelmet_Khaki");
					car.GetInventory().CreateInInventory("Wrench");
					car.GetInventory().CreateInInventory("TireRepairKit");
					car.GetInventory().CreateInInventory("CanisterGasoline");
				}
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
		{
			if (plan.StartsCooldown)
				rec.LastVehicle = now;
		}
		if (navGiven)
			rec.LastNavKit = now;
		MakeDirectory(DIR);
		JsonFileLoader<RefugeeArrivalLedger>.JsonSaveFile(LEDGER, m_Ledger);

		string kind = "respawn";
		if (plan.FirstArrival)
			kind = "first arrival";
		if (plan.Outfit)
			kind = kind + " as " + plan.Outfit.Name;
		if (granted)
		{
			if (!plan.StartsCooldown)
				got = got + " (no cooldown)";
		}
		string comp = GiveCompanion(player, plan);
		string beside = "";
		if (car)
		{
			beside = ", player " + Math.Round(vector.Distance(player.GetPosition(), car.GetPosition())).ToString() + " m from it" + before + KeepBeside(player, plan.CarPos, plan.PlayerPos, plan.CarOri[0], "after vehicle");
			GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(KeepBesideLater, BESIDE_RECHECK_MS, false, player, plan.CarPos, plan.PlayerPos, plan.CarOri[0]);
		}
		Print("[DZDS Arrivals] " + kind + " at " + plan.Where + ", random=" + plan.RandomCharacter.ToString() + ", " + got + beside + ", " + nav + ", " + comp + ", life " + rec.Lives);
	}
}

class DZDSCompanionDef
{
	string Name;
	string Title;
	string EntityClass;
	string Loadout;
	vector Position;
	float Heading;
	string Station;

	void DZDSCompanionDef(string name, string title, string entityCls, string loadout, vector pos, float heading, string station)
	{
		Name = name;
		Title = title;
		EntityClass = entityCls;
		Loadout = loadout;
		Position = pos;
		Heading = heading;
		Station = station;
	}
};

class DZDSCompanionManager
{
	static ref array<ref DZDSCompanionDef> s_Roster;
	static ref array<eAIBase> s_StationedAI;

	static void Init()
	{
#ifdef EXPANSIONMODAI
		if (!s_Roster)
		{
			s_Roster = new array<ref DZDSCompanionDef>;
			s_Roster.Insert(new DZDSCompanionDef("Soran the Scout", "Desert Tracker", "SurvivorM_Mirek", "DZDS_Settlers_scout", "14865.0 0.0 7970.0", 0.0, "North Watchtower"));
			s_Roster.Insert(new DZDSCompanionDef("Kaveh the Sentinel", "Fortress Guard", "SurvivorM_Boris", "DZDS_Settlers_guard", "14837.0 0.0 7815.0", 180.0, "South Gate Bastion"));
			s_Roster.Insert(new DZDSCompanionDef("Dr. Yasmin", "Field Surgeon", "SurvivorF_Eva", "DZDS_Settlers_medic", "14825.0 0.0 7855.0", 90.0, "Courtyard Clinic"));
			s_Roster.Insert(new DZDSCompanionDef("Rostam the Scavenger", "Logistics Runner", "SurvivorM_Denis", "DZDS_Settlers_scavenger", "14790.0 0.0 7880.0", 90.0, "West Workshop"));
		}

		if (!s_StationedAI)
			s_StationedAI = new array<eAIBase>;

		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(SpawnGarrison, 15000, false);
#endif
	}

	static void SpawnGarrison()
	{
#ifdef EXPANSIONMODAI
		if (!s_Roster)
			return;

		foreach (DZDSCompanionDef def : s_Roster)
		{
			eAIBase ai = eAIBase.Cast(GetGame().CreateObjectEx(def.EntityClass, def.Position, ECE_INITAI));
			if (ai)
			{
				vector ori = Vector(def.Heading, 0, 0);
				ai.SetOrientation(ori);
				ai.SetFaction(new eAIFactionDZDSSettlers());
				ExpansionHumanLoadout.Apply(ai, def.Loadout, false);

				s_StationedAI.Insert(ai);
				Print("[DZDS Companions] Stationed " + def.Name + " (" + def.Title + ") at " + def.Station + " " + def.Position.ToString());
			}
		}
		Print("[DZDS Companions] Spawned " + s_StationedAI.Count() + " hirable companion(s) at Qalat-e Lut.");
#endif
	}

	static void EquipRecruitCompanion(eAIBase ai, int variantIndex = -1)
	{
#ifdef EXPANSIONMODAI
		if (!ai)
			return;

		TStringArray loadouts = new TStringArray;
		loadouts.Insert("DZDS_Settlers_scout");
		loadouts.Insert("DZDS_Settlers_guard");
		loadouts.Insert("DZDS_Settlers_medic");
		loadouts.Insert("DZDS_Settlers_scavenger");

		string loadout = "DZDS_Settlers";
		if (variantIndex >= 0 && variantIndex < loadouts.Count())
			loadout = loadouts[variantIndex];
		else
			loadout = loadouts.GetRandomElement();

		ExpansionHumanLoadout.Apply(ai, loadout, false);
#endif
	}
};

// ===================================================================================
// DZDS Player Base Starting Supplies (Qalat-e Lut Fortress, [14837, 7855])
// Deploys base building containers, materials, kits, and tools for fresh starts.
// Checks existing objects on boot to prevent duplicating across server restarts.
// ===================================================================================
class DZDSBaseSupplies
{
	static const string MARKER_FILE = "$profile:DZDS\\base_supplies_deployed.txt";

	static void Init()
	{
		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(SpawnBaseSupplies, 12000, false);
	}

	static EntityAI CreateInCargo(EntityAI container, string itemClass, int quantity = 0)
	{
		if (!container || !container.GetInventory())
			return null;
		EntityAI item = container.GetInventory().CreateInInventory(itemClass);
		if (!item && container.GetInventory().GetCargo())
			item = container.GetInventory().CreateEntityInCargo(itemClass);
		if (!item)
			return null;
		if (quantity > 0)
		{
			ItemBase ib = ItemBase.Cast(item);
			if (ib)
				ib.SetQuantity(quantity);
		}
		return item;
	}

	static void SpawnBaseSupplies()
	{
		// Idempotency: check marker file to prevent restart duplication
		if (FileExist(MARKER_FILE))
		{
			Print("[DZDS Base] Base building supplies already deployed (" + MARKER_FILE + " exists). Skipping spawn.");
			return;
		}

		Print("[DZDS Base] Deploying fresh start base building supplies at Qalat-e Lut courtyard...");

		MakeDirectory("$profile:DZDS");
		FileHandle fh = OpenFile(MARKER_FILE, FileMode.WRITE);
		if (fh != 0)
		{
			FPrintln(fh, "deployed");
			CloseFile(fh);
		}

		// 1. Tool Chest (SeaChest 1) - Carpentry, Construction & Vehicle Maintenance Tools
		vector posChest1 = "14835.0 0.0 7853.0";
		posChest1[1] = GetGame().SurfaceY(posChest1[0], posChest1[2]);
		EntityAI toolChest = EntityAI.Cast(GetGame().CreateObjectEx("SeaChest", posChest1, ECE_PLACE_ON_SURFACE));
		if (toolChest)
		{
			CreateInCargo(toolChest, "Hatchet");
			CreateInCargo(toolChest, "Hatchet");
			CreateInCargo(toolChest, "WoodAxe");
			CreateInCargo(toolChest, "HandSaw");
			CreateInCargo(toolChest, "Hacksaw");
			CreateInCargo(toolChest, "Hammer");
			CreateInCargo(toolChest, "Hammer");
			CreateInCargo(toolChest, "SledgeHammer");
			CreateInCargo(toolChest, "Shovel");
			CreateInCargo(toolChest, "FieldShovel");
			CreateInCargo(toolChest, "Pliers");
			CreateInCargo(toolChest, "Pliers");
			CreateInCargo(toolChest, "Screwdriver");
			CreateInCargo(toolChest, "Screwdriver");
			CreateInCargo(toolChest, "Wrench");
			CreateInCargo(toolChest, "Wrench");
			CreateInCargo(toolChest, "Pickaxe");
			CreateInCargo(toolChest, "Crowbar");
			CreateInCargo(toolChest, "Whetstone");
			CreateInCargo(toolChest, "Whetstone");
			CreateInCargo(toolChest, "WeaponCleaningKit");
			CreateInCargo(toolChest, "WeaponCleaningKit");
			CreateInCargo(toolChest, "DuctTape");
			CreateInCargo(toolChest, "DuctTape");
			CreateInCargo(toolChest, "EpoxyPutty");
			CreateInCargo(toolChest, "EpoxyPutty");
		}

		// 2. Hardware & Kits Chest (SeaChest 2) - Fasteners, Locks, Base Kits & Blueprints
		vector posChest2 = "14836.5 0.0 7853.0";
		posChest2[1] = GetGame().SurfaceY(posChest2[0], posChest2[2]);
		EntityAI hardwareChest = EntityAI.Cast(GetGame().CreateObjectEx("SeaChest", posChest2, ECE_PLACE_ON_SURFACE));
		if (hardwareChest)
		{
			for (int n = 0; n < 8; n++)
				CreateInCargo(hardwareChest, "NailBox");
			CreateInCargo(hardwareChest, "FenceKit");
			CreateInCargo(hardwareChest, "FenceKit");
			CreateInCargo(hardwareChest, "FenceKit");
			CreateInCargo(hardwareChest, "FenceKit");
			CreateInCargo(hardwareChest, "WatchtowerKit");
			CreateInCargo(hardwareChest, "WatchtowerKit");
			CreateInCargo(hardwareChest, "TerritoryFlagKit");
			CreateInCargo(hardwareChest, "Flag_DayZ");
			CreateInCargo(hardwareChest, "DigitalCodeLock");
			CreateInCargo(hardwareChest, "DigitalCodeLock");
			CreateInCargo(hardwareChest, "DigitalCodeLock");
			CreateInCargo(hardwareChest, "DigitalCodeLock");
			CreateInCargo(hardwareChest, "Zen_CarWorkbenchKit");
			CreateInCargo(hardwareChest, "rag_hunting_cabin_kit");
			CreateInCargo(hardwareChest, "MetalWire");
			CreateInCargo(hardwareChest, "MetalWire");
			CreateInCargo(hardwareChest, "BarbedWire");
			CreateInCargo(hardwareChest, "BarbedWire");
			CreateInCargo(hardwareChest, "Rope");
			CreateInCargo(hardwareChest, "Rope");
			CreateInCargo(hardwareChest, "CamoNetDesert");
			CreateInCargo(hardwareChest, "CamoNetDesert");
		}

		// 3. Materials Crates (WoodenCrate x4) - Pre-cut Planks & Sheet Metal
		for (int c = 0; c < 4; c++)
		{
			vector posCrate = Vector(14835.0 + (c * 1.5), 0.0, 7856.5);
			posCrate[1] = GetGame().SurfaceY(posCrate[0], posCrate[2]);
			EntityAI crate = EntityAI.Cast(GetGame().CreateObjectEx("WoodenCrate", posCrate, ECE_PLACE_ON_SURFACE));
			if (crate)
			{
				CreateInCargo(crate, "WoodenPlank", 20);
				CreateInCargo(crate, "WoodenPlank", 20);
				CreateInCargo(crate, "MetalPlate", 10);
				CreateInCargo(crate, "NailBox");
			}
		}

		// 4. Fluid & Storage Barrels
		vector posBarrel1 = "14838.0 0.0 7853.0";
		posBarrel1[1] = GetGame().SurfaceY(posBarrel1[0], posBarrel1[2]);
		EntityAI barrel1 = EntityAI.Cast(GetGame().CreateObjectEx("Barrel_Blue", posBarrel1, ECE_PLACE_ON_SURFACE));
		if (barrel1)
		{
			CreateInCargo(barrel1, "WoodenPlank", 20);
			CreateInCargo(barrel1, "MetalPlate", 10);
			CreateInCargo(barrel1, "Rope");
		}

		vector posBarrel2 = "14839.5 0.0 7853.0";
		posBarrel2[1] = GetGame().SurfaceY(posBarrel2[0], posBarrel2[2]);
		EntityAI barrel2 = EntityAI.Cast(GetGame().CreateObjectEx("Barrel_Green", posBarrel2, ECE_PLACE_ON_SURFACE));
		if (barrel2)
		{
			CreateInCargo(barrel2, "WoodenPlank", 20);
			CreateInCargo(barrel2, "MetalPlate", 10);
			CreateInCargo(barrel2, "Rope");
		}

		// 5. Temporary Compound Shelter
		vector posTent = "14833.0 0.0 7855.0";
		posTent[1] = GetGame().SurfaceY(posTent[0], posTent[2]);
		EntityAI tent = EntityAI.Cast(GetGame().CreateObjectEx("MediumTent", posTent, ECE_PLACE_ON_SURFACE));

		Print("[DZDS Base] Deployed base building supply depot at Qalat-e Lut: 2 SeaChests, 4 WoodenCrates, 2 Barrels, 1 MediumTent, tools, hardware, and materials.");
	}
};

// ===================================================================================
// DZDS Base Recon & NPC Raid Defense System (Qalat-e Lut Citadel, [14837, 7855])
// NPC factions do not know where Player HQ is initially.
// If hostile scouts/patrols enter recon radius (< 1200m), discovery triggers.
// Once discovered, hostile factions organize periodic assault raids against Qalat-e Lut.
// ===================================================================================
class DZDSFactionRecon
{
	string FactionName;
	string DisplayName;
	string Loadout;
	int Discovered;
	int DiscoveredTime;
	int LastRaidTime;
	int RaidCount;

	void DZDSFactionRecon(string fName, string dName, string loadout)
	{
		FactionName = fName;
		DisplayName = dName;
		Loadout = loadout;
		Discovered = 0;
		DiscoveredTime = 0;
		LastRaidTime = 0;
		RaidCount = 0;
	}
};

class DZDSBaseReconData
{
	int BaseDiscovered;
	ref array<ref DZDSFactionRecon> Factions;
};

class DZDSBaseDefense
{
	static const string RECON_FILE = "$profile:DZDS\\base_recon.json";
	static const vector HQ_POS = "14837.0 0.0 7855.0";
	static const float RECON_RADIUS = 1200.0;
	static const int RAID_INTERVAL = 1800; // 30 minutes between raid waves
	static const int FIRST_RAID_DELAY = 180; // First raid arrives 3 minutes after discovery

	static ref DZDSBaseReconData s_Data;

	static void Init()
	{
		s_Data = new DZDSBaseReconData;
		s_Data.Factions = new array<ref DZDSFactionRecon>;

		if (FileExist(RECON_FILE))
		{
			JsonFileLoader<DZDSBaseReconData>.JsonLoadFile(RECON_FILE, s_Data);
		}

		if (!s_Data.Factions || s_Data.Factions.Count() == 0)
		{
			s_Data.BaseDiscovered = 0;
			s_Data.Factions = new array<ref DZDSFactionRecon>;
			s_Data.Factions.Insert(new DZDSFactionRecon("DZDSJackals", "The Jackal Cohort", "DZDS_Jackals"));
			s_Data.Factions.Insert(new DZDSFactionRecon("DZDSRust", "The Rust Syndicate", "DZDS_Rust"));
			s_Data.Factions.Insert(new DZDSFactionRecon("DZDSKarkas", "Karkas Mountain Clan", "DZDS_Karkas"));
			Save();
		}

		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(CheckRecon, 30000, true);
		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(CheckRaids, 60000, true);
		Print("[DZDS Base Defense] System online. Qalat-e Lut discovered status: " + s_Data.BaseDiscovered);
	}

	static void Save()
	{
		MakeDirectory("$profile:DZDS");
		JsonFileLoader<DZDSBaseReconData>.JsonSaveFile(RECON_FILE, s_Data);
	}

	static DZDSFactionRecon FindFaction(string name)
	{
		if (!s_Data || !s_Data.Factions)
			return null;
		foreach (DZDSFactionRecon f : s_Data.Factions)
		{
			if (f.FactionName == name)
				return f;
		}
		return null;
	}

	static void CheckRecon()
	{
#ifdef EXPANSIONMODAI
		if (!s_Data)
			return;

		vector hq = HQ_POS;
		hq[1] = GetGame().SurfaceY(hq[0], hq[2]);

		array<Man> survivors = new array<Man>;
		GetGame().GetPlayers(survivors);

		foreach (Man survivor : survivors)
		{
			eAIBase ai = eAIBase.Cast(survivor);
			if (!ai || !ai.IsAlive())
				continue;

			if (vector.Distance(ai.GetPosition(), hq) > RECON_RADIUS)
				continue;

			eAIFaction faction = ai.GetFaction();
			if (!faction)
				continue;

			string fName = faction.GetName();
			DZDSFactionRecon rec = FindFaction(fName);
			if (rec && rec.Discovered == 0)
			{
				rec.Discovered = 1;
				rec.DiscoveredTime = GetGame().GetTime() / 1000;
				rec.LastRaidTime = rec.DiscoveredTime - (RAID_INTERVAL - FIRST_RAID_DELAY);
				s_Data.BaseDiscovered = 1;
				Save();

				string alertMsg = "INTERCEPTED TRANSMISSION (87.8 MHz): Hostile " + rec.DisplayName + " scout spotted Qalat-e Lut! Citadel position compromised!";
				Print("[DZDS Base Defense] " + alertMsg);
			}
		}
#endif
	}

	static void CheckRaids()
	{
#ifdef EXPANSIONMODAI
		if (!s_Data || s_Data.BaseDiscovered == 0)
			return;

		int now = GetGame().GetTime() / 1000;
		foreach (DZDSFactionRecon f : s_Data.Factions)
		{
			if (f.Discovered == 1 && (now - f.LastRaidTime) >= RAID_INTERVAL)
			{
				LaunchRaid(f);
				f.LastRaidTime = now;
				f.RaidCount++;
				Save();
				break;
			}
		}
#endif
	}

	static void LaunchRaid(DZDSFactionRecon f)
	{
#ifdef EXPANSIONMODAI
		if (!f)
			return;

		TVectorArray approaches = new TVectorArray;
		approaches.Insert("14885.0 0.0 7750.0"); // South approach road
		approaches.Insert("14720.0 0.0 7800.0"); // West canyon trail
		approaches.Insert("14840.0 0.0 8050.0"); // North road

		vector spawnPos = approaches.GetRandomElement();
		spawnPos[1] = GetGame().SurfaceY(spawnPos[0], spawnPos[2]);

		string warn = "DEFENSE ALERT (87.8 MHz): Hostile assault party from " + f.DisplayName + " storming Qalat-e Lut!";
		Print("[DZDS Base Defense] " + warn);

		eAIGroup raidGroup = null;
		for (int i = 0; i < 4; i++)
		{
			vector p = spawnPos;
			p[0] = p[0] + Math.RandomFloatInclusive(-6, 6);
			p[2] = p[2] + Math.RandomFloatInclusive(-6, 6);
			p[1] = GetGame().SurfaceY(p[0], p[2]);

			string model = "SurvivorM_Mirek";
			if (i % 2 == 1) model = "SurvivorM_Boris";

			eAIBase raider = eAIBase.Cast(GetGame().CreateObjectEx(model, p, ECE_INITAI));
			if (raider)
			{
				if (f.FactionName == "DZDSJackals")
					raider.SetFaction(new eAIFactionDZDSJackals());
				else if (f.FactionName == "DZDSRust")
					raider.SetFaction(new eAIFactionDZDSRust());
				else if (f.FactionName == "DZDSKarkas")
					raider.SetFaction(new eAIFactionDZDSKarkas());

				string loadout = f.Loadout;
				if (i == 0)
				{
					if (f.FactionName == "DZDSJackals") loadout = "DZDS_Jackals_warlord";
					else if (f.FactionName == "DZDSRust") loadout = "DZDS_Rust_foreman";
				}
				ExpansionHumanLoadout.Apply(raider, loadout, false);

				if (i == 0)
				{
					raider.GetInventory().CreateInInventory("BreachingCharge");
					raider.GetInventory().CreateInInventory("BreachingChargeTimer");
				}

				if (!raidGroup)
					raidGroup = raider.GetGroup();
				else
					raidGroup.AddMember(raider);
			}
		}

		if (raidGroup)
		{
			vector gatePos = "14837.0 0.0 7815.0";
			gatePos[1] = GetGame().SurfaceY(gatePos[0], gatePos[2]);
			vector yardPos = HQ_POS;
			yardPos[1] = GetGame().SurfaceY(yardPos[0], yardPos[2]);

			raidGroup.AddWaypoint(gatePos);
			raidGroup.AddWaypoint(yardPos);
			Print("[DZDS Base Defense] Dispatched 4 raiders targeting Qalat-e Lut from " + spawnPos.ToString());
		}
#endif
	}
};

class DZDSGeocacheEntry
{
	int Id;
	string Landmark;
	string Coords;
	string ContainerClass;
	string Danger;
	ref TStringArray Items;
};

class DZDSGeocacheConfig
{
	ref array<ref DZDSGeocacheEntry> Geocaches;
};

class DZDSPlayerGeocacheRecord
{
	string PlayerId;
	string PlayerName;
	ref TIntArray AssignedCaches;
	int AssignedTime;

	void DZDSPlayerGeocacheRecord(string id = "", string name = "")
	{
		PlayerId = id;
		PlayerName = name;
		AssignedCaches = new TIntArray;
		AssignedTime = 0;
	}
};

class DZDSGeocacheLedger
{
	ref array<ref DZDSPlayerGeocacheRecord> Players;
};

class DZDSGeocacheManager
{
	static const string CONFIG_FILE = "$profile:DZDS\\geocaches.json";
	static const string LEDGER_FILE = "$profile:DZDS\\geocache_ledger.json";
	static const string MARKER_FILE = "$profile:DZDS\\geocaches_deployed.txt";

	static ref DZDSGeocacheConfig s_Config;
	static ref DZDSGeocacheLedger s_Ledger;
	static bool s_SpawnedThisSession = false;

	static void Init()
	{
		s_Config = new DZDSGeocacheConfig;
		s_Config.Geocaches = new array<ref DZDSGeocacheEntry>;

		if (FileExist(CONFIG_FILE))
		{
			JsonFileLoader<DZDSGeocacheConfig>.JsonLoadFile(CONFIG_FILE, s_Config);
		}

		s_Ledger = new DZDSGeocacheLedger;
		s_Ledger.Players = new array<ref DZDSPlayerGeocacheRecord>;

		if (FileExist(LEDGER_FILE))
		{
			JsonFileLoader<DZDSGeocacheLedger>.JsonLoadFile(LEDGER_FILE, s_Ledger);
		}

		if (!s_Ledger.Players)
			s_Ledger.Players = new array<ref DZDSPlayerGeocacheRecord>;

		Print("[DZDS Geocache] Loaded " + s_Config.Geocaches.Count().ToString() + " cache sites from " + CONFIG_FILE);
		GetGame().GetCallQueue(CALL_CATEGORY_GAMEPLAY).CallLater(DeployCaches, 15000, false);
	}

	static void SaveLedger()
	{
		MakeDirectory("$profile:DZDS");
		JsonFileLoader<DZDSGeocacheLedger>.JsonSaveFile(LEDGER_FILE, s_Ledger);
	}

	static DZDSPlayerGeocacheRecord FindPlayerRecord(string uid)
	{
		if (!s_Ledger || !s_Ledger.Players)
			return null;
		foreach (DZDSPlayerGeocacheRecord rec : s_Ledger.Players)
		{
			if (rec.PlayerId == uid)
				return rec;
		}
		return null;
	}

	static void DeployCaches()
	{
		if (s_SpawnedThisSession)
			return;
		s_SpawnedThisSession = true;

		if (FileExist(MARKER_FILE))
		{
			Print("[DZDS Geocache] Geocache world stashes already deployed (" + MARKER_FILE + " exists). Skipping world spawn.");
			return;
		}

		if (!s_Config || !s_Config.Geocaches)
			return;

		int count = 0;
		foreach (DZDSGeocacheEntry cache : s_Config.Geocaches)
		{
			vector pos = cache.Coords.ToVector();
			EntityAI chest = EntityAI.Cast(GetGame().CreateObjectEx(cache.ContainerClass, pos, ECE_CREATEPHYSICS));
			if (!chest)
				chest = EntityAI.Cast(GetGame().CreateObjectEx(cache.ContainerClass, pos, ECE_PLACE_ON_SURFACE));
			if (chest)
			{
				chest.SetPosition(pos);
				foreach (string itemCls : cache.Items)
				{
					EntityAI item = chest.GetInventory().CreateInInventory(itemCls);
					if (!item && chest.GetInventory().GetCargo())
						item = chest.GetInventory().CreateEntityInCargo(itemCls);

					if (item)
					{
						if (itemCls == "ER7_Gauss")
							item.GetInventory().CreateAttachment("ER7_Gauss_Battery");
						else if (itemCls == "Erapulsar_Exoskeleton")
							item.GetInventory().CreateAttachment("Erapulsar_Exoskeleton_Battery");
						else if (itemCls == "NVGoggles" || itemCls == "Rangefinder")
							item.GetInventory().CreateAttachment("Battery9V");
					}
				}
				count++;
			}
		}

		FileHandle f = OpenFile(MARKER_FILE, FileMode.WRITE);
		if (f != 0)
		{
			FPrintln(f, "Deployed " + count.ToString() + " geocache containers on Nasdara.");
			CloseFile(f);
		}
		Print("[DZDS Geocache] Deployed " + count.ToString() + " persistent geocache containers across Nasdara.");
	}

	static void AssignGeocaches(PlayerBase player)
	{
		if (!player || !player.GetIdentity())
			return;

		string uid = player.GetIdentity().GetId();
		string name = player.GetIdentity().GetName();

		// Give GPS Receiver with 9V battery
		EntityAI gps = player.GetInventory().CreateInInventory("GPSReceiver");
		if (!gps)
			gps = player.GetHumanInventory().CreateInHands("GPSReceiver");
		if (!gps)
			gps = EntityAI.Cast(GetGame().CreateObjectEx("GPSReceiver", player.GetPosition(), ECE_PLACE_ON_SURFACE));
		if (gps)
			gps.GetInventory().CreateAttachment("Battery9V");

		// Give ZenNote / Paper manifest
		EntityAI note = player.GetInventory().CreateInInventory("ZenNote");
		if (!note)
			note = player.GetInventory().CreateInInventory("Paper");

		if (!s_Config || !s_Config.Geocaches || s_Config.Geocaches.Count() == 0)
			return;

		DZDSPlayerGeocacheRecord rec = FindPlayerRecord(uid);
		int now = RefugeeArrivals.NowSeconds();
		if (!rec)
		{
			rec = new DZDSPlayerGeocacheRecord(uid, name);
			s_Ledger.Players.Insert(rec);
		}

		// Roll 3 distinct random geocaches from the 20 sites if not already assigned
		if (!rec.AssignedCaches || rec.AssignedCaches.Count() == 0)
		{
			rec.AssignedCaches = new TIntArray;
			int total = s_Config.Geocaches.Count();
			int targetCount = 3;
			if (targetCount > total)
				targetCount = total;

			while (rec.AssignedCaches.Count() < targetCount)
			{
				int pick = Math.RandomInt(0, total);
				if (rec.AssignedCaches.Find(pick) == -1)
					rec.AssignedCaches.Insert(pick);
			}
			rec.AssignedTime = now;
			SaveLedger();
		}

		string manifest = "[DZDS Geocache] Manifest issued to " + name + " (" + uid + "):\n";
		for (int i = 0; i < rec.AssignedCaches.Count(); i++)
		{
			int idx = rec.AssignedCaches.Get(i);
			if (idx >= 0 && idx < s_Config.Geocaches.Count())
			{
				DZDSGeocacheEntry entry = s_Config.Geocaches.Get(idx);
				manifest = manifest + "  [" + (i + 1).ToString() + "] " + entry.Landmark + " -> Grid: " + entry.Coords + " | Hazard: " + entry.Danger + "\n";
			}
		}
		Print(manifest);
	}
};

class CustomMission: MissionServer
{
	ref RefugeeArrivals m_RefugeeArrivals;
	ref RefugeeArrivalPlan m_ArrivalPlan;

	override void OnInit()
	{
		super.OnInit();
		DZDSCompanionManager.Init();
		DZDSBaseSupplies.Init();
		DZDSBaseDefense.Init();
		DZDSGeocacheManager.Init();
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
		else
		{
			pos = Vector(14837.0, GetGame().SurfaceY(14837.0, 7855.0), 7855.0);
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
		if (!m_RefugeeArrivals)
			m_RefugeeArrivals = new RefugeeArrivals();
		if (m_ArrivalPlan)
		{
			if (m_ArrivalPlan.Outfit && !m_ArrivalPlan.IsLightVehicle)
			{
				// Blae 2026-10-23: an outfit (Soviet Special Forces) instead of the civilian clothes.
				Print("[DZDS Arrivals] " + m_RefugeeArrivals.Dress(player, m_ArrivalPlan.Outfit));
				player.GetStatWater().Set( 1000 );
				player.GetStatEnergy().Set( 800 );
				RefugeeArrivals.GiveStartKit(player, m_RefugeeArrivals.RadioIndex(), m_RefugeeArrivals.Roadflare());
				return;
			}
			else if (m_ArrivalPlan.IsLightVehicle && m_ArrivalPlan.Archetype)
			{
				Print("[DZDS Arrivals] " + m_RefugeeArrivals.EquipLightArchetype(player, m_ArrivalPlan.Archetype));
				player.GetStatWater().Set( 1000 );
				player.GetStatEnergy().Set( 800 );
				RefugeeArrivals.GiveStartKit(player, m_RefugeeArrivals.RadioIndex(), m_RefugeeArrivals.Roadflare());
				return;
			}
		}

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
		itemEnt = player.GetInventory().CreateInInventory( "WaterBottle" );
		itemEnt = player.GetInventory().CreateInInventory( "PurificationTablets" );
		
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