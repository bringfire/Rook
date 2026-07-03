# LM5N Bounded Evidence Push Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add paired LM5N probe scenarios that compare evidence-absent clarification against evidence-present action requests using one bounded `WorkerKnowledgePacket(kind="evidence")`.

**Architecture:** LM5N changes only the probe harness script and its tests. The runner moves from the historical active `lm5k_golden_repair_v2` scenario to two private scenario configs, derives the graph to the honest `post_verify_pre_bind` point with `max_steps=2`, and uses scenario-relative LM5F expectations. Evidence is a probe convention carried as an existing knowledge packet, not a production schema or planner behavior.

**Tech Stack:** Python 3.10-compatible script code, pytest, existing LM5A-I worker artifacts, existing offline `run_current_step_stream` fixture path.

---

## File Structure

Modify:

- `scripts/lm5k_worker_probe.py`
  - Add private `_ProbeScenarioConfig` and `_SCENARIOS`.
  - Add `--scenario evidence_absent|evidence_present`, defaulting to `evidence_present` for compatibility.
  - Change derived fixture state to `max_steps=2`, with repair ready and no execution params.
  - Build knowledge packets from scenario config: gotcha only for absent, gotcha plus one evidence packet for present.
  - Build LM5F expectations from scenario config.
  - Write manifest scenario identity from scenario config.

- `mcp_server/tests/test_lm5k_worker_probe.py`
  - Update scenario identity tests.
  - Update graph-state and rendered-context tests for `post_verify_pre_bind`.
  - Add evidence packet boundedness/provenance tests.
  - Add paired offline probe tests for evidence-absent and evidence-present expectations.
  - Preserve raw/fenced/unavailable/positive-attempt tests.

Do not modify:

- `mcp_server/src/**`
- `docs/superpowers/probes/**`
- prompt text or adapter code
- response loader/parser strictness
- model transport
- production planner/compiler/runtime dispatch

---

## Pre-Implementation Gate

**Files:**
- Inspect: repository state

- [ ] **Step 1: Confirm branch and cleanliness**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git status --short --branch
git diff --name-status main..HEAD
```

Expected branch:

```text
## codex/lm5n-bounded-evidence-push
```

Expected diff before implementation:

```text
A       docs/superpowers/specs/2026-07-03-lm5n-bounded-evidence-push-design.md
A       docs/superpowers/plans/2026-07-03-lm5n-bounded-evidence-push.md
```

If `git status --short` shows unrelated tracked changes, stop and report them.

---

## Task 1: Scenario Config and CLI Selection

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Replace the old scenario identity test with config tests**

In `mcp_server/tests/test_lm5k_worker_probe.py`, replace `test_scenario_identity_constants()` with:

```python
def test_scenario_configs_are_source_of_truth() -> None:
    assert PROBE.SCENARIO_WORKFLOW_ID == "lm5k_first_probe"
    assert set(PROBE._SCENARIOS) == {"evidence_absent", "evidence_present"}

    absent = PROBE._SCENARIOS["evidence_absent"]
    assert absent.cli_name == "evidence_absent"
    assert absent.scenario_id == "lm5n_repair_evidence_absent"
    assert absent.scenario_version == "v3"
    assert absent.state == "post_verify_pre_bind"
    assert absent.include_evidence_packet is False
    assert absent.expected_disposition == "clarification_needed"
    assert absent.expected_response_kind == "clarification_request"
    assert absent.expected_action_id is None
    assert absent.expected_attempt_valid is True

    present = PROBE._SCENARIOS["evidence_present"]
    assert present.cli_name == "evidence_present"
    assert present.scenario_id == "lm5n_repair_evidence_present"
    assert present.scenario_version == "v3"
    assert present.state == "post_verify_pre_bind"
    assert present.include_evidence_packet is True
    assert present.expected_disposition == "candidate_action_request"
    assert present.expected_response_kind == "action_request"
    assert present.expected_action_id == "draft_repair_params"
    assert present.expected_attempt_valid is True

    assert "lm5k_golden_repair_v2" not in {
        absent.scenario_id,
        present.scenario_id,
    }


def test_scenario_config_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="unknown probe scenario"):
        PROBE._scenario_config("lm5k_golden_repair_v2")
```

This retires the old active scenario path. Historical evidence remains in the curated doc, not in the runner.

- [ ] **Step 2: Extend the test `_args` helper with a scenario field**

In `_args`, add `"scenario": "evidence_present"`:

```python
def _args(tmp_path, **overrides):
    values = {
        "local": "ollama_chat/fake:1", "cheap": None, "ceiling": None,
        "skip": ["cheap", "ceiling"], "attempts": 3,
        "capture_raw": False, "run_dir": str(tmp_path),
        "scenario": "evidence_present",
    }
    values.update(overrides)
    return argparse.Namespace(**values)
```

- [ ] **Step 3: Add a CLI parsing test for `--scenario`**

Add this test near `test_attempts_must_be_positive`:

```python
def test_main_rejects_legacy_scenario(monkeypatch) -> None:
    called = []

    def fake_run_probe(args):
        called.append(args)
        return Path("unused")

    monkeypatch.setattr(PROBE, "run_probe", fake_run_probe)
    with pytest.raises(SystemExit):
        PROBE.main(["--scenario", "lm5k_golden_repair_v2"])
    assert called == []


def test_main_accepts_lm5n_scenarios(monkeypatch) -> None:
    seen = []

    def fake_run_probe(args):
        seen.append(args.scenario)
        return Path("unused")

    monkeypatch.setattr(PROBE, "run_probe", fake_run_probe)
    assert PROBE.main(["--scenario", "evidence_absent"]) == 0
    assert PROBE.main(["--scenario", "evidence_present"]) == 0
    assert seen == ["evidence_absent", "evidence_present"]
```

Make sure `Path` is already imported at the top of the test file. It is.

- [ ] **Step 4: Run RED tests for scenario config**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py -q
```

Expected: FAIL.

Expected failures include:

```text
AttributeError: module 'lm5k_worker_probe' has no attribute '_SCENARIOS'
AttributeError: module 'lm5k_worker_probe' has no attribute '_scenario_config'
```

Do not commit after the RED step.

- [ ] **Step 5: Implement private scenario config**

In `scripts/lm5k_worker_probe.py`, add `dataclass` to the imports:

```python
from dataclasses import dataclass
```

Replace the old active scenario constants:

```python
# Scenario identity (spec section 5). The workflow contract is unchanged
# since rounds 1/1b; what changed in LM5L is the probe scenario STATE
# (fresh compiled graph -> coherent post-verify repair state), so the
# scenario id/version move to v2 while workflow_id stays. Any scenario
# change is a new experiment under the comparison-key doctrine.
SCENARIO_VERSION = "v2"
SCENARIO_ID = f"lm5k_golden_repair_{SCENARIO_VERSION}"
SCENARIO_STATE = "post_verify_needs_repair"
```

with:

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


_SCENARIOS = {
    "evidence_absent": _ProbeScenarioConfig(
        cli_name="evidence_absent",
        scenario_id="lm5n_repair_evidence_absent",
        scenario_version="v3",
        state="post_verify_pre_bind",
        include_evidence_packet=False,
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
        include_evidence_packet=True,
        expected_disposition="candidate_action_request",
        expected_response_kind="action_request",
        expected_action_id="draft_repair_params",
        expected_attempt_valid=True,
    ),
}


def _scenario_config(name: str) -> _ProbeScenarioConfig:
    try:
        return _SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"unknown probe scenario: {name}") from exc
```

- [ ] **Step 6: Add CLI argument**

In `main`, add this parser argument before `--capture-raw`:

```python
    parser.add_argument(
        "--scenario",
        choices=tuple(_SCENARIOS),
        default="evidence_present",
        help=(
            "probe scenario; live evidence runs should pass this explicitly"
        ),
    )
```

Do not add a legacy `lm5k_golden_repair_v2` choice.

- [ ] **Step 7: Run scenario config tests**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_scenario_configs_are_source_of_truth tests\test_lm5k_worker_probe.py::test_scenario_config_rejects_unknown_name tests\test_lm5k_worker_probe.py::test_main_rejects_legacy_scenario tests\test_lm5k_worker_probe.py::test_main_accepts_lm5n_scenarios -q
```

Expected:

```text
4 passed
```

- [ ] **Step 8: Commit Task 1**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5n): add paired probe scenario config"
```

---

## Task 2: Pre-Bind Graph Derivation and Guard

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Update the derived graph state test**

Replace `test_derived_graph_state_is_coherent_post_verify()` with:

```python
def test_derived_graph_state_is_post_verify_pre_bind() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    assert result.stop_reason == "max_steps_reached"
    assert result.steps_attempted == 2
    assert [r.execution_kind for r in result.records] == [
        "producer", "verifier",
    ]
    assert [r.accepted_node_id for r in result.records] == [
        "create_script", "verify_create",
    ]
    assert result.records[0].ran is True
    graph = result.final_graph
    assert graph.nodes["create_script"].evidence is not None
    assert result.records[1].verifier_outcome_status == "needs_repair"

    repair = graph.nodes["repair_same_component"]
    assert repair.status == "ready"
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    assert EXECUTION_PARAMS_KEY not in repair.metadata
    assert graph.memory.facts["component_guid"] == PROBE.PROBE_COMPONENT_GUID
    assert (
        graph.memory.facts["repair_anchor"]["component_guid"]
        == PROBE.PROBE_COMPONENT_GUID
    )
```

- [ ] **Step 2: Update guard mutation tests for missing execution params**

Replace `test_graph_state_guard_message_params_missing()` with:

```python
def test_graph_state_guard_message_params_present_too_early() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.nodes["repair_same_component"].metadata[
        EXECUTION_PARAMS_KEY
    ] = {"code": PROBE.PROBE_REPAIR_CODE, "mode": "body"}
    with pytest.raises(
        RuntimeError, match="execution params unexpectedly present"
    ):
        PROBE._require_coherent_graph_state(scaffold, result)
```

- [ ] **Step 3: Replace the old pre-bind sequence negative test**

Replace `test_graph_state_guard_message_pre_bind_sequence()` with:

```python
def test_graph_state_guard_rejects_post_bind_sequence() -> None:
    import asyncio

    from rook.agent.plan_graph_current_step_stream import (
        run_current_step_stream,
    )
    from rook.agent.plan_graph_workflow_contract import (
        compile_workflow_contract,
    )

    scaffold = compile_workflow_contract(PROBE._probe_contract())
    result = asyncio.run(
        run_current_step_stream(
            scaffold.graph,
            scaffold.provider,
            max_steps=3,
            runner=PROBE._OfflineCreateRunner(),
        )
    )
    with pytest.raises(RuntimeError, match="unexpected step sequence"):
        PROBE._require_coherent_graph_state(scaffold, result)
```

- [ ] **Step 4: Update the rendered context shape test**

In `test_probe_context_envelope_is_world_state_coherent()`, change the assertions to:

```python
    assert (
        "repair_same_component" in context["current_graph"]["ready_node_ids"]
    )
    node = context["current_node"]
    assert node["node_id"] == "repair_same_component"
    assert node["status"] == "ready"
    assert node["has_execution_params"] is False
    assert "repair_anchor" in node["memory_keys"]
    assert "component_guid" in node["memory_keys"]

    history = context["history"]
    assert history["current_step_count"] == 2
    assert [
        step["execution_kind"] for step in history["recent_steps"]
    ] == ["producer", "verifier"]
    assert [
        step["accepted_node_id"] for step in history["recent_steps"]
    ] == ["create_script", "verify_create"]
```

Keep the allowed action assertion at the end of the test.

- [ ] **Step 5: Run RED tests for the derivation point**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_derived_graph_state_is_post_verify_pre_bind tests\test_lm5k_worker_probe.py::test_graph_state_guard_message_params_present_too_early tests\test_lm5k_worker_probe.py::test_graph_state_guard_rejects_post_bind_sequence tests\test_lm5k_worker_probe.py::test_probe_context_envelope_is_world_state_coherent -q
```

Expected: FAIL.

Expected failures include:

```text
assert 3 == 2
assert ['producer', 'verifier', 'bind'] == ['producer', 'verifier']
assert node["has_execution_params"] is False
```

Do not commit after the RED step.

- [ ] **Step 6: Change `derive_probe_graph_state` to `max_steps=2`**

In `derive_probe_graph_state`, update the docstring to:

```python
def derive_probe_graph_state():
    """Advance the compiled scenario to post-verify / pre-bind state.

    Runs the existing offline stream driver for exactly two steps: create
    producer, then verify_create verifier. This leaves repair_same_component
    ready, with receipt-derived memory facts but without already-bound repair
    execution params. NOT a stream runner in the probe: no live provider, no
    tool dispatch, no model."""
```

Change the call to:

```python
            max_steps=2,
```

Update `_OfflineCreateRunner`'s docstring from the `max_steps=3` wording to:

```python
    Only create_script may execute: with max_steps=2 the stream stops after
    verify_create, so being asked to run any other producer node is a fixture
    bug."""
```

- [ ] **Step 7: Update the graph-state guard for pre-bind**

In `_require_coherent_graph_state`, keep the import of `EXECUTION_PARAMS_KEY` and update the checks to:

```python
    kinds = [record.execution_kind for record in stream_result.records]
    _invariant(
        kinds == ["producer", "verifier"],
        f"unexpected step sequence: {kinds}",
    )
```

Replace the execution-params presence check with:

```python
    _invariant(
        EXECUTION_PARAMS_KEY not in repair.metadata,
        "execution params unexpectedly present on repair node",
    )
```

Keep the memory fact checks. Keep the explicit missing `create_script` and `repair_same_component` node checks.

- [ ] **Step 8: Update `build_probe_context` docstring**

Replace the `build_probe_context` docstring with:

```python
    """LM5N scenario: post-verify / pre-bind repair state.

    The compiled repair workflow is advanced through the real offline stream
    for create + verify only. All world-state is derived: the create receipt's
    projection writes memory facts and verify_create readies the repair node.
    The repair bind step has not run, so no repair execution params exist yet.
    The knowledge packets and allowed action stay hand-declared planner inputs.
    """
```

- [ ] **Step 9: Run derivation tests**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_derived_graph_state_is_post_verify_pre_bind tests\test_lm5k_worker_probe.py::test_graph_state_guard_message_params_present_too_early tests\test_lm5k_worker_probe.py::test_graph_state_guard_rejects_post_bind_sequence tests\test_lm5k_worker_probe.py::test_probe_context_envelope_is_world_state_coherent -q
```

Expected:

```text
4 passed
```

- [ ] **Step 10: Commit Task 2**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5n): derive probe state before repair binding"
```

---

## Task 3: Evidence Packet Construction

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Add evidence packet tests**

Add these tests after `test_graph_state_guard_accepts_derived_state()`:

```python
def test_evidence_absent_knowledge_has_only_script_body_gotcha() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_absent"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == ["script_body_gotcha"]
    assert [packet.kind for packet in packets] == ["gotcha"]


def test_evidence_present_knowledge_adds_exactly_one_evidence_packet() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packets = PROBE._knowledge_packets_for_scenario(
        PROBE._SCENARIOS["evidence_present"], result.final_graph
    )
    assert [packet.packet_id for packet in packets] == [
        "script_body_gotcha",
        "lm5n_repair_evidence",
    ]
    assert [packet.kind for packet in packets] == ["gotcha", "evidence"]


def test_evidence_packet_fields_are_bounded_and_provenance_tagged() -> None:
    _scaffold, result = PROBE.derive_probe_graph_state()
    packet = PROBE._repair_evidence_packet(result.final_graph)

    assert packet.packet_id == "lm5n_repair_evidence"
    assert packet.kind == "evidence"
    assert packet.title == "Receipt-derived repair evidence"
    assert packet.content["source"] == "probe_fixture"
    assert packet.content["trust"] == "high"
    assert packet.content["state"] == "post_verify_pre_bind"

    fields = packet.content["fields"]
    assert set(fields) == {
        "source_node_id",
        "verifier_node_id",
        "producer_status",
        "verification_status",
        "target_error_count",
        "component_guid",
        "repair_anchor",
        "language",
        "current_code",
        "recommended_mode",
    }
    for name, item in fields.items():
        assert "value" in item, name
        assert isinstance(item["source"], str) and item["source"], name

    assert fields["source_node_id"] == {
        "value": "create_script",
        "source": "workflow_record",
    }
    assert fields["verifier_node_id"] == {
        "value": "verify_create",
        "source": "workflow_record",
    }
    assert fields["producer_status"]["value"] == "created_with_errors"
    assert fields["verification_status"]["value"] == "failed"
    assert fields["target_error_count"]["value"] == 1
    assert fields["component_guid"]["value"] == PROBE.PROBE_COMPONENT_GUID
    assert (
        fields["repair_anchor"]["value"]["component_guid"]
        == PROBE.PROBE_COMPONENT_GUID
    )
    assert fields["language"]["value"] == "csharp"
    assert fields["current_code"]["value"] == "A = DefinitelyMissingSymbol;"
    assert len(fields["current_code"]["value"]) <= 500
    assert fields["current_code"]["truncated"] is False
    assert fields["current_code"]["max_chars"] == 500
    assert fields["recommended_mode"] == {
        "value": "body",
        "source": "script_body_gotcha",
        "derivation": "existing worker-visible gotcha convention",
    }


def test_current_code_evidence_reads_derived_create_params_not_repair_literal() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    _scaffold, result = PROBE.derive_probe_graph_state()
    params = result.final_graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    params["code"] = "A = MutatedFromDerivedGraph;"

    packet = PROBE._repair_evidence_packet(result.final_graph)
    fields = packet.content["fields"]
    assert fields["current_code"]["value"] == "A = MutatedFromDerivedGraph;"
    assert fields["current_code"]["value"] != PROBE.PROBE_REPAIR_CODE
```

This explicitly carries the review note: `current_code` must be read from the derived `create_script` execution params, not from the repair literal.

- [ ] **Step 2: Run RED evidence packet tests**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_evidence_absent_knowledge_has_only_script_body_gotcha tests\test_lm5k_worker_probe.py::test_evidence_present_knowledge_adds_exactly_one_evidence_packet tests\test_lm5k_worker_probe.py::test_evidence_packet_fields_are_bounded_and_provenance_tagged tests\test_lm5k_worker_probe.py::test_current_code_evidence_reads_derived_create_params_not_repair_literal -q
```

Expected: FAIL.

Expected failures include:

```text
AttributeError: module 'lm5k_worker_probe' has no attribute '_knowledge_packets_for_scenario'
AttributeError: module 'lm5k_worker_probe' has no attribute '_repair_evidence_packet'
```

Do not commit after the RED step.

- [ ] **Step 3: Add evidence constants and helpers**

In `scripts/lm5k_worker_probe.py`, add below `PROBE_REPAIR_CODE`:

```python
EVIDENCE_PACKET_ID = "lm5n_repair_evidence"
EVIDENCE_CURRENT_CODE_MAX_CHARS = 500
```

Add these helpers below `_require_probe_context_shape`:

```python
def _script_body_gotcha_packet():
    from rook.agent.local_worker_turn_context import WorkerKnowledgePacket

    return WorkerKnowledgePacket(
        packet_id="script_body_gotcha",
        kind="gotcha",
        title="C# script components use body-style code",
        content={"source": "probe fixture", "trust": "high"},
    )


def _bounded_current_code(code: Any) -> dict:
    _invariant(isinstance(code, str) and code, "current code missing")
    truncated = len(code) > EVIDENCE_CURRENT_CODE_MAX_CHARS
    return {
        "value": code[:EVIDENCE_CURRENT_CODE_MAX_CHARS],
        "source": "create_script.initial_execution_params.code",
        "truncated": truncated,
        "max_chars": EVIDENCE_CURRENT_CODE_MAX_CHARS,
    }


def _require_receipt_mapping(graph) -> Mapping[str, Any]:
    create = graph.nodes["create_script"]
    evidence = create.evidence
    receipt = getattr(evidence, "receipt", None) if evidence is not None else None
    _invariant(isinstance(receipt, Mapping), "create receipt missing")
    return receipt


def _require_create_execution_params(graph) -> Mapping[str, Any]:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    create = graph.nodes["create_script"]
    params = create.metadata.get(EXECUTION_PARAMS_KEY)
    _invariant(isinstance(params, Mapping), "create execution params missing")
    return params


def _repair_evidence_packet(graph):
    from rook.agent.local_worker_turn_context import WorkerKnowledgePacket

    # LM5N probe convention only: this is not the final evidence schema.
    receipt = _require_receipt_mapping(graph)
    params = _require_create_execution_params(graph)
    verification = receipt.get("verification")
    _invariant(isinstance(verification, Mapping), "verification receipt missing")
    facts = graph.memory.facts
    repair_anchor = facts.get("repair_anchor")
    _invariant(isinstance(repair_anchor, Mapping), "repair anchor missing")

    content = {
        "source": "probe_fixture",
        "trust": "high",
        "state": "post_verify_pre_bind",
        "fields": {
            "source_node_id": {
                "value": "create_script",
                "source": "workflow_record",
            },
            "verifier_node_id": {
                "value": "verify_create",
                "source": "workflow_record",
            },
            "producer_status": {
                "value": receipt.get("artifact_status"),
                "source": (
                    "create_script.receipt.script_receipt.artifact_status"
                ),
            },
            "verification_status": {
                "value": verification.get("status"),
                "source": (
                    "create_script.receipt.script_receipt.verification.status"
                ),
            },
            "target_error_count": {
                "value": verification.get("target_error_count"),
                "source": (
                    "create_script.receipt.script_receipt.verification."
                    "target_error_count"
                ),
            },
            "component_guid": {
                "value": facts.get("component_guid"),
                "source": "graph.memory.facts.component_guid",
            },
            "repair_anchor": {
                "value": dict(repair_anchor),
                "source": "graph.memory.facts.repair_anchor",
            },
            "language": {
                "value": receipt.get("language"),
                "source": "create_script.receipt.script_receipt.language",
            },
            "current_code": _bounded_current_code(params.get("code")),
            "recommended_mode": {
                "value": "body",
                "source": "script_body_gotcha",
                "derivation": "existing worker-visible gotcha convention",
            },
        },
    }
    return WorkerKnowledgePacket(
        packet_id=EVIDENCE_PACKET_ID,
        kind="evidence",
        title="Receipt-derived repair evidence",
        content=content,
    )


def _knowledge_packets_for_scenario(
    scenario: _ProbeScenarioConfig,
    graph,
) -> tuple:
    packets = [_script_body_gotcha_packet()]
    if scenario.include_evidence_packet:
        packets.append(_repair_evidence_packet(graph))
    return tuple(packets)
```

The `recommended_mode` exception remains visible and provenance-tagged from the gotcha convention, not the receipt.

- [ ] **Step 4: Run evidence packet tests**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_evidence_absent_knowledge_has_only_script_body_gotcha tests\test_lm5k_worker_probe.py::test_evidence_present_knowledge_adds_exactly_one_evidence_packet tests\test_lm5k_worker_probe.py::test_evidence_packet_fields_are_bounded_and_provenance_tagged tests\test_lm5k_worker_probe.py::test_current_code_evidence_reads_derived_create_params_not_repair_literal -q
```

Expected:

```text
4 passed
```

- [ ] **Step 5: Commit Task 3**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5n): add bounded repair evidence packet"
```

---

## Task 4: Wire Scenario Config Through Context, Evaluation, and Manifest

**Files:**
- Modify: `scripts/lm5k_worker_probe.py`
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`

- [ ] **Step 1: Add paired expectation tests**

Add these tests near the offline probe e2e tests:

```python
class _FakeScenarioAwareTransport:
    """Clarifies without evidence, acts with the bounded evidence packet."""

    def __init__(self, resolution):
        self.last_call_info = None
        self.last_raw_output = None

    def send(self, prompt_artifact):
        self.last_call_info = _FakeCallInfo()
        envelope = json.loads(prompt_artifact["messages"][1]["content"])
        context = envelope["context"]
        packet_ids = [packet["packet_id"] for packet in context["knowledge"]]
        if "lm5n_repair_evidence" not in packet_ids:
            raw = json.dumps(
                {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "clarification_request",
                    "question": "Please provide the repair evidence.",
                    "rationale": (
                        "The visible context does not include enough evidence "
                        "to author the action input."
                    ),
                }
            )
        else:
            action_id = context["allowed_actions"][0]["action_id"]
            evidence = next(
                packet for packet in context["knowledge"]
                if packet["packet_id"] == "lm5n_repair_evidence"
            )
            fields = evidence["content"]["fields"]
            raw = json.dumps(
                {
                    "schema": "rook.local_worker_turn_response:v1",
                    "kind": "action_request",
                    "action_id": action_id,
                    "rationale": "Use bounded repair evidence.",
                    "input": {
                        "code": fields["current_code"]["value"],
                        "mode": fields["recommended_mode"]["value"],
                    },
                }
            )
        self.last_raw_output = raw
        return raw
```

Then add:

```python
def test_offline_probe_evidence_absent_expects_clarification(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, scenario="evidence_absent", attempts=2),
        transport_factory=_FakeScenarioAwareTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5n_repair_evidence_absent",
        "scenario_version": "v3",
        "state": "post_verify_pre_bind",
    }
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 2
    assert local["spine_passed"] == 2
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["adapter_status"] == "response_loaded"
    assert first["disposition"] == "clarification_needed"
    assert first["evaluation_passed"] is True


def test_offline_probe_evidence_present_expects_action(tmp_path) -> None:
    run_dir = PROBE.run_probe(
        _args(tmp_path, scenario="evidence_present", attempts=2),
        transport_factory=_FakeScenarioAwareTransport,
    )
    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5n_repair_evidence_present",
        "scenario_version": "v3",
        "state": "post_verify_pre_bind",
    }
    local = next(p for p in manifest["panel"] if p["slot"] == "local")
    assert local["status"] == "ran"
    assert local["strict_loadable"] == 2
    assert local["spine_passed"] == 2
    lines = (run_dir / "attempts.jsonl").read_text().strip().splitlines()
    first = json.loads(lines[0])
    assert first["adapter_status"] == "response_loaded"
    assert first["disposition"] == "candidate_action_request"
    assert first["evaluation_passed"] is True
```

These tests do not add explicit `action_id is None` enforcement for evidence-absent. LM5F treats `None` expectation fields as not checked; the clarification disposition and response kind carry the "no action expected" proof.

- [ ] **Step 2: Run RED paired expectation tests**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_offline_probe_evidence_absent_expects_clarification tests\test_lm5k_worker_probe.py::test_offline_probe_evidence_present_expects_action -q
```

Expected: FAIL.

Expected failures include the manifest still reporting:

```text
'scenario_id': 'lm5k_golden_repair_v2'
'state': 'post_verify_needs_repair'
```

or the evidence-absent run reporting `spine_passed == 0`.

Do not commit after the RED step.

- [ ] **Step 3: Wire scenario into `build_probe_context`**

Change the function signature:

```python
def build_probe_context(
    scenario: _ProbeScenarioConfig | None = None,
):
```

At the start of the function, add:

```python
    scenario = scenario or _SCENARIOS["evidence_present"]
```

Replace the hand-written `knowledge=(WorkerKnowledgePacket(...),)` block with:

```python
        knowledge=_knowledge_packets_for_scenario(
            scenario, stream_result.final_graph
        ),
```

Remove the now-unused `WorkerKnowledgePacket` import from the `build_probe_context` import block. Keep `WorkerAllowedAction` and `build_local_worker_turn_context`.

- [ ] **Step 4: Wire scenario into `run_candidate`**

Change the signature:

```python
def run_candidate(
    resolution: Mapping[str, Any],
    attempts: int,
    run_dir: Path,
    capture_raw: bool,
    scenario: _ProbeScenarioConfig,
    transport_factory=None,
) -> dict:
```

Change context construction:

```python
    context = build_probe_context(scenario)
```

Change `LocalWorkerScenarioExpectation(...)` to:

```python
                LocalWorkerScenarioExpectation(
                    scenario_id=scenario.scenario_id,
                    category="live_probe",
                    expected_status="completed",
                    expected_disposition=scenario.expected_disposition,
                    expected_attempt_valid=scenario.expected_attempt_valid,
                    expected_action_id=scenario.expected_action_id,
                    expected_response_kind=scenario.expected_response_kind,
                    expected_workflow_id=context.workflow.workflow_id,
                    expected_contract_fingerprint=(
                        context.workflow.contract_fingerprint
                    ),
                ),
```

This is the only place scenario-relative spine expectations are applied.

- [ ] **Step 5: Wire scenario into `build_manifest`**

Change the signature:

```python
def build_manifest(
    run_id: str,
    panel: list,
    attempts: int,
    capture_raw: bool,
    scenario: _ProbeScenarioConfig,
) -> dict:
```

Replace the scenario block with:

```python
        "scenario": {
            "workflow_id": SCENARIO_WORKFLOW_ID,
            "scenario_id": scenario.scenario_id,
            "scenario_version": scenario.scenario_version,
            "state": scenario.state,
        },
```

- [ ] **Step 6: Wire scenario into `run_probe`**

After the attempts validation in `run_probe`, add:

```python
    scenario = _scenario_config(args.scenario)
```

Pass it into `run_candidate`:

```python
        summary = run_candidate(
            resolution, args.attempts, run_dir, args.capture_raw,
            scenario,
            transport_factory=transport_factory,
        )
```

Pass it into `build_manifest`:

```python
    manifest = build_manifest(
        run_id, panel, args.attempts, args.capture_raw, scenario
    )
```

- [ ] **Step 7: Run paired expectation tests**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py::test_offline_probe_evidence_absent_expects_clarification tests\test_lm5k_worker_probe.py::test_offline_probe_evidence_present_expects_action -q
```

Expected:

```text
2 passed
```

- [ ] **Step 8: Commit Task 4**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5n): evaluate probe attempts by scenario"
```

---

## Task 5: Update Existing Probe Tests for LM5N Defaults and Visibility

**Files:**
- Modify: `mcp_server/tests/test_lm5k_worker_probe.py`
- Modify: `scripts/lm5k_worker_probe.py` only if a test reveals a small wiring mismatch

- [ ] **Step 1: Update the existing good transport test manifest assertion**

In `test_offline_probe_end_to_end_good_transport`, replace the manifest scenario assertion with:

```python
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5n_repair_evidence_present",
        "scenario_version": "v3",
        "state": "post_verify_pre_bind",
    }
```

Keep the `"scenario_workflow_id" not in manifest` assertion.

- [ ] **Step 2: Update the visibility boundary test for evidence scenarios**

Replace `test_probe_envelope_never_exposes_internal_values()` with:

```python
def test_evidence_absent_probe_envelope_does_not_expose_evidence_values() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context(PROBE._SCENARIOS["evidence_absent"])
    )
    rendered = json.dumps(payload)
    assert PROBE.PROBE_COMPONENT_GUID not in rendered
    assert "A = DefinitelyMissingSymbol;" not in rendered
    assert "lm5n_repair_evidence" not in rendered


def test_evidence_present_probe_envelope_exposes_only_bounded_evidence_values() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context(PROBE._SCENARIOS["evidence_present"])
    )
    rendered = json.dumps(payload)
    assert "lm5n_repair_evidence" in rendered
    assert PROBE.PROBE_COMPONENT_GUID in rendered
    assert "A = DefinitelyMissingSymbol;" in rendered
    assert PROBE.PROBE_REPAIR_CODE not in rendered
    assert "already-bound repair params" not in rendered
```

This re-derives the LM5L visibility test for LM5N: evidence-present exposes evidence values by design; evidence-absent still does not.

- [ ] **Step 3: Add a test that the repair node still has no hidden params in the rendered payload**

Add:

```python
def test_lm5n_rendered_current_node_has_no_execution_params() -> None:
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    for scenario in PROBE._SCENARIOS.values():
        payload = render_local_worker_turn_request_payload(
            PROBE.build_probe_context(scenario)
        )
        node = payload["context"]["current_node"]
        assert node["node_id"] == "repair_same_component"
        assert node["has_execution_params"] is False
```

- [ ] **Step 4: Run the full targeted probe test file**

Run from `mcp_server`:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py -q
```

Expected: PASS. The exact count will increase from the pre-LM5N count because this plan adds tests.

If the failure is only an assertion still expecting `lm5k_golden_repair_v2`, update that assertion to the scenario config value. If the failure is a production module import or a live/model call, stop and report it.

- [ ] **Step 5: Commit Task 5**

Run from repo root:

```powershell
cd C:\UDEV\Rook
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "test(lm5n): cover paired evidence probe scenarios"
```

---

## Task 6: Final Gates

**Files:**
- Verify: repo state and LM5N scope

- [ ] **Step 1: Run targeted LM5K probe tests**

Run:

```powershell
cd C:\UDEV\Rook\mcp_server
.\.venv\Scripts\python.exe -m pytest tests\test_lm5k_worker_probe.py -q
```

Expected: PASS. Record the exact count.

- [ ] **Step 2: Run Python 3.10 compile gate**

Run:

```powershell
cd C:\UDEV\Rook
py -3.10 -m py_compile `
  scripts\lm5k_worker_probe.py `
  mcp_server\tests\test_lm5k_worker_probe.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Run diff whitespace check**

Run:

```powershell
cd C:\UDEV\Rook
git diff --check main..HEAD
```

Expected: no output and exit code 0.

- [ ] **Step 4: Verify branch scope**

Run:

```powershell
cd C:\UDEV\Rook
git diff --name-status main..HEAD
```

Expected output:

```text
A       docs/superpowers/specs/2026-07-03-lm5n-bounded-evidence-push-design.md
A       docs/superpowers/plans/2026-07-03-lm5n-bounded-evidence-push.md
M       mcp_server/tests/test_lm5k_worker_probe.py
M       scripts/lm5k_worker_probe.py
```

There must be no `mcp_server/src/**` diff and no `docs/superpowers/probes/**` diff.

- [ ] **Step 5: Run static banned-scope scan**

Run:

```powershell
cd C:\UDEV\Rook
git diff --name-only main..HEAD | rg "^(mcp_server/src/|docs/superpowers/probes/|src/Rook|src/RookNative|src/RookBim)"
```

Expected: no output. Exit code 1 from `rg` is acceptable because it means no matches.

Run:

```powershell
git diff -U0 main..HEAD -- scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py |
  rg "load_local_worker_turn_response_payload|parser leniency|structured output|model-specific"
```

Expected: no output. Exit code 1 from `rg` is acceptable because it means no matches. Existing `json.loads` / `json.dumps` use in the probe script and tests is allowed; existing prompt-version assertions are allowed. LM5N must not touch parser leniency, response loading, structured-output leniency, or model-specific handling.

- [ ] **Step 6: Confirm no live probe artifacts were created by implementation tests**

Run:

```powershell
cd C:\UDEV\Rook
git status --short --ignored probe_runs
```

Expected: no tracked changes. Ignored `probe_runs/...` entries are acceptable only if a developer accidentally ran a probe; do not stage them.

- [ ] **Step 7: Commit final plan checklist update only if the executor marks checkboxes**

If the executor edits this plan to mark completed checkboxes, commit the plan checklist update:

```powershell
cd C:\UDEV\Rook
git add docs/superpowers/plans/2026-07-03-lm5n-bounded-evidence-push.md
git commit -m "docs(lm5n): mark bounded evidence push plan complete"
```

If the executor does not edit the plan checklist, no Task 6 commit is needed.

---

## Post-Merge Runbook

Do not run live probes inside the implementation PR.

After LM5N merges to `main`, run the paired evidence experiment from clean `main` with explicit scenario flags and the same model panel.

Evidence absent:

```powershell
cd C:\UDEV\Rook

.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_absent `
  --capture-raw `
  --local "ollama_chat/qwen3:14b" `
  --cheap "anthropic/claude-haiku-4-5-20251001" `
  --ceiling "anthropic/claude-sonnet-5"
```

Evidence present:

```powershell
cd C:\UDEV\Rook

.\mcp_server\.venv\Scripts\python.exe scripts\lm5k_worker_probe.py `
  --scenario evidence_present `
  --capture-raw `
  --local "ollama_chat/qwen3:14b" `
  --cheap "anthropic/claude-haiku-4-5-20251001" `
  --ceiling "anthropic/claude-sonnet-5"
```

If the shell lacks `ANTHROPIC_API_KEY`, load it from `mcp_server\.env` into the current process without printing the secret before running. Do not commit raw `probe_runs/` artifacts.

The curated evidence summary should treat the two run directories as one paired round-4 experiment. Manual semantic review can inspect bounded action input excerpts, but LM5N does not add automated semantic repair scoring.
