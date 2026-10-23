#!/usr/bin/env python3
"""How often players meet human AI OUTSIDE the zones (spec §4.4 target: <= 1 per player per ~3 sessions).

An encounter = a player hit by AI, or a player hitting/killing AI, grouped per player into
windows of `--window` seconds. Sessions = 'is connected' lines. Zones come from the current
war ledger (or initial control).

Usage: tools/encounter_audit.py [ADM files...]   (default: server/profiles/*.ADM)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import active
import zones as zmod

sys.path.insert(0, str(active.ROOT / "src"))
from gamemaster.adm import parse_line  # noqa: E402


def _secs(t: str) -> int:
    h, m, s = (int(x) for x in t.split(":"))
    return h * 3600 + m * 60 + s


def audit(lines: list[str], zs, window_s: int = 300) -> dict[str, dict]:
    out: dict[str, dict] = {}
    last: dict[tuple[str, bool], int] = {}
    for line in lines:
        ev = parse_line(line)
        if not ev:
            continue
        if ev.kind == "connect" and not ev.is_ai:
            out.setdefault(ev.player, {"sessions": 0, "outside": 0, "inside": 0})["sessions"] += 1
            continue
        if ev.kind not in ("hit", "death") or not ev.pos:
            continue
        if not ev.is_ai and ev.by_is_ai:
            player = ev.player
        elif ev.is_ai and ev.by and ev.by.startswith('Player "'):
            player = ev.by.split('"')[1]
        else:
            continue
        where = zmod.inside(ev.pos[0], ev.pos[1], zs)
        rec = out.setdefault(player, {"sessions": 0, "outside": 0, "inside": 0})
        t = _secs(ev.time)
        key = (player, where)
        if key not in last or t - last[key] > window_s or t < last[key]:
            rec["inside" if where else "outside"] += 1
        last[key] = t
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="*")
    ap.add_argument("--window", type=int, default=300)
    a = ap.parse_args()
    files = [Path(f) for f in a.files] or sorted((active.ROOT / "server" / "profiles").glob("*.ADM"))
    from gamemaster.ledger import WarLedger
    led = WarLedger.load_or_new(active.map_name())
    zs = zmod.build(active.map_data(), led.s.control, led.locations())
    lines = [ln for f in files for ln in f.read_text(errors="replace").splitlines()]
    res = audit(lines, zs, a.window)
    import ui
    if ui.use_color():
        print(ui.banner("OPEN-COUNTRY ENCOUNTER AUDIT", subtitle=f"{len(files)} ADM log file(s)  │  Target: <= 0.33 outside encounters / session", width=86))
        rows = []
        worst = 0.0
        for p, r in sorted(res.items()):
            rate = r["outside"] / max(1, r["sessions"])
            worst = max(worst, rate)
            status = ui.badge("OVER", "err") if rate > 1 / 3 else ui.badge("OK", "ok")
            rows.append([p, str(r["sessions"]), str(r["outside"]), str(r["inside"]), f"{rate:.2f}", status])
        if rows:
            print(ui.table(["PLAYER", "SESSIONS", "OUTSIDE", "INSIDE", "RATE", "STATUS"], rows,
                           alignments=["left", "right", "right", "right", "right", "left"]))
        else:
            print(ui.panel("No player sessions or AI encounters recorded in current ADM files.", title="AUDIT CLEAN"))
        return 1 if worst > 1 / 3 else 0
    print(f"{len(files)} ADM file(s); target <= 0.33 outside encounters per session")
    worst = 0.0
    for p, r in sorted(res.items()):
        rate = r["outside"] / max(1, r["sessions"])
        worst = max(worst, rate)
        print(f"  {p:<24} sessions {r['sessions']:>3}  outside {r['outside']:>3}  inside {r['inside']:>3}  "
              f"rate {rate:.2f} {'OVER' if rate > 1 / 3 else 'ok'}")
    return 1 if worst > 1 / 3 else 0


if __name__ == "__main__":
    sys.exit(main())
