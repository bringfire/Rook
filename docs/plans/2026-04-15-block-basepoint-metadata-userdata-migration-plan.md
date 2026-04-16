# Block basePoint UserData Migration Plan

**Implements design:** [2026-04-15-block-basepoint-metadata-userdata-migration-design.md](C:/Users/aryan/source/repos/Rook/docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-design.md)  
**Issue:** [#28](https://github.com/bringfire/Rook/issues/28)

## Goal

Replace the legacy `rook_block_base_point`-only storage model with a
Rook-owned symmetric `UserData` channel on block definitions while preserving:

- current public MCP tool behavior
- legacy `.3dm` compatibility
- PR #30's zero-drift behavior in companion-backed replace-object-geometry
- PR #32's live-Rhino regression coverage

This plan is execution-oriented. It assumes the design doc is already approved.

## Non-Goals

- Do not delete the legacy user-string write or the managed reflection bridge in this PR.
- Do not move any companion-backed block-definition mutation routes across the native/managed boundary.
- Do not add a generic metadata framework.
- Do not change `.vcxproj` / `.csproj` structure unless a build failure forces it.
- Do not broaden managed write ownership; managed stays read-only in this PR.

## Scope Summary

Native changes:

- add new `CRookBlockBasePointUserData`
- dual-write create/rebase/rebase-recursive/duplicate paths
- prefer new slot on native reads
- audit preserve and mask-sensitive definition mutation paths

Managed changes:

- add new `RookBlockBasePointUserData`
- prefer new slot on managed reads
- retain reflection bridge as legacy fallback only

Test changes:

- extend the live-Rhino pytest harness from PR #32
- add test-only introspection helper for the new slot

Docs:

- keep the design doc as architecture source-of-truth
- optionally add a short implementation note in the PR body or changelog if useful

## Files Expected To Change

Native:

- `src/RookNative/Handlers/BlocksHandler.cpp`
- `src/RookNative/UserData/RookBlockBasePointUserData.h` (new)
- `src/RookNative/UserData/RookBlockBasePointUserData.cpp` (new)

Managed:

- `src/Rook/Handlers/BlocksHandler.cs`
- `src/Rook/UserData/RookBlockBasePointUserData.cs` (new)

Tests:

- `mcp_server/tests/conftest.py`
- `mcp_server/tests/test_block_replace_object_geometry_live.py`
- optionally `mcp_server/tests/_rook_userdata_introspect.py` if the helper should not live in `conftest.py`

Docs:

- `docs/plans/2026-04-15-block-basepoint-metadata-userdata-migration-design.md` only if implementation learns something material

## Pre-Flight Checks

Before editing:

1. Verify the current native basePoint helpers and mutation sites still exist:
   - `StoreDefinitionBasePoint`
   - `UpdateDefinitionBasePoint`
   - `LookupDefinitionBasePoint`
   - `HandleBlockDuplicate`
   - `HandleBlockRebase`
   - `HandleBlockRebaseRecursive`
   - `HandleBlockAddObjects`
   - `HandleBlockRemoveObjects`
   - `HandleBlockReplaceGeometry`
   - `HandleBlockRename`
   - `HandleBlockLink`
   - `HandleBlockRefresh`
   - `HandleBlockUnlink`
   - `HandleBlockMerge`
2. Verify the managed fallback reader still lives in `BlocksHandler.cs`:
   - `_GetUserString` reflection binding
   - `BasePointReadState`
   - `TryReadDefinitionBasePoint`
3. Verify the PR #32 live test module still passes before migration work starts.

Exit criteria:

- file/line anchors still match the design closely enough that the plan remains valid
- no unexpected route-ownership change has happened

## Phase A: Scaffold New UserData Types

Objective:

- introduce the new symmetric storage primitive without changing runtime behavior

Native:

- create `src/RookNative/UserData/RookBlockBasePointUserData.h`
- create `src/RookNative/UserData/RookBlockBasePointUserData.cpp`
- add:
  - UUID `0CD9F899-C9AA-4FC5-8F45-E081409245E9`
  - `ON_OBJECT_DECLARE` / `ON_OBJECT_IMPLEMENT`
  - payload field `ON_3dPoint m_base_point`
  - `Archive`, `Write`, `Read`, `GetDescription`
  - `Attach`, `TryRead`, `Remove`
- set constructor invariants:
  - `m_userdata_copycount = 1`
  - `m_userdata_xformage = ON_UserData::not_transformed`

Managed:

- create `src/Rook/UserData/RookBlockBasePointUserData.cs`
- add:
  - matching `[Guid(...)]`
  - `Point3d BasePoint`
  - `Description`
  - `ShouldWrite`
  - `OnDuplicate`
  - `Read`, `Write`
  - `Attach`, `TryRead`, `Remove`

Rules:

- do not wire either class into read/write paths yet
- do not add product API for introspection

Verification:

- native and managed compile
- no runtime behavior changes
- optional one-off local smoke check: attach/read/remove through immediate code path if easy, but no permanent behavior changes yet

Suggested commit:

- `feat(blocks): scaffold Rook-owned basePoint userdata on native and managed sides`

## Phase B: Native Dual-Write On Authoritative Write Paths

Objective:

- start writing the new slot wherever native already writes a new basePoint

Primary file:

- `src/RookNative/Handlers/BlocksHandler.cpp`

Implementation:

1. Rewrite `StoreDefinitionBasePoint(ON_InstanceDefinition&, const ON_3dPoint&)` to:
   - remove any existing `CRookBlockBasePointUserData`
   - attach exactly one fresh `CRookBlockBasePointUserData`
   - keep writing the legacy `rook_block_base_point` user-string
2. Update `UpdateDefinitionBasePoint(...)` to maintain the strong post-condition on the live table entry.
   - prefer direct reattach on the live definition after modify
   - do not rely on slice-copy metadata carry-through if avoidable
3. Confirm create path still calls `StoreDefinitionBasePoint` after `AddInstanceDefinition`.
4. Make duplicate path explicit:
   - read source basePoint via native lookup
   - call `StoreDefinitionBasePoint` on the newly created definition
   - do not assume SDK duplication hooks preserve the new slot automatically

Must-write paths in this phase:

- create
- duplicate
- rebase
- rebase-recursive

Do not write new metadata in this phase from:

- add-objects
- remove-objects
- replace-geometry
- replace-object-geometry
- link
- refresh
- unlink
- merge

Verification:

- existing PR #32 tests still pass
- add test `test_new_slot_populated_on_block_create`
- use the new test-only introspection helper to confirm the slot is actually attached

Suggested commit:

- `feat(blocks): dual-write basePoint metadata to new userdata slot in native`

## Phase C: Prefer New Slot On Read Paths

Objective:

- switch both native and managed readers to new-slot-first semantics

Native:

- update `LookupDefinitionBasePoint(const CRhinoInstanceDefinition*)` in `src/RookNative/Handlers/BlocksHandler.cpp`
- order:
  - new `UserData`
  - legacy user-string
  - origin fallback

Managed:

- update `TryReadDefinitionBasePoint(...)` in `src/Rook/Handlers/BlocksHandler.cs`
- order:
  - new `RookBlockBasePointUserData`
  - reflection bridge `_GetUserString`
  - origin fallback

Rules:

- keep `BasePointReadState.BridgeFailure` for legacy-fallback-only failure
- once a valid new slot is present, the reflection bridge must not be consulted
- do not remove the reflection bridge in this PR

Verification:

- existing PR #32 tests still pass unchanged
- add `test_disagreement_new_slot_wins`
- confirm behavior still matches legacy-era expectations for old defs

Suggested commit:

- `feat(blocks): prefer new basePoint userdata over legacy fallback on read`

## Phase D: Preserve-Path Audit And Round-Trip Hardening

Objective:

- verify the new slot survives the native definition mutation paths that should preserve it
- finish round-trip coverage for the new storage

Native audit targets in `src/RookNative/Handlers/BlocksHandler.cpp`:

- `HandleBlockAddObjects`
- `HandleBlockRemoveObjects`
- `HandleBlockReplaceGeometry`
- `HandleBlockRename`
- `HandleBlockUnlink`
- `HandleBlockRefresh`
- `HandleBlockMerge`

What to do:

1. For preserve paths using `ModifyInstanceDefinitionGeometry`:
   - verify the attached `UserData` survives
   - only patch code if the SDK path demonstrably drops metadata
2. For mask-sensitive `ModifyInstanceDefinition` paths:
   - verify the chosen mask does not clear attached `UserData`
3. For refresh/merge:
   - document actual observed behavior inline if it matters to future maintenance
   - ensure no stale/duplicate payload state is introduced on surviving definitions

Tests to add:

- `test_save_load_roundtrip_preserves_basepoint`
- `test_block_duplicate_carries_basepoint`
- `test_block_rebase_updates_new_slot`
- `test_preserve_sites_retain_basepoint`

Rules:

- behavior assertions remain primary
- introspection helper is secondary proof that the new slot is present and correct
- do not add “new-only” testing in this PR; that belongs to legacy-retirement follow-up `#34`

Verification:

- all existing PR #32 tests pass
- all new migration tests pass

Suggested commit:

- `feat(blocks): harden basePoint userdata round-trips and preserve-path survival`

## Phase E: Final Cleanup And Documentation

Objective:

- leave the implementation legible and the migration state explicit

Tasks:

- add succinct inline comments where the migration contract is non-obvious:
  - why `not_transformed` is required
  - why managed remains read-only
  - why the reflection bridge is still present
- update the design doc only if implementation discoveries differ from the approved assumptions
- make sure follow-up `#34` remains clearly gated on a release window

Verification:

- no behavior change from Phase D
- docs match actual implementation decisions

Suggested commit:

- `docs(blocks): record userdata migration implementation notes`

## Test Plan

Baseline:

- run the existing live-Rhino module before edits

During implementation:

- after Phase B:
  - `pytest -m requires_rhino mcp_server/tests/test_block_replace_object_geometry_live.py -k populated`
- after Phase C:
  - `pytest -m requires_rhino mcp_server/tests/test_block_replace_object_geometry_live.py -k disagreement`
- after Phase D:
  - `pytest -m requires_rhino mcp_server/tests/test_block_replace_object_geometry_live.py`

Minimum acceptance:

- all four PR #32 regression tests pass unchanged
- all six new migration tests pass
- native build compiles without new warnings
- managed build compiles without new warnings

## Risk Notes

- The test-only introspection helper hits a native internal HTTP debug route (`POST /block/_debug/basepoint-userdata`) directly via `httpx`, not managed reflection. This shift happened because RhinoCommon 8.0.23304's `InstanceDefinition.UserData` collection does not surface plugin-defined `ON_UserData` subclasses to managed callers (see design doc §3.3). The route is internal/test-only and must not be promoted to a product MCP tool; it can be removed once follow-up #34 lands legacy retirement.
- `HandleBlockRefresh` and `HandleBlockMerge` are still the least-certain audit points; verify observed behavior rather than assuming preservation.
- If a preserve path unexpectedly drops attached `UserData`, fix the concrete path rather than weakening the design guarantee.
- Do not broaden the migration by opportunistically writing origin metadata to linked/external definitions.

## Rollback-Safe Sequencing

If implementation stalls mid-way:

- after Phase A: safe to abandon; no runtime behavior changed
- after Phase B: runtime still works because readers still honor legacy
- after Phase C: safe as long as dual-write from Phase B is already in place
- after Phase D: test coverage should prevent silent regressions

This ordering is intentional. Do not switch read paths before the new slot is being written.

## Done Criteria

This plan is complete when:

1. the new `UserData` classes exist and serialize symmetrically
2. native authoritative write paths dual-write
3. native and managed read new-first, legacy-second
4. preserve paths are verified not to drop metadata
5. live-Rhino regression coverage covers both behavior and new-slot presence
6. the reflection bridge remains present only as a compatibility fallback
