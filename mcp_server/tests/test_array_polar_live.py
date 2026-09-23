"""Live-Rhino characterization tests for POST /array/polar (Phase 1 PR-6).

Pins the direct-sdk polar contract:
  - mutation response envelope on success
  - structured {errorCode, errorMessage} on failure
  - count semantics are total-including-source
  - ids are source-major, theta-minor
  - signed full-circle predicate handles +/-360 symmetrically
  - count==1 short-circuits step computation AND axis validation, but
    NOT source pre-flight (bogus uuids still surface as not_found at count=1)
  - rotate=false orbits each source's tight-bbox center while preserving
    orientation
  - rollback is explicit on mid-loop failure via the internal debug seam

Run:
    pytest -m requires_rhino mcp_server/tests/test_array_polar_live.py

Rhino must be running with RookNative loaded. Tests reset the document on
entry via the fresh_document fixture — run them in a throwaway session.

The atomicity test additionally requires ROOK_ENABLE_DEBUG_ROUTES=1 in the
Rhino process environment; it skips cleanly if the env var is unset.
"""

from __future__ import annotations

import math
from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


async def _create_box(
    corner1: list[float],
    corner2: list[float],
    name: str,
    layer: str | None = None,
) -> str:
    from rook.server import _mcp_tool_executor

    args: dict[str, Any] = {
        "type": "BOX",
        "corner1": corner1,
        "corner2": corner2,
        "name": name,
    }
    if layer is not None:
        args["layer"] = layer

    res = await _mcp_tool_executor("rhino_create", args)
    assert not _is_error(res), f"rhino_create BOX failed: {res!r}"
    return res["id"]


async def _measure_bbox(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_measure_bbox", {"id": obj_id})
    assert not _is_error(res), f"rhino_measure_bbox failed: {res!r}"
    return res


async def _tool_array_polar(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_array_polar", body)
    assert not _is_error(res), f"rhino_array_polar failed: {res!r}"
    return res


async def _post_array_polar_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/array/polar", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/array/polar returned non-JSON body: {resp.text!r} ({ex!r})")
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
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"], (
        f"Expected non-empty errorMessage in {envelope!r}"
    )


def _assert_polar_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert data.get("mode") == "polar", f"Expected mode='polar': {envelope!r}"
    assert isinstance(data.get("ids"), list), f"Expected ids list: {envelope!r}"
    return data


def _assert_close(actual: float, expected: float, tol: float = 1e-4) -> None:
    assert abs(actual - expected) < tol, f"Expected {expected!r}, got {actual!r} (tol={tol})"


async def _object_count() -> int:
    _, envelope = await _get_objects_raw({"limit": 500})
    assert envelope.get("success") is True, f"/objects failed: {envelope!r}"
    return int(envelope["data"]["totalCount"])


def _bbox_dims(bbox: dict[str, Any]) -> tuple[float, float, float]:
    """Return (dx, dy, dz) of a measure_bbox result."""
    mn = bbox["min"]
    mx = bbox["max"]
    return (mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2])


def _bbox_center(bbox: dict[str, Any]) -> tuple[float, float, float]:
    mn = bbox["min"]
    mx = bbox["max"]
    return ((mn[0] + mx[0]) / 2.0, (mn[1] + mx[1]) / 2.0, (mn[2] + mx[2]) / 2.0)


# (a) Spike replication: 2x2x2 box at corner [220,0,0], polar around [220,0,0]
# count=6, angle=360. Source centroid at [221,1,1] is offset from rotation
# center, so 5 new copies form an even ring at 60° intervals.
async def test_array_polar_spike_replication_full_circle(fresh_document):
    source = await _create_box([220, 0, 0], [222, 2, 2], "PolarSpike")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [220, 0, 0],
        "count": 6,
        "angle": 360,
    })
    assert status == 200, f"Expected 200, got {status}: {envelope!r}"
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 5
    assert len(data["ids"]) == 5

    # Source centroid offset from center: [1,1,1]. Distance from Z axis = sqrt(2).
    expected_radius = math.sqrt(2.0)
    for new_id in data["ids"]:
        bbox = await _measure_bbox(new_id)
        cx, cy, cz = _bbox_center(bbox)
        # All copies stay at z=1 (rotation around Z axis preserves Z coordinate).
        _assert_close(cz, 1.0, tol=1e-3)
        # Distance from rotation center [220,0,0] in XY plane = sqrt(2).
        dx = cx - 220.0
        dy = cy - 0.0
        radius = math.sqrt(dx * dx + dy * dy)
        _assert_close(radius, expected_radius, tol=1e-3)


# (b) Partial sweep: count=4, angle=180 → step=60°, copies at 60/120/180.
async def test_array_polar_partial_sweep(fresh_document):
    source = await _create_box([10, 0, 0], [12, 2, 2], "PolarPartial")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 4,
        "angle": 180,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 3
    # Last copy lands at angle=180 → its centroid X equals -source_centroid_x.
    last_bbox = await _measure_bbox(data["ids"][-1])
    cx, _, _ = _bbox_center(last_bbox)
    _assert_close(cx, -11.0, tol=1e-3)


# (c) count=2, angle=90 → 1 new copy at 90°.
async def test_array_polar_count_two_angle_ninety(fresh_document):
    source = await _create_box([5, 0, 0], [6, 1, 1], "PolarCount2")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 2,
        "angle": 90,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 1
    # Source centroid at [5.5, 0.5, 0.5]. After 90° rotation around Z about origin:
    # new x = -0.5, new y = 5.5.
    bbox = await _measure_bbox(data["ids"][0])
    cx, cy, _ = _bbox_center(bbox)
    _assert_close(cx, -0.5, tol=1e-3)
    _assert_close(cy, 5.5, tol=1e-3)


# (d) rotate=false: fixture is asymmetric box + non-90° step (72°) so a
# rotation would visibly change the tight-bbox. Verifies the contract that
# rotate=false preserves source orientation. Cube fixtures and 90°-aligned
# steps are explicitly avoided — they can mask the bug.
async def test_array_polar_rotate_false_preserves_orientation(fresh_document):
    # Asymmetric source: 6×1×0.5
    source = await _create_box([10, 0, 0], [16, 1, 0.5], "PolarRotateFalse")
    source_dims = _bbox_dims(await _measure_bbox(source))

    # rotate=false: all copies must keep the source's tight-bbox dimensions.
    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 5,
        "angle": 360,
        "rotate": False,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 4

    for new_id in data["ids"]:
        copy_dims = _bbox_dims(await _measure_bbox(new_id))
        # Within ON_ZERO_TOLERANCE of source dims on each axis.
        _assert_close(copy_dims[0], source_dims[0], tol=1e-3)
        _assert_close(copy_dims[1], source_dims[1], tol=1e-3)
        _assert_close(copy_dims[2], source_dims[2], tol=1e-3)


# (d-baseline) rotate=true with the same fixture: at least one copy must have
# tight-bbox dimensions that differ from the source by > 1.0 unit in some
# axis. Proves the (d) test would catch a rotate=false regression.
async def test_array_polar_rotate_true_changes_bbox_dimensions(fresh_document):
    source = await _create_box([10, 0, 0], [16, 1, 0.5], "PolarRotateTrueBaseline")
    source_dims = _bbox_dims(await _measure_bbox(source))

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 5,
        "angle": 360,
        "rotate": True,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 4

    saw_rotation_evidence = False
    for new_id in data["ids"]:
        copy_dims = _bbox_dims(await _measure_bbox(new_id))
        max_axis_drift = max(abs(c - s) for c, s in zip(copy_dims, source_dims))
        if max_axis_drift > 1.0:
            saw_rotation_evidence = True
            break
    assert saw_rotation_evidence, (
        "rotate=true with asymmetric source + 72° step must produce at least "
        "one copy whose tight-bbox dims differ from source by > 1.0; otherwise "
        "the rotate=false test (d) would not catch a regression."
    )


# (e) count=1 with valid source → no copies, success.
async def test_array_polar_count_one_with_valid_source(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "PolarCountOne")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 1,
        "angle": 360,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 0
    assert data["ids"] == []


# (f) count=1 with a syntactically-valid but absent uuid → not_found
# (pre-flight runs even at count=1). The nil UUID
# 00000000-0000-0000-0000-000000000000 cannot be used here — ParseUuids
# rejects nil UUIDs at the worker thread via ON_UuidIsNil, surfacing as
# invalid_input. We need a well-formed non-nil UUID that simply isn't in
# the document so the request reaches the UI-thread pre-flight.
async def test_array_polar_count_one_with_bogus_source(fresh_document):
    absent_uuid = "deadbeef-dead-beef-dead-beefdeadbeef"

    status, envelope = await _post_array_polar_raw({
        "ids": [absent_uuid],
        "center": [0, 0, 0],
        "count": 1,
    })
    _assert_structured_error(envelope, "not_found")


# (g) count=1 with valid source AND degenerate axis → succeeds. Pins the
# contract that count=1 short-circuits axis validation (no rotation is
# performed; the axis value is never consumed).
async def test_array_polar_count_one_with_degenerate_axis_succeeds(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "PolarCountOneDegenAxis")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "axis": [0, 0, 0],
        "count": 1,
    })
    assert status == 200, f"count=1 should succeed even with degenerate axis: {envelope!r}"
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 0


# (h) count=0 → invalid_count.
async def test_array_polar_zero_count_is_invalid_count(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "PolarZeroCount")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 0,
    })
    _assert_structured_error(envelope, "invalid_count")


# (i) Non-integer count → invalid_count.
async def test_array_polar_non_integer_count_is_invalid_count(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "PolarBadCount")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 3.5,
    })
    _assert_structured_error(envelope, "invalid_count")


# (j) count=3, angle=0 → angle_zero_with_count.
async def test_array_polar_zero_angle_with_count_rejected(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "PolarZeroAngle")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 3,
        "angle": 0,
    })
    _assert_structured_error(envelope, "angle_zero_with_count")


# (k) count > 1 with degenerate axis → degenerate_axis.
async def test_array_polar_degenerate_axis_with_count_rejected(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "PolarDegenAxis")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "axis": [0, 0, 0],
        "count": 4,
    })
    _assert_structured_error(envelope, "degenerate_axis")


# (l) Negative full circle: count=4, angle=-360. step = -90°. Copies at
# -90°, -180°, -270°. Critically: NO copy lands on the source position (which
# would happen if -360 fell into the partial-sweep branch with step =
# -360/(count-1) = -120°, placing the last copy at -360° = source).
async def test_array_polar_negative_full_circle(fresh_document):
    source = await _create_box([5, 0, 0], [6, 1, 1], "PolarNegFull")
    source_bbox = await _measure_bbox(source)
    source_cx, source_cy, _ = _bbox_center(source_bbox)

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 4,
        "angle": -360,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 3

    # No copy may share the source centroid (would mean -360 was treated as
    # a partial sweep, not a reverse full circle).
    for new_id in data["ids"]:
        bbox = await _measure_bbox(new_id)
        cx, cy, _ = _bbox_center(bbox)
        same_position = (
            abs(cx - source_cx) < 1e-3 and abs(cy - source_cy) < 1e-3
        )
        assert not same_position, (
            f"Copy {new_id!r} at ({cx},{cy}) coincides with source ({source_cx},{source_cy}); "
            "negative full circle was incorrectly treated as partial sweep."
        )


# (m) Negative partial: count=4, angle=-180 → 3 copies at -60°/-120°/-180°.
async def test_array_polar_negative_partial_sweep(fresh_document):
    source = await _create_box([5, 0, 0], [6, 1, 1], "PolarNegPartial")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 4,
        "angle": -180,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 3
    # Last copy at angle = -180°. Source centroid at [5.5, 0.5, 0.5];
    # after rotating -180° around Z about origin: x = -5.5, y = -0.5.
    last_bbox = await _measure_bbox(data["ids"][-1])
    cx, cy, _ = _bbox_center(last_bbox)
    _assert_close(cx, -5.5, tol=1e-3)
    _assert_close(cy, -0.5, tol=1e-3)


# (n) Custom axis (non-Z): rotation around X.
async def test_array_polar_custom_axis(fresh_document):
    source = await _create_box([0, 5, 0], [1, 6, 1], "PolarCustomAxis")

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "axis": [1, 0, 0],
        "count": 4,
        "angle": 360,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 3
    # Source centroid at [0.5, 5.5, 0.5]. Rotating around X axis by 90°:
    # new y = -0.5, new z = 5.5. Take the first copy (k=1).
    first_bbox = await _measure_bbox(data["ids"][0])
    cx, cy, cz = _bbox_center(first_bbox)
    _assert_close(cx, 0.5, tol=1e-3)
    _assert_close(cy, -0.5, tol=1e-3)
    _assert_close(cz, 5.5, tol=1e-3)


# (o) Multi-source source-major + θ-minor ordering: 2 boxes + count=3,
# angle=360 → 4 new copies. Verifies BOTH that ids[0:2] are A's copies
# (source-major grouping) AND that within each group ids[i] is at θ=120°*i
# (k-order within source). Without the per-copy angular check, a regression
# that swapped A_θ1 with A_θ2 would still pass.
async def test_array_polar_multi_source_source_major_ordering(fresh_document):
    source_a = await _create_box([10, 0, 0], [11, 1, 1], "PolarMultiA")
    source_b = await _create_box([50, 0, 0], [51, 1, 1], "PolarMultiB")

    status, envelope = await _post_array_polar_raw({
        "ids": [source_a, source_b],
        "center": [0, 0, 0],
        "count": 3,
        "angle": 360,
    })
    assert status == 200
    data = _assert_polar_success(envelope)
    assert data["createdCount"] == 4
    assert len(data["ids"]) == 4

    # step = 120° (full circle, count=3). Compute the expected centroid for
    # each (source, k) pair by rotating the source centroid around the Z
    # axis about the origin. Source A centroid = [10.5, 0.5, 0.5]; B = [50.5,
    # 0.5, 0.5]. Z is preserved in both cases.
    step_rad = math.radians(120.0)

    def _rotated_xy(source_cx: float, source_cy: float, k: int) -> tuple[float, float]:
        theta = step_rad * k
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        return (
            cos_t * source_cx - sin_t * source_cy,
            sin_t * source_cx + cos_t * source_cy,
        )

    # ids[0] = A_θ1, ids[1] = A_θ2, ids[2] = B_θ1, ids[3] = B_θ2.
    expected_positions: list[tuple[float, float]] = []
    for k in (1, 2):
        expected_positions.append(_rotated_xy(10.5, 0.5, k))
    for k in (1, 2):
        expected_positions.append(_rotated_xy(50.5, 0.5, k))

    for new_id, (expected_cx, expected_cy) in zip(data["ids"], expected_positions):
        bbox = await _measure_bbox(new_id)
        cx, cy, cz = _bbox_center(bbox)
        _assert_close(cx, expected_cx, tol=1e-2)
        _assert_close(cy, expected_cy, tol=1e-2)
        _assert_close(cz, 0.5, tol=1e-3)  # Z preserved by Z-axis rotation.


# (p) Atomicity: arm /array/_debug/fail-next-copy at index=3, request a
# count=5 polar. Handler creates 2 copies, then synthetic null on the 3rd
# attempt triggers cleanup → response is operation_failed, ids empty, doc
# has zero net new objects. Requires ROOK_ENABLE_DEBUG_ROUTES=1; skip cleanly
# if the env var is unset.
async def test_array_polar_debug_failure_rolls_back_all_created_copies(fresh_document):
    source = await _create_box([10, 0, 0], [11, 1, 1], "PolarDebugRollback")

    initial_count = await _object_count()

    await _arm_fail_next_copy(3)  # may pytest.skip if debug routes disabled

    status, envelope = await _post_array_polar_raw({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 5,
        "angle": 360,
    })
    _assert_structured_error(envelope, "operation_failed")

    # Doc must show zero net new objects after rollback.
    final_count = await _object_count()
    assert final_count == initial_count, (
        f"Expected zero net new objects after rollback; before={initial_count}, "
        f"after={final_count}, delta={final_count - initial_count}"
    )


# Tool round-trip: confirm rhino_array_polar reaches the same handler with
# matching response shape.
async def test_array_polar_tool_round_trip(fresh_document):
    source = await _create_box([5, 0, 0], [6, 1, 1], "PolarToolRoundTrip")

    res = await _tool_array_polar({
        "ids": [source],
        "center": [0, 0, 0],
        "count": 4,
        "angle": 360,
    })
    assert res["mode"] == "polar"
    assert res["createdCount"] == 3
    assert len(res["ids"]) == 3
    assert res["count"] == 4
    assert res["angle"] == 360
    assert res["rotate"] is True
