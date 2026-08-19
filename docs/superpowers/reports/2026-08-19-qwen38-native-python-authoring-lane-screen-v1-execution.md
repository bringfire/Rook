# Qwen3.8 Native/Python Authoring-Lane Screen V1

**Date:** 2026-08-19
**Status:** Complete execution; one partial and one credible shadow success
**Live rows:** Two, ordered `N -> P`
**Reruns:** None

## Question

Does assigning Qwen3.8 an explicit Grasshopper authoring lane before discovery
reduce orientation churn while preserving the model-led empirical loop?

Both rows received the same task on separate fresh empty canvases:

> Create an adjustable circular array of vertical line segments. Expose Radius,
> Count, Height, and Start Angle. Produce exactly Count evenly spaced vertical
> lines around the circle. Exercise Count and Height, observe the effects,
> restore defaults, obtain a final receipt-fenced observation, and stop when
> satisfied.

Row `N` admitted native Grasshopper components. Row `P` admitted one Python
script component plus ordinary controls. The restrictions were skill guidance
over the unchanged full Rook surface, not mechanical capability hiding.

This is a paired product screen, not pure causal proof. The row fixtures differ
by design, the row order was fixed rather than randomized, and each stochastic
condition was sampled once. Evaluators remained silent until both Actors ended.

## Result

Both rows completed naturally. Row `N` is independently judged
`partial_success`; row `P` is judged `credible_success`:

| Observation | Native `N` | Python `P` |
|---|---:|---:|
| Prime exit | 0 | 0 |
| Goal status | `complete` | `complete` |
| Formal semantic status | `unproven` | `unproven` |
| Shadow disposition | `partial_success` | `credible_success` |
| Actor final checkpoint | pass | pass |
| Budget / custody | pass / pass | pass / pass |
| Elapsed time | 723.703 s | 240.875 s |
| Gateway calls | 42 | 19 |
| Discovery calls | 21 | 7 |
| Mutations / commits | 5 / 5 | 5 / 5 |
| Input tokens | 1,432,131 | 461,393 |
| Output tokens | 47,513 | 15,792 |
| Provider tokens | 1,479,644 | 477,185 |
| Final components / wires | 19 / 23 | 7 / 6 |
| Final errors / warnings | 0 / 0 | 0 / 0 |

The formal semantic result remains `unproven: independent_judgment_required`
by design. That status is not an infrastructure failure.

Operationally, row `P` used 33% of row `N`'s time, 32% of its provider tokens,
45% of its gateway calls, and one third of its discovery calls. Those are
observed differences in this pair, not a general authoring-lane ranking.

## Native Row

### Final state

The final receipt-fenced snapshot observed:

```text
Radius       5
Count       12
Height       3
StartAngle   0

19 components
23 wires
12 line outputs
0 errors
0 warnings
```

The final point projections contained 12 complete base points at `Z=0` and 12
matching top points at `Z=3`. The first three XY positions were approximately:

```text
(5.0000, 0.0000)
(4.3302, 2.4999)
(2.5001, 4.3300)
```

They support radius 5 and approximately 30-degree spacing. The native graph
uses Series, arithmetic, sine/cosine, two Construct Point components, and Line.
Start Angle enters the trigonometric angle path through a degree-to-radian
conversion.

### Empirical repair

Qwen's initial graph fed degrees directly into Grasshopper sine and cosine. The
first solved line was correct, but the second appeared at approximately
`(0.7713, -4.9402)` instead of the expected 30-degree position. Qwen identified
the radians mismatch from live output and made a local conversion repair.

That repair exposed slider rounding in the `PI/180` constant. Qwen again used
the observed coordinates, identified the remaining phase/spacing error, and
replaced only the affected angular subgraph with:

```text
Series / Count * 2pi + StartAngle * PI/180
```

The unaffected controls, point construction, and line construction were
preserved. The subsequent snapshot showed the expected circular positions at
the default zero phase.
This is evidence of two bounded local repairs driven by named live failures,
not an implementation-mode switch or an unsupported wholesale reset.

### Control exercise and stopping

Qwen changed Count and Height together from `12 / 3` to `24 / 8`. The observed
line count became 24, the second line moved to the expected approximately
15-degree position, and every previewed line extended from `Z=0` to `Z=8`.
It restored `12 / 3`, waited on receipt
`dead87ab3cf441759088d09516739988`, and took the final fenced snapshot as source
sequence 41. It then called `goal.complete()` with no later gateway event.

The prompt did not require independent perturbations, but the combined probe
does not isolate Count and Height causality as strongly as row `P`'s two probes.

### Native shadow judgment

Observed:

- Count was 12 and the final Line output count was 12.
- Complete base/top point collections shared XY coordinates and differed by
  exactly 3 in Z.
- The projected points formed a credible radius-5, evenly spaced circular
  sequence.
- Count 24 and Height 8 produced 24 taller lines; restoration returned the
  output to 12 lines of height 3.
- Every gateway event remained in the native lane.
- Final receipt custody, clean diagnostics, and stopping all passed.

Inferred:

- The approximate `6.283` constant implements the circular step closely enough
  for the default output to form a credible evenly spaced array.
- Start Angle is causally connected to phase from the solved native topology;
  it was not separately perturbed.

Unresolved:

- The combined Count/Height probe is less isolating than two independent probes.

Observed defect:

- Qwen explicitly established that the intended `PI/180` slider had rounded to
  `0.017`, then retained it for Start Angle conversion. Under Qwen's declared
  degree interpretation, a 90-degree setting would produce approximately
  87.7 degrees and a 360-degree setting approximately 350.7 degrees. The
  default zero phase hides this scale error.

Disposition: **`partial_success`**. The default circular array, Count, Height,
repair behavior, custody, and stopping succeeded, but the exposed Start Angle
control retained a known material scaling defect.

## Python Row

### Final state

The final receipt-fenced snapshot observed:

```text
Radius       5
Count       24
Height      10
StartAngle   0

7 components
6 wires
24 LineCurve outputs
NumLines     24
LineLength   10
0 errors
0 warnings
```

The Python component source constructs one line for each integer in
`range(Count)`, uses `360 / Count` angular steps from Start Angle, places base
points at radius `(cos(angle), sin(angle))` on `Z=0`, and places matching top
points at `Z=Height`.

### Control exercise and stopping

Qwen tested the controls independently:

1. Count changed from 24 to 12. `Lines` and `NumLines` both changed to 12 while
   `LineLength` remained 10.
2. Height changed from 10 to 25. `LineLength` changed to 25 while line count
   remained 12.
3. Count and Height were restored to 24 and 10.

It waited on receipt `7b5cc2928f497780d0b647514b617e41`, inspected the final
fenced snapshot at source sequence 18, and called `goal.complete()` with no
later gateway event.

### Python shadow judgment

Observed:

- The final control values and wiring were complete and clean.
- The solved script output contained 24 `Rhino.Geometry.LineCurve` objects,
  `NumLines=24`, and `LineLength=10`.
- Count and Height caused the expected independent output changes and were
  restored.
- The retained source implements the requested circular spacing, phase, and
  vertical endpoints directly.
- Every gateway event remained in the Python lane. No native component-library
  discovery or C# route appeared.
- Final receipt custody and stopping passed.

Inferred:

- Correlating the retained source with the solved LineCurve count, length, and
  clean diagnostics supports a credible circular array of vertical lines.

Unresolved:

- The snapshot projected LineCurve runtime types, count, and length but not
  endpoint coordinates. Circular spacing and verticality therefore rely on
  source-plus-solved-output correlation rather than direct host coordinate
  projection.
- Radius and Start Angle were not separately perturbed.

Disposition: **`credible_success`**.

## Predeclared Efficiency Criteria

| Criterion | Native `N` | Python `P` |
|---|---|---|
| Credible result or honest failure | `partial_success` | `credible_success` |
| Budget and custody | pass | pass |
| Count and Height exercised/restored | pass; combined perturbation | pass; independent perturbations |
| Final fenced snapshot before completion | pass | pass |
| Later gateway call | none | none |
| Search for listed capability names | none | none |
| Implementation-mode switch | none | none |
| First commit within 12 gateway calls | fail; source sequence 22 | pass; source sequence 8 |
| First commit within 200,000 tokens | fail; 213,300 | pass; 119,475 |
| Equivalent repeated mutation without reason | none observed | none observed |
| Semantic/evidence quality | known Start Angle scaling defect | credible result; spatial evidence is less direct |

The token boundary is frozen and evidence-cited:

- Native first commit: `gh_edit` source sequence 22, emitted by Actor turn 11.
  That turn used 41,484 tokens and brought cumulative provider use through the
  turn to 213,300.
- Python first commit: `gh_create_script` source sequence 8, emitted by Actor
  turn 10. That turn used 19,918 tokens and brought cumulative provider use
  through the turn to 119,475.

Both mappings are unique rather than `unproven`.

Neither row searched for a skill-listed capability name. Row `N` directly read
six contracts, then used 13 component-library searches and two batched metadata
requests. Row `P` directly read seven contracts and made no component-library
or metadata request.

## Interpretation

The pair supports four bounded conclusions:

1. Both explicit lanes preserved the simple model-led empirical loop. The
   native lane produced a healthy default definition with one known control
   defect; the Python lane produced a credible complete result.
2. Qwen used authentic solved evidence to repair two local native-graph defects
   without changing lanes or discarding the whole definition.
3. The Python lane exhibited much earlier commitment and materially lower call,
   token, and wall-clock cost on this task.
4. The Python lane's final spatial evidence was less direct than the native
   point projection, but its retained source and solved outputs support credible
   success without the native phase defect. This pair still cannot qualify a
   general efficiency or semantic superiority claim.

Do not promote either fixture or change the canonical product skill from this
pair. Do not add a supervisor, semantic acceptance vocabulary, cache, or Prime
mechanism. The smallest justified next experiment is one varied Python-lane
confirmation using the exact Python fixture and operational configuration on a
different compact geometry family. C# remains a later comparison.

## Custody

The exact execution command was:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger/scripts/qwen38_self_termination_campaign_runner.py run `
  --protocol C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger/docs/superpowers/experiments/2026-08-19-qwen38-native-python-authoring-lane-screen-v1.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-19-qwen38-native-python-authoring-lane-screen-v1 `
  --document-serial 268435457
```

- Frozen pre-contact package: `1cf03030eed80b977e2ee56888a067e96e98c191`.
- Reviewed correction: `8a22a4f3086a3015d2efbc561acd9b7c7ab95f28`.
- Pre-contact verification: **205 passed**, 11 existing warnings.
- Post-run verification: **205 passed**, 11 existing warnings; Python
  compilation and frozen JSON parsing passed.
- Global evidence: **86/86** independently reverified.
- Native row evidence: **35/35** independently reverified.
- Python row evidence: **34/34** independently reverified.
- Global manifest SHA-256:
  `9A9E7E26CADF3E96ED664ED3E84EE2B0D13A4D0B855245C03518EDAF0AB1A1EE`.
- Native row manifest SHA-256:
  `CDBE383D88D33863EE059F8A3BAAC7B63F108EC63C1AD5940099527B637BAFD6`.
- Python row manifest SHA-256:
  `FF5195706FE3EE97AE601102CD4DCECAC9FEE892B9CA68FEFAAD44B0C66E4CC8`.
- Protocol SHA-256:
  `D75537826C764A254928279420AEA045FB8AFBD9F60BDBE692A0B8A506CDEFB6`.
- Stderr was empty for both rows.
- Both rows ended with zero owned child processes.

Evidence root:
[qwen38-native-python-authoring-lane-screen-v1](C:/UDEV/RookEvidence/2026-08-19-qwen38-native-python-authoring-lane-screen-v1)
