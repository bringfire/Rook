#!/usr/bin/env python
"""Operator-only real Grasshopper compile smoke for the minimal handoff."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MCP_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_MCP_SRC) not in sys.path:
    sys.path.insert(0, str(_MCP_SRC))

from rook.agent.local_worker_model_transport import (  # noqa: E402
    LiteLLMWorkerTransport,
    _local_worker_response_union_schema,
)
from rook.agent.minimal_intent_worker_integration import (  # noqa: E402
    MinimalIntentWorkerIntegrationResult,
    MinimalPlannerDraftAdapter,
    build_minimal_planner_draft_response_schema,
    run_minimal_intent_worker_integration,
)
from rook.agent.model_profiles import get_models  # noqa: E402
from rook.agent.tool_dispatcher import (  # noqa: E402
    ToolDispatcher,
    build_local_tools,
)
from rook.bridge import discover_instances  # noqa: E402, F401


_FIXED_INTENT = (
    "Create a Grasshopper C# component with one A:double output "
    "and compile cleanly."
)
_PROFILE = "hybrid"
_PLANNER_MODEL = "anthropic/claude-opus-4-6"
_WORKER_MODEL = "ollama_chat/qwen3-coder:30b-a3b-q8_0"
_LIVE_FLAG = "--execute-live"
_TIMEOUT_S = 120.0
_MAX_OUTPUT_TOKENS = 1024
_MAX_RETRIES = 0
_MAX_MODEL_ID_UTF8_BYTES = 256


@dataclass(frozen=True, slots=True)
class _ResolvedRoles:
    profile: str
    planner_model: str
    worker_model: str
    profile_api_base: str | None


@dataclass(frozen=True, slots=True)
class _ResolvedRhinoTarget:
    process_id: int
    port: int


@dataclass(frozen=True, slots=True)
class _PreparedDocument:
    state: Literal["fresh_document_verified"]
    tool_calls: int


class _ProfileRefusal(ValueError):
    def __init__(
        self,
        reason: str,
        planner_model: str | None,
        worker_model: str | None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.planner_model = planner_model
        self.worker_model = worker_model


class _TargetRefusal(ValueError):
    def __init__(
        self,
        reason: str,
        process_id: int | None,
        port: int | None,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.process_id = process_id
        self.port = port


def _bounded_identity(value: object) -> str | None:
    if type(value) is not str or not value.strip() or not value.isascii():
        return None
    if len(value.encode("utf-8")) > _MAX_MODEL_ID_UTF8_BYTES:
        return None
    return value


def _resolve_hybrid_roles() -> _ResolvedRoles:
    models = get_models(_PROFILE)
    planner = _bounded_identity(models.planner)
    worker = _bounded_identity(models.worker)
    if planner is None or worker is None:
        raise _ProfileRefusal("profile_identity_invalid", planner, worker)
    if planner != _PLANNER_MODEL or worker != _WORKER_MODEL:
        raise _ProfileRefusal("profile_role_mismatch", planner, worker)
    return _ResolvedRoles(
        profile=_PROFILE,
        planner_model=planner,
        worker_model=worker,
        profile_api_base=models.api_base,
    )


def _planner_response_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "minimal_planner_draft",
            "strict": True,
            "schema": build_minimal_planner_draft_response_schema(),
        },
    }


def _resolve_single_rhino_target(
    instances: object,
) -> _ResolvedRhinoTarget:
    if type(instances) is not list:
        raise _TargetRefusal("rooknative_identity_invalid", None, None)
    native = [
        row
        for row in instances
        if type(row) is dict
        and type(row.get("pluginType")) is str
        and row.get("pluginType") == "native"
    ]
    if not native:
        raise _TargetRefusal("rooknative_instance_absent", None, None)
    if len(native) != 1:
        raise _TargetRefusal("rooknative_instance_ambiguous", None, None)
    row = native[0]
    process_id = row.get("processId")
    port = row.get("port")
    if (
        type(process_id) is not int
        or process_id <= 0
        or type(port) is not int
        or port <= 0
    ):
        raise _TargetRefusal(
            "rooknative_identity_invalid",
            process_id if type(process_id) is int else None,
            port if type(port) is int else None,
        )
    return _ResolvedRhinoTarget(process_id=process_id, port=port)


def _require_status(
    result: object,
    *,
    previous_document_id: str | None,
) -> str:
    if type(result) is not dict or result.get("success") is not True:
        raise ValueError("status rejected")
    data = result.get("data")
    if type(data) is not dict:
        raise ValueError("status data rejected")
    document_id = data.get("document_id")
    object_count = data.get("object_count")
    if (
        data.get("available") is not True
        or data.get("ready_for_edit") is not True
        or data.get("has_active_document") is not True
        or type(document_id) is not str
        or not document_id.strip()
        or type(object_count) is not int
        or object_count != 0
        or type(data.get("document_path")) is not str
        or data.get("document_path") != ""
        or (
            previous_document_id is not None
            and document_id == previous_document_id
        )
    ):
        raise ValueError("status equations rejected")
    return document_id


def _require_document_new(result: object) -> None:
    if type(result) is not dict or result.get("success") is not True:
        raise ValueError("document new rejected")
    data = result.get("data")
    if type(data) is not dict or data.get("Created") is not True:
        raise ValueError("document new data rejected")


async def _prepare_fresh_document(
    dispatcher: ToolDispatcher,
) -> _PreparedDocument:
    pre = await dispatcher.dispatch("gh_status", {})
    pre_id = _require_status(pre, previous_document_id=None)
    created = await dispatcher.dispatch("gh_document_new", {})
    _require_document_new(created)
    post = await dispatcher.dispatch("gh_status", {})
    _require_status(post, previous_document_id=pre_id)
    return _PreparedDocument(
        state="fresh_document_verified",
        tool_calls=3,
    )


class _RestrictedRealToolExecutor:
    __slots__ = ("_dispatch", "_calls")

    def __init__(self, dispatch: Any) -> None:
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")
        self._dispatch = dispatch
        self._calls: list[str] = []

    @property
    def call_names(self) -> tuple[str, ...]:
        return tuple(self._calls)

    async def __call__(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        if type(tool_name) is not str or type(params) is not dict:
            raise TypeError("restricted tool call shape differs")
        if "port" in params:
            raise ValueError("restricted tool parameters contain port")
        expected = (
            "gh_create_csharp_script"
            if not self._calls
            else "gh_update_script"
            if self._calls == ["gh_create_csharp_script"]
            else None
        )
        if expected is None or tool_name != expected:
            raise ValueError("restricted tool sequence differs")
        self._calls.append(tool_name)
        result = self._dispatch(tool_name, params)
        if hasattr(result, "__await__"):
            result = await result
        if type(result) is not dict:
            raise TypeError("dispatcher result must be an exact object")
        return result


@dataclass(frozen=True, slots=True)
class _LiveRun:
    result: MinimalIntentWorkerIntegrationResult
    target: _ResolvedRhinoTarget
    preparation: _PreparedDocument
    executor: _RestrictedRealToolExecutor


async def _run_live_once(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
) -> _LiveRun:
    dispatcher = ToolDispatcher(
        port=target.port,
        local_tools=build_local_tools(),
    )
    preparation = await _prepare_fresh_document(dispatcher)

    planner_transport = LiteLLMWorkerTransport(
        model=roles.planner_model,
        profile_api_base=roles.profile_api_base,
        generation_params={
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "max_retries": _MAX_RETRIES,
            "response_format": _planner_response_format(),
        },
        structured_response_schema=None,
        timeout_s=_TIMEOUT_S,
    )
    worker_transport = LiteLLMWorkerTransport(
        model=roles.worker_model,
        profile_api_base=roles.profile_api_base,
        generation_params={
            "temperature": 0,
            "max_tokens": _MAX_OUTPUT_TOKENS,
            "max_retries": _MAX_RETRIES,
        },
        structured_response_schema=_local_worker_response_union_schema(),
        timeout_s=_TIMEOUT_S,
    )
    executor = _RestrictedRealToolExecutor(dispatcher.dispatch)
    result = await run_minimal_intent_worker_integration(
        _FIXED_INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=executor,
    )
    return _LiveRun(
        result=result,
        target=target,
        preparation=preparation,
        executor=executor,
    )


def _summary_from_result(
    roles: _ResolvedRoles,
    live_run: _LiveRun,
) -> dict[str, object]:
    result = live_run.result
    handoff = result.handoff_result
    worker_status = (
        handoff.adapter_record.status
        if handoff is not None and handoff.adapter_record is not None
        else None
    )
    completed = (
        live_run.preparation.state == "fresh_document_verified"
        and live_run.executor.call_names
        == ("gh_create_csharp_script", "gh_update_script")
        and result.terminal_stage == "terminal"
        and result.terminal_reason == "terminal_node_selected:done"
    )
    return {
        "operator_status": "completed" if completed else "failed",
        "operator_reason": "native_terminal" if completed else "native_stop",
        "intent": _FIXED_INTENT,
        "profile": roles.profile,
        "planner_model": roles.planner_model,
        "worker_model": roles.worker_model,
        "rooknative_process_id": live_run.target.process_id,
        "rooknative_port": live_run.target.port,
        "document_preparation_status": live_run.preparation.state,
        "preparation_tool_calls": live_run.preparation.tool_calls,
        "planner_calls": 1,
        "worker_calls": int(
            handoff is not None and handoff.adapter_record is not None
        ),
        "execution_tool_calls": len(live_run.executor.call_names),
        "terminal_stage": result.terminal_stage,
        "terminal_reason": (
            result.terminal_reason if completed else "native_reason_unclassified"
        ),
        "planner_adapter_status": result.planner_adapter_record.status,
        "worker_adapter_status": worker_status,
    }
