# Meshy v6 Single-Image — Production-Ready Design (Step 1)

**Date:** 2026-06-24
**Status:** Approved (design); pending spec review
**Scope owner:** reconstruction subsystem (`src/Rook/Services/Reconstruction/`)

## Context

The reconstruction (image→3D) subsystem ships fal.ai models through a curated
catalog. `fal-ai/meshy/v6/image-to-3d` already exists as a catalog entry but is
**not production-ready**: it is unsubmittable and its metadata is wrong/incomplete.

Two independent blockers, both confirmed against the code:

1. **Wrong input field.** The catalog entry sets `input.source_field` to
   `input_image_url` (`fal-model-catalog.json:85`), but fal's live Meshy v6
   schema names the field **`image_url`**
   (https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api). Our own birefnet
   entry already uses `image_url` (`fal-model-catalog.json:112`), so this is an
   inconsistency, not a convention.
2. **Submit gate rejects experimental.** `IsSubmittable3DModel`
   (`ReconstructionJobManager.cs:722`) hard-requires `status == "stable"`. Meshy is
   `status: "experimental"` (`fal-model-catalog.json:75`), so it cannot be
   submitted at all — regardless of the field fix. This is a *functional* gate, not
   a visibility one.

This is the first step in a longer roadmap (image_url → image_url[] → model_url).
**Non-goals for this step:** Meshy multi-image (`image_urls[]`), any mesh-input /
3D→3D or retexture pipeline, and promotion to `stable`. Meshy remains
`experimental` at the end of Step 1; promotion is a later catalog-only follow-up,
gated on the documented live-smoke artifact produced here.

## Goal

Make `fal-ai/meshy/v6/image-to-3d` reliably submittable and importable through the
**full Rook pipeline** (submit → poll → materialize → import-prep → native import →
warnings), behind a narrow submit-time experimental override, with the texture-
expectation and warning logic telling the truth for Meshy's option set.

## Sequence (single spec, internal order)

gate → Meshy metadata/options + validator extensions → texture-expectation wiring →
deterministic tests → one full live smoke. The gate is **not** split into a separate
prerequisite PR: it has exactly one immediate consumer (Meshy), Meshy has exactly one
unblocker (the gate), they share a single live-smoke proof, and separating them
yields two weaker, individually-unverifiable PRs.

---

## §1 — Submit-time experimental override (the gate)

A test/dev override on the **submit path only**. It is **not** a catalog-visibility
policy and **not** a model-resolution policy.

### Invariants
1. `models` op stays **stable-only by default**; `include_experimental=true` lists
   Meshy for dev tooling (existing behavior, unchanged).
2. `IsSubmittable3DModel` (`ReconstructionJobManager.cs:722`) gains an
   `allowExperimental` parameter, **default `false`**. The flag relaxes **only** the
   `status == "stable"` clause; the importable-output-role clause
   (`model_glb`/`model_obj`) and the accepts-input clause (`source_field` or
   `view_slots`) still apply.
3. Submit accepts an experimental model **only** when **both** conditions hold:
   an explicit `model_id` is supplied **and** `allow_experimental_model: true`.
4. **No default/fallback model resolution may ever select an experimental model
   because of this flag.** The flag is inert unless an explicit `model_id` names the
   experimental model. Default resolution remains stable-only.
5. Background-removal submit (`IsSubmittableRemoveBackgroundModel`,
   `ReconstructionJobManager.cs:792`) is untouched — it already ships experimental and
   has its own gate.

### Layers touched (parser-backed — not just the predicate)
- **MCP tool schema** — `rhino_2d_to_3d_submit` (`mcp_server/src/rook/server.py`)
  gains an optional `allow_experimental_model: boolean` property (default false).
- **Request type** — `ReconstructionSubmitRequest` gains an
  `AllowExperimentalModel` field.
- **Parser** — `ReconstructionSubmitRequestParser.cs` parses the flag
  (default false; strict JSON bool).
- **Handler** — `ReconstructionOpHandler` submit op parses/forwards the flag into
  `JobManager.SubmitAsync`, which passes `allowExperimental` to the gate.
- **Predicate** — `IsSubmittable3DModel(model, allowExperimental)`.

### Implementation choice
Thread `allowExperimental` as a bool parameter into the **existing** predicate
(recommended — one gate, one decision site) rather than adding a parallel predicate.

---

## §2 — Meshy v6 catalog metadata + options

Edit the Meshy entry in `fal-model-catalog.json` (`:71`):

- `input.source_field`: `input_image_url` → **`image_url`**.
- `output_roles`: expand to advertise deliverable assets —
  `["model_glb", "model_obj", "model_fbx", "model_usdz", "texture", "thumbnail"]`.
  (Advertised vocabulary only; `BuildTextureWarnings` already treats `output_roles`
  as non-guarantee — `ReconstructionJobManager.cs:850`.)
- `default_texture_expected: true` (Meshy textures by default).
- `status` stays `experimental`; `enabled` stays `true`.

### Options (validated by `ReconstructionOptionsValidator`)
Final Step 1 option set:

| key | kind | default | constraint |
|-----|------|---------|------------|
| `topology` | enum | `triangle` | `quad`, `triangle` |
| `target_polycount` | integer | `30000` | min 100 (sanity), no hard max from fal docs |
| `symmetry_mode` | enum | `auto` | `off`, `auto`, `on` |
| `should_remesh` | boolean | `true` | — |
| `should_texture` | boolean | `true` | — |
| `enable_pbr` | boolean | `false` | omitted when `should_texture:false` (see §2b) |
| `texture_prompt` | **string** | (none) | omitted when `should_texture:false` (see §2b) |

**Deferred / out of scope:**
- `texture_image_url` — passing an arbitrary URL is a different trust/input path from
  artifact-uploaded source images, with no source-artifact/UI story yet. Defer until
  that story exists. (`texture_prompt` is the safe text-only guidance path and stays.)
- `model_type`, rigging/animation fields (`enable_rigging`, `enable_animation`, etc.)
  — out of scope for "image → clean textured mesh" (YAGNI).

### §2a — Add a validated `string` option kind
`ReconstructionOptionsValidator.ValidateValue` (`:70`) currently switches on
`enum`/`boolean`/`integer` only (`:74,80,84`); any other kind falls through and
**silently passes**. Because `texture_prompt` is a `string` option, Step 1 must:

- Add `case "string"`: accept a JSON string value; reject non-string.
  (No length/charset constraint required for Step 1.)
- Add a `default:` arm that **rejects genuinely unknown kinds** (defensive — closes
  the silent-pass hole). Only `enum`/`boolean`/`integer`/`string` exist today, so this
  is non-breaking.
- Tests: valid string accepted; non-string rejected; unknown-kind descriptor rejected.

> Decision dependency: `texture_prompt` is in Step 1 **only because** §2a adds
> validated string options. If §2a were dropped, `texture_prompt` would defer too.

### §2b — Boolean-gate `ignored_when` (omit dependent options)
When `should_texture:false`, the provider payload should **omit** `enable_pbr` and
`texture_prompt` (texturing is off, so PBR/prompt are meaningless). The validator
already "omits options whose `ignored_when` condition is satisfied"
(`ReconstructionOptionsValidator.cs:16`), but the gate comparison is **string-equality
only** (`:58-61`). Step 1 must:

- Extend `ignored_when` evaluation to support a **boolean** gate value, so
  `enable_pbr` and `texture_prompt` can declare
  `"ignored_when": { "key": "should_texture", "equals": false }`.
- Generalize the gate comparison to match the gate node's JSON value by type
  (string **or** bool) against the descriptor's `equals` value. Hunyuan's existing
  string gate (`generate_type == "Geometry"`, `fal-model-catalog.json:65`) must keep
  working unchanged.
- Tests: bool gate true (option omitted) and false (option kept); string gate
  regression (Hunyuan `generate_type:Geometry` still omits `enable_pbr`).

---

## §3 — Texture-expectation wiring (family-aware `DeriveTextureExpected`)

`DeriveTextureExpected` (`ReconstructionJobManager.cs:831`) computes the
`TextureExpected` ledger value (`ReconstructionJobLedger.cs:44`) that drives the
`result_missing_texture` warning (`BuildTextureWarnings`, called at `:517`). Its
current precedence is:

```
generate_type (Normal⇒true / Geometry⇒false)
  → enable_geometry==true ⇒ false
  → enable_pbr==true ⇒ true ; enable_pbr==false ⇒ false
  → default_texture_expected
```

### The collision
Meshy carries **both** `should_texture` and `enable_pbr`, but for Meshy `enable_pbr`
does **not** control whether texturing happens — `should_texture` does (PBR only
changes *which* maps). Under the current cascade:
- `{should_texture:false, enable_pbr:true}` would hit `enable_pbr==true ⇒ true` →
  wrongly expects a texture → false `result_missing_texture`.
- `{enable_pbr:false}` with `should_texture` left at its default `true` would hit
  `enable_pbr==false ⇒ false` → wrongly expects no texture, suppressing a real
  warning.

### Decision: family-aware derivation
Once a model **declares `should_texture` as a catalog option**, that option owns
texture expectation and the legacy `enable_pbr`/`enable_geometry` rules are **not
consulted for that model**:

```
if model declares generate_type option (Hunyuan Pro):
    Normal ⇒ true ; Geometry ⇒ false        (unchanged)
elif model declares should_texture option (Meshy):
    should_texture present ⇒ its bool value
    should_texture absent  ⇒ default_texture_expected
else (legacy):
    enable_geometry==true ⇒ false
    enable_pbr==true ⇒ true ; ==false ⇒ false
    default_texture_expected
```

This honors the precedence rule exactly: `should_texture:false ⇒ false`,
`should_texture:true ⇒ true`, absent ⇒ `default_texture_expected`; and `enable_pbr`
never implies texture presence for Meshy.

`DeriveTextureExpected` must read the **effective (validated, default-filled)**
options so `should_texture` (default-filled to `true`) is always present at the read
site (`ReconstructionJobManager.cs:232`).

**Regression guard:** Hunyuan Rapid (no options) and Hunyuan Pro
(`generate_type` Normal/Geometry; `enable_pbr` true/false) keep their exact current
expectation outcomes, pinned by tests.

---

## §4 — Result classification coverage

`FalReconstructionResultMapper` already classifies model assets by extension
(`.glb/.obj/.fbx/.usdz`) and textures by filename via `ClassifyTextureRole` — the same
path the materials-import fix hardened. Meshy's `model_urls` and `texture_urls` flow
through this existing code, so Step 1 adds **test coverage** for Meshy's payload
shape, not new mapper logic — **unless** a concrete shape gap surfaces.

**Mapper shape (established by tests now, confirmed live):** fal Meshy v6 returns
`model_urls` as a structured object (glb/obj/fbx/usdz) and `texture_urls` as an array
of texture-file objects. The deterministic tests in §5 assert the mapper walks this
documented shape — that is where shape compatibility is **established**. If those tests
reveal the current extraction does not walk it, mapper work is added in Step 1. The
live smoke does not discover the shape; it only confirms fal's real response matches
the documented shape the tests already cover.

---

## §5 — Verification split

### Deterministic tests (no fal calls)
- **Gate matrix:** experimental rejected by default; experimental submittable only
  with explicit `model_id` **and** `allow_experimental_model:true`; stable models
  unaffected; default `models` listing stays stable-only unless `include_experimental`.
- **String option (§2a):** valid string accepted; non-string rejected; unknown-kind
  descriptor rejected.
- **Boolean-gate `ignored_when` (§2b):** `should_texture:false` omits
  `enable_pbr`+`texture_prompt`; `should_texture:true` keeps them; Hunyuan string-gate
  regression intact.
- **Texture-expectation (§3):** Meshy `should_texture` true/false/absent → expected
  true/false/`default_texture_expected`; `enable_pbr` does not flip Meshy expectation;
  Hunyuan Rapid/Pro outcomes unchanged.
- **Classification + warnings:** `texture_urls` classified into
  base_color/normal/roughness/metallic; texture-expected-but-absent ⇒
  `result_missing_texture`; `should_texture:false` ⇒ **no** warning; MTL referencing
  undelivered maps ⇒ `material_maps_missing`.

### One paid live smoke
A single real **textured** Meshy v6 job driven through full Rook import, asserted
against the §6 checklist.

---

## §6 — Live-smoke acceptance checklist (the documented artifact)

1. Job reaches `completed`.
2. Package materializes; the **preferred importable asset** is present (not "glb AND
   obj" — fal guarantees only `model_glb` + `model_urls`); any delivered
   `model_urls`/`texture_urls` are classified correctly.
3. `resolved_import_role` (import-prep) **equals** the role native import actually
   consumes (parity invariant; the same authority pinned by the materials-fix tests).
4. Rhino import succeeds: document object count `0 → N`, non-degenerate bbox.
5. Texture is present on the imported mesh, and **no false warnings** fire.

This checklist, with recorded results, is the artifact that gates the eventual
`experimental → stable` promotion (a later catalog-only follow-up).

---

## Files in scope

| Concern | File |
|---------|------|
| Catalog entry, options, `ignored_when` declarations | `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` |
| Submit gate predicate | `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`IsSubmittable3DModel`, `DeriveTextureExpected`) |
| String kind + boolean-gate `ignored_when` | `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs` |
| Submit request type + flag parsing | `src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs` (+ request type) |
| Handler submit serialization | `src/Rook/Handlers/ReconstructionOpHandler.cs` |
| MCP submit tool schema | `mcp_server/src/rook/server.py` (`rhino_2d_to_3d_submit`) |
| Result classification coverage | `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs` (tests; code only if shape gap) |
| Tests | `src/Rook.Tests/...` reconstruction suites; MCP tool tests |

## Risks / open items
- **Mapper shape gap (§4):** the deterministic tests establish compatibility against
  fal's documented shape; budget for small mapper work in Step 1 if the current
  extraction doesn't already walk `model_urls`/`texture_urls`. The live smoke only
  confirms docs match reality.
- **`target_polycount` bounds:** fal docs give a default (30000) but no explicit
  min/max; use a sanity floor and leave the ceiling unbounded rather than guessing.
- **Live smoke is paid:** one job; the deterministic suite must carry all
  matrix/branch coverage so the paid call only proves the integrated happy path.
