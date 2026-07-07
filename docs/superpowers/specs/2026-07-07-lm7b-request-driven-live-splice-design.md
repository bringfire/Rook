# LM7B Request-Driven Live Splice Probe Design

Status: design checkpoint for review

Date: 2026-07-07

## 1. Purpose

LM7B is the first deterministic integration slice after LM7A.

LM7B's claim is:

```text
A validated PlannerWorkerContractRequest can head the live provenance chain
and drive the frozen worker splice to a receipted terminal outcome.
```

LM7B is not a Planner model probe. It does not ask a model to author a workflow.
It starts from the canonical, hand-authored LM7A request shape, validates and
materializes it, then uses the materialized contract and routing artifact to
drive the already-frozen one-turn worker splice.

## 2. Context

The worker line is closed for v1:

- LM6A proved first live arrival: a bounded local worker authored
  `draft_repair_params`, the worker-action applier staged those params, live
  `gh_update_script` ran, and `verify_repair` succeeded.
- LM6C proved repeatability of the frozen LM6B protocol: `5/5` scheduled
  attempts reached the worker path, `4/5` accepted live repairs, `1/5` ended in
  a clean observation disposition, and hidden-answer leak markers were `0`.
- LM6D froze the bounded-worker protocol shape and recorded the limitations.
- LM6E added a diagnostic retry variant, default off. LM7B does not consume the
  LM6E retry variant.

LM7A opened the Planner line with:

```text
PlannerWorkerContractRequest v1
  -> template selection
  -> initial param binding
  -> bounded routing delta
  -> unresolved intent declaration
  -> unified workflow_validate report
```

LM7B connects those two lines without changing either side's meaning.

## 3. Scope

In scope:

- new sibling script:
  `scripts/lm7b_request_driven_live_splice_probe.py`
- canonical script-local `PlannerWorkerContractRequest` literal
- authoring-time `workflow_validate` gate
- runtime LM5AA routability gate against the live graph
- one-turn frozen worker publication path
- LM7B-owned run directory, manifest, artifacts, and decision record
- deterministic tests with fakes in the implementation PR
- post-merge single live run from synced `main`
- separate doc-only evidence summary after the live run is reviewed

Out of scope:

- Planner model calls
- `--request-json` or external request loading
- template selector descriptors
- multiple request variants
- live run during the implementation PR
- N=5 repeatability
- LM6E retry
- worker prompt changes
- LM6A publication/applier semantic changes
- hidden bind params
- full graph dumps
- production Planner/compiler integration beyond the already-landed LM7A seam

## 4. Approach Decision

LM7B uses a new sibling script, not an LM6A mode:

```text
scripts/lm7b_request_driven_live_splice_probe.py
```

Rejected:

```text
scripts/lm6a_live_worker_splice_probe.py --planner-request
```

Reason:

- LM6A is the frozen worker splice runner.
- LM7B is the request/provenance-chain integration runner.
- LM7B must own request validation, request fingerprinting, materialized routing
  provenance, and LM7B decision artifacts.
- Extending LM6A would blur the distinction between the frozen worker protocol
  and the Planner-authored provenance head.

## 5. Canonical Request

LM7B v1 uses a script-local canonical request literal.

No checked-in JSON/YAML fixture and no CLI request override are allowed in v1.

Canonical request shape:

```yaml
schema: rook.planner_worker_contract_request:v1
template_id: repair_same_component_from_create_error
initial_params:
  create_script:
    pins_out:
      - A:double
routing_delta:
  enable_routes: []
  disable_routes: []
  set_required: {}
  add_unresolved_intent_routes:
    - route_id: missing_desired_output_value
      source_class: planner_user_intent
      source_path: planner.intent.desired_output_value
      purpose: unresolved_intent
      required: false
intent_slots:
  - intent_id: desired_output_value
    source_path: planner.intent.desired_output_value
    status: unresolved
    description: Desired output value was not provided.
```

The script writes this exact request as:

```text
planner_request.json
```

and records:

```text
request_fingerprint
```

The request is explicit evidence, not hidden script lore.

## 6. Validation Gates

LM7B has two required validation gates.

### 6.1 Gate 1: request_authoring_validate

Input:

```text
script-local PlannerWorkerContractRequest
```

Function:

```python
validate_planner_worker_contract_request(...)
```

Requirement:

```text
report.valid == true
```

Failure:

```text
decision = rejected_by_validate
reason = workflow_validate_failed
```

No live Rhino/GH work may run after this failure.

Gate 1 proves the Planner-authored request is legal to attempt. It does not
prove live receipts or runtime evidence exist.

After Gate 1 succeeds, LM7B must retrieve the materialized workflow contract and
resolved routing artifact by calling:

```python
materialize_planner_worker_contract_request(planner_request_payload)
```

on the exact same payload emitted to `planner_request.json`.

`workflow_validate` provides the validation report and fingerprints; it is not
the source of the full materialized artifacts. LM7B must not duplicate or
re-derive LM7A materialization logic inside the live probe script.

### 6.2 Gate 2: runtime_routability_validate

Gate 2 runs only after live `create_script` and `verify_create`.

Input:

```text
materialized routing artifact
live graph
script_body_gotcha convention packet
worker_node_ids = ("repair_same_component",)
```

Function:

```python
validate_worker_visible_source_routing(
    materialized_routing_artifact,
    workflow_contract=materialized_workflow_contract,
    graph=live_graph,
    convention_packets=(script_body_gotcha_packet,),
    worker_node_ids=("repair_same_component",),
)
```

Requirement:

```text
report.valid == true
report.routability_evaluated == true
```

Failure:

```text
decision = gate_failed
reason = runtime_routability_validate_failed
```

No worker publication may run after this failure.

Gate 2 proves the live evidence actually exists and is routable to the worker.

## 7. Live Splice Flow

Canonical LM7B sequence:

```text
1. Create LM7B run directory.
2. Write manifest.json.
3. Write planner_request.json from the canonical script-local literal.
4. Run workflow_validate.
5. Write workflow_validate_report.json.
6. If workflow_validate fails, write rejected_by_validate decision and stop.
7. Call materialize_planner_worker_contract_request(...) on the same emitted
   planner request payload to retrieve the workflow contract and routing
   artifacts.
8. Load/compile the materialized workflow contract.
9. Dispatch live create_script.
10. Run verify_create.
11. Write live_create_summary.json, verify_create_summary.json, phase_a_recon.json.
12. Run runtime LM5AA routability validation with live inputs.
13. Write runtime_routing_validation.json.
14. If runtime routability fails, write gate_failed decision and stop.
15. Extract LM5X sources from the live graph.
16. Assemble LM5W acceptance criteria packet.
17. Write acceptance_criteria_packet.json as artifact-only evidence.
18. Build worker-visible request using the LM5Y legacy projection.
19. Run one two-pass worker publication turn.
20. If publication fails or leaks hidden-answer markers, write publication_failed.
21. If the worker publishes non-action, write worker_declined.
22. If the worker publishes action_request, apply worker action to repair node.
23. If action apply fails, write rejected.
24. Dispatch live repair_same_component.
25. Run verify_repair.
26. Write accepted iff verify_repair succeeds; otherwise rejected.
```

LM7B may reuse LM6A helper functions if they are already parameterizable.

If a helper is not parameterizable but the logic is clearly shared, the
implementation may extract the smallest script-support helper. Any extraction
must include LM6A preservation tests.

If helper extraction would alter LM6A behavior, implementation must stop and
record the problem as a finding. It must not silently patch LM6A inside the
splice.

## 8. Logical LM6A Seam

The logical seam LM7B needs is:

```python
run_live_splice(
    *,
    workflow_contract,
    routing_artifact,
    request_fingerprint,
    workflow_validate_report_fingerprint,
    model,
    run_dir,
) -> decision_record
```

This is a design seam, not a required public API. The implementation may use
existing LM6A helpers directly, extract a small shared script helper, or keep the
sequence in LM7B if that is safer.

Any shared helper must preserve LM6A:

- same default CLI behavior
- same decision categories
- same publication row artifacts
- same leak checks
- same worker-action apply behavior
- same one-turn default behavior unless LM6E's explicit retry flag is used by
  LM6A itself

## 9. Worker-Visible Evidence Shape

LM7B must preserve the LM6/LM7 worker-visible shape.

The full LM5W packet is artifact-only:

```text
acceptance_criteria_packet.json
```

The worker-visible request uses the LM5Y legacy projection:

```json
{
  "source": "workflow_contract + create_script.initial_execution_params + create_script.receipt.script_receipt.repair_anchor + script_body_gotcha",
  "criteria": [
    {
      "criterion_id": "...",
      "description": "...",
      "source": "..."
    }
  ]
}
```

These LM5W fields must not enter the worker prompt in LM7B v1:

```text
schema
source_set
source_class
unresolved_intent
fingerprint
```

## 10. Retry Policy

Retry is disabled and unavailable in LM7B v1.

Pins:

- no `--retry-clean-observation`
- no retry context packet
- no retry artifacts
- one worker publication turn only
- clean observation or clarification leads to `worker_declined`

The manifest must include:

```json
{
  "worker_retry_enabled": false
}
```

LM7B consumes the frozen baseline worker splice, not the LM6E retry diagnostic
variant.

## 11. Decision Vocabulary

LM7B reuses the LM6A decision vocabulary and adds one pre-live validation
decision:

```text
accepted
rejected
worker_declined
gate_failed
publication_failed
rejected_by_validate
```

Decision meanings:

```text
rejected_by_validate
  PlannerWorkerContractRequest failed authoring-time workflow_validate.
  No live Rhino/GH work ran.

gate_failed
  Request validated, live create/verify ran, but runtime routability or
  acceptance-criteria extraction/assembly failed before worker publication.

publication_failed
  Worker publication failed or leak markers were detected before dispatch.

worker_declined
  Worker published a valid non-action response.

rejected
  Worker action reached the live splice path, but applier, live repair,
  or verify_repair failed.

accepted
  Worker action reached live repair and verify_repair succeeded.
```

`decision.json` must include:

```text
request_fingerprint
workflow_validate_valid
workflow_validate_report_fingerprint
runtime_routing_valid
runtime_routability_evaluated
worker_retry_enabled
```

When a phase has not run, its fields should be present with `null` or `false`
where that is clearer than omission.

## 12. Artifacts

LM7B writes a separate run directory:

```text
probe_runs/lm7b-<timestamp>-<sha>/
```

No child LM6A run directory is used.

Artifacts:

```text
manifest.json
planner_request.json
workflow_validate_report.json
phase_a_recon.json
runtime_routing_validation.json
acceptance_criteria_packet.json
worker_visible_acceptance_criteria.json
worker_publication_row.json
worker_action.json, only if action_request
live_create_summary.json
live_repair_summary.json, only if dispatched
verify_create_summary.json
verify_repair_summary.json, only if ran
decision.json
```

Artifact pins:

- no full graph dump
- no raw workflow contract dump if it could expose hidden params
- bounded summaries only
- `planner_request.json` is explicit and fingerprinted
- `workflow_validate_report.json` is explicit and fingerprinted
- full model transcripts are not copied into `decision.json`
- worker action code may appear only in ignored local artifacts and bounded
  decision excerpts/hashes, following the LM6A pattern

## 13. Hidden-Answer Policy

LM7B must preserve the hidden-answer fences from LM6A/LM7A.

Forbidden leak markers:

```text
PROBE_REPAIR_CODE
A = 42.0
BindStepSpec.base_params.code
BindStepSpec.base_params
repair_same_component.bind.base_params
```

These markers must not appear in:

- worker-visible request payloads
- `decision.json`
- bounded summary artifacts

If a worker-authored action contains hidden-answer markers, LM7B must classify
the run as `publication_failed` or `rejected` according to the inherited LM6A
safety point, with no live repair dispatch after a detected leak.

Legitimate worker-authored code such as `A = 0.0;` or `A = 1.0;` is not a leak.

## 14. CLI

Canonical command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm7b_request_driven_live_splice_probe.py
```

Allowed operational knobs:

```text
--model
--endpoint
--temperature
--timeout-s
--excerpt-chars
--run-dir
```

Defaults should match the LM6 worker path unless there is a specific reason not
to:

```text
model = gemma4:12b-it-qat
endpoint = http://localhost:11434/api/chat
temperature = 0
```

Forbidden CLI in LM7B v1:

```text
--request-json
--phase
--retry-clean-observation
```

There is no recon-only mode in LM7B v1. Authoring validation and runtime
routability are part of the full run.

## 15. Implementation PR Scope

Expected implementation PR scope:

```text
docs/superpowers/specs/2026-07-07-lm7b-request-driven-live-splice-design.md
docs/superpowers/plans/2026-07-07-lm7b-request-driven-live-splice.md
scripts/lm7b_request_driven_live_splice_probe.py
mcp_server/tests/test_lm7b_request_driven_live_splice_probe.py
```

Allowed only if implementation proves it is necessary:

```text
small script-support helper extraction
focused LM6A preservation tests for that extraction
```

Default expectation:

```text
no mcp_server/src production changes
no LM6A behavior changes
no worker prompt changes
no LM5W/LM5X/LM5Y evidence shape changes
no live run in implementation PR
no probe_runs artifacts committed
```

## 16. Deterministic Test Targets

Implementation tests should use fakes and must not require Rhino, Grasshopper,
Ollama, or a live model.

Required proof targets:

- canonical request is emitted and fingerprinted
- `workflow_validate` failure produces `rejected_by_validate` and no live calls
- valid `workflow_validate` allows live create/verify to begin
- runtime routability failure produces `gate_failed` and no worker publication
- runtime routability success allows worker publication
- worker-visible acceptance criteria are legacy-projected
- full LM5W packet remains artifact-only
- retry is unavailable and `worker_retry_enabled` is `false`
- no `--request-json` CLI exists
- no `--phase` recon-only mode exists
- no hidden-answer markers enter worker-visible request or `decision.json`
- publication failure, worker decline, applier rejection, live repair rejection,
  and accepted paths map to the locked decision vocabulary
- any helper extraction preserves LM6A default behavior and artifacts

Static checks:

```text
git diff --check main..HEAD
no probe_runs artifacts
no prompt instruction diff
no pass-two formatter/status/schema drift
no production mcp_server/src diff unless explicitly justified
```

## 17. Post-Merge Evidence

After the deterministic implementation PR merges, run one canonical LM7B live
probe from synced `main`:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm7b_request_driven_live_splice_probe.py
```

The live run should report:

- run directory
- git commit
- request fingerprint
- workflow_validate report fingerprint
- workflow_validate validity
- runtime routing validity and routability flag
- model
- terminal decision
- whether `worker_action.json` exists
- whether live repair and verify repair ran
- leak marker count

Do not replace the run. Any terminal outcome is evidence if it is receipted.

After review, write a separate doc-only evidence summary PR.

## 18. Relationship To LM7C

LM7B does not test Planner model authorship.

LM7C should ask:

```text
Can a Planner model author a valid PlannerWorkerContractRequest, and when
intent is missing, declare the missing slot instead of inventing it?
```

LM7B gives LM7C a validated consumption path. It proves that a request-shaped
Planner artifact can head the live chain before asking a model to produce that
artifact.

## 19. Success Criteria

LM7B succeeds deterministically when:

- the canonical request is explicit and fingerprinted
- `workflow_validate` is the authoring-time fence
- live LM5AA routability is the runtime evidence fence
- the worker-visible request shape remains frozen
- the worker splice remains one-turn, retry-disabled, and LM6-compatible
- all terminal paths write a decision record
- implementation tests require no live surface or model

LM7B succeeds as live evidence when a single post-merge run from synced `main`
produces a receipted terminal outcome from the request-driven chain.

An `accepted` live run proves request-driven arrival. Other terminal outcomes
are still useful if they preserve the provenance gates and do not leak hidden
answers.
