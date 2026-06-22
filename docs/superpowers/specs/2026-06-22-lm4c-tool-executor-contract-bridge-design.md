# LM4C — `ToolExecutor` Contract Bridge for One Live Producer Node

**Date:** 2026-06-22
**Campaign:** Local/Internal-Models (LM) reliability — Stage 5 (live PlanGraph execution)
**Slice:** LM4C — production-seam contract bridge
**Status:** Design approved (brainstorming), ready for implementation plan

---

## Goal

Let one PlanGraph `artifact_producer` node be driven from the **agent's actual
executor seam** — the looser `ToolExecutor` contract the production code already
exposes — not just the strict-async `ToolDispatcher.dispatch` LM4B proved.

This is the smallest real step toward production call-site wiring: a new thin
agent-layer function that accepts the production `ToolExecutor` callable shape,
normalizes its sync-or-async result into an awaitable dict, and delegates to the
LM4B kernel. **Call sites stay untouched this slice.**

## Position in the campaign

- Stages 1–4 done. Stage 5 started.
- **LM4A** — `apply_live_producer_node(graph, node_id, dispatch)`: drives one
  producer node through an injected **strict-async** dispatch callable
  (`Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]`); admissibility +
  resolution + param-copy precede dispatch; `dispatch_failed` only for the
  callable raising.
- **LM4A-FU1** — runnable_nodes boundary audit; live preflight reads
  `node.status == "ready"` directly.
- **LM4B** — `run_live_producer_node(...)` in `agent/plan_graph_live_dispatch.py`:
  the named live-dispatch **composition root**; proved a real
  `ToolDispatcher.dispatch` callable drives a node through a synthetic registered
  local tool, no Rhino/HTTP.
- **LM4C** (this slice) — bridges the production executor contract.

## The gap LM4C closes

LM4B passed a **strict-async** `dispatcher.dispatch` and hand-built its own
`ToolDispatcher` + synthetic probe. But the seam the agent code actually exposes
is looser:

- `ToolExecutor = Callable[[str, Dict[str, Any]], Any]`
  (`mcp_server/src/rook/agent/base_agent.py:66`) — returns a `dict` **or** an
  awaitable.
- `BaseAgent._tool_executor`, `ChatRunner._tool_executor`, and `spawn.run_task`'s
  `tool_executor` all hold exactly this shape, defaulting to `dispatcher.dispatch`
  or an injected executor. `BaseAgent` normalizes the may-be-sync return itself:
  `result = self._tool_executor(name, params); if inspect.isawaitable(result):
  result = await result` (`base_agent.py:928-930`).

LM4A's kernel `await dispatch(...)` requires a **strictly awaitable** return. So a
production `ToolExecutor` that returns a bare `dict` would break `await`. LM4C's
single responsibility is to **bridge that contract gap** — normalize awaitability
— so the agent's real executor callable can drive a node. That, not an LM4B
rename, is the substance.

## Placement

The new function lives in the **existing** composition root
`mcp_server/src/rook/agent/plan_graph_live_dispatch.py`, beside
`run_live_producer_node`. No sibling module: LM4C is the same responsibility
("drive one live producer node from an injected callable") with a looser input
contract, not a new architectural layer. A sibling would add an almost-empty file
and a second near-identical import-boundary test without adding separation.

## The function

```python
import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from rook.agent.plan_graph_live import apply_live_producer_node  # existing

if TYPE_CHECKING:
    from rook.agent.plan_graph_live import LiveProducerResult
    from rook.learning.plan_graph import PlanGraph


async def run_live_producer_node_with_executor(
    graph: "PlanGraph",
    node_id: str,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> "LiveProducerResult":
    """Drive one live producer node from a production ``ToolExecutor`` callable.

    ``tool_executor`` follows the agent seam's looser contract
    (``Callable[[str, dict], Any]`` -- sync OR async return). The inner ``dispatch``
    normalizes awaitability only, then delegates to the LM4B/LM4A kernel. Result
    shape and error taxonomy stay owned by LM4A.
    """
    async def dispatch(name: str, params: dict[str, Any]) -> dict[str, Any]:
        result = tool_executor(name, params)
        if inspect.isawaitable(result):
            result = await result
        return result

    return await run_live_producer_node(graph, node_id, dispatch)
```

(`run_live_producer_node` is already imported/defined in this module; the snippet
shows the imports the new function adds — `inspect` plus the existing ones.)

## Contract & semantics

- **Normalize awaitability only.** `inspect.isawaitable` is the chosen mechanism,
  but the *contract* is "accept sync-or-async, yield an awaited value." The tests
  pin that behavior, not the specific stdlib helper.
- **No result validation here.** A malformed/non-dict `result` flows straight
  into LM4A's existing raw-result handling. This wrapper never inspects result
  shape. (Test 5 pins this: a non-dict result becomes an *applied blocked*
  outcome via the pure runner, not `dispatch_failed`.)
- **No try/except here; one error taxonomy.** A sync executor that raises does so
  during `await dispatch(...)`; an async executor that raises does so on
  `await result`. Either way LM4A's `try: raw = await dispatch(...) except
  Exception: -> dispatch_failed` catches it. LM4C introduces no second error path.
- **Structural typing, no `base_agent` import.** The executor parameter is typed
  with a local `Callable[[str, dict[str, Any]], Any]`. It must **not** import the
  `ToolExecutor` alias from `base_agent`: the import-boundary AST test walks all
  `ImportFrom` nodes (including `TYPE_CHECKING`), so even a type-only import would
  add `rook.agent.base_agent` to the imported set, break the allowlist, and couple
  the seam.
- **No `ToolDispatcher`.** The seam accepts the executor callable; it never
  constructs, imports, or names a dispatcher (the existing source-substring ban
  on `ToolDispatcher`/`tool_dispatcher` still holds).

## Boundary test

`test_live_dispatch_module_import_boundary` in
`mcp_server/tests/test_plan_graph_live_dispatch.py` governs the whole module
source, so it already covers the new function. It stays green unchanged:

- `inspect` is added to the module's imports but is not rook-scoped, so the
  allowlist check (which only constrains `module.startswith("rook.")`) ignores it.
- Allowlist stays `{rook.agent.plan_graph_live, rook.learning.plan_graph}`.
- No new forbidden substrings, no `_producer_*` access.

No positive "must import `inspect`" assertion is added — the behavior (sync-or-async
normalization) is what matters, and pinning the exact stdlib mechanism would fail a
future `collections.abc`-based implementation for the wrong reason.

## Tests (extend `mcp_server/tests/test_plan_graph_live_dispatch.py`)

Reuse LM4B's fixtures (`_usable_raw`, `_error_raw`, `_producer_graph`,
`PROBE_TOOL_NAME`, `EXECUTION_PARAMS_KEY`/`OUTCOME_PROJECTION_ROLE_KEY`). All five
tests drive through `run_live_producer_node_with_executor`:

1. **Sync executor returns a dict — non-vacuous live-seam proof.** A plain
   `def executor(name, params) -> dict` returning `_usable_raw()`. Assert the
   result went **through LM4A's live seam**, not merely that the wrapper awaited:
   `applied is True`, `reason is None`, `outcome_status == "succeeded"`,
   `tool_name == PROBE_TOOL_NAME`, node `status == "succeeded"`, and producer
   **evidence** present on the node. Also assert the executor received the declared
   params.

2. **Async executor returns a dict.** An `async def executor(...) -> dict`
   returning `_usable_raw()`. Same successful live-seam outcome (`applied`,
   `outcome_status == "succeeded"`, `tool_name`).

3. **Sync executor raises before returning.** A `def executor(...)` that raises.
   Assert `applied is False`, `reason == "dispatch_failed"`, and the input graph is
   returned unchanged (`result.graph is graph`).

4. **Async executor returns an awaitable that raises when awaited.** An
   `async def executor(...)` that raises. Same `dispatch_failed` mapping and input
   graph preserved.

5. **Sync executor returns a non-dict — pins "no result validation."** A
   `def executor(...)` returning a non-dict sentinel (e.g. `"not a dict"`). The
   wrapper passes it through unchanged (a string isn't awaitable), and LM4A's pure
   raw-result handling owns it. Assert it is **applied through the pure runner, not
   converted to `dispatch_failed`**: `applied is True`, `reason is None`,
   `outcome_status == "blocked"`, node `status == "blocked"`. This mirrors the
   LM3I-established `apply_producer_result` malformed-raw behavior (no receipt → no
   artifact evidence → producer projection yields `blocked`) and proves the wrapper
   does not own result shape.

Tests use plain callables (no `ToolDispatcher`); driven with `asyncio.run`, no
Rhino/HTTP.

## Out of scope (explicit)

- **No edits to `base_agent.py`, `spawn.py`, or `chat_runner.py`** — they stay
  byte-stable. Call-site integration is a later slice.
- No scheduler/sequencer. One node, one step.
- No port/targeting policy.
- No template `execution_params` mutation.
- No Rhino, no HTTP, no real tool execution.
- No change to `plan_graph_live.py` (stays dispatcher-free) or the pure
  `learning/plan_graph_*` layer (stays import-light).

## Constraints (Global)

- `plan_graph_live.py`: unchanged this slice.
- `plan_graph_live_dispatch.py` imports: stays within the allowlist
  `{rook.agent.plan_graph_live, rook.learning.plan_graph}` plus stdlib; no
  `base_agent`, no `ToolDispatcher`, no `tool_dispatcher`/`rook.server`/
  `rook.agent.chat`/`ChatRunner`.
- Deterministic; no model calls; no live tools; no HTTP; no Rhino.
- Test runner (from `mcp_server/`):
  `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- LM4B + LM4C dispatch-seam suite stays green; LM4A + LM4B + LM4C focused suite
  stays green.
