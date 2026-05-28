# RookBIM Runtime Category Resolution Design

Date: 2026-05-28

Status: Approved design. This is not an implementation plan.

Related context:

- `docs/CURRENT_ARCHITECTURE.md`
- `docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md`
- Live RookBIM validation on 2026-05-28 across 3D, plan, sheet,
  schedule, family document, same-process document switching, and
  multi-Revit-process routing.

## Goal

RookBIM category resolution should be deterministic against the active live
Revit document.

The first milestone is:

> Given a live Revit document and a category string, RookBIM can resolve,
> reject, or suggest categories with auditable evidence.

This replaces the emerging pattern of adding one-off category aliases whenever
a new discipline model exposes a category name mismatch. Revit remains the
source of truth. The knowledge graph may become an advisory suggestion layer
later, but it must not decide successful category resolution in the first
implementation.

## Problem

`rookbim_query_elements` currently accepts a simple string category. The Revit
implementation resolves that string mostly through `BuiltInCategory` enum-name
matching plus a small curated alias table.

Live tests have already found category round-trip and human-name gaps:

- `Generic Models` was returned by RookBIM but originally rejected as input.
- `Curtain Panels` was returned by RookBIM while `Curtain Wall Panels` worked.
- In the plumbing sample, `Pipe Fittings` and `Plumbing Fixtures` worked, while
  natural plumbing inputs such as `Pipes` and `Pipe Accessories` returned
  structured `invalid_category`.

Patching each name as an alias leads toward maintaining a giant static Revit
category map. That is the wrong authority boundary. Category availability is
document-scoped, Revit-version-scoped, document-type-scoped, and potentially
locale-sensitive.

## Non-Goals

This design does not implement:

- Knowledge graph read/write learning.
- Knowledge graph-backed successful resolution.
- Active-view category availability.
- View visibility or view template diagnostics.
- Category element counts in `rookbim_list_categories`.
- Revit document writes.
- Linked-model category resolution.
- A full static Revit category catalog.
- Localization-specific alias packs.
- A new public plugin, HTTP server, or MCP server.

## Architecture

Add a Revit-side runtime service:

```text
RevitCategoryResolver
  input:  active Document, category string
  output: BimCategoryResolution
```

`RevitCategoryResolver` lives in `src/RookBim/Revit` and is used by
`RevitQueryService` before applying `FilteredElementCollector.OfCategory`.

The resolver inspects the active document category table through the Revit API.
It does not call the knowledge graph. It returns structured resolution evidence
so query responses and failures explain what happened.

Every successful resolution, regardless of strategy, must return a live
`Autodesk.Revit.DB.Category` identity from the active document category table.
`BuiltInCategory` enum matches and curated aliases are lookup aids, not
authorities. They are successful only after the resolved category is verified
against the active document category table.

Add a document-wide category listing surface:

```text
GET /bim/categories
MCP tool: rookbim_list_categories
managed BIM op: list_categories
```

`rookbim_list_categories` lists runtime categories available in the active
document category table. In v1 it is document-wide only. It must not imply that
a category has elements, is shown in the active view, or will produce nonzero
query results.

Existing query behavior remains compatible:

```text
rookbim_query_elements(category: string, scope, limit, filters)
```

The current string category input stays valid. The implementation changes from
direct enum resolution to runtime category resolution.

Route and bridge wiring must add `list_categories` everywhere the current BIM
ops are enumerated: native `/bim/categories` route handling, managed
`BimHandler.ExpectedBimOps`, `IRookBimRuntime`, `RevitRookBimRuntime`, native
proxy forwarding, MCP server tool registration, MCP dispatcher bridge routes,
targeting policies, context categories, and RookBIM tool groups.

## Resolution Precedence

The resolver uses this precedence:

1. Explicit machine forms.
   - Exact `OST_*` built-in category enum names.
   - Exact known `BuiltInCategory` enum names.
   - Exact integer category id strings, only when the whole input is an integer
     and the id exists in the active document category table.
2. Live document display-name exact match.
3. Normalized live document display-name match.
4. Built-in enum tolerant forms such as `GenericModel`, `PipeCurves`, or
   `CurtainWallPanels`.
5. Small curated aliases for known human/API/display-name mismatches.
6. Suggestions only.

Normalization is conservative:

- trim leading/trailing whitespace
- case-insensitive comparison
- ignore spaces, underscores, and hyphens
- singular/plural tolerance only when it is unambiguous

If a normalized input matches multiple live categories, the resolver must not
choose one. It returns `ambiguous_category`.

All successful strategies converge on a live category table entry. If an enum
or alias can be parsed but cannot be mapped back to a live document category,
the resolver returns a structured semantic failure rather than treating the enum
as sufficient.

## Category Resolution Contract

Add shared contract objects under `src/Rook/Bim`:

```json
{
  "schemaVersion": 1,
  "status": "resolved",
  "input": "Pipes",
  "normalizedInput": "pipes",
  "attemptedStrategies": [
    "built_in_exact",
    "document_display_name_exact"
  ],
  "strategy": "document_display_name_exact",
  "ambiguous": false,
  "category": {
    "id": -2008044,
    "name": "Pipes",
    "builtIn": "OST_PipeCurves",
    "categoryType": "Model",
    "parent": null
  },
  "document": {
    "title": "Snowdon Towers Sample Plumbing",
    "path": "C:/Program Files/Autodesk/Revit 2024/Samples/Snowdon Towers Sample Plumbing.rvt",
    "guidSource": "unavailable",
    "isFamilyDocument": false
  },
  "suggestions": [],
  "advisorySources": []
}
```

Status values:

```text
resolved
invalid
ambiguous
```

Strategy values:

```text
built_in_exact
category_id_exact
document_display_name_exact
document_display_name_normalized
built_in_tolerant
curated_alias
none
```

`schemaVersion` allows future knowledge graph advisory suggestions without a
breaking response-shape change.

`advisorySources` is empty in v1. It is reserved for future non-authoritative
suggestion sources such as `knowledge_graph`.

## Category Summary

Extend or complement the existing `BimCategorySummary` with enough identity
evidence for deterministic category work:

```json
{
  "id": -2008044,
  "name": "Pipes",
  "builtIn": "OST_PipeCurves",
  "categoryType": "Model",
  "parent": {
    "id": -2008000,
    "name": "Piping",
    "builtIn": null
  }
}
```

The stable output is the resolved category identity, not merely the input
string. Display names remain user-facing and may be localized or ambiguous.

`parent` is a shallow category identity object with `{ id, name, builtIn }`.
It must not recursively nest full `BimCategorySummary` objects.

## Queryability Contract

`rookbim_list_categories` may list categories from the document category table
even when no current elements exist in those categories.

`rookbim_query_elements` has a narrower contract: a resolved category must also
be applicable to bounded element collection. V1 may satisfy this in either of
two implementation-equivalent ways:

- apply a verified `BuiltInCategory` through `FilteredElementCollector.OfCategory`
- apply a verified category-id filter that is proven to collect the same Revit
  category

If a live category can be listed and resolved but cannot be applied safely to
the collector in v1, `rookbim_query_elements` must return a structured semantic
failure with `errorCode: "category_not_queryable"` and the resolution evidence
in `details.resolution`. It must not claim successful resolution and then
silently query the wrong category.

## Query Response Changes

`rookbim_query_elements` should include resolution evidence in the query
summary when a category was supplied:

```json
{
  "query": {
    "category": "Pipes",
    "categoryResolution": {
      "schemaVersion": 1,
      "status": "resolved",
      "strategy": "document_display_name_exact",
      "category": {
        "id": -2008044,
        "name": "Pipes",
        "builtIn": "OST_PipeCurves",
        "categoryType": "Model"
      }
    },
    "limit": 10,
    "returned": 3,
    "truncated": false,
    "filters": [],
    "missingParameterCounts": {}
  }
}
```

This evidence is diagnostic. Existing clients can continue using
`query.category` and `elements[*].category`.

## Failure Semantics

Invalid category:

```json
{
  "errorCode": "invalid_category",
  "message": "Unknown Revit category 'Pipe Accessoryz'.",
  "details": {
    "resolution": {
      "schemaVersion": 1,
      "status": "invalid",
      "input": "Pipe Accessoryz",
      "normalizedInput": "pipeaccessoryz",
      "attemptedStrategies": [
        "built_in_exact",
        "category_id_exact",
        "document_display_name_exact",
        "document_display_name_normalized",
        "built_in_tolerant",
        "curated_alias"
      ],
      "strategy": "none",
      "ambiguous": false,
      "document": {
        "title": "Snowdon Towers Sample Plumbing",
        "guidSource": "unavailable",
        "isFamilyDocument": false
      },
      "suggestions": [
        {
          "name": "Pipe Accessories",
          "id": -2008055,
          "builtIn": "OST_PipeAccessory",
          "source": "live_document",
          "matchReason": "close_normalized_name"
        }
      ],
      "advisorySources": []
    }
  }
}
```

Ambiguous category:

```json
{
  "errorCode": "ambiguous_category",
  "message": "Category 'Model Lines' matched multiple live Revit categories.",
  "details": {
    "resolution": {
      "schemaVersion": 1,
      "status": "ambiguous",
      "input": "Model Lines",
      "normalizedInput": "modellines",
      "attemptedStrategies": [
        "document_display_name_normalized"
      ],
      "ambiguous": true,
      "candidates": [
        {
          "name": "Lines",
          "id": -2000051,
          "builtIn": "OST_Lines",
          "categoryType": "Model"
        },
        {
          "name": "Lines",
          "id": -2000066,
          "builtIn": "OST_SketchLines",
          "categoryType": "Annotation"
        }
      ],
      "advisorySources": []
    }
  }
}
```

Add `BimErrorCode.AmbiguousCategory` and `BimErrorCode.CategoryNotQueryable`.

Category not queryable:

```json
{
  "errorCode": "category_not_queryable",
  "message": "Revit category 'Internal Area Loads' is available in the document but cannot be safely used for element collection.",
  "details": {
    "resolution": {
      "schemaVersion": 1,
      "status": "resolved",
      "input": "Internal Area Loads",
      "normalizedInput": "internalarealoads",
      "strategy": "document_display_name_exact",
      "ambiguous": false,
      "queryable": false,
      "category": {
        "id": -2005250,
        "name": "Internal Area Loads",
        "builtIn": "OST_InternalAreaLoads",
        "categoryType": "Internal",
        "parent": null
      },
      "advisorySources": []
    }
  }
}
```

The resolution status remains `resolved`; queryability failure is separate from
category identity resolution. The `queryable: false` field records why query
application stopped after successful category resolution.

Resolution failures remain structured semantic failures. They must not be
reported as internal errors unless the Revit API call itself fails unexpectedly.
Current BIM handler semantics are preserved: when `BimApiResponse.Data` is
supplied for a failure, the public wire envelope carries it under `details`.

Suggestions are bounded to at most five entries in v1. Each suggestion includes
at least `{ name, id, builtIn, source, matchReason }` when those fields are
available.

## `rookbim_list_categories`

The v1 tool is document-wide only.

Input:

```json
{
  "port": 52080
}
```

No `scope` field is accepted in v1.

Output:

```json
{
  "document": {
    "title": "Snowdon Towers Sample Plumbing",
    "path": "C:/Program Files/Autodesk/Revit 2024/Samples/Snowdon Towers Sample Plumbing.rvt",
    "guidSource": "unavailable",
    "isFamilyDocument": false,
    "isWorkshared": false
  },
  "schemaVersion": 1,
  "source": "document_category_table",
  "categories": [
    {
      "id": -2008044,
      "name": "Pipes",
      "builtIn": "OST_PipeCurves",
      "categoryType": "Model",
      "parent": null
    }
  ]
}
```

The tool lists categories available in the active document category table. It
does not filter by active view and does not assert element presence.

## Knowledge Graph Boundary

The first implementation is option A:

- Build the runtime resolver.
- Add `rookbim_list_categories`.
- Keep knowledge graph integration out of the resolution path.
- Reserve response fields for future advisory sources.

Future option B may add read-only KG suggestions only if:

- successful resolution never depends on KG
- KG lookup is failure-only or explicitly advisory
- KG failures degrade silently
- latency is bounded
- suggestions are marked as advisory
- suggestions never automatically change the resolved category

Option C, KG read/write learning, is out of scope. It raises unresolved
questions around scope, Revit version, locale, template, family vs project
documents, stale document identity, multi-process routing, and invalidation.

## Testing Strategy

Automated tests:

- `src/Rook.Tests`
  - contract serialization for category resolution objects
  - `BimErrorCode.AmbiguousCategory`
  - query summary includes `categoryResolution`
- `src/RookBim.Tests`
  - source/structure tests for `RevitCategoryResolver`
  - query service uses resolver before `OfCategory`
  - resolver exposes document table, enum, alias, invalid, and ambiguous paths
- `mcp_server/tests`
  - `rookbim_list_categories` tool registration and schema
  - bridge route wiring to `/bim/categories`
  - read-only targeting policy and tool group membership

Live Tester Codex passes:

- Architectural model:
  - `Curtain Panels` and `Generic Models` resolve with evidence.
- Plumbing model:
  - `Pipes`, `Pipe Fittings`, `Pipe Accessories`, and `Plumbing Fixtures`
    resolve or fail with useful evidence based on the live document category
    table.
- Family document:
  - `rookbim_list_categories` returns document-wide family categories.
  - zero element counts are not treated as invalid categories.
- Multi-Revit-process routing:
  - category listing and query resolution follow the explicitly bound port.
- Invalid category:
  - bogus input such as `Pipe Accessoryz` returns `invalid_category` with
    attempted strategies and live suggestions.
- Ambiguous category:
  - if an ambiguous normalized case is available, it returns
    `ambiguous_category` with candidates; otherwise validate with a targeted
    unit/source test.

## Acceptance Criteria

- `rookbim_list_categories` is available and document-wide only.
- `rookbim_query_elements` uses runtime category resolution.
- Returned category display names continue to round-trip as query inputs unless
  they are genuinely ambiguous.
- `Pipes` and `Pipe Accessories` no longer require hand-authored one-off fixes
  if they exist in the active document category table.
- Invalid category failures include schema version, input, normalized input,
  attempted strategies, document evidence, and suggestions.
- Ambiguous normalized matches return `ambiguous_category` instead of choosing
  arbitrarily.
- Existing RookBIM lifecycle behavior remains intact:
  - no active document
  - reopened document recovery
  - family documents
  - same-process document switching
  - multi-Revit-process explicit binding
  - stale identity rejection
