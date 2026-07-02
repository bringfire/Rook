# LM5L — Coherent Golden Probe Fixture (Design)

**Date:** 2026-07-02
**Status:** Draft for review
**Slice:** LM5L (follows LM5K, PR #397/#399/#400; north star
`docs/superpowers/specs/2026-07-02-rook-planner-harness-north-star.md`)
**Prior evidence:** `docs/superpowers/probes/2026-07-02-lm5k-first-worker-model-probe.md`
(rounds 1 + 1b, corrected diagnosis)

---

## 1. Problem

The LM5K probe's golden scenario is world-state-incoherent. `build_probe_context()`
in `scripts/lm5k_worker_probe.py` builds the worker context on a **freshly
compiled** graph — `create_script` is the only ready node, the current node
`repair_same_component` is `pending`, `has_execution_params` is `false`, and
memory facts are injected by hand — while the LM5F expectation demands an
`action_request` for `draft_repair_params`, a post-verify act.

Probe rounds 1 and 1b established the consequence empirically: qwen3:14b and
Claude Sonnet 5 both produced strict, schema-correct payloads 5/5 and then
**correctly refused or asked for clarification** — every factual claim in the
ceiling's refusal verified true against the rendered envelope. The models
audited the graph state; our deterministic fake transport never had. Spine 0/5
at all tiers is a fixture defect, not a model or prompt failure.

**Architecture lesson (from the committed evidence doc):** LM5A deliberately
allows an explicit `current_node` without a readiness requirement — that stays.
What must hold is that a probe *expectation* never pretends readiness happened
when the envelope says otherwise. Probe scenarios must be world-state-coherent.

## 2. Goal

Derive the golden scenario's graph state through the **real advancement path**
so the rendered LM5I envelope and the LM5F expectation tell one consistent
story:

- `create_script` executed (evidence captured, receipt-derived facts in memory),
- `verify_create` observed `needs_repair`,
- `repair_same_component` genuinely `ready` with execution params bound,
- the expectation (`action_request` / `draft_repair_params`) no longer
  contradicts anything the envelope presents.

Then round 2 can answer the fair-test question: **with a coherent envelope, do
qwen3 and Sonnet move from valid refusal/clarification to
`candidate_action_request`?**

## 3. Ratified decisions (do not relitigate)

1. **Option A — derive, don't hand-build.** The post-verify state is produced by
   existing PlanGraph/LM reducer APIs. Hand-built fixture state can recreate the
   same class of lie; a derived state is coherent because it passed through the
   same advancement semantics real workflows use.
2. **Offline stream, `max_steps=3`.** Reuse `run_current_step_stream` with a
   deterministic offline runner, stopped after the bind step — the LM4W
   chain-guard pattern (`test_plan_graph_workflow_contract_chain.py`). The
   reviewer's "not a stream runner in the probe" constraint means the probe must
   not become a general stream runner or live workflow executor; it does **not**
   forbid a deterministic fixture helper calling the existing offline driver.
   Pins: no live provider, no Rhino/GH, no tool dispatch, no model anywhere in
   the fixture path; the probe runner calls a small fixture helper and owns no
   stream orchestration inline.
   Reviewer spot-check confirmed the mechanism: at `max_steps=3` the records are
   producer/verifier/bind, the runner is called only for `create_script`,
   `repair_same_component` is `ready` with execution params present, and memory
   holds `repair_anchor` and `component_guid`.
3. **Scenario identity is versioned.** The world-state change is a new
   experiment. `workflow_id` is unchanged (the workflow contract itself did not
   change); the scenario id/version change (§7).
4. **Small slice.** Fixture helper + guard + tests in the probe script and its
   test file. Not in scope: prompt-text v2 (stays behind LM5L), any change to
   LM5A–J production modules (frozen), any LM4* change, running round 2 (a
   post-merge activity).
5. **Model-visible vs internal facts stay distinct.** LM5A/LM5H expose
   `has_execution_params: true` and `memory_keys: [...]` to the worker — not the
   execution-params payload and not memory fact values. LM5L fixes world-state
   coherence; it does not solve payload visibility or authoring-role
   communication. If round-2 models still ask for `code`/`mode` values, that is
   separate evidence about action-authoring framing or knowledge-push, **not** a
   fixture-coherence failure.

## 4. Design

### 4.1 `derive_probe_graph_state()` — fixture derivation

New module-level function in `scripts/lm5k_worker_probe.py`:

- Compiles the **unchanged** workflow contract via `compile_workflow_contract`.
- Runs `run_current_step_stream(scaffold.graph, scaffold.provider,
  max_steps=3, runner=_OfflineCreateRunner())` under `asyncio.run` (the probe
  is synchronous; no competing event loop).
- Returns `(scaffold, stream_result)` so tests can assert on both the derived
  graph and the stream records.

`_OfflineCreateRunner` mirrors the LM4W chain-guard runner:

- For `create_script`: applies `apply_producer_result` with a deterministic
  wrapped-failure create receipt (`artifact_status: "created_with_errors"`,
  `verification.status: "failed"`, `repair_anchor` carrying the component guid)
  and returns a `LiveProducerResult`.
- For **any other node: raises**. With `max_steps=3` the stream stops after the
  bind step; reaching the repair producer would be a fixture bug, not a valid
  path.

Why this yields coherence by construction: the create producer's projection
emits `memory_updates.facts` (`component_guid`, `repair_anchor`) **from the
receipt**; the `verify_create` verifier outcome `needs_repair` flips the
`on_repair` edge so `repair_same_component` becomes `ready`; the bind step
writes `EXECUTION_PARAMS_KEY` params including `guid` bound from
`repair_anchor`. The current hand-injected memory facts in
`build_probe_context()` are **deleted, not relocated** — after LM5L nothing
about the world-state is asserted by hand.

### 4.2 Coherence guards — fail fast, factual, probe-specific

Two small functions (split so graph coherence stays separate from
caller-declared worker affordances), each check raising `RuntimeError` with an
explicit message of the form
`"LM5L coherent fixture invariant failed: repair node is not ready"`:

`_require_coherent_graph_state(scaffold, stream_result)` — derived-state facts:

1. current node `repair_same_component` exists and `status == "ready"`;
2. `EXECUTION_PARAMS_KEY` params present on the node (the same source the
   envelope's `has_execution_params` reads);
3. graph memory has concrete `repair_anchor` / `component_guid` facts
   (internal-guard assertion on values is allowed; the *envelope* never shows
   values, §3.5);
4. stream records include the create-producer record with evidence and the
   `verify_create` verifier record;
5. the verifier record's outcome is `needs_repair`.

`_require_probe_context_shape(context)` — caller-declared affordances:

6. `context.current_node is not None` and
   `context.current_node.node_id == "repair_same_component"` (LM5A
   deliberately has no duplicate top-level `current_node_id` field; the guard
   checks the public context shape);
7. allowed action `draft_repair_params` is present.

The guards are tripwires, not a second verifier: no receipt re-interpretation,
no policy, no schema validation — those belong to the LM5B/C/D/F spine. Their
purpose is that a future drift fails the probe at startup instead of burning
live API attempts on an incoherent envelope.

### 4.3 `build_probe_context()` — real history

Calls `derive_probe_graph_state()`, runs both guards, then builds the context
with **real history**:

```python
build_local_worker_turn_context(
    scaffold,
    stream_result.final_graph,
    stream_result.records,          # was ()
    stream_result.supply_records,   # was ()
    current_node_id="repair_same_component",
    knowledge=(...),                # unchanged: planner-authored input
    allowed_actions=(...),          # unchanged: planner-authored input
)
```

The knowledge packet and allowed action stay hand-declared — they are
planner-authored inputs, not world-state claims. `build_probe_context()` runs
once per candidate as today; derivation is deterministic and millisecond-cheap,
so no caching.

## 5. Scenario identity

Constants in the probe script:

```python
SCENARIO_WORKFLOW_ID = "lm5k_first_probe"        # unchanged: same workflow family
SCENARIO_ID = "lm5k_golden_repair_v2"            # new experiment scenario
SCENARIO_VERSION = "v2"
SCENARIO_STATE = "post_verify_needs_repair"
```

- The LM5F expectation's `scenario_id` becomes `lm5k_golden_repair_v2`.
- The manifest gains a structured scenario block replacing the bare
  `scenario_workflow_id` string field:

```json
"scenario": {
  "workflow_id": "lm5k_first_probe",
  "scenario_id": "lm5k_golden_repair_v2",
  "scenario_version": "v2",
  "state": "post_verify_needs_repair"
}
```

- Comparison key becomes `(prompt_text_version, scenario_id, scenario_version,
  resolved_model, schema versions, generation_params)`. Rounds 1/1b are labeled
  retroactively in the round-2 evidence doc as `lm5k_golden_repair_v1` /
  `fresh_compiled_graph`; no old artifacts are edited.

## 6. Tests (extend `mcp_server/tests/test_lm5k_worker_probe.py`)

Two layers must agree — the antidote to the round-1b mistake is proving the
envelope a model sees agrees with our expectations, not just building a context
that passes them.

**Layer 1 — derived graph state is coherent:**

- stream stopped at the expected point; runner calls `== ["create_script"]`;
- record sequence is producer / verifier / bind;
- create producer record ran/applied with receipt evidence (the receipt is
  intentionally `created_with_errors` with `verification.status: "failed"` —
  "applied" must not be misread as "script verified clean");
- verifier record outcome `needs_repair` (asserted separately — the verifier,
  not the producer record, carries the repair signal);
- `repair_same_component` `ready`, bound params include the receipt guid;
- memory facts (`repair_anchor`, `component_guid`) are receipt-derived, and the
  hand-injection is provably gone.

**Layer 2 — rendered LM5I envelope tells the same coherent story**, asserted on
`render_local_worker_turn_request_payload(build_probe_context())` using only
**model-visible** facts (§3.5):

- `ready_node_ids` includes `repair_same_component`;
- current node status `ready`;
- `has_execution_params is True` (not: params visible);
- `memory_keys` includes `repair_anchor` and `component_guid` (not: fact values
  present);
- history reflects the create and verify records;
- `draft_repair_params` is offered.

These are point-for-point the negations of the ceiling's round-1b refusal
claims.

**Guard tests:**

- feed `_require_coherent_graph_state` doctored states and assert the specific
  failure messages;
- regression case: reconstruct the round-1b shape (freshly compiled graph,
  `current_node_id` forced) and prove the guard rejects it — the guard would
  have caught round 1b, and the test proves it stays able to;
- `_require_probe_context_shape` rejected on a context missing the allowed
  action.

Existing tests are updated only where scenario id / manifest shape changed.

## 7. Process

- Worktree `C:/UDEV/Rook-lm5l`, branch `codex/lm5l-coherent-probe-fixture`, cut
  explicitly from `main` (`87886a40`); own venv.
- Gates: focused probe/local-worker pytest suite green; `py -3.10 -m
  py_compile` on touched files; exact `git diff --name-only origin/main..HEAD`
  scope assertion (probe script, probe test file, spec/plan docs only);
  `git diff --check`.
- PR stops before merge; merge requires explicit user approval.
- **Round 2 is post-merge activity** (probes are evidence, never CI): run the
  panel from repo root with the same command as rounds 1/1b (`--capture-raw`,
  key sourced from `mcp_server/.env`, never printed), then author the round-2
  evidence section comparing `v1` vs `v2` scenarios in its own docs PR.

## 8. Out of scope

- Prompt-text v2 (Haiku fence-discipline baseline 10/10; authoring-role
  framing) — explicitly behind LM5L.
- Payload visibility / knowledge-push design (whether workers should ever see
  param values) — a planner-harness question, informed by round-2 evidence.
- Queued LM5K hardening wishlist: `_git_short_sha` cwd anchoring; mixed
  loaded/transport-error offline e2e; `api_base`/model digest in the comparison
  key.
- Any shared test-fixture module (rejected: guard independence beats DRY for
  evidence infrastructure; the LM4W chain guard keeps its own copies
  deliberately).
