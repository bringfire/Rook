# LM7E Model-Authored Live Splice Probe Design

Status: design checkpoint for review

Date: 2026-07-07

## 1. Purpose

LM7E joins the Planner-model authoring line to the request-driven live splice
line.

Core claim:

```text
One shape_guidance_v2 Planner-model-authored intent_incomplete request can be
strictly parsed, validated, materialized, routed, consumed by the frozen worker
splice, and driven to a receipted terminal outcome without changing LM5, LM6, or
LM7B protocol seams.
```

LM7E optimizes for a clean receipt, not for success. A parse failure,
`workflow_validate` rejection, runtime routing gate failure, worker decline,
publication failure, live repair rejection, or accepted live repair is valid
evidence if it is classified and receipted without muddying the chain.

LM7E is not:

- a new request schema
- a new Planner prompt experiment
- a Planner retry or repair loop
- a worker prompt change
- a worker retry slice
- an N=5 repeatability run
- a Gemma promotion claim

## 2. Context

LM7B proved that a hand-authored `PlannerWorkerContractRequest:v1` can head the
live provenance chain and drive the frozen one-turn worker splice to accepted
live repair.

LM7C then tested Planner-model authorship offline. GPT-5.5 obeyed strict JSON
and did not invent missing intent, but failed the sparse request surface:

```text
parse_success_count: 10/10
workflow_validate_valid_count: 0/10
invented_count: 0/10
over_declared_count: 0/10
```

LM7D added `shape_guidance_v2` and kept the same schema, validator, classifier,
template menu, briefs, and strict parser. The canonical GPT-5.5 run produced:

```text
parse_success_count: 10/10
workflow_validate_valid_count: 10/10
canonical_success_count: 10/10
invented_count: 0/10
over_declared_count: 0/10
hidden_marker_match_count: 0
```

An exploratory local Gemma run also produced `10/10` non-canonical success under
the same shape-guidance profile. That is useful floor-finding evidence, but it
does not replace the Planner-tier canonical model for LM7E.

LM7E asks the next joined question:

```text
Can the model-authored request become the provenance head of the live splice?
```

## 3. Scope

In scope:

- new sibling script:
  `scripts/lm7e_model_authored_live_splice_probe.py`
- `shape_guidance_v2` Planner authoring prompt/menu/brief artifacts
- one Planner-model provider call before live work
- strict JSON parse of the exact raw provider output
- `workflow_validate` gate
- LM7A materialization from the exact parsed request
- full resolved source-routing artifact
- bounded workflow-contract summary and fingerprint
- LM7B-style live create, verify-create, runtime routing, worker publication,
  worker-action apply, repair dispatch, and verify-repair sequence
- one-turn frozen worker protocol with retry disabled
- LM7E-owned run directory, artifacts, manifest, and decision record
- deterministic implementation PR with fake provider/live fakes
- one post-merge canonical live run from synced `main`
- separate doc-only evidence summary PR after the live run

Out of scope:

- extending LM7B or LM7C as modes
- live run during the implementation PR
- multiple Planner attempts
- prompt repair loop
- validator-diagnostic feedback loop
- JSON repair or markdown extraction
- N=5 repeatability
- scenario matrix
- `intent_complete` canonical scenario
- new template family
- request schema changes
- `workflow_validate` changes
- LM5W/LM5X/LM5Y changes
- LM6A/LM6E worker protocol changes
- worker retry
- worker prompt/evidence shape changes
- production Planner/compiler runtime integration beyond existing LM7A seams
- full graph dumps
- dumping hidden bind params or hidden repair literals

## 4. Approach Decision

LM7E uses a new sibling script:

```text
scripts/lm7e_model_authored_live_splice_probe.py
```

Rejected:

```text
scripts/lm7b_request_driven_live_splice_probe.py --provider-command ...
scripts/lm7c_planner_authoring_probe.py --live-splice ...
```

Reason:

- LM7C owns offline authoring measurement.
- LM7B owns hand-authored request-driven live splice.
- LM7E owns the joined provenance chain: model-authored request to live splice.
- A sibling script keeps run identity, artifacts, and terminal decisions
  legible.

LM7E may reuse helper logic from LM7B and LM7C if doing so is mechanically
behavior-preserving. Reuse must not change LM7B, LM7C, LM7D, LM6, or LM5
behavior. If a helper is not safely parameterizable, LM7E should duplicate the
minimal script-local logic and add parity tests.

## 5. Canonical Run Shape

Canonical LM7E uses:

```text
planner_provider: codex-cli-chatgpt
planner_model: gpt-5.5
prompt_profile: shape_guidance_v2
prompt_version: lm7d.planner_authoring_prompt_shape_guidance:v2
template_menu_version: lm7c.template_menu:v1
brief_version: lm7c.intent_incomplete_brief:v1
scenario: intent_incomplete
attempts: 1
worker_model: gemma4:12b-it-qat
worker_endpoint: http://localhost:11434/api/chat
canonical_evidence: true
```

`intent_incomplete` is canonical because it exercises the Planner v1
restraint surface:

```text
model declares desired_output_value unresolved
model adds planner_user_intent -> unresolved_intent route
workflow_validate accepts the request
live splice proceeds without treating unresolved intent as acceptance criteria
```

LM7E v1 does not run `intent_complete`, does not run both briefs, and does not
run a matrix.

Planner provider/model overrides are allowed only for exploratory runs:

```text
canonical_evidence: false
```

For example, an Ollama/Gemma LM7E run may be useful later, but it must be
labeled exploratory local-planner live splice evidence and must not replace the
canonical GPT-5.5 Planner-tier run.

`--canonical-evidence` must be rejected unless all of these hold:

```text
planner_provider == codex-cli-chatgpt
planner_model == gpt-5.5
prompt_profile == shape_guidance_v2
scenario == intent_incomplete
attempts == 1
worker_model == gemma4:12b-it-qat
worker_endpoint == http://localhost:11434/api/chat
worker_temperature == 0
```

The worker splice still uses the frozen LM6/LM7B worker publication defaults
unless explicitly overridden for non-canonical diagnostics:

```text
worker_model: gemma4:12b-it-qat
worker_endpoint: http://localhost:11434/api/chat
worker_temperature: 0
worker_retry_enabled: false
```

Planner model selection and worker model selection are separate surfaces.
Canonical GPT-5.5 Planner evidence must not cause the worker publication call
to use GPT-5.5.

## 6. Planner Authoring Input

LM7E uses the LM7D shape-guidance authoring surface, not a new prompt:

```text
prompt_profile: shape_guidance_v2
planner_authoring_prompt_version: lm7d.planner_authoring_prompt_shape_guidance:v2
template_menu_version: lm7c.template_menu:v1
brief_version: lm7c.intent_incomplete_brief:v1
```

LM7E should preserve exact LM7D prompt/menu/brief semantics.

Implementation may achieve this by either:

1. extracting a tiny script-support helper from LM7C, with tests proving LM7C
   sparse and shape-guidance prompt artifacts are unchanged; or
2. duplicating the minimal prompt construction locally, with tests proving LM7E
   prompt/menu/brief artifacts match LM7D artifacts byte-for-byte.

If a helper is extracted, it should be script-support only, for example:

```text
scripts/lm7_planner_authoring_prompt_support.py
```

Allowed helper ownership:

- prompt profile constants
- prompt version constants
- template menu artifact
- `intent_complete` and `intent_incomplete` brief artifacts
- rendering the Planner authoring prompt for `shape_guidance_v2`
- strict parser helper, only if already cleanly separable
- provider-command call helper, only if LM7C tests prove unchanged behavior

Forbidden helper ownership:

- LM7C scoring
- LM7E live splice
- `workflow_validate`
- LM7A materialization
- Rhino/GH calls
- worker publication
- decision vocabulary

LM7E must not include a full solved request exemplar, new prompt-shape guidance,
validator feedback, repair-loop instructions, worker-facing criteria prose,
repair code, output assignment literals, or hidden bind values.

## 7. Raw Planner Output and Parsed Request

LM7E writes both the raw model output and parsed request when available.

Raw output artifact:

```text
planner_model_output.txt
```

Rules:

- exact raw provider output used for strict parsing
- stored only under ignored `probe_runs`
- provenance artifact, not an alternate parse source
- may contain bad model-authored output if the model fails
- marker scanning over raw output is report-only

Decision records include bounded raw-output provenance:

```text
planner_model_output_sha256
planner_model_output_excerpt
planner_model_output_path
```

Parsed request artifact:

```text
planner_request.json
```

Rules:

- written only after strict parse succeeds
- exact parsed JSON object
- authority for `workflow_validate`
- authority for LM7A materialization
- raw output is never reparsed or semantically inspected after the strict parse
  result has been produced

Request fingerprint:

```text
request_fingerprint = sha256(canonical_json(planner_request.json))
```

## 8. Strict Parser Gate

LM7E requires exactly one JSON object.

Forbidden:

- markdown fence extraction
- prose stripping
- JSON repair
- schema repair
- fallback parse
- second Planner call
- validator-feedback retry

If strict parse fails:

```text
decision = rejected_by_validate
reason = planner_parse_failed
planner_parse_status = parse_failed
planner_validation_status = not_evaluated
planner_intent_decision = not_classifiable
live_rhino_work_started = false
worker_publication_ran = false
```

Artifacts:

- write `planner_model_output.txt`
- write `decision.json`
- do not write `planner_request.json`
- do not write `workflow_validate_report.json`
- do not run Rhino/GH
- do not call worker publication

### 8.1 Parsed Request Marker Gate

After strict parse succeeds, LM7E scans the parsed `planner_request.json`
payload for Planner hidden/invention markers:

```text
PROBE_REPAIR_CODE
A = 42.0
A = 0.0
A = 1.0
BindStepSpec.base_params
repair_same_component.bind.base_params
```

If a marker appears inside the parsed request, LM7E fails closed before
`workflow_validate`, materialization, Rhino/GH work, or worker publication:

```text
decision = rejected_by_validate
reason = planner_hidden_marker_detected
planner_parse_status = parsed
planner_validation_status = not_evaluated
live_rhino_work_started = false
worker_publication_ran = false
```

Artifacts:

- write `planner_model_output.txt`
- write `planner_request.json`
- write `decision.json`
- do not write `workflow_validate_report.json`
- do not materialize the request
- do not run Rhino/GH
- do not call worker publication

This gate is intentionally stricter than raw-output marker scanning. Raw invalid
Planner output is preserved as evidence. A strict-parsed request is about to
become the authority for validation and materialization, so hidden/invention
markers inside it must stop the run.

## 9. Workflow Validate Gate

If parsing succeeds and the parsed-request marker gate passes, LM7E runs:

```python
validate_planner_worker_contract_request(planner_request)
```

Requirement:

```text
workflow_validate_report.valid == true
```

Artifacts:

```text
planner_request.json
workflow_validate_report.json
workflow_validate_report_fingerprint
request_fingerprint
```

If validation fails:

```text
decision = rejected_by_validate
reason = workflow_validate_failed
planner_parse_status = parsed
planner_validation_status = workflow_validate_failed
live_rhino_work_started = false
worker_publication_ran = false
```

No Rhino/GH work may run after a validation failure.

LM7E may also compute `planner_intent_decision` using the existing LM7C/LM7D
classifier semantics for metadata. Intent metadata must not override
`workflow_validate`.

Example for an intent-correct but workflow-invalid request:

```json
{
  "decision": "rejected_by_validate",
  "reason": "workflow_validate_failed",
  "planner_parse_status": "parsed",
  "planner_validation_status": "workflow_validate_failed",
  "planner_intent_decision": "correct_declared",
  "live_rhino_work_started": false,
  "worker_publication_ran": false
}
```

## 10. Materialization

After `workflow_validate` succeeds, LM7E must retrieve materialized artifacts by
calling:

```python
materialize_planner_worker_contract_request(planner_request)
```

on the exact parsed payload written to `planner_request.json`.

`workflow_validate` provides the validation report and fingerprints. It is not
the source of the full materialized artifacts. LM7E must not duplicate or
re-derive LM7A materialization logic inside the live probe script.

Materialization outputs consumed by LM7E:

```text
workflow_contract
resolved_source_routing
worker_node_ids
```

## 11. Contract and Routing Artifacts

LM7E writes the full resolved routing artifact:

```text
resolved_source_routing.json
```

Reason:

```text
routing artifact = worker-visible source declaration, designed to be auditable
```

The resolved routing artifact must include the model-authored unresolved-intent
route:

```yaml
route_id: missing_desired_output_value
source_class: planner_user_intent
source_path: planner.intent.desired_output_value
purpose: unresolved_intent
required: false
```

LM7E writes only a bounded workflow-contract summary:

```text
workflow_contract_summary.json
```

Allowed summary fields:

- selected `template_id`
- workflow contract id or schema if already public
- node ids
- rule ids
- worker node ids
- worker-node bind-step absence/presence summary
- initial param keys
- initial param counts
- bounded hashes of initial param values
- workflow contract fingerprint, if safe

Forbidden:

- dumping loaded `RookWorkflowContract` object
- dumping `BindStepSpec.base_params`
- dumping hidden repair literals
- dumping full execution params except bounded live summaries already allowed by
  LM7B/LM6A
- full graph dumps

Fingerprint rule:

```text
workflow_contract_fingerprint =
  sha256(canonical materialized workflow contract payload)
```

only if that payload can be proven not to expose hidden bind values. Otherwise:

```text
workflow_contract_fingerprint =
  sha256(canonical workflow_contract_summary.json)
```

Tests must assert:

- `resolved_source_routing.json` contains the unresolved-intent route above.
- `workflow_contract_summary.json` reports no `BindStepSpec` for
  `repair_same_component`.
- `workflow_contract_summary.json` does not contain `base_params`,
  `PROBE_REPAIR_CODE`, `A = 42.0`, `A = 0.0`, or `A = 1.0`.

## 12. Live Sequence

LM7E runs the same logical live sequence as LM7B after validation succeeds:

```text
1. Build LM7E run directory.
2. Render/write Planner prompt/menu/brief artifacts.
3. Call Planner model provider once.
4. Write raw Planner output.
5. Strict parse PlannerWorkerContractRequest.
6. Run workflow_validate.
7. Materialize contract/routing from parsed request.
8. Write routing artifact and bounded contract summary.
9. Live dispatch create_script.
10. Run verify_create.
11. Run runtime LM5AA routability gate.
12. Run LM5X extraction + LM5W assembly.
13. Project LM5W packet to LM5Y legacy worker-visible acceptance criteria.
14. Build full worker-visible evidence envelope.
15. Run one-turn worker publication.
16. If action_request, apply worker action via worker-action applier.
17. If applier stages params, live dispatch gh_update_script.
18. Run verify_repair.
19. Write decision.json.
```

No generic workflow runner auto-advance is introduced in LM7E.

## 13. Runtime Routing Gate

After live `create_script` and `verify_create`, LM7E runs runtime routing
validation with LM5AA:

```python
validate_worker_visible_source_routing(
    resolved_source_routing,
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
reason = runtime_routing_validate_failed
worker_publication_ran = false
```

LM7E must write:

```text
runtime_routing_validation.json
```

This gate proves the live evidence exists. It does not judge whether the worker
will act.

## 14. Acceptance Criteria and Worker Evidence

LM7E must preserve the LM6/LM7B worker-visible evidence shape.

Full LM5W packet:

```text
acceptance_criteria_packet.json
```

is artifact-only.

Worker-visible acceptance criteria:

```text
worker_visible_acceptance_criteria.json
```

must use the LM5Y legacy projection:

```yaml
source: workflow_contract + create_script.initial_execution_params + create_script.receipt.script_receipt.repair_anchor + script_body_gotcha
criteria:
  - criterion_id
    description
    source
```

The worker prompt must not receive LM5W internal metadata:

```text
schema
source_set
source_class
unresolved_intent
fingerprint
```

The worker-visible evidence envelope must preserve the proven LM6/LM7B fields,
including:

- `current_code`
- `language`
- `recommended_mode`
- `repair_anchor`
- `pin_contract`
- `target_diagnostics`
- `expected_repair_outcome`
- legacy-projected `acceptance_criteria`

LM7E must not call an LM6A or LM7B helper that rebuilds worker evidence from an
old probe contract. The actual worker request must be built from the
model-authored, validated, materialized LM7E contract/routing output.

## 15. Worker Path

Worker path constraints:

- one worker publication turn only
- no LM6E retry
- no `retry_context`
- no worker prompt changes
- no worker evidence shape changes
- no hidden bind params
- no hand-written repair params
- no repair-code suggestion from the Planner
- no second Planner call
- no Planner feedback loop

LM7E reuses the frozen worker-action applier semantics:

```text
action_id == draft_repair_params
action_input keys == code, mode
mode == body
trusted anchor supplies component_guid/language
```

Worker-authored action params are still the only source of repair execution
params after the live create receipt exists.

## 16. Terminal Decisions

LM7E uses the LM7B terminal vocabulary:

```text
accepted
rejected
worker_declined
gate_failed
publication_failed
rejected_by_validate
```

`rejected_by_validate` covers pre-live Planner request failures:

```text
planner_parse_failed
planner_hidden_marker_detected
workflow_validate_failed
```

It does not mean the live worker or model repair path failed; those paths were
not reached.

Planner metadata in `decision.json`:

```text
planner_parse_status
planner_validation_status
planner_intent_decision
planner_model_output_sha256
planner_model_output_excerpt
planner_model_output_path
request_fingerprint
workflow_validate_valid
workflow_validate_report_fingerprint
live_rhino_work_started
worker_publication_ran
```

Other decision fields should remain aligned with LM7B where applicable:

```text
runtime_routing_valid
runtime_routability_evaluated
worker_response_kind
worker_action_input_sha256
worker_action_input_excerpt
live_repair_dispatched
verify_repair_ran
```

## 17. Artifacts

LM7E writes:

```text
probe_runs/lm7e-<timestamp>-<sha>/
  manifest.json
  prompts/
    planner_authoring_prompt.txt
    template_menu.json
    intent_incomplete_brief.txt
  planner_model_output.txt
  planner_request.json                       # only after strict parse succeeds
  workflow_validate_report.json              # only after parse + marker gate pass
  resolved_source_routing.json               # only after validation succeeds
  workflow_contract_summary.json             # only after validation succeeds
  runtime_routing_validation.json            # only after live create/verify_create
  acceptance_criteria_packet.json            # artifact-only full LM5W packet
  worker_visible_acceptance_criteria.json
  worker_publication_row.json                # only if worker publication ran
  worker_action.json                         # only if action_request
  live_create_summary.json                   # only if live create ran
  verify_create_summary.json                 # only if verify_create ran
  live_repair_summary.json                   # only if repair dispatched
  verify_repair_summary.json                 # only if verify_repair ran
  decision.json
```

No raw full graph dump is written in LM7E v1.

## 18. Manifest

`manifest.json` records:

```text
schema: rook.lm7e_model_authored_live_splice_probe:v1
git_commit
canonical_evidence
scenario
attempts
prompt_profile
prompt_version
template_menu_version
brief_version
worker_retry_enabled: false
planner_provider
planner_model
worker_model
worker_endpoint
worker_temperature
planner_model_output_path
planner_model_output_sha256
request_fingerprint, if available
workflow_validate_report_fingerprint, if available
workflow_contract_fingerprint, if available
```

The manifest should distinguish canonical GPT-5.5 evidence from exploratory
local-provider runs.

## 19. Marker Scanning

LM7E scans Planner prompt, raw-output, parsed-request, and non-worker metadata
for:

```text
PROBE_REPAIR_CODE
A = 42.0
A = 0.0
A = 1.0
BindStepSpec.base_params
repair_same_component.bind.base_params
```

Planner raw output marker scanning is report-only. If the Planner emits a hidden
marker in raw invalid output, that is evidence and should remain available in
`planner_model_output.txt` under ignored `probe_runs`.

The `A = 0.0` and `A = 1.0` terms are Planner-authorship invention markers in
LM7E. They must not appear in Planner prompt artifacts, parsed Planner request
metadata, routing artifacts, or workflow-contract summaries. If they appear in
raw Planner output or bounded raw-output excerpts, LM7E must preserve that as
model-authored evidence and classify/report it through Planner metadata rather
than erasing it.

They are not worker hidden-answer markers by themselves. A later worker-authored
`draft_repair_params.code` may legitimately contain concrete repair code such
as `A = 0.0;` or `A = 1.0;`, because the worker is the repair-code author in
the frozen splice. LM7E must not reinterpret legitimate worker-authored action
code as Planner invention.

Planner marker scanning explicitly excludes worker action fields:

```text
worker_action_input_sha256
worker_action_input_excerpt
worker_action_input_full_path
worker_action.json
```

Those fields belong to the frozen worker-action channel and remain governed by
the existing LM6/LM7B worker-action hidden-answer fences. LM7E must not count a
legitimate worker-authored repair excerpt in `decision.json` as a Planner marker
match.

No hidden marker may enter:

- prompt artifacts
- manifest non-output metadata
- workflow contract summary
- worker-visible evidence
- worker action staging except through the existing LM7B/LM6 worker-action
  hidden-answer fences

Marker matches should be summarized in `decision.json` or manifest-level summary
fields, but they do not replace parse, validation, runtime routing, or worker
decision semantics.

## 20. CLI

Canonical shape:

```powershell
python scripts\lm7e_model_authored_live_splice_probe.py `
  --planner-provider-command "<adapter>" `
  --planner-provider codex-cli-chatgpt `
  --planner-model gpt-5.5 `
  --canonical-evidence
```

Allowed operational knobs:

```text
--planner-provider-command
--planner-provider
--planner-model
--run-dir
--planner-provider-timeout-s
--worker-model
--worker-endpoint
--worker-temperature
--worker-timeout-s
--output-excerpt-chars
--canonical-evidence
```

Fixed in LM7E v1:

```text
prompt_profile = shape_guidance_v2
scenario = intent_incomplete
attempts = 1
worker_retry_enabled = false
```

Forbidden CLI:

```text
--request-json
--scenario intent_complete
--attempts > 1
--retry
--phase receipt_recon
--repair-json
--live-run-matrix
```

There is no recon-only mode in LM7E v1. The parse and validation gates happen
before live work; runtime routability remains part of the full run.

## 21. Deterministic Implementation PR

The implementation PR should include deterministic tests only:

- fake Planner provider success
- fake Planner provider parse failure
- fake Planner provider workflow-validate failure
- no live work before parse/validate success
- raw output written before parse result
- `planner_request.json` written only after parse success
- parsed-request marker detection produces `rejected_by_validate` with
  `reason = planner_hidden_marker_detected` before `workflow_validate`
- worker action excerpts are excluded from Planner marker scanning
- workflow validate report written only after parse success and parsed-request
  marker gate success
- materialization called on the exact parsed request
- resolved routing artifact contains the unresolved-intent route
- contract summary omits hidden bind markers
- `repair_same_component` has no worker-node `BindStepSpec`
- runtime routing failure produces `gate_failed`
- worker-visible evidence preserves the LM7B/LM6 envelope
- LM5W full packet remains artifact-only
- worker retry disabled
- canonical evidence gating rejects local Planner Gemma, wrong Planner model,
  wrong worker model, and wrong prompt/scenario
- fake live accepted path writes expected artifacts
- fake live worker decline/publication failure/rejection paths are receipted

Tests must not require:

- Rhino
- Grasshopper
- Ollama
- OpenAI/Anthropic credentials
- live model calls
- live worker publication

## 22. Diff Scope

Expected implementation scope:

```text
docs/superpowers/specs/2026-07-07-lm7e-model-authored-live-splice-design.md
docs/superpowers/plans/2026-07-07-lm7e-model-authored-live-splice.md
scripts/lm7e_model_authored_live_splice_probe.py
mcp_server/tests/test_lm7e_model_authored_live_splice_probe.py
```

Allowed only if tests prove helper extraction is the safest behavior-preserving
path:

```text
scripts/lm7_planner_authoring_prompt_support.py
LM7C prompt artifact preservation tests
minimal LM7C import updates that do not change outputs
```

Default expectation:

- no production `mcp_server/src` changes
- no LM5/LM6/LM7A schema changes
- no LM7B worker splice semantic changes
- no LM7C scoring/classifier changes
- no live run artifacts committed

## 23. Post-Merge Evidence

After deterministic implementation merges, run one canonical LM7E live probe
from synced `main` with Rhino/GH intentionally prepared:

```powershell
python scripts\lm7e_model_authored_live_splice_probe.py `
  --planner-provider-command "<codex adapter>" `
  --planner-provider codex-cli-chatgpt `
  --planner-model gpt-5.5 `
  --canonical-evidence
```

The evidence summary PR should record:

- run dir
- git commit
- planner provider/model
- worker model/endpoint
- prompt/profile versions
- raw output hash/excerpt
- parsed request fingerprint
- workflow_validate result
- runtime routing result
- worker publication result
- terminal decision
- whether live create/repair/verify ran
- marker scan result

If the terminal decision is `rejected_by_validate`, that is still a successful
LM7E measurement. It means the live chain was correctly gated before Rhino/GH or
worker publication.

## 24. Follow-Ups

Possible follow-ups depend on LM7E evidence:

If canonical GPT-5.5 reaches `accepted`:

```text
Consider a paired exploratory Gemma LM7E live splice or a small repeatability
slice.
```

If canonical GPT-5.5 is `rejected_by_validate`:

```text
Inspect whether LM7D offline/provider prompt parity drifted before designing any
repair loop.
```

If runtime routing fails:

```text
Treat it as a live provenance/materialization boundary issue, not a Planner model
safety result.
```

If worker declines or publication fails:

```text
Treat it as a worker splice outcome under a model-authored provenance head, not
as Planner request invalidity.
```

Gemma exploratory live splice should remain explicitly non-canonical unless a
later spec promotes local Planner evidence to a first-class comparison target.

## 25. Success Criteria

LM7E succeeds deterministically when the implementation PR proves:

- a model output can be strictly parsed or rejected before live work
- a parsed request can be validated or rejected before live work
- successful validation materializes through LM7A
- resolved routing and bounded contract summary artifacts are written safely
- the LM7B-style live splice path consumes the model-authored request artifacts
- worker protocol remains unchanged
- all terminal outcomes are receipted

LM7E succeeds as live evidence when a single post-merge canonical run from
synced `main` produces a receipted terminal outcome from the model-authored
request-driven chain.

An `accepted` run proves first model-authored request-driven live arrival. Other
terminal decisions are still evidence if the run is cleanly gated and classified.
