# LM6B - Bounded Worker Protocol Freeze Design

- **Date:** 2026-07-06
- **Status:** Draft for review
- **Slice:** LM6B
- **Type:** Doc-only capstone and v1 protocol freeze

## 1. Purpose

LM6B records the bounded-worker proof ladder through the LM6A live arrival run
and freezes the v1 protocol shape that made that run possible.

LM6B is not an implementation slice. It does not add code, change prompts, run
models, dispatch live Rhino/Grasshopper tools, or claim product readiness.

The purpose is narrower:

```text
Record the completed proof ladder and freeze the v1 bounded-worker protocol
shape, without claiming reliability beyond N=1.
```

This freeze means:

```text
This is the protocol shape that reached the live verifier floor once.
```

It does not mean:

```text
This protocol is reliable, complete, generalized, or ready as product behavior.
```

## 2. Run Identity

Terminal arrival run:

- implementation commit used by the accepted live run: `0d02180a`
- full splice run directory:
  `probe_runs/lm6a-20260706T215203Z-0d02180a/`
- final decision: `accepted`
- final reason: `verify_repair_succeeded`
- worker action excerpt: `{"code": "A = 0.0;", "mode": "body"}`

Curated evidence checkpoint:

- curated evidence merged on `main` at `57cf83fa`
- evidence file:
  `docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md`

Doctrine:

```text
failures are receipts, not noise
```

The two LM6A gate failures are part of the proof. They show that the gated
method rejected environment unreadiness and fixture/receipt drift before the
worker could contaminate the result.

## 3. Proof Ladder

The LM5/LM6 line should now be read as one evidence ladder, not as isolated
prompt attempts.

### LM5O

LM5O compared Gemma free-text and structured local transport. It showed that:

- free-text behavior had better intent but invalid LM5 envelopes
- structured output produced strict envelopes but degraded absent-scenario
  restraint
- the problem was not solved by simply choosing a model variant

### LM5P

LM5P directly tested Ollama `format` plus `think`. It showed that direct Ollama
could preserve `message.thinking` while enforcing the response envelope, but
thinking preservation alone did not preserve absent restraint.

### LM5Q

LM5Q replicated the disposition-flip problem. It showed exact repeated thinking
hashes across free and structured modes while the published disposition changed.
The conclusion was:

```text
single-pass constrained union publication can re-decide or distort disposition
```

### LM5R

LM5R introduced two-pass publication:

```text
think free, decide free, publish constrained
```

It proved that a pass-one decision could be preserved through a narrowed
single-kind publication pass. It also exposed a new failure mode: observation
could carry action intent if pass-one disposition semantics were too loose.

### LM5S

LM5S tightened pass-one disposition semantics and added report-only observation
action-intent anomaly scoring. It closed the observation-action escape hatch in
that run, but evidence-present action selection still remained unreliable.

### LM5T

LM5T added bounded repair-intent diagnostics without leaking the hidden repair
answer. It showed that diagnostics alone were not enough: the worker still
clarified because the visible evidence explained the failure but not the
checkable success condition.

### LM5U

LM5U added checkable acceptance criteria. This moved the canonical
evidence-present scenario from clarification to action:

```text
LM5T present_v2: 0/5 action_request
LM5U present_v3: 5/5 action_request
```

The hidden answer did not leak. LM5U proved decision movement, not broad repair
quality.

### LM5V, LM5W, LM5X, LM5Z, LM5AA

These slices turned the working fixture evidence into explicit seams:

- LM5V audited criterion source ownership
- LM5W assembled acceptance criteria from typed source facts
- LM5X extracted those source facts from real fixture/runtime objects
- LM5Z designed node-scoped worker-visible source routing
- LM5AA prototyped deterministic source-routing validation

Together they established this boundary:

```text
contract declares routable source facts
extractor resolves source facts
assembler turns resolved facts into worker-visible criteria
worker receives the assembled visible surface
```

### LM5Y

LM5Y joined LM5X extraction and LM5W assembly back into the probe while
preserving the LM5U worker-visible legacy evidence shape. It showed the seam was
real in the probe runtime, not only in isolated unit tests.

### LM6A

LM6A replaced the hidden repair bind step with a worker-authored action:

```text
live create -> verify_create -> routing/extraction/criteria gate
-> two-pass worker publication -> worker-action applier
-> live gh_update_script -> verify_repair
```

The final full splice ended:

```text
decision = accepted
reason = verify_repair_succeeded
```

The accepted repair was worker-authored:

```json
{"code": "A = 0.0;", "mode": "body"}
```

The hidden fixture answer did not leak:

- no `PROBE_REPAIR_CODE`
- no `A = 42.0`
- no `BindStepSpec.base_params.code`

## 4. Frozen v1 Protocol Shape

LM6B freezes the following v1 protocol boundaries for the next repeatability
probe.

### 4.1 Source Routing

Worker-visible authority is node-scoped and declared by source route, not by
global graph visibility.

Frozen shape:

```text
WorkerVisibleSourceRouting
  schema = rook.worker_visible_source_routing:v1
  routes[]
    node_id
    visible_sources[]
      route_id
      source_class
      source_path
      purpose
      required
```

Important boundary:

```text
The routing declaration names which upstream facts may be visible. It does not
contain worker-facing acceptance-criteria prose or hidden answers.
```

### 4.2 Source Extraction

Extraction projects already-selected real facts into typed
`AcceptanceCriteriaSources`.

Frozen boundary:

```text
real fixture/runtime objects -> extract_acceptance_criteria_sources(...)
```

Extraction must not read hidden bind params or future model-authored outputs.

### 4.3 Criteria Assembly

Assembly turns typed source facts into a versioned acceptance-criteria packet.

Frozen boundary:

```text
AcceptanceCriteriaSources -> assemble_acceptance_criteria_packet(...)
```

The full LM5W packet may be retained as an artifact, but LM6A worker-visible
input uses the LM5Y legacy projection.

### 4.4 Worker-Visible Legacy Packet

The worker-visible evidence shape remains the LM5Y legacy projection:

```text
acceptance_criteria:
  source
  criteria[]
    criterion_id
    description
    source
```

These LM5W internals are not worker-visible in v1:

- `schema`
- `source_set`
- `source_class`
- `unresolved_intent`
- `fingerprint`

### 4.5 Two-Pass Publication

Worker publication remains:

```text
pass 1: free decision, think=true, no format
pass 2: formatter-only, single-kind schema, think=false
```

Hard invariant:

```text
pass 2 may publish but may not choose the decision kind or action id
```

### 4.6 Worker-Action Applier

The applier is the splice seam from worker-authored action input to graph
execution params.

Frozen behavior:

- accepts only `draft_repair_params`
- accepts exact worker action input keys: `code`, `mode`
- requires `mode = body`
- stages trusted anchor `guid` and `language`
- writes execution params copy-on-write
- never reads hidden bind params
- never dispatches live work

### 4.7 Live Dispatch

Live dispatch remains manual and explicit for the proof line:

```text
apply worker action -> dispatch gh_update_script -> verify_repair
```

No generic runner auto-advance is part of the v1 freeze.

### 4.8 Decision Record

The LM6A decision record is the terminal evidence artifact for the live splice.

Frozen terminal decisions:

- `gate_failed`
- `publication_failed`
- `worker_declined`
- `rejected`
- `accepted`

For the accepted LM6A run:

```text
decision = accepted
reason = verify_repair_succeeded
```

## 5. What Is Not Frozen

LM6B intentionally does not freeze these areas:

- diagnostic format tolerance policy beyond the PR #431 live diagnostic fix
- repeatability rate
- Planner/compiler source-routing authorship
- clarify/resupply loop protocol
- model/provider canonicalization
- broad repair quality scoring
- semantic repair ranking
- retry strategy
- KG or convention retrieval strategy
- generic workflow-runner integration
- product-facing UX

In particular, LM6B does not decide whether the canonical provider should remain
`gemma4:12b-it-qat` after repeatability testing. LM6A used that model because it
was the canonical local witness model for the proof ladder.

## 6. Limits

The LM6A arrival result is important and narrow.

Known limits:

- N=1 accepted full splice
- one controlled C# Grasshopper fixture
- one local model/provider path
- one worker action family: `draft_repair_params`
- one repair target shape: body-mode C# script output assignment
- no retry loop
- no Planner model
- no clarify/resupply loop
- no generalized diagnostic interpretation
- no broad semantic repair-quality evaluation
- no product-readiness claim

LM6B therefore freezes a protocol shape, not a reliability result.

## 7. Gate Failures As Receipts

The two LM6A gate failures should remain in the capstone story.

First gate failure:

```text
live surface not ready -> no usable create receipt -> gate_failed
```

Evidence value:

```text
the protocol requires a ready throwaway Rhino/GH live document
```

Second gate failure:

```text
live receipt/routing passed, but criteria assembly rejected exact diagnostic
format drift -> gate_failed
```

Evidence value:

```text
the gate caught fixture/live receipt drift before worker publication
```

PR #431 was a deterministic seam correction:

```text
still require exactly one diagnostic containing DefinitelyMissingSymbol
stop requiring the fixture's exact CS0103 prose
```

It was not a worker prompt change, model change, or live splice behavior change.

## 8. Operational Rules

LM6B preserves these operational rules for LM6C:

- do not run more LM6A attempts before the repeatability slice is designed
- use a throwaway Rhino/GH document for live runs
- run receipt recon before full splice when debugging environment readiness
- treat gate failures as evidence artifacts, not noise to suppress
- keep raw `probe_runs/` local and ignored
- do not stage `knowledge/gh/operations_knowledge.json` live telemetry drift
  unless a dedicated telemetry slice intentionally owns it

## 9. Next Slice

The next slice should be LM6C:

```text
N=5 full LM6A arrival loops, same model, same fixture, same protocol,
new run manifest discipline, no code/prompt changes unless preflight fails.
```

LM6C should answer:

```text
Is the LM6A arrival path a stable primitive or a one-off?
```

Pre-registered interpretation:

- If stable: move upstream to Planner/compiler routing authorship.
- If declines or flakes: design pull-loop and reliability instrumentation.
- If preflight fails: record environment evidence and do not count it as model
  behavior.

LM6C is repeatability evidence. It should not change the v1 protocol frozen by
LM6B unless a preflight or deterministic validator defect blocks the run.
