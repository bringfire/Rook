# LM9B-P — Workerless Language-Visibility Closure (design amendment)

**Status:** spec for review — no code yet.
**Base:** `origin/main` `335bdadc`. **Branch:** `codex/lm9b-p-language-visibility-closure`.
**Evidence basis:** the comparative diagnostic + complete closure audit in `C:/Users/bring/rook-lm9b-p-attempts/2026-07-22-COMPARISON-NOTE.md` (§9, ledger M1–M6). This is a compact amendment, not a new architecture cycle.

## Objective

Make the existing workerless accepted language **visible and internally consistent** to the Planner, so that every rule the mechanical gate enforces has a model-visible carrier (recipe schema, authoring-contract `language_boundary`/`relational_invariants`, a vocabulary fixture, or an already-available runtime hook).

## One experimental variable

**Model-visible contract completeness.** Nothing else changes, so a later (separately authorized) rerun cleanly tests the single hypothesis: *does declaring the existing language suffice for the Planner to author an admissible recipe?* If site-by-site repair still fails with the language fully visible, feedback or typed incremental construction becomes the next, independently-testable intervention.

## Honest statement of effect on acceptance (pin 1)

This slice is **not** literally "no acceptance change." Three distinct kinds of change, labeled:

| Change | Kind | Effect |
|---|---|---|
| M2 `artifact_kind` closed vocab; M3 identifier grammar; M4 policy-pointer grammar; M1(a–c) reserved id + uniqueness | **existing gate rule made visible** | The *ultimately-accepted set is unchanged*; non-conforming recipes are rejected **earlier and more legibly** (at `recipe_schema_failed`/declared contract) instead of deep in `_structural_integrity_issue`. |
| M1(d) `task_envelope` forbidden in `authority_artifacts` | **normative rule newly aligned with enforcement** | Currently the gate admits a `task_envelope` authority descriptor (support L756); LM9A forbids it. Declaring `authority_artifacts.artifact_kind ∈ {environment_snapshot, planning_policy}` **will reject** a recipe the old gate could have accepted. This is justified architectural alignment with LM9A, and must be stated plainly, not hidden under "visibility." |
| Fingerprint assistance | **runtime feedback carrier already available** | On `recipe_fingerprint_mismatch` the gate returns `fingerprint_resubmission_required` with the **exact ratified fingerprint** (support L1014–1022). The model does not compute SHA-256 unaided; the audit records this as already-present, so no new "teach the hash" carrier is needed. |

No **gate semantics** (acceptance predicate for a conforming recipe), prompt, feedback text, model, or budget changes. The only acceptance-set delta is the single M1(d) normative alignment above.

## In scope

- **Carriers for M1–M6** placed at their designated model-visible homes:
  - **M2 — descriptor kind/schema, contextual:** `planner_recipe_probe_schema.json` — `source_task.artifact_kind` → `const:"task_envelope"`; `authority_artifacts.items.artifact_kind` → `enum:["environment_snapshot","planning_policy"]`; keep each bare kind's `schema` pairing consistent with the normative contract. Mirror declaratively in `planner_authoring_contract.json.language_boundary` (`source_task_artifact_kind`, `authority_artifact_kinds`), matching the existing `worker_slots_max_entries` / `confirmation_receipts_admitted` style.
  - **M1 — reserved source-task identity & placement / uniqueness:** schema `source_task.artifact_id` → `const:"task_envelope"`; express per-array `uniqueItems` where JSON Schema can; add declarative statements in `language_boundary`/`relational_invariants` for the **cross-collection** descriptor-id uniqueness and the single-occurrence / forbidden-reuse rules JSON Schema cannot express.
  - **M3 — complete machine-identifier field coverage:** one shared schema `$def` applying `^[a-z0-9]+(?:[._:-][a-z0-9]+)*$` to **every** field the gate applies it to — all `*_id`, all `*_ids` items, `affects` items, `semantic_key`, and any scalar member of `_MACHINE_SCALAR_FIELDS` not already more-strictly bound (documenting where a stricter `const`/`enum`/registry carrier already exists).
  - **M4 — policy-pointer grammar:** schema `pattern` `^/rules/[a-z0-9]+(?:[._:-][a-z0-9]+)*$` on the policy-reference `json_pointer`.
  - **M5/M6 — descriptor-use + local-reference invariants:** declarative statements in `relational_invariants` ("every recipe-bound authority descriptor is referenced"; "every local reference resolves to a declared symbol of its declared kind").
- **Required fixture/contract fingerprints and manifests:** recompute and update every fingerprint/manifest that pins the changed fixtures (e.g. `contract_fingerprint`, schema fingerprint, `manifest.json`, `payload_schema_registry`), so the frozen-input and identity checks remain internally consistent. Enumerate the exact dependents during planning.
- **Deterministic positive and boundary tests** (see Testing).

## Out of scope

Feedback changes; prompt/persona changes; model or budget changes; typed construction tools; new examples (no R01-derived content); semantic-policy expansion; **any model call**. The causal-feedback improvement (naming the descriptor + allowed set) is deferred to a *separate* slice so it does not co-vary with visibility.

## Where changes land

Source fixtures only: `scripts/lm9b_p_fixtures/planner_recipe_probe_schema.json` and `.../planner_authoring_contract.json` (+ dependent fingerprint/manifest fixtures). **No change to the gate validator** `scripts/lm9b_p_planner_recipe_transfer_support.py` — its `_MACHINE_SCALAR_FIELDS`, grammar, and acceptance predicate are unchanged; we are only making them declarable, plus the one M1(d) enum-driven alignment which is realized entirely in the schema, not in gate code.

## Testing

Deterministic, no model:
- **Carrier-ledger tests (pin, not proof):** one test per M1–M6 asserting the specific schema/contract representation exists (e.g. `authority_artifacts.items.artifact_kind.enum == ["environment_snapshot","planning_policy"]`; the shared identifier `$def` is referenced by every applicable field). These **pin the reviewed ledger and fail on drift**; they do *not* claim to mathematically prove every future gate rule has a carrier.
- **Positive:** a corrected R01-shaped-but-not-R01-derived synthetic descriptor set (bare `artifact_kind` tokens, unique ids, reserved `source_task`) passes schema validation.
- **Boundary/negative:** qualified-schema-id `artifact_kind`, duplicate descriptor id, `task_envelope` in `authority_artifacts`, malformed identifier, policy pointer outside `/rules/` each fail **schema validation** with a legible message — demonstrating the failure now surfaces at the visible carrier.
- **Consistency:** recomputed fingerprints/manifests match; existing LM9B-P suite stays green.

## Explicitly deferred (own later, independently-testable decisions)

Causal-feedback correction; prompt/turn-budget revisiting; typed construction tools / larger authoring-hook substrate. Each requires its own authorization; **no rerun or model call** happens until this slice is reviewed and merged and a new experiment is separately authorized.
