# LM4D — Opt-in `RookAgent.run_live_producer_node` Method

**Date:** 2026-06-22
**Campaign:** Local/Internal-Models (LM) reliability — Stage 5 (live PlanGraph execution)
**Slice:** LM4D — first wiring into live agent flow
**Status:** Design approved (brainstorming), ready for implementation plan

---

## Goal

Wire the LM4C contract bridge into a **real agent call site**: add one opt-in,
non-LLM method on `RookAgent` that drives a single PlanGraph `artifact_producer`
node against the agent's own `_tool_executor` — the production `ToolExecutor`
seam — without touching the LLM run loop.

This is the first edit to live agent flow. It is deliberately the narrowest such
edit: an **additive** method beside the existing explicit utility methods, no
change to `_run_loop`, no scheduler, no graph selection.

## Position in the campaign

- **LM4A** — `apply_live_producer_node(graph, node_id, dispatch)`: one producer
  node through an injected **strict-async** dispatch callable.
- **LM4A-FU1** — runnable_nodes boundary audit; live preflight reads
  `node.status == "ready"` directly.
- **LM4B** — `run_live_producer_node(...)` in `agent/plan_graph_live_dispatch.py`:
  proved a real `ToolDispatcher.dispatch` drives a node (no Rhino/HTTP).
- **LM4C** — `run_live_producer_node_with_executor(...)` in the same module:
  bridges the looser production `ToolExecutor` (`Callable[[str, dict], Any]`,
  sync-or-async) into the strict-async kernel.
- **LM4D** (this slice) — calls LM4C from the agent that owns the executor.

The executor-contract stack is closed; the only missing piece is "where do we
call this during a real agent run." LM4D answers it at the narrowest altitude.

## The precedent

`RookAgent.test_connection` (`mcp_server/src/rook/agent/base_agent.py`) is the
existing template: an opt-in, **non-LLM** method that calls
`self._tool_executor(name, params)`, normalizes awaitability
(`if inspect.isawaitable(result): result = await result`), and returns a
structured result — **outside** `_run_loop`. LM4D is the same shape, delegating
to LM4C instead of inlining a `rhino_ping`. The agent already exposes its
`_tool_executor` to explicit utility methods; LM4D adds one more.

## Architecture

One **additive** method on `RookAgent`, placed near the existing explicit utility
methods such as `test_connection`. The binding invariant is **outside
`_run_loop`, opt-in, non-LLM** — not a literal adjacency. The exact insertion
point is chosen at implementation time.

```python
async def run_live_producer_node(
    self, graph: "PlanGraph", node_id: str
) -> "LiveProducerResult":
    """Drive one live producer node against this agent's tool executor.

    Opt-in, one-node, non-LLM: delegates to the LM4C contract bridge using the
    agent's own ``_tool_executor``. Does not touch the LLM run loop; no scheduler,
    no graph selection.
    """
    return await run_live_producer_node_with_executor(
        graph, node_id, self._tool_executor
    )
```

Nothing fires unless the method is called. The LLM loop is unaffected: this is a
new method, not a change to `_run_loop`.

## Imports & types (empirically verified — no cycle)

No module in the dispatch-seam transitive chain
(`plan_graph_live_dispatch` -> `plan_graph_live` -> pure `learning/plan_graph_*`
-> `agent/chat/tool_result_view`) imports `base_agent`, so there is no back-edge
and no import cycle. `base_agent.py` already imports `TYPE_CHECKING` and has an
`if TYPE_CHECKING:` block.

- **Top-level runtime import:**
  `from rook.agent.plan_graph_live_dispatch import run_live_producer_node_with_executor`.
- **Type-only imports under the existing `TYPE_CHECKING` block**, quoted in the
  signature: `from rook.agent.plan_graph_live import LiveProducerResult`;
  `from rook.learning.plan_graph import PlanGraph`. `base_agent` is an agent-layer
  module, so importing the agent-layer seam is in-bounds; the learning-layer type
  stays a quoted `TYPE_CHECKING`-only reference (no broad learning import).
- **Documented contingency (not needed now):** if a future edit introduces an
  import cycle, fall back to a local import inside the method with a comment
  explaining why. None exists today, so the import is top-level.

## Tests (new file `mcp_server/tests/test_base_agent_live_producer.py`)

Construct a real `RookAgent(tool_executor=<injected>)` and prove the method
reaches `self._tool_executor` — the production seam, not a synthetic dispatcher.
A small producer-graph fixture mirrors the LM4B/LM4C fixtures: one node with
`execution_ref=PROBE`, role `artifact_producer`, `execution_params`, status
`ready`. Executors are plain injected callables; **no real `ToolDispatcher`, no
Rhino/HTTP** (LM4B already proved the real dispatcher; LM4D proves
`RookAgent -> _tool_executor -> LM4C`).

1. **Sync executor returns a dict.** `applied is True`, `reason is None`,
   `outcome_status == "succeeded"`, `tool_name == PROBE`, node status
   `"succeeded"`, the executor recorded the exact `(tool_name, declared_params)`,
   and `result.graph is not graph` (applied -> fresh reducer graph).

2. **Async executor returns a dict.** Same successful outcome
   (`applied`, `outcome_status == "succeeded"`, `tool_name`).

3. **Raising executor.** `applied is False`, `reason == "dispatch_failed"`,
   `outcome_status is None`, `result.graph is graph` (not-applied -> input graph
   preserved; proves no new error taxonomy and no exception leak through the
   `RookAgent` method).

**Constructor side-effect coverage (kept cheap).** Use an injected executor
**spy** that records every call. Assert the spy was **not** called during
`RookAgent(tool_executor=spy)` construction — it is only called when the method
runs. This proves construction does not auto-build a dispatcher or invoke the
executor. If a trivial monkeypatch around `ToolDispatcher` (asserting it is never
constructed) is easy in the test module, include it as an extra guard; otherwise
the spy assertion plus the review gate below suffices — do not overbuild it.

**Graph-identity distinction (pinned):** raise/not-applied returns the original
graph object (`is graph`); applied paths return a fresh reducer copy
(`is not graph`).

## Out of scope / byte-stable

- `_run_loop` is **byte-stable** — LM4D adds no code to it. `base_agent.py` is
  touched, but only with an **additive import + method** (so the file is not
  byte-stable; the *loop* is).
- `spawn.py` and `chat/chat_runner.py` are **unchanged**.
- No scheduler, no graph/node selection, no template `execution_params`
  mutation, no Rhino/HTTP by default.
- LM4A/LM4B/LM4C modules and the pure `learning/plan_graph_*` layer are
  unchanged. `plan_graph_live.py` stays dispatcher-free.

## Verification gates

- New test file green (3 functional tests + the constructor spy assertion).
- Full focused PlanGraph gate from the **repo root** still **236 passed**
  (LM4D's tests live in a separate agent test file, so this gate proves no
  PlanGraph regression).
- `py_compile` clean on `base_agent.py` and the new test file.
- **No-hot-path-diff review gate.** Confirm via `git diff` / grep that the slice's
  only production change is the additive import + method in `base_agent.py`, and
  specifically that:
  - `_run_loop` is unchanged,
  - `spawn.py` is unchanged,
  - `chat/chat_runner.py` is unchanged.

## Constraints (Global)

- `base_agent.py`: only an additive top-level import + one additive method;
  `_run_loop` byte-stable.
- `spawn.py`, `chat/chat_runner.py`: unchanged.
- `plan_graph_live.py`, `plan_graph_live_dispatch.py`, pure `learning/plan_graph_*`:
  unchanged.
- Deterministic; no model calls; no live tools; no HTTP; no Rhino.
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Focused PlanGraph gate runs from the **repo root** (purity probes use
  repo-root-relative paths).
