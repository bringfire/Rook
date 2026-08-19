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
- Snapshots project logical ports and incoming flows for every supported
  standalone parameter; no component-name or type-name catalog was added.

Raw connection and `gh_edit` paths use the same selector resolver. Existing
Grasshopper solve scheduling and receipt ownership remain unchanged.

## Live Qualification

The authoritative post-update run used an owned Rhino process and the deployed
Release companion:

```text
Rhino PID:       114108
Native port:     56470
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
```

The live harness manifest is SHA-256
`90B8A1EA1B3934E4D05BCB0A5952BD2EEBA84F29B5E1AADFC730ED434A41C957`.
The compact causal result is SHA-256
`FFDD0C2A1463261BCBFCE1C237389F3C2E3D1D255A4EFF671CB1A3999CD18AE5`.

## Verification

- Focused managed parameter/receipt tests: `64/64 passed`.
- Related Python tests: `191/191 passed`, 11 existing warnings.
- Full managed suite: `3800/3800 passed`.
- Full local Release deployment completed with native, managed, RookBIM,
  registration, AppData, and Chirp synchronization successful.
- Durable evidence manifest: `210/210`, zero mismatches, SHA-256
  `258489A53A1F8F06C24EB81A66BAE3F202B5084EBD0D56DA83C385F718B7A949`.
- No Qwen, Prime, Ollama, or other model contact occurred.

Evidence root:
[grasshopper-parameter-connection-truthfulness-v1](C:/UDEV/RookEvidence/2026-08-18-grasshopper-parameter-connection-truthfulness-v1)

## Disposition

The reviewer-identified Rook admission and reporting defect is repaired and
qualified against live Grasshopper. Qwen's separate judgment mistakes in the
VP2 specimen remain recorded. No reasoning rule was added, no semantic
acceptance machinery changed, and VP2 was not rerun.
