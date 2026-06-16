# RookBIM Revit→Rhino Geometry + Label/Sidecar Export v1 — design

> **Status (2026-06-16): DESIGN APPROVED (brainstorm complete, review corrections folded) — ready for writing-plans.**
> Slice owner: RookBIM track, branch `feature/spatial-intelligence`
> (worktree `C:/Users/aryan/source/repos/rook-spatial`; `main` untouched).
>
> First slice of the **RookBIM export** track, spun up while the spatial-intelligence
> read-model track is **parked**. Produces **calibration fixtures** (Rhino-consumable
> geometry + Revit-derived semantic labels) that a future **Threshold Calibration v1**
> slice will consume *offline* to calibrate `contains_semantic` confidence tiers.
>
> **Architectural constraint (load-bearing):** this is a one-way, file-producing export.
> It does **NOT** integrate RookBIM into the Rhino spatial-intelligence runtime, the active
> Rhino document, or the scene graph. RookBIM emits geometry + sidecars; spatial intelligence
> consumes the *files* later, as fixtures. The two systems stay separate.
>
> Companions: `docs/rook_docs/2026-06-16-spatial-intelligence-pivot-checkpoint.md` (why this
> track exists / return point), `docs/rook_docs/2026-06-13-freecad-rook-bim-architecture.md`
> (identity-spine + artifact-bundle + element⇄relationship-boundary precedent),
> `docs/superpowers/specs/2026-06-16-semantic-containment-refinement-v1-design.md` (the
> downstream consumer whose thresholds these fixtures calibrate). Memory:
> `project_freecad_bim_architecture`, `project_semantic_containment_refinement_v1`.

---

## 1. Problem & goal

Semantic Containment Refinement v1 ships confidence-scored `contains_semantic` edges, but its
ordinal thresholds (`MARGIN_EPS`, `DEPTH_*`, `VOLUME_RATIO_*`) are **uncalibrated** — the live
positive rate on `SpatialTest.3dm` was 27/28, i.e. almost certainly permissive. Calibration needs
**labeled positive/negative containment examples**, and the richest source of ground-truth spatial
labels is a real BIM model: Revit already *knows* which element is in which room, what hosts what,
and what level an element belongs to.

**Goal of v1:** a **read-only RookBIM export op** that, from an open Revit model, exports a
caller-selected set of elements into a **Rhino-consumable `.3dm`** plus a **sidecar JSON** that maps
every exported Rhino object back to its Revit identity, category/type, level, host, room/space
association, transform/bbox, and geometry representation/quality — and a **validation JSON** that
records units, counts, and hashes. The artifact bundle is a clean, self-describing calibration
fixture: every exported Rhino object joins back to exactly one Revit label record.

### In scope
- A read-only `export_elements` op on `IRookBimRuntime` (Revit read only — **no `Transaction`**).
- Strict one-of selection: reuse the existing `query_elements` selector **XOR** an explicit identity
  list. (`select_elements`-style.)
- In-process Revit→RhinoCommon geometry conversion (Brep-preferred, mesh fallback, optional
  bbox proxy), built into a **standalone in-memory `File3dm`** written to disk.
- Three-file artifact bundle: `<name>.3dm` + `<name>.sidecar.json` + `<name>.validation.json`.
- Per-element Revit identity + semantic labels (level, host, room/space, category, family/type),
  each label carrying source + missing-reason so absence is explicit, not implied.
- Rooms/spaces exported as **separate, typed reference geometry + labels**, degrading per-room.
- Output-path safety (absolute dir, sanitized name, no overwrite without opt-in, no path escape).
- A bijection **verification** block proving 1:1 join between Rhino objects and sidecar records.
- Native `/bim/export-elements` route + MCP `rookbim_export_elements` tool + targeting policy.
- Source-text tests (CI, no live Revit) + a gated live-verify script.

### Out of scope (deferred to later slices)
Bidirectional sync / write-back to Revit; mutating the Revit model (no `Transaction`); integrating
into the Rhino scene graph or spatial-intelligence runtime; the calibration itself (this only
*produces* fixtures); neutral-format geometry exchange (STEP/IGES/SAT — see §5, considered and
deferred); minting a Rook-owned `rookId` identity spine (Revit `UniqueId` is the v1 key, §7);
linked-model elements (the existing `LinkedElementUnsupported` boundary still holds); IFC export;
any new C++ geometry kernel work.

---

## 2. Architecture & placement

RookBIM runs **inside Rhino.Inside.Revit**, so **RhinoCommon is loaded in-process**. That is the
separation lever: the export builds a `Rhino.Geometry`/`Rhino.FileIO.File3dm` purely in memory and
`File3dm.Write(...)`s it to disk — it **never** opens or mutates the active Rhino document and never
calls into the scene graph. Geometry crosses to Rhino as *files*, exactly as a calibration consumer
will later read them.

New + touched units (follows the `RevitQueryService`/`RevitSelectionService` shape):

```
src/RookBim/Revit/RevitExportService.cs      NEW — orchestrates: resolve set → convert geometry →
                                                   assemble File3dm + sidecar + validation → write
src/RookBim/Revit/RevitGeometryConverter.cs  NEW — per-element Revit→RhinoCommon (Brep→mesh→bbox)
src/RookBim/Revit/RevitLabelExtractor.cs     NEW — level/host/room/space/type labels (+ source/missing)
src/RookBim/Revit/RevitRoomExporter.cs       NEW — rooms/spaces reference geometry + labels
src/RookBim/Revit/RevitRookBimRuntime.cs     EDIT — ExportElements() wired through the dispatcher
src/Rook/Bim/IRookBimRuntime.cs              EDIT — + BimApiResponse ExportElements(request)
src/Rook/Bim/RookBimUnavailableRuntime.cs    EDIT — + ExportElements returns Unavailable
src/Rook/Bim/BimContracts.cs                 EDIT — request/result types + new error codes
src/Rook/Handlers/BimHandler.cs              EDIT — export_elements op + route + error mapping
src/RookNative/...                           EDIT — POST /bim/export-elements proxy route
mcp_server/src/rook/server.py                EDIT — rookbim_export_elements tool (schema + dispatch)
mcp_server/src/rook/agent/tool_groups.py     EDIT — add to the bim tool group
mcp_server/src/rook/targeting.py             EDIT — policy: requires_rhino=True, risk="write"
```

**Why split the converter / label / room responsibilities into separate units:** geometry
conversion (RhinoCommon), label extraction (Revit parameter/relationship APIs), and room handling
(spatial-element APIs) are three distinct concerns with different failure modes and test surfaces.
Keeping `RevitExportService` a thin orchestrator over three focused collaborators preserves the
single-responsibility boundary that makes the existing query/selection/category units testable in
isolation.

### Concurrency / dispatch
`ExportElements` runs entirely inside the RhinoInside idling-queue dispatch (`RevitApiDispatcher`),
like every other RookBIM op — all Revit reads and the RhinoCommon conversion happen on the
Revit/Rhino UI thread. The `DispatchTimeout` (currently 5s) is **insufficient** for a multi-element
geometry export; v1 introduces a **separate, larger export timeout** (named constant, e.g. 120s,
pinned in the plan) used only for the export dispatch. File writes happen at the end of the dispatch
body (still on-thread — acceptable for v1; an off-thread write optimization is a later concern).

---

## 3. Request contract — strict one-of selector

```jsonc
{
  // exactly ONE of selector | identities (validation rejects both / neither)
  "selector":   { "scope": "active_view|document", "category": "Walls",
                  "filters": [ /* BimQueryFilter[] */ ], "limit": 100 },
  "identities": [ { "source":"revit", "uniqueId":"...", "elementId":123, "documentGuid":"..." } ],

  "output": {
    "directory": "<absolute local dir>",   // required, must be absolute + local
    "name":      "walls-fixture",          // required, sanitized: no path separators / traversal
    "units":     "meters",                 // output .3dm unit system; default meters. MUST be one of
                                           // meters|millimeters|centimeters|feet|inches — an unknown
                                           // unit is rejected at validation (no silent fallback).
    "overwrite": false                     // default false — refuse to clobber an existing bundle
  },

  "rooms":          "both|labels_only|exclude",  // default "both"
  "allowTruncated": false,   // default false — truncated selector is a hard failure unless opted in
  "allowBboxProxy": false    // default false — bbox proxy is a diagnostic last resort, not a mode
}
```

**Selector rules:**
- `selector` and `identities` are **mutually exclusive and exactly one is required** →
  `InvalidScope` otherwise. `selector` reuses the validated `BimQueryElementsRequest` path verbatim
  (scope/category/filters/limit, including the `document`-scope-requires-category rule). `identities`
  mirrors `BimSelectElementsRequest` resolution (`RevitIdentitySerializer.Resolve` per identity).
- **No silent partial fixtures (review guard 1):** if the `selector` resolution is **truncated**
  (more matches than `limit`) and `allowTruncated != true`, fail `query_truncated` with the counts —
  never emit a partial bundle. With `allowTruncated: true`, export the capped set and record
  `truncated: true` in the sidecar.
- The **resolved identity set is frozen into the sidecar before any geometry conversion** — the
  bundle always records exactly which elements were selected and by what request.
- Linked-model identities remain unsupported (`LinkedElementUnsupported`), unchanged from Phase 1.

---

## 4. Output-path safety (review correction 2)

This is a filesystem-writing tool; treat it as one even though Revit is read-only.

- `output.directory` **must be an absolute, local directory path** → `OutputPathInvalid` otherwise
  (reject relative, UNC-ambiguous, or non-local paths per the plan's pinned policy).
- `output.name` is **sanitized**: reject path separators (`/`, `\`), `..`, drive qualifiers, and
  reserved device names; allow a conservative `[A-Za-z0-9._-]` set → `OutputPathInvalid` otherwise.
- The bundle is written to a **deterministic file prefix** inside `output.directory`:
  `<name>.3dm`, `<name>.sidecar.json`, `<name>.validation.json`.
- **No overwrite unless `output.overwrite == true`:** if any of the three target files already
  exists and overwrite is false → `OutputPathInvalid` (`reason: bundle_exists`), nothing written.
- After computing the final absolute paths, **re-verify they remain inside the intended directory**
  (canonicalized) — reject anything that escapes → `OutputPathInvalid`.
- **All-or-nothing write:** assemble all three artifacts in memory, validate paths, then write; a
  write failure mid-bundle attempts cleanup of partials and returns `ExportFailed`. The response
  returns the **exact absolute paths** of all three files.

---

## 5. Geometry conversion (review corrections 1 & 3) — LOCKED

**v1 geometry path (locked; neutral-format STEP/IGES/SAT considered and deferred):**

```
Revit Solid/Face geometry
  → RhinoCommon Brep via the in-process Rhino.Inside.Revit converter (reflection) if available
  → else mesh fallback via Revit Face.Triangulate → RhinoCommon Mesh
  → else bbox proxy  (ONLY if allowBboxProxy == true; otherwise the element is recorded "failed")
```

- **Brep path = in-process Rhino.Inside.Revit converter via reflection.** We are guaranteed to be
  running inside Rhino.Inside.Revit (the module only activates under it), so the RIR converter
  assembly is already loaded in the AppDomain. RookBIM **must not** add a hard reference to
  `RhinoInside.Revit` (a source-test forbids it, and `RevitApiDispatcher` already establishes the
  reflection pattern for `RhinoInside.Revit.Revit`). The converter (e.g. the `GeometryDecoder`
  `Solid→Brep` extension) is resolved by reflection; **if resolution fails for any reason, fall
  through to mesh** — never hard-fail the element on a converter miss.
- **Mesh fallback** uses Revit `Solid.Faces` → `Face.Triangulate(level)` → RhinoCommon `Mesh`.
  Deterministic, no RIR dependency.
- **Bbox proxy** is a **diagnostic last resort**, emitted only when `allowBboxProxy == true`. With
  it false, an element that yields neither Brep nor mesh is recorded `failed` (and still gets its
  identity/label record — it just has no geometry object in the `.3dm`).
- **Never-silent fallback:** every exported record carries
  - `geometryRepresentation` ∈ { `brep`, `mesh`, `bbox_proxy`, `none` } (`none` for a `failed`
    element that produced no geometry object — distinct from `bbox_proxy`, so a consumer never
    mistakes "made nothing" for "made a box")
  - `geometryQuality` ∈ { `converted_brep`, `mesh_fallback`, `bbox_only`, `failed` }
  - `fallbackReason` (null on `converted_brep`; else why it degraded)
  - `sourceRevitGeometryKind` (e.g. `solid`, `mesh`, `geometry_instance`, `none`)
  - **`converted_brep` is defined narrowly:** "a non-tessellated Revit solid converted to a Rhino
    Brep via the RIR converter" — it explicitly does **NOT** claim geometric-truth exactness. The
    vocabulary deliberately avoids the word `exact`.
- **Units:** Revit internal units are feet. The output `.3dm` is created with the requested
  `units` (default meters); geometry is scaled feet→target with the explicit factor, and the factor
  + source/target units are recorded in `validation.json` (the FreeCAD units lesson — raw numeric
  comparison across a unit boundary is poison). Per-element transform/bbox in the sidecar are in
  **output units**.
- Physical elements land on a dedicated `.3dm` layer **`RookBIM::Model`**; each object is stamped
  with the join-key user-strings (§7).

---

## 6. Rooms/spaces (review correction 4) — typed separately, degrade per-room

`rooms` controls room/space handling: `both` (default), `labels_only`, `exclude`.

- Rooms/spaces are exported as **spatial-structure reference objects, NOT physical elements.** Their
  geometry (when present) goes on a distinct layer **`RookBIM::Rooms`** and is flagged
  `referenceGeometry: true` so a consumer never mistakes a room volume for a modeled object.
- They live in a **separate sidecar section** `rooms[]` / `spaces[]`, with:
  `roomId`, `uniqueId`, `documentGuid`, `number`, `name`, `level`, `phase`, `bbox`,
  `boundaryLoops` (only if cheaply available), and
  `geometryRepresentation` ∈ { `room_volume_brep`, `room_mesh`, `boundary_2d`, `label_only` }.
- **Per-room degrade WITHOUT failing the export:** with `rooms: "both"` the exporter *attempts*
  volume geometry, then degrades that individual room to `room_mesh` → `boundary_2d` →
  `label_only` as extraction permits. A room whose volume can't be extracted is **not** an export
  failure as long as its label record is emitted. (`SpatialElementGeometryCalculator` is read-only.)
- **Calibration must opt in to spatial-structure containment.** Room geometry is kept on its own
  layer and its own sidecar section so it **never silently pollutes object↔object containment
  fixtures**. A consumer that wants room-contains-element ground truth reads the `rooms[]` section
  and the per-element `containingRoomId`; a consumer doing object↔object work ignores `RookBIM::Rooms`.

---

## 7. Identity, labels & sidecar (review correction 5)

### Join key
Primary join key = **`(documentGuid, revitUniqueId)`** — Revit `UniqueId` is persistent/stable
across sessions (unlike FreeCAD's volatile IFC `GlobalId`), so for a one-way export it is a genuine
stable spine. **No Rook-owned `rookId` is minted in v1.** Every sidecar record carries the full
document identity so the key is globally unambiguous even if the local JSON map is keyed by
`revitUniqueId` alone.

Each exported Rhino object is stamped with user-strings:
`rook.source = "revit"`, `revit.uniqueId`, `revit.elementId`, `revit.category`, and optional
`rookbim.exportId` (a within-bundle ordinal for convenience). These are the in-`.3dm` pointers; the
sidecar is the brain (the "metadata-as-pointers, brain-beside-artifacts" rule).

### Semantic labels — every label is honest about its provenance
Revit room/host/level relationships are **not uniformly available** for every element type, so the
sidecar must never imply certainty. Each relationship/label is an object, not a bare value:

```jsonc
"level": {
  "value": "L03",
  "source": "revit_api|parameter|derived|unavailable",
  "confidence": "high|medium|low",
  "missingReason": null            // populated when value is null / source is "unavailable"
}
```

Per-element label set: `level`, `hostId` (host element's join key), `containingRoomId`,
`containingSpaceId`, `fromRoomId` / `toRoomId` (doors, where available) — each in the
`{value, source, confidence, missingReason}` shape. Element record also carries (plain, from the
already-built serializers): identity, `category`, `family`/`type`/`name`, `transform`, `bbox`,
and the §5 geometry fields.

### Sidecar (`<name>.sidecar.json`) sections
1. `request` — the original selector/identities + `rooms`/`allowTruncated`/`allowBboxProxy` flags.
2. `resolved` — the **frozen** resolved identity set + `truncated` status (§3).
3. `elements[]` — per-element identity + labels + geometry fields (above).
4. `rooms[]` / `spaces[]` — §6 reference records.

### Validation (`<name>.validation.json`) — the calibration-trust block
`schemaVersion`, source/target units + scale factor, document identity, counts
(`requested → resolved → exported{brep,mesh,bbox} → failed`, plus room counts by representation),
and content hashes (`.3dm` sha256, sidecar sha256) so a consumer can detect drift.

---

## 8. Verification (the joinability proof)

The export result includes a `verification` block, and a gated live script re-proves it end-to-end:

- **Bijection:** every geometry object written to the `.3dm` has join-key user-strings that resolve
  to a known exported record (an `elements[]` element OR a `rooms[]` room with geometry), and
  **every** exported record that claims a geometry representation (`brep`/`mesh`/`bbox_proxy`, or a
  room with non-`label_only` geometry) has **at least one** matching `.3dm` object. A single key may
  map to **more than one** object — a multi-solid element legitimately emits one Brep object per
  solid — so multiple-objects-per-key is valid, not a duplicate error. `failed`/`label_only` records
  have **no** `.3dm` object by definition (and verification asserts that too). (Implementation: the
  reconciliation is a pure, unit-tested `Rook.Bim.BimExportBijection.Verify` over the stamped object
  keys vs. the union of element + room-geometry keys; room objects live on the `RookBim::Rooms`
  layer, elements on `RookBim::Model`.)
- **Reconciliation:** `requested == resolved` (or `resolved < requested` only with `truncated`/
  filtered-out reasons enumerated); `resolved == exported + failed`; counts agree across sidecar and
  validation.
- **Determinism aid:** objects and records are emitted in a stable order (sorted by join key) so two
  exports of the same selection diff cleanly.
- The `verification` block reports `ok: true|false` + any discrepancies; a failed bijection is an
  `ExportFailed` (the bundle is not a trustworthy fixture).

---

## 9. Registration & error model

- **Contracts** (`BimContracts.cs`): `BimExportElementsRequest` (+ `BimExportOutput`,
  `BimExportSelector` reuse of `BimQueryElementsRequest`), `BimExportResult` (paths, counts,
  verification). New `BimErrorCode`s: `QueryTruncated`, `OutputPathInvalid`, `NoExportableGeometry`,
  `ExportFailed`. Extend `BimHandler.MapErrorCode` (snake_case wire codes) accordingly.
- **`BimHandler`**: add `export_elements` to `ExpectedBimOps`, a dispatch arm
  (`runtime.ExportElements(Deserialize<BimExportElementsRequest>(body))`), `RouteForOp`
  (`POST /bim/export-elements`), and diagnostic reason mapping for the new codes.
- **Native**: add the `POST /bim/export-elements` proxy route mirroring the existing per-op routes
  (forwards body to managed `BimHandler.Dispatch` with `op="export_elements"`).
- **MCP** (`server.py`): `rookbim_export_elements` tool — input schema (one-of selector/identities,
  output block, rooms/allowTruncated/allowBboxProxy, port), dispatch case →
  `call_rhino("/bim/export-elements", "POST", arguments, port=port)`. Add to the bim
  `TOOL_GROUPS` entry. **Targeting policy:** `requires_rhino=True`, `risk="mutate"` — the valid
  `Risk = Literal["read", "mutate", "meta"]` has no `"write"` value, and the mutation here is
  **filesystem artifact creation only; both the Revit and Rhino documents remain read-only**. Add
  to `_ALL_KNOWN_TOOLS`. Place `rookbim_export_elements` in the **full `rookbim` group only** — do
  **NOT** add it to `rookbim_readonly` / `READONLY_ALLOWED_GROUPS` (it is not read-only, and a
  broader file-writing-tool policy model is out of scope for v1).
- `NoExportableGeometry` is returned when a selection resolves to ≥1 element but **zero** produce any
  geometry **and** `allowBboxProxy` is false (the bundle would be all-`failed`) — a clear signal to
  retry with `allowBboxProxy: true` or a different selection.

---

## 10. Testing

- **Source-text tests** (`src/RookBim.Tests`, no live Revit — the existing CI pattern). Assert:
  - `IRookBimRuntime.ExportElements` exists; `RevitRookBimRuntime` wires it through the dispatcher
    with the larger export timeout; `RookBimUnavailableRuntime` implements it as Unavailable.
  - `BimHandler` registers `export_elements` (op set, dispatch arm, route, error mapping for the 4
    new codes).
  - `RevitExportService`/converter use the **reflection** Brep path and the `Face.Triangulate`
    fallback; **no hard `RhinoInside.Revit` reference** (extend the existing forbidding assertion);
    **no `Transaction`** anywhere in the new Revit files (extend the existing invariant test).
  - Output-path safety: name sanitization + overwrite + path-escape rejection logic present.
  - Geometry vocab is exactly `{converted_brep, mesh_fallback, bbox_only, failed}` /
    `{brep, mesh, bbox_proxy}` (guard against `exact_brep` creeping back in).
  - MCP tool registration: `server.py` tool + dispatch case + `TOOL_GROUPS` membership + targeting
    policy (`requires_rhino`/`write`) + `_ALL_KNOWN_TOOLS`.
- **Pure unit tests** for the path-safety + sanitization + one-of-selector validation logic where it
  can be isolated from the Revit API (host these in `Rook.Tests` against `BimContracts` validation,
  matching `BimQueryElementsRequest.Validate()`'s testability).
- **Live verify (gated, real Revit + Rhino.Inside.Revit) — contract/wiring + bijection.** A script
  (mirroring `docs/rook_docs/occt-spike/live_verify_*.py`) opens a sample Revit model, exports a
  small category (e.g. Walls in the active view), and asserts: three files written to the expected
  paths; sidecar/validation parse; the **bijection holds**; counts reconcile; units recorded; Revit
  + Rhino remain stable. Domain richness (how many Breps vs meshes) is reported, not hard-required.

---

## 11. Dependencies & sequencing within v1

1. Contracts + error codes (`BimContracts.cs`, `IRookBimRuntime`, `RookBimUnavailableRuntime`) +
   one-of-selector / output-path validation — unit-tested.
2. `RevitGeometryConverter` (reflection Brep → mesh → bbox) + `RevitLabelExtractor`
   (level/host/room/space with source+missingReason) + `RevitRoomExporter` (per-room degrade).
3. `RevitExportService` orchestration: resolve set → freeze identities → convert → assemble
   `File3dm` + sidecar + validation → path-safe write → verification block.
4. `RevitRookBimRuntime.ExportElements` wiring (dispatcher + export timeout).
5. `BimHandler` op + native route + MCP tool + tool group + targeting policy.
6. Source-text tests + gated live-verify script.

This slice depends only on the existing RookBIM read surface (`RevitQueryService`,
`RevitSelectionService`, `RevitIdentitySerializer`, `RevitCategoryResolver`) plus in-process
RhinoCommon. It introduces **no** native geometry-kernel work, **no** scene-graph coupling, and
**no** Revit mutation.

---

## 12. Carried-forward / explicitly-deferred

1. **Neutral-format geometry exchange (STEP/IGES/SAT)** — considered and **deferred**. Adds file IO,
   view/whole-export coupling, import-tolerance questions, and a second geometry pipeline that this
   slice's purpose (Revit identity + Rhino-correlatable fixtures) does not need. Revisit only if the
   reflection Brep path proves insufficient in practice.
2. **Rook-owned `rookId` identity spine** — deferred; Revit `UniqueId` is the v1 key. Add a minted
   alias only when a single id must span multiple source engines (Revit + FreeCAD).
3. **Threshold Calibration v1** — the downstream consumer; a separate slice that reads these
   fixtures offline. Not part of this export slice.
4. **Off-thread `File3dm` write** and **incremental / streaming export** for very large selections —
   later performance concerns; v1 writes on the dispatch thread under the export timeout.
5. **Linked-model elements** — remain unsupported, consistent with Phase 1's
   `LinkedElementUnsupported` boundary.
