# Relationship Profile v1 - design

> Status (2026-06-28): DESIGN - ready for review.
> Branch/worktree: `codex/relationship-profile-v1` at
> `C:/Users/aryan/source/repos/Rook/.worktrees/pearson-robot-feature-graph`.
>
> This branch is stacked on the frozen architectural relationship fixture slice. Do not add more
> commits to `codex/architectural-relationship-fixture-v1` unless review feedback requires it.

## 1. Reviewer Backfill

The previous stack added a neutral semantic relationship substrate:

- `scene_project_relationship_facts` hydrates authored Rhino `rook.graph.*` user text and projects
  owner-object-to-owner-object `relationship_fact_v1` edges into `SceneGraphAnalytics.graph`.
- `scene_semantic_relationships` is the raw object-centric inspector over already-projected
  relationship facts.
- `scene_object_semantic_context` is the bounded selected-object card/view-model layer over the raw
  inspector.
- The Pearson robot fixture proves the substrate at scale.
- The architectural fixture proves the substrate can express architecture-flavored authored facts:
  `supports`, `hosted_by`, `voids`, `penetrates`, and `bounded_by`.

The architectural fixture exposed the next risk: relationship vocabulary is starting to appear as
fixed strings in tests and card output. Before geometry evidence or inference grows around these
names, relationship semantics should become data-defined.

## 2. Goal

Add a read-only relationship profile layer:

```text
built-in default relationship profile
+ optional explicit project relationship profile
-> validated vocabulary metadata
-> scene_relationship_profile read surface
-> optional additive enrichment in object semantic cards
```

The profile should supply labels, inverse names, categories, and contact-kind hints without changing
the truth of relationship facts.

## 3. Non-Goals

This slice must not:

- add geometry evidence or inference;
- change relationship fact projection;
- change authored graph parsing;
- change semantic relationship grouping identity;
- reject unknown relationship names in facts;
- add profile write/update/suggest tools;
- add YAML support;
- read `.rook` from process cwd;
- walk upward looking for a project root;
- add ontology, IFC, BOT, Brick, RDF, TopologicPy, or Revit dependencies;
- make card prose authoritative.

## 4. Profile Files

Add a checked-in default profile:

```text
mcp_server/src/rook/scene/default_relationship_profile.json
```

Optional project profile:

```text
<project_root>/.rook/relationship_profile.json
```

Both files use the same schema marker:

```json
{
  "schema": "rook.relationship_profile.v1"
}
```

V1 supports JSON only. YAML can be considered later if a project-wide YAML dependency and policy
already exist, but this slice should not add YAML parsing.

## 5. Project Root Rules

Profile resolution must be explicit and deterministic.

Default:

```text
scene_relationship_profile()
-> built-in default profile only
```

Project override:

```text
scene_relationship_profile(project_root="C:/path/to/project")
-> built-in defaults + C:/path/to/project/.rook/relationship_profile.json
```

Rules:

- `project_root` is optional.
- If supplied, `project_root` must be an absolute path.
- No process-cwd fallback.
- No upward directory walking.
- No writes.
- Missing project profile is success with `projectProfileLoaded: false`.
- Present but invalid project profile is `success: false` with diagnostics.
- The response includes `profileSources` so agents can tell whether they are using defaults only or
  project-specific vocabulary.

`scene_object_semantic_context` must also accept:

```text
project_root?: str
```

with identical resolver rules. This preserves the no-hidden-cwd principle: cards can only use
project-specific vocabulary when the caller explicitly supplies the project root.

## 6. Profile Shape

The default profile should be small and practical, seeded by relationship names already present in
the stack:

```json
{
  "schema": "rook.relationship_profile.v1",
  "relationships": {
    "connects": {
      "label": "connects",
      "inverse": "connected by",
      "category": "assembly"
    },
    "supports": {
      "label": "supports",
      "inverse": "supported by",
      "category": "support"
    }
  },
  "contactKinds": {
    "point_to_point": {
      "label": "point to point",
      "category": "discrete_contact"
    }
  },
  "objectKinds": {
    "column": {
      "label": "column",
      "category": "architecture"
    }
  }
}
```

Required top-level fields:

- `schema`
- `relationships`

Optional top-level fields:

- `contactKinds`
- `objectKinds`
- `metadata`

Relationship entries may include:

- `label`
- `inverse`
- `category`
- `description`
- `defaultContactKinds`

Contact-kind entries may include:

- `label`
- `category`
- `description`

Object-kind entries may include:

- `label`
- `category`
- `description`

The module should tolerate unknown extra fields by preserving them in the resolved profile entry
rather than failing. This keeps the profile forward-compatible.

## 7. Merge Semantics

Merge behavior is shallow per entry.

For example:

```json
{
  "relationships": {
    "supports": {
      "label": "structurally supports"
    }
  }
}
```

overlays only the `supports.label` field and preserves other built-in fields for `supports`.

Rules:

- Project `relationships.<key>` overlays built-in `relationships.<key>` by field.
- Project `contactKinds.<key>` overlays built-in `contactKinds.<key>` by field.
- Project `objectKinds.<key>` overlays built-in `objectKinds.<key>` by field.
- New project keys extend the profile.
- Top-level `metadata` is shallow-merged.
- No recursive merge inside nested objects or lists.
- Lists replace lists.
- Scalars replace scalars.

This is deliberately simple. Recursive ontology-like merge semantics are out of scope.

## 8. Unknown Vocabulary

Unknown relationship names remain valid facts.

When an inspector/card sees a relationship not present in the resolved profile, the profile layer
should provide a fallback entry:

```json
{
  "key": "custom_relationship",
  "label": "custom_relationship",
  "inverse": "connected by",
  "category": "unknown",
  "source": "fallback"
}
```

Unknown contact kinds should similarly fall back to their raw key as the label and `category:
"unknown"`.

Fallback entries are response-time conveniences. They should not mutate the built-in or project
profile file.

## 9. New Module

Add:

```text
mcp_server/src/rook/scene/relationship_profile.py
```

Responsibilities:

- load the built-in default JSON profile;
- optionally load `<project_root>/.rook/relationship_profile.json`;
- validate schema and expected top-level shapes;
- merge built-in and project profiles;
- return source metadata and diagnostics;
- provide lookup helpers for relationship/contact/object-kind entries;
- provide fallback entries for unknown names.

Keep the module independent of Rhino and `SceneGraphAnalytics`. It should be pure filesystem/data
logic.

## 10. New Tool

Add a read-only MCP/local tool:

```text
scene_relationship_profile(project_root?: str)
```

Response shape:

```json
{
  "success": true,
  "schema": "rook.relationship_profile.v1",
  "projectProfileLoaded": false,
  "profileSources": [
    {
      "kind": "default",
      "path": "mcp_server/src/rook/scene/default_relationship_profile.json",
      "loaded": true
    },
    {
      "kind": "project",
      "path": null,
      "loaded": false,
      "reason": "project_root_not_supplied"
    }
  ],
  "profile": {
    "relationships": {},
    "contactKinds": {},
    "objectKinds": {},
    "metadata": {}
  },
  "diagnostics": {}
}
```

Invalid absolute path/project profile examples:

```json
{
  "success": false,
  "error": "invalid_project_root",
  "message": "project_root must be an absolute path in v1",
  "diagnostics": {
    "invalidProjectRoot": 1
  }
}
```

```json
{
  "success": false,
  "error": "invalid_relationship_profile",
  "message": "Project relationship profile is invalid",
  "diagnostics": {
    "invalidSchema": 1
  }
}
```

Tool registration should follow the recent scene tool pattern:

- server schema and `_call_tool_dispatch`;
- local `rook.agent.tool_dispatcher` registration;
- `scene_graph` tool group inclusion;
- read-only targeting policy.

The tool is Rhino-independent read-only.

## 11. Card Enrichment

`scene_object_semantic_context` should accept:

```text
project_root?: str
```

It should resolve the relationship profile and enrich card facts/groups additively.

Fact sample enrichment:

```json
{
  "relationship": "supports",
  "relationshipLabel": "supports",
  "inverseRelationship": "supported by",
  "relationshipCategory": "support",
  "contactKind": "point_to_region",
  "contactKindLabel": "point to region",
  "contactKindCategory": "region_contact"
}
```

Group enrichment:

```json
{
  "groupKey": "supports:outgoing:accepted:authored_architectural_fixture",
  "relationship": "supports",
  "relationshipLabel": "supports",
  "inverseRelationship": "supported by",
  "relationshipCategory": "support"
}
```

Summary enrichment may add:

```json
{
  "byRelationshipCategory": {
    "support": 1
  }
}
```

Existing fields remain unchanged:

- `relationship`
- `direction`
- `status`
- `provenance`
- `groupKey`
- `byRelationship`
- `relationshipFactCount`
- `relationshipViewCount`

Profile metadata is additive only. It must not affect grouping identity, counts, filters, or fact
truth.

If `project_root` is supplied and the project profile is invalid, the card request should fail with
the same profile diagnostics rather than silently falling back to defaults. Missing project profile
is not an error.

## 12. Default Profile Seed

The default profile should include at least:

Relationships:

- `connects`
- `supports`
- `hosted_by`
- `voids`
- `penetrates`
- `bounded_by`

Contact kinds:

- `point_to_point`
- `point_to_region`
- `body_to_region`
- `profile_to_region`
- `line_to_region`
- `boundary_to_face`

Object kinds:

- robot/assembly-flavored: `member`, `joint`
- architecture-flavored: `column`, `slab`, `wall`, `door`, `opening`, `duct`, `space`

These defaults are pragmatic labels and categories, not ontology commitments.

## 13. Testing

Pure profile tests:

- loads built-in default profile;
- rejects missing/invalid schema;
- rejects non-absolute `project_root`;
- missing project file succeeds with `projectProfileLoaded: false`;
- valid project file extends relationships/contact kinds/object kinds;
- valid project file shallow-overrides one field while preserving other built-in fields;
- invalid project file returns structured diagnostics;
- unknown relationship/contact lookup returns fallback entries without mutating profile.

Tool tests:

- `scene_relationship_profile` appears in MCP schema;
- server dispatch returns built-in profile when `project_root` is omitted;
- server dispatch rejects relative `project_root`;
- local dispatcher registers the tool;
- tool group contains the tool;
- targeting policy is Rhino-independent read-only.

Card tests:

- `scene_object_semantic_context(project_root=None)` enriches samples/groups from built-in defaults;
- explicit project profile overrides a label/category in card output;
- invalid project profile fails card request with profile diagnostics;
- existing grouping/count/filter semantics are unchanged.

Architectural fixture regression:

- architectural fixture card assertions can check `supports`, `hosted_by`, `penetrates`, and
  `bounded_by` category/label metadata from the default profile.

No live Rhino test is required for this slice because profile resolution and card enrichment are
Python-side read-only behavior. Existing architectural live gate remains a useful downstream smoke,
but it should not be required for profile v1.

## 14. Success Criteria

This slice is complete when:

- the default relationship profile is checked in;
- `scene_relationship_profile` exposes the resolved profile with explicit source metadata;
- project profile loading is opt-in via absolute `project_root`;
- `scene_object_semantic_context` accepts the same `project_root` and enriches output additively;
- invalid project profiles fail clearly;
- unknown relationships remain valid through fallback entries;
- no production projection/parser/inference behavior changes;
- focused profile, tool, card, and existing semantic tests pass.

## 15. Future Slices

Later work can add:

- profile authoring or guarded update tools;
- profile suggestions from observed authored facts;
- ontology predicate pass-through fields;
- geometry evidence rules that reference relationship/contact profile categories;
- contradiction checks between authored facts and inferred candidates;
- project-specific relationship profile discovery from active Rhino document metadata.

Those are intentionally deferred. V1 should make vocabulary data-defined without making it
self-mutating or inferential.
