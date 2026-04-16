# Encapsulate "mutate definition local frame" behind one helper

**Issue:** [#26](https://github.com/bringfire/Rook/issues/26)
**Depends on:** PR #25 (merged 2026-04-15), PR #33 (merged 2026-04-15), PR #36 (merged 2026-04-15)
**Status:** Design approved, ready for implementation plan.

---

## 1. Problem

PR #25 fixed non-origin basePoint normalization at definition-create time, and PR #33 rooted the basePoint metadata in Rook-owned `ON_UserData`. The three-part invariant for operations that shift a definition's local frame — *geometry rewrite + basePoint sync + instance compensation, under a single UndoScope* — is now enforced at multiple sites in [`src/RookNative/Handlers/BlocksHandler.cpp`](../../src/RookNative/Handlers/BlocksHandler.cpp):

- [`HandleBlockRebase`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4014) — materialize, modify, cleanup, basePoint sync, instance compensation, all inline.
- [`HandleBlockRebaseRecursive`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4463) leaf step (3a) — same sequence minus instance compensation, which is deferred to Step 3c.
- [`HandleBlockRebaseRecursive`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4722) parent step (3b) — pure geometry rewrite, no frame shift.

Any future handler that shifts a definition's local frame (e.g., a hypothetical `rhino_block_align_to_origin` or `rhino_block_scale_in_place`) inherits the responsibility of keeping all three steps in sync. There is no compiler or structural enforcement — a new handler that rewrites definition geometry without updating basePoint metadata silently reintroduces the Issue #24 drift.

---

## 2. Scope

Layered helper pair in [`BlocksHandler.cpp`](../../src/RookNative/Handlers/BlocksHandler.cpp). Structural extraction only. The only observable behavior change is removal of the orphaned `partialRebase=true` JSON envelope (see §3.5).

### In scope

- Inner primitive `RewriteDefinitionGeometry` — owns materialize + `ModifyInstanceDefinitionGeometry` + temp cleanup.
- Outer helper `MutateDefinitionLocalFrame` — owns the three-part frame-shift invariant.
- Migrate `HandleBlockRebase` → outer helper.
- Migrate `HandleBlockRebaseRecursive` leaf step → outer helper.
- Migrate `HandleBlockRebaseRecursive` parent step → inner primitive.
- Live-Rhino characterization test suite pinning the invariants before migration.

### Out of scope

- `HandleBlockReplaceGeometry`. Its contract is *rewrite this definition from an externally-supplied source set resolved from request `ids`*, with an origin fast path that passes originals through to preserve the broader accepted type set. See [`BlocksHandler.cpp:1743`](../../src/RookNative/Handlers/BlocksHandler.cpp#L1743). Forcing it through `RewriteDefinitionGeometry` — which is definition-to-definition plumbing — would blur the contract. A separate future extraction around "materialize external source set into definition-local coords" built from `MaterializeTransformedSource` is the right shape for that handler; tracked as a follow-up, not this issue.
- Post-mutation fault-injection coverage. Without a test-only fault hook, live Rhino has no way to force a failure after Step 3a or during instance compensation, so the rollback envelope is not testable from Python. Documented as an explicit gap.
- Managed-side (C#) parity. No equivalent pattern exists on the companion side.

---

## 3. Helper contract

### 3.1 Inner primitive — `RewriteDefinitionGeometry`

Owns the full `materialize → ModifyInstanceDefinitionGeometry → temp cleanup` sequence. Mode-shaped, not flag-shaped — the two existing modes of [`MaterializeDefinitionObjects`](../../src/RookNative/Handlers/BlocksHandler.cpp#L819) are genuinely different contracts.

```cpp
struct TranslateAllSpec {
    ON_Xform geometryXform;   // applied to plain geom;
                              // post-multiplied into nested ref xforms.
};

struct CompensateNestedRefsSpec {
    int      targetChildDefIndex;   // which nested child to compensate
    ON_Xform refCompensationXform;  // applied only to refs of
                                    // targetChildDefIndex; identity
                                    // elsewhere; identity on plain geom.
};

using RewriteSpec = std::variant<TranslateAllSpec, CompensateNestedRefsSpec>;

// Throws std::runtime_error on any failure. Cleans up any temp doc
// objects it created on BOTH success and failure paths before
// returning/throwing. Caller never sees temp IDs.
static void RewriteDefinitionGeometry(
    CRhinoDoc*         pDoc,
    int                idefIndex,
    const RewriteSpec& spec);
```

C++17 + `std::variant` are already in use in this project (see `Models/Snapshots.h`, `SceneGraph/SceneGraphModels.h`). Definition identity is `idefIndex`, not `pDef` — the helper owns the full "modify this exact idef" operation and re-fetches internally.

### 3.2 Outer helper — `MutateDefinitionLocalFrame`

Owns the three-part local-frame-shift invariant. Caller passes pre-computed `delta`; compensation is derived internally as `-delta` to keep the invariant self-contained.

```cpp
struct RecreatedInstanceIds {
    ON_UUID oldId = ON_nil_uuid;
    ON_UUID newId = ON_nil_uuid;
};

struct FrameShiftResult {
    ON_3dPoint oldBasePoint;
    ON_3dPoint newBasePoint;
    int        directInstancesCompensated = 0;
};

// Throws std::runtime_error on any step failure. Caller's UndoScope
// is the rollback envelope; the helper does not own it. If
// outRecreatedIds is non-null, populated with one entry per
// compensated instance; otherwise not collected.
static FrameShiftResult MutateDefinitionLocalFrame(
    CRhinoDoc*                           pDoc,
    int                                  idefIndex,
    const ON_3dVector&                   definitionDelta,
    std::vector<RecreatedInstanceIds>*   outRecreatedIds = nullptr);
```

Internal sequence (all under the caller's `UndoScope`):

1. Snapshot direct document instances before any mutation, via `pDef->GetReferences(...)`. Store `oldId`, `oldXform`, `attrs`. No post-mutation re-enumeration.
2. Call `RewriteDefinitionGeometry(pDoc, idefIndex, TranslateAllSpec{translation(delta)})`.
3. Re-fetch the updated definition. Read current basePoint via `LookupDefinitionBasePoint`, compute `newBase = oldBase - delta`, write via `UpdateDefinitionBasePoint`. Throw on failure.
4. For each snapshot instance: `DeleteObject(oldId)` (check return, throw on false), then `CreateInstanceObject` with `oldXform * translation(-delta)` on the same `idefIndex`, preserving `attrs`. Throw on `CreateInstanceObject` failure.

### 3.3 Validation boundary

All preflight validation stays in the callers — unchanged from current behavior:

- Materializability checks, null-object counts, linked-type rejection — before `UndoScope`.
- No-op delta detection, nested-use check (single rebase), planHash verification + execute-time re-resolution (recursive) — before `UndoScope`.
- Response JSON assembly — after the helper returns.

The helper assumes validated inputs.

### 3.4 Rollback & failure semantics

The helper throws uniformly on any failure in steps 1-4. The caller's `try/catch (const std::exception& ex) { CRookServer::SendError(res, ex.what()); }` at the handler boundary surfaces the message. The caller's `UndoScope` RAII guard (defined in [`Infrastructure/UndoScope.h`](../../src/RookNative/Infrastructure/UndoScope.h)) calls `EndUndoRecord` on stack unwind, giving the user Ctrl+Z access to the pre-mutation state.

`UndoScope` does *not* auto-rollback on exception — it only ensures the undo record is terminated. This is the current pattern; the refactor preserves it.

### 3.5 `partialRebase` JSON envelope removal

Current `HandleBlockRebase` has a mid-loop instance-recreation failure path that returns `{success:false, partialRebase:true, error:...}` instead of throwing. See [`BlocksHandler.cpp:4233-4240`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4233).

- `grep partialRebase` across the entire repo returns only this write site. Python MCP layer, C# companion, and all tests never consume it.
- The uniform-throw contract in §3.4 supersedes this path. The helper throws on recreation failure; the caller's existing catch surfaces a plain error via `SendError`.
- This is an **error-envelope cleanup**, not a success-path behavior change. Clients that never parse the orphaned field see no difference; clients that did parse it (none exist) would see `{success:false, error:"..."}` instead of `{success:false, partialRebase:true, error:"..."}`.
- Called out explicitly in the PR2 description so reviewers see it.

---

## 4. Data flow & migration

### 4.1 Site 1 — `HandleBlockRebase`

Preflight validation unchanged ([lines 4042-4103](../../src/RookNative/Handlers/BlocksHandler.cpp#L4042)). Everything from the `UndoScope` at line 4162 through the instance recreation loop at line 4249 collapses to approximately:

```cpp
UndoScope undo(pDoc, L"Rebase block");
std::vector<RecreatedInstanceIds> recreated;
FrameShiftResult shift = MutateDefinitionLocalFrame(
    pDoc, idefIndex, definitionDelta,
    verbose ? &recreated : nullptr);

wr.data["recreatedInstanceCount"] = shift.directInstancesCompensated;
wr.data["bboxAfter"] = BoundingBoxToJsonRounded(
    GetBlockDefinitionBoundingBox(
        pDoc->m_instance_definition_table[idefIndex]));
if (verbose) wr.data["recreatedInstances"] = IdsToJson(recreated);
pDoc->Redraw();
return wr;
```

~90 lines down to ~10. Materialize, modify, cleanup, basePoint sync, instance compensation — all inside the helper. Existing outer `catch` at line 4270 handles helper throws identically.

### 4.2 Site 2 — `HandleBlockRebaseRecursive`

Preflight (leaf + parents + planHash + execute-time re-resolution) unchanged. Inside the `UndoScope undo(pDoc, L"Recursive block rebase")` at line 4666:

- **Step 3a + 3c fused.** Lines 4677-4720 (leaf rewrite + basePoint sync) and lines 4755-4793 (direct doc instance compensation) collapse to a single `MutateDefinitionLocalFrame` call on the leaf. Direct-doc-instance compensation now lands **before** parent rewrites rather than after.
- **Step 3b.** Each parent rewrite loop body (lines 4732-4751) collapses to:
  ```cpp
  RewriteDefinitionGeometry(pDoc, parentEntry.parentDefIndex,
      CompensateNestedRefsSpec{
          .targetChildDefIndex = leafDefIndex,
          .refCompensationXform = compensationXform,
      });
  totalNestedRefsCompensated += parentEntry.nestedRefsToLeaf;
  ```

### 4.3 Reordering-safety verification

`3c` now executes before `3b`. This is semantically equivalent in the current implementation because:

- Direct parent discovery ([`FindDirectParentDefinitions`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4308)) is definition-only — walks each candidate parent's object list, records nested refs to the leaf. Never inspects document-level leaf instances.
- Step 3b is also definition-only. Re-fetches each parent by `parentDefIndex` and runs `ModifyInstanceDefinitionGeometry` on that parent definition only.
- Step 3c operates on `leafDocRefs` obtained from `pLeafDef->GetReferences(...)` — the direct document instances of the leaf. Parent rewrite never enumerates these.

Within this handler, `3c` does not feed `3b`, and `3b` does not observe `3c`. The relative order is choreography, not a real dependency. Called out in the PR2 description.

### 4.4 What stays in callers

- All preflight validation.
- `UndoScope` construction.
- Response JSON assembly, including reading bbox-after from the re-fetched `pDef`.
- `pDoc->Redraw()` at the end.

---

## 5. PR1 — Characterization test suite

New test module: `mcp_server/tests/test_block_rebase_live.py`. Existing live-test modules are scoped by handler surface; adding `_live` separation keeps rebase invariants cleanly discoverable.

### 5.1 New conftest helpers

Thin wrappers over existing MCP tools, no new debug routes. Helper surfaces match the real tool shapes in `BlocksHandler.cpp` exactly — no fabricated parameters.

- `_block_insert(name, insertion_point, scale=1.0, rotation=0.0) -> uuid` — wraps `rhino_block_insert` ([handler at `BlocksHandler.cpp:1097`](../../src/RookNative/Handlers/BlocksHandler.cpp#L1097)). `scale` is uniform; `rotation` is degrees about Z. Returns the created instance's `id`. Tests that want to exercise the `oldXform * compensationXform` post-multiplication (see §5.3 tests 2, 8, 9) pass non-unit `scale` and/or non-zero `rotation` so the xform composition is genuinely non-trivial.
- `_measure_world_bbox(obj_id) -> {"min": [...], "max": [...]}` — wraps `rhino_measure_bbox`. Measures the world-space bounding box of any doc object, including instance objects.
- `_block_instances_count(name) -> int` — wraps `rhino_block_instances` and returns `len(result["instances"])`. The tool does not expose instance xforms — its output is `id`, `blockName`, `insertionPoint` (translation column only), `layer`, `name`. All instance-preservation invariants in §5.3 use `_measure_world_bbox` on the instance `id`, which does not require reading the xform back. Reduced to a count-only helper to match what the tool actually provides.

### 5.2 Fixtures

- **Fixture A — single rebase.** Leaf definition (bbox_min ≠ origin) + one direct doc instance inserted via `_block_insert` with non-unit `scale` and non-zero `rotation`. The non-identity xform gives the post-multiplication invariant teeth — a translation-only instance could not distinguish `oldXform * translation(-delta)` from `oldXform + translation(-delta)`.
- **Fixture B — recursive rebase.** Leaf definition + parent definition (non-origin basePoint) containing one nested ref to leaf + one plain-geom seed + one direct doc leaf instance (non-unit `scale` / non-zero `rotation` as above) + one direct doc parent instance (for §5.3 test 9's parent-instance world-bbox assertion, also non-identity).

### 5.3 Test cases

Single rebase (`rhino_block_rebase`):

1. `test_rebase_shifts_basepoint_by_inverse_delta` — basePoint changes by `-delta`. Lifted and extended from [`test_block_replace_object_geometry_live.py:533`](../../mcp_server/tests/test_block_replace_object_geometry_live.py#L533).
2. `test_rebase_preserves_world_geometry_of_direct_instances` — world bbox of seeded instance (non-identity xform) unchanged. This is the invariant the refactor most easily breaks, and the non-identity `scale`/`rotation` at insert time ensures `oldXform * translation(-delta)` composition is actually exercised.
3. `test_rebase_preserves_instance_count` — `_block_instances_count(name)` unchanged.
4. `test_rebase_dryrun_does_not_mutate` — `dryRun:true` leaves basePoint, bbox, instance count untouched.
5. `test_rebase_no_op_axes_returns_error` — zero-axis delta rejected at preflight.
6. `test_rebase_linked_definition_returns_error` — linked-type rejected at preflight. The linked-definition fixture requires writing a .3dm file with a linked reference and is disproportionate effort for a single preflight assertion; marked as allowed-skip rather than required. See §5.5 acceptance.

Recursive rebase (`rhino_block_rebase_recursive`):

7. `test_recursive_rebase_shifts_leaf_basepoint` — leaf basePoint changes by `-delta`.
8. `test_recursive_rebase_preserves_leaf_direct_instance_world_bbox` — world bbox of direct doc leaf instance (non-identity xform) unchanged. Step 3c invariant.
9. `test_recursive_rebase_preserves_parent_world_geometry` — world bbox of a **document instance of the parent** (created via `_block_insert` on the parent with non-identity xform) unchanged. Step 3b invariant: parent's nested ref gets `-delta` compensation that exactly cancels the leaf's `+delta` shift, and this must hold under the parent instance's own non-identity xform.
10. `test_recursive_rebase_preserves_parent_nested_ref_count` — parent still contains the same number of nested refs to leaf.
11. `test_recursive_rebase_planhash_mismatch_errors` — stale `expectedPlanHash` rejected.
12. `test_recursive_rebase_leaves_parent_basepoint_unchanged` — parent's non-origin basePoint metadata unchanged. Catches any bug that spreads the basePoint update beyond the leaf. Non-origin is required for teeth; origin-basePoint parent passes accidentally.

### 5.4 Explicit gaps

Documented in PR1 description, not simulated:

- Post-mutation fault injection (no test-only fault hook).
- `partialRebase` consumer verification (grep returns only the write site; noted for reviewer).

### 5.5 Acceptance

11 of 12 tests pass against current `main` unchanged. Test 6 (`test_rebase_linked_definition_returns_error`) is **allowed-skip** — the linked-definition fixture requires writing a .3dm file containing a linked reference, which is disproportionate effort for a single preflight assertion already covered by the inline check at [`BlocksHandler.cpp:4058-4064`](../../src/RookNative/Handlers/BlocksHandler.cpp#L4058). If the fixture is built, test 6 becomes required; otherwise it is documented as a known coverage gap in the PR1 description and the test file carries a `pytest.skip(...)` with the rationale.

Zero production code changes in PR1.

---

## 6. PR2 — Helper extraction + migration

### 6.1 Code changes

All in [`src/RookNative/Handlers/BlocksHandler.cpp`](../../src/RookNative/Handlers/BlocksHandler.cpp):

- Introduce types: `TranslateAllSpec`, `CompensateNestedRefsSpec`, `RewriteSpec`, `RecreatedInstanceIds`, `FrameShiftResult`, `InstanceSnapshot` (internal).
- Introduce helpers: `RewriteDefinitionGeometry`, `MutateDefinitionLocalFrame`.
- Migrate `HandleBlockRebase` → `MutateDefinitionLocalFrame`.
- Migrate `HandleBlockRebaseRecursive` leaf step → `MutateDefinitionLocalFrame` (Step 3c reordered before Step 3b — verified safe in §4.3).
- Migrate `HandleBlockRebaseRecursive` parent rewrite step → `RewriteDefinitionGeometry(CompensateNestedRefsSpec{...})`.
- Check `DeleteObject` return value in the helper; throw on false.
- Remove the `partialRebase=true` JSON envelope from `HandleBlockRebase`'s mid-loop failure path (dead field).

### 6.2 PR2 description must call out

- **No success-path behavior change.**
- **Error-envelope cleanup:** `partialRebase` field removed from the instance-recreation failure envelope of `HandleBlockRebase`. Dead field with zero consumers in the repo. Not a success-path change.
- **Step 3c moves before Step 3b in recursive execution** — semantically equivalent per §4.3. Parent rewrites never observe direct doc leaf instances; direct doc instance compensation never touches definition geometry.
- **Site 3 (`HandleBlockReplaceGeometry`) out of scope** — separate future follow-up for "materialize external source set into definition-local coords."

### 6.3 Acceptance

- All PR1 characterization tests still pass unchanged under the same allowed-skip policy for test 6 (§5.5) — i.e., 11 required-pass + 1 skip-or-pass, identical to PR1 acceptance.
- Existing dispatch smoke in [`test_block_geometry_caps.py:206`](../../mcp_server/tests/test_block_geometry_caps.py#L206) passes.
- `scripts/build-native.bat` + `scripts/deploy-native.bat` succeed.
- **Manual sanity on a real fixture file** (CRYSTAL_BRIDGES or equivalent): invoke `rhino_block_rebase` and `rhino_block_rebase_recursive` pre- and post-refactor. Compare concretely:
  - Same dry-run plan shape (JSON equality on plan fields).
  - Same post-execute basePoint values.
  - Same post-execute world-space bbox of direct doc instances.
  - Same instance counts.
- Documented in PR2 description with exact commands + outcomes.

---

## 7. Follow-ups after PR2 merges

- **Work-queue.** Promote "Typed route coverage — close command-string fallback" from Parked to Next. #26 is its listed unblocker (per [`work-queue.md:98`](../../../rook_docs/work-queue.md)).
- **File a follow-up issue** for possible extraction of "materialize external source set into definition-local coords" around `MaterializeTransformedSource`, for `HandleBlockReplaceGeometry`. Not urgent; file only if a real workflow surfaces the need.
- **Memory.** No new entries. The helper pair is internal plumbing, not a user-facing contract.
