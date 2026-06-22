# LM3F — Role-Aware Outcome Projection from Receipt Evidence

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), sixth slice
**Branch:** `codex/lm3f-role-aware-outcome-projection`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM1D `script_receipt` (`gh_script_receipts.py`), LM1E reducer/types (`plan_graph.py`), LM1F tool-result adapter (`plan_graph_outcomes.py`), LM3D verifier adapter (`plan_graph_verifiers.py`).

---

## Summary

LM3F adds **role-aware outcome projection**: a pure function that converts an
already-captured `NodeEvidence` (its `script_receipt`) into a `NodeOutcome`
**whose meaning depends on the node's role**. The same receipt projects to
different graph outcomes by role — an `artifact_producer` treats
`created_with_errors` as success (the artifact exists and is repairable), while
an `artifact_verifier` or a `direct_task` treats it as `needs_repair`.

This formalizes the seam LM1D's receipt already separates and LM1F deliberately
compresses: **artifact-existence success** (the tool created / wrote / placed the
artifact) versus **artifact-functional/task success** (the artifact
compiles / solves / is usable). Role-awareness is the layer **above** LM1F — not a
correction to it. LM1F stays exactly as it is.

The producer role is the missing key that makes the deferred 5-node
verifier-mediated template bridge-drivable: because the reducer's `requires` edge
only unlocks on a source status of `succeeded` (`_requires_satisfied`), a create
node that LM1F maps to `needs_repair` can never unlock a downstream verifier.
`artifact_producer` projects `created_with_errors → succeeded`, so the verifier
unlocks — while the same evidence still records `verified=False` so the repair
work is not lost.

LM3F is a **pure role-semantics proof only**. It does not wire roles into
templates or `node.metadata`, does not revive the 5-node template, and does not
touch `PlanGraph`, the walker, LM1F, or LM3E. Role adoption (metadata / template
wiring) and the end-to-end 5-node drive are a later slice.

## Boundary (hard constraints)

- **Role is an explicit argument**, not graph state. The first slice declares the
  role as a closed `Literal` parameter to a pure helper. No `node.metadata` role
  key and no new `PlanGraphNode` field in this slice (deferred until the
  projection table is proven and templates need to carry roles).
- **Input is `NodeEvidence` (or `None`)** — never a raw tool result, never
  `GraphMemory`. Output is a `NodeOutcome`.
- **Single-sourced conservative mapping.** The conservative projection
  (`direct_task` / `artifact_verifier`) rides the existing public
  `ARTIFACT_STATUS_TO_OUTCOME` in `plan_graph_outcomes`. No second copy.
- **LM3D becomes a compatibility wrapper.** `script_receipt_verifier_outcome`
  keeps its public name and signature and delegates to
  `project_receipt_outcome(evidence, "artifact_verifier")`. LM3D's existing
  behavior is a **hard regression contract** (its current tests stay unchanged
  and green).
- **No `needs_escalation`.** Escalation needs retry/attempt policy, not receipt
  status alone — a later slice. Producer's gate failure is `blocked`, never
  `needs_repair` (repair needs an artifact anchor too).
- **Invalid role fails loudly.** An unknown role (e.g. `"banana"`, possible at
  runtime despite the `Literal`) raises `ValueError`. Evidence failures produce
  `blocked` outcomes; invalid *API usage* is programmer error and must raise.
- **No walker/scheduler integration, no live tools, no model calls, no
  `planner.py`, no LM1F change, no LM3E change.** Receipt inspection is this
  adapter's purpose (like LM1F / LM3D).
- **Never crash on data.** Malformed evidence and deep-copy failures return a
  `blocked` outcome with an explanatory error, not an exception. (Contrast: an
  invalid *role* raises — that is API misuse, not data.)
- **Import-light, one-way.** `plan_graph_projection` imports only
  `rook.learning.plan_graph` and `rook.learning.plan_graph_outcomes` among rook
  modules, plus stdlib `copy`. `plan_graph_verifiers` imports
  `plan_graph_projection`; projection must **never** import verifiers. Enforced by
  an AST allowlist test and a subprocess probe.

## Module & files

- **New:** `mcp_server/src/rook/learning/plan_graph_projection.py`
- **Modify (behavior-preserving):**
  `mcp_server/src/rook/learning/plan_graph_verifiers.py` —
  `script_receipt_verifier_outcome` becomes a thin wrapper delegating to
  `project_receipt_outcome(evidence, "artifact_verifier")`. The verifier purity
  allowlist test is updated **only** to permit the new `plan_graph_projection`
  import.
- **New tests:** `mcp_server/tests/test_plan_graph_projection.py`

## Public surface

```python
OutcomeProjectionRole = Literal["direct_task", "artifact_producer", "artifact_verifier"]


def project_receipt_outcome(
    evidence: NodeEvidence | None, role: OutcomeProjectionRole
) -> NodeOutcome
```

`OutcomeProjectionRole` is a closed `Literal`. An unrecognized `role` value raises
`ValueError` before any evidence inspection.

## Role taxonomy & projection table

Two distinct projection *behaviors* behind three named roles. `direct_task` and
`artifact_verifier` share the conservative behavior today but remain distinct
names (distinct call sites; they may diverge in a later slice).

| `artifact_status` | `direct_task` / `artifact_verifier` (conservative) | `artifact_producer` |
|---|---|---|
| `usable` | succeeded · `verified=True` | succeeded · `verified=True` (ungated) |
| `created_with_errors` | needs_repair · `verified=False` | **succeeded · `verified=False`** (gated) |
| `written_with_errors` | needs_repair · `verified=False` | **succeeded · `verified=False`** (gated) |
| `verification_pending` | blocked · `verified=carried` | **succeeded · `verified=None`** (gated) |
| `unknown` | blocked · `verified=carried` | blocked · `verified=carried` (ungated) |
| missing / non-dict receipt / no `artifact_status` | reference-free blocked (error: missing) | reference-free blocked (error: missing) |
| present but not a table key | reference-free blocked (error: unrecognized) | reference-free blocked (error: unrecognized) |
| deep-copy failure | reference-free blocked (error: copy failed) | reference-free blocked (error: copy failed) |

The conservative column is byte-identical to today's LM3D (which is
`ARTIFACT_STATUS_TO_OUTCOME` plus LM3D's `verified` / message / facts rules).

**Core insight — producer decouples `status` from `verified`.** `NodeOutcome.status`
expresses **existence / task-progress** success (this is what unlocks the
`requires` edge in the reducer). `NodeEvidence.verified` independently expresses
**functional** success. A producer can be `succeeded` with `verified=False` — "I
produced the artifact; it is not clean yet" — which unlocks a downstream verifier
*and* records, in the same evidence, that repair work remains.

## Producer mutation-evidence gate

The producer's three **promoted** rows (`created_with_errors`,
`written_with_errors`, `verification_pending`) promote to `succeeded` **only when
mutation evidence is present**:

```python
_has_mutation_evidence(receipt) is True when ANY of:
    receipt["mutation"]["status"] in {"created", "written", "updated"}
    OR a non-empty mutation.component_guid (str)
    OR a non-empty repair_anchor.component_guid (str)
    OR a NON-EMPTY repair_anchor dict
```

An empty `{}` repair anchor is **not** evidence. `usable` and `unknown` are never
gated (`usable → succeeded` because verification clean implies existence;
`unknown → blocked` always).

When a promoted row lacks mutation evidence → **`blocked`**, with the
**cleanly-copied receipt preserved** (isolated from the input),
`error="producer: artifact existence unconfirmed"`, `verified` carried/`None`, and
**no facts**. This is the honest outcome: there is no proof an artifact exists, so
the graph must not unlock a verifier (or a repair node) on nothing. `blocked`
routes via `on_failure`.

This producer-unconfirmed blocked path **preserves** the receipt, distinct from
the **reference-free** blocked path (receipt `None`) reserved for malformed /
unrecognized / copy-failed evidence — because here the receipt copied cleanly; the
only deficiency is insufficient existence proof, which is exactly the detail a
debugger needs to see.

## Facts & memory policy

Facts are **role-conditional** — this is what preserves LM3D's contract:

- **Conservative roles (`direct_task`, `artifact_verifier`):** keep LM3D's exact
  behavior — emit `component_guid` and/or `repair_anchor` into
  `memory_updates.facts` whenever derivable on the clean-copy path, including on
  the `verification_pending` / `unknown` blocked outcomes. Reference-free blocked
  cases emit no facts.
- **`artifact_producer`:** emit facts **only on confirmed success**, and then only
  **when derivable** — facts are *not* guaranteed for every producer success.
  - Mutation-status-only evidence (`mutation.status="created"` with no guid and no
    anchor) → `succeeded` with **no facts** (nothing derivable to emit).
  - Guid / anchor evidence → `succeeded` with `component_guid` and/or
    `repair_anchor` facts present.
  - Producer blocked paths (unconfirmed, `unknown`) emit **no facts**.

`node_summary` is a minimal role-local string (`"<prefix>: <status>"`).

## Message vocabulary (parity)

Messages are **role-prefixed**. The `artifact_verifier` branch must reproduce
LM3D's strings **verbatim** so the regression + parity tests pin them:

- `"verifier: artifact usable"`, `"verifier: artifact needs repair"`,
  `"verifier: artifact_status '<status>' is not usable"`,
  `"verifier: missing receipt or artifact_status"`,
  `"verifier: unrecognized artifact_status '<value>'"`,
  `"verifier: evidence copy failed"`, and `node_summary` `"verifier: <status>"` /
  `"verifier: blocked"`.

`direct_task` uses a `"task:"` prefix; `artifact_producer` uses a `"producer:"`
prefix, including the gate-failure error `"producer: artifact existence
unconfirmed"`. Producer success messages are short non-error strings (e.g.
`"producer: artifact usable"`, `"producer: artifact created with repairable
errors"`, `"producer: artifact written with repairable errors"`, `"producer:
artifact produced, verification pending"`).

`NodeOutcome.status` is always one of `succeeded` / `needs_repair` / `blocked` —
never an administrative status, never `needs_escalation`.

## Approved decisions

- **A — Role is an explicit `Literal` argument** to a pure helper (not metadata,
  not a typed `PlanGraphNode` field) for this slice. Provisional: metadata is the
  likely future home once templates carry roles; deferred until the table is
  proven.
- **B — LM3D delegates to the new helper.** `project_receipt_outcome` owns the
  role-aware projection; `script_receipt_verifier_outcome` is the
  `artifact_verifier` compatibility wrapper. LM3D's public function and tests are
  the hard regression contract; new parity tests prove wrapper == direct call.
- **C — Producer promotion requires mutation evidence**, falling back to `blocked`
  ("existence unconfirmed") — never `needs_repair`. `usable` / `unknown` ungated.
- **D — Producer-unconfirmed blocked preserves the cleanly-copied receipt** (new
  flavor), distinct from the reference-free blocked reserved for
  missing/unrecognized/copy-fail.
- **E — Facts are role-conditional and emitted when derivable** — conservative
  roles keep LM3D facts behavior; producer emits facts only on success and only
  when a guid/anchor is derivable (mutation-status-only success emits none).
- **F — Invalid role raises `ValueError`** (API misuse), distinct from evidence
  failures (which return `blocked`).
- **G — New module `plan_graph_projection.py`** is the home; one-way import
  `verifiers → projection → {plan_graph, plan_graph_outcomes}`.

## Outcome construction (algorithm)

`project_receipt_outcome(evidence, role)`:

1. **Validate role first.** If `role` not in
   `{"direct_task", "artifact_producer", "artifact_verifier"}` → raise
   `ValueError` (before any evidence inspection).
2. Derive `prefix` from role (`"task"` / `"producer"` / `"verifier"`).
3. `receipt = evidence.receipt` when `evidence` is not `None` and `evidence.receipt`
   is a `dict`; else `None`.
4. **Reference-free blocked** (receipt `None`):
   - receipt missing / non-dict / no `"artifact_status"` →
     `"<prefix>: missing receipt or artifact_status"`.
   - `artifact_status` present but not a known table key →
     `"<prefix>: unrecognized artifact_status '<value>'"`.
   Reference-free blocked carries `receipt=None`, `repair_anchor=None`,
   `verified=<carried-or-None>`, `node_summary="<prefix>: blocked"`, no facts.
5. **Deep-copy guard:** copying `receipt` / `evidence.repair_anchor` is wrapped in
   `try/except Exception`; on failure → reference-free blocked,
   `"<prefix>: evidence copy failed"`.
6. **Conservative roles** (`direct_task`, `artifact_verifier`): apply LM3D's exact
   logic — status from `ARTIFACT_STATUS_TO_OUTCOME`, `verified`
   (`succeeded→True`, `needs_repair→False`, `blocked→carried`), messages per the
   prefix, facts from derivable `component_guid` / `repair_anchor` on the
   clean-copy path. The `artifact_verifier` prefix reproduces LM3D verbatim.
7. **Producer role:**
   - `usable` → `succeeded`, `verified=True`, facts when derivable.
   - `unknown` → `blocked`, `verified=carried`, no facts (receipt preserved).
   - promoted rows (`created_with_errors` / `written_with_errors` /
     `verification_pending`): if `_has_mutation_evidence(receipt_copy)` →
     `succeeded` with `verified` `False` / `False` / `None` respectively, facts
     when derivable; else → blocked-unconfirmed (receipt preserved, no facts,
     `error="producer: artifact existence unconfirmed"`).

## Testing (TDD)

1. **Regression (unchanged):** the entire existing `test_plan_graph_verifiers.py`
   stays green with **no edits to its assertions** — LM3D behavior is the
   contract. (Only the verifier purity allowlist test gains
   `plan_graph_projection`.)
2. **Parity:** for representative evidence (`usable`, `created_with_errors`,
   `verification_pending`, missing receipt, unrecognized status, deep-copy
   failure), `project_receipt_outcome(ev, "artifact_verifier")` produces an
   outcome equal to `script_receipt_verifier_outcome(ev)` — status, `verified`,
   message, error, and `memory_updates`.
3. **Producer success — facts derivable:** each promoted row with **guid/anchor**
   evidence → `succeeded`, correct `verified` (`False`/`False`/`None`),
   `component_guid` (and `repair_anchor` when present) in `memory_updates.facts`.
4. **Producer success — mutation-status-only:** `mutation.status="created"` (no
   guid, no anchor) on `created_with_errors` → `succeeded`, `verified=False`,
   **no facts** (facts are emitted when derivable, not guaranteed).
5. **Producer gate failure:** each promoted row with **no** mutation evidence
   (and an empty `{}` repair anchor proving it is not counted) → `blocked`,
   receipt preserved, no facts, `error="producer: artifact existence
   unconfirmed"`, `verified` carried/`None`.
6. **Producer ungated rows:** `usable → succeeded`/`verified=True`;
   `unknown → blocked`/no facts.
7. **`direct_task`:** conservative status mapping with `"task:"` messages
   (e.g. `created_with_errors → needs_repair`, `usable → succeeded`,
   `verification_pending → blocked`).
8. **Invalid role:** `project_receipt_outcome(evidence, "banana")` raises
   `ValueError`; raised **before** evidence inspection (passing `evidence=None`
   with a bad role still raises `ValueError`, not a blocked outcome).
9. **Deep-copy isolation:** mutating the input `evidence.receipt` /
   `repair_anchor` after the call does not change the returned outcome's evidence
   or `memory_updates`, for producer success and producer-unconfirmed paths.
10. **Single-source / closed-Literal guards:** for every `(status, expected)` in
    `ARTIFACT_STATUS_TO_OUTCOME`, the conservative roles yield
    `outcome.status == expected` (proving they ride the shared table); the role
    `Literal` has exactly the three expected members.
11. **Purity:** AST allowlist (`plan_graph_projection` rook imports ⊆
    {`plan_graph`, `plan_graph_outcomes`}); subprocess probe (importing
    `plan_graph_projection` loads no `tool_dispatcher` / `dspy` / `litellm`); the
    updated verifier allowlist now permits `plan_graph_projection` and nothing
    else new.

## Out of scope (LM3F)

- Wiring roles into templates or `node.metadata`; any `PlanGraphNode` field
  change → later slice.
- Reviving the 5-node verifier-mediated template end-to-end (LM3F supplies the
  producer projection that *enables* it, but does not drive it).
- `needs_escalation` and any retry/attempt-policy input.
- Walker / scheduler integration; `GraphMemory` input; raw tool results (LM1F's
  job); LM1F changes of any kind.

## Roadmap (recorded, not built)

**Next candidate — role adoption + 5-node revival.** Once the projection table is
proven, a follow-up slice carries the role on the node (most likely
`node.metadata` with a strict allow-list, per Decision A's provisional lean) and a
runner step that projects a producer node's evidence with its declared role,
unlocking the downstream verifier through the reducer. That slice can finally
re-drive the 5-node verifier-mediated template end-to-end through the LM1G bridge
/ LM3E runner.

## File touch list

- Add: `mcp_server/src/rook/learning/plan_graph_projection.py` —
  `OutcomeProjectionRole`, `project_receipt_outcome`, `_has_mutation_evidence`,
  small private helpers.
- Modify: `mcp_server/src/rook/learning/plan_graph_verifiers.py` —
  `script_receipt_verifier_outcome` delegates to
  `project_receipt_outcome(evidence, "artifact_verifier")`.
- Modify: `mcp_server/tests/test_plan_graph_verifiers.py` — update **only** the
  purity allowlist test to permit `plan_graph_projection`; behavior assertions
  unchanged.
- Add: `mcp_server/tests/test_plan_graph_projection.py` — LM3F tests.
