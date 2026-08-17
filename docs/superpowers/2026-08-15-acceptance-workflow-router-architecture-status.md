# Acceptance Workflow Router Architecture Status

**Date:** 2026-08-15
**Baseline package:** `d9c61e47e67630bc43487c444e37cdde1e2326d4`
**Status:** North Star architecture hypothesis — not implementation-ready

## Correction

The package at `d9c61e47` usefully describes a possible production ownership
chain, but it outruns the evidence. Declaring an owner, schema, profile,
operation, or recovery rule does not prove the boundary works.

The governing invariant is:

> A declared boundary is not an effective boundary until its owner, admission
> rule, and causal handoff are mechanically demonstrated.

## Presently Unqualified Handoffs

| Handoff | What the package declares | Evidence still required |
|---|---|---|
| generated contract -> independently admitted meaning | symbolic roles, claims, authority, and evidence can represent intent | after Phase A, compiler-valid cases reviewed by fresh, fully informed Reviewers that detect meaningful semantic defects |
| Prime protocol/configuration -> effective role runtime | separate top-level sessions and profiles enforce roles | wire/runtime evidence proving exact model, context, tools, authority, terminal lifecycle, and session separation |
| persisted dispatch -> exclusive live worker ownership | ledger intent, CAS, and reconciliation prevent duplicate work | crash/race evidence proving one live owner and no repeated consumed mutation |

These are independent qualifications. Success at one does not transfer to the
others.

## Consequence

The seven-stage staging map is suspended. Its order and owners remain a useful
North Star, but no production stage is authorized until the first handoff is
qualified and the resulting evidence identifies the smallest justified next
slice.

## Retained Qualification Results

The frozen offline qualification stopped correctly after its first local model
call. The point-row Constructor produced a closed JSON shape but referenced
four symbolic role IDs it had not declared. Mechanical admission refused the
artifact, so no independent Reviewer call was admissible and the remaining
five calls were not spent.

Result:

```text
classification        incomplete
handoff qualified     no
constructor calls     1
reviewer calls        0
retry/repair/fallback 0
```

This directly confirms the governing invariant: output shape and declared
ownership do not establish effective semantic custody. The evidence-led report
is `docs/superpowers/reports/2026-08-15-acceptance-contract-handoff-offline-qualification.md`.

The separately frozen V2 continuation then established:

```text
exact compiler reference diagnostic
-> same-session Constructor continuation
-> complete replacement artifact
-> unchanged mechanical validation: pass
```

That is a qualified bounded repair for this mechanical defect class. The fresh
Reviewer session also passed transport, closed-envelope, and mechanical result
validation, but returned `adequate` with no findings despite material semantic
weaknesses. Its request omitted the expression semantic contract supplied to
the Constructor, and its retained reasoning explicitly assumed the operations
were valid. The correct result is therefore:

```text
Constructor reference repair              qualified
Reviewer transport and envelope validity  qualified
Reviewer semantic sensitivity              failed on this specimen
Reviewer failure causally confounded        yes; semantic contract omitted
```

The evidence-led report is
`docs/superpowers/reports/2026-08-15-acceptance-contract-handoff-continuation-qualification.md`.

The offline Phase A V4 successor then qualified the shared deterministic
compiler boundary:

```text
shared semantic manifest
-> typed schema and compiler
-> coherent artifact and marked-valid examples compile
-> 23 isolated mechanical mutations refuse causally
```

This closes the former `operation name -> fully defined deterministic
semantics` handoff for the frozen Phase A vocabulary. In particular,
`approx_equal` tolerances are now manifest-owned finite, nonnegative numeric
literals; negative and nonliteral sources have distinct exact diagnostics.
The fresh suite passed **48/48** tests and the artifact audit reproduced
`PHASE_A_AUDIT_OK examples=2 mutations=23`, with zero model or live contact.

The retained evidence report is
`docs/superpowers/reports/2026-08-15-acceptance-semantic-manifest-phase-a-qualification.md`.

## Current Authorized Boundary

Phase A is complete. The separately reviewed Phase B qualification has also
completed with deterministic status `not_qualified_on_corpus`:

```text
six complete admitted Reviewer responses
-> coherent control restraint: pass
-> residual recognition: pass on all six
-> intended sensitivity: pass on three of five mutations
-> hidden-risk case: semantic issue noticed but wrong frozen category
-> authority-misrouting case: missed
```

The result report is
`docs/superpowers/reports/2026-08-15-acceptance-reviewer-phase-b-qualification.md`.

This result does not authorize production router implementation or prompt
tuning. It shows that intelligent review adds material value beyond the
compiler, while also demonstrating that this frozen Reviewer configuration is
not yet reliable enough to own residual semantic acceptance. Any next slice
requires a separate reviewed decision; runtime evaluation, policy routing,
deployment, and production implementation remain outside the current boundary.
