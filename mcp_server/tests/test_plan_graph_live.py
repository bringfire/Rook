from __future__ import annotations

import asyncio
import ast
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphNode,
    initialize_graph,
)
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.agent.plan_graph_live import (
    EXECUTION_PARAMS_KEY,
    LiveProducerResult,
    apply_live_producer_node,
    _resolve_tool_name,
)


COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
_ABSENT = object()


# ----- shared raw-result builders (real server contract) -----

def _usable_receipt() -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": "usable",
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "repair_anchor": {"component_guid": COMPONENT_GUID},
    }


def _errors_receipt() -> dict:
    return {
        "version": 1,
        "operation": "create",
        "language": "csharp",
        "artifact_status": "created_with_errors",
        "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
        "verification": {"status": "failed", "target_error_count": 1},
        "repair_anchor": {
            "component_guid": COMPONENT_GUID,
            "pins_out": [{"name": "A", "type": "double"}],
        },
    }


def _usable_raw() -> dict:
    return {"success": True, "data": {"verified": True, "script_receipt": _usable_receipt()}}


def _error_raw() -> dict:
    # Real server contract: an errored script result is top-level success: False.
    return {"success": False, "data": {"verified": False, "script_receipt": _errors_receipt()}}


# ----- producer-node graph fixture -----

def _producer_graph(
    *,
    ready: bool = True,
    execution_ref: object = "gh_create_csharp_script:v1",
    role: object = "artifact_producer",
    with_params: bool = True,
    execution_params: object = None,
) -> PlanGraph:
    metadata: dict = {}
    if role is not _ABSENT:
        metadata[OUTCOME_PROJECTION_ROLE_KEY] = role
    if with_params:
        metadata[EXECUTION_PARAMS_KEY] = (
            execution_params
            if execution_params is not None
            else {"language": "csharp", "code": "// noop", "component_name": "C"}
        )
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component",
        execution_ref=execution_ref,
        metadata=metadata,
    )
    graph = PlanGraph(nodes={"create_script": node})
    return initialize_graph(graph) if ready else graph


# ----- fake dispatch spy -----

class _Spy:
    def __init__(self, raw: dict | None = None, raises: BaseException | None = None):
        self.calls: list[tuple[str, dict]] = []
        self._raw = raw if raw is not None else {"success": True, "data": {}}
        self._raises = raises

    async def __call__(self, name: str, params: dict) -> dict:
        self.calls.append((name, params))
        if self._raises is not None:
            raise self._raises
        return self._raw


# ===== Task 1 tests: tool-name grammar + result shape =====

@pytest.mark.parametrize(
    "execution_ref, expected_name, expected_reason",
    [
        (None, None, "execution_ref_missing"),
        ("", None, "execution_ref_missing"),
        (123, None, "execution_ref_invalid"),
        ("gh_create_csharp_script", "gh_create_csharp_script", None),
        ("gh_update_script:v1", "gh_update_script", None),
        ("tool:v123", "tool", None),
        (":v1", None, "execution_ref_invalid"),
        ("tool:", None, "execution_ref_invalid"),
        ("tool:v", None, "execution_ref_invalid"),
        ("tool with space", None, "execution_ref_invalid"),
    ],
)
def test_resolve_tool_name_grammar(execution_ref, expected_name, expected_reason):
    name, reason = _resolve_tool_name(execution_ref)
    assert name == expected_name
    assert reason == expected_reason


def test_live_producer_result_is_frozen():
    result = LiveProducerResult(
        graph=PlanGraph(),
        applied=False,
        node_id="create_script",
        tool_name=None,
        outcome_status=None,
        reason="unknown_node",
    )
    with pytest.raises(Exception):
        result.applied = True  # frozen dataclass
