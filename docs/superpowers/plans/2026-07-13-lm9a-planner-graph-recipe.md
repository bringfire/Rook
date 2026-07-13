# LM9A Planner Graph Recipe Implementation Plan

Status: withdrawn before implementation

Date: 2026-07-13

## Why This Plan Is Withdrawn

The original combined plan attempted to implement four distinct systems in one
slice:

```text
safe JSON/JCS ingress
companion artifact validation
phase-DAG/report machinery
Planner graph recipe semantics
```

Review showed that the first three are a generic validation kernel, while the
fourth is an LM9A semantic extension. Continuing with one plan would make
mutable host-language ingress, resource budgeting, phase dependencies,
immutability, report mechanics, and semantic rules co-evolve inside one large
implementation.

No task in the earlier version of this plan is approved for execution. Git
history preserves the draft for reference; it is not an implementation
contract.

## Corrected Architecture

```text
raw recipe bytes + raw validation-bundle bytes
-> LM9A validation kernel
   -> bounded owned parsing
   -> transitively immutable values
   -> one fixed validation budget
   -> declarative PhaseSpec engine
   -> immutable phase results
   -> deterministic report construction
-> LM9A semantic extension
   -> recipe and companion schemas
   -> provenance and authority rules
   -> clauses, assumptions, and unresolved intent
   -> shape, capabilities, and worker slots
   -> offline fixtures
```

The normative designs are:

- `docs/superpowers/specs/2026-07-13-lm9a-validation-kernel-design.md`
- `docs/superpowers/specs/2026-07-13-lm9a-planner-graph-recipe-design.md`

## Replacement Plan Sequence

After both designs are reviewed, write two independent plans:

1. **LM9A-Kernel plan**

   Implements raw byte ingress, the fixed budget ledger, owned immutable JSON
   values, RFC 8785 primitives, the `PhaseSpec` registry and engine, immutable
   issue/result types, and deterministic report construction. Tests use only
   synthetic domain-neutral phases and artifacts.

2. **LM9A-Semantics plan**

   Implements Planner graph recipe schemas, companion authority validation,
   semantic phase registrations, immutable semantic indexes, and the offline
   radial/control fixtures by consuming the merged kernel.

The semantics plan must not execute until the kernel implementation is merged.

## Locked Corrections For Replacement Plans

- Public inputs are raw `bytes`, never caller-owned parsed mappings.
- One fixed budget covers bytes, depth, width, nodes, decoded strings,
  references, diagnostics, blockers, and aggregate phase work.
- Budget checks occur before allocation or append where the bounded parser or
  engine can know the increment.
- JSON object source order is immaterial; changed key/value content is material.
- All accepted values, indexes, phase results, and exports are transitively
  immutable.
- Every phase is declared once through `PhaseSpec`; execution, dependencies,
  required inputs, issue authorization, and report rows derive from it.
- LM9A `provenance` depends on both `schema` and `companion_artifacts`.
- A malformed recipe may coexist with independently evaluated companions, but
  no semantic phase receives a schema-invalid recipe.
- The draft 145-row issue list is not frozen API. Replacement planning must
  retain only distinctions needed by consumers and use bounded metadata plus
  hashed detail for implementation branches.
- No model, compiler, worker, tool, Rhino, Grasshopper, or live run belongs in
  either implementation PR.

## Next Gate

Review the validation-kernel design first. Do not write either replacement
implementation plan until that design and the amended semantic design are
approved.
