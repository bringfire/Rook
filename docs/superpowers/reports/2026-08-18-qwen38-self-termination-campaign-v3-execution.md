# Qwen3.8 Self-Termination Campaign V3 Execution

Date: 2026-08-18

Classification: **qualified execution with mixed model outcomes**

## Scope

V3 repeated the frozen four-row Qwen3.8 self-termination campaign after closing
the V2 Python-runtime custody defect. It retained Prime's active-goal loop,
medium thinking, the same task prompts, the same Rook tool surface, hard
resource limits, fresh Grasshopper documents, and silent post-run evaluation.
No semantic evaluator result was returned to the Actor.

The correction was committed before contact:

    05582b8d  fix: seal Qwen campaign Python runtime custody

V3 added exact Windows import and DLL paths, a normal-kernel preflight that
imports goal, rlm, and the versioned rook_full, and recursive pre/post-row
manifests for the shared kernel and installed Rook Python support surface. The
frozen kernel contains the exact post-V2 bytes; V3 claims an unchanged,
explicitly identified runtime, not a pristine reconstructed one.

## Execution

    & C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe
      scripts/qwen38_self_termination_campaign_runner.py run
      --protocol docs/superpowers/experiments/2026-08-18-qwen38-self-termination-campaign-v3.json
      --evidence-root C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v3
      --document-serial 268435457

The smoke gate passed and the runner continued through all four rows without
operator intervention, evaluator feedback, retry, or configuration change.

| Row | Semantic | Goal | Budget | Row custody | Seconds | Provider tokens | Gateway calls |
|---|---|---|---|---|---:|---:|---:|
| T3 repair | pass | complete | pass | pass | 205.031 | 447,064 | 25 |
| T1 exact row | pass | complete | pass | pass | 355.578 | 641,792 | 40 |
| T2 open grid | shadow unproven | complete | pass | pass | 849.594 | 1,845,757 | 54 |
| T4 helix | incomplete | budget_limited | fail | fail | 897.844 | 2,085,831 | 44 |

Every baseline, pre-row, and post-row Python-environment record has zero
mismatches. T4's row-custody failure means abnormal goal/process closure after
the enforced provider ceiling; its Python environment still matched exactly.

## T3 And T1

T3 repaired the seeded point-row definition and T1 built the same behavior on a
fresh canvas. Both independently passed all eight retained criteria:

- adjustable Start, Step, and Count controls;
- point count equal to Count;
- X values equal to Start + i * Step;
- Y and Z fixed at zero; and
- zero runtime errors.

Both called Prime's documented goal.complete() seam and closed normally. The
completion-affordance failure from the earlier campaign did not recur.

## T2 Shadow Assessment

T2 produced a clean and useful native rectangular facade grid:

    12 components
    12 wires
    1 group
    4 controls: Width, Depth, Spacing X, Spacing Y
    90 points
    72 cells
    0 errors
    0 warnings

The final default was 12 by 9 units with 1.5 by 1.0 spacing. Qwen investigated
the Rectangular Grid port semantics, used floor-based cell counts, perturbed
Spacing X from 1.5 to 2.0, observed the changed grid, restored 1.5, and then
completed the goal. Its final response explicitly disclosed that floor-based
counts fit within the requested dimensions and may leave a short far-edge
remainder for non-divisible inputs. It also disclosed the world-origin and XY
orientation choices.

This is a credible behavioral success for the intentionally underspecified
request. It remains a shadow judgment rather than a formal deterministic pass;
the runtime correctly recorded unproven instead of inventing a universal grid
evaluator.

## T4 Incomplete Outcome

T4 eventually produced a mechanically healthy native helix candidate:

    21 components
    22 wires
    1 group
    5 principal controls: Radius, Height, Turns, StartAngle, Resolution
    96 points
    1 interpolated NURBS curve
    curve length 63.62078641963602
    0 errors
    0 warnings

The retained point previews support radial XY motion and monotonic Z. The graph
implements normalized range, angular progression, sine/cosine XY coordinates,
height-scaled Z, Construct Point, and Interpolate.

The row is nevertheless incomplete. Qwen never perturbed and restored the final
five controls, never called goal.complete(), and crossed the provider-token
ceiling. After reaching a clean final graph and a first turn_end, it spent a
large continuation reconstructing and checking curve-length behavior with
SciPy and custom B-spline calculations inside IPython. It made no additional
Rook mutation during most of that tail.

This is not an infrastructure failure and not proof that Qwen cannot build a
helix. It is direct evidence of excessive deliberation and weak self-termination
at the frozen medium thinking level.

## Resource And Custody Result

The runner mechanically enforced, per row:

- Prime goal token budget: 2,000,000;
- provider-reported token ceiling: 2,000,000;
- wall-clock ceiling: 1,800 seconds; and
- gateway-call ceiling: 150 before transport.

The preflight proved the sealed Python executable, exact imported module paths,
active disposable goal, 2,000,000-token budget, successful completion, and
kernel closure. The campaign retained zero qualification-owned processes.

Durable evidence:

    C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v3

    manifest entries: 124
    manifest mismatches: 0
    manifest SHA-256:
    D6D88FBEBC8788FF7ABED7DA097D338C3C1A809F5C0CAA3616AF28D1D36A6CBE

    campaign summary SHA-256:
    CE7A052CFF3370AADDC3614F17F01E82A7D1388A02FC59F56824CD40552CE5FF

Pre-contact verification passed 138 tests with 11 existing DSPy warnings.

## Bounded Conclusion

The primary infrastructure questions are now closed for this cohort:

- Prime's bundled goal skill works in the campaign kernel.
- The payload-first Rook adapter works.
- The normal Windows kernel starts reliably with explicit import/DLL custody.
- The shared Python environment stayed unchanged across all four rows.
- Hard resource limits and durable evidence custody worked.

Qwen3.8 can repair and build the exact point-row task and can complete a useful
underspecified grid with honest design disclosures. The remaining dominant
failure is operational: medium thinking can continue far beyond a viable
solution, particularly on geometry-bearing work.

The next smallest experiment is a new cohort that changes only Qwen's thinking
level one notch lower. It should reuse the V3 runner and custody boundary and
focus first on T2 and T4. No terminalization protocol, semantic supervisor, or
new acceptance vocabulary is justified by V3.
