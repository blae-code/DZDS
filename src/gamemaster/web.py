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
import front_plan  # noqa: E402
import modstring  # noqa: E402
import patrol_gen  # noqa: E402
import status as status_mod  # noqa: E402
import ui  # noqa: E402
import zones as zmod  # noqa: E402
from .adm import parse_line  # noqa: E402
from .ledger import STATE, WarLedger  # noqa: E402


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
            if -1 <= dv <= 5:
                out["default_view"] = dv
        except (TypeError, ValueError):
            pass
    if "last_view" in updates:
        try:
            lv = int(updates["last_view"])
            if 0 <= lv <= 5:
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
            entry = {
                "id": link_id,
                "token": token,
                "label": clean_label,
                "public_url": clean_url or self.active_public_url,
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
                "name": "Install, Run & Off-LAN Share",
                "short_name": "App & Share",
                "description": "PWA install guide, off-LAN share link generator, and persistent settings",
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
    map_name = (query.get("map") or [body.get("map") or active.map_name()])[0]
    uid = sanitize_user_id((query.get("user") or [body.get("user_id") or user_id])[0])

    if method == "GET" and path == "/api/state":
        return HTTPStatus.OK, STORE.build_state(map_name, user_id=uid, is_operator=is_operator)
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
