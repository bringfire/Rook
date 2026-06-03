# Router P1 — Read-Only Named Sessions + Liveness Envelope — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Project the Rhino instances Rook already discovers into **named sessions** with a **liveness envelope** (live / unreachable / dead), and expose two **read-only** MCP tools (`rhino_sessions`, `rhino_session_capabilities`) — without spawning, killing, mutating, or changing RookNative.

> **Tool naming (decided in review):** the MCP tools are `rhino_sessions` / `rhino_session_capabilities`. The `rhino_` prefix clusters them with the rest of the Rhino tool family and avoids the anagram clash with the pre-existing `session_list` tool (which lists *recording* sessions for replay — unrelated). Internal bridge callables keep their plain names (`list_sessions_result`, `get_session_capabilities`); only the tool-surface strings carry the prefix.

**Architecture:** Pure-Python, additive layer in `mcp_server/src/rook/bridge.py` on top of the existing `discover_instances()` / `resolve_capabilities()` primitives, surfaced through two new cases in `server.py`'s tool dispatch. The critical safety rule — **never reap an alive process whose port is merely unreachable** — is upheld for free: the existing `_cleanup_stale_discovery_files()` already deletes dead-PID files only and never probes the port, so this plan adds *classification* on top and changes **no** reaping behavior.

**Tech Stack:** Python 3.13, `httpx` (already used), `socket` (stdlib, new import), `pytest` + `pytest-asyncio` (already configured).

> **Forward-compatibility note** (north-star: `docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`): P1 remains **session-only**. It must **not** add work-unit or merge-contract state to session payloads. If document metadata is surfaced later, treat it as optional **document seed data**, not session identity. The P1 tasks below are unchanged by this note.

---

## Source-of-truth facts (verified against current code)

- `bridge.discover_instances()` (`bridge.py:513`) already returns **all** live instances (list of normalized dicts), filtered to `pluginType in ("native", "roadcreator")` (`bridge.py:530`). It calls `_cleanup_stale_discovery_files()` which deletes a discovery file **only when its PID is dead** (`bridge.py:487-490`) — it never probes the port. So "alive-but-port-down" records already survive. **Do not change this.**
- **CRITICAL — roadcreator shares the Rhino PID.** The RookRoads adapter (`pluginType: "roadcreator"`) runs in-process and reports the **same `processId`** as the native listener — `select_rhino_instance` scopes routing by pid precisely because of this (`bridge.py:379-381`). A *session* is a Rhino window, keyed by its **native** listener. So both `list_sessions` (Task 4) and the lookup in `get_session_capabilities` (Task 6) **MUST filter to `pluginType == "native"`**, or every Rhino with RoadCreator loaded yields a duplicate `rhino-<pid>` session and capability resolution may hit the wrong record.
- `bridge._is_pid_alive(pid)` (`bridge.py:102`) — Windows `OpenProcess` liveness check. Reuse.
- `bridge.resolve_capabilities(instance)` (`bridge.py:218`) — async; returns live `/capabilities` with an explicit bootstrap-fallback envelope. Reuse for `get_session_capabilities`.
- Discovery record fields (from `RookServer.cpp:2195-2214`): `host`, `port`, `pluginType`, `processId`, `startTime`, `pluginVersion`, `rhinoInside`, `capabilities`. **`processId` is the stable session key.** There is **no** Rhino-major-version field (do not invent one — out of scope, deferred to a later phase).
- MCP tools are declared in `server.py @mcp.list_tools()` (`server.py:2760`) as `Tool(name=..., description=..., inputSchema=...)`, and dispatched in `server.py async def _call_tool_dispatch(...)` via `match command:` / `case "...": result = ...`. `_call_tool_dispatch` returns the raw `{"success": bool, "data": ...}` envelope (the caller wraps it with `_format_tool_result`).
- `server.py:52` imports bridge symbols by name: `from .bridge import call_rhino, get_rhino_host, discover_instances, TIMEOUT, DISCOVERY_FOLDER, rhino_request_context`.
- Tests live in `mcp_server/tests/`, import via `sys.path.insert(0, ".../src")` then `from rook import bridge`, use `tmp_path` + `monkeypatch`, and use `@pytest.mark.asyncio` for async tests (see `tests/test_bridge.py:254`).

**Run command (all tasks), from repo root:**
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v
```
(Task 7 also runs `mcp_server/tests/test_session_tools.py`.)

---

## File Structure

- **Modify** `mcp_server/src/rook/bridge.py`
  - New import: `socket`.
  - New constants: `_SESSION_ID_PREFIX`, `_READONLY_SESSION_ENDPOINTS`.
  - New exception: `SessionEndpointNotAllowed`.
  - New functions: `_is_port_listening`, `session_id_for_instance`, `_process_id_from_session_id`, `assert_session_readonly_endpoint`, `classify_session_liveness`, `list_sessions`, `list_sessions_result`, `get_session_capabilities`.
  - Rationale: all of these are discovery/liveness concerns and belong beside `discover_instances`/`resolve_capabilities`. `targeting.py` (which owns *binding*) is intentionally untouched.
- **Modify** `mcp_server/src/rook/server.py`
  - Extend the `from .bridge import (...)` line with the two new public callables.
  - Add two `Tool(...)` declarations in `list_tools()`.
  - Add two `case` handlers in `_call_tool_dispatch`.
- **Create** `mcp_server/tests/test_sessions.py` — unit tests for the bridge layer.
- **Create** `mcp_server/tests/test_session_tools.py` — tests for tool registration + dispatch wiring.

**Not touched:** `src/RookNative/**` (no C++), `targeting.py`, any mutation route, any spawn/kill path.

---

## Task 1: Port-listening probe

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `import socket` to the stdlib imports near line 13-21; add `_is_port_listening` immediately after `_is_pid_alive`, ~line 116)
- Test: `mcp_server/tests/test_sessions.py` (create)

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_sessions.py`:

```python
import json
import os
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import bridge


def _write_instance(folder: Path, data: dict) -> Path:
    path = folder / f"instance-{data['processId']}-native.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_is_port_listening_true_for_open_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        assert bridge._is_port_listening("127.0.0.1", port) is True
    finally:
        sock.close()
    # After close, nothing is listening on that port.
    assert bridge._is_port_listening("127.0.0.1", port) is False


def test_is_port_listening_false_for_zero_port():
    assert bridge._is_port_listening("127.0.0.1", 0) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute '_is_port_listening'`

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add `import socket` alongside the existing stdlib imports (after `import os`). Then add after `_is_pid_alive` (after line 115):

```python
def _is_port_listening(host: str, port: int, timeout: float = 0.2) -> bool:
    """Return True iff a TCP connection to host:port succeeds.

    Probed independently of PID liveness: a Rhino process can be alive while
    its RookNative listener is down (plugin reload, restart, transient). The
    caller MUST treat that case conservatively (report, do not reap).
    """
    if not port or port <= 0:
        return False
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_sessions.py
git commit -m "feat(bridge): add independent TCP port-listening probe for session liveness"
```

---

## Task 2: Session id helpers

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `_SESSION_ID_PREFIX` constant near the other module constants ~line 29; add the two helpers after `discover_instances`, ~line 531)
- Test: `mcp_server/tests/test_sessions.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_sessions.py`:

```python
def test_session_id_round_trip():
    instance = {"processId": 12345, "port": 10500, "pluginType": "native"}
    sid = bridge.session_id_for_instance(instance)
    assert sid == "rhino-12345"
    assert bridge._process_id_from_session_id(sid) == 12345


def test_process_id_from_session_id_rejects_bad_input():
    assert bridge._process_id_from_session_id("bogus") is None
    assert bridge._process_id_from_session_id("rhino-") is None
    assert bridge._process_id_from_session_id("rhino-abc") is None
    assert bridge._process_id_from_session_id(None) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'session_id_for_instance'`

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add near the connection-settings constants (after line 30):

```python
# A session is a stable, legible name over a discovered Rhino process.
_SESSION_ID_PREFIX = "rhino-"
```

Add after `discover_instances` (after line 531):

```python
def session_id_for_instance(instance: dict[str, Any]) -> str:
    """Stable, human/agent-legible session id over a discovered Rhino process."""
    return f"{_SESSION_ID_PREFIX}{instance.get('processId')}"


def _process_id_from_session_id(session_id: Any) -> int | None:
    """Parse a session id back to its process id, or None if malformed."""
    if not isinstance(session_id, str) or not session_id.startswith(_SESSION_ID_PREFIX):
        return None
    raw = session_id[len(_SESSION_ID_PREFIX):]
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_sessions.py
git commit -m "feat(bridge): add stable session id <-> process id helpers"
```

---

## Task 3: Liveness classifier

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `classify_session_liveness` after the session id helpers from Task 2)
- Test: `mcp_server/tests/test_sessions.py`

The classifier is a pure function over one instance dict. It distinguishes the two failure cases that drive the whole safety story:
- **PID dead** → `state="dead"`, `code="rhino_session_dead"` (safe to reap; but this layer never reaps).
- **PID alive, port not listening** → `state="unreachable"`, `code="rook_native_listener_unreachable"` (do NOT reap — may be the user's live doc mid-reload).
- **PID alive, port listening** → `state="live"`, `code=None`.

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_sessions.py`:

```python
def test_classify_live(monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)
    out = bridge.classify_session_liveness({"processId": 1, "host": "127.0.0.1", "port": 10500})
    assert out["state"] == "live"
    assert out["pidAlive"] is True
    assert out["portListening"] is True
    assert out["code"] is None


def test_classify_unreachable_keeps_session(monkeypatch):
    # PID alive but port down => unreachable, NOT dead. Must never imply reaping.
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)
    out = bridge.classify_session_liveness({"processId": 2, "host": "127.0.0.1", "port": 10500})
    assert out["state"] == "unreachable"
    assert out["code"] == "rook_native_listener_unreachable"


def test_classify_dead(monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: False)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)
    out = bridge.classify_session_liveness({"processId": 3, "host": "127.0.0.1", "port": 10500})
    assert out["state"] == "dead"
    assert out["code"] == "rhino_session_dead"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'classify_session_liveness'`

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add after `_process_id_from_session_id`:

```python
def classify_session_liveness(instance: dict[str, Any]) -> dict[str, Any]:
    """Classify a discovered session's liveness without ever reaping it.

    Probes PID and port INDEPENDENTLY so the two failure modes can be told
    apart: a dead process (safe to reap, elsewhere) vs. an alive process whose
    listener is unreachable (must be left alone — may be the user's live doc).
    """
    pid = instance.get("processId")
    host = instance.get("host") or DEFAULT_HOST
    port = instance.get("port")

    pid_alive = bool(pid) and _is_pid_alive(int(pid))
    port_listening = bool(port) and _is_port_listening(host, int(port))

    if not pid_alive:
        state, code = "dead", "rhino_session_dead"
    elif not port_listening:
        state, code = "unreachable", "rook_native_listener_unreachable"
    else:
        state, code = "live", None

    return {
        "state": state,
        "pidAlive": pid_alive,
        "portListening": port_listening,
        "code": code,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_sessions.py
git commit -m "feat(bridge): classify session liveness (live/unreachable/dead) without reaping"
```

---

## Task 4: `list_sessions` projection + result envelope

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `list_sessions` and `list_sessions_result` after `classify_session_liveness`)
- Test: `mcp_server/tests/test_sessions.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_sessions.py`:

```python
@pytest.fixture
def sessions_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDER", tmp_path)
    monkeypatch.setattr(bridge, "DISCOVERY_FOLDERS", [tmp_path])
    return tmp_path


def test_list_sessions_projects_named_sessions_with_liveness(sessions_dir, monkeypatch):
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native",
        "processId": 4321, "pluginVersion": "1.5.8", "rhinoInside": False,
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    sessions = bridge.list_sessions()

    assert len(sessions) == 1
    s = sessions[0]
    assert s["session"] == "rhino-4321"
    assert s["processId"] == 4321
    assert s["port"] == 10500
    assert s["pluginType"] == "native"
    assert s["pluginVersion"] == "1.5.8"
    assert s["liveness"]["state"] == "live"


def test_list_sessions_dedupes_roadcreator_sharing_rhino_pid(sessions_dir, monkeypatch):
    # The roadcreator adapter shares the Rhino PID. Only the native listener is
    # a session — otherwise we'd emit two sessions with the same rhino-<pid> id.
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 909,
    })
    rc_path = sessions_dir / "instance-rc-909.json"
    rc_path.write_text(json.dumps({
        "host": "127.0.0.1", "port": 10600, "pluginType": "roadcreator", "processId": 909,
    }), encoding="utf-8")
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    sessions = bridge.list_sessions()

    assert [s["session"] for s in sessions] == ["rhino-909"]
    assert sessions[0]["pluginType"] == "native"


def test_list_sessions_result_envelope(sessions_dir, monkeypatch):
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 7,
    })

    envelope = bridge.list_sessions_result()

    assert envelope["success"] is True
    assert [s["session"] for s in envelope["data"]["sessions"]] == ["rhino-7"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'list_sessions'`

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add after `classify_session_liveness`:

```python
def list_sessions() -> list[dict[str, Any]]:
    """Project discovered Rhino instances into named sessions with liveness.

    Read-only: reads discovery (which already reaps dead-PID files) and probes
    liveness. Never spawns, kills, or mutates. Instances without a processId are
    skipped (no stable session id).
    """
    sessions: list[dict[str, Any]] = []
    for instance in discover_instances():
        # A session == a Rhino window, keyed by its native listener. The
        # roadcreator adapter shares the Rhino PID (bridge.py:379-381); including
        # it would emit a duplicate rhino-<pid> session. Native only.
        if instance.get("pluginType") != "native":
            continue
        pid = instance.get("processId")
        if not pid:
            continue
        sessions.append({
            "session": session_id_for_instance(instance),
            "processId": pid,
            "port": instance.get("port"),
            "host": instance.get("host") or DEFAULT_HOST,
            "pluginType": instance.get("pluginType"),
            "pluginVersion": instance.get("pluginVersion"),
            "rhinoInside": instance.get("rhinoInside"),
            "liveness": classify_session_liveness(instance),
        })
    return sessions


def list_sessions_result() -> dict[str, Any]:
    """MCP-facing envelope for list_sessions."""
    return {"success": True, "data": {"sessions": list_sessions()}}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_sessions.py
git commit -m "feat(bridge): project discovered instances into named sessions with liveness"
```

---

## Task 5: Read-only endpoint allowlist + guard

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `_READONLY_SESSION_ENDPOINTS`, `SessionEndpointNotAllowed`, `assert_session_readonly_endpoint` near the `_SESSION_ID_PREFIX` constant)
- Test: `mcp_server/tests/test_sessions.py`

This guard is the structural guarantee that session targeting in P1 can touch **only** vetted read-only endpoints. It gives P2+ a single chokepoint to extend deliberately, and fails closed on anything else.

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_sessions.py`:

```python
def test_assert_session_readonly_endpoint_allows_vetted():
    # Must not raise.
    bridge.assert_session_readonly_endpoint("/ping")
    bridge.assert_session_readonly_endpoint("/capabilities")


def test_assert_session_readonly_endpoint_rejects_others():
    with pytest.raises(bridge.SessionEndpointNotAllowed):
        bridge.assert_session_readonly_endpoint("/objects")
    with pytest.raises(bridge.SessionEndpointNotAllowed):
        bridge.assert_session_readonly_endpoint("/gh/add")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'assert_session_readonly_endpoint'`

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add directly below the `_SESSION_ID_PREFIX` constant (from Task 2):

```python
# P1 session targeting may touch ONLY these read-only endpoints. Mutating-route
# targeting is deliberately out of scope until a later phase; this guard fails
# closed so nothing else can be routed through a session in the meantime.
_READONLY_SESSION_ENDPOINTS = frozenset({"/ping", "/capabilities"})


class SessionEndpointNotAllowed(Exception):
    """Raised when a non-read-only endpoint is requested for a session call."""


def assert_session_readonly_endpoint(endpoint: str) -> None:
    if endpoint not in _READONLY_SESSION_ENDPOINTS:
        raise SessionEndpointNotAllowed(
            f"Endpoint {endpoint!r} is not in the P1 read-only session allowlist "
            f"{sorted(_READONLY_SESSION_ENDPOINTS)}."
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_sessions.py
git commit -m "feat(bridge): fail-closed read-only allowlist for session-targeted calls"
```

---

## Task 6: `get_session_capabilities`

**Files:**
- Modify: `mcp_server/src/rook/bridge.py` (add `get_session_capabilities` after `list_sessions_result`)
- Test: `mcp_server/tests/test_sessions.py`

> **Correction (added in review at Checkpoint 1 — shipped in `fc7e2c3`):** A **dead-state branch** was added to `get_session_capabilities`, placed **before** the `unreachable` branch. After a record matches in discovery, the process can die before `classify_session_liveness` returns `state="dead"`; the function must then return `success=False, code="rhino_session_dead"` and **never** call `resolve_capabilities` (whose bootstrap fallback would otherwise return a false `success=true` — a liveness lie P1 exists to prevent). Regression test `test_get_session_capabilities_dead_after_discovery_race` (stateful `_is_pid_alive`: alive at cleanup, dead at classification; asserts resolve is never called) brings this task's suite to **18** passing.

Contract (returns the `{"success", "data"}` envelope):
- Malformed `session` id → `success=False`, `data.code="invalid_session_id"`.
- No matching live instance → `success=False`, `data.code="rhino_session_dead"`.
- Matched but listener unreachable (PID alive, port down) → `success=False`, `data.code="rook_native_listener_unreachable"` (and the session is **not** reaped).
- Live → `success=True`, `data` includes `session`, `processId`, `liveness`, and the `resolve_capabilities` payload. Touches only `/capabilities`, asserted through the allowlist guard.

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_sessions.py`:

```python
@pytest.mark.asyncio
async def test_get_session_capabilities_invalid_id(sessions_dir):
    out = await bridge.get_session_capabilities("not-a-session")
    assert out["success"] is False
    assert out["data"]["code"] == "invalid_session_id"


@pytest.mark.asyncio
async def test_get_session_capabilities_dead_when_absent(sessions_dir, monkeypatch):
    # No discovery file for pid 999 => treated as dead/gone.
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    out = await bridge.get_session_capabilities("rhino-999")
    assert out["success"] is False
    assert out["data"]["code"] == "rhino_session_dead"
    assert out["data"]["session"] == "rhino-999"
    assert "next_action" in out["data"]


@pytest.mark.asyncio
async def test_get_session_capabilities_unreachable_does_not_reap(sessions_dir, monkeypatch):
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 555,
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: False)

    out = await bridge.get_session_capabilities("rhino-555")

    assert out["success"] is False
    assert out["data"]["code"] == "rook_native_listener_unreachable"
    # The discovery file must still be present (we never reap an alive process).
    assert (sessions_dir / "instance-555-native.json").exists()


@pytest.mark.asyncio
async def test_get_session_capabilities_pins_endpoint_to_allowlist(sessions_dir, monkeypatch):
    # A forged/malformed discovery record must NOT be able to redirect resolution
    # off the read-only allowlist. liveEndpoint="/objects" must be forced back to
    # "/capabilities" on the instance actually handed to resolve_capabilities.
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 77,
        "capabilities": {"liveEndpoint": "/objects"},
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    seen = {}

    async def capture_resolve(instance, timeout=None):
        seen["endpoint"] = (instance.get("capabilities") or {}).get("liveEndpoint")
        return {"source": "live", "capabilities": {"domains": []}}

    monkeypatch.setattr(bridge, "resolve_capabilities", capture_resolve)

    out = await bridge.get_session_capabilities("rhino-77")

    assert out["success"] is True
    assert seen["endpoint"] == "/capabilities"  # never "/objects"


@pytest.mark.asyncio
async def test_get_session_capabilities_live(sessions_dir, monkeypatch):
    _write_instance(sessions_dir, {
        "host": "127.0.0.1", "port": 10500, "pluginType": "native", "processId": 42,
    })
    monkeypatch.setattr(bridge, "_is_pid_alive", lambda pid: True)
    monkeypatch.setattr(bridge, "_is_port_listening", lambda host, port: True)

    async def fake_resolve(instance, timeout=None):
        return {"source": "live", "stale": False, "authoritative": True,
                "capabilities": {"domains": []}}

    monkeypatch.setattr(bridge, "resolve_capabilities", fake_resolve)

    out = await bridge.get_session_capabilities("rhino-42")

    assert out["success"] is True
    assert out["data"]["session"] == "rhino-42"
    assert out["data"]["processId"] == 42
    assert out["data"]["liveness"]["state"] == "live"
    assert out["data"]["capabilities"]["source"] == "live"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: FAIL with `AttributeError: module 'rook.bridge' has no attribute 'get_session_capabilities'`

- [ ] **Step 3: Write minimal implementation**

In `bridge.py`, add after `list_sessions_result`:

```python
async def get_session_capabilities(session_id: Any) -> dict[str, Any]:
    """Resolve live capabilities for one named session. Read-only.

    Touches only /capabilities (asserted via the read-only allowlist). Never
    spawns, kills, mutates, or reaps. Returns a structured error envelope for
    malformed ids, dead sessions, and unreachable-but-alive listeners.
    """
    process_id = _process_id_from_session_id(session_id)
    if process_id is None:
        return {
            "success": False,
            "data": {
                "code": "invalid_session_id",
                "session": session_id,
                "next_action": "Call list_sessions to get a valid session id (e.g. 'rhino-12345').",
            },
        }

    instance = next(
        (
            inst for inst in discover_instances()
            if inst.get("processId") == process_id and inst.get("pluginType") == "native"
        ),
        None,
    )
    if instance is None:
        return {
            "success": False,
            "data": {
                "code": "rhino_session_dead",
                "session": session_id,
                "processId": process_id,
                "next_action": "The session is gone. Call list_sessions to see live sessions.",
            },
        }

    liveness = classify_session_liveness(instance)
    if liveness["state"] == "unreachable":
        return {
            "success": False,
            "data": {
                "code": "rook_native_listener_unreachable",
                "session": session_id,
                "processId": process_id,
                "liveness": liveness,
                "next_action": (
                    "The Rhino process is alive but its RookNative listener is not "
                    "responding (plugin reload, listener restart, or a transient). "
                    "The session was left in place; retry shortly."
                ),
            },
        }

    # Read-only: PIN the effective endpoint to a vetted, allow-listed route.
    # resolve_capabilities() otherwise honors capabilities.liveEndpoint straight
    # from the discovery record (bridge.py:197-207). A malformed/forged record
    # could point liveEndpoint at any slash-prefixed route (e.g. "/objects"), so
    # asserting a literal here is not enough — we must force it on the instance
    # we actually pass down. Sanitize a copy, then assert, then resolve.
    endpoint = "/capabilities"
    assert_session_readonly_endpoint(endpoint)
    safe_instance = dict(instance)
    safe_capabilities = dict(safe_instance.get("capabilities") or {})
    safe_capabilities["liveEndpoint"] = endpoint
    safe_instance["capabilities"] = safe_capabilities
    resolved = await resolve_capabilities(safe_instance)
    return {
        "success": True,
        "data": {
            "session": session_id,
            "processId": process_id,
            "liveness": liveness,
            "capabilities": resolved,
        },
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py -v`
Expected: PASS (17 passed)

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_sessions.py
git commit -m "feat(bridge): get_session_capabilities — read-only, conservative on unreachable"
```

---

## Task 7: Wire the two read-only MCP tools

**Files:**
- Modify: `mcp_server/src/rook/server.py` (extend bridge import at line 52; add two `Tool(...)` in `list_tools()` after the `rhino_instances` Tool at ~line 2769; add two `case` handlers in `_call_tool_dispatch` next to `case "rhino_instances":` at ~line 12705)
- Test: `mcp_server/tests/test_session_tools.py` (create)

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_session_tools.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import server
from rook import bridge


@pytest.mark.asyncio
async def test_session_tools_are_registered():
    tools = await server.list_tools()
    names = {t.name for t in tools}
    assert "rhino_sessions" in names
    assert "rhino_session_capabilities" in names

    gsc = next(t for t in tools if t.name == "rhino_session_capabilities")
    assert gsc.inputSchema["required"] == ["session"]
    assert "session" in gsc.inputSchema["properties"]


@pytest.mark.asyncio
async def test_dispatch_list_sessions(monkeypatch):
    # server.py imports these names directly (server.py:52 pattern), so dispatch
    # calls server.list_sessions_result — patch THERE, not on the bridge module,
    # or the monkeypatch won't intercept.
    monkeypatch.setattr(
        server, "list_sessions_result",
        lambda: {"success": True, "data": {"sessions": [{"session": "rhino-1"}]}},
    )
    result = await server._call_tool_dispatch("rhino_sessions", {})
    assert result["success"] is True
    assert result["data"]["sessions"][0]["session"] == "rhino-1"


@pytest.mark.asyncio
async def test_dispatch_get_session_capabilities(monkeypatch):
    async def fake_gsc(session):
        return {"success": True, "data": {"session": session, "capabilities": {}}}

    monkeypatch.setattr(server, "get_session_capabilities", fake_gsc)
    result = await server._call_tool_dispatch(
        "rhino_session_capabilities", {"session": "rhino-7"}
    )
    assert result["success"] is True
    assert result["data"]["session"] == "rhino-7"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_tools.py -v`
Expected: FAIL — `test_session_tools_are_registered` fails the `in names` assertions; the dispatch tests raise/return an unknown-command result.

- [ ] **Step 3: Write minimal implementation**

(a) In `server.py:52`, replace the bridge import line with:

```python
from .bridge import (
    call_rhino,
    get_rhino_host,
    discover_instances,
    TIMEOUT,
    DISCOVERY_FOLDER,
    rhino_request_context,
    list_sessions_result,
    get_session_capabilities,
)
```

(b) In `list_tools()`, immediately after the `rhino_instances` `Tool(...)` (ends at line 2769), insert:

```python
        Tool(
            name="rhino_sessions",
            description="List discovered Rhino sessions (one per open Rhino window) with a liveness envelope (live / unreachable / dead). Read-only: does NOT launch, target, mutate, or close anything. Distinguishes a dead process from an alive process whose RookNative listener is temporarily unreachable. Use before targeting a specific Rhino window. NOTE: distinct from `session_list`, which lists past recording sessions for replay.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="rhino_session_capabilities",
            description="Resolve the live capability document for one Rhino session by its `session` id (from rhino_sessions, e.g. 'rhino-12345'). Read-only: touches only /capabilities. Returns a structured error if the session is dead (rhino_session_dead) or its listener is unreachable (rook_native_listener_unreachable).",
            inputSchema={
                "type": "object",
                "properties": {
                    "session": {
                        "type": "string",
                        "description": "Session id from rhino_sessions, e.g. 'rhino-12345'.",
                    }
                },
                "required": ["session"],
            },
        ),
```

(c) In `_call_tool_dispatch`, immediately after `case "rhino_instances":` block (line 12705-12706), insert:

```python
        case "rhino_sessions":
            result = list_sessions_result()

        case "rhino_session_capabilities":
            result = await get_session_capabilities(arguments.get("session"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_tools.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full session suite + a focused regression check**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_sessions.py mcp_server/tests/test_session_tools.py mcp_server/tests/test_bridge.py -v
```
Expected: PASS (existing `test_bridge.py` unaffected; new suites green).

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_session_tools.py
git commit -m "feat(mcp): expose read-only rhino_sessions and rhino_session_capabilities tools"
```

---

## Task 8: Live smoke verification (manual, against a real Rhino)

Per the project's "live smoke catches what mocks miss" rule, verify end-to-end against a running Rhino before opening the PR. This task has no code — it is a gate.

- [ ] **Step 1: Start Rhino with RookNative loaded.** Confirm a discovery file exists under `%LOCALAPPDATA%\Rook\discovery\`.

- [ ] **Step 2: In Claude Code, call `rhino_sessions`.** Expected: one session `rhino-<pid>` with `liveness.state == "live"`, correct `port`/`pluginVersion`. (If RoadCreator is also loaded, confirm there is still exactly **one** `rhino-<pid>` session, not two — the native-only filter.)

- [ ] **Step 3: Call `rhino_session_capabilities` with that session id.** Expected: `success: true`, a live `capabilities` payload with `source: "live"`.

- [ ] **Step 4: Unreachable path (synthetic record — do NOT unload the plugin).** Disabling/unloading RookNative will NOT reproduce this state: native `Stop()` calls `RemoveDiscoveryFile()` (`RookServer.cpp:2504`→`fs::remove` at `2309`), which deletes the discovery file, so the session would read as *dead/gone*, not *unreachable*. Instead, with Rhino running, reproduce "alive PID + closed port" deterministically:
  1. Back up the real native discovery file (`%LOCALAPPDATA%\Rook\discovery\instance-<rhinoPid>-native.json`) — move it aside (note: `_cleanup_stale_discovery_files` dedupes by `(pluginType, processId)`, so you must not leave two native files for the same PID).
  2. Write a replacement at the same path with the **real, live Rhino `processId`** but a `port` nothing listens on (e.g. `1`), keeping `pluginType: "native"`.
  3. Call `rhino_session_capabilities("rhino-<rhinoPid>")`. Expected: `success: false`, `code: "rook_native_listener_unreachable"`, and the file is **still present** (PID alive → never reaped).
  4. Restore the backed-up real file and confirm the session returns to `live`.

- [ ] **Step 5: Dead path.** Close that Rhino. Call `rhino_sessions`. Expected: the session is gone (discovery file reaped because PID is dead — note this comes from the discovery reap, not the classifier's `dead` branch). `rhino_session_capabilities("rhino-<old_pid>")` returns `code: "rhino_session_dead"`.

- [ ] **Step 6: Record the smoke outcomes in the PR body.** If any step deviates, file the gap as a new issue rather than widening this PR's scope.

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-06-02-rook-rhinomcp-architecture-assessment.md` §8):
- "Project records as named sessions" → Tasks 2, 4. ✅
- "session registry (in-process)" → `list_sessions()` is the read-through projection; no separate stateful registry needed in P1 (YAGNI — `discover_instances()` is the source of truth). ✅ (documented deviation: no persistent registry; SQLite explicitly deferred to P5 per §11.)
- "read-only tools list_sessions, get_session_capabilities" → exposed as `rhino_sessions` / `rhino_session_capabilities` (prefixed for legibility + to avoid the `session_list` clash); Tasks 4, 6, 7. ✅
- "session == a Rhino window" → native-only filter in `list_sessions` and the `get_session_capabilities` lookup, so the in-process roadcreator adapter (shares the Rhino PID) never produces a duplicate session. Regression test: `test_list_sessions_dedupes_roadcreator_sharing_rhino_pid`. ✅
- "read-only session targeting on a reviewed allowlist only" → Task 5 guard, enforced in Task 6 by **pinning** the effective endpoint (not just asserting a literal): `resolve_capabilities` honors `capabilities.liveEndpoint` from the discovery record (bridge.py:197-207), so Task 6 forces `liveEndpoint="/capabilities"` on a sanitized copy before resolving. Regression test: `test_get_session_capabilities_pins_endpoint_to_allowlist` (proves a record with `liveEndpoint="/objects"` still resolves only `/capabilities`). ✅
- "liveness: pid alive AND port listening, treated differently" → Task 3. ✅
- "structured dead vs unreachable; conservative deletion (dead-PID only)" → Task 3 codes; Task 6 unreachable-keeps-file test; reaping unchanged (existing `_cleanup_stale_discovery_files`). ✅
- Out of scope honored: no RookNative changes, no spawn/kill, no mutation routing, no `session` arg added to existing mutation tools. ✅

**2. Placeholder scan:** No TBD/TODO/"handle errors"/"similar to". Every code step shows complete code; every run step shows the command and expected result. ✅

**3. Type consistency:** `session_id_for_instance`/`_process_id_from_session_id` (Task 2) are used identically in Tasks 4 and 6. `classify_session_liveness` returns the same `{state,pidAlive,portListening,code}` shape consumed in Tasks 4 and 6. `list_sessions_result`/`get_session_capabilities` names match the server import and dispatch cases in Task 7. The `{"success","data"}` envelope matches the existing dispatch convention (`rhino_launch`, `rhino_ping`). ✅

---

## Notes / risks for the executor

- **Liveness probe ≠ readiness probe:** `_is_port_listening` / `classify_session_liveness` establish *transport liveness only* (the TCP port accepts a connection). They must **not** be read as semantic readiness — a listener can accept a socket mid-startup before it can serve. `/capabilities` (via `resolve_capabilities` in Task 6, with its bootstrap-fallback envelope) remains the authoritative capability/readiness check. Keep the two concerns separate.
- **Import weight:** `tests/test_session_tools.py` imports `rook.server`, which is large and pulls in agent/knowledge modules. It should import cleanly (tools are defined at module scope; the server only runs under `__main__`). If import is too slow/heavy in CI, the registration assertions can move to a thinner harness, but keep the dispatch tests.
- **`_call_tool_dispatch` shape:** Confirmed it sets `result` per case and returns the raw `{"success","data"}` envelope (caller wraps via `_format_tool_result`). If the local copy differs, place the two cases wherever the other `rhino_*` cases set `result` and ensure the same return path.
- **Patch the import site, not the source module:** `server.py:52` binds the bridge callables into the `server` namespace at import time, and dispatch calls the *local* name (`list_sessions_result()`, `get_session_capabilities(...)`). The Task 7 dispatch tests therefore monkeypatch `server.list_sessions_result` / `server.get_session_capabilities` — patching `bridge.*` would not intercept. (`from rook import bridge` in that test file is now only needed if you add bridge-level assertions; keep or drop as you see fit.)
- **Endpoint pinning is load-bearing, not cosmetic:** the read-only allowlist (Task 5) only constrains traffic if the endpoint that actually gets requested is the one asserted. Because `resolve_capabilities` reads `liveEndpoint` from the (potentially malformed) discovery record, Task 6 sanitizes a copy before resolving. Do not "simplify" this back to a bare `resolve_capabilities(instance)`.
- **No reaping regression:** The only behavior that could delete a discovery file is the pre-existing `_cleanup_stale_discovery_files()` (dead-PID only). This plan adds none. The Task 6 unreachable test asserts the file survives — keep it as the regression guard.
