# Relationship Fact Round-Trip Harness - design

> Status (2026-06-26): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/pearson-robot-roundtrip-harness` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on `codex/pearson-robot-feature-graph` at commit `d66f3119`.
> The projection slice below this branch should remain frozen while this harness slice is reviewed
> and implemented separately.

## 1. Reviewer backfill

Packaging/release work continues separately from the clean `main` checkout. This design lives in
the isolated Pearson worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/pearson-robot-roundtrip-harness
```

Stack base:

```text
d66f3119 fix: make relationship projection smoke repeatable
```

The base projection slice already provides:

- `scene_project_relationship_facts`;
- Rhino object user-text hydration through `/usertext/object-get`;
- owner-object-to-owner-object `relationship_fact_v1` edges in the Python NetworkX scene graph;
- `scene_context(sync=false)` rendering for projected `connects` edges;
- strict-mode mixed-document behavior that ignores plain non-graph Rhino objects;
- a repeatable five-object live smoke fixture under
  `experiments/relationship_fact_projection_smoke/`.

The two final projection review cleanups are included in the stack base:

- the smoke fixture clears its dedicated `Rook_RelationshipFactSmoke` layer before creating the
  five fixture objects;
- bounded diagnostic samples are explicitly deferred in the v1 projection spec, with
  `"samples": {}` retained as a response-envelope placeholder.

## 2. Goal

Add the first round-trip validation harness for relationship facts. The harness should prove the
smallest closed loop:

```text
Rhino fixture user text
-> scene_project_relationship_facts
-> Python scenegraph relationship_fact_v1 edge
-> structured fact comparison
-> scene_context(sync=false) readability check
-> compact mismatch report
```

The harness validates the semantic graph loop. It does not validate geometry inference, mesh
quality, robot modeling fidelity, or free-form scene context prose.

## 3. Scope

In scope:

- one small pure comparison helper;
- one live pytest adapter for the existing five-object smoke fixture;
- structured comparison of projected relationship-fact edge attributes;
- projection response count checks;
- high-signal `scene_context(sync=false)` substring checks;
- compact mismatch reporting.

Out of scope:

- geometry-first relationship inference;
- Pearson `g002` as a required automated pass gate;
- a generic harness framework;
- full context-line formatting snapshots;
- new MCP tools.

Pearson `g002` remains a documented manual follow-up gate after the minimal smoke harness is
stable.

## 4. Primary contract

Structured relationship facts are the primary pass/fail contract. The live adapter should extract
actual facts from projected NetworkX edge attributes after `scene_project_relationship_facts` runs.
It should not reparse the projection response as the source of semantic truth.

The expected semantic fact for v1 is:

```json
{
  "relationship": "connects",
  "fromFeature": "smoke_member.start",
  "toFeature": "smoke_joint.point",
  "contactKind": "point_to_point",
  "provenance": "authored_assembly_graph",
  "status": "accepted",
  "graphSource": "relationship_fact_smoke",
  "graphRevision": "smoke001",
  "pose": "smoke_pose"
}
```

Runtime Rhino object ids are evidence, not authored semantic identity. The harness may discover and
report `fromObjectId` and `toObjectId`, but those ids should not be part of the stable expected
semantic fact.

## 5. Secondary contract

The projection response proves count-level behavior. For the smoke fixture, the live adapter should
expect:

```json
{
  "relationshipFactCount": 1,
  "projectedEdgeCount": 1,
  "skippedFactCount": 0
}
```

`scene_context(sync=false)` is agent-facing evidence, but the harness should avoid freezing prose
formatting. It should require only high-signal substrings:

```text
connects
connected by
smoke_member.start -> smoke_joint.point
point_to_point
accepted
authored_assembly_graph
```

## 6. Helper shape

Create a deliberately small pure helper with this conceptual API:

```text
compare_roundtrip(expected_facts, actual_facts, context_text, required_substrings)
-> {
  success,
  missingFacts,
  unexpectedFacts,
  wrongMetadata,
  missingContextSubstrings
}
```

The helper should compare normalized dictionaries, not Rhino objects or NetworkX objects directly.
The live adapter owns extraction and normalization.

`wrongMetadata` should identify facts that match on the relationship identity fields but differ on
one or more metadata fields. For v1, identity fields are:

```text
relationship
fromFeature
toFeature
graphSource
graphRevision
pose
```

Metadata fields are:

```text
contactKind
provenance
status
```

This split keeps mismatch reports useful without making the helper complex.

## 7. Live adapter flow

The live pytest adapter should:

1. Require a live Rhino/Rook target or skip clearly when one is unavailable.
2. Execute `experiments/relationship_fact_projection_smoke/scripts/create_smoke_fixture_rhino.py`
   in Rhino.
3. Assert the fixture reports `source`, `revision`, `pose`, and the two owner object ids.
4. Call `scene_project_relationship_facts(graph_source="relationship_fact_smoke")`.
5. Assert the projection response count contract.
6. Extract actual semantic facts from `SceneGraphAnalytics.graph` projected edge attributes where
   `projectionKind == "relationship_fact_v1"` and `graphSource == "relationship_fact_smoke"`.
7. Query `scene_context(sync=false)` for the discovered owner object ids.
8. Run `compare_roundtrip(...)`.
9. Fail with the compact mismatch report when `success` is false.

The adapter may include discovered owner ids in the report for debugging.

## 8. Pearson manual gate

The Pearson robot `g002` graph should stay outside the first automated harness. A manual follow-up
check can run:

```text
scene_project_relationship_facts(graph_source="pearson_robot_skeleton_graph")
scene_context(sync=false) for selected connected owner objects
```

Expected rough scale for `g002` remains:

```text
28 authored relationships per pose
56 projected relationship facts across two poses when both poses are present
```

Any Pearson mismatch should inform the next slice, but should not block the minimal smoke harness.

## 9. Testing

Pure tests should cover:

- exact fact match succeeds;
- missing expected fact;
- unexpected actual fact;
- wrong metadata on a matching identity;
- missing required context substring.

Live pytest should cover:

- fixture creation;
- projection counts;
- edge-attribute extraction from NetworkX;
- context evidence;
- successful round-trip report.

The live test must be skippable when Rhino/Rook is not available. The pure tests should run in the
normal focused Python suite.

## 10. Review checklist

- Actual fact extraction comes from projected NetworkX edges, not projection response parsing.
- Runtime object ids are reported as evidence only.
- The helper remains a small comparator, not a framework.
- Context assertions use substrings, not full-line snapshots.
- Pearson `g002` is documented as a manual gate only.
- No geometry inference enters this slice.
