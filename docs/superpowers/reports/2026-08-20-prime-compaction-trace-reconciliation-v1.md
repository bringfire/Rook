# Prime Compaction Trace Reconciliation V1

**Date:** 2026-08-20
**Disposition:** `trace_admitted; semantic_judgment_unproven`
**Contact:** Offline only; zero Rhino, Grasshopper, Rook, Prime, Ollama, or Qwen contact

## Result

The sealed Vessel V5 source and Prime runtime now pass a separately versioned
trace-admission owner. The original V5 evidence and its campaign-time
`incomplete` classification remain byte-for-byte unchanged.

The offline shadow result is:

```text
trace admission             pass
latest terminal receipt     78e858015aeb627e69d4fe569cbaf37f
final fenced source event   39
components                  8
wires                       7
projected output items      180
errors                      0
warnings                    0
semantic status             unproven
semantic reason             independent_judgment_required
```

This closes the infrastructure classification. It does not convert the open
architectural task into a formal semantic pass. V5 remains a credible-success
and qualified Actor final-checkpoint specimen. No Qwen or Grasshopper failure
was observed; semantic evaluation still requires independent judgment.

## Versioned Ownership

Historical protocols continue to own the unchanged V1 module:

```text
mcp_server/src/rook/gh_behavioral_acceptance.py
SHA-256 8A68408AD6216A7DEF638EAC962B28CA7A32735312DCD00C57D038EAD8DEBAF5
```

The new V2 owner is additive:

```text
mcp_server/src/rook/gh_behavioral_acceptance_v2.py
SHA-256 85E6B175F939EFB728A2E36D686995F1CA3339AECE9CB06CDCE831F302F01D23
```

V2 delegates source-event, closure, receipt, and mutation semantics to V1. It
changes only these admitted projections:

1. Multiple Actor segments require one retained Prime session and equal ordered
   `agent_start` / `agent_end` pairs.
2. Every boundary must contain the exact successful sequence
   `compaction_start -> IPython state start/end -> compaction_end`, followed only
   by the observed preparing/committing handoff.
3. Every segment must retain the same goal ID and objective; continuation usage
   must increase by exactly one.
4. Failed, aborted, retrying, missing, or orphan compaction boundaries fail
   closed.
5. Goal changes, extra sessions, and any post-terminal activity other than the
   exact quiescent session action fail closed.
6. An exact successful `rhino_viewport` capture is observational with respect to
   Grasshopper authoring mutation. Failed, open, malformed, or unsaved capture
   shapes remain unknown. This does not classify viewport state as globally
   read-only.

The viewport rule was discovered honestly during the first offline attempt:
compaction admission passed, but 13 retained successful captures remained
unknown to V1 and prevented receipt selection. The final V2 projection is
closed over the public request fields and exact retained success shape. The
failed derived attempt is preserved separately and is not part of the sealed
result.

V2 streams the 3.54 GB runtime and retains only bounded lifecycle projections.
It does not load the runtime into memory or rewrite it.

## Custody And Shadow Evaluation

The reconciliation protocol froze both original manifests plus the exact V5
source, runtime, process result, historical evaluation, and V1/V2 owner bytes.
Both original manifests were independently verified before the output root was
created:

```text
V5 global manifest       66/66
V5 row manifest          39/39
source SHA-256           E86FDB1F88B1357F8811F3FC8F3DDBEC078C4949B873615E0CE1D98A98B966C8
runtime SHA-256          F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B
```

Only the 143,793-byte source log was copied. V2 appended a closure to the copy,
normalized that copy against the original retained runtime, selected the final
receipt, and inspected the already-retained final snapshot. No host call was
available in this execution path.

The final derived evidence is at:

```text
C:/UDEV/RookEvidence/2026-08-20-prime-compaction-trace-reconciliation-v1

entries                    9/9
manifest SHA-256           87F03B34230DE38B16C53D90CC6DF42DA5688574D7DCC4D3EE0D4F4E6507AABE
closure SHA-256            A2873069C69FD68D5C5B9D5740830126C67C77E3E1648EFC8D1610FB7A245F90
trace SHA-256              DE2337FCAF355E3C75C2215AEFB8B89971A027012E164D52A0BC8E72D627D376
shadow result SHA-256      BD5693D5D13A3FCC289B0019B2AE523C5525CB71F2B8111FF158840CF28956C6
mismatches                 0
```

## Prime Trace Size

The 3.54 GB runtime is dominated by cumulative stream records, not embedded
images:

```text
runtime rows                         74,473
runtime bytes                 3,543,087,572
message_update rows                  74,143
message_update bytes          3,521,830,701   99.40%
thinking_delta rows                  71,686
thinking_delta bytes          3,439,477,024
all delta text bytes                 306,219
serialized partial bytes      1,755,936,928
image-bearing rows                      38
image-bearing row bytes          20,054,395    0.57%
exact duplicate rows                     59
```

Every retained `message_update` contains a cumulative `partial` assistant
message in addition to its small delta. The 71,686 thinking-delta records alone
consume 3.44 GB, while all delta strings total only 306 KB. Exact duplicate rows
are rare, so ordinary file deduplication is not the issue; repeated cumulative
serialization is.

This is a Prime telemetry/storage efficiency finding. It does not weaken V5,
and no Prime format change is included here. A later bounded Prime change should
compare delta-only retention, reconstructability, crash custody, and diagnostic
utility before altering the trace contract.

## Verification

```text
focused and historical tests     269 passed
existing dependency warnings      11
Python compilation              passed
V1 owner hash                   unchanged
derived manifest                 9/9
live contact                    none
```

The reconciliation protocol SHA-256 is
`7822FBADDDF8F6989194790AA1A1DCE5C5CA3576E0F06D476603588C67807939`.
The offline runner SHA-256 is
`6B45F0DA15C81272A53BC6F09419729FA35F3DCB36EE59BFABBF2DBCB03D119D`.

## Disposition

The compaction compatibility repair is complete for this retained shape. Do
not rerun the Vessel. Keep V1 as the historical owner, use V2 only where its
version is explicitly frozen, and carry receipt-fenced visual self-observation
into varied product work.

Treat the Prime trace volume as a separate efficiency issue. It warrants a
small format investigation, not a change to Qwen guidance, semantic acceptance,
or the intelligent empirical loop.
