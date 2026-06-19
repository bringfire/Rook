# Rook Reconstruction 2D-to-3D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build v1 of Rook Reconstruction 2D-to-3D: submit a Vision image artifact to fal.ai Hunyuan rapid, materialize a durable `reconstruction_package`, expose reconstruction-owned routes/MCP tools, and import the selected asset into Rhino with object-level lineage.

**Architecture:** Reconstruction is a dedicated managed domain under `src/Rook/Services/Reconstruction/`, reached through native `/reconstruction/2d-to-3d/*` routes and a dedicated `reconstruction_dispatch` callback. Managed code owns provider calls, job ledger, package materialization, import planning, and import-history recording; native code owns the Rhino `_Import`, target layer, object diff, and user-text stamping. Once `_Import` succeeds, the import is committed; managed import-history recording must be idempotent and retryable, never rollback-implied.

**Tech Stack:** C# net48/net7/net8 managed companion, xUnit, `System.Text.Json`, existing `ArtifactStore`, existing fal client/lifecycle helpers, C++ RookNative/cpp-httplib/nlohmann::json/Rhino SDK, Python MCP server/pytest.

---

## Source Spec

Implement from `docs/superpowers/specs/2026-06-19-reconstruction-2d-to-3d-design.md`.

## Preflight Decisions

- Native project files are explicit. Creating `src/RookNative/Handlers/ReconstructionHandler.cpp` and `.h` requires editing `src/RookNative/RookNative.vcxproj` and `.filters`. AGENTS.md says not to modify those project files unless explicitly asked. Before Task 9, ask the user to authorize that project-file edit. If authorization is not granted, place the native route handlers in an existing compiled native file and add a follow-up cleanup item to extract the handler when project-file edits are allowed.
- Do not run live fal jobs in unit tests. Provider calls use fakes; live smoke testing is manual and gated by the existing fal API key.
- Do not add insertion point, scale, rotation, replace, reimport, automatic preprocessing, or cost-estimate gating in v1.

## File Structure

### Managed Reconstruction Domain

- Create `src/Rook/Services/Reconstruction/ReconstructionContracts.cs`  
  Request/response DTOs, states, stages, failure/warning shapes, package roles, user-text keys.

- Create `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs`  
  Loads and filters curated model catalog entries by `enabled`, `status`, `include_experimental`, and `include_hidden`.

- Create `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`  
  Curated catalog with Hunyuan rapid stable, Meshy v6 experimental, BiRefNet experimental/manual preprocessing.

- Create `src/Rook/Services/Reconstruction/ReconstructionSourceValidator.cs`  
  Validates `source_artifact_id`, source role, artifact kind allowlist, local blob path, image extension/MIME, size, and dimensions.

- Create `src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs`  
  JSONL ledger contracts and reader/writer for durable job records.

- Create `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs`  
  Materializes provider result envelopes into `reconstruction_package` artifacts, including `provider_result_json` and initial `import_manifest`.

- Create `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs`  
  Uses existing fal queue/client patterns and `GenerationSecretKeys.FalApiKey`.

- Create `src/Rook/Handlers/ReconstructionOpHandler.cs`  
  Managed dispatch boundary for models, submit, list, status, cancel, result, import prepare, and import record.

- Modify `src/Rook/RookSubsystemRoot.cs`  
  Lazy-create reconstruction dependencies from shared `ArtifactStore` and `DpapiGenerationSecretStore`.

- Modify `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`  
  Register `reconstruction_dispatch` callback and route to `ReconstructionOpHandler`.

- Modify `src/Rook/Capabilities/CapabilityDomainStatus.cs`  
  Add managed evidence for reconstruction readiness if this file remains the managed capability source for companion evidence.

### Artifact Store

- Modify `src/Rook/Artifacts/ArtifactStore.cs`  
  Add a scoped atomic JSON blob update/replace primitive for `import_manifest`.

- Modify `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`  
  Cover successful JSON blob replacement, missing role, invalid JSON, and atomic failure behavior.

### Native

- Preferred create, pending project-file authorization:  
  `src/RookNative/Handlers/ReconstructionHandler.cpp` and `src/RookNative/Handlers/ReconstructionHandler.h`

- Required if preferred create path is authorized:  
  Modify `src/RookNative/RookNative.vcxproj` and `src/RookNative/RookNative.vcxproj.filters`.

- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.cpp` and `.h`  
  Add `HasReconstructionDispatchRegistration()` and `InvokeReconstructionDispatchWithBody()`.

- Modify `src/RookNative/RookServer.cpp`  
  Register `/reconstruction/2d-to-3d/*` routes and add `reconstruction.2d_to_3d` capability evidence.

- Modify `src/RookNative/Handlers/ImportExportHandler.cpp` only if extracting a helper for import/layer/user-text stamping is simpler than duplicating the existing pattern.

### UI

- Modify `src/Rook/UI/Vision/Resources/*` and `src/Rook/UI/Vision/VisionWebSurface.cs` only for the minimal Vision artifact "Send to 3D" affordance.

### MCP

- Modify `mcp_server/src/rook/server.py`  
  Register reconstruction tools and dispatch cases.

- Modify `mcp_server/src/rook/agent/tool_dispatcher.py`  
  Add direct bridge routes/path-param transforms for reconstruction tools.

- Modify `mcp_server/src/rook/tool_groups.py` if reconstruction tool grouping is centralized there.

- Create `mcp_server/tests/test_reconstruction_mcp_tools.py`  
  Pin tool schemas, dispatch endpoints, path-param encoding, and tool groups.

### Tests

- Create `src/Rook.Tests/Services/Reconstruction/*Tests.cs`
- Create `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`
- Create `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`
- Create `mcp_server/tests/test_reconstruction_mcp_tools.py`

---

## Task 1: ArtifactStore Scoped JSON Blob Replacement

**Files:**
- Modify: `src/Rook/Artifacts/ArtifactStore.cs`
- Modify: `src/Rook.Tests/Artifacts/ArtifactStoreTests.cs`

- [ ] **Step 1: Write failing tests for JSON blob replacement**

Add tests to `ArtifactStoreTests.cs`:

```csharp
[Fact]
public void ReplaceJsonBlob_ReplacesExistingRoleContent_AndPreservesFiles()
{
    var artifact = _store.Create(
        "reconstruction_package",
        new[]
        {
            new BlobInput("model_glb", Bytes("glb"), "glb"),
            new BlobInput("import_manifest", Bytes(@"{""schema_version"":1,""imports"":[]}"), "json"),
        });

    var updated = _store.ReplaceJsonBlob(
        artifact.Id,
        "import_manifest",
        JsonNode.Parse(@"{""schema_version"":1,""imports"":[{""import_id"":""i1""}]}")!);

    Assert.True(updated.Success);
    var loaded = _store.Get(artifact.Id);
    Assert.NotNull(loaded);
    Assert.Equal(2, loaded!.Files.Count);
    Assert.Contains(loaded.Files, f => f.Role == "import_manifest" && f.Path == "import_manifest.json");
    var json = JsonNode.Parse(File.ReadAllText(BlobPath(artifact.Id, "import_manifest.json")))!;
    Assert.Equal("i1", json["imports"]![0]!["import_id"]!.GetValue<string>());
}

[Fact]
public void ReplaceJsonBlob_RejectsMissingRole_AndLeavesArtifactUnchanged()
{
    var artifact = _store.Create("reconstruction_package", OneBlob("model_glb", "glb", "glb"));

    var result = _store.ReplaceJsonBlob(
        artifact.Id,
        "import_manifest",
        JsonNode.Parse(@"{""schema_version"":1}")!);

    Assert.False(result.Success);
    Assert.Equal(ReplaceJsonBlobResultCode.RoleNotFound, result.Code);
    Assert.DoesNotContain(_store.Get(artifact.Id)!.Files, f => f.Role == "import_manifest");
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ArtifactStoreTests.ReplaceJsonBlob" --no-restore
```

Expected: compile failure because `ReplaceJsonBlob` and result types do not exist.

- [ ] **Step 3: Implement result types and method**

Add near the existing append blob result types in `ArtifactStore.cs`:

```csharp
public enum ReplaceJsonBlobResultCode
{
    Ok,
    InvalidRole,
    ArtifactNotFound,
    ManifestReadFailed,
    RoleNotFound,
    RoleIsNotJson,
    StagedWriteFailed,
    FinalizeBlobFailed,
    ManifestReplaceFailed,
}

public sealed record ReplaceJsonBlobResult(
    bool Success,
    ReplaceJsonBlobResultCode Code,
    Artifact? Artifact,
    string? Error)
{
    public static ReplaceJsonBlobResult Succeeded(Artifact artifact)
        => new(true, ReplaceJsonBlobResultCode.Ok, artifact, null);

    public static ReplaceJsonBlobResult Fail(ReplaceJsonBlobResultCode code, string error)
        => new(false, code, null, error);
}
```

Add method to `ArtifactStore`:

```csharp
public ReplaceJsonBlobResult ReplaceJsonBlob(Guid id, string role, JsonNode content)
{
    try
    {
        ValidateRoleArg(role);
    }
    catch (Exception ex) when (ex is ArgumentException || ex is ArgumentNullException)
    {
        return ReplaceJsonBlobResult.Fail(ReplaceJsonBlobResultCode.InvalidRole, ex.Message);
    }

    if (content is null)
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.StagedWriteFailed,
            "ReplaceJsonBlob content is null.");

    var dirs = FindFinalizedDirs(id);
    if (dirs.Count == 0)
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.ArtifactNotFound,
            $"Artifact '{id:D}' not found.");
    if (dirs.Count > 1)
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.ManifestReadFailed,
            DuplicateUuid(id).Message);

    var artifactDir = dirs[0];
    Artifact existing;
    try
    {
        existing = ReadArtifact(artifactDir);
    }
    catch (Exception ex)
    {
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.ManifestReadFailed,
            ex.Message);
    }

    var file = existing.Files.FirstOrDefault(f => f.Role == role);
    if (file is null)
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.RoleNotFound,
            $"Artifact {id:D} has no blob role '{role}'.");

    if (!string.Equals(Path.GetExtension(file.Path), ".json", StringComparison.OrdinalIgnoreCase))
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.RoleIsNotJson,
            $"Blob role '{role}' is not a JSON blob.");

    var finalPath = Path.Combine(artifactDir, file.Path);
    var tmpPath = finalPath + ".tmp-" + Guid.NewGuid().ToString("N");
    try
    {
        File.WriteAllText(tmpPath, content.ToJsonString(WriteOptions), Encoding.UTF8);
        File.Replace(
            sourceFileName: tmpPath,
            destinationFileName: finalPath,
            destinationBackupFileName: null);
    }
    catch (Exception ex)
    {
        TryDeleteFile(tmpPath);
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.FinalizeBlobFailed,
            ex.Message);
    }

    try
    {
        return ReplaceJsonBlobResult.Succeeded(ReadArtifact(artifactDir));
    }
    catch (Exception ex)
    {
        return ReplaceJsonBlobResult.Fail(
            ReplaceJsonBlobResultCode.ManifestReadFailed,
            ex.Message);
    }
}
```

- [ ] **Step 4: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ArtifactStoreTests.ReplaceJsonBlob" --no-restore
```

Expected: both new tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/Artifacts/ArtifactStore.cs src/Rook.Tests/Artifacts/ArtifactStoreTests.cs
git commit -m "feat: add artifact json blob replacement"
```

---

## Task 2: Reconstruction Contracts and Catalog

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionContracts.cs`
- Create: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs`
- Create: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs`

- [ ] **Step 1: Write catalog filtering tests**

Create `ReconstructionModelCatalogTests.cs`:

```csharp
using System.Linq;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionModelCatalogTests
{
    [Fact]
    public void List_Default_ReturnsOnlyEnabledStableModels()
    {
        var catalog = ReconstructionModelCatalog.FromJson(TestCatalogJson);

        var models = catalog.List(includeExperimental: false, includeHidden: false);

        var only = Assert.Single(models);
        Assert.Equal("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", only.ModelId);
        Assert.Equal("stable", only.Status);
        Assert.True(only.Enabled);
    }

    [Fact]
    public void List_WithExperimental_IncludesMeshyAndBirefnet()
    {
        var catalog = ReconstructionModelCatalog.FromJson(TestCatalogJson);

        var ids = catalog.List(includeExperimental: true, includeHidden: false)
            .Select(m => m.ModelId)
            .ToArray();

        Assert.Contains("fal-ai/meshy/v6/image-to-3d", ids);
        Assert.Contains("fal-ai/birefnet", ids);
        Assert.DoesNotContain("dev/hidden", ids);
    }

    private const string TestCatalogJson = """
    {
      "schema_version": 1,
      "models": [
        {"model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d","provider":"fal","task":"single_image_to_3d","status":"stable","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb","model_obj","material_mtl","texture","thumbnail"],"preferred_asset_role":"model_glb","fallback_order":["model_glb","model_obj"],"supports_pbr":true,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/api"},
        {"model_id":"fal-ai/meshy/v6/image-to-3d","provider":"fal","task":"single_image_to_3d","status":"experimental","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb","thumbnail"],"preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":true,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"},
        {"model_id":"fal-ai/birefnet","provider":"fal","task":"remove_background","status":"experimental","enabled":true,"pipeline_roles":["preprocess_remove_background"],"input_types":["image_url"],"output_roles":["preprocessed_image","mask"],"preferred_asset_role":"preprocessed_image","fallback_order":["preprocessed_image"],"supports_pbr":false,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://fal.ai/models/fal-ai/birefnet/api"},
        {"model_id":"dev/hidden","provider":"fal","task":"single_image_to_3d","status":"hidden","enabled":true,"pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb"],"preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":false,"preprocessing":{"recommended":false,"required":false},"docs_url":"https://example.invalid"}
      ]
    }
    """;
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests" --no-restore
```

Expected: compile failure because reconstruction catalog types do not exist.

- [ ] **Step 3: Add contracts**

Create `ReconstructionContracts.cs` with:

```csharp
namespace Rook.Services.Reconstruction;

public static class ReconstructionArtifactKinds
{
    public const string Package = "reconstruction_package";
    public static readonly string[] DefaultSourceAllowlist =
    {
        "generated_image",
        "imported_image",
        "captured_viewport",
    };
}

public static class ReconstructionFileRoles
{
    public const string ModelGlb = "model_glb";
    public const string ModelObj = "model_obj";
    public const string MaterialMtl = "material_mtl";
    public const string Texture = "texture";
    public const string Thumbnail = "thumbnail";
    public const string SourceImage = "source_image";
    public const string PreprocessedImage = "preprocessed_image";
    public const string ProviderResultJson = "provider_result_json";
    public const string ImportManifest = "import_manifest";
}

public static class ReconstructionUserTextKeys
{
    public const string PackageId = "rook.reconstruction.package_id";
    public const string JobId = "rook.reconstruction.job_id";
    public const string ImportId = "rook.reconstruction.import_id";
    public const string AssetRole = "rook.reconstruction.asset_role";
}

public enum ReconstructionJobState
{
    Queued,
    Running,
    CancellationRequested,
    Cancelled,
    Complete,
    Error,
    Interrupted,
}

public enum ReconstructionJobStage
{
    Queued,
    Preprocessing,
    Submitting,
    Polling,
    Materializing,
    Complete,
    Error,
    Cancelled,
}

public sealed record ReconstructionWarning(
    string Code,
    string Message,
    IReadOnlyDictionary<string, object?>? Details = null);

public sealed record ReconstructionFailure(
    string Code,
    string Message,
    bool Retryable,
    string? Field,
    IReadOnlyDictionary<string, object?> Details);
```

- [ ] **Step 4: Add catalog loader and catalog JSON**

Create `ReconstructionModelCatalog.cs`:

```csharp
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionModelEntry(
    [property: JsonPropertyName("model_id")] string ModelId,
    [property: JsonPropertyName("provider")] string Provider,
    [property: JsonPropertyName("task")] string Task,
    [property: JsonPropertyName("status")] string Status,
    [property: JsonPropertyName("enabled")] bool Enabled,
    [property: JsonPropertyName("pipeline_roles")] string[] PipelineRoles,
    [property: JsonPropertyName("input_types")] string[] InputTypes,
    [property: JsonPropertyName("output_roles")] string[] OutputRoles,
    [property: JsonPropertyName("preferred_asset_role")] string PreferredAssetRole,
    [property: JsonPropertyName("fallback_order")] string[] FallbackOrder,
    [property: JsonPropertyName("supports_pbr")] bool SupportsPbr,
    [property: JsonPropertyName("preprocessing")] ReconstructionPreprocessingMetadata Preprocessing,
    [property: JsonPropertyName("docs_url")] string DocsUrl);

public sealed record ReconstructionPreprocessingMetadata(
    [property: JsonPropertyName("recommended")] bool Recommended,
    [property: JsonPropertyName("required")] bool Required);

public sealed class ReconstructionModelCatalog
{
    private readonly IReadOnlyList<ReconstructionModelEntry> _models;

    private ReconstructionModelCatalog(IReadOnlyList<ReconstructionModelEntry> models)
    {
        _models = models;
    }

    public static ReconstructionModelCatalog FromJson(string json)
    {
        var envelope = JsonSerializer.Deserialize<CatalogEnvelope>(json)
            ?? throw new InvalidOperationException("Reconstruction catalog JSON is empty.");
        return new ReconstructionModelCatalog(envelope.Models);
    }

    public IReadOnlyList<ReconstructionModelEntry> List(bool includeExperimental, bool includeHidden)
        => _models
            .Where(m => m.Enabled)
            .Where(m => includeHidden || !string.Equals(m.Status, "hidden", StringComparison.OrdinalIgnoreCase))
            .Where(m => includeExperimental || string.Equals(m.Status, "stable", StringComparison.OrdinalIgnoreCase))
            .ToArray();

    public ReconstructionModelEntry? Find(string modelId)
        => _models.FirstOrDefault(m => string.Equals(m.ModelId, modelId, StringComparison.Ordinal));

    private sealed record CatalogEnvelope(
        [property: JsonPropertyName("schema_version")] int SchemaVersion,
        [property: JsonPropertyName("models")] ReconstructionModelEntry[] Models);
}
```

Create `fal-model-catalog.json` with the same three model entries from the test fixture, excluding the hidden test model.

- [ ] **Step 5: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests" --no-restore
```

Expected: catalog tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/Rook/Services/Reconstruction src/Rook.Tests/Services/Reconstruction
git commit -m "feat: add reconstruction catalog contracts"
```

---

## Task 3: Source Artifact and Preprocessing Request Validation

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionSourceValidator.cs`
- Create: `src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionSourceValidatorTests.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionSubmitRequestParserTests.cs`

- [ ] **Step 1: Write failing parser and source validation tests**

Create tests covering:

```csharp
[Fact]
public void Parse_RejectsLocalPath()
{
    var result = ReconstructionSubmitRequestParser.Parse("""
    {"path":"C:/tmp/source.png","model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d"}
    """);

    Assert.False(result.Success);
    Assert.Equal("invalid_request", result.Failure!.Code);
    Assert.Equal("source_artifact_id", result.Failure.Field);
}

[Fact]
public void Parse_AllowsOneManualRemoveBackgroundStage()
{
    var sourceId = Guid.NewGuid();
    var result = ReconstructionSubmitRequestParser.Parse($$"""
    {
      "source_artifact_id":"{{sourceId}}",
      "source_role":"image",
      "model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
      "preprocessing_chain":[
        {"role":"remove_background","model_id":"fal-ai/birefnet","input_role":"image","output_role":"preprocessed_image","options":{}}
      ],
      "options":{"enable_pbr":true,"enable_geometry":false}
    }
    """);

    Assert.True(result.Success);
    Assert.Single(result.Request!.PreprocessingChain);
}

[Fact]
public void Parse_RejectsTwoPreprocessingStages()
{
    var sourceId = Guid.NewGuid();
    var result = ReconstructionSubmitRequestParser.Parse($$"""
    {
      "source_artifact_id":"{{sourceId}}",
      "model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
      "preprocessing_chain":[
        {"role":"remove_background","model_id":"fal-ai/birefnet"},
        {"role":"remove_background","model_id":"fal-ai/birefnet"}
      ]
    }
    """);

    Assert.False(result.Success);
    Assert.Equal("preprocessing_chain", result.Failure!.Field);
}
```

Create source validator tests for allowed kinds and rejected `reconstruction_package`.

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionSubmitRequestParserTests|FullyQualifiedName~ReconstructionSourceValidatorTests" --no-restore
```

Expected: compile failure because parser and validator do not exist.

- [ ] **Step 3: Implement request parser**

Create parser result and request records:

```csharp
public sealed record ReconstructionSubmitRequest(
    Guid SourceArtifactId,
    string SourceRole,
    string ModelId,
    IReadOnlyList<ReconstructionPreprocessingStageRequest> PreprocessingChain,
    JsonObject Options,
    bool EstimateRequested);

public sealed record ReconstructionPreprocessingStageRequest(
    string Role,
    string ModelId,
    string InputRole,
    string OutputRole,
    JsonObject Options);

public sealed record ReconstructionParseResult(
    bool Success,
    ReconstructionSubmitRequest? Request,
    ReconstructionFailure? Failure);
```

Implement `ReconstructionSubmitRequestParser.Parse(string? body)` with these validation rules:

```csharp
// Required:
// - JSON object
// - source_artifact_id GUID
// - model_id string
// Defaults:
// - source_role = "image"
// - preprocessing_chain = []
// - options = {}
// - estimate_requested = false
// Reject:
// - any "path" field
// - preprocessing_chain length > 1
// - preprocessing role other than "remove_background"
// - preprocessing model_id other than "fal-ai/birefnet"
```

- [ ] **Step 4: Implement source validator**

`ReconstructionSourceValidator.Validate(Artifact artifact, string role)` returns success only when:

```csharp
Artifact kind is one of:
- generated_image
- imported_image
- captured_viewport

Role exists in artifact.Files.
Path is relative and combines under the artifact directory.
Extension is .png, .jpg, .jpeg, or .webp.
File length is <= 8 MB.
```

Use cheap dimension validation through `System.Drawing.Image.FromFile` only for net48-compatible test paths and return a typed warning instead of failing when dimensions cannot be read.

- [ ] **Step 5: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionSubmitRequestParserTests|FullyQualifiedName~ReconstructionSourceValidatorTests" --no-restore
```

Expected: parser and validator tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/Rook/Services/Reconstruction src/Rook.Tests/Services/Reconstruction
git commit -m "feat: validate reconstruction submit sources"
```

---

## Task 4: Reconstruction Ledger and Route Response Models

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobLedgerTests.cs`

- [ ] **Step 1: Write failing ledger tests**

Create tests that append and replay records:

```csharp
[Fact]
public void AppendAndList_PreservesResultAvailabilityAndWarnings()
{
    var path = Path.Combine(Path.GetTempPath(), $"rook-reconstruction-ledger-{Guid.NewGuid():N}.jsonl");
    var ledger = new JsonlReconstructionJobLedger(path);
    var jobId = Guid.NewGuid();
    var artifactId = Guid.NewGuid();

    ledger.Append(ReconstructionJobLedgerRecord.Queued(jobId, "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", Guid.NewGuid(), "image"));
    ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, artifactId));

    var jobs = ledger.List(limit: 100);

    var only = Assert.Single(jobs.Jobs);
    Assert.Equal(jobId, only.JobId);
    Assert.Equal(ReconstructionJobState.Complete, only.State);
    Assert.Equal(artifactId, only.ResultArtifactId);
    Assert.True(only.ResultAvailable);
    Assert.Empty(jobs.Warnings);
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobLedgerTests" --no-restore
```

Expected: compile failure because ledger types do not exist.

- [ ] **Step 3: Implement ledger contracts**

Create:

```csharp
public sealed record ReconstructionJobLedgerRecord(
    Guid JobId,
    ReconstructionJobState State,
    ReconstructionJobStage Stage,
    string Provider,
    string ModelId,
    string? ProviderJobId,
    Guid SourceArtifactId,
    string SourceRole,
    IReadOnlyList<ReconstructionPreprocessingStageRecord> PreprocessingChain,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    Guid? ResultArtifactId,
    bool ResultAvailable,
    ReconstructionFailure? Error);

public sealed record ReconstructionJobListResult(
    IReadOnlyList<ReconstructionJobLedgerRecord> Jobs,
    int AppliedLimit,
    IReadOnlyList<ReconstructionWarning> Warnings);
```

Implement JSONL append/replay matching `JsonlImageJobLedger` and `JsonlVideoJobLedger`: append one canonical JSON object per transition, replay by `job_id`, list newest first, and preserve malformed-line warnings without failing the entire list.

- [ ] **Step 4: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobLedgerTests" --no-restore
```

Expected: ledger tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobLedgerTests.cs
git commit -m "feat: add reconstruction job ledger"
```

---

## Task 5: Package Materializer and Import Manifest

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionPackageMaterializerTests.cs`

- [ ] **Step 1: Write failing package tests**

Create tests with Hunyuan-shaped and Meshy-shaped provider payloads:

```csharp
[Fact]
public void Materialize_HunyuanPayload_CreatesPackageRolesAndImportManifest()
{
    var store = new ArtifactStore(NewTempRoot());
    var source = store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
    var materializer = new ReconstructionPackageMaterializer(store, new FakeFileDownloader(new Dictionary<string, byte[]>
    {
        ["https://example.test/model.glb"] = new byte[] { 10 },
        ["https://example.test/model.obj"] = new byte[] { 11 },
        ["https://example.test/material.mtl"] = new byte[] { 12 },
        ["https://example.test/texture.png"] = new byte[] { 13 },
        ["https://example.test/thumb.png"] = new byte[] { 14 },
    }));

    var artifact = materializer.Materialize(
        jobId: Guid.NewGuid(),
        sourceArtifactIds: new[] { source.Id },
        provider: "fal",
        modelId: "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
        providerResultJson: HunyuanPayload);

    Assert.Equal("reconstruction_package", artifact.Kind);
    Assert.Contains(artifact.Files, f => f.Role == "model_glb");
    Assert.Contains(artifact.Files, f => f.Role == "model_obj");
    Assert.Contains(artifact.Files, f => f.Role == "material_mtl");
    Assert.Contains(artifact.Files, f => f.Role == "texture");
    Assert.Contains(artifact.Files, f => f.Role == "thumbnail");
    Assert.Contains(artifact.Files, f => f.Role == "provider_result_json");
    Assert.Contains(artifact.Files, f => f.Role == "import_manifest");
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionPackageMaterializerTests" --no-restore
```

Expected: compile failure because materializer does not exist.

- [ ] **Step 3: Implement role mapping**

Implement:

```csharp
public interface IReconstructionFileDownloader
{
    Task<byte[]> DownloadAsync(Uri uri, CancellationToken cancellationToken);
}

public sealed class ReconstructionPackageMaterializer
{
    public Artifact Materialize(
        Guid jobId,
        IReadOnlyList<Guid> sourceArtifactIds,
        string provider,
        string modelId,
        JsonNode providerResultJson)
    {
        // Map Hunyuan:
        // - direct model_glb
        // - model_urls.glb -> model_glb
        // - model_urls.obj -> model_obj
        // - model_urls.mtl or material_mtl -> material_mtl
        // - texture -> texture
        // - thumbnail -> thumbnail
        // Map Meshy:
        // - model_glb -> model_glb
        // - model_urls entries by extension
        // - texture_urls and texture maps to texture_* roles
        // Write provider_result_json and import_manifest JSON roles.
    }
}
```

The initial `import_manifest` must contain:

```json
{
  "schema_version": 1,
  "preferred_asset": "model_glb",
  "fallback_order": ["model_glb", "model_obj"],
  "asset_bindings": {
    "model_obj": {
      "companion_roles": ["material_mtl", "texture"]
    }
  },
  "placement": {
    "mode": "document_default",
    "transform": null,
    "units_policy": "provider_default"
  },
  "imports": []
}
```

- [ ] **Step 4: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionPackageMaterializerTests" --no-restore
```

Expected: package tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/Services/Reconstruction/ReconstructionPackageMaterializer.cs src/Rook.Tests/Services/Reconstruction/ReconstructionPackageMaterializerTests.cs
git commit -m "feat: materialize reconstruction packages"
```

---

## Task 6: Fal Reconstruction Provider Adapter

**Files:**
- Create: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`

- [ ] **Step 1: Write failing provider adapter tests**

Pin the Hunyuan request shape:

```csharp
[Fact]
public async Task Submit_HunyuanRapid_UsesImageUrlAndBooleanOptions()
{
    var client = new RecordingFalQueueClient();
    var provider = new FalReconstructionProvider(client);

    await provider.SubmitAsync(new ReconstructionProviderSubmitRequest(
        ModelId: "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
        InputImageUrl: new Uri("https://rook.local/source.png"),
        Options: JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":false}")!.AsObject()),
        CancellationToken.None);

    Assert.Equal("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", client.LastModelId);
    Assert.Equal("https://rook.local/source.png", client.LastPayload["input_image_url"]!.GetValue<string>());
    Assert.True(client.LastPayload["enable_pbr"]!.GetValue<bool>());
    Assert.False(client.LastPayload["enable_geometry"]!.GetValue<bool>());
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests" --no-restore
```

Expected: compile failure because provider types do not exist.

- [ ] **Step 3: Implement adapter**

Reuse existing fal client conventions in `src/Rook/Services/Vision/Fal/FalApiClient.cs`, `FalLifecycleMapper.cs`, and `FalErrorMapper.cs`. The reconstruction provider must expose:

```csharp
public sealed record ReconstructionProviderSubmitRequest(
    string ModelId,
    Uri InputImageUrl,
    JsonObject Options);

public sealed record ReconstructionProviderSubmitResult(
    string ProviderJobId,
    JsonNode ProviderSubmitJson);

public interface IReconstructionProvider
{
    Task<ReconstructionProviderSubmitResult> SubmitAsync(
        ReconstructionProviderSubmitRequest request,
        CancellationToken cancellationToken);

    Task<JsonNode> GetResultAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken);

    Task<ProviderCancelOutcome> CancelAsync(
        string modelId,
        string providerJobId,
        CancellationToken cancellationToken);
}
```

- [ ] **Step 4: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests" --no-restore
```

Expected: provider adapter tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/Services/Reconstruction/Fal src/Rook.Tests/Services/Reconstruction/Fal
git commit -m "feat: add fal reconstruction provider"
```

---

## Task 7: Reconstruction Job Manager

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`
- Create: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

- [ ] **Step 1: Write failing manager tests**

Cover submit/list/status/result/cancel:

```csharp
[Fact]
public async Task Submit_QueuesJobAndRecordsSourceLineage()
{
    var bundle = ReconstructionJobManagerFixture.Create();
    var source = bundle.Store.Create("generated_image", new[] { new BlobInput("image", PngBytes.Valid1x1, "png") });

    var result = await bundle.Manager.SubmitAsync(new ReconstructionSubmitRequest(
        source.Id,
        "image",
        "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
        Array.Empty<ReconstructionPreprocessingStageRequest>(),
        JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":false}")!.AsObject(),
        EstimateRequested: false),
        CancellationToken.None);

    Assert.True(result.Success);
    Assert.Equal(ReconstructionJobState.Queued, result.Job!.State);
    Assert.Equal(source.Id, result.Job.SourceArtifactId);
}

[Fact]
public async Task Cancel_PollingJob_AttemptsRemoteCancelAndReturnsCancellationRequested()
{
    var bundle = ReconstructionJobManagerFixture.CreateWithPollingJob(out var jobId, out var providerJobId);

    var result = await bundle.Manager.CancelAsync(jobId, CancellationToken.None);

    Assert.Equal(ReconstructionJobState.CancellationRequested, result.State);
    Assert.True(bundle.Provider.CancelCalls.Contains(providerJobId));
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests" --no-restore
```

Expected: compile failure because manager does not exist.

- [ ] **Step 3: Implement manager**

Implement `ReconstructionJobManager` with:

```csharp
public Task<ReconstructionSubmitResult> SubmitAsync(ReconstructionSubmitRequest request, CancellationToken ct);
public ReconstructionJobListResult List(int limit);
public ReconstructionJobStatusResult Status(Guid jobId);
public Task<ReconstructionCancelResult> CancelAsync(Guid jobId, CancellationToken ct);
public ReconstructionJobResultEnvelope Result(Guid jobId);
```

Rules:

- Submit validates source artifact and catalog model before provider submission.
- Submit records `queued`, `submitting`, `polling`, `materializing`, and terminal transitions.
- Preprocessing chain is inline; v1 supports zero stages or one `remove_background` stage.
- Cancellation sets local cancellation requested first, then attempts provider cancel if an active provider job ID exists.
- Result returns `result_available:false` and warning `result_artifact_missing` when ledger points to a missing package artifact.

- [ ] **Step 4: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests" --no-restore
```

Expected: manager tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/Services/Reconstruction src/Rook.Tests/Services/Reconstruction
git commit -m "feat: add reconstruction job manager"
```

---

## Task 8: Managed ReconstructionOpHandler and Subsystem Wiring

**Files:**
- Create: `src/Rook/Handlers/ReconstructionOpHandler.cs`
- Create: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`
- Modify: `src/Rook/RookSubsystemRoot.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`

- [ ] **Step 1: Write failing handler tests**

Create tests:

```csharp
[Fact]
public async Task DispatchAsync_Models_ReturnsDefaultStableCatalog()
{
    var handler = ReconstructionOpHandlerFixture.Create();

    var response = await handler.DispatchAsync(@"{""op"":""models""}", CancellationToken.None);

    Assert.True(response.Success);
    Assert.Contains("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", response.Data!.ToJsonString());
    Assert.DoesNotContain("fal-ai/meshy/v6/image-to-3d", response.Data.ToJsonString());
}

[Fact]
public async Task DispatchAsync_SubmitMissingSource_ReturnsStructuredFailure()
{
    var handler = ReconstructionOpHandlerFixture.Create();

    var response = await handler.DispatchAsync(@"{""op"":""submit_job""}", CancellationToken.None);

    Assert.False(response.Success);
    Assert.Equal(400, response.HttpStatus);
    Assert.Equal("invalid_request", response.Data!["code"]!.GetValue<string>());
    Assert.Equal("source_artifact_id", response.Data!["field"]!.GetValue<string>());
}
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests" --no-restore
```

Expected: compile failure because handler does not exist.

- [ ] **Step 3: Implement handler dispatch**

Dispatch op names:

```text
models
submit_job
list_jobs
job_status
cancel_job
job_result
prepare_import
record_import
```

Threading:

- `models`, `list_jobs`, `job_status`, `job_result`, `prepare_import`, and `record_import` can run off UI.
- `submit_job` and `cancel_job` use async dispatch.
- Native Rhino import remains native; managed `prepare_import` returns local import plan only.

- [ ] **Step 4: Wire `RookSubsystemRoot`**

Add a lazy reconstruction subsystem, following the image/video subsystem pattern:

```csharp
internal ReconstructionOpHandler Reconstruction
    => _reconstruction ??= CreateReconstruction();
```

Use the existing shared:

```csharp
ArtifactStore
DpapiGenerationSecretStore
GenerationSecretKeys.FalApiKey
```

- [ ] **Step 5: Register managed callback**

In `NativeGhBridgeRegistrar.cs`, add:

```csharp
private static readonly NativeGhBridgeCallback ReconstructionDispatchCallback = HandleReconstructionDispatch;
```

Add the function pointer to the native registration struct in the same style as `VisionDispatch` and `BimDispatch`. Implement `HandleReconstructionDispatch` so async network ops go through `Reconstruction.DispatchAsync` and off-UI ops go through `Reconstruction.DispatchOffUi`.

- [ ] **Step 6: Run tests and confirm pass**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests" --no-restore
```

Expected: handler tests pass.

- [ ] **Step 7: Commit**

```powershell
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook/RookSubsystemRoot.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "feat: add reconstruction dispatch handler"
```

---

## Task 9: Native Reconstruction Routes and Hybrid Import

**Files:**
- Preferred create: `src/RookNative/Handlers/ReconstructionHandler.cpp`
- Preferred create: `src/RookNative/Handlers/ReconstructionHandler.h`
- Modify: `src/RookNative/RookNative.vcxproj`
- Modify: `src/RookNative/RookNative.vcxproj.filters`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/RookServer.cpp`
- Create: `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`

- [ ] **Step 1: Confirm native project-file authorization**

Ask the user:

```text
This task needs new native handler files and therefore edits to src/RookNative/RookNative.vcxproj and .filters. Do you authorize those project-file edits for the dedicated Reconstruction handler?
```

Proceed with the preferred file layout only after the user says yes.

- [ ] **Step 2: Write source scan tests**

Create `NativeReconstructionDispatchSourceTests.cs`:

```csharp
[Fact]
public void RookServer_RegistersReconstructionRoutes()
{
    var text = File.ReadAllText(Path.Combine(RepoRoot, "src", "RookNative", "RookServer.cpp"));

    Assert.Contains(@"""/reconstruction/2d-to-3d/models""", text);
    Assert.Contains(@"""/reconstruction/2d-to-3d/jobs""", text);
    Assert.Contains(@"""/reconstruction/2d-to-3d/import""", text);
}

[Fact]
public void NativeBridge_HasDedicatedReconstructionDispatch()
{
    var text = File.ReadAllText(Path.Combine(RepoRoot, "src", "RookNative", "Handlers", "GrasshopperProxyHandler.h"));

    Assert.Contains("HasReconstructionDispatchRegistration", text);
    Assert.Contains("InvokeReconstructionDispatchWithBody", text);
}
```

- [ ] **Step 3: Run tests and confirm failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests" --no-restore
```

Expected: tests fail because native reconstruction routes and bridge helpers do not exist.

- [ ] **Step 4: Add bridge callback slot**

Modify `GrasshopperProxyHandler.cpp/.h` and the registration struct to add:

```cpp
bool HasReconstructionDispatchRegistration();

ManagedCreateInvokeResult InvokeReconstructionDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);
```

Implementation mirrors `InvokeVisionDispatchWithBody`, but uses `registration.reconstruction_dispatch`.

- [ ] **Step 5: Add non-import route proxy handlers**

Preferred `ReconstructionHandler.cpp` must include route handlers:

```cpp
void HandleReconstructionModels(const httplib::Request& req, httplib::Response& res);
void HandleReconstructionSubmit(const httplib::Request& req, httplib::Response& res);
void HandleReconstructionJobsList(const httplib::Request& req, httplib::Response& res);
void HandleReconstructionStatus(const httplib::Request& req, httplib::Response& res);
void HandleReconstructionCancel(const httplib::Request& req, httplib::Response& res);
void HandleReconstructionResult(const httplib::Request& req, httplib::Response& res);
```

Each handler injects an `op` field and forwards to `InvokeReconstructionDispatchWithBody`. Path-param handlers inject `job_id` from `req.matches[1]`. Jobs list folds `?limit=N` using the canonical integer-string rule already used by video routes.

- [ ] **Step 6: Add hybrid import handler**

Implement `HandleReconstructionImport`:

1. Parse body with `package_id`, optional `targetLayer`, optional `assetRole`.
2. Dispatch managed `prepare_import` with body fields.
3. If prepare fails, return managed response as-is.
4. Read `data.import_plan.asset_path`, `asset_role`, `package_id`, `job_id`, and `import_id`.
5. Run `_Import` on the main thread with `ObjectDiffTracker`.
6. Move new objects to `targetLayer` when provided.
7. Stamp user text keys on every imported object:
   - `rook.reconstruction.package_id`
   - `rook.reconstruction.job_id`
   - `rook.reconstruction.import_id`
   - `rook.reconstruction.asset_role`
8. Dispatch managed `record_import` with `import_id`, `package_id`, `job_id`, `asset_role`, `imported_ids`, and association status.
9. If `record_import` fails, return `success:false` with code `import_history_failed` and include `imported_ids`.

Do not attempt to delete imported objects after `_Import` succeeds.

- [ ] **Step 7: Register routes and capability evidence**

Modify `RookServer.cpp` route registration:

```cpp
m_server->Get("/reconstruction/2d-to-3d/models", Rook::Handlers::HandleReconstructionModels);
m_server->Post("/reconstruction/2d-to-3d/jobs", Rook::Handlers::HandleReconstructionSubmit);
m_server->Get("/reconstruction/2d-to-3d/jobs", Rook::Handlers::HandleReconstructionJobsList);
m_server->Get(R"(/reconstruction/2d-to-3d/jobs/([^/]+))", Rook::Handlers::HandleReconstructionStatus);
m_server->Post(R"(/reconstruction/2d-to-3d/jobs/([^/]+)/cancel)", Rook::Handlers::HandleReconstructionCancel);
m_server->Get(R"(/reconstruction/2d-to-3d/jobs/([^/]+)/result)", Rook::Handlers::HandleReconstructionResult);
m_server->Post("/reconstruction/2d-to-3d/import", Rook::Handlers::HandleReconstructionImport);
```

Add `/capabilities` domain `reconstruction.2d_to_3d` with callback evidence `reconstructionDispatch`.

- [ ] **Step 8: Run source tests and build**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests" --no-restore
```

Expected: source scan tests pass.

Run native build only on this Windows machine with Rhino/MFC toolchain:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native build succeeds.

- [ ] **Step 9: Commit**

```powershell
git add src/RookNative src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs
git commit -m "feat: add native reconstruction routes"
```

---

## Task 10: MCP Reconstruction Tools

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/tool_groups.py`
- Create: `mcp_server/tests/test_reconstruction_mcp_tools.py`

- [ ] **Step 1: Write failing MCP tests**

Create tests:

```python
import pytest
from rook import server

@pytest.mark.asyncio
async def test_reconstruction_models_dispatches_get(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"models": []}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    await server.call_tool("rhino_2d_to_3d_models", {})

    assert calls == [("/reconstruction/2d-to-3d/models", "GET", None)]

@pytest.mark.asyncio
async def test_reconstruction_status_encodes_job_id(monkeypatch):
    calls = []

    async def fake_call_rhino(endpoint, method="GET", data=None, port=None):
        calls.append((endpoint, method, data))
        return {"success": True, "data": {"job": {}}}

    monkeypatch.setattr(server, "call_rhino", fake_call_rhino)

    await server.call_tool("rhino_2d_to_3d_status", {"job_id": "bad?x=1"})

    assert calls[0][0] == "/reconstruction/2d-to-3d/jobs/bad%3Fx%3D1"
```

- [ ] **Step 2: Run tests and confirm failure**

Run:

```powershell
pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```

Expected: failure because tools do not exist.

- [ ] **Step 3: Add MCP tool schemas**

Add tools:

```text
rhino_2d_to_3d_models
rhino_2d_to_3d_submit
rhino_2d_to_3d_jobs
rhino_2d_to_3d_status
rhino_2d_to_3d_cancel
rhino_2d_to_3d_result
rhino_2d_to_3d_import
```

Tool schemas must mirror the native route request shapes from the spec. `rhino_2d_to_3d_submit` must require `source_artifact_id`; it must not accept local paths.

- [ ] **Step 4: Add dispatch cases**

Add `_encode_reconstruction_job_id` mirroring `_encode_video_job_id`. Dispatch:

```python
"rhino_2d_to_3d_models" -> GET /reconstruction/2d-to-3d/models
"rhino_2d_to_3d_submit" -> POST /reconstruction/2d-to-3d/jobs
"rhino_2d_to_3d_jobs" -> GET /reconstruction/2d-to-3d/jobs?limit=N
"rhino_2d_to_3d_status" -> GET /reconstruction/2d-to-3d/jobs/{job_id}
"rhino_2d_to_3d_cancel" -> POST /reconstruction/2d-to-3d/jobs/{job_id}/cancel
"rhino_2d_to_3d_result" -> GET /reconstruction/2d-to-3d/jobs/{job_id}/result
"rhino_2d_to_3d_import" -> POST /reconstruction/2d-to-3d/import
```

- [ ] **Step 5: Run tests and confirm pass**

Run:

```powershell
pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```

Expected: MCP reconstruction tests pass.

- [ ] **Step 6: Commit**

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/tool_groups.py mcp_server/tests/test_reconstruction_mcp_tools.py
git commit -m "feat: add reconstruction mcp tools"
```

---

## Task 11: Minimal Vision "Send to 3D" UI

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/*`
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`
- Create or modify: `src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs` only if a source scan is needed for route names.

- [ ] **Step 1: Locate artifact action component**

Run:

```powershell
rg -n "approve|consume|artifact|Vision artifact|action" src/Rook/UI/Vision/Resources src/Rook/UI/Vision
```

Expected: identify the Vision artifact row/action code.

- [ ] **Step 2: Add UI action**

Add a compact action labeled `Send to 3D` or `Reconstruct in 3D` on image-producing artifacts only. The action calls:

```json
{
  "op": "submit_job",
  "source_artifact_id": "<artifact id>",
  "source_role": "image",
  "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
  "preprocessing_chain": [],
  "options": {
    "enable_pbr": true,
    "enable_geometry": false
  }
}
```

Route through `/reconstruction/2d-to-3d/jobs`, not `vision_dispatch`.

- [ ] **Step 3: Add status/result/import UI states**

Expose:

- job id
- state/stage
- package id
- thumbnail role when present
- import button calling `/reconstruction/2d-to-3d/import`

Do not add model selection, preprocessing editor, cost gate, placement controls, or full Reconstruction panel.

- [ ] **Step 4: Manual browser verification**

Run managed build:

```powershell
dotnet build src/Rook/Rook.csproj -f net48
```

Open Rhino/Rook Vision panel and verify:

- artifact row has `Send to 3D`
- submit shows job status
- complete result exposes import action
- failed submit shows structured error text

- [ ] **Step 5: Commit**

```powershell
git add src/Rook/UI/Vision src/Rook.Tests
git commit -m "feat: add send to 3d vision affordance"
```

---

## Task 12: End-to-End Contract Validation

**Files:**
- Modify tests created in earlier tasks only when verification reveals contract mismatches.

- [ ] **Step 1: Run managed reconstruction tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore
```

Expected: all reconstruction managed tests pass.

- [ ] **Step 2: Run MCP reconstruction tests**

Run:

```powershell
pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q
```

Expected: all MCP reconstruction tests pass.

- [ ] **Step 3: Run native build**

Run:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native Debug x64 build succeeds.

- [ ] **Step 4: Live manual validation in Rhino**

With Rhino running and fal key configured:

1. Create or import a small PNG/JPEG/WebP Vision artifact.
2. Call `GET /reconstruction/2d-to-3d/models`.
3. Call `POST /reconstruction/2d-to-3d/jobs` with `source_artifact_id`.
4. Poll `GET /reconstruction/2d-to-3d/jobs/{job_id}`.
5. Call `GET /reconstruction/2d-to-3d/jobs/{job_id}/result`.
6. Call `POST /reconstruction/2d-to-3d/import` with `targetLayer:"Rook::Reconstruction"`.
7. Inspect imported Rhino objects for user text keys:
   - `rook.reconstruction.package_id`
   - `rook.reconstruction.job_id`
   - `rook.reconstruction.import_id`
   - `rook.reconstruction.asset_role`
8. Force or simulate `record_import` failure and verify response code `import_history_failed` includes `imported_ids`.

- [ ] **Step 5: Commit verification fixes**

If validation required fixes:

Stage only the files modified by the verification fix. Use `git diff --name-only` to list them before staging, then commit:

```powershell
git diff --name-only
git add docs/superpowers/specs/2026-06-19-reconstruction-2d-to-3d-design.md src/Rook/Services/Reconstruction src/Rook/Handlers/ReconstructionOpHandler.cs src/RookNative/Handlers/ReconstructionHandler.cpp src/RookNative/Handlers/ReconstructionHandler.h mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/tests/test_reconstruction_mcp_tools.py
git commit -m "fix: align reconstruction contract validation"
```

If validation changed a subset of those files, stage only that subset. If validation required no fixes, do not create an empty commit.

---

## Self-Review

Spec coverage:

- Dedicated Reconstruction domain: Tasks 2, 8, 9, 10.
- Hunyuan primary model and Meshy/BiRefNet catalog entries: Task 2.
- Source artifact-only submit and source allowlist/content validation: Task 3.
- Inline manual preprocessing stage: Task 3 and Task 7.
- Durable ledger with states/stages and deleted package behavior: Task 4 and Task 7.
- Package artifact with provider result JSON and import manifest: Task 5.
- Scoped `import_manifest` JSON update/replace primitive: Task 1 and Task 9.
- fal provider with shared fal key: Task 6 and Task 8.
- Native reconstruction routes and capability domain: Task 9.
- Hybrid import route with no rollback after `_Import`: Task 9 and Task 12.
- MCP parity: Task 10.
- Minimal Vision "Send to 3D" affordance: Task 11.

Validation commands:

- Managed: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" --no-restore`
- MCP: `pytest mcp_server/tests/test_reconstruction_mcp_tools.py -q`
- Native: `cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"`
- Live: Rhino manual flow in Task 12.
