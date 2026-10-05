"""DayZ .ADM log parsing and remote tailing over SFTP.

Vanilla .ADM covers connects, hits (with HP), deaths and positions. With Expansion AI's
LogAIHitBy / LogAIKilled enabled, AI appear too, with their faction in the prefix:
    AI "Name" (group=12:"Patrol" faction="East" pos=<x, y, z>)
and players in an Expansion group get ` group=.. faction=".."` before pos=. That's how the
GM sees faction-vs-faction fighting. Vehicle crashes are still NOT in ADM (needs a server hook).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_TIME = r"^(?P<time>\d{2}:\d{2}:\d{2})(?:\.\d+)? \| "
_PLAYER = r'(?P<etype>Player|AI) "(?P<name>[^"]+)"'
_POS = r"pos=<(?P<x>-?[\d.]+), (?P<y>-?[\d.]+), (?P<z>-?[\d.]+)>"

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("connect", re.compile(_TIME + _PLAYER + r".*is connected")),
    ("disconnect", re.compile(_TIME + _PLAYER + r".*has been disconnected")),
    ("death", re.compile(_TIME + _PLAYER + r" \(DEAD\)(?:[^<]*?" + _POS + r")?.*?(?:killed by|died)(?P<by>.*)")),
    ("unconscious", re.compile(_TIME + _PLAYER + r".*?" + _POS + r".*is unconscious")),
    ("hit", re.compile(_TIME + _PLAYER + r".*?" + _POS + r".*?\[HP: (?P<hp>[\d.]+)\] hit by (?P<by>.*)")),
    ("position", re.compile(_TIME + _PLAYER + r".*?" + _POS + r"\)?\s*$")),
]


@dataclass
class AdmEvent:
    kind: str
    player: str
    time: str
    pos: tuple[float, float] | None = None  # (x, z) map plane; DayZ y is altitude
    hp: float | None = None
    by: str | None = None
    raw: str = ""
    tags: set[str] = field(default_factory=set)
    is_ai: bool = False               # the subject (victim/actor) is an Expansion AI
    faction: str | None = None        # subject's faction, if logged
    by_is_ai: bool = False            # the attacker/killer is an Expansion AI
    by_faction: str | None = None     # attacker/killer's faction, if logged


_FACTION = re.compile(r'faction="([^"]*)"')
_SPLIT = re.compile(r"\b(?:hit by|killed by)\b")


def _factions(line: str) -> tuple[str | None, str | None]:
    """Faction of the subject (before 'hit/killed by') and of the attacker (after)."""
    parts = _SPLIT.split(line, maxsplit=1)
    subj = _FACTION.search(parts[0])
    by = _FACTION.search(parts[1]) if len(parts) > 1 else None
    return (subj.group(1) if subj else None, by.group(1) if by else None)


def parse_line(line: str) -> AdmEvent | None:
    line = line.rstrip()
    for kind, pat in PATTERNS:
        m = pat.search(line)
        if not m:
            continue
        g = m.groupdict()
        pos = (float(g["x"]), float(g["z"])) if g.get("x") else None
        by = (g.get("by") or "").strip() or None
        faction, by_faction = _factions(line)
        ev = AdmEvent(kind=kind, player=g["name"], time=g["time"], pos=pos,
                      hp=float(g["hp"]) if g.get("hp") else None, by=by, raw=line,
                      is_ai=g.get("etype") == "AI", faction=faction,
                      by_is_ai=bool(by and (by.startswith('AI "') or "eAI" in by)),
                      by_faction=by_faction)
        if ev.by_is_ai or (ev.is_ai and kind in {"hit", "death"}):
            ev.tags.add("ai_combat")
        if ev.is_ai and ev.by_is_ai and faction and by_faction and faction != by_faction:
            ev.tags.add("faction_combat")
        if by and "Infected" in by:
            ev.tags.add("infected")
        return ev
    return None


class HealthTracker:
    """Flags a player whose HP fell by more than `threshold` within `window` seconds."""

    def __init__(self, threshold: float = 40.0, window: float = 120.0) -> None:
        self.threshold, self.window = threshold, window
        self._hist: dict[str, list[tuple[float, float]]] = {}

    def observe(self, player: str, hp: float, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        hist = [(t, h) for t, h in self._hist.get(player, []) if now - t <= self.window]
        peak = max([h for _, h in hist] + [hp])
        hist.append((now, hp))
        self._hist[player] = hist
        if peak - hp > self.threshold:
            self._hist[player] = [(now, hp)]  # reset so one fight fires once
            return True
        return False


class SftpAdmTailer:
    """Polls the newest DayZServer*.ADM on the remote and yields new lines."""

    def __init__(self, host: str, port: int, user: str, password: str, profiles_dir: str,
                 poll_seconds: float = 5.0) -> None:
        self.host, self.port, self.user, self.password = host, port, user, password
        self.profiles_dir, self.poll = profiles_dir.rstrip("/"), poll_seconds

    async def lines(self):
        import asyncssh  # imported lazily so tests don't need it

        current, offset, buf = None, 0, b""
        while True:
            try:
                async with asyncssh.connect(self.host, port=self.port, username=self.user,
                                            password=self.password, known_hosts=None) as conn:
                    async with conn.start_sftp_client() as sftp:
                        while True:
                            names = [n for n in await sftp.listdir(self.profiles_dir)
                                     if n.upper().endswith(".ADM")]
                            if names:
                                newest = max(names)  # names embed a sortable timestamp
                                path = f"{self.profiles_dir}/{newest}"
                                if newest != current:
                                    # On first sight skip history; on rotation read from start.
                                    size = (await sftp.stat(path)).size or 0
                                    offset = size if current is None else 0
                                    current, buf = newest, b""
                                    log.info("Tailing %s from byte %d", path, offset)
                                async with sftp.open(path, "rb") as f:
                                    await f.seek(offset)
                                    chunk = await f.read()
                                if chunk:
                                    offset += len(chunk)
                                    buf += chunk
                                    *complete, buf = buf.split(b"\n")
                                    for raw in complete:
                                        yield raw.decode("utf-8", "replace")
                            await asyncio.sleep(self.poll)
            except (OSError, asyncssh.Error) as exc:
                log.warning("SFTP tail error (%s); reconnecting in 15s", exc)
                await asyncio.sleep(15)


class LocalAdmTailer:
    """Follows a local .ADM file, or the newest *.ADM in a directory (e.g. the local test
    server's server/profiles), switching when the server rotates logs.

    from_start=True replays the whole first file, useful for testing against real logs.
    """

    def __init__(self, path: str, from_start: bool = False, poll_seconds: float = 1.0) -> None:
        self.path, self.from_start, self.poll = path, from_start, poll_seconds

    def _newest(self) -> str | None:
        import glob
        import os

        if os.path.isdir(self.path):
            files = glob.glob(os.path.join(self.path, "*.ADM"))
            return max(files, key=os.path.getmtime) if files else None
        return self.path if os.path.exists(self.path) else None

    async def lines(self):
        import os

        current, f, buf = None, None, ""
        try:
            while True:
                newest = self._newest()
                if newest is None:
                    log.info("Waiting for an .ADM at %s", self.path)
                    await asyncio.sleep(2)
                    continue
                if newest != current:
                    if f:
                        f.close()
                    f = open(newest, "r", encoding="utf-8", errors="replace")
                    if current is None and not self.from_start:
                        f.seek(0, os.SEEK_END)
                    current, buf = newest, ""
                    log.info("Tailing %s", newest)
                chunk = f.read()
                if chunk:
                    buf += chunk
                    *complete, buf = buf.split("\n")
                    for line in complete:
                        yield line
                else:
                    await asyncio.sleep(self.poll)
        finally:
            if f:
                f.close()
