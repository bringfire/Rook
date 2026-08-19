# Qwen3.8 VP2 Evidence-Reuse Screening V1

**Date:** 2026-08-18  
**Status:** Complete execution; screening result incomplete  
**Protocol:** `rook.experiment.qwen38_varied_product_cohort:v1`  
**Implementation commit:** `5bf8670756273b5605c09fa69e6ee8c553eddcd9`

## Objective

Screen one behavioral intervention against the retained VP2 radial-canopy task:

> Reuse successfully and unambiguously resolved session-local capability schemas, component-discovery facts, and component metadata. Request only missing facts. Refresh a resolved fact only when refusal, runtime or target-identity change, or contradictory live evidence gives a named reason to consider it stale.

The prompt, Qwen3.8 27B model, low thinking, Prime runtime, Rook build,
adapter, checkpoint protocol, fresh-empty target, evaluator silence, and resource
limits remained identical to the retained VP2 baseline.

No evaluator feedback, operator repair, retry, cleanup, or second model run
occurred.

## Result

The row is truthfully:

```text
incomplete - provider_token_ceiling
```

- Prime elapsed time: `950.266` seconds.
- Provider-reported tokens at termination: `2,092,295`.
- Gateway events: `72` of `150` permitted.
- Prime exit code: `1`, caused by the mechanically detected token limit.
- Goal status: `budget_limited`.
- Terminal lifecycle: incomplete; no valid terminal completion marker.
- Qualification-owned child processes after exit: zero.
- Hidden evaluator status: `incomplete`.

The provider ceiling is detected after a provider usage report, so one-message
overshoot remains possible. The configured limit was not silently ignored.

## Baseline Custody

The new pre-contact check passed before target preparation:

- Declared baseline manifest existed.
- Manifest SHA-256 matched `3E62BE05...EB4990`.
- Existing manifest verification reproduced `123/123` entries with zero
  mismatches.
- The retained verification record is part of the new sealed archive.

## Efficiency Comparison

| Observation | VP2 baseline | Screening V1 | Direction |
|---|---:|---:|---|
| Exact repeated successful schema reads | 6 | 0 | improved |
| Metadata selector occurrences | 66 | 50 | improved |
| Repeated metadata selector occurrences | 25 | 19 | improved, criterion not met |
| Discovery plus schema/metadata calls | 36 | 48 | regressed |
| Actor turns | 46 | 43 | slightly improved |
| Provider tokens before first actual `gh_edit` turn | 760,257 | 531,114 | improved |
| Final input context | 85,407 | 96,888 | regressed |
| Cumulative provider input | 2,012,994 | 2,040,787 | regressed |
| Cumulative provider output | 60,694 | 51,508 | improved |
| Gateway calls | 69 | 72 | regressed |
| Canonical source-result bytes | 685,952 | 260,746 | improved |
| Retained Prime tool-result text bytes | 57,167 | 115,371 | regressed |

The rule eliminated the six exact repeated `rook_tools_read` calls and moved
the first actual edit materially earlier in cumulative provider usage. It did
not reduce total discovery work or total provider input.

Two exact successful metadata requests were repeated without a retained stale
fact trigger:

- `Point` by name at source sequences 19 and 20.
- `Merge` GUID `3cadddef-1e2b-4c09-9390-0e8f78f7609f` at sequences 42 and 43.

Both pairs returned identical successful results. The second predeclared reuse
criterion therefore failed. The third criterion also failed because discovery
plus schema/metadata calls increased from 36 to 48.

## Final Artifact

The latest model-facing receipt-fenced snapshot followed:

```text
gh_edit sequence 67
-> receipt cc1c790f092a1286c053edccaa09e81e
-> ready wait sequence 68
-> fenced snapshot sequence 69
```

That snapshot observed:

- 8 components and 7 wires.
- Six sliders: Span `20`, Ribs `12`, Rise `8`, Opening `4`, Curve `0.6`, and
  Twist `15` degrees.
- One Python 3 `Radial Canopy` component.
- 12 `Rhino.Geometry.NurbsCurve` rib outputs.
- Three complete sample points consistent with the intended radius, rise,
  curvature, and twist calculation.
- Zero errors and zero warnings.

This is credible partial canopy geometry, but not an accepted semantic pass:

- `BaseRing` and `HubRing` each previewed as `null`; their geometry was not
  proven.
- The final script-backed controls were not behaviorally perturbed.
- A leading script output named `out` shifted output indices. The panel was
  wired to `SamplePts` rather than `Info`.
- Qwen detected that wiring defect after two later unfenced snapshots and
  proposed the correct reconnection, but the provider-token ceiling terminated
  the run before the repair executed.
- Qwen never called `goal.complete()`.

## Interpretation

The intervention had a real but bounded effect: exact schema reacquisition was
eliminated, metadata repetition fell, and mutation began earlier in cumulative
provider usage. This one specimen does not establish causality or
repeatability.

The rule was not sufficient to improve the complete operational outcome.
Qwen performed more distinct discovery, attempted a native-component graph,
encountered repeated partial edits, deleted that graph, rebuilt the canopy as a
script component, and reached the token ceiling during final wiring repair.

Do not add caching, a supervisor, another completion protocol, or more semantic
guidance from this result. The narrow evidence-reuse rule remains reasonable,
but it should not be promoted as an efficiency solution. The next decision
should consider the broader discovery and implementation churn separately from
exact fact reuse.

## Evidence

Evidence root:

`C:/UDEV/RookEvidence/2026-08-18-qwen38-vp2-evidence-reuse-screening-v1`

Key SHA-256 values:

```text
Global manifest
22E45CAE9517C8BFDEA395BBFF9B734574251C1C979EB6FCD8618F413E05F173

Baseline custody verification
9ADA573597A16241BDACC7878FE121DB7A678869F521CD69F076732D785B6483

Prime JSONL
D2725C87CC8CEB430468863F995BE390E50EA0FE074F7716399C93212BB7690B

Canonical source trace
576A11C727CE6CB88C85AE7EE292A1F13BABFBD54A1D468BF073EDE6E9287ECD

Native session
D30C7FB4A542598C024CEF786D6380E38BA9DF89B723694ABCF7C127D983E88A

Outcome
8392760F12DC3FCF8D53F3B20CB3825AADF9D9DDF74E4D5FDDB3F437A4D39502
```

The global archive verifies `49/49`; the row archive verifies `33/33`.
