# LM4R Current-Step Thread-And-Record Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agent-layer `run_current_mapped_step` primitive that consumes one canonical `StepMappingResult`, delegates exactly once to LM4Q, and returns `execution.graph` plus a flattened non-authoritative audit record.

**Architecture:** Create one focused agent module, `rook.agent.plan_graph_current_step_runner`, that preserves canonical `mapping`, `revalidation`, and `execution` objects while flattening nullable observation fields for audit. The module never proposes, revalidates, maps, selects, loops, evaluates, marks terminal nodes, or calls producer/verifier/bind seams directly; it delegates only to `execute_mapped_step`.

**Tech Stack:** Python 3, dataclasses, stdlib `copy.deepcopy`, pytest async tests, existing PlanGraph LM4N/O/P/Q modules.

---

## Scope Check

This plan implements one subsystem: LM4R's current-step thread-and-record primitive. It does not implement a multi-step runner, scheduler, new selector, new mapper, live Rhino acceptance test, PR creation, or merge.

## File Structure

- Create: `mcp_server/src/rook/agent/plan_graph_current_step_runner.py`
  - Owns LM4R dataclasses, metadata snapshot-copy logic, nullable flattening helpers, and `run_current_mapped_step`.
  - Delegates execution to LM4Q `execute_mapped_step`.
  - Uses `ProducerStep` / `VerifierStep` / `BindStep` only for safe target flattening.
- Create: `mcp_server/tests/test_plan_graph_current_step_runner.py`
  - Unit tests for record shape, canonical object preservation, metadata snapshot behavior, nullable observations, refusal recording, and import/authority boundaries.
- Create: `mcp_server/tests/test_plan_graph_current_step_runner_chain.py`
  - Real template chain guard proving fresh current-step artifacts run once, and stale proposals must be re-mapped outside LM4R into a refused `StepMappingResult`.
- Modify: none.

## Preflight

- [ ] **Step 1: Confirm branch and dirty files**

Run:

```powershell
git branch --show-current
git status --short
```

Expected:

```text
codex/lm4r-current-step-record
 M installer/RookSetup.iss
 M scripts/tests/release-installer-guards.tests.ps1
```

If the two unrelated files are present, leave them unstaged and untouched.

---

### Task 1: Current-Step Record Unit Tests And Primitive

**Files:**
- Create: `mcp_server/tests/test_plan_graph_current_step_runner.py`
- Create: `mcp_server/src/rook/agent/plan_graph_current_step_runner.py`

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_current_step_runner.py` with this content:

```python
"""LM4R unit tests for run_current_mapped_step.

LM4R consumes one current-step StepMappingResult, delegates exactly once to LM4Q,
and records a flattened non-authoritative audit record. It does not propose,
revalidate, map, select, loop, evaluate, or mark terminal nodes.
"""

from __future__ import annotations

import ast
import pathlib
from dataclasses import fields

import pytest

import rook.agent.plan_graph_current_step_runner as current_step
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    CurrentStepRecord,
    run_current_mapped_step,
)
from rook.agent.plan_graph_live import LiveProducerResult
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import (
    StepMappingResult,
    map_accepted_proposal_to_step,
)
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={node_id: _node(node_id, status) for node_id, status in id_status})


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


def _reject_revalidation(node_id: str = "a") -> RevalidationResult:
    proposal = _proposal(node_id)
    fresh = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="fresh",
        candidate_node_ids=("fresh",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )
    return RevalidationResult(
        decision="REJECT",
        accepted_node_id=None,
        reject_reason="selected_not_ready",
        reason="a different node is uniquely ready now",
        proposal=proposal,
        fresh_proposal=fresh,
        expected_selector_ids=("unique_ready_node:v1",),
    )


def _hand_mapping(step, accepted: str | None, *, mapped: bool) -> StepMappingResult:
    return StepMappingResult(
        mapped=mapped,
        step=step,
        accepted_node_id=accepted,
        failure=None if mapped else "revalidation_rejected",
        reason="hand-built",
        revalidation=_accept_revalidation(accepted or "a") if mapped else _reject_revalidation(),
    )


class _FakeProducerRunner:
    def __init__(self, result: LiveProducerResult) -> None:
        self.result = result
        self.calls: list[tuple] = []

    async def run_live_producer_node(self, graph, node_id):
        self.calls.append((graph, node_id))
        return self.result


class _Undeepcopyable:
    def __deepcopy__(self, memo):
        raise RuntimeError("cannot deepcopy metadata value")


@pytest.mark.asyncio
async def test_happy_producer_record_preserves_canonical_objects_and_flattens():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    step = ProducerStep("a")
    mapping = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert mapping.mapped is True

    advanced = _graph(("a", "succeeded"))
    producer_result = LiveProducerResult(
        graph=advanced,
        applied=True,
        node_id="a",
        tool_name="gh_create_csharp_script",
        outcome_status="succeeded",
        reason=None,
    )
    runner = _FakeProducerRunner(producer_result)

    metadata = {"trace_id": "lm4r-1", "nested": {"step": 1}}
    result = await run_current_mapped_step(CurrentStepEnvelope(mapping, metadata), graph, runner)

    assert result.graph is result.record.execution.graph
    assert result.graph is advanced
    assert result.record.mapping is mapping
    assert result.record.revalidation is mapping.revalidation
    assert result.record.execution.mapping is mapping
    assert result.record.metadata == {"trace_id": "lm4r-1", "nested": {"step": 1}}
    assert result.record.metadata_status == "copied"
    assert result.record.metadata_error is None
    assert result.record.supplied_selected_node_id == "a"
    assert result.record.fresh_selected_node_id == "a"
    assert result.record.accepted_node_id == "a"
    assert result.record.mapping_mapped is True
    assert result.record.mapping_failure is None
    assert result.record.mapped_step_target == "a"
    assert result.record.ran is True
    assert result.record.execution_kind == "producer"
    assert result.record.execution_failure is None
    assert result.record.producer_node_id == "a"
    assert result.record.producer_tool_name == "gh_create_csharp_script"
    assert result.record.producer_applied is True
    assert result.record.producer_outcome_status == "succeeded"
    assert result.record.producer_reason is None
    assert result.record.verifier_node_id is None
    assert result.record.bind_node_id is None
    assert runner.calls == [(graph, "a")]


@pytest.mark.asyncio
async def test_happy_verifier_record_flattens_verifier_only():
    from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
    from rook.learning.plan_graph_runner import apply_producer_result

    graph = _graph(("a", "ready"), ("v", "ready"))
    graph.nodes["a"].metadata[OUTCOME_PROJECTION_ROLE_KEY] = "artifact_producer"
    raw = {
        "success": True,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": "g"},
                "verification": {"status": "passed", "target_error_count": 0},
            }
        },
    }
    graph = apply_producer_result(graph, "a", raw).graph
    mapping = _hand_mapping(VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is result.record.execution.graph
    assert result.record.metadata is None
    assert result.record.metadata_status == "absent"
    assert result.record.mapped_step_target == "v"
    assert result.record.ran is True
    assert result.record.execution_kind == "verifier"
    assert result.record.verifier_node_id == "v"
    assert result.record.verifier_source_node_id == "a"
    assert result.record.verifier_applied is True
    assert result.record.verifier_outcome_status == "succeeded"
    assert result.record.verifier_reason is None
    assert result.record.producer_node_id is None
    assert result.record.bind_node_id is None


@pytest.mark.asyncio
async def test_happy_bind_record_flattens_bind_only():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is result.record.execution.graph
    assert result.record.mapped_step_target == "a"
    assert result.record.ran is True
    assert result.record.execution_kind == "bind"
    assert result.record.bind_node_id == "a"
    assert result.record.bind_applied is True
    assert result.record.bind_reason is None
    assert result.record.producer_node_id is None
    assert result.record.verifier_node_id is None


@pytest.mark.asyncio
async def test_refused_mapping_still_records_lm4q_not_mapped():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(None, None, mapped=False)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is graph
    assert result.record.execution.graph is graph
    assert result.record.mapping is mapping
    assert result.record.revalidation.reject_reason == "selected_not_ready"
    assert result.record.mapping_mapped is False
    assert result.record.mapping_failure == "revalidation_rejected"
    assert result.record.mapped_step_target is None
    assert result.record.ran is False
    assert result.record.execution_kind is None
    assert result.record.execution_failure == "not_mapped"
    assert result.record.producer_node_id is None
    assert result.record.verifier_node_id is None
    assert result.record.bind_node_id is None


@pytest.mark.asyncio
async def test_forged_malformed_mapping_records_mapping_invalid_without_field_read_crash():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(object(), "a", mapped=True)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.graph is graph
    assert result.record.mapped_step_target is None
    assert result.record.ran is False
    assert result.record.execution_kind is None
    assert result.record.execution_failure == "mapping_invalid"


@pytest.mark.asyncio
async def test_runner_required_refusal_records_without_producer_result():
    graph = _graph(("a", "ready"))
    mapping = _hand_mapping(ProducerStep("a"), "a", mapped=True)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph, runner=None)

    assert result.graph is graph
    assert result.record.ran is False
    assert result.record.execution_kind is None
    assert result.record.execution_failure == "runner_required"
    assert result.record.producer_node_id is None
    assert result.record.producer_tool_name is None


@pytest.mark.asyncio
async def test_native_not_applied_is_recorded_not_reinterpreted():
    graph = _graph(("a", "ready"), ("v", "ready"))
    mapping = _hand_mapping(VerifierStep(verifier_node_id="v", source_node_id="a"), "v", mapped=True)

    result = await run_current_mapped_step(CurrentStepEnvelope(mapping), graph)

    assert result.record.ran is True
    assert result.record.execution_kind == "verifier"
    assert result.record.execution_failure is None
    assert result.record.verifier_applied is False
    assert result.record.verifier_reason == "source_evidence_missing"
    assert not hasattr(result.record, "ok")
    assert not hasattr(result.record, "passed")


@pytest.mark.asyncio
async def test_metadata_snapshot_copy_and_copy_failures_are_observations():
    graph = _graph(("a", "ready"))
    copied_mapping = _hand_mapping(BindStep(node_id="a", base_params={}, bindings={}), "a", mapped=True)
    metadata = {"nested": {"value": 1}}

    copied = await run_current_mapped_step(CurrentStepEnvelope(copied_mapping, metadata), graph)
    metadata["nested"]["value"] = 99
    assert copied.record.metadata == {"nested": {"value": 1}}
    assert copied.record.metadata_status == "copied"

    invalid = await run_current_mapped_step(CurrentStepEnvelope(copied_mapping, ["not", "mapping"]), graph)
    assert invalid.record.metadata is None
    assert invalid.record.metadata_status == "invalid"
    assert invalid.record.metadata_error is None

    bad_metadata = {"bad": _Undeepcopyable()}
    failed = await run_current_mapped_step(CurrentStepEnvelope(copied_mapping, bad_metadata), graph)
    assert failed.record.metadata is None
    assert failed.record.metadata_status == "copy_failed"
    assert "RuntimeError" in failed.record.metadata_error


def test_record_shape_has_no_authority_verdict_fields():
    record_fields = {field.name for field in fields(CurrentStepRecord)}
    assert record_fields.isdisjoint(
        {"ok", "passed", "completed", "should_continue", "graph_status"}
    )


def test_import_boundary_and_no_step_construction():
    tree = ast.parse(pathlib.Path(current_step.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    referenced: set[str] = set()
    constructor_calls = []

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
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"ProducerStep", "VerifierStep", "BindStep"}:
                constructor_calls.append(node.func.id)

    assert constructor_calls == []
    assert "rook.agent.plan_graph_step_mapping" in imported
    assert "rook.agent.plan_graph_step_executor" in imported
    assert "rook.agent.plan_graph_sequence_runner" in imported
    assert "rook.agent.base_agent" not in imported
    assert not any(module.startswith("rook.server") for module in imported)
    assert not any("dispatch" in module for module in imported)
    assert not any("litellm" in module for module in imported)
    for banned in (
        "propose_next_node",
        "revalidate_proposal",
        "map_accepted_proposal_to_step",
        "runnable_nodes",
        "apply_outcome",
        "apply_verifier_step",
        "apply_producer_result",
        "apply_memory_bound_params",
        "run_explicit_sequence",
        "build_live_producer_record",
        "select_template",
    ):
        assert banned not in referenced, banned
```

- [ ] **Step 2: Run the new unit test and verify it fails before the module exists**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_runner.py -q
```

Expected: FAIL during collection with `ModuleNotFoundError: No module named 'rook.agent.plan_graph_current_step_runner'`.

- [ ] **Step 3: Create the LM4R implementation module**

Create `mcp_server/src/rook/agent/plan_graph_current_step_runner.py` with this content:

```python
"""LM4R current-step thread-and-record primitive.

Consumes one canonical StepMappingResult for the current graph snapshot, delegates exactly
once to LM4Q execute_mapped_step, and returns execution.graph plus a flattened
non-authoritative audit record. No selection, revalidation, mapping, sequence fold,
evaluation, fallback, or terminal construction lives here.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from rook.agent.plan_graph_live_runner import SupportsLiveProducerNode
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import StepExecutionResult, execute_mapped_step
from rook.agent.plan_graph_step_mapping import StepMappingResult
from rook.learning.plan_graph_revalidation import RevalidationResult

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


MetadataStatus = Literal["absent", "copied", "invalid", "copy_failed"]


@dataclass(frozen=True)
class CurrentStepEnvelope:
    mapping: StepMappingResult
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class CurrentStepRecord:
    metadata: dict[str, Any] | None
    metadata_status: MetadataStatus
    metadata_error: str | None

    mapping: StepMappingResult
    revalidation: RevalidationResult
    execution: StepExecutionResult

    supplied_selected_node_id: str | None
    fresh_selected_node_id: str | None
    accepted_node_id: str | None
    mapping_mapped: bool
    mapping_failure: str | None
    mapped_step_target: str | None
    ran: bool
    execution_kind: str | None
    execution_failure: str | None

    producer_node_id: str | None
    producer_tool_name: str | None
    producer_applied: bool | None
    producer_outcome_status: str | None
    producer_reason: str | None
    verifier_node_id: str | None
    verifier_source_node_id: str | None
    verifier_applied: bool | None
    verifier_outcome_status: str | None
    verifier_reason: str | None
    bind_node_id: str | None
    bind_applied: bool | None
    bind_reason: str | None


@dataclass(frozen=True)
class CurrentStepResult:
    graph: "PlanGraph"
    record: CurrentStepRecord


def _copy_metadata(metadata: Any) -> tuple[dict[str, Any] | None, MetadataStatus, str | None]:
    if metadata is None:
        return None, "absent", None
    if not isinstance(metadata, Mapping):
        return None, "invalid", None
    try:
        return deepcopy(dict(metadata)), "copied", None
    except Exception as exc:
        return None, "copy_failed", f"{exc.__class__.__name__}: {exc}"


def _mapped_step_target(step: Any) -> str | None:
    if isinstance(step, VerifierStep):
        return step.verifier_node_id
    if isinstance(step, (ProducerStep, BindStep)):
        return step.node_id
    return None


async def run_current_mapped_step(
    envelope: CurrentStepEnvelope,
    graph: "PlanGraph",
    runner: SupportsLiveProducerNode | None = None,
) -> CurrentStepResult:
    """Run one already-mapped current step through LM4Q and record observations.

    The returned graph is exactly ``execution.graph``. The record preserves canonical
    mapping/revalidation/execution objects and flattens nullable observations for audit.
    It does not judge whether the caller should continue.
    """
    metadata, metadata_status, metadata_error = _copy_metadata(envelope.metadata)

    execution = await execute_mapped_step(envelope.mapping, graph, runner)
    mapping = envelope.mapping
    revalidation = mapping.revalidation
    proposal = revalidation.proposal
    fresh = revalidation.fresh_proposal
    producer = execution.producer_result
    verifier = execution.verifier_result
    bind = execution.bind_result

    record = CurrentStepRecord(
        metadata=metadata,
        metadata_status=metadata_status,
        metadata_error=metadata_error,
        mapping=mapping,
        revalidation=revalidation,
        execution=execution,
        supplied_selected_node_id=proposal.selected_node_id,
        fresh_selected_node_id=fresh.selected_node_id if fresh is not None else None,
        accepted_node_id=mapping.accepted_node_id,
        mapping_mapped=mapping.mapped,
        mapping_failure=mapping.failure,
        mapped_step_target=_mapped_step_target(mapping.step),
        ran=execution.ran,
        execution_kind=execution.kind,
        execution_failure=execution.failure,
        producer_node_id=producer.node_id if producer is not None else None,
        producer_tool_name=producer.tool_name if producer is not None else None,
        producer_applied=producer.applied if producer is not None else None,
        producer_outcome_status=producer.outcome_status if producer is not None else None,
        producer_reason=producer.reason if producer is not None else None,
        verifier_node_id=verifier.verifier_node_id if verifier is not None else None,
        verifier_source_node_id=verifier.source_node_id if verifier is not None else None,
        verifier_applied=verifier.applied if verifier is not None else None,
        verifier_outcome_status=verifier.outcome_status if verifier is not None else None,
        verifier_reason=verifier.reason if verifier is not None else None,
        bind_node_id=bind.node_id if bind is not None else None,
        bind_applied=bind.applied if bind is not None else None,
        bind_reason=bind.reason if bind is not None else None,
    )
    return CurrentStepResult(graph=execution.graph, record=record)
```

- [ ] **Step 4: Run the unit test and verify it passes**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_runner.py -q
```

Expected: PASS, with all tests in `test_plan_graph_current_step_runner.py` green.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add mcp_server/src/rook/agent/plan_graph_current_step_runner.py mcp_server/tests/test_plan_graph_current_step_runner.py
git commit -m "feat(lm4r): current-step audit runner"
```

Expected: one commit containing only the new module and unit test.

---

### Task 2: Chain Composition Guard

**Files:**
- Create: `mcp_server/tests/test_plan_graph_current_step_runner_chain.py`

- [ ] **Step 1: Write the chain guard test**

Create `mcp_server/tests/test_plan_graph_current_step_runner_chain.py` with this content:

```python
"""LM4R chain composition guard.

LM4R runs one current mapped step and records it. Freshness stays outside LM4R:
the stale-proposal case is re-run through LM4P outside LM4R to produce a refused
StepMappingResult, which LM4R records without revalidating or substituting.
"""

from __future__ import annotations

import pytest

from rook.agent.plan_graph_current_step_runner import (
    CurrentStepEnvelope,
    run_current_mapped_step,
)
from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4r-chain-guid"


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


def _chain_step_map():
    return {
        "verify_create": VerifierStep(
            verifier_node_id="verify_create",
            source_node_id="create_script",
            expected_outcome="needs_repair",
        ),
        "repair_same_component": ProducerStep(
            node_id="repair_same_component",
            expectation=None,
        ),
    }


@pytest.mark.asyncio
async def test_current_step_runs_once_then_refused_mapping_records_no_fallback():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph

    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "verify_create"
    step_map = _chain_step_map()
    mapping = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert mapping.mapped is True

    result = await run_current_mapped_step(
        CurrentStepEnvelope(mapping, {"trace_id": "lm4r-chain"}),
        graph,
    )
    assert result.record.mapping is mapping
    assert result.record.revalidation is mapping.revalidation
    assert result.record.execution.mapping is mapping
    assert result.graph is result.record.execution.graph
    assert result.record.ran is True
    assert result.record.execution_kind == "verifier"
    assert result.record.verifier_node_id == "verify_create"
    assert result.record.verifier_source_node_id == "create_script"
    assert result.record.verifier_applied is True
    assert result.record.verifier_outcome_status == "needs_repair"
    assert result.record.supplied_selected_node_id == "verify_create"
    assert result.record.fresh_selected_node_id == "verify_create"
    assert result.record.accepted_node_id == "verify_create"
    assert propose_next_node(result.graph).selected_node_id == "repair_same_component"

    advanced = result.graph

    # Freshness stays outside LM4R: re-run the OLD proposal through LM4P against the
    # advanced graph, producing a not-mapped artifact. LM4R only records that artifact.
    stale_mapping = map_accepted_proposal_to_step(proposal, advanced, step_map)
    assert stale_mapping.mapped is False
    assert stale_mapping.revalidation.reject_reason == "selected_not_ready"
    assert stale_mapping.revalidation.fresh_proposal.selected_node_id == "repair_same_component"

    stale_result = await run_current_mapped_step(CurrentStepEnvelope(stale_mapping), advanced)
    assert stale_result.graph is advanced
    assert stale_result.record.execution.graph is advanced
    assert stale_result.record.mapping is stale_mapping
    assert stale_result.record.ran is False
    assert stale_result.record.execution_kind is None
    assert stale_result.record.execution_failure == "not_mapped"
    assert stale_result.record.mapped_step_target is None
    assert stale_result.record.supplied_selected_node_id == "verify_create"
    assert stale_result.record.fresh_selected_node_id == "repair_same_component"
    assert stale_result.record.accepted_node_id is None
    assert stale_result.record.producer_node_id is None
    assert stale_result.record.verifier_node_id is None
    assert stale_result.record.bind_node_id is None
```

- [ ] **Step 2: Run the chain guard**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_runner_chain.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit Task 2**

Run:

```powershell
git add mcp_server/tests/test_plan_graph_current_step_runner_chain.py
git commit -m "test(lm4r): current-step chain guard"
```

Expected: one commit containing only the chain guard test.

---

### Task 3: Focused Gate And Boundary Verification

**Files:**
- Verify: `mcp_server/src/rook/agent/plan_graph_current_step_runner.py`
- Verify: `mcp_server/tests/test_plan_graph_current_step_runner.py`
- Verify: `mcp_server/tests/test_plan_graph_current_step_runner_chain.py`

- [ ] **Step 1: Run the two LM4R test files together**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_plan_graph_current_step_runner.py mcp_server\tests\test_plan_graph_current_step_runner_chain.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the focused PlanGraph gate**

Run:

```powershell
$tests = Get-ChildItem mcp_server\tests -Filter "test_plan_graph*.py" | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest $tests -q
```

Expected: PASS for the full focused PlanGraph gate. The count should be higher than the LM4Q checkpoint of 347 because the two new LM4R test files are included.

- [ ] **Step 3: Verify production diff scope**

Run:

```powershell
git diff --name-only main...HEAD -- mcp_server/src mcp_server/tests docs/superpowers/plans docs/superpowers/specs
```

Expected includes only LM4R files plus the already committed LM4R spec/plan:

```text
docs/superpowers/plans/2026-06-25-lm4r-current-step-thread-record.md
docs/superpowers/specs/2026-06-25-lm4r-current-step-thread-record-design.md
mcp_server/src/rook/agent/plan_graph_current_step_runner.py
mcp_server/tests/test_plan_graph_current_step_runner.py
mcp_server/tests/test_plan_graph_current_step_runner_chain.py
```

- [ ] **Step 4: Confirm unrelated local edits are still untouched**

Run:

```powershell
git status --short
```

Expected may still show these unrelated local modifications, unstaged:

```text
 M installer/RookSetup.iss
 M scripts/tests/release-installer-guards.tests.ps1
```

If those files are present, do not stage, restore, or edit them.

- [ ] **Step 5: Commit verification note only if files changed**

If Task 3 required no file changes, do not make a commit. If a small test or module adjustment was required, stage only LM4R files and commit:

```powershell
git add mcp_server/src/rook/agent/plan_graph_current_step_runner.py mcp_server/tests/test_plan_graph_current_step_runner.py mcp_server/tests/test_plan_graph_current_step_runner_chain.py
git commit -m "test(lm4r): pass focused plangraph gate"
```

Expected: no commit when no files changed; otherwise one commit containing only LM4R implementation/test adjustments.

---

## Self-Review Checklist

Spec coverage:

- One current graph snapshot per call: Task 1 unit tests and Task 2 chain guard.
- Minimal canonical envelope: `CurrentStepEnvelope(mapping, metadata=None)` in Task 1 implementation.
- Metadata snapshot-copy semantics: Task 1 metadata test and `_copy_metadata`.
- Nullable observation-only flattened fields: Task 1 refusal, malformed mapping, and seam-specific tests.
- Canonical object preservation: Task 1 happy producer and Task 2 chain guard.
- `CurrentStepResult.graph is execution.graph`: Task 1 happy producer and Task 2 chain guard.
- No stale-artifact protection inside LM4R: Task 2 explicitly calls LM4P outside LM4R to produce the refused mapping.
- No judgment/verdict fields: Task 1 dataclass field test and implementation.
- No selector/revalidator/mapper/sequence/terminal imports: Task 1 AST guard.
- No live gate required: Task 3 focused deterministic gates.

Type consistency:

- `CurrentStepEnvelope.mapping` uses `StepMappingResult`.
- `CurrentStepRecord.revalidation` uses `RevalidationResult`.
- `CurrentStepRecord.execution` uses `StepExecutionResult`.
- Producer fields match `LiveProducerResult`: `node_id`, `tool_name`, `applied`, `outcome_status`, `reason`.
- Verifier fields match `VerifierStepResult`: `verifier_node_id`, `source_node_id`, `applied`, `outcome_status`, `reason`.
- Bind fields match `MemoryParamApplyResult`: `node_id`, `applied`, `reason`.

Placeholder scan:

- Completed; no unresolved marker text or vague implementation instructions remain.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-25-lm4r-current-step-thread-record.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
