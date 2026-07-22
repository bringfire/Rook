# Plan — LM9B-P Evaluator Authority Boundary (small TDD)

**Spec:** `docs/superpowers/specs/2026-07-22-lm9b-p-evaluator-authority-boundary-design.md`.
**Base:** `15df78ee` on `codex/lm9b-p-evaluator-authority-boundary`. **No model call anywhere.**
**Runner:** `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest` from the worktree root.
Each task red→green; stop after Task 6 with completed diff + verification for review.

## Task 0 — Survey (no code change)
Map exactly where the evaluator request is rendered (support/artifacts/fixtures), every test pinning `faithful_ready|faithful_blocked|planner_failure`, and every consumer of `derive_checkpoint_classification`. List in PR description.

## Task 1 — Single source of truth + rendered report schema (Closure 1)
- **Red:** test asserting the rendered evaluator request embeds the exact report schema object the parser validates with (deep equality against `_PLANNER_EVALUATION_REPORT_SCHEMA`'s successor), plus the recommendation-meaning strings.
- **Green:** hoist one module-level `PLANNER_EVALUATION_REPORT_SCHEMA`; render it (and meanings) into the evaluator request; parser validates against the same object.

## Task 2 — Semantic-only recommendation enum (Closure 2a)
- **Red:** tests: parser accepts `semantically_faithful|semantically_unfaithful|evaluation_inconclusive`; rejects the legacy `faithful_ready|faithful_blocked|planner_failure` and any other value as malformed/invalid.
- **Green:** replace `_PLANNER_EVALUATION_RECOMMENDATIONS`; update meaning strings ("readiness is derived by the system from recipe state; do not judge it").

## Task 3 — `derive_probe_explicit_blockers` (Closure 2b)
- **Red:** pure-function tests: input is `final_recipe_bytes` (strict-parsed); nonempty `unresolved_intent` → output exactly `("unresolved_intent_present",)`; empty → `()`; output vocabulary closed — no other blocker kind exists or is representable; no evaluator input.
- **Green:** implement `derive_probe_explicit_blockers(final_recipe_bytes)` beside the controller. Docstring states the authority limit: this probe establishes only `unresolved_intent_present`; absence of policy/capability/selection/authorization blockers is NOT established (needs LM9A-S); `probe_candidate_ready` = eligibility for the inert compiler experiment only.

## Task 4 — Controller contract + equations (Closure 2c)
- **Red:** amended `derive_checkpoint_classification` tests:
  - contract consumes the independent post-session `checkpoint_gate` (recomputed from the final recipe under the frozen checkpoint inputs), a **required** keyword validated before any evaluator branch; blockers derived ONLY from `checkpoint_gate.final_recipe_bytes`;
  - **integrity checks:** `checkpoint_gate.final_recipe_bytes != planner_session.final_recipe_bytes`, or `checkpoint_gate` ≠ the accepted turn's retained gate result, or a missing/non-accepted gate on an accepted session → integrity/control failure (raise), never a classification;
  - matrix: faithful+`unresolved_intent_present`→`probe_candidate_blocked`; faithful+no-explicit-blocker→`probe_candidate_ready`; unfaithful→`probe_planner_failure`; inconclusive→`probe_inconclusive`; malformed/absent evaluator→`probe_inconclusive` (unchanged); mechanical rejection unchanged.
- **Green:** controller combines gate result + semantic verdict + explicit-blocker projection; recommendation can no longer directly select ready/blocked.

## Task 5 — Override-impossibility + compiler-isolation proofs
- **Red/Green:** vertical fake-provider tests through the real session/joined path:
  1. faithful verdict + recipe with nonempty `unresolved_intent` → aggregate `probe_candidate_blocked` with the architectural guarantee: **no handoff, no compiler provider CALL (fake compiler provider callable raises if invoked), no compiler attempt evidence in the archive, checkpoint-2 `not_evaluated`**. (Adapter construction is not forced lazy — construction has no demonstrated external side effect.)
  2. synthetic evaluator emitting any legacy/ready-style recommendation → rejected as malformed/invalid, never classifies ready, same compiler-isolation guarantee;
  3. faithful + empty unresolved intent (synthetic recipe) → `probe_candidate_ready` (eligibility only — compiler not exercised).

## Task 6 — Sweep + full suite
Update every test pinning the old enum (annotate each with the contract-change rationale); design-doc note recording the authority split; run full LM9B-P suite + `py_compile` + `git diff --check`. Must be green. Stop for review.

## Stop conditions
No merge, no model call, no evaluator-only continuation without fresh explicit separate authorization. **Falsifiable prediction for the continuation (a forecast, not a required success):** *if the evaluator judges the sealed recipe semantically faithful, the deterministic unresolved-intent projection must classify it `probe_candidate_blocked`.* The continuation may instead validly yield `semantically_unfaithful` or `evaluation_inconclusive`. No compiler entry for this recipe in any outcome. Sealed visibility run stays `probe_inconclusive` forever.
