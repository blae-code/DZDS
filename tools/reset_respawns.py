#!/usr/bin/env python3
"""Fresh respawns: clear the arrivals cooldowns and reset characters (everyone, or one player).

Run it with the server STOPPED (it refuses otherwise: the server holds the arrivals ledger in
memory and writes it back on every spawn and death, so an edit under a running server is lost):

  1. stop the server in the panel
  2. make reset-respawns            (DRY_RUN=1 to preview, YES=1 to skip the prompt)
  3. start the server

What it does, over SFTP (credentials from .env):
  * downloads profiles/DZDS/arrivals_ledger.json and storage_1/players.db into
    backups/reset-<UTC stamp>/ first;
  * zeroes every player's LastVehicle (the 24 h vehicle cooldown), LastNavKit and HasDeath,
    keeping the player known, so they come back on the respawn path (road + vehicle), not
    as a first arrival at the refugee column;
  * renames storage_1/players.db to players.db.old-<stamp> (never deleted), so every
    character starts fresh. The world (storage_1/data) is untouched.

With PLAYER=<id or favored name> (`--player`), only that player: their ledger record is reset
and their row is removed from a copy of players.db, which replaces the original (kept as
players.db.old-<stamp>). Everyone else keeps their character and cooldown.

With LIVE=1 (`--live`, needs PLAYER), the server may be RUNNING: it uploads
profiles/DZDS/reset_cooldowns.json naming that player, and init.c applies it (clears the
cooldowns, then deletes the file) at the next spawn of anyone. Cooldowns only: a live character
can't be reset under a running server, so use it after a death (the character is gone anyway).

The "is it stopped?" check is an A2S_INFO query to RCON_HOST:QUERY_PORT (default 26092),
which the game answers only while it runs.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import socket
import sqlite3
import sys
from pathlib import Path

import yaml

import active

ROOT = active.ROOT
A2S_INFO = b"\xff\xff\xff\xffTSource Engine Query\x00"
QUERY_PORT = 26092


def reset_ledger(ledger: dict, only: str | None = None) -> tuple[dict, int]:
    players = ledger.get("Players") or []
    n = 0
    for p in players:
        if only and p.get("Id") != only:
            continue
        p["LastVehicle"] = 0
        p["LastNavKit"] = 0
        p["HasDeath"] = 0
        n += 1
    return {**ledger, "Players": players}, n


def drop_character(db: Path, uid: str) -> int:
    """Remove one player's character from a local players.db copy; returns rows removed."""
    with sqlite3.connect(db) as conn:
        n = conn.execute("DELETE FROM Players WHERE UID = ?", (uid,)).rowcount
    return n


def resolve_player(arg: str) -> str:
    """An identity id as-is, or the id of a `favored` name in presets/arrivals.yaml."""
    favored = (yaml.safe_load((ROOT / "presets" / "arrivals.yaml").read_text()) or {}).get("favored") or []
    for f in favored:
        if f["name"].lower() == arg.lower():
            return f["id"]
    return arg


def live_request(ids: list[str]) -> dict:
    """The reset_cooldowns.json init.c reads (class RefugeeArrivalReset)."""
    return {"Ids": list(ids)}


async def apply_live(dry_run: bool, uid: str) -> int:
    import asyncssh

    env = os.environ
    ledger_path, _ = remote_paths()
    target = ledger_path.rsplit("/", 1)[0] + "/reset_cooldowns.json"
    body = json.dumps(live_request([uid]), indent=4)
    print(f"live reset: {target} -> {body.replace(chr(10), ' ')}")
    if dry_run:
        print("DRY_RUN: nothing changed on the server")
        return 0
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    local = ROOT / "backups" / f"reset-live-{stamp}.json"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(body)
    async with asyncssh.connect(env["SFTP_HOST"], port=int(env.get("SFTP_PORT") or 22),
                                username=env["SFTP_USER"], password=env["SFTP_PASSWORD"],
                                known_hosts=None) as conn:
        async with conn.start_sftp_client() as sftp:
            await sftp.put(str(local), target)
    print("done: applied at the next spawn (the RPT logs '[DZDS Arrivals] live reset')")
    return 0


def server_is_up(host: str, port: int, timeout: float = 3.0) -> bool:
    """True if anything answers an A2S_INFO query (an info reply or a challenge)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            s.sendto(A2S_INFO, (host, port))
            data, _ = s.recvfrom(1400)
        except OSError:
            return False
    return data[:4] == b"\xff\xff\xff\xff" and data[4:5] in (b"I", b"A")


def remote_paths() -> tuple[str, str]:
    env = os.environ
    base = (env.get("SFTP_REMOTE_ROOT") or "/").rstrip("/")
    profiles = env.get("REMOTE_PROFILES_DIR") or "profiles"
    missions = env.get("REMOTE_MPMISSIONS_DIR") or "mpmissions"
    return (f"{base}/{profiles}/DZDS/arrivals_ledger.json",
            f"{base}/{missions}/{active.mission_name()}/storage_1/players.db")


async def apply(dry_run: bool, assume_yes: bool, only: str | None = None) -> int:
    import asyncssh

    env = os.environ
    ledger_path, players_path = remote_paths()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = ROOT / "backups" / f"reset-{stamp}"
    async with asyncssh.connect(env["SFTP_HOST"], port=int(env.get("SFTP_PORT") or 22),
                                username=env["SFTP_USER"], password=env["SFTP_PASSWORD"],
                                known_hosts=None) as conn:
        async with conn.start_sftp_client() as sftp:
            has_ledger = await sftp.exists(ledger_path)
            has_players = await sftp.exists(players_path)
            backup.mkdir(parents=True, exist_ok=True)
            ledger, n, dropped = {"Players": []}, 0, 0
            if has_ledger:
                await sftp.get(ledger_path, str(backup / "arrivals_ledger.json"))
                ledger, n = reset_ledger(json.loads((backup / "arrivals_ledger.json").read_text()), only)
            if has_players:
                await sftp.get(players_path, str(backup / "players.db"))
                if only:
                    edited = backup / "players.reset.db"
                    edited.write_bytes((backup / "players.db").read_bytes())
                    dropped = drop_character(edited, only)

            who = f"player {only}" if only else "everyone"
            print(f"backup:     {backup.relative_to(ROOT)}")
            print(f"scope:      {who}")
            print(f"ledger:     {ledger_path}: " + (f"clear cooldowns for {n} player(s)" if has_ledger else "absent, nothing to clear"))
            if only:
                print(f"characters: {players_path}: " + (f"remove {dropped} character row(s), original kept as players.db.old-{stamp}" if has_players else "absent, already fresh"))
            else:
                print(f"characters: {players_path}: " + (f"rename to players.db.old-{stamp}" if has_players else "absent, already fresh"))
            if dry_run:
                print("DRY_RUN: nothing changed on the server")
                return 0
            if not (has_ledger or has_players):
                return 0
            if only and n == 0 and dropped == 0:
                print(f"{only} has no ledger record and no character: nothing to reset")
                return 0
            if not assume_yes and input("Apply to the server? [y/N] ").strip().lower() != "y":
                print("aborted: nothing changed")
                return 1

            if has_ledger:
                new = backup / "arrivals_ledger.reset.json"
                new.write_text(json.dumps(ledger, indent=4))
                # Plain overwrite: the Godlike panel's SFTP refuses posix-rename (2026-10-22).
                stray = ledger_path + ".reset-tmp"
                if await sftp.exists(stray):
                    await sftp.remove(stray)
                await sftp.put(str(new), ledger_path)
            if has_players:
                await sftp.rename(players_path, f"{players_path}.old-{stamp}")
                if only:
                    await sftp.put(str(backup / "players.reset.db"), players_path)
    print("done: start the server from the panel")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="show what would change, change nothing")
    ap.add_argument("--yes", action="store_true", help="don't prompt before writing")
    ap.add_argument("--player", help="only this player: identity id, or a `favored` name from arrivals.yaml")
    ap.add_argument("--live", action="store_true", help="server running: clear PLAYER's cooldowns at the next spawn")
    args = ap.parse_args(argv)
    only = resolve_player(args.player) if args.player else None
    if args.live:
        if not only:
            print("--live needs --player")
            return 2
        return asyncio.run(apply_live(args.dry_run, only))

    host = os.environ.get("RCON_HOST")
    port = int(os.environ.get("QUERY_PORT") or QUERY_PORT)
    if not host:
        print("RCON_HOST is not set in .env: can't check that the server is stopped")
        return 2
    if server_is_up(host, port):
        print(f"The server is running ({host}:{port} answers). Stop the server in the panel first, then re-run.")
        return 1
    print(f"server is stopped ({host}:{port} silent)")
    return asyncio.run(apply(args.dry_run, args.yes, only))


if __name__ == "__main__":
    sys.exit(main())
