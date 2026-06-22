# LM3D — Verifier-Outcome Adapter (NodeEvidence → verifier NodeOutcome)

**Date:** 2026-06-22
**Status:** Approved (design)
**Category:** LM campaign — LM3 (Planner / PlanGraph execution scaffold), fourth slice
**Branch:** `codex/lm3d-verifier-outcome-adapter`
**North-star:** `docs/superpowers/specs/2026-06-19-rook-local-internal-models-north-star.md`
**Builds on:** LM1D `script_receipt` (`gh_script_receipts.py`), LM1E reducer/types (`plan_graph.py`), LM1F tool-result adapter (`plan_graph_outcomes.py`).

---

## Summary

LM3D adds the **verifier-outcome adapter**: a pure function that converts an
**already-captured** `NodeEvidence` (its `script_receipt`) into a *verifier
node's* `NodeOutcome`. It gives a verifier node a legitimate way to emit
`needs_repair` / `blocked` from receipt truth, instead of pre-seeding those
statuses into fixtures.

It is distinct from LM1F: **LM1F** consumes a *raw tool result*
(`{success, data.script_receipt}`) and produces the **executing** node's outcome;
**LM3D** consumes already-produced `NodeEvidence` and produces a **verifier**
node's outcome. The two share one truth table for "what an `artifact_status`
means," single-sourced so they can never drift.

LM3D is the **pure adapter only**. Wiring a verifier node into the walker (and
reviving the deferred 5-node verifier-mediated template) is a later slice — this
slice does **not** touch the walker, schedule, call tools, inspect live state, or
introduce escalation policy.

## Boundary (hard constraints)

- **Input is `NodeEvidence` (or `None`)** — never a raw tool result, never
  `GraphMemory`. Output is a `NodeOutcome`.
- **Single-sourced mapping.** The `artifact_status → outcome` table is promoted
  to a public `ARTIFACT_STATUS_TO_OUTCOME` in `plan_graph_outcomes` and consumed
  by both LM1F and LM3D. LM3D reuses **only the table**, not LM1F's private
  helpers.
- **No `needs_escalation`.** Escalation needs retry/attempt policy, not receipt
  status alone — a later slice.
- **No walker/scheduler integration, no live tools, no model calls, no
  `planner.py`.** Receipt inspection is this adapter's purpose (like LM1F).
- **Never crash on data.** Malformed evidence and deep-copy failures return a
  `blocked` outcome with an explanatory error, not an exception.
- **Import-light.** `plan_graph_verifiers` imports only `rook.learning.plan_graph`
  (`NodeEvidence`, `NodeOutcome`) and `rook.learning.plan_graph_outcomes`
  (`ARTIFACT_STATUS_TO_OUTCOME`) among rook modules, plus stdlib `copy`. Enforced
  by an AST allowlist test and a subprocess probe (no dispatcher / walker / bridge
  / templates / planner / dspy / litellm).

## Module & files

- **New:** `mcp_server/src/rook/learning/plan_graph_verifiers.py`
- **Modify (behavior-preserving):** `mcp_server/src/rook/learning/plan_graph_outcomes.py`
  — rename `_ARTIFACT_STATUS_TO_OUTCOME` → public `ARTIFACT_STATUS_TO_OUTCOME` and
  update its one internal use in `_outcome_status`. (Repo-wide check: the private
  name is referenced only inside this module; no tests reference it by name.)
- **New tests:** `mcp_server/tests/test_plan_graph_verifiers.py`

## Public surface

```python
def script_receipt_verifier_outcome(evidence: NodeEvidence | None) -> NodeOutcome
```

A verifier node re-judges an already-captured `NodeEvidence` and emits its own
outcome.

## Mapping (single-sourced from `plan_graph_outcomes.ARTIFACT_STATUS_TO_OUTCOME`)

| `artifact_status` | outcome |
|---|---|
| `usable` | `succeeded` |
| `created_with_errors`, `written_with_errors` | `needs_repair` |
| `verification_pending`, `unknown` | `blocked` |
| missing / non-dict receipt / no `artifact_status` field / `evidence is None` | `blocked` (error: missing) |
| present but not a table key (e.g. `"future_status"`) | `blocked` (error: unrecognized) |

Status is `ARTIFACT_STATUS_TO_OUTCOME.get(artifact_status, "blocked")` for present
values; the missing/none cases resolve to `blocked` before the lookup. **Never**
`needs_escalation`.

## Outcome construction

Let `receipt = evidence.receipt` when `evidence` is not `None` and
`evidence.receipt` is a `dict`; else `None`.

1. **Determine status + diagnostics:**
   - `evidence is None` or `receipt is None` or `"artifact_status" not in receipt`
     → `status="blocked"`, `error="verifier: missing receipt or artifact_status"`.
   - `artifact_status` present and in the table → `status=ARTIFACT_STATUS_TO_OUTCOME[
     artifact_status]`. For the `blocked` ones (`verification_pending` / `unknown`)
     set a non-error `message="verifier: artifact_status '<status>' is not usable"`
     (`error=None`). For `succeeded` / `needs_repair`, a short non-error
     `message`.
   - `artifact_status` present but **not** a table key →
     `status="blocked"`, `error="verifier: unrecognized artifact_status '<value>'"`.

2. **Deep-copy guard (tightening 3):** copying `receipt` / `repair_anchor` is
   wrapped in `try/except Exception`. On failure → `status="blocked"`,
   `error="verifier: evidence copy failed"`, no `facts`, no carried receipt.

3. **`verified` (tightening 1):**
   - `succeeded` → `True`; `needs_repair` → `False`;
   - `blocked` → `evidence.verified` if `evidence is not None and
     evidence.verified is not None`, else `None`. (Don't overstate verification.)

4. **Evidence carried forward:** a fresh `NodeEvidence(tool_status=
   evidence.tool_status (or None), verified=<per rule>, receipt=deepcopy(receipt)
   or None, repair_anchor=deepcopy(evidence.repair_anchor) if present else None,
   message=<message>, error=<error>)`.

5. **`memory_updates` (tightening 4):** only emit `facts` from a **well-formed**
   receipt (status is one of `succeeded`/`needs_repair`/known-blocked, copy
   succeeded): `facts = {}`, then add `component_guid` (a `str`, from
   `receipt["mutation"]["component_guid"]` or `repair_anchor["component_guid"]`,
   computed locally) and `repair_anchor` (a `dict`, deep-copied) when clearly
   structured. For missing / unrecognized / copy-failed cases, emit **no
   `facts`**. `node_summary` is a minimal verifier-local string (e.g.
   `"verifier: <status>"`) — LM1F's `_ARTIFACT_STATUS_TO_SUMMARY` is **not**
   promoted or duplicated.

`NodeOutcome.status` is always one of `succeeded` / `needs_repair` / `blocked`
(all valid outcome states; never an administrative status).

## Approved decisions

- **A** — `memory_updates` mirrors LM1F's *shape* but is computed locally; only
  the table is shared (no import of LM1F private helpers).
- **B** — blocked-missing/unrecognized/copy-failed set `evidence.error` (+
  `message`) so a blocked verdict is self-explaining.
- **C** — `node_summary` is a minimal verifier-local string; the LM1F summary
  table is not duplicated.

## Testing (TDD)

1. `usable` → `succeeded`, `verified=True`, receipt carried, `component_guid` +
   `repair_anchor` in `memory_updates.facts`.
2. `created_with_errors` → `needs_repair`, `verified=False`; `written_with_errors`
   → `needs_repair` (the legitimate `needs_repair` entry point — no pre-seeding).
3. `verification_pending` → `blocked`, non-error message, `error is None`,
   `verified is None`; `unknown` → `blocked` likewise.
4. `evidence=None` → `blocked`, `error` mentions missing, no `facts`.
5. `receipt=None` and non-dict receipt and receipt-without-`artifact_status` →
   `blocked`, missing error, no `facts`.
6. Unrecognized `artifact_status="future_status"` → `blocked`, error mentions
   *unrecognized* (distinct message from the missing case), no `facts`.
7. **Deep-copy failure:** a receipt whose deepcopy raises → `blocked`,
   `error == "verifier: evidence copy failed"`, no `facts`, no raise.
8. **`verified` preservation on blocked:** blocked input evidence with
   `verified=True` → outcome `verified=True` (carried); with `verified=None` →
   `None`.
9. **Deep-copy isolation:** mutating the input `evidence.receipt` /
   `repair_anchor` after the call does not change the returned outcome's evidence
   or `memory_updates`.
10. **Single-source parity:** for every `(status, expected)` in
    `ARTIFACT_STATUS_TO_OUTCOME`, evidence with that `artifact_status` yields
    `outcome.status == expected` — proving LM3D rides the shared table, not a
    private copy.
11. **LM1F regression:** existing `test_plan_graph_outcomes.py` stays green after
    the constant rename.
12. **Purity:** AST allowlist (`rook` imports ⊆ {`rook.learning.plan_graph`,
    `rook.learning.plan_graph_outcomes`}); subprocess probe (importing
    `plan_graph_verifiers` loads no `tool_dispatcher` / `dspy` / `litellm`).

## Out of scope (LM3D)

- Walker integration / driving verifier nodes / reviving the 5-node template → later slice.
- `needs_escalation` and any retry/attempt-policy input.
- Non-script-receipt verifiers; `GraphMemory` input; raw tool results (LM1F's job).

## File touch list

- Add: `mcp_server/src/rook/learning/plan_graph_verifiers.py` —
  `script_receipt_verifier_outcome` + small private helpers.
- Modify: `mcp_server/src/rook/learning/plan_graph_outcomes.py` — promote the
  mapping constant to public `ARTIFACT_STATUS_TO_OUTCOME`; update the internal use.
- Add: `mcp_server/tests/test_plan_graph_verifiers.py` — LM3D tests.
