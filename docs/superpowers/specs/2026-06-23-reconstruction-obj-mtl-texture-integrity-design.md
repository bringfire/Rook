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
2. **Staging carries only the generic role (materializer).** [`ReconstructionPackageMaterializer.cs:173-177`](../../../src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs) hard-codes `asset_bindings.model_obj.companion_roles = [material_mtl, texture]`. The import bundle stages exactly that — OBJ + MTL + the single `texture` blob (renamed to its provider filename `texture_pbr_v128_metallic.png`). The MTL's `map_Kd texture_pbr_v128.png` has no file → Rhino renders white.
3. **False "healthy" (degraded detection).** [`ReconstructionJobManager.cs:701-711`](../../../src/Rook/Services/Reconstruction/ReconstructionJobManager.cs) treats `material_mtl` present ⇒ not degraded, so **no warning** fires even though the MTL points at maps absent from the package. The result is reported as healthy while importing white.

**Conclusion (proven, not assumed):** for this generation the diffuse/roughness/normal maps are **genuinely absent from fal's output** (`model_urls.glb=null`, `model_glb` is an OBJ, no `texture_urls`, only the metallic URL). There is no recoverable texture and no GLB fallback. The model *cannot* be made textured — so the fix is **truthful degradation**, plus recovering classification/staging for the cases where data *is* present.

---

## 2. Scope (B — recover-where-possible + degrade-honestly)

Three coordinated managed changes; **no native, no UI, no provider re-request**:

### Part 1 — Classify texture roles by filename (mapper)
Wire the **top-level `texture`** and any **`model_urls.texture`** through the existing `ClassifyTextureRole(fileName, url)`, exactly as the `texture_urls` loop already does. Result for this package: the metallic lands as `texture_metallic` (not generic `texture`), so the package honestly shows it has `texture_metallic` and **no `texture_base_color`**. Recovers any future payload that *does* ship detailed maps in `texture`/`model_urls`.

### Part 2 — Stage all texture roles (materializer)
`companion_roles` for `model_obj` must include **`material_mtl` + every texture role present** (`texture`, `texture_base_color`, `texture_metallic`, `texture_roughness`, `texture_normal`) — not just the generic `texture`. Otherwise Part 1's reclassification would stage *zero* textures (the metallic would no longer match the hard-coded `[material_mtl, texture]`). This is load-bearing, not optional.

### Part 3 — OBJ/MTL integrity check + truthful degradation (manager)
When the package has an OBJ + MTL, read the MTL, extract its `map_*` references, and compare each referenced **filename** against the **provider filenames** of the texture files present in the package (texture files carry their provider `file_name` in artifact metadata; the staged bundle is renamed to those names). For each referenced map with no matching file → **missing**.

- If any referenced map is missing → mark the result **degraded** and emit the **new** warning **`material_maps_missing`**:
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

### Part 4 — Degraded determination no longer trusts `material_mtl` alone
[`ReconstructionJobManager.cs:701-711`](../../../src/Rook/Services/Reconstruction/ReconstructionJobManager.cs): the "material_mtl present ⇒ healthy" rule is wrong when the MTL's referenced maps are unsatisfied. Degraded must also be true when the integrity check (Part 3) finds missing referenced maps.

### Contract decisions (locked)
- **A — warn-and-proceed.** Import still runs (white geometry is useful); the result is flagged degraded with the specific warning. **Do NOT block import.**
- **Do NOT reuse `result_missing_texture`** — too generic; it can't say *which* maps are missing or distinguish incomplete-bundle from no-texture-at-all. `material_maps_missing` is a new, distinct code.

### Out of scope
- Re-requesting alternate provider assets (a GLB, a re-run) — provider-coupled, separate effort (rejected option C).
- Making *this* import textured — impossible; the base-color map is genuinely absent from fal's output.
- Any UI, native importer, or provider-submit change. (The Result panel already renders `result.warnings[]` by code; this warning flows through that existing surface.)

---

## 3. Components / files (managed only)

- `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs` — Part 1: classify top-level `texture` + `model_urls.texture` via `ClassifyTextureRole` instead of the generic role.
- `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs` — Part 2: `companion_roles` = `material_mtl` + all present texture roles.
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — Part 3 + 4: an MTL-integrity helper (parse `map_*`, compare to package texture provider-filenames), emit `material_maps_missing`, and feed the degraded determination. A new warning code constant.
- A small reusable **MTL `map_*` parser** (new file, e.g. `ObjMaterialReferences.cs`) — extract referenced map filenames from MTL text (`map_Kd`, `map_Ka`, `map_Ks`, `map_Pm`, `map_Pr`, `map_Bump`/`bump`, `map_d`, `norm`), tolerating options like `-bm 1.0`, `-s`, `-o`. Pure, unit-testable.
- Warning code constant alongside the existing reconstruction warning codes.

No changes to `src/RookNative/`, the MCP server, or the Vision web UI.

---

## 4. Testing

- **MTL parser (new):** `map_Kd texture_pbr_v128.png` → `texture_pbr_v128.png`; `map_Bump -bm 1.0 texture_pbr_v128_normal.png` → `texture_pbr_v128_normal.png` (options stripped); multiple maps; blank/comment lines; missing-map lines ignored. The literal 4-line MTL above is a fixture.
- **Mapper classification:** feed the **literal `provider_result_json`** above; assert the result artifacts include role `texture_metallic` (filename `texture_pbr_v128_metallic.png`) and **no** generic `texture` / no `texture_base_color`; model role is `model_obj` (the `model_glb`-field OBJ reclassified by content-type), no `model_glb`.
- **Materializer staging:** given a package with `model_obj` + `material_mtl` + `texture_metallic`, the import manifest's `companion_roles` includes `material_mtl` and `texture_metallic` (and would include `texture_base_color`/`roughness`/`normal` when present).
- **Integrity + warning (the headline test):** package = OBJ + the literal MTL (refs 4 maps) + only `texture_pbr_v128_metallic.png` present → `material_maps_missing` warning with `missing_base_color: true`, `missing_maps == [texture_pbr_v128.png, texture_pbr_v128_roughness.png, texture_pbr_v128_normal.png]`, `material_role: "material_mtl"`, `asset_role: "model_obj"`; result is **degraded**; import is **not** blocked.
- **Healthy path (no false positive):** package whose MTL's referenced maps are all present → **no** `material_maps_missing`, **not** degraded.
- **Full C# suite green**; MTL/mapper/materializer/manager tests in the existing reconstruction test projects.

---

## 5. Verification

Managed-only → managed Release build (`dotnet build src/Rook/Rook.csproj -c Release` → `DeployToRhino` auto-deploys all TFMs; Rhino closed). No native rebuild, no MCP reload. Live smoke: re-run / re-open the failing job (or an equivalent rapid generation) and confirm the Result panel now shows the `material_maps_missing` warning naming the missing maps, the result is flagged (not silently healthy), and import still proceeds (geometry imports; white is now *explained*). A future generation that ships a complete texture set imports textured and shows no warning.

---

## 6. Relationship to parked work

The Reconstruct UI scaffold (`feature/reconstruct-ui-scaffold`) is parked, clean, unmerged — it is exonerated by this diagnosis (the texture path it never touched is the actual cause). This fix ships first; the scaffold resumes afterward. The Result panel already renders `result.warnings[]` generically, so `material_maps_missing` surfaces with no UI work.
