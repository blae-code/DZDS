"""Ad Aspera · DZDS Web Tactical Command Center (HTTP + REST API + PWA + Off-LAN Share Studio).

Provides a zero-external-dependency web server, Progressive Web App (PWA), and JSON API for
inspecting, simulating, and sharing the Nasdara / Chernarus+ living sandbox:
  - Interactive 16.4x16.4 km Vector Cartographic Map (zones, patrol waypoints, road spots,
    exclusion zones, war party routes, quest vectors, personal pins, and distance/flight-time ruler)
  - War Ledger & 5x5 Faction Diplomacy Matrix + per-user in-memory Turn & Skirmish Simulator
  - Front Plan (Barter Traders & Live Quests) + Refugee Arrival Kit & Aircraft Inspector
  - Mod Loadout Registry (Tier 1..4) with one-click Godlike panel string copy
  - GM Telemetry (.ADM stream, Open-Country Encounter Audit, and Radio Bulletin Studio)
  - Full PWA Support (Web App Manifest, Service Worker offline cache, generated crisp PNG/SVG
    icons, app shortcuts, install prompt & platform-specific install/run instructions)
  - Off-LAN Share Link Studio (token-authenticated invite links, optional Cloudflare Quick Tunnel
    or custom external URL / Tailscale Funnel, and portable single-file HTML export)
  - Per-User Persistent Preferences, Settings, Pinned Sites, Field Notes & Custom Map Pins
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import random
import re
import secrets
import shutil
import struct
import subprocess
import sys
import threading
import time
import zlib
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

import active  # noqa: E402
import arrivals  # noqa: E402
import dzds_profile  # noqa: E402
import encounter_audit  # noqa: E402
import campaign_gen  # noqa: E402
import front_plan  # noqa: E402
import modstring  # noqa: E402
import patrol_gen  # noqa: E402
import status as status_mod  # noqa: E402
import ui  # noqa: E402
import zones as zmod  # noqa: E402
from .adm import parse_line  # noqa: E402
from .ledger import STATE, WarLedger  # noqa: E402
from . import survival_goals  # noqa: E402
from . import companions  # noqa: E402


PWA_VERSION = "2026.10.24-v2"
USER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{3,64}$")

DEFAULT_PREFS: dict[str, Any] = {
    "callsign": "Survivor",
    "faction": "Settlers",
    "launcher": "auto",          # "auto", "linux-dzgui", "windows-dzsa"
    "default_map": "nasdara",    # "nasdara", "chernarusplus"
    "default_view": -1,          # -1 = remember last view, 0..5 = fixed tab
    "last_view": 0,
    "theme": "obsidian",         # "obsidian", "badlands", "phosphor", "high-contrast"
    "density": "standard",       # "compact", "standard", "comfortable"
    "units": "metric",           # "metric", "imperial"
    "grid_format": "alpha",      # "alpha", "meters", "km"
    "always_show_labels": False,
    "auto_refresh_sec": 0,       # 0 = off, 15, 30, 60
    "preferred_archetype": "bush_pilot",
    "layers": {
        "zones": True,
        "patrols": True,
        "arrivals": True,
        "quests": True,
        "exclusions": False,
        "pins": True,
    },
    "camera": {
        "nasdara": {"x": 8192.0, "z": 8192.0, "zoom": 1.05, "selected_site": "Settler Haven"},
        "chernarusplus": {"x": 7680.0, "z": 7680.0, "zoom": 1.05, "selected_site": ""},
    },
    "pinned_sites": [],
    "site_notes": {},
    "custom_pins": [],
    "checklist": {
        "installed_pwa": False,
        "configured_profile": False,
        "pinned_stronghold": False,
        "checked_column": False,
        "copied_server_addr": False,
    },
    "updated_at": "",
}


def sanitize_user_id(raw: str | None) -> str:
    """Validate and normalize a per-user profile identifier."""
    if not raw or not isinstance(raw, str):
        return "operator"
    cleaned = raw.strip()
    if USER_ID_RE.match(cleaned):
        return cleaned
    return "operator"


def _sanitize_prefs(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge and sanitize incoming user preferences against DEFAULT_PREFS."""
    out = copy.deepcopy(DEFAULT_PREFS)
    for k, v in base.items():
        if k in out and not isinstance(out[k], dict):
            out[k] = copy.deepcopy(v)
        elif k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k].update(copy.deepcopy(v))

    if not isinstance(updates, dict):
        return out

    if "callsign" in updates and isinstance(updates["callsign"], str):
        out["callsign"] = updates["callsign"].strip()[:40] or "Survivor"
    if "faction" in updates and updates["faction"] in (*ui.FACTION_ORDER, "Settlers"):
        out["faction"] = str(updates["faction"])
    if "launcher" in updates and updates["launcher"] in ("auto", "linux-dzgui", "windows-dzsa"):
        out["launcher"] = str(updates["launcher"])
    if "default_map" in updates and updates["default_map"] in ("nasdara", "chernarusplus"):
        out["default_map"] = str(updates["default_map"])
    if "default_view" in updates:
        try:
            dv = int(updates["default_view"])
            if -1 <= dv <= 6:
                out["default_view"] = dv
        except (TypeError, ValueError):
            pass
    if "last_view" in updates:
        try:
            lv = int(updates["last_view"])
            if 0 <= lv <= 6:
                out["last_view"] = lv
        except (TypeError, ValueError):
            pass
    if "theme" in updates and updates["theme"] in ("obsidian", "badlands", "phosphor", "high-contrast"):
        out["theme"] = str(updates["theme"])
    if "density" in updates and updates["density"] in ("compact", "standard", "comfortable"):
        out["density"] = str(updates["density"])
    if "units" in updates and updates["units"] in ("metric", "imperial"):
        out["units"] = str(updates["units"])
    if "grid_format" in updates and updates["grid_format"] in ("alpha", "meters", "km"):
        out["grid_format"] = str(updates["grid_format"])
    if "always_show_labels" in updates:
        out["always_show_labels"] = bool(updates["always_show_labels"])
    if "auto_refresh_sec" in updates:
        try:
            ar = int(updates["auto_refresh_sec"])
            if ar in (0, 15, 30, 60):
                out["auto_refresh_sec"] = ar
        except (TypeError, ValueError):
            pass
    if "preferred_archetype" in updates and isinstance(updates["preferred_archetype"], str):
        out["preferred_archetype"] = updates["preferred_archetype"].strip()[:40]

    if isinstance(updates.get("layers"), dict):
        for lk in ("zones", "patrols", "arrivals", "quests", "exclusions", "pins"):
            if lk in updates["layers"]:
                out["layers"][lk] = bool(updates["layers"][lk])

    if isinstance(updates.get("camera"), dict):
        for mname in ("nasdara", "chernarusplus"):
            cam_in = updates["camera"].get(mname)
            if isinstance(cam_in, dict):
                cam_out = dict(out["camera"].get(mname) or {})
                for coord_k in ("x", "z"):
                    if coord_k in cam_in:
                        try:
                            cam_out[coord_k] = round(max(-4096.0, min(20480.0, float(cam_in[coord_k]))), 1)
                        except (TypeError, ValueError):
                            pass
                if "zoom" in cam_in:
                    try:
                        cam_out["zoom"] = round(max(0.5, min(12.0, float(cam_in["zoom"]))), 3)
                    except (TypeError, ValueError):
                        pass
                if "selected_site" in cam_in and isinstance(cam_in["selected_site"], str):
                    cam_out["selected_site"] = cam_in["selected_site"].strip()[:60]
                out["camera"][mname] = cam_out

    if isinstance(updates.get("pinned_sites"), list):
        pins = []
        for item in updates["pinned_sites"][:50]:
            if isinstance(item, str) and item.strip():
                val = item.strip()[:60]
                if val not in pins:
                    pins.append(val)
        out["pinned_sites"] = pins

    if isinstance(updates.get("site_notes"), dict):
        notes: dict[str, str] = {}
        for k, v in list(updates["site_notes"].items())[:60]:
            if isinstance(k, str) and isinstance(v, str):
                ks = k.strip()[:60]
                vs = v.strip()[:600]
                if ks and vs:
                    notes[ks] = vs
        out["site_notes"] = notes

    if isinstance(updates.get("custom_pins"), list):
        cpins = []
        for raw_pin in updates["custom_pins"][:40]:
            if not isinstance(raw_pin, dict):
                continue
            try:
                px = round(max(0.0, min(16384.0, float(raw_pin.get("x", 8192.0)))), 1)
                pz = round(max(0.0, min(16384.0, float(raw_pin.get("z", 8192.0)))), 1)
            except (TypeError, ValueError):
                continue
            label = str(raw_pin.get("label") or "Waypoint").strip()[:48] or "Waypoint"
            pid = str(raw_pin.get("id") or f"pin_{len(cpins) + 1}").strip()[:32]
            pmap = str(raw_pin.get("map") or "nasdara")
            if pmap not in ("nasdara", "chernarusplus"):
                pmap = "nasdara"
            pcol = str(raw_pin.get("color") or "#68c0d0").strip()[:16]
            if not re.match(r"^#[0-9a-fA-F]{3,8}$", pcol):
                pcol = "#68c0d0"
            cpins.append({"id": pid, "label": label, "x": px, "z": pz, "map": pmap, "color": pcol})
        out["custom_pins"] = cpins

    if isinstance(updates.get("checklist"), dict):
        for ck in out["checklist"]:
            if ck in updates["checklist"]:
                out["checklist"][ck] = bool(updates["checklist"][ck])

    out["updated_at"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


class UserProfileStore:
    """Persistent per-user preferences and settings stored in gm_state/web_profiles.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "gm_state" / "web_profiles.json")
        self._lock = threading.Lock()
        self._profiles: dict[str, dict[str, Any]] | None = None

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._profiles is not None:
            return self._profiles
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("profiles"), dict):
                    self._profiles = data["profiles"]
                    return self._profiles
            except Exception:
                pass
        self._profiles = {}
        return self._profiles

    def _save(self) -> None:
        profiles = self._load()
        # Cap total stored profiles to prevent unbounded growth
        if len(profiles) > 200:
            keys = sorted(profiles.keys(), key=lambda k: profiles[k].get("updated_at", ""))
            for old_k in keys[:-200]:
                if old_k != "operator":
                    profiles.pop(old_k, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "profiles": profiles}
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def get(self, user_id: str) -> dict[str, Any]:
        uid = sanitize_user_id(user_id)
        with self._lock:
            profiles = self._load()
            stored = profiles.get(uid) or {}
            return _sanitize_prefs(stored, {})

    def update(self, user_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        uid = sanitize_user_id(user_id)
        with self._lock:
            profiles = self._load()
            current = profiles.get(uid) or {}
            merged = _sanitize_prefs(current, updates)
            profiles[uid] = merged
            self._save()
            return copy.deepcopy(merged)

    def reset(self, user_id: str) -> dict[str, Any]:
        uid = sanitize_user_id(user_id)
        with self._lock:
            profiles = self._load()
            fresh = _sanitize_prefs({}, {})
            profiles[uid] = fresh
            self._save()
            return copy.deepcopy(fresh)


class ShareManager:
    """Manages off-LAN share links and optional live tunnel subprocess (cloudflared / custom URL)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ROOT / "gm_state" / "share_links.json")
        self._lock = threading.Lock()
        self._links: dict[str, dict[str, Any]] | None = None
        self.active_public_url: str = ""
        self.tunnel_provider: str = ""
        self._tunnel_proc: subprocess.Popen | None = None
        self._tunnel_error: str = ""

    def _load(self) -> dict[str, dict[str, Any]]:
        if self._links is not None:
            return self._links
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("links"), dict):
                    self._links = data["links"]
                    if not self.active_public_url and isinstance(data.get("active_public_url"), str):
                        self.active_public_url = data["active_public_url"]
                    return self._links
            except Exception:
                pass
        self._links = {}
        return self._links

    def _save(self) -> None:
        links = self._load()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "active_public_url": self.active_public_url,
            "links": links,
        }
        self.path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def create_link(
        self,
        label: str = "Off-LAN Squad Invite",
        public_url: str = "",
        expires_hours: float | None = None,
        default_prefs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        clean_label = (label or "Off-LAN Squad Invite").strip()[:60] or "Off-LAN Squad Invite"
        clean_url = (public_url or "").strip().rstrip("/")
        if clean_url and not (clean_url.startswith("http://") or clean_url.startswith("https://")):
            clean_url = "https://" + clean_url
        with self._lock:
            links = self._load()
            if clean_url:
                self.active_public_url = clean_url
            link_id = "s_" + secrets.token_hex(4)
            token = secrets.token_urlsafe(18)
            now = dt.datetime.now(dt.timezone.utc)
            exp = (
                (now + dt.timedelta(hours=float(expires_hours))).strftime("%Y-%m-%dT%H:%M:%SZ")
                if expires_hours and float(expires_hours) > 0
                else None
            )
            base = clean_url or self.active_public_url or ""
            entry = {
                "id": link_id,
                "token": token,
                "label": clean_label,
                "public_url": base,
                "app_url": f"{base}/?share={token}" if base else f"/?share={token}",
                "portal_url": f"{base}/portal?share={token}" if base else f"/portal?share={token}",
                "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "expires_at": exp,
                "default_prefs": _sanitize_prefs({}, default_prefs) if isinstance(default_prefs, dict) else None,
                "visits": 0,
            }
            links[link_id] = entry
            self._save()
            return copy.deepcopy(entry)

    def ensure_default_link(self, public_url: str = "") -> dict[str, Any]:
        with self._lock:
            links = self._load()
            if public_url:
                self.active_public_url = public_url.strip().rstrip("/")
            for entry in links.values():
                if not self._is_expired(entry):
                    if self.active_public_url and not entry.get("public_url"):
                        entry["public_url"] = self.active_public_url
                        self._save()
                    return copy.deepcopy(entry)
        return self.create_link(label="Default Off-LAN Link", public_url=public_url)

    def revoke_link(self, id_or_token: str) -> bool:
        if not id_or_token:
            return False
        with self._lock:
            links = self._load()
            if id_or_token == "*":
                links.clear()
                self._save()
                return True
            target_key = None
            for k, v in links.items():
                if k == id_or_token or secrets.compare_digest(str(v.get("token", "")), str(id_or_token)):
                    target_key = k
                    break
            if target_key:
                links.pop(target_key, None)
                self._save()
                return True
            return False

    @staticmethod
    def _is_expired(entry: dict[str, Any]) -> bool:
        exp = entry.get("expires_at")
        if not exp:
            return False
        try:
            exp_dt = dt.datetime.strptime(exp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
            return dt.datetime.now(dt.timezone.utc) >= exp_dt
        except Exception:
            return False

    def validate_token(self, token: str | None, record_visit: bool = False) -> dict[str, Any] | None:
        if not token or not isinstance(token, str) or len(token) < 8:
            return None
        with self._lock:
            links = self._load()
            for entry in links.values():
                tok = str(entry.get("token", ""))
                if tok and secrets.compare_digest(tok, token):
                    if self._is_expired(entry):
                        return None
                    if record_visit:
                        entry["visits"] = int(entry.get("visits", 0)) + 1
                        self._save()
                    return copy.deepcopy(entry)
        return None

    def allowed_external_hosts(self) -> set[str]:
        hosts: set[str] = set()
        with self._lock:
            links = self._load()
            urls = [self.active_public_url] + [str(v.get("public_url") or "") for v in links.values()]
            for u in urls:
                if u:
                    netloc = urlparse(u).netloc
                    if netloc:
                        hosts.add(netloc)
        return hosts

    def start_tunnel(self, port: int, provider: str = "cloudflared", custom_url: str = "") -> dict[str, Any]:
        if provider == "custom" or custom_url.strip():
            clean = custom_url.strip().rstrip("/")
            if clean and not (clean.startswith("http://") or clean.startswith("https://")):
                clean = "https://" + clean
            with self._lock:
                self.active_public_url = clean
                self.tunnel_provider = "custom" if clean else ""
                self._tunnel_error = ""
                self._save()
            self.ensure_default_link(public_url=clean)
            return self.status(port=port, is_operator=True)

        cf_bin = shutil.which("cloudflared")
        if not cf_bin:
            self._tunnel_error = "cloudflared binary not found on PATH; enter a custom external URL or Tailscale Funnel address."
            self.ensure_default_link()
            return self.status(port=port, is_operator=True)

        self.stop_tunnel()
        self._tunnel_error = ""
        self.tunnel_provider = "cloudflared"
        url_found = threading.Event()

        try:
            proc = subprocess.Popen(
                [cf_bin, "tunnel", "--url", f"http://127.0.0.1:{port}", "--no-autoupdate"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except Exception as exc:
            self._tunnel_error = f"Failed to launch cloudflared: {exc}"
            self.tunnel_provider = ""
            return self.status(port=port, is_operator=True)

        self._tunnel_proc = proc
        url_re = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")

        def _reader() -> None:
            assert proc.stdout is not None
            for line in proc.stdout:
                m = url_re.search(line)
                if m:
                    with self._lock:
                        self.active_public_url = m.group(0)
                        self._save()
                    url_found.set()
                elif "failed" in line.lower() or "error" in line.lower():
                    if not self.active_public_url:
                        self._tunnel_error = line.strip()[:160]

        t = threading.Thread(target=_reader, daemon=True)
        t.start()
        url_found.wait(timeout=4.5)
        self.ensure_default_link(public_url=self.active_public_url)
        return self.status(port=port, is_operator=True)

    def stop_tunnel(self) -> dict[str, Any]:
        proc = self._tunnel_proc
        self._tunnel_proc = None
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if self.tunnel_provider == "cloudflared":
            self.tunnel_provider = ""
            self.active_public_url = ""
        return self.status(is_operator=True)

    def status(self, port: int = 8787, is_operator: bool = True) -> dict[str, Any]:
        with self._lock:
            links = self._load()
            running = bool(
                (self._tunnel_proc is not None and self._tunnel_proc.poll() is None)
                or (self.tunnel_provider == "custom" and self.active_public_url)
            )
            base_url = self.active_public_url or f"http://127.0.0.1:{port}"
            items = []
            for entry in links.values():
                if self._is_expired(entry):
                    continue
                link_base = entry.get("public_url") or base_url
                tok = entry["token"]
                items.append({
                    "id": entry["id"],
                    "label": entry["label"],
                    "created_at": entry["created_at"],
                    "expires_at": entry.get("expires_at"),
                    "visits": entry.get("visits", 0),
                    "public_url": link_base,
                    "token": tok if is_operator else (tok[:6] + "…"),
                    "app_url": f"{link_base}/?share={tok}" if is_operator else "",
                    "portal_url": f"{link_base}/portal?share={tok}" if is_operator else "",
                    "default_prefs": entry.get("default_prefs"),
                })
            return {
                "tunnel_running": running,
                "tunnel_provider": self.tunnel_provider or ("cloudflared" if running else ""),
                "active_public_url": self.active_public_url,
                "tunnel_error": self._tunnel_error,
                "cloudflared_available": bool(shutil.which("cloudflared")),
                "tailscale_available": bool(shutil.which("tailscale")),
                "links": items if is_operator else [],
                "link_count": len(items),
            }


# ---- Pure-Python Crisp PNG & SVG PWA Icons + Manifest + Service Worker -----------

ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" rx="96" fill="#0b0e11"/>
  <rect x="28" y="28" width="456" height="456" rx="76" fill="#11151a" stroke="#dedcd6" stroke-opacity="0.16" stroke-width="6"/>
  <circle cx="256" cy="256" r="168" fill="none" stroke="#d4af4f" stroke-opacity="0.45" stroke-width="8" stroke-dasharray="18 10"/>
  <circle cx="256" cy="256" r="124" fill="none" stroke="#68c0d0" stroke-opacity="0.6" stroke-width="4"/>
  <line x1="256" y1="56" x2="256" y2="116" stroke="#68c0d0" stroke-width="10" stroke-linecap="round"/>
  <line x1="256" y1="396" x2="256" y2="456" stroke="#dedcd6" stroke-opacity="0.35" stroke-width="6" stroke-linecap="round"/>
  <line x1="56" y1="256" x2="116" y2="256" stroke="#dedcd6" stroke-opacity="0.35" stroke-width="6" stroke-linecap="round"/>
  <line x1="396" y1="256" x2="456" y2="256" stroke="#dedcd6" stroke-opacity="0.35" stroke-width="6" stroke-linecap="round"/>
  <polygon points="256,126 352,350 256,302 160,350" fill="#db5c4b"/>
  <polygon points="256,162 316,316 256,284 196,316" fill="#d4af4f"/>
  <circle cx="256" cy="256" r="14" fill="#0b0e11" stroke="#dedcd6" stroke-width="5"/>
</svg>
"""

_ICON_CACHE: dict[tuple[int, bool], bytes] = {}


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(tag + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)


def build_pwa_icon_png(size: int = 192, maskable: bool = False) -> bytes:
    """Generate a valid RGBA PNG icon at exact pixel dimensions with zero external libraries."""
    key = (size, maskable)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    stride = 1 + size * 4
    bg_row = b"\x00" + (b"\x0b\x0e\x11\xff" * size)
    buf = bytearray(bg_row * size)

    cx = (size - 1) / 2.0
    cy = (size - 1) / 2.0
    scale = 0.78 if maskable else 0.90
    outer_r = (size / 2.0) * scale
    ring_r = outer_r * 0.78
    inner_r = outer_r * 0.56
    ring_thick = max(2.0, size * 0.028)
    cross_thick = max(1.5, size * 0.018)

    def set_px(x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < size and 0 <= y < size:
            idx = y * stride + 1 + x * 4
            buf[idx] = r
            buf[idx + 1] = g
            buf[idx + 2] = b
            buf[idx + 3] = 255

    # Draw subtle panel frame
    pad = int(size * (0.14 if maskable else 0.07))
    for y in range(pad, size - pad):
        for x in (pad, pad + 1, size - pad - 1, size - pad - 2):
            set_px(x, y, 48, 58, 66)
    for x in range(pad, size - pad):
        for y in (pad, pad + 1, size - pad - 1, size - pad - 2):
            set_px(x, y, 48, 58, 66)

    # Draw compass rings (gold outer ring + cyan inner ring)
    for deg in range(720):
        rad = math.radians(deg * 0.5)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        if (deg // 12) % 2 == 0:
            for dr in (-1.0, -0.5, 0.0, 0.5, 1.0):
                rr = ring_r + dr * (ring_thick * 0.5)
                set_px(int(round(cx + cos_a * rr)), int(round(cy + sin_a * rr)), 212, 175, 79)
        for dr in (-0.5, 0.0, 0.5):
            rr2 = inner_r + dr * (ring_thick * 0.35)
            set_px(int(round(cx + cos_a * rr2)), int(round(cy + sin_a * rr2)), 104, 192, 208)

    # North tick (cyan) and cardinal ticks
    tick_len = int(size * 0.11)
    half_t = max(1, int(cross_thick))
    for y in range(int(cy - ring_r - tick_len * 0.4), int(cy - inner_r + tick_len * 0.3)):
        for dx in range(-half_t, half_t + 1):
            set_px(int(cx) + dx, y, 104, 192, 208)

    # Center coral chevron / tactical delta
    top_y = int(cy - inner_r * 0.78)
    bot_y = int(cy + inner_r * 0.72)
    span_h = max(1, bot_y - top_y)
    for y in range(top_y, bot_y + 1):
        t = (y - top_y) / span_h
        half_w = int(t * inner_r * 0.68)
        notch_y = top_y + int(span_h * 0.74)
        notch_w = int(((y - notch_y) / max(1, bot_y - notch_y)) * half_w * 0.75) if y > notch_y else 0
        for x in range(int(cx) - half_w, int(cx) + half_w + 1):
            if abs(x - int(cx)) >= notch_w:
                if abs(x - int(cx)) < half_w * 0.48 and 0.22 < t < 0.72:
                    set_px(x, y, 212, 175, 79)  # inner gold core
                else:
                    set_px(x, y, 219, 92, 75)   # outer coral delta

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(buf), level=6)
    png = b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", ihdr) + _png_chunk(b"IDAT", idat) + _png_chunk(b"IEND", b"")
    _ICON_CACHE[key] = png
    return png


def build_manifest(share_token: str = "") -> dict[str, Any]:
    """Build the Web App Manifest JSON, preserving share_token for off-LAN PWA installs."""
    q = f"?share={share_token}" if share_token else ""
    amp_q = f"&share={share_token}" if share_token else ""
    return {
        "id": f"/{q}",
        "name": "Ad Aspera · DZDS Tactical Command Center",
        "short_name": "Ad Aspera",
        "description": (
            "Tactical Command Center, Living Sandbox Map, War Ledger, Off-LAN Share Studio, "
            "and Survivor's Guide for the Ad Aspera DayZ PvE world."
        ),
        "start_url": f"/{q}",
        "scope": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
        "background_color": "#0b0e11",
        "theme_color": "#0b0e11",
        "orientation": "any",
        "categories": ["games", "utilities", "navigation"],
        "prefer_related_applications": False,
        "icons": [
            {
                "src": f"/icon.svg{q}",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
            {
                "src": f"/icon-192.png{q}",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": f"/icon-512.png{q}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": f"/icon-maskable-512.png{q}",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
            {
                "src": f"/icon-180.png{q}",
                "sizes": "180x180",
                "type": "image/png",
                "purpose": "any",
            },
        ],
        "shortcuts": [
            {
                "name": "Tactical Map",
                "short_name": "Map",
                "description": "Open the 16.4x16.4 km Nasdara / Chernarus+ operational map",
                "url": f"/?view=0{amp_q}",
                "icons": [{"src": f"/icon-192.png{q}", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "War Ledger & Diplomacy",
                "short_name": "War Ledger",
                "description": "Inspect faction strength, standing, and simulate turns",
                "url": f"/?view=1{amp_q}",
                "icons": [{"src": f"/icon-192.png{q}", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "Campaign & Arrivals",
                "short_name": "Campaign",
                "description": "Barter traders, live front-line quests, and arrival kit simulator",
                "url": f"/?view=2{amp_q}",
                "icons": [{"src": f"/icon-192.png{q}", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "Basebuilding & Homestead Guide",
                "short_name": "Basebuilding",
                "description": "Visual blueprints, BOM calculator, and all vanilla + modded basebuilding recipes",
                "url": f"/?view=5{amp_q}",
                "icons": [{"src": f"/icon-192.png{q}", "sizes": "192x192", "type": "image/png"}],
            },
            {
                "name": "Survivor's Guide",
                "short_name": "Guide",
                "description": "Read-only field manual for joining and surviving Ad Aspera",
                "url": f"/portal{q}",
                "icons": [{"src": f"/icon-192.png{q}", "sizes": "192x192", "type": "image/png"}],
            },
        ],
        "screenshots": [
            {
                "src": f"/preview.png{q}",
                "sizes": "512x512",
                "type": "image/png",
                "form_factor": "wide",
                "label": "Ad Aspera Tactical Command Center",
            },
            {
                "src": f"/preview.png{q}",
                "sizes": "512x512",
                "type": "image/png",
                "form_factor": "narrow",
                "label": "Ad Aspera Mobile Field View",
            },
        ],
    }


SERVICE_WORKER_JS = f"""/* Ad Aspera · DZDS Service Worker ({PWA_VERSION}) */
const CACHE_NAME = 'dzds-pwa-{PWA_VERSION}';
const SHELL_URLS = [
  '/',
  '/portal',
  '/manifest.webmanifest',
  '/icon.svg',
  '/icon-192.png',
  '/icon-512.png',
  '/icon-maskable-512.png',
  '/icon-180.png',
  '/preview.png'
];

self.addEventListener('install', event => {{
  event.waitUntil((async () => {{
    const cache = await caches.open(CACHE_NAME);
    await Promise.allSettled(SHELL_URLS.map(u => cache.add(u)));
    await self.skipWaiting();
  }})());
}});

self.addEventListener('activate', event => {{
  event.waitUntil((async () => {{
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    await self.clients.claim();
  }})());
}});

self.addEventListener('message', event => {{
  const data = event.data || {{}};
  if (data.type === 'SKIP_WAITING') {{
    self.skipWaiting();
  }} else if (data.type === 'CACHE_STATE' && data.payload) {{
    caches.open(CACHE_NAME).then(cache => {{
      const resp = new Response(JSON.stringify(data.payload), {{
        headers: {{ 'Content-Type': 'application/json; charset=utf-8', 'X-DZDS-Offline': '1' }}
      }});
      cache.put('/api/state', resp);
    }});
  }}
}});

self.addEventListener('fetch', event => {{
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Network-first with offline cache fallback for API GETs
  if (url.pathname.startsWith('/api/')) {{
    event.respondWith((async () => {{
      const cache = await caches.open(CACHE_NAME);
      try {{
        const netResp = await fetch(req);
        if (netResp && netResp.ok) {{
          cache.put(req, netResp.clone());
          if (url.pathname === '/api/state') {{
            cache.put('/api/state', netResp.clone());
          }}
        }}
        return netResp;
      }} catch (err) {{
        const cached = (await cache.match(req)) || (url.pathname === '/api/state' ? await cache.match('/api/state') : null);
        if (cached) {{
          const body = await cached.text();
          return new Response(body, {{
            status: 200,
            headers: {{ 'Content-Type': 'application/json; charset=utf-8', 'X-DZDS-Offline': '1' }}
          }});
        }}
        return new Response(JSON.stringify({{ error: 'offline', offline: true }}), {{
          status: 503,
          headers: {{ 'Content-Type': 'application/json; charset=utf-8' }}
        }});
      }}
    }})());
    return;
  }}

  // Navigation requests ('/' and '/portal'): Network-first with cached shell fallback
  if (req.mode === 'navigate' || url.pathname === '/' || url.pathname === '/index.html' || url.pathname.startsWith('/portal')) {{
    event.respondWith((async () => {{
      const cache = await caches.open(CACHE_NAME);
      try {{
        const netResp = await fetch(req);
        if (netResp && netResp.ok) {{
          const canonical = url.pathname.startsWith('/portal') ? '/portal' : '/';
          cache.put(canonical, netResp.clone());
        }}
        return netResp;
      }} catch (err) {{
        const canonical = url.pathname.startsWith('/portal') ? '/portal' : '/';
        return (await cache.match(req)) || (await cache.match(canonical)) || (await cache.match('/'));
      }}
    }})());
    return;
  }}

  // Static assets (icons, manifest, preview.png): Cache-first with background refresh
  event.respondWith((async () => {{
    const cache = await caches.open(CACHE_NAME);
    const cached = (await cache.match(req)) || (await cache.match(url.pathname));
    const fetchPromise = fetch(req).then(netResp => {{
      if (netResp && netResp.ok) {{
        cache.put(url.pathname, netResp.clone());
      }}
      return netResp;
    }}).catch(() => null);
    return cached || (await fetchPromise) || new Response('', {{ status: 404 }});
  }})());
}});
"""


_BASEBUILDING_CACHE: tuple[tuple[int, ...], dict[str, Any]] | None = None


def _read_json_safe(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            pass
    return copy.deepcopy(default) if default else {}


def build_basebuilding_guide() -> dict[str, Any]:
    """Build the authoritative Basebuilding & Homesteading guide backed by live server configs."""
    global _BASEBUILDING_CACHE
    cfg_paths = [
        ROOT / "server" / "profiles" / "RaG_Core" / "Configs" / "RaG_BaseBuilding" / "RaG_BaseBuilding.json",
        ROOT / "server" / "profiles" / "RaG_Core" / "Configs" / "RaG_Hunting_Cabin" / "RaG_Hunting_Cabin.json",
        ROOT / "server" / "profiles" / "RaG_Core" / "Configs" / "RaG_Core" / "DigitalCodeLock.json",
        ROOT / "server" / "profiles" / "MMG_Storage" / "MMG_Config.json",
        ROOT / "server" / "profiles" / "Zenarchist" / "ZenStaticCarWorkbenchConfig.json",
        ROOT / "server" / "profiles" / "ImmersivePlacing" / "PlacementLifetime.json",
        ROOT / "server" / "profiles" / "BetterHarvest" / "BetterHarvest_Config.json",
        ROOT / "server" / "mpmissions" / "dayzOffline.nasdara" / "CookZ" / "CookZ_V003.json",
    ]
    sig = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in cfg_paths)
    if _BASEBUILDING_CACHE and _BASEBUILDING_CACHE[0] == sig:
        return copy.deepcopy(_BASEBUILDING_CACHE[1])

    rag_bb = _read_json_safe(cfg_paths[0])
    rag_cabin = _read_json_safe(cfg_paths[1])
    rag_lock = _read_json_safe(cfg_paths[2])
    mmg_cfg = _read_json_safe(cfg_paths[3])
    zen_wb = _read_json_safe(cfg_paths[4])
    placing_cfg = _read_json_safe(cfg_paths[5])
    harvest_cfg = _read_json_safe(cfg_paths[6])
    cookz_cfg = _read_json_safe(cfg_paths[7])

    kit_planks = int(round(float(rag_bb.get("PlanksPerKitCraft", 4.0))))
    kit_nails = int(round(float(rag_bb.get("NailsPerKitCraft", 10.0))))
    build_time_s = float(rag_bb.get("BaseBuildTime") or rag_bb.get("BuildTime") or 8.0)
    dismantle_time_s = float(rag_bb.get("BaseDismantleTime") or rag_bb.get("DismantleTime") or 15.0)
    part_costs_map = {
        (p.get("Part") or p.get("PartName")): {
            "logs": int(round(float(p.get("LOGS") or p.get("Logs") or 0))),
            "planks": int(round(float(p.get("PLANKS") or p.get("Planks") or 0))),
            "nails": int(round(float(p.get("NAILS") or p.get("Nails") or 0))),
            "metal": int(round(float(p.get("METALSHEETS") or p.get("MetalSheets") or 0))),
        }
        for p in (rag_bb.get("PartCosts") or [])
        if isinstance(p, dict) and (p.get("Part") or p.get("PartName"))
    }

    def _pc(name: str, logs: int = 0, planks: int = 0, nails: int = 0, metal: int = 0) -> dict[str, int]:
        return part_costs_map.get(name, {"logs": logs, "planks": planks, "nails": nails, "metal": metal})

    def _sum_parts(*parts: tuple[str, dict[str, int]], include_kit: bool = True) -> dict[str, int]:
        totals = {
            "logs": 0,
            "planks": kit_planks if include_kit else 0,
            "nails": kit_nails if include_kit else 0,
            "metal": 0,
            "stones": 0,
            "wire": 0,
            "rope": 0,
            "sticks": 0,
            "long_sticks": 0,
            "tarp": 0,
            "leather": 0,
            "camo_net": 0,
        }
        for _, cost in parts:
            for k in ("logs", "planks", "nails", "metal"):
                totals[k] += int(cost.get(k, 0))
        return {k: v for k, v in totals.items() if v > 0}

    cabin_kit_planks = int(rag_cabin.get("PlanksNeededCount", 10))
    cabin_kit_nails = int(rag_cabin.get("NailsNeededCount", 50))
    wb_nails = int(zen_wb.get("CraftNailsRequired", 60))
    wb_metal = int(zen_wb.get("CraftMetalRequired", 5))
    flag_radius_m = float(placing_cfg.get("flagRadius", 60.0))
    unflagged_h = round(float(placing_cfg.get("placedItemLifetimeSeconds", 86400)) / 3600)
    flagged_days = round(float(placing_cfg.get("flagZonePlacedItemLifetimeSeconds", 604800)) / 86400)

    progression = [
        {
            "stage": 1,
            "title": "Camp & Cache",
            "subtitle": "First 48 Hours in the Sand",
            "summary": "Pitch an Improvised Stick/Tarp/Leather Shelter (100 slots), build a 16-stone Camp Oven, and bury a Wooden Crate or Leather Sack stash.",
            "milestone_items": ["ShelterKit", "WoodenCrate", "UndergroundStash", "Fireplace (Stone Oven)"],
            "lifetime": "14 days (Underground Stash) · 45 days (Shelters/Tents)",
        },
        {
            "stage": 2,
            "title": "Home on Wheels",
            "subtitle": "Mobile Nomad Rig",
            "summary": "Claim an Apocalypse Truck, Semi Truck, or Loaf Van and cloak it when parked with a CamoNet via CarCover.",
            "milestone_items": ["MBM_ApocalypseTruck", "CamoNet (CarCover)", "ZenSleepingBag_*"],
            "lifetime": "Persistent while covered with CarCover",
        },
        {
            "stage": 3,
            "title": "First Canyon Shelter",
            "subtitle": "RaG Modular Snap-Grid",
            "summary": f"Craft an RaG Basebuilding Book or combine {kit_planks} Planks + {kit_nails} Nails into modular Foundation, Wall, Door, and Roof kits.",
            "milestone_items": ["RaG_BB_Book", "RaG_BB_FoundationKit", "RaG_BB_WallKit", "RaG_BB_DoorKit", "RaG_BB_RoofKit"],
            "lifetime": "14 days base · 40 days under raised Territory Flag",
        },
        {
            "stage": 4,
            "title": "The Hunting Cabin",
            "subtitle": "Signature Homestead Milestone",
            "summary": "Construct the lockable log Hunting Cabin with 8 openable windows, built-in stone fireplace, and wall-switched interior & party lights.",
            "milestone_items": ["rag_hunting_cabin_kit", "rag_hunting_cabin", "DigitalCodeLock"],
            "lifetime": "45 days · Full material & kit refund on dismantle",
        },
        {
            "stage": 5,
            "title": "Fortified Compound & Workshop",
            "subtitle": "Storage, Mechanics & Livestock",
            "summary": "Outfit your compound with MMG Gun Walls, 300-slot Supply Crates, lockable Equipment Lockers, Zens Car Workbench, Horse Stables, and Garden Plots.",
            "milestone_items": ["Zen_CarWorkbenchKit", "mmg_supplycrate_level1", "mmg_gun_wall_metal", "Saddle", "GardenPlot"],
            "lifetime": "10–28 days base · Refreshed by Territory Flag",
        },
        {
            "stage": 6,
            "title": "Settlement Network & @DZDS Respawn",
            "subtitle": "Territory Flag + Frontier Settler Garrison",
            "summary": f"Raise a Territory Flag ({int(flag_radius_m)}m ImmersivePlacing zone) to unlock @DZDS Base Respawn on death and claim a Frontier Settler garrison on the War Ledger.",
            "milestone_items": ["TerritoryFlagKit", "TerritoryFlag", "Flag_*", "tools/war.py claim"],
            "lifetime": "40-day Flag refresh · Never falls to off-screen AI fighting",
        },
    ]

    recipes: list[dict[str, Any]] = [
        # ---- CATEGORY 1: VANILLA 1.30 PREP, WALLS, TOWERS & FLAG ----
        {
            "id": "van_planks_from_log",
            "name": "Saw Wooden Planks (4×)",
            "classname": "WoodenPlank",
            "category": "vanilla",
            "subcategory": "Material Prep",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "1× Wooden Log + HandSaw / Hacksaw → 4× Wooden Plank",
            "build_tools": ["HandSaw", "Hacksaw", "WoodAxe", "Hatchet"],
            "dismantle_tools": [],
            "lifetime": "7 days (loose pile)",
            "slots": "Stack of 10",
            "materials": {"logs": 1},
            "stages": [
                {"name": "Fell Tree", "cost": "Axe / Hatchet on large tree → 1–2× WoodenLog"},
                {"name": "Saw Log", "cost": "1× WoodenLog + HandSaw or Hacksaw → 4× WoodenPlank"},
            ],
            "notes": "Each Wooden Log yields 4 Wooden Planks. Lumber piles around industrial yards can also be sawed directly.",
        },
        {
            "id": "van_improvised_rope",
            "name": "Improvised Rope",
            "classname": "Rope",
            "category": "vanilla",
            "subcategory": "Material Prep",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "6× Rag + 6× Rag  OR  1× Guts + Knife",
            "build_tools": ["Knife (for Guts)"],
            "dismantle_tools": [],
            "lifetime": "8 hours (dropped)",
            "slots": "1×3 inv",
            "materials": {"rope": 1},
            "stages": [
                {"name": "Rag Method", "cost": "6× Rag + 6× Rag → 1× Rope"},
                {"name": "Hunting Method", "cost": "1× Animal Guts + Any Knife → 1× Rope"},
            ],
            "notes": "Essential starter component for Fence Kit, Watchtower Kit, Territory Flag Kit, Shelter Kit, and Horse Bridle.",
        },
        {
            "id": "van_fence_wood",
            "name": "Vanilla Wooden Fence (Full Wall + Platform)",
            "classname": "FenceKit -> Fence",
            "category": "vanilla",
            "subcategory": "Perimeter & Defenses",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "2× Short Stick + 1× Rope",
            "build_tools": ["Shovel / Pickaxe / FarmingHoe (Posts)", "Hammer / Hatchet (Frames & Panels)"],
            "dismantle_tools": ["Hatchet", "Crowbar (from inside)"],
            "lifetime": "45 days",
            "slots": "1× CamoNet + 2× BarbedWire",
            "materials": {"sticks": 2, "rope": 1, "logs": 2, "planks": 14, "nails": 28},
            "stages": [
                {"name": "Fence Kit", "cost": "2× WoodenStick + 1× Rope (reclaimed when posts are driven)"},
                {"name": "Base Posts", "cost": "2× WoodenLog (drive with Shovel, FieldShovel, Pickaxe, or FarmingHoe)"},
                {"name": "Lower & Upper Frames", "cost": "4× WoodenPlank + 8× Nail (2 Planks + 4 Nails each)"},
                {"name": "Lower & Upper Wood Panels", "cost": "10× WoodenPlank + 20× Nail (5 Planks + 10 Nails each)"},
                {"name": "Optional Platform & Stairs", "cost": "Platform: 5 Planks + 15 Nails · Stairs (L/R): 4 Planks + 8 Nails each"},
            ],
            "notes": "Standard wall segment. Add 5 Planks + 15 Nails for an interior firing platform.",
        },
        {
            "id": "van_gate_metal",
            "name": "Vanilla Sheet Metal Gate (Lockable)",
            "classname": "FenceKit -> Fence (Gate)",
            "category": "vanilla",
            "subcategory": "Perimeter & Defenses",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "2× Short Stick + 1× Rope + 1× Metal Wire (Pliers)",
            "build_tools": ["Shovel / Pickaxe (Posts)", "Hammer / Hatchet (Panels)", "Pliers (MetalWire Gate conversion)"],
            "dismantle_tools": ["Pliers (remove wire)", "Hatchet / Crowbar (from inside)"],
            "lifetime": "45 days",
            "slots": "DigitalCodeLock / CombinationLock + CamoNet + 2× BarbedWire",
            "materials": {"sticks": 2, "rope": 1, "logs": 2, "planks": 4, "metal": 6, "nails": 32, "wire": 1},
            "stages": [
                {"name": "Fence Kit & Base Posts", "cost": "2× WoodenStick + 1× Rope + 2× WoodenLog"},
                {"name": "Lower & Upper Frames", "cost": "4× WoodenPlank + 8× Nail"},
                {"name": "Lower & Upper Sheet Metal Panels", "cost": "6× MetalPlate + 24× Nail (3 Metal Sheets + 12 Nails each)"},
                {"name": "Gate Hinge Conversion", "cost": "Attach 1× MetalWire + crimp with Pliers → swings open & accepts DigitalCodeLock"},
            ],
            "notes": "Accepts Vanilla 1.30 DigitalCodeLock, 4-Dial CombinationLock4, or 3-Dial CombinationLock. Infected cannot bash locked doors.",
        },
        {
            "id": "van_watchtower_1lvl",
            "name": "Vanilla Watchtower (1st Story Base + Roof + Stairs)",
            "classname": "WatchtowerKit -> Watchtower (L1)",
            "category": "vanilla",
            "subcategory": "Perimeter & Defenses",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "4× Short Stick + 1× Rope",
            "build_tools": ["Shovel / Pickaxe / FarmingHoe (L1 Posts)", "Hammer / Hatchet (Roof, Stairs & 3 Wall Sides)"],
            "dismantle_tools": ["Hatchet", "Crowbar (from inside)"],
            "lifetime": "45 days",
            "slots": "3× CamoNet + 6× BarbedWire per floor",
            "materials": {"sticks": 4, "rope": 1, "logs": 4, "planks": 47, "nails": 90},
            "stages": [
                {"name": "Watchtower Kit", "cost": "4× WoodenStick + 1× Rope"},
                {"name": "Level 1 Corner Posts", "cost": "4× WoodenLog (drive with Shovel / Pickaxe / FarmingHoe)"},
                {"name": "Level 1 Roof & Stairs", "cost": "Roof: 6 Planks + 10 Nails · Stairs: 5 Planks + 8 Nails"},
                {"name": "3 Wall Sides (Frames + Wood Panels)", "cost": "Frames: 12 Planks + 24 Nails · Wood Panels: 24 Planks + 48 Nails (or 12 Metal Sheets + 60 Nails)"},
            ],
            "notes": "Each of the 3 sides has a Lower & Upper section (2 Planks + 4 Nails per frame; 4 Planks + 8 Nails per wood panel, or 2 Metal Sheets + 10 Nails per metal panel).",
        },
        {
            "id": "van_watchtower_3lvl",
            "name": "Vanilla Watchtower (Full 3-Story Wood Tower)",
            "classname": "WatchtowerKit -> Watchtower (L1-L3)",
            "category": "vanilla",
            "subcategory": "Perimeter & Defenses",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "4× Short Stick + 1× Rope (3 Levels)",
            "build_tools": ["Shovel / Pickaxe (L1 Posts)", "Hammer / Hatchet (L2/L3 Posts, Roofs, Stairs & 9 Wall Sides)"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "45 days",
            "slots": "9× CamoNet + 18× BarbedWire total",
            "materials": {"sticks": 4, "rope": 1, "logs": 12, "planks": 136, "nails": 262},
            "stages": [
                {"name": "Level 1 (Posts + Roof + Stairs + 3 Walls)", "cost": "4× Logs + 47× Planks + 90× Nails"},
                {"name": "Level 2 (Posts + Roof + Stairs + 3 Walls)", "cost": "4× Logs + 47× Planks + 90× Nails (L2/L3 posts built with Hammer/Hatchet)"},
                {"name": "Level 3 (Posts + Roof + 3 Walls)", "cost": "4× Logs + 42× Planks + 82× Nails (no staircase needed above L3)"},
            ],
            "notes": "Commanding Badlands observation post. Upper-story logs are hammered into place rather than dug.",
        },
        {
            "id": "van_territory_flag",
            "name": "Territory Flag Pole (@DZDS Base Respawn Anchor)",
            "classname": "TerritoryFlagKit -> TerritoryFlag",
            "category": "vanilla",
            "subcategory": "Territory & Respawn",
            "mod": "Vanilla 1.30 + @DZDS + Immersive Placing",
            "mod_folder": "@DZDS",
            "kit_recipe": "3× Short Stick + 1× Rope",
            "build_tools": ["SledgeHammer / Pickaxe (Stage 1)", "Shovel / Pickaxe (Stage 2)", "Hammer / Hatchet (Stage 3)"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": f"40-day Flag refresh ({int(flag_radius_m)}m radius)",
            "slots": "1× Flag_*",
            "materials": {"sticks": 3, "rope": 2, "logs": 10, "stones": 32, "nails": 60, "wire": 1},
            "stages": [
                {"name": "Territory Flag Kit", "cost": "3× WoodenStick + 1× Rope"},
                {"name": "Stage 1: Base Post", "cost": "1× WoodenLog (drive with SledgeHammer or Pickaxe)"},
                {"name": "Stage 2: Stone & Timber Support", "cost": "32× Stone (Large Stones) + 6× WoodenLog (build with Shovel, FieldShovel, or Pickaxe)"},
                {"name": "Stage 3: Mast & Hoist Mechanism", "cost": "3× WoodenLog + 60× Nail + 1× MetalWire + 1× Rope (build with Hammer or Hatchet) + attach Flag_*"},
            ],
            "notes": f"Raising a flag on Ad Aspera does TWO things: (1) refreshes structure lifetimes within {int(flag_radius_m)}m (boosting placed items from {unflagged_h}h to {flagged_days}d), and (2) registers your base in DZDSBases.c so you respawn at home when no online friend is nearby.",
        },
        # ---- VANILLA SHELTERS, STORAGE & CAMP ----
        {
            "id": "van_shelter_stick",
            "name": "Improvised Stick Shelter (Camouflaged)",
            "classname": "ShelterKit -> ShelterStick",
            "category": "camp",
            "subcategory": "Vanilla Shelters & Storage",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "4× Short Stick + 1× Rope",
            "build_tools": ["Hands (no tool required once sticks are gathered)", "Knife / Hatchet (harvest sticks)"],
            "dismantle_tools": ["Hands (Pack Shelter)"],
            "lifetime": "45 days",
            "slots": "100 slots (10×10)",
            "materials": {"sticks": 54, "rope": 1, "long_sticks": 4},
            "stages": [
                {"name": "Shelter Kit", "cost": "4× WoodenStick + 1× Rope"},
                {"name": "Shelter Frame", "cost": "4× LongWoodenStick"},
                {"name": "Thatch Canopy", "cost": "50× WoodenStick"},
            ],
            "notes": "Lowest-profile bush shelter in Nasdara's scrub canyons; requires zero nails or saws.",
        },
        {
            "id": "van_shelter_tarp",
            "name": "Improvised Tarp Shelter (Waterproof)",
            "classname": "ShelterKit -> ShelterSite",
            "category": "camp",
            "subcategory": "Vanilla Shelters & Storage",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "4× Short Stick + 1× Rope",
            "build_tools": ["Hands"],
            "dismantle_tools": ["Hands (Pack Shelter)"],
            "lifetime": "45 days",
            "slots": "100 slots (10×10)",
            "materials": {"sticks": 4, "rope": 1, "long_sticks": 4, "tarp": 4},
            "stages": [
                {"name": "Shelter Kit & Frame", "cost": "4× WoodenStick + 1× Rope + 4× LongWoodenStick"},
                {"name": "Tarp Cover", "cost": "4× Fabric (Tarp)"},
            ],
            "notes": "Fast to erect if you find a roll of Tarp (`Fabric`) in industrial sheds.",
        },
        {
            "id": "van_shelter_leather",
            "name": "Improvised Leather Shelter (Insulated)",
            "classname": "ShelterKit -> ShelterLeather",
            "category": "camp",
            "subcategory": "Vanilla Shelters & Storage",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "4× Short Stick + 1× Rope",
            "build_tools": ["Hands"],
            "dismantle_tools": ["Hands (Pack Shelter)"],
            "lifetime": "45 days",
            "slots": "100 slots (10×10)",
            "materials": {"sticks": 4, "rope": 1, "long_sticks": 4, "leather": 8},
            "stages": [
                {"name": "Shelter Kit & Frame", "cost": "4× WoodenStick + 1× Rope + 4× LongWoodenStick"},
                {"name": "Hide Cover", "cost": "8× TannedLeather (tanned from animal pelts + GardenLime in a Barrel)"},
            ],
            "notes": "Blends naturally against Nasdara sandstone cliffs and rocky wadis.",
        },
        {
            "id": "van_wooden_crate",
            "name": "Wooden Crate (Buriable Cache)",
            "classname": "WoodenCrate",
            "category": "camp",
            "subcategory": "Vanilla Shelters & Storage",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "8× Wooden Plank + 16× Nail",
            "build_tools": ["Hammer / Hatchet (craft)", "Shovel / Pickaxe / FarmingHoe (bury UndergroundStash)"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "45 days (above ground) · 14 days (buried UndergroundStash)",
            "slots": "50 slots (10×5)",
            "materials": {"planks": 8, "nails": 16},
            "stages": [
                {"name": "Craft Crate", "cost": "8× WoodenPlank + 16× Nail"},
                {"name": "Optional Underground Stash", "cost": "Bury with Shovel, FieldShovel, Pickaxe, or FarmingHoe (14-day lifetime)"},
            ],
            "notes": "Can be stacked inside tents/cabins, loaded into truck beds, or buried underground.",
        },
        {
            "id": "van_stone_oven",
            "name": "Stone Oven & Stone Circle Fireplace",
            "classname": "Fireplace (Oven)",
            "category": "camp",
            "subcategory": "Vanilla Shelters & Storage",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "Fireplace + 8× Large Stone (Circle) or 16× Large Stone (Oven)",
            "build_tools": ["Pickaxe / SledgeHammer (mine boulders for Large Stones)"],
            "dismantle_tools": ["Hands / Pickaxe"],
            "lifetime": "7 days (Stone Oven)",
            "slots": "3× Direct Cooking / Smoking Slots",
            "materials": {"sticks": 1, "stones": 16},
            "stages": [
                {"name": "Base Fireplace", "cost": "1× WoodenStick / Firewood + 1× Rag / Bark / Paper"},
                {"name": "Stone Circle (Windproof)", "cost": "Attach 8× Stone (Large Stones) + build circle"},
                {"name": "Full Stone Oven (Persistent)", "cost": "Attach 16× Stone (Large Stones) + build oven (supports 3 pots/pans)"},
            ],
            "notes": "Essential for CookZ pot/pan/cauldron dishes before you build the Hunting Cabin's indoor hearth.",
        },
        {
            "id": "van_fire_barrel",
            "name": "Fire Barrel & Leather Tanning Barrel",
            "classname": "BarrelHoles_ColorBase / Barrel_ColorBase",
            "category": "camp",
            "subcategory": "Vanilla Shelters & Storage",
            "mod": "Vanilla DayZ 1.30",
            "mod_folder": "Vanilla",
            "kit_recipe": "1× Oil Barrel + Knife / Crowbar / Pickaxe (Fire Barrel) OR + Pelt + GardenLime + Water (Tanning)",
            "build_tools": ["Knife", "Crowbar", "Pickaxe", "Machete"],
            "dismantle_tools": ["Hands (when empty & cooled)"],
            "lifetime": "45 days",
            "slots": "150 slots (10×15)",
            "materials": {"leather": 8},
            "stages": [
                {"name": "Fire Barrel", "cost": "1× Barrel_ColorBase + poke holes with Knife/Crowbar/Pickaxe"},
                {"name": "Tan Leather Hides", "cost": "Intact Barrel + Animal Pelt + GardenLime + Water → TannedLeather"},
            ],
            "notes": "Tanned Leather is used for the Leather Shelter (8×), Leather Sack (63 slots), Vanilla 1.30 Leather Belt, Horse Saddle (8×), and Horse Bridle (4×).",
        },
        # ---- CATEGORY 2: RaG_BaseBuilding (ALL 21 ENABLED KITS / 37 STRUCTURAL PARTS) ----
        {
            "id": "rag_bb_book",
            "name": "RaG Basebuilding Book (Master Blueprint Manual)",
            "classname": "RaG_BB_Book",
            "category": "rag_modular",
            "subcategory": "Blueprint Manual",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"Found in Farm/Town/Village/Hunting OR craft any kit directly with {kit_planks}× Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (structures) · 40 days w/ Flag",
            "slots": "2×2 inv",
            "materials": {"planks": kit_planks, "nails": kit_nails},
            "stages": [
                {"name": "Universal Kit Recipe", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail (scroll mousewheel to choose any of the 21 kits)"},
                {"name": "Build / Dismantle Timers", "cost": f"Build: {build_time_s:.0f}s per part (Hammer/Hatchet) · Dismantle: {dismantle_time_s:.0f}s from inside (Hatchet/Crowbar)"},
            ],
            "notes": "EnableBookKitCrafting=1. Every RaG structure supports XmasLights, PortableGasLamp, and RaG/Vanilla DigitalCodeLock (AutoLockOnClose=1, RequireBattery=0).",
        },
        {
            "id": "rag_bb_foundation",
            "name": "RaG Modular Foundation",
            "classname": "RaG_BB_FoundationKit",
            "category": "rag_modular",
            "subcategory": "Foundations & Framing",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Snap Grid Base",
            "materials": _sum_parts(("Foundation", _pc("Foundation", 4, 15, 30))),
            "stages": [
                {"name": "Foundation Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Foundation Deck", "cost": f"{_pc('Foundation',4,15,30)['logs']}× Logs + {_pc('Foundation',4,15,30)['planks']}× Planks + {_pc('Foundation',4,15,30)['nails']}× Nails"},
            ],
            "notes": "Snap-grid foundation for leveling compounds on Nasdara's uneven rocky slopes.",
        },
        {
            "id": "rag_bb_pillar",
            "name": "RaG Corner Support Pillar",
            "classname": "RaG_BB_PillarKit",
            "category": "rag_modular",
            "subcategory": "Foundations & Framing",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Snap Corner",
            "materials": _sum_parts(("Pillar", _pc("Pillar", 1, 5, 5))),
            "stages": [
                {"name": "Pillar Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Pillar Post", "cost": f"{_pc('Pillar',1,5,5)['logs']}× Log + {_pc('Pillar',1,5,5)['planks']}× Planks + {_pc('Pillar',1,5,5)['nails']}× Nails"},
            ],
            "notes": "Vertical support beam for multi-story modular rooms and overhangs.",
        },
        {
            "id": "rag_bb_wall",
            "name": "RaG Full Modular Wall",
            "classname": "RaG_BB_WallKit",
            "category": "rag_modular",
            "subcategory": "Walls & Windows",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "XmasLights + PortableGasLamp",
            "materials": _sum_parts(("Wall", _pc("Wall", 4, 10, 25))),
            "stages": [
                {"name": "Wall Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Solid Wall Panel", "cost": f"{_pc('Wall',4,10,25)['logs']}× Logs + {_pc('Wall',4,10,25)['planks']}× Planks + {_pc('Wall',4,10,25)['nails']}× Nails"},
            ],
            "notes": "Snaps cleanly to Foundation edges and adjacent Walls/Doors.",
        },
        {
            "id": "rag_bb_low_wall",
            "name": "RaG Half / Low Parapet Wall",
            "classname": "RaG_BB_Low_WallKit",
            "category": "rag_modular",
            "subcategory": "Walls & Windows",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Half-Height Cover",
            "materials": _sum_parts(("LowWall", _pc("LowWall", 2, 5, 15))),
            "stages": [
                {"name": "Low Wall Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Low Wall", "cost": f"{_pc('LowWall',2,5,15)['logs']}× Logs + {_pc('LowWall',2,5,15)['planks']}× Planks + {_pc('LowWall',2,5,15)['nails']}× Nails"},
            ],
            "notes": "Ideal for roof battlements, porch railings, and firing parapets.",
        },
        {
            "id": "rag_bb_door_wood",
            "name": "RaG Modular Door Wall (Wood Door)",
            "classname": "RaG_BB_DoorKit",
            "category": "rag_modular",
            "subcategory": "Doors & Gates",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(("DoorFrame", _pc("DoorFrame", 4, 10, 20)), ("Door", _pc("Door", 0, 5, 5))),
            "stages": [
                {"name": "Door Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Door Frame", "cost": f"{_pc('DoorFrame',4,10,20)['logs']}× Logs + {_pc('DoorFrame',4,10,20)['planks']}× Planks + {_pc('DoorFrame',4,10,20)['nails']}× Nails"},
                {"name": "Wooden Door Leaf", "cost": f"{_pc('Door',0,5,5)['planks']}× Planks + {_pc('Door',0,5,5)['nails']}× Nails"},
            ],
            "notes": "Full wall section with centered lockable doorway. Auto-locks on close when fitted with DigitalCodeLock.",
        },
        {
            "id": "rag_bb_door_metal",
            "name": "RaG Modular Door Wall (Reinforced Sheet Metal Door)",
            "classname": "RaG_BB_DoorKit (MetalDoor)",
            "category": "rag_modular",
            "subcategory": "Doors & Gates",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(("DoorFrame", _pc("DoorFrame", 4, 10, 20)), ("MetalDoor", _pc("MetalDoor", 0, 0, 5, 5))),
            "stages": [
                {"name": "Door Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Door Frame", "cost": f"{_pc('DoorFrame',4,10,20)['logs']}× Logs + {_pc('DoorFrame',4,10,20)['planks']}× Planks + {_pc('DoorFrame',4,10,20)['nails']}× Nails"},
                {"name": "Reinforced Sheet Metal Door", "cost": f"{_pc('MetalDoor',0,0,5,5)['metal']}× Metal Sheets + {_pc('MetalDoor',0,0,5,5)['nails']}× Nails"},
            ],
            "notes": "Upgraded armored door leaf built inside the standard RaG DoorFrame.",
        },
        {
            "id": "rag_bb_single_door",
            "name": "RaG Standalone Single Door (Existing Doorways)",
            "classname": "RaG_BB_Single_DoorKit",
            "category": "rag_modular",
            "subcategory": "Doors & Gates",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(("SingleDoorFrame", _pc("SingleDoorFrame", 2, 10, 20)), ("SingleDoor", _pc("SingleDoor", 0, 5, 5))),
            "stages": [
                {"name": "Single Door Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Single Door Frame", "cost": f"{_pc('SingleDoorFrame',2,10,20)['logs']}× Logs + {_pc('SingleDoorFrame',2,10,20)['planks']}× Planks + {_pc('SingleDoorFrame',2,10,20)['nails']}× Nails"},
                {"name": "Single Door Leaf", "cost": f"{_pc('SingleDoor',0,5,5)['planks']}× Planks + {_pc('SingleDoor',0,5,5)['nails']}× Nails"},
            ],
            "notes": "Narrower standalone door frame for fortifying existing Nasdara buildings, bunkers, and canyon caves.",
        },
        {
            "id": "rag_bb_gate_double",
            "name": "RaG Double Vehicle Gate (Left + Right Doors)",
            "classname": "RaG_BB_GateKit",
            "category": "rag_modular",
            "subcategory": "Doors & Gates",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(
                ("GateFrame", _pc("GateFrame", 2, 10, 20)),
                ("GateDoorLeft", _pc("GateDoorLeft", 0, 10, 10)),
                ("GateDoorRight", _pc("GateDoorRight", 0, 10, 10)),
            ),
            "stages": [
                {"name": "Gate Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Gate Frame", "cost": f"{_pc('GateFrame',2,10,20)['logs']}× Logs + {_pc('GateFrame',2,10,20)['planks']}× Planks + {_pc('GateFrame',2,10,20)['nails']}× Nails"},
                {"name": "Left Gate Door", "cost": f"{_pc('GateDoorLeft',0,10,10)['planks']}× Planks + {_pc('GateDoorLeft',0,10,10)['nails']}× Nails"},
                {"name": "Right Gate Door", "cost": f"{_pc('GateDoorRight',0,10,10)['planks']}× Planks + {_pc('GateDoorRight',0,10,10)['nails']}× Nails"},
            ],
            "notes": "Full-width double compound gate wide enough for the Apocalypse Truck and Semi Truck.",
        },
        {
            "id": "rag_bb_gate_left",
            "name": "RaG Single Wide Gate (Left-Hinged)",
            "classname": "RaG_BB_GateLeftKit",
            "category": "rag_modular",
            "subcategory": "Doors & Gates",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(("GateLeftFrame", _pc("GateLeftFrame", 1, 10, 20)), ("GateLeftDoor", _pc("GateLeftDoor", 0, 10, 10))),
            "stages": [
                {"name": "Gate Left Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Gate Left Frame", "cost": f"{_pc('GateLeftFrame',1,10,20)['logs']}× Log + {_pc('GateLeftFrame',1,10,20)['planks']}× Planks + {_pc('GateLeftFrame',1,10,20)['nails']}× Nails"},
                {"name": "Gate Left Leaf", "cost": f"{_pc('GateLeftDoor',0,10,10)['planks']}× Planks + {_pc('GateLeftDoor',0,10,10)['nails']}× Nails"},
            ],
            "notes": "Single-leaf wide gate hinged on the left post; can pair with GateRightKit for extra-wide bays.",
        },
        {
            "id": "rag_bb_gate_right",
            "name": "RaG Single Wide Gate (Right-Hinged)",
            "classname": "RaG_BB_GateRightKit",
            "category": "rag_modular",
            "subcategory": "Doors & Gates",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(("GateRightFrame", _pc("GateRightFrame", 1, 10, 20)), ("GateRightDoor", _pc("GateRightDoor", 0, 10, 10))),
            "stages": [
                {"name": "Gate Right Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Gate Right Frame", "cost": f"{_pc('GateRightFrame',1,10,20)['logs']}× Log + {_pc('GateRightFrame',1,10,20)['planks']}× Planks + {_pc('GateRightFrame',1,10,20)['nails']}× Nails"},
                {"name": "Gate Right Leaf", "cost": f"{_pc('GateRightDoor',0,10,10)['planks']}× Planks + {_pc('GateRightDoor',0,10,10)['nails']}× Nails"},
            ],
            "notes": "Single-leaf wide gate hinged on the right post.",
        },
        {
            "id": "rag_bb_window_large",
            "name": "RaG Large Window Wall + Shutter",
            "classname": "RaG_BB_WindowKit",
            "category": "rag_modular",
            "subcategory": "Walls & Windows",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Openable Window Shutter",
            "materials": _sum_parts(("WindowBigFrame", _pc("WindowBigFrame", 4, 10, 25)), ("WindowBig", _pc("WindowBig", 0, 5, 5))),
            "stages": [
                {"name": "Window Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Large Window Frame", "cost": f"{_pc('WindowBigFrame',4,10,25)['logs']}× Logs + {_pc('WindowBigFrame',4,10,25)['planks']}× Planks + {_pc('WindowBigFrame',4,10,25)['nails']}× Nails"},
                {"name": "Window Shutter", "cost": f"{_pc('WindowBig',0,5,5)['planks']}× Planks + {_pc('WindowBig',0,5,5)['nails']}× Nails"},
            ],
            "notes": "Full wall with large shuttered observation window.",
        },
        {
            "id": "rag_bb_window_small",
            "name": "RaG Small Slit Window Wall + Shutter",
            "classname": "RaG_BB_Window_SmallKit",
            "category": "rag_modular",
            "subcategory": "Walls & Windows",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Firing Slit Shutter",
            "materials": _sum_parts(("WindowSmallFrame", _pc("WindowSmallFrame", 4, 10, 25)), ("WindowSmall", _pc("WindowSmall", 0, 5, 5))),
            "stages": [
                {"name": "Small Window Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Small Window Frame", "cost": f"{_pc('WindowSmallFrame',4,10,25)['logs']}× Logs + {_pc('WindowSmallFrame',4,10,25)['planks']}× Planks + {_pc('WindowSmallFrame',4,10,25)['nails']}× Nails"},
                {"name": "Small Window Shutter", "cost": f"{_pc('WindowSmall',0,5,5)['planks']}× Planks + {_pc('WindowSmall',0,5,5)['nails']}× Nails"},
            ],
            "notes": "Protected firing port with interior shutter.",
        },
        {
            "id": "rag_bb_floor",
            "name": "RaG Modular Floor Tile",
            "classname": "RaG_BB_FloorKit",
            "category": "rag_modular",
            "subcategory": "Floors, Roofs & Hatches",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Snap Floor",
            "materials": _sum_parts(("Floor", _pc("Floor", 2, 10, 25))),
            "stages": [
                {"name": "Floor Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Floor Deck", "cost": f"{_pc('Floor',2,10,25)['logs']}× Logs + {_pc('Floor',2,10,25)['planks']}× Planks + {_pc('Floor',2,10,25)['nails']}× Nails"},
            ],
            "notes": "Ground or upper-story floor decking.",
        },
        {
            "id": "rag_bb_ceiling",
            "name": "RaG Modular Flat Ceiling / Upper Floor",
            "classname": "RaG_BB_CeilingKit",
            "category": "rag_modular",
            "subcategory": "Floors, Roofs & Hatches",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Snap Ceiling",
            "materials": _sum_parts(("Ceiling", _pc("Ceiling", 2, 10, 25))),
            "stages": [
                {"name": "Ceiling Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Ceiling Panel", "cost": f"{_pc('Ceiling',2,10,25)['logs']}× Logs + {_pc('Ceiling',2,10,25)['planks']}× Planks + {_pc('Ceiling',2,10,25)['nails']}× Nails"},
            ],
            "notes": "Flat roof or second-floor deck plate.",
        },
        {
            "id": "rag_bb_roof",
            "name": "RaG Angled Pitched Roof + Left/Right Gables",
            "classname": "RaG_BB_RoofKit",
            "category": "rag_modular",
            "subcategory": "Floors, Roofs & Hatches",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Pitched Roof + 2 Gables",
            "materials": _sum_parts(
                ("AngledRoof", _pc("AngledRoof", 4, 15, 25)),
                ("AngledRoofEndLeft", _pc("AngledRoofEndLeft", 0, 5, 5)),
                ("AngledRoofEndRight", _pc("AngledRoofEndRight", 0, 5, 5)),
            ),
            "stages": [
                {"name": "Roof Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Angled Roof Slope", "cost": f"{_pc('AngledRoof',4,15,25)['logs']}× Logs + {_pc('AngledRoof',4,15,25)['planks']}× Planks + {_pc('AngledRoof',4,15,25)['nails']}× Nails"},
                {"name": "Left & Right Gable Ends", "cost": f"Left: {_pc('AngledRoofEndLeft',0,5,5)['planks']} Planks + {_pc('AngledRoofEndLeft',0,5,5)['nails']} Nails · Right: {_pc('AngledRoofEndRight',0,5,5)['planks']} Planks + {_pc('AngledRoofEndRight',0,5,5)['nails']} Nails"},
            ],
            "notes": "Weatherproof pitched roof with optional left/right gable end closures.",
        },
        {
            "id": "rag_bb_hatch",
            "name": "RaG Ceiling Hatch (w/ Staircase or Ladder)",
            "classname": "RaG_BB_Floor_HatchKit",
            "category": "rag_modular",
            "subcategory": "Floors, Roofs & Hatches",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "DigitalCodeLock / CombinationLock",
            "materials": _sum_parts(
                ("HatchFrame", _pc("HatchFrame", 4, 10, 20)),
                ("HatchDoor", _pc("HatchDoor", 0, 5, 5)),
                ("HatchStaircase", _pc("HatchStaircase", 0, 10, 20)),
            ),
            "stages": [
                {"name": "Hatch Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Hatch Frame & Lockable Hatch Door", "cost": f"Frame: {_pc('HatchFrame',4,10,20)['logs']} Logs + {_pc('HatchFrame',4,10,20)['planks']} Planks + {_pc('HatchFrame',4,10,20)['nails']} Nails · Door: {_pc('HatchDoor',0,5,5)['planks']} Planks + {_pc('HatchDoor',0,5,5)['nails']} Nails"},
                {"name": "Option A: Hatch Staircase", "cost": f"{_pc('HatchStaircase',0,10,20)['planks']}× Planks + {_pc('HatchStaircase',0,10,20)['nails']}× Nails"},
                {"name": "Option B: Hatch Vertical Ladder", "cost": f"{_pc('HatchLadder',0,5,10)['planks']}× Planks + {_pc('HatchLadder',0,5,10)['nails']}× Nails (EnableBuildHatchLadder=1)"},
            ],
            "notes": "Lockable roof/second-floor access hatch; supports either a full staircase or compact vertical ladder.",
        },
        {
            "id": "rag_bb_ramp",
            "name": "RaG Foundation Vehicle / Entry Ramp",
            "classname": "RaG_BB_RampKit",
            "category": "rag_modular",
            "subcategory": "Stairs, Ramps & Sheds",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Snap Ramp",
            "materials": _sum_parts(("Ramp", _pc("Ramp", 2, 10, 15))),
            "stages": [
                {"name": "Ramp Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Ramp Deck", "cost": f"{_pc('Ramp',2,10,15)['logs']}× Logs + {_pc('Ramp',2,10,15)['planks']}× Planks + {_pc('Ramp',2,10,15)['nails']}× Nails"},
            ],
            "notes": "Smooth incline for driving trucks or horses onto raised foundations.",
        },
        {
            "id": "rag_bb_stairs",
            "name": "RaG Foundation Entry Stairs",
            "classname": "RaG_BB_StairsKit",
            "category": "rag_modular",
            "subcategory": "Stairs, Ramps & Sheds",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Snap Porch Steps",
            "materials": _sum_parts(("Stairs", _pc("Stairs", 2, 10, 15))),
            "stages": [
                {"name": "Stairs Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Foundation Steps", "cost": f"{_pc('Stairs',2,10,15)['logs']}× Logs + {_pc('Stairs',2,10,15)['planks']}× Planks + {_pc('Stairs',2,10,15)['nails']}× Nails"},
            ],
            "notes": "Exterior steps snapping to the edge of a raised Foundation.",
        },
        {
            "id": "rag_bb_staircase1",
            "name": "RaG Full Story Staircase (Type 1 Straight)",
            "classname": "RaG_BB_StaircaseKit",
            "category": "rag_modular",
            "subcategory": "Stairs, Ramps & Sheds",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Full-Height Staircase",
            "materials": _sum_parts(("StairCase1", _pc("StairCase1", 2, 15, 60))),
            "stages": [
                {"name": "Staircase Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Staircase Type 1", "cost": f"{_pc('StairCase1',2,15,60)['logs']}× Logs + {_pc('StairCase1',2,15,60)['planks']}× Planks + {_pc('StairCase1',2,15,60)['nails']}× Nails"},
            ],
            "notes": "Full-story staircase connecting ground floor to upper ceiling deck.",
        },
        {
            "id": "rag_bb_staircase2",
            "name": "RaG Full Story Staircase (Type 2 Landing)",
            "classname": "RaG_BB_Staircase_2Kit",
            "category": "rag_modular",
            "subcategory": "Stairs, Ramps & Sheds",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Landing Staircase",
            "materials": _sum_parts(("StairCase2", _pc("StairCase2", 2, 20, 60))),
            "stages": [
                {"name": "Staircase 2 Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Staircase Type 2", "cost": f"{_pc('StairCase2',2,20,60)['logs']}× Logs + {_pc('StairCase2',2,20,60)['planks']}× Planks + {_pc('StairCase2',2,20,60)['nails']}× Nails"},
            ],
            "notes": "Alternative full-story staircase geometry for tighter interior corners.",
        },
        {
            "id": "rag_bb_stepladder",
            "name": "RaG Step Ladder",
            "classname": "RaG_BB_StepLadderKit",
            "category": "rag_modular",
            "subcategory": "Stairs, Ramps & Sheds",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Utility Step Ladder",
            "materials": _sum_parts(("Ladder", _pc("Ladder", 0, 5, 10))),
            "stages": [
                {"name": "Step Ladder Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Step Ladder", "cost": f"{_pc('Ladder',0,5,10)['planks']}× Planks + {_pc('Ladder',0,5,10)['nails']}× Nails"},
            ],
            "notes": "Compact climbable ladder for lofts, rooftops, and canyon ledges.",
        },
        {
            "id": "rag_bb_woodstorage",
            "name": "RaG Wood & Lumber Storage Shed",
            "classname": "RaG_BB_WoodStorageKit",
            "category": "rag_modular",
            "subcategory": "Stairs, Ramps & Sheds",
            "mod": "RaG_BaseBuilding (@3157695626)",
            "mod_folder": "@RaG_BaseBuilding",
            "kit_recipe": f"{kit_planks}× Wooden Plank + {kit_nails}× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Crowbar"],
            "lifetime": "14 days (40d w/ Flag)",
            "slots": "Dedicated Log, Plank & Firewood Rack",
            "materials": _sum_parts(
                ("WoodStorageFloor", _pc("WoodStorageFloor", 1, 5, 10)),
                ("WoodStorageFrame", _pc("WoodStorageFrame", 0, 5, 10)),
                ("WoodStorageRoof", _pc("WoodStorageRoof", 0, 5, 10)),
            ),
            "stages": [
                {"name": "Wood Storage Kit", "cost": f"{kit_planks}× WoodenPlank + {kit_nails}× Nail"},
                {"name": "Storage Floor", "cost": f"{_pc('WoodStorageFloor',1,5,10)['logs']}× Log + {_pc('WoodStorageFloor',1,5,10)['planks']}× Planks + {_pc('WoodStorageFloor',1,5,10)['nails']}× Nails"},
                {"name": "Storage Frame & Roof", "cost": f"Frame: {_pc('WoodStorageFrame',0,5,10)['planks']} Planks + {_pc('WoodStorageFrame',0,5,10)['nails']} Nails · Roof: {_pc('WoodStorageRoof',0,5,10)['planks']} Planks + {_pc('WoodStorageRoof',0,5,10)['nails']} Nails"},
            ],
            "notes": "Dedicated covered timber rack for stockpiling logs, planks, and firewood at your homestead.",
        },
        # ---- CATEGORY 3: RaG HUNTING CABIN ----
        {
            "id": "rag_hunting_cabin_full",
            "name": "RaG Hunting Cabin (Complete Log Homestead)",
            "classname": "rag_hunting_cabin_kit -> rag_hunting_cabin",
            "category": "cabin",
            "subcategory": "Homestead Milestone",
            "mod": "RaG_Hunting_Cabin (@3117613872)",
            "mod_folder": "@RaG_Hunting_Cabin",
            "kit_recipe": f"{cabin_kit_planks}× Wooden Plank + {cabin_kit_nails}× Nail",
            "build_tools": ["Hammer (non-ruined — ruined on completion!)"],
            "dismantle_tools": ["Crowbar", "Hatchet", "SledgeHammer (returns 100% materials + kit)"],
            "lifetime": "45 days",
            "slots": "Lockable Door + 8 Windows + Indoor Fireplace + Wall Light Switch",
            "materials": {
                "logs": 20,
                "planks": cabin_kit_planks + 100,
                "nails": cabin_kit_nails + 99,
                "stones": 32,
            },
            "stages": [
                {"name": "Step 1: Craft Cabin Kit", "cost": f"{cabin_kit_planks}× WoodenPlank + {cabin_kit_nails}× Nail → rag_hunting_cabin_kit (or find in Hunting/Farm)"},
                {"name": "Step 2: Attach Cabin Materials", "cost": "20× WoodenLog + 100× WoodenPlank + 99× Nail + 32× Stone (Large Stones)"},
                {"name": "Step 3: Construct with Hammer", "cost": "Build with a non-ruined Hammer (RuinHammerAfterBuilt=1 consumes the Hammer)"},
            ],
            "notes": "The signature Badlands homestead: lockable front door (DigitalCodeLock / CombinationLock), 8 openable windows, built-in stone fireplace/chimney for indoor warmth & CookZ cooking, and interior ceiling + party lights controlled from the wall switch. Dismantling returns all materials AND the kit!",
        },
        # ---- CATEGORY 4: MMG BASE STORAGE (CRAFTABLE + DEPLOYABLE KITS) ----
        {
            "id": "mmg_supply_crate",
            "name": "MMG Craftable Supply Crate (300 Slots)",
            "classname": "mmg_supply_crate_unfinished_wood -> mmg_supplycrate_level1",
            "category": "mmg_storage",
            "subcategory": "Craftable Storage",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "10× Wooden Plank + 40× Nail, then + 50× Nail (90 Nails total)",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Hatchet", "Screwdriver"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "300 slots (dedicated building material slots)",
            "materials": {"planks": 10, "nails": 90},
            "stages": [
                {"name": "Step 1: Unfinished Supply Crate", "cost": "10× WoodenPlank + 40× Nail → mmg_supply_crate_unfinished_wood"},
                {"name": "Step 2: Finish Supply Crate", "cost": "Unfinished Supply Crate + 50× Nail → mmg_supplycrate_level1 (300 slots)"},
            ],
            "notes": "Craft_SupplyCrate=true. Massive 300-slot workshop crate with dedicated attachment slots for logs, planks, nails, and sheet metal.",
        },
        {
            "id": "mmg_gun_rack_craft",
            "name": "MMG Craftable Wooden Gun Rack (6 Rifles)",
            "classname": "mmg_gun_rack_planks -> mmg_craftable_gun_rack",
            "category": "mmg_storage",
            "subcategory": "Craftable Weapon Racks",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "10× Wooden Plank + HandSaw → Gun Rack Planks + 45× Nail",
            "build_tools": ["HandSaw / Hacksaw (Step 1)", "Hammer / Hatchet (Step 2)"],
            "dismantle_tools": ["Screwdriver", "Hatchet"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "6× Long Gun Slots",
            "materials": {"planks": 10, "nails": 45},
            "stages": [
                {"name": "Step 1: Cut Gun Rack Planks", "cost": "10× WoodenPlank + HandSaw → mmg_gun_rack_planks"},
                {"name": "Step 2: Assemble Gun Rack", "cost": "mmg_gun_rack_planks + 45× Nail → mmg_craftable_gun_rack"},
            ],
            "notes": "Craft_Gun_Rack=true. Freestanding 6-rifle rack craftable from raw lumber and nails.",
        },
        {
            "id": "mmg_gun_wall_wood",
            "name": "MMG Wooden Gun Wall (8 Weapons + 40 Slots)",
            "classname": "mmg_gun_wall_kit_wooden -> mmg_gun_wall_wooden",
            "category": "mmg_storage",
            "subcategory": "Craftable Weapon Racks",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "10× Wooden Plank + 40× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Screwdriver (re-packs into kit)"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "8× Weapons + 40 cargo slots",
            "materials": {"planks": 10, "nails": 40},
            "stages": [
                {"name": "Craft Wooden Gun Wall Kit", "cost": "10× WoodenPlank + 40× Nail → mmg_gun_wall_kit_wooden"},
                {"name": "Place & Dismantle", "cost": "Deploy hologram on wall; use Screwdriver to re-pack into kit"},
            ],
            "notes": "Craft_Gunwall=true. Displays 8 primary rifles visually on your cabin or compound wall.",
        },
        {
            "id": "mmg_gun_wall_metal",
            "name": "MMG Sheet Metal Gun Wall (8 Weapons + 40 Slots)",
            "classname": "mmg_gun_wall_kit_metal -> mmg_gun_wall_metal",
            "category": "mmg_storage",
            "subcategory": "Craftable Weapon Racks",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "5× Metal Sheet + 40× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Screwdriver (re-packs into kit)"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "8× Weapons + 40 cargo slots",
            "materials": {"metal": 5, "nails": 40},
            "stages": [
                {"name": "Craft Metal Gun Wall Kit", "cost": "5× MetalPlate (Sheet Metal) + 40× Nail → mmg_gun_wall_kit_metal"},
                {"name": "Place & Dismantle", "cost": "Deploy hologram on wall; use Screwdriver to re-pack into kit"},
            ],
            "notes": "Craft_Gunwall=true. Industrial pegboard gun wall crafted from sheet metal.",
        },
        {
            "id": "mmg_craftable_tent",
            "name": "MMG Craftable Camo Tent (150 Slots)",
            "classname": "mmg_craftable_tent_kit -> mmg_craftable_tent",
            "category": "mmg_storage",
            "subcategory": "Craftable Storage",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "1× CamoNet + 5× Wooden Plank",
            "build_tools": ["Hands"],
            "dismantle_tools": ["Hands / Screwdriver"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "150 slots",
            "materials": {"camo_net": 1, "planks": 5},
            "stages": [
                {"name": "Craft Tent Kit", "cost": "1× CamoNet + 5× WoodenPlank → mmg_craftable_tent_kit"},
            ],
            "notes": "Craft_Tent=true. High-capacity camo field tent requiring zero nails.",
        },
        {
            "id": "mmg_old_table",
            "name": "MMG Craftable Work Table (Tools & Weapons)",
            "classname": "mmg_old_table",
            "category": "mmg_storage",
            "subcategory": "Craftable Furniture",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "5× Wooden Plank + 45× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Screwdriver", "Hatchet"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "50 slots + 2 Rifles + Axe + Sledge + Pickaxe + Shovel + 2 Ammo Boxes",
            "materials": {"planks": 5, "nails": 45},
            "stages": [
                {"name": "Craft Old Table", "cost": "5× WoodenPlank + 45× Nail → mmg_old_table"},
            ],
            "notes": "Craft_Old_Table=true. Holds basebuilding tools (Axe, Sledgehammer, Pickaxe, Shovel), 2 weapons, and 2 ammo boxes directly on the tabletop.",
        },
        {
            "id": "mmg_wall_shelf",
            "name": "MMG Craftable Wooden Wall Shelf",
            "classname": "mmg_wall_shelf_wood",
            "category": "mmg_storage",
            "subcategory": "Craftable Furniture",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "5× Wooden Plank + 50× Nail",
            "build_tools": ["Hammer", "Hatchet"],
            "dismantle_tools": ["Screwdriver", "Hatchet"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "70 slots + 2 Rifles + 1 Pistol + 4 Grenades + 1 Knife",
            "materials": {"planks": 5, "nails": 50},
            "stages": [
                {"name": "Craft Wall Shelf", "cost": "5× WoodenPlank + 50× Nail → mmg_wall_shelf_wood"},
            ],
            "notes": "Craft_Wall_Shelf=true. Compact cabin shelf with ready weapon & grenade mounts.",
        },
        {
            "id": "mmg_deployable_lockers",
            "name": "MMG Lockers, Safes, Crates, Fridge & Greenhouse Kits",
            "classname": "mmg_equipment_locker_*_kit / mmg_palette_storage_kit / mmg_greenhouse_kit",
            "category": "mmg_storage",
            "subcategory": "Found Deployable Kits",
            "mod": "MMG Base Storage (@3210162677)",
            "mod_folder": "@MMG_BaseStorage",
            "kit_recipe": "Found as Kits in Industrial / Military / Farm · Re-pack with Screwdriver",
            "build_tools": ["Hands (deploy hologram)"],
            "dismantle_tools": ["Screwdriver (when empty & unlocked → returns Kit)"],
            "lifetime": "10 days (40d w/ Flag)",
            "slots": "100 to 500 slots + Loadout Mannequins",
            "materials": {},
            "stages": [
                {"name": "Lockable Lockers & Gear Stand", "cost": "Equipment Locker & TA50 Locker (Full Loadout + 5 Guns + 100 slots) · Solo Locker (Loadout + 2 Guns + 100 slots) · Gear Stand (Full Loadout + 100 slots)"},
                {"name": "Heavy Safes & Crates", "cost": "Palette Storage (500 slots) · Military Case (400 slots) · Armored Cabinet (250 slots, lockable) · Old Safe (200 slots, lockable) · Army Box (200 slots) · Metal Crate (170 slots) · Weapon Crate (150 slots + 2 Guns)"},
                {"name": "Homestead Appliances & Gardening", "cost": "Toolwagon (200 slots) · Minsk Fridge (150 slots) · Lockable Gun Rack (10 Guns) · Greenhouse (10 plant slots) · Planter Box (3 plant slots)"},
            ],
            "notes": "All lockable MMG containers accept Vanilla 1.30 DigitalCodeLock and CombinationLock. Always empty cargo before using a Screwdriver to re-pack.",
        },
        # ---- CATEGORY 5: WORKBENCHES, HORSE TACK, VEHICLES & TROPHIES ----
        {
            "id": "zen_car_workbench",
            "name": "Zens Static Car Workbench (Garage Station)",
            "classname": "Zen_CarWorkbenchKit -> Zen_CarWorkbench",
            "category": "utility_tack",
            "subcategory": "Workbenches & Vehicles",
            "mod": "Zens Car Workbench (@3030756548)",
            "mod_folder": "@ZenCarWorkbench",
            "kit_recipe": f"{wb_nails}× Nail + {wb_metal}× Metal Sheet",
            "build_tools": ["Hands (combine Nails + MetalPlate)"],
            "dismantle_tools": ["Screwdriver (re-packs into Zen_CarWorkbenchKit)"],
            "lifetime": "28 days (40d w/ Flag)",
            "slots": "50 cargo slots + 17×4 Mechanic Tool/Part Mounts",
            "materials": {"nails": wb_nails, "metal": wb_metal},
            "stages": [
                {"name": "Craft Workbench Kit", "cost": f"{wb_nails}× Nail + {wb_metal}× MetalPlate (Sheet Metal) → Zen_CarWorkbenchKit"},
                {"name": "Dedicated Garage Mounts (up to 4 each)", "cost": "CarBattery, TruckBattery, CarRadiator, SparkPlug, GlowPlug, TireRepairKit, Blowtorch, CanisterGasoline, Wrench, LugWrench, PipeWrench, Screwdriver, Pliers, SledgeHammer, Rag, SprayCans"},
            ],
            "notes": "Persists 28 days even without a flag. Dismantle anytime with a Screwdriver.",
        },
        {
            "id": "car_cover_camo",
            "name": "CarCover Vehicle Cloak (CamoNet)",
            "classname": "CamoNet -> CarCover_*",
            "category": "utility_tack",
            "subcategory": "Workbenches & Vehicles",
            "mod": "CarCover (@2303483532)",
            "mod_folder": "@CarCover",
            "kit_recipe": "1× CamoNet in hands → Cover Vehicle / Helicopter",
            "build_tools": ["CamoNet"],
            "dismantle_tools": ["Hands (Uncover Vehicle)"],
            "lifetime": "Persistent while covered",
            "slots": "Covers Cars, Trucks & Helicopters",
            "materials": {"camo_net": 1},
            "stages": [
                {"name": "Cover Vehicle", "cost": "Hold CamoNet in hands, look at parked vehicle/aircraft, and hold 'Cover Vehicle'"},
                {"name": "Uncover Vehicle", "cost": "Interact with covered vehicle → returns CamoNet and restores vehicle"},
            ],
            "notes": "Protects parked trucks and helicopters from physics jitter and conceals them in canyons.",
        },
        {
            "id": "horse_saddle",
            "name": "Craftable Horse Saddle",
            "classname": "Saddle",
            "category": "utility_tack",
            "subcategory": "Horses & Companions",
            "mod": "Horse Expansion + DayZ Horse (@3297432307)",
            "mod_folder": "@HorseExpansion",
            "kit_recipe": "8× Tanned Leather + Leather Sewing Kit",
            "build_tools": ["LeatherSewingKit"],
            "dismantle_tools": [],
            "lifetime": "45 days (on horse / in storage)",
            "slots": "Mount Tack + Repair w/ LeatherSewingKit",
            "materials": {"leather": 8},
            "stages": [
                {"name": "Tan Leather", "cost": "Animal Pelt + GardenLime + Water in Barrel → 8× TannedLeather"},
                {"name": "Stitch Saddle", "cost": "8× TannedLeather + LeatherSewingKit → Saddle"},
            ],
            "notes": "Craftable saddle for riding wild horses when farm tack hasn't been scavenged yet.",
        },
        {
            "id": "horse_bridle_stable",
            "name": "Craftable Horse Bridle, Bags & Deployable Stable",
            "classname": "Bridle / HorseBags / Stable_dayz_kit",
            "category": "utility_tack",
            "subcategory": "Horses & Companions",
            "mod": "Horse Expansion + DayZ Horse (@3297432307)",
            "mod_folder": "@HorseExpansion",
            "kit_recipe": "Bridle: 4× Tanned Leather + 1× Rope · Stable: Stable_dayz_kit",
            "build_tools": ["Hands", "LeatherSewingKit (repairs)"],
            "dismantle_tools": ["Hands (pack kit)"],
            "lifetime": "45 days (Stable_dayz)",
            "slots": "Mount Control + Pack Saddlebags",
            "materials": {"leather": 4, "rope": 1},
            "stages": [
                {"name": "Craft Bridle", "cost": "4× TannedLeather + 1× Rope → Bridle"},
                {"name": "Deploy Horse Stable", "cost": "Place Stable_dayz_kit at your compound → Stable_dayz (45-day lifetime)"},
            ],
            "notes": "Pair with Dog Houses (`dog_shed_small_kit` / `dog_shed_big_kit`, 45-day lifetime) from @DayZ-Dog.",
        },
        {
            "id": "docs_animals_trophies",
            "name": "Doc's Animals Trophy Mounts, Skin Rugs & Masks",
            "classname": "Mount / Mount_* / *SkinRug / Mask_*",
            "category": "utility_tack",
            "subcategory": "Hunting Trophies & Rugs",
            "mod": "Doc's Animals (@2886393751)",
            "mod_folder": "@DocsAnimals",
            "kit_recipe": "Mount Base: 2× Wooden Plank + 4× Nail + Animal Head/Fish · Rugs: Pelt Prep",
            "build_tools": ["Hammer / Hatchet (Mount Base)", "Knife (Skinning & Rug/Mask Prep)"],
            "dismantle_tools": ["Hands"],
            "lifetime": "45 days (3,888,000s)",
            "slots": "Cabin Wall Trophies & Floor Rugs",
            "materials": {"planks": 2, "nails": 4},
            "stages": [
                {"name": "Craft Trophy Mount Plaque", "cost": "2× WoodenPlank + 4× Nail → Mount"},
                {"name": "Mount Trophy Head or Fish (18 Types)", "cost": "Combine Mount + Bear, Wolf (Grey/White), Deer, RedDeer, Reindeer, Wildboar, Bull, Goat, Sheep, Pig, Fox, Rabbit, Carp, Mackerel, Trout, or Walleye"},
                {"name": "Animal Skin Rugs (9 Types) & Masks (6 Types)", "cost": "Craft BearSkinRug, WolfSkinRug, DeerSkinRug, WildboarSkinRug, CowSkinRug, GoatSkinRug, SheepSkinRug, FoxSkinRug & Headdress Masks from pelts"},
            ],
            "notes": "Decorate your Hunting Cabin walls and floor; all mounts and rugs persist 45 days.",
        },
        # ---- CATEGORY 6: FARMING (BETTERHARVEST) & COOKZ HOMESTEAD KITCHEN ----
        {
            "id": "farming_betterharvest",
            "name": "Homestead Garden Plot (BetterHarvest Non-Rotting Crops)",
            "classname": "GardenPlot",
            "category": "camp",
            "subcategory": "Farming & CookZ Kitchen",
            "mod": "Vanilla 1.30 + BetterHarvest (@3687735580)",
            "mod_folder": "@BetterHarvest",
            "kit_recipe": "Dig GardenPlot (9 slots) with Shovel, FieldShovel, Pickaxe, or FarmingHoe + Seeds + Water",
            "build_tools": ["Shovel", "FieldShovel", "Pickaxe", "FarmingHoe"],
            "dismantle_tools": ["Shovel (Remove Plot)"],
            "lifetime": "allowPlantSpoilage = 0 (crops never rot on the vine!)",
            "slots": "9 plant slots (GardenPlot) · 10 (MMG Greenhouse) · 3 (MMG Planter Box)",
            "materials": {"lime": 1},
            "stages": [
                {"name": "Fast Crops (22–30 min)", "cost": "Zucchini: 22m 30s (2 base / 5 fertilized, 8 seeds) · Tomato: 27m 30s (2 / 5, 8 seeds) · Cannabis: 30m 00s (3 / 6)"},
                {"name": "Hearty Crops (37–47 min)", "cost": "Bell Pepper: 37m 30s (2 / 5, 12 seeds) · Pumpkin: 47m 30s (2 / 4, 12 seeds) · Potato: 47m 30s (2 / 5)"},
            ],
            "notes": "BetterHarvest_Config.json sets allowPlantSpoilage=0 so ripened crops wait safely until you return from patrol.",
        },
        {
            "id": "cookz_kitchen",
            "name": "CookZ Homestead Canning, Cheese & Sausage Kitchen",
            "classname": "CookZ_Cookbook / CookZ_EmptyCan",
            "category": "camp",
            "subcategory": "Farming & CookZ Kitchen",
            "mod": "CookZ (@3302732231)",
            "mod_folder": "@CookZ",
            "kit_recipe": "Cookbook: 2× Paper · Empty Cans (10×): 1× Metal Sheet + Hacksaw · Drum Peeler: Pot + Hammer",
            "build_tools": ["Hacksaw (10× Empty Cans)", "Hammer (Drum Peeler)", "Pot / FryingPan / Cauldron"],
            "dismantle_tools": [],
            "lifetime": "Cheese, Sausages & Sealed Cans NEVER spoil (EnableCheeseDecay=0, EnableSausageDecay=0)",
            "slots": "80°C Hot Meals · 100% Salmonella/Brain/HeavyMetal Purge",
            "materials": {"metal": 1, "paper": 2},
            "stages": [
                {"name": "Craft Cookbook & Packaging", "cost": "Cookbook: 1× Paper + 1× Paper · 10× Empty Cans: 1× MetalPlate + Hacksaw · Empty Box: 2× Paper or 1× Bark + Knife"},
                {"name": "Non-Spoiling Cheese & Sausages", "cost": "Makeshift Cheese: 2× Lard + 2× PowderedMilk in Pot w/ water · Sausages: 1× Guts + 1× Steak Meat in Pot"},
                {"name": "Sealed Expedition Cans", "cost": "Tactical Bacon Can: 2× PigSteak + 1× Lard + Empty Can · Goulash Can: 2× Potato + 1× Pepper + 1× Steak + Empty Can · Mystery Meat Can: 3× Steak + 1× Lard + Empty Can"},
            ],
            "notes": "Hold the crafted Cookbook in hands to view every pot, frying pan, and cauldron recipe.",
        },
    ]

    pruned_replacements = [
        {
            "pruned_mod": "BaseBuildingPlus (BBP)",
            "active_replacement": "RaG_BaseBuilding (@3157695626) + RaG_Hunting_Cabin (@3117613872)",
            "reason": "Single unified snap-grid system (21 kits / 37 parts, 4 Planks + 10 Nails per kit) plus the complete lockable log Hunting Cabin.",
        },
        {
            "pruned_mod": "BuildAnywhere_v3",
            "active_replacement": "Immersive Placing Update (@3441628354) + cfggameplay.json",
            "reason": "BuildAnywhere_v3 caused a 1.30.164200 script decode crash; Immersive Placing Update provides slant/clip placement and 60m Flag lifetime boost.",
        },
        {
            "pruned_mod": "Code Lock (legacy)",
            "active_replacement": "Vanilla 1.30 DigitalCodeLock + RaG DigitalCodeLock",
            "reason": "DayZ 1.30 ships a native DigitalCodeLock and RaG_Core adds auto-locking, battery-free, access-remembering DigitalCodeLock support.",
        },
        {
            "pruned_mod": "MuchStuffPack (MSP)",
            "active_replacement": "MMG Base Storage (@3210162677)",
            "reason": "Eliminates duplicate locker/crate bloat while keeping 7 craftable storage recipes and 15+ screwdriver-repackable military/industrial kits.",
        },
        {
            "pruned_mod": "Leather Crafting (legacy)",
            "active_replacement": "Vanilla 1.30 CraftLeatherBelt + Horse Expansion (@3297432307)",
            "reason": "DayZ 1.30 added native CraftLeatherBelt; Horse Expansion crafts Saddles (8× TannedLeather) and Bridles (4× TannedLeather + Rope).",
        },
        {
            "pruned_mod": "Simple Ammo Crafting",
            "active_replacement": "Faction Barter Traders (presets/traders.yaml)",
            "reason": "Intentionally disabled so ammunition remains the primary hard currency across Ad Aspera's 5 factions.",
        },
    ]

    guide = {
        "server_rules": {
            "flag_radius_m": int(flag_radius_m),
            "unflagged_placed_hours": unflagged_h,
            "flagged_placed_days": flagged_days,
            "flag_refresh_days": 40,
            "rag_kit_planks": kit_planks,
            "rag_kit_nails": kit_nails,
            "rag_build_time_s": build_time_s,
            "rag_dismantle_time_s": dismantle_time_s,
            "rag_book_crafting": bool(rag_bb.get("EnableBookKitCrafting", 1)),
            "rag_hatch_ladder": bool(rag_bb.get("EnableBuildHatchLadder", 1)),
            "rag_digital_codelock": bool(rag_bb.get("EnableRaGDigitalCodeLock", 1)),
            "codelock_auto_lock": bool(rag_lock.get("AutoLockOnClose", 1)),
            "codelock_require_battery": bool(rag_lock.get("RequireBattery", 0)),
            "codelock_raiding_enabled": bool(rag_lock.get("EnableRaiding", 0)),
            "cabin_kit_planks": cabin_kit_planks,
            "cabin_kit_nails": cabin_kit_nails,
            "cabin_ruin_hammer": bool(rag_cabin.get("RuinHammerAfterBuilt", 1)),
            "cabin_refund_materials": bool(rag_cabin.get("GiveBackMaterialsAfterDismantle", 1)),
            "workbench_nails": wb_nails,
            "workbench_metal": wb_metal,
            "mmg_craft_toggles": {k: (str(v).lower() == "true") for k, v in mmg_cfg.items()},
            "crop_spoilage_enabled": bool(harvest_cfg.get("allowPlantSpoilage", 0)),
            "cookz_cheese_decay": bool(cookz_cfg.get("EnableCheeseDecay", 0)),
            "cookz_sausage_decay": bool(cookz_cfg.get("EnableSausageDecay", 0)),
        },
        "progression": progression,
        "categories": [
            {"id": "all", "label": "All Recipes", "count": len(recipes)},
            {"id": "vanilla", "label": "Vanilla 1.30 Structures", "count": sum(1 for r in recipes if r["category"] == "vanilla")},
            {"id": "rag_modular", "label": "RaG Modular (21 Kits)", "count": sum(1 for r in recipes if r["category"] == "rag_modular")},
            {"id": "cabin", "label": "RaG Hunting Cabin", "count": sum(1 for r in recipes if r["category"] == "cabin")},
            {"id": "mmg_storage", "label": "MMG Storage & Furniture", "count": sum(1 for r in recipes if r["category"] == "mmg_storage")},
            {"id": "utility_tack", "label": "Workbench, Tack & Trophies", "count": sum(1 for r in recipes if r["category"] == "utility_tack")},
            {"id": "camp", "label": "Camp, Farming & CookZ", "count": sum(1 for r in recipes if r["category"] == "camp")},
        ],
        "recipes": recipes,
        "rag_part_costs": part_costs_map,
        "pruned_replacements": pruned_replacements,
    }
    _BASEBUILDING_CACHE = (sig, guide)
    return copy.deepcopy(guide)


_FLEET_CACHE: tuple[tuple[int, ...], dict[str, Any]] | None = None
_SURVIVAL_CACHE: tuple[tuple[int, ...], dict[str, Any]] | None = None
_NPC_DOSSIERS_CACHE: tuple[tuple[int, ...], dict[str, Any]] | None = None


def build_fleet_and_convoys(map_name: str = "nasdara") -> dict[str, Any]:
    """Build the authoritative Fleet, Aviation, and Convoy operations data backed by server configs."""
    global _FLEET_CACHE
    cfg_paths = [
        ROOT / "presets" / "vehicle_events.yaml",
        ROOT / "presets" / "convoys.yaml",
        ROOT / "presets" / "arrivals.yaml",
        ROOT / "presets" / "convoy_routes" / "nasdara" / "rust_supply_run.json",
        ROOT / "presets" / "convoy_routes" / "nasdara" / "jackal_highway_raid.json",
        ROOT / "presets" / "convoy_routes" / "nasdara" / "peacekeeper_escort.json",
        ROOT / "server" / "profiles" / "Zenarchist" / "ZenStaticCarWorkbenchConfig.json",
    ]
    sig = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in cfg_paths)
    if _FLEET_CACHE and _FLEET_CACHE[0] == sig:
        return copy.deepcopy(_FLEET_CACHE[1])

    arrivals_cfg = active.load_yaml("presets/arrivals.yaml")
    vevents_cfg = active.load_yaml("presets/vehicle_events.yaml")
    convoys_cfg = active.load_yaml("presets/convoys.yaml")

    routes_list: list[dict[str, Any]] = []
    routes_dir = ROOT / "presets" / "convoy_routes" / map_name
    for r in convoys_cfg.get("routes", {}).get(map_name, []):
        rf = routes_dir / r["route"]
        d = _read_json_safe(rf)
        from_site = r.get("from", "")
        to_site = r.get("to", "")
        faction = "Rust" if "rust" in r["route"] else "Jackals" if "jackal" in r["route"] else "Peacekeepers"
        color = "#d4775e" if faction == "Rust" else "#db5c4b" if faction == "Jackals" else "#68c0d0"
        amb_idx = int(d.get("AmbushWaypointIndex", 0))
        wps = d.get("Waypoints", [])
        amb_pos = wps[amb_idx] if (0 <= amb_idx < len(wps)) else (wps[len(wps) // 2] if wps else [0.0, 0.0, 0.0])
        amb_site = (
            "Pipeline Corridor Narrows"
            if faction == "Rust"
            else "Highway 1 Overpass Choke"
            if faction == "Jackals"
            else "Wadi Valley Approach"
        )
        brief = (
            "Heavy diesel and water tanker convoy escorted by two armed M1025s. Supplies the southern refineries from the industrial cement works."
            if faction == "Rust"
            else "High-speed raider war party patrolling Highway 1. Aggressive gun trucks targeting lone survivors and refugee columns."
            if faction == "Jackals"
            else "UN Blue Shield relief convoy transporting medical crates, water filters, and rations to northern civilian enclaves."
        )
        routes_list.append({
            "id": r["route"].replace(".json", ""),
            "name": d.get("Name", r["route"]),
            "from_site": from_site,
            "to_site": to_site,
            "faction": faction,
            "color": color,
            "speed_kmh": float(d.get("SpeedKmh", 50.0)),
            "vehicle_slots": d.get("VehicleSlots", []),
            "crew_slots": d.get("CrewSlots", []),
            "ambush_index": amb_idx,
            "ambush_site": amb_site,
            "ambush_pos": amb_pos,
            "waypoints_count": len(wps),
            "waypoints": wps,
            "brief": brief,
        })

    rigs: list[dict[str, Any]] = []

    # Aviation (9 helicopters)
    for cls in arrivals_cfg.get("aircraft", []):
        fuel = (
            60
            if "Mh6" in cls or "LittleBird" in cls
            else 120
            if "Uh1" in cls or "UH1" in cls
            else 180
            if "Mi8" in cls
            else 25
        )
        seats = (
            2
            if "Mh6" in cls or "LittleBird" in cls or "R22" in cls
            else 6
            if "Uh1" in cls or "UH1" in cls
            else 12
            if "Mi8" in cls
            else 1
        )
        cargo = (
            "10x100 Flight Case"
            if "R22" in cls
            else "100 Slots"
            if "Mh6" in cls
            else "200 Slots"
            if "Uh1" in cls or "UH1" in cls
            else "350 Slots"
            if "Mi8" in cls
            else "10 Slots"
        )
        role = (
            "Solo ultralight scout & rapid transport"
            if "Gyrocopter" in cls
            else "Observation, ridge spotting & light trainer"
            if "R22" in cls
            else "Airborne insertion & agile patrol"
            if "LittleBird" in cls or "Mh6" in cls or "MH6" in cls
            else "Tactical squad transport & medical evacuation"
            if "Uh1" in cls or "UH1" in cls
            else "Heavy logistics & bulk cargo transport"
        )
        clean_name = (
            cls.replace("RFFSHeli_", "")
            .replace("Expansion", "")
            .replace("EXT_", "")
            .replace("_", " ")
        )
        rigs.append({
            "class": cls,
            "name": clean_name,
            "category": "aviation",
            "is_aircraft": True,
            "weight": 4,
            "fuel_l": fuel,
            "seats": seats,
            "cargo": cargo,
            "role": role,
            "parts": ["Desert Camo Net", "Wrench", "Jerrycan (Gasoline 100%)", "Key Chain", "Flight Storage Case"],
        })

    # Ground vehicles from arrivals
    for v in arrivals_cfg.get("vehicles", []):
        cls = v["class"]
        is_truck = "Truck" in cls or "GAZ" in cls or "Apocalypse" in cls
        fuel = 150 if "Apocalypse" in cls else 120 if "Truck" in cls else 100 if "GAZ" in cls else 95 if "M1025" in cls else 50
        seats = 2 if is_truck else 4
        cargo = "600 Slots" if is_truck else "200 Slots" if "Offroad" in cls else "150 Slots"
        cat = "heavy" if is_truck else "overland"
        role = (
            "Heavy cargo hauler & mobile compound base"
            if is_truck
            else "All-terrain exploration & squad transit"
        )
        clean_name = (
            cls.replace("CrSk_", "")
            .replace("TP_Apoc_", "")
            .replace("MBM_", "")
            .replace("Expansion", "")
            .replace("_", " ")
        )
        rigs.append({
            "class": cls,
            "name": clean_name,
            "category": cat,
            "is_aircraft": False,
            "weight": v.get("weight", 5),
            "fuel_l": fuel,
            "seats": seats,
            "cargo": cargo,
            "role": role,
            "parts": v.get("parts", []),
        })

    # Light vehicles & Steppe mounts
    rigs.append({
        "class": "Motorbike_01",
        "name": "Enduro Dirtbike 250N",
        "category": "light",
        "is_aircraft": False,
        "weight": 10,
        "fuel_l": 12,
        "seats": 1,
        "cargo": "20 Slots",
        "role": "Fast agile mountain trail runner & scout",
        "parts": ["Motorbike_01_Wheel", "Motorbike_01_Wheel", "SparkPlug", "CarBattery"],
    })
    rigs.append({
        "class": "Motorbike_02",
        "name": "Scout Motorcycle TT650",
        "category": "light",
        "is_aircraft": False,
        "weight": 8,
        "fuel_l": 15,
        "seats": 2,
        "cargo": "30 Slots",
        "role": "Dual-sport overland scout motorcycle",
        "parts": ["Motorbike_02_Wheel", "Motorbike_02_Wheel", "SparkPlug", "CarBattery"],
    })
    rigs.append({
        "class": "Animal_Horse_Brown",
        "name": "Badlands Steppe Horse",
        "category": "mount",
        "is_aircraft": False,
        "weight": 10,
        "fuel_l": 0,
        "seats": 2,
        "cargo": "100 Slots (Horse Bags)",
        "role": "Living desert mount; silent ridge travel & low thermal profile",
        "parts": ["Western Saddle", "Bridle", "Horse Bags", "Horseshoes"],
    })

    mad_max_phases = [
        {
            "phase": 1,
            "title": "Phase 1: Desert Scavengers",
            "desc": "Light scout buggies, civil sedans, road beaters. Scavenge spark plugs, radiators, and tires to establish baseline overland mobility.",
            "threat": "Low (Roaming infected & opportunistic raider scouts)",
        },
        {
            "phase": 2,
            "title": "Phase 2: Raider Encampments",
            "desc": "Armored UAZs, light technicals, road blockade ambushes along Highway 1. Raiders deploy tire spikes and rifle fire.",
            "threat": "Medium (Armed Jackal scout parties & checkpoint ambushes)",
        },
        {
            "phase": 3,
            "title": "Phase 3: Faction Armored Warfare",
            "desc": "Vodniks, M1025 Apocalypse gun trucks, fortified fuel convoys. UN Blue Shield and Rust Syndicate deploy mechanized squads.",
            "threat": "High (Mounted machine guns & armored patrols)",
        },
        {
            "phase": 4,
            "title": "Phase 4: Air Superiority & Logistics",
            "desc": "Airfield control, 9 helicopter fleet deployments, heavy fuel & water tanker convoys. Armed recon helis secure supply drops.",
            "threat": "Severe (Rotary-wing overwatch & anti-air response)",
        },
        {
            "phase": 5,
            "title": "Phase 5: Total Badlands Hegemony",
            "desc": "Armored war rigs, battle wagons, fortress-wide citadel sieges at Qalat-e Lut. High-stakes compound warfare for regional dominance.",
            "threat": "Extreme (Full mechanized faction warfare)",
        },
    ]

    fleet_summary = {
        "total_world_fleet_count": 47,
        "aviation_count": len(arrivals_cfg.get("aircraft", [])),
        "ground_count": len(rigs) - len(arrivals_cfg.get("aircraft", [])),
        "categories": [
            {"id": "all", "label": "All Fleet Rigs", "count": len(rigs)},
            {"id": "aviation", "label": "Aviation & Helis", "count": sum(1 for r in rigs if r["category"] == "aviation")},
            {"id": "heavy", "label": "Heavy Armored & Trucks", "count": sum(1 for r in rigs if r["category"] == "heavy")},
            {"id": "overland", "label": "Overland 4x4s", "count": sum(1 for r in rigs if r["category"] == "overland")},
            {"id": "light", "label": "Light Bikes & Mounts", "count": sum(1 for r in rigs if r["category"] in ("light", "mount"))},
        ],
        "rigs": rigs,
        "convoys": routes_list,
        "mad_max_phases": mad_max_phases,
        "maintenance": {
            "workbench": "Zen's Static Car Workbench (Craft with 60× Nails + 5× Metal Sheets)",
            "workbench_repairs": "Repairs engine blocks, radiators, doors, hoods, trunks, and wheels back to pristine state without replacement parts.",
            "radiators": "Must be filled with 100% clean water; overheating ruins the engine block within 90 seconds in dune heat.",
            "fluids": "Motor oil, gasoline/diesel, and brake fluid maintenance.",
        },
        "security": {
            "keys": "Expansion physical vehicle keys with master pairing (VehicleRequireKeyToStart=1).",
            "lockpicking": "Lockpicks have 10-25% chance per attempt to bypass locks.",
            "car_covers": "CarCover camouflage tarps conceal vehicles in open desert terrain.",
            "towing": "Expansion car-to-car towing cables allow recovery of damaged rigs.",
        },
        "flight_controls": {
            "hosas_bridge": "tools/vkb_pad.py forwards VKB Gladiator sticks to virtual Xbox controller with 0.03 ms median latency.",
            "avionics": "Throttle, collective, cyclic pitch/roll, and anti-torque pedals mapped cleanly for Proton/Linux.",
            "heli_fuel": "Helicopters start with 60-90% fuel and a full Jerrycan attached to their inventory slot.",
        },
    }
    _FLEET_CACHE = (sig, fleet_summary)
    return copy.deepcopy(fleet_summary)


def build_survival_manual(map_name: str = "nasdara") -> dict[str, Any]:
    """Build the authoritative Survival Field Manual backed by server rules and presets."""
    global _SURVIVAL_CACHE
    cfg_paths = [
        ROOT / "presets" / "arrivals.yaml",
        ROOT / "presets" / "survival_goals.yaml",
        ROOT / "server" / "profiles" / "BetterHarvest" / "BetterHarvest_Config.json",
        ROOT / "server" / "mpmissions" / "dayzOffline.nasdara" / "CookZ" / "CookZ_V003.json",
    ]
    sig = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in cfg_paths)
    if _SURVIVAL_CACHE and _SURVIVAL_CACHE[0] == sig:
        return copy.deepcopy(_SURVIVAL_CACHE[1])

    arrivals_cfg = active.load_yaml("presets/arrivals.yaml")
    sg_summary = survival_goals.get_manager().get_summary()

    water_proj = next((p for p in sg_summary.get("projects", []) if p.get("id") == "water_reserves"), None)
    cistern_pct = water_proj.get("percent", 37.0) if water_proj else 37.0
    cistern_perk_active = len(water_proj.get("unlocked_perks", [])) >= 1 if water_proj else True

    manual = {
        "water_system": {
            "hazard": "Untreated badlands surface, well, and river water carries high cholera and fever bacteria. Drinking unboiled water causes dysentery and dehydration within minutes.",
            "purification_methods": [
                {"name": "Chlorine Purification Tablets", "effect": "1 tablet per water bottle/canteen neutralizes all pathogens instantly."},
                {"name": "Boiling over Fireplace / Stove", "effect": "Boiling water inside a cooking pot, kettle, or mess tin completely sterilizes water."},
                {"name": "Qalat-e Lut Cistern Perk", "effect": "Drinking from fountains at Qalat-e Lut carries 0% cholera risk due to the community aquifer project."},
            ],
            "cistern_percent": cistern_pct,
            "cistern_perk_active": cistern_perk_active,
        },
        "agriculture_and_food": {
            "betterharvest": "BetterHarvest mod active: `allowPlantSpoilage = 0`. Crops cultivated in GardenPlots never rot on the vine! Fast harvest cycles (22m Zucchini, 27m Tomato).",
            "cookz": "CookZ mod active: `EnableCheeseDecay = 0`, `EnableSausageDecay = 0`. Smoked sausages, cheese wheels, and canned rations never decay. Jars, lard, and salt provide long-term preservation.",
            "tanning": "Combine raw wild boar/deer pelt + Garden Lime in an intact water barrel to produce Tanned Leather for Bedouin saddles (8×), bridles (4×), and leather belts.",
        },
        "medical_triage": {
            "infection_stages": [
                {"stage": 1, "name": "Dirty Wound", "symptoms": "Minor grunting, wound contamination", "treatment": "Disinfect immediately with AlcoholicTincture or IodineTincture."},
                {"stage": 2, "name": "Wound Sepsis", "symptoms": "Blurry vision, fever, steady health decline", "treatment": "TetracyclineAntibiotics full course required."},
                {"stage": 3, "name": "Septic Shock", "symptoms": "Rapid dehydration, severe unconsciousness", "treatment": "IV SalineBagIV + Epinephrine + repeated Tetracycline."},
            ],
            "fractures": "Splint (crafted from 4 Wooden Sticks + 1 Bandage/Rag) heals broken bones in 15 minutes.",
        },
        "radio_net": {
            "frequency": "87.8 MHz (Settler Net)",
            "hardware": "Personal Radio / Transceiver requires 1x 9V Battery (ensure battery is inserted and radio is turned ON).",
            "bulletins": "Emergency tactical alerts, dust storm warnings, and AI convoy movement updates are broadcast automatically over the air.",
        },
        "respawn_network": {
            "tiers": [
                {"tier": 1, "name": "Qalat-e Lut Fortress HQ", "desc": "All survivors primarily respawn within the fortified citadel perimeter across 13 candidate staging spots."},
                {"tier": 2, "name": "Friend-First Co-op", "desc": "When allies are online, respawn places you within 1-2 km of a living player to ensure seamless co-op without cross-desert treks."},
                {"tier": 3, "name": "Raised Territory Flag", "desc": "Beside your compound's flagpole (up to 40-day active refresh)."},
                {"tier": 4, "name": "Pitched Wilderness Tent", "desc": "Beside any pitched tent within 5 km of death."},
                {"tier": 5, "name": "Roadside Campfire", "desc": "Near your previous death coordinates beside an arrival campfire."},
            ],
        },
        "special_forces_outfit": {
            "chance_percent": 3.0,
            "name": "Soviet Special Forces",
            "gear": "TTsKO or Gorka Summer/Flat, Smersh Vest & Bag, Military Belt, AKS-74U or AS Val with 3 full magazines, Makarov IJ-70 sidearm, combat knife, RGD-5 grenade, medical kit, binoculars, compass.",
        },
        "animal_companions": {
            "spawn_chance_percent": 50.0,
            "dog": {
                "weight_percent": 60.0,
                "classes": ["Doggo_Follow1", "Doggo_Follow2", "Doggo_Follow3", "Doggo_Follow4", "Doggo_Follow5"],
                "gear": ["Ballistic Dog Vest (Black, Sheriff, Camo)", "Dog Collar", "Dog Tag"],
                "instructions": "Tame wild badlands dogs with bones or steaks; whistle commands (Follow, Stay, Heel, Attack); bone summoning item.",
            },
            "horse": {
                "weight_percent": 30.0,
                "breeds": ["Animal_Horse_Brown", "Animal_Horse_Chestnut", "Animal_Horse_Palomino", "Animal_Horse_Appaloosa", "Animal_Horse_Black", "Animal_Horse_Shadow"],
                "tack": ["Western Saddle", "Bridle", "Horse Bags", "Horseshoes"],
                "instructions": "Riding, galloping, jumping obstacles, hitching posts, stamina, feeding apples/hay, whistle recall.",
            },
            "recruit": {
                "weight_percent": 10.0,
                "desc": "Armed friendly settler recruit grouping with the player.",
            },
        },
    }
    _SURVIVAL_CACHE = (sig, manual)
    return copy.deepcopy(manual)


def build_npc_dossiers() -> dict[str, Any]:
    """Build full lore and dialogue dossiers for all 7 Living World NPCs."""
    global _NPC_DOSSIERS_CACHE
    quests_cfg = active.load_yaml("presets/quests.yaml")
    dialog_dir = ROOT / "server" / "profiles" / "DialogFramework" / "Dialogues"
    cfg_paths = [ROOT / "presets" / "quests.yaml"] + [dialog_dir / f"NPC_{i}" / "Dialogue.json" for i in range(1, 8)]
    sig = tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in cfg_paths)
    if _NPC_DOSSIERS_CACHE and _NPC_DOSSIERS_CACHE[0] == sig:
        return copy.deepcopy(_NPC_DOSSIERS_CACHE[1])

    npcs = campaign_gen.load_npc_profiles(quests_cfg)
    dossiers: dict[str, dict[str, Any]] = {}
    for nid, profile in npcs.items():
        dlg_file = dialog_dir / f"NPC_{nid}" / "Dialogue.json"
        dlg_data = _read_json_safe(dlg_file)
        topics: list[dict[str, Any]] = []
        root = next((n for n in dlg_data.get("Nodes", []) if n.get("ID") == dlg_data.get("RootNodeID", 1)), None)
        if root:
            for resp in root.get("Responses", []):
                txt = resp.get("Text")
                if txt and txt not in ("Safe travels.", "Goodbye."):
                    topics.append({
                        "text": txt,
                        "next_node": resp.get("NextNodeID", 0),
                        "action": resp.get("ActionType", "NONE"),
                    })

        dossiers[nid] = {
            "id": int(nid),
            "name": profile["name"],
            "title": profile.get("title", ""),
            "faction": profile.get("faction", "Settlers"),
            "role_site": profile.get("role_site", ""),
            "pos": profile.get("pos", [0.0, 0.0, 0.0]),
            "heading": profile.get("heading", 0.0),
            "greeting": profile.get("greeting", ""),
            "lore": profile.get("lore", ""),
            "standing_info": profile.get("standing_info", ""),
            "survival_tip": profile.get("survival_tip", ""),
            "politics": profile.get("politics", ""),
            "topics": topics,
            "nodes": [
                {
                    "id": n["ID"],
                    "speaker_text": n.get("SpeakerText", ""),
                    "responses": [r.get("Text", "") for r in n.get("Responses", [])],
                }
                for n in dlg_data.get("Nodes", [])
            ],
        }

    _NPC_DOSSIERS_CACHE = (sig, dossiers)
    return copy.deepcopy(dossiers)


class SandboxStore:
    """Holds live + per-user preview WarLedger state per map for the Command Center."""

    def __init__(self) -> None:
        self.ledgers: dict[tuple[str, str], WarLedger] = {}
        self.rng = random.Random()
        self.turn_log: list[dict] = []
        self._road_cache: dict[tuple[str, int], tuple[list[dict], list[dict], list[dict]]] = {}
        self._adm_cache: tuple[tuple, int, list[str], list[dict]] | None = None
        self._audit_cache: dict[tuple, list[dict]] = {}

    def get_ledger(self, map_name: str, reload_disk: bool = False, user_id: str = "operator") -> WarLedger:
        uid = sanitize_user_id(user_id)
        key = (uid, map_name)
        if reload_disk or key not in self.ledgers:
            self.ledgers[key] = WarLedger.load_or_new(map_name)
        return self.ledgers[key]

    def _road_and_arrival_points(self, map_name: str, map_data: dict, arrivals_cfg: dict) -> tuple[list[dict], list[dict], list[dict]]:
        mission = arrivals.mission_dir(map_data)
        spawns_file = mission / "cfgeventspawns.xml"
        mtime = spawns_file.stat().st_mtime_ns if spawns_file.exists() else 0
        key = (map_name, mtime)
        if key in self._road_cache:
            return self._road_cache[key]
        raw_zones = arrivals.exclusion_zones(arrivals_cfg, map_data)
        excl_zones = [{"x": x, "z": z, "radius": r} for x, z, r in raw_zones]
        road_pts: list[dict] = []
        arr_pts: list[dict] = []
        if mtime:
            spots = arrivals.road_spots(mission, arrivals_cfg["road_events"])
            road_pts = [arrivals.point(s) for s in spots if not arrivals.excluded(s, raw_zones)]
            try:
                arr_pts = arrivals.arrival_points(arrivals_cfg, map_data, spots)
            except SystemExit:
                arr_pts = []
        res = (excl_zones, road_pts, arr_pts)
        self._road_cache[key] = res
        return res

    def _adm_telemetry(self, zs: list[zmod.Zone]) -> tuple[int, list[dict], list[dict]]:
        adm_files = sorted((ROOT / "server" / "profiles").glob("*.ADM"))
        sim_file = ROOT / "gm_state" / "sim.ADM"
        if sim_file.exists():
            adm_files.append(sim_file)
        tail_files = adm_files[-4:]
        sig = tuple((str(f), f.stat().st_mtime_ns, f.stat().st_size) for f in tail_files)
        if self._adm_cache and self._adm_cache[0] == sig:
            _, total_count, adm_lines, recent_adm = self._adm_cache
        else:
            adm_lines = [ln for f in tail_files for ln in f.read_text(errors="replace").splitlines()[-500:]]
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
            total_count = len(adm_files)
            self._adm_cache = (sig, total_count, adm_lines, recent_adm)

        audit_key = (sig, tuple(zs))
        if audit_key in self._audit_cache:
            audit_list = self._audit_cache[audit_key]
        else:
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
            self._audit_cache[audit_key] = audit_list
        return total_count, audit_list, recent_adm

    def build_state(
        self,
        map_name: str | None = None,
        user_id: str = "operator",
        is_operator: bool = True,
    ) -> dict:
        map_name = map_name or active.map_name()
        if map_name not in ("nasdara", "chernarusplus"):
            map_name = active.map_name()
        uid = sanitize_user_id(user_id)
        led = self.get_ledger(map_name, user_id=uid)
        map_data = active.map_data(map_name)
        factions_cfg = active.load_yaml("presets/factions.yaml")
        traders_cfg = active.load_yaml("presets/traders.yaml")
        quests_cfg = active.load_yaml("presets/quests.yaml")
        arrivals_cfg = active.load_yaml("presets/arrivals.yaml")
        world_cfg = active.load_yaml("presets/world.yaml")
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
        excl_zones, road_pts, arr_pts = self._road_and_arrival_points(map_name, map_data, arrivals_cfg)

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

        adm_file_count, audit_list, recent_adm = self._adm_telemetry(zs)

        client_panel, server_panel, local_mods = modstring.build_panel_fields(mods_all)
        panel_ok = modstring.PANEL_FILE.exists() and modstring.PANEL_FILE.read_text() == client_panel
        pbo_ok = (ROOT / "build" / "@DZDS" / "addons" / "dzds_scripts.pbo.dzds.bisign").exists()
        arr_ok = (ROOT / "server" / "profiles" / "DZDS" / "arrivals.json").exists()

        # Radio bulletin preview
        bulletin = dzds_profile.build_bulletin(led, traders, quests, world=world_cfg)

        fleet_data = build_fleet_and_convoys(map_name)
        survival_data = build_survival_manual(map_name)
        npc_dossiers = build_npc_dossiers()

        return {
            "active_map": map_name,
            "palette": ui.HEX,
            "session": {
                "user_id": uid,
                "is_operator": bool(is_operator),
                "pwa_version": PWA_VERSION,
                "server_query_address": "23.229.49.100:26092",
            },
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
                "fixed_quests": quests_cfg.get("fixed_quests", {}),
                "npcs": npc_dossiers,
                "currencies": traders_cfg.get("currencies", {}),
            },
            "survival_goals": survival_goals.get_manager().get_summary(),
            "companions": companions.get_manager().get_summary(),
            "fleet": fleet_data,
            "convoys": fleet_data["convoys"],
            "survival_manual": survival_data,
            "npc_dossiers": npc_dossiers,
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
                "adm_file_count": adm_file_count,
                "encounter_audit": audit_list,
                "recent_events": recent_adm,
                "bulletin": bulletin,
                "readiness": {
                    "panel_ok": panel_ok,
                    "pbo_ok": pbo_ok,
                    "arrivals_ok": arr_ok,
                },
            },
            "basebuilding": build_basebuilding_guide(),
        }

    def simulate_turn(
        self,
        map_name: str,
        commit: bool = False,
        user_id: str = "operator",
        is_operator: bool = True,
    ) -> dict:
        uid = sanitize_user_id(user_id)
        led = self.get_ledger(map_name, user_id=uid)
        now = dt.datetime.now() + dt.timedelta(hours=4 * (led.s.turn + 1))
        events = led.turn(now=now, force=True)
        if commit and is_operator:
            led.save()
        return {"events": events, "state": self.build_state(map_name, user_id=uid, is_operator=is_operator)}

    def record_skirmish(
        self,
        map_name: str,
        site: str,
        victim_faction: str,
        killer_faction: str = "Players",
        kills: int = 5,
        user_id: str = "operator",
        is_operator: bool = True,
    ) -> dict:
        uid = sanitize_user_id(user_id)
        led = self.get_ledger(map_name, user_id=uid)
        locs = led.locations()
        pos = locs.get(site)
        if pos:
            for _ in range(max(1, min(25, int(kills)))):
                led.record_death(victim_faction, killer_faction, pos, killer_name="Operator" if killer_faction == "Players" else None)
        return {"state": self.build_state(map_name, user_id=uid, is_operator=is_operator)}

    def reset_preview(
        self,
        map_name: str,
        user_id: str = "operator",
        is_operator: bool = True,
    ) -> dict:
        uid = sanitize_user_id(user_id)
        self.get_ledger(map_name, reload_disk=True, user_id=uid)
        return {"state": self.build_state(map_name, user_id=uid, is_operator=is_operator)}

    def claim_site(
        self,
        map_name: str,
        name: str,
        x: float,
        z: float,
        roles: list[str] | None = None,
        faction: str = "Settlers",
        commit: bool = False,
        user_id: str = "operator",
        is_operator: bool = True,
    ) -> dict:
        uid = sanitize_user_id(user_id)
        led = self.get_ledger(map_name, user_id=uid)
        led.claim(name, [float(x), float(z)], roles or ["inland_town"], faction)
        if commit and is_operator:
            led.save()
        return {"state": self.build_state(map_name, user_id=uid, is_operator=is_operator)}

    def roll_kit(self, archetype_name: str | None = None) -> dict:
        arrivals_cfg = active.load_yaml("presets/arrivals.yaml")
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
PROFILES = UserProfileStore()
SHARES = ShareManager()


UI_HTML_PATH = Path(__file__).with_name("web_ui.html")
PLAYER_PORTAL_HTML_PATH = Path(__file__).with_name("player_portal.html")


def build_portable_html(map_name: str = "nasdara", user_id: str = "operator") -> str:
    """Build a self-contained portable HTML bundle with embedded Nasdara + Chernarus+ states."""
    uid = sanitize_user_id(user_id)
    snapshots = {
        "nasdara": STORE.build_state("nasdara", user_id=uid, is_operator=False),
        "chernarusplus": STORE.build_state("chernarusplus", user_id=uid, is_operator=False),
    }
    prefs = PROFILES.get(uid)
    boot_script = (
        "<script>\n"
        f"window.__DZDS_PORTABLE_SNAPSHOTS__ = {json.dumps(snapshots)};\n"
        f"window.__DZDS_PORTABLE_PREFS__ = {json.dumps(prefs)};\n"
        f"window.__DZDS_PORTABLE_MAP__ = {json.dumps(map_name)};\n"
        "</script>\n</head>"
    )
    html = (
        UI_HTML_PATH.read_text(encoding="utf-8")
        .replace("__DZDS_TOKEN__", "portable-mode")
        .replace("__DZDS_SHARE__", "")
        .replace("__MANIFEST_QUERY__", "")
        .replace("</head>", boot_script, 1)
    )
    return html


def handle_api(
    method: str,
    path: str,
    query: dict[str, list[str]],
    body: dict,
    *,
    user_id: str = "operator",
    is_operator: bool = True,
    port: int = 8787,
    profile_store: UserProfileStore | None = None,
    share_manager: ShareManager | None = None,
) -> tuple[int, dict]:
    """Pure dispatcher for API requests (testable without a socket)."""
    pstore = profile_store or PROFILES
    smgr = share_manager or SHARES
    body_dict = body if isinstance(body, dict) else {}
    map_name = (query.get("map") or [body_dict.get("map") or active.map_name()])[0]
    uid = sanitize_user_id((query.get("user") or [body_dict.get("user_id") or user_id])[0])

    if method == "GET" and path == "/api/state":
        return HTTPStatus.OK, STORE.build_state(map_name, user_id=uid, is_operator=is_operator)
    if method == "GET" and path == "/api/basebuilding":
        return HTTPStatus.OK, build_basebuilding_guide()
    if method == "GET" and path == "/api/fleet":
        return HTTPStatus.OK, build_fleet_and_convoys(map_name)
    if method == "GET" and path == "/api/convoys":
        return HTTPStatus.OK, build_fleet_and_convoys(map_name)["convoys"]
    if method == "GET" and path == "/api/survival-manual":
        return HTTPStatus.OK, build_survival_manual(map_name)
    if method == "GET" and path == "/api/npcs":
        return HTTPStatus.OK, build_npc_dossiers()
    if method == "POST" and path == "/api/simulate-turn":
        return HTTPStatus.OK, STORE.simulate_turn(
            map_name, commit=bool(body.get("commit")), user_id=uid, is_operator=is_operator
        )
    if method == "POST" and path == "/api/skirmish":
        return HTTPStatus.OK, STORE.record_skirmish(
            map_name,
            site=str(body.get("site") or ""),
            victim_faction=str(body.get("victim") or "Jackals"),
            killer_faction=str(body.get("killer") or "Players"),
            kills=int(body.get("kills") or 5),
            user_id=uid,
            is_operator=is_operator,
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
            user_id=uid,
            is_operator=is_operator,
        )
    if method == "POST" and path == "/api/reset-preview":
        return HTTPStatus.OK, STORE.reset_preview(map_name, user_id=uid, is_operator=is_operator)
    if method == "POST" and path == "/api/roll-kit":
        return HTTPStatus.OK, STORE.roll_kit(body.get("archetype"))
    if method == "GET" and path == "/api/survival-goals":
        return HTTPStatus.OK, survival_goals.get_manager().get_summary()
    if method == "POST" and path == "/api/survival-goals/contribute":
        pid = str(body.get("project_id") or "water_reserves")
        try:
            amt = float(body.get("amount") or 10.0)
        except (ValueError, TypeError):
            amt = 10.0
        who = str(body.get("contributor") or "Survivor")
        res = survival_goals.get_manager().record_contribution(pid, amt, contributor=who)
        return HTTPStatus.OK, {"status": "ok", "project": res, "summary": survival_goals.get_manager().get_summary()}

    # Hirable Companions & Qalat-e Lut Garrison API
    if method == "GET" and path == "/api/companions":
        return HTTPStatus.OK, companions.get_manager().get_summary()
    if method == "POST" and path == "/api/companions/hire":
        cid = str(body.get("companion_id") or "soran_scout")
        who = str(body.get("player") or "Survivor")
        notes = str(body.get("notes") or "")
        try:
            res = companions.get_manager().hire_companion(cid, who, notes=notes)
            return HTTPStatus.OK, {"status": "ok", "companion": res, "summary": companions.get_manager().get_summary()}
        except ValueError as e:
            return HTTPStatus.BAD_REQUEST, {"error": str(e)}
    if method == "POST" and path == "/api/companions/dismiss":
        cid = str(body.get("companion_id") or "soran_scout")
        reason = str(body.get("reason") or "Returned to Qalat-e Lut garrison")
        try:
            res = companions.get_manager().dismiss_companion(cid, reason=reason)
            return HTTPStatus.OK, {"status": "ok", "companion": res, "summary": companions.get_manager().get_summary()}
        except ValueError as e:
            return HTTPStatus.BAD_REQUEST, {"error": str(e)}

    # Per-User Persistent Preferences & Settings API
    if method == "GET" and path == "/api/prefs":
        return HTTPStatus.OK, {
            "user_id": uid,
            "is_operator": is_operator,
            "prefs": pstore.get(uid),
        }
    if method == "POST" and path == "/api/prefs":
        if body.get("reset"):
            prefs = pstore.reset(uid)
        else:
            prefs = pstore.update(uid, body.get("prefs") if isinstance(body.get("prefs"), dict) else body)
        return HTTPStatus.OK, {
            "user_id": uid,
            "is_operator": is_operator,
            "saved": True,
            "prefs": prefs,
        }

    # Off-LAN Share Link & Tunnel Management API
    if method == "GET" and path == "/api/share/status":
        return HTTPStatus.OK, smgr.status(port=port, is_operator=is_operator)
    if method == "POST" and path == "/api/share/create":
        if not is_operator:
            return HTTPStatus.FORBIDDEN, {"error": "operator only"}
        entry = smgr.create_link(
            label=str(body.get("label") or "Off-LAN Squad Invite"),
            public_url=str(body.get("public_url") or ""),
            expires_hours=body.get("expires_hours"),
            default_prefs=body.get("default_prefs") if isinstance(body.get("default_prefs"), dict) else None,
        )
        return HTTPStatus.OK, {
            "created": entry,
            "share": smgr.status(port=port, is_operator=True),
        }
    if method == "POST" and path == "/api/share/revoke":
        if not is_operator:
            return HTTPStatus.FORBIDDEN, {"error": "operator only"}
        target = str(body.get("id") or body.get("token") or "")
        revoked = smgr.revoke_link(target)
        return HTTPStatus.OK, {
            "revoked": revoked,
            "share": smgr.status(port=port, is_operator=True),
        }
    if method == "POST" and path == "/api/share/tunnel":
        if not is_operator:
            return HTTPStatus.FORBIDDEN, {"error": "operator only"}
        action = str(body.get("action") or "start")
        if action == "stop":
            return HTTPStatus.OK, smgr.stop_tunnel()
        provider = str(body.get("provider") or "cloudflared")
        custom_url = str(body.get("custom_url") or "")
        return HTTPStatus.OK, smgr.start_tunnel(port=port, provider=provider, custom_url=custom_url)

    return HTTPStatus.NOT_FOUND, {"error": f"Unknown endpoint: {method} {path}"}


handle_request = handle_api


LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
TOKEN_HEADER = "X-DZDS-Token"
SHARE_HEADER = "X-DZDS-Share"
USER_HEADER = "X-DZDS-User"


class DZDSHTTPServer(ThreadingHTTPServer):
    dzds_token: str
    profile_store: UserProfileStore
    share_manager: ShareManager

    def server_close(self) -> None:
        if hasattr(self, "share_manager") and self.share_manager:
            self.share_manager.stop_tunnel()
        super().server_close()


def make_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    profile_store: UserProfileStore | None = None,
    share_manager: ShareManager | None = None,
) -> DZDSHTTPServer:
    """The dashboard server, loopback only, with a per-launch token for state-changing requests.

    The API carries player names and positions and its POSTs rewrite the war ledger, so a web
    page in the operator's browser must not reach it: Host/Origin are checked against loopback
    (DNS rebinding), and every POST needs JSON plus the token the served page embeds (CSRF).
    Off-LAN visitors reach the loopback server only via an explicit tunnel/reverse-proxy with
    an operator-minted cryptographic share token, running in an isolated per-user sandbox.
    """
    if host not in LOOPBACK_HOSTS:
        raise ValueError(f"the dashboard binds to loopback only, not {host!r}")
    server = DZDSHTTPServer((host, port), DashboardHandler)
    server.dzds_token = secrets.token_urlsafe(24)
    server.profile_store = profile_store or PROFILES
    server.share_manager = share_manager or SHARES
    return server


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:
        pass  # Keep console clean

    def _allowed_hosts(self) -> set[str]:
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def _cookie_value(self, name: str) -> str:
        raw = self.headers.get("Cookie")
        if not raw:
            return ""
        try:
            c = SimpleCookie()
            c.load(raw)
            if name in c:
                return c[name].value
        except Exception:
            pass
        return ""

    def _extract_share_token(self) -> str:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if qs.get("share") and qs["share"][0]:
            return qs["share"][0].strip()
        hdr = (self.headers.get(SHARE_HEADER) or "").strip()
        if hdr:
            return hdr
        return self._cookie_value("dzds_share").strip()

    def _extract_user_id(self, is_operator: bool) -> str:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        raw = (
            (qs.get("user") or [""])[0]
            or (self.headers.get(USER_HEADER) or "")
            or self._cookie_value("dzds_uid")
        ).strip()
        if raw and USER_ID_RE.match(raw):
            return raw
        return "operator" if is_operator else "guest_default"

    def _guard(self, post: bool = False) -> tuple[bool, bool, str]:
        """Validate Host/Origin/CSRF or Share Token.

        Returns (allowed, is_operator, active_share_token).
        """
        allowed_loopback = self._allowed_hosts()
        host = self.headers.get("Host", "")
        forwarded = bool(self.headers.get("Cf-Connecting-Ip") or self.headers.get("X-Forwarded-For"))
        smgr: ShareManager = getattr(self.server, "share_manager", SHARES)

        raw_share = self._extract_share_token()
        share_entry = smgr.validate_token(raw_share) if raw_share else None

        is_local_host = (host in allowed_loopback) and not forwarded
        is_operator = is_local_host and share_entry is None

        if not is_local_host and share_entry is None:
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "bad host"})
            return False, False, ""

        origin = self.headers.get("Origin")
        if origin:
            origin_netloc = urlparse(origin).netloc
            allowed_origins = set(allowed_loopback)
            if share_entry is not None and host:
                allowed_origins.add(host)
                allowed_origins.update(smgr.allowed_external_hosts())
            if origin_netloc not in allowed_origins:
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "bad origin"})
                return False, False, ""

        if post:
            if not (self.headers.get("Content-Type") or "").startswith("application/json"):
                self._send_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "JSON only"})
                return False, False, ""
            token = getattr(self.server, "dzds_token", None)
            if not token or not secrets.compare_digest(self.headers.get(TOKEN_HEADER, ""), token):
                self._send_json(HTTPStatus.FORBIDDEN, {"error": "bad token"})
                return False, False, ""

        return True, is_operator, (share_entry["token"] if share_entry else "")

    def _send_json(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(
        self,
        status: int,
        raw: bytes,
        content_type: str,
        *,
        cache: str = "no-store",
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", cache)
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self) -> None:  # noqa: N802
        ok, is_operator, share_token = self._guard()
        if not ok:
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        smgr: ShareManager = getattr(self.server, "share_manager", SHARES)
        pstore: UserProfileStore = getattr(self.server, "profile_store", PROFILES)
        user_id = self._extract_user_id(is_operator)

        if parsed.path in ("/", "/index.html"):
            if share_token:
                smgr.validate_token(share_token, record_visit=True)
            token = getattr(self.server, "dzds_token", "")
            manifest_q = f"?share={share_token}" if share_token else ""
            html = (
                UI_HTML_PATH.read_text(encoding="utf-8")
                .replace("__DZDS_TOKEN__", token)
                .replace("__DZDS_SHARE__", share_token)
                .replace("__MANIFEST_QUERY__", manifest_q)
                .encode("utf-8")
            )
            headers: dict[str, str] = {}
            if share_token:
                headers["Set-Cookie"] = f"dzds_share={share_token}; Path=/; HttpOnly; SameSite=Lax"
            self._send_bytes(HTTPStatus.OK, html, "text/html; charset=utf-8", extra_headers=headers)
            return

        if parsed.path in ("/portal", "/portal/"):
            html = PLAYER_PORTAL_HTML_PATH.read_bytes()
            headers = {}
            if share_token:
                headers["Set-Cookie"] = f"dzds_share={share_token}; Path=/; HttpOnly; SameSite=Lax"
            self._send_bytes(HTTPStatus.OK, html, "text/html; charset=utf-8", extra_headers=headers)
            return

        if parsed.path in ("/manifest.webmanifest", "/manifest.json"):
            manifest_raw = json.dumps(build_manifest(share_token=share_token), indent=2).encode("utf-8")
            self._send_bytes(
                HTTPStatus.OK,
                manifest_raw,
                "application/manifest+json; charset=utf-8",
                cache="no-cache",
            )
            return

        if parsed.path == "/sw.js":
            self._send_bytes(
                HTTPStatus.OK,
                SERVICE_WORKER_JS.encode("utf-8"),
                "application/javascript; charset=utf-8",
                cache="no-cache",
                extra_headers={"Service-Worker-Allowed": "/"},
            )
            return

        if parsed.path == "/icon.svg":
            self._send_bytes(
                HTTPStatus.OK,
                ICON_SVG.encode("utf-8"),
                "image/svg+xml; charset=utf-8",
                cache="public, max-age=3600",
            )
            return

        if parsed.path in ("/icon-192.png", "/icon-512.png", "/icon-maskable-512.png", "/icon-180.png", "/favicon.ico"):
            if parsed.path == "/icon-512.png":
                png = build_pwa_icon_png(512, maskable=False)
            elif parsed.path == "/icon-maskable-512.png":
                png = build_pwa_icon_png(512, maskable=True)
            elif parsed.path == "/icon-180.png":
                png = build_pwa_icon_png(180, maskable=False)
            elif parsed.path == "/favicon.ico":
                png = build_pwa_icon_png(32, maskable=False)
            else:
                png = build_pwa_icon_png(192, maskable=False)
            self._send_bytes(HTTPStatus.OK, png, "image/png", cache="public, max-age=3600")
            return

        if parsed.path == "/preview.png":
            img_path = ROOT / "mods" / "workshop" / "preview.png"
            raw = img_path.read_bytes() if img_path.exists() else build_pwa_icon_png(512, maskable=False)
            self._send_bytes(HTTPStatus.OK, raw, "image/png", cache="public, max-age=3600")
            return

        if parsed.path == "/api/export-portable":
            map_name = (query.get("map") or [active.map_name()])[0]
            portable = build_portable_html(map_name=map_name, user_id=user_id).encode("utf-8")
            self._send_bytes(
                HTTPStatus.OK,
                portable,
                "text/html; charset=utf-8",
                extra_headers={
                    "Content-Disposition": f'attachment; filename="ad-aspera-{map_name}-portable.html"'
                },
            )
            return

        port = self.server.server_address[1]
        status, data = handle_api(
            "GET",
            parsed.path,
            query,
            {},
            user_id=user_id,
            is_operator=is_operator,
            port=port,
            profile_store=pstore,
            share_manager=smgr,
        )
        self._send_json(status, data)

    def do_POST(self) -> None:  # noqa: N802
        ok, is_operator, _share_token = self._guard(post=True)
        if not ok:
            return
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        smgr: ShareManager = getattr(self.server, "share_manager", SHARES)
        pstore: UserProfileStore = getattr(self.server, "profile_store", PROFILES)
        user_id = self._extract_user_id(is_operator)

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            body = {}
        port = self.server.server_address[1]
        status, data = handle_api(
            "POST",
            parsed.path,
            query,
            body,
            user_id=user_id,
            is_operator=is_operator,
            port=port,
            profile_store=pstore,
            share_manager=smgr,
        )
        self._send_json(status, data)


def serve(
    host: str = "127.0.0.1",
    port: int = 8787,
    *,
    share: bool = False,
    public_url: str = "",
) -> None:
    server = make_server(host, port)
    actual_port = server.server_address[1]
    subtitle = f"Listening on http://{host}:{actual_port}  │  PWA Ready  │  Press Ctrl+C to stop"
    if share or public_url:
        st = server.share_manager.start_tunnel(
            port=actual_port,
            provider="custom" if public_url else "cloudflared",
            custom_url=public_url,
        )
        links = st.get("links") or []
        if links:
            subtitle += f"\nOff-LAN Share Link: {links[0]['app_url']}"
    print(ui.banner(
        "WEB TACTICAL COMMAND CENTER",
        subtitle=subtitle,
        right="LIVE PWA",
        width=84,
    ))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
