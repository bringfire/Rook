# Qwen3.8 Grasshopper Self-Termination Campaign Result

**Date:** 2026-08-18

**Protocol:**
`docs/superpowers/experiments/2026-08-17-qwen38-self-termination-campaign.md`

**Frozen protocol commit:**
`0986fc61933156acd318847362712e4672ec59fc`

**Qualification status:** `not_qualified`

**Durable partial-evidence root:**
`C:/UDEV/RookEvidence/2026-08-18-qwen38-self-termination-campaign-v1-partial`

**Durable partial-evidence manifest SHA-256:**
`9667506C1939F5111409F9FCFB9D7A64A025654AFDC0EA69FAAAA0AB651AB797`

## Result

The model-led Prime/Rook loop produced encouraging observations, but this
campaign is not qualified. Its original Temp evidence root lost 84 of 121
manifested files after the run, including all 36 T1 files. T1 is therefore an
unreviewable retained finding, not part of a verified aggregate result.

The original run was interpreted as three semantic successes and one semantic
failure. Surviving primary evidence supports the substantive T2-T4
observations, but the original three-pass/one-fail aggregate is no longer
independently reproducible. Prime recorded formal goal completion only in the
now-missing T1 evidence.

T3 directly establishes one important stopping defect: Qwen reached and
behaviorally verified the correct state in approximately three minutes, then
spent approximately twenty minutes trying to discover an unavailable Prime
goal-completion affordance. The runner both froze `enableBuiltinSkills: false`,
which excluded Prime's bundled `goal` Python skill, and forced an external
`PRIME_AGENT_KERNEL_PYTHON`. Prime treats that override as preprovisioned and
warns/disables missing Python skills rather than installing them. The surviving
T3 session proves that `goal` was not importable in the effective kernel. This
was a campaign-bootstrap defect, not a missing Prime public API and not a Rook
defect. It is a plausible contributor to other incomplete closures, but T4 does
not prove the same causal path and T2 was a genuine semantic failure.

| Row | Semantic result | Model outcome | Prime time | Gateway events | Provider-reported tokens |
|---|---|---|---:|---:|---:|
| T1 exact point row | `pass` (unreviewable) | `completed_belief` (unreviewable) | 458.4s | 49 | 875,726 |
| T2 open facade grid | `fail` | `interrupted` | 1281.0s | 90 | 2,363,232 |
| T3 repair in place | `pass` | `incomplete_reported` | 1405.5s | 96 | 6,860,401 |
| T4 adjustable helix | `pass` | `interrupted` | 1236.6s | 78 | 3,451,775 |

The token values are cumulative provider telemetry, not comparable to unique
context size. T2, T3, and T4 exceeded the protocol's frozen two-million-token
ceiling because that ceiling was recorded but not mechanically enforced by the
runner. Their semantic artifacts remain useful, but runtime and
self-termination measurements are not qualified under the declared resource
contract.

## Cohort Custody

Recovered launch records show that the four rows used these intended cohort
inputs:

- Prime commit `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`;
- Qwen `qwen3.8:27b` through Ollama `0.32.14`, medium reasoning;
- versioned Grasshopper skill SHA-256 `B333B5EC...0693DC53`;
- payload-first adapter SHA-256 `9B22757E...235C371`;
- Rook runtime commit `4a2adfa39657118924d57468b77ec0aa1c4b8991`;
- one unchanged tool surface and one Rhino process; and
- no runtime evaluator feedback, operator repair turn, prompt change, or
  between-row product tuning.

At initial campaign close, post-run checks reproduced Prime, Node, Ollama,
installed Rook Python, and behavioral-acceptance hashes. That claim cannot now
be re-audited for the complete campaign because the Temp root was not durable.

The surviving bytes were copied unchanged to the durable partial-evidence root.
Using extended Win32 paths, 37 original manifest entries verify, 84 are missing,
and none of the surviving entries mismatch. Conventional Windows APIs report
only 36 because `T3/nul` is a real 102-byte file whose reserved name is otherwise
treated as the null device. The exact reconciliation is retained in
`custody-reconciliation.json`.

The orchestrating Codex task log separately retained the exact Prime launch
commands and the settings inspection. A 14-record extract is preserved as
secondary evidence with SHA-256
`BD20E40C84F9335F7906134F887C1767EF9843836C9EA5CBE255D378E9510648`.
It proves launch configuration but does not replace missing primary row
evidence.

A post-review, non-provider Prime check also found that the current managed
kernel bootstrap is not a working Windows fallback: the focused bundled-goal
test stops before the skill bridge because bootstrap targets
`kernel-venv/bin/python`, while the created Windows environment exposes
`Scripts/python.exe`. This did not cause the campaign, which forced an external
kernel. It does mean that removing the override is not yet a qualified repair.

## T1: Exact Point Row

T1's complete primary evidence is missing. The following is the original
post-run interpretation and is retained for historical continuity, but it is
not independently reviewable.

Qwen was observed creating the requested native graph:

```text
Start -> Series.Start
Step  -> Series.Step
Count -> Series.Count
Series -> Construct Point.X
Construct Point.Y/Z use native zero defaults
```

It was observed verifying ten default points and perturbing the controls to produce
`(5,0,0)`, `(7,0,0)`, `(9,0,0)`, and `(11,0,0)`, restored the defaults, and
observed clean diagnostics.

The originally retained passing evidence appeared 195.9 seconds after goal start.
Prime recorded completion 229.9 seconds later. Qwen reached Prime's lower-level
`goal.complete` host request after finding that the ordinary `goal` object was
not bound. The row was originally interpreted as semantic success plus a
functioning lower-level completion operation, but the missing primary evidence
prevents that interpretation from being independently confirmed now.

The original legacy point-row shadow evaluator returned `incomplete` because an earlier
partial edit violated its stricter historical trace-admission rule. Those
receipt-fenced model observations are among the missing files, so neither the
behavioral pass nor that evaluator attribution is currently reviewable.

## T2: Underspecified Facade Grid

Qwen produced a mechanically healthy definition with 26 components, 31 wires,
231 points, and no errors or warnings. The geometry was not a Cartesian XY grid.
It consisted of repeated diagonal bands with samples such as:

```text
(0,0), (3,3), ..., (30,30), (33,30), ...
```

This is a genuine semantic construction failure, not a Prime completion-only
failure. Qwen began another correction and stated an intention to use Partition
List, but Prime ended while the goal was active. It did not make a final success
claim, so the row is `interrupted`, not false completion.

## T3: Repair In Place

The seeded document contained Start, Step, Count, Series, Division, a zero
divisor, and Construct Point. Qwen correctly diagnosed and removed the broken
division path while preserving the working control and Series subgraph.

Timing separates task performance from lifecycle behavior:

```text
~175s  correct clean default state observed
~206s  behavior perturbed, verified, and restored
~1406s Prime process ended
```

The probe changed Start, Step, and Count to produce
`10`, `12.5`, `15`, and `17.5`, then restored the original values. The task was
substantively complete after about 3 minutes 26 seconds.

For roughly the next twenty minutes, Qwen searched for ways to close the Prime
goal. It attempted or investigated `goal_complete`, `goal_status`,
`agent_goal_complete`, `rook_goal_complete`, `prime_goal_complete`, and related
names. Prime re-injected active-goal context 54 times. Qwen repeatedly explained
that the Grasshopper work was complete but the formal goal object was absent.

Prime eventually ended with the goal still active. This row is classified as
`incomplete_reported` because Qwen truthfully identified the formal closure
blocker rather than falsely claiming Prime lifecycle completion.

By post-run inspection time, the final solve receipt had been evicted; Rook
correctly refused the additional fenced snapshot. No unfenced salvage was used.
The earlier model-authored fenced snapshots and restored probe retain the
semantic evidence.

## T4: Adjustable Helix

Qwen created and corrected a 27-component, 31-wire native definition producing:

- 65 ordered points;
- one interpolated NURBS curve;
- radius mean `60` with negligible numerical spread;
- angular span approximately `25.136` radians;
- monotonic Z span `1200`; and
- zero errors and warnings.

It exercised radius, height, turns, start angle, and resolution, then restored
all five controls. The first retained passing helix evidence appeared about
1057.6 seconds after goal start. Unlike T3, most of this row's duration was real
construction, correction, and inspection work; only a short tail followed final
verification.

Prime emitted `agent_end` while the goal remained active. The last assistant
message stated that defaults had been restored and final acceptance passed, but
no supported Prime goal outcome was recorded, so the model outcome is
`interrupted`.

The retained top-level legacy helix evaluator reports only
`behavioral_evidence_unavailable`. During the original analysis this was
attributed to Qwen's five additional fixed-value sliders exceeding the
evaluator's frozen slider maximum, but the lower-level diagnostic establishing
that exact cause was not preserved. The attribution is therefore not a
qualified claim. Receipt-fenced point, curve, diagnostic, and perturbation
evidence still supports the substantive helix result.

## What The Retained Evidence Supports

1. **The simple empirical loop worked materially in retained T3 and T4
   evidence.** Qwen used discovery, metadata, mutation, snapshots, errors,
   receipts, and direct behavioral experiments without runtime semantic
   evaluator feedback. T2 retains a counterexample where the same loop produced
   clean but semantically wrong geometry.

2. **Qwen can judge successful Grasshopper behavior in some tasks.** T3 and T4
   retain model-authored perturbation or geometry evidence, not merely clean
   canvases. T1 was originally consistent with this finding but is now
   unreviewable.

3. **Missing Prime goal-skill bootstrap dominated T3's runtime.** T3 proves this
   can dominate runtime after the model has already established success. It is
   a plausible contributor elsewhere, not a proven cross-row cause.

4. **There is still a real model-semantic limit.** T2's clean but wrong geometry
   shows that trustworthy observations and self-inspection do not guarantee
   correct open-ended construction.

5. **The historical evaluators remain useful as shadow probes, not universal
   runtime gates.** Their refusals exposed bounded assumptions without changing
   the semantic evidence or feeding corrections to Qwen.

6. **The campaign runner did not enforce its token ceiling.** A future cohort
   needs a real outer resource stop or must remove the claimed limit. Recording
   an unenforced ceiling is not sufficient custody.

## Next Smallest Step

Do not resume the suspended terminalization state-machine plan and do not add a
semantic supervisor.

The next bounded correction belongs to the campaign runner and Prime's existing
goal-skill bootstrap. Do not teach `rook_full` to call Prime's lower-level host
protocol. Prime already ships `goal.get()` and `goal.complete()` and pre-imports
the `goal` module when the bundled skill is selected and importable in the
effective kernel.

The runner must set `enableBuiltinSkills: true` and, until the separate Windows
managed-bootstrap issue is repaired, use a sealed external kernel containing
every selected skill. Before model contact, a non-live preflight must prove
that an ordinary active-goal IPython session exposes `goal`, that
`await goal.get()` returns the active goal, and that a dedicated
`await goal.complete()` records completion. Configuration bytes, the effective
Python executable, and the imported `goal.__file__` must be retained. The
versioned Grasshopper skill should instruct Qwen to report an infrastructure
blocker immediately if that documented affordance is unexpectedly absent.

The corrected runtime behavior remains simple:

```text
inspect final solved state
-> state professional conclusion
-> call the supported goal completion operation once
-> stop
```

This is runner configuration and bootstrap qualification, not transactional
containment. The corrected runner must also set Prime's existing goal budget,
verify the resulting goal context before model contact, and enforce an outer
watchdog against the same declared provider-telemetry ceiling.

Separately, T2 justifies focused investigation of Grasshopper data-tree and
Cartesian-grid reasoning. That should begin with better observation or skill
guidance only if repeated evidence localizes the same failure. It does not
justify another general orchestration subsystem.

## Evidence Index

The durable partial-evidence root contains 40 hashed files plus its
non-self-referential manifest. Primary custody records are:

- `custody-reconciliation.json`;
- `recovered-codex-launch-events.jsonl`;
- the original, now-incomplete `evidence-manifest.json`;
- surviving T2-T4 row artifacts; and
- the original campaign summary and post-run custody records, retained as
  historical artifacts rather than current proof.

No T1 primary file was recovered. The original three-pass/one-fail aggregate
must not be cited as independently verified from this archive.
