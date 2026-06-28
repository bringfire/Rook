# Architectural Relationship Fixture v1 - design

> Status (2026-06-28): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/architectural-relationship-fixture-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen object semantic context card branch. Do not add more work to
> `codex/semantic-relationship-display-v1` unless review feedback requires it.

## 1. Reviewer backfill

This work is in the isolated Pearson/Rook graph worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/architectural-relationship-fixture-v1
```

Immediate stack base:

```text
3f883967 feat: expose object semantic context tool
```

The stack below this branch already provides:

- `scene_project_relationship_facts`, which hydrates authored `rook.graph.*` Rhino object user text
  and projects owner-object-to-owner-object `relationship_fact_v1` edges into the Python
  `SceneGraphAnalytics.graph`;
- `scene_semantic_relationships`, the raw object-centric fact inspector over already-projected
  relationship-fact edges;
- `scene_object_semantic_context`, the bounded per-object card/view-model layer over the raw
  inspector;
- a repeatable five-object relationship-fact smoke fixture;
- a skippable live smoke round-trip test;
- a skippable live Pearson `g002` scale gate with 56 robot `connects` facts.

The robot proves the mechanics. The object card tool proves selected-object summarization. This
slice should prove the same authored-fact substrate can express small architectural relationships
without starting ontology integration or geometry inference.

## 2. Goal

Add a small authored architectural fixture that validates this loop:

```text
authored architectural graph
-> generated Rhino fixture script
-> Rhino object user text
-> scene_project_relationship_facts
-> scene_semantic_relationships
-> scene_object_semantic_context
-> expected architectural facts/cards
```

The fixture should be intentionally small: enough to pressure the relationship vocabulary and card
grouping, but not enough to become a mini building.

## 3. Non-goals

This slice must not:

- add geometry inference;
- add ontology predicates or mapping fields;
- introduce IFC, BOT, Brick, RDF, TopologicPy, or Revit dependencies;
- add a new public MCP tool;
- change `scene_project_relationship_facts`;
- change `scene_semantic_relationships`;
- change `scene_object_semantic_context`;
- add scenegraph display UI or Rhino overlay geometry;
- validate architectural physical correctness;
- create a full building model.

The semantic graph is the artifact being tested. Geometry only needs to be simple, selectable Rhino
geometry that can carry user text.

## 4. Fixture scope

Create a durable experiment folder:

```text
experiments/architectural_relationship_fixture/
```

Files:

```text
experiments/architectural_relationship_fixture/assembly_graph.json
experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py
experiments/architectural_relationship_fixture/README.md
```

The fixture should contain seven owner objects:

```text
column_01
slab_01
wall_01
door_01
opening_01
duct_01
space_01
```

The authored relationships should be:

```text
column_01.top_point supports slab_01.underside_region
door_01.body hosted_by wall_01.host_region
opening_01.profile voids wall_01.opening_region
duct_01.centerline penetrates wall_01.penetration_region
space_01.boundary bounded_by wall_01.inner_face
```

Expected relationship count:

```text
5 relationships * 1 pose = 5 projected relationship facts
```

Use one pose:

```text
architectural_reference
```

Use:

```text
graphSource = architectural_relationship_fixture
graphRevision = a001
provenance = authored_architectural_fixture
status = accepted
```

## 5. Relationship direction

Relationship direction should follow the authored `from_feature -> to_feature` record:

```text
column_01.top_point -> slab_01.underside_region
door_01.body -> wall_01.host_region
opening_01.profile -> wall_01.opening_region
duct_01.centerline -> wall_01.penetration_region
space_01.boundary -> wall_01.inner_face
```

So selected-object direction is:

- `column_01`: outgoing `supports`;
- `slab_01`: incoming `supports`;
- `door_01`: outgoing `hosted_by`;
- `opening_01`: outgoing `voids`;
- `duct_01`: outgoing `penetrates`;
- `space_01`: outgoing `bounded_by`;
- `wall_01`: incoming `hosted_by`, incoming `voids`, incoming `penetrates`, incoming
  `bounded_by`.

`bounded_by` is intentionally authored as:

```text
space_01.boundary bounded_by wall_01.inner_face
```

That means the space card has outgoing `bounded_by`, and the wall card has incoming `bounded_by`.
Readable prose may sound awkward in v1 because the current generic line formatter does not know
relationship-specific inverse phrasing. Tests must assert structured facts/groups and only
high-signal substrings, not exact prose snapshots.

## 6. Contact kinds

Use architecture-flavored but neutral `contactKind` values:

```text
point_to_region
body_to_region
profile_to_region
line_to_region
boundary_to_face
```

Mapping:

```text
supports     -> point_to_region
hosted_by    -> body_to_region
voids        -> profile_to_region
penetrates   -> line_to_region
bounded_by   -> boundary_to_face
```

These are fixture vocabulary, not ontology commitments.

## 7. Authored graph format

`assembly_graph.json` should be small, explicit, and similar in spirit to the Pearson graph:

```json
{
  "schema": "rook.architectural_relationship_fixture.v1",
  "source": "architectural_relationship_fixture",
  "revision": "a001",
  "unit": "meters",
  "poses": {
    "architectural_reference": {
      "description": "Single authored architectural semantic fixture pose"
    }
  },
  "objects": [
    {
      "id": "column_01",
      "kind": "column",
      "name": "Column 01"
    }
  ],
  "features": [
    {
      "id": "column_01.top_point",
      "owner": "column_01",
      "owner_kind": "column",
      "feature_kind": "point",
      "role": "top_point"
    }
  ],
  "relationships": [
    {
      "id": "column_01.top_point_supports_slab_01.underside_region",
      "type": "supports",
      "from": "column_01.top_point",
      "to": "slab_01.underside_region",
      "contact_kind": "point_to_region",
      "provenance": "authored_architectural_fixture",
      "status": "accepted"
    }
  ]
}
```

The implementation plan may choose exact object geometry and feature coordinates. The graph must
remain the source of semantic truth.

## 8. Rhino fixture script

The generated Rhino script should be checked in:

```text
experiments/architectural_relationship_fixture/generated/create_architectural_fixture_rhino.py
```

It should be executable through `rhino_execute` in a throwaway Rhino document.

It should:

- create or reuse a dedicated layer, for example `Rook_ArchitecturalRelationshipFixture`;
- clear that dedicated layer before recreating objects, so repeated test runs are deterministic;
- create simple selectable geometry for seven owner objects;
- create feature marker geometry for each authored feature;
- create relationship marker geometry for each authored relationship;
- stamp every fixture object with:

```text
rook.graph.source = architectural_relationship_fixture
rook.graph.revision = a001
rook.graph.pose = architectural_reference
rook.graph.visual_type = member | feature | relationship
```

For this fixture, `visual_type=member` is the parser-facing value for owner objects. It does not
mean the architectural object is literally a robot member.

It should stamp owners with the existing relationship-fact projection keys:

```text
rook.graph.visual_type = member
rook.graph.member_id = <architectural owner id>
rook.graph.feature_ids
rook.graph.relationship_ids
```

This is a projection-v1 compatibility choice, not architectural terminology. The current projection
parser recognizes owner records through `rook.graph.visual_type == member` plus
`rook.graph.member_id`, or through `rook.graph.visual_type == joint` plus `rook.graph.node_id`.
Use the `member` path for all seven architectural owners so feature records can set:

```text
rook.graph.owner = <architectural owner id>
rook.graph.owner_kind = member
```

Do not expand the projection parser in this slice. A future parser generalization for arbitrary
owner kinds should be a separate design because it would affect all relationship-fact projection
fixtures, not only this architectural fixture.

The script should print a JSON summary with at least:

```text
success
source
revision
pose
clearedObjectCount
ownerObjectCount
featureObjectCount
relationshipObjectCount
createdObjectCount
ownerObjectIds
```

Expected counts:

```text
ownerObjectCount == 7
featureObjectCount == 10
relationshipObjectCount == 5
createdObjectCount == 22
```

The ten features are:

```text
column_01.top_point
slab_01.underside_region
door_01.body
wall_01.host_region
opening_01.profile
wall_01.opening_region
duct_01.centerline
wall_01.penetration_region
space_01.boundary
wall_01.inner_face
```

`clearedObjectCount` is intentionally variable.

## 9. Non-live tests

Add non-live tests that do not require Rhino:

- validate `assembly_graph.json` shape;
- assert source, revision, unit, one pose, seven owners, ten features, five relationships;
- build expected semantic facts from `assembly_graph.json`;
- assert the expected relationship types:

```text
bounded_by
hosted_by
penetrates
supports
voids
```

- build a synthetic `SceneGraphAnalytics.graph` with projected `relationship_fact_v1` edges from
  the expected facts;
- query `scene_semantic_relationships`;
- query `scene_object_semantic_context`;
- assert structured inspector/card results for representative objects.

Required card assertions:

- `column_01` has outgoing `supports: 1`;
- `slab_01` has incoming `supports: 1`;
- `door_01` has outgoing `hosted_by: 1`;
- `duct_01` has outgoing `penetrates: 1`;
- `space_01` has outgoing `bounded_by: 1`;
- `wall_01` has four incoming relationship groups:

```text
hosted_by:incoming:accepted:authored_architectural_fixture
voids:incoming:accepted:authored_architectural_fixture
penetrates:incoming:accepted:authored_architectural_fixture
bounded_by:incoming:accepted:authored_architectural_fixture
```

The wall card is the main architectural stress point in this slice. It proves one object can gather
multiple different architecture-flavored semantic relationships without falling back to fuzzy
adjacency.

## 10. Skippable live Rhino test

Add a skippable `requires_rhino` live test that:

1. requires a reachable throwaway Rhino/Rook target or skips clearly;
2. executes `generated/create_architectural_fixture_rhino.py` through `rhino_execute`;
3. parses the script summary and asserts count fields;
4. projects with:

```text
scene_project_relationship_facts(
  graph_source="architectural_relationship_fixture",
  graph_revision="a001",
  poses=["architectural_reference"]
)
```

5. asserts projection counts:

```text
relationshipFactCount == 5
projectedEdgeCount == 5
skippedFactCount == 0
```

6. extracts projected `relationship_fact_v1` edges from the same `SceneGraphAnalytics` instance;
7. compares expected semantic facts from `assembly_graph.json` with actual projected edges;
8. queries `scene_semantic_relationships` for selected owner object ids;
9. queries `scene_object_semantic_context` for selected owner object ids;
10. asserts the same structured fact/card expectations as the non-live test for column/slab,
    door/wall, duct/wall, and space/wall.

The live test should not assert exact context/card prose. It may assert high-signal substrings such
as relationship type, feature path, `accepted`, and `authored_architectural_fixture`.

## 11. Process-boundary rule

The live test must follow the same process-boundary rule as the smoke and Pearson gates:

- execute Rhino fixture creation through `rhino_execute`;
- project in the pytest process using source-level projection functions;
- inspect the same `SceneGraphAnalytics.graph` instance used for projection.

Do not call an external MCP server for projection and then inspect a different in-memory graph in
the pytest process. That split validates the response envelope but not the projected NetworkX edges.

## 12. Error handling

Classify live outcomes clearly:

- skip: Rhino/Rook target unavailable;
- skip: fixture script cannot be executed because the live target is unavailable;
- fail: fixture script runs but summary counts are wrong;
- fail: projection response counts are wrong;
- fail: expected vs actual structured facts differ;
- fail: inspector/card structured expectations are missing.

Mismatch reports should stay compact and include:

```text
missingFacts
unexpectedFacts
wrongMetadata
missingCardGroups
fixtureSummary
```

Runtime Rhino object ids may be reported for diagnostics, but they are not part of the stable
semantic fact identity.

## 13. Testing commands

Recommended focused non-live command:

```powershell
python -m pytest mcp_server/tests/test_architectural_relationship_fixture.py -q
```

Recommended live command:

```powershell
python -m pytest -m requires_rhino mcp_server/tests/test_architectural_relationship_fixture_live.py -q
```

Recommended guard command:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_projection.py mcp_server/tests/test_semantic_relationship_inspector.py mcp_server/tests/test_object_semantic_context.py -q
```

Whitespace:

```powershell
git diff --check
git show --check --stat HEAD
```

The live command should skip cleanly when Rhino/Rook is unavailable and pass when a throwaway Rhino
document is open and reachable.

## 14. Success criteria

This slice is complete when:

- the fixture graph and generated Rhino script are checked in under
  `experiments/architectural_relationship_fixture/`;
- the fixture uses seven owner objects, ten features, and five relationship markers;
- non-live tests validate expected facts and card summaries;
- the skippable live test proves Rhino user text -> projection -> inspector -> card behavior;
- the wall card proves four incoming architecture-flavored relationship groups;
- no ontology predicates, IFC/BOT/Brick/RDF integration, geometry inference, new MCP tool, display
  UI, or projection parser expansion is added;
- focused tests and whitespace checks pass.

## 15. Future slices

Later slices can build on this fixture:

- optional predicate metadata pass-through such as `ontologyPredicate` or `inversePredicate`;
- geometry-to-fact candidate inference for obvious column/slab or wall/roof contacts;
- IFC/RIR/RookBIM mapping experiments;
- graph contradiction checks between authored facts and inferred candidates;
- display modes or panels that consume `scene_object_semantic_context`.

Those are intentionally deferred. The current slice should answer only whether neutral authored
relationship facts and cards can represent a small architectural semantic scene.
