from __future__ import annotations

import importlib
import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

import rook.validation_kernel as validation_kernel
from rook.validation_kernel import (
    PublishedValidationReport,
    SchemaEvaluationInputError,
    ValidationControlFailure,
    compose_and_seal_program,
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
    JsonString,
    count_json_nodes,
    own_trusted_json,
)
from rook.validation_kernel.phase_engine import execute_phase_program
from rook.validation_kernel.reporting import (
    ReportBuilder,
    ReportProjectionEnvelope,
    seal_validation_report,
)
from rook.validation_kernel.schema_profile import (
    SchemaEvaluationReceipt,
    admit_schema,
)

from tests._validation_kernel_fakes import (
    make_assembler_profile_candidate,
    make_phase_engine_contribution,
    make_validation_bundle_bytes,
)


def _program(**changes: object):
    return compose_and_seal_program(make_phase_engine_contribution(**changes))


def _program_with_raw_pointer_report_schema():
    contribution = make_phase_engine_contribution()
    source = contribution.schemas[0]
    profile = next(
        spec.profile
        for spec in contribution.schema_evaluator_profiles
        if spec.profile.profile_id == source.profile_id
    )
    body = json.loads(canonical_json_bytes(source.value))
    wrapped = own_trusted_json(
        {
            "$schema": profile.metaschema_id,
            "$defs": {"body": body},
            "$ref": "/$defs/body",
        }
    )
    assert type(wrapped) is JsonObject
    admitted = admit_schema(source.schema_id, wrapped, profile)
    bindings = tuple(
        replace(
            binding,
            implementation_fingerprint=admitted.schema_fingerprint,
            target=admitted,
        )
        if (binding.binding_kind, binding.binding_id)
        == ("schema", source.schema_id)
        else binding
        for binding in contribution.runtime_bindings
    )
    return compose_and_seal_program(
        replace(
            contribution,
            schemas=(admitted,),
            report_projection=replace(
                contribution.report_projection,
                output_schema_fingerprint=admitted.schema_fingerprint,
            ),
            runtime_bindings=bindings,
        )
    )


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


def _execute_and_seal_with_audit(program: object):
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple
    reporting = importlib.import_module("rook.validation_kernel.reporting")
    return (
        context,
        phase_results,
        reporting._seal_validation_report_with_audit(context, phase_results),
    )


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
    real_claim = BudgetLedger.claim_report_seal
    real_charge = BudgetLedger.charge
    real_schema_reserve = reporting.reserve_schema_evaluation
    real_reserve = BudgetLedger.reserve_report_seal_and_freeze
    real_schema_evaluate = reporting.evaluate_schema_with_reservation
    real_canonical = reporting.canonical_json_bytes

    def put_spy(self: ReportBuilder, path: str, value: object) -> None:
        events.append(("put", path))
        real_put(self, path, value)  # type: ignore[arg-type]

    def charge_spy(self: BudgetLedger, dimension: object, amount: int, **kwargs: object) -> None:
        if dimension is BudgetDimension.REPORT_PROJECTION_FIELDS:
            events.append(("field_charge", amount))
        real_charge(self, dimension, amount, **kwargs)  # type: ignore[arg-type]

    def claim_spy(self: BudgetLedger) -> bool:
        events.append("claim")
        return real_claim(self)

    def schema_reserve_spy(*args: object, **kwargs: object):
        events.append("schema_reserve")
        return real_schema_reserve(*args, **kwargs)

    def reserve_spy(self: BudgetLedger):
        events.append("freeze")
        return real_reserve(self)

    def schema_evaluate_spy(*args: object, **kwargs: object):
        events.append("schema_evaluate")
        return real_schema_evaluate(*args, **kwargs)

    def canonical_spy(value: object, *, max_bytes: int | None = None) -> bytes:
        events.append("canonical")
        return real_canonical(value, max_bytes=max_bytes)

    monkeypatch.setattr(ReportBuilder, "put", put_spy)
    monkeypatch.setattr(BudgetLedger, "claim_report_seal", claim_spy)
    monkeypatch.setattr(BudgetLedger, "charge", charge_spy)
    monkeypatch.setattr(reporting, "reserve_schema_evaluation", schema_reserve_spy)
    monkeypatch.setattr(BudgetLedger, "reserve_report_seal_and_freeze", reserve_spy)
    monkeypatch.setattr(
        reporting,
        "evaluate_schema_with_reservation",
        schema_evaluate_spy,
    )
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
    assert events.index("claim") < events.index(("put", "/body"))
    assert events.index(("put", "/body")) < fixed_charge_index
    assert fixed_charge_index < events.index("schema_reserve") < freeze_index
    assert freeze_index < canonical_indexes[0] < events.index("schema_evaluate")
    assert events.index("schema_evaluate") < canonical_indexes[1]
    assert len(canonical_indexes) == 2


def test_frozen_receipt_contains_body_and_envelope_charges_but_not_serializer_work() -> None:
    program = _program()
    context, _, result = _execute_and_seal(program)
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
    output_schema = program.schemas[0]
    expected_schema_shape = output_schema.schema_nodes * count_json_nodes(result.value)
    assert _integer(observed["schema_evaluation_shape_units"]) == expected_schema_shape
    assert context.ledger.snapshot().report_projection_fields == expected_fields
    assert context.ledger.snapshot().report_seal_reserved_work_units == 262_144
    assert (
        context.ledger.snapshot().schema_evaluation_shape_units
        == expected_schema_shape
    )


@pytest.mark.parametrize(
    "scenario",
    ("normal", "raise", "return_owned_graph", "unknown_path"),
)
def test_builder_is_closed_on_every_projection_exit_without_late_charges(
    scenario: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")
    program = _program(report_projection_scenario=scenario)
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple
    retained: list[ReportBuilder] = []
    real_init = ReportBuilder.__init__

    def init_spy(self: ReportBuilder, *args: object, **kwargs: object) -> None:
        real_init(self, *args, **kwargs)
        retained.append(self)

    monkeypatch.setattr(ReportBuilder, "__init__", init_spy)

    seal_validation_report(context, phase_results)

    assert len(retained) == 1
    before = context.ledger.snapshot()
    with pytest.raises(reporting._ProjectionIntegrityError):
        retained[0].put("/valid", JsonBoolean(True))
    with pytest.raises(reporting._ProjectionIntegrityError):
        retained[0].append("/phases", JsonString("late"))
    assert context.ledger.snapshot() == before


def test_context_report_seal_is_one_shot_after_prefreeze_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = _program(report_projection_scenario="duplicate_field")
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple
    builders: list[ReportBuilder] = []
    real_init = ReportBuilder.__init__

    def init_spy(self: ReportBuilder, *args: object, **kwargs: object) -> None:
        real_init(self, *args, **kwargs)
        builders.append(self)

    monkeypatch.setattr(ReportBuilder, "__init__", init_spy)

    first = seal_validation_report(context, phase_results)
    after_first = context.ledger.snapshot()
    second = seal_validation_report(context, phase_results)

    _assert_report_failure(first, "validator_integrity_failure")
    _assert_report_failure(second, "validator_integrity_failure")
    assert len(builders) == 1
    assert context.ledger.snapshot() == after_first


def test_reserved_evaluator_input_rejection_maps_to_integrity_without_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")

    def reject(*_: object, **__: object) -> object:
        raise SchemaEvaluationInputError("synthetic reservation mismatch")

    monkeypatch.setattr(reporting, "evaluate_schema_with_reservation", reject)

    _, _, result = _execute_and_seal(_program())

    _assert_report_failure(result, "validator_integrity_failure")


def test_private_report_seal_records_accepted_final_schema_receipt() -> None:
    context, _, outcome = _execute_and_seal_with_audit(_program())

    assert type(outcome.public_result) is PublishedValidationReport
    assert len(outcome.schema_evaluation_attempts) == 1
    assert len(outcome.schema_evaluation_receipts) == 1
    attempt = outcome.schema_evaluation_attempts[0]
    receipt = outcome.schema_evaluation_receipts[0]
    assert attempt.receipt is receipt
    assert attempt.schema_id == outcome.public_result.schema_id
    assert attempt.instance_binding.artifact_id == context.invocation.program.program_id
    assert (
        attempt.instance_binding.artifact_fingerprint
        == outcome.public_result.report_fingerprint
    )
    assert attempt.instance_binding.instance_pointer == ""
    assert attempt.instance_fingerprint == canonical_fingerprint(
        outcome.public_result.value
    )
    assert attempt.instance_nodes == count_json_nodes(outcome.public_result.value)
    assert attempt.pre_evaluation_candidate is None
    assert type(receipt) is SchemaEvaluationReceipt
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is True
    assert receipt.failure_code is None
    assert (
        context.ledger.snapshot().schema_evaluation_shape_units
        == receipt.reservation.aggregate_after
    )


def test_private_report_seal_records_rejected_final_schema_reservation() -> None:
    program = _program()
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple
    for _ in range(4):
        reservation = context.ledger.reserve_schema_shape(
            schema_nodes=1,
            instance_nodes=4_000_000,
            per_evaluation_limit=4_000_000,
        )
        assert reservation.accepted is True
    reporting = importlib.import_module("rook.validation_kernel.reporting")

    outcome = reporting._seal_validation_report_with_audit(
        context, phase_results
    )

    result = _assert_report_failure(
        outcome.public_result, "validation_budget_exceeded"
    )
    assert result.budget_dimension == "schema_evaluation_shape_units"
    assert len(outcome.schema_evaluation_attempts) == 1
    assert len(outcome.schema_evaluation_receipts) == 1
    attempt = outcome.schema_evaluation_attempts[0]
    receipt = outcome.schema_evaluation_receipts[0]
    assert attempt.receipt is receipt
    assert attempt.instance_fingerprint is None
    assert attempt.instance_nodes is None
    candidate = attempt.pre_evaluation_candidate
    assert candidate is not None
    assert candidate.candidate_kind == "report_schema_instance_projection"
    assert candidate.projected_instance_nodes > 0
    assert candidate.candidate_fingerprint.startswith("sha256:")
    assert len(candidate.candidate_fingerprint) == 71
    assert attempt.instance_binding.artifact_id == (
        "artifact:validation-report-candidate"
    )
    assert (
        attempt.instance_binding.artifact_fingerprint
        == candidate.candidate_fingerprint
    )
    assert attempt.instance_binding.instance_pointer == ""
    assert type(receipt) is SchemaEvaluationReceipt
    assert receipt.reservation.accepted is False
    assert receipt.reservation.aggregate_before == 16_000_000
    assert receipt.reservation.aggregate_after is None
    assert receipt.reservation.rejection_reason == "invocation_shape_limit_exceeded"
    assert receipt.evaluator_invoked is False
    assert receipt.evaluation_passed is None
    assert receipt.bounded_errors == ()
    assert receipt.failure_code == "invocation_shape_limit_exceeded"


def test_private_report_schema_failure_retains_exact_final_receipt() -> None:
    _, _, outcome = _execute_and_seal_with_audit(
        _program(report_schema_probe="const")
    )

    _assert_report_failure(
        outcome.public_result, "validation_constructability_failed"
    )
    assert len(outcome.schema_evaluation_receipts) == 1
    receipt = outcome.schema_evaluation_receipts[0]
    assert type(receipt) is SchemaEvaluationReceipt
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is False
    assert receipt.failure_code == "instance_schema_failed"


def test_private_report_evaluator_failure_retains_exact_final_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    program = _program()
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple
    schema_profile = importlib.import_module("rook.validation_kernel.schema_profile")
    reporting = importlib.import_module("rook.validation_kernel.reporting")

    class BrokenValidator:
        def iter_errors(self, _: object) -> object:
            raise RuntimeError("synthetic final evaluator failure")

    monkeypatch.setattr(schema_profile, "_validator_for", lambda _: BrokenValidator())

    outcome = reporting._seal_validation_report_with_audit(
        context, phase_results
    )

    _assert_report_failure(outcome.public_result, "validator_integrity_failure")
    assert len(outcome.schema_evaluation_receipts) == 1
    receipt = outcome.schema_evaluation_receipts[0]
    assert type(receipt) is SchemaEvaluationReceipt
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is None
    assert receipt.failure_code == "schema_evaluator_failed"


def test_private_report_pre_attempt_failure_has_empty_audit() -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")

    outcome = reporting._seal_validation_report_with_audit(object(), ())

    _assert_report_failure(outcome.public_result, "validator_integrity_failure")
    assert outcome.schema_evaluation_receipts == ()


@pytest.mark.parametrize(
    "probe",
    (
        "const",
        "enum",
        "minProperties",
        "maxProperties",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "allOf",
        "anyOf",
        "oneOf",
    ),
)
def test_final_report_uses_exact_admitted_schema_evaluator_and_publishes_nothing_on_failure(
    probe: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reporting = importlib.import_module("rook.validation_kernel.reporting")
    canonical_calls = 0
    evaluation_calls = 0
    real_canonical = reporting.canonical_json_bytes
    real_evaluate = reporting.evaluate_schema_with_reservation

    def canonical_spy(value: object, *, max_bytes: int | None = None) -> bytes:
        nonlocal canonical_calls
        canonical_calls += 1
        return real_canonical(value, max_bytes=max_bytes)

    def evaluation_spy(*args: object, **kwargs: object):
        nonlocal evaluation_calls
        evaluation_calls += 1
        return real_evaluate(*args, **kwargs)

    monkeypatch.setattr(reporting, "canonical_json_bytes", canonical_spy)
    monkeypatch.setattr(
        reporting,
        "evaluate_schema_with_reservation",
        evaluation_spy,
    )
    program = _program(report_schema_probe=probe)
    context = _context(program)
    phase_results = execute_phase_program(context)
    assert type(phase_results) is tuple

    result = seal_validation_report(context, phase_results)

    _assert_report_failure(result, "validation_constructability_failed")
    assert context.ledger.snapshot().report_seal_reserved_work_units == 262_144
    assert evaluation_calls == 1
    assert canonical_calls == 2


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


def test_raw_rfc6901_report_schema_reference_composes_and_publishes() -> None:
    program = _program_with_raw_pointer_report_schema()

    _, _, result = _execute_and_seal(program)

    assert type(result) is PublishedValidationReport
    assert result.schema_id == "synthetic.report:v1"
    assert canonical_fingerprint(_without_fingerprint(result.value)) == result.report_fingerprint


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
    assert "PublishedValidationReport" in validation_kernel.__all__
    for name in ("ReportBuilder", "ReportProjectionEnvelope", "seal_validation_report"):
        assert name not in validation_kernel.__all__
        assert not hasattr(validation_kernel, name)
