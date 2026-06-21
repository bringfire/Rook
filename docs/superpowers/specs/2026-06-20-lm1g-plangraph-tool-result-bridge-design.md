# LM1G: PlanGraph Tool-Result Bridge Design

## Status

Design draft for senior review. This document defines the LM1G slice only. It
must not be treated as approval for a graph walker/scheduler, runnable-node
selection in production, verifier-output production, retry/escalation policy,
ChatRunner integration, LM2 capability registry work, or live Rhino/GH
execution.

## Context

The local/internal model roadmap now has these completed LM1 foundations:

- LM1A: visible tools are structurally dispatchable.
- LM1B: `ToolResultView` / `normalize_tool_result` normalize coarse tool-result
  truth.
- LM1C: C# script preflight stops obvious invalid script payloads before GH
  mutation.
- LM1D: GH script create/update paths emit post-mutation `script_receipt`
  evidence, including `artifact_status`, `verification`, `mutation`, and
  `repair_anchor`.
- LM1E: `PlanGraph` stores DAG-local state, evidence, retry state, and memory,
  and applies prepared `NodeOutcome` objects deterministically
  (`initialize_graph`, `runnable_nodes`, `apply_outcome`, `graph_status`).
- LM1F: `node_outcome_from_tool_result(result)` adapts a raw tool result plus
  `script_receipt` into a `NodeOutcome`.

The current evidence path is:

```text
tool result -> ToolResultView + script_receipt -> NodeOutcome -> PlanGraph reducer
```

Every link in that chain exists, but the **seam between LM1F and LM1E has never
been exercised as a composed unit**:

- LM1E's repair-loop test builds every `NodeOutcome` by hand; the outcomes are
  synthetic and never come from the adapter.
- LM1F's tests run the adapter in isolation; there is no graph and no walk.

So nothing yet proves that an adapter-produced `NodeOutcome`, applied to a
`PlanGraph`, drives a full create -> repair -> success loop while preserving the
`component_guid` and `repair_anchor` that a repair depends on.

LM1G closes exactly that seam with one tiny generic production helper and a
non-live proof test. It is the last narrow bridge before LM2 widens into a
capability registry / surface compiler.

## Goals

- Add a pure, non-live module
  `mcp_server/src/rook/learning/plan_graph_bridge.py`.
- Expose exactly one public V0 helper that composes the LM1F adapter with the
  LM1E reducer:

```python
def apply_tool_result(graph: PlanGraph, node_id: str, raw_result: Any) -> PlanGraph:
    outcome = node_outcome_from_tool_result(raw_result)
    return apply_outcome(graph, node_id, outcome)
```

- Prove, in tests only, that a canned GH script repair loop runs end to end
  through `apply_tool_result(...)`:
  - a create result with `script_receipt.artifact_status == "created_with_errors"`
    maps to `needs_repair`;
  - `GraphMemory` retains `component_guid` and `repair_anchor` from the receipt;
  - the repair node becomes runnable through an `on_repair` edge;
  - an update result with `artifact_status == "usable"` maps to `succeeded`;
  - the graph reaches `complete`.
- Keep the helper a pure composition with no added policy.
- Add import-boundary probes in the LM1F style so the module stays import-light.

## Non-Goals

- No graph walker, scheduler, or driver loop.
- No runnable-node selection in production code.
- No consumption of a sequence of results in production code.
- No retry policy, escalation policy, or readiness/guard logic in the bridge.
- No verifier nodes and no verifier-output production. Verifier-specific
  adapters that produce `NodeOutcome` directly remain future work (named in the
  LM1F design).
- No receipt inspection inside the bridge; that stays in the LM1F adapter.
- No ChatRunner, ToolDispatcher, ToolRegistry, server, or MCP wire changes.
- No `gh_set_script` changes.
- No capability registry, provider profile, model profile, or LM2 work.
- No live Rhino/GH dependency.
- No GH-specific node names or workflow-step names in production code. The GH
  script repair graph appears only as a test fixture.

## Module Boundary

Create:

`mcp_server/src/rook/learning/plan_graph_bridge.py`

Tests:

`mcp_server/tests/test_plan_graph_bridge.py`

Allowed imports in `plan_graph_bridge.py`:

- `typing.Any`
- `rook.learning.plan_graph.PlanGraph`
- `rook.learning.plan_graph.apply_outcome`
- `rook.learning.plan_graph_outcomes.node_outcome_from_tool_result`

Import direction:

```text
plan_graph_bridge imports plan_graph and plan_graph_outcomes
plan_graph_outcomes imports tool_result_view and plan_graph
plan_graph imports neither bridge nor plan_graph_outcomes
```

The module must not import:

- `rook.server`
- `rook.agent.tool_dispatcher`
- `rook.agent.chat.chat_runner`
- `rook.agent.chat.tool_contracts`
- ToolRegistry, capability, or registry modules
- Rhino/GH live tools
- KG write paths
- DSPy or LiteLLM

`plan_graph_bridge` is imported by its full module path
(`rook.learning.plan_graph_bridge`). It is **not** added to
`rook.learning.__all__` exports. `rook.learning.__init__` is lazy; keeping the
bridge out of the broad package exports preserves the import-light boundary and
follows the same precedent as `plan_graph_outcomes`.

## Public API

Use exactly:

```python
def apply_tool_result(graph: PlanGraph, node_id: str, raw_result: Any) -> PlanGraph:
    ...
```

Behavior:

- Calls `node_outcome_from_tool_result(raw_result)` (LM1F) to produce a
  `NodeOutcome`.
- Calls `apply_outcome(graph, node_id, outcome)` (LM1E) and returns its result.
- Returns a new graph; does not mutate the input graph (inherited from
  `apply_outcome`, which deep-copies).
- Raises `ValueError` for an unknown `node_id` (inherited from `apply_outcome`).
  The bridge adds no guard of its own.
- Does not check whether `node_id` is currently `ready`. A readiness or
  dispatch-eligibility check would be scheduling policy and is out of scope; the
  caller (the test) owns node selection via `runnable_nodes(...)`.
- Does not inspect `script_receipt`, `repair_anchor`, or any receipt fields
  directly; all receipt interpretation stays in the LM1F adapter.

No other public symbols are added in V0. Private helpers are not expected; the
function is a direct composition.

## Proof Graph (Test-Only)

The repair loop lives entirely in `test_plan_graph_bridge.py`. Production code
contains no graph builder and no GH-specific names.

Graph shape (two nodes, one edge):

```text
create_script --on_repair--> repair_same_component   (repair_same_component is terminal)
```

- `create_script`: `PlanGraphNode(id="create_script", intent=..., ...)`.
- `repair_same_component`: `PlanGraphNode(..., is_terminal=True)`.
- Edge: `PlanGraphEdge(source="create_script", target="repair_same_component", kind="on_repair")`.

There is no `done` node. `repair_same_component` is the terminal node, so the
graph is `complete` once it succeeds. This avoids manufacturing a synthetic
terminal result while still proving completion. The dormant happy-path edge
(`create --on_success--> done`) is intentionally omitted; it would dilute the
proof, whose only job is to pin the repair path.

### Canned results

Two canned dictionaries shaped like the internal/server result envelope LM1F
consumes (`result["data"]["script_receipt"]`):

- Create result: top-level `success == False`, with
  `script_receipt.artifact_status == "created_with_errors"`,
  `script_receipt.mutation.component_guid == <guid>`, and
  `script_receipt.repair_anchor == {"component_guid": <guid>, ...}`.
- Update result: top-level `success == True`, with
  `script_receipt.artifact_status == "usable"` for the same component.

These mirror the real LM1D create/update receipts captured in earlier live
smoke runs. No Rhino/GH call produces them in the test.

### Walk

1. `graph = initialize_graph(build_repair_fixture())`.
   - Assert `runnable_nodes(graph)` ids == `{"create_script"}`.
2. `graph = apply_tool_result(graph, "create_script", create_result)`.
   - Assert `graph.nodes["create_script"].status == "needs_repair"`.
   - Assert `graph.memory.facts["component_guid"] == <guid>`.
   - Assert `graph.memory.facts["repair_anchor"]` equals the receipt's repair
     anchor.
   - Assert `runnable_nodes(graph)` ids == `{"repair_same_component"}`.
   - Assert `graph_status(graph) == "running"`.
3. `graph = apply_tool_result(graph, "repair_same_component", update_result)`.
   - Assert `graph.nodes["repair_same_component"].status == "succeeded"`.
   - Assert `graph_status(graph) == "complete"`.

The repair node's evidence should also carry the usable receipt, confirming
adapter-produced evidence (not hand-built) flowed through the bridge.

## Single-Step Seam Tests

Beyond the loop, test the helper itself:

- Composition equivalence: for a representative `raw_result`,
  `apply_tool_result(graph, node_id, raw_result)` produces a graph equal to
  `apply_outcome(graph, node_id, node_outcome_from_tool_result(raw_result))`.
- Input immutability: the input graph is unchanged after the call.
- Deep-copy protection: mutating `raw_result` (its nested
  `script_receipt`/`repair_anchor`) after the call does not change the stored
  node evidence or `GraphMemory` facts.
- Unknown node: `apply_tool_result(graph, "missing", {...})` raises `ValueError`.
- Non-dict result: `apply_tool_result(graph, node_id, "plain string")` applies a
  `blocked` outcome (the LM1F contract for non-dict results) and does not raise.

## Import-Boundary Probes

Mirror the LM1F boundary tests:

- AST direct-import check on `plan_graph_bridge.py`:
  - imports `rook.learning.plan_graph`;
  - imports `rook.learning.plan_graph_outcomes`;
  - does not import `rook.agent.chat.tool_contracts`,
    `rook.agent.tool_dispatcher`, `rook.agent.chat.chat_runner`, or
    `rook.server`.
- Subprocess import probe: importing `rook.learning.plan_graph_bridge` does not
  load `rook.agent.tool_dispatcher`, `dspy`, or `litellm` into `sys.modules`.

## Test Strategy

Add `mcp_server/tests/test_plan_graph_bridge.py` with:

- the two-node repair-loop walk above;
- the single-step seam tests above;
- the import-boundary probes above.

All tests are deterministic and non-live with canned dictionaries. No Rhino, no
GH, no ToolDispatcher, no ChatRunner, no server, no network.

Suggested verification:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest -p no:cacheprovider mcp_server/tests/test_plan_graph_bridge.py mcp_server/tests/test_plan_graph_outcomes.py mcp_server/tests/test_plan_graph.py -q
mcp_server\.venv\Scripts\python.exe -m py_compile mcp_server/src/rook/learning/plan_graph_bridge.py
rg -n "tool_dispatcher|chat_runner|tool_contracts|rook.server|dspy|litellm" mcp_server/src/rook/learning/plan_graph_bridge.py
git diff --check
```

## Acceptance Criteria

- `apply_tool_result(graph, node_id, raw_result) -> PlanGraph` exists in
  `rook.learning.plan_graph_bridge` and is a pure composition of
  `node_outcome_from_tool_result(...)` and `apply_outcome(...)`.
- The bridge adds no walker, node selection, readiness check, retry policy, or
  escalation policy.
- The bridge does not inspect `script_receipt` or `repair_anchor` directly.
- The module is import-light: no server, dispatcher, ChatRunner, ToolRegistry,
  capability registry, Rhino, GH, DSPy, or LiteLLM imports, proven by AST and
  subprocess probes.
- The module is imported by full module path and is not added to
  `rook.learning.__all__`.
- A non-live test drives the two-node repair loop end to end through
  `apply_tool_result(...)`:
  - create result -> `needs_repair`;
  - `component_guid` and `repair_anchor` retained in `GraphMemory`;
  - repair node ready via `on_repair`;
  - update result -> `succeeded`;
  - `graph_status == "complete"`.
- The repair node carries adapter-produced evidence, not hand-built
  `NodeOutcome` objects.
- No ChatRunner, dispatcher, server, public MCP, PlanGraph reducer, LM1F adapter,
  or capability registry behavior changes.

## Future Work

Future slices may:

- add a verifier-output producer so verifier nodes have a real `NodeOutcome`
  source, enabling the north-star create -> verify -> repair -> verify -> report
  shape;
- add a graph walker / scheduler that selects runnable nodes and consumes
  injected or live results;
- feed `apply_tool_result(...)` from a ChatRunner or local scaffold loop;
- add capability registry references in LM2;
- support external presentation-layer result shapes once inventoried.

Those are intentionally out of scope for LM1G.
