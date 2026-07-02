# LM5H Local Worker Context Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic renderer from `LocalWorkerTurnContext` to a strict, schema-tagged, JSON-ready outbound context payload.

**Architecture:** LM5H extends `local_worker_turn_context.py` with exactly one schema constant and one renderer function. The renderer accepts only real `LocalWorkerTurnContext` objects, projects all LM5A public fields into fresh mutable `dict`/`list` containers, and does not call response loading, worker execution, evaluation, models, RookChat, streams, files, JSON parsers, or Capability Index surfaces.

**Tech Stack:** Python dataclasses and mappings, pytest, AST-based boundary guards, existing LM5A-G public APIs.

---

## Files

Create:

```text
mcp_server/tests/test_local_worker_turn_context_renderer.py
```

Modify:

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
mcp_server/tests/test_local_worker_turn_context.py
```

Docs already present on branch:

```text
docs/superpowers/specs/2026-07-01-lm5h-local-worker-context-renderer-design.md
docs/superpowers/plans/2026-07-01-lm5h-local-worker-context-renderer.md
```

Do not modify:

```text
mcp_server/src/rook/agent/local_worker_turn_response.py
mcp_server/src/rook/agent/local_worker_turn_disposition.py
mcp_server/src/rook/agent/local_worker_turn_harness.py
mcp_server/src/rook/agent/local_worker_scenario_evaluation.py
src/Rook/**
src/RookNative/**
operations_knowledge.json
knowledge/**
```

`test_local_worker_turn_context.py` may change only to update the canonical
`__all__` public-surface assertion.

---

## Task 0: Pre-Implementation Gate

**Files:** None

- [ ] **Step 0.1: Confirm isolated branch state**

Run:

```powershell
Set-Location C:\Users\bring\.config\superpowers\worktrees\Rook\lm5h-local-worker-context-renderer
git status --short --branch
git diff --name-status origin/main..HEAD
git diff --check origin/main..HEAD
```

Expected branch diff before implementation:

```text
A       docs/superpowers/specs/2026-07-01-lm5h-local-worker-context-renderer-design.md
A       docs/superpowers/plans/2026-07-01-lm5h-local-worker-context-renderer.md
```

If local `main` is stale or shows unrelated work, use `origin/main` as the baseline.

---

## Task 1: Write Renderer Tests First

**Files:**

- Create: `mcp_server/tests/test_local_worker_turn_context_renderer.py`

- [ ] **Step 1.1: Add failing renderer test file**

Create `mcp_server/tests/test_local_worker_turn_context_renderer.py` with this content:

```python
from __future__ import annotations

import ast
import copy
import inspect
import math
from collections.abc import Mapping
from types import MappingProxyType

import pytest

from rook.agent import local_worker_turn_context as context_module
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
    render_local_worker_turn_context_payload,
)
from rook.agent.local_worker_turn_harness import run_local_worker_turn
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
    "workflow",
    "current_graph",
    "current_node",
    "history",
    "knowledge",
    "allowed_actions",
}
WORKFLOW_KEYS = {
    "workflow_id",
    "contract_schema",
    "contract_fingerprint",
    "compiler_id",
    "provider_id",
    "selected_template_id",
    "max_steps",
}
GRAPH_KEYS = {
    "node_count",
    "node_ids",
    "ready_node_ids",
    "terminal_node_ids",
    "status_counts",
}
NODE_KEYS = {
    "node_id",
    "intent",
    "role",
    "status",
    "execution_ref",
    "is_terminal",
    "has_execution_params",
    "memory_keys",
}
HISTORY_KEYS = {
    "current_step_count",
    "supply_count",
    "last_accepted_node_id",
    "last_execution_kind",
    "last_stop_reason",
    "recent_steps",
    "recent_supplies",
}
STEP_KEYS = {"accepted_node_id", "execution_kind", "ran", "failure"}
SUPPLY_KEYS = {"decision", "reason", "selected_node_id", "has_envelope"}
KNOWLEDGE_KEYS = {"packet_id", "kind", "title", "content"}
ACTION_KEYS = {"action_id", "kind", "description", "input_schema"}


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
                    "nested": {"count": -3, "enabled": True, "ratio": 1.5},
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
        workflow_id="lm5h_context_renderer",
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
                    "name": "LM5HContextRenderer",
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
        metadata={"trace": {"slice": "LM5H"}},
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


def _response_payload_from_context_payload(
    payload: Mapping[str, object],
) -> dict[str, object]:
    actions = payload["allowed_actions"]
    assert isinstance(actions, list)
    first_action = actions[0]
    assert isinstance(first_action, Mapping)
    action_id = first_action["action_id"]
    assert isinstance(action_id, str)
    return {
        "schema": LOCAL_WORKER_TURN_RESPONSE_SCHEMA,
        "kind": "action_request",
        "action_id": action_id,
        "rationale": "Use the first allowed action from the rendered context.",
        "input": {
            "code": "A = 42.0;",
            "mode": "body",
            "language": "csharp",
        },
    }


def test_public_schema_and_renderer_exports_are_present() -> None:
    assert LOCAL_WORKER_TURN_CONTEXT_SCHEMA == "rook.local_worker_turn_context:v1"
    assert "LOCAL_WORKER_TURN_CONTEXT_SCHEMA" in context_module.__all__
    assert "render_local_worker_turn_context_payload" in context_module.__all__


def test_rendered_payload_has_exact_shape_and_schema_value() -> None:
    payload = render_local_worker_turn_context_payload(_context())

    assert type(payload) is dict
    assert set(payload) == TOP_LEVEL_KEYS
    assert payload["schema"] == LOCAL_WORKER_TURN_CONTEXT_SCHEMA
    assert set(payload["workflow"]) == WORKFLOW_KEYS
    assert set(payload["current_graph"]) == GRAPH_KEYS
    assert set(payload["current_node"]) == NODE_KEYS
    assert set(payload["history"]) == HISTORY_KEYS
    assert set(payload["history"]["recent_steps"][0]) == STEP_KEYS
    assert set(payload["history"]["recent_supplies"][0]) == SUPPLY_KEYS
    assert set(payload["knowledge"][0]) == KNOWLEDGE_KEYS
    assert set(payload["allowed_actions"][0]) == ACTION_KEYS
    assert "response_schema" not in payload
    assert "instructions" not in payload
    assert "tools" not in payload
    assert "capabilities" not in payload


def test_rendered_payload_preserves_lm5a_field_names_and_values() -> None:
    context = _context()
    payload = render_local_worker_turn_context_payload(context)

    assert payload["workflow"]["workflow_id"] == context.workflow.workflow_id
    assert payload["workflow"]["max_steps"] == context.workflow.max_steps
    assert payload["current_graph"]["node_ids"] == [
        "create_script",
        "done",
        "repair_same_component",
    ]
    assert payload["current_graph"]["status_counts"] == {
        "pending": 1,
        "ready": 1,
        "terminal": 1,
    }
    assert payload["current_node"]["execution_ref"] == "gh_update_script:v1"
    assert payload["current_node"]["memory_keys"] == [
        "component_guid",
        "repair_anchor",
    ]
    assert payload["history"]["current_step_count"] == 2
    assert payload["history"]["recent_steps"][1]["failure"] == "needs_repair"
    assert payload["history"]["recent_supplies"][1]["selected_node_id"] == (
        "repair_same_component"
    )
    assert payload["knowledge"][0]["content"]["nested"]["count"] == -3
    assert payload["knowledge"][0]["content"]["nested"]["enabled"] is True
    assert payload["allowed_actions"][0]["input_schema"]["required"] == [
        "code",
        "mode",
    ]


def test_rendered_payload_uses_plain_mutable_json_ready_containers() -> None:
    payload = render_local_worker_turn_context_payload(_context())

    assert type(payload) is dict
    assert type(payload["workflow"]) is dict
    assert type(payload["current_graph"]["node_ids"]) is list
    assert type(payload["current_node"]["memory_keys"]) is list
    assert type(payload["history"]["recent_steps"]) is list
    assert type(payload["knowledge"]) is list
    assert type(payload["knowledge"][0]["content"]) is dict
    assert type(payload["knowledge"][0]["content"]["flags"]) is list
    assert type(payload["allowed_actions"]) is list
    assert type(payload["allowed_actions"][0]["input_schema"]) is dict
    assert not isinstance(payload["knowledge"][0]["content"], MappingProxyType)

    payload["workflow"]["workflow_id"] = "changed"
    payload["knowledge"][0]["content"]["flags"].append("mutated")
    payload["allowed_actions"][0]["input_schema"]["required"].append("language")

    assert payload["workflow"]["workflow_id"] == "changed"


def test_payload_mutation_does_not_affect_source_context() -> None:
    context = _context()
    payload = render_local_worker_turn_context_payload(context)

    payload["workflow"]["workflow_id"] = "changed"
    payload["knowledge"][0]["content"]["flags"].append("mutated")
    payload["knowledge"][0]["content"]["nested"]["enabled"] = False
    payload["allowed_actions"][0]["input_schema"]["required"].append("language")

    assert context.workflow.workflow_id == "repair_component"
    assert context.knowledge[0].content["flags"] == ("body", "repair")
    assert context.knowledge[0].content["nested"]["enabled"] is True
    assert context.allowed_actions[0].input_schema["required"] == ("code", "mode")


def test_current_node_none_renders_key_with_none_value() -> None:
    payload = render_local_worker_turn_context_payload(_context(current_node=False))

    assert set(payload) == TOP_LEVEL_KEYS
    assert "current_node" in payload
    assert payload["current_node"] is None


def test_renderer_rejects_non_context_input() -> None:
    with pytest.raises(TypeError, match="LocalWorkerTurnContext"):
        render_local_worker_turn_context_payload({"not": "context"})  # type: ignore[arg-type]


def test_renderer_defensively_rejects_non_string_mapping_keys() -> None:
    context = _context()
    object.__setattr__(context.knowledge[0], "content", {1: "bad"})

    with pytest.raises(TypeError, match="keys must be strings"):
        render_local_worker_turn_context_payload(context)


@pytest.mark.parametrize("bad_float", [math.inf, -math.inf, math.nan])
def test_renderer_defensively_rejects_non_finite_floats(bad_float: float) -> None:
    context = _context()
    object.__setattr__(context.knowledge[0], "content", {"bad": bad_float})

    with pytest.raises(TypeError, match="finite"):
        render_local_worker_turn_context_payload(context)


def test_renderer_preserves_bool_and_int_values_distinctly() -> None:
    payload = render_local_worker_turn_context_payload(_context())

    nested = payload["knowledge"][0]["content"]["nested"]
    assert nested["enabled"] is True
    assert nested["count"] == -3
    assert type(nested["count"]) is int


def test_renderer_function_body_boundary_guard() -> None:
    source = inspect.getsource(context_module)
    tree = ast.parse(source)
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    target_names = {
        name
        for name in functions
        if name == "render_local_worker_turn_context_payload"
        or name.startswith("_render_")
    }

    assert "render_local_worker_turn_context_payload" in target_names
    assert "_render_json_value" in target_names

    banned_names = {
        "build_local_worker_turn_context",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "validate_local_worker_turn_response",
        "load_local_worker_turn_response_payload",
        "dispose_local_worker_turn_response",
        "run_local_worker_turn",
        "evaluate_local_worker_scenario_result",
        "build_local_worker_scenario_report",
        "LOCAL_WORKER_TURN_RESPONSE_SCHEMA",
        "WorkerActionRequest",
        "WorkerClarificationRequest",
        "WorkerRefusal",
        "WorkerObservation",
        "LocalWorkerTurnResponse",
        "Path",
        "open",
        "json",
        "loads",
        "dumps",
        "model",
        "RookChat",
        "prompt",
        "dispatcher",
        "stream",
        "runtime",
        "CapabilityIndex",
    }
    banned_attributes = {"loads", "dumps"}

    for target_name in sorted(target_names):
        node = functions[target_name]
        referenced_names = {
            child.id for child in ast.walk(node) if isinstance(child, ast.Name)
        }
        referenced_attributes = {
            child.attr for child in ast.walk(node) if isinstance(child, ast.Attribute)
        }
        assert not (referenced_names & banned_names), target_name
        assert not (referenced_attributes & banned_attributes), target_name


def test_rendered_context_payload_composes_with_lm5g_lm5d_and_lm5f() -> None:
    context = _compiled_context()
    payload = render_local_worker_turn_context_payload(context)
    response_payload = _response_payload_from_context_payload(payload)

    assert payload["current_node"]["execution_ref"] == "gh_update_script:v1"
    assert response_payload["action_id"] == "draft_repair_params"
    assert response_payload["action_id"] != payload["current_node"]["execution_ref"]

    response = load_local_worker_turn_response_payload(response_payload)
    harness_record = run_local_worker_turn(context, lambda received: response)

    result = evaluate_local_worker_scenario_result(
        LocalWorkerScenarioExpectation(
            scenario_id="rendered_context_payload_chain",
            category="renderer_integration",
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

- [ ] **Step 1.2: Run targeted renderer tests to verify RED**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context_renderer.py
```

Expected failure:

```text
ImportError: cannot import name 'LOCAL_WORKER_TURN_CONTEXT_SCHEMA'
```

The exact first missing symbol may be `render_local_worker_turn_context_payload`.
Either is an acceptable RED failure.

---

## Task 2: Implement Public Renderer

**Files:**

- Modify: `mcp_server/src/rook/agent/local_worker_turn_context.py`

- [ ] **Step 2.1: Add schema constant and public exports**

In `mcp_server/src/rook/agent/local_worker_turn_context.py`, add the schema
constant near the public surface definitions:

```python
LOCAL_WORKER_TURN_CONTEXT_SCHEMA = "rook.local_worker_turn_context:v1"
```

Update `__all__` exactly by adding only the two LM5H public names:

```python
__all__ = (
    "LOCAL_WORKER_TURN_CONTEXT_SCHEMA",
    "LocalWorkerTurnContext",
    "WorkerWorkflowSummary",
    "WorkerGraphSummary",
    "WorkerNodeSummary",
    "WorkerHistorySummary",
    "WorkerStepTraceSummary",
    "WorkerSupplyTraceSummary",
    "WorkerKnowledgePacket",
    "WorkerAllowedAction",
    "build_local_worker_turn_context",
    "render_local_worker_turn_context_payload",
)
```

- [ ] **Step 2.2: Add renderer after `LocalWorkerTurnContext`**

Add this code after the `LocalWorkerTurnContext` dataclass and before
`build_local_worker_turn_context(...)`:

```python
def render_local_worker_turn_context_payload(
    context: LocalWorkerTurnContext,
) -> Mapping[str, Any]:
    if not isinstance(context, LocalWorkerTurnContext):
        raise TypeError("context must be LocalWorkerTurnContext")

    return {
        "schema": LOCAL_WORKER_TURN_CONTEXT_SCHEMA,
        "workflow": _render_workflow_summary(context.workflow),
        "current_graph": _render_graph_summary(context.current_graph),
        "current_node": (
            None
            if context.current_node is None
            else _render_node_summary(context.current_node)
        ),
        "history": _render_history_summary(context.history),
        "knowledge": [
            _render_knowledge_packet(packet)
            for packet in context.knowledge
        ],
        "allowed_actions": [
            _render_allowed_action(action)
            for action in context.allowed_actions
        ],
    }
```

- [ ] **Step 2.3: Add private render helpers**

Place these helpers near the existing private summary/freezing helpers. Keep all
names starting with `_render_` so the function-scoped AST guard covers them:

```python
def _render_workflow_summary(summary: WorkerWorkflowSummary) -> dict[str, Any]:
    return {
        "workflow_id": summary.workflow_id,
        "contract_schema": summary.contract_schema,
        "contract_fingerprint": summary.contract_fingerprint,
        "compiler_id": summary.compiler_id,
        "provider_id": summary.provider_id,
        "selected_template_id": summary.selected_template_id,
        "max_steps": summary.max_steps,
    }


def _render_graph_summary(summary: WorkerGraphSummary) -> dict[str, Any]:
    return {
        "node_count": summary.node_count,
        "node_ids": _render_json_value(summary.node_ids),
        "ready_node_ids": _render_json_value(summary.ready_node_ids),
        "terminal_node_ids": _render_json_value(summary.terminal_node_ids),
        "status_counts": _render_json_value(summary.status_counts),
    }


def _render_node_summary(summary: WorkerNodeSummary) -> dict[str, Any]:
    return {
        "node_id": summary.node_id,
        "intent": summary.intent,
        "role": summary.role,
        "status": summary.status,
        "execution_ref": summary.execution_ref,
        "is_terminal": summary.is_terminal,
        "has_execution_params": summary.has_execution_params,
        "memory_keys": _render_json_value(summary.memory_keys),
    }


def _render_history_summary(summary: WorkerHistorySummary) -> dict[str, Any]:
    return {
        "current_step_count": summary.current_step_count,
        "supply_count": summary.supply_count,
        "last_accepted_node_id": summary.last_accepted_node_id,
        "last_execution_kind": summary.last_execution_kind,
        "last_stop_reason": summary.last_stop_reason,
        "recent_steps": [
            _render_step_trace_summary(step)
            for step in summary.recent_steps
        ],
        "recent_supplies": [
            _render_supply_trace_summary(supply)
            for supply in summary.recent_supplies
        ],
    }


def _render_step_trace_summary(
    summary: WorkerStepTraceSummary,
) -> dict[str, Any]:
    return {
        "accepted_node_id": summary.accepted_node_id,
        "execution_kind": summary.execution_kind,
        "ran": summary.ran,
        "failure": summary.failure,
    }


def _render_supply_trace_summary(
    summary: WorkerSupplyTraceSummary,
) -> dict[str, Any]:
    return {
        "decision": summary.decision,
        "reason": summary.reason,
        "selected_node_id": summary.selected_node_id,
        "has_envelope": summary.has_envelope,
    }


def _render_knowledge_packet(packet: WorkerKnowledgePacket) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "kind": packet.kind,
        "title": packet.title,
        "content": _render_json_value(packet.content),
    }


def _render_allowed_action(action: WorkerAllowedAction) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "kind": action.kind,
        "description": action.description,
        "input_schema": _render_json_value(action.input_schema),
    }


def _render_json_value(value: object) -> Any:
    if isinstance(value, Mapping):
        rendered: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("context payload mapping keys must be strings")
            rendered[key] = _render_json_value(item)
        return rendered
    if isinstance(value, (list, tuple)):
        return [_render_json_value(item) for item in value]
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("context payload float values must be finite")
        return value
    raise TypeError("context payload contains unsupported value")
```

Do not import response-loader symbols, LM5B response dataclasses, LM5C/D/F
helpers, `json`, `Path`, file IO, prompt/model surfaces, or Capability Index
surfaces.

- [ ] **Step 2.4: Run targeted renderer tests to verify GREEN**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context_renderer.py
```

Expected: all renderer tests pass.

---

## Task 3: Update Existing Public Surface Test

**Files:**

- Modify: `mcp_server/tests/test_local_worker_turn_context.py`

- [ ] **Step 3.1: Update canonical `__all__` assertion**

Find `test_public_surface_is_explicit` and update the expected set to include
only the two LM5H public additions:

```python
def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_context as module

    assert set(module.__all__) == {
        "LOCAL_WORKER_TURN_CONTEXT_SCHEMA",
        "LocalWorkerTurnContext",
        "WorkerWorkflowSummary",
        "WorkerGraphSummary",
        "WorkerNodeSummary",
        "WorkerHistorySummary",
        "WorkerStepTraceSummary",
        "WorkerSupplyTraceSummary",
        "WorkerKnowledgePacket",
        "WorkerAllowedAction",
        "build_local_worker_turn_context",
        "render_local_worker_turn_context_payload",
    }
```

No other assertions in this existing test file should change.

- [ ] **Step 3.2: Run context and renderer tests**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py
```

Expected: both test files pass.

---

## Task 4: Nearby Regression

**Files:** None

- [ ] **Step 4.1: Run nearby LM5 tests**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest `
  mcp_server\tests\test_local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py `
  mcp_server\tests\test_local_worker_turn_response.py `
  mcp_server\tests\test_local_worker_turn_response_loader.py `
  mcp_server\tests\test_local_worker_turn_harness.py `
  mcp_server\tests\test_local_worker_scenario_evaluation.py
```

Expected: all nearby tests pass.

---

## Task 5: Focused PlanGraph / Local-Worker Gate

**Files:** None

- [ ] **Step 5.1: Run focused gate with explicit PowerShell file list**

Run:

```powershell
$files = @(Get-ChildItem -Path mcp_server\tests -Filter 'test_plan_graph*.py' |
  Sort-Object Name |
  ForEach-Object { $_.FullName })
$files += @(Resolve-Path `
  mcp_server\tests\test_local_worker_turn_context.py, `
  mcp_server\tests\test_local_worker_turn_context_renderer.py, `
  mcp_server\tests\test_local_worker_turn_response.py, `
  mcp_server\tests\test_local_worker_turn_response_loader.py, `
  mcp_server\tests\test_local_worker_turn_disposition.py, `
  mcp_server\tests\test_local_worker_turn_harness.py, `
  mcp_server\tests\test_local_worker_turn_scenarios.py, `
  mcp_server\tests\test_local_worker_scenario_evaluation.py |
  ForEach-Object { $_.Path })
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m pytest @files
```

Expected: focused gate passes.

---

## Task 6: Static Scope And Boundary Checks

**Files:** None

- [ ] **Step 6.1: Run diff hygiene and scope checks**

Run:

```powershell
git status --short --branch
git diff --check origin/main
git diff --name-status origin/main
git diff --name-only origin/main -- src/Rook src/RookNative operations_knowledge.json knowledge
```

Before staging, `git status --short` may show the new renderer test as
untracked. It must be the only untracked file introduced by LM5H.

Expected changed files after staging or commit:

```text
A       docs/superpowers/specs/2026-07-01-lm5h-local-worker-context-renderer-design.md
A       docs/superpowers/plans/2026-07-01-lm5h-local-worker-context-renderer.md
M       mcp_server/src/rook/agent/local_worker_turn_context.py
M       mcp_server/tests/test_local_worker_turn_context.py
A       mcp_server/tests/test_local_worker_turn_context_renderer.py
```

Expected guarded-area diff:

```text
<no output>
```

- [ ] **Step 6.2: Run production boundary scans**

Run:

```powershell
rg -n "json\.loads|json\.dumps|from json|import json|Path\(|open\(" `
  mcp_server\src\rook\agent\local_worker_turn_context.py
rg -n "LOCAL_WORKER_TURN_RESPONSE_SCHEMA|load_local_worker_turn_response_payload|WorkerActionRequest|LocalWorkerTurnResponse|dispose_local_worker_turn_response|run_local_worker_turn|evaluate_local_worker_scenario_result|build_local_worker_scenario_report" `
  mcp_server\src\rook\agent\local_worker_turn_context.py
```

Expected: no output. The authoritative guard is the function-scoped AST test in
`test_local_worker_turn_context_renderer.py`, which must pass.

- [ ] **Step 6.3: Run compile checks**

Run:

```powershell
C:\UDEV\Rook\mcp_server\.venv\Scripts\python.exe -m py_compile `
  mcp_server\src\rook\agent\local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py
py -3.10 -m py_compile `
  mcp_server\src\rook\agent\local_worker_turn_context.py `
  mcp_server\tests\test_local_worker_turn_context_renderer.py
```

Expected: both commands exit successfully.

---

## Task 7: Commit Implementation

**Files:**

- Modify: `mcp_server/src/rook/agent/local_worker_turn_context.py`
- Modify: `mcp_server/tests/test_local_worker_turn_context.py`
- Create: `mcp_server/tests/test_local_worker_turn_context_renderer.py`
- Modify: `docs/superpowers/plans/2026-07-01-lm5h-local-worker-context-renderer.md` only if execution revealed a legitimate plan correction

- [ ] **Step 7.1: Stage only intended LM5H files**

Run:

```powershell
git add -- `
  docs/superpowers/plans/2026-07-01-lm5h-local-worker-context-renderer.md `
  mcp_server/src/rook/agent/local_worker_turn_context.py `
  mcp_server/tests/test_local_worker_turn_context.py `
  mcp_server/tests/test_local_worker_turn_context_renderer.py
git status --short --branch
```

Expected staged files are exactly the implementation/test files above plus the
plan only if it changed during execution.

- [ ] **Step 7.2: Commit implementation**

Run:

```powershell
git commit -m "feat(lm5h): render local worker context payloads"
```

Expected: commit succeeds.

- [ ] **Step 7.3: Post-commit scope receipt**

Run:

```powershell
git status --short --branch
git diff --name-status origin/main..HEAD
git diff --check origin/main..HEAD
```

Expected:

```text
working tree clean
branch ahead of origin/main
diff check clean
```

---

## Task 8: Review And Finish

**Files:** None

- [ ] **Step 8.1: Request fresh review**

Use `superpowers:requesting-code-review` or a subagent review. Ask the reviewer
to check:

- outbound renderer only;
- full LM5A field projection;
- exact key sets and schema value;
- mutable JSON-ready copy with no source aliasing;
- no response protocol leakage;
- no LM5G production imports;
- function-scoped guard accuracy;
- integration test composes through LM5G/D/F only in tests.

- [ ] **Step 8.2: Address findings**

If findings appear, patch them, rerun targeted/nearby/focused gates as needed,
and amend or add a follow-up commit.

- [ ] **Step 8.3: Use finishing branch workflow**

After review is clean and gates pass, use `superpowers:finishing-a-development-branch`.

Recommended completion option:

```text
Push and create a Pull Request.
```
