# LM4L — Memory-Backed Execution-Param Applier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an agent-layer applier `apply_memory_bound_params` — the first real consumer of LM4K's pure `bind_params_from_memory` — that sources a named node's producer params from `graph.memory.facts` and stages them onto that node's `metadata["execution_params"]` (copy-on-write), then prove (pure + live) that the staged guid drives a real `gh_update_script` repair.

**Architecture:** One new agent-layer module `agent/plan_graph_param_apply.py`. It calls the pure learning helper (`agent → learning`, one way), and on success writes `node.metadata[EXECUTION_PARAMS_KEY]` for one explicitly-named node on a **deep copy** of the graph; on every failure it returns the input graph unchanged. It does **not** dispatch, select a node, or advance the chain — readiness, role, ref, and dispatchability stay `run_live_producer_node`'s concern. Three test deliverables consume it: unit tests, a pure chain guard (applier replaces LM4K's manual assignment), and a `requires_rhino` live proof.

**Tech Stack:** Python 3.12, pytest (+ `pytest-asyncio`, `requires_rhino`), Rook `learning`/`agent` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4l-memory-backed-param-applier-design.md`).

- **Applier is agent-layer.** Imports `bind_params_from_memory` + `ParamBindingResult` from `rook.learning.plan_graph_param_binding`, and `EXECUTION_PARAMS_KEY` from `rook.agent.plan_graph_live` (single source — **not** redefined). `PlanGraph` is `TYPE_CHECKING`-quoted. **No dispatcher / server / `base_agent` import. No `RookAgent` method.**
- **Copy-on-write graph identity (load-bearing, tested):** success → `result.graph is not graph` (original node has **no** `execution_params`, returned node does); `unknown_node` / `binding_failed` / `graph_copy_failed` → `result.graph is graph` (no copy on failure).
- **Bind on the original, then copy, then stage — never the reverse.** Binding reads the original `graph.memory.facts`; the write lands on the copy.
- **Admissibility = node existence only.** No status / role / ref / dispatchability checks.
- **Reasons:** `unknown_node`, `binding_failed`, `graph_copy_failed` (the impl deep-copies the whole graph, so the honest name is graph-copy, not metadata-copy).
- **LM4K stays pure and untouched.** `bind_params_from_memory` keeps returning params and never writes a node. LM4K's test files are not modified.
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/agent/plan_graph_param_apply.py`. No edits to any existing `src/` file; `base_agent.py` byte-stable. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **No producer ref overrides in the live proof; create params omit `language`;** keep `_ensure_gh_document`; restore `knowledge/gh/operations_knowledge.json` after live runs.
- **Whole-branch diff = spec + plan + 1 module + 3 test files.**

## Seam reference (already merged — consume, do not modify)

- `PlanGraph`, `PlanGraphNode`, `GraphMemory`, `NodeOutcome`, `apply_outcome`, `graph_status`, `initialize_graph` — `rook.learning.plan_graph`. `PlanGraphNode(id, intent, ...)` requires `id` + `intent`; `metadata` defaults to `{}`, `status` to `"pending"`. `PlanGraph(nodes={id: node}, memory=GraphMemory(facts={...}))` constructs a minimal graph.
- `bind_params_from_memory(base_params, graph, bindings) -> ParamBindingResult` (`.params`, `.findings`) — `rook.learning.plan_graph_param_binding` (LM4K, pure).
- `apply_producer_result(graph, node_id, raw_result) -> .applied/.outcome_status/.graph`; `apply_verifier_step(graph, verifier_node_id, source_node_id) -> .applied/.outcome_status/.graph` — `rook.learning.plan_graph_runner`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`.
- `RookAgent(tool_executor=…).run_live_producer_node(graph, node_id) -> LiveProducerResult` (`.graph`, `.tool_name`) — `rook.agent.base_agent`.
- `EXECUTION_PARAMS_KEY` — `rook.agent.plan_graph_live`.
- `build_live_producer_record(result, expectation) -> .evaluated/.passed/.mismatches/.tool_status`; `LiveProducerExpectation(...)` — `rook.agent.plan_graph_live_runner`.
- `_mcp_tool_executor` — `rook.server`. `fresh_document` + `_is_error` — `mcp_server/tests/conftest.py`.

---

### Task 1: Applier module + pure unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_param_apply.py`
- Create: `mcp_server/src/rook/agent/plan_graph_param_apply.py`

**Interfaces:**
- Consumes: `bind_params_from_memory`, `ParamBindingResult` (LM4K), `EXECUTION_PARAMS_KEY`, `PlanGraph`, `PlanGraphNode`, `GraphMemory`.
- Produces: `ApplyReason = Literal["unknown_node", "binding_failed", "graph_copy_failed"]`; `MemoryParamApplyResult(graph, applied, node_id, binding, reason)` (frozen); `apply_memory_bound_params(graph, node_id, base_params, bindings) -> MemoryParamApplyResult`. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_param_apply.py` with exactly this content:

```python
"""LM4L unit tests for apply_memory_bound_params -- the agent-layer applier that stages
memory-sourced params onto ONE named node's execution_params (copy-on-write).

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_param_apply import apply_memory_bound_params
from rook.learning.plan_graph import GraphMemory, PlanGraph, PlanGraphNode


_BASE = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}
_NESTED = {"guid": ("repair_anchor", "component_guid")}


class _NoDeepcopy:
    """A value whose deepcopy raises -- exercises graph_copy_failed."""

    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def _node(node_id: str, **meta) -> PlanGraphNode:
    return PlanGraphNode(id=node_id, intent="x", metadata=dict(meta))


def _graph(nodes, facts) -> PlanGraph:
    return PlanGraph(nodes={n.id: n for n in nodes}, memory=GraphMemory(facts=facts))


def test_success_copy_on_write():
    graph = _graph(
        [_node("repair_same_component")],
        {"repair_anchor": {"component_guid": "GUID-1"}},
    )
    result = apply_memory_bound_params(graph, "repair_same_component", _BASE, _NESTED)
    assert result.applied is True
    assert result.reason is None
    assert result.node_id == "repair_same_component"
    assert result.binding is not None and result.binding.findings == ()
    assert result.binding.params["guid"] == "GUID-1"
    # copy-on-write: new graph object; original node untouched, returned node staged.
    assert result.graph is not graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata
    assert (
        result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == "GUID-1"
    )


def test_unknown_node():
    graph = _graph([_node("repair_same_component")], {"component_guid": "GUID-1"})
    result = apply_memory_bound_params(
        graph, "absent", _BASE, {"guid": ("component_guid",)}
    )
    assert result.applied is False
    assert result.binding is None
    assert result.reason == "unknown_node"
    assert result.node_id == "absent"
    assert result.graph is graph  # no copy on failure


def test_binding_failed_missing_fact():
    graph = _graph(
        [_node("repair_same_component")], {"repair_anchor": {"language": "csharp"}}
    )
    result = apply_memory_bound_params(graph, "repair_same_component", _BASE, _NESTED)
    assert result.applied is False
    assert result.reason == "binding_failed"
    assert result.binding is not None
    assert [f.code for f in result.binding.findings] == ["memory_fact_missing"]
    assert result.graph is graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata


def test_graph_copy_failed():
    # bind reads only memory.facts (succeeds); deepcopy(graph) fails on an UNRELATED node.
    graph = _graph(
        [
            _node("repair_same_component"),
            _node("other", bad=_NoDeepcopy()),
        ],
        {"repair_anchor": {"component_guid": "GUID-1"}},
    )
    result = apply_memory_bound_params(graph, "repair_same_component", _BASE, _NESTED)
    assert result.applied is False
    assert result.reason == "graph_copy_failed"
    assert result.binding is not None and result.binding.findings == ()
    assert result.binding.params["guid"] == "GUID-1"  # binding succeeded before the copy
    assert result.graph is graph
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata


def test_immutability_of_inputs_on_success():
    facts = {"repair_anchor": {"component_guid": "GUID-1"}}
    base = dict(_BASE)
    graph = _graph([_node("repair_same_component")], facts)
    result = apply_memory_bound_params(graph, "repair_same_component", base, _NESTED)
    assert result.applied is True
    # original graph + memory untouched; base untouched.
    assert EXECUTION_PARAMS_KEY not in graph.nodes["repair_same_component"].metadata
    assert graph.memory.facts == {"repair_anchor": {"component_guid": "GUID-1"}}
    assert base == _BASE
    # staged params are independent from memory: mutating them does not touch facts.
    result.graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY][
        "guid"
    ] = "MUTATED"
    assert graph.memory.facts["repair_anchor"]["component_guid"] == "GUID-1"


def test_applier_import_boundary():
    # The applier may import learning + plan_graph_live, but NOT server / base_agent /
    # a dispatcher; and learning's helper must NOT import the applier (agent->learning).
    import rook.agent.plan_graph_param_apply as applier
    import rook.learning.plan_graph_param_binding as helper

    def _imported_modules(path: str) -> set[str]:
        mods: set[str] = set()
        for node in ast.walk(ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                mods.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                mods.add(node.module or "")
        return mods

    applier_imports = _imported_modules(applier.__file__)
    assert not any(m.startswith("rook.server") for m in applier_imports), applier_imports
    assert "rook.agent.base_agent" not in applier_imports, applier_imports
    assert not any("dispatch" in m for m in applier_imports), applier_imports

    helper_imports = _imported_modules(helper.__file__)
    assert "rook.agent.plan_graph_param_apply" not in helper_imports, helper_imports
```

- [ ] **Step 2: Run the tests to verify they fail (module missing)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_param_apply.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.plan_graph_param_apply'`.

- [ ] **Step 3: Write the applier module**

Create `mcp_server/src/rook/agent/plan_graph_param_apply.py` with exactly this content:

```python
"""LM4L memory-backed execution-param applier (agent layer).

First real consumer of LM4K's pure bind_params_from_memory: it sources a node's
producer params from the runtime graph.memory.facts substrate (via the learning helper)
and STAGES them onto one explicitly-named node's metadata["execution_params"].

Copy-on-write: on success it returns a NEW graph (the input is untouched); on every
failure it returns the input graph unchanged (result.graph is graph). It does NOT
dispatch, does NOT select a node, does NOT advance the chain -- readiness, projection
role, execution-ref resolution, and param dispatchability remain run_live_producer_node's
concern.

Boundary: agent -> learning, one way. Imports bind_params_from_memory / ParamBindingResult
from learning and EXECUTION_PARAMS_KEY from plan_graph_live (single source, NOT redefined).
NO dispatcher/server/base_agent import; the applier needs no RookAgent instance state, so
there is no RookAgent method. learning/* never imports this module.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph_param_binding import (
    ParamBindingResult,
    bind_params_from_memory,
)

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


ApplyReason = Literal["unknown_node", "binding_failed", "graph_copy_failed"]


@dataclass(frozen=True)
class MemoryParamApplyResult:
    graph: "PlanGraph"
    applied: bool
    node_id: str
    binding: ParamBindingResult | None
    reason: ApplyReason | None


def apply_memory_bound_params(
    graph: "PlanGraph",
    node_id: str,
    base_params: "Mapping",
    bindings: "Mapping[str, tuple[str, ...]]",
) -> MemoryParamApplyResult:
    """Stage memory-sourced params onto ONE named node's execution_params.

    Copy-on-write: returns a NEW graph with ``node.metadata[EXECUTION_PARAMS_KEY]`` set on
    success; returns the INPUT graph unchanged on every failure (``result.graph is graph``).
    Binds against the ORIGINAL ``graph.memory.facts`` (pure), THEN copies, THEN stages --
    never the reverse. Checks ONLY node existence, binding success, and copy success;
    leaves status / role / ref / dispatchability to ``run_live_producer_node``.
    """
    if node_id not in graph.nodes:
        return MemoryParamApplyResult(
            graph=graph,
            applied=False,
            node_id=node_id,
            binding=None,
            reason="unknown_node",
        )

    binding = bind_params_from_memory(base_params, graph, bindings)
    if binding.findings:
        return MemoryParamApplyResult(
            graph=graph,
            applied=False,
            node_id=node_id,
            binding=binding,
            reason="binding_failed",
        )

    try:
        new_graph = deepcopy(graph)
    except Exception:
        return MemoryParamApplyResult(
            graph=graph,
            applied=False,
            node_id=node_id,
            binding=binding,
            reason="graph_copy_failed",
        )

    # binding.params is a fresh deep-copied dict (LM4K), so assigning it directly creates
    # no aliasing into the caller's graph or into new_graph.memory.
    new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = binding.params
    return MemoryParamApplyResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        binding=binding,
        reason=None,
    )
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_param_apply.py -v
```
Expected: all 6 tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected status: `?? mcp_server/src/rook/agent/plan_graph_param_apply.py` + `?? mcp_server/tests/test_plan_graph_param_apply.py` (+ spec/plan if uncommitted). `operations_knowledge.json` NOT listed. The numstat lists only `plan_graph_param_apply.py`.

Commit:
```
git add mcp_server/src/rook/agent/plan_graph_param_apply.py mcp_server/tests/test_plan_graph_param_apply.py
git commit -m "feat(lm4l): agent-layer apply_memory_bound_params + unit tests

First real consumer of LM4K's pure bind_params_from_memory: sources a named node's
producer params from graph.memory.facts and stages them onto execution_params
(copy-on-write). Success -> new graph; every failure (unknown_node / binding_failed /
graph_copy_failed) -> input graph unchanged. Node-exists-only admissibility, no
dispatch, no RookAgent method, base_agent untouched. 6 unit tests incl. per-outcome
graph identity + import-boundary guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Pure chain guard (applier stages memory-sourced params + composition)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_param_apply_chain.py`

**Interfaces:**
- Consumes: `apply_memory_bound_params` (Task 1), `EXECUTION_PARAMS_KEY`, `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `NodeOutcome`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_param_apply_chain.py` with exactly this content:

```python
"""LM4L pure chain guard -- the APPLIER (apply_memory_bound_params), not the test, stages
the memory-sourced repair guid into execution_params, then the 5-node chain composes to
complete.

HONEST SCOPE: apply_producer_result consumes a RAW tool-result dict, NOT the node's
execution_params. So this guard proves (a) the applier sources the guid from the runtime
memory substrate and writes it into execution_params on a named node, and (b) the graph
still composes to complete. It does NOT prove the staged guid drives a real repair
dispatch -- only the live proof (test_live_repair_chain_param_apply_live.py) does that.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root. Separate file
from test_plan_graph_param_binding_chain.py (LM4K), which stays untouched.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_param_apply import apply_memory_bound_params
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4l-chain-guid"
_BASE_REPAIR_PARAMS = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}


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


def test_applier_stages_memory_sourced_repair_params_then_compose_to_complete():
    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = initialize_graph(selection.graph)
    assert graph.nodes["create_script"].status == "ready"

    # create producer -> memory.facts populated.
    create = apply_producer_result(graph, "create_script", _wrapped_failure_create_raw())
    assert create.outcome_status == "succeeded"
    graph = create.graph
    assert graph.memory.facts["component_guid"] == _GUID

    # verify_create -> needs_repair, unlock repair.
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # The APPLIER stages the memory-sourced repair guid into execution_params (the manual
    # assignment LM4K's chain guard did is now done by the consumer).
    result = apply_memory_bound_params(
        graph,
        "repair_same_component",
        _BASE_REPAIR_PARAMS,
        {"guid": ("repair_anchor", "component_guid")},
    )
    assert result.applied is True
    assert result.reason is None
    assert result.binding is not None and result.binding.params["guid"] == _GUID
    assert result.graph is not graph  # copy-on-write
    graph = result.graph
    assert (
        graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == _GUID
    )

    # repair producer (raw-dict projection) -> succeeded, unlock verify_repair.
    repair = apply_producer_result(
        graph, "repair_same_component", _unwrapped_success_repair_raw()
    )
    assert repair.outcome_status == "succeeded"
    graph = repair.graph
    assert graph.nodes["verify_repair"].status == "ready"

    # verify_repair -> succeeded, unlock done.
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"

    # terminal done -> complete.
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Run the test and verify it passes**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_param_apply_chain.py -v
```
Expected: `1 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_param_apply_chain.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_param_apply_chain.py
git commit -m "test(lm4l): pure chain guard -- applier stages memory-sourced repair params, compose to complete

The applier (apply_memory_bound_params), not the test, sources the repair guid from
graph.memory.facts and writes it into execution_params; the 5-node chain composes to
graph_status==complete. Honest scope: proves memory->params staging + composition, NOT
that the staged guid drives dispatch (apply_producer_result consumes the raw dict).
LM4K's chain guard file is untouched.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Live proof (requires_rhino — applier-staged guid drives the real repair)

**Files:**
- Create: `mcp_server/tests/test_live_repair_chain_param_apply_live.py`

**Interfaces:**
- Consumes: `apply_memory_bound_params` (Task 1), `RookAgent`, `_mcp_tool_executor`, `EXECUTION_PARAMS_KEY`, `select_template`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `NodeOutcome`, `build_live_producer_record`, `LiveProducerExpectation`, `_is_error`, `fresh_document`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_live_repair_chain_param_apply_live.py` with exactly this content:

```python
"""LM4L live proof -- the APPLIER (apply_memory_bound_params), not the test, writes the
repair node's execution_params from graph.memory.facts, and the declared-ref chain (no
producer overrides) drives the real gh_update_script repair to graph_status=="complete".

create.evidence.repair_anchor.component_guid is captured ONLY as a CONTROL: the test
asserts the applier's memory-sourced guid equals it. This is LM4L's delta over LM4K --
the staging assignment moved from the test into the Rook agent-layer applier.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_param_apply_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.agent.plan_graph_param_apply import apply_memory_bound_params
from rook.learning.plan_graph import NodeOutcome, apply_outcome, graph_status
from rook.learning.plan_graph_runner import apply_verifier_step
from rook.learning.plan_graph_templates import select_template
from rook.server import _mcp_tool_executor

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]

_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}


async def _ensure_gh_document() -> None:
    """Establish an ACTIVE Grasshopper document; skip (never silently ignore) when GH
    cannot provide one. The `_Grasshopper` window open is not sufficient, and
    fresh_document resets only the Rhino document."""
    res = await _mcp_tool_executor("gh_document_new", {})
    if _is_error(res) or not isinstance(res, dict):
        pytest.skip(f"Grasshopper document setup unavailable: {res!r}")


async def test_applier_memory_sourced_repair_guid_drives_live_repair(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # No ref override; set ONLY create execution_params directly (author-supplied, not
    # memory-sourced; omit 'language' -- the csharp alias forces it).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4LParamApplyLive",
        "x": 350,
        "y": 880,
    }
    graph.nodes["create_script"].status = "ready"

    agent = RookAgent(tool_executor=_mcp_tool_executor)

    # --- Live dispatch 1: declared-ref create (broken) -> created_with_errors. ---
    create_result = await agent.run_live_producer_node(graph, "create_script")
    assert create_result.tool_name == "gh_create_csharp_script"
    create_record = build_live_producer_record(
        create_result,
        LiveProducerExpectation(
            applied=True,
            outcome_status="succeeded",
            node_status="succeeded",
            tool_status="failed",
            verified=False,
            artifact_status="created_with_errors",
        ),
    )
    assert create_record.evaluated is True
    assert create_record.passed is True, f"mismatches={create_record.mismatches!r}"

    graph = create_result.graph
    assert graph.nodes["verify_create"].status == "ready"

    # CONTROL only: the evidence guid we expect memory to also carry.
    repair_guid_control = graph.nodes["create_script"].evidence.repair_anchor[
        "component_guid"
    ]
    assert isinstance(repair_guid_control, str) and repair_guid_control

    # --- Verifier step -> needs_repair, unlock repair. ---
    step = apply_verifier_step(graph, "verify_create", "create_script")
    assert step.outcome_status == "needs_repair"
    graph = step.graph
    assert graph.nodes["repair_same_component"].status == "ready"

    # --- The APPLIER stages the repair guid FROM graph.memory.facts (not the test). ---
    result = apply_memory_bound_params(
        graph,
        "repair_same_component",
        {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
        {"guid": ("repair_anchor", "component_guid")},
    )
    assert result.applied is True
    assert result.reason is None
    assert result.binding is not None
    assert result.binding.params["guid"] == repair_guid_control  # memory == evidence
    graph = result.graph
    assert (
        graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
        == repair_guid_control
    )

    # --- Live dispatch 2: declared-ref repair, guid staged by the applier -> usable. ---
    repair_result = await agent.run_live_producer_node(graph, "repair_same_component")
    assert repair_result.tool_name == "gh_update_script"
    repair_record = build_live_producer_record(
        repair_result,
        LiveProducerExpectation(
            applied=True,
            outcome_status="succeeded",
            node_status="succeeded",
            verified=True,
            artifact_status="usable",
        ),
    )
    assert repair_record.evaluated is True
    assert repair_record.passed is True, f"mismatches={repair_record.mismatches!r}"
    assert repair_record.tool_status is None  # unwrapped success (LM4I/J finding)

    graph = repair_result.graph
    assert graph.nodes["verify_repair"].status == "ready"

    # --- Verifier step -> succeeded, unlock done; terminal -> complete. ---
    step = apply_verifier_step(graph, "verify_repair", "repair_same_component")
    assert step.outcome_status == "succeeded"
    graph = step.graph
    assert graph.nodes["done"].status == "ready"
    graph = apply_outcome(graph, "done", NodeOutcome(status="succeeded"))
    assert graph_status(graph) == "complete"
```

- [ ] **Step 2: Verify collection + import (Rhino-independent)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_live_repair_chain_param_apply_live.py --collect-only -q
```
Expected: collects `test_applier_memory_sourced_repair_guid_drives_live_repair` with no import errors.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_live_repair_chain_param_apply_live.py` (+ spec/plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_live_repair_chain_param_apply_live.py
git commit -m "test(lm4l): live proof -- applier-staged memory-sourced guid drives live gh_update_script

Declared-ref chain (no overrides); after live create, the agent-layer applier
(apply_memory_bound_params) -- not the test -- sources the repair guid from
graph.memory.facts and writes it into execution_params, with create.evidence as a
control assertion (memory==evidence). The live gh_update_script repair drives the chain
to complete; repair_record.tool_status is None (unwrapped-success finding) preserved.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Live acceptance (run only with Rhino + Grasshopper open)** — PAUSE POINT

Authoritative live proof, run during a live acceptance pass. Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_param_apply_live.py -v
```
Expected: `1 passed`. Creates a `LM4LParamApplyLive` C# component via the declared ref, repairs it with the **applier-staged, memory-sourced** guid, drives to `complete`. Mutates `knowledge/gh/operations_knowledge.json`.

**If it fails:** capture the exact assertion + `create_record.mismatches` / `repair_record.mismatches` / `result.reason` / `result.binding.findings` and report; do NOT weaken the test.

After the live run, restore the runtime mutation:
```
git restore knowledge/gh/operations_knowledge.json
git status --short
```
Expected after restore: clean (or only intended files).

---

## Final verification (whole-branch)

- [ ] **Focused gate green (Rhino-independent):** PowerShell does not expand the glob; enumerate explicitly:
```
$files = Get-ChildItem mcp_server/tests -Filter 'test_plan_graph*.py' | ForEach-Object { $_.FullName }
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider @files -q
```
Expected: all pass, including `test_plan_graph_param_apply.py` (6) and `test_plan_graph_param_apply_chain.py` (1) — gate rises from the LM4K baseline of 273 by 7 to 280.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/agent/plan_graph_param_apply.py` and nothing else.

- [ ] **`base_agent.py` byte-stable:**
```
git diff --numstat main...HEAD -- mcp_server/src/rook/agent/base_agent.py
```
Expected: empty (no output).

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly six paths — the spec, this plan, the applier module, and the three test files. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- Applier contract (signature, copy-on-write, node-exists-only admissibility, no dispatch, no `RookAgent` method) → Task 1 module + unit tests.
- Per-outcome graph identity (§6 of the spec) → Task 1: `test_success_copy_on_write` (`result.graph is not graph`), `test_unknown_node` / `test_binding_failed_missing_fact` / `test_graph_copy_failed` (`result.graph is graph`).
- All three reasons → Task 1: `unknown_node`, `binding_failed` (via `memory_fact_missing`), `graph_copy_failed` (via `_NoDeepcopy` planted in an unrelated node so bind still succeeds).
- Reuse of `ParamBindingResult` / `ParamBindingFinding` → Task 1 asserts on `result.binding.findings` / `result.binding.params`.
- Import boundary (no server / base_agent / dispatcher; learning does not import the applier) → Task 1 `test_applier_import_boundary` (AST-based, examines imported modules only).
- Pure chain guard, applier replaces LM4K's manual assignment, honest scope → Task 2 (docstring + comment).
- Live proof, applier writes the repair node's `execution_params`, evidence as control, no overrides, omit `language`, `tool_status is None` → Task 3.
- One-module production diff, `base_agent.py` byte-stable, restore `operations_knowledge.json` → Global Constraints + Final verification + Task 3.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `apply_memory_bound_params(graph, node_id, base_params, bindings) -> MemoryParamApplyResult(.graph, .applied, .node_id, .binding, .reason)`; `ApplyReason ∈ {"unknown_node","binding_failed","graph_copy_failed"}`; `.binding` is a `ParamBindingResult(.params, .findings)`; `ParamBindingFinding(.code, …)`; `PlanGraphNode(id, intent, metadata=…)`; `apply_producer_result(...).outcome_status/.graph`; `apply_verifier_step(...).outcome_status/.graph`; `select_template(...).selected_template_id/.graph`; `RookAgent(tool_executor=...).run_live_producer_node(...).graph/.tool_name`; `build_live_producer_record(result, expectation).evaluated/.passed/.mismatches/.tool_status`; `EXECUTION_PARAMS_KEY` from `plan_graph_live` (imported by the applier and the tests). Consistent across all tasks and matching merged modules.
