from __future__ import annotations

from typing import Iterable

from rook.agent.chat.chat_runner import (
    _CHAT_MODEL_TOOL_SCHEMAS,
    _build_fallback_catalog,
    _build_local_tool_catalog,
)
from rook.agent.chat.tool_contracts import (
    DispatchContext,
    audit_visible_tool_dispatchability,
    normalize_litellm_tool_schema,
)
from rook.agent.tool_dispatcher import (
    BRIDGE_ROUTES,
    STRICT_NO_ARGUMENT_BRIDGE_TOOLS,
    TRANSFORM_FUNCTIONS,
    build_local_tools,
)
from rook.agent.tool_groups import AGENT_TIER_0, READONLY_TIER_0, TOOL_GROUPS
from rook.agent.tool_registry import ToolRegistry


CHAT_MODEL_TIER0 = frozenset({"list_chat_models", "set_chat_model"})
CHATRUNNER_INTERCEPTED = frozenset({
    "request_tools",
    "search_tools",
    "ui_block",
    "list_chat_models",
    "set_chat_model",
})
GH_CANVAS_SENTINELS = frozenset({
    "gh_create_script",
    "gh_create_csharp_script",
    "gh_update_script",
    "gh_set_script",
    "gh_inspect_output",
})


def _stub_schema(name: str) -> dict:
    return normalize_litellm_tool_schema({
        "type": "function",
        "function": {
            "name": name,
            "description": f"Synthetic cached schema for {name}",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    })


def _fallback_local_catalog(extra_names: Iterable[str] = ()) -> dict[str, dict]:
    catalog = _build_fallback_catalog()
    catalog.update(_build_local_tool_catalog(build_local_tools()))
    catalog.update(_CHAT_MODEL_TOOL_SCHEMAS)
    for name in extra_names:
        catalog.setdefault(name, _stub_schema(name))
    return catalog


def _dispatch_context() -> DispatchContext:
    return DispatchContext(
        intercepted_names=CHATRUNNER_INTERCEPTED,
        local_tool_names=frozenset(build_local_tools().keys()),
        transform_names=frozenset(TRANSFORM_FUNCTIONS.keys()),
        bridge_names=frozenset(BRIDGE_ROUTES.keys()),
        excluded_names=frozenset(),
        strict_no_argument_names=STRICT_NO_ARGUMENT_BRIDGE_TOOLS,
    )


def _registry(catalog: dict[str, dict], tier0: set[str]) -> ToolRegistry:
    return ToolRegistry(
        catalog=catalog,
        tier0=set(tier0) | set(CHAT_MODEL_TIER0),
        agent_mode=True,
    )


def _active_schema_names(schemas: list[dict]) -> set[str]:
    names: set[str] = set()
    for schema in schemas:
        function = schema.get("function")
        if isinstance(function, dict):
            name = function.get("name")
            if isinstance(name, str):
                names.add(name)
    return names


def _assert_no_dispatchability_findings(schemas: list[dict]) -> None:
    findings = audit_visible_tool_dispatchability(schemas, _dispatch_context())
    assert findings == []


def test_dispatchability_audit_reports_malformed_duplicate_missing_and_no_arg_drift():
    context = DispatchContext(
        intercepted_names=frozenset(),
        local_tool_names=frozenset({"local_ok"}),
        transform_names=frozenset(),
        bridge_names=frozenset(),
        excluded_names=frozenset(),
        strict_no_argument_names=frozenset({"strict_zero"}),
    )
    schemas = [
        {
            "type": "function",
            "function": {
                "description": "Missing name",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
            },
        },
        _stub_schema("local_ok"),
        _stub_schema("local_ok"),
        _stub_schema("missing_tool"),
        {
            "type": "function",
            "function": {
                "name": "strict_zero",
                "description": "No-arg tool with drifted params",
                "parameters": {
                    "type": "object",
                    "properties": {"unexpected": {"type": "string"}},
                    "additionalProperties": False,
                },
            },
        },
    ]

    findings = audit_visible_tool_dispatchability(schemas, context)

    assert any(f.code == "missing_function_name" for f in findings)
    assert any(
        f.code == "duplicate_visible_name" and f.tool == "local_ok"
        for f in findings
    )
    assert any(
        f.code == "not_dispatchable" and f.tool == "missing_tool"
        for f in findings
    )
    assert any(
        f.code == "strict_no_arg_schema_drift" and f.tool == "strict_zero"
        for f in findings
    )


def test_default_local_initial_visible_tools_are_dispatchable_with_fallback_catalog():
    registry = _registry(_fallback_local_catalog(), AGENT_TIER_0)

    _assert_no_dispatchability_findings(registry.get_active_schemas())


def test_default_local_initial_visible_tools_are_dispatchable_with_synthetic_cached_catalog():
    extra_names = set(AGENT_TIER_0) | set(CHAT_MODEL_TIER0)
    registry = _registry(_fallback_local_catalog(extra_names), AGENT_TIER_0)

    _assert_no_dispatchability_findings(registry.get_active_schemas())


def test_default_local_gh_canvas_visible_tools_are_dispatchable_with_synthetic_cached_catalog():
    extra_names = set(AGENT_TIER_0) | set(TOOL_GROUPS["gh_canvas"]) | set(CHAT_MODEL_TIER0)
    registry = _registry(_fallback_local_catalog(extra_names), AGENT_TIER_0)

    result = registry.request_group("gh_canvas", turn=1)
    assert result["success"] is True
    schemas = registry.get_active_schemas()
    active_names = _active_schema_names(schemas)

    assert GH_CANVAS_SENTINELS <= active_names
    assert GH_CANVAS_SENTINELS - set(AGENT_TIER_0)
    _assert_no_dispatchability_findings(schemas)


def test_readonly_initial_visible_tools_are_dispatchable_with_synthetic_cached_catalog():
    extra_names = set(READONLY_TIER_0) | set(CHAT_MODEL_TIER0)
    registry = _registry(_fallback_local_catalog(extra_names), READONLY_TIER_0)

    _assert_no_dispatchability_findings(registry.get_active_schemas())
