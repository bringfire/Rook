"""Live-Rhino regression for the GH locked-solver crash. requires_rhino; throwaway session only.

Background: locking the Grasshopper solver and then calling gh_update_script used to crash Rhino
instantly (synchronous ExpireSolution(true) re-entering the non-reentrant solver). The fix marks
the component dirty and defers the solve when the solver is locked. Manually verified passing on
2026-06-02 (UI-lock repro); this is the automated guard for CI / future runs.

Run from repo root with Rhino + Grasshopper open and Rook loaded, in a THROWAWAY session:
    pytest -m requires_rhino mcp_server/tests/test_gh_locked_solver_live.py
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# Lock/unlock by setting BOTH candidate members via .NET reflection. The GH "Lock Solver" UI
# toggles one of these; setting both is robust to whichever it is, and GhSolverState.Inspect
# (which ANDs the readable flags) then reports the document as locked.
_SET_SOLVER = (
    "import Grasshopper as gh\n"
    "import System.Reflection as R\n"
    "doc = gh.Instances.ActiveCanvas.Document\n"
    "T = doc.GetType()\n"
    "def setp(name, static, val):\n"
    "    f = R.BindingFlags.Public | (R.BindingFlags.Static if static else R.BindingFlags.Instance)\n"
    "    p = T.GetProperty(name, f)\n"
    "    if p is not None and p.CanWrite:\n"
    "        p.SetValue(None if static else doc, val)\n"
    "setp('EnableSolutions', True, {val})\n"
    "setp('Enabled', False, {val})\n"
)


async def _ensure_document() -> None:
    """A fresh throwaway GH document so gh_create_script has a canvas to draw on."""
    from rook.server import _mcp_tool_executor

    await _mcp_tool_executor("gh_document_new", {})


async def _set_solver(enabled: bool) -> None:
    from rook.server import _mcp_tool_executor

    code = _SET_SOLVER.format(val=("True" if enabled else "False"))
    await _mcp_tool_executor("rhino_execute", {"code": code})


async def _make_script() -> str:
    from rook.server import _mcp_tool_executor

    result = await _mcp_tool_executor(
        "gh_create_script",
        {
            "language": "csharp",
            "code": "A = Convert.ToDouble(R);",
            "pins_in": [{"name": "R", "type": "double"}],
            "pins_out": [{"name": "A", "type": "double"}],
            "name": "LockedSolverLive",
            "x": 600,
            "y": 360,
        },
    )
    if _is_error(result):
        data = result.get("data") if isinstance(result, dict) else None
        if isinstance(data, dict) and data.get("error") == "no_rhino_instance":
            pytest.skip("requires a running Rhino/Rook instance")
        pytest.skip(f"gh_create_script unavailable: {result!r}")
    data = result.get("data", result)
    guid = data.get("guid") or data.get("Guid") or data.get("component_guid")
    assert guid, f"no component guid in response: {result!r}"
    return guid


async def test_update_script_on_locked_canvas_does_not_crash():
    from rook.server import _mcp_tool_executor

    await _ensure_document()
    guid = await _make_script()
    try:
        await _set_solver(False)  # LOCK both members
        result = await _mcp_tool_executor(
            "gh_update_script",
            {"guid": guid, "language": "csharp", "code": "A = Convert.ToDouble(R) * 3.0;"},
        )
        assert isinstance(result, dict)
        data = result.get("data", result)

        # The locked path must defer, not claim a clean compile, and must not crash.
        assert data.get("verification_deferred") is True, data
        assert data.get("solver_locked") in (True, None), data
        assert data.get("solve_scheduled") in (False, None), data

        # Source round-tripped even though it was not recomputed.
        read_back = await _mcp_tool_executor("gh_set_script", {"guid": guid})
        rb = read_back.get("data") if isinstance(read_back, dict) else None
        src = ((rb or {}).get("Script") or (rb or {}).get("script") or "") if isinstance(rb, dict) else ""
        assert "* 3.0" in src, f"source did not round-trip on locked write: {read_back!r}"

        # Rhino is still alive (the whole point).
        ping = await _mcp_tool_executor("rhino_ping", {})
        assert not _is_error(ping), f"Rhino unresponsive after locked update (possible crash): {ping!r}"
    finally:
        await _set_solver(True)  # always restore unlocked


async def test_update_script_on_unlocked_canvas_recomputes():
    from rook.server import _mcp_tool_executor

    await _ensure_document()
    guid = await _make_script()
    await _set_solver(True)  # ensure unlocked
    result = await _mcp_tool_executor(
        "gh_update_script",
        {"guid": guid, "language": "csharp", "code": "A = Convert.ToDouble(R) + 1.0;"},
    )
    data = result.get("data", result)
    # Unlocked: a real compile/error check ran; not deferred.
    assert data.get("verification_deferred") in (None, False, ""), data
    assert "component_errors" in data, data
