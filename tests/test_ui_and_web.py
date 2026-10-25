"""Tests for the Ad Aspera · DZDS UI surfaces: CLI design system, Status, TUI, and Web Command Center."""
from __future__ import annotations

import json
import pytest
import threading
import urllib.request

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


def test_dashboard_map_controls_use_progressive_disclosure():
    html = web.UI_HTML_PATH.read_text()
    assert 'id="locations-panel" aria-labelledby="locations-panel-title" hidden' in html
    assert 'id="dossier-panel" aria-labelledby="dossier-panel-title" hidden' in html
    assert 'aria-expanded="false" aria-controls="locations-panel"' in html
    assert 'aria-expanded="false" aria-controls="dossier-panel"' in html
    assert '<details class="layers-menu">' in html
    assert 'aria-pressed="true" onclick="toggleLayer(\'zones\')"' in html
    assert "function setMapPanel(panelName, open)" in html
    assert "if (e.key === 'Escape')" in html
    assert '<h1>War ledger</h1>' in html
    assert '<h1>Campaign</h1>' in html
    assert '<h1>Mod loadout</h1>' in html
    assert '<h1>Game Master</h1>' in html


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
    srv = web.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/")
        resp = conn.getresponse()
        html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "AD ASPERA · DZDS Tactical Command Center" in html

        conn.request("GET", "/portal")
        portal_resp = conn.getresponse()
        portal_html = portal_resp.read().decode("utf-8")
        assert portal_resp.status == 200
        assert portal_resp.getheader("Content-Type") == "text/html; charset=utf-8"
        assert "Ad Aspera | Survivor's Guide" in portal_html
        assert "23.229.49.100:26092" in portal_html
        assert "87.8 MHz" in portal_html
        assert "06:00 US Central" in portal_html
        assert "/api/" not in portal_html
        assert "simulateTurn" not in portal_html
        assert "<script" not in portal_html

        conn.request("GET", "/api/state?map=nasdara")
        resp2 = conn.getresponse()
        payload = json.loads(resp2.read().decode("utf-8"))
        assert resp2.status == 200
        assert payload["active_map"] == "nasdara"
        conn.close()

        conn.request("GET", "/portal/")
        portal_slash_resp = conn.getresponse()
        assert portal_slash_resp.status == 200
        portal_slash_resp.read()
    finally:
        srv.shutdown()
        srv.server_close()


def test_refactored_yaml_cache_and_load_or_new_cross_map(tmp_path):
    """active.load_yaml returns mutation-safe copies and WarLedger.load_or_new falls back across maps."""
    import active

    d1 = active.load_yaml("presets/traders.yaml")
    d1["traders"].clear()
    d2 = active.load_yaml("presets/traders.yaml")
    assert d2["traders"], "mutating a cached YAML result must not pollute subsequent loads"

    fake_ledger = tmp_path / "war_ledger.json"
    fake_ledger.write_text(json.dumps({"map": "chernarusplus", "turn": 7}))
    led_match = WarLedger.load_or_new("chernarusplus", path=fake_ledger)
    assert led_match.s.turn == 7
    led_fallback = WarLedger.load_or_new("nasdara", path=fake_ledger)
    assert led_fallback.s.map == "nasdara" and led_fallback.s.turn == 0
    led_initial = WarLedger.load_or_new("chernarusplus", path=fake_ledger, initial=True)
    assert led_initial.s.turn == 0


def test_web_rejects_foreign_hosts_origins_and_tokenless_posts():
    import http.client
    import dashboard
    srv = web.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()

    def req(method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request(method, path, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        conn.close()
        return r.status, data

    try:
        # DNS rebinding: a foreign Host never gets state.
        assert req("GET", "/api/state", {"Host": "evil.example:%d" % port})[0] == 403
        assert req("GET", "/api/state", {"Origin": "http://evil.example"})[0] == 403
        body = json.dumps({"map": "nasdara", "commit": False})
        json_ct = {"Content-Type": "application/json"}
        # CSRF: a simple cross-site POST (text/plain) or one without the token is refused.
        assert req("POST", "/api/simulate-turn", {"Content-Type": "text/plain"}, body)[0] == 415
        assert req("POST", "/api/simulate-turn", json_ct, body)[0] == 403
        ok = {**json_ct, web.TOKEN_HEADER: srv.dzds_token}
        assert req("POST", "/api/simulate-turn", ok, body)[0] == 200
        # The page embeds the launch token for its own fetches.
        status, html = req("GET", "/")
        assert status == 200 and srv.dzds_token.encode() in html and b"__DZDS_TOKEN__" not in html
    finally:
        srv.shutdown()
        srv.server_close()
    with pytest.raises(ValueError):
        web.make_server("0.0.0.0", 0)
    assert dashboard.main(["--host", "0.0.0.0"]) == 2
