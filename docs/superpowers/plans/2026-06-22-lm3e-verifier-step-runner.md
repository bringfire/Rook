# LM3E Verifier-Step Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `apply_verifier_step(graph, verifier_node_id, source_node_id)` — the single cross-node verifier primitive that drives one verifier node from a source node's captured evidence via the LM3D adapter and the LM1E reducer.

**Architecture:** A new import-light module `plan_graph_runner.py` (the first composition layer) reads the source node's `NodeEvidence`, projects it through `script_receipt_verifier_outcome`, and applies it with `apply_outcome`. `runnable_nodes` is the sole readiness authority; the walker and LM1F are untouched; the input graph is never mutated.

**Tech Stack:** Python 3.12, pytest. Stdlib `dataclasses`/`typing` only inside the module, plus `rook.learning.plan_graph` and `rook.learning.plan_graph_verifiers`.

## Global Constraints

- **One primitive only:** `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult`. No sequencing/scheduling.
- **`runnable_nodes(graph)` is the SOLE readiness authority.** No `source.status == "succeeded"` check, no edge inspection. The source node need only exist and carry evidence.
- **Receipt interpretation stays in LM3D** — the runner calls `script_receipt_verifier_outcome`; it never reads `script_receipt` fields itself.
- **No `initialize_graph` inside the primitive** — operates on the graph as given (like `apply_outcome`/`apply_tool_result`).
- **Never mutates the input graph:** not-applied returns the input unchanged (same object); applied returns `apply_outcome`'s fresh deep copy.
- **`reason` is a closed `Literal` union** `VerifierStepReason` (4 codes), drift-pinned.
- **No model calls, no live tools, no `planner.py`, no walker change, no LM1F change.** Does NOT revive the 5-node template (producer semantics are LM3F).
- **Import-light:** module imports only `rook.learning.plan_graph` + `rook.learning.plan_graph_verifiers` among rook modules (+ stdlib). AST allowlist + subprocess probe.
- **Watchpoint:** the happy-path `created_with_errors` test must assert BOTH `verify.status == "needs_repair"` AND `repair.status == "ready"` (the `on_repair` edge unlocked it) — proving composition through `apply_outcome`/the reducer, not just storing a status.
- Test commands run from repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/learning/plan_graph_runner.py` (new) — `VerifierStepReason`, `VerifierStepResult`, `apply_verifier_step`, a private `_not_applied` helper.
- `mcp_server/tests/test_plan_graph_runner.py` (new) — behavior + composition + purity suite.

---

### Task 1: `apply_verifier_step` verifier-step runner

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_runner.py`
- Create: `mcp_server/tests/test_plan_graph_runner.py`

**Interfaces:**
- Consumes (from `rook.learning.plan_graph`): `PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`, `NodeEvidence`, `OutcomeStatus` (Literal alias), `runnable_nodes(graph) -> list[PlanGraphNode]`, `apply_outcome(graph, node_id, outcome) -> PlanGraph`. (`PlanGraphNode` is a NON-frozen dataclass with mutable `status`/`evidence`; `PlanGraph.nodes` is a dict.)
- Consumes (from `rook.learning.plan_graph_verifiers`): `script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome` (has `.status`).
- Produces: `VerifierStepReason` (Literal), `VerifierStepResult` (frozen dataclass), `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_plan_graph_runner.py`:

```python
from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

from rook.learning.plan_graph import (
    NodeEvidence,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
)
from rook.learning.plan_graph_runner import apply_verifier_step


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _receipt(artifact_status: str) -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": artifact_status,
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "verification": {"status": "failed", "target_error_count": 1},
        "repair_anchor": {
            "component_guid": COMPONENT_GUID,
            "pins_out": [{"name": "A", "type": "double"}],
        },
    }


def _fixture(
    artifact_status: str = "created_with_errors", *, verify_status: str = "ready"
) -> PlanGraph:
    receipt = _receipt(artifact_status)
    return PlanGraph(
        nodes={
            "source": PlanGraphNode(
                id="source",
                intent="Fixture source evidence node",
                status="succeeded",
                evidence=NodeEvidence(
                    tool_status="failed",
                    verified=False,
                    receipt=receipt,
                    repair_anchor=receipt["repair_anchor"],
                ),
            ),
            "verify": PlanGraphNode(id="verify", intent="Verify", status=verify_status),
            "repair": PlanGraphNode(id="repair", intent="Repair", is_terminal=True),
        },
        edges=[
            # Documentary: in a real run a producer step would unlock `verify`;
            # here `verify` is pre-seeded ready (producer semantics -> LM3F).
            PlanGraphEdge(source="source", target="verify", kind="requires"),
            PlanGraphEdge(source="verify", target="repair", kind="on_repair"),
        ],
    )


def test_happy_path_needs_repair_unlocks_repair_node():
    graph = _fixture("created_with_errors")

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "needs_repair"
    assert result.graph.nodes["verify"].status == "needs_repair"
    # WATCHPOINT: the verifier's on_repair edge unlocks the repair node via the
    # reducer -- proves composition through apply_outcome, not just status storage.
    assert result.graph.nodes["repair"].status == "ready"
    # verifier node carries the receipt forward (via the LM3D adapter)
    assert result.graph.nodes["verify"].evidence is not None
    assert (
        result.graph.nodes["verify"].evidence.receipt["artifact_status"]
        == "created_with_errors"
    )


def test_usable_source_produces_succeeded():
    graph = _fixture("usable")

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is True
    assert result.outcome_status == "succeeded"
    assert result.graph.nodes["verify"].status == "succeeded"
    # on_repair does not fire on succeeded -> repair stays pending
    assert result.graph.nodes["repair"].status == "pending"


def test_unknown_verifier_node_not_applied():
    graph = _fixture()

    result = apply_verifier_step(graph, "missing", "source")

    assert result.applied is False
    assert result.reason == "unknown_verifier_node"
    assert result.outcome_status is None
    assert result.graph is graph  # input returned unchanged


def test_unknown_source_node_not_applied():
    graph = _fixture()

    result = apply_verifier_step(graph, "verify", "missing")

    assert result.applied is False
    assert result.reason == "unknown_source_node"
    assert result.graph is graph


def test_source_evidence_missing_not_applied():
    graph = _fixture()
    graph.nodes["source"].evidence = None

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is False
    assert result.reason == "source_evidence_missing"


def test_verifier_not_runnable_not_applied():
    graph = _fixture(verify_status="pending")

    result = apply_verifier_step(graph, "verify", "source")

    assert result.applied is False
    assert result.reason == "verifier_not_runnable"


def test_input_graph_not_mutated_on_apply():
    graph = _fixture("created_with_errors")
    before = copy.deepcopy(graph)

    apply_verifier_step(graph, "verify", "source")

    assert graph == before


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_runner_imports_only_plan_graph_layer():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_runner.py"
    )
    rook_or_relative = {
        m for m in imports if m.startswith("rook.") or m.startswith(".")
    }
    assert rook_or_relative == {
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_verifiers",
    }
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.learning.plan_graph_walker" not in imports
    assert "rook.agent.planner" not in imports


def test_importing_runner_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_runner\n"
        "for mod in ('rook.agent.tool_dispatcher', 'dspy', 'litellm'):\n"
        "    if mod in sys.modules:\n"
        "        raise SystemExit(mod + ' loaded')\n"
    )

    subprocess.run([sys.executable, "-c", probe], check=True, env=env)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_runner.py -v`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_runner'`.

- [ ] **Step 3: Implement the runner module**

Create `mcp_server/src/rook/learning/plan_graph_runner.py`:

```python
"""LM3E verifier-step runner -- first composition layer over the PlanGraph primitives.

A single cross-node primitive that drives one verifier node by reading a source
node's already-captured evidence, projecting it through the LM3D verifier adapter
(``script_receipt_verifier_outcome``), and applying the result through the LM1E
reducer (``apply_outcome``).

It is not a scheduler and not a sequencer: it applies exactly one verifier step.
``runnable_nodes`` is the sole readiness authority -- the runner never inspects
edges or requires ``source.status == "succeeded"``; the source node only needs to
exist and carry evidence. The walker and LM1F are untouched; receipt
interpretation stays in LM3D.

Imports only ``rook.learning.plan_graph`` (types + reducer) and
``rook.learning.plan_graph_verifiers`` (the verifier adapter).
"""

from dataclasses import dataclass
from typing import Literal

from rook.learning.plan_graph import (
    OutcomeStatus,
    PlanGraph,
    apply_outcome,
    runnable_nodes,
)
from rook.learning.plan_graph_verifiers import script_receipt_verifier_outcome


VerifierStepReason = Literal[
    "unknown_verifier_node",
    "unknown_source_node",
    "source_evidence_missing",
    "verifier_not_runnable",
]


@dataclass(frozen=True)
class VerifierStepResult:
    graph: PlanGraph
    applied: bool
    verifier_node_id: str
    source_node_id: str
    outcome_status: OutcomeStatus | None
    reason: VerifierStepReason | None


def _not_applied(
    graph: PlanGraph,
    verifier_node_id: str,
    source_node_id: str,
    reason: VerifierStepReason,
) -> VerifierStepResult:
    return VerifierStepResult(
        graph=graph,
        applied=False,
        verifier_node_id=verifier_node_id,
        source_node_id=source_node_id,
        outcome_status=None,
        reason=reason,
    )


def apply_verifier_step(
    graph: PlanGraph, verifier_node_id: str, source_node_id: str
) -> VerifierStepResult:
    """Apply one verifier node's outcome, derived from a source node's evidence.

    Reads ``source_node_id``'s captured ``NodeEvidence``, projects it through the
    LM3D verifier adapter, and applies the result to ``verifier_node_id`` via the
    reducer. ``runnable_nodes`` is the sole readiness authority. Never mutates the
    input graph: a not-applied result returns the input unchanged; an applied
    result returns the reducer's fresh graph.
    """
    if verifier_node_id not in graph.nodes:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "unknown_verifier_node"
        )
    if source_node_id not in graph.nodes:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "unknown_source_node"
        )

    source_evidence = graph.nodes[source_node_id].evidence
    if source_evidence is None:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "source_evidence_missing"
        )

    runnable_ids = {node.id for node in runnable_nodes(graph)}
    if verifier_node_id not in runnable_ids:
        return _not_applied(
            graph, verifier_node_id, source_node_id, "verifier_not_runnable"
        )

    outcome = script_receipt_verifier_outcome(source_evidence)
    new_graph = apply_outcome(graph, verifier_node_id, outcome)
    return VerifierStepResult(
        graph=new_graph,
        applied=True,
        verifier_node_id=verifier_node_id,
        source_node_id=source_node_id,
        outcome_status=outcome.status,
        reason=None,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_runner.py -v`
Expected: all 8 PASS.

- [ ] **Step 5: Regression — PlanGraph suites + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_runner.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_plan_graph_verifiers.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph_bridge.py mcp_server/tests/test_plan_graph_walker.py mcp_server/tests/test_plan_graph_templates.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_runner.py
```
Expected: all PASS; py_compile silent. (The runner adds no behavior to the other PlanGraph modules, so their suites must stay green.)

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_runner.py mcp_server/tests/test_plan_graph_runner.py
git commit -m "feat(lm3e): verifier-step runner (apply_verifier_step composition primitive)"
```

---

## Post-implementation (controller, not a task)

After Task 1 + the final whole-branch review:
- Open a PR `codex/lm3e-verifier-step-runner` → `main`. **Stop before merge — explicit human approval required (no self-merge).**
- Final reviewer EXTRA instructions:
  - (a) `runnable_nodes(graph)` is the SOLE readiness authority — no `source.status == "succeeded"` check, no edge inspection in the runner.
  - (b) **Watchpoint:** the happy-path test asserts the `repair` node becomes `ready` via the verifier's `on_repair` edge after `created_with_errors → needs_repair` — proving composition through `apply_outcome`, not just status storage.
  - (c) Verifier outcome is produced by the REAL LM3D `script_receipt_verifier_outcome` (not a stub); the runner never reads `script_receipt` fields itself.
  - (d) Input graph never mutated: not-applied returns the same input object; applied returns `apply_outcome`'s new graph. (`runnable_nodes` deep-copies, so it doesn't mutate.)
  - (e) `reason` is a closed `Literal` union; all four not-applied codes covered by tests.
  - (f) No `initialize_graph` inside the primitive; no sequencing/scheduling; no walker/LM1F change; no 5-node template revival.
  - (g) Import boundary — module imports only `rook.learning.plan_graph` + `rook.learning.plan_graph_verifiers` among rook modules; AST + subprocess probes pass.
- No deployed-runtime verification needed (pure learning-layer module; no wire/surface/runtime impact).
