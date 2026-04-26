# `rhino_block_replace_instance_batch` — Design

**Date:** 2026-04-14
**Status:** Approved (brainstorm complete)
**Author:** Codex
**Roadmap entry:** `rook_docs/2026-04-13-batch-tools-roadmap.md` #8
**Pattern siblings:** `2026-04-14-transform-instance-batch-design.md` (best-effort instance batch envelope, duplicate-GUID caveat), native single-target `/block/replace-instance`

## Goal

Add a batch variant of `rhino_block_replace_instance` for mass instance-definition
swaps such as `RAILING WEST 2 -> RAILING WEST`, under one undo scope, with
best-effort per-item error handling and a compact summary response.

## Non-goals

- No transform compensation. If the target definition has a different insertion
  point or scale convention, callers handle that with a later
  `rhino_block_transform_instance_batch`.
- No per-success payload beyond summary counts. Callers query follow-up state
  via `rhino_block_instances` if they need new GUIDs or post-swap inspection.
- No automatic aliasing of `instanceId` to `id` in the batch contract. Batch
  tools use `id` consistently.
- No companion bridge work unless the public architecture boundary changes.

## Architecture

**Route:** `POST /block/replace-instance-batch`, native-owned in
`src/RookNative/Handlers/BlocksHandler.cpp`.

Reasoning:

1. `replace-instance` is public-native today. The canonical live route in
   `RookServer.cpp` points at `HandleBlockReplaceInstance`, not the companion.
2. `docs/CURRENT_ARCHITECTURE.md` says only a narrow set of block-definition
   mutation exceptions remain companion-backed. Instance replacement is not on
   that list.
3. Native already has the exact replacement mechanics we want to batch:
   resolve instance, capture attrs/xform, delete old object, create new
   instance, return the replacement GUID.
4. A companion batch would create a second public engine for a native-owned
   operation and add ABI churn with no correctness or performance benefit.

### Wiring

| Layer | Change |
|-------|--------|
| Native handler (`src/RookNative/Handlers/BlocksHandler.{h,cpp}`) | New `HandleBlockReplaceInstanceBatch` |
| Native server (`src/RookNative/RookServer.{h,cpp}`) | New forwarder + route registration |
| MCP (`mcp_server/src/rook/server.py`) | Tool definition + dispatcher case |
| Direct agent dispatcher (`mcp_server/src/rook/agent/tool_dispatcher.py`) | Route mapping |
| Tool grouping (`mcp_server/src/rook/agent/tool_groups.py`) | Add `rhino_block_replace_instance_batch`; also backfill missing `rhino_block_transform_instance_batch` |
| Learning fallback (`mcp_server/src/rook/learning/agent.py`) | Tool list + route map |
| Explorer registry (`mcp_server/src/rook/explorer/registry.py`) | `CATEGORY_MODIFICATION` entry |
| Explorer executor (`mcp_server/src/rook/explorer/executor.py`) | Endpoint mapping |
| Intent runtime (`mcp_server/src/rook/learning/intent_runtime.py`) | `RouteSpec` entry + allowed-op list |

**No bridge / ABI changes.** This route stays fully native.

## Request / response contract

### Request

```json
{
  "items": [
    {"id": "guid-a", "newBlockName": "RAILING WEST"},
    {"id": "guid-b", "newBlockName": "RAILING EAST"}
  ],
  "redraw": false
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `items` | yes | array | Whole-request error if missing or not an array |
| `items[].id` | yes | string (GUID) | Target block-instance GUID |
| `items[].newBlockName` | yes | string | Target block definition name |
| `redraw` | no | boolean | Default `true`; wrong type is a whole-request error |

### Response

```json
{
  "routed": 47,
  "skipped": 3,
  "total": 50,
  "errors": [
    {"id": "bad-guid", "error": "invalid_id"},
    {"id": "guid-x", "error": "already_target"},
    {"id": "guid-y", "error": "block_not_found"},
    {"id": "guid-z", "error": "replace_failed", "restored": true}
  ]
}
```

- `errors[].id` echoes the request's raw `id` value when present; if the item is
  not an object or `id` is absent, it is `null`.
- `replace_failed` records include `restored: true|false` so callers can tell
  whether the handler recreated the original instance after the failed swap.
- Empty `items[]` is a successful no-op:
  `{ "routed": 0, "skipped": 0, "total": 0, "errors": [] }`.

## Processing semantics

Whole-request guards:

- Request body required
- Body must contain `items` array
- `redraw`, if present, must be boolean

Per-item flow, in request order:

1. Validate item object shape.
2. Parse `id`.
3. Validate `newBlockName`.
4. Resolve the current object by GUID.
5. Confirm the object is an instance.
6. Resolve target block definition by name, using a per-batch cache of
   `newBlockName -> definition index` to avoid repeated lookups.
7. If the instance already points at that definition, skip with
   `already_target`.
8. Replace natively using the same mechanics as the public single-target route:
   capture current transform and attributes, delete old instance, create new
   instance of the target definition. If target creation fails, immediately try
   to recreate the original instance before recording `replace_failed`; undo
   remains the final recovery path if restoration also fails.

Single `UndoScope(doc, "Batch Replace Block Instances")` wraps the loop.

### Duplicate-GUID behavior

Native replace deletes the old instance and creates a replacement with a new
GUID. Therefore if the same input GUID appears twice in `items[]`, iteration 2
normally resolves `not_found`. This is the same lifecycle exposed by the public
single-target native route today.

## Error taxonomy

| Code | When |
|------|------|
| `invalid_item` | Item is not a JSON object |
| `invalid_id` | Item missing `id`, `id` non-string, or GUID parse fails |
| `missing_new_block_name` | `newBlockName` missing, non-string, or empty |
| `not_found` | GUID does not resolve in the document |
| `not_instance` | Resolved object is not a `CRhinoInstanceObject` |
| `block_not_found` | Target definition name cannot be resolved |
| `already_target` | Instance already references the requested definition |
| `replace_failed` | Replacement creation failed; error includes `restored: true|false` to distinguish immediate restore from undo-required recovery |
| `exception` | Unexpected throw; fallback only |

## Implementation notes

### Field name decision

Use `id`, not `instanceId`.

Rationale:

- Every recent batch tool uses `id` for the target object in `items[]`.
- `transform-instance-batch` already established that instance batches should
  follow the batch-family shape, not the single-target outlier shape.
- The single-target `rhino_block_replace_instance` keeps `instanceId` for
  backward compatibility; the batch variant does not need to inherit that
  inconsistency.

### Cached target-definition lookup

Many cleanup batches map many instances to the same target definition. Cache
`newBlockName -> int` inside the main-thread loop. Cache misses that resolve to
`-1` should also be stored so repeated bad names do not re-scan the definition
table.

### Same-definition no-op policy

Skip with `already_target`, not routed success.

Reasoning:

- Matches the explicit no-op visibility from `transform-instance-batch`'s
  `no_ops` pattern.
- Makes it easy for cleanup callers to distinguish "changed state" from
  "already clean".

## Risks

| Risk | Mitigation |
|------|-----------|
| Boundary drift toward companion for a native-owned route | Keep the whole feature native; no ABI changes |
| GUID lifecycle surprises for duplicate entries | Documented explicitly in tool description and design doc |
| Same target lookup repeated many times | Per-batch name cache |
| Contract drift between public single-target and batch replace engine | Reuse the native replacement mechanics already shipping publicly |

## Testing plan

### Static

- Native build-style sanity by code inspection / grep (no ABI changes expected)
- Python `py_compile` for touched MCP files
- Route grep: `/block/replace-instance-batch` appears in native registration and
  MCP/dispatcher surfaces only where expected

### Live

| # | Test | Expected |
|---|------|----------|
| 1 | Happy path: several instance swaps to one existing target definition | `routed = N`, `skipped = 0` |
| 2 | Mixed lookup failures: bad GUID, deleted GUID, non-instance GUID | `invalid_id`, `not_found`, `not_instance` |
| 3 | Missing target name, empty target name | `missing_new_block_name` |
| 4 | Target definition missing | `block_not_found` |
| 5 | Already on target definition | `already_target` |
| 6 | Duplicate same GUID twice | First routed, second `not_found` |
| 7 | Empty `items[]` | Success with all zero counts |
| 8 | Undo after mixed successful batch | Single undo step reverts all routed swaps |
| 9 | `redraw: "false"` | Whole-request error |
| 10 | Provoked replacement-create failure | `replace_failed` with `restored: true` or `restored: false`; if false, undo recovers |

## Out-of-scope follow-ups

- Optional `includeReplacements: true` success payload returning old/new GUID
  pairs.
- A future compatibility alias `instanceId` inside batch items if a real caller
  surfaces migration pain. Not needed at initial ship.
- Roadmap item #9 `rhino_block_reset_scale_batch`.
