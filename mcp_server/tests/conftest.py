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


async def assert_new_slot(
    block_name: str,
    expected_base_point: "tuple[float, float, float]",
    tol: float = 1e-12,
) -> None:
    """Test-only introspection: assert a RookBlockBasePointUserData is
    attached to the named idef with the expected BasePoint value.

    Hits the native `POST /block/_debug/basepoint-userdata` route DIRECTLY
    via httpx, bypassing the MCP tool layer. That route is an internal/
    test-only debug hook — never registered as an MCP tool, no stable
    contract, product code must not depend on it. Design doc §1 explicitly
    rules out product MCP tool surface changes for this PR, so the route
    is deliberately off the MCP grid.

    Tests use this to prove the new storage slot is actually populated
    (distinguishing real new-slot writes from legacy user-string fallback
    during the dual-write transition window). See #28 design §5.2.

    Fails clearly if:
    - the native plugin is discoverable but does not expose the route
      (404) — signals Rhino is running an older RookNative build
    - the UserData is absent, malformed, or disagrees with expected
    """
    import httpx  # lazy import; not needed by unit tests
    from rook.bridge import get_rhino_host  # lazy; only when live-Rhino tests run

    base_url = get_rhino_host()
    if base_url is None:
        pytest.fail(
            "Native plugin not discoverable; cannot inspect new UserData slot. "
            "Ensure Rhino is running with RookNative loaded."
        )

    url = f"{base_url}/block/_debug/basepoint-userdata"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"name": block_name})
    except Exception as ex:
        pytest.fail(f"POST {url} failed: {ex!r}")

    if resp.status_code == 404:
        pytest.fail(
            f"{url} returned 404 — Rhino is running an older RookNative build "
            f"without the Phase B internal debug route. Rebuild + redeploy native."
        )
    if resp.status_code == 403:
        pytest.skip(
            f"{url} returned 403 — debug routes disabled on the running "
            f"RookNative. Set ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino process "
            f"environment and restart Rhino to enable #28 test-only routes."
        )
    if resp.status_code != 200:
        pytest.fail(f"{url} returned {resp.status_code}: {resp.text}")

    try:
        body = resp.json()
    except Exception as ex:
        pytest.fail(f"{url} returned non-JSON body: {resp.text!r} ({ex!r})")

    if body.get("success") is False:
        pytest.fail(f"{url} reported error: {body.get('data')!r}")

    data = body.get("data")
    if not isinstance(data, dict):
        pytest.fail(f"{url} unexpected response shape: {body!r}")

    if not data.get("attached"):
        pytest.fail(
            f"Expected new-slot UserData attached to block {block_name!r}, "
            f"but native reports attached=false. Phase B write path may not "
            f"have populated the slot."
        )

    bp = data.get("basePoint")
    if not (isinstance(bp, list) and len(bp) == 3):
        pytest.fail(f"Malformed basePoint in response: {data!r}")

    ex_x, ex_y, ex_z = expected_base_point
    if (
        abs(bp[0] - ex_x) > tol
        or abs(bp[1] - ex_y) > tol
        or abs(bp[2] - ex_z) > tol
    ):
        pytest.fail(
            f"new-slot basePoint mismatch for {block_name!r}: "
            f"got ({bp[0]!r}, {bp[1]!r}, {bp[2]!r}), "
            f"expected ({ex_x!r}, {ex_y!r}, {ex_z!r}), tol={tol}"
        )


async def set_legacy_basepoint_for_test(
    block_name: str,
    base_point: "tuple[float, float, float]",
) -> None:
    """Test-only: write ONLY the legacy `rook_block_base_point` user-string
    on a named idef, leaving the new UserData slot untouched.

    Used by the Phase C disagreement test to simulate a state production
    code cannot produce: new slot and legacy hold different values.

    Hits `POST /block/_debug/set-legacy-basepoint` directly via httpx. Not
    an MCP tool; see native handler comment for the contract.
    """
    import httpx
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.fail("Native plugin not discoverable; cannot set legacy basePoint")

    url = f"{base_url}/block/_debug/set-legacy-basepoint"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                url,
                json={"name": block_name, "basePoint": list(base_point)},
            )
    except Exception as ex:
        pytest.fail(f"POST {url} failed: {ex!r}")

    if resp.status_code == 404:
        pytest.fail(
            f"{url} returned 404 — older RookNative build loaded; "
            f"rebuild + redeploy native to pick up Phase C internal routes."
        )
    if resp.status_code == 403:
        pytest.skip(
            f"{url} returned 403 — debug routes disabled. Set "
            f"ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino process environment "
            f"and restart Rhino to enable #28 test-only routes."
        )
    if resp.status_code != 200:
        pytest.fail(f"{url} returned {resp.status_code}: {resp.text}")

    body = resp.json()
    if body.get("success") is False:
        pytest.fail(f"{url} reported error: {body.get('data')!r}")


async def assert_no_new_slot(block_name: str) -> None:
    """Test-only introspection: assert NO RookBlockBasePointUserData is
    attached to the named idef.

    Complement to assert_new_slot. Hits the same native debug route.
    Used by tests that verify Rook does NOT synthesize metadata on
    externally-authored or linked definitions (#35).
    """
    import httpx
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.fail(
            "Native plugin not discoverable; cannot inspect UserData slot."
        )

    url = f"{base_url}/block/_debug/basepoint-userdata"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json={"name": block_name})
    except Exception as ex:
        pytest.fail(f"POST {url} failed: {ex!r}")

    if resp.status_code == 403:
        pytest.skip(
            f"{url} returned 403 — debug routes disabled. Set "
            f"ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino process environment "
            f"and restart Rhino to enable #28 test-only routes."
        )
    if resp.status_code == 404:
        pytest.fail(
            f"{url} returned 404 — older RookNative build. Rebuild + redeploy."
        )
    if resp.status_code != 200:
        pytest.fail(f"{url} returned {resp.status_code}: {resp.text}")

    try:
        body = resp.json()
    except Exception as ex:
        pytest.fail(f"{url} returned non-JSON body: {resp.text!r} ({ex!r})")

    data = body.get("data")
    if not isinstance(data, dict):
        pytest.fail(f"{url} unexpected response shape: {body!r}")

    if data.get("attached") is not False:
        bp = data.get("basePoint")
        pytest.fail(
            f"Expected NO RookBlockBasePointUserData on block {block_name!r}, "
            f"but native reports attached=true with basePoint={bp!r}."
        )
