# `rhino_layer_set_properties_batch` — Design

**Date:** 2026-04-14
**Status:** Approved (brainstorm + review rounds complete)
**Roadmap entry:** `rook_docs/2026-04-13-batch-tools-roadmap.md` #8

## Goal

Add a batch variant of `rhino_layer_set_properties` that applies the same per-layer
property mutations to many layers in one call, with best-effort per-item error
semantics and a single undo scope.

## Non-goals

- No upsert / auto-create behavior. Missing target → `not_found` skip. Creation is
  handled by the separate `HandleCreateLayersBatch` route.
- No cross-item dependency resolution. Each item resolves against document state
  at its own turn; ordering is observable but not choreographed by the endpoint.
  Callers sequence or split batches if they need dependency ordering.
- No per-item `redraw` override.
- No per-item post-state readback in the default response. Callers query via
  `rhino_layers` / `rhino_layer_dependencies` if they need it.
- No perf optimizations for 500+ item batches. Layer tables rarely exceed a few
  hundred entries in practice.

## Architecture

**Route:** `POST /layers/properties-batch` — **pure native.** Follows the
`HandleCreateLayersBatch` precedent. No bridge callback, no ABI bump, no managed
companion involvement.

### Rhino-side wiring

| File | Change |
|------|--------|
| `src/RookNative/Handlers/LayerOpsHandler.cpp` | Extract per-layer mutation helper; add batch handler; refactor single-target to use helper |
| `src/RookNative/Handlers/LayerOpsHandler.h` | Declare `HandleLayerSetPropertiesBatch` only (helper stays file-local) |
| `src/RookNative/RookServer.h` | Declare class-level forwarder |
| `src/RookNative/RookServer.cpp` | Implement forwarder + register route in the layers section |

### MCP-side wiring

Parity with the single-target tool across all MCP registries — this design
intentionally closes the registry gap that PRs #12/#13/#14 left open for their
batch tools. (Backfill of those prior tools into the other three registries is a
separate followup commit, not bundled with this PR.)

| File | Change |
|------|--------|
| `mcp_server/src/rook/server.py` | Tool def + `case` handler (primary MCP exposure) |
| `mcp_server/src/rook/bootstrap/executor.py` | Add `"rhino_layer_set_properties_batch": ("POST", "/layers/properties-batch", params)` |
| `mcp_server/src/rook/agent/tool_dispatcher.py` | Add `"rhino_layer_set_properties_batch": ("/layers/properties-batch", "POST")` |
| `mcp_server/src/rook/learning/tool_schemas.py` | Add `ToolSchema` entry mirroring the single-target |

Total touch count: 8 files.

### Shared helper

The per-layer mutation logic currently lives inline in `HandleLayerSetProperties`.
Extract it into a file-local helper (anonymous namespace; not in the header) that
both endpoints call:

```cpp
struct LayerMutationResult {
    bool success;             // canonical success signal
    std::string errorCode;    // populated on failure; e.g. "not_found", "invalid_parent",
                              //                            "parent_not_found", "name_collision"
    std::string errorMessage; // human-readable detail
    nlohmann::json layerData; // populated on success; empty on failure (used by single-target)
};

LayerMutationResult ApplyLayerPropertiesMutation(
    CRhinoDoc* pDoc,
    const std::string& name,
    const nlohmann::json& setProps);
```

- **Single-target** calls the helper once; on failure re-throws /
  `CRookServer::SendError` using `errorCode`+`errorMessage`. On success returns
  `layerData` as the response.
- **Batch** calls the helper per item inside a `try/catch`. On failure, appends a
  structured entry to `errors[]` using `errorCode`+`errorMessage` and increments
  `skipped`. On success, increments `routed`.

`success` is the canonical field; `errorCode` / `errorMessage` / `layerData` are
only meaningful as described.

## Request / response contract

### Request

```json
{
  "items": [
    {"name": "A-WALL",          "set": {"color": [180, 170, 160], "material": "Concrete"}},
    {"name": "MATERIALS::STEEL", "set": {"plotWeight": 0.35, "linetype": "Dashed"}},
    {"name": "temp-scratch-1",   "set": {"rename": "SCRATCH", "parent": "WIP"}}
  ],
  "redraw": false
}
```

| Field | Required | Type | Notes |
|-------|----------|------|-------|
| `items` | yes | array | Contract violation if missing / not array |
| `items[].name` | yes | string | Layer name or full path; resolved via `ResolveLayerRef` at item's turn |
| `items[].set` | yes | object (non-null, non-empty) | Same shape as single-target. Any subset of the 11 supported properties |
| `redraw` | no | boolean | Default `true`. Guarded on `ValueKind ∈ {True, False}`; malformed → HTTP error |

**Supported `set` properties (full single-target parity):**
- *Display:* `color`, `plotColor`, `plotWeight`, `linetype`, `linetypeIndex`,
  `material`, `materialIndex`, `visible`, `locked`
- *Structural:* `rename`, `parent`

**Resolution timing:** Each item resolves `name`, `parent`, sibling collisions,
linetype, and material against the **current document state at that item's turn**.
Order is observable. Cross-item dependency choreography is not a contract
guarantee.

### Response

```json
{
  "routed": 47,
  "skipped": 3,
  "total": 50,
  "errors": [
    {"name": "A-WALL", "error": "invalid_parent", "message": "..."},
    {"name": "MATERIALS::STEEL", "error": "linetype_not_found", "message": "..."},
    {"name": "temp-scratch-1", "error": "name_collision", "rename": "SCRATCH", "message": "..."}
  ]
}
```

- `errors[].name` **always** echoes the request item's `name`. Never substituted
  with a rename target, resolved parent, or other derived value.
- Optional extras: `rename`, `parent`, `message` — populated per failure type for
  actionable diagnostics.
- No per-item `layerData` in the batch response. Callers query post-state via
  `rhino_layers` / `rhino_layer_dependencies` if needed.

This matches the **compact block-batch summary convention** (not exact field
parity with every prior batch tool — some, like `set_materials_batch`, also emit
`unresolvableMaterials` extras).

## Error taxonomy

### Contract-level (whole request → HTTP error)
- Body null/empty/unparseable JSON
- `items` missing or `ValueKind != Array`
- `redraw` present but `ValueKind ∉ {True, False}`

### Per-item shape/type errors
Payload format wrong. Caught before any lookup.

| Code | Trigger |
|------|---------|
| `invalid_name` | `name` missing, non-string, or empty |
| `invalid_set` | `set` missing, null, or not an object |
| `invalid_rename` | `rename` empty, non-string, or contains `::` |
| `invalid_parent` | `parent` not a string and not null |
| `invalid_color` | `color` not a 3-element int array 0–255 |
| `invalid_plot_color` | same for `plotColor` |
| `invalid_plot_weight` | `plotWeight` not a non-negative number |
| `invalid_linetype` | `linetype` present but non-string |
| `invalid_linetype_index` | `linetypeIndex` present but not a non-negative integer |
| `invalid_material` | `material` present but non-string |
| `invalid_material_index` | `materialIndex` present but not a non-negative integer |
| `invalid_visible` | `visible` not boolean |
| `invalid_locked` | `locked` not boolean |

### Per-item resolution errors
Payload format fine; referenced thing can't be found or applied.

| Code | Trigger |
|------|---------|
| `not_found` | `name` doesn't resolve to an existing layer |
| `parent_not_found` | `parent` references a layer that doesn't exist |
| `linetype_not_found` | `linetype` name not in linetype table |
| `material_not_found` | `material` name not in material table |
| `name_collision` | After rename/reparent, target full path already exists |
| `cycle_detected` | Reparent would create an ancestry cycle |
| `modify_failed` | **Narrow:** `m_layer_table.ModifyLayer(...)` returned false **after all validation passed** |

### Other per-item
- `no_changes` — `set` is an empty object `{}`
- `exception` — fallback for unexpected throws after validation

**Shape-vs-resolution split rationale:** callers retry differently. A shape error
means "fix the payload"; a resolution error means "the referenced resource
doesn't exist in this document." Distinct actionability.

**MCP schema defense-in-depth:** MCP schema declares types (color as integer
array, visible as boolean, etc.), so simple shape errors are caught at the MCP
boundary before reaching the handler. Handler-level `invalid_*` codes are the
authoritative validation for direct HTTP callers and for the value-lookup
failures that schemas can't catch.

## Undo semantics

Single `UndoScope(pDoc, L"Batch Set Layer Properties")` wraps the per-item loop.
Routed items revert as one Ctrl+Z step regardless of the routed/skipped mix.
Skipped items never mutated state and have nothing to revert.

## Testing plan

### Static
- Native Release x64 build clean (no companion or bridge rebuild needed)
- `python -c "import ast; ast.parse(open('mcp_server/src/rook/server.py').read())"` clean
- Grep: new tool name `rhino_layer_set_properties_batch` present in all four
  MCP registries (`server.py`, `bootstrap/executor.py`, `agent/tool_dispatcher.py`,
  `learning/tool_schemas.py`) — confirms registry parity
- Grep: new route `/layers/properties-batch` registered exactly once in
  `RookServer.cpp`
- Manual scan for paste-errors (no accidental copies of the wrong tool name
  or route string)

### Live (in a file with ≥5 layers with varied properties)

| # | Test | Expected |
|---|------|----------|
| 1 | Happy path — 3 items with different single-property ops | `routed: 3, skipped: 0, total: 3` |
| 2 | Structural op — 1 item `{rename, parent}` | `routed: 1`; layer renamed and reparented; full path reflects new parent |
| 3 | Shape errors — `color: [1,2]`, `plotWeight: "heavy"`, `visible: "yes"` | `routed: 0, skipped: 3` with `invalid_color`, `invalid_plot_weight`, `invalid_visible` |
| 4 | Resolution errors — `linetype: "ZZZ"`, `material: "ZZZ"`, `parent: "ZZZ"` | `routed: 0, skipped: 3` with `linetype_not_found`, `material_not_found`, `parent_not_found` |
| 5 | `not_found` — missing target layer name | `routed: 0, skipped: 1` with `not_found` |
| 6 | Empty `set` — `{name: "X", set: {}}` | `routed: 0, skipped: 1` with `no_changes` |
| 7 | `name_collision` + `cycle_detected` — rename to existing sibling, reparent under self-descendant | Two entries with the two codes |
| 8a | MCP surface: `items: "not-an-array"` + `redraw: "maybe"` | MCP schema catches both before native |
| 8b | Direct HTTP: same malformed payload hits native | Handler returns whole-request HTTP error |
| 9 | Empty `items: []` | `routed: 0, skipped: 0, total: 0`, success |
| 10 | Undo (manual) — Ctrl+Z after a mixed batch | Single undo step reverts all routed changes |
| 11 | Observable in-batch order — `[{rename: A→B}, {name: "B", set: {color: ...}}]` | Both succeed; item 2 sees the renamed state. Confirms per-item resolution timing. Does NOT imply dependency choreography is a contract guarantee. |
| 12 | **Mixed success** — 1 valid + 1 `not_found` + 1 `invalid_color` | `routed: 1, skipped: 2, total: 3`. Verify the valid change applied; the two failures did not affect each other or the success. |
| 13 | Parity spot-check — same payload via single-target and 1-item batch | Identical post-state; parity regression |

### Verification tools
- `rhino_layers` for post-batch state readback
- Rhino viewport visual confirmation where applicable (color, visibility)

### Deferred
- Perf at 500+ items — not a throughput-claim feature
- Chain-deferred-redraw multi-batch — same principle as prior PRs

## Risks

| Risk | Mitigation |
|------|-----------|
| Parity drift between single-target and batch | Shared `ApplyLayerPropertiesMutation` helper; single-target refactored to use it |
| MCP registry gap (new tool exposed in `server.py` only) | This design enumerates all four registries explicitly |
| Order-sensitive failures on rename+reparent batches surprise callers | Explicit non-guarantee in MCP tool description; resolution timing documented |
| `modify_failed` becoming a catch-all | Narrow semantics locked: only `ModifyLayer` returning false after full validation; everything else → `exception` |

## Out-of-scope follow-ups

- **Backfill prior batch tools** (`rhino_split_disjoint_breps`,
  `rhino_block_set_layers_batch`, `rhino_block_set_materials_batch`,
  `rhino_block_set_object_colors_batch`, `rhino_block_set_object_user_strings_batch`,
  `rhino_block_set_object_names_batch`, `rhino_block_transform_instance_batch`)
  into `executor.py` / `tool_dispatcher.py` / `tool_schemas.py`. Separate commit
  on a separate branch; do not bundle with this PR.
- Per-item `includeLayerData: true` opt-in for post-state readback (if a real
  caller surfaces the need).
- Next roadmap items: `rhino_block_replace_object_geometry_batch` (#6),
  `rhino_block_transform_object_batch` (#7).
