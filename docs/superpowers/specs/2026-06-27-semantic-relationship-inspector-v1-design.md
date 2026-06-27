# Semantic Relationship Inspector v1 - design

> Status (2026-06-27): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/semantic-relationship-inspector-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen Pearson `g002` scale-gate branch. Do not add more work to
> `codex/pearson-robot-g002-roundtrip-gate` unless review feedback requires it.

## 1. Reviewer backfill

This work is in the isolated Pearson worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/semantic-relationship-inspector-v1
```

Immediate stack base:

```text
e63470ea docs: document Pearson g002 scale gate
```

The stack below this branch already proves:

- authored relationship facts can be projected from Rhino object user text into the Python
  `SceneGraphAnalytics.graph`;
- projection creates owner-object-to-owner-object `relationship_fact_v1` edges;
- feature endpoints remain edge metadata through `fromFeature` and `toFeature`;
- the five-object smoke fixture passes the full round-trip path;
- Pearson `g002` passes the full live scale gate with 56 projected facts across two poses;
- `scene_context(sync=false)` can render relationship-fact prose, but it is a secondary readable
  surface, not a structured query contract.

The current generic scenegraph display remains centered on fuzzy spatial relationships such as
adjacency, containment, proximity, and other heuristic observations. Those edges answer a different
question than authored semantic facts.

The desired conceptual separation is:

```text
same scene object nodes
  spatial/fuzzy edges: near, adjacent, contains, overlaps
  semantic fact edges: connects, attached_to, supports, bounds, hosts
```

Semantic facts should be inspectable without visually or semantically mixing them with fuzzy
spatial edges.

## 2. Goal

Add a v1 object-centric semantic relationship inspector over already-projected relationship facts.

The tool should answer:

```text
Given these selected object ids, what semantic relationship facts touch them?
```

The primary output is structured JSON. Readable lines are secondary convenience text for agents and
future display surfaces.

## 3. Non-goals

This slice must not:

- mutate Rhino geometry, attributes, layers, blocks, or document state;
- create overlay geometry or visual glyphs;
- infer relationships from geometry;
- call `scene_project_relationship_facts` automatically;
- call `sync` or refresh the scene graph mirror;
- include fuzzy spatial edges such as `near`, `adjacent`, `contains`, or `overlaps`;
- add a whole-graph dump mode;
- change `scene_context` rendering.

The inspector reads the current in-memory Python scene graph only. Projection is a separate
explicit step.

## 4. Tool surface

Add a read-only MCP/local tool:

```text
scene_semantic_relationships
```

Input:

```text
object_ids: list[str] required
graph_source?: string
graph_revision?: string
poses?: list[str]
relationship_types?: list[str]
status?: list[str]
provenance?: list[str]
direction?: "both" | "outgoing" | "incoming"
```

There is intentionally no `sync` parameter in v1.

There is intentionally no `project_first` parameter in v1.

`object_ids` is required and must be non-empty. Missing or empty `object_ids` should return:

```json
{
  "success": false,
  "error": "missing_object_ids",
  "message": "scene_semantic_relationships requires object_ids in v1"
}
```

## 5. Edge scope

The inspector must only read edges where:

```text
projectionKind == "relationship_fact_v1"
```

It should ignore every other edge in the graph, including generic spatial/fuzzy edges and BIM
projection edges.

The inspector should preserve these relationship-fact fields:

```text
relationship
semanticRelationshipType
relationshipFactId
fromFeature
toFeature
contactKind
provenance
confidence
status
sourceMode
graphSource
graphRevision
pose
relationshipObjectId
fromFeatureObjectId
toFeatureObjectId
engineVersion
```

The response fact may omit fields that are absent from the edge, but it must not rename the core
contract fields:

```text
relationship
fromFeature
toFeature
contactKind
provenance
confidence
status
graphSource
graphRevision
pose
```

## 6. Object-centric response

Response shape:

```json
{
  "success": true,
  "projectionKind": "relationship_fact_v1",
  "counts": {
    "requestedObjectCount": 3,
    "existingSelectedObjectCount": 2,
    "missingSelectedObjectCount": 1,
    "relationshipFactCount": 3,
    "relationshipViewCount": 4
  },
  "objects": [
    {
      "objectId": "requested-id",
      "exists": false,
      "name": null,
      "facts": [],
      "lines": []
    },
    {
      "objectId": "selected-id",
      "exists": true,
      "name": "spine_base",
      "facts": [
        {
          "direction": "incoming",
          "relationship": "connects",
          "objectId": "selected-id",
          "otherObjectId": "member-id",
          "otherName": "spine_base_to_spine_top",
          "fromFeature": "spine_base_to_spine_top.start",
          "toFeature": "spine_base.point",
          "contactKind": "point_to_point",
          "provenance": "authored_assembly_graph",
          "confidence": 1.0,
          "status": "accepted",
          "graphSource": "pearson_robot_skeleton_graph",
          "graphRevision": "g002",
          "pose": "reclined_robot"
        }
      ],
      "lines": [
        "connected by spine_base_to_spine_top via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted"
      ]
    }
  ],
  "diagnostics": {}
}
```

Object entries must preserve requested `object_ids` order. Duplicate requested ids should be
deduplicated for response entries while preserving first occurrence order.

If both endpoints of the same relationship fact are selected, both selected object entries should
include a directional view of the same underlying fact:

- edge source selected: `direction == "outgoing"`;
- edge target selected: `direction == "incoming"`.

This duplication is intentional because the inspector is object-centric.

Count semantics must distinguish unique relationship facts from emitted object-local views:

- `relationshipFactCount` counts unique projected relationship-fact edges that match the filters
  and touch at least one requested existing object.
- `relationshipViewCount` counts emitted fact entries across all returned object entries.

When both endpoints of one underlying edge are selected, `relationshipFactCount` increases by `1`
and `relationshipViewCount` increases by `2`.

## 7. Missing and empty cases

Missing selected objects should not fail the whole call. Include each missing selected object:

```json
{
  "objectId": "missing-id",
  "exists": false,
  "name": null,
  "facts": [],
  "lines": []
}
```

Diagnostics should include:

```json
{
  "missingSelectedObjects": 1
}
```

If no `relationship_fact_v1` edges exist anywhere in the current graph, return success with empty
facts and:

```json
{
  "noProjectedRelationshipFacts": 1,
  "projectionRequired": 1
}
```

If projected relationship facts exist, but none touch the requested object ids after filters, return
success with:

```json
{
  "noFactsForSelectedObjects": 1
}
```

These diagnostics are additive. A mixed selection may have both `missingSelectedObjects` and
`noFactsForSelectedObjects`.

## 8. Filtering

Filters apply to relationship facts before object grouping:

- `graph_source` matches `graphSource`;
- `graph_revision` matches `graphRevision`;
- `poses` matches `pose`;
- `relationship_types` matches `semanticRelationshipType` when present, otherwise `relationship`;
- `status` matches `status`;
- `provenance` matches `provenance`;
- `direction` filters relative to each selected object.

`direction` defaults to:

```text
both
```

Allowed values:

```text
both
outgoing
incoming
```

Invalid direction should return:

```json
{
  "success": false,
  "error": "invalid_direction",
  "message": "direction must be one of: both, outgoing, incoming"
}
```

Filter diagnostics may include counts when useful:

```text
filteredByGraphSource
filteredByGraphRevision
filteredByPose
filteredByRelationshipType
filteredByStatus
filteredByProvenance
filteredByDirection
```

Filter diagnostics should not make the response a failure.

## 9. Readable lines

Readable `lines` are secondary. They should be compact and should not be treated as the source of
truth.

For outgoing facts:

```text
connects spine_base via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted
```

For incoming facts:

```text
connected by spine_base_to_spine_top via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted
```

Include `provenance` in the line when present:

```text
connects spine_base via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted, authored_assembly_graph
```

Do not rely on line formatting in tests beyond high-signal substrings.

## 10. Implementation placement

Add a focused Python module:

```text
mcp_server/src/rook/scene/semantic_relationship_inspector.py
```

This module should own:

- request validation;
- relationship-fact edge extraction;
- filtering;
- object grouping;
- diagnostics;
- response shaping.

Shared MCP surfaces should remain thin registration/dispatch seams:

- `mcp_server/src/rook/server.py`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
- `mcp_server/src/rook/agent/tool_groups.py`
- `mcp_server/src/rook/targeting.py`

Do not put business logic in those shared surface files.

## 11. Tool policy

The tool is read-only. It does not require a live Rhino call because it inspects the current Python
scene graph mirror and does not sync.

Targeting policy should be:

```text
requires_rhino = false
risk = "read"
```

This differs from `scene_project_relationship_facts`, which requires Rhino because it hydrates
object user text from Rhino.

## 12. Tests

Pure tests should cover:

- missing/empty `object_ids` fails with `missing_object_ids`;
- invalid `direction` fails with `invalid_direction`;
- only `projectionKind == "relationship_fact_v1"` edges are included;
- fuzzy spatial edges are ignored;
- missing selected objects are included with `exists: false`;
- existing selected objects with no facts are included with `exists: true`;
- response object order follows first occurrence in input `object_ids`;
- outgoing and incoming direction are relative to the selected object;
- selecting both endpoints duplicates the same fact into both object entries and reports
  `relationshipFactCount == 1` with `relationshipViewCount == 2`;
- filters for graph source, revision, pose, relationship type, status, and provenance;
- empty graph diagnostics distinguish `noProjectedRelationshipFacts` from
  `noFactsForSelectedObjects`.

Tool surface tests should cover:

- MCP schema exposes required `object_ids` and optional filters;
- local dispatcher registers `scene_semantic_relationships`;
- tool group includes `scene_semantic_relationships`;
- targeting policy is read-only and does not require Rhino;
- `_call_tool_dispatch("scene_semantic_relationships", ...)` returns the public payload shape;
- dispatch path does not call `sync`.

Live tests are optional for v1 because the Pearson scale gate already proves projection. If added,
they should:

- create the five-object smoke fixture;
- run `scene_project_relationship_facts`;
- call `scene_semantic_relationships` for the two owner ids;
- assert structured fact fields and high-signal line substrings.

Pearson `g002` should remain optional for this slice. A non-live unit test can exercise scale-like
grouping with synthetic edges instead of requiring the full live Pearson fixture.

## 13. Success criteria

This slice is complete when:

- `scene_semantic_relationships` exists as a read-only object-centric inspector;
- missing `object_ids` fails clearly;
- valid mixed selections preserve missing objects, existing empty objects, and fact-bearing
  objects;
- only `relationship_fact_v1` edges appear in responses;
- no sync, projection, inference, Rhino mutation, or overlay geometry is added;
- structured facts are authoritative and readable lines are secondary;
- focused pure and dispatch tests pass.

## 14. Future slices

Later slices can build on this read model:

- a semantic scenegraph display mode that consumes `scene_semantic_relationships`;
- context formatting improvements that include source/revision/pose when useful;
- Rhino overlay/glyph display for accepted and candidate facts;
- geometry-to-fact candidate inference that emits the same fact shape with
  `status="candidate"`;
- whole-graph semantic summaries or graph-wide query mode with explicit scope controls.

Those are intentionally deferred until the object-centric inspector contract is stable.
