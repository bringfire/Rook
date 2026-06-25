"""LM4U tests for the catalog current-step provider.

The provider is a caller-authored catalog/rule adapter for LM4S. It proposes via LM4N,
maps via LM4P, returns LM4S-native EnvelopeSupplyResult objects, and never executes,
mutates, falls back, constructs Steps, or applies terminal nodes.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import EnvelopeSupplyResult
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(
        nodes={node_id: _node(node_id, status) for node_id, status in id_status}
    )


def _proposal(node_id: str) -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def _accept_revalidation(node_id: str) -> RevalidationResult:
    proposal = _proposal(node_id)
    return RevalidationResult(
        decision="ACCEPT",
        accepted_node_id=node_id,
        reject_reason=None,
        reason="sentinel accept",
        proposal=proposal,
        fresh_proposal=proposal,
        expected_selector_ids=("unique_ready_node:v1",),
    )


def _record_for(
    node_id: str,
    *,
    supplied_selected_node_id: str | None = None,
    fresh_selected_node_id: str | None = None,
    accepted_node_id: str | None = None,
    mapped_step_target: str | None = None,
    bind_node_id: str | None = None,
) -> CurrentStepRecord:
    supplied_selected_node_id = (
        node_id if supplied_selected_node_id is None else supplied_selected_node_id
    )
    fresh_selected_node_id = (
        node_id if fresh_selected_node_id is None else fresh_selected_node_id
    )
    accepted_node_id = node_id if accepted_node_id is None else accepted_node_id
    mapped_step_target = (
        node_id if mapped_step_target is None else mapped_step_target
    )
    bind_node_id = node_id if bind_node_id is None else bind_node_id
    mapping = StepMappingResult(
        mapped=True,
        step=BindStep(node_id=node_id, base_params={}, bindings={}),
        accepted_node_id=node_id,
        failure=None,
        reason="sentinel mapping",
        revalidation=_accept_revalidation(node_id),
    )
    return CurrentStepRecord(
        metadata=None,
        metadata_status="absent",
        metadata_error=None,
        mapping=mapping,
        revalidation=mapping.revalidation,
        execution=None,
        supplied_selected_node_id=supplied_selected_node_id,
        fresh_selected_node_id=fresh_selected_node_id,
        accepted_node_id=accepted_node_id,
        mapping_mapped=True,
        mapping_failure=None,
        mapped_step_target=mapped_step_target,
        ran=True,
        execution_kind="bind",
        execution_failure=None,
        producer_node_id=None,
        producer_tool_name=None,
        producer_applied=None,
        producer_outcome_status=None,
        producer_reason=None,
        verifier_node_id=None,
        verifier_source_node_id=None,
        verifier_applied=None,
        verifier_outcome_status=None,
        verifier_reason=None,
        bind_node_id=bind_node_id,
        bind_applied=True,
        bind_reason=None,
    )


def _metadata(result: EnvelopeSupplyResult) -> dict:
    assert result.metadata is not None
    return dict(result.metadata)


@pytest.mark.parametrize(
    "provider_factory",
    [
        lambda: CatalogCurrentStepProvider(
            (
                NodeStepRule("a", (BindStep("a", {}, {}),)),
                NodeStepRule("a", (ProducerStep("a"),)),
            )
        ),
        lambda: CatalogCurrentStepProvider((NodeStepRule("", (ProducerStep(""),)),)),
        lambda: CatalogCurrentStepProvider((NodeStepRule("a", ()),)),
        lambda: CatalogCurrentStepProvider(
            (NodeStepRule("a", (ProducerStep("b"),)),)
        ),
        lambda: CatalogCurrentStepProvider(
            (NodeStepRule("done", (ProducerStep("done"),)),),
            frozenset({"done"}),
        ),
        lambda: CatalogCurrentStepProvider((), frozenset({""})),
    ],
    ids=[
        "duplicate-node-id",
        "empty-node-id",
        "empty-steps",
        "target-mismatch",
        "terminal-rule-overlap",
        "empty-terminal-node-id",
    ],
)
def test_constructor_rejects_invalid_static_config(provider_factory):
    with pytest.raises(ValueError):
        provider_factory()


def test_constructor_rejects_non_step_values_with_type_error():
    with pytest.raises(TypeError):
        CatalogCurrentStepProvider((NodeStepRule("a", (object(),)),))


def test_constructor_snapshots_mutable_rule_and_terminal_inputs():
    rules = [NodeStepRule("a", (ProducerStep("a"),))]
    terminal_node_ids = set()
    provider = CatalogCurrentStepProvider(rules, terminal_node_ids)

    rules.append(NodeStepRule("b", (ProducerStep("b"),)))
    terminal_node_ids.add("a")

    supplied = provider(_graph(("a", "ready")), (), ())
    missing_rule = provider(_graph(("b", "ready")), (), ())

    assert supplied.reason == "selected_node_mapped:a:0"
    assert missing_rule.reason == "no_step_rule_for_node:b"


def test_node_step_rule_snapshots_mutable_steps_by_seen_count():
    first = ProducerStep("a")
    second = BindStep("a", {}, {})
    steps = [first]
    rule = NodeStepRule("a", steps)
    provider = CatalogCurrentStepProvider((rule,))

    steps.append(second)

    supplied = provider(_graph(("a", "ready")), (), ())
    exhausted = provider(_graph(("a", "ready")), (_record_for("a"),), ())

    assert rule.steps_by_seen_count == (first,)
    assert supplied.envelope is not None
    assert supplied.envelope.mapping.step is first
    assert _metadata(supplied)["rule_step_count"] == 1
    assert exhausted.envelope is None
    assert exhausted.reason == "step_rule_exhausted:a:1"
    assert _metadata(exhausted)["rule_step_count"] == 1


def test_node_step_rule_snapshots_mutable_bind_step_payloads():
    base_params = {
        "operation": "create",
        "nested": {"radius": 2},
        "tags": ["initial"],
    }
    bindings = {"source_id": ["memory", "source_id"]}
    step = BindStep("a", base_params, bindings)
    provider = CatalogCurrentStepProvider((NodeStepRule("a", (step,)),))

    base_params["operation"] = "mutated"
    base_params["nested"]["radius"] = 99
    base_params["tags"].append("late")
    bindings["source_id"].append("late")
    bindings["new_param"] = ["memory", "new"]

    supplied = provider(_graph(("a", "ready")), (), ())

    assert supplied.envelope is not None
    supplied_step = supplied.envelope.mapping.step
    assert supplied_step is step
    assert isinstance(supplied_step, BindStep)
    assert supplied_step.base_params["operation"] == "create"
    assert supplied_step.base_params["nested"]["radius"] == 2
    assert supplied_step.base_params["tags"] == ("initial",)
    assert supplied_step.bindings == {"source_id": ("memory", "source_id")}


def test_node_step_rule_snapshots_nested_set_and_custom_mutable_bind_payloads():
    class MutableValue:
        def __init__(self, values):
            self.values = list(values)

    flags = {"initial"}
    mutable_value = MutableValue(["before"])
    base_params = {
        "nested": {"flags": flags},
        "custom": mutable_value,
    }
    step = BindStep("a", base_params, {})
    provider = CatalogCurrentStepProvider((NodeStepRule("a", (step,)),))

    flags.add("late")
    mutable_value.values.append("after")

    supplied = provider(_graph(("a", "ready")), (), ())

    assert supplied.envelope is not None
    supplied_step = supplied.envelope.mapping.step
    assert supplied_step is step
    assert isinstance(supplied_step, BindStep)
    assert supplied_step.base_params["nested"]["flags"] == frozenset({"initial"})
    assert supplied_step.base_params["custom"].values == ["before"]
    assert supplied_step.base_params["custom"] is not mutable_value


def test_rules_by_node_id_policy_cache_is_immutable():
    provider = CatalogCurrentStepProvider((NodeStepRule("a", (ProducerStep("a"),)),))

    with pytest.raises(TypeError):
        provider._rules_by_node_id["b"] = NodeStepRule("b", (ProducerStep("b"),))


def test_no_ready_selector_halt_is_valid_halt():
    provider = CatalogCurrentStepProvider((NodeStepRule("a", (ProducerStep("a"),)),))

    result = provider(_graph(("a", "pending")), (), ())

    assert result.decision == "HALT"
    assert result.envelope is None
    assert result.reason == "selector_halt:none_ready"
    assert _metadata(result) == {
        "provider": "catalog_current_step_provider:v1",
        "proposal_decision": "HALT_NONE_READY",
        "selected_node_id": None,
        "candidate_node_ids": (),
        "ready_count": 0,
        "selector_id": "unique_ready_node:v1",
        "seen_count": None,
        "rule_step_count": None,
        "step_kind": None,
    }


def test_ambiguous_ready_selector_halt_is_valid_halt():
    provider = CatalogCurrentStepProvider(
        (
            NodeStepRule("a", (ProducerStep("a"),)),
            NodeStepRule("b", (ProducerStep("b"),)),
        )
    )

    result = provider(_graph(("a", "ready"), ("b", "ready")), (), ())

    assert result.decision == "HALT"
    assert result.envelope is None
    assert result.reason == "selector_halt:ambiguous_ready"
    assert _metadata(result)["proposal_decision"] == "HALT_AMBIGUOUS_READY"
    assert _metadata(result)["candidate_node_ids"] == ("a", "b")
    assert _metadata(result)["ready_count"] == 2
    assert _metadata(result)["seen_count"] is None
    assert _metadata(result)["step_kind"] is None


def test_selected_terminal_node_is_valid_halt():
    provider = CatalogCurrentStepProvider((), frozenset({"done"}))

    result = provider(_graph(("done", "ready")), (), ())

    assert result.decision == "HALT"
    assert result.envelope is None
    assert result.reason == "terminal_node_selected:done"
    assert _metadata(result)["proposal_decision"] == "SELECT_NODE"
    assert _metadata(result)["selected_node_id"] == "done"
    assert _metadata(result)["candidate_node_ids"] == ("done",)
    assert _metadata(result)["seen_count"] is None
    assert _metadata(result)["rule_step_count"] is None
    assert _metadata(result)["step_kind"] is None


def test_selected_non_terminal_without_rule_returns_invalid_supply_shape():
    provider = CatalogCurrentStepProvider(())

    result = provider(_graph(("a", "ready")), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == "no_step_rule_for_node:a"
    assert _metadata(result)["selected_node_id"] == "a"
    assert _metadata(result)["seen_count"] == 0
    assert _metadata(result)["rule_step_count"] is None
    assert _metadata(result)["step_kind"] is None


def test_exhausted_repeat_rule_returns_invalid_supply_shape():
    provider = CatalogCurrentStepProvider(
        (NodeStepRule("repair", (BindStep("repair", {}, {}),)),)
    )
    records = (_record_for("repair"),)

    result = provider(_graph(("repair", "ready")), records, ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == "step_rule_exhausted:repair:1"
    assert _metadata(result)["selected_node_id"] == "repair"
    assert _metadata(result)["seen_count"] == 1
    assert _metadata(result)["rule_step_count"] == 1
    assert _metadata(result)["step_kind"] is None


@pytest.mark.parametrize(
    ("step", "expected_kind"),
    [
        (ProducerStep("a"), "producer"),
        (VerifierStep("a", "source"), "verifier"),
        (BindStep("a", {}, {}), "bind"),
    ],
)
def test_supplied_step_maps_through_lm4p_and_metadata_is_observational(
    step, expected_kind
):
    provider = CatalogCurrentStepProvider((NodeStepRule("a", (step,)),))

    result = provider(_graph(("a", "ready")), (), ())

    assert result.decision == "SUPPLY"
    assert result.reason == "selected_node_mapped:a:0"
    assert result.envelope is not None
    assert result.envelope.metadata is result.metadata
    mapping = result.envelope.mapping
    assert isinstance(mapping, StepMappingResult)
    assert mapping.mapped is True
    assert mapping.step is step
    assert mapping.accepted_node_id == "a"
    assert mapping.revalidation.decision == "ACCEPT"
    assert mapping.revalidation.proposal.selected_node_id == "a"
    assert mapping.revalidation.fresh_proposal.selected_node_id == "a"
    metadata = _metadata(result)
    assert metadata == {
        "provider": "catalog_current_step_provider:v1",
        "proposal_decision": "SELECT_NODE",
        "selected_node_id": "a",
        "candidate_node_ids": ("a",),
        "ready_count": 1,
        "selector_id": "unique_ready_node:v1",
        "seen_count": 0,
        "rule_step_count": 1,
        "step_kind": expected_kind,
    }
    assert set(metadata).isdisjoint(
        {"ok", "passed", "completed", "should_continue", "success"}
    )


def test_repeat_rule_uses_prior_accepted_record_count_as_index():
    first = BindStep("repair", {}, {})
    second = ProducerStep("repair")
    provider = CatalogCurrentStepProvider((NodeStepRule("repair", (first, second)),))

    first_result = provider(_graph(("repair", "ready")), (), ())
    misleading_result = provider(
        _graph(("repair", "ready")),
        (
            _record_for(
                "repair",
                supplied_selected_node_id="repair",
                fresh_selected_node_id="repair",
                accepted_node_id="other",
                mapped_step_target="repair",
                bind_node_id="repair",
            ),
        ),
        (),
    )
    second_result = provider(
        _graph(("repair", "ready")),
        (_record_for("repair"),),
        (),
    )

    assert first_result.envelope is not None
    assert first_result.envelope.mapping.step is first
    assert _metadata(first_result)["seen_count"] == 0
    assert _metadata(first_result)["step_kind"] == "bind"
    assert misleading_result.envelope is not None
    assert misleading_result.envelope.mapping.step is first
    assert _metadata(misleading_result)["seen_count"] == 0
    assert _metadata(misleading_result)["step_kind"] == "bind"
    assert second_result.envelope is not None
    assert second_result.envelope.mapping.step is second
    assert _metadata(second_result)["seen_count"] == 1
    assert _metadata(second_result)["step_kind"] == "producer"
