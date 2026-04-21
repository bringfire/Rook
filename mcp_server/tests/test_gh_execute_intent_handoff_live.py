"""Live-Rhino regression floor for the PR-3 handoff check.

PR-3 adds a handoff check to `gh_execute_intent` that refuses to create
modern RhinoCode script components via `/gh/create-component`. The check
keys on two fixed GUIDs and is otherwise pure-Python; the unit tests in
`test_server_contract_hardening.py` exercise its logic in isolation.

The concern with live coverage is false regression: the handoff must NOT
fire on normal non-script intents. This file pins exactly that — a
vanilla "create a sphere" intent runs end-to-end against a real Rhino /
Grasshopper session and does not trip the handoff.

Live handoff-path coverage for Python became deterministic once the
knowledge store + resolver ranking aligned on the modern GUID. The C#
positive case was deferred from PR-3 (Option B) because the knowledge
store did not surface modern RhinoCode C# Script for generic C# intents
— that was the parked "prefer modern RhinoCode C# Script over legacy"
follow-up (shipped 2026-04-21). Now that modern C# is both retrievable
and preferred by the resolver, the C# positive handoff is deterministic
and added below as a regression anchor.

See rook_docs/2026-04-21-gh-script-component-routing-design-pass.md §PR-3
and the csharp-modern-resolver-visibility follow-up.

Run (from repo root, with Rhino open and Rook loaded):
    pytest -m requires_rhino mcp_server/tests/test_gh_execute_intent_handoff_live.py
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


def _response_looks_like_handoff(result: Any) -> bool:
    """True iff the tool response carries PR-3 handoff markers. Handoffs
    put a structured dict in `result["data"]`; call_tool formats failures
    with dict-data as `Error: {json}` (PR-3 serializer update).
    """
    if not isinstance(result, dict):
        return False
    data = result.get("data")
    if isinstance(data, dict):
        return bool(data.get("handoff_required"))
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
        except Exception:
            return False
        if isinstance(parsed, dict):
            return bool(parsed.get("handoff_required"))
    return False


async def test_gh_execute_intent_non_script_intent_does_not_handoff_live():
    """Regression floor: the PR-3 handoff check must fire only on script
    components. A plain geometry intent — "create a sphere" — must
    resolve normally without tripping the handoff path.

    This is the non-handoff side of PR-3. If this test breaks, the
    handoff check has a false-positive surface (e.g., matching too
    broadly, wrong GUID list).
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_execute_intent",
        {"intent": "create a sphere", "x": 500, "y": 500},
    )
    # The intent may succeed or fail for unrelated reasons (DSPy confidence,
    # knowledge-store state, etc.); what MUST hold is that no handoff
    # marker appears in the response. That's what PR-3 regresses if
    # broken.
    assert not _response_looks_like_handoff(result), (
        f"Non-script intent tripped PR-3 handoff; result={result!r}"
    )


async def test_gh_execute_intent_csharp_intent_now_triggers_handoff_live():
    """End-to-end positive handoff coverage for C#. Previously deferred
    under PR-3 Option B because the knowledge store did not surface the
    modern RhinoCode C# Script GUID for generic C# intents — the DSPy
    resolver would pick the GH1-legacy component, which correctly does
    not trigger the handoff (narrow-match by design).

    With the modern C# note added and the resolver's concept-key +
    preference rule updated, a bare "create a C# script" intent now
    deterministically resolves to the modern `CS3_GUID`, which IS in
    the PR-3 handoff map, so the refusal fires.

    Behavioral pin: the full closure of the 2026-04-21 script-routing
    incident for both languages.
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_execute_intent",
        {"intent": "create a C# script that adds two numbers"},
    )

    assert _response_looks_like_handoff(result), (
        f"C# intent must now trigger PR-3 handoff after resolver-visibility "
        f"fix; result={result!r}"
    )

    # The structured response must name C# specifically so callers can
    # branch correctly on `recommended_language`.
    data = result.get("data") if isinstance(result, dict) else None
    if isinstance(data, dict):
        assert data.get("recommended_language") == "csharp"
        assert data.get("recommended_tool") == "gh_create_script"


async def test_gh_execute_intent_python_intent_triggers_handoff_live():
    """End-to-end positive handoff coverage for Python. Confirms the
    Python side of the campaign regression floor — already deterministic
    pre-PR because Python 3 was already ranked modern-first.
    """
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_execute_intent",
        {"intent": "create a python script that adds two numbers"},
    )

    assert _response_looks_like_handoff(result), (
        f"Python intent must trigger PR-3 handoff; result={result!r}"
    )

    data = result.get("data") if isinstance(result, dict) else None
    if isinstance(data, dict):
        assert data.get("recommended_language") == "python"
        assert data.get("recommended_tool") == "gh_create_script"
