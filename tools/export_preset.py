#!/usr/bin/env python3
"""Generate DayZ Launcher HTML and XML preset files from config/mods.yaml.

These presets can be directly imported into the official DayZ Launcher
via the Presets menu, or shared with players so their launcher automatically
subscribes to and loads all required mods.
"""
from __future__ import annotations

import datetime
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent
MODS_FILE = ROOT / "config" / "mods.yaml"
HTML_PRESET_FILE = ROOT / "presets" / "Ad_Aspera_Preset.html"
XML_PRESET_FILE = ROOT / "presets" / "Ad_Aspera.dayzpreset"

def load_active_mods():
    with open(MODS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    mods = [m for m in data.get("mods", []) if m.get("enabled", True)]
    return sorted(mods, key=lambda m: m["tier"])

def generate_html(mods, preset_name="Ad Aspera"):
    rows = []
    for m in mods:
        name = m.get("name", "Unknown Mod")
        wid = m.get("id")
        link = f"https://steamcommunity.com/sharedfiles/filedetails/?id={wid}"
        rows.append(
            f'      <tr data-type="ModContainer">\n'
            f'        <td data-type="DisplayName">{name}</td>\n'
            f'        <td>\n'
            f'          <a href="{link}" data-type="Link">{link}</a>\n'
            f'        </td>\n'
            f'      </tr>'
        )
    table_content = "\n".join(rows)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<html>
  <!--Created by DayZ Launcher: https://dayz.com-->
  <head>
    <meta name="DayZ-Mods-Preset" content="{preset_name}" />
    <title>DayZ Mods - {preset_name}</title>
  </head>
  <body>
    <h1>DayZ Mods - {preset_name}</h1>
    <table>
{table_content}
    </table>
  </body>
</html>
"""

def generate_xml(mods):
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
    ids = []
    for m in mods:
        wid = m.get("id")
        ids.append(f"    <id>steam:{wid}</id>")
    ids_content = "\n".join(ids)
    return f"""<?xml version="1.0" encoding="utf-8"?>
<addons-presets>
  <last-update>{now_iso}</last-update>
  <published-ids>
{ids_content}
  </published-ids>
  <dlcs-appids />
</addons-presets>
"""

def main():
    mods = load_active_mods()
    print(f"Loaded {len(mods)} active mods from {MODS_FILE.relative_to(ROOT)}")

    html_content = generate_html(mods)
    HTML_PRESET_FILE.write_text(html_content, encoding="utf-8")
    print(f"Wrote HTML preset: {HTML_PRESET_FILE.relative_to(ROOT)}")

    xml_content = generate_xml(mods)
    XML_PRESET_FILE.write_text(xml_content, encoding="utf-8")
    print(f"Wrote XML preset:  {XML_PRESET_FILE.relative_to(ROOT)}")

if __name__ == "__main__":
    main()
