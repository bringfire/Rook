# LM5E Local Worker Scenario Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a test-only deterministic Rook-shaped scenario suite that exercises the landed LM5A-D local worker boundary with curated repair, authority, gotcha, history, refusal, and harness-error scenarios.

**Architecture:** LM5E adds one scenario test file and no production code. The test suite builds real compiled repair workflow contexts by default, uses test-local deterministic worker functions, runs them through `run_local_worker_turn(...)`, and asserts the full LM5A-D audit trail. Gotcha-derived knowledge is represented only as hardcoded `WorkerKnowledgePacket` fixtures; no file, knowledge-store, model, stream, or live runtime surfaces are used.

**Tech Stack:** Python 3.11, pytest, dataclasses already in Rook, LM4 workflow contract compiler test fixtures, LM5A/B/C/D public APIs.

---

## Scope And File Structure

Create exactly one implementation file:

```text
mcp_server/tests/test_local_worker_turn_scenarios.py
```

Do not modify production files:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
```

Do not read docs, catalogs, session logs, `operations_knowledge.json`, or any knowledge store from tests. The only source inspection allowed is `inspect.getsource(sys.modules[__name__])` for the AST/import guard.

The untracked `.claude/worktrees/` directory may be present in the workspace. Do not stage it.

---

## Task 0: Pre-Implementation Branch And Scope Gate

**Files:**
- Read: `docs/superpowers/specs/2026-06-30-lm5e-local-worker-scenario-suite-design.md`
- Create later: `mcp_server/tests/test_local_worker_turn_scenarios.py`

- [ ] **Step 1: Verify branch and worktree state**

Run:

```powershell
git status --short --branch
git log --oneline --decorate -5
```

Expected:

```text
## codex/lm5e-local-worker-scenario-suite
```

Allowed untracked item:

```text
?? .claude/worktrees/
```

If the branch is behind `origin/main`, rebase or merge current `main` before writing tests. Preserve unrelated untracked files.

- [ ] **Step 2: Verify scope before editing**

Run:

```powershell
git diff --name-status main..HEAD
git diff --name-status
```

Expected before implementation:

```text
A       docs/superpowers/specs/2026-06-30-lm5e-local-worker-scenario-suite-design.md
A       docs/superpowers/plans/2026-06-30-lm5e-local-worker-scenario-suite.md
```

`git diff --name-status` should be empty or show only future LM5E plan edits. Do not proceed if RookChat, native, managed, knowledge, or LM5A-D production files appear.

---

## Task 1: Add Scenario Test Skeleton, Fixtures, And Boundary Guard

**Files:**
- Create: `mcp_server/tests/test_local_worker_turn_scenarios.py`

- [ ] **Step 1: Create the test file with imports, workflow fixture, context helpers, workers, assertions, and guard**

Create `mcp_server/tests/test_local_worker_turn_scenarios.py` with this starting content:

```python
from __future__ import annotations

import ast
import copy
import inspect
import sys
from collections.abc import Callable, Mapping

import pytest

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_harness import (
    LocalWorkerTurnHarnessRecord,
    run_local_worker_turn,
)
from rook.agent.local_worker_turn_response import (
    LocalWorkerTurnResponse,
    WorkerActionRequest,
    WorkerClarificationRequest,
    WorkerObservation,
    WorkerRefusal,
)
from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import EnvelopeSupplyRecord
from rook.agent.plan_graph_workflow_contract import (
    BindStepSpec,
    ExpectedNodeRef,
    InitialNodeParams,
    ProducerStepSpec,
    RookWorkflowContract,
    VerifierStepSpec,
    WorkflowNodeRule,
    WorkflowTemplateRef,
    compile_workflow_contract,
)


Worker = Callable[[LocalWorkerTurnContext], LocalWorkerTurnResponse]


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5e_worker_scenarios",
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
                    "name": "LM5ELocalWorkerScenarios",
                    "x": 350,
                    "y": 1320,
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
                        bindings={
                            "guid": ("repair_anchor", "component_guid"),
                        },
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
        metadata={"trace": {"slice": "LM5E"}},
    )


def _scaffold():
    return compile_workflow_contract(_repair_contract())


def _action(action_id: str = "draft_repair_params") -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=action_id,
        kind="draft_repair_params",
        description="Draft replacement C# body repair parameters.",
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "mode": {"type": "string"},
                "language": {"type": "string"},
            },
            "required": ["code", "mode", "language"],
        },
    )


def _context(
    *,
    current_node_id: str | None = "repair_same_component",
    knowledge: tuple[WorkerKnowledgePacket, ...] = (),
    allowed_actions: tuple[WorkerAllowedAction, ...] = (_action(),),
    records: tuple[CurrentStepRecord, ...] = (),
    supply_records: tuple[EnvelopeSupplyRecord, ...] = (),
) -> LocalWorkerTurnContext:
    scaffold = _scaffold()
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts["repair_anchor"] = {"component_guid": "component-123"}
    graph.memory.facts["component_guid"] = "component-123"
    return build_local_worker_turn_context(
        scaffold,
        graph,
        records,
        supply_records,
        current_node_id=current_node_id,
        knowledge=knowledge,
        allowed_actions=allowed_actions,
    )


def _record(
    *,
    accepted_node_id: str | None,
    execution_kind: str | None,
    ran: bool = True,
    mapping_failure: str | None = None,
    execution_failure: str | None = None,
) -> CurrentStepRecord:
    return CurrentStepRecord(
        metadata=None,
        metadata_status="absent",
        metadata_error=None,
        mapping=object(),
        revalidation=object(),
        execution=object(),
        supplied_selected_node_id=accepted_node_id,
        fresh_selected_node_id=accepted_node_id,
        accepted_node_id=accepted_node_id,
        mapping_mapped=mapping_failure is None,
        mapping_failure=mapping_failure,
        mapped_step_target=accepted_node_id,
        ran=ran,
        execution_kind=execution_kind,
        execution_failure=execution_failure,
        producer_node_id=None,
        producer_tool_name=None,
        producer_applied=None,
        producer_outcome_status=None,
        producer_reason=None,
        verifier_node_id=None,
        verifier_source_node_id=None,
        verifier_applied=None,
        verifier_outcome_status=None,
        verifier_reason=None,
        bind_node_id=None,
        bind_applied=None,
        bind_reason=None,
    )


def _supply(
    *,
    decision: str | None = "SUPPLY",
    reason: str | None = None,
    selected_node_id: str | None = None,
    envelope: object | None = object(),
    invalid_reason: str | None = None,
    error_class: str | None = None,
    metadata: Mapping[str, object] | None = None,
) -> EnvelopeSupplyRecord:
    if metadata is None and selected_node_id is not None:
        metadata = {"selected_node_id": selected_node_id}
    return EnvelopeSupplyRecord(
        decision=decision,
        envelope=envelope,
        reason=reason,
        metadata=metadata,
        invalid_reason=invalid_reason,
        error_class=error_class,
    )


def _knowledge_packet(
    *,
    packet_id: str,
    kind: str,
    title: str,
    content: Mapping[str, object],
) -> WorkerKnowledgePacket:
    return WorkerKnowledgePacket(
        packet_id=packet_id,
        kind=kind,
        title=title,
        content=dict(content),
    )


def _packet_by_id(
    context: LocalWorkerTurnContext,
    packet_id: str,
) -> WorkerKnowledgePacket | None:
    for packet in context.knowledge:
        if packet.packet_id == packet_id:
            return packet
    return None


def _action_response(
    action_id: str = "draft_repair_params",
    *,
    input_payload: Mapping[str, object] | None = None,
) -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerActionRequest(
            action_id=action_id,
            rationale="Request the bounded repair action from the turn context.",
            input=dict(
                input_payload
                if input_payload is not None
                else {
                    "code": "A = 42.0;",
                    "mode": "body",
                    "language": "csharp",
                }
            ),
        )
    )


def _clarification_response(
    question: str = "Which bounded repair facts should be used?",
) -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(
        WorkerClarificationRequest(
            question=question,
            rationale="The worker needs explicit context before requesting action.",
        )
    )


def _observation_response(message: str = "No action requested.") -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(WorkerObservation(message))


def _refusal_response(
    category: str = "out_of_scope",
    reason: str = "The requested operation is outside the declared worker scope.",
) -> LocalWorkerTurnResponse:
    return LocalWorkerTurnResponse(WorkerRefusal(category, reason))


def _request_allowed_action_worker(
    context: LocalWorkerTurnContext,
) -> LocalWorkerTurnResponse:
    return _action_response(context.allowed_actions[0].action_id)


def _request_action_id_worker(action_id: str) -> Worker:
    def worker(context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
        return _action_response(action_id)

    return worker


def _observe_terminal_worker(context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
    assert context.current_node is not None
    if context.current_node.is_terminal:
        return _observation_response("Terminal node is already selected.")
    return _action_response(context.allowed_actions[0].action_id)


def _script_body_gotcha_worker(
    context: LocalWorkerTurnContext,
) -> LocalWorkerTurnResponse:
    packet = _packet_by_id(context, "gh_csharp_script_body_gotcha")
    if packet is None:
        return _clarification_response("Is body-style C# script repair required?")
    return _action_response(
        context.allowed_actions[0].action_id,
        input_payload={
            "code": "A = 42.0;",
            "mode": "body",
            "language": "csharp",
            "source_gotcha": packet.packet_id,
        },
    )


def _wire_shape_gotcha_worker(
    context: LocalWorkerTurnContext,
) -> LocalWorkerTurnResponse:
    packet = _packet_by_id(context, "public_mcp_wire_shape_gotcha")
    assert packet is not None
    return _observation_response("MCP success text is treated as the payload itself.")


def _gh_bridge_uncertainty_worker(
    context: LocalWorkerTurnContext,
) -> LocalWorkerTurnResponse:
    packet = _packet_by_id(context, "gh_bridge_capability_uncertainty")
    assert packet is not None
    return _clarification_response("Is the Grasshopper bridge available for this turn?")


def _history_needs_repair_worker(
    context: LocalWorkerTurnContext,
) -> LocalWorkerTurnResponse:
    selected = {
        supply.selected_node_id
        for supply in context.history.recent_supplies
        if supply.selected_node_id is not None
    }
    if "repair_same_component" in selected:
        return _action_response(context.allowed_actions[0].action_id)
    return _clarification_response("No recent repair selection was visible.")


def _avoid_repeated_bad_action_worker(
    context: LocalWorkerTurnContext,
) -> LocalWorkerTurnResponse:
    packet = _packet_by_id(context, "recent_unknown_action_attempt")
    assert packet is not None
    return _observation_response("Prior unknown action id noted; not repeating it.")


def _out_of_scope_worker(context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
    packet = _packet_by_id(context, "out_of_scope_operation")
    assert packet is not None
    return _refusal_response()


def _raising_worker(context: LocalWorkerTurnContext) -> LocalWorkerTurnResponse:
    raise ValueError("scenario smoke failure")


def _assert_anchors(
    record: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
) -> None:
    assert record.context_workflow_id == context.workflow.workflow_id
    assert record.context_contract_fingerprint == context.workflow.contract_fingerprint
    if record.disposition is not None:
        assert (
            record.disposition.attempt.context_workflow_id
            == context.workflow.workflow_id
        )
        assert (
            record.disposition.attempt.context_contract_fingerprint
            == context.workflow.contract_fingerprint
        )


def _assert_completed_action(
    record: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
    action_id: str,
) -> WorkerActionRequest:
    _assert_anchors(record, context)
    assert record.status == "completed"
    assert record.reason == "completed:candidate_action_request"
    assert record.disposition is not None
    assert record.disposition.disposition == "candidate_action_request"
    assert record.disposition.attempt.valid is True
    assert record.disposition.attempt.action_id == action_id
    assert record.response is not None
    assert isinstance(record.response.payload, WorkerActionRequest)
    return record.response.payload


def _assert_blocked_unknown_action(
    record: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
    action_id: str,
) -> None:
    _assert_anchors(record, context)
    assert record.status == "completed"
    assert record.reason == "completed:blocked"
    assert record.disposition is not None
    assert record.disposition.disposition == "blocked"
    assert record.disposition.attempt.valid is False
    assert record.disposition.attempt.failure == "unknown_action_id"
    assert record.disposition.attempt.action_id == action_id


def _assert_completed_observation(
    record: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
) -> WorkerObservation:
    _assert_anchors(record, context)
    assert record.status == "completed"
    assert record.reason == "completed:observation_recorded"
    assert record.disposition is not None
    assert record.disposition.disposition == "observation_recorded"
    assert record.disposition.attempt.action_id is None
    assert record.response is not None
    assert isinstance(record.response.payload, WorkerObservation)
    return record.response.payload


def _assert_completed_clarification(
    record: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
) -> WorkerClarificationRequest:
    _assert_anchors(record, context)
    assert record.status == "completed"
    assert record.reason == "completed:clarification_needed"
    assert record.disposition is not None
    assert record.disposition.disposition == "clarification_needed"
    assert record.disposition.attempt.action_id is None
    assert record.response is not None
    assert isinstance(record.response.payload, WorkerClarificationRequest)
    return record.response.payload


def _assert_completed_refusal(
    record: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
    category: str,
) -> WorkerRefusal:
    _assert_anchors(record, context)
    assert record.status == "completed"
    assert record.reason == "completed:refusal_recorded"
    assert record.disposition is not None
    assert record.disposition.disposition == "refusal_recorded"
    assert record.disposition.attempt.valid is True
    assert record.disposition.attempt.action_id is None
    assert record.response is not None
    assert isinstance(record.response.payload, WorkerRefusal)
    assert record.response.payload.category == category
    return record.response.payload


def test_scenario_test_module_boundary_has_no_runtime_or_file_creep() -> None:
    source = inspect.getsource(sys.modules[__name__])
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    referenced_names: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Name):
            referenced_names.add(node.id)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                called_names.add(func.id)
            elif isinstance(func, ast.Attribute):
                called_names.add(func.attr)

    allowed_import_modules = {
        "__future__",
        "ast",
        "copy",
        "inspect",
        "sys",
        "collections.abc",
        "pytest",
        "rook.agent.local_worker_turn_context",
        "rook.agent.local_worker_turn_harness",
        "rook.agent.local_worker_turn_response",
        "rook.agent.plan_graph_current_step_runner",
        "rook.agent.plan_graph_current_step_stream",
        "rook.agent.plan_graph_workflow_contract",
    }
    assert imported_modules <= allowed_import_modules

    banned_names = {
        "json",
        "yaml",
        "Path",
        "open",
        "read_text",
        "loads",
        "dumps",
        "load",
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "CatalogCurrentStepProvider",
        "WorkflowProvenanceEnvelopeSource",
        "RookAgent",
        "base_agent",
        "dispatcher",
        "server",
        "model",
        "prompt",
        "litellm",
        "OpenAI",
        "retry",
        "fallback",
        "critic",
        "oversight",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "read_text", "loads", "dumps", "load"} & called_names)
```

- [ ] **Step 2: Run the skeleton boundary test**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_scenarios.py::test_scenario_test_module_boundary_has_no_runtime_or_file_creep -q
```

Expected:

```text
1 passed
```

- [ ] **Step 3: Commit Task 1**

Run:

```powershell
git add mcp_server/tests/test_local_worker_turn_scenarios.py
git commit -m "test(lm5e): add local worker scenario fixtures"
```

Expected:

```text
[codex/lm5e-local-worker-scenario-suite <hash>] test(lm5e): add local worker scenario fixtures
```

---

## Task 2: Add Baseline Action, Terminal, And Authority-Boundary Scenarios

**Files:**
- Modify: `mcp_server/tests/test_local_worker_turn_scenarios.py`

- [ ] **Step 1: Add repair-node allowed action scenario**

Append:

```python
def test_repair_node_requests_allowed_repair_action() -> None:
    context = _context(current_node_id="repair_same_component")

    record = run_local_worker_turn(context, _request_allowed_action_worker)

    payload = _assert_completed_action(record, context, "draft_repair_params")
    assert payload.input["mode"] == "body"
    assert payload.input["language"] == "csharp"
```

- [ ] **Step 2: Add terminal done observation scenario**

Append:

```python
def test_terminal_done_node_observes_completion_even_with_allowed_action() -> None:
    context = _context(current_node_id="done")

    assert context.current_node is not None
    assert context.current_node.node_id == "done"
    assert context.current_node.is_terminal is True

    record = run_local_worker_turn(context, _observe_terminal_worker)

    payload = _assert_completed_observation(record, context)
    assert "Terminal node" in payload.message
```

- [ ] **Step 3: Add execution-ref-as-action-id blocked scenario**

Append:

```python
def test_execution_ref_used_as_action_id_is_blocked() -> None:
    context = _context(current_node_id="repair_same_component")

    assert context.current_node is not None
    assert context.current_node.execution_ref == "gh_update_script:v1"

    record = run_local_worker_turn(
        context,
        _request_action_id_worker("gh_update_script:v1"),
    )

    _assert_blocked_unknown_action(record, context, "gh_update_script:v1")
```

- [ ] **Step 4: Add no-allowed-actions blocked scenario**

Append:

```python
def test_no_allowed_actions_blocks_action_request() -> None:
    context = _context(
        current_node_id="repair_same_component",
        allowed_actions=(),
    )

    assert context.allowed_actions == ()

    record = run_local_worker_turn(
        context,
        _request_action_id_worker("draft_repair_params"),
    )

    _assert_blocked_unknown_action(record, context, "draft_repair_params")
```

- [ ] **Step 5: Run Task 2 scenarios**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_repair_node_requests_allowed_repair_action `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_terminal_done_node_observes_completion_even_with_allowed_action `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_execution_ref_used_as_action_id_is_blocked `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_no_allowed_actions_blocks_action_request `
  -q
```

Expected:

```text
4 passed
```

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add mcp_server/tests/test_local_worker_turn_scenarios.py
git commit -m "test(lm5e): cover worker authority boundaries"
```

---

## Task 3: Add Gotcha, Capability, And Refusal Scenarios

**Files:**
- Modify: `mcp_server/tests/test_local_worker_turn_scenarios.py`

- [ ] **Step 1: Add gotcha packet helper functions**

Append before the scenario tests or near other fixture helpers:

```python
def _script_body_gotcha_packet() -> WorkerKnowledgePacket:
    return _knowledge_packet(
        packet_id="gh_csharp_script_body_gotcha",
        kind="gotcha",
        title="C# script components use body-style code",
        content={
            "source": "docs/rookchat-tool-contract-smoke.md",
            "trust": "high",
            "failure_family": "wrong_code_shape",
            "guidance": (
                "Use RhinoCode C# script body code, not a GH_Component subclass."
            ),
        },
    )


def _wire_shape_gotcha_packet() -> WorkerKnowledgePacket:
    return _knowledge_packet(
        packet_id="public_mcp_wire_shape_gotcha",
        kind="gotcha",
        title="Public MCP success text is the payload",
        content={
            "source": "docs/CURRENT_ARCHITECTURE.md",
            "trust": "high",
            "failure_family": "wire_shape_confusion",
            "guidance": (
                "MCP success text parses as the data payload itself, not data.data."
            ),
        },
    )


def _gh_bridge_uncertainty_packet() -> WorkerKnowledgePacket:
    return _knowledge_packet(
        packet_id="gh_bridge_capability_uncertainty",
        kind="capability_note",
        title="Grasshopper bridge capability is uncertain",
        content={
            "source": "test fixture",
            "trust": "medium",
            "capability": "grasshopper_bridge",
            "status": "unknown_or_unavailable",
            "guidance": (
                "Clarify availability before requesting GH-affecting action."
            ),
        },
    )


def _out_of_scope_packet() -> WorkerKnowledgePacket:
    return _knowledge_packet(
        packet_id="out_of_scope_operation",
        kind="scope_note",
        title="Requested operation is outside the declared action scope",
        content={
            "source": "test fixture",
            "trust": "high",
            "failure_family": "authority_boundary",
            "guidance": "Refuse operations that are outside declared allowed actions.",
        },
    )
```

- [ ] **Step 2: Add script-body gotcha present scenario**

Append:

```python
def test_script_body_gotcha_requests_body_style_repair_action() -> None:
    context = _context(
        current_node_id="repair_same_component",
        knowledge=(_script_body_gotcha_packet(),),
    )

    record = run_local_worker_turn(context, _script_body_gotcha_worker)

    payload = _assert_completed_action(record, context, "draft_repair_params")
    assert payload.input["mode"] == "body"
    assert payload.input["language"] == "csharp"
    assert "GH_Component" not in payload.input["code"]
    assert payload.input["source_gotcha"] == "gh_csharp_script_body_gotcha"
```

- [ ] **Step 3: Add script-body gotcha absent clarification scenario**

Append:

```python
def test_missing_script_body_gotcha_clarifies_instead_of_inventing_repair() -> None:
    context = _context(current_node_id="repair_same_component", knowledge=())

    record = run_local_worker_turn(context, _script_body_gotcha_worker)

    payload = _assert_completed_clarification(record, context)
    assert "body-style" in payload.question
```

- [ ] **Step 4: Add public MCP wire-shape gotcha observation scenario**

Append:

```python
def test_public_mcp_wire_shape_gotcha_is_observed_without_action() -> None:
    context = _context(
        current_node_id="verify_create",
        knowledge=(_wire_shape_gotcha_packet(),),
    )

    record = run_local_worker_turn(context, _wire_shape_gotcha_worker)

    payload = _assert_completed_observation(record, context)
    assert "payload itself" in payload.message
```

- [ ] **Step 5: Add GH bridge uncertainty clarification scenario**

Append:

```python
def test_gh_bridge_capability_uncertainty_clarifies_before_action() -> None:
    context = _context(
        current_node_id="repair_same_component",
        knowledge=(_gh_bridge_uncertainty_packet(),),
    )

    record = run_local_worker_turn(context, _gh_bridge_uncertainty_worker)

    payload = _assert_completed_clarification(record, context)
    assert "Grasshopper bridge" in payload.question
```

- [ ] **Step 6: Add out-of-scope refusal scenario**

Append:

```python
def test_out_of_scope_operation_is_recorded_as_refusal() -> None:
    context = _context(
        current_node_id="repair_same_component",
        knowledge=(_out_of_scope_packet(),),
    )

    record = run_local_worker_turn(context, _out_of_scope_worker)

    payload = _assert_completed_refusal(record, context, "out_of_scope")
    assert "outside" in payload.reason
```

- [ ] **Step 7: Run Task 3 scenarios**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_script_body_gotcha_requests_body_style_repair_action `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_missing_script_body_gotcha_clarifies_instead_of_inventing_repair `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_public_mcp_wire_shape_gotcha_is_observed_without_action `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_gh_bridge_capability_uncertainty_clarifies_before_action `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_out_of_scope_operation_is_recorded_as_refusal `
  -q
```

Expected:

```text
5 passed
```

- [ ] **Step 8: Commit Task 3**

Run:

```powershell
git add mcp_server/tests/test_local_worker_turn_scenarios.py
git commit -m "test(lm5e): cover gotcha and refusal scenarios"
```

---

## Task 4: Add History, Attempt-Memory, And Worker-Error Scenarios

**Files:**
- Modify: `mcp_server/tests/test_local_worker_turn_scenarios.py`

- [ ] **Step 1: Add attempt-memory packet helper**

Append near other packet helpers:

```python
def _recent_unknown_action_packet() -> WorkerKnowledgePacket:
    return _knowledge_packet(
        packet_id="recent_unknown_action_attempt",
        kind="attempt_memory",
        title="Prior worker response used an unknown action id",
        content={
            "source": "test fixture",
            "trust": "medium",
            "prior_failure": "unknown_action_id",
            "action_id": "gh_update_script:v1",
            "guidance": "Do not repeat the same invalid action id.",
        },
    )
```

- [ ] **Step 2: Add recent needs-repair history scenario**

Append:

```python
def test_recent_needs_repair_history_requests_bounded_repair_action() -> None:
    records = (
        _record(
            accepted_node_id="verify_create",
            execution_kind="verifier",
            ran=True,
            execution_failure=None,
        ),
    )
    supply_records = (
        _supply(
            decision="SUPPLY",
            selected_node_id="repair_same_component",
        ),
    )
    context = _context(
        current_node_id="repair_same_component",
        records=records,
        supply_records=supply_records,
    )

    assert context.history.recent_supplies[-1].selected_node_id == (
        "repair_same_component"
    )

    record = run_local_worker_turn(context, _history_needs_repair_worker)

    _assert_completed_action(record, context, "draft_repair_params")
```

- [ ] **Step 3: Add recent blocked unknown action packet scenario**

Append:

```python
def test_recent_blocked_unknown_action_packet_prevents_repeat_request() -> None:
    context = _context(
        current_node_id="repair_same_component",
        knowledge=(_recent_unknown_action_packet(),),
    )

    record = run_local_worker_turn(context, _avoid_repeated_bad_action_worker)

    payload = _assert_completed_observation(record, context)
    assert "not repeating" in payload.message
    assert record.disposition is not None
    assert record.disposition.attempt.action_id is None
```

- [ ] **Step 4: Add worker exception smoke scenario**

Append:

```python
def test_worker_exception_smoke_is_anchored_to_context() -> None:
    context = _context(current_node_id="repair_same_component")

    record = run_local_worker_turn(context, _raising_worker)

    assert record.status == "worker_error"
    assert record.response is None
    assert record.disposition is None
    assert record.failure == "worker_exception"
    assert record.reason == "worker_exception:ValueError"
    _assert_anchors(record, context)
```

- [ ] **Step 5: Run Task 4 scenarios**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_recent_needs_repair_history_requests_bounded_repair_action `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_recent_blocked_unknown_action_packet_prevents_repeat_request `
  mcp_server/tests/test_local_worker_turn_scenarios.py::test_worker_exception_smoke_is_anchored_to_context `
  -q
```

Expected:

```text
3 passed
```

- [ ] **Step 6: Run the full scenario file**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_scenarios.py -q
```

Expected:

```text
13 passed
```

The count is 12 required scenarios plus the boundary/import guard. If additional small helper tests are added during implementation, update this expected count in review notes rather than weakening scenario assertions.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add mcp_server/tests/test_local_worker_turn_scenarios.py
git commit -m "test(lm5e): cover history and harness smoke scenarios"
```

---

## Task 5: Full Verification And Scope Review

**Files:**
- Verify: `mcp_server/tests/test_local_worker_turn_scenarios.py`
- Verify unchanged: `mcp_server/src/rook/agent/local_worker_turn_context.py`
- Verify unchanged: `mcp_server/src/rook/agent/local_worker_turn_response.py`
- Verify unchanged: `mcp_server/src/rook/agent/local_worker_turn_disposition.py`
- Verify unchanged: `mcp_server/src/rook/agent/local_worker_turn_harness.py`

- [ ] **Step 1: Run targeted LM5E tests**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest mcp_server/tests/test_local_worker_turn_scenarios.py -q
```

Expected:

```text
13 passed
```

- [ ] **Step 2: Run nearby LM5 regression**

Run:

```powershell
mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server/tests/test_local_worker_turn_context.py `
  mcp_server/tests/test_local_worker_turn_response.py `
  mcp_server/tests/test_local_worker_turn_disposition.py `
  mcp_server/tests/test_local_worker_turn_harness.py `
  mcp_server/tests/test_local_worker_turn_scenarios.py `
  -q
```

Expected:

```text
all tests pass
```

Do not hardcode the count in the implementation report; LM5A-D counts may change before execution.

- [ ] **Step 3: Run focused PlanGraph/local-worker gate**

Run:

```powershell
$files = Get-ChildItem mcp_server\tests -Filter 'test_plan_graph*.py' | Sort-Object Name | ForEach-Object { $_.FullName }
mcp_server\.venv\Scripts\python.exe -m pytest @files `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_disposition.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_turn_scenarios.py `
  -q
```

Expected:

```text
all tests pass
```

- [ ] **Step 4: Run diff and production-scope checks**

Run:

```powershell
git diff --check main...HEAD
git diff --name-status main...HEAD
git status --short --branch
```

Expected changed files:

```text
A       docs/superpowers/specs/2026-06-30-lm5e-local-worker-scenario-suite-design.md
A       docs/superpowers/plans/2026-06-30-lm5e-local-worker-scenario-suite.md
A       mcp_server/tests/test_local_worker_turn_scenarios.py
```

No production source files should appear. The unrelated `.claude/worktrees/` may still be untracked and must not be staged.

- [ ] **Step 5: Run explicit no-production-diff guard**

Run:

```powershell
git diff --name-only main...HEAD -- mcp_server/src src/Rook src/RookNative knowledge/gh/operations_knowledge.json
```

Expected:

```text

```

No output.

- [ ] **Step 6: Commit plan checklist update only if the executor marks steps**

If the executor updates this plan checklist during implementation, commit those doc checkbox changes separately:

```powershell
git add docs/superpowers/plans/2026-06-30-lm5e-local-worker-scenario-suite.md
git commit -m "docs(lm5e): update scenario suite plan checklist"
```

If no checklist updates are made, skip this commit.

- [ ] **Step 7: Prepare completion summary**

Report:

```text
LM5E targeted tests: <actual count> passed
Nearby LM5 regression: <actual count> passed
Focused PlanGraph/local-worker gate: <actual count> passed
Production diff: empty
Changed files: spec, plan, test_local_worker_turn_scenarios.py
No file/knowledge reads, stream runner, model, live Rhino/GH, dispatcher, retry/fallback/critic/oversight creep
```

Then use the finishing branch process to choose push/PR versus local merge.

---

## Self-Review Checklist

- [ ] The plan implements all 12 minimum scenarios from the spec.
- [ ] Gotcha packets are hardcoded and do not read knowledge files.
- [ ] The AST/import guard uses `inspect.getsource(sys.modules[__name__])` and does not require `Path`, `open`, `read_text`, or `json`.
- [ ] No production module changes are planned.
- [ ] No LM4S stream runner, provider, mapper, revalidator, executor, live runner, model, RookChat, dispatcher, retry, fallback, critic, or oversight surface is planned.
- [ ] The history scenario uses direct `CurrentStepRecord` / `EnvelopeSupplyRecord` fixtures and only flattened fields LM5A summarizes.
- [ ] The recent blocked unknown action scenario uses a `WorkerKnowledgePacket`, not LM5D harness records in LM5A history.
- [ ] The verification commands include targeted, nearby, focused, diff, and production-scope gates.
