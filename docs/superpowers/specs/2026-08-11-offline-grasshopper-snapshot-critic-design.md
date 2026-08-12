# Offline Grasshopper Snapshot Critic Design

**Status:** Approved architecture, ready for one isolated qualification and one
small implementation slice

**Date:** 2026-08-11

## Objective

Qualify and implement the smallest independent semantic-critic boundary for one
retained failed Qwen Grasshopper run:

```text
original user intent
+ authentic final gh_snapshot
-> isolated Critic
-> closed discrepancy artifact
-> deterministic schema and authority gate
-> no mutation
```

This is an OpenProse-aligned experiment for discovering semantic
postconditions. It is not a permanent model judge, workflow engine, scoring
system, repair loop, or new agent runtime.

## Frozen source evidence

The only run evidence admitted to the Critic is:

```text
C:/Users/bring/AppData/Local/Temp/
prime-rook-qwen-strict-retest-v1/local/operator/final-inspection.jsonl
```

Its reviewed SHA-256 is:

```text
4B3E44B853D7EEC44D6052D2C4442BEB4CEE46BD3E728C14781FCDDB43C87AE8
```

The exact intent is:

> Create a Grasshopper definition that generates a row of points along the X
> axis using adjustable Start, Step, and Count controls, with Y and Z fixed at
> zero.

The source JSONL must remain byte-for-byte unchanged before and after all work.

## Isolation and authority

The Critic receives exactly two semantic inputs:

```json
{
  "intent": "<exact original intent>",
  "snapshot": {
    "success": true,
    "data": "<exact gh_snapshot data value>"
  }
}
```

The wrapper may add a schema identifier outside those two values for transport
validation. It may not add interpretations, diagnoses, acceptance hints, or
Actor-derived content.

The Critic must not receive:

- Actor reasoning or transcript;
- tool searches, calls, results, or history;
- Actor completion claims;
- the known diagnosis or suggested topology;
- skill text, model prompt history, or session state.

The isolated call uses Prime's existing local provider construction with
`qwen3.6:35b`, one user message, no tools, no extensions, no MCP integration,
no filesystem tool, `maxRetries=0`, and exactly one provider dispatch. It may
read the prepared prompt in memory and return text. It has no repair or mutation
authority.

## Source evidence admission

The source loader accepts exactly two nonblank UTF-8 JSONL rows with no duplicate
keys:

1. `{"kind":"request","payload":...}`
2. `{"kind":"result","payload":...}`

The request must be exactly:

```json
{
  "name": "gh_snapshot",
  "arguments": {
    "include_data": true,
    "max_preview_items": 3
  }
}
```

The result payload must contain exactly `success` and `data`, with `success`
equal to `true` and `data` an object. The projection retains that payload value
without normalization or augmentation.

## Critic prompt boundary

The prompt describes only:

- the independent semantic-review role;
- the closed response grammar below;
- the requirement to use only supplied intent and snapshot evidence;
- the requirement to cite resolvable JSON Pointers;
- the requirement to avoid inferred history or unseen state.

It must not mention Series, prescribe topology, describe the known defect, or
state the expected verdict. There is no prompt retry or tuning after observing
the response.

## Closed discrepancy artifact

The Critic must return one JSON object, without Markdown fencing, with exactly:

```json
{
  "verdict": "pass | fail | insufficient_evidence",
  "satisfied_claims": ["nonblank claim"],
  "discrepancies": ["nonblank discrepancy"],
  "evidence_references": [
    {
      "claim": "nonblank claim or discrepancy",
      "pointers": ["/intent", "/snapshot/data/components/0"]
    }
  ],
  "repair_requirements": ["nonblank semantic requirement"]
}
```

All arrays are ordered, all strings are strict UTF-8, and duplicate strings are
refused. Each evidence-reference object has exactly `claim` and `pointers`.
Every pointer is a syntactically valid JSON Pointer that resolves against the
exact Critic projection and begins with `/intent` or `/snapshot`.

Coherence rules are:

```text
pass
-> discrepancies == []
-> repair_requirements == []
-> satisfied_claims is nonempty

fail
-> discrepancies is nonempty
-> repair_requirements is nonempty

insufficient_evidence
-> discrepancies is nonempty
-> repair_requirements may be empty or nonempty
```

Every satisfied claim and discrepancy must appear exactly once as an
`evidence_references[].claim`. Repair requirements are future semantic
postconditions, not executable tool instructions.

The raw assistant response and strictly loaded artifact are retained separately.
Invalid output does not become a discrepancy artifact and does not authorize a
second call.

## Experimental success criterion

The one Critic call qualifies this boundary only if its admitted artifact
independently establishes all of the following from the supplied evidence:

- Y and Z are structurally fixed at zero;
- there is no adjustable Step control;
- `EndX` substitutes a different interface for Step;
- Count controls Range intervals/steps, producing Count plus one points;
- therefore the user intent is not satisfied.

These statements are qualification assessment criteria. They are not included
in the Critic prompt.

## Reusable no-contact boundary

If the call qualifies, add one focused Python module that owns only:

1. strict final-snapshot JSONL loading;
2. exact intent-plus-snapshot projection;
3. one invocation of an injected Critic callable;
4. strict discrepancy-result loading and pointer validation;
5. a completion gate requiring both Actor-reported success and Critic `pass`;
6. create-new discrepancy-artifact writing.

The injected callable receives only an immutable JSON-compatible projection. It
returns raw UTF-8 JSON text. The boundary has no model construction, MCP client,
Rhino client, tool dispatch, retry, repair, or conversation persistence.

The completion function is deliberately narrow:

```text
actor_reported_success AND critic.verdict == pass
-> completion allowed

otherwise
-> completion not allowed
```

The function proves only that Actor self-report cannot override an admitted
Critic failure. It is not integrated into the production runtime in this slice.

Artifact writing uses one create-new write followed by flush and fsync. It does
not overwrite, retry, truncate, or repair an existing artifact.

## Causal tests

Tests use the retained snapshot and injected fakes only. They prove:

- the source hash remains the reviewed value;
- exact request/result admission and Actor-field exclusion;
- malformed, duplicate-key, extra-field, invalid-enum, invalid-string, and
  unresolved-pointer results refuse;
- the injected Critic is called exactly once with only the projection;
- a fake Actor success plus Critic failure cannot complete;
- create-new artifact emission is exact and refuses overwrite;
- no network, Prime, Rhino, Grasshopper, MCP, or tool surface exists in the
  reusable module.

## Considered approaches

### 1. Pure boundary module plus disposable Prime call — selected

This separates the one empirical model observation from reusable deterministic
custody. It adds one focused module and one focused test file.

### 2. Disposable script only — rejected

It could run the Critic but would leave no reusable schema/authority gate and no
causal protection against Actor self-report.

### 3. ChatRunner or Prime runtime integration — rejected

It would give an experiment permanent runtime authority, couple the Critic to
Actor state, and expand into workflow and lifecycle policy before the semantic
postconditions are known.

## OpenProse alignment and north star

This experiment asks whether an isolated semantic Critic can discover missing
postconditions from intent and final evidence. Its findings may inform a future
pre-authored acceptance artifact.

The intended mature flow is:

```text
intent
-> acceptance/postcondition artifact authored before execution
-> Actor execution
-> authentic final evidence
-> mechanical postcondition evaluation
```

The runtime must not permanently delegate final authority to a free-form model
judge merely because this isolated experiment succeeds.

## Anti-quagmire boundary

Stop if the work requires any of the following:

- live Rhino, Grasshopper, MCP, deployment, or canvas mutation;
- a new Actor run, repair run, Opus call, or external provider call;
- Actor transcript or completion-claim access;
- more than one focused boundary module and one focused test module;
- a workflow engine, score, recorder, manifest campaign, or generalized critic
  framework;
- a permanent ChatRunner, Prime, or Rook runtime commit decision.

## Deliverables

- the one-call Critic input, raw response, parsed artifact, and hashes;
- the focused boundary module and causal tests, only if the call qualifies;
- verification results and changed-file scope;
- bounded claims and non-claims;
- one smallest proposed, explicitly unexecuted Actor -> Critic -> one-repair
  experiment.
