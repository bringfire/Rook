# LM4U Catalog Current-Step Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a generic catalog-backed current-step provider that feeds LM4S from caller-authored `Step` rules without gaining execution or scheduler authority.

**Architecture:** Create one agent-layer production module, `plan_graph_current_step_provider.py`, that calls LM4N for the current proposal and LM4P for canonical mapping. Add one deterministic test file that pins construction validation, call behavior, metadata, import boundaries, and a full offline LM4T-shaped chain through LM4S.

**Tech Stack:** Python dataclasses, pytest, existing PlanGraph learning/agent primitives, AST import guards.

---

## File Structure

- Create `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`
  - Defines `NodeStepRule`.
  - Defines frozen callable `CatalogCurrentStepProvider`.
  - Imports only LM4N, LM4P, LM4S `EnvelopeSupplyResult`, LM4R `CurrentStepEnvelope`/record types for typing, and LM4M Step types.
- Create `mcp_server/tests/test_plan_graph_current_step_provider.py`
  - Unit tests for static validation and call outcomes.
  - Offline LM4T-shaped chain guard through `run_current_step_stream`.
  - AST/import boundary guard.

No live Rhino test, server wiring, tool registration, template-specific provider factory, or production repair-chain knowledge belongs in LM4U.

---

### Task 1: Provider Unit Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_current_step_provider.py`

- [ ] **Step 1: Add the test file with imports and helpers**

Create `mcp_server/tests/test_plan_graph_current_step_provider.py` with this header and helper block:

```python
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


def _record_for(node_id: str) -> CurrentStepRecord:
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
        supplied_selected_node_id=node_id,
        fresh_selected_node_id=node_id,
        accepted_node_id=node_id,
        mapping_mapped=True,
        mapping_failure=None,
        mapped_step_target=node_id,
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
        bind_node_id=node_id,
        bind_applied=True,
        bind_reason=None,
    )


def _metadata(result: EnvelopeSupplyResult) -> dict:
    assert result.metadata is not None
    return dict(result.metadata)
```

- [ ] **Step 2: Add constructor validation tests**

Append these tests:

```python
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
    ],
    ids=[
        "duplicate-node-id",
        "empty-node-id",
        "empty-steps",
        "target-mismatch",
        "terminal-rule-overlap",
    ],
)
def test_constructor_rejects_invalid_static_config(provider_factory):
    with pytest.raises(ValueError):
        provider_factory()


def test_constructor_rejects_non_step_values_with_type_error():
    with pytest.raises(TypeError):
        CatalogCurrentStepProvider((NodeStepRule("a", (object(),)),))
```

- [ ] **Step 3: Add selector halt and terminal halt tests**

Append these tests:

```python
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
```

- [ ] **Step 4: Add invalid runtime path tests**

Append these tests:

```python
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
```

- [ ] **Step 5: Add supplied mapping and metadata tests**

Append these tests:

```python
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
    second_result = provider(
        _graph(("repair", "ready")),
        (_record_for("repair"),),
        (),
    )

    assert first_result.envelope is not None
    assert first_result.envelope.mapping.step is first
    assert _metadata(first_result)["seen_count"] == 0
    assert _metadata(first_result)["step_kind"] == "bind"
    assert second_result.envelope is not None
    assert second_result.envelope.mapping.step is second
    assert _metadata(second_result)["seen_count"] == 1
    assert _metadata(second_result)["step_kind"] == "producer"
```

- [ ] **Step 6: Run the new tests to verify they fail before implementation**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: collection fails with `ModuleNotFoundError: No module named 'rook.agent.plan_graph_current_step_provider'`.

---

### Task 2: Production Provider Module

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`
- Test: `mcp_server/tests/test_plan_graph_current_step_provider.py`

- [ ] **Step 1: Add the production module**

Create `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`:

```python
"""LM4U catalog-backed current-step provider for LM4S.

The provider is a caller-authored catalog/rule adapter: it proposes via LM4N, maps via
LM4P, and returns LM4S-native EnvelopeSupplyResult values. It does not execute, mutate
graphs, construct Steps, infer node roles, fallback, loop a stream, or apply terminal
nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
)
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
)
from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    Step,
    VerifierStep,
)
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph_selector import (
    NodeSelectionProposal,
    propose_next_node,
)

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


ProviderId = Literal["catalog_current_step_provider:v1"]
StepKind = Literal["producer", "verifier", "bind"]

_PROVIDER_ID: ProviderId = "catalog_current_step_provider:v1"


@dataclass(frozen=True)
class NodeStepRule:
    node_id: str
    steps_by_seen_count: tuple[Step, ...]


@dataclass(frozen=True)
class CatalogCurrentStepProvider:
    rules: tuple[NodeStepRule, ...]
    terminal_node_ids: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for rule in self.rules:
            if not rule.node_id:
                raise ValueError("NodeStepRule.node_id must be non-empty")
            if rule.node_id in seen:
                raise ValueError(f"duplicate NodeStepRule.node_id: {rule.node_id!r}")
            seen.add(rule.node_id)
            if not rule.steps_by_seen_count:
                raise ValueError(
                    f"NodeStepRule.steps_by_seen_count must be non-empty for "
                    f"{rule.node_id!r}"
                )
            for step in rule.steps_by_seen_count:
                if not isinstance(step, (ProducerStep, VerifierStep, BindStep)):
                    raise TypeError(
                        f"steps_by_seen_count for {rule.node_id!r} contains a "
                        "non-Step value"
                    )
                target = _step_target_node_id(step)
                if target != rule.node_id:
                    raise ValueError(
                        f"step for rule {rule.node_id!r} targets {target!r}"
                    )

        overlap = sorted(set(self.terminal_node_ids).intersection(seen))
        if overlap:
            raise ValueError(
                "terminal_node_ids must not also have NodeStepRule entries: "
                + ", ".join(overlap)
            )

    def __call__(
        self,
        current_graph: "PlanGraph",
        records: tuple[CurrentStepRecord, ...],
        supply_records: tuple[EnvelopeSupplyRecord, ...],
    ) -> EnvelopeSupplyResult:
        proposal = propose_next_node(current_graph)

        if proposal.decision == "HALT_NONE_READY":
            return EnvelopeSupplyResult(
                "HALT",
                None,
                "selector_halt:none_ready",
                _metadata(proposal, None, None, None),
            )
        if proposal.decision == "HALT_AMBIGUOUS_READY":
            return EnvelopeSupplyResult(
                "HALT",
                None,
                "selector_halt:ambiguous_ready",
                _metadata(proposal, None, None, None),
            )

        selected = proposal.selected_node_id
        if selected in self.terminal_node_ids:
            return EnvelopeSupplyResult(
                "HALT",
                None,
                f"terminal_node_selected:{selected}",
                _metadata(proposal, None, None, None),
            )

        seen_count = sum(1 for record in records if record.accepted_node_id == selected)
        rule = self._rule_by_node_id().get(selected)
        if rule is None:
            return EnvelopeSupplyResult(
                "SUPPLY",
                None,
                f"no_step_rule_for_node:{selected}",
                _metadata(proposal, seen_count, None, None),
            )
        if seen_count >= len(rule.steps_by_seen_count):
            return EnvelopeSupplyResult(
                "SUPPLY",
                None,
                f"step_rule_exhausted:{selected}:{seen_count}",
                _metadata(proposal, seen_count, len(rule.steps_by_seen_count), None),
            )

        step = rule.steps_by_seen_count[seen_count]
        metadata = _metadata(
            proposal,
            seen_count,
            len(rule.steps_by_seen_count),
            _step_kind(step),
        )
        mapping = map_accepted_proposal_to_step(
            proposal,
            current_graph,
            {selected: step},
        )
        return EnvelopeSupplyResult(
            "SUPPLY",
            CurrentStepEnvelope(mapping, metadata),
            f"selected_node_mapped:{selected}:{seen_count}",
            metadata,
        )

    def _rule_by_node_id(self) -> dict[str, NodeStepRule]:
        return {rule.node_id: rule for rule in self.rules}


def _step_target_node_id(step: Step) -> str:
    if isinstance(step, VerifierStep):
        return step.verifier_node_id
    return step.node_id


def _step_kind(step: Step) -> StepKind:
    if isinstance(step, ProducerStep):
        return "producer"
    if isinstance(step, VerifierStep):
        return "verifier"
    return "bind"


def _metadata(
    proposal: NodeSelectionProposal,
    seen_count: int | None,
    rule_step_count: int | None,
    step_kind: StepKind | None,
) -> Mapping[str, Any]:
    return {
        "provider": _PROVIDER_ID,
        "proposal_decision": proposal.decision,
        "selected_node_id": proposal.selected_node_id,
        "candidate_node_ids": tuple(proposal.candidate_node_ids),
        "ready_count": proposal.ready_count,
        "selector_id": proposal.selector_id,
        "seen_count": seen_count,
        "rule_step_count": rule_step_count,
        "step_kind": step_kind,
    }
```

- [ ] **Step 2: Run provider tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: all tests added in Task 1 pass.

- [ ] **Step 3: Commit provider unit slice**

Run:

```powershell
git add mcp_server/src/rook/agent/plan_graph_current_step_provider.py mcp_server/tests/test_plan_graph_current_step_provider.py
git commit -m "feat(lm4u): add catalog current-step provider"
```

---

### Task 3: Offline Chain Guard and Boundary Tests

**Files:**
- Modify: `mcp_server/tests/test_plan_graph_current_step_provider.py`

- [ ] **Step 1: Add imports for the offline chain guard**

Update the import block in `mcp_server/tests/test_plan_graph_current_step_provider.py` to include these additional imports:

```python
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode
from rook.learning.plan_graph import PlanGraph, PlanGraphNode, initialize_graph
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_templates import select_template
```

Keep the existing `EnvelopeSupplyResult`, `PlanGraph`, and `PlanGraphNode` imports deduplicated.

- [ ] **Step 2: Add fake producer runner and catalog fixtures**

Append this helper block before the tests:

```python
class _FakeRepairRunner(SupportsLiveProducerNode):
    def __init__(self) -> None:
        self.calls: list[tuple[PlanGraph, str]] = []

    async def run_live_producer_node(self, graph: PlanGraph, node_id: str):
        self.calls.append((graph, node_id))
        if node_id == "create_script":
            raw_result = {
                "success": False,
                "data": {
                    "script_receipt": {
                        "version": 1,
                        "operation": "create",
                        "language": "csharp",
                        "artifact_status": "created_with_errors",
                        "mutation": {
                            "status": "created",
                            "component_guid": "component-1",
                        },
                        "verification": {
                            "status": "failed",
                            "target_error_count": 1,
                        },
                        "repair_anchor": {
                            "component_guid": "component-1",
                        },
                    }
                },
            }
            return LiveProducerResult(
                graph=apply_producer_result(graph, node_id, raw_result).graph,
                applied=True,
                node_id=node_id,
                tool_name="gh_create_csharp_script",
                outcome_status="succeeded",
                reason=None,
            )
        if node_id == "repair_same_component":
            raw_result = {
                "success": True,
                "data": {
                    "script_receipt": {
                        "version": 1,
                        "operation": "update",
                        "language": "csharp",
                        "artifact_status": "usable",
                        "mutation": {
                            "status": "updated",
                            "component_guid": "component-1",
                        },
                        "verification": {
                            "status": "passed",
                            "target_error_count": 0,
                        },
                    }
                },
            }
            return LiveProducerResult(
                graph=apply_producer_result(graph, node_id, raw_result).graph,
                applied=True,
                node_id=node_id,
                tool_name="gh_update_script",
                outcome_status="succeeded",
                reason=None,
            )
        raise AssertionError(f"unexpected producer node: {node_id!r}")


def _repair_chain_provider() -> CatalogCurrentStepProvider:
    return CatalogCurrentStepProvider(
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
                        {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
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
        terminal_node_ids=frozenset({"done"}),
    )
```

- [ ] **Step 3: Add the offline chain guard test**

Append this test:

```python
@pytest.mark.asyncio
async def test_offline_repair_chain_provider_feeds_lm4s_trace():
    selection = select_template(
        {
            "domain": "grasshopper",
            "operation": "create_verify_repair_verify",
            "language": "csharp",
        }
    )
    assert selection.graph is not None
    graph = initialize_graph(selection.graph)
    graph.nodes["create_script"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = (
        "artifact_producer"
    )
    graph.nodes["repair_same_component"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = (
        "artifact_producer"
    )
    provider = _repair_chain_provider()
    runner = _FakeRepairRunner()

    result = await run_current_step_stream(
        graph,
        provider,
        max_steps=6,
        runner=runner,
    )

    assert result.stop_reason == "provider_halt"
    assert len(result.records) == 5
    assert len(result.supply_records) == 6
    assert result.steps_attempted == 5

    for index in range(5):
        assert result.supply_records[index].decision == "SUPPLY"
        assert result.supply_records[index].envelope is not None
        assert result.supply_records[index].envelope.mapping is result.records[
            index
        ].mapping
        assert result.supply_records[index].metadata is not None
        assert result.supply_records[index].metadata["provider"] == (
            "catalog_current_step_provider:v1"
        )

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata["selected_node_id"] == "done"
    assert final_supply.metadata["proposal_decision"] == "SELECT_NODE"

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
    assert all(record.ran is True for record in result.records)
    assert all(record.execution_failure is None for record in result.records)
    assert all(record.mapping_mapped is True for record in result.records)
    assert all(record.revalidation.decision == "ACCEPT" for record in result.records)

    bind_record = result.records[2]
    repair_record = result.records[3]
    assert bind_record.accepted_node_id == "repair_same_component"
    assert repair_record.accepted_node_id == "repair_same_component"
    assert bind_record.execution_kind == "bind"
    assert repair_record.execution_kind == "producer"
    assert bind_record.bind_applied is True
    assert result.records[1].verifier_applied is True
    assert result.records[1].verifier_outcome_status == "needs_repair"
    assert result.records[4].verifier_applied is True
    assert result.records[4].verifier_outcome_status == "succeeded"
    assert [node_id for _, node_id in runner.calls] == [
        "create_script",
        "repair_same_component",
    ]
```

- [ ] **Step 4: Add AST/import boundary guard**

Append this test:

```python
def test_import_boundary_and_no_authority_creep():
    tree = ast.parse(pathlib.Path(provider_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    referenced: set[str] = set()
    step_constructor_calls = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
            referenced.update((alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((alias.asname or alias.name) for alias in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr
            else:
                callee_name = None
            if callee_name in {"ProducerStep", "VerifierStep", "BindStep"}:
                step_constructor_calls.append(callee_name)

    assert step_constructor_calls == []
    assert "rook.agent.plan_graph_current_step_runner" in imported
    assert "rook.agent.plan_graph_current_step_stream" in imported
    assert "rook.agent.plan_graph_sequence_runner" in imported
    assert "rook.agent.plan_graph_step_mapping" in imported
    assert "rook.learning.plan_graph_selector" in imported
    assert "rook.learning.plan_graph_revalidation" not in imported
    assert "rook.agent.plan_graph_step_executor" not in imported
    assert "rook.agent.plan_graph_current_step_runner" in imported
    assert not any(module.startswith("rook.server") for module in imported)
    assert not any("dispatch" in module for module in imported)
    assert not any("litellm" in module for module in imported)

    for banned in (
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
    ):
        assert banned not in referenced, banned

    assert "propose_next_node" in referenced
    assert "map_accepted_proposal_to_step" in referenced
    assert "EnvelopeSupplyResult" in referenced
    assert "CurrentStepEnvelope" in referenced
```

- [ ] **Step 5: Run provider tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: all LM4U provider tests pass.

- [ ] **Step 6: Commit chain guard slice**

Run:

```powershell
git add mcp_server/tests/test_plan_graph_current_step_provider.py
git commit -m "test(lm4u): prove catalog provider stream trace"
```

---

### Task 4: Focused Gate and PR

**Files:**
- Review: `mcp_server/src/rook/agent/plan_graph_current_step_provider.py`
- Review: `mcp_server/tests/test_plan_graph_current_step_provider.py`
- Review: `docs/superpowers/specs/2026-06-25-lm4u-catalog-current-step-provider-design.md`
- Create: `docs/superpowers/plans/2026-06-25-lm4u-catalog-current-step-provider.md`

- [ ] **Step 1: Run focused provider tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run focused LM4N-U PlanGraph gate**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_selector.py mcp_server\tests\test_plan_graph_revalidation.py mcp_server\tests\test_plan_graph_step_mapping.py mcp_server\tests\test_plan_graph_step_executor.py mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_provider.py -q
```

Expected: selector, revalidation, mapping, executor, current-step runner, current-step stream, and current-step provider tests pass.

- [ ] **Step 3: Run diff and boundary scans**

Run:

```powershell
git diff --check main..HEAD
git diff --check
rg -n "revalidate_proposal|execute_mapped_step|run_current_mapped_step|run_current_step_stream|run_explicit_sequence|run_live_producer_node|build_live_producer_record|apply_verifier_step|apply_memory_bound_params|apply_outcome|runnable_nodes|select_template|RookAgent|dispatcher|LiteLLM|model" mcp_server\src\rook\agent\plan_graph_current_step_provider.py
```

Expected:

- both `git diff --check` commands produce no output;
- the `rg` scan produces no matches in the production provider module.

- [ ] **Step 4: Confirm branch scope**

Run:

```powershell
git diff --stat main..HEAD
git status --short --branch
```

Expected PR scope:

```text
docs/superpowers/specs/2026-06-25-lm4u-catalog-current-step-provider-design.md
docs/superpowers/plans/2026-06-25-lm4u-catalog-current-step-provider.md
mcp_server/src/rook/agent/plan_graph_current_step_provider.py
mcp_server/tests/test_plan_graph_current_step_provider.py
```

- [ ] **Step 5: Push and open draft PR**

Run:

```powershell
$body = @'
## Summary
- add LM4U catalog-backed current-step provider scaffold for LM4S
- keep provider authority bounded to LM4N proposal + LM4P mapping over caller-authored rules
- add unit coverage and an offline repair-chain stream guard

## Verification
- mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_provider.py -q
- mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_selector.py mcp_server\tests\test_plan_graph_revalidation.py mcp_server\tests\test_plan_graph_step_mapping.py mcp_server\tests\test_plan_graph_step_executor.py mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_stream.py mcp_server\tests\test_plan_graph_current_step_provider.py -q
- git diff --check main..HEAD
- git diff --check
- production provider boundary scan
'@
$bodyPath = Join-Path $env:TEMP 'rook-lm4u-catalog-current-step-provider-pr.md'
Set-Content -Path $bodyPath -Value $body -Encoding UTF8
git push -u origin codex/lm4u-catalog-current-step-provider
gh pr create --draft --title "LM4U catalog current-step provider" --body-file $bodyPath
```

Expected: draft PR opened against `main`; no merge without explicit approval.
