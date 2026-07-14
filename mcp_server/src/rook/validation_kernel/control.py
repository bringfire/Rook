"""Closed, bounded control-failure values for the validation kernel."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from enum import Enum


KERNEL_CONTROL_CODES = (
    "validation_input_invalid",
    "validation_budget_exceeded",
    "validation_constructability_failed",
    "validator_identity_unavailable",
    "validator_integrity_failure",
    "validator_internal_failure",
)

_SHA256_PATTERN = re.compile(r"sha256:[0-9a-f]{64}\Z")
_MAX_CONTROL_MESSAGE_CODE_POINTS = 512


class ControlFailureInputError(ValueError):
    """A caller attempted to construct a control failure outside its contract."""


class FailureStage(str, Enum):
    """The closed stages at which a principal control failure can arise."""

    PREFLIGHT = "preflight"
    VALIDATION = "validation"


class ArtifactRole(str, Enum):
    """The closed artifact roles named by kernel control failures."""

    VALIDATION_PROGRAM = "validation_program"
    RECIPE = "recipe"
    VALIDATION_BUNDLE = "validation_bundle"
    COMBINED = "combined"
    PHASE_ENGINE = "phase_engine"
    REPORT_SEAL = "report_seal"


class BudgetDimension(str, Enum):
    """The fixed budget dimensions used by the invocation ledger."""

    RECIPE_INPUT_BYTES = "recipe_input_bytes"
    VALIDATION_BUNDLE_INPUT_BYTES = "validation_bundle_input_bytes"
    CONTAINER_DEPTH = "container_depth"
    NUMBER_TOKEN_CHARS = "number_token_chars"
    PARSED_NODES = "parsed_nodes"
    OBJECT_MEMBERS = "object_members"
    ARRAY_ITEMS = "array_items"
    DECODED_STRING_BYTES = "decoded_string_bytes"
    PARSER_WORK_UNITS = "parser_work_units"
    SEMANTIC_REFERENCES = "semantic_references"
    SCHEMA_EVALUATION_SHAPE_UNITS = "schema_evaluation_shape_units"
    DIAGNOSTICS = "diagnostics"
    COMPILE_BLOCKERS = "compile_blockers"
    KERNEL_PHASE_WORK_UNITS = "kernel_phase_work_units"
    REPORT_CANONICAL_BYTES = "report_canonical_bytes"
    REPORT_PROJECTION_FIELDS = "report_projection_fields"
    REPORT_SEAL_WORK_UNITS = "report_seal_work_units"


_DEFAULT_MESSAGES = {
    "validation_input_invalid": "Validation input is invalid.",
    "validation_budget_exceeded": "Validation budget exceeded.",
    "validation_constructability_failed": "Validation report cannot be constructed.",
    "validator_identity_unavailable": "Validator identity is unavailable.",
    "validator_integrity_failure": "Validator integrity check failed.",
    "validator_internal_failure": "Validator internal failure.",
}


def _closed_value(value: object, enum_type: type[Enum], field_name: str) -> str:
    if isinstance(value, enum_type):
        return str(value.value)
    if type(value) is str and value in {member.value for member in enum_type}:
        return value
    raise ControlFailureInputError(f"invalid {field_name}")


def _optional_exact_string(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ControlFailureInputError(f"invalid {field_name}")
    return value


def _normalize_message(message: object) -> str:
    if type(message) is not str:
        raise ControlFailureInputError("control failure message must be an exact str")
    normalized = unicodedata.normalize("NFC", message)[:_MAX_CONTROL_MESSAGE_CODE_POINTS]
    try:
        normalized.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        raise ControlFailureInputError("control failure message has invalid Unicode") from None
    return normalized


def _optional_detail_hash(value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not _SHA256_PATTERN.fullmatch(value):
        raise ControlFailureInputError("invalid detail SHA-256")
    return value


def _sha256_prefixed(detail: bytes) -> str:
    return f"sha256:{hashlib.sha256(detail).hexdigest()}"


@dataclass(frozen=True, slots=True)
class ValidationControlFailure:
    """An immutable, public-safe failure emitted before a principal report."""

    failure_stage: str
    code: str
    artifact_role: str
    program_id: str | None
    program_fingerprint: str | None
    subject_path: str | None
    message: str
    detail_sha256: str | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "failure_stage", _closed_value(self.failure_stage, FailureStage, "failure stage")
        )
        if type(self.code) is not str or self.code not in KERNEL_CONTROL_CODES:
            raise ControlFailureInputError("invalid control failure code")
        object.__setattr__(
            self, "artifact_role", _closed_value(self.artifact_role, ArtifactRole, "artifact role")
        )
        program_id = _optional_exact_string(self.program_id, "program id")
        program_fingerprint = _optional_exact_string(
            self.program_fingerprint, "program fingerprint"
        )
        subject_path = _optional_exact_string(self.subject_path, "subject path")
        if subject_path is not None and not subject_path.startswith("/"):
            raise ControlFailureInputError("subject path must be an RFC 6901 pointer")
        if program_fingerprint is not None and not _SHA256_PATTERN.fullmatch(program_fingerprint):
            raise ControlFailureInputError("invalid program fingerprint")
        object.__setattr__(self, "program_id", program_id)
        object.__setattr__(self, "program_fingerprint", program_fingerprint)
        object.__setattr__(self, "subject_path", subject_path)
        object.__setattr__(self, "message", _normalize_message(self.message))
        object.__setattr__(self, "detail_sha256", _optional_detail_hash(self.detail_sha256))


@dataclass(frozen=True, slots=True)
class BudgetExceededFailure(ValidationControlFailure):
    """A control failure with the first known budget overrun."""

    budget_dimension: str
    limit: int
    observed_lower_bound: int

    def __post_init__(self) -> None:
        super(BudgetExceededFailure, self).__post_init__()
        object.__setattr__(
            self,
            "budget_dimension",
            _closed_value(self.budget_dimension, BudgetDimension, "budget dimension"),
        )
        if type(self.limit) is not int or type(self.observed_lower_bound) is not int:
            raise ControlFailureInputError("budget bounds must be exact integers")
        if self.limit < 0 or self.observed_lower_bound <= self.limit:
            raise ControlFailureInputError("invalid budget bounds")


def make_control_failure(
    *,
    failure_stage: FailureStage | str,
    code: str,
    artifact_role: ArtifactRole | str,
    program_id: str | None,
    program_fingerprint: str | None,
    subject_path: str | None,
    message: str,
    detail: bytes | None,
) -> ValidationControlFailure:
    """Create a bounded failure while retaining variable detail only as a hash."""

    if detail is not None and type(detail) is not bytes:
        raise ControlFailureInputError("control failure detail must be exact bytes")
    return ValidationControlFailure(
        failure_stage=failure_stage,
        code=code,
        artifact_role=artifact_role,
        program_id=program_id,
        program_fingerprint=program_fingerprint,
        subject_path=subject_path,
        message=message,
        detail_sha256=None if detail is None else _sha256_prefixed(detail),
    )


def control_failure_from_exception(
    *,
    failure_stage: FailureStage | str,
    code: str,
    artifact_role: ArtifactRole | str,
    program_id: str | None,
    program_fingerprint: str | None,
    subject_path: str | None,
    exception: BaseException,
    raw_input: bytes | None,
) -> ValidationControlFailure:
    """Convert caught internal state into a generic message and opaque detail hash."""

    if not isinstance(exception, BaseException):
        raise ControlFailureInputError("exception must derive from BaseException")
    if raw_input is not None and type(raw_input) is not bytes:
        raise ControlFailureInputError("raw input must be exact bytes")
    if type(code) is not str or code not in KERNEL_CONTROL_CODES:
        raise ControlFailureInputError("invalid control failure code")

    exception_type = f"{type(exception).__module__}.{type(exception).__qualname__}".encode(
        "utf-8"
    )
    detail = exception_type if raw_input is None else exception_type + b"\0" + raw_input
    return make_control_failure(
        failure_stage=failure_stage,
        code=code,
        artifact_role=artifact_role,
        program_id=program_id,
        program_fingerprint=program_fingerprint,
        subject_path=subject_path,
        message=_DEFAULT_MESSAGES[code],
        detail=detail,
    )


__all__ = (
    "ArtifactRole",
    "BudgetDimension",
    "BudgetExceededFailure",
    "ControlFailureInputError",
    "FailureStage",
    "KERNEL_CONTROL_CODES",
    "ValidationControlFailure",
    "control_failure_from_exception",
    "make_control_failure",
)
