from tools.clean_server import classify_entry, format_size, CleanupItem

T0 = 1_780_000_000.0  # reference timestamp


def test_format_size():
    assert format_size(500) == "500 B"
    assert format_size(2048) == "2.0 KB"
    assert format_size(10 * 1024 * 1024) == "10.0 MB"
    assert format_size(5 * 1024 * 1024 * 1024) == "5.00 GB"


def test_protected_items_never_classified():
    enabled = {"12345"}
    disabled = {"99999": "OldMod"}

    for name in ["serverDZ.cfg", "DayZServer", "keys", "dta", "addons", "battleye"]:
        res = classify_entry(name, 1000, T0, is_dir=False, enabled_ids=enabled, disabled_mods=disabled, now_ts=T0)
        assert res is None, f"{name} should be protected"


def test_active_mods_never_classified():
    enabled = {"3702420204", "1564026768"}
    disabled = {"3359682865": "UAZ_452"}

    # Enabled mod folder must be protected
    res = classify_entry("@3702420204", 1000, T0, is_dir=True, enabled_ids=enabled, disabled_mods=disabled, now_ts=T0)
    assert res is None

    # Disabled mod folder is classified
    res2 = classify_entry("@3359682865", 1000, T0, is_dir=True, enabled_ids=enabled, disabled_mods=disabled, now_ts=T0)
    assert res2 is not None
    assert res2.category == "disabled-mods"
    assert "UAZ_452" in res2.description


def test_core_dumps():
    enabled = set()
    disabled = {}

    item = classify_entry("core.1096", 9_000_000_000, T0, is_dir=False, enabled_ids=enabled, disabled_mods=disabled)
    assert item is not None
    assert item.category == "cores"
    assert item.path == "core.1096"
    assert item.size == 9_000_000_000


def test_stale_and_fresh_start():
    enabled = set()
    disabled = {}

    stale = classify_entry("stale-3210162677-20261026", 4096, T0, is_dir=True, enabled_ids=enabled, disabled_mods=disabled)
    assert stale is not None
    assert stale.category == "stale"

    fresh = classify_entry("fresh-start-20261016", 4096, T0, is_dir=True, enabled_ids=enabled, disabled_mods=disabled)
    assert fresh is not None
    assert fresh.category == "fresh-start"


def test_profiles_crash_dumps_and_logs():
    enabled = set()
    disabled = {}

    # Crash dump (.mdmp)
    mdmp = classify_entry("DayZServer_2026-10-22.mdmp", 500_000, T0, is_dir=False, enabled_ids=enabled, disabled_mods=disabled, parent="profiles")
    assert mdmp is not None
    assert mdmp.category == "crash-dumps"
    assert mdmp.path == "profiles/DayZServer_2026-10-22.mdmp"

    # Recent log (1 day old) vs old log (10 days old)
    recent = classify_entry("DayZServer.RPT", 1000, T0 - 86400, is_dir=False, enabled_ids=enabled, disabled_mods=disabled, parent="profiles", now_ts=T0, log_days=7)
    assert recent is None

    old_rpt = classify_entry("DayZServer_2026-10-01.RPT", 1000, T0 - 10 * 86400, is_dir=False, enabled_ids=enabled, disabled_mods=disabled, parent="profiles", now_ts=T0, log_days=7)
    assert old_rpt is not None
    assert old_rpt.category == "old-logs"

    old_crash = classify_entry("crash_2026-10-01_12-00-00.log", 1000, T0 - 10 * 86400, is_dir=False, enabled_ids=enabled, disabled_mods=disabled, parent="profiles", now_ts=T0, log_days=7)
    assert old_crash is not None
    assert old_crash.category == "old-logs"

