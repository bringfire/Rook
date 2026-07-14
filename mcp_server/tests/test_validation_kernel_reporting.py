from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

import rook.validation_kernel as validation_kernel
from rook.validation_kernel import (
    PublishedValidationReport,
    ReportBuilder,
    ReportProjectionEnvelope,
    ValidationControlFailure,
    compose_and_seal_program,
    execute_phase_program,
    seal_validation_report,
)
from rook.validation_kernel.budget import BudgetLedger
from rook.validation_kernel.canonical_json import (
    CanonicalJsonSizeError,
    canonical_fingerprint,
    canonical_json_bytes,
)
from rook.validation_kernel.control import BudgetDimension, BudgetExceededFailure
from rook.validation_kernel.owned_json import (
    JsonArray,
    JsonBoolean,
    JsonNumber,
    JsonObject,
)

from tests._validation_kernel_fakes import (
    make_assembler_profile_candidate,
    make_phase_engine_contribution,
    make_validation_bundle_bytes,
)


def _program(**changes: object):
    return compose_and_seal_program(make_phase_engine_contribution(**changes))


def _context(program: object, recipe: bytes = b'{"nested":{"value":1}}'):
    profile = validation_kernel.seal_trusted_bundle_assembler_profile(
        make_assembler_profile_candidate()
    )
    carrier = validation_kernel.issue_trusted_validation_bundle(
        profile, make_validation_bundle_bytes()
    )
    invocation_module = importlib.import_module("rook.validation_kernel.invocation")
    context = invocation_module._build_validation_execution_context(
        program, recipe, carrier
    )
    assert not isinstance(context, ValidationControlFailure)
    assert type(context.ledger) is BudgetLedger
    return context


def _execute_and_seal(program: object):
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple
    return context, phase_results, seal_validation_report(context, phase_results)


def _bool(report: PublishedValidationReport, field_name: str) -> bool:
    value = report.value[field_name]
    assert type(value) is JsonBoolean
    return value.value


def _integer(value: object) -> int:
    assert type(value) is JsonNumber
    assert value.value.is_integer()
    return int(value.value)


def _without_fingerprint(value: JsonObject) -> JsonObject:
    return JsonObject(
        tuple(
            (key, member)
            for key, member in value.members
            if key.value != "report_fingerprint"
        )
    )


def _nested_attachment_count(value: object) -> int:
    if type(value) is JsonObject:
        return sum(
            1 + _nested_attachment_count(member)
            for _, member in value.members
        )
    if type(value) is JsonArray:
        return sum(1 + _nested_attachment_count(item) for item in value.items)
    return 0


def _assert_report_failure(
    result: object, code: str = "validator_integrity_failure"
) -> ValidationControlFailure:
    assert isinstance(result, ValidationControlFailure)
    assert result.failure_stage == "validation"
    assert result.code == code
    assert result.artifact_role == "report_seal"
    assert not hasattr(result, "canonical_bytes")
    assert not hasattr(result, "value")
    return result


def test_projection_receives_only_exact_immutable_envelope_and_kernel_builder() -> None:
    program = _program()

    _, phase_results, result = _execute_and_seal(program)

    assert type(result) is PublishedValidationReport
    assert result.schema_id == "synthetic.report:v1"
    assert type(result.value) is JsonObject
    body = result.value["body"]
    phases = result.value["phases"]
    assert type(body) is JsonObject
    assert body["optional"].value == program.program_id  # type: ignore[union-attr]
    assert type(phases) is JsonArray
    assert tuple(item.value for item in phases) == tuple(
        f"{phase.phase_name}:{phase.status}" for phase in phase_results
    )
    with pytest.raises(TypeError):
        ReportBuilder()


def test_projection_envelope_and_published_report_are_frozen_exact_values() -> None:
    empty = JsonObject(())
    envelope = ReportProjectionEnvelope(
        program_id="synthetic.program:v1",
        program_fingerprint="sha256:" + "1" * 64,
        invocation_evidence=empty,
        phase_specs=(),
        phase_results=(),
    )
    published = PublishedValidationReport(
        schema_id="synthetic.report:v1",
        report_fingerprint="sha256:" + "2" * 64,
        canonical_bytes=b"{}",
        value=empty,
    )

    with pytest.raises((FrozenInstanceError, AttributeError)):
        envelope.program_id = "changed"  # type: ignore[misc]
    with pytest.raises((FrozenInstanceError, AttributeError)):
        published.value = JsonObject(())  # type: ignore[misc]


@pytest.mark.parametrize(
    ("scenario", "code"),
    (
        ("return_host_graph", "validator_integrity_failure"),
        ("return_owned_graph", "validator_integrity_failure"),
        ("unknown_path", "validator_integrity_failure"),
        ("kernel_path", "validator_integrity_failure"),
        ("wrong_shape", "validator_integrity_failure"),
        ("duplicate_field", "validator_integrity_failure"),
        ("missing_field", "validation_constructability_failed"),
        ("raise", "validator_internal_failure"),
    ),
)
def test_arbitrary_returns_and_unauthorized_builder_operations_publish_no_report(
    scenario: str, code: str
) -> None:
    program = _program(report_projection_scenario=scenario)
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple

    result = seal_validation_report(context, phase_results)

    failure = _assert_report_failure(result, code)
    assert failure.program_id == program.program_id
    assert failure.program_fingerprint == program.program_fingerprint


def test_unsealed_context_and_inexact_phase_results_fail_before_projection() -> None:
    result = seal_validation_report(object(), ())  # type: ignore[arg-type]
    _assert_report_failure(result)

    program = _program()
    context = _context(program)
    result = seal_validation_report(context, list(execute_phase_program(context)))  # type: ignore[arg-type]
    _assert_report_failure(result)


def test_seal_order_is_projection_then_fixed_charge_freeze_and_two_serializations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")
    events: list[object] = []
    real_put = ReportBuilder.put
    real_charge = BudgetLedger.charge
    real_reserve = BudgetLedger.reserve_report_seal_and_freeze
    real_canonical = reporting.canonical_json_bytes

    def put_spy(self: ReportBuilder, path: str, value: object) -> None:
        events.append(("put", path))
        real_put(self, path, value)  # type: ignore[arg-type]

    def charge_spy(self: BudgetLedger, dimension: object, amount: int, **kwargs: object) -> None:
        if dimension is BudgetDimension.REPORT_PROJECTION_FIELDS:
            events.append(("field_charge", amount))
        real_charge(self, dimension, amount, **kwargs)  # type: ignore[arg-type]

    def reserve_spy(self: BudgetLedger):
        events.append("freeze")
        return real_reserve(self)

    def canonical_spy(value: object, *, max_bytes: int | None = None) -> bytes:
        events.append("canonical")
        return real_canonical(value, max_bytes=max_bytes)

    monkeypatch.setattr(ReportBuilder, "put", put_spy)
    monkeypatch.setattr(BudgetLedger, "charge", charge_spy)
    monkeypatch.setattr(BudgetLedger, "reserve_report_seal_and_freeze", reserve_spy)
    monkeypatch.setattr(reporting, "canonical_json_bytes", canonical_spy)

    _, _, result = _execute_and_seal(_program())

    assert type(result) is PublishedValidationReport
    body_puts = [event for event in events if event == ("put", "/body")]
    assert body_puts == [("put", "/body")]
    fixed_charge_index = events.index(("field_charge", 21))
    freeze_index = events.index("freeze")
    canonical_indexes = [
        index for index, event in enumerate(events) if event == "canonical"
    ]
    assert events.index(("put", "/body")) < fixed_charge_index
    assert fixed_charge_index < freeze_index < canonical_indexes[0] < canonical_indexes[1]
    assert len(canonical_indexes) == 2


def test_frozen_receipt_contains_body_and_envelope_charges_but_not_serializer_work() -> None:
    context, _, result = _execute_and_seal(_program())
    assert type(result) is PublishedValidationReport
    budget = result.value["validation_budget"]
    assert type(budget) is JsonObject
    observed = budget["observed"]
    assert type(observed) is JsonObject

    projected = _without_fingerprint(result.value)
    projection_owned = JsonObject(
        tuple(
            (key, member)
            for key, member in projected.members
            if key.value != "validation_budget"
        )
    )
    expected_fields = _nested_attachment_count(projection_owned) + 21
    assert _integer(observed["report_projection_fields"]) == expected_fields
    assert _integer(observed["report_seal_reserved_work_units"]) == 262_144
    assert context.ledger.snapshot().report_projection_fields == expected_fields
    assert context.ledger.snapshot().report_seal_reserved_work_units == 262_144


def test_identical_inputs_publish_identical_bytes_and_exact_fingerprint_projection() -> None:
    program = _program()
    _, _, first = _execute_and_seal(program)
    _, _, second = _execute_and_seal(program)
    assert type(first) is PublishedValidationReport
    assert type(second) is PublishedValidationReport

    assert first.canonical_bytes == second.canonical_bytes
    assert first.report_fingerprint == second.report_fingerprint
    assert first.value == second.value
    assert canonical_json_bytes(first.value) == first.canonical_bytes
    fingerprint_projection = _without_fingerprint(first.value)
    assert canonical_fingerprint(fingerprint_projection) == first.report_fingerprint
    fingerprint_value = first.value["report_fingerprint"]
    assert fingerprint_value.value == first.report_fingerprint  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("scenario", "dimension"),
    (
        ("projection_overflow", "report_projection_fields"),
        ("canonical_overflow", "report_canonical_bytes"),
    ),
)
def test_projection_and_first_canonical_overflow_return_typed_failure_without_partial_artifact(
    scenario: str, dimension: str
) -> None:
    program = _program(report_projection_scenario=scenario)
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple

    result = seal_validation_report(context, phase_results)

    assert type(result) is BudgetExceededFailure
    _assert_report_failure(result, "validation_budget_exceeded")
    assert result.budget_dimension == dimension


def test_second_canonical_overflow_is_independent_and_publishes_no_partial_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")
    real_canonical = reporting.canonical_json_bytes
    calls = 0

    def fail_second(value: object, *, max_bytes: int | None = None) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise CanonicalJsonSizeError(2_097_152, 2_097_153)
        return real_canonical(value, max_bytes=max_bytes)

    monkeypatch.setattr(reporting, "canonical_json_bytes", fail_second)
    _, _, result = _execute_and_seal(_program())

    assert calls == 2
    assert type(result) is BudgetExceededFailure
    _assert_report_failure(result, "validation_budget_exceeded")
    assert result.budget_dimension == "report_canonical_bytes"


def test_optional_not_evaluated_phase_does_not_block_compile_readiness() -> None:
    program = _program(
        alpha_scenario="missing_output",
        alpha_required_statuses=(),
        required_for_compile_phases=("alpha",),
    )
    _, phase_results, report = _execute_and_seal(program)
    assert type(report) is PublishedValidationReport

    assert tuple(result.status for result in phase_results) == (
        "passed",
        "passed",
        "not_evaluated",
    )
    assert _bool(report, "valid") is True
    assert _bool(report, "compile_ready") is True


def test_required_not_evaluated_phase_blocks_compile_readiness() -> None:
    program = _program(
        alpha_scenario="missing_output",
        alpha_required_statuses=(),
        required_for_compile_phases=("alpha", "beta"),
    )
    _, phase_results, report = _execute_and_seal(program)
    assert type(report) is PublishedValidationReport

    assert phase_results[-1].status == "not_evaluated"
    assert _bool(report, "valid") is True
    assert _bool(report, "compile_ready") is False


def test_error_diagnostics_and_blockers_drive_validity_and_readiness_independently() -> None:
    _, _, failed = _execute_and_seal(_program(alpha_scenario="failed"))
    _, _, blocked = _execute_and_seal(_program(alpha_scenario="blocked"))
    assert type(failed) is PublishedValidationReport
    assert type(blocked) is PublishedValidationReport

    assert _bool(failed, "valid") is False
    assert _bool(failed, "compile_ready") is False
    assert _bool(blocked, "valid") is True
    assert _bool(blocked, "compile_ready") is False


def test_reporting_kernel_contains_no_planner_specific_semantics() -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")
    source = Path(reporting.__file__).read_text(encoding="utf-8")

    assert "planner" not in source.casefold()
    for name in (
        "PublishedValidationReport",
        "ReportBuilder",
        "ReportProjectionEnvelope",
        "seal_validation_report",
    ):
        assert name in validation_kernel.__all__
