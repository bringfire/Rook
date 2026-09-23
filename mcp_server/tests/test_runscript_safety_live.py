"""Live RunScript safety smoke tests for an owned Rhino runtime."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from rook.bridge import NATIVE_CLIENT_HEADERS
import pytest


pytestmark = [
    pytest.mark.requires_rhino,
    pytest.mark.runscript_safety_live,
]


REQUEST_TIMEOUT = 20.0
RECOVERY_TIMEOUT = 6.0
RECOVERY_POLL_INTERVAL = 0.25


def _positive_env_int(name: str) -> int:
    raw = os.environ.get(name)
    if raw is None:
        pytest.fail(f"{name} must be set for owned Rhino runtime smoke tests")
    try:
        value = int(raw)
    except ValueError:
        pytest.fail(f"{name} must be a positive integer")
    if value <= 0:
        pytest.fail(f"{name} must be a positive integer")
    return value


def _owned_port() -> int:
    return _positive_env_int("ROOK_RHINO_PORT")


def _owned_pid() -> int:
    return _positive_env_int("ROOK_RHINO_PROCESS_ID")


def _artifact_dir() -> Path:
    raw = os.environ.get("ROOK_HARNESS_ARTIFACT_DIR")
    if raw is None:
        pytest.fail("ROOK_HARNESS_ARTIFACT_DIR must be set for sentinel writes")
    artifact_dir = Path(raw)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return artifact_dir


def _base_url() -> str:
    return f"http://127.0.0.1:{_owned_port()}"


def _assert_owned_runtime_binding() -> None:
    from rook.runtime_harness import DiscoveryError, OwnedRhinoDiscovery

    pid = _owned_pid()
    port = _owned_port()
    try:
        record = OwnedRhinoDiscovery().read_owned_record(pid)
    except DiscoveryError as exc:
        pytest.fail(f"Could not verify owned Rhino discovery record for pid {pid}: {exc}")
    if record.port != port:
        pytest.fail(
            "ROOK_RHINO_PORT and ROOK_RHINO_PROCESS_ID do not refer to the same "
            f"owned runtime: env port {port}, discovery port {record.port}, pid {pid}"
        )


def _assert_not_parallel(config: pytest.Config | None = None) -> None:
    if os.environ.get("PYTEST_XDIST_WORKER"):
        pytest.fail("RunScript safety live tests must not run under pytest-xdist")
    if config is not None and getattr(config, "workerinput", None) is not None:
        pytest.fail("RunScript safety live tests must not run under pytest-xdist")


def _native_request(method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=NATIVE_CLIENT_HEADERS) as client:
            if method == "GET":
                response = client.get(url)
            elif method == "POST":
                response = client.post(url) if body is None else client.post(url, json=body)
            else:
                raise AssertionError(f"Unsupported method: {method}")
    except httpx.HTTPError as exc:
        pytest.fail(f"{method} {path} failed: {exc!r}")

    try:
        payload = response.json()
    except json.JSONDecodeError:
        pytest.fail(f"{method} {path} returned non-JSON response: {response.text!r}")
    if not isinstance(payload, dict):
        pytest.fail(f"{method} {path} returned non-object JSON: {payload!r}")
    if response.status_code >= 500:
        pytest.fail(f"{method} {path} returned HTTP {response.status_code}: {payload!r}")
    return payload


def _native_get(path: str) -> dict[str, Any]:
    return _native_request("GET", path)


def _native_post(path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    return _native_request("POST", path, body)


def _native_ping() -> None:
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT, headers=NATIVE_CLIENT_HEADERS) as client:
            response = client.get(f"{_base_url()}/ping")
    except httpx.HTTPError as exc:
        pytest.fail(f"GET /ping failed: {exc!r}")

    if response.text.strip() == "pong":
        return
    try:
        payload = response.json()
    except json.JSONDecodeError:
        pytest.fail(f"GET /ping returned unexpected response: {response.text!r}")
    if not isinstance(payload, dict) or payload.get("success") is not True:
        pytest.fail(f"GET /ping did not report success: {payload!r}")


def _is_idle_prompt_text(prompt: Any) -> bool:
    if prompt is None:
        text = ""
    elif isinstance(prompt, str):
        text = prompt.strip()
    else:
        return False
    return text == "" or text == "Command" or text.startswith("Command:")


def _is_idle_prompt_response(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    return (
        payload.get("success") is True
        and isinstance(data, dict)
        and data.get("is_active") is False
        and _is_idle_prompt_text(data.get("prompt", ""))
    )


def _is_verified_cancel_response(payload: dict[str, Any]) -> bool:
    data = payload.get("data")
    if not (
        payload.get("success") is True
        and isinstance(data, dict)
        and data.get("cancelled") is True
        and data.get("verified") is True
        and data.get("is_active") is False
    ):
        return False
    if "prompt" in data and not _is_idle_prompt_text(data.get("prompt")):
        return False
    return True


def _write_unrecovered_sentinel(
    request: pytest.FixtureRequest,
    reason: str,
    last_command: Any | None = None,
    last_cancel: Any | None = None,
    last_prompt: Any | None = None,
) -> Path:
    payload = {
        "test_node_id": request.node.nodeid,
        "reason": reason,
        "pid": _owned_pid(),
        "port": _owned_port(),
        "last_command": last_command,
        "last_cancel": last_cancel,
        "last_prompt": last_prompt,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    path = _artifact_dir() / "runscript_safety_unrecovered.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _kill_owned_pid() -> subprocess.CompletedProcess[str]:
    _assert_owned_runtime_binding()
    return subprocess.run(
        ["taskkill", "/PID", str(_owned_pid()), "/F"],
        capture_output=True,
        check=False,
        text=True,
        timeout=REQUEST_TIMEOUT,
    )


def _ensure_idle_or_abort(request: pytest.FixtureRequest) -> None:
    last_prompt = _native_get("/command/prompt")
    if _is_idle_prompt_response(last_prompt):
        return

    last_cancel = _native_post("/command/cancel")
    deadline = time.monotonic() + RECOVERY_TIMEOUT
    while time.monotonic() < deadline:
        last_prompt = _native_get("/command/prompt")
        if _is_idle_prompt_response(last_prompt):
            return
        time.sleep(RECOVERY_POLL_INTERVAL)

    _write_unrecovered_sentinel(
        request,
        "prompt_not_idle_after_cancel",
        last_cancel=last_cancel,
        last_prompt=last_prompt,
    )
    _kill_owned_pid()
    pytest.exit("RunScript safety prompt recovery failed; owned Rhino process killed", returncode=2)


def _require_verified_cancel_or_abort(request: pytest.FixtureRequest) -> None:
    last_cancel = _native_post("/command/cancel")
    last_prompt = _native_get("/command/prompt")
    if _is_verified_cancel_response(last_cancel) and _is_idle_prompt_response(last_prompt):
        return

    _write_unrecovered_sentinel(
        request,
        "verified_cancel_or_idle_prompt_missing",
        last_cancel=last_cancel,
        last_prompt=last_prompt,
    )
    _kill_owned_pid()
    pytest.exit("RunScript safety verified cancel failed; owned Rhino process killed", returncode=2)


def setup_module(module: Any) -> None:
    _assert_not_parallel()


@pytest.fixture
def owned_rhino_runtime(request: pytest.FixtureRequest) -> dict[str, Any]:
    _assert_not_parallel(request.config)
    _assert_owned_runtime_binding()
    _native_ping()
    return {"port": _owned_port(), "pid": _owned_pid(), "base_url": _base_url()}


@pytest.fixture(autouse=True)
def prompt_recovery_guard(
    request: pytest.FixtureRequest,
    owned_rhino_runtime: dict[str, Any],
) -> None:
    # Prompt observation alone does not clear /command uncertainty; teardown
    # requires a verified cancel plus an idle prompt.
    _ensure_idle_or_abort(request)
    yield
    _require_verified_cancel_or_abort(request)


@pytest.fixture(autouse=True)
def runscript_safety_hook_reset(
    request: pytest.FixtureRequest,
    prompt_recovery_guard: None,
) -> None:
    yield
    if request.node.get_closest_marker("runscript_safety_hooks") is None:
        return
    reset = _native_post("/command/_test/runscript-safety-hook", {"hook": "reset"})
    assert reset.get("success") is True, reset


def _assert_deprecated_interactive_refusal(payload: dict[str, Any], route: str) -> None:
    data = payload.get("data")
    assert payload.get("success") is False
    assert isinstance(data, dict)
    assert data.get("error") == "interactive_command_deprecated"
    assert data.get("route") == route
    assert data.get("verified") is False


def _assert_command_uncertain_failure(payload: dict[str, Any]) -> None:
    data = payload.get("data")
    assert payload.get("success") is False
    assert isinstance(data, dict)
    assert data.get("verified") is False
    assert data.get("executed") is not True
    assert data.get("state_uncertain") is True
    assert (
        data.get("waitingFor")
        or data.get("code") in {"native_command_prompt_unknown", "native_command_timeout"}
    )


def _set_hook(hook: str, enabled: bool = True) -> dict[str, Any]:
    return _native_post("/command/_test/runscript-safety-hook", {"hook": hook, "enabled": enabled})


def _mcp_success_data(payload: dict[str, Any]) -> dict[str, Any]:
    assert isinstance(payload, dict)
    assert payload.get("success") is True
    data = payload.get("data")
    assert isinstance(data, dict)
    return data


class SafeSelNoneStore:
    def parse_command_string(self, command_string: str) -> dict[str, Any]:
        assert command_string == "_SelNone"
        return {
            "command": "SelNone",
            "mode": "default",
            "syntax": "_SelNone",
            "parameters": {},
            "options_used": [],
        }

    def get_command(self, command: str) -> SimpleNamespace:
        assert command == "SelNone"
        return SimpleNamespace(
            options={},
            modes={"default": SimpleNamespace(syntax="_SelNone")},
            preconditions={"safe_non_interactive": True},
        )


def test_native_prompt_and_cancel_idle_contracts() -> None:
    prompt = _native_get("/command/prompt")
    assert _is_idle_prompt_response(prompt)

    cancel = _native_post("/command/cancel")
    assert _is_verified_cancel_response(cancel)


def test_native_start_and_send_refused_in_normal_mode() -> None:
    start = _native_post("/command/start", {"command": "_Line"})
    _assert_deprecated_interactive_refusal(start, "/command/start")

    send = _native_post("/command/send", {"input": "0,0,0"})
    _assert_deprecated_interactive_refusal(send, "/command/send")


def test_native_command_allows_harmless_complete_command() -> None:
    response = _native_post("/command", {"command": "_SelNone"})
    data = response.get("data")
    assert response.get("success") is True
    assert isinstance(data, dict)
    assert data.get("executed") is True
    assert data.get("command") == "_SelNone"


def test_active_prompt_quarantines_command_until_cancel(prompt_recovery_guard: None) -> None:
    first = _native_post("/command", {"command": "_-Line", "echo": False})
    _assert_command_uncertain_failure(first)

    quarantined = _native_post("/command", {"command": "_SelNone", "echo": False})
    data = quarantined.get("data")
    assert quarantined.get("success") is False
    assert isinstance(data, dict)
    assert data.get("code") == "native_command_state_uncertain"
    assert data.get("verified") is False

    cancel = _native_post("/command/cancel")
    assert _is_verified_cancel_response(cancel)

    prompt = _native_get("/command/prompt")
    assert _is_idle_prompt_response(prompt)

    final = _native_post("/command", {"command": "_SelNone", "echo": False})
    final_data = final.get("data")
    assert final.get("success") is True
    assert isinstance(final_data, dict)
    assert final_data.get("executed") is True


def test_concurrent_cancel_does_not_mask_command_uncertainty(
    prompt_recovery_guard: None,
) -> None:
    command_result: dict[str, Any] | None = None
    command_error: BaseException | None = None

    def run_prompt_command() -> None:
        nonlocal command_result, command_error
        try:
            command_result = _native_post("/command", {"command": "_-Line", "echo": False})
        except BaseException as exc:
            command_error = exc

    command_thread = threading.Thread(target=run_prompt_command)
    command_thread.start()
    time.sleep(0.5)

    cancel = _native_post("/command/cancel")
    command_thread.join(timeout=REQUEST_TIMEOUT)
    assert not command_thread.is_alive()
    if command_error is not None:
        raise command_error
    assert command_result is not None
    _assert_command_uncertain_failure(command_result)
    assert _is_verified_cancel_response(cancel)

    final = _native_post("/command", {"command": "_SelNone", "echo": False})
    final_data = final.get("data")
    assert final.get("success") is True
    assert isinstance(final_data, dict)
    assert final_data.get("executed") is True


def test_runscript_safety_hooks_disabled_by_default(owned_rhino_runtime: dict[str, Any]) -> None:
    response = _set_hook("prompt_unknown")
    data = response.get("data")
    assert response.get("success") is False
    assert isinstance(data, dict)
    assert data.get("error") == "runscript_safety_test_hooks_disabled"


@pytest.mark.runscript_safety_hooks
def test_hook_prompt_unknown_sets_uncertain_state(prompt_recovery_guard: None) -> None:
    hook = _set_hook("prompt_unknown")
    assert hook.get("success") is True

    response = _native_post("/command", {"command": "_SelNone", "echo": False})
    data = response.get("data")
    assert response.get("success") is False
    assert isinstance(data, dict)
    assert data.get("code") == "native_command_prompt_unknown"
    assert data.get("verified") is False
    assert data.get("state_uncertain") is True

    quarantined = _native_post("/command", {"command": "_SelNone", "echo": False})
    quarantined_data = quarantined.get("data")
    assert quarantined.get("success") is False
    assert isinstance(quarantined_data, dict)
    assert quarantined_data.get("code") == "native_command_state_uncertain"


@pytest.mark.runscript_safety_hooks
def test_hook_command_timeout_sets_uncertain_state(prompt_recovery_guard: None) -> None:
    hook = _set_hook("command_timeout")
    assert hook.get("success") is True

    response = _native_post("/command", {"command": "_SelNone", "echo": False})
    data = response.get("data")
    assert response.get("success") is False
    assert isinstance(data, dict)
    assert data.get("code") == "native_command_timeout"
    assert data.get("verified") is False
    assert data.get("state_uncertain") is True

    quarantined = _native_post("/command", {"command": "_SelNone", "echo": False})
    quarantined_data = quarantined.get("data")
    assert quarantined.get("success") is False
    assert isinstance(quarantined_data, dict)
    assert quarantined_data.get("code") == "native_command_state_uncertain"


@pytest.mark.runscript_safety_hooks
def test_hook_cancel_active_prompt_preserves_uncertain_state(prompt_recovery_guard: None) -> None:
    first = _native_post("/command", {"command": "_-Line", "echo": False})
    _assert_command_uncertain_failure(first)

    hook = _set_hook("cancel_prompt_active")
    assert hook.get("success") is True

    cancel = _native_post("/command/cancel")
    data = cancel.get("data")
    assert cancel.get("success") is False
    assert isinstance(data, dict)
    assert data.get("cancelled") is False
    assert data.get("verified") is False
    assert data.get("state_uncertain") is True
    assert data.get("is_active") is True

    quarantined = _native_post("/command", {"command": "_SelNone", "echo": False})
    quarantined_data = quarantined.get("data")
    assert quarantined.get("success") is False
    assert isinstance(quarantined_data, dict)
    assert quarantined_data.get("code") == "native_command_state_uncertain"


@pytest.mark.runscript_safety_hooks
def test_hook_cancel_waits_for_command_verification_window() -> None:
    hook = _set_hook("prompt_poll_delay")
    assert hook.get("success") is True

    command_result: dict[str, Any] | None = None
    command_error: BaseException | None = None

    def run_safe_command() -> None:
        nonlocal command_result, command_error
        try:
            command_result = _native_post("/command", {"command": "_SelNone", "echo": False})
        except BaseException as exc:
            command_error = exc

    command_thread = threading.Thread(target=run_safe_command)
    command_thread.start()
    time.sleep(0.1)

    start = time.monotonic()
    cancel = _native_post("/command/cancel")
    elapsed = time.monotonic() - start

    command_thread.join(timeout=REQUEST_TIMEOUT)
    assert not command_thread.is_alive()
    if command_error is not None:
        raise command_error
    assert command_result is not None
    command_data = command_result.get("data")
    assert command_result.get("success") is True
    assert isinstance(command_data, dict)
    assert command_data.get("executed") is True

    assert elapsed >= 1.0
    assert _is_verified_cancel_response(cancel)


@pytest.mark.asyncio
async def test_mcp_prompt_and_cancel_wrappers_preserve_native_success() -> None:
    from rook import server

    prompt = await server._call_tool_dispatch("rhino_command_interactive_prompt", {})
    prompt_data = _mcp_success_data(prompt)
    assert prompt_data.get("is_active") is False
    assert _is_idle_prompt_text(prompt_data.get("prompt", ""))

    cancel = await server._call_tool_dispatch("rhino_command_interactive_cancel", {})
    cancel_data = _mcp_success_data(cancel)
    assert cancel_data.get("cancelled") is True
    assert cancel_data.get("verified") is True
    assert cancel_data.get("is_active") is False
    if "prompt" in cancel_data:
        assert _is_idle_prompt_text(cancel_data.get("prompt"))


@pytest.mark.asyncio
async def test_mcp_rhino_command_rejects_before_native_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from rook import server

    calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def fake_call_rhino(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append((args, kwargs))
        raise AssertionError("rhino_command safety preflight must run before call_rhino")

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)
    monkeypatch.setattr(server.command_learner, "knowledge_store", None)

    response = await server._call_tool_dispatch("rhino_command", {"command": "_-Line"})

    assert response.get("success") is False
    data = response.get("data")
    assert isinstance(data, dict)
    assert data.get("error") == "run_script_safety_refusal"
    assert data.get("reason") == "command_safety_unavailable"
    assert calls == []


@pytest.mark.asyncio
async def test_mcp_rhino_command_allows_explicit_safe_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rook import server

    monkeypatch.setattr(server.command_learner, "knowledge_store", SafeSelNoneStore())

    response = await server._call_tool_dispatch("rhino_command", {"command": "_SelNone"})
    data = _mcp_success_data(response)

    assert data.get("executed") is True
    assert data.get("command") == "_SelNone"


@pytest.mark.asyncio
async def test_deprecated_prompt_driving_tools_not_listed_in_normal_tools() -> None:
    from rook import server

    tools = await server.list_tools()
    names = {tool.name for tool in tools}

    assert "rhino_command_interactive_start" not in names
    assert "rhino_command_interactive_send" not in names
    assert "rhino_command_experiment" not in names
    assert "rhino_learn_interactive" not in names
    assert "rhino_learn_next" not in names
    assert "rhino_learn_variations_interactive" not in names
    assert "rhino_prepare_geometry" not in names
    assert "rhino_command_interactive_prompt" in names
    assert "rhino_command_interactive_cancel" in names
