# LM5F Local Worker Scenario Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic scenario-evaluation receipt layer over existing LM5D local-worker harness records.

**Architecture:** LM5F is a small production module that evaluates an already-produced `LocalWorkerTurnHarnessRecord` against a compact expectation, then aggregates already-evaluated results into an immutable report. It does not run workers, build contexts, define scenarios, inspect response payloads, call models, serialize reports, read files, dispatch actions, mutate graphs, or touch LM5A-E modules.

**Tech Stack:** Python frozen dataclasses, `MappingProxyType`, LM5B/C/D literal vocabularies, pytest, AST import/call boundary checks.

---

## File Structure

- Create: `mcp_server/src/rook/agent/local_worker_scenario_evaluation.py`
  - Owns the LM5F public evaluation receipt surface.
  - Exports only expectation/check/result/report dataclasses and two pure functions.
  - Imports only stdlib dataclass/mapping helpers plus LM5B/C/D receipt vocabulary and harness record types.

- Create: `mcp_server/tests/test_local_worker_scenario_evaluation.py`
  - Owns unit coverage, a small LM5A-D integration proof, and an AST/import boundary guard for the new production module.
  - May import LM5A builders and LM4 workflow compiler helpers for integration fixtures.

- Do not modify:
  - `mcp_server/src/rook/agent/local_worker_turn_context.py`
  - `mcp_server/src/rook/agent/local_worker_turn_response.py`
  - `mcp_server/src/rook/agent/local_worker_turn_disposition.py`
  - `mcp_server/src/rook/agent/local_worker_turn_harness.py`
  - `mcp_server/tests/test_local_worker_turn_scenarios.py`

There is a known unrelated untracked `.claude/worktrees/` directory in this workspace. Do not stage, edit, remove, or mention it as LM5F work.

---

## Task 0: Verify Branch Baseline

**Files:**

- Verify: `docs/superpowers/specs/2026-06-30-lm5f-local-worker-scenario-evaluation-design.md`
- Verify: `docs/superpowers/plans/2026-06-30-lm5f-local-worker-scenario-evaluation.md`

- [ ] **Step 1: Confirm branch and committed diff before code**

Run:

```powershell
git status --short --branch
git diff --name-status main..HEAD
```

Expected branch:

```text
## codex/lm5f-local-worker-scenario-evaluation
```

Expected committed diff before implementation:

```text
A	docs/superpowers/plans/2026-06-30-lm5f-local-worker-scenario-evaluation.md
A	docs/superpowers/specs/2026-06-30-lm5f-local-worker-scenario-evaluation-design.md
```

The untracked `.claude/worktrees/` directory may appear in `git status`. Leave it untouched.

- [ ] **Step 2: Confirm clean diff hygiene before code**

Run:

```powershell
git diff --check main..HEAD
```

Expected output: no output.

If this command reports whitespace issues in the spec or this plan, fix those docs before starting implementation.

---

## Task 1: Add LM5F Tests First

**Files:**

- Create: `mcp_server/tests/test_local_worker_scenario_evaluation.py`

- [ ] **Step 1: Create the test file**

Create `mcp_server/tests/test_local_worker_scenario_evaluation.py` with this content:

```python
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
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerWorkflowSummary,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_disposition import (
    LocalWorkerTurnDispositionRecord,
    dispose_local_worker_turn_response,
)
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


def _minimal_context(
    *,
    workflow_id: str = "lm5f_worker_evaluation",
    contract_fingerprint: str = "f" * 64,
    action_ids: tuple[str, ...] = ("draft_bind_params",),
) -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id=workflow_id,
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint=contract_fingerprint,
            compiler_id="rook_workflow_contract_compiler:v1",
            provider_id="catalog_current_step_provider:v1",
            selected_template_id="gh_csharp_create_verify_repair_verify",
            max_steps=6,
        ),
        current_graph=WorkerGraphSummary(
            node_count=0,
            node_ids=(),
            ready_node_ids=(),
            terminal_node_ids=(),
            status_counts={},
        ),
        current_node=None,
        history=WorkerHistorySummary(
            current_step_count=0,
            supply_count=0,
            last_accepted_node_id=None,
            last_execution_kind=None,
            last_stop_reason=None,
            recent_steps=(),
            recent_supplies=(),
        ),
        knowledge=(),
        allowed_actions=tuple(
            WorkerAllowedAction(
                action_id=action_id,
                kind="draft",
                description="Draft replacement C# body parameters.",
                input_schema={},
            )
            for action_id in action_ids
        ),
    )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5f_worker_evaluation",
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


def _action_response(action_id: str = "draft_bind_params") -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=action_id,
            rationale="Draft repair params.",
            input={"code": "A = 42.0;"},
        )
    )


def _attempt(
    *,
    valid: bool,
    response_kind: str | None,
    failure: str | None,
    reason: str,
    action_id: str | None,
    workflow_id: str = "lm5f_worker_evaluation",
    contract_fingerprint: str = "f" * 64,
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


def _valid_action_attempt(
    action_id: str = "draft_bind_params",
) -> LocalWorkerTurnAttemptRecord:
    return _attempt(
        valid=True,
        response_kind="action_request",
        failure=None,
        reason="valid_action_request",
        action_id=action_id,
    )


def _unknown_action_attempt(
    action_id: str = "gh_update_script:v1",
) -> LocalWorkerTurnAttemptRecord:
    return _attempt(
        valid=False,
        response_kind="action_request",
        failure="unknown_action_id",
        reason=f"unknown_action_id:{action_id}",
        action_id=action_id,
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
        disposition = _disposition_for_attempt(_valid_action_attempt())
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
    attempt = _unknown_action_attempt(action_id)
    return _completed_record(
        response=_action_response(action_id),
        disposition=_disposition_for_attempt(attempt),
    )


def _invalid_response_record(type_name: str = "dict") -> LocalWorkerTurnHarnessRecord:
    context = _minimal_context()
    return LocalWorkerTurnHarnessRecord(
        status="invalid_response",
        response=None,
        disposition=None,
        failure="response_type_invalid",
        reason=f"response_type_invalid:{type_name}",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def _worker_error_record(exception_name: str = "ValueError") -> LocalWorkerTurnHarnessRecord:
    context = _minimal_context()
    return LocalWorkerTurnHarnessRecord(
        status="worker_error",
        response=None,
        disposition=None,
        failure="worker_exception",
        reason=f"worker_exception:{exception_name}",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def _expectation(
    **overrides: object,
) -> LocalWorkerScenarioExpectation:
    kwargs = {
        "scenario_id": "allowed_action",
        "category": "happy_action",
        "expected_status": "completed",
        "expected_disposition": "candidate_action_request",
        "expected_attempt_valid": True,
        "expected_action_id": "draft_bind_params",
        "expected_response_kind": "action_request",
    }
    kwargs.update(overrides)
    return LocalWorkerScenarioExpectation(**kwargs)


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
    assert "evaluate_local_worker_scenario_report" not in module.__all__


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
            "expected_action_id": "draft_bind_params",
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
                "actual": "completed",
                "passed": "yes",
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
                "passed": False,
                "reason": "matched:status",
            },
            ValueError,
        ),
    ],
)
def test_check_validates_scalar_values_and_reason_coherence(
    kwargs: dict[str, object],
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        LocalWorkerScenarioCheck(**kwargs)


def test_completed_action_expectation_evaluates_expected_fields_only() -> None:
    expectation = _expectation(
        expected_workflow_id="lm5f_worker_evaluation",
        expected_contract_fingerprint="f" * 64,
        expected_reason="completed:candidate_action_request",
    )
    record = _completed_record()

    result = evaluate_local_worker_scenario_result(expectation, record)

    assert result.scenario_id == "allowed_action"
    assert result.category == "happy_action"
    assert result.context_workflow_id == "lm5f_worker_evaluation"
    assert result.context_contract_fingerprint == "f" * 64
    assert result.passed is True
    assert result.reason == "passed"
    assert [(check.field, check.expected, check.actual, check.reason) for check in result.checks] == [
        ("status", "completed", "completed", "matched:status"),
        (
            "disposition",
            "candidate_action_request",
            "candidate_action_request",
            "matched:disposition",
        ),
        ("attempt.valid", True, True, "matched:attempt.valid"),
        (
            "attempt.action_id",
            "draft_bind_params",
            "draft_bind_params",
            "matched:attempt.action_id",
        ),
        (
            "attempt.response_kind",
            "action_request",
            "action_request",
            "matched:attempt.response_kind",
        ),
        ("reason", "completed:candidate_action_request", "completed:candidate_action_request", "matched:reason"),
        ("context.workflow_id", "lm5f_worker_evaluation", "lm5f_worker_evaluation", "matched:context.workflow_id"),
        ("context.contract_fingerprint", "f" * 64, "f" * 64, "matched:context.contract_fingerprint"),
    ]


def test_completed_blocked_unknown_action_can_pass_expectation() -> None:
    expectation = LocalWorkerScenarioExpectation(
        scenario_id="execution_ref_as_action",
        category="authority_boundary",
        expected_status="completed",
        expected_disposition="blocked",
        expected_attempt_valid=False,
        expected_attempt_failure="unknown_action_id",
        expected_action_id="gh_update_script:v1",
        expected_response_kind="action_request",
        expected_reason="completed:blocked",
    )

    result = evaluate_local_worker_scenario_result(expectation, _blocked_record())

    assert result.passed is True
    assert result.reason == "passed"
    assert {check.field for check in result.checks} == {
        "status",
        "disposition",
        "attempt.valid",
        "attempt.failure",
        "attempt.action_id",
        "attempt.response_kind",
        "reason",
    }


def test_wrong_plane_actual_returns_failed_result_not_exception() -> None:
    expectation = LocalWorkerScenarioExpectation(
        scenario_id="expected_action",
        category="wrong_plane",
        expected_status="completed",
        expected_disposition="candidate_action_request",
        expected_attempt_valid=True,
        expected_action_id="draft_bind_params",
    )

    result = evaluate_local_worker_scenario_result(expectation, _worker_error_record())

    assert result.passed is False
    assert result.reason == "failed:status"
    assert [(check.field, check.expected, check.actual, check.passed) for check in result.checks] == [
        ("status", "completed", "worker_error", False),
        ("disposition", "candidate_action_request", None, False),
        ("attempt.valid", True, None, False),
        ("attempt.action_id", "draft_bind_params", None, False),
    ]


def test_invalid_response_expectation_checks_harness_plane_only() -> None:
    expectation = LocalWorkerScenarioExpectation(
        scenario_id="raw_dict",
        category="harness_failure",
        expected_status="invalid_response",
        expected_harness_failure="response_type_invalid",
        expected_reason="response_type_invalid:dict",
    )

    result = evaluate_local_worker_scenario_result(
        expectation,
        _invalid_response_record(),
    )

    assert result.passed is True
    assert [(check.field, check.expected, check.actual) for check in result.checks] == [
        ("status", "invalid_response", "invalid_response"),
        ("harness.failure", "response_type_invalid", "response_type_invalid"),
        ("reason", "response_type_invalid:dict", "response_type_invalid:dict"),
    ]


def test_worker_error_expectation_checks_harness_plane_only() -> None:
    expectation = LocalWorkerScenarioExpectation(
        scenario_id="raising_worker",
        category="harness_failure",
        expected_status="worker_error",
        expected_harness_failure="worker_exception",
        expected_reason="worker_exception:ValueError",
    )

    result = evaluate_local_worker_scenario_result(
        expectation,
        _worker_error_record(),
    )

    assert result.passed is True
    assert [(check.field, check.expected, check.actual) for check in result.checks] == [
        ("status", "worker_error", "worker_error"),
        ("harness.failure", "worker_exception", "worker_exception"),
        ("reason", "worker_exception:ValueError", "worker_exception:ValueError"),
    ]


def test_reason_check_is_exact_string_match() -> None:
    expectation = _expectation(expected_reason="completed:blocked")

    result = evaluate_local_worker_scenario_result(expectation, _completed_record())

    assert result.passed is False
    assert result.reason == "failed:reason"
    reason_check = result.checks[-1]
    assert reason_check.field == "reason"
    assert reason_check.expected == "completed:blocked"
    assert reason_check.actual == "completed:candidate_action_request"
    assert reason_check.reason == "mismatched:reason"


@pytest.mark.parametrize(
    ("bad_expectation", "bad_record"),
    [
        (object(), _completed_record()),
        (_expectation(), object()),
    ],
)
def test_evaluator_rejects_bad_api_types(
    bad_expectation: object,
    bad_record: object,
) -> None:
    with pytest.raises(TypeError):
        evaluate_local_worker_scenario_result(bad_expectation, bad_record)


def test_result_direct_construction_rejects_incoherence() -> None:
    passed_check = LocalWorkerScenarioCheck(
        field="status",
        expected="completed",
        actual="completed",
        passed=True,
        reason="matched:status",
    )
    failed_check = LocalWorkerScenarioCheck(
        field="disposition",
        expected="blocked",
        actual="candidate_action_request",
        passed=False,
        reason="mismatched:disposition",
    )

    with pytest.raises(ValueError):
        LocalWorkerScenarioResult(
            scenario_id="case",
            category="category",
            context_workflow_id="workflow",
            context_contract_fingerprint="fingerprint",
            passed=True,
            checks=(passed_check, failed_check),
            reason="passed",
        )

    with pytest.raises(ValueError):
        LocalWorkerScenarioResult(
            scenario_id="case",
            category="category",
            context_workflow_id="workflow",
            context_contract_fingerprint="fingerprint",
            passed=False,
            checks=(failed_check,),
            reason="failed:status",
        )

    with pytest.raises(ValueError):
        LocalWorkerScenarioResult(
            scenario_id="case",
            category="category",
            context_workflow_id="workflow",
            context_contract_fingerprint="fingerprint",
            passed=True,
            checks=(),
            reason="passed",
        )


def test_result_checks_are_tuple_frozen_from_list() -> None:
    check = LocalWorkerScenarioCheck(
        field="status",
        expected="completed",
        actual="completed",
        passed=True,
        reason="matched:status",
    )
    source_checks = [check]

    result = LocalWorkerScenarioResult(
        scenario_id="case",
        category="category",
        context_workflow_id="workflow",
        context_contract_fingerprint="fingerprint",
        passed=True,
        checks=source_checks,
        reason="passed",
    )
    source_checks.append(check)

    assert result.checks == (check,)


def test_build_report_aggregates_failures_and_freezes_mappings() -> None:
    passed = evaluate_local_worker_scenario_result(_expectation(), _completed_record())
    failed_status = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="expected_worker_error",
            category="harness_failure",
            expected_status="worker_error",
            expected_harness_failure="worker_exception",
        ),
        _completed_record(),
    )
    failed_action = evaluate_local_worker_scenario_result(
        _expectation(
            scenario_id="wrong_action",
            category="authority_boundary",
            expected_action_id="other_action",
        ),
        _completed_record(),
    )

    report = build_local_worker_scenario_report([passed, failed_status, failed_action])

    assert report.total == 3
    assert report.passed == 1
    assert report.failed == 2
    assert report.results == (passed, failed_status, failed_action)
    assert report.failure_fields == {"status": 1, "attempt.action_id": 1}
    assert report.failure_reasons == {
        "failed:status": 1,
        "failed:attempt.action_id": 1,
    }
    assert report.failure_categories == {
        "harness_failure": 1,
        "authority_boundary": 1,
    }
    assert isinstance(report.failure_fields, MappingProxyType)
    with pytest.raises(TypeError):
        report.failure_fields["late"] = 1


@pytest.mark.parametrize(
    "results",
    [
        (),
        [],
    ],
)
def test_build_report_rejects_empty_results(results: object) -> None:
    with pytest.raises(ValueError):
        build_local_worker_scenario_report(results)


def test_build_report_rejects_duplicate_scenario_ids() -> None:
    first = evaluate_local_worker_scenario_result(_expectation(), _completed_record())
    second = evaluate_local_worker_scenario_result(_expectation(), _completed_record())

    with pytest.raises(ValueError):
        build_local_worker_scenario_report((first, second))


@pytest.mark.parametrize(
    "bad_results",
    [
        object(),
        (object(),),
    ],
)
def test_build_report_rejects_bad_input_types(bad_results: object) -> None:
    with pytest.raises(TypeError):
        build_local_worker_scenario_report(bad_results)


def test_report_direct_construction_validates_counts_and_groupings() -> None:
    result = evaluate_local_worker_scenario_result(_expectation(), _completed_record())
    with pytest.raises(ValueError):
        LocalWorkerScenarioReport(
            total=2,
            passed=1,
            failed=1,
            results=(result,),
            failure_fields={},
            failure_reasons={},
            failure_categories={},
        )
    with pytest.raises(ValueError):
        LocalWorkerScenarioReport(
            total=1,
            passed=1,
            failed=0,
            results=(result,),
            failure_fields={"status": 1},
            failure_reasons={},
            failure_categories={},
        )
    with pytest.raises(TypeError):
        LocalWorkerScenarioReport(
            total=1,
            passed=1,
            failed=0,
            results=(result,),
            failure_fields={1: 1},
            failure_reasons={},
            failure_categories={},
        )
    with pytest.raises(TypeError):
        LocalWorkerScenarioReport(
            total=1,
            passed=1,
            failed=0,
            results=(result,),
            failure_fields={"status": True},
            failure_reasons={},
            failure_categories={},
        )


def test_real_lm5a_to_lm5f_chain_evaluates_allowed_action() -> None:
    scaffold = compile_workflow_contract(_repair_contract())
    action = WorkerAllowedAction(
        action_id="draft_bind_params",
        kind="draft",
        description="Draft replacement C# body parameters.",
        input_schema={
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    )
    context = build_local_worker_turn_context(
        scaffold,
        copy.deepcopy(scaffold.graph),
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(),
        allowed_actions=(action,),
    )
    response = _action_response(action_id=context.allowed_actions[0].action_id)

    harness_record = run_local_worker_turn(context, lambda received_context: response)
    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="real_chain_allowed_action",
            category="happy_action",
            expected_status="completed",
            expected_disposition="candidate_action_request",
            expected_attempt_valid=True,
            expected_action_id=context.allowed_actions[0].action_id,
            expected_response_kind="action_request",
            expected_workflow_id=context.workflow.workflow_id,
            expected_contract_fingerprint=context.workflow.contract_fingerprint,
        ),
        harness_record,
    )
    report = build_local_worker_scenario_report((result,))

    assert result.passed is True
    assert result.context_workflow_id == context.workflow.workflow_id
    assert result.context_contract_fingerprint == context.workflow.contract_fingerprint
    assert report.total == 1
    assert report.passed == 1
    assert report.failed == 0


def test_local_worker_scenario_evaluation_module_boundary_is_receipt_only() -> None:
    import rook.agent.local_worker_scenario_evaluation as module

    source = inspect.getsource(module)
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    referenced_names: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    assert imported_modules <= {
        "__future__",
        "collections.abc",
        "dataclasses",
        "types",
        "rook.agent.local_worker_turn_response",
        "rook.agent.local_worker_turn_disposition",
        "rook.agent.local_worker_turn_harness",
    }

    banned_names = {
        "LocalWorkerTurnContext",
        "WorkerAllowedAction",
        "run_local_worker_turn",
        "LocalWorkerTurnWorker",
        "compile_workflow_contract",
        "snapshot_workflow_contract",
        "load_workflow_contract_payload",
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "CurrentStepRecord",
        "EnvelopeSupplyRecord",
        "EnvelopeSupplyResult",
        "PlanGraph",
        "CompiledWorkflowScaffold",
        "CatalogCurrentStepProvider",
        "WorkflowProvenanceEnvelopeSource",
        "RookAgent",
        "base_agent",
        "dispatcher",
        "server",
        "model",
        "prompt",
        "litellm",
        "OpenAI",
        "Path",
        "open",
        "json",
        "yaml",
        "loads",
        "dumps",
        "time",
        "datetime",
        "sleep",
        "uuid",
        "hashlib",
        "retry",
        "fallback",
        "critic",
        "oversight",
        "to_json",
        "to_dict",
        "write_report",
        "read_report",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps", "sleep"} & called_names)
```

- [ ] **Step 2: Run the targeted test and verify RED**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_scenario_evaluation.py -q
```

Expected output includes:

```text
ModuleNotFoundError: No module named 'rook.agent.local_worker_scenario_evaluation'
```

If the failure is anything other than the missing production module, fix the test file before continuing.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add mcp_server\tests\test_local_worker_scenario_evaluation.py
git commit -m "test(lm5f): add scenario evaluation tests"
```

Expected result: commit succeeds and stages only the new LM5F test file.

---

## Task 2: Add Production Evaluation Module

**Files:**

- Create: `mcp_server/src/rook/agent/local_worker_scenario_evaluation.py`

- [ ] **Step 1: Create the production module**

Create `mcp_server/src/rook/agent/local_worker_scenario_evaluation.py` with this content:

```python
"""LM5F deterministic local-worker scenario evaluation receipts."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from rook.agent.local_worker_turn_disposition import WorkerResponseDisposition
from rook.agent.local_worker_turn_harness import (
    HarnessStatus,
    LocalWorkerTurnHarnessRecord,
)
from rook.agent.local_worker_turn_response import (
    WorkerResponseKind,
    WorkerResponseValidationFailure,
)

__all__ = (
    "LocalWorkerScenarioExpectation",
    "LocalWorkerScenarioCheck",
    "LocalWorkerScenarioResult",
    "LocalWorkerScenarioReport",
    "evaluate_local_worker_scenario_result",
    "build_local_worker_scenario_report",
)

ScenarioScalar = str | bool | None

_HARNESS_STATUSES = frozenset(
    {
        "completed",
        "invalid_response",
        "worker_error",
    }
)
_DISPOSITIONS = frozenset(
    {
        "blocked",
        "candidate_action_request",
        "clarification_needed",
        "refusal_recorded",
        "observation_recorded",
    }
)
_ATTEMPT_FAILURES = frozenset(
    {
        "payload_invalid",
        "unknown_action_id",
        "action_input_invalid",
    }
)
_RESPONSE_KINDS = frozenset(
    {
        "action_request",
        "clarification_request",
        "refusal",
        "observation",
    }
)


@dataclass(frozen=True)
class LocalWorkerScenarioExpectation:
    scenario_id: str
    category: str
    expected_status: HarnessStatus
    expected_disposition: WorkerResponseDisposition | None = None
    expected_harness_failure: str | None = None
    expected_attempt_valid: bool | None = None
    expected_attempt_failure: WorkerResponseValidationFailure | None = None
    expected_action_id: str | None = None
    expected_response_kind: WorkerResponseKind | None = None
    expected_workflow_id: str | None = None
    expected_contract_fingerprint: str | None = None
    expected_reason: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_str(self.scenario_id, "scenario_id")
        _require_non_empty_str(self.category, "category")
        status = _require_choice(
            self.expected_status,
            _HARNESS_STATUSES,
            "expected_status",
        )
        _require_optional_choice(
            self.expected_disposition,
            _DISPOSITIONS,
            "expected_disposition",
        )
        _require_optional_non_empty_str(
            self.expected_harness_failure,
            "expected_harness_failure",
        )
        _require_optional_bool(
            self.expected_attempt_valid,
            "expected_attempt_valid",
        )
        _require_optional_choice(
            self.expected_attempt_failure,
            _ATTEMPT_FAILURES,
            "expected_attempt_failure",
        )
        _require_optional_non_empty_str(
            self.expected_action_id,
            "expected_action_id",
        )
        _require_optional_choice(
            self.expected_response_kind,
            _RESPONSE_KINDS,
            "expected_response_kind",
        )
        _require_optional_non_empty_str(
            self.expected_workflow_id,
            "expected_workflow_id",
        )
        _require_optional_non_empty_str(
            self.expected_contract_fingerprint,
            "expected_contract_fingerprint",
        )
        _require_optional_non_empty_str(self.expected_reason, "expected_reason")
        _validate_expectation_plane(self, status)


@dataclass(frozen=True)
class LocalWorkerScenarioCheck:
    field: str
    expected: ScenarioScalar
    actual: ScenarioScalar
    passed: bool
    reason: str

    def __post_init__(self) -> None:
        field = _require_non_empty_str(self.field, "field")
        _require_scenario_scalar(self.expected, "expected")
        _require_scenario_scalar(self.actual, "actual")
        passed = _require_bool(self.passed, "passed")
        reason = _require_non_empty_str(self.reason, "reason")
        expected_reason = (
            f"matched:{field}" if passed else f"mismatched:{field}"
        )
        if reason != expected_reason:
            raise ValueError("check reason must match field and passed")


@dataclass(frozen=True)
class LocalWorkerScenarioResult:
    scenario_id: str
    category: str
    context_workflow_id: str
    context_contract_fingerprint: str
    passed: bool
    checks: tuple[LocalWorkerScenarioCheck, ...]
    reason: str

    def __post_init__(self) -> None:
        _require_non_empty_str(self.scenario_id, "scenario_id")
        _require_non_empty_str(self.category, "category")
        _require_non_empty_str(self.context_workflow_id, "context_workflow_id")
        _require_non_empty_str(
            self.context_contract_fingerprint,
            "context_contract_fingerprint",
        )
        passed = _require_bool(self.passed, "passed")
        checks = _freeze_instance_tuple(
            self.checks,
            LocalWorkerScenarioCheck,
            "checks",
        )
        if not checks:
            raise ValueError("checks must not be empty")
        object.__setattr__(self, "checks", checks)
        reason = _require_non_empty_str(self.reason, "reason")

        actual_passed = all(check.passed for check in checks)
        if passed != actual_passed:
            raise ValueError("passed must match check outcomes")
        expected_reason = (
            "passed"
            if actual_passed
            else f"failed:{_first_failed_check(checks).field}"
        )
        if reason != expected_reason:
            raise ValueError("result reason must match first failed check")


@dataclass(frozen=True)
class LocalWorkerScenarioReport:
    total: int
    passed: int
    failed: int
    results: tuple[LocalWorkerScenarioResult, ...]
    failure_fields: Mapping[str, int]
    failure_reasons: Mapping[str, int]
    failure_categories: Mapping[str, int]

    def __post_init__(self) -> None:
        results = _freeze_instance_tuple(
            self.results,
            LocalWorkerScenarioResult,
            "results",
        )
        if not results:
            raise ValueError("results must not be empty")
        _reject_duplicate_scenario_ids(results)
        object.__setattr__(self, "results", results)

        total = _require_non_negative_int(self.total, "total")
        passed = _require_non_negative_int(self.passed, "passed")
        failed = _require_non_negative_int(self.failed, "failed")
        if total != len(results):
            raise ValueError("total must match result count")
        actual_passed = sum(1 for result in results if result.passed)
        if passed != actual_passed:
            raise ValueError("passed must match result outcomes")
        if failed != total - passed:
            raise ValueError("failed must equal total - passed")

        expected_fields, expected_reasons, expected_categories = _failure_groupings(
            results
        )
        failure_fields = _freeze_count_mapping(self.failure_fields, "failure_fields")
        failure_reasons = _freeze_count_mapping(
            self.failure_reasons,
            "failure_reasons",
        )
        failure_categories = _freeze_count_mapping(
            self.failure_categories,
            "failure_categories",
        )
        if failure_fields != expected_fields:
            raise ValueError("failure_fields do not match failed results")
        if failure_reasons != expected_reasons:
            raise ValueError("failure_reasons do not match failed results")
        if failure_categories != expected_categories:
            raise ValueError("failure_categories do not match failed results")
        object.__setattr__(self, "failure_fields", failure_fields)
        object.__setattr__(self, "failure_reasons", failure_reasons)
        object.__setattr__(self, "failure_categories", failure_categories)


def evaluate_local_worker_scenario_result(
    expectation: LocalWorkerScenarioExpectation,
    record: LocalWorkerTurnHarnessRecord,
) -> LocalWorkerScenarioResult:
    if not isinstance(expectation, LocalWorkerScenarioExpectation):
        raise TypeError("expectation must be LocalWorkerScenarioExpectation")
    if not isinstance(record, LocalWorkerTurnHarnessRecord):
        raise TypeError("record must be LocalWorkerTurnHarnessRecord")

    checks = [_check("status", expectation.expected_status, record.status)]
    if expectation.expected_status == "completed":
        checks.append(
            _check(
                "disposition",
                expectation.expected_disposition,
                _record_disposition(record),
            )
        )
        if expectation.expected_attempt_valid is not None:
            checks.append(
                _check(
                    "attempt.valid",
                    expectation.expected_attempt_valid,
                    _record_attempt_valid(record),
                )
            )
        if expectation.expected_attempt_failure is not None:
            checks.append(
                _check(
                    "attempt.failure",
                    expectation.expected_attempt_failure,
                    _record_attempt_failure(record),
                )
            )
        if expectation.expected_action_id is not None:
            checks.append(
                _check(
                    "attempt.action_id",
                    expectation.expected_action_id,
                    _record_attempt_action_id(record),
                )
            )
        if expectation.expected_response_kind is not None:
            checks.append(
                _check(
                    "attempt.response_kind",
                    expectation.expected_response_kind,
                    _record_attempt_response_kind(record),
                )
            )
    else:
        if expectation.expected_harness_failure is not None:
            checks.append(
                _check(
                    "harness.failure",
                    expectation.expected_harness_failure,
                    record.failure,
                )
            )

    if expectation.expected_reason is not None:
        checks.append(_check("reason", expectation.expected_reason, record.reason))
    if expectation.expected_workflow_id is not None:
        checks.append(
            _check(
                "context.workflow_id",
                expectation.expected_workflow_id,
                record.context_workflow_id,
            )
        )
    if expectation.expected_contract_fingerprint is not None:
        checks.append(
            _check(
                "context.contract_fingerprint",
                expectation.expected_contract_fingerprint,
                record.context_contract_fingerprint,
            )
        )

    passed = all(check.passed for check in checks)
    return LocalWorkerScenarioResult(
        scenario_id=expectation.scenario_id,
        category=expectation.category,
        context_workflow_id=record.context_workflow_id,
        context_contract_fingerprint=record.context_contract_fingerprint,
        passed=passed,
        checks=tuple(checks),
        reason=(
            "passed"
            if passed
            else f"failed:{_first_failed_check(tuple(checks)).field}"
        ),
    )


def build_local_worker_scenario_report(
    results: tuple[LocalWorkerScenarioResult, ...] | list[LocalWorkerScenarioResult],
) -> LocalWorkerScenarioReport:
    results_tuple = _freeze_instance_tuple(
        results,
        LocalWorkerScenarioResult,
        "results",
    )
    if not results_tuple:
        raise ValueError("results must not be empty")
    _reject_duplicate_scenario_ids(results_tuple)
    passed = sum(1 for result in results_tuple if result.passed)
    failed = len(results_tuple) - passed
    failure_fields, failure_reasons, failure_categories = _failure_groupings(
        results_tuple
    )
    return LocalWorkerScenarioReport(
        total=len(results_tuple),
        passed=passed,
        failed=failed,
        results=results_tuple,
        failure_fields=failure_fields,
        failure_reasons=failure_reasons,
        failure_categories=failure_categories,
    )


def _validate_expectation_plane(
    expectation: LocalWorkerScenarioExpectation,
    status: str,
) -> None:
    if status == "completed":
        if expectation.expected_disposition is None:
            raise ValueError("completed expectations require expected_disposition")
        if expectation.expected_harness_failure is not None:
            raise ValueError(
                "completed expectations must not set expected_harness_failure"
            )
        return

    if expectation.expected_harness_failure is None:
        raise ValueError(f"{status} expectations require expected_harness_failure")

    forbidden = {
        "expected_disposition": expectation.expected_disposition,
        "expected_attempt_valid": expectation.expected_attempt_valid,
        "expected_attempt_failure": expectation.expected_attempt_failure,
        "expected_action_id": expectation.expected_action_id,
        "expected_response_kind": expectation.expected_response_kind,
    }
    for field_name, value in forbidden.items():
        if value is not None:
            raise ValueError(f"{status} expectations must not set {field_name}")


def _check(
    field: str,
    expected: ScenarioScalar,
    actual: ScenarioScalar,
) -> LocalWorkerScenarioCheck:
    passed = expected == actual
    return LocalWorkerScenarioCheck(
        field=field,
        expected=expected,
        actual=actual,
        passed=passed,
        reason=f"{'matched' if passed else 'mismatched'}:{field}",
    )


def _record_disposition(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.disposition


def _record_attempt_valid(record: LocalWorkerTurnHarnessRecord) -> bool | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.valid


def _record_attempt_failure(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.failure


def _record_attempt_action_id(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.action_id


def _record_attempt_response_kind(record: LocalWorkerTurnHarnessRecord) -> str | None:
    if record.status != "completed" or record.disposition is None:
        return None
    return record.disposition.attempt.response_kind


def _failure_groupings(
    results: tuple[LocalWorkerScenarioResult, ...],
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    failure_fields: dict[str, int] = {}
    failure_reasons: dict[str, int] = {}
    failure_categories: dict[str, int] = {}
    for result in results:
        if result.passed:
            continue
        first_field = _first_failed_check(result.checks).field
        _increment(failure_fields, first_field)
        _increment(failure_reasons, result.reason)
        _increment(failure_categories, result.category)
    return failure_fields, failure_reasons, failure_categories


def _increment(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _first_failed_check(
    checks: tuple[LocalWorkerScenarioCheck, ...],
) -> LocalWorkerScenarioCheck:
    for check in checks:
        if not check.passed:
            return check
    raise ValueError("checks contain no failed check")


def _reject_duplicate_scenario_ids(
    results: tuple[LocalWorkerScenarioResult, ...],
) -> None:
    seen: set[str] = set()
    for result in results:
        if result.scenario_id in seen:
            raise ValueError(f"duplicate scenario_id: {result.scenario_id!r}")
        seen.add(result.scenario_id)


def _freeze_instance_tuple(
    value: tuple[object, ...] | list[object],
    expected_type: type,
    field_name: str,
) -> tuple[object, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    for item in value:
        if not isinstance(item, expected_type):
            raise TypeError(f"{field_name} items must be {expected_type.__name__}")
    return tuple(value)


def _freeze_count_mapping(
    value: Mapping[str, int],
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied: dict[str, int] = {}
    for key, item in value.items():
        _require_non_empty_str(key, f"{field_name} key")
        copied[key] = _require_positive_int(item, f"{field_name}.{key}")
    return MappingProxyType(copied)


def _require_choice(
    value: object,
    allowed: frozenset[str],
    field_name: str,
) -> str:
    result = _require_str(value, field_name)
    if result not in allowed:
        raise ValueError(f"{field_name} has unknown value: {result!r}")
    return result


def _require_optional_choice(
    value: object,
    allowed: frozenset[str],
    field_name: str,
) -> str | None:
    if value is None:
        return None
    return _require_choice(value, allowed, field_name)


def _require_scenario_scalar(value: object, field_name: str) -> ScenarioScalar:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value
    raise TypeError(f"{field_name} must be str, bool, or None")


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _require_optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    return _require_bool(value, field_name)


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_optional_non_empty_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_str(value, field_name)


def _require_non_empty_str(value: object, field_name: str) -> str:
    result = _require_str(value, field_name)
    if result == "":
        raise ValueError(f"{field_name} must not be empty")
    return result


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value
```

- [ ] **Step 2: Run targeted tests and verify GREEN**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_scenario_evaluation.py -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 3: Commit implementation**

Run:

```powershell
git add mcp_server\src\rook\agent\local_worker_scenario_evaluation.py mcp_server\tests\test_local_worker_scenario_evaluation.py
git commit -m "feat(lm5f): add local worker scenario evaluation"
```

Expected result: commit succeeds and stages only the LM5F production/test files.

---

## Task 3: Run Verification Gates

**Files:**

- Verify: `mcp_server/src/rook/agent/local_worker_scenario_evaluation.py`
- Verify: `mcp_server/tests/test_local_worker_scenario_evaluation.py`

- [ ] **Step 1: Run targeted LM5F tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_local_worker_scenario_evaluation.py -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 2: Run nearby LM5 tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Expected output:

```text
all tests pass
```

- [ ] **Step 3: Run focused PlanGraph/local-worker gate**

Run:

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' | Sort-Object Name | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  -q
```

Expected output:

```text
all tests pass
```

---

## Task 4: Run Boundary And Scope Checks

**Files:**

- Verify: `mcp_server/src/rook/agent/local_worker_scenario_evaluation.py`
- Verify no diff:
  - `mcp_server/src/rook/agent/local_worker_turn_context.py`
  - `mcp_server/src/rook/agent/local_worker_turn_response.py`
  - `mcp_server/src/rook/agent/local_worker_turn_disposition.py`
  - `mcp_server/src/rook/agent/local_worker_turn_harness.py`
  - `mcp_server/tests/test_local_worker_turn_scenarios.py`

- [ ] **Step 1: Check whitespace/diff hygiene**

Run:

```powershell
git diff --check main..HEAD
```

Expected output: no output.

- [ ] **Step 2: Check production scope**

Run:

```powershell
git diff --name-only main..HEAD -- mcp_server/src
```

Expected output:

```text
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
```

- [ ] **Step 3: Check test scope**

Run:

```powershell
git diff --name-only main..HEAD -- mcp_server/tests
```

Expected output:

```text
mcp_server/tests/test_local_worker_scenario_evaluation.py
```

- [ ] **Step 4: Check LM5A-E files stayed untouched**

Run:

```powershell
git diff --name-only main..HEAD -- `
  mcp_server/src/rook/agent/local_worker_turn_context.py `
  mcp_server/src/rook/agent/local_worker_turn_response.py `
  mcp_server/src/rook/agent/local_worker_turn_disposition.py `
  mcp_server/src/rook/agent/local_worker_turn_harness.py `
  mcp_server/tests/test_local_worker_turn_scenarios.py
```

Expected output: no output.

- [ ] **Step 5: Check guarded repo areas stayed untouched**

Run:

```powershell
git diff --name-only main..HEAD -- src/Rook/base_agent.py knowledge/gh/operations_knowledge.json src/Rook src/RookNative
```

Expected output: no output.

- [ ] **Step 6: Run quick production boundary scan**

Run:

```powershell
rg -n "LocalWorkerTurnContext|WorkerAllowedAction|run_local_worker_turn|LocalWorkerTurnWorker|compile_workflow_contract|snapshot_workflow_contract|load_workflow_contract_payload|run_current_step_stream|run_current_mapped_step|execute_mapped_step|map_accepted_proposal_to_step|revalidate_proposal|propose_next_node|CurrentStepRecord|EnvelopeSupplyRecord|EnvelopeSupplyResult|PlanGraph|CompiledWorkflowScaffold|CatalogCurrentStepProvider|WorkflowProvenanceEnvelopeSource|RookAgent|base_agent|dispatcher|server|prompt|litellm|OpenAI|Path|open\\(|import json|json\\.loads|json\\.dumps|yaml|time|datetime|sleep|uuid|hashlib|retry|fallback|critic|oversight|to_json|to_dict|write_report|read_report" mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
```

Expected output: no output.

The AST guard in `test_local_worker_scenario_evaluation.py` is the primary boundary check. This `rg` scan is a quick human-readable guard and intentionally avoids raw substring bans like `model`.

- [ ] **Step 7: Check final worktree status**

Run:

```powershell
git status --short --branch
```

Expected output may include only the known unrelated untracked directory:

```text
?? .claude/worktrees/
```

No LM5F files should be unstaged or uncommitted.

---

## Self-Review Checklist

- [ ] Public surface exports only `LocalWorkerScenarioExpectation`, `LocalWorkerScenarioCheck`, `LocalWorkerScenarioResult`, `LocalWorkerScenarioReport`, `evaluate_local_worker_scenario_result`, and `build_local_worker_scenario_report`.
- [ ] Production imports no LM5A context, worker runner, LM4 compiler, stream, provider, provenance, model, prompt, dispatcher, file, JSON, YAML, time, uuid, or hashing surfaces.
- [ ] `LocalWorkerScenarioExpectation` validates `expected_status`, `expected_disposition`, `expected_attempt_failure`, and `expected_response_kind` against LM5B/C/D literal vocabularies.
- [ ] `LocalWorkerScenarioExpectation` treats `None` as "not checked" and does not add an "expect actual None" sentinel.
- [ ] Plane separation rejects harness-failure fields on completed expectations and attempt/disposition fields on non-completed expectations.
- [ ] `evaluate_local_worker_scenario_result(...)` evaluates only existing `LocalWorkerTurnHarnessRecord` values and never calls workers.
- [ ] Wrong-plane actual outcomes return failed checks, not exceptions.
- [ ] Completed blocked responses use `expected_attempt_failure`; harness failure statuses use `expected_harness_failure`.
- [ ] Evaluation checks only compact receipt fields: status, harness failure, reason, disposition, attempt validity/failure/action id/response kind, workflow id, and contract fingerprint.
- [ ] Evaluation never inspects action input, observation message, clarification question, refusal reason, knowledge packets, or response payload data.
- [ ] `LocalWorkerScenarioResult` always carries actual workflow anchors from the harness record.
- [ ] Per-field checks use scalar values only and reasons exactly `matched:<field>` or `mismatched:<field>`.
- [ ] Result reason is `passed` or `failed:<first_failed_field>`.
- [ ] Report rejects empty result sequences and duplicate scenario ids.
- [ ] Report groups failures by first failed field, result reason, and result category.
- [ ] Report grouping maps are immutable `MappingProxyType` values and cannot be changed by caller mutation.
- [ ] No serialization, report writer, report loader, report fingerprint, timestamp, run id, model id, scenario runner, batch evaluator, retry/fallback/critic/oversight field, or action authorization was added.
