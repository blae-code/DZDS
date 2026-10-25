#!/usr/bin/env python3
"""Register enabled mods' own CE files in the mission, under presets/mod_loot.yaml's policy.

Reads each mod's shipped types / cfgspawnabletypes files from DAYZ_WORKSHOP_DIR/<id>/, applies the
mod's policy (author values, curated filters, or none), and writes one file per mod and kind to
<mission>/dzds_mods/. It owns the `<ce folder="dzds_mods">` block of cfgeconomycore.xml and
rewrites it every run, so a mod that is disabled or set to `none` disappears from the CE too.

Never registered: classes vanilla db/types.xml.vanilla defines, classes in our dzds/types_dzds.xml
(arrival vehicles and parts), and a class an earlier mod already registered.

Usage: tools/mod_ce.py [--dry-run]
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import active

ROOT = active.ROOT
FOLDER = "dzds_mods"
TIERS = ["Tier1", "Tier2", "Tier3", "Tier4"]


def workshop_dir() -> Path:
    raw = os.environ.get("DAYZ_WORKSHOP_DIR") or "~/.local/share/Steam/steamapps/workshop/content/221100"
    return Path(os.path.expandvars(os.path.expanduser(raw)))


def read_entries(path: Path, root_tag: str) -> list[ET.Element]:
    """<type> elements of a types/spawnabletypes file, tolerating what mods ship: a BOM, several
    root elements (CrSk cars), stray declarations or a missing root."""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    text = re.sub(r"<\?xml[^>]*\?>", "", text)
    text = re.sub(rf"</?{root_tag}\b[^>]*>", "", text)
    return ET.fromstring(f"<{root_tag}>{text}</{root_tag}>").findall("type")


def names_in(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {t.get("name") for t in read_entries(path, "types")}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _scaled(n: int, scale: float) -> int:
    return 0 if n <= 0 else max(1, round(n * scale))


def apply_policy(t: ET.Element, spec: dict) -> ET.Element | None:
    """A copy of type `t` with the mod's filters applied, or None if it must not be registered."""
    t = ET.fromstring(ET.tostring(t))
    nominal_el, min_el = t.find("nominal"), t.find("min")
    nominal = int(float((nominal_el.text or "0").strip())) if nominal_el is not None else 0
    if spec.get("policy") == "curated":
        if spec.get("usages") is not None:
            usages = t.findall("usage")
            for u in usages:
                if u.get("name") not in spec["usages"]:
                    t.remove(u)
            if usages and not t.findall("usage") and nominal > 0:
                return None
        if spec.get("min_tier"):
            floor = TIERS.index(spec["min_tier"])
            values = t.findall("value")
            for v in values:
                if v.get("name") in TIERS and TIERS.index(v.get("name")) < floor:
                    t.remove(v)
            if values and not t.findall("value") and nominal > 0:
                return None
        scale = float(spec.get("nominal_scale", 1.0))
        if scale != 1.0 and nominal_el is not None:
            new = _scaled(nominal, scale)
            nominal_el.text = str(new)
            if min_el is not None:
                old_min = int(float((min_el.text or "0").strip()))
                min_el.text = str(min(_scaled(old_min, scale), new))
    return t


@dataclass
class ModResult:
    mod_id: int
    name: str
    policy: str
    types: list[ET.Element] = field(default_factory=list)
    spawnable: list[ET.Element] = field(default_factory=list)
    skipped: dict[str, int] = field(default_factory=dict)
    note: str = ""

    def skip(self, why: str) -> None:
        self.skipped[why] = self.skipped.get(why, 0) + 1


def build(preset: dict, mods: dict[int, dict], workshop: Path, reserved: set[str]) -> list[ModResult]:
    """Apply every mod's policy. `reserved`: classnames vanilla and dzds already define."""
    taken = set(reserved)
    out = []
    for mod_id, spec in preset["mods"].items():
        mod_id = int(mod_id)
        res = ModResult(mod_id, spec.get("name", str(mod_id)), spec.get("policy", "none"))
        out.append(res)
        m = mods.get(mod_id)
        if res.policy == "none":
            res.note = (spec.get("reason") or "").strip()
            continue
        if not m or not m.get("enabled", True):
            res.policy, res.note = "none", "mod not enabled in config/mods.yaml"
            continue
        d = workshop / str(mod_id)
        if not d.is_dir():
            res.note = f"not downloaded ({d})"
            continue
        files = sorted({p for g in spec.get("types", []) for p in d.glob(g)})
        files = [p for p in files if not any(fnmatch.fnmatch(p.name, x) for x in spec.get("files_exclude", []))]
        if not files:
            res.note = "no types file matched"
        mine: set[str] = set()
        for f in files:
            for t in read_entries(f, "types"):
                n = t.get("name")
                if not n:
                    continue
                if any(fnmatch.fnmatch(n, x) for x in spec.get("exclude", [])):
                    res.skip("excluded")
                elif n in reserved:
                    res.skip("defined by vanilla or dzds")
                elif n in taken:
                    res.skip("duplicate")
                else:
                    kept = apply_policy(t, spec)
                    if kept is None:
                        res.skip("filtered by policy")
                        continue
                    taken.add(n)
                    mine.add(n)
                    res.types.append(kept)
        for g in spec.get("spawnabletypes", []):
            for f in sorted(d.glob(g)):
                res.spawnable += [t for t in read_entries(f, "spawnabletypes") if t.get("name") in mine]
    return out


def write_xml(path: Path, root_tag: str, entries: list[ET.Element]) -> None:
    root = ET.Element(root_tag)
    root.extend(entries)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def ce_block(files: list[tuple[str, str]]) -> str:
    lines = [f'    <ce folder="{FOLDER}">']
    lines += [f'        <file name="{n}" type="{k}" />' for n, k in files]
    lines.append("    </ce>")
    return "\n".join(lines) + "\n"


def register(core: Path, files: list[tuple[str, str]]) -> str:
    """cfgeconomycore.xml text with our block replaced (or removed when `files` is empty)."""
    text = core.read_text()
    text = re.sub(rf'[ \t]*<ce folder="{FOLDER}">.*?</ce>\n?', "", text, flags=re.S)
    if files:
        text = text.replace("</economycore>", ce_block(files) + "</economycore>", 1)
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    preset = active.load_yaml("presets/mod_loot.yaml")
    mods = {int(m["id"]): m for m in active.load_yaml("config/mods.yaml")["mods"]}
    mission = active.mission_dir()
    reserved = names_in(mission / "db" / "types.xml.vanilla") | names_in(mission / "dzds" / "types_dzds.xml")
    results = build(preset, mods, workshop_dir(), reserved)

    out_dir = mission / FOLDER
    files: list[tuple[str, str]] = []
    if not a.dry_run and out_dir.exists():
        shutil.rmtree(out_dir)
    for r in results:
        spawning = [t for t in r.types if int(float((t.findtext("nominal") or "0").strip())) > 0]
        total = sum(int(float((t.findtext("nominal") or "0").strip())) for t in spawning)
        skipped = ", ".join(f"{v} {k}" for k, v in sorted(r.skipped.items()))
        line = f"  {r.policy:<8} {r.name[:34]:<34} {len(r.types):>4} types, {len(spawning):>3} spawn (nominal {total})"
        print(line + (f"; skipped {skipped}" if skipped else "") + (f"  [{r.note}]" if r.note else ""))
        if not r.types:
            continue
        name = f"{slug(r.name)}_types.xml"
        files.append((name, "types"))
        if not a.dry_run:
            write_xml(out_dir / name, "types", r.types)
        if r.spawnable:
            sname = f"{slug(r.name)}_spawnabletypes.xml"
            files.append((sname, "spawnabletypes"))
            if not a.dry_run:
                write_xml(out_dir / sname, "spawnabletypes", r.spawnable)
    core = mission / "cfgeconomycore.xml"
    new = register(core, files)
    if not a.dry_run and new != core.read_text():
        core.write_text(new)
    print(f"{len(files)} file(s) in {FOLDER}/ registered in {core.relative_to(ROOT)}"
          + (" (dry run: nothing written)" if a.dry_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
