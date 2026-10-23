"""Tests for the Ad Aspera · DZDS UI surfaces: CLI design system, Status, TUI, and Web Command Center."""
from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import status as status_mod
import tui
import ui
import war
import yaml
from gamemaster import web
from gamemaster.ledger import WarLedger


def test_ui_ansi_stripping_and_alignment():
    styled = ui.fg("AD ASPERA", "coral", bold=True, enabled=True)
    assert "\x1b[1m\x1b[38;2;219;92;75m" in styled
    assert ui.strip_ansi(styled) == "AD ASPERA"
    assert ui.visible_len(styled) == 9
    padded = ui.pad(styled, 14, "right")
    assert ui.visible_len(padded) == 14


def test_ui_table_and_meters_render_cleanly():
    m = ui.meter(60, 100, width=10, color="Settlers", enabled=True)
    assert "60" in ui.strip_ansi(m)
    sb_pos = ui.standing_bar(50, width=10, enabled=True)
    sb_neg = ui.standing_bar(-40, width=10, enabled=True)
    assert "+50" in ui.strip_ansi(sb_pos)
    assert "-40" in ui.strip_ansi(sb_neg)
    tbl = ui.table(["FACTION", "STRENGTH"], [[ui.faction_tag("Settlers", enabled=True), m]],
                   title="TEST TABLE", enabled=True)
    lines = tbl.splitlines()
    widths = {ui.visible_len(ln) for ln in lines}
    assert len(widths) == 1, f"table rows have inconsistent visible widths: {widths}"


def test_braille_tactical_map_renders_locations_and_war_party():
    mp = yaml.safe_load((war. active.ROOT / "maps" / "nasdara.yaml").read_text())
    led = WarLedger.new("nasdara")
    led.s.war_party = {"kind": "offensive", "faction": "Rust",
                       "origin": "Cement Works", "target": "Southern Barracks", "size": [4, 6]}
    lines = ui.render_tactical_map(
        mp,
        led.s.control,
        war_party=led.s.war_party,
        active_column="East Roadside",
        selected_site="Settler Haven",
        width=54,
        height=18,
        enabled=False,
    )
    assert len(lines) == 18
    joined = "\n".join(lines)
    assert "[◆Settler]" in joined
    assert "◈" in joined


def test_status_overview_renders_both_maps_with_aligned_columns():
    for map_name in ("nasdara", "chernarusplus"):
        rendered = status_mod.render_overview(map_name, color=True)
        plain = ui.strip_ansi(rendered)
        assert f"TACTICAL SANDBOX STATUS · {map_name.upper()}" in plain
        assert "FACTION BALANCE & STANDING" in plain
        assert "TRADERS & LIVE QUESTS" in plain
        assert "READINESS & INTERFACES" in plain


def test_tui_all_five_tabs_and_actions():
    st = tui.TuiState("nasdara")
    for tab_idx in range(5):
        snap = tui.render_tab_snapshot(st, tab=tab_idx, color=True)
        plain = ui.strip_ansi(snap)
        assert "COMMAND DECK · NASDARA" in plain
        assert tui.TABS[tab_idx] in plain

    st.simulate_turn()
    assert st.led.s.turn >= 1
    old_kit = list(st.rolled_kit)
    st.roll_kit()
    assert st.rolled_kit and st.rolled_kit != old_kit
    st.toggle_map()
    assert st.map_name == "chernarusplus"
    assert "COMMAND DECK · CHERNARUSPLUS" in ui.strip_ansi(tui.render_tab_snapshot(st, tab=0, color=False))


def test_web_api_endpoints_and_live_http_roundtrip():
    web.STORE.reset_preview("nasdara")
    code, state = web.handle_api("GET", "/api/state", {"map": ["nasdara"]}, {})
    assert code == 200
    assert state["active_map"] == "nasdara"
    assert "Settlers" in state["factions"]
    assert state["map"]["locations"]["Settler Haven"]["holder"] == "Settlers"
    assert state["mods"]["enabled_count"] >= 60

    # Skirmish + Simulate Turn
    code, sk = web.handle_api("POST", "/api/skirmish", {},
                              {"map": "nasdara", "site": "North Highway Pileup", "victim": "Jackals", "kills": 9})
    assert code == 200
    assert sk["state"]["map"]["locations"]["North Highway Pileup"]["pressure"]["Settlers"] == 9

    code, sim = web.handle_api("POST", "/api/simulate-turn", {}, {"map": "nasdara", "commit": False})
    assert code == 200
    assert sim["state"]["ledger"]["turn"] >= 1
    assert sim["state"]["map"]["locations"]["North Highway Pileup"]["holder"] == "Settlers"

    # Claim site
    code, cl = web.handle_api("POST", "/api/claim", {},
                              {"map": "nasdara", "name": "Mesa Outpost", "x": 6500, "z": 8100, "commit": False})
    assert code == 200
    assert cl["state"]["map"]["locations"]["Mesa Outpost"]["holder"] == "Settlers"

    # Kit roll
    code, kit = web.handle_api("POST", "/api/roll-kit", {}, {"archetype": "bush_pilot"})
    assert code == 200
    assert kit["archetype"] == "bush_pilot" and kit["aircraft"] is True
    assert "FishingRod" in kit["items"] and "Hook" in kit["items"]

    # Reset preview back to disk state
    code, rst = web.handle_api("POST", "/api/reset-preview", {}, {"map": "nasdara"})
    assert code == 200
    assert "Mesa Outpost" not in rst["state"]["map"]["locations"]

    # HTTP Server socket test (direct HTTPConnection to bypass any proxy env vars)
    import http.client
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.DashboardHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "AD ASPERA · DZDS Tactical Command Center" in html

        conn.request("GET", "/api/state?map=nasdara")
        resp2 = conn.getresponse()
        payload = json.loads(resp2.read().decode("utf-8"))
        assert resp2.status == 200
        assert payload["active_map"] == "nasdara"
        conn.close()
    finally:
        srv.shutdown()
        srv.server_close()
