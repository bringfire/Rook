# LM3A PlanGraph Replay/Walker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single pure `walk_plan_graph` that replays an explicit, caller-supplied ordered list of `(node_id, raw_result)` steps against a `PlanGraph` via the existing LM1G bridge + LM1E reducer and returns a diagnostic `WalkReport`.

**Architecture:** One new import-light module `plan_graph_walker.py` exposing frozen report dataclasses (`EvidenceSummary`, `WalkStep`, `WalkReport`) and `walk_plan_graph`. The walker reads readiness only via `runnable_nodes`, transitions only via `apply_tool_result`, halts on the first invalid step or terminal graph status, and never selects nodes, calls tools/models, inspects receipts, or invents policy.

**Tech Stack:** Python 3.12, pytest. Stdlib only inside the module (`copy`, `dataclasses`, `typing`) plus `rook.learning.plan_graph` and `rook.learning.plan_graph_bridge`.

## Global Constraints

- **Walker-only.** No birth seam (intent→graph). No node selection / scheduling. No live tool or model call. No ToolRegistry mutation. No capability/profile resolution.
- **State authority stays in LM1E.** Readiness computed ONLY via `runnable_nodes(graph)`; never re-derive readiness from edges. All transitions go ONLY through `apply_tool_result`.
- **No receipt inspection.** `EvidenceSummary` reads only top-level `NodeEvidence` fields (`tool_status`, `verified`, `repair_anchor` presence, `message`, `error`) — never `evidence.receipt` internals.
- **Decision A:** an invalid step (named node not currently runnable) HALTS, not skips.
- **Decision B:** terminal = any `graph_status` not in `{"pending", "running"}` (so `complete`/`failed`/`needs_escalation`/`blocked` all halt).
- **Decision C:** the report carries `final_graph`.
- **`reason`** distinguishes `"unknown_node"` (node absent from graph) vs `"node_not_runnable"` (present but not `ready`).
- **`remaining_steps` watchpoint:** store the unprocessed tuple tail AS-IS (`tuple(steps[i+1:])`) — no deep-copy, no serialization (raw results are arbitrary `Any` and may be non-copyable). `memory_facts` snapshots, by contrast, ARE deep-copied.
- **Import-light, enforced.** The module must not import `plan_graph_outcomes`, `tool_result_view`, `tool_contracts`, `tool_dispatcher`, `chat_runner`, `rook.server`, `dspy`, or `litellm`. Proven by an AST allowlist test and a subprocess probe.
- **Non-dict raw result → `blocked` is bridge/adapter behavior surfaced by the walker**, not walker behavior — the walker applies it like any valid step and adds no special-casing.
- Test commands run from repo root (`C:\UDEV\Rook`) with the repo venv: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider ...`.

## File Structure

- `mcp_server/src/rook/learning/plan_graph_walker.py` (new) — the walker module; one public function + three frozen report dataclasses + small private helpers.
- `mcp_server/tests/test_plan_graph_walker.py` (new) — full behavior + purity suite.

---

### Task 1: `walk_plan_graph` replay/walker

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_walker.py`
- Create: `mcp_server/tests/test_plan_graph_walker.py`

**Interfaces:**
- Consumes (from `rook.learning.plan_graph`): `PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`, `NodeStatus`, `GraphStatus`, `initialize_graph(graph) -> PlanGraph`, `runnable_nodes(graph) -> list[PlanGraphNode]`, `graph_status(graph) -> GraphStatus`. Node fields used: `node.id`, `node.status`, `node.evidence` (a `NodeEvidence | None` with `tool_status`, `verified`, `repair_anchor`, `message`, `error`). Memory: `graph.memory.facts: dict[str, Any]`.
- Consumes (from `rook.learning.plan_graph_bridge`): `apply_tool_result(graph, node_id, raw_result) -> PlanGraph`.
- Produces: `EvidenceSummary`, `WalkStep`, `WalkReport` (frozen dataclasses) and `walk_plan_graph(graph: PlanGraph, steps: list[tuple[str, Any]]) -> WalkReport`.

- [ ] **Step 1: Write the failing tests**

Create `mcp_server/tests/test_plan_graph_walker.py`:

```python
from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    initialize_graph,
)
from rook.learning.plan_graph_walker import walk_plan_graph


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _create_result() -> dict:
    """LM1D-shaped create result: component placed with compile errors."""
    return {
        "success": False,
        "message": "Component was created, but the target script component has compile errors.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "method": "gh_create_component_then_script",
                    "component_guid": COMPONENT_GUID,
                    "note": None,
                },
                "verification": {
                    "status": "failed",
                    "method": "gh_errors",
                    "target_error_count": 1,
                },
                "repair_anchor": {
                    "component_guid": COMPONENT_GUID,
                    "language": "csharp",
                    "pins_out": [{"name": "A", "type": "double"}],
                },
            }
        },
    }


def _update_result() -> dict:
    """LM1D-shaped update result: same component repaired and usable."""
    return {
        "success": True,
        "message": "Script updated; component is usable.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "update",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {
                    "status": "written",
                    "method": "gh_script_write",
                    "component_guid": COMPONENT_GUID,
                    "note": None,
                },
                "verification": {
                    "status": "passed",
                    "method": "gh_errors",
                    "target_error_count": 0,
                },
                "repair_anchor": {
                    "component_guid": COMPONENT_GUID,
                    "language": "csharp",
                    "pins_out": [{"name": "A", "type": "Generic Data"}],
                },
            }
        },
    }


def _repair_fixture() -> PlanGraph:
    return PlanGraph(
        nodes={
            "create_script": PlanGraphNode(
                id="create_script",
                intent="Create C# script component",
                execution_ref="gh_create_csharp_script:v1",
            ),
            "repair_same_component": PlanGraphNode(
                id="repair_same_component",
                intent="Repair same component",
                execution_ref="gh_update_script:v1",
                is_terminal=True,
            ),
        },
        edges=[
            PlanGraphEdge(
                source="create_script",
                target="repair_same_component",
                kind="on_repair",
            ),
        ],
    )


def _orphan_create_graph() -> PlanGraph:
    return PlanGraph(nodes={"create": PlanGraphNode(id="create", intent="Create")})


def _single_terminal_graph() -> PlanGraph:
    return PlanGraph(
        nodes={"n": PlanGraphNode(id="n", intent="Node", is_terminal=True)}
    )


def _escalation_fixture() -> PlanGraph:
    # needs_escalation is never produced by the adapter/bridge; it enters the
    # graph from outside (a future verifier/repair-policy layer). The walker only
    # reflects it. Pre-seed it and drive an unrelated ready root.
    return PlanGraph(
        nodes={
            "ready_root": PlanGraphNode(id="ready_root", intent="Ready root"),
            "already_escalated": PlanGraphNode(
                id="already_escalated",
                intent="Pre-escalated",
                status="needs_escalation",
            ),
        },
    )


def test_full_create_repair_complete_replay_carries_memory_forward():
    report = walk_plan_graph(
        _repair_fixture(),
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert report.halted is False
    assert report.halt_reason is None
    assert report.remaining_steps == ()
    assert report.final_graph_status == "complete"
    assert [s.node_id for s in report.steps] == [
        "create_script",
        "repair_same_component",
    ]

    create_step = report.steps[0]
    assert create_step.applied is True
    assert create_step.runnable_before is True
    assert create_step.status_before == "ready"
    assert create_step.status_after == "needs_repair"
    assert create_step.graph_status_after == "running"
    assert create_step.memory_facts["component_guid"] == COMPONENT_GUID
    assert create_step.memory_facts["repair_anchor"]["component_guid"] == COMPONENT_GUID
    assert create_step.evidence is not None
    assert create_step.evidence.tool_status == "failed"
    assert create_step.evidence.has_repair_anchor is True
    assert create_step.reason is None

    repair_step = report.steps[1]
    assert repair_step.status_before == "ready"
    assert repair_step.status_after == "succeeded"
    assert repair_step.graph_status_after == "complete"
    assert repair_step.evidence is not None
    assert repair_step.evidence.tool_status == "success"

    assert report.final_memory_facts["component_guid"] == COMPONENT_GUID


def test_invalid_step_node_not_runnable_halts_without_mutating_input():
    graph = _repair_fixture()
    original = copy.deepcopy(graph)

    report = walk_plan_graph(graph, [("repair_same_component", _update_result())])

    assert len(report.steps) == 1
    step = report.steps[0]
    assert step.applied is False
    assert step.runnable_before is False
    assert step.reason == "node_not_runnable"
    assert step.status_before == "pending"
    assert step.evidence is None
    assert report.halted is True
    assert report.halt_reason == "invalid_step"
    assert report.remaining_steps == ()
    # input graph not mutated; final graph is merely the initialized form
    assert graph == original
    assert report.final_graph == initialize_graph(original)


def test_invalid_step_unknown_node_reports_unknown_node():
    report = walk_plan_graph(
        _repair_fixture(), [("does_not_exist", {"success": True})]
    )

    step = report.steps[0]
    assert step.applied is False
    assert step.reason == "unknown_node"
    assert step.status_before is None
    assert report.halted is True
    assert report.halt_reason == "invalid_step"


def test_remaining_steps_preserves_raw_result_tail_as_is():
    class _Uncopyable:
        def __deepcopy__(self, memo):
            raise AssertionError("remaining_steps must not deep-copy raw results")

    tail_payload = _Uncopyable()
    report = walk_plan_graph(
        _single_terminal_graph(),
        [("n", {"success": True}), ("later", tail_payload)],
    )

    assert report.halted is True
    assert report.halt_reason == "terminal_status"
    assert report.final_graph_status == "complete"
    assert len(report.remaining_steps) == 1
    node_id, payload = report.remaining_steps[0]
    assert node_id == "later"
    assert payload is tail_payload  # identity preserved, not copied


def test_walker_surfaces_pre_existing_escalation_and_halts_terminal():
    report = walk_plan_graph(
        _escalation_fixture(), [("ready_root", {"success": True})]
    )

    assert report.steps[0].applied is True
    assert report.final_graph_status == "needs_escalation"
    assert report.nodes_needing_escalation == ("already_escalated",)
    assert report.halted is True
    assert report.halt_reason == "terminal_status"


def test_needs_repair_without_repair_edge_reflected_and_blocks():
    report = walk_plan_graph(_orphan_create_graph(), [("create", _create_result())])

    assert report.steps[0].status_after == "needs_repair"
    assert report.nodes_needing_repair == ("create",)
    assert report.final_graph_status == "blocked"
    assert report.halted is True
    assert report.halt_reason == "terminal_status"


def test_non_dict_raw_result_blocks_via_adapter_without_raising():
    report = walk_plan_graph(_orphan_create_graph(), [("create", "plain string result")])

    step = report.steps[0]
    assert step.applied is True
    assert step.status_after == "blocked"
    assert report.final_graph_status == "blocked"
    assert report.halt_reason == "terminal_status"


def test_empty_steps_returns_initialized_graph_report():
    report = walk_plan_graph(_repair_fixture(), [])

    assert report.steps == ()
    assert report.halted is False
    assert report.halt_reason is None
    assert report.remaining_steps == ()
    assert report.final_graph == initialize_graph(_repair_fixture())
    assert report.final_runnable_node_ids == ("create_script",)


def test_input_graph_not_mutated_by_full_walk():
    graph = _repair_fixture()
    original = copy.deepcopy(graph)

    walk_plan_graph(
        graph,
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert graph == original


def test_initialize_graph_is_idempotent_for_already_initialized_graph():
    once = initialize_graph(_repair_fixture())
    twice = initialize_graph(once)

    assert twice == once


def test_memory_facts_snapshots_are_isolated_from_final_graph():
    report = walk_plan_graph(_orphan_create_graph(), [("create", _create_result())])

    report.final_memory_facts["repair_anchor"]["component_guid"] = "mutated"
    report.steps[0].memory_facts["component_guid"] = "mutated"

    assert (
        report.final_graph.memory.facts["repair_anchor"]["component_guid"]
        == COMPONENT_GUID
    )
    assert report.final_graph.memory.facts["component_guid"] == COMPONENT_GUID


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


def test_walker_imports_only_pure_graph_modules():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_walker.py"
    )

    assert "rook.learning.plan_graph" in imports
    assert "rook.learning.plan_graph_bridge" in imports
    assert "rook.learning.plan_graph_outcomes" not in imports
    assert "rook.agent.chat.tool_result_view" not in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.server" not in imports


def test_importing_walker_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_walker\n"
        "if 'rook.agent.tool_dispatcher' in sys.modules:\n"
        "    raise SystemExit('rook.agent.tool_dispatcher loaded')\n"
        "if 'dspy' in sys.modules:\n"
        "    raise SystemExit('dspy loaded')\n"
        "if 'litellm' in sys.modules:\n"
        "    raise SystemExit('litellm loaded')\n"
    )

    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        env=env,
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_walker.py -v`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_walker'` (the module does not exist yet).

- [ ] **Step 3: Implement the walker**

Create `mcp_server/src/rook/learning/plan_graph_walker.py`:

```python
"""LM3A PlanGraph replay/walker (non-live drive scaffold).

A single pure function that replays an explicit, caller-supplied ordered list of
``(node_id, raw_result)`` steps against a ``PlanGraph``, advancing it through the
LM1G bridge (``apply_tool_result``) and LM1E reducer, and returning a diagnostic
``WalkReport``.

It is not a scheduler: it never selects a node, calls a tool or model, resolves
profiles/capabilities, inspects ``script_receipt`` internals, or invents
retry/escalation policy. The caller dictates the exact step sequence. Readiness is
read only via ``runnable_nodes``; transitions go only through ``apply_tool_result``.
"""

import copy
from dataclasses import dataclass
from typing import Any

from rook.learning.plan_graph import (
    GraphStatus,
    NodeStatus,
    PlanGraph,
    PlanGraphNode,
    graph_status,
    initialize_graph,
    runnable_nodes,
)
from rook.learning.plan_graph_bridge import apply_tool_result


_NON_TERMINAL_STATUSES = ("pending", "running")


@dataclass(frozen=True)
class EvidenceSummary:
    """Projection of NodeEvidence TOP-LEVEL fields only (no receipt inspection)."""

    tool_status: str | None
    verified: bool | None
    has_repair_anchor: bool
    message: str | None
    error: str | None


@dataclass(frozen=True)
class WalkStep:
    node_id: str
    applied: bool
    runnable_before: bool
    status_before: NodeStatus | None
    status_after: NodeStatus | None
    graph_status_after: GraphStatus
    memory_facts: dict[str, Any]
    evidence: EvidenceSummary | None
    reason: str | None


@dataclass(frozen=True)
class WalkReport:
    steps: tuple[WalkStep, ...]
    final_graph: PlanGraph
    final_graph_status: GraphStatus
    final_runnable_node_ids: tuple[str, ...]
    final_memory_facts: dict[str, Any]
    nodes_needing_repair: tuple[str, ...]
    nodes_needing_escalation: tuple[str, ...]
    halted: bool
    halt_reason: str | None
    remaining_steps: tuple[tuple[str, Any], ...]


def _evidence_summary(node: PlanGraphNode) -> EvidenceSummary | None:
    evidence = node.evidence
    if evidence is None:
        return None
    return EvidenceSummary(
        tool_status=evidence.tool_status,
        verified=evidence.verified,
        has_repair_anchor=evidence.repair_anchor is not None,
        message=evidence.message,
        error=evidence.error,
    )


def _ids_by_status(graph: PlanGraph, status: NodeStatus) -> tuple[str, ...]:
    return tuple(
        sorted(
            node_id
            for node_id, node in graph.nodes.items()
            if node.status == status
        )
    )


def _report(
    graph: PlanGraph,
    steps: list[WalkStep],
    *,
    halted: bool,
    halt_reason: str | None,
    remaining: tuple[tuple[str, Any], ...],
) -> WalkReport:
    return WalkReport(
        steps=tuple(steps),
        final_graph=graph,
        final_graph_status=graph_status(graph),
        final_runnable_node_ids=tuple(
            sorted(node.id for node in runnable_nodes(graph))
        ),
        final_memory_facts=copy.deepcopy(graph.memory.facts),
        nodes_needing_repair=_ids_by_status(graph, "needs_repair"),
        nodes_needing_escalation=_ids_by_status(graph, "needs_escalation"),
        halted=halted,
        halt_reason=halt_reason,
        remaining_steps=remaining,
    )


def walk_plan_graph(graph: PlanGraph, steps: list[tuple[str, Any]]) -> WalkReport:
    """Replay ``steps`` against ``graph`` and return a diagnostic ``WalkReport``.

    Initializes ``graph`` once (relying on the reducer's copy semantics; the
    caller's graph is never mutated). For each ``(node_id, raw_result)``: if the
    node is not currently runnable, records an invalid step and halts
    (``halt_reason="invalid_step"``); otherwise applies it through the bridge and
    halts if the resulting graph status is terminal
    (``halt_reason="terminal_status"``). ``remaining_steps`` holds the unprocessed
    tail as-is (no copy).
    """
    graph = initialize_graph(graph)
    recorded: list[WalkStep] = []

    for index, (node_id, raw_result) in enumerate(steps):
        runnable_ids = {node.id for node in runnable_nodes(graph)}
        if node_id not in runnable_ids:
            known = node_id in graph.nodes
            status_before = graph.nodes[node_id].status if known else None
            recorded.append(
                WalkStep(
                    node_id=node_id,
                    applied=False,
                    runnable_before=False,
                    status_before=status_before,
                    status_after=status_before,
                    graph_status_after=graph_status(graph),
                    memory_facts=copy.deepcopy(graph.memory.facts),
                    evidence=None,
                    reason="unknown_node" if not known else "node_not_runnable",
                )
            )
            return _report(
                graph,
                recorded,
                halted=True,
                halt_reason="invalid_step",
                remaining=tuple(steps[index + 1 :]),
            )

        status_before = graph.nodes[node_id].status
        graph = apply_tool_result(graph, node_id, raw_result)
        node_after = graph.nodes[node_id]
        gstatus = graph_status(graph)
        recorded.append(
            WalkStep(
                node_id=node_id,
                applied=True,
                runnable_before=True,
                status_before=status_before,
                status_after=node_after.status,
                graph_status_after=gstatus,
                memory_facts=copy.deepcopy(graph.memory.facts),
                evidence=_evidence_summary(node_after),
                reason=None,
            )
        )
        if gstatus not in _NON_TERMINAL_STATUSES:
            return _report(
                graph,
                recorded,
                halted=True,
                halt_reason="terminal_status",
                remaining=tuple(steps[index + 1 :]),
            )

    return _report(
        graph, recorded, halted=False, halt_reason=None, remaining=()
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_walker.py -v`
Expected: all 13 PASS.

- [ ] **Step 5: Regression — sibling PlanGraph suites + py_compile**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_walker.py mcp_server/tests/test_plan_graph.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph_bridge.py -v
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_walker.py
```
Expected: all PASS; py_compile silent. (The walker adds no behavior to the sibling modules, so their suites must stay green.)

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_walker.py mcp_server/tests/test_plan_graph_walker.py
git commit -m "feat(lm3a): non-live PlanGraph replay/walker"
```

---

## Post-implementation (controller, not a task)

After Task 1 + the final whole-branch review:
- Open a PR `codex/lm3a-plan-graph-walker` → `main`. **Stop before merge — explicit human approval required (no self-merge).**
- Final reviewer EXTRA instructions:
  - (a) The walker selects no node and calls no tool/model — readiness comes only from `runnable_nodes`, transitions only from `apply_tool_result`.
  - (b) `EvidenceSummary` reads only top-level `NodeEvidence` fields — no `evidence.receipt` inspection.
  - (c) `remaining_steps` stores the raw tuple tail with no deep-copy/serialization; `memory_facts`/`final_memory_facts` are deep-copied.
  - (d) No import of `plan_graph_outcomes`, `tool_result_view`, `tool_dispatcher`, `rook.server`, `dspy`, or `litellm` in the module (AST + subprocess probe present and passing).
  - (e) Decisions A/B/C honored; `reason` distinguishes `unknown_node` vs `node_not_runnable`.
- Note for the reviewer/PR body: the escalation test pre-seeds a `needs_escalation` node because the LM1G adapter never synthesizes that status from a tool result; the walker only reflects escalation that enters the graph from a future verifier/repair-policy layer.
