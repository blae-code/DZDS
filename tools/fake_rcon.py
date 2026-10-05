#!/usr/bin/env python3
"""Fake BattlEye RCON server for developing the GM without a real server.

Accepts the configured password, answers commands, and prints every `say` broadcast
so you can see what players would read in-game.

Usage: tools/fake_rcon.py [--port 2310] [--password changeme]
Then run the GM with RCON_HOST=127.0.0.1 GM_DRY_RUN=0.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from gamemaster.rcon import COMMAND, LOGIN, build_packet, parse_packet  # noqa: E402


class FakeBE(asyncio.DatagramProtocol):
    def __init__(self, password: str, quiet: bool = False) -> None:
        self.password, self.quiet = password, quiet
        self.authed: set = set()
        self.received: list[str] = []

    def connection_made(self, transport) -> None:  # noqa: ANN001
        self.transport = transport

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        parsed = parse_packet(data)
        if not parsed:
            return
        ptype, body = parsed
        if ptype == LOGIN:
            ok = body.decode("utf-8", "replace") == self.password
            if ok:
                self.authed.add(addr)
            self._log(f"[login] {addr[0]}:{addr[1]} {'OK' if ok else 'REJECTED'}")
            self.transport.sendto(build_packet(LOGIN, b"\x01" if ok else b"\x00"), addr)
        elif ptype == COMMAND and addr in self.authed and body:
            seq, cmd = body[0], body[1:].decode("utf-8", "replace")
            if cmd:
                self.received.append(cmd)
                if cmd.startswith("say -1 "):
                    self._log(f"\033[1;33m[RADIO]\033[0m {cmd[7:]}")
                else:
                    self._log(f"[cmd] {cmd}")
            reply = "Players on server:\n(0 players in total)" if cmd == "players" else ""
            self.transport.sendto(build_packet(COMMAND, bytes([seq]) + reply.encode()), addr)

    def _log(self, msg: str) -> None:
        if not self.quiet:
            print(msg, flush=True)


async def serve(host: str, port: int, password: str, quiet: bool = False):
    loop = asyncio.get_running_loop()
    return await loop.create_datagram_endpoint(lambda: FakeBE(password, quiet), local_addr=(host, port))


async def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=2310)
    p.add_argument("--password", default="changeme")
    a = p.parse_args()
    await serve(a.host, a.port, a.password)
    print(f"Fake BattlEye RCON listening on {a.host}:{a.port} (password '{a.password}')")
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
