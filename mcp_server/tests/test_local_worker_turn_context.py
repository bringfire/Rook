from __future__ import annotations

import ast
import copy
import math
from collections.abc import Mapping
from dataclasses import replace
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

    bad_workflow = replace(
        scaffold,
        compile_record=replace(scaffold.compile_record, workflow_id="other"),
    )
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

    bad_fingerprint = replace(
        scaffold,
        compile_record=replace(
            scaffold.compile_record,
            contract_fingerprint="0" * 64,
        ),
    )
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

    bad_schema = replace(
        scaffold,
        compile_record=replace(scaffold.compile_record, contract_schema="other"),
    )
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
