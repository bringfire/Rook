# LM4P — Accepted-Selection → Typed Step Mapper (gated lookup)

**Date:** 2026-06-24
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push — policy pivot, rung 3
**Predecessors:** LM4N (#345) `propose_next_node` · LM4O (#352) `revalidate_proposal`

---

## 1. Goal

Complete the **propose → distrust → consume** ladder's third rung. LM4N proposes a node;
LM4O revalidates the proposal by re-deriving and full-equality checking. LM4P is the first
**consumer**: given a supplied proposal, the current graph, and an **explicit caller-authored
map** of `node_id → prebuilt Step`, it asks the LM4O distrust gate, and *only if accepted*
looks up the accepted node and returns the caller's exact typed `Step` (an LM4M
`ProducerStep` / `VerifierStep` / `BindStep`).

LM4P is **not a scheduler**: no dispatch, no loop, no graph mutation, no node selection (it
consumes a selection it was handed), and — critically — **no Step construction or
inference**. It maps an already-validated decision into runner language by *lookup only*.

The ladder:
- **LM4N:** policy may *propose*.
- **LM4O:** proposals are *distrusted and revalidated*.
- **LM4P:** an accepted selection is *mapped to a typed Step the caller pre-authored*.

---

## 2. Containment Contract (load-bearing)

- **Lookup, never construct.** LM4P returns the caller's prebuilt `Step` verbatim. It never
  builds a `Step`, never fills in params/expectations/bindings, never infers a Step from
  PlanGraph role/metadata. Enforced by an **AST guard that fails on any constructor call to
  `ProducerStep(...)` / `VerifierStep(...)` / `BindStep(...)`** in the module. (Using the
  classes for `isinstance` checks and type annotations is allowed; *calling* them is not.)
- **Delegate revalidation to LM4O.** LM4P imports `revalidate_proposal`, **not**
  `propose_next_node`. It does not know how to re-derive; it knows how to ask the distrust
  gate. AST-guarded (`propose_next_node` not referenced).
- **No fallback.** A rejected proposal yields no step — even when the map holds a valid entry
  for the node that is *now* correct. Validation rejection is final at the mapping layer too.
- **Distrust the caller map too.** `step_map` is runtime input. A missing entry, a non-`Step`
  value, or a `Step` that targets a different node are each rejected cleanly with a distinct
  reason — LM4P never crashes and never coerces.
- **No execution authority.** No dispatch, no loop, no graph mutation, no LLM. The returned
  `Step` is data; running it is a later (or caller's) concern.

---

## 3. Architecture

One new **agent-layer** module:

```
mcp_server/src/rook/agent/plan_graph_step_mapping.py
```

Agent-layer is *forced*, not chosen: LM4P imports both the LM4M `Step` types (agent:
`plan_graph_sequence_runner`) and LM4O `revalidate_proposal` (learning:
`plan_graph_revalidation`). Import direction stays one-way (`agent → {agent, learning}`). It
is pure-of-execution: a gated lookup that returns a verdict + an optional `Step`.

---

## 4. Public Surface

```python
from typing import Literal
from collections.abc import Mapping

StepMappingFailure = Literal[
    "revalidation_rejected",  # LM4O said REJECT (carry the RevalidationResult)
    "no_step_for_node",       # accepted, but step_map has no entry for the node
    "step_map_invalid",       # the map entry is not a ProducerStep/VerifierStep/BindStep
    "step_node_mismatch",     # the mapped Step targets a different node than accepted
]

@dataclass(frozen=True)
class StepMappingResult:
    mapped: bool
    step: Step | None                    # the caller's prebuilt Step iff mapped (same object)
    accepted_node_id: str | None         # from revalidation, iff ACCEPT
    failure: StepMappingFailure | None   # set iff not mapped
    reason: str                          # human/audit string
    revalidation: RevalidationResult     # the full LM4O result -- always present (audit)

def map_accepted_proposal_to_step(
    proposal: NodeSelectionProposal,
    graph: PlanGraph,
    step_map: Mapping[str, Step],
    expected_selector_ids: tuple[str, ...] = ("unique_ready_node:v1",),
) -> StepMappingResult: ...
```

`revalidation` is always populated (it is the gate's verdict, the audit spine). `step` is
non-None only on `mapped=True` and is the *same object* the caller put in `step_map` — never
a rebuilt or substituted one.

---

## 5. Logic (gate → lookup → validate-map; never construct, never fallback)

1. **Gate (delegate to LM4O).** `result = revalidate_proposal(proposal, graph,
   expected_selector_ids)`.
2. **Rejected → stop.** `result.decision != "ACCEPT"` → `mapped=False`,
   `failure="revalidation_rejected"`, `accepted_node_id=None`, `step=None`,
   `revalidation=result`. (Carries whatever LM4O decided — `untrusted_selector`,
   `selected_not_ready`, etc.)
3. **Lookup.** `accepted = result.accepted_node_id`. `accepted not in step_map` →
   `failure="no_step_for_node"`, `accepted_node_id=accepted`, `step=None`. (Refuse to invent.)
4. **Validate the map value.** `step = step_map[accepted]`. If `step` is not an instance of
   `(ProducerStep, VerifierStep, BindStep)` → `failure="step_map_invalid"`, `step=None`.
   (Reject malformed runtime input cleanly *before* touching its fields.)
5. **Target-node check.** Compute the mapped Step's target — `ProducerStep`/`BindStep` →
   `.node_id`; `VerifierStep` → `.verifier_node_id`. If target `!= accepted` →
   `failure="step_node_mismatch"`, `step=None` (the mismatched step is **not** returned — the
   map cannot redirect execution to a different node).
6. **Map.** Otherwise `mapped=True`, `step=step_map[accepted]` (the caller's exact object),
   `failure=None`, `reason="accepted node mapped to caller-authored step"`.

A small internal helper `_step_target_node_id(step)` does the isinstance-based field read in
step 5; it runs only after step 4 has confirmed `step` is a real `Step`, so it never falls
through or raises on bad input.

---

## 6. Boundaries / Invariants

- **Pure-of-execution:** no dispatch (`run_live_producer_node` / `SupportsLiveProducerNode`
  not imported), no loop, no graph mutation; never mutates `proposal`, `graph`, or `step_map`.
- **Imports:** `revalidate_proposal` + `RevalidationResult` (learning
  `plan_graph_revalidation`, module-level for the monkeypatch seam); `NodeSelectionProposal`
  (learning `plan_graph_selector`); `Step` + `ProducerStep` + `VerifierStep` + `BindStep`
  (agent `plan_graph_sequence_runner`); `PlanGraph` `TYPE_CHECKING`-quoted; stdlib
  `dataclass`/`typing`/`collections.abc`. **No `propose_next_node`** (delegates re-derivation
  to LM4O). **No `rook.agent.base_agent`, no dispatcher/server, no
  `apply_outcome`/`apply_verifier_step`/`apply_producer_result`, no LiteLLM/model.**
- **AST guards:** (a) no constructor call to `ProducerStep`/`VerifierStep`/`BindStep` in the
  module (lookup-only, mechanically reviewable); (b) no `propose_next_node` reference; (c) no
  agent-runner/dispatcher/server/model/`apply_*` import.
- Production change = **exactly** one new module
  (`git diff --numstat main...HEAD -- mcp_server/src` lists only
  `agent/plan_graph_step_mapping.py`); `base_agent.py` byte-stable; LM4M/LM4N/LM4O modules
  untouched.

---

## 7. Testing

Whole-branch diff = this spec + the plan + **1 module + 2 test files = 5 paths**.

### Task 1 — real TDD (the prod module)
`mcp_server/tests/test_plan_graph_step_mapping.py` (focused `test_plan_graph*.py` gate).
Failing tests first, then the module. Build a graph whose unique ready node is known, a
proposal via `propose_next_node`, and caller `step_map`s of prebuilt LM4M Steps.

- **mapped — ProducerStep:** accepted node `X`, `step_map={X: ProducerStep(X, …)}` →
  `mapped=True`, `result.step is step_map[X]` (exact object), `accepted_node_id == X`,
  `failure is None`, `revalidation.decision == "ACCEPT"`.
- **mapped — VerifierStep:** `step_map={X: VerifierStep(verifier_node_id=X, source_node_id=…)}`
  → `mapped=True` (target via `verifier_node_id`).
- **mapped — BindStep:** `step_map={X: BindStep(node_id=X, base_params={}, bindings={})}` →
  `mapped=True`.
- **revalidation_rejected:** a stale/forked/untrusted proposal → LM4O REJECT → `mapped=False`,
  `failure="revalidation_rejected"`, `accepted_node_id is None`, `step is None`,
  `revalidation.reject_reason` carried through. (Cover at least an untrusted and a stale case
  to show LM4P passes LM4O's verdict through unchanged.)
- **no_step_for_node:** accepted `X`, `step_map={}` (or only other keys) → `mapped=False`,
  `failure="no_step_for_node"`, `accepted_node_id == X`, `step is None`.
- **step_map_invalid:** accepted `X`, `step_map={X: object()}` → `mapped=False`,
  `failure="step_map_invalid"`, `step is None` (no crash, no inference).
- **step_node_mismatch — Producer:** `step_map={X: ProducerStep(node_id="Y")}` →
  `mapped=False`, `failure="step_node_mismatch"`, `step is None` (mismatched step not returned).
- **step_node_mismatch — Verifier:** `step_map={X: VerifierStep(verifier_node_id="Y",
  source_node_id="Z")}` → `step_node_mismatch`.
- **revalidate SEAM pin:** monkeypatch `plan_graph_step_mapping.revalidate_proposal` to return
  a sentinel `RevalidationResult` (ACCEPT, `accepted_node_id="s"`); with `step_map={s:
  ProducerStep("s")}` assert `mapped=True`, `result.revalidation is sentinel`, and the patched
  function received the **exact** `(proposal, graph, expected_selector_ids)` passed in. Proves
  LM4P delegates to LM4O and does not re-derive.
- **frozen / pure:** `proposal`, `graph`, and `step_map` unchanged after a call; two calls
  yield equal results; the returned `step` is identity-equal to the map entry.
- **no-Step-construction AST guard:** parse the module; assert there is **no `ast.Call` whose
  callee name is `ProducerStep` / `VerifierStep` / `BindStep`** (constructor ban), while
  isinstance usage and annotations are permitted.
- **import-boundary AST guard:** module imports no `rook.agent.base_agent`, no
  dispatcher/server, no LiteLLM/model; references no `propose_next_node`,
  `run_live_producer_node`, `apply_outcome`, `apply_verifier_step`, `apply_producer_result`.

### Task 2 — chain mapping guard
`mcp_server/tests/test_plan_graph_step_mapping_chain.py` (focused gate). Drive the real
5-node `gh_csharp_create_verify_repair_verify` template to where `verify_create` is uniquely
ready (`select_template` → `initialize_graph` → `apply_producer_result(create_script, …)`).
Build a caller `step_map` keyed by chain node id (each value a prebuilt Step that targets its
own node, e.g. `verify_create → VerifierStep("verify_create", "create_script",
expected_outcome="needs_repair")`, `repair_same_component → ProducerStep("repair_same_component",
…)`).

- **fresh → mapped:** `proposal = propose_next_node(graph)` (`SELECT_NODE("verify_create")`);
  `map_accepted_proposal_to_step(proposal, graph, step_map)` → `mapped=True`, `result.step is
  step_map["verify_create"]`.
- **stale after a real transition → no step, no fallback:** advance via
  `apply_verifier_step(graph, "verify_create", "create_script")` (needs_repair) so
  `repair_same_component` is now uniquely ready; map the **old** `verify_create` proposal
  against the advanced graph → `mapped=False`,
  `failure="revalidation_rejected"`, `revalidation.reject_reason == "selected_not_ready"`,
  `step is None` — **even though `step_map` contains a `repair_same_component` entry.** The
  no-fallback proof at the mapping layer.

Honest scope: LM4P returns a `Step` object; nothing in these guards dispatches or runs it —
no dispatch, no loop, no graph mutation driven by the mapping.

### Deliberate non-goal: no live test
LM4P is a pure-of-execution lookup over data structures; the `Step` it returns is never run
here. A `requires_rhino` test would add zero mapping-contract coverage. LM4P is a 2-task,
5-path slice with no live proof.

---

## 8. Process / Gates

- `codex/` branch off `main`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- PowerShell glob gotcha: enumerate the focused gate via `Get-ChildItem`.
- Focused PlanGraph gate green (rises from 316).
- No live acceptance step (pure-of-execution).
- Merge to `main` **always** needs explicit user approval.

---

## 9. North-Star Fit

The north-star scheduler eventually "validates [a proposal] against known contracts… inserts
it if safe" (§574–575). LM4O built the *validate* half; LM4P builds the *translate* half —
turning an accepted, revalidated selection into the runner's `Step` language — but still
withholds the *insert/run* authority: it constructs nothing, dispatches nothing, loops over
nothing, and refuses any map entry it cannot trust. The map is caller-authored, so execution
construction stays outside the policy/consumer seam. The next rung (its own design) would be
the first thing that actually *runs* a mapped Step under this gate — a bounded, still
non-scheduler step executor — or a runner that threads gate → map → `run_explicit_sequence`
for a caller-authored sequence. Both remain out of LM4P scope.
