# Crystal Bridges Visualization Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the active Crystal Bridges Revit-export Rhino file into an AIA parent/child visualization layer structure while preserving source provenance as queryable user metadata.

**Architecture:** Use existing Rook MCP tools and native HTTP routes. The workflow is audit-first: collect live Rhino state, classify by weighted signals, write review artifacts, get approval, then mutate layers/block-definition object layers with provenance and manifest safeguards.

**Tech Stack:** Rhino 8, RookNative HTTP routes, Rook MCP tools, PowerShell for local JSON artifact aggregation, Rhino user strings for durable metadata.

---

## Target File

Active Rhino file:

```text
H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\0_REVIT EXPORT_ALL_BACKUP-02.3dm
```

Cleanup artifact directory:

```text
H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup
```

Design spec:

```text
C:\Users\aryan\source\repos\Rook\docs\superpowers\specs\2026-05-11-crystal-bridges-visualization-cleanup-design.md
```

## File Responsibilities

- `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\conventions.yaml`: project-specific target layer taxonomy and cleanup policy for this Rhino file.
- Timestamped inventory JSON under `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup`: raw read-only inventory from Rook/Rhino.
- Timestamped classification audit JSON under `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup`: proposed object/block-object classification records.
- Timestamped cleanup report markdown under `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup`: human-readable review report.
- Rhino document user strings under `RookCleanup::*`: manifest and run state.
- Rhino object and block-definition user strings under `RookCleanup::*`: provenance, classification, and review evidence.

## Task 1: Preflight And Backup

**Files:**
- No repo file changes.
- Rhino file backup path generated in Step 4 and reused for the manifest.

- [ ] **Step 1: Confirm Rhino is reachable**

Call:

```json
{"tool":"rhino_ping","params":{}}
```

Expected: `"pong"`.

- [ ] **Step 2: Confirm the active document**

Call:

```json
{"tool":"rhino_document","params":{}}
```

Expected values:

```json
{
  "name": "0_REVIT EXPORT_ALL_BACKUP-02.3dm",
  "path": "H:\\AI EXPERIMENTS\\CRYSTAL_BRIDGES\\0_REVIT EXPORT_ALL_BACKUP-02.3dm",
  "units": "inches"
}
```

If a different document is active, stop and ask which file should be cleaned.

- [ ] **Step 3: Create the artifact directory**

Run:

```powershell
New-Item -ItemType Directory -Force -Path "H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup"
```

Expected: directory exists.

- [ ] **Step 4: Save a Rhino backup through the document route**

Set the backup path:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backupPath = "H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\0_REVIT EXPORT_ALL_BACKUP-02_ROOK_BACKUP_$stamp.3dm"
```

Call `rhino_document_ops` with:

```json
{"action":"save","path":"value of $backupPath"}
```

Expected: save succeeds. This captures current in-memory Rhino state, including unsaved modifications.

- [ ] **Step 5: Save back to the original path**

Call:

```json
{
  "tool": "rhino_document_ops",
  "params": {
    "action": "save",
    "path": "H:\\AI EXPERIMENTS\\CRYSTAL_BRIDGES\\0_REVIT EXPORT_ALL_BACKUP-02.3dm"
  }
}
```

Expected: save succeeds and the active working file remains the original path.

- [ ] **Step 6: Commit checkpoint**

No git commit is required for Rhino-only backup work. Record the backup path in the cleanup report and later in `RookCleanup::BackupPath`.

## Task 2: Create The Cleanup Convention File

**Files:**
- Create: `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\conventions.yaml`

- [ ] **Step 1: Write the convention file**

Create this exact YAML file:

```yaml
schema_version: 1
name: "Crystal Bridges Visualization Cleanup"
source:
  file: "0_REVIT EXPORT_ALL_BACKUP-02.3dm"
  captured: "2026-05-11"
  notes: "AIA parent layers with material-specific visualization child layers. Source Revit context is preserved in RookCleanup user strings before mutation."

naming:
  case: UPPER
  aia_prefixes: true
  prefix_separator: "-"

cleanup:
  protected_layers:
    - "S-COLS"
    - "S-BEAM"
    - "A-FLOR"
    - "A-WALL"
    - "A-ROOF"
    - "A-GLAZ-CURT"
    - "A-GLAZ-CWMG"
    - "A-DOOR"
    - "S-FSTN"
    - "L-SITE"
    - "EXPANSION"
  orphan_policy: "report"
  unresolved_policy: "stay_on_source_layer"
  merge_revit_layers: false

metadata:
  namespace: "RookCleanup"
  omit_empty_values: true
  signals_key: "RookCleanup::Signals"
  run_status_values:
    - "audit_started"
    - "audit_complete"
    - "mutation_started"
    - "verification_failed"
    - "completed"
    - "aborted"

target_layers:
  - parent: "A-GLAZ"
    children:
      - "A-GLAZ-GLASS"
      - "A-GLAZ-MULL-METAL"
      - "A-GLAZ-FRAME-METAL"
  - parent: "A-DOOR"
    children:
      - "A-DOOR-PANEL-WOOD"
      - "A-DOOR-PANEL-METAL"
      - "A-DOOR-FRAME-METAL"
      - "A-DOOR-GLASS"
  - parent: "A-WALL"
    children:
      - "A-WALL-CONC"
      - "A-WALL-GYP"
      - "A-WALL-MISC"
  - parent: "A-FLOR"
    children:
      - "A-FLOR-CONC"
      - "A-FLOR-FINISH"
  - parent: "A-ROOF"
    children:
      - "A-ROOF-METAL"
      - "A-ROOF-CONC"
      - "A-ROOF-MISC"
  - parent: "S-BEAM"
    children:
      - "S-BEAM-STEEL"
  - parent: "S-COLS"
    children:
      - "S-COLS-STEEL"
      - "S-COLS-CONC"
  - parent: "S-FSTN"
    children:
      - "S-FSTN-METAL"
  - parent: "L-SITE"
    children:
      - "L-SITE-WATER"
      - "L-SITE-GRADE"
      - "L-SITE-PLANTING"
  - parent: "G-REF"
    children:
      - "G-REF-IMPORT"
      - "G-REF-UNCLASSIFIED"

classification_rules:
  high_confidence:
    - match: "System Panel - Glazed"
      target: "A-GLAZ::A-GLAZ-GLASS"
      material: "glass"
    - match: "Rectangular Mullion"
      target: "A-GLAZ::A-GLAZ-MULL-METAL"
      material: "metal"
    - match: "W-Wide Flange"
      target: "S-BEAM::S-BEAM-STEEL"
      material: "steel"
    - match: "HSS"
      target: "S-BEAM::S-BEAM-STEEL"
      material: "steel"
    - match: "Railing"
      target: "S-FSTN::S-FSTN-METAL"
      material: "metal"
  review_required:
    - match: "Door"
      reason: "Door blocks may contain panels, frames, glass, and hardware."
    - match: "Storefront"
      reason: "Storefront blocks are heterogeneous and require per-object mappings."
    - match: "Roof"
      reason: "Roof blocks may contain concrete, metal, membrane, or massing stand-ins."
```

- [ ] **Step 2: Verify the convention file exists**

Run:

```powershell
Test-Path "H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\conventions.yaml"
```

Expected: `True`.

## Task 3: Build Read-Only Inventory Artifacts

**Files:**
- Create: timestamped inventory JSON under `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup`

- [ ] **Step 1: Collect primary MCP reads**

Call these tools without mutation:

```json
{"tool":"rhino_document","params":{}}
{"tool":"rhino_layers","params":{}}
{"tool":"rhino_material_ops","params":{"action":"list"}}
{"tool":"rhino_blocks","params":{}}
{"tool":"rhino_block_layer_census","params":{}}
{"tool":"scene_graph","params":{"depth":"summary"}}
```

Expected: all calls succeed.

- [ ] **Step 2: Page document objects through HTTP bridge**

Run:

```powershell
$inst = Get-ChildItem "$env:TEMP\rook\instance-*-native.json" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  Get-Content -Raw |
  ConvertFrom-Json
$base = "http://127.0.0.1:$($inst.port)"
$objects = @()
$offset = 0
do {
  $page = Invoke-RestMethod "$base/objects?limit=500&offset=$offset"
  $objects += @($page.data.objects)
  $offset += 500
} while ($objects.Count -lt $page.data.totalCount)
$objects.Count
```

Expected: count equals `totalCount` from `/objects`, currently `10034`.

- [ ] **Step 3: Query dependencies for all empty layers**

Run:

```powershell
$layers = (Invoke-RestMethod "$base/layers").data.layers
$emptyLayerDependencies = foreach ($layer in @($layers | Where-Object { $_.objectCount -eq 0 })) {
  $encoded = [System.Web.HttpUtility]::UrlEncode($layer.fullPath)
  (Invoke-RestMethod "$base/layers/dependencies?name=$encoded").data
}
$emptyLayerDependencies.Count
```

Expected: count equals current empty layer count, currently `24`.

- [ ] **Step 4: Write inventory JSON**

Run with the variables from prior steps:

```powershell
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$inventoryPath = "H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup\$stamp-inventory.json"
$inventory = [ordered]@{
  generatedAt = (Get-Date).ToString("o")
  rhinoInstance = $inst
  document = (Invoke-RestMethod "$base/document").data
  layers = (Invoke-RestMethod "$base/layers").data
  materials = (Invoke-RestMethod "$base/materials").data
  blocks = (Invoke-RestMethod "$base/blocks").data
  blockLayerCensus = (Invoke-RestMethod "$base/block/layer-census").data
  objects = $objects
  emptyLayerDependencies = $emptyLayerDependencies
}
$inventory | ConvertTo-Json -Depth 12 | Set-Content -Path $inventoryPath -Encoding UTF8
$inventoryPath
```

Expected: a timestamped inventory path is printed.

## Task 4: Sample And Classify Representative Blocks

**Files:**
- Create: timestamped classification audit JSON under `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup`
- Create: timestamped cleanup report markdown under `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\.rook\cleanup`

- [ ] **Step 1: Build family groups from block names**

Run:

```powershell
$blocks = (Invoke-RestMethod "$base/blocks").data.blocks
$families = $blocks |
  Group-Object { ($_.name -split ' - ')[0] } |
  Sort-Object Count -Descending |
  Select-Object Count,Name
$families | Select-Object -First 20 | Format-Table
```

Expected: top families include `System Panel`, `Rectangular Mullion`, and structural families.

- [ ] **Step 2: Select representative blocks for detail reads**

Run:

```powershell
$representatives = @()
foreach ($family in $families | Select-Object -First 25) {
  $match = $blocks |
    Where-Object { ($_.name -split ' - ')[0] -eq $family.Name } |
    Sort-Object instanceCount -Descending |
    Select-Object -First 3
  $representatives += $match
}
$representatives.Count
```

Expected: up to `75` representative block definitions.

- [ ] **Step 3: Read representative block internals**

For each representative block, call `rhino_block_objects_detailed` with the actual `name` from `$representatives`:

```json
{
  "tool": "rhino_block_objects_detailed",
  "params": {
    "name": "$representative.name",
    "geometry": true
  }
}
```

Expected: each result includes object index, layer, material/color/name, visibility, bounding box, and typed geometry details.

- [ ] **Step 4: Apply deterministic first-pass classification rules**

Use these exact rule defaults for the first audit:

```text
Block name contains "System Panel - Glazed" -> A-GLAZ::A-GLAZ-GLASS, high
Block name contains "Rectangular Mullion" -> A-GLAZ::A-GLAZ-MULL-METAL, high
Block name contains "W-Wide Flange" -> S-BEAM::S-BEAM-STEEL, high unless instance/source layer is S-COLS
Block name contains "HSS" -> S-BEAM::S-BEAM-STEEL, high unless instance/source layer is S-COLS
Block name contains "Railing" -> S-FSTN::S-FSTN-METAL, high
Block/source layer contains "A-DOOR" or name contains "Door" -> review
Block/source layer contains "Roof" or name contains "Roof" -> review
Block/source layer contains "Storefront" -> review
No rule match -> low, stay on source layer
Conflicting instance contexts for one block definition -> review_shared_definition
```

Expected: no mutation; produce proposed records only.

- [ ] **Step 5: Write the classification audit JSON**

The audit JSON must have this shape:

```json
{
  "schemaVersion": "1",
  "runId": "$runId",
  "generatedAt": "$now",
  "sourceDocument": "H:\\AI EXPERIMENTS\\CRYSTAL_BRIDGES\\0_REVIT EXPORT_ALL_BACKUP-02.3dm",
  "targetLayerTaxonomy": [],
  "classificationStats": {
    "high": 0,
    "medium": 0,
    "low": 0,
    "review": 0,
    "reviewSharedDefinition": 0
  },
  "records": [],
  "reviewQueue": [],
  "sharedDefinitionConflicts": [],
  "emptyLayerDependencies": [],
  "unusedBlocks": []
}
```

Expected: every record with an empty source value either omits that field or encodes it inside non-empty `signals` JSON. No metadata value is `""`.

- [ ] **Step 6: Write the cleanup report markdown**

The report must include:

```markdown
# Crystal Bridges Cleanup Audit

## Source
- File:
- Generated:
- Run ID:

## Proposed Layer Counts

## High Confidence Mappings

## Medium Confidence Mappings For Review

## Shared Definition Conflicts

## Unresolved Items Left On Source Layers

## Empty Layer Cleanup

## Unused Block Definitions

## Recommended First Mutation Batch
```

Expected: report is readable without opening JSON.

## Task 5: Review Gate Before Mutation

**Files:**
- Read: latest `*-cleanup-report.md`
- Read: latest `*-classification-audit.json`

- [ ] **Step 1: Present the report summary**

Send the user:

```text
The audit is complete. I found:
- N high-confidence block/object mappings
- N medium-confidence mappings needing review
- N shared block-definition conflicts
- N unresolved items left on source layers
- N unused block definitions
- N empty layers directly deletable

Recommended first mutation batch:
- Create target layers
- Tag provenance metadata
- Remap only high-confidence homogeneous block definitions
- Leave review/shared-conflict items untouched

Approve this first mutation batch?
```

Expected: user approves, rejects, or edits the mutation batch.

- [ ] **Step 2: Stop if approval is not explicit**

If the user does not approve mutation, do not call mutation tools. Revise the audit or report instead.

## Task 6: Create Approved Target Layers

**Files:**
- Mutates Rhino file after approval.

- [ ] **Step 1: Create missing parent layers**

Call `rhino_layer_create_batch` with parents that do not already exist:

```json
{
  "layers": [
    {"key":"a_glaz","name":"A-GLAZ"},
    {"key":"a_door","name":"A-DOOR"},
    {"key":"a_wall","name":"A-WALL"},
    {"key":"a_flor","name":"A-FLOR"},
    {"key":"a_roof","name":"A-ROOF"},
    {"key":"s_beam","name":"S-BEAM"},
    {"key":"s_cols","name":"S-COLS"},
    {"key":"s_fstn","name":"S-FSTN"},
    {"key":"l_site","name":"L-SITE"},
    {"key":"g_ref","name":"G-REF"}
  ]
}
```

Expected: existing layers are skipped or reported as already present; missing layers are created.

- [ ] **Step 2: Create missing child layers**

Call `rhino_layer_create_batch` with parents and children in one keyed batch. Existing top-level parents may report as already present; if the batch rejects existing parent collisions, create missing children with `rhino_layer_create` one at a time using the existing `parent` path.

```json
{
  "layers": [
    {"key":"a_glaz","name":"A-GLAZ"},
    {"key":"a_glaz_glass","name":"A-GLAZ-GLASS","parentKey":"a_glaz"},
    {"key":"a_glaz_mull_metal","name":"A-GLAZ-MULL-METAL","parentKey":"a_glaz"},
    {"key":"a_glaz_frame_metal","name":"A-GLAZ-FRAME-METAL","parentKey":"a_glaz"},
    {"key":"a_door","name":"A-DOOR"},
    {"key":"a_door_panel_wood","name":"A-DOOR-PANEL-WOOD","parentKey":"a_door"},
    {"key":"a_door_panel_metal","name":"A-DOOR-PANEL-METAL","parentKey":"a_door"},
    {"key":"a_door_frame_metal","name":"A-DOOR-FRAME-METAL","parentKey":"a_door"},
    {"key":"a_door_glass","name":"A-DOOR-GLASS","parentKey":"a_door"},
    {"key":"a_wall","name":"A-WALL"},
    {"key":"a_wall_conc","name":"A-WALL-CONC","parentKey":"a_wall"},
    {"key":"a_wall_gyp","name":"A-WALL-GYP","parentKey":"a_wall"},
    {"key":"a_wall_misc","name":"A-WALL-MISC","parentKey":"a_wall"},
    {"key":"a_flor","name":"A-FLOR"},
    {"key":"a_flor_conc","name":"A-FLOR-CONC","parentKey":"a_flor"},
    {"key":"a_flor_finish","name":"A-FLOR-FINISH","parentKey":"a_flor"},
    {"key":"a_roof","name":"A-ROOF"},
    {"key":"a_roof_metal","name":"A-ROOF-METAL","parentKey":"a_roof"},
    {"key":"a_roof_conc","name":"A-ROOF-CONC","parentKey":"a_roof"},
    {"key":"a_roof_misc","name":"A-ROOF-MISC","parentKey":"a_roof"},
    {"key":"s_beam","name":"S-BEAM"},
    {"key":"s_beam_steel","name":"S-BEAM-STEEL","parentKey":"s_beam"},
    {"key":"s_cols","name":"S-COLS"},
    {"key":"s_cols_steel","name":"S-COLS-STEEL","parentKey":"s_cols"},
    {"key":"s_cols_conc","name":"S-COLS-CONC","parentKey":"s_cols"},
    {"key":"s_fstn","name":"S-FSTN"},
    {"key":"s_fstn_metal","name":"S-FSTN-METAL","parentKey":"s_fstn"},
    {"key":"l_site","name":"L-SITE"},
    {"key":"l_site_water","name":"L-SITE-WATER","parentKey":"l_site"},
    {"key":"l_site_grade","name":"L-SITE-GRADE","parentKey":"l_site"},
    {"key":"l_site_planting","name":"L-SITE-PLANTING","parentKey":"l_site"},
    {"key":"g_ref","name":"G-REF"},
    {"key":"g_ref_import","name":"G-REF-IMPORT","parentKey":"g_ref"},
    {"key":"g_ref_unclassified","name":"G-REF-UNCLASSIFIED","parentKey":"g_ref"}
  ]
}
```

Expected: target children exist after this step.

- [ ] **Step 3: Verify layer creation**

Call:

```json
{"tool":"rhino_layers","params":{}}
```

Expected: every approved parent and child layer appears in `fullPath` form.

## Task 7: Write Run Manifest And Provenance Metadata

**Files:**
- Mutates Rhino document/user strings only after approval.

- [ ] **Step 1: Write document manifest with mutation status**

Call:

```json
{
  "tool": "rhino_usertext_document_set",
  "params": {
    "userStrings": {
      "RookCleanup::SchemaVersion": "1",
      "RookCleanup::LatestRunId": "$runId",
      "RookCleanup::RunStatus": "mutation_started",
      "RookCleanup::ConventionName": "Crystal Bridges Visualization Cleanup",
      "RookCleanup::TargetLayerTaxonomy": "{\"parents\":[\"A-GLAZ\",\"A-DOOR\",\"A-WALL\",\"A-FLOR\",\"A-ROOF\",\"S-BEAM\",\"S-COLS\",\"S-FSTN\",\"L-SITE\",\"G-REF\"]}",
      "RookCleanup::ClassificationStats": "{\"high\":0,\"medium\":0,\"low\":0,\"review\":0,\"reviewSharedDefinition\":0}",
      "RookCleanup::ReviewQueueSummary": "{\"count\":0}",
      "RookCleanup::AuditTimestamp": "$now",
      "RookCleanup::StartedAt": "$now",
      "RookCleanup::BackupPath": "$backupPath"
    }
  }
}
```

Replace the JSON string values with counts and timestamps from the approved audit. Do not include `RookCleanup::CompletedAt` or `RookCleanup::LatestCompletedRunId` yet.

- [ ] **Step 2: Write block-level summaries for approved block definitions**

For each approved block definition record from the audit, call:

```json
{
  "tool": "rhino_block_user_strings",
  "params": {
    "name": "$record.blockName",
    "action": "set",
    "userStrings": {
      "RookCleanup::SchemaVersion": "1",
      "RookCleanup::RunId": "$runId",
      "RookCleanup::ClassificationSummary": "{\"confidence\":\"high\",\"target\":\"A-GLAZ::A-GLAZ-GLASS\",\"material\":\"glass\"}",
      "RookCleanup::LayerMappingSummary": "{\"mode\":\"whole_block\",\"target\":\"A-GLAZ::A-GLAZ-GLASS\"}",
      "RookCleanup::RequiresReview": "false"
    }
  }
}
```

Expected: only non-empty string values are written.

- [ ] **Step 3: Defer object-level provenance when no route can write block-object user strings safely**

If the current available route for block-definition object user strings cannot preserve non-empty per-object provenance for the selected block objects, do not fake it. Record provenance at the block-definition summary level and keep the per-object details in the audit JSON. Add a report note:

```text
Per-object block provenance is represented in the cleanup audit artifact for this batch. Rhino block object user strings were not written because the available route did not support the required non-empty per-object provenance shape for this operation.
```

Expected: no empty user strings are attempted.

## Task 8: Remap Approved Block-Definition Object Layers

**Files:**
- Mutates Rhino block definitions after approval.

- [ ] **Step 1: Remap homogeneous approved definitions with batch**

Use this only for blocks where every object maps to the same target and all instance contexts agree. Build `items` from approved homogeneous audit records:

```json
{
  "tool": "rhino_block_set_layers_batch",
  "params": {
    "items": [
      {
        "name": "$record.blockName",
        "layer": "$record.targetLayer"
      }
    ],
    "redraw": false
  }
}
```

Expected: routed count equals approved homogeneous count; skipped items are reviewed before continuing.

- [ ] **Step 2: Remap heterogeneous approved definitions with per-object mappings**

Use this for storefronts, doors, or other mixed definitions after review approval. Build `mappings` from the approved per-object audit records for that block:

```json
{
  "tool": "rhino_block_set_layers",
  "params": {
    "name": "$record.blockName",
    "mappings": [
      {"index": "$mapping.index", "layer": "$mapping.targetLayer"}
    ]
  }
}
```

Expected: all listed indices remap; unlisted indices remain untouched.

- [ ] **Step 3: Do not remap shared-context conflicts**

For any audit record with `reviewSharedDefinition`, skip mutation and add it to the next review queue. Do not use definition-level remapping until the user approves either leaving it as-is or duplicating the block definition per context.

## Task 9: Move Approved Loose Objects

**Files:**
- Mutates document object layers after approval.

- [ ] **Step 1: Move only approved loose-object groups**

For each approved source-to-target move from the audit, call:

```json
{
  "tool": "rhino_layer_move_objects",
  "params": {
    "source": "$move.sourceLayer",
    "target": "$move.targetLayer"
  }
}
```

Expected: source object count decreases and target object count increases. Do not use this for layers containing mixed material categories unless the audit proves the whole layer is homogeneous.

- [ ] **Step 2: Keep unresolved loose objects on source layers**

No tool call. Confirm unresolved items remain untouched in the report.

## Task 10: Purge And Delete Only Proven-Safe Items

**Files:**
- Mutates Rhino file after approval.

- [ ] **Step 1: Purge unused blocks after classification metadata and layer remapping**

Call:

```json
{
  "tool": "rhino_block_purge",
  "params": {
    "unused": true,
    "deleted": true
  }
}
```

Expected: only unused/deleted block definitions are purged. If purge reports skipped definitions, preserve the reasons in the cleanup report.

- [ ] **Step 2: Re-check dependencies before deleting empty layers**

For each candidate empty layer, call:

```json
{
  "tool": "rhino_layer_dependencies",
  "params": {
    "name": "$layer.fullPath"
  }
}
```

Expected: `canDelete` is `true`.

- [ ] **Step 3: Delete only dependency-free empty layers**

For each layer with `canDelete=true`, call:

```json
{
  "tool": "rhino_layer_delete",
  "params": {
    "name": "$layer.fullPath"
  }
}
```

Expected: deletion succeeds. If any deletion fails, record it and continue with other approved deletes.

## Task 11: Verify And Complete Manifest

**Files:**
- Mutates document user strings only after verification.
- Updates cleanup report artifact with final status.

- [ ] **Step 1: Re-read layer, block, and dependency state**

Call:

```json
{"tool":"rhino_layers","params":{}}
{"tool":"rhino_blocks","params":{}}
{"tool":"rhino_block_layer_census","params":{}}
{"tool":"scene_graph","params":{"depth":"summary"}}
```

Expected: target layers exist and approved mappings are reflected in block-layer census.

- [ ] **Step 2: Capture viewport evidence**

Call:

```json
{
  "tool": "rhino_viewport",
  "params": {
    "view": "Perspective",
    "displayMode": "Shaded",
    "zoomExtents": true,
    "width": 1600,
    "height": 1000
  }
}
```

Expected: viewport image path is returned and image is nonblank.

- [ ] **Step 3: Update manifest as completed only after verification succeeds**

Call:

```json
{
  "tool": "rhino_usertext_document_set",
  "params": {
    "userStrings": {
      "RookCleanup::RunStatus": "completed",
      "RookCleanup::LatestCompletedRunId": "$runId",
      "RookCleanup::CompletedAt": "$completedAt"
    }
  }
}
```

Expected: document user strings show completed run status.

- [ ] **Step 4: Save the cleaned Rhino file**

Call:

```json
{
  "tool": "rhino_document_ops",
  "params": {
    "action": "save",
    "path": "H:\\AI EXPERIMENTS\\CRYSTAL_BRIDGES\\0_REVIT EXPORT_ALL_BACKUP-02.3dm"
  }
}
```

Expected: save succeeds.
