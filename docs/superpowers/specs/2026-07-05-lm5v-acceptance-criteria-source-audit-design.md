# LM5V — Acceptance-Criteria Source Audit Design

- **Date:** 2026-07-05
- **Status:** Draft for review
- **Slice:** LM5V
- **Type:** Diagnostic/spec artifact only

## 1. Purpose

LM5U closed the worker evidence-push ladder with a discriminating positive
result:

```text
LM5T present_v2: diagnostics visible, 0/5 action_request
LM5U present_v3: diagnostics + acceptance criteria visible, 5/5 action_request
```

The absent control also held:

```text
evidence_absent_like: 0/5 action_request
evidence_present_v3_like: 5/5 action_request
```

That result supports a narrow claim:

```text
Acceptance criteria, not hidden answers, moved worker decision behavior.
```

It does **not** prove semantic repair correctness. The worker authored simple
body snippets such as `A = 0.0;` and `A = 1.0;`; those were not executed or
verified in LM5U.

LM5V turns that result upstream. It audits where the six LM5U acceptance
criteria came from, which layer should own them durably, and what the next
design slice should target.

## 2. Scope

LM5V is a spec/doc-only diagnostic slice.

In scope:

- Inventory the six LM5U criteria.
- Trace each criterion to its current LM5U source path.
- Classify each source by ownership class.
- Recommend a durable home for each criterion.
- Identify what must **not** own each criterion.
- Recommend the next narrow design slice.

Out of scope:

- No production behavior changes.
- No `mcp_server/src` changes.
- No probe script changes.
- No tests.
- No live runs.
- No new evidence packets.
- No parser, prompt, transport, worker, or planner implementation changes.
- No durable schema changes in this slice.

## 3. Doctrine

Workers act on checkable acceptance criteria, not hidden answers.

Acceptance criteria should not collapse into a single monolithic artifact.
Different classes of criteria have different owners:

- Planner decides task intent and missing-information questions.
- Compiler turns accepted intent into workflow/task contracts.
- Verifier owns checkable outcome expectations.
- Receipts and evidence own observed failures.
- KG/convention sources may supply patterns only with provenance.
- Worker receives assembled criteria, not hidden reasoning or bound answers.

Therefore LM5V explicitly rejects:

```text
Put all acceptance criteria in RookWorkflowContract.
```

`RookWorkflowContract` may own some mechanical or verifier-linked facts, but it
must not absorb receipt observations, action conventions, KG lore, or user
intent that belongs elsewhere.

## 4. Fixed Audit Inventory

LM5V audits exactly the six criteria proven in LM5U:

```text
output_a_assigned
output_a_double_compatible
verify_repair_succeeds
preserve_body_mode
resolve_target_diagnostics
remove_unresolved_symbol
```

No other criterion family is authoritative in LM5V.

## 5. Ownership Classes

### 5.1 Compiler/Verifier-Owned Mechanical Criteria

Criteria mechanically derived from known task structure, pin contracts, node
types, or verifier expectations.

Examples in LM5U:

- `output_a_assigned`
- `output_a_double_compatible`
- `verify_repair_succeeds`

These should become generic derivation rules, not fixture-specific packet text.

### 5.2 Receipt/Evidence-Routed Diagnostic Criteria

Criteria derived from observed failures and their receipts.

Examples in LM5U:

- `resolve_target_diagnostics`
- `remove_unresolved_symbol`

These should remain evidence-routed. The workflow contract may say that repair
must address current diagnostics, but the concrete diagnostic content belongs
to receipts/evidence.

### 5.3 Convention/KG Criteria Needing Promotion

Criteria currently supplied through gotchas, conventions, or knowledge packets,
but which are stable enough to deserve a more explicit owner.

Example in LM5U:

- `preserve_body_mode`

This currently comes from `script_body_gotcha`. A durable system should decide
whether this belongs in the action contract, compiler node type, or a
KG-backed convention source with provenance.

### 5.4 Planner/User-Intent Criteria Requiring Clarification

Criteria that cannot be safely invented by compiler, verifier, or worker.

Examples outside the LM5U inventory:

- "use `42.0`"
- "preserve design intent"
- "make this visually lighter"
- "match project convention"

These require planner-owned intent, KG-backed convention with provenance, or a
clarify/resupply loop.

## 6. Source Audit Matrix

| Criterion ID | Criterion Text | Current LM5U Source Path | Source Class | Durable Owner | Promotion Recommendation | Do Not Put Here | Next Slice Implication |
|---|---|---|---|---|---|---|---|
| `output_a_assigned` | Output A must be assigned. | `create_script.initial_execution_params.pins_out` | Compiler/verifier-owned mechanical criterion | Compiler/task contract, optionally mirrored into verifier spec | Derive a generic output-assignment requirement from each required output pin. | Receipt diagnostics, worker prompt text, hidden bind params | Design an acceptance-criteria assembly boundary that can derive output-assignment criteria from pin contracts. |
| `output_a_double_compatible` | Output A must be double-compatible. | `create_script.initial_execution_params.pins_out` | Compiler/verifier-owned mechanical criterion | Compiler plus verifier type expectations | Derive a generic type-compatibility requirement from output pin type declarations. | Worker prompt text, KG lore, receipt diagnostics | Decide how pin type declarations become worker-visible checkable criteria without exposing hidden repair params. |
| `verify_repair_succeeds` | The repaired body must satisfy the `verify_repair` expected outcome: `succeeded`. | `workflow_contract.rules.verify_repair.expected_outcome` | Compiler/verifier-owned mechanical criterion | Verifier spec and workflow contract | Keep expected verifier outcome modeled; add a route that turns it into worker-visible acceptance criteria. | Receipt diagnostics, KG, prompt text | Design the assembly boundary to translate verifier expectations into criteria without moving verifier semantics into evidence packets. |
| `preserve_body_mode` | The repair must preserve body-style code. | `script_body_gotcha` | Convention/KG criterion needing promotion | Action contract, compiler node type, or KG-backed convention source with provenance | Promote from ad hoc gotcha into an explicit action/code-shape convention source. | Hidden bind params, prompt-only prose, receipt diagnostics | Decide whether action schemas or compiler node metadata should expose code-shape constraints. |
| `resolve_target_diagnostics` | The repair must resolve the current target diagnostics. | `create_script.receipt.script_receipt.repair_anchor.target_errors` | Receipt/evidence-routed diagnostic criterion | Receipt/evidence source routed by planner | Preserve as an evidence-derived criterion over current diagnostics; do not bake diagnostic content into the static workflow contract. | Static workflow contract content, hidden bind params, KG-only inference | Assembly boundary must route bounded current diagnostics into worker-visible criteria. |
| `remove_unresolved_symbol` | The repaired body must not leave `DefinitelyMissingSymbol` unresolved. | `create_script.receipt.script_receipt.repair_anchor.target_errors` | Receipt/evidence-routed diagnostic criterion, currently fixture-specific | Receipt/evidence source, with possible KG-assisted diagnostic interpretation later | Treat as a derived criterion from diagnostic content. Keep the exact symbol sourced from the receipt, not from fixture constants. | Static contract, prompt text, hidden bind params | Decide whether diagnostic-specific subcriteria are generated mechanically from receipt text or deferred to a later diagnostic interpreter. |

## 7. Current Modeling Status

### Already Modeled

- `pins_out` exists in `InitialNodeParams.execution_params`.
- `verify_repair.expected_outcome` exists in `VerifierStepSpec`.
- `target_errors` now exist in the deterministic receipt repair anchor after
  LM5T/LM5U fixture enrichment.

### Fixture-Only Or Convention-Shaped

- `preserve_body_mode` currently comes from `script_body_gotcha`.
- `remove_unresolved_symbol` is derived from a fixture diagnostic string and is
  not yet a generic diagnostic-interpretation layer.

### Not Modeled As A Durable Assembly Boundary

The system does not yet have a first-class boundary that gathers criteria from
compiler, verifier, evidence, and convention sources while preserving ownership.
LM5U constructed that packet inside the probe fixture; LM5V says where those
facts should come from before any generalization happens.

## 8. Relationship To Rook2

Rook2 should not become the first owner of acceptance-criteria semantics.

Rook2 may eventually consume or export assembled criteria as part of a brokered
workflow surface, but LM5V keeps ownership in the source layers:

- Planner owns intent and clarification.
- Compiler/verifier own mechanical and outcome criteria.
- Receipts/evidence own observed failures.
- KG/conventions own patterns only with provenance.

This lets Rook2 stay a broker/export surface rather than a semantic dumping
ground for criteria that should be generated upstream.

## 9. Future Criterion Families

The following families are plausible but **not audited in LM5V**:

- geometry tolerances
- object-count expectations
- layer/material/name/user-string constraints
- Grasshopper solve/error expectations
- visual/viewport acceptance
- user aesthetic intent
- project convention conformance
- BIM/Revit constraints

No future criterion family should enter a durable contract surface until it has
the same evidence trail LM5U has:

```text
source path -> ownership classification -> worker-visible shape -> live/probe result
```

## 10. Recommended Next Slice

Next recommended slice:

```text
Design a deterministic acceptance-criteria assembly boundary that can gather
criteria from compiler, verifier, evidence, and convention sources without
collapsing ownership into one artifact.
```

This should be a narrow extraction/design target, not an implementation of the
whole Planner/Compiler contract.

It should not start by adding a broad `acceptance_criteria` field to
`RookWorkflowContract`. Instead, it should define:

- inputs accepted by the assembly boundary
- source provenance for each criterion
- stable criterion ids and payload shape
- how missing planner/user intent is represented
- what remains outside the boundary

Only after that design exists should production schema or compiler behavior be
changed.
