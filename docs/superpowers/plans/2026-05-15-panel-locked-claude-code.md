# Panel-Locked Claude Code Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` (recommended for this tightly coupled change) or `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make embedded Claude Code tabs use a strict, Rook-only MCP server locked to the owning Rhino process and panel document.

**Architecture:** The Python MCP server owns the lock state in `rook.targeting`, initializes it once from env, and enforces it before active binding or auto-discovery. The dispatcher and direct bridge path both install locked process/document context and reject conflicting process, port, or document targets. The C# Claude wrapper generates a per-tab strict MCP config containing only the locked `rook` server.

**Tech Stack:** Python 3, pytest, MCP server stdio, Rhino bridge discovery files, C#/.NET net48/net7.0, xUnit.

---

## File Structure

- Modify `mcp_server/src/rook/targeting.py`
  - Add panel lock dataclasses/state, env initialization, test reset helpers, lock error helpers, document validation helpers, and lock-aware resolver/binding/meta behavior.
- Modify `mcp_server/src/rook/server.py`
  - Initialize targeting lock state on import/startup.
  - Pass explicit `documentSerialNumber` into route resolution.
  - Install locked `document_serial_number` in `rhino_request_context`.
  - Reject `spawn_agent`, `plan_and_execute`, `rhino_launch`, and clear/set-active cases according to lock state.
- Modify `mcp_server/src/rook/bridge.py`
  - Enforce panel lock in `call_rhino()` inputs using a lazy import from `rook.targeting`.
  - Inject locked `documentSerialNumber` or reject conflicts before HTTP dispatch.
- Modify `mcp_server/tests/test_multi_instance_targeting.py`
  - Add targeting/resolver/meta/dispatcher tests for panel lock.
- Modify `mcp_server/tests/test_bridge.py`
  - Add direct `call_rhino()` and endpoint routing tests for panel lock.
- Create `src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs`
  - Pure helper for copying the global `rook` MCP entry into a strict panel-locked temp config.
- Modify `src/Rook/UI/Chat/ClaudeCodeWrapper.cs`
  - Use `ClaudePanelMcpConfigBuilder`, launch with `--strict-mcp-config`, update prompt, and cleanup temp config best-effort.
- Create `src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs`
  - xUnit tests for strict Rook-only config generation and env preservation.
- Modify `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`
  - Source-level test that `ClaudeCodeWrapper` launch args use strict config and panel prompt text.

---

## Task 1: Panel Lock State And Env Initialization

**Files:**
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_multi_instance_targeting.py`

- [ ] **Step 1: Write failing tests for env initialization**

Add these tests near the existing policy tests in `mcp_server/tests/test_multi_instance_targeting.py`:

```python
def test_panel_lock_initializes_from_valid_env(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    monkeypatch.setenv("ROOK_MCP_TARGET_PROCESS_ID", "7101")
    monkeypatch.setenv("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER", "42")

    targeting.initialize_from_environment()

    lock = targeting.get_panel_target_lock()
    assert lock is not None
    assert lock.mode == "panel_locked"
    assert lock.process_id == 7101
    assert lock.document_serial_number == 42
    assert lock.reason == "rook_chat_panel"
    assert targeting.get_panel_target_config_error() is None


def test_panel_lock_missing_process_id_fails_closed(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_locked")
    monkeypatch.delenv("ROOK_MCP_TARGET_PROCESS_ID", raising=False)

    targeting.initialize_from_environment()

    assert targeting.get_panel_target_lock() is None
    error = targeting.get_panel_target_config_error()
    assert error is not None
    assert error["error"] == "panel_target_config_error"


def test_unknown_target_mode_fails_closed(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.setenv("ROOK_MCP_TARGET_MODE", "panel_lokced")
    monkeypatch.setenv("ROOK_MCP_TARGET_PROCESS_ID", "7101")

    targeting.initialize_from_environment()

    assert targeting.get_panel_target_lock() is None
    error = targeting.get_panel_target_config_error()
    assert error is not None
    assert error["error"] == "panel_target_config_error"


def test_no_target_mode_preserves_external_behavior(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    monkeypatch.delenv("ROOK_MCP_TARGET_MODE", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_PROCESS_ID", raising=False)
    monkeypatch.delenv("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER", raising=False)

    targeting.initialize_from_environment()

    assert targeting.get_panel_target_lock() is None
    assert targeting.get_panel_target_config_error() is None
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py::test_panel_lock_initializes_from_valid_env `
  mcp_server/tests/test_multi_instance_targeting.py::test_panel_lock_missing_process_id_fails_closed `
  mcp_server/tests/test_multi_instance_targeting.py::test_unknown_target_mode_fails_closed `
  mcp_server/tests/test_multi_instance_targeting.py::test_no_target_mode_preserves_external_behavior -q
```

Expected: FAIL because `reset_targeting_state_for_tests`, `initialize_from_environment`, `get_panel_target_lock`, and `get_panel_target_config_error` do not exist yet.

- [ ] **Step 3: Implement lock state in `targeting.py`**

Add these definitions after `UNKNOWN_TOOL_POLICY` and before `_ACTIVE_TARGET`:

```python
@dataclass(frozen=True)
class PanelTargetLock:
    mode: Literal["panel_locked"]
    process_id: int
    document_serial_number: int | None
    reason: str = "rook_chat_panel"


_PANEL_TARGET_LOCK: PanelTargetLock | None = None
_PANEL_TARGET_CONFIG_ERROR: dict[str, Any] | None = None
_ENV_INITIALIZED = False


def reset_targeting_state_for_tests() -> None:
    global _ACTIVE_TARGET, _PANEL_TARGET_LOCK, _PANEL_TARGET_CONFIG_ERROR, _ENV_INITIALIZED
    _ACTIVE_TARGET = None
    _PANEL_TARGET_LOCK = None
    _PANEL_TARGET_CONFIG_ERROR = None
    _ENV_INITIALIZED = False


def get_panel_target_lock() -> PanelTargetLock | None:
    return _PANEL_TARGET_LOCK


def get_panel_target_config_error() -> dict[str, Any] | None:
    return None if _PANEL_TARGET_CONFIG_ERROR is None else dict(_PANEL_TARGET_CONFIG_ERROR)


def _parse_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _set_panel_config_error(message: str, *, mode: str | None = None) -> None:
    global _PANEL_TARGET_CONFIG_ERROR, _PANEL_TARGET_LOCK
    _PANEL_TARGET_LOCK = None
    _PANEL_TARGET_CONFIG_ERROR = {
        "error": "panel_target_config_error",
        "message": message,
        "locked": True,
        "lockMode": mode or "panel_locked",
        "lockReason": "rook_chat_panel",
    }


def initialize_from_environment(env: dict[str, str] | None = None) -> None:
    global _ENV_INITIALIZED, _PANEL_TARGET_LOCK, _PANEL_TARGET_CONFIG_ERROR
    if _ENV_INITIALIZED:
        return
    _ENV_INITIALIZED = True
    source = env if env is not None else __import__("os").environ
    mode = (source.get("ROOK_MCP_TARGET_MODE") or "").strip()
    if not mode:
        _PANEL_TARGET_LOCK = None
        _PANEL_TARGET_CONFIG_ERROR = None
        return
    if mode != "panel_locked":
        _set_panel_config_error(
            f"Unknown ROOK_MCP_TARGET_MODE '{mode}'.",
            mode=mode,
        )
        return
    process_id = _parse_positive_int(source.get("ROOK_MCP_TARGET_PROCESS_ID"))
    if process_id is None:
        _set_panel_config_error(
            "This Rook MCP server was started in panel-locked mode without a valid Rhino process id."
        )
        return
    document_serial = _parse_positive_int(
        source.get("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER")
    )
    _PANEL_TARGET_LOCK = PanelTargetLock(
        mode="panel_locked",
        process_id=process_id,
        document_serial_number=document_serial,
    )
    _PANEL_TARGET_CONFIG_ERROR = None
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py::test_panel_lock_initializes_from_valid_env `
  mcp_server/tests/test_multi_instance_targeting.py::test_panel_lock_missing_process_id_fails_closed `
  mcp_server/tests/test_multi_instance_targeting.py::test_unknown_target_mode_fails_closed `
  mcp_server/tests/test_multi_instance_targeting.py::test_no_target_mode_preserves_external_behavior -q
```

Expected: `4 passed`.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_multi_instance_targeting.py
git commit -m "feat: add panel target lock state"
```

---

## Task 2: Lock-Aware Resolver And Binding Tools

**Files:**
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_multi_instance_targeting.py`

- [ ] **Step 1: Write failing resolver tests**

Add these tests in `mcp_server/tests/test_multi_instance_targeting.py`:

```python
def test_panel_lock_routes_read_tool_to_locked_process_without_auto_pick(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_document")

    assert route.success is True
    assert route.selection == "panel_locked"
    assert route.target == targeting.InstanceRef(9951, 7102)
    assert route.document_serial_number == 42
    assert route.warning is None


def test_panel_lock_rejects_explicit_different_process_port(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        _inst(9951, 7102, "B.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_execute", explicit_port=9950)

    assert route.success is False
    assert route.error == "panel_target_locked"
    assert route.target is None


def test_panel_lock_stale_owner_wins_over_conflicting_explicit_port(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7109",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
    ])

    route = targeting.resolve_tool_route("rhino_execute", explicit_port=9950)

    assert route.success is False
    assert route.error == "panel_target_stale"
    assert route.instances == [_inst(9950, 7101, "A.3dm")]
```

Add same-process RoadCreator canonicalization:

```python
def test_panel_lock_allows_same_process_roadcreator_peer(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "A.3dm"),
        {
            "host": "127.0.0.1",
            "port": 9960,
            "processId": 7101,
            "pluginType": "roadcreator",
            "documentName": "A.3dm",
        },
    ])

    route = targeting.resolve_tool_route("rhino_document", explicit_port=9960)

    assert route.success is True
    assert route.target == targeting.InstanceRef(9950, 7101)
    assert route.selection == "panel_locked"
```

- [ ] **Step 2: Write failing binding/meta tests**

Add:

```python
@pytest.mark.asyncio
async def test_panel_lock_bind_match_prefers_same_process_match(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "SK-101-other.3dm"),
        _inst(9951, 7102, "SK-101-panel.3dm"),
    ])

    result = await targeting.bind_active_instance(match="SK-101")

    assert result["success"] is True
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)
    assert result["data"]["locked"] is True


@pytest.mark.asyncio
async def test_panel_lock_bind_match_other_process_only_fails_locked(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9950, 7101, "SK-101-other.3dm"),
        _inst(9951, 7102, "Panel.3dm"),
    ])

    result = await targeting.bind_active_instance(match="SK-101")

    assert result["success"] is False
    assert result["data"]["error"] == "panel_target_locked"
    assert targeting.get_active_target() is None


def test_panel_lock_clear_active_instance_fails():
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    targeting.set_active_target(targeting.InstanceRef(9951, 7102))

    result = targeting.clear_active_instance_result()

    assert result["success"] is False
    assert result["data"]["error"] == "panel_target_locked"
    assert targeting.get_active_target() == targeting.InstanceRef(9951, 7102)


@pytest.mark.asyncio
async def test_panel_lock_instances_result_reports_lock(monkeypatch):
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        _inst(9951, 7102, "B.3dm"),
    ])

    result = await targeting.instances_result()

    assert result["success"] is True
    assert result["data"]["lock"]["locked"] is True
    assert result["data"]["lock"]["target"]["processId"] == 7102
    assert result["data"]["lock"]["target"]["documentSerialNumber"] == 42
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py -k "panel_lock" -q
```

Expected: FAIL because `ToolRoute` has no `document_serial_number`, no `panel_locked` selection, and binding/meta functions do not enforce lock.

- [ ] **Step 4: Implement lock helpers and resolver branches**

In `ToolRoute`, extend selection and document serial:

```python
selection: Literal["explicit", "active", "auto", "panel_locked", "none"] = "none"
document_serial_number: int | None = None
```

Add helpers after `_process_targets`:

```python
def _lock_payload(lock: PanelTargetLock | None = None) -> dict[str, Any]:
    current = lock or _PANEL_TARGET_LOCK
    payload: dict[str, Any] = {
        "locked": current is not None or _PANEL_TARGET_CONFIG_ERROR is not None,
        "lockMode": "panel_locked",
        "lockReason": "rook_chat_panel",
    }
    if current is not None:
        payload["target"] = {
            "processId": current.process_id,
            "documentSerialNumber": current.document_serial_number,
        }
    return payload


def _panel_error(error: str, message: str, *, instances: list[dict[str, Any]] | None = None, requested: dict[str, Any] | None = None) -> dict[str, Any]:
    data = {
        "error": error,
        "message": message,
        **_lock_payload(),
    }
    if instances is not None:
        data["instances"] = instances
    if requested:
        data.update(requested)
    return {"success": False, "data": data}


def _locked_process_instances(instances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    lock = _PANEL_TARGET_LOCK
    if lock is None:
        return []
    return [instance for instance in instances if instance.get("processId") == lock.process_id]


def _resolve_locked_target(instances: list[dict[str, Any]]) -> tuple[InstanceRef, dict[str, Any]] | None:
    locked = _locked_process_instances(instances)
    if not locked:
        return None
    targets = _process_targets(locked)
    return targets[0] if targets else None
```

At the top of `resolve_tool_route()` after policy check and before external behavior, add:

```python
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return ToolRoute(
            success=False,
            error="panel_target_config_error",
            instances=[],
        )

    lock = _PANEL_TARGET_LOCK
    if lock is not None:
        instances = discover_instances()
        locked_target = _resolve_locked_target(instances)
        if locked_target is None:
            return ToolRoute(
                success=False,
                error="panel_target_stale",
                instances=instances,
            )
        ref, canonical = locked_target
        if explicit_port is not None:
            explicit = next(
                (instance for instance in instances if instance.get("port") == explicit_port),
                None,
            )
            if explicit is None or explicit.get("processId") != lock.process_id:
                return ToolRoute(
                    success=False,
                    error="panel_target_locked",
                    instances=instances,
                )
            target = _target_from_instance(explicit, instances)
            if target is not None:
                ref, canonical = target
        return ToolRoute(
            success=True,
            target=ref,
            instance=canonical,
            selection="panel_locked",
            instances=instances,
            document_serial_number=lock.document_serial_number,
        )
```

Update `route_error_result()` with panel errors:

```python
    if route.error == "panel_target_config_error":
        config = get_panel_target_config_error() or {}
        return {"success": False, "data": config}
    if route.error == "panel_target_stale":
        return _panel_error(
            "panel_target_stale",
            "The Rhino process that owns this Claude Code tab is no longer available.",
            instances=route.instances or [],
        )
    if route.error == "panel_target_locked":
        return _panel_error(
            "panel_target_locked",
            "This Claude Code tab is locked to the Rhino document that owns the panel.",
            instances=route.instances or [],
        )
```

Update `bind_active_instance()` before normal matching:

```python
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return {"success": False, "data": get_panel_target_config_error()}
    lock = _PANEL_TARGET_LOCK
```

After `matched` is built, if `lock is not None`, constrain target resolution:

```python
    if lock is not None:
        locked_matches = [
            instance for instance in matched
            if instance.get("processId") == lock.process_id
        ]
        if not locked_matches:
            if matched:
                return _panel_error(
                    "panel_target_locked",
                    "This Claude Code tab is locked to the Rhino document that owns the panel.",
                    instances=instances,
                )
            return _error_result(error, instances=instances)
        matched = locked_matches
```

When `bind_active_instance()` succeeds under lock, include lock metadata:

```python
    response_data = {"active": active_payload}
    if _PANEL_TARGET_LOCK is not None:
        response_data.update(_lock_payload())
    return {"success": True, "data": response_data}
```

Update `clear_active_instance_result()`:

```python
    if _PANEL_TARGET_LOCK is not None:
        return _panel_error(
            "panel_target_locked",
            "This Claude Code tab is locked to the Rhino document that owns the panel.",
        )
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return {"success": False, "data": get_panel_target_config_error()}
```

Update `get_active_instance_result()` and `instances_result()` to add `lock` data:

```python
    data = {"active": payload}
    if _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None:
        data["lock"] = get_lock_state_result()["data"]["lock"]
    return {"success": True, "data": data}
```

Add:

```python
def get_lock_state_result() -> dict[str, Any]:
    if _PANEL_TARGET_CONFIG_ERROR is not None:
        return {"success": True, "data": {"lock": get_panel_target_config_error()}}
    payload = _lock_payload()
    if _PANEL_TARGET_LOCK is None:
        payload = {"locked": False}
    else:
        payload["live"] = _resolve_locked_target(discover_instances()) is not None
    return {"success": True, "data": {"lock": payload}}
```

- [ ] **Step 5: Run targeting tests**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py -q
```

Expected: all tests in the file pass.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server/src/rook/targeting.py mcp_server/tests/test_multi_instance_targeting.py
git commit -m "feat: enforce panel lock in target resolver"
```

---

## Task 3: MCP Dispatcher Document Lock And Tool Behavior

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_multi_instance_targeting.py`
- Test: `mcp_server/tests/test_bridge.py`

- [ ] **Step 1: Write failing dispatcher tests**

Add to `mcp_server/tests/test_multi_instance_targeting.py`:

```python
def test_panel_document_allows_missing_or_matching_serial():
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })

    assert targeting.apply_locked_document_context({}) == {"documentSerialNumber": 42}
    assert targeting.apply_locked_document_context({"documentSerialNumber": 42}) == {"documentSerialNumber": 42}
    assert targeting.apply_locked_document_context({"documentSerialNumber": 0}) == {"documentSerialNumber": 42}


def test_panel_document_rejects_conflicting_positive_serial():
    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })

    result = targeting.apply_locked_document_context({"documentSerialNumber": 99})

    assert result["success"] is False
    assert result["data"]["error"] == "panel_document_locked"
    assert result["data"]["requestedDocumentSerialNumber"] == 99
```

Add to `mcp_server/tests/test_bridge.py`:

```python
@pytest.mark.asyncio
async def test_call_tool_installs_locked_document_context(monkeypatch):
    from rook import server, targeting
    from rook.bridge import get_rhino_request_context

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    captured = {}

    async def fake_dispatch(name, arguments):
        captured["context"] = get_rhino_request_context()
        captured["arguments"] = dict(arguments)
        return {"success": True, "data": {"ok": True}}

    monkeypatch.setattr(server, "_call_tool_dispatch", fake_dispatch)

    await server.call_tool("rhino_document", {})

    assert captured["context"]["process_id"] == 7101
    assert captured["context"]["document_serial_number"] == 42
    assert captured["arguments"]["documentSerialNumber"] == 42


@pytest.mark.asyncio
async def test_call_tool_rejects_conflicting_document_serial(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    result = await server.call_tool("rhino_document", {"documentSerialNumber": 99})
    text = result[0].text

    assert "panel_document_locked" in text
    assert "requestedDocumentSerialNumber" in text
```

- [ ] **Step 2: Write failing tool-specific tests**

Add:

```python
@pytest.mark.asyncio
async def test_panel_lock_blocks_spawn_agent_before_background_task(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    result = await server.call_tool("spawn_agent", {"prompt": "create a box"})

    assert "panel_target_locked" in result[0].text


@pytest.mark.asyncio
async def test_panel_lock_launch_stale_owner_returns_stale(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7109",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])

    result = await server.call_tool("rhino_launch", {})

    assert "panel_target_stale" in result[0].text


@pytest.mark.asyncio
async def test_panel_lock_launch_live_owner_does_not_auto_bind(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    monkeypatch.setattr(targeting, "discover_instances", lambda: [
        {"host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native"},
    ])
    called = {"bind": False}
    monkeypatch.setattr(
        targeting,
        "bind_single_available_instance",
        lambda: called.__setitem__("bind", True),
    )

    async def fake_dispatch(name, arguments):
        return {"success": True, "data": {"status": "launched"}}

    monkeypatch.setattr(server, "_call_tool_dispatch", fake_dispatch)

    result = await server.call_tool("rhino_launch", {})

    assert '"status": "launched"' in result[0].text
    assert called["bind"] is False
```

- [ ] **Step 3: Run tests and verify they fail**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py::test_panel_document_allows_missing_or_matching_serial `
  mcp_server/tests/test_multi_instance_targeting.py::test_panel_document_rejects_conflicting_positive_serial `
  mcp_server/tests/test_bridge.py::test_call_tool_installs_locked_document_context `
  mcp_server/tests/test_bridge.py::test_call_tool_rejects_conflicting_document_serial `
  mcp_server/tests/test_bridge.py::test_panel_lock_blocks_spawn_agent_before_background_task `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_stale_owner_returns_stale `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_live_owner_does_not_auto_bind -q
```

Expected: FAIL because document helper and dispatcher lock branches do not exist.

- [ ] **Step 4: Implement document helper in `targeting.py`**

Add:

```python
def apply_locked_document_context(arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = dict(arguments) if arguments else {}
    lock = _PANEL_TARGET_LOCK
    if lock is None or not lock.document_serial_number:
        return args
    requested = _parse_positive_int(args.get("documentSerialNumber"))
    if requested is not None and requested != lock.document_serial_number:
        return _panel_error(
            "panel_document_locked",
            "This Claude Code tab is locked to the Rhino document that owns the panel.",
            requested={"requestedDocumentSerialNumber": requested},
        )
    args["documentSerialNumber"] = lock.document_serial_number
    return args
```

- [ ] **Step 5: Initialize environment and enforce document context in `server.py`**

After importing `targeting`, add:

```python
targeting.initialize_from_environment()
```

In `call_tool()`, before resolver-exempt dispatch:

```python
    if targeting.get_panel_target_config_error() is not None and policy.requires_rhino:
        return _format_tool_result({"success": False, "data": targeting.get_panel_target_config_error()})

    if targeting.get_panel_target_lock() is not None and name in {"spawn_agent", "plan_and_execute"}:
        return _format_tool_result(
            targeting.panel_target_locked_result(
                message="Background agents are disabled in the embedded panel-locked Claude Code tab."
            )
        )

    if name == "rhino_launch" and (
        targeting.get_panel_target_lock() is not None
        or targeting.get_panel_target_config_error() is not None
    ):
        lock_route = targeting.resolve_tool_route("rhino_ping")
        if not lock_route.success:
            return _format_tool_result(targeting.route_error_result(lock_route))
```

Expose `panel_target_locked_result()` in `targeting.py`:

```python
def panel_target_locked_result(message: str | None = None) -> dict[str, Any]:
    return _panel_error(
        "panel_target_locked",
        message or "This Claude Code tab is locked to the Rhino document that owns the panel.",
        instances=discover_instances(),
    )
```

After route resolution succeeds and before dispatch, apply document context:

```python
    dispatch_arguments = dict(arguments)
    doc_applied = targeting.apply_locked_document_context(dispatch_arguments)
    if isinstance(doc_applied, dict) and doc_applied.get("success") is False:
        return _format_tool_result(doc_applied)
    dispatch_arguments = doc_applied
```

Update `rhino_request_context` wrapper:

```python
    with rhino_request_context(
        port=route.target.port,
        process_id=route.target.process_id,
        document_serial_number=route.document_serial_number,
    ):
        raw_result = await _call_tool_dispatch(name, dispatch_arguments)
```

Leave live-lock `rhino_launch` to `_call_tool_dispatch()` after the preflight block above. The preflight block must sit before the existing `if not policy.requires_rhino:` branch, because `rhino_launch` is resolver-exempt metadata in the policy registry.

```python
    if not policy.requires_rhino:
        raw_result = await _call_tool_dispatch(name, arguments)
        return _format_tool_result(raw_result)
```

Update `targeting.should_auto_bind_launched_instance()` so the launch handler cannot auto-bind under any panel lock state:

```python
def should_auto_bind_launched_instance() -> bool:
    if _PANEL_TARGET_LOCK is not None or _PANEL_TARGET_CONFIG_ERROR is not None:
        return False
    active = resolve_active_target()
    return active.target is None
```

- [ ] **Step 6: Run dispatcher tests**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py::test_panel_document_allows_missing_or_matching_serial `
  mcp_server/tests/test_multi_instance_targeting.py::test_panel_document_rejects_conflicting_positive_serial `
  mcp_server/tests/test_bridge.py::test_call_tool_installs_locked_document_context `
  mcp_server/tests/test_bridge.py::test_call_tool_rejects_conflicting_document_serial `
  mcp_server/tests/test_bridge.py::test_panel_lock_blocks_spawn_agent_before_background_task `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_stale_owner_returns_stale `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_live_owner_does_not_auto_bind -q
```

Expected: all targeted tests pass.

- [ ] **Step 7: Commit**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/targeting.py mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py
git commit -m "feat: enforce panel document lock in MCP dispatcher"
```

---

## Task 4: Direct Bridge Enforcement

**Files:**
- Modify: `mcp_server/src/rook/bridge.py`
- Test: `mcp_server/tests/test_bridge.py`

- [ ] **Step 1: Write failing direct bridge tests**

Add to `mcp_server/tests/test_bridge.py`:

```python
@pytest.mark.asyncio
async def test_call_rhino_defaults_to_panel_locked_process(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native",
    })
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return None
        async def request(self, method, url, json=None):
            captured["method"] = method
            captured["url"] = str(url)
            captured["json"] = json
            class Response:
                def raise_for_status(self): return None
                def json(self): return {"success": True, "data": {"ok": True}}
            return Response()

    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda timeout=None: FakeClient())

    result = await bridge.call_rhino("/document", "GET", {})

    assert result["success"] is True
    assert ":9951" in captured["url"]
    assert captured["json"]["documentSerialNumber"] == 42


@pytest.mark.asyncio
async def test_call_rhino_rejects_conflicting_panel_port(discovery_dir: Path):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native",
    })

    result = await bridge.call_rhino("/document", "GET", {}, port=9950)

    assert result["success"] is False
    assert result["data"]["error"] == "panel_target_locked"


@pytest.mark.asyncio
async def test_call_rhino_rejects_conflicting_panel_document(discovery_dir: Path):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7102",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7102-native.json", {
        "host": "127.0.0.1", "port": 9951, "processId": 7102, "pluginType": "native",
    })

    result = await bridge.call_rhino("/document", "GET", {"documentSerialNumber": 99})

    assert result["success"] is False
    assert result["data"]["error"] == "panel_document_locked"
```

Add RoadCreator same-process routing:

```python
@pytest.mark.asyncio
async def test_call_rhino_panel_lock_routes_rc_to_same_process_peer(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7101-roadcreator.json", {
        "host": "127.0.0.1", "port": 9960, "processId": 7101, "pluginType": "roadcreator",
    })
    _write_instance(discovery_dir / "instance-7102-roadcreator.json", {
        "host": "127.0.0.1", "port": 9961, "processId": 7102, "pluginType": "roadcreator",
    })
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return None
        async def request(self, method, url, json=None):
            captured["url"] = str(url)
            class Response:
                def raise_for_status(self): return None
                def json(self): return {"success": True, "data": {"roads": []}}
            return Response()

    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda timeout=None: FakeClient())
    result = await bridge.call_rhino("/rc/roads")

    assert result["success"] is True
    assert ":9960" in captured["url"]


@pytest.mark.asyncio
async def test_call_rhino_panel_lock_canonicalizes_same_process_extension_port_for_native_endpoint(discovery_dir: Path, monkeypatch):
    from rook import targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "7101",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
    })
    _write_instance(discovery_dir / "instance-7101-native.json", {
        "host": "127.0.0.1", "port": 9950, "processId": 7101, "pluginType": "native",
    })
    _write_instance(discovery_dir / "instance-7101-roadcreator.json", {
        "host": "127.0.0.1", "port": 9960, "processId": 7101, "pluginType": "roadcreator",
    })
    captured = {}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return None
        async def request(self, method, url, json=None):
            captured["url"] = str(url)
            class Response:
                def raise_for_status(self): return None
                def json(self): return {"success": True, "data": {"name": "A.3dm"}}
            return Response()

    monkeypatch.setattr(bridge.httpx, "AsyncClient", lambda timeout=None: FakeClient())
    result = await bridge.call_rhino("/document", port=9960)

    assert result["success"] is True
    assert ":9950" in captured["url"]
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
pytest mcp_server/tests/test_bridge.py::test_call_rhino_defaults_to_panel_locked_process `
  mcp_server/tests/test_bridge.py::test_call_rhino_rejects_conflicting_panel_port `
  mcp_server/tests/test_bridge.py::test_call_rhino_rejects_conflicting_panel_document `
  mcp_server/tests/test_bridge.py::test_call_rhino_panel_lock_routes_rc_to_same_process_peer `
  mcp_server/tests/test_bridge.py::test_call_rhino_panel_lock_canonicalizes_same_process_extension_port_for_native_endpoint -q
```

Expected: FAIL because `bridge.py` does not consult panel lock state.

- [ ] **Step 3: Implement lazy lock helpers in `bridge.py`**

Add near `_apply_document_context()`:

```python
def _targeting_module():
    from . import targeting
    return targeting


def _panel_lock_state():
    targeting = _targeting_module()
    return targeting.get_panel_target_lock(), targeting.get_panel_target_config_error()


def _panel_locked_error(error: dict[str, Any] | None) -> dict[str, Any] | None:
    if error is None:
        return None
    return {"success": False, "data": error}


def _apply_panel_lock_to_request(
    endpoint: str,
    data: dict | None,
    port: int | None,
    process_id: int | None,
) -> tuple[dict | None, int | None, int | None, dict[str, Any] | None]:
    targeting = _targeting_module()
    lock, config_error = _panel_lock_state()
    if config_error is not None:
        return data, port, process_id, {"success": False, "data": config_error}
    if lock is None:
        return data, port, process_id, None

    instances = discover_instances()
    locked_instances = [
        instance for instance in instances
        if instance.get("processId") == lock.process_id
    ]
    if not locked_instances:
        return data, port, process_id, targeting.route_error_result(
            targeting.ToolRoute(
                success=False,
                error="panel_target_stale",
                instances=instances,
            )
        )

    if process_id is not None and process_id > 0 and process_id != lock.process_id:
        return data, port, process_id, targeting.panel_target_locked_result()

    if port is not None and port > 0:
        explicit = next((instance for instance in instances if instance.get("port") == port), None)
        if explicit is None or explicit.get("processId") != lock.process_id:
            return data, port, process_id, targeting.panel_target_locked_result()
        # The port is a valid same-process anchor, but preserving it can pin
        # native/GH endpoints to an extension peer. Clear it and route by
        # locked process id plus endpoint so select_rhino_instance chooses the
        # correct same-process capable peer.
        port = None

    applied = targeting.apply_locked_document_context(data)
    if isinstance(applied, dict) and applied.get("success") is False:
        return data, port, process_id, applied

    return applied, port, lock.process_id, None
```

At the start of `call_rhino()` after normalizing non-positive `resolved_port` / `resolved_process_id`, call:

```python
    data, resolved_port, resolved_process_id, panel_error = _apply_panel_lock_to_request(
        endpoint,
        data,
        resolved_port,
        resolved_process_id,
    )
    if panel_error is not None:
        return panel_error
```

Keep the existing `_apply_document_context(data)` call after this. It will preserve the locked `documentSerialNumber` that was just injected.

- [ ] **Step 4: Run direct bridge tests**

Run:

```powershell
pytest mcp_server/tests/test_bridge.py::test_call_rhino_defaults_to_panel_locked_process `
  mcp_server/tests/test_bridge.py::test_call_rhino_rejects_conflicting_panel_port `
  mcp_server/tests/test_bridge.py::test_call_rhino_rejects_conflicting_panel_document `
  mcp_server/tests/test_bridge.py::test_call_rhino_panel_lock_routes_rc_to_same_process_peer `
  mcp_server/tests/test_bridge.py::test_call_rhino_panel_lock_canonicalizes_same_process_extension_port_for_native_endpoint -q
```

Expected: all targeted tests pass.

- [ ] **Step 5: Commit**

```powershell
git add mcp_server/src/rook/bridge.py mcp_server/tests/test_bridge.py
git commit -m "feat: enforce panel lock in direct bridge calls"
```

---

## Task 5: C# Strict Rook-Only MCP Config Builder

**Files:**
- Create: `src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs`
- Test: `src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs`

- [ ] **Step 1: Write failing C# tests**

Create `src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json;
using Rook.UI.Chat;
using Xunit;

namespace Rook.Tests.UI.Chat
{
    public class ClaudePanelMcpConfigBuilderTests
    {
        [Fact]
        public void BuildStrictRookConfig_CopiesOnlyRookAndAddsPanelLockEnv()
        {
            var sourceJson = """
            {
              "mcpServers": {
                "rook": {
                  "type": "stdio",
                  "command": "C:/Python/python.exe",
                  "args": ["-m", "rook"],
                  "cwd": "C:/Rook/mcp_server",
                  "env": {
                    "PYTHONPATH": "",
                    "PYTHONHOME": "",
                    "ROOK_INSTALL_ROOT": "C:/Rook",
                    "ROOK_DATA_DIR": "C:/Users/aryan/AppData/Roaming/Rook",
                    "ROOK_MODE": "dev",
                    "CHIRP_HOME": "C:/Chirp"
                  }
                },
                "filesystem": {
                  "command": "node"
                }
              }
            }
            """;

            var result = ClaudePanelMcpConfigBuilder.BuildStrictRookConfigJson(
                sourceJson,
                rhinoProcessId: 7101,
                documentSerialNumber: 42);

            using var doc = JsonDocument.Parse(result);
            var servers = doc.RootElement.GetProperty("mcpServers");
            Assert.True(servers.TryGetProperty("rook", out var rook));
            Assert.False(servers.TryGetProperty("filesystem", out _));
            Assert.Equal("C:/Python/python.exe", rook.GetProperty("command").GetString());
            Assert.Equal("C:/Rook/mcp_server", rook.GetProperty("cwd").GetString());
            var env = rook.GetProperty("env");
            Assert.Equal("panel_locked", env.GetProperty("ROOK_MCP_TARGET_MODE").GetString());
            Assert.Equal("7101", env.GetProperty("ROOK_MCP_TARGET_PROCESS_ID").GetString());
            Assert.Equal("42", env.GetProperty("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER").GetString());
            Assert.Equal("C:/Rook", env.GetProperty("ROOK_INSTALL_ROOT").GetString());
            Assert.Equal("C:/Chirp", env.GetProperty("CHIRP_HOME").GetString());
        }

        [Fact]
        public void BuildStrictRookConfig_MissingRookEntryThrowsActionableError()
        {
            var sourceJson = """{ "mcpServers": { "filesystem": { "command": "node" } } }""";

            var ex = Assert.Throws<InvalidOperationException>(() =>
                ClaudePanelMcpConfigBuilder.BuildStrictRookConfigJson(
                    sourceJson,
                    rhinoProcessId: 7101,
                    documentSerialNumber: 42));

            Assert.Contains("rook", ex.Message, StringComparison.OrdinalIgnoreCase);
            Assert.Contains("MCP", ex.Message, StringComparison.OrdinalIgnoreCase);
        }
    }
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~ClaudePanelMcpConfigBuilderTests
```

Expected: FAIL because `ClaudePanelMcpConfigBuilder` does not exist.

- [ ] **Step 3: Implement config builder**

Create `src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs`:

```csharp
using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.UI.Chat
{
    internal static class ClaudePanelMcpConfigBuilder
    {
        internal const string TargetModeEnv = "ROOK_MCP_TARGET_MODE";
        internal const string TargetProcessIdEnv = "ROOK_MCP_TARGET_PROCESS_ID";
        internal const string TargetDocumentSerialEnv = "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER";

        public static string BuildStrictRookConfigJson(
            string sourceConfigJson,
            int rhinoProcessId,
            uint documentSerialNumber)
        {
            var parsed = JsonNode.Parse(sourceConfigJson);
            if (parsed is null)
                throw new InvalidOperationException("Claude MCP config is not valid JSON.");
            var root = parsed.AsObject();
            var serversNode = root["mcpServers"];
            if (serversNode is null)
                throw new InvalidOperationException("Claude MCP config does not contain mcpServers.");
            var servers = serversNode.AsObject();
            var rookNode = servers["rook"];
            if (rookNode is null)
                throw new InvalidOperationException("Claude MCP config does not contain a rook MCP server entry.");
            var rook = rookNode.DeepClone().AsObject();

            var envNode = rook["env"];
            var env = envNode is null ? new JsonObject() : envNode.AsObject();
            rook["env"] = env;
            env[TargetModeEnv] = "panel_locked";
            env[TargetProcessIdEnv] = rhinoProcessId.ToString(System.Globalization.CultureInfo.InvariantCulture);
            env[TargetDocumentSerialEnv] = documentSerialNumber.ToString(System.Globalization.CultureInfo.InvariantCulture);

            var output = new JsonObject
            {
                ["mcpServers"] = new JsonObject
                {
                    ["rook"] = rook
                }
            };
            return output.ToJsonString(new JsonSerializerOptions { WriteIndented = true });
        }

        public static string WriteTempConfig(
            string sourceConfigPath,
            int rhinoProcessId,
            uint documentSerialNumber)
        {
            if (!File.Exists(sourceConfigPath))
                throw new FileNotFoundException("Claude MCP config file was not found.", sourceConfigPath);

            var sourceJson = File.ReadAllText(sourceConfigPath);
            var configJson = BuildStrictRookConfigJson(
                sourceJson,
                rhinoProcessId,
                documentSerialNumber);

            var dir = Path.Combine(Path.GetTempPath(), "rook", "claude-code-panel");
            Directory.CreateDirectory(dir);
            var path = Path.Combine(dir, $"rook-panel-{Guid.NewGuid():N}.json");
            File.WriteAllText(path, configJson);
            return path;
        }
    }
}
```

- [ ] **Step 4: Run C# builder tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~ClaudePanelMcpConfigBuilderTests
```

Expected: all builder tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs
git commit -m "feat: generate panel-locked Claude MCP config"
```

---

## Task 6: Wire ClaudeCodeWrapper To Strict Panel Config

**Files:**
- Modify: `src/Rook/UI/Chat/ClaudeCodeWrapper.cs`
- Modify: `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`

- [ ] **Step 1: Write failing source-level wrapper tests**

Add to `src/Rook.Tests/UI/Chat/RookChatPanelTests.cs`:

```csharp
[Fact]
public void ClaudeCodeWrapper_UsesStrictPanelMcpConfig()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

    Assert.Contains("ClaudePanelMcpConfigBuilder.WriteTempConfig", source);
    Assert.Contains("--strict-mcp-config", source);
    Assert.DoesNotContain("--mcp-config \\\"{userMcpConfig}\\\"", source);
}

[Fact]
public void ClaudeCodeWrapper_PromptExplainsPanelLockedRookOnlyMode()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

    Assert.Contains("inside the Rook Rhino panel", source);
    Assert.Contains("panel-locked Rook MCP server", source);
}

[Fact]
public void ClaudeCodeWrapper_DisposeCleansTemporaryPanelConfigBestEffort()
{
    var source = ReadSourceFile("src", "Rook", "UI", "Chat", "ClaudeCodeWrapper.cs");

    Assert.Contains("_panelMcpConfigPath", source);
    Assert.Contains("DeletePanelMcpConfig", source);
    Assert.Contains("File.Delete", source);
}
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~RookChatPanelTests
```

Expected: FAIL because wrapper still uses the global user MCP config directly.

- [ ] **Step 3: Modify wrapper fields and cleanup**

In `ClaudeCodeWrapper.cs`, add field:

```csharp
private string? _panelMcpConfigPath;
```

Add method near process management:

```csharp
private void DeletePanelMcpConfig()
{
    var path = _panelMcpConfigPath;
    _panelMcpConfigPath = null;
    if (string.IsNullOrWhiteSpace(path))
        return;

    try
    {
        if (File.Exists(path))
            File.Delete(path);
    }
    catch (Exception ex)
    {
        RhinoApp.WriteLine($"[ClaudeCodeWrapper] Failed to delete panel MCP config: {ex.Message}");
    }
}
```

Call `DeletePanelMcpConfig();` in `KillProcess()` after process disposal and in `Dispose()` after `KillProcess()`.

- [ ] **Step 4: Modify launch argument generation**

Replace the current global `--mcp-config` block in `BuildLaunchArguments()` with:

```csharp
var userMcpConfig = Path.Combine(
    Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
    ".claude.json");
try
{
    DeletePanelMcpConfig();
    _panelMcpConfigPath = ClaudePanelMcpConfigBuilder.WriteTempConfig(
        userMcpConfig,
        Process.GetCurrentProcess().Id,
        _documentSerialNumber);
    sb.Append($"--mcp-config \"{_panelMcpConfigPath}\" ");
    sb.Append("--strict-mcp-config ");
}
catch (Exception ex)
{
    throw new InvalidOperationException(
        "Unable to create panel-locked Rook MCP config for Claude Code. Run Rook doctor to configure the rook MCP server for Claude Code.",
        ex);
}
```

Replace prompt construction with:

```csharp
var prompt = "You are a Rhino 3D assistant running inside the Rook Rhino panel. "
    + "You only have access to the panel-locked Rook MCP server. "
    + "Use knowledge_query before operations to learn patterns. "
    + "Use knowledge_record after operations to record outcomes.";

var docContext = _documentSerialNumber != 0
    ? $" The panel lock enforces documentSerialNumber {_documentSerialNumber}; do not target another Rhino document."
    : "";
sb.Append($"--append-system-prompt \"{EscapeForCommandLine(prompt + docContext)}\" ");
```

In `StartPersistentProcess()`, catch `InvalidOperationException` from `BuildLaunchArguments()`:

```csharp
string args;
try
{
    args = BuildLaunchArguments();
}
catch (InvalidOperationException ex)
{
    OnError?.Invoke(ex.Message);
    RhinoApp.WriteLine($"[ClaudeCodeWrapper] {ex}");
    return;
}
```

- [ ] **Step 5: Run C# wrapper tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter FullyQualifiedName~RookChatPanelTests
```

Expected: all `RookChatPanelTests` pass.

- [ ] **Step 6: Commit**

```powershell
git add src/Rook/UI/Chat/ClaudeCodeWrapper.cs src/Rook.Tests/UI/Chat/RookChatPanelTests.cs
git commit -m "feat: launch embedded Claude with panel-locked MCP"
```

---

## Task 7: Full Verification

**Files:**
- No new files. Verify all changed surfaces.

- [ ] **Step 1: Run Python targeting and bridge suites**

Run:

```powershell
pytest mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_bridge.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run Python compile check**

Run:

```powershell
python -m py_compile mcp_server\src\rook\targeting.py mcp_server\src\rook\bridge.py mcp_server\src\rook\server.py
```

Expected: exit code 0.

- [ ] **Step 3: Run C# chat tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.UI.Chat"
```

Expected: all chat tests pass.

- [ ] **Step 4: Run focused existing MCP UI-adjacent tests**

Run:

```powershell
pytest mcp_server/tests/test_vision_mcp_tools.py mcp_server/tests/test_video_mcp_tools.py -q
```

Expected: all tests pass. These guard that dispatcher formatting and MCP response behavior still work for non-targeting tool groups changed in the same branch.

- [ ] **Step 5: Inspect working tree**

Run:

```powershell
git status --short
```

Expected: only intended implementation files are modified. Do not revert unrelated pre-existing changes in the worktree.

- [ ] **Step 6: Commit final verification adjustments if any**

If verification required small fixes, commit them:

```powershell
git add mcp_server/src/rook/targeting.py mcp_server/src/rook/bridge.py mcp_server/src/rook/server.py mcp_server/tests/test_multi_instance_targeting.py mcp_server/tests/test_bridge.py src/Rook/UI/Chat/ClaudePanelMcpConfigBuilder.cs src/Rook/UI/Chat/ClaudeCodeWrapper.cs src/Rook.Tests/UI/Chat/ClaudePanelMcpConfigBuilderTests.cs src/Rook.Tests/UI/Chat/RookChatPanelTests.cs
git commit -m "test: verify panel-locked Claude routing"
```

If no fixes were needed after previous commits, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - strict Rook-only per-tab config: Task 5 and Task 6.
  - env lock initialization: Task 1.
  - fail-closed invalid env and unknown mode: Task 1.
  - resolver before active binding/read auto-pick: Task 2.
  - same-process canonicalization and stale priority: Task 2 and Task 4.
  - document serial context and conflict rejection: Task 3 and Task 4.
  - meta tool behavior: Task 2 and Task 3.
  - `spawn_agent` / `plan_and_execute` Phase 1 disablement: Task 3.
  - direct bridge bypass enforcement: Task 4.
  - `rhino_launch` not an escape hatch: Task 3.
  - C# prompt honesty and cleanup: Task 6.
- Placeholder scan:
  - No unfinished-marker or unspecified "write tests" steps remain.
- Type consistency:
  - Python lock state uses `PanelTargetLock`, `panel_locked`, `panel_target_locked`, `panel_target_stale`, `panel_target_config_error`, and `panel_document_locked`.
  - C# helper is `ClaudePanelMcpConfigBuilder` in namespace `Rook.UI.Chat`.
