# LM8D Scalar Action Affordance Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicit scalar action-selection contract to the LM8C worker-visible packet so the worker can see the required scalar action handle without changing publication validation or runtime semantics.

**Architecture:** LM8D is a local LM8C packet-shape refinement. It changes only `scripts/lm8c_gh_scalar_expectation_live_probe.py` and its focused tests, leaving LM8B extraction/assembly/applier, the shared two-pass publication helper, worker response validation, live scalar fixture creation, and verifier behavior unchanged. The harness must still reject a malformed `{"kind": "action_request"}` pass-1 response with missing `action_id`; no autofill path is allowed.

**Tech Stack:** Python 3.10, pytest, existing LM8C script-local helpers, existing `WorkerKnowledgePacket` / `WorkerAllowedAction` context rendering, existing `run_two_pass_worker_publication(...)`.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-08-lm8d-scalar-action-affordance-clarity-design.md`.
- Change only scalar worker-visible packet/request surface.
- No shared two-pass publication helper changes.
- No shared repair-worker prompt or protocol changes.
- No action id autofill.
- No "only one action, so infer it" behavior.
- No retry.
- No N=5.
- No `gh_edit`.
- No topology, wiring, code, script repair, or batch edit affordance.
- No scalar runtime readiness changes.
- No verifier changes.
- No Planner model.
- No live run in the implementation PR.
- Post-merge evidence is exactly one canonical LM8C live attempt from synced `main`.

---

## File Structure

- Modify: `scripts/lm8c_gh_scalar_expectation_live_probe.py`
  - Add a small script-local `_scalar_action_selection_contract()` helper.
  - Include that contract in `_scalar_worker_evidence_packet(...).content["fields"]`.
  - Do not modify `_scalar_allowed_action()`, `_decision_from_publication(...)`, `_run_probe(...)`, or shared publication imports.
- Modify: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`
  - Add tests for the new packet field and exact pass-1/final field split.
  - Strengthen the worker request test to assert no raw GUID or forbidden affordance drift.
  - Add or strengthen a publication-failure test proving missing `action_id` remains `publication_failed`, not inferred.
- No new production module.
- No new script.
- No docs beyond this implementation plan.

---

### Task 1: Add Scalar Action-Selection Contract To LM8C Worker Evidence

**Files:**
- Modify: `scripts/lm8c_gh_scalar_expectation_live_probe.py`
- Modify: `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`

**Interfaces:**
- Consumes:
  - `ACTION_ID = "draft_gh_set_value_params"`
  - existing `_scalar_allowed_action() -> WorkerAllowedAction`
  - existing `_scalar_worker_evidence_packet(packet, worker_visible) -> WorkerKnowledgePacket`
  - existing `_build_local_turn_payload(graph, packet, worker_visible) -> dict[str, Any]`
- Produces:
  - `_scalar_action_selection_contract() -> dict[str, Any]`
  - worker knowledge field `action_selection_contract`

- [ ] **Step 1: Write failing tests for the action-selection contract helper and rendered packet**

Add these tests near `test_worker_request_uses_scalar_knowledge_and_never_exposes_raw_guid` in `mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py`:

```python
def test_scalar_action_selection_contract_preserves_two_pass_shapes() -> None:
    contract = PROBE._scalar_action_selection_contract()

    assert contract == {
        "contract_id": "gh_scalar_action_selection:v1",
        "worker_agency": (
            "If the acceptance criteria are sufficient and action is warranted, "
            "publish action_request with the exact required_action_id. If action "
            "is not warranted, publish a non-action response."
        ),
        "required_response_kind_if_acting": "action_request",
        "required_action_id": "draft_gh_set_value_params",
        "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
        "final_action_request_required_fields": [
            "schema",
            "kind",
            "action_id",
            "rationale",
            "input",
        ],
        "action_input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
        "authority_limits": [
            "do not author target GUID",
            "do not call GH tools directly",
            "do not author topology, code, or batch edits",
        ],
    }
    assert "you must act" not in contract["worker_agency"].casefold()
    assert "input" not in contract["pass1_decision_required_fields_if_acting"]
```

Add this test after the existing worker request payload test:

```python
def test_worker_request_includes_action_selection_contract_without_autofill_hint() -> None:
    fixture = _valid_fixture()
    graph = PROBE._graph_from_scalar_receipt(fixture["receipt"])
    runtime = PROBE._scalar_runtime_context(
        graph=graph,
        workflow_contract_payload=PROBE._scalar_contract_payload(),
        convention_packets=(),
    )

    payload = PROBE._build_local_turn_payload(
        graph=graph,
        packet=runtime["packet"],
        worker_visible=runtime["worker_visible"],
    )

    packet = payload["context"]["knowledge"][0]
    fields = packet["content"]["fields"]
    contract = fields["action_selection_contract"]
    rendered = json.dumps(payload, sort_keys=True)

    assert contract["required_action_id"] == "draft_gh_set_value_params"
    assert contract["pass1_decision_required_fields_if_acting"] == [
        "kind",
        "action_id",
    ]
    assert contract["final_action_request_required_fields"] == [
        "schema",
        "kind",
        "action_id",
        "rationale",
        "input",
    ]
    assert contract["action_input_schema"]["required"] == ["value"]
    assert contract["action_input_schema"]["additionalProperties"] is False
    assert "SLIDER-GUID-1" not in rendered
    assert "only one action" not in rendered
    assert "infer" not in rendered.casefold()
    assert "autofill" not in rendered.casefold()
```

- [ ] **Step 2: Run the focused failing tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py::test_scalar_action_selection_contract_preserves_two_pass_shapes `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py::test_worker_request_includes_action_selection_contract_without_autofill_hint `
  -q
```

Expected: both fail because `_scalar_action_selection_contract` does not exist and the worker packet lacks `action_selection_contract`.

- [ ] **Step 3: Implement the minimal script-local contract helper**

Add this helper near `_scalar_worker_evidence_packet(...)` in `scripts/lm8c_gh_scalar_expectation_live_probe.py`:

```python
def _scalar_action_selection_contract() -> dict[str, Any]:
    return {
        "contract_id": "gh_scalar_action_selection:v1",
        "worker_agency": (
            "If the acceptance criteria are sufficient and action is warranted, "
            "publish action_request with the exact required_action_id. If action "
            "is not warranted, publish a non-action response."
        ),
        "required_response_kind_if_acting": "action_request",
        "required_action_id": ACTION_ID,
        "pass1_decision_required_fields_if_acting": ["kind", "action_id"],
        "final_action_request_required_fields": [
            "schema",
            "kind",
            "action_id",
            "rationale",
            "input",
        ],
        "action_input_schema": {
            "type": "object",
            "required": ["value"],
            "properties": {"value": {"type": "number"}},
            "additionalProperties": False,
        },
        "authority_limits": [
            "do not author target GUID",
            "do not call GH tools directly",
            "do not author topology, code, or batch edits",
        ],
    }
```

Then update `_scalar_worker_evidence_packet(...)` by adding one field:

```python
"action_selection_contract": _scalar_action_selection_contract(),
```

The field should live beside `recommended_action_id`:

```python
"fields": {
    "current_observed_output": fields["current_observed_output"],
    "expected_output_value": fields["expected_output_value"],
    "editable_value_contract": editable,
    "acceptance_criteria": dict(worker_visible),
    "recommended_action_id": ACTION_ID,
    "action_selection_contract": _scalar_action_selection_contract(),
},
```

Do not modify `_scalar_allowed_action()`. The existing allowed action remains the canonical machine-readable action list.

- [ ] **Step 4: Run the focused tests again**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py::test_scalar_action_selection_contract_preserves_two_pass_shapes `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py::test_worker_request_includes_action_selection_contract_without_autofill_hint `
  -q
```

Expected: both pass.

- [ ] **Step 5: Strengthen the existing worker request guard**

In `test_worker_request_uses_scalar_knowledge_and_never_exposes_raw_guid`, add these assertions after the existing action id assertions:

```python
    assert "action_selection_contract" in rendered
    assert "pass1_decision_required_fields_if_acting" in rendered
    assert "final_action_request_required_fields" in rendered
    assert "do not author target GUID" in rendered
    assert "do not call GH tools directly" in rendered
    assert "do not author topology, code, or batch edits" in rendered
```

Keep the existing forbidden strings:

```python
    assert "SLIDER-GUID-1" not in rendered
    assert "gh_edit" not in rendered
    assert "gh_update_script" not in rendered
    assert "repair_same_component" not in rendered
```

- [ ] **Step 6: Add an explicit no-autofill publication regression**

Add this test near `test_publication_failure_maps_to_publication_failed`:

```python
def test_missing_pass1_action_id_stays_publication_failed() -> None:
    decision = PROBE._decision_from_publication(
        {
            "status": "pass1_decision_invalid",
            "failure_reason": "pass1_missing_action_id",
            "pass1_content_excerpt": '{"kind": "action_request"}',
        },
        None,
    )

    assert decision == {
        "decision": "publication_failed",
        "reason": "pass1_decision_invalid:pass1_missing_action_id",
        "phase": "worker_publication",
    }
```

This pins that LM8D does not infer `draft_gh_set_value_params` even though the request contains exactly one allowed action.

- [ ] **Step 7: Run the full LM8C focused file**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  -q
```

Expected: all LM8C tests pass.

- [ ] **Step 8: Commit Task 1**

Run:

```powershell
git add `
  scripts\lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py

git commit -m "feat: clarify LM8C scalar action affordance"
```

---

### Task 2: Verify Scope, Drift Guards, And Nearby Worker Seams

**Files:**
- Test only; no source edits expected.

**Interfaces:**
- Consumes:
  - Task 1 `_scalar_action_selection_contract()`
  - unchanged LM8B source/criteria/applier modules
  - unchanged `lm_worker_two_pass_publication.py`
- Produces:
  - verified deterministic gate before PR

- [ ] **Step 1: Run the LM8D focused verification gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_gh_scalar_expectation_acceptance_criteria.py `
  mcp_server\tests\test_gh_scalar_expectation_sources.py `
  mcp_server\tests\test_plan_graph_gh_scalar_action_apply.py `
  mcp_server\tests\test_lm_worker_two_pass_publication.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run Python 3.10 compile check**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm8c_gh_scalar_expectation_live_probe.py `
  mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Check diff whitespace**

Run:

```powershell
git diff --check main..HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 4: Check exact implementation diff scope**

Run:

```powershell
git diff --name-only main..HEAD
```

Expected tracked files:

```text
docs/superpowers/plans/2026-07-08-lm8d-scalar-action-affordance-clarity.md
docs/superpowers/specs/2026-07-08-lm8d-scalar-action-affordance-clarity-design.md
mcp_server/tests/test_lm8c_gh_scalar_expectation_live_probe.py
scripts/lm8c_gh_scalar_expectation_live_probe.py
```

Do not stage or revert unrelated local files such as:

```text
knowledge/gh/operations_knowledge.json
.understand-anything/
docs/superpowers/plans/2026-07-04-rook2-minimal-base-roadmap.md
docs/superpowers/probes/2026-07-04-rook20-v01-hermes-plugin-validation.md
docs/superpowers/specs/2026-07-03-rook-2.0-minimal-iteration-design.md
```

- [ ] **Step 5: Check raw source for disallowed drift**

Run:

```powershell
Select-String -Path scripts\lm8c_gh_scalar_expectation_live_probe.py `
  -SimpleMatch `
  -Pattern "_worker_request_payload","lm6a_live_worker_splice_probe","lm7e_model_authored_live_splice_probe","gh_update_script","repair_same_component","retry_clean_observation","gh_edit("
```

Expected: no matches. The string `gh_edit_enabled` may appear in the manifest and is allowed; do not use a raw ban for plain `gh_edit`.

Also verify the policy strings remain only scalar affordance / guard data:

```powershell
Select-String -Path scripts\lm8c_gh_scalar_expectation_live_probe.py `
  -Pattern "PROBE_REPAIR_CODE","A = 42.0","BindStepSpec.base_params"
```

Expected: matches only inside `_hidden_marker_leaks(...)` policy data.

- [ ] **Step 6: Commit Task 2 only if verification docs or tests changed**

If Task 2 required no edits, do not create an empty commit. If a test adjustment was needed, commit only that adjustment:

```powershell
git add mcp_server\tests\test_lm8c_gh_scalar_expectation_live_probe.py
git commit -m "test: guard LM8D scalar affordance drift"
```

---

## Post-Merge Runbook

No live run belongs in the implementation PR.

After PR merge and sync to `main`, run exactly one canonical live LM8C attempt:

```powershell
.\mcp_server\.venv\Scripts\python.exe scripts\lm8c_gh_scalar_expectation_live_probe.py
```

Inspect:

```powershell
$run = "C:\UDEV\Rook\probe_runs\<printed-run-dir-name>"

Get-Content "$run\decision.json"
Get-Content "$run\worker_publication_row.json" -ErrorAction SilentlyContinue
Get-Content "$run\worker_action.json" -ErrorAction SilentlyContinue
Get-Content "$run\live_set_value_summary.json" -ErrorAction SilentlyContinue
Get-Content "$run\verify_scalar_output_summary.json" -ErrorAction SilentlyContinue

Select-String -Path "$run\scalar_sources.json","$run\acceptance_criteria_packet.json","$run\worker_visible_acceptance_criteria.json","$run\worker_request_payload.json","$run\verify_scalar_output_summary.json","$run\decision.json" `
  -Pattern "PROBE_REPAIR_CODE","A = 42.0","BindStepSpec.base_params.code","gh_update_script","repair_same_component"
```

Expected interpretation:

- `publication_failed / pass1_missing_action_id`: LM8D did not repair scalar action-handle publication.
- pass 2 reached or action apply reached: LM8D advanced the boundary.
- `accepted / verify_scalar_output_succeeded`: first scalar-family live arrival.

Do not replace the attempt. Do not run N=5. Do not enable retry.

---

## Self-Review Notes

- Spec coverage: plan implements only the scalar packet affordance and preserves no-autofill / no shared-helper-change rules.
- Scope: single implementation slice; no decomposition needed.
- Type consistency: `_scalar_action_selection_contract() -> dict[str, Any]` is script-local and consumed only by `_scalar_worker_evidence_packet(...)`.
- Live work: explicitly excluded from implementation PR and deferred to post-merge runbook.
