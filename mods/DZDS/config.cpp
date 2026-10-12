// @DZDS: this project's own server+client mod. Packed to @DZDS/addons/dzds_scripts.pbo
// and signed (see mods/README.md). Loads after Expansion AI, whose faction system it extends.
class CfgPatches
{
	class DZDS_Scripts
	{
		units[]={};
		weapons[]={};
		requiredVersion=0.1;
		requiredAddons[]=
		{
			"DayZExpansion_AI_Scripts",
			// Loads us after Simply's Car Trailer (3811085358) so the HeadlightH7 repair below
			// wins the merge. Drop this line if the trailer mod is ever removed, or @DZDS
			// stops loading (tests/test_dzds_contract.py checks both ways).
			"DZT_UtilityTrailer"
		};
	};
};
// Simply's Car Trailer declares `class HeadlightH7 {};` where it meant `class HeadlightH7;`.
// The braces redefine the class with no parent, stripping Inventory_Base, and the engine
// then refuses to create headlights at all ("Cannot create entity with abstract type
// HeadlightH7"): cars spawn without them and HeadlightH7_Box won't open (2026-10-12).
// Restoring the parent keeps vanilla's own HeadlightH7 values (scope, model, ...).
class CfgVehicles
{
	class Inventory_Base;
	class HeadlightH7: Inventory_Base
	{
	};
};
class CfgMods
{
	class DZDS
	{
		dir="DZDS";
		name="DZDS Living Sandbox";
		author="DZDS";
		type="mod";
		dependencies[]=
		{
			"Game",
			"World",
			"Mission"
		};
		class defs
		{
			class gameScriptModule
			{
				value="";
				files[]=
				{
					"DZDS/Scripts/3_Game"
				};
			};
			class worldScriptModule
			{
				value="";
				files[]=
				{
					"DZDS/Scripts/4_World"
				};
			};
			class missionScriptModule
			{
				value="";
				files[]=
				{
					"DZDS/Scripts/5_Mission"
				};
			};
		};
	};
};
