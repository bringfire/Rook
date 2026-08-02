"""Cross-seam tests for the explicit RookChat Worker-first C# action."""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping
from typing import Any

import pytest
from aiohttp.test_utils import TestClient, TestServer

from rook import bridge
from rook.agent.chat.chat_runner import ChatRunner
from rook.agent.chat.conversation_store import ConversationStore
from rook.agent.chat.prompt_builder import PromptBuilder
from rook.agent.chat.server import create_chat_app
from rook.agent.model_profiles import ModelSet
import rook.agent.worker_first_csharp_application as application


_INTENT = "Create one clean C# component"
_BODY = "A = 37.5;"
_PLANNER_MODEL = "anthropic/claude-opus-4-6"
_WORKER_MODEL = "ollama_chat/qwen3-coder:30b-a3b-q8_0"
_API_BASE = "http://worker.invalid/v1"


def _planner_payload(goal: str = _INTENT) -> dict[str, Any]:
    return {
        "goal": goal,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": "A", "type": "double"}],
        },
        "acceptance": "clean_compile_receipt",
    }


def _all_strings(value: object):
    if type(value) is str:
        yield value
    elif type(value) is dict:
        for key, item in value.items():
            yield from _all_strings(key)
            yield from _all_strings(item)
    elif type(value) in {list, tuple}:
        for item in value:
            yield from _all_strings(item)


class _NoChatRunner(ChatRunner):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    async def run_turn(self, *args: Any, **kwargs: Any):
        self.calls += 1
        raise AssertionError("ordinary ChatRunner must not own the explicit build")
        yield  # pragma: no cover


class _PlannerTransport:
    def __init__(self, harness: "_Harness") -> None:
        self.harness = harness

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.harness.planner_calls += 1
        captured = copy.deepcopy(dict(prompt_artifact))
        self.harness.planner_prompts.append(captured)
        assert self.harness.planner_calls == 1
        assert json.loads(captured["messages"][1]["content"]) == {
            "user_intent": _INTENT
        }
        prompt_text = "\n".join(_all_strings(captured))
        assert _BODY not in prompt_text
        assert "gh_create_csharp_script" not in prompt_text
        assert "draft_create_body" not in prompt_text
        assert "component_guid" not in prompt_text
        if self.harness.scenario == "planner_failure":
            raise RuntimeError("SENTINEL planner response")
        if self.harness.scenario == "draft_rejected":
            payload = {**_planner_payload(), "unexpected": True}
        elif self.harness.scenario == "goal_mismatch":
            payload = _planner_payload("SENTINEL substituted intent")
        else:
            payload = _planner_payload()
        return json.dumps(payload, separators=(",", ":"))


class _WorkerTransport:
    def __init__(self, harness: "_Harness") -> None:
        self.harness = harness

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        self.harness.worker_calls += 1
        captured = copy.deepcopy(dict(prompt_artifact))
        self.harness.worker_prompts.append(captured)
        assert self.harness.worker_calls == 1
        request = json.loads(captured["messages"][1]["content"])
        request_strings = set(_all_strings(request))
        assert _INTENT in request_strings
        assert "draft_create_body" in request_strings
        assert _BODY not in request_strings
        assert "draft_repair_params" not in request_strings
        assert "gh_update_script" not in request_strings
        assert "component_guid" not in request_strings
        if self.harness.scenario == "worker_refusal":
            payload: object = {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "refusal",
                "category": "unsupported_action",
                "reason": "SENTINEL worker response",
            }
        elif self.harness.scenario == "worker_malformed":
            return "SENTINEL not json"
        else:
            payload = {
                "schema": "rook.local_worker_turn_response:v1",
                "kind": "action_request",
                "action_id": "draft_create_body",
                "rationale": "Author the initial body.",
                "input": {"code": _BODY},
            }
        return json.dumps(payload, separators=(",", ":"))


class _Dispatcher:
    def __init__(self, harness: "_Harness", local_tools: dict[str, object]) -> None:
        self.harness = harness
        assert local_tools is harness.local_tools

    async def dispatch(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        self.harness.execution_calls += 1
        captured = copy.deepcopy(params)
        self.harness.dispatches.append((tool_name, captured))
        self.harness.dispatch_contexts.append(bridge.get_rhino_request_context())
        assert self.harness.execution_calls == 1
        assert tool_name == "gh_create_csharp_script"
        assert captured == {
            "pins_in": (),
            "pins_out": ("A:double",),
            "name": "RookMinimalInitialBodyHandoff",
            "x": 375,
            "y": 1080,
            "code": _BODY,
        }
        if self.harness.scenario == "ambiguous_create":
            raise RuntimeError("SENTINEL ambiguous create")
        errors = 2 if self.harness.scenario == "compile_failure" else 0
        warnings = 1 if errors else 0
        canonical = json.dumps(captured, sort_keys=True, separators=(",", ":"))
        component_guid = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return {
            "success": errors == 0,
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": "created_with_errors" if errors else "usable",
                    "mutation": {
                        "status": "created",
                        "component_guid": component_guid,
                    },
                    "verification": {
                        "status": "failed" if errors else "passed",
                        "target_error_count": errors,
                        "target_warning_count": warnings,
                    },
                    "repair_anchor": {
                        "component_guid": component_guid,
                        "language": "csharp",
                        "target_errors": ["SENTINEL compile diagnostic"] * errors,
                    },
                }
            },
        }


class _Harness:
    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.planner_calls = 0
        self.worker_calls = 0
        self.execution_calls = 0
        self.planner_prompts: list[dict[str, Any]] = []
        self.worker_prompts: list[dict[str, Any]] = []
        self.dispatches: list[tuple[str, dict[str, Any]]] = []
        self.dispatch_contexts: list[dict[str, int | None]] = []
        self.local_tools = {"gh_create_csharp_script": object()}

    def get_models(self, profile: str) -> ModelSet:
        assert profile == "hybrid"
        return ModelSet(
            planner=_PLANNER_MODEL,
            worker=_WORKER_MODEL,
            specialist="unused",
            guardian="unused",
            dspy="unused",
            api_base=_API_BASE,
        )

    def construct_transport(self, **kwargs: Any):
        model = kwargs["model"]
        if model == _PLANNER_MODEL:
            return _PlannerTransport(self)
        if model == _WORKER_MODEL:
            return _WorkerTransport(self)
        raise AssertionError(f"unexpected model: {model}")

    def build_local_tools(self) -> dict[str, object]:
        return self.local_tools

    def construct_dispatcher(self, *, local_tools: dict[str, object]) -> _Dispatcher:
        return _Dispatcher(self, local_tools)


def _install_harness(monkeypatch: pytest.MonkeyPatch, scenario: str) -> _Harness:
    harness = _Harness(scenario)
    monkeypatch.setattr(application, "get_models", harness.get_models)
    monkeypatch.setattr(
        application,
        "LiteLLMWorkerTransport",
        harness.construct_transport,
    )
    monkeypatch.setattr(application, "build_local_tools", harness.build_local_tools)
    monkeypatch.setattr(application, "ToolDispatcher", harness.construct_dispatcher)
    return harness


async def _run_request(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    *,
    execution_mode: str = "worker_first_csharp_v1",
) -> tuple[list[dict[str, Any]], _Harness, ConversationStore, _NoChatRunner, int]:
    harness = _install_harness(monkeypatch, scenario)
    store = ConversationStore()
    runner = _NoChatRunner()
    conversation = store.create("worker", document_serial_number=73)
    initial_messages = copy.deepcopy(conversation.messages)
    app = create_chat_app(
        store=store,
        builder=PromptBuilder(),
        runner=runner,
        rhino_process_id=2468,
    )
    client = TestClient(TestServer(app))
    await client.start_server()
    try:
        response = await client.post(
            "/agent/chat/message",
            json={
                "conversation_id": conversation.id,
                "message": _INTENT,
                "execution_mode": execution_mode,
                "documentSerialNumber": 73,
            },
        )
        status = response.status
        text = await response.text()
    finally:
        await client.close()
    events = [json.loads(line) for line in text.splitlines()] if status == 200 else []
    assert conversation.messages == initial_messages
    assert conversation.active_run_id is None
    return events, harness, store, runner, status


@pytest.mark.asyncio
async def test_real_route_and_application_root_complete_the_worker_first_vertical(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, harness, _, runner, status = await _run_request(monkeypatch, "clean")

    assert status == 200
    assert [event["type"] for event in events] == [
        "tool_start",
        "tool_result",
        "done",
    ]
    start, result_event, done = events
    assert start == {
        "type": "tool_start",
        "name": "worker_first_csharp_v1",
        "tool_call_id": result_event["tool_call_id"],
    }
    assert result_event["tool_status"] == "success"
    assert result_event["verified"] is True
    assert json.loads(result_event["result"]) == {
        "status": "success",
        "terminal_stage": "terminal",
        "terminal_reason": "terminal_node_selected:done",
        "compile_status": "passed",
        "error_count": 0,
        "warning_count": 0,
        "component_created": True,
    }
    assert done == {"type": "done", "usage": {}}
    assert (harness.planner_calls, harness.worker_calls, harness.execution_calls) == (
        1,
        1,
        1,
    )
    assert [name for name, _ in harness.dispatches] == ["gh_create_csharp_script"]
    assert harness.dispatch_contexts == [
        {
            "port": None,
            "process_id": 2468,
            "document_serial_number": 73,
        }
    ]
    assert runner.calls == 0
    serialized = json.dumps(events)
    assert _INTENT not in serialized
    assert _BODY not in serialized
    assert "component_guid" not in serialized
    assert "SENTINEL" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "expected_counts", "expected_projection"),
    [
        (
            "planner_failure",
            (1, 0, 0),
            ("failed", "planner_adapter", "unavailable", False),
        ),
        (
            "draft_rejected",
            (1, 0, 0),
            ("failed", "draft_admission", "unavailable", False),
        ),
        (
            "goal_mismatch",
            (1, 0, 0),
            ("failed", "draft_admission", "unavailable", False),
        ),
        (
            "worker_refusal",
            (1, 1, 0),
            ("failed", "worker_disposition", "unavailable", False),
        ),
        (
            "worker_malformed",
            (1, 1, 0),
            ("failed", "worker_adapter", "unavailable", False),
        ),
        (
            "compile_failure",
            (1, 1, 1),
            ("failed", "verify_create", "failed", True),
        ),
        (
            "ambiguous_create",
            (1, 1, 1),
            ("failed", "create", "unavailable", None),
        ),
    ],
)
async def test_real_route_and_application_root_preserve_native_stop_prefixes(
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
    expected_counts: tuple[int, int, int],
    expected_projection: tuple[str, str, str, bool | None],
) -> None:
    events, harness, _, runner, status = await _run_request(monkeypatch, scenario)

    assert status == 200
    assert [event["type"] for event in events] == [
        "tool_start",
        "tool_result",
        "done",
    ]
    projection = json.loads(events[1]["result"])
    assert (
        projection["status"],
        projection["terminal_stage"],
        projection["compile_status"],
        projection["component_created"],
    ) == expected_projection
    assert events[1]["tool_status"] == "failed"
    assert events[1]["verified"] is False
    assert (
        harness.planner_calls,
        harness.worker_calls,
        harness.execution_calls,
    ) == expected_counts
    assert runner.calls == 0
    serialized = json.dumps(events)
    assert _BODY not in serialized
    assert "SENTINEL" not in serialized


@pytest.mark.asyncio
async def test_unknown_mode_refuses_before_application_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events, harness, _, runner, status = await _run_request(
        monkeypatch,
        "clean",
        execution_mode="unknown_mode",
    )

    assert status == 400
    assert events == []
    assert (harness.planner_calls, harness.worker_calls, harness.execution_calls) == (
        0,
        0,
        0,
    )
    assert runner.calls == 0
