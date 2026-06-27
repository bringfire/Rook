# Pearson g002 Round-Trip Scale Gate - design

> Status (2026-06-27): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/pearson-robot-g002-roundtrip-gate` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on `codex/pearson-robot-roundtrip-harness` at commit `23d51446`.
> The lower projection and smoke round-trip slices should remain frozen while this scale-gate
> slice is reviewed and implemented separately.

## 1. Reviewer backfill

Packaging/release work continues separately from the clean `main` checkout. This design lives in
the isolated Pearson worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/pearson-robot-g002-roundtrip-gate
```

Stack base:

```text
23d51446 docs: document relationship fact roundtrip smoke
```

The stack below this slice already provides:

- `scene_project_relationship_facts`;
- owner-object-to-owner-object `relationship_fact_v1` projection into the Python NetworkX scene
  graph;
- strict-mode projection behavior that ignores plain non-graph Rhino objects;
- a pure relationship fact round-trip comparator;
- a skippable `requires_rhino` live smoke test for a five-object fixture;
- `scene_context(sync=false)` readability checks for projected relationship facts.

The Pearson authored graph artifacts already exist under:

```text
experiments/pearson_robot_skeleton_graph/
```

The durable authored graph is:

```text
experiments/pearson_robot_skeleton_graph/assembly_graph.json
```

The checked-in Rhino fixture script is:

```text
experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py
```

## 2. Goal

Add the first scale gate for the Pearson robot `g002` graph. The gate should prove that the
relationship fact projection and round-trip comparison path still works when the graph grows from
the five-object smoke fixture to the authored Pearson skeleton graph.

The closed loop is:

```text
assembly_graph.json expected facts
-> checked-in Pearson Rhino fixture script
-> live Rhino user text
-> scene_project_relationship_facts
-> Python scenegraph relationship_fact_v1 edges
-> structured fact comparison by pose
-> selected scene_context(sync=false) readability evidence
```

This slice validates authored semantic graph scale. It does not validate robot modeling quality,
geometry inference, mesh conversion, or final visual fidelity.

## 3. Scope

In scope:

- one skippable `requires_rhino` pytest live test for Pearson `g002`;
- executing the checked-in Pearson generated Rhino script through `rhino_execute`;
- count assertions against the generated script's printed JSON summary;
- expected fact generation from `assembly_graph.json`, expanded across poses;
- same-process projection and NetworkX edge inspection using one `SceneGraphAnalytics` instance;
- structured fact comparison grouped by pose;
- small selected `scene_context(sync=false)` checks for readability evidence;
- an optional cheap non-live drift check for the checked-in generated script payload.

Out of scope:

- regenerating `generated/skeleton_graph_rhino.py` inside the test;
- adding a new MCP query or graph-inspection surface;
- geometry-first relationship inference;
- comparing all context prose;
- screenshot or viewport validation;
- changing the authored Pearson graph schema.

## 4. Fixture source

The live test should use the checked-in generated fixture script:

```text
experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py
```

It should not regenerate that file during the test. Regeneration is a development action, not part
of the live gate. This keeps the gate deterministic and avoids generated-file churn during pytest
runs.

The fixture script is suitable for repeated live tests because it clears existing Rhino objects
whose object user text has:

```text
rook.graph.source == pearson_robot_skeleton_graph
```

Then it recreates both poses from its embedded `GRAPH = json.loads(...)` payload.

## 5. Fixture summary contract

The generated script prints a JSON summary. The live test should parse that summary from the
`rhino_execute` output and assert the actual current keys:

```text
success
revision
deleted_count
pose_count
joint_count
member_count
feature_count
relationship_marker_count
created_count
```

The required values are:

```text
success == true
revision == "g002"
pose_count == 2
joint_count == 30
member_count == 28
feature_count == 86
relationship_marker_count == 56
created_count == 200
```

`deleted_count` is intentionally not fixed. It may be `0` in a fresh throwaway document or nonzero
when the test reuses a document that already contains a prior Pearson fixture.

If `rhino_execute` is unavailable, no live Rhino target is reachable, or the script output cannot
be parsed, the live test should skip with a precise message when the failure is environmental. It
should fail when Rhino is reachable and the script runs but returns the wrong semantic counts.

## 6. Expected fact contract

Expected facts should be read from:

```text
experiments/pearson_robot_skeleton_graph/assembly_graph.json
```

The expected fact builder should:

1. load `revision`, `poses`, `features`, and `relationships`;
2. map feature ids to their owning graph objects;
3. expand every authored relationship across every pose;
4. emit normalized relationship facts compatible with the existing round-trip comparator.

The expected count is:

```text
len(relationships) * len(poses) == 28 * 2 == 56
```

The per-pose expected counts are:

```text
rest_t_pose == 28
reclined_robot == 28
```

Each expected fact should include:

```json
{
  "relationship": "connects",
  "fromFeature": "spine_base_to_spine_top.start",
  "toFeature": "spine_base.point",
  "contactKind": "point_to_point",
  "provenance": "authored_assembly_graph",
  "status": "accepted",
  "graphSource": "pearson_robot_skeleton_graph",
  "graphRevision": "g002",
  "pose": "rest_t_pose"
}
```

Runtime Rhino object ids may be reported for diagnostics, but they are not part of the stable
semantic expectation.

## 7. Projection and extraction flow

The live test should follow the same process-boundary rule as the smoke harness:

- execute Rhino fixture creation through `rhino_execute`;
- project in the pytest process using source-level projection functions;
- inspect the same `SceneGraphAnalytics.graph` instance used for projection.

The test must not call an external MCP server for projection and then inspect a different in-memory
graph in the pytest process. That split would validate the response envelope but not the projected
NetworkX edges.

Conceptual flow:

```text
require live Rhino/Rook target or skip
execute generated/skeleton_graph_rhino.py through rhino_execute
assert fixture summary counts
sg = get_scene_graph() or equivalent shared analytics instance
scene_project_relationship_facts(
  graph_source="pearson_robot_skeleton_graph",
  graph_revision="g002",
  analytics=sg,
  strict=True
)
extract sg.graph edges where:
  projectionKind == "relationship_fact_v1"
  graphSource == "pearson_robot_skeleton_graph"
  graphRevision == "g002"
compare expected vs actual normalized facts
```

The projection response should also be checked for count-level behavior:

```text
relationshipFactCount == 56
projectedEdgeCount == 56
skippedFactCount == 0
```

If the response includes additional informational diagnostics for normal filtering behavior, those
should not fail the live gate. Validation errors for malformed Pearson graph records should fail.

## 8. Context readability checks

`scene_context(sync=false)` should remain secondary evidence. The test should not query every fact
or freeze full prose formatting.

The test should choose a small representative subset across both poses, such as:

```text
spine_base_to_spine_top.start -> spine_base.point
spine_top_to_left_shoulder.end -> left_shoulder.point
left_hip_to_left_knee.end -> left_knee.point
right_knee_to_right_foot.end -> right_foot.point
```

Required context evidence should use high-signal substrings, for example:

```text
connects
connected by
point_to_point
accepted
authored_assembly_graph
```

The selected feature path strings should also appear, for example:

```text
spine_base_to_spine_top.start -> spine_base.point
spine_top_to_left_shoulder.end -> left_shoulder.point
```

Graph source, graph revision, and pose are structured edge-attribute assertions, not context text
assertions in this slice. Current relationship-fact context rendering does not emit those fields.
Adding them to `scene_context` would be a separate context-formatting change with its own tests.

The test may query context by selected owner object ids discovered from projected edges. It should
avoid depending on runtime Rhino object ids in expected semantic facts.

## 9. Optional non-live drift check

A small non-live test may parse the embedded payload in:

```text
experiments/pearson_robot_skeleton_graph/generated/skeleton_graph_rhino.py
```

and compare it with:

```text
experiments/pearson_robot_skeleton_graph/assembly_graph.json
```

The purpose is to catch stale generated fixture drift without requiring Rhino. The check should be
cheap and narrow:

```text
revision matches
pose ids match
node/member/feature/relationship counts match
relationship ids match
```

This check should not become a generic generated-code validator. Its job is only to make Pearson
live-test failures easier to diagnose.

## 10. Error handling

The live test should classify outcomes clearly:

- skip: Rhino/Rook target unavailable;
- skip: fixture script cannot be executed because the live target is not available;
- fail: fixture script runs but summary counts are wrong;
- fail: projection response counts are wrong;
- fail: expected vs actual structured facts differ;
- fail: selected context evidence is missing.

Mismatch reports should stay compact and should reuse the existing round-trip comparator shape
where practical:

```text
missingFacts
unexpectedFacts
wrongMetadata
missingContextSubstrings
```

For Pearson scale debugging, the report should also include per-pose actual counts.

## 11. Testing plan

Pure/non-live tests:

- expected fact builder expands `assembly_graph.json` into 56 facts;
- per-pose counts are 28 and 28;
- generated-script payload drift check matches `assembly_graph.json` when enabled;
- mismatch reporting includes pose-level counts when facts are missing.

Live/skippable test:

- executes the checked-in generated Pearson script in Rhino;
- asserts fixture summary keys and counts;
- projects `pearson_robot_skeleton_graph` revision `g002` in-process;
- extracts projected `relationship_fact_v1` edges from the same graph instance;
- compares 56 expected facts to 56 actual facts;
- checks selected `scene_context(sync=false)` readability substrings.

Recommended focused commands after implementation:

```powershell
python -m pytest mcp_server/tests/test_relationship_fact_roundtrip.py mcp_server/tests/test_pearson_g002_roundtrip_gate.py -q
python -m pytest -m requires_rhino mcp_server/tests/test_pearson_g002_roundtrip_gate_live.py -q
git diff --check
```

The live command should skip cleanly when Rhino/Rook is unavailable and pass when the throwaway
Rhino document is open and reachable.

## 12. Success criteria

This slice is complete when:

- the design and implementation remain on `codex/pearson-robot-g002-roundtrip-gate`;
- the non-live Pearson expectation tests pass;
- the live Pearson gate passes against a reachable throwaway Rhino document;
- the live test skips cleanly when the target is unavailable;
- no new MCP tool or graph-query surface is added;
- the Pearson scale gate remains authored-fact validation only.

## 13. Future slices

This scale gate may expose pressure for a future graph query surface if out-of-process inspection
becomes painful. That should be treated as a separate slice.

Likely next candidates after this gate:

- selected-object relationship context ergonomics for larger authored graphs;
- geometry-to-fact candidate inference against the same `RelationshipFact` contract;
- graph schema extensions for planar/continuous attachments, slabs, walls, grids, and IFC/RIR
  relationship analogs.

Those are intentionally deferred. The current slice should answer only whether the authored
Pearson `g002` graph survives the projection and round-trip validation path at meaningful scale.
