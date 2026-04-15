"""Shared pytest fixtures for the Rook MCP test suite.

Most tests in this folder are pure unit tests that mock `call_rhino` and
do not need Rhino running. Those tests do not request any of the fixtures
below; they will not be affected by this conftest.

The fixtures here exist for the `@pytest.mark.requires_rhino` live-integration
tests (see test_block_replace_object_geometry_live.py). They are opt-in via
fixture request — no autouse, no surprise side-effects for the unit suite.

Run live tests with:
    pytest -m requires_rhino mcp_server/tests/

IMPORTANT: live tests REPLACE the active Rhino document. Run them in a
throwaway Rhino session.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

# Make `rook.*` importable from the checked-out source tree. Mirrors the
# same shim used by scripts/validate_rhino_operational_suite.py so the live
# fixtures resolve the same bridge + MCP-executor modules the agents do.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = _REPO_ROOT / "mcp_server" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))


def _is_error(result: Any) -> bool:
    """True if a tool result indicates failure. Mirrors validate-script convention."""
    if result is None:
        return True
    if not isinstance(result, dict):
        return False
    if result.get("success") is False:
        return True
    if result.get("error"):
        return True
    data = result.get("data")
    if isinstance(data, str) and data.startswith("Error:"):
        return True
    return False


@pytest.fixture
def fresh_document():
    """Ping Rhino, reset to a blank document, yield to the test.

    Skips the requesting test cleanly if Rhino is not reachable — the
    `requires_rhino` marker is not a hard gate, so absent-Rhino must be
    a graceful skip rather than a hard failure.

    WARNING: calls `rhino_document_ops(action=new)`, which REPLACES the
    active document. Run tests under this fixture in a throwaway Rhino
    session.
    """
    from rook.server import _mcp_tool_executor

    async def _setup() -> tuple[bool, str | None]:
        try:
            ping = await asyncio.wait_for(
                _mcp_tool_executor("rhino_ping", {}),
                timeout=3.0,
            )
        except (asyncio.TimeoutError, Exception) as ex:  # noqa: BLE001 — skip path
            return False, f"Rhino ping raised: {ex!r}"

        if _is_error(ping):
            return False, f"Rhino ping returned error: {ping!r}"

        # Reset to a blank document so tests start from a known empty state.
        new_doc = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        if _is_error(new_doc):
            return False, f"rhino_document_ops(new) failed: {new_doc!r}"

        # `new` does NOT purge the InstanceDefinitions table on Rhino 8 —
        # block definitions from prior runs persist through the reset, and
        # `rhino_block_purge` only catches definitions with zero instances
        # (which may not be the post-`new` state depending on Rhino build).
        # Enumerate all surviving definitions and force-delete each.
        # Errors here are tolerated: the downstream test will fail loudly
        # on collision if a delete couldn't land.
        blocks_list = await _mcp_tool_executor("rhino_blocks", {})
        if isinstance(blocks_list, dict) and isinstance(blocks_list.get("blocks"), list):
            for entry in blocks_list["blocks"]:
                name = entry.get("name") if isinstance(entry, dict) else None
                if name:
                    await _mcp_tool_executor(
                        "rhino_block_delete",
                        {"name": name, "deleteInstances": True},
                    )

        return True, None

    ok, err = asyncio.run(_setup())
    if not ok:
        pytest.skip(err or "Rhino unavailable")
    yield
    # No teardown — next test's setup wipes via `rhino_document_ops(new)`.


def assert_bbox_x_range(bbox: dict, expected_min: float, expected_max: float, tol: float = 1e-5) -> None:
    """Assert a result's {min:[x,y,z], max:[x,y,z]} bbox matches on the X axis.

    Tolerance default is 1e-5 because Rhino's bbox returns can carry
    float32 representation error for InstanceReferenceGeometry transforms
    (observed during PR #30 live-verify: -3.699999988... instead of -3.7).
    """
    actual_min = bbox["min"][0]
    actual_max = bbox["max"][0]
    assert abs(actual_min - expected_min) < tol, (
        f"bbox.min.x = {actual_min!r}, expected {expected_min!r} (tol {tol})"
    )
    assert abs(actual_max - expected_max) < tol, (
        f"bbox.max.x = {actual_max!r}, expected {expected_max!r} (tol {tol})"
    )
