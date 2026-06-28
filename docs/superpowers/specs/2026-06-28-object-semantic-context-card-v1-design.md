# Object Semantic Context Card v1 - design

> Status (2026-06-28): DESIGN - brainstorm complete, ready for review.
> Branch/worktree: `codex/semantic-relationship-display-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen semantic relationship inspector branch. Do not add more work
> to `codex/semantic-relationship-inspector-v1` unless review feedback requires it.

## 1. Reviewer backfill

This work is in the isolated Pearson worktree:

```text
C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph
```

Current branch:

```text
codex/semantic-relationship-display-v1
```

Immediate stack base:

```text
9440cb6b fix: validate semantic relationship object ids
```

The stack below this branch already proves:

- authored relationship facts can be projected from Rhino object user text into the Python
  `SceneGraphAnalytics.graph`;
- projection creates owner-object-to-owner-object `relationship_fact_v1` edges;
- feature endpoints remain edge metadata through `fromFeature` and `toFeature`;
- the five-object smoke fixture passes the full round-trip path;
- Pearson `g002` passes the full live scale gate with 56 projected facts across two poses;
- `scene_semantic_relationships` provides the raw object-centric fact query contract over already
  projected `relationship_fact_v1` edges;
- `scene_context(sync=false)` can render readable relationship-fact prose, but it is not the
  structured query contract.

The current generic scenegraph display remains centered on fuzzy spatial relationships such as
adjacency, containment, proximity, and other heuristic observations. Those edges answer a different
question than authored or inferred semantic facts.

The desired medium-term mental model is:

```text
geometry observations
+ authored/imported facts
+ inferred candidate facts
+ provenance/confidence/status
-> agent can answer design questions and detect contradictions
```

This slice should not display more graph complexity. It should produce a compact semantic read
model that helps an agent understand selected design objects without mixing semantic facts with
fuzzy spatial edges.

## 2. Goal

Add a v1 object semantic context card tool:

```text
scene_object_semantic_context
```

The tool should answer:

```text
Given these selected object ids, what compact semantic context should an agent see for each object?
```

It is a bounded presentation layer over the raw semantic relationship inspector. The primary output
is structured JSON. Readable lines are secondary convenience text.

The architectural separation is:

```text
scene_semantic_relationships = raw fact inspector
scene_object_semantic_context = bounded agent-facing card view
```

## 3. Non-goals

This slice must not:

- mutate Rhino geometry, attributes, layers, blocks, or document state;
- create overlay geometry, visual glyphs, or Rhino display modes;
- infer relationships from geometry;
- call `scene_project_relationship_facts` automatically;
- call `sync` or refresh the scene graph mirror;
- include fuzzy spatial edges such as `near`, `adjacent`, `contains`, or `overlaps`;
- add a whole-scene graph dump mode;
- recursively expand cards through related objects;
- recursively expand block instance contents;
- add block-definition cards;
- change `scene_context` rendering;
- change the raw `scene_semantic_relationships` response contract.

Projection is a separate explicit step. The card reads the current in-memory Python scene graph only.

## 4. Meaning of object

The word "object" is overloaded in CAD. For v1, define the card target as:

```text
Card target = current scenegraph node keyed by a selectable/runtime Rhino object id.
```

Consequences:

- A normal Rhino object is card eligible.
- A block instance, also known as an insert object, is card eligible as one object.
- A block definition is not card eligible in v1.
- Geometry inside a block definition is not card eligible in v1 unless it already appears as its
  own runtime scenegraph node.
- There are no recursive cards for block contents.
- There is no implicit expansion through instance definitions.
- Relationship facts touching a block instance may appear on the block instance card.

This is an occurrence-oriented contract, not a definition-oriented contract. A selected block
instance represents one placed occurrence in the model. Shared definition geometry should not be
treated as if it were separate placed model geometry for every instance.

Feature and relationship marker nodes are not primary targets for v1. If explicitly requested and
present in the scenegraph, they should be treated like any other selected node: return a card for the
node, but do not special-case or expand marker semantics. In normal projected relationship facts,
owner-object cards carry the useful semantic relationships.

Optional block metadata may be copied onto cards when the current scenegraph already provides it:

```json
{
  "objectKind": "block_instance",
  "definitionId": "...",
  "definitionName": "...",
  "canExpandChildren": false
}
```

These fields are opportunistic. V1 must not invent block hierarchy semantics or require a block
fixture.

## 5. Tool surface

Add a read-only MCP/local tool:

```text
scene_object_semantic_context
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
max_groups?: int
max_facts_per_group?: int
```

There is intentionally no `sync` parameter in v1.

There is intentionally no `project_first` parameter in v1.

There is intentionally no `port` parameter in v1.

There is intentionally no recursive expansion parameter in v1.

`object_ids` is required and must be a non-empty `list[str]`. Missing or empty `object_ids` should
return:

```json
{
  "success": false,
  "error": "missing_object_ids",
  "message": "scene_object_semantic_context requires object_ids in v1"
}
```

Invalid `object_ids` shape should return:

```json
{
  "success": false,
  "error": "invalid_object_ids",
  "message": "scene_object_semantic_context requires object_ids to be a list of strings in v1"
}
```

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

Default card bounds:

```text
max_groups = 8
max_facts_per_group = 5
```

Bounds should be conservative and deterministic. If callers pass invalid or non-positive bounds,
return a validation failure instead of silently changing them:

```json
{
  "success": false,
  "error": "invalid_card_bounds",
  "message": "max_groups and max_facts_per_group must be positive integers in v1"
}
```

## 6. Response shape

Response shape:

```json
{
  "success": true,
  "projectionKind": "relationship_fact_v1",
  "counts": {
    "requestedObjectCount": 2,
    "existingSelectedObjectCount": 2,
    "missingSelectedObjectCount": 0,
    "relationshipFactCount": 4,
    "relationshipViewCount": 4,
    "cardCount": 2
  },
  "cards": [
    {
      "objectId": "selected-id",
      "exists": true,
      "name": "spine_base",
      "objectKind": null,
      "definitionId": null,
      "definitionName": null,
      "canExpandChildren": false,
      "summary": {
        "relationshipFactCount": 4,
        "relationshipViewCount": 4,
        "byRelationship": {
          "connects": 4
        },
        "byDirection": {
          "incoming": 4
        },
        "byStatus": {
          "accepted": 4
        },
        "byProvenance": {
          "authored_assembly_graph": 4
        },
        "poses": [
          "reclined_robot",
          "rest_t_pose"
        ]
      },
      "groups": [
        {
          "groupKey": "connects:incoming:accepted:authored_assembly_graph",
          "relationship": "connects",
          "direction": "incoming",
          "status": "accepted",
          "provenance": "authored_assembly_graph",
          "count": 4,
          "sampleFacts": [
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
            "connected by spine_base_to_spine_top via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted, authored_assembly_graph"
          ],
          "truncated": false
        }
      ],
      "expandableGroups": []
    }
  ],
  "diagnostics": {}
}
```

`cards` must preserve requested `object_ids` order after first-occurrence deduplication.

`relationshipFactCount` counts unique projected relationship-fact edges that match the filters and
touch at least one requested existing object.

`relationshipViewCount` counts emitted object-local fact views across returned cards. When both
endpoints of the same fact are selected, the same underlying fact may appear in two cards and
increase `relationshipViewCount` by `2` while increasing `relationshipFactCount` by only `1`.

`cardCount` counts returned cards, including missing-object cards.

Per-card `summary.relationshipFactCount` counts unique facts touching that card's selected object
after filters. Per-card `summary.relationshipViewCount` counts the emitted views on that one card.

## 7. No-fact and missing cards

If a selected id is missing from the current scenegraph, return a card:

```json
{
  "objectId": "missing-id",
  "exists": false,
  "name": null,
  "objectKind": null,
  "definitionId": null,
  "definitionName": null,
  "canExpandChildren": false,
  "summary": {
    "relationshipFactCount": 0,
    "relationshipViewCount": 0,
    "byRelationship": {},
    "byDirection": {},
    "byStatus": {},
    "byProvenance": {},
    "poses": []
  },
  "groups": [],
  "expandableGroups": []
}
```

Diagnostics should include:

```json
{
  "missingSelectedObjects": 1
}
```

If a selected id exists but has no matching relationship facts, return a card with `exists: true`,
object metadata when available, the same zero-count summary shape, empty groups, and:

```json
{
  "noFactsForSelectedObjects": 1
}
```

If no `relationship_fact_v1` edges exist anywhere in the current graph, return success with empty
fact summaries and:

```json
{
  "noProjectedRelationshipFacts": 1,
  "projectionRequired": 1
}
```

These diagnostics are additive. A mixed selection may have missing objects and existing objects with
no facts.

## 8. Grouping

Groups summarize facts for one selected object. The default grouping key is:

```text
relationship:direction:status:provenance
```

Example:

```text
connects:incoming:accepted:authored_assembly_graph
```

If a component is missing, use a stable placeholder:

```text
unknown
```

Example:

```text
connects:incoming:unknown:unknown
```

Group ordering must be deterministic:

1. descending `count`;
2. ascending `relationship`;
3. ascending `direction`;
4. ascending `status`;
5. ascending `provenance`;
6. ascending `groupKey`.

Within each group, `sampleFacts` should preserve raw structured fact fields from
`scene_semantic_relationships` rather than replacing them with prose. `lines` are secondary and may
be derived from the same facts.

When the group contains more facts than `max_facts_per_group`, include only the deterministic first
`max_facts_per_group` sample facts and set:

```json
{
  "truncated": true
}
```

If the object has more groups than `max_groups`, include only the first `max_groups` groups and add
an `expandableGroups` entry for each omitted group:

```json
{
  "groupKey": "connects:outgoing:accepted:authored_assembly_graph",
  "relationship": "connects",
  "direction": "outgoing",
  "status": "accepted",
  "provenance": "authored_assembly_graph",
  "count": 12,
  "reason": "group_limit"
}
```

V1 does not implement an expansion call. `expandableGroups` is a stable affordance for later
details-on-demand tooling.

## 9. Filtering

Filters mirror `scene_semantic_relationships`:

- `graph_source` matches `graphSource`;
- `graph_revision` matches `graphRevision`;
- `poses` matches `pose`;
- `relationship_types` matches `semanticRelationshipType` when present, otherwise `relationship`;
- `status` matches `status`;
- `provenance` matches `provenance`;
- `direction` filters relative to each selected object.

Filters apply before grouping.

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

## 10. Readable lines

Readable `lines` are secondary. They should be compact and should not be treated as the source of
truth.

Lines should describe grouped samples in ordinary agent-facing language:

```text
connected by spine_base_to_spine_top via spine_base_to_spine_top.start -> spine_base.point, point_to_point, accepted, authored_assembly_graph
```

Tests should assert only high-signal substrings, not full prose snapshots.

The structured fields in `summary`, `groups`, and `sampleFacts` are authoritative.

## 11. Relationship to large scenes

V1 deliberately avoids nested recursive cards. A scene with 1000 objects should not cause this tool
to dump a large semantic graph or recursively expand related objects.

The intended scaling model is progressive semantic expansion:

```text
Level 0: selected object card
Level 1: immediate semantic neighbor groups summarized
Level 2: expand one group or one related object in a later tool
Level 3: assembly, system, route, or path view in a later tool
```

The v1 affordances that support this future direction are:

- stable `groupKey` values;
- counts before lists;
- bounded `sampleFacts`;
- explicit `truncated` flags;
- `expandableGroups`;
- no automatic recursive expansion.

This follows the same general interaction pattern as overview first, filter or zoom, and details on
demand, but keeps v1 as a simple read model rather than a UI framework.

## 12. Future architectural semantics

The card shape should be able to carry richer relationship vocabularies later without changing the
raw fact model. Motivating future cases include:

- column to slab: `column.top_point -> slab.underside_region`, later summarized as support rather
  than mere proximity;
- wall to slab or roof: `wall.top_edge -> slab.underside_strip`, testing edge/strip contacts;
- curtain wall panel systems: `panel.edge -> mullion.face/slot` and `mullion -> frame`, testing
  repeated parts and hierarchy;
- door in wall: `door hosted_by wall` and `door.opening bounds wall void`, testing semantic hosting;
- stair landing to floor: `stair.landing_edge -> floor.edge/region`, testing circulation continuity;
- duct penetration: `duct penetrates wall` and `sleeve bounds penetration`, testing intersection
  semantics that are not ordinary adjacency;
- robot/member graph: `member.endpoint -> joint.point`, remaining the clean authored calibration
  fixture.

These are motivating examples only. V1 tests should use synthetic relationship-fact edges and the
existing robot/smoke vocabulary. Do not build new architectural fixtures in this slice.

## 13. Implementation placement

Add a focused Python module:

```text
mcp_server/src/rook/scene/object_semantic_context.py
```

This module should own:

- request validation;
- calling or sharing logic with `query_semantic_relationships`;
- card shaping;
- summary counts;
- deterministic grouping;
- truncation;
- diagnostics;
- response shaping.

`scene_semantic_relationships` should remain the raw fact-query surface. Do not add card formatting
or truncation behavior to `semantic_relationship_inspector.py` unless it is a small reusable helper
that does not change the public inspector contract.

Shared MCP surfaces should remain thin registration/dispatch seams:

- `mcp_server/src/rook/server.py`
- `mcp_server/src/rook/agent/tool_dispatcher.py`
- `mcp_server/src/rook/agent/tool_groups.py`
- `mcp_server/src/rook/targeting.py`

Do not put business logic in those shared surface files.

## 14. Tool policy

The tool is read-only. It does not require a live Rhino call because it inspects the current Python
scene graph mirror and does not sync.

Targeting policy should be:

```text
requires_rhino = false
risk = "read"
```

This matches `scene_semantic_relationships`, not `scene_project_relationship_facts`.

## 15. Tests

Pure tests should cover:

- missing/empty `object_ids` fails with `missing_object_ids`;
- invalid `object_ids` shape fails with `invalid_object_ids`;
- invalid `direction` fails with `invalid_direction`;
- missing selected objects produce `exists: false` cards with the full zero-count summary shape;
- existing selected objects with no facts produce `exists: true` cards with the full zero-count
  summary shape;
- only `projectionKind == "relationship_fact_v1"` facts appear in cards;
- fuzzy spatial edges are ignored;
- response card order follows first occurrence in input `object_ids`;
- both-endpoint selection preserves `relationshipFactCount` vs `relationshipViewCount` semantics;
- grouping key is deterministic;
- group ordering is deterministic;
- `max_groups` truncates groups and populates `expandableGroups`;
- `max_facts_per_group` truncates `sampleFacts` and marks the group as truncated;
- raw sample fact fields are preserved;
- filters for graph source, revision, pose, relationship type, status, provenance, and direction;
- diagnostics distinguish `noProjectedRelationshipFacts` from `noFactsForSelectedObjects`;
- optional block metadata is copied only when present and is not invented.

Tool surface tests should cover:

- MCP schema exposes required `object_ids`, optional filters, `max_groups`, and
  `max_facts_per_group`;
- local dispatcher registers `scene_object_semantic_context`;
- tool group includes `scene_object_semantic_context`;
- targeting policy is read-only and does not require Rhino;
- `_call_tool_dispatch("scene_object_semantic_context", ...)` returns the public payload shape;
- dispatch path does not call `sync`;
- dispatch path does not call `scene_project_relationship_facts`.

Live tests are optional for v1. If added, they should reuse the five-object smoke fixture, run
projection explicitly, and call `scene_object_semantic_context` for the two owner ids.

Pearson `g002` should remain optional for this slice. A non-live synthetic test can exercise
scale-like grouping and truncation without requiring the full live Pearson fixture.

## 16. Success criteria

This slice is complete when:

- `scene_object_semantic_context` exists as a read-only object semantic context card surface;
- `scene_semantic_relationships` remains the raw structured fact inspector;
- card targets are explicitly selectable/runtime scenegraph object nodes;
- block instances are eligible as single occurrence objects;
- block definitions and block definition contents are not expanded into cards;
- missing objects and no-fact objects return full card shapes;
- cards include summary counts, deterministic groups, bounded samples, and expandable group
  affordances;
- no sync, projection, inference, Rhino mutation, overlay geometry, recursive expansion, or
  whole-scene dump mode is added;
- focused pure and dispatch tests pass.

## 17. Future slices

Later slices can build on this card read model:

- details-on-demand expansion by `groupKey`;
- object-to-object semantic path views;
- assembly, system, route, or load-path summaries;
- optional visual scenegraph panel modes that consume cards rather than raw graph dumps;
- Rhino overlay/glyph display for accepted and candidate facts;
- geometry-to-fact candidate inference that emits the same fact shape with
  `status="candidate"`;
- contradiction detection between authored/imported facts and inferred candidate facts;
- block-aware occurrence/definition hierarchy views once Rook has a stable block scene model.

Those are intentionally deferred until the object card contract is stable.
