# LM4P — Accepted-Selection → Typed Step Mapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agent-layer `map_accepted_proposal_to_step(proposal, graph, step_map, expected_selector_ids)` that delegates to LM4O's `revalidate_proposal` and, only if accepted, looks up the accepted node in a caller-authored `node_id → prebuilt Step` map and returns that exact Step — a gated lookup, never a Step builder.

**Architecture:** One new agent-layer module `agent/plan_graph_step_mapping.py`. Agent-layer is forced: it imports both the LM4M `Step` types (agent) and LM4O `revalidate_proposal` (learning). Pure-of-execution: no dispatch, no loop, no graph mutation, no Step construction, no inference, no fallback. Two test deliverables: unit tests and an offline chain mapping guard. No live test.

**Tech Stack:** Python 3.12, pytest, Rook `agent`/`learning` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4p-accepted-selection-step-mapping-design.md`).

- **Gated lookup, never construct.** LM4P returns the caller's prebuilt `Step` verbatim; it never builds/infers/fills a `Step`. Enforced by an **AST guard that fails on any constructor call to `ProducerStep(...)`/`VerifierStep(...)`/`BindStep(...)`** in the module (isinstance + annotations are allowed).
- **Delegate revalidation to LM4O.** Import `revalidate_proposal`, **not** `propose_next_node` (AST-guarded: `propose_next_node` not referenced). No second/forked re-derivation.
- **No fallback.** A rejected proposal yields no step even when the map holds a valid entry for the now-correct node.
- **Distrust the caller map.** Four distinct failures: `revalidation_rejected`, `no_step_for_node`, `step_map_invalid` (non-`Step` runtime value), `step_node_mismatch` (mapped Step targets a different node). Never crash, never coerce.
- **`step_map_invalid` uses the explicit tuple form** `isinstance(step, (ProducerStep, VerifierStep, BindStep))` — never `isinstance(step, Step)` / never the union alias at runtime — checked *before* the target-node read.
- **Imports:** `revalidate_proposal` + `RevalidationResult` (learning `plan_graph_revalidation`, module-level); `NodeSelectionProposal` (learning `plan_graph_selector`); `Step` + `ProducerStep` + `VerifierStep` + `BindStep` (agent `plan_graph_sequence_runner`); `PlanGraph` `TYPE_CHECKING`-quoted; stdlib `dataclass`/`typing`/`collections.abc`.
  - **Allowed:** importing `rook.agent.plan_graph_sequence_runner` **for the `Step` / `ProducerStep` / `VerifierStep` / `BindStep` types only** (required — LM4P maps into these). The module itself is NOT banned.
  - **Banned (by name, not by module):** live runner / dispatch authority — `run_explicit_sequence`, `run_live_producer_node`, `SupportsLiveProducerNode`; `propose_next_node` (delegate re-derivation to LM4O); `apply_outcome` / `apply_verifier_step` / `apply_producer_result`; `rook.agent.base_agent`, dispatcher/server, LiteLLM/model. The AST guard bans these **names** in `referenced` (and `base_agent`/server/dispatch/litellm as imported modules), never the whole `plan_graph_sequence_runner` module.
- **Pure-of-execution:** never mutates `proposal`, `graph`, or `step_map`; `step` is non-None only on `mapped=True` and is the same object as `step_map[accepted]`; `revalidation` is always populated.
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/agent/plan_graph_step_mapping.py`. No edits to any existing `src/` file; `base_agent.py` byte-stable; LM4M/LM4N/LM4O modules + `plan_graph_walker.py` untouched. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **No live test.** Pure-of-execution; whole-branch diff = spec + plan + 1 module + 2 test files (5 paths).

## Seam reference (already merged — consume, do not modify)

- `revalidate_proposal(proposal, graph, expected_selector_ids=("unique_ready_node:v1",)) -> RevalidationResult` and `RevalidationResult(decision, accepted_node_id, reject_reason, reason, proposal, fresh_proposal, expected_selector_ids)` — `rook.learning.plan_graph_revalidation`. `decision ∈ {"ACCEPT","REJECT"}`; on ACCEPT, `accepted_node_id` is set; reject reasons include `untrusted_selector`, `selected_not_ready`, etc.
- `propose_next_node(graph) -> NodeSelectionProposal` and `NodeSelectionProposal(decision, selected_node_id, candidate_node_ids, ready_count, reason, selector_id)` (frozen) — `rook.learning.plan_graph_selector`. (Used in TESTS to build real proposals; the LM4P module does NOT import `propose_next_node`.)
- `Step = ProducerStep | VerifierStep | BindStep`; `ProducerStep(node_id, expectation=None)`; `VerifierStep(verifier_node_id, source_node_id, expected_outcome=None)`; `BindStep(node_id, base_params, bindings)` — all frozen — `rook.agent.plan_graph_sequence_runner`.
- `PlanGraph`, `PlanGraphNode`, `initialize_graph` — `rook.learning.plan_graph`. `PlanGraphNode(id, intent, status=...)` (status defaults `"pending"`). `PlanGraph(nodes={id: node})`.
- `apply_producer_result(graph, node_id, raw) -> .graph/.outcome_status`; `apply_verifier_step(graph, verifier_node_id, source_node_id) -> .graph/.outcome_status` — `rook.learning.plan_graph_runner`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`. The `gh_csharp_create_verify_repair_verify` template nodes: `create_script`, `verify_create`, `repair_same_component`, `verify_repair`, `done`.

---

### Task 1: Step-mapping module + pure unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_step_mapping.py`
- Create: `mcp_server/src/rook/agent/plan_graph_step_mapping.py`

**Interfaces:**
- Consumes: `revalidate_proposal`/`RevalidationResult` (LM4O), `NodeSelectionProposal` (LM4N), `Step`/`ProducerStep`/`VerifierStep`/`BindStep` (LM4M), `PlanGraph`/`PlanGraphNode` (learning).
- Produces: `StepMappingFailure`, `StepMappingResult(mapped, step, accepted_node_id, failure, reason, revalidation)`, `map_accepted_proposal_to_step(proposal, graph, step_map, expected_selector_ids=("unique_ready_node:v1",)) -> StepMappingResult`. Consumed by Task 2.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_step_mapping.py` with exactly this content:

```python
"""LM4P unit tests for map_accepted_proposal_to_step -- the agent-layer gated lookup that
delegates to LM4O revalidate_proposal and, only if ACCEPTED, returns the caller-authored
prebuilt Step for the accepted node. In the focused PlanGraph gate (test_plan_graph*.py).
Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

import rook.agent.plan_graph_step_mapping as step_mapping
from rook.agent.plan_graph_sequence_runner import BindStep, ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_revalidation import RevalidationResult
from rook.learning.plan_graph_selector import NodeSelectionProposal, propose_next_node


def _node(node_id: str, status: str) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", status=status)


def _graph(*id_status: tuple[str, str]) -> PlanGraph:
    return PlanGraph(nodes={nid: _node(nid, st) for nid, st in id_status})


def _select(node_id: str) -> NodeSelectionProposal:
    return NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id=node_id,
        candidate_node_ids=(node_id,),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="unique_ready_node:v1",
    )


def test_mapped_producer_step():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)  # SELECT_NODE("a")
    step = ProducerStep("a", expectation=None)
    result = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert result.mapped is True
    assert result.step is step  # exact caller object
    assert result.accepted_node_id == "a"
    assert result.failure is None
    assert result.revalidation.decision == "ACCEPT"


def test_mapped_verifier_step_targets_via_verifier_node_id():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    step = VerifierStep(verifier_node_id="a", source_node_id="src")
    result = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert result.mapped is True
    assert result.step is step


def test_mapped_bind_step():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    step = BindStep(node_id="a", base_params={}, bindings={})
    result = map_accepted_proposal_to_step(proposal, graph, {"a": step})
    assert result.mapped is True
    assert result.step is step


def test_revalidation_rejected_stale():
    # Supplied SELECT("a") but the current graph's unique-ready node is "b".
    proposal = _select("a")
    graph = _graph(("a", "succeeded"), ("b", "ready"))
    result = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("a")})
    assert result.mapped is False
    assert result.failure == "revalidation_rejected"
    assert result.step is None
    assert result.accepted_node_id is None
    assert result.revalidation.reject_reason == "selected_not_ready"


def test_revalidation_rejected_untrusted():
    proposal = NodeSelectionProposal(
        decision="SELECT_NODE",
        selected_node_id="a",
        candidate_node_ids=("a",),
        ready_count=1,
        reason="exactly one admissible ready node",
        selector_id="other:v9",
    )
    graph = _graph(("a", "ready"))
    result = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("a")})
    assert result.mapped is False
    assert result.failure == "revalidation_rejected"
    assert result.revalidation.reject_reason == "untrusted_selector"


def test_no_step_for_node():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    result = map_accepted_proposal_to_step(proposal, graph, {})  # no entry for "a"
    assert result.mapped is False
    assert result.failure == "no_step_for_node"
    assert result.accepted_node_id == "a"
    assert result.step is None


def test_step_map_invalid_non_step_value():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    result = map_accepted_proposal_to_step(proposal, graph, {"a": object()})
    assert result.mapped is False
    assert result.failure == "step_map_invalid"
    assert result.step is None
    assert result.accepted_node_id == "a"


def test_step_node_mismatch_producer():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    # The map entry for "a" is a Step that targets a DIFFERENT node "Y".
    result = map_accepted_proposal_to_step(proposal, graph, {"a": ProducerStep("Y")})
    assert result.mapped is False
    assert result.failure == "step_node_mismatch"
    assert result.step is None  # mismatched step is not returned


def test_step_node_mismatch_verifier():
    graph = _graph(("a", "ready"))
    proposal = propose_next_node(graph)
    result = map_accepted_proposal_to_step(
        proposal, graph, {"a": VerifierStep(verifier_node_id="Y", source_node_id="Z")}
    )
    assert result.mapped is False
    assert result.failure == "step_node_mismatch"
    assert result.step is None


def test_revalidate_seam_is_used(monkeypatch):
    # The load-bearing pin: LM4P delegates to LM4O's revalidate_proposal seam and passes
    # through the EXACT (proposal, graph, expected_selector_ids). Patch it to a sentinel
    # ACCEPT; with a matching step_map the run maps, proving the sentinel drove the result.
    received = {}
    supplied = _select("s")
    sentinel = RevalidationResult(
        decision="ACCEPT",
        accepted_node_id="s",
        reject_reason=None,
        reason="sentinel accept",
        proposal=supplied,
        fresh_proposal=supplied,
        expected_selector_ids=("unique_ready_node:v1",),
    )

    def _fake_revalidate(proposal, graph, expected_selector_ids):
        received["args"] = (proposal, graph, expected_selector_ids)
        return sentinel

    monkeypatch.setattr(step_mapping, "revalidate_proposal", _fake_revalidate)
    sentinel_graph = object()  # LM4P must not inspect the graph itself
    step = ProducerStep("s")
    result = map_accepted_proposal_to_step(
        supplied, sentinel_graph, {"s": step}, expected_selector_ids=("unique_ready_node:v1",)
    )
    assert result.mapped is True
    assert result.step is step
    assert result.revalidation is sentinel
    assert received["args"][0] is supplied
    assert received["args"][1] is sentinel_graph
    assert received["args"][2] == ("unique_ready_node:v1",)


def test_frozen_pure_inputs_unchanged():
    graph = _graph(("a", "ready"), ("b", "pending"))
    node_a = graph.nodes["a"]
    before = {nid: n.status for nid, n in graph.nodes.items()}
    proposal = propose_next_node(graph)
    step = ProducerStep("a")
    step_map = {"a": step}
    r1 = map_accepted_proposal_to_step(proposal, graph, step_map)
    r2 = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert {nid: n.status for nid, n in graph.nodes.items()} == before
    assert graph.nodes["a"] is node_a
    assert step_map == {"a": step}
    assert r1 == r2
    assert r1.step is step  # same object, not rebuilt


def test_module_does_not_construct_steps():
    # Containment pin: the module must be LOOKUP-only -- no constructor CALL to a Step type.
    # isinstance(...) uses the classes as args (not a call to them) and annotations are fine.
    import rook.agent.plan_graph_step_mapping as mod

    tree = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    step_ctor_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"ProducerStep", "VerifierStep", "BindStep"}
    ]
    assert step_ctor_calls == [], "LM4P must not construct Steps -- lookup only"


def test_import_boundary():
    import rook.agent.plan_graph_step_mapping as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    imported: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    # Importing plan_graph_sequence_runner for the Step types is REQUIRED and allowed; the
    # guard bans forbidden runner/dispatch NAMES, never that whole module.
    assert "rook.agent.plan_graph_sequence_runner" in imported, imported
    assert "rook.agent.base_agent" not in imported, imported
    assert not any(m.startswith("rook.server") for m in imported), imported
    assert not any("dispatch" in m for m in imported), imported
    assert not any("litellm" in m for m in imported), imported
    for banned in (
        "propose_next_node",
        "run_explicit_sequence",
        "run_live_producer_node",
        "SupportsLiveProducerNode",
        "apply_outcome",
        "apply_verifier_step",
        "apply_producer_result",
    ):
        assert banned not in referenced, banned
```

- [ ] **Step 2: Run the tests to verify they fail (module missing)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_step_mapping.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.plan_graph_step_mapping'`.

- [ ] **Step 3: Write the step-mapping module**

Create `mcp_server/src/rook/agent/plan_graph_step_mapping.py` with exactly this content:

```python
"""LM4P accepted-selection -> typed Step mapper (agent layer).

map_accepted_proposal_to_step delegates to the LM4O distrust gate (revalidate_proposal)
and, ONLY if the proposal is ACCEPTED, looks up the accepted node id in a caller-authored
``step_map`` of prebuilt LM4M Steps and returns that exact Step. It is a GATED LOOKUP, not
a Step builder: it never constructs/infers a Step, never re-derives (it asks LM4O, not the
selector), never dispatches, never loops, never mutates, and never falls back.

Containment (load-bearing):
- lookup, never construct: the module contains NO constructor call to ProducerStep /
  VerifierStep / BindStep (AST-guarded by the tests); it only returns the caller's object.
- delegate revalidation to LM4O: imports revalidate_proposal, NOT propose_next_node.
- no fallback: a rejected proposal yields no step even when ``step_map`` holds a valid entry
  for the node that is now correct.
- distrust the caller map: a missing entry (no_step_for_node), a non-Step value
  (step_map_invalid -- explicit tuple isinstance, checked before any field read), or a Step
  that targets a different node (step_node_mismatch) are each rejected cleanly.

Agent-layer is forced: imports both the LM4M Step types (agent) and LM4O revalidate_proposal
(learning). Pure-of-execution: never mutates proposal/graph/step_map; ``step`` is non-None
only on mapped=True and is the same object as ``step_map[accepted]``. NO base_agent /
dispatcher / server / runner / model import.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_sequence_runner import (
    BindStep,
    ProducerStep,
    Step,
    VerifierStep,
)
from rook.learning.plan_graph_revalidation import RevalidationResult, revalidate_proposal

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph
    from rook.learning.plan_graph_selector import NodeSelectionProposal


StepMappingFailure = Literal[
    "revalidation_rejected",
    "no_step_for_node",
    "step_map_invalid",
    "step_node_mismatch",
]

_DEFAULT_EXPECTED_SELECTOR_IDS = ("unique_ready_node:v1",)


@dataclass(frozen=True)
class StepMappingResult:
    mapped: bool
    step: Step | None
    accepted_node_id: str | None
    failure: StepMappingFailure | None
    reason: str
    revalidation: RevalidationResult


def _step_target_node_id(step: Step) -> str:
    """The node a Step acts on. Runs only after the caller value is confirmed a real Step."""
    if isinstance(step, VerifierStep):
        return step.verifier_node_id
    # ProducerStep and BindStep both carry ``node_id``.
    return step.node_id


def _not_mapped(
    failure: StepMappingFailure,
    reason: str,
    accepted_node_id: str | None,
    revalidation: RevalidationResult,
) -> StepMappingResult:
    return StepMappingResult(
        mapped=False,
        step=None,
        accepted_node_id=accepted_node_id,
        failure=failure,
        reason=reason,
        revalidation=revalidation,
    )


def map_accepted_proposal_to_step(
    proposal: "NodeSelectionProposal",
    graph: "PlanGraph",
    step_map: "Mapping[str, Step]",
    expected_selector_ids: tuple[str, ...] = _DEFAULT_EXPECTED_SELECTOR_IDS,
) -> StepMappingResult:
    """Revalidate ``proposal`` via LM4O, then look up the accepted node in ``step_map``.

    Returns the caller's prebuilt Step verbatim on ACCEPT + a matching, well-formed,
    node-targeted map entry. Otherwise a typed not-mapped result. Never constructs a Step,
    never re-derives, never dispatches, never falls back, never mutates inputs.
    """
    # 1. Delegate distrust + revalidation to LM4O (never re-derive here).
    revalidation = revalidate_proposal(proposal, graph, expected_selector_ids)

    # 2. A rejected proposal yields no step -- no fallback.
    if revalidation.decision != "ACCEPT":
        return _not_mapped(
            "revalidation_rejected",
            f"revalidation rejected the proposal: {revalidation.reject_reason}",
            None,
            revalidation,
        )

    accepted = revalidation.accepted_node_id

    # 3. Look up the accepted node in the caller-authored map -- refuse to invent.
    if accepted not in step_map:
        return _not_mapped(
            "no_step_for_node",
            f"no step_map entry for accepted node {accepted!r}",
            accepted,
            revalidation,
        )

    step = step_map[accepted]

    # 4. Distrust the map value: it must be a real LM4M Step (explicit tuple isinstance,
    #    never the Step union alias at runtime), checked before reading any field.
    if not isinstance(step, (ProducerStep, VerifierStep, BindStep)):
        return _not_mapped(
            "step_map_invalid",
            f"step_map entry for {accepted!r} is not a ProducerStep/VerifierStep/BindStep",
            accepted,
            revalidation,
        )

    # 5. The mapped Step must target the accepted node -- the map cannot redirect execution.
    if _step_target_node_id(step) != accepted:
        return _not_mapped(
            "step_node_mismatch",
            f"mapped step targets {_step_target_node_id(step)!r}, not accepted {accepted!r}",
            accepted,
            revalidation,
        )

    # 6. Gated lookup succeeds: return the caller's exact Step.
    return StepMappingResult(
        mapped=True,
        step=step,
        accepted_node_id=accepted,
        failure=None,
        reason="accepted node mapped to caller-authored step",
        revalidation=revalidation,
    )
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_step_mapping.py -v
```
Expected: all 13 tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected status: `?? mcp_server/src/rook/agent/plan_graph_step_mapping.py` + `?? mcp_server/tests/test_plan_graph_step_mapping.py` (+ spec/plan if uncommitted). The numstat lists only `plan_graph_step_mapping.py`.

Commit:
```
git add mcp_server/src/rook/agent/plan_graph_step_mapping.py mcp_server/tests/test_plan_graph_step_mapping.py
git commit -m "feat(lm4p): accepted-selection -> typed Step mapper + unit tests

map_accepted_proposal_to_step delegates to LM4O revalidate_proposal and, only if ACCEPTED,
returns the caller-authored prebuilt Step for the accepted node (gated lookup, never
construct). Four typed failures: revalidation_rejected / no_step_for_node / step_map_invalid
(explicit tuple isinstance) / step_node_mismatch. No fallback, no dispatch, no mutation;
imports revalidate_proposal NOT propose_next_node. 13 unit tests incl. the no-Step-construction
AST guard, the revalidate seam pin, and the import-boundary guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Chain mapping guard (map fresh, reject stale — no fallback at the mapping layer)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_step_mapping_chain.py`

**Interfaces:**
- Consumes: `map_accepted_proposal_to_step` (Task 1), `ProducerStep`/`VerifierStep` (LM4M), `propose_next_node` (selector), `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_step_mapping_chain.py` with exactly this content:

```python
"""LM4P chain mapping guard -- a fresh proposal maps to the caller's Step for the
uniquely-ready node, and the SAME proposal yields NO step once the graph advances one real
transition (no fallback even though the map holds the now-correct node's Step).

The reducer drives the graph (apply_producer_result / apply_verifier_step); LM4P only
revalidates-then-looks-up. HONEST SCOPE: LM4P returns a Step object; nothing here dispatches
or runs it -- no loop, no graph mutation driven by the mapping. In the focused PlanGraph
gate. Run from repo root. Separate file from test_plan_graph_step_mapping.py.
"""

from __future__ import annotations

from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.learning.plan_graph import initialize_graph
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_selector import propose_next_node
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4p-chain-guid"


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
            node_id="repair_same_component", expectation=None
        ),
    }


def test_map_fresh_then_no_step_for_stale_after_transition():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)

    # Advance so verify_create is uniquely ready.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph

    proposal = propose_next_node(graph)
    assert proposal.selected_node_id == "verify_create"
    step_map = _chain_step_map()

    # Fresh against the same graph -> mapped to the verify_create step.
    mapped = map_accepted_proposal_to_step(proposal, graph, step_map)
    assert mapped.mapped is True
    assert mapped.step is step_map["verify_create"]
    assert mapped.accepted_node_id == "verify_create"

    # Advance one real transition: verify_create -> needs_repair unlocks repair_same_component.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    advanced = step.graph
    assert propose_next_node(advanced).selected_node_id == "repair_same_component"

    # Map the OLD verify_create proposal against the advanced graph -> NO step. No fallback:
    # even though step_map HAS a repair_same_component entry, LM4P returns nothing.
    stale = map_accepted_proposal_to_step(proposal, advanced, step_map)
    assert stale.mapped is False
    assert stale.failure == "revalidation_rejected"
    assert stale.revalidation.reject_reason == "selected_not_ready"
    assert stale.step is None
```

- [ ] **Step 2: Run the test and verify it passes**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_step_mapping_chain.py -v
```
Expected: `1 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_step_mapping_chain.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_step_mapping_chain.py
git commit -m "test(lm4p): chain mapping guard -- map fresh, no step for stale (no fallback)

Drives the real 5-node chain to verify_create uniquely ready; mapping the fresh proposal
returns the caller's verify_create step. After apply_verifier_step advances the graph
(repair_same_component now uniquely ready), mapping the OLD verify_create proposal returns
NO step (revalidation_rejected / selected_not_ready) -- no fallback even though step_map
holds a repair_same_component entry. Honest scope: returns a Step object; nothing dispatches
it.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (whole-branch)

- [ ] **Focused gate green:** PowerShell does not expand the glob; enumerate explicitly:
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_step_mapping.py` (13) and `test_plan_graph_step_mapping_chain.py` (1) — gate rises from the LM4O baseline of 316 by 14 to 330.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/agent/plan_graph_step_mapping.py` and nothing else.

- [ ] **`base_agent.py` byte-stable:**
```
git diff --numstat main...HEAD -- mcp_server/src/rook/agent/base_agent.py
```
Expected: empty (no output).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly five paths — the spec, this plan, the step-mapping module, and the two test files. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- `StepMappingResult` shape + `map_accepted_proposal_to_step` + 4 failure reasons + ACCEPT/mapped → Task 1 module.
- Gate→lookup→validate-map logic order; full delegation to `revalidate_proposal` → Task 1 module + `test_revalidate_seam_is_used`.
- Lookup-only / no Step construction → Task 1 `test_module_does_not_construct_steps` (AST constructor-call ban) + the module containing no Step constructor call.
- Imports `revalidate_proposal` not `propose_next_node`; no agent-runner/dispatcher/server/model/`apply_*` → Task 1 `test_import_boundary`.
- `step_map_invalid` via explicit tuple isinstance before target read → Task 1 module step 4 + `test_step_map_invalid_non_step_value`.
- `step_node_mismatch` (Producer/Bind `.node_id`, Verifier `.verifier_node_id`) → Task 1 `test_step_node_mismatch_producer`/`_verifier`.
- `no_step_for_node`, `revalidation_rejected` (stale + untrusted) → Task 1 dedicated tests.
- No fallback → Task 1 stale test + Task 2 stale-after-transition test.
- frozen/pure, exact-object return → Task 1 `test_frozen_pure_inputs_unchanged`.
- Chain map-fresh-then-reject-stale (deterministic verify_create → repair) → Task 2.
- One-module production diff, `base_agent.py` byte-stable, no live test → Global Constraints + Final verification.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `map_accepted_proposal_to_step(proposal, graph, step_map, expected_selector_ids=("unique_ready_node:v1",)) -> StepMappingResult(.mapped, .step, .accepted_node_id, .failure, .reason, .revalidation)`; `StepMappingFailure` 4-member literal; consumes `revalidate_proposal(...) -> RevalidationResult(.decision, .accepted_node_id, .reject_reason, …)`; `ProducerStep(node_id, expectation=None)` / `VerifierStep(verifier_node_id, source_node_id, expected_outcome=None)` / `BindStep(node_id, base_params, bindings)`; `_step_target_node_id` reads `.verifier_node_id` (VerifierStep) else `.node_id`; `propose_next_node`/`NodeSelectionProposal` used only in tests; `PlanGraphNode(id, intent, status=...)`; `apply_producer_result(...).graph/.outcome_status`; `apply_verifier_step(...).graph/.outcome_status`; `select_template(...).selected_template_id/.graph`. Consistent across both tasks and matching merged modules.
