"""One place decides which map the tools act on (Badlands relaunch, 2026-10-15)."""
import re

import active


def test_env_overrides_default(monkeypatch):
    monkeypatch.setenv("GM_MAP", "chernarusplus")
    monkeypatch.delenv("MISSION_NAME", raising=False)
    assert active.map_name() == "chernarusplus"
    assert active.mission_name() == "dayzOffline.chernarusplus"
    assert active.mission_dir() == active.ROOT / "server" / "mpmissions" / "dayzOffline.chernarusplus"


def test_default_map_has_a_map_file(monkeypatch):
    monkeypatch.delenv("GM_MAP", raising=False)
    assert (active.ROOT / "maps" / f"{active.DEFAULT_MAP}.yaml").exists()
    assert active.map_name() == active.DEFAULT_MAP


def test_mission_name_env_wins_only_for_the_active_map(monkeypatch):
    monkeypatch.setenv("GM_MAP", "chernarusplus")
    monkeypatch.setenv("MISSION_NAME", "custom.mission")
    assert active.mission_name() == "custom.mission"
    assert active.mission_name("chernarusplus") == "dayzOffline.chernarusplus"


def test_no_tool_hardcodes_a_default_map():
    pat = re.compile(r"""environ\.get\(\s*["'](GM_MAP|MISSION_NAME)["']\s*,""")
    offenders = [p.name for p in (active.ROOT / "tools").glob("*.py")
                 if p.name != "active.py" and pat.search(p.read_text())]
    assert offenders == []


def test_gamemaster_falls_back_to_active_map():
    src = (active.ROOT / "src" / "gamemaster" / "gm_orchestrator.py").read_text()
    assert "chernarusplus" not in src
    import gamemaster.gm_orchestrator as gm
    assert gm.active is active
