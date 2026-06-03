# Router P3 — Explicit Session-Targeted Mutation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `session` ("rhino-<pid>") the canonical explicit target selector on the tool-call path — resolved through the *one* existing `resolve_tool_route` funnel, identity-only, with P2 owning call-time liveness.

**Architecture:** Add an `explicit_session` + `has_explicit_session` parameter to `targeting.resolve_tool_route`, inserting a **session rung above the explicit-port rung**; reuse `bridge._process_id_from_session_id` (parse) and a native-only instance lookup (resolve) to produce the existing `InstanceRef`, which flows through the unchanged `rhino_request_context` path. `server.call_tool` reads the selector, rejects `session` on non-routed tools, strips it from the dispatch payload, and renders new routing-error codes via `route_error_result`. No `call_rhino`/transport change, no RookNative/C++ change.

**Tech Stack:** Python 3.13, `pytest` + `pytest-asyncio` (already configured), `unittest.mock` (`AsyncMock`, `patch`). No new dependencies.

**Authoritative spec:** `docs/superpowers/specs/2026-06-03-p3-session-targeted-mutation-design.md`. Read it first.

**Commit convention:** every commit message ends with the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>` (omitted from the per-step examples below for brevity — add it to each).

---

## Source-of-truth facts (verified against current code)

- `resolve_tool_route(name, *, explicit_port=None)` lives at `targeting.py:873-999`. Ladder today: requires_rhino gate (874) → panel_config_error (879) → explicit_port format (886) → panel-lock branch (897-928) → explicit_port rung (932-951) → active (953-968) → auto/single/multiple (970-999).
- `ToolRoute` dataclass at `targeting.py:28-41`; `selection: Literal["explicit","active","auto","panel_locked","none"]` (`:33`); it already carries `invalid_port`, `requested_port`, `stale_target`, `document_serial_number`, etc.
- `route_error_result(route)` at `targeting.py:1227-1285` maps each `route.error` to `{success:false, data:{...}}` via `_error_result`/`_panel_error`. `_error_result(error, **payload)` at `:1012-1014`. `discovery_diagnostics()` supplies discovery-folder pointers (used by `requested_port_not_discovered`).
- Reusable targeting helpers: `instance_ref_from_instance(instance)` (`:705`, returns `InstanceRef|None`), `_native_preferred_instance(pid, instances)` (`:723`). `discover_instances` is imported from bridge (`:9`).
- Reusable bridge helpers: `session_id_for_instance(instance)` (`bridge.py:574`) and `_process_id_from_session_id(session_id) -> int|None` (`bridge.py:579`, already rejects `None`/`"rhino-"`/`"rhino-abc"`). **Import path is safe**: `targeting` imports from `bridge`; `bridge` imports `targeting` only lazily inside a function (`bridge.py:917`).
- Tool-policy sets end at `targeting.py:658-682`; `policy_for_tool(name).requires_rhino is True` ⟺ `name ∈ _RHINO_READ_TOOLS ∪ _RHINO_MUTATE_TOOLS` (+ unknown→mutate). `_META_TOOLS` includes `rhino_session_capabilities` (so it is **non-routed**).
- `call_tool` (the routing wrapper) at `server.py:19291-19346`: reads `explicit_port = arguments.get("port")` (`:19292`); non-routed branch dispatches directly (`:19313-19315`); resolves the route (`:19317`); on success binds `rhino_request_context(port, process_id, document_serial_number)` and dispatches (`:19339-19344`); sets `dispatch_arguments["port"]` only when `explicit_port is not None` (`:19336-19337`).
- `_call_tool_dispatch` (`server.py:12715+`) does `port = arguments.pop("port", None)` (`:12721`) and reads `arguments.get("session")` for `rhino_session_capabilities` (`:12731`) — so `session` must **not** be popped here; strip it in `call_tool`'s routed branch only.
- `call_rhino(port=None)` reads the contextvars set by `rhino_request_context` (`bridge.py:348-380`), and `select_rhino_instance` cross-checks `process_id` (`bridge.py:403-409`).
- **Test patterns:** unit tests `from rook import targeting`, autouse `reset_targeting_state()` fixture, `_inst(port, pid, name)` builds a native instance dict, monkeypatch `targeting.discover_instances`. Integration tests `from rook import server`, `await server.call_tool(name, args)`, `patch.object(server, "call_rhino", new_callable=AsyncMock)` (capture `bridge.get_rhino_request_context()` in a `side_effect`), result is a list whose `[0].text` is the JSON envelope. Panel lock is set with `targeting.initialize_from_environment({"ROOK_MCP_TARGET_MODE":"panel_locked","ROOK_MCP_TARGET_PROCESS_ID":"<pid>"})`.

**Run command (all P3 unit/integration tasks), from repo root:**
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v
```
Regression (Task 6 + final):
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_sessions.py mcp_server/tests/test_session_tools.py mcp_server/tests/test_bridge_diagnosis.py -v
```

---

## File Structure

- **Modify** `mcp_server/src/rook/targeting.py`
  - `ToolRoute`: add `invalid_session`, `requested_session`, `session_process_id`, `port_process_id` fields; add `"session"` to the `selection` Literal.
  - New module constant `_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {"rhino_session_capabilities"}` and helper `session_not_targetable_result(name)`.
  - `resolve_tool_route`: new params `explicit_session`, `has_explicit_session`; session-parse block (rung 3); panel-lock fail-closed for session; the new session rung (above explicit_port) with the selector-conflict logic.
  - `route_error_result`: branches for `invalid_session_id`, `rhino_session_not_found`, `selector_conflict`.
- **Modify** `mcp_server/src/rook/server.py` (`call_tool`, ~`:19291-19346`)
  - Read `has_explicit_session` + `explicit_session`; reject `session` on non-routed tools; thread the selector into `resolve_tool_route`; strip `session` from `dispatch_arguments`.
- **Create** `mcp_server/tests/test_session_routing.py` (all new unit + integration tests).
- **Create** `mcp_server/tools/p3_session_mutation_live_harness.py` and add a `p3-session-mutation` smoke choice to `scripts/run_rhino_runtime_harness.py`.

**Not touched:** `src/RookNative/**` (no C++), `bridge.call_rhino`/transport, any spawn/kill/registry path, `bind_active_instance`, document/serial selection.

---

## Task 1: Scaffolding — ToolRoute fields, `selection="session"`, non-routed set + helper

**Files:**
- Modify: `mcp_server/src/rook/targeting.py` (`ToolRoute` `:28-41`; new constant + helper near the tool-policy sets, after `policy_for_tool` `:686`)
- Test: `mcp_server/tests/test_session_routing.py` (create)

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_session_routing.py`:

```python
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import targeting


@pytest.fixture(autouse=True)
def reset_targeting_state():
    targeting.reset_targeting_state_for_tests()
    yield
    targeting.reset_targeting_state_for_tests()


def _inst(port: int, pid: int, name: str = "Doc.3dm", plugin_type: str = "native") -> dict:
    return {
        "host": "127.0.0.1",
        "port": port,
        "processId": pid,
        "pluginType": plugin_type,
        "documentName": name,
    }


def test_toolroute_supports_session_selection_and_fields():
    route = targeting.ToolRoute(
        success=True,
        selection="session",
        invalid_session="x",
        requested_session="rhino-7",
        session_process_id=7,
        port_process_id=9,
    )
    assert route.selection == "session"
    assert route.invalid_session == "x"
    assert route.requested_session == "rhino-7"
    assert route.session_process_id == 7
    assert route.port_process_id == 9


def test_non_routed_session_argument_tools_is_capabilities_only():
    assert targeting._NON_ROUTED_SESSION_ARGUMENT_TOOLS == {"rhino_session_capabilities"}


def test_session_not_targetable_result_shape():
    out = targeting.session_not_targetable_result("knowledge_query")
    assert out["success"] is False
    assert out["data"]["error"] == "session_not_targetable"
    assert out["data"]["tool"] == "knowledge_query"
    assert "session" in out["data"]["message"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v`
Expected: FAIL — `TypeError` on the unknown `ToolRoute` kwargs / `AttributeError: module 'rook.targeting' has no attribute '_NON_ROUTED_SESSION_ARGUMENT_TOOLS'`.

- [ ] **Step 3: Write minimal implementation**

In `targeting.py`, extend the `ToolRoute` dataclass (`:28-41`) — add the four fields after `invalid_port` and `"session"` to the Literal:

```python
@dataclass(frozen=True)
class ToolRoute:
    success: bool
    target: InstanceRef | None = None
    instance: dict[str, Any] | None = None
    selection: Literal["explicit", "active", "auto", "panel_locked", "session", "none"] = "none"
    warning: str | None = None
    error: str | None = None
    stale_target: InstanceRef | None = None
    instances: list[dict[str, Any]] | None = None
    alternatives: list[dict[str, Any]] | None = None
    document_serial_number: int | None = None
    requested_port: int | None = None
    invalid_port: object | None = None
    invalid_session: object | None = None
    requested_session: object | None = None
    session_process_id: int | None = None
    port_process_id: int | None = None
```

Add the import of the bridge session parser to the existing bridge-import line (`targeting.py:9`):

```python
from .bridge import (
    call_rhino,
    discover_instances,
    discovery_diagnostics,
    _process_id_from_session_id,
)
```

Insert the constant + helper immediately after `policy_for_tool` (`:686`):

```python
# Non-routed tools never execute against a Rhino session, so a `session` argument
# on them is a contract error (rejected, not silently ignored) — EXCEPT tools that
# legitimately own a non-routing `session` argument. This is an explicit exception
# list, NOT a second routing-policy surface; it grows only by intentional addition.
_NON_ROUTED_SESSION_ARGUMENT_TOOLS = {"rhino_session_capabilities"}


def session_not_targetable_result(name: str) -> dict[str, Any]:
    return _error_result(
        "session_not_targetable",
        message=(
            "This tool does not execute against a Rhino session; remove the "
            "'session' argument. Session targeting applies only to Rhino-routed tools."
        ),
        tool=name,
    )
```

> `_error_result` is defined later in the file (`:1012`) but is resolved at call time, so a forward reference from this helper is fine (Python looks up module globals when `session_not_targetable_result` runs, not at definition).

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_session_routing.py
git commit -m "feat(targeting): ToolRoute session fields + non-routed session-reject scaffolding"
```

---

## Task 2: Session parse + `invalid_session_id` (rung 3)

**Files:**
- Modify: `mcp_server/src/rook/targeting.py` (`resolve_tool_route` signature + parse block; `route_error_result` new branch)
- Test: `mcp_server/tests/test_session_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_session_routing.py`:

```python
def test_present_but_null_session_is_invalid(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session=None, has_explicit_session=True
    )
    assert route.success is False
    assert route.error == "invalid_session_id"


@pytest.mark.parametrize("bad", ["bogus", "rhino-", "rhino-abc", "rhino-0", "rhino--5", 12345])
def test_malformed_session_is_invalid(monkeypatch, bad):
    # Includes non-positive PIDs: the bridge parser leniently returns int("0")==0
    # and int("-5")==-5, so the parse gate must reject pid_s <= 0 as invalid (NOT
    # let them fall through to rhino_session_not_found).
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session=bad, has_explicit_session=True
    )
    assert route.error == "invalid_session_id"


def test_absent_session_skips_session_rung(monkeypatch):
    # No session key -> has_explicit_session False -> falls through to existing auto.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route("rhino_execute", has_explicit_session=False)
    assert route.success is True
    assert route.error is None
    assert route.selection == "auto"


def test_invalid_session_id_envelope(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="bogus", has_explicit_session=True
    )
    result = targeting.route_error_result(route)
    assert result["success"] is False
    assert result["data"]["error"] == "invalid_session_id"
    assert result["data"]["invalidSession"] == repr("bogus")
    assert "instances" in result["data"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -k session -v`
Expected: FAIL — `resolve_tool_route` has no `explicit_session`/`has_explicit_session` params (`TypeError`).

- [ ] **Step 3: Write minimal implementation**

In `targeting.py`, change the `resolve_tool_route` signature (`:873`):

```python
def resolve_tool_route(
    name: str,
    *,
    explicit_port: object | None = None,
    explicit_session: object | None = None,
    has_explicit_session: bool = False,
) -> ToolRoute:
```

Insert the session-parse block immediately after the `_PANEL_TARGET_CONFIG_ERROR` check (after `:884`, before the `if explicit_port is not None:` block at `:886`):

```python
    pid_s: int | None = None
    if has_explicit_session:
        pid_s = _process_id_from_session_id(explicit_session)
        # _process_id_from_session_id is lenient: "rhino-0" -> 0, "rhino--5" -> -5.
        # A real PID is positive, so reject None OR non-positive as malformed.
        if pid_s is None or pid_s <= 0:
            return ToolRoute(
                success=False,
                error="invalid_session_id",
                invalid_session=explicit_session,
                instances=instances,
            )
```

In `route_error_result` (`:1227`), add a branch before the final fallthrough (`:1285`):

```python
    if route.error == "invalid_session_id":
        return _error_result(
            "invalid_session_id",
            message=(
                "Session selector must be a string like 'rhino-<pid>' from "
                "rhino_sessions; null or malformed is invalid."
            ),
            invalidSession=repr(route.invalid_session),
            instances=route.instances or [],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v`
Expected: PASS (12 passed — 3 from Task 1 + 9 here; `test_malformed_session_is_invalid` is parametrized ×6).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_session_routing.py
git commit -m "feat(targeting): session parse rung — present-but-null/malformed -> invalid_session_id"
```

---

## Task 3: The session rung — resolve to `selection="session"`, else `rhino_session_not_found`

**Files:**
- Modify: `mcp_server/src/rook/targeting.py` (session rung after the panel-lock branch, before the explicit_port rung at `:932`; `route_error_result` new branch)
- Test: `mcp_server/tests/test_session_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_session_routing.py`:

```python
def test_session_selects_named_target_among_multiple(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7102", has_explicit_session=True
    )
    assert route.success is True
    assert route.selection == "session"
    assert route.target == targeting.InstanceRef(9951, 7102)


def test_session_bypasses_multiple_instance_mutate_refusal(monkeypatch):
    # Bare mutate with 2 instances would be multiple_rhino_instances; naming a
    # session disambiguates.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", has_explicit_session=True
    )
    assert route.success is True
    assert route.target == targeting.InstanceRef(9950, 7101)


def test_session_not_found_when_no_native_record(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-9999", has_explicit_session=True
    )
    assert route.success is False
    assert route.error == "rhino_session_not_found"


def test_session_not_found_when_only_roadcreator_for_pid(monkeypatch):
    # A session is the NATIVE listener; a pid with only a roadcreator record is not
    # a session.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9960, 7101, "A.3dm", plugin_type="roadcreator"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", has_explicit_session=True
    )
    assert route.error == "rhino_session_not_found"


def test_rhino_session_not_found_envelope(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [_inst(9950, 7101)])
    monkeypatch.setattr(targeting, "discovery_diagnostics", lambda: {
        "discoveryFolder": r"C:\disc", "discoveryFolders": [r"C:\disc"],
        "selection": "localappdata", "tempRoot": r"C:\t", "legacyTempDiscoveryFolder": r"C:\t\rook",
    })
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-9999", has_explicit_session=True
    )
    result = targeting.route_error_result(route)
    assert result["data"]["error"] == "rhino_session_not_found"
    assert result["data"]["session"] == "rhino-9999"
    assert result["data"]["discoveryFolder"] == r"C:\disc"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -k "session_selects or not_found or bypasses" -v`
Expected: FAIL — a valid session currently falls through to `auto` (selection `"auto"`, target may be the first instance, not the named one), and `rhino_session_not_found` is never produced.

- [ ] **Step 3: Write minimal implementation**

In `targeting.py`, insert the session rung **after** the panel-lock branch (after `:928`) and **before** `targets = _process_targets(instances)` (`:930`):

```python
    if has_explicit_session:
        inst_s = next(
            (
                instance
                for instance in instances
                if instance.get("processId") == pid_s
                and instance.get("pluginType") == "native"
                and instance_ref_from_instance(instance) is not None
            ),
            None,
        )
        if inst_s is None:
            return ToolRoute(
                success=False,
                error="rhino_session_not_found",
                requested_session=explicit_session,
                instances=instances,
            )
        ref = instance_ref_from_instance(inst_s)
        return ToolRoute(
            success=True,
            target=ref,
            instance=inst_s,
            selection="session",
            instances=instances,
        )
```

In `route_error_result`, add a branch before the final fallthrough (after the `invalid_session_id` branch):

```python
    if route.error == "rhino_session_not_found":
        diagnostics = discovery_diagnostics()
        return _error_result(
            "rhino_session_not_found",
            message=(
                "No discovered RookNative session owns that id. "
                "Call rhino_sessions for live sessions."
            ),
            session=route.requested_session,
            discoveryFolder=diagnostics.get("discoveryFolder"),
            discoveryFolders=diagnostics.get("discoveryFolders"),
            instances=route.instances or [],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v`
Expected: PASS (17 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_session_routing.py
git commit -m "feat(targeting): session rung resolves native target (selection=session) / rhino_session_not_found"
```

---

## Task 4: Selector conflict (session + port, PID-level)

**Files:**
- Modify: `mcp_server/src/rook/targeting.py` (extend the session rung with the both-present consistency check; `route_error_result` new branch)
- Test: `mcp_server/tests/test_session_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_session_routing.py`:

```python
def test_session_plus_same_pid_port_session_wins(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9950,
        has_explicit_session=True,
    )
    assert route.success is True
    assert route.selection == "session"
    assert route.target == targeting.InstanceRef(9950, 7101)


def test_session_plus_different_pid_port_is_conflict(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9951,
        has_explicit_session=True,
    )
    assert route.success is False
    assert route.error == "selector_conflict"


def test_session_plus_undiscovered_port_is_port_not_found(monkeypatch):
    # Conflict requires both selectors to resolve; an unknown port is a port error.
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9999,
        has_explicit_session=True,
    )
    assert route.error == "requested_port_not_discovered"


def test_selector_conflict_envelope(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", explicit_port=9951,
        has_explicit_session=True,
    )
    result = targeting.route_error_result(route)
    d = result["data"]
    assert d["error"] == "selector_conflict"
    assert d["session"] == "rhino-7101"
    assert d["requestedPort"] == 9951
    assert d["sessionProcessId"] == 7101
    assert d["portProcessId"] == 7102
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -k "conflict or same_pid or undiscovered" -v`
Expected: FAIL — the session rung currently ignores `explicit_port`, so a different-PID port still routes (selection `"session"`) and no `selector_conflict` is produced.

- [ ] **Step 3: Write minimal implementation**

In `targeting.py`, extend the session rung: insert the consistency check **between** the `inst_s is None` guard and the final `ref = ...` return:

```python
        if explicit_port is not None:
            owner = next(
                (instance for instance in instances if instance.get("port") == explicit_port),
                None,
            )
            if owner is None:
                return ToolRoute(
                    success=False,
                    error="requested_port_not_discovered",
                    requested_port=explicit_port,
                    instances=instances,
                )
            if owner.get("processId") != pid_s:
                return ToolRoute(
                    success=False,
                    error="selector_conflict",
                    requested_session=explicit_session,
                    requested_port=explicit_port,
                    session_process_id=pid_s,
                    port_process_id=owner.get("processId"),
                    instances=instances,
                )
        ref = instance_ref_from_instance(inst_s)
        return ToolRoute(
            success=True,
            target=ref,
            instance=inst_s,
            selection="session",
            instances=instances,
        )
```

> Note: `explicit_port` here is the raw argument. The format validation at `:886` runs *before* the session rung (rung 4 in the spec ladder), so a malformed port already returned `invalid_requested_port`; by the time the session rung reads `explicit_port`, it is either `None` or a normalized positive int.

In `route_error_result`, add the branch:

```python
    if route.error == "selector_conflict":
        return _error_result(
            "selector_conflict",
            message=(
                "session and port name different Rhino processes. Pass one selector, "
                "or a port on the same process as the session."
            ),
            session=route.requested_session,
            requestedPort=route.requested_port,
            sessionProcessId=route.session_process_id,
            portProcessId=route.port_process_id,
            instances=route.instances or [],
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v`
Expected: PASS (21 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_session_routing.py
git commit -m "feat(targeting): PID-level session/port selector conflict; same-PID port -> session wins"
```

---

## Task 5: Panel-lock fail-closed for `session`

**Files:**
- Modify: `mcp_server/src/rook/targeting.py` (panel-lock branch, `:897-928`)
- Test: `mcp_server/tests/test_session_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_session_routing.py`:

```python
def _lock_to(pid: int):
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": str(pid),
    })


def test_panel_lock_allows_in_lock_session(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])
    _lock_to(7101)
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7101", has_explicit_session=True
    )
    assert route.success is True
    assert route.selection == "panel_locked"
    assert route.target == targeting.InstanceRef(9950, 7101)


def test_panel_lock_rejects_out_of_lock_session(monkeypatch):
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])
    _lock_to(7101)
    route = targeting.resolve_tool_route(
        "rhino_execute", explicit_session="rhino-7102", has_explicit_session=True
    )
    assert route.success is False
    assert route.error == "panel_target_locked"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -k panel_lock -v`
Expected: FAIL — `test_panel_lock_rejects_out_of_lock_session` returns `selection="panel_locked"` success (lock branch ignores the session) instead of `panel_target_locked`.

- [ ] **Step 3: Write minimal implementation**

In `targeting.py`, inside the panel-lock branch, add the session fail-closed check immediately after `ref, canonical = locked_target` (`:906`) and before the `if explicit_port is not None:` block (`:907`):

```python
        if has_explicit_session and pid_s != lock.process_id:
            return ToolRoute(
                success=False,
                error="panel_target_locked",
                instances=instances,
            )
```

> An in-lock session (`pid_s == lock.process_id`) falls through to the locked target and reports `selection="panel_locked"` — the lock is the dominant fact (a session merely confirms it passed the lock). A PID-level conflict cannot arise in-lock: both selectors must equal `lock.process_id` or fail closed here / at the existing explicit-port guard (`:907-917`).

- [ ] **Step 4: Run test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -v`
Expected: PASS (23 passed).

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_session_routing.py
git commit -m "feat(targeting): panel-lock fail-closed for explicit session (coordinator cannot redirect a locked tab)"
```

---

## Task 6: `call_tool` wiring — read selector, reject on non-routed, thread + strip

**Files:**
- Modify: `mcp_server/src/rook/server.py` (`call_tool`, ~`:19291-19346`)
- Test: `mcp_server/tests/test_session_routing.py`

- [ ] **Step 1: Write the failing test**

Append to `mcp_server/tests/test_session_routing.py`:

```python
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_call_tool_routes_by_session_sets_context(monkeypatch):
    # Mirrors the proven context-capture pattern (a read tool that reaches
    # call_rhino without per-tool preprocessing). Session=rhino-7102 must route to
    # 7102 even though it is NOT the auto-first instance.
    from rook import bridge, server
    insts = [_inst(9950, 7101, "A.3dm"), _inst(9951, 7102, "B.3dm")]
    monkeypatch.setattr(server, "discover_instances", lambda: insts)
    monkeypatch.setattr(targeting, "discover_instances", lambda: insts)
    targeting.clear_active_target()

    captured = {}

    async def fake_call_rhino(*a, **k):
        captured.update(bridge.get_rhino_request_context())
        return {"success": True, "data": []}

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.side_effect = fake_call_rhino
        await server.call_tool("rhino_layers", {"session": "rhino-7102"})
    assert captured["port"] == 9951
    assert captured["process_id"] == 7102


@pytest.mark.asyncio
async def test_call_tool_session_bypasses_mutate_ambiguity(monkeypatch):
    # Two instances: a bare mutate refuses (multiple_rhino_instances); naming a
    # session disambiguates and dispatches.
    from rook import server
    insts = [_inst(9950, 7101, "A.3dm"), _inst(9951, 7102, "B.3dm")]
    monkeypatch.setattr(server, "discover_instances", lambda: insts)
    monkeypatch.setattr(targeting, "discover_instances", lambda: insts)
    targeting.clear_active_target()

    with patch.object(server, "call_rhino", new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"ok": True}}
        result = await server.call_tool(
            "rhino_execute", {"session": "rhino-7102", "code": "print(1)"}
        )
    assert "multiple_rhino_instances" not in result[0].text
    mock.assert_awaited()


@pytest.mark.asyncio
async def test_call_tool_strips_session_from_dispatch(monkeypatch):
    from rook import server
    insts = [_inst(9950, 7101, "A.3dm")]
    monkeypatch.setattr(server, "discover_instances", lambda: insts)
    monkeypatch.setattr(targeting, "discover_instances", lambda: insts)
    targeting.clear_active_target()

    captured = {}

    async def fake_dispatch(name, arguments):
        captured["arguments"] = arguments
        return {"success": True, "data": {}}

    with patch.object(server, "_call_tool_dispatch", new_callable=AsyncMock) as mock:
        mock.side_effect = fake_dispatch
        await server.call_tool(
            "rhino_execute", {"session": "rhino-7101", "code": "print(1)"}
        )
    assert "session" not in captured["arguments"]
    assert captured["arguments"]["code"] == "print(1)"


@pytest.mark.asyncio
async def test_call_tool_rejects_session_on_non_routed_tool(monkeypatch):
    from rook import server
    result = await server.call_tool(
        "knowledge_query", {"session": "rhino-7101", "intent": "x"}
    )
    assert "session_not_targetable" in result[0].text


@pytest.mark.asyncio
async def test_call_tool_allows_session_on_capabilities(monkeypatch):
    from rook import server
    monkeypatch.setattr(
        server, "get_session_capabilities",
        AsyncMock(return_value={"success": True, "data": {"session": "rhino-1"}}),
    )
    result = await server.call_tool("rhino_session_capabilities", {"session": "rhino-1"})
    assert "session_not_targetable" not in result[0].text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py -k call_tool -v`
Expected: FAIL — `call_tool` does not yet read/thread `session` (the mutation routes to the wrong instance or refuses as `multiple_rhino_instances`), does not strip it (it leaks into `captured["arguments"]`), and does not reject it on non-routed tools.

- [ ] **Step 3: Write minimal implementation**

In `server.py` `call_tool`, after `explicit_port = arguments.get("port")` (`:19292`) add:

```python
    has_explicit_session = "session" in arguments
    explicit_session = arguments.get("session")
```

Replace the non-routed branch (`:19313-19315`):

```python
    if not policy.requires_rhino:
        if has_explicit_session and name not in targeting._NON_ROUTED_SESSION_ARGUMENT_TOOLS:
            return _format_tool_result(targeting.session_not_targetable_result(name))
        raw_result = await _call_tool_dispatch(name, arguments)
        return _format_tool_result(raw_result)
```

Replace the route resolution call (`:19317`):

```python
    route = targeting.resolve_tool_route(
        name,
        explicit_port=explicit_port,
        explicit_session=explicit_session,
        has_explicit_session=has_explicit_session,
    )
```

Add the strip after the `if explicit_port is not None: dispatch_arguments["port"] = route.target.port` block (`:19336-19337`):

```python
    dispatch_arguments.pop("session", None)
```

- [ ] **Step 4: Run test to verify it passes + regression**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_session_routing.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_sessions.py mcp_server/tests/test_session_tools.py mcp_server/tests/test_bridge_diagnosis.py -v
```
Expected: PASS. The existing `test_multi_instance_targeting.py` contracts stay green — session is purely additive (new params default to absent/`False`), `explicit_port`/active/auto behavior is unchanged, and the non-routed branch only diverges when a `session` argument is present.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/tests/test_session_routing.py
git commit -m "feat(server): call_tool routes by session, rejects it on non-routed tools, strips it from dispatch"
```

---

## Task 7: Live smoke verification (against a real Rhino)

**Files:**
- Create: `mcp_server/tools/p3_session_mutation_live_harness.py`
- Modify: `scripts/run_rhino_runtime_harness.py` (add the `p3-session-mutation` smoke choice)

Per the project's "live smoke catches what mocks miss" rule, verify end-to-end before opening the PR. Follow the **P2 harness pattern** (`mcp_server/tools/p2_bridge_diagnosis_live_harness.py` is the structural template): it launches an OWNED throwaway Rhino, sets `ROOK_RHINO_PROCESS_ID` / `ROOK_RHINO_PORT`, runs scenarios against real OS/discovery state, and shuts the Rhino down gracefully — never touching the user's session.

- [ ] **Step 1: Add the smoke choice to the harness runner**

In `scripts/run_rhino_runtime_harness.py`, add a branch in `_smoke_command` (after the `p2-bridge-diagnosis` branch, ~`:65-72`):

```python
    if name == "p3-session-mutation":
        return (
            [
                sys.executable,
                "mcp_server/tools/p3_session_mutation_live_harness.py",
            ],
            repo_root,
        )
```

And add `"p3-session-mutation"` to the `--smoke` `choices` list (after `"p2-bridge-diagnosis"`, ~`:161-172`).

- [ ] **Step 2: Write the live harness**

Create `mcp_server/tools/p3_session_mutation_live_harness.py`. It drives the real `server.call_tool` routing wrapper against the owned Rhino's session id (`rhino-<owned pid>`), and validates the routing-error scenarios with synthetic discovery records. Honesty boundaries are documented in the docstring (the conflict/disambiguation scenarios use a *synthetic* second discovery record, not a second real Rhino).

```python
"""Live P3 session-targeted-routing harness.

Run via `scripts/run_rhino_runtime_harness.py --smoke p3-session-mutation`, which
launches an OWNED throwaway Rhino and sets ROOK_RHINO_PROCESS_ID / ROOK_RHINO_PORT.
It drives the REAL server.call_tool routing wrapper against the owned session and
validates the routing-error paths.

Honesty boundaries (so the PR claim stays precise):
  - The session-routed mutation and the bypass/conflict scenarios that need a
    "second instance" use a SYNTHETIC second discovery record (a fabricated native
    record with a throwaway pid/port), NOT a second real Rhino. They validate the
    routing decision, not a second live process.
  - Only the owned Rhino is ever mutated; it is shut down gracefully by the harness.

Scenarios:
  1. session_routes_mutation  — session-route a mutation, then read the object count
                                 back through the SAME session and assert it rose
                                 (success returns `data`; failures are "Error:"-
                                 prefixed, so there is no '"success": true' check).
  2. bogus_session_not_found   — session=rhino-<unused> -> rhino_session_not_found.
  3. session_disambiguates     — with a synthetic 2nd native record, FIRST prove a
                                 bare mutate refuses (multiple_rhino_instances), THEN
                                 prove session=<owned> routes the same call cleanly.
  4. selector_conflict         — session=<owned> + a synthetic different-pid port
                                 -> selector_conflict.
  5. non_routed_reject         — call_tool(knowledge_query, session=...) ->
                                 session_not_targetable.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def _ensure_import_path() -> None:
    src = Path(__file__).resolve().parents[1] / "src"
    if src.is_dir():
        sys.path.insert(0, str(src))


_ensure_import_path()

from rook import bridge, server, targeting  # noqa: E402

_RESULTS: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str) -> None:
    _RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)


def _owned() -> tuple[int, int]:
    return int(os.environ["ROOK_RHINO_PROCESS_ID"]), int(os.environ["ROOK_RHINO_PORT"])


def _text(result) -> str:
    return result[0].text if result else ""


async def scenario_session_routes_mutation(pid: int) -> None:
    # Prove a mutation actually LANDS in the named session: read the object count
    # before and after, through the SAME session. call_tool success returns just
    # `data` and failures are prefixed "Error:", so the honest signal is
    # "not an Error" + a concrete count delta — never a '"success": true' substring.
    sess = f"rhino-{pid}"

    def _count(t: str) -> int:
        try:
            d = json.loads(t)
            if isinstance(d, dict):
                return int(d.get("objectCount") or (d.get("data") or {}).get("objectCount") or 0)
        except Exception:
            pass
        return -1

    before = _text(await server.call_tool("rhino_document", {"session": sess}))
    create = _text(await server.call_tool(
        "rhino_execute",
        {"session": sess, "code": "import rhinoscriptsyntax as rs\nrs.AddPoint(0,0,0)"},
    ))
    after = _text(await server.call_tool("rhino_document", {"session": sess}))
    created_ok = not create.startswith("Error:")
    readback_ok = _count(after) > _count(before) >= 0
    _record(
        "session_routes_mutation", created_ok and readback_ok,
        f"created_ok={created_ok}, before={_count(before)}, after={_count(after)}",
    )


async def scenario_bogus_session(pid: int) -> None:
    out = await server.call_tool(
        "rhino_execute", {"session": "rhino-99999999", "code": "print(1)"}
    )
    txt = _text(out)
    _record("bogus_session_not_found", "rhino_session_not_found" in txt, txt[:160])


async def scenario_disambiguates(pid: int) -> None:
    # Honesty (P2 standard): FIRST prove a bare mutate REFUSES with two native
    # instances, THEN prove the same call routes cleanly when a session names the
    # target. The second instance is a SYNTHETIC discovery record, not a 2nd Rhino.
    real = bridge.discover_instances()
    synthetic = {"host": "127.0.0.1", "port": 1, "processId": 424242, "pluginType": "native"}

    def fake_discover():
        return list(real) + [synthetic]

    server.discover_instances = fake_discover
    targeting.discover_instances = fake_discover
    try:
        bare = _text(await server.call_tool("rhino_execute", {"code": "1+1"}))
        refused = "multiple_rhino_instances" in bare
        named = _text(await server.call_tool(
            "rhino_execute", {"session": f"rhino-{pid}", "code": "1+1"}
        ))
        routed = (
            "multiple_rhino_instances" not in named
            and "rhino_session_not_found" not in named
            and not named.startswith("Error:")
        )
        _record("session_disambiguates", refused and routed,
                f"bare_refused={refused}, named_routed={routed}")
    finally:
        server.discover_instances = bridge.discover_instances
        targeting.discover_instances = bridge.discover_instances


async def scenario_conflict(pid: int) -> None:
    real = bridge.discover_instances()
    synthetic = {"host": "127.0.0.1", "port": 1, "processId": 424242, "pluginType": "native"}

    def fake_discover():
        return list(real) + [synthetic]

    server.discover_instances = fake_discover
    targeting.discover_instances = fake_discover
    try:
        out = await server.call_tool(
            "rhino_execute", {"session": f"rhino-{pid}", "port": 1, "code": "print(1)"}
        )
        txt = _text(out)
        _record("selector_conflict", "selector_conflict" in txt, txt[:160])
    finally:
        server.discover_instances = bridge.discover_instances
        targeting.discover_instances = bridge.discover_instances


async def scenario_non_routed_reject(pid: int) -> None:
    out = await server.call_tool(
        "knowledge_query", {"session": f"rhino-{pid}", "intent": "x"}
    )
    txt = _text(out)
    _record("non_routed_reject", "session_not_targetable" in txt, txt[:160])


async def main() -> int:
    pid, port = _owned()
    print(f"Owned Rhino: pid={pid} port={port}", flush=True)
    await scenario_session_routes_mutation(pid)
    await scenario_bogus_session(pid)
    await scenario_disambiguates(pid)
    await scenario_conflict(pid)
    await scenario_non_routed_reject(pid)

    passed = sum(1 for _, ok, _ in _RESULTS if ok)
    print(f"\n=== P3 live smoke: {passed}/{len(_RESULTS)} PASS ===", flush=True)
    return 0 if passed == len(_RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 3: Run the live smoke**

Run: `mcp_server/.venv/Scripts/python.exe scripts/run_rhino_runtime_harness.py --smoke p3-session-mutation`
Expected: harness launches an owned Rhino, prints `=== P3 live smoke: 5/5 PASS ===`, and shuts the Rhino down gracefully (`graceful_exit` / `success`). If any scenario fails, read the captured envelope text, fix, and re-run. Record the 5/5 result and the honesty boundary (synthetic second record) in the PR body.

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tools/p3_session_mutation_live_harness.py scripts/run_rhino_runtime_harness.py
git commit -m "test(p3): live session-routing smoke harness (owned Rhino; synthetic 2nd record for routing-error paths)"
```

---

## Task 8: Finish the development branch

- [ ] **Step 1: Full regression**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/ -q
```
Expected: all green (the P3 suite + the existing ~156 P1/P2 tests).

- [ ] **Step 2: Finish**

Announce and use **superpowers:finishing-a-development-branch** — verify tests pass, present the 4 options, execute the user's choice (default for this stream: push + open a PR for Codex review, then squash-merge).

---

## Self-Review

**1. Spec coverage** (against `2026-06-03-p3-session-targeted-mutation-design.md`):
- §4.1 selector + presence flag + present-but-null→invalid → Task 2 (`has_explicit_session`, parse via `_process_id_from_session_id`). ✅
- §4.2 admission = `requires_rhino` → no allowlist added; session honored on any routed tool (Task 6 threads it for the `requires_rhino` path only). ✅
- §4.3 non-routed reject + exception set → Task 1 (set + helper) + Task 6 (guard). ✅
- §4.4 strip on routed path → Task 6 (`dispatch_arguments.pop("session", None)`). ✅
- §5 resolver identity-only (native lookup; no liveness probe) → Task 3. ✅
- §6 ladder (session above port; bypasses ambiguity) → Tasks 2/3/4/5. ✅
- §7 five guards: parse (T2), not-found (T3), panel-lock fail-closed (T5), conflict PID-level (T4), active-default (unchanged — session/port both absent falls to active, covered by existing tests + `test_absent_session_skips_session_rung`). ✅
- §8 four codes + envelopes → `route_error_result` branches (T2/T3/T4) + `session_not_targetable_result` (T1/T6). ✅
- §9 `selection="session"` → Task 1 (literal) + Task 3 (returned). ✅
- §11 testing (unit + conflict matrix + panel lock + non-routed + strip + live smoke) → Tasks 2-7. ✅

**2. Placeholder scan:** No TBD/TODO. Every code step shows complete code; every run step has a command + expected result. The live-harness scenarios are fully specified with assertions. ✅

**3. Type consistency:** `resolve_tool_route(name, *, explicit_port=None, explicit_session=None, has_explicit_session=False)` is identical across Tasks 2/3/4/5/6. `ToolRoute` fields `invalid_session`/`requested_session`/`session_process_id`/`port_process_id` are defined in Task 1 and read identically in `route_error_result` (Tasks 2/3/4). `_NON_ROUTED_SESSION_ARGUMENT_TOOLS` and `session_not_targetable_result(name)` names match between Task 1 (definition) and Task 6 (use). The error strings (`invalid_session_id`, `rhino_session_not_found`, `selector_conflict`, `session_not_targetable`) and the `selection="session"` literal are spelled identically everywhere. `_process_id_from_session_id` matches the bridge export. ✅

---

## Notes / risks for the executor

- **Ladder order is load-bearing.** The session-parse block must precede the explicit_port format check; the panel-lock session guard must be inside the lock branch (fail-closed-first); the session rung must sit **between** the panel-lock branch and the `_process_targets`/explicit_port rung. Misordering changes which error wins (e.g. a session+out-of-lock-port would wrongly become `selector_conflict` instead of `panel_target_locked`).
- **Do not pop `session` in `_call_tool_dispatch`.** `rhino_session_capabilities` reads `arguments.get("session")` there on the non-routed path; popping it globally breaks that tool. Strip only in `call_tool`'s `requires_rhino` branch.
- **Native-only session resolution.** The session rung matches `pluginType == "native"` (a session is the native listener, per P1's dedup). A pid with only a roadcreator record is `rhino_session_not_found`, not a roadcreator route.
- **`server.py` imports bridge callables by name** (`server.py:52`), so the integration tests monkeypatch `server.get_session_capabilities` / `server.call_rhino` / `server._call_tool_dispatch` / `server.discover_instances`, never the `bridge.*` originals.
- **No transport change.** P3 never touches `call_rhino`; a session that dies between resolution and dispatch is P2's `rhino_session_dead`, not a P3 concern. Keep the layers split.
