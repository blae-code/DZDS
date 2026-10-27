"""Test suite for Nasdara Geocaching system, ensuring 20 unique stashes,
valid coordinates, verified item classnames, and strict immersion guardrails."""

import json
from pathlib import Path
import yaml

from tools.geocaches import ROOT, PRESET, OUT, MISSION, load_all_known_types, compile_geocaches


def test_geocaches_yaml_structure_and_count():
    assert PRESET.exists(), "presets/geocaches.yaml must exist"
    data = yaml.safe_load(PRESET.read_text(encoding="utf-8"))
    caches = data.get("geocaches", [])
    assert len(caches) == 20, f"Expected exactly 20 geocaches, got {len(caches)}"

    ids = [c["id"] for c in caches]
    assert sorted(ids) == list(range(1, 21)), "Geocache IDs must be 1 to 20 without gaps or duplicates"


def test_geocaches_coordinates_within_nasdara_bounds():
    data = yaml.safe_load(PRESET.read_text(encoding="utf-8"))
    caches = data.get("geocaches", [])

    for c in caches:
        cid = c["id"]
        parts = [float(x) for x in c["pos"].split()]
        assert len(parts) == 3, f"Geocache {cid} position must be a 3D vector string"
        x, y, z = parts
        assert 0 <= x <= 16384, f"Geocache {cid} X={x} out of bounds"
        assert 0 <= z <= 16384, f"Geocache {cid} Z={z} out of bounds"
        assert y >= 100, f"Geocache {cid} Y={y} unexpectedly below terrain level"


def test_geocaches_item_classnames_registered_in_mission():
    data = yaml.safe_load(PRESET.read_text(encoding="utf-8"))
    caches = data.get("geocaches", [])
    known = load_all_known_types(MISSION)

    for c in caches:
        cid = c["id"]
        assert c["container"] in known, f"Cache {cid} container '{c['container']}' not found in mission types"
        for item in c.get("items", []):
            assert item in known, f"Cache {cid} item '{item}' not found in mission types"


def test_immersion_guardrails_no_forbidden_branding():
    data = yaml.safe_load(PRESET.read_text(encoding="utf-8"))
    caches = data.get("geocaches", [])
    forbidden = ["vault", "pipboy", "pip_boy", "nuka", "cybertruck", "tesla"]

    for c in caches:
        combined = (c["landmark"] + " " + " ".join(c.get("items", []))).lower()
        for term in forbidden:
            assert term not in combined, f"Immersion guardrail violated: found '{term}' in cache {c['id']}"


def test_compiled_json_matches_preset():
    compiled = compile_geocaches(dry_run=False)
    assert OUT.exists()
    disk_data = json.loads(OUT.read_text(encoding="utf-8"))
    assert len(disk_data["Geocaches"]) == 20
    assert disk_data == compiled


def test_init_c_integrates_geocache_manager():
    init_file = MISSION / "init.c"
    content = init_file.read_text(encoding="utf-8")
    assert "class DZDSGeocacheManager" in content
    assert "DZDSGeocacheManager.Init();" in content
    assert "DZDSGeocacheManager.AssignGeocaches(" in content
    assert "GPSReceiver" in content
