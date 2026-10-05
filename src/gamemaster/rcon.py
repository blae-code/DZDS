"""Minimal async BattlEye RCON (protocol v2) client over UDP.

Packet: b"BE" + crc32(payload) LE + payload, where payload = 0xFF + type + body.
  type 0x00 login   -> body: password            reply body: 0x01 ok / 0x00 fail
  type 0x01 command -> body: seq + command       reply body: seq [+ 0x00 total idx] + data
  type 0x02 message <- body: seq + text          must ack with 0xFF 0x02 seq
An empty command every <45 s keeps the session alive.
"""
from __future__ import annotations

import asyncio
import logging
import struct
import zlib

log = logging.getLogger(__name__)

LOGIN, COMMAND, MESSAGE = 0x00, 0x01, 0x02
KEEPALIVE_SECONDS = 30


def build_packet(ptype: int, body: bytes) -> bytes:
    payload = bytes([0xFF, ptype]) + body
    return b"BE" + struct.pack("<I", zlib.crc32(payload) & 0xFFFFFFFF) + payload


def parse_packet(data: bytes) -> tuple[int, bytes] | None:
    """Return (type, body) or None if malformed / bad checksum."""
    if len(data) < 8 or data[:2] != b"BE" or data[6] != 0xFF:
        return None
    (crc,) = struct.unpack("<I", data[2:6])
    if zlib.crc32(data[6:]) & 0xFFFFFFFF != crc:
        return None
    return data[7], data[8:]


class _Proto(asyncio.DatagramProtocol):
    def __init__(self, client: "RconClient") -> None:
        self.client = client

    def datagram_received(self, data: bytes, addr) -> None:  # noqa: ANN001
        self.client._on_packet(data)

    def error_received(self, exc: Exception) -> None:
        log.warning("RCON socket error: %s", exc)


class RconClient:
    def __init__(self, host: str, port: int, password: str, on_message=None) -> None:
        self.host, self.port, self.password = host, port, password
        self.on_message = on_message  # callable(str) for server chat/log messages
        self._transport: asyncio.DatagramTransport | None = None
        self._seq = 0
        self._login: asyncio.Future | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._parts: dict[int, dict[int, bytes]] = {}
        self._keepalive: asyncio.Task | None = None

    async def connect(self, timeout: float = 5.0) -> None:
        loop = asyncio.get_running_loop()
        self._transport, _ = await loop.create_datagram_endpoint(
            lambda: _Proto(self), remote_addr=(self.host, self.port))
        self._login = loop.create_future()
        self._transport.sendto(build_packet(LOGIN, self.password.encode()))
        ok = await asyncio.wait_for(self._login, timeout)
        if not ok:
            self.close()
            raise PermissionError("RCON login rejected (check RCON_PASSWORD)")
        self._keepalive = asyncio.create_task(self._keepalive_loop())
        log.info("RCON connected to %s:%s", self.host, self.port)

    def close(self) -> None:
        if self._keepalive:
            self._keepalive.cancel()
        if self._transport:
            self._transport.close()
        self._transport = None

    async def command(self, cmd: str, timeout: float = 5.0) -> str:
        if not self._transport:
            raise ConnectionError("RCON not connected")
        seq = self._seq
        self._seq = (self._seq + 1) % 256
        fut = asyncio.get_running_loop().create_future()
        self._pending[seq] = fut
        self._transport.sendto(build_packet(COMMAND, bytes([seq]) + cmd.encode("utf-8")))
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._pending.pop(seq, None)

    async def say_all(self, text: str) -> str:
        return await self.command(f"say -1 {text}")

    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(KEEPALIVE_SECONDS)
            try:
                await self.command("")
            except Exception as exc:  # noqa: BLE001
                log.warning("RCON keepalive failed: %s", exc)

    def _on_packet(self, data: bytes) -> None:
        parsed = parse_packet(data)
        if not parsed:
            return
        ptype, body = parsed
        if ptype == LOGIN and self._login and not self._login.done():
            self._login.set_result(body[:1] == b"\x01")
        elif ptype == COMMAND and body:
            seq, rest = body[0], body[1:]
            if rest[:1] == b"\x00" and len(rest) >= 3:  # multi-packet response
                total, idx = rest[1], rest[2]
                parts = self._parts.setdefault(seq, {})
                parts[idx] = rest[3:]
                if len(parts) < total:
                    return
                rest = b"".join(parts[i] for i in range(total))
                del self._parts[seq]
            fut = self._pending.get(seq)
            if fut and not fut.done():
                fut.set_result(rest.decode("utf-8", "replace"))
        elif ptype == MESSAGE and body:
            if self._transport:
                self._transport.sendto(build_packet(MESSAGE, body[:1]))
            if self.on_message:
                self.on_message(body[1:].decode("utf-8", "replace"))
