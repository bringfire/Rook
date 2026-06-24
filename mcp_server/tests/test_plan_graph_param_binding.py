"""LM4K unit tests for bind_params_from_memory — runtime memory.facts -> producer
params. Pure: returns merged params, no node write, no mutation, deep-copies, no
partial success. In the focused PlanGraph gate (test_plan_graph*.py). Run from repo root.
"""

from __future__ import annotations

import ast
import pathlib

from rook.learning.plan_graph import GraphMemory, PlanGraph
from rook.learning.plan_graph_param_binding import bind_params_from_memory


_BASE = {"code": "A = 42.0;", "mode": "body", "language": "csharp"}


def _graph_with_facts(facts: dict) -> PlanGraph:
    return PlanGraph(memory=GraphMemory(facts=facts))


class _NoDeepcopy:
    """A value whose deepcopy raises -- exercises the copy-failure findings."""

    def __deepcopy__(self, memo):
        raise RuntimeError("no copy")


def test_nested_path_success():
    g = _graph_with_facts({"repair_anchor": {"component_guid": "GUID-1"}})
    r = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.findings == ()
    assert r.params == {**_BASE, "guid": "GUID-1"}


def test_flat_path_equals_nested():
    g = _graph_with_facts(
        {"component_guid": "GUID-1", "repair_anchor": {"component_guid": "GUID-1"}}
    )
    flat = bind_params_from_memory(_BASE, g, {"guid": ("component_guid",)})
    nested = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert flat.findings == () and nested.findings == ()
    assert flat.params["guid"] == nested.params["guid"] == "GUID-1"


def test_memory_fact_missing_returns_none():
    g = _graph_with_facts({"repair_anchor": {"language": "csharp"}})  # no component_guid
    r = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_fact_missing"]


def test_memory_path_invalid_empty_and_nonstring():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    empty = bind_params_from_memory(_BASE, g, {"guid": ()})
    nonstr = bind_params_from_memory(_BASE, g, {"guid": ("component_guid", 5)})
    assert empty.params is None
    assert [f.code for f in empty.findings] == ["memory_path_invalid"]
    assert nonstr.params is None
    assert [f.code for f in nonstr.findings] == ["memory_path_invalid"]


def test_memory_fact_invalid_non_mapping_intermediate():
    g = _graph_with_facts({"repair_anchor": "not-a-dict"})
    r = bind_params_from_memory(_BASE, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_fact_invalid"]


def test_base_params_invalid():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    r = bind_params_from_memory(["not", "a", "mapping"], g, {"guid": ("component_guid",)})
    assert r.params is None
    assert [f.code for f in r.findings] == ["base_params_invalid"]


def test_param_key_invalid_none_and_empty():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    none_key = bind_params_from_memory(_BASE, g, {None: ("component_guid",)})
    empty_key = bind_params_from_memory(_BASE, g, {"": ("component_guid",)})
    assert none_key.params is None
    assert [f.code for f in none_key.findings] == ["param_key_invalid"]
    assert empty_key.params is None
    assert [f.code for f in empty_key.findings] == ["param_key_invalid"]


def test_base_params_copy_failed():
    g = _graph_with_facts({"component_guid": "GUID-1"})
    base = {"bad": _NoDeepcopy()}  # a Mapping, but deepcopy of its value raises
    r = bind_params_from_memory(base, g, {"guid": ("component_guid",)})
    assert r.params is None
    assert [f.code for f in r.findings] == ["base_params_copy_failed"]


def test_memory_value_copy_failed():
    g = _graph_with_facts({"weird": _NoDeepcopy()})  # present, but deepcopy raises
    r = bind_params_from_memory(_BASE, g, {"guid": ("weird",)})
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_value_copy_failed"]


def test_no_partial_success_collects_and_returns_none():
    # "guid" would resolve, but the missing binding nulls the whole result.
    g = _graph_with_facts({"component_guid": "GOOD"})
    r = bind_params_from_memory(
        _BASE, g, {"guid": ("component_guid",), "missing": ("absent_key",)}
    )
    assert r.params is None
    assert [f.code for f in r.findings] == ["memory_fact_missing"]


def test_collects_base_and_binding_findings_together():
    # Base copy fails AND bindings are bad -> ALL findings collected, params None
    # (the contract is to process all bindings, not short-circuit on base failure).
    g = _graph_with_facts({"component_guid": "GOOD"})
    base = {"bad": _NoDeepcopy()}
    r = bind_params_from_memory(
        base, g, {"guid": ("absent_key",), "x": ()}  # missing fact + invalid path
    )
    assert r.params is None
    assert sorted(f.code for f in r.findings) == [
        "base_params_copy_failed",
        "memory_fact_missing",
        "memory_path_invalid",
    ]


def test_immutability_of_inputs():
    facts = {"repair_anchor": {"component_guid": "GUID-1"}}
    g = _graph_with_facts(facts)
    base = dict(_BASE)
    r = bind_params_from_memory(base, g, {"guid": ("repair_anchor", "component_guid")})
    assert r.params is not None
    assert g.memory.facts == {"repair_anchor": {"component_guid": "GUID-1"}}
    assert base == _BASE
    # mutating the returned params must not touch base
    r.params["code"] = "changed"
    assert base["code"] == "A = 42.0;"


def test_bound_dict_value_is_deepcopied_from_memory():
    g = _graph_with_facts({"repair_anchor": {"component_guid": "GUID-1"}})
    r = bind_params_from_memory({"x": 1}, g, {"anchor": ("repair_anchor",)})
    assert r.params["anchor"] == {"component_guid": "GUID-1"}
    r.params["anchor"]["component_guid"] = "MUTATED"
    assert g.memory.facts["repair_anchor"]["component_guid"] == "GUID-1"


def test_module_uses_no_agent_layer_and_no_execution_params_key():
    # AST-based (not text-based): a docstring/comment mention of the token is fine;
    # what matters is that the module neither imports the agent layer nor references
    # EXECUTION_PARAMS_KEY as an identifier.
    import rook.learning.plan_graph_param_binding as mod

    src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported_modules: set[str] = set()
    referenced: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(a.name for a in node.names)
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            referenced.update((a.asname or a.name) for a in node.names)
        elif isinstance(node, ast.Name):
            referenced.add(node.id)
        elif isinstance(node, ast.Attribute):
            referenced.add(node.attr)
    assert not any(m.startswith("rook.agent") for m in imported_modules), imported_modules
    assert "EXECUTION_PARAMS_KEY" not in referenced
