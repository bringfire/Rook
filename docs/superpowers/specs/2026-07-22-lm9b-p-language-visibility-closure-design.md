# LM9B-P — Workerless Language-Visibility Closure (design amendment)

**Status:** spec (revised for reviewer round 3) — reviewer approved proceeding to TDD after these corrections; no further review gate before code.
**Base:** `origin/main` `335bdadc`. **Branch:** `codex/lm9b-p-language-visibility-closure`.
**Evidence basis:** the comparative diagnostic + complete closure audit in `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-COMPARISON-NOTE.md` (§9, ledger M1–M6). Compact amendment, not a new architecture cycle.

## Objective

**Every reviewed recipe-language rule in M1–M6 has an exact model-visible carrier** (recipe schema, authoring-contract `language_boundary`/`relational_invariants`, a vocabulary fixture, or an already-available runtime hook). This is deliberately narrower than "every rule the gate enforces": the audit leaves strict-JSON serialization and the `MAX_RECIPE_BYTES` cap explicitly outside this slice.

## One experimental variable

**Model-visible contract completeness.** Nothing else changes, so a later (separately authorized) rerun cleanly tests the single hypothesis: *does declaring the existing language suffice for the Planner to author an admissible recipe?* If site-by-site repair still fails with the language fully visible, feedback or typed incremental construction becomes the next, independently-testable intervention.

## Honest statement of effect on acceptance (pin)

Not literally "no acceptance change." Three labeled kinds:

| Change | Kind | Effect |
|---|---|---|
| M2 `artifact_kind` closed vocab; M3 identifier grammar; M4 policy-pointer grammar; M1 reserved `source_task.artifact_id` | **existing gate rule made visible** | Ultimately-accepted set unchanged; non-conforming recipes rejected **earlier and more legibly** (`recipe_schema_failed`) instead of deep in `_structural_integrity_issue`. |
| M1 `task_envelope` reserved to `source_task` (forbidden as an `authority_artifacts` id); descriptor **kind/`schema` pairing** | **normative rule newly aligned with enforcement** | The gate currently admits a `task_envelope` authority descriptor (support L756) and never checks descriptor `schema` against its kind. Declaring `authority_artifacts.items.artifact_id != "task_envelope"` and a kind↔schema `oneOf` **will reject** recipes the old gate could have accepted. Justified alignment with LM9A; stated plainly, not hidden under "visibility." |
| Fingerprint assistance | **runtime feedback carrier already available** | On `recipe_fingerprint_mismatch` the gate returns `fingerprint_resubmission_required` with the **exact ratified fingerprint** (support L1014–1022). No new carrier needed. |

No **gate semantics** for cross-object uniqueness / referential integrity change: those stay in `_structural_integrity_issue` unchanged (see M1/M5/M6 below). Prompt, feedback text, model, budget: unchanged.

## In scope — carriers for M1–M6

- **M2 — descriptor kind *and* kind/schema pairing (contextual).** In `planner_recipe_probe_schema.json`:
  - `source_task` → contextual `oneOf`/`allOf` binding `artifact_kind:"task_envelope"` **with** `schema:"rook.planner_task_envelope:v1"`;
  - `authority_artifacts.items` → contextual `oneOf`: `{artifact_kind:"environment_snapshot", schema:"rook.environment_snapshot:v1"}` | `{artifact_kind:"planning_policy", schema:"rook.planning_policy:v1"}`.
  - Mirror declaratively in `planner_authoring_contract.json.language_boundary` (`source_task_artifact_kind`, `authority_artifact_kinds`, and the kind→schema map), in the existing `worker_slots_max_entries` / `confirmation_receipts_admitted` style.
- **M1 — reserved identity & placement; uniqueness split by expressibility.**
  - *Schema-expressible:* `source_task.artifact_id` → `const:"task_envelope"`; `authority_artifacts.items.artifact_id` → `not:{const:"task_envelope"}` (reserved id cannot appear in the authority collection). **No `uniqueItems`** — it compares whole objects, not `artifact_id`, so it neither expresses id-uniqueness nor helps here.
  - *Not schema-expressible → authoring-contract declarative + unchanged gate:* global descriptor-id uniqueness across `source_task`+`authority_artifacts` and namespace-scoped id uniqueness are stated in `language_boundary`/`relational_invariants`; the gate continues to enforce them (`duplicate_identifier`, unchanged).
- **M3 — complete machine-identifier field coverage.** One shared schema `$def` applying `^[a-z0-9]+(?:[._:-][a-z0-9]+)*$` to **every** field the gate applies it to — all `*_id`, all `*_ids` items, `affects` items, `semantic_key`, and any `_MACHINE_SCALAR_FIELDS` scalar not already more-strictly bound (documenting where a stricter `const`/`enum`/registry carrier already exists).
- **M4 — policy-pointer grammar.** Schema `pattern` `^/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*$` on the policy-reference `json_pointer`.
- **M5/M6 — descriptor-use + local-reference invariants (declarative only; gate unchanged).** `relational_invariants` gains: "every recipe-bound authority descriptor is referenced" (M5, `unreferenced_authority_descriptor`) and "every local reference resolves to a declared symbol of its declared kind" (M6, `dangling_local_reference`). The gate continues to enforce both.
- **Required fixture/contract fingerprints and manifests.** Recompute and update every fingerprint/manifest that pins the changed fixtures (`contract_fingerprint`, schema fingerprint, `manifest.json`, `payload_schema_registry`, attempt-context/authority manifest), so frozen-input and identity checks stay internally consistent. Exact dependents enumerated in plan Task 0.
- **Model-visibility-through-renderer test.** At least one assertion that the changed schema + authoring-contract reach the model — their bytes/fingerprints appear in `render_planner_request(inputs).raw_bytes` and/or the frozen pretransmission input manifest (`authority_manifest_fingerprint`) — not merely that the fixture file changed on disk.

## Out of scope

Feedback changes (causal-feedback correction is a **deferred, independent** slice so it does not co-vary with visibility); prompt/persona changes; model or budget changes; typed construction tools; new examples (no R01-derived content); semantic-policy expansion; strict-JSON/byte-cap carriers; **any model call**.

## Where changes land (as implemented)

- Source fixtures: `scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json` (M1–M4 carriers), `planner_authoring_contract.json` (language_boundary mirror + relational_invariants, recomputed `contract_fingerprint`), `planner_evaluation_rubric.json` (propagated `authoring_contract_binding.contract_fingerprint` + recomputed `rubric_fingerprint`).
- **Frozen-input verifier:** `scripts/lm9b_p_planner_recipe_transfer_artifacts.py :: _verify_authoring_contract` — its hardcoded `expected_boundary` is an equality check against the contract's `language_boundary`, so the six new keys are mirrored there in lockstep. This is **frozen-input verification, not gate acceptance semantics** (it asserts the model-visible contract matches the reviewed shape; it does not change which recipes are accepted).
- **No change to the gate validator** `scripts/lm9b_p_planner_recipe_transfer_support.py`: its grammar, `_MACHINE_SCALAR_FIELDS`, uniqueness/referential checks, and acceptance predicate are untouched.

**Implementation note (nullability):** the identifier grammar is applied only where a field is a plain `string`; null-pinned ids (`worker_slot_id` in the workerless profile, schema `{"type":"null"}`) are left as-is — matching the gate, which skips null values for the grammar (`support.py` L505). The dependency map (plan Task 0) resolved to: the schema document carries no stored fingerprint (runtime manifest recomputes from bytes); only the contract→rubric fingerprint chain needed recomputation.

## Testing (deterministic, no model)

- **Carrier-ledger tests (pin, not proof):** one per M1–M6 asserting the exact schema/contract representation, and failing on drift. Not a claim that all future gate rules have carriers.
- **Model-visibility-through-renderer:** assert the changed carriers appear in the rendered planner request / frozen input manifest.
- **Schema-rejection boundary (failure moves to `recipe_schema_failed`):** wrong descriptor kind; wrong kind/schema pair; reserved `task_envelope` id in `authority_artifacts`; malformed identifier; malformed policy pointer.
- **Unchanged-gate-rejection boundary:** duplicate descriptor IDs, unreferenced descriptor, dangling local reference — for each, prove **both** (1) the authoring contract visibly states the rule and (2) the **unchanged** mechanical gate still rejects it.
- **Positive:** a corrected synthetic descriptor set (bare tokens, unique ids, reserved source_task, matching kind/schema — **not** R01-derived) passes schema validation.
- **Consistency:** recomputed fingerprints/manifests match; existing LM9B-P suite stays green.

## Explicitly deferred (own later, independently-testable decisions)

Causal-feedback correction; prompt/turn-budget revisiting; typed construction tools / larger authoring-hook substrate. Each needs its own authorization; **no rerun or model call** until this slice is reviewed-diff'd and merged and a new experiment is separately authorized.
