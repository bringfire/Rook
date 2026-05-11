# Crystal Bridges Visualization Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for live Rhino operations. Execute mutation tasks in one inline operator session because the shared state is the open `.3dm`, Rhino undo stack, active document, and viewport. Subagents may be used only for read-only artifact review after JSON/report files are written. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean the active Crystal Bridges Revit-export Rhino file into an AIA parent/child visualization layer structure while preserving source provenance as queryable user metadata.

**Architecture:** Use existing Rook MCP tools and native HTTP routes from one live Rhino operator session. The workflow is audit-first: collect live Rhino state, classify every candidate that may be remapped, write review artifacts, get approval, then mutate layers/block-definition object layers with provenance and manifest safeguards.

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

- [ ] **Step 4: Ask for explicit preflight backup/save approval**

Before any save call, ask:

```text
The file is modified. Creating an in-memory-accurate backup requires Rhino save operations: SaveAs to the backup path, then SaveAs back to the original path so the working file remains the intended document. This writes to disk before the mutation approval gate. Approve this preflight backup/save?
```

Expected: user explicitly approves. If not approved, stop before calling `rhino_document_ops`.

- [ ] **Step 5: Save a Rhino backup through the document route**

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

- [ ] **Step 6: Save back to the original path**

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

- [ ] **Step 7: Confirm the active document path after backup**

Call:

```json
{"tool":"rhino_document","params":{}}
```

Expected:

```json
{"path":"H:\\AI EXPERIMENTS\\CRYSTAL_BRIDGES\\0_REVIT EXPORT_ALL_BACKUP-02.3dm"}
```

If the active path is not the original path, stop and correct the active document before continuing.

- [ ] **Step 8: Commit checkpoint**

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

## Task 4: Discover Rules And Build Complete Candidate Audit

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

- [ ] **Step 4: Apply deterministic first-pass classification rules to representative blocks**

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

Expected: no mutation; produce candidate rules only. Representative sampling is for rule discovery, not sufficient evidence for mutation.

- [ ] **Step 5: Build the complete candidate universe**

Create a candidate set containing every item that may be remapped. Include both name-token matches and block definitions whose internal layers already sit on AIA/source layers that map to the target taxonomy:

```powershell
$nameTokenBlocks = @($blocks | Where-Object {
  $_.name -match 'System Panel - Glazed|Rectangular Mullion|W-Wide Flange|HSS|Railing|Door|Storefront|Roof'
})

$taxonomyLayerPattern = 'A-GLAZ|A-DOOR|A-WALL|A-FLOR|A-ROOF|S-BEAM|S-COLS|S-FSTN|L-SITE|EXPANSION'
$censusLayerBlocks = @($inventory.blockLayerCensus.blocks | Where-Object {
  @($_.layers | Where-Object { $_.layer -match $taxonomyLayerPattern }).Count -gt 0
} | ForEach-Object {
  $blockName = $_.name
  $blocks | Where-Object { $_.name -eq $blockName }
})

$candidateBlocks = @($nameTokenBlocks + $censusLayerBlocks |
  Where-Object { $_ -ne $null } |
  Sort-Object name -Unique)

$candidateLooseLayerGroups = @($layers | Where-Object {
  $_.objectCount -gt 0 -and $_.fullPath -match $taxonomyLayerPattern
})

[pscustomobject]@{
  candidateBlockDefinitions = $candidateBlocks.Count
  candidateLooseLayerGroups = $candidateLooseLayerGroups.Count
}
```

Expected: the candidate set includes every block definition or loose-object/layer group that the first mutation batch might touch, whether the useful signal comes from block name, block-internal layer, or loose-object source layer. Nothing outside this set may be remapped in later mutation tasks.

- [ ] **Step 6: Read full detail for every candidate block that may be remapped**

For every candidate block definition, call `rhino_block_objects_detailed` with `geometry=true`:

```json
{
  "tool": "rhino_block_objects_detailed",
  "params": {
    "name": "$candidateBlock.name",
    "geometry": true
  }
}
```

Expected: every block definition proposed for remapping has complete object-index detail. Blocks that cannot be read successfully are classified as `review` and cannot be mutated in the first batch.

- [ ] **Step 7: Determine shared instance context for every candidate block**

For every candidate block definition, call:

```json
{
  "tool": "rhino_block_instances",
  "params": {
    "name": "$candidateBlock.name",
    "depth": 0
  }
}
```

Expected: every block candidate has `instanceContextDecision`:

```json
{
  "blockName": "$candidateBlock.name",
  "instanceLayerTargetsAgree": true,
  "instanceLayers": ["A-GLAZ-CURT"],
  "decision": "definition_remap_allowed"
}
```

If instance contexts imply different target layers, set:

```json
{
  "blockName": "$candidateBlock.name",
  "instanceLayerTargetsAgree": false,
  "decision": "review_shared_definition"
}
```

Any `review_shared_definition` block is excluded from mutation unless the user approves a block-duplication strategy.

- [ ] **Step 8: Build complete remap records**

Every approved-candidate record must include exact mutation inputs:

```json
{
  "recordType": "block_definition_object",
  "blockName": "System Panel - Glazed-114458-_3D - kmacnichol_",
  "objectIndex": 0,
  "sourceLayer": "A-GLAZ-CURT",
  "targetLayer": "A-GLAZ::A-GLAZ-GLASS",
  "inferredMaterial": "glass",
  "confidence": "high",
  "instanceContextDecision": "definition_remap_allowed",
  "mutationMode": "per_object_mapping",
  "signals": {
    "blockNameTokens": ["System Panel", "Glazed"],
    "sourceLayer": "A-GLAZ-CURT",
    "geometryType": "Brep"
  }
}
```

Loose-object group records must include:

```json
{
  "recordType": "loose_object_group",
  "sourceLayer": "L-SITE",
  "targetLayer": "L-SITE::L-SITE-GRADE",
  "objectIds": ["guid-1", "guid-2"],
  "confidence": "high",
  "mutationMode": "layer_move",
  "signals": {
    "sourceLayer": "L-SITE",
    "classificationReason": "homogeneous site layer approved for first batch"
  }
}
```

No mutation task may invent a block name, object index, object id, source layer, or target layer that is absent from the approved audit JSON.

- [ ] **Step 9: Write the classification audit JSON**

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
  "unusedBlocks": [],
  "completeCandidatePass": {
    "blockDefinitionsConsidered": 0,
    "looseLayerGroupsConsidered": 0,
    "candidateRecordsWritten": 0
  }
}
```

Expected: every record with an empty source value either omits that field or encodes it inside non-empty `signals` JSON. No metadata value is `""`.

- [ ] **Step 10: Write the cleanup report markdown**

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

- [ ] **Step 3: Materialize and prevalidate exact outbound provenance payloads**

Before writing any object or block-object user strings, build the exact route payloads that will be sent. Optional fields are omitted when empty. Required fields must be non-empty. Then validate every outbound value is a non-empty string.

```powershell
function Add-NonEmptyString {
  param(
    [hashtable]$Map,
    [string]$Key,
    $Value,
    [bool]$Required = $false
  )
  $text = if ($null -eq $Value) { "" } else { [string]$Value }
  if ([string]::IsNullOrWhiteSpace($text)) {
    if ($Required) { throw "Required metadata value '$Key' is empty." }
    return
  }
  $Map[$Key] = $text
}

function New-RookCleanupUserStrings {
  param($Record, [string]$RunId)

  $signalsJson = ($Record.signals | ConvertTo-Json -Depth 8 -Compress)
  if ([string]::IsNullOrWhiteSpace($signalsJson) -or $signalsJson -eq "null") {
    throw "Record has no non-empty signals JSON."
  }

  $map = @{}
  Add-NonEmptyString $map "RookCleanup::SchemaVersion" "1" $true
  Add-NonEmptyString $map "RookCleanup::RunId" $RunId $true
  Add-NonEmptyString $map "RookCleanup::OriginalLayer" $Record.sourceLayer $true
  Add-NonEmptyString $map "RookCleanup::OriginalBlock" $Record.blockName $false
  Add-NonEmptyString $map "RookCleanup::OriginalBlockObjectIndex" $Record.objectIndex $false
  Add-NonEmptyString $map "RookCleanup::InferredLayer" $Record.targetLayer $true
  Add-NonEmptyString $map "RookCleanup::InferredMaterial" $Record.inferredMaterial $false
  Add-NonEmptyString $map "RookCleanup::Confidence" $Record.confidence $true
  Add-NonEmptyString $map "RookCleanup::Reason" $Record.reason $false
  Add-NonEmptyString $map "RookCleanup::Signals" $signalsJson $true
  Add-NonEmptyString $map "RookCleanup::Reviewed" $Record.reviewedString $false
  return $map
}

$blockObjectUserStringPayloads = @()
foreach ($record in @($approvedRecords | Where-Object { $_.recordType -eq "block_definition_object" })) {
  $blockObjectUserStringPayloads += [pscustomobject]@{
    blockName = $record.blockName
    objectIndex = [int]$record.objectIndex
    userStrings = New-RookCleanupUserStrings -Record $record -RunId $runId
  }
}

$looseObjectUserStringPayloads = @()
foreach ($record in @($approvedRecords | Where-Object { $_.recordType -eq "loose_object_group" })) {
  foreach ($objectId in @($record.objectIds)) {
    $looseObjectUserStringPayloads += [pscustomobject]@{
      id = $objectId
      sourceLayer = $record.sourceLayer
      targetLayer = $record.targetLayer
      userStrings = New-RookCleanupUserStrings -Record $record -RunId $runId
    }
  }
}

$allUserStringMaps = @($blockObjectUserStringPayloads.userStrings + $looseObjectUserStringPayloads.userStrings)
$invalidValues = @()
foreach ($map in $allUserStringMaps) {
  foreach ($prop in $map.GetEnumerator()) {
    if ($prop.Value -isnot [string] -or [string]::IsNullOrWhiteSpace($prop.Value)) {
      $invalidValues += [pscustomobject]@{ key = $prop.Key; value = $prop.Value }
    }
  }
}
if ($invalidValues.Count -gt 0) {
  throw "Metadata prevalidation failed: outbound user-string payload contains empty or non-string values."
}
```

Expected: `$blockObjectUserStringPayloads` and `$looseObjectUserStringPayloads` contain the exact outbound route payload data. Optional empty values are omitted. Every value in every `userStrings` map is a non-empty string.

- [ ] **Step 4: Write per-object provenance for approved block-object remaps**

For each approved block definition with object-index mappings, call `rhino_block_set_object_user_strings` before layer remapping. Build `mappings` from `$blockObjectUserStringPayloads` grouped by `blockName`:

```json
{
  "tool": "rhino_block_set_object_user_strings",
  "params": {
    "name": "$payloadGroup.blockName",
    "mappings": [
      {
        "index": "$payload.objectIndex",
        "userStrings": "$payload.userStrings"
      }
    ]
  }
}
```

Expected: every approved block-object remap has durable per-index provenance before its layer is changed. If any provenance write fails, do not remap that block definition in Task 8.

- [ ] **Step 5: Write provenance for approved loose objects**

For each approved loose object id in `$looseObjectUserStringPayloads`, call `rhino_usertext_object_set` before layer movement:

```json
{
  "tool": "rhino_usertext_object_set",
  "params": {
    "id": "$payload.id",
    "userStrings": "$payload.userStrings"
  }
}
```

Expected: every loose object that will move in Task 9 has non-empty provenance user strings first. If any provenance write fails, remove that object or group from the approved mutation batch.

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

- [ ] **Step 1: Prove each approved loose-object group covers the whole current source layer**

`rhino_layer_move_objects` moves all direct objects on the source layer. Use it only when the approved audit `objectIds` exactly equal all current direct objects on that source layer.

For each approved loose-object group, page the current direct source-layer objects:

```powershell
function Get-AllRhinoObjectsOnLayer {
  param([string]$BaseUrl, [string]$Layer)
  $all = @()
  $offset = 0
  $encodedLayer = [System.Web.HttpUtility]::UrlEncode($Layer)
  do {
    $page = Invoke-RestMethod "$BaseUrl/objects?layer=$encodedLayer&limit=500&offset=$offset"
    $all += @($page.data.objects)
    $offset += 500
  } while ($all.Count -lt $page.data.totalCount)
  return $all
}

$looseMovePayloads = @()
foreach ($move in @($approvedRecords | Where-Object { $_.recordType -eq "loose_object_group" })) {
  $currentObjects = @(Get-AllRhinoObjectsOnLayer -BaseUrl $base -Layer $move.sourceLayer)
  $currentIds = @($currentObjects | ForEach-Object { $_.id } | Sort-Object)
  $approvedIds = @($move.objectIds | Sort-Object)

  $sameCount = $currentIds.Count -eq $approvedIds.Count
  $sameIds = -not (Compare-Object -ReferenceObject $currentIds -DifferenceObject $approvedIds)

  if ($sameCount -and $sameIds) {
    $looseMovePayloads += [pscustomobject]@{
      sourceLayer = $move.sourceLayer
      targetLayer = $move.targetLayer
      objectIds = $approvedIds
      mode = "whole_layer_move_allowed"
    }
  } else {
    $move.mutationMode = "skipped_requires_different_strategy"
    $move.reason = "Approved objectIds do not exactly equal all current direct objects on source layer; rhino_layer_move_objects would move unapproved objects."
  }
}
```

Expected: only groups in `$looseMovePayloads` may use `rhino_layer_move_objects`. Any partial-layer group is skipped and returned to review unless the user approves a different strategy.

- [ ] **Step 2: Move only whole-layer approved loose-object groups**

For each payload in `$looseMovePayloads`, call:

```json
{
  "tool": "rhino_layer_move_objects",
  "params": {
    "source": "$payload.sourceLayer",
    "target": "$payload.targetLayer"
  }
}
```

Expected: source object count decreases and target object count increases. Do not use this for layers containing mixed material categories or unapproved direct objects.

- [ ] **Step 3: Keep unresolved and partial-layer loose objects on source layers**

No tool call. Confirm unresolved items and skipped partial-layer groups remain untouched in the report.

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

Failure rule for Tasks 7-11: if any approved mutation fails and cannot be cleanly skipped, write `RookCleanup::RunStatus=aborted`. If verification fails after mutations ran, write `RookCleanup::RunStatus=verification_failed`. In both cases, update the cleanup report with the failed step and do not set `RookCleanup::LatestCompletedRunId`.

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

- [ ] **Step 3: If verification fails, write failure status and stop**

If layer/block/dependency/viewport verification fails, call:

```json
{
  "tool": "rhino_usertext_document_set",
  "params": {
    "userStrings": {
      "RookCleanup::RunStatus": "verification_failed",
      "RookCleanup::ReviewQueueSummary": "{\"status\":\"verification_failed\",\"failedStep\":\"Task 11\",\"latestCompletedRunIdSet\":false}"
    }
  }
}
```

Expected: `LatestCompletedRunId` is not written. Stop and report the verification failure instead of saving the cleaned file as completed.

- [ ] **Step 4: If mutation aborts before verification, write aborted status**

If a mutation step fails and the operator stops before verification, call:

```json
{
  "tool": "rhino_usertext_document_set",
  "params": {
    "userStrings": {
      "RookCleanup::RunStatus": "aborted",
      "RookCleanup::ReviewQueueSummary": "{\"status\":\"aborted\",\"latestCompletedRunIdSet\":false}"
    }
  }
}
```

Expected: `LatestCompletedRunId` is not written. Update the cleanup report with the failed operation and stop.

- [ ] **Step 5: Update manifest as completed only after verification succeeds**

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

- [ ] **Step 6: Save the cleaned Rhino file**

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
