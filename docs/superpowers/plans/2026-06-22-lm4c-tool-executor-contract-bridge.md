# LM4C ToolExecutor Contract Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one agent-layer function that drives a live PlanGraph producer node from the production `ToolExecutor` callable (sync-or-async), normalizing awaitability and delegating to the LM4B kernel.

**Architecture:** A single new coroutine `run_live_producer_node_with_executor` in the existing composition root `agent/plan_graph_live_dispatch.py`, beside `run_live_producer_node`. It wraps the looser `ToolExecutor` contract (`Callable[[str, dict], Any]`) in an inner async `dispatch` that awaits only if the result is awaitable, then delegates to `run_live_producer_node`. No result validation, no new error taxonomy, no call-site edits.

**Tech Stack:** Python 3.12, stdlib `inspect`, pytest driven via `asyncio.run`.

**Spec:** `docs/superpowers/specs/2026-06-22-lm4c-tool-executor-contract-bridge-design.md`

## Global Constraints

- The new function lives in **existing** `mcp_server/src/rook/agent/plan_graph_live_dispatch.py` — no sibling module.
- Executor parameter typed **structurally**: `Callable[[str, dict[str, Any]], Any]`. **No** `from rook.agent.base_agent import ToolExecutor` (the import-boundary AST test walks `TYPE_CHECKING` imports too; that import would add `rook.agent.base_agent`, break the allowlist, and couple the seam).
- New runtime import: **stdlib `inspect` only.** No `ToolDispatcher`, no `tool_dispatcher`, no `rook.server`, no `rook.agent.chat`, no `ChatRunner`.
- **Normalize awaitability only** — never inspect/validate result shape. A malformed/non-dict result flows into LM4A's existing raw-result handling.
- **No try/except in the wrapper.** A raising executor (sync or async) propagates through the inner `dispatch` and is caught by LM4A as `dispatch_failed`. One error taxonomy, LM4A's.
- **No edits to `base_agent.py`, `spawn.py`, `chat_runner.py`** — they stay byte-stable. No scheduler, no port/targeting, no template `execution_params` mutation, no Rhino/HTTP.
- The module's existing `test_live_dispatch_module_import_boundary` stays green **unchanged**; no positive "must import `inspect`" assertion is added (pin behavior, not the stdlib mechanism).
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `mcp_server/src/rook/agent/plan_graph_live_dispatch.py` | Modify (add `import inspect`; add one coroutine) | The live-dispatch composition root; now also bridges the looser `ToolExecutor` contract |
| `mcp_server/tests/test_plan_graph_live_dispatch.py` | Modify (add 5 tests) | Behavioral coverage for the contract bridge across executor shapes |

One task: the function and its five tests are a single cohesive, independently-testable deliverable.

---

### Task 1: `run_live_producer_node_with_executor`

**Files:**
- Modify: `mcp_server/src/rook/agent/plan_graph_live_dispatch.py`
- Test: `mcp_server/tests/test_plan_graph_live_dispatch.py`

**Interfaces:**
- Consumes (already in the module): `run_live_producer_node(graph, node_id, dispatch)`; `from __future__ import annotations`; `from collections.abc import Awaitable, Callable`; `from typing import TYPE_CHECKING, Any`; the `TYPE_CHECKING` imports of `LiveProducerResult` and `PlanGraph`.
- Consumes (already in the test module): `run_live_producer_node`, `EXECUTION_PARAMS_KEY`, `OUTCOME_PROJECTION_ROLE_KEY`, `PlanGraph`, `PlanGraphNode`, `COMPONENT_GUID`, `PROBE_TOOL_NAME`, `_usable_raw()`, `_error_raw()`, `_producer_graph(declared_params)`, `asyncio`.
- Produces: `async def run_live_producer_node_with_executor(graph, node_id, tool_executor: Callable[[str, dict[str, Any]], Any]) -> LiveProducerResult`.

**Reference — the existing module (LM4B), for context:**

```python
"""LM4B live-dispatch composition root for one PlanGraph producer node."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_live import apply_live_producer_node

if TYPE_CHECKING:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph import PlanGraph


async def run_live_producer_node(
    graph: "PlanGraph",
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> "LiveProducerResult":
    """Drive one live producer node through an injected dispatch callable."""
    return await apply_live_producer_node(graph, node_id, dispatch)
```

- [ ] **Step 1: Write the failing tests** (append to `mcp_server/tests/test_plan_graph_live_dispatch.py`)

These reuse the module's existing fixtures (`_usable_raw`, `_producer_graph`, `PROBE_TOOL_NAME`, etc.) and import the not-yet-written function.

```python
from rook.agent.plan_graph_live_dispatch import run_live_producer_node_with_executor


_DECLARED_PARAMS = {"language": "csharp", "code": "// noop", "component_name": "C"}


def _run_with_executor(executor):
    graph = _producer_graph(_DECLARED_PARAMS)
    result = asyncio.run(
        run_live_producer_node_with_executor(graph, "create_script", executor)
    )
    return result, graph


def test_executor_sync_dict_drives_live_seam():
    """A plain sync executor returning a dict must drive LM4A's live seam --
    not merely be awaited. Assert producer outcome + evidence, not just return."""
    seen: list[dict] = []

    def executor(name, params):
        seen.append({"name": name, "params": params})
        return _usable_raw()

    result, graph = _run_with_executor(executor)

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    node = result.graph.nodes["create_script"]
    assert node.status == "succeeded"
    assert node.evidence is not None
    assert node.evidence.tool_status == "success"
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph
    # Executor received the declared params, no injected port.
    assert seen == [{"name": PROBE_TOOL_NAME, "params": _DECLARED_PARAMS}]


def test_executor_async_dict_drives_live_seam():
    """An async executor returning a dict drives the same successful outcome."""

    async def executor(name, params):
        return _usable_raw()

    result, _graph = _run_with_executor(executor)

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"


def test_executor_sync_raise_is_dispatch_failed():
    """A sync executor raising maps to LM4A dispatch_failed; input graph preserved."""

    def executor(name, params):
        raise RuntimeError("sync transport down")

    result, graph = _run_with_executor(executor)

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.outcome_status is None
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph is graph  # not-applied -> input graph unchanged


def test_executor_async_raise_is_dispatch_failed():
    """An async executor raising on await maps to dispatch_failed; graph preserved."""

    async def executor(name, params):
        raise RuntimeError("async transport down")

    result, graph = _run_with_executor(executor)

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.outcome_status is None
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph is graph  # not-applied -> input graph unchanged


def test_executor_non_dict_flows_to_applied_blocked():
    """A non-dict result is NOT validated by the wrapper: it flows into LM4A's
    raw-result handling and becomes an APPLIED blocked outcome (a fresh graph
    with the node blocked), never dispatch_failed."""

    def executor(name, params):
        return "not a dict"

    result, graph = _run_with_executor(executor)

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "blocked"
    node = result.graph.nodes["create_script"]
    assert node.status == "blocked"
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live_dispatch.py -v`
Expected: a **collection error for the whole module** — `ImportError: cannot import name 'run_live_producer_node_with_executor' from 'rook.agent.plan_graph_live_dispatch'`. (The new `from … import run_live_producer_node_with_executor` line runs at import time, so all tests in the file error at collection until Step 3 adds the function — this is the expected TDD-red state.) Confirm the error names the missing symbol.

- [ ] **Step 3: Add the function** (edit `mcp_server/src/rook/agent/plan_graph_live_dispatch.py`)

Add `import inspect` to the imports, and append the new coroutine after `run_live_producer_node`. Final module:

```python
"""LM4B live-dispatch composition root for one PlanGraph producer node.

Also hosts the LM4C ``ToolExecutor`` contract bridge: the production agent seam
exposes the looser ``Callable[[str, dict], Any]`` (sync-or-async) shape, which
``run_live_producer_node_with_executor`` normalizes before delegating to the
strict-async kernel. Result shape and error taxonomy stay owned by LM4A.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_live import apply_live_producer_node

if TYPE_CHECKING:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph import PlanGraph


async def run_live_producer_node(
    graph: "PlanGraph",
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> "LiveProducerResult":
    """Drive one live producer node through an injected dispatch callable."""
    return await apply_live_producer_node(graph, node_id, dispatch)


async def run_live_producer_node_with_executor(
    graph: "PlanGraph",
    node_id: str,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> "LiveProducerResult":
    """Drive one live producer node from a production ``ToolExecutor`` callable.

    ``tool_executor`` follows the agent seam's looser contract
    (``Callable[[str, dict], Any]`` -- sync OR async return). The inner ``dispatch``
    normalizes awaitability only, then delegates to the LM4B/LM4A kernel. It does
    not validate the result: a malformed/non-dict result flows into LM4A's
    raw-result handling, and a raising executor maps to LM4A ``dispatch_failed``.
    """
    async def dispatch(name: str, params: dict[str, Any]) -> dict[str, Any]:
        result = tool_executor(name, params)
        if inspect.isawaitable(result):
            result = await result
        return result

    return await run_live_producer_node(graph, node_id, dispatch)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live_dispatch.py -v`
Expected: PASS — all 8 tests (3 existing LM4B + 5 new LM4C). Confirm `test_live_dispatch_module_import_boundary` still passes unchanged (it governs the whole module source; `inspect` is stdlib, not rook-scoped, so the allowlist is untouched).

- [ ] **Step 5: Run the focused regression suite**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_plan_graph_live.py tests/test_plan_graph_live_dispatch.py -q`
Expected: PASS — LM4A (37) + LM4B/LM4C dispatch-seam (8) all green. (No `learning/` or pure-layer files were touched, so the broad purity-probe suite — which must run from the repo root — is unaffected by this slice.)

- [ ] **Step 6: Commit**

```bash
git add mcp_server/src/rook/agent/plan_graph_live_dispatch.py mcp_server/tests/test_plan_graph_live_dispatch.py
git commit -m "feat(lm4c): ToolExecutor contract bridge for one live producer node"
```

---

## Self-Review

**1. Spec coverage:**
- Placement in existing composition root → Task 1 module edit. ✓
- `run_live_producer_node_with_executor` signature + structural `Callable` (no `base_agent` import) → Step 3. ✓
- Normalize awaitability only, no result validation → Step 3 inner `dispatch`; pinned by `test_executor_non_dict_flows_to_applied_blocked`. ✓
- Raising executor → `dispatch_failed` (sync + async) → `test_executor_sync_raise_is_dispatch_failed` / `test_executor_async_raise_is_dispatch_failed`. ✓
- Non-vacuous sync-dict live-seam proof (tool_name/applied/outcome/evidence) → `test_executor_sync_dict_drives_live_seam`. ✓
- Async-dict path → `test_executor_async_dict_drives_live_seam`. ✓
- Graph identity: `result.graph is graph` only on the two raise (not-applied) cases; happy + non-dict assert `result.graph is not graph` → encoded in the tests. ✓
- Boundary test stays green unchanged, no `inspect` assertion → Step 4 verification, no edit to `test_live_dispatch_module_import_boundary`. ✓
- No `base_agent`/`spawn`/`chat_runner` edits → only two files touched. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. ✓

**3. Type consistency:** `run_live_producer_node_with_executor(graph, node_id, tool_executor)` is referenced identically in the test helper `_run_with_executor` and Step 3's definition. Reuses LM4B's existing fixtures verbatim (`_producer_graph`, `_usable_raw`, `PROBE_TOOL_NAME`). The sync-dict evidence assertion uses `tool_status == "success"` (matching `_usable_raw()`'s `{"success": True, ...}` → `normalize_tool_result` status `"success"`). ✓

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — batch execution with checkpoints.
