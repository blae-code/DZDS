"""Offline dev loop: simulator output parses, and the RCON client talks to the fake server."""
import random

import yaml

import adm_simulator
import fake_rcon
from gamemaster.adm import parse_line
from gamemaster.gm_orchestrator import ROOT, EventAggregator
from gamemaster.rcon import RconClient


def test_simulator_lines_parse():
    locs = yaml.safe_load((ROOT / "maps" / "chernarusplus.yaml").read_text())["locations"]
    sim = adm_simulator.Sim(["Host", "Buddy"], locs, random.Random(3))
    agg, kinds, triggers = EventAggregator(), set(), 0
    for _ in range(400):
        for line in sim.step():
            ev = parse_line(f"12:00:00 | {line}")
            assert ev is not None, line
            kinds.add(ev.kind)
            triggers += agg.ingest(ev)
    assert {"connect", "hit", "position"} <= kinds
    assert triggers > 0
    assert agg.faction_kills, "simulator should produce AI faction kills"


async def test_rcon_against_fake_server():
    transport, proto = await fake_rcon.serve("127.0.0.1", 0, "pw", quiet=True)
    port = transport.get_extra_info("sockname")[1]
    client = RconClient("127.0.0.1", port, "pw")
    try:
        await client.connect(timeout=2)
        await client.say_all("Static crackles...")
        assert "players" in (await client.command("players")).lower()
        assert proto.received == ["say -1 Static crackles...", "players"]
    finally:
        client.close()
        transport.close()


async def test_rcon_bad_password():
    transport, _ = await fake_rcon.serve("127.0.0.1", 0, "pw", quiet=True)
    port = transport.get_extra_info("sockname")[1]
    client = RconClient("127.0.0.1", port, "wrong")
    try:
        try:
            await client.connect(timeout=2)
            raise AssertionError("login should fail")
        except PermissionError:
            pass
    finally:
        transport.close()


async def test_local_tailer_follows_newest_in_dir(tmp_path):
    import asyncio
    import os

    from gamemaster.adm import LocalAdmTailer

    first = tmp_path / "DayZServer_x64_2026_10_05_120000.ADM"
    first.write_text("old line\n")
    gen = LocalAdmTailer(str(tmp_path), from_start=True, poll_seconds=0.01).lines()
    assert await asyncio.wait_for(gen.__anext__(), 1) == "old line"
    second = tmp_path / "DayZServer_x64_2026_10_05_160000.ADM"
    second.write_text("new line\n")
    os.utime(second, (first.stat().st_mtime + 10,) * 2)
    assert await asyncio.wait_for(gen.__anext__(), 1) == "new line"
    await gen.aclose()
