from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass

from rook.agent.local_worker_adapter import LocalWorkerTransport
from rook.agent.minimal_csharp_initial_body_handoff import (
    MinimalCSharpInitialBodyHandoffResult,
    run_minimal_csharp_initial_body_handoff,
)
from rook.agent.minimal_csharp_repair_handoff import load_minimal_csharp_repair_draft
from rook.agent.semantic_graph import SemanticGraphLoadResult, load_semantic_graph
from rook.agent.semantic_graph_compiler import (
    SemanticGraphWorkerLeafPartitionCompileResult,
    compile_semantic_graph_worker_leaf_partition,
)
from rook.agent.semantic_graph_runner import (
    SemanticGraphExecutionResult,
    SemanticGraphPlannerAdapter,
    SemanticGraphPlannerRecord,
    _execute_compiled_plan,
    _invoke_tool,
    _require_exact_intent,
)
from rook.bridge import get_rhino_request_context


@dataclass(frozen=True, slots=True)
class SemanticGraphSingleWorkerLeafResult:
    intent: str
    planner_record: SemanticGraphPlannerRecord
    graph_load_result: SemanticGraphLoadResult | None = None
    partition_compile_result: SemanticGraphWorkerLeafPartitionCompileResult | None = None
    worker_handoff_result: MinimalCSharpInitialBodyHandoffResult | None = None
    deterministic_execution_result: SemanticGraphExecutionResult | None = None
    connect_request: dict[str, object] | None = None
    connect_response: object | None = None
    completed: bool = False

    def __post_init__(self) -> None:
        _validate_result(self)


async def run_semantic_graph_single_worker_leaf_transaction(
    intent: str,
    *,
    planner_adapter: SemanticGraphPlannerAdapter,
    worker_transport: LocalWorkerTransport,
    tool_executor: Callable[[str, dict[str, object]], object],
) -> SemanticGraphSingleWorkerLeafResult:
    _require_exact_intent(intent)
    if type(planner_adapter) is not SemanticGraphPlannerAdapter:
        raise TypeError("planner_adapter must be the exact SemanticGraphPlannerAdapter")
    if not callable(getattr(worker_transport, "send", None)):
        raise TypeError("worker_transport must provide callable send")
    if not callable(tool_executor):
        raise TypeError("tool_executor must be callable")

    planner = planner_adapter.produce_worker_leaf(intent)
    if planner.status == "transport_failed":
        return _result(intent, planner)
    loaded = load_semantic_graph(planner.raw_response)  # type: ignore[arg-type]
    if not loaded.admitted:
        return _result(intent, planner, loaded=loaded)
    if loaded.graph is None:
        raise RuntimeError("admitted semantic graph is missing")

    compiled = compile_semantic_graph_worker_leaf_partition(loaded.graph)
    if not compiled.admitted:
        return _result(intent, planner, loaded=loaded, compiled=compiled)
    partition = compiled.partition
    if partition is None:
        raise RuntimeError("admitted partition is missing")
    if partition.unresolved_leaf is None or partition.cross_edge is None:
        return _result(intent, planner, loaded=loaded, compiled=compiled)

    leaf = partition.unresolved_leaf
    output = leaf.interface.outputs[0]
    draft = load_minimal_csharp_repair_draft({
        "goal": leaf.goal,
        "capability": "grasshopper_csharp_component",
        "interface": {
            "inputs": [],
            "outputs": [{"name": output.name, "type": output.type}],
        },
        "acceptance": "clean_compile_receipt",
    })
    frozen_context = copy.deepcopy(get_rhino_request_context())

    async def guarded_executor(name: str, params: dict[str, object]) -> object:
        _require_context(frozen_context)
        try:
            response = await _invoke_tool(tool_executor, name, params)
        except Exception:
            _require_context(frozen_context)
            raise
        _require_context(frozen_context)
        return response

    try:
        handoff = await run_minimal_csharp_initial_body_handoff(
            draft,
            worker_transport=worker_transport,
            tool_executor=guarded_executor,
        )
    except Exception:
        _require_context(frozen_context)
        raise
    _require_context(frozen_context)
    prefix = {"loaded": loaded, "compiled": compiled, "handoff": handoff}
    if not _clean_terminal(handoff):
        return _result(intent, planner, **prefix)

    source_guid = _source_guid(handoff)
    try:
        deterministic = await _execute_compiled_plan(
            intent,
            planner,
            partition.deterministic_plan,
            tool_executor,
        )
    except Exception:
        _require_context(frozen_context)
        raise
    _require_context(frozen_context)
    if not _clean_terminal(deterministic):
        return _result(intent, planner, **prefix, deterministic=deterministic)

    target_guid = _target_guid(deterministic, partition.cross_edge.target_node_id)
    request = {
        "sourceGuid": source_guid,
        "sourceIndex": partition.cross_edge.source_output_index,
        "targetGuid": target_guid,
        "targetIndex": partition.cross_edge.target_input_index,
    }
    _require_context(frozen_context)
    try:
        response = await _invoke_tool(tool_executor, "gh_connect", request)
    except Exception:
        _require_context(frozen_context)
        return _result(
            intent, planner, **prefix, deterministic=deterministic, request=request
        )
    _require_context(frozen_context)
    return _result(
        intent, planner, **prefix, deterministic=deterministic, request=request,
        response=response, completed=_connect_matches(response, request),
    )


def _result(
    intent: str, planner: SemanticGraphPlannerRecord, *,
    loaded: SemanticGraphLoadResult | None = None,
    compiled: SemanticGraphWorkerLeafPartitionCompileResult | None = None,
    handoff: MinimalCSharpInitialBodyHandoffResult | None = None,
    deterministic: SemanticGraphExecutionResult | None = None,
    request: dict[str, object] | None = None, response: object | None = None,
    completed: bool = False,
) -> SemanticGraphSingleWorkerLeafResult:
    return SemanticGraphSingleWorkerLeafResult(
        intent=intent,
        planner_record=planner,
        graph_load_result=loaded,
        partition_compile_result=compiled,
        worker_handoff_result=handoff,
        deterministic_execution_result=deterministic,
        connect_request=request,
        connect_response=response,
        completed=completed,
    )


def _clean_terminal(result: MinimalCSharpInitialBodyHandoffResult | SemanticGraphExecutionResult) -> bool:
    return (
        result.terminal_stage == "terminal"
        and result.terminal_reason == "terminal_node_selected:done"
    )


def _source_guid(result: MinimalCSharpInitialBodyHandoffResult) -> str:
    evidence = result.final_graph.nodes["create_script"].evidence
    receipt = None if evidence is None else evidence.receipt
    mutation = None if type(receipt) is not dict else receipt.get("mutation")
    guid = None if type(mutation) is not dict else mutation.get("component_guid")
    if type(guid) is not str or not guid.strip():
        raise RuntimeError("clean Worker handoff lacks a component GUID")
    return guid


def _target_guid(result: SemanticGraphExecutionResult, node_id: str) -> str:
    matches = () if result.structural_correlation is None else tuple(
        row[2] for row in result.structural_correlation if row[0] == node_id
    )
    if len(matches) != 1 or type(matches[0]) is not str or not matches[0].strip():
        raise RuntimeError("deterministic target identity is missing or ambiguous")
    return matches[0]


def _require_context(frozen: object) -> None:
    if get_rhino_request_context() != frozen:
        raise RuntimeError("Rhino context changed during Worker leaf transaction")


def _connect_matches(response: object, request: dict[str, object]) -> bool:
    if type(response) is not dict or response.get("success") is not True:
        return False
    data = response.get("data")
    if type(data) is not dict or data.get("connected") is not True:
        return False
    source, target = data.get("source"), data.get("target")
    return (
        type(source) is dict
        and type(target) is dict
        and type(source.get("guid")) is str
        and type(source.get("index")) is int
        and type(target.get("guid")) is str
        and type(target.get("index")) is int
        and source["guid"] == request["sourceGuid"]
        and source["index"] == request["sourceIndex"]
        and target["guid"] == request["targetGuid"]
        and target["index"] == request["targetIndex"]
    )


def _validate_result(result: SemanticGraphSingleWorkerLeafResult) -> None:
    _require_exact_intent(result.intent)
    if type(result.planner_record) is not SemanticGraphPlannerRecord:
        raise TypeError("planner_record must be exact")
    typed = (
        (result.graph_load_result, SemanticGraphLoadResult),
        (result.partition_compile_result, SemanticGraphWorkerLeafPartitionCompileResult),
        (result.worker_handoff_result, MinimalCSharpInitialBodyHandoffResult),
        (result.deterministic_execution_result, SemanticGraphExecutionResult),
    )
    if any(value is not None and type(value) is not kind for value, kind in typed):
        raise TypeError("result contains an invalid optional field")
    loaded = result.graph_load_result
    compiled = result.partition_compile_result
    handoff = result.worker_handoff_result
    deterministic = result.deterministic_execution_result
    if loaded is not None and result.planner_record.status != "response_received":
        raise ValueError("graph load requires a Planner response")
    if compiled is not None and (loaded is None or not loaded.admitted):
        raise ValueError("partition compilation requires an admitted graph")
    if handoff is not None and (
        compiled is None
        or not compiled.admitted
        or compiled.partition is None
        or compiled.partition.unresolved_leaf is None
        or compiled.partition.cross_edge is None
    ):
        raise ValueError("Worker handoff requires an admitted leaf partition")
    if deterministic is not None and (
        handoff is None or not _clean_terminal(handoff)
    ):
        raise ValueError("deterministic execution requires a clean Worker terminal")
    if result.connect_request is not None and type(result.connect_request) is not dict:
        raise TypeError("connect_request must be an exact dict")
    if result.connect_request is not None and (
        deterministic is None or not _clean_terminal(deterministic)
    ):
        raise ValueError("connect request requires clean deterministic terminal")
    if result.connect_response is not None and result.connect_request is None:
        raise ValueError("connect response requires its request")
    direct = (
        result.worker_handoff_result is not None
        and _clean_terminal(result.worker_handoff_result)
        and result.deterministic_execution_result is not None
        and _clean_terminal(result.deterministic_execution_result)
        and result.connect_request is not None
        and _connect_matches(result.connect_response, result.connect_request)
    )
    if type(result.completed) is not bool or result.completed is not direct:
        raise ValueError("completed differs from direct terminal equation")
