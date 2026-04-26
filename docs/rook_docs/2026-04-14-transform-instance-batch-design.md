# `rhino_block_transform_instance_batch` — Design

**Date:** 2026-04-14
**Status:** Approved (brainstorm complete)
**Author:** Claude + bringfire (review)
**Roadmap entry:** `rook_docs/2026-04-13-batch-tools-roadmap.md` #7

## Goal

Add a batch variant of `rhino_block_transform_instance` that applies incremental
transforms (scale / rotate / move / mirror) to many block instances in one call,
under a single undo scope, with best-effort per-item error semantics.

## Non-goals

- No support for absolute (non-incremental) transforms — parity with single-target only.
- No per-item position readback in the default response (add `includePositions` flag later if needed).
- No perf optimizations targeting 10k+ items — cleanup workflows stay well below that ceiling.
- No de-duplication of GUIDs in `items[]`. Duplicates apply in order.

## Architecture

**Route:** `POST /block/transform-instance-batch`, companion-backed via the
existing managed-companion bridge. Reasoning:

1. Block-instance transform semantics already live in C# (`BlocksHandler.TransformInstance`).
2. A native re-implementation would duplicate the transform-composition logic
   (scale → rotate → move → mirror around instance pivot), creating two transform
   engines to keep in sync for no practical latency win.
3. Matches the established pattern for the 5 batch tools already shipped (PR #13).

**Wiring (identical to the PR #13 wiring pattern):**

| Layer | Change |
|-------|--------|
| C# companion (`BlocksHandler.cs`) | New method `TransformInstanceBatch(string? body)` |
| Bridge (`NativeGhBridgeRegistrar.cs`) | New delegate, new struct field, new P/Invoke handler; `BridgeAbiVersion` 9 → 10 |
| Native proxy (`GrasshopperProxyHandler.cpp/h`) | New `HandleManagedBlockTransformInstanceBatch`; new struct field; `kGhBridgeAbiVersion` 9 → 10 |
| Native server (`RookServer.cpp/h`) | New forwarder method, new route registration in the managed/proxy section |
| MCP (`mcp_server/src/rook/server.py`) | New tool `rhino_block_transform_instance_batch` + case handler |

**ABI discipline:**
- Verify current `BridgeAbiVersion` at head before bumping (trust the repo, not memory).
- New callback field appended to the end of `GhBridgeRegistration` on both sides.
- Bridge version bumped synchronously on both managed and native sides.

## Request / response contract

### Request

```json
{
  "items": [
    {"id": "guid1", "move": [10, 0, 0]},
    {"id": "guid2", "rotate": 45, "scale": 0.5},
    {"id": "guid3", "mirror": {"normal": [1, 0, 0], "origin": [0, 0, 0]}}
  ],
  "redraw": false
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `items` | yes | array | Contract violation if missing or not an array |
| `items[].id` | yes | string (GUID) | Instance GUID |
| `items[].move` | no | `[dx, dy, dz]` | 3-element numeric array |
| `items[].rotate` | no | number | Z-axis degrees at instance pivot |
| `items[].scale` | no | number OR `[sx, sy, sz]` | Scalar or 3-element array; matches single-target parser |
| `items[].mirror` | no | `{normal: [x,y,z], origin: [x,y,z]}` | Both fields required; `normal` must be non-zero |
| `redraw` | no | boolean | Default `true`. Guarded on `JsonValueKind ∈ {True, False}` |

**Per-item rule:** Each item must specify at least one of
`move` / `rotate` / `scale` / `mirror`; otherwise it counts as skipped with
`{"error": "no_ops"}`.

**Per-item composition order:** same as single-target —
**scale → rotate → move → mirror**, pivoted at the instance's current
`M03/M13/M23` translation component.

**Duplicate-GUID behavior (corrected after Codex round 2):** Both the native
single-target route and the companion batch method call
`doc.Objects.Transform(guid, xform, deleteOriginal: true)`, which deletes the
original instance and returns a new GUID on success. Consequently, if the same
GUID appears twice in `items[]`, iteration 2 resolves `not_found` because the
original no longer exists. Callers that want to apply multiple transforms to
one instance should either compose them into a single item's op combo or call
the batch again with the replacement GUID.

Earlier plan language claimed duplicates would "accumulate against the current
state — matching N sequential single-target calls." That was incorrect: native
single-target also mutates the GUID, so N sequential calls must each target
the latest replacement. The behavior we actually ship is consistent with that
lifecycle; we just don't automatically resolve GUID remappings within a batch.

### Response

```json
{
  "routed": 487,
  "skipped": 13,
  "total": 500,
  "errors": [
    {"id": "guid-x", "error": "not_found"},
    {"id": "guid-y", "error": "not_instance"},
    {"id": "guid-z", "error": "no_ops"},
    {"id": "guid-w", "error": "transform_failed"},
    {"id": "guid-q", "error": "exception", "message": "..."}
  ]
}
```

### Error taxonomy

Deterministic input errors raised **before** transform composition begins for
an item:

| Code | When |
|------|------|
| `invalid_id` | `id` missing, non-string, or unparseable as GUID |
| `invalid_move` | `move` present but not a 3-element numeric array |
| `invalid_scale` | `scale` present but neither a scalar nor a 3-element numeric array, OR contains a zero element |
| `invalid_mirror` | `mirror` malformed: missing `normal`/`origin`, non-3-element, OR zero-vector `normal` |
| `no_ops` | Item has `id` but no transform fields |

Lookup / execution errors:

| Code | When |
|------|------|
| `not_found` | GUID doesn't exist in `doc.Objects` |
| `not_instance` | Object exists but isn't an `InstanceObject` |
| `transform_failed` | `doc.Objects.Transform(guid, xform, true)` returned `false` |
| `exception` | Unexpected throw, fallback only |

## Implementation notes

### Shared scale parser

Extract the existing scalar/array-of-3 `scale` parsing logic from
`BlocksHandler.TransformInstance` (currently at ~line 3221) into a private
helper so both the single-target and batch methods use the same code:

```csharp
private static bool TryParseScaleOp(
    JsonElement scaleEl,
    Point3d pivot,
    out Transform scaleXform,
    out string error);
```

This is the strongest guardrail against parity drift — the most common
failure mode for batch variants is the two implementations diverging silently
over time.

### Zero-scale rejection

- **Scalar** `scale == 0` → `invalid_scale`.
- **Array** `[sx, sy, sz]` with any `== 0` element → `invalid_scale`.
- **No epsilon.** Match single-target's current behavior exactly. Introducing
  tolerance only in batch would create parity drift.

### Contract-level vs item-level failures

| Condition | Handling |
|-----------|----------|
| Body missing / unparseable JSON | Whole-request error |
| `items` missing or not array | Whole-request error |
| `redraw` present but not boolean | Whole-request error (guard consistent with PR #13 fix) |
| Per-item malformed shape | Structured per-item error, batch continues |
| Per-item lookup failure | Structured per-item error, batch continues |
| Per-item transform failure | Structured per-item error, batch continues |

### Undo

Single `UndoScope(doc, "Batch Transform Instances")` wraps the per-item loop.
Whole batch reverts as one step regardless of routed/skipped mix.

### Empty `items[]`

Return `{routed: 0, skipped: 0, total: 0}` with HTTP success. A caller sending
an empty batch is a no-op, not an error.

## Testing plan

### Static
- Native Release x64 build clean
- Companion net7.0 build clean (0 errors)
- Python MCP `py_compile` clean

### Live (in an open Rhino session, e.g. `M2-UPPER PODIUM.3dm`)

| # | Test | Expected |
|---|------|----------|
| 1 | Happy path, 3 items exercising move / rotate+scale / mirror | `routed: 3, skipped: 0, total: 3` |
| 2 | Malformed shape: `move:[1,2]` + `scale:0` + zero-vector mirror | `routed: 1, skipped: 3` with `invalid_move` / `invalid_scale` / `invalid_mirror` |
| 3 | Identity mix: no-op item + missing `id` + non-GUID `id` | `routed: 0, skipped: 3` with `no_ops` / `invalid_id` / `invalid_id` |
| 4 | Lookup: deleted GUID + Brep GUID (not an instance) | `routed: 0, skipped: 2` with `not_found` / `not_instance` |
| 5 | Duplicate GUID: same GUID twice with `move:[10,0,0]` each | `routed: 1, skipped: 1` with `not_found` on iteration 2 (original deleted after iter 1's `doc.Objects.Transform(..., deleteOriginal: true)`) |
| 6 | Empty `items[]` | `routed: 0, skipped: 0, total: 0`, success |
| 7 | Contract violation: `items: "not-an-array"` | Whole-request error |
| 8 | MCP schema defense: `"id": 123` (integer) | Rejected at MCP layer |
| 9 | Undo: any routed batch → Ctrl+Z | Single undo step reverts all routed items |
| 10 | `redraw` malformed: `"redraw": "false"` (string) | Whole-request error, not per-item skip |
| 11 | Non-uniform scale: single item `scale: [2, 1, 0.5]` | Routed success; post-state proves `[sx,sy,sz]` path works |
| 12 | Parity spot-check: same payload via `rhino_block_transform_instance` vs 1-item `_batch`, against comparable instances | Same resulting transform (architectural promise) |

### Verification tools
- `rhino_block_instances` for post-transform position readback
- Visual confirmation in Rhino viewport

### Skipped
- Chain-deferred-redraw multi-batch test (deferred on PR #13; same principle)
- 10k-item perf test (not a throughput-claim feature)

## Risks

- **ABI drift.** Managed and native ABI versions must bump together; missed bump
  bricks the bridge. Mitigation: manual check of both constants before commit.
- **Parity drift with single-target.** The shared `TryParseScaleOp` helper keeps
  companion single/batch aligned, but the LIVE single-target route is native, not
  companion. Zero-scale is now rejected by the companion helper (strict) while the
  native handler still accepts it silently. Not a public regression today because
  no HTTP route calls the companion `TransformInstance`, but the drift should be
  closed in a future migration.
- **Duplicate GUID surprise.** `doc.Objects.Transform(..., deleteOriginal: true)`
  deletes the original and returns a new GUID, so repeat-GUID items in `items[]`
  produce `not_found` on iteration 2. Documented in the MCP tool description and
  the companion method's docstring.

## Out-of-scope follow-ups

- `includePositions: true` for per-item post-transform readback.
- Extracting `move`/`rotate`/`mirror` parsers to shared helpers (do after shipping; not a blocker).
- Rerouting `/block/transform-instance` from native to companion. Would close the
  zero-scale parity drift by making single-target and batch share the same
  implementation. Scope: add managed proxy, switch route registration, delete
  native `HandleBlockTransformInstance`.
- Native transform handler uses `deleteOriginal: true` → replacement GUID pattern.
  If callers want in-place GUID preservation, a separate "update-in-place" API is
  needed; that's a different feature from this batch.
- Next roadmap items: `rhino_block_replace_object_geometry_batch`, `rhino_block_transform_object_batch`, `rhino_layer_set_properties_batch`.
