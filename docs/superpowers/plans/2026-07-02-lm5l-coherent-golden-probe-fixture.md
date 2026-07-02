# LM5L Coherent Golden Probe Fixture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the world-state-incoherent golden fixture in `scripts/lm5k_worker_probe.py` with one derived through the real offline advancement path (`run_current_step_stream`, `max_steps=3`), guarded by fail-fast coherence tripwires and proven by two-layer tests.

**Architecture:** A `derive_probe_graph_state()` helper compiles the unchanged workflow contract and advances it three steps (create-producer → verify-verifier → bind) through the existing offline stream driver with a deterministic runner — the LM4W chain-guard pattern. `build_probe_context()` consumes the derived graph plus its real `records`/`supply_records`, runs two split guards (`_require_coherent_graph_state` for derived world-state, `_require_probe_context_shape` for caller-declared affordances), and deletes all hand-injected memory facts. Scenario identity is versioned to `lm5k_golden_repair_v2`.

**Tech Stack:** Python (3.10-compatible syntax), pytest, existing Rook modules only (no new dependencies).

**Spec:** `docs/superpowers/specs/2026-07-02-lm5l-coherent-golden-probe-fixture-design.md` (approved 2026-07-02)

## Global Constraints

- Worktree `C:/UDEV/Rook-lm5l`, branch `codex/lm5l-coherent-probe-fixture`, cut from `main` at `87886a40`. All commands below run in this worktree.
- Only two source files may change: `scripts/lm5k_worker_probe.py` and `mcp_server/tests/test_lm5k_worker_probe.py` (plus this plan, the spec, and the SDD ledger under `.superpowers/sdd/`). LM5A–J modules under `mcp_server/src/rook/agent/local_worker_*` are FROZEN. No `plan_graph*` module changes.
- All code must be Python 3.10-compatible (the probe has `from __future__ import annotations`; no `match`, no 3.12-only syntax). Gate: `py -3.10 -m py_compile` on both touched files.
- No live provider, no Rhino/GH, no tool dispatch, no model call anywhere in the fixture path or tests. Everything added here is deterministic and offline.
- Guard failure messages MUST use the exact prefix `LM5L coherent fixture invariant failed: ` (spec §4.2).
- Model-visible vs internal facts: tests on the rendered envelope assert ONLY `has_execution_params is True` and `memory_keys` contents — never param payloads or memory fact values (spec §3.5).
- Test runner: `cd C:/UDEV/Rook-lm5l/mcp_server` then `.venv/Scripts/python.exe -m pytest ...`. The venv is created in Task 1 and must import `rook` from THIS worktree.
- Commit after every task; commit messages end with the Claude Fable co-author trailer.

---

### Task 1: Worktree venv + scenario identity (constants, expectation, manifest block)

**Files:**
- Modify: `scripts/lm5k_worker_probe.py` (constants near line 48; expectation in `run_candidate` ~line 312; manifest in `build_manifest` ~line 422)
- Test: `mcp_server/tests/test_lm5k_worker_probe.py`

**Interfaces:**
- Produces: module constants `SCENARIO_ID = "lm5k_golden_repair_v2"`, `SCENARIO_VERSION = "v2"`, `SCENARIO_STATE = "post_verify_needs_repair"` (later tasks and the round-2 evidence doc rely on these exact values); manifest key `"scenario"` (dict) replacing `"scenario_workflow_id"` (str).

- [ ] **Step 1: Create the worktree venv and verify it imports rook from the worktree**

Run (PowerShell, from `C:/UDEV/Rook-lm5l/mcp_server`):

```powershell
uv venv .venv --python 3.12
uv pip install -e . --python .venv/Scripts/python.exe
.venv/Scripts/python.exe -c "import rook; print(rook.__file__)"
```

Expected: the printed path starts with `C:\UDEV\Rook-lm5l\mcp_server\src\rook` (NOT `C:\UDEV\Rook\...`). If it prints the main checkout's path, stop and fix before proceeding.

- [ ] **Step 2: Baseline — run the existing probe tests, all 13 must pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py -q`
Expected: `13 passed`

- [ ] **Step 3: Write the failing tests (scenario constants + manifest scenario block)**

Append to `mcp_server/tests/test_lm5k_worker_probe.py`:

```python
def test_scenario_identity_constants() -> None:
    assert PROBE.SCENARIO_WORKFLOW_ID == "lm5k_first_probe"
    assert PROBE.SCENARIO_ID == "lm5k_golden_repair_v2"
    assert PROBE.SCENARIO_VERSION == "v2"
    assert PROBE.SCENARIO_STATE == "post_verify_needs_repair"
```

And extend `test_offline_probe_end_to_end_good_transport` — after the line `assert manifest["prompt_text_version"] == "lm5j.prompt_text:v1"`, add:

```python
    # scenario identity: structured block, versioned (spec section 5);
    # the bare scenario_workflow_id string is replaced, not kept alongside
    assert manifest["scenario"] == {
        "workflow_id": "lm5k_first_probe",
        "scenario_id": "lm5k_golden_repair_v2",
        "scenario_version": "v2",
        "state": "post_verify_needs_repair",
    }
    assert "scenario_workflow_id" not in manifest
```

- [ ] **Step 4: Run the new tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py::test_scenario_identity_constants tests/test_lm5k_worker_probe.py::test_offline_probe_end_to_end_good_transport -v`
Expected: FAIL — `AttributeError: ... has no attribute 'SCENARIO_ID'` and `KeyError: 'scenario'`.

- [ ] **Step 5: Implement — constants, expectation scenario_id, manifest block**

In `scripts/lm5k_worker_probe.py`, directly below `SCENARIO_WORKFLOW_ID = "lm5k_first_probe"`, add:

```python
# Scenario identity (spec section 5). The workflow contract is unchanged
# since rounds 1/1b; what changed in LM5L is the probe scenario STATE
# (fresh compiled graph -> coherent post-verify repair state), so the
# scenario id/version move to v2 while workflow_id stays. Any scenario
# change is a new experiment under the comparison-key doctrine.
SCENARIO_ID = "lm5k_golden_repair_v2"
SCENARIO_VERSION = "v2"
SCENARIO_STATE = "post_verify_needs_repair"
```

In `run_candidate`, change the expectation's scenario id:

```python
                LocalWorkerScenarioExpectation(
                    scenario_id=SCENARIO_ID,
                    category="live_probe",
```

(replacing `scenario_id="lm5k_first_probe_golden",`).

In `build_manifest`, replace the line `"scenario_workflow_id": SCENARIO_WORKFLOW_ID,` with:

```python
        "scenario": {
            "workflow_id": SCENARIO_WORKFLOW_ID,
            "scenario_id": SCENARIO_ID,
            "scenario_version": SCENARIO_VERSION,
            "state": SCENARIO_STATE,
        },
```

- [ ] **Step 6: Run the full probe test file**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py -q`
Expected: `14 passed`

- [ ] **Step 7: Commit**

```bash
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5l): versioned scenario identity — lm5k_golden_repair_v2 constants, expectation, manifest block"
```

---

### Task 2: `derive_probe_graph_state()` — offline-stream derivation + Layer-1 tests

**Files:**
- Modify: `scripts/lm5k_worker_probe.py` (extract `_probe_contract()` from `build_probe_context`; add `PROBE_COMPONENT_GUID`, `_wrapped_failure_create_raw()`, `_OfflineCreateRunner`, `derive_probe_graph_state()`; `build_probe_context` NOT yet rewired — that is Task 4)
- Test: `mcp_server/tests/test_lm5k_worker_probe.py`

**Interfaces:**
- Consumes: existing Rook APIs — `compile_workflow_contract` (from `rook.agent.plan_graph_workflow_contract`), `run_current_step_stream` (from `rook.agent.plan_graph_current_step_stream`; signature `run_current_step_stream(initial_graph, envelope_source, *, max_steps, runner)` returning `CurrentStepStreamResult(final_graph, records, supply_records, stop_reason, steps_attempted)`), `apply_producer_result` (from `rook.learning.plan_graph_runner`), `LiveProducerResult` and `EXECUTION_PARAMS_KEY` (from `rook.agent.plan_graph_live`).
- Produces: `PROBE_COMPONENT_GUID: str`; `_probe_contract() -> RookWorkflowContract`; `_OfflineCreateRunner` (class with `calls: list[str]` and `async run_live_producer_node(graph, node_id)`); `derive_probe_graph_state() -> tuple[scaffold, CurrentStepStreamResult]`. Tasks 3–4 rely on these exact names.

- [ ] **Step 1: Write the failing Layer-1 tests**

Append to `mcp_server/tests/test_lm5k_worker_probe.py`:

```python
def test_derived_graph_state_is_coherent_post_verify() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    assert result.stop_reason == "max_steps_reached"
    assert result.steps_attempted == 3
    assert [r.execution_kind for r in result.records] == [
        "producer", "verifier", "bind",
    ]
    assert [r.accepted_node_id for r in result.records] == [
        "create_script", "verify_create", "repair_same_component",
    ]
    # create producer record ran/applied with receipt evidence; the receipt
    # is intentionally created_with_errors with verification failed, so
    # "applied" must not be read as "script verified clean" (spec section 6)
    assert result.records[0].ran is True
    graph = result.final_graph
    assert graph.nodes["create_script"].evidence is not None
    # the repair signal lives on the verifier record, asserted separately
    assert result.records[1].verifier_outcome_status == "needs_repair"

    repair = graph.nodes["repair_same_component"]
    assert repair.status == "ready"
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    params = repair.metadata[EXECUTION_PARAMS_KEY]
    assert params["guid"] == PROBE.PROBE_COMPONENT_GUID
    assert params["mode"] == "body"
    # memory facts are receipt-derived by the producer projection --
    # nothing is hand-injected anymore
    assert graph.memory.facts["component_guid"] == PROBE.PROBE_COMPONENT_GUID
    assert (
        graph.memory.facts["repair_anchor"]["component_guid"]
        == PROBE.PROBE_COMPONENT_GUID
    )


def test_offline_runner_refuses_non_create_nodes() -> None:
    import asyncio

    runner = PROBE._OfflineCreateRunner()
    _scaffold, result = PROBE.derive_probe_graph_state()
    with pytest.raises(RuntimeError, match="offline runner asked to execute"):
        asyncio.run(
            runner.run_live_producer_node(
                result.final_graph, "repair_same_component"
            )
        )
    assert runner.calls == ["repair_same_component"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py::test_derived_graph_state_is_coherent_post_verify -v`
Expected: FAIL with `AttributeError: ... has no attribute 'derive_probe_graph_state'`

- [ ] **Step 3: Extract `_probe_contract()` and add the derivation code**

In `scripts/lm5k_worker_probe.py`, below `SCENARIO_STATE`, add:

```python
# Deterministic component guid carried by the offline create receipt; every
# downstream fact (memory repair_anchor/component_guid, bound repair params)
# derives from this via the real projection + bind path, never by hand.
PROBE_COMPONENT_GUID = "lm5l-probe-component-guid"
```

Above `build_probe_context`, add a new function `_probe_contract()` containing EXACTLY the existing `RookWorkflowContract(...)` construction currently inside `build_probe_context` (lines ~146–223), including its imports, returning the contract:

```python
def _probe_contract():
    """The golden repair workflow contract — unchanged since rounds 1/1b.

    LM5L changes the derived scenario STATE, not the workflow contract."""
    from rook.agent.plan_graph_workflow_contract import (
        BindStepSpec,
        ExpectedNodeRef,
        InitialNodeParams,
        ProducerStepSpec,
        RookWorkflowContract,
        VerifierStepSpec,
        WorkflowNodeRule,
        WorkflowTemplateRef,
    )

    return RookWorkflowContract(
        workflow_id=SCENARIO_WORKFLOW_ID,
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify_repair_verify",
                "language": "csharp",
            },
            expected_template_id="gh_csharp_create_verify_repair_verify",
        ),
        initial_params=(
            InitialNodeParams(
                node_id="create_script",
                execution_params={
                    "code": "A = DefinitelyMissingSymbol;",
                    "pins_in": [],
                    "pins_out": ["A:double"],
                    "name": "LM5KFirstProbe",
                    "x": 350,
                    "y": 1420,
                },
            ),
        ),
        expected_refs=(
            ExpectedNodeRef(
                node_id="create_script",
                execution_ref="gh_create_csharp_script:v1",
            ),
            ExpectedNodeRef(
                node_id="repair_same_component",
                execution_ref="gh_update_script:v1",
            ),
        ),
        rules=(
            WorkflowNodeRule(
                node_id="create_script",
                steps_by_seen_count=(ProducerStepSpec(node_id="create_script"),),
            ),
            WorkflowNodeRule(
                node_id="verify_create",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_create",
                        source_node_id="create_script",
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                node_id="repair_same_component",
                steps_by_seen_count=(
                    BindStepSpec(
                        node_id="repair_same_component",
                        base_params={
                            "code": "A = 42.0;",
                            "mode": "body",
                            "language": "csharp",
                        },
                        bindings={"guid": ("repair_anchor", "component_guid")},
                    ),
                    ProducerStepSpec(node_id="repair_same_component"),
                ),
            ),
            WorkflowNodeRule(
                node_id="verify_repair",
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id="verify_repair",
                        source_node_id="repair_same_component",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=("done",),
        max_steps=6,
        metadata={"trace": {"slice": "LM5K"}},
    )
```

Then add the receipt, runner, and derivation:

```python
def _wrapped_failure_create_raw() -> dict:
    """Deterministic create receipt: mutation happened, verification failed.

    Same shape as the LM4W chain guard's — created_with_errors plus a
    repair_anchor is exactly what makes verify_create observe needs_repair
    and gives the bind step a real anchor to bind from."""
    return {
        "success": False,
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {
                    "status": "created",
                    "component_guid": PROBE_COMPONENT_GUID,
                },
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {
                    "component_guid": PROBE_COMPONENT_GUID,
                    "language": "csharp",
                },
            }
        },
    }


class _OfflineCreateRunner:
    """Deterministic offline producer runner for fixture derivation.

    Only create_script may execute: with max_steps=3 the stream stops after
    the bind step, so being asked to run any other node is a fixture bug."""

    def __init__(self) -> None:
        self.calls: list = []

    async def run_live_producer_node(self, graph, node_id):
        from rook.agent.plan_graph_live import LiveProducerResult
        from rook.learning.plan_graph_runner import apply_producer_result

        self.calls.append(node_id)
        if node_id != "create_script":
            raise RuntimeError(
                "LM5L coherent fixture invariant failed: "
                f"offline runner asked to execute {node_id!r}"
            )
        inner = apply_producer_result(
            graph, node_id, _wrapped_failure_create_raw()
        )
        return LiveProducerResult(
            graph=inner.graph,
            applied=inner.applied,
            node_id=node_id,
            tool_name="gh_create_csharp_script",
            outcome_status=inner.outcome_status,
            reason=inner.reason,
        )


def derive_probe_graph_state():
    """Advance the compiled golden scenario to the coherent post-verify state.

    Runs the existing offline stream driver (the LM4W chain-guard pattern)
    for exactly three steps — create producer, verify_create verifier,
    bind — leaving repair_same_component genuinely ready with bound
    execution params and receipt-derived memory facts. Returns
    (scaffold, stream_result); world-state coherence holds by construction
    because the state passed through the same advancement semantics real
    workflows use. NOT a stream runner in the probe: no live provider, no
    tool dispatch, no model."""
    import asyncio

    from rook.agent.plan_graph_current_step_stream import (
        run_current_step_stream,
    )
    from rook.agent.plan_graph_workflow_contract import (
        compile_workflow_contract,
    )

    scaffold = compile_workflow_contract(_probe_contract())
    result = asyncio.run(
        run_current_step_stream(
            scaffold.graph,
            scaffold.provider,
            max_steps=3,
            runner=_OfflineCreateRunner(),
        )
    )
    return scaffold, result
```

In `build_probe_context`, replace the inline `contract = RookWorkflowContract(...)` block with `contract = _probe_contract()` and delete the now-unused contract-class imports from its import list (keep `compile_workflow_contract` there for now — full rewiring is Task 4). Do NOT change its behavior otherwise in this task.

- [ ] **Step 4: Run the new tests and the full file**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py -q`
Expected: `16 passed` (14 prior + 2 new; the untouched `build_probe_context` path still passes its e2e tests)

- [ ] **Step 5: Commit**

```bash
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5l): derive_probe_graph_state — offline stream to post-verify state (LM4W pattern)"
```

---

### Task 3: Split coherence guards + guard tests (incl. round-1b regression)

**Files:**
- Modify: `scripts/lm5k_worker_probe.py` (add `_invariant`, `_require_coherent_graph_state`, `_require_probe_context_shape` below `derive_probe_graph_state`)
- Test: `mcp_server/tests/test_lm5k_worker_probe.py`

**Interfaces:**
- Consumes: `derive_probe_graph_state()`, `_probe_contract()`, `PROBE_COMPONENT_GUID` (Task 2); `EXECUTION_PARAMS_KEY` (from `rook.agent.plan_graph_live`); `Mapping` (already imported at probe module top from `collections.abc`).
- Produces: `_require_coherent_graph_state(scaffold, stream_result) -> None` and `_require_probe_context_shape(context) -> None`, both raising `RuntimeError` with messages prefixed `LM5L coherent fixture invariant failed: `. Task 4 wires both into `build_probe_context`.

- [ ] **Step 1: Write the failing guard tests**

Append to `mcp_server/tests/test_lm5k_worker_probe.py`:

```python
def _fresh_scaffold_and_empty_result():
    """The round-1b shape: freshly compiled graph, nothing executed."""
    from rook.agent.plan_graph_current_step_stream import (
        CurrentStepStreamResult,
    )
    from rook.agent.plan_graph_workflow_contract import (
        compile_workflow_contract,
    )

    scaffold = compile_workflow_contract(PROBE._probe_contract())
    return scaffold, CurrentStepStreamResult(
        final_graph=scaffold.graph,
        records=(),
        supply_records=(),
        stop_reason="max_steps_reached",
        steps_attempted=0,
    )


def test_graph_state_guard_rejects_round_1b_shape() -> None:
    # Regression: the guard must reject the exact fixture shape that
    # produced the round-1b false spine reading. It would have caught
    # round 1b; this proves it stays able to.
    scaffold, empty = _fresh_scaffold_and_empty_result()
    with pytest.raises(
        RuntimeError, match="LM5L coherent fixture invariant failed"
    ):
        PROBE._require_coherent_graph_state(scaffold, empty)


def test_graph_state_guard_accepts_derived_state() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    PROBE._require_coherent_graph_state(scaffold, result)  # must not raise


def test_graph_state_guard_message_repair_not_ready() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.nodes["repair_same_component"].status = "pending"
    with pytest.raises(RuntimeError, match="repair node is not ready"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_params_missing() -> None:
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    scaffold, result = PROBE.derive_probe_graph_state()
    del result.final_graph.nodes["repair_same_component"].metadata[
        EXECUTION_PARAMS_KEY
    ]
    with pytest.raises(
        RuntimeError, match="execution params missing on repair node"
    ):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_memory_facts_missing() -> None:
    scaffold, result = PROBE.derive_probe_graph_state()
    result.final_graph.memory.facts.clear()
    with pytest.raises(RuntimeError, match="memory facts missing repair anchor"):
        PROBE._require_coherent_graph_state(scaffold, result)


def test_graph_state_guard_message_pre_bind_sequence() -> None:
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
            max_steps=2,
            runner=PROBE._OfflineCreateRunner(),
        )
    )
    with pytest.raises(RuntimeError, match="unexpected step sequence"):
        PROBE._require_coherent_graph_state(scaffold, result)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py -k "guard" -v`
Expected: FAIL with `AttributeError: ... has no attribute '_require_coherent_graph_state'`

- [ ] **Step 3: Implement the guards**

In `scripts/lm5k_worker_probe.py`, below `derive_probe_graph_state`, add:

```python
def _invariant(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(
            f"LM5L coherent fixture invariant failed: {message}"
        )


def _require_coherent_graph_state(scaffold, stream_result) -> None:
    """Fail-fast tripwire on derived world-state facts (spec 4.2).

    Factual and probe-specific only — no receipt re-interpretation, no
    policy, no schema validation; those belong to the LM5B/C/D/F spine.
    Internal guard MAY inspect params/memory values; the rendered envelope
    never shows values (spec 3.5) and its tests assert only model-visible
    facts. Purpose: a future drift fails the probe at startup instead of
    burning live API attempts on an incoherent envelope."""
    from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY

    _invariant(
        stream_result.stop_reason == "max_steps_reached",
        f"stream stopped early: {stream_result.stop_reason}",
    )
    kinds = [record.execution_kind for record in stream_result.records]
    _invariant(
        kinds == ["producer", "verifier", "bind"],
        f"unexpected step sequence: {kinds}",
    )
    create_record = stream_result.records[0]
    _invariant(
        create_record.accepted_node_id == "create_script"
        and create_record.ran,
        "history missing create producer record",
    )
    graph = stream_result.final_graph
    _invariant(
        graph.nodes["create_script"].evidence is not None,
        "create producer record has no receipt evidence",
    )
    _invariant(
        stream_result.records[1].verifier_outcome_status == "needs_repair",
        "verifier outcome is not needs_repair",
    )
    repair = graph.nodes["repair_same_component"]
    _invariant(repair.status == "ready", "repair node is not ready")
    params = repair.metadata.get(EXECUTION_PARAMS_KEY)
    _invariant(
        isinstance(params, Mapping) and bool(params),
        "execution params missing on repair node",
    )
    facts = graph.memory.facts
    anchor = facts.get("repair_anchor")
    _invariant(
        isinstance(anchor, Mapping)
        and anchor.get("component_guid") == PROBE_COMPONENT_GUID
        and facts.get("component_guid") == PROBE_COMPONENT_GUID,
        "memory facts missing repair anchor",
    )


def _require_probe_context_shape(context) -> None:
    """Caller-declared worker affordances (spec 4.2) — split from graph
    state because these are hand-declared planner inputs, not derived
    world-state. LM5A deliberately has no top-level current_node_id field;
    the guard checks the public context shape."""
    _invariant(
        context.current_node is not None
        and context.current_node.node_id == "repair_same_component",
        "current node is not repair_same_component",
    )
    _invariant(
        any(
            action.action_id == "draft_repair_params"
            for action in context.allowed_actions
        ),
        "allowed action draft_repair_params missing",
    )
```

- [ ] **Step 4: Run the guard tests, then the full file**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py -q`
Expected: `22 passed` (16 prior + 6 new)

Note: `test_graph_state_guard_rejects_round_1b_shape` fails the guard at the step-sequence check (`kinds == []`) — that is correct; an empty history IS the round-1b incoherence signature.

- [ ] **Step 5: Commit**

```bash
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5l): split coherence guards with round-1b regression test"
```

---

### Task 4: Rewire `build_probe_context()` + Layer-2 rendered-envelope tests

**Files:**
- Modify: `scripts/lm5k_worker_probe.py` (`build_probe_context`, currently ~line 124)
- Test: `mcp_server/tests/test_lm5k_worker_probe.py`

**Interfaces:**
- Consumes: `derive_probe_graph_state()`, `_require_coherent_graph_state`, `_require_probe_context_shape` (Tasks 2–3); `build_local_worker_turn_context`, `WorkerKnowledgePacket`, `WorkerAllowedAction` (from `rook.agent.local_worker_turn_context`, FROZEN — consume only); `render_local_worker_turn_request_payload` (from `rook.agent.local_worker_turn_request`; returns a mapping whose `"context"` key holds the rendered context payload).
- Produces: `build_probe_context()` with the same zero-arg signature and return type (`LocalWorkerTurnContext`) — `run_candidate` continues calling it unchanged.

- [ ] **Step 1: Write the failing Layer-2 tests**

Append to `mcp_server/tests/test_lm5k_worker_probe.py`:

```python
def test_probe_context_envelope_is_world_state_coherent() -> None:
    # Layer 2 (spec section 6): the envelope a model actually sees must
    # tell the same coherent story as the derived graph — asserted ONLY on
    # model-visible facts (has_execution_params flag, memory KEYS), never
    # param payloads or memory fact values (spec section 3.5). These are
    # point-for-point the negations of the ceiling's round-1b refusal.
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context()
    )
    context = payload["context"]

    assert (
        "repair_same_component" in context["current_graph"]["ready_node_ids"]
    )
    node = context["current_node"]
    assert node["node_id"] == "repair_same_component"
    assert node["status"] == "ready"
    assert node["has_execution_params"] is True
    assert "repair_anchor" in node["memory_keys"]
    assert "component_guid" in node["memory_keys"]

    history = context["history"]
    assert history["current_step_count"] == 3
    assert [
        step["execution_kind"] for step in history["recent_steps"]
    ] == ["producer", "verifier", "bind"]
    assert [
        step["accepted_node_id"] for step in history["recent_steps"]
    ] == ["create_script", "verify_create", "repair_same_component"]

    action_ids = [a["action_id"] for a in context["allowed_actions"]]
    assert "draft_repair_params" in action_ids


def test_probe_envelope_never_exposes_internal_values() -> None:
    # The visibility boundary itself (spec section 3.5): bound execution
    # param values and memory fact values must NOT appear anywhere in the
    # rendered request payload — the worker sees has_execution_params and
    # memory_keys, not payloads.
    from rook.agent.local_worker_turn_request import (
        render_local_worker_turn_request_payload,
    )

    payload = render_local_worker_turn_request_payload(
        PROBE.build_probe_context()
    )
    rendered = json.dumps(payload)
    assert PROBE.PROBE_COMPONENT_GUID not in rendered
    assert "A = 42.0;" not in rendered


def test_probe_context_shape_guard_wired() -> None:
    import dataclasses

    context = PROBE.build_probe_context()
    stripped = dataclasses.replace(context, allowed_actions=())
    with pytest.raises(
        RuntimeError, match="allowed action draft_repair_params missing"
    ):
        PROBE._require_probe_context_shape(stripped)
    headless = dataclasses.replace(context, current_node=None)
    with pytest.raises(
        RuntimeError, match="current node is not repair_same_component"
    ):
        PROBE._require_probe_context_shape(headless)
```

- [ ] **Step 2: Run to verify the new tests fail for the right reason**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py::test_probe_context_envelope_is_world_state_coherent -v`
Expected: FAIL — with the OLD fixture the envelope shows `ready_node_ids == ["create_script"]` and `current_node.status == "pending"`, so the first assertions fail. (This failing run IS the round-1b defect reproduced as a test.)

- [ ] **Step 3: Rewire `build_probe_context`**

Replace the entire body of `build_probe_context` in `scripts/lm5k_worker_probe.py` with:

```python
def build_probe_context():
    """Golden scenario v2: the compiled repair workflow advanced through
    the real offline stream to the coherent post-verify state (spec 4.3).

    All world-state is derived — the create receipt's projection writes the
    memory facts, verify_create's needs_repair readies the repair node, and
    the bind step binds execution params. The knowledge packet and allowed
    action stay hand-declared: they are planner-authored inputs, not
    world-state claims. Runs once per candidate; derivation is
    deterministic and millisecond-cheap, so no caching."""
    from rook.agent.local_worker_turn_context import (
        WorkerAllowedAction,
        WorkerKnowledgePacket,
        build_local_worker_turn_context,
    )

    scaffold, stream_result = derive_probe_graph_state()
    _require_coherent_graph_state(scaffold, stream_result)
    context = build_local_worker_turn_context(
        scaffold,
        stream_result.final_graph,
        stream_result.records,
        stream_result.supply_records,
        current_node_id="repair_same_component",
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script components use body-style code",
                content={"source": "probe fixture", "trust": "high"},
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={"type": "object", "required": ["code", "mode"]},
            ),
        ),
    )
    _require_probe_context_shape(context)
    return context
```

This deletes: the `import copy` + `copy.deepcopy(scaffold.graph)`, the hand-injected `graph.memory.facts[...] = ...` lines, the empty `(), ()` records arguments, and the remaining contract-compile import (now inside `derive_probe_graph_state`). Hand-injection is deleted, not relocated (spec §4.1).

- [ ] **Step 4: Run the full probe test file**

Run: `.venv/Scripts/python.exe -m pytest tests/test_lm5k_worker_probe.py -q`
Expected: `25 passed` — including the untouched offline e2e tests: the fake transports read the allowed action from the envelope, so spine still passes 3/3 on the coherent fixture.

- [ ] **Step 5: Commit**

```bash
git add scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py
git commit -m "feat(lm5l): build_probe_context derives coherent post-verify state with real history"
```

---

### Task 5: Gates — full suite, 3.10 compile, scope, whitespace

**Files:**
- No source changes expected. Fix-forward only if a gate fails.

**Interfaces:**
- Consumes: everything above.
- Produces: a branch ready for PR (merge held for explicit user approval).

- [ ] **Step 1: Full local-worker + probe focused suite**

Run (from `C:/UDEV/Rook-lm5l/mcp_server`):
`.venv/Scripts/python.exe -m pytest tests/test_local_worker_prompt_artifact.py tests/test_local_worker_adapter.py tests/test_local_worker_model_transport.py tests/test_local_worker_turn_context.py tests/test_local_worker_turn_request.py tests/test_lm5k_worker_probe.py -q`
Expected: all pass, 0 failures.

- [ ] **Step 2: Full mcp_server test suite**

Run: `.venv/Scripts/python.exe -m pytest tests -q`
Expected: everything passes (baseline on main was 1015+; the count grows by this slice's 12 new tests). Any failure outside the two touched files must be investigated — it would mean unintended coupling.

- [ ] **Step 3: Python 3.10 compile gate**

Run (from `C:/UDEV/Rook-lm5l`):
`py -3.10 -m py_compile scripts/lm5k_worker_probe.py mcp_server/tests/test_lm5k_worker_probe.py`
Expected: exit 0, no output.

- [ ] **Step 4: Exact scope assertion**

Run: `git diff --name-only main..HEAD`
Expected — EXACTLY these paths (plus `.superpowers/sdd/` ledger files if the SDD process committed any):

```
docs/superpowers/plans/2026-07-02-lm5l-coherent-golden-probe-fixture.md
docs/superpowers/specs/2026-07-02-lm5l-coherent-golden-probe-fixture-design.md
mcp_server/tests/test_lm5k_worker_probe.py
scripts/lm5k_worker_probe.py
```

Any other path is a scope violation — stop and investigate.

- [ ] **Step 5: Whitespace gate**

Run: `git diff main..HEAD --check`
Expected: no output.

- [ ] **Step 6: Commit any gate fixes; otherwise nothing to commit**

```bash
git status --porcelain
```

Expected: clean tree.

---

## Post-merge activity (NOT part of this plan's execution)

Round 2 runs from the repo root **after** this branch merges (probes are evidence, never CI): same panel command as rounds 1/1b with `--capture-raw`, `ANTHROPIC_API_KEY` sourced from `mcp_server/.env` (never printed). The round-2 evidence section is authored in its own docs PR, labeling rounds 1/1b retroactively as `lm5k_golden_repair_v1` / `fresh_compiled_graph` and answering the fair-test question: do qwen3/Sonnet move from valid refusal/clarification to `candidate_action_request` on a coherent envelope?
