# Reconstruction OBJ/MTL Texture Integrity & Truthful Degradation — Design Spec

**Date:** 2026-06-23
**Status:** Approved for planning
**Base:** `origin/main` @ `c560ee88`
**Worktree:** `.worktrees/reconstruction-texture-integrity` on `feature/reconstruction-texture-integrity`

---

## 1. Purpose / root cause

A reconstruction job (`hunyuan-3d/v3.1/rapid`) imported as a **white/untextured** mesh. Forensics on the live package `96a7179f-c812-4880-ae1c-5d982a3e1e21` (data root `%APPDATA%\Rook\artifacts\…`) pinned the cause precisely. This is **not** a UI, OPEN, or deploy issue, and it is **not** a regression introduced by any recent slice — it is a latent defect in the managed result-mapping + import-prep + degraded-detection path, exposed by an incomplete provider payload.

### The literal provider payload (`provider_result_json`)
```jsonc
{
  "model_glb":   { "url": "…95befe79…obj", "content_type": "model/obj", "file_name": "95befe79….obj" }, // an OBJ, not a GLB
  "material_mtl":{ "url": "…material.mtl", "content_type": "text/plain", "file_name": "material.mtl" },
  "texture":     { "url": "…texture_pbr_v128_metallic.png", "content_type": "image/png",
                   "file_name": "texture_pbr_v128_metallic.png" },                                      // the METALLIC map
  "thumbnail":   { "url": "…preview.png", "file_name": "preview.png" },
  "model_urls":  { "glb": null, "fbx": null, "obj": { …obj… }, "mtl": { …mtl… },
                   "texture": { …same metallic… }, "usdz": null }
}
```

### The MTL (`material_mtl`) references four maps; the payload ships one
```
newmtl Material
map_Kd   texture_pbr_v128.png            # base color (diffuse) — THE white-maker — ABSENT
map_Pm   texture_pbr_v128_metallic.png   # metallic  — present (this is the only texture fal returned)
map_Pr   texture_pbr_v128_roughness.png  # roughness — ABSENT
map_Bump texture_pbr_v128_normal.png     # normal    — ABSENT
```

### Three coordinated defects
1. **Texture misclassification (mapper).** [`FalReconstructionResultMapper.cs:65-66`](../../../src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs) maps the provider's top-level `texture` to the **generic** `ReconstructionFileRoles.Texture` *without* running the existing [`ClassifyTextureRole`](../../../src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs) (line 217), which already maps filenames → `texture_metallic` / `texture_roughness` / `texture_normal` / `texture_base_color`. So the **metallic** map masquerades as "the texture," hiding the fact that there is no base color. Detailed classification only runs in the `texture_urls` loop, which this payload lacks.
2. **No texture-integrity check anywhere.** The pipeline never compares the MTL's `map_*` references against the files the package actually contains. The OBJ import-prep does the right structural thing — [`ReconstructionOpHandler.cs:632-639`](../../../src/Rook/Handlers/ReconstructionOpHandler.cs) already stages **every** `texture*`-role file present (its comment notes the static manifest binds only generic `texture`, so it stages detailed roles dynamically) — but it stages only what exists. The MTL's `map_Kd texture_pbr_v128.png` has no file in the package, so the staged bundle is `OBJ + MTL + texture_pbr_v128_metallic.png` and Rhino renders white. Nothing flags that the bundle is incomplete.
3. **False "healthy" (warning suppression).** [`ReconstructionJobManager.BuildTextureWarnings`](../../../src/Rook/Services/Reconstruction/ReconstructionJobManager.cs) returns "no warning" when **either** `material_mtl` **or** any `texture*` role is delivered (lines 736-740 — its own comment: *"material_mtl alone counts as not-degraded"*). For this package both are present, so **no warning** fires even though the MTL points at maps absent from the package. The result is reported clean while importing white.

**Conclusion (proven, not assumed):** for this generation the diffuse/roughness/normal maps are **genuinely absent from fal's output** (`model_urls.glb=null`, `model_glb` is an OBJ, no `texture_urls`, only the metallic URL). There is no recoverable texture and no GLB fallback. The model *cannot* be made textured — so the fix is **truthful degradation**, plus recovering classification/staging for the cases where data *is* present.

---

## 2. Scope (B — recover-where-possible + degrade-honestly)

Two required managed changes (Parts 1 and 3/4) plus one optional cleanup (Part 2); **no native, no UI, no provider re-request, no new API field**:

### Part 1 — Classify texture roles by filename (mapper)
Wire the **top-level `texture`** and any **`model_urls.texture`** through the existing `ClassifyTextureRole(fileName, url)`, exactly as the `texture_urls` loop already does. Result for this package: the metallic lands as `texture_metallic` (not generic `texture`), so the package honestly shows it has `texture_metallic` and **no `texture_base_color`**. Recovers any future payload that *does* ship detailed maps in `texture`/`model_urls`.

### Part 2 — Static manifest cleanup (materializer) — *optional, not load-bearing*
The actual OBJ import-prep already stages every `texture*` role dynamically ([`ReconstructionOpHandler.cs:632-639`](../../../src/Rook/Handlers/ReconstructionOpHandler.cs)), so Part 1's reclassification is staged automatically — **no materializer change is required for textures to reach Rhino.** The static `import_manifest.companion_roles = [material_mtl, texture]` in [`ReconstructionPackageMaterializer.cs:173-177`](../../../src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs) is now a slightly stale sidecar (it lists only the generic `texture`). Optionally align it to list `material_mtl` + the texture roles for honest documentation, but this is cosmetic consistency, not a functional requirement. **The plan must test the real staging path (the handler's companion enumeration), not just `import_manifest.companion_roles`.**

### Part 3 — OBJ/MTL integrity check + `material_maps_missing` warning (manager)
When the package has an OBJ + MTL, read the MTL, extract its `map_*` references, and compare each referenced **filename** against the **provider filenames** the package actually delivered. Provider filenames are **not** in the artifact manifest (which carries only role + path); they are recovered from the `provider_result_json` sidecar via the existing `ProviderFileNamesByRole(packageId, package)` pattern ([`ReconstructionOpHandler.cs:335`](../../../src/Rook/Handlers/ReconstructionOpHandler.cs)) — the same authority the import-prep uses to rename staged blobs. A referenced map is **present** iff its filename is among the package's delivered texture provider-filenames; otherwise **missing**.

- "Degraded" is **not** a new API field — `ReconstructionJobResultEnvelope` has only `Warnings`/`ResultKind`/`AssetRoles`. For this slice, **degraded ⇔ the result's `warnings[]` contains a `material_maps_missing` warning.**
- If any referenced map is missing → emit the **new** warning **`material_maps_missing`**:
  ```jsonc
  {
    "code": "material_maps_missing",
    "details": {
      "missing_maps": ["texture_pbr_v128.png", "texture_pbr_v128_roughness.png", "texture_pbr_v128_normal.png"],
      "missing_base_color": true,          // map_Kd's file is absent — the white-mesh cause (high signal)
      "material_role": "material_mtl",
      "asset_role": "model_obj"
    }
  }
  ```
- **`map_Kd` missing ⇒ `missing_base_color: true`** is the high-signal case (model imports white). Missing normal/roughness/metallic are lower-severity but **still listed** in `missing_maps`.
- The message text states the truth: *"The OBJ material references texture maps not present in the package; the model will import without its base-color texture."*

### Part 4 — Where the integrity warning slots in (manager `Result()`)
`BuildTextureWarnings` is intentionally **pure** (it sees only delivered role *names*, no store/MTL access) and its role-presence check (`material_mtl` or any `texture*` ⇒ no warning) stays as the "expected-but-totally-absent" guard. The integrity check is a **separate, additive** concern that needs package access (the MTL blob + `provider_result_json`), so it runs in the `Result()` path that assembles the envelope's `warnings[]`, **appending** `material_maps_missing` when an OBJ+MTL package has unsatisfied `map_*` references. The two are complementary: `result_missing_texture` fires when there is *no* texture/material at all; `material_maps_missing` fires when material/texture *is* present but the MTL references files the package didn't deliver — the exact gap line 736-740 leaves open. No change to `BuildTextureWarnings`' role-presence rule is required.

### Contract decisions (locked)
- **A — warn-and-proceed.** Import still runs (white geometry is useful); the result carries the specific `material_maps_missing` warning (which *is* the degraded signal — no separate flag). **Do NOT block import.**
- **Do NOT reuse `result_missing_texture`** — too generic; it can't say *which* maps are missing or distinguish incomplete-bundle from no-texture-at-all. `material_maps_missing` is a new, distinct code.

### Out of scope
- Re-requesting alternate provider assets (a GLB, a re-run) — provider-coupled, separate effort (rejected option C).
- Making *this* import textured — impossible; the base-color map is genuinely absent from fal's output.
- Any UI, native importer, or provider-submit change. (The Result panel already renders `result.warnings[]` by code; this warning flows through that existing surface.)

---

## 3. Components / files (managed only)

- `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs` — Part 1: classify top-level `texture` + `model_urls.texture` via the existing `ClassifyTextureRole` instead of the generic role.
- A small reusable **MTL `map_*` parser** (new file, e.g. `ObjMaterialReferences.cs`) — extract referenced map filenames from MTL text (`map_Kd`, `map_Ka`, `map_Ks`, `map_Pm`, `map_Pr`, `map_Bump`/`bump`, `map_d`, `norm`), tolerating options like `-bm 1.0`, `-s`, `-o`. Pure, unit-testable.
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — Part 3/4: in the `Result()` path, an MTL-integrity step that reads the package MTL blob, recovers delivered provider filenames from `provider_result_json` (the `ProviderFileNamesByRole` authority — extract/share that helper rather than duplicating it), compares `map_*` refs, and **appends** a `material_maps_missing` warning to the envelope's `warnings[]`. A new `material_maps_missing` warning-code constant.
- `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs` — *optional* Part 2 cleanup of the stale static `companion_roles` sidecar. Not required for textures to stage.

No changes to `src/RookNative/`, the MCP server, the Vision web UI, or `ReconstructionJobResultEnvelope`'s shape.

---

## 4. Testing

- **MTL parser (new):** `map_Kd texture_pbr_v128.png` → `texture_pbr_v128.png`; `map_Bump -bm 1.0 texture_pbr_v128_normal.png` → `texture_pbr_v128_normal.png` (options stripped); multiple maps; blank/comment lines; missing-map lines ignored. The literal 4-line MTL above is a fixture.
- **Mapper classification:** feed the **literal `provider_result_json`** above; assert the result artifacts include role `texture_metallic` (filename `texture_pbr_v128_metallic.png`) and **no** generic `texture` / no `texture_base_color`; model role is `model_obj` (the `model_glb`-field OBJ reclassified by content-type), no `model_glb`.
- **Real staging path (not the static manifest):** exercise the handler's OBJ companion enumeration ([`ReconstructionOpHandler.cs:632-639`](../../../src/Rook/Handlers/ReconstructionOpHandler.cs)) — a package with `model_obj` + `material_mtl` + `texture_metallic` stages `material_mtl` and `texture_metallic` (renamed to its provider filename), proving Part 1's reclassification reaches Rhino. (Asserting only `import_manifest.companion_roles` would be testing the wrong surface.)
- **Integrity + warning (the headline test):** a package built from the literal `provider_result_json` above (OBJ + MTL refs 4 maps + only `texture_pbr_v128_metallic.png` delivered) → `material_maps_missing` warning present in `warnings[]` with `missing_base_color: true`, `missing_maps == [texture_pbr_v128.png, texture_pbr_v128_roughness.png, texture_pbr_v128_normal.png]`, `material_role: "material_mtl"`, `asset_role: "model_obj"`; import is **not** blocked. (Provider filenames resolved from `provider_result_json`, the live mechanism.)
- **Healthy path (no false positive):** package whose MTL's referenced maps are all delivered → **no** `material_maps_missing` warning.
- **Full C# suite green**; MTL/mapper/materializer/manager tests in the existing reconstruction test projects.

---

## 5. Verification

Managed-only → managed Release build (`dotnet build src/Rook/Rook.csproj -c Release` → `DeployToRhino` auto-deploys all TFMs; Rhino closed). No native rebuild, no MCP reload. Live smoke: re-run / re-open the failing job (or an equivalent rapid generation) and confirm the Result panel now shows the `material_maps_missing` warning naming the missing maps, the result is flagged (not silently healthy), and import still proceeds (geometry imports; white is now *explained*). A future generation that ships a complete texture set imports textured and shows no warning.

---

## 6. Relationship to parked work

The Reconstruct UI scaffold (`feature/reconstruct-ui-scaffold`) is parked, clean, unmerged — it is exonerated by this diagnosis (the texture path it never touched is the actual cause). This fix ships first; the scaffold resumes afterward. The Result panel already renders `result.warnings[]` generically, so `material_maps_missing` surfaces with no UI work.
