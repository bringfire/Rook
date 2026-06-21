# LM1G PlanGraph Tool-Result Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one pure helper, `apply_tool_result(graph, node_id, raw_result)`, that composes the LM1F NodeOutcome adapter with the LM1E PlanGraph reducer, and prove a canned create→repair→success loop through it in non-live tests.

**Architecture:** A new import-light module `rook.learning.plan_graph_bridge` exposes a single function that calls `node_outcome_from_tool_result(...)` (LM1F) then `apply_outcome(...)` (LM1E). No walker, no node selection, no receipt inspection, no policy. The repair loop lives entirely in tests using a two-node fixture and canned result dictionaries.

**Tech Stack:** Python 3.12, pytest, the existing `rook.learning.plan_graph` and `rook.learning.plan_graph_outcomes` modules. Tests run via `mcp_server/.venv`.

## Global Constraints

- Module `mcp_server/src/rook/learning/plan_graph_bridge.py` may import only: `typing.Any`; `PlanGraph`, `apply_outcome` from `rook.learning.plan_graph`; `node_outcome_from_tool_result` from `rook.learning.plan_graph_outcomes`.
- No imports of: `rook.server`, `rook.agent.tool_dispatcher`, `rook.agent.chat.chat_runner`, `rook.agent.chat.tool_contracts`, ToolRegistry/capability/registry modules, Rhino/GH live tools, KG write paths, DSPy, or LiteLLM.
- The bridge adds no walker, no runnable-node selection, no readiness check, no retry policy, no escalation policy, and does not inspect `script_receipt`/`repair_anchor` directly.
- The bridge is imported by full module path (`rook.learning.plan_graph_bridge`); it is NOT added to `rook.learning.__all__`. Do not edit `rook/learning/__init__.py`.
- All tests are deterministic and non-live: canned dictionaries only, no Rhino, no GH, no ToolDispatcher, no ChatRunner, no server, no network.
- LM1F contract: `script_receipt` is extracted only from `result["data"]["script_receipt"]`. Canned test dicts must nest the receipt under `data`.
- Run all commands from the repo root `C:/UDEV/Rook`. Python: `mcp_server/.venv/Scripts/python.exe`.

---

### Task 1: Bridge helper + functional tests (seam + repair loop)

**Files:**
- Create: `mcp_server/src/rook/learning/plan_graph_bridge.py`
- Test: `mcp_server/tests/test_plan_graph_bridge.py`

**Interfaces:**
- Consumes:
  - `rook.learning.plan_graph.PlanGraph`, `PlanGraphNode`, `PlanGraphEdge`, `apply_outcome`, `initialize_graph`, `runnable_nodes`, `graph_status` (existing, LM1E).
  - `rook.learning.plan_graph_outcomes.node_outcome_from_tool_result` (existing, LM1F).
- Produces:
  - `rook.learning.plan_graph_bridge.apply_tool_result(graph: PlanGraph, node_id: str, raw_result: Any) -> PlanGraph` — returns a new graph; raises `ValueError` for an unknown `node_id`; does not mutate the input graph.

- [ ] **Step 1: Write the seam tests (helper contract)**

Create `mcp_server/tests/test_plan_graph_bridge.py` with the shared canned fixtures and the single-step seam tests:

```python
from __future__ import annotations

import ast
import copy
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    apply_outcome,
    graph_status,
    initialize_graph,
    runnable_nodes,
)
from rook.learning.plan_graph_outcomes import node_outcome_from_tool_result
from rook.learning.plan_graph_bridge import apply_tool_result


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _create_result() -> dict:
    """Canned LM1D-shaped create result: component placed with compile errors."""
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
                    "target_errors": [
                        "The name 'nonExistentSymbol' does not exist in the current context [14:13]"
                    ],
                },
            }
        },
    }


def _update_result() -> dict:
    """Canned LM1D-shaped update result: same component repaired and usable."""
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
                    "target_errors": [],
                },
            }
        },
    }


def _single_node_graph() -> PlanGraph:
    return initialize_graph(
        PlanGraph(nodes={"n": PlanGraphNode(id="n", intent="Node")})
    )


def test_apply_tool_result_equals_manual_adapter_then_reducer():
    graph = _single_node_graph()
    result = _create_result()

    via_bridge = apply_tool_result(graph, "n", result)
    via_manual = apply_outcome(graph, "n", node_outcome_from_tool_result(result))

    assert via_bridge == via_manual


def test_apply_tool_result_does_not_mutate_input_graph():
    graph = _single_node_graph()
    before = copy.deepcopy(graph)

    apply_tool_result(graph, "n", _create_result())

    assert graph == before


def test_apply_tool_result_deep_copies_against_post_call_mutation():
    graph = _single_node_graph()
    result = _create_result()

    updated = apply_tool_result(graph, "n", result)

    result["data"]["script_receipt"]["artifact_status"] = "mutated"
    result["data"]["script_receipt"]["repair_anchor"]["component_guid"] = "mutated"

    assert updated.nodes["n"].evidence.receipt["artifact_status"] == "created_with_errors"
    assert updated.memory.facts["repair_anchor"]["component_guid"] == COMPONENT_GUID


def test_apply_tool_result_raises_for_unknown_node_id():
    graph = PlanGraph(nodes={"known": PlanGraphNode(id="known", intent="Known")})

    with pytest.raises(ValueError, match="Unknown PlanGraph node"):
        apply_tool_result(graph, "missing", {"success": True})


def test_apply_tool_result_applies_blocked_for_non_dict_result_without_raising():
    graph = _single_node_graph()

    updated = apply_tool_result(graph, "n", "plain string result")

    assert updated.nodes["n"].status == "blocked"
```

- [ ] **Step 2: Write the repair-loop proof test**

Append the two-node repair-loop fixture and walk to `mcp_server/tests/test_plan_graph_bridge.py`:

```python
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


def test_canned_create_repair_loop_reaches_complete_through_bridge():
    graph = initialize_graph(_repair_fixture())
    assert {node.id for node in runnable_nodes(graph)} == {"create_script"}

    create_receipt = _create_result()["data"]["script_receipt"]
    graph = apply_tool_result(graph, "create_script", _create_result())

    assert graph.nodes["create_script"].status == "needs_repair"
    assert graph.memory.facts["component_guid"] == COMPONENT_GUID
    assert graph.memory.facts["repair_anchor"] == create_receipt["repair_anchor"]
    assert {node.id for node in runnable_nodes(graph)} == {"repair_same_component"}
    assert graph_status(graph) == "running"

    graph = apply_tool_result(graph, "repair_same_component", _update_result())

    assert graph.nodes["repair_same_component"].status == "succeeded"
    assert graph.memory.facts["component_guid"] == COMPONENT_GUID
    repair_evidence = graph.nodes["repair_same_component"].evidence
    assert repair_evidence is not None
    assert repair_evidence.receipt["artifact_status"] == "usable"
    assert graph_status(graph) == "complete"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_bridge.py -q`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_bridge'` (the module does not exist yet).

- [ ] **Step 4: Implement the bridge module**

Create `mcp_server/src/rook/learning/plan_graph_bridge.py`:

```python
"""LM1G PlanGraph tool-result bridge.

A single pure seam that composes the LM1F tool-result adapter with the LM1E
PlanGraph reducer. Given a raw tool-result dictionary, it produces a
``NodeOutcome`` and applies it to a named node.

The bridge holds no policy: it does not select runnable nodes, walk the graph,
check readiness, retry, escalate, or inspect ``script_receipt`` fields. Receipt
interpretation lives in ``plan_graph_outcomes``; graph transitions live in
``plan_graph``.
"""

from typing import Any

from rook.learning.plan_graph import PlanGraph, apply_outcome
from rook.learning.plan_graph_outcomes import node_outcome_from_tool_result


def apply_tool_result(
    graph: PlanGraph, node_id: str, raw_result: Any
) -> PlanGraph:
    """Adapt ``raw_result`` to a ``NodeOutcome`` and apply it to ``node_id``.

    Returns a new graph. Raises ``ValueError`` for an unknown ``node_id``
    (passed through from ``apply_outcome``). Does not mutate ``graph``.
    """
    outcome = node_outcome_from_tool_result(raw_result)
    return apply_outcome(graph, node_id, outcome)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_bridge.py -q`
Expected: PASS (6 tests passed).

- [ ] **Step 6: Run the adjacent suites to confirm no regression**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_bridge.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph.py -q`
Expected: PASS (all tests in the three files pass).

- [ ] **Step 7: Compile-check the new module**

Run: `mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_bridge.py`
Expected: no output, exit 0.

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/learning/plan_graph_bridge.py mcp_server/tests/test_plan_graph_bridge.py
git commit -m "feat(lm1g): PlanGraph tool-result bridge with repair-loop proof

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Import-boundary probes

**Files:**
- Modify: `mcp_server/tests/test_plan_graph_bridge.py` (append boundary tests)

**Interfaces:**
- Consumes: the source file `mcp_server/src/rook/learning/plan_graph_bridge.py` created in Task 1 (read via AST and an import subprocess; no runtime symbols needed beyond what Task 1 already imported).
- Produces: nothing new for other tasks; these tests guard the import-light invariant.

- [ ] **Step 1: Write the AST direct-import boundary test**

Append to `mcp_server/tests/test_plan_graph_bridge.py`:

```python
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


def test_plan_graph_bridge_imports_only_pure_graph_modules():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_bridge.py"
    )

    assert "rook.learning.plan_graph" in imports
    assert "rook.learning.plan_graph_outcomes" in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.chat.chat_runner" not in imports
    assert "rook.server" not in imports
```

- [ ] **Step 2: Run the AST test to verify it passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider "mcp_server/tests/test_plan_graph_bridge.py::test_plan_graph_bridge_imports_only_pure_graph_modules" -v`
Expected: PASS (the Task 1 module already satisfies this; this test pins it against future edits).

- [ ] **Step 3: Write the subprocess import-weight probe**

Append to `mcp_server/tests/test_plan_graph_bridge.py`:

```python
def test_importing_plan_graph_bridge_does_not_load_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_bridge\n"
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

- [ ] **Step 4: Run the full bridge test file to verify everything passes**

Run: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_bridge.py -q`
Expected: PASS (8 tests passed).

- [ ] **Step 5: Verify import direction by grep**

Run: `rg -n "tool_dispatcher|chat_runner|tool_contracts|rook\.server|dspy|litellm" mcp_server/src/rook/learning/plan_graph_bridge.py`
Expected: no matches (exit 1, no output).

- [ ] **Step 6: Whitespace/diff sanity check**

Run: `git diff --check`
Expected: no output (no whitespace errors).

- [ ] **Step 7: Commit**

```bash
git add mcp_server/tests/test_plan_graph_bridge.py
git commit -m "test(lm1g): import-boundary probes for plan_graph_bridge

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-06-20-lm1g-plangraph-tool-result-bridge-design.md`):

- Module `plan_graph_bridge.py` with one `apply_tool_result` helper → Task 1, Step 4.
- Pure composition of LM1F adapter + LM1E reducer → Task 1, Step 4; equivalence proven in Task 1, Step 1 (`test_apply_tool_result_equals_manual_adapter_then_reducer`).
- Import-light boundary, allowed imports only → Task 1, Step 4; enforced by Task 2 (AST + subprocess probes).
- Not added to `rook.learning.__all__`, imported by full path → Global Constraints + Task 1 imports the module by full path; `__init__.py` is untouched (no task edits it).
- Two-node proof graph `create_script --on_repair--> repair_same_component` (terminal), no `done`, no verifier node → Task 1, Step 2 (`_repair_fixture`).
- Walk: create → `needs_repair`, memory retains `component_guid` + `repair_anchor`, repair ready via `on_repair`, update → `succeeded`, `graph_status == "complete"` → Task 1, Step 2 (`test_canned_create_repair_loop_reaches_complete_through_bridge`).
- Repair node carries adapter-produced evidence (not hand-built) → asserted via `repair_evidence.receipt["artifact_status"] == "usable"`.
- Single-step seam tests: composition equivalence, input immutability, deep-copy protection, unknown-node `ValueError`, non-dict → `blocked` → Task 1, Step 1.
- Import-boundary probes (AST + subprocess), LM1F style → Task 2.
- Canned receipts nested under `result["data"]["script_receipt"]` per LM1F contract → both `_create_result`/`_update_result`.
- Verification commands (pytest, py_compile, rg, git diff --check) → Task 1 Steps 5–7, Task 2 Steps 5–6.

No gaps found.

**2. Placeholder scan:** No TBD/TODO, no "add error handling", no "write tests for the above", no "similar to Task N". All test and implementation code is shown in full. The non-dict seam test relies on the existing LM1F contract (non-dict → `blocked`), which is verified behavior in `test_plan_graph_outcomes.py`.

**3. Type consistency:** `apply_tool_result(graph: PlanGraph, node_id: str, raw_result: Any) -> PlanGraph` is named and signed identically in the spec, Global Constraints, Task 1 interfaces, the implementation (Step 4), and every test call. Node ids (`create_script`, `repair_same_component`, `n`, `known`), `COMPONENT_GUID`, and the `_create_result`/`_update_result`/`_repair_fixture`/`_single_node_graph` helpers are consistent across both tasks (Task 2 reuses the file from Task 1 and adds only the `_direct_import_modules` helper, which does not collide).
