# Crystal Bridges Visualization Cleanup Design

Date: 2026-05-11

## Context

The active Rhino file is `H:\AI EXPERIMENTS\CRYSTAL_BRIDGES\0_REVIT EXPORT_ALL_BACKUP-02.3dm`.
It is a Revit-exported model intended for visualization cleanup.

Current read-only scan:

- 10,034 Rhino objects
- 48 layers
- 24 empty layers
- 3,831 block definitions
- 122 unused block definitions
- 3,127 one-object block definitions
- 3,115 single-instance block definitions
- 1 material, `Plaster`

The current layers already use many AIA-style names, but Revit export blocks mix visually different geometry under the same system layer. For example, curtain-wall exports can place glazing panels, mullions, frames, and doors under related curtain-wall layers even though those objects need different visualization materials.

## Goal

Clean up the file for visualization by organizing geometry into a minimal, AIA-compatible parent/child layer structure where child layers represent renderable material or visual categories.

The workflow must avoid premature flattening. Before any layer remapping, Rook must classify geometry from all available signals and preserve source context as metadata so future sessions can query, audit, and revise the cleanup.

## Non-Goals

- Do not discard block definitions before classification.
- Do not merge all geometry into coarse material layers without preserving provenance.
- Do not force ambiguous geometry into a confident material bucket.
- Do not rely only on current layer names.
- Do not mutate the open file before a backup and a reviewed audit report.

## Target Layer Convention

Use AIA-style parent layers with material-specific child layers.

Initial target taxonomy:

```text
A-GLAZ
  A-GLAZ-GLASS
  A-GLAZ-MULL-METAL
  A-GLAZ-FRAME-METAL

A-DOOR
  A-DOOR-PANEL-WOOD
  A-DOOR-PANEL-METAL
  A-DOOR-FRAME-METAL
  A-DOOR-GLASS

A-WALL
  A-WALL-CONC
  A-WALL-GYP
  A-WALL-MISC

A-FLOR
  A-FLOR-CONC
  A-FLOR-FINISH

A-ROOF
  A-ROOF-METAL
  A-ROOF-CONC
  A-ROOF-MISC

S-BEAM
  S-BEAM-STEEL

S-COLS
  S-COLS-STEEL
  S-COLS-CONC

S-FSTN
  S-FSTN-METAL

L-SITE
  L-SITE-WATER
  L-SITE-GRADE
  L-SITE-PLANTING

G-REF
  G-REF-IMPORT
  G-REF-UNCLASSIFIED
```

The audit may propose additions when the file contains clear categories not covered here. New layers must preserve the parent/child AIA pattern.

## Classification Inputs

Rook should classify every candidate object or block-definition object using weighted evidence:

- Existing object layer and block-internal layer.
- Block definition name, including family/type/export IDs.
- Block instance layer and instance context.
- Object name, color, material, and existing user strings.
- Geometry type and metrics from block/object detail routes.
- Scene graph classification and relationships.
- Revit export naming patterns such as `System Panel - Glazed`, `Rectangular Mullion`, `W-Wide Flange`, `HSS`, `Railing`, `Door`, and `Roof Massing`.

Confidence levels:

- `high`: block or object metadata strongly indicates material and system.
- `medium`: multiple weaker signals agree.
- `low`: only generic layer, color, or geometry heuristics apply.
- `review`: conflicting or insufficient evidence.

Only `high` and reviewed `medium` classifications should be remapped automatically. `low` and `review` items stay on their source layers by default. They may move to `G-REF::G-REF-UNCLASSIFIED` only when the reviewed audit explicitly approves moving unresolved items into that bucket.

## Metadata Strategy

Metadata is a primary data source, not a side effect. The cleanup should write durable, queryable user strings before remapping geometry.

For document objects and block-definition objects, use namespaced keys:

```text
RookCleanup::SchemaVersion
RookCleanup::RunId
RookCleanup::OriginalLayer
RookCleanup::OriginalObjectName
RookCleanup::OriginalBlock
RookCleanup::OriginalBlockObjectIndex
RookCleanup::OriginalInstanceLayer
RookCleanup::OriginalMaterial
RookCleanup::OriginalColor
RookCleanup::InferredParentLayer
RookCleanup::InferredLayer
RookCleanup::InferredMaterial
RookCleanup::Confidence
RookCleanup::Reason
RookCleanup::Signals
RookCleanup::Reviewed
```

`RookCleanup::Signals` should be compact JSON stored as a string. It should include the evidence used for classification, such as matched block-name tokens, source layer, geometry class, and scene graph class.

Typed usertext write routes reject empty-string values because OpenNURBS treats empty strings as delete sentinels. Cleanup metadata must never write `""`. If a source value is missing or empty, omit that key or encode the field inside a non-empty JSON value such as `{"value":null}` in `RookCleanup::Signals`.

For block definitions, use `rhino_block_user_strings` to maintain block-level summary metadata:

```text
RookCleanup::SchemaVersion
RookCleanup::RunId
RookCleanup::ClassificationSummary
RookCleanup::LayerMappingSummary
RookCleanup::RequiresReview
```

At document level, use document user strings for a cleanup manifest:

```text
RookCleanup::SchemaVersion
RookCleanup::LatestRunId
RookCleanup::LatestCompletedRunId
RookCleanup::RunStatus
RookCleanup::ConventionName
RookCleanup::TargetLayerTaxonomy
RookCleanup::ClassificationStats
RookCleanup::ReviewQueueSummary
RookCleanup::AuditTimestamp
RookCleanup::StartedAt
RookCleanup::CompletedAt
RookCleanup::BackupPath
```

The manifest lets future Rook sessions discover cleanup state without assuming partial work completed. `LatestRunId` identifies the active or most recent attempted run. `RunStatus` must distinguish `audit_started`, `audit_complete`, `mutation_started`, `verification_failed`, `completed`, and `aborted`. `LatestCompletedRunId` and `CompletedAt` must update only after verification succeeds.

## Audit Workflow

1. Confirm Rhino bridge health with `rhino_ping`.
2. Read document, layers, materials, blocks, and object summaries.
3. Capture `rhino_block_layer_census` to understand block-internal layer usage.
4. Use `rhino_layer_dependencies` on empty or candidate-to-delete layers.
5. Sample representative block definitions with `rhino_block_objects_detailed`.
6. Use `rhino_block_compare` on candidate duplicate families before any merge decision.
7. Query `scene_graph` and `scene_query` for spatial and shape context.
8. Build a proposed classification table with counts by target layer and confidence.
9. Detect shared block definitions where different instance contexts imply different target layers.
10. Present the report for review before mutation.

The audit report should include:

- Proposed target layers and object/block-object counts.
- High-confidence mappings.
- Medium-confidence mappings needing review.
- Review queue items and reasons.
- Unused block definitions eligible for purge.
- Empty layers that are directly deletable.
- Empty layers blocked by block-definition references.
- Candidate duplicate block families for dry-run merge.
- Shared block-definition conflicts where definition-level remapping would affect instances that need different targets.

## Execution Workflow

All mutation must be gated by user approval.

1. Create a backup copy of the `.3dm` file.
2. Create approved target layers.
3. Write provenance metadata to document objects, block-definition objects, block definitions, and document manifest. Mark the manifest `RunStatus` as `mutation_started`, but do not update `LatestCompletedRunId`.
4. Remap block-definition object layers. Use `rhino_block_set_layers` with per-object `mappings` for heterogeneous definitions, such as blocks containing glazing, mullions, frames, and panels. Reserve `rhino_block_set_layers_batch` for homogeneous whole-block moves where every object in each listed block definition maps to the same target layer.
5. Move document-level loose objects to approved target layers.
6. Assign or create materials after layer grouping is stable.
7. Dry-run block merges with `rhino_block_merge` before execution.
8. Purge unused block definitions after remapping.
9. Delete only layers proven empty and dependency-free.
10. Verify with fresh layer, block, dependency, and viewport checks.
11. After successful verification, update the document manifest with `RunStatus=completed`, `CompletedAt`, and `LatestCompletedRunId`.

## Safety Rules

- Never delete or merge a layer without `rhino_layer_dependencies`.
- Never purge blocks before classification metadata is written.
- Never remap ambiguous items without review.
- Preserve original context in user strings before moving geometry.
- Prefer block-definition object remapping over exploding blocks.
- Remap block-definition objects only when all instance contexts agree with the proposed target mapping. If a shared definition is used in conflicting contexts, leave it in review or require an approved block-duplication strategy before remapping.
- Use block merge only where `rhino_block_compare` shows compatible definitions and dry-run confirms expected instance counts.
- Keep `G-REF::G-REF-UNCLASSIFIED` as an explicit review bucket instead of hiding uncertain geometry.

## Expected Outcome

The cleaned model should have a small, readable AIA parent/child layer tree suitable for visualization material assignment. Curtain-wall, door, structural, roof, site, and reference content should be separated by renderable material category while retaining original Revit export context as queryable metadata.

Future Rook sessions should be able to answer questions such as:

- Where did this object come from originally?
- Why was this object classified as glass, mullion metal, steel, concrete, or unclassified?
- Which block definitions still need review?
- Which layers are safe to delete or merge?
- What classification rules produced the current layer structure?
