#!/usr/bin/env python
"""Operator-only real Grasshopper compile smoke for the minimal handoff."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
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
_SUMMARY_FIELDS = (
    "operator_status",
    "operator_reason",
    "intent",
    "profile",
    "planner_model",
    "worker_model",
    "rooknative_process_id",
    "rooknative_port",
    "document_preparation_status",
    "preparation_tool_calls",
    "planner_calls",
    "worker_calls",
    "execution_tool_calls",
    "terminal_stage",
    "terminal_reason",
    "planner_adapter_status",
    "worker_adapter_status",
)
_SAFE_TERMINAL_REASON_TOKENS = frozenset(
    {
        "clarification_needed",
        "dispatch_failed",
        "draft_payload_rejected",
        "executed verifier step 'verify_create'",
        "goal_mismatch",
        "invalid_code",
        "invalid_mode",
        "observation_recorded",
        "refusal_recorded",
        "response_duplicate_key",
        "response_invalid_json",
        "response_nonfinite_number",
        "response_not_object",
        "response_not_string",
        "response_not_utf8",
        "response_too_large",
        "response_trailing_content",
        "selector_halt:none_ready",
        "terminal_node_selected:done",
        "transport_failed",
        "unexpected_action_input_key",
    }
)
_TERMINAL_REASON_CATEGORY_PREFIXES = (
    ("transport_error:", "worker_transport_error"),
    ("raw_output_invalid:", "worker_raw_output_invalid"),
    ("response_payload_invalid:", "worker_response_payload_invalid"),
    ("blocked:", "worker_response_blocked"),
)

_ArgumentDecision = Literal[
    "live_execution_not_requested",
    "invalid_arguments",
    "execute_live",
]
_PreparationState = Literal[
    "not_started",
    "status_rejected",
    "status_verified",
    "document_new_started",
    "fresh_document_verified",
]


def _project_terminal_reason(reason: object) -> str:
    if type(reason) is not str:
        return "native_reason_unclassified"
    if reason in _SAFE_TERMINAL_REASON_TOKENS:
        return reason
    for prefix, category in _TERMINAL_REASON_CATEGORY_PREFIXES:
        if reason.startswith(prefix):
            return category
    return "native_reason_unclassified"


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


class _PreparationFailure(RuntimeError):
    def __init__(
        self,
        reason: str,
        state: Literal["status_rejected", "document_new_started"],
        tool_calls: int,
    ) -> None:
        super().__init__(reason)
        self.reason = reason
        self.state = state
        self.tool_calls = tool_calls


class _PostPreparationFailure(RuntimeError):
    def __init__(
        self,
        target: _ResolvedRhinoTarget,
        preparation: _PreparedDocument,
    ) -> None:
        super().__init__("operator_internal_error")
        self.reason = "operator_internal_error"
        self.target = target
        self.preparation = preparation


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


def _classify_arguments(argv: Sequence[str]) -> _ArgumentDecision:
    supplied = list(argv)
    if supplied == []:
        return "live_execution_not_requested"
    if (
        len(supplied) == 1
        and type(supplied[0]) is str
        and supplied[0] == _LIVE_FLAG
    ):
        return "execute_live"
    return "invalid_arguments"


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
    if type(data) is not dict or data.get("created") is not True:
        raise ValueError("document new data rejected")


async def _prepare_fresh_document(
    dispatcher: ToolDispatcher,
) -> _PreparedDocument:
    preparation_state: _PreparationState = "not_started"
    tool_calls = 1
    try:
        pre = await dispatcher.dispatch("gh_status", {})
    except Exception as exc:
        preparation_state = "status_rejected"
        raise _PreparationFailure(
            "pre_status_exception",
            preparation_state,
            tool_calls,
        ) from exc
    try:
        pre_id = _require_status(pre, previous_document_id=None)
    except (TypeError, ValueError) as exc:
        preparation_state = "status_rejected"
        raise _PreparationFailure(
            "pre_status_rejected",
            preparation_state,
            tool_calls,
        ) from exc

    preparation_state = "status_verified"
    preparation_state = "document_new_started"
    tool_calls = 2
    try:
        created = await dispatcher.dispatch("gh_document_new", {})
    except Exception as exc:
        raise _PreparationFailure(
            "document_new_exception",
            preparation_state,
            tool_calls,
        ) from exc
    try:
        _require_document_new(created)
    except (TypeError, ValueError) as exc:
        raise _PreparationFailure(
            "document_new_rejected",
            preparation_state,
            tool_calls,
        ) from exc

    tool_calls = 3
    try:
        post = await dispatcher.dispatch("gh_status", {})
    except Exception as exc:
        raise _PreparationFailure(
            "post_status_exception",
            preparation_state,
            tool_calls,
        ) from exc
    try:
        _require_status(post, previous_document_id=pre_id)
    except (TypeError, ValueError) as exc:
        raise _PreparationFailure(
            "post_status_rejected",
            preparation_state,
            tool_calls,
        ) from exc

    preparation_state = "fresh_document_verified"
    return _PreparedDocument(
        state=preparation_state,
        tool_calls=tool_calls,
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

    try:
        return await _run_prepared_once(
            roles,
            target,
            dispatcher,
            preparation,
        )
    except Exception as exc:
        raise _PostPreparationFailure(target, preparation) from exc


async def _run_prepared_once(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    dispatcher: ToolDispatcher,
    preparation: _PreparedDocument,
) -> _LiveRun:

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
    execution_prefix = live_run.executor.call_names
    native_terminal = (
        result.terminal_stage == "terminal"
        and result.terminal_reason == "terminal_node_selected:done"
    )
    if native_terminal and execution_prefix != (
        "gh_create_csharp_script",
        "gh_update_script",
    ):
        raise RuntimeError("native terminal executor prefix differs")
    completed = (
        live_run.preparation.state == "fresh_document_verified"
        and execution_prefix
        == ("gh_create_csharp_script", "gh_update_script")
        and native_terminal
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
        "execution_tool_calls": len(execution_prefix),
        "terminal_stage": result.terminal_stage,
        "terminal_reason": _project_terminal_reason(result.terminal_reason),
        "planner_adapter_status": result.planner_adapter_record.status,
        "worker_adapter_status": worker_status,
    }


def _bounded_summary(
    *,
    operator_status: str,
    operator_reason: str,
    roles: _ResolvedRoles | None = None,
    target: _ResolvedRhinoTarget | None = None,
    preparation_state: _PreparationState = "not_started",
    preparation_tool_calls: int = 0,
    planner_calls: int | None = 0,
    worker_calls: int | None = 0,
    execution_tool_calls: int | None = 0,
) -> dict[str, object]:
    return {
        "operator_status": operator_status,
        "operator_reason": operator_reason,
        "intent": _FIXED_INTENT,
        "profile": roles.profile if roles is not None else _PROFILE,
        "planner_model": roles.planner_model if roles is not None else None,
        "worker_model": roles.worker_model if roles is not None else None,
        "rooknative_process_id": (
            target.process_id if target is not None else None
        ),
        "rooknative_port": target.port if target is not None else None,
        "document_preparation_status": preparation_state,
        "preparation_tool_calls": preparation_tool_calls,
        "planner_calls": planner_calls,
        "worker_calls": worker_calls,
        "execution_tool_calls": execution_tool_calls,
        "terminal_stage": None,
        "terminal_reason": None,
        "planner_adapter_status": None,
        "worker_adapter_status": None,
    }


def _profile_refusal_summary(exc: _ProfileRefusal) -> dict[str, object]:
    summary = _bounded_summary(
        operator_status="refused",
        operator_reason=exc.reason,
    )
    summary["planner_model"] = exc.planner_model
    summary["worker_model"] = exc.worker_model
    return summary


def _preparation_failure_summary(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    exc: _PreparationFailure,
) -> dict[str, object]:
    return _bounded_summary(
        operator_status="preparation_failed",
        operator_reason=exc.reason,
        roles=roles,
        target=target,
        preparation_state=exc.state,
        preparation_tool_calls=exc.tool_calls,
    )


def _post_preparation_failure_summary(
    roles: _ResolvedRoles,
    exc: _PostPreparationFailure,
) -> dict[str, object]:
    return _verified_preparation_internal_error_summary(
        roles,
        exc.target,
        exc.preparation,
    )


def _verified_preparation_internal_error_summary(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    preparation: _PreparedDocument,
) -> dict[str, object]:
    return _bounded_summary(
        operator_status="failed",
        operator_reason="operator_internal_error",
        roles=roles,
        target=target,
        preparation_state=preparation.state,
        preparation_tool_calls=preparation.tool_calls,
        planner_calls=None,
        worker_calls=None,
        execution_tool_calls=None,
    )


def _operator_internal_error_summary(
    roles: _ResolvedRoles | None,
    target: _ResolvedRhinoTarget | None,
) -> dict[str, object]:
    return _bounded_summary(
        operator_status="failed",
        operator_reason="operator_internal_error",
        roles=roles,
        target=target,
        planner_calls=None,
        worker_calls=None,
        execution_tool_calls=None,
    )


def _emit_summary(summary: dict[str, object]) -> None:
    if tuple(summary) != _SUMMARY_FIELDS:
        raise RuntimeError("operator summary fields differ")
    print(
        json.dumps(
            summary,
            ensure_ascii=True,
            separators=(",", ":"),
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    supplied = sys.argv[1:] if argv is None else list(argv)
    decision = _classify_arguments(supplied)
    if decision != "execute_live":
        _emit_summary(
            _bounded_summary(
                operator_status="refused",
                operator_reason=decision,
            )
        )
        return 0 if decision == "live_execution_not_requested" else 1

    roles: _ResolvedRoles | None = None
    target: _ResolvedRhinoTarget | None = None
    try:
        roles = _resolve_hybrid_roles()
    except _ProfileRefusal as exc:
        _emit_summary(_profile_refusal_summary(exc))
        return 1
    except Exception:
        _emit_summary(_operator_internal_error_summary(None, None))
        return 1

    try:
        target = _resolve_single_rhino_target(discover_instances())
    except _TargetRefusal as exc:
        _emit_summary(
            _bounded_summary(
                operator_status="refused",
                operator_reason=exc.reason,
                roles=roles,
            )
        )
        return 1
    except Exception:
        _emit_summary(_operator_internal_error_summary(roles, None))
        return 1

    try:
        live_run = asyncio.run(_run_live_once(roles, target))
    except _PreparationFailure as exc:
        _emit_summary(_preparation_failure_summary(roles, target, exc))
        return 1
    except _PostPreparationFailure as exc:
        _emit_summary(_post_preparation_failure_summary(roles, exc))
        return 1
    except Exception:
        _emit_summary(_operator_internal_error_summary(roles, target))
        return 1

    try:
        summary = _summary_from_result(roles, live_run)
        _emit_summary(summary)
    except Exception:
        _emit_summary(
            _verified_preparation_internal_error_summary(
                roles,
                live_run.target,
                live_run.preparation,
            )
        )
        return 1
    return 0 if summary["operator_status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
