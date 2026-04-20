"""Phase 2 surface/curve extension typed-route coverage audit.

Sibling of `test_capability_router_phase2_coverage.py` scoped to the
surface/curve extension campaign (Category 4 + Category 5 — 5 endpoints,
7 intent keys). Pins the invariant that every extension typed-route
intent is reachable across all four discoverability surfaces:

  1. MCP Tool registration   — rhino_<X> appears in list_tools()
  2. Executor routing        — `case "rhino_<X>":` exists in call_tool()
                                AND its body routes to the expected endpoint
                                (catches paste-error mismatches, per PR #61
                                Codex review)
  3. CapabilityRouter spec   — intent_runtime route table contains the intent
                                with the expected endpoint
  4. Category membership     — intent appears in the expected CATEGORIES bucket
                                (surface creators → "creation"; curve
                                creators → "curves")

Symmetric coverage-of-the-coverage at the bottom: the audit inventory is
verified against both the route table and the executor against the
campaign-scoped endpoint set — NOT the raw `/surface/*` / `/curve/*`
prefix, which would overcapture Phase 1 routes (`create_pipe`,
`create_loft`, etc.) and every pre-existing direct-sdk curve op
(`join_curves`, `explode_curve`, etc.) that pre-date this campaign.

The endpoint inventory is derived from the campaign tuple list itself
(see PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS below) so the audit remains
strictly scoped to the campaign's routes even though some share a
prefix with unrelated older routes. Follow-up route additions to either
namespace are picked up by extending the tuple list.

Runs as a pure unit test — no Rhino required, no network, no fixtures.

Adding a new Phase 2 surface/curve extension typed route? Append to
PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS below.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Canonical Phase 2 surface/curve extension typed-route inventory. Each
# tuple = (intent_key, mcp_tool_name, expected_endpoint, expected_category).
#
# This list IS the public contract of the audit. If a route is missing
# here, the audit cannot verify it.
#
# Note the three `curve_boolean_*` intents intentionally share the same
# `/curve/boolean` endpoint — they are dispatched by an `operation`
# discriminator (mirrors the Phase 1 brep-boolean pattern).
PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS: list[tuple[str, str, str, str]] = [
    # PR-1 worked example
    ("create_edge_srf",            "rhino_create_edge_srf",             "/surface/edge",    "creation"),
    ("blend_curves",               "rhino_blend_curves",                "/curve/blend",     "curves"),
    # PR-2
    ("create_patch",               "rhino_create_patch",                "/surface/patch",   "creation"),
    # PR-3
    ("create_network_srf",         "rhino_create_network_srf",          "/surface/network", "creation"),
    # PR-4 (three intents share /curve/boolean via operation discriminator)
    ("curve_boolean_union",        "rhino_curve_boolean_union",         "/curve/boolean",   "curves"),
    ("curve_boolean_difference",   "rhino_curve_boolean_difference",    "/curve/boolean",   "curves"),
    ("curve_boolean_intersection", "rhino_curve_boolean_intersection",  "/curve/boolean",   "curves"),
]


# Campaign endpoint set derived from the tuple list. NOT a prefix match —
# `/surface/*` and `/curve/*` contain many Phase 1 + pre-Phase-1 routes
# (create_pipe / create_loft / join_curves / explode_curve / etc.) that
# the symmetric coverage checks must NOT flag as uncovered.
PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS: frozenset[str] = frozenset(
    endpoint for _, _, endpoint, _ in PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS
)


# -- Surface accessors ------------------------------------------------------


def _server_py_source() -> str:
    mcp_server_root = Path(__file__).resolve().parents[1]
    server_py = mcp_server_root / "src" / "rook" / "server.py"
    return server_py.read_text(encoding="utf-8")


def _executor_case_labels(source: str) -> set[str]:
    return set(re.findall(r'^\s+case "([^"]+)":', source, flags=re.MULTILINE))


def _executor_simple_case_endpoints(source: str) -> dict[str, str]:
    """Map tool name → the first endpoint string in its case arm body.

    Strict regex match (per Phase 1 + Phase 2 audit pattern): catches
    case/endpoint paste-error mismatches where `case "rhino_X":` body
    calls `call_rhino("/wrong/endpoint", ...)`.

    The three `rhino_curve_boolean_*` tools inject the `operation` param
    via `{**arguments, "operation": "..."}` — this regex still matches
    because it looks at the first string literal in `call_rhino(...)`,
    which is the endpoint.
    """
    pattern = re.compile(
        r'case\s+"(rhino_[A-Za-z0-9_]+)"\s*:\s*\n'
        r'\s*result\s*=\s*await\s+call_rhino\(\s*"([^"]+)"',
        flags=re.MULTILINE,
    )
    return {tool_name: endpoint for tool_name, endpoint in pattern.findall(source)}


def _server_py_campaign_endpoints(source: str) -> set[str]:
    """Every call_rhino(<endpoint>, ...) invocation whose endpoint is in
    the campaign set. Used to derive the executor-side inventory for the
    symmetric coverage-of-coverage test.

    Intentionally NOT prefix-based (see module docstring).
    """
    pattern = re.compile(r'call_rhino\(\s*"([^"]+)"')
    all_endpoints = set(pattern.findall(source))
    return all_endpoints & PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS


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


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS)
@pytest.mark.asyncio
async def test_extension_intent_has_mcp_tool_registration(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 1: rhino_<X> appears in list_tools()."""
    registered = await _list_tools_names()
    assert tool_name in registered, (
        f"Intent {intent!r}: MCP tool {tool_name!r} is not registered in "
        f"list_tools(). Agents cannot discover this typed route."
    )


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS)
def test_extension_intent_has_executor_case_arm(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 2: `case "rhino_<X>":` in call_tool() routes to expected endpoint.

    Strict regex match catches paste-error mismatches between case label
    and call_rhino endpoint. Label-only check would silently pass when
    an agent invocation hits the wrong handler.

    For the three `curve_boolean_*` tools the regex matches the endpoint
    string (first literal in call_rhino(...)) — the operation-injection
    `{**arguments, "operation": "..."}` follows the endpoint and is not
    verified here. Operation-injection correctness is instead pinned by
    the live-Rhino tests (which assert the factory actually runs the
    requested operation).
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


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS)
def test_extension_intent_has_route_spec(
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


@pytest.mark.parametrize("intent,tool_name,endpoint,category", PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS)
def test_extension_intent_in_expected_category(
    intent: str, tool_name: str, endpoint: str, category: str
) -> None:
    """Surface 4: intent appears in its expected CATEGORIES bucket.

    Surface creators (EdgeSrf / Patch / NetworkSrf) → "creation".
    Curve factories (BlendCurve / CurveBoolean*) → "curves".
    Category-aware discovery (planner heuristics, explorer filters)
    depends on this.
    """
    categories = _categories()
    bucket = set(categories.get(category, ()))
    assert intent in bucket, (
        f"Intent {intent!r}: missing from CATEGORIES[{category!r}]. "
        f"Category-aware discovery would skip this intent.\n"
        f"To fix: add {intent!r} to the {category!r} tuple in "
        f"mcp_server/src/rook/learning/intent_runtime.py."
    )


# -- Coverage-of-the-coverage (bidirectional, campaign-scoped) --------------


def test_extension_inventory_covers_all_campaign_routes_in_route_table() -> None:
    """Every RouteSpec whose endpoint is in the campaign set must appear
    in PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS. Catches the case where
    a new extension typed route ships with a RouteSpec but isn't added
    to the audit.
    """
    routes = _route_table()
    inventory_intents = {entry[0] for entry in PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS}

    campaign_route_intents = {
        intent
        for intent, spec in routes.items()
        if spec.endpoint in PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS
    }

    missing_from_inventory = campaign_route_intents - inventory_intents
    assert not missing_from_inventory, (
        f"Route table contains Phase 2 surface/curve extension typed "
        f"routes not covered by the audit inventory: "
        f"{sorted(missing_from_inventory)}.\n"
        f"Add them to PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS so the "
        f"four-surface audit applies to them too."
    )


# -- Operation-injection pins for the three curve-boolean MCP tools -------
#
# Three `rhino_curve_boolean_*` tools share one endpoint with an
# `operation` discriminator. The injection fires on two surfaces:
#   1. MCP executor case arms in server.py (exercised by the live tests
#      `test_mcp_tool_curve_boolean_*_injects_*` in
#      test_curve_boolean_live.py via discriminating disjoint geometry)
#   2. Agent-direct TRANSFORM_FUNCTIONS in tool_dispatcher.py (pinned
#      here as pure unit — no Rhino required)
# A copy/paste mistake on either surface (e.g. `_difference -> "union"`)
# would be silent without these pins.


@pytest.mark.parametrize("tool_name,expected_operation", [
    ("rhino_curve_boolean_union",        "union"),
    ("rhino_curve_boolean_difference",   "difference"),
    ("rhino_curve_boolean_intersection", "intersection"),
])
def test_agent_transform_injects_correct_operation(
    tool_name: str, expected_operation: str
) -> None:
    """Unit pin: TRANSFORM_FUNCTIONS[tool] returns payload with the
    correct `operation` field. Catches copy/paste errors in the agent-
    direct injection surface (tool_dispatcher.py). Pure unit — no
    Rhino, no network.
    """
    from rook.agent.tool_dispatcher import TRANSFORM_FUNCTIONS

    assert tool_name in TRANSFORM_FUNCTIONS, (
        f"{tool_name!r} has no TRANSFORM_FUNCTIONS entry — agent-direct "
        f"path cannot dispatch it."
    )

    transform = TRANSFORM_FUNCTIONS[tool_name]
    endpoint, method, outgoing = transform({"curveIds": ["dummy1", "dummy2"]})

    assert endpoint == "/curve/boolean", (
        f"{tool_name!r}: transform returned wrong endpoint {endpoint!r}, "
        f"expected '/curve/boolean'."
    )
    assert method == "POST"
    assert outgoing.get("operation") == expected_operation, (
        f"{tool_name!r}: transform injected operation={outgoing.get('operation')!r}, "
        f"expected {expected_operation!r}. This is the exact copy/paste "
        f"mistake the pin exists to catch."
    )
    # Defensive: verify original argument keys survived.
    assert outgoing.get("curveIds") == ["dummy1", "dummy2"], (
        f"{tool_name!r}: transform mangled curveIds: {outgoing!r}"
    )


def test_extension_inventory_covers_all_executor_campaign_endpoints() -> None:
    """Every campaign endpoint appearing in a call_rhino() invocation in
    server.py must have a corresponding RouteSpec AND an inventory entry.
    Closes the symmetric drift window on the executor side.
    """
    source = _server_py_source()
    executor_endpoints = _server_py_campaign_endpoints(source)

    routes = _route_table()
    route_table_endpoints = {
        spec.endpoint
        for spec in routes.values()
        if spec.endpoint in PHASE2_SURFACE_CURVE_CAMPAIGN_ENDPOINTS
    }
    inventory_endpoints = {entry[2] for entry in PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS}

    missing_from_route_table = executor_endpoints - route_table_endpoints
    assert not missing_from_route_table, (
        f"Executor wires Phase 2 surface/curve extension endpoints that "
        f"have no CapabilityRouter RouteSpec: "
        f"{sorted(missing_from_route_table)}.\n"
        f"Agents invoking these via /intent would fall through to the "
        f"DSPy fallback. Add RouteSpec entries to intent_runtime.py."
    )

    missing_from_inventory = executor_endpoints - inventory_endpoints
    assert not missing_from_inventory, (
        f"Executor wires Phase 2 surface/curve extension endpoints that "
        f"aren't in the audit inventory: "
        f"{sorted(missing_from_inventory)}.\n"
        f"Add them to PHASE2_SURFACE_CURVE_TYPED_ROUTE_INTENTS."
    )
