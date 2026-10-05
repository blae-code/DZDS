"""Deliver GM world actions to the server through @DZDS's command queue.

The GM writes one JSON file per decision into $profile:DZDS/queue/ (DZDSWorld.c polls it,
spawns allowlisted classnames, deletes the file). Locally (GM_TELEMETRY=file with the local
test server, whose profile is the repo's server/profiles) it writes the file directly; against
the GSP it uploads over SFTP.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

import yaml

from .schema import WorldAction

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parents[2]


def load_actions() -> dict:
    return yaml.safe_load((ROOT / "presets" / "world.yaml").read_text())["gm_actions"]


def to_commands(action: WorldAction, xy: tuple[float, float] | None, actions: dict) -> list[dict]:
    spec = actions.get(action.target) or {}
    classes = spec.get("classnames") or []
    if not xy or not classes or not spec.get("count"):
        return []
    return [{"Type": "spawn", "ClassName": classes[0], "X": float(xy[0]), "Z": float(xy[1]),
             "Count": int(spec["count"])}]


def queue_filename() -> str:
    return f"gm_{int(time.time() * 1000)}.json"


class QueueWriter:
    def __init__(self) -> None:
        self.local = os.environ.get("GM_TELEMETRY", "sftp") == "file"
        self.local_dir = ROOT / "server" / "profiles" / "DZDS" / "queue"

    async def write(self, commands: list[dict]) -> str | None:
        if not commands:
            return None
        body = json.dumps({"Commands": commands}, indent=2)
        name = queue_filename()
        if self.local:
            self.local_dir.mkdir(parents=True, exist_ok=True)
            (self.local_dir / name).write_text(body)
            return str(self.local_dir / name)
        import asyncssh
        remote_dir = (f"{os.environ.get('SFTP_REMOTE_ROOT', '/').rstrip('/')}/"
                      f"{os.environ.get('REMOTE_PROFILES_DIR', 'profiles')}/DZDS/queue")
        async with asyncssh.connect(os.environ["SFTP_HOST"], port=int(os.environ.get("SFTP_PORT", 22)),
                                    username=os.environ["SFTP_USER"], password=os.environ["SFTP_PASSWORD"],
                                    known_hosts=None) as conn:
            async with conn.start_sftp_client() as sftp:
                await sftp.makedirs(remote_dir, exist_ok=True)
                async with sftp.open(f"{remote_dir}/{name}.part", "w") as f:
                    await f.write(body)
                await sftp.rename(f"{remote_dir}/{name}.part", f"{remote_dir}/{name}")
        return f"{remote_dir}/{name}"
