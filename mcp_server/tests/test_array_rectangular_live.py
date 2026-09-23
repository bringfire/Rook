"""Live-Rhino characterization tests for POST /array/rectangular (Phase 1 PR-5).

Pins the direct-sdk rectangular-array contract:
  - mutation response envelope on success
  - active-CPlane basis echoed back as planeUsed
  - ids are source-major, then row-major with inner X / Y / Z
  - rollback is explicit on mid-loop failure via the internal debug seam

Run:
    pytest -m requires_rhino mcp_server/tests/test_array_rectangular_live.py
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _create_box(corner1: list[float], corner2: list[float], name: str) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": corner1, "corner2": corner2, "name": name},
    )
    assert not _is_error(res), f"rhino_create BOX failed: {res!r}"
    return res["id"]


async def _measure_bbox(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_measure_bbox", {"id": obj_id})
    assert not _is_error(res), f"rhino_measure_bbox failed: {res!r}"
    return res


async def _tool_array_rectangular(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_array_rectangular", body)
    assert not _is_error(res), f"rhino_array_rectangular failed: {res!r}"
    return res


async def _execute_script(code: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_execute", {"code": code})
    assert not _is_error(res), f"rhino_execute failed: {res!r}"
    return res


async def _post_array_rectangular_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/array/rectangular", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/array/rectangular returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _get_objects_raw(params: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.get(f"{base_url}/objects", params=params or {})
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/objects returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


async def _arm_fail_next_copy(index: int) -> None:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(f"{base_url}/array/_debug/fail-next-copy", json={"index": index})

    if resp.status_code == 403:
        pytest.skip(
            "Debug routes disabled. Set ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino "
            "process environment and restart Rhino to enable /array/_debug/* routes."
        )
    if resp.status_code != 200:
        pytest.fail(f"/array/_debug/fail-next-copy returned {resp.status_code}: {resp.text}")


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured error data: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, got {data.get('errorCode')!r} in {envelope!r}"
    )


def _assert_rectangular_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert data.get("mode") == "rectangular", f"Expected mode='rectangular': {envelope!r}"
    assert isinstance(data.get("ids"), list), f"Expected ids list: {envelope!r}"
    assert isinstance(data.get("planeUsed"), dict), f"Expected planeUsed dict: {envelope!r}"
    return data


def _assert_close(actual: float, expected: float, tol: float = 1e-5) -> None:
    assert abs(actual - expected) < tol, f"Expected {expected!r}, got {actual!r} (tol={tol})"


async def _object_count() -> int:
    _, envelope = await _get_objects_raw({"limit": 500})
    assert envelope.get("success") is True, f"/objects failed: {envelope!r}"
    return int(envelope["data"]["totalCount"])


async def _set_active_cplane(origin: list[float], xaxis: list[float], yaxis: list[float]) -> None:
    script = (
        "import rhinoscriptsyntax as rs\n"
        "import Rhino.Geometry as rg\n"
        f"plane = rg.Plane(rg.Point3d({origin[0]}, {origin[1]}, {origin[2]}), "
        f"rg.Vector3d({xaxis[0]}, {xaxis[1]}, {xaxis[2]}), "
        f"rg.Vector3d({yaxis[0]}, {yaxis[1]}, {yaxis[2]}))\n"
        "rs.ViewCPlane(None, plane)\n"
    )
    await _execute_script(script)


async def test_array_rectangular_two_dimensional_grid(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectSource")

    status, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 3,
        "yCount": 2,
        "xSpacing": 10,
        "ySpacing": 5,
    })
    assert status == 200, f"Unexpected HTTP status: {status}"
    data = _assert_rectangular_success(envelope)
    assert data["createdCount"] == 5
    assert len(data["ids"]) == 5

    mins = []
    for obj_id in data["ids"]:
        bbox = await _measure_bbox(obj_id)
        mins.append((round(bbox["min"][0], 4), round(bbox["min"][1], 4)))

    assert mins == [
        (10.0, 0.0),
        (20.0, 0.0),
        (0.0, 5.0),
        (10.0, 5.0),
        (20.0, 5.0),
    ]


async def test_array_rectangular_three_dimensional_grid(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "Rect3DSource")

    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 2,
        "yCount": 2,
        "zCount": 2,
        "xSpacing": 10,
        "ySpacing": 10,
        "zSpacing": 10,
    })
    data = _assert_rectangular_success(envelope)
    assert data["createdCount"] == 7
    assert len(data["ids"]) == 7


async def test_array_rectangular_tool_defaults_zcount_to_one(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectDefaultZ")
    data = await _tool_array_rectangular({
        "ids": [source],
        "xCount": 1,
        "yCount": 1,
        "xSpacing": 10,
        "ySpacing": 10,
    })
    assert data["createdCount"] == 0
    assert data["ids"] == []
    assert data["zCount"] == 1


async def test_array_rectangular_non_integer_count_is_invalid_count(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectBadCount")
    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 2.5,
        "yCount": 2,
        "xSpacing": 10,
        "ySpacing": 5,
    })
    _assert_structured_error(envelope, "invalid_count")


async def test_array_rectangular_zero_xcount_is_invalid_count(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectZeroXCount")
    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 0,
        "yCount": 2,
        "xSpacing": 10,
        "ySpacing": 5,
    })
    _assert_structured_error(envelope, "invalid_count")


async def test_array_rectangular_zero_xspacing_is_invalid_spacing(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectZeroXSpacing")
    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 3,
        "yCount": 2,
        "xSpacing": 0,
        "ySpacing": 5,
    })
    _assert_structured_error(envelope, "invalid_spacing")


async def test_array_rectangular_missing_zspacing_is_rejected(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectMissingZSpacing")
    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 2,
        "yCount": 2,
        "zCount": 2,
        "xSpacing": 10,
        "ySpacing": 10,
    })
    _assert_structured_error(envelope, "zspacing_required")


async def test_array_rectangular_zero_zspacing_is_rejected(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectZeroZSpacing")
    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 2,
        "yCount": 2,
        "zCount": 2,
        "xSpacing": 10,
        "ySpacing": 10,
        "zSpacing": 0,
    })
    _assert_structured_error(envelope, "zspacing_required")


async def test_array_rectangular_multi_source_source_major_ordering(fresh_document):
    a = await _create_box([0, 0, 0], [1, 1, 1], "RectSourceA")
    b = await _create_box([100, 0, 0], [101, 1, 1], "RectSourceB")

    _, envelope = await _post_array_rectangular_raw({
        "ids": [a, b],
        "xCount": 3,
        "yCount": 2,
        "xSpacing": 10,
        "ySpacing": 5,
    })
    data = _assert_rectangular_success(envelope)
    assert data["createdCount"] == 10
    assert len(data["ids"]) == 10

    mins = []
    for obj_id in data["ids"]:
        bbox = await _measure_bbox(obj_id)
        mins.append((round(bbox["min"][0], 4), round(bbox["min"][1], 4)))

    assert mins == [
        (10.0, 0.0),
        (20.0, 0.0),
        (0.0, 5.0),
        (10.0, 5.0),
        (20.0, 5.0),
        (110.0, 0.0),
        (120.0, 0.0),
        (100.0, 5.0),
        (110.0, 5.0),
        (120.0, 5.0),
    ]


async def test_array_rectangular_plane_used_round_trip(fresh_document):
    await _set_active_cplane([12, 34, 56], [0, 1, 0], [0, 0, 1])
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectPlaneRoundTrip")

    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 2,
        "yCount": 1,
        "xSpacing": 10,
        "ySpacing": 5,
    })
    data = _assert_rectangular_success(envelope)
    plane = data["planeUsed"]

    assert plane["origin"] == [12.0, 34.0, 56.0]
    assert plane["xAxis"] == [0.0, 1.0, 0.0]
    assert plane["yAxis"] == [0.0, 0.0, 1.0]
    assert plane["zAxis"] == [1.0, 0.0, 0.0]


async def test_array_rectangular_debug_failure_rolls_back_all_created_copies(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "RectDebugRollback")
    before = await _object_count()
    await _arm_fail_next_copy(4)

    _, envelope = await _post_array_rectangular_raw({
        "ids": [source],
        "xCount": 3,
        "yCount": 2,
        "xSpacing": 10,
        "ySpacing": 5,
    })
    _assert_structured_error(envelope, "operation_failed")

    after = await _object_count()
    assert after == before, f"Expected rollback to restore object count; before={before}, after={after}"
