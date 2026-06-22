# LM4D Opt-in RookAgent.run_live_producer_node Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one opt-in, non-LLM method on `RookAgent` that drives a single PlanGraph producer node against the agent's own `_tool_executor`, delegating to the LM4C contract bridge.

**Architecture:** An additive method `run_live_producer_node(self, graph, node_id)` on `RookAgent` in `base_agent.py`, placed near the existing explicit utility methods (e.g. `test_connection`), that calls `run_live_producer_node_with_executor(graph, node_id, self._tool_executor)`. The LLM run loop (`_run_loop`) is byte-stable; `spawn.py` and `chat_runner.py` are unchanged.

**Tech Stack:** Python 3.12, pytest driven via `asyncio.run`, stdlib only.

**Spec:** `docs/superpowers/specs/2026-06-22-lm4d-agent-live-producer-method-design.md`

## Global Constraints

- `base_agent.py` change is **only** an additive top-level import + one additive method. `_run_loop` is **byte-stable** (no code added to or removed from it). Do NOT say "base_agent byte-stable" — the file is touched.
- `spawn.py` and `mcp_server/src/rook/agent/chat/chat_runner.py`: **unchanged**.
- `plan_graph_live.py`, `plan_graph_live_dispatch.py`, pure `learning/plan_graph_*`: **unchanged**.
- Top-level runtime import only (no import cycle — empirically verified): `from .plan_graph_live_dispatch import run_live_producer_node_with_executor`. Type-only imports go under the existing `TYPE_CHECKING` block; signature uses quoted `"PlanGraph"` / `"LiveProducerResult"`.
- Tests use **injected** sync/async/raising executors. **No real `ToolDispatcher`, no Rhino, no HTTP.** Construct `RookAgent(tool_executor=spy)` minimally; do NOT mock the agent.
- Graph identity: `result.graph is graph` only on the raising (not-applied) case; sync/async applied paths return a fresh reducer graph (`result.graph is not graph`).
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Focused PlanGraph gate runs from the **repo root** and stays **236** (LM4D tests live in a separate agent test file).

---

## File Structure

| File | Change | Responsibility |
|------|--------|----------------|
| `mcp_server/src/rook/agent/base_agent.py` | Modify (additive import + 1 method) | Adds the opt-in live-producer entry point on the agent that owns `_tool_executor` |
| `mcp_server/tests/test_base_agent_live_producer.py` | Create | Proves the method reaches `self._tool_executor` across sync/async/raising executors, plus construction has no executor side effect |

One task: the method and its tests are a single cohesive, independently-testable deliverable.

---

### Task 1: `RookAgent.run_live_producer_node`

**Files:**
- Modify: `mcp_server/src/rook/agent/base_agent.py` (import near line 50; `TYPE_CHECKING` block at line 33; method near `test_connection` at line 1177)
- Create: `mcp_server/tests/test_base_agent_live_producer.py`

**Interfaces:**
- Consumes: `run_live_producer_node_with_executor(graph, node_id, tool_executor)` (LM4C, in `agent/plan_graph_live_dispatch.py`); `RookAgent.__init__(tool_executor=...)`; `self._tool_executor`; LM4A `LiveProducerResult` (fields `graph, applied, node_id, tool_name, outcome_status, reason`); `EXECUTION_PARAMS_KEY`, `OUTCOME_PROJECTION_ROLE_KEY`, `PlanGraph`, `PlanGraphNode`.
- Produces: `async RookAgent.run_live_producer_node(self, graph, node_id) -> LiveProducerResult`.

- [ ] **Step 1: Write the failing tests** (`mcp_server/tests/test_base_agent_live_producer.py`)

```python
from __future__ import annotations

import asyncio

from rook.agent.base_agent import RookAgent
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
PROBE_TOOL_NAME = "lm4d_live_producer_probe"
_DECLARED_PARAMS = {"language": "csharp", "code": "// noop", "component_name": "C"}


def _usable_raw() -> dict:
    return {
        "success": True,
        "data": {
            "verified": True,
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
                "repair_anchor": {"component_guid": COMPONENT_GUID},
            },
        },
    }


def _producer_graph(declared_params: dict) -> PlanGraph:
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component via RookAgent live producer method",
        execution_ref=PROBE_TOOL_NAME,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={"create_script": node})
    node.status = "ready"
    return graph


class _SyncSpy:
    """A plain (non-async) ToolExecutor that records calls and returns a dict."""

    def __init__(self, raw: dict):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw

    def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        return self._raw


class _AsyncSpy:
    """An async ToolExecutor that records calls and returns a dict."""

    def __init__(self, raw: dict):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw

    async def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        return self._raw


def test_construction_does_not_invoke_executor():
    """RookAgent(tool_executor=spy) must not call the executor or build a
    dispatcher at construction -- the executor is only used when the method runs."""
    spy = _SyncSpy(_usable_raw())
    RookAgent(tool_executor=spy)
    assert spy.calls == []


def test_method_drives_node_via_sync_executor():
    spy = _SyncSpy(_usable_raw())
    agent = RookAgent(tool_executor=spy)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    # Applied path returns a fresh reducer graph (NOT identity).
    assert result.graph is not graph
    # Proves the method reached self._tool_executor with the node's tool + params.
    assert spy.calls == [(PROBE_TOOL_NAME, _DECLARED_PARAMS)]


def test_method_drives_node_via_async_executor():
    spy = _AsyncSpy(_usable_raw())
    agent = RookAgent(tool_executor=spy)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    assert result.graph is not graph
    assert spy.calls == [(PROBE_TOOL_NAME, _DECLARED_PARAMS)]


def test_method_raising_executor_is_dispatch_failed():
    def executor(name, params):
        raise RuntimeError("transport down")

    agent = RookAgent(tool_executor=executor)
    graph = _producer_graph(_DECLARED_PARAMS)

    result = asyncio.run(agent.run_live_producer_node(graph, "create_script"))

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.outcome_status is None
    assert result.tool_name == PROBE_TOOL_NAME
    # Not-applied -> the input graph object is returned unchanged.
    assert result.graph is graph
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_base_agent_live_producer.py -v`
Expected: the 3 method tests FAIL with `AttributeError: 'RookAgent' object has no attribute 'run_live_producer_node'`. `test_construction_does_not_invoke_executor` already PASSES (it only constructs the agent). Confirm the failures name the missing method.

(If `RookAgent(tool_executor=spy)` itself errors at construction — e.g. noisy default state — add `tool_schemas=[]` to the constructor call in each test: `RookAgent(tool_executor=spy, tool_schemas=[])`. Do NOT mock the agent. `tool_schemas` defaults to `[]` already, so this is only a fallback if construction is noisy.)

- [ ] **Step 3: Add the import and TYPE_CHECKING types** (`mcp_server/src/rook/agent/base_agent.py`)

Extend the existing `TYPE_CHECKING` block (currently lines 33-34):

```python
if TYPE_CHECKING:
    from .tool_registry import ToolRegistry
    from .plan_graph_live import LiveProducerResult
    from ..learning.plan_graph import PlanGraph
```

Add the runtime import in the agent-layer import group — immediately after `from .tool_groups import TOOL_TRANSITIONS, TOOL_GROUP_TRIGGERS` (line 50):

```python
from .tool_groups import TOOL_TRANSITIONS, TOOL_GROUP_TRIGGERS
from .plan_graph_live_dispatch import run_live_producer_node_with_executor
```

- [ ] **Step 4: Add the method** (`mcp_server/src/rook/agent/base_agent.py`)

Insert immediately after the `test_connection` method (after line 1187, before `_load_env`):

```python
    async def run_live_producer_node(
        self, graph: "PlanGraph", node_id: str
    ) -> "LiveProducerResult":
        """Drive one live producer node against this agent's tool executor.

        Opt-in, one-node, non-LLM: delegates to the LM4C contract bridge using the
        agent's own ``_tool_executor``. Does not touch the LLM run loop; no
        scheduler, no graph selection. A raising executor maps to LM4A
        ``dispatch_failed``; a malformed result flows into LM4A's raw-result
        handling -- this method owns neither result shape nor error taxonomy.
        """
        return await run_live_producer_node_with_executor(
            graph, node_id, self._tool_executor
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider tests/test_base_agent_live_producer.py -v`
Expected: PASS — all 4 tests (construction-no-call, sync, async, raising).

- [ ] **Step 6: Full focused PlanGraph gate (from repo root) + py_compile**

The focused PlanGraph gate proves no PlanGraph regression. LM4D's tests are in a separate agent file, so the gate count is unchanged.

Run (from `C:\UDEV\Rook`): `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph*.py -q`
Expected: **236 passed**.

Run (from `C:\UDEV\Rook`, single line — PowerShell-safe, no `\` continuations):
```
mcp_server/.venv/Scripts/python.exe -m py_compile mcp_server/src/rook/agent/base_agent.py mcp_server/tests/test_base_agent_live_producer.py
```
Expected: no output, exit 0.

- [ ] **Step 7: No-hot-path-diff review gate (specific)**

Confirm the `base_agent.py` change is purely additive and does not touch the hot execution path. Baseline is `origin/main` (run `git fetch origin` first if stale). Commands are PowerShell-native. Run (from `C:\UDEV\Rook`):

```
git diff --numstat origin/main -- mcp_server/src/rook/agent/base_agent.py
```
Expected: one row; the **second column (deletions) is `0`** — purely additive (insertions only, zero deletions/modifications).

```
git diff --unified=0 origin/main -- mcp_server/src/rook/agent/base_agent.py | Select-String -Pattern '^@@'
```
Expected: every hunk header lands in the **import / `TYPE_CHECKING` region (~lines 31-51)** or **near the new explicit utility method, after `test_connection` (~line 1187)**. **No hunk** falls within the loop/execute region — `_run_loop` (415), `_execute_tool` (904), or `_execute_local_tool` (1132). (Zero-deletions alone is not enough: this confirms no lines were *inserted into* the hot methods either.)

```
git diff --name-only origin/main -- mcp_server/src/rook/agent/spawn.py mcp_server/src/rook/agent/chat/chat_runner.py
```
Expected: **empty** — both files unchanged.

If any of these fail, the edit landed in the wrong place — move the method/import, do not adjust the gate.

- [ ] **Step 8: Commit**

```bash
git add mcp_server/src/rook/agent/base_agent.py mcp_server/tests/test_base_agent_live_producer.py
git commit -m "feat(lm4d): opt-in RookAgent.run_live_producer_node (live agent-flow wiring)"
```

---

## Self-Review

**1. Spec coverage:**
- Additive opt-in method on `RookAgent`, near explicit utility methods, outside `_run_loop` → Step 4. ✓
- Delegates to LM4C via `self._tool_executor` → Step 4 body. ✓
- Top-level import (no cycle) + `TYPE_CHECKING` quoted types → Step 3. ✓
- Tests prove the method reaches `self._tool_executor` with the node's tool + params (sync + async), spy records calls → Steps 1, `test_method_drives_node_via_{sync,async}_executor`. ✓
- Raising executor → `dispatch_failed`, input graph preserved (`is graph`) → `test_method_raising_executor_is_dispatch_failed`. ✓
- Graph identity: `is not graph` on applied (sync/async), `is graph` on raising → encoded in tests. ✓
- Constructor side-effect (no executor call / no dispatcher build), kept cheap via spy → `test_construction_does_not_invoke_executor`. ✓
- No real `ToolDispatcher`/Rhino → plain injected callables only. ✓
- `_run_loop` byte-stable; `spawn.py`/`chat_runner.py` unchanged; focused gate 236; py_compile → Steps 6-7. ✓
- No-hot-path-diff gate is specific (purely additive + hunk-location + the two sibling files unchanged) → Step 7. ✓

**2. Placeholder scan:** No TBD/TODO; every code step shows complete code. The `tool_schemas=[]` fallback in Step 2 is a conditional with the exact code, not a placeholder. ✓

**3. Type consistency:** `run_live_producer_node(self, graph, node_id)` referenced identically in Step 4 and every test call. `_producer_graph` / `_usable_raw` / `PROBE_TOOL_NAME` / `_DECLARED_PARAMS` defined once and reused. Import names (`run_live_producer_node_with_executor`, `LiveProducerResult`, `PlanGraph`) match LM4A/LM4C exactly. ✓

---

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.
2. **Inline Execution** — batch execution with checkpoints.
