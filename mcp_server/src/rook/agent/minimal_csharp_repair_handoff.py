"""One internal C# repair-capability Planner/worker handoff.

This module composes existing workflow, worker, action, and receipt seams for
one fixed repair specimen. It does not invoke a Planner, construct a provider,
or expose Chat, MCP, CLI, or live-runtime entry points.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json
from typing import Any, Literal

from rook.agent.local_worker_acceptance_criteria import (
    AcceptanceCriteriaSource,
    assemble_acceptance_criteria_packet,
)
from rook.agent.local_worker_acceptance_criteria_sources import (
    extract_acceptance_criteria_sources,
)
from rook.agent.local_worker_adapter import (
    LocalWorkerAdapterRecord,
    LocalWorkerTransport,
    run_local_worker_adapter,
)
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
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import WorkerActionRequest
from rook.agent.plan_graph_current_step_runner import CurrentStepRecord
from rook.agent.plan_graph_current_step_stream import (
    CurrentStepStreamResult,
    EnvelopeSupplyRecord,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_dispatch import (
    run_live_producer_node_with_executor,
)
from rook.agent.plan_graph_worker_action_apply import (
    WorkerActionApplyResult,
    apply_worker_action_to_node,
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


__all__ = (
    "PlannerDraftOutput",
    "PlannerDraftInterface",
    "ValidatedPlannerDraft",
    "MinimalCSharpRepairHandoffResult",
    "load_minimal_csharp_repair_draft",
    "run_minimal_csharp_repair_handoff",
)


_CAPABILITY = "grasshopper_csharp_component"
_ACCEPTANCE = "clean_compile_receipt"
_SPECIMEN_INITIAL_BODY = "A = DefinitelyMissingSymbol;"
_WORKFLOW_ID = "minimal_csharp_repair_handoff"
_TEMPLATE_ID = "gh_csharp_create_verify_repair_verify"
_ACTION_ID = "draft_repair_params"
_CREATE_NODE_ID = "create_script"
_VERIFY_CREATE_NODE_ID = "verify_create"
_REPAIR_NODE_ID = "repair_same_component"
_VERIFY_REPAIR_NODE_ID = "verify_repair"
_TERMINAL_NODE_ID = "done"


@dataclass(frozen=True)
class PlannerDraftOutput:
    name: Literal["A"]
    type: Literal["double"]

    def __post_init__(self) -> None:
        _require_planner_output(self)


@dataclass(frozen=True)
class PlannerDraftInterface:
    inputs: tuple[Any, ...]
    outputs: tuple[PlannerDraftOutput, ...]

    def __post_init__(self) -> None:
        inputs = tuple(self.inputs)
        outputs = tuple(self.outputs)
        if inputs:
            raise ValueError("Planner draft interface inputs must be empty")
        if len(outputs) != 1 or type(outputs[0]) is not PlannerDraftOutput:
            raise ValueError("Planner draft interface requires exact A:double output")
        object.__setattr__(self, "inputs", inputs)
        object.__setattr__(self, "outputs", outputs)
        _require_planner_interface(self)


@dataclass(frozen=True)
class ValidatedPlannerDraft:
    goal: str
    capability: Literal["grasshopper_csharp_component"]
    interface: PlannerDraftInterface
    acceptance: Literal["clean_compile_receipt"]

    def __post_init__(self) -> None:
        _require_validated_draft(self)


TerminalStage = Literal[
    "create",
    "verify_create",
    "worker_adapter",
    "worker_disposition",
    "action_apply",
    "repair",
    "verify_repair",
    "terminal",
]


@dataclass(frozen=True)
class MinimalCSharpRepairHandoffResult:
    draft: ValidatedPlannerDraft
    scaffold: CompiledWorkflowScaffold
    final_graph: PlanGraph
    supply_records: tuple[EnvelopeSupplyRecord, ...]
    step_records: tuple[CurrentStepRecord, ...]
    worker_request: Mapping[str, Any] | None
    worker_context: LocalWorkerTurnContext | None
    adapter_record: LocalWorkerAdapterRecord | None
    worker_record: LocalWorkerTurnHarnessRecord | None
    action_apply_result: WorkerActionApplyResult | None
    terminal_stage: TerminalStage
    terminal_reason: str

    def __post_init__(self) -> None:
        _validate_handoff_result(self)


def load_minimal_csharp_repair_draft(
    payload: Mapping[str, Any],
) -> ValidatedPlannerDraft:
    payload = _require_mapping(payload, "Planner draft")
    _require_exact_fields(
        payload,
        frozenset({"goal", "capability", "interface", "acceptance"}),
        "Planner draft",
    )
    goal = _require_exact_string(payload["goal"], "Planner draft goal")
    if not goal.strip():
        raise ValueError("Planner draft goal must be a non-empty string")
    capability = _require_exact_string(
        payload["capability"],
        "Planner draft capability",
    )
    if capability != _CAPABILITY:
        raise ValueError(f"Planner draft capability must be {_CAPABILITY!r}")
    interface_payload = _require_mapping(payload["interface"], "interface")
    _require_exact_fields(
        interface_payload,
        frozenset({"inputs", "outputs"}),
        "interface",
    )
    inputs = interface_payload["inputs"]
    if not isinstance(inputs, list) or inputs:
        raise ValueError("Planner draft interface inputs must be []")
    outputs = interface_payload["outputs"]
    if not isinstance(outputs, list) or len(outputs) != 1:
        raise ValueError("Planner draft interface requires one output")
    output_payload = _require_mapping(outputs[0], "interface output")
    _require_exact_fields(
        output_payload,
        frozenset({"name", "type"}),
        "interface output",
    )
    output = PlannerDraftOutput(
        name=output_payload["name"],
        type=output_payload["type"],
    )
    acceptance = _require_exact_string(
        payload["acceptance"],
        "Planner draft acceptance",
    )
    if acceptance != _ACCEPTANCE:
        raise ValueError(f"Planner draft acceptance must be {_ACCEPTANCE!r}")
    return ValidatedPlannerDraft(
        goal=goal,
        capability=capability,
        interface=PlannerDraftInterface(inputs=(), outputs=(output,)),
        acceptance=acceptance,
    )


async def run_minimal_csharp_repair_handoff(
    draft: ValidatedPlannerDraft,
    *,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, Any]], Any],
) -> MinimalCSharpRepairHandoffResult:
    _require_validated_draft(draft)
    if not callable(tool_executor):
        raise TypeError("tool_executor must be callable")

    contract = _build_repair_specimen_contract(draft)
    scaffold = compile_workflow_contract(contract)
    runner = _ToolExecutorRunner(tool_executor)
    phase_one = await run_current_step_stream(
        scaffold.graph,
        scaffold.provider,
        max_steps=2,
        runner=runner,
    )
    if not _phase_one_reached_frontier(phase_one):
        stage: TerminalStage = (
            "verify_create"
            if _last_accepted_node_id(phase_one.records) == _VERIFY_CREATE_NODE_ID
            else "create"
        )
        return _handoff_result(
            draft=draft,
            scaffold=scaffold,
            phase_one=phase_one,
            terminal_stage=stage,
            terminal_reason=_stream_terminal_reason(phase_one),
        )

    context = _build_worker_context(
        draft=draft,
        contract=contract,
        scaffold=scaffold,
        graph=phase_one.final_graph,
        step_records=phase_one.records,
        supply_records=phase_one.supply_records,
    )
    request = render_local_worker_turn_request_payload(context)
    adapter_record = run_local_worker_adapter(request, worker_transport)
    if adapter_record.status != "response_loaded":
        return _handoff_result(
            draft=draft,
            scaffold=scaffold,
            phase_one=phase_one,
            terminal_stage="worker_adapter",
            terminal_reason=_required_reason(
                adapter_record.failure_reason,
                "adapter failure",
            ),
            worker_request=request,
            worker_context=context,
            adapter_record=adapter_record,
        )
    if adapter_record.response is None:
        raise RuntimeError("loaded adapter record lacks a response")

    loaded_response = adapter_record.response

    def one_shot_worker(supplied_context: LocalWorkerTurnContext):
        if supplied_context is not context:
            raise RuntimeError("worker harness supplied a different context")
        return loaded_response

    worker_record = run_local_worker_turn(context, one_shot_worker)
    disposition = worker_record.disposition
    if worker_record.status != "completed" or disposition is None:
        raise RuntimeError("one-shot worker harness did not complete")
    if disposition.disposition != "candidate_action_request":
        return _handoff_result(
            draft=draft,
            scaffold=scaffold,
            phase_one=phase_one,
            terminal_stage="worker_disposition",
            terminal_reason=disposition.reason,
            worker_request=request,
            worker_context=context,
            adapter_record=adapter_record,
            worker_record=worker_record,
        )
    payload = loaded_response.payload
    if type(payload) is not WorkerActionRequest:
        raise RuntimeError("candidate disposition lacks exact action payload")

    anchor_binding = _project_anchor_binding(phase_one.final_graph)
    action_apply_result = apply_worker_action_to_node(
        phase_one.final_graph,
        _REPAIR_NODE_ID,
        action_id=payload.action_id,
        action_input=payload.input,
        anchor_binding=anchor_binding,
    )
    if not action_apply_result.applied:
        return _handoff_result(
            draft=draft,
            scaffold=scaffold,
            phase_one=phase_one,
            terminal_stage="action_apply",
            terminal_reason=_required_reason(
                action_apply_result.reason,
                "rejected action application",
            ),
            worker_request=request,
            worker_context=context,
            adapter_record=adapter_record,
            worker_record=worker_record,
            action_apply_result=action_apply_result,
        )

    phase_two = await run_current_step_stream(
        action_apply_result.graph,
        scaffold.provider,
        max_steps=scaffold.max_steps,
        runner=runner,
    )
    terminal = _phase_two_reached_terminal(phase_two)
    stage = (
        "terminal"
        if terminal
        else (
            "verify_repair"
            if _last_accepted_node_id(phase_two.records) == _VERIFY_REPAIR_NODE_ID
            else "repair"
        )
    )
    return _handoff_result(
        draft=draft,
        scaffold=scaffold,
        phase_one=phase_one,
        phase_two=phase_two,
        worker_request=request,
        worker_context=context,
        adapter_record=adapter_record,
        worker_record=worker_record,
        action_apply_result=action_apply_result,
        terminal_stage=stage,
        terminal_reason=_stream_terminal_reason(phase_two),
    )


def _build_repair_specimen_contract(
    draft: ValidatedPlannerDraft,
) -> RookWorkflowContract:
    _require_validated_draft(draft)
    return RookWorkflowContract(
        workflow_id=_WORKFLOW_ID,
        template=WorkflowTemplateRef(
            descriptor={
                "domain": "grasshopper",
                "operation": "create_verify_repair_verify",
                "language": "csharp",
            },
            expected_template_id=_TEMPLATE_ID,
        ),
        initial_params=(
            InitialNodeParams(
                node_id=_CREATE_NODE_ID,
                execution_params={
                    "code": _SPECIMEN_INITIAL_BODY,
                    "pins_in": list(draft.interface.inputs),
                    "pins_out": [
                        f"{output.name}:{output.type}"
                        for output in draft.interface.outputs
                    ],
                    "name": "RookMinimalRepairHandoff",
                    "x": 375,
                    "y": 1080,
                },
            ),
        ),
        rules=(
            WorkflowNodeRule(
                _CREATE_NODE_ID,
                (ProducerStepSpec(_CREATE_NODE_ID),),
            ),
            WorkflowNodeRule(
                _VERIFY_CREATE_NODE_ID,
                (
                    VerifierStepSpec(
                        _VERIFY_CREATE_NODE_ID,
                        _CREATE_NODE_ID,
                        expected_outcome="needs_repair",
                    ),
                ),
            ),
            WorkflowNodeRule(
                _REPAIR_NODE_ID,
                (ProducerStepSpec(_REPAIR_NODE_ID),),
            ),
            WorkflowNodeRule(
                _VERIFY_REPAIR_NODE_ID,
                (
                    VerifierStepSpec(
                        _VERIFY_REPAIR_NODE_ID,
                        _REPAIR_NODE_ID,
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=(_TERMINAL_NODE_ID,),
        expected_refs=(
            ExpectedNodeRef(_CREATE_NODE_ID, "gh_create_csharp_script:v1"),
            ExpectedNodeRef(_REPAIR_NODE_ID, "gh_update_script:v1"),
        ),
        max_steps=6,
        metadata={
            "capability": _CAPABILITY,
            "acceptance": _ACCEPTANCE,
        },
    )


@dataclass(frozen=True)
class _ToolExecutorRunner:
    tool_executor: Callable[[str, dict[str, Any]], Any]

    async def run_live_producer_node(
        self,
        graph: PlanGraph,
        node_id: str,
    ) -> LiveProducerResult:
        return await run_live_producer_node_with_executor(
            graph,
            node_id,
            self.tool_executor,
        )


def _script_body_gotcha_packet() -> WorkerKnowledgePacket:
    return WorkerKnowledgePacket(
        packet_id="script_body_gotcha",
        kind="gotcha",
        title="C# script components use body-style code",
        content={"body_mode": "body"},
    )


def _repair_action() -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=_ACTION_ID,
        kind=_ACTION_ID,
        description="Draft a complete replacement C# body.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "code": {"type": "string"},
                "mode": {"const": "body"},
            },
            "required": ["code", "mode"],
        },
    )


def _current_diagnostic_packet(
    source: AcceptanceCriteriaSource,
) -> WorkerKnowledgePacket:
    value = source.value
    if (
        not isinstance(value, list)
        or len(value) != 1
        or not isinstance(value[0], str)
    ):
        raise RuntimeError("extracted receipt diagnostic is not the admitted shape")
    return WorkerKnowledgePacket(
        packet_id="current_receipt_diagnostic",
        kind="current_diagnostic",
        title="Current C# compile diagnostic",
        content={
            "source_class": source.source_class,
            "source_path": source.source_path,
            "target_errors": list(value),
        },
    )


def _build_worker_context(
    *,
    draft: ValidatedPlannerDraft,
    contract: RookWorkflowContract,
    scaffold: CompiledWorkflowScaffold,
    graph: PlanGraph,
    step_records: tuple[CurrentStepRecord, ...],
    supply_records: tuple[EnvelopeSupplyRecord, ...],
) -> LocalWorkerTurnContext:
    convention_packet = _script_body_gotcha_packet()
    sources = extract_acceptance_criteria_sources(
        workflow_contract=contract,
        graph=graph,
        convention_packets=(convention_packet,),
    )
    _require_convention_agreement(convention_packet, sources.convention.value)
    acceptance_packet = assemble_acceptance_criteria_packet(sources)
    compiled_interface = _project_compiled_interface(scaffold)
    if compiled_interface != _render_draft_interface(draft.interface):
        raise RuntimeError("compiled create interface differs from validated draft")
    return build_local_worker_turn_context(
        scaffold,
        graph,
        step_records,
        supply_records,
        current_node_id=_REPAIR_NODE_ID,
        knowledge=(
            WorkerKnowledgePacket(
                packet_id="planner_goal_and_interface",
                kind="requirement",
                title="Planner goal and fixed component interface",
                content={"goal": draft.goal, "interface": compiled_interface},
            ),
            convention_packet,
            WorkerKnowledgePacket(
                packet_id="clean_compile_acceptance",
                kind="acceptance_criteria",
                title="Clean compile receipt acceptance",
                content=acceptance_packet,
            ),
            _current_diagnostic_packet(sources.receipt_diagnostic),
        ),
        allowed_actions=(_repair_action(),),
    )


def _handoff_result(
    *,
    draft: ValidatedPlannerDraft,
    scaffold: CompiledWorkflowScaffold,
    phase_one: CurrentStepStreamResult,
    terminal_stage: TerminalStage,
    terminal_reason: str,
    phase_two: CurrentStepStreamResult | None = None,
    worker_request: Mapping[str, Any] | None = None,
    worker_context: LocalWorkerTurnContext | None = None,
    adapter_record: LocalWorkerAdapterRecord | None = None,
    worker_record: LocalWorkerTurnHarnessRecord | None = None,
    action_apply_result: WorkerActionApplyResult | None = None,
) -> MinimalCSharpRepairHandoffResult:
    if phase_two is None:
        final_graph = phase_one.final_graph
        step_records = phase_one.records
        supply_records = phase_one.supply_records
    else:
        final_graph = phase_two.final_graph
        step_records = phase_one.records + phase_two.records
        supply_records = phase_one.supply_records + phase_two.supply_records
    return MinimalCSharpRepairHandoffResult(
        draft=draft,
        scaffold=scaffold,
        final_graph=final_graph,
        supply_records=supply_records,
        step_records=step_records,
        worker_request=worker_request,
        worker_context=worker_context,
        adapter_record=adapter_record,
        worker_record=worker_record,
        action_apply_result=action_apply_result,
        terminal_stage=terminal_stage,
        terminal_reason=terminal_reason,
    )


def _phase_one_reached_frontier(result: CurrentStepStreamResult) -> bool:
    accepted = tuple(record.accepted_node_id for record in result.records)
    _require_record_prefix(
        accepted,
        (_CREATE_NODE_ID, _VERIFY_CREATE_NODE_ID),
        "create phase",
    )
    if accepted != (_CREATE_NODE_ID, _VERIFY_CREATE_NODE_ID):
        return False
    if result.stop_reason != "max_steps_reached":
        return False
    repair = result.final_graph.nodes[_REPAIR_NODE_ID]
    return repair.status == "ready" and EXECUTION_PARAMS_KEY not in repair.metadata


def _phase_two_reached_terminal(result: CurrentStepStreamResult) -> bool:
    accepted = tuple(record.accepted_node_id for record in result.records)
    _require_record_prefix(
        accepted,
        (_REPAIR_NODE_ID, _VERIFY_REPAIR_NODE_ID),
        "repair phase",
    )
    terminal_selected = (
        result.stop_reason == "provider_halt"
        and bool(result.supply_records)
        and result.supply_records[-1].decision == "HALT"
        and result.supply_records[-1].reason == "terminal_node_selected:done"
    )
    if not terminal_selected:
        return False
    if accepted != (_REPAIR_NODE_ID, _VERIFY_REPAIR_NODE_ID):
        raise RuntimeError("terminal selection lacks the complete repair record path")
    verifier = result.records[-1]
    if verifier.verifier_outcome_status != "succeeded":
        raise RuntimeError("terminal selection lacks successful reverify evidence")
    if result.final_graph.nodes[_TERMINAL_NODE_ID].status != "ready":
        raise RuntimeError("terminal selection lacks the native ready terminal node")
    return True


def _require_record_prefix(
    observed: tuple[str | None, ...],
    expected: tuple[str, ...],
    context: str,
) -> None:
    if observed != expected[: len(observed)]:
        raise RuntimeError(f"{context} record sequence is not an allowed prefix")


def _last_accepted_node_id(
    records: tuple[CurrentStepRecord, ...],
) -> str | None:
    return records[-1].accepted_node_id if records else None


def _stream_terminal_reason(result: CurrentStepStreamResult) -> str:
    if result.stop_reason in {"provider_halt", "provider_invalid"}:
        if not result.supply_records:
            raise RuntimeError("stream stop lacks a supply record")
        return _supply_record_reason(result.supply_records[-1])
    if result.stop_reason == "provider_error":
        raise RuntimeError("provider error lacks a projected native reason")
    if not result.records:
        raise RuntimeError("stream stop lacks a current-step record")
    return _current_step_reason(result.records[-1])


def _current_step_reason(record: CurrentStepRecord) -> str:
    if record.execution_kind == "producer" and record.producer_reason is not None:
        return _required_reason(record.producer_reason, "producer stop")
    if record.execution_kind == "verifier" and record.verifier_reason is not None:
        return _required_reason(record.verifier_reason, "verifier stop")
    if record.execution_kind == "bind" and record.bind_reason is not None:
        return _required_reason(record.bind_reason, "bind stop")
    for value in (record.execution_failure, record.mapping_failure):
        if value is not None:
            return _required_reason(value, "current-step stop")
    return _required_reason(record.execution.reason, "current-step execution")


def _supply_record_reason(record: EnvelopeSupplyRecord) -> str:
    if record.reason is not None:
        return _required_reason(record.reason, "supply stop")
    if record.invalid_reason is not None:
        return _required_reason(record.invalid_reason, "invalid supply stop")
    raise RuntimeError("supply stop lacks reason or invalid_reason")


def _required_reason(value: object, context: str) -> str:
    if type(value) is not str or not value:
        raise RuntimeError(f"{context} lacks an exact native reason")
    return value


def _validate_handoff_result(result: MinimalCSharpRepairHandoffResult) -> None:
    _require_validated_draft(result.draft)
    if not isinstance(result.scaffold, CompiledWorkflowScaffold):
        raise TypeError("result scaffold must be CompiledWorkflowScaffold")
    if not isinstance(result.final_graph, PlanGraph):
        raise TypeError("result final_graph must be PlanGraph")
    if type(result.step_records) is not tuple or not all(
        type(record) is CurrentStepRecord for record in result.step_records
    ):
        raise TypeError("result step_records must be exact native records")
    if type(result.supply_records) is not tuple or not all(
        type(record) is EnvelopeSupplyRecord for record in result.supply_records
    ):
        raise TypeError("result supply_records must be exact native records")
    stage = _require_exact_string(result.terminal_stage, "terminal_stage")
    if stage not in {
        "create",
        "verify_create",
        "worker_adapter",
        "worker_disposition",
        "action_apply",
        "repair",
        "verify_repair",
        "terminal",
    }:
        raise ValueError(f"unknown terminal_stage: {stage!r}")
    reason = _require_exact_string(result.terminal_reason, "terminal_reason")
    if not reason:
        raise ValueError("terminal_reason must not be empty")
    _require_native_transaction_lineage(result, stage)

    if stage in {"create", "verify_create"}:
        _require_no_worker_material(result)
        _require_result_reason(result, _ledger_terminal_reason(result))
        return

    context = _require_worker_request_context(result)
    adapter = _require_adapter_record(result.adapter_record)
    if stage == "worker_adapter":
        if adapter.status == "response_loaded":
            raise ValueError("worker_adapter stage requires an adapter failure")
        if result.worker_record is not None or result.action_apply_result is not None:
            raise ValueError("worker_adapter stage cannot carry later records")
        _require_result_reason(
            result,
            _required_reason(adapter.failure_reason, "adapter failure"),
        )
        return

    if adapter.status != "response_loaded" or adapter.response is None:
        raise ValueError("later worker stages require a loaded adapter response")
    worker = _require_worker_record(result.worker_record)
    _require_harness_context_lineage(worker, context)
    if worker.status != "completed" or worker.disposition is None:
        raise ValueError("later worker stages require a completed disposition")
    if worker.response is not adapter.response:
        raise ValueError("worker response must be the exact adapter-loaded object")
    candidate = worker.disposition.disposition == "candidate_action_request"

    if stage == "worker_disposition":
        if candidate:
            raise ValueError("worker_disposition stage requires a non-candidate result")
        if result.action_apply_result is not None:
            raise ValueError("worker_disposition stage cannot carry action application")
        _require_result_reason(result, worker.disposition.reason)
        return

    if not candidate:
        raise ValueError("action and execution stages require a candidate disposition")
    action = _require_action_result(result.action_apply_result)
    if stage == "action_apply":
        if action.applied:
            raise ValueError("action_apply stage requires an unapplied action")
        _require_result_reason(
            result,
            _required_reason(action.reason, "rejected action application"),
        )
        return

    if not action.applied:
        raise ValueError("execution stages require an applied worker action")
    _require_result_reason(result, _ledger_terminal_reason(result))


def _require_no_worker_material(result: MinimalCSharpRepairHandoffResult) -> None:
    if any(
        value is not None
        for value in (
            result.worker_request,
            result.worker_context,
            result.adapter_record,
            result.worker_record,
            result.action_apply_result,
        )
    ):
        raise ValueError("early execution stages cannot carry worker records")


def _require_worker_request_context(
    result: MinimalCSharpRepairHandoffResult,
) -> LocalWorkerTurnContext:
    if type(result.worker_request) is not dict:
        raise ValueError("worker stage requires worker_request")
    if type(result.worker_context) is not LocalWorkerTurnContext:
        raise ValueError("worker stage requires worker_context")
    context = result.worker_context
    rendered_request = render_local_worker_turn_request_payload(context)
    if _canonical_payload_bytes(result.worker_request, "worker_request") != (
        _canonical_payload_bytes(rendered_request, "rendered worker_request")
    ):
        raise ValueError("worker_request differs from its retained worker_context")

    workflow = context.workflow
    record = result.scaffold.compile_record
    if (
        workflow.workflow_id,
        workflow.contract_schema,
        workflow.contract_fingerprint,
        workflow.compiler_id,
        workflow.provider_id,
        workflow.selected_template_id,
        workflow.max_steps,
    ) != (
        record.workflow_id,
        record.contract_schema,
        record.contract_fingerprint,
        record.compiler_id,
        record.provider_id,
        record.selected_template_id,
        result.scaffold.max_steps,
    ):
        raise ValueError("worker_context workflow differs from its scaffold")

    phase_one_records = result.step_records[:2]
    phase_one_supply = result.supply_records[:2]
    phase_one_graph = phase_one_records[-1].execution.graph
    try:
        expected_context = _build_worker_context(
            draft=result.draft,
            contract=_build_repair_specimen_contract(result.draft),
            scaffold=result.scaffold,
            graph=phase_one_graph,
            step_records=phase_one_records,
            supply_records=phase_one_supply,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        raise ValueError("worker_context cannot be reconstructed") from exc
    if _canonical_payload_bytes(
        render_local_worker_turn_request_payload(context),
        "worker_context",
    ) != _canonical_payload_bytes(
        render_local_worker_turn_request_payload(expected_context),
        "expected worker_context",
    ):
        raise ValueError("worker_context differs from the native transaction")
    return context


def _require_adapter_record(value: object) -> LocalWorkerAdapterRecord:
    if type(value) is not LocalWorkerAdapterRecord:
        raise ValueError("worker stage requires an exact adapter record")
    return value


def _require_worker_record(value: object) -> LocalWorkerTurnHarnessRecord:
    if type(value) is not LocalWorkerTurnHarnessRecord:
        raise ValueError("worker stage requires an exact harness record")
    return value


def _require_action_result(value: object) -> WorkerActionApplyResult:
    if type(value) is not WorkerActionApplyResult:
        raise ValueError("action stage requires an exact action-apply result")
    return value


def _require_native_transaction_lineage(
    result: MinimalCSharpRepairHandoffResult,
    stage: str,
) -> None:
    expected_prefix_by_stage = {
        "create": (_CREATE_NODE_ID,),
        "verify_create": (_CREATE_NODE_ID, _VERIFY_CREATE_NODE_ID),
        "worker_adapter": (_CREATE_NODE_ID, _VERIFY_CREATE_NODE_ID),
        "worker_disposition": (_CREATE_NODE_ID, _VERIFY_CREATE_NODE_ID),
        "action_apply": (_CREATE_NODE_ID, _VERIFY_CREATE_NODE_ID),
        "repair": (
            _CREATE_NODE_ID,
            _VERIFY_CREATE_NODE_ID,
            _REPAIR_NODE_ID,
        ),
        "verify_repair": (
            _CREATE_NODE_ID,
            _VERIFY_CREATE_NODE_ID,
            _REPAIR_NODE_ID,
            _VERIFY_REPAIR_NODE_ID,
        ),
        "terminal": (
            _CREATE_NODE_ID,
            _VERIFY_CREATE_NODE_ID,
            _REPAIR_NODE_ID,
            _VERIFY_REPAIR_NODE_ID,
        ),
    }
    observed = tuple(record.accepted_node_id for record in result.step_records)
    if observed != expected_prefix_by_stage[stage]:
        raise ValueError("terminal stage does not match the native record prefix")
    if result.final_graph is not result.step_records[-1].execution.graph:
        raise ValueError("final_graph is not owned by the final native record")

    record_count = len(result.step_records)
    if len(result.supply_records) not in {record_count, record_count + 1}:
        raise ValueError("supply records do not match the native record prefix")
    for index, record in enumerate(result.step_records):
        supply = result.supply_records[index]
        if (
            supply.decision != "SUPPLY"
            or supply.envelope is None
            or supply.envelope.mapping is not record.mapping
        ):
            raise ValueError("supply records do not own the native record prefix")
    tail = result.supply_records[record_count:]
    if tail and (tail[0].decision != "HALT" or tail[0].envelope is not None):
        raise ValueError("native record prefix has an invalid terminal supply")
    if tail and stage not in {"create", "repair", "verify_repair", "terminal"}:
        raise ValueError("terminal supply occurs outside its native stage")
    if stage == "terminal":
        if (
            len(tail) != 1
            or tail[0].reason != "terminal_node_selected:done"
        ):
            raise ValueError("terminal stage lacks its native terminal supply")
        _require_terminal_graph_evidence(result)


def _require_harness_context_lineage(
    worker: LocalWorkerTurnHarnessRecord,
    context: LocalWorkerTurnContext,
) -> None:
    workflow_id = context.workflow.workflow_id
    fingerprint = context.workflow.contract_fingerprint
    if worker.context_workflow_id != workflow_id:
        raise ValueError("harness workflow identity differs from worker_context")
    if worker.context_contract_fingerprint != fingerprint:
        raise ValueError("harness contract identity differs from worker_context")
    disposition = worker.disposition
    if disposition is None:
        return
    attempt = disposition.attempt
    if attempt.context_workflow_id != workflow_id:
        raise ValueError("harness attempt workflow differs from worker_context")
    if attempt.context_contract_fingerprint != fingerprint:
        raise ValueError("harness attempt contract differs from worker_context")


def _require_terminal_graph_evidence(
    result: MinimalCSharpRepairHandoffResult,
) -> None:
    records = result.step_records
    expected_record_outcomes = (
        ("producer", True, "succeeded"),
        ("verifier", True, "needs_repair"),
        ("producer", True, "succeeded"),
        ("verifier", True, "succeeded"),
    )
    observed_record_outcomes = (
        (
            records[0].execution_kind,
            records[0].producer_applied,
            records[0].producer_outcome_status,
        ),
        (
            records[1].execution_kind,
            records[1].verifier_applied,
            records[1].verifier_outcome_status,
        ),
        (
            records[2].execution_kind,
            records[2].producer_applied,
            records[2].producer_outcome_status,
        ),
        (
            records[3].execution_kind,
            records[3].verifier_applied,
            records[3].verifier_outcome_status,
        ),
    )
    if observed_record_outcomes != expected_record_outcomes:
        raise ValueError("terminal native record outcomes are incomplete")

    graph = result.final_graph
    expected_statuses = {
        _CREATE_NODE_ID: "succeeded",
        _VERIFY_CREATE_NODE_ID: "needs_repair",
        _REPAIR_NODE_ID: "succeeded",
        _VERIFY_REPAIR_NODE_ID: "succeeded",
        _TERMINAL_NODE_ID: "ready",
    }
    if not expected_statuses.keys() <= graph.nodes.keys():
        raise ValueError("terminal final_graph lacks required native nodes")
    if {
        node_id: graph.nodes[node_id].status for node_id in expected_statuses
    } != expected_statuses:
        raise ValueError("terminal final_graph has incomplete native state")
    _require_receipt_projection(
        graph,
        _CREATE_NODE_ID,
        operation="create",
        artifact_status="created_with_errors",
        verification_status="failed",
    )
    _require_receipt_projection(
        graph,
        _REPAIR_NODE_ID,
        operation="update",
        artifact_status="usable",
        verification_status="passed",
    )
    verify_evidence = graph.nodes[_VERIFY_REPAIR_NODE_ID].evidence
    if verify_evidence is None or verify_evidence.verified is not True:
        raise ValueError("terminal final_graph lacks successful reverify evidence")


def _require_receipt_projection(
    graph: PlanGraph,
    node_id: str,
    *,
    operation: str,
    artifact_status: str,
    verification_status: str,
) -> None:
    evidence = graph.nodes[node_id].evidence
    receipt = None if evidence is None else evidence.receipt
    if not isinstance(receipt, Mapping):
        raise ValueError(f"terminal final_graph lacks {node_id} receipt evidence")
    verification = receipt.get("verification")
    if (
        receipt.get("operation") != operation
        or receipt.get("artifact_status") != artifact_status
        or not isinstance(verification, Mapping)
        or verification.get("status") != verification_status
    ):
        raise ValueError(f"terminal final_graph has invalid {node_id} receipt evidence")


def _canonical_payload_bytes(value: object, context: str) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context} is not canonical JSON evidence") from exc


def _ledger_terminal_reason(result: MinimalCSharpRepairHandoffResult) -> str:
    if result.supply_records:
        supply = result.supply_records[-1]
        if supply.decision == "HALT" or supply.invalid_reason is not None:
            return _supply_record_reason(supply)
    if not result.step_records:
        raise RuntimeError("execution result lacks a native reason owner")
    return _current_step_reason(result.step_records[-1])


def _require_result_reason(
    result: MinimalCSharpRepairHandoffResult,
    expected: str,
) -> None:
    if result.terminal_reason != expected:
        raise ValueError("terminal_reason differs from its native owner")


def _project_compiled_interface(
    scaffold: CompiledWorkflowScaffold,
) -> dict[str, list[dict[str, str]]]:
    params = scaffold.graph.nodes[_CREATE_NODE_ID].metadata.get(EXECUTION_PARAMS_KEY)
    if not isinstance(params, Mapping):
        raise RuntimeError("compiled create parameters are missing")
    if set(params) != {"code", "pins_in", "pins_out", "name", "x", "y"}:
        raise RuntimeError("compiled create parameter shape differs")
    pins_in = params["pins_in"]
    pins_out = params["pins_out"]
    if not isinstance(pins_in, tuple) or not isinstance(pins_out, tuple):
        raise RuntimeError("compiled pin parameters are not immutable tuples")
    return {
        "inputs": [_pin_from_contract_token(item) for item in pins_in],
        "outputs": [_pin_from_contract_token(item) for item in pins_out],
    }


def _pin_from_contract_token(value: object) -> dict[str, str]:
    if not isinstance(value, str) or value.count(":") != 1:
        raise RuntimeError("compiled pin token is malformed")
    name, pin_type = value.split(":", 1)
    if not name or not pin_type:
        raise RuntimeError("compiled pin token is malformed")
    return {"name": name, "type": pin_type}


def _render_draft_interface(
    interface: PlannerDraftInterface,
) -> dict[str, list[dict[str, str]]]:
    return {
        "inputs": [],
        "outputs": [
            {"name": output.name, "type": output.type}
            for output in interface.outputs
        ],
    }


def _require_convention_agreement(
    packet: WorkerKnowledgePacket,
    extracted_value: object,
) -> None:
    packet_mode = packet.content.get("body_mode")
    if not isinstance(extracted_value, Mapping):
        raise RuntimeError("extracted convention value is not a mapping")
    extracted_mode = extracted_value.get("mode")
    if packet_mode != extracted_mode:
        raise RuntimeError("worker convention mode differs from acceptance source")


def _project_anchor_binding(graph: PlanGraph) -> dict[str, str]:
    evidence = graph.nodes[_CREATE_NODE_ID].evidence
    receipt = getattr(evidence, "receipt", None)
    if not isinstance(receipt, Mapping):
        raise RuntimeError("create receipt is missing")
    receipt_anchor = receipt.get("repair_anchor")
    memory_anchor = graph.memory.facts.get("repair_anchor")
    if not isinstance(receipt_anchor, Mapping) or not isinstance(
        memory_anchor, Mapping
    ):
        raise RuntimeError("repair anchor is missing")
    receipt_guid = receipt_anchor.get("component_guid")
    memory_guid = memory_anchor.get("component_guid")
    if not isinstance(receipt_guid, str) or not receipt_guid:
        raise RuntimeError("receipt repair anchor GUID is missing")
    if receipt_guid != memory_guid:
        raise RuntimeError("receipt and graph-memory repair anchors differ")
    return {"component_guid": receipt_guid, "language": "csharp"}


def _require_mapping(value: object, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise TypeError(f"{context} keys must be strings")
    return value


def _require_exact_string(value: object, context: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{context} must be an exact string")
    return value


def _require_planner_output(value: object) -> PlannerDraftOutput:
    if type(value) is not PlannerDraftOutput:
        raise TypeError("Planner draft output must be the exact validated type")
    name = _require_exact_string(value.name, "Planner draft output name")
    if name != "A":
        raise ValueError("Planner draft output name must be 'A'")
    pin_type = _require_exact_string(value.type, "Planner draft output type")
    if pin_type != "double":
        raise ValueError("Planner draft output type must be 'double'")
    return value


def _require_planner_interface(value: object) -> PlannerDraftInterface:
    if type(value) is not PlannerDraftInterface:
        raise TypeError("Planner draft interface must be the exact validated type")
    if type(value.inputs) is not tuple or value.inputs:
        raise ValueError("Planner draft interface inputs must be the exact empty tuple")
    if type(value.outputs) is not tuple or len(value.outputs) != 1:
        raise ValueError("Planner draft interface requires one exact output")
    _require_planner_output(value.outputs[0])
    return value


def _require_validated_draft(value: object) -> ValidatedPlannerDraft:
    if type(value) is not ValidatedPlannerDraft:
        raise TypeError("draft must be the exact ValidatedPlannerDraft type")
    goal = _require_exact_string(value.goal, "Planner draft goal")
    if not goal.strip():
        raise ValueError("Planner draft goal must be a non-empty string")
    capability = _require_exact_string(
        value.capability,
        "Planner draft capability",
    )
    if capability != _CAPABILITY:
        raise ValueError(f"Planner draft capability must be {_CAPABILITY!r}")
    _require_planner_interface(value.interface)
    acceptance = _require_exact_string(
        value.acceptance,
        "Planner draft acceptance",
    )
    if acceptance != _ACCEPTANCE:
        raise ValueError(f"Planner draft acceptance must be {_ACCEPTANCE!r}")
    return value


def _require_exact_fields(
    value: Mapping[str, Any],
    expected: frozenset[str],
    context: str,
) -> None:
    observed = set(value)
    if observed != expected:
        raise ValueError(
            f"{context} fields must be exactly {sorted(expected)!r}; "
            f"observed {sorted(observed)!r}"
        )
