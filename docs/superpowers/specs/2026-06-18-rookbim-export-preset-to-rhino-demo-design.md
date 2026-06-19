# RookBIM Export Preset To Rhino Demo Workflow - design

> Status (2026-06-18): DESIGN - ready for review before implementation planning.
> Branch: `feature/rookbim-export-preset-to-rhino-demo`.
> Base: `origin/main` at PR #273 merge (`940c5ba1`).

## 1. Goal

Create a demo-grade but forward-compatible one-shot RookBIM workflow tool that exports a Revit
preset bundle, imports the generated `.3dm` into the current Rhino/Rhino.Inside document, projects
the matching BIM sidecar into the Python scene graph, and optionally returns a compact BIM facts
relationship summary.

The long-term product shape should likely fold this into `rookbim_export_preset` as delivery/import
options. For today's in-house demo, the lowest-risk path is a thin Python/MCP orchestration wrapper
that reuses existing surfaces and does not change native or RookBIM export internals.

## 2. In scope

- New MCP workflow tool: `rookbim_export_preset_to_rhino`.
- Python/MCP orchestration only.
- Reuse existing routes/tools:
  - `/bim/export-preset`
  - `/import`
  - `scene_project_bim_relationships`
  - optional `scene_bim_facts(mode="relationship_scan")`
- Preserve existing `rookbim_export_preset` behavior and schema.
- Auto-generate an output bundle location when `output` is omitted.
- Return separate export, path, import, projection, and optional BIM facts blocks.
- Focused tests for schema, dispatch order, projection scoping, targeting, and tool groups.
- Optional live smoke if RIR/RookNative is discoverable.

## 3. Out of scope

- C++ native changes.
- C# RookBIM export changes.
- New Revit API behavior.
- Changing `rookbim_export_preset`.
- Revit write-back.
- Geometry inference, containment threshold tuning, or calibration.
- Generic bundle-import tool beyond what this wrapper needs.

## 4. API shape

```text
rookbim_export_preset_to_rhino(
  preset: string,
  output?: {
    directory: string,
    name: string,
    units?: "meters" | "millimeters" | "centimeters" | "feet" | "inches",
    overwrite?: boolean
  },
  scope?: "active_view" | "document",
  includeCategories?: string[],
  excludeCategories?: string[],
  layerPolicy?: "flat" | "by_category" | "by_level_then_category",
  namePolicy?: "none" | "revit_name" | "type_only" | "readable" | "readable_with_id",
  metadataProfile?: "minimal" | "standard" | "full",
  rooms?: "both" | "labels_only" | "exclude",
  limitPerCategory?: integer,
  allowTruncated?: boolean,
  allowBboxProxy?: boolean,
  projectRelationships?: boolean = true,
  includeRooms?: boolean = true,
  includeLevels?: boolean = true,
  relationshipSummary?: boolean = true,
  relationshipSampleLimit?: integer = 20,
  targetLayer?: string,
  port?: integer
)
```

Use the existing `rookbim_export_preset` camelCase naming style for forwarded export parameters.
Do not add snake_case aliases in v1.

### Output default

`output` is optional. If omitted, generate the existing export contract fields exactly as:

```text
output.directory = %TEMP%/rookbim-export-to-rhino
output.name = <safe-preset>-YYYYMMDD-HHMMSS
```

`<safe-preset>` should be derived from the preset name by keeping filesystem-safe characters and
falling back to `rookbim` if the result is empty.

### targetLayer

`targetLayer` is advanced and discouraged for v1. The exported `.3dm` already contains useful
`RookBim > Level > Category` layer organization. Passing `targetLayer` to `/import` can flatten or
override that organization depending on import behavior. The happy path should omit `targetLayer`.
If the field is exposed, the schema description must warn that it may destroy exported BIM layer
organization.

## 5. Tool flow

1. Build the export request from the wrapper input.
2. If `output` is omitted, create the default temp output shape.
3. Call `/bim/export-preset` with the export request and selected `port`.
4. Resolve artifact paths. Prefer authoritative paths returned by `/bim/export-preset` whenever the
   response provides them. Derive from the effective `output.directory` and `output.name` only as a
   fallback:
   - `<output.directory>/<output.name>.3dm`
   - `<output.directory>/<output.name>.sidecar.json`
   - `<output.directory>/<output.name>.validation.json`
5. Call `/import` with `{path: model3dm}` and `targetLayer` only when explicitly provided.
6. Extract imported object ids from the import response.
7. If `projectRelationships=true`:
   - require non-empty imported ids;
   - call `scene_project_bim_relationships(sidecar_path, object_ids=importedIds, include_rooms=includeRooms, include_levels=includeLevels, port=port)`.
8. If `relationshipSummary=true` and projection succeeded:
   - call `scene_bim_facts(mode="relationship_scan", sample_limit=relationshipSampleLimit)`.
   - Treat the returned `bimFacts` block as a scene-wide post-projection summary for v1.
     `relationship_scan` does not currently filter by `object_ids`, so the summary may include prior
     BIM projections already present in the Python scene graph.
9. Return a structured result.

Projection must be scoped to imported ids. If import succeeds but returns no imported ids, skip or
fail projection clearly rather than projecting over the whole scene.

For demo-accurate `bimFacts` counts, the live smoke should start from a clean or isolated Rhino/RIR
document. The import and projection stages remain scoped to `importedIds`; only the optional facts
summary is scene-wide in v1.

## 6. Response shape

```json
{
  "success": true,
  "workflow": "rookbim_export_preset_to_rhino",
  "export": {
    "request": {},
    "response": {}
  },
  "paths": {
    "bundleDirectory": "C:/...",
    "model3dm": "C:/.../openings.3dm",
    "sidecar": "C:/.../openings.sidecar.json",
    "validation": "C:/.../openings.validation.json"
  },
  "import": {
    "response": {},
    "importedObjectCount": 60,
    "importedIds": []
  },
  "projection": {},
  "bimFacts": {},
  "warnings": []
}
```

`success=true` only when every requested stage succeeds. If a later requested stage fails after an
earlier stage succeeds, return `success=false`, `partialSuccess=true`, the completed stage blocks,
and a stage-specific `error`/`message`. Examples:

- export fails: no import/projection/facts attempted, `stage="export"`;
- import fails: export/path blocks returned, `stage="import"`;
- import returns no object ids while `projectRelationships=true`: export/import blocks returned,
  `stage="projection"`, projection skipped, no whole-scene fallback;
- projection fails: export/import blocks returned, `stage="projection"`;
- relationship scan fails while `relationshipSummary=true`: export/import/projection blocks
  returned, `stage="bimFacts"`.

Warnings are for non-fatal diagnostics only; they must not turn a failed requested stage into
`success=true`.

## 7. Registration and targeting

- Register in MCP `server.py` schema and dispatch.
- Add local dispatcher support only if it can reuse the same orchestration helper without duplicating
  request logic.
- Add to `TOOL_GROUPS["rookbim"]`.
- Do not add to `rookbim_readonly`.
- Targeting policy should be `requires_rhino=True`, `risk="mutate"` because the workflow writes
  bundle files and imports geometry into the current Rhino/RIR document.

## 8. Test plan

Focused pytest coverage:

- Schema includes export preset fields, optional `output`, and workflow flags.
- Existing `rookbim_export_preset` schema and behavior remain unchanged.
- Generated output maps to `%TEMP%/rookbim-export-to-rhino` plus
  `<safe-preset>-YYYYMMDD-HHMMSS`.
- Artifact path resolution prefers export response paths and derives from effective output only as a
  fallback.
- Targeting derives mutate policy.
- Tool group includes wrapper in `rookbim`, not `rookbim_readonly`.
- Server dispatch calls export, import, projection, and optional facts in order.
- Generated output is used when `output` is omitted.
- Import receives no `targetLayer` by default.
- Projection receives `object_ids=importedIds`.
- Import success with no imported ids returns a clear projection diagnostic and does not project
  across the whole scene.
- `relationshipSummary=false` skips `scene_bim_facts`.
- `relationshipSummary=true` records that `bimFacts` is a scene-wide relationship scan, not an
  imported-object-scoped scan.
- Later requested-stage failures return `success=false`, `partialSuccess=true`, and completed stage
  blocks.

Optional live smoke if RIR/RookNative is available:

1. Start from a clean or isolated Rhino/RIR document when validating `bimFacts` counts.
2. Call `rookbim_export_preset_to_rhino` with `preset="openings_and_hosts"`,
   `scope="active_view"`, `limitPerCategory=10`, `allowTruncated=true`, and
   `allowBboxProxy=true`.
3. Confirm the bundle is written.
4. Confirm `.3dm` imports into the current Rhino/RIR document.
5. Confirm imported objects preserve Revit user strings.
6. Confirm relationship projection joins imported ids.
7. Confirm `scene_bim_facts` and `scene_context(sync=false)` can reason over the imported objects.

## 9. Later canonicalization

After the demo, fold the workflow into a cleaner product API:

- add delivery/import options directly to `rookbim_export_preset`; or
- split the reusable import/project part into `rookbim_import_bundle_to_rhino`;
- keep the same response blocks so callers can migrate without losing diagnostics.
