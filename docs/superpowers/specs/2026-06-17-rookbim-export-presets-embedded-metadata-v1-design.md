# RookBIM Revit→Rhino Export Presets + Embedded Metadata v1 — design

> **Status (2026-06-17): DESIGN — brainstorm complete, review corrections folded — ready for writing-plans.**
> Slice owner: RookBIM export track.
> Base: `origin/main` (`f47ed67d`, the PR #262 merge that shipped Export v1).
> Branch: `feature/rookbim-export-presets-v1` (worktree `C:/Users/aryan/source/repos/rook-bim-presets`).
> New work branches from `origin/main`, NOT the archived `feature/spatial-intelligence`.
>
> **Builds on** the merged Export v1
> (`docs/superpowers/specs/2026-06-16-rookbim-revit-rhino-export-v1-design.md`). It does NOT
> replace it: the existing `rookbim_export_elements` tool and its contract stay stable. This slice
> adds a **second, higher-level front door** for curated, product-grade Revit→Rhino export.
>
> **Architectural constraint (load-bearing, inherited from v1):** one-way, file-producing export.
> Revit and Rhino documents stay **read-only** — no Revit `Transaction`, no active-Rhino-document
> mutation, no scene-graph coupling. The only mutation is filesystem artifact creation.

---

## 1. Problem & goal

Export v1 (`rookbim_export_elements`) is a precise, verified, **single-category-or-identity-list**
export that produces a clean three-file bundle (`.3dm` + `.sidecar.json` + `.validation.json`). It
was built to produce calibration fixtures, and in practice it under-delivers as a **recurring
product workflow**:

- A real "bring this building shell into Rhino" task spans many categories (Walls, Floors, Roofs,
  Curtain Walls, Columns…); v1 selects one category per call.
- All physical geometry lands on a single flat `RookBim::Model` layer — no navigable structure.
- Objects are nameless in Rhino (`Brep`/`Mesh` in the UI) and carry only four user strings; the
  useful BIM metadata (level, family, type, host, room) lives **only** in the sidecar.
- The result reports flat counts with no per-category / per-quality breakdown and no human- or
  agent-readable digest.

**Goal of this slice:** a new read-only `rookbim_export_preset` op that takes a **curated export
recipe** (a named preset) and produces a product-grade bundle — multi-category selection, organized
Rhino layers, readable object names, richer embedded metadata, a self-describing summary, and a
factual relationship index — **routing through the exact same verified export core** as v1, with
v1's contract left semantically stable.

### In scope
- A new `rookbim_export_preset` MCP tool + native `/bim/export-preset` route + managed
  `export_preset` op on `IRookBimRuntime`.
- A **pure preset catalog** (`BimPresetCatalog`) mapping preset name → categories + default
  organization policy + rooms mode + per-category limit. CI-unit-testable, no Revit.
- **Multi-category resolution** (§4): per-category loop through the **existing** single-category
  query path, union/dedup by `(documentGuid, uniqueId)`, freeze identities, feed the unchanged
  convert/assemble/verify core.
- A **pure organization policy** (`BimExportOrganizationPolicy` = layer scheme + name scheme +
  metadata profile) threaded into `RevitExportService`, with a `Legacy` instance that reproduces
  v1's output semantics exactly (§3).
- **Layer organization** (§5): `by_category` / `by_level_then_category`, under the `RookBim::` root.
- **Object naming** (§6): `none|revit_name|type_only|readable|readable_with_id`.
- **Embedded metadata** (§7): `minimal|standard|full` profiles, value-only user strings.
- **Summary + relationships** (§8): rich structured summary + short digest + factual membership
  index, in **both** the response and `validation.json` — **emitted on the preset path only**.
- Include/exclude category overrides + policy overrides (§9).
- New error codes `UnknownPreset`, `NoCategoriesResolved`; targeting policy; tests + gated live
  script (§10–11).

### Out of scope (deferred)
- Any change to `rookbim_export_elements`' request/response **schema** (it keeps `Legacy` policy and
  emits no new decoration — §3.2). A future, explicitly-versioned additive enrichment of the raw
  path is a separate decision.
- Family/type layer depth (`by_category_family[_type]`) — explosion risk; revisit after inspecting
  real exports (§5).
- Bidirectional sync / write-back / Revit mutation; scene-graph integration; the calibration itself;
  neutral-format geometry (STEP/IGES/SAT); a minted Rook-owned `rookId` (Revit `UniqueId` stays the
  key); linked-model elements; IFC; any native geometry-kernel work.
- Inferred containment positives/negatives or precomputed calibration pairs (the relationship index
  is **facts only** — §8).

---

## 2. Architecture & placement

```
                 rookbim_export_preset (MCP)                 rookbim_export_elements (MCP, UNCHANGED)
                          │                                              │
                  POST /bim/export-preset                       POST /bim/export-elements
                          │                                              │
                 BimHandler "export_preset"                    BimHandler "export_elements"
                          │                                              │
              IRookBimRuntime.ExportPreset                   IRookBimRuntime.ExportElements
                          │                                              │
          RevitPresetResolver (NEW, src/RookBim)                        │
            • catalog → category list                                   │
            • per-category query via EXISTING RevitQueryService         │
            • union/dedup by (documentGuid, uniqueId) → freeze          │
            • resolved policy + per-category counts + warnings          │
                          │                                              │
                          ▼                                              ▼
          RevitExportService.Export(doc, view, request, organizationPolicy, presetContext?)
            • request carries the frozen identities (preset) OR selector/identities (raw)
            • organizationPolicy drives layer name + object name + stamped user strings
            • presetContext (preset path only) drives summary + relationships emission
```

**Why a separate front door (not a field on the existing tool):** it preserves the live-verified
`rookbim_export_elements` contract exactly, gives a clean mental model (`export_elements` = raw /
explicit; `export_preset` = curated product workflow), and lets preset behavior evolve without
destabilizing the proven selector/identity path.

**New + touched units:**

```
# Core assembly src/Rook/Bim/ (no Revit ref — unit-testable in CI)
BimContracts.cs                  EDIT — BimExportPresetRequest (+Validate), 2 error codes,
                                        summary/relationships/preset-counts POCOs
BimPresetCatalog.cs              NEW  — pure: preset name → BimPresetDefinition
BimExportOrganizationPolicy.cs   NEW  — pure value obj {LayerScheme, NameScheme, MetadataProfile}
                                        + static Legacy + Resolve(presetDefault, overrides)
BimExportLayerNamer.cs           NEW  — pure: (category, levelValue, scheme) → sanitized layer path
BimExportObjectNamer.cs          NEW  — pure: (category, type, elementId, scheme) → sanitized name
IRookBimRuntime.cs               EDIT — + BimApiResponse ExportPreset(BimExportPresetRequest)
RookBimUnavailableRuntime.cs     EDIT — ExportPreset → Unavailable

# Revit assembly src/RookBim/Revit/ (Revit + RhinoCommon — source-text tested + live)
RevitPresetResolver.cs           NEW  — multi-category resolution → frozen identities + policy + counts
RevitExportService.cs            EDIT — accept organizationPolicy + optional presetContext;
                                        policy-driven layer/name/metadata; build summary + relationships
RevitRookBimRuntime.cs           EDIT — ExportPreset wired through dispatcher (export timeout)

# Native src/RookNative/
Handlers/GrasshopperProxyHandler.{cpp,h}  EDIT — HandleBimExportPreset
RookServer.cpp                            EDIT — POST /bim/export-preset

# MCP mcp_server/src/rook/
server.py                        EDIT — rookbim_export_preset schema + tool entry + dispatch
agent/tool_groups.py             EDIT — add to rookbim group (NOT rookbim_readonly)
targeting.py                     EDIT — _ALL_KNOWN_TOOLS (requires_rhino, mutate)
```

### Concurrency / dispatch
`ExportPreset` runs inside the RhinoInside idling-queue dispatch (`RevitApiDispatcher`), like every
RookBIM op, under the **export timeout** v1 already introduced for multi-element geometry export.
Multi-category resolution issues several Revit queries within that single dispatch body.

---

## 3. The contract-stability seam (review correction 1 & 4) — LOAD-BEARING

This is the highest-risk area of the slice. Two rules:

### 3.1 Legacy parity = semantic / API parity, NOT byte-identical `.3dm`
The existing `rookbim_export_elements` path must remain **semantically** stable:
- same flat layers (`RookBim::Model`, `RookBim::Rooms`),
- same four user strings (`rook.source`, `revit.uniqueId`, `revit.elementId`, `revit.category`) and
  the existing room strings,
- **no** object names,
- same sidecar/validation **schema**, same counts and bijection behavior.

We explicitly do **NOT** require a binary-identical `.3dm` (RhinoCommon writer internals, layer-table
ordering, etc. are not part of the contract). The parity test asserts the **observable** facts above
(layer names, user-string keys/values, absence of object names, sidecar/validation schema shape),
not a file hash.

### 3.2 New decoration is preset-path-only
`RevitExportService` is generalized to take a `BimExportOrganizationPolicy` and an **optional**
`presetContext`. The raw path calls it with `BimExportOrganizationPolicy.Legacy` and a **null**
`presetContext`:
- `Legacy` ⇒ flat layer, four user strings, no object names (the §3.1 behavior).
- null `presetContext` ⇒ **no `summary` block, no `relationships` index** in the sidecar/validation —
  the raw bundle's JSON shape is unchanged.

Summary and relationships are emitted **only** when `presetContext` is non-null (the preset path).
Any future enrichment of the raw path is a separate, explicitly-versioned decision — never a silent
side effect of this slice.

---

## 4. Multi-category resolution (review correction, prior answer) — `RevitPresetResolver`

A preset spans many categories; the proven selector is single-category. Resolution stays in managed
C# near `RevitCategoryResolver`, and the **single-category query contract is never modified**:

```
resolve(preset, request, document, activeView):
  categories := catalog[preset].categories
              + request.includeCategories            # added after expansion
              − request.excludeCategories            # removed after expansion (case-insensitive)
  perCat := []
  identities := ordered-unique map keyed by (documentGuid, uniqueId)
  for category in categories (in catalog order, then includes):
      selector := { scope: request.scope ?? activeView, category, limit: request.limitPerCategory }
      r := RevitQueryService.Query(document, activeView, selector)   # EXISTING path, verbatim
      if r is category-unresolvable/absent:
          warnings += { code: "category_unavailable", category, detail }
          perCat += { category, resolved: 0, exported: 0, failed: 0, status: "unavailable" }
          continue
      if r.truncated and not request.allowTruncated:
          return Fail(QueryTruncated, category, counts)             # same rule as v1, per-category
      for summary in r.elements:
          add (documentGuid, uniqueId) to identities                # dedup; first category wins ordering
      perCat += { category, resolved: r.returned, status: "resolved" }
  frozenIdentities := identities.values   # stable order
  return { frozenIdentities, perCat, warnings, effectivePolicy, effectiveCategories }
```

- **Dedup key = `(documentGuid, uniqueId)`**, never display name. An element matching two preset
  categories appears once.
- **Per-category counts** (`resolved` / later `exported` / `failed` / `status`) feed the summary.
- **Missing category ⇒ warning, not failure.** Hard failure only when the success condition (§4.1)
  is not met.
- The frozen identity set is fed to `RevitExportService` via the **identities path** (the request
  handed to the core carries `Identities = frozenIdentities`), so geometry conversion/export is
  deterministic and independent of later view/category changes — exactly as v1's identity path.

### 4.1 Success condition & `rooms_and_spaces` (review correction 3)
- **Default presets:** success requires ≥1 category to resolve to ≥1 element. If **all** categories
  resolve empty/unavailable ⇒ `NoCategoriesResolved` (a clear, distinct signal from
  `NoExportableGeometry`, which means elements resolved but none produced geometry).
- **`rooms_and_spaces` is a rooms-driven preset** with an **empty** category list. It must **bypass
  `NoCategoriesResolved`**. Its success condition is defined separately: **the room section was
  exported** (room geometry and/or reference labels), even when the physical element count is zero.
  A `rooms_and_spaces` export with 0 elements and N rooms is a success, not a failure.
- The `presetContext` carries a `RoomsDriven` flag so the resolver/service apply the right success
  rule without special-casing preset *names* deep in the core.

---

## 5. Layer organization (review correction 2 — `RookBim::` root)

Layer scheme enum (`BimLayerScheme`): `flat` | `by_category` | `by_level_then_category`.

- **Root casing is `RookBim::`** everywhere — matching the existing `RookBim::Model` /
  `RookBim::Rooms` constants. **No `RookBIM::`** (mixed-root hazard). Preset output uses `RookBim::`.
- `flat` ⇒ `RookBim::Model` (this is what `Legacy` uses).
- `by_category` ⇒ `RookBim::<Category>` (bounded by #categories, ~5–20).
- `by_level_then_category` ⇒ `RookBim::<Level>::<Category>` (bounded by levels × categories — the
  architectural mental model). Level comes from the existing provenance-tagged label extractor
  (`labels.Level.Value`).
- **Fallbacks:** missing level ⇒ `RookBim::_NoLevel::<Category>`; unknown/blank category ⇒
  `RookBim::_Other`.
- **Sanitization:** layer segment names are sanitized (strip `::` collisions, control chars, trim);
  the pure `BimExportLayerNamer` owns this and is unit-tested.
- **Explosion guard:** if the resulting distinct-layer count exceeds a threshold (default 64), emit a
  `layer_count_high` warning into the summary — **never fail** (unless pathological / sanitizer
  cannot produce a valid name).
- Rooms always stay on `RookBim::Rooms` (unchanged), regardless of scheme.
- Layers are **navigational, not the source of truth** — the sidecar always carries full metadata
  regardless of layer policy.

---

## 6. Object naming (prior answer)

Name scheme enum (`BimNameScheme`): `none` | `revit_name` | `type_only` | `readable` |
`readable_with_id`. **Default `readable_with_id`.**

- `readable_with_id` ⇒ `<Category> - <Type> [<ElementId>]`
  (e.g. `Walls - Generic 200mm [350123]`, `Doors - Single-Flush 0915x2134mm [312044]`).
- `readable` ⇒ `<Category> - <Type>`; `type_only` ⇒ `<Type>`; `revit_name` ⇒ `element.Name`
  verbatim; `none` ⇒ leave unnamed (Legacy uses `none`).
- **Fallbacks:** missing type ⇒ use category; missing category ⇒ `Revit Element`; missing element id
  ⇒ omit the `[…]` suffix.
- Names are **sanitized but kept readable**; the **full `UniqueId` is never in the name** — it stays
  in user strings + sidecar as the stable join key (Rhino object names need not be unique).
- The pure `BimExportObjectNamer` owns formatting + fallbacks + sanitization; unit-tested.

---

## 7. Embedded metadata (prior answer)

Metadata profile enum (`BimMetadataProfile`): `minimal` | `standard` | `full`. **Default `standard`.**
Stamped user strings are **value-only**; full `{value, source, confidence, missingReason}` provenance
lives **only** in the sidecar. **Missing / low-confidence values are omitted, not faked** (no
`"unknown"` stamps).

Prefix convention: `rook.*` = system/source, `revit.*` = raw Revit facts, `rookbim.*` = Rook
export-derived.

**minimal** (== Legacy's four):
```
rook.source, revit.uniqueId, revit.elementId, revit.category
```

**standard** (default) adds:
```
rookbim.exportId, rookbim.preset, rookbim.geometryRepresentation, rookbim.geometryQuality,
revit.family, revit.type, revit.name, revit.level
```

**full** adds relationship/context labels where available:
```
revit.hostId, revit.hostUniqueId, revit.containingRoomId, revit.containingRoomName,
revit.containingSpaceId, revit.containingSpaceName, revit.documentGuid, revit.workset
```
(Each stamped only when the underlying label is present with adequate confidence; otherwise omitted.)

Per-preset default profile: most presets `standard`; `calibration_fixture` `full`. `metadataProfile`
override always allowed (e.g. `minimal` for a lightweight geometry transfer).

---

## 8. Summary + relationships (prior answers; preset-path-only per §3.2)

Both are emitted **only** on the preset path and persisted in **both** the MCP response `Data` and
`validation.json` (so the bundle is self-describing offline).

### 8.1 `summary`
```jsonc
"summary": {
  "digest": "Exported 58 elements across 5 categories: 58 Breps, 0 meshes, 0 bbox proxies, 0 failed. 54 rooms included. 1 warning.",
  "preset": "architectural_shell",
  "effectiveCategories": ["Walls","Floors","Roofs","Ceilings","Columns"],
  "layerPolicy": "by_level_then_category",
  "namePolicy": "readable_with_id",
  "metadataProfile": "standard",
  "limitPerCategory": 1000,
  "resolvedCategories": [
    { "category": "Walls",  "resolved": 50, "exported": 50, "failed": 0, "status": "resolved" },
    { "category": "Floors", "resolved": 8,  "exported": 8,  "failed": 0, "status": "resolved" },
    { "category": "Curtain Panels", "resolved": 0, "exported": 0, "failed": 0, "status": "unavailable" }
  ],
  "geometryQuality": { "brep": 58, "mesh": 0, "bbox_proxy": 0, "failed": 0 },
  "rooms": { "total": 54, "room_volume_brep": 0, "room_mesh": 54, "boundary_2d": 0, "label_only": 0 },
  "layers": { "count": 12, "warnings": [] },
  "warnings": [
    { "code": "category_unavailable", "message": "Category 'Curtain Panels' was not present in the active view." }
  ]
}
```
The **structured fields are the contract**; `digest` is a short human/agent convenience (kept brief).
The output bundle name/paths are reported via the existing `BimExportResult.Paths`.

### 8.2 `relationships` (facts only)
A compact membership index so any consumer (humans, agents, Threshold Calibration v1, future
hosting/aperture work) can join membership without walking every element record:
```jsonc
"relationships": {
  "roomMembership":  [ { "elementUniqueId":"…", "roomId":"…", "roomUniqueId":"…", "roomName":"Office 101", "source":"revit_api", "confidence":"high" } ],
  "hostMembership":  [ { "elementUniqueId":"…", "hostElementId":"…", "hostUniqueId":"…", "source":"revit_api", "confidence":"high" } ],
  "levelMembership": [ { "elementUniqueId":"…", "levelId":"…", "levelName":"Level 02", "source":"revit_api", "confidence":"high" } ]
}
```
Built from the labels `RevitLabelExtractor` already extracts. **Facts only:** no inferred containment
positives/negatives, no precomputed calibration pairs, no "ground-truth containment" claims beyond
what Revit explicitly provides (each entry carries its `source`/`confidence`). The calibration
consumer decides how to use these facts.

---

## 9. Request contract & catalog

### 9.1 `BimExportPresetRequest`
```jsonc
{
  "preset": "architectural_shell",            // required; must be a known catalog key
  "output": { "directory": "<abs local dir>", "name": "shell", "units": "meters", "overwrite": false }, // reuse BimExportOutput + path policy
  "scope": "active_view|document",            // optional; default active_view
  "includeCategories": ["Generic Models"],    // optional; added after expansion
  "excludeCategories": ["Ceilings"],          // optional; removed after expansion (case-insensitive)
  "layerPolicy":     "by_level_then_category",// optional override of preset default
  "namePolicy":      "readable_with_id",       // optional override
  "metadataProfile": "standard",               // optional override
  "rooms":           "both|labels_only|exclude", // optional override
  "limitPerCategory": 1000,                   // optional; default per catalog/preset
  "allowTruncated":  false,
  "allowBboxProxy":  false
}
```
`Validate()`: preset is a known catalog key (else `UnknownPreset`); `Output` passes the existing
`BimExportPathPolicy.ValidateRequestShape` (absolute-local dir, sanitized name, supported units);
`scope` valid; any supplied policy override parses to its enum. Multi-category resolution + the
success condition (§4.1) happen in `RevitPresetResolver` (needs the live document), not in `Validate()`.

### 9.2 Catalog (review correction 5 — calibrated)
`BimPresetCatalog` (pure) maps preset → `{ categories[], defaultLayerScheme, defaultNameScheme,
defaultMetadataProfile, defaultRooms, defaultLimitPerCategory, roomsDriven }`. Category strings are
canonical Revit display names resolved per-document by the existing `RevitCategoryResolver`.

| Preset | Categories (canonical display names) | Layer | Name | Profile | Rooms | roomsDriven |
|--------|--------------------------------------|-------|------|---------|-------|-------------|
| `architectural_shell` | Walls, Floors, Roofs, Ceilings, Curtain Walls, Curtain Panels, Curtain Wall Mullions, Columns | by_level_then_category | readable_with_id | standard | both | false |
| `interiors` | Furniture, Furniture Systems, Casework, Specialty Equipment, Plumbing Fixtures, Lighting Fixtures, Generic Models | by_level_then_category | readable_with_id | standard | both | false |
| `openings_and_hosts` | Doors, Windows | by_level_then_category | readable_with_id | standard | both | false |
| `structural` | Structural Columns, Structural Framing, Structural Foundations | by_level_then_category | readable_with_id | standard | exclude | false |
| `rooms_and_spaces` | *(empty)* | RookBim::Rooms (fixed) | readable_with_id | standard | both | **true** |
| `calibration_fixture` | Walls, Floors, Roofs, Ceilings, Columns, Doors, Windows, Structural Columns, Structural Framing, Furniture, Casework | by_level_then_category | readable_with_id | **full** | both | false |

**Catalog notes (documented decisions, not silent choices):**
- **Structural slabs/floors:** Revit commonly represents structural slabs as the **Floors** category.
  `structural` therefore covers `Structural Columns/Framing/Foundations` only and **intentionally
  leaves slabs/floors to `architectural_shell`** (which includes Floors). A user who wants slabs with
  the structural set adds them via `includeCategories: ["Floors"]`. This avoids double-owning Floors
  across two presets and double-counting if both are exported into one bundle.
- **`calibration_fixture` breadth (correction 5):** deliberately broad — it includes **openings
  (Doors, Windows)** and **interiors (Furniture, Casework)** in addition to the shell + structure,
  because doors/windows (host + from/to-room) and furniture (room membership) are exactly the
  high-value labeled relationships calibration needs. It pairs that breadth with `metadataProfile:
  full` + `rooms: both` so the relationship index is maximally populated.
- Categories absent from a given model are warnings, not errors (§4) — the catalog is a superset of
  what any one model contains.
- **`limitPerCategory` default = `1000`** (the existing `BimQueryElementsRequest.HardMaxLimit`),
  applied independently to each category's query so a large category (e.g. Walls) is not starved by a
  shared global cap. Per-category truncation still honors `allowTruncated` exactly as v1 (§4): a
  truncated category with `allowTruncated == false` fails `QueryTruncated`. No preset sets a lower
  default in v1; callers tune via `limitPerCategory`.

---

## 10. Error model, registration & targeting

- **New `BimErrorCode`s:** `UnknownPreset`, `NoCategoriesResolved`. Reuse `OutputPathInvalid`,
  `QueryTruncated`, `NoExportableGeometry`, `ExportFailed`. Extend `BimHandler.MapErrorCode`
  (snake_case wire codes: `unknown_preset`, `no_categories_resolved`).
- **`BimHandler`:** add `export_preset` to `ExpectedBimOps`, a dispatch arm
  (`runtime.ExportPreset(Deserialize<BimExportPresetRequest>(body))`), `RouteForOp`
  (`POST /bim/export-preset`), and reason mapping for the new codes.
- **Native:** add the `POST /bim/export-preset` proxy route mirroring `/bim/export-elements`
  (forwards body to managed `BimHandler.Dispatch` with `op="export_preset"`).
- **MCP (`server.py`):** `rookbim_export_preset` tool — input schema (preset enum, output block,
  scope, include/exclude, policy overrides, limitPerCategory, allowTruncated/allowBboxProxy, port);
  dispatch → `call_rhino("/bim/export-preset", "POST", arguments, port=port)`. Add to the **`rookbim`**
  `TOOL_GROUPS` entry — **NOT** `rookbim_readonly`. Add to `_ALL_KNOWN_TOOLS`.
- **Targeting policy:** `requires_rhino=True`, `risk="mutate"` (filesystem artifact creation only;
  Revit + Rhino documents read-only). Same posture as `rookbim_export_elements`.

---

## 11. Testing

**Pure unit (`src/Rook.Tests/Bim/`, CI, no Revit):**
- `BimPresetCatalog`: every catalog key resolves; category lists non-empty except `rooms_and_spaces`;
  `rooms_and_spaces.roomsDriven == true`; per-preset default policies match §9.2.
- `BimExportOrganizationPolicy`: `Legacy` == {flat, none, minimal}; `Resolve(presetDefault, overrides)`
  honors overrides and falls back to preset defaults.
- `BimExportLayerNamer`: `flat`/`by_category`/`by_level_then_category` outputs; `_NoLevel`/`_Other`
  fallbacks; `RookBim::` root (assert **not** `RookBIM::`); sanitization.
- `BimExportObjectNamer`: each scheme; type→category→`Revit Element` fallbacks; id-suffix omission;
  no `UniqueId` in name; sanitization.
- `BimExportPresetRequest.Validate()`: `UnknownPreset`; output path reuse; scope/enum-override
  validation.

**Source-text (`src/RookBim.Tests/`, CI):**
- `RevitPresetResolver`: per-category loop over the existing `RevitQueryService`; dedup by
  `(documentGuid, uniqueId)`; missing-category warning path; `NoCategoriesResolved` only when all
  empty **and** not `roomsDriven`; `rooms_and_spaces` bypass.
- `RevitExportService`: policy-driven layer/name/metadata threading; **`relationships` index built**;
  **summary/relationships emitted only when `presetContext != null`**.
- Guards (extend existing invariants): **no Revit references outside `src/RookBim`** (the resolver +
  service stay in RookBim; core stays Revit-free); **no `Transaction`** anywhere in the new Revit
  files; **no hard `RhinoInside.Revit` reference**; geometry vocab unchanged (no `exact_brep`).

**Legacy parity (`src/Rook.Tests/`, the §3 seam):**
- The raw `rookbim_export_elements` path uses `Legacy` policy + null `presetContext`: flat layers,
  four user strings, **no object names**, **no `summary`/`relationships`** in sidecar/validation,
  unchanged counts/bijection. Asserted at the **observable/API level** (layer names, user-string
  keys, sidecar schema), **not** a file hash (§3.1).

**Registration (`src/Rook.Tests/` + `mcp_server/tests/`):**
- `BimHandler` registers `export_preset` (op set, dispatch arm, route, error mapping).
- Native route row present.
- MCP: tool + dispatch case + `rookbim` group membership (and **absence** from `rookbim_readonly`) +
  targeting policy (`requires_rhino`, mutate) + `_ALL_KNOWN_TOOLS`.

**Live verify (gated, real Revit + Rhino.Inside.Revit) — `live_verify_rookbim_export_preset.py`:**
- Export `architectural_shell` from the Snowdon Towers sample (active view).
- Assert: three files written; sidecar/validation parse; **hierarchical layers present** under
  `RookBim::` with `::`-separated level/category (and **no** `RookBIM::`); **object names** populated
  per `readable_with_id`; **standard-profile user strings** present on objects; **bijection holds**;
  counts reconcile; **`summary` digest + structured fields present**; **`relationships` index present
  in sidecar/validation**; Revit + Rhino remain stable.
- Domain richness (brep vs mesh counts, exact category membership) is reported, not hard-required.

---

## 12. Dependencies & sequencing (≈ tasks for writing-plans)

1. Core contracts + error codes + `BimExportPresetRequest.Validate()` (pure, unit-tested).
2. `BimPresetCatalog` (pure, unit-tested) — the §9.2 table.
3. `BimExportOrganizationPolicy` + `BimExportLayerNamer` + `BimExportObjectNamer` (pure, unit-tested).
4. `IRookBimRuntime.ExportPreset` + `RookBimUnavailableRuntime` impl.
5. `RevitPresetResolver` (multi-category union/dedup/freeze; warnings; success condition) — source-text.
6. `RevitExportService` generalization: organization policy threading (+ **Legacy parity test**) →
   relationships index → summary; preset-path-only emission gate.
7. `RevitRookBimRuntime.ExportPreset` wiring (dispatcher + export timeout).
8. `BimHandler` op + native `/bim/export-preset` route + MCP tool + tool group + targeting.
9. Registration tests + gated `live_verify_rookbim_export_preset.py`.

This slice depends only on the merged Export v1 surface (`RevitExportService`, `RevitQueryService`,
`RevitIdentitySerializer`, `RevitCategoryResolver`, `RevitLabelExtractor`, `RevitRoomExporter`,
`BimExportPathPolicy`, `BimExportBijection`) plus in-process RhinoCommon. It introduces **no** native
geometry-kernel work, **no** scene-graph coupling, and **no** Revit mutation.
