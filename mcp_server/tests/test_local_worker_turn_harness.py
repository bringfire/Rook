from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path

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
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
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

from rook.agent.local_worker_turn_harness import (
    LocalWorkerTurnHarnessRecord,
    run_local_worker_turn,
)


def _minimal_context(
    *,
    action_ids: tuple[str, ...] = ("draft_bind_params",),
) -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="lm5d_worker_harness",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="d" * 64,
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
        workflow_id="lm5d_worker_harness",
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
                    "name": "LM5DLocalWorkerHarness",
                    "x": 350,
                    "y": 1240,
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
        metadata={"trace": {"slice": "LM5D"}},
    )


def _action_response(action_id: str = "draft_bind_params") -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=action_id,
            rationale="Draft repair params.",
            input={"code": "A = 42.0;"},
        )
    )


def _clarification_response() -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerClarificationRequest("Which component should be repaired?")
    )


def _refusal_response() -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerRefusal("insufficient_context", "No repair target was provided.")
    )


def _observation_response() -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(WorkerObservation("No action requested."))


def _disposition_for(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnDispositionRecord:
    return dispose_local_worker_turn_response(context, response)


def _completed_record(
    context: LocalWorkerTurnContext,
    response: LocalWorkerTurnResponse,
) -> LocalWorkerTurnHarnessRecord:
    disposition = _disposition_for(context, response)
    return LocalWorkerTurnHarnessRecord(
        status="completed",
        response=response,
        disposition=disposition,
        failure=None,
        reason=f"completed:{disposition.disposition}",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def _invalid_response_record(
    context: LocalWorkerTurnContext,
    type_name: str = "dict",
) -> LocalWorkerTurnHarnessRecord:
    return LocalWorkerTurnHarnessRecord(
        status="invalid_response",
        response=None,
        disposition=None,
        failure="response_type_invalid",
        reason=f"response_type_invalid:{type_name}",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def _worker_error_record(
    context: LocalWorkerTurnContext,
    exception_name: str = "ValueError",
) -> LocalWorkerTurnHarnessRecord:
    return LocalWorkerTurnHarnessRecord(
        status="worker_error",
        response=None,
        disposition=None,
        failure="worker_exception",
        reason=f"worker_exception:{exception_name}",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_harness as module

    assert module.__all__ == (
        "HarnessStatus",
        "LocalWorkerTurnWorker",
        "LocalWorkerTurnHarnessRecord",
        "run_local_worker_turn",
    )
    assert "classify_worker_result" not in module.__all__
    assert "record_worker_exception" not in module.__all__


def test_harness_record_is_frozen_compact_dataclass() -> None:
    context = _minimal_context()
    record = _completed_record(context, _action_response())

    assert is_dataclass(LocalWorkerTurnHarnessRecord)
    assert LocalWorkerTurnHarnessRecord.__dataclass_params__.frozen is True
    assert tuple(field.name for field in fields(LocalWorkerTurnHarnessRecord)) == (
        "status",
        "response",
        "disposition",
        "failure",
        "reason",
        "context_workflow_id",
        "context_contract_fingerprint",
    )

    with pytest.raises(FrozenInstanceError):
        record.reason = "changed"


@pytest.mark.parametrize(
    "record",
    [
        _completed_record(_minimal_context(), _action_response()),
        _completed_record(_minimal_context(), _action_response("invented")),
        _invalid_response_record(_minimal_context()),
        _worker_error_record(_minimal_context()),
    ],
)
def test_direct_construction_accepts_coherent_records(
    record: LocalWorkerTurnHarnessRecord,
) -> None:
    assert record.context_workflow_id == "lm5d_worker_harness"
    assert record.context_contract_fingerprint == "d" * 64


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("status", 123),
        ("response", object()),
        ("disposition", object()),
        ("failure", 123),
        ("reason", 123),
        ("context_workflow_id", 123),
        ("context_contract_fingerprint", 123),
    ],
)
def test_direct_construction_rejects_wrong_field_types(
    field_name: str,
    bad_value: object,
) -> None:
    context = _minimal_context()
    kwargs = {
        "status": "invalid_response",
        "response": None,
        "disposition": None,
        "failure": "response_type_invalid",
        "reason": "response_type_invalid:dict",
        "context_workflow_id": context.workflow.workflow_id,
        "context_contract_fingerprint": context.workflow.contract_fingerprint,
    }
    kwargs[field_name] = bad_value

    with pytest.raises(TypeError):
        LocalWorkerTurnHarnessRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "pending"},
        {"reason": ""},
        {"context_workflow_id": ""},
        {"context_contract_fingerprint": ""},
        {"response": None},
        {"disposition": None},
        {"failure": "worker_exception"},
        {"reason": "completed:blocked"},
        {"context_workflow_id": "other"},
        {"context_contract_fingerprint": "other"},
    ],
)
def test_completed_record_rejects_incoherence(overrides: dict[str, object]) -> None:
    context = _minimal_context()
    response = _action_response()
    disposition = _disposition_for(context, response)
    kwargs = {
        "status": "completed",
        "response": response,
        "disposition": disposition,
        "failure": None,
        "reason": f"completed:{disposition.disposition}",
        "context_workflow_id": context.workflow.workflow_id,
        "context_contract_fingerprint": context.workflow.contract_fingerprint,
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnHarnessRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"response": _action_response()},
        {"disposition": _disposition_for(_minimal_context(), _action_response())},
        {"failure": None},
        {"failure": "worker_exception"},
        {"reason": "response_type_invalid:"},
        {"reason": "response_type_invalid:dict:extra"},
        {"reason": "worker_exception:ValueError"},
    ],
)
def test_invalid_response_record_rejects_incoherence(
    overrides: dict[str, object],
) -> None:
    context = _minimal_context()
    kwargs = {
        "status": "invalid_response",
        "response": None,
        "disposition": None,
        "failure": "response_type_invalid",
        "reason": "response_type_invalid:dict",
        "context_workflow_id": context.workflow.workflow_id,
        "context_contract_fingerprint": context.workflow.contract_fingerprint,
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnHarnessRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"response": _action_response()},
        {"disposition": _disposition_for(_minimal_context(), _action_response())},
        {"failure": None},
        {"failure": "response_type_invalid"},
        {"reason": "worker_exception:"},
        {"reason": "worker_exception:ValueError:extra"},
        {"reason": "response_type_invalid:dict"},
    ],
)
def test_worker_error_record_rejects_incoherence(
    overrides: dict[str, object],
) -> None:
    context = _minimal_context()
    kwargs = {
        "status": "worker_error",
        "response": None,
        "disposition": None,
        "failure": "worker_exception",
        "reason": "worker_exception:ValueError",
        "context_workflow_id": context.workflow.workflow_id,
        "context_contract_fingerprint": context.workflow.contract_fingerprint,
    }
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnHarnessRecord(**kwargs)


def test_bad_harness_api_inputs_raise_type_error() -> None:
    context = _minimal_context()

    with pytest.raises(TypeError):
        run_local_worker_turn(object(), lambda received: _action_response())

    with pytest.raises(TypeError):
        run_local_worker_turn(context, object())


def test_worker_is_called_once_with_exact_context_and_response_is_preserved() -> None:
    context = _minimal_context()
    response = _action_response()
    calls: list[LocalWorkerTurnContext] = []

    def worker(received_context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
        calls.append(received_context)
        return response

    record = run_local_worker_turn(context, worker)

    assert calls == [context]
    assert record.status == "completed"
    assert record.response is response
    assert record.disposition is not None
    assert record.disposition.disposition == "candidate_action_request"
    assert record.reason == "completed:candidate_action_request"


def test_exact_lm5c_disposition_object_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rook.agent.local_worker_turn_harness as module

    context = _minimal_context()
    response = _observation_response()
    fake_attempt = LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="observation",
        failure=None,
        reason="valid_observation",
        action_id=None,
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )
    fake_disposition = LocalWorkerTurnDispositionRecord(
        disposition="observation_recorded",
        attempt=fake_attempt,
        response_kind="observation",
        action_id=None,
        reason="observation_recorded",
    )
    received: list[tuple[LocalWorkerTurnContext, LocalWorkerTurnResponse]] = []

    def fake_dispose(
        received_context: LocalWorkerTurnContext,
        received_response: LocalWorkerTurnResponse,
    ) -> LocalWorkerTurnDispositionRecord:
        received.append((received_context, received_response))
        return fake_disposition

    monkeypatch.setattr(module, "dispose_local_worker_turn_response", fake_dispose)

    record = module.run_local_worker_turn(context, lambda received_context: response)

    assert received == [(context, response)]
    assert record.response is response
    assert record.disposition is fake_disposition
    assert record.reason == "completed:observation_recorded"


def test_unknown_action_returns_completed_blocked() -> None:
    context = _minimal_context(action_ids=("draft_bind_params",))
    response = _action_response("invented")

    record = run_local_worker_turn(context, lambda received_context: response)

    assert record.status == "completed"
    assert record.response is response
    assert record.disposition is not None
    assert record.disposition.disposition == "blocked"
    assert record.disposition.attempt.failure == "unknown_action_id"
    assert record.reason == "completed:blocked"


@pytest.mark.parametrize(
    ("response", "disposition", "reason"),
    [
        (_clarification_response(), "clarification_needed", "completed:clarification_needed"),
        (_refusal_response(), "refusal_recorded", "completed:refusal_recorded"),
        (_observation_response(), "observation_recorded", "completed:observation_recorded"),
    ],
)
def test_non_action_responses_complete_with_matching_dispositions(
    response: LocalWorkerTurnResponse,
    disposition: str,
    reason: str,
) -> None:
    context = _minimal_context()

    record = run_local_worker_turn(context, lambda received_context: response)

    assert record.status == "completed"
    assert record.response is response
    assert record.disposition is not None
    assert record.disposition.disposition == disposition
    assert record.reason == reason


@pytest.mark.parametrize(
    ("raw_output", "type_name"),
    [
        ({"not": "a response"}, "dict"),
        (None, "NoneType"),
        (object(), "object"),
    ],
)
def test_non_response_returns_invalid_response_without_storing_raw_output(
    raw_output: object,
    type_name: str,
) -> None:
    context = _minimal_context()

    record = run_local_worker_turn(context, lambda received_context: raw_output)

    assert record.status == "invalid_response"
    assert record.response is None
    assert record.disposition is None
    assert record.failure == "response_type_invalid"
    assert record.reason == f"response_type_invalid:{type_name}"
    assert raw_output not in (record.response, record.disposition, record.failure, record.reason)


def test_worker_exception_is_captured_without_message_or_traceback() -> None:
    context = _minimal_context()

    def worker(received_context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
        raise ValueError("secret message must not leak")

    record = run_local_worker_turn(context, worker)

    assert record.status == "worker_error"
    assert record.response is None
    assert record.disposition is None
    assert record.failure == "worker_exception"
    assert record.reason == "worker_exception:ValueError"
    assert "secret message" not in record.reason
    assert "Traceback" not in record.reason


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit])
def test_base_exceptions_propagate(exception: type[BaseException]) -> None:
    context = _minimal_context()

    def worker(received_context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
        raise exception()

    with pytest.raises(exception):
        run_local_worker_turn(context, worker)


def test_context_anchors_are_read_before_worker_invocation() -> None:
    context = _minimal_context()

    def worker(received_context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
        object.__setattr__(
            received_context.workflow,
            "workflow_id",
            "mutated_after_anchor_read",
        )
        object.__setattr__(
            received_context.workflow,
            "contract_fingerprint",
            "e" * 64,
        )
        raise RuntimeError("worker failed after mutation")

    record = run_local_worker_turn(context, worker)

    assert record.status == "worker_error"
    assert record.context_workflow_id == "lm5d_worker_harness"
    assert record.context_contract_fingerprint == "d" * 64


def test_lm5c_error_after_typed_response_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rook.agent.local_worker_turn_harness as module

    context = _minimal_context()
    response = _observation_response()

    def raising_dispose(
        received_context: LocalWorkerTurnContext,
        received_response: LocalWorkerTurnResponse,
    ) -> LocalWorkerTurnDispositionRecord:
        raise ValueError("lm5c defensive failure")

    monkeypatch.setattr(module, "dispose_local_worker_turn_response", raising_dispose)

    with pytest.raises(ValueError, match="lm5c defensive failure"):
        module.run_local_worker_turn(context, lambda received_context: response)


def test_real_lm5a_lm5b_lm5c_lm5d_chain_runs_allowed_action() -> None:
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

    record = run_local_worker_turn(context, lambda received_context: response)

    assert record.status == "completed"
    assert record.response is response
    assert record.disposition is not None
    assert record.disposition.disposition == "candidate_action_request"
    assert record.disposition.attempt.context_workflow_id == context.workflow.workflow_id
    assert (
        record.disposition.attempt.context_contract_fingerprint
        == context.workflow.contract_fingerprint
    )
    assert record.context_workflow_id == context.workflow.workflow_id
    assert record.context_contract_fingerprint == context.workflow.contract_fingerprint


def test_local_worker_harness_module_boundary_is_one_turn_only() -> None:
    import rook.agent.local_worker_turn_harness as module

    source = Path(module.__file__).read_text(encoding="utf-8")
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
        "dataclasses",
        "typing",
        "rook.agent.local_worker_turn_context",
        "rook.agent.local_worker_turn_response",
        "rook.agent.local_worker_turn_disposition",
    }

    banned_names = {
        "Any",
        "Mapping",
        "MappingProxyType",
        "math",
        "json",
        "yaml",
        "Path",
        "open",
        "loads",
        "dumps",
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
        "WorkerAllowedAction",
        "RookAgent",
        "base_agent",
        "dispatcher",
        "server",
        "model",
        "litellm",
        "OpenAI",
        "asyncio",
        "threading",
        "time",
        "datetime",
        "sleep",
        "retry",
        "fallback",
        "critic",
        "oversight",
        "_freeze_json_value",
        "_freeze_json_mapping",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps", "sleep"} & called_names)
