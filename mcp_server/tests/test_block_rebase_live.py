"""Live-Rhino characterization tests for rhino_block_rebase and
rhino_block_rebase_recursive.

Pins the three-part rebase invariant (geometry rewrite + basePoint sync +
direct doc instance compensation) before the #26 helper extraction. See
docs/plans/2026-04-16-block-local-frame-helper-design.md.

Run (from repo root):
    pytest -m requires_rhino mcp_server/tests/test_block_rebase_live.py

Rhino must be running with RookNative + Rook companion loaded and
ROOK_ENABLE_DEBUG_ROUTES=1 in the Rhino process environment (needed by
assert_new_slot's debug route). Tests reset the document on entry — run
in a throwaway session.
"""

from __future__ import annotations

import math

import pytest

from rook.server import _mcp_tool_executor

from .conftest import (
    assert_new_slot,
    fresh_document,
    _is_error,
    _create_brep,
    _block_create,
    _block_insert,
    _measure_world_bbox,
    _block_instances,
    _block_objects_detailed,
)

# Every test here needs Rhino; fresh_document handles graceful skip.
pytestmark = [pytest.mark.requires_rhino, pytest.mark.asyncio]


# --- Fixture factories ----------------------------------------------------


async def _fixture_single_rebase(
    block_name: str = "REBASE_LEAF",
    leaf_seed_world_min: list[float] = None,
    leaf_seed_world_max: list[float] = None,
    leaf_base_point: list[float] = None,
    instance_insertion: tuple[float, float, float] = (10.0, 3.0, 0.0),
    instance_scale: float = 1.5,
    instance_rotation_degrees: float = 30.0,
) -> dict:
    """Fixture A — single-rebase.

    One leaf definition (created with replace_with_instance=False so no
    auto-instance) plus one explicit direct doc instance with non-identity
    xform. The non-identity scale/rotation gives the oldXform *
    compensation(-delta) post-multiplication real teeth — a pure-translation
    instance could not distinguish compose-then-translate from
    translate-then-compose.
    """
    if leaf_seed_world_min is None:
        leaf_seed_world_min = [5, 0, 0]
    if leaf_seed_world_max is None:
        leaf_seed_world_max = [6, 1, 1]
    if leaf_base_point is None:
        leaf_base_point = [5, 0, 0]

    seed_id = await _create_brep(
        leaf_seed_world_min, leaf_seed_world_max, f"{block_name}_SEED"
    )
    await _block_create(
        block_name,
        [seed_id],
        base_point=leaf_base_point,
        replace_with_instance=False,
    )
    inst_id = await _block_insert(
        block_name,
        instance_insertion,
        scale=instance_scale,
        rotation_degrees=instance_rotation_degrees,
    )
    return {
        "block_name": block_name,
        "instance_id": inst_id,
        "leaf_base_point": leaf_base_point,
    }


async def _fixture_recursive_rebase(
    leaf_name: str = "RR_LEAF",
    parent_name: str = "RR_PARENT",
    leaf_base_point: list[float] = None,
    parent_base_point: list[float] = None,
    leaf_seed_world_min: list[float] = None,
    leaf_seed_world_max: list[float] = None,
    parent_seed_world_min: list[float] = None,
    parent_seed_world_max: list[float] = None,
    leaf_instance_insertion: tuple[float, float, float] = (10.0, 3.0, 0.0),
    leaf_instance_scale: float = 1.5,
    leaf_instance_rotation_degrees: float = 30.0,
    parent_instance_insertion: tuple[float, float, float] = (40.0, 40.0, 0.0),
    parent_instance_scale: float = 1.2,
    parent_instance_rotation_degrees: float = 15.0,
) -> dict:
    """Fixture B — recursive-rebase.

    Leaf def (non-origin basePoint, no auto-instance) + parent def
    (non-origin basePoint, no auto-instance) containing one nested ref to
    leaf + one plain-geom seed. Plus exactly one direct doc leaf instance
    and exactly one direct doc parent instance, both with non-identity
    xforms to give the compensation invariants teeth.

    Construction primary path:
      1. Create leaf seed brep, _block_create leaf with
         replace_with_instance=False.
      2. Create parent seed brep.
      3. Insert a leaf instance at origin to serve as the nested ref
         inside the parent def.
      4. _block_create parent_name with [parent_seed_id, nested_leaf_id],
         replace_with_instance=False.
         IMPORTANT: if rhino_block_create rejects instance-object ids
         as seeds, fall back to creating the parent with
         [parent_seed_id] only and then rhino_block_add_objects for
         the nested ref.
      5. Explicitly _block_insert one leaf instance (non-identity xform).
      6. Explicitly _block_insert one parent instance (non-identity xform).
    """
    if leaf_base_point is None:
        leaf_base_point = [5, 0, 0]
    if parent_base_point is None:
        parent_base_point = [2, 2, 0]
    if leaf_seed_world_min is None:
        leaf_seed_world_min = [5, 0, 0]
    if leaf_seed_world_max is None:
        leaf_seed_world_max = [6, 1, 1]
    if parent_seed_world_min is None:
        parent_seed_world_min = [20, 20, 0]
    if parent_seed_world_max is None:
        parent_seed_world_max = [21, 21, 1]

    # Step 1: leaf definition, no auto-instance.
    leaf_seed_id = await _create_brep(
        leaf_seed_world_min, leaf_seed_world_max, f"{leaf_name}_SEED"
    )
    await _block_create(
        leaf_name, [leaf_seed_id],
        base_point=leaf_base_point,
        replace_with_instance=False,
    )

    # Step 2: parent seed as loose doc geometry.
    parent_seed_id = await _create_brep(
        parent_seed_world_min, parent_seed_world_max, f"{parent_name}_SEED"
    )

    # Step 3: insert a leaf instance at identity to serve as nested ref.
    nested_ref_id = await _block_insert(leaf_name, (0.0, 0.0, 0.0))

    # Step 4: create parent def with both seeds. If rhino_block_create
    # rejects the instance-id seed, fall back to add_objects per docstring.
    #
    # IMPORTANT: rhino_block_create(replaceWithInstance=False) does NOT
    # delete source objects (see BlocksHandler.cpp:1064). On the primary
    # path, nested_ref_id survives as a doc-level leaf instance after
    # parent creation — we must explicitly delete it below so the fixture
    # invariant "exactly one direct doc leaf instance" holds. The
    # fallback path via rhino_block_add_objects defaults to
    # deleteOriginals=True (BlocksHandler.cpp:1523), which already removes
    # nested_ref_id, so the explicit delete is skipped there.
    primary_path_ok = False
    try:
        await _block_create(
            parent_name,
            [parent_seed_id, nested_ref_id],
            base_point=parent_base_point,
            replace_with_instance=False,
        )
        primary_path_ok = True
    except AssertionError:
        await _block_create(
            parent_name, [parent_seed_id],
            base_point=parent_base_point,
            replace_with_instance=False,
        )
        add_res = await _mcp_tool_executor(
            "rhino_block_add_objects",
            {"name": parent_name, "ids": [nested_ref_id]},
        )
        assert add_res.get("success") is not False, (
            f"block_add_objects fallback failed: {add_res!r}"
        )

    if primary_path_ok:
        # Remove the orphaned doc-level leaf instance left behind by
        # rhino_block_create(replaceWithInstance=False). Without this,
        # fixture ends up with two direct doc leaf instances (this one +
        # the explicit step-5 insert below), breaking the len==1
        # invariant used by tests 8, 3 etc. See plan / finding from
        # review round 3.
        del_res = await _mcp_tool_executor(
            "rhino_delete", {"ids": [nested_ref_id]},
        )
        assert del_res.get("success") is not False, (
            f"rhino_delete(nested_ref_id) failed: {del_res!r}"
        )

    # Step 5 + 6: explicit direct doc instances, non-identity xforms.
    leaf_inst_id = await _block_insert(
        leaf_name,
        leaf_instance_insertion,
        scale=leaf_instance_scale,
        rotation_degrees=leaf_instance_rotation_degrees,
    )
    parent_inst_id = await _block_insert(
        parent_name,
        parent_instance_insertion,
        scale=parent_instance_scale,
        rotation_degrees=parent_instance_rotation_degrees,
    )

    return {
        "leaf_name": leaf_name,
        "parent_name": parent_name,
        "leaf_instance_id": leaf_inst_id,
        "parent_instance_id": parent_inst_id,
        "leaf_base_point": leaf_base_point,
        "parent_base_point": parent_base_point,
    }


# --- Common assertion helpers --------------------------------------------


def _assert_bbox_close(bbox_a: dict, bbox_b: dict, tol: float = 1e-5) -> None:
    """Assert two world bboxes agree on min and max within tolerance.

    Default tol is 1e-5 to match assert_bbox_x_range; Rhino's bbox returns
    on InstanceReferenceGeometry carry float32 representation error.
    """
    for key in ("min", "max"):
        for axis, (a, b) in enumerate(zip(bbox_a[key], bbox_b[key])):
            assert math.isclose(a, b, abs_tol=tol), (
                f"bbox.{key}[{axis}] mismatch: {a!r} vs {b!r} (tol={tol}); "
                f"before={bbox_a!r} after={bbox_b!r}"
            )


def _error_text(res: dict) -> str:
    """Extract a best-effort error string from a failed tool response.

    MCP wraps upstream native errors as {"success": True, "data":
    "Error: <msg>"} because json.loads fails on the plain-text error
    payload and _mcp_tool_executor falls back to that shape (see
    server.py:283 and server.py:15507). So the "data" field is where
    the error text actually lives on these paths — not "error".
    Use _is_error(res) from conftest to detect errors, then this
    helper to get the message text.
    """
    return str(res.get("error") or res.get("data") or res)


# --- Test 1: single rebase — basePoint shifts by inverse delta -----------


async def test_rebase_shifts_basepoint_by_inverse_delta(fresh_document):
    """Lifted + extended from test_block_replace_object_geometry_live.py::
    test_block_rebase_updates_new_slot. Pins: basePoint changes by -delta."""
    fx = await _fixture_single_rebase()
    await assert_new_slot(fx["block_name"], expected_base_point=(5.0, 0.0, 0.0))

    res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {
            "name": fx["block_name"],
            "anchor": "bbox_min",
            "targetPoint": [-2.0, 0.0, 0.0],
            "axes": ["x"],
            "dryRun": False,
        },
    )
    assert res.get("success") is not False, f"rebase failed: {res!r}"
    assert res.get("executed") is True, f"rebase not executed: {res!r}"

    # oldBase (5,0,0); delta = targetPoint - local bbox_min = (-2,0,0);
    # newBase = oldBase - delta = (7,0,0).
    await assert_new_slot(fx["block_name"], expected_base_point=(7.0, 0.0, 0.0))


# --- Test 2: single rebase — world bbox of direct instance unchanged -----


async def test_rebase_preserves_world_geometry_of_direct_instances(fresh_document):
    """Non-identity xform teeth: the seeded instance has scale=1.5,
    rotation=30°. World bbox must be numerically identical before and
    after rebase, after reacquiring the post-rebase instance id via the
    verbose response's recreatedInstances mapping.
    """
    fx = await _fixture_single_rebase()
    bbox_before = await _measure_world_bbox(fx["instance_id"])

    res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {
            "name": fx["block_name"],
            "anchor": "bbox_min",
            "targetPoint": [-2.0, 0.0, 0.0],
            "axes": ["x"],
            "dryRun": False,
            "verbose": True,
        },
    )
    assert res.get("executed") is True, f"rebase not executed: {res!r}"

    # HandleBlockRebase deletes + recreates each direct doc instance with
    # a fresh UUID. Map the old id to the post-rebase new id via the
    # verbose response before measuring.
    recreated = res.get("recreatedInstances") or []
    new_id = next(
        (entry["newId"] for entry in recreated if entry.get("oldId") == fx["instance_id"]),
        None,
    )
    assert new_id is not None, (
        f"old instance id {fx['instance_id']!r} not found in "
        f"recreatedInstances: {res!r}"
    )

    bbox_after = await _measure_world_bbox(new_id)
    _assert_bbox_close(bbox_before, bbox_after)


# --- Test 3: single rebase — instance count preserved --------------------


async def test_rebase_preserves_instance_count(fresh_document):
    """Fixture has exactly one direct doc instance. After rebase, still
    exactly one. (Rebase deletes + recreates each instance, so count
    preservation is a non-trivial invariant, not a trivial identity.)"""
    fx = await _fixture_single_rebase()
    count_before = len(await _block_instances(fx["block_name"]))
    assert count_before == 1, f"fixture invariant broken: {count_before}"

    res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {
            "name": fx["block_name"],
            "anchor": "bbox_min",
            "targetPoint": [-2.0, 0.0, 0.0],
            "axes": ["x"],
            "dryRun": False,
        },
    )
    assert res.get("executed") is True, f"rebase not executed: {res!r}"

    count_after = len(await _block_instances(fx["block_name"]))
    assert count_after == count_before, (
        f"instance count changed: {count_before} -> {count_after}"
    )


# --- Test 4: single rebase — dryRun leaves everything unchanged ----------


async def test_rebase_dryrun_does_not_mutate(fresh_document):
    """dryRun:True returns a plan but mutates nothing: basePoint, instance
    world bbox, and instance count all unchanged."""
    fx = await _fixture_single_rebase()
    bbox_before = await _measure_world_bbox(fx["instance_id"])
    count_before = len(await _block_instances(fx["block_name"]))

    res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {
            "name": fx["block_name"],
            "anchor": "bbox_min",
            "targetPoint": [-2.0, 0.0, 0.0],
            "axes": ["x"],
            "dryRun": True,
        },
    )
    assert res.get("success") is not False, f"dry-run failed: {res!r}"
    assert res.get("executed") is False, f"dry-run should not execute: {res!r}"

    # basePoint unchanged — still (5,0,0).
    await assert_new_slot(fx["block_name"], expected_base_point=(5.0, 0.0, 0.0))

    # Instance still there with same id, same world bbox.
    bbox_after = await _measure_world_bbox(fx["instance_id"])
    _assert_bbox_close(bbox_before, bbox_after)

    count_after = len(await _block_instances(fx["block_name"]))
    assert count_after == count_before, (
        f"dry-run mutated instance count: {count_before} -> {count_after}"
    )


# --- Test 5: single rebase — no-op delta rejected ------------------------


async def test_rebase_no_op_returns_error(fresh_document):
    """Pins the 'Requested rebase is a no-op for the selected axes' branch
    at BlocksHandler.cpp:4082. Valid axes=['x'] with targetPoint=[0,0,0]
    on a fixture whose local bbox_min is at origin gives delta=(0,0,0).

    An empty axes:[] array does NOT exercise this branch — it is rejected
    earlier by ParseRebaseAxes at BlocksHandler.cpp:543 with a different
    error message. See plan Step 2e note on Test 5.
    """
    fx = await _fixture_single_rebase()
    # Definition-local storage: world seed minus basePoint = [0,0,0]->[1,1,1].
    # So local bbox_min = [0,0,0]. targetPoint = [0,0,0] gives delta=0.
    res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {
            "name": fx["block_name"],
            "anchor": "bbox_min",
            "targetPoint": [0.0, 0.0, 0.0],
            "axes": ["x"],
            "dryRun": False,
        },
    )
    assert _is_error(res), f"expected no-op error, got success: {res!r}"
    err = _error_text(res).lower()
    assert "no-op" in err, f"expected 'no-op' in error, got: {err!r}"


# --- Test 6: single rebase — linked definition rejected (allowed-skip) ---


async def test_rebase_linked_definition_returns_error(fresh_document):
    """Pins the linked-type preflight rejection at BlocksHandler.cpp:4058.

    Allowed-skip per design §5.5: constructing a linked-definition fixture
    requires writing a .3dm file with a linked reference, which is
    disproportionate effort for a single preflight assertion. If the
    fixture is built in a future PR, remove this skip and implement the
    linked-def construction.
    """
    pytest.skip(
        "linked-definition fixture not implemented; see design §5.5 — "
        "single preflight assertion, disproportionate fixture cost"
    )


# --- Recursive rebase tests -----------------------------------------------


REBASE_RECURSIVE_TARGET = [-2.0, 0.0, 0.0]
REBASE_RECURSIVE_AXES = ["x"]


async def _recursive_execute(leaf_name: str) -> dict:
    """Shared sequence: dry-run to get planHash, then execute with it.

    Returns the execute response. Asserts both phases succeeded.
    """
    dry = await _mcp_tool_executor(
        "rhino_block_rebase_recursive",
        {
            "name": leaf_name,
            "anchor": "bbox_min",
            "targetPoint": REBASE_RECURSIVE_TARGET,
            "axes": REBASE_RECURSIVE_AXES,
            "dryRun": True,
        },
    )
    assert dry.get("success") is not False, f"dry-run failed: {dry!r}"
    plan_hash = dry.get("planHash")
    assert isinstance(plan_hash, str) and plan_hash, (
        f"no planHash in dry-run response: {dry!r}"
    )

    exe = await _mcp_tool_executor(
        "rhino_block_rebase_recursive",
        {
            "name": leaf_name,
            "anchor": "bbox_min",
            "targetPoint": REBASE_RECURSIVE_TARGET,
            "axes": REBASE_RECURSIVE_AXES,
            "dryRun": False,
            "expectedPlanHash": plan_hash,
            "verbose": True,
        },
    )
    assert exe.get("success") is not False, f"execute failed: {exe!r}"
    assert exe.get("executed") is True, f"execute not executed: {exe!r}"
    return exe


# --- Test 7: recursive — leaf basePoint shifts by -delta -----------------


async def test_recursive_rebase_shifts_leaf_basepoint(fresh_document):
    """Leaf basePoint changes by -delta; parent is unaffected by the
    basePoint write (test 12 pins that separately)."""
    fx = await _fixture_recursive_rebase()
    await assert_new_slot(fx["leaf_name"], expected_base_point=(5.0, 0.0, 0.0))

    await _recursive_execute(fx["leaf_name"])

    # delta = (-2, 0, 0); newBase = (5, 0, 0) - (-2, 0, 0) = (7, 0, 0).
    await assert_new_slot(fx["leaf_name"], expected_base_point=(7.0, 0.0, 0.0))


# --- Test 8: recursive — leaf direct instance world bbox preserved -------


async def test_recursive_rebase_preserves_leaf_direct_instance_world_bbox(fresh_document):
    """Step 3c invariant: direct doc leaf instance world bbox unchanged.

    Id reacquisition is different from test 2: the recursive response
    does not expose recreatedInstances, so re-enumerate post-rebase via
    _block_instances — fixture invariant gives len==1, so instances[0].id
    is the new id.
    """
    fx = await _fixture_recursive_rebase()
    bbox_before = await _measure_world_bbox(fx["leaf_instance_id"])

    await _recursive_execute(fx["leaf_name"])

    post = await _block_instances(fx["leaf_name"])
    assert len(post) == 1, (
        f"leaf instance count changed during recursive rebase: {post!r}"
    )
    new_id = post[0]["id"]
    assert isinstance(new_id, str) and new_id, f"missing id in response: {post!r}"

    bbox_after = await _measure_world_bbox(new_id)
    _assert_bbox_close(bbox_before, bbox_after)


# --- Test 9: recursive — parent doc instance world bbox preserved --------


async def test_recursive_rebase_preserves_parent_world_geometry(fresh_document):
    """Step 3b invariant: a document instance of the parent has its world
    bbox unchanged. Parent's nested ref to leaf gets -delta compensation
    that exactly cancels the leaf's +delta local-frame shift."""
    fx = await _fixture_recursive_rebase()
    bbox_before = await _measure_world_bbox(fx["parent_instance_id"])

    await _recursive_execute(fx["leaf_name"])

    # Parent doc instances are NOT deleted+recreated — only the leaf's
    # direct doc instances are. The parent instance id survives.
    bbox_after = await _measure_world_bbox(fx["parent_instance_id"])
    _assert_bbox_close(bbox_before, bbox_after)


# --- Test 10: recursive — parent InstanceReference count preserved -------


async def test_recursive_rebase_preserves_parent_nested_ref_count(fresh_document):
    """Parent rewrite preserves object structure. Count of InstanceReference
    entries in the parent def is unchanged. This catches any helper bug
    that drops or duplicates nested refs during parent rewrite."""
    fx = await _fixture_recursive_rebase()

    before = await _block_objects_detailed(fx["parent_name"])
    refs_before = [o for o in before["objects"] if o.get("type") == "InstanceReference"]

    await _recursive_execute(fx["leaf_name"])

    after = await _block_objects_detailed(fx["parent_name"])
    refs_after = [o for o in after["objects"] if o.get("type") == "InstanceReference"]

    assert len(refs_after) == len(refs_before), (
        f"parent InstanceReference count changed: "
        f"before={len(refs_before)} after={len(refs_after)}; "
        f"full before={before!r} after={after!r}"
    )
    assert after["objectCount"] == before["objectCount"], (
        f"parent objectCount changed: "
        f"{before['objectCount']} -> {after['objectCount']}"
    )


# --- Test 11: recursive — planhash mismatch rejected ---------------------


async def test_recursive_rebase_planhash_mismatch_errors(fresh_document):
    """Execute with a deliberately stale expectedPlanHash; expect the
    'Plan changed since dry-run' rejection at BlocksHandler.cpp:4640."""
    fx = await _fixture_recursive_rebase()

    res = await _mcp_tool_executor(
        "rhino_block_rebase_recursive",
        {
            "name": fx["leaf_name"],
            "anchor": "bbox_min",
            "targetPoint": REBASE_RECURSIVE_TARGET,
            "axes": REBASE_RECURSIVE_AXES,
            "dryRun": False,
            "expectedPlanHash": "0" * 16,  # deliberately stale
        },
    )
    assert _is_error(res), (
        f"expected plan-hash mismatch error, got success: {res!r}"
    )
    err = _error_text(res).lower()
    assert "plan changed" in err or "planhash" in err or "plan hash" in err, (
        f"expected plan-hash-mismatch error text, got: {err!r}"
    )


# --- Test 12: recursive — parent basePoint NOT changed by leaf rebase ----


async def test_recursive_rebase_leaves_parent_basepoint_unchanged(fresh_document):
    """Only the leaf's local frame shifts; the parent's basePoint
    metadata must be untouched. Catches any helper bug that accidentally
    spreads the basePoint update beyond the leaf definition.

    Parent basePoint is non-origin (2, 2, 0) for teeth — origin-basePoint
    parents pass accidentally when the helper mistakenly zeroes the
    basePoint on any rewritten definition."""
    fx = await _fixture_recursive_rebase()

    # Sanity: parent's pre-rebase basePoint is the fixture value.
    await assert_new_slot(
        fx["parent_name"], expected_base_point=tuple(fx["parent_base_point"])
    )

    await _recursive_execute(fx["leaf_name"])

    # Parent basePoint unchanged.
    await assert_new_slot(
        fx["parent_name"], expected_base_point=tuple(fx["parent_base_point"])
    )
