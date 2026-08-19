# Qwen3.8 VP2 Strategy-Churn Attribution

**Date:** 2026-08-18
**Status:** Complete offline analysis
**Live contact:** None

## Question

Why did the evidence-reuse screening spend roughly the same provider budget as
the retained VP2 baseline despite eliminating exact repeated schema reads and
reducing repeated metadata selectors?

This analysis compares only retained evidence. It does not modify either
archive, contact Prime, Qwen, Rook, Rhino, or Grasshopper, or claim causal
repeatability from two stochastic specimens.

## Custody

| Evidence | VP2 baseline | Evidence-reuse screening |
|---|---|---|
| Campaign manifest | `3E62BE05...EB4990` | `22E45CAE...5F173` |
| Prime JSONL | `5AB87A7B...57529` | `D2725C87...7690B` |
| Canonical source trace | `288AC2BF...7AC0` | `576A11C7...7ECD` |
| Native session | `8A9F3CB0...05BE2` | `D30C7FB4...E88A` |
| Verified manifest entries | `123/123` | `49/49` |

The screening archive's own pre-contact record also verifies the baseline
archive at `123/123` before target preparation.

## Method

Stages are bounded by retained source sequence numbers and provider turns:

- A source sequence is one canonical gateway event.
- A provider turn is one `message_end` carrying integer input and output usage.
- Stage token totals sum provider-reported input plus output for those turns.
- Provider input replays prior context, so stage totals are operational burden,
  not marginal causal token cost.
- "Ultimately unused" means the model later deleted or replaced the state. It
  does not prove that the investigation was unreasonable when initiated.

## Baseline Stages

| Stage | Source sequences | Provider turns | Calls | Provider tokens |
|---|---:|---:|---:|---:|
| Orientation and core schemas | 0-14 | 1-8 | 15 | 66,577 |
| Native-strategy discovery | 15-37 | 9-28 | 23 | 693,680 |
| Native build and initial verification | 38-44 | 29-34 | 7 | 392,753 |
| Control probe and native extension | 45-57 | 35-41 | 13 | 509,698 |
| Final verification, repair, and completion | 58-68 | 42-46 | 11 | 410,980 |
| **Total** | **0-68** | **1-46** | **69** | **2,073,688** |

The baseline was expensive and crossed the provider ceiling, but it retained
one native strategy. Its first edit created 40 components and 55 wires. A later
extension initially failed because it referenced obsolete temporary IDs; Qwen
rebound those references to committed short IDs and added five components
without discarding the working graph. It completed with 45 components, 62
wires, and a receipt-fenced final observation.

## Screening Stages

| Stage | Source sequences | Provider turns | Calls | Provider tokens |
|---|---:|---:|---:|---:|
| Orientation and core schemas | 0-14 | 1-7 | 15 | 57,175 |
| Native-strategy discovery | 15-46 | 8-23 | 32 | 473,939 |
| Native implementation and component probe | 47-58 | 24-31 | 12 | 474,188 |
| Replacement-strategy discovery | 59-61 | 32-33 | 3 | 158,015 |
| Abandonment and script rebuild | 62-67 | 34-38 | 6 | 451,597 |
| Final verification and unexecuted repair | 68-71 | 39-43 | 4 | 477,381 |
| **Total** | **0-71** | **1-43** | **72** | **2,092,295** |

The screening's initial native path consumed 59 calls and 1,005,302 cumulative
provider tokens before Qwen searched for a replacement strategy. It included:

- 31 component-library or metadata calls whose facts were ultimately unused;
- five native `gh_edit` attempts;
- two pre-mutation admission refusals;
- two commits with per-operation failures;
- one clean committed probe; and
- six structural or output snapshots.

At source sequence 63, Qwen deleted all 26 committed native components. It
then discovered and created one Python component, added six sliders and one
panel, and reached a receipt-fenced snapshot. The final four observations and
the unexecuted repair turn consumed another 477,381 provider tokens.

## Pivot Evidence

The retained reasoning gives one named blocker: the chosen `Weave` component
was a two-stream selector and could not assemble three per-rib point streams
into branch-local curve inputs. Live evidence supported rejecting that
component choice.

It did not support rejecting the entire native strategy:

- The canvas and solver had not established that native construction was
  impossible.
- The committed graph was deleted wholesale rather than retaining unaffected
  controls and arithmetic.
- No bounded search for alternative tree operations or a local replacement of
  the blocked subgraph occurred.
- The replacement script reproduced the same geometric relationships that the
  native graph was attempting to express.

The decisive transition was therefore:

```text
local component/subgraph mismatch
-> inferred strategy-level dead end
-> delete all committed work
-> rediscover an authoring capability
-> rebuild from zero
```

The baseline provides a useful contrast. It also encountered an admission
failure, but treated it as a local identity problem and repaired the affected
extension while preserving the established strategy.

## Conclusion

The evidence-reuse rule addressed exact fact reacquisition, but fact
reacquisition was not the dominant waste in this screening. The larger cost was
failure to distinguish a local implementation blocker from invalidation of the
overall strategy.

This supports one experimental guidance candidate:

> Once implementation starts, preserve the chosen strategy unless live evidence shows it cannot meet a consequential requirement. Treat a failed component or subgraph as a local blocker: inspect and replace that part before abandoning committed work. Further discovery must name the blocker it resolves.

This candidate does not require a planner, cache, supervisor, semantic gate, or
runtime change. It remains experimental guidance, not a product default. A
single otherwise frozen VP2 screening can test it; no other instruction should
change in that cohort.

## Evidence

- [Baseline Prime trace](C:/UDEV/RookEvidence/2026-08-18-qwen38-varied-product-cohort-v1/VP2/operator/prime.jsonl)
- [Baseline source trace](C:/UDEV/RookEvidence/2026-08-18-qwen38-varied-product-cohort-v1/VP2/operator/source.jsonl)
- [Screening Prime trace](C:/UDEV/RookEvidence/2026-08-18-qwen38-vp2-evidence-reuse-screening-v1/VP2/operator/prime.jsonl)
- [Screening source trace](C:/UDEV/RookEvidence/2026-08-18-qwen38-vp2-evidence-reuse-screening-v1/VP2/operator/source.jsonl)
