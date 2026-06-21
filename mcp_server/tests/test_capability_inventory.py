from __future__ import annotations

from rook.agent.capability_record import CapabilityInventory, SurfaceSources
from rook.agent.capability_inventory import (
    INTERCEPTED_META_TOOLS,
    _dispatch_context_from_sources,
    build_inventory,
    format_report,
)


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
        intercepted_names=INTERCEPTED_META_TOOLS,
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
        "request_tools", "search_tools", "ui_block", "list_chat_models",
        "set_chat_model", "gh_snapshot", "gh_move", "rhino_objects",
        "rhino_create", "gh_edit", "gh_knowledge_query", "dual_tool",
    }


def test_intercepted_meta_tools_are_not_dispatch_unknown():
    inv = build_inventory(_static_sources(), _static_catalog())
    by_name = {r.name: r for r in inv.records}

    for meta in ("request_tools", "search_tools", "ui_block", "list_chat_models", "set_chat_model"):
        assert by_name[meta].dispatch_path == "chatrunner_intercepted"
    assert not any(
        f.code == "dispatch_unknown" and f.tool in INTERCEPTED_META_TOOLS
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
    ctx = _dispatch_context_from_sources(sources)
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
    assert first.startswith("Capability inventory: 12 records, 4 findings")


def test_build_inventory_does_not_read_live_catalog_cache(monkeypatch):
    import rook.agent.tool_registry as tool_registry_module

    def _boom(*args, **kwargs):
        raise AssertionError("build_inventory must not read the live catalog cache")

    monkeypatch.setattr(tool_registry_module, "load_catalog_from_cache", _boom)
    monkeypatch.setattr(tool_registry_module, "get_catalog_cache_path", _boom)

    inv = build_inventory(_static_sources(), _static_catalog())
    assert inv.records  # built purely from injected args, no cache access


import rook.agent.tool_registry as tool_registry_module
from rook.agent.capability_inventory import (
    collect_live_sources,
    reconcile_active_schemas,
)


def _reconcile_sources(gh_canvas_members: tuple[str, ...]) -> SurfaceSources:
    return SurfaceSources(
        agent_tier0=frozenset({"request_tools", "search_tools", "gh_snapshot"}),
        groups={"gh_canvas": gh_canvas_members},
        mcp_only_groups=frozenset(),
        bridge_names=frozenset({"gh_snapshot", "gh_edit", "gh_move"}),
        intercepted_names=INTERCEPTED_META_TOOLS,
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
        intercepted_names=INTERCEPTED_META_TOOLS,
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
    assert sources.intercepted_names == INTERCEPTED_META_TOOLS
    assert sources.local_tool_names == frozenset()
    assert "gh_snapshot" in sources.bridge_names or "gh_snapshot" in sources.agent_tier0
