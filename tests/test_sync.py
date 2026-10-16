"""scripts/sync.sh push must never upload runtime state from a local test boot.

2026-10-16: a dry-run push after the local 1.30 boots listed ExpansionMod/ATM balances,
VPP admin logs, the engine's users/ profile and DataCache for upload to the live server.
Push now skips everything .gitignore marks as runtime; these tests run the real function.
"""
import re
import subprocess

from modstring import ROOT

SYNC = ROOT / "scripts" / "sync.sh"

# Per-player or per-boot state that only the live server may write.
RUNTIME = [
    "ExpansionMod/ATM/",
    "ExpansionMod/Quests/PlayerData/",
    "VPPAdminTools/Logging/",
    "VPPAdminTools/Permissions/credentials.txt",
    "users/",
    "DataCache/",
    "DZDS/arrivals_ledger.json",
    "DZDS/queue/",
]


def runtime_excludes(rel_dir):
    """Run sync.sh's own runtime_excludes() without its .env/lftp preamble."""
    src = SYNC.read_text()
    fn = re.search(r"^runtime_excludes\(\) \{.*?^\}", src, re.S | re.M).group(0)
    out = subprocess.run(
        ["bash", "-c", f'{fn}\nROOT="$1"; runtime_excludes "$2"', "_", str(ROOT), rel_dir],
        capture_output=True, text=True, check=True,
    )
    return set(out.stdout.splitlines())


def test_runtime_paths_are_gitignored():
    for rel in RUNTIME:
        path = f"server/profiles/{rel}"
        probe = path + ("probe.json" if path.endswith("/") else "")
        r = subprocess.run(["git", "-C", str(ROOT), "check-ignore", "-q", "--no-index", probe])
        assert r.returncode == 0, f"{path} is not gitignored, so push would upload it"


def test_runtime_excludes_lists_ignored_paths_relative_to_dir():
    got = runtime_excludes("server/profiles")
    assert got, "runtime_excludes printed nothing: push would exclude nothing"
    assert not any(p.startswith("server/") for p in got), "paths must be relative to the mirror root"
    for rel in RUNTIME:
        if (ROOT / "server/profiles" / rel).exists():
            assert rel in got, f"{rel} exists locally but push would upload it"


def test_runtime_excludes_never_skip_tracked_config():
    got = runtime_excludes("server/profiles")
    for cfg in ["DZDS/settings.json", "DZDS/arrivals.json", "KANSurvivorNPC/camps.json"]:
        assert cfg not in got


def test_runtime_excludes_escape_glob_characters():
    src = SYNC.read_text()
    fn = re.search(r"^runtime_excludes\(\) \{.*?^\}", src, re.S | re.M).group(0)
    out = subprocess.run(
        ["bash", "-c", f'{fn}\ngit() {{ printf "d/[CnG]a*?.json\\n"; }}\nruntime_excludes d'],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == r"\[CnG\]a\*\?.json"


def test_push_uses_excludes_and_active_mission_only():
    body = re.search(r"^push\(\) \{.*?^\}", SYNC.read_text(), re.S | re.M).group(0)
    mirrors = [l for l in body.splitlines() if "mirror -R" in l]
    assert len(mirrors) == 2
    assert all("--exclude-glob-from=" in l for l in mirrors)
    assert "$L_MISSIONS'" not in body, "push must upload the active mission, not every mission"
