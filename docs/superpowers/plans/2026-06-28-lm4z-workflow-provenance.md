# LM4Z Workflow Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a provenance-aware `EnvelopeSource` wrapper that attaches compact workflow compile identity to LM4S supply records and LM4R current-step records.

**Architecture:** Implement a new tiny bridge module, `plan_graph_workflow_provenance.py`, that consumes `CompiledWorkflowScaffold` and returns a callable `WorkflowProvenanceEnvelopeSource`. The wrapper delegates to an existing `EnvelopeSource`, overlays compile-record provenance into metadata, and never runs, compiles, selects, maps, validates graph state, executes, or mutates a graph.

**Tech Stack:** Python 3 dataclasses, existing PlanGraph workflow contract/compiler APIs, LM4S stream types, pytest, AST boundary tests.

---

## File Structure

- Create: `mcp_server/src/rook/agent/plan_graph_workflow_provenance.py`
  - Public constants for the provenance metadata key and invalid/collision reasons.
  - Public frozen callable dataclass `WorkflowProvenanceEnvelopeSource`.
  - Private helpers for scaffold invariant checks and shallow metadata overlays.
- Create: `mcp_server/tests/test_plan_graph_workflow_provenance.py`
  - Unit tests for constructor validation, delegation, metadata enrichment/refusal, non-result passthrough, exception propagation, mutation isolation, and import/AST boundary.
  - One offline full receipt-chain integration test using the compiled repair workflow and fake producer runner.

No existing production module should be modified. No package-level export should be added.

---

### Task 1: Add Failing LM4Z Provenance Tests

**Files:**
- Create: `mcp_server/tests/test_plan_graph_workflow_provenance.py`

- [ ] **Step 1: Create the dedicated provenance test file**

Add this complete file:

```python
"""LM4Z tests for workflow provenance over current-step envelope sources."""

from __future__ import annotations

import ast
import pathlib
from dataclasses import replace
from typing import Any

import pytest

import rook.agent.plan_graph_workflow_provenance as provenance_module
from rook.agent.plan_graph_current_step_runner import CurrentStepEnvelope
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_sequence_runner import BindStep
from rook.agent.plan_graph_step_mapping import StepMappingResult
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
    load_workflow_contract_payload,
    snapshot_workflow_contract,
)
from rook.agent.plan_graph_workflow_provenance import (
    WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON,
    WORKFLOW_PROVENANCE_METADATA_INVALID_REASON,
    WORKFLOW_PROVENANCE_METADATA_KEY,
    WorkflowProvenanceEnvelopeSource,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_selector import NodeSelectionProposal


_GUID = "lm4z-workflow-provenance-guid"
_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


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
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append(node_id)
        if node_id == "create_script":
            assert graph.nodes["create_script"].execution_ref == (
                "gh_create_csharp_script:v1"
            )
            params = graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
            assert params["pins_out"] == ("A:double",)
            assert params["name"] == "LM4ZWorkflowProvenance"
        elif node_id == "repair_same_component":
            assert graph.nodes["repair_same_component"].execution_ref == (
                "gh_update_script:v1"
            )
        raw = {
            "create_script": _wrapped_failure_create_raw(),
            "repair_same_component": _unwrapped_success_repair_raw(),
        }[node_id]
        tool_name = {
            "create_script": "gh_create_csharp_script",
            "repair_same_component": "gh_update_script",
        }[node_id]
        inner = apply_producer_result(graph, node_id, raw)
        assert inner.graph is not graph
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name=tool_name,
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm4z_repair_contract",
        template=WorkflowTemplateRef(
            descriptor=dict(_DESCRIPTOR),
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                "create_script",
                {
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM4ZWorkflowProvenance",
                    "x": 380,
                    "y": 1120,
                },
            ),
        ),
        rules=(
            WorkflowNodeRule("create_script", (ProducerStepSpec("create_script"),)),
            WorkflowNodeRule(
                "verify_create",
                (
                    VerifierStepSpec(
                        "verify_create",
                        "create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                "repair_same_component",
                (
                    BindStepSpec(
                        "repair_same_component",
                        {
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        {"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStepSpec("repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                "verify_repair",
                (
                    VerifierStepSpec(
                        "verify_repair",
                        "repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=("done",),
        expected_refs=(
            ExpectedNodeRef("create_script", "gh_create_csharp_script:v1"),
            ExpectedNodeRef("repair_same_component", "gh_update_script:v1"),
        ),
        max_steps=6,
        metadata={"trace_id": "lm4z-chain", "workflow": "repair"},
    )


def _compiled_scaffold():
    return compile_workflow_contract(_repair_contract())


@pytest.fixture
def scaffold():
    return _compiled_scaffold()


def _expected_provenance(scaffold) -> dict:
    record = scaffold.compile_record
    return {
        "workflow_id": record.workflow_id,
        "contract_schema": record.contract_schema,
        "contract_fingerprint": record.contract_fingerprint,
        "compiler_id": record.compiler_id,
        "provider_id": record.provider_id,
        "selected_template_id": record.selected_template_id,
    }


def _node(node_id: str, status: str = "ready") -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph() -> PlanGraph:
    return PlanGraph(nodes={"a": _node("a")})


def _proposal(node_id: str = "a") -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def _mapping(node_id: str = "a") -> StepMappingResult:
    proposal = _proposal(node_id)
    revalidation = RevalidationResult(
        decision="ACCEPT",
        accepted_node_id=node_id,
        reject_reason=None,
        reason="sentinel accept",
        proposal=proposal,
        fresh_proposal=proposal,
        expected_selector_ids=("unique_ready_node:v1",),
    )
    return StepMappingResult(
        mapped=True,
        step=BindStep(node_id=node_id, base_params={}, bindings={}),
        accepted_node_id=node_id,
        failure=None,
        reason="hand-built",
        revalidation=revalidation,
    )


def _envelope(metadata: Any | None = None) -> CurrentStepEnvelope:
    return CurrentStepEnvelope(_mapping(), metadata)


def _with_compile_record(scaffold, **changes):
    return replace(
        scaffold,
        compile_record=replace(scaffold.compile_record, **changes),
    )


def test_constructor_defaults_source_to_scaffold_provider(scaffold):
    source = WorkflowProvenanceEnvelopeSource(scaffold)

    assert source.source is scaffold.provider


def test_constructor_rejects_wrong_scaffold_type():
    with pytest.raises(TypeError):
        WorkflowProvenanceEnvelopeSource(object())


def test_constructor_rejects_non_callable_source(scaffold):
    with pytest.raises(TypeError):
        WorkflowProvenanceEnvelopeSource(scaffold, source=object())


@pytest.mark.parametrize(
    "mutate",
    [
        lambda scaffold: _with_compile_record(
            scaffold,
            contract_fingerprint="0" * 64,
        ),
        lambda scaffold: _with_compile_record(
            scaffold,
            contract_schema="rook.workflow_contract:v999",
        ),
        lambda scaffold: replace(scaffold, workflow_id="different_workflow"),
        lambda scaffold: replace(
            scaffold,
            contract_snapshot=replace(
                scaffold.contract_snapshot,
                workflow_id="different_workflow",
            ),
        ),
        lambda scaffold: _with_compile_record(
            scaffold,
            provider_id="wrong_provider:v1",
        ),
    ],
    ids=[
        "fingerprint",
        "schema",
        "workflow-id-scaffold",
        "workflow-id-snapshot",
        "provider-id",
    ],
)
def test_constructor_rejects_inconsistent_scaffold_receipts(scaffold, mutate):
    with pytest.raises(ValueError):
        WorkflowProvenanceEnvelopeSource(mutate(scaffold))


def test_delegates_exact_stream_context_and_enriches_halt(scaffold):
    graph = _graph()
    records = ()
    supply_records = (EnvelopeSupplyRecord("HALT", None, "prior"),)
    calls = []

    def source(current_graph, current_records, current_supply_records):
        calls.append((current_graph, current_records, current_supply_records))
        return EnvelopeSupplyResult("HALT", None, "stop", {"provider": "test"})

    wrapper = WorkflowProvenanceEnvelopeSource(scaffold, source=source)

    result = wrapper(graph, records, supply_records)

    assert calls == [(graph, records, supply_records)]
    assert result.decision == "HALT"
    assert result.envelope is None
    assert result.reason == "stop"
    assert result.metadata["provider"] == "test"
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


def test_enriches_supply_and_envelope_metadata_without_mutating_source(scaffold):
    source_metadata = {"provider": "test", "nested": {"value": 1}}
    envelope_metadata = {"node": "a", "nested": {"value": 2}}
    envelope = _envelope(envelope_metadata)
    delegated = EnvelopeSupplyResult(
        "SUPPLY",
        envelope,
        "selected",
        source_metadata,
    )

    def source(graph, records, supply_records):
        return delegated

    wrapper = WorkflowProvenanceEnvelopeSource(scaffold, source=source)

    result = wrapper(_graph(), (), ())

    assert result is not delegated
    assert result.decision == "SUPPLY"
    assert result.reason == "selected"
    assert result.envelope is not envelope
    assert result.envelope.mapping is envelope.mapping
    assert source_metadata == {"provider": "test", "nested": {"value": 1}}
    assert envelope_metadata == {"node": "a", "nested": {"value": 2}}

    expected = _expected_provenance(scaffold)
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
    assert result.envelope.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] is not (
        result.envelope.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]
    )

    result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]["workflow_id"] = "mutated"
    assert result.envelope.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected


def test_enriches_delegated_invalid_supply_without_envelope(scaffold):
    def source(graph, records, supply_records):
        return EnvelopeSupplyResult(
            "SUPPLY",
            None,
            "no_step_rule_for_node:a",
            {"provider": "test"},
        )

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == "no_step_rule_for_node:a"
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


def test_invalid_halt_with_envelope_preserves_envelope_reference(scaffold):
    envelope = _envelope({"node": "a"})

    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("HALT", envelope, "bad halt", {"provider": "test"})

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "HALT"
    assert result.envelope is envelope
    assert result.envelope.metadata == {"node": "a"}
    assert WORKFLOW_PROVENANCE_METADATA_KEY not in result.envelope.metadata
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


def test_unknown_decision_preserves_envelope_reference(scaffold):
    envelope = _envelope({"node": "a"})

    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("SURPRISE", envelope, "unknown", {"provider": "test"})

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SURPRISE"
    assert result.envelope is envelope
    assert result.envelope.metadata == {"node": "a"}
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )


@pytest.mark.parametrize(
    "metadata,reason,error,collision_key",
    [
        (["bad"], WORKFLOW_PROVENANCE_METADATA_INVALID_REASON, "metadata_invalid", None),
        (
            {WORKFLOW_PROVENANCE_METADATA_KEY: {"fake": True}},
            WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON,
            "metadata_collision",
            WORKFLOW_PROVENANCE_METADATA_KEY,
        ),
    ],
    ids=["invalid", "collision"],
)
def test_refuses_invalid_or_colliding_supply_metadata(
    scaffold,
    metadata,
    reason,
    error,
    collision_key,
):
    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("HALT", None, "stop", metadata)

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == reason
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )
    assert result.metadata["workflow_provenance_error"] == error
    assert result.metadata["workflow_provenance_error_location"] == "supply"
    if collision_key is None:
        assert "workflow_provenance_collision_key" not in result.metadata
    else:
        assert result.metadata["workflow_provenance_collision_key"] == collision_key


@pytest.mark.parametrize(
    "metadata,reason,error,collision_key",
    [
        (["bad"], WORKFLOW_PROVENANCE_METADATA_INVALID_REASON, "metadata_invalid", None),
        (
            {WORKFLOW_PROVENANCE_METADATA_KEY: {"fake": True}},
            WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON,
            "metadata_collision",
            WORKFLOW_PROVENANCE_METADATA_KEY,
        ),
    ],
    ids=["invalid", "collision"],
)
def test_refuses_invalid_or_colliding_envelope_metadata(
    scaffold,
    metadata,
    reason,
    error,
    collision_key,
):
    envelope = _envelope(metadata)

    def source(graph, records, supply_records):
        return EnvelopeSupplyResult("SUPPLY", envelope, "selected", {"provider": "test"})

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result.decision == "SUPPLY"
    assert result.envelope is None
    assert result.reason == reason
    assert result.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == (
        _expected_provenance(scaffold)
    )
    assert result.metadata["workflow_provenance_error"] == error
    assert result.metadata["workflow_provenance_error_location"] == "envelope"
    if collision_key is None:
        assert "workflow_provenance_collision_key" not in result.metadata
    else:
        assert result.metadata["workflow_provenance_collision_key"] == collision_key


def test_passes_non_envelope_supply_result_through_unchanged(scaffold):
    sentinel = object()

    def source(graph, records, supply_records):
        return sentinel

    result = WorkflowProvenanceEnvelopeSource(scaffold, source=source)(_graph(), (), ())

    assert result is sentinel


def test_delegated_source_exceptions_propagate(scaffold):
    def source(graph, records, supply_records):
        raise RuntimeError("source exploded")

    wrapper = WorkflowProvenanceEnvelopeSource(scaffold, source=source)

    with pytest.raises(RuntimeError, match="source exploded"):
        wrapper(_graph(), (), ())


def test_no_public_provenance_property(scaffold):
    wrapper = WorkflowProvenanceEnvelopeSource(scaffold)

    assert not hasattr(wrapper, "provenance")


@pytest.mark.asyncio
async def test_loaded_workflow_stream_records_carry_compile_provenance():
    source_snapshot = snapshot_workflow_contract(_repair_contract())
    loaded = load_workflow_contract_payload(source_snapshot.normalized_contract)
    loaded_snapshot = snapshot_workflow_contract(loaded)
    scaffold = compile_workflow_contract(loaded)
    runner = _OfflineProducerRunner()
    source = WorkflowProvenanceEnvelopeSource(scaffold)

    result = await run_current_step_stream(
        scaffold.graph,
        source,
        max_steps=scaffold.max_steps,
        runner=runner,
    )

    expected = _expected_provenance(scaffold)
    assert loaded_snapshot.contract_fingerprint == source_snapshot.contract_fingerprint
    assert scaffold.contract_snapshot.contract_fingerprint == (
        source_snapshot.contract_fingerprint
    )
    assert result.stop_reason == "provider_halt"
    assert result.steps_attempted == 5
    assert runner.calls == ["create_script", "repair_same_component"]
    assert len(result.records) == 5
    assert len(result.supply_records) == 6
    assert [record.accepted_node_id for record in result.records] == [
        "create_script",
        "verify_create",
        "repair_same_component",
        "repair_same_component",
        "verify_repair",
    ]
    assert [record.execution_kind for record in result.records] == [
        "producer",
        "verifier",
        "bind",
        "producer",
        "verifier",
    ]

    for index, record in enumerate(result.records):
        supply = result.supply_records[index]
        assert supply.decision == "SUPPLY"
        assert supply.envelope is not None
        assert supply.envelope.mapping is record.mapping
        assert supply.metadata is not None
        assert record.metadata is not None
        assert supply.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
        assert record.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
        assert set(
            supply.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]
        ) == set(expected)
        assert set(
            record.metadata[WORKFLOW_PROVENANCE_METADATA_KEY]
        ) == set(expected)
        assert record.ran is True
        assert record.execution_failure is None
        assert record.mapping_mapped is True
        assert record.revalidation.decision == "ACCEPT"

    final_supply = result.supply_records[5]
    assert final_supply.decision == "HALT"
    assert final_supply.envelope is None
    assert final_supply.reason == "terminal_node_selected:done"
    assert final_supply.metadata is not None
    assert final_supply.metadata[WORKFLOW_PROVENANCE_METADATA_KEY] == expected
    assert final_supply.metadata["selected_node_id"] == "done"

    assert result.final_graph.nodes["done"].status == "ready"
    assert result.final_graph.nodes["done"].is_terminal is True


def test_workflow_provenance_module_stays_metadata_bridge_only():
    source = pathlib.Path(provenance_module.__file__).read_text()
    tree = ast.parse(source)

    allowed_imports = {
        "__future__",
        "collections.abc",
        "dataclasses",
        "typing",
        "rook.agent.plan_graph_current_step_provider",
        "rook.agent.plan_graph_current_step_runner",
        "rook.agent.plan_graph_current_step_stream",
        "rook.agent.plan_graph_workflow_contract",
        "rook.learning.plan_graph",
    }
    banned_names = {
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "compile_workflow_contract",
        "snapshot_workflow_contract",
        "load_workflow_contract_payload",
        "run_explicit_sequence",
        "run_live_producer_node",
        "build_live_producer_record",
        "LiveProducerExpectation",
        "LiveProducerRecord",
        "LiveProducerResult",
        "LiveProducerReason",
        "SupportsLiveProducerNode",
        "run_and_record_live_producer_node",
        "apply_outcome",
        "NodeOutcome",
        "RookAgent",
        "dispatcher",
        "base_agent",
        "server",
        "LiteLLM",
        "model",
        "json",
        "yaml",
        "open",
        "Path",
    }

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[-1])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)

    assert imported_modules <= allowed_imports
    assert imported_names.isdisjoint(banned_names)

    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attrs = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }
    assert referenced_names.isdisjoint(banned_names)
    assert referenced_attrs.isdisjoint(banned_names)
```

- [ ] **Step 2: Run the new tests and confirm they fail for the missing module**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_provenance.py -q
```

Expected: collection fails with:

```text
ModuleNotFoundError: No module named 'rook.agent.plan_graph_workflow_provenance'
```

- [ ] **Step 3: Commit failing tests**

```powershell
git add mcp_server/tests/test_plan_graph_workflow_provenance.py
git commit -m "test(lm4z): add workflow provenance source tests"
```

---

### Task 2: Implement Workflow Provenance Envelope Source

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_workflow_provenance.py`

- [ ] **Step 1: Add the new production module**

Create `mcp_server/src/rook/agent/plan_graph_workflow_provenance.py` with this complete content:

```python
"""LM4Z workflow provenance overlay for current-step envelope sources.

This module bridges compiled workflow receipts into LM4S/LM4R metadata only.
It does not run streams, compile contracts, select nodes, map steps, execute
steps, mutate graphs, evaluate results, or apply terminal nodes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_current_step_provider import (
    CATALOG_CURRENT_STEP_PROVIDER_ID,
)
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
)
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSource,
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
)
from rook.agent.plan_graph_workflow_contract import CompiledWorkflowScaffold

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


WORKFLOW_PROVENANCE_METADATA_KEY = "workflow_provenance"
WORKFLOW_PROVENANCE_METADATA_INVALID_REASON = (
    "workflow_provenance_metadata_invalid"
)
WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON = (
    "workflow_provenance_metadata_collision:workflow_provenance"
)

_ERROR_KEY = "workflow_provenance_error"
_ERROR_LOCATION_KEY = "workflow_provenance_error_location"
_COLLISION_KEY = "workflow_provenance_collision_key"


@dataclass(frozen=True)
class WorkflowProvenanceEnvelopeSource:
    scaffold: CompiledWorkflowScaffold
    source: EnvelopeSource | None = None
    _provenance: Mapping[str, Any] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scaffold, CompiledWorkflowScaffold):
            raise TypeError("scaffold must be CompiledWorkflowScaffold")

        source = self.source if self.source is not None else self.scaffold.provider
        if not callable(source):
            raise TypeError("source must be callable")

        _validate_scaffold_receipt(self.scaffold)
        object.__setattr__(self, "source", source)
        object.__setattr__(
            self,
            "_provenance",
            _provenance_payload(self.scaffold),
        )

    def __call__(
        self,
        graph: "PlanGraph",
        records: tuple[CurrentStepRecord, ...],
        supply_records: tuple[EnvelopeSupplyRecord, ...],
    ) -> EnvelopeSupplyResult:
        supplied = self.source(graph, records, supply_records)
        if not isinstance(supplied, EnvelopeSupplyResult):
            return supplied

        supply_metadata, invalid = _merge_metadata(
            supplied.metadata,
            self._provenance,
            location="supply",
        )
        if invalid is not None:
            return invalid

        envelope = supplied.envelope
        if supplied.decision == "SUPPLY" and envelope is not None:
            envelope_metadata, invalid = _merge_metadata(
                envelope.metadata,
                self._provenance,
                location="envelope",
            )
            if invalid is not None:
                return invalid
            envelope = CurrentStepEnvelope(
                mapping=envelope.mapping,
                metadata=envelope_metadata,
            )

        return EnvelopeSupplyResult(
            supplied.decision,
            envelope,
            supplied.reason,
            supply_metadata,
        )


def _validate_scaffold_receipt(scaffold: CompiledWorkflowScaffold) -> None:
    record = scaffold.compile_record
    snapshot = scaffold.contract_snapshot
    if record.contract_fingerprint != snapshot.contract_fingerprint:
        raise ValueError("compile record fingerprint does not match snapshot")
    if record.contract_schema != snapshot.normalized_contract["schema"]:
        raise ValueError("compile record schema does not match snapshot")
    if record.workflow_id != scaffold.workflow_id:
        raise ValueError("compile record workflow_id does not match scaffold")
    if record.workflow_id != snapshot.workflow_id:
        raise ValueError("compile record workflow_id does not match snapshot")
    if record.provider_id != CATALOG_CURRENT_STEP_PROVIDER_ID:
        raise ValueError("compile record provider_id does not match catalog provider")


def _provenance_payload(scaffold: CompiledWorkflowScaffold) -> Mapping[str, Any]:
    record = scaffold.compile_record
    return {
        "workflow_id": record.workflow_id,
        "contract_schema": record.contract_schema,
        "contract_fingerprint": record.contract_fingerprint,
        "compiler_id": record.compiler_id,
        "provider_id": record.provider_id,
        "selected_template_id": record.selected_template_id,
    }


def _merge_metadata(
    metadata: Any,
    provenance: Mapping[str, Any],
    *,
    location: str,
) -> tuple[dict[str, Any], EnvelopeSupplyResult | None]:
    if metadata is None:
        return {WORKFLOW_PROVENANCE_METADATA_KEY: dict(provenance)}, None
    if not isinstance(metadata, Mapping):
        return {}, _invalid_metadata_result(
            provenance,
            error="metadata_invalid",
            location=location,
        )
    if WORKFLOW_PROVENANCE_METADATA_KEY in metadata:
        return {}, _invalid_metadata_result(
            provenance,
            error="metadata_collision",
            location=location,
        )

    merged = dict(metadata)
    merged[WORKFLOW_PROVENANCE_METADATA_KEY] = dict(provenance)
    return merged, None


def _invalid_metadata_result(
    provenance: Mapping[str, Any],
    *,
    error: str,
    location: str,
) -> EnvelopeSupplyResult:
    metadata = {
        WORKFLOW_PROVENANCE_METADATA_KEY: dict(provenance),
        _ERROR_KEY: error,
        _ERROR_LOCATION_KEY: location,
    }
    if error == "metadata_collision":
        metadata[_COLLISION_KEY] = WORKFLOW_PROVENANCE_METADATA_KEY

    reason = (
        WORKFLOW_PROVENANCE_METADATA_COLLISION_REASON
        if error == "metadata_collision"
        else WORKFLOW_PROVENANCE_METADATA_INVALID_REASON
    )
    return EnvelopeSupplyResult("SUPPLY", None, reason, metadata)
```

- [ ] **Step 2: Run the new provenance tests**

Run:

```powershell
pytest mcp_server/tests/test_plan_graph_workflow_provenance.py -q
```

Expected: all tests in the new file pass.

- [ ] **Step 3: Run targeted workflow contract/provenance regression tests**

Run:

```powershell
pytest `
  mcp_server/tests/test_plan_graph_workflow_provenance.py `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  -q
```

Expected: all targeted tests pass.

- [ ] **Step 4: Commit the production module**

```powershell
git add mcp_server/src/rook/agent/plan_graph_workflow_provenance.py
git commit -m "feat(lm4z): attach workflow provenance to envelope sources"
```

---

### Task 3: Final Verification

**Files:**
- No file edits expected.

- [ ] **Step 1: Run targeted LM4Z/LM4Y/LM4X/LM4W tests**

Run:

```powershell
pytest `
  mcp_server/tests/test_plan_graph_workflow_provenance.py `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run focused PlanGraph gate**

Run:

```powershell
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
pytest $files -q
```

Expected: focused PlanGraph gate passes.

- [ ] **Step 3: Run diff and scope guards**

Run:

```powershell
git diff --check main..HEAD
git diff --name-only main..HEAD
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
git diff --name-only main..HEAD -- mcp_server/src/rook/agent | Sort-Object
```

Expected changed files:

```text
docs/superpowers/specs/2026-06-28-lm4z-workflow-provenance-design.md
docs/superpowers/plans/2026-06-28-lm4z-workflow-provenance.md
mcp_server/src/rook/agent/plan_graph_workflow_provenance.py
mcp_server/tests/test_plan_graph_workflow_provenance.py
```

Expected sensitive drift command prints nothing:

```text
git diff --name-only main..HEAD -- base_agent.py knowledge/gh/operations_knowledge.json
```

Expected agent production diff:

```text
mcp_server/src/rook/agent/plan_graph_workflow_provenance.py
```

- [ ] **Step 4: Commit plan correction only if verification required a plan change**

If execution reveals this plan needed correction, commit only the plan correction:

```powershell
git add docs/superpowers/plans/2026-06-28-lm4z-workflow-provenance.md
git commit -m "docs(lm4z): refine workflow provenance plan"
```

If no files changed during verification, do not commit.

---

## Self-Review Checklist

- Spec coverage:
  - new bridge module and dataclass-only callable source: Task 2;
  - public key/reason constants: Task 2;
  - compact provenance from compile record: Task 2 and Task 1 assertions;
  - constructor invariant checks: Task 1 and Task 2;
  - no exception wrapping: Task 1 and Task 2;
  - non-result passthrough: Task 1 and Task 2;
  - supply-first metadata validation: Task 1 invalid metadata tests and Task 2 merge order;
  - envelope enrichment only for valid `SUPPLY` with envelope: Task 1 invalid HALT/unknown tests and Task 2 condition;
  - invalid metadata shape fields: Task 1 tests and Task 2 helper;
  - offline payload/load/snapshot/compile/stream proof: Task 1 integration test;
  - import/runtime boundary: Task 1 AST guard.
- Placeholder scan:
  - no deferred-work markers or unspecified test bodies.
- Type consistency:
  - public class name is `WorkflowProvenanceEnvelopeSource`;
  - public constants match spec strings;
  - no factory function is introduced;
  - no package-level export is introduced;
  - implementation imports only bridge-layer types.

Execution recommendation after plan approval: Subagent-Driven is reasonable because this is the final authority-adjacent LM4 joint, but Inline Execution is also acceptable because the slice is deterministic, test-only plus one tiny module, and no live services are involved.
