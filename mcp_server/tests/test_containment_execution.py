from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


from rook.agent.tool_dispatcher import ToolDispatcher  # noqa: E402
from rook.tool_lifecycle import CONTAINED_TOOLS  # noqa: E402


PINNED = [entry.name for entry in CONTAINED_TOOLS]
DENIED = [*PINNED, "rc_future_probe"]


class UntouchableArguments(dict):
    def __iter__(self):
        raise AssertionError("contained arguments were accessed")

    def get(self, *_args, **_kwargs):
        raise AssertionError("contained arguments were accessed")


def _wire_payload(result) -> dict:
    text = result[0].text
    assert text.startswith("Error: ")
    return json.loads(text.removeprefix("Error: "))


def _assert_denial(payload: dict, name: str) -> None:
    assert payload["code"] == "legacy_semantic_tool_contained"
    assert payload["tool"] == name
    assert payload["verified"] is False
    assert payload["retryable"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("name", DENIED)
async def test_public_and_server_dispatch_deny_before_argument_access(name: str) -> None:
    from rook import server

    _assert_denial(_wire_payload(await server.call_tool(name, UntouchableArguments())), name)
    direct = await server._call_tool_dispatch(name, UntouchableArguments())
    assert direct["success"] is False
    _assert_denial(direct["data"], name)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", DENIED)
async def test_progressive_meta_denies_target_before_target_arguments(name: str) -> None:
    from rook import server

    class Outer(dict):
        def get(self, key, default=None):
            if key == "name":
                return name
            if key == "arguments":
                raise AssertionError("target arguments were accessed")
            return super().get(key, default)

    result = await server._handle_meta_tool("rook_tools_call", Outer(), server.Profile.FULL)
    _assert_denial(_wire_payload(result), name)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", DENIED)
async def test_internal_executor_and_private_handlers_deny_without_work(name: str) -> None:
    from rook import server

    result = await server._mcp_tool_executor(name, UntouchableArguments())
    assert result["success"] is False
    _assert_denial(result["data"], name)

    if name == "spawn_agent":
        private = await server._handle_spawn_agent(UntouchableArguments())
        _assert_denial(private["data"], name)
    elif name == "plan_and_execute":
        private = await server._handle_plan_and_execute(UntouchableArguments())
        _assert_denial(private["data"], name)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", DENIED)
async def test_tool_dispatcher_all_entry_seams_deny_before_params_or_handlers(name: str) -> None:
    called = False

    async def handler(**_kwargs):
        nonlocal called
        called = True
        return {"success": True}

    dispatcher = ToolDispatcher(local_tools={name: handler})
    for invoke in (
        lambda: dispatcher.dispatch(name, UntouchableArguments()),
        lambda: dispatcher._dispatch_inner(name, UntouchableArguments(), None),
        lambda: dispatcher._call_local(name, UntouchableArguments()),
        lambda: dispatcher._dispatch_with_knowledge(name, UntouchableArguments(), None),
    ):
        result = await invoke()
        assert result["success"] is False
        _assert_denial(result["data"], name)
    assert called is False


def test_tool_dispatcher_refuses_contained_local_registration() -> None:
    dispatcher = ToolDispatcher()
    dispatcher.register_local("spawn_agent", object())
    dispatcher.register_local("rc_future_probe", object())
    dispatcher.register_locals({"gh_execute_intent": object(), "safe_tool": object()})
    assert set(dispatcher._local_tools) == {"safe_tool"}


@pytest.mark.asyncio
@pytest.mark.parametrize("profile", ("full", "lean", "readonly"))
async def test_public_tombstone_precedes_profile_and_emits_once(monkeypatch, profile: str) -> None:
    from rook import server
    import rook.tool_lifecycle_runtime as runtime

    monkeypatch.setenv("ROOK_MCP_TOOL_PROFILE", profile)
    events = []
    monkeypatch.setattr(runtime, "_record_denial", lambda entry, origin: events.append((entry.name, origin.value)))
    payload = _wire_payload(await server.call_tool("spawn_agent", UntouchableArguments()))
    _assert_denial(payload, "spawn_agent")
    assert events == [("spawn_agent", "public_mcp")]
