#!/usr/bin/env python3
"""Executive tactical overview of the Ad Aspera · DZDS living sandbox.

Renders the live Braille/Unicode tactical map alongside the War Ledger faction table,
Front Plan trader/quest readiness, today's Refugee Arrival column, and build health.

Usage:
  tools/status.py [--map nasdara] [--color | --plain]
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import active  # noqa: E402
import front_plan  # noqa: E402
import modstring  # noqa: E402
import ui  # noqa: E402
from gamemaster.ledger import STATE, WarLedger  # noqa: E402


def active_column_site(map_data: dict, arrivals_cfg: dict) -> str | None:
    sites = list((map_data.get("arrival_sites") or {}).keys())
    if not sites:
        return None
    start_hour = int(arrivals_cfg.get("column_day_start_utc_hour", 8))
    now_utc = int(dt.datetime.now(dt.timezone.utc).timestamp())
    day = (now_utc - start_hour * 3600) // 86400
    return sites[day % len(sites)]


def render_overview(map_name: str | None = None, color: bool | None = None) -> str:
    map_name = map_name or active.map_name()
    map_data = active.map_data(map_name)
    led = WarLedger.load_or_new(map_name)
    arrivals_cfg = active.load_yaml("presets/arrivals.yaml")
    traders_cfg = active.load_yaml("presets/traders.yaml")
    quests_cfg = active.load_yaml("presets/quests.yaml")

    mods = modstring.ordered(modstring.load_mods())
    ws_mods = [m for m in mods if not m.get("local")]
    col_site = active_column_site(map_data, arrivals_cfg)

    out: list[str] = []

    # Build map panel (left) and faction table (right)
    map_lines = ui.render_tactical_map(
        map_data,
        led.s.control,
        war_party=led.s.war_party,
        extra_sites=led.s.extra_sites,
        active_column=col_site,
        width=54,
        height=20,
        enabled=color,
    )
    legend = (
        f"{ui.fg('◆', 'Settlers', enabled=color)}Settlers "
        f"{ui.fg('⛨', 'Peacekeepers', enabled=color)}UN "
        f"{ui.fg('▲', 'Jackals', enabled=color)}Jackals "
        f"{ui.fg('⛰', 'Karkas', enabled=color)}Karkas "
        f"{ui.fg('⚙', 'Rust', enabled=color)}Rust "
        f"{ui.fg('⚔', 'contested', enabled=color)}Warzone "
        f"{ui.fg('◈', 'cyan', enabled=color)}Column"
    )
    map_box = ui.panel(
        "\n".join([*map_lines, ui.fg("─" * 54, "dim", enabled=color), legend]),
        title=f"SECTOR MAP · {map_name.upper()} (16.4 × 16.4 km)",
        width=58,
        enabled=color,
    ).splitlines()

    holders = led.holders()
    f_rows = []
    for f in ui.FACTION_ORDER:
        sites = holders.get(f, [])
        res = led.resources(f)
        res_str = " ".join(f"{k[0].upper()}:{v}" for k, v in sorted(res.items())) or "—"
        f_rows.append([
            ui.faction_tag(f, enabled=color),
            str(len(sites)),
            res_str,
            ui.meter(led.s.strength.get(f, 0), 100, width=8, color=f, enabled=color),
            ui.standing_bar(led.s.standing.get(f, 0), width=10, enabled=color),
        ])
    ftab = ui.table(
        ["FACTION", "SITES", "RES", "STRENGTH", "STANDING"],
        f_rows,
        alignments=["left", "right", "left", "left", "left"],
        title="FACTION BALANCE & STANDING",
        enabled=color,
    ).splitlines()
    right_w = max(ui.visible_len(ln) for ln in ftab)

    # Contested & War Party summary box below faction table
    contested = sorted(holders.get("contested", []))
    held_list = [f"{ui.fg(s, h, enabled=color)}" for s, h in sorted(led.s.control.items()) if h != "contested"]
    wp = led.s.war_party
    wp_str = (
        f"{ui.badge(wp['kind'].upper(), 'warn', enabled=color)} {wp['faction']}: {wp['origin']} → {wp['target']}"
        if wp else ui.fg("None active this turn (open country quiet)", "muted", enabled=color)
    )
    zone_lines = [
        f"{ui.fg('Warzones:   ', 'muted', enabled=color)} "
        + (", ".join(ui.fg(s, "contested", bold=True, enabled=color) for s in contested) or "None"),
        f"{ui.fg('Strongholds:', 'muted', enabled=color)} " + ", ".join(held_list[:3]),
        "             " + ", ".join(held_list[3:6]) if len(held_list) > 3 else "",
        "             " + ", ".join(held_list[6:]) if len(held_list) > 6 else "",
        f"{ui.fg('War Party:  ', 'muted', enabled=color)} {wp_str}",
    ]
    zbox = ui.panel("\n".join([ln for ln in zone_lines if ln]), title="FRONT LINE INTEL", width=right_w, enabled=color).splitlines()

    # Traders & Quests
    traders = front_plan.plan_traders(led, traders_cfg)
    quests = front_plan.plan_quests(led, quests_cfg)
    t_lines = []
    for t in traders:
        st_badge = ui.badge(t["status"].upper(), t["status"].upper(), enabled=color)
        t_lines.append(f"{ui.pad(st_badge, 11)} {ui.pad(t['display'][:28], 29)} {ui.fg(t['site'] or '—', 'bone', enabled=color)}")
    t_lines.append(ui.fg(f"Live Quests: {len(quests)} active across {len({q['site'] for q in quests})} front-line site(s)", "cyan", enabled=color))
    tbox = ui.panel("\n".join(t_lines), title="TRADERS & LIVE QUESTS", width=right_w, enabled=color).splitlines()

    right_col = [*ftab, *zbox, *tbox]
    max_h = max(len(map_box), len(right_col))
    left_w = max(ui.visible_len(ln) for ln in map_box)
    total_w = left_w + 2 + right_w

    out.append(ui.banner(
        f"TACTICAL SANDBOX STATUS · {map_name.upper()}",
        subtitle=f"Mission: {map_data.get('mission')}  │  Mods: {len(ws_mods)} Workshop + @DZDS  │  Today's Column: {col_site or 'n/a'}",
        right=f"WAR TURN {led.s.turn}",
        width=total_w,
        enabled=color,
    ))

    combined = []
    for i in range(max_h):
        l_ln = map_box[i] if i < len(map_box) else ""
        r_ln = right_col[i] if i < len(right_col) else ""
        combined.append(f"{ui.pad(l_ln, left_w)}  {r_ln}")
    out.append("\n".join(combined))

    # Health & Quick Commands footer
    client_panel, _, _ = modstring.build_panel_fields(modstring.load_mods())
    panel_ok = modstring.PANEL_FILE.exists() and modstring.PANEL_FILE.read_text() == client_panel
    pbo_ok = (ROOT / "build" / "@DZDS" / "addons" / "dzds_scripts.pbo.dzds.bisign").exists()
    arr_ok = (ROOT / "server" / "profiles" / "DZDS" / "arrivals.json").exists()

    checks = "  │  ".join([
        f"Panel Mods: {ui.badge('OK' if panel_ok else 'STALE', enabled=color)}",
        f"@DZDS Signed Build: {ui.badge('OK' if pbo_ok else 'MISSING', enabled=color)}",
        f"Arrivals Config: {ui.badge('OK' if arr_ok else 'MISSING', enabled=color)}",
        f"Interfaces: {ui.fg('make dashboard', 'cyan', bold=True, enabled=color)} (Web) · "
        f"{ui.fg('make tui', 'cyan', bold=True, enabled=color)} (TUI)",
    ])
    out.append(ui.panel(checks, title="READINESS & INTERFACES", width=total_w, enabled=color))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=None)
    ap.add_argument("--color", action="store_true", help="force ANSI truecolor output")
    ap.add_argument("--plain", action="store_true", help="disable ANSI colors")
    args = ap.parse_args(argv)
    color = True if args.color else False if args.plain else None
    print(render_overview(args.map, color=color))
    return 0


if __name__ == "__main__":
    sys.exit(main())
