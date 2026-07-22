# Plan — LM9B-P Language-Visibility Closure (small TDD)

**Spec:** `docs/superpowers/specs/2026-07-22-lm9b-p-language-visibility-closure-design.md`.
**Base:** `335bdadc` on `codex/lm9b-p-language-visibility-closure`. **No model call anywhere in this plan.**
**Runner:** `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest` from the worktree root.
Each task is red→green; stop for review after Task 7.

## Task 0 — Dependency map (no code change)
Enumerate every fixture/manifest that pins the two fixtures we will edit: `contract_fingerprint`, any schema fingerprint, `manifest.json`, `payload_schema_registry`, `attempt_context`, and any identity/readiness fingerprint that ingests them. Output: a short list in the PR description of exactly which fingerprints must be recomputed in Task 6. (Prevents a silent frozen-input mismatch.)

## Task 1 — Carrier-ledger test scaffold + M2 (descriptor kind)
- **Red:** new `mcp_server/tests/test_lm9b_p_language_visibility_ledger.py` asserting `source_task.artifact_kind.const == "task_envelope"` and `authority_artifacts.items.artifact_kind.enum == ["environment_snapshot","planning_policy"]` in the schema fixture, and the matching `language_boundary` mirror keys.
- **Green:** edit `scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json` + `planner_authoring_contract.json`.

## Task 2 — M1 reserved identity + placement
- **Red:** ledger asserts schema `source_task.artifact_id.const == "task_envelope"`; per-array `uniqueItems` where expressible; and declarative `language_boundary`/`relational_invariants` statements for cross-collection descriptor-id uniqueness and `task_envelope` single-occurrence / forbidden-reuse.
- **Green:** edit fixtures.

## Task 3 — M3 shared identifier `$def` coverage
- **Red:** ledger asserts a single `$def` (e.g. `machine_identifier`) with `pattern ^[a-z0-9]+(?:[._:-][a-z0-9]+)*$`, and that **every** applicable field (`*_id`, `*_ids` items, `affects` items, `semantic_key`, plus scalar members not already more-strictly bound) `$ref`s it. Test builds the applicable-field set from the schema and asserts coverage.
- **Green:** refactor schema to reference the shared `$def`.

## Task 4 — M4 policy-pointer grammar
- **Red:** ledger asserts `pattern ^/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*$` on the policy-reference `json_pointer`.
- **Green:** edit schema.

## Task 5 — M5/M6 relational invariants
- **Red:** ledger asserts `relational_invariants` contains a "every recipe-bound authority descriptor is referenced" statement and a "local reference resolves to a declared symbol of its declared kind" statement.
- **Green:** append the two statements.

## Task 6 — Fingerprint / manifest consistency
- **Red:** consistency test recomputes each dependent fingerprint/manifest from the edited fixture bytes and asserts it equals the stored value.
- **Green:** recompute and update the dependents listed in Task 0 (deterministic; no semantic change).

## Task 7 — Behavior boundary tests + full suite
- **Red/Green:** validation tests over `planner_recipe_probe_schema.json` (Draft2020-12): a corrected synthetic descriptor set (bare tokens, unique ids, reserved source_task — **not** R01-derived) **passes**; and each of {qualified-schema-id `artifact_kind`, duplicate descriptor id, `task_envelope` in `authority_artifacts`, malformed identifier, policy pointer outside `/rules/`} **fails schema validation** with a legible message. Confirm the failure locus moved to `recipe_schema_failed`.
- Run the **full LM9B-P suite** + `py_compile` + `git diff` review. Must be green.

## Stop
Return spec + plan + diff for review. **Do not** merge, rerun the experiment, or call any model without fresh, explicit, separate authorization. The causal-feedback slice is a distinct future step and is not started here.
