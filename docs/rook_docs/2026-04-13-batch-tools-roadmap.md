# Batch MCP Tools Roadmap

> Source: Codex analysis, 2026-04-13. Context: Crystal Bridges Revit cleanup
> session exposed the need for batch block-definition mutation tools when
> `rhino_block_set_layers` had to be called 3,832 times individually.

## Guiding Rules

1. Add batch variants where today's tool is single-target and users naturally run it in loops.
2. Don't add batch twins for tools that already accept `ids` or arrays and are effectively batch-capable.

## Architecture Constraints

- **Block-definition mutation batches must be companion-backed** (C# via P/Invoke).
  Native `ModifyInstanceDefinitionGeometry` crashes Rhino — confirmed 2026-04-13.
  The companion uses `doc.InstanceDefinitions.ModifyGeometry()` (managed RhinoCommon) which is safe.

- **Document-level mutation tools go native** (C++ in `src/RookNative/Handlers/`).
  Standard add/delete on the object table is a normal native pattern.

- **ABI discipline:** New companion callbacks must be appended to the end of the
  `GhBridgeRegistration` struct and the bridge version must be bumped.

## Implementation Pattern

All batch tools follow the `set_layers_batch` template:

```
Input:  {"items": [{name, ...params}], "redraw": false}
Output: {"routed": N, "skipped": N, "total": N, "errors": [...]}
```

- Single `UndoScope` for entire batch
- Pre-cache lookups (layers, materials) before iterating
- Per-item try/catch — skip failures, don't abort batch
- Deferred `Redraw()` controlled by caller
- Guard malformed array entries (`ValueKind == JsonValueKind.Object`)

---

## Priority 1 — Block Definition Mutation Batches

These are direct siblings of `rhino_block_set_layers_batch`. Same shape, same
cleanup workflows, same companion-backed path.

### 1. `rhino_block_set_materials_batch`

```json
{"items": [{"name": "Block A", "material": "Concrete"}], "redraw": false}
```

Why: Material assignment is the immediate next step after layer routing in every
Revit cleanup workflow.

### 2. `rhino_block_set_object_colors_batch`

```json
{"items": [{"name": "Block A", "color": [255, 0, 0]}], "redraw": false}
```

Why: Common standardization pass after import/convention capture.

### 3. `rhino_block_set_object_user_strings_batch`

```json
{"items": [{"name": "Block A", "userStrings": {"category": "structural"}}], "redraw": false}
```

Why: Metadata stamping across many block definitions. Useful for tagging Revit
family/type info back onto objects before exploding.

### 4. `rhino_block_set_object_names_batch`

```json
{"items": [{"name": "Block A", "objectName": "W-BEAM-01"}], "redraw": false}
```

Why: Less common than layers/materials but same implementation pattern.

### 5. `rhino_block_replace_object_geometry_batch`

```json
{"items": [{"name": "Block A", "index": 0, "sourceId": "guid"}], "redraw": false}
```

Why: Very high leverage for correction workflows, but higher risk.
Note: Needs careful validation. Should stay companion-backed.

### 6. `rhino_block_transform_object_batch`

```json
{"items": [{"name": "Block A", "indices": [0, 1], "transform": {"type": "move", "x": 10}}], "redraw": false}
```

Why: Same family, same loop pain, used in cleanup/migration scripts.

---

## Priority 2 — Instance & Layer Ops

### 7. `rhino_block_transform_instance_batch`

Current tool is single-instance. This is the biggest non-covered instance op.

```json
{"items": [{"id": "guid", "move": [10, 0, 0]}], "redraw": false}
```

### 8. `rhino_block_replace_instance_batch`

Useful for mass swaps (e.g., `RAILING WEST 2 -> RAILING WEST`).

```json
{"items": [{"instanceId": "guid", "newBlockName": "RAILING WEST"}], "redraw": false}
```

### 9. `rhino_block_reset_scale_batch`

Small tool, often needed on many imported instances. Could be a vectorized
upgrade of the existing single-instance tool instead of a separate endpoint.

```json
{"ids": ["guid1", "guid2", ...]}
```

### 10. `rhino_layer_set_properties_batch`

Natural companion to `rhino_layer_create_batch`.

```json
{"items": [{"name": "A-WALL", "set": {"color": [180, 170, 160], "material": "Concrete"}}]}
```

### 11. `rhino_block_set_layers_by_pattern`

Not a generic batch twin but probably more useful than some generic twins.
Convention-driven cleanup tool.

```json
{"matches": [{"namePattern": "System Panel*", "layer": "01-ARCHITECTURE::A-GLASS"}]}
```

---

## Already Batch-Capable (No New Tools Needed)

| Tool | Why |
|------|-----|
| `rhino_transform`, `rhino_delete`, `rhino_copy`, `rhino_select` | Accept `ids` array |
| UV mapping tools | Accept `ids` array |
| `rhino_block_set_instance_properties` | Accepts `id` or `ids` |
| `rhino_block_set_instance_visibility` | Accepts `id` or `ids` |
| `rhino_material_ops assign` | Accepts `ids` array |
| `rhino_tag_object_semantic` | Accepts `ids` array |
| `gh_edit` | Already the batch primitive for GH canvas |

---

## Shipped

| Tool | Path | Date |
|------|------|------|
| `rhino_split_disjoint_breps` | Native C++ | 2026-04-14 (PR #12) |
| `rhino_block_set_layers_batch` | Companion-backed, ABI v8 | 2026-04-14 (PR #13) |
| `rhino_block_set_materials_batch` | Companion-backed, ABI v9 | 2026-04-14 (PR #13) |
| `rhino_block_set_object_colors_batch` | Companion-backed, ABI v9 | 2026-04-14 (PR #13) |
| `rhino_block_set_object_user_strings_batch` | Companion-backed, ABI v9 | 2026-04-14 (PR #13) |
| `rhino_block_set_object_names_batch` | Companion-backed, ABI v9 | 2026-04-14 (PR #13) |
| `rhino_block_transform_instance_batch` | Companion-backed, ABI v10 | 2026-04-14 (PR #14) |
| `rhino_layer_set_properties_batch` | Native | 2026-04-14 (PR #15) |
| `rhino_block_replace_object_geometry_batch` | Companion-backed, ABI v11 | 2026-04-14 (PR #21) |
| `rhino_block_transform_object_batch` | Companion-backed, ABI v12 | 2026-04-14 (PR #22) |

---

## Recommended Build Order

1. ~~`rhino_block_set_materials_batch`~~ — shipped (PR #13)
2. ~~`rhino_block_set_object_colors_batch`~~ — shipped (PR #13)
3. ~~`rhino_block_set_object_user_strings_batch`~~ — shipped (PR #13)
4. ~~`rhino_block_set_object_names_batch`~~ — shipped (PR #13)
5. ~~`rhino_block_transform_instance_batch`~~ — shipped (PR #14)
6. ~~`rhino_block_replace_object_geometry_batch`~~ — shipped (PR #21)
7. ~~`rhino_block_transform_object_batch`~~ — shipped (PR #22)
8. ~~`rhino_layer_set_properties_batch`~~ — shipped
