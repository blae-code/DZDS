#!/usr/bin/env python3
"""Find mods whose server copy no longer matches the Workshop or this machine's client copy.

Why this exists (2026-10-08): the Godlike panel downloads a Workshop mod only when its
`/@<id>` folder is MISSING. It never refreshes one that is already installed, so when a mod
updates on the Workshop, clients get the new version and the server keeps the old one, and
players are kicked after the password prompt ("mod updated on the client but not the server").
Restarting the server does not fix it.

Per enabled mod it reads, read-only:
  * the server's `/@<id>/` files over SFTP (sizes, and the newest mtime = when it was installed),
  * the Workshop's `time_updated` (public API, no key),
  * the local client copy in DAYZ_WORKSHOP_DIR (default: Steam's 221100 content dir).

Status:
  MISSING  no `/@<id>` on the server (the panel will download it on the next restart)
  DIFFERS  addons/ or keys/ on the server differ from the client copy: players are kicked
  STALE    the Workshop updated after the server installed it; clients that update get kicked
  OK       none of the above

Fix for DIFFERS/STALE: rename `/@<id>` aside in the panel's File Manager and restart (the panel
re-downloads missing folders), or upload the client copy with lowercased file names.

Exit: 0 all OK, 1 drift found, 2 could not measure (a check that read nothing is not clean).

Usage: tools/mod_drift.py [--all]
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import stat
import sys
from pathlib import Path

from modstring import load_mods, ordered
from verify_mods import fetch

DEFAULT_CLIENT = Path.home() / ".local/share/Steam/steamapps/workshop/content/221100"
# Our own mod is published moments after its files are built and uploaded, so the Workshop
# timestamp can trail the server copy by a little. A real third-party update landing within
# this window of a server download is unlikely; DIFFERS still catches it when the client has it.
SLACK_SECONDS = 600
COMPARED_DIRS = ("addons/", "keys/")

Files = dict[str, tuple[int, float]]  # lowercased relative path -> (size, mtime)


def compared(files: Files) -> dict[str, int]:
    """The files whose bytes clients and server must agree on, with their sizes."""
    return {p: s for p, (s, _) in files.items() if p.startswith(COMPARED_DIRS)}


def classify(server: Files | None, client: Files | None, ws_updated: int | None) -> tuple[str, str]:
    """(status, detail) for one mod. Pure, so it is tested without SFTP or Steam."""
    if server is None:
        return "MISSING", "no folder on the server"
    if not compared(server):
        return "MISSING", "server folder has no addons/ or keys/ files"
    if client is not None:
        s, c = compared(server), compared(client)
        if s != c:
            changed = sorted(p for p in s.keys() | c.keys() if s.get(p) != c.get(p))
            newer = "client" if max(t for _, t in client.values()) > max(t for _, t in server.values()) else "server"
            return "DIFFERS", f"{newer} copy is newer; differs in {', '.join(changed[:3])}" + (
                f" (+{len(changed) - 3})" if len(changed) > 3 else "")
    installed = max(t for _, t in server.values())
    if ws_updated and ws_updated > installed + SLACK_SECONDS:
        return "STALE", f"Workshop updated {_ts(ws_updated)}, server installed {_ts(installed)}"
    return "OK", ""


def _ts(t: float) -> str:
    return dt.datetime.fromtimestamp(t).strftime("%m-%d %H:%M")


def local_files(root: Path) -> Files | None:
    if not root.is_dir():
        return None
    out: Files = {}
    for p in root.rglob("*"):
        if p.is_file():
            st = p.stat()
            out[p.relative_to(root).as_posix().lower()] = (st.st_size, st.st_mtime)
    return out


async def remote_files(sftp, root: str) -> Files | None:
    import asyncssh

    out: Files = {}

    async def walk(path: str, rel: str) -> None:
        for e in await sftp.readdir(path):
            if e.filename in (".", ".."):
                continue
            a, child = e.attrs, f"{rel}{e.filename}"
            if a.permissions is not None and stat.S_ISDIR(a.permissions):
                await walk(f"{path}/{e.filename}", child + "/")
            else:
                out[child.lower()] = (a.size or 0, float(a.mtime or 0))

    try:
        await walk(root, "")
    except asyncssh.SFTPNoSuchFile:
        return None
    return out


async def server_inventory(ids: list[int]) -> dict[int, Files | None]:
    import asyncssh

    env = os.environ
    base = (env.get("SFTP_REMOTE_ROOT") or "/").rstrip("/")
    async with asyncssh.connect(env["SFTP_HOST"], port=int(env.get("SFTP_PORT") or 22),
                                username=env["SFTP_USER"], password=env["SFTP_PASSWORD"],
                                known_hosts=None) as conn:
        async with conn.start_sftp_client() as sftp:
            gate = asyncio.Semaphore(8)

            async def one(i: int):
                async with gate:
                    return i, await remote_files(sftp, f"{base}/@{i}")

            return dict(await asyncio.gather(*(one(i) for i in ids)))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--all", action="store_true", help="also list mods that are OK")
    args = ap.parse_args()

    mods = [m for m in ordered(load_mods()) if int(m.get("id") or 0) > 0]
    if not mods:
        print("No enabled mods with a Workshop ID: nothing was checked.", file=sys.stderr)
        return 2
    ids = [int(m["id"]) for m in mods]
    for key in ("SFTP_HOST", "SFTP_USER", "SFTP_PASSWORD"):
        if not os.environ.get(key):
            print(f"{key} is not set (run via make, which loads .env)", file=sys.stderr)
            return 2
    try:
        server = asyncio.run(server_inventory(ids))
    except Exception as exc:  # noqa: BLE001 - any failure here means we measured nothing
        print(f"Could not read the server over SFTP: {exc}", file=sys.stderr)
        return 2
    try:
        ws = {int(k): int(d.get("time_updated") or 0) for k, d in fetch(ids).items()}
    except Exception as exc:  # noqa: BLE001
        print(f"Workshop API unavailable ({exc}); checking server vs client only", file=sys.stderr)
        ws = {}
    client_root = Path(os.environ.get("DAYZ_WORKSHOP_DIR") or DEFAULT_CLIENT)

    counts: dict[str, int] = {}
    rows: list[list[str]] = []
    import ui
    rich = ui.use_color()
    for m in mods:
        i = int(m["id"])
        client = local_files(client_root / str(i)) if m.get("side") != "server" else None
        status, detail = classify(server.get(i), client, ws.get(i))
        counts[status] = counts.get(status, 0) + 1
        if status != "OK" or args.all:
            if rich:
                rows.append([ui.badge(status, status), f"@{i}", m["name"][:38], detail or "in sync"])
            else:
                print(f"{status:8} @{i:<11} {m['name'][:38]:38} {detail}")

    if rich and rows:
        print(ui.table(["STATUS", "WORKSHOP ID", "MOD NAME", "DETAIL"], rows, title="MOD DRIFT REPORT"))
    print(f"\n{len(mods)} mods checked: " + ", ".join(f"{n} {s}" for s, n in sorted(counts.items())))
    if client_root.is_dir():
        print(f"client copies: {client_root}")
    else:
        print(f"client copies not found at {client_root}: DIFFERS cannot be detected", file=sys.stderr)
    if counts.keys() - {"OK"}:
        print("Fix DIFFERS/STALE: rename /@<id> aside in the panel File Manager, then restart "
              "(the panel re-downloads missing folders). MISSING fixes itself on restart.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
