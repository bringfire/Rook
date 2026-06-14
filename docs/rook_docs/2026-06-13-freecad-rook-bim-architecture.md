# FreeCAD → Rook → Rhino → VE: AI-Native BIM Architecture

> **Status:** Spike complete, architecture grounded. Identity model corrected by
> live evidence. PoC not yet built.
> **Provenance:** All "Observed" facts below were produced by running spike
> scripts under **FreeCADCmd 1.1.1** (`Libs 1.1.1R20260414`), per-user install at
> `C:\Users\aryan\AppData\Local\Programs\FreeCAD 1.1\bin\freecadcmd.exe`, on
> 2026-06-13. Scripts + raw outputs live beside this doc in
> `docs/rook_docs/freecad-spike/` (`spike_headless_bim.py`,
> `spike_identity_lifecycle.py`, `spike_id_export_stability.py`, and their
> `results*.json` / `blueprint.json` / `reference.*`).

---

## 1. Thesis

An AI-native CAD/BIM stack with a clean division of authority:

- **FreeCAD** owns design intent: parameters, recompute, dependency graph, BIM
  hierarchy and relationships. Source of truth.
- **Rook** extracts and normalizes that into an agent-readable semantic graph,
  projects it onto Rhino, and validates Rhino geometry against FreeCAD reference
  geometry.
- **Rhino** receives read-only linked/native geometry with rich metadata for
  spatial coordination. *Parametric-aware, never parametric.*
- **VE / splats** are real-time view-only. Never authoritative for quantities,
  topology, constraints, or BIM semantics.

This is not greenfield. It is the **visual-subsystem pattern** Rook already uses
for Vision (domain → programmatic → human; artifacts as the human↔agent
currency; view-layer never authoritative) and the **North-Star artifact/work-unit
+ fan-in** topology (`docs/superpowers/specs/2026-06-03-rook-north-star-topology.md`).
The FreeCAD artifact bundle *is* a work unit; "validate Rhino against FreeCAD
reference" *is* fan-in.

---

## 2. Spike results — observed facts

| Assumption under test | Verdict | Evidence |
|---|---|---|
| App/Part/PartDesign/Mesh/Draft recompute headless | **TRUE** | `FreeCADCmd` runs `App.GuiUp == False`; recompute returns cleanly |
| Arch/BIM object creation headless (`import Arch`, `makeWall`, `makeStructure`, `makeWindow`) | **TRUE** | All created without GUI; `import Arch` clean |
| STEP / BREP export headless | **TRUE** | `Part.export` → 7.9 KB STEP; `Compound.exportBrep` → BREP |
| IFC export headless | **TRUE (1.1.1)** | `from importers import exportIFC; E.export(...)` → 3.2 KB IFC. **The unguarded `import FreeCADGui` at `exportIFC.py:47` in the *source checkout* is NOT present/triggered in packaged 1.1.1.** Don't carry a fork on that basis without re-checking your build. |
| `ifcopenshell` bundled & headless | **TRUE** | `ifcopenshell.guid.new()` works in-process |
| **GlobalId present at object creation** | **FALSE** | Fresh `makeWall` → `GlobalId == ''` (property exists, empty). Minted lazily. |
| **GlobalId is a stable cross-system spine** | **FALSE** | IFC export **overwrites** a pre-set GlobalId (`1111…aa` → `2k6r9jMO…`). Volatile. |
| **A Rook-owned property is a stable spine** | **TRUE** | Custom `App::PropertyString "RookId"` survived IFC export, save/reopen (persists in `.FCStd`), and param-change+recompute. |
| **THE SEAM: identity persists while geometry changes** | **TRUE** | Wall Height ×1.5 → volume 3.0e9 → 4.5e9, `RookId` unchanged. |
| Dependency graph extractable | **TRUE** | `obj.OutList`/`InList` → Wall `dependsOn:[Line]`, Line `dependedOnBy:[Wall]` |

**Gotchas observed (test-quality, not platform limits):**
- A bare `Arch.makeWindow(width, height)` with no base sketch creates an
  **invalid** object whose `getSubVolume` raises during recompute, which
  **poisons the host Wall's Shape** (null shape, infinite bbox, Length 0) and
  breaks IFC export. Headless window/opening creation requires a proper hosted
  base sketch. Treat openings as a real modeling step, not a one-liner.

---

## 3. Identity model (corrected by evidence)

**Spine = a Rook-minted `App::PropertyString` (e.g. `RookId`), added to every
exported FreeCAD object and set once at bundle time.** It is the durable join key
across the whole pipeline:

```
RookId (FreeCAD property)
  → blueprint.json key
  → Rhino object user-string  ("rookId": "...")
  → (future) VE splat-group id
```

- **Do not** use IFC `GlobalId` as the join key — the IFC exporter regenerates it
  (observed). Carry GlobalId in the blueprint as a *secondary, IFC-facing,
  may-change* reference only.
- `obj.Name` (string) and `obj.ID` (int) are stable **within a document** and
  immutable across save/reopen, but are **not globally unique** across bundles —
  use them as intra-document anchors, never as the cross-system key.
- Minting: `ifcopenshell.guid.new()` (bundled) or any UUID scheme. The point is
  Rook controls it; FreeCAD never rewrites it.
- **Persistence rule (Observed v4):** mint is **read-existing-else-mint**, then
  **write the `.FCStd` back** so the property is durable. Proven **idempotent** —
  a fresh package mints all RookIds (pass 1), and re-running the mint after
  save/reopen keeps every one (pass 2, no churn). Repeated exports therefore do
  **not** churn IDs *as long as* the first export persists the property back into
  `source.fcstd` (or a durable sidecar overlay). Bundle-time minting is safe only
  under this rule.

---

## 4. Artifact bundle (per work-unit)

```
source.fcstd            authoritative FreeCAD model (RookId persisted inside)
blueprint.json          semantic/parametric relationship graph (RookId-keyed)
reference.step / .brep  precise reference geometry (validation + fallback)
reference.ifc           IFC reference (secondary; GlobalId volatile)
coordination.3dm        Rhino coordination package (linked block target)
preview.glb             mesh preview source (future splat input)
validation.json         hashes, bbox, volume, tolerance, error reports
```

**Granularity: storey × discipline.** Matches FreeCAD's `BuildingPart`/Level
hierarchy *and* the North-Star fan-in merge boundary. Object-family is too fine
(refresh churn); whole-building too coarse (kills the parallelism the topology
exists for).

---

## 5. blueprint.json — minimal schema (project from IFC, don't reinvent)

IFC already models the relationships; blueprint.json is the **agent-cheap
denormalized view**, not new information. Minimal per-object record:

```json
{
  "rookId": "rook-2Fg77H8HL0EAUHFyHz9EfB",   // THE key (Rook-owned, durable)
  "ifcGlobalId": "2k6r9jMO508hOMxusWXRkR",   // secondary, may change on export
  "name": "Wall", "label": "Wall",
  "kind": "Part::FeaturePython", "ifcType": "Wall",
  "storey": "L03",
  "params": { "Length": 5000, "Width": 200, "Height": 3000 },
  "bbox": [x0,y0,z0, x1,y1,z1],
  "dependsOn": ["<rookId>"],          // from obj.OutList
  "dependedOnBy": ["<rookId>"],       // from obj.InList
  "hosts": [], "hostedBy": null,      // IfcRelFillsElement / hosting
  "voids": [], "voidedBy": null,      // IfcRelVoidsElement (openings)
  "refGeomHash": "sha256:..."         // ties to reference.step entity
}
```

Rule: if you're adding a field IFC already models (spatial hierarchy,
`IfcRelVoidsElement`, `IfcRelFillsElement`, `IfcRelContainedInSpatialStructure`,
`IfcRelConnects*`), stop and project it instead of inventing it.

**Where it lives:** layered, reusing existing Rook muscle. `blueprint.json`
per-bundle (human-diffable, source of truth) → loaded into the existing NetworkX
mirror (`mcp_server/src/rook/scene/scene_graph.py`, MultiDiGraph) for agent
traversal → SQLite only if cross-bundle query volume later demands an index.
Do **not** start with SQLite.

---

## 6. Rook route sufficiency + gaps (audited)

**Sufficient today:** geometry `/import` (STEP/IGES/BREP/IFC/3dm),
`/export` (selective + batch), per-object metadata via `/usertext/object-set`,
batch block metadata via `/block/set-object-user-strings` (supports per-index
`mappings`), linked external `.3dm` via `/block/link`
(`SetLinkedFileReference`), geometry re-sync via `/block/refresh`. The
"user-strings-as-pointers, brain-beside-artifacts" design is fully supported.

**Genuine gaps:**
1. **No auto-tag on import.** `/import` returns `importedIds[]` but tags nothing —
   needs a post-import projection pass (or a new `/import-with-metadata`).
2. **No batch user-strings for loose objects** (`/usertext/object-set` is
   one-call-per-object; only block routes batch). At storey scale this matters —
   keep objects in blocks or add a batch route.
3. **No external-ID registry** — no built-in RookId → Rhino-GUID map. Use a
   sidecar (`validation.json`) or a new `/mapping/*` route.
4. **`/block/refresh` re-syncs geometry only** — metadata is NOT re-hydrated.
   Refresh must be two-step: refresh geometry → re-project metadata from the new
   blueprint.
5. **SceneNode schema is fixed** (`SceneGraphModels.h:24`) — cannot carry
   `sourceEngine`/`semanticRecord`. Correct: keep provenance in the sidecar,
   never in the scene graph. (Consistent with "don't put the brain in Rhino.")

---

## 6b. The geometry-boundary identity join (the real step-3 risk)

The RookId spine is proven **inside FreeCAD** (§3) and the bundle is now valid
(§2 v4). What is **NOT yet proven** is that identity survives the
FreeCAD-export → Rhino-import boundary — i.e. that imported Rhino object *A* can be
mapped back to `rook-123`. This is the next risky assumption, not a solved step.

**Observed (v4 mapping probe — what identity lands inside the exchange files):**

| Format | Per-object name? | Per-object id? | RookId carried? | Verdict |
|---|---|---|---|---|
| **STEP** (`Part.export`) | **No** — only product name `"Open CASCADE STEP translator 7.8 1"` | No | No | **Identity-blind. Flattens everything.** A single STEP gives anonymous geometry — no mapping possible. |
| **IFC** (`exportIFC`) | **Yes** (`IfcWall.Name`) | Yes (`GlobalId`) | No (would need a Pset) | Identity-bearing, but GlobalId is **volatile** (regenerated on export, §3) and Rhino's native IFC import is weak. |

**Consequence — the join cannot rely on a single combined STEP.** Viable strategies,
to be decided by the step-3 spike (needs a live Rhino):
1. **Per-object STEP, RookId as filename** (`rook-123.step` → `/import` → tag
   result with `rook-123`). Deterministic mapping, exact OCCT geometry, zero
   reliance on in-file identity. Cost: N files / N imports.
2. **Rook-built-from-blueprint** — Rook constructs the Rhino geometry from
   blueprint params and tags with RookId at creation; reference STEP/IFC used only
   to **validate** (bbox/volume). Native identity; loses exact brep fidelity for
   non-prismatic shapes.
3. IFC-derived (write RookId into an IfcPropertySet, import via an IFC-capable
   path) — richest BIM, but heaviest and depends on Rhino IFC support.

Lead hypothesis: **(1) per-object STEP** for v1 (exact geometry + trivial mapping),
with (2) as the fallback for shapes that round-trip poorly.

**PROVEN (live Rhino, 2026-06-13).** Strategy 1 works end-to-end:
- `rhino_import(<rookId>.step)` returns `importedIds` → deterministic file→GUID
  map, zero reliance on in-file identity. (`$` in the RookId survived as both a
  filename and a user-string value — but still mint URL-safe, §10.)
- `rhino_usertext_object_set` writes the pointer record
  (`rookId` + `sourceEngine` + `sourceDocument` + `blueprintRef`) and reads it
  back verbatim. The "metadata points to semantic records, brain beside the
  artifacts" principle is validated live.
- **Geometry is exact** after unit normalization — Wall/Slab/Window volumes
  matched the FreeCAD manifest to full precision (2.784 / 7.2 / 0.00108 m³).

**NEW finding — units (only visible at the live boundary):** FreeCAD authored in
**mm**; the Rhino doc was **meters**, and import scaled mm→m. Raw numeric
comparison fails; `validation.json` **must** record source + target units and
normalize (volume factor 1e9). **And:** `rhino_measure_bbox` returns a *loose*
(~20% inflated) box — use `rhino_measure_volume` (exact) for validation, never the
raw bbox.

---

## 7. Splat / VE reality (audited — keep out of v1)

- **mesh2splat is "headless" only in the no-window sense — it requires an
  OpenGL 4.5 GPU** (offscreen GLFW context + geometry/compute shaders). Won't run
  on a CPU-only/CI box. Input is `.glb` only. Combined with FreeCAD's glTF path
  being GUI-bound (`ImportGui`), the preview leg needs a GPU host **and** a
  headless OBJ/PLY→glb hop.
- **VE splats are identity-blind.** `GaussianSplat` carries position/scale/
  rotation/opacity/color and nothing else; chunks are LOD groupings, not objects.
  `.veprim` is object-aware (per-primitive material), but conversion to splats
  **loses identity**. Per-object splat selection (Q8) is ~500–1k LOC of new
  plumbing (per-splat ID buffer + segmentation/picking pass), not a flag. Cheapest
  honest path later: convert **per-object** so identity lives in the grouping.

---

## 8. Decisions locked

- **v1 = perception-only behavior, write-back-ready data.** Rhino read-only.
  Success = an agent selects a read-only object and answers: what is it, what
  FreeCAD/IFC object produced it, what storey/system owns it, what does it depend
  on, what depends on it, **and which source parameter would change it**. That
  last question is the seam that proves future editability without paying for
  mutation. No BIM mutation endpoint in v1, but `blueprint.json` reserves a
  `ChangeRequest` shape and every Rhino object points back to an editable source
  record.
- **Refresh success criterion (softened per review):** the goal is **"the same
  semantic `RookId` resolves to the refreshed Rhino geometry"** — *not* "the same
  Rhino GUID/object survived." `/block/refresh` is geometry-only and may replace
  objects; identity continuity lives in the RookId↔geometry re-projection, not in
  Rhino object persistence.
- **Identity spine = Rook-owned `RookId` property**, not IFC GlobalId (evidence,
  §3).
- **Splats deferred** past v1 (GPU + identity plumbing, §7).

---

## 9. Proof-of-concept plan

**One storey: grid + slabs + walls + openings.** Openings are the payload — they
exercise the `IfcRelVoidsElement` host/cut relationship that is the whole reason
blueprint.json beats a flat geometry dump.

**Sequence (revised per review — do NOT start the Rook projection route until the
geometry-boundary mapping is proven):**

1. **DONE (v4).** Valid one-storey source package: wall + slab + real hosted
   opening (Arch Window with a base rectangle in the wall plane — cuts the wall,
   216e6 mm³ removed, valid shape). RookId minted on every semantic object with
   the read-existing-else-mint persistence rule, proven idempotent. Clean
   RookId-keyed `blueprint.json` emitted. *Remaining polish:* populate inverse
   `voidedBy` (derive from `window.hostedBy`), set slab `IfcType=Slab` (defaults
   to Beam), give infrastructure objects RookIds or filter them.
2. **DONE (v4).** `blueprint.json` regenerated (RookId-keyed, real bbox,
   dependsOn / hostedBy captured).
3. **DONE (live, 2026-06-13).** Export/import mapping proven (§6b "PROVEN"):
   per-object STEP → `importedIds` → `rookId` user-string pointer → geometry exact
   after mm→m normalization. Per-object STEP is the chosen v1 strategy.
4. **NEXT — design/add the Rook metadata-projection route**, informed by step 3:
   batch the import+tag+validate flow (one call per bundle, not per object),
   record units in `validation.json`, validate by volume (not loose bbox). Also
   evaluate the existing `rookbim_*` element API as a possible projection surface.
5. Expose semantic lookup: agent selects a Rhino object → resolve `rookId` →
   answer the six perception questions from the blueprint + NetworkX graph.
6. **The round-trip that matters:** change a parameter in FreeCAD → recompute →
   re-export → `/block/refresh` → re-project metadata → confirm **the same
   `rookId` resolves to the refreshed geometry** (not "the same Rhino GUID
   survived" — see §8). Static first-import is not the test; the refresh loop is.
7. (Optional, GPU box only) `preview.glb` → mesh2splat → VE view.

---

## 10. Open questions / next

- **Window/opening modeling — SOLVED (v4).** Recipe: `Draft.makeRectangle(w,h)`
  placed in the wall plane (rotate 90° about X so the rect lies in XZ), then
  `Arch.makeWindow(rect, width > wall_width)` with `win.Hosts=[wall]`; recompute
  cuts the wall cleanly. The *bare* `makeWindow(w,h)` (no base sketch) is what
  poisons the host wall — don't use it. (Box-subtraction via
  `Arch.removeComponents(box, host=wall)` is the robust fallback.)
- **Export-mapping — RESOLVED (§6b "PROVEN", §9 step 3).** Per-object STEP +
  `importedIds` + `rookId` user-strings; geometry exact after mm→m normalization.
- **Re-verify the `exportIFC.py:47` trap against the exact FreeCAD build you ship
  on** — it was absent in packaged 1.1.1 but present in the source checkout.
- **RookId charset (Observed v4).** `ifcopenshell.guid.new()` uses the IFC base64
  charset including `$` (e.g. `rook-3b$R$EhWvAQ9qLKbKAtna1`), which is fragile as a
  filename/URL (shell `$` expansion, path quoting). If RookId is used as a STEP
  filename (§6b strategy 1), mint with a **filename/URL-safe** scheme (uuid4 hex
  or base64url) — keep the canonical RookId in the manifest regardless.
- **RookId injection point** — add the property at bundle-export time vs. at model
  authoring time. Bundle-time keeps authoring tools clean.
- **Batch metadata projection route** — decide build-vs-block-workaround before
  scaling past a single storey.

---

## 11. RookBIM audit — can `Rook.Bim` be the provider-neutral element surface?

> Bounded audit of the existing `Rook.Bim` contract + RevitRookBim runtime
> (read 2026-06-13). Question: does Rook already have the agent-facing BIM element
> abstraction, and can it span Revit **and** FreeCAD projection?

**Verdict: yes for the element surface, no for the relationship graph — and that
split is the answer.** `Rook.Bim` is structurally **element-centric**;
blueprint.json is **graph-centric**. Do not merge them — **join on `rookId`**.
RookBIM widening is a bounded extension (~4 enum/scope/diagnostic spots + one new
runtime class), not a rewrite. Adapt into it; don't duplicate it.

**What exists (evidence):**
- `BimElementIdentity.Source` is already a free discriminator, default `"revit"`
  (`BimContracts.cs:197`). `UniqueId`/`FullUniqueId` (`:209-211`), `ElementId:int?`
  nullable (`:207`).
- `IRookBimRuntime` — clean 8-method interface (status, active_document,
  list_categories, query_elements, element_info, element_parameters,
  select_elements, clear_selection) (`IRookBimRuntime.cs`).
- `RookBimRuntimeRegistry.Install(runtime, source)` — **single-active-runtime**
  (`RookBimRuntimeRegistry.cs:33`). `RookBimModule.Activate` installs
  `RevitRookBimRuntime` only under Rhino.Inside.Revit, else Unavailable
  (`RookBimModule.cs:23`).
- Resolution **prefers `UniqueId` over `ElementId`**
  (`RevitIdentitySerializer.cs:103-121`) — so a UniqueId-keyed identity is the
  primary path (good for rookId).
- Params shape `{source,name,storageType,rawValue,displayValue,isReadOnly,
  builtIn,guid}` (`RevitParameterSerializer.cs:35-48`) — maps fine to FreeCAD
  Length/Width/Height.

**The gap (central finding):** `BimElementSummary = {Identity, Name, Category,
Type}` (`BimContracts.cs:329`) — **no relationship fields at all**. The dependency
neighborhood (the reason blueprint beats a flat dump) has no home here. Boundary,
not bug.

**Revit-specificity to widen (Q6):**
- `BimDocumentGuidSource.RevitPersistentGuid` (`:31`) → add `FreeCadDocument`/
  `RookBundle` or rename `HostPersistentGuid`.
- `ElementId:int?` + six `Linked*` fields (`:207-223`) — nullable, FreeCAD leaves
  null.
- `BimQueryScope.ActiveView` (`:44`) — Revit view; FreeCAD needs `Layer`/`All`.
- `NotRhinoInside`/`RevitUnavailable` error codes (`:11-13`).
- **Most misleading:** `BimHandler.cs:360-407` hard-codes
  `domainId:"bim.rhino_inside_revit"` + "Open Rhino through Rhino.Inside.Revit"
  guidance — a FreeCAD user gets nonsense Revit advice. Must become
  provider-aware.

**`FreeCadProjectionRuntime` (thin; lives in core `src/Rook`, NOT the
Rhino.Inside-gated `src/RookBim`):**
```
Source         = "freecad"
UniqueId       = rookId
FullUniqueId   = rookId
ElementId      = null
Category.Name  = ifcType
Parameters     = blueprint params
SelectElements = resolve rookId → Rhino GUID → rhino_select
```
Backed by blueprint.json + Rhino user-strings + Rhino selection. Registration: add
a non-Revit branch that installs this instead of Unavailable. Single-active-runtime
is acceptable (a session is Revit-hosted XOR Rhino-native projection); a
multiplexer-by-`Source` is only needed if both must coexist.

---

## 12. The element ⇄ relationship boundary (contract language)

Two complementary surfaces, one join key (`rookId` = `BimElementIdentity.UniqueId`
with `Source="freecad"`). This boundary is normative.

**RookBIM (`/bim/*`) owns element lookup — and only this:**
- list / query elements
- element identity
- category / type
- parameters
- select the corresponding Rhino/Revit element

**Blueprint + graph (blueprint.json, scene_graph / NetworkX) owns relationships —
and only this:**
- dependency graph (dependsOn / dependedOnBy)
- host / void / fill relationships
- spatial containment relationships
- change-impact questions
- "what parameter would change this?"

Neither side reaches into the other's table. `BimElementSummary` gains no
relationship fields; the graph stores no parameter/category authority. An agent
answering a perception question queries **both** and stitches on `rookId`.
