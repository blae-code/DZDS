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
        assert "basebuilding" in payload
        assert payload["basebuilding"]["server_rules"]["flag_radius_m"] == 60

        conn.request("GET", "/api/basebuilding")
        resp_bb = conn.getresponse()
        payload_bb = json.loads(resp_bb.read().decode("utf-8"))
        assert resp_bb.status == 200
        assert len(payload_bb["recipes"]) >= 25
        assert "rag_part_costs" in payload_bb
        conn.close()

        conn.request("GET", "/portal/")
        portal_slash_resp = conn.getresponse()
        assert portal_slash_resp.status == 200
        portal_slash_resp.read()
    finally:
        srv.shutdown()
        srv.server_close()


def test_basebuilding_guide_api_and_server_configs():
    """Verify /api/basebuilding returns complete, accurate data matching live server configs."""
    code, guide = web.handle_api("GET", "/api/basebuilding", {}, {})
    assert code == 200

    # 1. Server Rules
    rules = guide["server_rules"]
    assert rules["flag_radius_m"] == 60
    assert rules["unflagged_placed_hours"] == 24
    assert rules["flagged_placed_days"] == 7
    assert rules["flag_refresh_days"] == 40
    assert rules["rag_kit_planks"] == 4
    assert rules["rag_kit_nails"] == 10
    assert rules["rag_build_time_s"] == 8.0
    assert rules["rag_dismantle_time_s"] == 15.0
    assert rules["cabin_ruin_hammer"] is True
    assert rules["cabin_refund_materials"] is True
    assert rules["crop_spoilage_enabled"] is False
    assert rules["cookz_cheese_decay"] is False
    assert rules["cookz_sausage_decay"] is False

    # 2. 6-Stage Progression Arc
    prog = guide["progression"]
    assert len(prog) == 6
    assert [p["stage"] for p in prog] == [1, 2, 3, 4, 5, 6]
    assert any("Shelter" in p["title"] or "Camp" in p["title"] for p in prog)
    assert any("Cabin" in p["title"] for p in prog)
    assert any("Flag" in p["summary"] or "Respawn" in p["title"] for p in prog)

    # 3. Recipes catalog across all categories
    recipes = guide["recipes"]
    assert len(recipes) >= 25
    categories = {r["category"] for r in recipes}
    assert {"vanilla", "rag_modular", "cabin", "mmg_storage", "utility_tack", "camp"}.issubset(categories)

    # Check key specific recipes and material structures
    by_id = {r["id"]: r for r in recipes}
    assert "van_fence_wood" in by_id
    assert "van_gate_metal" in by_id
    assert "van_watchtower_3lvl" in by_id
    assert "van_territory_flag" in by_id
    assert "rag_hunting_cabin_full" in by_id
    assert "rag_bb_foundation" in by_id
    assert "rag_bb_gate_double" in by_id
    assert "mmg_supply_crate" in by_id
    assert "zen_car_workbench" in by_id
    assert "farming_betterharvest" in by_id
    assert "cookz_kitchen" in by_id

    # RaG Hunting Cabin material verification
    cabin = by_id["rag_hunting_cabin_full"]
    assert cabin["materials"]["logs"] == 20
    assert cabin["materials"]["planks"] == 110  # 10 kit + 100 structure
    assert cabin["materials"]["nails"] == 149   # 50 kit + 99 structure
    assert cabin["materials"]["stones"] == 32

    # Zens Car Workbench material verification
    wb = by_id["zen_car_workbench"]
    assert wb["materials"]["nails"] == 60
    assert wb["materials"]["metal"] == 5

    # 4. RaG 37 Structural Parts table
    part_costs = guide["rag_part_costs"]
    assert len(part_costs) == 37
    assert "Foundation" in part_costs
    assert "Wall" in part_costs
    assert "DoorFrame" in part_costs
    assert "Door" in part_costs
    assert "MetalDoor" in part_costs
    assert "GateFrame" in part_costs
    assert "GateDoorLeft" in part_costs
    assert "GateDoorRight" in part_costs
    assert "AngledRoof" in part_costs
    assert "AngledRoofEndLeft" in part_costs
    assert "AngledRoofEndRight" in part_costs
    assert "HatchFrame" in part_costs
    assert "HatchDoor" in part_costs
    assert "HatchStaircase" in part_costs
    assert "HatchLadder" in part_costs
    assert "WoodStorageFloor" in part_costs

    # 5. Pruned and replaced mods
    pruned = guide["pruned_replacements"]
    pruned_names = [p["pruned_mod"] for p in pruned]
    assert any("BaseBuildingPlus" in p for p in pruned_names)
    assert any("BuildAnywhere" in p for p in pruned_names)
    assert any("Code Lock" in p for p in pruned_names)
    assert any("MuchStuffPack" in p for p in pruned_names)
    assert any("Leather Crafting" in p for p in pruned_names)
    assert any("Simple Ammo Crafting" in p for p in pruned_names)


def test_basebuilding_ui_surfaces_and_blueprints():
    """Verify both web_ui.html (Command Center PWA) and player_portal.html render the basebuilding guide."""
    # Surface 1: web_ui.html
    ui_html = web.UI_HTML_PATH.read_text(encoding="utf-8")
    assert 'id="view-5"' in ui_html
    assert 'id="nav-tab-build"' in ui_html
    assert "Basebuilding &amp; Homesteading Field Manual" in ui_html
    assert "ARCHITECTURAL BLUEPRINT STUDIO" in ui_html
    assert "COMPOUND BILL-OF-MATERIALS (BOM) PLANNER &amp; CALCULATOR" in ui_html
    assert "RECIPE CATALOG" in ui_html
    assert "getBlueprintSvg" in ui_html
    assert "BLUEPRINT 01 // TERRITORY FLAG POLE" in ui_html
    assert "BLUEPRINT 02 // RaG HUNTING CABIN" in ui_html
    assert "BLUEPRINT 03 // RaG MODULAR SNAP-GRID" in ui_html
    assert "BLUEPRINT 04 // VANILLA DAYZ 1.30 FENCE" in ui_html
    assert "renderBasebuildingView" in ui_html
    assert "updateBomQuantity" in ui_html
    assert "setBomPreset" in ui_html

    # Surface 2: player_portal.html (Survivor's Guide)
    portal_html = web.PLAYER_PORTAL_HTML_PATH.read_text(encoding="utf-8")
    assert 'id="basebuilding"' in portal_html
    assert '<a href="#basebuilding">Basebuilding</a>' in portal_html
    assert "Basebuilding &amp; Homesteading Field Manual" in portal_html
    assert "BLUEPRINT 01 // TERRITORY FLAG POLE" in portal_html
    assert "BLUEPRINT 02 // RaG HUNTING CABIN" in portal_html
    assert "BLUEPRINT 03 // RaG MODULAR SNAP-GRID" in portal_html
    assert "BLUEPRINT 04 // VANILLA DAYZ 1.30 FENCE" in portal_html
    assert 'id="pcat-vanilla"' in portal_html
    assert 'id="pcat-rag"' in portal_html
    assert 'id="pcat-cabin"' in portal_html
    assert 'id="pcat-mmg"' in portal_html
    assert 'id="pcat-utility"' in portal_html
    assert 'id="pcat-camp"' in portal_html
    assert "RaG Hunting Cabin (Complete Homestead)" in portal_html
    assert "Zens Static Car Workbench (Garage Station)" in portal_html
    assert "BetterHarvest Non-Rotting Garden Plots" in portal_html
    assert "CookZ Canning, Non-Decaying Cheese &amp; Sausages" in portal_html
    assert "BaseBuildingPlus (BBP)" in portal_html

    # Strict Portal Constraints must remain completely unbroken
    assert "/api/" not in portal_html
    assert "simulateTurn" not in portal_html
    assert "<script" not in portal_html


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
