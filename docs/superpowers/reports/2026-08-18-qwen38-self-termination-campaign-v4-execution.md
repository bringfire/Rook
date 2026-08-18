# Qwen3.8 Self-Termination Campaign V4 Execution

Date: 2026-08-18

Classification: **qualified low-thinking screening execution with mixed model outcomes**

## Scope

V4 changed one operational variable from the qualified V3 campaign: Prime's
Qwen3.8 thinking level moved from `medium` to `low`. It retained the V3 runner,
model and Ollama bytes, Prime commit, sealed Python kernel, Rook build, tool
surface, skill, adapter, task prompts, target preparation, resource limits, and
silent post-run evaluation. V4 omitted the redundant exact point-row row and
executed:

    T3 repair smoke
    -> T2 open grid
    -> T4 helix

No evaluator result was returned to Qwen. No configuration changed between
rows. This is one screening observation per task, not proof that thinking level
caused every observed difference.

The V3 report correction, V4 protocol, runner support, and tests were committed
before contact:

    e75ed7c5  test: screen Qwen self-termination at low thinking

Frozen input identities included:

    Prime commit:
    27b5be22cf0e0e81e324a59ebabbb41edfee6ec0

    V4 protocol SHA-256:
    7F5C500ABE5BA0E7005AEC003EF3B2A1952C71864D5CD053FD97BBA046A5BD38

    campaign runner SHA-256:
    12F9649CDEDBC58F2388A5C62F416C4FA466097C8BC26AA56D96E634C4B0897B

    Prime skill SHA-256:
    13FB486CE69C0681CF2F12A7D8F391AAEBF146363DD7A37B04C50E08A9D81696

    rook_full adapter SHA-256:
    06F1CB4AA58FD8C4C6F61F96CE7B8A5F4FEF7B6B126D00C0550B2CB3AA0BBF74

Each retained native Prime session contains exactly one
`thinking_level_change` record with `thinkingLevel: low` and no conflicting
thinking-level record.

## Execution

    & C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe
      scripts/qwen38_self_termination_campaign_runner.py run
      --protocol docs/superpowers/experiments/2026-08-18-qwen38-self-termination-campaign-v4.json
      --evidence-root C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v4
      --document-serial 268435457

The smoke gate passed and the runner continued through all three rows without
operator intervention, evaluator feedback, retry, or configuration change.

| Row | Semantic | Goal | Budget | Row custody | Seconds | Provider tokens | Gateway calls |
|---|---|---|---|---|---:|---:|---:|
| T3 repair | pass | complete | pass | pass | 178.375 | 362,411 | 24 |
| T2 open grid | shadow unproven | complete | pass | pass | 751.734 | 1,737,815 | 72 |
| T4 helix | incomplete | budget_limited | fail | fail | 829.937 | 2,067,953 | 70 |

Provider telemetry separated input and output observations as follows:

| Row | Completed model responses | Input tokens | Output tokens |
|---|---:|---:|---:|
| T3 | 37 | 353,902 | 8,509 |
| T2 | 81 | 1,695,113 | 42,702 |
| T4 | 97 | 2,012,964 | 54,989 |

## V3 Medium Versus V4 Low

The low-thinking rows finished or were terminated sooner, but tool use did not
become uniformly more efficient:

| Row | Time change | Token change | Gateway-call change |
|---|---:|---:|---:|
| T3 | -13.0% | -18.9% | -4.0% |
| T2 | -11.5% | -5.8% | +33.3% |
| T4 | -7.6% | -0.9% | +59.1% |

The sample is too small to attribute these differences generally to thinking
level. It does establish that `low` did not by itself cure expensive repeated
observation or guarantee bounded completion.

## T3 Formal Pass

T3 repaired the seeded divide-by-zero point-row definition and independently
passed all eight retained criteria:

- adjustable Start, Step, and Count controls;
- point count equal to Count;
- X values equal to Start + i * Step;
- Y and Z fixed at zero; and
- zero runtime errors.

Qwen exercised Start, Step, and Count, restored their original values, called
Prime's documented `goal.complete()` seam, and closed normally. The external
receipt-fenced evaluator then performed its own perturbation and restoration
cycle and passed 8/8.

Compared with V3 medium, this row used 26.656 fewer seconds and 84,653 fewer
provider-reported tokens. That is a favorable screening observation, not a
general low-thinking qualification.

## T2 Shadow Assessment

T2 produced a clean native rectangular point grid:

    14 components
    16 wires
    1 group
    4 controls: nCols, nRows, spacingX, spacingY
    20 points
    0 errors
    0 warnings

The final default was a 5 by 4 lattice anchored at the world origin, with X
spacing 300 and Y spacing 200. The retained final model-authored snapshot shows
all 20 points in row-major order from `(0,0,0)` through `(1200,600,0)`.

Qwen first attempted invalid temporary IDs and received an exact admission
refusal before mutation. It then built a Series-pair/Cartesian Product
candidate, observed an incompatible-cardinality error, deleted that candidate,
and rebuilt using a flat index:

    total = nCols * nRows
    index = Series(0, 1, total)
    column = index mod nCols
    row = index integer-div nCols
    X = column * spacingX
    Y = row * spacingY
    Point(X, Y, 0)

It changed all four controls to `3, 6, 500, 100`, observed the resulting 18
points, restored `5, 4, 300, 200`, verified a clean final state, disclosed its
origin, spacing, integer-count, and row-major choices, and completed the Prime
goal.

This is a credible semantic success for the intentionally underspecified task,
but it is not a formal evaluator pass. The hidden evaluator conservatively
returned `authoring_trace_invalid`: the early pre-mutation
`gh_edit_admission_failed` event was retained as an unknown mutation outcome,
so the evaluator made no additional host call and admitted no final fenced
observation. The final model-authored snapshot remains useful shadow evidence;
it is not silently promoted to receipt-fenced authority.

Operationally, low T2 was 97.860 seconds and 107,942 tokens below medium T2,
but used 18 more gateway calls. The row still consumed 12.5 minutes and 1.74
million cumulative provider tokens. Low thinking therefore produced only a
modest resource improvement on this task.

## T4 Incomplete Outcome

T4 built a mechanically healthy adjustable helix candidate:

    25 components
    29 wires
    1 group
    5 principal controls: Radius, Height, Turns, Start Angle, Resolution
    60 default points
    1 interpolated NURBS curve
    default curve length 74.4820589705733
    0 errors
    0 warnings

At the final restored state, retained point evidence shows radius 5, Z from 0
to 40, approximately two angular turns, and 60 points. The graph implements
normalized progression, radians conversion, sine/cosine XY coordinates,
height-scaled Z, Construct Point, and Interpolate.

Qwen changed Radius from 5 to 8, Turns from 2 to 3, Start Angle from 0 to 90
degrees, and Resolution from 60 to 12 in one combined exercise. The observed
12-point result had radius 8, Z from 0 to 40, and curve length
151.33838323108526. It then restored all principal values to
`5, 40, 2, 0, 60`, observed the original points and curve length again, and
retained clean diagnostics. Height was restored but was not independently
perturbed.

The row improved materially over V3's semantic path:

- it used the correct approximately 74.484 analytic length for the final
  two-turn helix;
- it did not construct SciPy or hand-coded spline oracles;
- it exercised and restored four principal controls;
- it used Rook's canvas image and focus capabilities to inspect the result; and
- it explicitly reasoned that the definition was complete and clean.

The row still failed completion and budget custody. After acknowledging that it
had already confirmed the endpoint, turns, radius, and curve length, Qwen chose
another full 60-point snapshot to be "100% sure." The provider ceiling was
crossed on that next tool-use response. The runner mechanically detected and
terminated the row after the first provider report above 2,000,000 tokens, with
the expected one-message overshoot to 2,067,953. Prime never reached
`goal.complete()`.

The hidden evaluator correctly returned `incomplete` because the killed Prime
stream had no valid terminal marker. No post-run host inspection or semantic
upgrade occurred. The mechanically healthy state described above comes only
from the already retained model-authored snapshots.

The final graph also exposes four implementation constants (`0`, `1`, `360`,
and approximately `2*pi`) as NumberSliders rather than fixed values. The five
requested controls work at the observed defaults, but those extra adjustable
internals make the definition less robust than its presentation implies. This
is a model design-judgment limitation, not a Rook observation failure.

## Resource And Custody Result

The runner mechanically enforced, per row:

- Prime goal token budget: 2,000,000;
- provider-reported token ceiling: 2,000,000, detected and terminated after
  the first provider `message_end` above the limit, with a possible one-message
  overshoot;
- wall-clock ceiling: 1,800 seconds; and
- gateway-call ceiling: 150 before transport.

The preflight proved the sealed Python executable, exact imported module paths,
active disposable goal, 2,000,000-token budget, successful completion, and
kernel closure. The campaign retained zero qualification-owned processes.

V4 retained the exact pre-contact command, stdout, stderr, and result before
model contact:

    145 passed, 11 existing warnings
    exit code: 0
    stdout SHA-256:
    5308620F78753B4D440B515DF165FC57C2502DFD09D6BDD494D4C8CDC1B95
    stderr: empty

Durable evidence:

    C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v4

    manifest entries: 96
    manifest mismatches: 0
    manifest SHA-256:
    99A1D37E45A4410CC668A53CB6ADD97A827C8080201C389C3F3BA9F5A4F9BF16

    campaign summary SHA-256:
    0E37C13251E76083B989F556D52F9C336CF893CCA223C08D352DECBE97963D68

Independent post-run manifest verification reproduced 96 entries and zero
mismatches.

## Bounded Conclusion

V4 supports four bounded conclusions:

1. Low thinking preserved the formally qualified T3 repair capability and was
   modestly faster and cheaper on all three sampled rows.
2. Low T2 remained a credible open-ended design success, but it was still slow,
   call-heavy, and only shadow-qualified.
3. Low T4 reasoned more accurately and exercised the artifact more usefully
   than medium T4, but still failed to stop within the resource budget.
4. The retained terminal thought identifies the immediate failure precisely:
   Qwen knew the result was complete, knew the requested facts were already
   established, and nevertheless requested another equivalent final check.

Low thinking should not be promoted as the default from this screening cohort,
and an unchanged confirmatory repeat is not yet justified because T4 did not
pass. The smallest evidence-led correction is behavioral guidance in the
versioned Prime skill: once fresh post-solve evidence satisfies the request and
no contradictory evidence remains, repeated equivalent checks are not
material investigation; summarize the evidence and call `goal.complete()`.

That correction should receive one focused T4-like retest before any broader
cohort or thinking-level promotion. The T2 pre-mutation refusal classification
is a separate narrow evidence-admission issue and should not be conflated with
Qwen's stopping behavior.

V4 does not justify a terminalization protocol, semantic supervisor, new
acceptance vocabulary, or lower thinking level. It justifies one small skill
clarification and one causal retest.
