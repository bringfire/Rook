from __future__ import annotations

import dataclasses
import pytest

import rook.agent.tool_registry as tool_registry_module
from rook.agent.capability_inventory import (
    INTERNAL_AGENT_META_TOOLS,
    build_inventory,
    capability_findings_from_audit,
    collect_live_sources,
    dispatch_context_from_sources,
    format_report,
    reconcile_active_schemas,
)
from rook.agent.capability_record import CapabilityInventory, SurfaceSources


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"{name} tool",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _static_sources() -> SurfaceSources:
    return SurfaceSources(
        agent_tier0=frozenset({"request_tools", "gh_snapshot"}),
        readonly_tier0=frozenset({"rhino_objects"}),
        groups={
            "gh_canvas": ("gh_edit", "gh_move"),
            "gh_knowledge": ("gh_knowledge_query",),
            "rhino_geometry": ("rhino_create",),
            "dual_group": ("dual_tool",),
            "gh_patterns": ("dual_tool",),
        },
        mcp_only_groups=frozenset({"gh_knowledge", "gh_patterns"}),
        bridge_names=frozenset(
            {"gh_edit", "gh_move", "gh_snapshot", "rhino_objects", "rhino_create"}
        ),
        intercepted_names=INTERNAL_AGENT_META_TOOLS,
        zero_argument_names=frozenset({"gh_snapshot"}),
        strict_no_argument_names=frozenset({"gh_snapshot"}),
        creation_tools=frozenset({"gh_edit"}),
        needs_verification=frozenset({"gh_edit"}),
    )


def _static_catalog() -> dict:
    # NOTE: "gh_edit" intentionally absent -> missing_schema for a local_visible tool.
    return {
        name: _schema(name)
        for name in (
            "gh_snapshot",
            "gh_move",
            "rhino_objects",
            "rhino_create",
            "gh_knowledge_query",
            "dual_tool",
            "request_tools",
        )
    }


def _finding_keys(inventory: CapabilityInventory):
    return {(f.code, f.tool, f.severity) for f in inventory.findings}


def test_build_inventory_emits_expected_findings():
    inv = build_inventory(_static_sources(), _static_catalog())

    assert _finding_keys(inv) == {
        ("dispatch_unknown", "dual_tool", "error"),
        ("contradictory_membership", "dual_tool", "error"),
        ("dispatch_unknown", "gh_knowledge_query", "info"),
        ("missing_schema", "gh_edit", "warning"),
    }


def test_build_inventory_records_cover_full_universe_sorted():
    inv = build_inventory(_static_sources(), _static_catalog())
    names = [r.name for r in inv.records]

    assert names == sorted(names)
    assert set(names) == {
        "request_tools", "search_tools", "gh_snapshot", "gh_move", "rhino_objects",
        "rhino_create", "gh_edit", "gh_knowledge_query", "dual_tool",
        "rook_tools_ls", "rook_tools_search", "rook_tools_read",
        "rook_tools_call",
    }


def test_intercepted_meta_tools_are_not_dispatch_unknown():
    inv = build_inventory(_static_sources(), _static_catalog())
    by_name = {r.name: r for r in inv.records}

    for meta in INTERNAL_AGENT_META_TOOLS:
        assert by_name[meta].dispatch_path == "internal_agent_intercepted"
    assert not any(
        f.code == "dispatch_unknown" and f.tool in INTERNAL_AGENT_META_TOOLS
        for f in inv.findings
    )


def test_record_fields_are_sorted_and_provenance_correct():
    inv = build_inventory(_static_sources(), _static_catalog())
    by_name = {r.name: r for r in inv.records}

    gh_edit = by_name["gh_edit"]
    assert gh_edit.visibility == "local_visible"
    assert gh_edit.dispatch_path == "bridge_route"
    assert gh_edit.has_schema is False
    assert gh_edit.risk == ("creation", "needs_verification")  # sorted-stable order
    assert gh_edit.mcp_only is False

    knowledge = by_name["gh_knowledge_query"]
    assert knowledge.visibility == "mcp_only_visible"
    assert knowledge.mcp_only is True

    snap = by_name["gh_snapshot"]
    assert snap.no_argument is True
    assert snap.tiers == ("agent_tier0",)


def test_dispatch_context_maps_all_six_fields():
    sources = SurfaceSources(
        intercepted_names=frozenset({"a"}),
        local_tool_names=frozenset({"b"}),
        transform_names=frozenset({"c"}),
        bridge_names=frozenset({"d"}),
        excluded_names=frozenset({"e"}),
        strict_no_argument_names=frozenset({"f"}),
    )
    ctx = dispatch_context_from_sources(sources)
    assert ctx.intercepted_names == frozenset({"a"})
    assert ctx.local_tool_names == frozenset({"b"})
    assert ctx.transform_names == frozenset({"c"})
    assert ctx.bridge_names == frozenset({"d"})
    assert ctx.excluded_names == frozenset({"e"})
    assert ctx.strict_no_argument_names == frozenset({"f"})


def test_format_report_is_pure_and_stable():
    inv = build_inventory(_static_sources(), _static_catalog())
    first = format_report(inv)
    second = format_report(inv)
    assert first == second
    assert first.startswith("Capability inventory: 13 records, 4 findings")


def test_build_inventory_does_not_read_live_catalog_cache(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("build_inventory must not read the live catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    inv = build_inventory(_static_sources(), _static_catalog())
    assert inv.records  # built purely from injected args, no cache access


def _reconcile_sources(gh_canvas_members: tuple[str, ...]) -> SurfaceSources:
    return SurfaceSources(
        agent_tier0=frozenset({"request_tools", "search_tools", "gh_snapshot"}),
        groups={"gh_canvas": gh_canvas_members},
        mcp_only_groups=frozenset(),
        bridge_names=frozenset({"gh_snapshot", "gh_edit", "gh_move"}),
        intercepted_names=INTERNAL_AGENT_META_TOOLS,
    )


def _reconcile_catalog(extra: dict | None = None) -> dict:
    catalog = {name: _schema(name) for name in ("gh_snapshot", "gh_edit", "gh_move")}
    if extra:
        catalog.update(extra)
    return catalog


def test_reconcile_initial_surface_is_clean():
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move")), _reconcile_catalog(), group=None
    )
    assert findings == ()


def test_reconcile_group_activates_real_members_cleanly():
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move")),
        _reconcile_catalog(),
        group="gh_canvas",
    )
    assert findings == ()


def test_reconcile_flags_intended_member_absent_from_catalog():
    # gh_status is a real gh_canvas member but absent from the canned catalog,
    # so request_group cannot activate it -> intended_not_active.
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move", "gh_status")),
        _reconcile_catalog(),
        group="gh_canvas",
    )
    keys = {(f.code, f.tool, f.severity) for f in findings}
    assert ("intended_not_active", "gh_status", "warning") in keys


def test_reconcile_audit_runs_over_active_schemas_only():
    # mystery_tool is tier-active but has no dispatch path -> not_dispatchable.
    # ghost_tool is catalog-only and never active -> produces no finding.
    sources = SurfaceSources(
        agent_tier0=frozenset({"mystery_tool"}),
        intercepted_names=INTERNAL_AGENT_META_TOOLS,
    )
    catalog = {"mystery_tool": _schema("mystery_tool"), "ghost_tool": _schema("ghost_tool")}
    findings = reconcile_active_schemas(sources, catalog, group=None)
    keys = {(f.code, f.tool, f.severity) for f in findings}
    assert ("not_dispatchable", "mystery_tool", "error") in keys
    assert not any(f.tool == "ghost_tool" for f in findings)


def test_reconcile_does_not_read_live_catalog_cache(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("reconcile must not read the live catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)
    findings = reconcile_active_schemas(
        _reconcile_sources(("gh_edit", "gh_move")), _reconcile_catalog(), group=None
    )
    assert findings == ()


def test_collect_live_sources_reads_constants_only(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("collect_live_sources must not load the catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    sources = collect_live_sources()
    assert isinstance(sources, SurfaceSources)
    assert sources.intercepted_names == INTERNAL_AGENT_META_TOOLS
    assert sources.local_tool_names == frozenset()
    assert "gh_snapshot" in sources.bridge_names or "gh_snapshot" in sources.agent_tier0


def test_collect_live_sources_carries_readonly_allowed_groups(monkeypatch):
    from rook.agent.tool_groups import READONLY_ALLOWED_GROUPS

    def _boom(*args, **kwargs):
        raise AssertionError("collect_live_sources must not load the catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    sources = collect_live_sources()
    assert sources.readonly_allowed_groups == frozenset(READONLY_ALLOWED_GROUPS)


def test_reconcile_flags_active_member_not_in_intended_membership():
    # ToolRegistry builds groups from the live TOOL_GROUPS table, but `intended`
    # uses the injected sources.groups. A real gh_canvas member present in the
    # canned catalog but omitted from sources.groups activates yet is not
    # intended -> active_not_intended.
    sources = SurfaceSources(
        agent_tier0=frozenset({"request_tools", "search_tools"}),
        groups={"gh_canvas": ("gh_edit",)},  # intentionally omits gh_status
        bridge_names=frozenset({"gh_edit", "gh_status"}),
        intercepted_names=INTERNAL_AGENT_META_TOOLS,
    )
    catalog = {name: _schema(name) for name in ("gh_edit", "gh_status")}

    findings = reconcile_active_schemas(sources, catalog, group="gh_canvas")
    keys = {(f.code, f.tool, f.severity) for f in findings}

    assert ("active_not_intended", "gh_status", "warning") in keys
    assert not any(f.code == "intended_not_active" for f in findings)


def test_capability_findings_from_audit_maps_codes_and_severities():
    from rook.agent.chat.tool_contracts import DispatchabilityFinding

    audit = [
        DispatchabilityFinding(
            code="not_dispatchable", tool="a", classification="failure", message="m1"
        ),
        DispatchabilityFinding(
            code="missing_function_name", tool="", classification="schema", message="m2"
        ),
        DispatchabilityFinding(
            code="strict_no_arg_schema_drift",
            tool="c",
            classification="bridge_route",
            message="m3",
        ),
        DispatchabilityFinding(
            code="duplicate_visible_name", tool="d", classification="schema", message="m4"
        ),
    ]
    out = capability_findings_from_audit(audit)
    assert {(f.code, f.tool, f.severity) for f in out} == {
        ("not_dispatchable", "a", "error"),
        ("missing_function_name", "", "error"),
        ("strict_no_arg_schema_drift", "c", "error"),
        ("duplicate_visible_name", "d", "warning"),
    }
    assert [f.message for f in out] == ["m1", "m2", "m3", "m4"]


def test_collect_runtime_sources_enriches_local_tool_names(monkeypatch):
    import rook.agent.capability_inventory as ci
    import rook.agent.tool_dispatcher as td

    base = SurfaceSources(
        agent_tier0=frozenset({"a"}),
        bridge_names=frozenset({"a"}),
    )
    # Patch the module global the function calls, and the lazy-import target
    # (td.build_local_tools is resolved as an attribute at call time).
    monkeypatch.setattr(ci, "collect_live_sources", lambda: base)
    monkeypatch.setattr(td, "build_local_tools", lambda: {"loc1": object(), "loc2": object()})

    out = ci.collect_runtime_sources()
    assert out.local_tool_names == frozenset({"loc1", "loc2"})
    # enriched, not rebuilt: every other field identical to base
    assert dataclasses.replace(out, local_tool_names=frozenset()) == base


def test_collect_runtime_sources_propagates_builder_failure(monkeypatch):
    import rook.agent.capability_inventory as ci
    import rook.agent.tool_dispatcher as td

    monkeypatch.setattr(ci, "collect_live_sources", lambda: SurfaceSources())

    def _boom():
        raise RuntimeError("builder exploded")

    monkeypatch.setattr(td, "build_local_tools", _boom)
    with pytest.raises(RuntimeError):
        ci.collect_runtime_sources()


def test_collect_live_sources_carries_planner_evidence(monkeypatch):
    from rook.agent.planner import PLANNER_ALLOWED_GROUPS, PLANNER_TIER_0

    def _boom(*args, **kwargs):
        raise AssertionError("collect_live_sources must not load the catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    sources = collect_live_sources()
    assert sources.planner_tier0 == frozenset(PLANNER_TIER_0)
    assert sources.planner_allowed_groups == frozenset(PLANNER_ALLOWED_GROUPS)


def test_tiers_for_planner_and_readonly_is_sorted():
    sources = SurfaceSources(
        readonly_tier0=frozenset({"dual"}),
        planner_tier0=frozenset({"dual"}),
    )
    inv = build_inventory(sources, {"dual": _schema("dual")})
    record = {r.name: r for r in inv.records}["dual"]
    assert record.tiers == ("planner_tier0", "readonly_tier0")


def test_planner_only_tool_is_in_inventory_universe():
    # Guards the _universe drift: a tool present ONLY in planner_tier0 must get a
    # record (it would be missing if _universe didn't include planner_tier0).
    sources = SurfaceSources(planner_tier0=frozenset({"planner_only"}))
    inv = build_inventory(sources, {})
    assert "planner_only" in {r.name for r in inv.records}


def test_reconcile_active_schemas_initial_literal_matches_tier_fields():
    import typing

    from rook.agent.capability_record import TIER_FIELDS

    hints = typing.get_type_hints(reconcile_active_schemas)
    assert set(typing.get_args(hints["initial"])) == set(TIER_FIELDS)


def test_collect_live_sources_stays_light_no_planner_machinery():
    import os
    import subprocess
    import sys
    from pathlib import Path

    env = os.environ.copy()
    src_path = str(Path("mcp_server/src").resolve())
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    probe = (
        "import sys\n"
        "from rook.agent.capability_inventory import collect_live_sources\n"
        "collect_live_sources()\n"
        "heavy = [m for m in ('dspy', 'litellm', 'rook.agent.base_agent') "
        "if m in sys.modules]\n"
        "if heavy:\n"
        "    raise SystemExit('heavy modules loaded by collect_live_sources: ' + repr(heavy))\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, env=env)
