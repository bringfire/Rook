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
from rook.validation_kernel.budget import BudgetLedger
from rook.validation_kernel.owned_json import JsonObject, JsonString
from rook.validation_kernel.schema_profile import SchemaEvaluationReceipt

from tests._validation_kernel_fakes import (
    SyntheticPhaseIndex,
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
    assert context.ledger.snapshot().kernel_phase_work_units - before == 7
    assert tuple(field.name for field in dataclass_fields(RunnerResult)) == (
        "diagnostics",
        "compile_blockers",
        "outputs",
    )


def test_schema_helper_records_exact_receipts_in_private_order_before_returning_view() -> None:
    context = _context(_program(alpha_scenario="schema_audit"))
    phase_engine = importlib.import_module("rook.validation_kernel.phase_engine")

    execution = phase_engine._execute_phase_program_with_audit(context)

    assert type(execution) is tuple
    results, audit = execution
    assert type(results) is tuple
    assert _phase(results, "alpha").status == "passed"
    assert len(audit.schema_evaluation_receipts) == 2
    assert all(
        type(receipt) is SchemaEvaluationReceipt
        for receipt in audit.schema_evaluation_receipts
    )
    first, second = audit.schema_evaluation_receipts
    assert first.reservation.accepted is True
    assert second.reservation.accepted is True
    assert first.reservation.aggregate_after == second.reservation.aggregate_before
    assert (
        context.ledger.snapshot().schema_evaluation_shape_units
        == second.reservation.aggregate_after
    )
    assert "_PhaseExecutionAudit" not in validation_kernel.__all__


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
