#!/usr/bin/env python3
"""Free up disk space on the remote DayZ dedicated server over SFTP.

The remote server (Godlike Rampage plan) has a 70 GB disk quota.
Over time, crashed server processes dump multi-gigabyte Linux `core.*` files,
mod update cycles leave `stale-<id>-<date>` folders, old setup snapshots
accumulate (`fresh-start-*`), disabled mods (`config/mods.yaml` enabled: false)
retain unreferenced `/@<id>` folders, and `profiles/` gathers memory crash dumps
and ancient logs.

Safety:
  - Default is DRY RUN. Deletions happen only when --apply is passed.
  - Active mods and the active mission (dayzOffline.nasdara) are protected.
  - Core DayZ binaries, server config, and keys are protected.

Usage:
  tools/clean_server.py                 # dry run report of all reclaimable space
  tools/clean_server.py --cores --apply # delete only core.* dumps (59+ GB)
  tools/clean_server.py --all-safe --apply # delete cores, stale mods, fresh-starts, disabled mods, and crash dumps
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.modstring import load_mods

PROTECTED_NAMES = {
    "serverdz.cfg",
    "dayzserver",
    "dayzsetting.xml",
    "dayz.gproj",
    "steamclient.so",
    "libsteam_api.so",
    "keys",
    "dta",
    "addons",
    "battleye",
    "steamcmd",
    ".steam",
    "steam",
    "server_manager",
    "docs",
}


@dataclass
class CleanupItem:
    category: str
    path: str
    size: int
    mtime: float
    is_dir: bool
    description: str


def format_size(num_bytes: int) -> str:
    """Format bytes as human-readable string (B, KB, MB, GB)."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    elif num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


def classify_entry(
    name: str,
    size: int,
    mtime: float,
    is_dir: bool,
    enabled_ids: set[str],
    disabled_mods: dict[str, str],
    now_ts: float | None = None,
    log_days: int = 7,
    parent: str = "",
) -> CleanupItem | None:
    """Pure classification of a remote entry. Returns a CleanupItem or None if kept."""
    now = now_ts if now_ts is not None else time.time()
    lower = name.lower()

    # Never touch protected top-level names
    if not parent and lower in PROTECTED_NAMES:
        return None

    # Top-level checks
    if not parent:
        # 1. Core dumps at root: core.<pid>
        if not is_dir and name.startswith("core."):
            return CleanupItem(
                category="cores",
                path=name,
                size=size,
                mtime=mtime,
                is_dir=False,
                description=f"Linux kernel core dump ({format_size(size)})",
            )

        # 2. Stale mod folders from updates: stale-<id>-<date>
        if is_dir and name.startswith("stale-"):
            return CleanupItem(
                category="stale",
                path=name,
                size=size,
                mtime=mtime,
                is_dir=True,
                description=f"Stale mod backup folder ({format_size(size)})",
            )

        # 3. Old fresh-start backup directories: fresh-start-*
        if is_dir and name.startswith("fresh-start-"):
            return CleanupItem(
                category="fresh-start",
                path=name,
                size=size,
                mtime=mtime,
                is_dir=True,
                description=f"Historical fresh-start snapshot ({format_size(size)})",
            )

        # 4. Disabled mods: @<id> where id is disabled in mods.yaml
        if is_dir and name.startswith("@"):
            mod_id = name[1:]
            if mod_id in enabled_ids:
                return None  # Active mod: PROTECTED
            if mod_id in disabled_mods:
                mod_name = disabled_mods[mod_id]
                return CleanupItem(
                    category="disabled-mods",
                    path=name,
                    size=size,
                    mtime=mtime,
                    is_dir=True,
                    description=f"Pruned mod @{mod_id} ({mod_name})",
                )

    # Profiles checks
    if parent == "profiles":
        # 5. Crash dumps in profiles (*.mdmp)
        if not is_dir and lower.endswith(".mdmp"):
            return CleanupItem(
                category="crash-dumps",
                path=f"profiles/{name}",
                size=size,
                mtime=mtime,
                is_dir=False,
                description=f"DayZ engine crash dump ({format_size(size)})",
            )

        # 6. Ancient crash logs and RPT logs
        if not is_dir and (lower.startswith("crash_") or lower.endswith(".rpt")):
            age_days = (now - mtime) / 86400
            if age_days > log_days:
                return CleanupItem(
                    category="old-logs",
                    path=f"profiles/{name}",
                    size=size,
                    mtime=mtime,
                    is_dir=False,
                    description=f"Log file ({age_days:.1f} days old)",
                )

    return None


async def measure_dir_size(sftp, dir_path: str) -> tuple[int, int]:
    """Recursively calculate total bytes and file count of an SFTP directory."""
    total_bytes = 0
    file_count = 0

    async def _walk(path: str):
        nonlocal total_bytes, file_count
        try:
            entries = await sftp.readdir(path)
        except Exception:
            return
        for e in entries:
            if e.filename in (".", ".."):
                continue
            sub = f"{path}/{e.filename}"
            if e.attrs.permissions is not None and stat.S_ISDIR(e.attrs.permissions):
                await _walk(sub)
            else:
                total_bytes += e.attrs.size or 0
                file_count += 1

    await _walk(dir_path)
    return total_bytes, file_count


async def sftp_rmtree(sftp, dir_path: str) -> tuple[int, int]:
    """Recursively delete all contents of an SFTP directory and the directory itself."""
    deleted_files = 0
    deleted_bytes = 0

    async def _walk_delete(path: str):
        nonlocal deleted_files, deleted_bytes
        try:
            entries = await sftp.readdir(path)
        except Exception:
            return
        for e in entries:
            if e.filename in (".", ".."):
                continue
            sub = f"{path}/{e.filename}"
            if e.attrs.permissions is not None and stat.S_ISDIR(e.attrs.permissions):
                await _walk_delete(sub)
            else:
                sz = e.attrs.size or 0
                await sftp.remove(sub)
                deleted_files += 1
                deleted_bytes += sz
        await sftp.rmdir(path)

    await _walk_delete(dir_path)
    return deleted_files, deleted_bytes


async def scan_and_clean(
    apply: bool = False,
    categories: set[str] | None = None,
    log_days: int = 7,
) -> dict[str, list[CleanupItem]]:
    import asyncssh

    env = os.environ
    host = env["SFTP_HOST"]
    port = int(env.get("SFTP_PORT", 22))
    user = env["SFTP_USER"]
    password = env["SFTP_PASSWORD"]
    remote_root = (env.get("SFTP_REMOTE_ROOT") or "/").rstrip("/")

    mods = load_mods()
    enabled_ids = {str(m["id"]) for m in mods if m.get("enabled", True) and "id" in m}
    disabled_mods = {
        str(m["id"]): m.get("name", str(m["id"]))
        for m in mods
        if not m.get("enabled", True) and "id" in m
    }

    selected_categories = categories or {"cores", "stale", "fresh-start", "disabled-mods", "crash-dumps"}

    items_by_cat: dict[str, list[CleanupItem]] = {cat: [] for cat in selected_categories}
    now_ts = time.time()

    async with asyncssh.connect(
        host, port=port, username=user, password=password, known_hosts=None
    ) as conn:
        async with conn.start_sftp_client() as sftp:
            root_path = remote_root if remote_root else "/"
            root_entries = await sftp.readdir(root_path)

            # Classify root items
            for e in root_entries:
                if e.filename in (".", ".."):
                    continue
                is_dir = e.attrs.permissions is not None and stat.S_ISDIR(e.attrs.permissions)
                item = classify_entry(
                    name=e.filename,
                    size=e.attrs.size or 0,
                    mtime=float(e.attrs.mtime or 0),
                    is_dir=is_dir,
                    enabled_ids=enabled_ids,
                    disabled_mods=disabled_mods,
                    now_ts=now_ts,
                    log_days=log_days,
                )
                if item and item.category in selected_categories:
                    items_by_cat[item.category].append(item)

            # Classify profiles items if needed
            if "crash-dumps" in selected_categories or "old-logs" in selected_categories:
                prof_path = f"{remote_root}/profiles" if remote_root else "profiles"
                try:
                    prof_entries = await sftp.readdir(prof_path)
                    for pe in prof_entries:
                        if pe.filename in (".", ".."):
                            continue
                        is_dir = pe.attrs.permissions is not None and stat.S_ISDIR(pe.attrs.permissions)
                        item = classify_entry(
                            name=pe.filename,
                            size=pe.attrs.size or 0,
                            mtime=float(pe.attrs.mtime or 0),
                            is_dir=is_dir,
                            enabled_ids=enabled_ids,
                            disabled_mods=disabled_mods,
                            now_ts=now_ts,
                            log_days=log_days,
                            parent="profiles",
                        )
                        if item and item.category in selected_categories:
                            items_by_cat[item.category].append(item)
                except Exception as err:
                    print(f"Warning: could not read profiles directory: {err}", file=sys.stderr)

            # For directory items, measure recursive sizes concurrently
            dir_items = [
                it for cat, items in items_by_cat.items()
                for it in items
                if it.is_dir and it.size <= 4096
            ]
            if dir_items:
                sem = asyncio.Semaphore(8)

                async def _measure_one(it: CleanupItem):
                    async with sem:
                        dir_full = f"{remote_root}/{it.path}" if remote_root else it.path
                        sz, _ = await measure_dir_size(sftp, dir_full)
                        it.size = sz

                await asyncio.gather(*(_measure_one(it) for it in dir_items))

            # Display plan
            print(f"=== SERVER DISK SPACE CLEANUP ({'APPLY' if apply else 'DRY RUN'}) ===")
            grand_total_bytes = 0
            for cat in sorted(items_by_cat.keys()):
                items = items_by_cat[cat]
                cat_bytes = sum(it.size for it in items)
                grand_total_bytes += cat_bytes
                print(f"\n[{cat.upper()}] {len(items)} items — {format_size(cat_bytes)}:")
                for it in sorted(items, key=lambda x: x.size, reverse=True):
                    t_str = dt.datetime.fromtimestamp(it.mtime).strftime("%Y-%m-%d %H:%M")
                    print(f"  {'[DIR] ' if it.is_dir else '      '}{it.path:<38} {format_size(it.size):>10}  ({t_str})")

            print(f"\nTotal reclaimable across selected categories: {format_size(grand_total_bytes)}")

            if not apply:
                print("\n[DRY RUN] No files or directories were deleted. Pass --apply to execute.")
                return items_by_cat

            # Execute deletion
            print("\n>> Executing deletion over SFTP...")
            freed_bytes = 0
            freed_files = 0
            freed_dirs = 0

            for cat in sorted(items_by_cat.keys()):
                items = items_by_cat[cat]
                for it in items:
                    target_path = f"{remote_root}/{it.path}" if remote_root else it.path
                    if it.is_dir:
                        print(f"Deleting directory: {it.path}...")
                        fc, bc = await sftp_rmtree(sftp, target_path)
                        freed_files += fc
                        freed_dirs += 1
                        freed_bytes += it.size
                    else:
                        print(f"Deleting file: {it.path}...")
                        await sftp.remove(target_path)
                        freed_files += 1
                        freed_bytes += it.size

            print(f"\n>> SUCCESS: Deleted {freed_files} files and {freed_dirs} directories.")
            print(f">> Freed: {format_size(freed_bytes)} of disk space on the server.")

    return items_by_cat


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--apply", action="store_true", help="Actually delete selected items (default: dry run)")
    parser.add_argument("--cores", action="store_true", help="Delete Linux core.<pid> dumps at root")
    parser.add_argument("--stale", action="store_true", help="Delete stale-<id>-<date> directories at root")
    parser.add_argument("--fresh-start", action="store_true", help="Delete fresh-start-* snapshots at root")
    parser.add_argument("--disabled-mods", action="store_true", help="Delete disabled mod folders /@<id> at root")
    parser.add_argument("--crash-dumps", action="store_true", help="Delete DayZServer_*.mdmp files in profiles/")
    parser.add_argument("--old-logs", action="store_true", help="Delete crash_*.log and *.RPT older than --days")
    parser.add_argument("--days", type=int, default=7, help="Log age threshold in days for --old-logs (default: 7)")
    parser.add_argument(
        "--all-safe",
        action="store_true",
        help="Select cores, stale, fresh-start, disabled-mods, and crash-dumps",
    )

    args = parser.parse_args()

    # Load credentials from .env if needed
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=ROOT / ".env")

    if not os.environ.get("SFTP_HOST"):
        print("SFTP_HOST is not set. Ensure .env exists with SFTP credentials.", file=sys.stderr)
        return 2

    selected = set()
    if args.all_safe:
        selected.update(["cores", "stale", "fresh-start", "disabled-mods", "crash-dumps"])
    if args.cores:
        selected.add("cores")
    if args.stale:
        selected.add("stale")
    if args.fresh_start:
        selected.add("fresh-start")
    if args.disabled_mods:
        selected.add("disabled-mods")
    if args.crash_dumps:
        selected.add("crash-dumps")
    if args.old_logs:
        selected.add("old-logs")

    if not selected:
        # Default dry run displays all categories including old-logs
        selected = {"cores", "stale", "fresh-start", "disabled-mods", "crash-dumps", "old-logs"}

    asyncio.run(scan_and_clean(apply=args.apply, categories=selected, log_days=args.days))
    return 0


if __name__ == "__main__":
    sys.exit(main())
