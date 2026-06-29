"""Live-Rhino tests for exact-id object hygiene tools.

Run:
    python -m pytest -m requires_rhino mcp_server/tests/test_exact_id_object_hygiene_live.py -q

Rhino must be running with the current locally deployed RookNative plugin.
These tests reset the active document through the fresh_document fixture.
"""

from __future__ import annotations

from typing import Any

import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


MISSING_ID = "00000000-0000-0000-0000-000000000001"
MALFORMED_ID = "not-a-uuid"


async def _tool(name: str, body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(name, body)
    assert not _is_error(res), f"{name} failed: {res!r}"
    assert isinstance(res, dict), f"{name} returned non-dict result: {res!r}"
    return res


async def _tool_error(name: str, body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(name, body)
    assert _is_error(res), f"{name} unexpectedly succeeded: {res!r}"
    assert isinstance(res, dict), f"{name} error was non-dict: {res!r}"
    data = res.get("data")
    assert isinstance(data, dict), f"{name} error data was not structured: {res!r}"
    assert isinstance(data.get("errorCode"), str), f"{name} error has no code: {res!r}"
    assert isinstance(data.get("errorMessage"), str), f"{name} error has no message: {res!r}"
    return data


async def _create_point(
    name: str,
    x: float = 0.0,
    layer: str | None = None,
) -> str:
    body: dict[str, Any] = {"type": "POINT", "point": [x, 0.0, 0.0], "name": name}
    if layer is not None:
        body["layer"] = layer
    res = await _tool("rhino_create", body)
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return str(res["id"])


async def _create_layer(name: str, parent: str | None = None) -> None:
    body: dict[str, Any] = {"name": name}
    if parent is not None:
        body["parent"] = parent
    res = await _tool_or_error("rhino_layer_create", body)
    if _is_error(res):
        data = res.get("data") if isinstance(res, dict) else None
        message = str(data.get("errorMessage") if isinstance(data, dict) else data)
        assert "already exists" in message.lower(), (
            f"rhino_layer_create failed unexpectedly: {res!r}"
        )


async def _tool_or_error(name: str, body: dict[str, Any]) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(name, body)
    assert isinstance(res, dict), f"{name} returned non-dict result: {res!r}"
    return res


async def _object_snapshot(obj_id: str) -> dict[str, Any]:
    res = await _tool("rhino_objects", {"limit": 500})
    objects = res.get("objects")
    assert isinstance(objects, list), f"rhino_objects returned no objects list: {res!r}"
    for obj in objects:
        if isinstance(obj, dict) and str(obj.get("id", "")).lower() == obj_id.lower():
            return obj
    pytest.fail(f"Object {obj_id!r} not found in rhino_objects snapshot: {res!r}")


async def _get_usertext(obj_id: str) -> dict[str, str]:
    res = await _tool("rhino_usertext_object_get", {"id": obj_id})
    user_strings = res.get("userStrings")
    assert isinstance(user_strings, dict), (
        f"rhino_usertext_object_get returned malformed userStrings: {res!r}"
    )
    return user_strings


def _result_by_id(result: dict[str, Any], obj_id: str) -> dict[str, Any]:
    results = result.get("results")
    assert isinstance(results, list), f"Expected results list: {result!r}"
    for item in results:
        if isinstance(item, dict) and str(item.get("id", "")).lower() == obj_id.lower():
            return item
    pytest.fail(f"Result for id {obj_id!r} not found: {result!r}")


def _assert_counts(
    result: dict[str, Any],
    *,
    requested: int,
    modified: int,
    skipped: int,
) -> None:
    assert result.get("requestedCount") == requested
    assert result.get("modifiedCount") == modified
    assert result.get("skippedCount") == skipped


def _assert_error_code(error: dict[str, Any], code: str) -> None:
    assert error.get("errorCode") == code, f"Expected {code!r}: {error!r}"


def _snapshot_layer(snapshot: dict[str, Any]) -> str:
    layer = snapshot.get("layer")
    assert isinstance(layer, str), f"Snapshot missing layer: {snapshot!r}"
    return layer


def _snapshot_visible(snapshot: dict[str, Any]) -> bool:
    visible = snapshot.get("visible")
    assert isinstance(visible, bool), f"Snapshot missing visible bool: {snapshot!r}"
    return visible


async def test_object_visibility_changes_only_requested_ids(fresh_document):
    target_a = await _create_point("vis_target_a", 0.0)
    target_b = await _create_point("vis_target_b", 1.0)
    neighbor = await _create_point("vis_neighbor", 2.0)

    result = await _tool(
        "rhino_object_visibility",
        {"object_ids": [target_a, target_b], "visible": False},
    )

    _assert_counts(result, requested=2, modified=2, skipped=0)
    assert {item["id"].lower() for item in result["results"]} == {
        target_a.lower(),
        target_b.lower(),
    }
    for obj_id in (target_a, target_b):
        item = _result_by_id(result, obj_id)
        assert item["status"] == "modified"
        assert item["after"]["objectVisible"] is False
        assert item["after"]["effectivelyVisible"] is False

    assert _snapshot_visible(await _object_snapshot(target_a)) is False
    assert _snapshot_visible(await _object_snapshot(target_b)) is False
    assert _snapshot_visible(await _object_snapshot(neighbor)) is True


async def test_object_visibility_unchanged_count(fresh_document):
    obj_id = await _create_point("vis_unchanged", 0.0)

    result = await _tool(
        "rhino_object_visibility",
        {"object_ids": [obj_id], "visible": True},
    )

    _assert_counts(result, requested=1, modified=0, skipped=1)
    item = _result_by_id(result, obj_id)
    assert item["status"] == "unchanged"
    assert item["before"] == item["after"]


async def test_object_visibility_true_on_hidden_layer_reports_not_effective(
    fresh_document,
):
    await _create_layer("HygieneHidden")
    obj_id = await _create_point("vis_hidden_layer", 0.0, "HygieneHidden")
    await _tool("rhino_layer_visibility", {"name": "HygieneHidden", "visible": False})

    result = await _tool(
        "rhino_object_visibility",
        {"object_ids": [obj_id], "visible": True},
    )

    _assert_counts(result, requested=1, modified=0, skipped=1)
    item = _result_by_id(result, obj_id)
    assert item["after"]["objectVisible"] is True
    assert item["after"]["layerVisible"] is False
    assert item["after"]["effectivelyVisible"] is False


async def test_object_set_layer_changes_only_requested_ids(fresh_document):
    await _create_layer("Animation")
    await _create_layer("Actors", parent="Animation")
    target_a = await _create_point("layer_target_a", 0.0)
    target_b = await _create_point("layer_target_b", 1.0)
    neighbor = await _create_point("layer_neighbor", 2.0)

    result = await _tool(
        "rhino_object_set_layer",
        {"object_ids": [target_a, target_b], "layer": "Animation::Actors"},
    )

    _assert_counts(result, requested=2, modified=2, skipped=0)
    assert result["layer"]["path"] == "Animation::Actors"
    assert isinstance(result["layer"]["id"], str) and result["layer"]["id"]
    for obj_id in (target_a, target_b):
        item = _result_by_id(result, obj_id)
        assert item["status"] == "modified"
        assert item["after"]["layerPath"] == "Animation::Actors"

    assert _snapshot_layer(await _object_snapshot(target_a)) == "Animation::Actors"
    assert _snapshot_layer(await _object_snapshot(target_b)) == "Animation::Actors"
    assert _snapshot_layer(await _object_snapshot(neighbor)) != "Animation::Actors"


async def test_object_set_layer_missing_layer_rejects_without_mutation(
    fresh_document,
):
    obj_id = await _create_point("layer_missing_target", 0.0)
    before = await _object_snapshot(obj_id)

    error = await _tool_error(
        "rhino_object_set_layer",
        {"object_ids": [obj_id], "layer": "NoSuchLayerForHygieneTest"},
    )

    _assert_error_code(error, "invalid_input")
    after = await _object_snapshot(obj_id)
    assert _snapshot_layer(after) == _snapshot_layer(before)


async def test_object_set_layer_ambiguous_leaf_rejected_without_mutation(
    fresh_document,
):
    await _create_layer("HygieneParentA")
    await _create_layer("HygieneParentB")
    await _create_layer("SharedLeaf", parent="HygieneParentA")
    await _create_layer("SharedLeaf", parent="HygieneParentB")
    obj_id = await _create_point("layer_ambiguous_target", 0.0)
    before = await _object_snapshot(obj_id)

    error = await _tool_error(
        "rhino_object_set_layer",
        {"object_ids": [obj_id], "layer": "SharedLeaf"},
    )

    _assert_error_code(error, "invalid_input")
    assert "ambiguous" in error["errorMessage"].lower()
    after = await _object_snapshot(obj_id)
    assert _snapshot_layer(after) == _snapshot_layer(before)


async def test_usertext_batch_sets_requested_objects_and_returns_full_post_state(
    fresh_document,
):
    target_a = await _create_point("ut_target_a", 0.0)
    target_b = await _create_point("ut_target_b", 1.0)
    neighbor = await _create_point("ut_neighbor", 2.0)

    result = await _tool(
        "rhino_object_usertext_set_batch",
        {
            "items": [
                {
                    "id": target_a,
                    "userStrings": {
                        "Director::role": "lead",
                        "Director::take": "one",
                    },
                },
                {
                    "id": target_b,
                    "userStrings": {"Director::role": "support"},
                },
            ]
        },
    )

    _assert_counts(result, requested=2, modified=2, skipped=0)
    assert _result_by_id(result, target_a)["userStrings"] == {
        "Director::role": "lead",
        "Director::take": "one",
    }
    assert _result_by_id(result, target_b)["userStrings"] == {
        "Director::role": "support",
    }
    assert await _get_usertext(neighbor) == {}


async def test_usertext_batch_overwrite_and_unchanged_count(fresh_document):
    obj_id = await _create_point("ut_unchanged", 0.0)
    body = {
        "items": [
            {"id": obj_id, "userStrings": {"Director::role": "unchanged"}}
        ]
    }
    await _tool("rhino_object_usertext_set_batch", body)

    second = await _tool("rhino_object_usertext_set_batch", body)

    _assert_counts(second, requested=1, modified=0, skipped=1)
    item = _result_by_id(second, obj_id)
    assert item["status"] == "unchanged"
    assert item["userStrings"] == {"Director::role": "unchanged"}


async def test_usertext_batch_preserves_unrelated_keys(fresh_document):
    obj_id = await _create_point("ut_preserve", 0.0)
    await _tool(
        "rhino_usertext_object_set",
        {"id": obj_id, "userStrings": {"Existing::key": "keep"}},
    )

    result = await _tool(
        "rhino_object_usertext_set_batch",
        {
            "items": [
                {"id": obj_id, "userStrings": {"Director::role": "actor"}}
            ]
        },
    )

    item = _result_by_id(result, obj_id)
    assert item["userStrings"] == {
        "Existing::key": "keep",
        "Director::role": "actor",
    }


@pytest.mark.parametrize(
    "tool_name,body",
    [
        ("rhino_object_visibility", {"object_ids": [], "visible": False}),
        ("rhino_object_set_layer", {"object_ids": [], "layer": "Default"}),
        ("rhino_object_usertext_set_batch", {"items": []}),
    ],
)
async def test_empty_batches_rejected(fresh_document, tool_name, body):
    error = await _tool_error(tool_name, body)
    _assert_error_code(error, "invalid_input")


@pytest.mark.parametrize(
    "tool_name,body_builder",
    [
        (
            "rhino_object_visibility",
            lambda obj_id: {"object_ids": [obj_id, obj_id], "visible": False},
        ),
        (
            "rhino_object_set_layer",
            lambda obj_id: {"object_ids": [obj_id, obj_id], "layer": "Default"},
        ),
    ],
)
async def test_duplicate_object_ids_rejected_without_mutation(
    fresh_document,
    tool_name,
    body_builder,
):
    obj_id = await _create_point("duplicate_ids", 0.0)
    before = await _object_snapshot(obj_id)

    error = await _tool_error(tool_name, body_builder(obj_id))

    _assert_error_code(error, "invalid_input")
    assert "duplicate" in error["errorMessage"].lower()
    after = await _object_snapshot(obj_id)
    assert after == before


async def test_usertext_batch_duplicate_item_ids_rejected_without_mutation(
    fresh_document,
):
    obj_id = await _create_point("ut_duplicate_ids", 0.0)
    before = await _get_usertext(obj_id)

    error = await _tool_error(
        "rhino_object_usertext_set_batch",
        {
            "items": [
                {"id": obj_id, "userStrings": {"Director::role": "first"}},
                {"id": obj_id, "userStrings": {"Director::role": "second"}},
            ]
        },
    )

    _assert_error_code(error, "invalid_input")
    assert "duplicate" in error["errorMessage"].lower()
    assert await _get_usertext(obj_id) == before


@pytest.mark.parametrize(
    "tool_name,body",
    [
        ("rhino_object_visibility", {"object_ids": [MALFORMED_ID], "visible": False}),
        ("rhino_object_set_layer", {"object_ids": [MALFORMED_ID], "layer": "Default"}),
        (
            "rhino_object_usertext_set_batch",
            {
                "items": [
                    {
                        "id": MALFORMED_ID,
                        "userStrings": {"Director::role": "actor"},
                    }
                ]
            },
        ),
    ],
)
async def test_malformed_uuid_rejected(fresh_document, tool_name, body):
    error = await _tool_error(tool_name, body)
    _assert_error_code(error, "invalid_input")


@pytest.mark.parametrize(
    "tool_name,body_builder,assert_unchanged",
    [
        (
            "rhino_object_visibility",
            lambda obj_id: {"object_ids": [MISSING_ID, obj_id], "visible": False},
            lambda before, after: after == before,
        ),
        (
            "rhino_object_set_layer",
            lambda obj_id: {"object_ids": [MISSING_ID, obj_id], "layer": "Default"},
            lambda before, after: after == before,
        ),
        (
            "rhino_object_usertext_set_batch",
            lambda obj_id: {
                "items": [
                    {
                        "id": MISSING_ID,
                        "userStrings": {"Director::role": "missing"},
                    },
                    {
                        "id": obj_id,
                        "userStrings": {"Director::role": "should_not_land"},
                    },
                ]
            },
            lambda before, after: after == before,
        ),
    ],
)
async def test_missing_object_id_rejected_before_mutation(
    fresh_document,
    tool_name,
    body_builder,
    assert_unchanged,
):
    obj_id = await _create_point("missing_id_guard", 0.0)
    before = (
        await _get_usertext(obj_id)
        if tool_name == "rhino_object_usertext_set_batch"
        else await _object_snapshot(obj_id)
    )

    error = await _tool_error(tool_name, body_builder(obj_id))

    _assert_error_code(error, "not_found")
    after = (
        await _get_usertext(obj_id)
        if tool_name == "rhino_object_usertext_set_batch"
        else await _object_snapshot(obj_id)
    )
    assert_unchanged(before, after)


@pytest.mark.parametrize(
    "tool_name,body_builder",
    [
        (
            "rhino_object_visibility",
            lambda obj_id: {"object_ids": [obj_id], "visible": False},
        ),
        (
            "rhino_object_set_layer",
            lambda obj_id: {"object_ids": [obj_id], "layer": "Default"},
        ),
        (
            "rhino_object_usertext_set_batch",
            lambda obj_id: {
                "items": [
                    {"id": obj_id, "userStrings": {"Director::role": "deleted"}}
                ]
            },
        ),
    ],
)
async def test_deleted_object_id_rejected(fresh_document, tool_name, body_builder):
    obj_id = await _create_point("deleted_id", 0.0)
    await _tool("rhino_delete", {"ids": [obj_id]})

    error = await _tool_error(tool_name, body_builder(obj_id))

    _assert_error_code(error, "not_found")


@pytest.mark.parametrize(
    "user_strings",
    [
        {"": "value"},
        {"Director::role": ""},
        {"Director::role": 12},
        {"Director::role": None},
    ],
)
async def test_usertext_batch_rejects_invalid_keys_and_values(
    fresh_document,
    user_strings,
):
    obj_id = await _create_point("ut_invalid", 0.0)
    before = await _get_usertext(obj_id)

    error = await _tool_error(
        "rhino_object_usertext_set_batch",
        {"items": [{"id": obj_id, "userStrings": user_strings}]},
    )

    _assert_error_code(error, "invalid_input")
    assert await _get_usertext(obj_id) == before


@pytest.mark.parametrize(
    "tool_name,body",
    [
        (
            "rhino_object_visibility",
            {
                "object_ids": [
                    f"11111111-1111-1111-1111-{i:012d}" for i in range(501)
                ],
                "visible": False,
            },
        ),
        (
            "rhino_object_set_layer",
            {
                "object_ids": [
                    f"11111111-1111-1111-1111-{i:012d}" for i in range(501)
                ],
                "layer": "Default",
            },
        ),
        (
            "rhino_object_usertext_set_batch",
            {
                "items": [
                    {
                        "id": f"11111111-1111-1111-1111-{i:012d}",
                        "userStrings": {"Director::role": "actor"},
                    }
                    for i in range(501)
                ]
            },
        ),
    ],
)
async def test_501_boundary_rejected(fresh_document, tool_name, body):
    error = await _tool_error(tool_name, body)
    _assert_error_code(error, "invalid_input")
    assert "500" in error["errorMessage"]
