"""The war ledger: persistent faction state that player actions change.

Records AI deaths (from Expansion's LogAIKilled lines in the .ADM) against the nearest named
site, then once per restart advances a "war turn": sites get contested and change hands,
faction strength and resources update, off-screen fighting resolves, and the players' standing
with each faction crosses thresholds that write timed diplomacy overrides. Downstream tools read
the result: patrol_gen (who garrisons what), diplomacy (truces/lockdowns), the GM (war reports).

Faction keys are preset names from presets/factions.yaml (Settlers, Peacekeepers, ...).
"""
from __future__ import annotations

import datetime as dt
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / "gm_state" / "war_ledger.json"
PLAYERS = "Players"


def load_yaml(rel: str):
    return yaml.safe_load((ROOT / rel).read_text())


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
    raids: list[dict] = field(default_factory=list)                     # raids scheduled for next restart
    auto_diplomacy: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)


class WarLedger:
    def __init__(self, state: LedgerState, rules: dict | None = None, factions: dict | None = None,
                 map_data: dict | None = None) -> None:
        self.s = state
        self.rules = rules or load_yaml("presets/ledger.yaml")
        self.factions = factions or load_yaml("presets/factions.yaml")
        self.map = map_data or load_yaml(f"maps/{state.map}.yaml")
        self.fspec = {k: v for k, v in self.factions["factions"].items() if v.get("custom_faction")}
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
            return cls(LedgerState(**json.loads(path.read_text())), **kw)
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
        self._update_strength()
        events += self._update_standing(today)
        events += self._schedule_raids(rng)
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

    def _hero(self, site: str) -> str | None:
        if not self.rules.get("deeds", {}).get("name_players"):
            return None
        d = self.s.deeds.get(site) or {}
        return max(d, key=d.get) if d else None

    def _schedule_raids(self, rng: random.Random) -> list[str]:
        r = self.rules.get("raids")
        self.s.raids = []
        if not r:
            return []
        events = []
        settlements = [s for s, h in self.s.control.items()
                       if s in self.s.extra_sites and h == self.rules["players_fight_for"]]
        for site in settlements:
            raiders = [f for f in self.fspec
                       if self.hostile(f, self.rules["players_fight_for"])
                       and self.s.strength.get(f, 0) >= r["min_strength"]
                       and self.s.standing.get(f, 0) <= r["max_standing"]]
            if not raiders:
                continue
            raider = max(raiders, key=lambda f: self.s.strength.get(f, 0))
            if rng.random() < r["chance"]:
                origin = self._nearest_held(raider, site)
                self.s.raids.append({"faction": raider, "target": site, "origin": origin,
                                     "size": r["size"]})
                events.append(f"Radio intercepts suggest {self._display(raider)} are massing near "
                              f"{origin or 'the hills'} to hit {site}")
        return events

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
        for r in self.s.raids:
            lines.append(f"  Raid scheduled: {r['faction']} from {r['origin']} -> {r['target']}")
        for d in self.s.auto_diplomacy:
            lines.append(f"  Diplomacy until {d['until']}: {d['from']} -> {d['to']} {d['stance']} ({d['why']})")
        return "\n".join(lines)

    def recent_events(self, n: int = 6) -> list[str]:
        return [h["event"] for h in self.s.history[-n:]]
