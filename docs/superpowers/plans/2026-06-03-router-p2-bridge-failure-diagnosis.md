# Router P2 — Structured Bridge-Failure Diagnosis — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `call_rhino`'s opaque failure strings into a structured, agent-consumable diagnosis envelope (four codes + `retryable` + locate-only `crash_artifact`), reusing P1's liveness primitives — diagnosis only, no recovery.

**Architecture:** A standalone `crash_artifacts.py` locates (never parses) the freshest Rhino crash file. In `bridge.py`, a shared envelope builder (`build_session_liveness_error`) and an exception classifier (`diagnose_bridge_failure`) assemble the structured error; `call_rhino` captures its target **once** (building the URL from that capture, not a second `get_rhino_host`) and routes only `httpx.RequestError` to the classifier; `get_session_capabilities` is tightened to probe the PID before claiming dead.

**Tech Stack:** Python 3.13, `httpx` (already used), `socket`/`os`/`pathlib`/`datetime` (stdlib), `pytest` + `pytest-asyncio` (already configured).

**Authoritative spec:** `docs/superpowers/specs/2026-06-03-p2-bridge-failure-diagnosis-design.md`. Read it first.

---

## Source-of-truth facts (verified against current code)

- `call_rhino`'s failure handling today: `except httpx.ConnectError:` returns a free-text `{success:False, data:"Cannot connect…"}`; `except Exception as e:` returns `{success:False, data:str(e)}` (`bridge.py:1001` / `:1020`). `response.json()` is **inside** the `try` (`bridge.py:999`), so JSON-decode failures hit the generic `Exception`.
- `call_rhino` builds its host via `host = get_rhino_host(resolved_port, endpoint=endpoint, process_id=resolved_process_id)` (`bridge.py:963`), and `get_rhino_host` **re-runs** `select_rhino_instance` internally (`bridge.py:762`). So `call_rhino` selects twice; P2 captures once.
- `selected_instance = select_rhino_instance(...)` is bound earlier in `call_rhino` and is non-`None` on every path that reaches the HTTP request (the `None` paths early-return). It carries `host`, `port`, `processId`, `pluginType`.
- P1 primitives to reuse (all in `bridge.py`): `_is_pid_alive(pid)` (`:124`), `_is_port_listening(host, port)`, `classify_session_liveness(instance)` (returns `{state,pidAlive,portListening,code}`), `session_id_for_instance(instance)`, `discover_instances()` (reaps dead-PID files), `DEFAULT_HOST`.
- `get_session_capabilities` (P1): the `instance is None` branch returns `rhino_session_dead` **without** a PID probe; the has-record branch already computes `classify_session_liveness`.
- `httpx` exception hierarchy: `RequestError` → `TransportError` → `{TimeoutException → ConnectTimeout/ReadTimeout/WriteTimeout/PoolTimeout}` and `{NetworkError → ConnectError/ReadError/WriteError/CloseError}`. **`ConnectTimeout` is a `TimeoutException`, not a `ConnectError`** — classify it with the connectivity group first.
- Tests: `sys.path.insert(0, .../src)` then `from rook import bridge`; `tmp_path`+`monkeypatch`; `@pytest.mark.asyncio` for async.

**Run command (all P2 tasks), from repo root:**
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_crash_artifacts.py mcp_server/tests/test_bridge_diagnosis.py -v
```
Regression (Task 5 + final): add `mcp_server/tests/test_sessions.py mcp_server/tests/test_session_tools.py`.

---

## File Structure

- **Create** `mcp_server/src/rook/crash_artifacts.py` — `find_recent_rhino_crash_artifact(process_id=None, since_utc=None) -> dict | None`. Standalone; imports only `os`, `pathlib`, `datetime`, `re`. No `bridge` import.
- **Modify** `mcp_server/src/rook/bridge.py`
  - New import: `from .crash_artifacts import find_recent_rhino_crash_artifact`.
  - New: `_BRIDGE_ERROR_POLICY`, `_assemble_bridge_error`, `build_session_liveness_error`, `_resolve_target_liveness`, `diagnose_bridge_failure` (inserted after `get_session_capabilities`, before `get_rhino_host`).
  - Refactor: `call_rhino` (capture target once; build URL from capture; transport-only `except`).
  - Tighten: `get_session_capabilities` (PID probe on no-record; reuse the builder).
- **Create** `mcp_server/tests/test_crash_artifacts.py`, `mcp_server/tests/test_bridge_diagnosis.py`.

**Not touched:** `src/RookNative/**` (no C++), `targeting.py`, any mutation route, any spawn/kill path, crash-artifact *parsing*.

---

## Task 1: Locate-only crash-artifact finder

**Files:**
- Create: `mcp_server/src/rook/crash_artifacts.py`
- Test: `mcp_server/tests/test_crash_artifacts.py`

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_crash_artifacts.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_crash_artifacts.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'rook.crash_artifacts'`.

- [ ] **Step 3: Write minimal implementation**

Create `mcp_server/src/rook/crash_artifacts.py`:

```python
"""Locate (never parse) the freshest Rhino crash artifact.

P2 surfaces a *pointer* to the OS/Rhino crash file so agents and humans can
inspect it. It does not parse minidumps or managed-exception text — that is a
later forensics slice. Windows-only locations today; returns None elsewhere.
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


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


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

    Never opens/parses the file. Prefers a PID-exact WER dump; otherwise returns
    the most recent artifact within the freshness window (or after since_utc).
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_crash_artifacts.py -v`
Expected: PASS (5 passed). *(The finder has no OS guard — it relies on `USERPROFILE`/`LOCALAPPDATA`, so the tests monkeypatch the dir accessors and pass on any runner.)*

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/crash_artifacts.py mcp_server/tests/test_crash_artifacts.py
git commit -m "feat(crash): locate-only Rhino crash-artifact finder (confidence-tagged)"
```

---

## Task 2: Envelope policy + `build_session_liveness_error`

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (new import near the top imports; insert the policy + `_assemble_bridge_error` + `build_session_liveness_error` after `get_session_capabilities`)
- Test: `mcp_server/tests/test_bridge_diagnosis.py` (create)

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_bridge_diagnosis.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge


def _target(**over):
    t = {"host": "127.0.0.1", "port": 59306, "processId": 12345,
         "session": "rhino-12345", "endpoint": "/objects", "method": "GET"}
    t.update(over)
    return t


def test_build_unreachable_envelope():
    liveness = {"state": "unreachable", "pidAlive": True, "portListening": False}
    out = bridge.build_session_liveness_error(_target(), liveness, reason="tool_call")
    assert out["success"] is False
    d = out["data"]
    assert d["code"] == "rook_native_listener_unreachable"
    assert d["retryable"] is True
    assert d["session"] == "rhino-12345"
    assert d["processId"] == 12345
    assert d["port"] == 59306
    assert d["endpoint"] == "/objects"
    assert d["liveness"]["state"] == "unreachable"
    assert "crash_artifact" not in d
    assert "next_action" in d


def test_build_dead_envelope_attaches_crash_artifact(monkeypatch):
    monkeypatch.setattr(
        bridge, "find_recent_rhino_crash_artifact",
        lambda process_id=None, since_utc=None: {"available": True, "kind": "minidump",
                                                 "path": "X", "pidMatched": True},
    )
    liveness = {"state": "dead", "pidAlive": False, "portListening": False}
    out = bridge.build_session_liveness_error(_target(), liveness, reason="tool_call")
    d = out["data"]
    assert d["code"] == "rhino_session_dead"
    assert d["retryable"] is False
    assert d["crash_artifact"]["pidMatched"] is True


def test_build_dead_envelope_no_artifact_when_none(monkeypatch):
    monkeypatch.setattr(
        bridge, "find_recent_rhino_crash_artifact",
        lambda process_id=None, since_utc=None: None,
    )
    liveness = {"state": "dead", "pidAlive": False, "portListening": False}
    out = bridge.build_session_liveness_error(_target(), liveness, reason="tool_call")
    assert out["data"]["code"] == "rhino_session_dead"
    assert "crash_artifact" not in out["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'build_session_liveness_error'`.

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add the import beside the other intra-package import (or near the top, after `import httpx`):

```python
from .crash_artifacts import find_recent_rhino_crash_artifact
```

Insert after `get_session_capabilities` (before `def get_rhino_host(`):

```python
# Per-code policy: (retryable, next_action). The single source of truth for how
# a bridge-failure code maps to agent-facing guidance.
_BRIDGE_ERROR_POLICY: dict[str, tuple[bool, str]] = {
    "rhino_session_dead": (
        False,
        "The Rhino process is gone. Inspect crash_artifact if present, then call "
        "rhino_sessions; do not retry this session.",
    ),
    "rook_native_listener_unreachable": (
        True,
        "The Rhino process is alive but its RookNative listener is not responding "
        "(plugin reload, listener restart, or a transient). Retry shortly.",
    ),
    "rook_native_request_timeout": (
        True,
        "The request did not complete before the timeout — Rhino may be busy (a long "
        "command or a modal dialog) or a client-side stall. Retry shortly.",
    ),
    "rook_native_transport_error": (
        True,
        "The bridge request failed at the transport layer and the cause could not be "
        "confirmed. Call rhino_sessions to check live sessions, then retry.",
    ),
}


def _assemble_bridge_error(
    code: str,
    target: dict[str, Any],
    liveness: dict[str, Any] | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    """Assemble the structured `{success:False, data:{...}}` bridge-error envelope.

    Attaches a locate-only `crash_artifact` only for `rhino_session_dead`. The
    `retryable` invariant is upheld by the policy table: only `rhino_session_dead`
    is non-retryable, and the only path to it is a PID confirmed not-alive.
    """
    retryable, next_action = _BRIDGE_ERROR_POLICY[code]
    data: dict[str, Any] = {
        "code": code,
        "session": target.get("session"),
        "processId": target.get("processId"),
        "port": target.get("port"),
        "endpoint": target.get("endpoint"),
        "method": target.get("method"),
        "retryable": retryable,
        "next_action": next_action,
    }
    if liveness is not None:
        data["liveness"] = liveness
    if reason:
        data["reason"] = reason
    if code == "rhino_session_dead":
        artifact = find_recent_rhino_crash_artifact(process_id=target.get("processId"))
        if artifact is not None:
            data["crash_artifact"] = artifact
    return {"success": False, "data": data}


def build_session_liveness_error(
    target: dict[str, Any],
    liveness: dict[str, Any],
    reason: str | None = None,
) -> dict[str, Any]:
    """Build the bridge-error envelope from a resolved liveness state.

    Used by both `diagnose_bridge_failure` (connectivity branch) and
    `get_session_capabilities`. `live`/indeterminate is not a liveness *error*
    and maps to `rook_native_transport_error` (the caller should normally only
    pass `dead`/`unreachable`).
    """
    code = {
        "dead": "rhino_session_dead",
        "unreachable": "rook_native_listener_unreachable",
    }.get(liveness.get("state"), "rook_native_transport_error")
    return _assemble_bridge_error(code, target, liveness=liveness, reason=reason)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge_diagnosis.py
git commit -m "feat(bridge): bridge-error envelope builder + per-code retryable/next_action policy"
```

---

## Task 3: `diagnose_bridge_failure` (exception classifier)

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `_resolve_target_liveness` + `diagnose_bridge_failure` after `build_session_liveness_error`)
- Test: `mcp_server/tests/test_bridge_diagnosis.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_bridge_diagnosis.py`:

```python
import httpx


def _diag(exc, monkeypatch, pid_alive=True, port_listening=True, target=None):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: pid_alive)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: port_listening)
    monkeypatch.setattr(
        bridge, "find_recent_rhino_crash_artifact",
        lambda process_id=None, since_utc=None: None,
    )
    return bridge.diagnose_bridge_failure(target or _target(), exc)


def test_read_timeout_is_request_timeout(monkeypatch):
    out = _diag(httpx.ReadTimeout("slow"), monkeypatch, pid_alive=True)
    assert out["data"]["code"] == "rook_native_request_timeout"
    assert out["data"]["retryable"] is True


def test_timeout_masking_death_is_dead(monkeypatch):
    # A death can surface as a ReadTimeout. PID known-dead => rhino_session_dead.
    out = _diag(httpx.ReadTimeout("slow"), monkeypatch, pid_alive=False)
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["retryable"] is False


def test_connect_error_dead(monkeypatch):
    out = _diag(httpx.ConnectError("refused"), monkeypatch, pid_alive=False, port_listening=False)
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["retryable"] is False


def test_connect_error_unreachable(monkeypatch):
    out = _diag(httpx.ConnectError("refused"), monkeypatch, pid_alive=True, port_listening=False)
    assert out["data"]["code"] == "rook_native_listener_unreachable"
    assert out["data"]["retryable"] is True


def test_connect_error_live_race_is_transport(monkeypatch):
    out = _diag(httpx.ConnectError("refused"), monkeypatch, pid_alive=True, port_listening=True)
    assert out["data"]["code"] == "rook_native_transport_error"


def test_close_error_probes_liveness(monkeypatch):
    # CloseError (connection dropped) is connectivity — probe liveness, don't fall
    # through to a generic transport error.
    out = _diag(httpx.CloseError("closed"), monkeypatch, pid_alive=True, port_listening=False)
    assert out["data"]["code"] == "rook_native_listener_unreachable"


def test_connect_timeout_uses_connectivity_not_timeout(monkeypatch):
    # ConnectTimeout subclasses TimeoutException but must be treated as connectivity.
    out = _diag(httpx.ConnectTimeout("slow"), monkeypatch, pid_alive=False, port_listening=False)
    assert out["data"]["code"] == "rhino_session_dead"


def test_protocol_error_is_transport(monkeypatch):
    out = _diag(httpx.ProtocolError("bad"), monkeypatch)
    assert out["data"]["code"] == "rook_native_transport_error"


def test_port_only_target_unresolvable_is_transport(monkeypatch):
    # No processId and no record owning the port => cannot confirm dead.
    monkeypatch.setattr(bridge, "discover_instances", lambda: [])
    out = _diag(httpx.ConnectError("refused"), monkeypatch,
                target=_target(processId=None, session=None))
    assert out["data"]["code"] == "rook_native_transport_error"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'diagnose_bridge_failure'`.

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add after `build_session_liveness_error`:

```python
# Connectivity failures: the connection could not be established or was dropped.
# ConnectTimeout is listed here on purpose (it subclasses TimeoutException) so it
# is diagnosed by probing liveness, not bucketed as a request timeout.
_CONNECTIVITY_ERRORS = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.CloseError,
)


def _resolve_target_liveness(target: dict[str, Any]) -> dict[str, Any]:
    """Liveness for a target, resolving a missing PID by port. Never guesses death.

    With a known PID, classify directly. Without one, look up the port in a fresh
    discover; if a native record owns it, classify that. If nothing owns the port,
    return an 'indeterminate' state — the caller maps that to a transport error,
    never a fabricated `rhino_session_dead`.
    """
    if target.get("processId"):
        return classify_session_liveness(target)
    port = target.get("port")
    inst = next(
        (i for i in discover_instances()
         if i.get("port") == port and i.get("pluginType") == "native"),
        None,
    )
    if inst is not None:
        return classify_session_liveness(inst)
    return {"state": "indeterminate", "pidAlive": None, "portListening": None}


def diagnose_bridge_failure(target: dict[str, Any], exc: Exception) -> dict[str, Any]:
    """Classify an httpx transport failure into a structured bridge-error envelope.

    Order matters: connectivity errors (incl. ConnectTimeout) are tested before
    the broad TimeoutException bucket. Timeouts PID-probe first so a death masked
    as a timeout returns `rhino_session_dead`, never a retryable timeout.
    """
    if isinstance(exc, _CONNECTIVITY_ERRORS):
        liveness = _resolve_target_liveness(target)
        if liveness["state"] in ("dead", "unreachable"):
            return build_session_liveness_error(target, liveness, reason="tool_call")
        return _assemble_bridge_error(
            "rook_native_transport_error", target, liveness=liveness, reason="tool_call"
        )

    if isinstance(exc, httpx.TimeoutException):  # ReadTimeout / WriteTimeout / PoolTimeout
        pid = target.get("processId")
        if pid and not _is_pid_alive(int(pid)):
            liveness = {"state": "dead", "pidAlive": False, "portListening": None}
            return build_session_liveness_error(target, liveness, reason="tool_call")
        return _assemble_bridge_error("rook_native_request_timeout", target, reason="tool_call")

    return _assemble_bridge_error("rook_native_transport_error", target, reason="tool_call")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -v`
Expected: PASS (12 passed — 3 from Task 2 + 9 here).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge_diagnosis.py
git commit -m "feat(bridge): diagnose_bridge_failure — classify httpx transport errors to codes"
```

---

## Task 4: `call_rhino` — capture once, build URL from capture, transport-only diagnosis

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (the `host = get_rhino_host(...)` block at ~`:963` and the `async with httpx.AsyncClient` try/except at ~`:978-1021`)
- Test: `mcp_server/tests/test_bridge_diagnosis.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_bridge_diagnosis.py`:

```python
class _RaisingClient:
    """Async context manager whose request methods raise a chosen exception."""
    def __init__(self, exc):
        self._exc = exc
    async def __aenter__(self):
        return self
    async def __aexit__(self, *a):
        return False
    async def get(self, *a, **k):
        raise self._exc
    async def post(self, *a, **k):
        raise self._exc
    async def request(self, *a, **k):
        raise self._exc


@pytest.mark.asyncio
async def test_call_rhino_connect_error_returns_structured_dead(monkeypatch):
    inst = {"host": "127.0.0.1", "port": 59306, "processId": 4242, "pluginType": "native"}
    monkeypatch.setattr(bridge, "select_rhino_instance", lambda **k: inst)
    monkeypatch.setattr(bridge, "discover_instances", lambda: [inst])
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)
    monkeypatch.setattr(bridge, "find_recent_rhino_crash_artifact",
                        lambda process_id=None, since_utc=None: None)
    monkeypatch.setattr(bridge.httpx, "AsyncClient",
                        lambda *a, **k: _RaisingClient(httpx.ConnectError("refused")))

    out = await bridge.call_rhino("/objects", method="GET", port=59306, process_id=4242)

    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["session"] == "rhino-4242"
    assert out["data"]["endpoint"] == "/objects"


@pytest.mark.asyncio
async def test_call_rhino_post_response_decode_error_is_not_transport(monkeypatch):
    # A response WAS received but .json() fails -> must NOT become a bridge transport
    # error; existing behavior (success:False, data=str(error)) is preserved.
    class _BadJsonClient(_RaisingClient):
        async def get(self, *a, **k):
            class _R:
                def json(self_inner):
                    raise ValueError("not json")
            return _R()
    inst = {"host": "127.0.0.1", "port": 59306, "processId": 7, "pluginType": "native"}
    monkeypatch.setattr(bridge, "select_rhino_instance", lambda **k: inst)
    monkeypatch.setattr(bridge, "discover_instances", lambda: [inst])
    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda *a, **k: _BadJsonClient(None))

    out = await bridge.call_rhino("/objects", method="GET", port=59306, process_id=7)

    assert out["success"] is False
    assert "code" not in out["data"]  # not a structured bridge error
    assert "not json" in out["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -k call_rhino -v`
Expected: FAIL — the first test gets the old free-text `"Cannot connect…"` string (no `code` key), so `out["data"]["code"]` raises `TypeError`/`KeyError`.

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, replace the host-resolution block (currently `host = get_rhino_host(...)` through `url = f"{host}{endpoint}"`, ~`:963-976`) with a single capture built from `selected_instance`:

```python
    # Capture the resolved target ONCE — the single source of truth for both the
    # request URL and failure diagnosis. Do NOT call get_rhino_host() here: it
    # re-runs select_rhino_instance (bridge.py) and, under discovery churn, could
    # resolve a different instance than the one we captured, splitting the URL's
    # target from the diagnosed PID.
    if selected_instance is None or not selected_instance.get("port"):
        return {
            "success": False,
            "data": (
                "No Rhino instance discovered. "
                "Ensure Rhino is running with RookNative loaded."
            ),
        }
    target = {
        "host": selected_instance.get("host") or DEFAULT_HOST,
        "port": selected_instance.get("port"),
        "processId": selected_instance.get("processId"),
        "session": (
            session_id_for_instance(selected_instance)
            if selected_instance.get("processId") else None
        ),
        "endpoint": endpoint,
        "method": method,
    }
    url = f"http://{target['host']}:{target['port']}{endpoint}"
```

Then replace the two `except` clauses (currently `except httpx.ConnectError:` … and `except Exception as e:`, ~`:1001-1021`) with:

```python
        except httpx.RequestError as exc:
            # Transport-level failure (connect/timeout/network) — diagnose it.
            return diagnose_bridge_failure(target, exc)
        except Exception as e:
            # A response was received but post-processing failed (e.g. response.json()
            # decode / body shape). NOT a bridge transport failure — preserve the
            # existing non-P2 behavior.
            return {"success": False, "data": str(e)}
```

> **Note:** keep the `async with httpx.AsyncClient(timeout=timeout or TIMEOUT) as client:` and the GET/POST/DELETE body intact; only the host-capture block and the two `except` clauses change. `select_rhino_instance` is already bound to `selected_instance` earlier in the function — do not re-select.

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -v`
Expected: PASS (14 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge_diagnosis.py
git commit -m "refactor(bridge): call_rhino captures target once; transport-only structured diagnosis"
```

---

## Task 5: Tighten `get_session_capabilities` (probe PID before claiming dead)

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (`get_session_capabilities` — the `instance is None` branch and the dead/unreachable branches)
- Test: `mcp_server/tests/test_bridge_diagnosis.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_bridge_diagnosis.py`:

```python
@pytest.fixture
def diag_sessions_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    return tmp_path


@pytest.mark.asyncio
async def test_gsc_no_record_alive_pid_is_unreachable_not_dead(diag_sessions_dir, monkeypatch):
    # No native record for the pid, but the pid is alive -> unreachable, NOT dead.
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    out = await bridge.get_session_capabilities("rhino-888")
    assert out["success"] is False
    assert out["data"]["code"] == "rook_native_listener_unreachable"
    assert out["data"]["retryable"] is True


@pytest.mark.asyncio
async def test_gsc_no_record_dead_pid_is_dead(diag_sessions_dir, monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "find_recent_rhino_crash_artifact",
                        lambda process_id=None, since_utc=None: None)
    out = await bridge.get_session_capabilities("rhino-889")
    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["retryable"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py -k gsc -v`
Expected: FAIL — `test_gsc_no_record_alive_pid_is_unreachable_not_dead` fails because the current no-record branch returns `rhino_session_dead` unconditionally.

- [ ] **Step 3: Write minimal implementation**

In `get_session_capabilities`, replace the `if instance is None:` block with a PID probe:

```python
    if instance is None:
        # No native record. Probe the PID before claiming dead (P2): the record may
        # be gone while the process lives (listener unloaded/reloading).
        gone_target = {
            "session": session_id, "processId": process_id, "port": None,
            "endpoint": "/capabilities", "method": "GET",
        }
        if _is_pid_alive(int(process_id)):
            return build_session_liveness_error(
                gone_target,
                {"state": "unreachable", "pidAlive": True, "portListening": False},
                reason="capability_query",
            )
        return build_session_liveness_error(
            gone_target,
            {"state": "dead", "pidAlive": False, "portListening": False},
            reason="capability_query",
        )
```

Then replace the existing `dead` and `unreachable` branches (which return hand-built dicts) with the shared builder:

```python
    liveness = classify_session_liveness(instance)
    if liveness["state"] in ("dead", "unreachable"):
        err_target = {
            "session": session_id, "processId": process_id,
            "port": instance.get("port"), "endpoint": "/capabilities", "method": "GET",
        }
        return build_session_liveness_error(err_target, liveness, reason="capability_query")
```

Leave the live path (`assert_session_readonly_endpoint` + `resolve_capabilities`) unchanged.

- [ ] **Step 4: Run test to verify it passes + regression**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_bridge_diagnosis.py mcp_server/tests/test_sessions.py mcp_server/tests/test_session_tools.py -v
```
Expected: PASS. The P1 `test_sessions.py` session-capability tests still pass — `code`, `session`, and `next_action` are preserved (now additionally carrying `retryable` and, on dead, `crash_artifact`); reaping is unchanged, so `test_get_session_capabilities_unreachable_does_not_reap` and `_dead_after_discovery_race` stay green.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge_diagnosis.py
git commit -m "feat(bridge): get_session_capabilities probes PID before claiming dead; reuses builder"
```

---

## Task 6: Live smoke verification (against a real Rhino)

> **Implemented as a repeatable harness smoke (corrected post-review):** built `mcp_server/tools/p2_bridge_diagnosis_live_harness.py`, run via `scripts/run_rhino_runtime_harness.py --smoke p2-bridge-diagnosis` (the harness launches an OWNED throwaway Rhino, sets `ROOK_RHINO_PROCESS_ID`/`ROOK_RHINO_PORT`, runs the smoke, shuts the Rhino down gracefully — never touches the user's session). Covers **all four codes** against real OS state: `live` baseline, `rook_native_listener_unreachable` (real alive pid + real dead port, record retained), `rook_native_request_timeout` (ReadTimeout + real alive pid), and `rhino_session_dead` (a real throwaway-process dead pid, via both ConnectError and timeout-masking) with and without a `crash_artifact`. **Honesty boundaries:** the dead path uses a *throwaway* dead pid (not a killed Rhino — killing it defeats the harness's graceful cleanup); the crash artifact is a **synthetic** `RhinoDotNetCrash.txt` validating the finder's filesystem-location + freshness logic (a real Rhino crash is non-deterministic to induce). Result: **7/7 PASS, harness `graceful_exit`/`success`.** The manual Steps 1–6 below were the original sketch; the harness tool supersedes them.

Per the project's "live smoke catches what mocks miss" rule, verify end-to-end before opening the PR. No code — a gate. (Bridge-level Python smoke is sufficient; no MCP redeploy required.)

- [ ] **Step 1:** Start Rhino + RookNative; note the PID and a live session id from `rhino_sessions`.
- [ ] **Step 2: Timeout path.** Trigger a long-running/modal state in Rhino (e.g. open a blocking dialog), then issue a normal tool call that routes through `call_rhino`. Expected: `rook_native_request_timeout`, `retryable:true`, no `crash_artifact`.
- [ ] **Step 3: Dead path (graceful).** Close Rhino, then call any Rhino tool. Expected: `rhino_session_dead`, `retryable:false`; `crash_artifact` omitted (clean shutdown writes none).
- [ ] **Step 4: Dead path (crash).** With Rhino running, force a crash (e.g. a RhinoDotNetCrash via a known-bad script, or kill the process to simulate), then call a Rhino tool. Expected: `rhino_session_dead` and a `crash_artifact` pointer (`kind`, `path`, `ageSeconds`) when an artifact was written within the window. Record whether `pidMatched` was true (WER) or `fresh_near_failure`.
- [ ] **Step 5: Unreachable path (synthetic, non-destructive).** Reuse the P1 smoke trick: with Rhino alive, point its discovery record's `port` at a dead port; call a tool. Expected: `rook_native_listener_unreachable`, `retryable:true`, record retained. Restore.
- [ ] **Step 6:** Record outcomes in the PR body. File any deviation as a new issue rather than widening this PR.

---

## Self-Review

**1. Spec coverage** (against `2026-06-03-p2-bridge-failure-diagnosis-design.md`):
- §3 capture-once / build-URL-from-capture / never-guess-death → Task 4 (capture) + `_resolve_target_liveness` (Task 3). ✅
- §4 four-code taxonomy + check-order + timeout-PID-override → Task 3 (`_CONNECTIVITY_ERRORS` before `TimeoutException`; timeout PID probe). ✅
- §5 envelope (+ `retryable`, `endpoint`, `method`) → `_assemble_bridge_error` (Task 2). ✅
- §6 locate-only confidence-tagged crash_artifact → Task 1. ✅
- §7 split helpers; `get_session_capabilities` reuses the builder + probes PID → Tasks 2/3/5. ✅
- §7 transport-only boundary (`httpx.RequestError`; response-received preserved) → Task 4 (two-except split). ✅
- §8 reaping unchanged → no reaping added in any task. ✅
- "never `retryable:true` when PID known dead" invariant → policy table makes `rhino_session_dead` the only non-retryable code, reachable only via a confirmed-dead PID (Tasks 2/3). ✅

**2. Placeholder scan:** No TBD/TODO/"handle errors". Every code step is complete; every run step has a command + expected result. The Task 1 Step-4 note about the `os.name` guard order is an explicit, resolved instruction, not a placeholder. ✅

**3. Type consistency:** the `target` dict shape (`host/port/processId/session/endpoint/method`) is identical in Tasks 3/4/5; `liveness` dict (`state/pidAlive/portListening`) matches `classify_session_liveness`'s output and the hand-built ones; `_assemble_bridge_error`/`build_session_liveness_error`/`diagnose_bridge_failure` names match across tasks and the spec; `find_recent_rhino_crash_artifact(process_id=, since_utc=)` signature matches its call in `_assemble_bridge_error`. ✅

---

## Notes / risks for the executor

- **Catch order is load-bearing:** `except httpx.RequestError` must precede `except Exception` in `call_rhino`, and inside `diagnose_bridge_failure` the `_CONNECTIVITY_ERRORS` tuple (with `ConnectTimeout`) must be tested before `httpx.TimeoutException`. Reordering silently misclassifies.
- **Do not re-introduce `get_rhino_host` in `call_rhino`:** the whole point of Task 4 is one capture. If a later edit "simplifies" the URL build back to `get_rhino_host`, the diagnosed PID can diverge from the failed URL under discovery churn.
- **`response.json()` stays inside the `try`:** the generic `except Exception` deliberately catches decode/body-shape failures (response received) and preserves the existing string return — never route those to `diagnose_bridge_failure`.
- **P1 regression surface:** Task 5 reshapes `get_session_capabilities`'s error branches through the builder. Run `test_sessions.py` in Task 5 Step 4 — the P1 assertions check `code`/`session`/`next_action` presence (preserved) and reaping (unchanged), so they must stay green.
- **Crash-artifact finder has no OS guard** — it depends on Windows env vars (`USERPROFILE`/`LOCALAPPDATA`), so it returns `None` naturally on non-Windows. Tests monkeypatch the dir accessors and pass on any runner.
