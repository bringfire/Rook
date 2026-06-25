# Package → Hunyuan Smart Topology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `submit_mesh_job` op that takes an existing `reconstruction_package`, uploads its local `model_glb` to fal, runs Hunyuan Smart Topology, and materializes the result as a new package (parent = source package), importable through the existing path.

**Architecture:** New package-mesh front (parser → mesh submit gate → mesh source validator → ledger start → GLB upload) funnels into a shared, source-agnostic `SubmitResolvedAsync` tail extracted from `SubmitCoreAsync`. Provider payload, result mapper, materializer, poll loop, and import are reused unchanged. A small native route + MCP tool expose the op.

**Tech Stack:** C# (.NET, `src/Rook`, `src/Rook.Tests`, xUnit), C++ (`src/RookNative`, route registration only), Python MCP (`mcp_server`), JSON via `System.Text.Json.Nodes`.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-06-24-reconstruction-mesh-smart-topology-design.md`. Every task conforms.
- **Always upload the package's local `model_glb`** (`model/gltf-binary`); no provider-URL reuse; no HEAD/freshness probing.
- **Deterministic source preconditions fail pre-ledger; upload failures record a failed job** (parity with image path).
- **`input_file_type` fixed `"glb"`**, injected after options validation (not a user option; unknown options already rejected).
- **Source-front gates both ways:** image submit requires `image_url` input; mesh submit requires `model_url` input or `input.mode == "single_model"`.
- **Ledger:** mesh job records `SourceArtifactId = sourcePackageId`, `SourceRole = "model_glb"`, `task = "mesh_to_mesh_topology"`.
- **Lineage:** new package `ParentIds = [sourcePackageId]` (via existing materializer).
- **Catalog entry `status: experimental`**, shipped behind `allow_experimental_model`; promote to `stable` after the live smoke.
- **No native geometry change** — only a route registration (endpoint + handler + soft allowlist). **A native build is required** for deploy/smoke.
- **Managed test side effect:** `dotnet test` on `src/Rook.Tests` deploys `Rook.rhp` into `%AppData%`; run with Rhino closed.
- **Verbatim names:** new op `submit_mesh_job`; new MCP tool `rhino_3d_to_3d_submit`; new native route `POST /reconstruction/3d-to-3d/jobs`; model id `fal-ai/hunyuan-3d/v3.1/smart-topology`.

---

### Task 1: Mesh submit request + strict parser

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionMeshSubmitRequestParser.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSubmitRequestParserTests.cs`

**Interfaces:**
- Produces: `ReconstructionMeshSubmitRequest { Guid SourcePackageId; string ModelId; JsonObject Options; bool AllowExperimentalModel }` and `ReconstructionMeshSubmitRequestParser.Parse(string? body) → ReconstructionMeshParseResult(bool Success, ReconstructionMeshSubmitRequest? Request, ReconstructionFailure? Failure)`.
- Consumes: `ReconstructionFailure` (existing public DTO).

- [ ] **Step 1: Write the failing tests**

Create `src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSubmitRequestParserTests.cs`:

```csharp
using System;
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionMeshSubmitRequestParserTests
{
    private const string Pkg = "11111111-1111-1111-1111-111111111111";

    [Fact]
    public void Parse_ValidBody_PopulatesRequest()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse(
            $"{{\"source_package_id\":\"{Pkg}\",\"model_id\":\"fal-ai/hunyuan-3d/v3.1/smart-topology\"," +
            "\"options\":{\"face_level\":\"high\"},\"allow_experimental_model\":true}");

        Assert.True(result.Success, result.Failure?.Message);
        Assert.Equal(Guid.Parse(Pkg), result.Request!.SourcePackageId);
        Assert.Equal("fal-ai/hunyuan-3d/v3.1/smart-topology", result.Request!.ModelId);
        Assert.True(result.Request!.AllowExperimentalModel);
        Assert.Equal("high", result.Request!.Options["face_level"]!.GetValue<string>());
    }

    [Fact]
    public void Parse_MissingSourcePackageId_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse("{\"model_id\":\"m\"}");
        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("source_package_id", result.Failure!.Field);
    }

    [Fact]
    public void Parse_MissingModelId_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse($"{{\"source_package_id\":\"{Pkg}\"}}");
        Assert.False(result.Success);
        Assert.Equal("model_id", result.Failure!.Field);
    }

    [Fact]
    public void Parse_OptionsNotObject_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse(
            $"{{\"source_package_id\":\"{Pkg}\",\"model_id\":\"m\",\"options\":[1,2]}}");
        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("options", result.Failure!.Field);
    }

    [Fact]
    public void Parse_AllowExperimentalNotBool_Fails()
    {
        var result = ReconstructionMeshSubmitRequestParser.Parse(
            $"{{\"source_package_id\":\"{Pkg}\",\"model_id\":\"m\",\"allow_experimental_model\":\"yes\"}}");
        Assert.False(result.Success);
        Assert.Equal("allow_experimental_model", result.Failure!.Field);
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionMeshSubmitRequestParserTests" -v minimal`
Expected: FAIL — `ReconstructionMeshSubmitRequestParser` does not exist (compile error).

- [ ] **Step 3: Implement the parser**

Create `src/Rook/Services/Reconstruction/ReconstructionMeshSubmitRequestParser.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionMeshSubmitRequest(
    Guid SourcePackageId,
    string ModelId,
    JsonObject Options,
    bool AllowExperimentalModel);

public sealed record ReconstructionMeshParseResult(
    bool Success,
    ReconstructionMeshSubmitRequest? Request,
    ReconstructionFailure? Failure);

public static class ReconstructionMeshSubmitRequestParser
{
    public static ReconstructionMeshParseResult Parse(string? body)
    {
        JsonObject root;
        try
        {
            root = (JsonNode.Parse(string.IsNullOrWhiteSpace(body) ? "{}" : body) as JsonObject)
                ?? throw new FormatException();
        }
        catch
        {
            return Fail("invalid_request", "Request body must be a JSON object.", "body");
        }

        if (!root.TryGetPropertyValue("source_package_id", out var pkgNode)
            || pkgNode is not JsonValue pkgVal
            || !pkgVal.TryGetValue<string>(out var pkgStr)
            || !Guid.TryParse(pkgStr, out var sourcePackageId))
        {
            return Fail("invalid_request", "source_package_id is required.", "source_package_id");
        }

        var modelId = (root["model_id"] as JsonValue)?.TryGetValue<string>(out var m) == true ? m : null;
        if (string.IsNullOrWhiteSpace(modelId))
            return Fail("invalid_request", "model_id is required.", "model_id");

        JsonObject options;
        if (root.TryGetPropertyValue("options", out var optNode) && optNode is not null)
        {
            if (optNode is not JsonObject optObj)
                return Fail("invalid_request", "options must be a JSON object.", "options");
            options = (JsonObject)optObj.DeepClone();
        }
        else
        {
            options = new JsonObject();
        }

        var allowExperimental = false;
        if (root.TryGetPropertyValue("allow_experimental_model", out var allowNode) && allowNode is not null)
        {
            if (allowNode is JsonValue allowValue && allowValue.TryGetValue<bool>(out var allowFlag))
                allowExperimental = allowFlag;
            else
                return Fail("invalid_request", "allow_experimental_model must be a boolean.", "allow_experimental_model");
        }

        return new ReconstructionMeshParseResult(
            true,
            new ReconstructionMeshSubmitRequest(sourcePackageId, modelId!, options, allowExperimental),
            null);
    }

    private static ReconstructionMeshParseResult Fail(string code, string message, string field)
        => new(false, null, new ReconstructionFailure(code, message, false, field,
            new Dictionary<string, object?>(StringComparer.Ordinal)));
}
```

Note: stricter than the image parser by design — a non-object `options` is rejected here (the image parser at `ReconstructionSubmitRequestParser.cs:86` silently coerces; the spec mandates strict rejection for mesh).

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionMeshSubmitRequestParserTests" -v minimal`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionMeshSubmitRequestParser.cs src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSubmitRequestParserTests.cs
git commit -m "feat(reconstruction): strict mesh submit request parser (source_package_id)"
```

---

### Task 2: Source-front-specific submit gates + picker guard

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (add gate helpers near `IsSubmittable3DModel` ~line 724; switch `SubmitAsync` line 118 to the image gate)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`Models` picker filter ~line 148-160)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionSubmitGateTests.cs`

**Interfaces:**
- Produces: `internal static bool IsSubmittableImageModel(ReconstructionModelEntry?, bool)` and `internal static bool IsSubmittableMeshModel(ReconstructionModelEntry?, bool)` on `ReconstructionJobManager`.
- Consumes: existing `IsSubmittable3DModel`, `ReconstructionModelEntry.InputTypes`, `.Input?.Mode`.

- [ ] **Step 1: Write the failing tests**

Create `src/Rook.Tests/Services/Reconstruction/ReconstructionSubmitGateTests.cs`:

```csharp
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionSubmitGateTests
{
    private static ReconstructionModelEntry Image(string status = "stable") => new(
        "img", "fal", "single_image_to_3d", status, true,
        new[] { "single_image_to_3d" }, new[] { "image_url" },
        new[] { "model_glb" }, "model_glb", new[] { "model_glb" }, false, false,
        new ReconstructionInputMetadata("single_image", "input_image_url"), null, null, null);

    private static ReconstructionModelEntry Mesh(string status = "experimental") => new(
        "mesh", "fal", "mesh_to_mesh_topology", status, true,
        new[] { "mesh_to_mesh", "smart_topology" }, new[] { "model_url" },
        new[] { "model_glb" }, "model_glb", new[] { "model_glb" }, false, false,
        new ReconstructionInputMetadata("single_model", "input_file_url"), null, null, null);

    [Fact]
    public void ImageGate_AcceptsImage_RejectsMesh()
    {
        Assert.True(ReconstructionJobManager.IsSubmittableImageModel(Image(), false));
        Assert.False(ReconstructionJobManager.IsSubmittableImageModel(Mesh(), true));
    }

    [Fact]
    public void MeshGate_AcceptsMesh_RejectsImage()
    {
        Assert.True(ReconstructionJobManager.IsSubmittableMeshModel(Mesh(), true));
        Assert.False(ReconstructionJobManager.IsSubmittableMeshModel(Image(), true));
    }

    [Fact]
    public void MeshGate_ExperimentalRejectedWithoutOverride()
    {
        Assert.False(ReconstructionJobManager.IsSubmittableMeshModel(Mesh(), false));
        Assert.True(ReconstructionJobManager.IsSubmittableMeshModel(Mesh(), true));
    }
}
```

Note: confirm the exact `ReconstructionModelEntry` positional ctor arity/order against `ReconstructionModelCatalog.cs` when implementing; adjust the two factory helpers above to match (the fields are: model_id, provider, task, status, enabled, pipeline_roles, input_types, output_roles, preferred_asset_role, fallback_order, supports_pbr, default_texture_expected, input, prompt, preprocessing, options — fill `null` for prompt/preprocessing/options).

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionSubmitGateTests" -v minimal`
Expected: FAIL — `IsSubmittableImageModel` / `IsSubmittableMeshModel` do not exist.

- [ ] **Step 3: Add the gate helpers and switch the image gate**

In `ReconstructionJobManager.cs`, immediately after `IsSubmittable3DModel` (~line 731) add:

```csharp
    // Image submit must reject mesh models (which also output model_glb); requires an image input.
    internal static bool IsSubmittableImageModel(ReconstructionModelEntry? model, bool allowExperimental = false)
        => IsSubmittable3DModel(model, allowExperimental)
            && model!.InputTypes.Contains("image_url", StringComparer.Ordinal);

    // Mesh submit must reject image models; requires a mesh input (model_url or single_model mode).
    internal static bool IsSubmittableMeshModel(ReconstructionModelEntry? model, bool allowExperimental = false)
        => IsSubmittable3DModel(model, allowExperimental)
            && (model!.InputTypes.Contains("model_url", StringComparer.Ordinal)
                || string.Equals(model.Input?.Mode, "single_model", StringComparison.Ordinal));
```

In `SubmitAsync` (line 118), change the gate from `IsSubmittable3DModel` to `IsSubmittableImageModel`:

```csharp
        if (!IsSubmittableImageModel(model, request.AllowExperimentalModel))
            return SubmitFail("invalid_request", "Requested reconstruction model is not available.", "model_id");
```

- [ ] **Step 4: Add the picker guard**

In `ReconstructionOpHandler.cs`, change `ProducesImportable3D` (line 148-149) to also require an image input so mesh models stay out of the image picker:

```csharp
    private static bool ProducesImportable3D(ReconstructionModelEntry m)
        => m.OutputRoles.Any(r => Array.IndexOf(ImportableModelRoles, r) >= 0)
            && m.InputTypes.Contains("image_url", StringComparer.Ordinal);
```

- [ ] **Step 5: Run gate tests + full reconstruction suite (no regressions)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" -v minimal`
Expected: PASS (gate tests green; existing image submit/catalog/picker tests unchanged — all existing image models have `image_url` input).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Services/Reconstruction/ReconstructionSubmitGateTests.cs
git commit -m "feat(reconstruction): source-front-specific submit gates (image_url vs model_url) + picker guard"
```

---

### Task 3: Mesh source validator (deterministic, pre-ledger)

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionMeshSourceValidator.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSourceValidatorTests.cs`

**Interfaces:**
- Produces: `ReconstructionMeshSourceValidator.Validate(ArtifactStore store, Guid sourcePackageId) → ReconstructionMeshSourceValidationResult(string? ModelGlbAbsolutePath, Guid SourcePackageId, ReconstructionFailure? Failure)`.
- Consumes: `ArtifactStore` (`Get`, `GetBlobAbsolutePath`), `ReconstructionArtifactKinds.Package`, `ReconstructionFileRoles.ModelGlb`.

- [ ] **Step 1: Write the failing tests**

Create `src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSourceValidatorTests.cs`. Use the existing reconstruction test fixture helpers to build an `ArtifactStore` + a package artifact (mirror how `ReconstructionOpHandlerTests` builds packages via `BuildPackageAsync`; reuse that fixture pattern). Cover:

```csharp
// 1) unknown package id -> invalid_source_package
// 2) artifact of a non-package kind -> invalid_source_package
// 3) package WITHOUT a model_glb file role -> missing_model_glb
// 4) package WITH model_glb but the blob is empty (0 bytes) -> invalid_source_package
// 5) happy path: package with non-empty model_glb -> Success, ModelGlbAbsolutePath set, Failure null
```

Write each as an explicit xUnit `[Fact]` asserting `result.Failure!.Code` / `result.Success` / `result.ModelGlbAbsolutePath`. (Build the store + package with the same `CreateFixture()`/`BuildPackageAsync` helpers used in `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`; for case 4 write a 0-byte `model_glb` blob.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionMeshSourceValidatorTests" -v minimal`
Expected: FAIL — validator class does not exist.

- [ ] **Step 3: Implement the validator**

Create `src/Rook/Services/Reconstruction/ReconstructionMeshSourceValidator.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Rook.Artifacts;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionMeshSourceValidationResult(
    string? ModelGlbAbsolutePath,
    Guid SourcePackageId,
    ReconstructionFailure? Failure)
{
    public bool Success => Failure is null;
}

public static class ReconstructionMeshSourceValidator
{
    public static ReconstructionMeshSourceValidationResult Validate(ArtifactStore store, Guid sourcePackageId)
    {
        var artifact = store.Get(sourcePackageId);
        if (artifact is null
            || !string.Equals(artifact.Kind, ReconstructionArtifactKinds.Package, StringComparison.Ordinal))
        {
            return Fail(sourcePackageId, "invalid_source_package",
                "source_package_id must reference an existing reconstruction_package.");
        }

        var hasGlb = artifact.Files.Any(f =>
            string.Equals(f.Role, ReconstructionFileRoles.ModelGlb, StringComparison.Ordinal));
        if (!hasGlb)
        {
            return Fail(sourcePackageId, "missing_model_glb",
                "source package has no model_glb; Smart Topology requires GLB input.");
        }

        var path = store.GetBlobAbsolutePath(sourcePackageId, ReconstructionFileRoles.ModelGlb);
        if (string.IsNullOrWhiteSpace(path) || !File.Exists(path) || new FileInfo(path).Length == 0)
        {
            return Fail(sourcePackageId, "invalid_source_package",
                "source package model_glb blob is empty or unreadable.");
        }

        return new ReconstructionMeshSourceValidationResult(path, sourcePackageId, null);
    }

    private static ReconstructionMeshSourceValidationResult Fail(Guid id, string code, string message)
        => new(null, id, new ReconstructionFailure(code, message, false, "source_package_id",
            new Dictionary<string, object?>(StringComparer.Ordinal)));
}
```

(Confirm `ArtifactStore.GetBlobAbsolutePath(Guid, string)` and `ReconstructionFileRoles.ModelGlb` / `ReconstructionArtifactKinds.Package` names against the codebase; the Explore pass confirmed these roles/kinds exist.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionMeshSourceValidatorTests" -v minimal`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionMeshSourceValidator.cs src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSourceValidatorTests.cs
git commit -m "feat(reconstruction): deterministic mesh source validator (package + model_glb preconditions)"
```

---

### Task 4: Extract the shared `SubmitResolvedAsync` tail (image path preserved)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`SubmitCoreAsync` ~lines 244-356; make the upload-failure text source-neutral at ~line 285)
- Test: existing `src/Rook.Tests` reconstruction submit tests are the regression pin (no new test needed; they must stay green)

**Interfaces:**
- Produces: `private async Task<ReconstructionSubmitResult> SubmitResolvedAsync(Guid jobId, ReconstructionJobLedgerRecord queued, ReconstructionModelEntry model, JsonObject validatedOptions, IReadOnlyList<ReconstructionProviderViewUrl> providerInputs, IReadOnlyList<Guid> sourceArtifactIds, CancellationToken ct)`. Note: takes the `queued` ledger record as anchor (derives Polling/Error records and returns it on success) — the one internal param beyond the approved source-agnostic shape.

- [ ] **Step 1: Add `SubmitResolvedAsync` (tail = provider submit + outcome switch)**

In `ReconstructionJobManager.cs`, add this method (the body is lifted verbatim from the current `SubmitCoreAsync` lines 262-355, re-anchored on `queued`):

```csharp
    // Source-agnostic submit tail: given already-published provider inputs + lineage parents and a
    // queued ledger anchor, submit to the provider, append Polling, stash lineage, and start the poll
    // loop. Knows nothing about whether providerInputs came from images, a package GLB, or future
    // Rhino export. Shared by submit_job and submit_mesh_job.
    private async Task<ReconstructionSubmitResult> SubmitResolvedAsync(
        Guid jobId,
        ReconstructionJobLedgerRecord queued,
        ReconstructionModelEntry model,
        JsonObject validatedOptions,
        IReadOnlyList<ReconstructionProviderViewUrl> providerInputs,
        IReadOnlyList<Guid> sourceArtifactIds,
        CancellationToken ct)
    {
        ProviderSubmitOutcome submitOutcome;
        try
        {
            submitOutcome = await _provider.SubmitAsync(
                new ReconstructionProviderSubmitRequest(model.ModelId, providerInputs, validatedOptions),
                ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (ReconstructionCredentialMissingException)
        {
            return RecordSubmitFailure(queued, ReconstructionErrorMapping.MissingCredentialFailure());
        }
        catch (Exception ex)
        {
            return RecordSubmitFailure(queued, Failure(
                "submit_failed",
                "Reconstruction submit failed.",
                null,
                retryable: true,
                new Dictionary<string, object?> { ["exception_type"] = ex.GetType().Name }));
        }

        switch (submitOutcome)
        {
            case QueuedSubmitOutcome queuedOutcome:
                var handle = queuedOutcome.Handle;
                var polling = queued with
                {
                    State = ReconstructionJobState.Running,
                    Stage = ReconstructionJobStage.Polling,
                    ProviderJobId = handle.ProviderJobId,
                    ProviderStatusUrl = handle.StatusUrl?.ToString(),
                    ProviderResponseUrl = handle.ResponseUrl?.ToString(),
                    ProviderCancelUrl = handle.CancelUrl?.ToString(),
                    ProviderCancelHttpMethod = handle.CancelHttpMethod,
                    UpdatedAt = DateTimeOffset.UtcNow,
                };
                _ledger.Append(polling);
                _jobSourceArtifactIds[jobId] = sourceArtifactIds.ToArray();
                StartBackgroundLoop(polling);
                return new ReconstructionSubmitResult(true, queued, null);

            case FailedSubmitOutcome failedOutcome:
                return RecordSubmitFailure(queued, ReconstructionErrorMapping.ToFailure(failedOutcome.Error));

            default:
                return RecordSubmitFailure(queued, Failure(
                    "submit_failed",
                    "Reconstruction provider returned an unexpected synchronous result.",
                    null));
        }
    }
```

(`RecordSubmitFailure(record, failure)` appends `record with { State=Error, Stage=Error, Error=failure }` — passing `queued` yields the same terminal error record the old `submitting`-anchored code produced, since only State/Stage differ and both are overwritten.)

- [ ] **Step 2: Rewrite the image `SubmitCoreAsync` to call the tail**

In `SubmitCoreAsync`, replace the block from `ProviderSubmitOutcome submitOutcome;` (line 245) through the end of the outcome `switch` (line 355) with the publish-only try plus a tail call. The publish loop and its catches stay (FalApi text made source-neutral):

```csharp
        var sourceArtifactIds = new List<Guid>();
        var providerViews = new List<ReconstructionProviderViewUrl>();
        try
        {
            foreach (var (rv, absolutePath) in validatedViews)
            {
                var bytes = await ReadFileBytesAsync(absolutePath, ct).ConfigureAwait(false);
                var mime = MimeForExtension(absolutePath);
                var fileName = $"rook-reconstruction-{rv.ArtifactId:D}-{rv.Slot}{Path.GetExtension(absolutePath)}";
                var url = await _sourcePublisher.PublishAsync(bytes, mime, fileName, ct).ConfigureAwait(false);
                providerViews.Add(new ReconstructionProviderViewUrl(rv.Field, url));
                sourceArtifactIds.Add(rv.ArtifactId);
            }
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (ReconstructionCredentialMissingException)
        {
            return RecordSubmitFailure(submitting, ReconstructionErrorMapping.MissingCredentialFailure());
        }
        catch (FalApiException ex)
        {
            return RecordSubmitFailure(submitting, Failure(
                "provider_unavailable",
                "Reconstruction source asset upload to the provider failed.",
                null,
                retryable: true,
                new Dictionary<string, object?> { ["exception_type"] = ex.GetType().Name }));
        }
        catch (Exception ex)
        {
            return RecordSubmitFailure(submitting, Failure(
                "submit_failed",
                "Reconstruction submit failed.",
                null,
                retryable: true,
                new Dictionary<string, object?> { ["exception_type"] = ex.GetType().Name }));
        }

        return await SubmitResolvedAsync(
            jobId, queued, model, request.Options, providerViews, sourceArtifactIds, ct)
            .ConfigureAwait(false);
```

(The upload-failure message changes from "source image upload" to "source asset upload" — source-neutral, shared by both fronts. `RecordSubmitFailure(submitting, …)` here is unchanged behavior for the image path's publish-phase failures.)

- [ ] **Step 3: Run the full reconstruction suite (regression — image path must be unchanged)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" -v minimal`
Expected: PASS. The image submit success/credential/FalApi/submit_failed/Failed-outcome tests stay green (same records appended, same result returned). If any test asserted the literal "source image upload" text, update that assertion to "source asset upload".

- [ ] **Step 4: Run the full managed suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal`
Expected: PASS (Rhino closed).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests
git commit -m "refactor(reconstruction): extract source-agnostic SubmitResolvedAsync tail; source-neutral upload-failure text"
```

---

### Task 5: Mesh submit front (`SubmitMeshAsync`) + op routing

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (add `SubmitMeshAsync`)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (op constant + `DispatchAsync` route + `SubmitMeshAsync` handler)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSubmitFlowTests.cs`

**Interfaces:**
- Consumes: `ReconstructionMeshSubmitRequest` (Task 1), `IsSubmittableMeshModel` (Task 2), `ReconstructionMeshSourceValidator` (Task 3), `SubmitResolvedAsync` (Task 4), `ReconstructionOptionsValidator.Validate`, `ReconstructionJobLedgerRecord.Queued`, the existing `_sourcePublisher`/`_store`/`_ledger`/`_catalog`.
- Produces: `ReconstructionJobManager.SubmitMeshAsync(ReconstructionMeshSubmitRequest request, CancellationToken ct) → ReconstructionSubmitResult`; op constant `OpSubmitMesh = "submit_mesh_job"`.

- [ ] **Step 1: Write the failing flow tests**

Create `src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSubmitFlowTests.cs` using the existing reconstruction test fixture (fake provider/publisher/store, mirroring how submit is tested today). Cover:

```csharp
// A) happy path: package with non-empty model_glb + experimental mesh model + allow_experimental_model:true
//    -> fake publisher receives bytes with mime "model/gltf-binary"
//    -> fake provider receives payload containing "input_file_url" + "input_file_type"="glb" + options
//    -> ledger queued record: SourceArtifactId == sourcePackageId, SourceRole == "model_glb", Task == "mesh_to_mesh_topology"
//    -> _jobSourceArtifactIds[jobId] == [sourcePackageId]  (lineage)
// B) image model id via submit_mesh_job -> invalid_request (mesh gate rejects), no ledger job, no publish
// C) missing model_glb package -> invalid_source_package/missing_model_glb, no ledger job, no publish
// D) user-supplied options.input_file_type -> invalid_request (unknown option), pre-ledger
// E) upload-failure parity: publisher throws ReconstructionCredentialMissingException
//    -> a FAILED ledger job exists (job created before upload), result.Failure.Code == "missing_credential"
```

Assert against the fake provider's captured payload and the fake ledger's records. (Reuse the same fakes the existing submit tests use; if a fake provider that captures the payload doesn't exist, add a minimal capturing fake in the test file.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionMeshSubmitFlowTests" -v minimal`
Expected: FAIL — `SubmitMeshAsync` does not exist.

- [ ] **Step 3: Implement `SubmitMeshAsync`**

In `ReconstructionJobManager.cs` add (mirrors `SubmitCoreAsync`'s structure: validate model+options pre-ledger → mesh source validate pre-ledger → ledger Queued/Submitting → upload post-ledger with publish catches → inject input_file_type → tail):

```csharp
    public async Task<ReconstructionSubmitResult> SubmitMeshAsync(
        ReconstructionMeshSubmitRequest request,
        CancellationToken ct)
    {
        var model = _catalog.Find(request.ModelId);
        if (!IsSubmittableMeshModel(model, request.AllowExperimentalModel))
            return SubmitFail("invalid_request", "Requested mesh-processing model is not available.", "model_id");

        // Catalog-described options validation (rejects unknown keys incl. a user-supplied input_file_type).
        var optionsResult = ReconstructionOptionsValidator.Validate(request.Options, model!);
        if (!optionsResult.Success)
            return new ReconstructionSubmitResult(false, null, optionsResult.Failure);
        var options = optionsResult.Options;

        // Deterministic source preconditions (pre-ledger; fail-closed, no phantom job).
        var source = ReconstructionMeshSourceValidator.Validate(_store, request.SourcePackageId);
        if (!source.Success)
            return new ReconstructionSubmitResult(false, null, source.Failure);

        var jobId = Guid.NewGuid();
        var queued = ReconstructionJobLedgerRecord.Queued(
            jobId,
            request.ModelId,
            request.SourcePackageId,
            "model_glb",
            textureExpected: false,
            task: "mesh_to_mesh_topology");
        _ledger.Append(queued);

        var submitting = queued with
        {
            State = ReconstructionJobState.Running,
            Stage = ReconstructionJobStage.Submitting,
            UpdatedAt = DateTimeOffset.UtcNow,
        };
        _ledger.Append(submitting);

        Uri inputFileUrl;
        try
        {
            var bytes = await ReadFileBytesAsync(source.ModelGlbAbsolutePath!, ct).ConfigureAwait(false);
            var fileName = $"rook-reconstruction-{request.SourcePackageId:D}-model.glb";
            inputFileUrl = await _sourcePublisher
                .PublishAsync(bytes, "model/gltf-binary", fileName, ct)
                .ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested)
        {
            throw;
        }
        catch (ReconstructionCredentialMissingException)
        {
            return RecordSubmitFailure(submitting, ReconstructionErrorMapping.MissingCredentialFailure());
        }
        catch (FalApiException ex)
        {
            return RecordSubmitFailure(submitting, Failure(
                "provider_unavailable",
                "Reconstruction source asset upload to the provider failed.",
                null,
                retryable: true,
                new Dictionary<string, object?> { ["exception_type"] = ex.GetType().Name }));
        }
        catch (Exception ex)
        {
            return RecordSubmitFailure(submitting, Failure(
                "submit_failed",
                "Reconstruction submit failed.",
                null,
                retryable: true,
                new Dictionary<string, object?> { ["exception_type"] = ex.GetType().Name }));
        }

        // input_file_type is fixed to glb (not a user option); inject after validation.
        options["input_file_type"] = "glb";

        var providerInputs = new List<ReconstructionProviderViewUrl>
        {
            new("input_file_url", inputFileUrl),
        };

        return await SubmitResolvedAsync(
            jobId, queued, model!, options,
            providerInputs, new[] { request.SourcePackageId }, ct).ConfigureAwait(false);
    }
```

- [ ] **Step 4: Wire the op in the handler**

In `ReconstructionOpHandler.cs`, add the op constant near line 30:

```csharp
        public const string OpSubmitMesh = "submit_mesh_job";
```

In `DispatchAsync` (line 75-85), add a route:

```csharp
                OpSubmitMesh => await SubmitMeshAsync(body, cancellationToken).ConfigureAwait(false),
```

And add the handler method (mirror `SubmitAsync` at line 168):

```csharp
        private async Task<ApiResponse> SubmitMeshAsync(string? body, CancellationToken ct)
        {
            var parsed = ReconstructionMeshSubmitRequestParser.Parse(body);
            if (!parsed.Success)
                return Fail(parsed.Failure!, StatusFor(parsed.Failure!));

            var result = await _manager.SubmitMeshAsync(parsed.Request!, ct).ConfigureAwait(false);
            if (!result.Success)
                return Fail(result.Failure!, StatusFor(result.Failure!));

            return Ok(JobToObj(result.Job!));
        }
```

- [ ] **Step 5: Run flow tests + full reconstruction suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" -v minimal`
Expected: PASS (flow tests A-E green; image path unaffected).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Services/Reconstruction/ReconstructionMeshSubmitFlowTests.cs
git commit -m "feat(reconstruction): submit_mesh_job front (package->GLB upload->shared tail) + op routing"
```

---

### Task 6: Catalog entry

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`
- Test: add a production-catalog test to `src/Rook.Tests` (mirror the existing catalog test that asserts the Meshy/Hunyuan entries)

- [ ] **Step 1: Write the failing catalog test**

Add a `[Fact]` to the existing reconstruction catalog test class (find it via `grep -rl "fal-model-catalog\|ProductionCatalog\|FromJson" src/Rook.Tests`). Assert the production catalog contains `fal-ai/hunyuan-3d/v3.1/smart-topology` with: `Status == "experimental"`, `InputTypes` contains `"model_url"`, `OutputRoles` contains `"model_glb"`, `Input.Mode == "single_model"`, `Input.SourceField == "input_file_url"`, options keys `{ "polygon_type", "face_level" }` both enum, and that `IsSubmittableMeshModel(entry, true)` is true while `IsSubmittableImageModel(entry, true)` is false.

- [ ] **Step 2: Run it to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Catalog" -v minimal`
Expected: FAIL — entry absent.

- [ ] **Step 3: Add the catalog entry**

In `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`, add to the `models` array:

```json
{
  "model_id": "fal-ai/hunyuan-3d/v3.1/smart-topology",
  "provider": "fal", "task": "mesh_to_mesh_topology", "status": "experimental", "enabled": true,
  "pipeline_roles": ["mesh_to_mesh", "smart_topology"], "input_types": ["model_url"],
  "output_roles": ["model_glb"], "preferred_asset_role": "model_glb", "fallback_order": ["model_glb"],
  "supports_pbr": false, "default_texture_expected": false,
  "input": { "mode": "single_model", "source_field": "input_file_url" },
  "prompt": { "supported": false, "required": false, "kind": null },
  "preprocessing": { "recommended": false, "required": false },
  "options": [
    { "key": "polygon_type", "label": "Polygon Type", "kind": "enum", "default": "triangle", "allowed_values": ["triangle", "quadrilateral"] },
    { "key": "face_level",   "label": "Face Level",   "kind": "enum", "default": "medium",   "allowed_values": ["high", "medium", "low"] }
  ]
}
```

(If the catalog is an embedded resource, no rebuild step beyond the normal test build is needed; the test reads the production JSON.)

- [ ] **Step 4: Run catalog tests + full reconstruction suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction" -v minimal`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json src/Rook.Tests
git commit -m "feat(reconstruction): Hunyuan Smart Topology catalog entry (experimental, mesh input)"
```

---

### Task 7: Native route + MCP tool

**Files:**
- Modify: `src/RookNative/RookServer.cpp` (route registration ~line 2145-2155; new handler) + the handler decl/site in `src/RookNative/Handlers/GrasshopperProxyHandler.cpp` (mirror `HandleReconstructionSubmit` ~line 1365)
- Modify: `mcp_server/src/rook/server.py` (new `rhino_3d_to_3d_submit` tool + dispatch case)
- Test: native source-text assertion in `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`; MCP tool test if the repo has one (else manual)

**Interfaces:**
- Produces: `POST /reconstruction/3d-to-3d/jobs` → `DispatchReconstructionOp(req, res, "submit_mesh_job")`; MCP tool `rhino_3d_to_3d_submit`.

- [ ] **Step 1: Native source-text assertion (TDD for the C++ route)**

In `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs` add a `[Fact]` asserting `RookServer.cpp` text contains the new route registration and op, e.g.:

```csharp
Assert.Contains("/reconstruction/3d-to-3d/jobs", serverText);
Assert.Contains("\"submit_mesh_job\"", serverText);
Assert.Contains("HandleReconstructionSubmitMesh", serverText);
```

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeReconstructionDispatchSourceTests" -v minimal` → FAIL.

- [ ] **Step 2: Add the native handler + route + soft-allowlist entry**

In the reconstruction handler block of `GrasshopperProxyHandler.cpp` (next to `HandleReconstructionSubmit`, ~line 1365), add:

```cpp
void HandleReconstructionSubmitMesh(const httplib::Request& req, httplib::Response& res)
{
    DispatchReconstructionOp(req, res, "submit_mesh_job");
}
```

Add its declaration wherever `HandleReconstructionSubmit` is declared (same header/namespace). In `RookServer.cpp`: register the route in the server-setup block next to the existing reconstruction routes:

```cpp
m_server->Post("/reconstruction/3d-to-3d/jobs", Rook::Handlers::HandleReconstructionSubmitMesh);
```

Add `"POST /reconstruction/3d-to-3d/jobs"` to the route-list string array (line ~2145-2154) and `"submit_mesh_job"` to the op soft-allowlist string array (line ~2155).

Run the native source test → PASS.

- [ ] **Step 3: Add the MCP tool**

In `mcp_server/src/rook/server.py`, add a `rhino_3d_to_3d_submit` tool next to `rhino_2d_to_3d_submit` (~line 12703):

```python
{
    "name": "rhino_3d_to_3d_submit",
    "description": "Submit a 3D->3D mesh-processing job (e.g. Hunyuan Smart Topology) against an existing reconstruction_package. model_id selects the mesh operation.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "source_package_id": {"type": "string", "description": "Existing reconstruction_package id (must contain a model_glb)."},
            "model_id": {"type": "string", "description": "Full fal model id (e.g. fal-ai/hunyuan-3d/v3.1/smart-topology). Required; no implicit default."},
            "options": {"type": "object", "description": "Mesh-operation options (e.g. polygon_type, face_level)."},
            "allow_experimental_model": {"type": "boolean", "description": "Dev/test override: allow an experimental catalog model. Honored only with an explicit model_id."},
            "port": {"type": "integer", "description": "Specific Rhino port to target."},
        },
        "required": ["source_package_id", "model_id"],
    },
},
```

Add the dispatch case near `rhino_2d_to_3d_submit` (~line 20295):

```python
case "rhino_3d_to_3d_submit":
    result = await call_rhino(
        "/reconstruction/3d-to-3d/jobs", "POST", arguments, port=port
    )
```

Status/result/import reuse the existing `rhino_2d_to_3d_status` / `_result` / `_import` (job/package-id based).

- [ ] **Step 4: Run the managed suite (native source test + no regressions)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -v minimal`
Expected: PASS (Rhino closed).

- [ ] **Step 5: Commit**

```bash
git add src/RookNative mcp_server/src/rook/server.py src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs
git commit -m "feat(reconstruction): native /reconstruction/3d-to-3d/jobs route + rhino_3d_to_3d_submit MCP tool"
```

---

### Task 8: Live smoke (one paid run — promotion gate; manual)

**Files:**
- Modify: spec (append smoke result); `fal-model-catalog.json` (promote to `stable` on success)

- [ ] **Step 1: Precondition — source package with model_glb still staged**

Run (PowerShell):

```powershell
Get-ChildItem "$env:APPDATA\Rook\artifacts\2026-06-24\d61c3f06-0c85-4e01-a84c-56bd5439a966" |
  Where-Object { $_.Name -eq "model_glb.glb" } | Select-Object -ExpandProperty Name
```

Expected: `model_glb.glb`. If missing, STOP and decide with the user whether to run a fresh image→3D package first — do not silently substitute.

- [ ] **Step 2: Deploy (Rhino closed, rook python stopped — native build required)**

```
pwsh -File scripts/deploy-local-testing.ps1
```

Confirm native + managed "Build succeeded / 0 Errors" and the native plugin registration in the log. `/mcp` reconnect after deploy (new MCP tool schema).

- [ ] **Step 3: Submit Smart Topology against the package (user launches Rhino first; `rhino_ping` → pong)**

```
rhino_3d_to_3d_submit source_package_id=d61c3f06-0c85-4e01-a84c-56bd5439a966 \
  model_id=fal-ai/hunyuan-3d/v3.1/smart-topology allow_experimental_model=true \
  options={"polygon_type":"triangle","face_level":"medium"}
```

Poll with `rhino_2d_to_3d_status job_id=<id>` to completion; fetch `rhino_2d_to_3d_result job_id=<id>` → new `package_id`.

- [ ] **Step 4: Import + verify**

`rhino_2d_to_3d_import package_id=<new>` → then verify (MCP + a small `rhino_execute` read):
- imported object exists with a non-empty bounding box (non-degenerate mesh),
- the new package's `asset_roles` includes `model_glb`,
- the new package's `ParentIds` contains `d61c3f06-…` (lineage).

- [ ] **Step 5: Promote to stable + record result**

On PASS, set the catalog entry `status` to `"stable"`, run `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Catalog"` (update the experimental-status assertion to stable), and append a `## Live smoke result` section to the spec. Commit:

```bash
git add src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json src/Rook.Tests docs/superpowers/specs/2026-06-24-reconstruction-mesh-smart-topology-design.md
git commit -m "feat(reconstruction): promote Smart Topology to stable after passing live smoke"
```

---

## Self-Review

**Spec coverage:** op/parser → Task 1; source-front gates + picker → Task 2; mesh source validator → Task 3; shared tail (T1) + source-neutral upload text → Task 4; mesh front + ledger SourceRole/task + input_file_type injection + upload-failure parity + lineage → Task 5; catalog → Task 6; MCP + native route → Task 7; live smoke + promotion → Task 8. All covered.

**Placeholder scan:** No TBD/TODO. Tasks 3, 5, 6 reference "the existing fixture/catalog test" rather than inlining the full fixture — acceptable because they reuse a documented existing harness (`CreateFixture`/`BuildPackageAsync`, the existing catalog test); the assertions to add are spelled out explicitly. Task 2's `ReconstructionModelEntry` ctor arity carries an explicit "confirm against catalog" note because the positional ctor is long.

**Type consistency:** `ReconstructionMeshSubmitRequest`/`ReconstructionMeshParseResult` (Task 1) consumed in Task 5 + Task 7 handler. `IsSubmittableMeshModel`/`IsSubmittableImageModel` (Task 2) used in Task 5/Task 6. `ReconstructionMeshSourceValidator.Validate(store, id)` → `.ModelGlbAbsolutePath`/`.Success`/`.Failure` (Task 3) consumed in Task 5. `SubmitResolvedAsync(Guid, ReconstructionJobLedgerRecord queued, model, JsonObject, IReadOnlyList<ReconstructionProviderViewUrl>, IReadOnlyList<Guid>, ct)` (Task 4) called by both `SubmitCoreAsync` and `SubmitMeshAsync` with matching argument types. Op constant `OpSubmitMesh = "submit_mesh_job"` (Task 5) matches the native op string and MCP endpoint (Task 7). Catalog `input_types: ["model_url"]` + `input.mode: "single_model"` (Task 6) satisfy `IsSubmittableMeshModel` (Task 2) and keep it out of `ProducesImportable3D` (Task 2).
