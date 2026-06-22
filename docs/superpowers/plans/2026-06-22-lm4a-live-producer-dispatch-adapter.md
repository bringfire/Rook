# LM4A Live Producer-Node Dispatch Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a single non-pure `agent/`-layer adapter that resolves one PlanGraph `artifact_producer` node to a dispatch call, fires it through an injected async dispatch callable, and delegates application to the pure runner.

**Architecture:** A new module `mcp_server/src/rook/agent/plan_graph_live.py` consumes the public pure PlanGraph seams (`runnable_nodes`, `projection_role_for_node`, `apply_producer_result`) but never alters or grows them. It performs side-effect-free admissibility + resolution + param-copy *before* the only live side effect (dispatch), then delegates post-dispatch application to `apply_producer_result`. Zero `learning/` changes.

**Tech Stack:** Python 3.12, dataclasses, `re`, `collections.abc`, pytest (async driven via `asyncio.run`, no plugin-mode dependency), `ast` for the import-boundary test.

**Spec:** `docs/superpowers/specs/2026-06-22-lm4a-live-producer-dispatch-adapter-design.md`

## Global Constraints

- Pure `learning/plan_graph_*` modules: **unchanged** this slice.
- Adapter imports public pure symbols only — no private `_producer_*`; no `tool_dispatcher` / `server` / ChatRunner import. The dispatcher arrives only as the injected `dispatch` callable.
- The dispatch callable is typed `Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]`; the adapter dispatches a detached plain `dict` via `deepcopy(dict(params_source))`.
- `EXECUTION_PARAMS_KEY = "execution_params"` is an adapter-owned constant; tests pin the literal.
- Closed 11-member `LiveProducerReason` union (exact members in Task 1).
- Admissibility + resolution + param-copy are side-effect-free and precede dispatch: a non-admissible or unresolvable node **never** fires a tool.
- `dispatch_failed` is **only** for the callable *raising*; a returned `{"success": False}` is a real raw result and flows into `apply_producer_result`.
- No template changes, no scheduler, no planner, no model calls, no HTTP, no Rhino.
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Full PlanGraph + new LM4A suite must stay green (≥191 + new tests).

---

## File Structure

| File | Responsibility |
|------|----------------|
| `mcp_server/src/rook/agent/plan_graph_live.py` (create) | The live adapter: constant, `LiveProducerReason`, `LiveProducerResult`, helpers `_resolve_tool_name` / `_check_admissibility` / `_resolve_params` / `_not_applied`, and public async `apply_live_producer_node`. |
| `mcp_server/tests/test_plan_graph_live.py` (create) | Unit tests: grammar table, admissibility, end-to-end happy/seam/fault paths, deep-copy isolation, dispatch-exception, bidirectional import-boundary. |

All four tasks build these two files incrementally.

---

### Task 1: Module foundation + tool-name resolution

**Files:**
- Create: `mcp_server/src/rook/agent/plan_graph_live.py`
- Create: `mcp_server/tests/test_plan_graph_live.py`

**Interfaces:**
- Consumes (public pure symbols): `from rook.learning.plan_graph import OutcomeStatus, PlanGraph, PlanGraphNode, runnable_nodes`; `from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY, projection_role_for_node`; `from rook.learning.plan_graph_runner import apply_producer_result`.
- Produces: `EXECUTION_PARAMS_KEY: str`; `LiveProducerReason` (Literal); `LiveProducerResult` (frozen dataclass: `graph, applied, node_id, tool_name, outcome_status, reason`); `_not_applied(graph, node_id, tool_name, reason) -> LiveProducerResult`; `_resolve_tool_name(execution_ref) -> tuple[str | None, LiveProducerReason | None]`.

- [ ] **Step 1: Write the failing tests** (`mcp_server/tests/test_plan_graph_live.py`)

```python
from __future__ import annotations

import asyncio
import ast
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphNode,
    initialize_graph,
)
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.agent.plan_graph_live import (
    EXECUTION_PARAMS_KEY,
    LiveProducerResult,
    apply_live_producer_node,
    _resolve_tool_name,
)


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
_ABSENT = object()


# ----- shared raw-result builders (real server contract) -----

def _usable_receipt() -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "repair_anchor": {"component_guid": COMPONENT_GUID},
    }


def _errors_receipt() -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": "created_with_errors",
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "verification": {"status": "failed", "target_error_count": 1},
        "repair_anchor": {
            "component_guid": COMPONENT_GUID,
            "pins_out": [{"name": "A", "type": "double"}],
        },
    }


def _usable_raw() -> dict:
    return {"success": True, "data": {"verified": True, "script_receipt": _usable_receipt()}}


def _error_raw() -> dict:
    # Real server contract: an errored script result is top-level success: False.
    return {"success": False, "data": {"verified": False, "script_receipt": _errors_receipt()}}


# ----- producer-node graph fixture -----

def _producer_graph(
    *,
    ready: bool = True,
    execution_ref: object = "gh_create_csharp_script:v1",
    role: object = "artifact_producer",
    with_params: bool = True,
    execution_params: object = None,
) -> PlanGraph:
    metadata: dict = {}
    if role is not _ABSENT:
        metadata[OUTCOME_PROJECTION_ROLE_KEY] = role
    if with_params:
        metadata[EXECUTION_PARAMS_KEY] = (
            execution_params
            if execution_params is not None
            else {"language": "csharp", "code": "// noop", "component_name": "C"}
        )
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component",
        execution_ref=execution_ref,
        metadata=metadata,
    )
    graph = PlanGraph(nodes={"create_script": node})
    return initialize_graph(graph) if ready else graph


# ----- fake dispatch spy -----

class _Spy:
    def __init__(self, raw: dict | None = None, raises: BaseException | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw if raw is not None else {"success": True, "data": {}}
        self._raises = raises

    async def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        if self._raises is not None:
            raise self._raises
        return self._raw


# ===== Task 1 tests: tool-name grammar + result shape =====

@pytest.mark.parametrize(
    "execution_ref, expected_name, expected_reason",
    [
        (None, None, "execution_ref_missing"),
        ("", None, "execution_ref_missing"),
        ("gh_create_csharp_script", "gh_create_csharp_script", None),
        ("gh_update_script:v1", "gh_update_script", None),
        ("tool:v123", "tool", None),
        (":v1", None, "execution_ref_invalid"),
        ("tool:", None, "execution_ref_invalid"),
        ("tool:v", None, "execution_ref_invalid"),
        ("tool with space", None, "execution_ref_invalid"),
    ],
)
def test_resolve_tool_name_grammar(execution_ref, expected_name, expected_reason):
    name, reason = _resolve_tool_name(execution_ref)
    assert name == expected_name
    assert reason == expected_reason


def test_live_producer_result_is_frozen():
    result = LiveProducerResult(
        graph=PlanGraph(),
        applied=False,
        node_id="create_script",
        tool_name=None,
        outcome_status=None,
        reason="unknown_node",
    )
    with pytest.raises(Exception):
        result.applied = True  # frozen dataclass
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py -v`
Expected: collection/import error — `ModuleNotFoundError: No module named 'rook.agent.plan_graph_live'`.

- [ ] **Step 3: Create the module foundation** (`mcp_server/src/rook/agent/plan_graph_live.py`)

```python
"""LM4A live producer-node dispatch adapter (Stage 5A).

Non-pure agent-layer adapter: resolves ONE PlanGraph ``artifact_producer`` node to
a dispatch call, fires it through an injected dispatch callable, and delegates
application to the pure runner (``apply_producer_result``). It CONSUMES the pure
PlanGraph seams and never alters or grows them.

Boundary invariants:
- Imports only PUBLIC pure symbols (``runnable_nodes``, ``projection_role_for_node``,
  ``apply_producer_result``, types). No private ``_producer_*`` helpers.
- Does NOT import the dispatcher / server / ChatRunner -- the dispatcher arrives
  only as the injected ``dispatch`` callable.
- Admissibility + tool-name resolution + param copy are ALL side-effect-free and
  precede dispatch: a non-admissible or unresolvable node never fires a tool.
- ``learning/plan_graph_*`` modules never import this adapter (agent -> learning,
  one direction).
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from rook.learning.plan_graph import (
    OutcomeStatus,
    PlanGraph,
    PlanGraphNode,
    runnable_nodes,
)
from rook.learning.plan_graph_projection import (
    OUTCOME_PROJECTION_ROLE_KEY,
    projection_role_for_node,
)
from rook.learning.plan_graph_runner import apply_producer_result


EXECUTION_PARAMS_KEY = "execution_params"

# A valid execution_ref is a non-whitespace, colon-free tool name with an
# optional trailing ``:vN`` version suffix (N = one or more digits). The tool
# name never contains a colon, so the only colon is the version separator.
_EXECUTION_REF_RE = re.compile(r"(?P<name>[^\s:]+)(?::v\d+)?")


LiveProducerReason = Literal[
    "unknown_node",
    "node_not_runnable",
    "role_missing",
    "role_invalid",
    "role_not_producer",
    "execution_ref_missing",
    "execution_ref_invalid",
    "execution_params_missing",
    "execution_params_invalid",
    "params_copy_failed",
    "dispatch_failed",
]


@dataclass(frozen=True)
class LiveProducerResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    tool_name: str | None
    outcome_status: OutcomeStatus | None
    reason: LiveProducerReason | None


def _not_applied(
    graph: PlanGraph,
    node_id: str,
    tool_name: str | None,
    reason: LiveProducerReason,
) -> LiveProducerResult:
    return LiveProducerResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        tool_name=tool_name,
        outcome_status=None,
        reason=reason,
    )


def _resolve_tool_name(
    execution_ref: Any,
) -> tuple[str | None, LiveProducerReason | None]:
    if execution_ref is None or execution_ref == "":
        return None, "execution_ref_missing"
    if not isinstance(execution_ref, str):
        return None, "execution_ref_missing"
    match = _EXECUTION_REF_RE.fullmatch(execution_ref)
    if match is None:
        return None, "execution_ref_invalid"
    return match.group("name"), None


# Stub so the test module imports cleanly; fully implemented in Task 3.
async def apply_live_producer_node(
    graph: PlanGraph,
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> LiveProducerResult:
    raise NotImplementedError  # implemented in Task 3
```

The stub references `Callable`, `Awaitable`, and `Any`, which are already imported at the top of the module (see the import block above). The stub keeps the Task 1 test file's top-level `from rook.agent.plan_graph_live import ... apply_live_producer_node` valid.

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py -v`
Expected: PASS — 10 grammar cases + frozen-result test green. The module imports cleanly (the `apply_live_producer_node` stub satisfies the test file's import); no Task 1 test invokes the stub.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/plan_graph_live.py mcp_server/tests/test_plan_graph_live.py
git commit -m "feat(lm4a): module foundation + execution_ref tool-name resolution"
```

---

### Task 2: Admissibility preflight

**Files:**
- Modify: `mcp_server/src/rook/agent/plan_graph_live.py` (add `_check_admissibility`)
- Test: `mcp_server/tests/test_plan_graph_live.py` (add admissibility tests)

**Interfaces:**
- Consumes: `runnable_nodes`, `OUTCOME_PROJECTION_ROLE_KEY`, `projection_role_for_node` (already imported in Task 1); the `_producer_graph` / `_ABSENT` fixtures from Task 1.
- Produces: `_check_admissibility(graph: PlanGraph, node_id: str) -> LiveProducerReason | None`.

- [ ] **Step 1: Write the failing tests** (append to `mcp_server/tests/test_plan_graph_live.py`)

```python
from rook.agent.plan_graph_live import _check_admissibility


@pytest.mark.parametrize(
    "graph_factory, node_id, expected",
    [
        (lambda: _producer_graph(), "create_script", None),
        (lambda: _producer_graph(), "missing", "unknown_node"),
        (lambda: _producer_graph(ready=False), "create_script", "node_not_runnable"),
        (lambda: _producer_graph(role=_ABSENT), "create_script", "role_missing"),
        (lambda: _producer_graph(role="banana"), "create_script", "role_invalid"),
        (lambda: _producer_graph(role="artifact_verifier"), "create_script", "role_not_producer"),
    ],
)
def test_check_admissibility(graph_factory, node_id, expected):
    assert _check_admissibility(graph_factory(), node_id) == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py::test_check_admissibility -v`
Expected: FAIL — `ImportError: cannot import name '_check_admissibility'`.

- [ ] **Step 3: Add the admissibility helper** (insert into `plan_graph_live.py` after `_resolve_tool_name`)

```python
def _check_admissibility(graph: PlanGraph, node_id: str) -> LiveProducerReason | None:
    if node_id not in graph.nodes:
        return "unknown_node"
    if node_id not in {node.id for node in runnable_nodes(graph)}:
        return "node_not_runnable"
    node = graph.nodes[node_id]
    if OUTCOME_PROJECTION_ROLE_KEY not in node.metadata:
        return "role_missing"
    role = projection_role_for_node(node)
    if role is None:
        return "role_invalid"
    if role != "artifact_producer":
        return "role_not_producer"
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py::test_check_admissibility -v`
Expected: PASS — all 6 cases green.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/plan_graph_live.py mcp_server/tests/test_plan_graph_live.py
git commit -m "feat(lm4a): adapter-local admissibility preflight (public primitives only)"
```

---

### Task 3: Params resolution + public async adapter

**Files:**
- Modify: `mcp_server/src/rook/agent/plan_graph_live.py` (add `_resolve_params`; replace the `apply_live_producer_node` stub with the full implementation)
- Test: `mcp_server/tests/test_plan_graph_live.py` (add end-to-end tests)

**Interfaces:**
- Consumes: `_check_admissibility`, `_resolve_tool_name`, `_not_applied` (Task 1/2), `apply_producer_result`, `deepcopy`, `Mapping`; the `_producer_graph` / `_Spy` / raw builders from Task 1.
- Produces: `_resolve_params(node: PlanGraphNode) -> tuple[dict[str, Any] | None, LiveProducerReason | None]`; the final `apply_live_producer_node` coroutine.

- [ ] **Step 1: Write the failing tests** (append to `mcp_server/tests/test_plan_graph_live.py`)

```python
# ----- helpers for params-copy and Mapping-subclass cases -----

class _ExplodingValue:
    def __deepcopy__(self, memo):
        raise RuntimeError("deepcopy of value failed")


class _WeirdMap(Mapping):
    """A Mapping that is NOT a dict (proves params is normalized to plain dict)."""

    def __init__(self, data: dict):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class _BadConversionMap(Mapping):
    """A Mapping whose dict(...) conversion fails (second params_copy_failed mode)."""

    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        raise RuntimeError("iteration boom")

    def __len__(self):
        return 1


def test_happy_path_applies_succeeded():
    graph = _producer_graph()
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == "gh_create_csharp_script"
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "gh_create_csharp_script"
    assert result.graph.nodes["create_script"].status == "succeeded"


def test_returned_failure_is_real_result_not_dispatch_failed():
    # success: False + created_with_errors is a REAL raw result, NOT dispatch_failed.
    graph = _producer_graph()
    spy = _Spy(raw=_error_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.reason is None
    assert result.reason != "dispatch_failed"
    assert result.applied is True
    # producer role: artifact existence -> succeeded, decoupled from tool failure
    assert result.outcome_status == "succeeded"
    node = result.graph.nodes["create_script"]
    assert node.status == "succeeded"
    assert node.evidence.tool_status == "failed"
    assert node.evidence.verified is False


@pytest.mark.parametrize(
    "graph_factory, node_id, expected_reason, expected_tool",
    [
        (lambda: _producer_graph(), "missing", "unknown_node", None),
        (lambda: _producer_graph(ready=False), "create_script", "node_not_runnable", None),
        (lambda: _producer_graph(role=_ABSENT), "create_script", "role_missing", None),
        (lambda: _producer_graph(role="banana"), "create_script", "role_invalid", None),
        (lambda: _producer_graph(role="artifact_verifier"), "create_script", "role_not_producer", None),
        (lambda: _producer_graph(execution_ref=None), "create_script", "execution_ref_missing", None),
        (lambda: _producer_graph(execution_ref=":v1"), "create_script", "execution_ref_invalid", None),
        (lambda: _producer_graph(with_params=False), "create_script", "execution_params_missing", "gh_create_csharp_script"),
        (lambda: _producer_graph(execution_params=["not", "a", "map"]), "create_script", "execution_params_invalid", "gh_create_csharp_script"),
        (lambda: _producer_graph(execution_params={"x": _ExplodingValue()}), "create_script", "params_copy_failed", "gh_create_csharp_script"),
    ],
)
def test_pre_dispatch_faults_never_dispatch(graph_factory, node_id, expected_reason, expected_tool):
    graph = graph_factory()
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, node_id, spy))

    assert result.applied is False
    assert result.reason == expected_reason
    assert result.tool_name == expected_tool
    assert result.outcome_status is None
    assert result.graph is graph          # input graph returned unchanged
    assert spy.calls == []                # NO side effect before admissibility/resolution


def test_params_copy_failed_on_dict_conversion():
    # Second params_copy_failed mode: a Mapping whose dict(...) conversion raises.
    graph = _producer_graph(execution_params=_BadConversionMap())
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.applied is False
    assert result.reason == "params_copy_failed"
    assert result.tool_name == "gh_create_csharp_script"
    assert spy.calls == []


def test_dispatched_params_is_plain_dict_not_mapping_subclass():
    source = {"language": "csharp", "code": "// x"}
    graph = _producer_graph(execution_params=_WeirdMap(source))
    spy = _Spy(raw=_usable_raw())

    asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    dispatched = spy.calls[0][1]
    assert type(dispatched) is dict       # plain dict, NOT a Mapping subclass
    assert dispatched == source


def test_dispatched_params_detached_from_node_metadata():
    params = {"code": "// original", "nested": {"k": 1}}
    graph = _producer_graph(execution_params=params)
    spy = _Spy(raw=_usable_raw())

    asyncio.run(apply_live_producer_node(graph, "create_script", spy))
    dispatched = spy.calls[0][1]

    # Mutate node metadata after the call; the dispatched dict must be unaffected.
    meta_params = graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    meta_params["code"] = "// mutated"
    meta_params["nested"]["k"] = 999

    assert dispatched is not meta_params
    assert dispatched["code"] == "// original"
    assert dispatched["nested"]["k"] == 1


def test_dispatch_exception_is_dispatch_failed():
    graph = _producer_graph()
    spy = _Spy(raises=RuntimeError("transport down"))

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.tool_name == "gh_create_csharp_script"
    assert result.outcome_status is None
    assert result.graph is graph          # input preserved, no synthesized raw result
    assert len(spy.calls) == 1            # dispatch WAS attempted exactly once


def test_admissibility_precedes_resolution():
    # Two coexisting faults: non-runnable AND missing execution_ref.
    graph = _producer_graph(ready=False, execution_ref=None)
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.reason == "node_not_runnable"   # admissibility wins
    assert spy.calls == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py -v`
Expected: the new end-to-end tests FAIL — `apply_live_producer_node` raises `NotImplementedError` (stub from Task 1). The Task 1/2 tests still pass.

- [ ] **Step 3: Add `_resolve_params` and the full adapter** (in `plan_graph_live.py`: insert `_resolve_params` after `_check_admissibility`, then replace the `apply_live_producer_node` stub body)

```python
def _resolve_params(
    node: PlanGraphNode,
) -> tuple[dict[str, Any] | None, LiveProducerReason | None]:
    if EXECUTION_PARAMS_KEY not in node.metadata:
        return None, "execution_params_missing"
    params_source = node.metadata[EXECUTION_PARAMS_KEY]
    if not isinstance(params_source, Mapping):
        return None, "execution_params_invalid"
    try:
        params = deepcopy(dict(params_source))
    except Exception:
        return None, "params_copy_failed"
    return params, None


async def apply_live_producer_node(
    graph: PlanGraph,
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> LiveProducerResult:
    """Drive one live producer step: resolve -> dispatch -> delegate-apply.

    Side-effect-free admissibility + tool-name resolution + param copy precede the
    only live side effect (``dispatch``). A returned ``{"success": False}`` is a real
    raw result (flows into ``apply_producer_result``); only the callable *raising*
    is ``dispatch_failed``. Post-dispatch application is delegated to the pure
    runner, which stays authoritative. Every not-applied path returns the input
    graph unchanged.
    """
    reason = _check_admissibility(graph, node_id)
    if reason is not None:
        return _not_applied(graph, node_id, None, reason)

    node = graph.nodes[node_id]

    tool_name, reason = _resolve_tool_name(node.execution_ref)
    if reason is not None:
        return _not_applied(graph, node_id, None, reason)

    params, reason = _resolve_params(node)
    if reason is not None:
        return _not_applied(graph, node_id, tool_name, reason)

    try:
        raw = await dispatch(tool_name, params)
    except Exception:
        return _not_applied(graph, node_id, tool_name, "dispatch_failed")

    inner = apply_producer_result(graph, node_id, raw)
    return LiveProducerResult(
        graph=inner.graph,
        applied=inner.applied,
        node_id=node_id,
        tool_name=tool_name,
        outcome_status=inner.outcome_status,
        reason=inner.reason,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py -v`
Expected: PASS — happy path, the seam, all 10 pre-dispatch faults (spy never called), both `params_copy_failed` modes, plain-dict + detached-copy proofs, `dispatch_failed`, and precedence all green.

- [ ] **Step 5: Commit**

```bash
git add mcp_server/src/rook/agent/plan_graph_live.py mcp_server/tests/test_plan_graph_live.py
git commit -m "feat(lm4a): params resolution + apply_live_producer_node (dispatch + delegate)"
```

---

### Task 4: Bidirectional import-boundary test

**Files:**
- Test: `mcp_server/tests/test_plan_graph_live.py` (add two AST tests)

**Interfaces:**
- Consumes: `ast`, `Path` (imported in Task 1); the adapter module and a pure module for path discovery.
- Produces: `test_adapter_imports_only_public_pure_symbols`, `test_pure_modules_do_not_import_live_adapter`.

- [ ] **Step 1: Write the failing tests** (append to `mcp_server/tests/test_plan_graph_live.py`)

```python
import rook.agent.plan_graph_live as _live_mod
from rook.learning import plan_graph as _pg_mod

_ADAPTER_PATH = Path(_live_mod.__file__)
_LEARNING_DIR = Path(_pg_mod.__file__).parent

_ALLOWED_ROOK_IMPORTS = {
    "rook.learning.plan_graph",
    "rook.learning.plan_graph_projection",
    "rook.learning.plan_graph_runner",
}
_FORBIDDEN_SUBSTRINGS = ("tool_dispatcher", "rook.server", "chat", "ChatRunner")


def test_adapter_imports_only_public_pure_symbols():
    tree = ast.parse(_ADAPTER_PATH.read_text(encoding="utf-8"))
    imported_modules: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.append(module)
            for alias in node.names:
                assert alias.name != "*", "no star imports in the live adapter"
                assert not alias.name.startswith("_producer"), (
                    f"adapter must not import private runner helper {alias.name!r}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)

    joined = " ".join(imported_modules)
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in joined, f"adapter must not import {forbidden!r}"

    for module in imported_modules:
        if module.startswith("rook."):
            assert module in _ALLOWED_ROOK_IMPORTS, (
                f"unexpected rook import in live adapter: {module!r}"
            )


def test_pure_modules_do_not_import_live_adapter():
    pure_files = sorted(_LEARNING_DIR.glob("plan_graph*.py"))
    assert pure_files, "expected to find learning/plan_graph*.py modules"

    for pyfile in pure_files:
        tree = ast.parse(pyfile.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "plan_graph_live" not in (node.module or ""), (
                    f"{pyfile.name} must not import the live adapter"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "plan_graph_live" not in alias.name, (
                        f"{pyfile.name} must not import the live adapter"
                    )
```

- [ ] **Step 2: Run the tests to verify they pass immediately (they assert an already-true invariant)**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py -k boundary_or_import -v`
Then run the two by name: `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py::test_adapter_imports_only_public_pure_symbols tests/test_plan_graph_live.py::test_pure_modules_do_not_import_live_adapter -v`
Expected: PASS — the adapter (from Task 3) already satisfies both directions. (These are guard tests: they pass now and fail loudly if a future edit imports the dispatcher or a pure module imports the adapter.) If either fails, the Task 3 import block violated the boundary — fix the import, not the test.

- [ ] **Step 3: Run the full new suite + a PlanGraph regression sweep**

Run (from `mcp_server/`):
`.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py -v`
Expected: PASS — entire LM4A file green.

Then the pure regression sweep (must be unchanged):
`.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph.py tests/test_plan_graph_runner.py tests/test_plan_graph_outcomes.py tests/test_plan_graph_projection.py tests/test_plan_graph_templates.py tests/test_plan_graph_verifiers.py tests/test_plan_graph_walker.py tests/test_plan_graph_bridge.py -q`
Expected: PASS — ≥191 prior PlanGraph tests still green (zero `learning/` changes).

- [ ] **Step 4: Commit**

```bash
git add mcp_server/tests/test_plan_graph_live.py
git commit -m "test(lm4a): bidirectional import-boundary guard (adapter <-> pure layer)"
```

---

## Self-Review

**1. Spec coverage:**
- Boundary & dependency direction → Task 1 module docstring + Task 4 bidirectional guard. ✓
- Public API (constant, `LiveProducerReason`, `LiveProducerResult`, async signature) → Task 1 + Task 3. ✓
- Dispatch-callable type + `deepcopy(dict(...))` normalization → Task 3 `_resolve_params`, proven by `test_dispatched_params_is_plain_dict_not_mapping_subclass`. ✓
- Control-flow strict order → Task 3 `apply_live_producer_node`; precedence pinned by `test_admissibility_precedes_resolution` + the parametrized pre-dispatch table. ✓
- `execution_ref` grammar table → Task 1 `test_resolve_tool_name_grammar` (all 9 rows). ✓
- 11 reasons, input-graph-unchanged, `tool_name` semantics → Task 3 parametrized + dispatch/seam tests. ✓
- `dispatch_failed` vs returned failure → `test_dispatch_exception_is_dispatch_failed` + `test_returned_failure_is_real_result_not_dispatch_failed`. ✓
- The live seam (success:False → succeeded, evidence failed) → `test_returned_failure_is_real_result_not_dispatch_failed`. ✓
- Both `params_copy_failed` modes → parametrized (value deepcopy) + `test_params_copy_failed_on_dict_conversion` (dict conversion). ✓
- Out-of-scope (no template/`learning/` changes) → no task touches `learning/` or `plan_graph_templates.py`; Task 4 Step 3 regression sweep proves it. ✓

**2. Placeholder scan:** No TBD/TODO/"handle edge cases"; every code step shows complete code. The only deliberate temporary is the Task 1 `apply_live_producer_node` stub, explicitly replaced in Task 3. ✓

**3. Type consistency:** `LiveProducerResult` fields (`graph, applied, node_id, tool_name, outcome_status, reason`) are identical across Task 1 definition, Task 3 construction, and all assertions. `_resolve_tool_name` / `_check_admissibility` / `_resolve_params` signatures match their call sites in `apply_live_producer_node`. `EXECUTION_PARAMS_KEY` and `OUTCOME_PROJECTION_ROLE_KEY` used consistently. ✓

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — batch execution with checkpoints.
