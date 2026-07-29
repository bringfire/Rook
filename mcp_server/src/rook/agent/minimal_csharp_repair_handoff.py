"""One internal C# repair-capability Planner/worker handoff.

This module composes existing workflow, worker, action, and receipt seams for
one fixed repair specimen. It does not invoke a Planner, construct a provider,
or expose Chat, MCP, CLI, or live-runtime entry points.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
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


def load_minimal_csharp_repair_draft(
    payload: Mapping[str, Any],
) -> ValidatedPlannerDraft:
    payload = _require_mapping(payload, "Planner draft")
    _require_exact_fields(
        payload,
        frozenset({"goal", "capability", "interface", "acceptance"}),
        "Planner draft",
    )
    goal = payload["goal"]
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError("Planner draft goal must be a non-empty string")
    if payload["capability"] != _CAPABILITY:
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
    if payload["acceptance"] != _ACCEPTANCE:
        raise ValueError(f"Planner draft acceptance must be {_ACCEPTANCE!r}")
    return ValidatedPlannerDraft(
        goal=goal,
        capability=_CAPABILITY,
        interface=PlannerDraftInterface(inputs=(), outputs=(output,)),
        acceptance=_ACCEPTANCE,
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
    _require_phase_one_frontier(phase_one)

    convention_packet = _script_body_gotcha_packet()
    sources = extract_acceptance_criteria_sources(
        workflow_contract=contract,
        graph=phase_one.final_graph,
        convention_packets=(convention_packet,),
    )
    _require_convention_agreement(convention_packet, sources.convention.value)
    acceptance_packet = assemble_acceptance_criteria_packet(sources)
    compiled_interface = _project_compiled_interface(scaffold)
    if compiled_interface != _render_draft_interface(draft.interface):
        raise RuntimeError("compiled create interface differs from validated draft")

    context = build_local_worker_turn_context(
        scaffold,
        phase_one.final_graph,
        phase_one.records,
        phase_one.supply_records,
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
    request = render_local_worker_turn_request_payload(context)
    adapter_record = run_local_worker_adapter(request, worker_transport)
    if adapter_record.status != "response_loaded" or adapter_record.response is None:
        raise RuntimeError("Task 1 vertical requires a loaded worker response")

    loaded_response = adapter_record.response

    def one_shot_worker(supplied_context: LocalWorkerTurnContext):
        if supplied_context is not context:
            raise RuntimeError("worker harness supplied a different context")
        return loaded_response

    worker_record = run_local_worker_turn(context, one_shot_worker)
    disposition = worker_record.disposition
    if (
        worker_record.status != "completed"
        or disposition is None
        or disposition.disposition != "candidate_action_request"
    ):
        raise RuntimeError("Task 1 vertical requires a candidate worker action")
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
        raise RuntimeError(
            f"Task 1 vertical action application failed: {action_apply_result.reason}"
        )

    phase_two = await run_current_step_stream(
        action_apply_result.graph,
        scaffold.provider,
        max_steps=scaffold.max_steps,
        runner=runner,
    )
    _require_phase_two_terminal(phase_two)
    step_records = phase_one.records + phase_two.records
    supply_records = phase_one.supply_records + phase_two.supply_records
    return MinimalCSharpRepairHandoffResult(
        draft=draft,
        scaffold=scaffold,
        final_graph=phase_two.final_graph,
        supply_records=supply_records,
        step_records=step_records,
        worker_request=request,
        worker_context=context,
        adapter_record=adapter_record,
        worker_record=worker_record,
        action_apply_result=action_apply_result,
        terminal_stage="terminal",
        terminal_reason=phase_two.supply_records[-1].reason,
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


def _require_phase_one_frontier(result: Any) -> None:
    if result.stop_reason != "max_steps_reached":
        raise RuntimeError(f"create phase stopped unexpectedly: {result.stop_reason}")
    if tuple(record.accepted_node_id for record in result.records) != (
        _CREATE_NODE_ID,
        _VERIFY_CREATE_NODE_ID,
    ):
        raise RuntimeError("create phase records differ from the repair frontier")
    repair = result.final_graph.nodes[_REPAIR_NODE_ID]
    if repair.status != "ready" or EXECUTION_PARAMS_KEY in repair.metadata:
        raise RuntimeError("create phase did not reach an unstaged repair frontier")


def _require_phase_two_terminal(result: Any) -> None:
    if result.stop_reason != "provider_halt":
        raise RuntimeError(f"repair phase stopped unexpectedly: {result.stop_reason}")
    if tuple(record.accepted_node_id for record in result.records) != (
        _REPAIR_NODE_ID,
        _VERIFY_REPAIR_NODE_ID,
    ):
        raise RuntimeError("repair phase records differ from the clean terminal path")
    terminal = result.supply_records[-1]
    if terminal.decision != "HALT" or terminal.reason != "terminal_node_selected:done":
        raise RuntimeError("repair phase did not halt on terminal done")


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


def _require_planner_output(value: object) -> PlannerDraftOutput:
    if type(value) is not PlannerDraftOutput:
        raise TypeError("Planner draft output must be the exact validated type")
    if value.name != "A":
        raise ValueError("Planner draft output name must be 'A'")
    if value.type != "double":
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
    if not isinstance(value.goal, str) or not value.goal.strip():
        raise ValueError("Planner draft goal must be a non-empty string")
    if value.capability != _CAPABILITY:
        raise ValueError(f"Planner draft capability must be {_CAPABILITY!r}")
    _require_planner_interface(value.interface)
    if value.acceptance != _ACCEPTANCE:
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
