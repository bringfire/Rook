"""Live-Rhino characterization tests for POST /block/distribute-along-curve.

Pins the first exotic-capability promotion:
  - doctrine: rook_docs/2026-04-22-exotic-capability-promotion-plan.md
  - scope:    rook_docs/2026-04-22-exotic-capability-pr1-scope.md

Pins:
  - mutation response envelope on success (createdCount, instanceIds, mode,
    parametersUsed, seedUsed, sampledPositions, sampledParameters, warnings)
  - structured {errorCode, errorMessage} on failure
  - mode-validation rejects accepted-but-ignored parameters (no
    documented-no-op footguns)
  - seeded randomness is deterministic across runs
  - vertical-tangent guard emits vertical_tangent_guard warning
  - atomic rollback on mid-loop failure via /block/_debug/fail-next-instance

Run:
    pytest -m requires_rhino \\
        mcp_server/tests/test_block_distribute_along_curve_live.py

Rhino must be running with RookNative loaded. Tests reset the document on
entry via the fresh_document fixture — run them in a throwaway session.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from .conftest import fresh_document, _is_error


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# ────────────────────────────────────────────────────────────────────────
# Fixture builders
# ────────────────────────────────────────────────────────────────────────


async def _create_line(
    start: list[float],
    end: list[float],
    name: str,
) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": start, "end": end, "name": name},
    )
    assert not _is_error(res), f"rhino_create LINE failed: {res!r}"
    return res["id"]


async def _create_box(
    corner1: list[float],
    corner2: list[float],
    name: str,
) -> str:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": corner1, "corner2": corner2, "name": name},
    )
    assert not _is_error(res), f"rhino_create BOX failed: {res!r}"
    return res["id"]


async def _create_block(object_ids: list[str], name: str) -> None:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor(
        "rhino_block_create",
        {"ids": object_ids, "name": name, "basePoint": [0, 0, 0]},
    )
    assert not _is_error(res), f"rhino_block_create failed: {res!r}"


async def _make_fixture_curve_and_block(
    curve_start: list[float] | None = None,
    curve_end: list[float] | None = None,
    block_name: str = "FixtureBlock",
) -> tuple[str, str]:
    """Create a line curve and one block definition. Returns (curveId, blockName)."""
    if curve_start is None:
        curve_start = [0, 0, 0]
    if curve_end is None:
        curve_end = [100, 0, 0]
    curve_id = await _create_line(curve_start, curve_end, "FixtureCurve")
    box_id = await _create_box([0, 0, 0], [1, 1, 1], "FixtureBoxSource")
    await _create_block([box_id], block_name)
    return curve_id, block_name


# ────────────────────────────────────────────────────────────────────────
# HTTP helpers
# ────────────────────────────────────────────────────────────────────────


async def _post_distribute_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(
            f"{base_url}/block/distribute-along-curve", json=body
        )
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(
            f"/block/distribute-along-curve returned non-JSON body: "
            f"{resp.text!r} ({ex!r})"
        )
    return resp.status_code, envelope


async def _get_objects_raw(
    params: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any]]:
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


async def _object_count() -> int:
    _, envelope = await _get_objects_raw({"limit": 1000})
    assert envelope.get("success") is True, f"/objects failed: {envelope!r}"
    return int(envelope["data"]["totalCount"])


async def _measure_bbox(obj_id: str) -> dict[str, Any]:
    from rook.server import _mcp_tool_executor

    res = await _mcp_tool_executor("rhino_measure_bbox", {"id": obj_id})
    assert not _is_error(res), f"rhino_measure_bbox failed: {res!r}"
    return res


async def _arm_fail_next_instance(index: int) -> None:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=10.0) as client:
        resp = await client.post(
            f"{base_url}/block/_debug/fail-next-instance", json={"index": index}
        )

    if resp.status_code == 403:
        pytest.skip(
            "Debug routes disabled. Set ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino "
            "process environment and restart Rhino to enable /block/_debug/* routes."
        )
    if resp.status_code != 200:
        pytest.fail(
            f"/block/_debug/fail-next-instance returned {resp.status_code}: {resp.text}"
        )


# ────────────────────────────────────────────────────────────────────────
# Assertion helpers
# ────────────────────────────────────────────────────────────────────────


def _assert_structured_error(envelope: dict[str, Any], expected_code: str) -> None:
    assert envelope.get("success") is False, f"Expected failure envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected structured error data: {envelope!r}"
    assert data.get("errorCode") == expected_code, (
        f"Expected errorCode={expected_code!r}, "
        f"got {data.get('errorCode')!r} in {envelope!r}"
    )
    assert isinstance(data.get("errorMessage"), str) and data["errorMessage"], (
        f"Expected non-empty errorMessage in {envelope!r}"
    )


def _assert_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success envelope: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    for key in (
        "createdCount",
        "instanceIds",
        "mode",
        "parametersUsed",
        "seedUsed",
        "warnings",
    ):
        assert key in data, f"Missing response key {key!r}: {envelope!r}"
    return data


def _assert_close(actual: float, expected: float, tol: float = 1e-4) -> None:
    assert abs(actual - expected) < tol, (
        f"Expected {expected!r}, got {actual!r} (tol={tol})"
    )


# ────────────────────────────────────────────────────────────────────────
# Contract tests — early-return paths
# ────────────────────────────────────────────────────────────────────────


async def test_contract_missing_curveId(fresh_document):
    _, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "blockNames": [block_name],
        "method": "fill",
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_missing_blockNames(fresh_document):
    curve_id, _ = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "method": "fill",
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_missing_method(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_empty_blockNames(fresh_document):
    curve_id, _ = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [],
        "method": "fill",
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_fill_with_spacing_rejected(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 5,
        "spacing": 3.0,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_fixedSpacing_with_count_rejected(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fixedSpacing",
        "spacing": 3.0,
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_fixedSpacing_with_placement_rejected(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fixedSpacing",
        "spacing": 3.0,
        "placement": "center",
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_fixedCount_with_distribution_rejected(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fixedCount",
        "count": 5,
        "spacing": 3.0,
        "distribution": "even",
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_keepUpright_with_orientation_world_rejected(fresh_document):
    # The canonical accepted-but-ignored footgun: keepUpright has no effect
    # under orientation='world'. Must be rejected, not silently accepted.
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 5,
        "orientation": "world",
        "keepUpright": True,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_randomRange_minGreaterThanMax_rejected(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 5,
        "scaleMode": "randomRange",
        "minScale": 1.5,
        "maxScale": 0.8,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_input")


async def test_contract_bogus_curveId_returns_not_found(fresh_document):
    # Syntactically-valid but document-absent UUID. Matches the pattern in
    # test_array_polar_live.py — nil UUID (00000000-...) is rejected by
    # ParseUuid as invalid_input before reaching the UI thread, so it would
    # not exercise the not_found path we want to pin here.
    _, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": "deadbeef-dead-beef-dead-beefdeadbeef",
        "blockNames": [block_name],
        "method": "fill",
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "not_found")


async def test_contract_all_missing_blockNames_returns_empty_pool(fresh_document):
    curve_id, _ = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": ["DoesNotExist_A", "DoesNotExist_B"],
        "method": "fill",
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "empty_pool")


# ────────────────────────────────────────────────────────────────────────
# Integration tests — full execution paths
# ────────────────────────────────────────────────────────────────────────


async def test_fill_even_deterministic_seeded(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    body = {
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 10,
        "distribution": "even",
        "seed": 42,
    }

    status1, env1 = await _post_distribute_raw(body)
    assert status1 == 200
    data1 = _assert_success(env1)
    assert data1["createdCount"] == 10
    assert data1["mode"] == "fill"
    assert data1["seedUsed"] == 42

    # Even distribution on a 100-unit line with count=10 should place at
    # arc lengths 0, 100/9, 200/9, ..., 100. Parameters are proportional
    # for a line.
    positions = data1["sampledPositions"]
    assert len(positions) == 10
    _assert_close(positions[0][0], 0.0)
    _assert_close(positions[-1][0], 100.0)


async def test_fill_random_seeded_determinism(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    body = {
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 10,
        "distribution": "random",
        "seed": 42,
    }

    status1, env1 = await _post_distribute_raw(body)
    assert status1 == 200
    data1 = _assert_success(env1)
    positions_first = data1["sampledPositions"]

    # Reset the document and run again with the same seed
    await fresh_document.__anext__() if False else None  # noqa: no-op, fixture already fresh
    # Rebuild fixtures for a clean second run in the same session
    curve_id2, block_name2 = await _make_fixture_curve_and_block(
        block_name="FixtureBlock2"
    )
    body2 = dict(body)
    body2["curveId"] = curve_id2
    body2["blockNames"] = [block_name2]

    status2, env2 = await _post_distribute_raw(body2)
    assert status2 == 200
    data2 = _assert_success(env2)
    positions_second = data2["sampledPositions"]

    # Same seed, same curve geometry → same positions.
    assert positions_first == positions_second


async def test_fixedSpacing_no_variation(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    body = {
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fixedSpacing",
        "spacing": 3.0,
        "seed": 7,
    }
    status, envelope = await _post_distribute_raw(body)
    assert status == 200
    data = _assert_success(envelope)
    positions = data["sampledPositions"]
    # With a 100-unit line, spacing 3.0, no variation: positions at 0, 3, 6, ..., 99
    assert len(positions) >= 33
    for i, pos in enumerate(positions):
        _assert_close(pos[0], i * 3.0)


async def test_fixedSpacing_with_variation_deterministic(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    body = {
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fixedSpacing",
        "spacing": 5.0,
        "spacingVariation": 1.0,
        "seed": 99,
    }
    status1, env1 = await _post_distribute_raw(body)
    assert status1 == 200
    data1 = _assert_success(env1)

    # Re-run in a clean fixture — same seed must yield same positions.
    curve_id2, block_name2 = await _make_fixture_curve_and_block(
        block_name="FixtureBlock2"
    )
    body2 = dict(body)
    body2["curveId"] = curve_id2
    body2["blockNames"] = [block_name2]
    status2, env2 = await _post_distribute_raw(body2)
    assert status2 == 200
    data2 = _assert_success(env2)

    assert data1["sampledPositions"] == data2["sampledPositions"]


@pytest.mark.parametrize("placement", ["start", "center", "end"])
async def test_fixedCount_span_exceeds_curve_rejected(fresh_document, placement):
    # length=5 curve, count=10, spacing=1 → requested span = 9 > length.
    # Silently truncating to 6 placements would violate the fixedCount
    # contract (N copies at fixed spacing). Must reject as span_exceeds_curve.
    # Applies under all three placements — start/center/end all have the
    # same overflow failure mode.
    short_curve = await _create_line([0, 0, 0], [5, 0, 0], "ShortCurve")
    box_id = await _create_box([0, 0, 0], [1, 1, 1], "SpanSrc")
    await _create_block([box_id], "SpanBlock")

    _, envelope = await _post_distribute_raw({
        "curveId": short_curve,
        "blockNames": ["SpanBlock"],
        "method": "fixedCount",
        "count": 10,
        "spacing": 1.0,
        "placement": placement,
    })
    _assert_structured_error(envelope, "span_exceeds_curve")


@pytest.mark.parametrize(
    "placement,expected_first_x",
    [("start", 0.0), ("center", 50.0 - 4.5), ("end", 100.0 - 9.0)],
)
async def test_fixedCount_placements(fresh_document, placement, expected_first_x):
    # spacing=1.0, count=10 → total span = 9.0 → on a 100-unit line the
    # expected first position depends on placement.
    curve_id, block_name = await _make_fixture_curve_and_block()
    body = {
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fixedCount",
        "count": 10,
        "spacing": 1.0,
        "placement": placement,
    }
    status, envelope = await _post_distribute_raw(body)
    assert status == 200
    data = _assert_success(envelope)
    positions = data["sampledPositions"]
    assert len(positions) == 10
    _assert_close(positions[0][0], expected_first_x)


async def test_orientation_world_translates_only(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    body = {
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 3,
        "orientation": "world",
    }
    status, envelope = await _post_distribute_raw(body)
    assert status == 200
    data = _assert_success(envelope)
    assert data["parametersUsed"]["orientation"] == "world"
    # keepUpright must not appear under orientation=world
    assert "keepUpright" not in data["parametersUsed"]


@pytest.mark.parametrize(
    "keep_upright,expected_max_z_min,expected_max_z_max",
    [
        # keepUpright=true  → tangent projected to XY, world Z remains the
        # up axis. The 5-unit X extent of the source box stays within the
        # XY plane, so the instance's max Z only reflects the source Y/Z
        # extents (unit box) plus the block's placement at curve start
        # (Z=0). Bbox max Z should stay near ~1.
        (True, 0.9, 1.5),
        # keepUpright=false → X axis aligns to the full 3D tangent
        # (1,0,1)/√2. The 5-unit X extent of the source box now points
        # along the inclined tangent, so its far tip sits at
        # (5/√2, 0, 5/√2) ≈ (3.54, 0, 3.54). Bbox max Z should land
        # around 3.5 — well above any value keepUpright=true could
        # produce. This is the observable difference between the two
        # transform branches.
        (False, 2.8, 4.5),
    ],
)
async def test_followCurve_keepUpright_modes_on_inclined_curve(
    fresh_document, keep_upright, expected_max_z_min, expected_max_z_max
):
    # 45°-inclined line: tangent is (1,0,1)/√2.
    curve_id = await _create_line([0, 0, 0], [10, 0, 10], "InclinedCurve")
    # Asymmetric source: long in X so the tilt is geometrically observable.
    box_id = await _create_box([0, 0, 0], [5, 1, 1], "InclinedSrc")
    await _create_block([box_id], "InclinedBlock")

    body = {
        "curveId": curve_id,
        "blockNames": ["InclinedBlock"],
        "method": "fill",
        "count": 1,
        "distribution": "even",
        "orientation": "followCurve",
        "keepUpright": keep_upright,
    }
    status, envelope = await _post_distribute_raw(body)
    assert status == 200
    data = _assert_success(envelope)
    assert data["parametersUsed"]["keepUpright"] is keep_upright
    assert data["createdCount"] == 1

    instance_id = data["instanceIds"][0]
    bbox = await _measure_bbox(instance_id)
    max_z = bbox["max"][2]
    assert expected_max_z_min <= max_z <= expected_max_z_max, (
        f"keepUpright={keep_upright}: expected bbox.max.z in "
        f"[{expected_max_z_min}, {expected_max_z_max}], got {max_z}. "
        f"If keepUpright branches do not differ observably in Z-extent, "
        f"the transform logic regressed to a single branch."
    )


async def test_vertical_tangent_emits_warning(fresh_document):
    # A vertical line curve causes the follow-curve frame to fall back to
    # world X. The handler must emit a structured warning.
    curve_id = await _create_line([0, 0, 0], [0, 0, 100], "VerticalCurve")
    box_id = await _create_box([0, 0, 0], [1, 1, 1], "SrcBox")
    await _create_block([box_id], "VertBlock")

    body = {
        "curveId": curve_id,
        "blockNames": ["VertBlock"],
        "method": "fill",
        "count": 3,
        "orientation": "followCurve",
    }
    status, envelope = await _post_distribute_raw(body)
    assert status == 200
    data = _assert_success(envelope)
    warnings = data["warnings"]
    assert any(
        w.startswith("vertical_tangent_guard:") for w in warnings
    ), f"Expected vertical_tangent_guard warning in {warnings!r}"


async def test_zero_length_curve_returns_invalid_geometry(fresh_document):
    # Degenerate line (start == end) has zero length.
    curve_id = await _create_line([5, 5, 0], [5, 5, 0], "ZeroCurve")
    box_id = await _create_box([0, 0, 0], [1, 1, 1], "SrcBox")
    await _create_block([box_id], "DegBlock")

    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": ["DegBlock"],
        "method": "fill",
        "count": 5,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "invalid_geometry")


async def test_seed_echo_when_omitted(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 3,
    })
    assert status == 200
    data = _assert_success(envelope)
    assert isinstance(data["seedUsed"], int)


async def test_rollback_on_synthetic_failure(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()

    baseline = await _object_count()

    # Arm synthetic failure on the 3rd instance attempt.
    await _arm_fail_next_instance(3)

    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name],
        "method": "fill",
        "count": 10,
        "seed": 1,
    })
    # Native sets HTTP 400 on structured-error envelopes; per gap-analysis
    # §4 that is existing drift. The agent-observable channel is the envelope
    # itself, not the HTTP status — assert on the envelope.
    _assert_structured_error(envelope, "operation_failed")

    # Rollback must have removed all instances created before the fault.
    # Final object count equals the baseline (curve + source box).
    final = await _object_count()
    assert final == baseline, (
        f"Expected rollback to restore baseline count {baseline}, "
        f"got {final}. Instances leaked on mid-loop failure."
    )


async def test_missing_name_emits_warning_but_succeeds(fresh_document):
    curve_id, block_name = await _make_fixture_curve_and_block()
    status, envelope = await _post_distribute_raw({
        "curveId": curve_id,
        "blockNames": [block_name, "ThisBlockDoesNotExist"],
        "method": "fill",
        "count": 5,
    })
    assert status == 200
    data = _assert_success(envelope)
    warnings = data["warnings"]
    assert any(
        "ThisBlockDoesNotExist" in w and w.startswith("missing_block_definition:")
        for w in warnings
    ), f"Expected missing_block_definition warning in {warnings!r}"
    assert data["createdCount"] == 5


# ────────────────────────────────────────────────────────────────────────
# Agent-level test — operation recognition only (Q7a smoke)
# ────────────────────────────────────────────────────────────────────────


@pytest.mark.skipif(
    not pytest.importorskip("dspy", reason="DSPy not installed"),
    reason="Intent-planner recognition test requires DSPy",
)
async def test_operation_recognition_smoke():
    """Q7a: DSPy extractor resolves natural-language intents to the new
    operation key.

    Recognition only — does not assert parameter population. Target: ≥80%
    of the 10 prompts return `block_distribute_along_curve`.
    """
    from rook.learning.intent_planner import IntentPlanner
    from rook.learning.intent_runtime import CapabilityRouter

    router = CapabilityRouter.get()
    planner = IntentPlanner(router)

    prompts = [
        "distribute blocks along this curve",
        "scatter blocks along the path",
        "array these blocks along the curve",
        "populate this curve with blocks",
        "place blocks along path",
        "distribute block instances along a curve",
        "scatter blocks across the road",
        "lay out blocks along the curve",
        "populate along curve with block instances",
        "arrange blocks along this path",
    ]

    hits = 0
    misses: list[tuple[str, str]] = []
    for prompt in prompts:
        plan = await planner.plan(prompt)
        operation = getattr(plan, "operation", None)
        if operation == "block_distribute_along_curve":
            hits += 1
        else:
            misses.append((prompt, str(operation)))

    hit_rate = hits / len(prompts)
    assert hit_rate >= 0.8, (
        f"Operation recognition below target: {hits}/{len(prompts)} = "
        f"{hit_rate:.0%}. Misses: {misses!r}. "
        f"If this fails, Q7a follow-up applies — see "
        f"rook_docs/2026-04-22-exotic-capability-pr1-scope.md."
    )
