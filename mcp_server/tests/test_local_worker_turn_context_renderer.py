from __future__ import annotations

import ast
import copy
import inspect
import math
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from rook.agent import local_worker_turn_context as context_module
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
    render_local_worker_turn_context_payload,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
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
    "workflow",
    "current_graph",
    "current_node",
    "history",
    "knowledge",
    "allowed_actions",
}
WORKFLOW_KEYS = {
    "workflow_id",
    "contract_schema",
    "contract_fingerprint",
    "compiler_id",
    "provider_id",
    "selected_template_id",
    "max_steps",
}
GRAPH_KEYS = {
    "node_count",
    "node_ids",
    "ready_node_ids",
    "terminal_node_ids",
    "status_counts",
}
NODE_KEYS = {
    "node_id",
    "intent",
    "role",
    "status",
    "execution_ref",
    "is_terminal",
    "has_execution_params",
    "memory_keys",
}
HISTORY_KEYS = {
    "current_step_count",
    "supply_count",
    "last_accepted_node_id",
    "last_execution_kind",
    "last_stop_reason",
    "recent_steps",
    "recent_supplies",
}
STEP_KEYS = {"accepted_node_id", "execution_kind", "ran", "failure"}
SUPPLY_KEYS = {"decision", "reason", "selected_node_id", "has_envelope"}
KNOWLEDGE_KEYS = {"packet_id", "kind", "title", "content"}
ACTION_KEYS = {"action_id", "kind", "description", "input_schema"}


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
                    "nested": {"count": -3, "enabled": True, "ratio": 1.5},
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
        workflow_id="lm5h_context_renderer",
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
                    "name": "LM5HContextRenderer",
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
        metadata={"trace": {"slice": "LM5H"}},
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


def _response_payload_from_context_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    actions = payload["allowed_actions"]
    assert isinstance(actions, list)
    first_action = actions[0]
    assert isinstance(first_action, Mapping)
    action_id = first_action["action_id"]
    assert isinstance(action_id, str)
    return {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "action_request",
        "action_id": action_id,
        "rationale": "Use the first allowed action from the rendered context.",
        "input": {
            "code": "A = 42.0;",
            "mode": "body",
            "language": "csharp",
        },
    }


def test_public_schema_and_renderer_exports_are_present() -> None:
    assert LOCAL_WORKER_TURN_CONTEXT_SCHEMA == "rook.local_worker_turn_context:v1"
    assert "LOCAL_WORKER_TURN_CONTEXT_SCHEMA" in context_module.__all__
    assert "render_local_worker_turn_context_payload" in context_module.__all__


def test_rendered_payload_has_exact_shape_and_schema_value() -> None:
    payload = render_local_worker_turn_context_payload(_context())

    assert type(payload) is dict
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema"] == LOCAL_WORKER_TURN_CONTEXT_SCHEMA
    assert set(payload["workflow"]) == WORKFLOW_KEYS
    assert set(payload["current_graph"]) == GRAPH_KEYS
    assert set(payload["current_node"]) == NODE_KEYS
    assert set(payload["history"]) == HISTORY_KEYS
    assert set(payload["history"]["recent_steps"][0]) == STEP_KEYS
    assert set(payload["history"]["recent_supplies"][0]) == SUPPLY_KEYS
    assert set(payload["knowledge"][0]) == KNOWLEDGE_KEYS
    assert set(payload["allowed_actions"][0]) == ACTION_KEYS
    assert "response_schema" not in payload
    assert "instructions" not in payload
    assert "tools" not in payload
    assert "capabilities" not in payload


def test_rendered_payload_preserves_lm5a_field_names_and_values() -> None:
    context = _context()
    payload = render_local_worker_turn_context_payload(context)

    assert payload["workflow"]["workflow_id"] == context.workflow.workflow_id
    assert payload["workflow"]["max_steps"] == context.workflow.max_steps
    assert payload["current_graph"]["node_ids"] == [
        "create_script",
        "done",
        "repair_same_component",
    ]
    assert payload["current_graph"]["status_counts"] == {
        "pending": 1,
        "ready": 1,
        "terminal": 1,
    }
    assert payload["current_node"]["execution_ref"] == "gh_update_script:v1"
    assert payload["current_node"]["memory_keys"] == [
        "component_guid",
        "repair_anchor",
    ]
    assert payload["history"]["current_step_count"] == 2
    assert payload["history"]["recent_steps"][1]["failure"] == "needs_repair"
    assert payload["history"]["recent_supplies"][1]["selected_node_id"] == (
        "repair_same_component"
    )
    assert payload["knowledge"][0]["content"]["nested"]["count"] == -3
    assert payload["knowledge"][0]["content"]["nested"]["enabled"] is True
    assert payload["allowed_actions"][0]["input_schema"]["required"] == [
        "code",
        "mode",
    ]


def test_rendered_payload_uses_plain_mutable_json_ready_containers() -> None:
    payload = render_local_worker_turn_context_payload(_context())

    assert type(payload) is dict
    assert type(payload["workflow"]) is dict
    assert type(payload["current_graph"]["node_ids"]) is list
    assert type(payload["current_node"]["memory_keys"]) is list
    assert type(payload["history"]["recent_steps"]) is list
    assert type(payload["knowledge"]) is list
    assert type(payload["knowledge"][0]["content"]) is dict
    assert type(payload["knowledge"][0]["content"]["flags"]) is list
    assert type(payload["allowed_actions"]) is list
    assert type(payload["allowed_actions"][0]["input_schema"]) is dict
    assert not isinstance(payload["knowledge"][0]["content"], MappingProxyType)

    payload["workflow"]["workflow_id"] = "changed"
    payload["knowledge"][0]["content"]["flags"].append("mutated")
    payload["allowed_actions"][0]["input_schema"]["required"].append("language")

    assert payload["workflow"]["workflow_id"] == "changed"


def test_payload_mutation_does_not_affect_source_context() -> None:
    context = _context()
    payload = render_local_worker_turn_context_payload(context)

    payload["workflow"]["workflow_id"] = "changed"
    payload["knowledge"][0]["content"]["flags"].append("mutated")
    payload["knowledge"][0]["content"]["nested"]["enabled"] = False
    payload["allowed_actions"][0]["input_schema"]["required"].append("language")

    assert context.workflow.workflow_id == "repair_component"
    assert context.knowledge[0].content["flags"] == ("body", "repair")
    assert context.knowledge[0].content["nested"]["enabled"] is True
    assert context.allowed_actions[0].input_schema["required"] == ("code", "mode")


def test_current_node_none_renders_key_with_none_value() -> None:
    payload = render_local_worker_turn_context_payload(_context(current_node=False))

    assert set(payload) == TOP_LEVEL_KEYS
    assert "current_node" in payload
    assert payload["current_node"] is None


def test_renderer_rejects_non_context_input() -> None:
    with pytest.raises(TypeError, match="LocalWorkerTurnContext"):
        render_local_worker_turn_context_payload({"not": "context"})  # type: ignore[arg-type]


def test_renderer_defensively_rejects_non_string_mapping_keys() -> None:
    context = _context()
    object.__setattr__(context.knowledge[0], "content", {1: "bad"})

    with pytest.raises(TypeError, match="keys must be strings"):
        render_local_worker_turn_context_payload(context)


@pytest.mark.parametrize("bad_float", [math.inf, -math.inf, math.nan])
def test_renderer_defensively_rejects_non_finite_floats(bad_float: float) -> None:
    context = _context()
    object.__setattr__(context.knowledge[0], "content", {"bad": bad_float})

    with pytest.raises(TypeError, match="finite"):
        render_local_worker_turn_context_payload(context)


def test_renderer_preserves_bool_and_int_values_distinctly() -> None:
    payload = render_local_worker_turn_context_payload(_context())

    nested = payload["knowledge"][0]["content"]["nested"]
    assert nested["enabled"] is True
    assert nested["count"] == -3
    assert type(nested["count"]) is int


def test_renderer_function_body_boundary_guard() -> None:
    source = inspect.getsource(context_module)
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    target_names = {
        name
        for name in functions
        if name == "render_local_worker_turn_context_payload"
        or name.startswith("_render_")
    }

    assert "render_local_worker_turn_context_payload" in target_names
    assert "_render_json_value" in target_names

    banned_names = {
        "build_local_worker_turn_context",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "validate_local_worker_turn_response",
        "load_local_worker_turn_response_payload",
        "dispose_local_worker_turn_response",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
        "LOCAL_WORKER_TURN_RESPONSE_SCHEMA",
        "WorkerActionRequest",
        "WorkerClarificationRequest",
        "WorkerRefusal",
        "WorkerObservation",
        "LocalWorkerTurnResponse",
        "Path",
        "open",
        "json",
        "yaml",
        "YAML",
        "loads",
        "dumps",
        "safe_load",
        "model",
        "RookChat",
        "prompt",
        "dispatcher",
        "stream",
        "runtime",
        "CapabilityIndex",
    }
    banned_attributes = {"loads", "dumps"}

    for target_name in sorted(target_names):
        node = functions[target_name]
        referenced_names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        referenced_attributes = {
            child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
        }
        assert not (referenced_names & banned_names), target_name
        assert not (referenced_attributes & banned_attributes), target_name


def test_rendered_context_payload_composes_with_lm5g_lm5d_and_lm5f() -> None:
    context = _compiled_context()
    payload = render_local_worker_turn_context_payload(context)
    response_payload = _response_payload_from_context_payload(payload)

    assert payload["current_node"]["execution_ref"] == "gh_update_script:v1"
    assert response_payload["action_id"] == "draft_repair_params"
    assert response_payload["action_id"] != payload["current_node"]["execution_ref"]

    response = load_local_worker_turn_response_payload(response_payload)
    harness_record = run_local_worker_turn(context, lambda received: response)

    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="rendered_context_payload_chain",
            category="renderer_integration",
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
