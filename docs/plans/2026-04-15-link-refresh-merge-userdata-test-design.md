# Live-Rhino test coverage for link/refresh/merge basePoint UserData preservation

**Issue:** [#35](https://github.com/bringfire/Rook/issues/35)
**Depends on:** PR #33 (merged 2026-04-15)
**Status:** Design approved, ready for implementation plan.

---

## 1. Problem

PR #33 added inline audit comments at five block-handler sites that touch
`ON_InstanceDefinition` without going through the Rook basePoint write helpers.
Three of those sites — `HandleBlockLink`, `HandleBlockRefresh`,
`HandleBlockMerge` — have no live-Rhino test coverage. If a Rhino SDK change
drops `UserData` on one of these paths, the current test suite won't catch it.

The other two audit sites (`HandleBlockRename`, `HandleBlockUnlink`) use
`ModifyInstanceDefinition` with specific masks (`idef_name_setting` and
`all_idef_settings` respectively). These were comment-audited in PR #33 Phase D
but intentionally left without live tests — they are out of scope for this issue
as well. Note: the PR #33 preserve-sites test (test 10) exercises
`ModifyInstanceDefinitionGeometry`, a different SDK path; it does not cover
the `ModifyInstanceDefinition`-with-mask behavior used by rename/unlink. Link,
refresh, and merge use fundamentally different SDK paths again and are the
priority for dedicated coverage here.

---

## 2. Scope

Three new tests in `mcp_server/tests/test_block_replace_object_geometry_live.py`.
One new conftest helper. Two fixture-factory helpers. No native or managed code
changes. No MCP tool surface changes.

### Out of scope

- Testing managed-side behavior (blocked by InstanceDefinition.UserData SDK gap; see #34).
- Testing `HandleBlockRefresh` with a source that has no UserData at all (the
  no-synthesis rule is already covered by the link test; refresh's job is to
  reload, not to synthesize).
- Asserting on orphaned source definitions after merge (audit expectation, not
  this test's claim).

---

## 3. New conftest helper

### `assert_no_new_slot(block_name: str)`

Async. Hits `POST /block/_debug/basepoint-userdata` directly via httpx (same
route as `assert_new_slot`). Asserts `data.attached == false`. Same 403->skip
and 404->fail error patterns as the existing helper.

---

## 4. Fixture factories

### 4.1 Slot-free .3dm (for link test)

The link test needs a .3dm whose block definition was NOT created through the
Rook pipeline, so no `RookBlockBasePointUserData` is attached. Using
`rhino_block_create` would defeat the claim because it dual-writes UserData.

Implementation: `rhino_execute` a Python script that adds top-level geometry
to a blank document via `doc.Objects.AddBrep(brep)` (a box converted to Brep).
No `InstanceDefinitions.Add` and no Rook handler involvement — the file
contains only raw model content with no `RookBlockBasePointUserData` anywhere.
When `HandleBlockLink` runs `_-Insert _File=... _Block`, it treats the file's
top-level content as the linked block geometry. No internal block definition
is needed because the link route consumes the file's model content, not its
definition table. Then save to a temp path.

This produces a genuine "pre-migration / externally-authored" .3dm file with
geometry but no Rook-owned metadata of any kind.

### 4.2 Rook-authored .3dm (for refresh test)

The refresh test needs two .3dm files with the same block name but different
basePoints, both created through the Rook `rhino_block_create` path so
UserData IS attached via dual-write.

Helper: `_create_rook_block_file(path, block_name, base_point)` — async. Resets
to new doc, creates a box, calls `rhino_block_create` with the given basePoint,
saves to `path`. Does NOT reset afterwards; caller manages doc state.

Both temp files are built upfront before the target doc is established, so the
target doc remains stable throughout the test.

---

## 5. Test designs

### 5.1 `test_block_link_does_not_synthesize_origin_userdata`

**Claim:** `HandleBlockLink` does not fabricate `RookBlockBasePointUserData` on
externally-authored linked definitions (design doc #28 §3.4).

```
1. Build slot-free source.3dm via rhino_execute Python script (NOT Rook
   block-create). Block name = "LINK_NOSLOT".
2. Reset to fresh target doc (fresh_document fixture).
3. rhino_block_link(path=source.3dm, name="LINK_NOSLOT").
4. Assert the returned definition name matches "LINK_NOSLOT" — prevents false
   negative if link naming differs from the requested name.
5. assert_no_new_slot("LINK_NOSLOT") — proves no synthesis.
6. Cleanup: delete temp file.
```

### 5.2 `test_block_refresh_reloads_userdata_from_modified_source`

**Claim:** `HandleBlockRefresh` reloads definition metadata from the source
archive on disk — it does not cache the in-doc state.

```
1. Build source_v1.3dm with block "REFRESH_BLOCK", basePoint P1=(3,0,0) via
   Rook block-create path.
2. Build source_v2.3dm with block "REFRESH_BLOCK", basePoint P2=(8,0,0) via
   Rook block-create path.
3. Reset to fresh target doc.
4. Copy source_v1.3dm -> linked_source.3dm (the path the linked def references).
5. rhino_block_link(path=linked_source.3dm, name="REFRESH_BLOCK").
6. (no assertion on current slot state — link-time inheritance is not this
   test's claim)
7. Overwrite linked_source.3dm with the bytes from source_v2.3dm via
   shutil.copyfile. Then bump the file's mtime via os.utime to ensure Rhino's
   last-write-time cache (if any) recognizes the change. This prevents flakiness
   from a byte-level overwrite that happens to preserve the original timestamp.
8. rhino_block_refresh(name="REFRESH_BLOCK").
9. assert_new_slot("REFRESH_BLOCK", expected_base_point=(8.0, 0.0, 0.0)) —
   proves refresh reloaded from disk.
10. Cleanup: delete all temp files.
```

### 5.3 `test_block_merge_target_userdata_survives`

**Claim:** `HandleBlockMerge` never touches the target definition's metadata.
Only instance refs are repointed.

```
1. Reset to fresh target doc.
2. Create target block "MERGE_TARGET" with basePoint=(5,0,0) via Rook path.
3. Create source block "MERGE_SOURCE" with basePoint=(7,0,0) via Rook path.
4. Insert a MERGE_SOURCE instance (so merge has something to repoint).
5. assert_new_slot("MERGE_TARGET", (5,0,0)) — pre-merge sanity.
6. rhino_block_merge(target="MERGE_TARGET", sources=["MERGE_SOURCE"],
   dryRun=false).
7. Assert merge actually executed: response indicates executed=true and
   totalInstancesAffected > 0. This prevents the metadata assertion from
   passing on a no-op merge.
8. assert_new_slot("MERGE_TARGET", (5,0,0)) — proves target metadata
   survived the merge.
9. No assertion on MERGE_SOURCE — orphaned source state is an audit
   expectation, not this test's claim.
```

---

## 6. Test infrastructure constraints

- All three tests use `fresh_document` fixture and `@pytest.mark.requires_rhino`.
- All three require `ROOK_ENABLE_DEBUG_ROUTES=1` in the Rhino process env (for
  the debug introspection routes).
- Temp .3dm paths are kept in native OS form (backslashes on Windows) per the
  finding from PR #33 test 6: Rhino's scripted `_-Open` rejects forward-slash
  paths on Windows.
- Cleanup uses `try/finally` with `os.unlink` / `shutil.rmtree` to avoid leaking
  temp files on test failure.

---

## 7. Files changed

| File | Change |
|------|--------|
| `mcp_server/tests/conftest.py` | Add `assert_no_new_slot` helper |
| `mcp_server/tests/test_block_replace_object_geometry_live.py` | Add 3 tests + 2 fixture-factory helpers |

No native or managed source changes. No new debug routes. No MCP tool surface
changes. No design doc updates needed (the #28 design doc already documents the
intended behavior; these tests enforce it).

---

## 8. Acceptance criteria

1. All 3 new tests pass against live Rhino with `ROOK_ENABLE_DEBUG_ROUTES=1`.
2. All 10 existing tests continue to pass (no regressions).
3. No native or managed rebuild required.
4. `assert_no_new_slot` correctly fails when UserData IS present (sanity-check
   during development by pointing it at a Rook-created block).
