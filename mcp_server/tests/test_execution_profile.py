from __future__ import annotations

import ast
from pathlib import Path

from rook.agent.capability_record import CapabilityInventory, CapabilityRecord
from rook.agent.execution_profile import (
    ProfileDefinition,
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
