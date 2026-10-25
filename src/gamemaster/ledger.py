"""The war ledger: persistent faction state that player actions change.

Records AI deaths (from Expansion's LogAIKilled lines in the .ADM) against the nearest named
site, then once per restart advances a "war turn": sites get contested and change hands,
faction strength and resources update, off-screen fighting resolves, and the players' standing
with each faction crosses thresholds that write timed diplomacy overrides. Downstream tools read
the result: patrol_gen (who garrisons what), diplomacy (truces/lockdowns), the GM (war reports).

Faction keys are preset names from presets/factions.yaml (Settlers, Peacekeepers, ...).
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import logging
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "gm_state" / "war_ledger.json"
PLAYERS = "Players"

_YAML_CACHE: dict[Path, tuple[int, int, object]] = {}


def load_yaml(rel: str | Path):
    """Mtime-cached YAML loader returning a fresh copy so callers may mutate safely."""
    path = Path(rel) if isinstance(rel, Path) else (ROOT / rel)
    if not path.is_absolute():
        path = ROOT / path
    st = path.stat()
    hit = _YAML_CACHE.get(path)
    if hit and hit[0] == st.st_mtime_ns and hit[1] == st.st_size:
        return copy.deepcopy(hit[2])
    parsed = yaml.safe_load(path.read_text())
    _YAML_CACHE[path] = (st.st_mtime_ns, st.st_size, parsed)
    return copy.deepcopy(parsed)


@dataclass
class LedgerState:
    map: str
    turn: int = 0
    last_turn_at: str | None = None
    control: dict[str, str] = field(default_factory=dict)          # site -> faction | "contested"
    extra_sites: dict[str, dict] = field(default_factory=dict)     # claimed: name -> {pos, roles}
    strength: dict[str, float] = field(default_factory=dict)
    standing: dict[str, float] = field(default_factory=dict)
    pressure: dict[str, dict[str, int]] = field(default_factory=dict)   # site -> attacker -> kills
    deaths: dict[str, int] = field(default_factory=dict)                # faction -> deaths this turn
    player_kills: dict[str, int] = field(default_factory=dict)          # faction -> killed by players
    flags: list[str] = field(default_factory=list)
    deeds: dict[str, dict[str, int]] = field(default_factory=dict)      # site -> player -> kills (this turn)
    war_party: dict | None = None                                       # the one movement this restart
    auto_diplomacy: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)


class WarLedger:
    def __init__(self, state: LedgerState, rules: dict | None = None, factions: dict | None = None,
                 map_data: dict | None = None) -> None:
        self.s = state
        self.rules = rules or load_yaml("presets/ledger.yaml")
        self.factions = factions or load_yaml("presets/factions.yaml")
        self.map = map_data or load_yaml(f"maps/{state.map}.yaml")
        convoys = ROOT / "presets" / "convoys.yaml"
        self.convoy_routes = ((load_yaml(convoys) or {}).get("routes") or {}).get(
            state.map) or [] if convoys.exists() else []
        self.fspec = {k: v for k, v in self.factions["factions"].items() if v.get("custom_faction")}
        # Engine factions seen in deaths that map to no ledger faction (e.g. "West" from a mod
        # that fell back to a default): counted, never credited, logged once each.
        self.unmapped: Counter[str] = Counter()
        self.engine_to_name = {}
        for name, spec in self.fspec.items():
            for key in ("custom_faction", "interim_faction"):
                if spec.get(key):
                    self.engine_to_name[spec[key]] = name

    # ---- construction / persistence -------------------------------------------------
    @classmethod
    def new(cls, map_name: str, **kw) -> "WarLedger":
        led = cls(LedgerState(map=map_name), **kw)
        control = led.factions["initial_control"][map_name]
        for faction, sites in control.items():
            for site in sites:
                led.s.control[site] = "contested" if faction == "contested" else faction
        led.s.strength = {f: float(led.rules["strength"]["start"]) for f in led.fspec}
        led.s.standing = {f: float(v) for f, v in led.rules["standing"]["start"].items()}
        return led

    @classmethod
    def load(cls, map_name: str, path: Path = STATE, **kw) -> "WarLedger":
        if path.exists():
            data = json.loads(path.read_text())
            if data.get("map") != map_name:
                raise SystemExit(f"{path} is the {data.get('map')} ledger; run tools/war.py reset for {map_name}")
            known = LedgerState.__dataclass_fields__
            return cls(LedgerState(**{k: v for k, v in data.items() if k in known}), **kw)
        return cls.new(map_name, **kw)

    @classmethod
    def load_or_new(cls, map_name: str, path: Path = STATE, initial: bool = False, **kw) -> "WarLedger":
        """Load the on-disk ledger if it exists and matches `map_name`, else return a fresh ledger."""
        if not initial and path.exists():
            try:
                return cls.load(map_name, path=path, **kw)
            except SystemExit:
                return cls.new(map_name, **kw)
        return cls.new(map_name, **kw)

    def save(self, path: Path = STATE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self.s), indent=2) + "\n")

    # ---- geometry ---------------------------------------------------------------------
    def locations(self) -> dict[str, list[float]]:
        locs = dict(self.map.get("locations") or {})
        locs.update({k: v["pos"] for k, v in self.s.extra_sites.items()})
        return locs

    def site_roles(self, site: str) -> set[str]:
        if site in self.s.extra_sites:
            return set(self.s.extra_sites[site].get("roles", []))
        return {r for r, sites in (self.map.get("roles") or {}).items() if site in (sites or [])}

    def nearest_site(self, pos) -> str | None:
        if not pos:
            return None
        best, best_d = None, float(self.rules["site_radius"]) ** 2
        for name, (x, z, *_) in self.locations().items():
            d = (x - pos[0]) ** 2 + (z - pos[1]) ** 2
            if d <= best_d:
                best, best_d = name, d
        return best if best in self.s.control else None

    # ---- relations ----------------------------------------------------------------------
    def hostile(self, a: str, b: str) -> bool:
        return self.fspec.get(a, {}).get("stance", {}).get(b) == "hostile"

    def name_of(self, engine_or_name: str | None) -> str | None:
        if engine_or_name in (None, ""):
            return None
        if engine_or_name == PLAYERS or engine_or_name in self.fspec:
            return engine_or_name
        return self.engine_to_name.get(engine_or_name)

    # ---- recording ----------------------------------------------------------------------
    def record_death(self, victim: str, killer: str | None, pos, killer_name: str | None = None) -> None:
        """victim/killer: engine faction names (DZDSJackals, Raiders...) or 'Players'.
        killer_name: the player's name when a player made the kill (for named deeds)."""
        v, k = self.name_of(victim), self.name_of(killer)
        for engine, mapped in ((victim, v), (killer, k)):
            if engine and not mapped:
                if not self.unmapped[engine]:
                    log.warning("Faction %r maps to no ledger faction; its deaths are not counted", engine)
                self.unmapped[engine] += 1
        if not v:
            return
        self.s.deaths[v] = self.s.deaths.get(v, 0) + 1
        if k == PLAYERS:
            self.s.player_kills[v] = self.s.player_kills.get(v, 0) + 1
        site = self.nearest_site(pos)
        if site and k == PLAYERS and killer_name:
            self.s.deeds.setdefault(site, {})
            self.s.deeds[site][killer_name] = self.s.deeds[site].get(killer_name, 0) + 1
        if site and k and k != v:
            attacker = self.rules["players_fight_for"] if k == PLAYERS else k
            if attacker == v:
                return  # players killing settlers doesn't give settlers pressure
            self.s.pressure.setdefault(site, {})
            self.s.pressure[site][attacker] = self.s.pressure[site].get(attacker, 0) + 1

    def claim(self, name: str, pos: list[float], roles: list[str], faction: str | None = None) -> None:
        """Register a player settlement (or any new site) as held by `faction`."""
        self.s.extra_sites[name] = {"pos": [float(pos[0]), float(pos[1])], "roles": roles}
        self.s.control[name] = faction or self.rules["players_fight_for"]

    def record_quest_completion(self, quest_name_or_key: str, player_name: str,
                                site: str | None = None) -> list[str]:
        """Record a completed quest contract and apply its world-changing impact."""
        quests_cfg = load_yaml("presets/quests.yaml")
        templates = quests_cfg.get("templates") or {}
        matched_key = None
        for k, t in templates.items():
            if k == quest_name_or_key or str(t.get("id")) == str(quest_name_or_key):
                matched_key = k
                break
            if t.get("title") and t["title"].split(":")[0].strip().lower() in quest_name_or_key.lower():
                matched_key = k
                break
        if not matched_key:
            matched_key = quest_name_or_key if quest_name_or_key in templates else "break_the_siege"

        spec = templates.get(matched_key, {})
        impact = spec.get("ledger_impact") or {}
        events = []

        if not site:
            if spec.get("target") == "contested":
                contested = [s for s, h in self.s.control.items() if h == "contested"]
                site = contested[0] if contested else "Northern Dam"
            elif spec.get("target") == "held_by:Jackals":
                jackal_sites = [s for s, h in self.s.control.items() if h == "Jackals"]
                site = jackal_sites[0] if jackal_sites else "North Highway Pileup"
            else:
                site = "Settler Haven"

        if "pressure" in impact and site:
            attacker = self.rules.get("players_fight_for", "Settlers")
            self.s.pressure.setdefault(site, {})
            self.s.pressure[site][attacker] = self.s.pressure[site].get(attacker, 0) + int(impact["pressure"])
            events.append(f"{player_name} applied {impact['pressure']} liberation pressure for the Settlers at {site}")

        for faction, delta in (impact.get("standing") or {}).items():
            old = self.s.standing.get(faction, 0.0)
            self.s.standing[faction] = max(-100.0, min(100.0, old + delta))

        for faction, delta in (impact.get("strength") or {}).items():
            old = self.s.strength.get(faction, 50.0)
            self.s.strength[faction] = max(0.0, min(100.0, old + delta))

        deed_n = int(impact.get("deeds", 1))
        if site and player_name:
            self.s.deeds.setdefault(site, {})
            self.s.deeds[site][player_name] = self.s.deeds[site].get(player_name, 0) + deed_n

        title = spec.get("title", matched_key).format(site=site)
        ev_msg = f"{player_name} completed campaign contract '{title}' at {site}"
        events.append(ev_msg)
        self.s.history.append({
            "turn": self.s.turn,
            "date": dt.date.today().isoformat(),
            "event": ev_msg,
        })
        self.s.history = self.s.history[-200:]
        return events

    # ---- derived views ------------------------------------------------------------------
    def holders(self) -> dict[str, list[str]]:
        """Same shape as factions.yaml initial_control: faction -> sites, plus 'contested'."""
        out: dict[str, list[str]] = {}
        for site, holder in self.s.control.items():
            out.setdefault(holder, []).append(site)
        return out

    def resources(self, faction: str) -> Counter:
        res = Counter()
        for site, holder in self.s.control.items():
            if holder != faction:
                continue
            roles = self.site_roles(site)
            for r, spec in self.factions.get("resources", {}).items():
                if roles & set(spec["from_roles"]):
                    res[r] += 1
        return res

    # ---- the war turn -------------------------------------------------------------------
    def turn(self, today: dt.date | None = None, now: dt.datetime | None = None,
             force: bool = False) -> list[str]:
        now = now or dt.datetime.now()
        today = today or now.date()
        if self.s.last_turn_at and not force:
            last = dt.datetime.fromisoformat(self.s.last_turn_at)
            if (now - last).total_seconds() < 3600 * self.rules["min_hours_between_turns"]:
                return []
        self.s.turn += 1
        rng = random.Random(self.s.turn if self.rules["offscreen"]["seed_from_turn"] else None)
        events: list[str] = []
        events += self._resolve_pressure()
        events += self._offscreen(rng)
        events += self._keep_front(rng)
        self._update_strength()
        events += self._update_standing(today)
        events += self._schedule_war_party(rng)
        self.s.pressure, self.s.deaths, self.s.player_kills, self.s.deeds = {}, {}, {}, {}
        self.s.auto_diplomacy = [d for d in self.s.auto_diplomacy
                                 if dt.date.fromisoformat(d["until"]) >= today]
        self.s.last_turn_at = now.isoformat(timespec="seconds")
        for e in events:
            self.s.history.append({"turn": self.s.turn, "date": today.isoformat(), "event": e})
        self.s.history = self.s.history[-200:]
        return events

    def _resolve_pressure(self) -> list[str]:
        c = self.rules["control"]
        events = []
        for site, attackers in self.s.pressure.items():
            holder = self.s.control.get(site)
            ranked = sorted(attackers.items(), key=lambda kv: kv[1], reverse=True)
            top, top_n = ranked[0]
            second_n = ranked[1][1] if len(ranked) > 1 else 0
            if holder not in ("contested", None) and top != holder and top_n >= c["pressure_to_contest"]:
                events.append(f"{self._display(top)} broke the {self._display(holder)} hold on {site}; "
                              f"it is now contested")
                self.s.control[site] = "contested"
                holder = "contested"
            if holder == "contested" and top_n >= c["hold_min_pressure"] and top_n >= c["hold_dominance"] * max(1, second_n):
                self.s.control[site] = top
                hero = self._hero(site) if top == self.rules["players_fight_for"] else None
                events.append(f"{hero}'s militia drove the defenders out of {site}; the Frontier Settlers hold it now"
                              if hero else f"{self._display(top)} took {site}")
        return events

    def _offscreen(self, rng: random.Random) -> list[str]:
        o = self.rules["offscreen"]
        events = []
        for site, holder in sorted(self.s.control.items()):
            if site in self.s.pressure:
                continue  # players or AI already decided this one this turn
            roles = self.site_roles(site)
            fits = [f for f, spec in self.fspec.items() if roles & set(spec.get("holds_roles", []))]
            if holder == "contested":
                if not fits:
                    continue
                best = max(fits, key=lambda f: self.s.strength.get(f, 0))
                if rng.random() < o["take_contested_chance"] * self.s.strength.get(best, 0) / 100:
                    self.s.control[site] = best
                    events.append(f"{self._display(best)} secured {site} (no witnesses)")
                continue
            rivals = [f for f in fits if f != holder and self.hostile(f, holder)]
            if not rivals or site in self.s.extra_sites:
                continue  # player settlements only fall to real fighting
            rival = max(rivals, key=lambda f: self.s.strength.get(f, 0))
            edge = (self.s.strength.get(rival, 0) - self.s.strength.get(holder, 0)) / 100
            if edge > 0 and rng.random() < o["contest_held_chance"] * edge:
                self.s.control[site] = "contested"
                events.append(f"{self._display(rival)} are pushing on {self._display(holder)}-held {site}")
        return events

    def _fits(self, site: str) -> list[str]:
        roles = self.site_roles(site)
        return [f for f, spec in sorted(self.fspec.items()) if roles & set(spec.get("holds_roles", []))]

    def _warzone_usable(self, site: str) -> bool:
        """Mirror of the War Zones team rule (tools/zone_events._teams): a fitting faction exists and the
        strongest one (strength desc, name) has a hostile custom rival."""
        fits = sorted(self._fits(site), key=lambda f: (-self.s.strength.get(f, 0), f))
        return bool(fits) and any(f != fits[0] and self.hostile(fits[0], f) for f in self.fspec)

    def _keep_front(self, rng: random.Random) -> list[str]:
        """Spec 4.1: the war never freezes. Keep min..max sites contested after each turn."""
        cfg = self.rules.get("front") or {}
        lo, hi = cfg.get("min_contested", 0), cfg.get("max_contested", 10 ** 6)
        events: list[str] = []

        def contested() -> list[str]:
            return sorted(s for s, h in self.s.control.items() if h == "contested")

        skip: set[str] = set()
        while len(contested()) > hi:
            pool = [s for s in contested() if s not in skip]
            if not pool:
                break
            site = min(pool, key=lambda s: (sum(self.s.pressure.get(s, {}).values()), s))
            fits = self._fits(site)
            if not fits:
                skip.add(site)
                continue
            best = max(fits, key=lambda f: (self.s.strength.get(f, 0), -fits.index(f)))
            self.s.control[site] = best
            events.append(f"{self._display(best)} secured {site} as the fighting moved elsewhere")
        while len(contested()) < lo:
            # Strict: a rival whose holds_roles fit the site. Relaxed (only when no strict site exists,
            # e.g. Nasdara where each role has exactly one claimant): any hostile faction may push.
            strict, relaxed, usable = [], [], []
            for site, holder in sorted(self.s.control.items()):
                if holder not in self.fspec or site in self.s.extra_sites:
                    continue
                if any(f != holder and self.hostile(f, holder) for f in self._fits(site)):
                    strict.append(site)
                if any(f != holder and self.hostile(f, holder) for f in sorted(self.fspec)):
                    relaxed.append(site)
                    if self._warzone_usable(site):
                        usable.append(site)
            cands = strict or usable or relaxed
            if not cands:
                break
            site = rng.choice(cands)
            holder = self.s.control[site]
            rivals = [f for f in (self._fits(site) if strict else sorted(self.fspec))
                      if f != holder and self.hostile(f, holder)]
            rival = max(rivals, key=lambda f: (self.s.strength.get(f, 0), -rivals.index(f)))
            self.s.control[site] = "contested"
            events.append(f"{self._display(rival)} are pushing on {self._display(holder)}-held {site}")
        return events

    def _hero(self, site: str) -> str | None:
        if not self.rules.get("deeds", {}).get("name_players"):
            return None
        d = self.s.deeds.get(site) or {}
        return max(d, key=d.get) if d else None

    def war_party_candidates(self) -> list[dict]:
        us = self.rules["players_fight_for"]
        cfg, r = self.rules["war_party"], self.rules["raids"]
        out: list[dict] = []
        for site, holder in sorted(self.s.control.items()):
            if site in self.s.extra_sites and holder == us:
                for f in sorted(self.fspec):
                    if (self.hostile(f, us) and self.s.strength.get(f, 0) >= r["min_strength"]
                            and self.s.standing.get(f, 0) <= r["max_standing"]):
                        origin = self._nearest_held(f, site)
                        if origin:
                            out.append({"kind": "raid", "faction": f, "origin": origin,
                                        "target": site, "size": list(r["size"])})
        for site, holder in sorted(self.s.control.items()):
            if holder != "contested":
                continue
            roles = self.site_roles(site)
            for f, spec in sorted(self.fspec.items()):
                if not roles & set(spec.get("holds_roles", [])):
                    continue
                if self.s.strength.get(f, 0) < cfg["min_strength"]:
                    continue
                origin = self._nearest_held(f, site)
                if origin:
                    out.append({"kind": "offensive", "faction": f, "origin": origin,
                                "target": site, "size": list(cfg["size"])})
        for rt in self.convoy_routes:
            f = self.s.control.get(rt["from"])
            if f in self.fspec and self.s.control.get(rt["to"]) == f:
                out.append({"kind": "convoy", "faction": f, "origin": rt["from"],
                            "target": rt["to"], "route": rt["route"], "size": [0, 0]})
        return out

    def _schedule_war_party(self, rng: random.Random) -> list[str]:
        self.s.war_party = None
        cands = self.war_party_candidates()
        if not cands or rng.random() >= self.rules["war_party"]["chance"]:
            return []
        wp = cands[rng.randrange(len(cands))]
        self.s.war_party = wp
        who = self._display(wp["faction"])
        if wp["kind"] == "raid":
            return [f"Radio intercepts suggest {who} are massing near {wp['origin']} to hit {wp['target']}"]
        if wp["kind"] == "convoy":
            return [f"{who} trucks are moving between {wp['origin']} and {wp['target']}"]
        return [f"{who} are moving out of {wp['origin']} toward {wp['target']}"]

    def _nearest_held(self, faction: str, target: str) -> str | None:
        locs = self.locations()
        tx, tz = locs[target][:2]
        held = [s for s, h in self.s.control.items() if h == faction and s in locs]
        return min(held, key=lambda s: (locs[s][0] - tx) ** 2 + (locs[s][1] - tz) ** 2) if held else None

    def _update_strength(self) -> None:
        st = self.rules["strength"]
        for f in self.fspec:
            gain = st["regen_per_turn"] + st["per_resource_site"] * sum(self.resources(f).values())
            loss = st["loss_per_death"] * self.s.deaths.get(f, 0)
            self.s.strength[f] = max(0.0, min(100.0, self.s.strength.get(f, st["start"]) + gain - loss))

    def _update_standing(self, today: dt.date) -> list[str]:
        sr = self.rules["standing"]
        events = []
        before = dict(self.s.standing)
        for victim, n in self.s.player_kills.items():
            self.s.standing[victim] = self.s.standing.get(victim, 0) + sr["player_kill"] * n
            for other in self.fspec:
                if other != victim and self.hostile(other, victim):
                    self.s.standing[other] = self.s.standing.get(other, 0) + sr["enemy_bonus"] * n
        for f, start in sr["start"].items():
            cur = self.s.standing.get(f, start)
            step = min(sr["decay_per_turn"], abs(cur - start))
            cur += step if cur < start else -step
            self.s.standing[f] = max(-100.0, min(100.0, cur))
        for th in sr["thresholds"]:
            f = th["faction"]
            old, new = before.get(f, sr["start"].get(f, 0)), self.s.standing.get(f, 0)
            crossed = (("below" in th and old >= th["below"] > new)
                       or ("above" in th and old <= th["above"] < new))
            if not crossed:
                continue
            events.append(th["event"])
            if th.get("flag") and th["flag"] not in self.s.flags:
                self.s.flags.append(th["flag"])
            until = (today + dt.timedelta(days=th["days"])).isoformat()
            for ov in th.get("overrides", []):
                self.s.auto_diplomacy.append({**ov, "until": until, "why": th["event"]})
        return events

    def _display(self, name: str) -> str:
        spec = self.fspec.get(name)
        return spec.get("display", name).split(" (")[0] if spec else name

    # ---- reporting ----------------------------------------------------------------------
    def report(self) -> str:
        lines = [f"War ledger: {self.s.map}, turn {self.s.turn}"]
        for faction, sites in sorted(self.holders().items()):
            label = "Contested" if faction == "contested" else self._display(faction)
            lines.append(f"  {label:<28} {', '.join(sorted(sites))}")
        lines.append("  Strength: " + ", ".join(f"{f} {v:.0f}" for f, v in self.s.strength.items()))
        lines.append("  Standing with players: " + ", ".join(f"{f} {v:+.0f}" for f, v in self.s.standing.items()))
        if self.s.war_party:
            wp = self.s.war_party
            lines.append(f"  War party: {wp['kind']} {wp['faction']} {wp['origin']} -> {wp['target']}")
        for d in self.s.auto_diplomacy:
            lines.append(f"  Diplomacy until {d['until']}: {d['from']} -> {d['to']} {d['stance']} ({d['why']})")
        return "\n".join(lines)

    def recent_events(self, n: int = 6) -> list[str]:
        return [h["event"] for h in self.s.history[-n:]]
