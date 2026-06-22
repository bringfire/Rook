# LM4A / Stage 5A — Live Producer-Node Dispatch Adapter

**Date:** 2026-06-22
**Campaign:** Local/Internal-Models (LM) reliability — Stage 5 (live PlanGraph execution)
**Slice:** LM4A — first live-execution adapter
**Status:** Design approved (brainstorming), ready for implementation plan

---

## Goal

Prove that **one** PlanGraph `artifact_producer` node can receive a **real tool
result through the existing dispatch path** and land evidence + role-aware
projection correctly — by introducing a single non-pure adapter that resolves a
node to a dispatch call, fires it, and delegates application to the pure runner.

This is the first slice that leaves the pure learning layer and touches the live
dispatch contract. It is deliberately narrow: **one node, one producer-result
path, no scheduler, no planner, no model calls, no Rhino in tests.**

## Position in the campaign

- Stage 1 (truthful surface), Stage 2 (receipt/result truth), Stage 3 (pure
  PlanGraph semantics through LM3H), Stage 4 (pure-dict live evidence bridge
  through LM3I) are **done**.
- LM3I established the pure-dict bridge: `node_evidence_from_tool_result(raw)`
  and `apply_producer_result(graph, node_id, raw_result)`. It consumed realistic
  raw dicts only — no HTTP, no dispatcher.
- **LM4A** is Stage 5 starting: live PlanGraph execution. The remaining LM4-ish
  work (per the reconciled north-star) is dispatcher wiring, runner/scheduler,
  knowledge/memory persistence, escalation policy, and an eval harness. This
  slice does **only** the narrowest dispatcher-wiring piece: a single live
  producer step.

## The two facts that make this slice small

1. **The live seam is already dict-shaped.** `ToolDispatcher.dispatch(name,
   params) -> dict` returns the exact `{"success", "data": {"script_receipt":
   …}}` envelope that `node_evidence_from_tool_result` consumes. So
   `apply_producer_result(graph, node_id, raw_result)` is purpose-built to
   receive a real `dispatch()` return verbatim — the pure side needs **no**
   change to accept live output.
2. **The only genuinely new logic is `(node, graph) → (tool_name, params)`.**
   Nothing today turns a node's `execution_ref` + declared params into a
   dispatch call. That resolution, plus pre-dispatch side-effect safety, is the
   entirety of LM4A.

`ToolDispatcher.dispatch` is **async** (verified:
`async def dispatch(self, name: str, params: dict) -> dict`), so the adapter is
`async` and the injected dispatch callable returns an `Awaitable`.

---

## Boundary & dependency direction

A new **non-pure live adapter** at
`mcp_server/src/rook/agent/plan_graph_live.py`. It is explicitly **not** a new
pure PlanGraph primitive. It **consumes** the pure seams and **does not alter or
grow** them.

> The live adapter owns pre-dispatch side-effect safety. It reuses public pure
> primitives (`runnable_nodes`, `projection_role_for_node`) but does **not**
> import private runner helpers (`_producer_*`) or require new pure APIs.
> Post-dispatch application stays delegated to the pure runner
> (`apply_producer_result`), which remains the authoritative
> producer-application path.

Dependency arrow stays **agent → learning(pure)**:

```
agent/plan_graph_live.py
  ├─ imports an injected dispatch callable (production: dispatcher.dispatch)
  └─ imports public pure PlanGraph seams (plan_graph, plan_graph_projection,
     plan_graph_runner)

learning/plan_graph_*   does NOT import agent / dispatcher / server / ChatRunner
```

**Zero `learning/` changes in this slice.** The pure suite (191 green on `main`)
cannot regress because no pure module is touched.

### Why adapter-local admissibility (not a shared pure helper)

LM4A is the first non-pure layer. It should consume the pure seams without
forcing them to grow API just because a live adapter needs a preflight. The five
admissibility reason-strings coincide with `ProducerStepReason`'s admissibility
subset, but they are **not** a shared contract — the adapter's taxonomy is its
own concern (a superset that also carries resolution and dispatch reasons). The
~6 duplicated lines buy a clean dependency boundary. The adapter's own tests pin
the same five admission outcomes; if role semantics change later, those tests
fail in both the adapter and the pure runner — enough pressure without exporting
a helper prematurely. If this preflight pattern repeats across multiple live
adapters, a public helper can be promoted **deliberately** then — not now.

---

## Public API

```python
EXECUTION_PARAMS_KEY = "execution_params"   # adapter-owned constant

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
    graph: PlanGraph                       # input graph on every not-applied path;
                                           # reducer's fresh graph when applied
    applied: bool
    node_id: str
    tool_name: str | None                  # resolved name once execution_ref resolves;
                                           # None if resolution failed earlier
    outcome_status: OutcomeStatus | None
    reason: LiveProducerReason | None

async def apply_live_producer_node(
    graph: PlanGraph,
    node_id: str,
    dispatch: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
) -> LiveProducerResult: ...
```

**Imports are public-only:**

- from `rook.learning.plan_graph`: `PlanGraph`, `OutcomeStatus`, `runnable_nodes`
- from `rook.learning.plan_graph_projection`: `OUTCOME_PROJECTION_ROLE_KEY`,
  `projection_role_for_node`
- from `rook.learning.plan_graph_runner`: `apply_producer_result`

No `_producer_*` private import. No `tool_dispatcher` / `server` / ChatRunner
import — the dispatcher arrives only as the injected `dispatch` callable.

### Dispatch-callable type and params normalization

The adapter accepts a node-metadata `Mapping` but dispatches a **detached
`dict`**, matching `ToolDispatcher.dispatch`'s `params: dict` signature:

```python
params_source = node.metadata[EXECUTION_PARAMS_KEY]
if not isinstance(params_source, Mapping):
    return _not_applied(graph, node_id, tool_name, "execution_params_invalid")
try:
    params = deepcopy(dict(params_source))
except Exception:
    return _not_applied(graph, node_id, tool_name, "params_copy_failed")
raw = await dispatch(tool_name, params)
```

This avoids a subtle production mismatch where tests pass a `Mapping` but the
real dispatcher expects a `dict`. The callable is typed
`Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]`.

---

## Control flow (strict order — every step before dispatch is side-effect-free)

1. **Admissibility** (adapter-local, public primitives only):
   `unknown_node` → `node_not_runnable` → `role_missing` → `role_invalid` →
   `role_not_producer`.
2. **Resolve tool name** from `node.execution_ref` (grammar below):
   missing/empty → `execution_ref_missing`; malformed → `execution_ref_invalid`.
3. **Resolve + copy params**: key absent → `execution_params_missing`; value not
   a `Mapping` → `execution_params_invalid`; `deepcopy(dict(...))` raises →
   `params_copy_failed`.
4. **Dispatch** (the *only* live side effect): `await dispatch(tool_name,
   params)`; if the callable **raises** → `dispatch_failed` (input graph
   preserved, no synthesized raw result).
5. **Delegate** to `apply_producer_result(graph, node_id, raw)` — capture →
   project → apply, unchanged. Surface its `graph`, `applied`, `outcome_status`,
   `reason`.

Admissibility (1) and resolution+copy (2–4) all **precede** dispatch, so a
non-admissible or unresolvable node **never fires a tool** — LM3I's "admissibility
before capture" extended to "admissibility before live side effects."

### Admissibility predicate (adapter-local)

```python
def _check_admissibility(graph, node_id) -> LiveProducerReason | None:
    if node_id not in graph.nodes:
        return "unknown_node"
    if node_id not in {n.id for n in runnable_nodes(graph)}:
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

### `execution_ref` grammar (boring and pinned)

A valid `execution_ref` fullmatches `^(?P<name>[^\s:]+)(?::v\d+)?$`. The tool
name is `name` (the version suffix, if present, is stripped). Rook tool names
contain no colon, so the only colon is the version separator.

| `execution_ref`              | Result                          | `tool_name` |
|------------------------------|---------------------------------|-------------|
| `None`                       | `execution_ref_missing`         | `None`      |
| `""`                         | `execution_ref_missing`         | `None`      |
| `"gh_create_csharp_script"`  | accepted                        | `gh_create_csharp_script` |
| `"gh_update_script:v1"`      | accepted                        | `gh_update_script` |
| `"tool:v123"`                | accepted                        | `tool`      |
| `":v1"`                      | `execution_ref_invalid`         | `None`      |
| `"tool:"`                    | `execution_ref_invalid`         | `None`      |
| `"tool:v"`                   | `execution_ref_invalid`         | `None`      |
| `"tool with space"`         | `execution_ref_invalid`         | `None`      |

No tool-name inference from intent or metadata. Only the version suffix is
stripped; everything else is rejected or passed through verbatim.

---

## Error handling

Closed 11-member `LiveProducerReason` union. Every not-applied path returns the
**input graph unchanged**. `tool_name` is populated from step 2 onward, so
`execution_params_missing` / `execution_params_invalid` / `params_copy_failed` /
`dispatch_failed` carry the resolved name for diagnostics, while admissibility
and `execution_ref_*` failures carry `None`. Reason precedence is the step order
above — pinned by tests where multiple faults coexist.

### `dispatch_failed` vs a returned failure dict

`dispatch_failed` is **only** for the injected callable **raising** (a transport
failure). A returned `{"success": False, ...}` is a **real raw result** — it
flows into step 5 and `apply_producer_result`, where the producer role projects
it to `succeeded` with evidence `tool_status="failed"` / `verified is False`
(the LM3I seam, now live-shaped). The adapter never synthesizes a raw result for
a transport failure; that would blur transport failure with tool-result failure.

### Applied-path invariant

Because admissibility is pre-checked and the graph is unchanged between
pre-check and dispatch, `apply_producer_result` re-checks runnable+role
(passes), captures, and applies — so on the applied path `applied=True` and
`reason=None`. The adapter surfaces the inner result faithfully rather than
asserting, keeping the pure primitive's contract authoritative.

---

## Out of scope (explicit — prevents quiet expansion)

- **No registered-template changes.** This slice does **not** modify
  `plan_graph_templates.py` to add `execution_params` to any template node.
  Tests build a small live-adapter fixture node carrying `execution_ref`,
  `outcome_projection_role`, and `execution_params` directly. Wiring template
  binding to populate execution params is a **later** slice. Otherwise LM4A
  quietly expands into template/binding policy.
- **No scheduler / sequencer.** One node, one step. No multi-node walk.
- **No planner integration, no model calls, no real `ToolDispatcher`
  instantiation, no HTTP, no Rhino.** The adapter takes the dispatch callable by
  injection; production passes `dispatcher.dispatch`, tests pass a fake.
- **No `apply_tool_result` on the producer path** (the LM1G direct-task bridge).
  Producer application stays `apply_producer_result`.
- **LM1F direct-task behavior preserved** — untouched.

---

## Testing (`mcp_server/tests/test_plan_graph_live.py`, Rhino-free)

- **Fake dispatch**: a spy recording every `(name, params)` call and returning a
  configured raw dict; plus a raising variant. No HTTP, no `ToolDispatcher`.
- **Happy path**: runnable producer node + valid `execution_ref` +
  `execution_params` + a `usable` `script_receipt` raw → `applied=True`,
  `outcome_status="succeeded"`, `tool_name` correct, spy called exactly once.
- **The live seam** (mirrors LM3I at the live layer): fake returns real-contract
  `success: False` + `created_with_errors` receipt → `applied=True`,
  `outcome_status="succeeded"`, and the inner graph's node evidence has
  `tool_status="failed"` / `verified is False`.
- **Each of the 11 reasons** as its own test. For every **pre-dispatch** reason
  (`unknown_node`, `node_not_runnable`, `role_missing`, `role_invalid`,
  `role_not_producer`, `execution_ref_missing`, `execution_ref_invalid`,
  `execution_params_missing`, `execution_params_invalid`, `params_copy_failed`)
  assert **the spy was never called** and the returned graph is the input graph.
- **`execution_ref` grammar**: a parametrized test over the table above
  (accepted shapes yield the stripped `tool_name`; rejected shapes yield
  `execution_ref_missing` / `execution_ref_invalid` with no dispatch).
- **Deep-copy proof**: the dispatched params is a **distinct object** from
  `node.metadata[EXECUTION_PARAMS_KEY]`; mutating the node metadata after the
  call does not change what was dispatched. `params_copy_failed` uses a value
  whose `__deepcopy__` raises (analogous to LM3I's `ExplodingRaw`).
- **`dispatch_failed`**: the raising fake → not-applied with
  `reason="dispatch_failed"`, `tool_name` set, input graph preserved,
  `outcome_status is None`.
- **Returned-failure-is-not-dispatch_failed**: a returned `{"success": False}`
  with a real receipt is applied via the pure runner (distinguishes transport
  failure from tool-result failure).
- **Precedence**: e.g. a non-runnable node that *also* lacks `execution_ref`
  returns `node_not_runnable` (admissibility wins over resolution).
- **Boundary/import test**: AST-parse `agent/plan_graph_live.py` and assert it
  imports only public symbols, contains no `_producer_*` private import, no
  `import *`, and no `tool_dispatcher` / `server` / ChatRunner import.

---

## Constraints (Global)

- Pure `learning/plan_graph_*` modules: **unchanged** this slice.
- Adapter imports: public pure symbols only; no private `_producer_*`; no
  dispatcher/server/ChatRunner import.
- Deterministic; no model calls; no live tools; no HTTP; no Rhino.
- Test runner: `mcp_server/.venv/Scripts/python.exe -m pytest -p no:cacheprovider`.
- Full PlanGraph + adapter suite must stay green (≥191 + new LM4A tests).
