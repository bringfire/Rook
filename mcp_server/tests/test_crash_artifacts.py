import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import crash_artifacts


def test_finds_fresh_dotnet_crash_txt(tmp_path, monkeypatch):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    artifact = desktop / "RhinoDotNetCrash.txt"
    artifact.write_text("[ERROR] FATAL UNHANDLED EXCEPTION: System.Exception: boom", encoding="utf-8")
    monkeypatch.setattr(crash_artifacts, "_desktop_dirs", lambda: [desktop])
    monkeypatch.setattr(crash_artifacts, "_dump_dirs", lambda: [])

    out = crash_artifacts.find_recent_rhino_crash_artifact(process_id=999)

    assert out is not None
    assert out["available"] is True
    assert out["kind"] == "RhinoDotNetCrash.txt"
    assert out["path"] == str(artifact)
    assert out["pidMatched"] is False
    assert out["match"] == "fresh_near_failure"
    assert out["sizeBytes"] > 0
    assert out["ageSeconds"] >= 0


def test_wer_dump_pid_match(tmp_path, monkeypatch):
    dumps = tmp_path / "CrashDumps"
    dumps.mkdir()
    (dumps / "Rhino.exe.4321.dmp").write_bytes(b"MDMP____")
    monkeypatch.setattr(crash_artifacts, "_desktop_dirs", lambda: [])
    monkeypatch.setattr(crash_artifacts, "_dump_dirs", lambda: [dumps])

    out = crash_artifacts.find_recent_rhino_crash_artifact(process_id=4321)

    assert out["kind"] == "minidump"
    assert out["pidMatched"] is True
    assert out["match"] == "pid_exact"


def test_ignores_stale_pid_exact_dump(tmp_path, monkeypatch):
    # A stale PID-exact dump (e.g. a reused PID from a prior session) must NOT be
    # attached — the freshness gate applies even to PID matches.
    dumps = tmp_path / "CrashDumps"
    dumps.mkdir()
    dump = dumps / "Rhino.exe.4321.dmp"
    dump.write_bytes(b"MDMP____")
    old = time.time() - 3600  # 1 hour ago, outside the 5-min window
    os.utime(dump, (old, old))
    monkeypatch.setattr(crash_artifacts, "_desktop_dirs", lambda: [])
    monkeypatch.setattr(crash_artifacts, "_dump_dirs", lambda: [dumps])

    assert crash_artifacts.find_recent_rhino_crash_artifact(process_id=4321) is None


def test_ignores_stale_artifact(tmp_path, monkeypatch):
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    artifact = desktop / "RhinoDotNetCrash.txt"
    artifact.write_text("old", encoding="utf-8")
    old = time.time() - 3600  # 1 hour ago, outside the 5-min window
    os.utime(artifact, (old, old))
    monkeypatch.setattr(crash_artifacts, "_desktop_dirs", lambda: [desktop])
    monkeypatch.setattr(crash_artifacts, "_dump_dirs", lambda: [])

    assert crash_artifacts.find_recent_rhino_crash_artifact(process_id=1) is None


def test_returns_none_when_nothing_found(tmp_path, monkeypatch):
    monkeypatch.setattr(crash_artifacts, "_desktop_dirs", lambda: [tmp_path])
    monkeypatch.setattr(crash_artifacts, "_dump_dirs", lambda: [tmp_path])
    assert crash_artifacts.find_recent_rhino_crash_artifact() is None
