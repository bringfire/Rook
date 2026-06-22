from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

from rook.learning.plan_graph import PlanGraph, PlanGraphNode
from rook.learning.plan_graph_projection import OUTCOME_PROJECTION_ROLE_KEY
from rook.learning.plan_graph_templates import (
    BindingSpec,
    TemplateEntry,
    bind_parameters,
    select_and_bind,
    select_template,
)


_DESCRIPTOR = {
    "domain": "grasshopper",
    "operation": "create_repair",
    "language": "csharp",
}

COMPONENT_GUID = "fbfd3ba5-5951-4064-8478-ee1d173150a9"


def _create_result() -> dict:
    return {
        "success": False,
        "message": "Component created with compile errors.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "create",
                "language": "csharp",
                "artifact_status": "created_with_errors",
                "mutation": {"status": "created", "component_guid": COMPONENT_GUID},
                "verification": {"status": "failed", "target_error_count": 1},
                "repair_anchor": {"component_guid": COMPONENT_GUID, "language": "csharp"},
            }
        },
    }


def _update_result() -> dict:
    return {
        "success": True,
        "message": "Script updated; component is usable.",
        "data": {
            "script_receipt": {
                "version": 1,
                "operation": "update",
                "language": "csharp",
                "artifact_status": "usable",
                "mutation": {"status": "written", "component_guid": COMPONENT_GUID},
                "verification": {"status": "passed", "target_error_count": 0},
                "repair_anchor": {"component_guid": COMPONENT_GUID, "language": "csharp"},
            }
        },
    }


def test_single_exact_match_selects_template():
    selection = select_template(_DESCRIPTOR)

    assert selection.selected_template_id == "gh_csharp_create_repair"
    assert selection.graph is not None
    assert "create_script" in selection.graph.nodes
    assert [f.code for f in selection.findings] == ["template_selected"]
    assert selection.findings[0].severity == "info"
    assert selection.findings[0].template_ids == ("gh_csharp_create_repair",)

    evaluation = next(
        e for e in selection.evaluations if e.template_id == "gh_csharp_create_repair"
    )
    assert evaluation.matched is True
    assert all(c.outcome == "accepted" for c in evaluation.criteria)


def test_two_selections_are_independent_and_do_not_corrupt_registry():
    first = select_template(_DESCRIPTOR)
    second = select_template(_DESCRIPTOR)

    # mutate the first selection's graph structure
    first.graph.nodes["create_script"].status = "succeeded"
    first.graph.nodes["create_script"].intent = "MUTATED"
    first.graph.nodes["injected"] = PlanGraphNode(id="injected", intent="X")
    first.graph.edges.clear()

    # second selection is pristine
    assert second.graph.nodes["create_script"].status == "pending"
    assert second.graph.nodes["create_script"].intent == "Create C# script component"
    assert "injected" not in second.graph.nodes
    assert len(second.graph.edges) == 1

    # a fresh selection is also pristine (registry source uncorrupted)
    third = select_template(_DESCRIPTOR)
    assert third.graph.nodes["create_script"].status == "pending"
    assert "injected" not in third.graph.nodes
    assert len(third.graph.edges) == 1


def test_value_mismatch_yields_no_matching_template():
    descriptor = {**_DESCRIPTOR, "language": "python"}
    selection = select_template(descriptor)

    assert selection.selected_template_id is None
    assert selection.graph is None
    assert [f.code for f in selection.findings] == ["no_matching_template"]
    assert selection.findings[0].severity == "error"

    evaluation = selection.evaluations[0]
    lang_check = next(c for c in evaluation.criteria if c.field == "language")
    assert lang_check.outcome == "value_mismatch"
    assert lang_check.actual == "python"
    assert lang_check.expected == "csharp"


def test_missing_field_is_distinct_from_value_mismatch():
    descriptor = {"domain": "grasshopper", "operation": "create_repair"}  # no language
    selection = select_template(descriptor)

    assert selection.graph is None
    assert selection.findings[0].code == "no_matching_template"

    evaluation = selection.evaluations[0]
    lang_check = next(c for c in evaluation.criteria if c.field == "language")
    assert lang_check.outcome == "missing_field"
    assert lang_check.actual is None


def test_ambiguous_intent_matches_multiple_templates():
    crit = (("kind", "x"),)
    registry = (
        TemplateEntry(
            "alpha",
            crit,
            lambda: PlanGraph(nodes={"a": PlanGraphNode(id="a", intent="A")}),
        ),
        TemplateEntry(
            "beta",
            crit,
            lambda: PlanGraph(nodes={"b": PlanGraphNode(id="b", intent="B")}),
        ),
    )
    selection = select_template({"kind": "x"}, registry=registry)

    assert selection.selected_template_id is None
    assert selection.graph is None
    assert [f.code for f in selection.findings] == ["ambiguous_template"]
    assert selection.findings[0].severity == "error"
    assert selection.findings[0].template_ids == ("alpha", "beta")


def test_selected_template_drives_to_complete_through_walker():
    from rook.learning.plan_graph_walker import walk_plan_graph

    selection = select_template(_DESCRIPTOR)
    report = walk_plan_graph(
        selection.graph,
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert report.final_graph_status == "complete"
    assert report.halted is False


def test_evaluations_are_deterministic():
    a = select_template(_DESCRIPTOR)
    b = select_template(_DESCRIPTOR)

    assert [e.template_id for e in a.evaluations] == [e.template_id for e in b.evaluations]
    fields_a = [c.field for c in a.evaluations[0].criteria]
    fields_b = [c.field for c in b.evaluations[0].criteria]
    assert fields_a == fields_b
    assert fields_a == sorted(fields_a)  # criteria normalized to sorted order


def _direct_import_modules(path: str) -> set[str]:
    tree = ast.parse(Path(path).read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level
            modules.add(f"{prefix}{node.module or ''}")
    return modules


def test_templates_module_imports_only_plan_graph_among_rook():
    imports = _direct_import_modules(
        "mcp_server/src/rook/learning/plan_graph_templates.py"
    )
    assert "rook.learning.plan_graph" in imports
    assert "rook.learning.plan_graph_bridge" not in imports
    assert "rook.learning.plan_graph_walker" not in imports
    assert "rook.agent.planner" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.server" not in imports
    rook_or_relative = {
        m for m in imports if m.startswith("rook.") or m.startswith(".")
    }
    assert rook_or_relative == {"rook.learning.plan_graph"}


def test_importing_templates_does_not_load_drive_or_heavy_modules():
    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )

    probe = (
        "import sys\n"
        "import rook.learning.plan_graph_templates\n"
        "for mod in (\n"
        "    'rook.learning.plan_graph_walker',\n"
        "    'rook.learning.plan_graph_bridge',\n"
        "    'rook.agent.planner',\n"
        "    'rook.agent.tool_dispatcher',\n"
        "    'dspy',\n"
        "    'litellm',\n"
        "):\n"
        "    if mod in sys.modules:\n"
        "        raise SystemExit(mod + ' loaded')\n"
    )

    subprocess.run(
        [sys.executable, "-c", probe],
        check=True,
        env=env,
    )


def _bindable_graph() -> PlanGraph:
    return PlanGraph(
        nodes={"create_script": PlanGraphNode(id="create_script", intent="Create")}
    )


def test_bind_parameters_writes_memory_fact_and_node_metadata():
    graph = _bindable_graph()
    bindings = (
        BindingSpec("goal", "memory_fact", "goal"),
        BindingSpec(
            "component_name", "node_metadata", "component_name", node_id="create_script"
        ),
    )

    result = bind_parameters(
        graph, bindings, {"goal": "make a box", "component_name": "BoxMaker"}
    )

    assert result.findings == ()
    assert result.graph is not None
    assert result.graph.memory.facts["goal"] == "make a box"
    assert result.graph.nodes["create_script"].metadata["component_name"] == "BoxMaker"
    # input graph unmutated
    assert graph.memory.facts == {}
    assert graph.nodes["create_script"].metadata == {}


def test_bind_parameters_applies_all_bindings_in_order():
    graph = _bindable_graph()
    bindings = (
        BindingSpec("a", "memory_fact", "a"),
        BindingSpec("b", "memory_fact", "b"),
    )

    result = bind_parameters(graph, bindings, {"a": "1", "b": "2"})

    assert result.findings == ()
    assert result.graph.memory.facts == {"a": "1", "b": "2"}


def test_bind_parameters_required_missing_returns_none_with_error():
    graph = _bindable_graph()
    bindings = (
        BindingSpec(
            "component_name",
            "node_metadata",
            "component_name",
            node_id="create_script",
            required=True,
        ),
    )

    result = bind_parameters(graph, bindings, {})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["missing_required_binding"]
    assert result.findings[0].severity == "error"
    assert result.findings[0].field == "component_name"


def test_bind_parameters_optional_missing_skips_silently():
    graph = _bindable_graph()
    bindings = (BindingSpec("goal", "memory_fact", "goal"),)

    result = bind_parameters(graph, bindings, {})

    assert result.findings == ()
    assert result.graph is not None
    assert "goal" not in result.graph.memory.facts


def test_bind_parameters_unknown_node_target_returns_none_with_error():
    graph = _bindable_graph()
    bindings = (BindingSpec("x", "node_metadata", "x", node_id="does_not_exist"),)

    result = bind_parameters(graph, bindings, {"x": "v"})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["unknown_binding_target"]


def test_bind_parameters_node_metadata_without_node_id_returns_none_with_error():
    graph = _bindable_graph()
    bindings = (BindingSpec("x", "node_metadata", "x", node_id=None),)

    result = bind_parameters(graph, bindings, {"x": "v"})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["unknown_binding_target"]


def test_bind_parameters_deepcopies_mutable_value():
    graph = _bindable_graph()
    payload = {"nested": ["a"]}
    bindings = (BindingSpec("cfg", "memory_fact", "cfg"),)

    result = bind_parameters(graph, bindings, {"cfg": payload})

    # mutate the descriptor value AFTER binding
    payload["nested"].append("b")
    payload["added"] = True

    assert result.graph.memory.facts["cfg"] == {"nested": ["a"]}


def test_bind_parameters_copy_failure_returns_none_with_error():
    class _Uncopyable:
        def __deepcopy__(self, memo):
            raise RuntimeError("nope")

    graph = _bindable_graph()
    bindings = (BindingSpec("cfg", "memory_fact", "cfg"),)

    result = bind_parameters(graph, bindings, {"cfg": _Uncopyable()})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["binding_value_copy_failed"]


def test_bind_parameters_later_failure_discards_earlier_success():
    # Watchpoint 1: a later failure must null the graph; no partial bind leaks.
    graph = _bindable_graph()
    bindings = (
        BindingSpec("goal", "memory_fact", "goal"),  # would succeed
        BindingSpec("missing", "memory_fact", "missing", required=True),  # fails
    )

    result = bind_parameters(graph, bindings, {"goal": "g"})

    assert result.graph is None
    assert [f.code for f in result.findings] == ["missing_required_binding"]


def test_bind_parameters_reports_all_errors():
    graph = _bindable_graph()
    bindings = (
        BindingSpec("a", "node_metadata", "a", node_id="nope"),  # unknown target
        BindingSpec("b", "memory_fact", "b", required=True),  # required missing
    )

    result = bind_parameters(graph, bindings, {"a": "v"})

    assert result.graph is None
    assert sorted(f.code for f in result.findings) == [
        "missing_required_binding",
        "unknown_binding_target",
    ]


def test_select_and_bind_binds_only_binding_graph():
    descriptor = {**_DESCRIPTOR, "component_name": "BoxMaker", "goal": "make a box"}

    result = select_and_bind(descriptor)

    assert result.binding is not None
    assert result.binding.graph is not None
    assert (
        result.binding.graph.nodes["create_script"].metadata["component_name"]
        == "BoxMaker"
    )
    assert result.binding.graph.memory.facts["goal"] == "make a box"
    # Watchpoint 2: selection.graph stays UNBOUND
    assert (
        "component_name"
        not in result.selection.graph.nodes["create_script"].metadata
    )
    assert "goal" not in result.selection.graph.memory.facts
    # findings streams separate
    assert [f.code for f in result.selection.findings] == ["template_selected"]
    assert result.binding.findings == ()


def test_select_and_bind_no_match_has_no_binding():
    result = select_and_bind({**_DESCRIPTOR, "language": "python"})

    assert result.binding is None
    assert [f.code for f in result.selection.findings] == ["no_matching_template"]


def test_bound_default_template_drives_to_complete_through_walker():
    from rook.learning.plan_graph_walker import walk_plan_graph

    descriptor = {**_DESCRIPTOR, "component_name": "BoxMaker"}
    result = select_and_bind(descriptor)
    graph = result.binding.graph
    assert graph.nodes["create_script"].metadata["component_name"] == "BoxMaker"

    report = walk_plan_graph(
        graph,
        [
            ("create_script", _create_result()),
            ("repair_same_component", _update_result()),
        ],
    )

    assert report.final_graph_status == "complete"
    assert report.halted is False


_CREATE_REPAIR = {"domain": "grasshopper", "operation": "create_repair", "language": "csharp"}
_CREATE_VERIFY_REPAIR = {
    "domain": "grasshopper",
    "operation": "create_verify_repair",
    "language": "csharp",
}


def test_select_create_verify_repair():
    sel = select_template(_CREATE_VERIFY_REPAIR)
    assert sel.selected_template_id == "gh_csharp_create_verify_repair"


def test_select_create_repair_still_selects_two_node():
    sel = select_template(_CREATE_REPAIR)
    assert sel.selected_template_id == "gh_csharp_create_repair"


def test_registry_disjoint_via_evaluation_trail():
    # canonical create_repair -> verify template mismatches on `operation`
    sel = select_template(_CREATE_REPAIR)
    assert sel.selected_template_id == "gh_csharp_create_repair"
    other = next(
        e for e in sel.evaluations if e.template_id == "gh_csharp_create_verify_repair"
    )
    assert not other.matched
    op = next(c for c in other.criteria if c.field == "operation")
    assert op.outcome == "value_mismatch"

    # canonical create_verify_repair -> 2-node template mismatches on `operation`
    sel2 = select_template(_CREATE_VERIFY_REPAIR)
    assert sel2.selected_template_id == "gh_csharp_create_verify_repair"
    other2 = next(
        e for e in sel2.evaluations if e.template_id == "gh_csharp_create_repair"
    )
    assert not other2.matched
    op2 = next(c for c in other2.criteria if c.field == "operation")
    assert op2.outcome == "value_mismatch"


def test_template_role_metadata_pinned_to_projection_constant():
    graph = select_template(_CREATE_VERIFY_REPAIR).graph
    assert graph.nodes["create_script"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_producer"
    assert graph.nodes["verify_create"].metadata[OUTCOME_PROJECTION_ROLE_KEY] == "artifact_verifier"


def test_create_verify_repair_topology():
    graph = select_template(_CREATE_VERIFY_REPAIR).graph
    assert set(graph.nodes) == {"create_script", "verify_create", "repair_same_component"}
    assert graph.nodes["repair_same_component"].is_terminal is True
    kinds = {(e.source, e.target): e.kind for e in graph.edges}
    assert kinds[("create_script", "verify_create")] == "requires"
    assert kinds[("verify_create", "repair_same_component")] == "on_repair"
