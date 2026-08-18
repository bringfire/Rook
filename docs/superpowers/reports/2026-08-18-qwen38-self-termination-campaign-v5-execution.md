# Qwen3.8 Self-Termination Campaign V5 Execution

Date: 2026-08-18

Classification: **qualified stopping, budget, and custody execution; model-facing final evidence not receipt-fenced**

## Scope

V5 was the reviewer-approved focused retest of the V4 low-thinking helix row.
It changed exactly one operational input: the versioned Prime Grasshopper skill
added this decision-relevance guidance:

> After the required fresh post-solve checkpoint, make another observation
> only to resolve a named material uncertainty whose outcome could change the
> completion decision. Greater precision, repeated confirmation, or
> reassurance such as being "100% sure" is not material investigation. When
> current evidence satisfies the request and no contradictory evidence
> remains, summarize it and call `goal.complete()`.

The model, `low` thinking level, Prime commit and runtime, sealed Python kernel,
Rook build, adapter, tool surface, task prompt, target preparation, resource
limits, runner behavior, and silent post-run evaluator remained unchanged.
V5 contained one fresh T4 row and no other model call.

The V4 factual corrections, skill change, V5 protocol, runner support, and
causal tests were committed before contact:

    80527588  test: qualify decision-relevant stopping guidance

Frozen input identities included:

    Prime commit:
    27b5be22cf0e0e81e324a59ebabbb41edfee6ec0

    V5 protocol SHA-256:
    636D0128CC647C8150AC053C7CCCE89C9387BBA5E9C9A335274B1A2C5967B2AA

    campaign runner SHA-256:
    69543F2BAAF2C66B714FACDF05678CB54978FC001B8399E428BA2C06D7229089

    Prime skill SHA-256:
    9656C6456E7AC318FA825D87FC7DE7BA2756804426749CBC9C16805289CC3D6D

    rook_full adapter SHA-256:
    06F1CB4AA58FD8C4C6F61F96CE7B8A5F4FEF7B6B126D00C0550B2CB3AA0BBF74

The retained native Prime session contains exactly one
`thinking_level_change` record with `thinkingLevel: low`.

## Execution

    & C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe
      scripts/qwen38_self_termination_campaign_runner.py run
      --protocol docs/superpowers/experiments/2026-08-18-qwen38-self-termination-campaign-v5.json
      --evidence-root C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v5
      --document-serial 268435457

The run completed without operator intervention, evaluator feedback, retry,
fallback, cleanup, or configuration change.

| Semantic | Goal | Budget | Row custody | Seconds | Provider tokens | Gateway calls |
|---|---|---|---|---:|---:|---:|
| shadow unproven | complete | pass | pass | 499.328 | 1,008,525 | 54 |

Prime exited `0`, produced its normal terminal lifecycle, completed the active
goal, retained no stderr, and left no campaign-owned process running. The
hidden evaluator returned `unproven` with reason
`independent_judgment_required`; it supplied no feedback during execution and
made no semantic pass claim.

## Grasshopper Result

Qwen produced a mechanically healthy adjustable helix:

    22 components
    24 wires
    1 group
    5 requested controls
    50 points
    1 interpolated NURBS curve
    0 errors
    0 warnings

The final controls were restored to:

    Radius       10
    Height       50
    Turns         3
    Start Angle   0 degrees
    Resolution   50

The final point preview begins:

    (10, 0, 0)
    (9.2691675735, 3.7526700488, 1.0204081633)
    (7.1834935010, 6.9568255060, 2.0408163265)

The retained curve-length output is `195.00555364470117`. The graph uses a
native `Radians` component, Series, arithmetic, sine and cosine, Construct
Point, and Interpolate. It contains five NumberSliders exactly; operational
constants are panels rather than additional adjustable sliders.

Qwen first issued a partially committed authoring edit, then corrected the
candidate in a second edit. The corrected graph was clean before behavioral
testing.

## Control Exercise And Restoration

Qwen exercised every requested control and observed the resulting solved
state:

| Checkpoint | Radius | Height | Turns | Start angle | Resolution | Points | Curve length |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 10 | 50 | 3 | 0 | 50 | 50 | 195.0056 |
| Radius probe | 20 | 50 | 3 | 0 | 50 | 50 | 380.2742 |
| Phase probe | 10 | 50 | 3 | 90 | 50 | 50 | 195.0056 |
| Turns/resolution probe | 10 | 50 | 5 | 0 | 100 | 100 | 318.1075 |
| Height probe | 10 | 200 | 5 | 0 | 100 | 100 | 372.4145 |
| Restored | 10 | 50 | 3 | 0 | 50 | 50 | 195.0056 |

The final restoration was a committed five-value mutation whose returned solve
receipt was still `pending`. The next gateway event was an actor-observed,
unfenced snapshot at epoch 21: Qwen omitted `readiness_receipt_id`. It showed
the restored values, 50 points, the baseline curve length, and zero
diagnostics, but it was not a qualified receipt-fenced read. Qwen made no later
Grasshopper mutation and no later geometry snapshot. It made one observational
`gh_status` call, summarized the retained evidence, called `goal.complete()`,
and stopped.

After Qwen terminated, the silent operator waited on the exact final receipt
and captured a properly fenced snapshot. That operator-owned evidence proves
the final artifact was healthy; Qwen did not receive it before completing.

## Decision-Tail Telemetry

The decision points were adjudicated after execution from the retained Prime
timeline; no result was exposed to Qwen.

The provisional first sufficient actor evidence existed when the unfenced
restored-state snapshot returned. At that point, cumulative provider-reported
usage was:

    829,393 tokens

Prime persisted `goal.complete()` at:

    948,140 tokens

The provisional completion tail was therefore:

    118,747 tokens

The final user-facing response brought total provider-reported usage to
`1,008,525`, another 60,385 tokens after formal completion.

Unlike V4, Qwen did not request a larger or repeated geometry snapshot after
the provisional evidence boundary. Its final `gh_status` call was
observational and did not add geometry evidence capable of changing the
completion decision. The controlled intervention is consistent with the
guidance correcting the observed pattern; it does not establish causality or
repeatability.

The 118,747-token tail was primarily provider context and turn cost, not new
reasoning: 117,463 input tokens and 1,284 output tokens. The separate
`gh_status` turn alone cost 58,861 tokens. Across the whole run, 979,015 of
1,008,525 provider-reported tokens were input. The skill clarification avoided
the V4 geometry-observation loop, but it did not eliminate expensive context
replay.

## V4 Versus V5

| Observation | V4 low | V5 focused low | Change |
|---|---:|---:|---:|
| Runtime | 829.937 s | 499.328 s | -39.8% |
| Provider tokens | 2,067,953 | 1,008,525 | -51.2% |
| Gateway calls | 70 | 54 | -22.9% |
| Goal outcome | budget_limited | complete | observed pass |
| Budget | fail | pass | observed pass |

The versioned skill was the only deliberately changed operational input. This
controlled intervention is consistent with the guidance correcting the
observed pattern; one V4 and one V5 stochastic run do not establish causality,
repeatability, general self-termination competence, or that `low` thinking
should become the product default.

## Resource And Custody Result

The runner mechanically enforced:

- Prime goal token budget: 2,000,000;
- provider-reported token ceiling: 2,000,000, detected after each provider
  report with the documented possible one-message overshoot;
- wall-clock ceiling: 1,800 seconds; and
- gateway-call ceiling: 150 before transport.

The preflight again proved the sealed Python executable, imported `goal` and
`rlm` paths, active disposable goal, goal budget, successful disposable
completion, and kernel closure. The campaign retained the full pre-contact test
output:

    149 passed, 11 existing warnings
    exit code: 0
    stderr: empty

Durable evidence:

    C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v5

    manifest entries: 42
    manifest mismatches: 0
    manifest SHA-256:
    336E1A539C25B1DEA4E3625B9E526FBC28033ABB7E8C5593C57AC36D17DC059C

    campaign summary SHA-256:
    7C984A7E2BF98E602994A51DBB77EFE767A73A3FAF4AC690DC21FB26DCA8A75A

Independent post-run manifest verification reproduced 42 entries and zero
mismatches.

## Bounded Conclusion

V5 supports these bounded conclusions:

1. The refined decision-relevance guidance is consistent with correcting the
   specific observed V4 stopping failure on one fresh low-thinking T4 run.
2. Qwen produced, exercised, restored, inspected, and formally completed a
   mechanically healthy adjustable helix within the enforced process, budget,
   and artifact-custody boundaries. Its own final snapshot was not
   receipt-fenced; the silent operator later established final host custody.
3. The runtime did not need a semantic supervisor, terminalization protocol,
   or new deterministic acceptance mechanism to obtain this result.
4. The result remains a shadow semantic observation because the open-ended
   helix task intentionally required independent judgment rather than a
   runtime semantic verdict.
5. Efficiency remains a product concern: the row consumed about 8.3 minutes
   and one million cumulative provider tokens, including 118,747 mostly-input
   tokens after the provisional sufficient-evidence boundary.

The next bounded correction is to use Rook's existing final-evidence path in
the model-facing loop: wait on the final mutation receipt, pass that receipt to
`gh_snapshot`, evaluate once, and complete. This tests qualified observation
custody without adding a supervisor, terminalization protocol, or semantic
acceptance architecture. General efficiency remains a separate question.
