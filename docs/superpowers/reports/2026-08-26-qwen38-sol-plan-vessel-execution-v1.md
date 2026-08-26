# Qwen3.8 Sol-Plan Vessel Execution V1

**Date:** 2026-08-26
**Disposition:** `partial_success - mixed handoff and final checkpoint passed; semantic defects remain`
**Actor executions:** One; zero retries or external steering
**Target:** Rhino document `268435457`, fresh empty Grasshopper canvas

## Result

This run tested a narrow mixed-intelligence relay. Qwen received the two Vessel
reference images plus the exact sealed GPT-5.6 Sol design baseline and topology
refinement. Sol did not participate in the live run. Qwen independently owned
Grasshopper authoring, repair, control tests, visual inspection, restoration,
and completion inside Prime.

The relay worked operationally. Qwen read the supplied design artifacts, stayed
in the explicit Python lane, built a substantial adjustable definition, repaired
authentic script failures, exercised three consequential controls, restored its
defaults, obtained a same-receipt fenced final snapshot, and called
`goal.complete()` with no later Rook gateway event.

The geometry is not a clean semantic pass. The final model contains an open
atrium, six landing pads per tier, explicit walkway solids, a flared envelope,
and eight stair flights per lift in both angular directions. However, Qwen's
claimed route verification is unsound: its route construction inserts some
horizontal pad-to-pad chords for which no matching walkway solid was created.
The retained report also identifies the top two stair lifts at approximately
42 and 39 degrees, outside the 25–35 degree design target in the supplied Sol
strategy. Qwen saw those values and still declared the result complete.

The appropriate classification is therefore partial success. The experiment
supports the Sol-plan-to-Qwen-execution mechanism, but it also shows that a
strong supplied plan does not remove the need for Qwen to reason correctly
about its own implementation and evidence.

## Operational Result

```text
Prime commit                    739400844f8f3f280414b0c7b9c65797208815d3
Actor                           ollama_chat/qwen3.8:27b, low thinking
Sol live participation          none
Actor transactions              1
Actor retries                   0
Prime exit code                 0
elapsed time                    1,406.453 seconds
gateway events                  62
committed mutations             12
mutation calls                  13
discovery calls                 10
provider-reported total         3,794,529 tokens
Prime goal usage                3,681,359 / 9,500,000 tokens
goal status                     complete
budget status                   pass
custody status                  pass
Actor final checkpoint          pass
compact capture status          pass
owned child PIDs                0
```

The runner verified the exact goal context and `low` thinking level. The
pre-contact gate verified Prime, the installed goal bridge, branch-local
`rlm`, `rook_full`, Qwen model blobs, current Ollama `0.32.15`, both image
attachments, GPU capacity, compaction continuation, and the sealed kernel.

The compact Prime event stream is 24,110,326 bytes. This confirms that the
opt-in compact capture avoided the historical multi-gigabyte cumulative-event
retention pattern for this run. It is a storage result, not a claim about the
model's context size or semantic performance.

## Handoff Custody

The model-facing task named the two sealed Sol artifacts directly:

```text
C:/UDEV/RookEvidence/2026-08-20-gpt56-sol-vessel-design-baseline-v2/operator/stdout.txt
C:/UDEV/RookEvidence/2026-08-20-gpt56-sol-vessel-topology-refinement-v1/operator/stdout.txt
```

Their frozen hashes remained:

```text
design baseline answer          00A074E2...2D66D8A
topology refinement answer      133DC8BA...4A6F3FC
```

The task explicitly made the topology refinement authoritative where the two
documents differed. No detailed topology was invented by the experiment
runner, and no Sol or Codex correction was supplied after Qwen began.

Both source images were attached before the first Rook call. The attachment
audit passed and retained two image blocks in the Prime session.

## Authoring Loop

Qwen made ten discovery calls and committed its first Python script at source
sequence 11. It kept the same component and repaired locally rather than
resetting the canvas. The retained session describes three concrete
RhinoCommon/script corrections:

```text
close the planar profile polyline
use MeshFaceList.AddFace rather than Add
convert the manifold mesh with Brep.CreateFromMesh
```

The final canvas has one Python component and nine connected sliders:

```text
TierCount       8
Spacing         3.5
BaseRadius      5.5
TopRadius       9.5
PadDepth        1.6
WalkwayWidth    1.4
Stagger         1
StairWidth      1.8
Stairs          8
```

The final receipt-fenced snapshot reports:

```text
components                     10
wires                           9
landing-pad Breps              48
walkway Breps                  24
stair-tread Breps           1,120
route curves                    1
errors                          0
warnings                        0
```

Qwen exercised and observed:

```text
TierCount       8 -> 12 -> 8
TopRadius     9.5 -> 14 -> 9.5
Stagger         1 -> 2 -> 1
```

One stale-epoch control mutation was refused without committing. Qwen obtained
a fresh snapshot and retried successfully. A `gh_errors` call also failed with
an infrastructure exception; Qwen continued from subsequent authentic
snapshots and diagnostics.

## Final Checkpoint

The closing source sequence is:

```text
57  restore TierCount, TopRadius, and Stagger; terminal receipt
58  wait for receipt bba6b671656898f43ee26c3a73fa6480 -> ready
59  final Top viewport capture
60  final Perspective viewport capture
61  same-receipt fenced gh_snapshot                    <- final Rook call
end goal.complete(), then text only
```

The actor-final-checkpoint owner selected mutation 57, wait 58, and snapshot 61.
The snapshot is bound to document session
`6cef493dc9acec0838a49cb670d58842`, mutation epoch 12, and solution run epoch
29. No Rook gateway event followed it.

Qwen did not pass the final restored Top and Perspective captures through
`attach_image`. It did attach and inspect earlier Top, Perspective, and Front
captures before the last source cleanup and default restoration. Therefore the
run qualifies final structural receipt custody, but not model inspection of the
exact final restored viewport images.

## Independent Visual Review

The retained session includes model-visible intermediate views. The final
viewport paths remained available for independent post-run inspection.

The Top view shows a large open center, a strong six-fold radial pattern, and
no filled floor plate. The Front view shows a narrow base, broad top, and a
dense recurring X/chevron field. These are materially closer to the supplied
Vessel strategy than a helix or stacked annular slabs.

The result remains schematic and visually congested. The final Perspective
capture is poorly framed at a very small scale, and the red selected display
obscures landing/stair hierarchy. This evidence supports a flared circulation
lattice, not architectural fidelity, code-compliant stairs, or a finished
Vessel reconstruction.

## Semantic Defects

### Route proof

The script creates only three walkway connections per tier:

```text
phi -> phi+2
phi+2 -> phi+4
phi+4 -> phi+6
```

Its route builder can instead choose a horizontal transfer such as `11 -> 9`
on a tier whose actual walkways are `1 -> 3`, `3 -> 5`, and `5 -> 7`. The route
curve then contains a horizontal edge unsupported by walkway geometry while
the report labels it `verified on pads+walkways+flights`.

Because every lower-tier pad emits a flight, a stair-only ground-to-top chain
may still exist. That possibility was not independently traversed in this
campaign. The retained `Route` object is not valid proof of the required
walkable path.

### Stair feasibility

The final script report records:

```text
lifts 0..4       approximately 20–27 degrees
lift 5           approximately 42 degrees
lift 6           approximately 39 degrees
```

The upper lifts are materially steeper than the supplied 25–35 degree design
target. Qwen disclosed the values but did not treat them as a completion
blocker.

### Walkway distribution

The three walkway strips occupy three consecutive sector connections rather
than an alternating or balanced set around all six pads. This leaves real open
gaps but creates an uneven horizontal circulation pattern. No claim of
multi-route connectivity is supported.

## Frozen Evaluator Boundary

The campaign-time hidden evaluator returned:

```text
status   unproven
reason   authoring_trace_invalid
```

Semantic probing did not run. The frozen trace owner treats successful
`rhino_viewport` events as unknown mutation classifications and also retained
one failed `gh_errors` event as unknown. This is an evaluator-admission
limitation. It does not invalidate the independently selected terminal receipt
or Actor checkpoint, and it cannot be rewritten after contact to manufacture a
semantic pass.

## Interpretation

This specimen supports four bounded conclusions:

1. A sealed frontier-model design artifact can be handed to local Qwen as a
   useful planning input without a hierarchical live supervisor.
2. Qwen can execute that plan through a long empirical Grasshopper loop,
   including local repair, control probes, visual observation, restoration,
   and disciplined completion.
3. The Sol handoff materially constrained the result toward discrete pads,
   explicit walkways, dense two-directional stairs, flare, and an open atrium.
4. Qwen still made consequential implementation-judgment errors that the plan
   did not prevent: an invalid route proof and knowingly steep upper flights.

This is positive evidence for a peer relay, not proof that the local executor
can faithfully realize every strong plan. It also does not establish causality
against the earlier Qwen Vessel specimens because the prompt, runtime custody,
capture mode, and generated implementation differ.

No supervisor, semantic acceptance vocabulary, subagent hierarchy, or
mid-run frontier-model correction was added. No retry is justified from this
single specimen. The next decision should concern how much implementation
structure the planning artifact must make explicit, not another harness layer.

## Evidence

```text
root
C:/UDEV/RookEvidence/2026-08-26-qwen38-sol-plan-vessel-execution-v1

global entries             65/65
global manifest SHA-256    42562D88C382E1F46BDA5204C95679EF0E0466DBC5317B41943949F82D893E2C
row manifest SHA-256       E10789D7E13E4EFD94A5BE03A98CF669C78568D6731C003188A94BEA59F0868A
mismatches                 0
```

Key retained hashes:

| Artifact | SHA-256 |
|---|---|
| Protocol | `04C53FED0F9E5F4B4764182A6ADA09DAE9F61D1D7850401CC9C8920DDCB80F30` |
| Runner | `8E9D1C8DE74E1745E85296C6A1B0AC43C0818F4B51D3703BA44B203C3A81B7E8` |
| Source log | `61233C016AC3BF4148F73002AC31ED9867A59FA8DD5AD824024543D96CEFD62A` |
| Durable Prime session | `469340F9EB1A966C210087432332D979E381EAC27BD838CC88C9775BCCEB644B` |
| Compact Prime event stream | `A59218DC767CBB01734E5F30982E5691581020D853E7E398C80B8B9DD3A7ED1C` |
| Process result | `83CE98F809D5DFFF79E83EA67D95946654013E818E8792BE29EE4F838C7DCDEE` |
| Actor final checkpoint | `7E8765FB3AD388BFF7A0FC6C0FA5DD39C381F3C92125C8B452914D6EC3C1B98C` |
| Attachment audit | `8FFF5C2E0F553680953CF18D367CCC8C5B62354B27785296E6B2C95E97A0B121` |
| Outcome | `6384866C755BD2CD9B4198F2FC04951B0EBC0559E09A3876A5E49CE89D3A5C98` |

## Disposition

V1 is durably retained as one authentic mixed Sol-plan/Qwen-execution partial
success. The handoff, empirical authoring loop, compact capture, and final
checkpoint worked. The route proof and upper stair feasibility did not meet the
supplied design standard, and the exact final viewport state was not inspected
by Qwen. Do not call this a semantic Vessel pass.
