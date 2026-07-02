# LM5I Local Worker Request Envelope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic LM5I request-envelope renderer that composes an LM5H context payload with LM5G response schema/contract vocabulary without adding prompt, model, adapter, validation, or runtime authority.

**Architecture:** Add one tiny production module, `rook.agent.local_worker_turn_request`, with a request schema constant and `render_local_worker_turn_request_payload(...)`. The module prechecks `LocalWorkerTurnContext`, calls LM5H exactly once for the nested context payload, embeds LM5G's public response schema, and renders a private structural response contract as fresh mutable `dict`/`list` containers. Tests live in one focused file and include a compact integration path through LM5H -> LM5I -> LM5G -> LM5D -> LM5F.

**Tech Stack:** Python 3.10-compatible code, frozen LM5A/LM5B dataclasses, pytest, AST/import guards, PowerShell verification commands.

---

## Scope And File Map

Create:

```text
mcp_server/src/rook/agent/local_worker_turn_request.py
mcp_server/tests/test_local_worker_turn_request.py
```

Do not modify:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
mcp_server/src/rook/agent/__init__.py
mcp_server/tests/test_local_worker_turn_context.py
mcp_server/tests/test_local_worker_turn_context_renderer.py
mcp_server/tests/test_local_worker_turn_response.py
mcp_server/tests/test_local_worker_turn_response_loader.py
```

Allowed production imports in `local_worker_turn_request.py`:

```python
from collections.abc import Mapping
from typing import Any

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    render_local_worker_turn_context_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
)
```

Forbidden production behavior:

```text
No LM5G loader calls.
No LM5B validation calls.
No LM5C/D/F calls.
No prompt/model/RookChat/Capability Index/file/JSON/YAML/runtime/stream/tool execution surfaces.
No package-level re-export.
```

---

## Task 0: Pre-Implementation Branch And Baseline Check

**Files:**
- Read-only: repository state

- [ ] **Step 1: Confirm the isolated LM5I worktree is clean**

Run:

```powershell
git status --short --branch
git diff --name-status origin/main..HEAD
```

Expected:

```text
## codex/lm5i-local-worker-request-envelope...origin/main [ahead 2]
A       docs/superpowers/specs/2026-07-02-lm5i-local-worker-request-envelope-design.md
A       docs/superpowers/plans/2026-07-02-lm5i-local-worker-request-envelope.md
```

If `git diff --name-status origin/main..HEAD` includes production or test files before Task 1, stop and investigate. Do not proceed on a mixed branch.

- [ ] **Step 2: Re-run the current transport baseline**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context_renderer.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py
```

Expected:

```text
55 passed
```

If this fails, stop and investigate before writing LM5I tests.

---

## Task 1: Add Failing LM5I Tests

**Files:**
- Create: `mcp_server/tests/test_local_worker_turn_request.py`

- [ ] **Step 1: Create the test file with unit and integration coverage**

Create `mcp_server/tests/test_local_worker_turn_request.py` with this content:

```python
from __future__ import annotations

import ast
import copy
import inspect
from collections.abc import Mapping

import pytest

from rook.agent import local_worker_turn_request as request_module
from rook.agent.local_worker_scenario_evaluation import (
    LocalWorkerScenarioExpectation,
    evaluate_local_worker_scenario_result,
)
from rook.agent.local_worker_turn_context import (
    LOCAL_WORKER_TURN_CONTEXT_SCHEMA,
    LocalWorkerTurnContext,
    WorkerAllowedAction,
    WorkerGraphSummary,
    WorkerHistorySummary,
    WorkerKnowledgePacket,
    WorkerNodeSummary,
    WorkerStepTraceSummary,
    WorkerSupplyTraceSummary,
    WorkerWorkflowSummary,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
from rook.agent.local_worker_turn_request import (
    LOCAL_WORKER_TURN_REQUEST_SCHEMA,
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
    load_local_worker_turn_response_payload,
)
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


TOP_LEVEL_KEYS = {
    "schema",
    "context",
    "response_schema",
    "response_contract",
}
RESPONSE_CONTRACT_KEYS = {
    "kinds",
    "field_sets",
    "required_nullable_fields",
    "refusal_categories",
}
RESPONSE_KINDS = [
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
]
RESPONSE_FIELD_SETS = {
    "action_request": ["schema", "kind", "action_id", "rationale", "input"],
    "clarification_request": ["schema", "kind", "question", "rationale"],
    "refusal": ["schema", "kind", "category", "reason"],
    "observation": ["schema", "kind", "message", "data"],
}
REQUIRED_NULLABLE_FIELDS = {
    "clarification_request": ["rationale"],
    "observation": ["data"],
}
REFUSAL_CATEGORIES = [
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
]


def _context(*, current_node: bool = True) -> LocalWorkerTurnContext:
    return LocalWorkerTurnContext(
        workflow=WorkerWorkflowSummary(
            workflow_id="repair_component",
            contract_schema="rook.workflow_contract:v1",
            contract_fingerprint="fingerprint-123",
            compiler_id="rook.workflow_contract.compiler:v1",
            provider_id="rook.catalog_current_step_provider:v1",
            selected_template_id="gh_repair_component:v1",
            max_steps=6,
        ),
        current_graph=WorkerGraphSummary(
            node_count=3,
            node_ids=("create_script", "done", "repair_same_component"),
            ready_node_ids=("repair_same_component",),
            terminal_node_ids=("done",),
            status_counts={"pending": 1, "ready": 1, "terminal": 1},
        ),
        current_node=(
            WorkerNodeSummary(
                node_id="repair_same_component",
                intent="repair existing C# script component",
                role="repair",
                status="ready",
                execution_ref="gh_update_script:v1",
                is_terminal=False,
                has_execution_params=True,
                memory_keys=("component_guid", "repair_anchor"),
            )
            if current_node
            else None
        ),
        history=WorkerHistorySummary(
            current_step_count=2,
            supply_count=2,
            last_accepted_node_id="verify_create",
            last_execution_kind="verifier",
            last_stop_reason="needs_repair",
            recent_steps=(
                WorkerStepTraceSummary(
                    accepted_node_id="create_script",
                    execution_kind="producer",
                    ran=True,
                    failure=None,
                ),
                WorkerStepTraceSummary(
                    accepted_node_id="verify_create",
                    execution_kind="verifier",
                    ran=True,
                    failure="needs_repair",
                ),
            ),
            recent_supplies=(
                WorkerSupplyTraceSummary(
                    decision="SUPPLY",
                    reason=None,
                    selected_node_id="create_script",
                    has_envelope=True,
                ),
                WorkerSupplyTraceSummary(
                    decision="SUPPLY",
                    reason="needs_repair",
                    selected_node_id="repair_same_component",
                    has_envelope=True,
                ),
            ),
        ),
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script body mode",
                content={
                    "source": "test fixture",
                    "trust": "high",
                    "flags": ("body", "repair"),
                    "nested": {"count": -3, "enabled": True},
                },
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id="draft_repair_params",
                kind="draft_repair_params",
                description="Draft replacement C# body repair parameters.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string"},
                        "mode": {"enum": ("body", "full_source")},
                    },
                    "required": ("code", "mode"),
                },
            ),
        ),
    )


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5i_request_envelope",
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
                    "name": "LM5IRequestEnvelope",
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
        metadata={"trace": {"slice": "LM5I"}},
    )


def _compiled_context() -> LocalWorkerTurnContext:
    scaffold = compile_workflow_contract(_repair_contract())
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts["repair_anchor"] = {"component_guid": "component-123"}
    graph.memory.facts["component_guid"] = "component-123"
    return build_local_worker_turn_context(
        scaffold,
        graph,
        (),
        (),
        current_node_id="repair_same_component",
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script components use body-style code",
                content={
                    "source": "test fixture",
                    "trust": "high",
                    "guidance": "Use body-style code.",
                },
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


def _response_payload_from_request_payload(
    request_payload: Mapping[str, object],
) -> dict[str, object]:
    context_payload = request_payload["context"]
    assert isinstance(context_payload, Mapping)
    actions = context_payload["allowed_actions"]
    assert isinstance(actions, list)
    first_action = actions[0]
    assert isinstance(first_action, Mapping)
    action_id = first_action["action_id"]
    assert isinstance(action_id, str)

    current_node = context_payload["current_node"]
    assert isinstance(current_node, Mapping)
    assert action_id != current_node["execution_ref"]

    assert request_payload["response_schema"] == LOCAL_WORKER_TURN_RESPONSE_SCHEMA
    response_contract = request_payload["response_contract"]
    assert isinstance(response_contract, Mapping)
    assert response_contract["field_sets"]["action_request"] == RESPONSE_FIELD_SETS[
        "action_request"
    ]

    return {
        "schema": request_payload["response_schema"],
        "kind": "action_request",
        "action_id": action_id,
        "rationale": "Use the first allowed action from the request context.",
        "input": {
            "code": "A = 42.0;",
            "mode": "body",
            "language": "csharp",
        },
    }


def test_public_surface_is_explicit() -> None:
    assert LOCAL_WORKER_TURN_REQUEST_SCHEMA == "rook.local_worker_turn_request:v1"
    assert request_module.__all__ == (
        "LOCAL_WORKER_TURN_REQUEST_SCHEMA",
        "render_local_worker_turn_request_payload",
    )


def test_request_payload_has_exact_top_level_shape_and_schema_values() -> None:
    payload = render_local_worker_turn_request_payload(_context())

    assert type(payload) is dict
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema"] == LOCAL_WORKER_TURN_REQUEST_SCHEMA
    assert payload["context"]["schema"] == LOCAL_WORKER_TURN_CONTEXT_SCHEMA
    assert payload["response_schema"] == LOCAL_WORKER_TURN_RESPONSE_SCHEMA
    assert "context_schema" not in payload
    assert "instructions" not in payload
    assert "prompt" not in payload
    assert "adapter" not in payload
    assert "model" not in payload
    assert "worker" not in payload
    assert "request_id" not in payload
    assert "timestamp" not in payload
    assert "run_id" not in payload
    assert "context_id" not in payload
    assert "fingerprint" not in payload


def test_response_contract_is_exact_structural_vocabulary_only() -> None:
    payload = render_local_worker_turn_request_payload(_context())
    contract = payload["response_contract"]

    assert type(contract) is dict
    assert set(contract) == RESPONSE_CONTRACT_KEYS
    assert contract["kinds"] == RESPONSE_KINDS
    assert contract["field_sets"] == RESPONSE_FIELD_SETS
    assert contract["required_nullable_fields"] == REQUIRED_NULLABLE_FIELDS
    assert contract["refusal_categories"] == REFUSAL_CATEGORIES
    assert "descriptions" not in contract
    assert "examples" not in contract
    assert "notes" not in contract
    assert "instructions" not in contract
    assert "semantics" not in contract
    assert "action_authorization" not in contract


def test_request_payload_uses_plain_mutable_containers() -> None:
    payload = render_local_worker_turn_request_payload(_context())

    assert type(payload) is dict
    assert type(payload["context"]) is dict
    assert type(payload["response_contract"]) is dict
    assert type(payload["response_contract"]["kinds"]) is list
    assert type(payload["response_contract"]["field_sets"]) is dict
    assert type(payload["response_contract"]["field_sets"]["action_request"]) is list
    assert type(payload["response_contract"]["required_nullable_fields"]) is dict
    assert type(
        payload["response_contract"]["required_nullable_fields"]["observation"]
    ) is list
    assert type(payload["response_contract"]["refusal_categories"]) is list

    payload["response_contract"]["kinds"].append("mutated")
    payload["response_contract"]["field_sets"]["action_request"].append("mutated")

    assert payload["response_contract"]["kinds"][-1] == "mutated"


def test_response_contract_is_fresh_across_calls() -> None:
    context = _context()
    first = render_local_worker_turn_request_payload(context)
    first["response_contract"]["kinds"].append("bad")
    first["response_contract"]["field_sets"]["action_request"].append("bad")
    first["response_contract"]["required_nullable_fields"]["observation"].append(
        "bad"
    )
    first["response_contract"]["refusal_categories"].append("bad")

    second = render_local_worker_turn_request_payload(context)

    assert second["response_contract"]["kinds"] == RESPONSE_KINDS
    assert second["response_contract"]["field_sets"] == RESPONSE_FIELD_SETS
    assert second["response_contract"]["required_nullable_fields"] == (
        REQUIRED_NULLABLE_FIELDS
    )
    assert second["response_contract"]["refusal_categories"] == REFUSAL_CATEGORIES


def test_context_payload_is_fresh_across_calls_and_detached_from_source() -> None:
    context = _context()
    first = render_local_worker_turn_request_payload(context)
    first["context"]["workflow"]["workflow_id"] = "changed"
    first["context"]["knowledge"][0]["content"]["flags"].append("mutated")

    second = render_local_worker_turn_request_payload(context)

    assert second["context"]["workflow"]["workflow_id"] == "repair_component"
    assert second["context"]["knowledge"][0]["content"]["flags"] == [
        "body",
        "repair",
    ]
    assert context.workflow.workflow_id == "repair_component"
    assert context.knowledge[0].content["flags"] == ("body", "repair")


def test_request_renderer_prechecks_context_type() -> None:
    with pytest.raises(TypeError, match="LocalWorkerTurnContext"):
        render_local_worker_turn_request_payload({"not": "context"})  # type: ignore[arg-type]


def test_request_renderer_calls_lm5h_once_and_embeds_returned_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    context = _context()
    rendered_context = {
        "schema": LOCAL_WORKER_TURN_CONTEXT_SCHEMA,
        "sentinel": "context-payload",
    }
    calls: list[LocalWorkerTurnContext] = []

    def fake_renderer(received: LocalWorkerTurnContext) -> Mapping[str, object]:
        calls.append(received)
        return rendered_context

    monkeypatch.setattr(
        request_module,
        "render_local_worker_turn_context_payload",
        fake_renderer,
    )

    payload = render_local_worker_turn_request_payload(context)

    assert calls == [context]
    assert payload["context"] is rendered_context


def test_module_level_boundary_guard() -> None:
    source = inspect.getsource(request_module)
    tree = ast.parse(source)

    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )

    assert "json" not in imports
    assert "yaml" not in imports
    assert "pathlib" not in imports

    banned_names = {
        "LOCAL_WORKER_TURN_CONTEXT_SCHEMA",
        "load_local_worker_turn_response_payload",
        "validate_local_worker_turn_response",
        "WorkerActionRequest",
        "WorkerClarificationRequest",
        "WorkerRefusal",
        "WorkerObservation",
        "LocalWorkerTurnResponse",
        "dispose_local_worker_turn_response",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
        "build_local_worker_turn_context",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "run_current_step_stream",
        "run_current_mapped_step",
        "execute_mapped_step",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "propose_next_node",
        "json",
        "yaml",
        "YAML",
        "Path",
        "open",
        "model",
        "RookChat",
        "prompt",
        "dispatcher",
        "CapabilityIndex",
    }
    referenced_names = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    }
    referenced_attributes = {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    }

    assert not (referenced_names & banned_names)
    assert "loads" not in referenced_attributes
    assert "dumps" not in referenced_attributes
    assert "safe_load" not in referenced_attributes


def test_request_payload_composes_with_lm5g_lm5d_and_lm5f() -> None:
    context = _compiled_context()
    request_payload = render_local_worker_turn_request_payload(context)
    response_payload = _response_payload_from_request_payload(request_payload)

    assert request_payload["context"]["current_node"]["execution_ref"] == (
        "gh_update_script:v1"
    )
    assert response_payload["action_id"] == "draft_repair_params"
    assert response_payload["action_id"] != (
        request_payload["context"]["current_node"]["execution_ref"]
    )

    response = load_local_worker_turn_response_payload(response_payload)
    harness_record = run_local_worker_turn(context, lambda received: response)

    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="request_envelope_payload_chain",
            category="request_envelope_integration",
            expected_status="completed",
            expected_disposition="candidate_action_request",
            expected_attempt_valid=True,
            expected_action_id="draft_repair_params",
            expected_response_kind="action_request",
            expected_workflow_id=context.workflow.workflow_id,
            expected_contract_fingerprint=context.workflow.contract_fingerprint,
        ),
        harness_record,
    )

    assert harness_record.status == "completed"
    assert result.passed is True
```

- [ ] **Step 2: Run the new tests and verify they fail for missing module**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_request.py
```

Expected failure:

```text
ModuleNotFoundError: No module named 'rook.agent.local_worker_turn_request'
```

Do not implement production code until this RED check fails for the expected reason.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add mcp_server\tests\test_local_worker_turn_request.py
git commit -m "test(lm5i): cover local worker request envelope"
```

Expected:

```text
[codex/lm5i-local-worker-request-envelope <sha>] test(lm5i): cover local worker request envelope
```

---

## Task 2: Implement The LM5I Request Envelope Module

**Files:**
- Create: `mcp_server/src/rook/agent/local_worker_turn_request.py`
- Test: `mcp_server/tests/test_local_worker_turn_request.py`

- [ ] **Step 1: Create the production module**

Create `mcp_server/src/rook/agent/local_worker_turn_request.py` with this content:

```python
"""LM5I local-worker request envelope renderer.

Composes the LM5H context payload with the LM5G response schema and structural
response contract. This module does not render prompts, call models, load
responses, validate admissibility, run workers, dispatch tools, mutate graphs,
continue streams, or bind Capability Index metadata.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext,
    render_local_worker_turn_context_payload,
)
from rook.agent.local_worker_turn_response import (
    LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
)

LOCAL_WORKER_TURN_REQUEST_SCHEMA = "rook.local_worker_turn_request:v1"

__all__ = (
    "LOCAL_WORKER_TURN_REQUEST_SCHEMA",
    "render_local_worker_turn_request_payload",
)

_RESPONSE_KINDS = (
    "action_request",
    "clarification_request",
    "refusal",
    "observation",
)
_RESPONSE_FIELD_SETS = {
    "action_request": ("schema", "kind", "action_id", "rationale", "input"),
    "clarification_request": ("schema", "kind", "question", "rationale"),
    "refusal": ("schema", "kind", "category", "reason"),
    "observation": ("schema", "kind", "message", "data"),
}
_REQUIRED_NULLABLE_FIELDS = {
    "clarification_request": ("rationale",),
    "observation": ("data",),
}
_REFUSAL_CATEGORIES = (
    "unsafe",
    "insufficient_context",
    "unsupported_action",
    "out_of_scope",
)


def render_local_worker_turn_request_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    if not isinstance(context, LocalWorkerTurnContext):
        raise TypeError("context must be LocalWorkerTurnContext")

    context_payload = render_local_worker_turn_context_payload(context)
    return {
        "schema": LOCAL_WORKER_TURN_REQUEST_SCHEMA,
        "context": context_payload,
        "response_schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "response_contract": _render_response_contract(),
    }


def _render_response_contract() -> dict[str, Any]:
    return {
        "kinds": list(_RESPONSE_KINDS),
        "field_sets": {
            kind: list(fields)
            for kind, fields in _RESPONSE_FIELD_SETS.items()
        },
        "required_nullable_fields": {
            kind: list(fields)
            for kind, fields in _REQUIRED_NULLABLE_FIELDS.items()
        },
        "refusal_categories": list(_REFUSAL_CATEGORIES),
    }
```

- [ ] **Step 2: Run targeted tests and verify they pass**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_request.py
```

Expected:

```text
10 passed
```

If the count differs only because tests were split or combined during implementation, verify zero failures and document the actual count in the final review notes.

- [ ] **Step 3: Run py_compile on the new production and test files**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m py_compile `
  mcp_server\src\rook\agent\local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_request.py

py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_request.py
```

Expected: both commands exit `0` with no output.

- [ ] **Step 4: Commit the implementation**

Run:

```powershell
git add `
  mcp_server\src\rook\agent\local_worker_turn_request.py `
  mcp_server\tests\test_local_worker_turn_request.py
git commit -m "feat(lm5i): render local worker request envelopes"
```

Expected:

```text
[codex/lm5i-local-worker-request-envelope <sha>] feat(lm5i): render local worker request envelopes
```

---

## Task 3: Verification And Boundary Checks

**Files:**
- Verify: `mcp_server/src/rook/agent/local_worker_turn_request.py`
- Verify: `mcp_server/tests/test_local_worker_turn_request.py`

- [ ] **Step 1: Run targeted LM5I tests**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_request.py
```

Expected: all collected tests pass.

- [ ] **Step 2: Run nearby LM5 tests**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py `
  mcp_server\tests\test_local_worker_turn_request.py
```

Expected: all collected tests pass.

- [ ] **Step 3: Run the focused PlanGraph/local-worker gate**

Run:

```powershell
$files = @(Get-ChildItem -Path mcp_server\tests -Filter 'test_plan_graph*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName })
$files += @(Get-ChildItem -Path mcp_server\tests -Filter 'test_local_worker*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName })
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest @files
```

Expected: all collected tests pass. Use this safer two-step array build rather than combining `.FullName` arrays inside a single `@(...)` expression.

- [ ] **Step 4: Run diff whitespace check**

Run:

```powershell
git diff --check origin/main..HEAD
```

Expected: exit code `0` and no output.

- [ ] **Step 5: Verify production diff scope**

Run:

```powershell
git diff --name-status origin/main..HEAD
```

Expected output includes exactly these implementation files plus the LM5I spec/plan docs:

```text
A       docs/superpowers/specs/2026-07-02-lm5i-local-worker-request-envelope-design.md
A       docs/superpowers/plans/2026-07-02-lm5i-local-worker-request-envelope.md
A       mcp_server/src/rook/agent/local_worker_turn_request.py
A       mcp_server/tests/test_local_worker_turn_request.py
```

If the output includes LM5H/LM5G production files, package-level exports, native/managed files, knowledge files, or unrelated docs, stop and inspect before review.

- [ ] **Step 6: Run direct production forbidden-symbol scan**

Run:

```powershell
$path = 'mcp_server\src\rook\agent\local_worker_turn_request.py'
$matches = rg -n "LOCAL_WORKER_TURN_CONTEXT_SCHEMA|load_local_worker_turn_response_payload|validate_local_worker_turn_response|WorkerActionRequest|WorkerClarificationRequest|WorkerRefusal|WorkerObservation|LocalWorkerTurnResponse|dispose_local_worker_turn_response|run_local_worker_turn|evaluate_local_worker_scenario_result|build_local_worker_scenario_report|build_local_worker_turn_context|compile_workflow_contract|load_workflow_contract_payload|snapshot_workflow_contract|run_current_step_stream|run_current_mapped_step|execute_mapped_step|map_accepted_proposal_to_step|revalidate_proposal|propose_next_node|import json|from json|json\.|import yaml|from yaml|yaml\.|from pathlib|Path\(|open\(|RookChat|prompt_builder|ToolDispatcher|CapabilityIndex|OpenAI|litellm" $path
if ($LASTEXITCODE -eq 0) {
  $matches
  exit 1
}
if ($LASTEXITCODE -ne 1) {
  exit $LASTEXITCODE
}
```

Expected: exit code `0` and no output. The authoritative boundary check remains the AST/import guard in `test_local_worker_turn_request.py`; this scan is a quick backstop.

- [ ] **Step 7: Verify no package-level export edits**

Run:

```powershell
git diff --name-only origin/main..HEAD -- mcp_server/src/rook/agent/__init__.py
```

Expected: no output.

- [ ] **Step 8: Request code review**

Use `superpowers:requesting-code-review` after verification passes. Provide the reviewer:

```text
Base: origin/main
Head: current branch HEAD
Spec: docs/superpowers/specs/2026-07-02-lm5i-local-worker-request-envelope-design.md
Plan: docs/superpowers/plans/2026-07-02-lm5i-local-worker-request-envelope.md
Focus: request-envelope only, no prompt/model/adapter/runtime authority, no LM5G loader calls, no LM5B/C/D/F calls, exact response contract shape, fresh mutable containers, and module-level boundary guard.
```

- [ ] **Step 9: Address review findings or record clean review**

If the reviewer reports findings, fix them in a new commit and rerun the targeted and affected nearby tests. If the reviewer reports no findings, record the review outcome in the handoff.

- [ ] **Step 10: Final branch status**

Run:

```powershell
git status --short --branch
```

Expected:

```text
## codex/lm5i-local-worker-request-envelope...origin/main [ahead <N>]
```

with no unstaged or untracked files.

---

## Implementation Handoff Recommendation

Use **Option 1: Subagent-Driven** for execution.

Reason: LM5I is a small code slice, but it is boundary-sensitive. The risk is not algorithmic difficulty; it is accidental policy, prompt, model, response-loader, or runtime creep. A fresh implementer plus review pass is worth the discipline.
