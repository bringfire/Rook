"""Model-visible tool schema contract policy for RookChat.

This module normalizes and audits LiteLLM function schemas before they are
shown to chat models. It never executes tools and never calls Rhino.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from ..tool_dispatcher import STRICT_NO_ARGUMENT_BRIDGE_TOOLS
from .tool_result_view import ToolResultView, normalize_tool_result

ZERO_ARGUMENT_TOOLS: frozenset[str] = STRICT_NO_ARGUMENT_BRIDGE_TOOLS

ROOT_OPEN_ALLOWLIST: frozenset[str] = frozenset()

DYNAMIC_NESTED_OBJECT_ALLOWLIST: dict[str, set[tuple[str, ...]]] = {}


@dataclass(frozen=True)
class DispatchContext:
    intercepted_names: frozenset[str]
    local_tool_names: frozenset[str]
    transform_names: frozenset[str]
    bridge_names: frozenset[str]
    excluded_names: frozenset[str]
    strict_no_argument_names: frozenset[str]


@dataclass(frozen=True)
class DispatchabilityFinding:
    code: str
    tool: str
    classification: str
    message: str


def _is_object_schema(schema: dict[str, Any]) -> bool:
    return schema.get("type") == "object" or isinstance(schema.get("properties"), dict)


def closed_no_arg_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def _tool_name(schema: dict[str, Any]) -> str:
    function = schema.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        if isinstance(name, str):
            return name
    return ""


def _ensure_root_object(parameters: Any) -> dict[str, Any]:
    if not isinstance(parameters, dict):
        return closed_no_arg_parameters()
    normalized = deepcopy(parameters)
    normalized["type"] = "object"
    if not isinstance(normalized.get("properties"), dict):
        normalized["properties"] = {}
    return normalized


def _normalize_nested_object_schemas(
    tool_name: str,
    schema: dict[str, Any],
    path: tuple[str, ...] = (),
) -> dict[str, Any]:
    normalized = deepcopy(schema)
    allowlist = DYNAMIC_NESTED_OBJECT_ALLOWLIST.get(tool_name, set())

    if _is_object_schema(normalized) and path and path not in allowlist:
        normalized["type"] = "object"
        normalized["additionalProperties"] = False

    properties = normalized.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in list(properties.items()):
            if isinstance(prop_schema, dict):
                properties[prop_name] = _normalize_nested_object_schemas(
                    tool_name,
                    prop_schema,
                    (*path, prop_name),
                )

    items = normalized.get("items")
    if isinstance(items, dict):
        normalized["items"] = _normalize_nested_object_schemas(
            tool_name,
            items,
            (*path, "items"),
        )
    elif isinstance(items, list):
        normalized["items"] = [
            _normalize_nested_object_schemas(
                tool_name,
                item,
                (*path, "items", str(index)),
            )
            if isinstance(item, dict)
            else item
            for index, item in enumerate(items)
        ]

    for keyword in ("oneOf", "anyOf", "allOf"):
        entries = normalized.get(keyword)
        if isinstance(entries, list):
            normalized[keyword] = [
                _normalize_nested_object_schemas(
                    tool_name,
                    entry,
                    (*path, keyword, str(index)),
                )
                if isinstance(entry, dict)
                else entry
                for index, entry in enumerate(entries)
            ]

    return normalized


def normalize_litellm_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    normalized = deepcopy(schema)
    function = normalized.setdefault("function", {})
    if not isinstance(function, dict):
        normalized["function"] = function = {}

    name = _tool_name(normalized)
    if name in ZERO_ARGUMENT_TOOLS:
        function["parameters"] = closed_no_arg_parameters()
        description = function.get("description")
        suffix = " Takes no arguments."
        if isinstance(description, str):
            if "Takes no arguments" not in description:
                function["description"] = f"{description.rstrip()}{suffix}"
        else:
            function["description"] = "Takes no arguments."
        return normalized

    parameters = _ensure_root_object(function.get("parameters"))
    parameters["additionalProperties"] = False
    function["parameters"] = _normalize_nested_object_schemas(name, parameters)
    return normalized


def normalize_catalog(catalog: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        name: normalize_litellm_tool_schema(schema)
        for name, schema in catalog.items()
    }


def _schema_path(path: tuple[str, ...]) -> str:
    schema_keywords = {"items", "oneOf", "anyOf", "allOf"}
    parts: list[str] = ["function", "parameters"]
    for part in path:
        if part in schema_keywords or part.isdigit():
            parts.append(part)
        else:
            parts.extend(["properties", part])
    return ".".join(parts)


def _audit_nested_object_schemas(
    tool_name: str,
    schema: dict[str, Any],
    path: tuple[str, ...] = (),
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    allowlist = DYNAMIC_NESTED_OBJECT_ALLOWLIST.get(tool_name, set())

    if (
        _is_object_schema(schema)
        and path
        and path not in allowlist
        and schema.get("additionalProperties") is not False
    ):
        findings.append({
            "code": "open_nested_object",
            "tool": tool_name,
            "path": f"{_schema_path(path)}.additionalProperties",
            "message": (
                "Nested object allows arbitrary keys without an "
                "explicit allowlist entry."
            ),
        })

    properties = schema.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            if isinstance(prop_schema, dict):
                findings.extend(
                    _audit_nested_object_schemas(
                        tool_name,
                        prop_schema,
                        (*path, prop_name),
                    )
                )

    items = schema.get("items")
    if isinstance(items, dict):
        findings.extend(_audit_nested_object_schemas(tool_name, items, (*path, "items")))
    elif isinstance(items, list):
        for index, item in enumerate(items):
            if isinstance(item, dict):
                findings.extend(
                    _audit_nested_object_schemas(
                        tool_name,
                        item,
                        (*path, "items", str(index)),
                    )
                )

    for keyword in ("oneOf", "anyOf", "allOf"):
        entries = schema.get(keyword)
        if isinstance(entries, list):
            for index, entry in enumerate(entries):
                if isinstance(entry, dict):
                    findings.extend(
                        _audit_nested_object_schemas(
                            tool_name,
                            entry,
                            (*path, keyword, str(index)),
                        )
                    )

    return findings


def audit_litellm_tool_schema(schema: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    tool_name = _tool_name(schema)
    function = schema.get("function")
    parameters = function.get("parameters") if isinstance(function, dict) else None

    if not isinstance(parameters, dict):
        findings.append({
            "code": "missing_parameters",
            "tool": tool_name,
            "path": "function.parameters",
            "message": "Tool schema is missing an object parameters schema.",
        })
        return findings

    if (
        tool_name not in ROOT_OPEN_ALLOWLIST
        and parameters.get("additionalProperties") is not False
    ):
        findings.append({
            "code": "open_root_parameters",
            "tool": tool_name,
            "path": "function.parameters.additionalProperties",
            "message": "Root tool parameters allow arbitrary keys.",
        })

    findings.extend(_audit_nested_object_schemas(tool_name, parameters))
    return findings


def classify_visible_tool(tool_name: str, context: DispatchContext) -> str:
    """Classify a model-visible tool against structural dispatch surfaces.

    Internal-agent meta tools take precedence over ordinary dispatch surfaces.
    """
    if tool_name in context.intercepted_names:
        return "internal_agent_intercepted"
    if tool_name in context.local_tool_names:
        return "dispatcher_local_tool"
    if tool_name in context.transform_names:
        return "dispatcher_transform"
    if tool_name in context.bridge_names:
        return "bridge_route"
    if tool_name in context.excluded_names:
        return "explicitly_excluded"
    return "failure"


def _closed_empty_parameters(parameters: Any) -> bool:
    return parameters == closed_no_arg_parameters()


def _parameters_for_schema(schema: dict[str, Any]) -> Any:
    function = schema.get("function")
    if not isinstance(function, dict):
        return None
    return function.get("parameters")


def audit_visible_tool_dispatchability(
    schemas: Iterable[dict[str, Any]],
    context: DispatchContext,
) -> list[DispatchabilityFinding]:
    """Audit model-visible tools for structural dispatchability.

    This function only inspects schema names and static dispatch membership.
    It must not execute tools, call Rhino, or ask the MCP server to dispatch.
    """
    findings: list[DispatchabilityFinding] = []
    seen: set[str] = set()

    for schema in schemas:
        tool_name = _tool_name(schema)
        if not tool_name:
            findings.append(DispatchabilityFinding(
                code="missing_function_name",
                tool="",
                classification="schema",
                message="Visible tool schema is missing function.name.",
            ))
            continue

        if tool_name in seen:
            findings.append(DispatchabilityFinding(
                code="duplicate_visible_name",
                tool=tool_name,
                classification="schema",
                message=f"Tool '{tool_name}' is visible more than once.",
            ))
            continue
        seen.add(tool_name)

        classification = classify_visible_tool(tool_name, context)

        if tool_name in context.strict_no_argument_names:
            parameters = _parameters_for_schema(schema)
            if not _closed_empty_parameters(parameters):
                findings.append(DispatchabilityFinding(
                    code="strict_no_arg_schema_drift",
                    tool=tool_name,
                    classification=classification,
                    message=(
                        f"Strict no-argument tool '{tool_name}' does not expose "
                        "closed empty parameters."
                    ),
                ))

        if classification == "failure":
            findings.append(DispatchabilityFinding(
                code="not_dispatchable",
                tool=tool_name,
                classification=classification,
                message=(
                    f"Visible tool '{tool_name}' has no internal-agent intercept, "
                    "dispatcher local handler, transform function, bridge route, "
                    "or named exclusion."
                ),
            ))

    return findings
