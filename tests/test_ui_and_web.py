"""Tests for the Ad Aspera · DZDS UI surfaces: CLI design system, Status, TUI, and Web Command Center."""
from __future__ import annotations

import json
import pytest
import struct
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


def test_pwa_manifest_service_worker_and_generated_icons():
    """Verify Web App Manifest, Service Worker, and pure-Python generated crisp PNG/SVG icons."""
    import http.client
    import struct
    srv = web.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)

        # 1. Manifest (.webmanifest and .json)
        for mpath in ("/manifest.webmanifest", "/manifest.json"):
            conn.request("GET", mpath)
            r = conn.getresponse()
            assert r.status == 200
            assert "application/manifest+json" in r.getheader("Content-Type", "")
            manifest = json.loads(r.read().decode("utf-8"))
            assert "Ad Aspera" in manifest["name"]
            assert manifest["short_name"] == "Ad Aspera"
            assert manifest["display"] == "standalone"
            assert manifest["theme_color"] == "#0b0e11"
            assert manifest["background_color"] == "#0b0e11"
            assert len(manifest["icons"]) >= 4
            assert len(manifest["shortcuts"]) >= 3
            assert any(s["url"].startswith("/?view=0") for s in manifest["shortcuts"])
            assert any(s["url"].startswith("/?view=5") for s in manifest["shortcuts"])
            assert any(s["url"].startswith("/portal") for s in manifest["shortcuts"])
            assert len(manifest["screenshots"]) >= 2

        # 2. Service Worker (/sw.js)
        conn.request("GET", "/sw.js")
        sw_resp = conn.getresponse()
        assert sw_resp.status == 200
        assert "application/javascript" in sw_resp.getheader("Content-Type", "")
        assert sw_resp.getheader("Service-Worker-Allowed") == "/"
        sw_code = sw_resp.read().decode("utf-8")
        assert "dzds-pwa-" in sw_code
        assert "/portal" in sw_code
        assert "/manifest.webmanifest" in sw_code
        assert "fetch" in sw_code

        # 3. Vector SVG Icon (/icon.svg)
        conn.request("GET", "/icon.svg")
        svg_resp = conn.getresponse()
        assert svg_resp.status == 200
        assert "image/svg+xml" in svg_resp.getheader("Content-Type", "")
        svg_body = svg_resp.read().decode("utf-8")
        assert svg_body.startswith("<svg") and svg_body.strip().endswith("</svg>")

        # 4. Pure-Python Generated Crisp PNG Icons
        icons_to_test = [
            ("/icon-192.png", 192, 192),
            ("/icon-512.png", 512, 512),
            ("/icon-maskable-512.png", 512, 512),
            ("/icon-180.png", 180, 180),
            ("/favicon.ico", 32, 32),
        ]
        for ipath, exp_w, exp_h in icons_to_test:
            conn.request("GET", ipath)
            iresp = conn.getresponse()
            assert iresp.status == 200
            assert iresp.getheader("Content-Type") == "image/png"
            data = iresp.read()
            # PNG signature
            assert data.startswith(b"\x89PNG\r\n\x1a\n")
            # IHDR width and height at bytes 16..24
            w, h = struct.unpack(">II", data[16:24])
            assert (w, h) == (exp_w, exp_h), f"{ipath} expected {exp_w}x{exp_h}, got {w}x{h}"

        conn.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_user_persistent_preferences_api_and_isolation(tmp_path):
    """Verify UserProfileStore deep sanitization, isolated storage, and HTTP API roundtrip."""
    store_file = tmp_path / "web_profiles.json"
    pstore = web.UserProfileStore(store_file)

    # 1. Defaults for new user
    p_alpha = pstore.get("survivor_alpha")
    assert p_alpha["callsign"] == "Survivor"
    assert p_alpha["faction"] == "Settlers"
    assert p_alpha["theme"] == "obsidian"
    assert p_alpha["density"] == "standard"
    assert p_alpha["pinned_sites"] == []
    assert p_alpha["custom_pins"] == []
    assert p_alpha["site_notes"] == {}

    # 2. Update with custom pins, site notes, checklist
    updated_alpha = pstore.update("survivor_alpha", {
        "callsign": "Delta-Lead",
        "faction": "Jackals",
        "theme": "phosphor",
        "density": "compact",
        "default_view": 6,
        "pinned_sites": ["Cement Works", "Settler Haven"],
        "site_notes": {"Cement Works": "Hidden stash under silo B"},
        "custom_pins": [
            {"id": "pin_1", "label": "Extraction LZ", "x": 6400.0, "z": 8200.0, "map": "nasdara", "color": "#ffaa00"}
        ],
        "checklist": {"installed_pwa": True, "configured_profile": True},
    })
    assert updated_alpha["callsign"] == "Delta-Lead"
    assert updated_alpha["faction"] == "Jackals"
    assert updated_alpha["theme"] == "phosphor"
    assert updated_alpha["density"] == "compact"
    assert updated_alpha["default_view"] == 6
    assert updated_alpha["pinned_sites"] == ["Cement Works", "Settler Haven"]
    assert updated_alpha["site_notes"]["Cement Works"] == "Hidden stash under silo B"
    assert len(updated_alpha["custom_pins"]) == 1
    assert updated_alpha["custom_pins"][0]["label"] == "Extraction LZ"
    assert updated_alpha["checklist"]["installed_pwa"] is True
    assert updated_alpha["updated_at"] != ""

    # 3. Reload from disk into fresh store instance (persistence check)
    reloaded_store = web.UserProfileStore(store_file)
    from_disk = reloaded_store.get("survivor_alpha")
    assert from_disk["callsign"] == "Delta-Lead"
    assert from_disk["custom_pins"][0]["label"] == "Extraction LZ"

    # 4. User isolation: survivor_bravo must have separate defaults
    p_bravo = reloaded_store.get("survivor_bravo")
    assert p_bravo["callsign"] == "Survivor"
    assert p_bravo["faction"] == "Settlers"
    assert p_bravo["pinned_sites"] == []
    assert p_bravo["site_notes"] == {}
    assert p_bravo["custom_pins"] == []

    # 5. HTTP API roundtrip via make_server
    import http.client
    srv = web.make_server("127.0.0.1", 0, profile_store=reloaded_store)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)

        # GET /api/prefs for survivor_alpha
        conn.request("GET", "/api/prefs?user=survivor_alpha")
        r = conn.getresponse()
        assert r.status == 200
        data = json.loads(r.read().decode("utf-8"))
        assert data["user_id"] == "survivor_alpha"
        assert data["prefs"]["callsign"] == "Delta-Lead"

        # POST /api/prefs to update survivor_bravo
        post_body = json.dumps({
            "callsign": "Bravo-Sniper",
            "faction": "Rust",
            "theme": "badlands",
        })
        headers = {
            "Content-Type": "application/json",
            web.TOKEN_HEADER: srv.dzds_token,
            web.USER_HEADER: "survivor_bravo",
        }
        conn.request("POST", "/api/prefs", body=post_body, headers=headers)
        r2 = conn.getresponse()
        assert r2.status == 200
        data2 = json.loads(r2.read().decode("utf-8"))
        assert data2["saved"] is True
        assert data2["prefs"]["callsign"] == "Bravo-Sniper"
        assert data2["prefs"]["faction"] == "Rust"

        # POST /api/prefs with reset
        conn.request("POST", "/api/prefs", body=json.dumps({"reset": True}), headers=headers)
        r3 = conn.getresponse()
        assert r3.status == 200
        data3 = json.loads(r3.read().decode("utf-8"))
        assert data3["prefs"]["callsign"] == "Survivor"

        conn.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_share_manager_and_remote_off_lan_access(tmp_path):
    """Verify off-LAN share links, DNS rebinding bypass with share tokens, and remote sandboxing."""
    share_file = tmp_path / "share_links.json"
    smgr = web.ShareManager(share_file)

    # 1. Create a share link
    link = smgr.create_link(
        label="Squad Delta Link",
        public_url="https://tactical.example.com",
        expires_hours=24,
    )
    token = link["token"]
    assert token and len(token) >= 16
    assert link["label"] == "Squad Delta Link"
    assert link["app_url"] == f"https://tactical.example.com/?share={token}"
    assert link["portal_url"] == f"https://tactical.example.com/portal?share={token}"

    # Validate active token
    entry = smgr.validate_token(token)
    assert entry is not None
    assert entry["id"] == link["id"]

    # 2. HTTP Server integration
    import http.client
    srv = web.make_server("127.0.0.1", 0, share_manager=smgr)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        # A. Foreign host without share token is blocked by DNS rebinding protection (403)
        conn_evil = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn_evil.request("GET", "/api/state?map=nasdara", headers={"Host": "tactical.example.com"})
        r_evil = conn_evil.getresponse()
        assert r_evil.status == 403
        conn_evil.close()

        # B. Foreign host WITH valid share token query param is accepted (200)
        conn_share = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn_share.request("GET", f"/api/state?map=nasdara&share={token}", headers={"Host": "tactical.example.com"})
        r_share = conn_share.getresponse()
        assert r_share.status == 200
        state = json.loads(r_share.read().decode("utf-8"))
        assert state["active_map"] == "nasdara"

        # C. GET / with share token sets cookie and succeeds
        conn_share.request("GET", f"/?share={token}", headers={"Host": "tactical.example.com"})
        r_html = conn_share.getresponse()
        assert r_html.status == 200
        set_cookie = r_html.getheader("Set-Cookie", "")
        assert f"dzds_share={token}" in set_cookie
        r_html.read()

        # D. GET /api/share/status as remote visitor (redacts tokens)
        conn_share.request("GET", f"/api/share/status?share={token}", headers={"Host": "tactical.example.com"})
        r_stat = conn_share.getresponse()
        assert r_stat.status == 200
        stat_data = json.loads(r_stat.read().decode("utf-8"))
        assert stat_data["links"] == []  # Non-operator cannot see other tokens
        assert stat_data["link_count"] >= 1

        # E. Remote visitor simulation is sandboxed and does not touch disk ledger
        initial_turn = WarLedger.load_or_new("nasdara").s.turn
        remote_headers = {
            "Content-Type": "application/json",
            web.TOKEN_HEADER: srv.dzds_token,
            web.SHARE_HEADER: token,
            web.USER_HEADER: "remote_guest_42",
            "Host": "tactical.example.com",
        }
        body = json.dumps({"map": "nasdara", "commit": False})
        conn_share.request("POST", "/api/simulate-turn", body=body, headers=remote_headers)
        r_sim = conn_share.getresponse()
        assert r_sim.status == 200
        sim_data = json.loads(r_sim.read().decode("utf-8"))
        assert sim_data["state"]["ledger"]["turn"] >= initial_turn + 1
        # Disk ledger is unaffected
        assert WarLedger.load_or_new("nasdara").s.turn == initial_turn

        # F. Remote visitor cannot perform operator-only share mutations
        conn_share.request("POST", "/api/share/create", body=json.dumps({"label": "Malicious"}), headers=remote_headers)
        r_forbidden = conn_share.getresponse()
        assert r_forbidden.status == 403

        # G. Operator can revoke the token, then access is blocked
        op_headers = {
            "Content-Type": "application/json",
            web.TOKEN_HEADER: srv.dzds_token,
        }
        conn_local = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn_local.request("POST", "/api/share/revoke", body=json.dumps({"token": token}), headers=op_headers)
        r_revoke = conn_local.getresponse()
        assert r_revoke.status == 200
        conn_local.close()

        # Subsequent foreign request with revoked token is refused (403)
        conn_share.request("GET", f"/api/state?map=nasdara&share={token}", headers={"Host": "tactical.example.com"})
        r_after = conn_share.getresponse()
        assert r_after.status == 403
        conn_share.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_portable_html_export_api():
    """Verify single-file portable HTML export bundle contains offline data and zero network dependencies."""
    import http.client
    srv = web.make_server("127.0.0.1", 0)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True)
    t.start()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        conn.request("GET", "/api/export-portable")
        r = conn.getresponse()
        assert r.status == 200
        assert "text/html" in r.getheader("Content-Type", "")
        cd = r.getheader("Content-Disposition", "")
        assert 'filename="ad-aspera-nasdara-portable.html"' in cd
        body = r.read().decode("utf-8")
        assert len(body) > 30000
        assert "<!DOCTYPE html>" in body
        assert "window.__DZDS_PORTABLE_SNAPSHOTS__" in body
        assert "window.__DZDS_PORTABLE_PREFS__" in body
        assert "window.__DZDS_PORTABLE_MAP__" in body
        assert "nasdara" in body
        assert "chernarusplus" in body
        assert "Basebuilding &amp; Homesteading Field Manual" in body
        assert "portable-mode" in body
        # Self-contained: no external script tags pointing to cdn / remote origins
        assert "<script src=" not in body.lower()
        conn.close()
    finally:
        srv.shutdown()
        srv.server_close()


def test_in_app_instructions_and_pwa_surfaces():
    """Verify in-app installation guides, run commands, preferences, and portal constraints."""
    # Surface 1: web_ui.html (Command Center PWA)
    ui_html = web.UI_HTML_PATH.read_text(encoding="utf-8")
    # PWA head tags
    assert '<meta name="theme-color" content="#0b0e11">' in ui_html
    assert '<meta name="apple-mobile-web-app-capable" content="yes">' in ui_html
    assert '<link rel="manifest" href="/manifest.webmanifest' in ui_html
    assert '<link rel="apple-touch-icon" sizes="180x180" href="/icon-180.png">' in ui_html

    # Topbar controls
    assert 'id="nav-tab-app"' in ui_html
    assert 'id="btn-pwa-install"' in ui_html
    assert 'id="hdr-callsign"' in ui_html
    assert 'id="pwa-status-pill"' in ui_html

    # View 6 (App & Share Studio)
    assert 'id="view-6"' in ui_html
    assert "App, off-LAN sharing &amp; persistent settings" in ui_html
    assert "PROGRESSIVE WEB APP (PWA) DIAGNOSTICS &amp; INSTALL GUIDE" in ui_html
    assert "Desktop Chrome / Edge / Brave" in ui_html
    assert "Apple iOS &amp; iPadOS (Safari)" in ui_html
    assert "Android (Chrome, Edge, Samsung Internet, Firefox)" in ui_html
    assert "Firefox Desktop" in ui_html
    assert "make dashboard OPEN=1" in ui_html
    assert "make dashboard SHARE=1 OPEN=1" in ui_html
    assert "tools/dashboard.py --share --open" in ui_html
    assert "OFF-LAN SHARE LINK STUDIO (SECURE REMOTE ACCESS)" in ui_html
    assert 'id="share-custom-url-input"' in ui_html
    assert 'id="share-links-table-wrap"' in ui_html
    assert "PERSISTENT SURVIVOR PREFERENCES &amp; SETTINGS" in ui_html
    assert 'id="pref-callsign"' in ui_html
    assert 'id="pref-faction"' in ui_html
    assert 'id="pref-launcher"' in ui_html
    assert 'id="pref-theme"' in ui_html
    assert 'id="pref-density"' in ui_html
    assert 'id="pref-default-view"' in ui_html

    # Custom Waypoint Drop Pin Tool
    assert 'id="btn-drop-pin"' in ui_html
    assert 'id="lyr-pins"' in ui_html
    assert 'Personal pins &amp; notes' in ui_html

    # Surface 2: player_portal.html (Survivor's Guide)
    portal_html = web.PLAYER_PORTAL_HTML_PATH.read_text(encoding="utf-8")
    assert '<link rel="manifest" href="/manifest.webmanifest"' in portal_html
    assert '<meta name="theme-color" content="#101412">' in portal_html
    assert 'id="install"' in portal_html
    assert '<a href="#install">Install &amp; Run App</a>' in portal_html
    assert "Install &amp; run the app (PWA &amp; off-LAN links)" in portal_html
    assert "Install on desktop (Linux, Windows, macOS)" in portal_html
    assert "Install on mobile (iOS, iPadOS &amp; Android)" in portal_html
    assert "make dashboard OPEN=1" in portal_html
    assert "make dashboard SHARE=1 OPEN=1" in portal_html
    assert "Off-LAN share links &amp; personal preferences" in portal_html

    # Strict Portal Constraints
    assert "/api/" not in portal_html
    assert "simulateTurn" not in portal_html
    assert "<script" not in portal_html


def test_deep_alignment_api_endpoints_and_state():
    """Verify backend API endpoints and state payloads reflect server systems."""
    # 1. /api/fleet
    code, fleet_data = web.handle_api("GET", "/api/fleet", {"map": ["nasdara"]}, {})
    assert code == 200
    assert fleet_data["total_world_fleet_count"] >= 47
    assert fleet_data["aviation_count"] >= 9
    assert len(fleet_data["rigs"]) >= 47
    assert len(fleet_data["convoys"]) == 3
    assert len(fleet_data["mad_max_phases"]) == 5
    assert "60× Nails + 5× Metal Sheets" in fleet_data["maintenance"]["workbench"]
    assert "VehicleRequireKeyToStart=1" in fleet_data["security"]["keys"]

    # Verify sample rig structure
    rig0 = fleet_data["rigs"][0]
    assert "class" in rig0 and "name" in rig0 and "category" in rig0
    assert "fuel_l" in rig0 and "parts" in rig0

    # 2. /api/convoys
    code, convoys = web.handle_api("GET", "/api/convoys", {"map": ["nasdara"]}, {})
    assert code == 200
    assert len(convoys) == 3
    c_ids = [c["id"] for c in convoys]
    assert "rust_supply_run" in c_ids
    assert "jackal_highway_raid" in c_ids
    assert "peacekeeper_escort" in c_ids

    for c in convoys:
        assert c["from_site"] and c["to_site"]
        assert c["ambush_site"]
        assert len(c["ambush_pos"]) == 3
        assert len(c["waypoints"]) > 10

    # 3. /api/survival-manual
    code, surv = web.handle_api("GET", "/api/survival-manual", {"map": ["nasdara"]}, {})
    assert code == 200
    assert "water_system" in surv
    assert "agriculture_and_food" in surv
    assert "medical_triage" in surv
    assert "radio_net" in surv
    assert "respawn_network" in surv
    assert "cholera" in surv["water_system"]["hazard"].lower()
    assert "87.8 MHz" in surv["radio_net"]["frequency"]
    assert len(surv["respawn_network"]["tiers"]) == 5
    assert surv["special_forces_outfit"]["chance_percent"] == 3

    # 4. /api/npcs
    code, npcs = web.handle_api("GET", "/api/npcs", {}, {})
    assert code == 200
    assert len(npcs) == 7
    assert "1" in npcs
    assert npcs["1"]["name"] == "Elder Tariq"
    assert npcs["1"]["role_site"] == "Qalat-e Lut"
    assert len(npcs["1"]["nodes"]) >= 5
    assert len(npcs["1"]["topics"]) >= 5

    # 5. /api/state
    code, state = web.handle_api("GET", "/api/state", {"map": ["nasdara"]}, {})
    assert code == 200
    assert "fleet" in state
    assert "convoys" in state
    assert "survival_manual" in state
    assert "npc_dossiers" in state
    assert state["fleet"]["total_world_fleet_count"] >= 47
    assert len(state["convoys"]) == 3
    assert len(state["front_plan"]["npcs"]) == 7


def test_deep_alignment_player_portal_content():
    """Verify player_portal.html static survivor manual matches all server features."""
    portal_html = web.PLAYER_PORTAL_HTML_PATH.read_text(encoding="utf-8")

    # Strict static portal safety invariants
    assert "<script" not in portal_html, "player_portal.html must NEVER contain <script> tags"
    assert "/api/" not in portal_html, "player_portal.html must NEVER contain /api/ references"
    assert "simulateTurn" not in portal_html, "player_portal.html must NEVER contain simulateTurn"

    # Navigation anchors
    assert '<a href="#vehicles">Vehicles &amp; Flight</a>' in portal_html
    assert '<a href="#survive">Survive</a>' in portal_html
    assert '<a href="#companions">Companions &amp; Recruits</a>' in portal_html
    assert '<a href="#campaign">Campaign &amp; Barter</a>' in portal_html

    # Vehicles & Aviation Section (#vehicles)
    assert '<section id="vehicles"' in portal_html
    assert "Overland Logistics, Fleet &amp; Flight Operations" in portal_html
    assert "9-Aircraft Helicopter Fleet &amp; Pre-Fitted Kits" in portal_html
    assert "Zen's Static Car Workbench" in portal_html
    assert "60× Nails + 5× Metal Sheets" in portal_html
    assert "Expansion Keys, Lockpicking &amp; Camo Tarps" in portal_html
    assert "CarCover Tarps" in portal_html
    assert "Tri-Corridor Automated AI Supply Convoys" in portal_html
    assert "5-Phase Mad Max Vehicular Progression Arc" in portal_html

    # Survival Field Manual 5 Pillars (#survive)
    assert '<section id="survive"' in portal_html
    assert "Badlands Survival Field Manual · 5 Pillars" in portal_html
    assert "1. Water Purification &amp; Cholera" in portal_html
    assert "2. Homestead Farming &amp; Curing" in portal_html
    assert "3. Trauma &amp; Infection Triage" in portal_html
    assert "4. Settler Radio Net 87.8 MHz" in portal_html
    assert "5. 5-Tier Respawn Network" in portal_html
    assert "87.8 MHz" in portal_html
    assert "Qalat-e Lut Fortress HQ" in portal_html
    assert "Friend-First Co-op" in portal_html
    assert "Soviet Special Forces Outfit" in portal_html
    assert "3% RARE ROLL" in portal_html

    # Companions Section (#companions)
    assert '<section id="companions"' in portal_html
    assert "Frontier Settler Companions &amp; Recruits" in portal_html
    assert "Soran the Scout" in portal_html
    assert "Kaveh the Sentinel" in portal_html
    assert "Dr. Yasmin" in portal_html
    assert "Rostam the Scavenger" in portal_html

    # Barter Currency Matrix (#campaign)
    assert '<section id="campaign"' in portal_html
    assert "Faction Barter Currency Exchange Matrix" in portal_html
    assert "Ammunition (Hard Currency)" in portal_html
    assert "Builders' Currency (Hardware)" in portal_html
    assert "UN Humanitarian Scrip" in portal_html
    assert "Industrial Hardware &amp; Tolls" in portal_html


def test_deep_alignment_companion_app_ui():
    """Verify web_ui.html tactical command center contains all interactive modules."""
    ui_html = web.UI_HTML_PATH.read_text(encoding="utf-8")

    # Layer toggle button
    assert 'id="lyr-convoys"' in ui_html
    assert "Tri-Corridor Convoys" in ui_html

    # NPC Dossier Modal Dialog
    assert 'id="npc-dossier-modal"' in ui_html
    assert 'id="npc-modal-content"' in ui_html
    assert 'class="modal-backdrop"' in ui_html
    assert 'class="modal-dialog"' in ui_html

    # Expedition Survival & Water Calculator
    assert "EXPEDITION SURVIVAL &amp; WATER REQUIREMENTS CALCULATOR" in ui_html
    assert 'id="scalc-hours"' in ui_html
    assert 'id="scalc-party"' in ui_html
    assert 'id="scalc-transport"' in ui_html
    assert 'id="scalc-out-water"' in ui_html
    assert 'id="scalc-out-food"' in ui_html
    assert 'id="scalc-out-fuel"' in ui_html
    assert 'id="scalc-out-med"' in ui_html
    assert 'id="scalc-out-cistern"' in ui_html

    # World Vehicle Fleet, Aviation & Convoys
    assert "WORLD VEHICLE FLEET, AVIATION &amp; LOGISTICS (47 RIGS)" in ui_html
    assert 'id="fleet-search"' in ui_html
    assert 'id="fleet-grid"' in ui_html
    assert 'id="convoys-grid"' in ui_html
    assert 'id="fleet-filt-all"' in ui_html
    assert 'id="fleet-filt-aviation"' in ui_html
    assert 'id="fleet-filt-heavy"' in ui_html
    assert 'id="fleet-filt-overland"' in ui_html
    assert 'id="fleet-filt-light"' in ui_html

    # Chop-Shops & Zen's Workbench
    assert "CHOP-SHOPS &amp; ZEN'S STATIC CAR WORKBENCH (REPAIR PROTOCOL)" in ui_html
    assert "60× Nails + 5× Metal Sheets" in ui_html

    # Geocaches layer & map integration
    assert 'id="lyr-geocaches"' in ui_html
    assert "LAYERS.geocaches" in ui_html
    assert "GEO #" in ui_html


def test_api_geocaches_endpoint():
    from http import HTTPStatus
    status, data = web.handle_api("GET", "/api/geocaches", {}, {})
    assert status == HTTPStatus.OK
    caches = data.get("Geocaches", [])
    assert len(caches) == 20
    assert caches[0]["Id"] == 1
    assert "Landmark" in caches[0]
    assert "Pos" in caches[0]



