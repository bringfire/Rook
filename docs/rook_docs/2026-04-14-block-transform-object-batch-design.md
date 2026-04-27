# `rhino_block_transform_object_batch` — Design

**Date:** 2026-04-14
**Status:** Approved (brainstorm complete)
**Author:** Claude + bringfire (review)
**Roadmap entry:** `rook_docs/2026-04-13-batch-tools-roadmap.md` entry #7
**Pattern siblings:** `2026-04-14-block-replace-object-geometry-batch-design.md` (PR #21 — closest pattern: coalesced per-block, fixed snapshot, shared helpers, attribute preservation, whole-item skip semantics), `2026-04-14-transform-instance-batch-design.md` (PR #14 — transform-spec parsing reference, but operates on instances not block-def objects)

## Goal

Batch variant of `rhino_block_transform_object`. Apply move/rotate/scale/scale3d
transforms to objects inside one or more block definitions in a single call.
Companion-backed via the P/Invoke bridge, coalesced per-definition rebuild,
single `UndoScope`, best-effort per-item semantics, compact summary response.
The item is the atomic unit: overlap failures and transform-math failures
skip the whole item; group-level `ModifyGeometry` failure escalates to all
items that committed to that group.

## Non-goals

- No new transform types beyond the four the single-target supports (`move`, `rotate`, `scale`, `scale3d`).
- No per-slot blast-radius granularity. Slot-level failures (overlap or `geom.Transform` returning false) skip the whole item.
- No transform composition across items. Two items targeting the same `(name, index)` → later item skipped with `overlapping_indices`. No silent composition.
- No per-success metadata in the response. Callers query post-state via `rhino_block_objects_detailed`.
- No zero-check tightening on scale factor. Scale `factor: 0` and `scale3d` components of `0` are accepted **at parse phase** — matches the live single-target wire behavior. Runtime outcome (routed vs `item_transform_failed` vs silent degenerate geometry) is whatever `geom.Transform(xform)` returns for the chosen geometry; not promised here. Not a regression either way.

## Architecture

**Route:** `POST /block/transform-object-batch`, companion-backed via the
P/Invoke bridge.

**ABI bump 11 → 12, atomic both sides, single commit.**

### Wiring

| Layer | Change |
|-------|--------|
| C# companion (`BlocksHandler.cs`) | New method `TransformBlockObjectBatch(string? body)`; shared transform-spec parser extracted from existing `TransformBlockObject`; single-target refactored to use helpers in the same PR |
| Bridge managed (`NativeGhBridgeRegistrar.cs`) | New delegate typedef + struct field append; `BridgeAbiVersion` 11 → 12; P/Invoke handler wires body through to BlocksHandler |
| Native proxy (`GrasshopperProxyHandler.cpp/h`) | New `HandleManagedBlockTransformObjectBatch`; struct field append at same ordinal position as managed; `kGhBridgeAbiVersion` 11 → 12 |
| Native server (`RookServer.cpp/h`) | New class-level forwarder + route registration next to `/block/transform-object` |
| MCP | 6 surfaces (see parity table below) |

### ABI discipline

- Verify both constants match `v11` at head before bumping.
- New callback struct field appended at the **end** of `GhBridgeRegistration` on both sides, identical ordinal position.
- Both sides bumped in the same commit — no cross-commit ABI drift.

### MCP parity surfaces

Strict parity rule: add to surface X iff single-target
`rhino_block_transform_object` is on X. Audit run before implementation; all
6 MCP surfaces expected to match PR #21's placement pattern:

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
    {"name": "BlockA", "indices": [0, 1, 2], "transform": {"type": "rotate", "angle": 90, "axis": [0, 0, 1], "center": [0, 0, 0]}},
    {"name": "BlockA", "indices": [3, 4],    "transform": {"type": "move",   "x": 10, "y": 0, "z": 0}},
    {"name": "BlockB", "indices": [0],       "transform": {"type": "scale",  "factor": 2.0, "center": [0, 0, 0]}}
  ],
  "redraw": false
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `items` | yes | array | Contract violation if missing or `ValueKind != Array`. Envelope non-object guard inherited from PR #21 |
| `items[].name` | yes | string | Block definition name |
| `items[].indices` | yes | integer[] | Non-empty; integer element type enforced at shape phase. Duplicates **silently deduped** via `HashSet<int>` (matches single-target `BlocksHandler.cs:5048`). `HashSet<int>` is used internally; serialized output (response echo + error-message subsets) is always **sorted ascending** for API stability |
| `items[].transform` | yes | object | `{type, ...params}`. Type one of `move` / `rotate` / `scale` / `scale3d`. Params match single-target exactly |
| `redraw` | no | boolean | Default `true`; `ValueKind ∉ {True, False}` → whole-request error |

### Transform spec shapes (parity with single-target)

| Type | Params |
|------|--------|
| `move` | `x`, `y`, `z` (optional, default 0) |
| `rotate` | `angle` (degrees; required), `axis` (3-element array, default `[0,0,1]`), `center` (3-element array, default `[0,0,0]`) |
| `scale` | `factor` (required), `center` (3-element array, default `[0,0,0]`). **Zero factor accepted at parse phase** — matches single-target loose parse behavior. Runtime outcome depends on `geom.Transform` |
| `scale3d` | `x`, `y`, `z` (optional, default 1), `center` (3-element array, default `[0,0,0]`). **Zero component accepted at parse phase** — matches single-target loose parse behavior. Runtime outcome depends on `geom.Transform` |

### Response

```json
{
  "routed": 2,
  "skipped": 1,
  "total": 3,
  "errors": [
    {"name": "BlockA", "indices": [3, 4], "error": "overlapping_indices", "message": "index 3 already claimed by an earlier item for block 'BlockA'"}
  ]
}
```

- `errors[].name` echoes request item's `name` verbatim (raw `JsonElement`; non-string / null / missing values round-trip, per PR #21 convention).
- `errors[].indices` echoes the request item's `indices` as the **deduped set**, **serialized in ascending order** for stable API output. Omitted on `invalid_indices`.
- Any overlap subsets embedded in `error.message` (for `overlapping_indices`) are likewise listed in ascending order.
- Empty `items[]` → `{"routed": 0, "skipped": 0, "total": 0, "errors": []}`, HTTP success.

## Processing pipeline

Four phases. Fail-fast at the first matching error code per item. Whole
pipeline inside one `UndoScope(doc, "Batch Transform Block Objects")`.

### Phase 1 — Shape validation (pure payload, per item, independent)

Shape errors collected into `errors[]`; items fail out of the pipeline.
Deduped `indices` set carried forward on success.

| Code | Trigger |
|------|---------|
| `invalid_name` | `name` missing, non-string, or empty |
| `invalid_indices` | `indices` missing, not an array, empty, or contains a non-integer element (single code, multiple trigger paths) |
| `invalid_transform` | `transform` missing or not an object |
| `invalid_transform_type` | `transform.type` missing, non-string, or not one of `move` / `rotate` / `scale` / `scale3d` |
| `invalid_move` | `move` present but `x`/`y`/`z` non-numeric |
| `invalid_rotate` | `rotate.angle` missing or non-numeric, OR `axis` / `center` present with invalid shape |
| `invalid_scale` | `scale.factor` missing or non-numeric, OR `center` present with invalid shape. **Zero factor is NOT invalid** (loose parity) |
| `invalid_scale3d` | `scale3d.x`/`y`/`z` non-numeric, OR `center` present with invalid shape. **Zero component is NOT invalid** (loose parity) |

### Phase 2 — Relational validation (cross-item, first-occurrence-wins)

Iterate shape-valid items in request order. Maintain a per-block set of
claimed indices. For each item:

| Code | Trigger |
|------|---------|
| `overlapping_indices` | For this item's `(name, index)` pairs, at least one was already claimed by an earlier shape-valid item targeting the same block. Whole item skipped. Error message lists the overlapping subset |

The claim set grows as items pass phase 2.

### Phase 3 — Grouping and resolution (per-group fixed snapshot)

Group surviving items by `name`. Per group:

1. Resolve `idef = doc.InstanceDefinitions.Find(name)`. Missing → **all items in this group** marked `block_not_found`; group is skipped.
2. Read `existingObjects = idef.GetObjects()` exactly **once** at group entry. Snapshot is fixed for the whole group.
3. Per item: validate every index in its deduped set against `existingObjects.Length`. Any index out of range → item marked `index_out_of_range` (message includes the offending index), whole item skipped.

### Phase 4 — Group rebuild (try-then-commit per item)

Build `allGeometry[]` / `allAttributes[]` from the same fixed snapshot used
for resolution:

- `allAttributes[i] = existingObjects[i].Attributes.Duplicate()` for every `i`, **unchanged**. Attribute-preservation invariant (inherited from PR #21): only geometry is modified, attributes are preserved across every slot.
- `allGeometry[i] = existingObjects[i].Geometry.Duplicate()` for every `i` initially.

Per surviving item in the group, in order:

- For each `idx` in the item's deduped `indices[]`: duplicate the snapshot geometry at `idx`, call `geom.Transform(xform)`.
- If **any** of the item's indices returns `false` from `geom.Transform`, mark item `item_transform_failed` (message lists the failed indices); discard the item's proposed geometries; **do not** commit any of its changes into `allGeometry`.
- If all succeed, commit the transformed geometries: `allGeometry[idx] = transformedGeom` for each idx in the item.

After all items processed for the group, call
`doc.InstanceDefinitions.ModifyGeometry(idef.Index, allGeometry, allAttributes)` once:

- On `false` → **all items that committed into this group's `allGeometry`** are marked `group_modify_failed`. Narrow semantic: only fires after every committed item passed shape, relational, resolution, and per-item transform phases.
- On `true` → those items count as routed.

Items with slot-level failures (`overlapping_indices`, `index_out_of_range`,
`item_transform_failed`, `block_not_found`) never contribute to
`ModifyGeometry`.

`doc.Views.Redraw()` at the end if `redraw` is true (default).

### Fallback

`exception` — unexpected throw after shape validation; not a catch-all.

## Error taxonomy (consolidated)

### Contract-level (whole-request HTTP error)
- Body missing / null / unparseable JSON
- Body not a JSON object (`ValueKind != Object`) — envelope guard inherited from PR #21
- `items` missing or `ValueKind != Array`
- `redraw` present but `ValueKind ∉ {True, False}`

### Per-item shape (phase 1)
`invalid_name`, `invalid_indices`, `invalid_transform`, `invalid_transform_type`, `invalid_move`, `invalid_rotate`, `invalid_scale`, `invalid_scale3d`.

### Per-item relational (phase 2)
`overlapping_indices`.

### Per-item resolution (phase 3)
`block_not_found`, `index_out_of_range`.

### Per-item execution (phase 4)
`item_transform_failed` (slot-level math failure; whole item skipped);
`group_modify_failed` (group-level `ModifyGeometry` returned `false`; applies
to every item that committed to that group).

### Fallback
`exception`.

**Shape-vs-resolution split rationale:** callers retry differently. Shape
errors mean "fix the payload"; relational errors mean "your payload conflicts
with itself"; resolution errors mean "the referenced resource doesn't exist
or the index is out of bounds"; execution errors mean "the math itself
didn't apply." Distinct actionability.

## Shared helper discipline

The current `TransformBlockObject` inlines all validation and transform
composition. Extract into file-local helpers used by **both** single-target
and batch. Refactor single-target to call them in the same PR.

### Helpers to extract

- **`TryParseTransformSpec(JsonElement transformEl, out Transform xform, out string? errorCode, out string? errorMessage)`** — parses `{type, ...params}` into a concrete `Transform`. Preserves single-target's loose zero-scale behavior: `factor: 0` and zero components in `scale3d` are accepted.
- **`TryParseTransformItemShape(JsonElement itemEl, out TransformItemShape shape, out string? errorCode, out string? errorMessage)`** — parses one item's `{name, indices[], transform}`. Dedupes `indices[]` into a `HashSet<int>` silently (matches `BlocksHandler.cs:5048`). Delegates to `TryParseTransformSpec`.
- **`TryValidateItemIndicesAgainstSnapshot(RhinoObject[] existingObjects, HashSet<int> indices, out int offendingIndex, out string? errorMessage)`** — resolution helper, returns the first offending index on failure (if any).

### Guardrail

The existing helper `TryParseScaleOp` (`BlocksHandler.cs:5216`) is
**intentionally NOT reused**. It serves the TransformInstance family and
operates on a different scale shape (scalar-or-3-array) with strict
zero-rejection semantics. Reusing it here would silently tighten
`rhino_block_transform_object`'s public wire contract. The new
`TryParseTransformSpec` preserves loose behavior by design. Any future
tightening must be an opt-in flag (pattern: `strictDeleteFlag` in PR #21),
never a silent helper swap.

## Attribute preservation invariant

Inherited verbatim from PR #21:

- `allAttributes[i] = existingObjects[i].Attributes.Duplicate()` for every `i`, **unchanged**.
- `allGeometry[i]` only modified at indices present in a successfully-committed item.

This is the core parity invariant with single-target. Test #8 verifies.

## Undo semantics

Single `UndoScope(doc, "Batch Transform Block Objects")` wraps the whole
pipeline. Routed items revert as one `Ctrl+Z` step regardless of
routed/skipped mix. Skipped items never mutated state and have nothing to
revert.

## Risks

| Risk | Mitigation |
|------|-----------|
| ABI drift (managed/native out of sync) | Both sides bump in same commit; Codex review; boot-time ABI check rejects mismatch |
| Accidental strictness regression via `TryParseScaleOp` reuse | Explicit note in helper docstring + design doc + commit message: different scale shape, different strictness, do NOT reuse |
| Parity drift single-target vs batch | Shared helpers + refactor in same PR + parity spot-check live test |
| Group-snapshot drift | Fixed `idef` + `existingObjects` snapshot read once per group; never re-read mid-group |
| Attribute clobbering | Rule stated in Phase 4 + shared-helper section; test #8 verifies |
| Overlap composition surprise | `overlapping_indices` explicit; documented in MCP tool description; no silent compose |
| Slot-level `geom.Transform == false` blast radius | Whole-item skip; siblings in same group unaffected; proposed geometries discarded before reaching `allGeometry` |
| Confusing contract error on non-object body | Envelope `ValueKind != Object` guard (PR #21 pattern inherited) |

## Testing plan

### Static

- Native Release x64 build clean
- Companion net7.0 build clean (0 errors, auto-deploys)
- Python `py_compile` clean for all 6 MCP files
- Grep: `rhino_block_transform_object_batch` present in all 6 parity surfaces
- Grep scoped to `src/RookNative/RookServer.cpp` for `m_server->Post(...,.*/block/transform-object-batch` — must match exactly once. Repo-wide grep for the raw route string is expected to return multiple hits after MCP parity lands; the uniqueness check is deliberately file-scoped to the native registration site
- ABI constants match: `BridgeAbiVersion == kGhBridgeAbiVersion == 12`
- Manual scan for paste-errors (no accidental copies of `transform-object` vs `transform-object-batch`, or cross-contamination with `replace-object-geometry`)

### Live (via MCP; scratch blocks on a safe test file)

| # | Test | Expected |
|---|------|----------|
| 1 | Happy path: 3 items across 2 blocks exercising `rotate`, `move`, `scale` | `routed: 3, skipped: 0, total: 3` |
| 2 | Shape error survey: one item each triggering `invalid_transform`, `invalid_transform_type`, `invalid_move`, `invalid_rotate`, `invalid_scale`, `invalid_scale3d` | 6 distinct codes, all `routed: 0` on their items |
| 3 | `invalid_indices` trigger survey — one item each with: missing `indices`, empty `[]`, non-array `"nope"`, non-integer element `[0, "a", 2]` | All four return `invalid_indices` (single code, four trigger paths); messages distinct |
| 4 | Relational: two items targeting `BlockA` with overlapping `[2, 3]` indices | `routed: 1, skipped: 1`, second item `overlapping_indices` with overlapping subset listed |
| 5 | Resolution: mix of `block_not_found` (whole group) and `index_out_of_range` (single item) | Per-item codes; other groups unaffected |
| 6 | **`item_transform_failed`** — explicitly uncovered branch. No concrete `geom.Transform == false` state identified during this session; ships uncovered matching PR #21's `group_modify_failed` disposition. Logged in Deferred Follow-Up |
| 7 | Multi-block coalescing: 4 items across 3 blocks | `routed: 4`; one `ModifyGeometry` call per block expected (behavioral verification; direct counter instrumentation deferred per prior roadmap pattern) |
| 8 | **Attribute preservation** — target object in block has custom color + custom user string; post-transform both survive unchanged, only geometry changes |
| 9 | Duplicate indices within one item: `indices: [0, 0, 1]` | Silently deduped to `{0, 1}`; item routes with 2 slots transformed. Any serialized echo (e.g. `errors[].indices` if this item errored for another reason) must be `[0, 1]` in ascending order — deterministic regardless of `HashSet` iteration order |
| 10 | Zero-scale parse-phase acceptance: `{type: "scale", factor: 0}` on a given test geometry | Must **not** fail as `invalid_scale` at the shape phase. Runtime outcome (routed vs `item_transform_failed`) matches whatever single-target returns on the same geometry. Parity spot-check against single-target is the validation, not an absolute "routed" assertion |
| 11 | Empty `items[]` | `{routed: 0, skipped: 0, total: 0, errors: []}`, HTTP success |
| 12 | Undo (Ctrl+Z) after mixed-block routed batch | Single undo step reverts all group rebuilds |
| 13 | Parity spot-check: `rhino_block_transform_object` with `{indices: [0], transform: ...}` vs batch with one item `{indices: [0], transform: ...}` on same block | Identical post-state (geometry bbox + attributes) |

### Boundary-validated by MCP schema (not exercisable via MCP direct)

MCP's `inputSchema` enforces types at the boundary. These malformed requests
never reach the handler through the MCP path; the handler's defensive guards
(including the PR #21 non-object-body guard inherited here) are preserved in
code but cannot be exercised via MCP this session:

- Non-string `name`, non-array `indices`, non-object `transform`, non-boolean `redraw` at the MCP item or envelope level
- `items: "not-an-array"` at envelope level
- Non-object request body (e.g. `body = "foo"`)
- `redraw: "false"` (string) at envelope level

Handler-path coverage for these would require direct HTTP, which CLAUDE.md
disallows. Preservation of the defensive guards in code is the test evidence.

### Deferred

- `item_transform_failed` coverage — same disposition as PR #21's `group_modify_failed`. No companion test harness exists today; requires a separate infrastructure PR to close.
- `group_modify_failed` coverage — inherited gap from PR #21. Closed by the same future test-harness PR.
- Perf at 500+ items — not a throughput-claim feature.
- Chain-deferred-redraw multi-batch — same principle as prior PRs.

## Out-of-scope follow-ups

- **Companion test project scaffolding.** Logged previously (in PR #21's design doc follow-ups). Continues to be the closure path for `item_transform_failed` and `group_modify_failed` coverage.
- **New transform types.** If future workflows need `reflect`, `shear`, `four-point-alignment`, etc., add them to both single-target and batch in a dedicated PR with its own fork resolution.
- **Strict zero-scale opt-in.** A `strictScale: true` flag could reject zero factor/components. Pattern is known from PR #21's `strictDeleteFlag`. Only worth adding if a real caller surfaces the need.
- **Next roadmap item:** `rhino_block_replace_instance_batch` (#8) — different family (instance-level not definition-level); transform-instance-batch (PR #14) is the closer pattern reference.
