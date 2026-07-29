#!/usr/bin/env python
"""Operator-only model-composition smoke for the minimal C# repair handoff."""

from __future__ import annotations

import re
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
_MAX_BODY_UTF8_BYTES = 128
_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_FAKE_COMPONENT_GUID = "minimal-intent-model-smoke-component-guid"
_INITIAL_BODY_PATTERN = re.compile(
    r"[ \t]*A[ \t]*=[ \t]*(?P<identifier>[A-Za-z_][A-Za-z0-9_]*)[ \t]*;[ \t]*",
    re.ASCII,
)
_UPDATE_BODY_PATTERN = re.compile(
    r"[ \t]*A[ \t]*=[ \t]*-?(?:0|[1-9][0-9]{0,8})"
    r"(?:\.[0-9]{1,16})?[dD]?[ \t]*;[ \t]*",
    re.ASCII,
)
_SUMMARY_FIELDS = (
    "operator_status",
    "operator_reason",
    "intent",
    "profile",
    "planner_model",
    "worker_model",
    "planner_calls",
    "worker_calls",
    "tool_calls",
    "terminal_stage",
    "terminal_reason",
    "planner_adapter_status",
    "worker_adapter_status",
)


@dataclass(frozen=True, slots=True)
class _ResolvedRoles:
    profile: str
    planner_model: str
    worker_model: str
    profile_api_base: str | None


@dataclass(frozen=True, slots=True)
class _LiveRun:
    result: MinimalIntentWorkerIntegrationResult
    executor: _CausalFakeToolExecutor


_ArgumentDecision = Literal[
    "live_execution_not_requested",
    "invalid_arguments",
    "execute_live",
]


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


class _SyntheticToolContractError(ValueError):
    pass


def _classify_arguments(argv: Sequence[str]) -> _ArgumentDecision:
    supplied = list(argv)
    if supplied == []:
        return "live_execution_not_requested"
    if supplied == [_LIVE_FLAG]:
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


def _diagnostic_for_initial_body(body: str) -> str:
    match = _INITIAL_BODY_PATTERN.fullmatch(body)
    if match is None:
        raise ValueError("initial body does not contain one missing identifier")
    identifier = match.group("identifier")
    return f"CS0103: The name '{identifier}' does not exist in the current context."


class _CausalFakeToolExecutor:
    def __init__(self) -> None:
        self.contract_failed = False
        self._call_markers: list[None] = []
        self._issued_guid: str | None = None

    @property
    def tool_call_count(self) -> int:
        return len(self._call_markers)

    def _fail(self) -> None:
        self.contract_failed = True
        raise _SyntheticToolContractError("synthetic tool contract rejected")

    def __call__(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        self._call_markers.append(None)
        if len(self._call_markers) == 1:
            return self._create(tool_name, params)
        if len(self._call_markers) == 2:
            return self._update(tool_name, params)
        self._fail()

    def _create(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        expected = {
            "code": _INITIAL_BODY,
            "pins_in": (),
            "pins_out": ("A:double",),
            "name": "RookMinimalRepairHandoff",
            "x": 375,
            "y": 1080,
        }
        if type(params) is not dict or tool_name != "gh_create_csharp_script":
            self._fail()
        if params != expected:
            self._fail()
        try:
            diagnostic = _diagnostic_for_initial_body(params["code"])
        except (TypeError, ValueError):
            self._fail()
        self._issued_guid = _FAKE_COMPONENT_GUID
        return {
            "success": False,
            "data": {
                "script_receipt": {
                    "version": 1,
                    "operation": "create",
                    "language": "csharp",
                    "artifact_status": "created_with_errors",
                    "mutation": {
                        "status": "created",
                        "component_guid": self._issued_guid,
                    },
                    "verification": {
                        "status": "failed",
                        "target_error_count": 1,
                    },
                    "repair_anchor": {
                        "component_guid": self._issued_guid,
                        "language": "csharp",
                        "target_errors": [diagnostic],
                    },
                }
            },
        }

    def _update(self, tool_name: str, params: dict[str, Any]) -> dict[str, Any]:
        if type(params) is not dict or tool_name != "gh_update_script":
            self._fail()
        if set(params) != {"guid", "code", "mode", "language"}:
            self._fail()
        if (
            params["guid"] != self._issued_guid
            or params["mode"] != "body"
            or params["language"] != "csharp"
        ):
            self._fail()
        code = params["code"]
        if type(code) is not str or not code.isascii():
            self._fail()
        if len(code.encode("utf-8")) > _MAX_BODY_UTF8_BYTES:
            self._fail()
        if _UPDATE_BODY_PATTERN.fullmatch(code) is None:
            self._fail()
        return {
            "script_receipt": {
                "version": 1,
                "operation": "update",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {
                    "status": "written",
                    "component_guid": self._issued_guid,
                },
                "verification": {
                    "status": "passed",
                    "target_error_count": 0,
                },
                "repair_anchor": {
                    "component_guid": self._issued_guid,
                    "language": "csharp",
                    "target_errors": [],
                },
            }
        }


async def _run_live_once(roles: _ResolvedRoles) -> _LiveRun:
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
    executor = _CausalFakeToolExecutor()
    result = await run_minimal_intent_worker_integration(
        _FIXED_INTENT,
        planner_adapter=MinimalPlannerDraftAdapter(planner_transport),
        worker_transport=worker_transport,
        tool_executor=executor,
    )
    return _LiveRun(result=result, executor=executor)


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
    if live_run.executor.contract_failed:
        status, reason = "failed", "synthetic_tool_contract_failure"
    elif (
        result.terminal_stage == "terminal"
        and result.terminal_reason == "terminal_node_selected:done"
    ):
        status, reason = "completed", "native_terminal"
    else:
        status, reason = "failed", "native_stop"
    summary: dict[str, object] = {
        "operator_status": status,
        "operator_reason": reason,
        "intent": _FIXED_INTENT,
        "profile": roles.profile,
        "planner_model": roles.planner_model,
        "worker_model": roles.worker_model,
        "planner_calls": 1,
        "worker_calls": int(
            handoff is not None and handoff.adapter_record is not None
        ),
        "tool_calls": live_run.executor.tool_call_count,
        "terminal_stage": result.terminal_stage,
        "terminal_reason": result.terminal_reason,
        "planner_adapter_status": result.planner_adapter_record.status,
        "worker_adapter_status": worker_status,
    }
    if tuple(summary) != _SUMMARY_FIELDS:
        raise RuntimeError("operator summary fields differ")
    return summary
