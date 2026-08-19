# Qwen3.8 VP1 Prospective Efficiency Screen V1

**Date:** 2026-08-19
**Status:** Complete execution; credible shadow success
**Live rows:** One
**Reruns:** None

## Question

Can Qwen3.8 complete one smaller varied Grasshopper product task under a narrow
experimental discovery rule while preserving the existing model-led empirical
loop?

This was a prospective screening and generalization specimen. It was not a
causal prompt comparison because both the task and versioned skill differed from
the immediately preceding VP2 run. The evaluator remained silent until the Actor
terminated.

The frozen rule was:

> Tool names listed in this skill are already known. Read each required contract
> directly once; do not search for a known tool name. After `gh_edit` and one
> viable authoring contract are known, choose an implementation mode and create
> the smallest working scaffold. Further discovery must name the exact unresolved
> fact required by the next intended mutation, for example a component identity,
> parameter index, or required tool argument, and stop once that fact is resolved.

Prime's goal budget was **1,900,000 tokens** inside the runner's **2,000,000
provider-token ceiling**, reserving 100,000 tokens for completion and final
response cost.

## Result

The single row completed naturally:

```text
Prime exit:                    0
source closure:                agent_end
goal status:                   complete
actor final checkpoint:       pass
budget:                        pass
custody:                       pass
seed preservation:             pass
hidden semantic evaluation:   unproven (independent judgment required)
shadow disposition:            credible_success
```

Operational telemetry:

| Observation | Value |
|---|---:|
| Elapsed time | 186.953 seconds |
| Gateway calls | 11 |
| Discovery calls | 7 |
| Mutations / commits | 1 / 1 |
| Input tokens | 278,731 |
| Output tokens | 9,921 |
| Cumulative provider tokens | 288,652 |
| Owned processes after exit | 0 |

The formal semantic status remains `unproven` because VP1 deliberately requires
independent open-ended judgment. That is not an infrastructure failure.

## Final Grasshopper State

The final receipt-fenced snapshot observed:

```text
9 components
7 wires
0 errors
0 warnings
```

The seeded system remained intact:

```text
Radius (8) -> original Circle
Reference A (2) + Reference B (3) -> Reference Result (5)
```

Qwen added exactly three components and three wires:

```text
Radius (8) -----> Addition (+W) -----> Outer Circle (radius 10)
Width (2) ------^
```

The original Circle is the inner boundary at radius 8. The added Circle is the
outer boundary at radius 10. Both use the same unconnected default Plane input.
The result is a useful adjustable annular band whose Width control governs the
radial difference while the original Radius control and useful Circle output
remain untouched.

The closed preservation evaluator passed with no violations. It retained every
protected component field and every protected flow in the unrelated arithmetic
cluster.

## Independent Shadow Judgment

The following judgment was made only after Qwen ended and the evidence was
sealed.

### Observed

- Two distinct Circle components each produced one `Rhino.Geometry.Circle`.
- The original Radius slider remained 8 and continued to drive the original
  Circle.
- The new Width slider was 2 and drove Addition with Radius; its solved output
  was 10 and drove the outer Circle.
- The final graph had zero errors and warnings.
- The preservation evaluator passed without a missing or altered protected fact.
- Qwen disclosed its interpretation: Radius is the inner boundary and
  `Radius + Width` is the outer boundary.

### Inferred

- The two valid circles sharing the same default Plane and having radii 8 and 10
  constitute a credible adjustable annular-band representation.
- Width is materially causal through the retained `Width -> Addition -> Outer`
  path and solved value 10.

### Unresolved

- Width was not behaviorally perturbed. Its causal role is supported by wiring
  and solved data rather than a separate probe.
- No viewport image was used in the retained judgment. The task is supported by
  component, flow, output, diagnostic, receipt, and preservation evidence.

Disposition: **`credible_success`** for this specimen.

## Predeclared Efficiency Observations

| Observation | Result |
|---|---|
| Searches for skill-listed tool names | 0 canonical `rook_tools_search` calls. |
| Duplicate contract reads | 0. Each admitted capability contract was read at most once. |
| Gateway calls before first mutation | 7. The committed mutation was source sequence 7. |
| Tokens before first mutation | 153,396 cumulative: 146,026 input and 7,370 output through Actor turn 14. |
| Named reasons for further discovery | Qwen named component identity and parameter-index uncertainty before exact Addition/Circle discovery. |
| Semantic health | Credible success; 9 components, 7 wires, clean diagnostics, preservation pass. |
| Final receipt-fenced evidence | Pass. Mutation sequence 7 -> wait sequence 9 -> fenced snapshot sequence 10. |
| `goal.complete()` | Pass. It followed the fenced snapshot and no later gateway call occurred. |

The model did not fully eliminate orientation waste:

- It attempted unsupported `rook_full.tools()`, received `AttributeError`, then
  inspected `dir(rook_full)` before using the documented `read/call/search`
  interface. These were two model-controlled IPython turns but no gateway calls.
- The initial snapshot already exposed the Addition and Circle GUIDs and ports.
  Qwen nevertheless made two exact `gh_library` calls and read the
  `gh_batch_component_info` contract. It then correctly recognized that the live
  snapshot already supplied the needed port facts and did not make the metadata
  call.

This is much smaller than the earlier discovery churn, but it remains evidence
that Qwen sometimes seeks reassurance after the next mutation is already
constructible.

## Descriptive Context

The earlier VP1 specimen under a different historical configuration also reached
a credible result:

| VP1 specimen | Seconds | Tokens | Calls | Discovery calls |
|---|---:|---:|---:|---:|
| Historical varied cohort | 242.469 | 501,605 | 23 | 16 |
| Prospective efficiency screen | 186.953 | 288,652 | 11 | 7 |

The new specimen exhibited lower latency, token use, and call volume while
preserving semantic quality and improving final-checkpoint custody. This is
promising screening evidence, not causal attribution: the intervening skill,
runner, and Rook configuration history prevents treating the historical row as
an isolated control.

## Disposition

The experimental rule is a useful candidate, not a promoted product default.
This specimen supports three bounded conclusions:

1. The simple model-led empirical loop produced a credible brownfield result.
2. Qwen can commit early, preserve unrelated work, inspect solved evidence, and
   stop honestly without semantic supervision.
3. Discovery cost dropped materially in this specimen, while adapter orientation
   and redundant confirmation remain visible optimization targets.

Do not add a supervisor, semantic acceptance vocabulary, caching layer, or new
Prime mechanism based on this run. The next decision should be based on another
genuinely varied product task, not another VP1 rerun or further tuning to this
specimen.

## Custody

- Frozen pre-contact commit: `cd8cc17b`.
- Pre-contact verification: **196 passed**, 11 existing warnings.
- Global evidence: **50/50** independently reverified.
- Row evidence: **35/35** independently reverified.
- Global manifest SHA-256:
  `2D6A52AC35C83DDE019184978E7FE0BD4C19D0E6670FFBBB18055DD79642882A`.
- Row manifest SHA-256:
  `5761E33AA0C930DFF2CB89315185BA712472FD717C5AAC7DB4071DEC4158CF53`.
- Frozen protocol SHA-256:
  `FB3C088B854A74B783F34CFF4AAE798FBB7BEBDBAF69BB536272F587049B9D63`.
- Prime JSONL SHA-256:
  `10217EB9252375A6755916F6292283F3E77154A14A1316CFD3D301F05BCC3464`.
- Source JSONL SHA-256:
  `5D62DCD2613E172B960AB33FBBB5A9918A48BBC198EA711C38C7DF7FD8D51E15`.
- Authoring trace SHA-256:
  `ED7DBF7FD8E69B029B337B1BB13C3C1C82F0C187B8F6DA97D406F8417AE2AB0D`.
- Final checkpoint SHA-256:
  `5CDDA0A8FBC7DE6A0D71344F0007EEC3D5F1951B46485E17E20C49615161F254`.
- Final observation SHA-256:
  `C867369C977E003D22038E0AC409383A0AAD0237CE19FBB0D14FCA4CA7274827`.
- Stderr: empty.
- Worktree was clean for the complete live transaction.

Evidence root:
[qwen38-vp1-prospective-efficiency-screen-v1](C:/UDEV/RookEvidence/2026-08-19-qwen38-vp1-prospective-efficiency-screen-v1)
