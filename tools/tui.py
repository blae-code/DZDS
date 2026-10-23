#!/usr/bin/env python3
"""Ad Aspera · DZDS Interactive Terminal UI (TUI) Command Deck.

Provides a keyboard-driven, multi-tab curses interface for inspecting the Nasdara /
Chernarus+ tactical map, War Ledger, Faction Diplomacy matrix, Front Plan (traders &
quests), Mod Loadout, Refugee Arrival Kit simulator, and GM / ADM Encounter Audit.

Also supports `--snapshot [--tab 1..5]` for non-interactive rendering and automated tests.

Keybindings:
  1..5 / Tab   Switch tactical view
  j/k or ↑/↓   Select site / item in active list
  m            Toggle active map (nasdara <-> chernarusplus)
  t            Simulate a War Turn in-memory (preview front-line evolution)
  r            Reset in-memory War Ledger back to disk state
  k            Roll a new Refugee Arrival Archetype Kit (in Tab 4)
  q / Esc      Quit TUI
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import active  # noqa: E402
import arrivals  # noqa: E402
import encounter_audit  # noqa: E402
import front_plan  # noqa: E402
import modstring  # noqa: E402
import patrol_gen  # noqa: E402
import status as status_mod  # noqa: E402
import ui  # noqa: E402
import zones as zmod  # noqa: E402
from gamemaster.adm import parse_line  # noqa: E402
from gamemaster.ledger import STATE, WarLedger  # noqa: E402

TABS = [
    "1:MAP & SITES",
    "2:FACTIONS & DIPLOMACY",
    "3:TRADERS & QUESTS",
    "4:MODS & KIT ROLLER",
    "5:GM & ENCOUNTER AUDIT",
]


class TuiState:
    def __init__(self, map_name: str | None = None) -> None:
        self.map_name = map_name or active.map_name()
        self.tab = 0
        self.cursor = 0
        self.kit_arch_idx = 0
        self.rng = random.Random()
        self.toast = "Ready · Press [1-5] or [Tab] to switch views, [j/k] to navigate, [t] to preview a war turn, [q] to quit."
        self.last_turn_events: list[str] = []
        self.reload()

    def reload(self) -> None:
        self.map_data = yaml.safe_load((ROOT / "maps" / f"{self.map_name}.yaml").read_text())
        if STATE.exists():
            try:
                self.led = WarLedger.load(self.map_name)
            except SystemExit:
                self.led = WarLedger.new(self.map_name)
        else:
            self.led = WarLedger.new(self.map_name)
        self.factions_cfg = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())
        self.traders_cfg = yaml.safe_load((ROOT / "presets" / "traders.yaml").read_text())
        self.quests_cfg = yaml.safe_load((ROOT / "presets" / "quests.yaml").read_text())
        self.arrivals_cfg = yaml.safe_load((ROOT / "presets" / "arrivals.yaml").read_text())
        self.mods = modstring.ordered(modstring.load_mods())
        self.archs = arrivals.archetypes(self.arrivals_cfg)
        self.sites = sorted(self.led.locations().keys())
        self.patrols = patrol_gen.generate(self.map_name, control=self.led.holders(), locs=self.led.locations())
        self.traders = front_plan.plan_traders(self.led, self.traders_cfg)
        self.quests = front_plan.plan_quests(self.led, self.quests_cfg)
        self.rolled_kit: list[str] = arrivals.simulate_kit(self.archs[self.kit_arch_idx % len(self.archs)], self.rng)
        self.cursor = min(self.cursor, max(0, len(self.sites) - 1))

    def toggle_map(self) -> None:
        self.map_name = "chernarusplus" if self.map_name == "nasdara" else "nasdara"
        self.cursor = 0
        self.last_turn_events = []
        self.reload()
        self.toast = f"Switched sector map to {self.map_name.upper()}"

    def simulate_turn(self) -> None:
        now = dt.datetime.now() + dt.timedelta(hours=4 * (self.led.s.turn + 1))
        self.last_turn_events = self.led.turn(now=now, force=True)
        self.patrols = patrol_gen.generate(self.map_name, control=self.led.holders(), locs=self.led.locations())
        self.traders = front_plan.plan_traders(self.led, self.traders_cfg)
        self.quests = front_plan.plan_quests(self.led, self.quests_cfg)
        ev_summary = "; ".join(self.last_turn_events[:2]) if self.last_turn_events else "quiet front"
        self.toast = f"Simulated Turn {self.led.s.turn} (in-memory preview): {ev_summary}"

    def roll_kit(self) -> None:
        self.kit_arch_idx = (self.kit_arch_idx + 1) % len(self.archs)
        arch = self.archs[self.kit_arch_idx]
        self.rolled_kit = arrivals.simulate_kit(arch, self.rng)
        self.toast = f"Rolled '{arch['Name']}' kit ({len(self.rolled_kit)} items, weapon: {self.rolled_kit[0]})"

    def selected_site(self) -> str:
        if not self.sites:
            return ""
        return self.sites[self.cursor % len(self.sites)]


def render_tab_snapshot(st: TuiState, tab: int | None = None, color: bool | None = None) -> str:
    """Render the active TUI tab as a multi-line string (used by both curses & --snapshot)."""
    idx = st.tab if tab is None else tab
    col_site = status_mod.active_column_site(st.map_data, st.arrivals_cfg)

    nav_pills = []
    for i, label in enumerate(TABS):
        if i == idx:
            nav_pills.append(ui.fg(f"▸ [{label}]", "coral", bold=True, enabled=color))
        else:
            nav_pills.append(ui.fg(f"  {label} ", "muted", enabled=color))
    nav_bar = "  ".join(nav_pills)

    out = [
        ui.banner(
            f"COMMAND DECK · {st.map_name.upper()}",
            subtitle=nav_bar,
            right=f"TURN {st.led.s.turn}",
            width=120,
            enabled=color,
        )
    ]

    if idx == 0:
        sel = st.selected_site()
        map_lines = ui.render_tactical_map(
            st.map_data,
            st.led.s.control,
            war_party=st.led.s.war_party,
            extra_sites=st.led.s.extra_sites,
            active_column=col_site,
            selected_site=sel,
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
            f"{ui.fg('⚔', 'contested', enabled=color)}Warzone"
        )
        left_box = ui.panel(
            "\n".join([*map_lines, ui.fg("─" * 54, "dim", enabled=color), legend]),
            title=f"TACTICAL SECTOR MAP · SELECTED: {sel.upper()}",
            width=58,
            enabled=color,
        ).splitlines()

        # Right side: site list + selected site dossier
        locs = st.led.locations()
        pos = locs.get(sel, [0, 0])
        holder = st.led.s.control.get(sel, "unheld")
        roles = sorted(st.led.site_roles(sel))
        site_patrols = [p for p in st.patrols if p["Name"].endswith(f"@ {sel}")]
        site_traders = [t for t in st.traders if t["site"] == sel]
        site_quests = [q for q in st.quests if q["site"] == sel or q["giver_site"] == sel]

        dossier_lines = [
            f"{ui.fg('Location:', 'muted', enabled=color)}  {ui.fg(sel, 'bone', bold=True, enabled=color)}  "
            f"({pos[0]:.0f}, {pos[1]:.0f})  │  Radius: {st.map_data.get('zone_radius_m', 400)} m",
            f"{ui.fg('Control: ', 'muted', enabled=color)}  "
            + (ui.faction_tag(holder, enabled=color) if holder != "unheld" else ui.fg("Open Country (Vanilla)", "muted", enabled=color)),
            f"{ui.fg('Roles:   ', 'muted', enabled=color)}  {', '.join(roles) or 'none'}",
            f"{ui.fg('Patrols: ', 'muted', enabled=color)}  {len(site_patrols)} squad(s), "
            f"up to {sum(p['NumberOfAIMax'] for p in site_patrols)} AI ("
            + (", ".join(f"{p['Name'].split(' @ ')[0]} [{p['NumberOfAI']}-{p['NumberOfAIMax']}]" for p in site_patrols[:2]) or "none") + ")",
            f"{ui.fg('Traders: ', 'muted', enabled=color)}  "
            + (", ".join(f"{t['display']} [{t['status'].upper()}]" for t in site_traders) or "none stationed here"),
            f"{ui.fg('Quests:  ', 'muted', enabled=color)}  "
            + (", ".join(f"{q['quest']} ({q['giver']})" for q in site_quests[:3]) or "none active here"),
        ]
        dossier_box = ui.panel("\n".join(dossier_lines), title=f"SITE DOSSIER · {sel.upper()}", width=60, enabled=color).splitlines()

        s_rows = []
        for i, sname in enumerate(st.sites):
            h = st.led.s.control.get(sname, "—")
            ptr = ui.fg("▸", "coral", bold=True, enabled=color) if i == (st.cursor % len(st.sites)) else " "
            h_tag = ui.faction_tag(h, enabled=color) if h != "—" else ui.fg("open country", "muted", enabled=color)
            r_str = ",".join(sorted(st.led.site_roles(sname)))
            s_rows.append([f"{ptr} {sname}", h_tag, r_str])
        stab = ui.table(["SITE NAME", "CONTROL / STATE", "ROLES"], s_rows[:14], title="SECTOR LOCATIONS (j/k to inspect)", enabled=color).splitlines()

        right_col = [*dossier_box, *stab]
        max_h = max(len(left_box), len(right_col))
        lw = max(ui.visible_len(ln) for ln in left_box)
        merged = [f"{ui.pad(left_box[i] if i < len(left_box) else '', lw)}  {right_col[i] if i < len(right_col) else ''}"
                  for i in range(max_h)]
        out.append("\n".join(merged))

    elif idx == 1:
        f_rows = []
        holders = st.led.holders()
        for f in ui.FACTION_ORDER:
            spec = st.factions_cfg["factions"][f]
            res = st.led.resources(f)
            res_str = " ".join(f"{k}:{v}" for k, v in sorted(res.items())) or "none"
            f_rows.append([
                ui.faction_tag(f, spec["display"], enabled=color),
                ui.meter(st.led.s.strength.get(f, 0), 100, width=10, color=f, enabled=color),
                ui.standing_bar(st.led.s.standing.get(f, 0), width=12, enabled=color),
                res_str,
                ", ".join(sorted(holders.get(f, []))) or "—",
            ])
        out.append(ui.table(
            ["FACTION", "STRENGTH", "PLAYER STANDING", "RESOURCES", "STRONGHOLDS"],
            f_rows,
            title="FACTION STRENGTH, STANDING & TERRITORY",
            enabled=color,
        ))
        # 5x5 Diplomacy Stance Matrix
        m_rows = []
        overrides = {(d["from"], d["to"]): d["stance"] for d in st.led.s.auto_diplomacy}
        for f_row in ui.FACTION_ORDER:
            row_cells = [ui.faction_tag(f_row, enabled=color)]
            stances = st.factions_cfg["factions"][f_row]["stance"]
            for f_col in ui.FACTION_ORDER:
                st_val = overrides.get((f_row, f_col), stances.get(f_col, "hostile"))
                b_col = "ok" if st_val == "friendly" else "warn" if st_val == "neutral" else "err"
                row_cells.append(ui.fg(st_val.upper(), b_col, bold=(f_row, f_col) in overrides, enabled=color))
            m_rows.append(row_cells)
        out.append(ui.table(["FROM \\ TOWARD", *ui.FACTION_ORDER], m_rows, title="DIPLOMACY & STANCE MATRIX", enabled=color))
        if st.last_turn_events:
            out.append(ui.panel("\n".join(f"★ {e}" for e in st.last_turn_events), title="LATEST SIMULATED TURN DISPATCHES", border_color="coral", width=120, enabled=color))

    elif idx == 2:
        t_rows = []
        for t in st.traders:
            raw = st.traders_cfg["traders"][t["trader"]]
            t_rows.append([
                ui.badge(t["status"].upper(), t["status"].upper(), enabled=color),
                t["display"],
                ui.faction_tag(raw["faction"], enabled=color) if raw["faction"] != "none" else "Independent",
                t["site"] or "—",
                ", ".join(raw.get("currencies", [])),
            ])
        out.append(ui.table(["STATUS", "TRADER", "FACTION", "CURRENT SITE", "CURRENCIES"], t_rows, title="DYNAMIC FACTION BARTER TRADERS", enabled=color))
        q_rows = [
            [ui.fg(q["quest"], "bone", bold=True, enabled=color), q["objective"], q["site"],
             ui.faction_tag(q["giver"], enabled=color), q["giver_site"], q["text"]]
            for q in st.quests
        ]
        out.append(ui.table(["QUEST ID", "TYPE", "TARGET SITE", "GIVER", "AT SITE", "IN-WORLD BRIEFING"], q_rows, title=f"LIVE FRONT-LINE QUESTS ({len(st.quests)})", enabled=color))

    elif idx == 3:
        arch = st.archs[st.kit_arch_idx % len(st.archs)]
        kit_lines = [
            f"{ui.fg('Archetype:', 'muted', enabled=color)} {ui.fg(arch['Name'].upper(), 'coral', bold=True, enabled=color)} "
            f"({'Pilot / Aircraft Profile' if arch['Aircraft'] else 'Ground Survivor Profile'}, weight {arch['Weight']:.0f})",
            f"{ui.fg('Firearm:  ', 'muted', enabled=color)} {ui.fg(st.rolled_kit[0], 'bone', bold=True, enabled=color)}  │  "
            f"Total Cargo Items: {len(st.rolled_kit)}",
            f"{ui.fg('Kit Roll: ', 'muted', enabled=color)} " + ", ".join(st.rolled_kit[:10]),
            "           " + ", ".join(st.rolled_kit[10:]),
        ]
        out.append(ui.panel("\n".join(kit_lines), title="REFUGEE ARRIVAL KIT SIMULATOR (Press [k] to roll next archetype)", border_color="cyan", width=120, enabled=color))

        tier_counts = {t: sum(1 for m in st.mods if m["tier"] == t) for t in modstring.TIER_NAMES}
        m_rows = []
        start = (st.cursor % max(1, len(st.mods)))
        window = st.mods[start:start + 12] or st.mods[:12]
        for m in window:
            m_rows.append([
                f"Tier {m['tier']} ({modstring.TIER_NAMES[m['tier']]})",
                f"@{m['id']}" if not m.get("local") else "LOCAL",
                m["folder"],
                m["name"][:36],
                m.get("side", "both"),
                ui.badge("VERIFIED" if m.get("verified") else "LOCAL", "ok" if m.get("verified") else "cyan", enabled=color),
            ])
        out.append(ui.table(
            ["LOAD TIER", "WORKSHOP ID", "FOLDER", "MOD NAME", "SIDE", "STATE"],
            m_rows,
            title=f"ENABLED MOD LOADOUT ({len(st.mods)} active: T1={tier_counts[1]}, T2={tier_counts[2]}, T3={tier_counts[3]}, T4={tier_counts[4]}) · j/k to scroll",
            enabled=color,
        ))

    elif idx == 4:
        adm_files = sorted((ROOT / "server" / "profiles").glob("*.ADM"))
        sim_file = ROOT / "gm_state" / "sim.ADM"
        if sim_file.exists():
            adm_files.append(sim_file)
        zs = zmod.build(st.map_data, st.led.s.control, st.led.locations())
        lines = [ln for f in adm_files[-3:] for ln in f.read_text(errors="replace").splitlines()[-400:]]
        audit_res = encounter_audit.audit(lines, zs)
        a_rows = []
        for p, r in sorted(audit_res.items()):
            rate = r["outside"] / max(1, r["sessions"])
            a_rows.append([p, str(r["sessions"]), str(r["outside"]), str(r["inside"]), f"{rate:.2f}",
                           ui.badge("OVER" if rate > 1 / 3 else "OK", "err" if rate > 1 / 3 else "ok", enabled=color)])
        if not a_rows:
            a_rows.append(["(no sessions in recent ADM tail)", "0", "0", "0", "0.00", ui.badge("CLEAN", "ok", enabled=color)])
        out.append(ui.table(["PLAYER", "SESSIONS", "OUTSIDE ZONES", "INSIDE ZONES", "OUTSIDE/SESS", "SPEC TARGET (<=0.33)"],
                            a_rows, title=f"OPEN-COUNTRY AI ENCOUNTER AUDIT ({len(adm_files)} ADM file(s))", enabled=color))

        parsed_events = []
        for ln in reversed(lines):
            ev = parse_line(ln)
            if ev and ev.kind in ("connect", "disconnect", "hit", "death"):
                parsed_events.append([
                    ev.time,
                    ui.badge(ev.kind.upper(), "err" if ev.kind == "death" else "warn" if ev.kind == "hit" else "cyan", enabled=color),
                    "AI" if ev.is_ai else "Player",
                    ev.player,
                    ev.faction or "Settlers",
                    ev.by or "—",
                ])
            if len(parsed_events) >= 8:
                break
        if not parsed_events:
            parsed_events.append(["—", ui.badge("IDLE", "muted", enabled=color), "—", "No recent combat/connect events", "—", "—"])
        out.append(ui.table(["TIME", "EVENT", "KIND", "ENTITY", "FACTION", "SOURCE / BY"], parsed_events, title="RECENT .ADM TELEMETRY STREAM", enabled=color))

    out.append(ui.panel(st.toast, title="OPERATOR TELEMETRY & KEYBINDINGS", border_color="dim", width=120, enabled=color))
    return "\n".join(out)


def run_interactive(st: TuiState) -> int:
    """Flicker-free 24-bit truecolor interactive TUI using alternate screen buffer."""
    import select
    import shutil
    import termios
    import tty

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    sys.stdout.flush()
    try:
        tty.setraw(fd)
        while True:
            cols, rows = shutil.get_terminal_size((124, 38))
            rendered = render_tab_snapshot(st, color=True)
            out_lines = []
            for line in rendered.splitlines()[: max(1, rows - 1)]:
                out_lines.append(line + "\x1b[K")
            sys.stdout.write("\x1b[H" + "\r\n".join(out_lines) + "\x1b[J")
            sys.stdout.flush()

            ch = os.read(fd, 1)
            if not ch:
                break
            if ch == b"\x1b":
                # Check for arrow key escape sequence
                if select.select([fd], [], [], 0.03)[0]:
                    seq = os.read(fd, 2)
                    if seq == b"[B":  # Down
                        st.cursor += 1
                    elif seq == b"[A":  # Up
                        st.cursor = max(0, st.cursor - 1)
                    elif seq == b"[C":  # Right
                        st.tab = (st.tab + 1) % len(TABS)
                        st.cursor = 0
                    elif seq == b"[D":  # Left
                        st.tab = (st.tab - 1) % len(TABS)
                        st.cursor = 0
                else:
                    break
            elif ch in (b"q", b"Q", b"\x03"):
                break
            elif ch in (b"1", b"2", b"3", b"4", b"5"):
                st.tab = int(ch.decode()) - 1
                st.cursor = 0
            elif ch == b"\t":
                st.tab = (st.tab + 1) % len(TABS)
                st.cursor = 0
            elif ch == b"j":
                st.cursor += 1
            elif ch == b"k":
                if st.tab == 3:
                    st.roll_kit()
                else:
                    st.cursor = max(0, st.cursor - 1)
            elif ch in (b"n", b"N"):
                st.roll_kit()
            elif ch in (b"m", b"M"):
                st.toggle_map()
            elif ch in (b"t", b"T"):
                st.simulate_turn()
            elif ch in (b"r", b"R"):
                st.reload()
                st.toast = "Reloaded War Ledger and presets from disk."
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=None)
    ap.add_argument("--snapshot", action="store_true", help="render active tab to stdout and exit")
    ap.add_argument("--tab", type=int, default=1, choices=[1, 2, 3, 4, 5], help="initial tab (1..5)")
    ap.add_argument("--color", action="store_true", help="force ANSI truecolor in --snapshot mode")
    ap.add_argument("--plain", action="store_true", help="disable ANSI color in --snapshot mode")
    args = ap.parse_args(argv)

    st = TuiState(args.map)
    st.tab = args.tab - 1
    if args.snapshot or not sys.stdout.isatty():
        color = True if args.color else False if args.plain else ui.use_color()
        print(render_tab_snapshot(st, color=color))
        return 0
    return run_interactive(st)


if __name__ == "__main__":
    sys.exit(main())
