#!/usr/bin/env python3
"""Ad Aspera · DZDS Tactical Cartographic Terminal UI & Design System.

Provides truecolor ANSI styling, faction color tokens (matching mods/workshop/preview.png),
Unicode box-drawing tables, gauges, bipolar standing meters, and a Braille/Unicode tactical
map renderer for CLI tools and the interactive TUI.

Automatically degrades to clean plain text when stdout is not a TTY or NO_COLOR is set
(unless FORCE_COLOR=1 or color=True is explicitly requested), preserving all script/test
stdout contracts.
"""
from __future__ import annotations

import math
import os
import re
import sys
from typing import Iterable

ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")

# Exact RGB palette from the Ad Aspera · DZDS brand identity (mods/workshop/preview.png)
RGB: dict[str, tuple[int, int, int]] = {
    "coral": (219, 92, 75),          # #db5c4b — Ad Aspera signal red/coral
    "bone": (222, 220, 214),         # #dedcd6 — Primary stencil bone white
    "muted": (132, 144, 156),        # #84909c — Secondary tactical label
    "dim": (74, 86, 98),             # #4a5662 — Grid / frame border
    "contour": (110, 92, 66),        # #6e5c42 — Topographic contour ochre
    "ok": (98, 189, 123),            # #62bd7b — Nominal / verified
    "warn": (229, 176, 75),          # #e5b04b — Caution / relocated / stale
    "err": (224, 82, 82),            # #e05252 — Alert / contested / differs
    "cyan": (104, 192, 208),         # #68c0d0 — Telemetry / radio frequency
    # Five factions (in top-bar order from preview.png)
    "Settlers": (212, 175, 79),      # #d4af4f — Warm Frontier Brass/Gold
    "Peacekeepers": (111, 161, 217), # #6fa1d9 — UN Task Force Blue Shield
    "Jackals": (176, 149, 107),      # #b0956b — Lowland Nomad Desert Khaki
    "Karkas": (118, 156, 119),       # #769c77 — Mountain Clan Sage Green
    "Rust": (232, 133, 71),          # #e88547 — Syndicate Industrial Orange
    "contested": (224, 82, 82),      # #e05252 — Active Warzone Crimson
    "Infected": (148, 112, 160),     # #9470a0 — Infected
}

HEX: dict[str, str] = {k: f"#{r:02x}{g:02x}{b:02x}" for k, (r, g, b) in RGB.items()}

FACTION_ORDER = ("Settlers", "Peacekeepers", "Jackals", "Karkas", "Rust")

FACTION_SYMBOLS: dict[str, str] = {
    "Settlers": "◆",
    "Peacekeepers": "⛨",
    "Jackals": "▲",
    "Karkas": "⛰",
    "Rust": "⚙",
    "contested": "⚔",
    "Infected": "☣",
}

FACTION_SHORT: dict[str, str] = {
    "Settlers": "Frontier Settlers",
    "Peacekeepers": "UN Peacekeepers",
    "Jackals": "Jackal Cohort",
    "Karkas": "Karkas Clan",
    "Rust": "Rust Syndicate",
    "contested": "Contested Warzone",
}


def use_color(force: bool | None = None, stream=None) -> bool:
    """Return True when ANSI colors should be emitted."""
    if force is not None:
        return force
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR") in ("1", "true", "yes"):
        return True
    if os.environ.get("TERM") == "dumb":
        return False
    out = stream or sys.stdout
    return hasattr(out, "isatty") and out.isatty()


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", str(text))


def visible_len(text: str) -> int:
    return len(strip_ansi(text))


def pad(text: str, width: int, align: str = "left") -> str:
    s = str(text)
    vlen = visible_len(s)
    diff = max(0, width - vlen)
    if align == "right":
        return (" " * diff) + s
    if align == "center":
        left = diff // 2
        return (" " * left) + s + (" " * (diff - left))
    return s + (" " * diff)


def fg(text: str, color: str, bold: bool = False, dim: bool = False, enabled: bool | None = None) -> str:
    if not use_color(enabled):
        return str(text)
    r, g, b = RGB.get(color, RGB["bone"])
    prefix = f"\x1b[38;2;{r};{g};{b}m"
    if bold:
        prefix = "\x1b[1m" + prefix
    if dim:
        prefix = "\x1b[2m" + prefix
    return f"{prefix}{text}\x1b[0m"


def style(text: str, *, color: str | None = None, bold: bool = False, dim: bool = False,
          enabled: bool | None = None) -> str:
    if not use_color(enabled):
        return str(text)
    codes = []
    if bold:
        codes.append("1")
    if dim:
        codes.append("2")
    if color and color in RGB:
        r, g, b = RGB[color]
        codes.append(f"38;2;{r};{g};{b}")
    if not codes:
        return str(text)
    return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def faction_stripe(enabled: bool | None = None, seg_width: int = 4) -> str:
    """Render the signature 5-faction color bar from mods/workshop/preview.png."""
    bar = "━" * seg_width
    return " ".join(fg(bar, f, bold=True, enabled=enabled) for f in FACTION_ORDER)


def faction_tag(faction: str, label: str | None = None, enabled: bool | None = None) -> str:
    sym = FACTION_SYMBOLS.get(faction, "•")
    text = label or FACTION_SHORT.get(faction, faction)
    color = faction if faction in RGB else "bone"
    return fg(f"{sym} {text}", color, bold=(faction == "contested"), enabled=enabled)


def badge(text: str, kind: str | None = None, enabled: bool | None = None) -> str:
    key = (kind or text).upper().strip()
    color_map = {
        "OK": "ok",
        "OPEN": "ok",
        "CLEAN": "ok",
        "STRONGHOLD": "Peacekeepers",
        "STALE": "warn",
        "RELOCATED": "warn",
        "TODO": "warn",
        "CHECK": "warn",
        "DIFFERS": "err",
        "MISSING": "err",
        "REMOVED": "err",
        "CLOSED": "err",
        "OVER": "err",
        "CONTESTED": "contested",
        "WARZONE": "contested",
        "LOCAL": "cyan",
    }
    col = color_map.get(key, kind if kind in RGB else "muted")
    return fg(f"[{text}]", col, bold=True, enabled=enabled)


def meter(value: float, max_val: float = 100.0, width: int = 12, color: str | None = None,
          show_val: bool = True, enabled: bool | None = None) -> str:
    ratio = max(0.0, min(1.0, (value / max_val) if max_val > 0 else 0.0))
    filled = int(round(ratio * width))
    empty = width - filled
    col = color or ("ok" if ratio >= 0.6 else "warn" if ratio >= 0.3 else "err")
    bar = fg("▰" * filled, col, enabled=enabled) + fg("▱" * empty, "dim", enabled=enabled)
    if show_val:
        return f"{bar} {fg(f'{value:3.0f}', 'bone', bold=True, enabled=enabled)}"
    return bar


def standing_bar(value: float, width: int = 14, enabled: bool | None = None) -> str:
    """Bipolar -100..+100 standing gauge with center origin."""
    half = max(2, width // 2)
    clamped = max(-100.0, min(100.0, float(value)))
    mag = int(round(abs(clamped) / 100.0 * half))
    if clamped < 0:
        left = fg("░" * (half - mag), "dim", enabled=enabled) + fg("◀" + "━" * max(0, mag - 1), "err", enabled=enabled) if mag else fg("─" * half, "dim", enabled=enabled)
        right = fg("─" * half, "dim", enabled=enabled)
        col = "err" if clamped <= -30 else "warn"
    elif clamped > 0:
        left = fg("─" * half, "dim", enabled=enabled)
        right = fg("━" * max(0, mag - 1) + "▶", "ok", enabled=enabled) + fg("░" * (half - mag), "dim", enabled=enabled) if mag else fg("─" * half, "dim", enabled=enabled)
        col = "ok"
    else:
        left = fg("─" * half, "dim", enabled=enabled)
        right = fg("─" * half, "dim", enabled=enabled)
        col = "muted"
    mid = fg("┼", "bone", enabled=enabled)
    num = fg(f"{clamped:+4.0f}", col, bold=True, enabled=enabled)
    return f"{left}{mid}{right} {num}"


def banner(title: str, subtitle: str = "", right: str = "", width: int = 78,
           enabled: bool | None = None) -> str:
    """Render the Ad Aspera · DZDS tactical command header."""
    stripe = faction_stripe(enabled=enabled, seg_width=3)
    brand = fg("AD", "bone", bold=True, enabled=enabled) + " " + fg("ASPERA", "coral", bold=True, enabled=enabled)
    sub = fg(f" · {title.upper()}", "bone", bold=True, enabled=enabled)
    top_left = f"{brand}{sub}"
    top_right = fg(right, "cyan", enabled=enabled) if right else stripe
    inner = max(width - 4, visible_len(top_left) + visible_len(top_right) + 2)
    gap = max(1, inner - visible_len(top_left) - visible_len(top_right))
    lines = [
        fg("╭" + "─" * (inner + 2) + "╮", "dim", enabled=enabled),
        fg("│ ", "dim", enabled=enabled) + top_left + (" " * gap) + top_right + fg(" │", "dim", enabled=enabled),
    ]
    if subtitle:
        sub_line = fg(subtitle, "muted", enabled=enabled)
        right_stripe = stripe if right else ""
        sgap = max(1, inner - visible_len(sub_line) - visible_len(right_stripe))
        lines.append(
            fg("│ ", "dim", enabled=enabled) + sub_line + (" " * sgap) + right_stripe + fg(" │", "dim", enabled=enabled)
        )
    lines.append(fg("╰" + "─" * (inner + 2) + "╯", "dim", enabled=enabled))
    return "\n".join(lines)


def table(headers: list[str], rows: Iterable[ Iterable[object] ],
          alignments: list[str] | None = None, title: str | None = None,
          enabled: bool | None = None) -> str:
    """Render a rounded Unicode table with ANSI-aware column widths."""
    str_rows = [[str(c) for c in r] for r in rows]
    ncols = len(headers)
    aligns = alignments or ["left"] * ncols
    widths = [visible_len(h) for h in headers]
    for r in str_rows:
        for i, cell in enumerate(r[:ncols]):
            widths[i] = max(widths[i], visible_len(cell))

    def hline(left: str, mid: str, right: str, fill: str = "─") -> str:
        segs = [fill * (w + 2) for w in widths]
        return fg(left + mid.join(segs) + right, "dim", enabled=enabled)

    out = []
    if title:
        total_w = sum(w + 3 for w in widths) - 1
        t_str = f" {title} "
        rem = max(0, total_w - visible_len(t_str))
        out.append(fg("╭─", "dim", enabled=enabled) + fg(t_str, "bone", bold=True, enabled=enabled)
                   + fg("─" * max(0, rem - 1) + "╮", "dim", enabled=enabled))
        sep_top = "├"
        segs = ["─" * (w + 2) for w in widths]
        out.append(fg(sep_top + "┬".join(segs) + "┤", "dim", enabled=enabled))
    else:
        out.append(hline("╭", "┬", "╮"))

    hdr_cells = [
        " " + fg(pad(h, widths[i], aligns[i]), "muted", bold=True, enabled=enabled) + " "
        for i, h in enumerate(headers)
    ]
    vbar = fg("│", "dim", enabled=enabled)
    out.append(vbar + vbar.join(hdr_cells) + vbar)
    out.append(hline("├", "┼", "┤"))
    for r in str_rows:
        cells = [
            " " + pad(r[i] if i < len(r) else "", widths[i], aligns[i]) + " "
            for i in range(ncols)
        ]
        out.append(vbar + vbar.join(cells) + vbar)
    out.append(hline("╰", "┴", "╯"))
    return "\n".join(out)


def panel(body: str, title: str = "", border_color: str = "dim",
          width: int | None = None, enabled: bool | None = None) -> str:
    lines = body.splitlines() or [""]
    inner = max((visible_len(ln) for ln in lines), default=0)
    if title:
        inner = max(inner, visible_len(title) + 4)
    if width:
        inner = max(inner, width - 4)
    if title:
        t_str = f" {title} "
        rem = max(0, inner + 2 - visible_len(t_str) - 1)
        top = fg("╭─", border_color, enabled=enabled) + fg(t_str, "bone", bold=True, enabled=enabled) + fg("─" * rem + "╮", border_color, enabled=enabled)
    else:
        top = fg("╭" + "─" * (inner + 2) + "╮", border_color, enabled=enabled)
    bbar = fg("│", border_color, enabled=enabled)
    mid = [f"{bbar} {pad(ln, inner)} {bbar}" for ln in lines]
    bot = fg("╰" + "─" * (inner + 2) + "╯", border_color, enabled=enabled)
    return "\n".join([top, *mid, bot])


# ---- Braille / Unicode Tactical Map Renderer --------------------------------------
_BRAILLE_MAP = (
    (0x01, 0x08),
    (0x02, 0x10),
    (0x04, 0x20),
    (0x40, 0x80),
)


class BrailleCanvas:
    """2x4 subpixel Braille canvas with per-cell color and character overlays."""

    def __init__(self, char_w: int, char_h: int) -> None:
        self.cw = char_w
        self.ch = char_h
        self.pw = char_w * 2
        self.ph = char_h * 4
        self.dots = [[0] * char_w for _ in range(char_h)]
        self.colors: list[list[str | None]] = [[None] * char_w for _ in range(char_h)]
        self.overlays: dict[tuple[int, int], tuple[str, str, bool]] = {}

    def set_px(self, px: int, py: int, color: str | None = None) -> None:
        if 0 <= px < self.pw and 0 <= py < self.ph:
            cx, cy = px // 2, py // 4
            dx, dy = px % 2, py % 4
            self.dots[cy][cx] |= _BRAILLE_MAP[dy][dx]
            if color:
                self.colors[cy][cx] = color

    def circle(self, cx_px: float, cy_px: float, r_px: float, color: str, steps: int = 36) -> None:
        for i in range(steps):
            ang = 2 * math.pi * i / steps
            self.set_px(int(round(cx_px + r_px * math.cos(ang))),
                        int(round(cy_px + r_px * math.sin(ang))), color)

    def line(self, x0: float, y0: float, x1: float, y1: float, color: str, dashed: bool = False) -> None:
        dist = max(1, int(math.hypot(x1 - x0, y1 - y0)))
        for i in range(dist + 1):
            if dashed and (i // 2) % 2 == 1:
                continue
            t = i / dist
            self.set_px(int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t)), color)

    def put_text(self, cx: int, cy: int, text: str, color: str = "bone", bold: bool = False) -> None:
        if not (0 <= cy < self.ch):
            return
        for i, ch in enumerate(text):
            x = cx + i
            if 0 <= x < self.cw:
                self.overlays[(x, cy)] = (ch, color, bold)

    def render(self, enabled: bool | None = None) -> list[str]:
        rows = []
        for y in range(self.ch):
            line = []
            for x in range(self.cw):
                if (x, y) in self.overlays:
                    ch, col, b = self.overlays[(x, y)]
                    line.append(fg(ch, col, bold=b, enabled=enabled))
                else:
                    mask = self.dots[y][x]
                    ch = chr(0x2800 + mask) if mask else "·" if (x % 8 == 0 and y % 4 == 0) else " "
                    col = self.colors[y][x] or ("dim" if ch == "·" else None)
                    line.append(fg(ch, col, enabled=enabled) if col else ch)
            rows.append("".join(line))
        return rows


def render_tactical_map(
    map_data: dict,
    control: dict[str, str],
    *,
    war_party: dict | None = None,
    extra_sites: dict | None = None,
    active_column: str | None = None,
    selected_site: str | None = None,
    width: int = 58,
    height: int = 22,
    enabled: bool | None = None,
) -> list[str]:
    """Render a high-density Braille + Unicode tactical map of Nasdara or Chernarus+."""
    xmin, zmin, xmax, zmax = map_data.get("bounds", [0, 0, 16384, 16384])
    span_x = max(1.0, float(xmax - xmin))
    span_z = max(1.0, float(zmax - zmin))
    canvas = BrailleCanvas(width, height)

    def to_px(wx: float, wz: float) -> tuple[float, float]:
        nx = (wx - xmin) / span_x
        nz = 1.0 - (wz - zmin) / span_z  # North (+Z) at top
        return nx * (canvas.pw - 4) + 2, nz * (canvas.ph - 4) + 2

    def to_cell(wx: float, wz: float) -> tuple[int, int]:
        px, py = to_px(wx, wz)
        return max(0, min(width - 1, int(px // 2))), max(0, min(height - 1, int(py // 4)))

    # 1. Subtle topographic contour arcs in desert ochre
    for ring in (0.28, 0.52, 0.76):
        canvas.circle(canvas.pw * 0.62, canvas.ph * 0.38, min(canvas.pw, canvas.ph) * ring * 0.45, "dim", steps=48)

    locs = dict(map_data.get("locations") or {})
    if extra_sites:
        for k, v in extra_sites.items():
            locs[k] = v["pos"]

    zone_r = float(map_data.get("zone_radius_m", 400))
    r_px = max(2.5, (zone_r / span_x) * canvas.pw * 1.4)

    # 2. War party movement vector
    if war_party:
        orig, tgt = war_party.get("origin"), war_party.get("target")
        if orig in locs and tgt in locs:
            ox, oz = locs[orig][:2]
            tx, tz = locs[tgt][:2]
            p0, p1 = to_px(ox, oz), to_px(tx, tz)
            canvas.line(p0[0], p0[1], p1[0], p1[1], war_party.get("faction", "coral"), dashed=True)

    # 3. Unheld locations first, then arrival sites, then held strongholds/warzones on top
    for site, pos in sorted(locs.items()):
        if site in control:
            continue
        cx, cy = to_cell(pos[0], pos[1])
        is_sel = (site == selected_site)
        short = site.split()[0][:6]
        tag = f"[{short}]" if is_sel else f"·{short}"
        canvas.put_text(max(0, min(width - len(tag), cx)), cy, tag,
                        "bone" if is_sel else "muted", bold=is_sel)

    for aname, apos in (map_data.get("arrival_sites") or {}).items():
        cx, cy = to_cell(apos[0], apos[1])
        is_col = (aname == active_column)
        canvas.put_text(cx, cy, "◈" if is_col else "◇", "cyan" if is_col else "muted", bold=is_col)

    for site, pos in sorted(locs.items()):
        holder = control.get(site)
        if not holder:
            continue
        px, py = to_px(pos[0], pos[1])
        cx, cy = to_cell(pos[0], pos[1])
        is_sel = (site == selected_site)
        col = holder if holder in RGB else "coral"
        canvas.circle(px, py, r_px, col, steps=24)
        sym = FACTION_SYMBOLS.get(holder, "●")
        short = site.split()[0][:8]
        tag = f"[{sym}{short}]" if is_sel else f"{sym}{short}"
        canvas.put_text(max(0, min(width - len(tag), cx - 1)), cy, tag,
                        "bone" if is_sel else col, bold=True)

    return canvas.render(enabled=enabled)
