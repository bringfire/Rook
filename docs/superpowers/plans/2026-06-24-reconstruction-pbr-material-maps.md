# Reconstruction PBR Material Maps (v1: normal) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the reconstruction `normal` texture map into the repaired Rhino material, via a generalized `material_repair.maps[]` plan that replaces the flat `base_color_*` scalars.

**Architecture:** Managed `MaterialRepair` emits an ordered, present-only `maps[]` (base_color, then normal). Native `ApplyReconstructionMaterialRepair` reads `maps[]`, binds each channel to its `ON_Texture::TYPE` (base_color → `pbr_base_color_texture` + legacy bitmap mirror; normal → `pbr_bump_texture`, linear), strictly errors on unknown channel / missing file, and stays non-fatal to `import_package`. Roughness/metallic are out of scope for v1.

**Tech Stack:** C# (.NET, `src/Rook`, `src/Rook.Tests`, xUnit), C++ (`src/RookNative`, OpenNURBS / Rhino 8 SDK), JSON via `System.Text.Json.Nodes` (managed) and `nlohmann::json` (native).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-24-reconstruction-pbr-material-maps-design.md`. Every task implicitly conforms to it.
- **No compatibility mirror:** `base_color_role` / `base_color_path` / `base_color_file_name` are **removed**, not kept alongside `maps[]`.
- **v1 channels only:** `base_color` and `normal`. Do **not** add roughness/metallic to managed emission or the native channel table.
- **Present-only:** a channel appears in `maps[]` only when its staged file role exists.
- **base_color is the repair trigger:** no base-color role → `MaterialRepair` returns `null` (no plan).
- **Strict repair, non-fatal import:** unknown channel or missing file → set `material_repair_error`, return `false` from `ApplyReconstructionMaterialRepair`. Import success stays `wr.success = associated`; a repair failure never fails `import_package`.
- **No `.vcxproj` / `.vcxproj.filters` edits.** No Python/MCP/schema changes.
- **Do not claim a native build.** Native correctness = source assertions + the Task 3 live smoke.
- **Verified Rhino 8 SDK facts** (from `C:\Program Files\Rhino 8 SDK\openNURBS\opennurbs_texture.h` / `opennurbs_material.h` / `opennurbs_file_utilities.h`):
  - `ON_Texture::TYPE::pbr_base_color_texture = 1`, `pbr_bump_texture = 2` (= legacy `bump_texture`; **the** PBR normal slot — there is no `pbr_normal_texture`).
  - `ON_Texture` public fields: `ON_FileReference m_image_file_reference`, `ON_Texture::TYPE m_type`, `bool m_bTreatAsLinear`, `bool m_bOn`.
  - `ON_FileReference::CreateFromFullPath(const wchar_t* full_path, bool bSetContentHash, bool bSetFullPathStatus)`.
  - `ON_PhysicallyBasedMaterial::AddTexture(const ON_Texture&)` and `ON_Material::AddTexture(const wchar_t*, ON_Texture::TYPE)`.
- **Managed test side effect:** `dotnet test` on `src/Rook.Tests` deploys `Rook.rhp` into `%AppData%` (touches the local install). Run with Rhino closed.

---

### Task 1: Managed — emit `material_repair.maps[]` (base_color + normal)

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs:663-695` (`MaterialRepair`, `BaseColorTextureRole`)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Consumes: existing `BaseColorTextureRole(Artifact)`, `HasRole(Artifact, string)`, `FileNameForRole(IReadOnlyDictionary<string,string>, string, string)`, `_store.GetBlobAbsolutePath(Guid, string)`.
- Produces: `MaterialRepair(...)` now returns `Dictionary<string,object?>?` with keys `material_name` and `maps` (a `List<object?>` of `Dictionary<string,object?>` entries, each `{ channel, role, path, file_name }`). No `base_color_*` keys.

- [ ] **Step 1: Update the existing GLB+texture test to the `maps` shape**

In `ReconstructionOpHandlerTests.cs`, replace the three `base_color_*` assertions in `DispatchOffUi_PrepareImport_GlbWithTextureCarriesMaterialRepair` (currently lines ~179-181) with:

```csharp
        var repair = Assert.IsType<Dictionary<string, object?>>(data["material_repair"]);
        Assert.Equal("Rook Reconstruction cccccccc", repair["material_name"]);
        var maps = Assert.IsAssignableFrom<IReadOnlyList<object?>>(repair["maps"]);
        var baseMap = Assert.IsType<Dictionary<string, object?>>(Assert.Single(maps));
        Assert.Equal("base_color", baseMap["channel"]);
        Assert.Equal("texture", baseMap["role"]);
        Assert.Equal("texture_20250901.png", baseMap["file_name"]);
        Assert.EndsWith("texture.png", Assert.IsType<string>(baseMap["path"]));
```

- [ ] **Step 2: Add a test that appends `normal` when `texture_normal` is staged**

Add to `ReconstructionOpHandlerTests.cs` (mirror the structure of the GLB test; the Meshy-shape provider json yields `texture_base_color` + `texture_normal` package roles):

```csharp
    [Fact]
    public async Task DispatchOffUi_PrepareImport_AppendsNormalMapWhenPresent()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/m.glb"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/base.png"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/normal.png"] = new byte[] { 7, 8, 9 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_glb": {"url": "https://example.test/m.glb"},
          "texture_urls": [
            {
              "base_color": {"url": "https://example.test/base.png", "file_name": "texture_0.png"},
              "normal":     {"url": "https://example.test/normal.png", "file_name": "texture_0_normal.png"},
              "metallic":   null,
              "roughness":  null
            }
          ]
        }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        var repair = Assert.IsType<Dictionary<string, object?>>(data["material_repair"]);
        var maps = Assert.IsAssignableFrom<IReadOnlyList<object?>>(repair["maps"]);
        Assert.Equal(2, maps.Count);

        var baseMap = Assert.IsType<Dictionary<string, object?>>(maps[0]);
        Assert.Equal("base_color", baseMap["channel"]);
        Assert.Equal("texture_base_color", baseMap["role"]);

        var normalMap = Assert.IsType<Dictionary<string, object?>>(maps[1]);
        Assert.Equal("normal", normalMap["channel"]);
        Assert.Equal("texture_normal", normalMap["role"]);
        Assert.Equal("texture_0_normal.png", normalMap["file_name"]);
        Assert.EndsWith("normal.png", Assert.IsType<string>(normalMap["path"]));
    }
```

- [ ] **Step 3: Add a test that geometry-only packages produce no repair plan**

```csharp
    [Fact]
    public async Task DispatchOffUi_PrepareImport_NoBaseColorYieldsNoMaterialRepair()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/m.glb"] = new byte[] { 1, 2, 3 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        { "model_glb": {"url": "https://example.test/m.glb"} }
        """)!);

        var response = fixture.Handler.DispatchOffUi(
            "{" +
            "\"op\":\"prepare_import\"," +
            $"\"package_id\":\"{package.Id}\"," +
            "\"import_id\":\"cccccccc-cccc-cccc-cccc-cccccccccccc\"" +
            "}");

        Assert.True(response.Success, JsonSerializer.Serialize(response.Data));
        var data = Assert.IsType<Dictionary<string, object?>>(response.Data);
        Assert.False(data.ContainsKey("material_repair"));
    }
```

- [ ] **Step 4: Run the new/updated tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests" -v minimal`
Expected: `GlbWithTexture...` FAILs on `repair["maps"]` (key missing), `AppendsNormalMap...` FAILs (no `maps` key). `NoBaseColor...` will likely already **PASS** against current behavior — today a package with no base-color role already gets no `material_repair`. That is fine: it is a regression guard, not a red-first test. The two `maps`-shape tests are the ones that must be red here.

- [ ] **Step 5: Rewrite `MaterialRepair` to emit `maps[]`**

In `ReconstructionOpHandler.cs`, replace the body of `MaterialRepair` (lines ~663-679) with:

```csharp
        private Dictionary<string, object?>? MaterialRepair(
            Artifact package,
            Guid importId,
            IReadOnlyDictionary<string, string> providerFileNames)
        {
            var baseColorRole = BaseColorTextureRole(package);
            if (baseColorRole is null) return null;

            var maps = new List<object?>
            {
                MaterialMapEntry(package, "base_color", baseColorRole, providerFileNames),
            };

            if (HasRole(package, "texture_normal"))
                maps.Add(MaterialMapEntry(package, "normal", "texture_normal", providerFileNames));

            return new Dictionary<string, object?>
            {
                ["material_name"] = "Rook Reconstruction " + importId.ToString("N").Substring(0, 8),
                ["maps"] = maps,
            };
        }

        private Dictionary<string, object?> MaterialMapEntry(
            Artifact package,
            string channel,
            string role,
            IReadOnlyDictionary<string, string> providerFileNames)
        {
            var path = _store.GetBlobAbsolutePath(package.Id, role);
            return new Dictionary<string, object?>
            {
                ["channel"] = channel,
                ["role"] = role,
                ["path"] = path,
                ["file_name"] = FileNameForRole(providerFileNames, role, path),
            };
        }
```

Leave `BaseColorTextureRole` (lines ~681-695) unchanged.

- [ ] **Step 6: Run the full managed reconstruction tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" -v minimal`
Expected: PASS (all reconstruction tests, including the three above).

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "feat(reconstruction): emit material_repair.maps[] with base_color + normal"
```

---

### Task 2: Native — bind `maps[]` (base_color + normal), strict + non-fatal

**Files:**
- Modify: `docs/superpowers/specs/2026-06-24-reconstruction-pbr-material-maps-design.md` (append the SDK audit note)
- Modify: `src/RookNative/Handlers/ImportExportHandler.cpp:224-305` (`ApplyReconstructionMaterialRepair`)
- Test: `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs:175-197`

**Interfaces:**
- Consumes: `materialRepair["maps"]` (array of `{ channel, role, path, file_name }`) from Task 1; native helpers `JsonStringOr`, `Rook::ValidateFilePath`, `Utf8ToWide`, `fs::exists`.
- Produces: `ApplyReconstructionMaterialRepair` binds base_color (`pbr_base_color_texture` + legacy `bitmap_texture`) and normal (`pbr_bump_texture`, `m_bTreatAsLinear = true`); returns `false` with `error` set on unknown channel / missing file (non-fatal to import).

- [ ] **Step 1: Append the SDK audit note to the spec**

This is **header/API verification** (read from the installed SDK), not a live Rhino material
check. Append this section to the spec file, then commit it on its own:

```markdown
## SDK audit note (verified 2026-06-24, Rhino 8 SDK headers)

- **Slot:** the PBR normal map binds to `ON_Texture::TYPE::pbr_bump_texture` (value 2,
  aliasing legacy `bump_texture`). Rhino 8 has **no** `pbr_normal_texture`; the bump slot is
  the normal-map slot.
- **Construction (explicit `ON_Texture`, not the filename convenience):**
  - `tex.m_image_file_reference = ON_FileReference::CreateFromFullPath(pathW, /*bSetContentHash*/ false, /*bSetFullPathStatus*/ true);`
  - `tex.m_type = ON_Texture::TYPE::pbr_bump_texture;`
  - `tex.m_bTreatAsLinear = true;`  // normal vectors must sample linearly, not sRGB
  - `tex.m_bOn = true;`
  - `pbr->AddTexture(tex);`
- **base_color** keeps `m_bTreatAsLinear = false` (sRGB color) plus the legacy
  `mat.AddTexture(path, bitmap_texture)` mirror so non-PBR display modes are unaffected.
- The convenience `AddTexture(filename, type)` builds a default `ON_Texture`
  (`m_bTreatAsLinear = false`), which is wrong for a normal map — hence the explicit build.
```

```bash
git add docs/superpowers/specs/2026-06-24-reconstruction-pbr-material-maps-design.md
git commit -m "docs(reconstruction): record verified normal-map ON_Texture audit"
```

- [ ] **Step 2: Update the native source-assertion test to the `maps[]` contract**

In `NativeReconstructionDispatchSourceTests.cs`, replace the body of
`ReconstructionImport_AppliesPreparedMaterialRepairToImportedObjects` (lines ~175-197) with:

```csharp
    [Fact]
    public void ReconstructionImport_AppliesPreparedMaterialRepairToImportedObjects()
    {
        var text = File.ReadAllText(Path.Combine(
            RepoRoot, "src", "RookNative", "Handlers", "ImportExportHandler.cpp"));
        var handler = ExtractFunction(text, "void HandleReconstructionImport");

        Assert.Contains("static bool ApplyReconstructionMaterialRepair", text);
        Assert.Contains("const nlohmann::json materialRepair = plan.value(", handler);
        Assert.Contains("\"material_repair\"", handler);
        Assert.Contains("ApplyReconstructionMaterialRepair(", handler);
        Assert.Contains("newIds", handler);
        Assert.Contains("materialRepair", handler);

        // Generalized maps[] binding
        Assert.Contains("materialRepair[\"maps\"]", text);
        Assert.Contains("ON_Texture::TYPE::pbr_base_color_texture", text);
        Assert.Contains("ON_Texture::TYPE::pbr_bump_texture", text);
        Assert.Contains("m_bTreatAsLinear = true", text);
        Assert.Contains("ON_FileReference::CreateFromFullPath", text);
        Assert.Contains("mat.ToPhysicallyBased();", text);

        // Strict contract
        Assert.Contains("Unknown material repair channel", text);
        Assert.Contains("Material repair map entry was not an object", text);

        // Assignment + result flags
        Assert.Contains("attrs.SetMaterialSource(ON::material_from_object);", text);
        Assert.Contains("attrs.m_material_index = matIdx;", text);
        Assert.Contains("wr.data[\"material_repair_applied\"]", handler);

        // Non-fatal guarantee: import success is gated on association, not material repair
        Assert.Contains("wr.success = associated;", handler);
    }
```

- [ ] **Step 3: Run the source test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests" -v minimal`
Expected: FAIL on `materialRepair["maps"]` / `pbr_bump_texture` / `m_bTreatAsLinear = true` / `CreateFromFullPath` / `Unknown material repair channel` (none present yet).

- [ ] **Step 4: Rewrite `ApplyReconstructionMaterialRepair` to bind `maps[]`**

In `ImportExportHandler.cpp`, replace the whole function body (lines ~224-305) with:

```cpp
static bool ApplyReconstructionMaterialRepair(
    CRhinoDoc* pDoc,
    const std::vector<ON_UUID>& objectIds,
    const nlohmann::json& materialRepair,
    std::string& error)
{
    if (!materialRepair.is_object() || materialRepair.empty())
        return false;

    if (!materialRepair.contains("maps")
        || !materialRepair["maps"].is_array()
        || materialRepair["maps"].empty())
    {
        error = "Prepared material repair was missing maps.";
        return false;
    }

    const std::string materialName = JsonStringOr(
        materialRepair, "material_name", "Rook Reconstruction Material");

    ON_Material mat;
    mat.SetName(Utf8ToWide(materialName));
    mat.SetDiffuse(ON_Color::White);
    mat.SetSpecular(ON_Color::Black);
    mat.SetShine(0.0);
    mat.ToPhysicallyBased();

    auto pbr = mat.PhysicallyBased();
    if (!pbr)
    {
        error = "Failed to initialize physically based material for repair.";
        return false;
    }
    pbr->SetBaseColor(ON_4fColor(1.0f, 1.0f, 1.0f, 1.0f));
    pbr->SetRoughness(0.5);

    for (const auto& entry : materialRepair["maps"])
    {
        if (!entry.is_object())
        {
            error = "Material repair map entry was not an object.";
            return false;
        }

        const std::string channel = JsonStringOr(entry, "channel");
        const std::string texturePath = JsonStringOr(entry, "path");

        ON_Texture::TYPE pbrType = ON_Texture::TYPE::no_texture_type;
        bool treatAsLinear = false;
        bool addLegacyBitmap = false;
        if (channel == "base_color")
        {
            pbrType = ON_Texture::TYPE::pbr_base_color_texture;
            treatAsLinear = false;   // sRGB color
            addLegacyBitmap = true;  // show in non-PBR display modes
        }
        else if (channel == "normal")
        {
            pbrType = ON_Texture::TYPE::pbr_bump_texture;
            treatAsLinear = true;    // normal vectors sample linearly
            addLegacyBitmap = false;
        }
        else
        {
            error = "Unknown material repair channel: " + channel;
            return false;
        }

        if (texturePath.empty())
        {
            error = "Material repair map for channel '" + channel + "' was missing path.";
            return false;
        }
        const std::string pathErr = Rook::ValidateFilePath(texturePath);
        if (!pathErr.empty())
        {
            error = pathErr;
            return false;
        }
        if (!fs::exists(texturePath))
        {
            error = "Material repair texture was not found: " + texturePath;
            return false;
        }

        const ON_wString texturePathW = Utf8ToWide(texturePath);

        ON_Texture tex;
        tex.m_image_file_reference = ON_FileReference::CreateFromFullPath(
            static_cast<const wchar_t*>(texturePathW), false, true);
        tex.m_type = pbrType;
        tex.m_bTreatAsLinear = treatAsLinear;
        tex.m_bOn = true;
        pbr->AddTexture(tex);

        if (addLegacyBitmap)
            mat.AddTexture(
                static_cast<const wchar_t*>(texturePathW),
                ON_Texture::TYPE::bitmap_texture);
    }

    pbr->SynchronizeLegacyMaterial();

    const int matIdx = pDoc->m_material_table.AddMaterial(mat);
    if (matIdx < 0)
    {
        error = "Failed to create reconstruction import material.";
        return false;
    }

    int assignedCount = 0;
    for (const auto& uuid : objectIds)
    {
        const CRhinoObject* obj = pDoc->LookupObject(uuid);
        if (!obj) continue;

        ON_3dmObjectAttributes attrs = obj->Attributes();
        attrs.SetMaterialSource(ON::material_from_object);
        attrs.m_material_index = matIdx;
        if (pDoc->ModifyObjectAttributes(CRhinoObjRef(obj), attrs))
            ++assignedCount;
    }

    if (assignedCount == 0)
    {
        error = "Prepared material repair found no imported objects to assign.";
        return false;
    }

    return true;
}
```

Note: `ON_Texture::TYPE::no_texture_type` is the enum's "unset" member; the unknown-channel branch returns before `pbrType` is used, so its initializer is only a safe default. If `no_texture_type` is not the exact member name in this SDK, initialize with `ON_Texture::TYPE::bitmap_texture` instead — it is equally unreached.

- [ ] **Step 5: Run the source test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests" -v minimal`
Expected: PASS.

- [ ] **Step 6: Run the full managed suite (regression) with Rhino closed**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal`
Expected: PASS (whole suite). This deploys `Rook.rhp` to `%AppData%` — ensure Rhino is closed.

- [ ] **Step 7: Commit**

```bash
git add src/RookNative/Handlers/ImportExportHandler.cpp src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs
git commit -m "feat(reconstruction): bind material_repair maps (base_color + normal) in native import"
```

---

### Task 3: Live smoke (promotion gate — manual, no code)

**Files:**
- Modify: `docs/superpowers/specs/2026-06-24-reconstruction-pbr-material-maps-design.md` (append the smoke result)

**Interfaces:**
- Consumes: deployed managed + native plugins from Tasks 1-2. The user controls Rhino launch (do not auto-launch/close Rhino).

- [ ] **Step 1: Deploy the build locally**

Hand the user / run (Rhino closed, `python -m rook` stopped so the full deploy can mutate):

```
pwsh -File scripts/deploy-local-testing.ps1
```

If a `-PayloadOnly` deploy is used, manually copy the fresh native binary
`src/RookNative/bin/Release/x64/RookNative.rhp` over the staged one (the `-PayloadOnly`
path is known to deploy a stale staged `.rhp`).

- [ ] **Step 2: Re-run the Meshy v6 single-image submit and import**

With Rhino started by the user and `rhino_ping` returning `pong`:
1. `rhino_2d_to_3d_submit` the cat image with the Meshy model id + `allow_experimental_model: true` (boolean — reconnect `/mcp` first if the schema is stale).
2. Poll `rhino_2d_to_3d_status` to completion; `rhino_2d_to_3d_import` the package.

- [ ] **Step 3: Verify the material**

In Rhino, open the imported object's material properties:
- **Pass:** the **normal/bump slot is populated** with the staged normal map, the base-color slot still holds the base texture, and the object renders without a non-PBR display regression.
- **Fail:** normal slot empty, or base color regressed, or `material_repair_applied=false` with a `material_repair_error`.

Use `rhino_select_none` before rendering to avoid mistaking selection highlight for material color.

- [ ] **Step 4: Record the result in the spec**

Append a `## Live smoke result (2026-06-24)` section stating PASS/FAIL, which channels bound (`material_repair_applied`, the populated slots), and any `material_repair_error`. Commit:

```bash
git add docs/superpowers/specs/2026-06-24-reconstruction-pbr-material-maps-design.md
git commit -m "docs(reconstruction): record PBR normal-map live smoke result"
```

---

## Self-Review

**Spec coverage:**
- §1 `maps[]` schema → Task 1 Step 5. §2 managed builder (trigger, present-only, no rough/metallic) → Task 1 Steps 2-5. §3 native binding + channel table + strict + non-fatal → Task 2 Steps 1,4 + non-fatal assertion Step 2. §4 SDK facts → Global Constraints + Task 2 audit note. §5 deterministic tests → Task 1 Steps 1-3, Task 2 Step 2. §6 audit task → Task 2 Step 1. §7 live smoke → Task 3. All covered.

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one conditional note (`no_texture_type` fallback) is an explicit, resolved instruction, not a placeholder.

**Type consistency:** `MaterialRepair` returns `Dictionary<string,object?>?` with `maps` = `List<object?>` of `Dictionary<string,object?>` `{channel,role,path,file_name}` (Task 1) — matched by the managed assertions (Task 1 Steps 1-3) and the native reader iterating `materialRepair["maps"]` with `JsonStringOr(entry, "channel"|"path")` (Task 2 Step 4). `material_name` consistent across both. Native helper name `ApplyReconstructionMaterialRepair` unchanged; managed helper `MaterialMapEntry` is new and only referenced within `MaterialRepair`.
