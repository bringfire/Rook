# MCP Schema Array Hardening Design

> **PARTIALLY SUPERSEDED — Director MCP retirement (2026-07-13):** The general
> non-Director architecture and dated evidence in this document remain available.
> All `rhino_director_*`, `/director`, VisionDirector, and Director-domain examples,
> allowlist entries, count assumptions, acceptance criteria, and positive dispatch
> tests are superseded as of 2026-07-13. Replace those examples with
> non-Director fixtures when maintaining or replaying this work. This document must
> not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: 2026-07-13-director-mcp-surface-retirement-design.md

## Context

PR #168 shipped Director timeline authoring and a targeted `rhino_create` MCP
schema/runtime correction. During that work, a broader schema hygiene issue was
found: many MCP tool input schemas allow arrays without declaring an `items`
contract. This came from early loose schema authoring and affects agent-facing
tool discovery directly. Clients can be guided toward payload shapes that pass
discovery but fail runtime validation.

The follow-up work must be a focused MCP hardening PR, separate from Director
work. The intended code boundary is Python MCP schema declarations in
`mcp_server/src/rook/server.py` plus regression coverage in
`mcp_server/tests/test_server_contract_hardening.py`.

## PR Boundary

Make every registered MCP tool input schema structurally explicit wherever an
array is permitted.

This includes both:

- Exact array schemas: `{"type": "array"}` must define `items`.
- Union schemas that permit arrays, such as
  `{"type": ["string", "array", "object"]}`, must define `items` for the
  accepted array form.

Do not split RoadCreator/profile or Grasshopper workflow schemas out of the PR.
The contract invariant is global across registered MCP tool schemas, so
`rc_build_profile` and `gh_explore_workflow` should be corrected in the same
mechanical pass.

Do not touch native C++ or managed C# unless implementation discovers a concrete
contradiction that cannot be fixed in MCP schemas alone. This design expects no
native or managed changes.

## Schema Helpers

Add small local helpers near the existing schema constants in `server.py`.
Helpers should return fresh dictionaries so call sites cannot accidentally
mutate shared schema objects.

Expected helper set:

- `_number_array_schema(description, *, min_items=None, max_items=None)`
- `_integer_array_schema(description, *, min_items=None, max_items=None)`
- `_point3_schema(description)`
- `_vector3_schema(description)`
- `_point3_list_schema(description, *, min_items=None)`
- `_string_array_schema(description, *, min_items=None)`
- `_object_array_schema(description, *, min_items=None)`
- `_color_schema(description)`

The helper names may be adjusted to match local style, but the implementation
should preserve these distinctions: points/vectors are numeric 3-arrays,
polylines/leaders are arrays of numeric 3-arrays, GUID/string lists are string
arrays, RoadCreator/profile and workflow collections are object arrays, and
color arrays are integer RGB triples while retaining accepted string/object
forms.

Color schemas that currently accept string, array, or object should keep those
forms but explicitly define the array branch:

```python
{
    "type": ["string", "array", "object"],
    "items": {"type": "integer"},
    "minItems": 3,
    "maxItems": 3,
    "description": "...",
}
```

JSON Schema applies `items` only to array instances, so this remains compatible
with string and object colors while documenting the array payload shape.

## Implementation Shape

Replace missing `items` declarations mechanically in `server.py`, using the
helpers rather than hand-copying schema fragments.

Coordinate-like affected fields should use numeric 3-array helpers. This covers
transform vectors, annotation points, array axes, block insertion/base points,
split/trim planes, mesh/SubD centers/origins, closest-point inputs, and related
coordinate fields.

Nested coordinate collections, such as annotation leader `points`, should use
an array-of-point3 helper and preserve existing constraints such as minimum
polyline point count.

Non-coordinate arrays must not be forced into numeric arrays:

- `rc_build_profile.features`
- `rc_build_profile.observations`
- `rc_build_profile.surfaces`
- `rc_build_profile.elements`
- `gh_explore_workflow.workflow.components`
- `gh_explore_workflow.workflow.wiring`

These should become object arrays unless a nearby implementation contract proves
a narrower item schema is already expected. Avoid new deep object schemas in
this PR unless they are already documented by the runtime contract; the primary
goal is to make array acceptance explicit, not to redesign payload validation.

Do not change runtime validation behavior unless a schema correction exposes a
clear contradiction. Keep the `rhino_create` and `rhino_director_run`
protections from PR #168 intact, including OpenAI-compatible schema constraints
that avoid `oneOf`, `anyOf`, `allOf`, and `not`.

## Regression Test

Add a recursive test in `test_server_contract_hardening.py` that walks every
registered tool's `inputSchema`.

The test should fail for any schema dictionary where:

- `type == "array"` and `items` is absent.
- `type` is a list containing `"array"` and `items` is absent.

The walker should recurse through dictionaries and lists, including `properties`,
`items`, and future schema containers. Failure output should include precise
tool names and schema paths. The test should assert zero violations rather than
asserting a historical count such as 67 or 74.

Do not add allowlists for current offenders. If a future field genuinely accepts
free-form arrays, it should still declare intent with `items: {}`.

## Verification

Required local verification:

- `python -m pytest mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_director_mcp_tools.py -q`
- A direct recursive schema scan showing zero missing-array-items violations.
- `git diff --check`

Optional installed-runtime verification after a payload-only deploy:

- Run the same schema preflight against the installed AppData MCP runtime.

Do not claim native build verification for this PR.

## Out Of Scope

- Native C++ route behavior.
- Managed C# companion behavior.
- Runtime validation rewrites beyond contradictions exposed by schema cleanup.
- Deep semantic validation for RoadCreator/profile or GH workflow object items.
- Director feature work.

## Design Decision

The design intentionally chooses the stricter invariant: any schema that permits
arrays must define `items`, including union type schemas. This treats the PR as
a cleanup of early loose schema authoring rather than a spot fix for the exact
array findings from the PR #168 scan.
