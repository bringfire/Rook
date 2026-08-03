from __future__ import annotations

import copy
import inspect
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from rook.agent.plan_graph_current_step_provider import (
    CatalogCurrentStepProvider,
    NodeStepRule,
)
from rook.agent.plan_graph_current_step_runner import (
    CurrentStepRecord,
    project_current_step_record,
)
from rook.agent.plan_graph_current_step_stream import (
    EnvelopeSupplyRecord,
    EnvelopeSupplyResult,
    run_current_step_stream,
)
from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY, LiveProducerResult
from rook.agent.plan_graph_sequence_runner import ProducerStep, VerifierStep
from rook.agent.plan_graph_step_executor import StepExecutionResult
from rook.agent.semantic_graph import (
    build_semantic_graph_response_schema,
    load_semantic_graph,
    semantic_primitive_prompt_projection,
)
from rook.agent.semantic_graph_compiler import (
    CanonicalSemanticGraph,
    EpochFreeEditPlan,
    compile_semantic_graph,
    materialize_gh_edit_request,
)
from rook.bridge import get_rhino_request_context
from rook.gh_edit_contract import extract_edit_errors
from rook.learning.plan_graph import (
    NodeOutcome,
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    apply_outcome,
    initialize_graph,
)
from rook.learning.plan_graph_outcomes import node_evidence_from_tool_result
from rook.learning.plan_graph_runner import VerifierStepResult


MAX_SEMANTIC_GRAPH_INTENT_UTF8_BYTES = 16_384
_SNAPSHOT_REQUEST: dict[str, object] = {
    "include_data": False,
    "max_preview_items": 0,
}
_FLOW_RE = re.compile(
    r"(?P<source>[^.\s>]+)\.O(?P<output>[0-9]+)>"
    r"(?P<target>[^.\s>]+)\.I(?P<input>[0-9]+)\Z"
)

PlannerStatus = Literal["response_received", "transport_failed"]
TerminalStage = Literal[
    "planner",
    "graph_admission",
    "snapshot",
    "edit",
    "verification",
    "terminal",
]


class SemanticGraphPlannerTransport(Protocol):
    def send(self, prompt_artifact: dict[str, object]) -> str: ...


@dataclass(frozen=True, slots=True)
class SemanticGraphPromptSnapshot:
    system_content: str
    user_content: str

    def materialize(self) -> dict[str, object]:
        return {
            "messages": [
                {"role": "system", "content": self.system_content},
                {"role": "user", "content": self.user_content},
            ]
        }


@dataclass(frozen=True, slots=True)
class SemanticGraphPlannerRecord:
    prompt_snapshot: SemanticGraphPromptSnapshot
    status: PlannerStatus
    raw_response: object | None
    failure_reason: str | None
    transport_error_type: str | None

    def __post_init__(self) -> None:
        if type(self.prompt_snapshot) is not SemanticGraphPromptSnapshot:
            raise TypeError("prompt_snapshot must be SemanticGraphPromptSnapshot")
        if self.status == "response_received":
            if self.failure_reason is not None or self.transport_error_type is not None:
                raise ValueError("response_received record cannot contain failure fields")
            return
        if self.status == "transport_failed":
            if self.raw_response is not None:
                raise ValueError("transport_failed record cannot contain a response")
            if self.failure_reason != "transport_failed":
                raise ValueError("transport_failed record must retain its native reason")
            if type(self.transport_error_type) is not str or not self.transport_error_type:
                raise ValueError("transport_failed record requires an exception type")
            return
        raise ValueError(f"unknown Planner status: {self.status}")


class SemanticGraphPlannerAdapter:
    __slots__ = ("_transport",)

    def __init__(self, transport: SemanticGraphPlannerTransport) -> None:
        if not callable(getattr(transport, "send", None)):
            raise TypeError("transport must provide send()")
        self._transport = transport

    def produce(self, intent: str) -> SemanticGraphPlannerRecord:
        _require_exact_intent(intent)
        prompt_snapshot = _render_prompt_snapshot(intent)
        try:
            raw_response = self._transport.send(prompt_snapshot.materialize())
        except Exception as exc:
            return SemanticGraphPlannerRecord(
                prompt_snapshot=prompt_snapshot,
                status="transport_failed",
                raw_response=None,
                failure_reason="transport_failed",
                transport_error_type=type(exc).__name__,
            )
        return SemanticGraphPlannerRecord(
            prompt_snapshot=prompt_snapshot,
            status="response_received",
            raw_response=raw_response,
            failure_reason=None,
            transport_error_type=None,
        )


@dataclass(frozen=True, slots=True)
class SemanticGraphExecutionResult:
    intent: str
    planner_record: SemanticGraphPlannerRecord
    terminal_stage: TerminalStage
    terminal_reason: str
    canonical_graph: CanonicalSemanticGraph | None = None
    edit_plan: EpochFreeEditPlan | None = None
    snapshot_request: dict[str, object] | None = None
    snapshot_response: object | None = None
    execution_graph: PlanGraph | None = None
    step_records: tuple[object, ...] = ()
    supply_records: tuple[object, ...] = ()
    edit_request: dict[str, object] | None = None
    edit_response: object | None = None
    structural_correlation: tuple[tuple[str, str, str], ...] | None = None
    final_graph: PlanGraph | None = None

    def __post_init__(self) -> None:
        _require_exact_intent(self.intent)
        if type(self.planner_record) is not SemanticGraphPlannerRecord:
            raise TypeError("planner_record must be SemanticGraphPlannerRecord")
        if self.terminal_stage not in (
            "planner",
            "graph_admission",
            "snapshot",
            "edit",
            "verification",
            "terminal",
        ):
            raise ValueError("unknown terminal_stage")
        if type(self.terminal_reason) is not str or not self.terminal_reason:
            raise ValueError("terminal_reason must be a nonempty string")
        if type(self.step_records) is not tuple or type(self.supply_records) is not tuple:
            raise TypeError("native record collections must be exact tuples")

        if self.terminal_stage == "planner":
            if self.planner_record.status != "transport_failed":
                raise ValueError("planner stop requires transport_failed record")
            if self.terminal_reason != self.planner_record.failure_reason:
                raise ValueError("planner reason must match adapter reason")
            _require_no_execution_fields(self)
            return

        if self.planner_record.status != "response_received":
            raise ValueError("post-Planner stage requires a response")
        if self.terminal_stage == "graph_admission":
            _require_no_execution_fields(self)
            return
        if self.canonical_graph is None or self.edit_plan is None:
            raise ValueError("execution stages require admitted graph and edit plan")
        if self.terminal_stage == "snapshot":
            if self.snapshot_request is None:
                raise ValueError("snapshot stage requires its request")
            if any(
                value is not None
                for value in (
                    self.execution_graph,
                    self.edit_request,
                    self.edit_response,
                    self.structural_correlation,
                    self.final_graph,
                )
            ) or self.step_records or self.supply_records:
                raise ValueError("snapshot stage cannot retain later-stage fields")
            return
        if (
            self.snapshot_request is None
            or self.snapshot_response is None
            or self.execution_graph is None
            or self.edit_request is None
            or self.final_graph is None
            or not self.step_records
            or not self.supply_records
        ):
            raise ValueError("post-snapshot stage lacks its immediate native fields")
        if self.terminal_stage == "edit":
            if self.structural_correlation is not None:
                raise ValueError("edit stop cannot claim structural correlation")
            return
        if self.edit_response is None:
            raise ValueError("verification stages require a returned edit response")
        if self.terminal_stage == "verification":
            if self.structural_correlation is not None:
                raise ValueError("verification stop cannot claim structural correlation")
            return
        if self.structural_correlation is None:
            raise ValueError("terminal stage requires structural correlation")
        if self.terminal_reason != "terminal_node_selected:done":
            raise ValueError("terminal stage requires the native done selection")


async def run_semantic_graph_transaction(
    intent: str,
    *,
    planner_adapter: SemanticGraphPlannerAdapter,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> SemanticGraphExecutionResult:
    _require_exact_intent(intent)
    if type(planner_adapter) is not SemanticGraphPlannerAdapter:
        raise TypeError("planner_adapter must be exact SemanticGraphPlannerAdapter")
    if not callable(tool_executor):
        raise TypeError("tool_executor must be callable")

    planner_record = planner_adapter.produce(intent)
    if planner_record.status == "transport_failed":
        return SemanticGraphExecutionResult(
            intent=intent,
            planner_record=planner_record,
            terminal_stage="planner",
            terminal_reason=planner_record.failure_reason or "transport_failed",
        )

    loaded = load_semantic_graph(planner_record.raw_response)  # type: ignore[arg-type]
    if not loaded.admitted:
        return SemanticGraphExecutionResult(
            intent=intent,
            planner_record=planner_record,
            terminal_stage="graph_admission",
            terminal_reason=loaded.reason,
        )
    if loaded.graph is None:
        raise RuntimeError("admitted semantic graph is missing")

    compiled = compile_semantic_graph(loaded.graph)
    if not compiled.admitted:
        return SemanticGraphExecutionResult(
            intent=intent,
            planner_record=planner_record,
            terminal_stage="graph_admission",
            terminal_reason=compiled.reason,
        )
    if compiled.plan is None:
        raise RuntimeError("admitted semantic graph plan is missing")
    return await _execute_compiled_plan(
        intent,
        planner_record,
        compiled.plan,
        tool_executor,
    )


def _build_execution_graph(edit_request: dict[str, object]) -> PlanGraph:
    if type(edit_request) is not dict:
        raise TypeError("edit_request must be an exact dict")
    return initialize_graph(
        PlanGraph(
            nodes={
                "create_edit": PlanGraphNode(
                    id="create_edit",
                    intent="Apply the admitted Grasshopper semantic graph",
                    execution_ref="gh_edit:v1",
                    metadata={
                        "outcome_projection_role": "artifact_producer",
                        "execution_params": copy.deepcopy(edit_request),
                    },
                ),
                "verify_edit": PlanGraphNode(
                    id="verify_edit",
                    intent="Verify exact structural materialization",
                ),
                "done": PlanGraphNode(
                    id="done",
                    intent="Complete admitted Grasshopper edit",
                    is_terminal=True,
                ),
            },
            edges=[
                PlanGraphEdge("create_edit", "verify_edit", "requires"),
                PlanGraphEdge("verify_edit", "done", "requires"),
            ],
        )
    )


async def _execute_compiled_plan(
    intent: str,
    planner_record: SemanticGraphPlannerRecord,
    plan: EpochFreeEditPlan,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> SemanticGraphExecutionResult:
    frozen_context = copy.deepcopy(get_rhino_request_context())
    snapshot_request = copy.deepcopy(_SNAPSHOT_REQUEST)
    try:
        snapshot_response = await _invoke_tool(
            tool_executor,
            "gh_snapshot",
            snapshot_request,
        )
    except Exception:
        return SemanticGraphExecutionResult(
            intent=intent,
            planner_record=planner_record,
            terminal_stage="snapshot",
            terminal_reason="snapshot_dispatch_failed",
            canonical_graph=plan.canonical_graph,
            edit_plan=plan,
            snapshot_request=snapshot_request,
        )

    epoch = _admit_snapshot_epoch(snapshot_response)
    if epoch is None:
        return SemanticGraphExecutionResult(
            intent=intent,
            planner_record=planner_record,
            terminal_stage="snapshot",
            terminal_reason="snapshot_response_invalid",
            canonical_graph=plan.canonical_graph,
            edit_plan=plan,
            snapshot_request=snapshot_request,
            snapshot_response=snapshot_response,
        )
    if get_rhino_request_context() != frozen_context:
        raise RuntimeError("Rhino context changed during semantic graph transaction")

    edit_request = materialize_gh_edit_request(plan, epoch)
    execution_graph = _build_execution_graph(edit_request)
    provider = _build_step_provider()
    edit_runner = _EditStepRunner(tool_executor)
    edit_stream = await run_current_step_stream(
        execution_graph,
        provider,
        max_steps=1,
        runner=edit_runner,
    )
    if (
        len(edit_stream.records) != 1
        or len(edit_stream.supply_records) != 1
        or edit_stream.records[0].accepted_node_id != "create_edit"
    ):
        raise RuntimeError("semantic edit did not produce the exact native prefix")

    common = {
        "intent": intent,
        "planner_record": planner_record,
        "canonical_graph": plan.canonical_graph,
        "edit_plan": plan,
        "snapshot_request": snapshot_request,
        "snapshot_response": snapshot_response,
        "execution_graph": execution_graph,
        "step_records": edit_stream.records,
        "supply_records": edit_stream.supply_records,
        "edit_request": edit_request,
        "edit_response": edit_runner.response,
        "final_graph": edit_stream.final_graph,
    }
    if edit_runner.failure is not None:
        return SemanticGraphExecutionResult(
            **common,
            terminal_stage="edit",
            terminal_reason=edit_runner.failure,
        )
    if edit_runner.response is None:
        raise RuntimeError("entered edit call returned neither response nor failure")

    correlation, verification_failure = _verify_structural_materialization(
        plan,
        edit_request,
        edit_runner.response,
    )
    records = list(edit_stream.records)
    supply_records = list(edit_stream.supply_records)
    verify_supply = provider(
        edit_stream.final_graph,
        tuple(records),
        tuple(supply_records),
    )
    if verify_supply.decision != "SUPPLY" or verify_supply.envelope is None:
        raise RuntimeError("verify_edit was not supplied after a successful edit")
    supply_records.append(_retain_supply_record(verify_supply))
    verify_status = "succeeded" if verification_failure is None else "failed"
    verified_graph = apply_outcome(
        edit_stream.final_graph,
        "verify_edit",
        NodeOutcome(
            status=verify_status,
            message=(
                "exact structural materialization verified"
                if verification_failure is None
                else verification_failure
            ),
        ),
    )
    verifier_result = VerifierStepResult(
        graph=verified_graph,
        applied=True,
        verifier_node_id="verify_edit",
        source_node_id="create_edit",
        outcome_status=verify_status,
        reason=None,
    )
    verify_execution = StepExecutionResult(
        ran=True,
        kind="verifier",
        graph=verified_graph,
        failure=None,
        reason="executed deterministic structural verifier",
        mapping=verify_supply.envelope.mapping,
        verifier_result=verifier_result,
    )
    records.append(
        project_current_step_record(verify_supply.envelope, verify_execution)
    )
    terminal_supply = provider(
        verified_graph,
        tuple(records),
        tuple(supply_records),
    )
    supply_records.append(_retain_supply_record(terminal_supply))

    finished = {
        **common,
        "step_records": tuple(records),
        "supply_records": tuple(supply_records),
        "final_graph": verified_graph,
    }
    if verification_failure is not None:
        if (
            terminal_supply.decision != "HALT"
            or terminal_supply.reason != "selector_halt:none_ready"
        ):
            raise RuntimeError("failed verification did not halt with no ready node")
        return SemanticGraphExecutionResult(
            **finished,
            terminal_stage="verification",
            terminal_reason=verification_failure,
        )
    if (
        terminal_supply.decision != "HALT"
        or terminal_supply.reason != "terminal_node_selected:done"
    ):
        raise RuntimeError("verified graph did not select the terminal node")
    return SemanticGraphExecutionResult(
        **finished,
        terminal_stage="terminal",
        terminal_reason=terminal_supply.reason,
        structural_correlation=correlation,
    )


class _EditStepRunner:
    def __init__(
        self,
        tool_executor: Callable[[str, dict[str, object]], object],
    ) -> None:
        self._tool_executor = tool_executor
        self._entered = False
        self.response: object | None = None
        self.failure: str | None = None

    async def run_live_producer_node(
        self,
        graph: PlanGraph,
        node_id: str,
    ) -> LiveProducerResult:
        if self._entered:
            raise RuntimeError("semantic edit runner entered more than once")
        self._entered = True
        if node_id != "create_edit":
            raise RuntimeError("semantic edit runner received an unexpected node")
        node = graph.nodes.get(node_id)
        if (
            node is None
            or node.status != "ready"
            or node.execution_ref != "gh_edit:v1"
        ):
            raise RuntimeError("semantic edit node contradicts the fixed graph")
        params = node.metadata.get(EXECUTION_PARAMS_KEY)
        if type(params) is not dict:
            raise RuntimeError("semantic edit node lacks exact execution parameters")
        try:
            self.response = await _invoke_tool(
                self._tool_executor,
                "gh_edit",
                params,
            )
        except Exception:
            self.failure = "dispatch_failed"
            return LiveProducerResult(
                graph=graph,
                applied=False,
                node_id=node_id,
                tool_name="gh_edit",
                outcome_status=None,
                reason="dispatch_failed",
            )

        self.failure = _edit_contract_failure(self.response)
        status = "failed" if self.failure is not None else "succeeded"
        outcome = NodeOutcome(
            status=status,
            evidence=node_evidence_from_tool_result(self.response),
            message=("gh_edit contract accepted" if self.failure is None else self.failure),
            error=self.failure,
        )
        next_graph = apply_outcome(graph, node_id, outcome)
        return LiveProducerResult(
            graph=next_graph,
            applied=True,
            node_id=node_id,
            tool_name="gh_edit",
            outcome_status=status,
            reason=None,
        )


async def _invoke_tool(
    tool_executor: Callable[[str, dict[str, object]], object],
    tool_name: str,
    params: dict[str, object],
) -> object:
    result = tool_executor(tool_name, copy.deepcopy(params))
    if inspect.isawaitable(result):
        result = await result
    return result


def _admit_snapshot_epoch(response: object) -> int | None:
    if type(response) is not dict or response.get("success") is not True:
        return None
    data = response.get("data")
    if type(data) is not dict:
        return None
    epoch = data.get("epoch")
    return epoch if type(epoch) is int and epoch > 0 else None


def _edit_contract_failure(response: object) -> str | None:
    if type(response) is not dict:
        return "edit_response_invalid"
    data = response.get("data")
    if response.get("success") is not True:
        return "edit_failed"
    if response.get("partial_success") is True or (
        type(data) is dict and data.get("partial_success") is True
    ):
        return "edit_partial_success"
    if extract_edit_errors(response):
        return "edit_errors"
    return None


def _build_step_provider() -> CatalogCurrentStepProvider:
    return CatalogCurrentStepProvider(
        rules=(
            NodeStepRule("create_edit", (ProducerStep("create_edit"),)),
            NodeStepRule(
                "verify_edit",
                (
                    VerifierStep(
                        "verify_edit",
                        "create_edit",
                        expected_outcome="succeeded",
                    ),
                ),
            ),
        ),
        terminal_node_ids=frozenset(("done",)),
    )


def _retain_supply_record(supplied: EnvelopeSupplyResult) -> EnvelopeSupplyRecord:
    metadata = None
    metadata_status: Literal["absent", "copied"] = "absent"
    if supplied.metadata is not None:
        metadata = copy.deepcopy(dict(supplied.metadata))
        metadata_status = "copied"
    return EnvelopeSupplyRecord(
        decision=supplied.decision,
        envelope=supplied.envelope,
        reason=supplied.reason,
        metadata=metadata,
        metadata_status=metadata_status,
    )


def _verify_structural_materialization(
    plan: EpochFreeEditPlan,
    edit_request: dict[str, object],
    response: object,
) -> tuple[tuple[tuple[str, str, str], ...] | None, str | None]:
    if type(response) is not dict:
        return None, "edit_response_not_mapping"
    data = response.get("data")
    if type(data) is not dict:
        return None, "edit_snapshot_missing"
    summary = data.get("edit_summary")
    if type(summary) is not dict:
        return None, "edit_summary_missing"
    expected_temp_ids = {temp_id for _, temp_id in plan.semantic_node_to_temp_id}
    temp_id_map = summary.get("temp_id_map")
    instance_guids = summary.get("instance_guids")
    if type(temp_id_map) is not dict or set(temp_id_map) != expected_temp_ids:
        return None, "temp_id_map_keys_disagree"
    if type(instance_guids) is not dict or set(instance_guids) != expected_temp_ids:
        return None, "instance_guid_keys_disagree"

    c_ids = tuple(temp_id_map[temp_id] for temp_id in sorted(expected_temp_ids))
    physical_guids = tuple(
        instance_guids[temp_id] for temp_id in sorted(expected_temp_ids)
    )
    if any(type(value) is not str or not value.strip() for value in c_ids):
        return None, "mapped_component_id_invalid"
    if any(
        type(value) is not str or not value.strip() for value in physical_guids
    ):
        return None, "instance_guid_invalid"
    if len(set(c_ids)) != len(c_ids):
        return None, "mapped_component_ids_not_unique"
    if len(set(physical_guids)) != len(physical_guids):
        return None, "instance_guids_not_unique"

    create = edit_request.get("create")
    components = data.get("components")
    if type(create) is not list or type(components) is not list:
        return None, "returned_components_missing"
    create_by_temp: dict[str, dict[str, object]] = {}
    for entry in create:
        if type(entry) is not dict or type(entry.get("temp_id")) is not str:
            raise RuntimeError("materialized create instruction is malformed")
        create_by_temp[entry["temp_id"]] = entry

    correlation: list[tuple[str, str, str]] = []
    for semantic_id, temp_id in plan.semantic_node_to_temp_id:
        component_id = temp_id_map[temp_id]
        matches = [
            component
            for component in components
            if type(component) is dict and component.get("id") == component_id
        ]
        if len(matches) != 1:
            return None, "mapped_component_missing_or_ambiguous"
        component = matches[0]
        instruction = create_by_temp.get(temp_id)
        if instruction is None:
            raise RuntimeError("semantic correlation lacks a create instruction")
        if "guid" in instruction:
            if component.get("componentGuid") != instruction["guid"]:
                return None, "component_identity_disagrees"
        elif instruction.get("type") == "slider":
            if component.get("type") != "NumberSlider":
                return None, "slider_identity_disagrees"
        else:
            raise RuntimeError("unknown materialized create representation")
        correlation.append(
            (semantic_id, component_id, instance_guids[temp_id])
        )

    if type(summary.get("created")) is not int or summary["created"] != len(create):
        return None, "created_count_disagrees"
    connect = edit_request.get("connect")
    if type(connect) is not list:
        raise RuntimeError("materialized connect instructions are malformed")
    if (
        type(summary.get("connected")) is not int
        or summary["connected"] != len(connect)
    ):
        return None, "connected_count_disagrees"

    expected_wires: set[str] = set()
    for flow in connect:
        if type(flow) is not str:
            raise RuntimeError("materialized flow is not a string")
        match = _FLOW_RE.fullmatch(flow)
        if match is None:
            raise RuntimeError("materialized flow contradicts compiler syntax")
        expected_wires.add(
            f"{temp_id_map[match.group('source')]}.O{match.group('output')}>"
            f"{temp_id_map[match.group('target')]}.I{match.group('input')}"
        )
    returned_flows = data.get("flows")
    if type(returned_flows) is not list:
        return None, "returned_flows_missing"
    new_components = set(c_ids)
    actual_incident: set[str] = set()
    for flow in returned_flows:
        if type(flow) is not str:
            return None, "returned_flow_invalid"
        match = _FLOW_RE.fullmatch(flow)
        if match is None:
            return None, "incident_flow_malformed"
        if (
            match.group("source") in new_components
            or match.group("target") in new_components
        ):
            actual_incident.add(flow)
    if actual_incident != expected_wires:
        return None, "incident_wires_disagree"
    return tuple(correlation), None


def _require_exact_intent(intent: str) -> None:
    if type(intent) is not str:
        raise TypeError("intent must be an exact string")
    if not intent.strip():
        raise ValueError("intent must be nonblank")
    try:
        encoded = intent.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("intent must be valid UTF-8") from exc
    if len(encoded) > MAX_SEMANTIC_GRAPH_INTENT_UTF8_BYTES:
        raise ValueError("intent exceeds UTF-8 byte limit")


def _render_prompt_snapshot(intent: str) -> SemanticGraphPromptSnapshot:
    schema_json = json.dumps(
        build_semantic_graph_response_schema(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    primitives_json = json.dumps(
        semantic_primitive_prompt_projection(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    system_content = (
        "Return exactly one JSON object matching this output schema. "
        "Compose only the listed semantic primitives and their exact, "
        "case-sensitive pins and parameters. Do not add prose or markdown.\n"
        f"OUTPUT_SCHEMA={schema_json}\n"
        f"SEMANTIC_PRIMITIVES={primitives_json}"
    )
    user_content = json.dumps(
        {"user_intent": intent},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return SemanticGraphPromptSnapshot(
        system_content=system_content,
        user_content=user_content,
    )


def _require_no_execution_fields(result: SemanticGraphExecutionResult) -> None:
    if any(
        value is not None
        for value in (
            result.canonical_graph,
            result.edit_plan,
            result.snapshot_request,
            result.snapshot_response,
            result.execution_graph,
            result.edit_request,
            result.edit_response,
            result.structural_correlation,
            result.final_graph,
        )
    ):
        raise ValueError("pre-execution result cannot retain execution fields")
    if result.step_records or result.supply_records:
        raise ValueError("pre-execution result cannot retain native records")
