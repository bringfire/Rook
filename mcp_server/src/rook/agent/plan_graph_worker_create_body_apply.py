"""Apply one Worker-authored initial body to an exact compiled scaffold."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_workflow_contract import CompiledWorkflowScaffold
from rook.learning.plan_graph import PlanGraph


_TEMPLATE_ID = "gh_csharp_create_verify"
_CREATE_NODE_ID = "create_script"
_CREATE_EXECUTION_REF = "gh_create_csharp_script:v1"
_ACTION_ID = "draft_create_body"
_ORIGINAL_PARAM_KEYS = frozenset({"pins_in", "pins_out", "name", "x", "y"})
_ACTION_INPUT_KEYS = frozenset({"code"})


@dataclass(frozen=True)
class WorkerCreateBodyApplyResult:
    graph: PlanGraph
    applied: bool
    node_id: str
    reason: str | None
    params_sha256: str | None


def _reject(
    scaffold: CompiledWorkflowScaffold,
    node_id: Any,
    reason: str,
) -> WorkerCreateBodyApplyResult:
    return WorkerCreateBodyApplyResult(
        graph=scaffold.graph,
        applied=False,
        node_id=node_id,
        reason=reason,
        params_sha256=None,
    )


def _params_sha256(params: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        params,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_worker_create_body_to_scaffold(
    scaffold: CompiledWorkflowScaffold,
    node_id: str,
    *,
    action_id: str,
    action_input: Mapping[str, Any],
) -> WorkerCreateBodyApplyResult:
    if type(scaffold) is not CompiledWorkflowScaffold:
        raise TypeError("scaffold must be exact CompiledWorkflowScaffold")

    compile_record = scaffold.compile_record
    if (
        type(compile_record.expected_template_id) is not str
        or compile_record.expected_template_id != _TEMPLATE_ID
        or type(compile_record.selected_template_id) is not str
        or compile_record.selected_template_id != _TEMPLATE_ID
    ):
        return _reject(scaffold, node_id, "invalid_template")

    if type(node_id) is not str or node_id not in scaffold.graph.nodes:
        return _reject(scaffold, node_id, "unknown_node")

    node = scaffold.graph.nodes[node_id]
    if (
        node_id != _CREATE_NODE_ID
        or type(node.execution_ref) is not str
        or node.execution_ref != _CREATE_EXECUTION_REF
    ):
        return _reject(scaffold, node_id, "invalid_tool_ref")

    if type(action_id) is not str or action_id != _ACTION_ID:
        return _reject(scaffold, node_id, "invalid_action_id")

    if not isinstance(action_input, Mapping):
        return _reject(scaffold, node_id, "invalid_action_input")
    action_input_keys = tuple(action_input.keys())
    if (
        any(type(key) is not str for key in action_input_keys)
        or frozenset(action_input_keys) - _ACTION_INPUT_KEYS
    ):
        return _reject(scaffold, node_id, "unexpected_action_input_key")
    if "code" not in action_input:
        return _reject(scaffold, node_id, "missing_code")
    code = action_input["code"]
    if type(code) is not str or not code.strip():
        return _reject(scaffold, node_id, "invalid_code")

    original_params = node.metadata.get(EXECUTION_PARAMS_KEY)
    if not isinstance(original_params, Mapping):
        return _reject(scaffold, node_id, "invalid_execution_params")
    original_param_keys = tuple(original_params.keys())
    if any(type(key) is str and key == "code" for key in original_param_keys):
        return _reject(scaffold, node_id, "code_already_present")
    if (
        any(type(key) is not str for key in original_param_keys)
        or frozenset(original_param_keys) != _ORIGINAL_PARAM_KEYS
    ):
        return _reject(scaffold, node_id, "execution_params_shape_mismatch")

    try:
        new_graph = deepcopy(scaffold.graph)
    except Exception:
        return _reject(scaffold, node_id, "graph_copy_failed")

    completed_params = dict(original_params)
    completed_params["code"] = code
    new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = completed_params
    return WorkerCreateBodyApplyResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        reason=None,
        params_sha256=_params_sha256(completed_params),
    )
