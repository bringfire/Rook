"""Stage worker-authored action params onto one plan-graph node."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from typing import Any

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY


_ACTION_INPUT_KEYS = {"code", "mode"}
_ANCHOR_BINDING_KEYS = {"component_guid", "language"}


@dataclass(frozen=True)
class WorkerActionApplyResult:
    graph: Any
    applied: bool
    node_id: str
    reason: str | None
    params_sha256: str | None


def _reject(graph: Any, node_id: str, reason: str) -> WorkerActionApplyResult:
    return WorkerActionApplyResult(
        graph=graph,
        applied=False,
        node_id=node_id,
        reason=reason,
        params_sha256=None,
    )


def _validate_action_input(action_input: Any) -> str | None:
    if not isinstance(action_input, Mapping):
        return "invalid_action_input"
    if set(action_input) - _ACTION_INPUT_KEYS:
        return "unexpected_action_input_key"
    if "code" not in action_input:
        return "missing_code"
    code = action_input["code"]
    if not isinstance(code, str) or not code.strip():
        return "invalid_code"
    if action_input.get("mode") != "body":
        return "invalid_mode"
    return None


def _validate_anchor_binding(anchor_binding: Any) -> str | None:
    if not isinstance(anchor_binding, Mapping):
        return "invalid_anchor_binding"
    if set(anchor_binding) - _ANCHOR_BINDING_KEYS:
        return "unexpected_anchor_binding_key"
    if "component_guid" not in anchor_binding:
        return "missing_component_guid"
    component_guid = anchor_binding["component_guid"]
    if not isinstance(component_guid, str) or not component_guid.strip():
        return "invalid_component_guid"
    if "language" not in anchor_binding:
        return "missing_language"
    language = anchor_binding["language"]
    if not isinstance(language, str) or language != "csharp":
        return "invalid_language"
    return None


def _params_sha256(params: dict[str, str]) -> str:
    encoded = json.dumps(params, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_worker_action_to_node(
    graph: Any,
    node_id: str,
    *,
    action_id: str,
    action_input: Mapping[str, Any],
    anchor_binding: Mapping[str, Any],
    allowed_action_id: str = "draft_repair_params",
) -> WorkerActionApplyResult:
    if node_id not in graph.nodes:
        return _reject(graph, node_id, "unknown_node")
    if action_id != allowed_action_id:
        return _reject(graph, node_id, "invalid_action_id")

    action_input_reason = _validate_action_input(action_input)
    if action_input_reason is not None:
        return _reject(graph, node_id, action_input_reason)

    anchor_binding_reason = _validate_anchor_binding(anchor_binding)
    if anchor_binding_reason is not None:
        return _reject(graph, node_id, anchor_binding_reason)

    params = {
        "guid": anchor_binding["component_guid"],
        "code": action_input["code"],
        "mode": "body",
        "language": "csharp",
    }

    try:
        new_graph = deepcopy(graph)
    except Exception:
        return _reject(graph, node_id, "graph_copy_failed")

    new_graph.nodes[node_id].metadata[EXECUTION_PARAMS_KEY] = params
    return WorkerActionApplyResult(
        graph=new_graph,
        applied=True,
        node_id=node_id,
        reason=None,
        params_sha256=_params_sha256(params),
    )
