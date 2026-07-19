"""Deterministic support for the LM9B-C compiler-sufficiency probe.

This module validates the probe container and its declared trace. It does not
judge semantic fidelity, compile C#, or authorize execution.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from jsonschema import Draft202012Validator

from rook.gh_csharp_preflight import (
    is_recognized_csharp_full_source,
    preflight_csharp_script,
)


COMPILER_RESULT_SCHEMA_ID = "rook.lm9b_c.compiler_result:v1"
_SHA256_PATTERN = r"^sha256:[0-9a-f]{64}$"

_PIN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "name": {"type": "string", "minLength": 1, "maxLength": 80},
        "type": {"type": "string", "minLength": 1, "maxLength": 80},
        "access": {"enum": ["item", "list", "tree"]},
    },
    "required": ["name", "type", "access"],
}

_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "decision_id": {"type": "string", "minLength": 1, "maxLength": 160},
        "decision_kind": {
            "enum": ["material_semantic", "guard_or_read", "implementation"]
        },
        "statement": {"type": "string", "minLength": 1, "maxLength": 1200},
        "maintains_clause_id": {
            "type": ["string", "null"],
            "maxLength": 160,
        },
        "support_refs": {
            "type": "array",
            "maxItems": 128,
            "items": {"type": "string", "minLength": 1, "maxLength": 240},
        },
        "requires_or_invariant_clause_id": {
            "type": ["string", "null"],
            "maxLength": 160,
        },
        "shape_delegation_id": {
            "type": ["string", "null"],
            "maxLength": 160,
        },
        "capability_id": {
            "type": ["string", "null"],
            "maxLength": 160,
        },
    },
    "required": [
        "decision_id",
        "decision_kind",
        "statement",
        "maintains_clause_id",
        "support_refs",
        "requires_or_invariant_clause_id",
        "shape_delegation_id",
        "capability_id",
    ],
}

_VERIFICATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verification_id": {"type": "string", "minLength": 1, "maxLength": 160},
        "clause_id": {"type": "string", "minLength": 1, "maxLength": 160},
        "observation": {"type": "string", "minLength": 1, "maxLength": 1200},
        "acceptance": {"type": "string", "minLength": 1, "maxLength": 1200},
    },
    "required": ["verification_id", "clause_id", "observation", "acceptance"],
}

_COMPILED_CANDIDATE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "representation": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "kind": {"const": "csharp_script_instance"},
                "pins_in": {
                    "type": "array",
                    "maxItems": 32,
                    "items": _PIN_SCHEMA,
                },
                "pins_out": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 32,
                    "items": _PIN_SCHEMA,
                },
                "source": {"type": "string", "minLength": 1, "maxLength": 100000},
            },
            "required": ["kind", "pins_in", "pins_out", "source"],
        },
        "decisions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 256,
            "items": _DECISION_SCHEMA,
        },
        "verification_plan": {
            "type": "array",
            "minItems": 1,
            "maxItems": 128,
            "items": _VERIFICATION_SCHEMA,
        },
        "unused_recipe_paths": {
            "type": "array",
            "maxItems": 256,
            "items": {"type": "string", "minLength": 1, "maxLength": 320},
        },
    },
    "required": [
        "representation",
        "decisions",
        "verification_plan",
        "unused_recipe_paths",
    ],
}

_MISSING_DECISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "missing_decision_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 160,
        },
        "statement": {"type": "string", "minLength": 1, "maxLength": 1200},
        "affected_clause_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 64,
            "items": {"type": "string", "minLength": 1, "maxLength": 160},
        },
        "absent_authority": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1600,
        },
        "why_delegation_is_insufficient": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1600,
        },
    },
    "required": [
        "missing_decision_id",
        "statement",
        "affected_clause_ids",
        "absent_authority",
        "why_delegation_is_insufficient",
    ],
}

COMPILER_RESULT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": COMPILER_RESULT_SCHEMA_ID,
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema": {"const": COMPILER_RESULT_SCHEMA_ID},
        "result_kind": {"enum": ["compiled_candidate", "contract_insufficient"]},
        "recipe_fingerprint": {"type": "string", "pattern": _SHA256_PATTERN},
        "compiled_candidate": _COMPILED_CANDIDATE_SCHEMA,
        "contract_insufficient": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "missing_decisions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 64,
                    "items": _MISSING_DECISION_SCHEMA,
                }
            },
            "required": ["missing_decisions"],
        },
    },
    "required": ["schema", "result_kind", "recipe_fingerprint"],
    "oneOf": [
        {
            "properties": {"result_kind": {"const": "compiled_candidate"}},
            "required": ["compiled_candidate"],
            "not": {"required": ["contract_insufficient"]},
        },
        {
            "properties": {"result_kind": {"const": "contract_insufficient"}},
            "required": ["contract_insufficient"],
            "not": {"required": ["compiled_candidate"]},
        },
    ],
}

_TERMINAL_VALIDATOR = Draft202012Validator(COMPILER_RESULT_SCHEMA)

COMPILER_TOOL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "submission_json": {
            "type": "string",
            "description": "Exact JSON serialization of the terminal result.",
        }
    },
    "required": ["submission_json"],
}

EVALUATION_REPORT_SCHEMA_ID = "rook.lm9b_c.compiler_evaluation:v1"
_ASSESSMENT_STATUS = {"enum": ["accepted", "rejected"]}
EVALUATION_REPORT_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": EVALUATION_REPORT_SCHEMA_ID,
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "schema": {"const": EVALUATION_REPORT_SCHEMA_ID},
        "evaluated_result_kind": {
            "enum": ["compiled_candidate", "contract_insufficient"]
        },
        "decision": {"enum": ["accepted", "rejected"]},
        "candidate_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "source_fidelity": _ASSESSMENT_STATUS,
                "material_authority": _ASSESSMENT_STATUS,
                "representation_coherence": _ASSESSMENT_STATUS,
                "verification_fidelity": _ASSESSMENT_STATUS,
            },
            "required": [
                "source_fidelity",
                "material_authority",
                "representation_coherence",
                "verification_fidelity",
            ],
        },
        "contract_gap_assessment": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "missing_decision_precise": {"type": "boolean"},
                "absent_from_semantic_source": {"type": "boolean"},
                "necessary_for_conforming_lowering": {"type": "boolean"},
                "outside_delegated_latitude": {"type": "boolean"},
            },
            "required": [
                "missing_decision_precise",
                "absent_from_semantic_source",
                "necessary_for_conforming_lowering",
                "outside_delegated_latitude",
            ],
        },
        "issue_codes": {
            "type": "array",
            "maxItems": 64,
            "items": {
                "type": "string",
                "pattern": r"^[a-z][a-z0-9_]{0,79}$",
            },
        },
        "bounded_rationale": {
            "type": "string",
            "minLength": 1,
            "maxLength": 4000,
        },
    },
    "required": [
        "schema",
        "evaluated_result_kind",
        "decision",
        "issue_codes",
        "bounded_rationale",
    ],
    "oneOf": [
        {
            "properties": {
                "evaluated_result_kind": {"const": "compiled_candidate"}
            },
            "required": ["candidate_assessment"],
            "not": {"required": ["contract_gap_assessment"]},
        },
        {
            "properties": {
                "evaluated_result_kind": {"const": "contract_insufficient"}
            },
            "required": ["contract_gap_assessment"],
            "not": {"required": ["candidate_assessment"]},
        },
    ],
}
_EVALUATION_VALIDATOR = Draft202012Validator(EVALUATION_REPORT_SCHEMA)
EVALUATOR_TOOL_PARAMETERS: dict[str, Any] = {
    "type": "object",
    "properties": {
        "evaluation_json": {
            "type": "string",
            "description": "Exact JSON serialization of the evaluation report.",
        }
    },
    "required": ["evaluation_json"],
}


@dataclass(frozen=True)
class TraceError:
    code: str
    path: str
    message: str


@dataclass(frozen=True)
class TerminalValidationResult:
    result_kind: str | None
    schema_valid: bool
    trace_valid: bool
    errors: tuple[TraceError, ...]
    csharp_preflight_ok: bool | None
    csharp_preflight_code: str | None
    csharp_compiled: None = None


@dataclass(frozen=True)
class ProviderTurn:
    """One provider response with its exact transport evidence."""

    raw_response: bytes
    assistant_message: Mapping[str, object]
    usage: Mapping[str, object]
    provider_metadata: Mapping[str, object]
    raw_request: bytes = b""


class ProviderCallFailure(RuntimeError):
    """Provider adapter failure carrying complete sanitized transport evidence."""

    def __init__(
        self,
        *,
        failure_type: str,
        message: str,
        raw_request: bytes,
        raw_error: bytes,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.message = message
        self.raw_request = raw_request
        self.raw_error = raw_error


@dataclass(frozen=True)
class SessionLimits:
    max_turns: int
    max_completion_tokens_per_call: int
    provider_timeout_s: float
    overall_deadline_s: float
    cumulative_token_stop_threshold: int
    cumulative_cost_stop_threshold_usd: float

    def __post_init__(self) -> None:
        if type(self.max_turns) is not int or self.max_turns < 1:
            raise ValueError("max_turns must be a positive exact int")
        if (
            type(self.max_completion_tokens_per_call) is not int
            or self.max_completion_tokens_per_call < 1
        ):
            raise ValueError("max_completion_tokens_per_call must be positive")
        if self.provider_timeout_s <= 0 or self.overall_deadline_s <= 0:
            raise ValueError("time limits must be positive")
        if (
            type(self.cumulative_token_stop_threshold) is not int
            or self.cumulative_token_stop_threshold < 1
        ):
            raise ValueError("the token stop threshold must be positive")
        if self.cumulative_cost_stop_threshold_usd <= 0:
            raise ValueError("the cost stop threshold must be positive")


@dataclass(frozen=True)
class CompilerTurnRecord:
    turn_number: int
    controller_request: Mapping[str, object]
    raw_provider_request: bytes
    raw_provider_response: bytes
    assistant_message: Mapping[str, object]
    usage: Mapping[str, object]
    provider_metadata: Mapping[str, object]
    feedback_codes: tuple[str, ...]
    elapsed_s: float


@dataclass(frozen=True)
class CompilerSessionResult:
    stop_reason: str
    turns: tuple[CompilerTurnRecord, ...]
    terminal_submission: Mapping[str, object] | None
    terminal_validation: TerminalValidationResult | None
    total_tokens: int
    total_cost_usd: float
    cost_evidence_complete: bool
    elapsed_s: float
    control_error: str | None
    control_evidence: Mapping[str, object] | None
    raw_control_request: bytes | None
    raw_control_error: bytes | None

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def to_summary(self) -> dict[str, object]:
        return {
            "stop_reason": self.stop_reason,
            "turn_count": self.turn_count,
            "terminal_result_kind": (
                self.terminal_submission.get("result_kind")
                if self.terminal_submission is not None
                else None
            ),
            "total_tokens": self.total_tokens,
            "total_cost_usd": self.total_cost_usd,
            "cost_evidence_complete": self.cost_evidence_complete,
            "elapsed_s": self.elapsed_s,
            "control_error": self.control_error,
            "control_evidence": self.control_evidence,
        }


@dataclass(frozen=True)
class EvaluatorAttemptResult:
    stop_reason: str
    report: Mapping[str, object] | None
    raw_provider_response: bytes | None
    usage: Mapping[str, object] | None
    provider_metadata: Mapping[str, object] | None
    validation_errors: tuple[str, ...]
    control_error: str | None
    control_evidence: Mapping[str, object] | None = None
    raw_provider_request: bytes | None = None
    raw_provider_error: bytes | None = None
    elapsed_s: float | None = None

    @classmethod
    def control_failure(cls, reason: str) -> "EvaluatorAttemptResult":
        return cls(
            stop_reason=reason,
            report=None,
            raw_provider_response=None,
            usage=None,
            provider_metadata=None,
            validation_errors=(),
            control_error=reason,
            control_evidence={"failure_type": reason, "message": reason},
        )


@dataclass(frozen=True)
class ObservationDecision:
    outcome: str
    reason_codes: tuple[str, ...]


def _error(code: str, path: str, message: str) -> TraceError:
    return TraceError(code=code, path=path, message=message)


def _schema_errors(value: object) -> tuple[TraceError, ...]:
    errors: list[TraceError] = []
    for finding in sorted(
        _TERMINAL_VALIDATOR.iter_errors(value),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    ):
        pointer = "/" + "/".join(str(part) for part in finding.absolute_path)
        errors.append(
            _error(
                "terminal_schema_invalid",
                pointer if pointer != "/" else "",
                finding.message[:800],
            )
        )
    return tuple(errors)


def _duplicates(values: list[str]) -> set[str]:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    return duplicates


def _validate_candidate_trace(
    candidate: Mapping[str, Any],
    contract_index: Mapping[str, object],
) -> tuple[list[TraceError], bool, str | None]:
    errors: list[TraceError] = []
    maintains = set(contract_index["maintains_clause_ids"])
    requirements = set(contract_index["requires_clause_ids"])
    invariants = set(contract_index["invariant_clause_ids"])
    postconditions = set(contract_index["postcondition_clause_ids"])
    delegations = set(contract_index["shape_delegation_ids"])
    capabilities = set(contract_index["capability_ids"])
    supports = set(contract_index["support_ids"])

    decisions = candidate["decisions"]
    decision_ids = [item["decision_id"] for item in decisions]
    for duplicate in sorted(_duplicates(decision_ids)):
        errors.append(
            _error("duplicate_decision_id", "/compiled_candidate/decisions", duplicate)
        )

    for index, decision in enumerate(decisions):
        path = f"/compiled_candidate/decisions/{index}"
        kind = decision["decision_kind"]
        maintains_id = decision["maintains_clause_id"]
        support_refs = decision["support_refs"]
        if maintains_id is not None and maintains_id not in maintains:
            errors.append(
                _error(
                    "unknown_maintains_clause",
                    f"{path}/maintains_clause_id",
                    maintains_id,
                )
            )

        if kind == "material_semantic":
            if maintains_id is None:
                errors.append(
                    _error(
                        "material_decision_missing_maintains",
                        f"{path}/maintains_clause_id",
                        "material decisions require maintained truth",
                    )
                )
            if not support_refs:
                errors.append(
                    _error(
                        "material_decision_missing_support",
                        f"{path}/support_refs",
                        "material decisions require recipe-authorized support",
                    )
                )
            for support_ref in support_refs:
                if support_ref not in supports:
                    errors.append(
                        _error(
                            "unknown_support_ref",
                            f"{path}/support_refs",
                            support_ref,
                        )
                    )
        elif kind == "guard_or_read":
            clause_id = decision["requires_or_invariant_clause_id"]
            if clause_id not in requirements | invariants:
                errors.append(
                    _error(
                        "guard_decision_missing_requirement_or_invariant",
                        f"{path}/requires_or_invariant_clause_id",
                        str(clause_id),
                    )
                )
        else:
            if maintains_id is None:
                errors.append(
                    _error(
                        "implementation_decision_missing_maintains",
                        f"{path}/maintains_clause_id",
                        "implementation decisions require a maintained obligation",
                    )
                )
            if decision["shape_delegation_id"] not in delegations:
                errors.append(
                    _error(
                        "implementation_decision_missing_delegation",
                        f"{path}/shape_delegation_id",
                        str(decision["shape_delegation_id"]),
                    )
                )
            if decision["capability_id"] not in capabilities:
                errors.append(
                    _error(
                        "implementation_decision_missing_capability",
                        f"{path}/capability_id",
                        str(decision["capability_id"]),
                    )
                )

    verification = candidate["verification_plan"]
    verification_ids = [item["verification_id"] for item in verification]
    for duplicate in sorted(_duplicates(verification_ids)):
        errors.append(
            _error(
                "duplicate_verification_id",
                "/compiled_candidate/verification_plan",
                duplicate,
            )
        )
    observed_clauses = [item["clause_id"] for item in verification]
    for clause_id in observed_clauses:
        if clause_id not in postconditions:
            errors.append(
                _error(
                    "unknown_verification_clause",
                    "/compiled_candidate/verification_plan",
                    clause_id,
                )
            )
    missing = sorted(postconditions - set(observed_clauses))
    if missing:
        errors.append(
            _error(
                "verification_coverage_missing",
                "/compiled_candidate/verification_plan",
                ", ".join(missing),
            )
        )

    representation = candidate["representation"]
    preflight = preflight_csharp_script(
        code=representation["source"],
        pins_in=representation["pins_in"],
        pins_out=representation["pins_out"],
        mode="full",
    )
    recognized = is_recognized_csharp_full_source(representation["source"])
    preflight_ok = preflight.ok and recognized
    preflight_code = preflight.code if not preflight.ok else None
    if preflight.ok and not recognized:
        preflight_code = "full_source_not_recognized"
    return errors, preflight_ok, preflight_code


def _validate_insufficient_trace(
    payload: Mapping[str, Any],
    contract_index: Mapping[str, object],
) -> list[TraceError]:
    errors: list[TraceError] = []
    known_clauses = (
        set(contract_index["maintains_clause_ids"])
        | set(contract_index["requires_clause_ids"])
        | set(contract_index["invariant_clause_ids"])
        | set(contract_index["postcondition_clause_ids"])
    )
    rows = payload["missing_decisions"]
    ids = [item["missing_decision_id"] for item in rows]
    for duplicate in sorted(_duplicates(ids)):
        errors.append(
            _error(
                "duplicate_missing_decision_id",
                "/contract_insufficient/missing_decisions",
                duplicate,
            )
        )
    for index, row in enumerate(rows):
        for clause_id in row["affected_clause_ids"]:
            if clause_id not in known_clauses:
                errors.append(
                    _error(
                        "unknown_affected_clause",
                        f"/contract_insufficient/missing_decisions/{index}/affected_clause_ids",
                        clause_id,
                    )
                )
    return errors


def validate_terminal_submission(
    value: object,
    contract_index: Mapping[str, object],
) -> TerminalValidationResult:
    """Validate one terminal tool submission without judging its semantics."""

    schema_errors = _schema_errors(value)
    if schema_errors:
        return TerminalValidationResult(
            result_kind=None,
            schema_valid=False,
            trace_valid=False,
            errors=schema_errors,
            csharp_preflight_ok=None,
            csharp_preflight_code=None,
        )

    assert isinstance(value, dict)
    errors: list[TraceError] = []
    expected_fingerprint = contract_index["recipe_fingerprint"]
    if value["recipe_fingerprint"] != expected_fingerprint:
        errors.append(
            _error(
                "recipe_fingerprint_mismatch",
                "/recipe_fingerprint",
                "submission does not bind the frozen recipe",
            )
        )

    preflight_ok: bool | None = None
    preflight_code: str | None = None
    result_kind = value["result_kind"]
    if result_kind == "compiled_candidate":
        candidate_errors, preflight_ok, preflight_code = _validate_candidate_trace(
            value["compiled_candidate"],
            contract_index,
        )
        errors.extend(candidate_errors)
    else:
        errors.extend(
            _validate_insufficient_trace(value["contract_insufficient"], contract_index)
        )

    return TerminalValidationResult(
        result_kind=result_kind,
        schema_valid=True,
        trace_valid=not errors,
        errors=tuple(errors),
        csharp_preflight_ok=preflight_ok,
        csharp_preflight_code=preflight_code,
    )


def _evaluation_errors(
    value: object,
    expected_result_kind: str | None = None,
) -> tuple[str, ...]:
    errors = [
        finding.message[:800]
        for finding in sorted(
            _EVALUATION_VALIDATOR.iter_errors(value),
            key=lambda item: tuple(str(part) for part in item.absolute_path),
        )
    ]
    if errors or not isinstance(value, dict):
        return tuple(errors)
    if (
        expected_result_kind is not None
        and value["evaluated_result_kind"] != expected_result_kind
    ):
        errors.append("evaluated result kind does not match the compiler result")
        return tuple(errors)

    accepted = value["decision"] == "accepted"
    if value["evaluated_result_kind"] == "compiled_candidate":
        statuses = tuple(value["candidate_assessment"].values())
        if accepted != all(status == "accepted" for status in statuses):
            errors.append("candidate decision disagrees with its assessment rows")
    else:
        findings = tuple(value["contract_gap_assessment"].values())
        if accepted != all(finding is True for finding in findings):
            errors.append("gap decision disagrees with its required findings")
    if accepted and value["issue_codes"]:
        errors.append("an accepted evaluation cannot carry issue codes")
    if not accepted and not value["issue_codes"]:
        errors.append("a rejected evaluation requires at least one issue code")
    if len(value["issue_codes"]) != len(set(value["issue_codes"])):
        errors.append("evaluation issue codes must be unique")
    return tuple(errors)


def evaluator_result_from_report(
    report: object,
    *,
    expected_result_kind: str | None = None,
) -> EvaluatorAttemptResult:
    errors = _evaluation_errors(report, expected_result_kind)
    if errors:
        return EvaluatorAttemptResult(
            stop_reason="invalid_report",
            report=None,
            raw_provider_response=None,
            usage=None,
            provider_metadata=None,
            validation_errors=errors,
            control_error=None,
        )
    assert isinstance(report, dict)
    return EvaluatorAttemptResult(
        stop_reason="valid_report",
        report=report,
        raw_provider_response=None,
        usage=None,
        provider_metadata=None,
        validation_errors=(),
        control_error=None,
    )


def evaluator_tool_definition() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "submit_evaluation_result",
            "description": (
                "Submit the independent source-to-result evaluation. This report "
                "does not authorize execution and is not returned to the compiler."
            ),
            "parameters": EVALUATOR_TOOL_PARAMETERS,
        },
    }


def run_evaluator_once(
    *,
    provider: Callable[[dict[str, object]], ProviderTurn],
    system_prompt: str,
    user_prompt: str,
    evaluated_result_kind: str,
    max_completion_tokens: int,
    provider_timeout_s: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> EvaluatorAttemptResult:
    """Run one independent evaluator call with no repair or feedback path."""

    started = monotonic()
    request = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "tools": [evaluator_tool_definition()],
        "tool_choice": {
            "type": "function",
            "function": {"name": "submit_evaluation_result"},
        },
        "max_completion_tokens": max_completion_tokens,
        "provider_timeout_s": provider_timeout_s,
    }
    try:
        response = provider(request)
    except ProviderCallFailure as exc:
        return EvaluatorAttemptResult(
            stop_reason="provider_failure",
            report=None,
            raw_provider_response=None,
            usage=None,
            provider_metadata=None,
            validation_errors=(),
            control_error=exc.failure_type,
            control_evidence={
                "failure_type": exc.failure_type,
                "message": exc.message[:2000],
            },
            raw_provider_request=exc.raw_request,
            raw_provider_error=exc.raw_error,
            elapsed_s=max(0.0, monotonic() - started),
        )
    except Exception as exc:
        failure_type = type(exc).__name__
        return EvaluatorAttemptResult(
            stop_reason="provider_failure",
            report=None,
            raw_provider_response=None,
            usage=None,
            provider_metadata=None,
            validation_errors=(),
            control_error=failure_type,
            control_evidence={
                "failure_type": failure_type,
                "message": str(exc)[:2000],
            },
            elapsed_s=max(0.0, monotonic() - started),
        )
    if type(response) is not ProviderTurn:
        return EvaluatorAttemptResult.control_failure("provider_protocol_failure")

    message = response.assistant_message
    calls = message.get("tool_calls", []) if isinstance(message, Mapping) else []
    if type(calls) is not list or len(calls) != 1 or type(calls[0]) is not dict:
        return EvaluatorAttemptResult(
            stop_reason="invalid_report",
            report=None,
            raw_provider_response=response.raw_response,
            usage=response.usage,
            provider_metadata=response.provider_metadata,
            validation_errors=("exactly one evaluator tool call is required",),
            control_error=None,
            raw_provider_request=response.raw_request,
            elapsed_s=max(0.0, monotonic() - started),
        )
    function = calls[0].get("function")
    if type(function) is not dict or function.get("name") != "submit_evaluation_result":
        return EvaluatorAttemptResult(
            stop_reason="invalid_report",
            report=None,
            raw_provider_response=response.raw_response,
            usage=response.usage,
            provider_metadata=response.provider_metadata,
            validation_errors=("the evaluator called an unknown tool",),
            control_error=None,
            raw_provider_request=response.raw_request,
            elapsed_s=max(0.0, monotonic() - started),
        )
    arguments = function.get("arguments")
    try:
        envelope = json.loads(arguments) if type(arguments) is str else None
    except (json.JSONDecodeError, UnicodeError):
        envelope = None
    if (
        type(envelope) is dict
        and set(envelope) == {"evaluation_json"}
        and type(envelope.get("evaluation_json")) is str
    ):
        try:
            report = json.loads(envelope["evaluation_json"])
        except (json.JSONDecodeError, UnicodeError):
            report = None
    else:
        report = None
    checked = evaluator_result_from_report(
        report,
        expected_result_kind=evaluated_result_kind,
    )
    return EvaluatorAttemptResult(
        stop_reason=checked.stop_reason,
        report=checked.report,
        raw_provider_response=response.raw_response,
        usage=response.usage,
        provider_metadata=response.provider_metadata,
        validation_errors=checked.validation_errors,
        control_error=None,
        raw_provider_request=response.raw_request,
        elapsed_s=max(0.0, monotonic() - started),
    )


def classify_observation(
    compiler: CompilerSessionResult,
    evaluator: EvaluatorAttemptResult | None,
) -> ObservationDecision:
    """Derive the probe's conservative four-way empirical observation."""

    if compiler.terminal_submission is None:
        reason = compiler.stop_reason
        if reason == "provider_failure":
            reason = "provider_failure"
        return ObservationDecision(
            outcome="inconclusive",
            reason_codes=(f"compiler_{reason}",),
        )
    if evaluator is None:
        return ObservationDecision(
            outcome="inconclusive",
            reason_codes=("evaluator_not_run",),
        )
    if evaluator.stop_reason != "valid_report" or evaluator.report is None:
        return ObservationDecision(
            outcome="inconclusive",
            reason_codes=(f"evaluator_{evaluator.stop_reason}",),
        )

    result_kind = compiler.terminal_submission["result_kind"]
    if evaluator.report.get("evaluated_result_kind") != result_kind:
        return ObservationDecision(
            outcome="inconclusive",
            reason_codes=("evaluator_result_kind_mismatch",),
        )
    if result_kind == "compiled_candidate":
        if (
            compiler.terminal_validation is None
            or compiler.terminal_validation.csharp_preflight_ok is not True
        ):
            return ObservationDecision(
                outcome="candidate_failure",
                reason_codes=("csharp_preflight_failed",),
            )
        if evaluator.report["decision"] == "accepted":
            return ObservationDecision(
                outcome="bounded_lowering_demonstrated",
                reason_codes=("independent_evaluation_accepted",),
            )
        return ObservationDecision(
            outcome="candidate_failure",
            reason_codes=("independent_evaluation_rejected",),
        )

    gap = evaluator.report["contract_gap_assessment"]
    if evaluator.report["decision"] == "accepted" and all(gap.values()):
        return ObservationDecision(
            outcome="contract_gap_demonstrated",
            reason_codes=("independent_gap_evaluation_accepted",),
        )
    return ObservationDecision(
        outcome="candidate_failure",
        reason_codes=("contract_gap_not_demonstrated",),
    )


def compiler_tool_definition() -> dict[str, object]:
    """Return the only tool exposed to the compiler session."""

    return {
        "type": "function",
        "function": {
            "name": "submit_compiler_result",
            "description": (
                "Submit either one inert C# Script_Instance candidate or an honest "
                "contract-insufficient result as exact JSON in submission_json. "
                "A valid submission ends the session."
            ),
            "parameters": COMPILER_TOOL_PARAMETERS,
        },
    }


def _feedback_message(
    feedback_codes: tuple[str, ...],
    tool_call_id: str | None,
) -> dict[str, object]:
    content = json.dumps(
        {
            "accepted": False,
            "feedback_codes": list(feedback_codes),
            "instruction": (
                "Submit one value that conforms to the terminal tool schema and "
                "uses only declared recipe references."
            ),
        },
        separators=(",", ":"),
    )
    if tool_call_id is not None:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
    return {"role": "user", "content": content}


def _unique_codes(errors: tuple[TraceError, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(error.code for error in errors))


def _terminal_from_message(
    message: Mapping[str, object],
    contract_index: Mapping[str, object],
) -> tuple[
    Mapping[str, object] | None,
    TerminalValidationResult | None,
    tuple[str, ...],
    str | None,
]:
    tool_calls = message.get("tool_calls", [])
    if type(tool_calls) is not list:
        return None, None, ("provider_tool_calls_malformed",), None
    if not tool_calls:
        return None, None, ("terminal_tool_missing",), None
    if len(tool_calls) != 1:
        return None, None, ("multiple_tool_calls",), None

    tool_call = tool_calls[0]
    if type(tool_call) is not dict:
        return None, None, ("provider_tool_call_malformed",), None
    tool_call_id = tool_call.get("id")
    if type(tool_call_id) is not str or not tool_call_id:
        tool_call_id = None
    function = tool_call.get("function")
    if type(function) is not dict:
        return None, None, ("provider_tool_call_malformed",), tool_call_id
    if function.get("name") != "submit_compiler_result":
        return None, None, ("unknown_tool",), tool_call_id
    arguments = function.get("arguments")
    if type(arguments) is not str:
        return None, None, ("tool_arguments_not_string",), tool_call_id
    try:
        envelope = json.loads(arguments)
    except (json.JSONDecodeError, UnicodeError):
        return None, None, ("tool_arguments_invalid_json",), tool_call_id
    if (
        type(envelope) is not dict
        or set(envelope) != {"submission_json"}
        or type(envelope.get("submission_json")) is not str
    ):
        return None, None, ("tool_arguments_shape_invalid",), tool_call_id
    try:
        value = json.loads(envelope["submission_json"])
    except (json.JSONDecodeError, UnicodeError):
        return None, None, ("terminal_json_invalid",), tool_call_id

    validation = validate_terminal_submission(value, contract_index)
    if not validation.schema_valid or not validation.trace_valid:
        return None, validation, _unique_codes(validation.errors), tool_call_id
    assert isinstance(value, dict)
    return value, validation, (), tool_call_id


def _usage_values(usage: Mapping[str, object]) -> tuple[int, float, bool]:
    token_value = usage.get("total_tokens", 0)
    total_tokens = token_value if type(token_value) is int and token_value >= 0 else 0
    cost_value = usage.get("cost_usd")
    if type(cost_value) in (int, float) and float(cost_value) >= 0:
        return total_tokens, float(cost_value), True
    return total_tokens, 0.0, False


def run_compiler_session(
    *,
    provider: Callable[[dict[str, object]], ProviderTurn],
    system_prompt: str,
    user_prompt: str,
    contract_index: Mapping[str, object],
    limits: SessionLimits,
    monotonic: Callable[[], float] = time.monotonic,
) -> CompilerSessionResult:
    """Run one bounded compiler session; no retry or semantic repair occurs."""

    started = monotonic()
    messages: list[dict[str, object]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    turns: list[CompilerTurnRecord] = []
    total_tokens = 0
    total_cost = 0.0
    cost_complete = True

    def finish(
        reason: str,
        *,
        terminal: Mapping[str, object] | None = None,
        validation: TerminalValidationResult | None = None,
        control_error: str | None = None,
        control_evidence: Mapping[str, object] | None = None,
        raw_control_request: bytes | None = None,
        raw_control_error: bytes | None = None,
    ) -> CompilerSessionResult:
        return CompilerSessionResult(
            stop_reason=reason,
            turns=tuple(turns),
            terminal_submission=terminal,
            terminal_validation=validation,
            total_tokens=total_tokens,
            total_cost_usd=total_cost,
            cost_evidence_complete=cost_complete,
            elapsed_s=max(0.0, monotonic() - started),
            control_error=control_error,
            control_evidence=control_evidence,
            raw_control_request=raw_control_request,
            raw_control_error=raw_control_error,
        )

    for turn_number in range(1, limits.max_turns + 1):
        if monotonic() - started >= limits.overall_deadline_s:
            return finish("overall_deadline_exhausted")

        request = {
            "messages": json.loads(json.dumps(messages)),
            "tools": [compiler_tool_definition()],
            "tool_choice": "auto",
            "max_completion_tokens": limits.max_completion_tokens_per_call,
            "provider_timeout_s": limits.provider_timeout_s,
        }
        turn_started = monotonic()
        try:
            response = provider(request)
        except ProviderCallFailure as exc:
            return finish(
                "provider_failure",
                control_error=exc.failure_type,
                control_evidence={
                    "failure_type": exc.failure_type,
                    "message": exc.message[:2000],
                },
                raw_control_request=exc.raw_request,
                raw_control_error=exc.raw_error,
            )
        except Exception as exc:  # Provider adapters are an experimental boundary.
            failure_type = type(exc).__name__
            return finish(
                "provider_failure",
                control_error=failure_type,
                control_evidence={
                    "failure_type": failure_type,
                    "message": str(exc)[:2000],
                },
            )
        turn_elapsed = max(0.0, monotonic() - turn_started)
        if type(response) is not ProviderTurn:
            return finish("provider_protocol_failure", control_error=type(response).__name__)
        if type(response.raw_response) is not bytes:
            return finish("provider_protocol_failure", control_error="raw_response_not_bytes")
        if not isinstance(response.assistant_message, Mapping):
            return finish("provider_protocol_failure", control_error="message_not_mapping")

        turn_tokens, turn_cost, turn_cost_complete = _usage_values(response.usage)
        total_tokens += turn_tokens
        total_cost += turn_cost
        cost_complete = cost_complete and turn_cost_complete

        if monotonic() - started >= limits.overall_deadline_s:
            turns.append(
                CompilerTurnRecord(
                    turn_number=turn_number,
                    controller_request=request,
                    raw_provider_request=response.raw_request,
                    raw_provider_response=response.raw_response,
                    assistant_message=dict(response.assistant_message),
                    usage=dict(response.usage),
                    provider_metadata=dict(response.provider_metadata),
                    feedback_codes=(),
                    elapsed_s=turn_elapsed,
                )
            )
            return finish("overall_deadline_exhausted")

        terminal, validation, feedback_codes, tool_call_id = _terminal_from_message(
            response.assistant_message,
            contract_index,
        )
        turns.append(
            CompilerTurnRecord(
                turn_number=turn_number,
                controller_request=request,
                raw_provider_request=response.raw_request,
                raw_provider_response=response.raw_response,
                assistant_message=dict(response.assistant_message),
                usage=dict(response.usage),
                provider_metadata=dict(response.provider_metadata),
                feedback_codes=feedback_codes,
                elapsed_s=turn_elapsed,
            )
        )
        if terminal is not None:
            return finish(
                "terminal_submission",
                terminal=terminal,
                validation=validation,
            )

        messages.append(dict(response.assistant_message))
        messages.append(_feedback_message(feedback_codes, tool_call_id))

        if total_tokens >= limits.cumulative_token_stop_threshold:
            return finish("token_stop_threshold_reached")
        if cost_complete and total_cost >= limits.cumulative_cost_stop_threshold_usd:
            return finish("cost_stop_threshold_reached")

    return finish("max_turns_exhausted")


__all__ = (
    "COMPILER_RESULT_SCHEMA",
    "COMPILER_RESULT_SCHEMA_ID",
    "COMPILER_TOOL_PARAMETERS",
    "CompilerSessionResult",
    "CompilerTurnRecord",
    "EVALUATION_REPORT_SCHEMA",
    "EVALUATION_REPORT_SCHEMA_ID",
    "EVALUATOR_TOOL_PARAMETERS",
    "EvaluatorAttemptResult",
    "ObservationDecision",
    "ProviderCallFailure",
    "ProviderTurn",
    "SessionLimits",
    "TerminalValidationResult",
    "TraceError",
    "classify_observation",
    "compiler_tool_definition",
    "evaluator_result_from_report",
    "evaluator_tool_definition",
    "run_evaluator_once",
    "run_compiler_session",
    "validate_terminal_submission",
)
