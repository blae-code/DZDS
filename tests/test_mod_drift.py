from pathlib import Path

import mod_drift as md

T0 = 1_780_000_000.0  # server install time


def files(pbo_size: int, mtime: float = T0) -> md.Files:
    return {
        "addons/kan_survivornpc.pbo": (pbo_size, mtime),
        "addons/kan_survivornpc.pbo.kan.bisign": (556, mtime),
        "keys/kan.bikey": (156, mtime),
        "readme.md": (5000, mtime),
    }


def test_missing_folder():
    assert md.classify(None, files(1), None)[0] == "MISSING"
    assert md.classify({"readme.md": (1, T0)}, None, None)[0] == "MISSING"


def test_identical_and_not_updated_is_ok():
    assert md.classify(files(100), files(100, T0 + 50_000), int(T0) - 10) == ("OK", "")


def test_client_pbo_differs():
    # The 2026-10-08 incident: client had the new 1,196,830-byte pbo, server the old one.
    status, detail = md.classify(files(1_185_837), files(1_196_830, T0 + 3600), int(T0) + 3000)
    assert status == "DIFFERS"
    assert "client copy is newer" in detail and "addons/kan_survivornpc.pbo" in detail


def test_docs_only_difference_is_ignored():
    client = files(100)
    client["readme.md"] = (9999, T0)
    assert md.classify(files(100), client, None)[0] == "OK"


def test_workshop_newer_than_install_is_stale_without_client_copy():
    status, _ = md.classify(files(100), None, int(T0) + md.SLACK_SECONDS + 1)
    assert status == "STALE"


def test_publish_skew_within_slack_is_ok():
    # Our own mod: files uploaded, then published a few minutes later.
    assert md.classify(files(100), files(100), int(T0) + 20)[0] == "OK"


def test_local_files_lowercases(tmp_path: Path):
    (tmp_path / "Addons").mkdir()
    (tmp_path / "Addons" / "KAN.pbo").write_bytes(b"x" * 7)
    assert md.local_files(tmp_path)["addons/kan.pbo"][0] == 7
    assert md.local_files(tmp_path / "nope") is None
