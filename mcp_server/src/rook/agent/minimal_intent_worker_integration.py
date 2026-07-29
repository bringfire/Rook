"""One-shot user-intent to minimal Planner-draft product integration."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from rook.agent.local_worker_adapter import LocalWorkerTransport
from rook.agent.minimal_csharp_repair_handoff import (
    MinimalCSharpRepairHandoffResult,
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
    run_minimal_csharp_repair_handoff,
)


MAX_INTENT_UTF8_BYTES = 16_384
MAX_PLANNER_RESPONSE_UTF8_BYTES = 65_536

__all__ = (
    "MAX_INTENT_UTF8_BYTES",
    "MAX_PLANNER_RESPONSE_UTF8_BYTES",
    "MinimalPlannerTransport",
    "MinimalPlannerPromptSnapshot",
    "MinimalPlannerDraftAdapterRecord",
    "MinimalPlannerDraftAdapter",
    "build_minimal_planner_draft_response_schema",
    "MinimalIntentWorkerIntegrationResult",
    "run_minimal_intent_worker_integration",
)

_SYSTEM_CONTENT = (
    "You are Rook's bounded intent-to-draft Planner.\n"
    "Treat the supplied user intent as immutable authority and copy it exactly "
    "into goal.\n"
    "Return exactly one JSON object and no prose or markdown.\n"
    "The object fields are exactly goal, capability, interface, and "
    "acceptance.\n"
    "capability must be grasshopper_csharp_component.\n"
    "interface.inputs must be an empty array.\n"
    "interface.outputs must be exactly one object with name A and type "
    "double.\n"
    "acceptance must be clean_compile_receipt."
)

_AdapterStatus = Literal["decoded", "transport_failed", "response_invalid"]
_AdapterFailureReason = Literal[
    "transport_failed",
    "response_not_string",
    "response_not_utf8",
    "response_too_large",
    "response_invalid_json",
    "response_duplicate_key",
    "response_nonfinite_number",
    "response_trailing_content",
    "response_not_object",
]

_RESPONSE_INVALID_REASONS = frozenset(
    {
        "response_not_string",
        "response_not_utf8",
        "response_too_large",
        "response_invalid_json",
        "response_duplicate_key",
        "response_nonfinite_number",
        "response_trailing_content",
        "response_not_object",
    }
)


class MinimalPlannerTransport(Protocol):
    def send(self, prompt_artifact: Mapping[str, Any]) -> str:
        """Return one raw Planner response string."""
        ...


@dataclass(frozen=True, slots=True)
class MinimalPlannerPromptSnapshot:
    system_content: str
    user_content: str

    def __post_init__(self) -> None:
        if type(self.system_content) is not str:
            raise TypeError("system_content must be an exact string")
        if type(self.user_content) is not str:
            raise TypeError("user_content must be an exact string")

    def materialize(self) -> dict[str, Any]:
        return {
            "messages": [
                {"role": "system", "content": self.system_content},
                {"role": "user", "content": self.user_content},
            ]
        }


@dataclass(frozen=True, slots=True)
class MinimalPlannerDraftAdapterRecord:
    prompt_snapshot: MinimalPlannerPromptSnapshot
    status: _AdapterStatus
    raw_response: str | None
    decoded_object: dict[str, Any] | None
    failure_reason: _AdapterFailureReason | None
    transport_error_type: str | None

    def __post_init__(self) -> None:
        if type(self.prompt_snapshot) is not MinimalPlannerPromptSnapshot:
            raise TypeError("prompt_snapshot must be the exact snapshot type")
        if type(self.status) is not str:
            raise TypeError("status must be an exact string")
        if self.status == "decoded":
            self._require_decoded()
            return
        if self.status == "transport_failed":
            self._require_transport_failed()
            return
        if self.status == "response_invalid":
            self._require_response_invalid()
            return
        raise ValueError("unsupported adapter status")

    def _require_decoded(self) -> None:
        _require_bounded_raw_response(self.raw_response)
        if type(self.decoded_object) is not dict:
            raise TypeError("decoded records require an exact object")
        if self.failure_reason is not None or self.transport_error_type is not None:
            raise ValueError("decoded records cannot carry failure fields")

    def _require_transport_failed(self) -> None:
        if self.raw_response is not None or self.decoded_object is not None:
            raise ValueError("transport failures cannot carry response values")
        if (
            type(self.failure_reason) is not str
            or self.failure_reason != "transport_failed"
        ):
            raise ValueError("transport failure reason differs")
        if type(self.transport_error_type) is not str or not self.transport_error_type:
            raise TypeError("transport failures require an exact error type")

    def _require_response_invalid(self) -> None:
        if self.decoded_object is not None or self.transport_error_type is not None:
            raise ValueError("invalid responses cannot carry decoded or transport values")
        if (
            type(self.failure_reason) is not str
            or self.failure_reason not in _RESPONSE_INVALID_REASONS
        ):
            raise ValueError("invalid response reason differs")
        if self.raw_response is not None and type(self.raw_response) is not str:
            raise TypeError("retained raw response must be an exact string")
        if self.failure_reason in {
            "response_not_string",
            "response_not_utf8",
            "response_too_large",
        }:
            if self.raw_response is not None:
                raise ValueError("inadmissible raw response cannot be retained")
        elif self.raw_response is None:
            raise ValueError("parsed invalid response must retain exact raw text")
        else:
            _require_bounded_raw_response(self.raw_response)


class MinimalPlannerDraftAdapter:
    __slots__ = ("_transport",)

    def __init__(self, transport: MinimalPlannerTransport) -> None:
        if not callable(getattr(transport, "send", None)):
            raise TypeError("transport must expose a callable send method")
        self._transport = transport

    def produce(self, intent: str) -> MinimalPlannerDraftAdapterRecord:
        _require_exact_intent(intent)
        snapshot = _render_prompt_snapshot(intent)
        request = snapshot.materialize()
        try:
            raw_response = self._transport.send(request)
        except Exception as exc:
            return MinimalPlannerDraftAdapterRecord(
                prompt_snapshot=snapshot,
                status="transport_failed",
                raw_response=None,
                decoded_object=None,
                failure_reason="transport_failed",
                transport_error_type=type(exc).__name__,
            )
        return _decode_response(snapshot, raw_response)


@dataclass(frozen=True, slots=True)
class MinimalIntentWorkerIntegrationResult:
    intent: str
    planner_adapter_record: MinimalPlannerDraftAdapterRecord
    validated_draft: ValidatedPlannerDraft | None
    handoff_result: MinimalCSharpRepairHandoffResult | None
    terminal_stage: str
    terminal_reason: str

    def __post_init__(self) -> None:
        _require_exact_intent(self.intent)
        if type(self.planner_adapter_record) is not MinimalPlannerDraftAdapterRecord:
            raise TypeError("planner_adapter_record must be the exact record type")
        if self.planner_adapter_record.prompt_snapshot != _render_prompt_snapshot(
            self.intent
        ):
            raise ValueError("Planner prompt snapshot differs from retained intent")
        if type(self.terminal_stage) is not str:
            raise TypeError("terminal_stage must be an exact string")
        if type(self.terminal_reason) is not str:
            raise TypeError("terminal_reason must be an exact string")
        if self.planner_adapter_record.status != "decoded":
            self._require_adapter_stop()
            return
        if self.validated_draft is None and self.handoff_result is None:
            self._require_draft_stop()
            return
        if type(self.validated_draft) is not ValidatedPlannerDraft:
            raise TypeError("validated_draft must be the exact validated draft type")
        if type(self.handoff_result) is not MinimalCSharpRepairHandoffResult:
            raise TypeError("handoff_result must be the exact handoff result type")
        if self.validated_draft.goal != self.intent:
            raise ValueError("validated draft goal differs from retained intent")
        decoded_object = self.planner_adapter_record.decoded_object
        if decoded_object is None:
            raise ValueError("reached handoff lacks retained decoded Planner object")
        try:
            reconstructed_draft = load_minimal_csharp_repair_draft(decoded_object)
        except (TypeError, ValueError) as exc:
            raise ValueError("retained decoded Planner object is not admissible") from exc
        if reconstructed_draft != self.validated_draft:
            raise ValueError("retained decoded Planner object differs from draft")
        if self.validated_draft != self.handoff_result.draft:
            raise ValueError("validated draft differs from handoff draft")
        if self.terminal_stage != self.handoff_result.terminal_stage:
            raise ValueError("terminal stage differs from handoff result")
        if self.terminal_reason != self.handoff_result.terminal_reason:
            raise ValueError("terminal reason differs from handoff result")

    def _require_adapter_stop(self) -> None:
        if self.validated_draft is not None or self.handoff_result is not None:
            raise ValueError("Planner adapter stop cannot carry downstream results")
        if self.terminal_stage != "planner_adapter":
            raise ValueError("Planner adapter stop stage differs")
        if self.terminal_reason != self.planner_adapter_record.failure_reason:
            raise ValueError("Planner adapter stop reason differs")

    def _require_draft_stop(self) -> None:
        if self.terminal_stage != "draft_admission":
            raise ValueError("draft admission stop stage differs")
        if self.terminal_reason not in {
            "draft_payload_rejected",
            "goal_mismatch",
        }:
            raise ValueError("draft admission stop reason differs")


async def run_minimal_intent_worker_integration(
    intent: str,
    *,
    planner_adapter: MinimalPlannerDraftAdapter,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalIntentWorkerIntegrationResult:
    intent = _require_exact_intent(intent)
    if type(planner_adapter) is not MinimalPlannerDraftAdapter:
        raise TypeError("planner_adapter must be the exact MinimalPlannerDraftAdapter")
    if not callable(getattr(worker_transport, "send", None)):
        raise TypeError("worker_transport must provide callable send")
    if not callable(tool_executor):
        raise TypeError("tool_executor must be callable")

    adapter_record = planner_adapter.produce(intent)
    if adapter_record.status != "decoded":
        if adapter_record.failure_reason is None:
            raise RuntimeError("Planner adapter stop lacks a failure reason")
        return MinimalIntentWorkerIntegrationResult(
            intent=intent,
            planner_adapter_record=adapter_record,
            validated_draft=None,
            handoff_result=None,
            terminal_stage="planner_adapter",
            terminal_reason=adapter_record.failure_reason,
        )
    if adapter_record.decoded_object is None:
        raise RuntimeError("decoded Planner adapter record lacks an object")
    try:
        draft = load_minimal_csharp_repair_draft(adapter_record.decoded_object)
    except (TypeError, ValueError):
        return _draft_stop(intent, adapter_record, "draft_payload_rejected")
    if draft.goal != intent:
        return _draft_stop(intent, adapter_record, "goal_mismatch")
    handoff = await run_minimal_csharp_repair_handoff(
        draft,
        worker_transport=worker_transport,
        tool_executor=tool_executor,
    )
    return MinimalIntentWorkerIntegrationResult(
        intent=intent,
        planner_adapter_record=adapter_record,
        validated_draft=draft,
        handoff_result=handoff,
        terminal_stage=handoff.terminal_stage,
        terminal_reason=handoff.terminal_reason,
    )


def _draft_stop(
    intent: str,
    adapter_record: MinimalPlannerDraftAdapterRecord,
    reason: Literal["draft_payload_rejected", "goal_mismatch"],
) -> MinimalIntentWorkerIntegrationResult:
    return MinimalIntentWorkerIntegrationResult(
        intent=intent,
        planner_adapter_record=adapter_record,
        validated_draft=None,
        handoff_result=None,
        terminal_stage="draft_admission",
        terminal_reason=reason,
    )


class _DuplicateKeyError(ValueError):
    pass


class _NonFiniteNumberError(ValueError):
    pass


def _require_exact_intent(intent: str) -> str:
    if type(intent) is not str:
        raise TypeError("intent must be an exact string")
    if not intent.strip():
        raise ValueError("intent must be nonblank")
    try:
        encoded = intent.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("intent must be valid UTF-8") from exc
    if len(encoded) > MAX_INTENT_UTF8_BYTES:
        raise ValueError("intent exceeds the UTF-8 byte limit")
    return intent


def _render_prompt_snapshot(intent: str) -> MinimalPlannerPromptSnapshot:
    return MinimalPlannerPromptSnapshot(
        system_content=_SYSTEM_CONTENT,
        user_content=json.dumps(
            {"user_intent": intent},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ),
    )


def _decode_response(
    snapshot: MinimalPlannerPromptSnapshot,
    raw_response: object,
) -> MinimalPlannerDraftAdapterRecord:
    if type(raw_response) is not str:
        return _response_failure(snapshot, "response_not_string", None)
    try:
        encoded = raw_response.encode("utf-8")
    except UnicodeEncodeError:
        return _response_failure(snapshot, "response_not_utf8", None)
    if len(encoded) > MAX_PLANNER_RESPONSE_UTF8_BYTES:
        return _response_failure(snapshot, "response_too_large", None)
    try:
        decoded = json.loads(
            raw_response,
            object_pairs_hook=_object_pairs,
            parse_constant=_reject_constant,
            parse_float=_parse_finite_float,
        )
    except _DuplicateKeyError:
        return _response_failure(snapshot, "response_duplicate_key", raw_response)
    except _NonFiniteNumberError:
        return _response_failure(snapshot, "response_nonfinite_number", raw_response)
    except json.JSONDecodeError as exc:
        reason: _AdapterFailureReason = (
            "response_trailing_content"
            if exc.msg == "Extra data"
            else "response_invalid_json"
        )
        return _response_failure(snapshot, reason, raw_response)
    except RecursionError:
        return _response_failure(snapshot, "response_invalid_json", raw_response)
    except ValueError:
        return _response_failure(snapshot, "response_invalid_json", raw_response)
    if type(decoded) is not dict:
        return _response_failure(snapshot, "response_not_object", raw_response)
    return MinimalPlannerDraftAdapterRecord(
        prompt_snapshot=snapshot,
        status="decoded",
        raw_response=raw_response,
        decoded_object=decoded,
        failure_reason=None,
        transport_error_type=None,
    )


def _object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(key)
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise _NonFiniteNumberError(value)


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _NonFiniteNumberError(value)
    return parsed


def _response_failure(
    snapshot: MinimalPlannerPromptSnapshot,
    reason: _AdapterFailureReason,
    raw_response: str | None,
) -> MinimalPlannerDraftAdapterRecord:
    return MinimalPlannerDraftAdapterRecord(
        prompt_snapshot=snapshot,
        status="response_invalid",
        raw_response=raw_response,
        decoded_object=None,
        failure_reason=reason,
        transport_error_type=None,
    )


def _require_bounded_raw_response(raw_response: object) -> None:
    if type(raw_response) is not str:
        raise TypeError("raw response must be an exact string")
    try:
        encoded = raw_response.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("raw response must be valid UTF-8") from exc
    if len(encoded) > MAX_PLANNER_RESPONSE_UTF8_BYTES:
        raise ValueError("raw response exceeds the UTF-8 byte limit")


def build_minimal_planner_draft_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["goal", "capability", "interface", "acceptance"],
        "properties": {
            "goal": {"type": "string"},
            "capability": {"const": "grasshopper_csharp_component"},
            "interface": {
                "type": "object",
                "additionalProperties": False,
                "required": ["inputs", "outputs"],
                "properties": {
                    "inputs": {"type": "array", "maxItems": 0},
                    "outputs": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["name", "type"],
                            "properties": {
                                "name": {"const": "A"},
                                "type": {"const": "double"},
                            },
                        },
                    },
                },
            },
            "acceptance": {"const": "clean_compile_receipt"},
        },
    }
