# Optional Python Skill Sine-Wave Confirmation V1

**Date:** 2026-08-19
**Status:** Complete execution; credible shadow success
**Live rows:** One, `PY1`
**Reruns:** None

## Question

Does the empirically qualified Python Grasshopper lane remain effective when it
is packaged as a clean optional Prime skill, explicitly selected on reconciled
Prime baseline `739400844`, and used for a task from a third computational
family?

The exact prompt was:

> Create an adjustable sine-wave polyline in the XZ plane. Expose Length,
> Amplitude, Waves, and integer Samples controls. Produce exactly Samples
> ordered points from X=0 to Length with Y=0 and
> Z=Amplitude*sin(2*pi*Waves*X/Length), plus one polyline curve through them.
> Exercise Amplitude and Waves independently, observe each effect, restore
> defaults, obtain a final same-receipt fenced observation, and call
> goal.complete(). Do not bake or add unrelated geometry.

The Python lane body, model, low thinking level, Rook build, adapter, budgets,
target preparation, silent evaluation, evidence capture, and receipt-fenced
completion discipline were frozen. The Prime baseline, optional-skill packaging
and explicit selection, and task differed from the earlier confirmations.

This is one prospective product-path confirmation. It is not a causal estimate,
universal Prime qualification, or proof that Python is the best authoring lane
for every Grasshopper task.

## Result

Row `PY1` completed naturally and is independently judged `credible_success`:

| Observation | Result |
|---|---:|
| Prime exit | 0 |
| Goal status | `complete` |
| Formal semantic status | `unproven: independent_judgment_required` |
| Shadow disposition | `credible_success` |
| Actor final checkpoint | pass |
| Budget / custody | pass / pass |
| Elapsed time | 300.219 s |
| Gateway calls | 24 |
| Discovery calls | 6 |
| Mutation attempts / commits | 6 / 6 |
| Refused or failed calls | 0 |
| Input tokens | 501,585 |
| Output tokens | 16,352 |
| Provider tokens | 517,937 |
| Final components / wires | 5 / 4 |
| Final errors / warnings | 0 / 0 |

The formal semantic result remains `unproven` by design. The evaluator was
silent during execution and delegates this open task to independent judgment.

## Optional Skill Selection

Prime loaded exactly one explicitly selected external skill:

```text
prime-execute-grasshopper-python
```

The runner staged that skill outside the default skill directory, supplied its
exact path through Prime's supported `--skill` argument, and began the goal with
`/skill:prime-execute-grasshopper-python`. The unselected external-skill set was
empty. The canonical native Grasshopper skill remained unchanged and was not
selected. No automatic router or default installation was introduced.

The packaged body is byte-for-byte identical to qualified fixture
`E70095B5...4AD6`; only the Prime skill name and description package it as an
optional resource. Its checkpoint reference carries the current final receipt,
readiness wait, same-receipt snapshot, and completion ordering.

## Final Definition

The independent final fenced observation retained:

```text
Length       10
Amplitude     1
Waves         1
Samples      10

1 Python 3 Script component, nicknamed Sine Wave
4 Number Sliders
4 wires
10 complete projected points
1 PolylineCurve preview
0 errors
0 warnings
```

All four sliders connect directly to the corresponding Python inputs. The final
point projection is complete:

```text
(0,                  0,  0)
(1.1111111111111112, 0,  0.6427876096865393)
(2.2222222222222223, 0,  0.9848077530122080)
(3.3333333333333330, 0,  0.8660254037844387)
(4.4444444444444450, 0,  0.3420201433256689)
(5.5555555555555550, 0, -0.3420201433256687)
(6.6666666666666660, 0, -0.8660254037844385)
(7.7777777777777780, 0, -0.9848077530122081)
(8.8888888888888900, 0, -0.6427876096865396)
(10,                 0, -2.4492935982947064e-16)
```

These are the ten ordered samples of the requested function for the retained
defaults, within ordinary floating-point precision. X begins at zero and ends
at Length, every Y coordinate is zero, and the Z values match one sine cycle.

The retained Python source computes:

```python
L = float(Length)
A = float(Amplitude)
W = float(Waves)
N = int(Samples)
if N < 2:
    N = 2

pts = []
for i in range(N):
    t = i / float(N - 1)
    x = L * t
    z = A * math.sin(2.0 * math.pi * W * t)
    pts.append(rg.Point3d(x, 0.0, z))

Points = pts
Polyline = rg.Polyline(pts)
```

The source enforces integer sample count at the script boundary. The retained
snapshot does not expose slider step granularity, so no claim is made that the
Samples slider itself advances only by integers.

The host projected one output item as `Rhino.Geometry.PolylineCurve`. The
polyline-through-points claim is supported jointly by that preview and the
retained source; this run did not project the curve's vertices independently.

## Empirical Loop

Qwen read the six required capability contracts directly, took an initial
empty-canvas snapshot, and made no capability search. Its first mutation was a
successful `gh_create_script` at source sequence 7. It then created the four
sliders and all four connections in one `gh_edit` call.

The resulting definition solved cleanly. Qwen then performed the required
independent exercises:

1. Amplitude changed from 1 to 3. After readiness, the retained points showed
   the same X values and every nonzero Z value scaled by exactly three.
2. Amplitude was restored from 3 to 1, returning the solved values to baseline.
3. Waves changed from 1 to 3. After readiness, the retained points showed the
   expected three-cycle sampled pattern over the unchanged X span.
4. Waves was restored from 3 to 1 as the final terminal mutation.

The two effect snapshots and the intermediate restoration snapshot followed
successful readiness waits but did not carry receipt fence arguments. They are
credible post-readiness observations, not formally receipt-fenced probes. The
final restoration has stronger custody.

Qwen retained final receipt
`c5a2bdf77a15a00f0bff9f2a80249c9a`, waited until it was ready, and supplied
that exact receipt to the final snapshot. The checkpoint sequences were:

```text
final mutation  21
readiness wait  22
fenced snapshot 23
```

The fenced snapshot was the final gateway event. Qwen audited the objective,
called `goal.complete()` as a dedicated final action, made no later Rook call,
and emitted exactly one terminal `agent_end`.

## Shadow Adjudication

### `sine_points_match_requested_formula`

**Observed and supported.** All ten final points were retained. Their ordered
coordinates match the requested default-domain sine samples, every Y is zero,
and the endpoints are X=0 and X=10.

### `samples_count_and_polyline_are_credible`

**Credible.** The complete point projection contains exactly ten items for
Samples=10. The source casts Samples to an integer and builds one Rhino
polyline from those points; the host previews one `PolylineCurve`. Slider step
granularity and independent curve-vertex projection remain unobserved.

### `amplitude_and_waves_are_causal_and_restored`

**Credible.** Amplitude scaled the retained Z values without changing X, and
Waves changed the sampled frequency while retaining the same span. Both controls
returned to their defaults before the final fenced snapshot. The effect
snapshots were post-readiness but unfenced, which limits the strength of this
claim without contradicting it.

### `python_lane_and_scope_are_respected`

**Observed and supported.** All 24 calls used the canonical gateway. Qwen used
the explicitly selected Python skill, made no capability search, created one
Python component plus ordinary controls, did not switch to native or C#, and
added no baked or unrelated geometry.

### `final_evidence_and_stopping_are_credible`

**Observed and supported.** The final wait and snapshot used the same committed
receipt, the snapshot was the final gateway event, the goal completed, Prime
exited normally, and no tracked process remained alive.

Overall disposition: **`credible_success`**.

## Efficiency

Qwen used 21 model turns, 24 gateway calls, and 517,937 provider tokens. The
input/output split was 501,585 / 16,352. The first committed mutation was source
sequence 7, and every one of the six mutation attempts committed successfully.

The six discovery calls were direct contract reads. Qwen then took the initial
snapshot as a separate observation. There was no broad capability search, component-library
search, native metadata exploration, implementation-mode switch, destructive
reset, or failed tool-call recovery. This is materially cleaner than the earlier
VP2 discovery-churn specimens, but it remains one stochastic task and is not a
causal efficiency estimate.

## Interpretation

The optional packaged skill reproduced the qualified Python lane behavior on a
third computational family:

- radial line array;
- Cartesian point lattice; and
- sampled sine-wave polyline.

On this run Qwen selected the intended lane explicitly, committed early, built
the requested script and controls, exercised and restored two consequential
controls, obtained authentic final receipt custody, and self-terminated within
budget. This supports the package as a qualified empirical candidate for an
explicitly selected optional Python Grasshopper skill on reconciled Prime
`739400844`.

The result does not justify default installation, automatic routing, removal of
native authoring, C# guidance, general Python superiority, or broader Prime
production qualification. Prime `27b5be22` remains a read-only historical and
rollback baseline; new Rook/Qwen experiments use `739400844`.

No supervisor, semantic acceptance vocabulary, terminalization mechanism,
cache, compaction layer, or additional compatibility smoke is justified by this
result.

## Custody

The exact execution command was:

```powershell
C:/UDEV/Rook/mcp_server/.venv/Scripts/python.exe `
  C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger/scripts/qwen38_self_termination_campaign_runner.py run `
  --protocol C:/UDEV/Rook/.worktrees/coordinating-intelligence-evidence-ledger/docs/superpowers/experiments/2026-08-19-qwen38-optional-python-skill-sine-wave-confirmation-v1.json `
  --evidence-root C:/UDEV/RookEvidence/2026-08-19-qwen38-optional-python-skill-sine-wave-confirmation-v1 `
  --document-serial 268435457
```

- Package/pre-contact commit: `96b9f9cd1bd4c75382105a425441ed52a6efbddb`.
- Offline and post-run verification: **228 passed**, 11 existing warnings;
  Python compilation and frozen JSON parsing passed.
- Prime baseline: `739400844f8f3f280414b0c7b9c65797208815d3`.
- Optional skill SHA-256:
  `15C00152070150089AC8FE7488273946AD4AC932F176A94C58342A26B6257292`.
- Canonical native skill SHA-256, unchanged:
  `30CA98809CCE8F4BE5B1CC291DEB8820511B6B13A0D546CBA93848DBC9074B07`.
- Protocol SHA-256:
  `22B9D7FBDF158D4FE132B9C335746FE5A3636449C7B1898FD8266E96DE6528D3`.
- Adjudication SHA-256:
  `23B92ECDF500B4568196D302E3DDB53CB64188DA39DAD2B68327A2CA1FF5125F`.
- Runner SHA-256:
  `8197214023B409DB1CF358582833E3BF304C95F49CD5B103D087139B10DAC5B8`.
- Global evidence: **49/49** independently reverified.
- Row evidence: **34/34** independently reverified.
- Global manifest SHA-256:
  `9E52CA8A192BA1A0526A98FA3FED4AEDE04600109980F4F284F9C15DD633D442`.
- Row manifest SHA-256:
  `395F3C2BC4BB607B625196B128BC69ECBDCE0B4E31D784846F5FB8404F41A002`.
- Source trace closed at 24 canonical gateway events with exactly one terminal
  `agent_end`.
- Standard error was empty, the process result retained no owned child PID, and
  no tracked process identity remained alive at final audit.

Evidence root:
[qwen38-optional-python-skill-sine-wave-confirmation-v1](C:/UDEV/RookEvidence/2026-08-19-qwen38-optional-python-skill-sine-wave-confirmation-v1)
