# LM4K — Memory-Backed Repair-Param Sourcing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pure learning-layer primitive `bind_params_from_memory` that sources a node's producer params from the runtime `graph.memory.facts` substrate, and prove (pure + live) that the repair guid can come from memory instead of hand-wired evidence.

**Architecture:** One new pure module `learning/plan_graph_param_binding.py` that **returns** merged params (never writes node metadata, no agent import, no graph mutation, deep-copies, no partial success). Three test deliverables consume it: unit tests for the helper, a pure chain guard (memory→params + composition), and a `requires_rhino` live proof (memory-sourced guid actually drives `gh_update_script`).

**Tech Stack:** Python 3.12, pytest (+ `pytest-asyncio`, `requires_rhino`), Rook `learning`/`agent` packages (editable-installed in `mcp_server/.venv`).

## Global Constraints

From the spec (`docs/superpowers/specs/2026-06-24-lm4k-memory-backed-param-sourcing-design.md`).

- **Helper is PURE learning-layer.** Reads only `graph.memory.facts`; no graph/base mutation; deep-copies base params and every bound value. Imports only stdlib + `rook.learning.plan_graph` (TYPE_CHECKING-quoted `PlanGraph`). **No `rook.agent.*`, no `EXECUTION_PARAMS_KEY`.**
- **Helper returns params; it never writes `node.metadata["execution_params"]`.** The tests perform that assignment (and import `EXECUTION_PARAMS_KEY` themselves).
- **No partial success:** process every binding, collect all findings; if any error finding exists, return `params=None`.
- **Findings (all severity `error`):** `base_params_invalid`, `base_params_copy_failed`, `param_key_invalid`, `memory_path_invalid`, `memory_fact_missing`, `memory_fact_invalid`, `memory_value_copy_failed`.
- **Distinct types** `ParamBindingResult` / `ParamBindingFinding` (not the templates' `BindingResult`).
- **Nested path is the live source** (`("repair_anchor", "component_guid")`); flat `("component_guid",)` is equivalence/control coverage only.
- **Production change is EXACTLY one new module:** `mcp_server/src/rook/learning/plan_graph_param_binding.py`. No edits to any existing `src/` file. `git diff --numstat main...HEAD -- mcp_server/src` lists only that file.
- **No producer ref overrides in the live proof; create params omit `language`;** keep `_ensure_gh_document`; restore `knowledge/gh/operations_knowledge.json` after live runs.
- **Whole-branch diff = spec + plan + 1 module + 3 test files.**

## Seam reference (already merged — consume, do not modify)

- `PlanGraph`, `GraphMemory`, `NodeOutcome`, `apply_outcome`, `graph_status`, `initialize_graph` — `rook.learning.plan_graph`. `PlanGraph(memory=GraphMemory(facts={...}))` constructs a minimal graph.
- `apply_producer_result(graph, node_id, raw_result) -> ProducerStepResult` (`.applied`, `.outcome_status`, `.graph`); `apply_verifier_step(graph, verifier_node_id, source_node_id) -> VerifierStepResult` (`.applied`, `.outcome_status`, `.graph`) — `rook.learning.plan_graph_runner`.
- `select_template(descriptor) -> .selected_template_id/.graph` — `rook.learning.plan_graph_templates`.
- `RookAgent(tool_executor=…).run_live_producer_node(graph, node_id) -> LiveProducerResult` (`.graph`, `.tool_name`) — `rook.agent.base_agent`.
- `EXECUTION_PARAMS_KEY` — `rook.agent.plan_graph_live` (imported by **tests**, never the helper).
- `build_live_producer_record(result, expectation) -> .evaluated/.passed/.mismatches/.tool_status`; `LiveProducerExpectation(...)` — `rook.agent.plan_graph_live_runner`.
- `_mcp_tool_executor` — `rook.server`. `fresh_document` + `_is_error` — `mcp_server/tests/conftest.py`.

---

### Task 1: Helper module + pure unit tests (TDD — tests first)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_param_binding.py`
- Create: `mcp_server/src/rook/learning/plan_graph_param_binding.py`

**Interfaces:**
- Produces: `ParamBindingFinding(code, severity, param_key, message)`, `ParamBindingResult(params, findings)`, `bind_params_from_memory(base_params, graph, bindings) -> ParamBindingResult`. Consumed by Tasks 2 and 3.

- [ ] **Step 1: Write the failing unit tests**

Create `mcp_server/tests/test_plan_graph_param_binding.py` with exactly this content:

```python
"""LM4K unit tests for bind_params_from_memory — runtime memory.facts -> producer
params. Pure: returns merged params, no node write, no mutation, deep-copies, no
partial success. In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

from rook.learning.plan_graph import GraphMemory, PlanGraph
from rook.learning.plan_graph_param_binding import bind_params_from_memory


_BASE = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}


def _graph_with_facts(facts: dict) -> PlanGraph:
    return PlanGraph(memory=GraphMemory(facts=facts))


class _NoDeepcopy:
    """A value whose deepcopy raises -- exercises the copy-failure findings."""

    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def test_nested_path_success():
    g = _graph_with_facts({"repair_anchor": {"component_guid": "GUID-1"}})
    r = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.findings == ()
    assert r.params == {**_BASE, "guid": "GUID-1"}


def test_flat_path_equals_nested():
    g = _graph_with_facts(
        {"component_guid": "GUID-1", "repair_anchor": {"component_guid": "GUID-1"}}
    )
    flat = bind_params_from_memory(_BASE, g, {"guid": ("component_guid",)})
    nested = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert flat.findings == () and nested.findings == ()
    assert flat.params["guid"] == nested.params["guid"] == "GUID-1"


def test_memory_fact_missing_returns_none():
    g = _graph_with_facts({"repair_anchor": {"language": "csharp"}})  # no component_guid
    r = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_fact_missing"]


def test_memory_path_invalid_empty_and_nonstring():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    empty = bind_params_from_memory(_BASE, g, {"guid": ()})
    nonstr = bind_params_from_memory(_BASE, g, {"guid": ("component_guid", 5)})
    assert empty.params is None
    assert [f.code for f in empty.findings] == ["memory_path_invalid"]
    assert nonstr.params is None
    assert [f.code for f in nonstr.findings] == ["memory_path_invalid"]


def test_memory_fact_invalid_non_mapping_intermediate():
    g = _graph_with_facts({"repair_anchor": "not-a-dict"})
    r = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_fact_invalid"]


def test_base_params_invalid():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    r = bind_params_from_memory(["not", "a", "mapping"], g, {"guid": ("component_guid",)})
    assert r.params is None
    assert [f.code for f in r.findings] == ["base_params_invalid"]


def test_param_key_invalid_none_and_empty():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    none_key = bind_params_from_memory(_BASE, g, {None: ("component_guid",)})
    empty_key = bind_params_from_memory(_BASE, g, {"": ("component_guid",)})
    assert none_key.params is None
    assert [f.code for f in none_key.findings] == ["param_key_invalid"]
    assert empty_key.params is None
    assert [f.code for f in empty_key.findings] == ["param_key_invalid"]


def test_base_params_copy_failed():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    base = {"bad": _NoDeepcopy()}  # a Mapping, but deepcopy of its value raises
    r = bind_params_from_memory(base, g, {"guid": ("component_guid",)})
    assert r.params is None
    assert [f.code for f in r.findings] == ["base_params_copy_failed"]


def test_memory_value_copy_failed():
    g = _graph_with_facts({"weird": _NoDeepcopy()})  # present, but deepcopy raises
    r = bind_params_from_memory(_BASE, g, {"guid": ("weird",)})
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_value_copy_failed"]


def test_no_partial_success_collects_and_returns_none():
    # "guid" would resolve, but the missing binding nulls the whole result.
    g = _graph_with_facts({"component_guid": "GOOD"})
    r = bind_params_from_memory(
        _BASE, g, {"guid": ("component_guid",), "missing": ("absent_key",)}
    )
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_fact_missing"]


def test_immutability_of_inputs():
    facts = {"repair_anchor": {"component_guid": "GUID-1"}}
    g = _graph_with_facts(facts)
    base = dict(_BASE)
    r = bind_params_from_memory(base, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.params is not None
    assert g.memory.facts == {"repair_anchor": {"component_guid": "GUID-1"}}
    assert base == _BASE
    # mutating the returned params must not touch base
    r.params["code"] = "changed"
    assert base["code"] == "A = 42.0;"


def test_bound_dict_value_is_deepcopied_from_memory():
    g = _graph_with_facts({"repair_anchor": {"component_guid": "GUID-1"}})
    r = bind_params_from_memory({"x": 1}, g, {"anchor": ("repair_anchor",)})
    assert r.params["anchor"] == {"component_guid": "GUID-1"}
    r.params["anchor"]["component_guid"] = "MUTATED"
    assert g.memory.facts["repair_anchor"]["component_guid"] == "GUID-1"


def test_module_uses_no_agent_layer_and_no_execution_params_key():
    # AST-based (not text-based): a docstring/comment mention of the token is fine;
    # what matters is that the module neither imports the agent layer nor references
    # EXECUTION_PARAMS_KEY as an identifier.
    import rook.learning.plan_graph_param_binding as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert not any(m.startswith("rook.agent") for m in imported_modules), imported_modules
    assert "EXECUTION_PARAMS_KEY" not in referenced
```

- [ ] **Step 2: Run the tests to verify they fail (module missing)**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_param_binding.py -q
```
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.learning.plan_graph_param_binding'`.

- [ ] **Step 3: Write the helper module**

Create `mcp_server/src/rook/learning/plan_graph_param_binding.py` with exactly this content:

```python
"""LM4K pure memory-backed param binding (learning layer).

bind_params_from_memory resolves a node's producer params from the RUNTIME
graph.memory.facts substrate (populated by apply_producer_result -> _merge_memory)
instead of from node evidence. PURE: reads only graph.memory.facts, RETURNS merged
params, never writes node metadata, never mutates the graph or base params,
deep-copies all values.

Distinct from BindingSpec/bind_parameters (plan_graph_templates), which binds an
intent-descriptor field -> memory/metadata at CONSTRUCTION time. This is RUNTIME
memory -> params binding: the seam a future runner calls to source producer params
without the model. NO agent import, NO EXECUTION_PARAMS_KEY -- the caller assigns the
returned dict into node.metadata["execution_params"].
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from rook.learning.plan_graph import PlanGraph


@dataclass(frozen=True)
class ParamBindingFinding:
    code: str
    severity: Literal["error"]
    param_key: str | None
    message: str


@dataclass(frozen=True)
class ParamBindingResult:
    params: dict | None
    findings: tuple[ParamBindingFinding, ...]


def _finding(code: str, param_key: str | None, message: str) -> ParamBindingFinding:
    return ParamBindingFinding(
        code=code, severity="error", param_key=param_key, message=message
    )


_MISSING = object()


def bind_params_from_memory(
    base_params: "Mapping",
    graph: "PlanGraph",
    bindings: "Mapping[str, tuple[str, ...]]",
) -> ParamBindingResult:
    """Merge ``base_params`` with values sourced from ``graph.memory.facts`` along the
    explicit string-tuple paths in ``bindings`` (``{param_key: path}``).

    Returns merged params on full success. Processes ALL bindings and collects ALL
    findings; if ANY error finding exists, returns ``params=None`` (no partial bind).
    Pure: never mutates ``graph`` or ``base_params``; deep-copies base and every bound
    value.
    """
    if not isinstance(base_params, Mapping):
        return ParamBindingResult(
            params=None,
            findings=(
                _finding("base_params_invalid", None, "base_params is not a Mapping."),
            ),
        )

    try:
        merged: dict = deepcopy(dict(base_params))
    except Exception:
        return ParamBindingResult(
            params=None,
            findings=(
                _finding(
                    "base_params_copy_failed", None, "Could not deep-copy base_params."
                ),
            ),
        )

    findings: list[ParamBindingFinding] = []
    facts = graph.memory.facts

    for param_key, path in bindings.items():
        if not isinstance(param_key, str) or not param_key:
            findings.append(
                _finding(
                    "param_key_invalid",
                    None,
                    f"Binding param_key {param_key!r} is not a non-empty string.",
                )
            )
            continue
        if (
            not isinstance(path, tuple)
            or len(path) == 0
            or not all(isinstance(p, str) for p in path)
        ):
            findings.append(
                _finding(
                    "memory_path_invalid",
                    param_key,
                    f"Binding path {path!r} must be a non-empty tuple of strings.",
                )
            )
            continue

        current = facts
        resolved = _MISSING
        for i, key in enumerate(path):
            if not isinstance(current, Mapping):
                findings.append(
                    _finding(
                        "memory_fact_invalid",
                        param_key,
                        f"Path element {key!r} cannot descend into a non-Mapping.",
                    )
                )
                break
            if key not in current:
                findings.append(
                    _finding(
                        "memory_fact_missing",
                        param_key,
                        f"Memory fact key {key!r} is absent.",
                    )
                )
                break
            current = current[key]
            if i == len(path) - 1:
                resolved = current

        if resolved is _MISSING:
            continue
        try:
            merged[param_key] = deepcopy(resolved)
        except Exception:
            findings.append(
                _finding(
                    "memory_value_copy_failed",
                    param_key,
                    f"Could not deep-copy the memory value for {param_key!r}.",
                )
            )

    if findings:
        return ParamBindingResult(params=None, findings=tuple(findings))
    return ParamBindingResult(params=merged, findings=())
```

- [ ] **Step 4: Run the unit tests to verify they pass**

Run:
```
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_param_binding.py -v
```
Expected: all (13) tests PASS.

- [ ] **Step 5: Confirm the production change is exactly one module, then commit**

Run:
```
git status --short
git diff --numstat main...HEAD -- mcp_server/src
```
Expected status: `?? mcp_server/src/rook/learning/plan_graph_param_binding.py` + `?? mcp_server/tests/test_plan_graph_param_binding.py` (+ plan if uncommitted). `operations_knowledge.json` NOT listed.

Commit:
```
git add mcp_server/src/rook/learning/plan_graph_param_binding.py mcp_server/tests/test_plan_graph_param_binding.py
git commit -m "feat(lm4k): pure bind_params_from_memory + unit tests

Learning-layer primitive sourcing producer params from graph.memory.facts along
explicit paths; returns merged params (no node write, no agent import, no graph
mutation, deep-copies, no partial success). Distinct ParamBindingResult/
ParamBindingFinding types. 13 unit tests incl. all finding codes + immutability +
AST import-boundary guard.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Pure chain guard (memory→params + composition)

**Files:**
- Create: `mcp_server/tests/test_plan_graph_param_binding_chain.py`

**Interfaces:**
- Consumes: `bind_params_from_memory` (Task 1), `select_template`, `initialize_graph`, `apply_producer_result`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `NodeOutcome`, `EXECUTION_PARAMS_KEY` (imported here, not in the helper).

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_plan_graph_param_binding_chain.py` with exactly this content:

```python
"""LM4K pure chain guard — bind the repair guid from graph.memory.facts, then compose
the 5-node chain to complete.

HONEST SCOPE: apply_producer_result consumes a RAW tool-result dict, NOT the node's
execution_params. So this guard proves (a) the helper sources the guid from the runtime
memory substrate into a real execution_params assignment, and (b) the graph still
composes to complete. It does NOT prove the bound guid drives a real repair dispatch --
only the live proof (test_live_repair_chain_memory_sourced_live.py) does that.

In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root. Separate file
from test_plan_graph_live_repair_memory.py (LM4J), which stays untouched.
"""

from __future__ import annotations

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import (
    NodeOutcome,
    apply_outcome,
    graph_status,
    initialize_graph,
)
from rook.learning.plan_graph_param_binding import bind_params_from_memory
from rook.learning.plan_graph_runner import apply_producer_result, apply_verifier_step
from rook.learning.plan_graph_templates import select_template


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair_verify",
    "language": "csharp",
}

_GUID = "lm4k-chain-guid"
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


def test_memory_sourced_repair_params_then_compose_to_complete():
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

    # SOURCE the repair guid from memory (nested path) and assign into execution_params.
    binding = bind_params_from_memory(
        _BASE_REPAIR_PARAMS, graph, {"guid": ("repair_anchor", "component_guid")}
    )
    assert binding.findings == ()
    assert binding.params["guid"] == _GUID
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = binding.params
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
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_plan_graph_param_binding_chain.py -v
```
Expected: `1 passed`. If it fails, capture the exact assertion and report — do not weaken it.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_plan_graph_param_binding_chain.py` (+ plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_plan_graph_param_binding_chain.py
git commit -m "test(lm4k): pure chain guard -- memory-sourced repair params + compose to complete

Sources the repair guid from graph.memory.facts via bind_params_from_memory,
assigns into execution_params (EXECUTION_PARAMS_KEY imported in the TEST), and
composes the 5-node chain to graph_status==complete. Honest scope: proves
memory->params binding + composition, NOT that the bound guid drives dispatch
(apply_producer_result consumes the raw dict).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Live proof (requires_rhino — memory-sourced guid drives the real repair)

**Files:**
- Create: `mcp_server/tests/test_live_repair_chain_memory_sourced_live.py`

**Interfaces:**
- Consumes: `bind_params_from_memory` (Task 1), `RookAgent`, `_mcp_tool_executor`, `EXECUTION_PARAMS_KEY`, `select_template`, `apply_verifier_step`, `apply_outcome`, `graph_status`, `NodeOutcome`, `build_live_producer_record`, `LiveProducerExpectation`, `_is_error`, `fresh_document`.

- [ ] **Step 1: Write the test file**

Create `mcp_server/tests/test_live_repair_chain_memory_sourced_live.py` with exactly this content:

```python
"""LM4K live proof -- the repair guid is SOURCED FROM graph.memory.facts (not from
evidence) and drives the real gh_update_script repair, with the declared-ref chain
from LM4J (no producer overrides) to graph_status=="complete".

create.evidence.repair_anchor.component_guid is captured ONLY as a CONTROL: the test
asserts the memory-sourced guid equals it, proving graph.memory.facts is the source of
truth carrying the right repair target. Automatic propagation INTO a runner is still
out of scope -- the test performs the assignment.

requires_rhino: deselected from CI; fresh_document + _ensure_gh_document skip when
Rhino/GH unreachable. Run (repo root, Rhino + Grasshopper open):
    pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_memory_sourced_live.py
"""

from __future__ import annotations

import pytest

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_runner import (
    LiveProducerExpectation,
    build_live_producer_record,
)
from rook.learning.plan_graph import NodeOutcome, apply_outcome, graph_status
from rook.learning.plan_graph_param_binding import bind_params_from_memory
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


async def test_memory_sourced_repair_guid_drives_live_repair(fresh_document):
    await _ensure_gh_document()

    selection = select_template(_DESCRIPTOR)
    assert selection.selected_template_id == "gh_csharp_create_verify_repair_verify"
    graph = selection.graph
    assert graph.nodes["create_script"].execution_ref == "gh_create_csharp_script:v1"
    assert graph.nodes["repair_same_component"].execution_ref == "gh_update_script:v1"

    # No ref override; set ONLY create execution_params (omit 'language' -- csharp alias).
    graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY] = {
        "code": "A = DefinitelyMissingSymbol;",
        "pins_in": [],
        "pins_out": ["A:double"],
        "name": "LM4KMemorySourcedLive",
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

    # --- SOURCE the repair guid FROM graph.memory.facts (not evidence). ---
    binding = bind_params_from_memory(
        {"code": "A = 42.0;", "mode": "body", "language": "csharp"},
        graph,
        {"guid": ("repair_anchor", "component_guid")},
    )
    assert binding.findings == ()
    assert binding.params["guid"] == repair_guid_control  # memory == evidence control
    graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY] = binding.params

    # --- Live dispatch 2: declared-ref repair, guid sourced from memory -> usable. ---
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
mcp_server/.venv/Scripts/python.exe -m pytest mcp_server/tests/test_live_repair_chain_memory_sourced_live.py --collect-only -q
```
Expected: collects `test_memory_sourced_repair_guid_drives_live_repair` with no import errors.

- [ ] **Step 3: Confirm no stray mutation, then commit**

Run:
```
git status --short
```
Expected: only `?? mcp_server/tests/test_live_repair_chain_memory_sourced_live.py` (+ plan if uncommitted). No `operations_knowledge.json`.

Commit:
```
git add mcp_server/tests/test_live_repair_chain_memory_sourced_live.py
git commit -m "test(lm4k): live proof -- memory-sourced repair guid drives live gh_update_script

Declared-ref chain (no overrides); after live create, sources the repair guid from
graph.memory.facts via bind_params_from_memory (nested path), with create.evidence
as a control assertion (memory==evidence), assigns into execution_params, and the
live gh_update_script repair drives the chain to complete. repair_record.tool_status
is None (unwrapped-success finding) preserved.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

- [ ] **Step 4: Live acceptance (run only with Rhino + Grasshopper open)** — PAUSE POINT

Authoritative live proof, run during a live acceptance pass. Run (from repo root):
```
mcp_server\.venv\Scripts\python.exe -m pytest -m requires_rhino mcp_server/tests/test_live_repair_chain_memory_sourced_live.py -v
```
Expected: `1 passed`. Creates a `LM4KMemorySourcedLive` C# component via the declared ref, repairs it with the **memory-sourced** guid, drives to `complete`. Mutates `knowledge/gh/operations_knowledge.json`.

**If it fails:** capture the exact assertion + `create_record.mismatches` / `repair_record.mismatches` / `binding.findings` and report; do NOT weaken the test.

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
Expected: all pass, including `test_plan_graph_param_binding.py` (13) and `test_plan_graph_param_binding_chain.py` (1) — gate rises from the LM4J baseline of 258 by 14 to 272.

- [ ] **Production change is exactly one module:**
```
git diff --numstat main...HEAD -- mcp_server/src
```
Expected: a single line for `mcp_server/src/rook/learning/plan_graph_param_binding.py` and nothing else.

- [ ] **Diff guard (whole branch):** `git diff --stat main...HEAD` lists exactly six paths — the spec, this plan, the helper module, and the three test files. No `operations_knowledge.json`.

## Self-Review

**Spec coverage:**
- Helper contract (signature, deep-copy, no node write, no agent import, no partial success) → Task 1 module + unit tests.
- All seven finding codes → Task 1 unit tests, each directly: `base_params_invalid`, `base_params_copy_failed` (via `_NoDeepcopy` base value), `param_key_invalid`, `memory_path_invalid`, `memory_fact_missing`, `memory_fact_invalid`, `memory_value_copy_failed` (via `_NoDeepcopy` memory value). Plus `test_no_partial_success_collects_and_returns_none` pins the no-partial contract.
- Distinct types `ParamBindingResult`/`ParamBindingFinding` → Task 1 module.
- Nested path live source + flat equivalence → Task 1 (`test_flat_path_equals_nested`), Tasks 2/3 (nested).
- Pure chain guard honest scope → Task 2 (docstring + comment).
- Live proof memory-sourced guid drives dispatch, evidence as control → Task 3.
- One-module production diff, restore `operations_knowledge.json`, no overrides, omit `language` → Global Constraints + Final verification + Task 3.

*Note:* `base_params_copy_failed` and `memory_value_copy_failed` are deterministically triggered by the local `_NoDeepcopy` fixture (a value whose `__deepcopy__` raises), used once as a base-params value and once as a memory value. All seven finding codes are directly unit-tested.

**Placeholder scan:** No TBD/TODO; every code step shows complete file content; every run step gives an exact command + expected output.

**Type consistency:** `bind_params_from_memory(base_params, graph, bindings) -> ParamBindingResult(.params, .findings)`; `ParamBindingFinding(.code, .severity, .param_key, .message)`; `apply_producer_result(...).outcome_status/.graph`; `apply_verifier_step(...).outcome_status/.graph`; `select_template(...).selected_template_id/.graph`; `initialize_graph(graph)`; `graph_status(graph)`; `RookAgent(tool_executor=...).run_live_producer_node(...).graph/.tool_name`; `build_live_producer_record(result, expectation).evaluated/.passed/.mismatches/.tool_status`; `EXECUTION_PARAMS_KEY` imported only in tests. Consistent across all tasks and matching merged modules.
