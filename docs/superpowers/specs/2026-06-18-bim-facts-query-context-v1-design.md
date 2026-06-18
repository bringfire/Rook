# BIM Facts Query + Context v1 - design

> Status (2026-06-18): DESIGN - brainstorm complete, ready for review before writing-plans.
> Branch: `feature/bim-facts-query-context-v1`.
> Base: current `origin/main` after PR #270 (`5a307f0a`).
>
> This slice starts from a clean branch off `origin/main`. The old
> `feature/spatial-intelligence` branch is archival context only and is not the base for this work.

## 1. Goal

PR #270 made RookBIM sidecar facts first-class graph facts by projecting Revit host, room, and level
relationships into the Python `networkx.MultiDiGraph` scene mirror. Those facts are now present in
the read model, but users and agents still need a compact, reliable consumer surface.

The goal of v1 is to make already-projected BIM facts queryable and readable:

- add one canonical structured query tool, `scene_bim_facts`;
- add a small BIM summary block to `scene_context`;
- preserve the strict boundary between projection and query.

`scene_project_bim_relationships` remains the explicit enrichment step. `scene_bim_facts` reads the
current Python mirror only. It does not project, sync, hydrate, infer, or mutate external documents.

## 2. In scope

- New pure query module, likely `mcp_server/src/rook/scene/bim_facts_query.py`.
- New MCP scene tool:
  `scene_bim_facts(mode, object_ids?, room_id?, room_name?, level_name?, host_object_id?, detail?, limit?, sample_limit?)`.
- Local/agent-direct dispatcher support for the same tool.
- Query modes:
  - `object_context`
  - `room_members`
  - `level_members`
  - `hosted_elements`
  - `relationship_scan`
- Explicit no-projection failure when no BIM projection artifacts are present.
- Compact BIM block in `scene_context`.
- `scene_context(sync=false)` so callers can render the current enriched Python mirror without
  rebuilding it from Rhino.
- Unit tests for query behavior, response shape, caps, ambiguity, registration, targeting, and no
  hidden runtime calls.

## 3. Out of scope

- Automatic BIM projection inside the query tool.
- Automatic scene sync inside `scene_bim_facts`.
- Sidecar parsing in `scene_bim_facts`.
- New Revit, Rhino.Inside.Revit, C++, or C# behavior.
- Geometry inference, exact adjacency, containment refinement, calibration, or threshold tuning.
- Revit write-back or Rhino document mutation.
- Fuzzy room/level matching.
- Native `scene_query` retrofit.
- Convenience alias tools such as `scene_bim_room_members`; those can come later if usage patterns
  justify them.
- Full raw sidecar or large geometry payloads in query responses.

## 4. Hard invariants

`scene_bim_facts` must not call `analytics.sync()`, `call_rhino()`,
`scene_project_bim_relationships()`, `project_bim_relationships_for_tool()`, or any Rhino/Revit
route. It is a pure read over the current Python mirror.

The pure query module must not import:

- `call_rhino`
- `bim_relationship_projection.project_bim_relationships_for_tool`
- `exact_projection`
- `containment_refinement`

A source-guard test should enforce this.

BIM facts remain parallel graph facts:

- `provenance="rookbim_sidecar"` BIM facts are not collapsed into `contains_semantic`.
- `provenance="occt"` exact adjacency and `provenance="semantic_refiner"` containment remain
  separate.
- Querying BIM facts never feeds BIM labels into geometry inference.

## 5. Tool contract

```text
scene_bim_facts(
  mode: "object_context" | "room_members" | "level_members" | "hosted_elements" | "relationship_scan",
  object_ids?: string[],
  room_id?: string,
  room_name?: string,
  level_name?: string,
  host_object_id?: string,
  detail: "ids" | "compact" | "full" = "compact",
  limit?: int,
  sample_limit?: int
)
```

Tool classification:

- `requires_rhino=True`
- `risk="read"`
- scene/read tool group

The tool does not call Rhino, but it depends on live-session Python scene mirror state produced by
scene graph sync and BIM projection. The description should be explicit:

- reads only the current in-memory projected scene graph;
- does not sync Rhino;
- does not call Rhino or Revit routes;
- run `scene_project_bim_relationships` first.

Unknown `mode` and unknown `detail` are explicit input errors. `limit` and `sample_limit` are
clamped to mode-specific maxes and are never trusted directly.

## 6. Projection precondition

No projected BIM facts is a failed precondition, not an empty result.

Failure envelope:

```json
{
  "success": false,
  "error": "bim_projection_required",
  "message": "No BIM relationship projection is present in the scene graph. Run scene_project_bim_relationships first.",
  "bimProjectionPresent": false,
  "graphSequence": 123,
  "sidecarFingerprints": []
}
```

Include `graphSequence` and any detected BIM projection fingerprints in the failure envelope when
possible. If BIM projection exists but a selector finds no matching target, return `success=true`
with `bimProjectionPresent=true` and empty `results`.

Invalid or missing required mode inputs return `success=false` with
`error="invalid_bim_query_input"`; they are not treated as empty results.

## 7. Response envelope

Successful responses use one consistent envelope:

```json
{
  "success": true,
  "mode": "room_members",
  "bimProjectionPresent": true,
  "graphSequence": 123,
  "sidecarFingerprints": ["..."],
  "query": {},
  "summary": {
    "relationshipCounts": {
      "revit_hosted_by": 12,
      "revit_in_room": 280,
      "revit_on_level": 280
    },
    "effectiveLimit": 100,
    "totalCount": 42
  },
  "results": [],
  "truncated": false,
  "diagnostics": {}
}
```

`summary.relationshipCounts` or an equivalent structured field is required so agents can tell which
BIM fact families are currently projected. `summary.effectiveLimit` is included for every mode, even
when the response is not truncated.

For multi-object `object_context`, truncation is per object. Each object's `hostedElements` block
carries `totalCount`, `effectiveLimit`, and `truncated`. Top-level `truncated=true` if any child
block is truncated.

## 8. Detail levels

- `detail="ids"`: return object ids only for member lists and hosted lists.
- `detail="compact"`: default. Return object id, display/name, category, family, type, Revit ids,
  layer, and relevant BIM edge summary.
- `detail="full"`: return compact fields plus bounded graph node attributes and relevant edge
  attributes.

`full` means "full bounded graph record", not "full BIM export record." It excludes raw sidecar
payloads and large geometry fields by policy.

## 9. Mode semantics

### object_context

Input:

- `object_ids` required and non-empty.

For each requested object, return a per-object result. If the object is present but not BIM-joined,
include:

```json
{
  "objectId": "...",
  "bimJoined": false
}
```

Do not fail the whole call just because one requested object is not BIM-joined.

BIM-joined objects include:

- BIM identity annotations: Revit unique id, element id, category, family, type, name, level;
- outgoing facts:
  - `revit_hosted_by` targets;
  - `revit_in_room` targets;
  - `revit_on_level` targets;
- incoming facts:
  - hosted elements from incoming `revit_hosted_by` sources, capped by mode limits;
- lightweight peer context:
  - same-room count;
  - same-level count.

Do not return full same-room or same-level peer lists in `object_context`; callers should use
`room_members` or `level_members` intentionally for those.

### room_members

Inputs:

- `room_id` optional;
- `room_name` optional;
- at least one is required.

If both `room_id` and `room_name` are provided, they are conjunctive: both must match the same room
reference node.

Room selector matching is case-insensitive exact matching against:

- projected room node id;
- `roomUniqueId`;
- `roomNumber`;
- `roomName`;
- `displayName`.

If multiple room nodes match, fail with:

```json
{
  "success": false,
  "error": "ambiguous_bim_reference",
  "candidates": []
}
```

When exactly one room matches, return scene objects with outgoing `revit_in_room` edges to that room
node, capped by the room member limits.

### level_members

Input:

- `level_name` required.

Level selector matching is case-insensitive exact matching against:

- projected level node id;
- `levelName`;
- `displayName`.

Ambiguous matches fail with `error="ambiguous_bim_reference"` and candidate levels. A single match
returns scene objects with outgoing `revit_on_level` edges to that level node.

### hosted_elements

Input:

- `host_object_id` required.

`host_object_id` is the Rhino scene object id, not a Revit unique id. If later usage needs Revit-id
lookup, add a separate `host_revit_unique_id` input.

Return scene objects that have outgoing `revit_hosted_by` edges whose target is `host_object_id`.

### relationship_scan

Return counts and bounded samples for projected BIM relationship families. Samples include:

- relationship;
- source id and display/name;
- target id and display/name;
- sidecar fingerprint.

Samples are capped by `sample_limit`.

## 10. Limits

Limits are strict by mode:

- `object_context`: hosted examples default `10`, max `50`; same-room and same-level are counts
  only.
- `room_members`: default `100`, max `500`.
- `level_members`: default `100`, max `500`.
- `hosted_elements`: default `100`, max `500`.
- `relationship_scan`: samples default `20`, max `100`.

Every capped response includes `truncated=true`, `totalCount`, and the effective limit at the
relevant response level. The top-level `truncated` value is true if any part of the response is
truncated.

## 11. scene_context enhancement

`scene_context` keeps `sync=true` by default for backward compatibility. This slice adds
`sync=false` so callers can render the current enriched Python mirror without rebuilding it from
Rhino.

BIM blocks are only guaranteed after:

1. `scene_project_bim_relationships(...)`
2. `scene_context(object_ids=[...], sync=false)`

There is no auto-skip behavior. `scene_context` must not silently change sync policy based on
whether BIM projection artifacts happen to be present.

When rendering a BIM-joined object, `get_context()` adds a compact BIM block before or near the
relationship lines:

```text
BIM: Walls | Basic Wall | Generic 200mm
  Revit: element 12345, uniqueId ...
  Room: 101 Office
  Level: L1
  Hosted by: Wall-01
  Hosts: 3 elements
```

Rules:

- Render the block only when `rookbimJoined=true`.
- Use graph node attributes and projected graph edges only. Do not read sidecar files.
- `Hosted by` reads outgoing `revit_hosted_by` targets.
- `Hosts` count reads incoming `revit_hosted_by` sources.
- If multiple room or level edges exist, render a short comma-separated list capped at 3 entries,
  then `+N more`.
- Show hosted examples only if the implementation already has a clean capped representation;
  count-only is enough for v1.
- Avoid duplicating BIM edge details too aggressively. Generic edge lines can remain for now, but
  the BIM block is the readable summary.
- Add `sync` handling wherever `scene_context` is dispatched: MCP `call_tool` path and
  agent-local/direct path if applicable.

`scene_bim_facts` remains stricter: it never syncs and has no sync option.

## 12. Module shape

The pure query module should expose a library function similar to:

```python
query_bim_facts(
    analytics,
    *,
    mode,
    object_ids=None,
    room_id=None,
    room_name=None,
    level_name=None,
    host_object_id=None,
    detail="compact",
    limit=None,
    sample_limit=None,
) -> dict
```

This function reads `analytics.graph` and `analytics.sequence`. It may use constants shared with
`bim_relationship_projection` only if that does not import tool-boundary code. If sharing would drag
in runtime dependencies, duplicate the small relationship/projection-kind constants locally.

## 13. Registration and targeting

Register `scene_bim_facts` in:

- MCP tool schema in `mcp_server/src/rook/server.py`;
- MCP call dispatch in `mcp_server/src/rook/server.py`;
- local/agent dispatcher in `mcp_server/src/rook/agent/tool_dispatcher.py`;
- scene graph tool group;
- targeting policy and known-tool lists.

Also update `scene_context` schema and dispatch so `sync=false` passes through both MCP and
agent-local/direct paths. Partial wiring is a known risk and should be covered by tests.

## 14. Testing

Pure unit tests:

- projection absent returns `bim_projection_required`;
- unknown mode returns `invalid_bim_query_input`;
- unknown detail returns `invalid_bim_query_input`;
- missing mode-specific inputs return `invalid_bim_query_input`;
- ambiguous room/level selector returns `ambiguous_bim_reference`;
- `room_id` + `room_name` must match the same room node;
- projected-but-no-match returns `success=true` with empty results;
- `object_context` returns per-object `bimJoined=false` for unjoined objects;
- object context returns outgoing host/room/level facts and incoming hosted counts with per-object
  truncation;
- room, level, and hosted member modes respect detail levels, caps, `effectiveLimit`, `totalCount`,
  and `truncated`;
- `relationship_scan` returns relationship counts and bounded samples with relationship, source,
  target, and sidecar fingerprint;
- `full` excludes raw sidecar payloads and large geometry fields;
- source-guard test proves the query module does not import runtime/projection/inference modules.

Context tests:

- `scene_context(sync=false)` preserves projected facts and renders the BIM block;
- default `scene_context` behavior remains `sync=true`;
- BIM block uses outgoing `revit_hosted_by` for `Hosted by`;
- BIM block uses incoming `revit_hosted_by` for `Hosts`;
- room/level lists are capped at 3 with `+N more`.

Registration and targeting tests:

- tool schema includes all query inputs;
- MCP dispatch calls the pure query function without sync;
- local/agent dispatcher registers `scene_bim_facts`;
- `scene_context` sync flag passes through all dispatch paths;
- targeting classifies `scene_bim_facts` as Rhino-read/scene-read;
- tool groups include `scene_bim_facts`.

No live gate is required for the spec itself. Implementation can include a focused live smoke later,
but the v1 query logic is intentionally testable without Rhino because it reads the Python graph.

## 15. Implementation sequencing for the plan

The implementation plan should keep the pure query layer ahead of wiring:

1. Add `bim_facts_query.py` with projection-detection, validation, and response helpers.
2. Add offline tests for all query modes, selectors, details, caps, and failure envelopes.
3. Add source-guard tests for no hidden runtime/projection/inference imports.
4. Add `scene_context(sync=false)` dispatch support and BIM block formatting tests.
5. Register `scene_bim_facts` in MCP, local dispatcher, tool groups, and targeting.
6. Add registration/targeting tests and focused integration tests.

Do not implement projection, sync, geometry inference, or sidecar parsing in this slice.
