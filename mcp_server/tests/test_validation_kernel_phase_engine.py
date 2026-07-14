from __future__ import annotations

import importlib
from dataclasses import FrozenInstanceError, fields as dataclass_fields

import pytest

import rook.validation_kernel as validation_kernel
from rook.validation_kernel import (
    KernelIssue,
    NamedOutput,
    PhaseResult,
    RunnerResult,
    ValidationControlFailure,
    compose_and_seal_program,
    execute_phase_program,
)
from rook.validation_kernel.budget import BudgetExceeded, BudgetLedger
from rook.validation_kernel.control import ArtifactRole, BudgetDimension
from rook.validation_kernel.owned_json import JsonObject, JsonString
from rook.validation_kernel.schema_profile import InstanceBinding, SchemaEvaluationReceipt

from tests._validation_kernel_fakes import (
    HugeTypeMetadataError,
    KERNEL_STRING_EXPORT_CALLS,
    SYNTHETIC_WIDE_PHASE_INDEX,
    SyntheticPhaseIndex,
    make_assembler_profile_candidate,
    make_phase_engine_contribution,
    make_validation_bundle_bytes,
    non_boolean_kernel_string_export_validator,
    raising_kernel_string_export_validator,
    rejecting_kernel_string_export_validator,
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


def _phase(results: tuple[PhaseResult, ...], name: str) -> PhaseResult:
    return next(result for result in results if result.phase_name == name)


def _assert_integrity_failure(result: object) -> ValidationControlFailure:
    assert isinstance(result, ValidationControlFailure)
    assert result.failure_stage == "validation"
    assert result.code == "validator_integrity_failure"
    assert result.artifact_role == "phase_engine"
    assert result.message == "Validator integrity check failed."
    assert result.detail_sha256 is not None
    assert len(result.detail_sha256) == 71
    return result


def test_scheduler_uses_bindings_for_availability_and_ordering_only_for_sequence() -> None:
    program = _program(alpha_scenario="failed")
    assert program.data_dependencies == {"alpha": (), "audit": (), "beta": ("alpha",)}
    assert program.scheduling_dependencies == {
        "alpha": (),
        "audit": ("alpha",),
        "beta": ("alpha",),
    }

    result = execute_phase_program(_context(program))

    assert type(result) is tuple
    assert tuple(phase.phase_name for phase in result) == ("alpha", "audit", "beta")
    assert tuple(phase.status for phase in result) == (
        "failed",
        "passed",
        "not_evaluated",
    )
    assert _phase(result, "audit").kernel_work_units_delta == 0
    assert _phase(result, "beta").outputs == ()


def test_simultaneously_ready_phases_follow_sealed_rfc8785_name_order() -> None:
    program = _program(audit_ordering_after=())
    assert program.execution_order == ("alpha", "audit", "beta")

    result = execute_phase_program(_context(program))

    assert type(result) is tuple
    assert tuple(phase.phase_name for phase in result) == program.execution_order


def test_blocked_provider_supplies_required_exact_named_output() -> None:
    result = execute_phase_program(_context(_program(alpha_scenario="blocked")))

    assert type(result) is tuple
    alpha = _phase(result, "alpha")
    beta = _phase(result, "beta")
    assert alpha.status == "blocked"
    assert len(alpha.compile_blockers) == 1
    assert beta.status == "passed"
    assert beta.outputs == (NamedOutput("beta_value", (JsonString("alpha-index"),)),)


def test_not_evaluated_provider_suppresses_consumer() -> None:
    program = _program(invocation_cardinality="zero_or_one")
    result = execute_phase_program(_context(program, b'{"nested":'))

    assert type(result) is tuple
    assert tuple(phase.status for phase in result) == (
        "not_evaluated",
        "passed",
        "not_evaluated",
    )


def test_ordinary_optional_missing_output_suppresses_without_integrity_failure() -> None:
    program = _program(
        alpha_scenario="missing_output",
        alpha_required_statuses=(),
    )

    result = execute_phase_program(_context(program))

    assert type(result) is tuple
    assert _phase(result, "alpha").status == "passed"
    assert _phase(result, "alpha").outputs == ()
    assert _phase(result, "beta").status == "not_evaluated"


def test_required_invocation_input_type_is_checked_before_runner_entry() -> None:
    result = execute_phase_program(_context(_program(), b'{"nested":'))

    _assert_integrity_failure(result)


def test_warning_and_information_diagnostics_are_public_and_do_not_fail_phase() -> None:
    context = _context(_program(alpha_scenario="warning_information"))

    result = execute_phase_program(context)

    assert type(result) is tuple
    alpha = _phase(result, "alpha")
    assert alpha.status == "passed"
    assert tuple(issue.severity for issue in alpha.diagnostics) == (
        "warning",
        "information",
    )
    assert context.ledger.snapshot().diagnostics == 2


@pytest.mark.parametrize(
    ("scenario", "diagnostics", "compile_blockers"),
    (
        ("duplicate_diagnostic", 2, 0),
        ("duplicate_blocker", 0, 2),
        ("cross_list_issue", 1, 1),
    ),
)
def test_duplicate_issue_domains_charge_before_integrity_rejection(
    scenario: str, diagnostics: int, compile_blockers: int
) -> None:
    context = _context(_program(alpha_scenario=scenario))

    result = execute_phase_program(context)

    _assert_integrity_failure(result)
    snapshot = context.ledger.snapshot()
    assert snapshot.diagnostics == diagnostics
    assert snapshot.compile_blockers == compile_blockers


def test_error_status_has_precedence_over_compile_blockers() -> None:
    context = _context(_program(alpha_scenario="error_precedence"))

    result = execute_phase_program(context)

    assert type(result) is tuple
    alpha = _phase(result, "alpha")
    assert alpha.status == "failed"
    assert len(alpha.diagnostics) == 1
    assert len(alpha.compile_blockers) == 1
    snapshot = context.ledger.snapshot()
    assert snapshot.diagnostics == 1
    assert snapshot.compile_blockers == 1


@pytest.mark.parametrize(
    "scenario",
    (
        "unregistered_issue",
        "wrong_classification",
        "non_exact_issue_fields",
        "duplicate_output",
        "extra_output",
        "missing_output",
        "blocked_missing_output",
        "wrong_type",
        "mutable_output",
        "wrong_cardinality",
        "output_on_failed",
        "authored_fields",
    ),
)
def test_structural_runner_contradictions_abort_without_partial_results(
    scenario: str,
) -> None:
    result = execute_phase_program(_context(_program(alpha_scenario=scenario)))

    _assert_integrity_failure(result)


def test_passed_and_blocked_promised_output_omissions_are_integrity_failures() -> None:
    passed = execute_phase_program(
        _context(_program(alpha_scenario="missing_output"))
    )
    blocked = execute_phase_program(
        _context(_program(alpha_scenario="blocked_missing_output"))
    )

    _assert_integrity_failure(passed)
    _assert_integrity_failure(blocked)


def test_kernel_primitive_output_still_uses_exact_sealed_export_validator() -> None:
    KERNEL_STRING_EXPORT_CALLS.clear()
    program = _program(
        beta_output_type="kernel.string:v1",
        beta_export_validator=rejecting_kernel_string_export_validator,
    )
    assert (
        program.resolve_runtime_binding("export_type", "kernel.string:v1")
        is rejecting_kernel_string_export_validator
    )

    result = execute_phase_program(_context(program))

    _assert_integrity_failure(result)
    assert KERNEL_STRING_EXPORT_CALLS == [JsonString("alpha-index")]


@pytest.mark.parametrize(
    "validator",
    (
        raising_kernel_string_export_validator,
        non_boolean_kernel_string_export_validator,
    ),
)
def test_sealed_export_validator_faults_are_integrity_failures(
    validator: object,
) -> None:
    program = _program(
        beta_output_type="kernel.string:v1",
        beta_export_validator=validator,
    )

    result = execute_phase_program(_context(program))

    _assert_integrity_failure(result)


def test_runner_exception_uses_generic_bounded_message_and_stable_hashed_evidence() -> None:
    first = execute_phase_program(
        _context(_program(alpha_scenario="oversized_exception"))
    )
    second = execute_phase_program(
        _context(_program(alpha_scenario="oversized_exception_alt"))
    )

    assert isinstance(first, ValidationControlFailure)
    assert isinstance(second, ValidationControlFailure)
    assert first.code == second.code == "validator_internal_failure"
    assert first.message == second.message == "Validator internal failure."
    assert "variable-exception" not in first.message
    assert len(first.message) <= 512
    assert first.detail_sha256 is not None
    assert second.detail_sha256 is not None
    assert first.detail_sha256 != second.detail_sha256


def test_runner_exception_evidence_never_decimalizes_an_oversized_integer() -> None:
    result = execute_phase_program(
        _context(_program(alpha_scenario="oversized_integer_exception"))
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_internal_failure"
    assert result.message == "Validator internal failure."
    assert result.detail_sha256 is not None


@pytest.mark.parametrize(
    "scenario",
    (
        "hostile_args_exception",
        "hostile_type_metadata_exception",
        "huge_type_metadata_exception",
        "nested_cyclic_custom_exception",
    ),
)
def test_hostile_exception_shapes_always_return_bounded_internal_failure(
    scenario: str,
) -> None:
    result = execute_phase_program(_context(_program(alpha_scenario=scenario)))

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_internal_failure"
    assert result.message == "Validator internal failure."
    assert result.detail_sha256 is not None
    assert len(result.detail_sha256) == 71


def test_exception_projection_enforces_exact_byte_item_and_depth_caps() -> None:
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")
    nested: object = HugeTypeMetadataError("bounded")
    for _ in range(64):
        nested = (nested,)
    exception = RuntimeError(nested)

    projection = phase_engine._exception_detail_projection(exception)

    assert projection.projected_bytes <= 4_096
    assert projection.projected_items <= 128
    assert projection.maximum_depth <= 16
    assert projection.truncated is True
    assert len(projection.digest) == 32


def test_runner_receives_only_transitively_immutable_inputs_and_restricted_helpers() -> None:
    program = _program(
        alpha_scenario="immutability_probe",
        audit_scenario="immutability_probe",
        beta_scenario="immutability_probe",
    )

    result = execute_phase_program(_context(program))

    assert type(result) is tuple
    assert tuple(phase.status for phase in result) == ("passed", "passed", "passed")
    alpha_output = _phase(result, "alpha").outputs[0]
    index = alpha_output.values[0]
    assert type(index) is SyntheticPhaseIndex
    assert index.identity == "alpha-index"
    assert type(index.source) is JsonObject
    assert index.paths == ("/recipe",)
    with pytest.raises(FrozenInstanceError):
        index.identity = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        index.source["nested"] = JsonString("changed")  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        alpha_output.values = ()  # type: ignore[misc]


def test_engine_snapshots_ledger_and_derives_runner_work_delta() -> None:
    context = _context(_program(alpha_scenario="work_accounting"))
    before = context.ledger.snapshot().kernel_phase_work_units

    result = execute_phase_program(context)

    assert type(result) is tuple
    assert _phase(result, "alpha").kernel_work_units_delta == 7
    assert _phase(result, "audit").kernel_work_units_delta == 0
    assert _phase(result, "beta").kernel_work_units_delta == 0
    assert context.ledger.snapshot().kernel_phase_work_units - before > 7
    assert tuple(field.name for field in dataclass_fields(RunnerResult)) == (
        "diagnostics",
        "compile_blockers",
        "outputs",
    )


def test_phase_result_validation_meters_ten_thousand_output_values() -> None:
    context = _context(
        _program(beta_scenario="many_10000", beta_output_cardinality="many")
    )
    before = context.ledger.snapshot().kernel_phase_work_units

    result = execute_phase_program(context)

    assert type(result) is tuple
    beta_values = _phase(result, "beta").outputs[0].values
    assert len(beta_values) == 10_000
    assert context.ledger.snapshot().kernel_phase_work_units > before


def test_wide_index_budget_failure_precedes_fields_and_set_materialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(_program(alpha_scenario="wide_index"))
    context.ledger.charge(
        BudgetDimension.KERNEL_PHASE_WORK_UNITS,
        998_000,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path="/reviewer-probe",
    )
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")
    calls = {"fields": 0, "set": 0}
    real_fields = phase_engine.fields
    real_set = set

    def fields_spy(value: object) -> object:
        calls["fields"] += 1
        return real_fields(value)

    def set_spy(*args: object) -> set[object]:
        calls["set"] += 1
        return real_set(*args)

    monkeypatch.setattr(phase_engine, "fields", fields_spy)
    monkeypatch.setattr(phase_engine, "set", set_spy, raising=False)

    outcome = phase_engine._execute_phase_program_with_audit(context)

    execution = outcome.public_result
    assert isinstance(execution, ValidationControlFailure)
    assert execution.code == "validation_budget_exceeded"
    assert execution.budget_dimension == "kernel_phase_work_units"
    assert outcome.schema_evaluation_receipts == ()
    assert calls == {"fields": 0, "set": 0}


def test_wide_index_exact_remaining_budget_materializes_layout_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context(_program())
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")
    charger = phase_engine._phase_work_charger(context, "alpha")
    expected_delta = 16_016
    context.ledger.charge(
        BudgetDimension.KERNEL_PHASE_WORK_UNITS,
        1_000_000 - expected_delta,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path="/reviewer-probe",
    )
    calls = {"fields": 0, "set": 0}
    real_fields = phase_engine.fields
    real_set = set

    def fields_spy(value: object) -> object:
        calls["fields"] += 1
        return real_fields(value)

    def set_spy(*args: object) -> set[object]:
        calls["set"] += 1
        return real_set(*args)

    monkeypatch.setattr(phase_engine, "fields", fields_spy)
    monkeypatch.setattr(phase_engine, "set", set_spy, raising=False)
    before = context.ledger.snapshot().kernel_phase_work_units

    accepted = phase_engine._is_transitively_immutable(
        SYNTHETIC_WIDE_PHASE_INDEX, charger
    )

    after = context.ledger.snapshot().kernel_phase_work_units
    assert accepted is True
    assert after - before == expected_delta
    assert after == 1_000_000
    assert calls == {"fields": 1, "set": 2}


def test_phase_validation_budget_exhaustion_before_schema_attempt_has_empty_audit() -> None:
    context = _context(
        _program(beta_scenario="many_10000", beta_output_cardinality="many")
    )
    context.ledger.charge(
        BudgetDimension.KERNEL_PHASE_WORK_UNITS,
        999_000,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path="/reviewer-probe",
    )
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")

    outcome = phase_engine._execute_phase_program_with_audit(context)

    execution = outcome.public_result
    assert isinstance(execution, ValidationControlFailure)
    assert execution.code == "validation_budget_exceeded"
    assert execution.failure_stage == "validation"
    assert execution.artifact_role == "phase_engine"
    assert execution.budget_dimension == "kernel_phase_work_units"
    assert outcome.schema_evaluation_receipts == ()


def test_schema_helper_budget_exhaustion_attaches_no_partial_audit_receipt() -> None:
    context = _context(_program())
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")
    alpha = next(
        phase for phase in context.invocation.program.phases if phase.phase_name == "alpha"
    )
    receipts: list[SchemaEvaluationReceipt] = []
    charger = phase_engine._phase_work_charger(context, "alpha")
    helper = phase_engine._helper_facade(context, alpha, receipts, charger)
    current = context.ledger.snapshot().kernel_phase_work_units
    context.ledger.charge(
        BudgetDimension.KERNEL_PHASE_WORK_UNITS,
        1_000_000 - current - 2,
        artifact_role=ArtifactRole.PHASE_ENGINE,
        subject_path="/reviewer-probe",
    )
    recipe = context.invocation.invocation_inputs["recipe"]
    binding = InstanceBinding(
        artifact_id="synthetic.recipe",
        artifact_fingerprint="sha256:" + ("0" * 64),
        instance_pointer="",
    )

    with pytest.raises(BudgetExceeded):
        helper.evaluate_schema(
            "synthetic.report:v1", recipe, instance_binding=binding
        )

    assert receipts == []


def test_schema_helper_records_exact_receipts_in_private_order_before_returning_view() -> None:
    context = _context(_program(alpha_scenario="schema_audit"))
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")

    outcome = phase_engine._execute_phase_program_with_audit(context)

    results = outcome.public_result
    assert type(results) is tuple
    assert _phase(results, "alpha").status == "passed"
    assert len(outcome.schema_evaluation_receipts) == 2
    assert all(
        type(receipt) is SchemaEvaluationReceipt
        for receipt in outcome.schema_evaluation_receipts
    )
    first, second = outcome.schema_evaluation_receipts
    assert first.reservation.accepted is True
    assert second.reservation.accepted is True
    assert first.reservation.aggregate_after == second.reservation.aggregate_before
    assert (
        context.ledger.snapshot().schema_evaluation_shape_units
        == second.reservation.aggregate_after
    )
    assert "_PhaseExecutionAudit" not in validation_kernel.__all__


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    (
        ("schema_then_integrity_failure", "validator_integrity_failure"),
        ("schema_then_budget_failure", "validation_budget_exceeded"),
        ("schema_then_internal_failure", "validator_internal_failure"),
    ),
)
def test_control_failure_after_schema_attempt_preserves_exact_private_receipts(
    scenario: str, expected_code: str
) -> None:
    context = _context(_program(alpha_scenario=scenario))
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")

    outcome = phase_engine._execute_phase_program_with_audit(context)

    result = outcome.public_result
    assert isinstance(result, ValidationControlFailure)
    assert result.code == expected_code
    assert len(outcome.schema_evaluation_receipts) == 1
    receipt = outcome.schema_evaluation_receipts[0]
    assert type(receipt) is SchemaEvaluationReceipt
    assert receipt.reservation.accepted is True
    assert receipt.evaluator_invoked is True
    assert receipt.evaluation_passed is False
    assert receipt.failure_code == "instance_schema_failed"


def test_public_phase_control_failure_exposes_no_private_audit_evidence() -> None:
    result = execute_phase_program(
        _context(_program(alpha_scenario="schema_then_integrity_failure"))
    )

    assert isinstance(result, ValidationControlFailure)
    assert result.code == "validator_integrity_failure"
    assert not hasattr(result, "schema_evaluation_receipts")


def test_public_phase_values_are_frozen_and_have_no_authored_authority_fields() -> None:
    result = execute_phase_program(_context(_program()))

    assert type(result) is tuple
    phase = result[0]
    assert tuple(field.name for field in dataclass_fields(PhaseResult)) == (
        "phase_name",
        "status",
        "diagnostics",
        "compile_blockers",
        "outputs",
        "kernel_work_units_delta",
    )
    assert tuple(field.name for field in dataclass_fields(KernelIssue)) == (
        "classification",
        "code",
        "severity",
        "subject_id",
        "path",
        "related_paths",
        "bounded_message",
        "detail_sha256",
    )
    with pytest.raises(FrozenInstanceError):
        phase.status = "failed"  # type: ignore[misc]


def test_phase_engine_public_exports_are_exact() -> None:
    expected = {
        "KernelIssue",
        "NamedOutput",
        "PhaseResult",
        "RunnerResult",
        "execute_phase_program",
    }
    assert expected.issubset(validation_kernel.__all__)
    assert "PhaseHelperFacade" not in validation_kernel.__all__
    assert "_ValidationExecutionContext" not in validation_kernel.__all__
