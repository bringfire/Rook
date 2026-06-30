from __future__ import annotations

import ast
import copy
import inspect
import sys
from collections.abc import Callable, Mapping

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


def _loaded_name_references(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            names.add(node.id)
    return names


def test_scenario_test_module_boundary_has_no_runtime_or_file_creep() -> None:
    source = inspect.getsource(sys.modules[__name__])
    tree = ast.parse(source)

    imported_modules: set[str] = set()
    imported_names: set[str] = set()
    called_names: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.add(alias.name)
                imported_names.add(alias.asname or alias.name.split(".", maxsplit=1)[0])
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            for alias in node.names:
                imported_names.add(alias.asname or alias.name)
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
    referenced_names = _loaded_name_references(tree) - {"banned_names"}
    assert not (banned_names & imported_names)
    assert not (banned_names & referenced_names)
    assert not (banned_names & called_names)


def test_repair_node_requests_allowed_repair_action() -> None:
    context = _context(current_node_id="repair_same_component")

    record = run_local_worker_turn(context, _request_allowed_action_worker)

    payload = _assert_completed_action(record, context, "draft_repair_params")
    assert payload.input["mode"] == "body"
    assert payload.input["language"] == "csharp"


def test_terminal_done_node_observes_completion_even_with_allowed_action() -> None:
    context = _context(current_node_id="done")

    assert context.current_node is not None
    assert context.current_node.node_id == "done"
    assert context.current_node.is_terminal is True

    record = run_local_worker_turn(context, _observe_terminal_worker)

    payload = _assert_completed_observation(record, context)
    assert "Terminal node" in payload.message


def test_execution_ref_used_as_action_id_is_blocked() -> None:
    context = _context(current_node_id="repair_same_component")

    assert context.current_node is not None
    assert context.current_node.execution_ref == "gh_update_script:v1"

    record = run_local_worker_turn(
        context,
        _request_action_id_worker("gh_update_script:v1"),
    )

    _assert_blocked_unknown_action(record, context, "gh_update_script:v1")


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
