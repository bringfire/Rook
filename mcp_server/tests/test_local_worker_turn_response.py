from __future__ import annotations

import ast
import copy
import math
from dataclasses import fields, is_dataclass
from pathlib import Path

import pytest

from rook.agent.local_worker_turn_context import (
    WorkerAllowedAction,
    build_local_worker_turn_context,
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

from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnAttemptRecord,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
    validate_local_worker_turn_response,
)


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5b_worker_response",
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
                    "name": "LM5BLocalWorkerResponse",
                    "x": 350,
                    "y": 1160,
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
        metadata={"trace": {"slice": "LM5B"}},
    )


def _context(*, include_actions: bool = True):
    scaffold = compile_workflow_contract(_repair_contract())
    actions = (
        (
            WorkerAllowedAction(
                action_id="draft_bind_params",
                kind="draft",
                description="Draft replacement C# body parameters.",
                input_schema={
                    "type": "object",
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            ),
        )
        if include_actions
        else ()
    )
    return build_local_worker_turn_context(
        scaffold,
        copy.deepcopy(scaffold.graph),
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(),
        allowed_actions=actions,
    )


def _action_request(action_id: str = "draft_bind_params") -> WorkerActionRequest:
    return WorkerActionRequest(
        action_id=action_id,
        rationale="Need to propose repair parameters.",
        input={"code": "A = 42.0;"},
    )


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_response as module

    assert module.__all__ == (
        "LocalWorkerTurnResponse",
        "LocalWorkerTurnAttemptRecord",
        "WorkerActionRequest",
        "WorkerClarificationRequest",
        "WorkerRefusal",
        "WorkerObservation",
        "WorkerResponseKind",
        "WorkerRefusalCategory",
        "WorkerResponseValidationFailure",
        "validate_local_worker_turn_response",
    )
    assert "WorkerResponsePayload" not in module.__all__


def test_public_dataclasses_are_frozen() -> None:
    for cls in (
        WorkerActionRequest,
        WorkerClarificationRequest,
        WorkerRefusal,
        WorkerObservation,
        LocalWorkerTurnResponse,
        LocalWorkerTurnAttemptRecord,
    ):
        assert is_dataclass(cls)
        assert cls.__dataclass_params__.frozen is True


def test_action_request_freezes_and_detaches_input() -> None:
    payload = {"nested": {"tags": ["before"]}}
    request = WorkerActionRequest(
        action_id="draft_bind_params",
        rationale="Need repair params.",
        input=payload,
    )

    payload["nested"]["tags"].append("after")

    assert request.input["nested"]["tags"] == ("before",)
    with pytest.raises(TypeError):
        request.input["nested"]["late"] = True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action_id": "", "rationale": "why", "input": {}},
        {"action_id": "draft", "rationale": "", "input": {}},
    ],
)
def test_action_request_empty_values_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkerActionRequest(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"action_id": 1, "rationale": "why", "input": {}},
        {"action_id": "draft", "rationale": 1, "input": {}},
        {"action_id": "draft", "rationale": "why", "input": []},
        {"action_id": "draft", "rationale": "why", "input": {1: "bad"}},
        {"action_id": "draft", "rationale": "why", "input": {"bad": object()}},
        {"action_id": "draft", "rationale": "why", "input": {"bad": math.inf}},
        {"action_id": "draft", "rationale": "why", "input": {"bad": lambda: None}},
    ],
)
def test_action_request_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerActionRequest(**kwargs)  # type: ignore[arg-type]


def test_clarification_request_accepts_question_and_optional_rationale() -> None:
    request = WorkerClarificationRequest(
        question="Which component should be repaired?",
        rationale="The context names two candidates.",
    )

    assert request.question == "Which component should be repaired?"
    assert request.rationale == "The context names two candidates."


def test_clarification_request_empty_question_rejected() -> None:
    with pytest.raises(ValueError):
        WorkerClarificationRequest(question="")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"question": 1, "rationale": None},
        {"question": "Question?", "rationale": 1},
        {"question": None, "rationale": None},
    ],
)
def test_clarification_request_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerClarificationRequest(**kwargs)  # type: ignore[arg-type]


def test_refusal_accepts_closed_category() -> None:
    refusal = WorkerRefusal(
        category="insufficient_context",
        reason="No action can be selected from the provided context.",
    )

    assert refusal.category == "insufficient_context"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": "unknown", "reason": "No."},
        {"category": "unsafe", "reason": ""},
    ],
)
def test_refusal_bad_values_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkerRefusal(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"category": 1, "reason": "No."},
        {"category": "unsafe", "reason": 1},
    ],
)
def test_refusal_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerRefusal(**kwargs)  # type: ignore[arg-type]


def test_observation_freezes_and_detaches_data() -> None:
    data = {"nested": {"warnings": ["one"]}}
    observation = WorkerObservation(
        message="The graph has a repair node.",
        data=data,
    )

    data["nested"]["warnings"].append("two")

    assert observation.data is not None
    assert observation.data["nested"]["warnings"] == ("one",)
    with pytest.raises(TypeError):
        observation.data["nested"]["late"] = True


def test_observation_allows_missing_data() -> None:
    observation = WorkerObservation(message="Nothing to add.")

    assert observation.data is None


def test_observation_empty_message_rejected() -> None:
    with pytest.raises(ValueError):
        WorkerObservation(message="")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"message": 1, "data": None},
        {"message": "note", "data": []},
        {"message": "note", "data": {1: "bad"}},
        {"message": "note", "data": {"bad": object()}},
        {"message": "note", "data": {"bad": math.inf}},
    ],
)
def test_observation_bad_types_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerObservation(**kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "payload",
    [
        WorkerActionRequest("draft_bind_params", "Need repair params.", {}),
        WorkerClarificationRequest("Which component?"),
        WorkerRefusal("out_of_scope", "Cannot answer with provided actions."),
        WorkerObservation("Observed a repair node."),
    ],
)
def test_response_accepts_exactly_one_closed_payload(payload: object) -> None:
    response = LocalWorkerTurnResponse(payload=payload)

    assert response.payload is payload


@pytest.mark.parametrize("payload", [None, {}, [], (WorkerObservation("one"),), object()])
def test_response_rejects_non_closed_payloads(payload: object) -> None:
    with pytest.raises(TypeError):
        LocalWorkerTurnResponse(payload=payload)  # type: ignore[arg-type]


def test_validator_wrong_context_type_raises_type_error() -> None:
    response = LocalWorkerTurnResponse(WorkerObservation("note"))

    with pytest.raises(TypeError):
        validate_local_worker_turn_response(object(), response)  # type: ignore[arg-type]


def test_validator_wrong_response_type_raises_type_error() -> None:
    context = _context()

    with pytest.raises(TypeError):
        validate_local_worker_turn_response(context, object())  # type: ignore[arg-type]


def test_valid_action_request_returns_compact_attempt_record() -> None:
    context = _context()
    response = LocalWorkerTurnResponse(payload=_action_request())

    record = validate_local_worker_turn_response(context, response)

    assert record == LocalWorkerTurnAttemptRecord(
        valid=True,
        response_kind="action_request",
        failure=None,
        reason="valid_action_request",
        action_id="draft_bind_params",
        context_workflow_id=context.workflow.workflow_id,
        context_contract_fingerprint=context.workflow.contract_fingerprint,
    )


def test_action_request_input_schema_is_not_validated() -> None:
    context = _context()
    action_id = context.allowed_actions[0].action_id
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=action_id,
            rationale="Request stays structurally valid despite schema mismatch.",
            input={"not_code": 123},
        )
    )

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is True
    assert record.response_kind == "action_request"
    assert record.reason == "valid_action_request"
    assert record.failure is None


def test_unknown_action_id_returns_invalid_attempt_record() -> None:
    context = _context()
    response = LocalWorkerTurnResponse(payload=_action_request("invented_action"))

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind == "action_request"
    assert record.failure == "unknown_action_id"
    assert record.reason == "unknown_action_id:invented_action"
    assert record.action_id == "invented_action"
    assert record.context_workflow_id == context.workflow.workflow_id
    assert record.context_contract_fingerprint == context.workflow.contract_fingerprint


def test_context_with_no_actions_still_accepts_non_action_responses() -> None:
    context = _context(include_actions=False)

    clarification = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(WorkerClarificationRequest("What should I do?")),
    )
    refusal = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(WorkerRefusal("unsupported_action", "No actions.")),
    )
    observation = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(WorkerObservation("No actions are available.")),
    )
    action = validate_local_worker_turn_response(
        context,
        LocalWorkerTurnResponse(_action_request()),
    )

    assert clarification.valid is True
    assert refusal.valid is True
    assert observation.valid is True
    assert action.valid is False
    assert action.failure == "unknown_action_id"
    assert action.reason == "unknown_action_id:draft_bind_params"


@pytest.mark.parametrize(
    ("payload", "kind", "reason"),
    [
        (
            WorkerClarificationRequest("What should I do?"),
            "clarification_request",
            "valid_clarification_request",
        ),
        (
            WorkerRefusal("out_of_scope", "Cannot respond."),
            "refusal",
            "valid_refusal",
        ),
        (
            WorkerObservation("Observed context."),
            "observation",
            "valid_observation",
        ),
    ],
)
def test_valid_non_action_responses_use_stable_reasons(
    payload: object,
    kind: str,
    reason: str,
) -> None:
    context = _context(include_actions=False)
    response = LocalWorkerTurnResponse(payload=payload)

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is True
    assert record.response_kind == kind
    assert record.failure is None
    assert record.reason == reason
    assert record.action_id is None


def test_validator_defensively_records_payload_invalid_after_bypass() -> None:
    context = _context()
    response = LocalWorkerTurnResponse(WorkerObservation("Observed context."))
    object.__setattr__(response, "payload", object())

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind is None
    assert record.failure == "payload_invalid"
    assert record.reason == "payload_invalid:closed_payload_required"
    assert record.action_id is None


def test_validator_defensively_records_action_input_invalid_after_bypass() -> None:
    context = _context()
    action = _action_request()
    object.__setattr__(action, "input", [])
    response = LocalWorkerTurnResponse(action)

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind == "action_request"
    assert record.failure == "action_input_invalid"
    assert record.reason == "action_input_invalid:input_not_mapping"
    assert record.action_id == "draft_bind_params"


def test_validator_rejects_bypass_mutated_mutable_action_input() -> None:
    context = _context()
    action = _action_request()
    object.__setattr__(action, "input", {"code": "A = 42.0;"})
    response = LocalWorkerTurnResponse(action)

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind == "action_request"
    assert record.failure == "action_input_invalid"
    assert record.reason == "action_input_invalid:input_malformed"
    assert record.action_id == "draft_bind_params"


def test_validator_rejects_bypass_mutated_mutable_observation_data() -> None:
    context = _context()
    observation = WorkerObservation("Observed context.", data={"frozen": True})
    object.__setattr__(observation, "data", {"x": 1})
    response = LocalWorkerTurnResponse(observation)

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is False
    assert record.response_kind is None
    assert record.failure == "payload_invalid"
    assert record.reason == "payload_invalid:observation_invalid"
    assert record.action_id is None


def test_attempt_record_has_only_compact_fields() -> None:
    assert tuple(field.name for field in fields(LocalWorkerTurnAttemptRecord)) == (
        "valid",
        "response_kind",
        "failure",
        "reason",
        "action_id",
        "context_workflow_id",
        "context_contract_fingerprint",
    )


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "valid": True,
            "response_kind": "action_request",
            "failure": "unknown_action_id",
            "reason": "valid_action_request",
            "action_id": "draft_bind_params",
        },
        {
            "valid": True,
            "response_kind": None,
            "failure": None,
            "reason": "valid_action_request",
            "action_id": "draft_bind_params",
        },
        {
            "valid": False,
            "response_kind": "action_request",
            "failure": None,
            "reason": "unknown_action_id:draft_bind_params",
            "action_id": "draft_bind_params",
        },
        {
            "valid": True,
            "response_kind": "action_request",
            "failure": None,
            "reason": "valid_action_request",
            "action_id": None,
        },
        {
            "valid": True,
            "response_kind": "observation",
            "failure": None,
            "reason": "valid_observation",
            "action_id": "draft_bind_params",
        },
        {
            "valid": True,
            "response_kind": "observation",
            "failure": None,
            "reason": "valid_refusal",
            "action_id": None,
        },
    ],
)
def test_attempt_record_rejects_semantically_impossible_validity(
    kwargs: dict[str, object],
) -> None:
    with pytest.raises(ValueError):
        LocalWorkerTurnAttemptRecord(
            **kwargs,
            context_workflow_id="workflow",
            context_contract_fingerprint="fingerprint",
        )  # type: ignore[arg-type]


def test_attempt_record_allows_minimal_invalid_reason_coherence() -> None:
    record = LocalWorkerTurnAttemptRecord(
        valid=False,
        response_kind="action_request",
        failure="unknown_action_id",
        reason="custom-invalid-detail",
        action_id="draft_bind_params",
        context_workflow_id="workflow",
        context_contract_fingerprint="fingerprint",
    )

    assert record.reason == "custom-invalid-detail"


def test_real_lm5a_context_validates_real_allowed_action_request() -> None:
    context = _context()
    action_id = context.allowed_actions[0].action_id
    response = LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=action_id,
            rationale="Draft repair params from the LM5A turn context.",
            input={"code": "A = 42.0;"},
        )
    )

    record = validate_local_worker_turn_response(context, response)

    assert record.valid is True
    assert record.action_id == action_id
    assert record.context_workflow_id == context.workflow.workflow_id
    assert record.context_contract_fingerprint == context.workflow.contract_fingerprint


def test_local_worker_response_module_boundary_is_response_contract_only() -> None:
    import rook.agent.local_worker_turn_response as module

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

    allowed_import_modules = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "math",
        "types",
        "typing",
        "rook.agent.local_worker_turn_context",
    }
    assert imported_modules <= allowed_import_modules

    banned_names = {
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
        "yaml",
        "loads",
        "dumps",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps"} & called_names)
