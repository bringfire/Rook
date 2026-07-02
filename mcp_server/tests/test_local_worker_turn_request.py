from __future__ import annotations

import ast
import copy
import inspect
from collections.abc import Mapping

import pytest

import rook.agent.local_worker_turn_request as request_module
from rook.agent.local_worker_scenario_evaluation import (
    LocalWorkerScenarioExpectation,
    evaluate_local_worker_scenario_result,
)
from rook.agent.local_worker_turn_context import (
    LOCAL_WORKER_TURN_CONTEXT_SCHEMA,
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerKnowledgePacket,
    WorkerNodeSummary,
    WorkerStepTraceSummary,
    WorkerSupplyTraceSummary,
    WorkerWorkflowSummary,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
from rook.agent.local_worker_turn_request import (
    LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
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


TOP_LEVEL_KEYS = {
    "schema",
    "context",
    "response_schema",
    "response_contract",
}
RESPONSE_CONTRACT_KEYS = {
    "kinds",
    "field_sets",
    "required_nullable_fields",
    "refusal_categories",
}
RESPONSE_KINDS = [
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
]
RESPONSE_FIELD_SETS = {
    "action_request": ["schema", "kind", "action_id", "rationale", "input"],
    "clarification_request": ["schema", "kind", "question", "rationale"],
    "refusal": ["schema", "kind", "category", "reason"],
    "observation": ["schema", "kind", "message", "data"],
}
REQUIRED_NULLABLE_FIELDS = {
    "clarification_request": ["rationale"],
    "observation": ["data"],
}
REFUSAL_CATEGORIES = [
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
]


def _context(*, current_node: bool = True) -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="repair_component",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="fingerprint-123",
            compiler_id="rook.workflow_contract.compiler:v1",
            provider_id="rook.catalog_current_step_provider:v1",
            selected_template_id="gh_repair_component:v1",
            max_steps=6,
        ),
        current_graph=WorkerGraphSummary(
            node_count=3,
            node_ids=("create_script", "done", "repair_same_component"),
            ready_node_ids=("repair_same_component",),
            terminal_node_ids=("done",),
            status_counts={"pending": 1, "ready": 1, "terminal": 1},
        ),
        current_node=(
            WorkerNodeSummary(
                node_id="repair_same_component",
                intent="repair existing C# script component",
                role="repair",
                status="ready",
                execution_ref="gh_update_script:v1",
                is_terminal=False,
                has_execution_params=True,
                memory_keys=("component_guid", "repair_anchor"),
            )
            if current_node
            else None
        ),
        history=WorkerHistorySummary(
            current_step_count=2,
            supply_count=2,
            last_accepted_node_id="verify_create",
            last_execution_kind="verifier",
            last_stop_reason="needs_repair",
            recent_steps=(
                WorkerStepTraceSummary(
                    accepted_node_id="create_script",
                    execution_kind="producer",
                    ran=True,
                    failure=None,
                ),
                WorkerStepTraceSummary(
                    accepted_node_id="verify_create",
                    execution_kind="verifier",
                    ran=True,
                    failure="needs_repair",
                ),
            ),
            recent_supplies=(
                WorkerSupplyTraceSummary(
                    decision="SUPPLY",
                    reason=None,
                    selected_node_id="create_script",
                    has_envelope=True,
                ),
                WorkerSupplyTraceSummary(
                    decision="SUPPLY",
                    reason="needs_repair",
                    selected_node_id="repair_same_component",
                    has_envelope=True,
                ),
            ),
        ),
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script body mode",
                content={
                    "source": "test fixture",
                    "trust": "high",
                    "flags": ("body", "repair"),
                    "nested": {"count": -3, "enabled": True},
                },
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "mode": {"enum": ("body", "full_source")},
                    },
                    "required": ("code", "mode"),
                },
            ),
        ),
    )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5i_request_envelope",
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
                    "name": "LM5IRequestEnvelope",
                    "x": 350,
                    "y": 1420,
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
                        bindings={"guid": ("repair_anchor", "component_guid")},
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
        metadata={"trace": {"slice": "LM5I"}},
    )


def _compiled_context() -> LocalWorkerTurnContext:
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
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script components use body-style code",
                content={
                    "source": "test fixture",
                    "trust": "high",
                    "guidance": "Use body-style code.",
                },
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={"type": "object", "required": ["code", "mode"]},
            ),
        ),
    )


def _response_payload_from_request_payload(
    request_payload: Mapping[str, object],
) -> dict[str, object]:
    context_payload = request_payload["context"]
    assert isinstance(context_payload, Mapping)
    actions = context_payload["allowed_actions"]
    assert isinstance(actions, list)
    first_action = actions[0]
    assert isinstance(first_action, Mapping)
    action_id = first_action["action_id"]
    assert isinstance(action_id, str)

    current_node = context_payload["current_node"]
    assert isinstance(current_node, Mapping)
    assert action_id != current_node["execution_ref"]

    assert request_payload["response_schema"] == LOCAL_WORKER_TURN_RESPONSE_SCHEMA
    response_contract = request_payload["response_contract"]
    assert isinstance(response_contract, Mapping)
    assert response_contract["field_sets"]["action_request"] == RESPONSE_FIELD_SETS[
        "action_request"
    ]

    return {
        "schema": request_payload["response_schema"],
        "kind": "action_request",
        "action_id": action_id,
        "rationale": "Use the first allowed action from the request context.",
        "input": {
            "code": "A = 42.0;",
            "mode": "body",
            "language": "csharp",
        },
    }


def test_public_surface_is_explicit() -> None:
    assert LOCAL_WORKER_TURN_REQUEST_SCHEMA == "rook.local_worker_turn_request:v1"
    assert request_module.__all__ == (
        "LOCAL_WORKER_TURN_REQUEST_SCHEMA",
        "render_local_worker_turn_request_payload",
    )


def test_request_payload_has_exact_top_level_shape_and_schema_values() -> None:
    payload = render_local_worker_turn_request_payload(_context())

    assert type(payload) is dict
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema"] == LOCAL_WORKER_TURN_REQUEST_SCHEMA
    assert payload["context"]["schema"] == LOCAL_WORKER_TURN_CONTEXT_SCHEMA
    assert payload["response_schema"] == LOCAL_WORKER_TURN_RESPONSE_SCHEMA
    assert "context_schema" not in payload
    assert "instructions" not in payload
    assert "prompt" not in payload
    assert "adapter" not in payload
    assert "model" not in payload
    assert "worker" not in payload
    assert "request_id" not in payload
    assert "timestamp" not in payload
    assert "run_id" not in payload
    assert "context_id" not in payload
    assert "fingerprint" not in payload


def test_response_contract_is_exact_structural_vocabulary_only() -> None:
    payload = render_local_worker_turn_request_payload(_context())
    contract = payload["response_contract"]

    assert type(contract) is dict
    assert set(contract) == RESPONSE_CONTRACT_KEYS
    assert contract["kinds"] == RESPONSE_KINDS
    assert contract["field_sets"] == RESPONSE_FIELD_SETS
    assert contract["required_nullable_fields"] == REQUIRED_NULLABLE_FIELDS
    assert contract["refusal_categories"] == REFUSAL_CATEGORIES
    assert "descriptions" not in contract
    assert "examples" not in contract
    assert "notes" not in contract
    assert "instructions" not in contract
    assert "semantics" not in contract
    assert "action_authorization" not in contract


def test_request_payload_uses_plain_mutable_containers() -> None:
    payload = render_local_worker_turn_request_payload(_context())

    assert type(payload) is dict
    assert type(payload["context"]) is dict
    assert type(payload["response_contract"]) is dict
    assert type(payload["response_contract"]["kinds"]) is list
    assert type(payload["response_contract"]["field_sets"]) is dict
    assert type(payload["response_contract"]["field_sets"]["action_request"]) is list
    assert type(payload["response_contract"]["required_nullable_fields"]) is dict
    assert type(
        payload["response_contract"]["required_nullable_fields"]["observation"]
    ) is list
    assert type(payload["response_contract"]["refusal_categories"]) is list

    payload["response_contract"]["kinds"].append("mutated")
    payload["response_contract"]["field_sets"]["action_request"].append("mutated")

    assert payload["response_contract"]["kinds"][-1] == "mutated"


def test_response_contract_is_fresh_across_calls() -> None:
    context = _context()
    first = render_local_worker_turn_request_payload(context)
    first["response_contract"]["kinds"].append("bad")
    first["response_contract"]["field_sets"]["action_request"].append("bad")
    first["response_contract"]["required_nullable_fields"]["observation"].append(
        "bad"
    )
    first["response_contract"]["refusal_categories"].append("bad")

    second = render_local_worker_turn_request_payload(context)

    assert second["response_contract"]["kinds"] == RESPONSE_KINDS
    assert second["response_contract"]["field_sets"] == RESPONSE_FIELD_SETS
    assert second["response_contract"]["required_nullable_fields"] == (
        REQUIRED_NULLABLE_FIELDS
    )
    assert second["response_contract"]["refusal_categories"] == REFUSAL_CATEGORIES


def test_context_payload_is_fresh_across_calls_and_detached_from_source() -> None:
    context = _context()
    first = render_local_worker_turn_request_payload(context)
    first["context"]["workflow"]["workflow_id"] = "changed"
    first["context"]["knowledge"][0]["content"]["flags"].append("mutated")

    second = render_local_worker_turn_request_payload(context)

    assert second["context"]["workflow"]["workflow_id"] == "repair_component"
    assert second["context"]["knowledge"][0]["content"]["flags"] == [
        "body",
        "repair",
    ]
    assert context.workflow.workflow_id == "repair_component"
    assert context.knowledge[0].content["flags"] == ("body", "repair")


def test_request_renderer_prechecks_context_type() -> None:
    with pytest.raises(TypeError, match="LocalWorkerTurnContext"):
        render_local_worker_turn_request_payload({"not": "context"})  # type: ignore[arg-type]


def test_request_renderer_calls_lm5h_once_and_embeds_returned_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    rendered_context = {
        "schema": LOCAL_WORKER_TURN_CONTEXT_SCHEMA,
        "sentinel": "context-payload",
    }
    calls: list[LocalWorkerTurnContext] = []

    def fake_renderer(received: LocalWorkerTurnContext) -> Mapping[str, object]:
        calls.append(received)
        return rendered_context

    monkeypatch.setattr(
        request_module,
        "render_local_worker_turn_context_payload",
        fake_renderer,
    )

    payload = render_local_worker_turn_request_payload(context)

    assert calls == [context]
    assert payload["context"] is rendered_context


def test_module_level_boundary_guard() -> None:
    source = inspect.getsource(request_module)
    tree = ast.parse(source)

    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                if alias.asname is not None:
                    imports.add(alias.asname)
        elif isinstance(node, ast.ImportFrom):
            imports.add(node.module or "")
            for alias in node.names:
                imports.add(alias.name)
                if alias.asname is not None:
                    imports.add(alias.asname)

    assert "json" not in imports
    assert "yaml" not in imports
    assert "pathlib" not in imports

    banned_names = {
        "LOCAL_WORKER_TURN_CONTEXT_SCHEMA",
        "load_local_worker_turn_response_payload",
        "validate_local_worker_turn_response",
        "WorkerActionRequest",
        "WorkerClarificationRequest",
        "WorkerRefusal",
        "WorkerObservation",
        "LocalWorkerTurnResponse",
        "dispose_local_worker_turn_response",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
        "build_local_worker_turn_context",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "json",
        "yaml",
        "YAML",
        "Path",
        "open",
        "model",
        "RookChat",
        "prompt",
        "dispatcher",
        "CapabilityIndex",
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not (imports & banned_names)
    assert not (referenced_names & banned_names)
    assert "loads" not in referenced_attributes
    assert "dumps" not in referenced_attributes
    assert "safe_load" not in referenced_attributes


def test_request_payload_composes_with_lm5g_lm5d_and_lm5f() -> None:
    context = _compiled_context()
    request_payload = render_local_worker_turn_request_payload(context)
    response_payload = _response_payload_from_request_payload(request_payload)

    assert request_payload["context"]["current_node"]["execution_ref"] == (
        "gh_update_script:v1"
    )
    assert response_payload["action_id"] == "draft_repair_params"
    assert response_payload["action_id"] != (
        request_payload["context"]["current_node"]["execution_ref"]
    )

    response = load_local_worker_turn_response_payload(response_payload)
    harness_record = run_local_worker_turn(context, lambda received: response)

    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="request_envelope_payload_chain",
            category="request_envelope_integration",
            expected_status="completed",
            expected_disposition="candidate_action_request",
            expected_attempt_valid=True,
            expected_action_id="draft_repair_params",
            expected_response_kind="action_request",
            expected_workflow_id=context.workflow.workflow_id,
            expected_contract_fingerprint=context.workflow.contract_fingerprint,
        ),
        harness_record,
    )

    assert harness_record.status == "completed"
    assert result.passed is True
