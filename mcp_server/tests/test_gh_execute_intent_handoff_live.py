"""Live-Rhino regression floor for the PR-3 handoff check.

PR-3 adds a handoff check to `gh_execute_intent` that refuses to create
modern RhinoCode script components via `/gh/create-component`. The check
keys on two fixed GUIDs and is otherwise pure-Python; the unit tests in
`test_server_contract_hardening.py` exercise its logic in isolation.

The concern with live coverage is false regression: the handoff must NOT
fire on normal non-script intents. This file pins exactly that — a
vanilla "create a sphere" intent runs end-to-end against a real Rhino /
Grasshopper session and does not trip the handoff.

Live handoff-path coverage (i.e. asking for a script component and
confirming the refusal) is intentionally out of scope per the PR-3
scope pass Option B — the DSPy resolver's selection on a given intent
text depends on live model + sparse-index state, making the positive
case non-deterministic in a live test.

See rook_docs/2026-04-21-gh-script-component-routing-design-pass.md §PR-3.

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
