# Authored Graph Schema v2 Design

> Branch/worktree: `codex/authored-graph-schema-v2` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen `codex/profile-boundary-audit-v1` slice. Do not add more
> commits to `codex/profile-boundary-audit-v1` unless review feedback requires it.

## 1. Context

The relationship fact projection substrate now supports:

- authored graph user text hydration from Rhino objects;
- projection into Python-only `relationship_fact_v1` scenegraph edges;
- raw semantic relationship inspection;
- selected-object semantic context cards;
- profile-enriched labels, inverse labels, categories, and contact-kind display hints.

The current authored graph user text vocabulary still carries early Pearson robot experiment terms as
parser-facing schema:

```text
rook.graph.visual_type = member | joint
rook.graph.member_id
rook.graph.node_id
rook.graph.owner
rook.graph.owner_kind = member | node
```

That was useful while proving the first robot fixture, but it is now the wrong kernel vocabulary.
Rook needs an authored relationship graph schema that can support robot, architecture, product,
infrastructure, and future inferred facts without making any one domain part of the parser contract.

The guiding principle is:

```text
opinionated kernel + extensible semantic/profile layer
```

not:

```text
fully generic thing/link/tag
```

The kernel should be domain-neutral but typed. It should not become vague; it should name the stable
concepts that relationship reasoning actually needs.

## 2. Goal

Define Authored Graph Schema v2 and migration scope.

V2 cleans up parser-facing user text keys so Rook's core vocabulary is precise, neutral, and stable:

```text
object / object_kind
feature / feature_kind
relationship / relationship_type
relationship_fact
contact_kind
provenance
confidence
status
evidence
```

Domain terms such as `member`, `joint`, `column`, `wall`, `door`, `duct`, `supports`, and
`hosted_by` remain valid as data values and profile entries. They are not valid as core parser key
names or visual-type branches.

## 3. Kernel Boundary

The v2 vocabulary preserves this boundary:

```text
object/object_kind
  occurrence identity and coarse typed role

feature/feature_kind
  addressable semantic or geometric attachment point on an object

relationship/relationship_type
  asserted or inferred fact connecting two addressable features

contact_kind
  geometric/contact shape of the relationship

profile
  labels, inverse labels, categories, contact-kind display, and future domain vocabulary mappings
```

This is domain-neutral but typed. It is not generic `thing/link/tag` modeling.

## 4. Canonical v2 User Text Vocabulary

Every graph-authored Rhino object still carries common scope keys:

```json
{
  "rook.graph.source": "pearson_robot_skeleton_graph",
  "rook.graph.revision": "g002",
  "rook.graph.pose": "rest_t_pose",
  "rook.graph.visual_type": "object"
}
```

`source`, `revision`, and `pose` remain required for graph records.

### 4.1 Object Records

Object records represent selectable/runtime Rhino owner objects.

Canonical v2 user text:

```json
{
  "rook.graph.visual_type": "object",
  "rook.graph.object_id": "column_01",
  "rook.graph.object_kind": "column",
  "rook.graph.feature_ids": "column_01.top_point",
  "rook.graph.relationship_ids": "column_01.top_point_supports_slab_01.underside_region",
  "rook.graph.display_name": "Column 01"
}
```

Required object keys:

- `rook.graph.visual_type = object`
- `rook.graph.object_id`
- `rook.graph.object_kind`

Optional object keys:

- `rook.graph.feature_ids`
- `rook.graph.relationship_ids`
- `rook.graph.display_name`
- domain-specific metadata, such as `rook.graph.arch_kind`, if still useful as data

The Pearson robot can still use:

```json
{
  "rook.graph.visual_type": "object",
  "rook.graph.object_id": "spine_base",
  "rook.graph.object_kind": "joint"
}
```

and:

```json
{
  "rook.graph.visual_type": "object",
  "rook.graph.object_id": "spine_base_to_spine_top",
  "rook.graph.object_kind": "member"
}
```

The cleanup is about removing `member_id`, `node_id`, and `visual_type=member|joint` as parser-facing
schema. It is not about banning `member` or `joint` as data values.

### 4.2 Feature Records

Feature records identify addressable semantic or geometric attachment points on owner objects.

Canonical v2 user text:

```json
{
  "rook.graph.visual_type": "feature",
  "rook.graph.feature_id": "column_01.top_point",
  "rook.graph.owner_id": "column_01",
  "rook.graph.owner_kind": "column",
  "rook.graph.feature_kind": "point",
  "rook.graph.role": "top_point"
}
```

Required feature keys:

- `rook.graph.visual_type = feature`
- `rook.graph.feature_id`
- `rook.graph.owner_id`
- `rook.graph.feature_kind`

Optional feature keys:

- `rook.graph.owner_kind`
- `rook.graph.role`
- `rook.graph.true_position_m`
- `rook.graph.visual_lift_m`
- other measured or authored evidence fields

Feature resolution should use `owner_id`, not `owner_kind`. If `owner_kind` is present, the parser
should validate it against the resolved owner object's `object_kind` and emit a validation diagnostic
on mismatch. This keeps `owner_kind` useful as denormalized evidence without making it a second
source of truth.

### 4.3 Relationship Records

Relationship records stay aligned with the already-proven `RelationshipFact` model.

Canonical v2 user text:

```json
{
  "rook.graph.visual_type": "relationship",
  "rook.graph.relationship_id": "column_01.top_point_supports_slab_01.underside_region",
  "rook.graph.relationship_type": "supports",
  "rook.graph.from_feature": "column_01.top_point",
  "rook.graph.to_feature": "slab_01.underside_region",
  "rook.graph.contact_kind": "point_to_region",
  "rook.graph.provenance": "authored_architectural_fixture",
  "rook.graph.confidence": "1.0",
  "rook.graph.status": "accepted"
}
```

Required relationship keys:

- `rook.graph.visual_type = relationship`
- `rook.graph.relationship_id`
- `rook.graph.relationship_type`
- `rook.graph.from_feature`
- `rook.graph.to_feature`

Optional relationship keys:

- `rook.graph.contact_kind`
- `rook.graph.provenance`
- `rook.graph.confidence`
- `rook.graph.status`
- `rook.graph.sourceMode`
- `rook.graph.evidence`
- position/debug visualization fields such as `from_feature_position_m`, `to_feature_position_m`,
  `marker_start_m`, and `marker_end_m`

Defaults remain:

- `confidence = 1.0`
- `status = accepted`
- `sourceMode = authored_graph_user_strings`

The default provenance may remain `authored_assembly_graph` for compatibility with existing
relationship fact behavior, but fixtures should stamp explicit provenance.

## 5. Removed or Renamed v1 Keys

V2 removes these parser-facing owner keys:

```text
rook.graph.visual_type = member
rook.graph.visual_type = joint
rook.graph.member_id
rook.graph.node_id
rook.graph.owner
```

Replacement keys:

```text
rook.graph.visual_type = object
rook.graph.object_id
rook.graph.object_kind
rook.graph.owner_id
```

Mapping:

| v1 | v2 |
| --- | --- |
| `visual_type=member` | `visual_type=object`, `object_kind=member` |
| `visual_type=joint` | `visual_type=object`, `object_kind=joint` |
| `member_id` | `object_id` |
| `node_id` | `object_id` |
| feature `owner` | feature `owner_id` |
| feature `owner_kind=node` | feature `owner_kind=joint` if representing a robot joint |

Relationship keys already use neutral language and remain mostly unchanged.

## 6. Fixture Migration Scope

V2 applies to both persisted authored fixture JSON and emitted Rhino user text. Generator local
variables may still use short names such as `owner` while computing geometry, but checked-in graph
schema and stamped user text should use v2 names.

### 6.1 Architectural Fixture

The architectural authored graph JSON is conceptually close to v2, but it must migrate its persisted
schema names too.

Current source JSON shape:

```json
{
  "objects": [{"id": "column_01", "kind": "column"}],
  "features": [{"owner": "column_01", "owner_kind": "column"}],
  "relationships": [{"type": "supports"}]
}
```

Canonical v2 source JSON shape:

```json
{
  "objects": [{"object_id": "column_01", "object_kind": "column"}],
  "features": [
    {
      "feature_id": "column_01.top_point",
      "owner_id": "column_01",
      "feature_kind": "point",
      "owner_kind": "column"
    }
  ],
  "relationships": [
    {
      "relationship_id": "column_01.top_point_supports_slab_01.underside_region",
      "relationship_type": "supports",
      "from_feature": "column_01.top_point",
      "to_feature": "slab_01.underside_region",
      "contact_kind": "point_to_region"
    }
  ]
}
```

The generated Rhino script still emits v1 parser-facing owner keys:

```text
visual_type=member
member_id=obj["id"]
owner_kind=member
```

Migration required:

- migrate `objects[].id` to `objects[].object_id`;
- migrate `objects[].kind` to `objects[].object_kind`;
- migrate `features[].id` to `features[].feature_id`;
- migrate `features[].owner` to `features[].owner_id`;
- keep `features[].feature_kind`;
- keep `features[].owner_kind` only as optional denormalized metadata and validate it against
  `objects[].object_kind`;
- migrate `relationships[].id` to `relationships[].relationship_id`;
- migrate `relationships[].type` to `relationships[].relationship_type`;
- migrate `relationships[].from` to `relationships[].from_feature`;
- migrate `relationships[].to` to `relationships[].to_feature`;
- emit `visual_type=object`;
- emit `object_id=obj["object_id"]`;
- emit `object_kind=obj["object_kind"]`;
- emit feature `owner_id=feature["owner_id"]`;
- emit feature `owner_kind=feature["owner_kind"]` only when present;
- update tests that assert the generated script contains old keys.

### 6.2 Pearson Robot Fixture

Pearson currently uses domain-shaped top-level graph sections:

```text
nodes
members
features
relationships
```

and feature owner kinds:

```text
node
member
```

Migration required:

- introduce or derive a canonical `objects` list for the authored graph;
- represent former `nodes` as objects with `object_kind=joint` or a more specific robot data value;
- represent former `members` as objects with `object_kind=member`;
- migrate features to `feature_id`, `owner_id`, and `feature_kind`;
- use optional `owner_kind=joint` for former node-owned features only as denormalized metadata;
- migrate relationships to `relationship_id`, `relationship_type`, `from_feature`, and `to_feature`;
- regenerate `generated/skeleton_graph_rhino.py` from the updated script;
- update Pearson helper/tests to expect v2 user text while preserving expected counts:
  - 2 poses;
  - 30 joint-like objects total across poses;
  - 28 member-like objects total across poses;
  - 86 feature objects;
  - 56 relationship marker objects;
  - 200 created objects.

The actual relationship facts should remain unchanged:

```text
28 per pose
56 total
relationship_type = connects
contact_kind = point_to_point
```

## 7. Parser Compatibility Stance

Approach A, direct v2 migration, is canonical.

The parser should accept v2 as the primary path:

```text
visual_type=object
object_id
object_kind
feature owner_id
```

Preferred implementation is v2-only after migrating tests and fixtures.

If implementation reveals a short transitional branch is materially safer, it must be:

- private to `relationship_fact_projection.py`;
- tested as legacy input;
- diagnostic-emitting, for example `legacyAuthoredGraphV1Records`;
- not documented as a supported public schema;
- removed in a later cleanup once stacked work no longer depends on v1 fixtures.

Do not add a public compatibility layer just to preserve `member_id` or `node_id`.

## 8. Projection Output Contract

Projected `relationship_fact_v1` edges should retain the existing stable output fields:

```text
relationship
semanticRelationshipType
fromFeature
toFeature
fromFeatureObjectId
toFeatureObjectId
relationshipObjectId
contactKind
provenance
confidence
status
graphSource
graphRevision
pose
sourceMode
```

Owner-kind attributes inside `RelationshipFact` should reflect v2 data values:

```text
from_owner_kind = member | joint | column | wall | ...
to_owner_kind = member | joint | slab | wall | ...
```

These are data/profile vocabulary values, not parser branch names.

## 9. Tests Required

Pure projection parser tests:

- v2 owner object records parse with `visual_type=object`, `object_id`, and `object_kind`;
- missing `object_id` reports the owner-id diagnostic;
- missing `object_kind` reports an owner-kind diagnostic;
- feature records require `owner_id` and `feature_kind`;
- feature records may include optional `owner_kind`;
- if feature `owner_kind` is present and does not match resolved owner `object_kind`, projection reports
  an owner-kind mismatch diagnostic;
- relationship records remain compatible with existing fact fields;
- v2 owner-object projection produces owner-object-to-owner-object edges;
- if any transitional v1 branch is implemented, legacy input emits a legacy diagnostic and v2 tests remain the primary tests.

Tool/projection tests:

- `scene_project_relationship_facts` test fixtures use v2 user strings;
- object-scoped filtering still filters by resolved owner object ids;
- strict mode still fails only on validation diagnostics, not normal filters.

Architectural fixture tests:

- checked-in generated script emits v2 object and feature keys;
- non-live architectural fixture tests still pass;
- live architectural fixture gate still creates the expected fixture and cards when Rhino is available.

Pearson robot tests:

- graph drift check verifies the generated script embeds the current v2 graph;
- non-live Pearson g002 expected facts still expand to 56;
- live Pearson g002 gate still passes when Rhino is available;
- helper assertions are updated from v1 key expectations to v2 key expectations.

Inspector/card/profile tests:

- `scene_semantic_relationships` still reports the same structured facts;
- `scene_object_semantic_context` still summarizes selected objects;
- profile enrichment remains unchanged;
- profile boundary guard remains valid.

## 10. Out of Scope

This slice does not:

- add IFC, BOT, Brick, RDF, or ontology imports;
- add geometry inference;
- add display modes or Rhino overlays;
- add profile authoring tools;
- change the raw relationship fact edge output contract except owner-kind values becoming neutral data
  values;
- broaden the profile boundary guard.

## 11. Success Criteria

The schema-v2 slice is complete when:

- Authored Graph Schema v2 is documented as domain-neutral but typed;
- parser-facing owner keys use `object_id` / `object_kind`;
- feature records use `owner_id`;
- persisted fixture JSON uses v2 field names, not only emitted Rhino user text;
- `member_id`, `node_id`, and `visual_type=member|joint` are gone from migrated fixtures/tests;
- domain terms remain valid as data values and profile entries;
- projection, inspector, card, profile, architectural fixture, and Pearson g002 tests pass;
- any v1 compatibility path, if added, is private, diagnostic-emitting, and tested as legacy only.
