"""Phase 2 typed-route coverage audit (closes plan §Campaign exit criterion).

Mirror of `test_capability_router_phase1_coverage.py` applied to Phase 2.
Pins the invariant that every Phase 2 typed-route intent is reachable
across all four discoverability surfaces:

  1. MCP Tool registration   — rhino_<X> appears in list_tools()
  2. Executor routing        — `case "rhino_<X>":` exists in call_tool()
                                AND its body routes to the expected endpoint
                                (catches paste-error mismatches, per PR #61
                                Codex review)
  3. CapabilityRouter spec   — intent_runtime route table contains the intent
                                with the expected endpoint
  4. Category membership     — intent appears in the expected CATEGORIES bucket
                                (annotation family → "creation", user-text
                                family → "user_text")

Symmetric coverage-of-the-coverage at the bottom: the audit inventory is
verified against both the route table (a RouteSpec without an inventory
entry fails) and the executor (an endpoint wired in server.py without a
RouteSpec or inventory entry fails). Closes the bidirectional drift
window Codex flagged on PR #61.

Additive `/select` shape (PR-0) reciprocity: pinned as a pair of checks
that BOTH the legacy (`namePattern`, flat `bboxMin`/`bboxMax`) and the
new (`name` exact, nested `bbox:{min,max}`) shapes are documented in the
MCP tool description — the contract change is ADDITIVE, and the
inventory must reflect both shapes.

Runs as a pure unit test — no Rhino required, no network, no fixtures.

Adding a new Phase 2 typed route? Append to PHASE2_TYPED_ROUTE_INTENTS.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Canonical Phase 2 typed-route inventory. Each tuple =
# (intent_key, mcp_tool_name, expected_endpoint, expected_category).
#
# This list IS the public contract of the audit. If a Phase 2 route is
# missing here, the audit cannot verify it.
PHASE2_TYPED_ROUTE_INTENTS: list[tuple[str, str, str, str]] = [
    # Annotation family (PR-1 through PR-7)
    ("create_text",         "rhino_annotation_text",         "/annotation/text",         "creation"),
    ("create_dim_linear",   "rhino_annotation_dim_linear",   "/annotation/dim-linear",   "creation"),
    ("create_dim_aligned",  "rhino_annotation_dim_aligned",  "/annotation/dim-aligned",  "creation"),
    ("create_dim_radius",   "rhino_annotation_dim_radius",   "/annotation/dim-radius",   "creation"),
    ("create_dim_diameter", "rhino_annotation_dim_diameter", "/annotation/dim-diameter", "creation"),
    ("create_dim_angle",    "rhino_annotation_dim_angle",    "/annotation/dim-angle",    "creation"),
    ("create_leader",       "rhino_annotation_leader",       "/annotation/leader",       "creation"),
    ("create_dot",          "rhino_annotation_dot",          "/annotation/dot",          "creation"),
    # User-text family (PR-9 object-level; PR-10 document-level)
    ("set_object_user_strings",   "rhino_usertext_object_set",   "/usertext/object-set",   "user_text"),
    ("get_object_user_strings",   "rhino_usertext_object_get",   "/usertext/object-get",   "user_text"),
    ("set_document_user_strings", "rhino_usertext_document_set", "/usertext/document-set", "user_text"),
    ("get_document_user_strings", "rhino_usertext_document_get", "/usertext/document-get", "user_text"),
]


# Phase 2 typed-route endpoint prefixes used by the symmetric
# coverage-of-coverage tests to derive inventories from source.
PHASE2_ENDPOINT_PREFIXES = ("/annotation/", "/usertext/")


# -- Surface accessors ------------------------------------------------------


def _server_py_source() -> str:
    mcp_server_root = Path(__file__).resolve().parents[1]
    server_py = mcp_server_root / "src" / "rook" / "server.py"
    return server_py.read_text(encoding="utf-8")


def _executor_case_labels(source: str) -> set[str]:
    return set(re.findall(r'^\s+case "([^"]+)":', source, flags=re.MULTILINE))


def _executor_simple_case_endpoints(source: str) -> dict[str, str]:
    """Same strict regex as the Phase 1 audit — catches case/endpoint
    paste-error mismatches where `case "rhino_X":` body calls
    `call_rhino("/wrong/endpoint", ...)`.
    """
    pattern = re.compile(
        r'case\s+"(rhino_[A-Za-z0-9_]+)"\s*:\s*\n'
        r'\s*result\s*=\s*await\s+call_rhino\(\s*"([^"]+)"',
        flags=re.MULTILINE,
    )
    return {tool_name: endpoint for tool_name, endpoint in pattern.findall(source)}


def _server_py_typed_endpoints(source: str) -> set[str]:
    """All /annotation/* and /usertext/* endpoints in any call_rhino(...)
    invocation. Used to derive the executor-side inventory for the
    symmetric coverage-of-coverage test.
    """
    pattern = re.compile(
        r'call_rhino\(\s*"(/(?:annotation|usertext)/[^"]+)"'
    )
    return set(pattern.findall(source))


async def _list_tools_names() -> set[str]:
    from rook.server import list_tools
    tools = await list_tools()
    return {tool.name for tool in tools}


async def _find_tool(tool_name: str):
    from rook.server import list_tools
    for tool in await list_tools():
        if tool.name == tool_name:
            return tool
    return None


def _route_table() -> dict:
    from rook.learning.intent_runtime import _build_route_table
    return _build_route_table()


def _categories() -> dict[str, tuple[str, ...]]:
    from rook.learning.intent_runtime import CATEGORIES
    return CATEGORIES


# -- Per-surface audits -----------------------------------------------------


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_TYPED_ROUTE_INTENTS)
@pytest.mark.asyncio
async def test_phase2_intent_has_mcp_tool_registration(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 1: rhino_<X> appears in list_tools()."""
    registered = await _list_tools_names()
    assert tool_name in registered, (
        f"Intent {intent!r}: MCP tool {tool_name!r} is not registered in "
        f"list_tools(). Agents cannot discover this typed route."
    )


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_TYPED_ROUTE_INTENTS)
def test_phase2_intent_has_executor_case_arm(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 2: `case "rhino_<X>":` in call_tool() routes to expected endpoint.

    Strict regex match (per Codex PR-10 review directive + PR #61 Codex
    review): catches paste-error mismatches between case label and
    call_rhino endpoint. Label-only check would silently pass when an
    agent invocation hits the wrong handler.
    """
    source = _server_py_source()
    labels = _executor_case_labels(source)
    assert tool_name in labels, (
        f"Intent {intent!r}: tool {tool_name!r} has no executor case arm. "
        f"Agent invocations would hit the default branch."
    )

    routed = _executor_simple_case_endpoints(source)
    assert tool_name in routed, (
        f"Intent {intent!r}: tool {tool_name!r} has a case arm but its body "
        f"does not match the expected simple shape\n"
        f"  case \"{tool_name}\":\n"
        f"      result = await call_rhino(\"<endpoint>\", ...)"
    )

    actual_endpoint = routed[tool_name]
    assert actual_endpoint == endpoint, (
        f"Intent {intent!r}: executor case arm routes to the wrong endpoint.\n"
        f"  case label: {tool_name!r}\n"
        f"  expected:   call_rhino({endpoint!r}, ...)\n"
        f"  actual:     call_rhino({actual_endpoint!r}, ...)"
    )


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_TYPED_ROUTE_INTENTS)
def test_phase2_intent_has_route_spec(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 3: RouteSpec for the intent exists with the expected endpoint."""
    routes = _route_table()
    assert intent in routes, (
        f"Intent {intent!r}: missing from CapabilityRouter route table. "
        f"`/intent` calls would fall through to DSPy command-string fallback."
    )

    actual_endpoint = routes[intent].endpoint
    assert actual_endpoint == endpoint, (
        f"Intent {intent!r}: RouteSpec endpoint mismatch.\n"
        f"  expected: {endpoint!r}\n"
        f"  actual:   {actual_endpoint!r}"
    )


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_TYPED_ROUTE_INTENTS)
def test_phase2_intent_in_expected_category(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 4: intent appears in its expected CATEGORIES bucket.

    Annotation family → "creation" (backfilled in PR-10 — prior annotation
    PRs did not wire category membership). User-text family → "user_text"
    (new category introduced by PR-9, extended by PR-10). Category-aware
    discovery (planner heuristics, explorer filters) depends on this.
    """
    categories = _categories()
    bucket = set(categories.get(category, ()))
    assert intent in bucket, (
        f"Intent {intent!r}: missing from CATEGORIES[{category!r}]. "
        f"Category-aware discovery would skip this intent.\n"
        f"To fix: add {intent!r} to the {category!r} tuple in "
        f"mcp_server/src/rook/learning/intent_runtime.py."
    )


# -- Coverage-of-the-coverage (bidirectional) -------------------------------


def test_phase2_inventory_covers_all_typed_routes_in_route_table() -> None:
    """Every RouteSpec with an /annotation/* or /usertext/* endpoint must
    appear in PHASE2_TYPED_ROUTE_INTENTS. Catches the case where a new
    typed route ships with a RouteSpec but isn't added to the audit.
    """
    routes = _route_table()
    inventory_intents = {entry[0] for entry in PHASE2_TYPED_ROUTE_INTENTS}

    typed_route_intents_in_table = {
        intent
        for intent, spec in routes.items()
        if spec.endpoint.startswith(PHASE2_ENDPOINT_PREFIXES)
    }

    missing_from_inventory = typed_route_intents_in_table - inventory_intents
    assert not missing_from_inventory, (
        f"Route table contains Phase 2 typed routes not covered by the "
        f"audit inventory: {sorted(missing_from_inventory)}.\n"
        f"Add them to PHASE2_TYPED_ROUTE_INTENTS so the four-surface audit "
        f"applies to them too."
    )


def test_phase2_inventory_covers_all_executor_typed_endpoints() -> None:
    """Every /annotation/* or /usertext/* endpoint appearing in a
    call_rhino() invocation in server.py must have a corresponding
    RouteSpec AND an inventory entry. Closes the symmetric drift window
    on the executor side.
    """
    source = _server_py_source()
    executor_endpoints = _server_py_typed_endpoints(source)

    routes = _route_table()
    route_table_endpoints = {
        spec.endpoint
        for spec in routes.values()
        if spec.endpoint.startswith(PHASE2_ENDPOINT_PREFIXES)
    }
    inventory_endpoints = {entry[2] for entry in PHASE2_TYPED_ROUTE_INTENTS}

    missing_from_route_table = executor_endpoints - route_table_endpoints
    assert not missing_from_route_table, (
        f"Executor wires Phase 2 typed endpoints that have no "
        f"CapabilityRouter RouteSpec: {sorted(missing_from_route_table)}.\n"
        f"Agents invoking these via /intent would fall through to the DSPy "
        f"fallback. Add RouteSpec entries to intent_runtime.py."
    )

    missing_from_inventory = executor_endpoints - inventory_endpoints
    assert not missing_from_inventory, (
        f"Executor wires Phase 2 typed endpoints that aren't in the audit "
        f"inventory: {sorted(missing_from_inventory)}.\n"
        f"Add them to PHASE2_TYPED_ROUTE_INTENTS."
    )


# -- Additive /select shape reciprocity (PR-0) -----------------------------
#
# Pins that BOTH the legacy + new /select predicates are documented in the
# MCP tool description. The contract is ADDITIVE by design (legacy callers
# continue to work); the inventory must reflect both shapes.


@pytest.mark.asyncio
async def test_select_tool_documents_legacy_shape() -> None:
    """Legacy /select shape (namePattern + flat bboxMin/bboxMax) must be
    present in the rhino_select MCP tool description. Pre-PR-0 callers
    depend on this surface; PR-0 was additive, not a replacement.
    """
    tool = await _find_tool("rhino_select")
    assert tool is not None, "rhino_select tool must be registered"
    desc = tool.description or ""
    schema_props = (tool.inputSchema or {}).get("properties", {}) or {}

    # Legacy predicate names advertised either in the description OR as
    # schema properties.
    legacy_names = ("namePattern", "bboxMin", "bboxMax")
    for name in legacy_names:
        assert (name in desc) or (name in schema_props), (
            f"Legacy /select field {name!r} is not advertised in the "
            f"rhino_select tool description OR schema properties. "
            f"PR-0 contract is ADDITIVE — the legacy shape must remain "
            f"documented."
        )


@pytest.mark.asyncio
async def test_select_tool_documents_additive_shape() -> None:
    """Additive /select shape (exact `name` + nested `bbox:{min,max}`)
    from PR #62 must be present in the rhino_select MCP tool description.
    This is the router-advertised shape agents plan against.
    """
    tool = await _find_tool("rhino_select")
    assert tool is not None, "rhino_select tool must be registered"
    desc = tool.description or ""
    schema_props = (tool.inputSchema or {}).get("properties", {}) or {}

    # `name` as an exact-match predicate and nested `bbox` object must
    # both be advertised.
    for field in ("name", "bbox"):
        assert (field in desc) or (field in schema_props), (
            f"Additive /select field {field!r} is not advertised in the "
            f"rhino_select tool description OR schema properties. PR-0 "
            f"added this surface; agents planning against the router need "
            f"to discover it."
        )
