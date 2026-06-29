# Exact-ID Object Hygiene Tools Design

Date: 2026-06-29

Branch: `codex/director-prepare-take`

Status: Approved design, pending implementation plan

## Context

The Director prepare-take work exposed a small set of missing hygiene tools during live planning against:

`H:\AI EXPERIMENTS\Pearson\ANIMATION\Axon_Pearson_Experimental_TESTING.3dm`

The current model planning workflow depends on exact object identity. Rhino selection is the human interface, while project-local Director ledgers and sidecars are the audit interface. During the planning session, two stray point objects needed to be excluded from animation and hidden, but Rook did not expose a safe generic exact-ID object visibility tool. Existing layer visibility was too broad, and raw `_Hide` was correctly refused by the command safety gate.

This interlude adds three small exact-ID primitives before any Director materialization work:

- exact-ID object visibility
- exact-ID object layer assignment
- exact-ID batch object user-text stamping

Director planning wrappers and `rhino_director_materialize_take` are intentionally deferred.

## Goals

1. Provide explicit, boring, exact-ID mutating tools for planning hygiene.
2. Avoid selector ambiguity: no layer/name/type/bbox selectors in these tools.
3. Keep source-model mutations narrow and auditable.
4. Preserve Rook's existing native handler patterns, MCP schemas, targeting policy, and agent dispatchability rules.
5. Make live validation straightforward by returning per-object post-state for requested IDs only.

## Non-Goals

- No Director materialization, block decomposition, or actor creation.
- No Director planning wrapper tools in this pass.
- No auto-create behavior for missing layers.
- No selector support beyond exact document object IDs.
- No mixed set/delete semantics for user text batch stamping.
- No new native handler `.cpp` or `.h` files requiring `.vcxproj` or `.filters` edits.
- No readonly exposure.

## Existing Tooling Check

Before implementation, verify the existing tree again, but the current design is based on this observed state:

- Generic exact-ID object visibility is not exposed.
- Exact-ID layer reassignment is not exposed; `rhino_layer_move_objects` moves all objects from a source layer to a target layer.
- Single-object user text set/delete/get exists under `/usertext/object-*`.
- There is no implemented `/usertext/object-set-batch` route, although at least one source test references that route as a forbidden mutation surface for BIM projection code.
- Block instance visibility exists, but it only targets instance references and is not a generic document-object route.

If implementation discovers an existing exact-ID primitive that fully satisfies one of these contracts, prefer exposing or tightening that primitive instead of duplicating behavior.

## Tool Contracts

### `rhino_object_visibility`

Native route: `POST /objects/visibility`

MCP tool: `rhino_object_visibility`

Request:

```json
{
  "object_ids": ["uuid", "uuid"],
  "visible": false,
  "redraw": true
}
```

Rules:

- `object_ids` is required, must be a non-empty array of valid UUID strings.
- `object_ids` is capped at 500 entries to bound main-thread work and response size.
- Duplicate object IDs are rejected.
- Every ID must resolve to an existing active document object before mutation starts.
- `visible` is required and must be boolean.
- `redraw` is optional and defaults to `true`.
- This sets object-level visibility only.
- If the object's layer is hidden, `visible: true` may not make the object effectively visible.
- `effectivelyVisible` is optional/null unless Rhino exposes a reliable value directly. Do not synthesize a misleading value.

Success response:

```json
{
  "requestedCount": 2,
  "modifiedCount": 1,
  "skippedCount": 1,
  "visible": false,
  "results": [
    {
      "id": "uuid",
      "status": "modified",
      "before": {
        "objectVisible": true,
        "layerVisible": true,
        "effectivelyVisible": true
      },
      "after": {
        "objectVisible": false,
        "layerVisible": true,
        "effectivelyVisible": false
      }
    },
    {
      "id": "uuid",
      "status": "unchanged",
      "before": {
        "objectVisible": false,
        "layerVisible": true,
        "effectivelyVisible": false
      },
      "after": {
        "objectVisible": false,
        "layerVisible": true,
        "effectivelyVisible": false
      }
    }
  ]
}
```

Implementation rule: first verify the exact Rhino SDK call for object-level visibility from in-repo usage. Use `ModifyObjectAttributes` only if the current SDK exposes a clean object attribute visibility setter. If not, use the existing `HideObject` / `ShowObject` pattern from block instance visibility and document the behavioral difference in code comments and tests.

### `rhino_object_set_layer`

Native route: `POST /objects/set-layer`

MCP tool: `rhino_object_set_layer`

Request:

```json
{
  "object_ids": ["uuid", "uuid"],
  "layer": "Layer::Path",
  "redraw": true
}
```

Rules:

- `object_ids` is required, must be a non-empty array of valid UUID strings.
- `object_ids` is capped at 500 entries to bound main-thread work and response size.
- Duplicate object IDs are rejected.
- Every ID must resolve to an existing active document object before mutation starts.
- `layer` is required and must resolve to an existing layer.
- Missing layer is an error.
- No auto-create behavior.
- Prefer full layer paths in docs and tests.
- Layer resolution follows existing layer APIs. Ambiguous short names must fail instead of picking an arbitrary layer.
- `redraw` is optional and defaults to `true`.

Success response:

```json
{
  "requestedCount": 2,
  "modifiedCount": 1,
  "skippedCount": 1,
  "layer": {
    "input": "Layer::Path",
    "index": 42,
    "id": "uuid",
    "path": "Layer::Path"
  },
  "results": [
    {
      "id": "uuid",
      "status": "modified",
      "before": {
        "layerIndex": 7,
        "layerPath": "Old::Layer"
      },
      "after": {
        "layerIndex": 42,
        "layerPath": "Layer::Path"
      }
    }
  ]
}
```

Implementation rule: use the existing layer resolution behavior as the base. If short-name ambiguity cannot be reliably detected, make tests and docs prefer full paths and fail any input that cannot be resolved to exactly one layer.

### `rhino_object_usertext_set_batch`

Native route: `POST /usertext/object-set-batch`

MCP tool: `rhino_object_usertext_set_batch`

Request:

```json
{
  "items": [
    {
      "id": "uuid",
      "userStrings": {
        "RookDirector::Intent": "static_context",
        "RookDirector::ReviewState": "accepted"
      }
    }
  ],
  "redraw": true
}
```

Rules:

- `items` is required and must be a non-empty array.
- `items` is capped at 500 entries to bound main-thread work and response size.
- One item per object ID.
- Duplicate item IDs are rejected.
- Every item ID must be a valid UUID and must resolve to an existing active document object before mutation starts.
- `userStrings` is required per item and must be an object.
- User text keys must be non-empty strings.
- User text values must be non-empty strings.
- Empty-string values are rejected; deletion remains on the existing object delete route.
- Non-string values are rejected.
- Overwrite is allowed.
- Empty `userStrings: {}` is allowed as a per-object no-op to match `/usertext/object-set`; it returns post-state and does not count as modified.
- JSON duplicate keys are not promised to be detected because normal parsing may collapse them before route validation. The enforceable contract is one parsed key/value entry per key.
- Response is bounded to requested objects only.
- Each result intentionally returns the full post-mutation `userStrings` map for that requested object, rather than a `before`/`after` diff, to match the existing single-object `/usertext/object-set` route.

Success response:

```json
{
  "requestedCount": 2,
  "modifiedCount": 1,
  "skippedCount": 1,
  "results": [
    {
      "id": "uuid",
      "status": "modified",
      "userStrings": {
        "RookDirector::Intent": "static_context"
      }
    },
    {
      "id": "uuid",
      "status": "unchanged",
      "userStrings": {
        "RookDirector::Intent": "static_context"
      }
    }
  ]
}
```

## Error And Mutation Semantics

All three routes use the same high-level contract.

Preflight:

- Validate the whole request before opening mutation logic.
- Malformed input returns a structured typed error and performs no mutation.
- Missing/deleted IDs are preflight failures.
- Duplicate IDs are preflight failures.
- Missing or ambiguous layer is a preflight failure for layer assignment.

Mutation:

- Mutations run on the Rhino main thread.
- Mutations run under one undo record per request.
- Success returns only per-object `modified` or `unchanged` statuses.
- `unchanged` increments `skippedCount`.
- No best-effort partial-success mode in this pass.

Runtime mutation failure:

- Do not imply a clean rollback unless implementation actually guarantees one.
- If a mutation failure occurs after mutation starts, the handler should attempt internal restoration only if a reliable local pattern exists.
- Otherwise return `operation_failed` with:
  - `id`
  - `operation`
  - `message`
  - `dirty_partial_state: true`
- This marks that the all-or-nothing contract may have been breached and callers should inspect or undo manually.

Structured error codes should follow nearby handler conventions while remaining specific enough for tests:

- `invalid_input`
- `invalid_object_id`
- `duplicate_object_id`
- `not_found`
- `missing_layer`
- `ambiguous_layer`
- `operation_failed`

If existing route-local code prefers fewer error codes, the implementation may map validation failures to `invalid_input` with a precise `errorMessage`, but tests must still assert clear, stable failure meaning.

## Native Placement

Avoid native project-file churn in this interlude.

- Put `rhino_object_visibility` and `rhino_object_set_layer` handlers in existing `src/RookNative/Handlers/ObjectsHandler.cpp`.
- Add declarations in the existing object handler header if the server delegates through `Rook::Handlers`.
- Put `/usertext/object-set-batch` in existing `src/RookNative/Handlers/UserTextHandler.cpp`.
- Add declarations in `src/RookNative/Handlers/UserTextHandler.h`.
- Register routes in `src/RookNative/RookServer.cpp`.
- Add server declarations in `src/RookNative/RookServer.h` only where required by existing server routing style.
- Do not add new `.cpp` or `.h` files.
- Do not modify `.vcxproj` or `.vcxproj.filters`.

## MCP And Agent Surface

Expose all three tools through the normal MCP and agent paths.

- Add clean schemas to `mcp_server/src/rook/server.py`.
- Add bridge route mappings to `mcp_server/src/rook/agent/tool_dispatcher.py`.
- Add bootstrap executor mappings if required by existing tool coverage.
- Add explorer/registry entries if required by current metadata patterns.
- Mark tools as Rhino mutating in `mcp_server/src/rook/targeting.py`.
- Add them to appropriate mutating object/usertext tool groups only.
- Keep them out of readonly groups.
- Make bridge dispatchability a hard test.

Tool schemas must be exact and intentionally narrow:

- no selector fields
- no layer/name/type/bbox filters
- no auto-create toggles
- no delete semantics
- no fallback layer behavior

## Testing Plan

### Static And Source Tests

Add tests that verify:

- native route registration exists
- native handler declarations exist in existing headers
- MCP schemas exist and contain only exact fields
- bridge routes exist in `ToolDispatcher`
- targeting policy marks all three as Rhino mutating
- tools are not exposed in readonly groups
- dispatchability checks pass for any agent-visible group including these tools

### Python Contract Tests

Cover:

- empty `object_ids`
- malformed UUIDs
- duplicate IDs
- duplicate batch item IDs
- missing layer
- ambiguous layer if existing layer resolution can create that condition
- non-boolean visibility
- empty user text keys
- empty user text values
- non-string user text values
- overwrite semantics
- empty `userStrings: {}` no-op semantics

### Live Rhino Tests

Cover:

- visibility changes exactly requested IDs and not selection/layer neighbors
- visibility `true` on a hidden-layer object reports object-level state and leaves effective visibility null or accurate, not synthesized
- layer assignment changes exactly requested IDs and returns resolved layer index/id/path
- missing layer rejects before mutation
- usertext batch writes multiple keys per requested object
- usertext batch overwrites requested keys and preserves unrelated keys
- usertext batch changes exactly requested IDs and not layer neighbors
- unchanged values return `status: "unchanged"` and increment `skippedCount`

## Validation Bar

Before claiming this interlude complete:

- Focused Python/static test suite passes.
- Native build succeeds with the Rhino/MFC toolchain.
- Local deploy succeeds.
- Live Rhino tests pass against a disposable document.
- At least one live smoke validates the original motivating use case: exact-ID hiding or usertext tagging of the two stray planning point objects, without broad layer mutation.

## Deferred Work

- `rhino_director_capture_selection_intent`
- `rhino_director_capture_next_model_chunk`
- `rhino_director_materialize_take`
- exact-ID object usertext delete batch
- generic object attribute mega-tool
- selector-based convenience wrappers
