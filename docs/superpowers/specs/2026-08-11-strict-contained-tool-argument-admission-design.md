# Strict Contained-Tool Argument Admission

**Status:** Implementation-ready production contract

**Date:** 2026-08-11

**Baseline:** `06534f371b173308179164189e54b722a34f8a24`

## Purpose

Make `rook_tools_call` reject unknown top-level target arguments before target dispatch.
The correction is generic, schema-owned, and independent of Prime, Qwen, Grasshopper,
or any individual tool.

The triggering retained Qwen row called:

```text
gh_library({"query": ...})
```

The authoritative schema admits `search`, not `query`. Because the existing validator
checks required fields, declared-field types, enums, and numeric bounds but ignores unknown
keys, the request became catalog browsing. The model repeatedly consumed a bounded catalog
page, failed to find `Series`, substituted a hard-coded topology, and falsely reported
semantic success.

## Ownership

The existing owners remain unchanged:

```text
rook_tools_call
-> capability index retrieves the target's authoritative live input schema
-> capability_index.validate_arguments() validates the untrusted argument object
-> invalid_arguments stops before call_tool() re-entry
-> admitted arguments enter the existing target policy and dispatch path unchanged
```

`mcp_server/src/rook/capability_index.py` remains the sole argument-validation owner.
`mcp_server/src/rook/server.py` retains guard ordering and target dispatch. No new production
module, schema copy, alias table, retry, fallback, or validation taxonomy is introduced.

## Considered Approaches

### 1. Extend `validate_arguments()` — selected

Compare the caller's top-level keys with the target schema's top-level `properties` keys.
This uses the already-authoritative schema and existing error envelope, affects every
contained target consistently, and adds no dependency.

### 2. Add per-tool validation for `gh_library` and `gh_batch_component_info` — rejected

This would fix only the witnessed spellings, duplicate schema knowledge, and allow the same
silent degradation on other tools.

### 3. Add a general JSON Schema engine — rejected

Full recursive JSON Schema validation is broader than the demonstrated defect, would add
new validation semantics and possibly a dependency, and is unnecessary for top-level
admission.

## Closed Validation Contract

For a contained target request:

```text
allowed = sorted authoritative input_schema.properties keys
unknown = sorted caller argument keys not in allowed
```

When `unknown` is nonempty, `validate_arguments()` adds this exact deterministic field error:

```text
unknown fields: <comma-separated unknown>; accepted fields: <comma-separated allowed>
```

For a schema with no admitted top-level fields, the accepted-field suffix is:

```text
accepted fields: <none>
```

Unknown-field validation is top-level only. Existing required-field, type, enum, array-item,
minimum, and maximum validation remains unchanged and may report additional errors in the
same `fields` list. Unknown-field evidence appears first.

The existing contained-call envelope remains:

```json
{
  "success": false,
  "data": {
    "error": "invalid_arguments",
    "name": "gh_library",
    "fields": [
      "unknown fields: query; accepted fields: audit, category, exact, limit, search"
    ]
  }
}
```

The existing public MCP projection makes this a truthful MCP error while retaining the
legacy text projection. No new result type is added.

## Guard Ordering and Contact Boundary

The existing ordering remains authoritative:

```text
meta recursion
-> readonly profile wall
-> target existence / MCP dispatchability
-> arguments-is-object
-> target-schema validation, including unknown fields
-> call_tool() re-entry
```

An unknown-field refusal performs zero target dispatch, Rhino, Grasshopper, provider, or
other external contact. Capability-index lookup is local schema custody, not target contact.
Readonly default-deny behavior continues to precede validation and must not become a hidden
surface enumeration oracle.

## Compatibility

- Every request using only declared fields behaves exactly as before.
- Requests with unknown top-level fields intentionally change from accidental acceptance to
  `invalid_arguments`.
- No `query` alias is added for `search`.
- No singular `name` alias is added for `names` or `guids`.
- Nested object validation is unchanged.
- Direct `server.call_tool()` consumers and ChatRunner direct dispatch remain unchanged.
- Tool schemas, discovery ranking, Grasshopper execution, and result projection remain
  unchanged.

The baseline live-schema audit found 382 public live tools, including 43 tools with no
top-level properties. No target schema deliberately admits arbitrary top-level fields through
`additionalProperties: true` or an `additionalProperties` schema.

## Tests

Focused causal tests must prove:

1. `validate_arguments()` refuses one and multiple unknown fields in sorted order and reports
   the complete sorted accepted-field list.
2. A zero-argument schema reports `accepted fields: <none>`.
3. Existing valid, required, type, enum, numeric-bound, array-item, and boolean rejection
   behavior remains unchanged.
4. `rook_tools_call(gh_library, {"query": "Series"})` returns `invalid_arguments`, names
   `search` among accepted fields, and makes zero target calls.
5. `rook_tools_call(gh_batch_component_info, {"name": "Series"})` returns the same generic
   refusal, names `names` and `guids`, and makes zero target calls.
6. A valid contained request enters the target exactly once with exact arguments.
7. Readonly guard ordering remains unchanged.

Focused and adjacent no-contact Python suites must pass before deployment.

## Explicit Exclusions

- No aliases or spelling correction.
- No Prime or model changes.
- No prompt or skill changes.
- No mutation/call budget enforcement.
- No recursive schema validator.
- No planner, critic, scoring, retry, or fallback behavior.
- No Grasshopper, managed, native, or UI changes.

The model-authored excess correction observed in the Qwen row remains a separate later safety
boundary. This slice only ensures malformed contained arguments fail early and truthfully.
