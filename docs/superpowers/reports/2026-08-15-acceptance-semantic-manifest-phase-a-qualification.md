# Acceptance Semantic Manifest Phase A Qualification

**Date:** 2026-08-15

**Classification:** Completed offline qualification

**Product changes:** None

**Specification baseline:** `4ec4929d8a351b022d8735c8bb9340d1968f63f0`

**Execution head:** `d0646a00e208dbb67de07dd1730ac6f6058f075f`

## Result

The V4 successor completed the bounded Phase A qualification:

```text
shared semantic manifest
-> closed typed contract schema
-> deterministic compiler
-> two marked-valid specification examples compile
-> coherent point-row artifact compiles
-> 23 isolated mechanical mutations refuse exactly
```

The fresh post-result suite passed **48/48** tests. The independent artifact
audit reproduced:

```text
PHASE_A_AUDIT_OK examples=2 mutations=23
```

No Constructor, Reviewer, model, provider, Prime, network, Rook MCP, Rhino, or
Grasshopper call occurred.

## Closed Tolerance Semantics

V3 demonstrated the core compiler seam but retained a cross-owner discrepancy:
the manifest admitted `finite_scalar` tolerance inputs while compiler code
secretly required literals. V3 remains byte-for-byte preserved and is not the
authoritative completed result.

V4 closes that discrepancy in the shared semantic contract. Both absolute and
relative `approx_equal` tolerances are exactly:

```text
finite
nonnegative
numeric literals
```

Roles, fields, binder variables, computed expressions, defaults, and inferred
values cannot supply a tolerance. Diagnostics are exact:

```text
negative finite literal  -> invalid / tolerance_negative
nonliteral source        -> invalid / tolerance_source_invalid
nonfinite literal        -> invalid / nonfinite
```

The corpus contains isolated absolute and relative mutations for negative and
nonliteral tolerances. Each mutation changes one declared property, returns its
expected path and code, constructs no Reviewer request, and leaves every other
case unaffected.

## Qualified Compiler Boundary

Within the frozen Phase A vocabulary, the evidence qualifies:

- role-kind and `valueType` compatibility;
- explicit scalar and collection field projection;
- lexical quantifier binding and collection quantification;
- manifest-owned operation arity, input patterns, result types, and costs;
- the four authority modes and their expression compatibility matrix;
- finite nonnegative literal tolerance admission and exact failure ownership;
- expression node, depth, quantifier-depth, and work-cost budgets;
- strict JSON, canonical bytes, closed schemas, and digest-sealed semantics;
- causal refusal of all 23 isolated mechanical mutations; and
- strict parsing and compilation of both specification examples marked valid.

This is a compiler qualification, not a semantic-adequacy result. It establishes
that mechanically decidable contract meaning has one closed owner and that
invalid artifacts stop before review.

## Evidence Custody

Root:

```text
C:/Users/bring/AppData/Local/Temp/rook-acceptance-semantic-phase-a-v4/operator
```

Headline SHA-256 values:

| Artifact | SHA-256 |
|---|---|
| Specification | `2A70E492AA2EDD36A69DD84C832790D782656DA05F941CB71D14DEA1D25DCF7D` |
| Semantic manifest | `D80D10393BFA7250B217C8636739EF4287E3AFBBE6E3C6A63834D99D4D51B30C` |
| Coherent point-row artifact | `76C4721C1FC7EDF60140DBFF6AF16744FE0B034441A2477766ED2C9D71AACB02` |
| Mutation corpus | `F1F36D43EBAE6DEDD9F8716CB3E16F9491278332923995B8E9F8CF067C67C3F8` |
| Source manifest | `9848312A2C7DCFE32C1B568F87B6701453F61AC3A421ED8B51C2C4030F39809F` |
| Execution ledger | `557149FF19372820D948EF3DB9F62DE4E65EB524365ADFCA220285146EB82292` |
| Qualification result | `3D378014A36F2AF1C28B8C30026C64064C54D5387B20D3066E2E19F793F23B28` |
| Evidence manifest | `FB8A376BD9EBA48AE1BC904A6F4CA2701B6E2596E71E0EC711F3E278618B5F46` |

The execution ledger derives repository custody rather than trusting caller
claims. It records a clean worktree, the exact baseline and execution head,
the sole post-baseline plan path, the specification blob, Python identity, and
zero contact budgets.

## Nonclaims And Next Boundary

Phase A does not qualify runtime expression evaluation, evidence collection,
intent adequacy, Reviewer sensitivity, policy routing, provider behavior, or
live-system behavior. It does not authorize production router implementation.

It does justify the separately bounded Phase B experiment:

```text
compiler-valid semantic artifacts
-> fresh fully informed Reviewer sessions
-> residual requirement coverage, invented-assumption, weakening,
   and unresolved-risk sensitivity
```

Phase B must consume this same semantic contract. Mechanically invalid cases
remain compiler-owned and must never be sent to a Reviewer.
