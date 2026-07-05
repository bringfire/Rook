# LM5U Acceptance-Criteria Evidence v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic probe-only `evidence_present_v3` scenario that publishes acceptance-criteria evidence without leaking hidden repair output.

**Architecture:** Extend the existing LM5K probe scenario table with a new evidence packet selector and builder, then expose it to the LM5R two-pass probe through a new explicit selector. Keep v1/v2 evidence and LM5R publication mechanics stable; LM5U only adds v3 worker-visible evidence and tests.

**Tech Stack:** Python 3.10, pytest, existing LM5K/LM5R probe scripts, existing frozen `WorkerKnowledgePacket` normalization.

---

## File Structure

Modify only:

```text
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

Docs already created:

```text
docs/superpowers/specs/2026-07-05-lm5u-acceptance-criteria-evidence-v3-design.md
docs/superpowers/plans/2026-07-05-lm5u-acceptance-criteria-evidence-v3.md
```

No production `mcp_server/src` files may change.

Important existing behavior:

- `WorkerKnowledgePacket` freezes nested JSON-shaped values; lists in builder code may appear as tuples when inspecting `packet.content` directly in tests.
- v1/v2 evidence tests must continue to pass unchanged unless a task explicitly updates expectations for newly added constants/scenario sets.
- LM5R defaults must remain `("evidence_absent_like", "evidence_present_like")`.

---

### Task 1: Add LM5U Scenario Identity

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`
- Test: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Write the failing scenario identity test**

In `mcp_server/tests/test_lm5k_worker_probe.py`, update `test_scenario_configs_are_source_of_truth` so the scenario set includes `evidence_present_v3`, then add assertions for the new config immediately after the `present_v2` assertions:

```python
    assert set(PROBE._SCENARIOS) == {
        "evidence_absent",
        "evidence_present",
        "evidence_present_v2",
        "evidence_present_v3",
    }
```

```python
    present_v3 = PROBE._SCENARIOS["evidence_present_v3"]
    assert present_v3.cli_name == "evidence_present_v3"
    assert (
        present_v3.scenario_id
        == "lm5u_acceptance_criteria_evidence_present"
    )
    assert present_v3.scenario_version == "v5"
    assert present_v3.state == "post_verify_pre_bind"
    assert present_v3.evidence_packet == "acceptance_criteria_v3"
    assert present_v3.expected_disposition == "candidate_action_request"
    assert present_v3.expected_response_kind == "action_request"
    assert present_v3.expected_action_id == "draft_repair_params"
    assert present_v3.expected_attempt_valid is True
```

Also update the legacy scenario-id negative assertion:

```python
    assert "lm5k_golden_repair_v2" not in {
        absent.scenario_id,
        present.scenario_id,
        present_v2.scenario_id,
        present_v3.scenario_id,
    }
```

- [ ] **Step 2: Run the new identity test and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_scenario_configs_are_source_of_truth `
  -q
```

Expected: fail with a missing `evidence_present_v3` key or scenario-set mismatch.

- [ ] **Step 3: Add the scenario config and packet id constant**

In `scripts/lm5k_worker_probe.py`, add this scenario after `evidence_present_v2`:

```python
    "evidence_present_v3": _ProbeScenarioConfig(
        cli_name="evidence_present_v3",
        scenario_id="lm5u_acceptance_criteria_evidence_present",
        scenario_version="v5",
        state="post_verify_pre_bind",
        evidence_packet="acceptance_criteria_v3",
        expected_disposition="candidate_action_request",
        expected_response_kind="action_request",
        expected_action_id="draft_repair_params",
        expected_attempt_valid=True,
    ),
```

Add this constant beside the existing evidence packet ids:

```python
ACCEPTANCE_CRITERIA_EVIDENCE_PACKET_ID = (
    "lm5u_acceptance_criteria_evidence"
)
```

- [ ] **Step 4: Update constants test for the new packet id**

Rename `test_lm5t_evidence_constants_are_source_of_truth` to a neutral name such as `test_probe_evidence_constants_are_source_of_truth`, and add:

```python
    assert (
        PROBE.ACCEPTANCE_CRITERIA_EVIDENCE_PACKET_ID
        == "lm5u_acceptance_criteria_evidence"
    )
```

- [ ] **Step 5: Run Task 1 tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_scenario_configs_are_source_of_truth `
  mcp_server\tests\test_lm5k_worker_probe.py::test_probe_evidence_constants_are_source_of_truth `
  -q
```

Expected: `2 passed`.

- [ ] **Step 6: Commit Task 1**

```powershell
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "test(lm5u): add acceptance criteria scenario identity"
```

---

### Task 2: Add Acceptance-Criteria v3 Packet Builder

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`
- Test: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Write failing routing and packet-shape tests**

Add a routing test near `test_knowledge_packets_route_v2_repair_intent_evidence`:

```python
def test_knowledge_packets_route_v3_acceptance_criteria_evidence() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_present_v3"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == [
        "script_body_gotcha",
        "lm5u_acceptance_criteria_evidence",
    ]
    assert [packet.kind for packet in packets] == ["gotcha", "evidence"]
```

Add the v3 field-shape test after the v2 evidence test:

```python
def test_acceptance_criteria_evidence_v3_fields_are_bounded_and_provenance_tagged() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)

    assert packet.packet_id == "lm5u_acceptance_criteria_evidence"
    assert packet.kind == "evidence"
    assert packet.title == "Acceptance-criteria repair evidence"
    assert packet.content["source"] == "probe_fixture"
    assert packet.content["trust"] == "high"
    assert packet.content["state"] == "post_verify_pre_bind"

    fields = packet.content["fields"]
    assert set(fields) == {
        "current_code",
        "language",
        "recommended_mode",
        "repair_anchor",
        "pin_contract",
        "target_diagnostics",
        "expected_repair_outcome",
        "acceptance_criteria",
    }

    assert fields["current_code"]["value"] == "A = DefinitelyMissingSymbol;"
    assert fields["language"]["value"] == "csharp"
    assert fields["recommended_mode"]["value"] == "body"
    assert fields["repair_anchor"] == {
        "value": {
            "component_guid": PROBE.PROBE_COMPONENT_GUID,
            "language": "csharp",
        },
        "source": "graph.memory.facts.repair_anchor",
    }

    assert fields["pin_contract"] == {
        "source": "create_script.initial_execution_params.pins_out",
        "value": {
            "pins_out": ("A:double",),
            "output_requirements": (
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
            ),
        },
    }

    target_diagnostics = fields["target_diagnostics"]
    assert target_diagnostics["source"] == (
        "create_script.receipt.script_receipt.repair_anchor"
    )
    assert set(target_diagnostics["fields"]) == {"target_errors"}
    assert target_diagnostics["fields"]["target_errors"]["value"] == (
        PROBE.REPAIR_TARGET_ERROR,
    )

    assert fields["expected_repair_outcome"] == {
        "value": "succeeded",
        "source": "workflow_contract.rules.verify_repair.expected_outcome",
    }

    acceptance = fields["acceptance_criteria"]
    assert acceptance["source"] == (
        "workflow_contract + create_script.initial_execution_params + "
        "create_script.receipt.script_receipt.repair_anchor + script_body_gotcha"
    )
    assert [
        criterion["criterion_id"]
        for criterion in acceptance["criteria"]
    ] == [
        "output_a_assigned",
        "output_a_double_compatible",
        "verify_repair_succeeds",
        "preserve_body_mode",
        "resolve_target_diagnostics",
        "remove_unresolved_symbol",
    ]
    assert all(
        set(criterion) == {"criterion_id", "description", "source"}
        for criterion in acceptance["criteria"]
    )
```

- [ ] **Step 2: Run the v3 tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_knowledge_packets_route_v3_acceptance_criteria_evidence `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_evidence_v3_fields_are_bounded_and_provenance_tagged `
  -q
```

Expected: fail because `_acceptance_criteria_evidence_packet` and routing do not exist.

- [ ] **Step 3: Add v3 helper functions**

In `scripts/lm5k_worker_probe.py`, add these helpers near `_pin_contract_from_params` and `_repair_intent_evidence_packet`:

```python
def _acceptance_pin_contract_from_params(params: Mapping[str, Any]) -> dict:
    base = _pin_contract_from_params(params)
    pins_out = base["value"]["pins_out"]
    _invariant(
        pins_out == ["A:double"],
        "acceptance criteria output pin contract changed",
    )
    return {
        "source": "create_script.initial_execution_params.pins_out",
        "value": {
            "pins_out": list(pins_out),
            "output_requirements": [
                {
                    "requirement_id": "output_a_assigned",
                    "description": "Output A must be assigned.",
                    "source": (
                        "create_script.initial_execution_params.pins_out"
                    ),
                },
                {
                    "requirement_id": "output_a_double_compatible",
                    "description": "Output A must be double-compatible.",
                    "source": (
                        "create_script.initial_execution_params.pins_out"
                    ),
                },
            ],
        },
    }


def _acceptance_criteria() -> dict:
    return {
        "source": (
            "workflow_contract + create_script.initial_execution_params + "
            "create_script.receipt.script_receipt.repair_anchor + "
            "script_body_gotcha"
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
                    "The repaired body must satisfy the verify_repair "
                    "expected_outcome: succeeded."
                ),
                "source": (
                    "workflow_contract.rules.verify_repair.expected_outcome"
                ),
            },
            {
                "criterion_id": "preserve_body_mode",
                "description": "The repair must preserve body-style code.",
                "source": "script_body_gotcha",
            },
            {
                "criterion_id": "resolve_target_diagnostics",
                "description": (
                    "The repair must resolve the current target diagnostics."
                ),
                "source": (
                    "create_script.receipt.script_receipt.repair_anchor."
                    "target_errors"
                ),
            },
            {
                "criterion_id": "remove_unresolved_symbol",
                "description": (
                    "The repaired body must not leave "
                    "DefinitelyMissingSymbol unresolved."
                ),
                "source": (
                    "create_script.receipt.script_receipt.repair_anchor."
                    "target_errors"
                ),
            },
        ],
    }
```

- [ ] **Step 4: Add `_acceptance_criteria_evidence_packet`**

Add the new builder after `_repair_intent_evidence_packet`:

```python
def _acceptance_criteria_evidence_packet(graph):
    from rook.agent.local_worker_turn_context import WorkerKnowledgePacket

    receipt = _require_receipt_mapping(graph)
    params = _require_create_execution_params(graph)
    initial_params = _create_initial_execution_params_from_contract()
    receipt_repair_anchor = receipt.get("repair_anchor")
    _invariant(
        isinstance(receipt_repair_anchor, Mapping),
        "receipt repair anchor missing",
    )
    facts = graph.memory.facts
    repair_anchor = facts.get("repair_anchor")
    _invariant(isinstance(repair_anchor, Mapping), "repair anchor missing")

    diagnostic_fields = {}
    if "target_errors" in receipt_repair_anchor:
        diagnostic_fields["target_errors"] = _bounded_target_diagnostics(
            receipt_repair_anchor.get("target_errors"),
            source=(
                "create_script.receipt.script_receipt.repair_anchor."
                "target_errors"
            ),
        )
    if "target_warnings" in receipt_repair_anchor:
        diagnostic_fields["target_warnings"] = _bounded_target_diagnostics(
            receipt_repair_anchor.get("target_warnings"),
            source=(
                "create_script.receipt.script_receipt.repair_anchor."
                "target_warnings"
            ),
        )
    _invariant(bool(diagnostic_fields), "target diagnostics missing")

    content = {
        "source": "probe_fixture",
        "trust": "high",
        "state": "post_verify_pre_bind",
        "fields": {
            "current_code": _bounded_current_code(params.get("code")),
            "language": {
                "value": receipt.get("language"),
                "source": "create_script.receipt.script_receipt.language",
            },
            "recommended_mode": {
                "value": "body",
                "source": "script_body_gotcha",
                "derivation": "existing worker-visible gotcha convention",
            },
            "repair_anchor": {
                "value": _stable_repair_anchor_value(repair_anchor),
                "source": "graph.memory.facts.repair_anchor",
            },
            "pin_contract": _acceptance_pin_contract_from_params(
                initial_params
            ),
            "target_diagnostics": {
                "source": (
                    "create_script.receipt.script_receipt.repair_anchor"
                ),
                "fields": diagnostic_fields,
            },
            "expected_repair_outcome": {
                "value": _expected_repair_outcome(),
                "source": (
                    "workflow_contract.rules.verify_repair."
                    "expected_outcome"
                ),
            },
            "acceptance_criteria": _acceptance_criteria(),
        },
    }
    return WorkerKnowledgePacket(
        packet_id=ACCEPTANCE_CRITERIA_EVIDENCE_PACKET_ID,
        kind="evidence",
        title="Acceptance-criteria repair evidence",
        content=content,
    )
```

- [ ] **Step 5: Route `acceptance_criteria_v3`**

Update `_knowledge_packets_for_scenario`:

```python
    if scenario.evidence_packet == "acceptance_criteria_v3":
        packets.append(_acceptance_criteria_evidence_packet(graph))
        return tuple(packets)
```

Keep the existing `none`, `repair_v1`, and `repair_intent_v2` branches unchanged.

- [ ] **Step 6: Run Task 2 tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_knowledge_packets_route_v3_acceptance_criteria_evidence `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_evidence_v3_fields_are_bounded_and_provenance_tagged `
  -q
```

Expected: `2 passed`.

- [ ] **Step 7: Run full LM5K probe tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  -q
```

Expected: all LM5K probe tests pass.

- [ ] **Step 8: Commit Task 2**

```powershell
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "feat(lm5u): add acceptance criteria evidence packet"
```

---

### Task 3: Preserve Evidence Ladder and Non-Leakage

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Add explicit ladder visibility test**

Add this test near the v1/v2 diagnostic visibility tests:

```python
def test_evidence_ladder_visibility_is_stable() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()

    v1 = json.dumps(
        _jsonable(PROBE._repair_evidence_packet(result.final_graph).content),
        sort_keys=True,
    )
    v2 = json.dumps(
        _jsonable(
            PROBE._repair_intent_evidence_packet(result.final_graph).content
        ),
        sort_keys=True,
    )
    v3 = json.dumps(
        _jsonable(
            PROBE._acceptance_criteria_evidence_packet(result.final_graph).content
        ),
        sort_keys=True,
    )

    assert "target_errors" not in v1
    assert "acceptance_criteria" not in v1

    assert "target_errors" in v2
    assert "acceptance_criteria" not in v2

    assert "target_errors" in v3
    assert "acceptance_criteria" in v3

    for rendered in (v1, v2, v3):
        assert PROBE.PROBE_REPAIR_CODE not in rendered
        assert "A = 42.0;" not in rendered
        assert "hidden BindStepSpec.base_params.code" not in rendered
```

- [ ] **Step 2: Add v3 no-replacement-literal test**

Add this focused guard:

```python
def test_acceptance_criteria_v3_does_not_publish_replacement_literals() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)
    rendered = json.dumps(_jsonable(packet.content), sort_keys=True)

    assert "DefinitelyMissingSymbol" in rendered
    assert "Output A must be assigned." in rendered
    assert "Output A must be double-compatible." in rendered
    assert "A = 42.0;" not in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "set A to" not in rendered
    assert "replacement code" not in rendered
    assert "repair diff" not in rendered
```

- [ ] **Step 3: Run the ladder tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_evidence_ladder_visibility_is_stable `
  mcp_server\tests\test_lm5k_worker_probe.py::test_acceptance_criteria_v3_does_not_publish_replacement_literals `
  -q
```

Expected: `2 passed`.

- [ ] **Step 4: Commit Task 3**

```powershell
git add mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "test(lm5u): guard acceptance evidence ladder"
```

---

### Task 4: Add LM5R v3 Scenario Selector

**Files:**
- Modify: `scripts/lm5r_two_pass_publication_probe.py`
- Test: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Write failing selector/default tests**

Update `test_constants_are_pinned`:

```python
    assert PROBE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
        "evidence_present_v2_like",
        "evidence_present_v3_like",
    )
```

Update `test_args_defaults_and_custom_values` so the custom parse exercises v3:

```python
            "evidence_present_v3_like",
```

and:

```python
    assert custom.scenarios == [
        "evidence_absent_like",
        "evidence_present_v3_like",
    ]
```

Rename `test_scenario_map_includes_lm5t_v2_without_changing_defaults` to `test_scenario_map_includes_lm5u_v3_without_changing_defaults`, and update the expected map:

```python
def test_scenario_map_includes_lm5u_v3_without_changing_defaults() -> None:
    assert PROBE._SCENARIO_MAP == {
        "evidence_absent_like": "evidence_absent",
        "evidence_present_like": "evidence_present",
        "evidence_present_v2_like": "evidence_present_v2",
        "evidence_present_v3_like": "evidence_present_v3",
    }
    assert PROBE.DEFAULT_SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
```

Add a render test after `test_pass1_messages_can_render_lm5t_v2_envelope`:

```python
def test_pass1_messages_can_render_lm5u_v3_envelope() -> None:
    messages, envelope = PROBE._pass1_messages_for_scenario(
        "evidence_present_v3_like"
    )

    assert [message["role"] for message in messages] == [
        "system",
        "user",
        "user",
    ]
    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    assert [packet["packet_id"] for packet in envelope["context"]["knowledge"]] == [
        "script_body_gotcha",
        "lm5u_acceptance_criteria_evidence",
    ]
    rendered_envelope = json.dumps(envelope, sort_keys=True)
    assert "target_errors" in rendered_envelope
    assert "acceptance_criteria" in rendered_envelope
    assert "output_a_assigned" in rendered_envelope
    assert "output_a_double_compatible" in rendered_envelope
    assert "verify_repair_succeeds" in rendered_envelope
    assert "A = 42.0;" not in rendered_envelope
    assert "PROBE_REPAIR_CODE" not in rendered_envelope
```

- [ ] **Step 2: Run selector tests and verify RED**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_constants_are_pinned `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_scenario_map_includes_lm5u_v3_without_changing_defaults `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_messages_can_render_lm5u_v3_envelope `
  -q
```

Expected: fail because LM5R does not know `evidence_present_v3_like`.

- [ ] **Step 3: Add LM5R selector**

In `scripts/lm5r_two_pass_publication_probe.py`, update `SCENARIO_NAMES`:

```python
SCENARIO_NAMES = (
    "evidence_absent_like",
    "evidence_present_like",
    "evidence_present_v2_like",
    "evidence_present_v3_like",
)
```

Keep `DEFAULT_SCENARIO_NAMES` unchanged:

```python
DEFAULT_SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
```

Update `_SCENARIO_MAP`:

```python
_SCENARIO_MAP = {
    "evidence_absent_like": "evidence_absent",
    "evidence_present_like": "evidence_present",
    "evidence_present_v2_like": "evidence_present_v2",
    "evidence_present_v3_like": "evidence_present_v3",
}
```

Do not edit `PASS1_DECISION_INSTRUCTION_VERSION`, `_PASS1_DECISION_INSTRUCTION`, pass-two formatter text, `STATUSES`, or `_single_kind_response_schema`.

- [ ] **Step 4: Run LM5R selector tests and verify GREEN**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_constants_are_pinned `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_args_defaults_and_custom_values `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_scenario_map_includes_lm5u_v3_without_changing_defaults `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_messages_can_render_lm5u_v3_envelope `
  -q
```

Expected: `4 passed`.

- [ ] **Step 5: Run full LM5R probe tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all LM5R probe tests pass.

- [ ] **Step 6: Commit Task 4**

```powershell
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5u): add acceptance criteria probe selector"
```

---

### Task 5: Scope and Boundary Guards

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

- [ ] **Step 1: Add LM5K boundary guard test**

Add this test near the existing hidden-repair-params guard:

```python
def test_lm5u_acceptance_criteria_boundary_guard() -> None:
    contract = PROBE._probe_contract()
    repair_rule = next(
        rule for rule in contract.rules
        if rule.node_id == "repair_same_component"
    )
    bind_step = next(
        step for step in repair_rule.steps_by_seen_count
        if getattr(step, "base_params", None)
    )
    assert bind_step.base_params["code"] == PROBE.PROBE_REPAIR_CODE

    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._acceptance_criteria_evidence_packet(result.final_graph)
    rendered = json.dumps(_jsonable(packet.content), sort_keys=True)

    assert "acceptance_criteria" in rendered
    assert "lm5u_acceptance_criteria_evidence" not in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "A = 42.0;" not in rendered
    assert "set A to" not in rendered
```

Note: `packet_id` is not part of `packet.content`, so the packet id should be asserted in the packet-shape test, not in this rendered-content guard.

- [ ] **Step 2: Add LM5R no-drift test**

Extend the existing pass-one instruction guard or add a new focused test:

```python
def test_lm5u_does_not_change_two_pass_publication_mechanics() -> None:
    assert (
        PROBE.PASS1_DECISION_INSTRUCTION_VERSION
        == "lm5s.pass1_decision_instruction:v2"
    )
    instruction = PROBE._PASS1_DECISION_INSTRUCTION
    assert (
        "observation: choose only to report visible state or evidence"
        in instruction
    )
    assert "Do not use observation to choose" in instruction
    assert "acceptance_criteria" not in instruction
    assert "target_errors" not in instruction
    assert "output_a_assigned" not in instruction
    assert "A = 42.0;" not in instruction
```

- [ ] **Step 3: Run new boundary tests**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_lm5u_acceptance_criteria_boundary_guard `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_lm5u_does_not_change_two_pass_publication_mechanics `
  -q
```

Expected: `2 passed`.

- [ ] **Step 4: Commit Task 5**

```powershell
git add mcp_server\tests\test_lm5k_worker_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "test(lm5u): guard acceptance criteria boundaries"
```

---

### Task 6: Final Verification

**Files:**
- No source changes unless verification exposes a defect.

- [ ] **Step 1: Run targeted gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all targeted tests pass.

- [ ] **Step 2: Run nearby gate**

Run:

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  -q
```

Expected: all nearby probe tests pass.

- [ ] **Step 3: Run Python 3.10 compile**

Run:

```powershell
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Verify exact scope**

Run:

```powershell
git diff --name-only origin/main..HEAD
```

Expected:

```text
docs/superpowers/plans/2026-07-05-lm5u-acceptance-criteria-evidence-v3.md
docs/superpowers/specs/2026-07-05-lm5u-acceptance-criteria-evidence-v3-design.md
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
```

- [ ] **Step 5: Verify no production diff**

Run:

```powershell
git diff --name-only origin/main..HEAD -- mcp_server\src
```

Expected: no output.

- [ ] **Step 6: Verify no LM5R prompt/publication drift**

Run:

```powershell
$matches = git diff -U0 origin/main..HEAD -- scripts\lm5r_two_pass_publication_probe.py |
  rg "^[+-][^+-].*(PASS1_DECISION_INSTRUCTION_VERSION|_PASS1_DECISION_INSTRUCTION|_PASS2|STATUSES =|_single_kind_response_schema)"
if ($LASTEXITCODE -eq 1) {
  exit 0
}
$matches
exit $LASTEXITCODE
```

Expected: no output.

- [ ] **Step 7: Verify whitespace and probe artifacts**

Run:

```powershell
git diff --check origin/main..HEAD
git status --short --ignored probe_runs
git status --short --branch
```

Expected:

```text
git diff --check exits 0
probe_runs/ is absent or ignored only
branch has no unstaged/staged changes
```

- [ ] **Step 8: Commit verification fixes only if needed**

If verification required a fix, commit that fix with a focused message. If no fixes were needed, do not create a Task 6 commit.
