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
| generated contract -> independently admitted meaning | symbolic roles, claims, authority, and evidence can represent intent | a fresh Constructor artifact plus a separate no-shared-context Reviewer that detects meaningful semantic defects |
| Prime protocol/configuration -> effective role runtime | separate top-level sessions and profiles enforce roles | wire/runtime evidence proving exact model, context, tools, authority, terminal lifecycle, and session separation |
| persisted dispatch -> exclusive live worker ownership | ledger intent, CAS, and reconciliation prevent duplicate work | crash/race evidence proving one live owner and no repeated consumed mutation |
| operation name -> fully defined deterministic semantics | a closed vocabulary can compile generic claims | exact type, precision, evidence, completeness, error, and budget semantics with causal tests for each operation |

These are independent qualifications. Success at one does not transfer to the
others.

## First Evidence Slice

The only authorized next slice is offline and disposable:

```text
three authentic retained intents
-> three fresh Qwen3.8 Acceptance Constructor calls
-> mechanical artifact validation only
-> three separate fresh Qwen3.8 Acceptance Reviewer calls
-> attributed adequacy findings
```

It permits at most six local model calls and no retry, repair, tuning, fallback,
provider/network access, Rhino, Grasshopper, Rook MCP, deployment, or product
change. Constructor and Reviewer artifacts are experiment data, not shipped
schemas or a new framework.

The slice reports requirement coverage, assumption honesty, evidence
feasibility, authority allocation, mechanically knowable expression/schema
validity, and reviewer defect detection independently. Semantic adequacy
remains attributed judgment.

## Consequence

The seven-stage staging map is suspended. Its order and owners remain a useful
North Star, but no production stage is authorized until the first handoff is
qualified and the resulting evidence identifies the smallest justified next
slice.

## First Qualification Result

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

No production slice is justified. A separately frozen follow-up must first
test whether a bounded Constructor continuation can consume the exact reference
diagnostic and produce an admitted artifact for a fresh independent Reviewer.
