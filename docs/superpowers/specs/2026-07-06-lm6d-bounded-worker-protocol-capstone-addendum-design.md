# LM6D - Bounded Worker Protocol Capstone Addendum Design

- **Date:** 2026-07-06
- **Status:** Draft for review
- **Slice:** LM6D
- **Type:** Doc-only capstone addendum to LM6B

## 1. Purpose

LM6D records what changed after the LM6C repeatability evidence.

LM6B froze the v1 bounded-worker protocol after the first LM6A live-arrival run.
At that point the protocol had reached the live verifier floor once:

```text
bounded worker action -> worker-action applier -> live gh_update_script ->
verify_repair_succeeded
```

LM6C then tested whether that frozen path was a one-off. The answer was more
specific than "yes" or "no":

```text
5/5 scheduled attempts reached the worker path.
4/5 completed accepted live repairs.
1/5 ended in a clean observation disposition.
0/5 leaked hidden-answer markers.
```

LM6D is the capstone addendum that updates the freeze story:

```text
The protocol is not merely possible. It repeated under the N=5 fixture run,
with one safe non-action disposition and no hidden-answer leakage.
```

LM6D does not add code, change prompts, run models, dispatch live tools, or
create another evidence packet. It is an onboarding and decision artifact for
the next phase of work.

## 2. Relationship To LM6B

LM6D is an addendum to LM6B, not a replacement.

LM6B established:

- the proof ladder through LM6A
- the v1 protocol boundaries
- the operational rule that gate failures are evidence artifacts, not noise
- the limits of the first arrival result
- the next question: repeatability

LM6D preserves all of that and adds the post-LM6C read:

- repeatability was tested without changing the frozen protocol
- the scheduled denominator was explicit
- the worker-reached denominator was explicit
- the protocol reached the worker path in all scheduled attempts
- most attempts accepted through live verification
- the only non-accepted attempt was a clean non-action disposition

The v1 protocol boundary remains the same. LM6D freezes the **story after
repeatability**, not a new implementation surface.

## 3. Proof Ladder Snapshot

The proof ladder now reads:

```text
LM5O/LM5Q:
  single-pass structured publication can distort disposition.

LM5R:
  two-pass publication can preserve a freely chosen disposition.

LM5S:
  clearer pass-one disposition semantics closes the observation-action leak
  in the diagnostic run.

LM5T:
  target diagnostics alone do not make the worker act.

LM5U:
  acceptance criteria move the worker from clarification to action without
  leaking hidden repair params.

LM5V/LM5W/LM5X/LM5Y/LM5Z/LM5AA:
  acceptance-criteria ownership, assembly, extraction, joining, source routing,
  and validation become deterministic seams.

LM6A:
  one bounded local worker action reaches the live verifier floor.

LM6B:
  the v1 protocol is frozen after the arrival milestone.

LM6C:
  the frozen protocol repeats: 5/5 worker path reached, 4/5 accepted, 1/5 clean
  observation disposition, 0 leak markers.
```

The durable doctrine is:

```text
Workers act on checkable acceptance criteria, not hidden answers.
Failures are receipts, not noise.
The worker-visible surface is assembled from routed source facts.
The worker publishes through a two-pass mechanism.
Execution params enter the live floor only through the worker-action applier.
```

## 4. Post-LM6C Evidence

Canonical LM6C repeatability run:

```text
probe_runs/lm6c-20260706T233550Z-6d52039f/
```

Identity:

- git commit: `6d52039f`
- model: `gemma4:12b-it-qat`
- provider path: direct Ollama `/api/chat`
- attempts: `5`
- protocol: frozen LM6B/LM6A path
- worker-visible evidence: LM5Y legacy projection
- no replacement attempts

Outcomes:

```text
scheduled_attempts: 5
lm6a_invoked_count: 5
worker_reached_count: 5

accepted: 4
worker_declined: 1
gate_failed: 0
publication_failed: 0
wrapper_error: 0
preflight_failed: 0

leak_marker_match_count: 0
```

The accepted rows all used a worker-authored body repair:

```json
{"code": "A = 0.0;", "mode": "body"}
```

The clean non-action row published an `observation`, not an action. It was:

- LM5G-loadable
- kind-preserved
- not an observation-action-intent anomaly
- not dispatched to live repair
- not counted as verifier failure

This should be called a **safe non-action disposition** or **clean observation
wobble**, not a failed repair attempt.

## 5. Harness Defect Accounting

The first LM6C invocation after PR #434 produced:

```text
probe_runs/lm6c-20260706T233115Z-efb205b3/

preflight_failed: 5
lm6a_invoked_count: 0
worker_reached_count: 0
```

Direct diagnostics showed the live surface was actually healthy:

```text
rhino_ping -> "pong"
gh_document_new -> {"created": true, ...}
```

The defect was in the LM6C wrapper's preflight predicate, which rejected the
bare `"pong"` success shape. PR #435 fixed only that deterministic adapter
issue.

LM6D records that run as a harness defect, not repeatability evidence and not
worker/model behavior.

## 6. Frozen Protocol Boundaries After LM6C

LM6C did not change the v1 protocol. The frozen boundaries remain:

- node-scoped source routing
- LM5AA static/routability validation
- LM5X source extraction
- LM5W acceptance-criteria assembly
- LM5Y legacy worker-visible projection
- direct Ollama local worker path
- two-pass worker publication
- single-kind constrained publication
- LM5G loadability check
- observation-action anomaly check
- worker-action applier as the only execution-param splice
- script-local bind-free LM6A contract variant
- live `gh_update_script`
- `verify_repair` floor
- bounded local decision records

Nothing about LM6C authorizes:

- hidden bind params
- broad evidence stuffing
- prompt tuning as the next default move
- production Planner integration
- production retry policy
- broad claims about model reliability

## 7. Limits

LM6D freezes the post-LM6C read with explicit limits:

- `N=5`, not large-scale reliability
- one controlled C# Grasshopper repair fixture
- one local model: `gemma4:12b-it-qat`
- one provider path: direct Ollama
- one worker action family: `draft_repair_params`
- one evidence/criteria shape
- no semantic repair-quality panel
- no Planner model
- no user-intent/general clarify loop
- no multi-fixture or multi-domain generalization

The evidence says:

```text
The bounded-worker protocol is a repeatable primitive for this fixture.
```

It does not say:

```text
Gemma reliably repairs arbitrary code.
The Planner knows how to author criteria generally.
The worker no longer needs any recovery path.
```

## 8. Next Slice Recommendation

The next diagnostic slice should test a **bounded retry budget** for clean
non-action dispositions.

Reason:

```text
LM6C's 1/5 non-accepted row was a clean observation disposition, not missing
evidence, not a publication failure, not an applier rejection, and not a live
repair failure.
```

That makes it disposition wobble under an otherwise sufficient protocol surface.
The next slice should test whether a single receipted retry can recover that
kind of clean non-action without changing the evidence packet, model, or core
protocol.

The retry slice should not be framed as production policy yet. It is a
diagnostic experiment:

- bounded retry budget
- both turns receipted
- no hidden answers
- no prompt/evidence stuffing
- same fixture/model/protocol
- N=5 after deterministic gates

If the bounded retry stabilizes acceptance, Planner/compiler authorship becomes
the next large pressure:

```text
How do real task contracts and source-routing declarations produce these
acceptance criteria generally?
```

If the bounded retry does not help, the next pressure is not more evidence. It
is the clarify/resupply pull-loop, but only when there is real unresolved intent
or a receipted non-action state that asks for resupply.

## 9. Operational Notes

Raw `probe_runs/` artifacts remain local and ignored.

Live runs may update:

```text
knowledge/gh/operations_knowledge.json
```

That file records live usage counters/timestamps and should remain unstaged
unless a dedicated telemetry slice intentionally owns it.

LM6D itself requires no tests beyond doc diff hygiene:

- branch diff is this spec only
- `git diff --check main..HEAD` is clean
- no raw probe artifacts are committed
- no code files are changed
