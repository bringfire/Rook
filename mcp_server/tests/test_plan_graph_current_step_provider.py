"""LM4U tests for the catalog current-step provider.

The provider is a caller-authored catalog/rule adapter for LM4S. It proposes via LM4N,
maps via LM4P, returns LM4S-native EnvelopeSupplyResult objects, and never executes,
mutates, falls back, constructs Steps, or applies terminal nodes.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

import rook.agent.plan_graph_current_step_provider as provider_module
from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph import PlanGraph, PlanGraphNode, initialize_graph
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_selector import NodeSelectionProposal
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4u-current-step-provider-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}


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


def _wrapped_failure_create_raw() -> dict:
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": _GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
            }
        },
    }


def _unwrapped_success_repair_raw() -> dict:
    return {
        "script_receipt": {
            "version": 1,
            "operation": "update",
            "language": "csharp",
            "artifact_status": "usable",
            "mutation": {"status": "written", "component_guid": _GUID},
            "verification": {"status": "passed", "target_error_count": 0},
            "repair_anchor": {"component_guid": _GUID, "language": "csharp"},
        }
    }


class _OfflineProducerRunner:
    def __init__(self, raws: dict[str, dict]) -> None:
        self._raws = raws
        self.calls: list[str] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append(node_id)
        inner = apply_producer_result(graph, node_id, self._raws[node_id])
        tool_name = {
            "create_script": "gh_create_csharp_script",
            "repair_same_component": "gh_update_script",
        }[node_id]
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name=tool_name,
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


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


def test_node_step_rule_rejects_uncopyable_mutable_bind_payloads():
    class UncopyableMutableValue:
        def __init__(self):
            self.values = ["before"]

        def __deepcopy__(self, memo):
            raise RuntimeError("copy denied")

    mutable_value = UncopyableMutableValue()
    step = BindStep("a", {"custom": mutable_value}, {})

    with pytest.raises(TypeError, match="BindStep.base_params"):
        NodeStepRule("a", (step,))


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


@pytest.mark.asyncio
async def test_catalog_provider_runs_full_offline_repair_chain_to_terminal_halt():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    assert selection.graph is not None
    graph = initialize_graph(selection.graph)
    graph.nodes["create_script"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = (
        "artifact_producer"
    )
    graph.nodes["repair_same_component"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = (
        "artifact_producer"
    )

    provider = CatalogCurrentStepProvider(
        (
            NodeStepRule("create_script", (ProducerStep("create_script"),)),
            NodeStepRule(
                "verify_create",
                (
                    VerifierStep(
                        "verify_create",
                        "create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            NodeStepRule(
                "repair_same_component",
                (
                    BindStep(
                        "repair_same_component",
                        _BASE_REPAIR_PARAMS,
                        {"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStep("repair_same_component"),
                ),
            ),
            NodeStepRule(
                "verify_repair",
                (
                    VerifierStep(
                        "verify_repair",
                        "repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        frozenset({"done"}),
    )
    fake_runner = _OfflineProducerRunner(
        {
            "create_script": _wrapped_failure_create_raw(),
            "repair_same_component": _unwrapped_success_repair_raw(),
        }
    )
    runner: SupportsLiveProducerNode = fake_runner

    result = await run_current_step_stream(
        graph,
        provider,
        max_steps=6,
        runner=runner,
    )

    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 5
    assert len(result.records) == 5
    assert len(result.supply_records) == 6
    assert fake_runner.calls == ["create_script", "repair_same_component"]

    expected_nodes = [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
    ]
    expected_kinds = ["producer", "verifier", "bind", "producer", "verifier"]
    assert [record.accepted_node_id for record in result.records] == expected_nodes
    assert [record.execution_kind for record in result.records] == expected_kinds

    for index, record in enumerate(result.records):
        supply = result.supply_records[index]
        assert supply.decision == "SUPPLY"
        assert supply.envelope is not None
        assert supply.envelope.mapping is record.mapping
        assert supply.metadata is not None
        assert supply.metadata["selected_node_id"] == record.accepted_node_id
        assert record.supplied_selected_node_id == record.accepted_node_id
        assert record.fresh_selected_node_id == record.accepted_node_id
        assert record.mapped_step_target == record.accepted_node_id
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"
        assert record.mapping.revalidation is record.revalidation

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata["proposal_decision"] == "SELECT_NODE"
    assert final_supply.metadata["selected_node_id"] == "done"

    create_record = result.records[0]
    assert create_record.producer_node_id == "create_script"
    assert create_record.producer_tool_name == "gh_create_csharp_script"
    assert create_record.producer_applied is True
    assert create_record.producer_outcome_status == "succeeded"

    verify_create_record = result.records[1]
    assert verify_create_record.verifier_node_id == "verify_create"
    assert verify_create_record.verifier_source_node_id == "create_script"
    assert verify_create_record.verifier_applied is True
    assert verify_create_record.verifier_outcome_status == "needs_repair"
    assert verify_create_record.verifier_reason is None
    assert verify_create_record.execution.verifier_result is not None
    assert (
        verify_create_record.verifier_applied
        is verify_create_record.execution.verifier_result.applied
    )
    assert (
        verify_create_record.verifier_outcome_status
        == verify_create_record.execution.verifier_result.outcome_status
    )

    bind_record = result.records[2]
    assert bind_record.bind_node_id == "repair_same_component"
    assert bind_record.bind_applied is True
    assert bind_record.bind_reason is None
    assert bind_record.execution.bind_result is not None
    assert bind_record.bind_applied is bind_record.execution.bind_result.applied
    assert bind_record.bind_reason == bind_record.execution.bind_result.reason
    assert bind_record.execution.bind_result.binding is not None
    assert bind_record.execution.bind_result.binding.params["guid"] == _GUID

    repair_record = result.records[3]
    assert repair_record.producer_node_id == "repair_same_component"
    assert repair_record.producer_tool_name == "gh_update_script"
    assert repair_record.producer_applied is True
    assert repair_record.producer_outcome_status == "succeeded"

    verify_repair_record = result.records[4]
    assert verify_repair_record.verifier_node_id == "verify_repair"
    assert verify_repair_record.verifier_source_node_id == "repair_same_component"
    assert verify_repair_record.verifier_applied is True
    assert verify_repair_record.verifier_outcome_status == "succeeded"
    assert verify_repair_record.verifier_reason is None
    assert verify_repair_record.execution.verifier_result is not None
    assert (
        verify_repair_record.verifier_applied
        is verify_repair_record.execution.verifier_result.applied
    )
    assert (
        verify_repair_record.verifier_outcome_status
        == verify_repair_record.execution.verifier_result.outcome_status
    )

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True


def test_catalog_provider_production_module_stays_at_mapping_boundary():
    source = pathlib.Path(provider_module.__file__).read_text()
    tree = ast.parse(source)

    stdlib_modules = {
        "__future__",
        "collections.abc",
        "copy",
        "dataclasses",
        "types",
        "typing",
    }
    allowed_imports = {
        "rook.agent.plan_graph_current_step_runner": {
            "CurrentStepEnvelope",
            "CurrentStepRecord",
        },
        "rook.agent.plan_graph_current_step_stream": {
            "EnvelopeSupplyRecord",
            "EnvelopeSupplyResult",
        },
        "rook.agent.plan_graph_sequence_runner": {
            "BindStep",
            "ProducerStep",
            "Step",
            "VerifierStep",
        },
        "rook.agent.plan_graph_step_mapping": {"map_accepted_proposal_to_step"},
        "rook.learning.plan_graph_selector": {
            "NodeSelectionProposal",
            "propose_next_node",
        },
        "rook.learning.plan_graph": {"PlanGraph"},
    }
    banned_symbols = {
        "revalidate_proposal",
        "execute_mapped_step",
        "run_current_mapped_step",
        "run_current_step_stream",
        "run_explicit_sequence",
        "run_live_producer_node",
        "build_live_producer_record",
        "apply_verifier_step",
        "apply_memory_bound_params",
        "apply_outcome",
        "runnable_nodes",
        "select_template",
        "RookAgent",
        "dispatcher",
        "base_agent",
        "LiteLLM",
        "model",
        "ok",
        "passed",
        "completed",
        "should_continue",
    }

    imported_names: set[str] = set()
    imported_modules: set[str] = set()
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[-1])
                if alias.name not in stdlib_modules:
                    violations.append(f"unexpected import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.add(module)
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
            if module in stdlib_modules:
                continue
            allowed_names = allowed_imports.get(module)
            if allowed_names is None:
                violations.append(f"unexpected import from {module}")
                continue
            extras = {
                alias.name
                for alias in node.names
                if alias.name not in allowed_names
            }
            if extras:
                violations.append(
                    f"unexpected import from {module}: {sorted(extras)}"
                )

    assert violations == []
    assert imported_names.isdisjoint(banned_symbols)
    assert imported_modules.isdisjoint(banned_symbols)

    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert referenced_names.isdisjoint(banned_symbols)
    assert referenced_attrs.isdisjoint(banned_symbols)

    step_constructor_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called = node.func.id
        elif isinstance(node.func, ast.Attribute):
            called = node.func.attr
        else:
            continue
        if called in {"ProducerStep", "VerifierStep", "BindStep"}:
            step_constructor_calls.append(called)

    assert step_constructor_calls == []
