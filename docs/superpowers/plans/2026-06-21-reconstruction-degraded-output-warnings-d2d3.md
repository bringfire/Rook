# Reconstruction Degraded-Output Warnings (D2/D3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Surface a high-signal warning on a reconstruction *result* when a textured output was expected but the delivered package came back without material/texture.

**Architecture:** Derive a normalized `TextureExpected` flag at submit (from options + the model's catalog default), persist it on the job ledger (schema v2), and at `Result()` time compute two mutually-exclusive warnings from `TextureExpected` × catalog `supports_pbr` × the delivered package's roles. All warning logic lives behind two `internal static` pure helpers. Result-only; no status/package/MCP/UI changes.

**Tech Stack:** C# (.NET, net48 test target), `System.Text.Json` / `System.Text.Json.Nodes`, xUnit.

## Global Constraints

- **Result-only.** `Status`/`StatusAsync` and their HTTP response stay warning-free. No package mutation. No MCP/Python/UI changes.
- **Strict JSON booleans.** Option reads accept only a JSON boolean literal; `"true"`, `1`, `null`, missing → treated as absent (never coerced). Reuse D1's discipline.
- **`output_roles` stays non-load-bearing.** Role-presence uses role-name constants (`material_mtl`, `texture*`) directly, not an intersection with `output_roles`.
- **Material-only = NOT degraded.** Presence of `material_mtl` alone suppresses the missing-texture warning.
- **Missing-package precedence.** If the package artifact is gone, emit `result_artifact_missing` only; do not evaluate texture warnings.
- **Old ledger records:** `texture_expected` absent → `false` (no retroactive warnings). The schema-version gate must accept `1..CurrentSchemaVersion` (exact-match would orphan all v1 records).
- **Catalog default absent → `false`** (no accidental default-true).
- **Warning codes:** `pbr_unsupported_by_model`, `result_missing_texture`.
- **Messages (verbatim):**
  - `pbr_unsupported_by_model`: `Texture output was expected for this request, but model '{model_id}' is not catalogued as supporting textured/PBR output. The result may lack materials or textures.`
  - `result_missing_texture`: `Texture output was expected and this model supports it, but the delivered package contains no material or texture assets.`
- **`TextureExpected` derivation (first match wins, strict booleans):** ① `enable_geometry===true`→false; ② `enable_pbr===true`→true; ③ `enable_pbr===false`→false; ④ otherwise→`catalog.default_texture_expected`.

---

### Task 1: Catalog `default_texture_expected` field + data

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` (the `ReconstructionModelEntry` record)
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` (Hunyuan rapid entry)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs`

**Interfaces:**
- Produces: `ReconstructionModelEntry.DefaultTextureExpected` (`bool`, JSON `default_texture_expected`), consumed by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests**

Open `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs`. Add these two facts inside the test class (match the file's existing using/namespace; `ReconstructionModelCatalog.FromJson` is the construction entry point):

```csharp
    [Fact]
    public void DefaultTextureExpected_ParsesTrue_WhenPresent()
    {
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d",
            "provider": "fal", "task": "single_image_to_3d", "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": true,
            "default_texture_expected": true,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://fal.ai/x"
          }]
        }
        """;
        var entry = ReconstructionModelCatalog.FromJson(json).Find("fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d");
        Assert.NotNull(entry);
        Assert.True(entry!.DefaultTextureExpected);
    }

    [Fact]
    public void DefaultTextureExpected_DefaultsFalse_WhenAbsent()
    {
        const string json = """
        {
          "schema_version": 1,
          "models": [{
            "model_id": "fal-ai/minimal", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": false,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://fal.ai/x"
          }]
        }
        """;
        var entry = ReconstructionModelCatalog.FromJson(json).Find("fal-ai/minimal");
        Assert.NotNull(entry);
        Assert.False(entry!.DefaultTextureExpected);   // absent → false, no accidental default-true
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests"`
Expected: FAIL — `ReconstructionModelEntry` has no `DefaultTextureExpected` member (compile error).

- [ ] **Step 3: Add the field to the record**

In `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs`, append a trailing positional parameter to `ReconstructionModelEntry` (after `DocsUrl`):

```csharp
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
    [property: JsonPropertyName("docs_url")] string DocsUrl,
    [property: JsonPropertyName("default_texture_expected")] bool DefaultTextureExpected);
```

(System.Text.Json sets a missing constructor parameter to `default(bool)` = `false`, so absent → false.)

- [ ] **Step 4: Check for positional construction sites**

Run: `git grep -n "new ReconstructionModelEntry(" -- src/`
Expected: no production matches (catalog is built via `FromJson`). If any positional `new ReconstructionModelEntry(...)` exists, append a trailing `false` (or the intended value) argument to it. If the grep is empty, nothing to do.

- [ ] **Step 5: Add the catalog data**

In `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`, add `"default_texture_expected": true` to the `fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d` entry (place it next to `"supports_pbr": true`). Leave all other entries without the field (they default to `false`).

- [ ] **Step 6: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs
git commit -m "feat(reconstruction): add default_texture_expected catalog field (D3)"
```

---

### Task 2: Ledger `TextureExpected` field + schema v2 migration

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobLedgerTests.cs`

**Interfaces:**
- Produces: `ReconstructionJobLedgerRecord.TextureExpected` (`bool`, trailing positional, JSON `texture_expected`); `ReconstructionJobLedgerRecord.Queued(..., bool textureExpected = false)`. Consumed by Tasks 3 and 4.

- [ ] **Step 1: Write the failing tests**

In `src/Rook.Tests/Services/Reconstruction/ReconstructionJobLedgerTests.cs`, add these facts (match the file's existing fixture/temp-path helper conventions; if the file constructs `JsonlReconstructionJobLedger` against a temp path, mirror that — shown here with a self-contained temp file):

```csharp
    [Fact]
    public void Append_Then_List_RoundTrips_TextureExpected_True()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rook-ledger-{Guid.NewGuid():N}.jsonl");
        try
        {
            var ledger = new JsonlReconstructionJobLedger(path);
            var rec = ReconstructionJobLedgerRecord.Queued(
                Guid.NewGuid(), "fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d", Guid.NewGuid(), "image",
                textureExpected: true);
            ledger.Append(rec);

            var read = ledger.List(10).Jobs.Single();
            Assert.True(read.TextureExpected);
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void List_ReadsLegacyV1Record_WithTextureExpectedFalse_NotDropped()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rook-ledger-{Guid.NewGuid():N}.jsonl");
        try
        {
            // A hand-written v1 line: schema_version 1, NO texture_expected key.
            var jobId = Guid.NewGuid();
            var v1 = $$"""
            {"schema_version":1,"job_id":"{{jobId:D}}","state":"Complete","stage":"Complete","provider":"fal","model_id":"fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d","source_artifact_id":"{{Guid.NewGuid():D}}","source_role":"image","created_at":"2026-06-20T00:00:00.0000000+00:00","updated_at":"2026-06-20T00:00:00.0000000+00:00","result_available":false,"preprocessing_chain":[]}
            """;
            File.WriteAllText(path, v1 + "\n");

            var ledger = new JsonlReconstructionJobLedger(path);
            var result = ledger.List(10);

            var job = Assert.Single(result.Jobs);                  // NOT dropped as unsupported
            Assert.Equal(jobId, job.JobId);
            Assert.False(job.TextureExpected);                      // absent → false
            Assert.DoesNotContain(result.Warnings, w => w.Code == "unsupported_schema_version");
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }

    [Fact]
    public void List_RejectsFutureSchemaVersion_AsUnsupported()
    {
        var path = Path.Combine(Path.GetTempPath(), $"rook-ledger-{Guid.NewGuid():N}.jsonl");
        try
        {
            var future = $$"""
            {"schema_version":99,"job_id":"{{Guid.NewGuid():D}}","state":"Complete","stage":"Complete","provider":"fal","model_id":"x","source_role":"image","result_available":false,"preprocessing_chain":[]}
            """;
            File.WriteAllText(path, future + "\n");

            var result = new JsonlReconstructionJobLedger(path).List(10);

            Assert.Empty(result.Jobs);
            Assert.Contains(result.Warnings, w => w.Code == "unsupported_schema_version");
        }
        finally { if (File.Exists(path)) File.Delete(path); }
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobLedgerTests"`
Expected: FAIL — `Queued` has no `textureExpected` parameter and the record has no `TextureExpected` (compile error).

- [ ] **Step 3: Add the record field and bump the schema version**

In `src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs`, append `bool TextureExpected` as the trailing positional parameter of `ReconstructionJobLedgerRecord` (after `ReconstructionFailure? Error`) and bump the version constant:

```csharp
public sealed record ReconstructionJobLedgerRecord(
    int SchemaVersion,
    Guid JobId,
    ReconstructionJobState State,
    ReconstructionJobStage Stage,
    string Provider,
    string ModelId,
    string? ProviderJobId,
    string? ProviderStatusUrl,
    string? ProviderResponseUrl,
    string? ProviderCancelUrl,
    string? ProviderCancelHttpMethod,
    Guid SourceArtifactId,
    string SourceRole,
    IReadOnlyList<ReconstructionPreprocessingStageRecord> PreprocessingChain,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    Guid? ResultArtifactId,
    bool ResultAvailable,
    ReconstructionFailure? Error,
    bool TextureExpected)
{
    public const int CurrentSchemaVersion = 2;
```

- [ ] **Step 4: Thread the field through both factory methods**

In the same file, update `Queued` to accept an optional `textureExpected` (keeps every existing caller compiling) and pass it; update `Complete` to pass `false`. Add the trailing argument to both `new ReconstructionJobLedgerRecord(...)` calls:

```csharp
    public static ReconstructionJobLedgerRecord Queued(
        Guid jobId,
        string modelId,
        Guid sourceArtifactId,
        string sourceRole,
        bool textureExpected = false)
    {
        var now = DateTimeOffset.UtcNow;
        return new ReconstructionJobLedgerRecord(
            CurrentSchemaVersion,
            jobId,
            ReconstructionJobState.Queued,
            ReconstructionJobStage.Queued,
            "fal",
            modelId,
            null, null, null, null, null,
            sourceArtifactId,
            sourceRole,
            Array.Empty<ReconstructionPreprocessingStageRecord>(),
            now, now,
            null,
            false,
            null,
            textureExpected);
    }

    public static ReconstructionJobLedgerRecord Complete(Guid jobId, Guid resultArtifactId)
    {
        var now = DateTimeOffset.UtcNow;
        return new ReconstructionJobLedgerRecord(
            CurrentSchemaVersion,
            jobId,
            ReconstructionJobState.Complete,
            ReconstructionJobStage.Complete,
            "fal",
            string.Empty,
            null, null, null, null, null,
            Guid.Empty,
            "image",
            Array.Empty<ReconstructionPreprocessingStageRecord>(),
            now, now,
            resultArtifactId,
            true,
            null,
            false);
    }
```

- [ ] **Step 5: Serialize the new field**

In `Serialize(...)`, add the key alongside the others (e.g. after `["result_available"]`):

```csharp
            ["result_available"] = record.ResultAvailable,
            ["texture_expected"] = record.TextureExpected,
```

- [ ] **Step 6: Relax the schema gate and deserialize the field**

In `TryDeserialize(...)`, replace the exact-match version gate:

```csharp
        var schemaVersion = ReadInt(obj, "schema_version");
        if (schemaVersion < 1 || schemaVersion > ReconstructionJobLedgerRecord.CurrentSchemaVersion)
        {
            warning = Warning(lineNumber, "unsupported_schema_version", "Unsupported ledger schema version.");
            return null;
        }
```

and add the trailing constructor argument reading `texture_expected` (absent → false), mirroring the existing `ReadBool(obj, "result_available") ?? false`:

```csharp
            ReadBool(obj, "result_available") ?? false,
            DeserializeFailure(obj["error"]),
            ReadBool(obj, "texture_expected") ?? false);
```

- [ ] **Step 7: Check for other positional construction sites**

Run: `git grep -n "new ReconstructionJobLedgerRecord(" -- src/`
Expected: only the two factories in `ReconstructionJobLedger.cs` (now updated). If any other positional construction exists, append the trailing `false`/intended argument. `with { }` expressions need no change.

- [ ] **Step 8: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobLedgerTests"`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobLedger.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobLedgerTests.cs
git commit -m "feat(reconstruction): persist TextureExpected on ledger; schema v2 with back-compat gate (D2)"
```

---

### Task 3: Derive `TextureExpected` at submit

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (add helpers; wire into `SubmitAsync`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionModelEntry.DefaultTextureExpected` (Task 1); `ReconstructionJobLedgerRecord.Queued(..., bool textureExpected)` (Task 2); existing private `IsJsonTrue` (D1).
- Produces: `internal static bool DeriveTextureExpected(JsonObject options, ReconstructionModelEntry model)` (consumed by tests; used by `SubmitAsync`). New private `ReadStrictBool`.

- [ ] **Step 1: Write the failing tests**

In `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`, first add `default_texture_expected` to the embedded `CatalogJson`'s Hunyuan entry (the `fal-ai/hunyuan-3d/...` block) so rule ④ resolves to `true`:

```csharp
          "fallback_order": ["model_glb", "model_obj"],
          "supports_pbr": true,
          "default_texture_expected": true,
```

Then add these facts. The first six are pure-unit tests of the helper (build entries via a tiny catalog JSON); the last is the submit-persistence wiring test (asserts the flag is readable on the ledger record via `Status`):

```csharp
    private static ReconstructionModelEntry ModelEntry(bool defaultTextureExpected, bool supportsPbr = true)
    {
        var json = $$"""
        {"schema_version":1,"models":[{
          "model_id":"fal-ai/test","provider":"fal","task":"single_image_to_3d","status":"stable","enabled":true,
          "pipeline_roles":["single_image_to_3d"],"input_types":["image_url"],"output_roles":["model_glb"],
          "preferred_asset_role":"model_glb","fallback_order":["model_glb"],"supports_pbr":{{(supportsPbr ? "true" : "false")}},
          "default_texture_expected":{{(defaultTextureExpected ? "true" : "false")}},
          "preprocessing":{"recommended":false,"required":false},"docs_url":"x"}]}
        """;
        return ReconstructionModelCatalog.FromJson(json).Find("fal-ai/test")!;
    }

    private static JsonObject Opts(string json) => JsonNode.Parse(json)!.AsObject();

    [Fact]
    public void DeriveTextureExpected_GeometryTrue_IsFalse()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_geometry"":true}"), ModelEntry(true)));

    [Fact]
    public void DeriveTextureExpected_PbrTrue_IsTrue()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_pbr"":true}"), ModelEntry(false)));

    [Fact]
    public void DeriveTextureExpected_PbrFalse_IsFalse()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_pbr"":false}"), ModelEntry(true)));

    [Fact]
    public void DeriveTextureExpected_Omitted_UsesCatalogDefaultTrue()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts("{}"), ModelEntry(true)));

    [Fact]
    public void DeriveTextureExpected_Omitted_UsesCatalogDefaultFalse()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts("{}"), ModelEntry(false)));

    [Fact]
    public void DeriveTextureExpected_NonBool_TreatedAsOmitted_UsesCatalogDefault()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts(@"{""enable_pbr"":""true""}"), ModelEntry(true)));

    [Fact]
    public async Task Submit_OmittedOptions_PersistsTextureExpectedFromCatalogDefault()
    {
        var fixture = CreateFixture();
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var request = Request(source.Id) with { Options = new JsonObject() };   // omitted → Hunyuan default true

        var submit = await fixture.Manager.SubmitAsync(request, CancellationToken.None);

        Assert.True(submit.Success);
        Assert.True(fixture.Manager.Status(submit.Job!.JobId).Job!.TextureExpected);
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: FAIL — `ReconstructionJobManager.DeriveTextureExpected` does not exist (compile error).

- [ ] **Step 3: Add the helpers**

In `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`, add next to the existing `IsJsonTrue` helper (leave `IsJsonTrue` untouched — D1 uses it):

```csharp
    private static bool? ReadStrictBool(JsonObject options, string key)
    {
        if (options is null) return null;
        if (!options.TryGetPropertyValue(key, out var node)) return null;
        if (node is not JsonValue value) return null;
        return value.TryGetValue<bool>(out var parsed) ? parsed : (bool?)null;
    }

    internal static bool DeriveTextureExpected(JsonObject options, ReconstructionModelEntry model)
    {
        if (ReadStrictBool(options, "enable_geometry") == true) return false;   // rule 1
        var pbr = ReadStrictBool(options, "enable_pbr");
        if (pbr == true) return true;                                          // rule 2
        if (pbr == false) return false;                                        // rule 3
        return model.DefaultTextureExpected;                                   // rule 4
    }
```

- [ ] **Step 4: Wire it into `SubmitAsync`**

In `SubmitAsync`, the resolved catalog entry is already in scope as `model` (from `var model = _catalog.Find(request.ModelId);`, non-null after the `IsSubmittableV1Model` guard). Pass the derived flag into `Queued`:

```csharp
        var jobId = Guid.NewGuid();
        var queued = ReconstructionJobLedgerRecord.Queued(
            jobId,
            request.ModelId,
            request.SourceArtifactId,
            request.SourceRole,
            DeriveTextureExpected(request.Options, model!));
        _ledger.Append(queued);
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS (new derivation + persistence facts green; all pre-existing manager tests, including D1's, still green).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): derive and persist TextureExpected at submit (D2)"
```

---

### Task 4: Compute degraded-texture warnings at `Result()`

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (add `BuildTextureWarnings`; wire into `Result()`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionModelEntry.SupportsPbr`/`ModelId` (Task 1); `ReconstructionJobLedgerRecord.TextureExpected` (Task 2); persisted flag (Task 3); `_store.Get(id)!.Files` (each file has `.Role`, per `ReconstructionOpHandler.PackageSummary`); existing `ReconstructionWarning`, `_catalog`.
- Produces: `internal static IReadOnlyList<ReconstructionWarning> BuildTextureWarnings(bool textureExpected, ReconstructionModelEntry? model, IReadOnlyCollection<string> deliveredRoles)`.

- [ ] **Step 1: Write the failing tests**

In `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`, add the warning-matrix unit tests plus two integration tests. (`BuildTextureWarnings` is pure; the integration tests reuse the existing completion path, whose `GlbResultJson` yields a `model_glb`-only package — i.e. no texture/material.)

```csharp
    private static string[] WarningCodes(IReadOnlyList<ReconstructionWarning> ws) => ws.Select(w => w.Code).ToArray();

    [Fact]
    public void BuildTextureWarnings_NotExpected_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(false, ModelEntry(true, supportsPbr: true), new[] { "model_glb" }));

    [Fact]
    public void BuildTextureWarnings_NullModel_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(true, null, new[] { "model_glb" }));

    [Fact]
    public void BuildTextureWarnings_Expected_NoPbrSupport_EmitsPbrUnsupported()
    {
        var ws = ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: false), new[] { "model_glb" });
        Assert.Equal(new[] { "pbr_unsupported_by_model" }, WarningCodes(ws));
    }

    [Fact]
    public void BuildTextureWarnings_Expected_PbrSupported_BareRoles_EmitsMissingTexture()
    {
        var ws = ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: true), new[] { "model_glb", "model_obj" });
        Assert.Equal(new[] { "result_missing_texture" }, WarningCodes(ws));
    }

    [Fact]
    public void BuildTextureWarnings_Expected_PbrSupported_TexturePresent_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: true), new[] { "model_glb", "texture_base_color" }));

    [Fact]
    public void BuildTextureWarnings_Expected_PbrSupported_MaterialOnly_NoWarning()
        => Assert.Empty(ReconstructionJobManager.BuildTextureWarnings(true, ModelEntry(true, supportsPbr: true), new[] { "model_obj", "material_mtl" }));

    [Fact]
    public async Task Result_TextureExpected_BarePackage_EmitsMissingTexture()
    {
        var fixture = CreateFixture();
        fixture.Provider.StatusComplete.Enqueue(true);
        fixture.Provider.ResultJson = GlbResultJson;                 // model_glb only → no texture/material
        fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
        var source = fixture.Store.Create(
            "generated_image",
            new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });
        var submit = await fixture.Manager.SubmitAsync(Request(source.Id), CancellationToken.None);   // enable_pbr:true → expected
        await fixture.Manager.PollActiveJobAsync(submit.Job!.JobId, CancellationToken.None);

        var result = fixture.Manager.Result(submit.Job.JobId);

        Assert.True(result.Success);
        Assert.Contains(result.Warnings, w => w.Code == "result_missing_texture");
    }

    [Fact]
    public void Result_MissingPackage_EmitsArtifactMissingOnly_NoTextureWarning()
    {
        var fixture = CreateFixture();
        var jobId = Guid.NewGuid();
        // Complete job pointing at a non-existent package, with TextureExpected true.
        fixture.Ledger.Append(ReconstructionJobLedgerRecord.Complete(jobId, Guid.NewGuid()) with { TextureExpected = true });

        var result = fixture.Manager.Result(jobId);

        Assert.Contains(result.Warnings, w => w.Code == "result_artifact_missing");
        Assert.DoesNotContain(result.Warnings, w => w.Code == "result_missing_texture");
        Assert.DoesNotContain(result.Warnings, w => w.Code == "pbr_unsupported_by_model");
    }
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: FAIL — `ReconstructionJobManager.BuildTextureWarnings` does not exist (compile error).

- [ ] **Step 3: Add the warning helper**

In `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs`, add the pure helper near `DeriveTextureExpected`:

```csharp
    internal static IReadOnlyList<ReconstructionWarning> BuildTextureWarnings(
        bool textureExpected,
        ReconstructionModelEntry? model,
        IReadOnlyCollection<string> deliveredRoles)
    {
        if (!textureExpected || model is null)
            return Array.Empty<ReconstructionWarning>();

        if (!model.SupportsPbr)
        {
            return new[]
            {
                new ReconstructionWarning(
                    "pbr_unsupported_by_model",
                    $"Texture output was expected for this request, but model '{model.ModelId}' is not "
                    + "catalogued as supporting textured/PBR output. The result may lack materials or textures.",
                    new Dictionary<string, object?>
                    {
                        ["model_id"] = model.ModelId,
                        ["supports_pbr"] = false,
                    }),
            };
        }

        var hasMaterial = deliveredRoles.Any(r => string.Equals(r, ReconstructionFileRoles.MaterialMtl, StringComparison.Ordinal));
        var hasTexture = deliveredRoles.Any(r => r.StartsWith("texture", StringComparison.Ordinal));
        if (hasMaterial || hasTexture)
            return Array.Empty<ReconstructionWarning>();

        return new[]
        {
            new ReconstructionWarning(
                "result_missing_texture",
                "Texture output was expected and this model supports it, but the delivered package "
                + "contains no material or texture assets.",
                new Dictionary<string, object?>
                {
                    ["model_id"] = model.ModelId,
                    ["delivered_roles"] = deliveredRoles.ToArray(),
                }),
        };
    }
```

- [ ] **Step 4: Wire it into `Result()`**

In `Result()`, the existing block handles the missing-package case. Add an `else` branch for the package-present case that reads roles and appends the texture warnings. Replace:

```csharp
        var warnings = new List<ReconstructionWarning>();
        var available = ResultAvailable(job);
        if (job.ResultArtifactId.HasValue && !available)
        {
            warnings.Add(new ReconstructionWarning(
                "result_artifact_missing",
                "The reconstruction package artifact referenced by the job ledger is missing.",
                new Dictionary<string, object?>
                {
                    ["result_artifact_id"] = job.ResultArtifactId.Value.ToString("D"),
                }));
        }
```

with:

```csharp
        var warnings = new List<ReconstructionWarning>();
        var available = ResultAvailable(job);
        if (job.ResultArtifactId.HasValue && !available)
        {
            warnings.Add(new ReconstructionWarning(
                "result_artifact_missing",
                "The reconstruction package artifact referenced by the job ledger is missing.",
                new Dictionary<string, object?>
                {
                    ["result_artifact_id"] = job.ResultArtifactId.Value.ToString("D"),
                }));
        }
        else if (available)
        {
            var roles = _store.Get(job.ResultArtifactId!.Value)!.Files
                .Select(f => f.Role)
                .ToArray();
            warnings.AddRange(BuildTextureWarnings(
                job.TextureExpected,
                _catalog.Find(job.ModelId),
                roles));
        }
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS.

- [ ] **Step 6: Run the full suite (no regressions)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS — full `Rook.Tests` green. (Managed test build deploys `Rook.rhp` into `%AppData%` as a side effect; that is expected, not a failure.)

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): emit degraded-texture warnings at Result() (D2/D3)"
```

---

## Self-Review

**1. Spec coverage:**
- Catalog `default_texture_expected` (new, load-bearing, absent→false) → Task 1. ✓
- `TextureExpected` 4-rule derivation, strict booleans → Task 3 (`DeriveTextureExpected` + unit tests for all 4 rules incl. default true/false + non-bool). ✓
- Persist on ledger; schema v1→v2; **gate relaxed to `1..current`**; v1 absent→false, not dropped → Task 2 (+ explicit legacy-record and future-version tests). ✓
- Result-only warnings, two mutually-exclusive codes, exact messages → Task 4 (`BuildTextureWarnings` + matrix). ✓
- Role check: `material_mtl` / `texture*`; material-only = not degraded → Task 4 unit tests. ✓
- Missing-package precedence (artifact-missing only) → Task 4 `Result_MissingPackage_...`. ✓
- `output_roles` non-load-bearing → role check uses constants, never `OutputRoles`. ✓
- No status/package/MCP/UI change → no such files touched; `Result()` only. ✓
- Review note 1 (centralized helper) → `BuildTextureWarnings` pure + isolated tests. ✓
- Review note 2 (catalog absence test) → Task 1 `DefaultTextureExpected_DefaultsFalse_WhenAbsent`. ✓

**2. Placeholder scan:** No TBD/TODO/vague steps; every code step shows complete code; every run step has an expected outcome. ✓

**3. Type consistency:** `DeriveTextureExpected(JsonObject, ReconstructionModelEntry)` and `BuildTextureWarnings(bool, ReconstructionModelEntry?, IReadOnlyCollection<string>)` are used identically in their tests and call sites. `Queued(..., bool textureExpected = false)` matches the `SubmitAsync` call (5 args) and the existing 4-arg test callers (default applies). `TextureExpected` trailing positional matches all three constructor sites (Queued/Complete/TryDeserialize) and the `with { TextureExpected = true }` usage. `ReconstructionFileRoles.MaterialMtl` is the existing constant. ✓
