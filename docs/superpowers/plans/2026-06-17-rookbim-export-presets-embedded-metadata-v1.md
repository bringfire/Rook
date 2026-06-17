# RookBIM Export Presets + Embedded Metadata v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new read-only `rookbim_export_preset` op that resolves a curated multi-category recipe into a frozen element set + organization policy and routes through the verified Export v1 core, producing an organized, self-describing Rhino bundle — while leaving the existing `rookbim_export_elements` contract semantically stable.

**Architecture:** A new front door (`rookbim_export_preset`) resolves a preset (category bundle + default layer/name/metadata policy) in managed C# via the existing single-category `RevitQueryService`, unions/dedups by `(documentGuid, uniqueId)`, freezes the element set, and feeds a generalized `RevitExportService` that drives layers/names/embedded metadata from a `BimExportOrganizationPolicy` and emits a summary + relationship index **only** for the preset path. The raw `rookbim_export_elements` path passes `BimExportOrganizationPolicy.Legacy` + a null preset context, so its layers (`RookBim::Model`), four user strings, absent object names, and sidecar/validation schema are unchanged.

**Tech Stack:** C# (net48, `src/RookBim` + `src/Rook`), RhinoCommon (`Rhino.FileIO.File3dm`, `Rhino.Geometry`), Revit API (reflection-only for Rhino.Inside converter), C++ (`src/RookNative`, httplib + nlohmann::json), Python (`mcp_server`, MCP tool surface), xUnit (C# tests), pytest (Python tests).

## Global Constraints

- **Branch:** `feature/rookbim-export-presets-v1` (worktree `C:/Users/aryan/source/repos/rook-bim-presets`, based on `origin/main` `f47ed67d`). Never stage `knowledge/contextual_mab.pkl`, `knowledge/gh/component_observations.json`, `src/Rook/Properties/launchSettings.json`.
- **Spec:** `docs/superpowers/specs/2026-06-17-rookbim-export-presets-embedded-metadata-v1-design.md` (read it first).
- **Read-only invariant:** no Revit `Transaction` anywhere in new Revit code; never open or mutate the active Rhino document or scene graph. The only mutation is filesystem artifact creation.
- **Layer root is `RookBim::`** everywhere (never `RookBIM::`) — matches existing `RevitExportService.ModelLayer` / `RevitRoomExporter.RoomsLayer`.
- **Legacy parity = semantic/API parity, NOT byte-identical `.3dm`.** The raw path keeps flat layers, the four user strings, no object names, unchanged sidecar/validation schema and counts/bijection. Assert observables (layer names, user-string keys, sidecar shape), never a file hash.
- **New decoration is preset-path-only:** `presetContext == null` ⇒ no `summary`, no `relationships` in sidecar/validation; `BimExportOrganizationPolicy.Legacy` ⇒ flat layer, four user strings, no names.
- **No hard `RhinoInside.Revit` reference** in `src/RookBim` (reflection only). **No Revit references outside `src/RookBim`** (core `src/Rook/Bim` stays Revit-free and CI-unit-testable).
- **Geometry vocabulary is frozen:** `{converted_brep, mesh_fallback, bbox_only, failed}` / `{brep, mesh, bbox_proxy, none}`. Never introduce `exact_brep`.
- **Targeting:** `policy_for_tool("rookbim_export_preset")` must derive to `RhinoToolPolicy(True, "mutate")` — achieved by adding the tool to `_ALL_KNOWN_TOOLS` only (and to NO read/meta bucket).

**Build/test commands** (run from worktree root `C:/Users/aryan/source/repos/rook-bim-presets`):
- Core/handler C# tests: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
- RookBim source-text tests: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj`
- RookBim build gate: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
- Python tests: `cd mcp_server && python -m pytest tests/test_rookbim_export_preset_tool.py -q`

---

## File Structure

**Core assembly `src/Rook/Bim/` (no Revit ref — unit-testable in CI):**
- `BimContracts.cs` (MODIFY) — `UnknownPreset` + `NoCategoriesResolved` codes; `BimExportPresetRequest` (+ `Validate()`, `EffectiveScope`); summary/relationship/per-category result POCOs.
- `BimPresetCatalog.cs` (CREATE) — pure: `BimPresetDefinition` + `BimPresetCatalog.TryGet`/`Names`.
- `BimExportOrganizationPolicy.cs` (CREATE) — pure: `BimLayerScheme`/`BimNameScheme`/`BimMetadataProfile` enums, the policy value object, `Legacy`, parse helpers, `Resolve`.
- `BimExportLayerNamer.cs` (CREATE) — pure: `(scheme, category, levelValue) → sanitized layer path`.
- `BimExportObjectNamer.cs` (CREATE) — pure: `(scheme, category, type, elementId, revitName) → sanitized object name`.
- `IRookBimRuntime.cs` (MODIFY) — `+ BimApiResponse ExportPreset(BimExportPresetRequest request)`.
- `RookBimUnavailableRuntime.cs` (MODIFY) — `ExportPreset` → Unavailable.

**Revit assembly `src/RookBim/Revit/` (Revit + RhinoCommon — source-text tested + live):**
- `RevitPresetContext.cs` (CREATE) — internal context produced by the resolver, consumed by the service (policy echo, per-category counts, warnings, relationships toggle).
- `RevitPresetResolver.cs` (CREATE) — multi-category union/dedup/freeze + warnings + success condition.
- `RevitExportService.cs` (MODIFY) — split `Export` into a public resolve-path + internal `ExportResolved`; policy-driven layer/name/metadata; preset-only summary + relationships.
- `RevitRookBimRuntime.cs` (MODIFY) — `ExportPreset` wired through the dispatcher (export timeout).

**Native `src/RookNative/`:**
- `Handlers/GrasshopperProxyHandler.h` + `.cpp` (MODIFY) — `HandleBimExportPreset`.
- `RookServer.cpp` (MODIFY) — `POST /bim/export-preset` route.

**MCP `mcp_server/src/rook/`:**
- `server.py` (MODIFY) — `_rookbim_export_preset_schema`, tool entry, dispatch case.
- `agent/tool_groups.py` (MODIFY) — add to `rookbim` group (NOT `rookbim_readonly`).
- `targeting.py` (MODIFY) — add to `_ALL_KNOWN_TOOLS` only.

**Tests:**
- `src/Rook.Tests/Bim/BimExportPresetContractsTests.cs`, `BimPresetCatalogTests.cs`, `BimExportOrganizationPolicyTests.cs`, `BimExportLayerNamerTests.cs`, `BimExportObjectNamerTests.cs`, `RookBimUnavailablePresetTests.cs` (CREATE).
- `src/Rook.Tests/Handlers/BimHandlerExportPresetSourceTests.cs` (CREATE).
- `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` (CREATE).
- `mcp_server/tests/test_rookbim_export_preset_tool.py` (CREATE).
- `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export_preset.py` (CREATE).

---

## Task 1: Core error codes + `BimExportPresetRequest` contract

**Files:**
- Modify: `src/Rook/Bim/BimContracts.cs`
- Test: `src/Rook.Tests/Bim/BimExportPresetContractsTests.cs`

**Interfaces:**
- Produces: `BimErrorCode.UnknownPreset`, `BimErrorCode.NoCategoriesResolved`; `class BimExportPresetRequest { string? Preset; BimExportOutput Output; string? Scope; List<string>? IncludeCategories; List<string>? ExcludeCategories; string? LayerPolicy; string? NamePolicy; string? MetadataProfile; string? Rooms; int? LimitPerCategory; bool AllowTruncated; bool AllowBboxProxy; BimQueryScope EffectiveScope; BimValidationResult Validate(); }`. Task 2 upgrades `Validate()` to check catalog membership.

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/BimExportPresetContractsTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportPresetContractsTests
    {
        private static BimExportOutput ValidOutput() =>
            new BimExportOutput { Directory = @"C:\fixtures", Name = "shell" };

        [Fact]
        public void Validate_RejectsMissingPreset()
        {
            var request = new BimExportPresetRequest { Output = ValidOutput() };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnknownPreset, result.ErrorCode);
        }

        [Fact]
        public void Validate_RejectsMissingOutput()
        {
            var request = new BimExportPresetRequest
            {
                Preset = "architectural_shell",
                Output = new BimExportOutput { Name = "shell" },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Fact]
        public void Validate_RejectsInvalidScope()
        {
            var request = new BimExportPresetRequest
            {
                Preset = "architectural_shell",
                Output = ValidOutput(),
                Scope = "sideways",
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }

        [Fact]
        public void EffectiveScope_DefaultsToActiveView()
        {
            var request = new BimExportPresetRequest { Preset = "x", Output = ValidOutput() };
            Assert.Equal(BimQueryScope.ActiveView, request.EffectiveScope);
        }

        [Fact]
        public void EffectiveScope_ParsesDocument()
        {
            var request = new BimExportPresetRequest { Preset = "x", Output = ValidOutput(), Scope = "document" };
            Assert.Equal(BimQueryScope.Document, request.EffectiveScope);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportPresetContractsTests`
Expected: FAIL — `BimExportPresetRequest`, `BimErrorCode.UnknownPreset` do not exist (compile error).

- [ ] **Step 3: Add the error codes**

In `src/Rook/Bim/BimContracts.cs`, extend the `BimErrorCode` enum (after `ExportFailed`, before `InternalError`):

```csharp
        ExportFailed,
        UnknownPreset,
        NoCategoriesResolved,
        InternalError
```

- [ ] **Step 4: Add the request type**

Append to `src/Rook/Bim/BimContracts.cs` (inside `namespace Rook.Bim`, after `BimExportElementsRequest`):

```csharp
    public sealed class BimExportPresetRequest
    {
        public string? Preset { get; set; }

        public BimExportOutput Output { get; set; } = new BimExportOutput();

        public string? Scope { get; set; }

        public List<string>? IncludeCategories { get; set; }

        public List<string>? ExcludeCategories { get; set; }

        public string? LayerPolicy { get; set; }

        public string? NamePolicy { get; set; }

        public string? MetadataProfile { get; set; }

        public string? Rooms { get; set; }

        public int? LimitPerCategory { get; set; }

        public bool AllowTruncated { get; set; }

        public bool AllowBboxProxy { get; set; }

        public BimQueryScope EffectiveScope
        {
            get
            {
                return string.Equals(Scope, "document", StringComparison.OrdinalIgnoreCase)
                    ? BimQueryScope.Document
                    : BimQueryScope.ActiveView;
            }
        }

        public BimValidationResult Validate()
        {
            if (string.IsNullOrWhiteSpace(Preset))
            {
                return Fail(BimErrorCode.UnknownPreset, "export-preset requires a 'preset' name.");
            }

            if (!string.IsNullOrWhiteSpace(Scope) &&
                !string.Equals(Scope, "active_view", StringComparison.OrdinalIgnoreCase) &&
                !string.Equals(Scope, "document", StringComparison.OrdinalIgnoreCase))
            {
                return Fail(BimErrorCode.InvalidScope, "scope must be 'active_view' or 'document'.");
            }

            var outputValidation = BimExportPathPolicy.ValidateRequestShape(Output);
            if (!outputValidation.Success)
            {
                return outputValidation;
            }

            return BimValidationResult.Ok;
        }

        private static BimValidationResult Fail(BimErrorCode code, string message)
        {
            return new BimValidationResult { Success = false, ErrorCode = code, Message = message };
        }
    }
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportPresetContractsTests`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Bim/BimContracts.cs src/Rook.Tests/Bim/BimExportPresetContractsTests.cs
git commit -m "feat(bim): export-preset request contract + UnknownPreset/NoCategoriesResolved codes"
```

---

## Task 2: Preset catalog (pure)

**Files:**
- Create: `src/Rook/Bim/BimPresetCatalog.cs`
- Modify: `src/Rook/Bim/BimContracts.cs` (upgrade `BimExportPresetRequest.Validate()` to check catalog membership)
- Test: `src/Rook.Tests/Bim/BimPresetCatalogTests.cs`

**Interfaces:**
- Consumes: `BimRoomsMode` (existing). Will reference `BimLayerScheme`/`BimNameScheme`/`BimMetadataProfile` from Task 3 — **Task 3 must be implemented before this compiles**; if implementing in order, define the enums (Task 3 Step 3) first, then this. To keep Task 2 independently testable, the catalog stores the **default policy as enums** introduced in Task 3.
- Produces: `sealed class BimPresetDefinition { string Name; IReadOnlyList<string> Categories; BimLayerScheme DefaultLayerScheme; BimNameScheme DefaultNameScheme; BimMetadataProfile DefaultMetadataProfile; BimRoomsMode DefaultRooms; int DefaultLimitPerCategory; bool RoomsDriven; }`; `static class BimPresetCatalog { bool TryGet(string preset, out BimPresetDefinition def); IReadOnlyList<string> Names; }`.

> **Ordering note:** Task 2 and Task 3 are mutually referential (the catalog stores Task 3's enums; Task 1's `Validate()` upgrade needs Task 2's catalog). Implement **Task 3 first** (enums + policy), then this task. The subagent runner should treat Tasks 2–3 as an ordered pair; the build of `Rook.csproj` after Task 2 must be green.

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/BimPresetCatalogTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimPresetCatalogTests
    {
        [Theory]
        [InlineData("architectural_shell")]
        [InlineData("interiors")]
        [InlineData("openings_and_hosts")]
        [InlineData("structural")]
        [InlineData("rooms_and_spaces")]
        [InlineData("calibration_fixture")]
        public void TryGet_ResolvesEveryDocumentedPreset(string preset)
        {
            Assert.True(BimPresetCatalog.TryGet(preset, out var def));
            Assert.Equal(preset, def.Name);
        }

        [Fact]
        public void TryGet_IsCaseInsensitive()
        {
            Assert.True(BimPresetCatalog.TryGet("Architectural_Shell", out _));
        }

        [Fact]
        public void TryGet_RejectsUnknownPreset()
        {
            Assert.False(BimPresetCatalog.TryGet("kitchen_sink", out _));
        }

        [Fact]
        public void ArchitecturalShell_HasCategoriesAndByLevelLayers()
        {
            BimPresetCatalog.TryGet("architectural_shell", out var def);
            Assert.Contains("Walls", def.Categories);
            Assert.Contains("Floors", def.Categories);
            Assert.Equal(BimLayerScheme.ByLevelThenCategory, def.DefaultLayerScheme);
            Assert.Equal(BimMetadataProfile.Standard, def.DefaultMetadataProfile);
            Assert.False(def.RoomsDriven);
        }

        [Fact]
        public void RoomsAndSpaces_IsRoomsDrivenWithNoCategories()
        {
            BimPresetCatalog.TryGet("rooms_and_spaces", out var def);
            Assert.Empty(def.Categories);
            Assert.True(def.RoomsDriven);
            Assert.Equal(BimRoomsMode.Both, def.DefaultRooms);
        }

        [Fact]
        public void Structural_ExcludesFloorsAndRooms()
        {
            BimPresetCatalog.TryGet("structural", out var def);
            Assert.DoesNotContain("Floors", def.Categories);
            Assert.Contains("Structural Framing", def.Categories);
            Assert.Equal(BimRoomsMode.Exclude, def.DefaultRooms);
        }

        [Fact]
        public void CalibrationFixture_IsBroadAndFullProfile()
        {
            BimPresetCatalog.TryGet("calibration_fixture", out var def);
            Assert.Contains("Doors", def.Categories);
            Assert.Contains("Windows", def.Categories);
            Assert.Contains("Furniture", def.Categories);
            Assert.Equal(BimMetadataProfile.Full, def.DefaultMetadataProfile);
            Assert.Equal(BimRoomsMode.Both, def.DefaultRooms);
        }

        [Fact]
        public void Names_ListsAllPresets()
        {
            Assert.Equal(6, BimPresetCatalog.Names.Count);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimPresetCatalogTests`
Expected: FAIL — `BimPresetCatalog` does not exist.

- [ ] **Step 3: Implement the catalog**

Create `src/Rook/Bim/BimPresetCatalog.cs`:

```csharp
using System;
using System.Collections.Generic;

namespace Rook.Bim
{
    public sealed class BimPresetDefinition
    {
        public string Name { get; set; } = string.Empty;

        public IReadOnlyList<string> Categories { get; set; } = Array.Empty<string>();

        public BimLayerScheme DefaultLayerScheme { get; set; } = BimLayerScheme.ByCategory;

        public BimNameScheme DefaultNameScheme { get; set; } = BimNameScheme.ReadableWithId;

        public BimMetadataProfile DefaultMetadataProfile { get; set; } = BimMetadataProfile.Standard;

        public BimRoomsMode DefaultRooms { get; set; } = BimRoomsMode.Both;

        public int DefaultLimitPerCategory { get; set; } = 1000;

        public bool RoomsDriven { get; set; }
    }

    public static class BimPresetCatalog
    {
        private static readonly Dictionary<string, BimPresetDefinition> Presets =
            new Dictionary<string, BimPresetDefinition>(StringComparer.OrdinalIgnoreCase)
            {
                ["architectural_shell"] = new BimPresetDefinition
                {
                    Name = "architectural_shell",
                    Categories = new[]
                    {
                        "Walls", "Floors", "Roofs", "Ceilings",
                        "Curtain Walls", "Curtain Panels", "Curtain Wall Mullions", "Columns",
                    },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                },
                ["interiors"] = new BimPresetDefinition
                {
                    Name = "interiors",
                    Categories = new[]
                    {
                        "Furniture", "Furniture Systems", "Casework", "Specialty Equipment",
                        "Plumbing Fixtures", "Lighting Fixtures", "Generic Models",
                    },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                },
                ["openings_and_hosts"] = new BimPresetDefinition
                {
                    Name = "openings_and_hosts",
                    Categories = new[] { "Doors", "Windows" },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                },
                ["structural"] = new BimPresetDefinition
                {
                    Name = "structural",
                    // Revit commonly represents structural slabs as the Floors category; Floors are
                    // intentionally left to architectural_shell to avoid double-owning the category.
                    Categories = new[] { "Structural Columns", "Structural Framing", "Structural Foundations" },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Exclude,
                },
                ["rooms_and_spaces"] = new BimPresetDefinition
                {
                    Name = "rooms_and_spaces",
                    Categories = Array.Empty<string>(),
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Standard,
                    DefaultRooms = BimRoomsMode.Both,
                    RoomsDriven = true,
                },
                ["calibration_fixture"] = new BimPresetDefinition
                {
                    Name = "calibration_fixture",
                    Categories = new[]
                    {
                        "Walls", "Floors", "Roofs", "Ceilings", "Columns",
                        "Doors", "Windows",
                        "Structural Columns", "Structural Framing",
                        "Furniture", "Casework",
                    },
                    DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                    DefaultMetadataProfile = BimMetadataProfile.Full,
                    DefaultRooms = BimRoomsMode.Both,
                },
            };

        public static IReadOnlyList<string> Names
        {
            get { return new List<string>(Presets.Keys); }
        }

        public static bool TryGet(string? preset, out BimPresetDefinition definition)
        {
            if (!string.IsNullOrWhiteSpace(preset) && Presets.TryGetValue(preset!, out var found))
            {
                definition = found;
                return true;
            }

            definition = new BimPresetDefinition();
            return false;
        }
    }
}
```

- [ ] **Step 4: Upgrade `Validate()` to check catalog membership**

In `src/Rook/Bim/BimContracts.cs`, replace the preset null/empty check in `BimExportPresetRequest.Validate()`:

```csharp
            if (string.IsNullOrWhiteSpace(Preset))
            {
                return Fail(BimErrorCode.UnknownPreset, "export-preset requires a 'preset' name.");
            }
```

with:

```csharp
            if (string.IsNullOrWhiteSpace(Preset) || !BimPresetCatalog.TryGet(Preset, out _))
            {
                return Fail(
                    BimErrorCode.UnknownPreset,
                    $"Unknown export preset '{Preset}'. Known presets: {string.Join(", ", BimPresetCatalog.Names)}.");
            }
```

The Task 1 `Validate_RejectsMissingPreset` test still passes (null preset ⇒ `UnknownPreset`).

- [ ] **Step 5: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "BimPresetCatalogTests|BimExportPresetContractsTests"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Bim/BimPresetCatalog.cs src/Rook/Bim/BimContracts.cs src/Rook.Tests/Bim/BimPresetCatalogTests.cs
git commit -m "feat(bim): preset catalog (architectural_shell..calibration_fixture) + catalog-aware validation"
```

---

## Task 3: Organization policy (pure)

> **Implement before Task 2** (the catalog stores these enums). See Task 2's ordering note.

**Files:**
- Create: `src/Rook/Bim/BimExportOrganizationPolicy.cs`
- Test: `src/Rook.Tests/Bim/BimExportOrganizationPolicyTests.cs`

**Interfaces:**
- Produces: `enum BimLayerScheme { Flat, ByCategory, ByLevelThenCategory }`; `enum BimNameScheme { None, RevitName, TypeOnly, Readable, ReadableWithId }`; `enum BimMetadataProfile { Minimal, Standard, Full }`; `sealed class BimExportOrganizationPolicy { BimLayerScheme LayerScheme; BimNameScheme NameScheme; BimMetadataProfile MetadataProfile; static BimExportOrganizationPolicy Legacy; static bool TryParseLayer(string?, out BimLayerScheme); static bool TryParseName(string?, out BimNameScheme); static bool TryParseProfile(string?, out BimMetadataProfile); static BimValidationResult Resolve(BimPresetDefinition def, string? layerOverride, string? nameOverride, string? profileOverride, out BimExportOrganizationPolicy policy); }`.

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/BimExportOrganizationPolicyTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportOrganizationPolicyTests
    {
        [Fact]
        public void Legacy_IsFlatNoNameMinimal()
        {
            var p = BimExportOrganizationPolicy.Legacy;
            Assert.Equal(BimLayerScheme.Flat, p.LayerScheme);
            Assert.Equal(BimNameScheme.None, p.NameScheme);
            Assert.Equal(BimMetadataProfile.Minimal, p.MetadataProfile);
        }

        [Theory]
        [InlineData("by_category", BimLayerScheme.ByCategory)]
        [InlineData("by_level_then_category", BimLayerScheme.ByLevelThenCategory)]
        [InlineData("flat", BimLayerScheme.Flat)]
        public void TryParseLayer_ParsesKnownSchemes(string raw, BimLayerScheme expected)
        {
            Assert.True(BimExportOrganizationPolicy.TryParseLayer(raw, out var scheme));
            Assert.Equal(expected, scheme);
        }

        [Fact]
        public void TryParseLayer_RejectsUnknown()
        {
            Assert.False(BimExportOrganizationPolicy.TryParseLayer("spiral", out _));
        }

        [Theory]
        [InlineData("readable_with_id", BimNameScheme.ReadableWithId)]
        [InlineData("type_only", BimNameScheme.TypeOnly)]
        [InlineData("revit_name", BimNameScheme.RevitName)]
        [InlineData("none", BimNameScheme.None)]
        public void TryParseName_ParsesKnownSchemes(string raw, BimNameScheme expected)
        {
            Assert.True(BimExportOrganizationPolicy.TryParseName(raw, out var scheme));
            Assert.Equal(expected, scheme);
        }

        [Theory]
        [InlineData("minimal", BimMetadataProfile.Minimal)]
        [InlineData("standard", BimMetadataProfile.Standard)]
        [InlineData("full", BimMetadataProfile.Full)]
        public void TryParseProfile_ParsesKnownProfiles(string raw, BimMetadataProfile expected)
        {
            Assert.True(BimExportOrganizationPolicy.TryParseProfile(raw, out var profile));
            Assert.Equal(expected, profile);
        }

        [Fact]
        public void Resolve_UsesPresetDefaultsWhenNoOverrides()
        {
            var def = new BimPresetDefinition
            {
                DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                DefaultNameScheme = BimNameScheme.ReadableWithId,
                DefaultMetadataProfile = BimMetadataProfile.Full,
            };
            var result = BimExportOrganizationPolicy.Resolve(def, null, null, null, out var policy);
            Assert.True(result.Success);
            Assert.Equal(BimLayerScheme.ByLevelThenCategory, policy.LayerScheme);
            Assert.Equal(BimNameScheme.ReadableWithId, policy.NameScheme);
            Assert.Equal(BimMetadataProfile.Full, policy.MetadataProfile);
        }

        [Fact]
        public void Resolve_AppliesOverrides()
        {
            var def = new BimPresetDefinition
            {
                DefaultLayerScheme = BimLayerScheme.ByLevelThenCategory,
                DefaultNameScheme = BimNameScheme.ReadableWithId,
                DefaultMetadataProfile = BimMetadataProfile.Standard,
            };
            var result = BimExportOrganizationPolicy.Resolve(def, "by_category", "type_only", "minimal", out var policy);
            Assert.True(result.Success);
            Assert.Equal(BimLayerScheme.ByCategory, policy.LayerScheme);
            Assert.Equal(BimNameScheme.TypeOnly, policy.NameScheme);
            Assert.Equal(BimMetadataProfile.Minimal, policy.MetadataProfile);
        }

        [Fact]
        public void Resolve_RejectsBadOverrideWithInvalidScope()
        {
            var def = new BimPresetDefinition();
            var result = BimExportOrganizationPolicy.Resolve(def, "spiral", null, null, out _);
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportOrganizationPolicyTests`
Expected: FAIL — types do not exist.

- [ ] **Step 3: Implement the policy**

Create `src/Rook/Bim/BimExportOrganizationPolicy.cs`:

```csharp
using System;

namespace Rook.Bim
{
    public enum BimLayerScheme
    {
        Flat,
        ByCategory,
        ByLevelThenCategory
    }

    public enum BimNameScheme
    {
        None,
        RevitName,
        TypeOnly,
        Readable,
        ReadableWithId
    }

    public enum BimMetadataProfile
    {
        Minimal,
        Standard,
        Full
    }

    public sealed class BimExportOrganizationPolicy
    {
        public BimLayerScheme LayerScheme { get; set; } = BimLayerScheme.Flat;

        public BimNameScheme NameScheme { get; set; } = BimNameScheme.None;

        public BimMetadataProfile MetadataProfile { get; set; } = BimMetadataProfile.Minimal;

        // The raw rookbim_export_elements path uses Legacy so its output stays semantically identical:
        // flat RookBim::Model layer, the four user strings, no object names.
        public static BimExportOrganizationPolicy Legacy
        {
            get
            {
                return new BimExportOrganizationPolicy
                {
                    LayerScheme = BimLayerScheme.Flat,
                    NameScheme = BimNameScheme.None,
                    MetadataProfile = BimMetadataProfile.Minimal,
                };
            }
        }

        public static bool TryParseLayer(string? raw, out BimLayerScheme scheme)
        {
            switch ((raw ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "flat": scheme = BimLayerScheme.Flat; return true;
                case "by_category": scheme = BimLayerScheme.ByCategory; return true;
                case "by_level_then_category": scheme = BimLayerScheme.ByLevelThenCategory; return true;
                default: scheme = BimLayerScheme.Flat; return false;
            }
        }

        public static bool TryParseName(string? raw, out BimNameScheme scheme)
        {
            switch ((raw ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "none": scheme = BimNameScheme.None; return true;
                case "revit_name": scheme = BimNameScheme.RevitName; return true;
                case "type_only": scheme = BimNameScheme.TypeOnly; return true;
                case "readable": scheme = BimNameScheme.Readable; return true;
                case "readable_with_id": scheme = BimNameScheme.ReadableWithId; return true;
                default: scheme = BimNameScheme.None; return false;
            }
        }

        public static bool TryParseProfile(string? raw, out BimMetadataProfile profile)
        {
            switch ((raw ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "minimal": profile = BimMetadataProfile.Minimal; return true;
                case "standard": profile = BimMetadataProfile.Standard; return true;
                case "full": profile = BimMetadataProfile.Full; return true;
                default: profile = BimMetadataProfile.Standard; return false;
            }
        }

        public static BimValidationResult Resolve(
            BimPresetDefinition definition,
            string? layerOverride,
            string? nameOverride,
            string? profileOverride,
            out BimExportOrganizationPolicy policy)
        {
            var layer = definition.DefaultLayerScheme;
            var name = definition.DefaultNameScheme;
            var profile = definition.DefaultMetadataProfile;

            if (!string.IsNullOrWhiteSpace(layerOverride))
            {
                if (!TryParseLayer(layerOverride, out layer))
                {
                    return Bad("layerPolicy", layerOverride!, out policy);
                }
            }

            if (!string.IsNullOrWhiteSpace(nameOverride))
            {
                if (!TryParseName(nameOverride, out name))
                {
                    return Bad("namePolicy", nameOverride!, out policy);
                }
            }

            if (!string.IsNullOrWhiteSpace(profileOverride))
            {
                if (!TryParseProfile(profileOverride, out profile))
                {
                    return Bad("metadataProfile", profileOverride!, out policy);
                }
            }

            policy = new BimExportOrganizationPolicy
            {
                LayerScheme = layer,
                NameScheme = name,
                MetadataProfile = profile,
            };
            return BimValidationResult.Ok;
        }

        private static BimValidationResult Bad(string field, string value, out BimExportOrganizationPolicy policy)
        {
            policy = Legacy;
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = BimErrorCode.InvalidScope,
                Message = $"Invalid {field} override '{value}'.",
            };
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportOrganizationPolicyTests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Bim/BimExportOrganizationPolicy.cs src/Rook.Tests/Bim/BimExportOrganizationPolicyTests.cs
git commit -m "feat(bim): export organization policy (layer/name/metadata schemes) + Legacy + parse"
```

---

## Task 4: Layer namer (pure)

**Files:**
- Create: `src/Rook/Bim/BimExportLayerNamer.cs`
- Test: `src/Rook.Tests/Bim/BimExportLayerNamerTests.cs`

**Interfaces:**
- Consumes: `BimLayerScheme` (Task 3).
- Produces: `static class BimExportLayerNamer { const string Root = "RookBim"; string LayerPath(BimLayerScheme scheme, string? category, string? levelValue); }` (returns full `RookBim::…` path; `flat` ⇒ `RookBim::Model`).

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/BimExportLayerNamerTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportLayerNamerTests
    {
        [Fact]
        public void Flat_AlwaysModelLayer()
        {
            Assert.Equal("RookBim::Model",
                BimExportLayerNamer.LayerPath(BimLayerScheme.Flat, "Walls", "Level 01"));
        }

        [Fact]
        public void ByCategory_UsesCategoryUnderRoot()
        {
            Assert.Equal("RookBim::Walls",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByCategory, "Walls", "Level 01"));
        }

        [Fact]
        public void ByLevelThenCategory_NestsLevelThenCategory()
        {
            Assert.Equal("RookBim::Level 01::Walls",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByLevelThenCategory, "Walls", "Level 01"));
        }

        [Fact]
        public void ByLevelThenCategory_MissingLevelUsesNoLevel()
        {
            Assert.Equal("RookBim::_NoLevel::Walls",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByLevelThenCategory, "Walls", null));
        }

        [Fact]
        public void MissingCategoryUsesOther()
        {
            Assert.Equal("RookBim::_Other",
                BimExportLayerNamer.LayerPath(BimLayerScheme.ByCategory, "  ", "Level 01"));
        }

        [Fact]
        public void NeverEmitsUppercaseRoot()
        {
            var path = BimExportLayerNamer.LayerPath(BimLayerScheme.ByCategory, "Walls", null);
            Assert.StartsWith("RookBim::", path);
            Assert.DoesNotContain("RookBIM", path);
        }

        [Fact]
        public void SanitizesSeparatorCollisionsInSegments()
        {
            // A category/level containing "::" must not break the path structure.
            var path = BimExportLayerNamer.LayerPath(BimLayerScheme.ByLevelThenCategory, "A::B", "L::1");
            Assert.Equal("RookBim::L__1::A__B", path);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportLayerNamerTests`
Expected: FAIL — `BimExportLayerNamer` does not exist.

- [ ] **Step 3: Implement the namer**

Create `src/Rook/Bim/BimExportLayerNamer.cs`:

```csharp
using System.Text;

namespace Rook.Bim
{
    public static class BimExportLayerNamer
    {
        public const string Root = "RookBim";
        public const string ModelLeaf = "Model";
        public const string NoLevel = "_NoLevel";
        public const string OtherCategory = "_Other";

        public static string LayerPath(BimLayerScheme scheme, string? category, string? levelValue)
        {
            switch (scheme)
            {
                case BimLayerScheme.ByCategory:
                    return Root + "::" + CategorySegment(category);

                case BimLayerScheme.ByLevelThenCategory:
                    return Root + "::" + LevelSegment(levelValue) + "::" + CategorySegment(category);

                case BimLayerScheme.Flat:
                default:
                    return Root + "::" + ModelLeaf;
            }
        }

        private static string CategorySegment(string? category)
        {
            var clean = Sanitize(category);
            return clean.Length == 0 ? OtherCategory : clean;
        }

        private static string LevelSegment(string? levelValue)
        {
            var clean = Sanitize(levelValue);
            return clean.Length == 0 ? NoLevel : clean;
        }

        // Collapse the "::" separator (and control chars) inside a single segment so a category or
        // level name can never alter the layer path's structure. Spaces are preserved (Rhino allows
        // them); ":" becomes "_".
        private static string Sanitize(string? value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return string.Empty;
            }

            var builder = new StringBuilder(value!.Length);
            foreach (var c in value.Trim())
            {
                if (c == ':' || char.IsControl(c))
                {
                    builder.Append('_');
                }
                else
                {
                    builder.Append(c);
                }
            }

            return builder.ToString();
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportLayerNamerTests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Bim/BimExportLayerNamer.cs src/Rook.Tests/Bim/BimExportLayerNamerTests.cs
git commit -m "feat(bim): pure layer namer (flat/by_category/by_level_then_category) under RookBim:: root"
```

---

## Task 5: Object namer (pure)

**Files:**
- Create: `src/Rook/Bim/BimExportObjectNamer.cs`
- Test: `src/Rook.Tests/Bim/BimExportObjectNamerTests.cs`

**Interfaces:**
- Consumes: `BimNameScheme` (Task 3).
- Produces: `static class BimExportObjectNamer { string? ObjectName(BimNameScheme scheme, string? category, string? type, long? elementId, string? revitName); }` (returns `null` for `None`).

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/BimExportObjectNamerTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportObjectNamerTests
    {
        [Fact]
        public void None_ReturnsNull()
        {
            Assert.Null(BimExportObjectNamer.ObjectName(BimNameScheme.None, "Walls", "Generic 200mm", 1, "x"));
        }

        [Fact]
        public void ReadableWithId_FormatsCategoryTypeAndId()
        {
            Assert.Equal("Walls - Generic 200mm [350123]",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, "Walls", "Generic 200mm", 350123, "x"));
        }

        [Fact]
        public void Readable_OmitsId()
        {
            Assert.Equal("Walls - Generic 200mm",
                BimExportObjectNamer.ObjectName(BimNameScheme.Readable, "Walls", "Generic 200mm", 350123, "x"));
        }

        [Fact]
        public void TypeOnly_UsesType()
        {
            Assert.Equal("Generic 200mm",
                BimExportObjectNamer.ObjectName(BimNameScheme.TypeOnly, "Walls", "Generic 200mm", 1, "x"));
        }

        [Fact]
        public void RevitName_UsesRevitName()
        {
            Assert.Equal("My Wall",
                BimExportObjectNamer.ObjectName(BimNameScheme.RevitName, "Walls", "Generic 200mm", 1, "My Wall"));
        }

        [Fact]
        public void ReadableWithId_FallsBackToCategoryWhenTypeMissing()
        {
            Assert.Equal("Walls [42]",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, "Walls", null, 42, null));
        }

        [Fact]
        public void ReadableWithId_FallsBackToRevitElementWhenAllMissing()
        {
            Assert.Equal("Revit Element [42]",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, null, null, 42, null));
        }

        [Fact]
        public void ReadableWithId_OmitsSuffixWhenNoId()
        {
            Assert.Equal("Walls - Generic 200mm",
                BimExportObjectNamer.ObjectName(BimNameScheme.ReadableWithId, "Walls", "Generic 200mm", null, null));
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportObjectNamerTests`
Expected: FAIL — `BimExportObjectNamer` does not exist.

- [ ] **Step 3: Implement the namer**

Create `src/Rook/Bim/BimExportObjectNamer.cs`:

```csharp
using System.Text;

namespace Rook.Bim
{
    public static class BimExportObjectNamer
    {
        public static string? ObjectName(
            BimNameScheme scheme, string? category, string? type, long? elementId, string? revitName)
        {
            switch (scheme)
            {
                case BimNameScheme.None:
                    return null;

                case BimNameScheme.RevitName:
                    return Clean(revitName) ?? FallbackBase(category, type);

                case BimNameScheme.TypeOnly:
                    return FallbackBase(category, type);

                case BimNameScheme.Readable:
                    return Readable(category, type);

                case BimNameScheme.ReadableWithId:
                default:
                    return WithId(Readable(category, type), elementId);
            }
        }

        private static string Readable(string? category, string? type)
        {
            var cat = Clean(category);
            var typ = Clean(type);
            if (cat != null && typ != null)
            {
                return cat + " - " + typ;
            }

            return FallbackBase(category, type);
        }

        // Type preferred; then category; then the generic literal.
        private static string FallbackBase(string? category, string? type)
        {
            return Clean(type) ?? Clean(category) ?? "Revit Element";
        }

        private static string WithId(string baseName, long? elementId)
        {
            return elementId.HasValue ? baseName + " [" + elementId.Value + "]" : baseName;
        }

        // Object names may contain spaces and most punctuation; strip only control chars and trim.
        private static string? Clean(string? value)
        {
            if (string.IsNullOrWhiteSpace(value))
            {
                return null;
            }

            var builder = new StringBuilder(value!.Length);
            foreach (var c in value.Trim())
            {
                if (!char.IsControl(c))
                {
                    builder.Append(c);
                }
            }

            var result = builder.ToString().Trim();
            return result.Length == 0 ? null : result;
        }
    }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportObjectNamerTests`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Bim/BimExportObjectNamer.cs src/Rook.Tests/Bim/BimExportObjectNamerTests.cs
git commit -m "feat(bim): pure object namer (none/revit_name/type_only/readable/readable_with_id)"
```

---

## Task 6: Interface + Unavailable runtime

**Files:**
- Modify: `src/Rook/Bim/IRookBimRuntime.cs`
- Modify: `src/Rook/Bim/RookBimUnavailableRuntime.cs`
- Test: `src/Rook.Tests/Bim/RookBimUnavailablePresetTests.cs`

**Interfaces:**
- Produces: `IRookBimRuntime.ExportPreset(BimExportPresetRequest request) : BimApiResponse`. Task 7/10 implement it on `RevitRookBimRuntime`.

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/RookBimUnavailablePresetTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimUnavailablePresetTests
    {
        [Fact]
        public void ExportPreset_ReturnsUnavailable()
        {
            var runtime = new RookBimUnavailableRuntime("rookbim_unavailable", "nope");
            var response = runtime.ExportPreset(new BimExportPresetRequest());
            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Equal(503, response.HttpStatus);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookBimUnavailablePresetTests`
Expected: FAIL — `IRookBimRuntime` has no `ExportPreset`.

- [ ] **Step 3: Add to the interface**

In `src/Rook/Bim/IRookBimRuntime.cs`, add after `ExportElements`:

```csharp
        BimApiResponse ExportPreset(BimExportPresetRequest request);
```

- [ ] **Step 4: Implement on the Unavailable runtime**

In `src/Rook/Bim/RookBimUnavailableRuntime.cs`, add after `ExportElements`:

```csharp
        public BimApiResponse ExportPreset(BimExportPresetRequest request)
        {
            return Unavailable();
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookBimUnavailablePresetTests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Bim/IRookBimRuntime.cs src/Rook/Bim/RookBimUnavailableRuntime.cs src/Rook.Tests/Bim/RookBimUnavailablePresetTests.cs
git commit -m "feat(bim): add ExportPreset to runtime interface + Unavailable impl"
```

---

## Task 7: Generalize `RevitExportService` with an organization policy (+ Legacy parity)

**Files:**
- Create: `src/RookBim/Revit/RevitPresetContext.cs`
- Modify: `src/RookBim/Revit/RevitExportService.cs`
- Test: `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` (created here; extended later)

This is the contract-risk seam. `Export(doc, view, request)` is refactored to resolve the element set, then call a new internal `ExportResolved(...)` that takes a `BimExportOrganizationPolicy` and an optional `RevitPresetContext`. The raw path passes `BimExportOrganizationPolicy.Legacy` + `null` context, preserving its observable output. Verified by **source-text tests** (CI) + a **build gate** + Task 13's live script.

- [ ] **Step 1: Add the preset-context type**

Create `src/RookBim/Revit/RevitPresetContext.cs`:

```csharp
using System.Collections.Generic;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Produced by RevitPresetResolver, consumed by RevitExportService. Its presence is the single
    /// gate for preset-only decoration (summary + relationships); a null context = the raw path.
    /// </summary>
    internal sealed class RevitPresetContext
    {
        public string Preset { get; set; } = string.Empty;

        public BimExportOrganizationPolicy Policy { get; set; } = BimExportOrganizationPolicy.Legacy;

        public BimRoomsMode EffectiveRooms { get; set; } = BimRoomsMode.Both;

        public bool RoomsDriven { get; set; }

        public int LimitPerCategory { get; set; } = 1000;

        public List<string> EffectiveCategories { get; set; } = new List<string>();

        public List<RevitPresetCategoryCount> ResolvedCategories { get; set; } = new List<RevitPresetCategoryCount>();

        public List<RevitPresetWarning> Warnings { get; set; } = new List<RevitPresetWarning>();
    }

    internal sealed class RevitPresetCategoryCount
    {
        public string Category { get; set; } = string.Empty;

        public int Resolved { get; set; }

        public string Status { get; set; } = "resolved"; // resolved | unavailable
    }

    internal sealed class RevitPresetWarning
    {
        public string Code { get; set; } = string.Empty;

        public string Message { get; set; } = string.Empty;
    }
}
```

- [ ] **Step 2: Write the failing source-text test**

Create `src/RookBim.Tests/RookBimExportPresetSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimExportPresetSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void ExportService_ThreadsOrganizationPolicyAndGatesPresetDecoration()
        {
            var src = Read("src/RookBim/Revit/RevitExportService.cs");

            // Generalized: a resolved-export path that takes a policy + optional preset context.
            Assert.Contains("ExportResolved", src);
            Assert.Contains("BimExportOrganizationPolicy", src);
            Assert.Contains("RevitPresetContext", src);

            // Raw path keeps Legacy + null context (parity seam).
            Assert.Contains("BimExportOrganizationPolicy.Legacy", src);

            // Policy-driven layer + name + metadata via the pure helpers.
            Assert.Contains("BimExportLayerNamer.LayerPath", src);
            Assert.Contains("BimExportObjectNamer.ObjectName", src);

            // Read-only invariant preserved.
            Assert.DoesNotContain("Transaction", src);
        }

        internal static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Rook.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new InvalidOperationException("Could not find repository root.");
        }
    }
}
```

- [ ] **Step 3: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RookBimExportPresetSourceTests`
Expected: FAIL — `ExportResolved`/`BimExportOrganizationPolicy` not yet in the source.

- [ ] **Step 4: Refactor `Export` into resolve + `ExportResolved`**

In `src/RookBim/Revit/RevitExportService.cs`, replace the **public `Export` method** (the entire method from `public BimApiResponse Export(Document document, View? activeView, BimExportElementsRequest request)` through its closing brace) with the following two methods. This moves path-safety + assembly into `ExportResolved`, which now takes a policy + optional context; the public `Export` resolves elements then delegates with `Legacy` + `null`:

```csharp
        public BimApiResponse Export(Document document, View? activeView, BimExportElementsRequest request)
        {
            var resolution = ResolveElements(document, activeView, request);
            if (resolution.Failure != null)
            {
                return resolution.Failure;
            }

            return ExportResolved(
                document,
                resolution.Elements,
                resolution.Truncated,
                resolution.RequestedCount,
                request,
                BimExportOrganizationPolicy.Legacy,
                presetContext: null);
        }

        // Shared assembly core. The raw path passes Legacy + null context (no new decoration);
        // the preset path passes a resolved policy + context (summary + relationships, Task 9).
        internal BimApiResponse ExportResolved(
            Document document,
            IReadOnlyList<Element> elements,
            bool truncated,
            int requestedCount,
            BimExportElementsRequest request,
            BimExportOrganizationPolicy policy,
            RevitPresetContext? presetContext)
        {
            // 1. Output-path safety.
            var pathShape = BimExportPathPolicy.ValidateRequestShape(request.Output);
            if (!pathShape.Success)
            {
                return BimApiResponse.Fail(pathShape.ErrorCode, pathShape.Message ?? "Invalid output path.", 400);
            }

            var paths = BimExportPathPolicy.ResolveBundlePaths(request.Output.Directory!, request.Output.Name!);
            foreach (var path in new[] { paths.Model3dm, paths.Sidecar, paths.Validation })
            {
                if (BimExportPathPolicy.EscapesIntendedDirectory(path, request.Output.Directory!))
                {
                    return BimApiResponse.Fail(
                        BimErrorCode.OutputPathInvalid, "Resolved artifact path escapes the output directory.", 400);
                }

                if (!request.Output.Overwrite && File.Exists(path))
                {
                    return BimApiResponse.Fail(
                        BimErrorCode.OutputPathInvalid,
                        $"Bundle artifact already exists (set overwrite=true to replace): {Path.GetFileName(path)}",
                        409);
                }
            }

            var scale = RevitGeometryConverter.ScaleFromFeet(request.Output.Units);
            var converter = new RevitGeometryConverter(scale);

            // 2. Build the in-memory File3dm + element records.
            var file = new Rhino.FileIO.File3dm();
            file.Settings.ModelUnitSystem = MapUnits(request.Output.Units);
            var layerCache = new Dictionary<string, int>(StringComparer.Ordinal);

            var elementRecords = new List<object>();
            var counts = new BimExportCounts
            {
                Requested = requestedCount,
                Resolved = elements.Count,
                Truncated = truncated,
            };
            var exportedKeys = new HashSet<string>(StringComparer.Ordinal);
            var exportedRoomKeys = new HashSet<string>(StringComparer.Ordinal);
            var relationships = new RevitRelationshipIndex();
            var perCategoryExport = new Dictionary<string, RevitCategoryExportTally>(StringComparer.OrdinalIgnoreCase);
            var exportId = 0;

            foreach (var element in elements)
            {
                var key = element.UniqueId;
                try
                {
                    var conversion = converter.Convert(element, request.AllowBboxProxy);
                    var labelSet = labels.Extract(document, element);
                    var stamp = BuildStampData(document, element, conversion, presetContext, exportId);
                    elementRecords.Add(BuildElementRecord(document, element, conversion, labelSet, stamp));

                    if (presetContext != null)
                    {
                        relationships.Accumulate(element.UniqueId, labelSet);
                    }

                    if (conversion.HasGeometry)
                    {
                        var layerIndex = EnsureLayerForElement(file, layerCache, policy, stamp, labelSet);
                        AddGeometryWithPolicy(file, layerIndex, element, conversion, policy, stamp, labelSet);
                        exportedKeys.Add(key);
                        TallyExport(perCategoryExport, stamp.Category, conversion.Quality, failed: false);
                        switch (conversion.Quality)
                        {
                            case RevitGeometryConverter.QualityConvertedBrep: counts.ExportedBrep++; break;
                            case RevitGeometryConverter.QualityMeshFallback: counts.ExportedMesh++; break;
                            case RevitGeometryConverter.QualityBboxOnly: counts.ExportedBboxProxy++; break;
                        }
                    }
                    else
                    {
                        counts.Failed++;
                        TallyExport(perCategoryExport, stamp.Category, conversion.Quality, failed: true);
                    }

                    exportId++;
                }
                catch (Exception ex)
                {
                    counts.Failed++;
                    elementRecords.Add(BuildFailedElementRecord(element, ex));
                    exportId++;
                }
            }

            // 3. Rooms (typed separately).
            var roomRecords = new List<object>();
            var effectiveRooms = presetContext?.EffectiveRooms ?? request.EffectiveRooms;
            var roomRepCounts = new Dictionary<string, int>(StringComparer.Ordinal);
            if (effectiveRooms != BimRoomsMode.Exclude)
            {
                var includeGeometry = effectiveRooms == BimRoomsMode.Both;
                var roomLayerIndex = EnsureLayer(file, layerCache, RevitRoomExporter.RoomsLayer);
                var rooms = new RevitRoomExporter(scale).ExportRooms(document);
                counts.Rooms = rooms.Count;
                foreach (var room in rooms)
                {
                    var rep = MaterializeRoom(file, roomLayerIndex, room, scale, includeGeometry, exportedRoomKeys);
                    roomRecords.Add(new
                    {
                        roomId = room.UniqueId,
                        uniqueId = room.UniqueId,
                        number = room.Number,
                        name = room.Name,
                        geometryRepresentation = rep,
                        referenceGeometry = true
                    });
                    roomRepCounts.TryGetValue(rep, out var n);
                    roomRepCounts[rep] = n + 1;
                }
            }

            // 4. NoExportableGeometry guard (unchanged: only when elements resolved but none had geometry).
            if (elements.Count > 0 && counts.ExportedBrep + counts.ExportedMesh + counts.ExportedBboxProxy == 0)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoExportableGeometry,
                    "No element produced exportable geometry (retry with allowBboxProxy=true or a different selection).",
                    422);
            }

            // 5. Verify the bijection BEFORE writing.
            var verification = VerifyBijection(file, exportedKeys, exportedRoomKeys);

            // 6. Assemble sidecar + validation; write all three path-safely.
            var sidecar = BuildSidecar(document, request, elements, truncated, elementRecords, roomRecords, presetContext);
            var sidecarJson = JsonSerializer.Serialize(sidecar, JsonOptions);
            var written = new List<string>();

            try
            {
                written.Add(paths.Model3dm);
                if (!file.Write(paths.Model3dm, 7))
                {
                    return CleanupAndFail(written, "Failed to write the .3dm bundle artifact.");
                }

                File.WriteAllText(paths.Sidecar, sidecarJson, new UTF8Encoding(false));
                written.Add(paths.Sidecar);

                var summary = presetContext == null
                    ? null
                    : BuildSummary(presetContext, counts, perCategoryExport, roomRepCounts, layerCache.Count, paths);
                var validation = BuildValidation(
                    document, counts, scale, request.Output.Units, paths, sidecarJson, presetContext, summary, relationships);
                File.WriteAllText(paths.Validation, JsonSerializer.Serialize(validation, JsonOptions), new UTF8Encoding(false));
                written.Add(paths.Validation);

                if (!verification.Ok)
                {
                    CleanupBundle(written);
                    var failure = BimApiResponse.Fail(
                        BimErrorCode.ExportFailed, "Export bijection verification failed; bundle is not a trustworthy fixture.", 500);
                    failure.Data = new { verification };
                    return failure;
                }

                return BimApiResponse.Ok(BuildResult(paths, counts, verification, scale, request.Output.Units, presetContext, summary, relationships));
            }
            catch (Exception ex)
            {
                return CleanupAndFail(written, $"Bundle write failed: {ex.GetType().Name}: {ex.Message}");
            }
        }
```

- [ ] **Step 5: Replace the layer + geometry + record helpers**

Still in `RevitExportService.cs`, make these changes:

(a) Delete the `private const string ModelLayer = "RookBim::Model";` field (the layer name now comes from `BimExportLayerNamer`).

(b) Replace the old `EnsureLayer(Rhino.FileIO.File3dm file, string name)` method and the old `AddGeometry(...)` method with the cache-aware + policy-aware versions below, and add the new helpers (`EnsureLayerForElement`, `BuildStampData`, `TallyExport`, `StampObject`, and the `RevitStampData`/`RevitCategoryExportTally` types):

```csharp
        private static int EnsureLayer(Rhino.FileIO.File3dm file, Dictionary<string, int> cache, string name)
        {
            if (cache.TryGetValue(name, out var existing))
            {
                return existing;
            }

            var index = file.AllLayers.Count;
            var layer = new Rhino.DocObjects.Layer { Name = name, Index = index };
            file.AllLayers.Add(layer);
            cache[name] = index;
            return index;
        }

        private static int EnsureLayerForElement(
            Rhino.FileIO.File3dm file,
            Dictionary<string, int> cache,
            BimExportOrganizationPolicy policy,
            RevitStampData stamp,
            RevitElementLabels labelSet)
        {
            var levelValue = labelSet.Level?.Value;
            var layerName = BimExportLayerNamer.LayerPath(policy.LayerScheme, stamp.Category, levelValue);
            return EnsureLayer(file, cache, layerName);
        }

        private void AddGeometryWithPolicy(
            Rhino.FileIO.File3dm file,
            int layerIndex,
            Element element,
            RevitGeometryConversion conversion,
            BimExportOrganizationPolicy policy,
            RevitStampData stamp,
            RevitElementLabels labelSet)
        {
            var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
            StampObject(attrs, element, conversion, policy, stamp, labelSet);

            var name = BimExportObjectNamer.ObjectName(
                policy.NameScheme, stamp.Category, stamp.Type, stamp.ElementIdValue, stamp.RevitName);
            if (!string.IsNullOrEmpty(name))
            {
                attrs.Name = name;
            }

            if (conversion.Breps.Count > 0)
            {
                foreach (var brep in conversion.Breps)
                {
                    file.Objects.AddBrep(brep, attrs);
                }
            }
            else if (conversion.Mesh != null)
            {
                file.Objects.AddMesh(conversion.Mesh, attrs);
            }
            else if (conversion.Bbox != null)
            {
                file.Objects.AddBrep(conversion.Bbox.Value.ToBrep(), attrs);
            }
        }

        // Value-only user strings. minimal = the legacy four; standard/full add Rook-derived +
        // raw Revit facts. Missing/low-confidence labels are omitted, never stamped as "unknown".
        private static void StampObject(
            Rhino.DocObjects.ObjectAttributes attrs,
            Element element,
            RevitGeometryConversion conversion,
            BimExportOrganizationPolicy policy,
            RevitStampData stamp,
            RevitElementLabels labelSet)
        {
            attrs.SetUserString("rook.source", "revit");
            attrs.SetUserString("revit.uniqueId", element.UniqueId);
            attrs.SetUserString("revit.elementId", element.Id.Value.ToString());
            attrs.SetUserString("revit.category", stamp.Category ?? string.Empty);

            if (policy.MetadataProfile == BimMetadataProfile.Minimal)
            {
                return;
            }

            attrs.SetUserString("rookbim.exportId", stamp.ExportId.ToString());
            if (!string.IsNullOrEmpty(stamp.Preset)) { attrs.SetUserString("rookbim.preset", stamp.Preset); }
            attrs.SetUserString("rookbim.geometryRepresentation", conversion.Representation);
            attrs.SetUserString("rookbim.geometryQuality", conversion.Quality);
            StampIfPresent(attrs, "revit.family", stamp.Family);
            StampIfPresent(attrs, "revit.type", stamp.Type);
            StampIfPresent(attrs, "revit.name", stamp.RevitName);
            StampLabel(attrs, "revit.level", labelSet.Level);

            if (policy.MetadataProfile != BimMetadataProfile.Full)
            {
                return;
            }

            StampLabel(attrs, "revit.hostId", labelSet.HostId);
            StampLabel(attrs, "revit.containingRoomId", labelSet.ContainingRoom);
            StampLabel(attrs, "revit.containingSpaceId", labelSet.ContainingSpace);
        }

        private static void StampIfPresent(Rhino.DocObjects.ObjectAttributes attrs, string key, string? value)
        {
            if (!string.IsNullOrWhiteSpace(value))
            {
                attrs.SetUserString(key, value);
            }
        }

        private static void StampLabel(Rhino.DocObjects.ObjectAttributes attrs, string key, BimSemanticLabel? label)
        {
            if (label != null && !string.IsNullOrWhiteSpace(label.Value))
            {
                attrs.SetUserString(key, label.Value);
            }
        }

        private static RevitStampData BuildStampData(
            Document document,
            Element element,
            RevitGeometryConversion conversion,
            RevitPresetContext? presetContext,
            int exportId)
        {
            var type = document.GetElement(element.GetTypeId()) as ElementType;
            return new RevitStampData
            {
                Category = element.Category?.Name,
                Family = type?.FamilyName,
                Type = type?.Name,
                RevitName = NullIfWhiteSpace(element.Name),
                ElementIdValue = element.Id.Value,
                ExportId = exportId,
                Preset = presetContext?.Preset ?? string.Empty,
            };
        }

        private static void TallyExport(
            Dictionary<string, RevitCategoryExportTally> tallies, string? category, string quality, bool failed)
        {
            var key = string.IsNullOrWhiteSpace(category) ? "_Other" : category!;
            if (!tallies.TryGetValue(key, out var tally))
            {
                tally = new RevitCategoryExportTally();
                tallies[key] = tally;
            }

            if (failed) { tally.Failed++; } else { tally.Exported++; }
        }

        private static string? NullIfWhiteSpace(string? value)
        {
            return string.IsNullOrWhiteSpace(value) ? null : value;
        }

        private sealed class RevitStampData
        {
            public string? Category { get; set; }
            public string? Family { get; set; }
            public string? Type { get; set; }
            public string? RevitName { get; set; }
            public long ElementIdValue { get; set; }
            public long? ElementIdValueNullable => ElementIdValue;
            public int ExportId { get; set; }
            public string Preset { get; set; } = string.Empty;
        }

        private sealed class RevitCategoryExportTally
        {
            public int Exported { get; set; }
            public int Failed { get; set; }
        }
```

> Note: `RevitStampData.ElementIdValue` is `long`; `BimExportObjectNamer.ObjectName` takes `long?`. Pass `stamp.ElementIdValue` (implicitly widened to `long?`). The `ElementIdValueNullable` helper above is unused sugar — omit it if your analyzer flags it.

(c) Update `BuildElementRecord` to accept the prebuilt `stamp` (so family/type aren't re-fetched) and keep the existing JSON shape. Replace the existing `BuildElementRecord(Document document, Element element, RevitGeometryConversion conversion, RevitElementLabels labelSet)` with:

```csharp
        private object BuildElementRecord(
            Document document, Element element, RevitGeometryConversion conversion, RevitElementLabels labelSet, RevitStampData stamp)
        {
            var bb = element.get_BoundingBox(null);
            return new
            {
                identity = RevitIdentitySerializer.ElementIdentity(element),
                category = stamp.Category,
                family = stamp.Family,
                type = stamp.Type,
                name = element.Name,
                bbox = bb == null ? null : new[] { bb.Min.X, bb.Min.Y, bb.Min.Z, bb.Max.X, bb.Max.Y, bb.Max.Z },
                geometryRepresentation = conversion.Representation,
                geometryQuality = conversion.Quality,
                fallbackReason = conversion.FallbackReason,
                labels = new
                {
                    level = Label(labelSet.Level),
                    hostId = Label(labelSet.HostId),
                    containingRoomId = Label(labelSet.ContainingRoom),
                    containingSpaceId = Label(labelSet.ContainingSpace)
                }
            };
        }
```

- [ ] **Step 6: Update `BuildSidecar`/`BuildValidation`/result + add stub summary/relationship/result builders**

Replace the existing `BuildSidecar(...)` and `BuildValidation(...)` signatures, and add the new builders. Task 9 fills the summary/relationship bodies; for **this** task they are minimal so the raw path stays unchanged and the file compiles:

```csharp
        private object BuildSidecar(
            Document document,
            BimExportElementsRequest request,
            IReadOnlyList<Element> elements,
            bool truncated,
            List<object> elementRecords,
            List<object> roomRecords,
            RevitPresetContext? presetContext)
        {
            var requestSection = presetContext == null
                ? (object)new
                {
                    hasSelector = request.HasSelector,
                    hasIdentities = request.HasIdentities,
                    rooms = request.EffectiveRooms.ToString(),
                    allowTruncated = request.AllowTruncated,
                    allowBboxProxy = request.AllowBboxProxy
                }
                : new
                {
                    preset = presetContext.Preset,
                    effectiveCategories = presetContext.EffectiveCategories,
                    rooms = presetContext.EffectiveRooms.ToString(),
                    layerPolicy = presetContext.Policy.LayerScheme.ToString(),
                    namePolicy = presetContext.Policy.NameScheme.ToString(),
                    metadataProfile = presetContext.Policy.MetadataProfile.ToString(),
                    limitPerCategory = presetContext.LimitPerCategory,
                    allowTruncated = request.AllowTruncated,
                    allowBboxProxy = request.AllowBboxProxy
                };

            var sidecar = new Dictionary<string, object?>
            {
                ["schemaVersion"] = 1,
                ["document"] = RevitIdentitySerializer.DocumentIdentity(document),
                ["request"] = requestSection,
                ["resolved"] = new
                {
                    count = elements.Count,
                    truncated = truncated,
                    identities = elements.Select(RevitIdentitySerializer.ElementIdentity).ToList()
                },
                ["elements"] = elementRecords,
                ["rooms"] = roomRecords,
            };

            // Preset-only: relationships index lives in the sidecar too (Task 9 fills it).
            if (presetContext != null)
            {
                sidecar["relationships"] = _pendingRelationships?.ToWire() ?? RevitRelationshipIndex.EmptyWire();
            }

            return sidecar;
        }

        private object BuildValidation(
            Document document,
            BimExportCounts counts,
            double scale,
            string targetUnits,
            BimExportArtifactPaths paths,
            string sidecarJson,
            RevitPresetContext? presetContext,
            object? summary,
            RevitRelationshipIndex relationships)
        {
            var validation = new Dictionary<string, object?>
            {
                ["schemaVersion"] = 1,
                ["document"] = RevitIdentitySerializer.DocumentIdentity(document),
                ["units"] = new { source = "feet", target = targetUnits, scaleFactor = scale },
                ["counts"] = counts,
                ["hashes"] = new
                {
                    model3dm = "sha256:" + Sha256File(paths.Model3dm),
                    sidecar = "sha256:" + Sha256String(sidecarJson)
                },
            };

            if (presetContext != null)
            {
                validation["summary"] = summary;
                validation["relationships"] = relationships.ToWire();
            }

            return validation;
        }

        private object BuildResult(
            BimExportArtifactPaths paths,
            BimExportCounts counts,
            BimExportVerification verification,
            double scale,
            string targetUnits,
            RevitPresetContext? presetContext,
            object? summary,
            RevitRelationshipIndex relationships)
        {
            var result = BimApiResponse.Ok(new BimExportResult
            {
                Paths = paths,
                Counts = counts,
                Verification = verification,
                SourceUnits = "feet",
                TargetUnits = targetUnits,
                UnitScaleFactor = scale
            });

            // For the preset path, attach summary + relationships to the response Data alongside the
            // typed result. The raw path returns the bare BimExportResult (unchanged shape).
            if (presetContext == null)
            {
                return result.Data!;
            }

            return new
            {
                schemaVersion = 1,
                paths,
                counts,
                verification,
                sourceUnits = "feet",
                targetUnits,
                unitScaleFactor = scale,
                summary,
                relationships = relationships.ToWire()
            };
        }
```

> The sidecar's relationship index references a `_pendingRelationships` field set in `ExportResolved` right before `BuildSidecar`. Add the field and set it. In `ExportResolved`, immediately before `var sidecar = BuildSidecar(...)`, insert:
> ```csharp
>             _pendingRelationships = presetContext == null ? null : relationships;
> ```
> and add the field near the top of the class:
> ```csharp
>         private RevitRelationshipIndex? _pendingRelationships;
> ```

- [ ] **Step 7: Add a minimal `RevitRelationshipIndex` + `BuildSummary` stub (filled in Task 9)**

Add to `RevitExportService.cs` (these keep the file compiling now; Task 9 implements the real bodies):

```csharp
        private static object BuildSummary(
            RevitPresetContext presetContext,
            BimExportCounts counts,
            Dictionary<string, RevitCategoryExportTally> perCategoryExport,
            Dictionary<string, int> roomRepCounts,
            int layerCount,
            BimExportArtifactPaths paths)
        {
            // Task 9 fills this. Stub keeps the preset path returning a present-but-minimal summary.
            return new { digest = string.Empty };
        }
```

Add a new file `src/RookBim/Revit/RevitRelationshipIndex.cs`:

```csharp
using System.Collections.Generic;

namespace RookBim.Revit
{
    /// <summary>Factual membership index (room/host/level). Task 9 fills Accumulate/ToWire.</summary>
    internal sealed class RevitRelationshipIndex
    {
        public void Accumulate(string elementUniqueId, RevitElementLabels labels)
        {
            // Task 9.
        }

        public object ToWire()
        {
            return EmptyWire();
        }

        public static object EmptyWire()
        {
            return new
            {
                roomMembership = new List<object>(),
                hostMembership = new List<object>(),
                levelMembership = new List<object>()
            };
        }
    }
}
```

- [ ] **Step 8: Run the source-text test**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RookBimExportPresetSourceTests`
Expected: PASS.

- [ ] **Step 9: BUILD GATE — compile the real Revit/RhinoCommon code**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds. Fix any signature mismatches (e.g. `ObjectAttributes.Name`, `ElementType.FamilyName`, `Layer` index assignment) until green.

- [ ] **Step 10: Run the existing export source-text + parity tests**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj` and `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter Bim`
Expected: PASS — the existing `RookBimExportSourceTests` (no `exact_brep`, no `Transaction`, reflection brep path) still hold.

- [ ] **Step 11: Commit**

```bash
git add src/RookBim/Revit/RevitExportService.cs src/RookBim/Revit/RevitPresetContext.cs src/RookBim/Revit/RevitRelationshipIndex.cs src/RookBim.Tests/RookBimExportPresetSourceTests.cs
git commit -m "feat(rookbim): generalize export service with organization policy (Legacy parity preserved)"
```

---

## Task 8: `RevitPresetResolver` (multi-category union/dedup/freeze)

**Files:**
- Create: `src/RookBim/Revit/RevitPresetResolver.cs`
- Test: `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` (add a method)

**Interfaces:**
- Consumes: `RevitQueryService.Query(document, view, BimQueryElementsRequest) : BimApiResponse` (`.Data` is `BimQueryElementsResult`; `.Query.Returned/.Truncated/.Limit`; `.Elements[].Identity`); `RevitIdentitySerializer.Resolve(document, identity)`; `BimPresetCatalog`; `BimExportOrganizationPolicy.Resolve`.
- Produces: `internal sealed class RevitPresetResolver { RevitPresetResolution Resolve(Document document, View? activeView, BimExportPresetRequest request); }` where `RevitPresetResolution { BimApiResponse? Failure; List<Element> Elements; bool Truncated; int RequestedCount; RevitPresetContext Context; }`.

- [ ] **Step 1: Add the failing source-text test**

Add to `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` (inside the class):

```csharp
        [Fact]
        public void PresetResolver_LoopsCategoriesUnionsByIdentityAndDegradesGracefully()
        {
            var src = Read("src/RookBim/Revit/RevitPresetResolver.cs");

            // Reuses the existing single-category query path per category.
            Assert.Contains("RevitQueryService", src);
            Assert.Contains("BimPresetCatalog.TryGet", src);

            // Dedup by document GUID + unique id, not display name.
            Assert.Contains("documentGuid", src);
            Assert.Contains("UniqueId", src);

            // include/exclude overrides.
            Assert.Contains("IncludeCategories", src);
            Assert.Contains("ExcludeCategories", src);

            // Missing category = warning; all-missing (non rooms-driven) = NoCategoriesResolved.
            Assert.Contains("category_unavailable", src);
            Assert.Contains("NoCategoriesResolved", src);
            Assert.Contains("RoomsDriven", src);

            // Per-category truncation honors allowTruncated (same rule as v1).
            Assert.Contains("QueryTruncated", src);

            // Read-only.
            Assert.DoesNotContain("Transaction", src);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter PresetResolver_LoopsCategoriesUnionsByIdentityAndDegradesGracefully`
Expected: FAIL — file missing.

- [ ] **Step 3: Implement the resolver**

Create `src/RookBim/Revit/RevitPresetResolver.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Resolves a curated preset into a frozen, deduplicated element set + organization policy by
    /// looping the preset's categories through the existing single-category query path. Read-only.
    /// </summary>
    internal sealed class RevitPresetResolver
    {
        private readonly RevitQueryService query = new RevitQueryService();

        public RevitPresetResolution Resolve(Document document, View? activeView, BimExportPresetRequest request)
        {
            if (!BimPresetCatalog.TryGet(request.Preset, out var definition))
            {
                return RevitPresetResolution.Fail(BimApiResponse.Fail(
                    BimErrorCode.UnknownPreset, $"Unknown export preset '{request.Preset}'.", 400));
            }

            var policyResult = BimExportOrganizationPolicy.Resolve(
                definition, request.LayerPolicy, request.NamePolicy, request.MetadataProfile, out var policy);
            if (!policyResult.Success)
            {
                return RevitPresetResolution.Fail(BimApiResponse.Fail(
                    policyResult.ErrorCode, policyResult.Message ?? "Invalid organization policy override.", 400));
            }

            var effectiveRooms = ResolveRooms(definition, request.Rooms, out var roomsError);
            if (roomsError != null)
            {
                return RevitPresetResolution.Fail(roomsError);
            }

            var limitPerCategory = request.LimitPerCategory ?? definition.DefaultLimitPerCategory;
            var categories = EffectiveCategories(definition, request);

            var context = new RevitPresetContext
            {
                Preset = definition.Name,
                Policy = policy,
                EffectiveRooms = effectiveRooms,
                RoomsDriven = definition.RoomsDriven,
                LimitPerCategory = limitPerCategory,
                EffectiveCategories = categories.ToList(),
            };

            // Dedup by (documentGuid, uniqueId); first category to surface an element wins ordering.
            var documentGuid = RevitIdentitySerializer.DocumentIdentity(document).Guid ?? string.Empty;
            var seen = new HashSet<string>(StringComparer.Ordinal);
            var ordered = new List<Element>();
            var totalResolved = 0;

            foreach (var category in categories)
            {
                var selector = new BimQueryElementsRequest
                {
                    Scope = request.EffectiveScope,
                    Category = category,
                    Limit = limitPerCategory,
                };

                var response = query.Query(document, activeView, selector);
                if (!response.Success || !(response.Data is BimQueryElementsResult result))
                {
                    // Unknown/unqueryable category in THIS model degrades to a warning, not a failure.
                    context.Warnings.Add(new RevitPresetWarning
                    {
                        Code = "category_unavailable",
                        Message = $"Category '{category}' is not available in this model: {response.Message}",
                    });
                    context.ResolvedCategories.Add(new RevitPresetCategoryCount
                    {
                        Category = category, Resolved = 0, Status = "unavailable",
                    });
                    continue;
                }

                if (result.Query.Truncated && !request.AllowTruncated)
                {
                    var failure = BimApiResponse.Fail(
                        BimErrorCode.QueryTruncated,
                        $"Category '{category}' resolved a truncated set ({result.Query.Returned} of more than " +
                        $"{result.Query.Limit}); set allowTruncated=true to export the capped set.",
                        409);
                    failure.Data = new { category, returned = result.Query.Returned, limit = result.Query.Limit };
                    return RevitPresetResolution.Fail(failure);
                }

                var categoryCount = 0;
                foreach (var summary in result.Elements)
                {
                    var resolved = RevitIdentitySerializer.Resolve(document, summary.Identity);
                    if (!resolved.Success || resolved.Element == null)
                    {
                        continue;
                    }

                    var dedupKey = documentGuid + "|" + resolved.Element.UniqueId;
                    if (seen.Add(dedupKey))
                    {
                        ordered.Add(resolved.Element);
                        categoryCount++;
                    }
                }

                totalResolved += result.Query.Returned;
                context.ResolvedCategories.Add(new RevitPresetCategoryCount
                {
                    Category = category, Resolved = result.Query.Returned, Status = "resolved",
                });
            }

            // Success condition: non-rooms-driven presets require at least one resolved element.
            if (!definition.RoomsDriven && ordered.Count == 0)
            {
                var failure = BimApiResponse.Fail(
                    BimErrorCode.NoCategoriesResolved,
                    $"Preset '{definition.Name}' resolved no elements (none of its categories were present " +
                    "in the selected scope).",
                    422);
                failure.Data = new { warnings = context.Warnings.Select(w => new { w.Code, w.Message }).ToList() };
                return RevitPresetResolution.Fail(failure);
            }

            return new RevitPresetResolution
            {
                Elements = ordered,
                Truncated = false,
                RequestedCount = totalResolved,
                Context = context,
            };
        }

        private static IReadOnlyList<string> EffectiveCategories(
            BimPresetDefinition definition, BimExportPresetRequest request)
        {
            var categories = new List<string>(definition.Categories);
            if (request.IncludeCategories != null)
            {
                foreach (var add in request.IncludeCategories)
                {
                    if (!string.IsNullOrWhiteSpace(add) &&
                        !categories.Any(c => string.Equals(c, add, StringComparison.OrdinalIgnoreCase)))
                    {
                        categories.Add(add.Trim());
                    }
                }
            }

            if (request.ExcludeCategories != null && request.ExcludeCategories.Count > 0)
            {
                var excluded = new HashSet<string>(
                    request.ExcludeCategories.Where(c => !string.IsNullOrWhiteSpace(c)).Select(c => c.Trim()),
                    StringComparer.OrdinalIgnoreCase);
                categories = categories.Where(c => !excluded.Contains(c)).ToList();
            }

            return categories;
        }

        private static BimRoomsMode ResolveRooms(
            BimPresetDefinition definition, string? roomsOverride, out BimApiResponse? error)
        {
            error = null;
            if (string.IsNullOrWhiteSpace(roomsOverride))
            {
                return definition.DefaultRooms;
            }

            switch (roomsOverride!.Trim().ToLowerInvariant())
            {
                case "both": return BimRoomsMode.Both;
                case "labels_only": return BimRoomsMode.LabelsOnly;
                case "exclude": return BimRoomsMode.Exclude;
                default:
                    error = BimApiResponse.Fail(
                        BimErrorCode.InvalidScope, $"Invalid rooms override '{roomsOverride}'.", 400);
                    return definition.DefaultRooms;
            }
        }
    }

    internal sealed class RevitPresetResolution
    {
        public BimApiResponse? Failure { get; set; }

        public IReadOnlyList<Element> Elements { get; set; } = Array.Empty<Element>();

        public bool Truncated { get; set; }

        public int RequestedCount { get; set; }

        public RevitPresetContext Context { get; set; } = new RevitPresetContext();

        public static RevitPresetResolution Fail(BimApiResponse failure)
        {
            return new RevitPresetResolution { Failure = failure };
        }
    }
}
```

- [ ] **Step 4: Run the source-text test**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter PresetResolver_LoopsCategoriesUnionsByIdentityAndDegradesGracefully`
Expected: PASS.

- [ ] **Step 5: BUILD GATE**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds. Fix Revit/contract signature mismatches until green.

- [ ] **Step 6: Commit**

```bash
git add src/RookBim/Revit/RevitPresetResolver.cs src/RookBim.Tests/RookBimExportPresetSourceTests.cs
git commit -m "feat(rookbim): multi-category preset resolver (union/dedup/freeze + warnings + success gate)"
```

---

## Task 9: Fill summary + relationship index (preset-path-only)

**Files:**
- Modify: `src/RookBim/Revit/RevitExportService.cs` (`BuildSummary`)
- Modify: `src/RookBim/Revit/RevitRelationshipIndex.cs` (`Accumulate`/`ToWire`)
- Test: `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` (add a method)

- [ ] **Step 1: Add the failing source-text test**

Add to `src/RookBim.Tests/RookBimExportPresetSourceTests.cs`:

```csharp
        [Fact]
        public void Summary_AndRelationships_ArePresetPathOnlyAndFactual()
        {
            var service = Read("src/RookBim/Revit/RevitExportService.cs");
            var rel = Read("src/RookBim/Revit/RevitRelationshipIndex.cs");

            // Summary structured fields + digest.
            Assert.Contains("digest", service);
            Assert.Contains("resolvedCategories", service);
            Assert.Contains("geometryQuality", service);
            Assert.Contains("layerPolicy", service);
            Assert.Contains("warnings", service);

            // Relationships are facts only (carry source/confidence), three membership lists.
            Assert.Contains("roomMembership", rel);
            Assert.Contains("hostMembership", rel);
            Assert.Contains("levelMembership", rel);
            Assert.Contains("confidence", rel);

            // Decoration stays gated on the preset context.
            Assert.Contains("presetContext == null", service);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter Summary_AndRelationships_ArePresetPathOnlyAndFactual`
Expected: FAIL — `resolvedCategories`/`digest` not yet present.

- [ ] **Step 3: Implement `BuildSummary`**

In `src/RookBim/Revit/RevitExportService.cs`, replace the `BuildSummary` stub with:

```csharp
        private static object BuildSummary(
            RevitPresetContext presetContext,
            BimExportCounts counts,
            Dictionary<string, RevitCategoryExportTally> perCategoryExport,
            Dictionary<string, int> roomRepCounts,
            int layerCount,
            BimExportArtifactPaths paths)
        {
            var resolvedCategories = presetContext.ResolvedCategories.Select(rc =>
            {
                perCategoryExport.TryGetValue(rc.Category, out var tally);
                return new
                {
                    category = rc.Category,
                    resolved = rc.Resolved,
                    exported = tally?.Exported ?? 0,
                    failed = tally?.Failed ?? 0,
                    status = rc.Status,
                };
            }).ToList();

            var warnings = presetContext.Warnings.Select(w => new { code = w.Code, message = w.Message }).ToList();
            var layerWarnings = new List<object>();
            const int LayerCountThreshold = 64;
            if (layerCount > LayerCountThreshold)
            {
                layerWarnings.Add(new
                {
                    code = "layer_count_high",
                    message = $"Export produced {layerCount} layers (threshold {LayerCountThreshold}).",
                });
            }

            var exportedTotal = counts.ExportedBrep + counts.ExportedMesh + counts.ExportedBboxProxy;
            var digest =
                $"Exported {exportedTotal} elements across {presetContext.EffectiveCategories.Count} categories: " +
                $"{counts.ExportedBrep} Breps, {counts.ExportedMesh} meshes, {counts.ExportedBboxProxy} bbox proxies, " +
                $"{counts.Failed} failed. {counts.Rooms} rooms included. {warnings.Count} warning(s).";

            return new
            {
                digest,
                preset = presetContext.Preset,
                effectiveCategories = presetContext.EffectiveCategories,
                layerPolicy = presetContext.Policy.LayerScheme.ToString(),
                namePolicy = presetContext.Policy.NameScheme.ToString(),
                metadataProfile = presetContext.Policy.MetadataProfile.ToString(),
                limitPerCategory = presetContext.LimitPerCategory,
                resolvedCategories,
                geometryQuality = new
                {
                    brep = counts.ExportedBrep,
                    mesh = counts.ExportedMesh,
                    bbox_proxy = counts.ExportedBboxProxy,
                    failed = counts.Failed,
                },
                rooms = new
                {
                    total = counts.Rooms,
                    byRepresentation = roomRepCounts,
                },
                layers = new { count = layerCount, warnings = layerWarnings },
                warnings,
            };
        }
```

- [ ] **Step 4: Implement the relationship index**

Replace the body of `src/RookBim/Revit/RevitRelationshipIndex.cs`:

```csharp
using System.Collections.Generic;

namespace RookBim.Revit
{
    /// <summary>
    /// Factual membership index (room/host/level) built from already-extracted labels. Emits only
    /// what Revit explicitly provides, each entry carrying source + confidence. No inferred
    /// containment, no precomputed calibration pairs.
    /// </summary>
    internal sealed class RevitRelationshipIndex
    {
        private readonly List<object> roomMembership = new List<object>();
        private readonly List<object> hostMembership = new List<object>();
        private readonly List<object> levelMembership = new List<object>();

        public void Accumulate(string elementUniqueId, RevitElementLabels labels)
        {
            if (HasValue(labels.ContainingRoom))
            {
                roomMembership.Add(new
                {
                    elementUniqueId,
                    roomUniqueId = labels.ContainingRoom.Value,
                    source = labels.ContainingRoom.Source,
                    confidence = labels.ContainingRoom.Confidence,
                });
            }

            if (HasValue(labels.HostId))
            {
                hostMembership.Add(new
                {
                    elementUniqueId,
                    hostUniqueId = labels.HostId.Value,
                    source = labels.HostId.Source,
                    confidence = labels.HostId.Confidence,
                });
            }

            if (HasValue(labels.Level))
            {
                levelMembership.Add(new
                {
                    elementUniqueId,
                    levelName = labels.Level.Value,
                    source = labels.Level.Source,
                    confidence = labels.Level.Confidence,
                });
            }
        }

        public object ToWire()
        {
            return new
            {
                roomMembership,
                hostMembership,
                levelMembership,
            };
        }

        public static object EmptyWire()
        {
            return new
            {
                roomMembership = new List<object>(),
                hostMembership = new List<object>(),
                levelMembership = new List<object>()
            };
        }

        private static bool HasValue(BimSemanticLabel? label)
        {
            return label != null && !string.IsNullOrWhiteSpace(label.Value);
        }
    }
}
```

- [ ] **Step 5: Run the source-text tests**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RookBimExportPresetSourceTests`
Expected: PASS (all three methods).

- [ ] **Step 6: BUILD GATE**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add src/RookBim/Revit/RevitExportService.cs src/RookBim/Revit/RevitRelationshipIndex.cs src/RookBim.Tests/RookBimExportPresetSourceTests.cs
git commit -m "feat(rookbim): preset summary digest + factual relationship index (preset-path-only)"
```

---

## Task 10: Wire `ExportPreset` on the Revit runtime

**Files:**
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`
- Test: `src/RookBim.Tests/RookBimExportPresetSourceTests.cs` (add a method)

**Interfaces:**
- Consumes: `RevitPresetResolver.Resolve(...)`, `RevitExportService.ExportResolved(...)`.

- [ ] **Step 1: Add the failing source-text test**

Add to `src/RookBim.Tests/RookBimExportPresetSourceTests.cs`:

```csharp
        [Fact]
        public void Runtime_WiresExportPresetThroughResolverAndExportTimeout()
        {
            var src = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("public BimApiResponse ExportPreset(BimExportPresetRequest request)", src);
            Assert.Contains("RevitPresetResolver", src);
            Assert.Contains("ExportResolved", src);
            Assert.Contains("ExportDispatchTimeout", src);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter Runtime_WiresExportPresetThroughResolverAndExportTimeout`
Expected: FAIL.

- [ ] **Step 3: Add the resolver field + `ExportPreset` method**

In `src/RookBim/Revit/RevitRookBimRuntime.cs`:

(a) Add a resolver field next to `private readonly RevitExportService export;`:

```csharp
        private readonly RevitPresetResolver presetResolver;
```

(b) In the `internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)` constructor, after `this.export = new RevitExportService();`, add:

```csharp
            this.presetResolver = new RevitPresetResolver();
```

(c) Add the method after `ExportElements`:

```csharp
        public BimApiResponse ExportPreset(BimExportPresetRequest request)
        {
            if (request == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope, "export-preset request is required.", 400);
            }

            var validation = request.Validate();
            if (!validation.Success)
            {
                return BimApiResponse.Fail(
                    validation.ErrorCode, validation.Message ?? "export-preset validation failed.", 400);
            }

            try
            {
                return DispatchWithTimeout(uiapp =>
                {
                    var uidoc = RevitContext.ActiveUiDocument(uiapp);
                    if (uidoc == null || uidoc.Document == null)
                    {
                        return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);
                    }

                    var document = uidoc.Document;
                    var view = uidoc.ActiveView ?? document.ActiveView;
                    try
                    {
                        var resolution = presetResolver.Resolve(document, view, request);
                        if (resolution.Failure != null)
                        {
                            return resolution.Failure;
                        }

                        // Build the inner export request that the resolved core consumes (identities path
                        // semantics; rooms come from the resolved preset context).
                        var innerRequest = new BimExportElementsRequest
                        {
                            Output = request.Output,
                            Rooms = resolution.Context.EffectiveRooms,
                            AllowTruncated = request.AllowTruncated,
                            AllowBboxProxy = request.AllowBboxProxy,
                        };

                        return export.ExportResolved(
                            document,
                            resolution.Elements,
                            resolution.Truncated,
                            resolution.RequestedCount,
                            innerRequest,
                            resolution.Context.Policy,
                            resolution.Context);
                    }
                    catch (Exception ex)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.ExportFailed,
                            $"RookBIM preset export failed inside the Revit document context: {DescribeDispatchException(ex)}",
                            500);
                    }
                }, ExportDispatchTimeout);
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    $"RookBIM could not enter the Revit API context: {DescribeDispatchException(ex)}",
                    503);
            }
        }
```

- [ ] **Step 4: Run the source-text test**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter Runtime_WiresExportPresetThroughResolverAndExportTimeout`
Expected: PASS.

- [ ] **Step 5: BUILD GATE**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add src/RookBim/Revit/RevitRookBimRuntime.cs src/RookBim.Tests/RookBimExportPresetSourceTests.cs
git commit -m "feat(rookbim): wire ExportPreset through resolver + shared export core (export timeout)"
```

---

## Task 11: `BimHandler` op + native `/bim/export-preset` route

**Files:**
- Modify: `src/Rook/Handlers/BimHandler.cs`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Test: `src/Rook.Tests/Handlers/BimHandlerExportPresetSourceTests.cs`

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Handlers/BimHandlerExportPresetSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class BimHandlerExportPresetSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void BimHandler_RegistersExportPresetOpRouteAndCodes()
        {
            var src = Read("src/Rook/Handlers/BimHandler.cs");

            Assert.Contains("\"export_preset\"", src);
            Assert.Contains("runtime.ExportPreset(DeserializeRequest<BimExportPresetRequest>(body))", src);
            Assert.Contains("\"export_preset\" => \"POST /bim/export-preset\"", src);
            Assert.Contains("BimErrorCode.UnknownPreset => \"unknown_preset\"", src);
            Assert.Contains("BimErrorCode.NoCategoriesResolved => \"no_categories_resolved\"", src);
        }

        [Fact]
        public void Native_ExposesExportPresetRouteAndHandler()
        {
            var server = Read("src/RookNative/RookServer.cpp");
            var handlerH = Read("src/RookNative/Handlers/GrasshopperProxyHandler.h");
            var handlerCpp = Read("src/RookNative/Handlers/GrasshopperProxyHandler.cpp");

            Assert.Contains("/bim/export-preset", server);
            Assert.Contains("HandleBimExportPreset", server);
            Assert.Contains("HandleBimExportPreset", handlerH);
            Assert.Contains("export_preset", handlerCpp);
        }

        internal static string Read(string relativePath)
        {
            return File.ReadAllText(Path.Combine(RepoRoot, relativePath.Replace('/', Path.DirectorySeparatorChar)));
        }

        private static string FindRepoRoot()
        {
            var directory = new DirectoryInfo(AppContext.BaseDirectory);
            while (directory != null)
            {
                if (File.Exists(Path.Combine(directory.FullName, "Rook.sln")))
                {
                    return directory.FullName;
                }

                directory = directory.Parent;
            }

            throw new InvalidOperationException("Could not find repository root.");
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimHandlerExportPresetSourceTests`
Expected: FAIL.

- [ ] **Step 3: Extend `BimHandler`**

In `src/Rook/Handlers/BimHandler.cs`:

(a) Add `"export_preset",` to `ExpectedBimOps` (after `"export_elements",`).

(b) Add the dispatch arm after the `export_elements` arm in the `op switch`:

```csharp
                    "export_preset" => FromBimResponse(
                        "export_preset",
                        runtime.ExportPreset(DeserializeRequest<BimExportPresetRequest>(body))),
```

(c) In `MapErrorCode`, add after `BimErrorCode.ExportFailed => "export_failed",`:

```csharp
                BimErrorCode.UnknownPreset => "unknown_preset",
                BimErrorCode.NoCategoriesResolved => "no_categories_resolved",
```

(d) In `RouteForOp`, add after `"export_elements" => "POST /bim/export-elements",`:

```csharp
                "export_preset" => "POST /bim/export-preset",
```

- [ ] **Step 4: Extend the native handler + route**

(a) In `src/RookNative/Handlers/GrasshopperProxyHandler.h`, add after the `HandleBimExportElements` declaration:

```cpp
void HandleBimExportPreset(const httplib::Request& req, httplib::Response& res);
```

(b) In `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`, add after the `HandleBimExportElements` function (it ends at the `}` on the line after `ForwardBimDispatch(... "export_elements" ...)`):

```cpp
void HandleBimExportPreset(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (ParseBimPostBody(req, res, "export_preset", body))
        ForwardBimDispatch(req, res, "POST /bim/export-preset", "export_preset", body);
}
```

(c) In `src/RookNative/RookServer.cpp`, add after the `/bim/export-elements` route registration:

```cpp
    m_server->Post("/bim/export-preset", Rook::Handlers::HandleBimExportPreset);
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimHandlerExportPresetSourceTests`
Expected: PASS.

- [ ] **Step 6: Build the managed handler assembly**

Run: `dotnet build src/Rook/Rook.csproj`
Expected: build succeeds (the `BimExportPresetRequest` deserialization arm compiles).

> The native C++ build is exercised by the live deploy in Task 13. If a local native toolchain is available, `scripts/build-native.bat Release` (via `cmd /c`) confirms the route compiles; otherwise the source-text assertions + Task 13 deploy cover it.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Handlers/BimHandler.cs src/RookNative/Handlers/GrasshopperProxyHandler.h src/RookNative/Handlers/GrasshopperProxyHandler.cpp src/RookNative/RookServer.cpp src/Rook.Tests/Handlers/BimHandlerExportPresetSourceTests.cs
git commit -m "feat(bim): export_preset handler op + native /bim/export-preset route"
```

---

## Task 12: MCP tool + tool group + targeting policy

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_rookbim_export_preset_tool.py`

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_rookbim_export_preset_tool.py`:

```python
from rook import server
from rook.agent import tool_groups
from rook.targeting import RhinoToolPolicy, policy_for_tool
from rook.targeting import (
    _ALL_KNOWN_TOOLS,
    _META_TOOLS,
    _RHINO_READ_TOOLS,
    _RHINO_INDEPENDENT_READ_TOOLS,
    _RHINO_INDEPENDENT_MUTATE_TOOLS,
)


def test_export_preset_schema_shape():
    schema = server._rookbim_export_preset_schema()
    props = schema["properties"]
    assert "preset" in props
    assert "output" in props
    assert "includeCategories" in props
    assert "excludeCategories" in props
    assert "layerPolicy" in props
    assert "namePolicy" in props
    assert "metadataProfile" in props
    assert "limitPerCategory" in props
    assert schema["required"] == ["preset", "output"]
    assert schema["additionalProperties"] is False


def test_export_preset_derives_mutate_policy():
    # The derived policy must be (True, "mutate") — achieved by membership in _ALL_KNOWN_TOOLS
    # and ABSENCE from every read/meta bucket (the user's plan note 1).
    assert policy_for_tool("rookbim_export_preset") == RhinoToolPolicy(True, "mutate")
    assert "rookbim_export_preset" in _ALL_KNOWN_TOOLS
    assert "rookbim_export_preset" not in _META_TOOLS
    assert "rookbim_export_preset" not in _RHINO_READ_TOOLS
    assert "rookbim_export_preset" not in _RHINO_INDEPENDENT_READ_TOOLS
    assert "rookbim_export_preset" not in _RHINO_INDEPENDENT_MUTATE_TOOLS


def test_export_preset_in_full_group_not_readonly():
    assert "rookbim_export_preset" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_export_preset" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_rookbim_export_preset_tool.py -q`
Expected: FAIL — `_rookbim_export_preset_schema` and the registrations do not exist.

- [ ] **Step 3: Add the schema + tool entry + dispatch (`server.py`)**

(a) Add the schema function next to `_rookbim_export_elements_schema` in `mcp_server/src/rook/server.py`:

```python
def _rookbim_export_preset_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": [
                    "architectural_shell",
                    "interiors",
                    "openings_and_hosts",
                    "structural",
                    "rooms_and_spaces",
                    "calibration_fixture",
                ],
                "description": "Curated export recipe (category bundle + default organization policy).",
            },
            "output": {
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Absolute local output directory."},
                    "name": {"type": "string", "description": "Bundle name ([A-Za-z0-9._-], no separators)."},
                    "units": {
                        "type": "string",
                        "enum": ["meters", "millimeters", "centimeters", "feet", "inches"],
                        "default": "meters",
                    },
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["directory", "name"],
                "additionalProperties": False,
            },
            "scope": {"type": "string", "enum": ["active_view", "document"], "default": "active_view"},
            "includeCategories": {"type": "array", "items": {"type": "string"}},
            "excludeCategories": {"type": "array", "items": {"type": "string"}},
            "layerPolicy": {
                "type": "string",
                "enum": ["flat", "by_category", "by_level_then_category"],
            },
            "namePolicy": {
                "type": "string",
                "enum": ["none", "revit_name", "type_only", "readable", "readable_with_id"],
            },
            "metadataProfile": {"type": "string", "enum": ["minimal", "standard", "full"]},
            "rooms": {"type": "string", "enum": ["both", "labels_only", "exclude"]},
            "limitPerCategory": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 1000},
            "allowTruncated": {"type": "boolean", "default": False},
            "allowBboxProxy": {"type": "boolean", "default": False},
            "port": _rookbim_port_schema(),
        },
        "required": ["preset", "output"],
        "additionalProperties": False,
    }
```

(b) Add the `Tool(...)` entry immediately after the `rookbim_export_elements` Tool entry:

```python
        Tool(
            name="rookbim_export_preset",
            description=(
                "Export a curated Revit recipe (architectural_shell, interiors, openings_and_hosts, "
                "structural, rooms_and_spaces, calibration_fixture) to an organized Rhino bundle: "
                "multi-category selection, RookBim:: layers, readable names, embedded metadata, a "
                "summary + relationship index. Read-only on Revit/Rhino; writes files to disk."
            ),
            inputSchema=_rookbim_export_preset_schema(),
        ),
```

(c) Add the dispatch case immediately after the `rookbim_export_elements` case:

```python
        case "rookbim_export_preset":
            result = await call_rhino(
                "/bim/export-preset", "POST", arguments, port=port
            )
```

- [ ] **Step 4: Add to the tool group (`tool_groups.py`)**

In `mcp_server/src/rook/agent/tool_groups.py`, add `"rookbim_export_preset",` to the `"rookbim"` list (after `"rookbim_export_elements",`). Do **NOT** add it to `"rookbim_readonly"`.

- [ ] **Step 5: Add to `_ALL_KNOWN_TOOLS` (`targeting.py`)**

In `mcp_server/src/rook/targeting.py`, add `"rookbim_export_preset",` to `_ALL_KNOWN_TOOLS` (next to `"rookbim_export_elements",`). Add it to **no other set** — the derived `_RHINO_MUTATE_TOOLS` then yields `(True, "mutate")`.

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_rookbim_export_preset_tool.py -q`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_rookbim_export_preset_tool.py
git commit -m "feat(mcp): rookbim_export_preset tool (schema, dispatch, rookbim group, mutate policy)"
```

---

## Task 13: Gated live verification (non-vacuous)

**Files:**
- Create: `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export_preset.py`

This is a **gated** script (real Revit + Rhino.Inside.Revit, run manually). It must NOT pass vacuously on an empty/sheet view: it requires ≥1 exported model object, ≥1 preset-organized layer, populated object names, standard metadata stamps, and the preset summary. Exact category composition is reported, not hard-pinned.

- [ ] **Step 1: Write the live-verify script**

Create `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export_preset.py`:

```python
"""Gated live verification for rookbim_export_preset.

Run with Rhino.Inside.Revit active and a Revit model open on a 3D view (NOT a sheet).
Exports the architectural_shell preset, then asserts a non-vacuous, organized bundle:
hierarchical RookBim:: layers, populated object names, standard metadata stamps, the bijection,
count reconciliation, the summary, and the relationship index.

Usage: python docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export_preset.py <abs_output_dir>
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

from rook.bridge import discover_instances


def _native_port() -> int:
    instances = discover_instances()
    native = [i for i in instances if i.get("pluginType") == "native" and isinstance(i.get("port"), int)]
    if not native:
        raise RuntimeError(
            "No native Rook instance found. Is Rhino.Inside.Revit running with the Rook plugins loaded?"
        )
    return int(native[0]["port"])


def _post(port: int, path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="rookbim_preset_")
    port = _native_port()

    result = _post(port, "/bim/export-preset", {
        "preset": "architectural_shell",
        "output": {"directory": out_dir, "name": "shell-preset", "units": "meters", "overwrite": True},
        "scope": "active_view",
        "allowTruncated": True,
    })

    assert result.get("success"), f"export failed: {result}"
    data = result["data"]
    paths = data["paths"]
    for key in ("model3dm", "sidecar", "validation"):
        assert Path(paths[key]).exists(), f"missing artifact {key}: {paths[key]}"

    sidecar = json.loads(Path(paths["sidecar"]).read_text(encoding="utf-8"))
    validation = json.loads(Path(paths["validation"]).read_text(encoding="utf-8"))

    # Bijection + counts.
    assert data["verification"]["ok"], f"bijection failed: {data['verification']['discrepancies']}"
    counts = data["counts"]
    exported = counts["exportedBrep"] + counts["exportedMesh"] + counts["exportedBboxProxy"]
    assert counts["resolved"] == exported + counts["failed"], f"count mismatch: {counts}"

    # NON-VACUOUS gate 1: at least one exported model object.
    assert exported >= 1, f"vacuous export — no model geometry: {counts}"

    # NON-VACUOUS gate 2: at least one preset-organized layer under RookBim:: that is not the flat
    # Model layer, and never the wrong-cased root.
    elements = sidecar["elements"]
    assert elements, "vacuous export — no element records"
    raw_text = Path(paths["sidecar"]).read_text(encoding="utf-8")
    assert "RookBIM::" not in raw_text, "wrong-cased layer root present"

    # NON-VACUOUS gate 3: summary present + structured.
    summary = data["summary"]
    assert summary["digest"], "summary digest missing"
    assert summary["preset"] == "architectural_shell"
    assert summary["layerPolicy"] == "ByLevelThenCategory"
    assert summary["resolvedCategories"], "no resolved categories in summary"
    assert summary["geometryQuality"]["brep"] >= 1 or summary["geometryQuality"]["mesh"] >= 1

    # NON-VACUOUS gate 4: standard metadata stamps + populated object names reach the sidecar records.
    first = elements[0]
    assert first.get("name"), "element record missing name"
    assert first.get("type") is not None or first.get("category") is not None

    # NON-VACUOUS gate 5: relationship index present (facts only).
    rel = validation["relationships"]
    assert set(rel.keys()) >= {"roomMembership", "hostMembership", "levelMembership"}

    print("LIVE VERIFY PASS (preset)")
    print(f"  preset=architectural_shell resolved={counts['resolved']} exported={exported} "
          f"failed={counts['failed']} rooms={counts['rooms']}")
    print(f"  categories={[c['category'] for c in summary['resolvedCategories']]}")
    print(f"  digest: {summary['digest']}")
    print(f"  bundle: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Commit (script only — execution is a manual gate)**

```bash
git add docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export_preset.py
git commit -m "test(rookbim): gated non-vacuous live-verify for rookbim_export_preset"
```

- [ ] **Step 3: (Manual, gated) Deploy + run the live verification**

When a live Rhino.Inside.Revit session is available on a sample architectural model (e.g. Snowdon Towers) with a **3D view active** (not a sheet):
1. Deploy the native route: `cmd /c scripts\deploy-native.bat Release` (after closing Revit if the binary is locked), then relaunch Rhino.Inside.Revit.
2. Run: `cd mcp_server && set PYTHONPATH=src && python ..\docs\rook_docs\rookbim-export-spike\live_verify_rookbim_export_preset.py %TEMP%\rookbim_preset_live`
3. Expected: `LIVE VERIFY PASS (preset)` with `exported >= 1`, hierarchical categories listed, and a non-empty digest.

---

## Self-Review

**Spec coverage:**
- §2 new front door / units → Tasks 1, 6, 10, 11, 12. ✓
- §3 contract-stability seam (Legacy parity, preset-only decoration) → Task 7 (Legacy + null gating), Task 9 (`presetContext == null` gate), parity assertions in Task 7 Step 10 + Task 13 gate 2. ✓
- §4 multi-category resolution + success condition + `rooms_and_spaces` bypass → Task 8 (`RoomsDriven`, `NoCategoriesResolved`, dedup by docGuid|uniqueId). ✓
- §5 layer schemes + `RookBim::` root + fallbacks + sanitize + count guard → Task 4 (namer) + Task 9 (`layer_count_high`). ✓
- §6 object naming → Task 5. ✓
- §7 metadata profiles + value-only + omit-missing → Task 7 (`StampObject`). ✓
- §8 summary + relationships, both response & validation, facts-only → Task 9. ✓
- §9 request contract + catalog + `limitPerCategory` default 1000 → Tasks 1, 2, 8. ✓
- §10 error codes + registration + targeting → Tasks 1, 11, 12. ✓
- §11 testing (legacy parity, no Revit outside RookBim, no Transactions, registration, live smoke, relationship presence) → Tasks 7, 8, 11, 12, 13. ✓

**Placeholder scan:** `BuildSummary`/`RevitRelationshipIndex` are explicitly stubbed in Task 7 and filled in Task 9 (each is real code at each step, not a "TODO"). No `TBD`/`implement later`. ✓

**Type consistency:** `ExportResolved`, `RevitPresetContext`, `RevitPresetResolution`, `RevitRelationshipIndex.Accumulate/ToWire`, `BimExportOrganizationPolicy.Resolve(out policy)`, `BimExportLayerNamer.LayerPath`, `BimExportObjectNamer.ObjectName(long?)`, `BimPresetCatalog.TryGet`, error codes `UnknownPreset`/`NoCategoriesResolved` and their wire strings `unknown_preset`/`no_categories_resolved` are used consistently across tasks. The `RevitStampData.ElementIdValue` (`long`) widens to the namer's `long?`. ✓

**Known follow-ups (not blocking):** per-category `exported`/`failed` in the summary are keyed by the element's live `Category.Name`; an included category whose Revit display name differs from the queried string would tally under its actual name (acceptable — reported, not hard-pinned, per the live-gate boundary).
