# Meshy v6 Single-Image — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `fal-ai/meshy/v6/image-to-3d` reliably submittable and importable through full Rook, behind a narrow submit-time experimental override, with truthful texture/warning behavior for Meshy's option set.

**Architecture:** Pure C# data/validation changes in the reconstruction subsystem plus one MCP schema field. A submit-time `allow_experimental_model` flag threads request→parser→manager gate; the shared options validator gains a `string` kind and boolean-gate `ignored_when`; `DeriveTextureExpected` becomes family-aware so `should_texture` (not `enable_pbr`) owns Meshy texture expectation. The result mapper already walks fal's Meshy payload shape, so §4 is test-only.

**Tech Stack:** C# (.NET, `System.Text.Json.Nodes`), xUnit (`[Fact]`/`[Theory]`), Python MCP server (tool schema only).

## Global Constraints

- Meshy stays `status: "experimental"`, `enabled: true` for all of Step 1 — **no promotion to `stable`**.
- The experimental override is submit-time only: it MUST NOT change catalog visibility (`models` op stays stable-only by default) and MUST NOT affect default/fallback model resolution. It only relaxes the `status=="stable"` clause for an explicitly named `model_id`.
- Spec refinement locked here: the `ignored_when` `equals` value becomes a JSON value (`JsonNode?`) so a boolean gate is expressed as `"equals": false` (not the string `"false"`). Existing string gates (`"equals": "Geometry"`) keep working unchanged.
- TDD: write the failing test first, watch it fail, implement minimally, watch it pass, commit. One logical change per commit.
- Run C# tests with: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
- Source spec: `docs/superpowers/specs/2026-06-24-meshy-v6-single-image-design.md`.

---

## File map

| File | Responsibility | Tasks |
|------|----------------|-------|
| `src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs` | Submit request record + parse `allow_experimental_model` | 1 |
| `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` | `IsSubmittable3DModel` gate + family-aware `DeriveTextureExpected` | 1, 5 |
| `mcp_server/src/rook/server.py` | `rhino_2d_to_3d_submit` schema field | 1 |
| `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs` | `string` kind, reject-unknown-kind, boolean-gate `ignored_when` | 2, 3 |
| `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` | `ReconstructionOptionIgnoredWhen.EqualsValue` → `JsonNode?` | 3 |
| `src/Rook/Handlers/ReconstructionOpHandler.cs` | `OptionToObj` serializes `JsonNode?` equals | 3 |
| `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` | Meshy entry: `image_url`, outputs, options + gates | 4 |
| `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs` | gate + texture-expectation tests | 1, 5 |
| `src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs` | validator string/unknown/bool-gate tests | 2, 3, 4 |
| `src/Rook.Tests/Services/Reconstruction/FalReconstructionResultMapperTests.cs` | Meshy classification coverage | 6 |

---

## Task 1: Submit-time experimental override (the gate)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs` (request record + parse)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs:722-729` (`IsSubmittable3DModel`), `:118` (call site)
- Modify: `mcp_server/src/rook/server.py:12673-12697` (`rhino_2d_to_3d_submit` schema)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces: `ReconstructionSubmitRequest.AllowExperimentalModel` (`bool`, init, default `false`); `internal static bool IsSubmittable3DModel(ReconstructionModelEntry? model, bool allowExperimental = false)`.

- [ ] **Step 1: Write the failing gate tests**

Add to `ReconstructionJobManagerTests.cs` (place near the existing `DeriveTextureExpected` tests). This adds a local helper that builds full catalog entries:

```csharp
    // ReconstructionModelEntry/InputMetadata/PreprocessingMetadata are all POSITIONAL records
    // (verified against ReconstructionModelCatalog.cs). Ctor order:
    // (ModelId, Provider, Task, Status, Enabled, PipelineRoles, InputTypes, OutputRoles,
    //  PreferredAssetRole, FallbackOrder, SupportsPbr, Preprocessing, DocsUrl, DefaultTextureExpected,
    //  Input=null, Prompt=null, Options=null).
    private static ReconstructionModelEntry GateEntry(string status, params string[] outputRoles)
        => new(
            "fal-ai/test/model", "fal", "single_image_to_3d", status, true,
            new[] { "single_image_to_3d" }, new[] { "image_url" }, outputRoles,
            "model_glb", new[] { "model_glb" }, false,
            new ReconstructionPreprocessingMetadata(false, false), "https://example/docs",
            true, new ReconstructionInputMetadata("single_image", "image_url"));

    [Fact]
    public void IsSubmittable3DModel_Experimental_RejectedByDefault()
        => Assert.False(ReconstructionJobManager.IsSubmittable3DModel(GateEntry("experimental", "model_glb")));

    [Fact]
    public void IsSubmittable3DModel_Experimental_AllowedWithFlag()
        => Assert.True(ReconstructionJobManager.IsSubmittable3DModel(GateEntry("experimental", "model_glb"), allowExperimental: true));

    [Fact]
    public void IsSubmittable3DModel_Stable_AllowedRegardlessOfFlag()
    {
        Assert.True(ReconstructionJobManager.IsSubmittable3DModel(GateEntry("stable", "model_glb")));
        Assert.True(ReconstructionJobManager.IsSubmittable3DModel(GateEntry("stable", "model_glb"), allowExperimental: true));
    }

    [Fact]
    public void IsSubmittable3DModel_Experimental_WithFlag_StillNeedsImportableRole()
        => Assert.False(ReconstructionJobManager.IsSubmittable3DModel(GateEntry("experimental", "thumbnail"), allowExperimental: true));
```

The ctor shapes above are verified against `ReconstructionModelCatalog.cs:10-46`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IsSubmittable3DModel"`
Expected: FAIL — `IsSubmittable3DModel` is `private` (inaccessible) and has no `allowExperimental` parameter (compile error).

- [ ] **Step 3: Make the gate internal + add the parameter**

In `ReconstructionJobManager.cs:722-729`, replace:

```csharp
    private static bool IsSubmittable3DModel(ReconstructionModelEntry? model)
        => model is not null
            && model.Enabled
            && string.Equals(model.Status, "stable", StringComparison.OrdinalIgnoreCase)
            && (model.OutputRoles.Contains("model_glb", StringComparer.Ordinal)
                || model.OutputRoles.Contains("model_obj", StringComparer.Ordinal))
            && (!string.IsNullOrWhiteSpace(model.Input?.SourceField)
                || (model.Input?.ViewSlots is { Length: > 0 }));
```

with:

```csharp
    // Capability-based 3D submit gate: enabled + (stable OR explicit experimental override) + has an
    // importable 3D output role (model_glb/model_obj) + accepts input (a source_field, or view_slots).
    // allowExperimental is a submit-time dev/test override; it relaxes ONLY the stable clause and is
    // honored only for an explicitly named model_id (see SubmitAsync). It never affects model resolution.
    internal static bool IsSubmittable3DModel(ReconstructionModelEntry? model, bool allowExperimental = false)
        => model is not null
            && model.Enabled
            && (allowExperimental || string.Equals(model.Status, "stable", StringComparison.OrdinalIgnoreCase))
            && (model.OutputRoles.Contains("model_glb", StringComparer.Ordinal)
                || model.OutputRoles.Contains("model_obj", StringComparer.Ordinal))
            && (!string.IsNullOrWhiteSpace(model.Input?.SourceField)
                || (model.Input?.ViewSlots is { Length: > 0 }));
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~IsSubmittable3DModel"`
Expected: PASS (4 tests).

- [ ] **Step 5: Thread the flag through the request + parser (failing tests first)**

Add to `ReconstructionJobManagerTests.cs` (or a parser test file if one exists — otherwise here). Note the strictness test: an existing-but-non-bool value must be REJECTED, not silently treated as absent (the parser's `ReadBool` returns null for a non-bool, which would otherwise pass as default false):

```csharp
    [Fact]
    public void Parse_ReadsAllowExperimentalModel_DefaultsFalse()
    {
        var withFlag = ReconstructionSubmitRequestParser.Parse(
            @"{""source_artifact_id"":""" + Guid.NewGuid() + @""",""model_id"":""m"",""allow_experimental_model"":true}");
        Assert.True(withFlag.Success);
        Assert.True(withFlag.Request!.AllowExperimentalModel);

        var without = ReconstructionSubmitRequestParser.Parse(
            @"{""source_artifact_id"":""" + Guid.NewGuid() + @""",""model_id"":""m""}");
        Assert.True(without.Success);
        Assert.False(without.Request!.AllowExperimentalModel);
    }

    [Fact]
    public void Parse_RejectsNonBoolAllowExperimentalModel()
    {
        var result = ReconstructionSubmitRequestParser.Parse(
            @"{""source_artifact_id"":""" + Guid.NewGuid() + @""",""model_id"":""m"",""allow_experimental_model"":""true""}");
        Assert.False(result.Success);
        Assert.Equal("allow_experimental_model", result.Failure!.Field);
    }
```

- [ ] **Step 6: Run to verify failure**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~AllowExperimentalModel"`
Expected: FAIL — `ReconstructionSubmitRequest` has no `AllowExperimentalModel` member (compile error).

- [ ] **Step 7: Add the request field + strict parse**

In `ReconstructionSubmitRequestParser.cs`, add the init property to the request record (alongside `Views`, lines 14-22):

```csharp
    /// <summary>
    /// Submit-time dev/test override: when true AND an explicit model_id is supplied, an experimental
    /// catalog model passes the 3D submit gate. Default false. Never affects model resolution.
    /// </summary>
    public bool AllowExperimentalModel { get; init; }
```

In the `Parse` method, before the `return` that constructs the request, add a STRICT read (reject a present-but-non-bool value rather than silently defaulting — `ReadBool` is too lenient for this):

```csharp
        var allowExperimental = false;
        if (root.TryGetPropertyValue("allow_experimental_model", out var allowNode) && allowNode is not null)
        {
            if (allowNode is JsonValue allowValue && allowValue.TryGetValue<bool>(out var allowFlag))
                allowExperimental = allowFlag;
            else
                return Fail("invalid_request", "allow_experimental_model must be a boolean.", "allow_experimental_model");
        }
```

and extend the object initializer (currently `{ Views = views, }`) to:

```csharp
            {
                Views = views,
                AllowExperimentalModel = allowExperimental,
            },
```

- [ ] **Step 8: Wire the flag into the gate at the call site**

In `ReconstructionJobManager.cs:118`, replace `if (!IsSubmittable3DModel(model))` with:

```csharp
        if (!IsSubmittable3DModel(model, request.AllowExperimentalModel))
```

- [ ] **Step 9: Run to verify pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Parse_ReadsAllowExperimentalModel"`
Expected: PASS.

- [ ] **Step 10: Add the MCP schema field**

In `mcp_server/src/rook/server.py`, inside the `rhino_2d_to_3d_submit` tool's `inputSchema.properties` (after the `estimate_requested` property, ~line 12692), add:

```python
                    "allow_experimental_model": {
                        "type": "boolean",
                        "description": (
                            "Dev/test override: allow submitting an experimental catalog model. "
                            "Honored only with an explicit model_id; never affects default model "
                            "resolution. Omit for normal use."
                        ),
                    },
```

- [ ] **Step 11: Run the full reconstruction suite + commit**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Reconstruction"`
Expected: PASS (no regressions).

```bash
git add src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs src/Rook/Services/Reconstruction/ReconstructionJobManager.cs mcp_server/src/rook/server.py src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): submit-time allow_experimental_model override for the 3D gate"
```

---

## Task 2: Validator — `string` option kind + reject unknown kinds (§2a)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs:70-92` (`ValidateValue`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs`

**Interfaces:**
- Consumes: `ReconstructionOptionsValidator.Validate(JsonObject, ReconstructionModelEntry)` (unchanged signature).
- Produces: `ValidateValue` now accepts `kind == "string"` and rejects any other (unknown) kind.

- [ ] **Step 1: Write the failing tests**

Add to `ReconstructionOptionsValidatorTests.cs`. These use a small local model with a string option and an unknown-kind option:

```csharp
    // Positional ctor (verified ReconstructionModelCatalog.cs:10-46); Options is the last positional arg.
    private static ReconstructionModelEntry ModelWithOptions(params ReconstructionOptionDescriptor[] options)
        => new(
            "test/model", "fal", "single_image_to_3d", "experimental", true,
            new[] { "single_image_to_3d" }, new[] { "image_url" }, new[] { "model_glb" },
            "model_glb", new[] { "model_glb" }, false,
            new ReconstructionPreprocessingMetadata(false, false), "https://example/docs",
            true, new ReconstructionInputMetadata("single_image", "image_url"), null, options);

    private static ReconstructionModelEntry StringOptModel()
        => ModelWithOptions(new ReconstructionOptionDescriptor(
            "texture_prompt", "Texture Prompt", "string"));

    private static ReconstructionModelEntry UnknownKindModel()
        => ModelWithOptions(new ReconstructionOptionDescriptor(
            "weird", "Weird", "color"));

    [Fact]
    public void Validate_AcceptsStringOption()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["texture_prompt"] = "a red ceramic mug" }, StringOptModel());
        Assert.True(result.Success);
        Assert.Equal("a red ceramic mug", result.Options["texture_prompt"]!.GetValue<string>());
    }

    [Fact]
    public void Validate_RejectsNonStringForStringOption()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["texture_prompt"] = 7 }, StringOptModel());
        Assert.False(result.Success);
    }

    [Fact]
    public void Validate_RejectsUnknownOptionKind()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["weird"] = "x" }, UnknownKindModel());
        Assert.False(result.Success);
    }
```

`ModelWithOptions` is defined inline above; `ReconstructionOptionDescriptor` is positional (`Key, Label, Kind, Default=null, ...`).

- [ ] **Step 2: Run to verify failure**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOptionsValidator"`
Expected: FAIL — `Validate_RejectsNonStringForStringOption` and `Validate_RejectsUnknownOptionKind` fail because the current `default:` arm returns `null` (silently passes); `Validate_AcceptsStringOption` passes only incidentally.

- [ ] **Step 3: Add the `string` case and reject unknown kinds**

In `ReconstructionOptionsValidator.cs`, in the `ValidateValue` switch, add a `string` case before `default` and change `default` to reject:

```csharp
            case "string":
                if (node is not JsonValue sv || !sv.TryGetValue<string>(out _))
                    return $"'{d.Key}' must be a string.";
                return null;
            default:
                return $"'{d.Key}' has an unsupported option kind '{d.Kind}'.";
```

- [ ] **Step 4: Run to verify pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOptionsValidator"`
Expected: PASS (all, including the three new tests and the existing enum/boolean/integer tests).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs
git commit -m "feat(reconstruction): validated string option kind; reject unknown option kinds"
```

---

## Task 3: Validator — boolean-gate `ignored_when` (§2b)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` (`ReconstructionOptionIgnoredWhen.EqualsValue` → `JsonNode?`)
- Modify: `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs:55-65` (gate comparison)
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs:903-909` (`OptionToObj` — only if a test breaks; verify)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs` (new bool-gate tests), `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs:69` (existing assertion fix)

**Interfaces:**
- Produces: `ReconstructionOptionIgnoredWhen(string Key, JsonNode? EqualsValue)`; the validator omits an option when its sibling gate's JSON value (string OR bool) equals `EqualsValue`.

- [ ] **Step 1: Write the failing tests**

Add to `ReconstructionOptionsValidatorTests.cs`:

```csharp
    // Model with should_texture (bool) + enable_pbr (bool, omitted when should_texture==false).
    private static ReconstructionModelEntry BoolGateModel()
        => ModelWithOptions(
            new ReconstructionOptionDescriptor("should_texture", "Should Texture", "boolean",
                Default: JsonValue.Create(true)),
            new ReconstructionOptionDescriptor("enable_pbr", "Enable PBR", "boolean",
                Default: JsonValue.Create(false),
                IgnoredWhen: new ReconstructionOptionIgnoredWhen("should_texture", JsonValue.Create(false))));

    [Fact]
    public void Validate_OmitsEnablePbr_WhenShouldTextureFalse()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["should_texture"] = false, ["enable_pbr"] = true }, BoolGateModel());
        Assert.True(result.Success);
        Assert.False(result.Options.ContainsKey("enable_pbr")); // bool gate matched → omitted
    }

    [Fact]
    public void Validate_KeepsEnablePbr_WhenShouldTextureTrue()
    {
        var result = ReconstructionOptionsValidator.Validate(
            new JsonObject { ["should_texture"] = true, ["enable_pbr"] = true }, BoolGateModel());
        Assert.True(result.Success);
        Assert.True(result.Options["enable_pbr"]!.GetValue<bool>());
    }
```

The existing `Validate_OmitsEnablePbr_WhenGeometry` test (string gate, `generate_type=="Geometry"`) is the regression guard and must keep passing.

- [ ] **Step 2: Run to verify failure**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ShouldTexture"`
Expected: FAIL — `ReconstructionOptionIgnoredWhen`'s second argument is `string`, so `JsonValue.Create(false)` is a compile error.

- [ ] **Step 3: Change `EqualsValue` to `JsonNode?`**

In `ReconstructionModelCatalog.cs`, change the `ReconstructionOptionIgnoredWhen` record:

```csharp
public sealed record ReconstructionOptionIgnoredWhen(
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("equals")] JsonNode? EqualsValue);
```

(The file already imports `System.Text.Json.Nodes` for `ReconstructionOptionDescriptor.Default`.)

- [ ] **Step 3b: Update the existing catalog test that reads `EqualsValue` as a string**

`ReconstructionModelCatalogTests.cs:69` currently asserts `Assert.Equal("Geometry", pbr.IgnoredWhen.EqualsValue);` — this no longer compiles once `EqualsValue` is `JsonNode?` (and the whole test assembly fails to build until fixed). Change it to read the node's value:

```csharp
        Assert.Equal("Geometry", pbr.IgnoredWhen!.EqualsValue!.GetValue<string>());
```

- [ ] **Step 4: Make the gate comparison type-aware**

In `ReconstructionOptionsValidator.cs`, replace the `ignored_when` omission block (lines ~55-65):

```csharp
        // Omit ignored options.
        foreach (var d in descriptors)
        {
            if (d.IgnoredWhen is null) continue;
            if (effective.TryGetPropertyValue(d.IgnoredWhen.Key, out var gate)
                && gate is JsonValue gv
                && JsonValueEquals(gv, d.IgnoredWhen.EqualsValue))
            {
                effective.Remove(d.Key);
            }
        }
```

and add this helper (next to `TryGetLong`):

```csharp
    // Type-aware equality for an ignored_when gate: matches a string gate (generate_type=="Geometry")
    // or a boolean gate (should_texture==false). Any other JSON kind never matches.
    private static bool JsonValueEquals(JsonValue gate, JsonNode? expected)
    {
        if (expected is not JsonValue ev) return false;
        if (gate.TryGetValue<string>(out var gs) && ev.TryGetValue<string>(out var es))
            return string.Equals(gs, es, StringComparison.Ordinal);
        if (gate.TryGetValue<bool>(out var gb) && ev.TryGetValue<bool>(out var eb))
            return gb == eb;
        return false;
    }
```

- [ ] **Step 5: Run to verify pass (including the string-gate regression)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOptionsValidator"`
Expected: PASS — the two new bool-gate tests AND the existing `Validate_OmitsEnablePbr_WhenGeometry` string-gate test.

- [ ] **Step 6: Verify the `OptionToObj` serializer still compiles/serializes**

`ReconstructionOpHandler.cs:908` is `["equals"] = option.IgnoredWhen.EqualsValue;` — now a `JsonNode?` value in a `Dictionary<string, object?>`, which serializes natively. No code change is required. Check for any test asserting `OptionToObj(...)["equals"]` as a `string`:

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ModelToObj|FullyQualifiedName~OptionToObj"`
Expected: PASS. If a test casts `equals` to `string`, update it to read the `JsonNode` value (`.GetValue<string>()`).

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs
git commit -m "feat(reconstruction): boolean-gate ignored_when (omit dependent options on bool sibling)"
```

---

## Task 4: Meshy v6 catalog entry (§2)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json:71-97` (Meshy entry)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs` (production-shape), `src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs` (options behavior)

**Interfaces:**
- Consumes: validated `string` kind (Task 2) and boolean-gate `ignored_when` (Task 3).
- Produces: a Meshy entry whose `source_field` is `image_url`, whose `output_roles` advertise glb/obj/fbx/usdz/texture/thumbnail, and whose options validate/default/omit correctly.

**Note:** `ReconstructionModelCatalog`'s only entry point is `FromJson(string)` (private ctor) — `new ReconstructionModelCatalog()` does NOT compile. Tests load the shipped catalog from the embedded resource, exactly as `ReconstructionModelCatalogTests.ProductionCatalog()` already does.

- [ ] **Step 1: Write the failing tests (split by concern)**

**(A) Catalog-shape tests** — add to `ReconstructionModelCatalogTests.cs`, reusing its existing `ProductionCatalog()` helper (`ReconstructionModelCatalogTests.cs:15-24`):

```csharp
    [Fact]
    public void ProductionCatalog_Meshy_SourceFieldIsImageUrl()
        => Assert.Equal("image_url", ProductionCatalog().Find("fal-ai/meshy/v6/image-to-3d")!.Input!.SourceField);

    [Fact]
    public void ProductionCatalog_Meshy_AdvertisesObjFbxUsdzOutputs()
    {
        var roles = ProductionCatalog().Find("fal-ai/meshy/v6/image-to-3d")!.OutputRoles;
        Assert.Contains("model_obj", roles);
        Assert.Contains("model_fbx", roles);
        Assert.Contains("model_usdz", roles);
    }

    [Fact]
    public void ProductionCatalog_Meshy_StaysExperimental_WithOptionKeys()
    {
        var meshy = ProductionCatalog().Find("fal-ai/meshy/v6/image-to-3d")!;
        Assert.Equal("experimental", meshy.Status);
        Assert.Equal(
            new[] { "topology", "target_polycount", "symmetry_mode", "should_remesh", "should_texture", "enable_pbr", "texture_prompt" },
            meshy.Options!.Select(o => o.Key).ToArray());
    }
```

**(B) Options-behavior tests** — add to `ReconstructionOptionsValidatorTests.cs`, with a local production-catalog loader mirroring `ReconstructionModelCatalogTests.ProductionCatalog()`:

```csharp
    private static ReconstructionModelEntry MeshyEntry()
    {
        var assembly = typeof(ReconstructionModelEntry).Assembly;
        using var stream = assembly.GetManifestResourceStream(
            "Rook.Services.Reconstruction.Fal.fal-model-catalog.json")!;
        using var reader = new System.IO.StreamReader(stream);
        return ReconstructionModelCatalog.FromJson(reader.ReadToEnd())
            .Find("fal-ai/meshy/v6/image-to-3d")!;
    }

    [Fact]
    public void MeshyOptions_DefaultsFillTopologyAndShouldTexture()
    {
        var result = ReconstructionOptionsValidator.Validate(new JsonObject(), MeshyEntry());
        Assert.True(result.Success);
        Assert.Equal("triangle", result.Options["topology"]!.GetValue<string>());
        Assert.True(result.Options["should_texture"]!.GetValue<bool>());
    }

    [Fact]
    public void MeshyOptions_OmitEnablePbrAndTexturePrompt_WhenShouldTextureFalse()
    {
        var submitted = new JsonObject
        {
            ["should_texture"] = false,
            ["enable_pbr"] = true,
            ["texture_prompt"] = "ignored",
        };
        var result = ReconstructionOptionsValidator.Validate(submitted, MeshyEntry());
        Assert.True(result.Success);
        Assert.False(result.Options.ContainsKey("enable_pbr"));
        Assert.False(result.Options.ContainsKey("texture_prompt"));
    }
```

- [ ] **Step 2: Run to verify failure**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Meshy"`
Expected: FAIL — `ProductionCatalog_Meshy_SourceFieldIsImageUrl` fails (`source_field` is still `input_image_url`); the option/output tests fail (options block + obj/fbx/usdz absent).

- [ ] **Step 3: Replace the Meshy catalog entry**

In `fal-model-catalog.json`, replace the Meshy object (lines 71-97) with:

```json
    {
      "model_id": "fal-ai/meshy/v6/image-to-3d",
      "provider": "fal",
      "task": "single_image_to_3d",
      "status": "experimental",
      "enabled": true,
      "pipeline_roles": ["single_image_to_3d"],
      "input_types": ["image_url"],
      "output_roles": ["model_glb", "model_obj", "model_fbx", "model_usdz", "texture", "thumbnail"],
      "preferred_asset_role": "model_glb",
      "fallback_order": ["model_glb", "model_obj"],
      "supports_pbr": true,
      "default_texture_expected": true,
      "input": {
        "mode": "single_image",
        "source_field": "image_url"
      },
      "prompt": { "supported": true, "required": false, "kind": "texture" },
      "preprocessing": { "recommended": false, "required": false },
      "options": [
        { "key": "topology", "label": "Topology", "kind": "enum",
          "default": "triangle", "allowed_values": ["quad", "triangle"] },
        { "key": "target_polycount", "label": "Target Polycount", "kind": "integer",
          "default": 30000, "min": 100 },
        { "key": "symmetry_mode", "label": "Symmetry Mode", "kind": "enum",
          "default": "auto", "allowed_values": ["off", "auto", "on"] },
        { "key": "should_remesh", "label": "Should Remesh", "kind": "boolean", "default": true },
        { "key": "should_texture", "label": "Should Texture", "kind": "boolean", "default": true },
        { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean", "default": false,
          "ignored_when": { "key": "should_texture", "equals": false } },
        { "key": "texture_prompt", "label": "Texture Prompt", "kind": "string",
          "ignored_when": { "key": "should_texture", "equals": false } }
      ],
      "docs_url": "https://fal.ai/models/fal-ai/meshy/v6/image-to-3d/api"
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Meshy"`
Expected: PASS (5 new tests). Also run the full catalog suite to confirm no production-shape regression: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalog"`.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs
git commit -m "feat(reconstruction): Meshy v6 catalog -- image_url, expanded outputs, structured options"
```

---

## Task 5: Family-aware `DeriveTextureExpected` (§3)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs:831-846` (`DeriveTextureExpected`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionModelEntry.Options` to detect the `should_texture` family; reads the effective (validated, default-filled) options object (`DeriveTextureExpected` is called at `:232`, after validation at `:134-137`).
- Produces: for a model declaring `should_texture`, texture expectation = explicit `should_texture` value, else `DefaultTextureExpected`; `enable_pbr`/`enable_geometry` legacy rules are NOT consulted for that model. Hunyuan paths unchanged.

- [ ] **Step 1: Write the failing tests**

Add to `ReconstructionJobManagerTests.cs`. These need a model that declares `should_texture`:

```csharp
    private static ReconstructionModelEntry ShouldTextureModel(bool defaultTextureExpected)
        => GateEntry("experimental", "model_glb") with
        {
            DefaultTextureExpected = defaultTextureExpected,
            Options = new[]
            {
                new ReconstructionOptionDescriptor("should_texture", "Should Texture", "boolean",
                    Default: JsonValue.Create(true)),
                new ReconstructionOptionDescriptor("enable_pbr", "Enable PBR", "boolean",
                    Default: JsonValue.Create(false)),
            },
        };

    [Fact]
    public void DeriveTextureExpected_ShouldTextureFalse_IsFalse_EvenIfPbrTrue()
        => Assert.False(ReconstructionJobManager.DeriveTextureExpected(
            Opts(@"{""should_texture"":false,""enable_pbr"":true}"), ShouldTextureModel(true)));

    [Fact]
    public void DeriveTextureExpected_ShouldTextureTrue_IsTrue()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(
            Opts(@"{""should_texture"":true}"), ShouldTextureModel(false)));

    [Fact]
    public void DeriveTextureExpected_ShouldTextureAbsent_UsesCatalogDefault()
    {
        Assert.True(ReconstructionJobManager.DeriveTextureExpected(Opts("{}"), ShouldTextureModel(true)));
        Assert.False(ReconstructionJobManager.DeriveTextureExpected(Opts("{}"), ShouldTextureModel(false)));
    }

    [Fact]
    public void DeriveTextureExpected_ShouldTextureModel_IgnoresEnablePbrFalse()
        => Assert.True(ReconstructionJobManager.DeriveTextureExpected(
            Opts(@"{""should_texture"":true,""enable_pbr"":false}"), ShouldTextureModel(true)));
```

These four MUST coexist with the existing Hunyuan tests (`DeriveTextureExpected_PbrTrue_IsTrue`, `_PbrFalse_IsFalse`, `_GeometryTrue_IsFalse`, `_Omitted_UsesCatalogDefault*`) — those are the regression guard.

- [ ] **Step 2: Run to verify failure**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~DeriveTextureExpected"`
Expected: FAIL — `DeriveTextureExpected_ShouldTextureFalse_IsFalse_EvenIfPbrTrue` returns `true` today (hits the legacy `enable_pbr==true ⇒ true` rule).

- [ ] **Step 3: Make `DeriveTextureExpected` family-aware**

In `ReconstructionJobManager.cs:831-846`, replace the method body:

```csharp
    internal static bool DeriveTextureExpected(JsonObject options, ReconstructionModelEntry model)
    {
        // Catalog-described (Pro) path: generate_type drives texture expectation. Normal expects a
        // texture even when enable_pbr=false; Geometry never does.
        if (ReadString(options, "generate_type") is { } generateType)
        {
            if (string.Equals(generateType, "Geometry", StringComparison.Ordinal)) return false;
            if (string.Equals(generateType, "Normal", StringComparison.Ordinal)) return true;
        }

        // Meshy family: once the model declares should_texture, that option OWNS texture expectation
        // and the legacy enable_pbr/enable_geometry rules do NOT apply (enable_pbr only selects which
        // maps, not whether texturing happens).
        if (ModelDeclaresOption(model, "should_texture"))
        {
            var shouldTexture = ReadStrictBool(options, "should_texture");
            if (shouldTexture == true) return true;
            if (shouldTexture == false) return false;
            return model.DefaultTextureExpected;
        }

        if (ReadStrictBool(options, "enable_geometry") == true) return false;   // legacy rule 1
        var pbr = ReadStrictBool(options, "enable_pbr");
        if (pbr == true) return true;                                          // legacy rule 2
        if (pbr == false) return false;                                        // legacy rule 3
        return model.DefaultTextureExpected;                                   // legacy rule 4
    }

    private static bool ModelDeclaresOption(ReconstructionModelEntry model, string key)
        => model.Options is { } opts
            && opts.Any(o => string.Equals(o.Key, key, StringComparison.Ordinal));
```

(Confirm `System.Linq` is imported in the file; it is used elsewhere in the manager.)

- [ ] **Step 4: Run to verify pass (new + Hunyuan regression)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~DeriveTextureExpected"`
Expected: PASS — all four new tests AND the existing Hunyuan tests.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): family-aware DeriveTextureExpected (should_texture owns Meshy expectation)"
```

---

## Task 6: Meshy result classification coverage (§4)

**Files:**
- Test: `src/Rook.Tests/Services/Reconstruction/FalReconstructionResultMapperTests.cs`
- Modify (only if a test fails): `src/Rook/Services/Reconstruction/Fal/FalReconstructionResultMapper.cs`

**Interfaces:**
- Consumes: `FalReconstructionResultMapper.MapArtifacts(JsonNode)` → `IReadOnlyList<ResultArtifact>` (each has a `Role`).

**Context:** The mapper already walks fal's documented Meshy shape — top-level `model_glb`/`texture`, `model_urls.{glb,obj,mtl,fbx,usdz}` (`FalReconstructionResultMapper.cs:60-90`), and `texture_urls` as an array via `EnumerateFiles` (`:93-94`, `:153-171`), each texture routed through `ClassifyTextureRole`. These tests assert that coverage; no mapper change is expected.

- [ ] **Step 1: Write the classification tests against a Meshy-shaped body**

Add to `FalReconstructionResultMapperTests.cs` (create the file if absent, mirroring existing mapper-test conventions):

```csharp
    private static IReadOnlyList<ResultArtifact> Map(string json)
        => FalReconstructionResultMapper.MapArtifacts(JsonNode.Parse(json)!);

    [Fact]
    public void MapArtifacts_MeshyShape_ClassifiesModelsAndTextures()
    {
        // fal Meshy v6: model_glb (top-level) + model_urls{glb,obj,fbx,usdz} + texture_urls[] (array).
        const string body = @"{
            ""model_glb"": { ""url"": ""https://cdn.fal/m.glb"", ""file_name"": ""m.glb"" },
            ""model_urls"": {
                ""glb"": { ""url"": ""https://cdn.fal/m.glb"" },
                ""obj"": { ""url"": ""https://cdn.fal/m.obj"", ""file_name"": ""m.obj"" },
                ""fbx"": { ""url"": ""https://cdn.fal/m.fbx"", ""file_name"": ""m.fbx"" },
                ""usdz"": { ""url"": ""https://cdn.fal/m.usdz"", ""file_name"": ""m.usdz"" }
            },
            ""texture_urls"": [
                { ""url"": ""https://cdn.fal/base_color.png"", ""file_name"": ""base_color.png"" },
                { ""url"": ""https://cdn.fal/normal.png"", ""file_name"": ""normal.png"" }
            ]
        }";
        var roles = Map(body).Select(a => a.Role).ToList();
        Assert.Contains("model_glb", roles);
        Assert.Contains("model_obj", roles);
        Assert.Contains("model_fbx", roles);
        Assert.Contains("model_usdz", roles);
        Assert.Contains("texture_base_color", roles);
        Assert.Contains("texture_normal", roles);
    }

    [Fact]
    public void MapArtifacts_MeshyGeometryOnly_HasModelNoTexture()
    {
        const string body = @"{ ""model_glb"": { ""url"": ""https://cdn.fal/m.glb"", ""file_name"": ""m.glb"" } }";
        var roles = Map(body).Select(a => a.Role).ToList();
        Assert.Contains("model_glb", roles);
        Assert.DoesNotContain(roles, r => r.StartsWith("texture", StringComparison.Ordinal));
    }
```

- [ ] **Step 2: Run the tests**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~MapArtifacts_Meshy"`
Expected: PASS (the mapper already handles this shape). **If any role is missing**, that is a real gap — fix it in `FalReconstructionResultMapper.cs` (e.g. extend `RoleForModelExtension`/`EnumerateFiles`) and re-run until green. Do not weaken the assertions.

- [ ] **Step 3: Commit**

```bash
git add src/Rook.Tests/Services/Reconstruction/FalReconstructionResultMapperTests.cs
git commit -m "test(reconstruction): Meshy v6 model_urls/texture_urls classification coverage"
```

---

## Task 7: Live smoke (paid integration gate)

**This task is a manual, documented procedure — not an automated test.** It is the merge gate and produces the artifact that later gates `experimental → stable`.

**Preconditions:** Built and deployed Release build (managed) per the repo's deploy procedure; a fal API key configured; Rhino running with the Rook plugins loaded; `rhino_ping` returns pong.

- [ ] **Step 1: Confirm the deterministic suite is green**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS (full suite). The paid call must only prove integration, not branch coverage.

- [ ] **Step 2: Drive one real textured Meshy job through full Rook**

Use the MCP tools (or chat) against the deployed build:
1. Produce/choose a source image artifact (e.g. `rhino_render_view` or an imported image).
2. Submit: `rhino_2d_to_3d_submit` with `model_id="fal-ai/meshy/v6/image-to-3d"`, `allow_experimental_model=true`, `options={"should_texture": true}`.
3. Poll: `rhino_2d_to_3d_status` until complete; fetch `rhino_2d_to_3d_result`.
4. Import: `rhino_2d_to_3d_import`.

- [ ] **Step 3: Assert the acceptance checklist (record results)**

Verify and record each, per the spec's §6:
1. Job reaches `completed`.
2. Package materializes; the **preferred importable asset** is present; delivered `model_urls`/`texture_urls` are classified (inspect `rhino_2d_to_3d_result`).
3. `resolved_import_role` equals the role native import consumes (parity).
4. Rhino import: object count `0 → N` (check `rhino_document`/`rhino_objects`), non-degenerate bbox (`rhino_measure_bbox`).
5. Texture present on the imported mesh; **no false warnings** in the result.

- [ ] **Step 4: Record the smoke artifact + commit**

Append a "Live smoke result (YYYY-MM-DD)" section to `docs/superpowers/specs/2026-06-24-meshy-v6-single-image-design.md` with: job id, package id, delivered roles, `resolved_import_role`, object count/bbox, and warnings observed (expected: none). This is the documented artifact gating future promotion.

```bash
git add docs/superpowers/specs/2026-06-24-meshy-v6-single-image-design.md
git commit -m "docs(reconstruction): Meshy v6 single-image live smoke result"
```

> **Out of scope (explicitly):** promotion to `stable` (a later catalog-only follow-up), multi-image, mesh-input/3D→3D. Do not flip Meshy's `status` in this plan.

---

## Self-Review

**Spec coverage:**
- §1 submit-time override → Task 1 (request/parser/gate/MCP). Invariants: stable-only `models` default is unchanged (no edit to `Models`/`List`); explicit-`model_id` requirement is pre-existing (parser fails without `model_id`); no fallback resolution touched. ✓
- §2 catalog metadata + options → Task 4; §2a string kind → Task 2; §2b boolean-gate `ignored_when` → Task 3. ✓
- §3 family-aware texture expectation → Task 5. ✓
- §4 classification coverage → Task 6. ✓
- §5 verification split → deterministic tests across Tasks 1–6; one live smoke in Task 7. ✓
- §6 acceptance checklist → Task 7 Step 3. ✓

**Placeholder scan:** no TBD/TODO; every code step shows real code. Previously-guarded uncertainties are now resolved against source: positional ctors (`ReconstructionModelCatalog.cs:10-46`), catalog load via `FromJson` + embedded-resource `ProductionCatalog()` (`ReconstructionModelCatalogTests.cs:15-24`), strict non-bool rejection for `allow_experimental_model`, and the `EqualsValue`→`JsonNode?` ripple into `ReconstructionModelCatalogTests.cs:69`.

**Type consistency:** `AllowExperimentalModel` (bool, init) used consistently in Task 1; `IsSubmittable3DModel(model, allowExperimental)` signature matches its call site; `ReconstructionOptionIgnoredWhen.EqualsValue` is `JsonNode?` everywhere after Task 3 (record, validator helper `JsonValueEquals`, serializer); `DeriveTextureExpected(JsonObject, ReconstructionModelEntry)` signature unchanged, internal helper `ModelDeclaresOption` added; `ClassifyTextureRole` role names (`texture_base_color`, `texture_normal`) match Task 6 assertions and `FalReconstructionResultMapper.cs:231-236`.
