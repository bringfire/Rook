# LM9B-P — Evaluator Authority Boundary + Report Visibility (design amendment)

**Status:** spec for review — no code yet.
**Base:** `origin/main` `15df78ee`. **Branch:** `codex/lm9b-p-evaluator-authority-boundary`.
**Evidence basis:** the sealed visibility-intervention run (`probe_inconclusive`, preserved `AC7716B7…`): Planner reached `mechanically_accepted` in 4 turns; the evaluator emitted a rubric-shaped report with `faithful_ready` and the hidden parser rejected it as `malformed`. Reviewer's read-only inspection + independent code verification established **two** defects, not one.

## Governing invariant (the authority ledger)

> **Models propose and judge meaning; deterministic authority decides whether the system may advance.**

`faithful_ready` conflates two authorities: *faithful* (a semantic judgment, the evaluator model's to make) and *ready* (a deterministic system state derivable from the recipe's explicit `unresolved_intent` and other blockers). The current controller (`derive_checkpoint_classification`, artifacts.py:1223–1243) lets the model's recommendation alone authorize `probe_candidate_ready` → compiler entry, with **no deterministic consultation of recipe state**. The sealed recipe makes the hazard concrete: 5 explicit unresolved material values, evaluator said `faithful_ready` — merely fixing serialization would have admitted a deterministically-blocked recipe into the compiler.

**Authority ledger for this slice (the 5 questions):**

| Fact established | Authorized actor | Evidence | Controller recompute? | Downstream action authorized |
|---|---|---|---|---|
| structural admissibility | mechanical gate (deterministic) | recipe bytes vs schema/gate | yes (already) | evaluation may proceed |
| semantic fidelity | evaluator **model** | brief + authority + rubric + recipe | no — model judgment, recorded with evidence | contributes to classification, never alone advances |
| blocked vs unblocked | **deterministic blocker projection** (new, controller-side) | the recipe's own `unresolved_intent` state | yes — pure function of recipe bytes | ready/blocked classification |
| checkpoint classification | controller (deterministic) | combines the three above | yes | compiler entry only if admissible + faithful + unblocked |

## Two closures (both required; neither alone is sufficient)

### Closure 1 — report serialization visibility
The evaluator tool exposes only `{evaluation_json: string}` (support.py L77–86) while the hidden parser requires the inner report schema (`_PLANNER_EVALUATION_REPORT_SCHEMA`, L90–109). Same defect class as the descriptor language. Fix: render the **exact closed report schema into the evaluator request**, derived from the parser's **single source of truth** (the same constant object — no hand-copied duplicate).

### Closure 2 — recommendation semantics / authority boundary
Restrict the evaluator to **semantic fidelity findings only** and make readiness a deterministic derivation:

- Evaluator recommendation vocabulary becomes semantic-only:
  - `semantically_faithful` — the recipe faithfully represents the brief under the authority context (regardless of blockers);
  - `semantically_unfaithful` — unauthorized, contradictory, invented, or unfaithful content;
  - `evaluation_inconclusive` — the evaluator cannot establish either.
- **Deterministic explicit-blocker projection, bound to the accepted artifact.** New pure function `derive_probe_explicit_blockers(final_recipe_bytes)`:
  - **Input binding:** classification consumes the independent post-session `checkpoint_gate` — the `MechanicalGateResult` recomputed from the final recipe under the frozen checkpoint inputs — validated for **every** accepted session before any evaluator branch. It must exactly match the accepted turn's retained gate result and bind the same final bytes as `planner_session.final_recipe_bytes`; unresolved intent is derived **only** from `checkpoint_gate.final_recipe_bytes`. **Any mismatch (bytes or gate identity) is an integrity/control failure, never a classification.** The session-loop turn result alone is never authoritative — it does not prove acceptance under the archived frozen inputs.
  - **Closed output:** the only blocker this probe can deterministically establish is `unresolved_intent_present`. The function's output vocabulary is closed to exactly that. This slice does **not** and cannot establish that policy, capability, selection, or authorization blockers are absent — that requires LM9A-S. Accordingly, `probe_candidate_ready` retains its existing meaning: **eligibility for the inert compiler experiment only, not product compile readiness.**
- **Controller equations** (deterministic, replace the direct recommendation map):
  ```text
  mechanically admissible + semantically_faithful   + unresolved_intent_present -> probe_candidate_blocked
  mechanically admissible + semantically_faithful   + no explicit blocker       -> probe_candidate_ready
  mechanically admissible + semantically_unfaithful                             -> probe_planner_failure
  mechanically admissible + evaluation_inconclusive                             -> probe_inconclusive
  ```
- **Override impossibility:** no semantic recommendation can override explicit recipe state. A faithful recipe with nonempty `unresolved_intent` can never classify `probe_candidate_ready`. The architectural guarantee for a blocked classification is: **no handoff, no compiler provider call, no compiler attempt evidence, checkpoint 2 = `not_evaluated`** — proven by test. (Compiler adapter *construction* in the transmit path is not forced lazy; construction has no demonstrated external side effect.)

**Declared contract change (honest):** this replaces the evaluator recommendation enum (`faithful_ready|faithful_blocked|planner_failure` → the semantic-only triple). It is an intentional authority-boundary correction directed by the reviewer, superseding the earlier "keep the recommendation vocabulary" instruction. The `recommendation + evidence[{criterion_id, finding}]` report **shape** is retained; the rubric criteria, evaluator model, temperature, retry policy (one attempt), and semantic scoring approach are unchanged. We do **not** accept the model's earlier richer report shape merely because it was emitted.

## In scope

1. Single source of truth: one module-level report-schema object; the evaluator request renders it verbatim; the parser validates against the same object.
2. Semantic-only recommendation enum + explicit meaning strings rendered with the schema (so the evaluator is told what each verdict means, including that readiness is **not** its decision).
3. `derive_probe_explicit_blockers` + amended controller contract (consumes the accepted turn's `MechanicalGateResult`; byte-equality integrity check; equations above) in/beside `derive_checkpoint_classification`.
4. Vertical fake-provider test: the **rendered** evaluator-request schema equals the **accepted** parser schema (object identity/equality, not token match).
5. Consistency tests:
   - faithful + nonempty `unresolved_intent` → `probe_candidate_blocked`; and the blocked path shows **no handoff, no compiler provider call, no compiler attempt evidence, checkpoint 2 `not_evaluated`**;
   - faithful + empty `unresolved_intent` → `probe_candidate_ready` (eligibility for the inert experiment only);
   - unfaithful → `probe_planner_failure`; inconclusive → `probe_inconclusive`;
   - a synthetic evaluator emitting a legacy/inconsistent recommendation is rejected (`malformed` or explicit invalid-recommendation), never classified ready;
   - gate-bytes vs session-bytes mismatch → integrity/control failure, never a classification.
6. Doc note in the LM9B-P design doc recording the authority split and equations.

## Out of scope

Full LM9A-S; a general blocker framework; policy evaluation; capability authorization; receipt handling; forced-lazy compiler adapter construction; rubric criteria changes; evaluator/compiler model, temperature, token budget, retry-policy changes; Planner-side anything; compiler-side anything; accepting the richer emitted report shape; **any model call**. The evaluator-only continuation on the sealed recipe bytes is a separate, later, explicitly-authorized run. Its **falsifiable prediction** (a forecast, not a required success): *if the evaluator judges the sealed recipe semantically faithful, the deterministic unresolved-intent projection must classify it `probe_candidate_blocked`.* The continuation may instead validly yield `semantically_unfaithful` or `evaluation_inconclusive`. The sealed visibility run remains permanently `probe_inconclusive`.

## Where changes land

`scripts/lm9b_p_planner_recipe_transfer_support.py` (report schema single-source + rendered exposure + semantic enum), `scripts/lm9b_p_planner_recipe_transfer_probe.py` / `..._artifacts.py` (blocker projection + controller equations + evaluator request rendering), tests under `mcp_server/tests/`. Fixture changes only if the evaluator request template lives in fixtures (verify in plan Task 0).

## Testing (deterministic, no model)

As enumerated in-scope items 4–5, plus: full LM9B-P suite green; existing tests that pinned the old enum updated to the new authority-split expectations (each update annotated with the contract-change rationale); `py_compile`; clean diff.
