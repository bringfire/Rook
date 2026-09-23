"""Live-Rhino characterization tests for POST /array/linear (Phase 1 PR-5).

Pins the direct-sdk array contract:
  - mutation response envelope on success
  - structured {errorCode, errorMessage} on failure
  - count semantics are total-including-source
  - ids are source-major, k-minor
  - rollback is explicit on mid-loop failure via the internal debug seam

Run:
    pytest -m requires_rhino mcp_server/tests/test_array_linear_live.py

Rhino must be running with RookNative loaded. Tests reset the document on
entry via the fresh_document fixture — run them in a throwaway session.
"""

from __future__ import annotations

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


async def _create_layer(name: str) -> None:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_layer_create", {"name": name})
    assert not _is_error(res), f"rhino_layer_create failed: {res!r}"


async def _measure_bbox(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_measure_bbox", {"id": obj_id})
    assert not _is_error(res), f"rhino_measure_bbox failed: {res!r}"
    return res


async def _tool_array_linear(body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_array_linear", body)
    assert not _is_error(res), f"rhino_array_linear failed: {res!r}"
    return res


async def _post_array_linear_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/array/linear", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(f"/array/linear returned non-JSON body: {resp.text!r} ({ex!r})")
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


def _assert_linear_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert data.get("mode") == "linear", f"Expected mode='linear': {envelope!r}"
    assert isinstance(data.get("ids"), list), f"Expected ids list: {envelope!r}"
    return data


def _assert_close(actual: float, expected: float, tol: float = 1e-5) -> None:
    assert abs(actual - expected) < tol, f"Expected {expected!r}, got {actual!r} (tol={tol})"


async def _object_count() -> int:
    _, envelope = await _get_objects_raw({"limit": 500})
    assert envelope.get("success") is True, f"/objects failed: {envelope!r}"
    return int(envelope["data"]["totalCount"])


async def _object_layer(obj_id: str) -> str:
    _, envelope = await _get_objects_raw({"limit": 500})
    assert envelope.get("success") is True, f"/objects failed: {envelope!r}"
    for obj in envelope["data"]["objects"]:
        if obj.get("id") == obj_id:
            return obj.get("layer", "")
    pytest.fail(f"Object {obj_id!r} not found in /objects response")


async def test_array_linear_single_source_happy_path(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearSource")

    status, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 5,
    })
    assert status == 200, f"Unexpected HTTP status: {status}"
    data = _assert_linear_success(envelope)
    assert data["createdCount"] == 4
    assert data["sourceIds"] == [source]
    assert len(data["ids"]) == 4

    expected_xs = [10.0, 20.0, 30.0, 40.0]
    for obj_id, expected_min_x in zip(data["ids"], expected_xs):
        bbox = await _measure_bbox(obj_id)
        _assert_close(bbox["min"][0], expected_min_x)
        _assert_close(bbox["max"][0], expected_min_x + 1.0)


async def test_array_linear_multi_source_source_major_ordering(fresh_document):
    a = await _create_box([0, 0, 0], [1, 1, 1], "LinearSourceA")
    b = await _create_box([100, 0, 0], [101, 1, 1], "LinearSourceB")

    status, envelope = await _post_array_linear_raw({
        "ids": [a, b],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 3,
    })
    assert status == 200, f"Unexpected HTTP status: {status}"
    data = _assert_linear_success(envelope)
    assert data["createdCount"] == 4
    assert len(data["ids"]) == 4

    mins = []
    for obj_id in data["ids"]:
        bbox = await _measure_bbox(obj_id)
        mins.append(round(bbox["min"][0], 4))

    assert mins == [10.0, 20.0, 110.0, 120.0], (
        f"Expected source-major ordering [A_k1, A_k2, B_k1, B_k2], got {mins!r}"
    )


async def test_array_linear_tool_success_count_one(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearCountOne")
    data = await _tool_array_linear({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 5,
        "count": 1,
    })
    assert data["createdCount"] == 0
    assert data["ids"] == []
    assert data["sourceIds"] == [source]


async def test_array_linear_non_integer_count_is_invalid_count(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearBadCount")
    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 3.5,
    })
    _assert_structured_error(envelope, "invalid_count")


async def test_array_linear_zero_count_is_invalid_count(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearZeroCount")
    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 0,
    })
    _assert_structured_error(envelope, "invalid_count")


async def test_array_linear_zero_direction_is_degenerate(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearZeroDir")
    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [0, 0, 0],
        "spacing": 10,
        "count": 3,
    })
    _assert_structured_error(envelope, "degenerate_direction")


async def test_array_linear_zero_spacing_is_invalid_spacing(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearZeroSpacing")
    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 0,
        "count": 3,
    })
    _assert_structured_error(envelope, "invalid_spacing")


async def test_array_linear_negative_spacing_is_invalid_spacing(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearNegativeSpacing")
    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": -5,
        "count": 3,
    })
    _assert_structured_error(envelope, "invalid_spacing")


async def test_array_linear_missing_source_aborts_without_partial_state(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearRealSource")
    before = await _object_count()

    _, envelope = await _post_array_linear_raw({
        "ids": [source, "00000000-0000-0000-0000-000000000001"],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 4,
    })
    _assert_structured_error(envelope, "not_found")

    after = await _object_count()
    assert after == before, f"Expected no new objects after not_found pre-flight failure; before={before}, after={after}"


async def test_array_linear_debug_failure_rolls_back_all_created_copies(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearDebugRollback")
    before = await _object_count()
    await _arm_fail_next_copy(3)

    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 5,
    })
    _assert_structured_error(envelope, "operation_failed")

    after = await _object_count()
    assert after == before, f"Expected rollback to restore object count; before={before}, after={after}"


async def test_array_linear_attribute_preservation_layer(fresh_document):
    await _create_layer("Foo")
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearLayerSource", layer="Foo")

    _, envelope = await _post_array_linear_raw({
        "ids": [source],
        "direction": [1, 0, 0],
        "spacing": 10,
        "count": 3,
    })
    data = _assert_linear_success(envelope)
    assert len(data["ids"]) == 2

    for obj_id in data["ids"]:
        layer = await _object_layer(obj_id)
        assert layer == "Foo", f"Expected copied object on layer Foo, got {layer!r}"


async def test_array_linear_tool_round_trip(fresh_document):
    source = await _create_box([0, 0, 0], [1, 1, 1], "LinearToolRoundTrip")
    data = await _tool_array_linear({
        "ids": [source],
        "direction": [-1, 0, 0],
        "spacing": 10,
        "count": 3,
    })
    assert data["createdCount"] == 2
    mins = []
    for obj_id in data["ids"]:
        bbox = await _measure_bbox(obj_id)
        mins.append(round(bbox["min"][0], 4))
    assert mins == [-10.0, -20.0]
