# BIM Relationship Projection v1 - design

> Status (2026-06-17): DESIGN - brainstorm complete, ready for writing-plans after review.
> Branch: `feature/bim-relationship-projection-v1`.
> Base: current `origin/main` (`32d4a093`, PR #266 merge).
>
> This slice starts from a clean branch off `origin/main`. The old
> `feature/spatial-intelligence` branch is archival context only and is not the base for this work.

## 1. Goal

RookBIM preset exports now carry enough factual Revit metadata to become useful graph substrate:
stable object join keys, element identity/category/family/type/name labels, room records, and
relationship indexes for host, room, and level membership. Threshold Calibration v1 intentionally
kept those labels post-hoc for evaluation. This slice makes a different product decision:

**BIM facts are first-class read-model facts.**

The goal of v1 is a Python scene-graph projector that consumes a RookBIM export sidecar and the
current Rhino/Rook scene graph, joins Rhino objects by `revit.uniqueId`, and projects BIM
relationships into the existing `networkx.MultiDiGraph` mirror as provenance-tagged nodes, edges,
and node annotations.

The result should make BIM facts available to agents, `scene_context`, graph export/stats, and
future reconciliation queries without feeding those facts into geometry inference.

### In scope

- New MCP scene tool:
  `scene_project_bim_relationships(sidecar_path, object_ids?, category_filters?, include_rooms=true, include_levels=true)`.
- New Python read-model projector module:
  `mcp_server/src/rook/scene/bim_relationship_projection.py`.
- Read-only scene sync and user-string hydration using the existing Rhino routes.
- Parsing the actual RookBIM preset sidecar shape:
  - `elements[].identity.uniqueId`
  - `elements[].identity.elementId`
  - top-level `category`, `family`, `type`, `name`
  - `elements[].labels.level`
  - `elements[].labels.hostId`
  - `elements[].labels.containingRoomId`
  - `rooms[]`
  - `relationships.hostMembership[]`
  - `relationships.roomMembership[]`
  - `relationships.levelMembership[]`
- Projection of:
  - `revit_hosted_by` edges between joined scene objects
  - `revit_in_room` edges from scene objects to BIM room reference nodes
  - `revit_on_level` edges from scene objects to BIM level reference nodes
  - minimal BIM/Revit annotations on joined Rhino object nodes
- Explicit provenance, projection ownership, graph sequence, sidecar identity, and diagnostics.
- Unit tests without Rhino for parsing/projection/pruning behavior, plus live-gated wiring tests.

### Out of scope

- Containment threshold tuning.
- Revit write-back.
- Calling Revit or Rhino.Inside.Revit.
- Mutating Rhino or Revit documents.
- Collapsing BIM facts into `contains_semantic`.
- Passing BIM labels or relationship data into `scene_exact_neighbors`,
  `scene_refine_containment`, or any geometry/inference route.
- Creating reference nodes for missing physical host elements.
- Group, assembly, curtain wall, phase, workset, design option, or linked-model projection beyond
  carrying available metadata as attributes where already present.

## 2. Design choice and alternatives

Three shapes were considered:

1. **Script/library only.** This matches calibration, but it would keep BIM facts outside the
   normal scene/NL surfaces and would undercut the goal of product substrate.
2. **MCP tool with pure projector core.** The tool handles scene sync and metadata hydration; the
   core accepts prepared runtime records and sidecar data for deterministic unit tests.
3. **Native or Rhino-document projection.** This would put BIM relationships closer to the source
   document, but it would create write/mutation semantics and blur read-model enrichment with Rhino
   document state.

v1 uses option 2. The public feature is a normal MCP scene tool. The durable logic lives in a
testable Python projector. The only mutation is in-memory enrichment of the Python
`networkx.MultiDiGraph` mirror.

## 3. Tool contract

### MCP tool

```text
scene_project_bim_relationships(
  sidecar_path: string,
  object_ids?: string[],
  category_filters?: string[],
  include_rooms: bool = true,
  include_levels: bool = true,
  port?: int
)
```

The tool belongs with scene/Rhino-read tools. It requires Rhino because it syncs and reads current
scene object user strings, but it must be targeted as read-only with an explicit note:

**This performs a read-model mutation only. It enriches the in-memory Python scene graph mirror. It
does not mutate Rhino or Revit documents.**

### Tool flow

1. `analytics.sync(port)` to refresh the `SceneGraphAnalytics` mirror.
2. Determine candidate object ids from the mirror and input filters.
3. Hydrate candidate object user strings with read-only `/usertext/object-get`.
4. Extract `revit.uniqueId`, `revit.elementId`, and `revit.category`.
5. Parse and validate the sidecar.
6. Join candidate scene objects to sidecar elements by `revit.uniqueId`.
7. Prune prior projector-owned BIM artifacts if needed.
8. Annotate joined scene nodes.
9. Project host, room, and level relationship facts.
10. Return counts, diagnostics, samples, and prune/upsert status.

Hydration failures are per-object diagnostics. They do not fail the whole tool unless zero objects
can be joined after hydration and sidecar parsing.

### Candidate filtering semantics

Filtering must be exact and predictable:

- If `object_ids` is supplied, only those scene ids are eligible as primary projected objects.
- `category_filters` further narrows eligible objects by hydrated `revit.category`. After a
  successful join, the sidecar element category may be used to confirm the same filter comparison.
- Category filters are case-insensitive and compare canonical display strings after trimming.
- If neither `object_ids` nor `category_filters` is supplied, all joinable scene objects are
  eligible.
- Room and level reference nodes are created only as needed for eligible objects.
- Host edge semantics are intentionally asymmetric:
  - the hosted element must be eligible;
  - the host object must be present and joined in the current scene graph;
  - the host object does not need to be included in `object_ids`.

That host rule makes focused questions useful. Projecting a single door can still show its Revit
host wall if that wall is present in the scene, while partial exports do not invent absent wall
nodes.

## 4. Projection model

### Projector ownership

Every artifact created by this projector carries:

```json
{
  "provenance": "rookbim_sidecar",
  "projectionKind": "bim_relationship_v1",
  "sidecarFingerprint": "...",
  "sourceSidecarPath": "...",
  "graphSequence": 123,
  "engineVersion": 1
}
```

Pruning must use projector ownership, not just `provenance`. The implementation should remove only
artifacts with `projectionKind == "bim_relationship_v1"` or deterministic `rookbim:` keys owned by
this projector. This avoids deleting unrelated future BIM projections.

### Joined Rhino object annotations

Joined scene object nodes receive minimal namespaced attributes:

```json
{
  "rookbimJoined": true,
  "rookbimSidecarFingerprint": "...",
  "rookbimSidecarPath": "...",
  "revitUniqueId": "...",
  "revitElementId": "...",
  "revitCategory": "...",
  "revitFamily": "...",
  "revitType": "...",
  "revitName": "...",
  "revitLevel": "..."
}
```

These attributes must never overwrite existing geometric/classification fields such as `shape_class`,
`domain_label`, dimensions, bbox fields, or existing scene provenance. They are pruned with the same
lifecycle as the projected BIM edges and reference nodes.

Raw `revitRoomUniqueId` or `revitHostUniqueId` may be included only as debugging attributes if they
are directly available. Relationship semantics should come from `revit_in_room` and
`revit_hosted_by` edges.

### Host membership

For each valid `relationships.hostMembership[]` fact:

- Source sidecar field: `elementUniqueId`.
- Target sidecar field: `hostUniqueId`.
- Project only if the hosted element is eligible and joined.
- Project only if the host element is present and joined in the current scene graph.
- Add a directed edge from hosted object to host object:

```json
{
  "relationship": "revit_hosted_by",
  "provenance": "rookbim_sidecar",
  "projectionKind": "bim_relationship_v1",
  "sourceRevitUniqueId": "...",
  "targetRevitUniqueId": "...",
  "source": "revit_api",
  "confidence": "high"
}
```

No inverse `revit_hosts` edge is stored in v1. Context rendering and graph queries can derive inverse
wording from incoming edges.

Skipped host facts are reported separately:

- `skippedHostMissingHostedObject`
- `skippedHostMissingHostObject`
- `skippedHostBothMissing`

Samples should include Revit unique ids and available categories.

### Room membership

For each valid `relationships.roomMembership[]` fact where `elementUniqueId` is eligible and joined:

- Create or reuse a sidecar-scoped room reference node.
- Add a directed edge from scene object to room node with relationship `revit_in_room`.

Room node id:

```text
rookbim:<sidecarFingerprint>:room:<roomUniqueId>
```

Complete room nodes are built from `rooms[]`:

```json
{
  "nodeKind": "rookbim_room",
  "provenance": "rookbim_sidecar",
  "projectionKind": "bim_relationship_v1",
  "sidecarFingerprint": "...",
  "sourceSidecarPath": "...",
  "roomUniqueId": "...",
  "roomNumber": "101",
  "roomName": "Office",
  "displayName": "101 Office",
  "recordCompleteness": "complete",
  "graphSequence": 123
}
```

If `roomMembership` references a `roomUniqueId` missing from `rooms[]`, v1 creates a sparse room
node instead:

```json
{
  "nodeKind": "rookbim_room",
  "roomUniqueId": "...",
  "displayName": "Room <short id>",
  "recordCompleteness": "sparse",
  "diagnostics": ["roomReferenceMissingRecord"]
}
```

Sparse room creation is a soft diagnostic, not a hard failure. If `include_rooms=false`, no room
nodes or `revit_in_room` edges are created, and skipped room fact counts are returned.

### Level membership

The current sidecar has no separate level table, so `relationships.levelMembership[]` is the source
record. For each valid fact where `elementUniqueId` is eligible and joined:

- Create or reuse a sidecar-scoped level reference node.
- Add a directed edge from scene object to level node with relationship `revit_on_level`.

Level node id:

```text
rookbim:<sidecarFingerprint>:level:<normalizedLevelName>
```

Level node attributes:

```json
{
  "nodeKind": "rookbim_level",
  "provenance": "rookbim_sidecar",
  "projectionKind": "bim_relationship_v1",
  "sidecarFingerprint": "...",
  "sourceSidecarPath": "...",
  "levelName": "L1 - Block 35",
  "displayName": "L1 - Block 35",
  "recordCompleteness": "membership_only",
  "graphSequence": 123
}
```

Level names are normalized only for the id segment. The raw level name is preserved as an attribute.
If `include_levels=false`, no level nodes or `revit_on_level` edges are created, and skipped level
fact counts are returned.

## 5. Sidecar identity and idempotency

Reference node ids and projection identity must be scoped by sidecar identity. Room numbers, level
names, and Revit unique ids are not globally stable across documents, exports, phases, or model
versions.

v1 sidecar fingerprint:

- Prefer a durable export id if a future sidecar provides one.
- For the current sidecar shape, compute a content hash of the sidecar file bytes and use a short,
  filesystem-safe prefix for node ids.
- Store the full hash or full fingerprint in attributes and response data.

The idempotent projection identity should include:

- graph sequence
- sidecar fingerprint
- selected object ids or `all`
- category filters
- `include_rooms`
- `include_levels`
- engine version

Projection is explicit and lazy. It runs only when `scene_project_bim_relationships` is called.

On graph sequence advance or sidecar fingerprint change, prune this projector's prior artifacts:

- `revit_hosted_by`, `revit_in_room`, and `revit_on_level` edges with
  `projectionKind="bim_relationship_v1"`.
- Room/level reference nodes with `projectionKind="bim_relationship_v1"` and no remaining non-owned
  edges.
- Joined-node annotations added by this projector.

Pruning should return counts and `pruned=true|false`.

v1 does not maintain a value cache. Projection should instead be an idempotent upsert into the
Python mirror: repeated calls with the same graph sequence, sidecar fingerprint, and filters replace
or update the same deterministic nodes and edges, rather than appending duplicates. A future cache
can be added only with explicit invalidation rules.

### Deterministic edge keys

Because the scene mirror is a `networkx.MultiDiGraph`, BIM edges must use deterministic keys so
repeated projection calls are idempotent:

```text
rookbim:hosted_by:<sidecarFingerprint>:<elementUid>:<hostUid>
rookbim:in_room:<sidecarFingerprint>:<elementUid>:<roomUid>
rookbim:on_level:<sidecarFingerprint>:<elementUid>:<levelId>
```

`levelId` is the normalized level-name id segment used for the level reference node. These keys are
also the preferred pruning handles for projector-owned edges.

## 6. Validation and diagnostics

### Hard failures

The tool fails before projection when:

- `sidecar_path` is missing, unreadable, or not a file.
- Sidecar JSON is invalid.
- `elements` is missing or is not a list.
- `relationships` is missing or is not an object.
- `relationships.hostMembership` is missing.
- `relationships.roomMembership` is missing when `include_rooms=true`.
- `relationships.levelMembership` is missing when `include_levels=true`.
- No scene objects join by `revit.uniqueId` after hydration and filtering.

### Soft skips

Malformed or incomplete records are skipped with counts and samples:

- malformed membership record
- missing `elementUniqueId`
- missing host, room, or level target
- relationship references an element not in `elements`
- relationship endpoint not present in the current scene graph
- object missing `revit.uniqueId`
- object user-string hydration failed
- room reference missing from `rooms[]`

Response diagnostics should be structured, for example:

```json
{
  "diagnostics": {
    "objectsMissingRevitUniqueId": 12,
    "hydrationFailed": 1,
    "malformedHostRecords": 3,
    "hostTargetNotInScene": 42,
    "roomReferenceMissingRecord": 5
  },
  "diagnosticSamples": {
    "hostTargetNotInScene": [
      {
        "elementUniqueId": "...",
        "hostUniqueId": "...",
        "elementCategory": "Doors",
        "hostCategory": "Walls"
      }
    ]
  }
}
```

Samples should be bounded so large models do not produce noisy responses.

## 7. Response shape

The tool should return a structured payload:

```json
{
  "success": true,
  "projectionKind": "bim_relationship_v1",
  "provenance": "rookbim_sidecar",
  "graphSequence": 123,
  "sidecarPath": "C:/...",
  "sidecarFingerprint": "...",
  "pruned": true,
  "upserted": true,
  "counts": {
    "candidateObjectCount": 2912,
    "hydratedCount": 2912,
    "joinableCount": 2912,
    "eligibleObjectCount": 50,
    "joinedObjectCount": 50,
    "annotatedObjectCount": 50,
    "projectedHostEdges": 12,
    "projectedRoomEdges": 4,
    "projectedLevelEdges": 50,
    "roomNodes": 4,
    "levelNodes": 6,
    "skippedHostMissingHostedObject": 0,
    "skippedHostMissingHostObject": 38,
    "skippedHostBothMissing": 0
  },
  "diagnostics": {},
  "samples": {}
}
```

These field names are the v1 response contract unless implementation discovers an existing local
naming convention that would make one field inconsistent with neighboring scene tools. Any such
rename must preserve the semantic groups: identity, prune/upsert status, counts, diagnostics, and
bounded samples.

## 8. Scene context and graph surfaces

`SceneGraphAnalytics` already stores parallel relationships in a `networkx.MultiDiGraph`, so BIM
edges can coexist with bbox edges, OCCT exact adjacency, and semantic containment. v1 should update
context formatting so BIM relationships are readable instead of raw machine labels.

Forward examples:

- `Hosted by Revit: WALL "Exterior - 13 5/8 ..."`
- `In Revit room: ROOM "101 Office"`
- `On Revit level: LEVEL "L1 - Block 35"`

Inverse examples:

- `Revit host for: DOOR "Single-Flush [312044]"`
- `Contains Revit room member: FURNITURE "..."`
- `Has Revit level member: WALL "..."`

Edge details may include sidecar provenance and confidence where concise. `scene_stats` should count
the new relationship types naturally through existing relationship counting. `export_json` should
include node/edge metadata through existing metadata export.

The existing native `scene_query` route queries the native graph, not the enriched Python mirror. v1
does not need to retrofit that native route. It should make the facts available through Python mirror
surfaces now (`scene_context`, `scene_stats`, `export_json`) and leave a Python-side query tool or
native sync strategy for a later slice if needed.

## 9. Invariants

- BIM relationship projection never mutates Rhino or Revit documents.
- BIM relationship projection never calls Revit or Rhino.Inside.Revit.
- BIM sidecar facts are never passed into `scene_exact_neighbors`, `scene_refine_containment`, or
  geometry inference code.
- `provenance="occt"` exact adjacency, `provenance="semantic_refiner"` containment, and
  `provenance="rookbim_sidecar"` BIM facts remain separate.
- `contains_semantic` is not created, modified, boosted, or suppressed by this projector.
- Host facts connect only present scene objects in v1.
- Room and level facts use non-geometric reference nodes and are sidecar-scoped.
- Projector pruning removes only artifacts owned by `projectionKind="bim_relationship_v1"`.

## 10. Testing

### Pure unit tests

No Rhino required:

- Parse the actual #263 sidecar shape with nested `identity` and `labels`.
- Validate required sidecar sections and hard failure cases.
- Build element, room, host, room, and level lookup maps from relationship lists.
- Join prepared runtime records by `revit.uniqueId`.
- Apply `object_ids` and `category_filters` exactly as specified.
- Annotate joined nodes without overwriting geometric/classification fields.
- Project host edges only when hosted element is eligible and host object is joined.
- Create complete and sparse room nodes.
- Create membership-only level nodes from `levelMembership`.
- Skip disabled room/level projection and report skipped counts.
- Prune only `projectionKind="bim_relationship_v1"` artifacts.
- Verify idempotent repeated projection for the same graph sequence and sidecar fingerprint.
- Guard that the projector module imports no refiner/projector routes and never calls
  `scene_exact_neighbors`, `scene_refine_containment`, or mutating Rhino/Revit routes.

### MCP/registration tests

- Tool schema exists with `sidecar_path`, `object_ids`, `category_filters`, `include_rooms`,
  `include_levels`, and optional `port`.
- Dispatch calls the BIM relationship projector and returns its structured payload.
- Tool group includes it with scene graph tools.
- Targeting classifies it as Rhino-read/scene-read, with an explicit read-model mutation note, not
  as a Rhino/Revit document mutation tool.

### Live gate

The live gate is for wiring, not algorithm tuning:

1. Open or import an existing RookBIM preset `.3dm` in a fresh/isolated Rhino document.
2. Call `scene_graph` to establish a graph sequence.
3. Call `scene_project_bim_relationships` with the matching sidecar.
4. Verify joined object count is nonzero.
5. Verify projected host, room, and level counts reconcile with eligible sidecar facts.
6. Call `scene_context` on representative objects and confirm readable BIM host/room/level lines.
7. Confirm no Rhino/Revit document mutation occurred.

If live Rhino is unavailable, unit and registration tests can pass, but the PR remains live-gated
until this wiring check runs.

## 11. Implementation sequencing for the plan

The implementation plan should keep the pure core ahead of live wiring:

1. Sidecar parser and fixture-shape tests.
2. Pure projection model and lookup/join utilities.
3. NetworkX projection/prune behavior with unit tests.
4. Context formatting for BIM relationships.
5. MCP tool schema, dispatch, tool group, and targeting.
6. Tool-boundary hydration via `/usertext/object-get`.
7. Live gate script or documented live test steps.

This order keeps the slice from becoming a Rhino debugging loop before the data model and invariants
are locked.
