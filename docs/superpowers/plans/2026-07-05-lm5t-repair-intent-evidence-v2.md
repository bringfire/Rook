# LM5T Repair-Intent Evidence v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic LM5T repair-intent evidence v2 scenario and selector without changing prompt, parser, production transport, or publication mechanics.

**Architecture:** LM5T extends the existing LM5K probe fixture with a new `evidence_present_v2` scenario and a new `lm5t_repair_intent_evidence` packet built from upstream fixture facts. LM5R gets one new scenario selector that consumes the new context, while its defaults and two-pass mechanics remain unchanged.

**Tech Stack:** Python 3.10-compatible scripts/tests, pytest, existing LM5K/LM5R probe helpers, `WorkerKnowledgePacket(kind="evidence")`.

---

## File Map

Modify:

```text
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
```

Docs already present:

```text
docs/superpowers/specs/2026-07-05-lm5t-repair-intent-evidence-v2-design.md
```

This plan adds:

```text
docs/superpowers/plans/2026-07-05-lm5t-repair-intent-evidence-v2.md
```

Do not modify:

```text
mcp_server/src/rook/**/*.py
docs/superpowers/probes/**/*.md
scripts/lm5p_ollama_think_format_spike.py
```

No live probe run in this implementation PR. No `probe_runs/` artifacts.

---

## Task 1: Scenario Config Identity

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `scripts/lm5k_worker_probe.py`

### Goal

Replace the scenario boolean with an explicit evidence-packet selector and add the new `evidence_present_v2` scenario identity.

### Steps

- [ ] **Step 1: Update the scenario config test first**

In `mcp_server/tests/test_lm5k_worker_probe.py`, update `test_scenario_configs_are_source_of_truth` to expect three scenarios and the new selector field:

```python
def test_scenario_configs_are_source_of_truth() -> None:
    assert PROBE.SCENARIO_WORKFLOW_ID == "lm5k_first_probe"
    assert set(PROBE._SCENARIOS) == {
        "evidence_absent",
        "evidence_present",
        "evidence_present_v2",
    }

    absent = PROBE._SCENARIOS["evidence_absent"]
    assert absent.cli_name == "evidence_absent"
    assert absent.scenario_id == "lm5n_repair_evidence_absent"
    assert absent.scenario_version == "v3"
    assert absent.state == "post_verify_pre_bind"
    assert absent.evidence_packet == "none"
    assert absent.expected_disposition == "clarification_needed"
    assert absent.expected_response_kind == "clarification_request"
    assert absent.expected_action_id is None
    assert absent.expected_attempt_valid is True

    present = PROBE._SCENARIOS["evidence_present"]
    assert present.cli_name == "evidence_present"
    assert present.scenario_id == "lm5n_repair_evidence_present"
    assert present.scenario_version == "v3"
    assert present.state == "post_verify_pre_bind"
    assert present.evidence_packet == "repair_v1"
    assert present.expected_disposition == "candidate_action_request"
    assert present.expected_response_kind == "action_request"
    assert present.expected_action_id == "draft_repair_params"
    assert present.expected_attempt_valid is True

    present_v2 = PROBE._SCENARIOS["evidence_present_v2"]
    assert present_v2.cli_name == "evidence_present_v2"
    assert present_v2.scenario_id == "lm5t_repair_intent_evidence_present"
    assert present_v2.scenario_version == "v4"
    assert present_v2.state == "post_verify_pre_bind"
    assert present_v2.evidence_packet == "repair_intent_v2"
    assert present_v2.expected_disposition == "candidate_action_request"
    assert present_v2.expected_response_kind == "action_request"
    assert present_v2.expected_action_id == "draft_repair_params"
    assert present_v2.expected_attempt_valid is True

    assert "lm5k_golden_repair_v2" not in {
        absent.scenario_id,
        present.scenario_id,
        present_v2.scenario_id,
    }
```

- [ ] **Step 2: Run the test and verify it fails**

Run from repo root:

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5t-repair-intent-evidence-v2
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py::test_scenario_configs_are_source_of_truth -q
```

Expected: FAIL because `_ProbeScenarioConfig` has no `evidence_packet` field and `_SCENARIOS` lacks `evidence_present_v2`.

If this worktree has no `.venv`, create a temporary junction to the primary venv for test execution only:

```powershell
cmd /c mklink /J "C:\Users\bring\.config\superpowers\worktrees\Rook\lm5t-repair-intent-evidence-v2\mcp_server\.venv" "C:\UDEV\Rook\mcp_server\.venv"
```

Remove that junction before final status checks:

```powershell
cmd /c rmdir "C:\Users\bring\.config\superpowers\worktrees\Rook\lm5t-repair-intent-evidence-v2\mcp_server\.venv"
```

- [ ] **Step 3: Update the dataclass and scenarios**

In `scripts/lm5k_worker_probe.py`, replace the `include_evidence_packet` field in `_ProbeScenarioConfig` with `evidence_packet: str`.

Change:

```python
@dataclass(frozen=True)
class _ProbeScenarioConfig:
    cli_name: str
    scenario_id: str
    scenario_version: str
    state: str
    include_evidence_packet: bool
    expected_disposition: str
    expected_response_kind: str
    expected_action_id: str | None
    expected_attempt_valid: bool
```

to:

```python
@dataclass(frozen=True)
class _ProbeScenarioConfig:
    cli_name: str
    scenario_id: str
    scenario_version: str
    state: str
    evidence_packet: str
    expected_disposition: str
    expected_response_kind: str
    expected_action_id: str | None
    expected_attempt_valid: bool
```

Update `_SCENARIOS`:

```python
_SCENARIOS = {
    "evidence_absent": _ProbeScenarioConfig(
        cli_name="evidence_absent",
        scenario_id="lm5n_repair_evidence_absent",
        scenario_version="v3",
        state="post_verify_pre_bind",
        evidence_packet="none",
        expected_disposition="clarification_needed",
        expected_response_kind="clarification_request",
        expected_action_id=None,
        expected_attempt_valid=True,
    ),
    "evidence_present": _ProbeScenarioConfig(
        cli_name="evidence_present",
        scenario_id="lm5n_repair_evidence_present",
        scenario_version="v3",
        state="post_verify_pre_bind",
        evidence_packet="repair_v1",
        expected_disposition="candidate_action_request",
        expected_response_kind="action_request",
        expected_action_id="draft_repair_params",
        expected_attempt_valid=True,
    ),
    "evidence_present_v2": _ProbeScenarioConfig(
        cli_name="evidence_present_v2",
        scenario_id="lm5t_repair_intent_evidence_present",
        scenario_version="v4",
        state="post_verify_pre_bind",
        evidence_packet="repair_intent_v2",
        expected_disposition="candidate_action_request",
        expected_response_kind="action_request",
        expected_action_id="draft_repair_params",
        expected_attempt_valid=True,
    ),
}
```

- [ ] **Step 4: Run the config test**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py::test_scenario_configs_are_source_of_truth -q
```

Expected: PASS.

- [ ] **Step 5: Run the LM5K probe tests to expose remaining routing failures**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py -q
```

Expected: FAIL in tests that still expect `include_evidence_packet` or old packet routing. Those failures are handled in the next tasks.

- [ ] **Step 6: Commit Task 1**

```powershell
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "test(lm5t): add repair intent scenario identity"
```

---

## Task 2: Upstream Receipt Diagnostic and v1 Stability

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `scripts/lm5k_worker_probe.py`

### Goal

Enrich the deterministic upstream receipt with one bounded target diagnostic while preventing the historical LM5N v1 packet from exposing it.

### Steps

- [ ] **Step 1: Add constants expectations**

In `mcp_server/tests/test_lm5k_worker_probe.py`, add to an existing constants/source-of-truth test or create a new test near `test_transport_modes_are_source_of_truth`:

```python
def test_lm5t_evidence_constants_are_source_of_truth() -> None:
    assert PROBE.EVIDENCE_PACKET_ID == "lm5n_repair_evidence"
    assert PROBE.REPAIR_INTENT_EVIDENCE_PACKET_ID == "lm5t_repair_intent_evidence"
    assert PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS == 3
    assert PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS == 300
    assert PROBE.REPAIR_TARGET_ERROR == (
        "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the "
        "current context."
    )
```

- [ ] **Step 2: Add receipt and v1 stability assertions**

Add this test after `test_derived_graph_state_is_coherent_post_verify` or near the evidence-packet tests:

```python
def test_upstream_receipt_contains_bounded_target_error() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    receipt = PROBE._require_receipt_mapping(result.final_graph)
    repair_anchor = receipt["repair_anchor"]

    assert repair_anchor["target_errors"] == [PROBE.REPAIR_TARGET_ERROR]
    assert "target_warnings" not in repair_anchor
    assert isinstance(repair_anchor["target_errors"][0], str)
```

Update `test_evidence_packet_fields_are_bounded_and_provenance_tagged` to pin v1 `repair_anchor.value`:

```python
    assert fields["repair_anchor"] == {
        "value": {
            "component_guid": PROBE.PROBE_COMPONENT_GUID,
            "language": "csharp",
        },
        "source": "graph.memory.facts.repair_anchor",
    }
```

Add explicit v1 non-leak assertions:

```python
def test_repair_evidence_v1_does_not_expose_target_diagnostics() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_evidence_packet(result.final_graph)
    rendered = json.dumps(packet.content)

    assert "target_errors" not in rendered
    assert "target_warnings" not in rendered
    assert "DefinitelyMissingSymbol" in rendered
    assert PROBE.REPAIR_TARGET_ERROR not in rendered
```

The `DefinitelyMissingSymbol` assertion remains true because v1 already exposes `current_code`; the full diagnostic string must not appear.

- [ ] **Step 3: Run the new tests and verify they fail**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_lm5t_evidence_constants_are_source_of_truth `
  mcp_server\tests\test_lm5k_worker_probe.py::test_upstream_receipt_contains_bounded_target_error `
  mcp_server\tests\test_lm5k_worker_probe.py::test_repair_evidence_v1_does_not_expose_target_diagnostics `
  -q
```

Expected: FAIL because constants and receipt diagnostic do not exist and v1 still copies the whole repair anchor.

- [ ] **Step 4: Add constants and enrich the deterministic receipt**

In `scripts/lm5k_worker_probe.py`, near evidence constants, change:

```python
EVIDENCE_PACKET_ID = "lm5n_repair_evidence"
EVIDENCE_CURRENT_CODE_MAX_CHARS = 500
```

to:

```python
EVIDENCE_PACKET_ID = "lm5n_repair_evidence"
REPAIR_INTENT_EVIDENCE_PACKET_ID = "lm5t_repair_intent_evidence"
EVIDENCE_CURRENT_CODE_MAX_CHARS = 500
EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS = 3
EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS = 300
REPAIR_TARGET_ERROR = (
    "CS0103: The name 'DefinitelyMissingSymbol' does not exist in the "
    "current context."
)
```

In `_wrapped_failure_create_raw`, update `repair_anchor` from:

```python
"repair_anchor": {
    "component_guid": PROBE_COMPONENT_GUID,
    "language": "csharp",
},
```

to:

```python
"repair_anchor": {
    "component_guid": PROBE_COMPONENT_GUID,
    "language": "csharp",
    "target_errors": [REPAIR_TARGET_ERROR],
},
```

Do not add `target_warnings`.

- [ ] **Step 5: Stabilize the v1 repair anchor copy**

Add helper:

```python
def _stable_repair_anchor_value(repair_anchor: Mapping[str, Any]) -> dict:
    component_guid = repair_anchor.get("component_guid")
    language = repair_anchor.get("language")
    _invariant(isinstance(component_guid, str) and component_guid, "repair anchor component_guid missing")
    _invariant(isinstance(language, str) and language, "repair anchor language missing")
    return {
        "component_guid": component_guid,
        "language": language,
    }
```

In `_repair_evidence_packet`, replace:

```python
"repair_anchor": {
    "value": dict(repair_anchor),
    "source": "graph.memory.facts.repair_anchor",
},
```

with:

```python
"repair_anchor": {
    "value": _stable_repair_anchor_value(repair_anchor),
    "source": "graph.memory.facts.repair_anchor",
},
```

- [ ] **Step 6: Run the Task 2 tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_lm5t_evidence_constants_are_source_of_truth `
  mcp_server\tests\test_lm5k_worker_probe.py::test_upstream_receipt_contains_bounded_target_error `
  mcp_server\tests\test_lm5k_worker_probe.py::test_repair_evidence_v1_does_not_expose_target_diagnostics `
  mcp_server\tests\test_lm5k_worker_probe.py::test_evidence_packet_fields_are_bounded_and_provenance_tagged `
  -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 2**

```powershell
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "feat(lm5t): enrich receipt diagnostic without v1 leak"
```

---

## Task 3: Repair-Intent Evidence v2 Packet

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `scripts/lm5k_worker_probe.py`

### Goal

Add `_repair_intent_evidence_packet(...)`, route it through `evidence_present_v2`, and prove the v2 packet exposes bounded diagnostics without exposing hidden repair params.

### Steps

- [ ] **Step 1: Add v2 packet shape tests**

Add this helper test near the existing evidence-packet tests:

```python
def test_repair_intent_evidence_v2_fields_are_bounded_and_provenance_tagged() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_intent_evidence_packet(result.final_graph)

    assert packet.packet_id == "lm5t_repair_intent_evidence"
    assert packet.kind == "evidence"
    assert packet.title == "Receipt-derived repair intent evidence"
    assert packet.content["source"] == "probe_fixture"
    assert packet.content["trust"] == "high"
    assert packet.content["state"] == "post_verify_pre_bind"

    fields = packet.content["fields"]
    assert set(fields) == {
        "current_code",
        "recommended_mode",
        "language",
        "component_guid",
        "repair_anchor",
        "pin_contract",
        "current_verification",
        "target_diagnostics",
        "expected_repair_outcome",
    }

    assert fields["current_code"]["value"] == "A = DefinitelyMissingSymbol;"
    assert fields["recommended_mode"]["value"] == "body"
    assert fields["language"]["value"] == "csharp"
    assert fields["component_guid"]["value"] == PROBE.PROBE_COMPONENT_GUID
    assert fields["repair_anchor"] == {
        "value": {
            "component_guid": PROBE.PROBE_COMPONENT_GUID,
            "language": "csharp",
        },
        "source": "graph.memory.facts.repair_anchor",
    }
    assert "target_errors" not in fields["repair_anchor"]["value"]
    assert "target_warnings" not in fields["repair_anchor"]["value"]

    assert fields["pin_contract"] == {
        "source": "create_script.initial_execution_params",
        "value": {
            "pins_in": [],
            "pins_out": ["A:double"],
        },
    }
    assert fields["current_verification"] == {
        "source": "create_script.receipt.script_receipt.verification",
        "value": {
            "status": "failed",
            "target_error_count": 1,
        },
    }
    assert fields["expected_repair_outcome"] == {
        "value": "succeeded",
        "source": "workflow_contract.rules.verify_repair.expected_outcome",
    }

    diagnostics = fields["target_diagnostics"]
    assert diagnostics["source"] == "create_script.receipt.script_receipt.repair_anchor"
    assert set(diagnostics["fields"]) == {"target_errors"}
    target_errors = diagnostics["fields"]["target_errors"]
    assert target_errors == {
        "value": [PROBE.REPAIR_TARGET_ERROR],
        "source": "create_script.receipt.script_receipt.repair_anchor.target_errors",
        "max_items": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS,
        "max_chars_per_item": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS,
        "truncated": False,
    }
    assert all(isinstance(item, str) for item in target_errors["value"])
```

Add a routing test:

```python
def test_knowledge_packets_route_v2_repair_intent_evidence() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_present_v2"],
        result.final_graph,
    )

    assert [packet.packet_id for packet in packets] == [
        "script_body_gotcha",
        "lm5t_repair_intent_evidence",
    ]
    assert [packet.kind for packet in packets] == ["gotcha", "evidence"]
```

- [ ] **Step 2: Add rendered-envelope visibility tests**

Add:

```python
def test_evidence_present_v2_probe_envelope_exposes_repair_intent_evidence_only() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context(PROBE._SCENARIOS["evidence_present_v2"])
    )
    rendered = json.dumps(payload)

    assert "lm5t_repair_intent_evidence" in rendered
    assert "target_errors" in rendered
    assert PROBE.REPAIR_TARGET_ERROR in rendered
    assert "DefinitelyMissingSymbol" in rendered
    assert PROBE.PROBE_COMPONENT_GUID in rendered
    assert "A = DefinitelyMissingSymbol;" in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "A = 42.0;" not in rendered
    assert "already-bound repair params" not in rendered
```

Update `test_evidence_present_probe_envelope_exposes_only_bounded_evidence_values` so v1 explicitly does not expose target diagnostics:

```python
    assert "target_errors" not in rendered
    assert PROBE.REPAIR_TARGET_ERROR not in rendered
```

- [ ] **Step 3: Add bounded diagnostic helper tests**

Add:

```python
def test_target_diagnostic_evidence_bounds_items_and_chars() -> None:
    values = [
        "short",
        "x" * (PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS + 10),
        "kept",
        "dropped",
    ]
    wrapped = PROBE._bounded_target_diagnostics(
        values,
        source="test.source",
    )

    assert wrapped == {
        "value": [
            "short",
            "x" * PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS,
            "kept",
        ],
        "source": "test.source",
        "max_items": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS,
        "max_chars_per_item": PROBE.EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS,
        "truncated": True,
    }
```

Add:

```python
def test_target_diagnostic_evidence_requires_string_items() -> None:
    with pytest.raises(RuntimeError, match="target diagnostic item not string"):
        PROBE._bounded_target_diagnostics(
            ["ok", {"message": "not allowed"}],
            source="test.source",
        )
```

- [ ] **Step 4: Run the new tests and verify they fail**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_repair_intent_evidence_v2_fields_are_bounded_and_provenance_tagged `
  mcp_server\tests\test_lm5k_worker_probe.py::test_knowledge_packets_route_v2_repair_intent_evidence `
  mcp_server\tests\test_lm5k_worker_probe.py::test_evidence_present_v2_probe_envelope_exposes_repair_intent_evidence_only `
  mcp_server\tests\test_lm5k_worker_probe.py::test_target_diagnostic_evidence_bounds_items_and_chars `
  mcp_server\tests\test_lm5k_worker_probe.py::test_target_diagnostic_evidence_requires_string_items `
  -q
```

Expected: FAIL because `_repair_intent_evidence_packet` and `_bounded_target_diagnostics` do not exist.

- [ ] **Step 5: Implement v2 helper functions**

In `scripts/lm5k_worker_probe.py`, add helpers near `_bounded_current_code`:

```python
def _bounded_target_diagnostics(values: Any, *, source: str) -> dict:
    _invariant(isinstance(values, list), "target diagnostics must be list")
    output: list[str] = []
    truncated = len(values) > EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS
    for item in values[:EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS]:
        _invariant(isinstance(item, str), "target diagnostic item not string")
        if len(item) > EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS:
            truncated = True
        output.append(item[:EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS])
    return {
        "value": output,
        "source": source,
        "max_items": EVIDENCE_TARGET_DIAGNOSTIC_MAX_ITEMS,
        "max_chars_per_item": EVIDENCE_TARGET_DIAGNOSTIC_MAX_CHARS,
        "truncated": truncated,
    }
```

Add:

```python
def _expected_repair_outcome() -> str:
    contract = _probe_contract()
    for rule in contract.rules:
        if rule.node_id != "verify_repair":
            continue
        for step in rule.steps_by_seen_count:
            outcome = getattr(step, "expected_outcome", None)
            if isinstance(outcome, str) and outcome:
                return outcome
    raise RuntimeError(
        "LM5L coherent fixture invariant failed: "
        "verify_repair expected outcome missing"
    )
```

Add:

```python
def _pin_contract_from_params(params: Mapping[str, Any]) -> dict:
    pins_in = params.get("pins_in")
    pins_out = params.get("pins_out")
    _invariant(isinstance(pins_in, list), "pins_in missing")
    _invariant(isinstance(pins_out, list), "pins_out missing")
    _invariant(all(isinstance(item, str) for item in pins_in), "pins_in item not string")
    _invariant(all(isinstance(item, str) for item in pins_out), "pins_out item not string")
    return {
        "source": "create_script.initial_execution_params",
        "value": {
            "pins_in": list(pins_in),
            "pins_out": list(pins_out),
        },
    }
```

Keep these helpers private.

- [ ] **Step 6: Implement `_repair_intent_evidence_packet`**

Add beside `_repair_evidence_packet`:

```python
def _repair_intent_evidence_packet(graph):
    from rook.agent.local_worker_turn_context import WorkerKnowledgePacket

    receipt = _require_receipt_mapping(graph)
    params = _require_create_execution_params(graph)
    verification = receipt.get("verification")
    _invariant(isinstance(verification, Mapping), "verification receipt missing")
    receipt_repair_anchor = receipt.get("repair_anchor")
    _invariant(
        isinstance(receipt_repair_anchor, Mapping),
        "receipt repair anchor missing",
    )
    facts = graph.memory.facts
    repair_anchor = facts.get("repair_anchor")
    _invariant(isinstance(repair_anchor, Mapping), "repair anchor missing")

    current_verification_value = {
        "status": verification.get("status"),
        "target_error_count": verification.get("target_error_count"),
    }
    if "target_warning_count" in verification:
        current_verification_value["target_warning_count"] = verification.get(
            "target_warning_count"
        )

    diagnostic_fields: dict[str, Any] = {}
    target_errors = receipt_repair_anchor.get("target_errors")
    if target_errors is not None:
        diagnostic_fields["target_errors"] = _bounded_target_diagnostics(
            target_errors,
            source=(
                "create_script.receipt.script_receipt.repair_anchor."
                "target_errors"
            ),
        )
    target_warnings = receipt_repair_anchor.get("target_warnings")
    if target_warnings is not None:
        diagnostic_fields["target_warnings"] = _bounded_target_diagnostics(
            target_warnings,
            source=(
                "create_script.receipt.script_receipt.repair_anchor."
                "target_warnings"
            ),
        )

    content = {
        "source": "probe_fixture",
        "trust": "high",
        "state": "post_verify_pre_bind",
        "fields": {
            "current_code": _bounded_current_code(params.get("code")),
            "recommended_mode": {
                "value": "body",
                "source": "script_body_gotcha",
                "derivation": "existing worker-visible gotcha convention",
            },
            "language": {
                "value": receipt.get("language"),
                "source": "create_script.receipt.script_receipt.language",
            },
            "component_guid": {
                "value": facts.get("component_guid"),
                "source": "graph.memory.facts.component_guid",
            },
            "repair_anchor": {
                "value": _stable_repair_anchor_value(repair_anchor),
                "source": "graph.memory.facts.repair_anchor",
            },
            "pin_contract": _pin_contract_from_params(params),
            "current_verification": {
                "source": "create_script.receipt.script_receipt.verification",
                "value": current_verification_value,
            },
            "target_diagnostics": {
                "source": "create_script.receipt.script_receipt.repair_anchor",
                "fields": diagnostic_fields,
            },
            "expected_repair_outcome": {
                "value": _expected_repair_outcome(),
                "source": (
                    "workflow_contract.rules.verify_repair.expected_outcome"
                ),
            },
        },
    }
    return WorkerKnowledgePacket(
        packet_id=REPAIR_INTENT_EVIDENCE_PACKET_ID,
        kind="evidence",
        title="Receipt-derived repair intent evidence",
        content=content,
    )
```

- [ ] **Step 7: Update knowledge-packet routing**

Replace `_knowledge_packets_for_scenario` with:

```python
def _knowledge_packets_for_scenario(
    scenario: _ProbeScenarioConfig,
    graph,
) -> tuple:
    packets = [_script_body_gotcha_packet()]
    if scenario.evidence_packet == "none":
        return tuple(packets)
    if scenario.evidence_packet == "repair_v1":
        packets.append(_repair_evidence_packet(graph))
        return tuple(packets)
    if scenario.evidence_packet == "repair_intent_v2":
        packets.append(_repair_intent_evidence_packet(graph))
        return tuple(packets)
    raise RuntimeError(
        "LM5L coherent fixture invariant failed: "
        f"unknown evidence packet {scenario.evidence_packet!r}"
    )
```

- [ ] **Step 8: Run the Task 3 tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_repair_intent_evidence_v2_fields_are_bounded_and_provenance_tagged `
  mcp_server\tests\test_lm5k_worker_probe.py::test_knowledge_packets_route_v2_repair_intent_evidence `
  mcp_server\tests\test_lm5k_worker_probe.py::test_evidence_present_v2_probe_envelope_exposes_repair_intent_evidence_only `
  mcp_server\tests\test_lm5k_worker_probe.py::test_target_diagnostic_evidence_bounds_items_and_chars `
  mcp_server\tests\test_lm5k_worker_probe.py::test_target_diagnostic_evidence_requires_string_items `
  -q
```

Expected: PASS.

- [ ] **Step 9: Run the full LM5K probe test file**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5k_worker_probe.py -q
```

Expected: all tests pass.

- [ ] **Step 10: Commit Task 3**

```powershell
git add scripts\lm5k_worker_probe.py mcp_server\tests\test_lm5k_worker_probe.py
git commit -m "feat(lm5t): add repair intent evidence packet"
```

---

## Task 4: LM5R Scenario Selector

**Files:**
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`
- Modify: `scripts/lm5r_two_pass_publication_probe.py`

### Goal

Add `evidence_present_v2_like -> evidence_present_v2` while leaving LM5R defaults and two-pass mechanics unchanged.

### Steps

- [ ] **Step 1: Update selector constants tests**

In `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`, update `test_constants_are_pinned`:

```python
    assert PROBE.SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
        "evidence_present_v2_like",
    )
    assert PROBE.DEFAULT_SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
```

Add this assertion if the test does not already cover `_SCENARIO_MAP`:

```python
def test_scenario_map_includes_lm5t_v2_without_changing_defaults() -> None:
    assert PROBE._SCENARIO_MAP == {
        "evidence_absent_like": "evidence_absent",
        "evidence_present_like": "evidence_present",
        "evidence_present_v2_like": "evidence_present_v2",
    }
    assert PROBE.DEFAULT_SCENARIO_NAMES == (
        "evidence_absent_like",
        "evidence_present_like",
    )
```

- [ ] **Step 2: Update args tests**

In `test_args_defaults_and_custom_values`, keep defaults historical:

```python
    assert defaults.scenarios == list(PROBE.DEFAULT_SCENARIO_NAMES)
```

Change the custom scenario args to include v2:

```python
    custom = PROBE._args(
        [
            "--model",
            "gemma4:12b-it-qat",
            "--scenario",
            "evidence_absent_like",
            "--scenario",
            "evidence_present_v2_like",
            "--attempts",
            "5",
            "--excerpt-chars",
            "1200",
        ]
    )
    assert custom.scenarios == [
        "evidence_absent_like",
        "evidence_present_v2_like",
    ]
```

Add:

```python
def test_pass1_messages_can_render_lm5t_v2_envelope() -> None:
    messages, envelope = PROBE._pass1_messages_for_scenario(
        "evidence_present_v2_like"
    )

    assert [message["role"] for message in messages] == ["system", "user", "user"]
    assert envelope["schema"] == "rook.local_worker_turn_request:v1"
    assert [packet["packet_id"] for packet in envelope["context"]["knowledge"]] == [
        "script_body_gotcha",
        "lm5t_repair_intent_evidence",
    ]
    rendered = json.dumps(envelope)
    assert "target_errors" in rendered
    assert "DefinitelyMissingSymbol" in rendered
    assert "A = 42.0;" not in rendered
```

- [ ] **Step 3: Run the new LM5R selector tests and verify they fail**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_constants_are_pinned `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_scenario_map_includes_lm5t_v2_without_changing_defaults `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_pass1_messages_can_render_lm5t_v2_envelope `
  -q
```

Expected: FAIL because `evidence_present_v2_like` and `DEFAULT_SCENARIO_NAMES` do not exist.

- [ ] **Step 4: Add selector and defaults**

In `scripts/lm5r_two_pass_publication_probe.py`, replace:

```python
SCENARIO_NAMES = ("evidence_absent_like", "evidence_present_like")
```

with:

```python
SCENARIO_NAMES = (
    "evidence_absent_like",
    "evidence_present_like",
    "evidence_present_v2_like",
)
DEFAULT_SCENARIO_NAMES = (
    "evidence_absent_like",
    "evidence_present_like",
)
```

Update `_args`:

```python
    if args.scenarios is None:
        args.scenarios = list(DEFAULT_SCENARIO_NAMES)
```

Update `_SCENARIO_MAP`:

```python
_SCENARIO_MAP = {
    "evidence_absent_like": "evidence_absent",
    "evidence_present_like": "evidence_present",
    "evidence_present_v2_like": "evidence_present_v2",
}
```

Do not change `PASS1_DECISION_INSTRUCTION_VERSION`, `_PASS1_DECISION_INSTRUCTION`, pass-2 schemas, status taxonomy, or anomaly scoring.

- [ ] **Step 5: Run LM5R tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest mcp_server\tests\test_lm5r_two_pass_publication_probe.py -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit Task 4**

```powershell
git add scripts\lm5r_two_pass_publication_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "feat(lm5t): add repair intent probe selector"
```

---

## Task 5: Scope and Boundary Guards

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`

### Goal

Add static/boundary assertions that prevent LM5T from drifting into prompt, parser, production source, or publication-mechanics changes.

### Steps

- [ ] **Step 1: Add LM5K boundary test**

In `mcp_server/tests/test_lm5k_worker_probe.py`, add:

```python
def test_lm5t_probe_script_does_not_publish_hidden_repair_params() -> None:
    source = Path(PROBE.__file__).read_text(encoding="utf-8")
    assert "PROBE_REPAIR_CODE" in source
    assert '"code": PROBE_REPAIR_CODE' in source

    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_intent_evidence_packet(result.final_graph)
    rendered = json.dumps(packet.content)
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "A = 42.0;" not in rendered
    assert "hidden BindStepSpec.base_params.code" not in rendered
```

This test confirms the hidden repair literal still exists as a fixture bind target, but the v2 packet does not publish it.

- [ ] **Step 2: Add LM5R instruction stability test**

In `mcp_server/tests/test_lm5r_two_pass_publication_probe.py`, add:

```python
def test_lm5t_does_not_change_lm5s_pass1_instruction() -> None:
    assert (
        PROBE.PASS1_DECISION_INSTRUCTION_VERSION
        == "lm5s.pass1_decision_instruction:v2"
    )
    instruction = PROBE._PASS1_DECISION_INSTRUCTION
    assert "Do not use observation to choose" in instruction
    assert "lm5t" not in instruction.lower()
    assert "target_errors" not in instruction
    assert "DefinitelyMissingSymbol" not in instruction
```

- [ ] **Step 3: Run targeted boundary tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py::test_lm5t_probe_script_does_not_publish_hidden_repair_params `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py::test_lm5t_does_not_change_lm5s_pass1_instruction `
  -q
```

Expected: PASS.

- [ ] **Step 4: Run targeted LM5K/LM5R tests**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add mcp_server\tests\test_lm5k_worker_probe.py mcp_server\tests\test_lm5r_two_pass_publication_probe.py
git commit -m "test(lm5t): guard repair intent evidence boundaries"
```

---

## Task 6: Final Verification

**Files:**
- No source edits expected.

### Goal

Run deterministic gates only. Do not run the live LM5T probe and do not update curated evidence docs.

### Steps

- [ ] **Step 1: Run targeted LM5T tests**

```powershell
cd C:\Users\bring\.config\superpowers\worktrees\Rook\lm5t-repair-intent-evidence-v2
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 2: Run nearby probe gate**

```powershell
.\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5p_ollama_think_format_spike.py `
  -q
```

Expected: all tests pass.

- [ ] **Step 3: Run Python 3.10 compile gate**

```powershell
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  scripts\lm5r_two_pass_publication_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py `
  mcp_server\tests\test_lm5r_two_pass_publication_probe.py
```

Expected: no output and exit code 0.

- [ ] **Step 4: Check scope**

```powershell
git diff --name-only origin/main..HEAD
```

Expected exactly:

```text
docs/superpowers/plans/2026-07-05-lm5t-repair-intent-evidence-v2.md
docs/superpowers/specs/2026-07-05-lm5t-repair-intent-evidence-v2-design.md
mcp_server/tests/test_lm5k_worker_probe.py
mcp_server/tests/test_lm5r_two_pass_publication_probe.py
scripts/lm5k_worker_probe.py
scripts/lm5r_two_pass_publication_probe.py
```

- [ ] **Step 5: Check whitespace**

```powershell
git diff --check origin/main..HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 6: Check forbidden production drift**

```powershell
git diff --name-only origin/main..HEAD -- mcp_server\src
```

Expected: no output.

```powershell
git diff -U0 origin/main..HEAD -- scripts\lm5r_two_pass_publication_probe.py |
  rg "^[+-][^+-].*(PASS1_DECISION_INSTRUCTION_VERSION|_PASS1_DECISION_INSTRUCTION|_PASS2|STATUSES =|_single_kind_response_schema)"
```

Expected: no output. If this prints actual added or removed instruction,
formatter, schema-builder, or status lines, stop and review.

- [ ] **Step 7: Confirm raw artifacts are not tracked**

```powershell
git status --short --ignored probe_runs
git status --short --branch
```

Expected: `probe_runs/` may appear ignored as `!! probe_runs/`; it must not appear as tracked or staged.

- [ ] **Step 8: Do not make a gates-only commit**

If Task 6 produces no source changes, do not commit. Report the verification results for review and PR creation.

---

## Post-Merge Runbook

Run only after this deterministic PR lands and `main` is synced:

```powershell
cd C:\UDEV\Rook
.\mcp_server\.venv\Scripts\python.exe scripts\lm5r_two_pass_publication_probe.py `
  --scenario evidence_absent_like `
  --scenario evidence_present_v2_like `
  --attempts 5
```

No Anthropic key is needed for this canonical run.

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
whether PROBE_REPAIR_CODE / A = 42.0 appears in visible evidence or raw outputs
```

Do not commit `probe_runs/`. Write a curated evidence summary only after the run is reviewed.
