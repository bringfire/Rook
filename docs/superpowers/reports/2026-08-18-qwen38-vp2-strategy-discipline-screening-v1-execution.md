# Qwen3.8 VP2 Strategy-Discipline Screening V1

**Date:** 2026-08-18
**Status:** Complete execution; not qualified
**Live rows:** One
**Reruns:** None

## Question

Would one narrow strategy-discipline rule prevent the destructive implementation
pivot observed in the retained VP2 evidence-reuse screening while preserving
Qwen's ability to change strategy when live evidence made a pivot preferable?

The exact experimental addition was:

> Treat a component or subgraph failure as local first. Before abandoning a committed strategy, either attempt one bounded local repair or identify live evidence making a pivot preferable. Preserve unaffected committed work during a pivot. Further discovery must name the blocker it resolves.

The prior evidence-reuse guidance remained frozen. The canonical product skill
remained byte-identical at SHA-256
`30CA98809CCE8F4BE5B1CC291DEB8820511B6B13A0D546CBA93848DBC9074B07`.
The strategy-screening skill was an experiment-only fixture at SHA-256
`A1AB103DBD878A2DEEF5C2060352057C4CBF02DF8FF9878B2CECE3B9FA16C6C7`.

## Result

The one row completed as:

```text
semanticStatus: incomplete
goalStatus: budget_limited
budgetStatus: fail
custodyStatus: fail
actorFinalCheckpointStatus: fail
evaluationInfrastructureStatus: pass
```

Prime was terminated after the first provider report above the two-million-token
ceiling. The goal did not complete, no valid terminal `agent_end` was retained,
and no receipt-fenced final observation was available. Qwen did not falsely
claim success; it was still investigating a live error when the budget stopped
the row.

## Observed Behavior

The destructive strategy reset did not recur.

- Qwen created one native Grasshopper graph containing 31 components and 40
  observed wires.
- It issued no delete operation.
- All 31 committed components remained present in its last observed snapshot.
- It made two later connection edits against the same local `Point On Curve`
  blocker rather than deleting the graph or rebuilding it as a script.
- It was considering a trigonometric replacement for that local subgraph when
  the budget ended.

This is consistent with the guidance changing the observed strategy behavior.
One stochastic specimen does not establish causality or repeatability.

The row did not produce a healthy canopy. The last actor-observed snapshot had:

```text
31 components
40 wires
1 group
1 error
0 warnings
```

The error was:

```text
Point On Curve
Data conversion failed from Number to curve
```

The final committed mutation had receipt
`4d31e30b36c56e6a64ccb9299e592c24`, but Qwen did not wait on or snapshot that
receipt before termination. Its mechanical and semantic effect is therefore
unproven.

## Strategy Comparison

| Observation | Evidence-reuse screen | Strategy screen |
|---|---:|---:|
| Elapsed seconds | 950.266 | 945.406 |
| Gateway calls | 72 | 87 |
| Discovery calls | 48 | 68 |
| First-edit cumulative tokens | 531,114 | 816,217 |
| Total provider tokens | 2,092,295 | 2,026,180 |
| Deleted committed components during pivot | 26 | 0 |
| Final formal completion | No | No |

The total-token comparison improved by 66,115 tokens, or about 3.2 percent,
but both rows crossed the same two-million-token ceiling. Discovery increased
by 20 calls, and the first edit occurred 285,103 cumulative tokens later. The
guidance prevented the observed destructive reset but did not improve overall
efficiency or completion.

After the first edit, the retained source sequence was:

```text
initial native build
-> solve and error inspection
-> two local connection edits
-> component exploration and knowledge queries
-> search for a trigonometric local replacement
-> budget termination
```

The last 15 gateway events were devoted to resolving or replacing the local
component blocker. The predeclared criterion requiring fewer than three such
replacement-discovery calls therefore failed.

## Predeclared Criteria

| Criterion | Result | Basis |
|---|---|---|
| `no_wholesale_deletion_without_live_evidence` | pass | No delete operation occurred. |
| `preserve_unaffected_committed_work_during_pivot` | not exercised | No strategy pivot occurred. Committed work remained present. |
| `fewer_than_3_replacement_strategy_discovery_calls` | fail | Fifteen post-repair gateway events investigated the blocker or a replacement. |
| `fewer_than_2092295_cumulative_provider_tokens` | pass | 2,026,180 tokens, 66,115 below the comparison row. |
| `any_strategy_pivot_supported_by_live_evidence` | not exercised | Qwen had not pivoted when terminated. |
| `mechanically_healthy_canopy_without_material_regression` | not met | The last observed graph retained one error and no qualified final output. |
| `receipt_fenced_final_snapshot_then_goal_complete` | fail | Neither the receipt wait, fenced snapshot, nor completion occurred. |
| `budget_pass` | fail | The provider-token ceiling was crossed by one reported turn. |
| `custody_pass` | fail | Budget termination left no valid terminal lifecycle marker. |

## Evidence Boundary

The component evidence available to Qwen is material. `gh_batch_component_info`
identified the selected `Point On Curve` object as `isSimpleParam` and did not
return input or output ports. A later live exploration returned empty input and
output maps. Qwen nevertheless treated it as the curve-evaluation component,
attempted indexed connections, and then tried to infer the missing contract.

Qwen made material judgment mistakes: it ignored `isSimpleParam`, inferred a
nonexistent `I1`, and initially called `gh_explore_component` with an
unsupported `name` field. The retained evidence and implementation also
establish a separate Rook defect rather than an unresolved ownership question:

- `gh_edit` bypassed the bounded connection-selector resolver and treated any
  standalone parameter as every requested input index.
- Both local edits reported `connected: 1`; the attempted `I1` could not name a
  real endpoint, while the valid logical `I0` outcome remained absent from the
  observed flow set.
- The initial edit reported 42 connections while the snapshot exposed only 40.
- Connection reporting incremented after invoking `AddSource` without checking
  that the requested source was present afterward.
- Snapshot flow projection recognized only a short type-name allowlist instead
  of every supported standalone parameter, hiding incoming sources for this
  object.

Rook therefore supplied misleading mutation and observation feedback during
Qwen's bounded local investigation. This is a closed-semantics interface defect;
it does not require another reasoning rule or semantic acceptance mechanism.

## Conclusion

The strategy rule is a useful behavioral signal, not a qualified product
improvement. It prevented the exact destructive pattern under study, but Qwen
then spent the saved strategy state on prolonged local investigation and still
failed to complete within budget.

Do not promote either experimental guidance rule to the canonical product
skill. Do not rerun VP2 yet and do not add another reasoning rule. The next KISS
slice is to unify standalone-parameter classification across metadata,
connection admission, and snapshots; reject nonexistent indices before
mutation; confirm source membership before reporting a connection; and qualify
the repair against live Grasshopper before another VP2 run.

## Custody

- Pre-contact tests: `188 passed`, 11 existing warnings.
- Historical source archive: `49/49` verified before target preparation.
- Row evidence: `38/38` verified, manifest SHA-256
  `ADC19B85D35B7EEB0CD5D3308B196FFE20B852B7D454477DB8671130B3053CE8`.
- Global evidence: `54/54` verified, manifest SHA-256
  `265DF9D8B86056492EF15ACB39290A1B9080F324FE2E57EBC37A1A5931B44588`.
- Prime trace SHA-256:
  `1016AD57C1468C5F9EC18993319824DE6138F8900592E89E976975890E402696`.
- Canonical source trace SHA-256:
  `7F96CB700D9FF52D16205687ECD5BB848268F888DD1837A0D96811E76B5CB37A`.
- Native session SHA-256:
  `01F355E808DD516CBBE9B4756FECA72F2539485220176ACFEC1ADDC4A7149E8B`.
- Stderr was empty.
- No qualification-owned process remained.

Evidence root:
[qwen38-vp2-strategy-discipline-screening-v1](C:/UDEV/RookEvidence/2026-08-18-qwen38-vp2-strategy-discipline-screening-v1)
