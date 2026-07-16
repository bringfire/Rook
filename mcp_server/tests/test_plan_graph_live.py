from __future__ import annotations

import asyncio
import ast
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path

import pytest

from rook import tool_lifecycle_runtime
from rook.learning.plan_graph import (
    PlanGraph,
    PlanGraphNode,
)
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.agent.plan_graph_live import (
    EXECUTION_PARAMS_KEY,
    LiveProducerResult,
    apply_live_producer_node,
    _resolve_tool_name,
    _check_admissibility,
)
from rook.tool_lifecycle import (
    DispatchOrigin,
    contained_names,
    resolve_contained_identity,
)

import rook.agent.plan_graph_live as _live_mod
from rook.learning import plan_graph as _pg_mod

_ADAPTER_PATH = Path(_live_mod.__file__)
_LEARNING_DIR = Path(_pg_mod.__file__).parent

_ALLOWED_ROOK_IMPORTS = {
    "rook.tool_lifecycle",
    "rook.tool_lifecycle_runtime",
    "rook.learning.plan_graph",
    "rook.learning.plan_graph_projection",
    "rook.learning.plan_graph_runner",
}
_FORBIDDEN_SUBSTRINGS = ("tool_dispatcher", "rook.server", "chat", "ChatRunner")
_T5_EXPECTED_RED = "EXPECTED_RED:T5:AGENT_PROTOCOLS"


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
    if not ready:
        return graph
    # For ready=True, manually initialize to avoid deepcopy issues with non-deepcopyable
    # objects in metadata (e.g., _ExplodingValue in tests).
    node.status = "ready"
    return graph


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


# ===== Task 2 tests: admissibility preflight =====


@pytest.mark.parametrize(
    "graph_factory, node_id, expected",
    [
        (lambda: _producer_graph(), "create_script", None),
        (lambda: _producer_graph(), "missing", "unknown_node"),
        (lambda: _producer_graph(ready=False), "create_script", "node_not_runnable"),
        (lambda: _producer_graph(role=_ABSENT), "create_script", "role_missing"),
        (lambda: _producer_graph(role="banana"), "create_script", "role_invalid"),
        (lambda: _producer_graph(role="artifact_verifier"), "create_script", "role_not_producer"),
    ],
)
def test_check_admissibility(graph_factory, node_id, expected):
    assert _check_admissibility(graph_factory(), node_id) == expected


# ===== Task 3 tests: params resolution + dispatch + delegation =====

# ----- helpers for params-copy and Mapping-subclass cases -----


class _ExplodingValue:
    def __deepcopy__(self, memo):
        raise RuntimeError("deepcopy of value failed")


class _WeirdMap(Mapping):
    """A Mapping that is NOT a dict (proves params is normalized to plain dict)."""

    def __init__(self, data: dict):
        self._data = dict(data)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class _BadConversionMap(Mapping):
    """A Mapping whose dict(...) conversion fails (second params_copy_failed mode)."""

    def __getitem__(self, key):
        raise KeyError(key)

    def __iter__(self):
        raise RuntimeError("iteration boom")

    def __len__(self):
        return 1


class _ContainmentPoisonParams(Mapping):
    def __init__(self):
        self.accesses: list[str] = []

    def _fail(self, action: str):
        self.accesses.append(action)
        raise AssertionError(
            f"{_T5_EXPECTED_RED} PlanGraph parameters accessed via {action}"
        )

    def __getitem__(self, key):
        return self._fail(f"getitem:{key}")

    def __iter__(self):
        return self._fail("iter")

    def __len__(self):
        return self._fail("len")

    def get(self, key, default=None):
        return self._fail(f"get:{key}")

    def items(self):
        return self._fail("items")

    def keys(self):
        return self._fail("keys")

    def __copy__(self):
        return self._fail("copy")

    def __deepcopy__(self, memo):
        return self._fail("deepcopy")


@pytest.mark.parametrize("contained_name", tuple(sorted(contained_names())))
def test_contained_execution_ref_returns_typed_refusal_before_params_or_dispatch(
    monkeypatch,
    tmp_path,
    contained_name,
):
    from rook.learning import metrics_store

    poison = _ContainmentPoisonParams()
    graph = _producer_graph(
        execution_ref=f"{contained_name}:v1",
        execution_params=poison,
    )
    resolve_params_calls = []
    original_resolve_params = _live_mod._resolve_params

    def tracking_resolve_params(node):
        resolve_params_calls.append(node)
        return original_resolve_params(node)

    monkeypatch.setattr(_live_mod, "_resolve_params", tracking_resolve_params)
    monkeypatch.setattr(
        _live_mod,
        "apply_producer_result",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError(
                f"{_T5_EXPECTED_RED} PlanGraph containment reached outcome projection"
            )
        ),
    )
    store = metrics_store.MetricsStore(tmp_path / "metrics.json")
    monkeypatch.setattr(metrics_store, "_metrics_store", store)
    attempts = []
    real_recorder = tool_lifecycle_runtime._record_containment_denial

    def recording_spy(entry, origin):
        attempts.append((entry.name, origin.value))
        return real_recorder(entry, origin)

    monkeypatch.setattr(
        tool_lifecycle_runtime,
        "_record_containment_denial",
        recording_spy,
    )
    before = store.get_containment_denials_snapshot()

    async def forbidden_dispatch(_name, _params):
        raise AssertionError(
            f"{_T5_EXPECTED_RED} PlanGraph containment reached dispatch"
        )

    result = asyncio.run(
        apply_live_producer_node(graph, "create_script", forbidden_dispatch)
    )
    after = store.get_containment_denials_snapshot()
    added = after["events"][len(before["events"]):]
    entry = resolve_contained_identity(contained_name)

    assert entry is not None, _T5_EXPECTED_RED
    assert result.graph is graph, _T5_EXPECTED_RED
    assert result.applied is False, _T5_EXPECTED_RED
    assert result.node_id == "create_script", _T5_EXPECTED_RED
    assert result.tool_name == contained_name, _T5_EXPECTED_RED
    assert result.outcome_status is None, _T5_EXPECTED_RED
    assert result.reason == "tool_lifecycle_denied", _T5_EXPECTED_RED
    assert resolve_params_calls == [], _T5_EXPECTED_RED
    assert poison.accesses == [], _T5_EXPECTED_RED
    assert attempts == [
        (contained_name, DispatchOrigin.PLAN_GRAPH.value)
    ], _T5_EXPECTED_RED
    assert before["process_id"] == after["process_id"], _T5_EXPECTED_RED
    assert (
        before["process_start_token"] == after["process_start_token"]
    ), _T5_EXPECTED_RED
    assert len(added) == 1, _T5_EXPECTED_RED
    assert added[0]["tool"] == contained_name, _T5_EXPECTED_RED
    assert added[0]["disposition"] == entry.disposition.value, _T5_EXPECTED_RED
    assert added[0]["origin"] == DispatchOrigin.PLAN_GRAPH.value, _T5_EXPECTED_RED


def test_happy_path_applies_succeeded():
    graph = _producer_graph()
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.applied is True
    assert result.reason is None
    assert result.outcome_status == "succeeded"
    assert result.tool_name == "gh_create_csharp_script"
    assert len(spy.calls) == 1
    assert spy.calls[0][0] == "gh_create_csharp_script"
    assert result.graph.nodes["create_script"].status == "succeeded"


def test_returned_failure_is_real_result_not_dispatch_failed():
    # success: False + created_with_errors is a REAL raw result, NOT dispatch_failed.
    graph = _producer_graph()
    spy = _Spy(raw=_error_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.reason is None
    assert result.reason != "dispatch_failed"
    assert result.applied is True
    # producer role: artifact existence -> succeeded, decoupled from tool failure
    assert result.outcome_status == "succeeded"
    node = result.graph.nodes["create_script"]
    assert node.status == "succeeded"
    assert node.evidence.tool_status == "failed"
    assert node.evidence.verified is False


@pytest.mark.parametrize(
    "graph_factory, node_id, expected_reason, expected_tool",
    [
        (lambda: _producer_graph(), "missing", "unknown_node", None),
        (lambda: _producer_graph(ready=False), "create_script", "node_not_runnable", None),
        (lambda: _producer_graph(role=_ABSENT), "create_script", "role_missing", None),
        (lambda: _producer_graph(role="banana"), "create_script", "role_invalid", None),
        (lambda: _producer_graph(role="artifact_verifier"), "create_script", "role_not_producer", None),
        (lambda: _producer_graph(execution_ref=None), "create_script", "execution_ref_missing", None),
        (lambda: _producer_graph(execution_ref=":v1"), "create_script", "execution_ref_invalid", None),
        (lambda: _producer_graph(with_params=False), "create_script", "execution_params_missing", "gh_create_csharp_script"),
        (lambda: _producer_graph(execution_params=["not", "a", "map"]), "create_script", "execution_params_invalid", "gh_create_csharp_script"),
        (lambda: _producer_graph(execution_params={"x": _ExplodingValue()}), "create_script", "params_copy_failed", "gh_create_csharp_script"),
    ],
)
def test_pre_dispatch_faults_never_dispatch(graph_factory, node_id, expected_reason, expected_tool):
    graph = graph_factory()
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, node_id, spy))

    assert result.applied is False
    assert result.reason == expected_reason
    assert result.tool_name == expected_tool
    assert result.outcome_status is None
    assert result.graph is graph          # input graph returned unchanged
    assert spy.calls == []                # NO side effect before admissibility/resolution


def test_params_copy_failed_on_dict_conversion():
    # Second params_copy_failed mode: a Mapping whose dict(...) conversion raises.
    graph = _producer_graph(execution_params=_BadConversionMap())
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.applied is False
    assert result.reason == "params_copy_failed"
    assert result.tool_name == "gh_create_csharp_script"
    assert spy.calls == []


def test_dispatched_params_is_plain_dict_not_mapping_subclass():
    source = {"language": "csharp", "code": "// x"}
    graph = _producer_graph(execution_params=_WeirdMap(source))
    spy = _Spy(raw=_usable_raw())

    asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    dispatched = spy.calls[0][1]
    assert type(dispatched) is dict       # plain dict, NOT a Mapping subclass
    assert dispatched == source


def test_dispatched_params_detached_from_node_metadata():
    params = {"code": "// original", "nested": {"k": 1}}
    graph = _producer_graph(execution_params=params)
    spy = _Spy(raw=_usable_raw())

    asyncio.run(apply_live_producer_node(graph, "create_script", spy))
    dispatched = spy.calls[0][1]

    # Mutate node metadata after the call; the dispatched dict must be unaffected.
    meta_params = graph.nodes["create_script"].metadata[EXECUTION_PARAMS_KEY]
    meta_params["code"] = "// mutated"
    meta_params["nested"]["k"] = 999

    assert dispatched is not meta_params
    assert dispatched["code"] == "// original"
    assert dispatched["nested"]["k"] == 1


def test_dispatch_exception_is_dispatch_failed():
    graph = _producer_graph()
    spy = _Spy(raises=RuntimeError("transport down"))

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.applied is False
    assert result.reason == "dispatch_failed"
    assert result.tool_name == "gh_create_csharp_script"
    assert result.outcome_status is None
    assert result.graph is graph          # input preserved, no synthesized raw result
    assert len(spy.calls) == 1            # dispatch WAS attempted exactly once


def test_admissibility_precedes_resolution():
    # Two coexisting faults: non-runnable AND missing execution_ref.
    graph = _producer_graph(ready=False, execution_ref=None)
    spy = _Spy(raw=_usable_raw())

    result = asyncio.run(apply_live_producer_node(graph, "create_script", spy))

    assert result.reason == "node_not_runnable"   # admissibility wins
    assert spy.calls == []


# ===== Task 4 tests: bidirectional import-boundary guard =====


def test_adapter_imports_only_public_pure_symbols():
    tree = ast.parse(_ADAPTER_PATH.read_text(encoding="utf-8"))
    imported_modules: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            imported_modules.append(module)
            for alias in node.names:
                assert alias.name != "*", "no star imports in the live adapter"
                assert not alias.name.startswith("_producer"), (
                    f"adapter must not import private runner helper {alias.name!r}"
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imported_modules.append(alias.name)
        # Catch private-helper access via attribute or bare name, e.g.
        # `runner._producer_runnable_check(...)` or a re-bound `_producer_*`,
        # which a from-import scan alone would miss.
        elif isinstance(node, ast.Attribute):
            assert not node.attr.startswith("_producer"), (
                f"adapter must not reach a private runner helper: .{node.attr}"
            )
        elif isinstance(node, ast.Name):
            assert not node.id.startswith("_producer"), (
                f"adapter must not reference a private runner helper: {node.id}"
            )

    joined = " ".join(imported_modules)
    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in joined, f"adapter must not import {forbidden!r}"

    for module in imported_modules:
        if module.startswith("rook."):
            assert module in _ALLOWED_ROOK_IMPORTS, (
                f"unexpected rook import in live adapter: {module!r}"
            )


def test_adapter_does_not_use_runnable_nodes():
    """LM4A-FU1 regression guard: the live adapter must never reach for
    ``runnable_nodes``.

    ``runnable_nodes`` is a SNAPSHOT api -- it deep-copies every ready node. In a
    live side-effect preflight that can raise on a transient non-deepcopyable
    ``execution_params`` value BEFORE ``_resolve_params`` can return the graceful
    ``params_copy_failed`` (the original LM4A bug). Readiness in the live adapter
    is a direct ``node.status == "ready"`` read. ``runnable_nodes`` stays valid for
    PURE scheduling/replay consumers; it is simply wrong here. See
    docs/superpowers/findings/2026-06-22-lm4a-runnable-nodes-boundary-audit.md.
    """
    tree = ast.parse(_ADAPTER_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                assert alias.name != "runnable_nodes", (
                    "live adapter must not import runnable_nodes (snapshot/deepcopy "
                    "api -- use node.status directly in a side-effect preflight)"
                )
        elif isinstance(node, ast.Attribute):
            assert node.attr != "runnable_nodes", (
                "live adapter must not call .runnable_nodes (snapshot/deepcopy api)"
            )
        elif isinstance(node, ast.Name):
            assert node.id != "runnable_nodes", (
                "live adapter must not reference runnable_nodes (snapshot/deepcopy api)"
            )


def test_pure_modules_do_not_import_live_adapter():
    pure_files = sorted(_LEARNING_DIR.glob("plan_graph*.py"))
    assert pure_files, "expected to find learning/plan_graph*.py modules"

    for pyfile in pure_files:
        tree = ast.parse(pyfile.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "plan_graph_live" not in (node.module or ""), (
                    f"{pyfile.name} must not import the live adapter"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "plan_graph_live" not in alias.name, (
                        f"{pyfile.name} must not import the live adapter"
                    )
