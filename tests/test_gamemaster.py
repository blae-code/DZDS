import asyncio

import pytest

from gamemaster.adm import HealthTracker, parse_line
from gamemaster.gm_orchestrator import EventAggregator
from gamemaster.llm import extract_json, strip_thoughts
from gamemaster.rcon import COMMAND, LOGIN, RconClient, build_packet, parse_packet
from gamemaster.schema import GMPayload, WorldAction, resolve_coords


# ---- RCON ----
def test_packet_roundtrip():
    pkt = build_packet(COMMAND, b"\x05players")
    assert pkt[:2] == b"BE"
    assert parse_packet(pkt) == (COMMAND, b"\x05players")


def test_bad_crc_rejected():
    pkt = bytearray(build_packet(LOGIN, b"pw"))
    pkt[-1] ^= 0xFF
    assert parse_packet(bytes(pkt)) is None


async def test_multipart_response_reassembled():
    c = RconClient("127.0.0.1", 2310, "pw")
    fut = asyncio.get_running_loop().create_future()
    c._pending[7] = fut
    c._on_packet(build_packet(COMMAND, bytes([7, 0, 2, 1]) + b"world"))
    assert not fut.done()
    c._on_packet(build_packet(COMMAND, bytes([7, 0, 2, 0]) + b"hello "))
    assert fut.result() == "hello world"


# ---- ADM ----
HIT = ('14:02:11 | Player "Bob" (id=abc= pos=<6712.3, 301.2, 2510.9>)[HP: 42.5] '
       'hit by Infected into Torso(12) for 10.1 damage (MeleeInfected)')


def test_parse_hit():
    ev = parse_line(HIT)
    assert ev.kind == "hit" and ev.player == "Bob" and ev.hp == 42.5
    assert ev.pos == (6712.3, 2510.9)
    assert "infected" in ev.tags


def test_parse_connect():
    ev = parse_line('10:00:00 | Player "Alice" is connected (id=xyz=)')
    assert ev.kind == "connect" and ev.player == "Alice"


def test_health_tracker():
    h = HealthTracker(threshold=40, window=120)
    assert not h.observe("Bob", 100, now=0)
    assert not h.observe("Bob", 80, now=10)
    assert h.observe("Bob", 55, now=20)


def test_aggregator_digest():
    agg = EventAggregator()
    assert agg.ingest(parse_line('10:00:00 | Player "Bob" is connected (id=x=)'))
    agg.ingest(parse_line(HIT))
    d = agg.digest({"Chernogorsk": [6700, 2500], "Berezino": [12300, 9500]})
    assert "Bob" in d and "near Chernogorsk" in d


# ---- LLM output handling ----
def test_strip_thoughts_and_extract():
    raw = '<|channel>thought I should drop a crate<channel|>```json\n{"narrative_broadcast": "hi"}\n```'
    assert "thought" not in strip_thoughts(raw)
    assert extract_json(raw) == {"narrative_broadcast": "hi"}


def test_payload_sanitised():
    p = GMPayload.model_validate({
        "narrative_broadcast": "line1\nline2 " + "x" * 500,
        "world_actions": [
            {"type": "trigger_event", "target": "spawn_airdrop", "coords": [4512, 10240]},
            {"type": "trigger_event", "target": "delete_all_bases"},
        ],
    })
    assert "\n" not in p.narrative_broadcast and len(p.narrative_broadcast) <= 200
    assert [a.target for a in p.world_actions] == ["spawn_airdrop"]


def test_resolve_coords_prefers_location_and_clamps():
    locs = {"Berezino": [12300, 9500]}
    b = (0, 0, 15360, 15360)
    assert resolve_coords(WorldAction(target="spawn_airdrop", location="Berezino",
                                      coords=(1, 1)), locs, b) == (12300, 9500)
    assert resolve_coords(WorldAction(target="spawn_airdrop", coords=(-50, 99999)),
                          locs, b) == (0, 15360)


@pytest.mark.parametrize("delay", [-1, 5000])
def test_delay_bounds(delay):
    with pytest.raises(Exception):
        WorldAction(target="spawn_airdrop", delay_seconds=delay)


# ---- Expansion AI faction lines (LogAIHitBy / LogAIKilled) ----
AI_KILL = ('14:10:02 | AI "Sgt Volkov" (DEAD) (group=12:"East Garrison" faction="East" '
           'pos=<9512.0, 300.0, 8890.0>) killed by AI "Pvt Hale" (group=7:"West Patrol" '
           'faction="West" pos=<9480.0, 301.0, 8850.0>) with M4A1 from 52.3 meters')
PLAYER_KILLS_AI = ('14:11:00 | AI "Raider" (DEAD) (group=3:"Bandits" faction="Raiders" '
                   'pos=<6100.0, 300.0, 7700.0>) killed by Player "Host" (id=abc= pos=<6090.0, 300.0, 7690.0>) with SKS')
AI_HITS_PLAYER = ('14:12:00 | Player "Host" (id=abc= pos=<6100.0, 300.0, 7700.0>)[HP: 70] hit by AI "Raider" '
                  '(group=3:"Bandits" faction="Raiders" pos=<6150.0, 300.0, 7720.0>) into Torso(12) for 20 damage')


def test_parse_ai_faction_kill():
    ev = parse_line(AI_KILL)
    assert ev.kind == "death" and ev.is_ai and ev.player == "Sgt Volkov"
    assert (ev.faction, ev.by_faction, ev.by_is_ai) == ("East", "West", True)
    assert {"ai_combat", "faction_combat"} <= ev.tags
    assert ev.pos == (9512.0, 8890.0)


def test_parse_ai_hits_player():
    ev = parse_line(AI_HITS_PLAYER)
    assert ev.kind == "hit" and not ev.is_ai and ev.hp == 70
    assert ev.by_is_ai and ev.by_faction == "Raiders" and "ai_combat" in ev.tags


def test_digest_tallies_faction_fighting():
    agg = EventAggregator()
    for line in (AI_KILL, AI_KILL, PLAYER_KILLS_AI):
        assert agg.ingest(parse_line(line)) is False
    d = agg.digest({"Gorka": [9500, 8900], "Stary Sobor": [6100, 7700]})
    assert "West killed 2 East near Gorka" in d
    assert "Players killed 1 Raiders near Stary Sobor" in d
    assert not agg.faction_kills  # reset after digest


def test_digest_uses_our_faction_names():
    agg = EventAggregator(faction_names={"West": "The Jackal Cohort", "East": "Karkas Mountain Clan"})
    agg.ingest(parse_line(AI_KILL))
    assert "The Jackal Cohort killed 1 Karkas Mountain Clan near Gorka" in agg.digest({"Gorka": [9500, 8900]})


def test_load_config_maps_custom_and_interim_factions():
    from gamemaster.gm_orchestrator import load_config
    names = load_config()["faction_names"]
    assert names["DZDSJackals"] == names["Raiders"] == "The Jackal Cohort"
    assert names["DZDSKarkas"] == names["Shamans"] == "Karkas Mountain Clan"
    assert names["DZDSPeacekeepers"] == names["Guards"] == "UN Peacekeeping Remnants"
    assert names["DZDSSettlers"] == "Frontier Settlers"


def test_system_prompt_includes_faction_voices():
    from gamemaster.gm_orchestrator import load_config
    from gamemaster.llm import OllamaGM
    cfg = load_config()
    assert set(cfg["faction_voices"]) >= {"The Jackal Cohort", "Karkas Mountain Clan", "The Rust Syndicate"}
    gm = OllamaGM("http://x", "m", voices=cfg["faction_voices"])
    assert "feed the crows" in gm.system_prompt and "Blue Shield" in gm.system_prompt
