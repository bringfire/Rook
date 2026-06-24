# Wire reconstruction PBR texture maps into repaired Rhino materials — v1 (normal map)

- **Issue:** [#348](https://github.com/bringfire/Rook/issues/348)
- **Date:** 2026-06-24
- **Status:** Design approved; ready for implementation plan
- **Base:** `origin/main` @ `1f0ce948`
- **Scope:** managed (`src/Rook`) + native (`src/RookNative`). No Python/MCP changes.
- **Follow-on to:** PR #347 (Meshy v6 single-image). This is the deferred limitation captured there.

## Problem

Reconstruction packages (Meshy v6, Hunyuan) carry detailed PBR texture roles —
`texture_base_color`, `texture_normal`, `texture_roughness`, `texture_metallic` — and
`ReconstructionOpHandler.CompanionFiles` already stages **every** `texture*` role to disk
alongside the imported mesh. But the material-repair path binds **only** the base color:

- Managed `MaterialRepair` ([`ReconstructionOpHandler.cs`](../../../src/Rook/Handlers/ReconstructionOpHandler.cs))
  emits a flat plan with `material_name`, `base_color_role`, `base_color_path`,
  `base_color_file_name`.
- Native `ApplyReconstructionMaterialRepair`
  ([`ImportExportHandler.cpp`](../../../src/RookNative/Handlers/ImportExportHandler.cpp))
  reads only `base_color_path` and assigns it to `pbr_base_color_texture` (+ a legacy
  `bitmap_texture` mirror for non-PBR display modes).

The Meshy v6 live smoke (PR #347) confirmed `texture_normal` is produced **and staged on
disk**, but it is never assigned to a material slot — the Rhino material's normal channel is
empty. This is **general**, not Meshy-specific: any provider package with a normal map hits
the same gap.

## Goal (v1)

Bind the **normal** map into the repaired Rhino material, and replace the flat single-channel
plan with a general, ordered `maps[]` schema so future channels are additive on the managed
side. v1 emits and binds exactly two channels: `base_color` and `normal`.

Explicit non-goals for v1:
- Roughness and metallic are **not** emitted by managed and **not** present in the native
  channel table. They come in a later PR — *managed emission + its own live smoke* against a
  real package that emits them. They are **not** "data-only."
- No Python/MCP/schema changes. The plan is an internal managed→native contract.

## Design

### 1. Plan schema (managed → native)

`MaterialRepair` returns an ordered, **present-only** `maps[]`. The legacy
`base_color_role` / `base_color_path` / `base_color_file_name` scalar fields are **removed**
(no compatibility mirror — managed and native deploy as a pair, and nothing else consumes
them):

```json
{
  "material_name": "Rook Reconstruction a1b2c3d4",
  "maps": [
    { "channel": "base_color", "role": "texture_base_color", "path": "<abs>", "file_name": "texture_0.png" },
    { "channel": "normal",     "role": "texture_normal",     "path": "<abs>", "file_name": "texture_0_normal.png" }
  ]
}
```

Rules:
- **Ordered:** `base_color` first, then `normal`.
- **Present-only:** a channel appears only when its staged file role exists in the package.
  No expected-but-missing entries, no null paths. Missing-map diagnostics remain in the
  existing warning path, out of the repair plan.
- Each entry carries `{ channel, role, path, file_name }`.

### 2. Managed builder behavior

In `MaterialRepair`:
- **`base_color` is the repair trigger.** Resolve the base-color role via the existing
  `BaseColorTextureRole` logic. If there is **no** base-color role, return `null` — no repair
  plan at all (preserves today's behavior; avoids creating a material whose only texture is a
  normal map).
- Append a `normal` entry when `HasRole(package, "texture_normal")` is true (the role is
  already staged by `CompanionFiles`).
- Do **not** emit roughness/metallic.
- Build `material_name` exactly as today (`"Rook Reconstruction " + importId[:8]`).

### 3. Native binding (`ApplyReconstructionMaterialRepair`)

- Read `maps[]` instead of the old scalar fields.
- A small **channel → `ON_Texture::TYPE`** table, **v1 = two channels only**:
  - `base_color → ON_Texture::TYPE::pbr_base_color_texture` (value 1), **plus** the legacy
    `bitmap_texture` add it does today, so non-PBR display modes still show the texture (no
    regression).
  - `normal → ON_Texture::TYPE::pbr_bump_texture` (value 2), applied with the verified
    normal-map `ON_Texture` treatment from the audit (Task 1) — at minimum
    `m_bTreatAsLinear = true`, because normal data must be sampled linearly, not as sRGB.
- **Strict contract** (once managed emits a map, native treats it as binding):
  - A present map entry whose `path` does not exist on disk → set `material_repair_error`
    and fail the repair (not silently skipped).
  - An **unknown** `channel` string (anything outside the v1 table) → `material_repair_error`
    and fail. (Inert recognized-but-unbound channels are deliberately excluded so "unknown
    channel is an error" stays meaningful.)
  - Absent `maps`/empty plan → no repair (unchanged "nothing to do").
- **"Fail the repair" means skip material assignment and report — it does NOT fail
  `import_package`.** This preserves today's behavior:
  `ApplyReconstructionMaterialRepair` returning `false` sets `material_repair_applied = false`
  and `material_repair_error`, but the import still succeeds and returns its imported objects.
  Import success is governed by object association (`wr.success = associated`), independent of
  material repair. A strict repair failure must remain non-fatal to the import.
- Object→material assignment is unchanged (`SetMaterialSource(material_from_object)`,
  `m_material_index`).

### 4. Rhino 8 SDK facts (verified from installed headers)

From `C:\Program Files\Rhino 8 SDK\openNURBS\opennurbs_texture.h` and
`opennurbs_material.h`:

| Channel | `ON_Texture::TYPE` | Value |
|---|---|---|
| base_color | `pbr_base_color_texture` | 1 |
| normal | `pbr_bump_texture` | 2 (aliases legacy `bump_texture`) |
| roughness *(future)* | `pbr_roughness_texture` | 16 |
| metallic *(future)* | `pbr_metallic_texture` | 13 |

- **There is no `pbr_normal_texture`.** In Rhino 8 the PBR normal map is delivered through
  the bump slot (`pbr_bump_texture == bump_texture == 2`).
- `ON_Texture` carries `bool m_bTreatAsLinear = false;` and
  `ON_Interval m_bump_scale = ON_Interval::ZeroToOne;`.
- `ON_PhysicallyBasedMaterial` exposes `AddTexture(const wchar_t* filename, ON_Texture::TYPE)`
  (already used for base color) and `AddTexture(const ON_Texture&)` for an explicitly
  configured texture.

### 5. Testing (deterministic — no fal calls, no MFC build)

- **Managed** ([`ReconstructionOpHandlerTests.cs`](../../../src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs)):
  - base-color-only package → plan has `maps` with one `base_color` entry, no `normal`.
  - package with `texture_normal` staged → `maps` has `base_color` then `normal`, in order.
  - no base-color role → `MaterialRepair` returns `null` (no plan).
  - plan carries no roughness/metallic channels.
- **Native source assertions**
  ([`NativeReconstructionDispatchSourceTests.cs`](../../../src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs)):
  assert the `.cpp` text contains the channel table, `pbr_bump_texture`, the
  `m_bTreatAsLinear` normal treatment, `maps` iteration, the strict `material_repair_error`
  path for missing-file and unknown-channel, and that `pbr_base_color_texture` +
  `ToPhysicallyBased()` + the assignment lines are retained. (Update the existing
  base_color-scalar assertions to the new `maps` shape.)
  - **Non-fatal guarantee:** assert import success stays gated on association
    (`wr.success = associated`), not on `materialRepairApplied` — a strict repair failure
    must not fail `import_package`.

### 6. SDK audit note (gates the native edit)

Before writing the native binding, produce a short, concrete note (appended to this spec)
that records, **from the installed Rhino 8 SDK headers** (`opennurbs_texture.h`,
`opennurbs_material.h`, `opennurbs_file_utilities.h`) — header/API verification, not a live
material render check:
- the **exact `ON_Texture` fields/methods** used to bind the normal map (e.g. construct
  `ON_Texture`, set `m_filename`, `m_type = pbr_bump_texture`, `m_bTreatAsLinear = true`,
  any `m_bump_scale` / mapping-channel settings), and whether the convenience
  `AddTexture(filename, type)` is sufficient or an explicit `ON_Texture` is required;
- **why `pbr_bump_texture` is the correct Rhino 8 slot** for a tangent-space normal map (no
  dedicated `pbr_normal_texture`; bump slot semantics).

The source assertions in §5 then lock whatever the audit verifies.

### 7. Live smoke (promotion gate)

Re-run the Meshy v6 single-image submit (the cat) → import → open the resulting material:
- **normal slot is populated** with the staged normal map,
- base color still bound,
- no non-PBR display regression.

That is the single pass criterion for v1. Roughness/metallic are a **separate future PR**
(managed emission **+** their own live smoke against a package that actually emits them).

## Risks

- **Normal-map color space.** If the bump slot is fed an sRGB-sampled texture, lighting is
  subtly wrong. Mitigated by the audit task pinning `m_bTreatAsLinear` (and any normal-map
  mode) before the native edit lands.
- **Native build not verifiable here.** Native correctness is covered by source assertions +
  the live smoke; we do not claim a native build/test in CI for this change.

## Out of scope

- Roughness, metallic, AO, emission, and any other PBR channel.
- Any change to staging (`CompanionFiles` already stages all `texture*` roles).
- MCP tool surface, Python provider mapping, package manifest schema.
