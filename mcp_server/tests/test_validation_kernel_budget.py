from __future__ import annotations

import inspect
import json
import re
import sys
import threading
import unicodedata
from dataclasses import asdict, replace

import pytest

import rook.validation_kernel as validation_kernel
from rook.validation_kernel import budget as budget_module
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
    BudgetReceipt,
    SealMeter,
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


SECRET_SENTINEL = "TASK2_SECRET_SENTINEL_7d31e4"
CLOSED_CONTROL_MESSAGES = {
    "validation_input_invalid": "Validation input is invalid.",
    "validation_budget_exceeded": "Validation budget exceeded.",
    "validation_constructability_failed": "Validation report cannot be constructed.",
    "validator_identity_unavailable": "Validator identity is unavailable.",
    "validator_integrity_failure": "Validator integrity check failed.",
    "validator_internal_failure": "Validator internal failure.",
}


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


def _frozen_receipt() -> tuple[BudgetLedger, BudgetReceipt]:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    return ledger, ledger.reserve_report_seal_and_freeze()


def test_fixed_manifest_has_exact_profile_limits_and_fingerprint() -> None:
    assert LM9A_BUDGET_MANIFEST.profile_id == LM9A_BUDGET_PROFILE_ID
    assert LM9A_BUDGET_MANIFEST.profile_id == "rook.validation_budget:lm9a_v1"
    assert len(LIMIT_CASES) == 15
    for dimension, _, limit, _ in LIMIT_CASES:
        assert _limit_from_manifest(dimension) == limit
    assert _limit_from_manifest(BudgetDimension.REPORT_CANONICAL_BYTES) == 2_097_152
    assert _limit_from_manifest(BudgetDimension.REPORT_SEAL_WORK_UNITS) == 262_144
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", LM9A_BUDGET_MANIFEST.limits_fingerprint)


def test_ledger_requires_fixed_manifest_and_seal_meter_rejects_manifest_only() -> None:
    equivalent_but_untrusted = BudgetManifest(
        profile_id=LM9A_BUDGET_MANIFEST.profile_id,
        limits=LM9A_BUDGET_MANIFEST.limits,
        limits_fingerprint=LM9A_BUDGET_MANIFEST.limits_fingerprint,
    )

    with pytest.raises(BudgetInputError):
        BudgetLedger(equivalent_but_untrusted)
    with pytest.raises(BudgetInputError):
        SealMeter(equivalent_but_untrusted)
    with pytest.raises(BudgetInputError):
        SealMeter(LM9A_BUDGET_MANIFEST)


def test_seal_meter_requires_a_frozen_fixed_profile_receipt() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    pre_reservation = BudgetReceipt(
        budget_profile=LM9A_BUDGET_PROFILE_ID,
        limits_fingerprint=LM9A_BUDGET_MANIFEST.limits_fingerprint,
        observed=ledger.snapshot(),
    )
    with pytest.raises(BudgetInputError):
        SealMeter(pre_reservation)

    _, receipt = _frozen_receipt()
    wrong_reservation = replace(
        receipt,
        observed=receipt.observed.with_report_seal_reservation(262_143),
    )
    wrong_profile = replace(receipt, budget_profile="rook.validation_budget:forged")
    wrong_fingerprint = replace(receipt, limits_fingerprint="sha256:" + "0" * 64)
    for forged in (wrong_reservation, wrong_profile, wrong_fingerprint):
        with pytest.raises(BudgetInputError):
            SealMeter(forged)

    meter = SealMeter(receipt)
    assert not hasattr(meter, "_ledger")
    assert not hasattr(meter, "_receipt")


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
    _, receipt = _frozen_receipt()
    meter = SealMeter(receipt)
    limit = _limit_from_manifest(BudgetDimension.REPORT_CANONICAL_BYTES)

    meter.charge_canonical_bytes(limit)

    assert meter.canonical_bytes == limit
    with pytest.raises(budget_module._SealMeterExceeded) as raised:
        meter.charge_canonical_bytes(limit + 1)
    assert raised.value.dimension == BudgetDimension.REPORT_CANONICAL_BYTES.value
    assert raised.value.limit == limit
    assert raised.value.observed_lower_bound == limit + 1
    assert meter.canonical_bytes == limit


def test_seal_meter_projection_fields_accepts_exact_and_rejects_131073() -> None:
    _, receipt = _frozen_receipt()
    meter = SealMeter(receipt)
    field_limit = _limit_from_manifest(BudgetDimension.REPORT_PROJECTION_FIELDS)

    meter.charge_projection_fields(field_limit)

    assert meter.projection_fields == 131_072
    with pytest.raises(budget_module._SealMeterExceeded) as raised:
        meter.charge_projection_fields(1)
    assert raised.value.dimension == BudgetDimension.REPORT_PROJECTION_FIELDS.value
    assert raised.value.limit == 131_072
    assert raised.value.observed_lower_bound == 131_073
    assert meter.projection_fields == 131_072


def test_seal_meter_work_accepts_exact_and_rejects_262145_without_receipt_mutation() -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    receipt = ledger.reserve_report_seal_and_freeze()
    meter = SealMeter(receipt)
    receipt_before_metering = receipt
    report_bytes = _limit_from_manifest(BudgetDimension.REPORT_CANONICAL_BYTES)
    field_limit = _limit_from_manifest(BudgetDimension.REPORT_PROJECTION_FIELDS)

    meter.charge_projection_fields(field_limit)
    for _ in range(4):
        meter.charge_canonical_bytes(report_bytes)
    assert meter.work_units == 262_144
    assert receipt.observed.report_seal_reserved_work_units == 262_144
    with pytest.raises(budget_module._SealMeterExceeded) as raised:
        meter.charge_canonical_bytes(1)
    assert raised.value.dimension == BudgetDimension.REPORT_SEAL_WORK_UNITS.value
    assert raised.value.limit == 262_144
    assert raised.value.observed_lower_bound == 262_145
    assert meter.work_units == 262_144
    assert receipt == receipt_before_metering


def test_seal_meter_exhaustion_stays_private_until_task_8_maps_context() -> None:
    private_exception = getattr(budget_module, "_SealMeterExceeded", None)

    assert private_exception is not None
    assert "SealMeterExceeded" not in budget_module.__all__
    assert "_SealMeterExceeded" not in budget_module.__all__
    assert "SealMeterExceeded" not in validation_kernel.__all__
    assert "_SealMeterExceeded" not in validation_kernel.__all__
    documentation = inspect.getdoc(private_exception) or ""
    assert "Task 8" in documentation
    assert "validation_budget_exceeded" in documentation
    assert "artifact_role=report_seal" in documentation
    assert KERNEL_CONTROL_CODES == tuple(CLOSED_CONTROL_MESSAGES)


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


def test_charge_and_report_seal_freeze_are_one_atomic_transition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ledger = BudgetLedger(LM9A_BUDGET_MANIFEST)
    charge_checked_mutability = threading.Event()
    release_charge = threading.Event()
    seal_started = threading.Event()
    seal_finished = threading.Event()
    charge_errors: list[BaseException] = []
    seal_errors: list[BaseException] = []
    receipts: list[BudgetReceipt] = []
    original_ensure_mutable = BudgetLedger._ensure_mutable

    def pause_charge_after_mutability_check(target: BudgetLedger) -> None:
        original_ensure_mutable(target)
        if threading.current_thread().name == "task2-budget-charge":
            charge_checked_mutability.set()
            if not release_charge.wait(timeout=5):
                raise AssertionError("test did not release the paused charge")

    monkeypatch.setattr(
        BudgetLedger,
        "_ensure_mutable",
        pause_charge_after_mutability_check,
    )

    def run_charge() -> None:
        try:
            ledger.charge(
                BudgetDimension.DIAGNOSTICS,
                1,
                artifact_role=ArtifactRole.PHASE_ENGINE,
                subject_path=None,
            )
        except BaseException as error:
            charge_errors.append(error)

    def run_seal() -> None:
        seal_started.set()
        try:
            receipts.append(ledger.reserve_report_seal_and_freeze())
        except BaseException as error:
            seal_errors.append(error)
        finally:
            seal_finished.set()

    charge_thread = threading.Thread(target=run_charge, name="task2-budget-charge")
    seal_thread = threading.Thread(target=run_seal, name="task2-budget-seal")
    charge_thread.start()
    assert charge_checked_mutability.wait(timeout=2)
    seal_thread.start()
    assert seal_started.wait(timeout=2)
    seal_finished.wait(timeout=0.5)
    release_charge.set()
    charge_thread.join(timeout=5)
    seal_thread.join(timeout=5)

    assert not charge_thread.is_alive()
    assert not seal_thread.is_alive()
    assert seal_errors == []
    assert len(receipts) == 1
    receipt = receipts[0]
    if charge_errors:
        assert len(charge_errors) == 1
        assert isinstance(charge_errors[0], BudgetLedgerFrozen)
        assert receipt.observed.diagnostics == 0
    else:
        assert receipt.observed.diagnostics == 1
    assert ledger.snapshot() == receipt.observed


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


def test_control_factory_replaces_caller_message_with_each_codes_closed_message() -> None:
    for code, expected_message in CLOSED_CONTROL_MESSAGES.items():
        caller_message = f"{SECRET_SENTINEL}:{code}:e\u0301"
        failure = make_control_failure(
            failure_stage=FailureStage.VALIDATION,
            code=code,
            artifact_role=ArtifactRole.PHASE_ENGINE,
            program_id="program",
            program_fingerprint="sha256:" + "a" * 64,
            subject_path="/phases/0",
            message=caller_message,
            detail=caller_message.encode("utf-8"),
        )

        serialized_fields = json.dumps(asdict(failure), ensure_ascii=False, sort_keys=True)
        assert isinstance(failure, ValidationControlFailure)
        assert failure.code in KERNEL_CONTROL_CODES
        assert failure.message == expected_message
        assert len(failure.message) <= 512
        assert unicodedata.is_normalized("NFC", failure.message)
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", failure.detail_sha256 or "")
        assert SECRET_SENTINEL not in repr(failure)
        assert SECRET_SENTINEL not in serialized_fields

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


def test_direct_control_dataclass_replaces_raw_message_with_hash_only() -> None:
    failure = ValidationControlFailure(
        failure_stage=FailureStage.PREFLIGHT,
        code="validation_input_invalid",
        artifact_role=ArtifactRole.RECIPE,
        program_id=None,
        program_fingerprint=None,
        subject_path=None,
        message=SECRET_SENTINEL,
        detail_sha256=None,
    )

    serialized_fields = json.dumps(asdict(failure), ensure_ascii=False, sort_keys=True)
    assert failure.message == CLOSED_CONTROL_MESSAGES[failure.code]
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", failure.detail_sha256 or "")
    assert SECRET_SENTINEL not in repr(failure)
    assert SECRET_SENTINEL not in serialized_fields


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
