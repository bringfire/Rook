# All Reconstruction PBR Maps Binding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind all four mapper-produced reconstruction PBR maps (`base_color`, `normal`, `roughness`, `metallic`) into the repaired Rhino material.

**Architecture:** Managed `MaterialRepair` emits all four staged roles into `material_repair.maps[]` in fixed order, present-only. Native `ApplyReconstructionMaterialRepair` binds each channel via a small file-local `{channel, ON_Texture::TYPE, treatAsLinear, legacyMirror}` lookup table replacing the existing `if/else` chain. No schema change; strict/non-fatal semantics from #349 preserved.

**Tech Stack:** C# (.NET, `src/Rook`, `src/Rook.Tests`, xUnit), C++ (`src/RookNative`, OpenNURBS / Rhino 8 SDK), JSON via `System.Text.Json.Nodes` (managed) / `nlohmann::json` (native).

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-24-reconstruction-all-pbr-maps-design.md`. Every task conforms to it.
- **Four channels only:** `base_color`, `normal`, `roughness`, `metallic`. No AO/emissive (mapper doesn't produce them).
- **Fixed order:** base_color → normal → roughness → metallic.
- **Present-only:** a channel appears only when `HasRole(package, "texture_<x>")`. base_color stays the repair trigger (no base color → `MaterialRepair` returns `null`).
- **No schema change:** `material_repair.maps[]` entry shape stays `{channel, role, path, file_name}`.
- **Color space (SDK-confirmed):** base_color `treatAsLinear=false` (sRGB); normal/roughness/metallic `treatAsLinear=true` (data, used raw).
- **Native table is file-local** to `ImportExportHandler.cpp` — no exported types, no broad abstraction.
- **Strict + non-fatal:** non-object entry / unknown channel / missing file → `material_repair_error`, repair returns `false`; import still succeeds (`wr.success = associated`).
- **Legacy bitmap mirror** (base_color only) is added **after** `SynchronizeLegacyMaterial()`.
- **No `.vcxproj`/`.vcxproj.filters` edits.** No Python/MCP/UI change. Do not claim a native build.
- **Verified enum values:** `pbr_base_color_texture=1`, `pbr_bump_texture=2`, `pbr_metallic_texture=13`, `pbr_roughness_texture=16`.
- **Managed test side effect:** `dotnet test` on `src/Rook.Tests` deploys `Rook.rhp` into `%AppData%`; run with Rhino closed.

---

### Task 1: Managed — emit roughness + metallic maps

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`MaterialRepair`, ~the `if (HasRole(... "texture_normal"))` block)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Consumes: existing `MaterialMapEntry(Artifact, string channel, string role, IReadOnlyDictionary<string,string>)`, `HasRole(Artifact, string)`, `BaseColorTextureRole(Artifact)`.
- Produces: `MaterialRepair` now appends `roughness` (role `texture_roughness`) and `metallic` (role `texture_metallic`) after `normal`, present-only, in that order. `maps` remains a `List<object?>` of `Dictionary<string,object?>`.

- [ ] **Step 1: Write the failing test (all four maps, in order)**

Add to `ReconstructionOpHandlerTests.cs` (after `DispatchOffUi_PrepareImport_AppendsNormalMapWhenPresent`, ~line 233):

```csharp
    [Fact]
    public async Task DispatchOffUi_PrepareImport_AppendsAllPbrMapsWhenPresent()
    {
        var fixture = CreateFixture();
        fixture.Downloader.Files["https://example.test/m.glb"] = new byte[] { 1, 2, 3 };
        fixture.Downloader.Files["https://example.test/base.png"] = new byte[] { 4, 5, 6 };
        fixture.Downloader.Files["https://example.test/normal.png"] = new byte[] { 7, 8, 9 };
        fixture.Downloader.Files["https://example.test/rough.png"] = new byte[] { 10, 11, 12 };
        fixture.Downloader.Files["https://example.test/metal.png"] = new byte[] { 13, 14, 15 };
        var package = await BuildPackageAsync(fixture, JsonNode.Parse("""
        {
          "model_glb": {"url": "https://example.test/m.glb"},
          "texture_urls": [
            {
              "base_color": {"url": "https://example.test/base.png",   "file_name": "texture_0.png"},
              "normal":     {"url": "https://example.test/normal.png", "file_name": "texture_0_normal.png"},
              "roughness":  {"url": "https://example.test/rough.png",  "file_name": "texture_0_roughness.png"},
              "metallic":   {"url": "https://example.test/metal.png",  "file_name": "texture_0_metallic.png"}
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
        Assert.Equal(4, maps.Count);

        var expected = new[]
        {
            ("base_color", "texture_base_color"),
            ("normal",     "texture_normal"),
            ("roughness",  "texture_roughness"),
            ("metallic",   "texture_metallic"),
        };
        for (var i = 0; i < expected.Length; i++)
        {
            var entry = Assert.IsType<Dictionary<string, object?>>(maps[i]);
            Assert.Equal(expected[i].Item1, entry["channel"]);
            Assert.Equal(expected[i].Item2, entry["role"]);
        }
    }
```

The existing `DispatchOffUi_PrepareImport_AppendsNormalMapWhenPresent` (metallic/roughness `null` → 2 entries) is left unchanged; it now doubles as the present-only/partial test. `NoBaseColor` is unchanged.

- [ ] **Step 2: Run the new test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AppendsAllPbrMapsWhenPresent" -v minimal`
Expected: FAIL on `Assert.Equal(4, maps.Count)` — actual 2 (roughness/metallic not emitted yet).

- [ ] **Step 3: Add the roughness + metallic appends**

In `ReconstructionOpHandler.cs`, find the normal append in `MaterialRepair`:

```csharp
            if (HasRole(package, "texture_normal"))
                maps.Add(MaterialMapEntry(package, "normal", "texture_normal", providerFileNames));
```

Replace it with (adds roughness + metallic after normal, fixed order):

```csharp
            if (HasRole(package, "texture_normal"))
                maps.Add(MaterialMapEntry(package, "normal", "texture_normal", providerFileNames));
            if (HasRole(package, "texture_roughness"))
                maps.Add(MaterialMapEntry(package, "roughness", "texture_roughness", providerFileNames));
            if (HasRole(package, "texture_metallic"))
                maps.Add(MaterialMapEntry(package, "metallic", "texture_metallic", providerFileNames));
```

- [ ] **Step 4: Run the reconstruction managed tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests" -v minimal`
Expected: PASS (new 4-map test, the 2-entry partial test, and NoBaseColor all green).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "feat(reconstruction): emit roughness + metallic maps in material_repair.maps[]"
```

---

### Task 2: Native — file-local channel table binds all four

**Files:**
- Modify: `src/RookNative/Handlers/ImportExportHandler.cpp` (`ApplyReconstructionMaterialRepair`, ~lines 224-335)
- Test: `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs` (`ReconstructionImport_AppliesPreparedMaterialRepairToImportedObjects`, ~lines 175-230)

**Interfaces:**
- Consumes: `materialRepair["maps"]` entries `{channel, path}` from Task 1.
- Produces: a file-local `struct PbrChannelBinding { const char* channel; ON_Texture::TYPE type; bool treatAsLinear; bool legacyMirror; }` + `static const PbrChannelBinding kPbrChannelBindings[]` (four rows). The loop resolves the channel via table lookup (`binding`), errors on no match, and binds `binding->type` / `binding->treatAsLinear` / `binding->legacyMirror`.

- [ ] **Step 1: Update the source-assertion test to require exact table tuples**

In `NativeReconstructionDispatchSourceTests.cs`, in `ReconstructionImport_AppliesPreparedMaterialRepairToImportedObjects`, replace these two lines (the per-branch linear assertions, ~lines 197-200):

```csharp
        // normal channel binds linearly: the branch sets treatAsLinear = true and the
        // ON_Texture field is assigned from it.
        Assert.Contains("treatAsLinear = true", text);
        Assert.Contains("m_bTreatAsLinear = treatAsLinear", text);
```

with the exact-tuple table assertions (whitespace-insensitive) + the four PBR types + the binding-field assignment:

```csharp
        // The file-local channel table encodes the exact per-channel tuples
        // {channel, ON_Texture::TYPE, treatAsLinear, legacyMirror}. Compare whitespace-stripped
        // so source formatting is irrelevant.
        var compact = System.Text.RegularExpressions.Regex.Replace(text, @"\s+", "");
        Assert.Contains("{\"base_color\",ON_Texture::TYPE::pbr_base_color_texture,false,true}", compact);
        Assert.Contains("{\"normal\",ON_Texture::TYPE::pbr_bump_texture,true,false}", compact);
        Assert.Contains("{\"roughness\",ON_Texture::TYPE::pbr_roughness_texture,true,false}", compact);
        Assert.Contains("{\"metallic\",ON_Texture::TYPE::pbr_metallic_texture,true,false}", compact);
        Assert.Contains("ON_Texture::TYPE::pbr_roughness_texture", text);
        Assert.Contains("ON_Texture::TYPE::pbr_metallic_texture", text);
        Assert.Contains("m_bTreatAsLinear = binding->treatAsLinear", text);
```

Leave all other assertions in the method unchanged (maps iteration, `pbr_base_color_texture`, `pbr_bump_texture`, `CreateFromFullPath`, `ToPhysicallyBased`, unknown-channel, non-object-entry, assignment, `material_repair_applied`, `wr.success = associated`, and the synchronize-before-legacy-bitmap ordering block below them).

- [ ] **Step 2: Run the source test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests.ReconstructionImport_AppliesPreparedMaterialRepairToImportedObjects" -v minimal`
Expected: FAIL — the compact table rows / `pbr_roughness_texture` / `pbr_metallic_texture` / `binding->treatAsLinear` are not present yet.

- [ ] **Step 3: Add the file-local table above the function**

In `ImportExportHandler.cpp`, immediately **above** `static bool ApplyReconstructionMaterialRepair(` (line ~224), insert:

```cpp
// File-local PBR channel binding table for reconstruction material repair. Each row maps a
// material_repair.maps[] channel to its Rhino PBR texture slot, color-space treatment
// (base color = sRGB; normal/roughness/metallic = linear data maps), and whether it also gets
// a legacy bitmap_texture mirror for non-PBR display modes (base color only).
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

- [ ] **Step 4: Replace the `if/else` channel chain with a table lookup**

In `ApplyReconstructionMaterialRepair`, replace this block (the `pbrType`/`treatAsLinear`/`mirrorAsLegacyBitmap` locals + `if/else`, ~lines 278-297):

```cpp
        ON_Texture::TYPE pbrType = ON_Texture::TYPE::no_texture_type;
        bool treatAsLinear = false;
        bool mirrorAsLegacyBitmap = false;
        if (channel == "base_color")
        {
            pbrType = ON_Texture::TYPE::pbr_base_color_texture;
            treatAsLinear = false;        // sRGB color
            mirrorAsLegacyBitmap = true;  // show in non-PBR display modes
        }
        else if (channel == "normal")
        {
            pbrType = ON_Texture::TYPE::pbr_bump_texture;
            treatAsLinear = true;         // normal vectors sample linearly
            mirrorAsLegacyBitmap = false;
        }
        else
        {
            error = "Unknown material repair channel: " + channel;
            return false;
        }
```

with the table lookup:

```cpp
        const PbrChannelBinding* binding = nullptr;
        for (const auto& candidate : kPbrChannelBindings)
        {
            if (channel == candidate.channel)
            {
                binding = &candidate;
                break;
            }
        }
        if (binding == nullptr)
        {
            error = "Unknown material repair channel: " + channel;
            return false;
        }
```

- [ ] **Step 5: Bind from the resolved `binding`**

In the same function, replace the `ON_Texture` build + legacy-mirror capture (~lines 318-327):

```cpp
        ON_Texture tex;
        tex.m_image_file_reference = ON_FileReference::CreateFromFullPath(
            static_cast<const wchar_t*>(texturePathW), false, true);
        tex.m_type = pbrType;
        tex.m_bTreatAsLinear = treatAsLinear;
        tex.m_bOn = true;
        pbr->AddTexture(tex);

        if (mirrorAsLegacyBitmap)
            baseColorLegacyPath = texturePath;
```

with the `binding->` form:

```cpp
        ON_Texture tex;
        tex.m_image_file_reference = ON_FileReference::CreateFromFullPath(
            static_cast<const wchar_t*>(texturePathW), false, true);
        tex.m_type = binding->type;
        tex.m_bTreatAsLinear = binding->treatAsLinear;
        tex.m_bOn = true;
        pbr->AddTexture(tex);

        if (binding->legacyMirror)
            baseColorLegacyPath = texturePath;
```

Everything else in the function (the `maps` array guard, per-entry `is_object`/empty/`ValidateFilePath`/`fs::exists` checks, `SynchronizeLegacyMaterial()` then the post-sync legacy bitmap add, material assignment, non-fatal result) stays exactly as is.

- [ ] **Step 6: Run the source test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests" -v minimal`
Expected: PASS.

- [ ] **Step 7: Run the full managed suite (regression), Rhino closed**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal`
Expected: PASS (whole suite). Deploys `Rook.rhp` to `%AppData%` — ensure Rhino is closed.

- [ ] **Step 8: Commit**

```bash
git add src/RookNative/Handlers/ImportExportHandler.cpp src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs
git commit -m "feat(reconstruction): bind all four PBR maps via file-local native channel table"
```

---

### Task 3: Live smoke (gate — no paid run, manual)

**Files:**
- Modify: `docs/superpowers/specs/2026-06-24-reconstruction-all-pbr-maps-design.md` (append the smoke result)

**Interfaces:**
- Consumes: deployed managed + native plugins from Tasks 1-2. The user controls Rhino launch (do not auto-launch/close Rhino).

- [ ] **Step 1: Verify the captured package still exists (precondition)**

Run:

```bash
ls "$APPDATA/Rook/artifacts/2026-06-24/d61c3f06-0c85-4e01-a84c-56bd5439a966" 2>/dev/null \
  | grep -E "texture_(base_color|normal|roughness|metallic)\.png" || echo "MISSING"
```

Expected: all four `texture_*.png` present. **If `MISSING` (package gone): STOP and decide with the user whether to rerun a paid Meshy job** (`fal-ai/meshy/v6/image-to-3d`, `options: { should_texture: true, enable_pbr: true }`, source `866573ea`). Do NOT substitute a different package or smoke fewer than four channels.

- [ ] **Step 2: Deploy the build locally (Rhino closed, rook python stopped)**

Hand the user / run:

```
pwsh -File scripts/deploy-local-testing.ps1
```

Verify the fresh native `.rhp` carries the new code (grep the deployed binary for a new literal):

```bash
grep -a -c "pbr_roughness_texture" "$APPDATA/McNeel/Rhinoceros/8.0/Plug-ins/RookNative/RookNative.rhp" 2>/dev/null || true
```

(Compiled enum names are not string literals; instead confirm freshness via the managed/native deploy log "Build succeeded" + the deployed-vs-source check. The authoritative proof is Step 4's `GetTextures()` dump.)

- [ ] **Step 3: Re-import the staged package (user launches Rhino first)**

With Rhino started by the user and `rhino_ping` → `pong`:

```
rhino_2d_to_3d_import package_id=d61c3f06-0c85-4e01-a84c-56bd5439a966
```

Then `rhino_select_none` to avoid selection-highlight confusion.

- [ ] **Step 4: Dump the material textures (authoritative check)**

Run via `rhino_execute`:

```python
import scriptcontext as sc
doc = sc.doc
mat = None
for m in doc.Materials:
    if m.Name and m.Name.startswith("Rook Reconstruction"):
        mat = m
        break
out = []
if mat is None:
    out.append("MATERIAL NOT FOUND")
else:
    out.append("Material: %s" % mat.Name)
    for t in mat.GetTextures():
        try:
            fn = t.FileReference.FullPath if t.FileReference else ""
        except:
            fn = ""
        out.append("  type=%s on=%s linear=%s file=%s" % (
            str(t.TextureType), str(t.Enabled), str(getattr(t, "TreatAsLinear", "n/a")), fn))
    out.append("PhysicallyBased: %s" % (mat.PhysicallyBased is not None))
print("\n".join(out))
```

**Pass criteria:** base color is bound (and non-PBR display intact — Rhino may expose both the PBR base-color texture and the legacy bitmap mirror; do not require a single specific row); `normal`, `roughness`, and `metallic` are each bound to their PBR slot with `linear=True`; `PhysicallyBased: True`; the import reported `material_repair_applied: true` with no `material_repair_error`.

- [ ] **Step 5: Record the result in the spec**

Append a `## Live smoke result (YYYY-MM-DD)` section stating PASS/FAIL with the `GetTextures()` rows (the four bound slots + linear flags). Commit:

```bash
git add docs/superpowers/specs/2026-06-24-reconstruction-all-pbr-maps-design.md
git commit -m "docs(reconstruction): record all-PBR-maps live smoke result"
```

---

## Self-Review

**Spec coverage:**
- §1 managed four-map emission (fixed order, present-only, base_color trigger) → Task 1. §2 native file-local table → Task 2 Steps 3-5. §3 color space (table tuples) → Task 2 table + assertions. §4 strict/non-fatal → unchanged code + retained assertions. §Testing managed (4-map order, partial 2-entry, no-base-color) → Task 1 + retained tests; native exact tuples → Task 2 Step 1. §Live smoke precondition + four-slot dump → Task 3. All covered.

**Placeholder scan:** No TBD/TODO; every code step shows full code. Step 2's freshness note is an explicit instruction (authoritative proof deferred to Step 4's dump), not a placeholder.

**Type consistency:** Managed `MaterialMapEntry(package, channel, role, providerFileNames)` calls match the existing signature; `maps` stays `List<object?>`. Native `PbrChannelBinding` fields (`channel`/`type`/`treatAsLinear`/`legacyMirror`) match between the table (Task 2 Step 3), the lookup (Step 4: `binding`), the bind (Step 5: `binding->type`/`binding->treatAsLinear`/`binding->legacyMirror`), and the source assertions (Step 1: compact rows + `m_bTreatAsLinear = binding->treatAsLinear`). The removed `treatAsLinear = true` / `m_bTreatAsLinear = treatAsLinear` assertions are exactly the lines deleted in Steps 4-5.
