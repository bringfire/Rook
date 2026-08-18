# Qwen3.8 Self-Termination Campaign V6 Execution

Date: 2026-08-18

Classification: **qualified model-facing final-evidence, stopping, budget, and custody execution**

## Scope

V6 was the single reviewer-approved confirmation after V5. It changed one
conceptual operational input: the versioned Prime execution instructions. The
skill and its checkpoint reference now require the final model-facing path:

    final terminal mutation receipt
    -> gh_wait_for_solve_readiness(receipt)
    -> gh_snapshot(readiness_receipt_id=receipt)
    -> evaluate the fenced evidence once
    -> goal.complete()

An unfenced snapshot or `gh_status` cannot substitute for the final checkpoint.
The model, low thinking level, Prime runtime, sealed Python kernel, Rook build,
adapter, tool surface, T4 prompt, resource limits, and silent post-run evaluator
remained unchanged from V5.

The V5 report correction, instruction changes, V6 protocol, runner audit, and
tests were committed before contact:

    5f91e3de  test: require receipt-fenced final checkpoint

Frozen identities included:

    Prime commit:
    27b5be22cf0e0e81e324a59ebabbb41edfee6ec0

    V6 protocol SHA-256:
    F3DFAFD00C0DF55A1F6C2A8B2DA3A4AEE0BE2A2DEAE533892F909F0AC184ECB8

    campaign runner SHA-256:
    2D2035F39980C7EB9C49890B4A195B8D885E9D29088BAC58A60436E9FCFF6D43

    Prime skill SHA-256:
    30CA98809CCE8F4BE5B1CC291DEB8820511B6B13A0D546CBA93848DBC9074B07

    checkpoint reference SHA-256:
    2D574EABF45EC1EB9B9BBCFCBD68F1CBE311E466CD922DF312F88A51925D63E7

    rook_full adapter SHA-256:
    06F1CB4AA58FD8C4C6F61F96CE7B8A5F4FEF7B6B126D00C0550B2CB3AA0BBF74

The retained Prime session contains exactly one effective
`thinking_level_change: low` record.

## Execution

    & C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe
      scripts/qwen38_self_termination_campaign_runner.py run
      --protocol docs/superpowers/experiments/2026-08-18-qwen38-self-termination-campaign-v6.json
      --evidence-root C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v6
      --document-serial 268435457

The row completed once without operator intervention, evaluator feedback,
retry, fallback, cleanup, or configuration change.

| Semantic | Goal | Budget | Row custody | Actor final checkpoint | Seconds | Provider tokens | Gateway calls |
|---|---|---|---|---|---:|---:|---:|
| shadow unproven | complete | pass | pass | pass | 586.468 | 1,283,808 | 69 |

Prime exited `0`, produced one normal terminal lifecycle, completed the active
goal, retained empty stderr, and left no campaign-owned process running.

## Model-Facing Receipt Custody

The runner's closed offline audit admitted this exact source ordering:

    sequence 65: gh_edit committed
                 receipt a353887455c21e1def19fbc922327e67
    sequence 66: schema read for gh_wait_for_solve_readiness
    sequence 67: wait on the exact receipt returned ready
    sequence 68: gh_snapshot used the exact readiness_receipt_id
                 and returned successfully
    later gateway events: none

The schema read was observational and did not invalidate the receipt. The
fenced snapshot was the final Rook gateway call. Qwen received and inspected
that snapshot before invoking Prime's public `goal.complete()` seam.

The persisted custody result is:

    schema: rook.experiment.actor_final_checkpoint:v1
    status: pass
    mutationSequence: 65
    waitSequence: 67
    snapshotSequence: 68
    gatewayEventCount: 69

    actor-final-checkpoint SHA-256:
    BFB70EA75CFDC7B1A8A943790DCB7724BC32309B6C0CB2CB3D46BE76CF6DD6C0

This closes the V5 evidence-custody shortfall using existing Rook behavior. No
new solve scheduler, semantic gate, supervisor, or Prime terminalization
mechanism was introduced.

## Grasshopper Result

The final receipt-fenced snapshot showed:

    25 components
    30 wires
    5 requested sliders
    4 constant panels
    96 points
    1 interpolated NURBS curve
    0 errors
    0 warnings

Final controls:

| Control | Value | Range |
|---|---:|---:|
| Radius | 5 | 0.5 to 20 |
| Height | 12 | 0.5 to 60 |
| Turns | 3 | 0.1 to 12 |
| Start Angle | 0 | -360 to 360 |
| Resolution | 96 | 4 to 720 |

The fenced point output contained 96 items and began:

    (5, 0, 0)
    (4.9018998294, 0.9855851373, 0.1263157895)
    (4.6114487749, 1.9324958465, 0.2526315789)

The retained curve-length output was `95.00838573002892`.

Qwen exercised the five controls together at Radius 8, Height 20, Turns 2,
Start Angle 90, and Resolution 24. It observed the changed 24-point helix and
curve length, then restored all five defaults. This proves a meaningful
combined control response and exact restoration in the observed run; it does
not isolate each control's causal effect independently.

## Decision-Tail Telemetry

Per-turn provider usage was derived after execution from retained Prime
`message_end` records. The fenced snapshot reached Qwen after model response
29:

    cumulative input:   1,058,150
    cumulative output:     26,749
    cumulative total:   1,084,899

Qwen then used one offline IPython turn to inspect the already-returned snapshot
without another gateway call. It requested `goal.complete()` after model
response 31:

    cumulative input:   1,189,025
    cumulative output:     27,538
    cumulative total:   1,216,563

The qualified-evidence-to-completion tail was:

    input:   130,875
    output:      789
    total:   131,664

The final user-facing report added 66,613 input and 632 output tokens. Final
provider telemetry was:

    input:   1,255,638
    output:     28,170
    total:   1,283,808

The tail was again almost entirely provider context replay. V6 eliminated the
compensating `gh_status` call after final evidence, but adding qualified receipt
custody did not improve total efficiency.

## V5 Versus V6

| Observation | V5 | V6 | Change |
|---|---:|---:|---:|
| Runtime | 499.328 s | 586.468 s | +17.5% |
| Provider tokens | 1,008,525 | 1,283,808 | +27.3% |
| Gateway calls | 54 | 69 | +27.8% |
| Model-facing final checkpoint | unfenced | receipt-fenced | corrected |
| Goal, budget, process custody | pass | pass | preserved |

This is one stochastic specimen. The controlled intervention is consistent
with the instructions causing Qwen to use Rook's receipt path, but it does not
establish general causality or repeatability. It does establish that the
requested behavior is within Qwen3.8's observed capability under the frozen
configuration.

## Separate Trace-Admission Limitation

The silent semantic evaluator remained `unproven` with
`authoring_trace_invalid`. Earlier in the Actor run, a stale-epoch `gh_edit`
was truthfully refused with `epoch_mismatch` and no mutation. At campaign time,
the trace normalizer classified that refusal as an unknown mutation outcome, so
it did not admit an independent semantic evaluation. This is the previously
observed trace-admission limitation. It does not invalidate the later
model-facing receipt-fenced snapshot, but it prevented the evaluator from
retaining its own fenced observation and reporting the accurate reason
classification. Even with
a valid trace, this open task remains `unproven: independent_judgment_required`;
the correction does not upgrade it to a formal semantic pass.

## Resource And Evidence Custody

The runner enforced:

- Prime goal token budget: 2,000,000;
- provider-reported token ceiling: 2,000,000;
- wall-clock ceiling: 1,800 seconds; and
- gateway-call ceiling: 150 before transport.

Pre-contact verification was retained in full:

    154 passed, 11 existing warnings
    exit code: 0
    stderr: empty

Durable evidence:

    C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v6

    manifest entries: 42
    manifest mismatches: 0
    manifest SHA-256:
    28ECADA059914D3858B909B0C1A89F9233139AE1A982FC2F0E43EDF071037425

    campaign summary SHA-256:
    7C1BE3F15C0D23FD4724D1AA293788F3EF1E5D2D685FA12A67BFCD9F7147AFA7

Independent post-run verification reproduced all 42 hashes with zero
mismatches.

## Bounded Conclusion

V6 supports these bounded conclusions:

1. Qwen can use Rook's existing solve receipt, readiness wait, and
   receipt-fenced snapshot as its own final evidence path.
2. Qwen built, exercised, restored, inspected, and formally completed a
   mechanically healthy helix while meeting every process, budget, and final
   evidence-custody gate.
3. No later gateway call followed the qualified snapshot, and the V5
   compensating status turn did not recur.
4. The semantic result remains shadow evidence because independent judgment is
   required. The campaign-time trace refusal was an additional historical
   limitation.
5. Efficiency remains unresolved: V6 was slower, used more gateway calls, and
   consumed more provider context than V5 despite cleaner final custody.

The helix stopping and final-evidence questions have now received the bounded
confirmation requested by review. Further helix tuning is not justified. The
next product experiment should move to varied tasks while preserving the
receipt-fenced final-checkpoint discipline. Context replay and discovery-call
volume should be measured as separate efficiency concerns rather than used to
justify new semantic orchestration.
