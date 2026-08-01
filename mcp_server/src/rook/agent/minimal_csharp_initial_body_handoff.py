"""One-turn Worker-authored initial C# body handoff."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from rook.agent.local_worker_adapter import (
    LocalWorkerAdapterRecord, LocalWorkerTransport, run_local_worker_adapter,
)
from rook.agent.local_worker_turn_context import (
    LocalWorkerTurnContext, WorkerAllowedAction, WorkerKnowledgePacket,
    build_local_worker_turn_context,
)
from rook.agent.local_worker_turn_harness import LocalWorkerTurnHarnessRecord, run_local_worker_turn
from rook.agent.local_worker_turn_request import render_local_worker_turn_request_payload
from rook.agent.local_worker_turn_response import WorkerActionRequest
from rook.agent.minimal_csharp_repair_handoff import (
    ValidatedPlannerDraft,
    _require_validated_draft,
)
from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import (
    CurrentStepStreamResult, EnvelopeSupplyRecord, run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_dispatch import run_live_producer_node_with_executor
from rook.agent.plan_graph_worker_create_body_apply import (
    WorkerCreateBodyApplyResult, apply_worker_create_body_to_scaffold,
)
from rook.agent.plan_graph_workflow_contract import (
    CompiledWorkflowScaffold,
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


_WORKFLOW_ID = "minimal_csharp_initial_body_handoff"
_TEMPLATE_ID = "gh_csharp_create_verify"
_CREATE_NODE_ID = "create_script"
_VERIFY_NODE_ID = "verify_create"
_TERMINAL_NODE_ID = "done"
_ACTION_ID = "draft_create_body"

@dataclass(frozen=True)
class MinimalCSharpInitialBodyHandoffResult:
    draft: ValidatedPlannerDraft
    scaffold: CompiledWorkflowScaffold
    final_graph: PlanGraph
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    step_records: tuple[CurrentStepRecord, ...]
    worker_request: Mapping[str, Any]
    worker_context: LocalWorkerTurnContext
    adapter_record: LocalWorkerAdapterRecord
    worker_record: LocalWorkerTurnHarnessRecord | None
    action_apply_result: WorkerCreateBodyApplyResult | None
    terminal_stage: str
    terminal_reason: str

    def __post_init__(self) -> None:
        _validate_result_shape(self)


def _build_initial_body_contract(
    draft: ValidatedPlannerDraft,
) -> RookWorkflowContract:
    _require_validated_draft(draft)
    return RookWorkflowContract(
        workflow_id=_WORKFLOW_ID,
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify",
                "language": "csharp",
            },
            expected_template_id=_TEMPLATE_ID,
        ),
        initial_params=(
            InitialNodeParams(
                node_id=_CREATE_NODE_ID,
                execution_params={
                    "pins_in": list(draft.interface.inputs),
                    "pins_out": [
                        f"{output.name}:{output.type}"
                        for output in draft.interface.outputs
                    ],
                    "name": "RookMinimalInitialBodyHandoff",
                    "x": 375,
                    "y": 1080,
                },
            ),
        ),
        rules=(
            WorkflowNodeRule(
                node_id=_CREATE_NODE_ID,
                steps_by_seen_count=(ProducerStepSpec(_CREATE_NODE_ID),),
            ),
            WorkflowNodeRule(
                node_id=_VERIFY_NODE_ID,
                steps_by_seen_count=(
                    VerifierStepSpec(
                        verifier_node_id=_VERIFY_NODE_ID,
                        source_node_id=_CREATE_NODE_ID,
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=(_TERMINAL_NODE_ID,),
        expected_refs=(
            ExpectedNodeRef(_CREATE_NODE_ID, "gh_create_csharp_script:v1"),
        ),
        max_steps=4,
        metadata={
            "capability": "grasshopper_csharp_component",
            "acceptance": "clean_compile_receipt",
        },
    )


async def run_minimal_csharp_initial_body_handoff(
    draft: ValidatedPlannerDraft,
    *,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalCSharpInitialBodyHandoffResult:
    _require_validated_draft(draft)
    if not callable(tool_executor): raise TypeError("tool_executor must be callable")

    contract = _build_initial_body_contract(draft)
    scaffold = compile_workflow_contract(contract)
    context = _build_worker_context(draft, contract, scaffold)
    request = render_local_worker_turn_request_payload(context)
    adapter = run_local_worker_adapter(request, worker_transport)
    if adapter.status != "response_loaded":
        return _result(
            draft,
            scaffold,
            request,
            context,
            adapter,
            "worker_adapter",
            _reason(adapter.failure_reason),
        )
    if adapter.response is None: raise RuntimeError("loaded Worker response is absent")
    response = adapter.response

    def one_shot(supplied: LocalWorkerTurnContext):
        if supplied is not context:
            raise RuntimeError("Worker harness supplied a different context")
        return response

    worker_record = run_local_worker_turn(context, one_shot)
    disposition = worker_record.disposition
    if worker_record.status != "completed" or disposition is None:
        raise RuntimeError("one-shot Worker harness did not complete")
    if disposition.disposition != "candidate_action_request":
        return _result(
            draft,
            scaffold,
            request,
            context,
            adapter,
            "worker_disposition",
            disposition.reason,
            worker_record=worker_record,
        )
    if type(response.payload) is not WorkerActionRequest:
        raise RuntimeError("candidate disposition lacks an action request")
    action = apply_worker_create_body_to_scaffold(
        scaffold,
        _CREATE_NODE_ID,
        action_id=response.payload.action_id,
        action_input=response.payload.input,
    )
    if not action.applied:
        return _result(
            draft,
            scaffold,
            request,
            context,
            adapter,
            "action_apply",
            _reason(action.reason),
            worker_record=worker_record,
            action=action,
        )
    stream = await run_current_step_stream(
        action.graph,
        scaffold.provider,
        max_steps=scaffold.max_steps,
        runner=_ToolExecutorRunner(tool_executor),
    )
    return _result(
        draft,
        scaffold,
        request,
        context,
        adapter,
        _stage(stream),
        _stream_reason(stream),
        worker_record=worker_record,
        action=action,
        stream=stream,
    )


@dataclass(frozen=True)
class _ToolExecutorRunner:
    tool_executor: Callable[[str, dict[str, Any]], Any]

    async def run_live_producer_node(
        self, graph: PlanGraph, node_id: str,
    ) -> LiveProducerResult:
        return await run_live_producer_node_with_executor(
            graph, node_id, self.tool_executor,
        )


def _build_worker_context(
    draft: ValidatedPlannerDraft,
    contract: RookWorkflowContract,
    scaffold: CompiledWorkflowScaffold,
) -> LocalWorkerTurnContext:
    params = scaffold.graph.nodes[_CREATE_NODE_ID].metadata[EXECUTION_PARAMS_KEY]
    interface = {
        "inputs": [_pin(token) for token in params["pins_in"]],
        "outputs": [_pin(token) for token in params["pins_out"]],
    }
    expected_interface = {
        "inputs": [],
        "outputs": [
            {"name": output.name, "type": output.type}
            for output in draft.interface.outputs
        ],
    }
    if interface != expected_interface:
        raise RuntimeError("compiled interface differs from the admitted draft")
    verifier = contract.rules[1].steps_by_seen_count[0]
    if type(verifier) is not VerifierStepSpec:
        raise RuntimeError("initial-body verifier rule is absent")
    return build_local_worker_turn_context(
        scaffold,
        scaffold.graph,
        (),
        (),
        current_node_id=_CREATE_NODE_ID,
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="planner_goal_and_interface",
                kind="requirement",
                title="Planner goal and fixed component interface",
                content={"goal": draft.goal, "interface": interface},
            ),
            WorkerKnowledgePacket(
                packet_id="script_body_gotcha",
                kind="gotcha",
                title="C# script components use body-style code",
                content={"body_mode": "body"},
            ),
            WorkerKnowledgePacket(
                packet_id="clean_compile_acceptance",
                kind="acceptance_criteria",
                title="Clean initial compile receipt acceptance",
                content={
                    "verifier_node_id": verifier.verifier_node_id,
                    "source_node_id": verifier.source_node_id,
                    "expected_outcome": verifier.expected_outcome,
                    "criterion": (
                        "The initial C# body must compile cleanly for the "
                        "declared interface."
                    ),
                },
            ),
        ),
        allowed_actions=(
            WorkerAllowedAction(
                action_id=_ACTION_ID,
                kind=_ACTION_ID,
                description="Draft the complete initial C# body.",
                input_schema={
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {"code": {"type": "string"}},
                    "required": ["code"],
                },
            ),
        ),
    )


def _pin(token: object) -> dict[str, str]:
    if type(token) is not str or token.count(":") != 1:
        raise RuntimeError("compiled pin token is malformed")
    name, pin_type = token.split(":", 1)
    return {"name": name, "type": pin_type}


def _result(
    draft: ValidatedPlannerDraft,
    scaffold: CompiledWorkflowScaffold,
    request: Mapping[str, Any],
    context: LocalWorkerTurnContext,
    adapter: LocalWorkerAdapterRecord,
    stage: str,
    reason: str,
    *,
    worker_record: LocalWorkerTurnHarnessRecord | None = None,
    action: WorkerCreateBodyApplyResult | None = None,
    stream: CurrentStepStreamResult | None = None,
) -> MinimalCSharpInitialBodyHandoffResult:
    return MinimalCSharpInitialBodyHandoffResult(
        draft=draft,
        scaffold=scaffold,
        final_graph=scaffold.graph if stream is None else stream.final_graph,
        supply_records=() if stream is None else stream.supply_records,
        step_records=() if stream is None else stream.records,
        worker_request=request,
        worker_context=context,
        adapter_record=adapter,
        worker_record=worker_record,
        action_apply_result=action,
        terminal_stage=stage,
        terminal_reason=reason,
    )


def _stage(stream: CurrentStepStreamResult) -> str:
    accepted = tuple(record.accepted_node_id for record in stream.records)
    if accepted not in {(), (_CREATE_NODE_ID,), (_CREATE_NODE_ID, _VERIFY_NODE_ID)}:
        raise RuntimeError("create stream returned an unexpected record prefix")
    if (
        stream.stop_reason == "provider_halt"
        and stream.supply_records
        and stream.supply_records[-1].reason == "terminal_node_selected:done"
    ):
        return "terminal"
    return "verify_create" if accepted[-1:] == (_VERIFY_NODE_ID,) else "create"


def _stream_reason(stream: CurrentStepStreamResult) -> str:
    if stream.supply_records:
        supply = stream.supply_records[-1]
        if supply.reason is not None:
            return _reason(supply.reason)
        if supply.invalid_reason is not None:
            return _reason(supply.invalid_reason)
    if stream.records:
        record = stream.records[-1]
        for value in (
            record.producer_reason,
            record.verifier_reason,
            record.execution_failure,
            record.mapping_failure,
            record.execution.reason,
        ):
            if value is not None:
                return _reason(value)
    raise RuntimeError("native stream stop lacks a reason")


def _reason(value: object) -> str:
    if type(value) is not str or not value:
        raise RuntimeError("native stop lacks a reason")
    return value


def _validate_result_shape(result: MinimalCSharpInitialBodyHandoffResult) -> None:
    _require_validated_draft(result.draft)
    immediate_types = ((result.scaffold, CompiledWorkflowScaffold),
                       (result.final_graph, PlanGraph),
                       (result.worker_context, LocalWorkerTurnContext),
                       (result.adapter_record, LocalWorkerAdapterRecord))
    if any(type(value) is not expected for value, expected in immediate_types):
        raise TypeError("result contains an invalid immediate field type")
    optional_types = ((result.worker_record, LocalWorkerTurnHarnessRecord),
                      (result.action_apply_result, WorkerCreateBodyApplyResult))
    if any(value is not None and type(value) is not expected for value, expected in optional_types):
        raise TypeError("result contains an invalid optional field type")
    if type(result.step_records) is not tuple or not all(
        type(record) is CurrentStepRecord for record in result.step_records
    ):
        raise TypeError("step_records must contain exact native records")
    if type(result.supply_records) is not tuple or not all(
        type(record) is EnvelopeSupplyRecord for record in result.supply_records
    ):
        raise TypeError("supply_records must contain exact native records")
    if type(result.terminal_reason) is not str or not result.terminal_reason:
        raise TypeError("terminal_reason must be an exact nonblank string")
    allowed_prefixes = {
        "worker_adapter": {()}, "worker_disposition": {()},
        "action_apply": {()}, "create": {(), (_CREATE_NODE_ID,)},
        "verify_create": {(_CREATE_NODE_ID, _VERIFY_NODE_ID)},
        "terminal": {(_CREATE_NODE_ID, _VERIFY_NODE_ID)},
    }
    if type(result.terminal_stage) is not str:
        raise TypeError("terminal_stage must be an exact string")
    if result.terminal_stage not in allowed_prefixes:
        raise ValueError("terminal_stage is unsupported")
    if (result.worker_record is None) != (result.terminal_stage == "worker_adapter"):
        raise ValueError("worker_record presence differs from terminal stage")
    action_stages = {"action_apply", "create", "verify_create", "terminal"}
    if (result.action_apply_result is None) != (
        result.terminal_stage not in action_stages
    ):
        raise ValueError("action result presence differs from terminal stage")
    action = result.action_apply_result
    if action is not None:
        expected_applied = result.terminal_stage != "action_apply"
        if action.applied is not expected_applied:
            raise ValueError("action state differs from terminal stage")
        if not expected_applied and result.terminal_reason != action.reason:
            raise ValueError("action state reason differs from terminal reason")
    actual_prefix = tuple(record.accepted_node_id for record in result.step_records)
    if actual_prefix not in allowed_prefixes[result.terminal_stage]:
        raise ValueError("native record prefix differs from terminal stage")
    done_ready = result.final_graph.nodes[_TERMINAL_NODE_ID].status == "ready"
    if (result.terminal_stage == "terminal") != done_ready:
        raise ValueError("done readiness differs from terminal stage")
    if result.terminal_stage == "terminal" and (
        result.terminal_reason != "terminal_node_selected:done"
    ):
        raise ValueError("terminal reason differs")
