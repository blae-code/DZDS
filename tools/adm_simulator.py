#!/usr/bin/env python3
"""Write synthetic DayZ .ADM lines so the GM can be developed with no server.

Simulates a few players wandering between named map locations, getting hit by
infected and Expansion AI, occasionally going unconscious or dying. Line formats
mirror vanilla .ADM. Check them against a real log once you have one (`make logs`).

Usage: tools/adm_simulator.py [--out gm_state/sim.ADM] [--map chernarusplus]
                              [--players Host,Buddy] [--rate 2.0] [--seed 1]
"""
from __future__ import annotations

import argparse
import random
import time
import zlib
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
ATTACKERS = [
    ("Infected", "into Torso(12) for 9.8 damage (MeleeInfected)"),
    ("Infected", "into LeftArm(4) for 6.1 damage (MeleeInfectedLong)"),
    ('Player "eAI Raider" (id=Unknown pos=<0, 0, 0>)', "into Torso(12) for 22.4 damage (Bullet_545x39) with AKS-74U from 84.2 meters"),
    ('Player "eAI Guard" (id=Unknown pos=<0, 0, 0>)', "into Head(0) for 31.0 damage (Bullet_762x39) with SKS from 140.6 meters"),
    ("FallDamage", "into LeftLeg(15) for 12.0 damage"),
]


class Sim:
    def __init__(self, players: list[str], locations: dict[str, list[float]], rng: random.Random):
        self.rng = rng
        self.locations = locations
        self.state = {p: {"hp": 100.0, "loc": rng.choice(list(locations)), "online": False}
                      for p in players}

    def pos(self, p: str) -> str:
        x, z = self.locations[self.state[p]["loc"]]
        x += self.rng.uniform(-250, 250)
        z += self.rng.uniform(-250, 250)
        return f"<{x:.1f}, {self.rng.uniform(5, 300):.1f}, {z:.1f}>"

    def step(self) -> list[str]:
        p = self.rng.choice(list(self.state))
        s = self.state[p]
        pid = f"id={zlib.crc32(p.encode()):012d}="
        if not s["online"]:
            s["online"], s["hp"] = True, 100.0
            return [f'Player "{p}" is connected ({pid})']
        r = self.rng.random()
        if r < 0.05:
            s["online"] = False
            return [f'Player "{p}"({pid}) has been disconnected']
        if r < 0.40:
            if self.rng.random() < 0.3:
                s["loc"] = self.rng.choice(list(self.locations))
            s["hp"] = min(100.0, s["hp"] + self.rng.uniform(0, 8))
            return [f'Player "{p}" ({pid} pos={self.pos(p)})']
        by, detail = self.rng.choice(ATTACKERS)
        s["hp"] = max(0.0, s["hp"] - self.rng.uniform(5, 30))
        lines = [f'Player "{p}" ({pid} pos={self.pos(p)})[HP: {s["hp"]:.1f}] hit by {by} {detail}']
        if s["hp"] <= 0:
            killer = by.split('"')[1] if '"' in by else by
            lines.append(f'Player "{p}" (DEAD) ({pid} pos={self.pos(p)}) killed by {killer}')
            s["hp"] = 100.0
            s["loc"] = self.rng.choice(list(self.locations))
        elif s["hp"] < 20 and self.rng.random() < 0.5:
            lines.append(f'Player "{p}" ({pid} pos={self.pos(p)}) is unconscious')
        return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "gm_state" / "sim.ADM"))
    ap.add_argument("--map", default="chernarusplus")
    ap.add_argument("--players", default="Host,Buddy")
    ap.add_argument("--rate", type=float, default=2.0, help="seconds between lines")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--count", type=int, help="write N steps then exit (no sleeping)")
    a = ap.parse_args()

    locations = yaml.safe_load((ROOT / "maps" / f"{a.map}.yaml").read_text())["locations"]
    if not locations:
        raise SystemExit(f"maps/{a.map}.yaml has no locations yet")
    sim = Sim(a.players.split(","), locations, random.Random(a.seed))
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Writing simulated ADM to {out} (Ctrl+C to stop)")
    with out.open("a", encoding="utf-8") as f:
        n = 0
        while a.count is None or n < a.count:
            for line in sim.step():
                stamp = datetime.now().strftime("%H:%M:%S")
                f.write(f"{stamp} | {line}\n")
                f.flush()
                if a.count is None:
                    print(line)
            n += 1
            if a.count is None:
                time.sleep(a.rate)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
