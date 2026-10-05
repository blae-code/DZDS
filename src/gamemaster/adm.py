"""DayZ .ADM log parsing and remote tailing over SFTP.

Vanilla .ADM covers connects, hits (with HP), deaths and positions. Vehicle crashes and
richer AI telemetry are NOT in vanilla ADM; those need the Enforce RestApi hook (TODO).
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

_TIME = r"^(?P<time>\d{2}:\d{2}:\d{2})(?:\.\d+)? \| "
_PLAYER = r'Player "(?P<name>[^"]+)"'
_POS = r"pos=<(?P<x>-?[\d.]+), (?P<y>-?[\d.]+), (?P<z>-?[\d.]+)>"

PATTERNS: list[tuple[str, re.Pattern]] = [
    ("connect", re.compile(_TIME + _PLAYER + r".*is connected")),
    ("disconnect", re.compile(_TIME + _PLAYER + r".*has been disconnected")),
    ("death", re.compile(_TIME + _PLAYER + r" \(DEAD\).*?(?:" + _POS + r")?.*?(?:killed by|died)(?P<by>.*)")),
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


def parse_line(line: str) -> AdmEvent | None:
    line = line.rstrip()
    for kind, pat in PATTERNS:
        m = pat.search(line)
        if not m:
            continue
        g = m.groupdict()
        pos = (float(g["x"]), float(g["z"])) if g.get("x") else None
        ev = AdmEvent(kind=kind, player=g["name"], time=g["time"], pos=pos,
                      hp=float(g["hp"]) if g.get("hp") else None,
                      by=(g.get("by") or "").strip() or None, raw=line)
        if ev.by and re.search(r"\beAI|Expansion|AI\b", ev.by):
            ev.tags.add("ai_combat")
        if ev.by and "Infected" in ev.by:
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
