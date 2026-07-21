# LM9B-P Readiness Boundary Design

- Date: 2026-07-21
- Status: Design approved in brainstorming; specification for review; no
  implementation
- Base: `main` at `dfd90659` (LM9B-P merged via PR #496; reviewed head
  `6611306d`)
- Scope: One small operational readiness boundary in front of the existing,
  unchanged LM9B-P Planner-transfer experiment

## 1. Purpose

The one canonical LM9B-P attempt at `9959650f` was recorded honestly as
`probe_inconclusive`: LiteLLM rejected the only Planner call before any model
turn because `OPENAI_API_KEY` was absent. An irreversible attempt identity was
spent on an environment-configuration fault that was fully knowable before the
identity was minted.

This slice adds a staged readiness boundary so that a **present-or-absent and
present-but-nonfunctional** credential/access fault is caught operationally,
before an attempt identity is allocated. It changes nothing about the
scientific experiment, the recipe architecture, the validation kernel, the
compiler, LM9A-S, or the semantic vocabulary.

## 2. What This Is And Is Not

This is an **operational check against operator error**. It is not a second
validation kernel and not an adversarial trust boundary — the readiness record
is produced by our own trusted readiness command, so the threat model is
operator mistake and stale state, not forgery.

The canary's claim is deliberately narrow:

> At time T, this credential source authenticated to this provider/model
> through the production adapter and completed a basic tool-call round trip.

It is **point-in-time evidence, never a guarantee**. Provider state (keys,
quotas, model access, service health) can decay after a passing readiness run;
readiness only materially reduces the chance of another pre-model inconclusive
run. The experiment itself proves that the full experimental request succeeds;
readiness does not certify every experimental request parameter.

### Non-Goals

- reproducing each role's temperature/token/`tool_choice`/streaming settings;
- treating post-call metadata wrappers as independent routes;
- adversarial authentication of a locally produced readiness record;
- a general route or provider-family ontology or framework;
- any change to LM9B-P treatment, LM9B-C, the kernel, or LM9A-S.

## 3. Staged Boundary

```text
local deterministic preflight            [no provider contact]
-> explicitly approved authenticated canary   [--authenticate; one contact/route]
-> fresh sealed readiness record              [separate operational evidence]
-> pure launch verifier                       [refuse-before-allocation]
-> unchanged one-shot LM9B-P experiment
```

A failure anywhere above the experiment is an **operational** failure: no
attempt is consumed, credentials may be corrected, and the readiness run may be
repeated under a **new readiness-record identity**. The LM9B-P attempt remains
strictly one-shot and behaviorally unchanged.

## 4. Code Topology

Three surfaces; the pure module is the only seam between readiness and the
experiment.

```text
lm9b_p_readiness_contract   (pure: NO Git/filesystem/clock/environment I/O)
  - frozen route derivation (profile tuples -> routes)
  - route-manifest fingerprinting
  - readiness-record schema + verification (evidence-derived)
  - FROZEN_MAX_AGE constant
  callers pass in: current SHA, current time, credential-presence
  observations, frozen route inputs
        ▲                                        ▲
        │ imports                                │ imports
  lm9b_p_readiness_probe  (disposable)      experiment CLI (--transmit)
  - owns provider contact (canary)          - imports ONLY the pure verifier
  - owns record writing                     - verify / refuse; never contacts
  - --authenticate gate                       a provider; no canary controller
```

The experiment CLI must not import the canary controller or any
provider-contact code. Importing the verifier is a pure operation.

## 5. Route Identity And Deduplication

Route identity represents the **provider / model / authentication route through
the production adapter** — the thing that determines whether a call
authenticates and reaches a model at all:

```text
route identity = (production-adapter construction path,
                  provider, model, credential-source name)
```

Deliberately excluded from identity: temperature, completion-token limits,
`tool_choice` mode, streaming, parallel-tool-calls flag, post-call wrapper
identity, and all local timeout/cost/accounting controls.

Deduplication is by exact route identity. Distinct routes are derived from the
four experiment roles (`planner`, `planner_evaluator`, `compiler`,
`compiler_evaluator`); each distinct route records its `member_roles`.
Production code must not hardcode the resulting count. Under the current frozen
configuration this is expected to derive two routes (OpenAI `gpt-5.4`; Gemini
`gemini-3.1-pro-preview`), each covering two roles — but that count is derived
and asserted only in tests.

```text
route_manifest:
  routes                distinct route[] in canonical route_fingerprint order
  manifest_fingerprint  fingerprint(canonical routes set)
```

## 6. Canary Shape

One contact per distinct route, no retry, only under explicit `--authenticate`.

- Constructed through the **production adapter**, exactly as the experiment
  constructs it — that is what makes the authentication authentic.
- Fixed benign messages with **no experiment content**: system = "You are a
  readiness canary."; user = "Call the `ack` tool." No brief, authority
  artifacts, R01, rubric, recipe schema, expected output, or forbidden
  experiment markers appear anywhere in the request.
- One throwaway forced tool `ack(ok: boolean)`, `tool_choice` forcing it, to
  prove the tool-call round trip. Minimal completion tokens, bounded timeout,
  streaming off.
- The fixed messages and tool schema are part of `canary_implementation_identity`.
- The canary uses its own minimal safe request parameters; it does not
  reproduce the experiment's temperature/token settings.
- Sanitized outcome (existing `_API_KEY`/`_TOKEN` redaction) is written to a
  **separate readiness run root**, never an experiment run root.

## 7. Readiness Record

The record carries a **discriminated per-route evidence** projection so the
verifier derives readiness rather than trusting a stored boolean. No top-level
`passed` field is authoritative.

```text
readiness_record (schema_id: lm9b_p.readiness_record:v1)
  reviewed_commit_sha
  route_manifest_fingerprint
  canary_implementation_identity  fingerprint of canary controller +
                                  fixed messages + throwaway tool schema
  max_age_seconds                 echo of FROZEN_MAX_AGE (module constant is
                                  authority; verifier requires equality)
  completed_at                    controlled-host UTC, exact ISO-8601
  routes:                         one row per distinct route
    route_fingerprint             must match a route in the CURRENT manifest
    member_roles
    observed_at                   controlled-host UTC
    request_fingerprint
    outcome (exactly one of):
      transport_failure:          classification, sanitized detail hash
      model_response:             assistant_present (bool),
                                  tool_calls (name + strict-JSON arguments,
                                  or arguments fingerprint),
                                  raw_response_fingerprint
  record_fingerprint              unkeyed; detects accidental mutation only
```

### 7.1 Route Readiness Predicate

Route readiness validates the actual canary protocol against the one tiny
closed `ack` shape — not merely that some tool call exists:

```text
route_ready(row) ≜ outcome is model_response
                   AND assistant_present
                   AND exactly one tool call exists
                   AND tool_call_name == "ack"
                   AND arguments are strict JSON
                   AND arguments == {"ok": true}
```

Exact argument-byte identity is not required; strict-JSON semantic validation
against this closed shape is sufficient.

## 8. Three Launch Coordinates And Attribution

`mkdir` allocates an irreversible attempt identity, but no model has interpreted
anything at that instant. Three distinct coordinates keep attribution honest:

```text
attempt allocation  : atomic run-root creation; one-shot identity immutable
provider contact    : first invocation of the Planner provider adapter
model observation   : first captured provider response containing an
                      attributable assistant/model message, whether or not its
                      tool submission is valid or accepted
```

One-shot handling begins at allocation. Scientific evidence about Planner
competence begins only at model observation. A malformed or mechanically
rejected model response is still a model observation and still evidence.

```text
failure before allocation             -> readiness failure; NO attempt consumed
failure after allocation,
  before provider contact             -> pre-contact operational failure
provider failure, no model response   -> probe_inconclusive; supports NEITHER
                                         semantic hypothesis
first attributable model message      -> the empirical Planner experiment has
                                         genuinely begun
```

## 9. Launch Verifier

Pure, side-effect-free, inside `--transmit`, immediately before run-root
creation. It recomputes rather than trusting any serialized outcome:

```text
launch readiness ≜
  identity continuity   : current clean HEAD == reviewed_commit_sha
                          AND recomputed manifest fp == route_manifest_fingerprint
  role coverage         : member_roles across routes cover all four roles
  temporal freshness    : (see 9.1)
  credential presence   : repeat the Section-3 non-contact presence check
                          for every route's credential-source name
  route readiness       : route_ready(row) for every route (from evidence)
  age-constant binding  : max_age_seconds == FROZEN_MAX_AGE

fail -> refuse before mkdir; no attempt allocated
pass -> proceed to atomic run-root creation (the unchanged experiment)
```

### 9.1 Temporal Freshness

Identity equality cannot prove remote provider state is still usable, so
freshness is an independent gate using controlled-host UTC `now`:

```text
completed_at >= every route observed_at
0 <= now - completed_at <= FROZEN_MAX_AGE
for every route: 0 <= now - observed_at <= FROZEN_MAX_AGE
future timestamps (now - t < 0) FAIL, for any route or the record
```

`FROZEN_MAX_AGE = 600` seconds, frozen into the module and the verifier
identity, not operator-configurable per run. Controlled-host UTC is an explicit
operational assumption; no clock-authority subsystem is introduced.

## 10. Essential Deterministic Tests

All use deterministic fakes; no real provider is contacted.

```text
1. missing credential      -> local preflight fails; NO canary contact attempted
2. transport failure       -> fake adapter raises; row = transport_failure;
                              launch verifier refuses; run root never created
3. assistant, no ack call  -> fake returns a message without a conforming ack
                              call (or wrong name / bad args / ok != true);
                              route_ready = false; verifier refuses
4. identity mismatch       -> record SHA != HEAD, or recomputed manifest fp !=
                              record fp -> refuse before mkdir
5. staleness / future time -> observed_at or completed_at outside
                              [now - 600, now] (including future) -> refuse
6. import isolation        -> importing the pure verifier does NOT import the
                              canary controller / provider-contact module; the
                              refuse path creates no run root
7. approval and cardinality-> without --authenticate, no provider contact
                              occurs with valid credentials present; with
                              approval, each distinct route is contacted once
8. credential disappearance-> a fresh passing record, then a missing credential
                              at launch, is refused before mkdir
9. content exclusion       -> every canary request contains none of the brief,
                              authority artifacts, R01 identifiers, rubric,
                              recipe schema, expected output, or forbidden
                              experiment markers
```

Acceptance anchor (happy path): a fresh record whose every route is
`model_response` and `route_ready`, whose SHA and manifest fingerprint match,
and whose timestamps are in range, permits allocation. It also asserts all four
roles are covered and that the current frozen configuration derives two routes
(assertion only; production code derives the count).

## 11. Successor

After a passing readiness record and explicit launch approval, the next step is
the unchanged one-shot LM9B-P Planner-transfer experiment under a new attempt
identity, new run root, and newly reviewed committed SHA — exactly as the prior
result's "Next Falsifiable Experiment" section requires. This slice provides
the credible launch condition; it does not itself begin the scientific attempt
and grants no execution authority.
