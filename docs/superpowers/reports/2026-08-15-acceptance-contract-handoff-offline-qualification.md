# Acceptance Contract Handoff Offline Qualification

**Date:** 2026-08-15
**Architecture baseline:** `d9c61e47e67630bc43487c444e37cdde1e2326d4`
**Classification:** Incomplete — Constructor artifact failed mechanical admission
**Handoff qualified:** No

## Objective

Test only the first unproven North Star handoff:

```text
authentic user intent
-> proposed acceptance artifact
-> independent adequacy review
```

The experiment was deliberately isolated from Prime protocol authority, Rook
profiles, persistence, Rhino, Grasshopper, Rook MCP, and deterministic runtime
operation semantics.

## Frozen Inputs

Three authentic retained intent files were recovered byte-for-byte:

| Intent | Exact retained text | SHA-256 |
|---|---|---|
| Point row | “Create a Grasshopper definition that generates a row of points along the X axis using adjustable Start, Step, and Count controls, with Y and Z fixed at zero.” | `75F25C167C296DA15148C7C0DC57211388E0E6A3489F690A5335F99F187BA711` |
| XY grid | “Create a rectangular grid of points in the XY plane with four adjustable sliders: Columns=3, Rows=2, X Spacing=5, and Y Spacing=10. Anchor the grid at the origin and keep every Z coordinate fixed at zero.” | `EE012EDE9D45D423D646DE3A91F987541FA32745E686FC234B47B2394C1F56E1` |
| Helix | “Create an adjustable helical curve around the Z axis using native Grasshopper components. Provide useful controls for its principal dimensions and resolution.” | `19B9E53AEE6B9ADBD3855A0146B19B65B3E68F8191F767F6A7F6144FFFBE9B3E` |

The local model was frozen as:

```text
model             qwen3.8:27b
reasoning         medium
Ollama            0.32.13
manifest SHA-256  22130167C4C20E20C7B71454612966CA8E8171E9B3CC8AB6CE8AA6CBFEC79643
```

The manifest's exact config/layer digests, sizes, and blob presence were
verified. The 17 GB model blob was not independently rehashed; the evidence
makes that nonclaim explicit.

Generation was frozen at six calls maximum, zero retry, zero repair, no
fallback, `num_ctx=32768`, `num_predict=8192`, and a 900-second per-call limit.
Constructor and Reviewer used separate system prompts and stateless two-message
requests. The exact reviewer request was to be composed deterministically from
the frozen template, original intent, validated proposal bytes, proposal hash,
evidence vocabulary, and closed reviewer schema.

## Pre-Contact Reviews

### A. Pre-design audit

Passed. The slice tested only acceptance-meaning construction and independent
review. It explicitly excluded:

- Prime role/runtime effectiveness;
- Rook mutation/profile authority;
- exclusive dispatch ownership;
- deterministic operation semantics;
- Grasshopper correctness; and
- production readiness.

### B. Pre-contact review

Passed:

- `20/20` inert tests;
- `20/20` frozen manifest entries matched;
- three Constructor requests contained exactly `system,user` messages;
- no shared conversation history;
- closed constructor and reviewer schemas;
- explicit output paths;
- no result or call-ledger artifact;
- no task topology, component name, GUID, C* identity, or tool call in the
  static prompts; and
- no Rhino, Grasshopper, Rook MCP, or external provider contact.

Frozen pre-contact manifest:

```text
ECF7C500DF1C37D136204667BB40DB2BEF8849E39401D432F467AC322D90FA49
```

Independent pre-contact review:

```text
FF941B45D58516AB6902716BC1B713F2D0AD1098D4E378D77E6B56E8F2238309
```

## Authentic Run

Exactly one local inference call was started and completed:

```text
call                 point_row.constructor
HTTP status          200
done                 true
done reason          stop
prompt tokens        6925
generated tokens     2377
total duration       51.0076643 seconds
```

No second call, Reviewer call, retry, repair, fallback, provider call, or host
contact occurred.

## Mechanical Admission Failure

The raw Constructor proposal declared these symbolic roles:

```text
start
step
count
points
```

Its requirements, claims, evidence requests, and candidate expressions instead
referenced a second naming family:

```text
start_control
step_control
count_control
points_output
```

The first exact failure was:

```text
$/requirements/0/roleIds:
unknown_refs=['points_output', 'start_control', 'step_control', 'count_control']
```

The frozen JSON output schema constrained keys and local shapes but could not
enforce cross-object reference closure. The post-output mechanical validator
owned that rule and refused the artifact correctly.

Because the proposal was not admitted, it could not enter the independent
Reviewer handoff. Running a Reviewer over unadmitted data or altering the
schema/prompt after observation would have tested a different protocol. The
no-retry/no-tuning contract therefore required an immediate stop.

## Dimension Results

These dimensions remain separate; no aggregate score is reported.

| Dimension | Result | Evidence |
|---|---|---|
| Requirement coverage | Not admitted | The raw proposal extracted four exact source spans, but no accepted artifact or independent review exists. |
| Assumption honesty | Not independently reviewed | The raw proposal explicitly recorded two material assumptions and two unresolved items. Their adequacy is not established. |
| Evidence feasibility | Mechanically recognized, artifact inadmissible | Evidence type and fact names came from the frozen vocabulary, but their references used undeclared roles. |
| Deterministic vs. judgment authority | Not independently reviewed | The raw proposal assigned authorities, including `user` for structural adjustability, but no Reviewer assessed whether those assignments weaken the intent. |
| Expression/schema validity | Fail | Candidate expressions and other records contain unknown symbolic-role references. Full operation semantics were outside this qualification. |
| Independent Reviewer defect detection | Untested | No valid proposal crossed the Reviewer admission boundary. |

## Raw Proposal Observations

The unadmitted artifact still supplies bounded evidence about Constructor
behavior:

- It found all four explicit point-row requirement phrases.
- It identified symbolic controls and an output collection without prescribing
  Grasshopper components or topology.
- It marked the exact indexed X relationship `unproven` under the supplied
  expression vocabulary.
- It marked structural adjustability `unsupported` rather than inventing a
  deterministic fact.
- It failed exact internal identity custody by using two role-name families.

These are observations about raw output, not accepted semantic conclusions.

## C. Post-Run Causal Review

The call ledger proves:

```text
calls started       1
calls completed     1
constructor calls   1
reviewer calls      0
retry calls         0
repair calls        0
fallback calls      0
```

The consumed request contained exactly one system and one user message. The
frozen pre-contact manifest remained unchanged with zero mismatches. No
qualification-owned Python or Ollama invocation process remained after the
failure.

## D. Adversarial Final Review

- **Self-approval:** none. The Constructor emitted no adequacy disposition and
  no Reviewer was invoked.
- **Hidden shared context:** none in the consumed two-message request.
- **Topology leakage:** none in the static prompts or artifact.
- **Unsupported claims:** the artifact disclosed two, but remained inadmissible
  because its references did not close.
- **Vacuity risk:** candidate expressions use operation names whose full
  deterministic semantics remain unqualified; this run does not treat their
  shape as meaning.
- **Overclaim check:** the result remains `incomplete` and makes no claim about
  the two uncalled intents, Reviewer competence, or production readiness.

## Evidence Custody

Disposable evidence root:

```text
C:/Users/bring/AppData/Local/Temp/rook-acceptance-contract-handoff-qualification-v1
```

| Artifact | SHA-256 |
|---|---|
| Frozen pre-contact manifest | `ECF7C500DF1C37D136204667BB40DB2BEF8849E39401D432F467AC322D90FA49` |
| Independent pre-contact review | `FF941B45D58516AB6902716BC1B713F2D0AD1098D4E378D77E6B56E8F2238309` |
| Call ledger | `6507E328AE7B5DC1140D2105078DF10D4C3E50E113908CF70CB29D9984ED87BD` |
| Constructor request | `CE962771AC67C63B02B6701938A051C4AEDFDB1E6FE7BBF76921085C690B09F4` |
| Raw Ollama response | `2ABEF635394255D2977B3C5E8F51785A03EC7ED49C0F4A693292B2FEAA1B02B0` |
| Parsed raw proposal | `D78CF151BB6A5613790FC49E9443DBD14E9D4D70AFA3AF7819751C529FD5363A` |
| Qualification result | `03D9D78B617B5E1E2A645BD90C6E801E665F8F4BAA47A00B36CDBC1BA8A57A10` |
| Post-run causal review | `CFB1ACEC160D6A4D6E70E67E3AB54F2060BA4EEEC523A0BEC0DFEE0D0C89DF99` |
| Adversarial final review | `D11A61F27026BD2CD26BF0F7392B16A2DF6D2E0B3637AAB2B393488887B76FC6` |

Evidence-prefix manifest:

```text
758E33DDD31DED0104EC67B25C7519C6B3296438B61898856A26F610F11E7433
```

All nine entries in that manifest independently rehashed with zero mismatches.

## Conclusion And Next Slice

The first authority handoff is not qualified. This is not evidence against the
North Star architecture or Qwen's general reasoning ability. It is direct
evidence that constrained JSON shape is not the same as admitted symbolic
meaning.

No production implementation slice is justified yet. More contract-
construction evidence is required.

The smallest honest follow-up is another separately frozen, point-row-only
offline qualification that tests whether one bounded Constructor continuation
can consume the exact mechanical reference diagnostic and return a closed
artifact before a fresh independent Reviewer is invoked. That future slice
must preserve this lane unchanged and must not silently normalize, rename, or
repair symbolic IDs outside the model-authored artifact.

Until that succeeds, do not implement the seven-stage router, acceptance
compiler, Prime role adapter, workflow persistence, profile enforcement, or
stair qualification against this package.
