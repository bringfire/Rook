# LM5T Repair-Intent Evidence v2 Design

## 1. Purpose

LM5T is a deterministic probe-fixture evidence slice.

LM5S closed the observation-action escape hatch in the LM5R two-pass probe and
improved absent-scenario restraint. It did not make evidence-present action
selection reliable:

```text
evidence_present_like:
  1/5 action_request
  3/5 clarification_request
  1/5 invalid action decision missing action_id
```

The useful read is not "Gemma is flaky." The worker is acting like a
requirements-elicitation machine: when the visible evidence does not establish
what repair it can responsibly author, it asks for more information.

LM5T asks one narrower question:

```text
Does honest, bounded repair-intent evidence change the worker's decision
behavior in the evidence-present condition?
```

LM5T does not try to prove semantic repair quality. If v2 evidence increases
`action_request` decisions but the authored action inputs remain weak, LM5T
still succeeds at testing decision movement. Repair-quality diagnostics are a
follow-up slice.

## 2. Design Line

LM5T publishes bounded, provenance-tagged repair-intent evidence from upstream
fixture facts, without exposing already-bound repair params or changing
prompt/publication mechanics.

The doctrine is:

```text
planner routes evidence
evidence packet publishes upstream facts
worker authors action input
```

The evidence packet is not allowed to invent new intent. Every v2 evidence
value must have a source path in one of:

```text
compiled workflow contract
derived graph state
producer/verifier receipt
graph memory facts
existing gotcha packet
```

## 3. Scope

LM5T may modify only:

```text
docs/superpowers/specs/2026-07-05-lm5t-repair-intent-evidence-v2-design.md
docs/superpowers/plans/2026-07-05-lm5t-repair-intent-evidence-v2.md
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

LM5T must not change:

```text
mcp_server/src/rook/**/*.py
LM5A/H/I context or request payload schemas
LM5G response loader/parser behavior
LM5J prompt artifact or adapter behavior
LM5S pass-one decision instruction
LM5R pass-two formatter prompt
LM5R publication status taxonomy
production transport behavior
```

LM5T does not add:

```text
typed evidence API
new production evidence schema
mechanical action-input diagnostics
semantic repair scoring
LLM judge
repair execution/verifier loop
curated evidence doc update during implementation
live probe run during the implementation PR
```

Raw probe artifacts remain ignored under `probe_runs/`.

## 4. Scenario Identity

LM5T adds a new evidence-present scenario instead of mutating the historical
LM5N evidence-present scenario.

LM5K probe config:

```text
evidence_present_v2:
  scenario_id = lm5t_repair_intent_evidence_present
  scenario_version = v4
  state = post_verify_pre_bind
  evidence_packet = repair_intent_v2
  expected disposition = candidate_action_request
  expected response kind = action_request
  expected action id = draft_repair_params
```

Existing scenarios remain:

```text
evidence_absent:
  gotcha only

evidence_present:
  LM5N v1 evidence packet
```

`_ProbeScenarioConfig` should use an explicit evidence packet selector instead
of boolean flags:

```python
evidence_packet: "none" | "repair_v1" | "repair_intent_v2"
```

Plain strings are acceptable in the script. A public type alias is unnecessary.

## 5. LM5R Selector

LM5T adds one LM5R scenario selector:

```text
evidence_present_v2_like -> evidence_present_v2
```

The existing selectors remain unchanged:

```text
evidence_absent_like
evidence_present_like
```

LM5R defaults remain historical:

```text
evidence_absent_like
evidence_present_like
```

The canonical LM5T runbook must pass scenarios explicitly:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v2_like `
  --attempts 5
```

The canonical run is local-only and uses the existing LM5R defaults:

```text
model = gemma4:12b-it-qat
direct Ollama /api/chat
pass 1 = free decision, think=true
pass 2 = single-kind constrained publication, think=false
```

No Anthropic key is required for the canonical LM5T run.

## 6. Upstream Fixture Enrichment

LM5T enriches the deterministic upstream create receipt before publishing v2
evidence.

The receipt currently says verification failed with one target error, but does
not expose the target diagnostic. LM5T adds a bounded, receipt-owned diagnostic:

```python
"target_errors": [
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
]
```

Diagnostic entries are strings, matching the existing production receipt shape
from `gh_script_receipts.py`.

LM5T must not introduce structured per-error objects such as:

```json
{"code": "CS0103", "message": "...", "symbol": "..."}
```

`target_warnings` remains absent unless the upstream receipt explicitly carries
warnings.

This enrichment is honest because the fixture already records:

```text
verification.status = failed
verification.target_error_count = 1
```

LM5T makes the single target error inspectable without leaking the desired
replacement.

## 7. Evidence Packet Builders

LM5T keeps the LM5N evidence builder and adds a new v2 builder beside it:

```python
_repair_evidence_packet(...)          # LM5N v1, stable
_repair_intent_evidence_packet(...)   # LM5T v2
```

Scenario routing:

```text
evidence_absent      -> gotcha only
evidence_present     -> gotcha + LM5N v1 packet
evidence_present_v2  -> gotcha + LM5T v2 packet
```

The v2 packet identity is:

```text
packet_id = lm5t_repair_intent_evidence
kind = evidence
```

The v1 packet must remain stable. Because LM5T adds `target_errors` upstream to
`repair_anchor`, v1 must not copy the whole repair anchor mapping anymore. Its
`repair_anchor.value` should be narrowed to the historical stable fields:

```json
{
  "component_guid": "<PROBE_COMPONENT_GUID>",
  "language": "csharp"
}
```

That prevents the new upstream diagnostic from leaking into the LM5N baseline.

The v2 packet must use the same stable `repair_anchor.value` shape. Target
diagnostics may appear only under `target_diagnostics.fields`, where they are
bounded and provenance-wrapped. They must not appear through the top-level
`repair_anchor.value` copy.

## 8. v2 Evidence Shape

The LM5T packet publishes these fields:

```text
current_code
recommended_mode
language
component_guid
repair_anchor

pin_contract:
  pins_in
  pins_out

current_verification:
  status
  target_error_count
  target_warning_count, only if present

target_diagnostics:
  source
  fields:
    target_errors, only if upstream has it
    target_warnings, only if upstream has it

expected_repair_outcome:
  value = succeeded
  source = workflow_contract.rules.verify_repair.expected_outcome
```

The packet must explicitly exclude:

```text
expected_target_error_count
PROBE_REPAIR_CODE
A = 42.0;
hidden BindStepSpec.base_params.code
already-bound repair params
repair diff
desired replacement code
```

The `repair_anchor` evidence field is intentionally a stable anchor identity
copy, not a full receipt dump:

```json
{
  "component_guid": "<PROBE_COMPONENT_GUID>",
  "language": "csharp"
}
```

`target_errors` and `target_warnings` must not appear inside
`repair_anchor.value`. They may appear only under `target_diagnostics.fields`.

`target_diagnostics` remains present for stable shape, but absent optional
diagnostic fields are omitted from `target_diagnostics.fields`.

Example diagnostic wrapper:

```json
{
  "target_diagnostics": {
    "source": "create_script.receipt.script_receipt.repair_anchor",
    "fields": {
      "target_errors": {
        "value": [
          "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context."
        ],
        "source": "create_script.receipt.script_receipt.repair_anchor.target_errors",
        "max_items": 3,
        "max_chars_per_item": 300,
        "truncated": false
      }
    }
  }
}
```

Bounds:

```text
target diagnostic max items = 3
target diagnostic max chars per item = 300
current_code max chars remains the existing evidence current-code cap
```

If truncation occurs, the wrapper records `truncated = true`.

## 9. Expected Outcome Source

`expected_repair_outcome` comes from the compiled workflow contract's
`verify_repair` verifier rule:

```text
workflow_contract.rules.verify_repair.expected_outcome = succeeded
```

LM5T does not add `expected_target_error_count`.

If a future slice wants expected target-error count as worker evidence, it must
first model that as verifier intent. LM5T should not smuggle it into evidence
packet prose.

## 10. Deterministic Tests

LM5T tests should prove identity, visibility, and stability:

```text
evidence_present v1 scenario_id/version remain unchanged
evidence_present_v2 scenario_id = lm5t_repair_intent_evidence_present
evidence_present_v2 scenario_version = v4
evidence_present_v2 packet_id = lm5t_repair_intent_evidence
```

Visibility guards:

```text
evidence_present v1 does not expose target_errors
evidence_present_v2 exposes target_errors
evidence_present_v2 still does not expose PROBE_REPAIR_CODE
```

v1 stability guard:

```python
v1_repair_anchor_value == {
    "component_guid": PROBE_COMPONENT_GUID,
    "language": "csharp",
}
```

v2 diagnostic guards:

```text
target_diagnostics.fields.target_errors.value contains DefinitelyMissingSymbol
target_diagnostics.fields does not contain target_warnings unless upstream has it
target_errors entries are strings
target_errors wrapper includes source, max_items, max_chars_per_item, truncated
v2 repair_anchor.value contains only component_guid and language
v2 repair_anchor.value does not contain target_errors or target_warnings
```

LM5R selector guards:

```text
evidence_present_v2_like is accepted
evidence_present_v2_like maps to evidence_present_v2
LM5R defaults remain evidence_absent_like + evidence_present_like
```

Scope guards:

```text
no mcp_server/src changes
no LM5R pass-one instruction change
no LM5R pass-two formatter change
no LM5G parser/loader change
no prompt artifact change
```

## 11. Verification Scope

Targeted:

```text
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

Nearby:

```text
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5p_ollama_think_format_spike.py
```

Static:

```text
git diff --check
production diff limited to scripts/lm5k_worker_probe.py and scripts/lm5r_two_pass_publication_probe.py
test diff limited to the LM5K/LM5R probe tests
spec/plan docs only in docs/superpowers
no probe_runs artifacts
```

No live/model run in the implementation PR.

## 12. Post-Merge Runbook

After the deterministic PR lands, sync `main` and run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v2_like `
  --attempts 5
```

Report:

```text
run_dir
commit
instruction version/hash
status counts by scenario
pass1/pass2 kind distributions
published count
LM5G-loadable count
observation anomaly counts
representative bounded action inputs if any
whether PROBE_REPAIR_CODE appears anywhere in visible evidence or raw outputs
```

Do not commit raw `probe_runs/`.

If the run is clean, write a later doc-only curated evidence summary.

## 13. Interpretation

Expected reads:

```text
absent clarifies/refuses
  restraint preserved

present_v2 action_requests increase
  repair-intent evidence helps decision movement

present_v2 still clarifies
  evidence is still insufficient or too indirect

present_v2 copies failing code
  action rate improved but repair quality remains weak

present_v2 uses PROBE_REPAIR_CODE / A = 42.0;
  bug or evidence leak, not model success
```

LM5T success is not "Gemma repairs correctly." LM5T success is a clean,
provenance-preserving comparison of absent control versus repair-intent evidence
v2.

## 14. Anti-Goals

LM5T must not:

```text
publish PROBE_REPAIR_CODE
publish already-bound repair params
rewrite prompt text
change two-pass publication mechanics
add action-input diagnostics
score semantic repair quality
execute proposed repairs
call cloud models in the canonical run
introduce typed evidence API
change LM5A/H/I/G/J production surfaces
```

Mechanical action-input diagnostics are deferred to LM5U unless they are
separately scoped and approved.
