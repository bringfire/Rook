# Bind all supported reconstruction PBR maps into repaired Rhino materials

- **Date:** 2026-06-24
- **Status:** Design approved; ready for implementation plan
- **Base:** `origin/main` @ `1ce26cbe`
- **Scope:** managed (`src/Rook`) + native (`src/RookNative`). No Python/MCP changes.
- **Follow-on to:** PR #349 (issue #348 v1 — normal map). This completes PBR map binding.

## Problem

#349 wired `base_color` + `normal` into the repaired Rhino material via the
`material_repair.maps[]` schema. But reconstruction packages from Meshy v6 (with
`enable_pbr: true`) also stage **roughness** and **metallic** maps — the captured package
`d61c3f06` carries all four (`texture_base_color`, `texture_normal`, `texture_roughness`,
`texture_metallic`). Those two are staged on disk but never bound to a material slot, so the
repaired material is incomplete.

This slice binds **all four roles the mapper can produce today**.

## Goal

Emit and bind every staged, supported PBR map:

| role (mapper) | channel | `ON_Texture::TYPE` | color space |
|---|---|---|---|
| `texture_base_color` | `base_color` | `pbr_base_color_texture` (1) | sRGB (linear=false) |
| `texture_normal` | `normal` | `pbr_bump_texture` (2) | data (linear=true) |
| `texture_roughness` | `roughness` | `pbr_roughness_texture` (16) | data (linear=true) |
| `texture_metallic` | `metallic` | `pbr_metallic_texture` (13) | data (linear=true) |

Non-goals:
- **AO / emissive are out.** The mapper
  ([`FalReconstructionResultMapper`](../../../src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs))
  produces only the four roles above — neither its `TextureSlotRoles` table nor its filename
  classifier emits `texture_ao` / `texture_emissive`. Binding them would be dead native
  branches. They are a separate future slice that must start on the **mapper/provider** side
  (plus a captured fixture that proves them).
- No `material_repair.maps[]` schema change (same `{channel, role, path, file_name}`).
- No Python/MCP/UI change.

## Design

### 1. Managed `MaterialRepair` — emit four maps, fixed order, present-only

In [`ReconstructionOpHandler.cs`](../../../src/Rook/Handlers/ReconstructionOpHandler.cs),
`MaterialRepair` keeps `base_color` as the repair trigger, then appends each staged data map
in **fixed order**: `base_color → normal → roughness → metallic`. Each appended via the
existing `MaterialMapEntry(...)`, gated on `HasRole(package, "texture_<x>")`:

```csharp
var maps = new List<object?>
{
    MaterialMapEntry(package, "base_color", baseColorRole, providerFileNames),
};
if (HasRole(package, "texture_normal"))
    maps.Add(MaterialMapEntry(package, "normal", "texture_normal", providerFileNames));
if (HasRole(package, "texture_roughness"))
    maps.Add(MaterialMapEntry(package, "roughness", "texture_roughness", providerFileNames));
if (HasRole(package, "texture_metallic"))
    maps.Add(MaterialMapEntry(package, "metallic", "texture_metallic", providerFileNames));
```

- `base_color` is still the trigger: no base-color role → return `null` (no plan).
- Present-only: a base-color-only package yields one entry; a base_color+normal package two;
  `d61c3f06` four.

### 2. Native — small file-local channel binding table

In [`ImportExportHandler.cpp`](../../../src/RookNative/Handlers/ImportExportHandler.cpp),
replace the growing `if/else` channel chain in `ApplyReconstructionMaterialRepair` with a
**small file-local table** (struct + static array immediately above the function — nothing
exported, no new types elsewhere):

```cpp
struct PbrChannelBinding
{
    const char* channel;
    ON_Texture::TYPE type;
    bool treatAsLinear;
    bool legacyMirror;
};

static const PbrChannelBinding kPbrChannelBindings[] = {
    { "base_color", ON_Texture::TYPE::pbr_base_color_texture, false, true  },
    { "normal",     ON_Texture::TYPE::pbr_bump_texture,       true,  false },
    { "roughness",  ON_Texture::TYPE::pbr_roughness_texture,  true,  false },
    { "metallic",   ON_Texture::TYPE::pbr_metallic_texture,   true,  false },
};
```

The loop looks the channel up in the table:
- **No match → `material_repair_error` "Unknown material repair channel: <channel>"**, return
  `false` (strict, preserved).
- On match, build the explicit `ON_Texture` exactly as #349:
  `m_image_file_reference = ON_FileReference::CreateFromFullPath(pathW, false, true)`,
  `m_type = binding.type`, `m_bTreatAsLinear = binding.treatAsLinear`, `m_bOn = true`, then
  `pbr->AddTexture(tex)`.
- `binding.legacyMirror` (true only for `base_color`) captures `baseColorLegacyPath`; the
  legacy `bitmap_texture` mirror is still added **after** `SynchronizeLegacyMaterial()`
  (unchanged #349 ordering — synchronize must not clobber the mirror).

Per-entry validation (empty path, `ValidateFilePath`, `fs::exists`) is unchanged.

### 3. Color space (SDK-confirmed, not assumed)

From `opennurbs_texture.h`, `m_bTreatAsLinear`'s own doc: *"If false, the texture color
values [are] corrected by the linear-workflow gamma… if true, the values [are] used raw."*
So `base_color` is color (gamma-corrected, `linear=false`); `normal`/`roughness`/`metallic`
are data maps used raw (`linear=true`). Encoded in the table's `treatAsLinear` column. Enum
values verified from the installed SDK: `pbr_base_color_texture=1`, `pbr_bump_texture=2`,
`pbr_metallic_texture=13`, `pbr_roughness_texture=16`.

### 4. Strict + non-fatal (unchanged from #349)

A non-object map entry, an unknown channel, or a missing file each set
`material_repair_error` and make the repair return `false` — but `import_package` still
succeeds (`wr.success = associated`). The v1 two-channel guarantees simply extend to four.

## Testing (deterministic — no fal calls, no native build)

- **Managed** ([`ReconstructionOpHandlerTests.cs`](../../../src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs)):
  - A package with all four `texture_*` roles staged → `maps[]` has four entries with channels
    `base_color, normal, roughness, metallic` **in that order**, each role matched.
  - A `base_color` + `normal` only package → exactly two entries (proves present-only/partial:
    roughness/metallic omitted when absent).
  - No base-color role → `MaterialRepair` returns `null` (no plan).
- **Native source assertions**
  ([`NativeReconstructionDispatchSourceTests.cs`](../../../src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs)):
  Assert the `.cpp` table **rows encode the exact tuples** (not merely that `treatAsLinear=true`
  appears somewhere):
  - `base_color` → `pbr_base_color_texture`, `false, true`
  - `normal` → `pbr_bump_texture`, `true, false`
  - `roughness` → `pbr_roughness_texture`, `true, false`
  - `metallic` → `pbr_metallic_texture`, `true, false`

  Plus the retained guards: `material_repair[\"maps\"]` iteration, `CreateFromFullPath`,
  `Material repair map entry was not an object`, `Unknown material repair channel`,
  `wr.success = associated;`, and synchronize-before-legacy-bitmap ordering.

## Live smoke (gate — no paid run)

Re-import the **already-staged** package `d61c3f06-0c85-4e01-a84c-56bd5439a966`
(`rhino_2d_to_3d_import package_id=d61c3f06…`) on the deployed build. Authoritative
`Material.GetTextures()` dump of the `Rook Reconstruction …` material must show:

- **base-color texture remains bound** (and legacy/non-PBR display still works — Rhino may
  expose both the PBR base-color texture and the legacy bitmap mirror; the pass criterion is
  that base color is bound and non-PBR display is intact, NOT a specific single `Bitmap` row),
- **`normal`, `roughness`, `metallic` each bound to their PBR slot with `TreatAsLinear=true`**,
- `material_repair_applied: true`, no `material_repair_error`, no non-PBR display regression.

Note: `d61c3f06`'s metallic map is a 7 KB near-uniform image (the subject is non-metallic) —
it binds and proves the channel even though it won't look dramatic. No fresh paid fal call is
needed; the package is staged on disk at
`%AppData%\Rook\artifacts\2026-06-24\d61c3f06-…\`.

## Risks

- **Native build not verifiable here.** Native correctness = source assertions + the live
  smoke; we do not claim a native build/test in CI.
- **Color-space drift.** A data map sampled as sRGB renders subtly wrong; mitigated by the
  per-row `treatAsLinear=true` (SDK-confirmed) and the live `GetTextures()` dump.

## Out of scope

- AO, emissive, displacement, clearcoat, and any PBR channel beyond the four.
- Mapper/provider changes (the four roles already exist; new roles are a separate slice).
- `material_repair.maps[]` schema, MCP surface, Python provider mapping, UI.
