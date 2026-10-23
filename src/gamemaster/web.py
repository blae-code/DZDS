"""Ad Aspera · DZDS Web Tactical Command Center (HTTP + REST API + SPA).

Provides a zero-external-dependency web server and JSON API for inspecting and simulating
the Nasdara / Chernarus+ living sandbox:
  - Interactive 16.4x16.4 km Vector Cartographic Map (zones, patrol waypoints, road spots,
    exclusion zones, war party routes, quest vectors, and distance/flight-time ruler)
  - War Ledger & 5x5 Faction Diplomacy Matrix + in-memory Turn & Skirmish Simulator
  - Front Plan (Barter Traders & Live Quests) + Refugee Arrival Kit & Aircraft Inspector
  - Mod Loadout Registry (Tier 1..4) with one-click Godlike panel string copy
  - GM Telemetry (.ADM stream, Open-Country Encounter Audit, and Radio Bulletin Studio)
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import random
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import active  # noqa: E402
import arrivals  # noqa: E402
import dzds_profile  # noqa: E402
import encounter_audit  # noqa: E402
import front_plan  # noqa: E402
import modstring  # noqa: E402
import patrol_gen  # noqa: E402
import status as status_mod  # noqa: E402
import ui  # noqa: E402
import zones as zmod  # noqa: E402
from .adm import parse_line  # noqa: E402
from .ledger import STATE, WarLedger  # noqa: E402


class SandboxStore:
    """Holds live + preview WarLedger state per map for the Command Center."""

    def __init__(self) -> None:
        self.ledgers: dict[str, WarLedger] = {}
        self.rng = random.Random()
        self.turn_log: list[dict] = []

    def get_ledger(self, map_name: str, reload_disk: bool = False) -> WarLedger:
        if reload_disk or map_name not in self.ledgers:
            if STATE.exists():
                try:
                    led = WarLedger.load(map_name)
                except SystemExit:
                    led = WarLedger.new(map_name)
            else:
                led = WarLedger.new(map_name)
            self.ledgers[map_name] = led
        return self.ledgers[map_name]

    def build_state(self, map_name: str | None = None) -> dict:
        map_name = map_name or active.map_name()
        if map_name not in ("nasdara", "chernarusplus"):
            map_name = active.map_name()
        led = self.get_ledger(map_name)
        map_data = yaml.safe_load((ROOT / "maps" / f"{map_name}.yaml").read_text())
        factions_cfg = yaml.safe_load((ROOT / "presets" / "factions.yaml").read_text())
        traders_cfg = yaml.safe_load((ROOT / "presets" / "traders.yaml").read_text())
        quests_cfg = yaml.safe_load((ROOT / "presets" / "quests.yaml").read_text())
        arrivals_cfg = yaml.safe_load((ROOT / "presets" / "arrivals.yaml").read_text())
        world_cfg = yaml.safe_load((ROOT / "presets" / "world.yaml").read_text())
        mods_all = modstring.load_mods()
        mods_enabled = modstring.ordered(mods_all)

        locs = led.locations()
        holders = led.holders()
        zs = zmod.build(map_data, led.s.control, locs)
        patrols = patrol_gen.generate(map_name, control=holders, locs=locs)
        if led.s.war_party and led.s.war_party.get("kind") in ("raid", "offensive"):
            patrols += patrol_gen.war_party_patrols(led.s.war_party, locs)

        traders = front_plan.plan_traders(led, traders_cfg)
        for t in traders:
            raw = traders_cfg["traders"].get(t["trader"], {})
            t["faction"] = raw.get("faction", "none")
            t["role"] = raw.get("role", "")
            t["currencies"] = raw.get("currencies", [])
            t["notes"] = raw.get("notes", "")

        quests = front_plan.plan_quests(led, quests_cfg)
        col_site = status_mod.active_column_site(map_data, arrivals_cfg)

        # Arrivals road points & exclusion zones (if mission files exist)
        mission = arrivals.mission_dir(map_data)
        excl_zones = [
            {"x": x, "z": z, "radius": r}
            for x, z, r in arrivals.exclusion_zones(arrivals_cfg, map_data)
        ]
        road_pts = []
        arr_pts = []
        if (mission / "cfgeventspawns.xml").exists():
            spots = arrivals.road_spots(mission, arrivals_cfg["road_events"])
            raw_zones = arrivals.exclusion_zones(arrivals_cfg, map_data)
            road_pts = [arrivals.point(s) for s in spots if not arrivals.excluded(s, raw_zones)]
            try:
                arr_pts = arrivals.arrival_points(arrivals_cfg, map_data, spots)
            except SystemExit:
                arr_pts = []

        # Faction detail cards
        factions_out = {}
        overrides = {(d["from"], d["to"]): d["stance"] for d in led.s.auto_diplomacy}
        for fname in ui.FACTION_ORDER:
            spec = factions_cfg["factions"][fname]
            effective_stance = {}
            for other in (*ui.FACTION_ORDER, "Infected"):
                effective_stance[other] = overrides.get((fname, other), spec["stance"].get(other, "hostile"))
            factions_out[fname] = {
                "key": fname,
                "display": spec["display"],
                "custom_faction": spec["custom_faction"],
                "color": ui.HEX.get(fname, "#dedcd6"),
                "symbol": ui.FACTION_SYMBOLS.get(fname, "●"),
                "lore": spec.get("lore", ""),
                "player_standing_desc": spec.get("player_standing", ""),
                "recruitable": bool(spec.get("recruitable")),
                "holds_roles": spec.get("holds_roles", []),
                "behaviour": spec.get("behaviour", {}),
                "loadout": spec.get("loadout", {}),
                "radio_voice": spec.get("radio_voice", {}),
                "strength": round(led.s.strength.get(fname, 60.0), 1),
                "standing": round(led.s.standing.get(fname, 0.0), 1),
                "sites": sorted(holders.get(fname, [])),
                "resources": dict(led.resources(fname)),
                "deaths_this_turn": led.s.deaths.get(fname, 0),
                "player_kills_this_turn": led.s.player_kills.get(fname, 0),
                "stance": effective_stance,
            }

        # Telemetry & ADM audit
        adm_files = sorted((ROOT / "server" / "profiles").glob("*.ADM"))
        sim_file = ROOT / "gm_state" / "sim.ADM"
        if sim_file.exists():
            adm_files.append(sim_file)
        adm_lines = [ln for f in adm_files[-4:] for ln in f.read_text(errors="replace").splitlines()[-500:]]
        audit_raw = encounter_audit.audit(adm_lines, zs)
        audit_list = []
        for player, rec in sorted(audit_raw.items()):
            rate = rec["outside"] / max(1, rec["sessions"])
            audit_list.append({
                "player": player,
                "sessions": rec["sessions"],
                "outside": rec["outside"],
                "inside": rec["inside"],
                "rate": round(rate, 2),
                "ok": rate <= 1 / 3,
            })

        recent_adm = []
        for ln in reversed(adm_lines):
            ev = parse_line(ln)
            if ev and ev.kind in ("connect", "disconnect", "hit", "death"):
                recent_adm.append({
                    "time": ev.time,
                    "kind": ev.kind,
                    "is_ai": ev.is_ai,
                    "player": ev.player,
                    "faction": ev.faction or ("Settlers" if not ev.is_ai else ""),
                    "by": ev.by or "",
                    "hp": ev.hp,
                    "pos": list(ev.pos) if ev.pos else None,
                })
            if len(recent_adm) >= 25:
                break

        client_panel, server_panel, local_mods = modstring.build_panel_fields(mods_all)
        panel_ok = modstring.PANEL_FILE.exists() and modstring.PANEL_FILE.read_text() == client_panel
        pbo_ok = (ROOT / "build" / "@DZDS" / "addons" / "dzds_scripts.pbo.dzds.bisign").exists()
        arr_ok = (ROOT / "server" / "profiles" / "DZDS" / "arrivals.json").exists()

        # Radio bulletin preview
        bulletin = dzds_profile.build_bulletin(led, traders, quests) if hasattr(dzds_profile, "build_bulletin") else {
            "Turn": led.s.turn,
            "Frequency": "87.8 MHz (Settler Net)",
            "Messages": led.recent_events(6) or [f"Turn {led.s.turn}: All Settler strongholds holding perimeter."],
        }

        return {
            "active_map": map_name,
            "palette": ui.HEX,
            "map": {
                "name": map_name,
                "mission": map_data.get("mission"),
                "bounds": map_data.get("bounds", [0, 0, 16384, 16384]),
                "zone_radius_m": map_data.get("zone_radius_m", 400),
                "locations": {
                    k: {
                        "pos": v[:2],
                        "roles": sorted(led.site_roles(k)),
                        "holder": led.s.control.get(k, "unheld"),
                        "state": "warzone" if led.s.control.get(k) == "contested"
                                 else "stronghold" if k in led.s.control else "open_country",
                        "marker": (world_cfg.get("markers", {}).get("by_holder") or {}).get(led.s.control.get(k, "")),
                        "pressure": led.s.pressure.get(k, {}),
                        "is_claimed": k in led.s.extra_sites,
                    }
                    for k, v in sorted(locs.items())
                },
                "arrival_sites": map_data.get("arrival_sites") or {},
                "active_column": col_site,
                "exclusion_zones": excl_zones,
                "road_points": road_pts,
                "arrival_points": arr_pts,
            },
            "ledger": {
                "turn": led.s.turn,
                "last_turn_at": led.s.last_turn_at,
                "control": led.s.control,
                "war_party": led.s.war_party,
                "war_party_candidates": led.war_party_candidates(),
                "auto_diplomacy": led.s.auto_diplomacy,
                "history": list(reversed(led.s.history[-30:])),
                "pressure": led.s.pressure,
            },
            "factions": factions_out,
            "patrols": patrols,
            "front_plan": {
                "traders": traders,
                "quests": quests,
                "currencies": traders_cfg.get("currencies", {}),
            },
            "arrivals": {
                "cooldown_hours": arrivals_cfg.get("cooldown_hours", 24),
                "nav_kit": arrivals_cfg.get("nav_kit", {}),
                "radio_index": arrivals_cfg.get("radio", {}).get("settler_net_index", 0),
                "aircraft": arrivals_cfg.get("aircraft", []),
                "favored": arrivals_cfg.get("favored", []),
                "vehicles": arrivals_cfg.get("vehicles", []),
                "archetypes": arrivals.archetypes(arrivals_cfg),
            },
            "mods": {
                "enabled_count": len(mods_enabled),
                "total_count": len(mods_all),
                "panel_additional_mods": client_panel,
                "panel_server_mods": server_panel,
                "local_mods": local_mods,
                "items": [
                    {
                        "name": m["name"],
                        "folder": m["folder"],
                        "id": m["id"],
                        "tier": m["tier"],
                        "tier_name": modstring.TIER_NAMES.get(m["tier"], ""),
                        "side": m.get("side", "both"),
                        "enabled": bool(m.get("enabled", True)),
                        "verified": bool(m.get("verified", False)),
                        "local": bool(m.get("local", False)),
                        "note": m.get("note", ""),
                    }
                    for m in sorted(mods_all, key=lambda x: (not x.get("enabled", True), x["tier"], x["name"]))
                ],
            },
            "telemetry": {
                "adm_file_count": len(adm_files),
                "encounter_audit": audit_list,
                "recent_events": recent_adm,
                "bulletin": bulletin,
                "readiness": {
                    "panel_ok": panel_ok,
                    "pbo_ok": pbo_ok,
                    "arrivals_ok": arr_ok,
                },
            },
        }

    def simulate_turn(self, map_name: str, commit: bool = False) -> dict:
        led = self.get_ledger(map_name)
        now = dt.datetime.now() + dt.timedelta(hours=4 * (led.s.turn + 1))
        events = led.turn(now=now, force=True)
        if commit:
            led.save()
        return {"events": events, "state": self.build_state(map_name)}

    def record_skirmish(self, map_name: str, site: str, victim_faction: str,
                        killer_faction: str = "Players", kills: int = 5) -> dict:
        led = self.get_ledger(map_name)
        locs = led.locations()
        pos = locs.get(site)
        if pos:
            for _ in range(max(1, min(25, int(kills)))):
                led.record_death(victim_faction, killer_faction, pos, killer_name="Operator" if killer_faction == "Players" else None)
        return {"state": self.build_state(map_name)}

    def reset_preview(self, map_name: str) -> dict:
        self.get_ledger(map_name, reload_disk=True)
        return {"state": self.build_state(map_name)}

    def claim_site(self, map_name: str, name: str, x: float, z: float,
                   roles: list[str] | None = None, faction: str = "Settlers",
                   commit: bool = False) -> dict:
        led = self.get_ledger(map_name)
        led.claim(name, [float(x), float(z)], roles or ["inland_town"], faction)
        if commit:
            led.save()
        return {"state": self.build_state(map_name)}

    def roll_kit(self, archetype_name: str | None = None) -> dict:
        arrivals_cfg = yaml.safe_load((ROOT / "presets" / "arrivals.yaml").read_text())
        archs = arrivals.archetypes(arrivals_cfg)
        arch = next((a for a in archs if a["Name"] == archetype_name), archs[0])
        items = arrivals.simulate_kit(arch, self.rng)
        return {
            "archetype": arch["Name"],
            "aircraft": bool(arch["Aircraft"]),
            "weight": arch["Weight"],
            "firearm": items[0] if items else "",
            "items": items,
            "count": len(items),
        }


STORE = SandboxStore()


UI_HTML_PATH = Path(__file__).with_name("web_ui.html")


def handle_api(method: str, path: str, query: dict[str, list[str]], body: dict) -> tuple[int, dict]:
    """Pure dispatcher for API requests (testable without a socket)."""
    map_name = (query.get("map") or [body.get("map") or active.map_name()])[0]

    if method == "GET" and path == "/api/state":
        return HTTPStatus.OK, STORE.build_state(map_name)
    if method == "POST" and path == "/api/simulate-turn":
        return HTTPStatus.OK, STORE.simulate_turn(map_name, commit=bool(body.get("commit")))
    if method == "POST" and path == "/api/skirmish":
        return HTTPStatus.OK, STORE.record_skirmish(
            map_name,
            site=str(body.get("site") or ""),
            victim_faction=str(body.get("victim") or "Jackals"),
            killer_faction=str(body.get("killer") or "Players"),
            kills=int(body.get("kills") or 5),
        )
    if method == "POST" and path == "/api/claim":
        return HTTPStatus.OK, STORE.claim_site(
            map_name,
            name=str(body.get("name") or "Player Outpost"),
            x=float(body.get("x") or 7500),
            z=float(body.get("z") or 8500),
            roles=list(body.get("roles") or ["inland_town"]),
            faction=str(body.get("faction") or "Settlers"),
            commit=bool(body.get("commit")),
        )
    if method == "POST" and path == "/api/reset-preview":
        return HTTPStatus.OK, STORE.reset_preview(map_name)
    if method == "POST" and path == "/api/roll-kit":
        return HTTPStatus.OK, STORE.roll_kit(body.get("archetype"))
    return HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {method} {path}"}


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass  # Keep console clean

    def _send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            html = UI_HTML_PATH.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
            return
        if parsed.path == "/preview.png":
            img_path = ROOT / "mods" / "workshop" / "preview.png"
            if img_path.exists():
                raw = img_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        status, data = handle_api("GET", parsed.path, parse_qs(parsed.query), {})
        self._send_json(status, data)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        status, data = handle_api("POST", parsed.path, parse_qs(parsed.query), body)
        self._send_json(status, data)


def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), DashboardHandler)
    print(ui.banner(
        "WEB TACTICAL COMMAND CENTER",
        subtitle=f"Listening on http://{host}:{port}  │  Press Ctrl+C to stop",
        right="LIVE API",
        width=84,
    ))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
