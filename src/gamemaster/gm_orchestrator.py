"""GM orchestrator: tail .ADM → aggregate events → Gemma (Ollama) → dispatch via RCON.

Run:  python -m gamemaster.gm_orchestrator   (or `make gm`)
Dry-run (default, GM_DRY_RUN=1) logs what it would broadcast/spawn without touching RCON.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from collections import Counter, deque
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .adm import AdmEvent, HealthTracker, LocalAdmTailer, SftpAdmTailer, parse_line
from .ledger import WarLedger
from .llm import OllamaGM
from .rcon import RconClient
from .schema import GMPayload, resolve_coords

ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("gm")


def load_config() -> dict:
    load_dotenv(ROOT / ".env")
    cfg = yaml.safe_load((ROOT / "config" / "gm.yaml").read_text())
    map_name = os.environ.get("GM_MAP", cfg.get("map", "chernarusplus"))
    cfg["map"] = yaml.safe_load((ROOT / "maps" / f"{map_name}.yaml").read_text())
    cfg["dry_run"] = os.environ.get("GM_DRY_RUN", "1") != "0"
    factions = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())["factions"]
    # Logs carry the engine class name: our @DZDS factions (DZDSJackals) or, before @DZDS
    # is built, the interim built-ins (Raiders). Map both to the in-world display name.
    cfg["faction_voices"] = {spec.get("display", name).split(" (")[0]: spec["radio_voice"]
                             for name, spec in factions.items() if spec.get("radio_voice")}
    cfg["faction_names"] = {}
    for name, spec in factions.items():
        for key in ("custom_faction", "interim_faction"):
            if spec.get(key):
                cfg["faction_names"][spec[key]] = spec.get("display", name).split(" (")[0]
    return cfg


class EventAggregator:
    """Buffers events and decides when a cognition pass is warranted.

    Player events go into the digest individually. AI-vs-AI fighting (from Expansion's
    LogAIKilled) is too frequent for that, so it is tallied per faction pair and place,
    which is also the raw material for the campaign-scale war ledger.
    """

    SIGNIFICANT = {"death", "unconscious", "health_drop", "connect"}

    def __init__(self, maxlen: int = 200, faction_names: dict[str, str] | None = None) -> None:
        self.faction_names = faction_names or {}  # engine faction -> display name (DZDSJackals -> The Jackal Cohort)
        self.events: deque[AdmEvent] = deque(maxlen=maxlen)
        self.online: set[str] = set()
        self.last_pos: dict[str, tuple[float, float]] = {}
        self.health = HealthTracker()
        # (killer_faction, victim_faction, nearest_location) -> kills since last digest
        self.faction_kills: Counter[tuple[str, str, tuple[float, float] | None]] = Counter()

    def ingest(self, ev: AdmEvent) -> bool:
        """Returns True if this event should trigger an immediate GM pass."""
        if ev.is_ai:
            if ev.kind == "death" and ev.faction:
                killer = ev.by_faction or ("Players" if ev.by and ev.by.startswith("Player") else "Unknown")
                self.faction_kills[(killer, ev.faction, ev.pos)] += 1
            return False  # AI hits/positions are too chatty for the digest
        if ev.pos:
            self.last_pos[ev.player] = ev.pos
        if ev.kind == "connect":
            self.online.add(ev.player)
        elif ev.kind == "disconnect":
            self.online.discard(ev.player)
        if ev.kind == "hit" and ev.hp is not None and self.health.observe(ev.player, ev.hp):
            ev.tags.add("health_drop")
        if ev.kind == "position":
            return False  # too chatty to keep in the digest
        self.events.append(ev)
        return ev.kind in self.SIGNIFICANT or bool(ev.tags & self.SIGNIFICANT)

    def digest(self, locations: dict[str, list[float]]) -> str:
        def nearest(pos):
            if not pos or not locations:
                return "unknown"
            return min(locations, key=lambda n: (locations[n][0] - pos[0]) ** 2
                                                + (locations[n][1] - pos[1]) ** 2)

        lines = [f"Players online: {', '.join(sorted(self.online)) or 'none'}"]
        for p, pos in self.last_pos.items():
            if p in self.online:
                lines.append(f"- {p} last seen near {nearest(pos)}")
        if self.faction_kills:
            lines.append("Faction fighting since last report:")
            grouped: Counter[tuple[str, str, str]] = Counter()
            name = lambda f: self.faction_names.get(f, f)  # noqa: E731
            for (killer, victim, pos), n in self.faction_kills.items():
                grouped[(name(killer), name(victim), nearest(pos))] += n
            for (killer, victim, place), n in grouped.most_common(8):
                lines.append(f"- {killer} killed {n} {victim} near {place}")
        lines.append("Recent events:")
        for ev in list(self.events)[-25:]:
            extra = f" hp={ev.hp:.0f}" if ev.hp is not None else ""
            by = f" by {ev.by[:60]}" if ev.by else ""
            tags = f" [{','.join(sorted(ev.tags))}]" if ev.tags else ""
            lines.append(f"{ev.time} {ev.kind} {ev.player}{extra}{by} near {nearest(ev.pos)}{tags}")
        self.events.clear()
        self.faction_kills.clear()
        return "\n".join(lines)


class Orchestrator:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.map = cfg["map"]
        self.locations: dict[str, list[float]] = self.map.get("locations", {})
        self.bounds = tuple(self.map["bounds"])
        self.agg = EventAggregator(faction_names=cfg.get("faction_names"))
        self.gm = OllamaGM(os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                           os.environ.get("OLLAMA_MODEL", cfg.get("model", "gemma4:e4b")),
                           voices=cfg.get("faction_voices"))
        self.rcon: RconClient | None = None
        # The war ledger: every AI death is recorded against the nearest site; `make war-turn`
        # advances it between restarts. Recent war events open the first digest of a session.
        self.ledger = WarLedger.load(self.map.get("name", "chernarusplus"))
        self.pending_war_report = self.ledger.recent_events()
        self.wake = asyncio.Event()
        self.last_pass = 0.0

    async def start_rcon(self) -> None:
        if self.cfg["dry_run"]:
            log.info("DRY RUN: RCON disabled")
            return
        self.rcon = RconClient(os.environ["RCON_HOST"], int(os.environ.get("RCON_PORT", 2310)),
                               os.environ["RCON_PASSWORD"],
                               on_message=lambda m: log.debug("BE: %s", m))
        await self.rcon.connect()

    def make_tailer(self):
        """GM_TELEMETRY=file reads GM_ADM_FILE locally (no server needed); default is SFTP."""
        if os.environ.get("GM_TELEMETRY", "sftp") == "file":
            path = ROOT / os.path.expanduser(os.environ.get("GM_ADM_FILE", "gm_state/sim.ADM"))
            log.info("Telemetry: local file %s", path)
            return LocalAdmTailer(str(path), from_start=os.environ.get("GM_ADM_REPLAY") == "1")
        return SftpAdmTailer(
            os.environ["SFTP_HOST"], int(os.environ.get("SFTP_PORT", 22)),
            os.environ["SFTP_USER"], os.environ["SFTP_PASSWORD"],
            f"{os.environ.get('SFTP_REMOTE_ROOT', '/').rstrip('/')}/"
            f"{os.environ.get('REMOTE_PROFILES_DIR', 'profiles')}",
            poll_seconds=self.cfg.get("adm_poll_seconds", 5))

    async def telemetry_loop(self) -> None:
        async for line in self.make_tailer().lines():
            ev = parse_line(line)
            if not ev:
                continue
            if ev.is_ai and ev.kind == "death" and ev.faction:
                killer = ev.by_faction or ("Players" if ev.by and ev.by.startswith("Player") else None)
                self.ledger.record_death(ev.faction, killer, ev.pos)
            if self.agg.ingest(ev):
                self.wake.set()

    async def cognition_loop(self) -> None:
        heartbeat = self.cfg.get("heartbeat_seconds", 720)
        cooldown = self.cfg.get("min_seconds_between_passes", 120)
        while True:
            try:
                await asyncio.wait_for(self.wake.wait(), timeout=heartbeat)
            except asyncio.TimeoutError:
                pass
            self.wake.clear()
            wait = cooldown - (time.monotonic() - self.last_pass)
            if wait > 0:
                await asyncio.sleep(wait)
            if not self.agg.online and not self.cfg.get("run_when_empty", False):
                self.agg.events.clear()
                continue
            self.last_pass = time.monotonic()
            digest = self.agg.digest(self.locations)
            if self.pending_war_report:
                digest = ("War report since the last session (announce it in-world):\n- "
                          + "\n- ".join(self.pending_war_report) + "\n" + digest)
                self.pending_war_report = []
            self.ledger.save()
            log.debug("Digest:\n%s", digest)
            payload = await self.gm.decide(digest, list(self.locations))
            if payload:
                await self.dispatch(payload)

    async def dispatch(self, payload: GMPayload) -> None:
        if payload.narrative_broadcast:
            log.info("BROADCAST: %s", payload.narrative_broadcast)
            if self.rcon:
                await self.rcon.say_all(payload.narrative_broadcast)
        for action in payload.world_actions:
            xy = resolve_coords(action, self.locations, self.bounds)
            log.info("ACTION: %s at %s (delay %ss)", action.target, xy, action.delay_seconds)
            # TODO(phase 3/4): enqueue to the Enforce RestApi command queue on the server.
            # Until that mod hook exists, actions are logged only.

    async def run(self) -> None:
        await self.start_rcon()
        try:
            await asyncio.gather(self.telemetry_loop(), self.cognition_loop())
        finally:
            self.ledger.save()
            if self.rcon:
                self.rcon.close()
            await self.gm.aclose()


def main() -> None:
    logging.basicConfig(level=os.environ.get("GM_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    asyncio.run(Orchestrator(load_config()).run())


if __name__ == "__main__":
    main()
