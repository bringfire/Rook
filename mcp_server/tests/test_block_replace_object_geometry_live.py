"""Live Rhino integration tests for companion-backed block replace-object-geometry.

These codify the regression coverage for PR #30 (closes #27). Each case below
was run by hand against a live Rhino during the PR review; this file exists
so those same assertions run automatically before the next change touches
this code.

Run:
    pytest -m requires_rhino mcp_server/tests/test_block_replace_object_geometry_live.py

Rhino must be running with RookNative + Rook companion loaded. Tests reset
the document to blank on entry — run in a throwaway session.

Note: `rhino_document_ops(action=new)` resets the geometry table but does
NOT appear to purge the InstanceDefinitions table in Rhino 8 — block
definitions from prior tests may still exist. Each test uses a unique
block-name prefix so cross-test name collisions don't mask real
regressions.

Scope (#31): storage-agnostic behavioral assertions only. Intentionally
does NOT cover:
- `basepoint_bridge_unavailable` — tied to the interim reflection bridge in
  PR #30; expected to become obsolete when storage migrates to
  `InstanceDefinition.UserDictionary` (issue #28).
- `transform_failed` per-item path — defensive; unreachable in practice
  with a rigid Translation xform on valid GeometryBase instances.
"""

from __future__ import annotations

import pytest

from rook.server import _mcp_tool_executor

from .conftest import assert_bbox_x_range

# Every test in this module needs Rhino; fixture handles graceful skip.
pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Small helpers (async wrappers over _mcp_tool_executor) --------------


async def _create_brep(corner1: list[float], corner2: list[float], name: str) -> str:
    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": corner1, "corner2": corner2, "name": name},
    )
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _create_cone(center: list[float], radius: float, height: float, name: str) -> str:
    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "CONE", "center": center, "radius": radius, "height": height, "name": name},
    )
    assert "id" in res, f"rhino_create CONE returned no id: {res!r}"
    return res["id"]


async def _block_create(name: str, ids: list[str], base_point: list[float]) -> dict:
    res = await _mcp_tool_executor(
        "rhino_block_create",
        {"name": name, "ids": ids, "basePoint": base_point, "replaceWithInstance": True},
    )
    assert res.get("name") == name, f"rhino_block_create unexpected: {res!r}"
    return res


async def _block_insert(name: str, point: list[float]) -> str:
    res = await _mcp_tool_executor(
        "rhino_block_insert",
        {"name": name, "point": point},
    )
    assert "instanceId" in res, f"rhino_block_insert returned no instanceId: {res!r}"
    return res["instanceId"]


async def _block_objects_detailed(name: str) -> dict:
    res = await _mcp_tool_executor("rhino_block_objects_detailed", {"name": name})
    assert "objects" in res, f"rhino_block_objects_detailed unexpected: {res!r}"
    return res


async def _replace_object(name: str, index: int, source_id: str) -> dict:
    res = await _mcp_tool_executor(
        "rhino_block_replace_object_geometry",
        {"name": name, "index": index, "sourceId": source_id, "deleteOriginal": True},
    )
    assert res.get("success") is not False, f"replace_object failed: {res!r}"
    return res


async def _replace_object_batch(items: list[dict]) -> dict:
    res = await _mcp_tool_executor(
        "rhino_block_replace_object_geometry_batch",
        {"items": items},
    )
    assert "routed" in res, f"replace batch unexpected shape: {res!r}"
    return res


# --- Tests ---------------------------------------------------------------


async def test_origin_basepoint_replace_passes_through(fresh_document):
    """Origin-basePoint block: replacement lands at source world coords.

    With basePoint=(0,0,0), `Translation(-basePoint)` is identity, so the
    replacement must appear at its world-coord position inside the
    definition. This exercises the origin fast path — regression check
    that the normalization branch doesn't mutate identity-case geometry.
    """
    seed = await _create_brep([0, 0, 0], [1, 1, 1], "SEED")
    source = await _create_brep([5, 0, 0], [5.5, 0.5, 0.5], "SRC")

    await _block_create("ORIGIN_BLOCK", [seed], base_point=[0, 0, 0])
    await _replace_object("ORIGIN_BLOCK", index=0, source_id=source)

    details = await _block_objects_detailed("ORIGIN_BLOCK")
    assert_bbox_x_range(details["objects"][0]["bbox"], 5.0, 5.5)


async def test_non_origin_basepoint_plain_geometry_zero_drift(fresh_document):
    """Non-origin basePoint, plain Brep source: definition stores local coords.

    Before PR #30: replaced object landed at world coords inside the
    definition (drift = +basePoint on every inserted instance).
    After PR #30: replaced object lands at (source_world - basePoint).

    Source box at world x in [-0.5, 0.5], basePoint (5,0,0) → definition
    object stored at local x in [-5.5, -4.5]. Two inserted instances at
    world (5,0,0) and (15,0,0) render the replacement at world [-0.5, 0.5]
    and [9.5, 10.5] respectively.
    """
    seed_a = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "SEED_A")
    seed_b = await _create_brep([6.5, 0, 0], [7, 0.5, 1], "SEED_B")
    source = await _create_brep([-0.5, -0.5, 0], [0.5, 0.5, 1], "SRC")

    block = await _block_create("PLAIN_BLOCK", [seed_a, seed_b], base_point=[5, 0, 0])
    instance_1_id = block["instanceId"]
    instance_2_id = await _block_insert("PLAIN_BLOCK", [15, 0, 0])

    await _replace_object("PLAIN_BLOCK", index=0, source_id=source)

    details = await _block_objects_detailed("PLAIN_BLOCK")
    # Definition object[0] (replaced): source world [-0.5, 0.5] - basePoint 5
    assert_bbox_x_range(details["objects"][0]["bbox"], -5.5, -4.5)
    # Definition object[1] (untouched): unchanged from creation. seed_b was
    # at world x in [6.5, 7] - basePoint 5 → local [1.5, 2.0].
    assert_bbox_x_range(details["objects"][1]["bbox"], 1.5, 2.0)

    # Instance 1 at world (5,0,0): replaced piece at world [-0.5, 0.5].
    inst1 = await _mcp_tool_executor("rhino_measure_bbox", {"id": instance_1_id})
    # Combined bbox includes replaced piece + untouched seed_b at world [6.5, 7].
    assert_bbox_x_range(inst1, -0.5, 7.0)

    # Instance 2 at world (15,0,0): replaced piece at world [9.5, 10.5],
    # untouched seed_b at world [16.5, 17.0]. Combined [9.5, 17.0].
    inst2 = await _mcp_tool_executor("rhino_measure_bbox", {"id": instance_2_id})
    assert_bbox_x_range(inst2, 9.5, 17.0)


async def test_nested_block_instance_source_composes_xform(fresh_document):
    """Nested block instance as replacement source — the Codex residual-risk case.

    Source is an InstanceReferenceGeometry (not plain Brep). PR #30 applies
    GeometryBase.Duplicate().Transform(worldToLocal); the question is whether
    that correctly composes the internal Xform (equivalent to native's
    `composed = xform * instObj->InstanceXform()`).

    Live-verify (PR #30): InstanceReferenceGeometry.Transform correctly
    composes the Xform. No CreateInstanceObject special-case needed.
    This test codifies that finding so any future SDK change breaks loudly.

    Setup: NESTED_INNER block (origin basePoint) with a cone. A
    NESTED_INNER instance at world (1, 0, 0). Target: NESTED_OUTER
    (basePoint=(5,0,0)) index 0.

    Expected definition-local bbox of the replaced instance: world-source
    minus basePoint = [0.7, 1.3] − 5 = [-4.3, -3.7].
    """
    # Outer block setup (basePoint=(5,0,0))
    seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "OUTER_SEED")
    block = await _block_create("NESTED_OUTER", [seed], base_point=[5, 0, 0])
    instance_1_id = block["instanceId"]
    instance_2_id = await _block_insert("NESTED_OUTER", [15, 0, 0])

    # Inner block setup (basePoint=origin); replaceWithInstance gives us
    # one instance at origin. Insert a second one at (1, 0, 0) to use as
    # the replacement source.
    inner_cone = await _create_cone([0, 0, 0], radius=0.3, height=2, name="INNER_SEED")
    await _block_create("NESTED_INNER", [inner_cone], base_point=[0, 0, 0])
    inner_inst_at_1 = await _block_insert("NESTED_INNER", [1, 0, 0])

    # Replace NESTED_OUTER index 0 (the Brep) with the inner instance.
    replaced = await _replace_object("NESTED_OUTER", index=0, source_id=inner_inst_at_1)
    assert replaced.get("newGeometryType") == "InstanceReference", (
        f"expected InstanceReference, got {replaced!r}"
    )

    details = await _block_objects_detailed("NESTED_OUTER")
    # Definition-local bbox of the inner reference: source world [0.7, 1.3]
    # minus basePoint 5 → local [-4.3, -3.7].
    assert_bbox_x_range(details["objects"][0]["bbox"], -4.3, -3.7)

    # Instance 1 at world (5,0,0): inner cone renders at world [0.7, 1.3].
    inst1 = await _mcp_tool_executor("rhino_measure_bbox", {"id": instance_1_id})
    assert_bbox_x_range(inst1, 0.7, 1.3)

    # Instance 2 at world (15,0,0): inner cone renders at world [10.7, 11.3].
    inst2 = await _mcp_tool_executor("rhino_measure_bbox", {"id": instance_2_id})
    assert_bbox_x_range(inst2, 10.7, 11.3)


async def test_batch_per_group_basepoint_independent_normalization(fresh_document):
    """Batch request crossing two definitions with different basePoints.

    Per-group basePoint lookup must fire once per idef group and apply the
    correct translation per group. If a single basePoint were reused across
    groups (a plausible regression), BATCH_B would inherit BATCH_A's
    basePoint and show drift.

    Item A: BATCH_A (bp=(5,0,0)) index 0 ← box at world [-0.25, 0.25]
            expected definition-local x ∈ [-5.25, -4.75]
    Item B: BATCH_B (bp=(20,0,0)) index 0 ← sphere at world [-0.3, 0.3]
            expected definition-local x ∈ [-20.3, -19.7]
    """
    # BATCH_A with bp=(5,0,0)
    seed_a = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "A_SEED")
    await _block_create("BATCH_A", [seed_a], base_point=[5, 0, 0])

    # BATCH_B with bp=(20,0,0)
    seed_b = await _create_brep([19, -0.5, 0], [21, 1.5, 2], "B_SEED")
    await _block_create("BATCH_B", [seed_b], base_point=[20, 0, 0])

    # Sources at the origin (distinct bboxes so we can tell them apart)
    src_a = await _create_brep([-0.25, -0.25, 0], [0.25, 0.25, 0.5], "SRC_A")
    src_b_sphere = await _mcp_tool_executor(
        "rhino_create",
        {"type": "SPHERE", "center": [0, 0, 0], "radius": 0.3, "name": "SRC_B"},
    )
    src_b = src_b_sphere["id"]

    batch = await _replace_object_batch([
        {"name": "BATCH_A", "index": 0, "sourceId": src_a, "deleteOriginal": True},
        {"name": "BATCH_B", "index": 0, "sourceId": src_b, "deleteOriginal": True},
    ])
    assert batch["routed"] == 2, f"expected routed=2, got {batch!r}"
    assert batch["skipped"] == 0, f"expected skipped=0, got {batch!r}"
    assert batch["errors"] == [], f"expected no errors, got {batch!r}"
    assert set(batch["deletedSources"]) == {src_a, src_b}, (
        f"expected both sources deleted, got {batch['deletedSources']!r}"
    )

    details_a = await _block_objects_detailed("BATCH_A")
    assert_bbox_x_range(details_a["objects"][0]["bbox"], -5.25, -4.75)

    details_b = await _block_objects_detailed("BATCH_B")
    assert_bbox_x_range(details_b["objects"][0]["bbox"], -20.3, -19.7)
