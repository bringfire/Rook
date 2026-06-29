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

from rook.agent.local_worker_turn_disposition import (
    LocalWorkerTurnDispositionRecord,
    dispose_local_worker_turn_response,
)


def _minimal_context(
    *,
    action_ids: tuple[str, ...] = ("draft_bind_params",),
) -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="lm5c_worker_disposition",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="a" * 64,
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
        workflow_id="lm5c_worker_disposition",
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
                    "name": "LM5CLocalWorkerDisposition",
                    "x": 350,
                    "y": 1200,
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
        metadata={"trace": {"slice": "LM5C"}},
    )


def _attempt(
    *,
    valid: bool,
    response_kind: str | None,
    failure: str | None,
    reason: str,
    action_id: str | None,
) -> LocalWorkerTurnAttemptRecord:
    return LocalWorkerTurnAttemptRecord(
        valid=valid,
        response_kind=response_kind,
        failure=failure,
        reason=reason,
        action_id=action_id,
        context_workflow_id="lm5c_worker_disposition",
        context_contract_fingerprint="a" * 64,
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


def _valid_non_action_attempt(response_kind: str) -> LocalWorkerTurnAttemptRecord:
    reason_by_kind = {
        "clarification_request": "valid_clarification_request",
        "refusal": "valid_refusal",
        "observation": "valid_observation",
    }
    return _attempt(
        valid=True,
        response_kind=response_kind,
        failure=None,
        reason=reason_by_kind[response_kind],
        action_id=None,
    )


def _unknown_action_attempt(action_id: str = "invented") -> LocalWorkerTurnAttemptRecord:
    return _attempt(
        valid=False,
        response_kind="action_request",
        failure="unknown_action_id",
        reason=f"unknown_action_id:{action_id}",
        action_id=action_id,
    )


def _record_kwargs(
    attempt: LocalWorkerTurnAttemptRecord,
) -> dict[str, object]:
    if attempt.valid is False:
        return {
            "disposition": "blocked",
            "attempt": attempt,
            "response_kind": attempt.response_kind,
            "action_id": attempt.action_id,
            "reason": f"blocked:{attempt.reason}",
        }
    if attempt.response_kind == "action_request":
        return {
            "disposition": "candidate_action_request",
            "attempt": attempt,
            "response_kind": attempt.response_kind,
            "action_id": attempt.action_id,
            "reason": f"candidate_action_request:{attempt.action_id}",
        }
    if attempt.response_kind == "clarification_request":
        return {
            "disposition": "clarification_needed",
            "attempt": attempt,
            "response_kind": attempt.response_kind,
            "action_id": None,
            "reason": "clarification_needed",
        }
    if attempt.response_kind == "refusal":
        return {
            "disposition": "refusal_recorded",
            "attempt": attempt,
            "response_kind": attempt.response_kind,
            "action_id": None,
            "reason": "refusal_recorded",
        }
    if attempt.response_kind == "observation":
        return {
            "disposition": "observation_recorded",
            "attempt": attempt,
            "response_kind": attempt.response_kind,
            "action_id": None,
            "reason": "observation_recorded",
        }
    raise AssertionError(f"unsupported attempt fixture: {attempt!r}")


@pytest.mark.parametrize(
    ("payload", "disposition", "kind", "action_id", "reason"),
    [
        (
            WorkerActionRequest(
                action_id="draft_bind_params",
                rationale="Draft repair params.",
                input={"code": "A = 42.0;"},
            ),
            "candidate_action_request",
            "action_request",
            "draft_bind_params",
            "candidate_action_request:draft_bind_params",
        ),
        (
            WorkerClarificationRequest("Which component should be repaired?"),
            "clarification_needed",
            "clarification_request",
            None,
            "clarification_needed",
        ),
        (
            WorkerRefusal("out_of_scope", "No allowed action fits."),
            "refusal_recorded",
            "refusal",
            None,
            "refusal_recorded",
        ),
        (
            WorkerObservation("No action requested."),
            "observation_recorded",
            "observation",
            None,
            "observation_recorded",
        ),
    ],
)
def test_valid_responses_map_to_dispositions(
    payload: object,
    disposition: str,
    kind: str,
    action_id: str | None,
    reason: str,
) -> None:
    context = _minimal_context()
    response = LocalWorkerTurnResponse(payload)

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == disposition
    assert record.attempt.valid is True
    assert record.attempt.response_kind == kind
    assert record.response_kind == kind
    assert record.action_id == action_id
    assert record.reason == reason


def test_unknown_action_flows_through_lm5b_and_maps_to_blocked() -> None:
    context = _minimal_context(action_ids=("draft_bind_params",))
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id="invented",
            rationale="Try an unavailable action.",
            input={},
        )
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.attempt.valid is False
    assert record.attempt.failure == "unknown_action_id"
    assert record.attempt.reason == "unknown_action_id:invented"
    assert record.disposition == "blocked"
    assert record.response_kind == "action_request"
    assert record.action_id == "invented"
    assert record.reason == "blocked:unknown_action_id:invented"


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_disposition as module

    assert module.__all__ == (
        "WorkerResponseDisposition",
        "LocalWorkerTurnDispositionRecord",
        "dispose_local_worker_turn_response",
    )
    assert "_disposition_from_attempt" not in module.__all__


def test_disposition_record_is_frozen_compact_dataclass() -> None:
    assert is_dataclass(LocalWorkerTurnDispositionRecord)
    assert LocalWorkerTurnDispositionRecord.__dataclass_params__.frozen is True
    assert tuple(field.name for field in fields(LocalWorkerTurnDispositionRecord)) == (
        "disposition",
        "attempt",
        "response_kind",
        "action_id",
        "reason",
    )

    record = LocalWorkerTurnDispositionRecord(**_record_kwargs(_valid_action_attempt()))
    with pytest.raises(FrozenInstanceError):
        record.reason = "changed"


@pytest.mark.parametrize(
    "attempt",
    [
        _valid_action_attempt(),
        _valid_non_action_attempt("clarification_request"),
        _valid_non_action_attempt("refusal"),
        _valid_non_action_attempt("observation"),
        _unknown_action_attempt(),
    ],
)
def test_direct_construction_accepts_coherent_records(
    attempt: LocalWorkerTurnAttemptRecord,
) -> None:
    record = LocalWorkerTurnDispositionRecord(**_record_kwargs(attempt))

    assert record.attempt is attempt
    assert record.response_kind == attempt.response_kind
    assert record.action_id == attempt.action_id


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("attempt", object()),
        ("disposition", 123),
        ("response_kind", 123),
        ("action_id", 123),
        ("reason", 123),
    ],
)
def test_direct_construction_rejects_wrong_scalar_types(
    field_name: str,
    bad_value: object,
) -> None:
    kwargs = _record_kwargs(_valid_non_action_attempt("observation"))
    kwargs[field_name] = bad_value

    with pytest.raises(TypeError):
        LocalWorkerTurnDispositionRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"reason": ""},
        {"disposition": "invalid_response"},
        {"response_kind": "refusal"},
        {"action_id": "not-none"},
        {"disposition": "blocked"},
        {"reason": "wrong_reason"},
    ],
)
def test_valid_observation_record_rejects_incoherence(
    overrides: dict[str, object],
) -> None:
    kwargs = _record_kwargs(_valid_non_action_attempt("observation"))
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"disposition": "candidate_action_request"},
        {"reason": "blocked:other"},
        {"response_kind": None},
        {"action_id": "other"},
    ],
)
def test_blocked_record_rejects_incoherence(overrides: dict[str, object]) -> None:
    kwargs = _record_kwargs(_unknown_action_attempt())
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)


@pytest.mark.parametrize(
    "overrides",
    [
        {"disposition": "observation_recorded"},
        {"action_id": None},
        {"reason": "candidate_action_request:other"},
    ],
)
def test_valid_action_record_rejects_incoherence(
    overrides: dict[str, object],
) -> None:
    kwargs = _record_kwargs(_valid_action_attempt())
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(**kwargs)


def test_valid_action_record_rejects_missing_attempt_action_id_after_bypass() -> None:
    attempt = _valid_action_attempt()
    object.__setattr__(attempt, "action_id", None)

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(
            disposition="candidate_action_request",
            attempt=attempt,
            response_kind="action_request",
            action_id=None,
            reason="candidate_action_request:None",
        )


@pytest.mark.parametrize(
    ("attempt", "disposition", "reason"),
    [
        (
            _valid_non_action_attempt("clarification_request"),
            "candidate_action_request",
            "clarification_needed",
        ),
        (
            _valid_non_action_attempt("clarification_request"),
            "clarification_needed",
            "refusal_recorded",
        ),
        (
            _valid_non_action_attempt("refusal"),
            "clarification_needed",
            "refusal_recorded",
        ),
        (
            _valid_non_action_attempt("observation"),
            "refusal_recorded",
            "observation_recorded",
        ),
    ],
)
def test_valid_non_action_records_reject_wrong_disposition_or_reason(
    attempt: LocalWorkerTurnAttemptRecord,
    disposition: str,
    reason: str,
) -> None:
    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(
            disposition=disposition,
            attempt=attempt,
            response_kind=attempt.response_kind,
            action_id=None,
            reason=reason,
        )


def test_valid_non_action_record_rejects_attempt_action_id_after_bypass() -> None:
    attempt = _valid_non_action_attempt("refusal")
    object.__setattr__(attempt, "action_id", "not-none")

    with pytest.raises(ValueError):
        LocalWorkerTurnDispositionRecord(
            disposition="refusal_recorded",
            attempt=attempt,
            response_kind="refusal",
            action_id="not-none",
            reason="refusal_recorded",
        )


def test_private_disposition_helper_rejects_wrong_attempt_type() -> None:
    import rook.agent.local_worker_turn_disposition as module

    with pytest.raises(TypeError):
        module._disposition_from_attempt(object())


def test_monkeypatched_validator_receives_exact_inputs_and_nests_exact_attempt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rook.agent.local_worker_turn_disposition as module

    context = _minimal_context()
    response = LocalWorkerTurnResponse(WorkerObservation("Observed."))
    fake_attempt = _valid_non_action_attempt("observation")
    received: list[tuple[LocalWorkerTurnContext, LocalWorkerTurnResponse]] = []

    def fake_validator(
        received_context: LocalWorkerTurnContext,
        received_response: LocalWorkerTurnResponse,
    ) -> LocalWorkerTurnAttemptRecord:
        received.append((received_context, received_response))
        return fake_attempt

    monkeypatch.setattr(module, "validate_local_worker_turn_response", fake_validator)

    record = module.dispose_local_worker_turn_response(context, response)

    assert received == [(context, response)]
    assert record.attempt is fake_attempt
    assert record.disposition == "observation_recorded"


def test_malformed_api_inputs_propagate_lm5b_type_error() -> None:
    context = _minimal_context()
    response = LocalWorkerTurnResponse(WorkerObservation("Observed."))

    with pytest.raises(TypeError):
        dispose_local_worker_turn_response(object(), response)

    with pytest.raises(TypeError):
        dispose_local_worker_turn_response(context, object())


def test_lm5b_type_error_propagates_from_dispose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import rook.agent.local_worker_turn_disposition as module

    def raising_validator(
        received_context: LocalWorkerTurnContext,
        received_response: LocalWorkerTurnResponse,
    ) -> LocalWorkerTurnAttemptRecord:
        raise TypeError("bad lm5b api input")

    monkeypatch.setattr(module, "validate_local_worker_turn_response", raising_validator)

    with pytest.raises(TypeError, match="bad lm5b api input"):
        module.dispose_local_worker_turn_response(
            _minimal_context(),
            LocalWorkerTurnResponse(WorkerObservation("Observed.")),
        )


def test_real_lm5a_lm5b_chain_disposes_allowed_action_request() -> None:
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
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=context.allowed_actions[0].action_id,
            rationale="Draft repair params from the LM5A turn context.",
            input={"code": "A = 42.0;"},
        )
    )

    record = dispose_local_worker_turn_response(context, response)

    assert record.disposition == "candidate_action_request"
    assert record.attempt.valid is True
    assert record.attempt.context_workflow_id == context.workflow.workflow_id
    assert (
        record.attempt.context_contract_fingerprint
        == context.workflow.contract_fingerprint
    )


def test_local_worker_disposition_module_boundary_is_gate_only() -> None:
    import rook.agent.local_worker_turn_disposition as module

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
    }

    banned_names = {
        "Any",
        "Mapping",
        "MappingProxyType",
        "math",
        "WorkerAllowedAction",
        "propose_next_node",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "execute_mapped_step",
        "run_current_mapped_step",
        "run_current_step_stream",
        "EnvelopeSupplyResult",
        "CurrentStepRecord",
        "EnvelopeSupplyRecord",
        "PlanGraph",
        "CompiledWorkflowScaffold",
        "CatalogCurrentStepProvider",
        "WorkflowProvenanceEnvelopeSource",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "RookAgent",
        "base_agent",
        "dispatcher",
        "server",
        "model",
        "litellm",
        "OpenAI",
        "Path",
        "open",
        "json",
        "yaml",
        "loads",
        "dumps",
        "_freeze_json_value",
        "_freeze_json_mapping",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps"} & called_names)
