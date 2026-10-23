import json
import socket
import threading

import pytest

import reset_respawns as rr


LEDGER = {"Players": [
    {"Id": "a=", "FirstSeen": 100, "LastVehicle": 5000, "LastNavKit": 5000, "Lives": 3,
     "DeathX": 1.0, "DeathZ": 2.0, "HasDeath": 1},
    {"Id": "b=", "FirstSeen": 200, "LastVehicle": 0, "LastNavKit": 7000, "Lives": 1,
     "DeathX": 0.0, "DeathZ": 0.0, "HasDeath": 0},
]}


def test_reset_clears_timers_and_death_but_keeps_the_player_known():
    out, n = rr.reset_ledger(json.loads(json.dumps(LEDGER)))
    assert n == 2
    for p in out["Players"]:
        assert p["LastVehicle"] == 0 and p["LastNavKit"] == 0 and p["HasDeath"] == 0
    # Kept: a known player respawns on a road rather than at the first-arrival column.
    assert [(p["Id"], p["FirstSeen"], p["Lives"]) for p in out["Players"]] == [("a=", 100, 3), ("b=", 200, 1)]


def test_reset_tolerates_an_empty_or_missing_ledger():
    assert rr.reset_ledger({}) == ({"Players": []}, 0)
    assert rr.reset_ledger({"Players": None}) == ({"Players": []}, 0)


def _udp_responder(reply: bytes | None):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    sock.settimeout(2)

    def serve():
        try:
            _, addr = sock.recvfrom(1400)
            if reply is not None:
                sock.sendto(reply, addr)
        except OSError:
            pass
    threading.Thread(target=serve, daemon=True).start()
    return sock


@pytest.mark.parametrize("reply", [b"\xff\xff\xff\xffI\x11Ad Aspera\x00", b"\xff\xff\xff\xffA\x01\x02\x03\x04"])
def test_server_is_up_on_any_a2s_reply(reply):
    """An info reply (I) or a challenge (A) both mean a live server."""
    sock = _udp_responder(reply)
    assert rr.server_is_up("127.0.0.1", sock.getsockname()[1], timeout=1.0) is True
    sock.close()


def test_server_is_down_when_nothing_answers():
    sock = _udp_responder(None)
    assert rr.server_is_up("127.0.0.1", sock.getsockname()[1], timeout=0.5) is False
    sock.close()


def test_refuses_to_touch_files_while_the_server_is_up(monkeypatch, capsys):
    monkeypatch.setenv("RCON_HOST", "127.0.0.1")
    monkeypatch.setattr(rr, "server_is_up", lambda *a, **k: True)
    monkeypatch.setattr(rr, "apply", lambda *a, **k: pytest.fail("touched the server while it was up"))
    assert rr.main(["--yes"]) == 1
    assert "stop the server" in capsys.readouterr().out.lower()


def test_remote_paths_follow_the_active_mission(monkeypatch):
    monkeypatch.setenv("SFTP_REMOTE_ROOT", "/")
    ledger, players = rr.remote_paths()
    assert ledger == "/profiles/DZDS/arrivals_ledger.json"
    assert players.startswith("/mpmissions/dayzOffline.") and players.endswith("/storage_1/players.db")


def test_reset_one_player_leaves_everyone_else_alone():
    out, n = rr.reset_ledger(json.loads(json.dumps(LEDGER)), only="a=")
    assert n == 1
    a, b = out["Players"]
    assert a["LastVehicle"] == 0 and a["LastNavKit"] == 0 and a["HasDeath"] == 0
    assert b == LEDGER["Players"][1]


def test_drop_character_removes_only_that_uid(tmp_path):
    import sqlite3
    db = tmp_path / "players.db"
    with sqlite3.connect(db) as c:
        c.execute('CREATE TABLE "Players" (Id INTEGER PRIMARY KEY NOT NULL, Alive INTEGER NOT NULL, '
                  'UID CHAR(64) UNIQUE NOT NULL, Data BLOB NULL)')
        c.executemany("INSERT INTO Players (Alive, UID, Data) VALUES (?, ?, ?)",
                      [(1, "a=", b"x"), (0, "b=", b"y")])
    assert rr.drop_character(db, "a=") == 1
    assert rr.drop_character(db, "a=") == 0
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT UID FROM Players").fetchall() == [("b=",)]


def test_player_resolves_a_favored_name_to_its_id():
    assert rr.resolve_player("Blae") == "eEbDg86Qv3w5T_ZJj-9b9BriMPuvigsufukc_oCLOAQ="
    assert rr.resolve_player("someid=") == "someid="


def test_live_request_matches_init_c():
    """--live writes the file init.c's ApplyLiveResets reads (class RefugeeArrivalReset)."""
    assert rr.live_request(["abc="]) == {"Ids": ["abc="]}
    src = (rr.ROOT / "server" / "mpmissions" / "dayzOffline.nasdara" / "init.c").read_text()
    assert "class RefugeeArrivalReset" in src and "ref TStringArray Ids;" in src
    assert 'RESET = DIR + "\\\\reset_cooldowns.json"' in src
    assert "ApplyLiveResets();" in src and "DeleteFile(RESET);" in src
