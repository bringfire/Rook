# LM4L — Memory-Backed Execution-Param Applier (one named node)

**Date:** 2026-06-23
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push — Stage 5 (live execution)
**Predecessors:** LM4I (PR #339, `5d21f27b`) full live repair chain · LM4J (PR #340, `487aa3ef`) declared-ref chain · LM4K (PR #341, `162b5a78`) `bind_params_from_memory` (first memory→params primitive)

---

## 1. Goal

Move one rung from *"the test manually calls `bind_params_from_memory` and assigns
`execution_params`"* to *"a bounded Rook scaffold seam stages memory-sourced params
onto one explicitly-named node."*

LM4L adds the **first real consumer** of LM4K's pure `bind_params_from_memory`: an
**agent-layer applier** that sources a node's producer params from the runtime
`graph.memory.facts` substrate and writes them into that node's
`metadata["execution_params"]`. It does **not** dispatch, does **not** select a node,
and does **not** advance the chain. The caller names the node, supplies the bindings,
and still drives `run_live_producer_node`.

This is **memory-backed param staging for one named node**, not workflow automation.

---

## 2. Non-Goals (guardrails)

- **No scheduler.** No automatic node selection, no successor advancement, no run loop.
- **No dispatch.** The applier's job ends at the `execution_params` write. Readiness,
  projection role, execution-ref resolution, and param dispatchability remain
  `run_live_producer_node`'s concern.
- **No model.** Rook owns memory, contracts, verifier gates, and params.
- **No new node-metadata "bindings" schema.** Bindings stay caller-supplied
  (`{param_key: path}`). No template-declared runtime-binding declaration format.
- **No `base_agent.py` edit.** The applier needs no agent instance state; it is a free
  function. The LLM run loop stays byte-stable.
- **LM4K stays pure and untouched.** `bind_params_from_memory` keeps returning params
  and never writing a node. LM4L does not undo that contract.

---

## 3. Architecture

One new agent-layer production module:

```
mcp_server/src/rook/agent/plan_graph_param_apply.py
```

It is the agent-layer consumer that bridges the pure learning helper to the
agent-owned `execution_params` slot:

- `EXECUTION_PARAMS_KEY` is **defined in the agent layer** (`plan_graph_live.py`).
  Writing it is an agent/live-dispatch concern, so the applier lives in agent land.
- Import direction is one-way: `agent → learning`. The applier imports
  `bind_params_from_memory` and `ParamBindingResult` from
  `rook.learning.plan_graph_param_binding`, and `EXECUTION_PARAMS_KEY` from
  `rook.agent.plan_graph_live` (single source — not redefined).
- The applier is a pure-of-I/O graph transform: no dispatcher, no server, no
  `base_agent`, no Rhino. It needs no `RookAgent` instance, so there is **no new
  `RookAgent` method** (unlike LM4D's `run_live_producer_node`).

---

## 4. Public Surface

```python
from typing import Literal

ApplyReason = Literal["unknown_node", "binding_failed", "graph_copy_failed"]

@dataclass(frozen=True)
class MemoryParamApplyResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    binding: ParamBindingResult | None   # LM4K result; None only when unknown_node
                                         # short-circuits before binding runs
    reason: ApplyReason | None           # None on success

def apply_memory_bound_params(
    graph: PlanGraph,
    node_id: str,
    base_params: Mapping,
    bindings: Mapping[str, tuple[str, ...]],
) -> MemoryParamApplyResult: ...
```

- `reason: ApplyReason | None` mirrors LM4A's `LiveProducerResult.reason` shape so the
  agent layer stays idiomatic.
- `binding` embeds the LM4K `ParamBindingResult` verbatim, preserving binding-finding
  detail (which path/key failed) without flattening. Findings reuse LM4K's
  `ParamBindingFinding` type exactly.
- `graph_copy_failed` (renamed from an earlier `metadata_copy_failed`): the
  implementation deep-copies the **whole graph** to stage metadata copy-on-write, so
  the honest failure name is graph-copy, not metadata-copy. The failure may originate
  from any uncopyable payload anywhere in the graph.

---

## 5. Data Flow (copy-on-write)

1. **Existence check.** If `node_id not in graph.nodes` → `unknown_node`,
   `binding=None`, return the **input graph unchanged**.
2. **Bind (pure).** `binding = bind_params_from_memory(base_params, graph, bindings)`,
   reading the **original** `graph.memory.facts`. If `binding.findings` is non-empty →
   `binding_failed`, embed `binding`, return the **input graph unchanged**.
3. **Copy.** `try: new_graph = deepcopy(graph)`. On failure → `graph_copy_failed`,
   embed the (successful) `binding`, return the **input graph unchanged**.
4. **Stage.** `new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = binding.params`.
   `binding.params` is already a fresh deep-copied dict (LM4K deep-copies), so no
   aliasing into the caller's graph or into `new_graph.memory`.
5. **Success.** `applied=True`, `graph=new_graph`, `reason=None`.

Binding reads the original graph (pure); the write lands on the copy. Order matters:
bind on the original, then copy, then stage — never the reverse.

---

## 6. Graph-Identity Contract (per outcome)

This is the load-bearing copy-on-write contract. Tests assert it explicitly.

| Outcome | `applied` | `reason` | `binding` | Graph identity |
|---|---|---|---|---|
| success | `True` | `None` | populated, `findings == ()` | `result.graph is not graph` (new copy; original node has no `execution_params`) |
| `unknown_node` | `False` | `"unknown_node"` | `None` | `result.graph is graph` (unchanged) |
| `binding_failed` | `False` | `"binding_failed"` | embedded, `findings` non-empty | `result.graph is graph` (unchanged) |
| `graph_copy_failed` | `False` | `"graph_copy_failed"` | embedded, `findings == ()` (binding succeeded) | `result.graph is graph` (unchanged) |

On **every** failure path the result carries the **same** graph object the caller
passed in (`result.graph is graph`) — no copy on failure. Only the success path
returns a distinct object.

---

## 7. Boundaries / Invariants

- LM4K's `bind_params_from_memory` is untouched and stays pure (returns params, no
  node write, no graph mutation, deep-copies).
- The applier checks **only** node existence, binding success, and copy success. It
  does **not** check node status (`ready`), projection role (`artifact_producer`),
  execution-ref validity, or param dispatchability — those belong to
  `run_live_producer_node`. Staging params before a node is `ready` is legitimate.
- AST import-boundary guard: the applier imports no dispatcher / server /
  `base_agent`; learning (`plan_graph_param_binding`) never imports the applier.
- Production change = **exactly** the one new module
  (`git diff --numstat main...HEAD -- mcp_server/src` lists only
  `agent/plan_graph_param_apply.py`); `base_agent.py` byte-stable.

---

## 8. Testing

Whole-branch diff = this spec + the plan + **1 module + 3 test files**.

### Task 1 — real TDD (the prod module)
`mcp_server/tests/test_plan_graph_param_apply.py` (in the focused
`test_plan_graph*.py` gate). Failing tests first, then the module:

- **success / copy-on-write:** memory populated; `apply_memory_bound_params(graph,
  "repair_same_component", base, {"guid": ("repair_anchor", "component_guid")})` →
  `applied`, `reason is None`, `binding.findings == ()`, `binding.params["guid"]==GUID`;
  `result.graph is not graph`; the **original** node has no `execution_params`, the
  **returned** node does.
- **unknown_node:** absent `node_id` → `applied False`, `binding None`,
  `reason "unknown_node"`, `result.graph is graph`.
- **binding_failed:** bindings reference a missing memory fact → `applied False`,
  `binding.findings` non-empty, `reason "binding_failed"`, `result.graph is graph`,
  node has no `execution_params`.
- **graph_copy_failed:** a `_NoDeepcopy` payload planted in an **unrelated** node's
  metadata (so bind still succeeds reading `memory.facts`) → `applied False`,
  `binding` successful, `reason "graph_copy_failed"`, `result.graph is graph`.
- **immutability:** success path leaves the original graph and `memory.facts`
  untouched; written params are not the same object as the memory value.
- **AST import-boundary guard:** module imports no `rook.server` / `rook.agent.base_agent`
  / dispatcher; `learning/plan_graph_param_binding` does not import the applier.

### Task 2 — pure chain guard
`mcp_server/tests/test_plan_graph_param_apply_chain.py` (focused gate, **separate
file** — LM4K's `test_plan_graph_param_binding_chain.py` stays untouched). The LM4K
chain, but the manual repair-node assignment is replaced by `apply_memory_bound_params`:
`select_template` 5-node `gh_csharp_create_verify_repair_verify` + `initialize_graph` →
`apply_producer_result(create_script, wrapped-failure raw)` populates `memory.facts` →
`apply_verifier_step(verify_create)` → `needs_repair` →
`result = apply_memory_bound_params(graph, "repair_same_component", base,
{"guid": ("repair_anchor", "component_guid")})`; assert `applied`,
`result.binding.params["guid"]==GUID`; `graph = result.graph` →
`apply_producer_result(repair_same_component, unwrapped-success raw)` → succeeded →
`apply_verifier_step(verify_repair)` → succeeded → `apply_outcome(done)` →
`graph_status == "complete"`.

**Honest scope:** `apply_producer_result` consumes a raw tool-result dict, not the
node's `execution_params`. This guard proves the applier sources from memory, stages
into `execution_params`, and the graph composes to complete — **not** that the staged
guid drives dispatch. Only the live proof does that.

### Task 3 — live proof (`requires_rhino`, outside the glob)
`mcp_server/tests/test_live_repair_chain_param_apply_live.py`. The LM4K declared-ref
live chain (no producer ref overrides), but the **applier** (not the test) writes the
repair node's `execution_params`:

- `_ensure_gh_document()` guard (`gh_document_new`, skip on error); `fresh_document`.
- Live create dispatch via `run_live_producer_node` → `created_with_errors`; capture
  `repair_guid_control = create_result.graph.nodes["create_script"].evidence.repair_anchor["component_guid"]`
  (CONTROL only). Create params stay a **direct** assignment (author-supplied: code,
  pins, name, x/y — not memory-sourced; only the repair guid comes from memory).
- `apply_verifier_step(verify_create)` → `needs_repair`.
- `result = apply_memory_bound_params(graph, "repair_same_component", {"code":
  "A = 42.0;", "mode": "body", "language": "csharp"}, {"guid": ("repair_anchor",
  "component_guid")})`; assert `result.applied`, `result.reason is None`,
  `result.binding.params["guid"] == repair_guid_control`; `graph = result.graph`;
  assert `graph.nodes["repair_same_component"].metadata[EXECUTION_PARAMS_KEY]["guid"]
  == repair_guid_control`. The test no longer writes the repair node's metadata
  directly — the applier did.
- Live repair dispatch via `run_live_producer_node` → `tool_name == "gh_update_script"`,
  `build_live_producer_record` passes, `repair_record.tool_status is None` (LM4I/J
  unwrapped-success finding) → `usable`.
- `apply_verifier_step(verify_repair)` → succeeded → `apply_outcome(done)` →
  `graph_status == "complete"`.

---

## 9. Process / Gates

- `codex/` branch off `main`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- PowerShell glob gotcha: PS does not expand `test_plan_graph*.py` — enumerate the
  focused gate via `Get-ChildItem`.
- Focused PlanGraph gate green (rises from 273).
- **Pause before Task 3 live acceptance** (needs Rhino + Grasshopper open, Rook loaded).
- Restore `knowledge/gh/operations_knowledge.json` after live runs (live runs dirty
  it); never commit it.
- Merge to `main` **always** needs explicit user approval — present options, do not
  self-merge.

---

## 10. North-Star Fit

Stage 5 (live execution) progressed: LM4A→G observability, LM4H handoff, LM4I full
repair chain, LM4J declared-ref dispatch, LM4K the first memory→params **primitive**.
LM4L is the first **consumer** of that primitive — a bounded seam a future runner will
call, proving memory-sourced params can be staged onto a named node by Rook (not the
test) and still drive a real live repair to `complete`. The next rung beyond LM4L (a
runner that *chooses* which node to stage + dispatch) remains explicitly out of scope.
