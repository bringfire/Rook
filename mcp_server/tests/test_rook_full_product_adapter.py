from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ADAPTER_PATH = (
    Path(__file__).parents[2]
    / "integrations"
    / "prime"
    / "skills"
    / "rook-full"
    / "src"
    / "rook_full"
    / "__init__.py"
)
PACKAGE_ROOT = ADAPTER_PATH.parents[2]
GH_ID = "01234567-89ab-cdef-0123-456789abcdef"


class FakeMcpToolError(RuntimeError):
    def __init__(self, message: str, *, structured_content: Any = None) -> None:
        self.structured_content = structured_content
        super().__init__(message)


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch):
    rlm = types.ModuleType("rlm")
    mcp_base = types.ModuleType("rlm.mcp_base")
    mcp_base.McpToolError = FakeMcpToolError
    monkeypatch.setitem(sys.modules, "rlm", rlm)
    monkeypatch.setitem(sys.modules, "rlm.mcp_base", mcp_base)
    name = f"rook_full_product_test_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, ADAPTER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def product_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    install = tmp_path / "install"
    data = tmp_path / "data"
    cache = data / "dspy-cache"
    chirp = install / "chirp"
    workdir = install / "mcp_server"
    python = install / "venv" / "Scripts" / "python.exe"
    for directory in (
        data,
        cache,
        chirp,
        workdir,
        python.parent,
        tmp_path / "temp",
        tmp_path / "profile",
        tmp_path / "local",
        tmp_path / "roaming",
        tmp_path / "programdata",
    ):
        directory.mkdir(parents=True, exist_ok=True)
    python.write_bytes(b"python")
    values = {
        "ROOK_MCP_PYTHON_EXECUTABLE": str(python),
        "ROOK_MCP_WORKING_DIRECTORY": str(workdir),
        "ROOK_INSTALL_ROOT": str(install),
        "ROOK_DATA_DIR": str(data),
        "DSPY_CACHEDIR": str(cache),
        "CHIRP_HOME": str(chirp),
        "ROOK_MODE": "release",
        "ROOK_DSPY_RESTRICT_PICKLE": "1",
        "ROOK_MCP_TOOL_PROFILE": "full",
        "ROOK_MCP_TARGET_MODE": "panel_locked",
        "ROOK_MCP_TARGET_PROCESS_ID": "2468",
        "ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS": "638920000000000000",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER": "42",
        "ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID": GH_ID,
        "SystemRoot": "C:/Windows",
        "WINDIR": "C:/Windows",
        "COMSPEC": "C:/Windows/System32/cmd.exe",
        "TEMP": str(tmp_path / "temp"),
        "TMP": str(tmp_path / "temp"),
        "USERPROFILE": str(tmp_path / "profile"),
        "LOCALAPPDATA": str(tmp_path / "local"),
        "APPDATA": str(tmp_path / "roaming"),
        "PROGRAMDATA": str(tmp_path / "programdata"),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


class FakeSession:
    def __init__(self, result: Any = None) -> None:
        self.result = result or SimpleNamespace(
            isError=False,
            structuredContent={"success": True, "data": {"ok": True}},
            content=[],
        )
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.initialize_gate: asyncio.Event | None = None
        self.call_gate: asyncio.Event | None = None
        self.initialize_error: BaseException | None = None
        self.call_error: BaseException | None = None
        self.close_error: BaseException | None = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        if self.close_error is not None:
            raise self.close_error

    async def initialize(self) -> None:
        if self.initialize_gate is not None:
            await self.initialize_gate.wait()
        if self.initialize_error is not None:
            raise self.initialize_error

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        self.calls.append((name, arguments))
        if self.call_gate is not None:
            await self.call_gate.wait()
        if self.call_error is not None:
            raise self.call_error
        return self.result


def install_transport(
    adapter,
    monkeypatch: pytest.MonkeyPatch,
    session: FakeSession,
    *,
    launch_gate: asyncio.Event | None = None,
    transport_close_error: BaseException | None = None,
    close_observer: list[bool] | None = None,
):
    captured: list[Any] = []

    @asynccontextmanager
    async def transport(parameters, *, errlog):
        captured.append(parameters)
        if launch_gate is not None:
            await launch_gate.wait()
        try:
            yield object(), object()
        finally:
            if close_observer is not None:
                close_observer.append(True)
            if transport_close_error is not None:
                raise transport_close_error

    monkeypatch.setattr(adapter, "stdio_client", transport)
    monkeypatch.setattr(adapter, "ClientSession", lambda _read, _write: session)
    return captured


def test_public_api_and_source_are_product_only(adapter) -> None:
    assert adapter.__all__ == ("search", "read", "call")
    assert all(callable(getattr(adapter, name)) for name in adapter.__all__)
    source = ADAPTER_PATH.read_text(encoding="utf-8")
    assert "gh_behavioral_acceptance" not in source
    assert "ROOK_GH_AUTHORING_SOURCE_LOG" not in source
    assert "ROOK_GATEWAY_CALL_LIMIT" not in source
    assert "C:/Users/" not in source


def test_product_skill_freezes_goal_target_and_completion_discipline() -> None:
    skill = (PACKAGE_ROOT / "SKILL.md").read_text(encoding="utf-8")
    reference = (PACKAGE_ROOT / "references" / "grasshopper.md").read_text(
        encoding="utf-8"
    )
    normalized_skill = " ".join(skill.split())
    normalized_reference = " ".join(reference.split())

    assert "name: rook-full" in skill
    assert "ordinary conversational and observational turns" in normalized_skill
    assert "await goal.get()" in skill
    assert "await goal.create(" in skill
    assert "User-issued `/goal` commands" in skill
    assert "await rook_full.search(" in skill
    assert "await rook_full.read(" in skill
    assert "await rook_full.call(" in skill
    assert "references/grasshopper.md" in skill
    assert "Stop aborts the current prompt" in skill
    assert "dedicated final IPython cell" in skill
    assert "final text only" in skill
    assert "same receipt" in reference
    assert "goal.complete()" in reference
    assert "No later tool call" in normalized_reference


@pytest.mark.asyncio
async def test_child_configuration_is_closed_and_drops_ambient_authority(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("PYTHONPATH", "C:/hostile")
    monkeypatch.setenv("ROOK_MCP_TARGET_PORT", "9999")
    monkeypatch.setenv("UNRELATED", "ambient")
    session = FakeSession()
    captured = install_transport(adapter, monkeypatch, session)

    assert await adapter.call("gh_status", {}) == {"ok": True}

    assert len(captured) == 1
    parameters = captured[0]
    assert parameters.command == product_environment["ROOK_MCP_PYTHON_EXECUTABLE"]
    assert parameters.cwd == product_environment["ROOK_MCP_WORKING_DIRECTORY"]
    expected_keys = {
        "SystemRoot",
        "WINDIR",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
        "PROGRAMDATA",
        "PATH",
        "ROOK_INSTALL_ROOT",
        "ROOK_DATA_DIR",
        "ROOK_MODE",
        "DSPY_CACHEDIR",
        "ROOK_DSPY_RESTRICT_PICKLE",
        "CHIRP_HOME",
        "PYTHONHOME",
        "PYTHONPATH",
        "ROOK_MCP_TOOL_PROFILE",
        "ROOK_MCP_TARGET_MODE",
        "ROOK_MCP_TARGET_PROCESS_ID",
        "ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS",
        "ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER",
        "ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID",
    }
    assert set(parameters.env) == expected_keys
    assert parameters.env["PYTHONPATH"] == ""
    assert "secret" not in parameters.env.values()
    assert "C:/hostile" not in parameters.env.values()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("ROOK_MCP_TARGET_PROCESS_ID", "0"),
        ("ROOK_MCP_TARGET_PROCESS_START_UTC_TICKS", "0638920000000000000"),
        ("ROOK_MCP_TARGET_DOCUMENT_SERIAL_NUMBER", "missing"),
        ("ROOK_MCP_TOOL_PROFILE", "inspect"),
        ("ROOK_MCP_TARGET_MODE", "automatic"),
        ("ROOK_MCP_PYTHON_EXECUTABLE", "relative/python.exe"),
    ],
)
async def test_malformed_base_lock_refuses_before_launch(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    captured = install_transport(adapter, monkeypatch, FakeSession())

    with pytest.raises(adapter.RookFullError) as caught:
        await adapter.search("gh_status")

    assert caught.value.code == "rook_full_invalid_arguments"
    assert captured == []


@pytest.mark.asyncio
async def test_gh_call_requires_bound_document_and_rejects_conflicting_selectors(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID")
    captured = install_transport(adapter, monkeypatch, FakeSession())
    with pytest.raises(adapter.RookFullError, match="grasshopper_target_unbound"):
        await adapter.call("gh_status", {})
    assert captured == []

    monkeypatch.setenv("ROOK_MCP_TARGET_GRASSHOPPER_DOCUMENT_ID", GH_ID)
    with pytest.raises(adapter.RookFullError, match="locked target"):
        await adapter.call("gh_status", {"documentSerialNumber": 43})
    with pytest.raises(adapter.RookFullError, match="locked target"):
        await adapter.call("gh_status", {"port": 9999})
    assert captured == []


@pytest.mark.asyncio
async def test_agreeing_selectors_are_removed_before_meta_call(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    install_transport(adapter, monkeypatch, session)

    await adapter.call(
        "gh_status",
        {
            "processId": 2468,
            "processStartUtcTicks": "638920000000000000",
            "documentSerialNumber": 42,
            "grasshopperDocumentId": GH_ID,
            "detail": "summary",
        },
    )

    assert session.calls == [
        (
            "rook_tools_call",
            {"name": "gh_status", "arguments": {"detail": "summary"}},
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("phase", "expected_code"),
    [
        ("launch", "rook_full_launch_failed"),
        ("initialize", "rook_full_initialize_timeout"),
        ("call", "rook_full_outcome_uncertain"),
    ],
)
async def test_phase_timeouts_are_bounded_and_never_replayed(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    expected_code: str,
) -> None:
    monkeypatch.setattr(adapter, "_LAUNCH_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(adapter, "_INITIALIZE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(adapter, "_CALL_TIMEOUT_SECONDS", 0.01)
    session = FakeSession()
    launch_gate = asyncio.Event() if phase == "launch" else None
    session.initialize_gate = asyncio.Event() if phase == "initialize" else None
    session.call_gate = asyncio.Event() if phase == "call" else None
    captured = install_transport(
        adapter, monkeypatch, session, launch_gate=launch_gate
    )

    with pytest.raises(adapter.RookFullError) as caught:
        await adapter.call("gh_status", {})

    assert caught.value.code == expected_code
    assert len(captured) == 1
    assert len(session.calls) <= 1


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["launch", "initialize", "call"])
async def test_caller_cancellation_unwinds_each_phase(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    session = FakeSession()
    launch_gate = asyncio.Event() if phase == "launch" else None
    session.initialize_gate = asyncio.Event() if phase == "initialize" else None
    session.call_gate = asyncio.Event() if phase == "call" else None
    closed: list[bool] = []
    install_transport(
        adapter,
        monkeypatch,
        session,
        launch_gate=launch_gate,
        close_observer=closed,
    )
    task = asyncio.create_task(adapter.call("gh_status", {}))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert closed == ([True] if phase != "launch" else [])


@pytest.mark.asyncio
async def test_authentic_success_survives_cleanup_failure(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    install_transport(
        adapter,
        monkeypatch,
        session,
        transport_close_error=RuntimeError("cleanup failed"),
    )

    assert await adapter.call("gh_status", {}) == {"ok": True}
    diagnostic = adapter._last_call_diagnostic.get()
    assert diagnostic["authenticEnvelopeReceived"] is True
    assert diagnostic["cleanupSucceeded"] is False
    assert "cleanup failed" in diagnostic["cleanupError"]


@pytest.mark.asyncio
async def test_same_structured_failure_survives_cleanup_failure(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    envelope = {
        "success": False,
        "data": {"error": "target_mismatch", "message": "wrong document"},
    }
    error = FakeMcpToolError("wrong document", structured_content=envelope)
    session = FakeSession()
    session.call_error = error
    install_transport(
        adapter,
        monkeypatch,
        session,
        transport_close_error=RuntimeError("cleanup failed"),
    )

    with pytest.raises(FakeMcpToolError) as caught:
        await adapter.call("gh_status", {})

    assert caught.value is error
    assert caught.value.structured_content == envelope
    assert adapter._last_call_diagnostic.get()["cleanupSucceeded"] is False


@pytest.mark.asyncio
async def test_transport_loss_without_envelope_is_uncertain_and_not_replayed(
    adapter,
    product_environment: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = FakeSession()
    session.call_error = ConnectionError("transport lost")
    install_transport(adapter, monkeypatch, session)

    with pytest.raises(adapter.RookFullError) as caught:
        await adapter.call("gh_status", {})

    assert caught.value.code == "rook_full_outcome_uncertain"
    assert len(session.calls) == 1
