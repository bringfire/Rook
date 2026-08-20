# Qwen3.8 Multimodal Vessel Massing V5 Execution

**Date:** 2026-08-20
**Disposition:** `credible_success - Actor checkpoint passed; shadow trace normalization incomplete`
**Executions:** One V5 Actor transaction; zero V5 Actor retries

## Result

Qwen received both reference images in order and produced an adjustable,
flared, six-sided circulation lattice. The final definition has six separate
landing pads per tier, narrow horizontal connectors, an open central atrium,
and a dense set of diagonal stair ribbons between alternating tier states. It
does not fall back to stacked floor plates, continuous skins, or the side-wide
panels seen in V3.

The Actor completed naturally with `goal.complete()`. Goal, budget, process,
model, attachment, target, and final-checkpoint custody passed. The final
same-receipt fenced snapshot was the last Rook gateway call.

The campaign-time hidden evaluator remains honestly `incomplete`. Prime
performed one successful threshold compaction and continued the active goal,
but the frozen acceptance owner admits only one `agent_end`. The retained Prime
runtime therefore contains two authentic run boundaries and is refused as
`invalid_prime_terminal_marker` before semantic evaluation. This is a
Prime-compaction trace-admission compatibility gap, not an ambiguity in the
final Grasshopper mutation or checkpoint. No Qwen or Grasshopper failure was
observed; semantic evaluation did not run, so neither was formally ruled out.

## Operational Result

```text
Prime exit code                    0
Actor elapsed time        1,351.391 seconds
provider total tokens      1,789,878
gateway events                    40
goal status                 complete
budget status               pass
custody status              pass
Actor checkpoint            pass
owned child PIDs                   0
```

All 40 source events used the canonical gateway. Both reference images were
attached before the first Rook call. Qwen stayed in the explicitly selected
Python authoring lane. It made eight discovery calls and committed its initial
script at source sequence 9.

Two late calls used incorrect argument names:

```text
36  gh_wait_for_solve_readiness(receipt_id=...)       refused pre-dispatch
38  gh_snapshot(readiness_receipt=...)                refused pre-dispatch
```

Qwen read each diagnostic, corrected the argument, and continued. Neither
refusal mutated the canvas.

## Final Definition

The final fenced snapshot observed:

```text
components                       8
wires                            7
Python output Breps            180
errors                           0
warnings                         0

Levels                           8
Level Height                     4
Base Radius                     10
Top Radius                      16
Walkway Depth                  0.6
Tier Stagger Angle              30
Stair Width                    1.2
```

The retained Python source supports this decomposition:

```text
landing pads        6 x 8 tiers                         48
walkway connectors  6 x 8 tiers                         48
stair ribbons       12 x 7 adjacent-tier intervals      84
total                                                    180
```

The source alternates tier angle between `0` and `Tier Stagger Angle`, linearly
interpolates outer radius from Base Radius to Top Radius, and keeps the inner
radius at one-half the outer radius. Each lower landing connects to the two
nearest upper-tier landings, yielding the visible crossing stair field.

Qwen refined Walkway Depth from `1.5` to `0.6` while inspecting the massing. It
then exercised the required controls independently:

```text
Levels              8 -> 5 -> 8
Tier Stagger Angle 30 -> 10 -> 30
```

The final restoration produced receipt:

```text
78e858015aeb627e69d4fe569cbaf37f
```

The closing source order was:

```text
33  restore Tier Stagger Angle to 30; terminal receipt
34  final Perspective viewport
35  final Top viewport
36  invalid wait arguments; refused before dispatch
37  wait for terminal receipt -> ready
38  invalid snapshot arguments; refused before dispatch
39  same-receipt fenced snapshot                       <- final gateway call
end goal.complete(), text only, final agent_end
```

The actor-final-checkpoint owner selected mutation 33, wait 37, and snapshot 39
with no later gateway event.

## Visual Judgment

The final Top capture shows a large open center and alternating sets of six
radial pads. The intervening geometry is visibly narrower than the pads. The
Perspective capture shows the narrow-to-wide flare, stacked landings, and a
dense field of separate inclined ribbons rather than enclosing surfaces.

The result is schematic and visually busy. The red wire display makes the
circulation hierarchy harder to read than a shaded architectural rendering,
and no claim is made that this is a literal reconstruction, code-compliant
stair design, or proven multi-route circulation graph. The supported claim is
that Qwen used the images and architectural brief to produce a credible
conceptual circulation lattice while avoiding the exact V3 failure modes.

The final captures were copied from their source-referenced viewport paths into
the durable evidence root before the manifests were regenerated:

```text
MV1/operator/final-perspective.png
MV1/operator/final-top.png
```

## Prime Compaction Boundary

The 3.54 GB Prime runtime contains this authentic lifecycle:

```text
agent_start
... Actor work ...
agent_end
compaction_start(reason=threshold)
IPython state retention
compaction_end(success; willRetry=false)
agent_start
... continued Actor work and completion ...
agent_end
quiescent session_action_update
```

The current acceptance function requires exactly one `agent_end`; it was
written before this upstream Prime continuation shape was exercised live. A
minimal regression for the observed sequence failed for exactly that reason.
An exploratory local correction admitted the sequence, but changing the shared
module invalidated the byte custody of 15 historical protocol tests. No such
change is retained in this commit or evidence.

The appropriate later correction is a separately versioned, fail-closed
compaction-continuation admission contract. It is not required to establish the
already-retained Actor checkpoint, and it should not be smuggled into this
campaign by rewriting historical hashes.

## Evidence

```text
root
C:/UDEV/RookEvidence/2026-08-20-qwen38-multimodal-vessel-massing-v5

global entries             66/66
global manifest SHA-256    7BDD42FE284CDCF34AE101CE5550E9A1B5B7742A90F0437B5735C3FB5F67259D
row entries                39/39
row manifest SHA-256       FCD5205D361C1772ADB8C266CB33A9490F4679697CE28DE3B7D75636065B13A4
mismatches                 0
```

Key retained hashes:

| Artifact | SHA-256 |
|---|---|
| Protocol | `4D6FBBBF7329189FAC4A48C5DC28603D33B2248AE489503D549336059190DB2D` |
| Runner | `F18E0FFC3C86B6CF0A93F356EB714FCA188BCCCAD5FFA3D81635514F81CC1B14` |
| Source log | `E86FDB1F88B1357F8811F3FC8F3DDBEC078C4949B873615E0CE1D98A98B966C8` |
| Prime runtime | `F79FF8A329993C9770B7E103B3F10620A6E118C5AD58E6184E9777EDFBFCAA3B` |
| Process result | `4920BA546D4FFF73C1C8DDEB8887E5C1CABA3762A5775C75C516683D54342F70` |
| Actor final checkpoint | `CD45C4990CE59EDE623D92F41F462897FDB70CDBB9DE3230E6E626688F8D2365` |
| Attachment audit | `97C43510AAA4B2E1667FB58015582E4F58C316FCCE7E1550114C59577F1D3B98` |
| Outcome | `893DB7A5859462F0519B6A4F826FE05987DD8C3690375CA9305F2F372B038DD4` |
| Final Perspective | `CC72F31E7FD293BF8AC9EFA1E225F4102C785204F123C419F6727F9AD85A6CB3` |
| Final Top | `9D5D99225F0E29DC8CA1315261FFE6E1FC98BC2993B24E45158565FFEB58E5EC` |

## Disposition

V5 is credible multimodal product evidence and a qualified Actor final-checkpoint
pass. It is not a formal shadow semantic pass because the frozen trace owner
cannot yet admit upstream Prime's successful compaction continuation.

Do not rerun this Vessel task. Preserve the specimen, carry the successful
Python-lane and receipt-fenced stopping behavior forward, and handle Prime
compaction admission as a separate compatibility correction with versioned
custody.
