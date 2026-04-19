"""Phase 1 typed-route coverage audit (closes plan §Exit criterion 7).

Pins the invariant that every Phase 1 typed-route intent is reachable across
all four discoverability surfaces:

  1. MCP Tool registration   — rhino_<X> appears in list_tools()
  2. Executor routing        — `case "rhino_<X>":` exists in call_tool()
  3. CapabilityRouter spec   — intent_runtime route table contains the intent
                                with the expected endpoint
  4. Category membership     — intent appears in CATEGORIES["creation"]

A discoverability gap on any one surface (e.g. tool registered but no executor
arm, or RouteSpec without category) means an agent's invocation either fails
to find the tool, fails to route, fails to plan, or falls through to the
DSPy/command-string fallback. The narrower "intent is in the route table"
check would still pass in those cases.

This audit runs as a pure unit test — no Rhino required, no network, no
fixtures. It MUST stay green after every Phase 1 change.

Adding a new typed route? Append to PHASE1_TYPED_ROUTE_INTENTS below — the
parametrized tests will exercise the four surfaces automatically.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


# Canonical Phase 1 typed-route inventory. Each tuple = (intent_key,
# mcp_tool_name, expected_endpoint).
#
# This list IS the public contract of the audit. If a Phase 1 route is
# missing here, the audit cannot verify it. Add new entries as Phase 2+
# routes ship.
PHASE1_TYPED_ROUTE_INTENTS: list[tuple[str, str, str]] = [
    # Surface family (PR-1 through PR-4)
    ("create_pipe",     "rhino_create_pipe",     "/surface/pipe"),
    ("create_loft",     "rhino_create_loft",     "/surface/loft"),
    ("create_sweep1",   "rhino_create_sweep1",   "/surface/sweep1"),
    ("create_sweep2",   "rhino_create_sweep2",   "/surface/sweep2"),
    ("create_revolve",  "rhino_create_revolve",  "/surface/revolve"),
    # Array family (PR-5 + PR-6)
    ("array_linear",       "rhino_array_linear",       "/array/linear"),
    ("array_rectangular",  "rhino_array_rectangular",  "/array/rectangular"),
    ("array_polar",        "rhino_array_polar",        "/array/polar"),
]


# -- Surface accessors ------------------------------------------------------


def _server_py_source() -> str:
    """Read mcp_server/src/rook/server.py as text once per session.

    parents[0] = mcp_server/tests; parents[1] = mcp_server. The source
    sits at mcp_server/src/rook/server.py.
    """
    mcp_server_root = Path(__file__).resolve().parents[1]
    server_py = mcp_server_root / "src" / "rook" / "server.py"
    return server_py.read_text(encoding="utf-8")


def _executor_case_labels(source: str) -> set[str]:
    """All `case "<name>":` labels inside the call_tool match statement.

    Implementation: regex over the full file. The match block is the only
    place in server.py that uses `case "...":` syntax, so this is unambiguous
    without AST parsing. If that ever changes, narrow this to the call_tool
    function body.
    """
    return set(re.findall(r'^\s+case "([^"]+)":', source, flags=re.MULTILINE))


def _executor_simple_case_endpoints(source: str) -> dict[str, str]:
    """Pairs of (tool_name, call_rhino endpoint) for the simple case-arm
    pattern used by every Phase 1 typed-route arm:

        case "rhino_<X>":
            result = await call_rhino("<endpoint>", ...)

    Complex arms that wrap call_rhino with argument munging (e.g.
    rhino_boolean, rhino_extrude) won't match this pattern and won't appear
    in the result dict. That's acceptable — the audit only needs to pin the
    simple typed-route arms used by all 8 Phase 1 intents, and any future
    complex arm that wants the assertion can be refactored to call a small
    helper that the regex covers.

    Catches: case-label-vs-endpoint mismatch (e.g. somebody pastes
    `case "rhino_array_polar":` followed by `call_rhino("/array/linear", ...)`).
    Without this check, the label-presence test passes while the agent
    invokes the wrong route.
    """
    pattern = re.compile(
        r'case\s+"(rhino_[A-Za-z0-9_]+)"\s*:\s*\n'
        r'\s*result\s*=\s*await\s+call_rhino\(\s*"([^"]+)"',
        flags=re.MULTILINE,
    )
    return {tool_name: endpoint for tool_name, endpoint in pattern.findall(source)}


def _server_py_typed_endpoints(source: str) -> set[str]:
    """All /surface/* and /array/* endpoint strings appearing in any
    call_rhino(...) call in server.py. Used by the coverage-of-coverage
    test to catch a typed route that's wired in the executor but never
    given a RouteSpec.
    """
    pattern = re.compile(r'call_rhino\(\s*"(/(?:surface|array)/[^"]+)"')
    return set(pattern.findall(source))


async def _list_tools_names() -> set[str]:
    """Names of all MCP tools registered via the @mcp.list_tools() handler."""
    from rook.server import list_tools

    tools = await list_tools()
    return {tool.name for tool in tools}


def _route_table() -> dict:
    """The CapabilityRouter route-spec table."""
    from rook.learning.intent_runtime import _build_route_table

    return _build_route_table()


def _categories() -> dict[str, tuple[str, ...]]:
    from rook.learning.intent_runtime import CATEGORIES

    return CATEGORIES


# -- Per-surface audits -----------------------------------------------------


@pytest.mark.parametrize("intent,tool_name,endpoint", PHASE1_TYPED_ROUTE_INTENTS)
@pytest.mark.asyncio
async def test_phase1_intent_has_mcp_tool_registration(
    intent: str, tool_name: str, endpoint: str
) -> None:
    """Surface 1: rhino_<X> appears in the @mcp.list_tools() output.

    Failure mode caught: tool defined but missing from the registered list
    (e.g. accidentally inside a different conditional branch, indentation
    bug, missed paste).
    """
    registered = await _list_tools_names()
    assert tool_name in registered, (
        f"Intent {intent!r}: MCP tool {tool_name!r} is not registered in "
        f"list_tools(). Agents cannot discover this typed route.\n"
        f"Registered tools (sample): {sorted(registered)[:5]}..."
    )


@pytest.mark.parametrize("intent,tool_name,endpoint", PHASE1_TYPED_ROUTE_INTENTS)
def test_phase1_intent_has_executor_case_arm(
    intent: str, tool_name: str, endpoint: str
) -> None:
    """Surface 2: `case "rhino_<X>":` exists in the call_tool match block
    AND its body routes to the expected endpoint.

    Failure modes caught:
    - Tool registered but no executor routing — invocation falls into the
      default case and returns "Unknown tool" or similar.
    - Case label exists but routes to the wrong endpoint (e.g. paste error
      where `case "rhino_array_polar":` body calls `call_rhino("/array/linear", ...)`).
      The label-only check would pass; an agent would silently invoke the
      wrong route. Per Codex review of PR #61.
    """
    source = _server_py_source()
    labels = _executor_case_labels(source)
    assert tool_name in labels, (
        f"Intent {intent!r}: tool {tool_name!r} has no executor case arm. "
        f"Agent invocations would hit the default branch.\n"
        f"To fix: add `case \"{tool_name}\":` to call_tool() routing the "
        f"call to {endpoint!r}."
    )

    routed = _executor_simple_case_endpoints(source)
    assert tool_name in routed, (
        f"Intent {intent!r}: tool {tool_name!r} has a case arm but its body "
        f"does not match the expected simple shape\n"
        f"  case \"{tool_name}\":\n"
        f"      result = await call_rhino(\"<endpoint>\", ...)\n"
        f"If the arm has been wrapped with argument munging or other logic, "
        f"refactor the call_rhino invocation into a recognizable shape so "
        f"this audit can verify endpoint routing."
    )

    actual_endpoint = routed[tool_name]
    assert actual_endpoint == endpoint, (
        f"Intent {intent!r}: executor case arm routes to the wrong endpoint.\n"
        f"  case label: {tool_name!r}\n"
        f"  expected:   call_rhino({endpoint!r}, ...)\n"
        f"  actual:     call_rhino({actual_endpoint!r}, ...)\n"
        f"An agent invoking this tool would hit the wrong handler. Likely "
        f"a paste error or refactor that swapped endpoints."
    )


@pytest.mark.parametrize("intent,tool_name,endpoint", PHASE1_TYPED_ROUTE_INTENTS)
def test_phase1_intent_has_route_spec(
    intent: str, tool_name: str, endpoint: str
) -> None:
    """Surface 3: RouteSpec for the intent exists with the expected endpoint.

    Failure mode caught: intent not in the CapabilityRouter table, so
    /intent invocations fall through to DSPy resolution (the slow,
    keyword-gated fallback path). The whole point of typed routes is to
    take this branch.
    """
    routes = _route_table()
    assert intent in routes, (
        f"Intent {intent!r}: missing from CapabilityRouter route table. "
        f"`/intent` calls would fall through to DSPy command-string fallback "
        f"instead of routing to the typed endpoint."
    )

    actual_endpoint = routes[intent].endpoint
    assert actual_endpoint == endpoint, (
        f"Intent {intent!r}: RouteSpec endpoint mismatch.\n"
        f"  expected: {endpoint!r}\n"
        f"  actual:   {actual_endpoint!r}\n"
        f"This means the agent would call the wrong endpoint when planning "
        f"with this intent."
    )


@pytest.mark.parametrize("intent,tool_name,endpoint", PHASE1_TYPED_ROUTE_INTENTS)
def test_phase1_intent_in_creation_category(
    intent: str, tool_name: str, endpoint: str
) -> None:
    """Surface 4: intent appears in CATEGORIES["creation"].

    Failure mode caught: RouteSpec exists but the intent is not classified
    under any category, so explorer / planner heuristics that filter by
    category miss it. All 8 Phase 1 typed routes are creation-class
    operations (creators or mutation-class array creators); none belong
    to other categories.
    """
    categories = _categories()
    creation = set(categories.get("creation", ()))
    assert intent in creation, (
        f"Intent {intent!r}: missing from CATEGORIES['creation']. "
        f"Category-aware discovery (planner heuristics, explorer filters) "
        f"would skip this intent.\n"
        f"To fix: add {intent!r} to the creation tuple in "
        f"mcp_server/src/rook/learning/intent_runtime.py."
    )


# -- Coverage-of-the-coverage --------------------------------------------------
#
# A test that the canonical inventory itself isn't drifting silently. If
# someone adds a /surface/* or /array/* RouteSpec without adding it to
# PHASE1_TYPED_ROUTE_INTENTS, this catches it.


def test_phase1_inventory_covers_all_surface_and_array_routes() -> None:
    """Every RouteSpec with /surface/* or /array/* endpoint must appear in
    PHASE1_TYPED_ROUTE_INTENTS. Catches the case where a new typed route
    ships, gets a RouteSpec, but isn't added to the audit list.
    """
    routes = _route_table()
    inventory_intents = {entry[0] for entry in PHASE1_TYPED_ROUTE_INTENTS}

    typed_route_intents_in_table = {
        intent
        for intent, spec in routes.items()
        if spec.endpoint.startswith(("/surface/", "/array/"))
    }

    missing_from_inventory = typed_route_intents_in_table - inventory_intents
    assert not missing_from_inventory, (
        f"Route table contains typed routes not covered by the audit "
        f"inventory: {sorted(missing_from_inventory)}.\n"
        f"Add them to PHASE1_TYPED_ROUTE_INTENTS so the four-surface audit "
        f"applies to them too."
    )


def test_phase1_inventory_covers_all_executor_typed_endpoints() -> None:
    """Every /surface/* or /array/* endpoint mentioned in any call_rhino()
    invocation in server.py must have a corresponding RouteSpec in
    intent_runtime AND an entry in PHASE1_TYPED_ROUTE_INTENTS.

    Closes the symmetric blind spot Codex flagged on PR #61: the
    intent_runtime-derived inventory check would miss a typed route added
    to the executor but never given a RouteSpec. This check derives the
    inventory from server.py instead, so neither side can drift silently.

    A future typed-route family being shipped behind a feature flag and
    intentionally without a RouteSpec would need to be exempted here
    explicitly — that's the right discipline for "shipped but not yet
    plannable" routes.
    """
    source = _server_py_source()
    executor_endpoints = _server_py_typed_endpoints(source)

    routes = _route_table()
    route_table_endpoints = {
        spec.endpoint
        for spec in routes.values()
        if spec.endpoint.startswith(("/surface/", "/array/"))
    }
    inventory_endpoints = {entry[2] for entry in PHASE1_TYPED_ROUTE_INTENTS}

    missing_from_route_table = executor_endpoints - route_table_endpoints
    assert not missing_from_route_table, (
        f"Executor wires typed endpoints that have no CapabilityRouter "
        f"RouteSpec: {sorted(missing_from_route_table)}.\n"
        f"Agents invoking these via /intent would fall through to the DSPy "
        f"command-string fallback instead of the typed endpoint. Add the "
        f"missing RouteSpec entries to mcp_server/src/rook/learning/"
        f"intent_runtime.py."
    )

    missing_from_inventory = executor_endpoints - inventory_endpoints
    assert not missing_from_inventory, (
        f"Executor wires typed endpoints that aren't in the audit inventory: "
        f"{sorted(missing_from_inventory)}.\n"
        f"Add them to PHASE1_TYPED_ROUTE_INTENTS so the four-surface audit "
        f"covers them."
    )
