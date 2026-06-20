from __future__ import annotations

from typing import Any, Literal, Sequence


Operation = Literal["create", "update"]
MutationStatus = Literal["created", "written", "failed", "not_attempted"]
MutationMethod = Literal["gh_create_component_then_script", "gh_script_write"]
VerificationStatus = Literal["passed", "failed", "deferred", "unavailable", "not_requested"]
VerificationMethod = Literal["gh_errors", "gh_snapshot_fallback", "none"]
ArtifactStatus = Literal[
    "usable",
    "created_with_errors",
    "written_with_errors",
    "verification_pending",
    "unknown",
]


def _copy_pin_list(value: Sequence[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    return [dict(pin) for pin in value if isinstance(pin, dict)]


def _diagnostics(value: Sequence[Any] | None) -> list[Any]:
    if value is None:
        return []
    return list(value)


def _unknown_count(status: VerificationStatus) -> bool:
    return status in ("deferred", "unavailable", "not_requested")


def derive_verification(
    *,
    component_errors: Sequence[Any] | None,
    component_warnings: Sequence[Any] | None,
    unrelated_error_count: int | None,
    unrelated_warning_count: int | None,
    method: VerificationMethod,
    deferred: bool = False,
    not_requested: bool = False,
    unavailable_note: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Derive target-scoped verification evidence for a GH script receipt."""
    if deferred:
        status: VerificationStatus = "deferred"
        return {
            "status": status,
            "method": "none",
            "target_error_count": None,
            "target_warning_count": None,
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "note": note,
        }

    if not_requested:
        status = "not_requested"
        return {
            "status": status,
            "method": "none",
            "target_error_count": None,
            "target_warning_count": None,
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "note": note,
        }

    if unavailable_note:
        status = "unavailable"
        return {
            "status": status,
            "method": method,
            "target_error_count": None,
            "target_warning_count": None,
            "unrelated_error_count": None,
            "unrelated_warning_count": None,
            "note": unavailable_note,
        }

    errors = _diagnostics(component_errors)
    warnings = _diagnostics(component_warnings)
    status = "failed" if errors else "passed"
    return {
        "status": status,
        "method": method,
        "target_error_count": len(errors),
        "target_warning_count": len(warnings),
        "unrelated_error_count": unrelated_error_count if unrelated_error_count is not None else 0,
        "unrelated_warning_count": unrelated_warning_count if unrelated_warning_count is not None else 0,
        "note": note,
    }


def derive_artifact_status(
    operation: Operation,
    verification_status: VerificationStatus,
) -> ArtifactStatus:
    if verification_status == "passed":
        return "usable"
    if verification_status == "failed":
        return "created_with_errors" if operation == "create" else "written_with_errors"
    if verification_status in ("deferred", "not_requested"):
        return "verification_pending"
    return "unknown"


def build_script_receipt(
    *,
    operation: Operation,
    language: str,
    mutation_status: MutationStatus,
    mutation_method: MutationMethod,
    component_guid: str,
    mode_used: str | None,
    wrapped: bool | None,
    pins_in: Sequence[dict[str, Any]] | None,
    pins_out: Sequence[dict[str, Any]] | None,
    input_code_length: int,
    prepared_source_length: int,
    full_source_detected: bool,
    component_errors: Sequence[Any] | None,
    component_warnings: Sequence[Any] | None,
    unrelated_error_count: int | None,
    unrelated_warning_count: int | None,
    verification_method: VerificationMethod,
    requested_guid: str | None = None,
    include_requested_guid: bool = False,
    recovery_hint: str | None = None,
    deferred: bool = False,
    not_requested: bool = False,
    unavailable_note: str | None = None,
    verification_note: str | None = None,
    mutation_note: str | None = None,
) -> dict[str, Any]:
    verification = derive_verification(
        component_errors=component_errors,
        component_warnings=component_warnings,
        unrelated_error_count=unrelated_error_count,
        unrelated_warning_count=unrelated_warning_count,
        method=verification_method,
        deferred=deferred,
        not_requested=not_requested,
        unavailable_note=unavailable_note,
        note=verification_note,
    )
    verification_status = verification["status"]
    diagnostics_unknown = _unknown_count(verification_status)

    repair_anchor: dict[str, Any] = {
        "component_guid": component_guid,
        "language": language,
        "mode_used": mode_used,
        "wrapped": wrapped,
        "pins_in": _copy_pin_list(pins_in),
        "pins_out": _copy_pin_list(pins_out),
        "source_shape": {
            "input_code_length": input_code_length,
            "prepared_source_length": prepared_source_length,
            "full_source_detected": full_source_detected,
        },
        "target_errors": None if diagnostics_unknown else _diagnostics(component_errors),
        "target_warnings": None if diagnostics_unknown else _diagnostics(component_warnings),
        "recovery_hint": recovery_hint,
    }
    if requested_guid and (include_requested_guid or requested_guid != component_guid):
        repair_anchor["requested_guid"] = requested_guid

    return {
        "version": 1,
        "operation": operation,
        "language": language,
        "mutation": {
            "status": mutation_status,
            "method": mutation_method,
            "component_guid": component_guid,
            "note": mutation_note,
        },
        "verification": verification,
        "artifact_status": derive_artifact_status(operation, verification_status),
        "repair_anchor": repair_anchor,
    }
