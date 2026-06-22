from __future__ import annotations

import asyncio
import ast
from pathlib import Path

from rook.agent.plan_graph_live import EXECUTION_PARAMS_KEY
from rook.agent.plan_graph_live_dispatch import run_live_producer_node
import rook.agent.plan_graph_live_dispatch as _dispatch_mod
from rook.agent.tool_dispatcher import ToolDispatcher
from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY


_DISPATCH_MODULE_PATH = Path(_dispatch_mod.__file__)
_ALLOWED_ROOK_IMPORTS = {
    "rook.agent.plan_graph_live",
    "rook.learning.plan_graph",
}
_FORBIDDEN_SOURCE_SUBSTRINGS = (
    "ToolDispatcher",
    "tool_dispatcher",
    "rook.server",
    "rook.agent.chat",
    "ChatRunner",
)

COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"
PROBE_TOOL_NAME = "lm4b_live_producer_probe"


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
    return {
        "success": True,
        "data": {"verified": True, "script_receipt": _usable_receipt()},
    }


def _error_raw() -> dict:
    return {
        "success": False,
        "data": {"verified": False, "script_receipt": _errors_receipt()},
    }


def _producer_graph(declared_params: dict) -> PlanGraph:
    node = PlanGraphNode(
        id="create_script",
        intent="Create C# script component through real dispatcher contract proof",
        execution_ref=PROBE_TOOL_NAME,
        metadata={
            OUTCOME_PROJECTION_ROLE_KEY: "artifact_producer",
            EXECUTION_PARAMS_KEY: declared_params,
        },
    )
    graph = PlanGraph(nodes={"create_script": node})
    node.status = "ready"
    return graph


class _Probe:
    def __init__(self, raw: dict):
        self.calls: list[dict] = []
        self._raw = raw

    async def __call__(self, **kwargs) -> dict:
        self.calls.append(dict(kwargs))
        return self._raw


def _install_no_rhino_sentinel(monkeypatch):
    # Record every invocation so a swallowed exception cannot pass silently:
    # ToolDispatcher.dispatch catches Exception around its post-dispatch
    # call_rhino path, so a raise alone is not proof the sentinel never fired.
    calls = []

    async def _fail_call_rhino(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("LM4B contract test must not call Rhino")

    monkeypatch.setattr("rook.agent.tool_dispatcher.call_rhino", _fail_call_rhino)
    return calls


def _run_with_real_dispatcher(raw: dict, monkeypatch):
    rhino_calls = _install_no_rhino_sentinel(monkeypatch)

    declared_params = {
        "language": "csharp",
        "code": "// noop",
        "component_name": "C",
    }
    graph = _producer_graph(declared_params)
    probe = _Probe(raw)
    dispatcher = ToolDispatcher()
    dispatcher.register_local(PROBE_TOOL_NAME, probe)

    result = asyncio.run(
        run_live_producer_node(graph, "create_script", dispatcher.dispatch)
    )
    return result, probe, declared_params, rhino_calls


def test_real_tool_dispatcher_dispatch_happy_path(monkeypatch):
    result, probe, declared_params, rhino_calls = _run_with_real_dispatcher(
        _usable_raw(), monkeypatch
    )

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    assert result.graph.nodes["create_script"].status == "succeeded"
    assert probe.calls == [declared_params]
    assert "port" not in probe.calls[0]
    assert rhino_calls == []


def test_real_tool_dispatcher_dispatch_returned_failure_is_producer_success(monkeypatch):
    result, probe, declared_params, rhino_calls = _run_with_real_dispatcher(
        _error_raw(), monkeypatch
    )

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == PROBE_TOOL_NAME
    node = result.graph.nodes["create_script"]
    assert node.status == "succeeded"
    assert node.evidence is not None
    assert node.evidence.tool_status == "failed"
    assert node.evidence.verified is False
    assert node.evidence.receipt is not None
    assert node.evidence.receipt["mutation"]["status"] == "created"
    assert node.evidence.repair_anchor is not None
    assert node.evidence.repair_anchor["component_guid"] == COMPONENT_GUID
    assert probe.calls == [declared_params]
    assert "port" not in probe.calls[0]
    assert rhino_calls == []


def test_live_dispatch_module_import_boundary():
    source = _DISPATCH_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_modules: list[str] = []

    for forbidden in _FORBIDDEN_SOURCE_SUBSTRINGS:
        assert forbidden not in source, (
            f"plan_graph_live_dispatch.py must not mention {forbidden!r}"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.append(module)
            for alias in node.names:
                assert alias.name != "*", "no star imports in the live dispatch seam"
                assert not alias.name.startswith("_producer"), (
                    f"dispatch seam must not import private runner helper {alias.name!r}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        elif isinstance(node, ast.Attribute):
            assert not node.attr.startswith("_producer"), (
                f"dispatch seam must not reach a private runner helper: .{node.attr}"
            )
        elif isinstance(node, ast.Name):
            assert not node.id.startswith("_producer"), (
                f"dispatch seam must not reference a private runner helper: {node.id}"
            )

    for module in imported_modules:
        if module.startswith("rook."):
            assert module in _ALLOWED_ROOK_IMPORTS, (
                f"unexpected rook import in live dispatch seam: {module!r}"
            )
