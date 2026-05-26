# RookBIM Vision: Agentic BIM Through RhinoInside/Revit

Date: 2026-05-26

Status: Vision and architecture framing. This is not an implementation plan yet.

Related queue item: `docs/rook_docs/work-queue.md`, parked item "RookBIM MCP toolset for direct RhinoInside/Revit document access".

## Executive Summary

RookBIM is the proposed Revit/RhinoInside expansion of Rook: a managed-companion MCP toolset that lets agents inspect, reason about, validate, and eventually modify live Revit BIM data while Rhino is hosted inside Revit through RhinoInside.

The important idea is not simply "AI can run Grasshopper" or "AI can call Revit." The unique opportunity is that Rook already has a live agent control plane into Rhino, Grasshopper, and the Rook native/managed runtime, and RhinoInside places Rhino and Revit in the same process. That creates a path to a live, identity-aware BIM operating layer:

```text
MCP agent
  -> Rook MCP server
  -> RookNative public bridge
  -> managed companion in RhinoInside/Revit
  -> Revit API, RhinoCommon, and optional Grasshopper workflows
```

With this stack, agents can work with the actual building model rather than screenshots, exports, PDFs, or stale snapshots. Revit remains the authoritative BIM database. Rhino and Grasshopper provide modeling, geometry, and parametric workflows. Rook provides the agent-facing control plane, routing, runtime discovery, and the place to add safe, auditable BIM tools.

The first RookBIM milestone should be read-only and evidence-focused: prove that an MCP client can query the active Revit document, inspect elements and parameters, select/highlight model objects, and report stable identities without depending on Grasshopper as the data path.

## Why This Is Different

Most "AI for BIM" workflows are detached from the live model. They operate on exported IFC, spreadsheets, schedules, screenshots, PDFs, or simplified geometry. Those are useful, but they are not the building model. They lose transaction context, element identity, document state, selection state, worksharing state, and the live API surface.

RookBIM can be different because it can operate at the intersection of four live systems:

- Revit as the source of BIM truth: documents, elements, categories, types, parameters, views, sheets, rooms, levels, links, worksets, design options, and transactions.
- Rhino as the geometric/modeling environment: geometry, blocks, materials, layers, view state, and existing Rook route coverage.
- Grasshopper as an optional visual computation layer: Revit components, parametric definitions, canvas snapshots, and reusable recipes.
- MCP as the agent protocol: structured tools that make model operations inspectable, testable, repeatable, and constrained.

This combination suggests a new product category for Rook: an agentic BIM operations layer that can understand both semantic BIM and geometric design intent.

## Grounding Evidence From Live Testing

On 2026-05-26, a live RhinoInside/Revit session was validated through the Rook MCP server:

- Active process: Revit PID `39724`.
- Native Rook bridge port: `61798`.
- `rhino_ping` returned `pong` after binding to the live RhinoInside instance.
- Rook discovery file `instance-39724-native.json` reported `rhinoInside: true`, plugin type `native`, plugin version `1.5.8`, and Grasshopper callback routes.
- Companion self-report `companion-39724.json` reported:
  - `processName: Revit`
  - `rhinoInside: true`
  - `runtimeChild: net48`
  - `startupComplete: true`
  - `bridgeRegistered: true`
- Grasshopper live control was proven:
  - `gh_status` reported Grasshopper available and canvas visible.
  - A new GH document was created.
  - A number slider and built-in Surface/Primitive Sphere were created through MCP.
  - The slider was wired to the sphere radius input.
  - Final snapshot had two objects, one wire, zero errors, and zero warnings.
  - A canvas PNG was captured.
- RhinoInside/Revit GH components were visible:
  - `Revit` category: 400 components.
  - `Params > Revit`: 54 parameter components.
  - `Params > Revit Elements`: 43 parameter components.
  - Representative components included `Active Document`, `Revit Version`, `Query Elements`, `Query Walls`, `Query Views`, `Element Parameter`, `Inspect Element`, `Add Wall (Curve)`, `Add DirectShape (Geometry)`, `Add Level`, and `Add Grid`.

This proves the current Rook runtime can reach the RhinoInside/Revit host and can control Grasshopper. It does not yet prove direct Revit API MCP tools. That is the RookBIM opportunity.

## Grounding Evidence From Rhino.Inside.Revit Source

Rhino.Inside.Revit already carries Revit identity through its Grasshopper wrapper types and, in some baked Rhino content, through object or instance definition naming.

Relevant source observations from `mcneel/rhino.inside-revit`, branch `1.x`, commit `7fb1f1ff1dd535ce358c0e98797b1f92f8d6a175`:

- `NameConverter.EscapeName(...)` documents and builds a Rhino name format that includes `FullUniqueId`:

  ```text
  Project::CategoryFullName[::FamilyName::TypeName][::Nomen] FullUniqueId
  ```

  It builds `FullUniqueId` from `element.Document.GetPersistentGUID()` and `element.UniqueId`.

  Source: `src/RhinoInside.Revit/Convert/DocObjects/NameConverter.cs`

- Baked geometric elements use that escaped name as the Rhino instance definition name:

  ```csharp
  var idef_name = NameConverter.EscapeName(element, out var idef_description);
  index = doc.InstanceDefinitions.Find(idef_name)?.Index ?? -1;
  ```

  Source: `src/RhinoInside.Revit.GH/Types/GeometricElement+Bake.cs`

- Grasshopper reference objects persist:

  ```text
  DocumentGUID
  UniqueID
  ```

  Source: `src/RhinoInside.Revit.GH/Types/DocumentObject.cs`

- Revit element wrappers set:

  ```csharp
  ReferenceDocumentId = Document.GetPersistentGUID();
  ReferenceUniqueId = element.UniqueId;
  ```

  Source: `src/RhinoInside.Revit.GH/Types/Element.cs`

- RhinoInside has utilities for parsing and formatting full unique IDs and persistent Revit references:

  - `FullUniqueId.Format(Guid documentId, string stableId)`
  - `ReferenceId`
  - `ConvertToPersistentRepresentation`
  - `ParseFromPersistentRepresentation`

  Sources:
  - `src/RhinoInside.Revit.External/DB/UniqueId.cs`
  - `src/RhinoInside.Revit.External/DB/Extensions/Reference.cs`

The conclusion is precise:

- Grasshopper references can persist Revit document identity plus Revit element identity.
- Rhino.Inside-baked Rhino content can contain a Revit identity trail in Rhino instance definition names.
- Arbitrary Rhino geometry does not automatically have a reliable Revit backlink.
- RookBIM should use RhinoInside's identity conventions as a compatibility/backfill source, but should stamp explicit Rook-owned metadata when Rook creates, imports, tracks, or transforms Revit-derived Rhino objects.

## Identity Model

RookBIM should treat identity as a first-class contract. Without identity, the system is just geometry automation. With identity, it can reason over BIM.

### Revit-Side Identity

Candidate identity fields:

- `documentGuid`: Revit document persistent GUID, matching RhinoInside's `GetPersistentGUID()` convention.
- `documentPath`: local path or central model path where available.
- `documentTitle`: human-readable title.
- `elementId`: Revit runtime element ID. Useful in-session but not enough by itself.
- `uniqueId`: Revit element `UniqueId`. Better for stable lookup within the same document lineage.
- `categoryId` / `categoryName`.
- `typeId` / `typeUniqueId`.
- `familyName` and `typeName` where applicable.
- `linkInstanceId` / `linkInstanceUniqueId` for linked models.
- `linkedDocumentGuid` and `linkedElementUniqueId` for linked model elements.

### Rhino-Side Identity

Candidate metadata for Rhino objects, blocks, and materials created or tracked by RookBIM:

```text
rook:bim:source = revit
rook:bim:documentGuid
rook:bim:documentPath
rook:bim:documentTitle
rook:bim:elementId
rook:bim:elementUniqueId
rook:bim:elementFullUniqueId
rook:bim:linkInstanceUniqueId
rook:bim:linkedDocumentGuid
rook:bim:linkedElementUniqueId
rook:bim:category
rook:bim:family
rook:bim:type
rook:bim:lastSyncedUtc
rook:bim:syncRole = source | derived | generated | preview
rook:bim:provenanceRunId
```

This metadata should not replace RhinoInside's naming convention. It should complement it. The name convention is useful for interoperability and backfill; explicit metadata is safer for programmatic routing.

### Stable Enough, Not Magical

Revit identity is strong but not absolute:

- `ElementId` is not portable across documents and can be fragile across delete/recreate workflows.
- `UniqueId` is better but still tied to the document lineage.
- Copying, grouping, linking, detaching, and recreating elements can produce new identities.
- Linked models require two identities: the link instance in the host and the linked element inside the linked document.

RookBIM should therefore expose identity confidence:

```json
{
  "identity": {
    "documentGuid": "...",
    "elementId": 12345,
    "uniqueId": "...",
    "confidence": "exact",
    "resolved": true
  }
}
```

When RookBIM reconstructs identity from a Rhino name or partial metadata, it should report `confidence: "inferred"` rather than pretending certainty.

## Grasshopper Is Optional, Not Foundational

Grasshopper is immediately useful because Rhino.Inside.Revit ships a large Revit component library and Rook can already control the GH canvas. That makes GH a powerful proof and automation surface.

But RookBIM should not depend on GH for core BIM queries.

The better architecture:

```text
Direct read path:
MCP -> Rook managed companion -> Revit API -> structured JSON

Optional visual computation path:
MCP -> Rook GH routes -> RhinoInside.Revit GH components -> Revit API

Optional geometry path:
MCP -> Rook native/managed Rhino routes -> RhinoCommon -> Rhino document
```

Grasshopper remains valuable for:

- visual workflows
- parametric definitions
- user-authored computational BIM recipes
- canvas inspection and debugging
- reuse of existing RhinoInside/Revit components

Direct managed companion routes are better for:

- active document metadata
- element queries
- parameter inspection
- selection/highlighting
- read-only audit tools
- stable MCP schemas
- tests that do not depend on GH canvas state

## Product Possibility Map

### 1. BIM Query Agent

Natural language questions become structured Revit queries:

- "Which walls are fire-rated but missing acoustic ratings?"
- "Find all doors on Level 2 without hardware set data."
- "Show exterior wall types and total area by type."
- "List all linked models and their loaded state."
- "Which elements are on the wrong workset?"

MCP tools should return traceable element identities, not just prose. The agent can then select, isolate, or annotate the results.

### 2. Model QA and Standards Auditor

RookBIM can become an always-available model auditor:

- duplicate room numbers
- unplaced or unenclosed rooms
- missing sheet metadata
- noncompliant type names
- unassigned parameters
- elements on wrong worksets
- views without templates
- unused or duplicate types
- links with stale paths
- view/sheet issue readiness

The key product difference is traceability: every finding should include element IDs, unique IDs, category/type context, and a suggested fix path.

### 3. BIM Selection and Explanation Layer

Agents should be able to select or highlight Revit elements, then explain:

- what they are
- where they are
- what type/family/category they belong to
- what parameters matter
- what changed recently
- why they were included in a query result

This is one of the smallest high-value early slices because it turns RookBIM from a data dump into an interactive model assistant.

### 4. BIM-to-Rhino Semantic Scene Graph

Rook can build a semantic scene graph from Revit:

```text
Document
  -> Links
  -> Levels
  -> Grids
  -> Rooms / Spaces / Areas
  -> Elements
      -> category
      -> type
      -> family
      -> parameters
      -> geometry
      -> materials
      -> location
      -> host
      -> room/space containment
      -> view/sheet visibility
```

This gives agents a structure that supports reasoning rather than treating the model as unrelated objects.

### 5. Geometry-to-BIM Authoring

Once read-only identity and selection are solid, RookBIM can safely author Revit elements:

- walls from Rhino curves
- floors and roofs from boundaries
- grids and levels from layout logic
- DirectShapes from Rhino meshes/breps
- adaptive components from point sets
- family instances from Rhino/GH point and plane data

Write tools should require explicit transaction boundaries, preview payloads, undo strategy, and user confirmation for risky operations.

### 6. Round-Trip Design Memory

RookBIM can track where design artifacts came from:

- this Rhino block came from Revit element X
- this GH study used Revit wall type Y
- this generated facade option was based on these levels and grids
- this Revit DirectShape was produced by Rook run Z

When the Revit model changes, Rook can identify stale studies and suggest recomputation.

### 7. Model Diff and Change Explainer

Element-level diff can answer:

- what changed since a previous snapshot?
- which element geometry changed?
- which parameters changed?
- which elements were deleted and recreated?
- which linked model changed?
- which downstream generated Rhino/GH artifacts are stale?

This is a natural fit for Rook's existing session/provenance direction.

### 8. Parametric BIM Recipes

Grasshopper definitions can become callable BIM recipes:

- Inputs: selected Revit elements, categories, parameters, curves, levels.
- Process: GH definition or script.
- Outputs: Revit elements, Rhino geometry, reports, previews.
- Metadata: provenance, identities, timestamps, and run arguments.

The agent should be able to run these recipes through MCP without manually operating the GH canvas, while still allowing GH to be the visual authoring/debugging surface.

### 9. Documentation and Sheet Automation

RookBIM can eventually operate on:

- views
- sheets
- schedules
- tags
- dimensions
- revision metadata
- title blocks
- view templates

This must come after read-only and lower-risk write slices, but the product value is high.

### 10. BIM Operations and Governance

The long-term product shape is a BIM operations layer:

- inspect
- select
- explain
- audit
- fix
- generate
- document
- diff
- report
- remember

Each operation should be structured, identity-aware, and auditable.

## Proposed MCP Tool Families

### Phase 1: Read-Only Foundation

Candidate tools:

```text
revit_active_document
revit_document_info
revit_open_documents
revit_categories
revit_query_elements
revit_element_info
revit_element_parameters
revit_element_geometry_summary
revit_select_elements
revit_clear_selection
```

Purpose:

- establish direct managed-companion Revit API access
- avoid GH dependency for core data
- return identity-rich JSON
- prove selection/highlighting in live Revit
- build tests against shape and error contracts

### Phase 2: Filters, Views, and Links

Candidate tools:

```text
revit_query_by_category
revit_query_by_parameter
revit_query_by_view
revit_query_by_level
revit_query_rooms
revit_query_spaces
revit_query_links
revit_link_element_info
revit_view_info
revit_sheet_info
```

Purpose:

- support practical model audits
- handle linked model identity explicitly
- query elements by real BIM relationships

### Phase 3: Audit Tools

Candidate tools:

```text
revit_audit_rooms
revit_audit_parameters
revit_audit_worksets
revit_audit_view_templates
revit_audit_type_naming
revit_audit_links
```

Purpose:

- convert common BIM QA checks into reusable structured reports
- keep findings traceable to element identities
- support select/focus/fix loops

### Phase 4: Controlled Writes

Candidate tools:

```text
revit_transaction_preview
revit_set_element_parameter
revit_batch_set_parameters
revit_create_directshape
revit_create_level
revit_create_grid
revit_create_wall_from_curve
revit_create_floor_from_boundary
```

Purpose:

- introduce transactions only after read-only reliability is proven
- require explicit write intent
- report created/modified element identities
- preserve undo and provenance

### Phase 5: Rhino/Revit Round-Trip

Candidate tools:

```text
rookbim_stamp_rhino_objects
rookbim_resolve_rhino_source
rookbim_bake_revit_elements_to_rhino
rookbim_sync_status
rookbim_mark_stale_derivatives
rookbim_recompute_derivative
```

Purpose:

- bridge Rhino geometry and Revit elements with explicit Rook metadata
- provide stale-state detection
- make round-trip workflows durable

## Architecture Direction

### Managed Companion Owns Revit API Access

Direct Revit access should live in the managed companion, not native C++.

Reasons:

- Revit API is .NET.
- RhinoInside/Revit runs in the Revit process.
- Existing managed companion already owns RhinoInside-specific startup evidence.
- Grasshopper callback bridge is managed by design.
- Revit transactions and UI-thread behavior are managed/API concerns.

Native Rook should remain the public bridge and route registrar where appropriate, but it should not try to become a Revit API host.

### Relationship to Rook and the RookVision Precedent

RookVision is the closest existing precedent, but RookBIM should not copy the RookVision structure exactly.

RookVision established a useful product pattern:

```text
one public Rook plugin
one public Rook HTTP/MCP surface
internal feature domain behind that surface
shared domain code consumed by human UI and MCP tools
```

That pattern should carry forward. RookBIM should not become a second public Rhino plugin, a second localhost server, or a separate user-facing runtime that competes with RookNative. RookNative should remain the only public Rhino plugin and public bridge surface.

The difference is that RookBIM has a stronger host-specific dependency than RookVision:

- RookVision is Rook-owned domain code with provider APIs, artifact storage, and UI surfaces.
- RookBIM needs Revit API access.
- RookBIM only makes sense when Rhino is running inside Revit.
- RookBIM likely targets `net48` first because RhinoInside/Revit 2024 is hosted in Revit's .NET Framework runtime.
- RookBIM may eventually have separate product entitlement or licensing behavior.

Therefore RookBIM should use the RookVision product integration pattern, but with a cleaner module boundary.

Recommended shape:

```text
RookNative
  public Rhino plugin
  public HTTP/MCP bridge
  route registration and proxying only

Rook managed companion
  core managed companion
  Rhino/RhinoInside awareness
  bridge registration
  feature discovery
  BIM contracts and unavailable fallback

RookBIM managed module
  optional net48 assembly
  loaded only inside RhinoInside/Revit
  owns Revit API calls
  owns Revit identity/query/selection/transaction services
```

This keeps the user experience unified while preventing Revit-specific references from spreading through the core companion.

### Proposed Module Layout

Use the core managed companion for contracts and dispatch, and a separate RookBIM assembly for Revit-specific implementation.

```text
src/Rook/
  Bim/
    IRookBimRuntime.cs
    RookBimUnavailableRuntime.cs
    BimContracts.cs
    BimRouteSchemas.cs
  Handlers/
    BimHandler.cs
  InternalBridge/
    NativeBimBridgeRegistrar.cs

src/RookBim/
  RookBim.csproj
  RevitRuntimeDetector.cs
  RevitDocumentService.cs
  RevitElementQueryService.cs
  RevitParameterService.cs
  RevitSelectionService.cs
  RevitIdentitySerializer.cs
  RevitTransactionService.cs
```

Boundary rule:

- `src/Rook` may define interfaces, DTOs, fallback behavior, and route plumbing.
- `src/Rook` should not directly reference `RevitAPI.dll` or `RevitAPIUI.dll`.
- `src/RookBim` may reference Revit API assemblies from the host installation.
- `src/RookBim` should be loaded only when the runtime is RhinoInside/Revit.

The fallback runtime is important. In standalone Rhino, BIM tools should exist only if the product wants discoverable-but-unavailable tools; otherwise they should be omitted from MCP discovery. Either way, they must not fail because Revit assemblies are missing.

### Dynamic Loading and Availability

The companion should load or activate RookBIM only when all required runtime conditions are met:

```text
processName == Revit
Rhino.Runtime.HostUtils.RunningAsRhinoInside == true
RookBim.dll exists
Revit API assemblies are already host-available or resolvable from Revit
RookBIM entitlement/configuration allows activation
```

If unavailable, the BIM runtime should return a structured error:

```json
{
  "error": "rookbim_unavailable",
  "reason": "RookBIM is only available inside RhinoInside/Revit"
}
```

Availability should also be surfaced through discovery/status, similar in spirit to the companion self-report that proved RhinoInside startup state. RookBIM status should include host evidence, not just a boolean:

```json
{
  "available": true,
  "hostProcess": "Revit",
  "rhinoInside": true,
  "activeDocument": true,
  "runtime": "net48",
  "moduleLoaded": true
}
```

### Route and MCP Naming

RookNative should continue to own the public HTTP route table. BIM routes should be native-registered proxy routes into the managed companion, not a separate server.

Candidate HTTP route family:

```text
/bim/status
/bim/active-document
/bim/query-elements
/bim/element-info
/bim/element-parameters
/bim/select-elements
```

Candidate MCP tool names should be explicitly BIM-branded:

```text
rookbim_status
rookbim_active_document
rookbim_query_elements
rookbim_element_info
rookbim_element_parameters
rookbim_select_elements
```

This naming makes the capability clear without implying these tools work in standalone Rhino. It also leaves room for broader non-Revit BIM integrations later, while the first implementation remains Revit-specific.

### Licensing and Source Hygiene Boundary

RookBIM should preserve Rook's ability to move from the current MIT license to a proprietary EULA.

The core policy:

- Do not redistribute Autodesk binaries.
- Do not ship `RevitAPI.dll`, `RevitAPIUI.dll`, or other Revit runtime DLLs.
- Reference Revit API assemblies from the user's installed, licensed Revit environment.
- Do not vendor RhinoInside.Revit wholesale.
- Do not copy RhinoInside.Revit implementation code unless explicitly approved and tracked with MIT notices.
- Use RhinoInside.Revit source as reference material for interoperability and identity behavior, then implement Rook-owned code.
- Keep Revit-specific implementation in `src/RookBim`, not scattered through Rook core.
- Keep RookNative free of Revit API concepts beyond route names and opaque JSON proxying.

RhinoInside.Revit is MIT licensed, so copying code is generally allowed with notice compliance. The preferred RookBIM posture is still to avoid copying where practical. Public API behavior, observed runtime behavior, and independently implemented identity conventions are enough for the first slice.

This yields a clean commercial/product boundary:

```text
Rook core
  proprietary/EULA-ready
  no Autodesk binaries
  no copied RhinoInside implementation
  BIM contracts and routing only

RookBIM module
  proprietary/EULA-ready Rook implementation
  optional host-specific assembly
  references host-installed Revit APIs
  no redistribution of Autodesk runtime

User environment
  licensed Revit
  licensed Rhino
  RhinoInside/Revit installed or loaded by user
```

RookBIM should be positioned as a Rook module that interoperates with the user's licensed Revit, Rhino, and RhinoInside installation through installed public APIs. It should not be positioned as a bundled Revit/RhinoInside redistribution.

### Threading and Transactions

RookBIM must respect Revit's threading and transaction model:

- Read operations should run on the correct Revit/Rhino UI context.
- Write operations must use explicit Revit transactions.
- Mutating tools should never silently write during a query.
- Transaction failures should return structured diagnostics.
- Selection/highlighting may require UI-context dispatch.
- Long scans should be cancellable or bounded.

### Error Model

Core error codes should be explicit:

```text
not_rhino_inside
revit_unavailable
no_active_document
document_closed
element_not_found
linked_document_unloaded
invalid_element_id
invalid_unique_id
unsupported_category
transaction_required
transaction_failed
permission_denied
workshared_checkout_required
```

Every error should include enough identity context to debug the failure without guessing.

### Response Contract

Element responses should use a compact identity envelope:

```json
{
  "document": {
    "guid": "...",
    "title": "...",
    "path": "...",
    "isFamilyDocument": false,
    "isWorkshared": true
  },
  "element": {
    "id": 12345,
    "uniqueId": "...",
    "fullUniqueId": "...",
    "name": "...",
    "category": "Walls",
    "type": {
      "id": 67890,
      "uniqueId": "...",
      "familyName": "Basic Wall",
      "name": "Generic - 8 inch"
    }
  }
}
```

For list queries, return concise summaries by default and allow detail expansion.

## First Slice Recommendation

The first RookBIM implementation slice should be read-only and small:

```text
revit_active_document
revit_document_info
revit_query_elements
revit_element_info
revit_element_parameters
revit_select_elements
```

Acceptance evidence:

- Rook refuses with `not_rhino_inside` or `revit_unavailable` when not hosted in Revit.
- In RhinoInside/Revit, `revit_active_document` returns document identity and host process evidence.
- `revit_query_elements` can return a bounded list of elements by category.
- `revit_element_info` resolves by `elementId` and by `uniqueId`.
- `revit_element_parameters` returns names, storage types, display values, and raw values where safe.
- `revit_select_elements` selects/highlights returned elements in the active Revit UI.
- Every result includes document GUID and element identity.
- No write transaction is opened.
- No Grasshopper canvas state is required.

This slice proves the core thesis without taking on authoring risk.

## Design Principles

1. **Revit remains authoritative.**
   RookBIM should not treat Rhino geometry as the source of truth unless the user explicitly makes it a generated design source.

2. **Identity before geometry.**
   Every BIM result should carry stable identity first, geometry second.

3. **Read before write.**
   Build trust through inspection, selection, and explanation before mutation.

4. **Grasshopper is optional.**
   GH is a powerful visual workflow surface, but direct Revit MCP tools should not depend on GH.

5. **Writes require transaction discipline.**
   Mutations should be explicit, scoped, auditable, and undoable.

6. **Linked models are first-class.**
   Linked identity must be modeled explicitly rather than flattened away.

7. **Metadata is a contract.**
   When Rook creates or derives Rhino objects from Revit elements, it should stamp Rook-owned metadata rather than relying only on names.

8. **Agents need bounded tools.**
   Avoid "do anything to the model" tools. Prefer small, composable, inspectable operations.

## Risks and Constraints

### Revit API Discipline

Revit is strict about API context, transactions, and document state. RookBIM must not bypass those constraints. The architecture should make invalid contexts fail clearly.

### Identity Drift

Delete/recreate workflows, copy operations, groups, links, detachments, and upgrades can change identity. RookBIM should report identity confidence and avoid pretending identity is immutable.

### Worksharing

Writes may require element checkout or workset permissions. Even read operations should surface worksharing context where useful.

### Performance

Full-model scans can be expensive. Query tools need limits, filters, pagination, and summary/detail modes.

### Safety

BIM writes can have real project consequences. Early RookBIM should be read-only. Later write tools should require explicit transactions, previews, and clear result summaries.

### Source of Truth Confusion

Round-trip workflows can create confusion about whether Revit, Rhino, or GH owns an artifact. RookBIM metadata should declare role and provenance.

## Near-Term Research Questions

- Which Revit document GUID should RookBIM expose as canonical across local, central, detached, and cloud models?
- How should RookBIM represent linked model identity in MCP schemas?
- Can selection/highlight be implemented as a safe read/UI operation without transaction overhead?
- What is the smallest useful element summary shape for large queries?
- Which parameters should include raw values, display values, units, and storage type?
- How should RookBIM paginate or stream large element query results?
- Should RookBIM store model snapshots for diffing, and if so where?
- How should RookBIM mark Rhino objects that are derived from Revit but not intended to sync back?
- Which GH/Revit components should be wrapped as recipes rather than direct Revit API tools?

## Long-Term Vision

The long-term vision is not just an MCP wrapper around Revit. It is a model-aware operating layer for design and documentation work:

- Ask the model questions.
- Get traceable answers.
- Select and inspect the exact elements involved.
- Generate controlled design options.
- Move between Revit semantics and Rhino geometry.
- Use Grasshopper when visual computation is useful.
- Stamp provenance on derived artifacts.
- Detect stale studies when the BIM changes.
- Make safe, explicit, auditable transactions.
- Produce reports and documentation from live model state.

This is why the RookBIM opportunity is larger than a normal plugin feature. Rook can become the place where agents, BIM identity, geometry, and computational design meet.

## Immediate Next Step

Promote the queued RookBIM item when the active queue permits or when user direction explicitly prioritizes BIM. The first formal spec should scope the read-only foundation slice:

```text
RookBIM Phase 1: active document, element query, parameter inspection, and selection
```

That spec should define exact routes, MCP schemas, managed companion boundaries, Revit context dispatch, test strategy, and live RhinoInside/Revit acceptance proof.
