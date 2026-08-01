"""Tests for the Worker-authored initial C# body handoff."""

from __future__ import annotations

from rook.agent.minimal_csharp_initial_body_handoff import (
    _build_initial_body_contract,
)
from rook.agent.minimal_csharp_repair_handoff import (
    ValidatedPlannerDraft,
    load_minimal_csharp_repair_draft,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    compile_workflow_contract,
)


def _valid_draft(
    goal: str = "Create a C# component with one double output and compile cleanly.",
) -> ValidatedPlannerDraft:
    return load_minimal_csharp_repair_draft(
        {
            "goal": goal,
            "capability": "grasshopper_csharp_component",
            "interface": {
                "inputs": [],
                "outputs": [{"name": "A", "type": "double"}],
            },
            "acceptance": "clean_compile_receipt",
        }
    )


def test_builder_compiles_exact_incomplete_create_verify_scaffold():
    contract = _build_initial_body_contract(_valid_draft())
    scaffold = compile_workflow_contract(contract)

    assert scaffold.compile_record.expected_template_id == "gh_csharp_create_verify"
    assert scaffold.compile_record.selected_template_id == "gh_csharp_create_verify"
    assert scaffold.max_steps == 4
    assert tuple(scaffold.graph.nodes) == (
        "create_script",
        "verify_create",
        "done",
    )
    params = scaffold.graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    assert set(params) == {"pins_in", "pins_out", "name", "x", "y"}
    assert params["pins_in"] == ()
    assert params["pins_out"] == ("A:double",)
    assert "code" not in params
    assert "mode" not in params
    assert scaffold.compile_record.expected_refs == (
        ("create_script", "gh_create_csharp_script:v1"),
    )
    assert scaffold.compile_record.step_kinds_by_rule == (
        ("create_script", ("producer",)),
        ("verify_create", ("verifier",)),
    )
    assert all(
        not isinstance(step, BindStepSpec)
        for rule in contract.rules
        for step in rule.steps_by_seen_count
    )


def test_different_goals_do_not_move_compiler_owned_contract_fields():
    first = _build_initial_body_contract(_valid_draft("First goal"))
    second = _build_initial_body_contract(_valid_draft("Second goal"))

    assert first.template == second.template
    assert first.initial_params == second.initial_params
    assert first.rules == second.rules
    assert first.terminal_node_ids == second.terminal_node_ids
    assert first.expected_refs == second.expected_refs
    assert first.max_steps == second.max_steps
    assert first.metadata == second.metadata
