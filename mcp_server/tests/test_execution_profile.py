from __future__ import annotations

import ast
from pathlib import Path

from rook.agent.capability_record import (
    CapabilityInventory,
    CapabilityRecord,
    SurfaceSources,
)
from rook.agent.capability_inventory import build_inventory
from rook.agent.execution_profile import (
    ProfileDefinition,
    default_profile_definitions,
    format_profile_report,
    readonly_excluded_mcp_only_groups,
    readonly_profile_from_sources,
    resolve_profile,
    resolve_profiles,
)


def _record(
    name: str,
    *,
    visibility: str = "local_visible",
    tiers: tuple[str, ...] = (),
    groups: tuple[str, ...] = (),
    dispatch_path: str | None = "bridge_route",
    has_schema: bool = True,
    risk: tuple[str, ...] = (),
    no_argument: bool = False,
    mcp_only: bool = False,
) -> CapabilityRecord:
    return CapabilityRecord(
        name=name,
        visibility=visibility,
        tiers=tiers,
        groups=groups,
        dispatch_path=dispatch_path,
        has_schema=has_schema,
        risk=risk,
        no_argument=no_argument,
        mcp_only=mcp_only,
    )


def _inventory() -> CapabilityInventory:
    return CapabilityInventory(
        records=(
            _record("good_local", tiers=("agent_tier0",), groups=("gh_canvas",)),
            _record("nodispatch_local", tiers=("agent_tier0",), dispatch_path=None),
            _record("noschema_local", tiers=("agent_tier0",), has_schema=False),
            _record(
                "mcp_tool",
                visibility="mcp_only_visible",
                groups=("gh_knowledge",),
                dispatch_path=None,
                mcp_only=True,
            ),
            _record("readonly_tool", tiers=("readonly_tier0",)),
        ),
        findings=(),
    )


def _finding_keys(resolution):
    return {(f.code, f.subject, f.severity) for f in resolution.findings}


def test_tier_expansion_resolves_tier_members():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="agent_tier0"), _inventory()
    )
    assert [r.name for r in res.tools] == [
        "good_local",
        "nodispatch_local",
        "noschema_local",
    ]


def test_group_expansion_resolves_group_members():
    res = resolve_profile(
        ProfileDefinition(name="p", groups=("gh_canvas",)), _inventory()
    )
    assert [r.name for r in res.tools] == ["good_local"]


def test_pins_are_additive_and_tool_names_sorted_deduped():
    res = resolve_profile(
        ProfileDefinition(
            name="p",
            initial_tier="readonly_tier0",
            tools=("readonly_tool", "good_local"),
        ),
        _inventory(),
    )
    assert res.tool_names == ("good_local", "readonly_tool")
    assert [r.name for r in res.tools] == ["good_local", "readonly_tool"]


def test_unknown_tier_warning():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="ghost_tier"),  # type: ignore[arg-type]
        _inventory(),
    )
    assert ("unknown_tier", "ghost_tier", "warning") in _finding_keys(res)


def test_unknown_group_warning():
    res = resolve_profile(
        ProfileDefinition(name="p", groups=("ghost_group",)), _inventory()
    )
    assert ("unknown_group", "ghost_group", "warning") in _finding_keys(res)


def test_unknown_tool_warning_keeps_pin_in_tool_names_not_tools():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="agent_tier0", tools=("ghost_tool",)),
        _inventory(),
    )
    assert ("unknown_tool", "ghost_tool", "warning") in _finding_keys(res)
    assert "ghost_tool" in res.tool_names
    assert "ghost_tool" not in {r.name for r in res.tools}


def test_mcp_only_tool_does_not_also_flag_not_dispatchable():
    res = resolve_profile(
        ProfileDefinition(name="p", groups=("gh_knowledge",)), _inventory()
    )
    codes = {(f.code, f.subject) for f in res.findings}
    assert ("mcp_only_tool", "mcp_tool") in codes
    assert ("not_dispatchable", "mcp_tool") not in codes


def test_not_dispatchable_error_for_local_visible_without_path():
    res = resolve_profile(
        ProfileDefinition(name="p", tools=("nodispatch_local",)), _inventory()
    )
    assert ("not_dispatchable", "nodispatch_local", "error") in _finding_keys(res)


def test_missing_schema_warning_for_local_visible_without_schema():
    res = resolve_profile(
        ProfileDefinition(name="p", tools=("noschema_local",)), _inventory()
    )
    assert ("missing_schema", "noschema_local", "warning") in _finding_keys(res)


def test_empty_profile_warning_when_no_known_tools():
    res = resolve_profile(ProfileDefinition(name="p"), _inventory())
    assert res.tools == ()
    assert ("empty_profile", "p", "warning") in _finding_keys(res)


def test_tools_sorted_and_findings_sorted_by_code_subject():
    res = resolve_profile(
        ProfileDefinition(name="p", initial_tier="agent_tier0"), _inventory()
    )
    names = [r.name for r in res.tools]
    assert names == sorted(names)
    finding_keys = [(f.code, f.subject) for f in res.findings]
    assert finding_keys == sorted(finding_keys)


def test_resolve_profiles_preserves_definition_order():
    defs = (
        ProfileDefinition(name="b", initial_tier="readonly_tier0"),
        ProfileDefinition(name="a", initial_tier="agent_tier0"),
    )
    results = resolve_profiles(defs, _inventory())
    assert [r.profile.name for r in results] == ["b", "a"]


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


def test_execution_profile_is_import_light():
    imports = _direct_import_modules(
        "mcp_server/src/rook/agent/execution_profile.py"
    )
    assert "rook.agent.capability_record" in imports
    assert "rook.agent.tool_groups" not in imports
    assert "rook.agent.tool_dispatcher" not in imports
    assert "rook.agent.tool_registry" not in imports
    assert "rook.agent.chat.tool_contracts" not in imports
    assert "rook.agent.capability_inventory" not in imports
    assert imports <= {
        "__future__",
        "dataclasses",
        "typing",
        "rook.agent.capability_record",
    }


def test_default_profile_definitions_are_tier_only_seeds():
    by_name = {d.name: d for d in default_profile_definitions()}
    assert set(by_name) == {"rookchat_local", "readonly"}
    assert by_name["rookchat_local"].initial_tier == "agent_tier0"
    assert by_name["rookchat_local"].groups == ()
    assert by_name["readonly"].initial_tier == "readonly_tier0"
    assert by_name["readonly"].groups == ()
    assert "planner" not in by_name
    assert "external_mcp" not in by_name


def test_default_profile_definitions_is_constant():
    assert default_profile_definitions() == default_profile_definitions()


def test_injected_planner_definition_resolves():
    res = resolve_profile(
        ProfileDefinition(name="planner", initial_tier="readonly_tier0"),
        _inventory(),
    )
    assert res.profile.name == "planner"
    assert [r.name for r in res.tools] == ["readonly_tool"]


def test_format_profile_report_is_pure_and_stable():
    results = resolve_profiles(default_profile_definitions(), _inventory())
    first = format_profile_report(results)
    second = format_profile_report(results)
    assert first == second
    assert "Profile rookchat_local:" in first
    assert "Profile readonly:" in first


def test_readonly_profile_excludes_mcp_only_and_undefined_groups():
    sources = SurfaceSources(
        groups={"a": ("ta",), "b": ("tb",), "gh_knowledge": ("tk",)},
        mcp_only_groups=frozenset({"gh_knowledge"}),
        readonly_allowed_groups=frozenset({"a", "b", "gh_knowledge", "ghost_group"}),
    )
    profile = readonly_profile_from_sources(sources)
    assert profile.name == "readonly"
    assert profile.initial_tier == "readonly_tier0"
    # gh_knowledge dropped (MCP-only); ghost_group dropped (no definition).
    assert profile.groups == ("a", "b")


def test_readonly_profile_groups_are_sorted():
    sources = SurfaceSources(
        groups={"z": ("tz",), "a": ("ta",), "m": ("tm",)},
        readonly_allowed_groups=frozenset({"z", "a", "m"}),
    )
    assert readonly_profile_from_sources(sources).groups == ("a", "m", "z")


def test_readonly_profile_empty_evidence_degrades_to_tier_only():
    profile = readonly_profile_from_sources(SurfaceSources())
    assert profile.groups == ()
    assert profile.initial_tier == "readonly_tier0"


def test_readonly_excluded_mcp_only_groups_synthetic():
    sources = SurfaceSources(
        groups={"a": ("ta",), "gh_knowledge": ("tk",)},
        mcp_only_groups=frozenset({"gh_knowledge"}),
        readonly_allowed_groups=frozenset({"a", "gh_knowledge"}),
    )
    assert readonly_excluded_mcp_only_groups(sources) == ("gh_knowledge",)


def test_readonly_excluded_mcp_only_groups_real_constants_pin():
    from rook.agent.tool_groups import MCP_ONLY_GROUPS, READONLY_ALLOWED_GROUPS

    sources = SurfaceSources(
        mcp_only_groups=frozenset(MCP_ONLY_GROUPS),
        readonly_allowed_groups=frozenset(READONLY_ALLOWED_GROUPS),
    )
    assert readonly_excluded_mcp_only_groups(sources) == (
        "gh_exploration",
        "gh_knowledge",
        "gh_validation",
    )


def test_readonly_seed_resolves_locally_executable_no_mcp_only_findings():
    # One readonly-allowed non-MCP group with a local-visible, dispatchable,
    # schema-backed tool; one readonly-allowed MCP-only group. Small deterministic
    # fixture -- no live catalog.
    sources = SurfaceSources(
        readonly_tier0=frozenset({"ro_tool_local"}),
        groups={"ro_local": ("ro_tool_local",), "ro_mcp": ("ro_tool_mcp",)},
        mcp_only_groups=frozenset({"ro_mcp"}),
        readonly_allowed_groups=frozenset({"ro_local", "ro_mcp"}),
        bridge_names=frozenset({"ro_tool_local"}),
    )
    catalog = {
        "ro_tool_local": {
            "type": "function",
            "function": {
                "name": "ro_tool_local",
                "description": "ro_tool_local",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        }
    }

    profile = readonly_profile_from_sources(sources)
    assert profile.groups == ("ro_local",)  # ro_mcp excluded

    inventory = build_inventory(sources, catalog)
    res = resolve_profile(profile, inventory)

    assert "ro_tool_mcp" not in res.tool_names
    assert not any(f.code == "mcp_only_tool" for f in res.findings)
