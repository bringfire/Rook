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
    """Surface 2: `case "rhino_<X>":` exists in the call_tool match block.

    Failure mode caught: tool registered but no executor routing — invocation
    falls into the default case and returns "Unknown tool" or similar.
    """
    labels = _executor_case_labels(_server_py_source())
    assert tool_name in labels, (
        f"Intent {intent!r}: tool {tool_name!r} has no executor case arm. "
        f"Agent invocations would hit the default branch.\n"
        f"To fix: add `case \"{tool_name}\":` to call_tool() routing the "
        f"call to {endpoint!r}."
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
    ships and the audit list isn't updated to cover it.
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
