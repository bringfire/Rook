# Implementation plan: #26 local-frame helper extraction

**Design doc:** `docs/plans/2026-04-16-block-local-frame-helper-design.md`
**Issue:** [#26](https://github.com/bringfire/Rook/issues/26)
**Branches:**
- `test/26-rebase-characterization` (PR1, off `main`)
- `fix/26-local-frame-helper` (PR2, off merged PR1)
**Estimated commits:** 2 total (one per PR, squash-merge)

This plan is structured as two sequential PRs. Do not start PR2 until PR1 has been reviewed and merged — that is the whole point of the test-first sequencing (see the §5 / §6 split in the design doc).

---

# PR1 — Characterization test suite

All changes in this PR are Python-only. No native, managed, or MCP surface changes. Acceptance: 11 tests pass against current `main` unchanged, test 6 is allowed-skip per design §5.5.

## Step 1: Add conftest helpers

**File:** `mcp_server/tests/conftest.py`
**Insert after:** `set_legacy_basepoint_for_test` (end of file), keeping the same httpx/pytest patterns as the existing helpers.

All three helpers live in `conftest.py` alongside existing ones like `_mcp_tool_executor`, `_create_brep`, and `_block_create`. They call `_mcp_tool_executor` directly (same module) — no import needed. If any existing helper uses a slightly different executor name or access pattern, follow that local convention rather than the snippets below.

### 1a: `_block_insert`

```python
async def _block_insert(
    block_name: str,
    insertion_point: "tuple[float, float, float]",
    scale: float = 1.0,
    rotation_degrees: float = 0.0,
) -> str:
    """Insert a block instance via rhino_block_insert. Returns instance id.

    Matches the actual handler surface (BlocksHandler.cpp:1097): uniform
    scale + Z-axis rotation in degrees. Tests use non-identity scale and
    rotation to give oldXform * compensation post-multiplication teeth —
    a pure-translation insert couldn't distinguish compose-then-translate
    from translate-then-compose.
    """
    res = await _mcp_tool_executor(
        "rhino_block_insert",
        {
            "name": block_name,
            "insertionPoint": list(insertion_point),
            "scale": scale,
            "rotation": rotation_degrees,
        },
    )
    assert res.get("success") is not False, f"block insert failed: {res!r}"
    iid = res.get("instanceId")
    assert isinstance(iid, str) and iid, f"no instanceId in response: {res!r}"
    return iid
```

### 1b: `_measure_world_bbox`

```python
async def _measure_world_bbox(obj_id: str) -> dict:
    """World-space bbox of any doc object. Returns {"min": [x,y,z], "max": [x,y,z]}."""
    res = await _mcp_tool_executor("rhino_measure_bbox", {"id": obj_id})
    assert res.get("success") is not False, f"measure_bbox failed: {res!r}"
    bbox = res.get("bbox") or res.get("data", {}).get("bbox") or res
    assert isinstance(bbox, dict) and "min" in bbox and "max" in bbox, (
        f"unexpected bbox response shape: {res!r}"
    )
    return {"min": list(bbox["min"]), "max": list(bbox["max"])}
```

*Verify shape against the real `rhino_measure_bbox` handler output during implementation — if the response envelope differs, adjust the extraction line.*

### 1c: `_block_instances`

```python
async def _block_instances(block_name: str) -> list[dict]:
    """Return the raw rhino_block_instances list for a block definition.

    Each entry carries: id, blockName, insertionPoint, layer, name. Tests
    use len() for count assertions and index for id read-back. The list
    shape (rather than a count-only helper) is required because the
    recursive rebase response does not expose an oldId→newId mapping;
    test 8 must re-enumerate post-rebase to discover the new instance id.
    """
    res = await _mcp_tool_executor("rhino_block_instances", {"name": block_name})
    assert res.get("success") is not False, f"block_instances failed: {res!r}"
    instances = res.get("instances") or res.get("data", {}).get("instances")
    assert isinstance(instances, list), f"unexpected shape: {res!r}"
    return instances
```

### 1d: Extract shared helpers from `test_block_replace_object_geometry_live.py`

Three block-helpers the new test module needs currently live *inside* `test_block_replace_object_geometry_live.py` (lines 54, 72, 90, 81) rather than `conftest.py`. Importing from `conftest` as the plan does would fail. Move them and extend `_block_create` so fixtures can suppress the auto-insert.

**Move to `conftest.py`** (same file Step 1a-1c added helpers to):

```python
async def _create_brep(corner1: list[float], corner2: list[float], name: str) -> str:
    """Create a box brep via rhino_create. Returns object id."""
    res = await _mcp_tool_executor(
        "rhino_create",
        {"type": "BOX", "corner1": corner1, "corner2": corner2, "name": name},
    )
    assert "id" in res, f"rhino_create returned no id: {res!r}"
    return res["id"]


async def _block_create(
    name: str,
    ids: list[str],
    base_point: list[float],
    replace_with_instance: bool = True,  # NEW parameter; default matches prior hardcoded value
) -> dict:
    """Create a block definition from object ids. If replace_with_instance
    is True (default), the source objects are replaced by an inserted
    instance at base_point — matching the pre-extraction behavior. Fixtures
    that need a definition with zero auto-instances (so the test can
    explicitly insert instances with controlled xforms) pass False.
    """
    res = await _mcp_tool_executor(
        "rhino_block_create",
        {
            "name": name,
            "ids": ids,
            "basePoint": base_point,
            "replaceWithInstance": replace_with_instance,
        },
    )
    assert res.get("name") == name, f"rhino_block_create unexpected: {res!r}"
    return res


async def _block_objects_detailed(name: str) -> dict:
    """Definition-local geometry listing for a block. Used for parent
    definition inspection in recursive-rebase tests."""
    res = await _mcp_tool_executor("rhino_block_objects_detailed", {"name": name})
    assert "objects" in res, f"rhino_block_objects_detailed unexpected: {res!r}"
    return res
```

**Remove** from `mcp_server/tests/test_block_replace_object_geometry_live.py`:
- The local `_create_brep` definition (line 54).
- The local `_block_create` definition (line 72).
- The local `_block_objects_detailed` definition (line 90).
- The local `_block_insert(name, point)` definition (line 81) — the richer Step 1a version in conftest supersedes it; `_block_insert(name, point)` callers are covered by the default `scale=1.0, rotation_degrees=0.0`.

**Update** the import block at the top of `test_block_replace_object_geometry_live.py` to import all four from `.conftest`:

```python
from .conftest import (
    # ... existing imports ...
    _create_brep,
    _block_create,
    _block_insert,
    _block_objects_detailed,
)
```

**Verify** the existing `_block_insert(name, point)` call sites in `test_block_replace_object_geometry_live.py` still work with the new keyword-argument signature — if any caller used positional `_block_insert(name, [x, y, z])`, the first-positional-arg semantics are preserved because the parameter is renamed only conceptually (`point` → `insertion_point`) but position and type are unchanged. Run the existing test module locally before PR1 commit to confirm no regressions.

This extraction is **strictly additive** from a behavior standpoint: prior callers get identical semantics with `replace_with_instance=True` as the default. The scope widening is small (3 helpers moved, 1 helper extended with a backwards-compatible parameter) but must be made explicit because the naive plan ("import from conftest") silently assumes state that does not exist.

## Step 2: Create the new live test module

**File:** `mcp_server/tests/test_block_rebase_live.py` (new).

Structure: module-level imports, fixture-factory helpers (Fixtures A and B from design §5.2), then the 12 test functions grouped as `TestSingleRebase` and `TestRecursiveRebase` (or top-level — match whichever pattern the nearest live module uses).

### 2a: Module imports and pytest markers

```python
"""Live-Rhino characterization tests for rhino_block_rebase and
rhino_block_rebase_recursive. Pins the three-part invariant (geometry
rewrite + basePoint sync + instance compensation) before #26 helper
extraction. See docs/plans/2026-04-16-block-local-frame-helper-design.md.
"""

import math
import uuid
import pytest

from .conftest import (
    assert_new_slot,
    fresh_document,
    _mcp_tool_executor,
    _create_brep,
    _block_create,
    _block_insert,
    _measure_world_bbox,
    _block_instances,
    _block_objects_detailed,
)

pytestmark = pytest.mark.live_rhino  # match the marker used by sibling live modules
```

### 2b: Fixture-factory helpers

Both fixtures pass `replace_with_instance=False` to `_block_create` so the definition has **zero auto-inserted instances**. Each test then explicitly inserts exactly one instance with a known non-identity xform. This keeps `len(await _block_instances(name)) == 1` as a clean fixture invariant for tests 3, 8, 9 and the manual-sanity id reacquisition.

```python
async def _fixture_single_rebase(
    block_name: str = "REBASE_LEAF",
    leaf_seed_world_min: list[float] = [5, 0, 0],
    leaf_seed_world_max: list[float] = [6, 1, 1],
    leaf_base_point: list[float] = [5, 0, 0],
    instance_insertion: tuple[float, float, float] = (10.0, 3.0, 0.0),
    instance_scale: float = 1.5,
    instance_rotation_degrees: float = 30.0,
) -> dict:
    """Fixture A: single-rebase fixture. One leaf definition (created
    with replace_with_instance=False so no auto-instance) + one explicit
    direct doc instance with non-identity xform."""
    seed_id = await _create_brep(leaf_seed_world_min, leaf_seed_world_max,
                                 f"{block_name}_SEED")
    await _block_create(
        block_name, [seed_id],
        base_point=leaf_base_point,
        replace_with_instance=False,
    )
    inst_id = await _block_insert(
        block_name, instance_insertion,
        scale=instance_scale, rotation_degrees=instance_rotation_degrees,
    )
    return {"block_name": block_name, "instance_id": inst_id}


async def _fixture_recursive_rebase(
    leaf_name: str = "RR_LEAF",
    parent_name: str = "RR_PARENT",
    leaf_base_point: list[float] = [5, 0, 0],
    parent_base_point: list[float] = [2, 2, 0],
    leaf_seed_world_min: list[float] = [5, 0, 0],
    leaf_seed_world_max: list[float] = [6, 1, 1],
    parent_seed_world_min: list[float] = [20, 20, 0],
    parent_seed_world_max: list[float] = [21, 21, 1],
    leaf_instance_insertion: tuple[float, float, float] = (10.0, 3.0, 0.0),
    leaf_instance_scale: float = 1.5,
    leaf_instance_rotation_degrees: float = 30.0,
    parent_instance_insertion: tuple[float, float, float] = (40.0, 40.0, 0.0),
    parent_instance_scale: float = 1.2,
    parent_instance_rotation_degrees: float = 15.0,
) -> dict:
    """Fixture B: recursive-rebase fixture.

    Leaf def (non-origin basePoint, no auto-instance) + parent def
    (non-origin basePoint, no auto-instance) containing one nested ref
    to leaf + one plain-geom seed. Plus exactly one direct doc leaf
    instance and exactly one direct doc parent instance, both with
    non-identity xforms to give compensation invariants teeth.

    Construction:
      1. Create leaf seed brep, _block_create leaf with replace_with_instance=False.
      2. Create parent seed brep as loose doc geometry.
      3. Insert a leaf instance to serve as the nested ref inside the parent def.
      4. _block_create parent_name with [parent_seed_id, nested_leaf_instance_id],
         replace_with_instance=False.
         IMPORTANT: verify during implementation that _block_create (i.e.
         rhino_block_create) accepts an instance-object id among its seeds.
         If the handler rejects instance ids as seeds, fall back to:
           a. _block_create parent_name with [parent_seed_id] only, replace_with_instance=False
           b. rhino_block_add_objects(name=parent_name, ids=[nested_leaf_instance_id])
         to attach the nested ref post-creation.
      5. Explicitly _block_insert one leaf instance (non-identity xform).
      6. Explicitly _block_insert one parent instance (non-identity xform).
    """
    leaf_seed_id = await _create_brep(leaf_seed_world_min, leaf_seed_world_max,
                                      f"{leaf_name}_SEED")
    await _block_create(
        leaf_name, [leaf_seed_id],
        base_point=leaf_base_point,
        replace_with_instance=False,
    )

    parent_seed_id = await _create_brep(parent_seed_world_min, parent_seed_world_max,
                                        f"{parent_name}_SEED")

    # Nested ref: insert a leaf instance at identity, then use it as a
    # parent-def seed. This doc instance will be consumed by _block_create
    # and become part of the parent definition's internal geometry.
    nested_ref_id = await _block_insert(leaf_name, (0.0, 0.0, 0.0))

    # Primary path: create parent def with both seeds in one call.
    # If rhino_block_create rejects instance-object ids as seeds, replace
    # this block with the fallback below (plain-geom seed only, then
    # rhino_block_add_objects to attach the nested ref).
    try:
        await _block_create(
            parent_name, [parent_seed_id, nested_ref_id],
            base_point=parent_base_point,
            replace_with_instance=False,
        )
    except AssertionError:
        # Fallback path per docstring step 4. Replace the try/except with
        # this two-call sequence verbatim if the primary path fails during
        # implementation.
        await _block_create(
            parent_name, [parent_seed_id],
            base_point=parent_base_point,
            replace_with_instance=False,
        )
        add_res = await _mcp_tool_executor(
            "rhino_block_add_objects",
            {"name": parent_name, "ids": [nested_ref_id]},
        )
        assert add_res.get("success") is not False, f"add_objects failed: {add_res!r}"

    leaf_inst_id = await _block_insert(
        leaf_name, leaf_instance_insertion,
        scale=leaf_instance_scale,
        rotation_degrees=leaf_instance_rotation_degrees,
    )
    parent_inst_id = await _block_insert(
        parent_name, parent_instance_insertion,
        scale=parent_instance_scale,
        rotation_degrees=parent_instance_rotation_degrees,
    )

    return {
        "leaf_name": leaf_name,
        "parent_name": parent_name,
        "leaf_instance_id": leaf_inst_id,
        "parent_instance_id": parent_inst_id,
    }
```

*Fixture B's step 4 (whether `_block_create` accepts an instance-object id as a seed) is the one concrete uncertainty in this plan. The code above raises a clear error if it doesn't; the fallback via `rhino_block_add_objects` is noted in the docstring and should be implemented then if the initial approach fails. Either way the fixture should end up with: leaf def (1 direct doc instance), parent def (1 nested ref to leaf + 1 plain geom + 1 direct doc instance).*

### 2c: Test 1 — basePoint shifts by `-delta`

```python
async def test_rebase_shifts_basepoint_by_inverse_delta(fresh_document):
    """Lift from test_block_replace_object_geometry_live.py::test_block_rebase_updates_new_slot.
    Extended: also assert old basePoint != new basePoint (no-op guard)."""
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
    assert res.get("executed") is True

    # oldBase (5,0,0), delta = targetPoint - bbox_min = (-2,0,0) - (0,0,0) = (-2,0,0)
    # newBase = oldBase - delta = (5,0,0) - (-2,0,0) = (7,0,0)
    await assert_new_slot(fx["block_name"], expected_base_point=(7.0, 0.0, 0.0))
```

### 2d: Test 2 — world bbox of direct instance unchanged

Rebase deletes the old instance and creates a new one with a fresh UUID (see [`BlocksHandler.cpp:4222-4231`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4222)). Measuring on the pre-rebase id post-rebase targets a deleted object. Use `verbose: True` on the rebase call to get the `oldId → newId` map.

```python
async def test_rebase_preserves_world_geometry_of_direct_instances(fresh_document):
    """Non-identity xform teeth: the seeded instance has scale=1.5, rotation=30°.
    World bbox must be numerically identical (within tol) before and after rebase,
    after reacquiring the post-rebase instance id via the verbose response."""
    fx = await _fixture_single_rebase()
    bbox_before = await _measure_world_bbox(fx["instance_id"])

    res = await _mcp_tool_executor(
        "rhino_block_rebase",
        {"name": fx["block_name"], "anchor": "bbox_min",
         "targetPoint": [-2.0, 0.0, 0.0], "axes": ["x"],
         "dryRun": False, "verbose": True},
    )
    assert res.get("executed") is True

    # Rebase deletes + recreates each direct doc instance. Find the new id
    # that corresponds to our seeded old id.
    recreated = res.get("recreatedInstances") or res.get("data", {}).get("recreatedInstances") or []
    new_id = next(
        (entry["newId"] for entry in recreated if entry.get("oldId") == fx["instance_id"]),
        None,
    )
    assert new_id is not None, (
        f"old instance id {fx['instance_id']!r} not found in recreatedInstances: {res!r}"
    )

    bbox_after = await _measure_world_bbox(new_id)
    tol = 1e-6
    for a, b in zip(bbox_before["min"], bbox_after["min"]):
        assert math.isclose(a, b, abs_tol=tol), (bbox_before, bbox_after)
    for a, b in zip(bbox_before["max"], bbox_after["max"]):
        assert math.isclose(a, b, abs_tol=tol), (bbox_before, bbox_after)
```

### 2e: Tests 3-12

Implement using the patterns established by tests 1-2. Full bodies deferred to implementation time — writing them speculatively adds noise to this plan. Each test's invariant is specified in design §5.3; the acceptance criterion is that each one pins exactly that invariant against current `main`.

Key implementation notes per test:

- **Test 3** — `len(await _block_instances(name))` before and after; assert equality.
- **Test 4** — invoke with `dryRun: True`, then assert basePoint + bbox + count all unchanged.
- **Test 5** — **no-op branch.** Use a valid axes set with zero delta — `axes: ["x"]`, `anchor: "bbox_min"`, `targetPoint: [0, 0, 0]` on a fixture whose definition-local bbox_min is at origin → delta = (0,0,0) triggers `"Requested rebase is a no-op for the selected axes"` at [`BlocksHandler.cpp:4082`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4082). An empty `axes: []` array does **not** exercise this branch — it is rejected earlier at [`BlocksHandler.cpp:543`](../../src/RookNative/Handlers/BlocksHandler.cpp#L543) by `ParseRebaseAxes` with a different error message. If you want to cover the parser-level rejection separately, add a 5b test; otherwise keep this test focused on the no-op branch.
- **Test 6** — allowed-skip; if fixture is built, construct a linked definition and assert linked-type rejection. Otherwise top of the test calls `pytest.skip("linked-definition fixture not implemented; see design §5.5")`.
- **Test 7** — recursive, `dryRun: True` first to obtain `planHash`, then `dryRun: False` with `expectedPlanHash` set to the dry-run's hash; assert leaf basePoint changed by `-delta` via `assert_new_slot`.
- **Test 8** — recursive; leaf direct doc instance world bbox unchanged. **Id-reacquisition is different from test 2:** the recursive response does not expose `recreatedInstances`, so re-enumerate post-rebase via `_block_instances(leaf_name)` — fixture has exactly one direct doc leaf instance, so `len == 1` is an invariant and `instances[0]["id"]` is the new id. Shape:
  ```python
  bbox_before = await _measure_world_bbox(fx["leaf_instance_id"])
  # ... run dry-run + execute with planHash ...
  post = await _block_instances(fx["leaf_name"])
  assert len(post) == 1, f"leaf instance count changed: {post!r}"
  new_id = post[0]["id"]
  bbox_after = await _measure_world_bbox(new_id)
  # math.isclose comparison on min/max
  ```
- **Test 9** — recursive; parent doc instance world bbox unchanged. Same id-reacquisition pattern as test 8 but on `fx["parent_name"]` — enumerate `_block_instances(parent_name)`, expect `len == 1`, take `[0]["id"]`, measure.
- **Test 10** — recursive; count `instanceRef` objects in parent definition via `_block_objects_detailed` before and after; assert equality.
- **Test 11** — recursive; call execute with a deliberately stale `expectedPlanHash` (e.g. `"0" * 16`); assert error carries "Plan changed since dry-run".
- **Test 12** — recursive; parent's non-origin basePoint unchanged post-rebase, via `assert_new_slot(parent_name, expected_base_point=parent_base_point)`.

## Step 3: Run suite locally against current `main`

```bash
cd c:/Users/aryan/source/repos/Rook
# Ensure Rhino is running with RookNative + ROOK_ENABLE_DEBUG_ROUTES=1
python -m pytest mcp_server/tests/test_block_rebase_live.py -v
```

All 11 required tests must pass. Test 6 may skip. Any test that fails against unmodified `main` indicates either (a) the test is mis-specified (fix the test) or (b) an existing bug the refactor will not fix (flag to user, decide whether to narrow the assertion or track as a separate issue — *do not adjust the assertion to match buggy behavior*).

## Step 4: Commit and open PR1

```bash
git checkout -b test/26-rebase-characterization main
git add mcp_server/tests/conftest.py mcp_server/tests/test_block_rebase_live.py
git commit -m "test(blocks): live-Rhino characterization for rebase invariants (#26)

PR1 of two. Pins the three-part rebase invariant (geometry rewrite +
basePoint sync + instance compensation) before the #26 helper extraction.

12 tests; test 6 (linked-definition preflight) is allowed-skip per
design §5.5. No production code changes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push -u origin test/26-rebase-characterization
gh pr create --title "test(blocks): live-Rhino characterization for rebase invariants (#26)" --body "..."
```

PR1 body must include:
- Link to `docs/plans/2026-04-16-block-local-frame-helper-design.md`.
- Explicit framing: "pins current behavior ahead of #26 helper extraction; reviewer should verify the invariants, not review any refactor."
- The allowed-skip note for test 6.
- Result of local test run.

Merge with `gh pr merge --squash --delete-branch` after review.

---

# PR2 — Helper extraction and migration

Do not start until PR1 is merged to `main` and the tests are green there. Branch off updated `main`.

All changes in this PR are in a single file: [`src/RookNative/Handlers/BlocksHandler.cpp`](../../src/RookNative/Handlers/BlocksHandler.cpp). No header changes, no MCP surface changes, no managed/Python changes.

## Step 5: Introduce helper types

**File:** `src/RookNative/Handlers/BlocksHandler.cpp`
**Location:** Near the existing basePoint helpers at lines 318-393 (just after `LookupDefinitionBasePoint`). Keep the helper neighborhood local.

Define in order (each as file-static or anonymous namespace):

```cpp
namespace {

struct TranslateAllSpec {
    ON_Xform geometryXform;
};

struct CompensateNestedRefsSpec {
    int      targetChildDefIndex;
    ON_Xform refCompensationXform;
};

using RewriteSpec = std::variant<TranslateAllSpec, CompensateNestedRefsSpec>;

struct InstanceSnapshot {
    ON_UUID                 oldId   = ON_nil_uuid;
    ON_Xform                oldXform = ON_Xform::IdentityTransformation;
    ON_3dmObjectAttributes  attrs;
};

struct RecreatedInstanceIds {
    ON_UUID oldId = ON_nil_uuid;
    ON_UUID newId = ON_nil_uuid;
};

struct FrameShiftResult {
    ON_3dPoint oldBasePoint;
    ON_3dPoint newBasePoint;
    int        directInstancesCompensated = 0;
};

} // namespace
```

Verify `<variant>` is included via one of the existing includes (`Models/Snapshots.h` or `SceneGraph/SceneGraphModels.h` already use `std::variant`, so the header is likely already pulled in transitively — add `#include <variant>` at the top of `BlocksHandler.cpp` if it isn't).

## Step 6: Implement `RewriteDefinitionGeometry`

**Location:** Just after the types from Step 5.

```cpp
// Owns materialize -> ModifyInstanceDefinitionGeometry -> temp cleanup
// for a single definition rewrite. Two modes via the RewriteSpec variant.
// Throws std::runtime_error on any failure, after cleaning up any temp
// objects it created. Caller never sees temp IDs.
static void RewriteDefinitionGeometry(
    CRhinoDoc*         pDoc,
    int                idefIndex,
    const RewriteSpec& spec)
{
    if (!pDoc)
        throw std::runtime_error("RewriteDefinitionGeometry: null doc");

    const CRhinoInstanceDefinition* pDef =
        pDoc->m_instance_definition_table[idefIndex];
    if (!pDef)
        throw std::runtime_error(
            "RewriteDefinitionGeometry: definition lookup failed");

    // Dispatch spec variant to the matching MaterializeDefinitionObjects
    // call. Both modes already exist in the current helper; we just route
    // spec fields into the right parameter slots.
    ON_SimpleArray<const CRhinoObject*> docObjects;
    std::vector<ON_UUID> tempIds;

    auto cleanupTemps = [&]() {
        for (const auto& tid : tempIds)
            pDoc->DeleteObject(CRhinoObjRef(pDoc->RuntimeSerialNumber(), tid));
    };

    bool ok = false;
    if (auto* t = std::get_if<TranslateAllSpec>(&spec)) {
        ok = MaterializeDefinitionObjects(
            pDoc, pDef, t->geometryXform,
            /*targetDefIndex*/ -1,
            /*refCompensationXform*/ ON_Xform::IdentityTransformation,
            docObjects, tempIds);
    } else if (auto* c = std::get_if<CompensateNestedRefsSpec>(&spec)) {
        ok = MaterializeDefinitionObjects(
            pDoc, pDef, ON_Xform::IdentityTransformation,
            c->targetChildDefIndex,
            c->refCompensationXform,
            docObjects, tempIds);
    }

    if (!ok) {
        cleanupTemps();
        throw std::runtime_error(
            "RewriteDefinitionGeometry: failed to materialize definition objects");
    }

    if (!pDoc->m_instance_definition_table.ModifyInstanceDefinitionGeometry(
            idefIndex, docObjects, false)) {
        cleanupTemps();
        throw std::runtime_error(
            "RewriteDefinitionGeometry: ModifyInstanceDefinitionGeometry failed");
    }

    // Success path also cleans up temps — cleanup is best-effort; temps
    // may already be implicitly soft-deleted by the SDK call, so ignored
    // DeleteObject returns here are consistent with the existing pattern.
    cleanupTemps();
}
```

## Step 7: Implement `MutateDefinitionLocalFrame`

**Location:** Just after `RewriteDefinitionGeometry`.

```cpp
// Owns the full three-part invariant for a definition local-frame shift:
// (1) snapshot direct doc instances, (2) rewrite geometry via the inner
// primitive, (3) sync basePoint metadata, (4) recreate instances with
// -delta compensation. Throws std::runtime_error on any step failure;
// caller's UndoScope is the rollback envelope.
static FrameShiftResult MutateDefinitionLocalFrame(
    CRhinoDoc*                            pDoc,
    int                                   idefIndex,
    const ON_3dVector&                    definitionDelta,
    std::vector<RecreatedInstanceIds>*    outRecreatedIds)
{
    if (!pDoc)
        throw std::runtime_error("MutateDefinitionLocalFrame: null doc");

    const CRhinoInstanceDefinition* pDef =
        pDoc->m_instance_definition_table[idefIndex];
    if (!pDef)
        throw std::runtime_error(
            "MutateDefinitionLocalFrame: definition lookup failed");

    // ── Step 1: snapshot direct doc instances BEFORE any mutation ───
    std::vector<InstanceSnapshot> snapshots;
    {
        ON_SimpleArray<const CRhinoInstanceObject*> refs;
        pDef->GetReferences(refs);
        snapshots.reserve(refs.Count());
        for (int i = 0; i < refs.Count(); ++i) {
            const CRhinoInstanceObject* inst = refs[i];
            if (!inst) continue;
            InstanceSnapshot s;
            s.oldId = inst->Attributes().m_uuid;
            s.oldXform = inst->InstanceXform();
            s.attrs = inst->Attributes();
            snapshots.push_back(std::move(s));
        }
    }

    // ── Step 2: rewrite geometry in translate-all mode ──────────────
    const ON_Xform translationXform =
        ON_Xform::TranslationTransformation(definitionDelta);
    RewriteDefinitionGeometry(pDoc, idefIndex,
        TranslateAllSpec{ translationXform });

    // ── Step 3: sync basePoint metadata ─────────────────────────────
    const CRhinoInstanceDefinition* pUpdatedDef =
        pDoc->m_instance_definition_table[idefIndex];
    if (!pUpdatedDef)
        throw std::runtime_error(
            "MutateDefinitionLocalFrame: lookup failed after rewrite");

    const ON_3dPoint oldBase = LookupDefinitionBasePoint(pUpdatedDef);
    const ON_3dPoint newBase(
        oldBase.x - definitionDelta.x,
        oldBase.y - definitionDelta.y,
        oldBase.z - definitionDelta.z);
    if (!UpdateDefinitionBasePoint(pDoc, idefIndex, newBase))
        throw std::runtime_error(
            "MutateDefinitionLocalFrame: basePoint metadata update failed");

    // ── Step 4: recreate instances with -delta compensation ─────────
    const ON_Xform compensationXform =
        ON_Xform::TranslationTransformation(-definitionDelta);

    int compensated = 0;
    for (const auto& s : snapshots) {
        // Hard failure on delete — current code ignores this; the new
        // contract checks it (see design §2 caution + §3.4).
        const bool deleted = pDoc->DeleteObject(
            CRhinoObjRef(pDoc->RuntimeSerialNumber(), s.oldId));
        if (!deleted)
            throw std::runtime_error(
                "MutateDefinitionLocalFrame: failed to delete old instance");

        const ON_Xform newXform = s.oldXform * compensationXform;
        CRhinoInstanceObject* pNewInst =
            pDoc->m_instance_definition_table.CreateInstanceObject(
                idefIndex, newXform, &s.attrs, nullptr,
                false, false, true);
        if (!pNewInst)
            throw std::runtime_error(
                "MutateDefinitionLocalFrame: failed to recreate compensated instance");

        ++compensated;
        if (outRecreatedIds) {
            RecreatedInstanceIds ids;
            ids.oldId = s.oldId;
            ids.newId = pNewInst->Attributes().m_uuid;
            outRecreatedIds->push_back(ids);
        }
    }

    FrameShiftResult result;
    result.oldBasePoint = oldBase;
    result.newBasePoint = newBase;
    result.directInstancesCompensated = compensated;
    return result;
}
```

## Step 8: Migrate `HandleBlockRebase`

**Current location:** Lines 4014-4271.
**Replace:** Lines 4129-4254 (the entire `struct InstanceData { ... }` block through the `recreatedInstances` response assembly).

New body inside the dispatcher lambda, after all preflight validation:

```cpp
// Everything from here is wrapped in a single undo record so that
// all of the helper's mutations are covered by one Ctrl+Z.
UndoScope undo(pDoc, L"Rebase block");

std::vector<RecreatedInstanceIds> recreated;
FrameShiftResult shift = MutateDefinitionLocalFrame(
    pDoc, idefIndex, definitionDelta,
    verbose ? &recreated : nullptr);

const CRhinoInstanceDefinition* pUpdatedDef =
    pDoc->m_instance_definition_table[idefIndex];
wr.data["recreatedInstanceCount"] = shift.directInstancesCompensated;
wr.data["bboxAfter"] = BoundingBoxToJsonRounded(
    GetBlockDefinitionBoundingBox(pUpdatedDef));

if (verbose) {
    nlohmann::json j = nlohmann::json::array();
    for (const auto& r : recreated) {
        j.push_back({
            {"oldId", UuidToString(r.oldId)},
            {"newId", UuidToString(r.newId)},
        });
    }
    wr.data["recreatedInstances"] = std::move(j);
}

pDoc->Redraw();
return wr;
```

**Remove:** The mid-loop `partialRebase=true` branch entirely. The outer `catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }` at lines 4260-4270 handles helper throws identically. No caller consumes `partialRebase`.

## Step 9: Migrate `HandleBlockRebaseRecursive` leaf step

**Current location:** Step 3a at lines 4677-4720, Step 3c at lines 4755-4793.
**Action:** Fuse Step 3a + 3c into a single `MutateDefinitionLocalFrame` call at the start of the execute block, then remove the old Step 3c entirely.

Replace Step 3a block with:

```cpp
// ─── Step 3a+3c fused: leaf frame shift + direct doc instance compensation ───
// Reordered from original 3a→3b→3c to 3a+3c→3b. Semantically equivalent —
// parent rewrites (3b) never observe direct leaf doc instances, and direct
// instance compensation never touches definition geometry. See design §4.3.
int directInstancesCompensated = 0;
{
    FrameShiftResult leafShift = MutateDefinitionLocalFrame(
        pDoc, leafDefIndex, plan.definitionTranslation,
        /*outRecreatedIds*/ nullptr);
    directInstancesCompensated = leafShift.directInstancesCompensated;
}
```

Delete the entire original Step 3c block (lines 4755-4793). Its work is now inside the helper call above.

## Step 10: Migrate `HandleBlockRebaseRecursive` parent step

**Current location:** Step 3b at lines 4722-4753.
**Replace** the inner materialize + modify + cleanup block (lines 4732-4751) with:

```cpp
RewriteDefinitionGeometry(pDoc, parentEntry.parentDefIndex,
    CompensateNestedRefsSpec{
        /*targetChildDefIndex*/ leafDefIndex,
        /*refCompensationXform*/ compensationXform,
    });
totalNestedRefsCompensated += parentEntry.nestedRefsToLeaf;
```

Keep the enclosing `for (const auto& parentEntry : plan.parentDefinitions)` loop and the surrounding error-context strings as-is.

## Step 11: Build

```bash
cd c:/Users/aryan/source/repos/Rook
cmd /c scripts\build-native.bat
```

Fix any compile errors. Most likely issues:
- `<variant>` include missing → add at top of `BlocksHandler.cpp`.
- Designated-initializer syntax `{.field = value}` may need C++20 — if build fails, fall back to positional initialization.
- `std::get_if` return type mismatch → verify `RewriteSpec` variant order matches the `std::get_if<Type>(&spec)` dispatch.

## Step 12: Deploy + run characterization tests

```bash
cmd /c scripts\deploy-native.bat
# Restart Rhino with ROOK_ENABLE_DEBUG_ROUTES=1
python -m pytest mcp_server/tests/test_block_rebase_live.py -v
python -m pytest mcp_server/tests/test_block_geometry_caps.py -v
```

Run the full `test_block_geometry_caps.py` module (not just `TestBlockRebaseDispatch`) — PR2 migrates both `HandleBlockRebase` and `HandleBlockRebaseRecursive`, so recursive-rebase dispatch smoke and any other block-routing checks must stay green too.

All PR1 tests must still pass (11 required + test 6 skip-or-pass). All dispatch smoke in `test_block_geometry_caps.py` must pass.

If any PR1 test now fails, **the refactor introduced a regression** — do not adjust the test. Fix the helper.

## Step 13: Manual sanity on a real fixture file

Open `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\0_REVIT EXPORT_ALL.3dm` (or any sizable real fixture). Pick one non-origin block definition. Record four data points pre- and post-refactor via a copy of current `main`:

1. `rhino_block_rebase` with `dryRun: True` — compare the full response JSON. Must be identical field-for-field.
2. `rhino_block_rebase` with `dryRun: False, verbose: True` — compare:
   - Post-execute `basePoint` (via `rhino_block_info` or the debug route).
   - World bbox of each direct doc instance **after id reacquisition**: rebase deletes + recreates each instance with a fresh UUID (see [`BlocksHandler.cpp:4222-4231`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4222)), so map pre-rebase ids to post-rebase ids via the `verbose` response's `recreatedInstances` array before measuring via `rhino_measure_bbox`.
   - `rhino_block_instances` count.
3. `rhino_block_rebase_recursive` with `dryRun: True` — same plan-shape comparison.
4. `rhino_block_rebase_recursive` with `dryRun: False` — same four-point comparison as step 2 but with a different id-reacquisition path: the recursive response does not expose `recreatedInstances`, so re-enumerate direct doc leaf instances via `rhino_block_instances(leaf_name)` post-execute to find the new ids. Plus: parent's basePoint unchanged, and bbox of doc instances of the **parent** also reacquired via `rhino_block_instances(parent_name)` if the fixture has any.

Documented in PR2 description as a table: `field → pre-value → post-value → match?`. Include a short note about the id-reacquisition asymmetry between the two paths so future reviewers understand why the pre/post ids differ.

## Step 14: Commit and open PR2

```bash
git checkout -b fix/26-local-frame-helper main  # after PR1 merged
git add src/RookNative/Handlers/BlocksHandler.cpp
git commit -m "fix(blocks): extract MutateDefinitionLocalFrame helper (#26)

Layered helper pair:
- RewriteDefinitionGeometry (inner): materialize + modify + temp cleanup.
- MutateDefinitionLocalFrame (outer): three-part invariant with rollback
  throws to caller's UndoScope.

Migrates HandleBlockRebase and HandleBlockRebaseRecursive (leaf + parent
steps). HandleBlockReplaceGeometry out of scope per design §2.

No success-path behavior change. Error-envelope cleanup: the orphaned
partialRebase=true field is removed from HandleBlockRebase's mid-loop
failure path (dead field, zero consumers). Step 3c moves before Step 3b
in recursive execution — semantically equivalent per design §4.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
git push -u origin fix/26-local-frame-helper
gh pr create --title "fix(blocks): extract MutateDefinitionLocalFrame helper (#26)" --body "..."
```

PR2 body must include:
- Link to design doc.
- Manual-sanity comparison table from Step 13.
- The three explicit call-outs from design §6.2:
  - *No success-path behavior change.*
  - *Error-envelope cleanup: `partialRebase` field removed.*
  - *Step 3c reordered before Step 3b in recursive execution; semantically equivalent.*
  - *Site 3 (`HandleBlockReplaceGeometry`) out of scope; separate future follow-up tracked.*

Merge with `gh pr merge --squash --delete-branch` after review.

---

# Post-merge follow-ups

Per design §7:

1. **Work-queue** — promote "Typed route coverage — close command-string fallback" from Parked to Next. Update `rook_docs/work-queue.md`.
2. **File follow-up issue** (not urgent) for potential extraction of "materialize external source set into definition-local coords" around `MaterializeTransformedSource`, scoped to `HandleBlockReplaceGeometry`. Reference design §2 out-of-scope rationale.
3. **Memory** — no new entries. Helper pair is internal plumbing.
