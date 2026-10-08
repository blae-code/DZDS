#!/usr/bin/env python3
"""Pack a mod source folder into an uncompressed PBO (what DayZ Tools' Addon Builder does with
-packonly). Addon Builder hangs at a first-run window under Proton, so we pack on Linux and sign
with DSSignFile.exe (scripts/build_dzds.sh).

PBO layout: a "Vers" header entry carrying extensions (prefix), one entry per file
(name, method 0, sizes), an empty terminator entry, the file data in entry order, then a zero
byte and the SHA-1 of everything before it. Files are sorted and timestamps zeroed so the
output is deterministic.

Usage: tools/pack_pbo.py <source dir> <out.pbo> --prefix DZDS
"""
from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

SKIP_SUFFIXES = (".bak", ".tmp", ".orig")


def entry(name: str, method: int = 0, size: int = 0) -> bytes:
    return name.encode() + b"\0" + struct.pack("<5I", method, 0, 0, 0, size)


def pack(src: Path, out: Path, prefix: str) -> list[str]:
    files = sorted(
        p for p in src.rglob("*")
        if p.is_file() and not any(part.startswith(".") for part in p.relative_to(src).parts)
        and not p.name.endswith(SKIP_SUFFIXES)
    )
    names = [str(p.relative_to(src)).replace("/", "\\") for p in files]
    blobs = [p.read_bytes() for p in files]
    body = entry("", method=0x56657273) + b"prefix\0" + prefix.encode() + b"\0" + b"\0"
    for name, blob in zip(names, blobs):
        body += entry(name, size=len(blob))
    body += entry("")
    body += b"".join(blobs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(body + b"\0" + hashlib.sha1(body).digest())
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--prefix", required=True)
    a = ap.parse_args()
    for n in pack(a.src, a.out, a.prefix):
        print(f"  {n}")
    print(f"Packed {a.out} (prefix {a.prefix})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
