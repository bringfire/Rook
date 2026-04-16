"""Live Rhino integration tests for companion-backed block replace-object-geometry.

These codify the regression coverage for PR #30 (closes #27). Each case below
was run by hand against a live Rhino during the PR review; this file exists
so those same assertions run automatically before the next change touches
this code.

Run (from `mcp_server/`):
    pytest -m requires_rhino tests/test_block_replace_object_geometry_live.py

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

import os
import tempfile

import pytest

from rook.server import _mcp_tool_executor

from .conftest import assert_bbox_x_range, assert_new_slot, set_legacy_basepoint_for_test

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


# ---------------------------------------------------------------------------
# Phase B migration tests (#28)
# ---------------------------------------------------------------------------


async def test_new_slot_populated_on_block_create(fresh_document):
    """After rhino_block_create with a non-origin basePoint, the idef has a
    RookBlockBasePointUserData attached with the correct value.

    Exercises Phase B's StoreDefinitionBasePoint dual-write path. Uses
    the introspection helper to prove the new slot was actually written,
    not just that the behavior read returns correct values (which could
    be served by the legacy user-string fallback during dual-write).
    """
    seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "CREATE_SEED")
    await _block_create("CREATE_NEW_SLOT", [seed], base_point=[5, 0, 0])

    # Behavior assertion: existing basePoint semantic still works.
    # (We re-use test 1's "origin pass-through" style check — after create,
    # the definition object[0] should be at local coords relative to the
    # basePoint, mirroring PR #30's behavior.)
    details = await _block_objects_detailed("CREATE_NEW_SLOT")
    assert details["objectCount"] == 1
    assert_bbox_x_range(details["objects"][0]["bbox"], -1, 1)

    # Primary assertion: the new-slot UserData is actually attached and
    # holds the expected basePoint. Without this check, the test could
    # pass via legacy fallback even if Phase B's Attach call silently
    # no-opped.
    await assert_new_slot("CREATE_NEW_SLOT", expected_base_point=(5.0, 0.0, 0.0))


async def test_disagreement_new_slot_wins(fresh_document):
    """New slot wins over legacy user-string when both are present but disagree
    — NATIVE read path.

    Scoped to native because RhinoCommon 8.0.23304's InstanceDefinition.UserData
    does not surface plugin-defined custom UserData instances to managed
    callers (diagnosed in #28 Phase C: Contains(UUID)=true but ud_list[i]
    returns null, Add(managed_ud) returns false). Managed reads therefore
    always fall through to the reflection-bridge legacy path during this
    transition — a graceful-degrade, not a disagreement-wins test. See
    design doc §3.3 for the native vs managed coexistence distinction.

    This test exercises `rhino_block_replace_geometry` (native-backed,
    calls LookupDefinitionBasePoint directly) instead of the companion-
    backed `rhino_block_replace_object_geometry`. The native read path
    does a true new-first lookup, so setting legacy to a divergent value
    must NOT affect the result.

    Setup: native dual-write on create puts new=(5,0,0), legacy=(5,0,0).
    The test-only endpoint clobbers ONLY the legacy user-string to
    (99,0,0), leaving the new UserData slot at (5,0,0).

    Assertion: native replace-geometry normalizes using (5,0,0) — the
    new-slot value — NOT (99,0,0). If the native read-side switch in
    Phase C regressed, this test would fail because the replacement
    would land at x∈[-99.5, -98.5] instead of x∈[-5.5, -4.5].

    No introspection helper is needed — the disagreement itself
    structurally isolates new-slot behavior via the observable bbox.
    """
    # Create block with basePoint=(5,0,0) via normal path (native dual-write).
    seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "DISAGREE_SEED")
    await _block_create("DISAGREE_BLOCK", [seed], base_point=[5, 0, 0])

    # Clobber legacy user-string to (99,0,0); new slot stays at (5,0,0).
    await set_legacy_basepoint_for_test("DISAGREE_BLOCK", (99.0, 0.0, 0.0))

    # Source at world origin. With new slot (5,0,0) → expected local
    # x∈[-5.5, -4.5]. With legacy (99,0,0) → expected local x∈[-99.5,
    # -98.5]. The native read-side switch must pick the new slot.
    source = await _create_brep([-0.5, -0.5, 0], [0.5, 0.5, 1], "DISAGREE_SRC")

    # rhino_block_replace_geometry is native-backed (HandleBlockReplaceGeometry),
    # which calls LookupDefinitionBasePoint — the function Phase C switched
    # to new-first.
    replace_result = await _mcp_tool_executor(
        "rhino_block_replace_geometry",
        {"name": "DISAGREE_BLOCK", "ids": [source], "deleteOriginals": True},
    )
    assert replace_result.get("success") is not False, (
        f"native replace-geometry failed: {replace_result!r}"
    )

    # Verify definition-local bbox: must be [-5.5, -4.5], NOT [-99.5, -98.5].
    details = await _block_objects_detailed("DISAGREE_BLOCK")
    assert details["objectCount"] == 1, (
        f"expected 1 object after replace-geometry, got {details!r}"
    )
    assert_bbox_x_range(details["objects"][0]["bbox"], -5.5, -4.5)


# ---------------------------------------------------------------------------
# Phase D migration tests (#28) — round-trip and preserve-path survival
# ---------------------------------------------------------------------------


async def test_save_load_roundtrip_preserves_basepoint(fresh_document):
    """The new-slot RookBlockBasePointUserData survives a .3dm save + reopen.

    Dual-write is irrelevant here — the legacy user-string is stored on
    the InstanceDefinition and trivially survives save/load, so a legacy
    read would pass even if UserData was lost at serialization time. The
    introspection helper reads the native slot directly, so a regression
    where ON_BinaryArchive drops our UserData payload on write or read
    manifests as an explicit introspection failure instead of silently
    degrading to legacy-only behavior.
    """
    seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "ROUNDTRIP_SEED")
    await _block_create("ROUNDTRIP_BLOCK", [seed], base_point=[5, 0, 0])

    # Pre-save sanity: new slot is populated.
    await assert_new_slot("ROUNDTRIP_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

    # Save to a temp file, drop the doc, reopen. NamedTemporaryFile with
    # delete=False because Rhino must be able to reopen the path after we
    # close the handle; we clean up in the `finally`. Path kept in native
    # OS form (backslashes on Windows): Rhino's scripted `_-Open` rejects
    # forward-slash paths on Windows with "did not change active document".
    tmp = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    tmp.close()
    save_path = tmp.name
    try:
        save_res = await _mcp_tool_executor(
            "rhino_document_ops", {"action": "save", "path": save_path}
        )
        assert save_res.get("success") is not False, f"save failed: {save_res!r}"

        new_res = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        assert new_res.get("success") is not False, f"new failed: {new_res!r}"

        open_res = await _mcp_tool_executor(
            "rhino_document_ops", {"action": "open", "path": save_path}
        )
        assert open_res.get("success") is not False, f"open failed: {open_res!r}"

        # Primary assertion: the slot is still attached with the correct
        # value after a full round-trip through the .3dm binary archive.
        await assert_new_slot("ROUNDTRIP_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

        # Behavior corroboration: the definition object's local bbox is
        # still (seed_world - basePoint) = [-1, 1] on X.
        details = await _block_objects_detailed("ROUNDTRIP_BLOCK")
        assert details["objectCount"] == 1
        assert_bbox_x_range(details["objects"][0]["bbox"], -1.0, 1.0)
    finally:
        try:
            os.unlink(save_path)
        except OSError:
            pass


async def test_block_duplicate_carries_basepoint(fresh_document):
    """rhino_block_duplicate copies basePoint onto the new definition.

    HandleBlockDuplicate constructs a fresh ON_InstanceDefinition for the
    duplicate and cannot rely on SDK copy-ctor metadata transfer through
    AddInstanceDefinition (design §3.4 Duplicate audit). Phase B therefore
    reads the source basePoint via LookupDefinitionBasePoint and calls
    StoreDefinitionBasePoint explicitly on the new idef.

    This test validates that explicit reattach — the source's basePoint
    must land on the duplicate's new-slot UserData (not just the legacy
    user-string, which would survive via the SDK's GetUserString copy).
    """
    seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "DUP_SRC_SEED")
    await _block_create("DUP_SRC_BLOCK", [seed], base_point=[5, 0, 0])

    dup_res = await _mcp_tool_executor(
        "rhino_block_duplicate",
        {"name": "DUP_SRC_BLOCK", "newName": "DUP_DST_BLOCK"},
    )
    assert dup_res.get("success") is not False, f"duplicate failed: {dup_res!r}"
    assert dup_res.get("newName") == "DUP_DST_BLOCK"

    # Primary assertion: basePoint carries to the new definition's new slot.
    await assert_new_slot("DUP_DST_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

    # Behavior corroboration: both definitions store identical local-coord
    # geometry for the same source world position.
    src_details = await _block_objects_detailed("DUP_SRC_BLOCK")
    dup_details = await _block_objects_detailed("DUP_DST_BLOCK")
    assert src_details["objectCount"] == dup_details["objectCount"] == 1
    src_bbox = src_details["objects"][0]["bbox"]
    dup_bbox = dup_details["objects"][0]["bbox"]
    assert src_bbox["min"] == dup_bbox["min"], (src_bbox, dup_bbox)
    assert src_bbox["max"] == dup_bbox["max"], (src_bbox, dup_bbox)


async def test_block_rebase_updates_new_slot(fresh_document):
    """rhino_block_rebase carries the adjusted basePoint through to the
    new-slot UserData on the live InstanceDefinition table entry.

    UpdateDefinitionBasePoint uses slice-copy (`ON_InstanceDefinition
    settings = *pDef`) + ModifyInstanceDefinition with the
    idef_userdata_setting mask. The assumption is that the SDK's copy
    ctor carries UserData via m_userdata_copycount=1 AND that
    ModifyInstanceDefinition applies the settings object's UserData to
    the live entry under the userdata-only mask. This test decides that.

    Setup: seed at world [5,0,0]→[6,1,1], basePoint=(5,0,0), definition
    geometry stored at local [0,0,0]→[1,1,1] (bbox_min = origin).

    Rebase call: anchor=bbox_min, targetPoint=(-2,0,0), axes=[x].
        definitionDelta = targetPoint - anchorPoint
                        = (-2,0,0) - (0,0,0) = (-2,0,0)  (axes=x filters other components to 0)
        newBase         = oldBase - definitionDelta
                        = (5,0,0) - (-2,0,0) = (7,0,0)

    If this test fails, escalate UpdateDefinitionBasePoint to
    direct-attach-on-live-entry per the handoff doc's "Known limitations
    #3" snippet.
    """
    seed = await _create_brep([5, 0, 0], [6, 1, 1], "REBASE_SEED")
    await _block_create("REBASE_BLOCK", [seed], base_point=[5, 0, 0])

    # Sanity: pre-rebase new slot is (5,0,0).
    await assert_new_slot("REBASE_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

    rebase_res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {
            "name": "REBASE_BLOCK",
            "anchor": "bbox_min",
            "targetPoint": [-2.0, 0.0, 0.0],
            "axes": ["x"],
            "dryRun": False,
        },
    )
    assert rebase_res.get("success") is not False, f"rebase failed: {rebase_res!r}"
    assert rebase_res.get("executed") is True, f"rebase not executed: {rebase_res!r}"

    # Primary assertion: rebase pushed newBase=(7,0,0) into the new slot.
    await assert_new_slot("REBASE_BLOCK", expected_base_point=(7.0, 0.0, 0.0))


async def test_preserve_sites_retain_basepoint(fresh_document):
    """The new-slot UserData survives add-objects, remove-objects, and
    replace-geometry on an existing InstanceDefinition.

    None of these sites touch basePoint metadata directly — they only
    rewrite geometry (ModifyInstanceDefinitionGeometry) or modify the
    idef's geometry list through SDK paths that must preserve attached
    UserData by contract. This test proves that contract holds end-to-end.

    If this test fails, do NOT weaken the invariant. Audit the specific
    preserve path that dropped UserData and patch it (design doc §3.4:
    "only patch code if the SDK path demonstrably drops metadata").
    """
    # Initial setup: block with one seed, basePoint=(5,0,0).
    seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "PRESERVE_SEED")
    await _block_create("PRESERVE_BLOCK", [seed], base_point=[5, 0, 0])
    await assert_new_slot("PRESERVE_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

    # 1. add-objects → new slot still (5,0,0).
    extra = await _create_brep([7, 0, 0], [7.5, 0.5, 0.5], "PRESERVE_EXTRA")
    add_res = await _mcp_tool_executor(
        "rhino_block_add_objects",
        {"name": "PRESERVE_BLOCK", "ids": [extra], "deleteOriginals": True},
    )
    assert add_res.get("success") is not False, f"add_objects failed: {add_res!r}"
    await assert_new_slot("PRESERVE_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

    # 2. remove-objects (drop the object we just added, index=1) → still (5,0,0).
    details_after_add = await _block_objects_detailed("PRESERVE_BLOCK")
    assert details_after_add["objectCount"] == 2, (
        f"expected 2 objects after add, got {details_after_add!r}"
    )
    rm_res = await _mcp_tool_executor(
        "rhino_block_remove_objects",
        {"name": "PRESERVE_BLOCK", "indices": [1]},
    )
    assert rm_res.get("success") is not False, f"remove_objects failed: {rm_res!r}"
    await assert_new_slot("PRESERVE_BLOCK", expected_base_point=(5.0, 0.0, 0.0))

    # 3. replace-geometry (wholesale) → still (5,0,0).
    replacement = await _create_brep([5.2, 0, 0], [5.8, 0.6, 0.6], "PRESERVE_REPLACEMENT")
    rep_res = await _mcp_tool_executor(
        "rhino_block_replace_geometry",
        {"name": "PRESERVE_BLOCK", "ids": [replacement], "deleteOriginals": True},
    )
    assert rep_res.get("success") is not False, f"replace_geometry failed: {rep_res!r}"
    await assert_new_slot("PRESERVE_BLOCK", expected_base_point=(5.0, 0.0, 0.0))
