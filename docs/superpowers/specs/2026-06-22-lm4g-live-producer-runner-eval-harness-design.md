# LM4G — One-node Live Producer Runner / Eval Harness

**Date:** 2026-06-22
**Campaign:** Local/Internal-Models (LM) reliability — Stage 5 (live PlanGraph execution)
**Slice:** LM4G — durable execution-record / eval layer around the one-node live path
**Status:** Design approved (brainstorming), ready for implementation plan

---

## Goal

A durable, explainable **execution-record layer** around the proven one-node live
path: drive exactly one declared producer node through
`RookAgent.run_live_producer_node`, record what happened **from the returned
graph**, and evaluate it against a declarative expectation. This is the measuring
stick laid down before any multi-node chain work — so a later chain slice has a
stable observability surface to report into.

**Explicitly out of scope:** graph/node selection, successor advancement,
multi-node chains, scheduling, chat-loop integration. One node, once.

## Position in the campaign

LM4A–D made the executor stack reachable from a real agent; LM4E proved the live
one-node path end-to-end (both two-successes seams); LM4F fixed the MCP-unwrapped
receipt capture. LM4G adds no new execution capability — it is a **downstream
reader** that turns one `LiveProducerResult` (+ its returned graph) into a
structured, serial­izable record with a self-explaining pass/fail verdict. The
graph node's evidence is the canonical execution record (north star); LM4G never
opens a raw side channel.

## Architecture

New module `mcp_server/src/rook/agent/plan_graph_live_runner.py` — **pure in
behavior** (no I/O, no dispatcher, no Rhino, deterministic), yet agent-layer
because it consumes the agent-layer `LiveProducerResult`.

- **Pure core:** `build_live_producer_record(result, expectation=None) -> LiveProducerRecord`.
- **Thin live wrapper:** `async run_and_record_live_producer_node(runner, graph, node_id, expectation=None) -> LiveProducerRecord`
  = `result = await runner.run_live_producer_node(graph, node_id)` then
  `return build_live_producer_record(result, expectation)`.
- **Structural boundary:** `runner` is typed as a `Protocol`, NOT a `RookAgent`:

  ```python
  class SupportsLiveProducerNode(Protocol):
      async def run_live_producer_node(
          self, graph: "PlanGraph", node_id: str
      ) -> "LiveProducerResult": ...
  ```

  `RookAgent` satisfies it structurally. This keeps the module decoupled from
  `base_agent` and trivially testable with a fake runner — same discipline as the
  LM4C/LM4D structural boundaries.

### Imports / boundary invariants

- Runtime imports limited to: `from rook.agent.plan_graph_live import
  LiveProducerResult, EXECUTION_PARAMS_KEY` + stdlib (`dataclasses`, `copy`,
  `typing`). Learning-layer types (`PlanGraph`) are `TYPE_CHECKING`-only / quoted.
- **No** `base_agent`, **no** dispatcher / `tool_dispatcher`, **no** `rook.server`,
  **no** `rook.agent.chat`, **no** Rhino / HTTP. The module never executes a tool.
- No edit to any merged LM4 module (`plan_graph_live.py`,
  `plan_graph_live_dispatch.py`, `base_agent.py`) or the pure `learning/` layer.

## Dataclasses (all frozen)

```python
@dataclass(frozen=True)
class LiveProducerExpectation:
    applied: bool | None = None
    outcome_status: str | None = None
    node_status: str | None = None
    verified: bool | None = None
    artifact_status: str | None = None
    reason: str | None = None

@dataclass(frozen=True)
class Mismatch:
    field: str
    expected: object      # plain, repr-safe
    observed: object      # plain, repr-safe

@dataclass(frozen=True)
class LiveProducerRecord:
    # captured from result + result.graph
    node_id: str
    tool_name: str | None
    applied: bool
    reason: str | None
    outcome_status: str | None
    node_status: str | None
    verified: bool | None
    artifact_status: str | None
    repair_anchor_guid: str | None
    declared_params: dict | None
    # evaluation
    expectation: LiveProducerExpectation | None
    evaluated: bool
    passed: bool | None
    mismatches: tuple[Mismatch, ...]
```

## Capture semantics (read from `result.graph`)

Tightening: **read the returned graph**, not the input graph (applied paths return
a fresh reducer copy). Look the node up defensively:

```python
node = result.graph.nodes.get(node_id)
```

- **`unknown_node` (node absent):** `node_status=None`, `verified=None`,
  `artifact_status=None`, `repair_anchor_guid=None`, `declared_params=None`.
- **node present (applied OR node-present not-applied):** `node_status = node.status`
  read straight from the returned graph node (graph-native — the node's status is
  the durable DAG state). Evidence fields come from `node.evidence` when present,
  else `None`:
  - `verified = node.evidence.verified`
  - `artifact_status = node.evidence.receipt["artifact_status"]` (guarded: receipt
    may be `None` or lack the key → `None`)
  - `repair_anchor_guid = node.evidence.repair_anchor["component_guid"]` (guarded)
- `tool_name`, `applied`, `reason`, `outcome_status` come straight off the
  `LiveProducerResult`.

The record summarizes the **captured evidence**, not a byte-for-byte transport
payload — intentional for LM4G. Evidence is the single-source capture (LM3I/LM1F),
so no raw side channel is needed.

### `declared_params` is best-effort and non-throwing (LM4A-alarm guard)

The metadata params are **declared** params (LM4A deep-copies before dispatch, so
the harness confirms what was *declared*, not the exact dispatched object). Capture
must never crash — in particular the `params_copy_failed` not-applied path returns
the input graph holding exactly the **non-deepcopyable** `execution_params` that
made LM4A bail gracefully. Blindly deep-copying them here would crash *after* the
kernel correctly didn't.

```python
def _safe_declared_params(node) -> dict | None:
    """Best-effort declared-params capture. Returns a deep copy when possible,
    else None. NEVER raises -- a non-deepcopyable execution_params (the exact
    shape that makes LM4A return params_copy_failed) must not crash the record."""
    if node is None:
        return None
    meta = getattr(node, "metadata", None)
    if not isinstance(meta, dict) or EXECUTION_PARAMS_KEY not in meta:
        return None
    try:
        return deepcopy(dict(meta[EXECUTION_PARAMS_KEY]))
    except Exception:
        return None
```

The deep copy also isolates the record from the graph (mutating the record's
`declared_params` cannot touch the node's metadata).

## Evaluation semantics

- `expectation is None` → `evaluated=False`, `passed=None`, `mismatches=()`.
- expectation provided → `evaluated=True`; for each expectation field that is
  **not `None`**, compare to the observed record field and append
  `Mismatch(field, expected, observed)` on inequality; `passed = (not mismatches)`.
- All-`None` expectation → no comparisons → `mismatches=()`, `passed=True`
  ("intentionally evaluated nothing" — distinct from no expectation supplied).
- The compared observed values are the record's own captured fields (`applied`,
  `outcome_status`, `node_status`, `verified`, `artifact_status`, `reason`).
- `expectation` is echoed into the record for durability.

## Tests

### Pure unit — `mcp_server/tests/test_plan_graph_live_runner.py`

In the focused PlanGraph gate (filename matches `test_plan_graph*.py`), **no Rhino**.
Fabricate `LiveProducerResult`s over real `PlanGraph`/`PlanGraphNode` objects:

1. **Clean applied** (`usable`): record fields — `applied=True`,
   `outcome_status=="succeeded"`, `node_status=="succeeded"`, `verified is True`,
   `artifact_status=="usable"`, `repair_anchor_guid` set, `declared_params` echoes
   the node metadata.
2. **Broken applied** (`created_with_errors`): `verified is False`,
   `artifact_status=="created_with_errors"`, `outcome_status=="succeeded"`.
3. **Not-applied `unknown_node`** (node absent): record still builds —
   `node_status is None`, all evidence fields `None`, `declared_params is None`,
   `reason=="unknown_node"`.
4. **Not-applied, node present, evidence `None`** (e.g. `node_not_runnable`):
   `node_status` read from the graph node; `verified/artifact_status/
   repair_anchor_guid is None`; `reason` preserved.
5. **Not-applied `params_copy_failed` with non-deepcopyable `execution_params`:**
   record builds (no crash), `reason=="params_copy_failed"`,
   `declared_params is None`. (Pins the LM4A-alarm guard.)
6. **Eval — no expectation:** `evaluated is False`, `passed is None`,
   `mismatches == ()`.
7. **Eval — all-`None` expectation:** `evaluated is True`, `passed is True`,
   `mismatches == ()`.
8. **Eval — single mismatch:** one wrong expected field → `passed is False`,
   `mismatches` has exactly `Mismatch(field, expected, observed)` with the right
   values.
9. **Eval — multiple mismatches:** two wrong fields → both present.
10. **`declared_params` deep-copy isolation:** mutating the record's
    `declared_params` does not change the node's metadata.

### One live test — `mcp_server/tests/test_live_producer_runner_live.py`

Named **outside** the `test_plan_graph*` glob so it stays out of the focused gate
(keeps that gate Rhino-free), mirroring LM4E. `requires_rhino` + `asyncio`, a
**local** producer-graph fixture (no imports from LM4E's test module),
`fresh_document` for graceful skip. Clean-path only — LM4E already carries the
broken/two-successes live seam:

- Call `run_and_record_live_producer_node(agent, graph, "create", expectation)`
  with a real `RookAgent(tool_executor=_mcp_tool_executor)` and a clean C# body,
  `expectation = LiveProducerExpectation(outcome_status="succeeded",
  node_status="succeeded", verified=True, artifact_status="usable")`.
- Assert the **record**, not the implementation: `evaluated is True`,
  `passed is True`, `mismatches == ()`, and observed `artifact_status=="usable"`,
  `node_status=="succeeded"`, `verified is True`.

The exhaustive mismatch / not-applied / eval matrix lives in the pure unit tests;
the live test only proves the wrapper records and evaluates a real run (not
ornamental).

## Out of scope / constraints (Global)

- One node only — no selection, no successor advancement, no scheduler, no chat
  loop.
- No kernel change; pure-consumer of `LiveProducerResult`. No edit to
  `plan_graph_live.py` / `plan_graph_live_dispatch.py` / `base_agent.py` / pure
  `learning/`.
- Record summarizes captured evidence, NOT raw transport payload (intentional). If
  raw-payload debugging is ever needed, it is a separate diagnostic slice.
- Structural `Protocol`, never a `RookAgent` import.
- `declared_params` capture is best-effort / non-throwing.
- Deterministic core; no model calls; no live tools / HTTP / Rhino in the pure
  module or its unit tests.
- Test runner (from `mcp_server/`): `.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Focused PlanGraph gate runs from the **repo root**.

## Verification gates

- Focused PlanGraph gate from repo root: **242 + the new pure tests passed** (the
  pure file matches the glob and adds to the count; the live file does not match,
  so the gate stays Rhino-free).
- Live test: `1 passed` with Rhino + GH up; skips cleanly otherwise.
- `py_compile` clean on the new module + both test files.
- Import-boundary check: the new module imports no `base_agent` / dispatcher /
  `rook.server` / `rook.agent.chat` / Rhino.
- Diff confined to the new module + two new test files + this spec/plan. No
  `knowledge/**`, no edits to merged LM4 modules.
