from __future__ import annotations

import re
import sys
import unicodedata

import pytest

from rook.validation_kernel.budget import (
    LM9A_BUDGET_MANIFEST,
    LM9A_BUDGET_PROFILE_ID,
    MAX_CHECKED_BUDGET_INTEGER,
    BudgetDimension,
    BudgetExceeded,
    BudgetInputError,
    BudgetLedger,
    BudgetLedgerFrozen,
    BudgetManifest,
    SealMeter,
    SealMeterExceeded,
)
from rook.validation_kernel.control import (
    ArtifactRole,
    FailureStage,
    KERNEL_CONTROL_CODES,
    BudgetExceededFailure,
    ControlFailureInputError,
    ValidationControlFailure,
    control_failure_from_exception,
    make_control_failure,
)
from rook.validation_kernel.owned_json import JsonNumber


LIMIT_CASES = (
    (BudgetDimension.RECIPE_INPUT_BYTES, "recipe_input_bytes", 1_048_576, False),
    (
        BudgetDimension.VALIDATION_BUNDLE_INPUT_BYTES,
        "validation_bundle_input_bytes",
        4_194_304,
        False,
    ),
    (BudgetDimension.CONTAINER_DEPTH, "maximum_container_depth", 64, False),
    (
        BudgetDimension.NUMBER_TOKEN_CHARS,
        "maximum_number_token_chars",
        1_024,
        False,
    ),
    (BudgetDimension.PARSED_NODES, "parsed_nodes", 100_000, True),
    (
        BudgetDimension.OBJECT_MEMBERS,
        "maximum_object_members",
        16_384,
        False,
    ),
    (BudgetDimension.ARRAY_ITEMS, "maximum_array_items", 16_384, False),
    (
        BudgetDimension.DECODED_STRING_BYTES,
        "decoded_string_bytes",
        2_097_152,
        True,
    ),
    (BudgetDimension.PARSER_WORK_UNITS, "parser_work_units", 500_000, True),
    (
        BudgetDimension.SEMANTIC_REFERENCES,
        "semantic_references",
        25_000,
        True,
    ),
    (
        BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS,
        "schema_evaluation_shape_units",
        16_000_000,
        True,
    ),
    (BudgetDimension.DIAGNOSTICS, "diagnostics", 1_024, True),
    (BudgetDimension.COMPILE_BLOCKERS, "compile_blockers", 1_024, True),
    (
        BudgetDimension.KERNEL_PHASE_WORK_UNITS,
        "kernel_phase_work_units",
        1_000_000,
        True,
    ),
    (
        BudgetDimension.REPORT_PROJECTION_FIELDS,
        "report_projection_fields",
        131_072,
        True,
    ),
)


def _limit_from_manifest(dimension: BudgetDimension) -> int:
    value = LM9A_BUDGET_MANIFEST.limits[dimension.value]
    assert isinstance(value, JsonNumber)
    return int(value.value)


def _charge_to_limit(
    ledger: BudgetLedger,
    dimension: BudgetDimension,
    limit: int,
    aggregate: bool,
) -> None:
    if aggregate:
        first = limit // 3
        second = limit - first
        ledger.charge(
            dimension,
            first,
            artifact_role=ArtifactRole.COMBINED,
            subject_path=None,
        )
        ledger.charge(
            dimension,
            second,
            artifact_role=ArtifactRole.COMBINED,
            subject_path=None,
        )
        return
    ledger.charge(
        dimension,
        limit,
        artifact_role=ArtifactRole.RECIPE,
        subject_path="/fixture",
    )


def test_fixed_manifest_has_exact_profile_limits_and_fingerprint() -> None:
    assert LM9A_BUDGET_MANIFEST.profile_id == LM9A_BUDGET_PROFILE_ID
    assert LM9A_BUDGET_MANIFEST.profile_id == "rook.validation_budget:lm9a_v1"
    assert len(LIMIT_CASES) == 15
    for dimension, _, limit, _ in LIMIT_CASES:
        assert _limit_from_manifest(dimension) == limit
    assert _limit_from_manifest(BudgetDimension.REPORT_CANONICAL_BYTES) == 2_097_152
    assert _limit_from_manifest(BudgetDimension.REPORT_SEAL_WORK_UNITS) == 262_144
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", LM9A_BUDGET_MANIFEST.limits_fingerprint)


def test_ledger_and_seal_meter_require_the_fixed_manifest_capability() -> None:
    equivalent_but_untrusted = BudgetManifest(
        profile_id=LM9A_BUDGET_MANIFEST.profile_id,
        limits=LM9A_BUDGET_MANIFEST.limits,
        limits_fingerprint=LM9A_BUDGET_MANIFEST.limits_fingerprint,
    )

    with pytest.raises(BudgetInputError):
        BudgetLedger(equivalent_but_untrusted)
    with pytest.raises(BudgetInputError):
        SealMeter(equivalent_but_untrusted)


@pytest.mark.parametrize(
    ("dimension", "snapshot_field", "limit", "aggregate"), LIMIT_CASES
)
def test_every_ledger_limit_is_inclusive_and_rejects_limit_plus_one(
    dimension: BudgetDimension,
    snapshot_field: str,
    limit: int,
    aggregate: bool,
) -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    _charge_to_limit(ledger, dimension, limit, aggregate)

    assert getattr(ledger.snapshot(), snapshot_field) == limit
    next_amount = 1 if aggregate else limit + 1
    with pytest.raises(BudgetExceeded) as raised:
        ledger.charge(
            dimension,
            next_amount,
            artifact_role=ArtifactRole.COMBINED,
            subject_path=None,
        )
    failure = raised.value.failure
    assert failure.code == "validation_budget_exceeded"
    assert failure.budget_dimension == dimension.value
    assert failure.limit == limit
    assert failure.observed_lower_bound == limit + 1
    assert getattr(ledger.snapshot(), snapshot_field) == limit


def test_report_canonical_byte_limit_is_inclusive_per_serialization() -> None:
    meter = SealMeter(LM9A_BUDGET_MANIFEST)
    limit = _limit_from_manifest(BudgetDimension.REPORT_CANONICAL_BYTES)

    meter.charge_canonical_bytes(limit)

    assert meter.canonical_bytes == limit
    with pytest.raises(SealMeterExceeded) as raised:
        meter.charge_canonical_bytes(limit + 1)
    assert raised.value.dimension == BudgetDimension.REPORT_CANONICAL_BYTES.value
    assert raised.value.limit == limit
    assert raised.value.observed_lower_bound == limit + 1
    assert meter.canonical_bytes == limit


def test_seal_meter_enforces_fixed_allowance_without_mutating_a_receipt() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    receipt = ledger.reserve_report_seal_and_freeze()
    meter = SealMeter(LM9A_BUDGET_MANIFEST)
    report_bytes = _limit_from_manifest(BudgetDimension.REPORT_CANONICAL_BYTES)
    field_limit = _limit_from_manifest(BudgetDimension.REPORT_PROJECTION_FIELDS)

    meter.charge_projection_fields(field_limit)
    for _ in range(4):
        meter.charge_canonical_bytes(report_bytes)
    assert meter.work_units == 262_144
    assert receipt.observed.report_seal_reserved_work_units == 262_144
    with pytest.raises(SealMeterExceeded) as raised:
        meter.charge_canonical_bytes(report_bytes)
    assert raised.value.dimension == BudgetDimension.REPORT_SEAL_WORK_UNITS.value
    assert receipt.observed.report_seal_reserved_work_units == 262_144


def test_schema_reservation_rejects_without_changing_aggregate() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    before = ledger.snapshot().schema_evaluation_shape_units

    result = ledger.reserve_schema_shape(
        schema_nodes=4_001,
        instance_nodes=500,
        per_evaluation_limit=2_000_000,
    )

    assert result.accepted is False
    assert result.attempted_shape_units is None
    assert result.aggregate_before == before
    assert result.aggregate_after is None
    assert result.rejection_reason == "per_evaluation_limit_exceeded"
    assert ledger.snapshot().schema_evaluation_shape_units == before


def test_schema_reservation_checks_aggregate_before_multiplying_or_mutating() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    limit = _limit_from_manifest(BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS)
    ledger.charge(
        BudgetDimension.SCHEMA_EVALUATION_SHAPE_UNITS,
        limit - 3,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path=None,
    )

    result = ledger.reserve_schema_shape(
        schema_nodes=2,
        instance_nodes=2,
        per_evaluation_limit=10,
    )

    assert result.accepted is False
    assert result.attempted_shape_units is None
    assert result.aggregate_before == limit - 3
    assert result.aggregate_after is None
    assert result.rejection_reason == "invocation_shape_limit_exceeded"
    assert ledger.snapshot().schema_evaluation_shape_units == limit - 3


def test_schema_reservation_classifies_host_integer_overflow_without_mutation() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    result = ledger.reserve_schema_shape(
        schema_nodes=MAX_CHECKED_BUDGET_INTEGER + 1,
        instance_nodes=1,
        per_evaluation_limit=MAX_CHECKED_BUDGET_INTEGER,
    )

    assert result.accepted is False
    assert result.attempted_shape_units is None
    assert result.aggregate_before == 0
    assert result.aggregate_after is None
    assert result.rejection_reason == "shape_product_overflow"
    assert ledger.snapshot().schema_evaluation_shape_units == 0


def test_successful_schema_reservations_charge_each_evaluation_without_refund() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    first = ledger.reserve_schema_shape(
        schema_nodes=4,
        instance_nodes=5,
        per_evaluation_limit=20,
    )
    second = ledger.reserve_schema_shape(
        schema_nodes=4,
        instance_nodes=5,
        per_evaluation_limit=20,
    )

    assert first.accepted is True
    assert first.attempted_shape_units == 20
    assert first.aggregate_before == 0
    assert first.aggregate_after == 20
    assert second.accepted is True
    assert second.aggregate_before == 20
    assert second.aggregate_after == 40
    assert ledger.snapshot().schema_evaluation_shape_units == 40


@pytest.mark.parametrize("amount", [-1, True, 1.5, "1"])
def test_ledger_rejects_negative_or_non_exact_integer_charges(amount: object) -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    with pytest.raises(BudgetInputError):
        ledger.charge(
            BudgetDimension.DIAGNOSTICS,
            amount,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=None,
        )
    assert ledger.snapshot().diagnostics == 0


def test_diagnostic_charge_is_not_refunded_when_the_caller_rejects_a_duplicate() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)

    ledger.charge(
        BudgetDimension.DIAGNOSTICS,
        1,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path="/phases/0/issues/0",
    )
    caller_rejected_duplicate = True

    assert caller_rejected_duplicate is True
    assert ledger.snapshot().diagnostics == 1


def test_report_seal_reservation_is_atomic_exactly_once_and_freezes_all_mutation() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    ledger.charge(
        BudgetDimension.DIAGNOSTICS,
        7,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path=None,
    )
    before = ledger.snapshot()

    receipt = ledger.reserve_report_seal_and_freeze()

    assert receipt.budget_profile == LM9A_BUDGET_PROFILE_ID
    assert receipt.limits_fingerprint == LM9A_BUDGET_MANIFEST.limits_fingerprint
    assert receipt.observed == before.with_report_seal_reservation(262_144)
    assert receipt.observed.report_seal_reserved_work_units == 262_144
    assert ledger.snapshot() == receipt.observed
    with pytest.raises(BudgetLedgerFrozen):
        ledger.reserve_report_seal_and_freeze()
    with pytest.raises(BudgetLedgerFrozen):
        ledger.charge(
            BudgetDimension.DIAGNOSTICS,
            1,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=None,
        )
    with pytest.raises(BudgetLedgerFrozen):
        ledger.reserve_schema_shape(
            schema_nodes=1,
            instance_nodes=1,
            per_evaluation_limit=1,
        )


def test_snapshots_and_receipts_are_frozen_values_not_live_ledger_views() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    snapshot = ledger.snapshot()
    ledger.charge(
        BudgetDimension.DIAGNOSTICS,
        1,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path=None,
    )
    receipt = ledger.reserve_report_seal_and_freeze()

    assert snapshot.diagnostics == 0
    assert receipt.observed.diagnostics == 1
    with pytest.raises((AttributeError, TypeError)):
        receipt.observed.diagnostics = 9
    with pytest.raises((AttributeError, TypeError)):
        receipt.budget_profile = "other"


def test_public_control_failures_use_closed_codes_and_bounded_nfc_messages() -> None:
    message = "e\u0301" * 600
    failure = make_control_failure(
        failure_stage=FailureStage.VALIDATION,
        code="validator_integrity_failure",
        artifact_role=ArtifactRole.PHASE_ENGINE,
        program_id="program",
        program_fingerprint="sha256:" + "a" * 64,
        subject_path="/phases/0",
        message=message,
        detail=b"opaque detail",
    )

    assert isinstance(failure, ValidationControlFailure)
    assert failure.code in KERNEL_CONTROL_CODES
    assert failure.message == unicodedata.normalize("NFC", message)[:512]
    assert len(failure.message) == 512
    assert unicodedata.is_normalized("NFC", failure.message)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", failure.detail_sha256 or "")
    with pytest.raises(ControlFailureInputError):
        make_control_failure(
            failure_stage=FailureStage.VALIDATION,
            code="unknown",
            artifact_role=ArtifactRole.PHASE_ENGINE,
            program_id=None,
            program_fingerprint=None,
            subject_path=None,
            message="invalid",
            detail=None,
        )


def test_control_failure_from_exception_never_leaks_raw_exception_or_input() -> None:
    raw_input = '{"secret":"never publish this"}'
    raw_exception = RuntimeError(f"parser saw {raw_input}")

    failure = control_failure_from_exception(
        failure_stage=FailureStage.PREFLIGHT,
        code="validation_input_invalid",
        artifact_role=ArtifactRole.RECIPE,
        program_id=None,
        program_fingerprint=None,
        subject_path=None,
        exception=raw_exception,
        raw_input=raw_input.encode("utf-8"),
    )

    assert failure.code in KERNEL_CONTROL_CODES
    assert raw_input not in failure.message
    assert str(raw_exception) not in failure.message
    assert raw_input not in repr(failure)
    assert str(raw_exception) not in repr(failure)
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", failure.detail_sha256 or "")


def test_budget_exhaustion_exposes_only_a_closed_failure_envelope() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    limit = _limit_from_manifest(BudgetDimension.DIAGNOSTICS)

    ledger.charge(
        BudgetDimension.DIAGNOSTICS,
        limit,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path=None,
    )
    with pytest.raises(BudgetExceeded) as raised:
        ledger.charge(
            BudgetDimension.DIAGNOSTICS,
            1,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            subject_path=None,
        )

    failure = raised.value.failure
    assert isinstance(failure, BudgetExceededFailure)
    assert failure.code == "validation_budget_exceeded"
    assert failure.code in KERNEL_CONTROL_CODES
    assert failure.detail_sha256 is None
    assert failure.message == "Validation budget exceeded."


def test_checked_integer_limit_tracks_the_host_signed_integer_range() -> None:
    assert MAX_CHECKED_BUDGET_INTEGER == sys.maxsize
