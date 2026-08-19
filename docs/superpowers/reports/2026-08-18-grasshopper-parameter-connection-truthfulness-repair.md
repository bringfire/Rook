# Grasshopper Parameter Connection Truthfulness Repair

**Date:** 2026-08-18
**Status:** Implemented and live-qualified
**Model contact:** None
**VP2 rerun:** None

## Defect

The retained VP2 strategy-discipline evidence exposed a closed-semantics Rook
defect. Grasshopper metadata identified `Point On Curve` as a standalone
parameter, but mutation admission treated arbitrary requested input indices as
valid. Connection responses counted `AddSource` calls without proving source
membership, and snapshots projected incoming sources only for a short
type-name allowlist.

This allowed an attempted `C1.O0>C2.I1` connection to report success even
though the standalone parameter has only one logical input. The resulting flow
was absent from later snapshots, leaving Qwen to investigate misleading host
feedback.

## Repair

One capability-based parameter contract now owns connection selection,
metadata, and snapshot projection:

- A supported standalone Grasshopper parameter has exactly one logical input
  `I0` and one logical output `O0`.
- Conventional components retain their actual input and output collections.
- Out-of-range selectors are refused before mutation.
- Connection and disconnection counts advance only after source membership is
  observed in the requested post-state.
- Raw `/gh/connect` and `/gh/disconnect` detect an already-satisfied post-state
  before undo recording or mutation, return an explicit no-op reason, and do
  not request a solve or canvas refresh.
- `/gh/connections` projects standalone and conventional parameters through
  the same logical `ParamIndex` plus `Sources`/`Recipients` envelope.
- Snapshots project logical ports and incoming flows for every supported
  standalone parameter; no component-name or type-name catalog was added.

Raw connection and `gh_edit` paths use the same selector resolver. Existing
Grasshopper solve scheduling and receipt ownership remain unchanged.

## Python Boundary Follow-up

The MCP knowledge wrappers now preserve the same distinction as the managed
routes:

```text
request succeeded
!= mutation committed
!= proven no-op
```

Duplicate connect and missing disconnect calls remain successful, auditable
invocations, but they record no connection delta, do not clear a prior failure
as a correction, and do not earn mutation-derived gotcha success. Session
metadata retains normalized `request_succeeded`, `mutation_committed`, and
`no_op` facts. Successful disconnect history now uses the route-resolved source
and target GUIDs and indexed selectors, matching connect history.

This was an offline Python telemetry-custody correction. It did not change the
managed host behavior qualified below, and no rebuild, deployment, Rhino, or
model contact was performed for this follow-up.

## Live Qualification

The authoritative post-update run used an owned Rhino process and the deployed
Release companion:

```text
Rhino PID:       44964
Native port:     52374
Live tests:      2/2 passed
Shutdown:        graceful
Remaining Rhino: zero
```

The conventional indexed-component regression passed. The new `Point On Curve`
regression then established:

```text
metadata
-> isSimpleParam = true
-> one logical input I0
-> one logical output O0

C1.O0>C2.I1
-> connected = 0
-> exact out-of-range diagnostic
-> no solve-relevant mutation committed
-> observed flows remain empty

C1.O0>C2.I0
-> connected = 1
-> solve receipt reaches ready
-> receipt-fenced snapshot contains C1.O0>C2.I0
-> target input I0 reports one source

duplicate C1.O0>C2.I0
-> connected = 0
-> no solve-relevant mutation committed
-> observed flow remains exactly once

missing C2.O0>C1.I0 disconnect
-> disconnected = 0
-> no solve-relevant mutation committed
-> valid C1.O0>C2.I0 flow remains

raw duplicate C1.O0>C2.I0 connect
-> connected = false
-> noOp = true, reason = connection_already_exists
-> valid flow remains exactly once

raw missing C2.O0>C1.I0 disconnect
-> disconnected = false
-> noOp = true, reason = connection_does_not_exist
-> valid flow remains

/gh/connections for standalone Point On Curve
-> one input envelope at ParamIndex 0
-> Sources contains the connected Circle output
```

The live harness manifest is SHA-256
`E874EF57889939DDC3F313FD59A44AFB6C9191EB512BB7AD0CE57762562452E1`.
The compact causal result is SHA-256
`EE85F0411AAE5BEE8A0C665EE7C916D0CFEC40EAC72F7593A23E835D3DE23FBD`.

One earlier owned run is retained as non-green because its live test required
epoch equality across a no-op. A delayed solution from prior `gh_edit` work
advanced the global epoch, so that assertion could not establish route-owned
solve behavior. The managed regression instead proves zero scheduling and
refresh calls; the live regression proves the public no-op response and
unchanged wiring.

## Verification

- Focused managed parameter/receipt tests: `67/67 passed`.
- Related Python tests: `212/212 passed`, 11 existing warnings.
- Follow-up wrapper/session/gateway tests: `204/204 passed`, 22 existing
  warnings.
- Full managed suite: `3803/3803 passed`.
- Full local Release deployment completed with native, managed, RookBIM,
  registration, AppData, and Chirp synchronization successful.
- Durable evidence manifest: `247/247`, zero mismatches, SHA-256
  `3EA39AFA9C4817CF6694481E85F867B335CC04ED7FF1908B3509737B00A1F27D`.
- No Qwen, Prime, Ollama, or other model contact occurred.

Evidence root:
[grasshopper-parameter-connection-truthfulness-v1](C:/UDEV/RookEvidence/2026-08-18-grasshopper-parameter-connection-truthfulness-v1)

## Disposition

The reviewer-identified Rook admission and reporting defect is repaired across
`gh_edit`, raw public connect/disconnect routes, snapshots, `/gh/connections`,
and MCP session/learning custody. The managed surface remains qualified against
live Grasshopper; the final Python boundary is covered offline. Qwen's separate
judgment mistakes in the VP2 specimen remain recorded. No reasoning rule was
added, no semantic acceptance machinery changed, and VP2 was not rerun.
