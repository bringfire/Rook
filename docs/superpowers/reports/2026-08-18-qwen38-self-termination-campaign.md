# Qwen3.8 Grasshopper Self-Termination Campaign Result

**Date:** 2026-08-18

**Protocol:**
`docs/superpowers/experiments/2026-08-17-qwen38-self-termination-campaign.md`

**Frozen protocol commit:**
`0986fc61933156acd318847362712e4672ec59fc`

**Evidence root:**
`C:/Users/bring/AppData/Local/Temp/rook-qwen38-self-termination-campaign-v1`

**Evidence-manifest SHA-256:**
`874CFC6545070C935100E41C665D80BEBEBA7742A3814961D9892A700B7F3AA2`

## Result

The model-led Prime/Rook loop is promising, but this cohort did not establish
reliable formal self-termination.

Qwen3.8 produced three semantically successful Grasshopper outcomes and one
semantic failure. It recorded formal Prime goal completion in only one of the
four rows. No row contained a false formal completion belief.

The dominant stopping failure was not inability to judge the Grasshopper
canvas. In the repair row, Qwen reached and behaviorally verified the correct
state in approximately three minutes, then spent approximately twenty minutes
trying to discover an unavailable Prime goal-completion affordance. Construction
ability, completion judgment, and Prime lifecycle closure are therefore
separate concerns.

| Row | Semantic result | Model outcome | Prime time | Gateway events | Provider-reported tokens |
|---|---|---|---:|---:|---:|
| T1 exact point row | `pass` | `completed_belief` | 458.4s | 49 | 875,726 |
| T2 open facade grid | `fail` | `interrupted` | 1281.0s | 90 | 2,363,232 |
| T3 repair in place | `pass` | `incomplete_reported` | 1405.5s | 96 | 6,860,401 |
| T4 adjustable helix | `pass` | `interrupted` | 1236.6s | 78 | 3,451,775 |

The token values are cumulative provider telemetry, not comparable to unique
context size. T2, T3, and T4 exceeded the protocol's frozen two-million-token
ceiling because that ceiling was recorded but not mechanically enforced by the
runner. Those rows remain useful evidence, but the resource-policy
nonconformance must not be hidden.

## Cohort Custody

The four rows used the unchanged frozen cohort:

- Prime commit `27b5be22cf0e0e81e324a59ebabbb41edfee6ec0`;
- Qwen `qwen3.8:27b` through Ollama `0.32.14`, medium reasoning;
- versioned Grasshopper skill SHA-256 `B333B5EC...0693DC53`;
- payload-first adapter SHA-256 `9B22757E...235C371`;
- Rook runtime commit `4a2adfa39657118924d57468b77ec0aa1c4b8991`;
- one unchanged tool surface and one Rhino process; and
- no runtime evaluator feedback, operator repair turn, prompt change, or
  between-row product tuning.

Post-run checks reproduced Prime, Node, Ollama manifest/layer, installed Rook
Python, and behavioral-acceptance hashes. Each row's 13-entry precontact
manifest still matched exactly. All four stderr files were empty and no
qualification-owned process remained.

## T1: Exact Point Row

Qwen created the requested native graph:

```text
Start -> Series.Start
Step  -> Series.Step
Count -> Series.Count
Series -> Construct Point.X
Construct Point.Y/Z use native zero defaults
```

It verified ten default points, perturbed the controls to produce
`(5,0,0)`, `(7,0,0)`, `(9,0,0)`, and `(11,0,0)`, restored the defaults, and
observed clean diagnostics.

The first retained passing evidence appeared 195.9 seconds after goal start.
Prime recorded completion 229.9 seconds later. Qwen reached Prime's lower-level
`goal.complete` host request after finding that the ordinary `goal` object was
not bound. This row demonstrates both semantic success and a functioning
underlying completion operation, but also avoidable completion discovery.

The legacy point-row shadow evaluator returned `incomplete` because an earlier
partial edit violated its stricter historical trace-admission rule. The retained
receipt-fenced model observations independently establish the behavioral pass;
the evaluator refusal is not rewritten as a semantic failure.

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

The unchanged legacy helix evaluator returned `incomplete` because Qwen used
five additional fixed-value sliders as numerical constants, raising the total
slider count above that evaluator's frozen maximum. Receipt-fenced point,
curve, diagnostic, and perturbation evidence still establishes the semantic
pass. This is another example of a shadow evaluator's bounded coverage, not a
reason to expand runtime semantic authority.

## What The Campaign Establishes

1. **The simple empirical loop works materially.** Qwen used discovery,
   metadata, mutation, snapshots, errors, receipts, and direct behavioral
   experiments to produce three viable definitions without runtime semantic
   evaluator feedback.

2. **Qwen can judge successful Grasshopper behavior.** T1, T3, and T4 include
   model-authored perturbation or geometry evidence, not merely clean canvases.

3. **Prime formal completion is the main cross-row operational defect.** Only
   T1 closed its goal. T3 proves this can dominate runtime after the model has
   already established success.

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

The next bounded product experiment should make Prime's existing goal
completion affordance reliably available in the versioned execution skill or
IPython environment, then run a new cohort. The desired behavior is simple:

```text
inspect final solved state
-> state professional conclusion
-> call the supported goal completion operation once
-> stop
```

This should be treated as affordance repair, not transactional containment. The
test must prove that a normal `/goal` session receives the completion object or
documented supported equivalent and that a dedicated final completion call
closes the goal without further Rook mutation.

Separately, T2 justifies focused investigation of Grasshopper data-tree and
Cartesian-grid reasoning. That should begin with better observation or skill
guidance only if repeated evidence localizes the same failure. It does not
justify another general orchestration subsystem.

## Evidence Index

The evidence root contains 121 hashed files plus its non-self-referential
manifest. Primary summaries are:

- `campaign-summary.json`;
- `runtime-custody-postrun.json`;
- each row's `prime.jsonl`, `source.jsonl`, target, process result, and stderr;
- T2's hidden final fenced snapshot;
- T3's post-run receipt-refusal record; and
- T4's fenced geometry probe and evaluator result.

All retained canvases remain untouched after their row's permitted hidden
inspection.
