# Implementation plan: #35 link/refresh/merge UserData test coverage

**Design doc:** `docs/plans/2026-04-15-link-refresh-merge-userdata-test-design.md`
**Branch:** `test/link-refresh-merge-userdata-coverage` (off `main`)
**Estimated commits:** 1 (all Python-only; squash-merge at end)

---

## Step 1: Add `assert_no_new_slot` to conftest.py

**File:** `mcp_server/tests/conftest.py`
**Insert after:** `set_legacy_basepoint_for_test` (end of file)

```python
async def assert_no_new_slot(block_name: str) -> None:
    """Test-only introspection: assert NO RookBlockBasePointUserData is
    attached to the named idef.

    Complement to assert_new_slot. Hits the same native debug route.
    Used by tests that verify Rook does NOT synthesize metadata on
    externally-authored or linked definitions.
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
```

**Update import line** in `test_block_replace_object_geometry_live.py`:
```python
from .conftest import assert_bbox_x_range, assert_new_slot, assert_no_new_slot, set_legacy_basepoint_for_test
```

---

## Step 2: Add fixture-factory helpers to the test module

**File:** `mcp_server/tests/test_block_replace_object_geometry_live.py`
**Insert in the helpers section** (after `_replace_object_batch`, before the tests).

### 2a: `_create_slot_free_block_file`

Creates a .3dm with a block definition via raw RhinoCommon (no Rook handler),
so NO `RookBlockBasePointUserData` is attached. Uses `rhino_execute` to run
a Python script inside Rhino.

```python
async def _create_slot_free_block_file(
    path: str, block_name: str, base_point: list[float]
) -> None:
    """Create a .3dm with a block definition via raw RhinoCommon API.
    No Rook handler involvement — no UserData attached."""
    bp_str = f"Rhino.Geometry.Point3d({base_point[0]}, {base_point[1]}, {base_point[2]})"
    script = f"""
import scriptcontext as sc
import Rhino

box = Rhino.Geometry.Box(
    Rhino.Geometry.Plane.WorldXY,
    Rhino.Geometry.Interval(0, 1),
    Rhino.Geometry.Interval(0, 1),
    Rhino.Geometry.Interval(0, 1),
)
brep = box.ToBrep()
attr = Rhino.DocObjects.ObjectAttributes()
idef_index = sc.doc.InstanceDefinitions.Add(
    "{block_name}", "", {bp_str}, [brep], [attr]
)
if idef_index < 0:
    raise Exception("InstanceDefinitions.Add failed")
"""
    # Start from a blank doc
    new_res = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
    assert new_res.get("success") is not False, f"new failed: {new_res!r}"

    exec_res = await _mcp_tool_executor("rhino_execute", {"code": script})
    assert not (isinstance(exec_res, dict) and exec_res.get("success") is False), (
        f"rhino_execute failed: {exec_res!r}"
    )

    save_res = await _mcp_tool_executor(
        "rhino_document_ops", {"action": "save", "path": path}
    )
    assert save_res.get("success") is not False, f"save failed: {save_res!r}"
```

### 2b: `_create_rook_block_file`

Creates a .3dm with a block definition via the Rook `rhino_block_create` path,
so UserData IS attached via dual-write.

```python
async def _create_rook_block_file(
    path: str, block_name: str, base_point: list[float]
) -> None:
    """Create a .3dm with a Rook-authored block (UserData attached)."""
    new_res = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
    assert new_res.get("success") is not False, f"new failed: {new_res!r}"

    seed = await _create_brep([0, 0, 0], [1, 1, 1], f"{block_name}_SEED")
    await _block_create(block_name, [seed], base_point=base_point)

    save_res = await _mcp_tool_executor(
        "rhino_document_ops", {"action": "save", "path": path}
    )
    assert save_res.get("success") is not False, f"save failed: {save_res!r}"
```

---

## Step 3: Add the three tests

**File:** `mcp_server/tests/test_block_replace_object_geometry_live.py`
**Insert after:** `test_preserve_sites_retain_basepoint` (end of Phase D section)

Add a new section header comment:
```python
# ---------------------------------------------------------------------------
# Phase D+ migration tests (#35) — link/refresh/merge UserData preservation
# ---------------------------------------------------------------------------
```

### 3a: `test_block_link_does_not_synthesize_origin_userdata`

```python
async def test_block_link_does_not_synthesize_origin_userdata(fresh_document):
    """HandleBlockLink does not fabricate RookBlockBasePointUserData on
    externally-authored linked definitions.

    The source .3dm is created via raw RhinoCommon InstanceDefinitions.Add
    (no Rook handler) so no UserData is attached. After linking into the
    target doc, the linked definition must NOT have a synthesized origin
    basePoint — design §3.4: externally-authored linked defs inherit
    whatever the source file says, which in this case is nothing.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    tmp.close()
    source_path = tmp.name
    try:
        await _create_slot_free_block_file(source_path, "LINK_NOSLOT", [0, 0, 0])

        # Reset to fresh target doc
        new_res = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        assert new_res.get("success") is not False

        link_res = await _mcp_tool_executor(
            "rhino_block_link", {"path": source_path, "name": "LINK_NOSLOT"}
        )
        assert link_res.get("success") is not False, f"link failed: {link_res!r}"

        # Verify the definition name matches what we requested
        returned_name = link_res.get("name", "")
        assert returned_name == "LINK_NOSLOT", (
            f"expected linked def name 'LINK_NOSLOT', got {returned_name!r}"
        )

        # Primary assertion: no UserData synthesized
        await assert_no_new_slot("LINK_NOSLOT")
    finally:
        try:
            os.unlink(source_path)
        except OSError:
            pass
```

### 3b: `test_block_refresh_reloads_userdata_from_modified_source`

```python
async def test_block_refresh_reloads_userdata_from_modified_source(fresh_document):
    """HandleBlockRefresh reloads definition metadata from the source
    archive on disk — it does not cache the in-doc state.

    Two source .3dm files with the same block name but different
    basePoints (P1, P2) are built upfront via the Rook path. The
    target doc links to P1's file, then the file is overwritten with
    P2's bytes and refreshed. The post-refresh assertion on P2 is the
    sole load-bearing claim.

    The copy-overwrite shape keeps the target doc stable throughout —
    no document-switching after the link is established.
    """
    tmp_v1 = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    tmp_v1.close()
    tmp_v2 = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    tmp_v2.close()
    tmp_linked = tempfile.NamedTemporaryFile(suffix=".3dm", delete=False)
    tmp_linked.close()

    v1_path = tmp_v1.name
    v2_path = tmp_v2.name
    linked_path = tmp_linked.name

    try:
        # Build both source versions upfront
        await _create_rook_block_file(v1_path, "REFRESH_BLOCK", [3, 0, 0])
        await _create_rook_block_file(v2_path, "REFRESH_BLOCK", [8, 0, 0])

        # Prepare linked_source as a copy of v1
        shutil.copyfile(v1_path, linked_path)

        # Establish target doc and link
        new_res = await _mcp_tool_executor("rhino_document_ops", {"action": "new"})
        assert new_res.get("success") is not False

        link_res = await _mcp_tool_executor(
            "rhino_block_link", {"path": linked_path, "name": "REFRESH_BLOCK"}
        )
        assert link_res.get("success") is not False, f"link failed: {link_res!r}"

        # (no assertion on current slot state — link-time inheritance is
        # not this test's claim)

        # Overwrite with v2 bytes + bump mtime so Rhino's cache sees a change
        shutil.copyfile(v2_path, linked_path)
        now = time.time()
        os.utime(linked_path, (now, now))

        # Refresh
        refresh_res = await _mcp_tool_executor(
            "rhino_block_refresh", {"name": "REFRESH_BLOCK"}
        )
        assert refresh_res.get("success") is not False, (
            f"refresh failed: {refresh_res!r}"
        )

        # Primary assertion: metadata reloaded from disk
        await assert_new_slot("REFRESH_BLOCK", expected_base_point=(8.0, 0.0, 0.0))
    finally:
        for p in (v1_path, v2_path, linked_path):
            try:
                os.unlink(p)
            except OSError:
                pass
```

### 3c: `test_block_merge_target_userdata_survives`

```python
async def test_block_merge_target_userdata_survives(fresh_document):
    """HandleBlockMerge never touches the target definition's metadata.
    Only instance refs are repointed.

    Target has basePoint=(5,0,0), source has basePoint=(7,0,0). After
    merge, the target's UserData must still read (5,0,0). The merge
    response is checked for executed=true + totalInstancesAffected > 0
    to confirm merge was not a no-op.
    """
    # Target block
    t_seed = await _create_brep([4, -0.5, 0], [6, 1.5, 2], "MERGE_T_SEED")
    await _block_create("MERGE_TARGET", [t_seed], base_point=[5, 0, 0])

    # Source block
    s_seed = await _create_brep([6, -0.5, 0], [8, 1.5, 2], "MERGE_S_SEED")
    await _block_create("MERGE_SOURCE", [s_seed], base_point=[7, 0, 0])

    # Insert a source instance so merge has something to repoint
    await _block_insert("MERGE_SOURCE", [7, 0, 0])

    # Pre-merge sanity
    await assert_new_slot("MERGE_TARGET", expected_base_point=(5.0, 0.0, 0.0))

    merge_res = await _mcp_tool_executor(
        "rhino_block_merge",
        {"target": "MERGE_TARGET", "sources": ["MERGE_SOURCE"], "dryRun": False},
    )
    assert merge_res.get("success") is not False, f"merge failed: {merge_res!r}"

    # Verify merge actually executed (not a no-op)
    assert merge_res.get("executed") is True, (
        f"expected executed=true, got {merge_res!r}"
    )
    affected = merge_res.get("totalInstancesAffected", 0)
    assert affected > 0, (
        f"expected totalInstancesAffected > 0, got {affected}"
    )

    # Primary assertion: target metadata untouched
    await assert_new_slot("MERGE_TARGET", expected_base_point=(5.0, 0.0, 0.0))
```

---

## Step 4: Add imports to test module

At the top of `test_block_replace_object_geometry_live.py`, add `shutil` and
`time` to the existing imports:

```python
import os
import shutil
import tempfile
import time
```

Update the conftest import line to include `assert_no_new_slot`.

---

## Step 5: Run the full test suite

```bash
cd mcp_server && python -m pytest tests/test_block_replace_object_geometry_live.py -m requires_rhino -v
```

Expected: 13 passed (10 existing + 3 new).

If `test_block_link_does_not_synthesize_origin_userdata` fails because
`rhino_execute` script syntax is wrong, debug the script in isolation first
via the MCP tool before re-running. The RhinoCode Python 3 environment may
need slightly different import paths for `Rhino.Geometry`.

If `test_block_refresh_reloads_userdata_from_modified_source` fails on the
P2 assertion, investigate whether Rhino's linked-block cache ignores mtime
and needs a different invalidation mechanism.

---

## Step 6: Commit + PR

Single commit, `test/` branch, squash-merge:

```
test(blocks): live-Rhino coverage for link/refresh/merge UserData preservation (#35)
```

PR body: reference design doc, list the three test claims, cross-reference
#28 audit comments now proven by live tests.

`gh pr merge --squash --delete-branch` at end.
