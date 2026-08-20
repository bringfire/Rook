# Qwen3.8 Multimodal Vessel Massing V2 Execution

**Date:** 2026-08-20
**Disposition:** `partial_success - lifecycle qualified, architectural result incomplete`
**Executions:** One V2 transaction; zero V2 retries

## Result

The V2 transaction completed naturally. Qwen received both retained reference
images in order, created a working adjustable Grasshopper definition, repaired
its own script and control defects, exercised the two requested controls,
restored the defaults, obtained final receipt-fenced evidence, called
`goal.complete()`, and emitted text only.

The resulting definition is mechanically healthy but is not accepted as the
intended Vessel massing. It contains eight largely full polygonal slabs and
seven alternating stair solids. Independent viewport inspection found no
visible clear central void, and the overall result is much sparser and less
flared than the references.

This is partly a Qwen implementation miss and partly a brief-design failure.
The frozen prompt explicitly requested full annular platforms and exactly one
flight between adjacent levels. That topology directed Qwen away from the
reference's denser circulation lattice.

## Custody And Lifecycle

The retained transaction reports:

```text
Prime exit code             0
elapsed time                1,331.875 seconds
provider input tokens       2,094,375
provider output tokens         70,619
provider total tokens       2,164,994
gateway events                     64
goal status                 complete
budget status               pass
custody status              pass
owned child PIDs            0
```

The ordered attachment audit passed for both converted JPEGs. Qwen's opening
reasoning distinguished Image 1 as exterior massing and Image 2 as circulation
and identified the faceted, stacked, twisting character before authoring.

All 64 retained source events used the canonical gateway. The source log closed
with one `agent_end`. No model, Prime, Ollama, or campaign-owned process remained
after sealing.

## Authoring Behavior

Qwen created one Python 3 script component and six connected sliders:

```text
Levels             8
LevelHeight        6
BaseRadius         12
WalkwayWidth       4
TwistPerLevel      12
StairWidth         2.5
```

It recovered from three material problems using live evidence:

1. The initial script used an invalid RhinoCommon `CrossProduct` overload.
2. Its first control implementation read RhinoCode pins through `globals()`, so
   slider changes did not affect outputs despite clean diagnostics.
3. One source update contained a syntax error.

Qwen repaired each issue locally without deleting the graph or changing lanes.
The final definition contained seven components, six wires, zero errors, and
zero warnings.

Receipt-fenced observations established these control effects:

| Control state | Platforms | Stairs | Readout |
|---|---:|---:|---|
| Defaults: Levels 8, Twist 12 | 8 | 7 | `8, 7, 84, 42` |
| Levels 5 | 5 | 4 | `5, 4, 48, 24` |
| Levels 12 | 12 | 11 | `12, 11, 132, 66` |
| Twist 0 | 8 | 7 | `8, 7, 0, 42` |
| Twist 30 | 8 | 7 | `8, 7, 210, 42` |
| Restored defaults | 8 | 7 | `8, 7, 84, 42` |

## Final Checkpoint Correction

The sealed campaign artifact reports `later_gateway_call` because the runner
selected the first valid wait/snapshot pair after the final mutation. Qwen then
repeated that same receipt checkpoint more completely immediately before
completion. The retained source order is:

```text
59  restore TwistPerLevel to 12; receipt 550a73d4...
60  wait for receipt 550a73d4... -> ready
61  receipt-fenced snapshot
62  final wait for the same receipt -> ready
63  final receipt-fenced snapshot
end goal.complete(), agent_end, no later gateway call
```

A test-first runner correction now selects the latest valid repeated checkpoint.
Offline derivation from the untouched source trace returns:

```text
status             pass
mutation sequence  59
wait sequence      62
snapshot sequence  63
receipt            550a73d4a1dd5035b2f7edd9935fd63d
```

The original sealed artifact and manifest remain unchanged. This is a runner
bookkeeping correction, not a retroactive change to Qwen's behavior.

## Architectural Review

The final script attempted each platform as an outer prism minus an inner
prism, but caught every Boolean exception and silently returned the outer prism.
The independent top viewport showed a filled center. A nonempty Brep list and
clean diagnostics therefore did not establish the requested central void.

The larger mismatch came from the brief itself. The references read more
credibly as a flared six-sided circulation lattice: discrete landings and
walkway strips, an atrium that expands upward, alternating tier stagger, and
many crisscrossing stair ribbons. Full slabs plus one flight per level cannot
produce that density. V2 consequently should not be used to conclude that Qwen
could not understand the images; it followed an overconstrained, partly wrong
verbal specification.

The next attempt should supply the corrected architectural invariants without
supplying equations, source code, exact graph topology, or a solved algorithm.
Qwen should remain responsible for implementation and completion judgment.

## Evidence

Sealed campaign root:

```text
C:/UDEV/RookEvidence/2026-08-19-qwen38-multimodal-vessel-massing-v2
```

```text
global manifest entries    68/68
global manifest SHA-256    1A1EE6857B126EEE7EA125BF508BB86D08414E6E590892862C19EF269F19E328
row manifest entries       41/41
row manifest SHA-256       FDDC4DD416C0948F3773FF681ACEDE898330059DB88745A4B25826211F183B66
mismatches                 0
```

Independent post-run review root:

```text
C:/UDEV/RookEvidence/2026-08-19-qwen38-multimodal-vessel-massing-v2-postreview
```

```text
post-review manifest SHA-256  B2247D366DB18458BC1AB6F938BD600109EF0B56DC31824203758AF41991B07C
```

Key retained hashes:

| Artifact | SHA-256 |
|---|---|
| Authoring trace | `4DC3825E04C655676B0ABA10B9FB8CAF2EEA10068FF545447468E36A6C111352` |
| Source log | `C6120FB428ADD36C01067FF47C2CDF310D416F20D7E3B2101FD6AA66208F205B` |
| Process result | `60B3EDAAC2C45EBB378FB58D9A7CC805DE4ED2A402CE217A6447084ED60FC84F` |
| Hidden final observation | `D575BD2E2F8869F2A0FABA3FAE4C04F0C775599856668CC2368827CBF660EF99` |
| Derived final checkpoint | `5775B5DE5319629D925658475AF3DCADD8008647C4BF12D6805A78977F2189E1` |

## Disposition

V2 qualifies multimodal delivery, the Python authoring loop, local recovery,
control causality, exact restoration, final receipt custody, budget custody,
and self-termination for this specimen. It does not qualify the architectural
result.

Preserve V2 unchanged. A fresh attempt is justified with a corrected brief and
explicit model-visible viewport inspection before the final checkpoint. No
supervisor, deterministic semantic vocabulary, Prime change, Rook change, or
automatic repair mechanism is justified.
