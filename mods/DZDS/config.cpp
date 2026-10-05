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
			"DayZExpansion_AI_Scripts"
		};
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
			"Game"
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
		};
	};
};
