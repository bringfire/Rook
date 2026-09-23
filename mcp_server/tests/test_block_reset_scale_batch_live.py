"""Live-Rhino characterization tests for POST /block/reset-scale-batch.

Batch variant of /block/reset-scale. Reference pattern:
HandleBlockReplaceInstanceBatch (per-item validation with per-element
error records; request-order preserved). Deliberate forks from the
ParseInstanceIds family (silent-drop bad-shape, reject-empty) are
explicitly pinned as the new contract.

Contract pins:
  - Happy path: N scaled instances reset → per-id success with
    oldInstanceId / newInstanceId / scale [1,1,1]
  - **GUID-preservation**: oldInstanceId == newInstanceId on every
    success (matches single-instance rhythm + documented batch-family
    contract at BlocksHandler.cs:3314). Request-order preserved.
  - Per-element best-effort: malformed UUIDs → invalid_id; unknown
    UUID → not_found; non-instance object → not_instance.
    No case aborts the batch.
  - Empty `ids: []` → idempotent success no-op
    (explicit fork from ParseInstanceIds which rejects empty).
  - Duplicate id in request → both iterations succeed (second finds
    the recreated instance at the preserved GUID).

Run (from `mcp_server/`):
    pytest -m requires_rhino tests/test_block_reset_scale_batch_live.py

Rhino must be running with RookNative loaded.
"""

from __future__ import annotations

from typing import Any

from rook.bridge import native_client
import pytest

from rook.server import _mcp_tool_executor

from .conftest import (
    fresh_document,
    _is_error,
    _create_brep,
    _block_create,
    _block_insert,
)


pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Helpers --------------------------------------------------------------


async def _post_reset_scale_batch_raw(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    from rook.bridge import get_rhino_host

    base_url = get_rhino_host()
    if base_url is None:
        pytest.skip("Native plugin not discoverable; skipping live test.")

    async with native_client(timeout=15.0) as client:
        resp = await client.post(f"{base_url}/block/reset-scale-batch", json=body)
    try:
        envelope = resp.json()
    except Exception as ex:
        pytest.fail(
            f"/block/reset-scale-batch returned non-JSON body: {resp.text!r} ({ex!r})")
    return resp.status_code, envelope


def _assert_batch_success(envelope: dict[str, Any]) -> dict[str, Any]:
    assert envelope.get("success") is True, f"Expected success: {envelope!r}"
    data = envelope.get("data")
    assert isinstance(data, dict), f"Expected data dict: {envelope!r}"
    assert "modifiedCount" in data, f"Missing modifiedCount: {envelope!r}"
    assert "instances" in data, f"Missing instances: {envelope!r}"
    assert isinstance(data["instances"], list), f"instances not list: {envelope!r}"
    return data


async def _seed_scaled_block(block_name: str, scale: float, point: list[float]) -> str:
    """Create a one-brep block definition + insert a scaled instance.
    Returns the instance GUID."""
    corner1 = point
    corner2 = [point[0] + 1.0, point[1] + 1.0, point[2] + 1.0]
    brep_id = await _create_brep(corner1, corner2, name=f"brep-{block_name}")
    await _block_create(
        block_name, [brep_id], base_point=point, replace_with_instance=False
    )
    inst_id = await _block_insert(block_name, point, scale=scale)
    return inst_id


# --- Happy path ----------------------------------------------------------


async def test_batch_three_scaled_instances_reset(fresh_document):
    """3 instances scaled ≠ 1 → all reset; per-id success with
    oldInstanceId / newInstanceId / scale [1,1,1]; request-order preserved."""
    inst_a = await _seed_scaled_block("ResetBatchA", 2.0, [0, 0, 0])
    inst_b = await _seed_scaled_block("ResetBatchB", 3.5, [10, 0, 0])
    inst_c = await _seed_scaled_block("ResetBatchC", 0.5, [20, 0, 0])

    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [inst_a, inst_b, inst_c],
    })
    assert status == 200, f"HTTP {status}: {envelope!r}"
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 3, f"Expected modifiedCount=3: {envelope!r}"
    instances = data["instances"]
    assert len(instances) == 3, f"Expected 3 instances: {envelope!r}"

    # Request-order pin: instances[i].id == ids[i]
    for i, expected_id in enumerate([inst_a, inst_b, inst_c]):
        entry = instances[i]
        assert entry["id"] == expected_id, (
            f"Request-order violated at index {i}: expected {expected_id!r}, "
            f"got {entry!r}"
        )
        assert entry["success"] is True, f"Entry {i} failed: {entry!r}"
        assert entry["scale"] == [1.0, 1.0, 1.0], f"Scale not reset: {entry!r}"


async def test_batch_guid_preservation_pin(fresh_document):
    """GUID-preservation contract: oldInstanceId == newInstanceId.

    Documented at BlocksHandler.cs:3314 for transform-instance-batch;
    this pin verifies the same contract holds for reset-scale-batch.
    If CreateInstanceObject ever stopped honoring pre-filled m_uuid,
    this test would flip immediately.
    """
    inst = await _seed_scaled_block("ResetGuidPin", 2.0, [0, 10, 0])

    status, envelope = await _post_reset_scale_batch_raw({"ids": [inst]})
    assert status == 200
    data = _assert_batch_success(envelope)
    entry = data["instances"][0]
    assert entry["success"] is True
    assert entry["oldInstanceId"] == inst, f"old id mismatch: {entry!r}"
    assert entry["newInstanceId"] == inst, (
        f"GUID-preservation contract violated — oldInstanceId "
        f"({entry['oldInstanceId']!r}) != newInstanceId "
        f"({entry['newInstanceId']!r}): {entry!r}"
    )


async def test_batch_of_one_parity_with_single_route(fresh_document):
    """ids: [one] should match the single-instance route's response
    shape per-entry."""
    inst = await _seed_scaled_block("ResetBatchSingle", 2.5, [0, 20, 0])

    status, envelope = await _post_reset_scale_batch_raw({"ids": [inst]})
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 1
    entry = data["instances"][0]
    assert entry["id"] == inst
    assert entry["success"] is True
    assert entry["oldInstanceId"] == inst
    assert entry["newInstanceId"] == inst  # GUID preservation
    assert entry["scale"] == [1.0, 1.0, 1.0]


# --- Per-element best-effort (forks from ParseInstanceIds) --------------


async def test_batch_malformed_uuid_is_per_item_not_abort(fresh_document):
    """Non-string or malformed-UUID element → per-item invalid_id;
    batch continues. Explicit fork from ParseInstanceIds silent-drop."""
    good = await _seed_scaled_block("ResetMalformed", 2.0, [0, 30, 0])

    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [good, "not-a-uuid", good],
    })
    assert status == 200
    data = _assert_batch_success(envelope)
    # First good succeeds; bad is invalid_id; second good finds recreated
    # instance at the same (preserved) GUID and succeeds again.
    assert data["modifiedCount"] == 2, f"Expected 2 successes: {envelope!r}"
    instances = data["instances"]
    assert len(instances) == 3

    assert instances[0]["success"] is True
    assert instances[1]["success"] is False
    assert instances[1]["error"] == "invalid_id"
    assert instances[1]["id"] == "not-a-uuid", (
        f"invalid_id entry should echo raw value: {instances[1]!r}"
    )
    assert instances[2]["success"] is True


async def test_batch_non_string_element(fresh_document):
    """JSON number / null / object as an element → invalid_id with
    echoed raw value (not silently dropped)."""
    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [42, None, {"nope": True}],
    })
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 0
    instances = data["instances"]
    assert len(instances) == 3
    for entry in instances:
        assert entry["success"] is False
        assert entry["error"] == "invalid_id"


async def test_batch_unknown_uuid_per_item(fresh_document):
    """Unknown (well-formed) UUID → not_found per-item; batch continues."""
    import uuid as _uuid

    good = await _seed_scaled_block("ResetUnknown", 2.0, [0, 40, 0])
    fake = str(_uuid.uuid4())

    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [good, fake],
    })
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 1
    assert data["instances"][0]["success"] is True
    assert data["instances"][1]["success"] is False
    assert data["instances"][1]["error"] == "not_found"


async def test_batch_non_instance_object_per_item(fresh_document):
    """Non-instance object (e.g. a line) → not_instance per-item.
    Error code matches HandleBlockReplaceInstanceBatch:2310."""
    # Seed a real instance + a plain curve.
    inst = await _seed_scaled_block("ResetNonInstance", 2.0, [0, 50, 0])

    line_res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "LINE", "start": [0, 60, 0], "end": [1, 60, 0], "name": "PlainLine"},
    )
    assert not _is_error(line_res), f"line create failed: {line_res!r}"
    line_id = line_res["id"]

    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [inst, line_id],
    })
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 1
    assert data["instances"][0]["success"] is True
    assert data["instances"][1]["success"] is False
    assert data["instances"][1]["error"] == "not_instance", (
        f"Expected error='not_instance' (matches HandleBlockReplaceInstanceBatch "
        f"convention), got {data['instances'][1]!r}"
    )


# --- Fork pins: empty array + duplicate id ------------------------------


async def test_batch_empty_ids_is_idempotent_noop(fresh_document):
    """`ids: []` → success no-op. Explicit fork from ParseInstanceIds
    which rejects empty input at BlocksHandler.cpp:2480.

    Also pins the stricter "no fingerprint" contract flagged by Codex
    review of PR #77: an empty-ids request must NOT open an UndoScope
    and must NOT call Redraw. Verified here by reading the document's
    undo-record count before and after the no-op; equal counts prove
    the handler short-circuited before the UndoScope RAII. Matches
    the rhythm at UserTextHandler.cpp:710 for /usertext/*-delete.
    """
    # Pin the no-op contract: empty `ids: []` must NOT open UndoScope
    # or call Redraw. Measured via Rhino's NextUndoRecordSerialNumber,
    # which advances once per BeginUndoRecord.
    #
    # Baseline caveat (verified empirically 2026-04-20): every
    # `rhino_execute` call advances the serial by 1 because the
    # scripting host wraps each script in an undo scope. So the
    # contract-correct delta across "[probe1, handler, probe2]" is
    # exactly 1 — only from probe2's own scope. Delta ≥ 2 would prove
    # the handler between the probes opened a scope too. Delta ==
    # baseline-from-probe-alone is the load-bearing check.
    probe_code = (
        "import Rhino\n"
        "print(Rhino.RhinoDoc.ActiveDoc.NextUndoRecordSerialNumber)\n"
    )

    async def _probe_serial() -> int:
        res = await _mcp_tool_executor("rhino_execute", {"code": probe_code})
        assert not _is_error(res), f"undo serial probe failed: {res!r}"
        return int((res.get("output") or "0").strip().splitlines()[-1])

    pre_serial = await _probe_serial()

    status, envelope = await _post_reset_scale_batch_raw({"ids": []})
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 0
    assert data["instances"] == []

    post_serial = await _probe_serial()
    delta = post_serial - pre_serial
    # Expected: 1 (only from post_probe's own rhino_execute scope).
    # If the handler had opened its own UndoScope, delta would be ≥ 2.
    assert delta == 1, (
        f"No-op contract violated: NextUndoRecordSerialNumber advanced "
        f"{pre_serial} -> {post_serial} (delta {delta}); expected exactly 1 "
        f"(from the post-probe's own rhino_execute scope). Delta ≥ 2 means "
        f"the handler opened an UndoScope despite the empty-input "
        f"short-circuit. Fix: UserTextHandler.cpp:710 rhythm — return "
        f"before UndoScope+Redraw (Codex PR #77 review)."
    )


async def test_batch_duplicate_id_both_succeed(fresh_document):
    """Duplicate id in request → both iterations succeed; second finds
    the recreated instance at the preserved GUID. Pins the documented
    batch-family contract (BlocksHandler.cs:3314) against reset-scale-batch."""
    inst = await _seed_scaled_block("ResetDupe", 2.0, [0, 70, 0])

    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [inst, inst],
    })
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 2, (
        f"Duplicate id should process twice (GUID-preservation contract): "
        f"{envelope!r}"
    )
    for entry in data["instances"]:
        assert entry["success"] is True
        assert entry["oldInstanceId"] == inst
        assert entry["newInstanceId"] == inst


# --- Envelope / shape errors --------------------------------------------


async def test_batch_missing_ids(fresh_document):
    """Missing `ids` → top-level shape error (not per-item)."""
    status, envelope = await _post_reset_scale_batch_raw({})
    assert envelope.get("success") is False
    # Uses CRookServer::SendError (not SendErrorData) for top-level shape
    # errors — consistent with the single-instance reset and replace-instance-batch.
    # Data is a string, not a structured {errorCode, errorMessage}.
    data = envelope.get("data")
    assert data is not None, f"Expected error envelope: {envelope!r}"


async def test_batch_ids_not_array(fresh_document):
    """`ids` not an array → shape error."""
    status, envelope = await _post_reset_scale_batch_raw({"ids": "not-an-array"})
    assert envelope.get("success") is False


async def test_single_preserves_rotation_on_rotated_instance(fresh_document):
    """Single-instance companion to the batch test below. Fix bundled
    in the batch PR because BuildResetScaleXform is shared between
    both routes — any regression in the shared helper would surface
    via either test, but having both routes pinned prevents handler-
    level wrapping code from silently diverging."""
    await _seed_scaled_block("ResetRotatedSingle", scale=2.0, point=[30, 90, 0])
    # Delete the auto-inserted instance and re-insert with explicit rotation.
    rotated_inst = await _block_insert(
        "ResetRotatedSingle", [30, 90, 0], scale=2.0, rotation_degrees=45.0
    )

    res = await _mcp_tool_executor(
        "rhino_block_reset_scale",
        {"id": rotated_inst},
    )
    assert not _is_error(res), f"single reset-scale failed: {res!r}"

    post_bbox = await _mcp_tool_executor("rhino_measure_bbox", {"id": rotated_inst})
    assert not _is_error(post_bbox), f"bbox post-reset failed: {post_bbox!r}"
    min_pt = post_bbox.get("min") or post_bbox.get("bbox", {}).get("min")
    max_pt = post_bbox.get("max") or post_bbox.get("bbox", {}).get("max")
    assert min_pt is not None and max_pt is not None

    x_extent = max_pt[0] - min_pt[0]
    assert x_extent > 1.2, (
        f"Single-instance rotation-preservation contract violated — "
        f"X extent {x_extent:.4f} suggests rotation was destroyed. "
        f"Post-bbox: {post_bbox!r}"
    )
    assert x_extent < 1.5, (
        f"Single-instance scale-reset contract violated — X extent "
        f"{x_extent:.4f} > 1.5. Post-bbox: {post_bbox!r}"
    )


async def test_batch_preserves_rotation_on_rotated_instance(fresh_document):
    """Pins Codex #77-review finding 1: reset-scale MUST preserve
    rotation. Earlier code extracted only translation from oldXform,
    silently zeroing rotation on every rotated block instance — a
    behavioral regression since the public contract is "reset scale
    to 1,1,1", not "reset to identity orientation."

    Insert a block at 45° rotation with scale 2.0, batch-reset, and
    verify the rotation is preserved (the recreated instance's bbox
    is NOT axis-aligned at the origin it would be if rotation were
    destroyed). Scale IS reset: bbox dimensions match the definition's
    unit cube rather than the scaled 2x.
    """
    inst = await _seed_scaled_block(
        "ResetRotatedA",
        scale=2.0,
        point=[0, 90, 0],
    )
    # Retarget: reinsert with an explicit rotation that won't match
    # identity. _block_insert accepts rotation_degrees — delete the
    # already-inserted instance first, then re-insert with rotation.
    await _mcp_tool_executor("rhino_delete", {"ids": [inst]})
    rotated_inst = await _block_insert(
        "ResetRotatedA", [0, 90, 0], scale=2.0, rotation_degrees=45.0
    )

    # Measure bbox pre-reset: the rotated scaled instance has a larger
    # bbox than the unit cube because rotation expands the axis-aligned
    # bbox of a scaled box.
    pre_bbox = await _mcp_tool_executor("rhino_measure_bbox", {"id": rotated_inst})
    assert not _is_error(pre_bbox), f"bbox pre-reset failed: {pre_bbox!r}"

    status, envelope = await _post_reset_scale_batch_raw({"ids": [rotated_inst]})
    assert status == 200
    data = _assert_batch_success(envelope)
    assert data["modifiedCount"] == 1

    # The reset instance still reports scale [1,1,1] per the response
    # contract. Crucially, its bbox is NOT a pristine axis-aligned
    # unit cube — that would prove rotation was destroyed. The bbox
    # of a rotated unit cube has equal X and Y extents that are each
    # √2 for a 45° rotation (diagonal). If rotation were destroyed,
    # bbox would be [0,0,0]..[1,1,1] — a pure axis-aligned unit cube
    # at the insertion point.
    post_bbox = await _mcp_tool_executor("rhino_measure_bbox", {"id": rotated_inst})
    assert not _is_error(post_bbox), f"bbox post-reset failed: {post_bbox!r}"

    min_pt = post_bbox.get("min") or post_bbox.get("bbox", {}).get("min")
    max_pt = post_bbox.get("max") or post_bbox.get("bbox", {}).get("max")
    assert min_pt is not None and max_pt is not None, (
        f"Could not extract bbox min/max: {post_bbox!r}"
    )

    # 45°-rotated unit cube has X and Y extents of √2 ≈ 1.414. An
    # axis-aligned unit cube has extent 1.0. Any extent > 1.2 proves
    # rotation survived.
    x_extent = max_pt[0] - min_pt[0]
    y_extent = max_pt[1] - min_pt[1]
    assert x_extent > 1.2, (
        f"Rotation-preservation contract violated — X extent {x_extent:.4f} "
        f"suggests axis-aligned unit cube (rotation was destroyed). "
        f"Expected ~√2 ≈ 1.414 for a 45°-rotated unit cube. "
        f"Post-bbox: {post_bbox!r}"
    )
    assert y_extent > 1.2, (
        f"Rotation-preservation contract violated — Y extent {y_extent:.4f} "
        f"suggests axis-aligned unit cube. Post-bbox: {post_bbox!r}"
    )
    # Scale IS reset: extent ≤ √2 × 1 = 1.415, well under the
    # pre-reset ~2√2 ≈ 2.83 that a 2x-scaled 45°-rotated cube had.
    assert x_extent < 1.5, (
        f"Scale-reset contract violated — X extent {x_extent:.4f} > 1.5 "
        f"suggests scale was not reset. Post-bbox: {post_bbox!r}"
    )


async def test_batch_request_order_mixed_outcomes(fresh_document):
    """["good-A", "bad-uuid", "good-B"] — response instances[]
    mirrors request-index order: success / invalid_id / success.
    Load-bearing pin: if order were ever changed to group-by-outcome
    or sorted alphabetically, callers relying on positional
    correlation would silently break."""
    a = await _seed_scaled_block("ResetOrderA", 2.0, [0, 80, 0])
    b = await _seed_scaled_block("ResetOrderB", 2.0, [10, 80, 0])

    status, envelope = await _post_reset_scale_batch_raw({
        "ids": [a, "obviously-not-a-uuid", b],
    })
    assert status == 200
    data = _assert_batch_success(envelope)
    instances = data["instances"]
    assert len(instances) == 3

    assert instances[0]["id"] == a and instances[0]["success"] is True
    assert instances[1]["id"] == "obviously-not-a-uuid" and instances[1]["success"] is False
    assert instances[1]["error"] == "invalid_id"
    assert instances[2]["id"] == b and instances[2]["success"] is True
