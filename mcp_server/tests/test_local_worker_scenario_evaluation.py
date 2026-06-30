from __future__ import annotations

import ast
import copy
import inspect
from dataclasses import FrozenInstanceError, fields, is_dataclass
from types import MappingProxyType

import pytest

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_disposition import LocalWorkerTurnDispositionRecord
from rook.agent.local_worker_turn_harness import (
    LocalWorkerTurnHarnessRecord,
    run_local_worker_turn,
)
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerObservation,
)
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    ExpectedNodeRef,
    InitialNodeParams,
    ProducerStepSpec,
    RookWorkflowContract,
    VerifierStepSpec,
    WorkflowNodeRule,
    WorkflowTemplateRef,
    compile_workflow_contract,
)

from rook.agent.local_worker_scenario_evaluation import (
    LocalWorkerScenarioCheck,
    LocalWorkerScenarioExpectation,
    LocalWorkerScenarioReport,
    LocalWorkerScenarioResult,
    build_local_worker_scenario_report,
    evaluate_local_worker_scenario_result,
)


WORKFLOW_ID = "lm5f_worker_evaluation"
FINGERPRINT = "f" * 64
ACTION_ID = "draft_bind_params"


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id=WORKFLOW_ID,
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify_repair_verify",
                "language": "csharp",
            },
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                node_id="create_script",
                execution_params={
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM5FLocalWorkerEvaluation",
                    "x": 350,
                    "y": 1360,
                },
            ),
        ),
        expected_refs=(
            ExpectedNodeRef(
                node_id="create_script",
                execution_ref="gh_create_csharp_script:v1",
            ),
            ExpectedNodeRef(
                node_id="repair_same_component",
                execution_ref="gh_update_script:v1",
            ),
        ),
        rules=(
            WorkflowNodeRule(
                node_id="create_script",
                steps_by_seen_count=(ProducerStepSpec(node_id="create_script"),),
            ),
            WorkflowNodeRule(
                node_id="verify_create",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_create",
                        source_node_id="create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                node_id="repair_same_component",
                steps_by_seen_count=(
                    BindStepSpec(
                        node_id="repair_same_component",
                        base_params={
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        bindings={
                            "guid": ("repair_anchor", "component_guid"),
                        },
                    ),
                    ProducerStepSpec(node_id="repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                node_id="verify_repair",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_repair",
                        source_node_id="repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=("done",),
        max_steps=6,
        metadata={"trace": {"slice": "LM5F"}},
    )


def _context(action_id: str = ACTION_ID) -> LocalWorkerTurnContext:
    scaffold = compile_workflow_contract(_repair_contract())
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts["repair_anchor"] = {"component_guid": "component-123"}
    graph.memory.facts["component_guid"] = "component-123"
    return build_local_worker_turn_context(
        scaffold,
        graph,
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(),
        allowed_actions=(
            WorkerAllowedAction(
                action_id=action_id,
                kind="draft",
                description="Draft replacement C# body parameters.",
                input_schema={},
            ),
        ),
    )


def _action_response(action_id: str = ACTION_ID) -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=action_id,
            rationale="Draft repair params.",
            input={"code": "A = 42.0;"},
        )
    )


def _observation_response() -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(WorkerObservation("No action requested."))


def _attempt(
    *,
    valid: bool,
    response_kind: str | None,
    failure: str | None,
    reason: str,
    action_id: str | None,
    workflow_id: str = WORKFLOW_ID,
    contract_fingerprint: str = FINGERPRINT,
) -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=valid,
        response_kind=response_kind,
        failure=failure,
        reason=reason,
        action_id=action_id,
        context_workflow_id=workflow_id,
        context_contract_fingerprint=contract_fingerprint,
    )


def _disposition_for_attempt(
    attempt: LocalWorkerTurnAttemptRecord,
) -> LocalWorkerTurnDispositionRecord:
    if attempt.valid:
        return LocalWorkerTurnDispositionRecord(
            disposition="candidate_action_request",
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=attempt.action_id,
            reason=f"candidate_action_request:{attempt.action_id}",
        )
    return LocalWorkerTurnDispositionRecord(
        disposition="blocked",
        attempt=attempt,
        response_kind=attempt.response_kind,
        action_id=attempt.action_id,
        reason=f"blocked:{attempt.reason}",
    )


def _completed_record(
    *,
    response: LocalWorkerTurnResponse | None = None,
    disposition: LocalWorkerTurnDispositionRecord | None = None,
) -> LocalWorkerTurnHarnessRecord:
    if response is None:
        response = _action_response()
    if disposition is None:
        disposition = _disposition_for_attempt(
            _attempt(
                valid=True,
                response_kind="action_request",
                failure=None,
                reason="valid_action_request",
                action_id=ACTION_ID,
            )
        )
    return LocalWorkerTurnHarnessRecord(
        status="completed",
        response=response,
        disposition=disposition,
        failure=None,
        reason=f"completed:{disposition.disposition}",
        context_workflow_id=disposition.attempt.context_workflow_id,
        context_contract_fingerprint=disposition.attempt.context_contract_fingerprint,
    )


def _blocked_record(action_id: str = "gh_update_script:v1") -> LocalWorkerTurnHarnessRecord:
    attempt = _attempt(
        valid=False,
        response_kind="action_request",
        failure="unknown_action_id",
        reason=f"unknown_action_id:{action_id}",
        action_id=action_id,
    )
    return _completed_record(
        response=_action_response(action_id),
        disposition=_disposition_for_attempt(attempt),
    )


def _invalid_response_record(type_name: str = "dict") -> LocalWorkerTurnHarnessRecord:
    return LocalWorkerTurnHarnessRecord(
        status="invalid_response",
        response=None,
        disposition=None,
        failure="response_type_invalid",
        reason=f"response_type_invalid:{type_name}",
        context_workflow_id=WORKFLOW_ID,
        context_contract_fingerprint=FINGERPRINT,
    )


def _worker_error_record(exception_name: str = "ValueError") -> LocalWorkerTurnHarnessRecord:
    return LocalWorkerTurnHarnessRecord(
        status="worker_error",
        response=None,
        disposition=None,
        failure="worker_exception",
        reason=f"worker_exception:{exception_name}",
        context_workflow_id=WORKFLOW_ID,
        context_contract_fingerprint=FINGERPRINT,
    )


def _expectation(**overrides: object) -> LocalWorkerScenarioExpectation:
    kwargs = {
        "scenario_id": "allowed_action",
        "category": "happy_action",
        "expected_status": "completed",
        "expected_disposition": "candidate_action_request",
        "expected_attempt_valid": True,
        "expected_action_id": ACTION_ID,
        "expected_response_kind": "action_request",
    }
    kwargs.update(overrides)
    return LocalWorkerScenarioExpectation(**kwargs)


def _passed_result(
    scenario_id: str = "passed_case",
    category: str = "happy_action",
) -> LocalWorkerScenarioResult:
    return LocalWorkerScenarioResult(
        scenario_id=scenario_id,
        category=category,
        context_workflow_id=WORKFLOW_ID,
        context_contract_fingerprint=FINGERPRINT,
        passed=True,
        checks=(
            LocalWorkerScenarioCheck(
                field="status",
                expected="completed",
                actual="completed",
                passed=True,
                reason="matched:status",
            ),
        ),
        reason="passed",
    )


def _failed_result(
    scenario_id: str = "failed_case",
    category: str = "harness_failure",
    field: str = "reason",
) -> LocalWorkerScenarioResult:
    return LocalWorkerScenarioResult(
        scenario_id=scenario_id,
        category=category,
        context_workflow_id=WORKFLOW_ID,
        context_contract_fingerprint=FINGERPRINT,
        passed=False,
        checks=(
            LocalWorkerScenarioCheck(
                field="status",
                expected="completed",
                actual="completed",
                passed=True,
                reason="matched:status",
            ),
            LocalWorkerScenarioCheck(
                field=field,
                expected="expected",
                actual="actual",
                passed=False,
                reason=f"mismatched:{field}",
            ),
        ),
        reason=f"failed:{field}",
    )


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_scenario_evaluation as module

    assert module.__all__ == (
        "LocalWorkerScenarioExpectation",
        "LocalWorkerScenarioCheck",
        "LocalWorkerScenarioResult",
        "LocalWorkerScenarioReport",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
    )
    assert "ScenarioScalar" not in module.__all__


def test_public_dataclasses_are_frozen() -> None:
    for cls in (
        LocalWorkerScenarioExpectation,
        LocalWorkerScenarioCheck,
        LocalWorkerScenarioResult,
        LocalWorkerScenarioReport,
    ):
        assert is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True

    result = evaluate_local_worker_scenario_result(
        _expectation(),
        _completed_record(),
    )
    with pytest.raises(FrozenInstanceError):
        result.reason = "changed"


def test_dataclass_fields_are_compact_and_response_free() -> None:
    assert tuple(field.name for field in fields(LocalWorkerScenarioExpectation)) == (
        "scenario_id",
        "category",
        "expected_status",
        "expected_disposition",
        "expected_harness_failure",
        "expected_attempt_valid",
        "expected_attempt_failure",
        "expected_action_id",
        "expected_response_kind",
        "expected_workflow_id",
        "expected_contract_fingerprint",
        "expected_reason",
    )
    assert tuple(field.name for field in fields(LocalWorkerScenarioResult)) == (
        "scenario_id",
        "category",
        "context_workflow_id",
        "context_contract_fingerprint",
        "passed",
        "checks",
        "reason",
    )
    assert "response" not in {field.name for field in fields(LocalWorkerScenarioResult)}
    assert "record" not in {field.name for field in fields(LocalWorkerScenarioResult)}


@pytest.mark.parametrize(
    "overrides",
    [
        {"scenario_id": ""},
        {"category": ""},
        {"expected_status": "pending"},
        {"expected_disposition": "execute_now"},
        {"expected_attempt_failure": "schema_failed"},
        {"expected_response_kind": "tool_call"},
        {"expected_harness_failure": ""},
        {"expected_action_id": ""},
        {"expected_workflow_id": ""},
        {"expected_contract_fingerprint": ""},
        {"expected_reason": ""},
    ],
)
def test_expectation_rejects_bad_values(overrides: dict[str, object]) -> None:
    kwargs = {
        "scenario_id": "case",
        "category": "authority_boundary",
        "expected_status": "completed",
        "expected_disposition": "blocked",
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerScenarioExpectation(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"scenario_id": 123},
        {"category": 123},
        {"expected_status": 123},
        {"expected_disposition": 123},
        {"expected_harness_failure": 123},
        {"expected_attempt_valid": "false"},
        {"expected_attempt_failure": 123},
        {"expected_action_id": 123},
        {"expected_response_kind": 123},
        {"expected_workflow_id": 123},
        {"expected_contract_fingerprint": 123},
        {"expected_reason": 123},
    ],
)
def test_expectation_rejects_bad_types(overrides: dict[str, object]) -> None:
    kwargs = {
        "scenario_id": "case",
        "category": "authority_boundary",
        "expected_status": "completed",
        "expected_disposition": "blocked",
    }
    kwargs.update(overrides)

    with pytest.raises(TypeError):
        LocalWorkerScenarioExpectation(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"expected_status": "completed", "expected_disposition": None},
        {
            "expected_status": "completed",
            "expected_disposition": "blocked",
            "expected_harness_failure": "response_type_invalid",
        },
        {
            "expected_status": "invalid_response",
            "expected_harness_failure": "response_type_invalid",
            "expected_disposition": "blocked",
        },
        {
            "expected_status": "worker_error",
            "expected_harness_failure": "worker_exception",
            "expected_attempt_valid": False,
        },
        {
            "expected_status": "worker_error",
            "expected_harness_failure": "worker_exception",
            "expected_attempt_failure": "unknown_action_id",
        },
        {
            "expected_status": "invalid_response",
            "expected_harness_failure": "response_type_invalid",
            "expected_action_id": ACTION_ID,
        },
        {
            "expected_status": "worker_error",
            "expected_harness_failure": "worker_exception",
            "expected_response_kind": "action_request",
        },
    ],
)
def test_expectation_enforces_plane_separation(overrides: dict[str, object]) -> None:
    kwargs = {
        "scenario_id": "case",
        "category": "plane",
        "expected_status": "completed",
        "expected_disposition": "candidate_action_request",
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerScenarioExpectation(**kwargs)


@pytest.mark.parametrize("status", ["invalid_response", "worker_error"])
def test_non_completed_expectations_require_harness_failure(status: str) -> None:
    with pytest.raises(ValueError, match="require expected_harness_failure"):
        LocalWorkerScenarioExpectation(
            scenario_id="raw_dict",
            category="harness_failure",
            expected_status=status,
        )


@pytest.mark.parametrize(
    ("kwargs", "error_type"),
    [
        (
            {
                "field": "",
                "expected": "completed",
                "actual": "completed",
                "passed": True,
                "reason": "matched:status",
            },
            ValueError,
        ),
        (
            {
                "field": "status",
                "expected": 1,
                "actual": "completed",
                "passed": True,
                "reason": "matched:status",
            },
            TypeError,
        ),
        (
            {
                "field": "status",
                "expected": "completed",
                "actual": {"status": "completed"},
                "passed": True,
                "reason": "matched:status",
            },
            TypeError,
        ),
        (
            {
                "field": "status",
                "expected": "completed",
                "actual": "completed",
                "passed": 1,
                "reason": "matched:status",
            },
            TypeError,
        ),
        (
            {
                "field": "status",
                "expected": "completed",
                "actual": "completed",
                "passed": True,
                "reason": "mismatched:status",
            },
            ValueError,
        ),
        (
            {
                "field": "status",
                "expected": "completed",
                "actual": "worker_error",
                "passed": True,
                "reason": "matched:status",
            },
            ValueError,
        ),
    ],
)
def test_check_rejects_non_scalar_and_incoherent_values(
    kwargs: dict[str, object],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        LocalWorkerScenarioCheck(**kwargs)


def test_completed_action_result_passes_with_exact_checks() -> None:
    result = evaluate_local_worker_scenario_result(
        _expectation(
            expected_workflow_id=WORKFLOW_ID,
            expected_contract_fingerprint=FINGERPRINT,
            expected_reason="completed:candidate_action_request",
        ),
        _completed_record(),
    )

    assert result.passed is True
    assert result.reason == "passed"
    assert result.context_workflow_id == WORKFLOW_ID
    assert result.context_contract_fingerprint == FINGERPRINT
    assert [(check.field, check.passed, check.reason) for check in result.checks] == [
        ("status", True, "matched:status"),
        ("disposition", True, "matched:disposition"),
        ("attempt.valid", True, "matched:attempt.valid"),
        ("attempt.action_id", True, "matched:attempt.action_id"),
        ("attempt.response_kind", True, "matched:attempt.response_kind"),
        ("reason", True, "matched:reason"),
        ("context.workflow_id", True, "matched:context.workflow_id"),
        (
            "context.contract_fingerprint",
            True,
            "matched:context.contract_fingerprint",
        ),
    ]


def test_completed_blocked_unknown_action_result_passes() -> None:
    action_id = "gh_update_script:v1"
    result = evaluate_local_worker_scenario_result(
        _expectation(
            scenario_id="unknown_action",
            category="authority_boundary",
            expected_disposition="blocked",
            expected_attempt_valid=False,
            expected_attempt_failure="unknown_action_id",
            expected_action_id=action_id,
            expected_response_kind="action_request",
            expected_reason="completed:blocked",
        ),
        _blocked_record(action_id),
    )

    assert result.passed is True
    assert result.reason == "passed"
    assert {check.field: check.actual for check in result.checks}[
        "attempt.failure"
    ] == "unknown_action_id"


def test_wrong_plane_actual_returns_failed_result_not_exception() -> None:
    result = evaluate_local_worker_scenario_result(
        _expectation(),
        _invalid_response_record(),
    )

    assert result.passed is False
    assert result.reason == "failed:status"
    assert {check.field: check.actual for check in result.checks} == {
        "status": "invalid_response",
        "disposition": None,
        "attempt.valid": None,
        "attempt.action_id": None,
        "attempt.response_kind": None,
    }


def test_invalid_response_path_passes_without_attempt_inspection() -> None:
    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="raw_dict",
            category="harness_failure",
            expected_status="invalid_response",
            expected_harness_failure="response_type_invalid",
            expected_reason="response_type_invalid:dict",
            expected_workflow_id=WORKFLOW_ID,
            expected_contract_fingerprint=FINGERPRINT,
        ),
        _invalid_response_record(),
    )

    assert result.passed is True
    assert [check.field for check in result.checks] == [
        "status",
        "harness.failure",
        "reason",
        "context.workflow_id",
        "context.contract_fingerprint",
    ]


def test_worker_error_path_passes_without_attempt_inspection() -> None:
    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="raised",
            category="harness_failure",
            expected_status="worker_error",
            expected_harness_failure="worker_exception",
            expected_reason="worker_exception:ValueError",
        ),
        _worker_error_record(),
    )

    assert result.passed is True
    assert {check.field: check.actual for check in result.checks}[
        "harness.failure"
    ] == "worker_exception"


def test_exact_reason_mismatch_is_first_failed_reason_check() -> None:
    result = evaluate_local_worker_scenario_result(
        _expectation(expected_reason="completed:blocked"),
        _completed_record(),
    )

    assert result.passed is False
    assert result.reason == "failed:reason"
    assert result.checks[-1] == LocalWorkerScenarioCheck(
        field="reason",
        expected="completed:blocked",
        actual="completed:candidate_action_request",
        passed=False,
        reason="mismatched:reason",
    )


def test_api_rejects_wrong_input_types() -> None:
    with pytest.raises(TypeError):
        evaluate_local_worker_scenario_result(object(), _completed_record())
    with pytest.raises(TypeError):
        evaluate_local_worker_scenario_result(_expectation(), object())
    with pytest.raises(TypeError):
        build_local_worker_scenario_report((_passed_result(), object()))
    with pytest.raises(TypeError):
        build_local_worker_scenario_report(object())


def test_result_validates_coherence_and_freezes_checks() -> None:
    check = LocalWorkerScenarioCheck(
        field="status",
        expected="completed",
        actual="completed",
        passed=True,
        reason="matched:status",
    )
    result = LocalWorkerScenarioResult(
        scenario_id="coherent",
        category="shape",
        context_workflow_id=WORKFLOW_ID,
        context_contract_fingerprint=FINGERPRINT,
        passed=True,
        checks=[check],
        reason="passed",
    )
    assert result.checks == (check,)

    with pytest.raises(ValueError):
        LocalWorkerScenarioResult(
            scenario_id="bad",
            category="shape",
            context_workflow_id=WORKFLOW_ID,
            context_contract_fingerprint=FINGERPRINT,
            passed=False,
            checks=(check,),
            reason="failed:status",
        )
    with pytest.raises(ValueError):
        LocalWorkerScenarioResult(
            scenario_id="bad",
            category="shape",
            context_workflow_id=WORKFLOW_ID,
            context_contract_fingerprint=FINGERPRINT,
            passed=True,
            checks=(check,),
            reason="failed:status",
        )


def test_report_grouping_and_mapping_immutability() -> None:
    passed = _passed_result()
    failed_reason = _failed_result(
        scenario_id="failed_reason",
        category="harness_failure",
        field="reason",
    )
    failed_status = _failed_result(
        scenario_id="failed_status",
        category="authority_boundary",
        field="status",
    )

    report = build_local_worker_scenario_report(
        [passed, failed_reason, failed_status]
    )

    assert report.total == 3
    assert report.passed == 1
    assert report.failed == 2
    assert report.results == (passed, failed_reason, failed_status)
    assert report.failure_fields == {"reason": 1, "status": 1}
    assert report.failure_reasons == {"failed:reason": 1, "failed:status": 1}
    assert report.failure_categories == {
        "harness_failure": 1,
        "authority_boundary": 1,
    }
    assert isinstance(report.failure_fields, MappingProxyType)

    with pytest.raises(TypeError):
        report.failure_fields["reason"] = 2

    source_fields = {"reason": 1}
    direct = LocalWorkerScenarioReport(
        total=1,
        passed=0,
        failed=1,
        results=(failed_reason,),
        failure_fields=source_fields,
        failure_reasons={"failed:reason": 1},
        failure_categories={"harness_failure": 1},
    )
    source_fields["status"] = 9
    assert direct.failure_fields == {"reason": 1}


def test_report_rejects_duplicate_ids_empty_and_incoherent_counts() -> None:
    with pytest.raises(ValueError):
        build_local_worker_scenario_report(())
    with pytest.raises(ValueError):
        build_local_worker_scenario_report(
            [_passed_result("dup"), _failed_result("dup")]
        )
    with pytest.raises(ValueError):
        LocalWorkerScenarioReport(
            total=1,
            passed=1,
            failed=1,
            results=(_passed_result(),),
            failure_fields={},
            failure_reasons={},
            failure_categories={},
        )
    with pytest.raises(TypeError):
        LocalWorkerScenarioReport(
            total=1,
            passed=0,
            failed=1,
            results=(_failed_result(),),
            failure_fields={"reason": True},
            failure_reasons={"failed:reason": 1},
            failure_categories={"harness_failure": 1},
        )


def test_direct_report_construction_rejects_empty_results() -> None:
    with pytest.raises(ValueError):
        LocalWorkerScenarioReport(
            total=0,
            passed=0,
            failed=0,
            results=(),
            failure_fields={},
            failure_reasons={},
            failure_categories={},
        )


def test_direct_report_construction_rejects_duplicate_scenario_ids() -> None:
    first = _failed_result("dup", field="reason")
    second = _failed_result("dup", field="status")

    with pytest.raises(ValueError):
        LocalWorkerScenarioReport(
            total=2,
            passed=0,
            failed=2,
            results=(first, second),
            failure_fields={"reason": 1, "status": 1},
            failure_reasons={"failed:reason": 1, "failed:status": 1},
            failure_categories={"harness_failure": 2},
        )


def test_small_real_lm5a_to_lm5f_integration_chain() -> None:
    context = _context()

    record = run_local_worker_turn(
        context,
        lambda ctx: _action_response(ctx.allowed_actions[0].action_id),
    )
    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="integration_allowed_action",
            category="integration",
            expected_status="completed",
            expected_disposition="candidate_action_request",
            expected_attempt_valid=True,
            expected_action_id=ACTION_ID,
            expected_response_kind="action_request",
            expected_workflow_id=context.workflow.workflow_id,
            expected_contract_fingerprint=context.workflow.contract_fingerprint,
            expected_reason="completed:candidate_action_request",
        ),
        record,
    )
    report = build_local_worker_scenario_report([result])

    assert result.passed is True
    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0


def test_local_worker_scenario_evaluation_module_boundary_is_receipt_only() -> None:
    import rook.agent.local_worker_scenario_evaluation as module

    source = inspect.getsource(module)
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    banned_names = {
        "LocalWorkerTurnContext",
        "WorkerAllowedAction",
        "run_local_worker_turn",
        "compile_workflow_contract",
        "Path",
        "open",
        "json",
        "yaml",
        "time",
        "datetime",
        "sleep",
        "uuid",
        "hashlib",
        "retry",
        "fallback",
        "critic",
        "oversight",
        "model",
        "prompt",
        "stream",
        "runtime",
        "server",
        "dispatcher",
    }
    banned_modules = {
        "json",
        "yaml",
        "time",
        "datetime",
        "uuid",
        "hashlib",
        "pathlib",
        "rook.agent.local_worker_turn_context",
        "rook.agent.plan_graph_workflow_contract",
        "rook.agent.plan_graph_current_step_stream",
        "rook.agent.plan_graph_current_step_runner",
        "rook.agent.plan_graph_step_executor",
        "rook.agent.plan_graph_step_mapping",
        "rook.agent.plan_graph_live",
        "rook.agent.plan_graph_live_runner",
        "rook.agent.chat",
        "rook.agent.base_agent",
        "rook.agent.tool_dispatcher",
    }
    imported_module_roots = {
        module.split(".", maxsplit=1)[0] for module in imported_modules
    }
    assert not (banned_names & imported_names)
    assert not (banned_modules & imported_modules)
    assert not (banned_modules & imported_module_roots)
    assert not (banned_names & called_names)
