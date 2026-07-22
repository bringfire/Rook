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

## Task 3 — Deterministic blocker projection (Closure 2b)
- **Red:** pure-function tests: nonempty `unresolved_intent` → blocked (with blocker source listed); empty → unblocked; function consumes recipe mapping only (no evaluator input).
- **Green:** implement `derive_recipe_blockers(recipe)` (name per existing conventions) beside the controller.

## Task 4 — Controller equations (Closure 2c)
- **Red:** `derive_checkpoint_classification` matrix tests:
  faithful+blocked→`probe_candidate_blocked`; faithful+unblocked→`probe_candidate_ready`; unfaithful→`probe_planner_failure`; inconclusive→`probe_inconclusive`; malformed/absent evaluator→`probe_inconclusive` (unchanged); mechanical rejection unchanged.
- **Green:** controller combines gate result + semantic verdict + blocker projection; recommendation can no longer directly select ready/blocked.

## Task 5 — Override-impossibility + compiler-isolation proofs
- **Red/Green:** vertical fake-provider tests through the real session path:
  1. faithful verdict + recipe with nonempty `unresolved_intent` → aggregate `probe_candidate_blocked`, checkpoint-2 `not_evaluated`, and **no compiler provider is ever constructed** (fake compiler factory raises if called);
  2. synthetic evaluator emitting any legacy/ready-style recommendation → never classifies ready, never touches compiler;
  3. faithful + empty unresolved intent (synthetic recipe) → `probe_candidate_ready` (compiler entry permitted — not exercised).

## Task 6 — Sweep + full suite
Update every test pinning the old enum (annotate each with the contract-change rationale); design-doc note recording the authority split; run full LM9B-P suite + `py_compile` + `git diff --check`. Must be green. Stop for review.

## Stop conditions
No merge, no model call, no evaluator-only continuation without fresh explicit separate authorization. Expected continuation outcome for the sealed recipe under the corrected boundary: **`probe_candidate_blocked`** (faithful + 5 blockers), not compiler entry. Sealed visibility run stays `probe_inconclusive` forever.
