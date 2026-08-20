# Prime Upstream T3 Compatibility Smoke V3 Execution

**Date:** 2026-08-19
**Status:** Pass; qualified for the exact frozen Rook/Qwen compatibility path
**Executions:** One authorized V3 transaction; zero retries

## Result

The exact V3 command completed naturally with:

```text
runner status       complete
semantic status     pass
goal status         complete
budget status       pass
custody status      pass
Prime exit code     0
agent_end count     1
owned child PIDs    0
```

This qualifies Prime commit `739400844f8f3f280414b0c7b9c65797208815d3`
for this exact frozen Rook/Qwen path. It is not universal Prime production
qualification and makes no claim about other models, tasks, skills, adapters,
Rook builds, or execution modes.

No retry, repair turn, tuning, alternate evidence root, accepted-smoke import,
or second transaction occurred.

## Pre-Contact Gates

The runner completed its frozen gates before target preparation:

```text
offline tests           222 passed, 11 existing warnings
runtime custody         pass
tool-surface custody    pass
goal preflight          pass
Python environment      pass
Prime worktree          clean
Rook worktree           clean
```

The model-free preflight observed the sealed external-kernel `goal` module at
its exact admitted path and the fork-modified `rlm` module under the frozen
Prime worktree. Both admitted `goal` files retained the exact SHA-256
`9A6F39CC...D4A`, `goal.get()` returned the disposable active goal, and
`goal.complete()` completed it before the T3 target was prepared.

## Seeded Failure

The fresh T3 target contained seven components and six wires. The working
Start, Step, Count, Series, and Construct Point components were interrupted by:

```text
Series -> Division -> Construct Point X
Fault Divisor (0) -> Division divisor
```

The fenced seed snapshot reported one `Division by zero` error and ten null
point outputs.

## Qwen Repair

Qwen used three committed `gh_edit` calls:

1. At source sequence 6, it disconnected the Division output, deleted the
   Division and Fault Divisor components, and connected Series directly to
   Construct Point X. Receipt: `9d66e33b1b86a56bbfc238eb9fe17231`.
2. At sequence 10, it set Start/Step/Count to `5/2/4` and observed four points
   at X = `5, 7, 9, 11`. Receipt:
   `e1911ad8b2f42b7245569bb1c3b888c5`.
3. At sequence 13, it restored Start/Step/Count to `0/1/10`. Receipt:
   `86cabf561c11a88e627e226a59882586`.

The final Actor-observed state contained:

```text
components      5
wires           4
errors          0
warnings        0
point count     10
points          (0,0,0) through (9,0,0)
controls        Start=0, Step=1, Count=10
```

Qwen preserved all five useful seeded components, removed only the two faulty
components, tested the three principal controls together, restored them, and
called `await goal.complete()` exactly once. No gateway call followed the final
`gh_errors` observation.

## Behavioral Evaluation

The silent evaluator admitted the closed 17-event authoring trace, selected
the final committed receipt `86cabf561c11a88e627e226a59882586`, waited for
solve readiness, and captured a receipt-fenced baseline snapshot.

It then perturbed Start, Step, and Count independently, fenced each solve,
restored each exact original value, and fenced each restoration. All eight
criteria passed:

```text
adjustable_start_present
adjustable_step_present
adjustable_count_present
point_count_equals_count
x_values_equal_start_step_count
all_y_zero
all_z_zero
no_runtime_errors
```

The baseline contained ten complete points from `(0,0,0)` through `(9,0,0)`
with zero errors and warnings. All six perturbation/restoration mutations used
unique managed receipts and every restoration returned `restored: true`.

### Receipt Boundary

Qwen's historical skill used `gh_status` followed by ordinary snapshots; its
own final snapshot did not include `readiness_receipt_id`. The Actor therefore
observed a fresh but unfenced final checkpoint.

The formal pass is supported because the silent operator subsequently waited
on Qwen's exact final receipt and obtained the fenced baseline before reading
or perturbing behavior. This run qualifies the frozen compatibility path, but
it is not independent evidence that this historical skill causes Qwen itself
to follow the newer model-facing receipt-fenced checkpoint discipline.

## Gateway And Lifecycle

All 17 source events used the frozen gateway adapter:

| Capability | Calls |
|---|---:|
| `gh_snapshot` | 4 |
| `rook_tools_read` | 4 |
| `gh_edit` | 3 |
| `gh_status` | 3 |
| `gh_errors` | 2 |
| `rook_tools_search` | 1 |

The source log closed at sequence 16 with terminal marker `agent_end`. Prime
retained 18 assistant responses, one `goal.complete()` call, and one
`agent_end`. The goal completed at 258,445 of 2,000,000 tokens with no
continuation.

## Telemetry

```text
Actor elapsed time             177.094 seconds
Prime goal time                164 seconds
provider input tokens          275,868
provider output tokens           5,728
provider total tokens          281,596
gateway events                      17
limit breach                       none
```

The final post-completion response accounts for the difference between Prime's
goal usage and the provider total. The runner correctly retained the full
provider total inside the campaign ceiling.

## Evidence

Evidence root:

```text
C:/UDEV/RookEvidence/2026-08-19-prime-upstream-t3-compatibility-smoke-v3
```

Independent manifest verification reproduced:

```text
entries              42/42
mismatches           0
manifest SHA-256     C3C1C1F52954C61E94145695487F9D094F8005770B8DD171E4A077BA86497DD5
```

Key evidence hashes:

| Artifact | SHA-256 |
|---|---|
| Hidden evaluation | `F70AA631BB748D7EC148EA4EAAF7CFBDCEEFE5892B0EDA5DF6AB9E7229655755` |
| Hidden probe | `6B4D49C05B23B0F2B675957BDB7BE4B9676A273818469C9B3321435A33627BA1` |
| Authoring trace | `5D55470001E1822841E049E4FD6674E3270401DA58E375C518D289DCF27A3069` |
| Source log | `49D3C6FA310C6AA21F8C45A5AF9BE0AA7591F174D6D569A28B012F66C9385819` |
| Prime JSONL | `C8E56DABFB465ED83E3837EB511B79CF4B06BECBCED7DFA95400EDD9D4260F1F` |
| Native session | `920C3E26EEAE69B89A5F3FCE3825BCDD0A61595A9DC0B29DBCE74DC8B7369F3C` |
| Runtime custody | `B887469815F4E2A13BDDF5017E7EEB4A6F97861C4EAD5ACA2E05B16786661928` |
| Goal preflight | `60390BC129EBA4666A2A54C95B53A2874E0B897A73F0AE57BDE7A77A13EB709F` |

The runner-reported root PID no longer exists, retained `ownedChildPids` is
empty, both source worktrees are clean, and no qualification-owned process
remains.

## Disposition

The exact upstream-plus-structured-error Prime baseline is compatible with the
frozen Rook/Qwen T3 path. The prior V1 refusal was a custody-policy mismatch,
not a Prime runtime failure; V2 corrected and qualified the content-equivalent
external-kernel goal boundary, and V3 now demonstrates one successful live
transaction through that boundary.

No broader configuration promotion, deployment, additional smoke, or product
change is authorized by this result.
