# Reconstruction OBJ/MTL Texture Integrity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop misclassifying provider texture maps and emit a truthful `material_maps_missing` warning when an OBJ/MTL bundle references texture maps the package didn't deliver.

**Architecture:** Three small, local managed changes — **one role classifier** (already exists: `ClassifyTextureRole`), **one filename resolver** (extract the existing `ProviderFileNamesByRole`), **one MTL parser** (new, tiny, pure). No new service layer, no provider abstraction, no API/envelope shape change.

**Tech Stack:** C# (.NET Framework/8 multi-target companion, xUnit). Base: `origin/main` @ `c560ee88`. Worktree: `.worktrees/reconstruction-texture-integrity`, branch `feature/reconstruction-texture-integrity`.

**Spec:** `docs/superpowers/specs/2026-06-23-reconstruction-obj-mtl-texture-integrity-design.md` — implement it verbatim; read it.

## Global Constraints

- **KISS.** This is a bug fix, not a subsystem. One classifier, one resolver, one parser; everything else stays local. No new abstractions, no API field, no native/MCP/UI change.
- **Classifier-agreement invariant:** the mapper and the filename resolver MUST assign the same role to the same provider texture file (top-level `texture`, `model_urls.texture`, `texture_urls.*`), all via `FalReconstructionResultMapper.ClassifyTextureRole`.
- **"Degraded" is the warning**, not a field: `ReconstructionJobResultEnvelope` is unchanged; degraded ⇔ `warnings[]` contains `material_maps_missing`.
- **Warn-and-proceed:** never block import.
- Managed-only. Full C# suite stays green.

---

## File Structure

- `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs` — classify top-level `texture` + `model_urls.texture` via `ClassifyTextureRole`. *(T1)*
- `src/Rook/Handlers/ReconstructionOpHandler.cs` — extract `ProviderFileNamesByRole`'s body into a shared static and fix it to classify top-level `texture` + `model_urls.texture` the same way. *(T1)*
- `src/Rook/Services/Reconstruction/Fal/ObjMaterialReferences.cs` *(new)* — pure MTL `map_*` filename parser. *(T2)*
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — in `Result()`, append `material_maps_missing` using the shared resolver + parser; new warning-code constant. *(T3)*
- `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs` — *optional* static `companion_roles` cleanup. *(T4 — skip unless trivial.)*
- Tests live in the existing reconstruction test project(s) alongside the current mapper/manager/handler tests.

---

## Task 1: One classifier — mapper + resolver agree on texture roles

Make both texture-keying sites classify top-level `texture` and `model_urls.texture` via the existing `ClassifyTextureRole` (they already classify `texture_urls.*`). Extract the resolver into a single shared static so there is exactly one filename resolver.

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs`
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs`
- Test: the existing mapper test file + handler/resolver test file (locate via the current `MapArtifacts`/`ProviderFileNamesByRole` tests).

**Interfaces (produced, used by T3):**
- A shared static, e.g. `public static IReadOnlyDictionary<string,string> ProviderFileNamesByRole(JsonObject providerResultJson, Artifact package)` — role → original provider filename, classifying texture sources via `ClassifyTextureRole`. (Move the existing handler body here; the handler keeps a thin wrapper that reads the blob then calls it.)

- [ ] **Step 1: Failing tests**

In the mapper tests, add (using the literal payload from spec §1):
```csharp
[Fact]
public void MapArtifacts_TopLevelTexture_ClassifiedByFilename_NotGeneric()
{
    var json = JsonNode.Parse(LiteralHunyuanRapidResultJson); // the spec §1 provider_result_json
    var artifacts = FalReconstructionResultMapper.MapArtifacts(json!);
    Assert.Contains(artifacts, a => a.Role == "texture_metallic");
    Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.Texture);     // no generic
    Assert.DoesNotContain(artifacts, a => a.Role == "texture_base_color");                 // no diffuse
    Assert.Contains(artifacts, a => a.Role == ReconstructionFileRoles.ModelObj);
    Assert.DoesNotContain(artifacts, a => a.Role == ReconstructionFileRoles.ModelGlb);
}
```
In the resolver tests, add the agreement test:
```csharp
[Fact]
public void ProviderFileNamesByRole_TopLevelTexture_KeyedUnderClassifiedRole()
{
    var json = (JsonObject)JsonNode.Parse(LiteralHunyuanRapidResultJson)!;
    var package = PackageWithRoles("model_obj","material_mtl","texture_metallic","thumbnail"); // helper builds an Artifact with these file roles
    var names = FalReconstructionResultMapper.ProviderFileNamesByRole(json, package); // shared static
    Assert.Equal("texture_pbr_v128_metallic.png", names["texture_metallic"]);
    Assert.False(names.ContainsKey(ReconstructionFileRoles.Texture));
}
```

- [ ] **Step 2: Run → red**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~FalReconstructionResultMapper|FullyQualifiedName~ProviderFileNames"`
Expected: FAIL (generic `texture` role; resolver private/generic).

- [ ] **Step 3: Mapper — classify top-level + model_urls texture**

In `MapArtifacts`, replace the generic top-level `texture` add (line 65-66) with a classified add, and classify any `model_urls.texture`:
```csharp
var topTexture = ReadFile(root["texture"]) ?? ReadFile(Prop(root["texture_urls"], "texture"));
if (topTexture is not null)
    Add(byRole, order, ClassifyTextureRole(topTexture.FileName, topTexture.Url), topTexture);
// model_urls.texture (when present) — classify, don't leave to the model loop
var modelUrlsTexture = ReadFile(Prop(root["model_urls"], "texture"));
if (modelUrlsTexture is not null)
    Add(byRole, order, ClassifyTextureRole(modelUrlsTexture.FileName, modelUrlsTexture.Url), modelUrlsTexture);
```
(`Add` is first-writer-wins, so the top-level classified texture and any model_urls duplicate coalesce.)

- [ ] **Step 4: Resolver — extract to shared static + classify consistently**

In `FalReconstructionResultMapper.cs`, add the shared static `ProviderFileNamesByRole(JsonObject providerResultJson, Artifact package)` containing the body currently in `ReconstructionOpHandler.ProviderFileNamesByRole` (the `AddProviderFileName` loop), BUT: for the top-level `texture` and `model_urls.texture`, key under `ClassifyTextureRole(file.FileName, file.Url)` instead of the generic `ReconstructionFileRoles.Texture` (the `texture_urls.*` loop already does this — keep it). Then in `ReconstructionOpHandler.cs`, replace the private method body with a thin wrapper:
```csharp
private Dictionary<string,string> ProviderFileNamesByRole(Guid packageId, Artifact package)
{
    try {
        var json = JsonNode.Parse(File.ReadAllText(
            _store.GetBlobAbsolutePath(packageId, ReconstructionFileRoles.ProviderResultJson))) as JsonObject;
        return json is null ? new() : new(FalReconstructionResultMapper.ProviderFileNamesByRole(json, package));
    } catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException) { return new(); }
}
```
Move `AddProviderFileName`/`ReadProviderFile`/`FallbackRoleForModelUrlKey` (or the minimal subset) alongside the shared static, or keep them where they are and have the static reference them — whichever is the smaller diff. **Do not change behavior for `model_glb`/`model_obj`/`material_mtl`/`thumbnail`/`texture_urls.*`.**

- [ ] **Step 5: Run → green**

Run the Step-2 filter, then the full reconstruction subset: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~Reconstruction"`.
Expected: PASS, no regressions (existing staging/import tests still green — the metallic now keys under `texture_metallic` and still resolves to `texture_pbr_v128_metallic.png`).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "fix(reconstruction): classify top-level/model_urls texture in both mapper and resolver (T1)"
```

---

## Task 2: One parser — pure MTL `map_*` reference extractor

A tiny, dependency-free helper. Nothing else.

**Files:**
- Create: `src/Rook/Services/Reconstruction/Fal/ObjMaterialReferences.cs`
- Test: new `ObjMaterialReferencesTests.cs`

**Interfaces (produced, used by T3):**
- `public static IReadOnlyList<string> ReferencedMapFileNames(string mtlText)` — the set of filenames referenced by `map_*`/`bump`/`norm` statements, options stripped, in first-seen order, de-duplicated.

- [ ] **Step 1: Failing tests**
```csharp
[Fact]
public void ReferencedMapFileNames_ParsesAllMapsAndStripsOptions()
{
    var mtl = "newmtl Material\nKd 0.8 0.8 0.8\n"
        + "map_Kd texture_pbr_v128.png\nmap_Pm texture_pbr_v128_metallic.png\n"
        + "map_Pr texture_pbr_v128_roughness.png\nmap_Bump -bm 1.0 texture_pbr_v128_normal.png\n";
    var maps = ObjMaterialReferences.ReferencedMapFileNames(mtl);
    Assert.Equal(new[]{
        "texture_pbr_v128.png","texture_pbr_v128_metallic.png",
        "texture_pbr_v128_roughness.png","texture_pbr_v128_normal.png"}, maps);
}

[Fact]
public void ReferencedMapFileNames_IgnoresBlankCommentNonMapLines()
{
    var maps = ObjMaterialReferences.ReferencedMapFileNames("# c\n\nnewmtl M\nNs 250\nmap_Kd a.png\n");
    Assert.Equal(new[]{ "a.png" }, maps);
}
```

- [ ] **Step 2: Run → red.**

Run: `dotnet test … --filter "FullyQualifiedName~ObjMaterialReferences"`. FAIL.

- [ ] **Step 3: Implement**

Parse line-by-line: for tokens starting with `map_` (any: `map_Kd`/`map_Ka`/`map_Ks`/`map_Ns`/`map_d`/`map_Pm`/`map_Pr`/`map_Ps`/`map_Pc`/`map_Pcr`/`map_Ke`), and `bump`/`norm`, take the **last whitespace-delimited token** on the line as the filename (this naturally drops options like `-bm 1.0`, `-s 1 1 1`, `-o 0 0 0`). Trim; skip empties; de-dupe preserving order. Pure static; no I/O.

- [ ] **Step 4: Run → green.** **Step 5: Commit** — `test+feat(reconstruction): pure MTL map_* reference parser (T2)`.

---

## Task 3: Integrity warning — append `material_maps_missing` in `Result()`

Use the T1 resolver + T2 parser to compare MTL references against delivered filenames and append the warning.

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`
- Test: the existing manager `Result()`/`BuildTextureWarnings` test file.

**Interfaces:**
- Consumes: `FalReconstructionResultMapper.ProviderFileNamesByRole(json, package)` (T1), `ObjMaterialReferences.ReferencedMapFileNames(mtl)` (T2).

- [ ] **Step 1: Failing test**

Build a `reconstruction_package` artifact (mirror existing manager-result test fixtures) with roles `model_obj` + `material_mtl` (the literal 4-map MTL) + `texture_metallic` + `provider_result_json` (the literal payload), and only `texture_pbr_v128_metallic.png` delivered. Drive `Result(jobId)` and assert:
```csharp
var w = result.Warnings.Single(x => x.Code == "material_maps_missing");
Assert.Equal(true, w.Details["missing_base_color"]);
Assert.Equal(new[]{ "texture_pbr_v128.png","texture_pbr_v128_roughness.png","texture_pbr_v128_normal.png" },
             ((IEnumerable<object?>)w.Details["missing_maps"]!).Cast<string>().ToArray());
Assert.Equal("material_mtl", w.Details["material_role"]);
Assert.Equal("model_obj", w.Details["asset_role"]);
// import is not blocked: the result is still available with its artifact
Assert.True(result.ResultAvailable);
Assert.NotNull(result.ResultArtifactId);
```
Add a **no-false-positive** test: a package whose MTL's referenced maps are all delivered → `result.Warnings` has **no** `material_maps_missing`.

- [ ] **Step 2: Run → red.**

Run: `dotnet test … --filter "FullyQualifiedName~ReconstructionJobManager"`. FAIL.

- [ ] **Step 3: Implement**

Add a private helper invoked from `Result()` after the existing texture warnings are assembled (it appends, it does not replace):
```csharp
// `package` is the result artifact already loaded in Result() via _store.Get(job.ResultArtifactId.Value).
private ReconstructionWarning? BuildMaterialMapsMissingWarning(Artifact package)
{
    bool Has(string role) => package.Files.Any(f => string.Equals(f.Role, role, StringComparison.Ordinal));
    if (!Has(ReconstructionFileRoles.ModelObj) || !Has(ReconstructionFileRoles.MaterialMtl)) return null;
    string mtl;
    JsonObject? providerJson;
    try {
        mtl = File.ReadAllText(_store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.MaterialMtl));
        providerJson = JsonNode.Parse(File.ReadAllText(
            _store.GetBlobAbsolutePath(package.Id, ReconstructionFileRoles.ProviderResultJson))) as JsonObject;
    } catch (Exception ex) when (ex is IOException or JsonException or InvalidOperationException) { return null; }
    if (providerJson is null) return null;

    var delivered = new HashSet<string>(
        FalReconstructionResultMapper.ProviderFileNamesByRole(providerJson, package).Values, StringComparer.Ordinal);
    var referenced = ObjMaterialReferences.ReferencedMapFileNames(mtl);
    var missing = referenced.Where(r => !delivered.Contains(r)).ToList();
    if (missing.Count == 0) return null;

    // map_Kd is the base-color/white-mesh map. Re-parse just its filename to flag missing_base_color.
    var baseColorRef = ObjMaterialReferences.MapFileName(mtl, "map_Kd"); // small sibling helper, or scan referenced for the map_Kd line
    var missingBaseColor = baseColorRef is not null && missing.Contains(baseColorRef);

    return new ReconstructionWarning(
        "material_maps_missing",
        "The OBJ material references texture maps not present in the package; the model will import "
        + (missingBaseColor ? "without its base-color texture (it will appear untextured)." : "with some maps missing."),
        new Dictionary<string, object?>
        {
            ["missing_maps"] = missing,
            ["missing_base_color"] = missingBaseColor,
            ["material_role"] = ReconstructionFileRoles.MaterialMtl,
            ["asset_role"] = ReconstructionFileRoles.ModelObj,
        });
}
```
In `Result()`, after the existing `warnings.AddRange(BuildTextureWarnings(...))`, do `var mm = BuildMaterialMapsMissingWarning(package); if (mm is not null) warnings.Add(mm);`. Add a `MapFileName(mtl, "map_Kd")` sibling to `ObjMaterialReferences` (T2) that returns the single filename for a given map keyword, or inline the map_Kd lookup — whichever is smaller. The warning **code string is a literal/const** consistent with the existing `result_missing_texture`/`pbr_unsupported_by_model` codes; no new warning infrastructure.

- [ ] **Step 4: Run → green** (manager filter), then **full suite** `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`.

- [ ] **Step 5: Commit** — `feat(reconstruction): emit material_maps_missing when MTL refs unmet (T3)`.

---

## Task 4: *(Optional)* static manifest cleanup — skip unless trivial

Only if it falls out trivially: update `ReconstructionPackageMaterializer.cs:173-177` static `companion_roles` from `[material_mtl, texture]` to `[material_mtl]` + the texture roles, for documentation honesty. **Not required** (the handler stages dynamically). If it adds any test churn or risk, **skip it** and note the skip. No deploy/behavior dependence either way.

---

## Task 5: Deploy + live smoke (merge gate)

Managed-only → managed Release build deploys via `DeployToRhino` (all TFMs). **Close Rhino**, then `dotnet build src/Rook/Rook.csproj -c Release`; confirm the `Deployed Rook.rhp to …` messages; relaunch Rhino. No native rebuild, no MCP reload.

**Smoke:** re-open / re-run a rapid-Hunyuan job whose package matches the failing shape (or the existing package `96a7179f…` if still present). Confirm: the Result panel now shows the `material_maps_missing` warning naming the missing maps; the result is no longer silently clean; **import still proceeds** (geometry imports; white is now explained). A generation that delivers a complete texture set imports textured with no warning.

Then **REQUIRED SUB-SKILL:** superpowers:finishing-a-development-branch (verify tests, push, PR non-squash, smoke marked passed).

---

## Self-Review Notes

- **One classifier / one resolver / one parser:** `ClassifyTextureRole` (existing, now used in both keying sites), `ProviderFileNamesByRole` (extracted to one shared static), `ObjMaterialReferences` (new, pure). No other new types.
- **No API change:** `material_maps_missing` is just another `ReconstructionWarning` in the existing `warnings[]`; envelope shape untouched.
- **Spec coverage:** §2 Part 1 → T1; the MTL parser → T2; §2 Part 3/4 integrity warning → T3; §2 Part 2 optional → T4; §5 verification → T5.
- **Dependency order respected:** T3 consumes T1's shared resolver + T2's parser.
