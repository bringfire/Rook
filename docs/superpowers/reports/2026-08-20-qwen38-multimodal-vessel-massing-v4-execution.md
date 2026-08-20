# Qwen3.8 Multimodal Vessel Massing V4 Execution

**Date:** 2026-08-20
**Disposition:** `partial_success - credible architectural result, final checkpoint failed`
**Executions:** One V4 Actor transaction; zero V4 Actor retries

## Result

V4 materially corrected V3's architectural failure. Qwen received both reference
images in order and produced a flared, six-sided circulation lattice containing
six separate landing pads per tier, an open central atrium, horizontal walkway
links, and many separate inclined stair ribbons. The final massing is a rough
conceptual interpretation rather than a polished Vessel replica, but it no
longer reads as continuous floor belts or enclosing facade panels.

The Actor completed naturally with `goal.complete()`. Goal, budget, process,
model, attachment, and target custody passed. The formal Actor checkpoint failed
because Qwen made one read-only `gh_errors` call after its final receipt-fenced
snapshot. The result is therefore not a qualified final-checkpoint pass.

## Operational Result

```text
Prime exit code                 0
Actor elapsed time        1,162.562 seconds
provider total tokens     2,263,276
gateway events                   65
goal status                complete
budget status              pass
custody status             pass
owned child PIDs                  0
```

All 65 source events used the canonical gateway. Both reference images were
attached before the first Rook call. The retained source closed with one
`agent_end`; no qualification-owned process remained.

Qwen stayed in one Python authoring strategy. Its first script creation was
refused without mutation, the corrected creation committed, and a subsequent
RhinoCommon error (`Brep.CreateExtrusion` unavailable) was diagnosed from
`gh_errors` and repaired locally. The final canvas contained one Python component,
seven sliders, seven wires, zero errors, and zero warnings.

## Final Definition

The restored default output reported:

```text
Levels                       8
Level Height                14
Base Radius                 26
Top Radius                  44
Walkway Depth                8
Tier Stagger Angle           8
Stair Width                3.5

landing meshes              48
walkway meshes              48
stair meshes                84
combined meshes            180
```

The 48 landings equal six pads across eight tiers. Top Radius exceeds Base
Radius, yielding the observed flare. Qwen exercised `Levels` at 12 and 5 before
restoring 8. It exercised `Tier Stagger Angle` at 0 and 35 before restoring 8.
Each probe was followed by diagnostics and a viewport observation.

The final restoration produced receipt:

```text
ce83238cc2328cbf7e54d430c933c188
```

The retained source order was:

```text
57  restore all chosen defaults; terminal receipt
58  clean diagnostics
59  wait for receipt -> ready
60  capture Top viewport
61  capture Perspective viewport
62  wait for same receipt -> ready
63  same-receipt fenced snapshot
64  clean diagnostics                         <- unnecessary later gateway call
end goal.complete(), agent_end
```

## Visual Judgment

The final Top capture shows a large open center, six radial landing locations,
and open space between the principal pads. The final Perspective capture shows a
narrow base, broad top, stacked landings, and a dense field of diagonal members.
Those members read as separate inclined ribbons rather than the side-wide panels
from V3.

The result is still schematic. Its stair field is visually busy, the landing and
walkway hierarchy is only partly legible, and no claim is made that the geometry
reconstructs the actual Vessel or provides code-compliant circulation. The
bounded claim is that Qwen produced a credible conceptual circulation lattice
from the images and corrected the exact V3 category errors.

## Trace And Orchestration Limits

The sealed campaign-time hidden evaluator returned
`unproven: authoring_trace_invalid`. Qwen included the optional `displayMode`
argument on successful `rhino_viewport` calls, while V4's runner-only classifier
admitted only the otherwise identical argument shape without that field. This is
an experimental trace-normalization gap, not a host mutation ambiguity.

The next runner revision admits the exact closed `displayMode` variant only when
the returned mode matches the requested mode. Replaying normalization in memory
over the untouched V4 source then leaves zero unknown events and selects receipt
`ce83238cc2328cbf7e54d430c933c188` without error. V4's sealed files and original
classification remain unchanged.

The Codex execution wrapper also disappeared after the Actor process result was
durably written and before the runner's post-Actor operator phase. No Actor or
model retry occurred. The exact existing offline normalization, silent operator
evaluation, custody recording, row sealing, and campaign sealing functions were
resumed from the retained Actor bytes. The operator phase completed with no
owned process and no semantic feedback to Qwen.

## Evidence

```text
root
C:/UDEV/RookEvidence/2026-08-20-qwen38-multimodal-vessel-massing-v4

global entries             67/67
global manifest SHA-256    04AB6BC227D0DBD9E1ABFA7A58D80DCB553E5DCDE752EDD83650E8A77759F23C
row entries                40/40
row manifest SHA-256       2A8CF7356A54CC2637342699EFC2503D004C6CDA53F57B6716C73E0B7B492602
mismatches                 0
```

Key retained hashes:

| Artifact | SHA-256 |
|---|---|
| Protocol | `225C8D8689755C0C120BD3430B8A9D628407C19415B45BC6B094C37D23B65BA4` |
| Source log | `6F0D37AC9287377451259CA63DA9130DA0D8CCFF612C7E0C4DA95534DEB8899A` |
| Process result | `032D3A6E7320338F3FB8526F306AA5259858660C84D11DF392998A11E9FA6033` |
| Source closure | `8E4B0F779F40FD4C05ECCFCF18DC3366433BA5755C7903BACE4223558A95660A` |
| Actor final checkpoint | `EFEDC3A1B366826B4C76ABF01C18AE195969E631A0A74311FB773344758B2E6E` |
| Attachment audit | `672219BFBD433ED186F0DD40CD117B970D02C7BBAE781BED5A47D9E35D5F64D1` |
| Outcome | `D24ED34B1283B34A273A1D93B456654C446C229986F0097924D3A2C046717808` |

## Disposition

V4 is credible architectural evidence and a lifecycle/custody pass, but it is not
a final-checkpoint qualification. Preserve it unchanged. One confirmation is
justified with the same architectural brief and runtime, the exact viewport
classifier correction, and an explicit instruction that the fenced snapshot is
the last Rook call: no later diagnostics, viewport, status, or other gateway
activity before `goal.complete()`.
