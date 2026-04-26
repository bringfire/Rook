# `rhino_block_replace_object_geometry_batch` — Design

**Date:** 2026-04-14
**Status:** Approved (brainstorm complete)
**Author:** Claude + bringfire (review)
**Roadmap entry:** `rook_docs/2026-04-13-batch-tools-roadmap.md` #6
**Pattern siblings:** `2026-04-14-transform-instance-batch-design.md` (PR #14, companion-backed block batch, ABI v10), `2026-04-14-layer-set-properties-batch-design.md` (PR #15, best-effort taxonomy + shared-helper discipline)

## Goal

Batch variant of `rhino_block_replace_object_geometry`. Replace the geometry of
one or more objects across one or more block definitions in a single call.
Companion-backed via the P/Invoke bridge, coalesced per-definition rebuilds,
single `UndoScope`, best-effort per-item semantics, compact summary response
plus a one-field `deletedSources` lifecycle audit.

## Non-goals

- No upsert-create-block behavior. Missing block name → `block_not_found` skip.
- No cross-item dependency choreography. Shape + relational phases run
  globally; resolution runs per-group against the original doc snapshot.
- No geometry-type compatibility checks beyond "`sourceObj.Geometry != null`" —
  exact parity with single-target. `InstanceReference`-as-source stays legal if
  weird, for the same reason.
- No per-item post-replace readback beyond `deletedSources`. Callers query
  `rhino_block_objects_detailed` / `rhino_block_info` for full post-state.
- No perf optimizations for 10k+ items. Real cleanup workloads are bounded
  (hundreds, not tens of thousands).

## Architecture

**Route:** `POST /block/replace-object-geometry-batch`, companion-backed via the
P/Invoke bridge. Block-definition mutations must not run on the native side —
native `ModifyInstanceDefinitionGeometry` is a confirmed crash path.
`doc.InstanceDefinitions.ModifyGeometry()` (managed RhinoCommon) is safe.

**ABI bump 10 → 11, atomic both sides, single commit.**

### Wiring

| Layer | Change |
|-------|--------|
| C# companion (`BlocksHandler.cs`) | New method `ReplaceObjectGeometryBatch(string? body)`; shared validation helpers extracted from existing `ReplaceObjectGeometry`; single-target refactored to call helpers |
| Bridge managed (`NativeGhBridgeRegistrar.cs`) | New delegate typedef + struct field append; `BridgeAbiVersion` 10 → 11; P/Invoke handler wires body through to BlocksHandler |
| Native proxy (`GrasshopperProxyHandler.cpp/h`) | New `HandleManagedBlockReplaceObjectGeometryBatch`; struct field append at same ordinal position as managed; `kGhBridgeAbiVersion` 10 → 11 |
| Native server (`RookServer.cpp/h`) | New class-level forwarder + route registration next to `/block/replace-object-geometry` |
| MCP | 6 surfaces (see parity table below) |

### ABI discipline

- Verify both constants match at head before bumping.
- New callback struct field appended at the **end** of `GhBridgeRegistration`
  on both sides, identical ordinal position.
- Both sides bumped in the same commit — no cross-commit ABI drift.

### MCP parity surfaces (audit run 2026-04-14)

Strict parity rule: add to surface X iff single-target
`rhino_block_replace_object_geometry` is on X. Audit confirmed 6 surfaces:

| File | Change |
|------|--------|
| `mcp_server/src/rook/server.py` | Tool definition + dispatcher `case` |
| `mcp_server/src/rook/agent/tool_dispatcher.py` | Route mapping |
| `mcp_server/src/rook/agent/tool_groups.py` | Group membership |
| `mcp_server/src/rook/learning/agent.py` | Fallback list (~line 64) + route table (~line 221) |
| `mcp_server/src/rook/explorer/registry.py` | `TOOL_CATEGORIES` entry (`CATEGORY_MODIFICATION`) |
| `mcp_server/src/rook/explorer/executor.py` | Endpoint map entry |

**Total touch count: 12 files** (4 C++, 2 C#, 6 MCP).

## Request / response contract

### Request

```json
{
  "items": [
    {"name": "BlockA", "index": 0, "sourceId": "guid-1"},
    {"name": "BlockA", "index": 2, "sourceId": "guid-2", "deleteOriginal": false},
    {"name": "BlockB", "index": 0, "sourceId": "guid-3"}
  ],
  "redraw": false
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `items` | yes | array | Contract violation if missing or `ValueKind != Array` |
| `items[].name` | yes | string | Block definition name |
| `items[].index` | yes | integer | 0-based; negatives pass shape, caught at resolution as `index_out_of_range` (parity with single-target at `BlocksHandler.cs:4532`) |
| `items[].sourceId` | yes | string (GUID) | Malformed / non-string → `invalid_source_id`; parseable-but-unresolved → `source_not_found` |
| `items[].deleteOriginal` | no | boolean | Default `true`; omitted ≡ `true` for policy-conflict purposes (FORK 3 rule) |
| `redraw` | no | boolean | Default `true`; `ValueKind ∉ {True, False}` → whole-request error |

### Response

```json
{
  "routed": 47,
  "skipped": 3,
  "total": 50,
  "deletedSources": ["guid-1", "guid-3"],
  "errors": [
    {"name": "BlockA", "index": 3, "error": "index_out_of_range", "message": "..."},
    {"name": "BlockB", "index": 0, "error": "conflicting_delete_flag", "message": "..."}
  ]
}
```

- `errors[].name` echoes the request item's `name` verbatim, captured as raw
  `JsonElement` (non-string values like `123` / `null` round-trip, per the
  PR #14 non-string-echo convention).
- `errors[].index` echoes when the shape allowed it to parse; omitted on
  `invalid_index`.
- `deletedSources` always present; empty array `[]` when nothing was deleted
  (stable shape).
- Empty `items[]` → `{"routed": 0, "skipped": 0, "total": 0, "deletedSources": [], "errors": []}`, HTTP success. A caller sending an empty batch is a no-op, not an error.

## Processing pipeline

Four phases. Fail-fast at the first matching error code per item. All phases
run inside one `UndoScope(doc, "Batch Replace Block Object Geometry")`.

### Phase 1 — Shape validation (pure payload)

Runs per item, independent. Produces shape-error set. Items with shape errors
are marked skipped and do **not** reserve a `(name, index)` slot for
relational validation.

| Code | Trigger |
|------|---------|
| `invalid_name` | `name` missing, non-string, or empty |
| `invalid_index` | `index` missing or not an integer |
| `invalid_source_id` | `sourceId` missing, non-string, or unparseable as GUID |
| `invalid_delete_flag` | `deleteOriginal` present but not boolean |

### Phase 2 — Relational validation (cross-item, first-occurrence-wins)

Iterate remaining shape-valid items in request order. Relational order is
load-bearing: `duplicate_target` checked before `conflicting_delete_flag`. If
an item already lost the `(name, index)` slot, that's the more local
diagnosis; no need to also report a policy conflict.

| Code | Trigger |
|------|---------|
| `duplicate_target` | An earlier shape-valid item used the same `(name, index)` pair |
| `conflicting_delete_flag` | An earlier shape-valid item referenced the same `sourceId` with a different **effective** `deleteOriginal` value (omitted ≡ `true`) |

The first occurrence of a given `(name, index)` wins the slot. The first
occurrence of a given `sourceId` establishes that source's delete policy.

### Phase 3 — Grouping and resolution

Group surviving items by `name`. Per group, **snapshot semantics are fixed
for the entire group**:

1. Resolve `idef = doc.InstanceDefinitions.Find(name)`. Missing → **all items
   in this group** are marked `block_not_found`; group is skipped.
2. Read `existingObjects = idef.GetObjects()` exactly **once** at group entry.
3. Per item, validate against that fixed snapshot:
   - `source_not_found` if `doc.Objects.FindId(sourceGuid) == null`
   - `source_has_no_geometry` if `sourceObj.Geometry == null`
   - `index_out_of_range` if `index < 0 || index >= existingObjects.Length`

Items failing resolution are individually skipped; the group continues with
the remaining surviving items. No re-reads of `existingObjects` mid-group.

### Phase 4 — Group rebuild and deferred deletion

For each group with ≥1 surviving item:

1. Build `allGeometry[]` and `allAttributes[]` from the **same fixed
   snapshot** used for resolution:
   - `allAttributes[i] = existingObjects[i].Attributes.Duplicate()` for every
     `i`, **unchanged**. This is the core parity invariant with single-target:
     we replace geometry, not attributes.
   - `allGeometry[i] = existingObjects[i].Geometry.Duplicate()` for every
     `i`, **except** at each surviving item's target index, where
     `allGeometry[targetIndex] = sourceObj.Geometry.Duplicate()`.
2. Call `doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes)`.
3. On `false` — **all surviving items in this group** get `group_modify_failed`.
   **No per-item retries.** Other groups proceed independently.
4. On `true` — all surviving items in the group count as routed. Queue their
   source GUIDs for deletion if the established policy is `true`.

After all groups complete:

5. Execute `doc.Objects.Delete(guid, true)` for each queued GUID (de-duped).
6. `deletedSources` contains the GUIDs for which `Delete` returned `true`,
   in insertion order, uniqued.
7. Final `doc.Views.Redraw()` guarded by the top-level `redraw` flag.

**Deletion failure policy (explicit):**

- `routed` status is cemented at successful group rebuild; later source
  deletion outcomes do not change `routed` / `skipped` counts.
- `deletedSources` contains only GUIDs whose `Delete(guid, true)` actually
  succeeded. This is the authoritative lifecycle audit.
- Failed deletions (source held by another reference, concurrent delete, etc.)
  are silent at the per-item error level — no new error code, no taxonomy
  entry. Callers noticing `guid ∈ item.sourceId` but `guid ∉ deletedSources`
  know the delete didn't complete.

## Error taxonomy (consolidated)

### Contract-level (whole-request → HTTP error)
- Body missing / null / unparseable JSON
- `items` missing or `ValueKind != Array`
- `redraw` present but `ValueKind ∉ {True, False}`

### Per-item shape (phase 1)
`invalid_name`, `invalid_index`, `invalid_source_id`, `invalid_delete_flag`.

### Per-item relational (phase 2, first-occurrence-wins, ordered)
`duplicate_target`, `conflicting_delete_flag`.

### Per-item resolution (phase 3, against fixed group snapshot)
`block_not_found`, `source_not_found`, `source_has_no_geometry`, `index_out_of_range`.

### Per-item execution (phase 4, whole group)
`group_modify_failed` — narrow semantic: only fires when `ModifyGeometry`
returns `false` after every item in the group passed shape, relational, and
resolution phases. Naming explicit to make the blast radius clear (coalesced
rebuild failed for the definition group, not an item-level mutation).

### Fallback
`exception` — unexpected throw after shape validation; not a catch-all.

**Shape-vs-resolution split rationale:** callers retry differently. Shape
errors mean "fix the payload"; resolution errors mean "the referenced
resource doesn't exist or is out of bounds in this document." Distinct
actionability.

**`source_not_found` vs `invalid_source_id` boundary:** a parseable GUID that
doesn't resolve in `doc.Objects` is `source_not_found` (resolution). A
malformed / non-string / unparseable value is `invalid_source_id` (shape).
This boundary matters in tests.

## Shared helper discipline

The current `BlocksHandler.ReplaceObjectGeometry` inlines all validation and
geometry composition. Extract into file-local helpers (anonymous namespace or
`private static`; not in a header) that **both** single-target and batch call.
Refactor single-target to use them in the same PR.

**Principle, not exact signature** (finalize in plan doc):

- **Shape parser** for one item: validates `name` / `index` / `sourceId` /
  `deleteOriginal` types; returns a `ReplaceItemShape` record or a shape error
  code.
- **Resolution resolver** against a fixed `idef` snapshot: takes
  `(doc, idef, existingObjects, shape)` and returns the resolved
  `(sourceObj, targetIndex)` pair or a resolution error code.

**Attribute-preservation rule applies to both callers.** The shared helper
returns the resolved source and target index, but the rebuild path —
single-target **and** batch — must preserve the original block-slot
attributes unchanged:

- `allAttributes[i] = existingObjects[i].Attributes.Duplicate()` for every `i`.
- `allGeometry[i]` swapped only at the target index.

This is the parity invariant that the single-target establishes; the batch
inherits it, and the shared helper makes drift a refactor concern rather than
a silent divergence.

## Undo semantics

One `UndoScope(doc, "Batch Replace Block Object Geometry")` wraps the whole
pipeline, including all group rebuilds and all source deletions. Single
Ctrl+Z reverts everything as one step regardless of routed/skipped mix.
Skipped items never mutated state and have nothing to revert.

## Risks

| Risk | Mitigation |
|------|-----------|
| ABI drift (managed/native out of sync) | Both sides bump in same commit; Codex review validates; boot-time ABI check rejects mismatch; `BridgeAbiVersion` ≡ `kGhBridgeAbiVersion` assertion in testing |
| Parity drift single-target vs batch | Shared validation helpers; refactor single-target to use them in same PR; parity spot-check test |
| Group-snapshot drift | Fixed `idef` + `existingObjects` snapshot per group; never re-read mid-group; explicit invariant |
| Attribute clobbering | Rule stated explicitly in Phase 4 + in shared-helper section; test #8 verifies |
| Partial deletion aftermath | `routed` cemented at rebuild success; failed `Delete` calls silent at error level; `deletedSources` authoritative |
| `conflicting_delete_flag` surprises callers | Documented in MCP tool description; first-wins ordering explicit; `deletedSources` lets callers verify intent |
| `ModifyGeometry` cost at large groups | Not optimized. Bounded by real Revit-cleanup workloads. Deferred as out-of-scope |

## Testing plan

### Static

- Native Release x64 build clean
- Companion net7.0 build clean (0 errors, auto-deploys)
- Python `py_compile` clean for all 6 MCP files
- Grep: `rhino_block_replace_object_geometry_batch` present in all 6 parity
  surfaces
- Grep scoped to `src/RookNative/RookServer.cpp` for the pattern `m_server->Post(...,.*/block/replace-object-geometry-batch` — must match exactly once (the native registration site). Repo-wide grep for the raw route string is expected to return multiple hits after Step 5 MCP parity lands, so the uniqueness check must be file-scoped, not global
- ABI constants match (`BridgeAbiVersion == kGhBridgeAbiVersion == 11`)
- Manual scan for paste-errors (no accidental copies of `replace_geometry`
  vs `replace_object_geometry` vs the `_batch` suffix)

### Live (scratch blocks in `M2-UPPER PODIUM.3dm` or dedicated test file)

| # | Test | Expected |
|---|------|----------|
| 1 | Happy path: 3 items, 2 blocks, all valid | `routed: 3, skipped: 0, total: 3`, `deletedSources` has 3 GUIDs |
| 2 | Shape errors: `name: null`, `index: "0"`, `sourceId: 42`, `deleteOriginal: "yes"` | `routed: 0, skipped: 4` with four distinct `invalid_*` codes |
| 3 | Relational — `duplicate_target`: two items on same `(BlockA, 0)` | `routed: 1, skipped: 1` with `duplicate_target` on item 2 |
| 4 | Relational — `conflicting_delete_flag`: two items with same `sourceId`, different `deleteOriginal` | `routed: 1, skipped: 1` with `conflicting_delete_flag` on item 2 |
| 5 | Resolution errors: mix of `block_not_found`, `source_not_found`, `source_has_no_geometry`, `index_out_of_range` | Per-item codes; other items still route |
| 6 | **`group_modify_failed` is an explicitly uncovered branch for this PR.** No companion test project exists today; establishing one is out-of-scope. Test path: if a concrete Rhino state producing `ModifyGeometry == false` is identified during implementation, document a manual repro and exercise it. Otherwise the branch of the taxonomy is shipped uncovered, matching the single-target's existing coverage posture. Gap is tracked in Out-of-scope follow-ups | Manual repro (if found) exercises the code path; if no repro identified, branch ships uncovered |
| 7 | **Multi-block coalescing verified by counter** — 5 items across 3 blocks. Instrument the companion's `ModifyGeometry` call site with a temporary debug counter or explicit log line; assert counter = 3, not 5. Not behavioral guesswork. Counter/log removed before merge. | Exactly 3 `ModifyGeometry` calls |
| 8 | Attribute preservation: target object has custom color + user-string; post-replace those are retained | Attributes survive; only geometry changed |
| 9 | `deleteOriginal` matrix: explicit `true`, explicit `false`, omitted (default `true`) | `deletedSources` matches expected set (omitted ≡ true) |
| 10 | Same `sourceId` in N routed items all effective-true | `deletedSources` contains the GUID exactly once |
| 11 | Empty `items[]` | `{routed: 0, skipped: 0, total: 0, deletedSources: [], errors: []}`, HTTP success |
| 12 | Contract violation: `items: "not-an-array"` | Whole-request HTTP error |
| 13 | `redraw: "false"` (string) | Whole-request error, not per-item |
| 14 | Undo (Ctrl+Z) after mixed batch | Single undo step reverts all routed rebuilds AND all deletions |
| 15 | Parity spot-check: same single item via single-target vs 1-item batch | Identical post-state (block geometry + attributes + source lifecycle) |

### Verification tools

- `rhino_block_objects_detailed` for post-rebuild state
- `rhino_objects` to verify source lifecycle matches `deletedSources`
- Rhino viewport visual confirmation

### Deferred

- Perf at 500+ items — not a throughput-claim feature
- Chain-deferred-redraw multi-batch — same principle as prior PRs

## Out-of-scope follow-ups

- **Companion test project scaffolding.** No C# test harness currently
  exists in the repo (`src/Rook/Rook.csproj` is the only companion project).
  A dedicated test project (xUnit or similar) with a stubbable seam around
  `InstanceDefinitions.ModifyGeometry` would let us cover
  `group_modify_failed` without relying on a manual Rhino repro — and would
  unlock similar coverage for other companion-side batch handlers. Requires
  its own design pass: test framework choice, build/deploy integration, CI
  wiring. Separate PR.
- **Geometry-type compatibility checks.** The single-target accepts any
  non-null `Geometry`, including `InstanceReferenceGeometry`. Batch inherits.
  A future "strict mode" flag could reject `InstanceReference`-as-source,
  cross-dimensional mismatches, or other weirdness. Not this PR.
- **Per-item `replacedGeometryType` readback.** The single-target returns
  `newGeometryType` in its response; the batch does not in per-item form.
  If a caller surfaces the need, add an `includeReplacementTypes: true`
  opt-in.
- **Zero-cost re-entry for retry scenarios.** A caller with a partially
  failed batch currently has to re-shape their payload. A future
  "`retryFromErrors: [...]`" helper could flip the ergonomics.
- **Next roadmap item:** `rhino_block_transform_object_batch` (#7) — pattern
  from this PR transfers with minor shape differences (transform spec vs
  geometry source).
