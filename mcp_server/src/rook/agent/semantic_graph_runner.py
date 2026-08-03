from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from rook.agent.semantic_graph import (
    build_semantic_graph_response_schema,
    load_semantic_graph,
    semantic_primitive_prompt_projection,
)
from rook.agent.semantic_graph_compiler import (
    CanonicalSemanticGraph,
    EpochFreeEditPlan,
    compile_semantic_graph,
)
from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphEdge,
    PlanGraphNode,
    initialize_graph,
)


MAX_SEMANTIC_GRAPH_INTENT_UTF8_BYTES = 16_384

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
                    metadata={"execution_params": copy.deepcopy(edit_request)},
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
    raise NotImplementedError


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
