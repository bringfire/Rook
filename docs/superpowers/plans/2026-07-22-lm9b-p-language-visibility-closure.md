# Plan — LM9B-P Language-Visibility Closure (small TDD, revised)

**Spec:** `docs/superpowers/specs/2026-07-22-lm9b-p-language-visibility-closure-design.md`.
**Base:** `335bdadc` on `codex/lm9b-p-language-visibility-closure`. **No model call anywhere.**
**Runner:** `C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe -m pytest` from the worktree root.
Each task red→green. Reviewer approved coding after the round-3 corrections; return the completed diff + verification before merge.

## Task 0 — Dependency map (no code change)
Enumerate every fixture/manifest that pins the two edited fixtures: `contract_fingerprint`, schema fingerprint, `manifest.json`, `payload_schema_registry`, attempt-context/`authority_manifest_fingerprint`, and any identity/readiness fingerprint ingesting them. List the exact recompute set for Task 6 in the PR description.

## Task 1 — M2 descriptor kind + kind/schema pairing
- **Red:** `mcp_server/tests/test_lm9b_p_language_visibility_ledger.py` asserts, in the schema fixture: `source_task` contextually binds `artifact_kind:"task_envelope"` **and** `schema:"rook.planner_task_envelope:v1"`; `authority_artifacts.items` is a `oneOf` of `{environment_snapshot ↔ rook.environment_snapshot:v1}` | `{planning_policy ↔ rook.planning_policy:v1}`; and the `language_boundary` mirror keys exist. Plus a schema-validation test that a **mismatched** kind/schema pair fails.
- **Green:** edit `scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json` + `planner_authoring_contract.json`.

## Task 2 — M1 reserved identity + placement (uniqueness split)
- **Red:** ledger asserts schema `source_task.artifact_id.const == "task_envelope"` and `authority_artifacts.items.artifact_id` has `not:{const:"task_envelope"}`; **assert `uniqueItems` is *not* used** for id-uniqueness. Assert `language_boundary`/`relational_invariants` declaratively state global + namespace descriptor-id uniqueness.
- **Green:** edit fixtures.
- *(cross-object uniqueness itself stays gate-enforced; proven unchanged in Task 7.)*

## Task 3 — M3 shared identifier `$def` coverage
- **Red:** ledger builds the applicable-field set from the schema and asserts a single `$def` (`machine_identifier`, `pattern ^[a-z0-9]+(?:[._:-][a-z0-9]+)*$`) is `$ref`d by **every** `*_id`, `*_ids` item, `affects` item, and `semantic_key`; documents scalars already more-strictly bound.
- **Green:** refactor schema to the shared `$def`.

## Task 4 — M4 policy-pointer grammar
- **Red:** ledger asserts `pattern ^/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*$` on the policy-reference `json_pointer`.
- **Green:** edit schema.

## Task 5 — M5/M6 relational invariants (declarative)
- **Red:** ledger asserts `relational_invariants` contains a descriptor-use statement (M5) and a local-reference-resolution statement (M6).
- **Green:** append the two statements. *(Gate enforcement of both is proven unchanged in Task 7.)*

## Task 6 — Fingerprint / manifest consistency
- **Red:** consistency test recomputes each dependent fingerprint/manifest from the edited fixture bytes and asserts equality with the stored value.
- **Green:** recompute + update the Task-0 dependents (deterministic; no semantic change).

## Task 7 — Visibility-through-renderer + split boundary + full suite
- **Model-visibility (renderer):** assert the changed schema + authoring-contract reach the model — their bytes/fingerprints appear in `render_planner_request(inputs).raw_bytes` and/or the frozen input manifest (`authority_manifest_fingerprint`). *(Fixture-on-disk assertions alone are insufficient.)*
- **Schema-rejection boundary** (locus = `recipe_schema_failed`): wrong descriptor kind; wrong kind/schema pair; reserved `task_envelope` id in `authority_artifacts`; malformed identifier; malformed policy pointer.
- **Unchanged-gate-rejection boundary** — for each of {duplicate descriptor IDs, unreferenced descriptor, dangling local reference}, prove **both**: (1) the authoring contract visibly states the rule, and (2) the **unchanged** gate still rejects it (drive `evaluate_mechanical_gate`/`_structural_integrity_issue` with a crafted recipe and assert the original diagnostic code).
- **Positive:** corrected synthetic descriptor set (bare tokens, unique ids, reserved source_task, matching kind/schema — not R01-derived) passes schema validation.
- Run the **full LM9B-P suite** + `py_compile` + `git diff` review. Must be green.

## Stop
Return spec + plan + **completed diff + verification** for review. **Do not** merge, rerun the experiment, or call any model without fresh, explicit, separate authorization. Causal-feedback is a distinct future slice, not started here.
