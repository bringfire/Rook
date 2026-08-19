# Qwen3.8 VP4 Profile Stack Prospective Screen V1

**Date:** 2026-08-19
**Status:** Complete execution; credible shadow success with unresolved independent geometry facts
**Live rows:** One
**Reruns:** None

## Question

Can Qwen3.8 complete a second compact, genuinely varied Grasshopper product task
under the unchanged experimental skill and runtime configuration, without
returning to destructive strategy churn?

This was a prospective screening and generalization specimen, not a causal
prompt comparison. The task changed while the model, low thinking level,
adapter, skill bytes, budgets, checkpoint discipline, and silent-evaluation
boundary remained frozen. No evaluator result was shown to the Actor.

The exact task was:

> Create a compact adjustable stack of closed horizontal rectangular profiles
> for possible future lofting. Expose Width, Depth, integer Levels, and Level
> Spacing controls. Produce exactly Levels profiles. Their XY centroids must
> align on one vertical axis, and adjacent profiles must be separated evenly by
> Level Spacing in Z. Exercise at least one consequential control, observe its
> effect, and restore the chosen defaults. Inspect the final stack and stop when
> satisfied. Do not loft, surface, bake, or create downstream geometry.

Prime's goal budget was **1,900,000 tokens** inside the runner's **2,000,000
provider-token ceiling**, preserving the 100,000-token response reserve.

## Result

The single row completed naturally:

```text
Prime exit:                    0
source closure:                agent_end
goal status:                   complete
actor final checkpoint:       pass
budget:                        pass
custody:                       pass
preservation:                  not applicable (fresh empty target)
hidden semantic evaluation:   unproven (independent judgment required)
shadow disposition:            credible_success
```

Operational telemetry:

| Observation | Value |
|---|---:|
| Elapsed time | 548.937 seconds |
| Gateway calls | 47 |
| Discovery calls | 26 |
| Source-observed mutation calls | 7 |
| Source-observed terminal commits | 6 |
| Input tokens | 1,045,491 |
| Output tokens | 30,091 |
| Cumulative provider tokens | 1,075,582 |
| Owned processes after exit | 0 |

The generic row telemetry reports six mutation calls and five committed
mutations because its mutation-target set excludes the
`gh_create_python_script` alias. The authoritative source trace contains that
initial committed creation, five later terminal commits, and one preparatory pin
mutation. This report uses the source-observed totals and preserves the telemetry
discrepancy rather than altering the frozen run after contact.

The formal semantic status remains `unproven` because this prospective path
deliberately leaves open-ended task judgment outside the runtime evaluator. That
is not an infrastructure failure.

## Final Grasshopper State

The final receipt-fenced snapshot observed:

```text
5 components
4 wires
1 group containing all 5 components
0 errors
0 warnings
```

The graph was:

```text
Width (4) -----------\
Depth (3) ------------\
Levels (5) ------------> Profile Stack (Python 3) -> Curves, Zs, Centroid
Level Spacing (2) -----/
```

At the restored defaults the solved outputs were:

```text
Curves:    5 Rhino.Geometry.NurbsCurve items
Zs:        0, 2, 4, 6, 8
Centroid:  (0,0,0), (0,0,2), (0,0,4), (0,0,6), (0,0,8)
```

No loft, surface, bake, or downstream geometry was created.

## Control Exercise And Restoration

Qwen changed two consequential controls together:

```text
Levels:         5 -> 9
Level Spacing:  2 -> 5
```

After waiting for solve readiness, its observation showed nine curve items and
Z values `0, 5, 10, 15, 20, 25, 30, 35, 40`. That snapshot was post-wait but did
not carry the receipt as a snapshot fence. Qwen then restored both defaults in
one edit.

The restoration checkpoint was fully receipt-fenced:

```text
restore mutation sequence:  44
receipt:                     25bcb58be3787fd298b1d0ab81e48587
readiness wait sequence:     45
fenced snapshot sequence:    46
mutation epoch:              6
completed solution epoch:    18
```

The fenced snapshot was the final gateway event. Qwen inspected it, invoked
`goal.complete()` as a dedicated final operation, and made no later gateway
call.

## Independent Shadow Judgment

The following judgment was made only after Qwen ended and the evidence was
sealed.

### Observed

- Four named controls were present, wired, and restored to Width 4, Depth 3,
  Levels 5, and Level Spacing 2.
- The final output contained exactly five curve items, five Z values, and five
  point-valued centroid witnesses.
- The final Z sequence was `0, 2, 4, 6, 8`.
- The projected point witnesses were `(0,0,z)` at those same five elevations.
- The perturbation produced nine curves and the expected Z sequence at spacing
  5; the restoration returned the graph to five curves at spacing 2.
- The final receipt-fenced snapshot had zero errors and warnings.
- The retained script constructs five-corner polylines with repeated first/last
  point, constant Z per profile, symmetric X/Y coordinates, and converts them to
  NURBS curves.
- The canvas contained no requested-out-of-scope downstream geometry.

### Inferred

- The retained script and solved output count credibly describe five closed,
  horizontal rectangular profiles centered on one vertical axis.
- `Levels` is functionally integral at the script boundary because the retained
  code rounds and converts it to `int` before constructing exactly that many
  profiles.
- The four controls form a useful adjustable profile-stack deliverable for this
  task.

### Unresolved

- The snapshot does not independently project the actual curves' closure,
  planarity, geometric centroids, or rectangular boundary coordinates. The
  centroid output is a witness authored by the same script that creates the
  curves, not an independent host calculation.
- The Levels component is a Number Slider. The retained snapshot does not expose
  slider decimal-place or integer-step configuration, so a strictly integer UI
  control is not proven even though output count is coerced to an integer.
- Width and Depth were not perturbed.
- The perturbation observation followed a successful readiness wait but was not
  itself receipt-fenced.

Disposition: **`credible_success`** for this specimen. The unresolved facts are
reported rather than filled by a new capture feature or task-specific evaluator.

## Predeclared Efficiency Observations

| Observation | Result |
|---|---|
| Searches for skill-listed tools | 12 broad `rook_tools_search` calls before authoring. None used an exact known tool name, but the broad searches were contrary to the intended direct-read discipline. |
| Duplicate contract reads | 0. Each of the 13 capability contracts was read once. |
| Discovery before first scaffold | 20 discovery calls plus one session-orientation call preceded source sequence 21, the first committed mutation. |
| Tokens through first mutation turn | 156,693 cumulative: 147,084 input and 9,609 output through Actor turn 13. |
| Implementation strategy | Python was selected before the first commit and never abandoned. No component deletion, wholesale reset, or replacement implementation occurred. |
| Local refinement | One preparatory pin update, two semantically equivalent script updates, one combined perturbation, and one restoration. |
| Semantic health | Credible success with the independent geometry and integer-slider limits stated above. |
| Final receipt-fenced evidence | Pass: mutation 44 -> wait 45 -> fenced snapshot 46. |
| `goal.complete()` | Pass. It followed the fenced snapshot; no later gateway call occurred. |

The run did not return to VP2-style destructive strategy churn. Qwen chose one
implementation mode, preserved it, added diagnostic outputs locally, exercised
controls, restored them, and stopped inside budget.

Discovery discipline nevertheless remained weak. Before creating the first
scaffold Qwen issued these 12 searches:

```text
grasshopper, gh, component, canvas, create, add,
value, curve, rectangle, curve, number, slider
```

It then read seven contracts and requested one metadata batch before the first
mutation. The repeated `curve` search and generic query sequence did not identify
an exact unresolved fact required by the next mutation. Later contract reads
were unique, and no further search calls occurred after the scaffold.

The two script updates at sequences 36 and 37 were semantically equivalent: the
second compacted the first successful script despite both calls returning clean
results. This is local reassurance churn, not a strategy pivot.

## Disposition

This second prospective task adds useful product evidence:

1. The simple model-led empirical loop again produced a credible Grasshopper
   deliverable on a different component family and task shape.
2. Qwen selected one viable implementation, repaired and instrumented it
   locally, restored controls, obtained authentic final evidence, and stopped.
3. The experimental guidance did not reliably prevent broad pre-commit search,
   so it is not yet a qualified efficiency solution.
4. The remaining semantic uncertainty comes from the bounded observation
   surface, not an observed contradiction in the final graph.

Do not tune or rerun this task, add a semantic supervisor, or manufacture a
profile-stack evaluator. Also do not treat another prompt rule as the automatic
next move. The semantic loop has now produced credible results on two varied
tasks; the persistent product question is the cost and salience of initial tool
orientation. That efficiency problem should remain separate from semantic
competence and final-evidence custody.

The experimental skill should remain an explicitly versioned candidate until a
separate product decision determines which concise guidance belongs in the
durable skill. This run supports the strategy-preservation and stopping
discipline, but shows that the direct-read discovery discipline was not followed
consistently.

## Custody

- Frozen pre-contact commit: `12700da2`.
- Pre-contact verification: **197 passed**, 11 existing warnings.
- Global evidence: **49/49** independently reverified.
- Row evidence: **34/34** independently reverified.
- Global manifest SHA-256:
  `0EF189A86D932D35C5480A28BB7F12BCAAFD445692BD1029ED386D8E6B9AE3C0`.
- Row manifest SHA-256:
  `E3CBCD323B54BCE892D46652A18DB82B426077A722D6574BF6EF4AF8FD7E307B`.
- Frozen protocol SHA-256:
  `A7FFE939D1CE2369D01D416C7B1222FE779B7F2D838CAB887F1D3D22D560153B`.
- Frozen experimental skill SHA-256:
  `6C6A7AFF7B7A6F8B4C36F4F6E2ACCCC44D00443354662843523B92D4AB22A2DD`.
- Canonical product-baseline skill remained unchanged at:
  `30CA98809CCE8F4BE5B1CC291DEB8820511B6B13A0D546CBA93848DBC9074B07`.
- Prime JSONL SHA-256:
  `B29E0502D9426D01727FF72534C8D3359176A7F0D9944433F96AF3F97C2BFE61`.
- Source JSONL SHA-256:
  `F87A59261F544FC8E105E25CCFF7551417F7ACE84E475A68CEAAA2B8F31E71C2`.
- Authoring trace SHA-256:
  `64E8E3255BBF2EAEF395F95EE5425520AAD2D4BBE97623D4B6BF2ECCF9FAC691`.
- Final checkpoint SHA-256:
  `0C6C58DBC5E60897B16E14368B9C6CE31B85EDBE11F1E94820CC445CF2092FC3`.
- Final observation SHA-256:
  `9FA1BF9B025F450AF4C081B8EF98E37FE3B4A5A3FBF537998220D276635E7A09`.
- Stderr: empty.
- Worktree was clean for the complete live transaction.

Evidence root:
[qwen38-vp4-profile-stack-prospective-screen-v1](C:/UDEV/RookEvidence/2026-08-19-qwen38-vp4-profile-stack-prospective-screen-v1)
