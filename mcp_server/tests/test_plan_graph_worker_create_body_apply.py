"""Tests for the pure Worker initial-body scaffold applicator."""

from __future__ import annotations

import copy
from dataclasses import replace
import hashlib
import json

import pytest

import rook.agent.plan_graph_worker_create_body_apply as apply_module
from rook.agent.minimal_csharp_initial_body_handoff import (
    _build_initial_body_contract,
)
from rook.agent.minimal_csharp_repair_handoff import (
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_worker_create_body_apply import (
    apply_worker_create_body_to_scaffold,
)
from rook.agent.plan_graph_workflow_contract import compile_workflow_contract
from rook.learning.plan_graph import PlanGraphEdge, PlanGraphNode


_WORKER_BODY = "A = 42.0;"


class _EqualitySpoof:
    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("draft_create_body")


def _valid_draft() -> ValidatedPlannerDraft:
    return load_minimal_csharp_repair_draft(
        {
            "goal": "Create one C# component and compile cleanly.",
            "capability": "grasshopper_csharp_component",
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
            "acceptance": "clean_compile_receipt",
        }
    )


def _scaffold():
    return compile_workflow_contract(
        _build_initial_body_contract(_valid_draft())
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _replace_graph(scaffold, mutate):
    graph = copy.deepcopy(scaffold.graph)
    mutate(graph)
    return replace(scaffold, graph=graph)


def _set_create_params(graph, value: object) -> None:
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = value


def test_applicator_adds_only_worker_code_to_a_copied_scaffold_graph():
    scaffold = _scaffold()
    original_graph = copy.deepcopy(scaffold.graph)
    original_params = scaffold.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    original_bytes = _canonical(dict(original_params))
    action_input = {"code": _WORKER_BODY}

    result = apply_worker_create_body_to_scaffold(
        scaffold,
        "create_script",
        action_id="draft_create_body",
        action_input=action_input,
    )

    assert result.applied is True
    assert result.reason is None
    assert result.node_id == "create_script"
    assert result.graph is not scaffold.graph
    assert scaffold.graph == original_graph
    assert _canonical(dict(original_params)) == original_bytes
    returned_params = result.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    assert set(returned_params) == set(original_params) | {"code"}
    assert {
        key: returned_params[key]
        for key in original_params
    } == dict(original_params)
    assert returned_params["code"] == _WORKER_BODY
    assert result.params_sha256 == hashlib.sha256(
        _canonical(dict(returned_params))
    ).hexdigest()
    assert action_input == {"code": _WORKER_BODY}


@pytest.mark.parametrize(
    ("case", "expected_reason"),
    [
        ("expected_template", "invalid_template"),
        ("selected_template", "invalid_template"),
        ("extra_repair_topology", "invalid_template"),
        ("changed_output_pin", "invalid_template"),
        ("changed_initial_status", "invalid_template"),
        ("changed_provider", "invalid_template"),
        ("changed_rules", "invalid_template"),
        ("verifier_node", "invalid_tool_ref"),
        ("unknown_node", "unknown_node"),
        ("wrong_tool", "invalid_tool_ref"),
        ("wrong_action", "invalid_action_id"),
        ("spoofed_action", "invalid_action_id"),
        ("input_list", "invalid_action_input"),
        ("missing_code", "missing_code"),
        ("extra_mode", "unexpected_action_input_key"),
        ("attempt_pin_change", "unexpected_action_input_key"),
        ("blank_code", "invalid_code"),
        ("spoofed_code", "invalid_code"),
        ("code_already_present", "code_already_present"),
        ("missing_original_param", "execution_params_shape_mismatch"),
        ("extra_original_param", "execution_params_shape_mismatch"),
        ("nonmapping_params", "invalid_execution_params"),
    ],
)
def test_applicator_rejects_closed_boundary_mutations(
    case: str,
    expected_reason: str,
):
    scaffold = _scaffold()
    node_id: object = "create_script"
    action_id: object = "draft_create_body"
    action_input: object = {"code": _WORKER_BODY}

    if case == "expected_template":
        scaffold = replace(
            scaffold,
            compile_record=replace(
                scaffold.compile_record,
                expected_template_id="other_template",
            ),
        )
    elif case == "selected_template":
        scaffold = replace(
            scaffold,
            compile_record=replace(
                scaffold.compile_record,
                selected_template_id="other_template",
            ),
        )
    elif case == "extra_repair_topology":
        def add_repair_topology(graph):
            graph.nodes["repair_same_component"] = PlanGraphNode(
                id="repair_same_component",
                intent="Unauthorized repair",
                execution_ref="gh_update_script:v1",
            )
            graph.edges.append(
                PlanGraphEdge(
                    source="verify_create",
                    target="repair_same_component",
                    kind="on_repair",
                )
            )

        scaffold = _replace_graph(scaffold, add_repair_topology)
    elif case == "changed_output_pin":
        params = dict(
            scaffold.graph.nodes["create_script"].metadata[
                EXECUTION_PARAMS_KEY
            ]
        )
        params["pins_out"] = ("B:integer",)
        scaffold = _replace_graph(
            scaffold,
            lambda graph: _set_create_params(graph, params),
        )
    elif case == "changed_initial_status":
        scaffold = _replace_graph(
            scaffold,
            lambda graph: setattr(
                graph.nodes["create_script"],
                "status",
                "pending",
            ),
        )
    elif case == "changed_provider":
        scaffold = replace(
            scaffold,
            provider=replace(
                scaffold.provider,
                terminal_node_ids=frozenset(),
            ),
        )
    elif case == "changed_rules":
        scaffold = replace(scaffold, rules=())
    elif case == "verifier_node":
        node_id = "verify_create"
    elif case == "unknown_node":
        node_id = "absent_from_graph"
    elif case == "wrong_tool":
        scaffold = _replace_graph(
            scaffold,
            lambda graph: setattr(
                graph.nodes["create_script"],
                "execution_ref",
                "gh_update_script:v1",
            ),
        )
    elif case == "wrong_action":
        action_id = "draft_repair_params"
    elif case == "spoofed_action":
        action_id = _EqualitySpoof()
    elif case == "input_list":
        action_input = [_WORKER_BODY]
    elif case == "missing_code":
        action_input = {}
    elif case == "extra_mode":
        action_input = {"code": _WORKER_BODY, "mode": "body"}
    elif case == "attempt_pin_change":
        action_input = {"code": _WORKER_BODY, "pins_out": ["B:integer"]}
    elif case == "blank_code":
        action_input = {"code": "   "}
    elif case == "spoofed_code":
        action_input = {"code": _EqualitySpoof()}
    elif case == "code_already_present":
        params = dict(
            scaffold.graph.nodes["create_script"].metadata[
                EXECUTION_PARAMS_KEY
            ]
        )
        params["code"] = "compiler-owned code"
        scaffold = _replace_graph(
            scaffold,
            lambda graph: _set_create_params(graph, params),
        )
    elif case == "missing_original_param":
        params = dict(
            scaffold.graph.nodes["create_script"].metadata[
                EXECUTION_PARAMS_KEY
            ]
        )
        params.pop("x")
        scaffold = _replace_graph(
            scaffold,
            lambda graph: _set_create_params(graph, params),
        )
    elif case == "extra_original_param":
        params = dict(
            scaffold.graph.nodes["create_script"].metadata[
                EXECUTION_PARAMS_KEY
            ]
        )
        params["language"] = "csharp"
        scaffold = _replace_graph(
            scaffold,
            lambda graph: _set_create_params(graph, params),
        )
    elif case == "nonmapping_params":
        scaffold = _replace_graph(
            scaffold,
            lambda graph: _set_create_params(graph, []),
        )
    else:
        raise AssertionError(f"unknown mutation case: {case}")

    before = copy.deepcopy(scaffold.graph)
    before_action_input = copy.deepcopy(action_input)
    result = apply_worker_create_body_to_scaffold(
        scaffold,
        node_id,
        action_id=action_id,
        action_input=action_input,
    )

    assert result.applied is False
    assert result.reason == expected_reason
    assert result.graph is scaffold.graph
    assert result.node_id == node_id
    assert result.params_sha256 is None
    assert scaffold.graph == before
    assert action_input == before_action_input


def test_applicator_requires_the_exact_scaffold_carrier():
    with pytest.raises(TypeError, match="scaffold must be exact"):
        apply_worker_create_body_to_scaffold(
            object(),
            "create_script",
            action_id="draft_create_body",
            action_input={"code": _WORKER_BODY},
        )


def test_applicator_does_not_mutate_caller_owned_param_values_or_action_mapping():
    scaffold = _scaffold()
    params = scaffold.graph.nodes["create_script"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    pins_in = params["pins_in"]
    pins_out = params["pins_out"]
    action_input = {"code": _WORKER_BODY}
    before_graph = copy.deepcopy(scaffold.graph)
    before_params = _canonical(dict(params))
    before_action = copy.deepcopy(action_input)

    result = apply_worker_create_body_to_scaffold(
        scaffold,
        "create_script",
        action_id="draft_create_body",
        action_input=action_input,
    )

    assert result.applied is True
    assert scaffold.graph == before_graph
    assert _canonical(dict(params)) == before_params
    assert pins_in == ()
    assert pins_out == ("A:double",)
    assert action_input == before_action


def test_applicator_rejects_graph_copy_failure_without_retry(
    monkeypatch: pytest.MonkeyPatch,
):
    scaffold = _scaffold()
    before = copy.deepcopy(scaffold.graph)
    attempts = 0

    def fail_copy(value: object):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("copy failed")

    monkeypatch.setattr(apply_module, "deepcopy", fail_copy)

    result = apply_worker_create_body_to_scaffold(
        scaffold,
        "create_script",
        action_id="draft_create_body",
        action_input={"code": _WORKER_BODY},
    )

    assert result.applied is False
    assert result.reason == "graph_copy_failed"
    assert result.graph is scaffold.graph
    assert result.params_sha256 is None
    assert attempts == 1
    assert scaffold.graph == before
