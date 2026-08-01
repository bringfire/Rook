"""One-turn Worker-authored initial C# body handoff."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal

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
from rook.agent.local_worker_turn_disposition import (
    dispose_local_worker_turn_response,
)
from rook.agent.local_worker_turn_harness import (
    LocalWorkerTurnHarnessRecord,
    run_local_worker_turn,
)
from rook.agent.local_worker_turn_request import (
    render_local_worker_turn_request_payload,
)
from rook.agent.local_worker_turn_response import WorkerActionRequest
from rook.agent.minimal_csharp_repair_handoff import (
    PlannerDraftInterface,
    ValidatedPlannerDraft,
    _require_validated_draft,
)
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepRecord,
    project_current_step_record,
)
from rook.agent.plan_graph_current_step_stream import (
    CurrentStepStreamResult,
    EnvelopeSupplyRecord,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_live_dispatch import run_live_producer_node_with_executor
from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import StepExecutionResult
from rook.agent.plan_graph_step_mapping import map_accepted_proposal_to_step
from rook.agent.plan_graph_worker_create_body_apply import (
    WorkerCreateBodyApplyResult,
    _exact_value_equal,
    apply_worker_create_body_to_scaffold,
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
from rook.learning.plan_graph import PlanGraph, apply_outcome
from rook.learning.plan_graph_projection import project_receipt_outcome
from rook.learning.plan_graph_runner import apply_verifier_step


__all__ = (
    "MinimalCSharpInitialBodyHandoffResult",
    "run_minimal_csharp_initial_body_handoff",
)


_WORKFLOW_ID = "minimal_csharp_initial_body_handoff"
_TEMPLATE_ID = "gh_csharp_create_verify"
_CREATE_NODE_ID = "create_script"
_VERIFY_NODE_ID = "verify_create"
_TERMINAL_NODE_ID = "done"
_ACTION_ID = "draft_create_body"


TerminalStage = Literal[
    "worker_adapter",
    "worker_disposition",
    "action_apply",
    "create",
    "verify_create",
    "terminal",
]


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
    terminal_stage: TerminalStage
    terminal_reason: str

    def __post_init__(self) -> None:
        _validate_handoff_result(self)


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
    if not callable(tool_executor):
        raise TypeError("tool_executor must be callable")

    contract = _build_initial_body_contract(draft)
    scaffold = compile_workflow_contract(contract)
    context = _build_worker_context(draft, contract, scaffold)
    request = render_local_worker_turn_request_payload(context)
    adapter_record = run_local_worker_adapter(request, worker_transport)
    if adapter_record.status != "response_loaded":
        return _handoff_result(
            draft=draft,
            scaffold=scaffold,
            worker_request=request,
            worker_context=context,
            adapter_record=adapter_record,
            terminal_stage="worker_adapter",
            terminal_reason=_required_reason(
                adapter_record.failure_reason,
                "adapter failure",
            ),
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
            worker_request=request,
            worker_context=context,
            adapter_record=adapter_record,
            worker_record=worker_record,
            terminal_stage="worker_disposition",
            terminal_reason=disposition.reason,
        )

    payload = loaded_response.payload
    if type(payload) is not WorkerActionRequest:
        raise RuntimeError("candidate disposition lacks exact action payload")
    action_apply_result = apply_worker_create_body_to_scaffold(
        scaffold,
        _CREATE_NODE_ID,
        action_id=payload.action_id,
        action_input=payload.input,
    )
    if not action_apply_result.applied:
        return _handoff_result(
            draft=draft,
            scaffold=scaffold,
            worker_request=request,
            worker_context=context,
            adapter_record=adapter_record,
            worker_record=worker_record,
            action_apply_result=action_apply_result,
            terminal_stage="action_apply",
            terminal_reason=_required_reason(
                action_apply_result.reason,
                "rejected action application",
            ),
        )

    stream = await run_current_step_stream(
        action_apply_result.graph,
        scaffold.provider,
        max_steps=scaffold.max_steps,
        runner=_ToolExecutorRunner(tool_executor),
    )
    stage = _stage_from_stream(stream)
    return _handoff_result(
        draft=draft,
        scaffold=scaffold,
        worker_request=request,
        worker_context=context,
        adapter_record=adapter_record,
        worker_record=worker_record,
        action_apply_result=action_apply_result,
        stream=stream,
        terminal_stage=stage,
        terminal_reason=_stream_terminal_reason(stream),
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


def _draft_create_body_action() -> WorkerAllowedAction:
    return WorkerAllowedAction(
        action_id=_ACTION_ID,
        kind=_ACTION_ID,
        description="Draft the complete initial C# body.",
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    )


def _build_worker_context(
    draft: ValidatedPlannerDraft,
    contract: RookWorkflowContract,
    scaffold: CompiledWorkflowScaffold,
) -> LocalWorkerTurnContext:
    compiled_interface = _project_compiled_interface(scaffold)
    if compiled_interface != _render_draft_interface(draft.interface):
        raise RuntimeError("compiled create interface differs from validated draft")
    verifier = contract.rules[1].steps_by_seen_count[0]
    if type(verifier) is not VerifierStepSpec:
        raise RuntimeError("initial-body contract lacks its exact verifier rule")
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
                content={"goal": draft.goal, "interface": compiled_interface},
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
        allowed_actions=(_draft_create_body_action(),),
    )


def _project_compiled_interface(
    scaffold: CompiledWorkflowScaffold,
) -> dict[str, list[dict[str, str]]]:
    params = scaffold.graph.nodes[_CREATE_NODE_ID].metadata.get(EXECUTION_PARAMS_KEY)
    if not isinstance(params, Mapping):
        raise RuntimeError("compiled create parameters are missing")
    if set(params) != {"pins_in", "pins_out", "name", "x", "y"}:
        raise RuntimeError("compiled create parameter shape differs")
    pins_in = params["pins_in"]
    pins_out = params["pins_out"]
    if type(pins_in) is not tuple or type(pins_out) is not tuple:
        raise RuntimeError("compiled pin parameters are not immutable tuples")
    return {
        "inputs": [_pin_from_contract_token(item) for item in pins_in],
        "outputs": [_pin_from_contract_token(item) for item in pins_out],
    }


def _pin_from_contract_token(value: object) -> dict[str, str]:
    if type(value) is not str or value.count(":") != 1:
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


def _handoff_result(
    *,
    draft: ValidatedPlannerDraft,
    scaffold: CompiledWorkflowScaffold,
    worker_request: Mapping[str, Any],
    worker_context: LocalWorkerTurnContext,
    adapter_record: LocalWorkerAdapterRecord,
    terminal_stage: TerminalStage,
    terminal_reason: str,
    worker_record: LocalWorkerTurnHarnessRecord | None = None,
    action_apply_result: WorkerCreateBodyApplyResult | None = None,
    stream: CurrentStepStreamResult | None = None,
) -> MinimalCSharpInitialBodyHandoffResult:
    return MinimalCSharpInitialBodyHandoffResult(
        draft=draft,
        scaffold=scaffold,
        final_graph=(scaffold.graph if stream is None else stream.final_graph),
        supply_records=(() if stream is None else stream.supply_records),
        step_records=(() if stream is None else stream.records),
        worker_request=worker_request,
        worker_context=worker_context,
        adapter_record=adapter_record,
        worker_record=worker_record,
        action_apply_result=action_apply_result,
        terminal_stage=terminal_stage,
        terminal_reason=terminal_reason,
    )


def _stage_from_stream(result: CurrentStepStreamResult) -> TerminalStage:
    accepted = tuple(record.accepted_node_id for record in result.records)
    expected = (_CREATE_NODE_ID, _VERIFY_NODE_ID)
    if accepted != expected[: len(accepted)]:
        raise RuntimeError("create stream record sequence is not an allowed prefix")
    terminal_selected = (
        result.stop_reason == "provider_halt"
        and bool(result.supply_records)
        and result.supply_records[-1].decision == "HALT"
        and result.supply_records[-1].reason == "terminal_node_selected:done"
    )
    if terminal_selected:
        if (
            accepted != expected
            or result.records[-1].verifier_outcome_status != "succeeded"
            or result.final_graph.nodes[_TERMINAL_NODE_ID].status != "ready"
        ):
            raise RuntimeError("terminal selection lacks complete create verification")
        return "terminal"
    if accepted and accepted[-1] == _VERIFY_NODE_ID:
        return "verify_create"
    return "create"


def _stream_terminal_reason(result: CurrentStepStreamResult) -> str:
    if result.stop_reason in {"provider_halt", "provider_invalid"}:
        if not result.supply_records:
            raise RuntimeError("stream stop lacks a supply record")
        supply = result.supply_records[-1]
        if supply.reason is not None:
            return _required_reason(supply.reason, "supply stop")
        return _required_reason(supply.invalid_reason, "invalid supply stop")
    if result.stop_reason == "provider_error":
        raise RuntimeError("provider error lacks a projected native reason")
    if not result.records:
        raise RuntimeError("stream stop lacks a current-step record")
    record = result.records[-1]
    for value in (
        record.producer_reason,
        record.verifier_reason,
        record.execution_failure,
        record.mapping_failure,
        record.execution.reason,
    ):
        if value is not None:
            return _required_reason(value, "current-step stop")
    raise RuntimeError("current-step stop lacks a native reason")


def _required_reason(value: object, context: str) -> str:
    if type(value) is not str or not value:
        raise RuntimeError(f"{context} lacks an exact native reason")
    return value


def _validate_handoff_result(
    result: MinimalCSharpInitialBodyHandoffResult,
) -> None:
    _require_validated_draft(result.draft)
    if type(result.scaffold) is not CompiledWorkflowScaffold:
        raise TypeError("result scaffold must be exact CompiledWorkflowScaffold")
    expected_scaffold = compile_workflow_contract(
        _build_initial_body_contract(result.draft)
    )
    if not _exact_value_equal(result.scaffold, expected_scaffold):
        raise ValueError("result scaffold differs from the validated draft")
    if type(result.final_graph) is not PlanGraph:
        raise TypeError("result final_graph must be exact PlanGraph")
    if type(result.step_records) is not tuple or not all(
        type(record) is CurrentStepRecord for record in result.step_records
    ):
        raise TypeError("result step_records must be exact native records")
    if type(result.supply_records) is not tuple or not all(
        type(record) is EnvelopeSupplyRecord for record in result.supply_records
    ):
        raise TypeError("result supply_records must be exact native records")
    stage = result.terminal_stage
    if type(stage) is not str or stage not in {
        "worker_adapter",
        "worker_disposition",
        "action_apply",
        "create",
        "verify_create",
        "terminal",
    }:
        raise ValueError("result terminal_stage is invalid")
    _required_reason(result.terminal_reason, "result terminal_reason")

    contract = _build_initial_body_contract(result.draft)
    expected_context = _build_worker_context(
        result.draft,
        contract,
        result.scaffold,
    )
    if type(result.worker_context) is not LocalWorkerTurnContext or not (
        _exact_value_equal(result.worker_context, expected_context)
    ):
        raise ValueError("worker context differs from compiler-owned inputs")
    expected_request = render_local_worker_turn_request_payload(expected_context)
    if not _exact_value_equal(result.worker_request, expected_request):
        raise ValueError("worker request differs from retained context")
    if type(result.adapter_record) is not LocalWorkerAdapterRecord:
        raise TypeError("result adapter_record must be exact")

    if stage == "worker_adapter":
        _require_pre_execution_result(
            result,
            worker_record=None,
            action_result=None,
        )
        if result.adapter_record.status == "response_loaded":
            raise ValueError("worker_adapter stage retains a loaded response")
        if result.terminal_reason != result.adapter_record.failure_reason:
            raise ValueError("worker_adapter reason differs from adapter record")
        return

    if (
        result.adapter_record.status != "response_loaded"
        or result.adapter_record.response is None
    ):
        raise ValueError("post-adapter stage lacks a loaded response")
    response = result.adapter_record.response
    expected_worker_record = run_local_worker_turn(
        expected_context,
        lambda supplied_context: (
            response
            if supplied_context is expected_context
            else _raise_context_mismatch()
        ),
    )
    if type(result.worker_record) is not LocalWorkerTurnHarnessRecord or not (
        _exact_value_equal(result.worker_record, expected_worker_record)
    ):
        raise ValueError("worker record differs from adapter response")
    disposition = dispose_local_worker_turn_response(expected_context, response)
    if result.worker_record.disposition is None or not _exact_value_equal(
        result.worker_record.disposition,
        disposition,
    ):
        raise ValueError("worker disposition differs from retained response")

    if disposition.disposition != "candidate_action_request":
        if stage != "worker_disposition":
            raise ValueError("non-action disposition has the wrong stage")
        _require_pre_execution_result(
            result,
            worker_record=result.worker_record,
            action_result=None,
        )
        if result.terminal_reason != disposition.reason:
            raise ValueError("worker_disposition reason differs from disposition")
        return

    payload = response.payload
    if type(payload) is not WorkerActionRequest:
        raise ValueError("candidate disposition lacks exact action payload")
    expected_action = apply_worker_create_body_to_scaffold(
        result.scaffold,
        _CREATE_NODE_ID,
        action_id=payload.action_id,
        action_input=payload.input,
    )
    if type(result.action_apply_result) is not WorkerCreateBodyApplyResult or not (
        _exact_value_equal(result.action_apply_result, expected_action)
    ):
        raise ValueError("action result differs from retained worker response")
    if not expected_action.applied:
        if stage != "action_apply":
            raise ValueError("rejected action result has the wrong stage")
        _require_pre_execution_result(
            result,
            worker_record=result.worker_record,
            action_result=result.action_apply_result,
        )
        if result.terminal_reason != expected_action.reason:
            raise ValueError("action_apply reason differs from action result")
        return

    if stage not in {"create", "verify_create", "terminal"}:
        raise ValueError("applied action result has a non-execution stage")
    _require_native_transaction_lineage(
        result,
        stage,
        result.action_apply_result.graph,
    )


def _raise_context_mismatch():
    raise RuntimeError("worker harness supplied a different context")


def _require_pre_execution_result(
    result: MinimalCSharpInitialBodyHandoffResult,
    *,
    worker_record: LocalWorkerTurnHarnessRecord | None,
    action_result: WorkerCreateBodyApplyResult | None,
) -> None:
    if result.worker_record is not worker_record:
        raise ValueError("pre-execution stage has the wrong worker record")
    if result.action_apply_result is not action_result:
        raise ValueError("pre-execution stage has the wrong action result")
    if result.step_records or result.supply_records:
        raise ValueError("pre-execution stage retains native execution records")
    if not _exact_value_equal(result.final_graph, result.scaffold.graph):
        raise ValueError("pre-execution final graph differs from the scaffold")


def _require_native_transaction_lineage(
    result: MinimalCSharpInitialBodyHandoffResult,
    stage: str,
    action_graph: PlanGraph,
) -> None:
    expected_prefix = {
        "create": (_CREATE_NODE_ID,),
        "verify_create": (_CREATE_NODE_ID, _VERIFY_NODE_ID),
        "terminal": (_CREATE_NODE_ID, _VERIFY_NODE_ID),
    }[stage]
    observed = tuple(record.accepted_node_id for record in result.step_records)
    if stage == "create":
        if observed not in {(), expected_prefix}:
            raise ValueError("create stage has an invalid native record prefix")
    elif observed != expected_prefix:
        raise ValueError("terminal stage does not match native record prefix")

    record_count = len(result.step_records)
    if len(result.supply_records) not in {record_count, record_count + 1}:
        raise ValueError("supply records do not match native record prefix")
    prior_graph = action_graph
    prior_records: list[CurrentStepRecord] = []
    prior_supplies: list[EnvelopeSupplyRecord] = []
    for index, record in enumerate(result.step_records):
        supply = result.supply_records[index]
        _require_provider_supply(
            result.scaffold,
            prior_graph,
            tuple(prior_records),
            tuple(prior_supplies),
            supply,
        )
        if (
            supply.decision != "SUPPLY"
            or supply.envelope is None
            or supply.envelope.mapping is not record.mapping
        ):
            raise ValueError("supply records do not own native record prefix")
        expected_record = project_current_step_record(
            supply.envelope,
            record.execution,
        )
        if not _exact_value_equal(record, expected_record):
            raise ValueError("native record differs from flattened projection")
        _require_record_transition(record, prior_graph)
        prior_graph = record.execution.graph
        prior_records.append(record)
        prior_supplies.append(supply)

    if result.step_records:
        if result.final_graph is not result.step_records[-1].execution.graph:
            raise ValueError("final graph is not owned by final native record")
    elif not _exact_value_equal(result.final_graph, action_graph):
        raise ValueError("empty execution prefix changed the action graph")

    tail = result.supply_records[record_count:]
    if tail:
        _require_provider_supply(
            result.scaffold,
            prior_graph,
            tuple(prior_records),
            tuple(prior_supplies),
            tail[0],
        )
    if tail and (tail[0].decision != "HALT" or tail[0].envelope is not None):
        raise ValueError("native record prefix has an invalid terminal supply")
    if stage == "terminal":
        if (
            len(tail) != 1
            or tail[0].reason != "terminal_node_selected:done"
            or result.terminal_reason != tail[0].reason
        ):
            raise ValueError("terminal stage lacks native terminal selection")
        _require_terminal_graph_evidence(result)
        return
    if result.terminal_reason != _ledger_terminal_reason(result):
        raise ValueError("execution reason differs from native ledger")
    if stage == "verify_create":
        if (
            not tail
            or tail[0].reason != "selector_halt:none_ready"
            or result.step_records[-1].verifier_outcome_status != "needs_repair"
            or result.final_graph.nodes[_TERMINAL_NODE_ID].status != "pending"
        ):
            raise ValueError("verify_create stage lacks compile-failure state")


def _require_provider_supply(
    scaffold: CompiledWorkflowScaffold,
    graph: PlanGraph,
    records: tuple[CurrentStepRecord, ...],
    supplies: tuple[EnvelopeSupplyRecord, ...],
    retained: EnvelopeSupplyRecord,
) -> None:
    expected = scaffold.provider(graph, records, supplies)
    if (
        retained.decision != expected.decision
        or retained.reason != expected.reason
        or not _exact_value_equal(retained.envelope, expected.envelope)
        or retained.invalid_reason is not None
        or retained.error_class is not None
        or retained.error_message is not None
    ):
        raise ValueError("supply record differs from compiler-owned provider")
    if expected.metadata is None:
        if (
            retained.metadata is not None
            or retained.metadata_status != "absent"
            or retained.metadata_error is not None
        ):
            raise ValueError("supply record has unexpected provider metadata")
        return
    if (
        retained.metadata_status != "copied"
        or retained.metadata_error is not None
        or retained.metadata is None
        or not _exact_value_equal(retained.metadata, dict(expected.metadata))
    ):
        raise ValueError("supply metadata differs from compiler-owned provider")


def _require_record_transition(
    record: CurrentStepRecord,
    prior_graph: PlanGraph,
) -> None:
    mapping = record.mapping
    step = mapping.step
    accepted = record.accepted_node_id
    if accepted is None or step is None:
        raise ValueError("native record lacks accepted mapped step")
    expected_mapping = map_accepted_proposal_to_step(
        mapping.revalidation.proposal,
        prior_graph,
        {accepted: step},
        mapping.revalidation.expected_selector_ids,
    )
    if not _exact_value_equal(mapping, expected_mapping):
        raise ValueError("native record mapping differs from preceding graph")
    execution = record.execution
    if type(execution) is not StepExecutionResult or execution.mapping is not mapping:
        raise ValueError("native execution carries another mapping")
    if type(step) is ProducerStep:
        _require_producer_transition(prior_graph, step, execution)
        return
    if type(step) is VerifierStep:
        expected = apply_verifier_step(
            prior_graph,
            step.verifier_node_id,
            step.source_node_id,
        )
        if (
            execution.ran is not True
            or execution.kind != "verifier"
            or execution.failure is not None
            or execution.reason
            != f"executed verifier step {step.verifier_node_id!r}"
            or execution.producer_result is not None
            or execution.bind_result is not None
            or not _exact_value_equal(execution.verifier_result, expected)
            or execution.graph is not execution.verifier_result.graph
        ):
            raise ValueError("verifier transition differs from native inputs")
        return
    raise ValueError("initial-body record carries unsupported step kind")


def _require_producer_transition(
    prior_graph: PlanGraph,
    step: ProducerStep,
    execution: StepExecutionResult,
) -> None:
    producer = execution.producer_result
    if type(producer) is not LiveProducerResult:
        raise ValueError("producer transition lacks native result")
    execution_ref = prior_graph.nodes[step.node_id].execution_ref
    expected_tool = (
        execution_ref.partition(":")[0]
        if type(execution_ref) is str and execution_ref
        else None
    )
    if (
        execution.ran is not True
        or execution.kind != "producer"
        or execution.failure is not None
        or execution.reason != f"executed producer step {step.node_id!r}"
        or execution.verifier_result is not None
        or execution.bind_result is not None
        or execution.graph is not producer.graph
        or producer.node_id != step.node_id
        or producer.tool_name != expected_tool
    ):
        raise ValueError("producer transition differs from native inputs")
    if producer.applied is False:
        if (
            producer.graph is not prior_graph
            or producer.outcome_status is not None
            or producer.reason is None
        ):
            raise ValueError("unapplied producer transition is not input-preserving")
        return
    if producer.applied is not True or producer.reason is not None:
        raise ValueError("producer transition has invalid applied state")
    evidence = producer.graph.nodes[step.node_id].evidence
    if evidence is None:
        raise ValueError("applied producer transition lacks receipt evidence")
    outcome = project_receipt_outcome(evidence, "artifact_producer")
    expected_graph = apply_outcome(prior_graph, step.node_id, outcome)
    if (
        producer.outcome_status != outcome.status
        or not _exact_value_equal(producer.graph, expected_graph)
    ):
        raise ValueError("producer transition differs from receipt projection")


def _ledger_terminal_reason(
    result: MinimalCSharpInitialBodyHandoffResult,
) -> str:
    if result.supply_records:
        supply = result.supply_records[-1]
        if supply.decision == "HALT" or supply.invalid_reason is not None:
            if supply.reason is not None:
                return _required_reason(supply.reason, "supply stop")
            return _required_reason(supply.invalid_reason, "invalid supply stop")
    if not result.step_records:
        raise ValueError("execution result lacks native reason owner")
    record = result.step_records[-1]
    for value in (
        record.producer_reason,
        record.verifier_reason,
        record.execution_failure,
        record.mapping_failure,
        record.execution.reason,
    ):
        if value is not None:
            return _required_reason(value, "current-step stop")
    raise ValueError("execution result lacks native reason")


def _require_terminal_graph_evidence(
    result: MinimalCSharpInitialBodyHandoffResult,
) -> None:
    records = result.step_records
    if (
        len(records) != 2
        or records[0].execution_kind != "producer"
        or records[0].producer_applied is not True
        or records[0].producer_outcome_status != "succeeded"
        or records[1].execution_kind != "verifier"
        or records[1].verifier_applied is not True
        or records[1].verifier_outcome_status != "succeeded"
    ):
        raise ValueError("terminal native outcomes are incomplete")
    expected_statuses = {
        _CREATE_NODE_ID: "succeeded",
        _VERIFY_NODE_ID: "succeeded",
        _TERMINAL_NODE_ID: "ready",
    }
    if {
        node_id: result.final_graph.nodes[node_id].status
        for node_id in expected_statuses
    } != expected_statuses:
        raise ValueError("terminal graph has incomplete native state")
    evidence = result.final_graph.nodes[_CREATE_NODE_ID].evidence
    receipt = None if evidence is None else evidence.receipt
    verification = receipt.get("verification") if isinstance(receipt, Mapping) else None
    if (
        not isinstance(receipt, Mapping)
        or receipt.get("operation") != "create"
        or receipt.get("artifact_status") != "usable"
        or not isinstance(verification, Mapping)
        or verification.get("status") != "passed"
    ):
        raise ValueError("terminal graph lacks clean create receipt")
