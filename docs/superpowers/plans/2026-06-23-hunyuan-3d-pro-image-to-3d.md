# Hunyuan 3D Pro (multi-view image-to-3D) Implementation Plan

> **DIRECTOR HISTORICAL EVIDENCE — classified 2026-07-13:** Director routes,
> tool names, and workflows below are retained only as dated evidence. They are not
> current instructions and must not be used to restore a Director MCP tool. See the
> [Director MCP Surface Retirement Design][director-mcp-retirement].

[director-mcp-retirement]: ../specs/2026-07-13-director-mcp-surface-retirement-design.md

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add full support for Fal's Hunyuan 3D Pro image-to-3D model (`fal-ai/hunyuan-3d/v3.1/pro/image-to-3d`) — labeled multi-view submit, catalog-driven options (Generate Type / Enable PBR / Face Count), generate-type-driven texture expectation, and UI in both I3D and MV3D modes.

**Architecture:** Catalog metadata (not task taxonomy) declares Pro's capabilities: a `view_slots` map (slot→Fal field) and a bounded `options` descriptor block. The submit request gains an inline `views[]` carrier; `source_artifact_id`+`source_role` remain the sole canonical front. The manager resolves slot→artifact, publishes every labeled image, and the provider writes each URL to its named Fal field. Options are validated + default-filled in the manager before submit so texture prediction and the Fal payload never diverge. UI controls render from catalog metadata. Pro ships `experimental` and flips to `stable` behind a live roundtrip gate.

**Tech Stack:** C# (.NET, `System.Text.Json` + `System.Text.Json.Nodes`), xUnit (`[Fact]`/`[Theory]`, `Assert.*`), vanilla JS/HTML/CSS Vision web surface (asserted via source-string tests).

## Global Constraints

- New feature branch off `main`; current branch `feature/hunyuan-3d-pro-image-to-3d` is already that branch — do **not** use the old RookVisionDirector branch.
- Do **not** modify native `vcxproj`/`vcxproj.filters` (no native build changes).
- **No new external dependencies.**
- Managed companion owns UI resources under `src/Rook/UI/Vision/Resources/`.
- Follow existing reconstruction patterns and tests; mirror `ReconstructionViewSetRequest.TryParse`'s per-field typed-read style for new parsing.
- Build the canonical tree under `src/` — ignore the stale `.worktrees/reconstruction-2d-to-3d/` copy entirely.
- Pro stays `experimental` until Slice 4. Slices 2–3 test UI behavior using **scaffold source tests** (structural, catalog-status-independent) and synthetic **stable** catalog entries in backend tests; default UI visibility waits for the Slice 4 stable flip. Manual dev verification in Slices 1–3 surfaces Pro via `include_experimental=true`.
- Texture expectation is driven by `generate_type`: `Geometry` ⇒ no texture; `Normal` ⇒ texture expected even when `enable_pbr=false`; `enable_pbr=true` ⇒ PBR requested (default off); `enable_pbr` under `Geometry` is ignored/omitted, never an error.
- Front rule (immutable invariant): `source_artifact_id` + `source_role` are the only canonical front. A `views[]` entry with `slot=="front"` is accepted **only if** its `artifact_id == source_artifact_id` **AND** its `role` is absent or equals `source_role`; it never overrides either. Any artifact-or-role mismatch → `invalid_request` / `conflicting_front`.

**Spec:** `docs/superpowers/specs/2026-06-23-hunyuan-3d-pro-image-to-3d-design.md`

---

## File Structure

**Backend (modify):**
- `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs` — new option-descriptor types; `Options` on `ReconstructionModelEntry`.
- `src/Rook/Services/Reconstruction/ReconstructionContracts.cs` — new `ReconstructionFileRoles`/`ReconstructionViewSlots` constants only. **Note:** the `ReconstructionSubmitRequest` / `ReconstructionParseResult` / `ReconstructionPreprocessingStageRequest` records are **not** here — they live in `ReconstructionSubmitRequestParser.cs`.
- `src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs` — `ReconstructionViewRequest` (new co-located contract type); `Views` on the existing `ReconstructionSubmitRequest` record (declared here at line 8); parse `views[]`.
- `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs` — `ReconstructionProviderViewUrl`; `ViewUrls` on the provider request; `BuildSubmitPayload` multi-field.
- `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` — capability gate, options validation wiring, multi-view resolution/publish, `DeriveTextureExpected` rework, materializer provenance.
- `src/Rook/Handlers/ReconstructionOpHandler.cs` — `OptionToObj`, capability flags, capability-based picker filter.
- `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json` — Pro entry.

**Backend (create):**
- `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs` — shared validator + default-fill.

**UI (modify):**
- `src/Rook/UI/Vision/Resources/index.html`, `app.js`, `styles.css`.

**Tests (modify/create):** mirror under `src/Rook.Tests/Services/Reconstruction/...`, `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`, `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`.

---

# SLICE 1 — Backend machinery + experimental catalog

Each task is shippable and green. Pro is `experimental`, so it is not prod-submittable yet; full unit coverage uses a synthetic **stable** Pro entry in test catalogs.

---

### Task 1.1: Catalog option-descriptor types + deserialization

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs`

**Interfaces:**
- Produces:
  - `public sealed record ReconstructionOptionDescriptor([property: JsonPropertyName("key")] string Key, [property: JsonPropertyName("label")] string Label, [property: JsonPropertyName("kind")] string Kind, [property: JsonPropertyName("default")] JsonNode? Default = null, [property: JsonPropertyName("allowed_values")] string[]? AllowedValues = null, [property: JsonPropertyName("min")] long? Min = null, [property: JsonPropertyName("max")] long? Max = null, [property: JsonPropertyName("step")] long? Step = null, [property: JsonPropertyName("ignored_when")] ReconstructionOptionIgnoredWhen? IgnoredWhen = null)`
  - `public sealed record ReconstructionOptionIgnoredWhen([property: JsonPropertyName("key")] string Key, [property: JsonPropertyName("equals")] string EqualsValue)` — **NOTE:** the property is `EqualsValue`, not `Equals`, because a record property named `Equals` collides with the synthesized `Equals` methods (compile error). JSON key stays `"equals"`.
  - `ReconstructionModelEntry` gains `[property: JsonPropertyName("options")] ReconstructionOptionDescriptor[]? Options = null` (last positional param, defaulted → old JSON still deserializes).

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionModelCatalogTests.cs` (this file already constructs catalogs via `ReconstructionModelCatalog.FromJson(json)`; add `using System.Text.Json.Nodes;` if absent):

```csharp
[Fact]
public void FromJson_ParsesOptionsBlock_EnumBooleanInteger_WithIgnoredWhenAndDefaults()
{
    const string json = """
    {
      "schema_version": 1,
      "models": [{
        "model_id": "test/pro", "provider": "fal", "task": "single_image_to_3d",
        "status": "experimental", "enabled": true,
        "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
        "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
        "fallback_order": ["model_glb"], "supports_pbr": true,
        "default_texture_expected": true,
        "preprocessing": {"recommended": false, "required": false},
        "docs_url": "https://example.test",
        "options": [
          { "key": "generate_type", "label": "Generate Type", "kind": "enum",
            "default": "Normal", "allowed_values": ["Normal", "Geometry"] },
          { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean",
            "default": false, "ignored_when": { "key": "generate_type", "equals": "Geometry" } },
          { "key": "face_count", "label": "Face Count", "kind": "integer",
            "default": 500000, "min": 40000, "max": 1500000, "step": 10000 }
        ]
      }]
    }
    """;

    var catalog = ReconstructionModelCatalog.FromJson(json);
    var model = catalog.Find("test/pro");

    Assert.NotNull(model!.Options);
    Assert.Equal(3, model.Options!.Length);

    var gen = model.Options[0];
    Assert.Equal("generate_type", gen.Key);
    Assert.Equal("enum", gen.Kind);
    Assert.Equal("Normal", gen.Default!.GetValue<string>());
    Assert.Equal(new[] { "Normal", "Geometry" }, gen.AllowedValues);

    var pbr = model.Options[1];
    Assert.Equal("boolean", pbr.Kind);
    Assert.False(pbr.Default!.GetValue<bool>());
    Assert.Equal("generate_type", pbr.IgnoredWhen!.Key);
    Assert.Equal("Geometry", pbr.IgnoredWhen.EqualsValue);

    var fc = model.Options[2];
    Assert.Equal("integer", fc.Kind);
    Assert.Equal(500000L, fc.Default!.GetValue<long>());
    Assert.Equal(40000L, fc.Min);
    Assert.Equal(1500000L, fc.Max);
    Assert.Equal(10000L, fc.Step);
}

[Fact]
public void FromJson_ModelWithoutOptions_DeserializesWithNullOptions()
{
    const string json = """
    {
      "schema_version": 1,
      "models": [{
        "model_id": "test/legacy", "provider": "fal", "task": "single_image_to_3d",
        "status": "stable", "enabled": true,
        "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
        "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
        "fallback_order": ["model_glb"], "supports_pbr": false,
        "default_texture_expected": true,
        "preprocessing": {"recommended": false, "required": false},
        "docs_url": "https://example.test"
      }]
    }
    """;
    var model = ReconstructionModelCatalog.FromJson(json).Find("test/legacy");
    Assert.Null(model!.Options);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests.FromJson_ParsesOptionsBlock"`
Expected: FAIL — compile error (`ReconstructionOptionDescriptor` / `Options` not defined).

- [ ] **Step 3: Add the types and the `Options` property**

In `ReconstructionModelCatalog.cs`, add `Options` as the last positional parameter of `ReconstructionModelEntry` (after `Prompt`):

```csharp
    [property: JsonPropertyName("prompt")] ReconstructionPromptMetadata? Prompt = null,
    [property: JsonPropertyName("options")] ReconstructionOptionDescriptor[]? Options = null);
```

Add the new records below `ReconstructionPromptMetadata` (top of file already has `using System.Text.Json.Serialization;`; add `using System.Text.Json.Nodes;`):

```csharp
public sealed record ReconstructionOptionDescriptor(
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("label")] string Label,
    [property: JsonPropertyName("kind")] string Kind,
    [property: JsonPropertyName("default")] JsonNode? Default = null,
    [property: JsonPropertyName("allowed_values")] string[]? AllowedValues = null,
    [property: JsonPropertyName("min")] long? Min = null,
    [property: JsonPropertyName("max")] long? Max = null,
    [property: JsonPropertyName("step")] long? Step = null,
    [property: JsonPropertyName("ignored_when")] ReconstructionOptionIgnoredWhen? IgnoredWhen = null);

public sealed record ReconstructionOptionIgnoredWhen(
    [property: JsonPropertyName("key")] string Key,
    [property: JsonPropertyName("equals")] string EqualsValue);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests.FromJson"`
Expected: PASS (both new tests + existing catalog tests).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionModelCatalog.cs src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs
git commit -m "feat(reconstruction): catalog option-descriptor types + deserialization"
```

---

### Task 1.2: Pro catalog entry + vocabulary expansion (file roles + slots)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionContracts.cs` (add `ReconstructionFileRoles` constants + `ReconstructionViewSlots.Allowed` members)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs`

**Interfaces:**
- Produces: production catalog contains `fal-ai/hunyuan-3d/v3.1/pro/image-to-3d` with `input.mode == "multi_view_labeled"`, 8 `view_slots`, 3 `options`; `ReconstructionFileRoles.ModelFbx/ModelUsdz/ViewBottom/ViewLeftFront/ViewRightFront`; `ReconstructionViewSlots.Allowed` includes `bottom/left_front/right_front`.

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionModelCatalogTests.cs` (loads the **production** catalog file). Confirm how the test project reads the embedded/production catalog — search the test file for an existing test that loads the real catalog (e.g. one referencing `fal-ai/hunyuan-3d/v3.1/rapid`); reuse that loader helper. If none exists, load via the same mechanism `ReconstructionModelCatalog` uses at runtime (find the loader in `ReconstructionModelCatalog.cs` — the `FromJson` caller). Name the helper `LoadProductionCatalog()` in the test:

```csharp
[Fact]
public void ProductionCatalog_IncludesHunyuanPro_WithEightSlotsAndThreeOptions()
{
    var pro = LoadProductionCatalog().Find("fal-ai/hunyuan-3d/v3.1/pro/image-to-3d");

    Assert.NotNull(pro);
    Assert.Equal("experimental", pro!.Status);          // flips to stable in Slice 4
    Assert.True(pro.SupportsPbr);
    Assert.True(pro.DefaultTextureExpected);
    Assert.Equal("multi_view_labeled", pro.Input!.Mode);
    Assert.Equal("input_image_url", pro.Input.SourceField);

    var slots = pro.Input.ViewSlots!;
    Assert.Equal(8, slots.Length);
    Assert.Equal(
        new[] { "front", "back", "left", "right", "top", "bottom", "left_front", "right_front" },
        slots.Select(s => s.Role).ToArray());
    Assert.Equal("input_image_url", slots[0].Field);
    Assert.Equal("back_image_url", slots[1].Field);
    Assert.Equal("right_front_image_url", slots[7].Field);
    Assert.True(slots[0].Required);
    Assert.False(slots[1].Required);

    Assert.Equal(3, pro.Options!.Length);
    Assert.Equal(new[] { "generate_type", "enable_pbr", "face_count" },
        pro.Options.Select(o => o.Key).ToArray());
}
```

(Ensure `using System.Linq;` is present in the test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ProductionCatalog_IncludesHunyuanPro"`
Expected: FAIL — `pro` is null (entry absent).

- [ ] **Step 3: Add the Pro entry to the catalog JSON**

In `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`, add this object to the `models` array (after the Rapid entry):

```json
{
  "model_id": "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
  "provider": "fal",
  "task": "single_image_to_3d",
  "status": "experimental",
  "enabled": true,
  "pipeline_roles": ["single_image_to_3d"],
  "input_types": ["image_url"],
  "output_roles": ["model_glb", "model_obj", "material_mtl", "model_fbx", "model_usdz", "texture", "thumbnail"],
  "preferred_asset_role": "model_glb",
  "fallback_order": ["model_glb", "model_obj"],
  "supports_pbr": true,
  "default_texture_expected": true,
  "input": {
    "mode": "multi_view_labeled",
    "source_field": "input_image_url",
    "view_slots": [
      { "role": "front",       "field": "input_image_url",       "required": true  },
      { "role": "back",        "field": "back_image_url",        "required": false },
      { "role": "left",        "field": "left_image_url",        "required": false },
      { "role": "right",       "field": "right_image_url",       "required": false },
      { "role": "top",         "field": "top_image_url",         "required": false },
      { "role": "bottom",      "field": "bottom_image_url",      "required": false },
      { "role": "left_front",  "field": "left_front_image_url",  "required": false },
      { "role": "right_front", "field": "right_front_image_url", "required": false }
    ]
  },
  "prompt": { "supported": false, "required": false, "kind": null },
  "preprocessing": { "recommended": false, "required": false },
  "options": [
    { "key": "generate_type", "label": "Generate Type", "kind": "enum",
      "default": "Normal", "allowed_values": ["Normal", "Geometry"] },
    { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean",
      "default": false, "ignored_when": { "key": "generate_type", "equals": "Geometry" } },
    { "key": "face_count", "label": "Face Count", "kind": "integer",
      "default": 500000, "min": 40000, "max": 1500000, "step": 10000 }
  ],
  "docs_url": "https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/pro/image-to-3d/api"
}
```

- [ ] **Step 4: Add vocabulary constants**

In `ReconstructionContracts.cs`, extend `ReconstructionFileRoles` (after `ViewThreeQuarter`):

```csharp
    public const string ModelFbx = "model_fbx";
    public const string ModelUsdz = "model_usdz";
    public const string ViewBottom = "view_bottom";
    public const string ViewLeftFront = "view_left_front";
    public const string ViewRightFront = "view_right_front";
```

And extend `ReconstructionViewSlots.Allowed`:

```csharp
public static readonly HashSet<string> Allowed = new HashSet<string>(StringComparer.Ordinal)
{
    "front", "left", "right", "back", "top", "three_quarter",
    "bottom", "left_front", "right_front",
};
```

- [ ] **Step 5: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json src/Rook/Services/Reconstruction/ReconstructionContracts.cs src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs
git commit -m "feat(reconstruction): experimental Hunyuan Pro catalog entry + slot/role vocabulary"
```

---

### Task 1.3: Request contract `Views` + parser `views[]`

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs` (add `ReconstructionViewRequest`; add `Views` to the existing `ReconstructionSubmitRequest` record declared at line 8 of this file — **not** `ReconstructionContracts.cs`; parse `views[]`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionSubmitRequestParserTests.cs`

> **Contract placement (verified):** `ReconstructionSubmitRequest`, `ReconstructionPreprocessingStageRequest`, and `ReconstructionParseResult` are all declared at the top of `ReconstructionSubmitRequestParser.cs` (lines 8–26), not in `ReconstructionContracts.cs` (which holds only the `Reconstruction*` constants/enums). Co-locate the new `ReconstructionViewRequest` with `ReconstructionSubmitRequest` in the parser file — these submit-request contracts change together. Do **not** introduce a second copy in `ReconstructionContracts.cs`. (If a future refactor wants all request contracts moved into `ReconstructionContracts.cs`, do that as its own explicit, separately-reviewed task — out of scope here.)

**Interfaces:**
- Produces:
  - `public sealed record ReconstructionViewRequest(string Slot, Guid ArtifactId, string Role);`
  - `ReconstructionSubmitRequest` gains `public IReadOnlyList<ReconstructionViewRequest> Views { get; init; } = Array.Empty<ReconstructionViewRequest>();` (init property in the record body — keeps the positional ctor + all existing constructions unchanged).
- Consumes (Task 1.7): `request.Views`.

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionSubmitRequestParserTests.cs`:

```csharp
[Fact]
public void Parse_AbsentViews_YieldsEmptyList()
{
    var id = Guid.NewGuid();
    var result = ReconstructionSubmitRequestParser.Parse(
        $"{{\"source_artifact_id\":\"{id}\",\"model_id\":\"m\"}}");
    Assert.True(result.Success);
    Assert.Empty(result.Request!.Views);
}

[Fact]
public void Parse_ParsesViews_SlotArtifactRole()
{
    var front = Guid.NewGuid();
    var left = Guid.NewGuid();
    var result = ReconstructionSubmitRequestParser.Parse(
        "{" +
        $"\"source_artifact_id\":\"{front}\",\"model_id\":\"m\"," +
        "\"views\":[" +
        $"{{\"slot\":\"front\",\"artifact_id\":\"{front}\"}}," +
        $"{{\"slot\":\"left\",\"artifact_id\":\"{left}\",\"role\":\"image\"}}" +
        "]}");
    Assert.True(result.Success);
    Assert.Equal(2, result.Request!.Views.Count);
    Assert.Equal("front", result.Request.Views[0].Slot);
    Assert.Equal(front, result.Request.Views[0].ArtifactId);
    Assert.Equal("image", result.Request.Views[0].Role);   // default when role absent
    Assert.Equal("left", result.Request.Views[1].Slot);
    Assert.Equal(left, result.Request.Views[1].ArtifactId);
}

[Fact]
public void Parse_ViewMissingSlot_Fails()
{
    var id = Guid.NewGuid();
    var result = ReconstructionSubmitRequestParser.Parse(
        "{" + $"\"source_artifact_id\":\"{id}\",\"model_id\":\"m\"," +
        $"\"views\":[{{\"artifact_id\":\"{id}\"}}]}}");
    Assert.False(result.Success);
    Assert.Equal("invalid_request", result.Failure!.Code);
    Assert.Equal("views", result.Failure.Field);
}

[Fact]
public void Parse_ViewBadGuid_Fails()
{
    var id = Guid.NewGuid();
    var result = ReconstructionSubmitRequestParser.Parse(
        "{" + $"\"source_artifact_id\":\"{id}\",\"model_id\":\"m\"," +
        "\"views\":[{\"slot\":\"left\",\"artifact_id\":\"not-a-guid\"}]}");
    Assert.False(result.Success);
    Assert.Equal("invalid_request", result.Failure!.Code);
    Assert.Equal("views", result.Failure.Field);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionSubmitRequestParserTests.Parse_ParsesViews"`
Expected: FAIL — `Views` not defined.

- [ ] **Step 3: Add the contract type + property**

In `ReconstructionSubmitRequestParser.cs` (the file where `ReconstructionSubmitRequest` is declared, line 8), add the new record immediately above or below `ReconstructionSubmitRequest`:

```csharp
public sealed record ReconstructionViewRequest(string Slot, Guid ArtifactId, string Role);
```

In the **same file**, add the init property inside the existing `ReconstructionSubmitRequest` record body (convert the positional record at line 8 to a body-bearing one — keep all 6 positional params, add a body block):

```csharp
public sealed record ReconstructionSubmitRequest(
    Guid SourceArtifactId,
    string SourceRole,
    string ModelId,
    IReadOnlyList<ReconstructionPreprocessingStageRequest> PreprocessingChain,
    JsonObject Options,
    bool EstimateRequested)
{
    public IReadOnlyList<ReconstructionViewRequest> Views { get; init; }
        = Array.Empty<ReconstructionViewRequest>();
}
```

(`using System;` already present for `Array`.)

- [ ] **Step 4: Add parsing to the parser**

In `ReconstructionSubmitRequestParser.cs`, after the `options`/`estimateRequested` reads and before constructing the result, parse views:

```csharp
        var views = ParseViews(root["views"], out var viewsFailure);
        if (viewsFailure is not null)
            return new ReconstructionParseResult(false, null, viewsFailure);
```

Construct the request with `Views`:

```csharp
        return new ReconstructionParseResult(
            true,
            new ReconstructionSubmitRequest(
                sourceArtifactId,
                sourceRole!,
                modelId!,
                preprocessing,
                options,
                estimateRequested)
            {
                Views = views,
            },
            null);
```

Add the helper (mirrors `ReconstructionViewSetRequest.TryParse`'s typed-read style):

```csharp
private static IReadOnlyList<ReconstructionViewRequest> ParseViews(
    JsonNode? node, out ReconstructionFailure? failure)
{
    failure = null;
    if (node is null)
        return Array.Empty<ReconstructionViewRequest>();

    if (node is not JsonArray array)
    {
        failure = Failure("invalid_request", "views must be an array.", "views");
        return Array.Empty<ReconstructionViewRequest>();
    }

    var result = new List<ReconstructionViewRequest>();
    foreach (var item in array)
    {
        if (item is not JsonObject obj)
        {
            failure = Failure("invalid_request", "Each view must be a JSON object.", "views");
            return Array.Empty<ReconstructionViewRequest>();
        }

        var slot = ReadString(obj, "slot");
        if (string.IsNullOrWhiteSpace(slot))
        {
            failure = Failure("invalid_request", "Each view requires a 'slot'.", "views");
            return Array.Empty<ReconstructionViewRequest>();
        }

        if (!TryReadGuid(obj, "artifact_id", out var artifactId))
        {
            failure = Failure("invalid_request", "Each view requires a valid 'artifact_id'.", "views");
            return Array.Empty<ReconstructionViewRequest>();
        }

        var role = ReadString(obj, "role");
        role = string.IsNullOrWhiteSpace(role) ? "image" : role;

        result.Add(new ReconstructionViewRequest(slot!, artifactId, role!));
    }

    return result;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionSubmitRequestParserTests"`
Expected: PASS (new + existing parser tests).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionSubmitRequestParser.cs src/Rook.Tests/Services/Reconstruction/ReconstructionSubmitRequestParserTests.cs
git commit -m "feat(reconstruction): inline labeled views[] in submit request + parser"
```

---

### Task 1.4: Shared options validator + default-fill

**Files:**
- Create: `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs`

**Interfaces:**
- Produces:
  - `public sealed record ReconstructionOptionsResult(bool Success, JsonObject Options, ReconstructionFailure? Failure);`
  - `public static ReconstructionOptionsResult ReconstructionOptionsValidator.Validate(JsonObject submitted, ReconstructionModelEntry model);`
- Behavior: for a model with `Options != null` — validate each present option against its descriptor; fill defaults for absent options; omit options whose `ignored_when` is satisfied; reject unknown keys. Returns the cleaned options object on success.
- Consumes (Task 1.8): called by `SubmitAsync` for catalog-described models.

- [ ] **Step 1: Write the failing test**

Create `ReconstructionOptionsValidatorTests.cs`:

```csharp
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction;

public sealed class ReconstructionOptionsValidatorTests
{
    private static ReconstructionModelEntry ProModel()
        => ReconstructionModelCatalog.FromJson("""
        {
          "schema_version": 1,
          "models": [{
            "model_id": "test/pro", "provider": "fal", "task": "single_image_to_3d",
            "status": "stable", "enabled": true,
            "pipeline_roles": ["single_image_to_3d"], "input_types": ["image_url"],
            "output_roles": ["model_glb"], "preferred_asset_role": "model_glb",
            "fallback_order": ["model_glb"], "supports_pbr": true,
            "default_texture_expected": true,
            "preprocessing": {"recommended": false, "required": false},
            "docs_url": "https://example.test",
            "options": [
              { "key": "generate_type", "label": "Generate Type", "kind": "enum",
                "default": "Normal", "allowed_values": ["Normal", "Geometry"] },
              { "key": "enable_pbr", "label": "Enable PBR", "kind": "boolean",
                "default": false, "ignored_when": { "key": "generate_type", "equals": "Geometry" } },
              { "key": "face_count", "label": "Face Count", "kind": "integer",
                "default": 500000, "min": 40000, "max": 1500000, "step": 10000 }
            ]
          }]
        }
        """).Find("test/pro")!;

    [Fact]
    public void Validate_FillsDefaults_WhenAbsent()
    {
        var result = ReconstructionOptionsValidator.Validate(new JsonObject(), ProModel());
        Assert.True(result.Success);
        Assert.Equal("Normal", result.Options["generate_type"]!.GetValue<string>());
        Assert.False(result.Options["enable_pbr"]!.GetValue<bool>());
        Assert.Equal(500000L, result.Options["face_count"]!.GetValue<long>());
    }

    [Fact]
    public void Validate_OmitsEnablePbr_WhenGeometry()
    {
        var submitted = new JsonObject { ["generate_type"] = "Geometry", ["enable_pbr"] = true };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.True(result.Success);
        Assert.Equal("Geometry", result.Options["generate_type"]!.GetValue<string>());
        Assert.False(result.Options.ContainsKey("enable_pbr"));   // ignored → omitted
    }

    [Fact]
    public void Validate_RejectsUnknownKey()
    {
        var submitted = new JsonObject { ["bogus"] = 1 };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.False(result.Success);
        Assert.Equal("invalid_request", result.Failure!.Code);
        Assert.Equal("unknown_option", result.Failure.Details["reason"]);
    }

    [Fact]
    public void Validate_RejectsEnumOutOfRange()
    {
        var submitted = new JsonObject { ["generate_type"] = "Sculpt" };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.False(result.Success);
        Assert.Equal("options.generate_type", result.Failure!.Field);
    }

    [Fact]
    public void Validate_RejectsIntegerOutOfRange()
    {
        var submitted = new JsonObject { ["face_count"] = 10 };
        var result = ReconstructionOptionsValidator.Validate(submitted, ProModel());
        Assert.False(result.Success);
        Assert.Equal("options.face_count", result.Failure!.Field);
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOptionsValidatorTests"`
Expected: FAIL — `ReconstructionOptionsValidator` not defined.

- [ ] **Step 3: Implement the validator**

Create `src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction;

public sealed record ReconstructionOptionsResult(
    bool Success,
    JsonObject Options,
    ReconstructionFailure? Failure);

/// <summary>
/// Validates and normalizes a submit-options object against a model's catalog option descriptors:
/// rejects unknown keys, range/enum-checks present values, fills defaults for absent options, and
/// omits options whose <c>ignored_when</c> condition is satisfied. Only applies to models that
/// declare an <c>options</c> block; callers keep verbatim pass-through for models without one.
/// </summary>
public static class ReconstructionOptionsValidator
{
    public static ReconstructionOptionsResult Validate(JsonObject submitted, ReconstructionModelEntry model)
    {
        var descriptors = model.Options ?? Array.Empty<ReconstructionOptionDescriptor>();
        var byKey = descriptors.ToDictionary(d => d.Key, StringComparer.Ordinal);

        // Reject unknown keys.
        foreach (var kvp in submitted)
        {
            if (!byKey.ContainsKey(kvp.Key))
                return Fail($"Unknown option '{kvp.Key}'.", "options", "unknown_option");
        }

        // Validate present values.
        foreach (var d in descriptors)
        {
            if (!submitted.TryGetPropertyValue(d.Key, out var node) || node is null)
                continue;
            var error = ValidateValue(d, node);
            if (error is not null)
                return Fail(error, $"options.{d.Key}", "invalid_option_value");
        }

        // Build the effective (default-filled) set first so ignored_when sees final values.
        var effective = new JsonObject();
        foreach (var d in descriptors)
        {
            var value = submitted.TryGetPropertyValue(d.Key, out var node) && node is not null
                ? node.DeepClone()
                : d.Default?.DeepClone();
            if (value is not null)
                effective[d.Key] = value;
        }

        // Omit ignored options.
        foreach (var d in descriptors)
        {
            if (d.IgnoredWhen is null) continue;
            if (effective.TryGetPropertyValue(d.IgnoredWhen.Key, out var gate)
                && gate is JsonValue gv
                && gv.TryGetValue<string>(out var gateText)
                && string.Equals(gateText, d.IgnoredWhen.EqualsValue, StringComparison.Ordinal))
            {
                effective.Remove(d.Key);
            }
        }

        return new ReconstructionOptionsResult(true, effective, null);
    }

    private static string? ValidateValue(ReconstructionOptionDescriptor d, JsonNode node)
    {
        switch (d.Kind)
        {
            case "enum":
                if (node is not JsonValue ev || !ev.TryGetValue<string>(out var s))
                    return $"'{d.Key}' must be a string.";
                if (d.AllowedValues is not null && !d.AllowedValues.Contains(s, StringComparer.Ordinal))
                    return $"'{d.Key}' must be one of: {string.Join(", ", d.AllowedValues)}.";
                return null;
            case "boolean":
                if (node is not JsonValue bv || !bv.TryGetValue<bool>(out _))
                    return $"'{d.Key}' must be a boolean.";
                return null;
            case "integer":
                if (node is not JsonValue iv || !iv.TryGetValue<long>(out var i))
                    return $"'{d.Key}' must be an integer.";
                if (d.Min is not null && i < d.Min) return $"'{d.Key}' must be >= {d.Min}.";
                if (d.Max is not null && i > d.Max) return $"'{d.Key}' must be <= {d.Max}.";
                return null;
            default:
                return null;
        }
    }

    private static ReconstructionOptionsResult Fail(string message, string field, string reason)
        => new(false, new JsonObject(),
            new ReconstructionFailure("invalid_request", message, false, field,
                new Dictionary<string, object?> { ["reason"] = reason }));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOptionsValidatorTests"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionOptionsValidator.cs src/Rook.Tests/Services/Reconstruction/ReconstructionOptionsValidatorTests.cs
git commit -m "feat(reconstruction): shared options validator (range/enum/unknown/default-fill/ignored)"
```

---

### Task 1.5: Provider multi-field payload (`ViewUrls`)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs`
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (the one construction site of `ReconstructionProviderSubmitRequest`, lines ~214–219)
- Test: `src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs`

**Interfaces:**
- Produces:
  - `public sealed record ReconstructionProviderViewUrl(string Field, Uri Url);`
  - `ReconstructionProviderSubmitRequest` replaces `Uri InputImageUrl` + `string? SourceField` with `IReadOnlyList<ReconstructionProviderViewUrl> ViewUrls` (ordered, front first).
- Consumes (Task 1.7): the manager builds `ViewUrls`.

> This is a breaking change to the provider request shape. In **production** the manager's `SubmitCoreAsync` is the only construction site; update it in the same task so the build stays green. The remove-background path also flows through `SubmitCoreAsync`, so its single-source build must produce a one-entry `ViewUrls` list — covered in Task 1.7. For *this* task, update that production site to a one-entry list. **In tests, the provider test file constructs the request eight times** (see Step 1's table) — all must be updated here too, or the provider suite won't compile.

- [ ] **Step 1: Write the failing test**

In `FalReconstructionProviderTests.cs`, add the multi-field test below and update **all** existing request constructions (eight — see the table after the snippet). Add:

```csharp
[Fact]
public async Task BuildSubmitPayload_WritesAllViewFields_FrontFirst()
{
    var transport = new FakeTransport();
    transport.Posts.Enqueue(Resp(200, @"{""request_id"":""req-1"",""status_url"":""https://queue.fal.run/status/req-1""}"));

    await new FalReconstructionProvider(transport).SubmitAsync(
        new ReconstructionProviderSubmitRequest(
            HunyuanModelId,
            new[]
            {
                new ReconstructionProviderViewUrl("input_image_url", new Uri("https://rook.local/front.png")),
                new ReconstructionProviderViewUrl("back_image_url", new Uri("https://rook.local/back.png")),
                new ReconstructionProviderViewUrl("left_image_url", new Uri("https://rook.local/left.png")),
            },
            new JsonObject { ["generate_type"] = "Normal" }),
        CancellationToken.None);

    Assert.Contains(@"""input_image_url"":""https://rook.local/front.png""", transport.LastPostBody);
    Assert.Contains(@"""back_image_url"":""https://rook.local/back.png""", transport.LastPostBody);
    Assert.Contains(@"""left_image_url"":""https://rook.local/left.png""", transport.LastPostBody);
    Assert.Contains(@"""generate_type"":""Normal""", transport.LastPostBody);
    // front first
    Assert.True(transport.LastPostBody!.IndexOf("input_image_url") < transport.LastPostBody.IndexOf("back_image_url"));
}
```

**Update ALL existing constructions of `ReconstructionProviderSubmitRequest` in this file — there are eight, not two.** The old 3-arg signature `(string, Uri, JsonObject)` (plus a `{ SourceField = ... }` initializer on one) no longer compiles. Add a small helper to the test class and route every site through it:

```csharp
private static ReconstructionProviderSubmitRequest Req(
    string modelId, string url, JsonObject options, string field = "input_image_url")
    => new(modelId, new[] { new ReconstructionProviderViewUrl(field, new Uri(url)) }, options);
```

Then replace each existing construction (the new multi-field test above constructs its 3-entry list inline and does **not** use the helper):

| Line (approx) | Test | Replace with |
|---|---|---|
| 31 | `Submit_Queued_ReturnsHandleWithRequestIdAndUrls` | `Req(HunyuanModelId, "https://rook.local/source.png", JsonNode.Parse(@"{""enable_pbr"":true,""enable_geometry"":false}")!.AsObject())` |
| 61 | `BuildSubmitPayload_UsesSourceField_WhenProvided` (BiRefNet) | `Req("fal-ai/birefnet/v2", "https://rook.local/source.png", new JsonObject(), field: "image_url")` — drop the `{ SourceField = "image_url" }` initializer |
| 84 | (plain hunyuan submit) | `Req(HunyuanModelId, "https://rook.local/source.png", new JsonObject())` |
| 100, 114, 126, 142, 161 | (failure/transport/cancel cases) | `Req(HunyuanModelId, "https://rook.local/s.png", new JsonObject())` |

After editing, grep the file to confirm no old-signature artifacts remain (the `Req` helper and the inline multi-field test legitimately use `new Uri`, so don't grep for that):

Run: `rg "InputImageUrl|SourceField =" src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs` — expect **no hits**.

(Ensure `using System.Text.Json.Nodes;` present for `JsonObject`/`JsonNode`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests"`
Expected: FAIL — compile error (`ReconstructionProviderViewUrl` undefined; old ctor signature gone).

- [ ] **Step 3: Update the provider request + payload**

In `FalReconstructionProvider.cs`, replace the `ReconstructionProviderSubmitRequest` record:

```csharp
public sealed record ReconstructionProviderSubmitRequest(
    string ModelId,
    IReadOnlyList<ReconstructionProviderViewUrl> ViewUrls,
    JsonObject Options);

public sealed record ReconstructionProviderViewUrl(string Field, Uri Url);
```

(Add `using System.Collections.Generic;` if not present.) Replace `BuildSubmitPayload`:

```csharp
private static JsonObject BuildSubmitPayload(ReconstructionProviderSubmitRequest request)
{
    var payload = new JsonObject();
    foreach (var view in request.ViewUrls)
        payload[view.Field] = view.Url.ToString();
    foreach (var kvp in request.Options)
        payload[kvp.Key] = kvp.Value?.DeepClone();
    return payload;
}
```

- [ ] **Step 4: Update the manager construction site**

In `ReconstructionJobManager.cs` `SubmitCoreAsync` (the `_provider.SubmitAsync(new ReconstructionProviderSubmitRequest(... ) { SourceField = ... }, ct)` call, ~lines 214–219), change to a one-entry list for now (Task 1.7 generalizes this):

```csharp
        submitOutcome = await _provider.SubmitAsync(
            new ReconstructionProviderSubmitRequest(
                request.ModelId,
                new[] { new ReconstructionProviderViewUrl(model.Input?.SourceField ?? "input_image_url", sourceUrl) },
                request.Options),
            ct).ConfigureAwait(false);
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~FalReconstructionProviderTests|FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS (provider + manager suites green).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/FalReconstructionProvider.cs src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/Fal/FalReconstructionProviderTests.cs
git commit -m "feat(reconstruction): provider writes labeled view URLs to named Fal fields"
```

---

### Task 1.6: Manager capability gate (`IsSubmittable3DModel`)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (replace `IsSubmittableV1Model`; gate call at line 112)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Produces: `private static bool IsSubmittable3DModel(ReconstructionModelEntry? model)` — true iff enabled, status stable, has an importable 3D output role (`model_glb` or `model_obj`), and accepts input (a `source_field` exists, or `view_slots` declared). No `task` check.

- [ ] **Step 1: Write the failing test**

The manager test catalog (`CatalogJson` constant in `ReconstructionJobManagerTests.cs`) currently has Rapid as `stable`. Add a **synthetic stable Pro** entry to that catalog constant (mirror Task 1.2's JSON but `"status": "stable"`), then add a test asserting a multi-view-only model (no `single_image` task semantics, capability via slots) is submittable. Add to `ReconstructionJobManagerTests.cs`:

```csharp
[Fact]
public async Task Submit_MultiViewLabeledModel_IsSubmittable_ViaCapabilityGate()
{
    var fixture = CreateFixture();
    var source = fixture.Store.Create(
        "generated_image", new[] { new BlobInput("image", new byte[] { 1, 2, 3 }, "png") });

    var result = await fixture.Manager.SubmitAsync(
        Request(source.Id) with { ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d" },
        CancellationToken.None);

    Assert.True(result.Success);
}
```

(If the local `Request(...)` helper hardcodes the Rapid model id, this `with { ModelId = ... }` overrides it. Confirm `Request` returns a `ReconstructionSubmitRequest`.)

Add the synthetic **stable** Pro entry to the `CatalogJson` constant's `models` array (full entry from Task 1.2 with `"status": "stable"`).

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests.Submit_MultiViewLabeledModel"`
Expected: FAIL — gate rejects (current `IsSubmittableV1Model` requires `task == single_image_to_3d` and `pipeline_roles` contains it; Pro's `task` is `single_image_to_3d` so this passes today — but to make the test *meaningful* and force the capability rewrite, also assert that submit succeeds while we will remove the task dependency). If it passes immediately because Pro keeps `task=single_image_to_3d`, still proceed to Step 3 to replace the predicate (the capability gate is required by §8 and exercised by Task 1.11's picker test). Confirm failure by temporarily setting the synthetic Pro entry's `task` to `"multi_view_to_3d"` in the test catalog — the old gate then rejects it. Keep that altered `task` in the test catalog to lock in capability-not-task behavior.

- [ ] **Step 3: Replace the predicate**

In `ReconstructionJobManager.cs`, replace `IsSubmittableV1Model` (lines 670–675) with:

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

Update the gate call at line 112:

```csharp
        if (!IsSubmittable3DModel(model))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS (incl. existing submit tests — Rapid still qualifies: stable, `model_glb`, `source_field` present).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): capability-based 3D submit gate (no task dependency)"
```

---

### Task 1.7: Manager multi-view resolution + per-slot publish

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`SubmitCoreAsync`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `request.Views` (Task 1.3), `ReconstructionProviderViewUrl` (Task 1.5), `model.Input.ViewSlots`.
- Produces: ordered published `ViewUrls` (front first, then `view_slots` order), with front-conflict / duplicate-slot / unsupported-slot validation and per-slot source validation.

- [ ] **Step 1: Write the failing tests**

Add to `ReconstructionJobManagerTests.cs`:

```csharp
[Fact]
public async Task Submit_MultiView_PublishesAllSlots_FrontFirst()
{
    var fixture = CreateFixture();
    var front = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var left = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 2 }, "png") });

    var req = Request(front.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Views = new[]
        {
            new ReconstructionViewRequest("front", front.Id, "image"),
            new ReconstructionViewRequest("left", left.Id, "image"),
        },
    };

    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);

    Assert.True(result.Success);
    Assert.Equal(2, fixture.Publisher.Published.Count);                 // both slots published
    var submitted = Assert.Single(fixture.Provider.SubmitRequests);
    Assert.Equal("input_image_url", submitted.ViewUrls[0].Field);       // front first
    Assert.Equal("left_image_url", submitted.ViewUrls[1].Field);
}

[Fact]
public async Task Submit_FrontView_DifferentArtifact_ConflictingFront()
{
    var fixture = CreateFixture();
    var front = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var other = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 9 }, "png") });

    var req = Request(front.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Views = new[] { new ReconstructionViewRequest("front", other.Id, "image") },
    };

    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.False(result.Success);
    Assert.Equal("conflicting_front", result.Failure!.Details["reason"]);
}

[Fact]
public async Task Submit_FrontView_DifferentRole_ConflictingFront()
{
    var fixture = CreateFixture();
    var front = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });

    // source_role defaults to "image"; an explicit differing role on the front view conflicts.
    var req = Request(front.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Views = new[] { new ReconstructionViewRequest("front", front.Id, "depth") },
    };

    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.False(result.Success);
    Assert.Equal("conflicting_front", result.Failure!.Details["reason"]);
}

[Fact]
public async Task Submit_UnsupportedSlot_Rejected()
{
    var fixture = CreateFixture();
    var front = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var extra = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 2 }, "png") });

    var req = Request(front.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Views = new[] { new ReconstructionViewRequest("three_quarter", extra.Id, "image") },  // no Pro mapping
    };

    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.False(result.Success);
    Assert.Equal("unsupported_slot", result.Failure!.Details["reason"]);
    Assert.Equal("views", result.Failure.Field);
}

[Fact]
public async Task Submit_DuplicateNonFrontSlot_Rejected()
{
    var fixture = CreateFixture();
    var front = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var a = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 2 }, "png") });
    var b = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 3 }, "png") });

    var req = Request(front.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Views = new[]
        {
            new ReconstructionViewRequest("left", a.Id, "image"),
            new ReconstructionViewRequest("left", b.Id, "image"),
        },
    };

    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.False(result.Success);
    Assert.Equal("duplicate_slot", result.Failure!.Details["reason"]);
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests.Submit_MultiView|FullyQualifiedName~ReconstructionJobManagerTests.Submit_FrontView|FullyQualifiedName~ReconstructionJobManagerTests.Submit_UnsupportedSlot|FullyQualifiedName~ReconstructionJobManagerTests.Submit_DuplicateNonFrontSlot"`
Expected: FAIL — single-source path ignores `Views`; only one image published; no conflict detection.

- [ ] **Step 3: Implement multi-view resolution in `SubmitCoreAsync`**

Replace the single-source body of `SubmitCoreAsync` with resolution over the effective slot map, in **two passes**: (A) resolve + validate every slot **before** the `Queued`/`Submitting` ledger appends (so a rejected submit creates no phantom job and typed failures aren't swallowed by the publish `try`); (B) read + publish each slot **inside** the existing `try` (it can throw `FalApiException`).

**Pass A — resolve + validate (pre-ledger, replaces the original `var source`/`sourceValidation` block):**

```csharp
    // ── Resolve the effective slot→artifact map (front is canonical, immutable) ──
    var resolution = ResolveViews(request, model);
    if (!resolution.Success)
        return new ReconstructionSubmitResult(false, null, resolution.Failure);
    var resolvedViews = resolution.Views;   // ordered: front first, then view_slots order

    // Validate every slot's source up front; capture each AbsolutePath for the publish pass.
    var validatedViews = new List<(ResolvedView View, string AbsolutePath)>();
    foreach (var rv in resolvedViews)
    {
        var artifact = _store.Get(rv.ArtifactId);
        if (artifact is null)
            return SubmitFail("invalid_request", $"artifact for slot '{rv.Slot}' was not found.", "views");

        var validation = ReconstructionSourceValidator.Validate(_store, artifact, rv.Role);
        if (!validation.Success)
        {
            var f = validation.Failure!;
            return new ReconstructionSubmitResult(false, null, new ReconstructionFailure(
                f.Code, f.Message, f.Retryable, f.Field ?? "views",
                new Dictionary<string, object?>(f.Details) { ["slot"] = rv.Slot }));
        }
        validatedViews.Add((rv, validation.AbsolutePath!));
    }
```

Then the existing `jobId`/`Queued`/`Submitting` ledger appends run unchanged (still recording the single front `request.SourceArtifactId`).

**Pass B — read + publish.** Declare `sourceArtifactIds` **above** the existing `try` (next to `ProviderSubmitOutcome submitOutcome;`), because Task 1.10 reads it in the post-`try` `switch` (the `QueuedSubmitOutcome` branch). `providerViews` stays inside the `try`:

```csharp
        var sourceArtifactIds = new List<Guid>();   // declared before the try — read in the switch below
        ProviderSubmitOutcome submitOutcome;
        try
        {
            var providerViews = new List<ReconstructionProviderViewUrl>();
            foreach (var (rv, absolutePath) in validatedViews)
            {
                var bytes = await ReadFileBytesAsync(absolutePath, ct).ConfigureAwait(false);
                var mime = MimeForExtension(absolutePath);
                var fileName = $"rook-reconstruction-{rv.ArtifactId:D}-{rv.Slot}{Path.GetExtension(absolutePath)}";
                var url = await _sourcePublisher.PublishAsync(bytes, mime, fileName, ct).ConfigureAwait(false);
                providerViews.Add(new ReconstructionProviderViewUrl(rv.Field, url));
                sourceArtifactIds.Add(rv.ArtifactId);
            }

            submitOutcome = await _provider.SubmitAsync(
                new ReconstructionProviderSubmitRequest(request.ModelId, providerViews, request.Options),
                ct).ConfigureAwait(false);
        }
        catch (/* existing credential / FalApiException / generic catches unchanged */)
        {
            // ... existing catch bodies unchanged ...
        }
```

Keep the existing `try/catch` envelope (credential / FalApiException / generic) and the existing `switch (submitOutcome)` flow. The `Queued` ledger record still records the single front `SourceArtifactId` (no schema change) and `DeriveTextureExpected(request.Options, model)` stays as-is. The `sourceArtifactIds` list (front + filled slots, in resolved order) is **carried for Task 1.10**, which stashes it into a job-keyed carrier **inside the `QueuedSubmitOutcome` branch only** (not here) so failed submits leave no stale entry.

> **Validation-before-ledger ordering:** `ResolveViews` and the per-slot `ReconstructionSourceValidator.Validate` calls return `invalid_request`-class failures (`conflicting_front`/`unsupported_slot`/`duplicate_slot`/invalid source) and must run **before** the `Queued`/`Submitting` ledger records are appended — exactly as the original single-source `sourceValidation` ran before `jobId` creation — so a rejected submit never creates a phantom ledger job. Only the **read-bytes + publish** portion of the loop belongs inside the `try` (it can throw `FalApiException`). Split the loop accordingly: resolve + validate every slot first (pre-ledger), then read+publish each (in-try). A source-validation failure must surface as its typed `invalid_request` failure, not be swallowed by the generic `catch` → `submit_failed`.

Add the resolution helper + result type to the manager:

```csharp
private sealed record ResolvedView(string Slot, Guid ArtifactId, string Role, string Field);
private sealed record ViewResolution(bool Success, IReadOnlyList<ResolvedView> Views, ReconstructionFailure? Failure);

private static ViewResolution ResolveViews(ReconstructionSubmitRequest request, ReconstructionModelEntry model)
{
    var slots = model.Input?.ViewSlots ?? Array.Empty<ReconstructionViewSlot>();
    var byRole = slots.ToDictionary(s => s.Role, StringComparer.Ordinal);

    // Canonical front: source_artifact_id + source_role. Resolve its field from the catalog
    // (front slot field, else the model's source_field, else input_image_url).
    var frontField = byRole.TryGetValue("front", out var frontSlot)
        ? frontSlot.Field
        : (model.Input?.SourceField ?? "input_image_url");

    var ordered = new Dictionary<string, ResolvedView>(StringComparer.Ordinal)
    {
        ["front"] = new ResolvedView("front", request.SourceArtifactId, request.SourceRole, frontField),
    };

    foreach (var v in request.Views)
    {
        if (string.Equals(v.Slot, "front", StringComparison.Ordinal))
        {
            // Canonical-front restatement only: must match artifact AND (role absent-defaulted-to-image OR == source_role).
            if (v.ArtifactId != request.SourceArtifactId
                || !string.Equals(v.Role, request.SourceRole, StringComparison.Ordinal))
            {
                return Conflict("front", "views.front must match source_artifact_id and source_role.", "conflicting_front");
            }
            continue;   // redundant restatement; canonical front already seeded
        }

        if (!byRole.ContainsKey(v.Slot))
            return Conflict("views", $"slot '{v.Slot}' is not supported by this model.", "unsupported_slot");

        if (ordered.ContainsKey(v.Slot))
            return Conflict("views", $"slot '{v.Slot}' appears more than once.", "duplicate_slot");

        ordered[v.Slot] = new ResolvedView(v.Slot, v.ArtifactId, v.Role, byRole[v.Slot].Field);
    }

    // Order front first, then declared view_slots order.
    var result = new List<ResolvedView> { ordered["front"] };
    foreach (var slot in slots)
    {
        if (string.Equals(slot.Role, "front", StringComparison.Ordinal)) continue;
        if (ordered.TryGetValue(slot.Role, out var rv)) result.Add(rv);
    }

    return new ViewResolution(true, result, null);
}

private static ViewResolution Conflict(string field, string message, string reason)
    => new(false, Array.Empty<ResolvedView>(),
        new ReconstructionFailure("invalid_request", message, false, field,
            new Dictionary<string, object?> { ["reason"] = reason }));
```

> The role-default: the parser defaults an absent view `role` to `"image"`, and `source_role` also defaults to `"image"`. So a `front` view with no explicit role naturally equals `source_role` in the common case. A front view whose explicit role differs from `source_role` conflicts — matching the immutable-front invariant.

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS (new multi-view tests + existing single-source tests — single source resolves to a one-entry front list).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): multi-view slot resolution, front-conflict guard, per-slot publish"
```

---

### Task 1.8: Manager options-validation wiring + legacy split

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`SubmitAsync`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `ReconstructionOptionsValidator.Validate` (Task 1.4).
- Behavior: in `SubmitAsync`, for a model with `Options != null` → run the validator, on failure return it, on success replace `request` options with the default-filled set and **skip** the legacy `enable_pbr`/`enable_geometry` guards (subsumed). For a model with `Options == null` → keep the existing legacy guards + verbatim options (Rapid unchanged).

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionJobManagerTests.cs`:

```csharp
[Fact]
public async Task Submit_ProUnknownOption_Rejected()
{
    var fixture = CreateFixture();
    var src = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var req = Request(src.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Options = new JsonObject { ["bogus"] = 1 },
    };
    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.False(result.Success);
    Assert.Equal("unknown_option", result.Failure!.Details["reason"]);
}

[Fact]
public async Task Submit_ProDefaults_ForwardedToProvider()
{
    var fixture = CreateFixture();
    var src = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var req = Request(src.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Options = new JsonObject(),   // empty → defaults filled
    };
    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.True(result.Success);
    var submitted = Assert.Single(fixture.Provider.SubmitRequests);
    Assert.Equal("Normal", submitted.Options["generate_type"]!.GetValue<string>());
    Assert.Equal(500000L, submitted.Options["face_count"]!.GetValue<long>());
}

[Fact]
public async Task Submit_ProGeometry_OmitsEnablePbr_InProviderPayload()
{
    var fixture = CreateFixture();
    var src = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var req = Request(src.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Options = new JsonObject { ["generate_type"] = "Geometry", ["enable_pbr"] = true },
    };
    var result = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.True(result.Success);
    var submitted = Assert.Single(fixture.Provider.SubmitRequests);
    Assert.False(submitted.Options.ContainsKey("enable_pbr"));
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests.Submit_Pro"`
Expected: FAIL — `bogus` currently passes through (legacy verbatim) → submit succeeds; defaults not filled.

- [ ] **Step 3: Wire the validator into `SubmitAsync`**

In `ReconstructionJobManager.cs` `SubmitAsync`, after the preprocessing-chain guard (line 121) and before the legacy guards (line 123), branch on whether the model declares options:

```csharp
        if (model!.Options is not null)
        {
            var optionsResult = ReconstructionOptionsValidator.Validate(request.Options, model);
            if (!optionsResult.Success)
                return new ReconstructionSubmitResult(false, null, optionsResult.Failure);
            request = request with { Options = optionsResult.Options };
        }
        else
        {
            // Legacy verbatim-options models: keep the existing pbr/geometry guards.
            if (IsJsonTrue(request.Options, "enable_pbr") && IsJsonTrue(request.Options, "enable_geometry"))
            {
                return SubmitFail(
                    "invalid_request",
                    "enable_geometry=true requests geometry-only output and cannot be combined with "
                    + "enable_pbr=true. Remove enable_geometry to request textured output, or remove "
                    + "enable_pbr to request geometry-only output.",
                    "options");
            }

            if (IsJsonTrue(request.Options, "enable_pbr") && !model.SupportsPbr)
            {
                return SubmitFail(
                    "invalid_request",
                    $"Model '{model.ModelId}' does not support reliable PBR output. Submit without "
                    + "enable_pbr for the model's default output, or choose a PBR-capable model.",
                    "options");
            }
        }
```

Delete the original unconditional guards at lines 123–140 (they now live in the `else` branch).

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS (Pro option handling + existing Rapid legacy-guard tests).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): validate+default-fill catalog options; legacy guards for verbatim models"
```

---

### Task 1.9: `DeriveTextureExpected` rework (generate-type-driven)

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (`DeriveTextureExpected`, lines 711–718)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Behavior: if (default-filled) options contain `generate_type` → `Geometry ⇒ false`, `Normal ⇒ true` (regardless of `enable_pbr`). Else → existing legacy rules (`enable_geometry=true ⇒ false`; `enable_pbr=true ⇒ true`; `enable_pbr=false ⇒ false`; else `model.DefaultTextureExpected`).

- [ ] **Step 1: Write the failing test**

`DeriveTextureExpected` is `internal static`; the test project already accesses internals (the test class calls other internal manager members). Add:

```csharp
[Theory]
[InlineData("Normal", true, true)]
[InlineData("Normal", false, true)]   // Normal expects texture even without PBR — the Pro fix
[InlineData("Geometry", true, false)]
[InlineData("Geometry", false, false)]
public void DeriveTextureExpected_GenerateTypeDriven(string generateType, bool enablePbr, bool expected)
{
    var model = ProStableModelEntry();   // helper returning the synthetic stable Pro entry
    var options = new JsonObject { ["generate_type"] = generateType, ["enable_pbr"] = enablePbr };
    Assert.Equal(expected, ReconstructionJobManager.DeriveTextureExpected(options, model));
}

[Fact]
public void DeriveTextureExpected_LegacyModel_UsesEnableFlags()
{
    var model = RapidStableModelEntry();   // helper returning the Rapid entry (no options block)
    Assert.False(ReconstructionJobManager.DeriveTextureExpected(
        new JsonObject { ["enable_geometry"] = true }, model));
    Assert.True(ReconstructionJobManager.DeriveTextureExpected(
        new JsonObject { ["enable_pbr"] = true }, model));
}
```

Add the two helper methods to the test class (load from the same `CatalogJson` constant and `Find` the entries).

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests.DeriveTextureExpected"`
Expected: FAIL — current rules ignore `generate_type` (Normal+enable_pbr=false returns false).

- [ ] **Step 3: Rework the method**

Replace `DeriveTextureExpected`:

```csharp
internal static bool DeriveTextureExpected(JsonObject options, ReconstructionModelEntry model)
{
    if (ReadString(options, "generate_type") is { } generateType)
    {
        if (string.Equals(generateType, "Geometry", StringComparison.Ordinal)) return false;
        if (string.Equals(generateType, "Normal", StringComparison.Ordinal)) return true;
    }

    if (ReadStrictBool(options, "enable_geometry") == true) return false;   // legacy rule 1
    var pbr = ReadStrictBool(options, "enable_pbr");
    if (pbr == true) return true;                                          // legacy rule 2
    if (pbr == false) return false;                                        // legacy rule 3
    return model.DefaultTextureExpected;                                   // legacy rule 4
}
```

Add a private `ReadString(JsonObject, string)` helper to the manager if one is not already in scope (returns the string value of a `JsonValue`, else null):

```csharp
private static string? ReadString(JsonObject options, string key)
    => options.TryGetPropertyValue(key, out var node)
        && node is JsonValue value
        && value.TryGetValue<string>(out var text)
            ? text
            : null;
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests.DeriveTextureExpected"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): generate_type-driven texture expectation (Normal textures even without PBR)"
```

---

### Task 1.10: Materializer provenance — all view source ids

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionJobManager.cs` (add job-keyed source-id carrier field; populate in `SubmitCoreAsync`; read in `PollActiveJobAsync`'s 3D materialize branch; clean up in `RunJobAsync`'s `finally`)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs`

**Interfaces:**
- Consumes: `MaterializeAsync(Guid jobId, IReadOnlyList<Guid> sourceArtifactIds, ...)` (already array-shaped); the `sourceArtifactIds` list built in `SubmitCoreAsync` (Task 1.7).
- Behavior: pass **all** resolved view source ids (front + filled slots) into 3D materialization so the package's `parent_ids` capture full multi-view provenance. The ledger record keeps a single `SourceArtifactId = front` (**no schema change**).

> **Why a job-keyed dictionary (not a `RunningJob` field):** materialization happens inside `PollActiveJobAsync` (`ReconstructionJobManager.cs:496`), which rehydrates the job from the ledger via `FindJob(jobId)` and therefore only sees the single `SourceArtifactId`. `PollActiveJobAsync` is reached from **two** callers — the background loop `RunJobAsync` (`:911`) **and** on-demand `StatusAsync` (`:373`) — so the carrier must be lookup-by-`jobId`, not loop-local. The existing `RunningJob` (`_runningJobs`, `:70`) is also removed once the loop ends (`RunJobAsync` `finally`, `:934`), so a field on it wouldn't reliably cover a `StatusAsync`-driven materialization. **Use a dedicated `ConcurrentDictionary<Guid, IReadOnlyList<Guid>>` keyed by jobId**, populated at submit time and read at the materialize site, **falling back to `new[] { materializing.SourceArtifactId }` when absent** (e.g. after a process restart that lost in-memory state — front-only provenance, still correct). In-memory only; the spec mandates no ledger schema change. The `remove_background` materialize branch is unchanged (single source — no multi-view).

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionJobManagerTests.cs`, mirroring the existing concrete completion test `PollActiveJob_StatusComplete_FetchesResultAndMaterializesPackage` (`ReconstructionJobManagerTests.cs:140`) — it drives completion with `StatusComplete.Enqueue(true)` + `ResultJson = GlbResultJson` + a `Downloader.Files[...]` entry, calls `PollActiveJobAsync`, then retrieves the package via `Store.Get(status.Job.ResultArtifactId!.Value)`. The retrieved `Artifact` exposes `ParentIds` (`Artifact.cs:17`):

```csharp
[Fact]
public async Task PollActiveJob_MultiView_MaterializesPackageWithAllParentIds()
{
    var fixture = CreateFixture();
    fixture.Provider.StatusComplete.Enqueue(true);
    fixture.Provider.ResultJson = GlbResultJson;                                  // file-level const, reused
    fixture.Downloader.Files["https://example.test/model.glb"] = new byte[] { 9, 8, 7 };
    var front = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 1 }, "png") });
    var left = fixture.Store.Create("generated_image", new[] { new BlobInput("image", new byte[] { 2 }, "png") });

    var req = Request(front.Id) with
    {
        ModelId = "fal-ai/hunyuan-3d/v3.1/pro/image-to-3d",
        Views = new[]
        {
            new ReconstructionViewRequest("front", front.Id, "image"),
            new ReconstructionViewRequest("left", left.Id, "image"),
        },
    };
    var submit = await fixture.Manager.SubmitAsync(req, CancellationToken.None);
    Assert.True(submit.Success);

    await fixture.Manager.PollActiveJobAsync(submit.Job!.JobId, CancellationToken.None);

    var status = fixture.Manager.Status(submit.Job.JobId);
    Assert.Equal(ReconstructionJobState.Complete, status.Job!.State);
    var package = fixture.Store.Get(status.Job.ResultArtifactId!.Value);
    Assert.NotNull(package);
    Assert.Contains(front.Id, package!.ParentIds);
    Assert.Contains(left.Id, package.ParentIds);
}
```

(`GlbResultJson` is the same file-level constant the line-140 test uses; reuse it verbatim. The direct `PollActiveJobAsync` call is deterministic — it shares the per-job single-flight gate with the background loop that `SubmitAsync` already started.)

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests.PollActiveJob_MultiView_MaterializesPackage"`
Expected: FAIL — only the front id is passed to `MaterializeAsync` (left missing from `parent_ids`).

- [ ] **Step 3: Thread the full id list to materialization via a job-keyed carrier**

**(a) Add the carrier field** next to the existing `_runningJobs` declaration (`ReconstructionJobManager.cs:70`):

```csharp
    // Job-keyed multi-view provenance: front + filled-slot source ids in resolved order. Read at the
    // 3D materialize site (PollActiveJobAsync), which is shared by the background loop and on-demand
    // StatusAsync, so it must be lookup-by-jobId. In-memory only — the ledger keeps the single front id.
    private readonly ConcurrentDictionary<Guid, IReadOnlyList<Guid>> _jobSourceArtifactIds = new();
```

(`System.Collections.Concurrent` is already imported — `_runningJobs`/`_pollLocks` use it.)

**(b) Populate it in `SubmitCoreAsync` inside the `QueuedSubmitOutcome` branch only** — *not* right after building `sourceArtifactIds`. The post-`try` `switch` has `FailedSubmitOutcome` (`ReconstructionJobManager.cs:282`) and `default` (`:293`) branches that return without starting a background loop; only the queued branch (`:266`) calls `StartBackgroundLoop`, which is the sole place `RunJobAsync`'s cleanup `finally` runs. Populating before the switch would leak a stale entry for every failed/unexpected submit. Add the stash next to the existing `_ledger.Append(polling)` / `StartBackgroundLoop(polling)` lines:

```csharp
            case QueuedSubmitOutcome queuedOutcome:
                var handle = queuedOutcome.Handle;
                var polling = submitting with { /* ...existing handle fields unchanged... */ };
                _ledger.Append(polling);
                _jobSourceArtifactIds[jobId] = sourceArtifactIds.ToArray();   // queued only — no stale entry on failure
                StartBackgroundLoop(polling);
                return new ReconstructionSubmitResult(true, queued, null);
```

(`.ToArray()` snapshots the list as an immutable `IReadOnlyList<Guid>`. `jobId` and `sourceArtifactIds` are both in scope — `jobId` from the `Queued` record, `sourceArtifactIds` declared above the `try` in Task 1.7's Pass B.)

**(c) Read it at the 3D materialize call** in `PollActiveJobAsync` (`:567`). Replace the 3D branch's source-ids argument `new[] { materializing.SourceArtifactId }` (only the `_materializer.MaterializeAsync(...)` branch, **not** the `_preprocessMaterializer` remove_background branch) with the carried list, falling back to the front id:

```csharp
                        : await _materializer.MaterializeAsync(
                            materializing.JobId,
                            _jobSourceArtifactIds.TryGetValue(materializing.JobId, out var allSourceIds)
                                ? allSourceIds
                                : new[] { materializing.SourceArtifactId },
                            materializing.Provider,
                            materializing.ModelId,
                            success.Envelope,
                            ct).ConfigureAwait(false);
```

**(d) Clean up** in `RunJobAsync`'s `finally` (`:932`), alongside `_runningJobs.TryRemove(jobId, out _)`:

```csharp
            _runningJobs.TryRemove(jobId, out _);
            _jobSourceArtifactIds.TryRemove(jobId, out _);
```

(Cleanup is best-effort housekeeping; correctness does not depend on it — the fallback covers a missing entry. The carrier is populated **only** in the queued branch (step b), and exactly those jobs run `RunJobAsync`, so this `finally` runs for every populated entry after the job reaches a terminal state — by which point materialization is already done. Failed/unexpected submits never populate the carrier, so they need no cleanup.)

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionJobManagerTests"`
Expected: PASS (multi-view provenance + existing single-source materialization tests — single source → one-entry list, unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionJobManager.cs src/Rook.Tests/Services/Reconstruction/ReconstructionJobManagerTests.cs
git commit -m "feat(reconstruction): full multi-view provenance in materialized package parent_ids"
```

---

### Task 1.11: Handler — option metadata, capability flags, capability picker filter

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs` (`ModelToObj`, `Models`, add `OptionToObj`, replace `ThreeDProducingTasks`)
- Test: `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Produces (UI consumes): each model object gains `options` (array of `{key,label,kind,default,allowed_values,min,max,step,ignored_when}`), `supports_single_image` (bool), `supports_multi_view` (bool). Models op filters by capability: included iff `output_roles` ∩ `{model_glb, model_obj}` ≠ ∅.

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionOpHandlerTests.cs`. Add a synthetic **stable** Pro entry to the handler test's `CatalogJson` constant (line ~1205) first (full Task 1.2 entry, `"status": "stable"` so the default models call surfaces it). Then:

```csharp
[Fact]
public async Task Models_ExposesOptionsAndCapabilityFlags_ForPro()
{
    var fixture = CreateFixture();
    var response = await fixture.Handler.DispatchAsync(
        @"{""op"":""models"",""include_experimental"":true}", CancellationToken.None);

    Assert.True(response.Success);
    var json = JsonSerializer.Serialize(response.Data);
    Assert.Contains("fal-ai/hunyuan-3d/v3.1/pro/image-to-3d", json);
    Assert.Contains("\"supports_multi_view\":true", json);
    Assert.Contains("\"supports_single_image\":true", json);
    Assert.Contains("\"generate_type\"", json);
    Assert.Contains("\"allowed_values\"", json);
    Assert.Contains("\"face_count\"", json);
}

[Fact]
public async Task Models_BirefnetExcluded_ByCapabilityFilter()
{
    var fixture = CreateFixture();
    var response = await fixture.Handler.DispatchAsync(
        @"{""op"":""models"",""include_experimental"":true,""include_hidden"":true}", CancellationToken.None);

    var json = JsonSerializer.Serialize(response.Data);
    Assert.DoesNotContain("fal-ai/birefnet/v2", json);   // no model_glb/model_obj role
}
```

(The handler test `CatalogJson` must also include birefnet for the exclusion test — confirm it does, or add it.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests.Models_Exposes|FullyQualifiedName~ReconstructionOpHandlerTests.Models_Birefnet"`
Expected: FAIL — no `options`/capability flags emitted.

- [ ] **Step 3: Update the handler**

In `ReconstructionOpHandler.cs`, replace the `ThreeDProducingTasks` field (lines 144–145) with a capability predicate and update `Models` (lines 147–162):

```csharp
private static readonly string[] ImportableModelRoles = { "model_glb", "model_obj" };

private static bool ProducesImportable3D(ReconstructionModelEntry m)
    => m.OutputRoles.Any(r => Array.IndexOf(ImportableModelRoles, r) >= 0);
```

```csharp
private ApiResponse Models(Dictionary<string, JsonElement> args)
{
    var includeExperimental = GetBoolArg(args, "include_experimental") ?? false;
    var includeHidden = GetBoolArg(args, "include_hidden") ?? false;
    return Ok(new Dictionary<string, object?>
    {
        ["models"] = _catalog
            .List(includeExperimental, includeHidden)
            .Where(ProducesImportable3D)
            .Select(ModelToObj)
            .ToArray(),
        ["include_experimental"] = includeExperimental,
        ["include_hidden"] = includeHidden,
        ["warnings"] = Array.Empty<object>(),
    });
}
```

In `ModelToObj`, add the options array and capability flags (extend the returned dictionary):

```csharp
        ["options"] = model.Options is null ? null : model.Options.Select(OptionToObj).ToArray(),
        ["supports_single_image"] = !string.IsNullOrWhiteSpace(model.Input?.SourceField),
        ["supports_multi_view"] = (model.Input?.ViewSlots?.Length ?? 0) > 1,
```

Add `OptionToObj`:

```csharp
private static Dictionary<string, object?> OptionToObj(ReconstructionOptionDescriptor option)
    => new()
    {
        ["key"] = option.Key,
        ["label"] = option.Label,
        ["kind"] = option.Kind,
        ["default"] = option.Default,
        ["allowed_values"] = option.AllowedValues,
        ["min"] = option.Min,
        ["max"] = option.Max,
        ["step"] = option.Step,
        ["ignored_when"] = option.IgnoredWhen is null
            ? null
            : new Dictionary<string, object?>
            {
                ["key"] = option.IgnoredWhen.Key,
                ["equals"] = option.IgnoredWhen.EqualsValue,
            },
    };
```

(`using System.Linq;` is already present in the handler.) Update the existing `ModelsOp_Excludes_RemoveBackgroundTasks` test if its name/intent now overlaps — keep it; it still passes under the capability filter.

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite (Slice 1 gate)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS — entire suite green.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs
git commit -m "feat(reconstruction): models endpoint exposes options + capability flags; capability-based picker filter"
```

---

# SLICE 2 — UI I3D options

Scaffold source tests only (structural HTML/JS assertions via `ReadVisionResource` + `Assert.Contains`). Catalog-status-independent. Build is the managed Release build (Vision assets are embedded resources).

---

### Task 2.1: I3D option controls markup

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Modify: `src/Rook/UI/Vision/Resources/styles.css` (control styling — reuse existing `.reconstruct-field` patterns)
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

**Interfaces:**
- Produces element IDs the JS (Task 2.2) binds: `reconstruct-options` (container), `reconstruct-opt-generate-type` (select), `reconstruct-opt-enable-pbr` (checkbox), `reconstruct-opt-face-count` (number input).

- [ ] **Step 1: Write the failing test**

Add to `VisionWebSurfaceTests.cs`:

```csharp
[Fact]
public void IndexHtml_ReconstructOptions_ExposeGenerateTypePbrFaceCount()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("id=\"reconstruct-options\"", html);
    Assert.Contains("id=\"reconstruct-opt-generate-type\"", html);
    Assert.Contains("id=\"reconstruct-opt-enable-pbr\"", html);
    Assert.Contains("id=\"reconstruct-opt-face-count\"", html);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.IndexHtml_ReconstructOptions"`
Expected: FAIL — IDs absent.

- [ ] **Step 3: Add the markup**

In `index.html`, inside the Reconstruct form, after the Model select `.reconstruct-field` (the block containing `id="reconstruct-model-select"`, ~line 731) and before the mode-switch field, add:

```html
                    <!-- Catalog-driven model options (rendered/toggled by app.js) -->
                    <div class="reconstruct-field hidden" id="reconstruct-options">
                      <label class="reconstruct-label">Options</label>
                      <div class="reconstruct-option-row" id="reconstruct-opt-generate-type-row">
                        <label class="reconstruct-option-label" for="reconstruct-opt-generate-type">Generate Type</label>
                        <div class="select-wrapper">
                          <select id="reconstruct-opt-generate-type"></select>
                          <svg class="select-arrow" viewBox="0 0 24 24" fill="none">
                            <path d="M6 9L12 15L18 9" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                          </svg>
                        </div>
                      </div>
                      <div class="reconstruct-option-row" id="reconstruct-opt-enable-pbr-row">
                        <label class="reconstruct-option-label" for="reconstruct-opt-enable-pbr">Enable PBR</label>
                        <input type="checkbox" id="reconstruct-opt-enable-pbr" />
                      </div>
                      <div class="reconstruct-option-row" id="reconstruct-opt-face-count-row">
                        <label class="reconstruct-option-label" for="reconstruct-opt-face-count">Face Count</label>
                        <input type="number" id="reconstruct-opt-face-count" />
                      </div>
                    </div>
```

Add matching styling to `styles.css` (reuse existing tokens — mirror `.reconstruct-field` / `.option-hint`):

```css
.reconstruct-option-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 8px; }
.reconstruct-option-label { font-size: 13px; color: var(--text-secondary); }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.IndexHtml_ReconstructOptions"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/styles.css src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "feat(vision): I3D catalog-option controls markup (generate_type/enable_pbr/face_count)"
```

---

### Task 2.2: I3D option control behavior (render from metadata + build options)

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

**Interfaces:**
- Consumes: model objects with `options` array (Task 1.11).
- Behavior: when the selected model exposes `options`, render the controls (populate `generate_type` from `allowed_values`, set defaults, set `face_count` min/max/step); show the `reconstruct-options` container; hide it when the model has no options. `optionsForMode()` builds the submit options from the controls (omitting `enable_pbr` when `generate_type==Geometry`). When `generate_type==Geometry`, disable `enable_pbr`.

- [ ] **Step 1: Write the failing test**

Add to `VisionWebSurfaceTests.cs` (source-string assertions on app.js):

```csharp
[Fact]
public void AppJs_RendersCatalogOptions_AndGatesPbrUnderGeometry()
{
    var js = ReadVisionResource("app.js");
    // binds the option control elements
    Assert.Contains("reconstruct-opt-generate-type", js);
    Assert.Contains("reconstruct-opt-enable-pbr", js);
    Assert.Contains("reconstruct-opt-face-count", js);
    // renders from catalog metadata
    Assert.Contains("renderModelOptions", js);
    // gates enable_pbr when generate_type is Geometry
    Assert.Contains("Geometry", js);
    // options builder references the controls (not just enable_pbr/enable_geometry literals)
    Assert.Contains("generate_type", js);
    Assert.Contains("face_count", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.AppJs_RendersCatalogOptions"`
Expected: FAIL — `renderModelOptions`/`generate_type` absent.

- [ ] **Step 3: Implement the JS**

In `app.js`, register the new elements in the `re` element map (where `re.modelSelect` etc. are defined) and add a `renderModelOptions` function. Cache controls:

```javascript
re.options = $("reconstruct-options");
re.optGenerateType = $("reconstruct-opt-generate-type");
re.optEnablePbr = $("reconstruct-opt-enable-pbr");
re.optFaceCount = $("reconstruct-opt-face-count");
```

(Use the file's existing element-lookup helper — match how `re.modelSelect` is assigned; if it uses `document.getElementById`, mirror that.)

Add the renderer and call it from `updateModelHint()`/model-change (where `selectedModel()` is available):

```javascript
function renderModelOptions() {
    const model = selectedModel();
    const opts = (model && Array.isArray(model.options)) ? model.options : null;
    if (!opts || opts.length === 0) {
        re.options.classList.add("hidden");
        return;
    }
    re.options.classList.remove("hidden");
    for (const d of opts) {
        if (d.key === "generate_type") {
            re.optGenerateType.innerHTML = (d.allowed_values || [])
                .map(v => `<option value="${escapeAttr(v)}">${escapeHtml(v)}</option>`).join("");
            if (d.default != null) re.optGenerateType.value = String(d.default);
        } else if (d.key === "enable_pbr") {
            re.optEnablePbr.checked = d.default === true;
        } else if (d.key === "face_count") {
            if (d.min != null) re.optFaceCount.min = d.min;
            if (d.max != null) re.optFaceCount.max = d.max;
            if (d.step != null) re.optFaceCount.step = d.step;
            if (d.default != null) re.optFaceCount.value = d.default;
        }
    }
    applyGenerateTypeGating();
}

function applyGenerateTypeGating() {
    const geometry = re.optGenerateType.value === "Geometry";
    re.optEnablePbr.disabled = geometry;
    if (geometry) re.optEnablePbr.checked = false;
}
```

Wire `applyGenerateTypeGating` to the generate-type select's `change` event, and call `renderModelOptions()` from the model-select change handler and from `setReconstructMode`. Extend `optionsForMode()` so that, when the selected model has catalog options, it builds from the controls:

```javascript
function optionsForMode() {
    const model = selectedModel();
    if (model && Array.isArray(model.options) && model.options.length > 0) {
        const o = {};
        if (re.optGenerateType.value) o.generate_type = re.optGenerateType.value;
        if (o.generate_type !== "Geometry" && re.optEnablePbr.checked) o.enable_pbr = true;
        const fc = parseInt(re.optFaceCount.value, 10);
        if (!Number.isNaN(fc)) o.face_count = fc;
        return o;
    }
    // legacy models: existing behavior
    if (outputMode === "geometry") return { enable_geometry: true };
    return model && model.supports_pbr ? { enable_pbr: true } : {};
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.AppJs_RendersCatalogOptions"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/UI/Vision/Resources/app.js src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "feat(vision): render I3D catalog options + build submit options from controls"
```

---

# SLICE 3 — UI MV3D submit

---

### Task 3.1: MV3D slot markup (Fal slots replace three_quarter)

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/index.html`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

**Interfaces:**
- Produces: MV3D slot panes for `bottom`, `left_front`, `right_front` (replacing `three_quarter`), each with `data-slot` + `.btn-slot-pick`/`.btn-slot-clear` matching the existing slot pattern.

- [ ] **Step 1: Write the failing test**

```csharp
[Fact]
public void IndexHtml_Mv3dSlots_UseFalVocabulary()
{
    var html = ReadVisionResource("index.html");
    Assert.Contains("data-slot=\"bottom\"", html);
    Assert.Contains("data-slot=\"left_front\"", html);
    Assert.Contains("data-slot=\"right_front\"", html);
    Assert.DoesNotContain("data-slot=\"three_quarter\"", html);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.IndexHtml_Mv3dSlots"`
Expected: FAIL — `three_quarter` still present; new slots absent.

- [ ] **Step 3: Replace the slot markup**

In `index.html`, within `#reconstruct-mv-slots`, replace the single `three_quarter` slot block with `bottom`, `left_front`, `right_front` blocks (mirror the existing optional-slot structure). Example for one (repeat for each, adjusting `data-slot` + label):

```html
                        <div class="reconstruct-slot reconstruct-slot-optional" data-slot="bottom">
                          <span class="reconstruct-slot-label">bottom &middot; optional</span>
                          <div class="reconstruct-slot-thumb"></div>
                          <div class="reconstruct-slot-actions">
                            <button class="btn-text btn-slot-pick" data-slot="bottom">Pick</button>
                            <button class="btn-text btn-slot-clear" data-slot="bottom">Clear</button>
                          </div>
                        </div>
                        <div class="reconstruct-slot reconstruct-slot-optional" data-slot="left_front">
                          <span class="reconstruct-slot-label">left front &middot; optional</span>
                          <div class="reconstruct-slot-thumb"></div>
                          <div class="reconstruct-slot-actions">
                            <button class="btn-text btn-slot-pick" data-slot="left_front">Pick</button>
                            <button class="btn-text btn-slot-clear" data-slot="left_front">Clear</button>
                          </div>
                        </div>
                        <div class="reconstruct-slot reconstruct-slot-optional" data-slot="right_front">
                          <span class="reconstruct-slot-label">right front &middot; optional</span>
                          <div class="reconstruct-slot-thumb"></div>
                          <div class="reconstruct-slot-actions">
                            <button class="btn-text btn-slot-pick" data-slot="right_front">Pick</button>
                            <button class="btn-text btn-slot-clear" data-slot="right_front">Clear</button>
                          </div>
                        </div>
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.IndexHtml_Mv3dSlots"`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "feat(vision): MV3D slot vocabulary matches Fal Pro (bottom/left_front/right_front)"
```

---

### Task 3.2: MV3D submit action (build views[])

**Files:**
- Modify: `src/Rook/UI/Vision/Resources/app.js`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`

**Interfaces:**
- Consumes: backend `submit_job` op accepting `views[]` (Slice 1).
- Behavior: the slot-state object replaces `three_quarter` with `bottom`/`left_front`/`right_front`; the MV3D action submits (front from `source_artifact_id` + filled secondary slots → `views[]`), reusing the I3D `submit()` body plus a `views` array; `assemble_view_set` stays an optional helper (not on the submit path); `updateReconstructActionForMode("mv3d")` enables submit.

- [ ] **Step 1: Write the failing test**

```csharp
[Fact]
public void AppJs_Mv3dSubmits_ViewsArray_AndDropsThreeQuarterState()
{
    var js = ReadVisionResource("app.js");
    // slot-state object uses the Fal vocabulary
    Assert.Contains("left_front", js);
    Assert.Contains("right_front", js);
    Assert.DoesNotContain("three_quarter", js);
    // submit carries a views[] array
    Assert.Contains("views:", js);
    // MV3D action is no longer the disabled "Assemble view set" stub
    Assert.DoesNotContain("Slot assembly wires next.", js);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.AppJs_Mv3dSubmits"`
Expected: FAIL — `three_quarter` still in slot state; no `views:` key; stub text present.

- [ ] **Step 3: Implement the JS**

Update the slot-state object (currently `{ front: null, left: null, right: null, back: null, top: null, three_quarter: null }`):

```javascript
const slots = { front: null, left: null, right: null, back: null, top: null, bottom: null, left_front: null, right_front: null };
```

In `submit()`, build `views[]` from filled slots and include it in the `submit_job` payload:

```javascript
        const views = Object.keys(slots)
            .filter(s => slots[s] && slots[s].artifact_id)
            .map(s => ({ slot: s, artifact_id: slots[s].artifact_id, role: slots[s].role || "image" }));
        const job = await reconstructionBridgeCall("submit_job", {
            source_artifact_id: frontSlot.artifact_id,
            source_role: frontSlot.role || "image",
            model_id: modelId,
            preprocessing_chain: [],
            options: optionsForMode(),
            views: views,
            estimate_requested: false,
        });
```

(For I3D the `views` array is just the front entry, which the backend accepts as a canonical-front restatement — harmless. Alternatively gate `views` to `reconstructMode === "mv3d"`; either is correct since the backend treats a front-only views list as a no-op restatement.)

Update `updateReconstructActionForMode` MV3D branch to enable submit:

```javascript
    } else { // mv3d
        re.submitBtn.textContent = "Reconstruct";
        re.submitBtn.disabled = false;
        re.actionNote.textContent = "";
    }
```

Confirm `renderSlot`/`fillSlot`/`clearSlot` already key off the `slots` object generically (they do — secondary slots are looked up by `[data-slot]`), so the new slots work without further change.

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~VisionWebSurfaceTests.AppJs_Mv3dSubmits"`
Expected: PASS.

- [ ] **Step 5: Run the full test suite (Slice 3 gate)**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/UI/Vision/Resources/app.js src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs
git commit -m "feat(vision): MV3D submits labeled views[]; assemble_view_set demoted to optional helper"
```

---

# SLICE 4 — Stable flip + live gate

---

### Task 4.1: Flip Pro to stable

**Files:**
- Modify: `src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs`

**Interfaces:**
- Behavior: Pro `status` → `stable`; the default (non-experimental) models call surfaces it.

- [ ] **Step 1: Write the failing test**

Add to `ReconstructionModelCatalogTests.cs`:

```csharp
[Fact]
public void ProductionCatalog_HunyuanPro_IsStable()
{
    var pro = LoadProductionCatalog().Find("fal-ai/hunyuan-3d/v3.1/pro/image-to-3d");
    Assert.Equal("stable", pro!.Status);
}
```

Update the Task 1.2 test `ProductionCatalog_IncludesHunyuanPro_WithEightSlotsAndThreeOptions` assertion `Assert.Equal("experimental", pro!.Status)` → `Assert.Equal("stable", pro!.Status)`.

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~ReconstructionModelCatalogTests.ProductionCatalog_HunyuanPro_IsStable"`
Expected: FAIL — status is `experimental`.

- [ ] **Step 3: Flip the status**

In `fal-model-catalog.json`, change the Pro entry `"status": "experimental"` → `"status": "stable"`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
Expected: PASS — full suite green.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/Fal/fal-model-catalog.json src/Rook.Tests/Services/Reconstruction/ReconstructionModelCatalogTests.cs
git commit -m "feat(reconstruction): flip Hunyuan 3D Pro to stable"
```

---

### Task 4.2: Live roundtrip gate (manual merge gate)

**Files:** none (verification only).

This task is the **merge gate** — a live 2D→3D Pro roundtrip on the deployed Release build, mirroring the reconstruction lineage's live-gate practice. It is performed by the user/operator, not automated.

- [ ] **Step 1: Deploy the Release build**

Build + deploy via the standard local-testing flow:

```powershell
pwsh -File scripts/deploy-local-testing.ps1
```

Vision web assets are embedded resources in the managed companion, so a managed Release build is the relevant deploy (no native build needed for this feature). Restart Rhino so the redeployed `Rook.rhp` + chat server load, then verify connectivity with `rhino_ping` (expect `pong`). If the `models` MCP op does not surface the Pro entry after restart, confirm Claude Code loaded the **installed Release** MCP — a repo-local `.mcp.json` pointing at the dev/feature tree can shadow it; if so, move the repo `.mcp.json` aside, reconnect, then restore it.

- [ ] **Step 2: Single-image Pro roundtrip**

Drive a single front image through Pro (`fal-ai/hunyuan-3d/v3.1/pro/image-to-3d`) with `generate_type=Normal`: submit → poll to complete → result has a textured model package → import to Rhino yields a visible mesh (doc object count increments; non-degenerate bbox).

- [ ] **Step 3: Multi-view Pro roundtrip**

Drive front + at least one secondary slot (e.g. `left`, `back`) through Pro multi-view: the submit payload carries each image under its named Fal field; job completes; package imports a visible mesh. Verify a `Geometry` run produces a geometry-only (untextured) result and `Normal` produces a textured result.

- [ ] **Step 4: Record the result**

Record the live-gate outcome (job ids, package id, model id, timings, textured-vs-geometry observation) in the PR description and update the reconstruction memory topic. Only after a passing live gate is the slice considered complete and mergeable.

---

## Self-Review

**1. Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §1 goal: labeled views, correct Fal fields, controls, generate-type texture | Tasks 1.3, 1.5, 1.7, 1.9, 2.1, 2.2 |
| §3.1 inline `views[]`; assemble_view_set optional | Tasks 1.3, 3.2 |
| §3.2 / §4 front canonical + immutable (artifact AND role) | Task 1.7 (`ResolveViews`) |
| §3.3 capability via metadata, both modes | Tasks 1.6, 1.11, 2.2, 3.2 |
| §3.4 / §5 bounded options block | Tasks 1.1, 1.2, 1.4 |
| §5 catalog types + Pro entry + output-role constants | Tasks 1.1, 1.2 |
| §6 models endpoint flags + capability picker filter | Task 1.11 |
| §7 provider ViewUrls payload | Task 1.5 |
| §8 capability gate, multi-view validation, publish, options validator, texture rework | Tasks 1.6, 1.7, 1.8, 1.9 |
| §9 materializer provenance | Task 1.10 |
| §10 UI I3D + MV3D + vocabulary expansion | Tasks 1.2, 2.1, 2.2, 3.1, 3.2 |
| §10 experimental visibility during 1–3 | synthetic stable catalogs in tests; `include_experimental` for manual |
| §11 four slices | Slices 1–4 |
| §12 validation/error table | Tasks 1.3, 1.4, 1.7, 1.8 |
| §13 test strategy (per-layer + live gate) | every task's tests + Task 4.2 |

No uncovered spec requirement.

**2. Placeholder scan:** No "TBD"/"add error handling"/"similar to Task N" — each step shows concrete code or a concrete command. Task 1.10's carrier (field + populate + read + cleanup) and its provenance test now use verbatim code at named line numbers, modeled on the real `PollActiveJob_StatusComplete_FetchesResultAndMaterializesPackage` test (`:140`) — no pseudo-helper. The only remaining "mirror the existing entry" note (handler/manager-test `CatalogJson` constant edits) is a concrete file-local edit to a single named constant, not a hand-wave; surrounding code is fully specified.

**3. Contract placement (reviewer fix #1):** `ReconstructionSubmitRequest` / `ReconstructionParseResult` / `ReconstructionPreprocessingStageRequest` are declared in `ReconstructionSubmitRequestParser.cs` (line 8+), **not** `ReconstructionContracts.cs` (which holds only `Reconstruction*` constants). Task 1.3 adds `ReconstructionViewRequest` + `Views` there; Task 1.2 adds constants to `ReconstructionContracts.cs`. No duplicate contract placement. ✓

**4. Provenance carrier (reviewer fix #2 + round-3 P2):** `_jobSourceArtifactIds` is a `ConcurrentDictionary<Guid, IReadOnlyList<Guid>>` keyed by jobId — populated **only inside the `QueuedSubmitOutcome` branch** of `SubmitCoreAsync` (so `FailedSubmitOutcome`/`default` submits leave no stale entry), read at the 3D materialize site in `PollActiveJobAsync` (shared by `StatusAsync` + the loop), fallback to `[SourceArtifactId]` when absent, cleaned in `RunJobAsync`'s `finally`. `sourceArtifactIds` is declared above the `try` (Task 1.7 Pass B) so it is in scope at the switch. No ledger schema change. ✓

**5. Provider request construction sites (round-3 P1):** the production manager has one construction site, but `FalReconstructionProviderTests.cs` constructs `ReconstructionProviderSubmitRequest` **eight** times (lines 31/61/84/100/114/126/142/161). Task 1.5 Step 1 adds a `Req(...)` helper and updates all eight (table provided) + a verifying `rg` sweep, so the provider suite compiles. ✓

**6. Type consistency:**
- `ReconstructionViewRequest(Slot, ArtifactId, Role)` — produced Task 1.3 (in `ReconstructionSubmitRequestParser.cs`), consumed Tasks 1.7/3.2. ✓
- `ReconstructionProviderViewUrl(Field, Url)` + `ViewUrls` — produced Task 1.5, consumed Tasks 1.5/1.7. ✓
- `ReconstructionOptionDescriptor` / `ReconstructionOptionIgnoredWhen.EqualsValue` (not `Equals`) — produced Task 1.1, consumed Tasks 1.4/1.11/2.2. ✓
- `ReconstructionOptionsValidator.Validate` → `ReconstructionOptionsResult` — produced Task 1.4, consumed Task 1.8. ✓
- `IsSubmittable3DModel` — Task 1.6, gate call updated same task. ✓
- `DeriveTextureExpected(JsonObject, ReconstructionModelEntry)` — signature unchanged; body reworked Task 1.9. ✓
- Failure `Details["reason"]` codes (`conflicting_front`, `unsupported_slot`, `duplicate_slot`, `unknown_option`) consistent between Tasks 1.4/1.7/1.8 and their tests. ✓

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-23-hunyuan-3d-pro-image-to-3d.md`. **Do not implement production code yet** — this plan is for review/approval first (per the takeover brief).
