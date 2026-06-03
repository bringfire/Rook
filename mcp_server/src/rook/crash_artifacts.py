"""Locate (never parse) the freshest Rhino crash artifact.

P2 surfaces a *pointer* to the OS/Rhino crash file so agents and humans can
inspect it. It does not parse minidumps or managed-exception text — that is a
later forensics slice. Windows-only locations today; on other platforms the
Windows env vars are absent, so this naturally returns None.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# A crash artifact is only "ours" if it was written close to the failure.
_FRESH_WINDOW_SECONDS = 5 * 60

# WER LocalDumps name files "Rhino.exe.<pid>.dmp".
_WER_PID_RE = re.compile(r"Rhino\.exe\.(\d+)\.dmp$", re.IGNORECASE)


def _desktop_dirs() -> list[Path]:
    """Desktop locations Rhino may write RhinoDotNetCrash.txt to (incl. OneDrive)."""
    dirs: list[Path] = []
    seen: set[str] = set()

    def _add(p: Path) -> None:
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            dirs.append(p)

    profile = os.environ.get("USERPROFILE")
    if profile:
        _add(Path(profile) / "Desktop")
        _add(Path(profile) / "OneDrive" / "Desktop")
    onedrive = os.environ.get("ONEDRIVE")
    if onedrive:
        _add(Path(onedrive) / "Desktop")
    return dirs


def _dump_dirs() -> list[Path]:
    """Directories that may hold Rhino .dmp crash dumps."""
    dirs: list[Path] = []
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return dirs
    rhino_root = Path(local) / "McNeel" / "Rhinoceros"
    if rhino_root.is_dir():
        for vdir in rhino_root.iterdir():
            for folder in ("Crash Reports", "CrashDumps", "Crashes"):
                d = vdir / folder
                if d.is_dir():
                    dirs.append(d)
    wer = Path(local) / "CrashDumps"
    if wer.is_dir():
        dirs.append(wer)
    return dirs


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _candidates() -> list[tuple[Path, str]]:
    """(path, kind) for every plausible artifact, newest first."""
    found: list[tuple[Path, str]] = []
    for d in _desktop_dirs():
        p = d / "RhinoDotNetCrash.txt"
        if p.is_file():
            found.append((p, "RhinoDotNetCrash.txt"))
    for d in _dump_dirs():
        try:
            for p in d.glob("Rhino*.dmp"):
                if p.is_file():
                    # All .dmp are kind "minidump"; PID confidence is carried by
                    # match/pidMatched (WER filenames embed the pid).
                    found.append((p, "minidump"))
        except OSError:
            continue
    found.sort(key=lambda pk: _safe_mtime(pk[0]), reverse=True)
    return found


def _metadata(path: Path, kind: str, process_id: int | None) -> dict[str, Any]:
    st = path.stat()
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc)
    pid_matched = False
    match = "fresh_near_failure"
    m = _WER_PID_RE.search(path.name)
    if m is not None and process_id is not None and int(m.group(1)) == process_id:
        pid_matched = True
        match = "pid_exact"
    return {
        "available": True,
        "kind": kind,
        "path": str(path),
        "modifiedUtc": mtime.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ageSeconds": max(0, int((datetime.now(timezone.utc) - mtime).total_seconds())),
        "sizeBytes": st.st_size,
        "match": match,
        "pidMatched": pid_matched,
    }


def find_recent_rhino_crash_artifact(
    process_id: int | None = None,
    since_utc: datetime | None = None,
) -> dict[str, Any] | None:
    """Return metadata for the freshest plausible Rhino crash artifact, or None.

    Never opens/parses the file. Prefers a PID-exact WER dump within the freshness
    window; otherwise returns the most recent artifact within the window.
    """
    # No OS guard needed: the Windows env vars (USERPROFILE/LOCALAPPDATA) are absent
    # on other platforms, so _candidates() is naturally empty there and this returns
    # None. Rook itself is Windows-only.
    candidates = _candidates()
    if not candidates:
        return None

    now = datetime.now(timezone.utc)
    cutoff = since_utc or datetime.fromtimestamp(
        now.timestamp() - _FRESH_WINDOW_SECONDS, tz=timezone.utc
    )

    def _fresh(path: Path) -> bool:
        return datetime.fromtimestamp(_safe_mtime(path), tz=timezone.utc) >= cutoff

    # 1) PID-exact match — but ONLY within the freshness window. A stale dump whose
    #    embedded PID happens to match a reused PID must not be attached.
    if process_id is not None:
        for path, kind in candidates:  # newest first
            if not _fresh(path):
                break
            m = _WER_PID_RE.search(path.name)
            if m is not None and int(m.group(1)) == process_id:
                return _metadata(path, kind, process_id)

    # 2) Otherwise the most recent artifact within the window.
    for path, kind in candidates:
        if not _fresh(path):
            break
        return _metadata(path, kind, process_id)

    return None
