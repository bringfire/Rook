from __future__ import annotations

import ast
from collections.abc import Mapping
import inspect

import pytest

from rook.agent import local_worker_turn_response as response_module
from rook.agent.local_worker_scenario_evaluation import (
    LocalWorkerScenarioExpectation,
    evaluate_local_worker_scenario_result,
)
from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerWorkflowSummary,
)
from rook.agent.local_worker_turn_disposition import (
    dispose_local_worker_turn_response,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
    load_local_worker_turn_response_payload,
    validate_local_worker_turn_response,
)


def _action_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "action_request",
        "action_id": "draft_repair_params",
        "rationale": "Use the explicit repair action.",
        "input": {
            "mode": "body",
            "pins_out": ["A:double"],
            "nested": {"values": [1, 2]},
        },
    }
    payload.update(overrides)
    return payload


def _clarification_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "clarification_request",
        "question": "Which component should be repaired?",
        "rationale": None,
    }
    payload.update(overrides)
    return payload


def _refusal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "refusal",
        "category": "out_of_scope",
        "reason": "The requested operation is outside this worker turn.",
    }
    payload.update(overrides)
    return payload


def _observation_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "observation",
        "message": "The terminal node is already visible.",
        "data": {"node_id": "done", "flags": ["terminal"]},
    }
    payload.update(overrides)
    return payload


def _context(*, action_id: str = "draft_repair_params") -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="repair_component",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="fingerprint-123",
            compiler_id="rook.workflow_contract.compiler:v1",
            provider_id="rook.catalog_current_step_provider:v1",
            selected_template_id="gh_repair_component:v1",
            max_steps=5,
        ),
        current_graph=WorkerGraphSummary(
            node_count=1,
            node_ids=("repair_same_component",),
            ready_node_ids=("repair_same_component",),
            terminal_node_ids=("done",),
            status_counts={"READY": 1},
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
        allowed_actions=(
            WorkerAllowedAction(
                action_id=action_id,
                kind="draft_params",
                description="Draft repair params.",
                input_schema={"type": "object"},
            ),
        ),
    )


def test_schema_constant_and_public_exports_are_present() -> None:
    assert LOCAL_WORKER_TURN_RESPONSE_SCHEMA == "rook.local_worker_turn_response:v1"
    assert "LOCAL_WORKER_TURN_RESPONSE_SCHEMA" in response_module.__all__
    assert "load_local_worker_turn_response_payload" in response_module.__all__


def test_loads_action_request_payload_and_normalizes_nested_lists() -> None:
    response = load_local_worker_turn_response_payload(_action_payload())

    assert isinstance(response, LocalWorkerTurnResponse)
    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.action_id == "draft_repair_params"
    assert response.payload.rationale == "Use the explicit repair action."
    assert response.payload.input["mode"] == "body"
    assert response.payload.input["pins_out"] == ("A:double",)
    nested = response.payload.input["nested"]
    assert isinstance(nested, Mapping)
    assert nested["values"] == (1, 2)


def test_loads_action_request_payload_and_normalizes_nested_tuples() -> None:
    response = load_local_worker_turn_response_payload(
        _action_payload(input={"pins_out": ("A:double",), "nested": {"values": (1, 2)}})
    )

    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.input["pins_out"] == ("A:double",)
    nested = response.payload.input["nested"]
    assert isinstance(nested, Mapping)
    assert nested["values"] == (1, 2)


def test_loads_unknown_action_id_without_context_admissibility() -> None:
    response = load_local_worker_turn_response_payload(
        _action_payload(action_id="not_declared_here")
    )

    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.action_id == "not_declared_here"

    attempt = validate_local_worker_turn_response(_context(), response)
    assert attempt.valid is False
    assert attempt.failure == "unknown_action_id"
    assert attempt.reason == "unknown_action_id:not_declared_here"


def test_loads_clarification_request_with_required_none_rationale() -> None:
    response = load_local_worker_turn_response_payload(_clarification_payload())

    assert isinstance(response.payload, WorkerClarificationRequest)
    assert response.payload.question == "Which component should be repaired?"
    assert response.payload.rationale is None


def test_loads_refusal_payload() -> None:
    response = load_local_worker_turn_response_payload(_refusal_payload())

    assert isinstance(response.payload, WorkerRefusal)
    assert response.payload.category == "out_of_scope"
    assert response.payload.reason == "The requested operation is outside this worker turn."


def test_loads_observation_payload_with_required_mapping_data() -> None:
    response = load_local_worker_turn_response_payload(_observation_payload())

    assert isinstance(response.payload, WorkerObservation)
    assert response.payload.message == "The terminal node is already visible."
    assert response.payload.data is not None
    assert response.payload.data["flags"] == ("terminal",)


def test_loads_observation_payload_with_required_none_data() -> None:
    response = load_local_worker_turn_response_payload(_observation_payload(data=None))

    assert isinstance(response.payload, WorkerObservation)
    assert response.payload.data is None


@pytest.mark.parametrize(
    ("payload_factory", "missing_field"),
    [
        (_action_payload, "input"),
        (_clarification_payload, "rationale"),
        (_refusal_payload, "reason"),
        (_observation_payload, "data"),
    ],
)
def test_rejects_missing_variant_fields(
    payload_factory: object,
    missing_field: str,
) -> None:
    payload = payload_factory()
    assert isinstance(payload, dict)
    payload.pop(missing_field)

    with pytest.raises(ValueError, match="missing required fields"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize(
    "payload_factory",
    [
        _action_payload,
        _clarification_payload,
        _refusal_payload,
        _observation_payload,
    ],
)
def test_rejects_unknown_variant_fields(payload_factory: object) -> None:
    payload = payload_factory(extra="nope")
    assert isinstance(payload, dict)

    with pytest.raises(ValueError, match="unknown fields"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize("field", ["schema", "kind"])
def test_rejects_missing_top_level_dispatch_fields(field: str) -> None:
    payload = _action_payload()
    payload.pop(field)

    with pytest.raises(ValueError, match="missing required fields"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema", 123),
        ("kind", 123),
    ],
)
def test_rejects_non_string_top_level_dispatch_fields(
    field: str,
    value: object,
) -> None:
    payload = _action_payload(**{field: value})

    with pytest.raises(TypeError):
        load_local_worker_turn_response_payload(payload)


def test_rejects_unsupported_schema() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        load_local_worker_turn_response_payload(_action_payload(schema="other:v1"))


def test_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown"):
        load_local_worker_turn_response_payload(_action_payload(kind="action"))


def test_rejects_non_mapping_top_level_payload() -> None:
    with pytest.raises(TypeError, match="mapping"):
        load_local_worker_turn_response_payload(["not", "a", "mapping"])  # type: ignore[arg-type]


def test_rejects_non_string_top_level_mapping_keys() -> None:
    payload: dict[object, object] = dict(_action_payload())
    payload[1] = "bad"

    with pytest.raises(TypeError, match="string keys"):
        load_local_worker_turn_response_payload(payload)  # type: ignore[arg-type]


def test_rejects_non_string_nested_mapping_keys() -> None:
    payload = _action_payload(input={"ok": 1, 2: "bad"})

    with pytest.raises(TypeError, match="string keys"):
        load_local_worker_turn_response_payload(payload)


@pytest.mark.parametrize(
    "bad_input",
    [
        None,
        ["not", "mapping"],
        "not mapping",
    ],
)
def test_rejects_action_input_that_is_not_mapping(bad_input: object) -> None:
    with pytest.raises(TypeError, match="mapping"):
        load_local_worker_turn_response_payload(_action_payload(input=bad_input))


@pytest.mark.parametrize(
    "bad_data",
    [
        ["not", "mapping"],
        "not mapping",
        42,
    ],
)
def test_rejects_observation_data_that_is_not_mapping_or_none(
    bad_data: object,
) -> None:
    with pytest.raises(TypeError, match="mapping"):
        load_local_worker_turn_response_payload(_observation_payload(data=bad_data))


@pytest.mark.parametrize(
    "bad_value",
    [
        float("inf"),
        float("-inf"),
        float("nan"),
        object(),
        {"bad", "set"},
        lambda: None,
    ],
)
def test_rejects_non_json_safe_nested_values(bad_value: object) -> None:
    with pytest.raises(TypeError):
        load_local_worker_turn_response_payload(
            _action_payload(input={"bad": bad_value})
        )


def test_caller_payload_mutation_after_load_does_not_affect_response() -> None:
    payload = _action_payload()
    input_payload = payload["input"]
    assert isinstance(input_payload, dict)
    pins_out = input_payload["pins_out"]
    nested = input_payload["nested"]
    assert isinstance(pins_out, list)
    assert isinstance(nested, dict)

    response = load_local_worker_turn_response_payload(payload)

    pins_out.append("B:int")
    nested_values = nested["values"]
    assert isinstance(nested_values, list)
    nested_values.append(3)
    input_payload["mode"] = "class"

    assert isinstance(response.payload, WorkerActionRequest)
    assert response.payload.input["mode"] == "body"
    assert response.payload.input["pins_out"] == ("A:double",)
    copied_nested = response.payload.input["nested"]
    assert isinstance(copied_nested, Mapping)
    assert copied_nested["values"] == (1, 2)


def test_caller_observation_data_mutation_after_load_does_not_affect_response() -> None:
    payload = _observation_payload()
    data_payload = payload["data"]
    assert isinstance(data_payload, dict)
    flags = data_payload["flags"]
    assert isinstance(flags, list)

    response = load_local_worker_turn_response_payload(payload)

    flags.append("mutated")
    data_payload["node_id"] = "changed"

    assert isinstance(response.payload, WorkerObservation)
    assert response.payload.data is not None
    assert response.payload.data["node_id"] == "done"
    assert response.payload.data["flags"] == ("terminal",)


def test_loaded_response_composes_with_lm5b_lm5c_lm5d_and_lm5f() -> None:
    context = _context()
    response = load_local_worker_turn_response_payload(_action_payload())

    attempt = validate_local_worker_turn_response(context, response)
    assert attempt.valid is True
    assert attempt.action_id == "draft_repair_params"

    disposition = dispose_local_worker_turn_response(context, response)
    assert disposition.disposition == "candidate_action_request"

    harness_record = run_local_worker_turn(context, lambda received: response)
    assert harness_record.status == "completed"
    assert harness_record.response is response
    assert harness_record.disposition is not None
    assert harness_record.disposition.disposition == "candidate_action_request"

    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="loaded_response_chain",
            category="loader_integration",
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
    assert result.passed is True


def test_loader_function_body_boundary_guard() -> None:
    source = inspect.getsource(response_module)
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    target_names = {
        name
        for name in functions
        if name == "load_local_worker_turn_response_payload"
        or name.startswith("_load_")
        or name
        in {
            "_copy_json_payload",
            "_copy_json_mapping",
            "_require_fields",
            "_require_mapping",
            "_require_present",
            "_require_string_keys",
        }
    }

    assert "load_local_worker_turn_response_payload" in target_names
    assert "_copy_json_payload" in target_names

    banned_names = {
        "LocalWorkerTurnContext",
        "validate_local_worker_turn_response",
        "dispose_local_worker_turn_response",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
        "Path",
        "open",
        "compile_workflow_contract",
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "RookAgent",
        "base_agent",
        "RookChat",
        "dispatcher",
        "json",
        "loads",
        "model",
        "prompt",
        "dumps",
        "yaml",
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
