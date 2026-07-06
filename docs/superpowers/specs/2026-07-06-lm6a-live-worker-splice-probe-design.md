# LM6A - Live Worker Splice Probe Design

- **Date:** 2026-07-06
- **Status:** Draft for review
- **Slice:** LM6A
- **Type:** Deterministic implementation slice with post-merge live evidence run

## 1. Purpose

LM5U proved that bounded acceptance criteria moved the local worker from
clarification to action:

```text
diagnostics alone -> clarification
diagnostics + acceptance criteria -> action
```

LM5Y then joined that acceptance-criteria packet construction to the durable
LM5X/LM5W extraction and assembly seam without changing worker-visible input.

LM6A is the next arrival proof:

```text
Can a bounded worker-authored action reach the live Rhino/Grasshopper repair
floor and pass verify_repair?
```

LM6A is a splice, not a new workflow product. The existing live repair chain
has already proven create/verify/repair/verify with hand-staged params. The
LM5 worker line has proven bounded local decision/publication behavior. LM6A
tests the integrated seam:

```text
live receipt/routing facts
  -> worker-visible request
  -> two-pass worker action
  -> worker-action applier
  -> live gh_update_script
  -> verify_repair
```

LM6A measures bounded worker arrival, not freestyle model competitiveness.

## 2. Controlled Variables

Controlled variables in LM6A:

```text
live receipt/routing evidence from the actual create/verify_create run
worker-authored repair params replacing hidden bind params
worker-action staging into repair_same_component execution params
```

Unchanged:

```text
LM5S pass-1 decision instruction
two-pass publication mechanics
LM5U/Y acceptance-criteria visible evidence shape, using the legacy projection
LM5AA routing validation semantics
live gh_create_script / gh_update_script / verifier tools
canonical local Gemma/Ollama provider path
```

Not measured:

```text
freestyle model competitiveness
Hermes / llmfit / Anthropic baselines
semantic repair ranking beyond live verify_repair outcome
Planner model behavior
retry loops
KG retrieval
```

## 3. Scope

Production scope:

```text
mcp_server/src/rook/agent/plan_graph_worker_action_apply.py
```

Script scope:

```text
scripts/lm_worker_two_pass_publication.py
scripts/lm6a_live_worker_splice_probe.py
```

Test scope:

```text
mcp_server/tests/test_plan_graph_worker_action_apply.py
mcp_server/tests/test_lm_worker_two_pass_publication.py
mcp_server/tests/test_lm6a_live_worker_splice_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py if needed to pin
  behavior after helper extraction
```

Documentation scope:

```text
docs/superpowers/specs/2026-07-06-lm6a-live-worker-splice-probe-design.md
docs/superpowers/plans/2026-07-06-lm6a-live-worker-splice-probe.md
```

Implementation PR exclusions:

- No live run in the PR.
- No `probe_runs/` artifacts committed.
- No curated evidence summary in the implementation PR.
- No production workflow template changes.
- No `select_template` behavior change.
- No `BindStepSpec` semantics change.
- No generic sequence/current-step runner changes.
- No `RookWorkflowContract` schema mutation.
- No LM5G/LM5J/parser changes.
- No prompt text change unless the shared helper extraction must preserve the
  existing versioned prompt text exactly.
- No Anthropic key or cloud model path.
- No LiteLLM.
- No full graph dumps.

## 4. LM6A Contract Variant

LM6A uses a script-local bind-free contract variant.

The variant is derived locally for the probe. It keeps the same create,
verify_create, repair, and verify_repair node identities and live tool refs as
the LM5K/LM4 repair chain, but removes only the `BindStepSpec` that would write
hidden repair params for `repair_same_component`.

```text
repair_same_component rule:
  LM5K/LM4 chain: BindStepSpec + ProducerStepSpec
  LM6A variant:   ProducerStepSpec only
```

The worker action becomes the sole source of repair execution params.

Allowed in LM6A:

- script-local helper to build the bind-free contract variant
- tests proving `repair_same_component` contains no `BindStepSpec`
- tests proving `create_script`, `verify_create`, `repair_same_component`, and
  `verify_repair` identities stay stable
- tests proving `PROBE_REPAIR_CODE` / `A = 42.0;` do not appear in the LM6A
  contract or worker-visible request

Forbidden in LM6A:

- changing production workflow templates
- changing template selection
- leaving a bind step present and manually skipping it
- hidden bind/base params
- hand-written repair params

## 5. Manual Graph Sequencing

LM6A manually sequences the graph. It does not use the generic sequence runner
or current-step runner.

Canonical sequence:

```text
1. Build/select LM6A bind-free graph.
2. Set create_script execution params with the broken C# body.
3. Live dispatch create_script.
4. Run apply_verifier_step(graph, "verify_create", "create_script").
5. Run Phase A routing/extraction/criteria gate against the live graph.
6. If gate passes, build worker request from the live graph/context.
7. Run two-pass worker publication.
8. If no action, write worker_declined/publication_failed decision.
9. If action, apply_worker_action_to_node(...).
10. If applier rejects, write rejected decision.
11. Live dispatch repair_same_component.
12. Run apply_verifier_step(graph, "verify_repair", "repair_same_component").
13. Write accepted/rejected decision from verifier result.
```

Manual sequencing is required because the worker gate lives between:

```text
verify_create -> worker turn -> apply worker action -> repair_same_component
```

That gate is not a normal workflow step yet.

## 6. Phase A - Live Receipt Recon

Phase A is always run before any worker call in the canonical/full command.

Phase A performs:

```text
live create_script
apply verify_create
capture real create receipt
require repair_anchor.target_errors at the LM5X path
run LM5AA routability validation
run LM5X extraction
run LM5W assembly
write recon artifacts
```

Required diagnostic path:

```text
create_script.receipt.script_receipt.repair_anchor.target_errors
```

If Phase A cannot prove that the live receipt/routing/extraction facts support
the LM5U acceptance criteria, LM6A stops before the worker:

```text
decision = gate_failed
```

Phase A must fail closed for:

- missing or malformed create receipt
- missing repair anchor
- missing `target_errors`
- failed LM5AA routability validation
- failed LM5X extraction
- failed LM5W assembly
- hidden repair answer appearing in worker-visible evidence

LM5AA validation in Phase A is not static-only validation. The script must call
the validator with the live graph inputs and:

```text
worker_node_ids = ("repair_same_component",)
routability_evaluated = true
no severity="error" diagnostics in static_diagnostics
no severity="error" diagnostics in routability_diagnostics
```

If routability is skipped or produces errors, Phase A fails with
`gate_failed`.

## 7. Worker-Visible Acceptance-Criteria Shape

LM6A may write the full LM5W packet as a local artifact:

```text
acceptance_criteria_packet.json
```

That packet is artifact-only. It must not be inserted directly into the worker
prompt.

The worker-visible request keeps the LM5Y legacy projection:

```python
{
    "acceptance_criteria": {
        "source": (
            "workflow_contract + create_script.initial_execution_params + "
            "create_script.receipt.script_receipt.repair_anchor + "
            "script_body_gotcha"
        ),
        "criteria": [
            {
                "criterion_id": "...",
                "description": "...",
                "source": "...",
            },
            ...
        ],
    }
}
```

The following LM5W packet fields must not enter the worker-visible request:

```text
schema
source_set
source_class
unresolved_intent
fingerprint
rook.acceptance_criteria_packet:v1
```

## 8. Routing Artifact

LM6A uses a script-local routing artifact literal. It does not load a committed
JSON routing file and does not change `RookWorkflowContract`.

The artifact should match the LM5U/LM5Z repair route family:

```python
_LM6A_ROUTING_ARTIFACT = {
    "schema": "rook.worker_visible_source_routing:v1",
    "routes": [
        {
            "node_id": "repair_same_component",
            "visible_sources": [
                {
                    "route_id": "repair_pin_contract",
                    "source_class": "pin_contract",
                    "source_path": "create_script.initial_execution_params.pins_out",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_expected_outcome",
                    "source_class": "verifier_outcome",
                    "source_path": (
                        "workflow_contract.rules.verify_repair.expected_outcome"
                    ),
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_target_diagnostics",
                    "source_class": "receipt_diagnostic",
                    "source_path": (
                        "create_script.receipt.script_receipt.repair_anchor."
                        "target_errors"
                    ),
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
                {
                    "route_id": "repair_body_mode_convention",
                    "source_class": "convention",
                    "source_path": "script_body_gotcha",
                    "purpose": "acceptance_criteria",
                    "required": True,
                },
            ],
        }
    ],
}
```

Tests should assert the artifact is statically valid and routable against the
LM6A live-derived graph fixture shape.

## 9. Worker-Action Applier

LM6A adds a production agent-layer seam:

```text
mcp_server/src/rook/agent/plan_graph_worker_action_apply.py
```

Public surface:

```python
@dataclass(frozen=True)
class WorkerActionApplyResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    reason: str | None
    params_sha256: str | None


def apply_worker_action_to_node(
    graph: PlanGraph,
    node_id: str,
    *,
    action_id: str,
    action_input: Mapping[str, Any],
    anchor_binding: Mapping[str, Any],
    allowed_action_id: str = "draft_repair_params",
) -> WorkerActionApplyResult:
    ...
```

This seam is intentionally separate from `plan_graph_param_apply.py`.

```text
plan_graph_param_apply.py
  memory/bind-param seam

plan_graph_worker_action_apply.py
  model-authored action input + trusted anchor binding -> execution params
```

The applier is copy-on-write. It stages params by writing
`EXECUTION_PARAMS_KEY` onto the target node, but never dispatches live work.

Staged params are exactly:

```json
{
  "guid": "<trusted anchor guid>",
  "code": "<worker-authored code>",
  "mode": "body",
  "language": "csharp"
}
```

The worker provides only:

```json
{
  "code": "...",
  "mode": "body"
}
```

The trusted anchor binding provides only:

```json
{
  "component_guid": "...",
  "language": "csharp"
}
```

The applier must not accept whole `repair_anchor` objects. Diagnostics belong
in evidence, not execution-param staging.

## 10. Worker-Action Validation

Expected validation failures return:

```python
WorkerActionApplyResult(applied=False, reason="...")
```

Do not raise `ValueError` for malformed worker action JSON. A bad worker action
is loop evidence, not a programmer error.

Stable fail reasons:

```text
unknown_node
invalid_action_id
invalid_action_input
unexpected_action_input_key
missing_code
invalid_code
invalid_mode
invalid_anchor_binding
unexpected_anchor_binding_key
missing_component_guid
invalid_component_guid
missing_language
invalid_language
graph_copy_failed
```

Rules:

- `action_id` must equal `allowed_action_id`.
- `action_input` must be a mapping.
- `action_input` keys must be exactly `code`, `mode`.
- `code` must be a non-empty string.
- `mode` must equal `"body"`.
- `action_input` must not contain `guid` or `language`.
- `anchor_binding` keys must be exactly `component_guid`, `language`.
- `component_guid` must be a non-empty string.
- `language` must equal `"csharp"` in LM6A v1.
- The function never reads `BindStepSpec.base_params`.
- The function never invents code.

If the applier rejects a worker action, LM6A writes:

```text
decision = rejected
reason = worker_action_apply_failed:<reason>
live_repair_dispatched = false
verify_repair_ran = false
```

## 11. Shared Two-Pass Publication Helper

LM6A adds a script-support module:

```text
scripts/lm_worker_two_pass_publication.py
```

Public helper surface:

```python
@dataclass(frozen=True)
class TwoPassPublicationResult:
    row: dict[str, Any]
    response_payload: dict[str, Any] | None


def run_two_pass_worker_publication(
    request_payload: Mapping[str, Any],
    *,
    model: str,
    endpoint: str,
    temperature: float,
    timeout_s: float,
    excerpt_chars: int,
    post_chat: Callable[..., str] = _post_ollama_chat,
) -> TwoPassPublicationResult:
    ...
```

The helper owns shared mechanics:

- pass-1 decision prompt
- pass-1 JSON extraction/validation
- single-kind schema construction
- pass-2 formatter prompt
- LM5G response loading
- kind/action/refusal-category preservation checks
- observation-action anomaly scoring
- bounded row telemetry

LM5R remains the local matrix probe. It keeps:

- scenario selection
- matrix loop
- summary/manifest/run-directory identity
- result aggregation

LM6A keeps:

- live graph creation
- receipt recon
- routing validation
- worker request construction
- action apply
- live repair dispatch
- decision record

No production code imports the script helper.

## 12. Observation-Action Anomaly Handling

Observation-action anomaly scoring belongs in the shared helper because it
depends on parsed request and response objects.

The helper row carries:

```text
pass1_observation_action_intent_anomaly
pass1_observation_action_intent_reasons
pass2_observation_action_intent_anomaly
pass2_observation_action_intent_reasons
observation_action_intent_anomaly
observation_action_intent_reasons
```

Scoring rules stay LM5S-compatible:

- inspect parsed objects only
- do not scan raw provider content
- do not scan thinking text
- do not scan excerpts
- do not change publication status because of anomaly alone

LM6A decision mapping for non-action responses:

```text
clarification_request -> worker_declined / worker_clarified
refusal               -> worker_declined / worker_refused
observation no anomaly -> worker_declined / worker_observed
observation anomaly    -> worker_declined /
                          worker_observation_action_intent_anomaly
```

Observation anomaly does not become `rejected` because no action entered the
execution path.

## 13. LM6A CLI

Canonical command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6a_live_worker_splice_probe.py
```

Recon-only command:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6a_live_worker_splice_probe.py `
  --phase receipt_recon
```

CLI shape:

```text
--phase receipt_recon|full
--model gemma4:12b-it-qat
--endpoint http://localhost:11434/api/chat
--temperature 0
--timeout-s <default pinned in plan>
--excerpt-chars <default pinned in plan>
```

Default phase is `full`.

`receipt_recon`:

- runs Phase A only
- writes recon manifest/decision
- never calls the worker
- never calls `gh_update_script`

`full`:

- runs Phase A
- stops with `gate_failed` if Phase A fails
- otherwise runs Phase B

Canonical model:

```text
gemma4:12b-it-qat
```

Provider path:

```text
direct Ollama /api/chat
```

No Anthropic key is required. `--model` exists for ad hoc local variants only.
LM6A does not run a model matrix.

## 14. Terminal Decisions

Terminal decision vocabulary:

```text
accepted
rejected
worker_declined
gate_failed
publication_failed
```

Meaning:

```text
accepted
  worker action was staged, live repair dispatched, verify_repair succeeded

rejected
  worker action was published but failed applier validation, live repair dispatch,
  or verify_repair

worker_declined
  worker published a valid non-action response

gate_failed
  Phase A receipt/routing/extraction/assembly failed before worker call

publication_failed
  two-pass worker publication failed before a trusted LM5G response payload was
  available
```

Recon-only diagnostic decision:

```text
gate_passed
  --phase receipt_recon completed Phase A successfully and intentionally stopped
  before any worker or repair dispatch
```

`gate_passed` is not a full-run terminal decision. It may appear only when
`--phase receipt_recon` is selected.

Publication statuses mapped to `publication_failed`:

```text
pass1_provider_error
pass1_decision_invalid
pass2_provider_error
pass2_lm5g_invalid
pass2_invariant_violation
```

## 15. Decision Record

Every run writes `decision.json`.

For an applier rejection:

```json
{
  "decision": "rejected",
  "reason": "worker_action_apply_failed:invalid_mode",
  "phase": "worker_action_apply",
  "worker_response_kind": "action_request",
  "worker_action_id": "draft_repair_params",
  "worker_action_apply": {
    "applied": false,
    "reason": "invalid_mode",
    "params_sha256": null
  },
  "live_repair_dispatched": false,
  "verify_repair_ran": false
}
```

Decision records should include bounded references to worker action input:

```text
worker_action_input_sha256
worker_action_input_excerpt
worker_action_input_full_path
```

`decision.json` must not store unbounded model output or full action code. The
full action payload may be stored separately in ignored local artifacts.

## 16. Run Artifacts

LM6A writes ignored local artifacts under:

```text
probe_runs/lm6a-<timestamp>-<sha>/
```

Artifact layout:

```text
manifest.json
phase_a_recon.json
routing_validation.json
acceptance_criteria_packet.json   # full LM5W packet, artifact-only
worker_publication_row.json
worker_action.json              # only if action_request
live_create_summary.json
verify_create_summary.json
live_repair_summary.json        # only if repair dispatched
verify_repair_summary.json      # only if verifier ran
decision.json
```

No full graph dumps in LM6A v1.

No `--debug-full-graph` flag in LM6A v1.

No raw workflow contract dump if it could include hidden bind material.

## 17. Bounded Live Summaries

`live_create_summary.json`:

```text
node_id
tool_name
node_status
outcome_status
artifact_status
verified
receipt_status
repair_anchor.component_guid
repair_anchor.language
repair_anchor.target_errors bounded list/excerpts if present
receipt_sha256
```

`live_repair_summary.json`:

```text
same core shape as live_create_summary
params_sha256 from staged worker params
```

Verifier summaries:

```text
verifier_node_id
source_node_id
applied
outcome_status
unlocked_node_ids/statuses if already available without graph dump
```

Summary artifacts must not contain:

```text
PROBE_REPAIR_CODE
A = 42.0;
hidden bind/base params
full graph snapshots
unbounded raw model transcripts
```

## 18. Hidden Answer Leak Checks

LM6A must test and runtime-check that the following do not appear in the
contract variant, worker-visible request, decision record, or bounded artifacts:

```text
PROBE_REPAIR_CODE
A = 42.0;
hidden BindStepSpec.base_params.code
hand-authored repair diff sourced from hidden fixture/bind params
```

This leak check is about the hidden fixture/hand-authored answer, not about
worker-authored code in general. Legitimate worker-authored replacement code
such as `A = 0.0;` may appear only in ignored `worker_action.json`, with bounded
hashes/excerpts elsewhere.

If `A = 42.0;`, `PROBE_REPAIR_CODE`, or hidden
`BindStepSpec.base_params.code` appears in visible evidence, contract variant,
or bounded decision/summary artifacts, that is a bug/evidence leak, not model
success. If a worker independently authors the exact hidden answer, treat the
run as suspicious and inspect the ignored raw artifacts before citing it.

The only place exact worker code may be stored is the ignored
`worker_action.json` artifact after the worker has authored an action.

## 19. Tests

Deterministic test groups:

Worker-action applier:

- stages exact params on success
- copy-on-write graph behavior
- rejects unknown node
- rejects invalid action id
- rejects non-mapping action input
- rejects unexpected action input keys
- rejects missing/invalid code
- rejects invalid mode
- rejects non-mapping anchor binding
- rejects unexpected anchor binding keys
- rejects missing/invalid component guid
- rejects missing/invalid language
- never accepts worker-provided `guid` or `language`
- does not read or mention hidden bind params outside negative/static guards

Shared two-pass helper:

- fake `post_chat` success for clarification/action/refusal/observation
- fake provider errors map to row statuses
- pass-1 malformed JSON maps to decision invalid row status
- pass-2 malformed/LM5G-invalid maps to LM5G invalid row status
- invariant violations are detected
- observation-action anomaly scoring remains parsed-object only
- LM5R pass-1 instruction version and hash are unchanged
- LM5R status vocabulary is unchanged
- LM5R existing row/anomaly fields are preserved
- LM5R manifest and summary behavior are unchanged except for internal helper
  reuse

LM6A script:

- bind-free contract variant contains no `BindStepSpec` for
  `repair_same_component`
- node identities and live refs remain stable
- script-local routing artifact is statically valid and routability-valid with
  `worker_node_ids=("repair_same_component",)`
- Phase A gate maps failures to `gate_failed`
- publication failure maps to `publication_failed`
- non-action responses map to `worker_declined`
- observation anomaly maps to `worker_declined` with
  `worker_observation_action_intent_anomaly`
- applier rejection maps to `rejected`
- successful fake chain maps to `accepted`
- run artifacts are bounded and shaped as specified
- no full graph artifact is written
- no hidden repair answer appears in worker-visible request

## 20. Verification Scope

Implementation PR targeted tests should include:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  -q
```

Nearby seam tests should include the LM5/LM6 worker path:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_local_worker_acceptance_criteria.py `
  mcp_server\tests\test_local_worker_acceptance_criteria_sources.py `
  mcp_server\tests\test_local_worker_source_routing_validator.py `
  -q
```

Static:

```powershell
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\plan_graph_worker_action_apply.py `
  mcp_server\tests\test_plan_graph_worker_action_apply.py `
  scripts\lm_worker_two_pass_publication.py `
  scripts\lm6a_live_worker_splice_probe.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  mcp_server\tests\test_lm6a_live_worker_splice_probe.py

git diff --check main..HEAD
```

Confirm no diff in:

```text
production workflow templates
template selection
BindStepSpec semantics
plan_graph_param_apply.py
LM5G/LM5J parser/prompt modules
```

Confirm no `probe_runs/` artifacts are staged or committed.

## 21. Post-Merge Live Run

The implementation PR is deterministic only.

After merge, from synced `main`, run:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6a_live_worker_splice_probe.py `
  --phase receipt_recon
```

If recon passes, run:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm6a_live_worker_splice_probe.py
```

No Anthropic key is needed.

No curated evidence summary should be written until the live run artifacts are
reviewed.

## 22. Evidence Summary Follow-Up

After the post-merge live run, write a separate doc-only evidence summary PR.

The evidence summary should classify LM6A by terminal decision:

```text
accepted
  bounded worker reached live repair floor and verify_repair succeeded

rejected
  bounded worker reached action/apply/repair path but failed before acceptance

worker_declined
  bounded worker published a non-action decision

gate_failed
  receipt/routing/extraction gate failed before worker

publication_failed
  worker two-pass publication failed before trusted response payload
```

Do not include raw `probe_runs/` artifacts.

## 23. Success Criteria

LM6A implementation succeeds when:

```text
bind-free contract variant is deterministic and hidden-answer-free
worker-action applier is tested and fail-closed
LM5R two-pass behavior is preserved through the shared helper extraction
LM6A script can run Phase A and Phase B with fakes in deterministic tests
run artifacts are bounded and leak-checked
implementation PR contains no live artifacts
```

LM6A evidence succeeds with `accepted` only if:

```text
Phase A passes
worker publishes action_request
applier stages worker-authored params
live gh_update_script dispatches
verify_repair succeeds
hidden repair answer never leaks
```

If LM6A returns `rejected`, `worker_declined`, `gate_failed`, or
`publication_failed`, that is still useful arrival evidence. The terminal
decision should drive the next slice rather than being papered over by retries.
