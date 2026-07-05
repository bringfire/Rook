# LM5U Acceptance-Criteria Evidence v3 Design

## 1. Purpose

LM5U is a deterministic probe-fixture evidence slice.

LM5T was a discriminating experiment, not a failure. It eliminated this
hypothesis under clean controls:

```text
diagnostic visibility alone is sufficient
```

LM5T published the current failing code, the body-mode convention, the pin
contract, the expected repair outcome, and the bounded target diagnostic:

```text
CS0103: The name 'DefinitelyMissingSymbol' does not exist in the current context.
```

The worker still clarified 5/5 in `evidence_present_v2_like`, asking what value
or behavior should replace the missing symbol. That is useful signal. The worker
is no longer asking "what is going on?" It is asking for the missing semantic
value or behavior.

LM5U asks one narrower question:

```text
Does worker-visible acceptance-criteria evidence move evidence_present_v3_like
from clarification to action?
```

LM5U does not try to prove semantic repair quality. It only tests decision
movement under a stronger, checkable contract surface.

## 2. Design Line

LM5U publishes checkable acceptance criteria derived from workflow and scaffold
facts, without exposing already-bound repair params or desired replacement code.

The doctrine is:

```text
Workers act on checkable acceptance criteria, not answers.
```

The acceptance criteria are acceptance criteria, not the answer. They can tell
the worker what a valid repair must satisfy:

```text
the output pin A must be assigned
the output pin A must be double-compatible
the repair must satisfy verify_repair expected_outcome succeeded
the repair must preserve body-style code
the repair must resolve the current target diagnostics
the repair must not leave DefinitelyMissingSymbol unresolved
```

They must not tell the worker what concrete replacement expression to use.

## 3. Scope

LM5U may modify only:

```text
docs/superpowers/specs/2026-07-05-lm5u-acceptance-criteria-evidence-v3-design.md
docs/superpowers/plans/2026-07-05-lm5u-acceptance-criteria-evidence-v3.md
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

LM5U must not change:

```text
mcp_server/src/rook/**/*.py
LM5A/H/I context or request payload schemas
LM5G response loader/parser behavior
LM5J prompt artifact or adapter behavior
LM5S pass-one decision instruction
LM5R pass-two formatter prompt
LM5R publication status taxonomy
LM5R single-kind publication schemas
production transport behavior
```

LM5U does not add:

```text
typed evidence API
new production evidence schema
mechanical action-input diagnostics
semantic repair scoring
code execution
repair verifier loop
LLM judge
curated evidence doc update during implementation
live probe run during the implementation PR
```

Raw probe artifacts remain ignored under `probe_runs/`.

## 4. Evidence Ladder

LM5U preserves the historical evidence ladder:

```text
v1 = repair context
v2 = repair diagnostics
v3 = repair acceptance criteria
```

The builders remain separate:

```python
_repair_evidence_packet(...)                 # LM5N v1, unchanged
_repair_intent_evidence_packet(...)          # LM5T v2, unchanged
_acceptance_criteria_evidence_packet(...)    # LM5U v3
```

Scenario routing is:

```text
evidence_absent      -> gotcha only
evidence_present     -> gotcha + repair_v1
evidence_present_v2  -> gotcha + repair_intent_v2
evidence_present_v3  -> gotcha + acceptance_criteria_v3
```

LM5U must not rewrite v1 or v2 evidence under the same scenario identity.

## 5. Scenario Identity

LM5U adds one new evidence-present scenario:

```text
evidence_present_v3:
  scenario_id = lm5u_acceptance_criteria_evidence_present
  scenario_version = v5
  state = post_verify_pre_bind
  evidence_packet = acceptance_criteria_v3
  expected disposition = candidate_action_request
  expected response kind = action_request
  expected action id = draft_repair_params
```

The evidence packet id is:

```text
lm5u_acceptance_criteria_evidence
```

Existing scenario identities remain unchanged:

```text
evidence_absent
evidence_present
evidence_present_v2
```

`_ProbeScenarioConfig` should continue to use an explicit evidence packet
selector string. The accepted values become:

```text
none
repair_v1
repair_intent_v2
acceptance_criteria_v3
```

No public type alias is required in the probe script.

## 6. LM5R Selector

LM5U adds one LM5R selector:

```text
evidence_present_v3_like -> evidence_present_v3
```

Existing selectors remain available:

```text
evidence_absent_like
evidence_present_like
evidence_present_v2_like
```

LM5R defaults remain historical:

```text
evidence_absent_like
evidence_present_like
```

The canonical LM5U live run must pass scenarios explicitly after merge:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v3_like `
  --attempts 5
```

The canonical run is local-only and uses the existing LM5R defaults:

```text
model = gemma4:12b-it-qat
direct Ollama /api/chat
pass 1 = free decision, think=true
pass 2 = single-kind constrained publication, think=false
```

No Anthropic key is required for the canonical LM5U run.

## 7. V3 Packet Field Set

The v3 packet is v2 evidence plus a checkable acceptance-criteria layer. It
keeps the facts that got the worker to a rational clarification and adds the
criteria needed to test whether those facts are enough to act.

The v3 packet content fields are:

```text
current_code
language
recommended_mode
repair_anchor
pin_contract
target_diagnostics
expected_repair_outcome
acceptance_criteria
```

Hard exclusions:

```text
0
42.0
A = 42.0;
PROBE_REPAIR_CODE
set A to ...
replacement code
repair diff
already-bound repair params
hidden BindStepSpec.base_params.code
```

The ban on `0` and `42.0` means those values must not appear as suggested
replacement literals. It does not ban unrelated numeric metadata if a future
fixture legitimately owns it, but LM5U should not add such metadata.

## 8. V3 Fact Fields

`current_code` is copied from the same visible source as v2:

```text
create_script.initial_execution_params.code
```

It contains the current failing body, not the repair body.

`language` is copied from the receipt:

```text
create_script.receipt.script_receipt.language
```

`recommended_mode` is copied from the existing gotcha/convention source:

```text
script_body_gotcha
```

`repair_anchor.value` is stable identity only:

```python
{
    "component_guid": PROBE_COMPONENT_GUID,
    "language": "csharp",
}
```

`repair_anchor.value` must not contain:

```text
target_errors
target_warnings
acceptance_criteria
replacement code
```

`pin_contract` includes the output pin contract and explicit output
requirements:

```python
"pin_contract": {
    "value": {
        "pins_out": ["A:double"],
        "output_requirements": [
            {
                "requirement_id": "output_a_assigned",
                "description": "Output A must be assigned.",
                "source": "create_script.initial_execution_params.pins_out",
            },
            {
                "requirement_id": "output_a_double_compatible",
                "description": "Output A must be double-compatible.",
                "source": "create_script.initial_execution_params.pins_out",
            },
        ],
    },
    "source": "create_script.initial_execution_params.pins_out",
}
```

The output requirements are contract-derived from `pins_out = ["A:double"]`.
They are not prompt-invented repair hints.

`expected_repair_outcome` remains a sourced fact:

```python
"expected_repair_outcome": {
    "value": "succeeded",
    "source": "workflow_contract.rules.verify_repair.expected_outcome",
}
```

`target_diagnostics` carries bounded receipt-derived diagnostics:

```python
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
            "truncated": False,
        }
    },
}
```

`target_warnings` remains absent unless the upstream receipt explicitly carries
warnings. The evidence packet must not fabricate an empty warnings list when no
upstream source exists.

## 9. Acceptance Criteria Shape

`acceptance_criteria` is structured, deterministic, and provenance-tagged. It is
not a free-form prompt paragraph.

Exact shape:

```python
"acceptance_criteria": {
    "source": (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
    ),
    "criteria": [
        {
            "criterion_id": "output_a_assigned",
            "description": "Output A must be assigned.",
            "source": "create_script.initial_execution_params.pins_out",
        },
        {
            "criterion_id": "output_a_double_compatible",
            "description": "Output A must be double-compatible.",
            "source": "create_script.initial_execution_params.pins_out",
        },
        {
            "criterion_id": "verify_repair_succeeds",
            "description": (
                "The repaired body must satisfy the verify_repair expected_outcome: "
                "succeeded."
            ),
            "source": "workflow_contract.rules.verify_repair.expected_outcome",
        },
        {
            "criterion_id": "preserve_body_mode",
            "description": "The repair must preserve body-style code.",
            "source": "script_body_gotcha",
        },
        {
            "criterion_id": "resolve_target_diagnostics",
            "description": "The repair must resolve the current target diagnostics.",
            "source": "create_script.receipt.script_receipt.repair_anchor.target_errors",
        },
        {
            "criterion_id": "remove_unresolved_symbol",
            "description": (
                "The repaired body must not leave DefinitelyMissingSymbol unresolved."
            ),
            "source": "create_script.receipt.script_receipt.repair_anchor.target_errors",
        },
    ],
}
```

Pins:

```text
criteria is a list
criteria order is deterministic
criterion_id values are stable
every criterion has criterion_id, description, source
criteria may mention DefinitelyMissingSymbol because it is receipt-derived
criteria must not mention replacement literals
criteria must not mention PROBE_REPAIR_CODE
criteria must not mention A = 42.0;
```

The expected outcome appears twice intentionally:

```text
expected_repair_outcome = sourced fact
acceptance_criteria.verify_repair_succeeds = derived worker-facing criterion
```

## 10. Deterministic Tests

LM5U tests should prove identity, visibility, stability, and non-leakage.

Scenario identity:

```text
evidence_present_v3 scenario_id = lm5u_acceptance_criteria_evidence_present
evidence_present_v3 scenario_version = v5
evidence_present_v3 packet_id = lm5u_acceptance_criteria_evidence
```

Evidence ladder:

```text
v1:
  no target_errors
  no acceptance criteria

v2:
  target_errors visible
  no acceptance criteria

v3:
  target_errors visible
  acceptance criteria visible
```

Shared non-leakage:

```text
v1/v2/v3 do not expose PROBE_REPAIR_CODE
v1/v2/v3 do not expose A = 42.0;
v1/v2/v3 do not expose hidden BindStepSpec.base_params.code
```

v3 field tests:

```text
v3 fields are exactly:
  current_code
  language
  recommended_mode
  repair_anchor
  pin_contract
  target_diagnostics
  expected_repair_outcome
  acceptance_criteria

v3 repair_anchor.value contains only component_guid and language
v3 target_diagnostics.fields.target_errors contains DefinitelyMissingSymbol
v3 target_diagnostics.fields does not contain target_warnings unless upstream has it
v3 pin_contract.value.pins_out == ["A:double"]
v3 pin_contract.value.output_requirements are deterministic and sourced from pins_out
v3 expected_repair_outcome.value == "succeeded"
v3 acceptance_criteria.criteria criterion ids match the locked list and order
```

LM5R selector guards:

```text
evidence_present_v3_like is accepted
evidence_present_v3_like maps to evidence_present_v3
LM5R defaults remain evidence_absent_like + evidence_present_like
```

Boundary guards:

```text
no mcp_server/src changes
no LM5R pass-one instruction change
no LM5R pass-two formatter change
no LM5R status taxonomy change
no LM5R single-kind schema change
no LM5G parser/loader change
no prompt artifact change
no probe_runs artifacts
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
no mcp_server/src diff
no prompt instruction diff
no pass-two formatter/status/schema diff
no probe_runs artifacts
```

No live/model run in the implementation PR.

## 12. Post-Merge Runbook

After the deterministic PR lands, sync `main` and run:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v3_like `
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
whether A = 42.0 appears anywhere in visible evidence or raw outputs
```

Do not commit raw `probe_runs/`.

If the run is clean, write a later doc-only curated evidence summary.

## 13. Interpretation

Expected reads:

```text
absent clarifies/refuses
  restraint preserved

present_v3 action_requests increase
  worker has enough acceptance criteria to attempt
  next slice can inspect action quality

present_v3 still clarifies
  worker is rationally deferring
  next slice is clarify/resupply or upstream functional-intent modeling

present_v3 leaks A = 42.0 / PROBE_REPAIR_CODE
  implementation bug or evidence leak, not model success
```

Stop condition:

```text
If evidence_present_v3_like still produces clean clarification without leakage,
LM5U closes the evidence-push ladder for this fixture. Do not keep adding
worker-visible evidence packets in this line. The next design must move upstream
to functional-intent modeling or outward to a clarify/resupply loop.
```

LM5U success is not "Gemma repairs correctly." LM5U success is a clean,
provenance-preserving discriminator between:

```text
acceptance criteria are sufficient to attempt
acceptance criteria still leave functional intent underdetermined
```

## 14. Anti-Goals

LM5U must not:

```text
publish PROBE_REPAIR_CODE
publish A = 42.0;
publish already-bound repair params
publish replacement literals
publish repair diffs
rewrite prompt text
change two-pass publication mechanics
add action-input diagnostics
score semantic repair quality
execute proposed repairs
call cloud models in the canonical run
introduce typed evidence API
change LM5A/H/I/G/J production surfaces
change LM5R pass-one/pass-two instructions
change LM5R status taxonomy or schemas
```

Mechanical action-input diagnostics, semantic repair quality, execution, and
clarify/resupply loops are explicitly deferred unless a later slice scopes them
separately.
