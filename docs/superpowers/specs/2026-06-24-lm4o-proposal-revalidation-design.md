# LM4O — Proposal Revalidation Gate (distrust & verify policy)

**Date:** 2026-06-24
**Status:** Design approved (pending spec review)
**Campaign:** LM north-star internal DAG agent coordination push — policy pivot, rung 2
**Predecessors:** LM4N (#345) `propose_next_node` (first policy seam, proposal-only)

---

## 1. Goal

Honor LM4N's **snapshot-validity contract** — *"a NodeSelectionProposal describes the
snapshot observed at call time; it is NOT authority — any future consumer MUST revalidate
against the current graph before acting."* LM4O is the first thing that revalidates: a pure
gate that **distrusts** a supplied proposal and verifies it against the *current* graph,
returning a typed `ACCEPT(accepted_node_id)` or `REJECT(reject_reason)`.

The conceptual ladder:
- **LM4N:** policy may *propose*.
- **LM4O:** policy proposals are *distrusted and revalidated*.
- **LM4P (later):** an agent runner may *consume* an accepted selection.

LM4O performs **no execution**: no dispatch, no typed-`Step` construction, no scheduler
loop, no graph mutation. It loads the snapshot-validity contract without letting validation
become hidden selection.

---

## 2. Containment Contract (load-bearing)

- **Re-derive, don't re-implement.** Revalidation calls `propose_next_node(current_graph)`
  and compares the *fresh* proposal to the *supplied* one. The gate never hand-rolls a
  readiness check — it distrusts policy by re-running the **same** canonical rule against
  the current graph. (Mirrors LM4N's "observe-not-bypass.")
- **No fallback acceptance.** If the supplied proposal is stale/mismatched but a fresh
  proposal *would* be acceptable, LM4O still **REJECTS**. It may include the fresh proposal
  for audit, but it MUST NOT substitute it. `accepted_node_id` is *only ever*
  `proposal.selected_node_id` on ACCEPT — never the fresh proposal's. Validation must not
  become selection.
- **Distrust the whole proposal, not just the selected node.** `NodeSelectionProposal` is a
  public dataclass; a caller can hand the gate a malformed proposal. ACCEPT requires the
  supplied *actionable* proposal to **equal** the freshly re-derived one (all fields), not
  merely share a `selected_node_id`.
- **`expected_selector_ids` cannot launder a foreign selector.** Being in
  `expected_selector_ids` is necessary but not sufficient: ACCEPT also requires the
  supplied `selector_id` to equal the fresh proposal's `selector_id` (the one the gate
  actually re-derived). The gate validates `unique_ready_node:v1`; it must not accept a
  proposal stamped with a selector it did not re-derive.
- **Pure / learning-layer.** No `rook.agent.*`, no dispatcher/server, no
  `apply_outcome`/`apply_*_step`, no LLM. Never mutates the proposal or the graph.

---

## 3. Architecture

One new **learning-layer** module, beside the selector:

```
mcp_server/src/rook/learning/plan_graph_revalidation.py
```

Pure `(proposal, current_graph) -> RevalidationResult`. It imports `propose_next_node` and
`NodeSelectionProposal` from `plan_graph_selector` (module-level, so the re-derive seam is
monkeypatchable) and re-derives the fresh proposal through it. LM4P will be the first
agent-layer consumer that imports *this* gate one-way.

---

## 4. Public Surface

```python
from typing import Literal

RevalidationDecision = Literal["ACCEPT", "REJECT"]
RejectReason = Literal[
    "untrusted_selector",   # supplied selector_id not in expected_selector_ids
    "not_a_selection",      # supplied proposal is a HALT, not a SELECT_NODE
    "none_ready",           # fresh re-derivation: no node ready now (graph advanced)
    "no_longer_unique",     # fresh re-derivation: graph forked (>=2 ready)
    "selected_not_ready",   # fresh selects a DIFFERENT node than the supplied one
    "proposal_mismatch",    # same selected node, but supplied != fresh on another field
]

@dataclass(frozen=True)
class RevalidationResult:
    decision: RevalidationDecision
    accepted_node_id: str | None          # set iff ACCEPT; ALWAYS proposal.selected_node_id
    reject_reason: RejectReason | None    # set iff REJECT
    reason: str                           # human/audit string
    proposal: NodeSelectionProposal       # the supplied (snapshot-time) proposal -- audit
    fresh_proposal: NodeSelectionProposal | None  # re-derived now -- audit; None iff rejected before re-derive
    expected_selector_ids: tuple[str, ...]

def revalidate_proposal(
    proposal: NodeSelectionProposal,
    graph: PlanGraph,
    expected_selector_ids: tuple[str, ...] = ("unique_ready_node:v1",),
) -> RevalidationResult: ...
```

---

## 5. Logic (re-derive-and-compare, full-equality ACCEPT, no fallback)

1. **Trust provenance.** `proposal.selector_id not in expected_selector_ids` →
   **REJECT `untrusted_selector`**, `fresh_proposal=None` (do not even re-derive — the
   proposal's provenance is untrusted).
2. **Re-derive (the seam).** `fresh = propose_next_node(graph)`. Populates `fresh_proposal`
   on every path from here on.
3. **Actionable?** `proposal.decision != "SELECT_NODE"` → **REJECT `not_a_selection`**
   (a halt is not an actionable selection).
4. **Classify against the fresh re-derivation:**
   - `fresh.decision == "HALT_NONE_READY"` → **REJECT `none_ready`**.
   - `fresh.decision == "HALT_AMBIGUOUS_READY"` → **REJECT `no_longer_unique`**.
   - `fresh.decision == "SELECT_NODE"`:
     - `proposal.selected_node_id != fresh.selected_node_id` → **REJECT
       `selected_not_ready`** (a *different* node is now uniquely ready). **No fallback** —
       `fresh` is valid, but we reject and never substitute it.
     - `proposal != fresh` (selected node matches, but some other field —
       `candidate_node_ids`, `ready_count`, `reason`, `selector_id`, or `decision` —
       differs) → **REJECT `proposal_mismatch`**.
     - `proposal == fresh` → **ACCEPT**, `accepted_node_id = proposal.selected_node_id`.

The ACCEPT condition is exactly: *the supplied selector is trusted AND the supplied
proposal equals the freshly re-derived proposal.* Because `NodeSelectionProposal` is a
frozen dataclass, `proposal == fresh` is full field equality — so:

- **P2 (whole-proposal distrust):** a malformed supplied proposal
  (`decision="SELECT_NODE"`, `selected_node_id="x"`, `candidate_node_ids=("x","y")`,
  `ready_count=2`) is **rejected `proposal_mismatch`** even though `selected_node_id`
  matches a fresh `SELECT_NODE("x")` — because `candidate_node_ids`/`ready_count` differ.
- **P3 (no selector laundering):** a proposal with `selector_id="custom:v1"` passed via
  `expected_selector_ids=("custom:v1", "unique_ready_node:v1")` clears step 1 but is
  **rejected `proposal_mismatch`** at step 4 — the fresh proposal's `selector_id` is
  `"unique_ready_node:v1"`, so `proposal != fresh`. Being trusted by the caller never
  substitutes for matching the selector the gate actually re-derived.

`reason` equality is included (it is part of the dataclass), making the gate maximally
distrustful of tampered audit fields.

---

## 6. Boundaries / Invariants

- **Pure:** reads the graph only via `propose_next_node` (→ `runnable_nodes`); never mutates
  `proposal` or `graph`.
- **Imports:** `propose_next_node` + `NodeSelectionProposal` from
  `rook.learning.plan_graph_selector` (module-level, for the monkeypatch seam pin);
  `PlanGraph` `TYPE_CHECKING`-quoted; stdlib `dataclass`/`typing`. **No `rook.agent.*`, no
  dispatcher/server, no `apply_outcome`/`apply_verifier_step`/`apply_producer_result`, no
  LiteLLM/model.** AST-guarded.
- Production change = **exactly** one new module
  (`git diff --numstat main...HEAD -- mcp_server/src` lists only
  `learning/plan_graph_revalidation.py`); `base_agent.py` byte-stable; LM4N selector and
  all other modules untouched.

---

## 7. Testing

Whole-branch diff = this spec + the plan + **1 module + 2 test files = 5 paths**.

### Task 1 — real TDD (the prod module)
`mcp_server/tests/test_plan_graph_revalidation.py` (focused `test_plan_graph*.py` gate).
Failing tests first, then the module. A small helper builds a graph whose unique ready node
is known, and a `propose_next_node`-derived (or hand-built but equal-to-fresh) proposal.

- **ACCEPT:** supplied proposal equals the fresh re-derivation on a graph where the selected
  node is still uniquely ready → `decision == "ACCEPT"`, `accepted_node_id == selected`,
  `reject_reason is None`, `fresh_proposal == proposal`.
- **REJECT `untrusted_selector`:** `proposal.selector_id == "other:v9"` with default
  expected → REJECT, `fresh_proposal is None` (re-derivation skipped).
- **REJECT `not_a_selection`:** supplied is `HALT_AMBIGUOUS_READY` (or `HALT_NONE_READY`) →
  REJECT `not_a_selection`.
- **REJECT `none_ready`:** supplied `SELECT_NODE("a")`; current graph has zero ready (node
  consumed) → fresh `HALT_NONE_READY` → REJECT `none_ready`.
- **REJECT `no_longer_unique`:** supplied `SELECT_NODE("a")`; current graph forked (`a`+`b`
  ready) → fresh `HALT_AMBIGUOUS_READY` → REJECT `no_longer_unique`.
- **REJECT `selected_not_ready` (no fallback):** supplied `SELECT_NODE("a")`; current graph's
  unique ready is `b` → fresh `SELECT_NODE("b")` → REJECT `selected_not_ready`,
  `accepted_node_id is None`, `fresh_proposal` present (`b`) but **not** substituted.
- **REJECT `proposal_mismatch` — P2:** supplied `SELECT_NODE("x")` with
  `candidate_node_ids=("x","y")`, `ready_count=2`; fresh `SELECT_NODE("x")` with
  `candidate_node_ids=("x",)`, `ready_count=1` → REJECT `proposal_mismatch`,
  `accepted_node_id is None`.
- **REJECT `proposal_mismatch` — P3 (no selector laundering):** supplied `SELECT_NODE("x")`
  with `selector_id="custom:v1"`, passed via
  `expected_selector_ids=("custom:v1","unique_ready_node:v1")`; fresh `selector_id ==
  "unique_ready_node:v1"` → REJECT `proposal_mismatch` (clears `untrusted_selector` but
  fails full equality on `selector_id`).
- **REJECT `proposal_mismatch` — tampered reason:** supplied `SELECT_NODE("x")` with a
  doctored `reason`, everything else equal to fresh → REJECT `proposal_mismatch` (reason is
  part of the audit record).
- **re-derive SEAM pin:** monkeypatch `plan_graph_revalidation.propose_next_node` to return
  a sentinel fresh proposal and assert (a) the result's `fresh_proposal` is that sentinel,
  (b) the patched function received the **exact** graph object. Proves the gate re-derives
  through the seam, not a private readiness check.
- **`expected_selector_ids` override:** a custom expected tuple that includes the proposal's
  id changes only the `untrusted_selector` gate, not the equality requirement (covered by
  the P3 test); a default-expected call rejects a foreign id as `untrusted_selector`.
- **frozen / pure:** input `graph` and `proposal` unchanged after a call; calling twice
  yields equal results.
- **AST import-boundary guard:** module imports `propose_next_node`/`NodeSelectionProposal`
  from `plan_graph_selector` + `PlanGraph` (TYPE_CHECKING) + stdlib; references no
  `rook.agent.*`, no dispatcher/server, no `apply_outcome`/`apply_verifier_step`/
  `apply_producer_result`, no LiteLLM/model.

### Task 2 — chain revalidation guard
`mcp_server/tests/test_plan_graph_revalidation_chain.py` (focused gate). Drive the real
5-node `gh_csharp_create_verify_repair_verify` template through the reducer to the point
where `verify_create` is the uniquely-ready node (after `initialize_graph` +
`apply_producer_result(create_script, …)`), and capture
`proposal = propose_next_node(graph)` (→ `SELECT_NODE("verify_create")`):

- **fresh-against-same-graph → ACCEPT:** `revalidate_proposal(proposal, graph)` → ACCEPT,
  `accepted_node_id == "verify_create"`.
- **stale-across-a-real-transition → REJECT `selected_not_ready` (deterministic, no
  fallback):** advance the graph via `apply_verifier_step(graph, "verify_create",
  "create_script")` (outcome `needs_repair`), so `verify_create` is now `needs_repair` and
  `repair_same_component` becomes the uniquely-ready node. Re-derivation on the advanced
  graph yields `SELECT_NODE("repair_same_component")`. Revalidating the **old**
  `verify_create` proposal against the advanced graph → **REJECT `selected_not_ready`**
  (`accepted_node_id is None`; `fresh_proposal` is the `repair_same_component` selection but
  is **not** substituted). This pins that, when a *different* valid node is now uniquely
  ready, the gate refuses rather than re-selecting. (`none_ready` has its own Task-1 unit
  coverage.)
- **fork → REJECT `no_longer_unique`:** revalidate a `SELECT` proposal against a hand-built
  2-ready fork graph → REJECT `no_longer_unique`.

Honest scope: still no dispatch, no step construction, no loop — the reducer drives the
graph; the gate only judges whether a snapshot-time proposal still holds.

### Deliberate non-goal: no live test
The gate is a pure read/compare over `PlanGraph` state; the graph it observes is identical
in shape whether produced live or offline. A `requires_rhino` test would re-prove the
already-proven chain and add zero revalidation-contract coverage. LM4O is a 2-task, 5-path
slice with no live proof.

---

## 8. Process / Gates

- `codex/` branch off `main`.
- Run gates with `mcp_server/.venv/Scripts/python.exe` from the repo root.
- PowerShell glob gotcha: enumerate the focused gate via `Get-ChildItem`.
- Focused PlanGraph gate green (rises from 301).
- No live acceptance step (pure primitive).
- Merge to `main` **always** needs explicit user approval.

---

## 9. North-Star Fit

The north-star scheduler (§9.3, §574–575) eventually "validates [a proposal] against known
contracts… inserts it if safe." LM4O builds the *validate* half in isolation, with no
insert and no authority: it re-derives the trusted rule against the current graph and
accepts only an exact match, rejecting everything else without substitution. It makes the
scaffold able to **distrust** policy — the operational honesty that must exist before any
consumer is allowed to act on a proposal. The next rung (LM4P, its own design) is the
agent-layer consumer that maps an *accepted* selection to a typed step and, eventually,
dispatch — still no broad scheduler loop.
