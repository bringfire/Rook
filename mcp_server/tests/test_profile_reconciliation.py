from __future__ import annotations

from rook.agent.capability_inventory import build_inventory
from rook.agent.capability_record import SurfaceSources
from rook.agent.execution_profile import (
    ProfileDefinition,
    ProfileFinding,
    ProfileResolution,
    resolve_profile,
)
from rook.agent.profile_reconciliation import ProfileReconciliation, reconcile_profile


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }


def _resolution(definition, *, tool_names=(), findings=()) -> ProfileResolution:
    # reconcile_profile reads only profile, tool_names, findings -> tools can be ().
    return ProfileResolution(
        profile=definition,
        tools=(),
        tool_names=tuple(tool_names),
        findings=tuple(findings),
    )


def _codes(rec: ProfileReconciliation):
    return {(f.code, f.tool, f.severity) for f in rec.registry_findings}


def test_clean_profile_has_no_registry_findings():
    sources = SurfaceSources(
        agent_tier0=frozenset({"gh_snapshot"}),
        bridge_names=frozenset({"gh_snapshot"}),
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0", groups=())
    resolution = _resolution(definition, tool_names=("gh_snapshot",))
    rec = reconcile_profile(resolution, sources, {"gh_snapshot": _schema("gh_snapshot")})
    assert rec.registry_findings == ()
    assert rec.active_names == ("gh_snapshot",)
    assert rec.intended_names == ("gh_snapshot",)


def test_intended_not_active_flagged():
    sources = SurfaceSources(
        agent_tier0=frozenset({"gh_snapshot"}),
        bridge_names=frozenset({"gh_snapshot"}),
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("ghost_tool", "gh_snapshot"))
    rec = reconcile_profile(resolution, sources, {"gh_snapshot": _schema("gh_snapshot")})
    assert ("intended_not_active", "ghost_tool", "warning") in _codes(rec)


def test_active_not_intended_proves_live_tool_groups_seam():
    # sources.groups lists ONLY gh_edit for gh_canvas, so the inventory (and thus
    # resolve_profile) intends only gh_edit. The disposable ToolRegistry activates
    # gh_canvas from the LIVE TOOL_GROUPS table, which also holds gh_move present
    # in the catalog -> active_not_intended for gh_move. Not a tautology: active
    # comes from the real registry, intended from resolve_profile.
    sources = SurfaceSources(
        groups={"gh_canvas": ("gh_edit",)},
        bridge_names=frozenset({"gh_edit", "gh_move"}),
    )
    catalog = {"gh_edit": _schema("gh_edit"), "gh_move": _schema("gh_move")}
    inventory = build_inventory(sources, catalog)
    resolution = resolve_profile(
        ProfileDefinition(name="canvas", groups=("gh_canvas",)), inventory
    )
    assert resolution.tool_names == ("gh_edit",)

    rec = reconcile_profile(resolution, sources, catalog)
    assert "gh_move" in rec.active_names
    assert ("active_not_intended", "gh_move", "warning") in _codes(rec)
    assert ("active_not_intended", "gh_edit", "warning") not in _codes(rec)


def test_group_activation_failed_for_mcp_only_group():
    definition = ProfileDefinition(name="p", groups=("gh_knowledge",))
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert ("group_activation_failed", "gh_knowledge", "warning") in _codes(rec)
    msg = next(f.message for f in rec.registry_findings if f.tool == "gh_knowledge")
    assert "MCP-only" in msg


def test_group_activation_failed_for_unknown_group():
    definition = ProfileDefinition(name="p", groups=("nonexistent_group",))
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert ("group_activation_failed", "nonexistent_group", "warning") in _codes(rec)
    msg = next(
        f.message for f in rec.registry_findings if f.tool == "nonexistent_group"
    )
    assert "Unknown group" in msg


def test_folds_not_dispatchable_audit_finding_as_error():
    # orphan_tool is tier-active and in catalog but in no dispatch surface.
    sources = SurfaceSources(agent_tier0=frozenset({"orphan_tool"}))
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("orphan_tool",))
    rec = reconcile_profile(
        resolution, sources, {"orphan_tool": _schema("orphan_tool")}
    )
    assert ("not_dispatchable", "orphan_tool", "error") in _codes(rec)


def test_profile_findings_carried_verbatim_and_not_folded():
    pf = ProfileFinding(
        profile="p",
        code="unknown_tier",
        subject="ghost_tier",
        severity="warning",
        message="m",
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=(), findings=(pf,))
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert rec.profile_findings == (pf,)
    assert all(f.code != "unknown_tier" for f in rec.registry_findings)


def test_registry_findings_sorted_and_names_sorted():
    sources = SurfaceSources(
        agent_tier0=frozenset({"b_tool", "a_tool"}),
        bridge_names=frozenset({"a_tool", "b_tool"}),
    )
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("z_tool", "m_tool"))
    catalog = {"a_tool": _schema("a_tool"), "b_tool": _schema("b_tool")}
    rec = reconcile_profile(resolution, sources, catalog)
    tools_order = [f.tool for f in rec.registry_findings]
    assert tools_order == sorted(tools_order)
    assert rec.active_names == ("a_tool", "b_tool")
    assert rec.intended_names == ("z_tool", "m_tool")  # carried from resolution verbatim


def test_initial_tier_none_uses_empty_tier_zero():
    sources = SurfaceSources(bridge_names=frozenset({"gh_edit", "gh_move"}))
    definition = ProfileDefinition(name="p", initial_tier=None, groups=("gh_canvas",))
    resolution = _resolution(definition, tool_names=("gh_edit",))
    catalog = {"gh_edit": _schema("gh_edit"), "gh_move": _schema("gh_move")}
    rec = reconcile_profile(resolution, sources, catalog)
    assert set(rec.active_names) == {"gh_edit", "gh_move"}


def test_malformed_initial_tier_yields_empty_tier_zero_no_crash():
    definition = ProfileDefinition(name="p", initial_tier="not_a_real_tier")  # type: ignore[arg-type]
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, SurfaceSources(), {})
    assert rec.active_names == ()
    assert isinstance(rec, ProfileReconciliation)


def test_malformed_initial_tier_matching_real_field_yields_empty_tier_zero():
    # "groups" is a real SurfaceSources field (a Mapping); a malformed initial_tier
    # equal to it must NOT pull its keys in as tier-0 members.
    sources = SurfaceSources(groups={"gh_canvas": ("gh_edit",)})
    definition = ProfileDefinition(name="p", initial_tier="groups", groups=())  # type: ignore[arg-type]
    resolution = _resolution(definition, tool_names=())
    rec = reconcile_profile(resolution, sources, {"gh_edit": _schema("gh_edit")})
    assert rec.active_names == ()
    assert "gh_canvas" not in rec.active_names


def test_local_tool_names_clears_not_dispatchable_on_audit_path():
    # x is tier-active and in the catalog; its ONLY dispatch route is the local
    # handler. With x in local_tool_names the LM2D audit must NOT flag
    # not_dispatchable; without it the false positive returns -> proves the
    # enrichment is load-bearing on reconcile_profile's audit path.
    definition = ProfileDefinition(name="p", initial_tier="agent_tier0")
    resolution = _resolution(definition, tool_names=("x",))
    catalog = {"x": _schema("x")}

    enriched = SurfaceSources(
        agent_tier0=frozenset({"x"}),
        local_tool_names=frozenset({"x"}),
    )
    rec = reconcile_profile(resolution, enriched, catalog)
    assert not any(
        f.code == "not_dispatchable" and f.tool == "x" for f in rec.registry_findings
    )

    bare = SurfaceSources(agent_tier0=frozenset({"x"}))
    rec_bare = reconcile_profile(resolution, bare, catalog)
    assert any(
        f.code == "not_dispatchable" and f.tool == "x" for f in rec_bare.registry_findings
    )
