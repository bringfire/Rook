"""One-shot public composition for the sealed validation kernel."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union

from .control import (
    ArtifactRole,
    FailureStage,
    ValidationControlFailure,
    make_control_failure,
)
from .invocation import (
    TrustedValidationBundleInput,
    _ValidationExecutionContext,
    _build_validation_execution_context,
)
from .phase_engine import (
    _AuditedPhaseExecution,
    _execute_phase_program_with_audit,
)
from .program import SealedValidationProgram
from .reporting import (
    PublishedValidationReport,
    _AuditedReportSeal,
    _seal_validation_report_with_audit,
)
from .schema_profile import SchemaEvaluationReceipt


ValidationResult = Union[
    PublishedValidationReport,
    ValidationControlFailure,
]

_AUDIT_ISSUER_CAPABILITY = object()


class _ValidationExecutionAudit:
    """Kernel-issued evidence for the exact ordered schema attempts."""

    __slots__ = (
        "program_id",
        "program_fingerprint",
        "schema_evaluation_receipts",
        "__issuer_capability",
    )

    program_id: str | None
    program_fingerprint: str | None
    schema_evaluation_receipts: tuple[SchemaEvaluationReceipt, ...]

    def __init__(self) -> None:
        raise TypeError("validation execution audits are kernel-issued")

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError("validation execution audits are immutable")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("validation execution audits are immutable")

    def __copy__(self) -> object:
        raise TypeError("validation execution audits cannot be copied")

    def __deepcopy__(self, memo: object) -> object:
        raise TypeError("validation execution audits cannot be copied")

    def __reduce__(self) -> object:
        raise TypeError("validation execution audits cannot be serialized")

    def __reduce_ex__(self, protocol: int) -> object:
        raise TypeError("validation execution audits cannot be serialized")


@dataclass(frozen=True, slots=True)
class _AuditedValidationOutcome:
    public_result: ValidationResult
    audit: _ValidationExecutionAudit

    def __post_init__(self) -> None:
        if not isinstance(
            self.public_result,
            (PublishedValidationReport, ValidationControlFailure),
        ):
            raise TypeError("audited outcome requires a public validation result")
        if not _has_audit_issuer_capability(self.audit):
            raise TypeError("audited outcome requires a kernel-issued audit")


def _has_audit_issuer_capability(value: object) -> bool:
    if type(value) is not _ValidationExecutionAudit:
        return False
    try:
        capability = object.__getattribute__(
            value,
            "_ValidationExecutionAudit__issuer_capability",
        )
    except AttributeError:
        return False
    return capability is _AUDIT_ISSUER_CAPABILITY


def _issue_validation_execution_audit(
    *,
    program_id: str | None,
    program_fingerprint: str | None,
    receipts: tuple[SchemaEvaluationReceipt, ...],
) -> _ValidationExecutionAudit:
    if program_id is not None and type(program_id) is not str:
        raise TypeError("audit program ID must be an exact string")
    if program_fingerprint is not None and type(program_fingerprint) is not str:
        raise TypeError("audit program fingerprint must be an exact string")
    if type(receipts) is not tuple or any(
        type(receipt) is not SchemaEvaluationReceipt for receipt in receipts
    ):
        raise TypeError("audit receipts must be an exact immutable receipt tuple")
    audit = object.__new__(_ValidationExecutionAudit)
    object.__setattr__(audit, "program_id", program_id)
    object.__setattr__(audit, "program_fingerprint", program_fingerprint)
    object.__setattr__(audit, "schema_evaluation_receipts", receipts)
    object.__setattr__(
        audit,
        "_ValidationExecutionAudit__issuer_capability",
        _AUDIT_ISSUER_CAPABILITY,
    )
    return audit


def _is_validation_execution_audit(
    value: object,
    program: object,
) -> bool:
    """Check private audit authority and its exact sealed-program binding."""

    if (
        not _has_audit_issuer_capability(value)
        or type(program) is not SealedValidationProgram
    ):
        return False
    audit = value
    return (
        audit.program_id == program.program_id
        and audit.program_fingerprint == program.program_fingerprint
        and type(audit.schema_evaluation_receipts) is tuple
        and all(
            type(receipt) is SchemaEvaluationReceipt
            for receipt in audit.schema_evaluation_receipts
        )
    )


def _outcome_without_phase_audit(
    result: ValidationResult,
) -> _AuditedValidationOutcome:
    return _AuditedValidationOutcome(
        public_result=result,
        audit=_issue_validation_execution_audit(
            program_id=result.program_id,
            program_fingerprint=result.program_fingerprint,
            receipts=(),
        ),
    )


def _outcome_for_program(
    result: ValidationResult,
    program: SealedValidationProgram,
    receipts: tuple[SchemaEvaluationReceipt, ...],
) -> _AuditedValidationOutcome:
    return _AuditedValidationOutcome(
        public_result=result,
        audit=_issue_validation_execution_audit(
            program_id=program.program_id,
            program_fingerprint=program.program_fingerprint,
            receipts=receipts,
        ),
    )


def _has_exact_receipts(value: object) -> bool:
    return type(value) is tuple and all(
        type(receipt) is SchemaEvaluationReceipt for receipt in value
    )


def _phase_audit_integrity_failure(
    context: _ValidationExecutionContext,
) -> ValidationControlFailure:
    program = context.invocation.program
    return make_control_failure(
        failure_stage=FailureStage.VALIDATION,
        code="validator_integrity_failure",
        artifact_role=ArtifactRole.PHASE_ENGINE,
        program_id=program.program_id,
        program_fingerprint=program.program_fingerprint,
        subject_path=None,
        message="Validator integrity check failed.",
        detail=b"phase_execution_audit_contract",
    )


def _report_audit_integrity_failure(
    context: _ValidationExecutionContext,
) -> ValidationControlFailure:
    program = context.invocation.program
    return make_control_failure(
        failure_stage=FailureStage.VALIDATION,
        code="validator_integrity_failure",
        artifact_role=ArtifactRole.REPORT_SEAL,
        program_id=program.program_id,
        program_fingerprint=program.program_fingerprint,
        subject_path=None,
        message="Validator integrity check failed.",
        detail=b"report_seal_audit_contract",
    )


def _validate_artifacts_with_audit(
    program: SealedValidationProgram,
    raw_recipe_bytes: bytes,
    trusted_validation_bundle: TrustedValidationBundleInput,
) -> _AuditedValidationOutcome:
    """Validate once while retaining private ordered schema-attempt evidence."""

    context = _build_validation_execution_context(
        program,
        raw_recipe_bytes,
        trusted_validation_bundle,
    )
    if isinstance(context, ValidationControlFailure):
        return _outcome_without_phase_audit(context)

    phase_execution = _execute_phase_program_with_audit(context)
    if (
        type(phase_execution) is not _AuditedPhaseExecution
        or not _has_exact_receipts(
            phase_execution.schema_evaluation_receipts
        )
    ):
        return _outcome_without_phase_audit(
            _phase_audit_integrity_failure(context)
        )
    phase_result = phase_execution.public_result
    phase_receipts = phase_execution.schema_evaluation_receipts
    if isinstance(phase_result, ValidationControlFailure):
        return _outcome_for_program(phase_result, program, phase_receipts)
    if type(phase_result) is not tuple:
        return _outcome_for_program(
            _phase_audit_integrity_failure(context), program, ()
        )

    report_seal = _seal_validation_report_with_audit(context, phase_result)
    if (
        type(report_seal) is not _AuditedReportSeal
        or not _has_exact_receipts(report_seal.schema_evaluation_receipts)
        or not isinstance(
            report_seal.public_result,
            (PublishedValidationReport, ValidationControlFailure),
        )
    ):
        return _outcome_for_program(
            _report_audit_integrity_failure(context),
            program,
            phase_receipts,
        )
    receipts = phase_receipts + report_seal.schema_evaluation_receipts
    return _outcome_for_program(
        report_seal.public_result,
        program,
        receipts,
    )


def validate_artifacts(
    program: SealedValidationProgram,
    raw_recipe_bytes: bytes,
    trusted_validation_bundle: TrustedValidationBundleInput,
) -> ValidationResult:
    """Return only the public terminal result from one audited execution."""

    return _validate_artifacts_with_audit(
        program,
        raw_recipe_bytes,
        trusted_validation_bundle,
    ).public_result


__all__ = (
    "ValidationResult",
    "validate_artifacts",
)
