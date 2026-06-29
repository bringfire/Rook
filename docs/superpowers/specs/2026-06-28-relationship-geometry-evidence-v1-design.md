# Relationship Geometry Evidence v1 - design

> Status (2026-06-28): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/relationship-geometry-evidence-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen `codex/authored-graph-schema-v2` slice. Do not add more work
> to `codex/authored-graph-schema-v2` unless review feedback requires it.

## 1. Reviewer backfill

The graph work now has a tested semantic relationship substrate:

- Authored Graph Schema v2 defines domain-neutral typed records:
  `object`, `feature`, `relationship`, `relationship_type`, `contact_kind`, `provenance`,
  `confidence`, and `status`.
- `scene_project_relationship_facts` hydrates `rook.graph.*` Rhino object user text and projects
  owner-object-to-owner-object `relationship_fact_v1` edges into `SceneGraphAnalytics.graph`.
- Projected edges preserve feature marker object ids on the edge:
  `fromFeatureObjectId` and `toFeatureObjectId`.
- `scene_semantic_relationships` reads already-projected semantic facts from the current Python
  graph mirror.
- `scene_object_semantic_context` builds bounded per-object cards over those facts.
- Relationship profiles provide labels, inverse labels, categories, and contact-kind display hints
  without changing fact truth.
- The architectural fixture and Pearson `g002` fixture both pass non-live and live Rhino gates.

The current abstraction is clean for authored fixtures. The next risk is whether semantic facts can
carry measured geometric support without jumping into inference. This slice adds that support signal.

## 2. Goal

Add a read-only relationship evidence query that measures simple feature-marker distance for
already-projected relationship facts.

The tool should answer:

```text
Which projected relationship facts have measurable feature-position evidence, and is that evidence
within a requested tolerance?
```

The key stance is:

```text
evidence != truth
```

An authored fact can remain `status=accepted` because of its provenance/status while its geometry
evidence is missing, weak, or outside tolerance. This tool reports measured support; it does not
decide semantic truth.

## 3. Non-goals

This slice must not:

- infer new relationships;
- accept, reject, downgrade, or mutate relationship fact status;
- mutate Rhino geometry, layers, attributes, user text, document strings, or files;
- inspect owner Breps, curves, surfaces, meshes, blocks, or bounding boxes;
- run spatial adjacency heuristics;
- call `scene_project_relationship_facts` automatically;
- call scene graph `sync`;
- enrich object semantic context cards;
- add ontology, IFC, BOT, Brick, RDF, Revit, TopologicPy, or profile predicate behavior.

V1 measures only feature marker positions already stamped on Rhino feature marker objects.

## 4. Tool surface

Add a read-only MCP/local tool:

```text
scene_relationship_evidence
```

Input:

```text
object_ids?: list[str]
graph_source?: string
graph_revision?: string
poses?: list[str]
relationship_types?: list[str]
relationship_fact_ids?: list[str]
tolerance_m?: float
port?: int
```

Defaults:

```text
tolerance_m = 0.01
```

There is intentionally no `sync` parameter in v1.

There is intentionally no `project_first` parameter in v1.

The tool inspects the current in-memory Python scene graph for `relationship_fact_v1` edges. If no
matching projected facts exist, return success with empty evidence records and a diagnostic such as
`noProjectedRelationshipFacts` or `noMatchingRelationshipFacts`, not a failure.

## 5. Fact scope

Candidate edges are `SceneGraphAnalytics.graph` edges where:

```text
projectionKind == "relationship_fact_v1"
```

Optional filters apply to projected edge attributes:

- `object_ids`: include facts whose source or target owner object id is in the supplied set;
- `graph_source`: match `graphSource`;
- `graph_revision`: match `graphRevision`;
- `poses`: match `pose`;
- `relationship_types`: match `relationship` / `semanticRelationshipType`;
- `relationship_fact_ids`: match `relationshipFactId`.

`object_ids` is optional in this tool because evidence queries may reasonably target a graph source,
revision, pose, or exact fact id. This is different from `scene_semantic_relationships` and
`scene_object_semantic_context`, which are deliberately selected-object inspectors.

## 6. Hydration source

The evidence tool must not assume feature marker user strings are already cached in the Python scene
graph.

For each matching projected fact, read feature marker user text from Rhino using the read-only object
user text route for:

```text
fromFeatureObjectId
toFeatureObjectId
```

This is the same class of read-only Rhino access used by relationship fact projection. The tool must
not hydrate every scene object. It should hydrate only the unique feature marker object ids required
by the matching facts.

If either feature marker object id is missing from a projected edge, do not call Rhino for that
feature marker. Return a missing-evidence record for that fact.

Separate ordinary data gaps from environment/read failures:

- If a feature marker object exists but lacks the expected user text or position payload, keep the
  tool response successful and mark the affected evidence record as missing.
- If one feature marker user text read fails while other requested feature marker reads succeed,
  keep the tool response successful, mark only affected records as missing, and count a
  `hydrationFailures` diagnostic.
- If the Rhino connection is unavailable, the user text route is unavailable, or all requested
  feature marker user text reads fail for route-level reasons, return `success=false` because the
  read-backed measurement could not run. This is an environment/read failure, not missing evidence.

## 7. Position source

V1 position source:

```text
rook.graph.true_position_m
```

This user string is expected on feature marker objects and stores a JSON array:

```json
[x, y, z]
```

Coordinates are in the model unit system used by the authored graph; current fixtures use meters.

Do not use:

- feature marker rendered geometry;
- relationship marker geometry;
- owner object geometry;
- bounding boxes;
- scenegraph fuzzy edge distance.

If `rook.graph.true_position_m` is missing, invalid JSON, not a length-3 numeric list, or contains
non-finite values, return missing evidence for that feature.

## 8. Evidence model

Each matching relationship fact returns one evidence record:

```json
{
  "relationshipFactId": "column_01.top_point_supports_slab_01.underside_region",
  "relationship": "supports",
  "fromObjectId": "...",
  "toObjectId": "...",
  "fromFeature": "column_01.top_point",
  "toFeature": "slab_01.underside_region",
  "fromFeatureObjectId": "...",
  "toFeatureObjectId": "...",
  "contactKind": "point_to_region",
  "graphSource": "architectural_relationship_fixture",
  "graphRevision": "a001",
  "pose": "architectural_reference",
  "provenance": "authored_architectural_fixture",
  "status": "accepted",
  "evidence": {
    "kind": "relationship_geometry_evidence_v1",
    "method": "feature_marker_position_distance",
    "status": "measured",
    "distanceM": 0.0,
    "toleranceM": 0.01,
    "withinTolerance": true,
    "source": "rhino_user_text_feature_positions"
  }
}
```

Missing evidence is first-class:

```json
{
  "relationshipFactId": "door_01.body_hosted_by_wall_01.host_region",
  "relationship": "hosted_by",
  "fromFeature": "door_01.body",
  "toFeature": "wall_01.host_region",
  "contactKind": "body_to_region",
  "evidence": {
    "kind": "relationship_geometry_evidence_v1",
    "method": "feature_marker_position_distance",
    "status": "missing",
    "missing": ["fromFeaturePosition"],
    "toleranceM": 0.01,
    "withinTolerance": null,
    "source": "rhino_user_text_feature_positions"
  }
}
```

Missing evidence status values:

```text
measured
missing
```

Missing keys should be stable and specific:

```text
fromFeatureObjectId
toFeatureObjectId
fromFeatureUserText
toFeatureUserText
fromFeaturePosition
toFeaturePosition
```

## 9. Response shape

Top-level response:

```json
{
  "success": true,
  "projectionKind": "relationship_fact_v1",
  "evidenceKind": "relationship_geometry_evidence_v1",
  "method": "feature_marker_position_distance",
  "counts": {
    "matchingRelationshipFactCount": 5,
    "evidenceRecordCount": 5,
    "measuredEvidenceCount": 5,
    "missingEvidenceCount": 0,
    "withinToleranceCount": 3,
    "outsideToleranceCount": 2,
    "hydratedFeatureObjectCount": 10
  },
  "records": [],
  "diagnostics": {}
}
```

Diagnostics are counts, not fatal errors, for ordinary data gaps:

```text
noProjectedRelationshipFacts
noMatchingRelationshipFacts
missingFeatureObjectId
hydrationFailures
missingFeatureUserText
missingFeaturePosition
invalidFeaturePosition
outsideTolerance
```

Invalid input should return `success=false`:

- `object_ids` supplied but not `list[str]`;
- `poses`, `relationship_types`, or `relationship_fact_ids` supplied but not `list[str]`;
- `tolerance_m` not numeric, non-finite, or less than zero.

Read environment failures should also return `success=false`:

- no reachable Rhino/Rook instance for the requested `port`;
- the user text read route is unavailable;
- every required feature marker hydration fails for route-level reasons.

Suggested error identifiers:

```text
relationship_evidence_hydration_unavailable
relationship_evidence_hydration_failed
```

## 10. Targeting policy

This tool is not Rhino-independent. It reads Rhino user text for feature marker object ids.

Targeting policy:

```text
risk = "read"
```

The tool must be listed in the scene graph tool group and local/server dispatch surfaces, matching
the existing thin-registration pattern used by `scene_project_relationship_facts`,
`scene_semantic_relationships`, and `scene_object_semantic_context`.

## 11. Testing

Pure tests:

- filter projected `relationship_fact_v1` edges by graph source, revision, pose, relationship type,
  fact id, and selected owner object ids;
- compute distance between two valid feature positions;
- classify measured evidence inside tolerance;
- classify measured evidence outside tolerance;
- return missing evidence when either feature marker object id is absent from the edge;
- return missing evidence when either feature marker user text is absent;
- return missing evidence when either `true_position_m` value is missing or invalid;
- reject invalid input shapes and invalid tolerance values.

Tool/dispatch tests:

- local dispatcher exposes `scene_relationship_evidence`;
- server tool schema exposes the v1 inputs;
- targeting policy is read-only Rhino access;
- dispatch does not call `sync`;
- dispatch hydrates only the unique `fromFeatureObjectId` / `toFeatureObjectId` values needed by
  matching projected facts;
- dispatch returns success with missing evidence for ordinary data gaps.
- dispatch returns `success=false` when Rhino/user-text hydration is unavailable for all requested
  feature marker reads.

Live test:

- use the architectural fixture in a throwaway Rhino document;
- run the generated fixture script;
- run `scene_project_relationship_facts` for:

```text
graph_source = architectural_relationship_fixture
graph_revision = a001
```

- run `scene_relationship_evidence` for the same graph source and revision;
- use the default `tolerance_m = 0.01`;
- assert 5 matching facts, 5 evidence records, 10 hydrated feature marker objects, and 5 measured
  records;
- assert `withinToleranceCount == 3` and `outsideToleranceCount == 2`;
- assert the two outside-tolerance authored facts are reported as measured evidence rather than
  failed facts:
  - `hosted_by` distance `0.1000`;
  - `voids` distance `0.0200`;
- assert representative records for:
  - `supports` / `point_to_region`;
  - `penetrates` / `line_to_region`;
  - `bounded_by` / `boundary_to_face`.

Pearson is not a v1 live requirement. It can become a secondary scale gate after the evidence model
has proven useful on the architectural fixture.

## 12. Future slices

This slice intentionally prepares, but does not implement:

- object semantic context evidence summaries;
- owner geometry measurement methods;
- contact-kind-specific measurement strategies;
- evidence-aware fact validation;
- inferred candidate relationship facts;
- contradiction reporting between authored facts and geometry evidence;
- profile-driven tolerance defaults.

Those future capabilities should consume the evidence model established here rather than changing
relationship fact truth directly.
