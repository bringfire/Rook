#!/usr/bin/env python
"""Operator-only real Grasshopper compile smoke for the minimal handoff."""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO, Literal, NoReturn

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
from rook.agent.minimal_csharp_repair_handoff import (  # noqa: E402
    MinimalCSharpRepairHandoffResult,
)
from rook.agent.model_profiles import get_models  # noqa: E402
from rook.agent.tool_dispatcher import (  # noqa: E402
    ToolDispatcher,
    build_local_tools,
)
from rook.bridge import discover_instances  # noqa: E402, F401
from rook.learning.plan_graph import PlanGraph, runnable_nodes  # noqa: E402


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
_TRACE_ROW_MAX_BYTES = 256 * 1024
_TRACE_TOTAL_MAX_BYTES = 4 * 1024 * 1024
_TRACE_REJECTION_RESERVE_BYTES = 4 * 1024
_TRACE_NORMAL_MAX_BYTES = (
    _TRACE_TOTAL_MAX_BYTES - _TRACE_REJECTION_RESERVE_BYTES
)
_TRACE_EXCEPTION_MESSAGE_MAX_JSON_BYTES = 16 * 1024
_TRACE_EVENTS = frozenset(
    {
        "run_started",
        "tool_request",
        "tool_response",
        "tool_exception",
        "planner_request",
        "planner_response",
        "planner_exception",
        "worker_request",
        "worker_response",
        "worker_exception",
        "planner_admission",
        "compiled_workflow",
        "native_step_projection",
        "final_native_result",
        "handoff_raised",
        "event_rejected",
        "event_serialization_failed",
        "run_finished",
    }
)
_TRACE_REJECTION_EVENTS = {
    "json_serialization_failed": "event_serialization_failed",
    "row_size_exceeded": "event_rejected",
    "total_size_exceeded": "event_rejected",
    "exception_message_size_exceeded": "event_rejected",
}
_SUMMARY_FIELDS = (
    "operator_status",
    "operator_reason",
    "trace_path",
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


class _TraceWriteFailure(RuntimeError):
    def __init__(self, reason: str, path: Path | None) -> None:
        super().__init__("trace_write_failed")
        self.reason = reason
        self.path = path


class _JsonlFlightRecorder:
    def __init__(
        self,
        *,
        path: Path,
        stream: BinaryIO,
        clock: Callable[[], datetime],
    ) -> None:
        self._path = path
        self._stream = stream
        self._clock = clock
        self._bytes_written = 0
        self._sequence = 0
        self._failed = False
        self._closed = False
        self._close_attempted = False

    @property
    def path(self) -> Path:
        return self._path

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def sequence(self) -> int:
        return self._sequence

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def closed(self) -> bool:
        return self._closed

    def record(self, event: str, payload: Mapping[str, Any]) -> None:
        self._require_writable()
        if type(event) is not str or event not in _TRACE_EVENTS:
            raise ValueError("trace event is not in the closed vocabulary")
        next_sequence = self._sequence + 1
        try:
            row = self._serialize_row(next_sequence, event, payload)
        except Exception:
            self._reject(event, "json_serialization_failed")
        if len(row) > _TRACE_ROW_MAX_BYTES:
            self._reject(event, "row_size_exceeded")
        if self._bytes_written + len(row) > _TRACE_NORMAL_MAX_BYTES:
            self._reject(event, "total_size_exceeded")
        self._write_complete_row(row, next_sequence)

    def record_exception(
        self,
        event: str,
        payload: Mapping[str, Any],
        exc: Exception,
    ) -> None:
        self._require_writable()
        try:
            message = str(exc)
        except Exception:
            self._reject(event, "json_serialization_failed")
        try:
            encoded_message = json.dumps(
                message,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except Exception:
            self._reject(event, "json_serialization_failed")
        if len(encoded_message) > _TRACE_EXCEPTION_MESSAGE_MAX_JSON_BYTES:
            self._reject(event, "exception_message_size_exceeded")
        exception_payload = dict(payload)
        exception_payload.update(
            {
                "exception_type": type(exc).__name__,
                "exception_message": message,
            }
        )
        self.record(event, exception_payload)

    def finish(self, payload: Mapping[str, Any]) -> None:
        self.record("run_finished", payload)
        self._close()

    def close_incomplete(self) -> None:
        if self._close_attempted:
            return
        self._close()

    def _require_writable(self) -> None:
        if self._failed:
            raise _TraceWriteFailure("recorder_failed", self._path)
        if self._closed:
            raise _TraceWriteFailure("recorder_closed", self._path)

    def _serialize_row(
        self,
        sequence: int,
        event: str,
        payload: Mapping[str, Any],
    ) -> bytes:
        recorded_at = self._clock().astimezone(timezone.utc)
        return (
            json.dumps(
                {
                    "sequence": sequence,
                    "recorded_at_utc": recorded_at.strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ"
                    ),
                    "event": event,
                    "payload": payload,
                },
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")

    def _write_complete_row(self, row: bytes, sequence: int) -> None:
        try:
            written = self._stream.write(row)
        except Exception:
            self._failed = True
            raise _TraceWriteFailure("write_failed", self._path) from None
        if type(written) is not int or written < 0:
            self._failed = True
            raise _TraceWriteFailure("invalid_write_count", self._path)
        self._bytes_written += written
        if written != len(row):
            self._failed = True
            raise _TraceWriteFailure("short_write", self._path)
        try:
            self._stream.flush()
        except Exception:
            self._failed = True
            raise _TraceWriteFailure("flush_failed", self._path) from None
        self._sequence = sequence

    def _reject(self, attempted_event: str, reason: str) -> NoReturn:
        rejection_event = _TRACE_REJECTION_EVENTS[reason]
        next_sequence = self._sequence + 1
        try:
            row = self._serialize_row(
                next_sequence,
                rejection_event,
                {
                    "attempted_event": attempted_event,
                    "rejection_reason": reason,
                },
            )
        except Exception:
            self._failed = True
            raise _TraceWriteFailure(
                "rejection_serialization_failed",
                self._path,
            ) from None
        if len(row) > _TRACE_REJECTION_RESERVE_BYTES:
            self._failed = True
            raise _TraceWriteFailure("rejection_row_size_exceeded", self._path)
        if self._bytes_written + len(row) > _TRACE_TOTAL_MAX_BYTES:
            self._failed = True
            raise _TraceWriteFailure("rejection_total_size_exceeded", self._path)
        self._write_complete_row(row, next_sequence)
        self._failed = True
        raise _TraceWriteFailure(reason, self._path)

    def _close(self) -> None:
        if self._close_attempted:
            return
        self._close_attempted = True
        try:
            self._stream.close()
        except Exception:
            self._failed = True
            raise _TraceWriteFailure("close_failed", self._path) from None
        self._closed = True


def _open_live_flight_recorder() -> _JsonlFlightRecorder:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if type(local_app_data) is not str or not local_app_data.strip():
        raise _TraceWriteFailure("localappdata_missing", None)
    trace_directory = Path(local_app_data) / "Rook" / "traces"
    try:
        trace_directory.mkdir(parents=True, exist_ok=True)
    except Exception:
        raise _TraceWriteFailure("trace_directory_create_failed", None) from None
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        filename = (
            f"minimal-intent-worker-real-compile-{stamp}-"
            f"p{os.getpid()}-{secrets.token_hex(4)}.jsonl"
        )
        path = (trace_directory / filename).resolve()
    except Exception:
        raise _TraceWriteFailure("trace_path_prepare_failed", None) from None
    try:
        stream = path.open("xb", buffering=0)
    except Exception:
        raise _TraceWriteFailure("exclusive_open_failed", None) from None
    return _JsonlFlightRecorder(
        path=path,
        stream=stream,
        clock=lambda: datetime.now(timezone.utc),
    )


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


@dataclass(slots=True)
class _LiveCallCounts:
    preparation: int = 0
    planner: int = 0
    worker: int = 0
    execution: int = 0


def _project_planner_admission(
    result: MinimalIntentWorkerIntegrationResult,
) -> dict[str, object]:
    draft = result.validated_draft
    if draft is None:
        raise ValueError("Planner admission requires an admitted draft")
    return {
        "adapter_status": result.planner_adapter_record.status,
        "draft": {
            "goal": draft.goal,
            "capability": draft.capability,
            "interface": {
                "inputs": list(draft.interface.inputs),
                "outputs": [
                    {"name": output.name, "type": output.type}
                    for output in draft.interface.outputs
                ],
            },
            "acceptance": draft.acceptance,
        },
    }


def _project_compiled_workflow(
    result: MinimalCSharpRepairHandoffResult,
) -> dict[str, object]:
    scaffold = result.scaffold
    record = scaffold.compile_record
    if scaffold.workflow_id != record.workflow_id:
        raise ValueError("compiled scaffold workflow identity differs")
    if tuple(sorted(scaffold.graph.nodes)) != record.graph_node_ids:
        raise ValueError("compiled scaffold graph nodes differ")
    if scaffold.max_steps != record.max_steps:
        raise ValueError("compiled scaffold maximum steps differ")
    return {
        "workflow_id": record.workflow_id,
        "compiler_id": record.compiler_id,
        "contract_schema": record.contract_schema,
        "contract_fingerprint_algorithm": record.contract_fingerprint_algorithm,
        "contract_fingerprint": record.contract_fingerprint,
        "provider_id": record.provider_id,
        "expected_template_id": record.expected_template_id,
        "selected_template_id": record.selected_template_id,
        "graph_node_ids": list(record.graph_node_ids),
        "initial_param_node_ids": list(record.initial_param_node_ids),
        "rule_node_ids": list(record.rule_node_ids),
        "terminal_node_ids": list(record.terminal_node_ids),
        "expected_refs": [list(item) for item in record.expected_refs],
        "step_kinds_by_rule": [
            [rule_id, list(step_kinds)]
            for rule_id, step_kinds in record.step_kinds_by_rule
        ],
        "max_steps": record.max_steps,
    }


def _project_graph_state(graph: PlanGraph) -> dict[str, object]:
    if type(graph) is not PlanGraph:
        raise TypeError("graph must be the exact PlanGraph type")
    return {
        "node_statuses": [
            {"node_id": node_id, "status": graph.nodes[node_id].status}
            for node_id in sorted(graph.nodes)
        ],
        "ready_node_ids": sorted(node.id for node in runnable_nodes(graph)),
    }


def _project_native_steps(
    result: MinimalCSharpRepairHandoffResult,
) -> tuple[dict[str, object], ...]:
    records = result.step_records
    supplies = result.supply_records
    if len(supplies) not in {len(records), len(records) + 1}:
        raise ValueError("native record and supply lengths differ")
    projected: list[dict[str, object]] = []
    for index, record in enumerate(records):
        supply = supplies[index]
        if (
            supply.decision != "SUPPLY"
            or supply.envelope is None
            or supply.envelope.mapping is not record.mapping
        ):
            raise ValueError("native step lacks its owning supply")
        graph = record.execution.graph
        if type(graph) is not PlanGraph:
            raise TypeError("native execution graph must be exact")
        evidence_node_id: str | None = None
        if record.execution_kind == "producer":
            evidence_node_id = record.producer_node_id
        elif record.execution_kind == "verifier":
            evidence_node_id = record.verifier_source_node_id
        node = (
            graph.nodes.get(evidence_node_id)
            if evidence_node_id is not None
            else None
        )
        evidence = None if node is None else node.evidence
        receipt = None if evidence is None else evidence.receipt
        projected.append(
            {
                "step_index": index + 1,
                "accepted_node_id": record.accepted_node_id,
                "execution_kind": record.execution_kind,
                "ran": record.ran,
                "execution_failure": record.execution_failure,
                "producer_applied": record.producer_applied,
                "producer_outcome_status": record.producer_outcome_status,
                "producer_reason": record.producer_reason,
                "verifier_applied": record.verifier_applied,
                "verifier_outcome_status": record.verifier_outcome_status,
                "verifier_reason": record.verifier_reason,
                "receipt": receipt,
                "graph": _project_graph_state(graph),
                "supply": {
                    "decision": supply.decision,
                    "reason": supply.reason,
                },
            }
        )
    return tuple(projected)


def _project_final_native_result(
    integration: MinimalIntentWorkerIntegrationResult,
    call_counts: _LiveCallCounts,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "terminal_stage": integration.terminal_stage,
        "terminal_reason": integration.terminal_reason,
        "call_counts": {
            "preparation": call_counts.preparation,
            "planner": call_counts.planner,
            "worker": call_counts.worker,
            "execution": call_counts.execution,
        },
    }
    handoff = integration.handoff_result
    if handoff is None:
        return payload
    payload["graph"] = _project_graph_state(handoff.final_graph)
    if handoff.adapter_record is not None:
        payload["worker_adapter_status"] = handoff.adapter_record.status
    tail = handoff.supply_records[len(handoff.step_records) :]
    if len(tail) > 1:
        raise ValueError("native result has multiple control supplies")
    if tail:
        payload["terminal_supply"] = {
            "decision": tail[0].decision,
            "reason": tail[0].reason,
        }
    return payload


def _record_returned_projections(
    recorder: _JsonlFlightRecorder,
    integration: MinimalIntentWorkerIntegrationResult,
    call_counts: _LiveCallCounts,
) -> None:
    if integration.validated_draft is not None:
        recorder.record(
            "planner_admission",
            _project_planner_admission(integration),
        )
    handoff = integration.handoff_result
    if handoff is not None:
        recorder.record(
            "compiled_workflow",
            _project_compiled_workflow(handoff),
        )
        for step in _project_native_steps(handoff):
            recorder.record("native_step_projection", step)
    recorder.record(
        "final_native_result",
        _project_final_native_result(integration, call_counts),
    )


class _RecordingPreparationDispatcher:
    __slots__ = ("_counts", "_delegate", "_recorder")

    def __init__(
        self,
        *,
        delegate: Any,
        recorder: _JsonlFlightRecorder,
        counts: _LiveCallCounts,
    ) -> None:
        if not callable(getattr(delegate, "dispatch", None)):
            raise TypeError("preparation delegate must expose dispatch")
        if type(recorder) is not _JsonlFlightRecorder:
            raise TypeError("recorder must be the exact flight recorder")
        if type(counts) is not _LiveCallCounts:
            raise TypeError("counts must be the exact live call counts")
        self._delegate = delegate
        self._recorder = recorder
        self._counts = counts

    async def dispatch(
        self,
        tool_name: str,
        params: dict[str, Any],
    ) -> Any:
        call_index = self._counts.preparation + 1
        common = {
            "phase": "preparation",
            "call_index": call_index,
            "tool_name": tool_name,
        }
        self._recorder.record(
            "tool_request",
            {**common, "params": params},
        )
        self._counts.preparation = call_index
        try:
            response = await self._delegate.dispatch(tool_name, params)
        except Exception as exc:
            self._recorder.record_exception("tool_exception", common, exc)
            raise
        self._recorder.record(
            "tool_response",
            {**common, "raw_response": response},
        )
        return response


class _RecordingModelTransport:
    __slots__ = ("_counts", "_delegate", "_recorder", "_role")

    def __init__(
        self,
        *,
        role: Literal["planner", "worker"],
        delegate: Any,
        recorder: _JsonlFlightRecorder,
        counts: _LiveCallCounts,
    ) -> None:
        if type(role) is not str or role not in {"planner", "worker"}:
            raise ValueError("recording model role differs")
        if not callable(getattr(delegate, "send", None)):
            raise TypeError("model delegate must expose send")
        if type(recorder) is not _JsonlFlightRecorder:
            raise TypeError("recorder must be the exact flight recorder")
        if type(counts) is not _LiveCallCounts:
            raise TypeError("counts must be the exact live call counts")
        self._role = role
        self._delegate = delegate
        self._recorder = recorder
        self._counts = counts

    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        previous_count = (
            self._counts.planner
            if self._role == "planner"
            else self._counts.worker
        )
        call_index = previous_count + 1
        common = {"role": self._role, "call_index": call_index}
        self._recorder.record(
            f"{self._role}_request",
            {**common, "prompt_artifact": prompt_artifact},
        )
        if self._role == "planner":
            self._counts.planner = call_index
        else:
            self._counts.worker = call_index
        try:
            response = self._delegate.send(prompt_artifact)
        except Exception as exc:
            self._recorder.record_exception(
                f"{self._role}_exception",
                common,
                exc,
            )
            raise
        self._recorder.record(
            f"{self._role}_response",
            {**common, "raw_response": response},
        )
        return response


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


class _PreparationTraceFailure(RuntimeError):
    def __init__(
        self,
        trace_failure: _TraceWriteFailure,
        state: _PreparationState,
        tool_calls: int,
    ) -> None:
        super().__init__("trace_write_failed")
        self.trace_failure = trace_failure
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


class _PostPreparationTraceFailure(RuntimeError):
    def __init__(
        self,
        trace_failure: _TraceWriteFailure,
        target: _ResolvedRhinoTarget,
        preparation: _PreparedDocument,
    ) -> None:
        super().__init__("trace_write_failed")
        self.trace_failure = trace_failure
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
    dispatcher: Any,
    *,
    call_counts: _LiveCallCounts | None = None,
) -> _PreparedDocument:
    preparation_state: _PreparationState = "not_started"
    tool_calls = 1
    try:
        pre = await dispatcher.dispatch("gh_status", {})
    except _TraceWriteFailure as exc:
        entered_calls = (
            call_counts.preparation if call_counts is not None else 0
        )
        raise _PreparationTraceFailure(
            exc,
            "not_started" if entered_calls == 0 else "status_rejected",
            entered_calls,
        ) from exc
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
    except _TraceWriteFailure as exc:
        state: _PreparationState = (
            "document_new_started"
            if call_counts is not None and call_counts.preparation >= 2
            else "status_verified"
        )
        raise _PreparationTraceFailure(
            exc,
            state,
            call_counts.preparation if call_counts is not None else 1,
        ) from exc
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
    except _TraceWriteFailure as exc:
        raise _PreparationTraceFailure(
            exc,
            "document_new_started",
            call_counts.preparation if call_counts is not None else 2,
        ) from exc
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
    __slots__ = ("_calls", "_counts", "_dispatch", "_recorder")

    def __init__(
        self,
        dispatch: Any,
        *,
        recorder: _JsonlFlightRecorder | None = None,
        counts: _LiveCallCounts | None = None,
    ) -> None:
        if not callable(dispatch):
            raise TypeError("dispatch must be callable")
        if (recorder is None) != (counts is None):
            raise TypeError("recorder and counts must be supplied together")
        if recorder is not None and type(recorder) is not _JsonlFlightRecorder:
            raise TypeError("recorder must be the exact flight recorder")
        if counts is not None and type(counts) is not _LiveCallCounts:
            raise TypeError("counts must be the exact live call counts")
        self._dispatch = dispatch
        self._recorder = recorder
        self._counts = counts
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
        common: dict[str, Any] | None = None
        if self._recorder is not None and self._counts is not None:
            call_index = self._counts.execution + 1
            common = {
                "phase": "execution",
                "call_index": call_index,
                "tool_name": tool_name,
            }
            self._recorder.record(
                "tool_request",
                {**common, "params": params},
            )
            self._counts.execution = call_index
        self._calls.append(tool_name)
        try:
            result = self._dispatch(tool_name, params)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as exc:
            if self._recorder is not None and common is not None:
                self._recorder.record_exception("tool_exception", common, exc)
            raise
        if self._recorder is not None and common is not None:
            self._recorder.record(
                "tool_response",
                {**common, "raw_response": result},
            )
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
    *,
    recorder: _JsonlFlightRecorder,
    call_counts: _LiveCallCounts,
) -> _LiveRun:
    dispatcher = ToolDispatcher(
        port=target.port,
        local_tools=build_local_tools(),
    )
    recording_preparation = _RecordingPreparationDispatcher(
        delegate=dispatcher,
        recorder=recorder,
        counts=call_counts,
    )
    preparation = await _prepare_fresh_document(
        recording_preparation,
        call_counts=call_counts,
    )

    try:
        return await _run_prepared_once(
            roles,
            target,
            dispatcher,
            preparation,
            recorder=recorder,
            call_counts=call_counts,
        )
    except _TraceWriteFailure as exc:
        raise _PostPreparationTraceFailure(
            exc,
            target,
            preparation,
        ) from exc
    except Exception as exc:
        raise _PostPreparationFailure(target, preparation) from exc


async def _run_prepared_once(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    dispatcher: ToolDispatcher,
    preparation: _PreparedDocument,
    *,
    recorder: _JsonlFlightRecorder,
    call_counts: _LiveCallCounts,
) -> _LiveRun:

    planner_delegate = LiteLLMWorkerTransport(
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
    worker_delegate = LiteLLMWorkerTransport(
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
    planner_transport = _RecordingModelTransport(
        role="planner",
        delegate=planner_delegate,
        recorder=recorder,
        counts=call_counts,
    )
    worker_transport = _RecordingModelTransport(
        role="worker",
        delegate=worker_delegate,
        recorder=recorder,
        counts=call_counts,
    )
    executor = _RestrictedRealToolExecutor(
        dispatcher.dispatch,
        recorder=recorder,
        counts=call_counts,
    )
    planner_adapter = MinimalPlannerDraftAdapter(planner_transport)
    try:
        result = await run_minimal_intent_worker_integration(
            _FIXED_INTENT,
            planner_adapter=planner_adapter,
            worker_transport=worker_transport,
            tool_executor=executor,
        )
    except _TraceWriteFailure:
        raise
    except Exception as exc:
        recorder.record_exception(
            "handoff_raised",
            {"phase": "integration"},
            exc,
        )
        raise
    if recorder.failed:
        raise _TraceWriteFailure("recorder_failed", recorder.path)
    return _LiveRun(
        result=result,
        target=target,
        preparation=preparation,
        executor=executor,
    )


def _summary_from_result(
    roles: _ResolvedRoles,
    live_run: _LiveRun,
    *,
    trace_path: Path | None = None,
    call_counts: _LiveCallCounts | None = None,
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
        "trace_path": str(trace_path) if trace_path is not None else None,
        "intent": _FIXED_INTENT,
        "profile": roles.profile,
        "planner_model": roles.planner_model,
        "worker_model": roles.worker_model,
        "rooknative_process_id": live_run.target.process_id,
        "rooknative_port": live_run.target.port,
        "document_preparation_status": live_run.preparation.state,
        "preparation_tool_calls": (
            call_counts.preparation
            if call_counts is not None
            else live_run.preparation.tool_calls
        ),
        "planner_calls": call_counts.planner if call_counts is not None else 1,
        "worker_calls": (
            call_counts.worker
            if call_counts is not None
            else int(handoff is not None and handoff.adapter_record is not None)
        ),
        "execution_tool_calls": (
            call_counts.execution
            if call_counts is not None
            else len(execution_prefix)
        ),
        "terminal_stage": result.terminal_stage,
        "terminal_reason": _project_terminal_reason(result.terminal_reason),
        "planner_adapter_status": result.planner_adapter_record.status,
        "worker_adapter_status": worker_status,
    }


def _bounded_summary(
    *,
    operator_status: str,
    operator_reason: str,
    trace_path: Path | None = None,
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
        "trace_path": str(trace_path) if trace_path is not None else None,
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


def _profile_refusal_summary(
    exc: _ProfileRefusal,
    *,
    trace_path: Path | None = None,
) -> dict[str, object]:
    summary = _bounded_summary(
        operator_status="refused",
        operator_reason=exc.reason,
        trace_path=trace_path,
    )
    summary["planner_model"] = exc.planner_model
    summary["worker_model"] = exc.worker_model
    return summary


def _preparation_failure_summary(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    exc: _PreparationFailure,
    *,
    trace_path: Path | None = None,
) -> dict[str, object]:
    return _bounded_summary(
        operator_status="preparation_failed",
        operator_reason=exc.reason,
        trace_path=trace_path,
        roles=roles,
        target=target,
        preparation_state=exc.state,
        preparation_tool_calls=exc.tool_calls,
    )


def _post_preparation_failure_summary(
    roles: _ResolvedRoles,
    exc: _PostPreparationFailure,
    *,
    trace_path: Path | None = None,
) -> dict[str, object]:
    return _verified_preparation_internal_error_summary(
        roles,
        exc.target,
        exc.preparation,
        trace_path=trace_path,
    )


def _verified_preparation_internal_error_summary(
    roles: _ResolvedRoles,
    target: _ResolvedRhinoTarget,
    preparation: _PreparedDocument,
    *,
    trace_path: Path | None = None,
) -> dict[str, object]:
    return _bounded_summary(
        operator_status="failed",
        operator_reason="operator_internal_error",
        trace_path=trace_path,
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
    *,
    trace_path: Path | None = None,
) -> dict[str, object]:
    return _bounded_summary(
        operator_status="failed",
        operator_reason="operator_internal_error",
        trace_path=trace_path,
        roles=roles,
        target=target,
        planner_calls=None,
        worker_calls=None,
        execution_tool_calls=None,
    )


def _run_finished_payload(
    summary: Mapping[str, object],
) -> dict[str, object]:
    return {
        "operator_status": summary["operator_status"],
        "operator_reason": summary["operator_reason"],
        "document_preparation_status": summary[
            "document_preparation_status"
        ],
        "preparation_tool_calls": summary["preparation_tool_calls"],
        "planner_calls": summary["planner_calls"],
        "worker_calls": summary["worker_calls"],
        "execution_tool_calls": summary["execution_tool_calls"],
    }


def _trace_write_failure_summary(
    *,
    trace_path: Path | None,
    roles: _ResolvedRoles | None = None,
    target: _ResolvedRhinoTarget | None = None,
    preparation_status: _PreparationState = "not_started",
    call_counts: _LiveCallCounts | None = None,
    known_native_summary: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if known_native_summary is None:
        summary = _bounded_summary(
            operator_status="failed",
            operator_reason="trace_write_failed",
            trace_path=trace_path,
            roles=roles,
            target=target,
            preparation_state=preparation_status,
            preparation_tool_calls=(
                call_counts.preparation if call_counts is not None else 0
            ),
            planner_calls=call_counts.planner if call_counts is not None else 0,
            worker_calls=call_counts.worker if call_counts is not None else 0,
            execution_tool_calls=(
                call_counts.execution if call_counts is not None else 0
            ),
        )
    else:
        summary = dict(known_native_summary)
        summary["operator_status"] = "failed"
        summary["operator_reason"] = "trace_write_failed"
        summary["trace_path"] = (
            str(trace_path) if trace_path is not None else None
        )
        if call_counts is not None:
            summary["preparation_tool_calls"] = call_counts.preparation
            summary["planner_calls"] = call_counts.planner
            summary["worker_calls"] = call_counts.worker
            summary["execution_tool_calls"] = call_counts.execution
    return summary


def _finish_trace_or_failure(
    recorder: _JsonlFlightRecorder,
    summary: Mapping[str, object],
    *,
    call_counts: _LiveCallCounts,
) -> dict[str, object]:
    normalized_summary = dict(summary)
    normalized_summary["preparation_tool_calls"] = call_counts.preparation
    normalized_summary["planner_calls"] = call_counts.planner
    normalized_summary["worker_calls"] = call_counts.worker
    normalized_summary["execution_tool_calls"] = call_counts.execution
    try:
        recorder.finish(_run_finished_payload(normalized_summary))
    except _TraceWriteFailure:
        _close_incomplete_trace(recorder)
        return _trace_write_failure_summary(
            trace_path=recorder.path,
            call_counts=call_counts,
            known_native_summary=normalized_summary,
        )
    return normalized_summary


def _close_incomplete_trace(recorder: _JsonlFlightRecorder) -> None:
    try:
        recorder.close_incomplete()
    except _TraceWriteFailure:
        pass


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

    recorder: _JsonlFlightRecorder | None = None
    call_counts = _LiveCallCounts()
    try:
        recorder = _open_live_flight_recorder()
        recorder.record(
            "run_started",
            {
                "intent": _FIXED_INTENT,
                "profile": _PROFILE,
                "expected_planner_model": _PLANNER_MODEL,
                "expected_worker_model": _WORKER_MODEL,
            },
        )
    except _TraceWriteFailure as exc:
        if recorder is not None:
            _close_incomplete_trace(recorder)
        _emit_summary(
            _trace_write_failure_summary(
                trace_path=exc.path,
                call_counts=call_counts,
            )
        )
        return 1

    roles: _ResolvedRoles | None = None
    target: _ResolvedRhinoTarget | None = None
    try:
        roles = _resolve_hybrid_roles()
    except _ProfileRefusal as exc:
        summary = _finish_trace_or_failure(
            recorder,
            _profile_refusal_summary(exc, trace_path=recorder.path),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1
    except Exception:
        summary = _finish_trace_or_failure(
            recorder,
            _operator_internal_error_summary(
                None,
                None,
                trace_path=recorder.path,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1

    try:
        target = _resolve_single_rhino_target(discover_instances())
    except _TargetRefusal as exc:
        summary = _finish_trace_or_failure(
            recorder,
            _bounded_summary(
                operator_status="refused",
                operator_reason=exc.reason,
                trace_path=recorder.path,
                roles=roles,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1
    except Exception:
        summary = _finish_trace_or_failure(
            recorder,
            _operator_internal_error_summary(
                roles,
                None,
                trace_path=recorder.path,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1

    try:
        live_run = asyncio.run(
            _run_live_once(
                roles,
                target,
                recorder=recorder,
                call_counts=call_counts,
            )
        )
    except _PreparationTraceFailure as exc:
        _close_incomplete_trace(recorder)
        _emit_summary(
            _trace_write_failure_summary(
                trace_path=recorder.path,
                roles=roles,
                target=target,
                preparation_status=exc.state,
                call_counts=call_counts,
            )
        )
        return 1
    except _PostPreparationTraceFailure as exc:
        _close_incomplete_trace(recorder)
        _emit_summary(
            _trace_write_failure_summary(
                trace_path=recorder.path,
                roles=roles,
                target=target,
                preparation_status=exc.preparation.state,
                call_counts=call_counts,
            )
        )
        return 1
    except _PreparationFailure as exc:
        summary = _finish_trace_or_failure(
            recorder,
            _preparation_failure_summary(
                roles,
                target,
                exc,
                trace_path=recorder.path,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1
    except _PostPreparationFailure as exc:
        summary = _finish_trace_or_failure(
            recorder,
            _post_preparation_failure_summary(
                roles,
                exc,
                trace_path=recorder.path,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1
    except Exception:
        summary = _finish_trace_or_failure(
            recorder,
            _operator_internal_error_summary(
                roles,
                target,
                trace_path=recorder.path,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1

    try:
        summary = _summary_from_result(
            roles,
            live_run,
            trace_path=recorder.path,
            call_counts=call_counts,
        )
    except Exception:
        summary = _finish_trace_or_failure(
            recorder,
            _verified_preparation_internal_error_summary(
                roles,
                live_run.target,
                live_run.preparation,
                trace_path=recorder.path,
            ),
            call_counts=call_counts,
        )
        _emit_summary(summary)
        return 1
    try:
        _record_returned_projections(
            recorder,
            live_run.result,
            call_counts,
        )
    except Exception:
        _close_incomplete_trace(recorder)
        _emit_summary(
            _trace_write_failure_summary(
                trace_path=recorder.path,
                call_counts=call_counts,
                known_native_summary=summary,
            )
        )
        return 1
    summary = _finish_trace_or_failure(
        recorder,
        summary,
        call_counts=call_counts,
    )
    _emit_summary(summary)
    return 0 if summary["operator_status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
