# Hunyuan 3D Pro (multi-view image-to-3D) — Design

**Date:** 2026-06-23
**Status:** Approved (brainstorm → spec)
**Base branch:** `main` (new feature branch off `main` before implementation)
**Author:** senior engineer (Claude); reviewer: Codex (senior reviewer)

---

## 1. Goal

Add **full** support for Fal's Hunyuan 3D Pro image-to-3D model:

```
fal-ai/hunyuan-3d/v3.1/pro/image-to-3d
docs: https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/pro/image-to-3d/api
```

End state — not a single-image catalog entry, but full Pro support:

- The reconstruction request contract carries **labeled view artifacts**.
- Each labeled image is published to Fal and submitted under the **correct named Fal slot field**.
- Wired to the existing Reconstruct / MV3D UI scaffold.
- User controls for **Generate Type** (Normal/Geometry), **Enable PBR**, **Face Count**.
- Texture expectation driven by **Generate Type**, not by `enable_pbr=false`.

Measured implementation slices are acceptable but must lead to the full end state (see §11).

### Known Fal Pro API facts

- Required input: `input_image_url`.
- Optional labeled multi-view inputs: `back_image_url`, `left_image_url`, `right_image_url`,
  `top_image_url`, `bottom_image_url`, `left_front_image_url`, `right_front_image_url`.
- Options: `generate_type` (enum `Normal`|`Geometry`), `enable_pbr` (bool, ignored when
  `generate_type=Geometry`), `face_count` (int, min 40000, max 1500000, default 500000).
- Output: `model_glb` (required), `thumbnail` (optional), `model_urls` (glb/fbx/obj/mtl/texture/usdz),
  `seed` (optional).

---

## 2. Current state (main) — what we build on

- **Contract/parser** (`ReconstructionSubmitRequestParser` / `ReconstructionSubmitRequest`):
  one `source_artifact_id` + `source_role` + free-form `options` JsonObject; `source_artifact_id`
  required.
- **Manager** (`ReconstructionJobManager.SubmitCoreAsync`): validates one source → publishes one
  image to the fal CDN → submits one URL under `model.Input.SourceField`. Submit gated by
  `IsSubmittableV1Model` (task `single_image_to_3d` + status `stable`).
  `DeriveTextureExpected` uses legacy `enable_geometry`/`enable_pbr` rules.
- **Provider** (`FalReconstructionProvider` / `ReconstructionProviderSubmitRequest`): one
  `InputImageUrl` + `SourceField`; `BuildSubmitPayload` writes that one field + forwards `options`
  verbatim. **Result mapper already** maps `glb/obj/mtl/fbx/usdz/stl/texture_*/thumbnail` roles.
- **Catalog** (`ReconstructionModelCatalog`): `ReconstructionInputMetadata` already has scaffolded,
  production-unused `view_slots` (`ReconstructionViewSlot(Role, Field, Required)`) and `array` shapes.
  No `options`-schema descriptor exists.
- **View-set abstraction** (`assemble_view_set` / `ReconstructionViewSetAssembler`): composes
  `[{slot, artifact_id, role, provenance}]` into one `reconstruction_view_set` artifact with `view_*`
  role'd blobs + `parent_ids` + a `complete` flag. Slot vocabulary
  (`ReconstructionViewSlots.Allowed`): `front, left, right, back, top, three_quarter`.
- **UI scaffold** (`src/Rook/UI/Vision/Resources/{index.html,app.js,styles.css}`): Reconstruct view
  with three modes T3D / I3D / MV3D. MV3D renders slots (`front` pane + `left/right/back/top/
  three_quarter`); its action is stubbed to "Assemble view set" ("Slot assembly wires next").

### The slot-vocabulary tension (resolved in this design)

| Source | Slots |
|---|---|
| `ReconstructionViewSlots.Allowed` (+ UI MV3D) | front, left, right, back, top, **three_quarter** |
| Fal Pro named inputs | front(`input_image_url`), back, left, right, top, **bottom**, **left_front**, **right_front** |

We **align to Fal Pro's real slots** and make the slot→Fal-field mapping **catalog-driven** per model
(`input.view_slots`). `three_quarter` is kept in the generic view-set/assembly vocabulary for
back-compat but has **no Pro mapping**, so it cannot be submitted to Pro.

---

## 3. Decisions (from brainstorming)

1. **View carrier:** inline labeled `views[]` in the submit request. `assemble_view_set` stays an
   optional preview/provenance/save helper — **not** required for submit.
2. **Front source:** `source_artifact_id` is the **only canonical front**. `views[]` carries optional
   *secondary* labeled views. A `front` entry in `views[]` is accepted **only if its `artifact_id`
   matches `source_artifact_id`**, otherwise rejected as a front conflict. `views.front` never
   overrides `source_artifact_id`.
3. **Capability via metadata, not task:** one Pro catalog entry; multi-view capability expressed by
   `input.view_slots`. Pro appears in **both** I3D (front-only) and MV3D (labeled views). Catalog
   metadata (not `task`) is the authority for mode availability and gating.
4. **Options schema:** a **bounded, structured catalog `options` block** consumed by both a shared C#
   validator and the UI. Not hardcoded; not a generic forms engine.

---

## 4. Request contract & parser

### Types
```csharp
public sealed record ReconstructionViewRequest(string Slot, Guid ArtifactId, string Role);

// ReconstructionSubmitRequest gains:
//   IReadOnlyList<ReconstructionViewRequest> Views   // default: empty
```

### Parser (`ReconstructionSubmitRequestParser.Parse`)
- Parse optional `views: [{ "slot": string (req), "artifact_id": guid (req), "role"?: string }]`.
  Structural checks only (mirrors `ReconstructionViewSetRequest.TryParse`'s careful per-field style:
  typed reads, GUID parse, clear `invalid_request` failures). `role` defaults to `"image"`.
- Missing / absent `views` → empty list (single-image path, unchanged).
- `source_artifact_id` remains **required** (canonical front).
- Front-conflict rule lives in the **manager** (it owns the store + GUID comparison); the parser only
  guarantees structural validity.

### Effective slot→artifact resolution (manager)
1. Seed `{ front: (source_artifact_id, source_role) }`.
2. Apply `views[]`:
   - `slot == "front"`: allowed **iff** `artifact_id == source_artifact_id` (role may differ; the
     explicit role wins for front). Mismatch → `invalid_request` / `conflicting_front`.
   - duplicate non-front slot within `views[]` → `invalid_request` / `duplicate_slot`.
3. Result = the labeled set to validate, publish, and submit.

---

## 5. Catalog metadata (catalog-driven)

### New types (`ReconstructionModelCatalog.cs`)
```csharp
public sealed record ReconstructionOptionDescriptor(
    string Key, string Label, string Kind,            // kind ∈ { "enum", "boolean", "integer" }
    JsonNode? Default,
    string[]? AllowedValues,                            // enum
    long? Min, long? Max, long? Step,                  // integer (step = UI hint)
    ReconstructionOptionIgnoredWhen? IgnoredWhen);

public sealed record ReconstructionOptionIgnoredWhen(string Key, string Equals);

// ReconstructionModelEntry gains:
//   ReconstructionOptionDescriptor[]? Options   // nullable/additive — old JSON still deserializes
```
`input.mode` gains the value `"multi_view_labeled"`. The existing
`ReconstructionViewSlot(Role, Field, Required)` is reused as-is (`Role` = slot name, `Field` = Fal
field).

### New Pro entry (`fal-model-catalog.json`)
```jsonc
{
  "model_id": "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
  "provider": "fal",
  "task": "single_image_to_3d",            // kept; capability lives in metadata, NOT task
  "status": "experimental",                 // flips to "stable" in slice 4 (after live gate)
  "enabled": true,
  "pipeline_roles": ["single_image_to_3d"],
  "input_types": ["image_url"],
  "output_roles": ["model_glb", "model_obj", "material_mtl",
                   "model_fbx", "model_usdz", "texture", "thumbnail"],
  "preferred_asset_role": "model_glb",
  "fallback_order": ["model_glb", "model_obj"],
  "supports_pbr": true,
  "default_texture_expected": true,
  "input": {
    "mode": "multi_view_labeled",
    "source_field": "input_image_url",
    "view_slots": [
      { "role": "front",       "field": "input_image_url",       "required": true  },
      { "role": "back",        "field": "back_image_url",        "required": false },
      { "role": "left",        "field": "left_image_url",        "required": false },
      { "role": "right",       "field": "right_image_url",       "required": false },
      { "role": "top",         "field": "top_image_url",         "required": false },
      { "role": "bottom",      "field": "bottom_image_url",      "required": false },
      { "role": "left_front",  "field": "left_front_image_url",  "required": false },
      { "role": "right_front", "field": "right_front_image_url", "required": false }
    ]
  },
  "prompt": { "supported": false, "required": false, "kind": null },
  "preprocessing": { "recommended": false, "required": false },
  "options": [
    { "key": "generate_type", "label": "Generate Type", "kind": "enum",
      "default": "Normal", "allowed_values": ["Normal", "Geometry"] },
    { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean",
      "default": false, "ignored_when": { "key": "generate_type", "equals": "Geometry" } },
    { "key": "face_count", "label": "Face Count", "kind": "integer",
      "default": 500000, "min": 40000, "max": 1500000, "step": 10000 }
  ],
  "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/pro/image-to-3d/api"
}
```

### Output-role note (`model_fbx` / `model_usdz`)
These are **supplemental** package output roles. The result mapper already emits the string roles
`model_fbx` / `model_usdz`; this design adds matching `ReconstructionFileRoles` constants
(`ModelFbx = "model_fbx"`, `ModelUsdz = "model_usdz"`) for clarity, but they remain **supplemental
only**. `model_glb` then `model_obj` stay the only import-preferred / fallback model assets
(`preferred_asset_role` / `fallback_order` unchanged). No broader import support is added here.

---

## 6. Models endpoint

`ReconstructionOpHandler.ModelToObj` serializes:
- the new `options` block (`OptionToObj`), and
- derived capability flags: `supports_single_image` (a single `input.source_field` exists) and
  `supports_multi_view` (`input.view_slots` count > 1).

`InputToObj` already emits `mode` + `view_slots`. The UI uses **these flags** (not `task`) for mode
availability.

### Picker filter — capability, not task
`ThreeDProducingTasks` (task-based) is replaced by a **capability** predicate: a model is a 3D
producer for the picker iff `output_roles` intersects `{ model_glb, model_obj }`. This keeps existing
behavior (birefnet excluded — no `model_*` role; hunyuan/meshy included) while removing task as the
hidden authority. Mode sub-filtering: I3D shows `supports_single_image`; MV3D shows
`supports_multi_view`.

---

## 7. Provider payload mapping

```csharp
// ReconstructionProviderSubmitRequest: replace InputImageUrl + SourceField with
public IReadOnlyList<ReconstructionProviderViewUrl> ViewUrls   // ordered (field, url), front first
public sealed record ReconstructionProviderViewUrl(string Field, Uri Url);
```
- The **manager** resolves slot→Fal field via `model.Input.view_slots` and produces the ordered
  `ViewUrls` list (front first). The provider stays catalog-agnostic.
- Single-image submit = a one-entry list `{ input_image_url: url }`.
- `BuildSubmitPayload` writes each `field → url`, then forwards the validated, **default-filled**
  options (with ignored options omitted — see §8).

---

## 8. Manager: gating, validation, publish, texture/PBR

### Generalized 3D submit gating (capability-driven, not task)
`IsSubmittable3DModel(model)` ⇔ all of:
- `Enabled == true`
- `Status == "stable"` (Pro qualifies after the slice-4 flip)
- has an **importable 3D output role**: `output_roles` contains `model_glb` or `model_obj`
- accepts input: `supports_single_image` **or** declares labeled `view_slots`

No `task` check. (The legacy `IsSubmittableV1Model` is replaced by this predicate.)

### Multi-view validation (against `model.Input.view_slots`)
- Resolve the effective slot→artifact map (§4). Front always present (via `source_artifact_id`).
- Every submitted slot must exist in the model's `view_slots`, else `invalid_request` /
  `unsupported_slot` (field `views`). A model with no `view_slots` (or a single slot) rejects any
  extra views.
- Revalidate each source per-slot with the existing `ReconstructionSourceValidator` (kind / role /
  ext / size / dimensions); failures annotated with the offending slot.

### Publish
Loop the resolved map: read bytes (manager owns the store) → publish each to the fal CDN via
`IReconstructionSourceImagePublisher` → assemble the ordered `ViewUrls` (front first).

### Options validator (`ReconstructionOptionsValidator`, shared by manager + surfaced for UI)
For a catalog-described model (has an `options` block):
- For each present option: validate against its descriptor — `enum` value ∈ `allowed_values`;
  `integer` ∈ `[min, max]` (`step` is a **UI hint**, not a hard backend reject); `boolean` is a bool.
- **Fill defaults** for absent options before submit (Fal sees explicit, predictable values).
- **Unknown option key → reject** `invalid_request` / `unknown_option`. (Models **without** an
  `options` block keep today's verbatim pass-through, so **Rapid is unchanged**.)
- `ignored_when` satisfied (`generate_type == "Geometry"` ⇒ `enable_pbr` ignored) → **omit**
  `enable_pbr` from the submit payload.

### Texture-expectation rework (`DeriveTextureExpected`)
- If the (default-filled) options contain `generate_type`:
  - `Geometry` ⇒ `false` (geometry-only, no texture expected)
  - `Normal` ⇒ `true` (**regardless of `enable_pbr`** — so `enable_pbr=false` still expects texture;
    this is the Pro fix the brief calls for)
- Else (no `generate_type`, i.e. legacy models like Rapid) ⇒ legacy rules:
  `enable_geometry=true ⇒ false`; `enable_pbr=true ⇒ true`; `enable_pbr=false ⇒ false`; else
  `model.DefaultTextureExpected`. **Rapid behavior is unchanged.**

The legacy `enable_pbr && enable_geometry` combo guard and `enable_pbr && !SupportsPbr` guard remain
for legacy (verbatim-options) models; for Pro they are subsumed by the validator + `ignored_when`
(and `supports_pbr=true` makes the latter moot).

---

## 9. Materializer & provenance

`ReconstructionPackageMaterializer.MaterializeAsync` already accepts an array of source artifact ids.
Pass **all** view source artifact ids (front + filled slots) so the package's `parent_ids` capture
full multi-view provenance. The ledger record keeps a single `SourceArtifactId` = front for display
(**no ledger schema change**); full provenance lives in the package `parent_ids`.

---

## 10. UI integration

- **I3D mode:** Pro joins the picker (`supports_single_image`). The three option controls render
  **from catalog `options` metadata** when the selected model exposes them (Rapid has none → no
  controls). Submit shape unchanged (front `source_artifact_id` + `options`).
- **MV3D mode:** picker filters to `supports_multi_view` (Pro). Slots render **from the selected
  model's `view_slots`** (catalog-driven) → Pro's 8 slots: `front` (large pane) + 7 optional
  secondary slots. The current `three_quarter` slot is replaced by `bottom` / `left_front` /
  `right_front` to match Fal. The MV3D action changes from the `assemble view set` stub to a real
  **submit** (build `views[]` from filled slots, with front from the front pane, plus options).
  `assemble_view_set` remains an optional save/preview helper, not on the submit path.
- **Option control behavior:** `enable_pbr` disabled/hidden when `generate_type == Geometry`;
  `face_count` integer input with min/max/step (client-side clamp, **backend authoritative**).
- **Generic vocabulary expansion:** `ReconstructionViewSlots.Allowed` and `ReconstructionFileRoles`
  add `bottom` / `left_front` / `right_front` (so `assemble_view_set` accepts them);
  `view_bottom` / `view_left_front` / `view_right_front` file-role constants added. `three_quarter`
  kept for back-compat (no Pro mapping).

### Experimental-visibility during slices 1–3
Pro ships `experimental` until slice 4, so the default `models` call (which omits experimental) won't
surface it. Concretely:
- **Backend/unit tests** use a **synthetic stable** Pro catalog entry, so backend behavior is fully
  covered before the production status flip.
- **Scaffold source tests** are structural (HTML/JS assertions) and do not depend on catalog status.
- **Manual dev verification** during slices 1–3 surfaces Pro by calling the models op with
  `include_experimental=true` (already supported). Slice 4 flips Pro to `stable` so the default
  (non-experimental) UI shows it.

---

## 11. Slice plan (each shippable, green, leading to full Pro)

1. **Backend machinery + catalog (experimental).** Catalog option/view-slot types + deserialization;
   Pro entry (`experimental`); models endpoint exposes `view_slots` / `options` / capability flags +
   capability-based picker filter; parser `views[]`; provider multi-field payload; manager
   capability gating + multi-view resolution (incl. front-conflict rule) + options validator +
   texture/PBR rework. Full unit coverage via a synthetic **stable** Pro catalog in tests. Not
   prod-submittable yet (experimental).
2. **UI I3D options.** Pro in the I3D picker; option controls rendered from catalog metadata;
   `enable_pbr`/`generate_type` gating; scaffold source tests.
3. **UI MV3D submit.** Catalog-driven slots (Pro's 8); MV3D action submits `views[]`;
   `assemble_view_set` demoted to optional helper; scaffold source tests.
4. **Flip to stable + live gate.** Pro `status` → `stable`. Merge gate = a **live 2D→3D Pro
   roundtrip** (single image **and** multi-view) on the deployed Release build — mirrors the
   reconstruction lineage's live-gate practice.

---

## 12. Validation / error behavior (explicit)

| Case | Result |
|---|---|
| Missing `source_artifact_id` | `invalid_request` (parser; field `source_artifact_id`) |
| `views.front` artifact ≠ `source_artifact_id` | `invalid_request` / `conflicting_front` |
| Slot not in model's `view_slots` | `invalid_request` / `unsupported_slot` (field `views`) |
| Duplicate non-front slot in `views[]` | `invalid_request` / `duplicate_slot` |
| Invalid `generate_type` (not Normal/Geometry) | `invalid_request` (field `options.generate_type`) |
| `face_count` out of `[40000, 1500000]` / non-int | `invalid_request` (field `options.face_count`) |
| Unknown option key (catalog-described model) | `invalid_request` / `unknown_option` |
| `enable_pbr` under `generate_type=Geometry` | **not an error** — omitted from payload; texture expectation = geometry-only |
| Per-view source invalid (kind/role/ext/size/dims) | reuse `ReconstructionSourceValidator` failure, annotated with the slot |

---

## 13. Test strategy

Per-layer unit tests (all in `src/Rook.Tests/Services/Reconstruction/...` and
`.../Handlers` / `.../UI/Vision`):
- **Catalog:** deserialize `options` (enum/boolean/integer, `ignored_when`, defaults) and
  `view_slots`; old JSON without `options` still deserializes.
- **Parser:** `views[]` shapes + structural rejects; absent `views` → empty.
- **Options validator:** enum / range / unknown / `ignored_when` / default-fill.
- **Manager:** effective-map resolution, front overlay + `conflicting_front`, `unsupported_slot`,
  per-slot source validation, texture/PBR matrix (esp. `Normal + enable_pbr=false ⇒ textured`,
  `Geometry ⇒ geometry-only`), capability gating.
- **Provider:** `BuildSubmitPayload` writes all slot fields (front first) + omits ignored option +
  forwards default-filled options.
- **Handler:** models endpoint exposes `options` / `view_slots` / capability flags; capability-based
  picker filter (birefnet excluded, hunyuan/pro included); submit success/failure envelopes.
- **Scaffold source tests:** Pro slots (`bottom`/`left_front`/`right_front`), option controls present
  + `generate_type` gating of `enable_pbr`, MV3D submit action.
- **Live roundtrip gate** in slice 4 (single + multi-view) on the deployed Release build.

New feature branch off `main` before implementation. No native `vcxproj`/`vcxproj.filters` changes.
No new external dependencies. Managed companion owns the UI resources under
`src/Rook/UI/Vision/Resources`.
