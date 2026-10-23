#!/usr/bin/env python3
"""Launch the Ad Aspera · DZDS Web Tactical Command Center.

Usage:
  tools/dashboard.py [--host 127.0.0.1] [--port 8787] [--open]
"""
from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from gamemaster.web import serve  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--open", action="store_true", help="open dashboard in the default browser")
    args = ap.parse_args(argv)
    if args.open:
        webbrowser.open(f"http://{args.host}:{args.port}")
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
