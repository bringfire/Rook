# RookBIM Phase 1 Design: Traceable Live Model Interrogation

Date: 2026-05-27

Status: Approved design. This is not an implementation plan.

> **Superseded document-identity doctrine (2026-07-28):** The approved
> [RookBIM File-Workshared Document Identity Design](2026-07-26-rookbim-file-workshared-identity-design.md)
> supersedes this document's path-fallback/non-stable and fail-open matching
> language. Versioned `documentKey` identity and closed comparison now govern
> production resolution, selection, and export authorization.

Related context:

- `docs/rook_docs/2026-05-26-rookbim-vision.md`
- `docs/CURRENT_ARCHITECTURE.md`
- `docs/superpowers/specs/2026-05-24-rhino-inside-revit-discovery-design.md`
- Local Revit API reference: `C:/Revit 2024.2 SDK`
- External precedents, used only for learning:
  - `https://github.com/mcp-servers-for-revit/mcp-servers-for-revit`
  - `https://github.com/schauh11/revit-mcp-server`
  - `https://github.com/nguyenngocdue/revit-mcp-server`
  - `https://github.com/mcp-servers-for-revit/mcp-server-for-revit-python`

## Goal

RookBIM Phase 1 is traceable live model interrogation.

The first product promise is:

> Ask the live Revit model a bounded question, get exact element identities
> back, inspect parameters, and select the evidence in Revit.

This is not Revit authoring, Rhino export cleanup, or a Grasshopper automation
wrapper. The goal is to prove a trustworthy read-only BIM evidence loop:

1. Query live Revit elements through bounded tools.
2. Return document and element identities with confidence.
3. Inspect parameter evidence for exact elements.
4. Select those elements in the Revit UI.
5. Avoid Revit document writes and Grasshopper canvas dependencies.

## Non-Goals

Phase 1 excludes:

- Revit writes and write transactions
- Parameter edits
- Element creation or deletion
- Temporary isolate, hide/unhide, color overrides, and graphic highlighting
- Dynamic Revit code execution
- Model diff or snapshot storage
- Rhino object metadata stamping
- Rhino/Revit round-trip sync
- Grasshopper/Revit recipe wrapping
- Dirty export recovery automation
- Numeric filters
- `OR` filter logic
- Pagination or cursors beyond hard-limit truncation
- Full linked-model query or selection support

## Architecture Boundary

RookBIM uses Rook's existing public surface. It does not introduce a second
public plugin, HTTP server, or MCP server.

```text
MCP client
  -> Rook MCP server
  -> RookNative public HTTP route /bim/*
  -> Rook managed companion proxy/contracts
  -> optional RookBim managed module
  -> Revit API inside RhinoInside/Revit
```

Responsibilities:

- `RookNative`: public `/bim/*` route registration and opaque JSON proxying to
  managed callbacks, following existing native route/error conventions.
- `src/Rook`: BIM DTOs/contracts, unavailable fallback, module activation, and
  managed proxy callback support.
- `mcp_server/src/rook`: `rookbim_*` MCP tool definitions and bridge routing to
  `/bim/*`.
- `src/RookBim`: Revit runtime detection, Revit API references,
  document/query/parameter/selection services.

Rejected for product code:

- Putting Revit API handlers directly in `src/Rook`.
- Using Grasshopper/RhinoInside.Revit components as the core Phase 1 data path.

Allowed only as disposable learning:

- Companion-only local spikes that are deleted or rewritten before product
  implementation.

Boundary guard:

- `src/Rook` must not reference `RevitAPI.dll`, `RevitAPIUI.dll`, or Autodesk
  Revit namespaces.

## Phase 1 Tools

MCP tools:

```text
rookbim_status
rookbim_active_document
rookbim_query_elements
rookbim_element_info
rookbim_element_parameters
rookbim_select_elements
rookbim_clear_selection
```

Native HTTP route family:

```text
GET  /bim/status
GET  /bim/active-document
POST /bim/query-elements
POST /bim/element-info
POST /bim/element-parameters
POST /bim/select-elements
POST /bim/clear-selection
```

Tool roles:

- `rookbim_status`: reports availability and host evidence: Revit process,
  RhinoInside state, active document presence, runtime/module loaded state.
- `rookbim_active_document`: returns document identity and active view summary
  where available.
- `rookbim_query_elements`: bounded active-view or document-scope query,
  returning summary results only.
- `rookbim_element_info`: resolves one element by identity envelope, including
  document identity plus `elementId` or `uniqueId`, returning identity, type,
  category, and safe location-like summary data.
- `rookbim_element_parameters`: returns serialized parameter evidence for one
  element identity envelope.
- `rookbim_select_elements`: selects exact returned identities in the Revit UI.
  This mutates UI selection only, not the Revit document.
- `rookbim_clear_selection`: clears Revit selection. This mutates UI selection
  only, not the Revit document.

Selection tools are read-only with respect to the Revit document, not
side-effect free.

Temporary view isolation or graphic highlighting is excluded from Phase 1 unless
plain Revit selection proves insufficient during live validation.

## Identity Contract

Every RookBIM response carries document identity. Element-bearing responses also
carry an element identity envelope. Phase 1 must not return loose Revit
`ElementId` values without document context.

Document identity:

```json
{
  "document": {
    "guid": null,
    "guidSource": "unavailable",
    "title": "Model.rvt",
    "path": "C:/path/Model.rvt",
    "isFamilyDocument": false,
    "isWorkshared": true
  }
}
```

`guidSource` values:

```text
revit_persistent_guid
path_fallback
unavailable
```

`path_fallback` is diagnostic and non-stable in Phase 1. It must not be treated
as an exact identity key.

Element identity envelope:

```json
{
  "identity": {
    "source": "revit",
    "documentGuid": null,
    "documentGuidSource": "unavailable",
    "documentPath": "C:/path/Model.rvt",
    "documentTitle": "Model.rvt",
    "elementId": 12345,
    "uniqueId": "...",
    "fullUniqueId": "...",
    "linked": false,
    "confidence": "exact",
    "resolved": true
  }
}
```

`documentPath` is diagnostic. It is not part of exact identity.

`documentGuid` and `documentGuidSource` mirror the document identity contract.
If `documentGuidSource` is not `revit_persistent_guid`, `confidence: "exact"`
means the live element was resolved exactly within the active Revit document
context for this request. It does not claim a stable cross-session document
identity.

Linked-model fields are reserved now so linked identity is not flattened later:

```text
linkInstanceId
linkInstanceUniqueId
linkedDocumentGuid
linkedElementId
linkedElementUniqueId
```

First implementation may return `linked_element_unsupported` or
`capability_unavailable` for linked element resolution if linked selection/query
behavior is not ready.

Identity confidence values:

```text
exact       resolved directly from live Revit document + UniqueId/ElementId
inferred    reconstructed from partial metadata or compatibility naming
unresolved  identity was provided but no live element was found
unsupported valid shape, but Phase 1 cannot resolve that identity class
```

Expected pairings:

```text
exact + resolved=true
unresolved + resolved=false
unsupported + resolved=false
inferred + resolved=true|false depending on later backfill behavior
```

In Phase 1, normal live Revit query/resolve/select paths should return `exact`
or a structured error. `inferred` is reserved for later Rhino/RhinoInside.Revit
metadata backfill and should not appear unless explicitly implemented.

Active-view query responses include a view summary:

```json
{
  "view": {
    "id": 987,
    "uniqueId": "...",
    "name": "Level 1"
  }
}
```

`view.uniqueId` is optional if available. The implementation must verify Revit
2024.2 view identity behavior before making this field mandatory.

## Query Contract

`rookbim_query_elements` supports both active-view and document-wide queries
through one explicit `scope` field.

Input:

```json
{
  "scope": "active_view",
  "category": "Walls",
  "limit": 100,
  "filters": [
    {
      "parameter": "Fire Rating",
      "operation": "is_not_empty"
    }
  ]
}
```

Rules:

- `scope` allowed values: `active_view`, `document`.
- If omitted, `scope` defaults to `active_view`.
- `active_view` is the preferred Phase 1 path because it is bounded and
  visually explainable.
- `document` scope requires `category` in Phase 1. Filters may narrow the
  category result set, but they are not sufficient by themselves because
  negative or empty filters can match most heterogeneous model elements.
- Default `limit`: `100`.
- Hard max: `1000`.
- `truncated: true` is a successful capped query.
- `query_limit_exceeded` means the request asked for more than the hard max or
  supplied an invalid limit policy.
- Multiple filters are `AND` only in Phase 1.
- Query responses return summary element rows only. Deep parameter data stays in
  `rookbim_element_parameters`.

Summary result shape:

```json
{
  "document": {
    "guid": "...",
    "guidSource": "revit_persistent_guid",
    "title": "Model.rvt",
    "path": "C:/path/Model.rvt",
    "isFamilyDocument": false,
    "isWorkshared": true
  },
  "scope": "active_view",
  "view": {
    "id": 987,
    "uniqueId": "...",
    "name": "Level 1"
  },
  "query": {
    "category": "Walls",
    "limit": 100,
    "returned": 42,
    "truncated": false
  },
  "elements": [
    {
      "identity": {
        "source": "revit",
        "documentGuid": "...",
        "documentGuidSource": "revit_persistent_guid",
        "documentPath": "C:/path/Model.rvt",
        "documentTitle": "Model.rvt",
        "elementId": 12345,
        "uniqueId": "...",
        "fullUniqueId": "...",
        "linked": false,
        "confidence": "exact",
        "resolved": true
      },
      "name": "Basic Wall",
      "category": {
        "id": -2000011,
        "name": "Walls"
      },
      "type": {
        "id": 67890,
        "uniqueId": "...",
        "familyName": "Basic Wall",
        "name": "Generic - 8 inch"
      }
    }
  ]
}
```

## Filter Contract

Phase 1 filter operations:

```text
equals
not_equals
contains
is_empty
is_not_empty
```

Filter semantics:

- `contains` applies only to string/display text values.
- `equals` and `not_equals` compare normalized display strings.
- Numeric comparisons are excluded from Phase 1.
- Missing parameter evaluation:
  - `is_empty` => true
  - `is_not_empty` => false
  - `equals` => false
  - `contains` => false
  - `not_equals` => true
- Missing-parameter counts should be included in query metadata where
  practical.
- Ambiguous parameter names fail at the query level only when ambiguity is
  detected within the target candidate set.
- `ambiguous_parameter` errors include candidate parameter identities when
  available.

Example ambiguity error:

```json
{
  "error": "ambiguous_parameter",
  "parameter": "Mark",
  "candidates": [
    { "name": "Mark", "builtIn": "ALL_MODEL_MARK" },
    { "name": "Mark", "guid": "..." }
  ]
}
```

Deferred Phase 1b numeric filter contract may add numeric comparison only after
parameter serialization proves fields such as:

```json
{
  "name": "Area",
  "storageType": "Double",
  "rawValue": 123.45,
  "displayValue": "123.45 SF",
  "specType": "autodesk.spec.aec:area",
  "unitTypeId": "autodesk.unit.unit:squareFeet",
  "canCompareNumeric": true
}
```

When numeric filters are introduced, they must compare JSON numbers against a
documented value basis, not display strings.

## Runtime Activation

`src/RookBim` loads or activates only when hosted inside RhinoInside/Revit.

Required evidence:

- host process is Revit
- RhinoInside is active
- active `UIApplication` / `UIDocument` / `Document` is available for
  document-bound tools
- RookBIM module loaded successfully

Standalone Rhino returns structured unavailability, not missing-method or proxy
callback failures.

## Error Handling

Core error codes:

```text
rookbim_unavailable
not_rhino_inside
revit_unavailable
no_active_document
no_active_view
invalid_scope
unbounded_document_query
invalid_category
ambiguous_parameter
element_not_found
document_mismatch
linked_element_unsupported
capability_unavailable
selection_failed
query_limit_exceeded
internal_error
```

Error payloads should include enough runtime evidence to debug without guessing:

```json
{
  "error": "no_active_document",
  "message": "RookBIM requires an active Revit document.",
  "host": {
    "processName": "Revit",
    "rhinoInside": true,
    "moduleLoaded": true
  }
}
```

## Threading And API Context

All Revit API work runs through a verified Revit UI-context dispatch pattern.

`ExternalEvent` is the expected Revit API dispatch mechanism unless SDK and
RhinoInside validation proves an existing managed callback path is already on a
valid Revit API context.

Phase 1 opens no write transactions. Selection tools mutate Revit UI selection
only and remain read-only with respect to the Revit document.

Do not assume Rook's Rhino main-thread dispatcher is automatically valid for
Revit API calls.

## SDK And Precedent Policy

`C:/Revit 2024.2 SDK` is the local primary reference for Revit API usage when
designing or implementing RookBIM.

Verify against the local SDK samples/docs and existing Rook patterns before
committing implementation details for:

- `ExternalEvent` / UI-context execution patterns
- document and `UIApplication` access
- `FilteredElementCollector`
- `ElementId` / `UniqueId` handling
- parameter storage/display serialization
- selection APIs
- transaction boundaries, even though Phase 1 avoids writes
- linked model APIs and limitations

External Revit MCP repositories are useful precedent for tool ergonomics,
dispatch mechanics, and common pitfalls, but they are not mandates. RookBIM
keeps its own schemas, RookNative public surface, read-only Phase 1 scope, and
module boundaries.

Do not guess Revit APIs from memory or external MCP repos.

## Verification

Automated/source verification:

- Source guard: `src/Rook` does not reference `RevitAPI.dll`,
  `RevitAPIUI.dll`, or Autodesk Revit namespaces.
- Unit/source tests for managed fallback behavior, route schemas, MCP tool
  schemas, invalid inputs, and native proxy route registration.
- SDK verification against `C:/Revit 2024.2 SDK` before implementation.

Live validation in standalone Rhino:

- `rookbim_status` returns structured unavailable evidence.
- Document-bound tools fail with `rookbim_unavailable` or `not_rhino_inside`,
  not native/managed callback errors.

Live validation inside RhinoInside/Revit:

- `rookbim_status` reports available host evidence.
- `rookbim_active_document` returns document identity.
- `rookbim_query_elements` works for active-view and bounded document queries.
- `rookbim_element_info` resolves by identity envelope.
- `rookbim_element_parameters` returns serialized parameter evidence.
- `rookbim_select_elements` selects exact query results.
- No Grasshopper document or canvas is required.
- No Revit transaction is opened.

## Phase 1b Candidates

After the Phase 1 substrate is proven:

- Numeric parameter serialization and numeric filters
- Linked model identity/resolution
- Pagination/cursor design
- Current selection query / selection-to-query round trip
- Active view/category summaries
- First audit tool built on the generic query substrate
- Optional temporary visual focus only if selection is insufficient

## Longer Lanes

Longer-term lanes stay out of Phase 1:

- Rhino/Revit semantic bridge and provenance metadata
- Dirty export recovery lane informed by the Revit proto-skills
- Controlled write tools with explicit transaction previews
- Grasshopper recipe wrapping as an optional visual computation path

## Success Criteria

Phase 1 succeeds when:

- An agent can ask a bounded question about live Revit elements.
- RookBIM returns exact element identities and summary evidence.
- The agent can inspect parameters for returned identities.
- The agent can select those exact elements in Revit.
- The workflow does not rely on Grasshopper and does not modify the Revit
  document.
- Runtime boundaries prevent Revit API drift into core `src/Rook`.

## Self-Review Notes

- Scope is limited to one implementation plan: the read-only RookBIM Phase 1
  substrate.
- The design explicitly rejects the two tempting shortcuts: Revit API handlers
  in `src/Rook` and GH/Revit components as the core data path.
- The design reserves linked identity fields without requiring full linked-model
  support in Phase 1.
- The query/filter language is intentionally small and avoids numeric/unit
  semantics until parameter serialization is proven.
