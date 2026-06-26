# Relationship Fact Projection v1 - design

> Status (2026-06-26): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/pearson-robot-feature-graph` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This slice is motivated by the Pearson robot `g002` feature graph experiment, but it is
> intentionally not robot-specific. It introduces a neutral relationship-fact projection model
> that can later accept facts authored from graph JSON, inferred from modeled Rhino geometry,
> imported from Revit/RIR, or produced by OCCT exact topology.

## 1. Reviewer backfill

Packaging/release work is happening separately from the clean `main` checkout. This design lives
in the dedicated Pearson worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/pearson-robot-feature-graph
```

Current committed robot experiment:

```text
experiments/pearson_robot_skeleton_graph/
```

The current robot graph is `assembly_graph.json` revision `g002`. It contains:

- 15 `nodes`;
- 14 `members`;
- 43 `features`;
- 28 authored `relationships`;
- formal vocabulary: `node`, `member`, `feature`, `relationship`, `pose`.

`g002` generated Rhino debug geometry for two poses:

- 30 joint objects;
- 28 member objects;
- 86 feature marker objects;
- 56 relationship marker objects.

Screenshot evidence:

```text
experiments/pearson_robot_skeleton_graph/screenshots/g002_feature_graph_plain.png
```

The core lesson from `g002`: feature-level graph semantics are useful, but marker geometry should
not become the semantic source of truth. The generic Rook scene graph sees the markers and ticks as
ordinary Rhino objects and produces noisy `near`, `intersects`, `contains`, and `supports` edges.
The next slice should project authored relationship facts into the Python scene-graph read model
as semantic edges.

This also connects to the earlier spatial-intelligence work:

```text
geometry/topology -> exact or inferred relationships -> projected graph -> agent-readable intelligence
```

The robot work adds the bidirectional design workflow:

```text
authored graph -> generated geometry
modeled geometry -> inferred graph
graph <-> geometry round-trip validation
```

This slice implements only the first controlled leg: authored relationship facts projected into
the existing Python scene graph. Geometry-first inference and round-trip validation are deferred.

## 2. Goal

Add a Python read-model projector that turns authored feature relationships already present in
Rhino object user strings into deterministic semantic edges in Rook's in-memory NetworkX scene
graph.

The first source mode is:

```text
sourceMode = "authored_graph_user_strings"
```

For the Pearson robot `g002` case, this means:

```text
relationship object references feature A/B
feature A belongs to member M
feature B belongs to node N
projected semantic edge is M -> N
edge preserves fromFeature=A and toFeature=B
```

The result should let an agent answer:

```text
Which member connects to this joint?
```

without relying on generic spatial `near` or `intersects` relationships.

### In scope

- New pure relationship-fact data model.
- New Python read-model projector module:
  `mcp_server/src/rook/scene/relationship_fact_projection.py`.
- New MCP scene tool:
  `scene_project_relationship_facts(...)`.
- Read-only Rhino object user-string hydration via `/usertext/object-get`.
- Projection of owner-object-to-owner-object semantic edges into
  `SceneGraphAnalytics.graph`.
- Idempotent edge upsert and projection-owned pruning.
- Context formatting for projected relationship facts.
- Unit tests for parsing, owner projection, idempotency, pruning, defaults, diagnostics, and
  formatting.

### Out of scope

- Geometry-first inference.
- OCCT exact-contact computation.
- Revit/RIR import.
- IFC import or IFC Lite integration.
- Native C++ scene graph changes.
- Rhino document mutation.
- Additional Rhino marker geometry.
- Whole-scene graph ontology redesign.
- Persisting projected facts into the Rhino file.

## 3. Design choice and alternatives

Three approaches were considered:

1. **Authored relationship projection first.** Project existing `g002` authored facts into the
   Python scene-graph read model. This is controlled, testable, and gives agents a semantic graph
   surface now.
2. **Geometry-first inference first.** Infer features and relationships from modeled geometry.
   This attacks the designer workflow directly, but it mixes discovery with representation before
   the fact model exists.
3. **Round-trip validation harness first.** Compare `graph -> geometry -> inferred graph` against
   `g002` ground truth. This is the right long-term framing but depends on both authored projection
   and at least a small inference path.

v1 uses option 1. The implementation should leave explicit extension points for options 2 and 3 by
keeping the core model neutral: `RelationshipFact`, not `AuthoredRelationship`.

## 4. Architecture

The slice follows the existing BIM relationship projection pattern:

```text
MCP tool
  -> analytics.sync()
  -> candidate scene node ids
  -> /usertext/object-get hydration
  -> parse feature + relationship records
  -> owner-object projection
  -> NetworkX edge upsert
  -> context/stats/query surfaces
```

The projector mutates only the Python read-model graph. It does not mutate Rhino, Revit, files,
blocks, layers, or object user strings.

Proposed module:

```text
mcp_server/src/rook/scene/relationship_fact_projection.py
```

Proposed constants:

```python
PROJECTION_KIND = "relationship_fact_v1"
DEFAULT_SOURCE_MODE = "authored_graph_user_strings"
DEFAULT_CONFIDENCE = 1.0
DEFAULT_STATUS = "accepted"
ENGINE_VERSION = 1
```

The module should be pure at the core. Hydration and tool orchestration may be async, but parsing
and projection should be unit-testable without Rhino.

## 5. Tool contract

New MCP tool:

```text
scene_project_relationship_facts(
  graph_source?: string,
  graph_revision?: string,
  poses?: string[],
  object_ids?: string[],
  source_mode?: "authored_graph_user_strings",
  strict?: bool = false,
  port?: int
)
```

Defaults:

- `graph_source`: if omitted, project all supported graph sources found in hydrated records.
  For the robot smoke, callers should pass `pearson_robot_skeleton_graph`.
- `graph_revision`: if omitted, accept all revisions for the chosen source. Revision is still
  stored on every projected edge.
- `poses`: if omitted, accept all poses.
- `source_mode`: `authored_graph_user_strings`.
- `strict`: `false`.

Lenient mode is the default. Malformed or incomplete records are skipped with diagnostics. Strict
mode fails the tool if any malformed relationship fact is encountered after candidate hydration.

The tool should be registered consistently with other scene tools:

- MCP tool schema in `server.py`;
- dispatch case in `server.py`;
- scene graph tool group in `mcp_server/src/rook/agent/tool_groups.py`;
- local agent-direct handler in `mcp_server/src/rook/agent/tool_dispatcher.py`;
- targeting/read-only classification alongside `scene_project_bim_relationships`.

## 6. User-string source model

The Python scene graph does not currently carry arbitrary Rhino object user strings, so the
projector must hydrate candidates with `/usertext/object-get`.

Candidate object ids come from `SceneGraphAnalytics.graph` after sync. The projector should narrow
hydration where possible:

- if `object_ids` are supplied, hydrate those plus any same-source feature and relationship marker
  objects needed to resolve facts;
- otherwise hydrate non-projection scene nodes and filter by `rook.graph.source`.

v1 reads these user-string records:

### Owner objects

Joint/member objects carry:

```text
rook.graph.source
rook.graph.revision
rook.graph.pose
rook.graph.visual_type = "joint" | "member"
rook.graph.node_id
rook.graph.member_id
rook.graph.feature_ids
rook.graph.relationship_ids
```

### Feature marker objects

Feature marker objects carry:

```text
rook.graph.source
rook.graph.revision
rook.graph.pose
rook.graph.visual_type = "feature"
rook.graph.feature_id
rook.graph.owner
rook.graph.owner_kind = "node" | "member"
rook.graph.feature_kind
rook.graph.role
rook.graph.true_position_m
rook.graph.visual_lift_m
```

### Relationship marker objects

Relationship marker objects carry:

```text
rook.graph.source
rook.graph.revision
rook.graph.pose
rook.graph.visual_type = "relationship"
rook.graph.relationship_id
rook.graph.relationship_type
rook.graph.from_feature
rook.graph.to_feature
rook.graph.contact_kind
rook.graph.provenance
rook.graph.from_feature_position_m
rook.graph.to_feature_position_m
rook.graph.marker_start_m
rook.graph.marker_end_m
rook.graph.visual_lift_m
```

The generator does not currently stamp `confidence`, `status`, or `sourceMode`. v1 defaults them:

```text
confidence = 1.0
status = "accepted"
sourceMode = "authored_graph_user_strings"
```

## 7. RelationshipFact model

Use a neutral fact model, even though v1 facts are authored:

```json
{
  "id": "spine_base_to_spine_top.start_connects_spine_base",
  "type": "connects",
  "fromFeature": "spine_base_to_spine_top.start",
  "toFeature": "spine_base.point",
  "fromOwner": "spine_base_to_spine_top",
  "fromOwnerKind": "member",
  "fromOwnerObjectId": "<member object id>",
  "fromFeatureObjectId": "<feature marker object id>",
  "toOwner": "spine_base",
  "toOwnerKind": "node",
  "toOwnerObjectId": "<joint object id>",
  "toFeatureObjectId": "<feature marker object id>",
  "contactKind": "point_to_point",
  "provenance": "authored_assembly_graph",
  "confidence": 1.0,
  "status": "accepted",
  "sourceMode": "authored_graph_user_strings",
  "graphSource": "pearson_robot_skeleton_graph",
  "graphRevision": "g002",
  "pose": "reclined_robot"
}
```

Future geometry inference should emit the same model with different values, for example:

```json
{
  "provenance": "inferred_from_geometry",
  "confidence": 0.74,
  "status": "candidate"
}
```

## 8. Projection model

Projected graph endpoints are owner objects, not marker objects.

For `g002`:

```text
feature A belongs to member M
feature B belongs to node N
relationship A connects B
project edge M -> N
```

The feature marker object ids are preserved as edge metadata. They are not the primary endpoints.

Projected edge attributes:

```json
{
  "relationship": "connects",
  "projectionKind": "relationship_fact_v1",
  "semanticRelationshipType": "connects",
  "provenance": "authored_assembly_graph",
  "confidence": 1.0,
  "status": "accepted",
  "sourceMode": "authored_graph_user_strings",
  "contactKind": "point_to_point",
  "graphSource": "pearson_robot_skeleton_graph",
  "graphRevision": "g002",
  "pose": "reclined_robot",
  "relationshipFactId": "spine_base_to_spine_top.start_connects_spine_base",
  "fromFeature": "spine_base_to_spine_top.start",
  "toFeature": "spine_base.point",
  "fromFeatureObjectId": "<optional feature marker id>",
  "toFeatureObjectId": "<optional feature marker id>",
  "relationshipObjectId": "<relationship marker id>",
  "engineVersion": 1
}
```

Do not use `authored_connects` as the relationship name. The relationship name remains
`connects`; provenance and status disambiguate authored, inferred, imported, and exact facts.

Deterministic edge key:

```text
relationship_fact:<sourceMode>:<graphSource>:<graphRevision>:<pose>:<relationshipFactId>
```

If two facts share an id across poses or revisions, the edge key remains distinct because pose and
revision are part of the key. Repeated projection updates the same edge instead of appending
parallel duplicates.

## 9. Pruning and idempotency

Projection artifacts are owned by:

```text
projectionKind = "relationship_fact_v1"
```

Pruning should remove only this projector's edges. It must not delete:

- native approximate spatial edges;
- `adjacent_exact`;
- `contains_semantic`;
- BIM projection edges;
- Rhino objects or user strings.

The tool should prune stale relationship-fact edges before projection when:

- graph sequence changes from the stored projection sequence;
- projected graph source/revision/pose no longer matches the current request scope;
- source mode or engine version changes.

The response should include prune counts:

```json
{
  "prune": {
    "pruned": true,
    "removedEdges": 28
  }
}
```

Every graph mutation must invalidate `SceneGraphAnalytics` cached centrality/community/path
results, matching the existing projection/refinement pattern.

## 10. Diagnostics and strict mode

Malformed or incomplete facts are skipped in lenient mode.

Skip diagnostics should include bounded samples for:

- relationship object missing `relationship_id`;
- relationship object missing `relationship_type`;
- relationship object missing `from_feature` or `to_feature`;
- feature id not found for relationship endpoint;
- feature owner object not found;
- owner object not found in current scene graph;
- unsupported source mode;
- unsupported or empty graph source after filtering;
- duplicate feature records for the same `(graphSource, revision, pose, feature_id)`;
- duplicate owner records for the same `(graphSource, revision, pose, owner_kind, owner_id)`.

Hard failures:

- invalid tool arguments;
- unsupported `source_mode`;
- no current scene graph after sync;
- strict mode plus any malformed fact after candidate hydration.

No eligible facts in lenient mode is not a crash. Return `success: true` with zero projected edges
and diagnostics unless the caller explicitly asked for strict behavior.

## 11. Response shape

The tool should return a structured payload:

```json
{
  "success": true,
  "projectionKind": "relationship_fact_v1",
  "sourceMode": "authored_graph_user_strings",
  "graphSequence": 123,
  "counts": {
    "candidateObjectCount": 200,
    "hydratedObjectCount": 200,
    "ownerObjectCount": 58,
    "featureObjectCount": 86,
    "relationshipObjectCount": 56,
    "relationshipFactCount": 56,
    "projectedEdgeCount": 56,
    "skippedFactCount": 0
  },
  "byRelationshipType": {
    "connects": 56
  },
  "byPose": {
    "rest_t_pose": 28,
    "reclined_robot": 28
  },
  "diagnostics": {},
  "samples": {},
  "prune": {
    "pruned": false,
    "removedEdges": 0
  }
}
```

The response counts relationship facts per pose. For the Pearson `g002` Rhino document, the graph
JSON has 28 authored relationships and two poses, so a successful full projection should create 56
semantic edges.

## 12. Scene context and query surfaces

`scene_context(sync=false)` should be able to render projected facts after projection, just as BIM
projection requires `sync=false` to preserve Python-only enrichment.

Forward display example:

```text
connects: MEMBER "member_reclined_robot_spine_base_to_spine_top" -> JOINT "joint_reclined_robot_spine_base"
  via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted, authored_assembly_graph
```

Inverse display example:

```text
connected by: MEMBER "member_reclined_robot_spine_base_to_spine_top"
  via spine_base_to_spine_top.start -> spine_base.point
```

`scene_stats` should count `connects` edges naturally through existing relationship counting.

v1 does not need a separate query tool if `scene_context`, `scene_stats`, and graph export provide
enough visibility. If implementation discovers that context output becomes too noisy, add a small
read-only query tool in the plan:

```text
scene_relationship_facts(mode="object_context" | "relationship_scan", ...)
```

but do not require it for the first implementation unless tests or live use show the need.

## 13. Testing

Pure tests should carry most of the confidence.

Required pure tests:

- Parse valid `g002`-style owner, feature, and relationship user strings.
- Default missing `confidence`, `status`, and `sourceMode` to `1.0`, `accepted`, and
  `authored_graph_user_strings`.
- Owner projection:
  - relationship object references feature A/B;
  - feature A belongs to member M;
  - feature B belongs to node N;
  - projected edge is M -> N with `fromFeature=A` and `toFeature=B`.
- Idempotency: repeated projection creates one deterministic edge per fact, not duplicates.
- Pose separation: same relationship id in two poses creates two distinct projected edges.
- Revision separation: same relationship id in different revisions remains distinct.
- Stale projection pruning removes only `projectionKind="relationship_fact_v1"` edges.
- Lenient malformed fact handling skips bad facts with diagnostics.
- Strict malformed fact handling fails the tool.
- Missing feature endpoint is diagnostic, not a crash in lenient mode.
- Missing owner object is diagnostic, not a crash in lenient mode.
- Projection does not mutate Rhino or call mutating Rhino routes.
- Context formatting includes relationship type, owner objects, feature ids, contact kind,
  provenance, confidence, and status.
- Tool registration exists in MCP schema, dispatch, tool groups, local dispatcher, and targeting.

Live/manual gate:

1. Open the Rhino document containing the Pearson `g002` generated skeleton graph.
2. Run `scene_project_relationship_facts(graph_source="pearson_robot_skeleton_graph")`.
3. Expect 56 projected `connects` edges if both poses are present.
4. Run `scene_context(sync=false)` for a sample member and joint.
5. Confirm context reports semantic `connects` facts without relying on generic `near` edges.
6. Re-run projection and confirm idempotent counts.
7. Confirm no Rhino document mutation occurred.

## 14. Extension path

This slice should make later designer workflows easier, not harder.

Future geometry-first inference can emit:

```json
{
  "provenance": "inferred_from_geometry",
  "confidence": 0.74,
  "status": "candidate"
}
```

Future OCCT projection can emit:

```json
{
  "provenance": "exact_from_occt",
  "confidence": 1.0,
  "status": "accepted",
  "evidence": {
    "sharedArea": 0.42,
    "areaUnit": "meters^2"
  }
}
```

Future Revit/RIR projection can either continue using BIM-specific edges where useful, or map
selected facts into the neutral `RelationshipFact` model when the agent needs a unified graph
query surface.

Future round-trip validation can compare:

```text
authored accepted relationship facts
against
inferred candidate relationship facts
```

without changing the projected graph contract.

## 15. Implementation sequence for the plan

The implementation plan should keep pure parsing/projection ahead of live Rhino work:

1. Define dataclasses/constants and pure parse functions.
2. Unit-test `g002`-style user-string records.
3. Implement owner-object projection into a fake NetworkX graph.
4. Implement idempotent edge keys and pruning.
5. Add context formatting for `relationship_fact_v1` edges.
6. Add MCP schema, dispatch, tool group, local dispatcher, and targeting.
7. Add hydration orchestration using `/usertext/object-get`.
8. Add live/manual smoke script or documented live gate.

This keeps the slice from becoming a Rhino debugging loop before the data model and graph
semantics are locked.
