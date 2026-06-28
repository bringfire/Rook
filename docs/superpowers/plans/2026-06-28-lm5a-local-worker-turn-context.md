# LM5A Local Worker Turn Context Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic, model-free worker-consumption boundary that summarizes an LM4 compiled scaffold, current graph snapshot, stream history, pushed knowledge, and allowed action descriptors into a frozen `LocalWorkerTurnContext`.

**Architecture:** One new agent-layer adapter module creates worker-facing facts from existing LM4 artifacts. It does not select, map, execute, stream, compile, load payloads, call models, or expose raw LM4 objects.

**Tech Stack:** Python dataclasses, `MappingProxyType`, pytest, AST import/call boundary checks.

---

## Overview

LM5A begins the worker phase without calling a worker. It defines the input artifact a future local/internal model or workflow tool may consume for one caller-declared turn.

The implementation adds:

- `mcp_server/src/rook/agent/local_worker_turn_context.py`
- `mcp_server/tests/test_local_worker_turn_context.py`

It must not change existing runtime, compiler, provider, stream, chat, live Rhino/GH, or model behavior.

The central public API is:

```python
build_local_worker_turn_context(
    scaffold: CompiledWorkflowScaffold,
    graph: PlanGraph,
    records: tuple[CurrentStepRecord, ...] | list[CurrentStepRecord],
    supply_records: tuple[EnvelopeSupplyRecord, ...] | list[EnvelopeSupplyRecord],
    *,
    current_node_id: str | None,
    knowledge: tuple[WorkerKnowledgePacket, ...] | list[WorkerKnowledgePacket],
    allowed_actions: tuple[WorkerAllowedAction, ...] | list[WorkerAllowedAction],
    history_limit: int = 5,
) -> LocalWorkerTurnContext
```

No raw `PlanGraph`, `CompiledWorkflowScaffold`, `CurrentStepRecord`, `EnvelopeSupplyRecord`, mappings, providers, or callables appear in the returned context.

---

## Task 1: Add Failing LM5A Tests

**Purpose:** Lock the public worker context contract before implementation.

**Files:**

- Add `mcp_server/tests/test_local_worker_turn_context.py`

**Implementation:**

Create the complete test file:

```python
from __future__ import annotations

import ast
import copy
import math
from collections.abc import Mapping
from pathlib import Path

import pytest

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
from rook.learning.plan_graph import PlanGraph

from rook.agent.local_worker_turn_context import (
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


def _repair_contract() -> RookWorkflowContract:
    return RookWorkflowContract(
        workflow_id="lm5a_worker_context",
        template=WorkflowTemplateRef(
            descriptor={
                "goal": "create csharp script and repair it",
                "tool": "grasshopper",
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
                    "name": "LM5ALocalWorkerTurnContext",
                    "x": 350,
                    "y": 1120,
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
        metadata={"trace": {"slice": "LM5A"}},
    )


def _scaffold():
    return compile_workflow_contract(_repair_contract())


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


def _knowledge(packet_id: str = "k1") -> WorkerKnowledgePacket:
    return WorkerKnowledgePacket(
        packet_id=packet_id,
        kind="graph_hint",
        title="Repair anchor",
        content={"facts": {"target": "repair_same_component"}, "tags": ["repair"]},
    )


def _action(action_id: str = "a1") -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=action_id,
        kind="draft_bind_params",
        description="Draft replacement C# body parameters.",
        input_schema={
            "type": "object",
            "properties": {
                "code": {"type": "string"},
            },
            "required": ["code"],
        },
    )


def test_public_surface_is_explicit() -> None:
    import rook.agent.local_worker_turn_context as module

    assert set(module.__all__) == {
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
    }


def test_packet_and_action_freeze_payloads_on_direct_construction() -> None:
    knowledge_payload = {"nested": {"tags": ["before"]}}
    packet = WorkerKnowledgePacket(
        packet_id="packet",
        kind="reference",
        title="Reference",
        content=knowledge_payload,
    )

    action_payload = {"properties": {"code": {"type": "string"}}}
    action = WorkerAllowedAction(
        action_id="action",
        kind="draft",
        description="Draft a response.",
        input_schema=action_payload,
    )

    knowledge_payload["nested"]["tags"].append("after")
    action_payload["properties"]["code"]["type"] = "number"

    assert packet.content["nested"]["tags"] == ("before",)
    assert action.input_schema["properties"]["code"]["type"] == "string"

    with pytest.raises(TypeError):
        packet.content["nested"]["late"] = True

    with pytest.raises(TypeError):
        action.input_schema["properties"]["late"] = True


def test_build_context_summarizes_real_compiled_scaffold_without_raw_objects() -> None:
    scaffold = _scaffold()
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts["component_guid"] = "abc"
    graph.memory.facts["repair_anchor"] = {"component_guid": "abc"}

    records = (
        _record(accepted_node_id="create_script", execution_kind="producer"),
        _record(accepted_node_id="verify_create", execution_kind="verifier"),
        _record(
            accepted_node_id="repair_same_component",
            execution_kind="bind",
            ran=False,
            execution_failure="bind_missing",
        ),
    )
    supplies = (
        _supply(selected_node_id="create_script"),
        _supply(selected_node_id="verify_create"),
        _supply(selected_node_id="repair_same_component"),
        _supply(
            decision="HALT",
            reason="terminal_node_selected:done",
            selected_node_id="done",
            envelope=None,
        ),
    )

    context = build_local_worker_turn_context(
        scaffold,
        graph,
        records,
        supplies,
        current_node_id="create_script",
        knowledge=[_knowledge()],
        allowed_actions=[_action()],
        history_limit=2,
    )

    assert isinstance(context, LocalWorkerTurnContext)
    assert isinstance(context.workflow, WorkerWorkflowSummary)
    assert context.workflow.workflow_id == scaffold.workflow_id
    assert (
        context.workflow.contract_fingerprint
        == scaffold.compile_record.contract_fingerprint
    )
    assert context.workflow.max_steps == scaffold.max_steps

    assert isinstance(context.current_graph, WorkerGraphSummary)
    assert context.current_graph.node_count == len(graph.nodes)
    assert context.current_graph.node_ids == tuple(sorted(graph.nodes))
    assert "create_script" in context.current_graph.ready_node_ids
    assert context.current_graph.terminal_node_ids == ("done",)
    assert context.current_graph.status_counts["ready"] >= 1

    assert isinstance(context.current_node, WorkerNodeSummary)
    assert context.current_node.node_id == "create_script"
    assert context.current_node.intent
    assert context.current_node.execution_ref == "gh_create_csharp_script:v1"
    assert context.current_node.is_terminal is False
    assert context.current_node.has_execution_params is True
    assert context.current_node.memory_keys == ("component_guid", "repair_anchor")
    assert isinstance(context.current_node.role, str) or context.current_node.role is None

    assert isinstance(context.history, WorkerHistorySummary)
    assert context.history.current_step_count == 3
    assert context.history.supply_count == 4
    assert context.history.last_accepted_node_id == "repair_same_component"
    assert context.history.last_execution_kind == "bind"
    assert context.history.last_stop_reason == "terminal_node_selected:done"
    assert context.history.recent_steps == (
        WorkerStepTraceSummary(
            accepted_node_id="verify_create",
            execution_kind="verifier",
            ran=True,
            failure=None,
        ),
        WorkerStepTraceSummary(
            accepted_node_id="repair_same_component",
            execution_kind="bind",
            ran=False,
            failure="bind_missing",
        ),
    )
    assert context.history.recent_supplies[-1] == WorkerSupplyTraceSummary(
        decision="HALT",
        reason="terminal_node_selected:done",
        selected_node_id="done",
        has_envelope=False,
    )

    assert context.knowledge == (_knowledge(),)
    assert context.allowed_actions == (_action(),)
    assert not hasattr(context, "scaffold")
    assert not hasattr(context, "graph")
    assert not hasattr(context, "records")
    assert not hasattr(context, "supply_records")
    assert all(
        not isinstance(step, CurrentStepRecord)
        for step in context.history.recent_steps
    )
    assert all(
        not isinstance(supply, EnvelopeSupplyRecord)
        for supply in context.history.recent_supplies
    )


def test_current_node_none_produces_global_context_without_node_summary() -> None:
    scaffold = _scaffold()

    context = build_local_worker_turn_context(
        scaffold,
        scaffold.graph,
        (),
        (),
        current_node_id=None,
        knowledge=(),
        allowed_actions=(),
    )

    assert context.current_node is None


def test_current_node_does_not_need_to_be_ready() -> None:
    scaffold = _scaffold()
    graph = copy.deepcopy(scaffold.graph)

    assert graph.nodes["verify_repair"].status == "pending"
    context = build_local_worker_turn_context(
        scaffold,
        graph,
        (),
        (),
        current_node_id="verify_repair",
        knowledge=(),
        allowed_actions=(),
    )

    assert context.current_node is not None
    assert context.current_node.node_id == "verify_repair"
    assert context.current_node.status == "pending"


@pytest.mark.parametrize("bad_current_node_id", [123, object(), False])
def test_current_node_id_wrong_type_rejected(bad_current_node_id: object) -> None:
    scaffold = _scaffold()

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=bad_current_node_id,  # type: ignore[arg-type]
            knowledge=(),
            allowed_actions=(),
        )


@pytest.mark.parametrize("bad_current_node_id", ["", "missing"])
def test_current_node_id_bad_value_rejected(bad_current_node_id: str) -> None:
    scaffold = _scaffold()

    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=bad_current_node_id,
            knowledge=(),
            allowed_actions=(),
        )


@pytest.mark.parametrize("bad_history_limit", [0, -1])
def test_history_limit_bad_value_rejected(bad_history_limit: int) -> None:
    scaffold = _scaffold()

    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
            history_limit=bad_history_limit,
        )


@pytest.mark.parametrize("bad_history_limit", [True, 1.5, "2"])
def test_history_limit_bad_type_rejected(bad_history_limit: object) -> None:
    scaffold = _scaffold()

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
            history_limit=bad_history_limit,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field_name", "bad_value"),
    [
        ("scaffold", object()),
        ("graph", object()),
        ("records", object()),
        ("supply_records", object()),
        ("knowledge", object()),
        ("allowed_actions", object()),
    ],
)
def test_builder_wrong_input_shapes_are_type_errors(
    field_name: str,
    bad_value: object,
) -> None:
    scaffold = _scaffold()
    kwargs = {
        "scaffold": scaffold,
        "graph": scaffold.graph,
        "records": (),
        "supply_records": (),
        "current_node_id": None,
        "knowledge": (),
        "allowed_actions": (),
    }
    kwargs[field_name] = bad_value

    with pytest.raises(TypeError):
        build_local_worker_turn_context(**kwargs)  # type: ignore[arg-type]


def test_builder_rejects_wrong_history_item_types() -> None:
    scaffold = _scaffold()

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            [object()],  # type: ignore[list-item]
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
        )

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            [object()],  # type: ignore[list-item]
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
        )


def test_builder_rejects_wrong_packet_and_action_item_types() -> None:
    scaffold = _scaffold()

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=None,
            knowledge=[object()],  # type: ignore[list-item]
            allowed_actions=(),
        )

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=[object()],  # type: ignore[list-item]
        )


def test_duplicate_packet_and_action_ids_rejected() -> None:
    scaffold = _scaffold()

    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=None,
            knowledge=[_knowledge("same"), _knowledge("same")],
            allowed_actions=(),
        )

    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            scaffold,
            scaffold.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=[_action("same"), _action("same")],
        )


@pytest.mark.parametrize(
    "packet_kwargs",
    [
        {"packet_id": "", "kind": "kind", "title": None, "content": {}},
        {"packet_id": "id", "kind": "", "title": None, "content": {}},
    ],
)
def test_knowledge_packet_empty_values_rejected(packet_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkerKnowledgePacket(**packet_kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "packet_kwargs",
    [
        {"packet_id": 1, "kind": "kind", "title": None, "content": {}},
        {"packet_id": "id", "kind": 1, "title": None, "content": {}},
        {"packet_id": "id", "kind": "kind", "title": 1, "content": {}},
        {"packet_id": "id", "kind": "kind", "title": None, "content": []},
        {"packet_id": "id", "kind": "kind", "title": None, "content": {1: "bad"}},
        {
            "packet_id": "id",
            "kind": "kind",
            "title": None,
            "content": {"bad": object()},
        },
        {
            "packet_id": "id",
            "kind": "kind",
            "title": None,
            "content": {"bad": math.inf},
        },
    ],
)
def test_knowledge_packet_bad_types_rejected(packet_kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerKnowledgePacket(**packet_kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "action_kwargs",
    [
        {
            "action_id": "",
            "kind": "kind",
            "description": "description",
            "input_schema": {},
        },
        {
            "action_id": "id",
            "kind": "",
            "description": "description",
            "input_schema": {},
        },
        {
            "action_id": "id",
            "kind": "kind",
            "description": "",
            "input_schema": {},
        },
    ],
)
def test_allowed_action_empty_values_rejected(action_kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        WorkerAllowedAction(**action_kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "action_kwargs",
    [
        {
            "action_id": 1,
            "kind": "kind",
            "description": "description",
            "input_schema": {},
        },
        {
            "action_id": "id",
            "kind": 1,
            "description": "description",
            "input_schema": {},
        },
        {
            "action_id": "id",
            "kind": "kind",
            "description": 1,
            "input_schema": {},
        },
        {
            "action_id": "id",
            "kind": "kind",
            "description": "description",
            "input_schema": [],
        },
        {
            "action_id": "id",
            "kind": "kind",
            "description": "description",
            "input_schema": {1: "bad"},
        },
        {
            "action_id": "id",
            "kind": "kind",
            "description": "description",
            "input_schema": {"bad": object()},
        },
    ],
)
def test_allowed_action_bad_types_rejected(action_kwargs: dict[str, object]) -> None:
    with pytest.raises(TypeError):
        WorkerAllowedAction(**action_kwargs)  # type: ignore[arg-type]


def test_context_is_detached_from_caller_sequences() -> None:
    scaffold = _scaffold()
    knowledge = [_knowledge()]
    actions = [_action()]

    context = build_local_worker_turn_context(
        scaffold,
        scaffold.graph,
        [],
        [],
        current_node_id=None,
        knowledge=knowledge,
        allowed_actions=actions,
    )

    knowledge.append(_knowledge("late"))
    actions.append(_action("late"))

    assert len(context.knowledge) == 1
    assert len(context.allowed_actions) == 1


def test_malformed_graph_memory_rejected() -> None:
    scaffold = _scaffold()
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts = [(1, "not mapping")]  # type: ignore[assignment]

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            graph,
            (),
            (),
            current_node_id="create_script",
            knowledge=(),
            allowed_actions=(),
        )


def test_non_string_graph_memory_key_rejected() -> None:
    scaffold = _scaffold()
    graph = copy.deepcopy(scaffold.graph)
    graph.memory.facts[1] = "bad"  # type: ignore[index]

    with pytest.raises(TypeError):
        build_local_worker_turn_context(
            scaffold,
            graph,
            (),
            (),
            current_node_id="create_script",
            knowledge=(),
            allowed_actions=(),
        )


def test_scaffold_identity_mismatches_are_value_errors() -> None:
    scaffold = _scaffold()

    bad_workflow = copy.copy(scaffold)
    object.__setattr__(bad_workflow.compile_record, "workflow_id", "other")
    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            bad_workflow,
            bad_workflow.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
        )

    bad_fingerprint = copy.copy(scaffold)
    object.__setattr__(bad_fingerprint.compile_record, "contract_fingerprint", "0" * 64)
    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            bad_fingerprint,
            bad_fingerprint.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
        )

    bad_schema = copy.copy(scaffold)
    object.__setattr__(bad_schema.compile_record, "contract_schema", "other")
    with pytest.raises(ValueError):
        build_local_worker_turn_context(
            bad_schema,
            bad_schema.graph,
            (),
            (),
            current_node_id=None,
            knowledge=(),
            allowed_actions=(),
        )


def test_supply_summary_ignores_malformed_metadata() -> None:
    scaffold = _scaffold()
    supply = EnvelopeSupplyRecord(
        decision="SUPPLY",
        envelope=object(),
        reason=None,
        metadata="not mapping",  # type: ignore[arg-type]
    )

    context = build_local_worker_turn_context(
        scaffold,
        scaffold.graph,
        (),
        (supply,),
        current_node_id=None,
        knowledge=(),
        allowed_actions=(),
    )

    assert context.history.recent_supplies == (
        WorkerSupplyTraceSummary(
            decision="SUPPLY",
            reason=None,
            selected_node_id=None,
            has_envelope=True,
        ),
    )


def test_history_reason_precedence_uses_invalid_reason_reason_then_error_class() -> None:
    scaffold = _scaffold()

    invalid = _supply(
        decision="SUPPLY",
        invalid_reason="supply_missing_envelope",
        reason="ignored",
        error_class="IgnoredError",
        envelope=None,
    )
    provider_halt = _supply(
        decision="HALT",
        reason="terminal_node_selected:done",
        envelope=None,
    )
    provider_error = _supply(
        decision=None,
        error_class="ProviderBoom",
        envelope=None,
    )

    context = build_local_worker_turn_context(
        scaffold,
        scaffold.graph,
        (),
        (invalid, provider_halt, provider_error),
        current_node_id=None,
        knowledge=(),
        allowed_actions=(),
    )

    assert [supply.reason for supply in context.history.recent_supplies] == [
        "supply_missing_envelope",
        "terminal_node_selected:done",
        "ProviderBoom",
    ]
    assert context.history.last_stop_reason == "ProviderBoom"


def test_local_worker_module_boundary_is_pure_context_builder() -> None:
    import rook.agent.local_worker_turn_context as module

    source = Path(module.__file__).read_text(encoding="utf-8")
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
        "collections.abc",
        "dataclasses",
        "math",
        "types",
        "typing",
        "rook.agent.plan_graph_current_step_runner",
        "rook.agent.plan_graph_current_step_stream",
        "rook.agent.plan_graph_live",
        "rook.agent.plan_graph_workflow_contract",
        "rook.learning.plan_graph",
        "rook.learning.plan_graph_projection",
    }
    assert imported_modules <= allowed_import_modules

    banned_names = {
        "propose_next_node",
        "map_accepted_proposal_to_step",
        "revalidate_proposal",
        "execute_mapped_step",
        "run_current_mapped_step",
        "run_current_step_stream",
        "EnvelopeSupplyResult",
        "CatalogCurrentStepProvider",
        "WorkflowProvenanceEnvelopeSource",
        "compile_workflow_contract",
        "load_workflow_contract_payload",
        "snapshot_workflow_contract",
        "RookAgent",
        "base_agent",
        "dispatcher",
        "server",
        "model",
        "litellm",
        "OpenAI",
        "Path",
        "open",
        "json",
        "yaml",
        "loads",
        "dumps",
    }
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not ({"open", "loads", "dumps"} & called_names)
```

**Run:**

```powershell
python -m pytest mcp_server/tests/test_local_worker_turn_context.py -q
```

**Expected failure before implementation:**

```text
ModuleNotFoundError: No module named 'rook.agent.local_worker_turn_context'
```

**Commit:**

```powershell
git add mcp_server/tests/test_local_worker_turn_context.py
git commit -m "test(lm5a): add local worker turn context tests"
```

---

## Task 2: Implement Local Worker Turn Context Module

**Purpose:** Add the frozen worker-facing context surface and builder.

**Files:**

- Add `mcp_server/src/rook/agent/local_worker_turn_context.py`

**Implementation:**

Create the complete production module:

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from types import MappingProxyType
from typing import Any

from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import EnvelopeSupplyRecord
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import CompiledWorkflowScaffold
from rook.learning.plan_graph import PlanGraph
from rook.learning.plan_graph_projection import projection_role_for_node

__all__ = (
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
)


@dataclass(frozen=True)
class WorkerWorkflowSummary:
    workflow_id: str
    contract_schema: str
    contract_fingerprint: str
    compiler_id: str
    provider_id: str
    selected_template_id: str
    max_steps: int

    def __post_init__(self) -> None:
        _require_non_empty_str(self.workflow_id, "workflow_id")
        _require_non_empty_str(self.contract_schema, "contract_schema")
        _require_non_empty_str(self.contract_fingerprint, "contract_fingerprint")
        _require_non_empty_str(self.compiler_id, "compiler_id")
        _require_non_empty_str(self.provider_id, "provider_id")
        _require_non_empty_str(self.selected_template_id, "selected_template_id")
        _require_positive_int(self.max_steps, "max_steps")


@dataclass(frozen=True)
class WorkerGraphSummary:
    node_count: int
    node_ids: tuple[str, ...]
    ready_node_ids: tuple[str, ...]
    terminal_node_ids: tuple[str, ...]
    status_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.node_count, "node_count")
        object.__setattr__(
            self,
            "node_ids",
            _freeze_str_tuple(self.node_ids, "node_ids"),
        )
        object.__setattr__(
            self,
            "ready_node_ids",
            _freeze_str_tuple(self.ready_node_ids, "ready_node_ids"),
        )
        object.__setattr__(
            self,
            "terminal_node_ids",
            _freeze_str_tuple(self.terminal_node_ids, "terminal_node_ids"),
        )
        object.__setattr__(
            self,
            "status_counts",
            _freeze_count_mapping(self.status_counts, "status_counts"),
        )


@dataclass(frozen=True)
class WorkerNodeSummary:
    node_id: str
    intent: str
    role: str | None
    status: str
    execution_ref: str | None
    is_terminal: bool
    has_execution_params: bool
    memory_keys: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.node_id, "node_id")
        _require_str(self.intent, "intent")
        _require_optional_str(self.role, "role")
        _require_str(self.status, "status")
        _require_optional_str(self.execution_ref, "execution_ref")
        _require_bool(self.is_terminal, "is_terminal")
        _require_bool(self.has_execution_params, "has_execution_params")
        object.__setattr__(
            self,
            "memory_keys",
            _freeze_str_tuple(self.memory_keys, "memory_keys"),
        )


@dataclass(frozen=True)
class WorkerStepTraceSummary:
    accepted_node_id: str | None
    execution_kind: str | None
    ran: bool
    failure: str | None

    def __post_init__(self) -> None:
        _require_optional_str(self.accepted_node_id, "accepted_node_id")
        _require_optional_str(self.execution_kind, "execution_kind")
        _require_bool(self.ran, "ran")
        _require_optional_str(self.failure, "failure")


@dataclass(frozen=True)
class WorkerSupplyTraceSummary:
    decision: str | None
    reason: str | None
    selected_node_id: str | None
    has_envelope: bool

    def __post_init__(self) -> None:
        _require_optional_str(self.decision, "decision")
        _require_optional_str(self.reason, "reason")
        _require_optional_str(self.selected_node_id, "selected_node_id")
        _require_bool(self.has_envelope, "has_envelope")


@dataclass(frozen=True)
class WorkerHistorySummary:
    current_step_count: int
    supply_count: int
    last_accepted_node_id: str | None
    last_execution_kind: str | None
    last_stop_reason: str | None
    recent_steps: tuple[WorkerStepTraceSummary, ...]
    recent_supplies: tuple[WorkerSupplyTraceSummary, ...]

    def __post_init__(self) -> None:
        _require_non_negative_int(self.current_step_count, "current_step_count")
        _require_non_negative_int(self.supply_count, "supply_count")
        _require_optional_str(self.last_accepted_node_id, "last_accepted_node_id")
        _require_optional_str(self.last_execution_kind, "last_execution_kind")
        _require_optional_str(self.last_stop_reason, "last_stop_reason")
        object.__setattr__(
            self,
            "recent_steps",
            _freeze_instance_tuple(
                self.recent_steps,
                WorkerStepTraceSummary,
                "recent_steps",
            ),
        )
        object.__setattr__(
            self,
            "recent_supplies",
            _freeze_instance_tuple(
                self.recent_supplies,
                WorkerSupplyTraceSummary,
                "recent_supplies",
            ),
        )


@dataclass(frozen=True)
class WorkerKnowledgePacket:
    packet_id: str
    kind: str
    title: str | None
    content: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.packet_id, "packet_id")
        _require_non_empty_str(self.kind, "kind")
        _require_optional_str(self.title, "title")
        object.__setattr__(
            self,
            "content",
            _freeze_json_mapping(self.content, "content"),
        )


@dataclass(frozen=True)
class WorkerAllowedAction:
    action_id: str
    kind: str
    description: str
    input_schema: Mapping[str, Any]

    def __post_init__(self) -> None:
        _require_non_empty_str(self.action_id, "action_id")
        _require_non_empty_str(self.kind, "kind")
        _require_non_empty_str(self.description, "description")
        object.__setattr__(
            self,
            "input_schema",
            _freeze_json_mapping(self.input_schema, "input_schema"),
        )


@dataclass(frozen=True)
class LocalWorkerTurnContext:
    workflow: WorkerWorkflowSummary
    current_graph: WorkerGraphSummary
    current_node: WorkerNodeSummary | None
    history: WorkerHistorySummary
    knowledge: tuple[WorkerKnowledgePacket, ...]
    allowed_actions: tuple[WorkerAllowedAction, ...]

    def __post_init__(self) -> None:
        _require_instance(self.workflow, WorkerWorkflowSummary, "workflow")
        _require_instance(self.current_graph, WorkerGraphSummary, "current_graph")
        if self.current_node is not None:
            _require_instance(self.current_node, WorkerNodeSummary, "current_node")
        _require_instance(self.history, WorkerHistorySummary, "history")
        object.__setattr__(
            self,
            "knowledge",
            _freeze_instance_tuple(
                self.knowledge,
                WorkerKnowledgePacket,
                "knowledge",
            ),
        )
        object.__setattr__(
            self,
            "allowed_actions",
            _freeze_instance_tuple(
                self.allowed_actions,
                WorkerAllowedAction,
                "allowed_actions",
            ),
        )


def build_local_worker_turn_context(
    scaffold: CompiledWorkflowScaffold,
    graph: PlanGraph,
    records: tuple[CurrentStepRecord, ...] | list[CurrentStepRecord],
    supply_records: tuple[EnvelopeSupplyRecord, ...] | list[EnvelopeSupplyRecord],
    *,
    current_node_id: str | None,
    knowledge: tuple[WorkerKnowledgePacket, ...] | list[WorkerKnowledgePacket],
    allowed_actions: tuple[WorkerAllowedAction, ...] | list[WorkerAllowedAction],
    history_limit: int = 5,
) -> LocalWorkerTurnContext:
    _require_instance(scaffold, CompiledWorkflowScaffold, "scaffold")
    _require_instance(graph, PlanGraph, "graph")
    records_tuple = _freeze_instance_tuple(records, CurrentStepRecord, "records")
    supply_records_tuple = _freeze_instance_tuple(
        supply_records,
        EnvelopeSupplyRecord,
        "supply_records",
    )
    knowledge_tuple = _freeze_instance_tuple(
        knowledge,
        WorkerKnowledgePacket,
        "knowledge",
    )
    allowed_actions_tuple = _freeze_instance_tuple(
        allowed_actions,
        WorkerAllowedAction,
        "allowed_actions",
    )
    _require_unique_ids(
        (packet.packet_id for packet in knowledge_tuple),
        "knowledge packet_id",
    )
    _require_unique_ids(
        (action.action_id for action in allowed_actions_tuple),
        "allowed action_id",
    )
    _require_positive_int(history_limit, "history_limit")
    _validate_scaffold_identity(scaffold)

    if current_node_id is not None and not isinstance(current_node_id, str):
        raise TypeError("current_node_id must be str or None")
    if current_node_id == "":
        raise ValueError("current_node_id must not be empty")
    if current_node_id is not None and current_node_id not in graph.nodes:
        raise ValueError(f"current_node_id not found in graph: {current_node_id!r}")

    return LocalWorkerTurnContext(
        workflow=_summarize_workflow(scaffold),
        current_graph=_summarize_graph(graph),
        current_node=(
            None
            if current_node_id is None
            else _summarize_node(graph, current_node_id)
        ),
        history=_summarize_history(
            records_tuple,
            supply_records_tuple,
            history_limit=history_limit,
        ),
        knowledge=knowledge_tuple,
        allowed_actions=allowed_actions_tuple,
    )


def _validate_scaffold_identity(scaffold: CompiledWorkflowScaffold) -> None:
    if scaffold.compile_record.workflow_id != scaffold.workflow_id:
        raise ValueError("scaffold workflow_id does not match compile record")
    if (
        scaffold.compile_record.contract_fingerprint
        != scaffold.contract_snapshot.contract_fingerprint
    ):
        raise ValueError(
            "scaffold contract fingerprint does not match contract snapshot"
        )
    snapshot_schema = scaffold.contract_snapshot.normalized_contract["schema"]
    if scaffold.compile_record.contract_schema != snapshot_schema:
        raise ValueError("scaffold contract schema does not match contract snapshot")


def _summarize_workflow(
    scaffold: CompiledWorkflowScaffold,
) -> WorkerWorkflowSummary:
    record = scaffold.compile_record
    return WorkerWorkflowSummary(
        workflow_id=record.workflow_id,
        contract_schema=record.contract_schema,
        contract_fingerprint=record.contract_fingerprint,
        compiler_id=record.compiler_id,
        provider_id=record.provider_id,
        selected_template_id=record.selected_template_id,
        max_steps=scaffold.max_steps,
    )


def _summarize_graph(graph: PlanGraph) -> WorkerGraphSummary:
    node_ids = tuple(sorted(_require_str(node_id, "graph node id") for node_id in graph.nodes))
    ready_node_ids = tuple(
        sorted(
            node_id
            for node_id, node in graph.nodes.items()
            if _node_status(node) == "ready"
        )
    )
    terminal_node_ids = tuple(
        sorted(
            node_id
            for node_id, node in graph.nodes.items()
            if _node_terminal(node)
        )
    )

    status_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        status = _node_status(node)
        status_counts[status] = status_counts.get(status, 0) + 1

    return WorkerGraphSummary(
        node_count=len(graph.nodes),
        node_ids=node_ids,
        ready_node_ids=ready_node_ids,
        terminal_node_ids=terminal_node_ids,
        status_counts=status_counts,
    )


def _summarize_node(graph: PlanGraph, node_id: str) -> WorkerNodeSummary:
    node = graph.nodes[node_id]
    role = projection_role_for_node(node)
    if role is not None and not isinstance(role, str):
        role = str(role)

    metadata = node.metadata if isinstance(node.metadata, Mapping) else {}
    execution_params = metadata.get(EXECUTION_PARAMS_KEY)

    return WorkerNodeSummary(
        node_id=node_id,
        intent=_node_intent(node),
        role=role,
        status=_node_status(node),
        execution_ref=_node_execution_ref(node),
        is_terminal=_node_terminal(node),
        has_execution_params=(
            isinstance(execution_params, Mapping) and bool(execution_params)
        ),
        memory_keys=_graph_memory_keys(graph),
    )


def _summarize_history(
    records: tuple[CurrentStepRecord, ...],
    supply_records: tuple[EnvelopeSupplyRecord, ...],
    *,
    history_limit: int,
) -> WorkerHistorySummary:
    recent_records = records[-history_limit:]
    recent_supply_records = supply_records[-history_limit:]
    last_record = records[-1] if records else None
    last_supply = supply_records[-1] if supply_records else None

    return WorkerHistorySummary(
        current_step_count=len(records),
        supply_count=len(supply_records),
        last_accepted_node_id=(
            None if last_record is None else last_record.accepted_node_id
        ),
        last_execution_kind=(
            None if last_record is None else last_record.execution_kind
        ),
        last_stop_reason=(
            None if last_supply is None else _supply_reason(last_supply)
        ),
        recent_steps=tuple(_summarize_step(record) for record in recent_records),
        recent_supplies=tuple(
            _summarize_supply(record) for record in recent_supply_records
        ),
    )


def _summarize_step(record: CurrentStepRecord) -> WorkerStepTraceSummary:
    return WorkerStepTraceSummary(
        accepted_node_id=record.accepted_node_id,
        execution_kind=record.execution_kind,
        ran=record.ran,
        failure=record.execution_failure or record.mapping_failure,
    )


def _summarize_supply(record: EnvelopeSupplyRecord) -> WorkerSupplyTraceSummary:
    return WorkerSupplyTraceSummary(
        decision=record.decision,
        reason=_supply_reason(record),
        selected_node_id=_supply_selected_node_id(record),
        has_envelope=record.envelope is not None,
    )


def _supply_reason(record: EnvelopeSupplyRecord) -> str | None:
    return record.invalid_reason or record.reason or record.error_class


def _supply_selected_node_id(record: EnvelopeSupplyRecord) -> str | None:
    if not isinstance(record.metadata, Mapping):
        return None
    selected_node_id = record.metadata.get("selected_node_id")
    return selected_node_id if isinstance(selected_node_id, str) else None


def _graph_memory_keys(graph: PlanGraph) -> tuple[str, ...]:
    facts = graph.memory.facts
    if not isinstance(facts, Mapping):
        raise TypeError("graph.memory.facts must be a mapping")
    keys: list[str] = []
    for key in facts:
        if not isinstance(key, str):
            raise TypeError("graph.memory.facts keys must be strings")
        keys.append(key)
    return tuple(sorted(keys))


def _node_intent(node: Any) -> str:
    return _require_str(node.intent, "node.intent")


def _node_status(node: Any) -> str:
    return _require_str(node.status, "node.status")


def _node_execution_ref(node: Any) -> str | None:
    return _require_optional_str(node.execution_ref, "node.execution_ref")


def _node_terminal(node: Any) -> bool:
    return _require_bool(node.is_terminal, "node.is_terminal")


def _freeze_json_mapping(value: object, field_name: str) -> Mapping[str, Any]:
    frozen = _freeze_json_value(value, field_name)
    if not isinstance(frozen, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return frozen


def _freeze_json_value(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        copied: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{field_name} mapping keys must be strings")
            copied[key] = _freeze_json_value(item, f"{field_name}.{key}")
        return MappingProxyType(copied)
    if isinstance(value, (list, tuple)):
        return tuple(
            _freeze_json_value(item, f"{field_name}[]")
            for item in value
        )
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{field_name} float values must be finite")
        return value
    raise TypeError(f"{field_name} contains unsupported JSON value")


def _freeze_count_mapping(
    value: Mapping[str, int],
    field_name: str,
) -> Mapping[str, int]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    copied: dict[str, int] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError(f"{field_name} keys must be strings")
        copied[key] = _require_non_negative_int(item, f"{field_name}.{key}")
    return MappingProxyType(copied)


def _freeze_instance_tuple(
    value: tuple[object, ...] | list[object],
    expected_type: type,
    field_name: str,
) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    for item in value:
        _require_instance(item, expected_type, f"{field_name} item")
    return tuple(value)


def _freeze_str_tuple(
    value: tuple[str, ...] | list[str],
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"{field_name} must be a list or tuple")
    return tuple(_require_str(item, f"{field_name} item") for item in value)


def _require_unique_ids(values: object, field_name: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"duplicate {field_name}: {value!r}")
        seen.add(value)


def _require_instance(value: object, expected_type: type, field_name: str) -> object:
    if not isinstance(value, expected_type):
        raise TypeError(f"{field_name} must be {expected_type.__name__}")
    return value


def _require_non_empty_str(value: object, field_name: str) -> str:
    result = _require_str(value, field_name)
    if result == "":
        raise ValueError(f"{field_name} must not be empty")
    return result


def _require_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _require_optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_str(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
    return value


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")
    return value
```

**Run:**

```powershell
python -m pytest mcp_server/tests/test_local_worker_turn_context.py -q
```

**Expected output:**

```text
49 passed
```

**Commit:**

```powershell
git add mcp_server/src/rook/agent/local_worker_turn_context.py
git commit -m "feat(lm5a): add local worker turn context"
```

---

## Task 3: Run Targeted and Nearby Regression Gates

**Purpose:** Verify LM5A in isolation and against the LM4 artifact/provenance stack it consumes.

**Run targeted tests:**

```powershell
python -m pytest mcp_server/tests/test_local_worker_turn_context.py -q
```

**Expected output:**

```text
49 passed
```

**Run nearby regression tests:**

```powershell
python -m pytest `
  mcp_server/tests/test_local_worker_turn_context.py `
  mcp_server/tests/test_plan_graph_workflow_contract.py `
  mcp_server/tests/test_plan_graph_workflow_contract_chain.py `
  mcp_server/tests/test_plan_graph_workflow_contract_fingerprint.py `
  mcp_server/tests/test_plan_graph_workflow_contract_loader.py `
  mcp_server/tests/test_plan_graph_workflow_provenance.py `
  -q
```

**Expected output:**

```text
201 passed
```

**Run focused PlanGraph/local-worker gate:**

```powershell
python -m pytest `
  mcp_server/tests/test_plan_graph*.py `
  mcp_server/tests/test_local_worker_turn_context.py `
  -q
```

**Expected output:**

```text
605 passed
```

If the glob expands differently in PowerShell or pytest collects an unintended set, use an explicit file list matching the PlanGraph-focused pattern already used in recent LM4 reviews, plus `test_local_worker_turn_context.py`.

---

## Task 4: Final Boundary and Scope Review

**Purpose:** Prove the slice stayed inside the deterministic worker-context boundary.

**Diff check:**

```powershell
git diff --check main..HEAD
```

**Expected output:** no output.

**Production scope check:**

```powershell
git diff --name-only main..HEAD -- mcp_server/src
```

**Expected output:**

```text
mcp_server/src/rook/agent/local_worker_turn_context.py
```

**No drift check:**

```powershell
git diff --name-only main..HEAD -- src/Rook/base_agent.py knowledge/gh/operations_knowledge.json src/Rook src/RookNative
```

**Expected output:** no output.

**Boundary scan:**

```powershell
rg -n "propose_next_node|map_accepted_proposal_to_step|revalidate_proposal|execute_mapped_step|run_current_mapped_step|run_current_step_stream|EnvelopeSupplyResult|CatalogCurrentStepProvider|WorkflowProvenanceEnvelopeSource|compile_workflow_contract|load_workflow_contract_payload|snapshot_workflow_contract|RookAgent|base_agent|dispatcher|server|litellm|OpenAI|Path|open\(|import json|json\.loads|json\.dumps|yaml" mcp_server/src/rook/agent/local_worker_turn_context.py
```

**Expected output:** no output.

Note: the AST guard in `test_local_worker_turn_context.py` is the primary boundary check. This `rg` scan is a final quick human-readable guard.

**Final status check:**

```powershell
git status --short
```

**Expected output:** clean after committing implementation files, or only intentional uncommitted review edits before final commit.

---

## Self-Review Checklist

- [ ] `LocalWorkerTurnContext` contains only worker-facing summaries, no raw LM4 objects.
- [ ] Builder requires explicit `current_node_id` and never calls current-node selector logic.
- [ ] Non-`str | None` `current_node_id` raises `TypeError`.
- [ ] Packet/action dataclasses freeze payloads in `__post_init__`, independent of the builder.
- [ ] `role` uses only `projection_role_for_node(node)`.
- [ ] `has_execution_params` uses `EXECUTION_PARAMS_KEY` from `plan_graph_live`.
- [ ] `memory_keys` comes from sorted `graph.memory.facts` keys and raises on malformed keys.
- [ ] History summaries use flattened LM4 record fields only.
- [ ] No serialization, prompt formatting, model, RookChat, stream, compile, selector, mapper, execution, file, JSON, or YAML surface was introduced.
- [ ] Production diff is exactly one new module.
- [ ] Tests cover direct packet/action immutability before the context builder sees those objects.

---

## Execution Recommendation

Use **Subagent-Driven** execution for this slice if possible. LM5A is deterministic and small, but it establishes the first LM5 worker-facing contract and is worth one fresh review loop for accidental authority or raw-object leakage.

Inline execution is acceptable after plan approval if we keep the review checkpoint before PR.
