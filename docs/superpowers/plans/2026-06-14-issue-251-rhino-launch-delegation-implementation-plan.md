# Issue #251 Rhino Launch Delegation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace legacy `rhino_launch` detached-process launch behavior with a compatibility wrapper over `rhino_workbench_launch`.

**Architecture:** Keep `rhino_launch` public, but make it a thin server-dispatch wrapper: config errors fail fast, reachable Rhino returns `already_running`, panel-locked launch attempts are rejected, and external launch attempts delegate to `workbench.launch_owned_workbench()`. All `rhino_launch` outcomes carry `canonicalTool: "rhino_workbench_launch"` and inherit the merged #222 launch-environment hardening through the owned launcher.

**Tech Stack:** Python MCP server, pytest, `unittest.mock.AsyncMock`, existing Rook targeting/workbench helpers.

---

## Current Foundation

- Branch: `codex/rhino-launch-workbench-spec`, rebased on merged #222 (`main` contains `dfbdac61`).
- Gate status: `clear`, recorded in `docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate-rerun.md`.
- Current branch diff before implementation: only five #251 design/plan/audit docs.
- Do not touch backup refs (`backup/rhino-launch-before-spatial-excise`, `backup/rhino-launch-workbench-spec-before-253-rebase`) or `preserve/gate4-adjacency-23c802a`.

## Files

- Modify: `mcp_server/src/rook/server.py`
  - Update `rhino_launch` tool description/schema.
  - Add a small canonical metadata helper.
  - Change pre-dispatch config-error handling to attach canonical metadata for `rhino_launch`.
  - Remove the panel-lock `resolve_tool_route("rhino_ping")` special case for `rhino_launch`.
  - Replace the legacy `rhino_launch` hardcoded `Popen` implementation with fork-(b) dispatch: reachability -> scope gate -> owned launcher delegation.
- Modify: `mcp_server/tests/test_workbench.py`
  - Add wrapper/delegation tests for external launch, timeout mapping/default/invalid, structured failure envelope, schema wording, and hardcoded-exe source guard.
- Modify: `mcp_server/tests/test_bridge.py`
  - Update panel-lock `rhino_launch` tests to assert fork-(b) behavior.
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`
  - Extend no-rebind stale-active test to assert canonical metadata.
- Create after implementation/live smoke: `docs/superpowers/audits/2026-06-14-issue-251-rhino-launch-delegation-smoke.md`
  - Record MCP-driven `rhino_launch` success and forced-failure smoke evidence.

## Task 1: Add Failing Wrapper Tests

**Files:**
- Modify: `mcp_server/tests/test_workbench.py`
- Modify: `mcp_server/tests/test_bridge.py`
- Modify: `mcp_server/tests/test_multi_instance_targeting.py`

- [ ] **Step 1: Branch and status check**

Run:

```powershell
git branch --show-current
git status --short
```

Expected:

```text
codex/rhino-launch-workbench-spec
```

`git status --short` should be empty before edits.

- [ ] **Step 2: Add `rhino_launch` delegation tests to `test_workbench.py`**

Append these tests near the existing `test_call_tool_dispatches_launch` workbench-dispatch tests:

```python
@pytest.mark.asyncio
async def test_rhino_launch_delegates_to_workbench_with_default_timeout(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()

    async def unreachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("not reachable")

    monkeypatch.setattr(server, "call_rhino", unreachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {
            "session": "rhino-5",
            "processId": 5,
            "port": 64000,
            "owned": True,
            "mode": "workbench",
            "boundInSeconds": 1.0,
        }}
        result = await server.call_tool("rhino_launch", {})

    text = result[0].text
    assert '"session": "rhino-5"' in text
    assert '"canonicalTool": "rhino_workbench_launch"' in text
    mock.assert_awaited_once_with(readiness_timeout_seconds=90)
```

```python
@pytest.mark.asyncio
async def test_rhino_launch_maps_timeout_to_readiness_timeout(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()

    async def unreachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("not reachable")

    monkeypatch.setattr(server, "call_rhino", unreachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {
            "session": "rhino-7",
            "processId": 7,
            "port": 64001,
            "owned": True,
            "mode": "workbench",
            "boundInSeconds": 1.0,
        }}
        result = await server.call_tool("rhino_launch", {"timeout": 120})

    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    mock.assert_awaited_once_with(readiness_timeout_seconds=120)
```

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [None, "abc", 0, -5, True, False])
async def test_rhino_launch_invalid_timeout_uses_owned_launcher_validation(monkeypatch, bad):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()

    async def unreachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("not reachable")

    monkeypatch.setattr(server, "call_rhino", unreachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {
            "success": False,
            "data": {
                "code": "invalid_readiness_timeout",
                "message": f"readinessTimeoutSeconds must be a positive number, got {bad!r}",
                "retryable": False,
            },
        }
        result = await server.call_tool("rhino_launch", {"timeout": bad})

    text = result[0].text
    assert '"code": "invalid_readiness_timeout"' in text
    assert '"canonicalTool": "rhino_workbench_launch"' in text
    mock.assert_awaited_once_with(readiness_timeout_seconds=bad)
```

```python
@pytest.mark.asyncio
async def test_rhino_launch_external_reachable_returns_already_running_without_launch_or_rebind(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    called = {"bind": False}

    async def reachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        return {"success": True, "data": {"status": "ok"}}

    monkeypatch.setattr(server, "call_rhino", reachable_ping)
    monkeypatch.setattr(
        targeting,
        "bind_single_available_instance",
        lambda: called.__setitem__("bind", True),
    )
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {})

    text = result[0].text
    assert '"status": "already_running"' in text
    assert '"canonicalTool": "rhino_workbench_launch"' in text
    assert '"auto_bound": true' not in text
    assert called["bind"] is False
    mock.assert_not_awaited()
```

```python
@pytest.mark.asyncio
async def test_rhino_launch_config_error_precedes_reachability(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()
    targeting.initialize_from_environment({"ROOK_MCP_TARGET_MODE": "bogus_mode"})

    async def reachable_ping(endpoint, *args, **kwargs):
        raise AssertionError("reachability must not be checked after config error")

    monkeypatch.setattr(server, "call_rhino", reachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        try:
            result = await server.call_tool("rhino_launch", {})
        finally:
            targeting.reset_targeting_state_for_tests()

    text = result[0].text
    assert "panel_target_config_error" in text
    assert '"canonicalTool": "rhino_workbench_launch"' in text
    mock.assert_not_awaited()
```

```python
@pytest.mark.asyncio
async def test_rhino_launch_structured_failure_envelope_replaces_legacy_string(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()

    async def unreachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("not reachable")

    monkeypatch.setattr(server, "call_rhino", unreachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {
            "success": False,
            "data": {
                "code": "workbench_readiness_timeout",
                "message": "Rhino did not publish discovery before readiness timeout",
                "reason": "timeout",
                "retryable": True,
                "evidence": {
                    "discoveryLogSeen": False,
                    "elapsedSeconds": 90.0,
                },
            },
        }
        result = await server.call_tool("rhino_launch", {})

    text = result[0].text
    assert '"code": "workbench_readiness_timeout"' in text
    assert '"reason": "timeout"' in text
    assert '"discoveryLogSeen": false' in text
    assert '"canonicalTool": "rhino_workbench_launch"' in text
    assert "Rhino failed to start within" not in text
```

```python
@pytest.mark.asyncio
async def test_rhino_launch_launch_success_may_auto_bind(monkeypatch):
    from rook import server, targeting

    targeting.reset_targeting_state_for_tests()

    async def unreachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("not reachable")

    monkeypatch.setattr(server, "call_rhino", unreachable_ping)
    monkeypatch.setattr(targeting, "should_auto_bind_launched_instance", lambda: True)
    monkeypatch.setattr(
        targeting,
        "bind_single_available_instance",
        lambda: targeting.InstanceRef(64002, 42),
    )
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {
            "session": "rhino-42",
            "processId": 42,
            "port": 64002,
            "owned": True,
            "mode": "workbench",
            "boundInSeconds": 1.0,
        }}
        result = await server.call_tool("rhino_launch", {})

    text = result[0].text
    assert '"auto_bound": true' in text
    assert '"processId": 42' in text
    assert '"port": 64002' in text
    assert '"canonicalTool": "rhino_workbench_launch"' in text
```

```python
@pytest.mark.asyncio
async def test_rhino_launch_tool_schema_documents_workbench_alias():
    from rook.server import list_tools

    tools = await list_tools()
    launch_tool = next(tool for tool in tools if tool.name == "rhino_launch")

    assert "compatibility" in launch_tool.description.lower()
    assert "rhino_workbench_launch" in launch_tool.description
    assert "default: 90" in launch_tool.inputSchema["properties"]["timeout"]["description"]
```

```python
def test_rhino_launch_case_does_not_hardcode_rhino_executable():
    from pathlib import Path

    source = Path("mcp_server/src/rook/server.py").read_text(encoding="utf-8")
    start = source.index('case "rhino_launch":')
    end = source.index('case "rhino_workbench_launch":', start)
    launch_case = source[start:end]

    assert "Program Files" not in launch_case
    assert "Rhino 8/System/Rhino.exe" not in launch_case
    assert "subprocess" not in launch_case
    assert "Popen" not in launch_case
```

- [ ] **Step 3: Replace panel-lock tests in `test_bridge.py`**

Replace `test_panel_lock_launch_stale_owner_returns_stale` with:

```python
@pytest.mark.asyncio
async def test_panel_lock_launch_unreachable_requires_external_scope(monkeypatch):
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

    async def failed_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        raise RuntimeError("panel target unreachable")

    monkeypatch.setattr(server, "call_rhino", failed_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {})

    assert "workbench_requires_external_scope" in result[0].text
    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    mock.assert_not_awaited()
```

Change `test_panel_lock_launch_live_owner_does_not_auto_bind` so it uses a reachable ping and expects `already_running`:

```python
@pytest.mark.asyncio
async def test_panel_lock_launch_live_owner_returns_already_running_without_auto_bind(monkeypatch):
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

    async def reachable_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        return {"success": True, "data": {"status": "ok"}}

    monkeypatch.setattr(server, "call_rhino", reachable_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {})

    assert '"status": "already_running"' in result[0].text
    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    assert '"auto_bound": true' not in result[0].text
    assert called["bind"] is False
    mock.assert_not_awaited()
```

Change `test_panel_lock_launch_ping_failure_does_not_spawn_rhino` to assert no owned-launch delegation:

```python
@pytest.mark.asyncio
async def test_panel_lock_launch_ping_failure_does_not_launch_workbench(monkeypatch):
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

    async def failed_ping(endpoint, *args, **kwargs):
        assert endpoint == "/ping"
        return {"success": False, "data": "ping failed"}

    monkeypatch.setattr(server, "call_rhino", failed_ping)
    with patch.object(server.workbench, "launch_owned_workbench",
                      new_callable=AsyncMock) as mock:
        result = await server.call_tool("rhino_launch", {"timeout": 0})

    assert "workbench_requires_external_scope" in result[0].text
    assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
    mock.assert_not_awaited()
```

Also add the missing imports at the top of `test_bridge.py`:

```python
from unittest.mock import AsyncMock, patch
```

- [ ] **Step 4: Extend the stale-active no-rebind test**

In `mcp_server/tests/test_multi_instance_targeting.py`, update `test_launch_already_running_leaves_stale_active_binding_unchanged` by adding the canonical assertion:

```python
        assert '"canonicalTool": "rhino_workbench_launch"' in result[0].text
```

Keep these existing assertions:

```python
        assert '"already_running"' in result[0].text
        assert '"auto_bound": true' not in result[0].text
        assert targeting.get_active_target() == targeting.InstanceRef(9950, 7101)
```

- [ ] **Step 5: Run focused tests and verify the intended failures**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_workbench.py `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_unreachable_requires_external_scope `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_live_owner_returns_already_running_without_auto_bind `
  mcp_server/tests/test_bridge.py::test_panel_lock_launch_ping_failure_does_not_launch_workbench `
  mcp_server/tests/test_multi_instance_targeting.py::test_launch_already_running_leaves_stale_active_binding_unchanged
```

Expected: failures that show the current `rhino_launch` still uses legacy behavior:

- default timeout is `120`, not `90`;
- panel-unreachable returns `panel_target_stale`, not `workbench_requires_external_scope`;
- no `canonicalTool` appears;
- source guard finds the hardcoded executable / `Popen`.

Do not implement code until these tests fail for those reasons.

## Task 2: Implement the Server Wrapper

**Files:**
- Modify: `mcp_server/src/rook/server.py`

- [ ] **Step 1: Add canonical metadata helper**

Place this near `_format_tool_result`, before `call_tool`:

```python
_RHINO_LAUNCH_CANONICAL_TOOL = "rhino_workbench_launch"


def _with_rhino_launch_canonical_tool(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    data = out.get("data")
    if isinstance(data, dict):
        out["data"] = {**data, "canonicalTool": _RHINO_LAUNCH_CANONICAL_TOOL}
    else:
        out["data"] = {
            "value": data,
            "canonicalTool": _RHINO_LAUNCH_CANONICAL_TOOL,
        }
    return out
```

The non-dict fallback is defensive only. After this implementation, `rhino_launch` should not intentionally return bare strings.

- [ ] **Step 2: Update the `rhino_launch` tool description/schema**

Replace the existing `rhino_launch` `Tool(...)` entry with:

```python
        Tool(
            name="rhino_launch",
            description="""Compatibility launcher for Rhino availability. If Rhino is already reachable, returns already_running without changing the active binding. If Rhino is not reachable, delegates to rhino_workbench_launch and returns that owned workbench launch envelope.

Prefer rhino_workbench_launch for new automation that needs an owned disposable Rhino session. Safe to call multiple times.""",
            inputSchema={
                "type": "object",
                "properties": {
                    "timeout": {
                        "type": "integer",
                        "description": "Max seconds to wait for owned workbench readiness (default: 90). Maps to readinessTimeoutSeconds."
                    }
                },
                "required": []
            }
        ),
```

- [ ] **Step 3: Attach canonical metadata to config-error preflight**

Replace the existing config-error preflight block:

```python
    if targeting.get_panel_target_config_error() is not None and (
        policy.requires_rhino or name == "rhino_launch"
    ):
        return _format_tool_result(
            {"success": False, "data": targeting.get_panel_target_config_error()}
        )
```

with:

```python
    if targeting.get_panel_target_config_error() is not None and (
        policy.requires_rhino or name == "rhino_launch"
    ):
        raw_result = {"success": False, "data": targeting.get_panel_target_config_error()}
        if name == "rhino_launch":
            raw_result = _with_rhino_launch_canonical_tool(raw_result)
        return _format_tool_result(raw_result)
```

- [ ] **Step 4: Remove the pre-dispatch panel-lock route check for `rhino_launch`**

Delete this block from `call_tool`:

```python
    if name == "rhino_launch" and targeting.get_panel_target_lock() is not None:
        lock_route = targeting.resolve_tool_route("rhino_ping")
        if not lock_route.success:
            return _format_tool_result(targeting.route_error_result(lock_route))
```

Fork-(b) requires reachability to be checked inside the wrapper before the launch-ownership scope gate.

- [ ] **Step 5: Replace the legacy `rhino_launch` dispatch case**

Replace the whole `case "rhino_launch":` body in `_call_tool_dispatch` through the old timeout failure branch with:

```python
        case "rhino_launch":
            timeout = arguments.get("timeout", 90)

            try:
                ping_result = await call_rhino("/ping")
                if ping_result.get("success"):
                    result = _with_rhino_launch_canonical_tool({
                        "success": True,
                        "data": {
                            "status": "already_running",
                            "message": "Rhino is already running",
                        },
                    })
                else:
                    raise RuntimeError("ping failed")
            except Exception:
                if targeting.get_panel_target_lock() is not None:
                    result = _with_rhino_launch_canonical_tool({
                        "success": False,
                        "data": {
                            "code": "workbench_requires_external_scope",
                            "message": (
                                "rhino_launch can only launch an owned workbench "
                                "from an external MCP client when Rhino is not reachable."
                            ),
                            "retryable": False,
                        },
                    })
                else:
                    result = await workbench.launch_owned_workbench(
                        readiness_timeout_seconds=timeout,
                    )
                    if result.get("success") and isinstance(result.get("data"), dict):
                        data = result["data"]
                        if targeting.should_auto_bind_launched_instance():
                            target = targeting.bind_single_available_instance()
                            if target is not None:
                                data = {
                                    **data,
                                    "auto_bound": True,
                                    "active": {
                                        "port": target.port,
                                        "processId": target.process_id,
                                    },
                                }
                                result = {**result, "data": data}
                    result = _with_rhino_launch_canonical_tool(result)
```

Do not import `subprocess` or `os` in this branch. Do not check a hardcoded Rhino executable path. The owned launcher now owns executable resolution and launch environment construction.

- [ ] **Step 6: Run the failing tests again**

Run the same command from Task 1 Step 5.

Expected: all selected tests pass.

- [ ] **Step 7: Commit checkpoint if reviewer wants task-level commits**

If committing at this checkpoint, run:

```powershell
git branch --show-current
git status --short
git diff --check
git add mcp_server/src/rook/server.py mcp_server/tests/test_workbench.py mcp_server/tests/test_bridge.py mcp_server/tests/test_multi_instance_targeting.py
git commit -m "Delegate rhino_launch to owned workbench launcher"
```

If the reviewer wants implementation review before commits, do not commit; present the diff and test result.

## Task 3: Run Full Relevant Unit Coverage

**Files:**
- Read/verify only unless failures require code fixes:
  - `mcp_server/src/rook/server.py`
  - `mcp_server/tests/test_workbench.py`
  - `mcp_server/tests/test_bridge.py`
  - `mcp_server/tests/test_multi_instance_targeting.py`

- [ ] **Step 1: Run focused dispatch and targeting tests**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_workbench.py `
  mcp_server/tests/test_bridge.py `
  mcp_server/tests/test_multi_instance_targeting.py
```

Expected: all pass.

- [ ] **Step 2: Run #222-owned-launch regression suite**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_rhino_launch.py `
  mcp_server/tests/test_workbench.py `
  mcp_server/tests/test_runtime_harness.py
```

Expected: all pass. This confirms the delegation did not break the merged launch-env hardening seam.

- [ ] **Step 3: Run whitespace/source checks**

Run:

```powershell
git diff --check
rg -n "Rhino failed to start within|C:/Program Files/Rhino 8/System/Rhino.exe|Rhino 8/System/Rhino.exe|subprocess as _sp|import os as _os" mcp_server/src/rook/server.py
```

Expected:

- `git diff --check` exits 0.
- `rg` exits non-zero or returns no matches for the removed legacy strings/imports.

## Task 4: Bound-Runtime Deploy and MCP Live Smoke

**Files:**
- Create: `docs/superpowers/audits/2026-06-14-issue-251-rhino-launch-delegation-smoke.md`

- [ ] **Step 1: Sync or deploy the changed Python server to the runtime Codex binds**

Use the project’s local deploy path or the lighter AppData source sync pattern already used in #222.

Preferred command when safe:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -PayloadOnly -AllowRunning
```

If that path fails in the post-install config step, sync only the changed Python source to the installed AppData venv:

```powershell
Copy-Item mcp_server\src\rook\server.py `
  "$env:LOCALAPPDATA\Rook\venv\Lib\site-packages\rook\server.py" `
  -Force
```

Then restart the MCP server / fresh Codex connector so the changed module loads. A smoke result without `canonicalTool` is stale installed code and is not evidence.

- [ ] **Step 2: Success smoke through MCP `rhino_launch`**

From a fresh in-app Rook MCP binding, run:

```json
rhino_workbench_list {}
```

If it returns owned sessions, close them through `rhino_workbench_close`. If any non-owned `Rhino.exe` exists, stop and ask the user before closing it.

Then run:

```json
rhino_launch {"timeout":90}
```

Record:

- full returned payload;
- presence of `"canonicalTool": "rhino_workbench_launch"`;
- whether outcome is `already_running` or newly launched owned workbench;
- for newly launched workbench, `session`, `processId`, `port`, `evidence.launchEnv`, and `boundInSeconds`;
- follow-up MCP liveness with `rhino_workbench_list`.

If a new owned workbench was launched, close it through:

```json
rhino_workbench_close {"session":"<session>","graceful":false}
```

Record final empty list and PID-gone evidence.

- [ ] **Step 3: Forced-failure smoke through MCP `rhino_launch`**

Use a controlled failure that exercises real public serialization without depending on a broken machine. The lowest-risk option is invalid timeout:

```json
rhino_launch {"timeout":0}
```

Precondition: no reachable Rhino. If Rhino is reachable, this call returns `already_running` before timeout validation by design. Close any Rook-owned workbench first; if a non-owned Rhino remains, ask the user before proceeding.

Record:

- full returned payload;
- `"canonicalTool": "rhino_workbench_launch"`;
- structured `"code": "invalid_readiness_timeout"`;
- absence of the old bare string `"Rhino failed to start within"`;
- MCP still live afterward.

If invalid timeout cannot be exercised because a user-owned Rhino must stay open, record that limitation and run a mock-only forced-failure unit proof instead. Do not close non-owned Rhino without approval.

- [ ] **Step 4: Write the live smoke audit**

Create `docs/superpowers/audits/2026-06-14-issue-251-rhino-launch-delegation-smoke.md` with:

````markdown
# Issue #251 Rhino Launch Delegation Smoke

## Repository State

- Branch: `codex/rhino-launch-workbench-spec`
- Base: merged #222 on `main`
- Commit under test: `<short sha>`

## Runtime State

- Bound runtime path: `<installed AppData venv path or repo runtime path>`
- Stale-code guard: `canonicalTool` present in MCP response

## Success Smoke

- Pre-run `rhino_workbench_list`: `<payload>`
- Pre-run OS `Rhino.exe` snapshot: `<none or details>`
- `rhino_launch {"timeout":90}` result:

```json
<payload>
```

- Follow-up MCP liveness: `<payload>`
- Cleanup result: `<payload or not applicable>`
- Final process/list cleanup: `<payload>`

## Forced-Failure Smoke

- Preconditions: `<state>`
- `rhino_launch {"timeout":0}` result:

```json
<payload>
```

- Legacy bare string absent: `<yes/no>`
- MCP liveness after failure: `<payload>`

## Classification

- Outcome: `<passed/blocked>`
- Rationale: `<short evidence-backed explanation>`
````

- [ ] **Step 5: Commit live smoke artifact**

Run:

```powershell
git branch --show-current
git status --short
git diff --check
git add docs\superpowers\audits\2026-06-14-issue-251-rhino-launch-delegation-smoke.md
git commit -m "Record rhino_launch delegation smoke"
```

## Task 5: Final Review Package

**Files:**
- Read/verify:
  - `mcp_server/src/rook/server.py`
  - `mcp_server/tests/test_workbench.py`
  - `mcp_server/tests/test_bridge.py`
  - `mcp_server/tests/test_multi_instance_targeting.py`
  - `docs/superpowers/audits/2026-06-14-issue-251-rhino-launch-delegation-smoke.md`

- [ ] **Step 1: Final branch/scope check**

Run:

```powershell
git branch --show-current
git status --short
git diff --name-only main...HEAD
```

Expected branch:

```text
codex/rhino-launch-workbench-spec
```

Expected implementation files after this slice:

```text
docs/superpowers/audits/2026-06-14-issue-251-rhino-mcp-transport-probe.md
docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate-rerun.md
docs/superpowers/audits/2026-06-14-issue-251-rhino-workbench-launch-gate.md
docs/superpowers/audits/2026-06-14-issue-251-rhino-launch-delegation-smoke.md
docs/superpowers/plans/2026-06-14-issue-251-rhino-launch-gate-plan.md
docs/superpowers/plans/2026-06-14-issue-251-rhino-launch-delegation-implementation-plan.md
docs/superpowers/specs/2026-06-14-issue-251-rhino-launch-workbench-delegation-design.md
mcp_server/src/rook/server.py
mcp_server/tests/test_bridge.py
mcp_server/tests/test_multi_instance_targeting.py
mcp_server/tests/test_workbench.py
```

- [ ] **Step 2: Final verification commands**

Run:

```powershell
python -m pytest `
  mcp_server/tests/test_workbench.py `
  mcp_server/tests/test_bridge.py `
  mcp_server/tests/test_multi_instance_targeting.py

python -m pytest `
  mcp_server/tests/test_rhino_launch.py `
  mcp_server/tests/test_workbench.py `
  mcp_server/tests/test_runtime_harness.py

git diff --check
```

Expected:

- all pytest commands pass;
- `git diff --check` exits 0.

- [ ] **Step 3: Present reviewer packet**

Report:

- branch and HEAD;
- changed files;
- unit test results;
- live smoke result and audit path;
- explicit statement that #222 code is on `main` and not duplicated in this branch;
- explicit statement that the legacy hardcoded executable and bare timeout string were removed from the `rhino_launch` case;
- any smoke limitations, especially if forced failure could not be run because a non-owned Rhino had to stay open.

## Self-Review

- Spec coverage: every approved test bullet maps to Task 1 or Task 4. Fork-(b) ordering is pinned by config-precedence, reachable external/panel tests, panel launch rejection, and delegated external launch tests. Canonical metadata is asserted for config-error, already-running, scope rejection, launch success, invalid timeout, and structured failure. Timeout mapping/default and source guard are explicit.
- Placeholder scan: all steps name concrete files, commands, snippets, expected failures, and expected passes. The only conditional path is the live forced-failure smoke, with a concrete fallback and reporting requirement.
- Type consistency: the plan uses existing module names (`server.workbench.launch_owned_workbench`, `targeting.InstanceRef`, `server.call_tool`, `list_tools`) and existing result field names (`success`, `data`, `code`, `canonicalTool`, `auto_bound`, `active`).
