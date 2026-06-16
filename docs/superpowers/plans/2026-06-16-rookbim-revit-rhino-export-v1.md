# RookBIM Revit→Rhino Geometry + Label/Sidecar Export v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only RookBIM `export_elements` op that exports caller-selected Revit elements into a Rhino-consumable `.3dm` plus `sidecar.json` + `validation.json` bundle (geometry + identity + semantic labels) for later offline consumption by Threshold Calibration v1.

**Architecture:** RookBIM runs inside Rhino.Inside.Revit, so RhinoCommon is in-process. The export reads Revit elements (no `Transaction`), converts geometry to RhinoCommon (in-process Rhino.Inside converter via reflection → mesh fallback → opt-in bbox proxy), builds a **standalone in-memory `File3dm`**, and writes a three-file bundle to disk via a path-safe writer — never touching the active Rhino document or scene graph. Pure validation + path policy live in the core `src/Rook` assembly (unit-tested in CI); Revit/RhinoCommon-coupled code lives in `src/RookBim` (source-text tested in CI + a gated live script).

**Tech Stack:** C# (net48, `src/RookBim` + `src/Rook`), RhinoCommon (`Rhino.FileIO.File3dm`, `Rhino.Geometry`), Revit API (reflection-only for Rhino.Inside converter), C++ (`src/RookNative`, httplib + nlohmann::json), Python (`mcp_server`, MCP tool surface), xUnit (C# tests), pytest (Python tests).

**Branch:** `feature/spatial-intelligence` (worktree `C:/Users/aryan/source/repos/rook-spatial`). Never stage `knowledge/contextual_mab.pkl`, `knowledge/gh/component_observations.json`, `src/Rook/Properties/launchSettings.json`.

**Spec:** `docs/superpowers/specs/2026-06-16-rookbim-revit-rhino-export-v1-design.md` (read it first).

---

## File Structure

**Core assembly `src/Rook/Bim/` (no Revit ref — unit-testable in CI):**
- `BimContracts.cs` (MODIFY) — new error codes; `BimExportOutput`, `BimRoomsMode`, `BimExportElementsRequest` (+ `Validate()`); result POCOs (`BimExportArtifactPaths`, `BimExportCounts`, `BimExportVerification`, `BimExportResult`).
- `BimExportPathPolicy.cs` (CREATE) — pure path/name-safety helper (absolute-local dir, name sanitization, bundle paths, overwrite + escape checks).
- `IRookBimRuntime.cs` (MODIFY) — `+ BimApiResponse ExportElements(BimExportElementsRequest request)`.
- `RookBimUnavailableRuntime.cs` (MODIFY) — implement `ExportElements` → Unavailable.

**Revit assembly `src/RookBim/Revit/` (Revit + RhinoCommon — source-text tested + live):**
- `RevitGeometryConverter.cs` (CREATE) — per-element Revit→RhinoCommon (reflection Brep → `Face.Triangulate` mesh → bbox), feet→units scale, representation/quality tags.
- `RevitLabelExtractor.cs` (CREATE) — level/host/room/space labels with `{value, source, confidence, missingReason}`.
- `RevitRoomExporter.cs` (CREATE) — rooms/spaces reference geometry + labels, per-room degrade.
- `RevitExportService.cs` (CREATE) — orchestrator: resolve set → freeze identities → convert → assemble `File3dm` + sidecar + validation → path-safe write → verification.
- `RevitRookBimRuntime.cs` (MODIFY) — `ExportElements` wired through the dispatcher with a larger export timeout.

**Native `src/RookNative/` (C++):**
- `Handlers/GrasshopperProxyHandler.cpp` + `.h` (MODIFY) — `HandleBimExportElements`.
- `RookServer.cpp` (MODIFY) — `POST /bim/export-elements` route.

**MCP `mcp_server/src/rook/` (Python):**
- `server.py` (MODIFY) — `_rookbim_export_elements_schema`, tool entry, dispatch case.
- `agent/tool_groups.py` (MODIFY) — add to `rookbim` group (NOT `rookbim_readonly`).
- `targeting.py` (MODIFY) — add to `_ALL_KNOWN_TOOLS` only (auto-classified mutate).

**Tests:**
- `src/Rook.Tests/Bim/RookBimExportContractsTests.cs` (CREATE) — request validation (behavioral).
- `src/Rook.Tests/Bim/RookBimExportPathPolicyTests.cs` (CREATE) — path-safety + units validation (behavioral).
- `src/Rook.Tests/Bim/RookBimUnavailableExportTests.cs` (CREATE) — Unavailable runtime (behavioral).
- `src/Rook.Tests/Handlers/BimHandlerExportSourceTests.cs` (CREATE) — handler wiring (source-text).
- `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs` (MODIFY) — native route row.
- `src/RookBim.Tests/RookBimExportSourceTests.cs` (CREATE) — RookBim service source-text tests.
- `mcp_server/tests/test_rookbim_export_tool.py` (CREATE) — MCP tool + targeting (behavioral).
- `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py` (CREATE) — gated live verify.

**Build/test commands** (run from worktree root `C:/Users/aryan/source/repos/rook-spatial`):
- Core/handler C# tests: `dotnet test src/Rook.Tests/Rook.Tests.csproj`
- RookBim source-text tests: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj`
- Python tests: `cd mcp_server && python -m pytest tests/test_rookbim_export_tool.py -q`

---

## Task 1: Core contracts — error codes, request, validation, result POCOs

**Files:**
- Modify: `src/Rook/Bim/BimContracts.cs`
- Test: `src/Rook.Tests/Bim/BimExportContractsTests.cs`

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/BimExportContractsTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class BimExportContractsTests
    {
        private static BimExportOutput ValidOutput() =>
            new BimExportOutput { Directory = @"C:\fixtures", Name = "walls" };

        [Fact]
        public void Validate_RejectsNeitherSelectorNorIdentities()
        {
            var request = new BimExportElementsRequest { Output = ValidOutput() };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }

        [Fact]
        public void Validate_RejectsBothSelectorAndIdentities()
        {
            var request = new BimExportElementsRequest
            {
                Output = ValidOutput(),
                Selector = new BimQueryElementsRequest { Category = "Walls" },
                Identities = new System.Collections.Generic.List<BimElementIdentity>
                {
                    new BimElementIdentity { UniqueId = "abc" },
                },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.InvalidScope, result.ErrorCode);
        }

        [Fact]
        public void Validate_AcceptsSelectorOnly_AndDefaultsRoomsToBoth()
        {
            var request = new BimExportElementsRequest
            {
                Output = ValidOutput(),
                Selector = new BimQueryElementsRequest { Category = "Walls" },
            };
            var result = request.Validate();
            Assert.True(result.Success);
            Assert.Equal(BimRoomsMode.Both, request.EffectiveRooms);
        }

        [Fact]
        public void Validate_RejectsMissingOutputDirectoryOrName()
        {
            var request = new BimExportElementsRequest
            {
                Selector = new BimQueryElementsRequest { Category = "Walls" },
                Output = new BimExportOutput { Name = "walls" },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Fact]
        public void Validate_PropagatesSelectorValidationFailure()
        {
            // document scope with no category is invalid in the underlying selector
            var request = new BimExportElementsRequest
            {
                Output = ValidOutput(),
                Selector = new BimQueryElementsRequest { Scope = BimQueryScope.Document },
            };
            var result = request.Validate();
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnboundedDocumentQuery, result.ErrorCode);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportContractsTests`
Expected: FAIL — `BimExportElementsRequest`, `BimExportOutput`, `BimRoomsMode`, `BimErrorCode.OutputPathInvalid` do not exist (compile error).

- [ ] **Step 3: Add the error codes**

In `src/Rook/Bim/BimContracts.cs`, extend the `BimErrorCode` enum (after `SelectionFailed`, before `InternalError`):

```csharp
        SelectionFailed,
        QueryTruncated,
        OutputPathInvalid,
        NoExportableGeometry,
        ExportFailed,
        InternalError
```

- [ ] **Step 4: Add the request + output + rooms-mode types**

Append to `src/Rook/Bim/BimContracts.cs` (inside `namespace Rook.Bim`, after `BimSelectElementsRequest`):

```csharp
    public enum BimRoomsMode
    {
        Both,
        LabelsOnly,
        Exclude
    }

    public sealed class BimExportOutput
    {
        public string? Directory { get; set; }

        public string? Name { get; set; }

        public string Units { get; set; } = "meters";

        public bool Overwrite { get; set; }
    }

    public sealed class BimExportElementsRequest
    {
        public BimQueryElementsRequest? Selector { get; set; }

        public List<BimElementIdentity>? Identities { get; set; }

        public BimExportOutput Output { get; set; } = new BimExportOutput();

        public BimRoomsMode? Rooms { get; set; }

        public bool AllowTruncated { get; set; }

        public bool AllowBboxProxy { get; set; }

        public BimRoomsMode EffectiveRooms
        {
            get { return Rooms ?? BimRoomsMode.Both; }
        }

        public bool HasSelector
        {
            get { return Selector != null; }
        }

        public bool HasIdentities
        {
            get { return Identities != null && Identities.Count > 0; }
        }

        public BimValidationResult Validate()
        {
            if (HasSelector == HasIdentities)
            {
                return Fail(
                    BimErrorCode.InvalidScope,
                    "export-elements requires exactly one of 'selector' or 'identities'.");
            }

            if (HasSelector)
            {
                var selectorValidation = Selector!.Validate();
                if (!selectorValidation.Success)
                {
                    return selectorValidation;
                }
            }

            // Task 1 does ONLY local output-shape validation so it is independently green.
            // Task 2 swaps this for the full BimExportPathPolicy.ValidateRequestShape.
            if (Output == null ||
                string.IsNullOrWhiteSpace(Output.Directory) ||
                string.IsNullOrWhiteSpace(Output.Name))
            {
                return Fail(
                    BimErrorCode.OutputPathInvalid,
                    "export-elements requires output.directory and output.name.");
            }

            return BimValidationResult.Ok;
        }

        private static BimValidationResult Fail(BimErrorCode code, string message)
        {
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = code,
                Message = message
            };
        }
    }
```

- [ ] **Step 5: Add the result POCOs**

Append to `src/Rook/Bim/BimContracts.cs`:

```csharp
    public sealed class BimExportArtifactPaths
    {
        public string Model3dm { get; set; } = string.Empty;

        public string Sidecar { get; set; } = string.Empty;

        public string Validation { get; set; } = string.Empty;
    }

    public sealed class BimExportCounts
    {
        public int Requested { get; set; }

        public int Resolved { get; set; }

        public int ExportedBrep { get; set; }

        public int ExportedMesh { get; set; }

        public int ExportedBboxProxy { get; set; }

        public int Failed { get; set; }

        public int Rooms { get; set; }

        public bool Truncated { get; set; }
    }

    public sealed class BimExportVerification
    {
        public bool Ok { get; set; }

        public List<string> Discrepancies { get; set; } = new List<string>();
    }

    public sealed class BimExportResult
    {
        public int SchemaVersion { get; set; } = 1;

        public BimExportArtifactPaths Paths { get; set; } = new BimExportArtifactPaths();

        public BimExportCounts Counts { get; set; } = new BimExportCounts();

        public BimExportVerification Verification { get; set; } = new BimExportVerification();

        public string SourceUnits { get; set; } = "feet";

        public string TargetUnits { get; set; } = "meters";

        public double UnitScaleFactor { get; set; } = 1.0;
    }
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimExportContractsTests`
Expected: PASS (5 tests). Task 1 is now self-contained — it has no dependency on Task 2.

- [ ] **Step 7: Commit**

```bash
git add src/Rook/Bim/BimContracts.cs src/Rook.Tests/Bim/BimExportContractsTests.cs
git commit -m "feat(bim): export request contract, error codes, result POCOs"
```

---

## Task 2: Path-safety policy (pure, unit-tested)

**Files:**
- Create: `src/Rook/Bim/BimExportPathPolicy.cs`
- Test: `src/Rook.Tests/Bim/RookBimExportPathPolicyTests.cs` (folder convention is `RookBim*`)

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/RookBimExportPathPolicyTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimExportPathPolicyTests
    {
        [Theory]
        [InlineData(null)]
        [InlineData("")]
        [InlineData("relative/dir")]
        [InlineData("C:fixtures")]   // drive-relative — Path.IsPathRooted returns true, but it is NOT absolute
        [InlineData("C:")]
        [InlineData(@"\\server\share\fixtures")]  // UNC — ambiguous local target
        public void ValidateRequestShape_RejectsNonAbsoluteOrNonLocalDirectory(string? dir)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = dir, Name = "walls" });
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Theory]
        [InlineData("walls/foo")]
        [InlineData("walls\\foo")]
        [InlineData("..walls")]
        [InlineData("wall:s")]
        [InlineData("")]
        [InlineData("CON")]       // reserved device name
        [InlineData("nul")]       // case-insensitive
        [InlineData("COM1")]
        [InlineData("LPT1")]
        [InlineData("PRN")]
        [InlineData("AUX")]
        [InlineData("CON.json")]  // reserved base name with extension
        public void ValidateRequestShape_RejectsUnsafeName(string name)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = name });
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Theory]
        [InlineData("meters")]
        [InlineData("Meters")]      // case-insensitive
        [InlineData("millimeters")]
        [InlineData("centimeters")]
        [InlineData("feet")]
        [InlineData("inches")]
        public void ValidateRequestShape_AcceptsSupportedUnits(string units)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = "walls", Units = units });
            Assert.True(result.Success);
        }

        [Theory]
        [InlineData("cubits")]
        [InlineData("")]
        [InlineData("mm")]          // aliases are NOT part of the public unit contract
        public void ValidateRequestShape_RejectsUnsupportedUnits(string units)
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = "walls", Units = units });
            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.OutputPathInvalid, result.ErrorCode);
        }

        [Fact]
        public void ValidateRequestShape_AcceptsAbsoluteDirAndSafeName()
        {
            var result = BimExportPathPolicy.ValidateRequestShape(
                new BimExportOutput { Directory = @"C:\fixtures", Name = "walls-01_v2" });
            Assert.True(result.Success);
        }

        [Fact]
        public void ResolveBundlePaths_BuildsDeterministicPrefixInsideDirectory()
        {
            var paths = BimExportPathPolicy.ResolveBundlePaths(@"C:\fixtures", "walls");
            Assert.EndsWith("walls.3dm", paths.Model3dm);
            Assert.EndsWith("walls.sidecar.json", paths.Sidecar);
            Assert.EndsWith("walls.validation.json", paths.Validation);
            Assert.StartsWith(@"C:\fixtures", paths.Model3dm);
        }

        [Fact]
        public void EscapesIntendedDirectory_TrueWhenPathOutside()
        {
            Assert.True(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\other\walls.3dm", @"C:\fixtures"));
            Assert.False(BimExportPathPolicy.EscapesIntendedDirectory(@"C:\fixtures\walls.3dm", @"C:\fixtures"));
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookBimExportPathPolicyTests`
Expected: FAIL — `BimExportPathPolicy` does not exist.

- [ ] **Step 3: Implement the policy**

Create `src/Rook/Bim/BimExportPathPolicy.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;

namespace Rook.Bim
{
    public static class BimExportPathPolicy
    {
        private static readonly char[] DisallowedNameChars =
            new[] { '/', '\\', ':', '*', '?', '"', '<', '>', '|' };

        // Windows reserved device names — illegal as file base names even with an extension.
        private static readonly HashSet<string> ReservedDeviceNames = new HashSet<string>(
            new[]
            {
                "CON", "PRN", "AUX", "NUL",
                "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
                "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
            },
            StringComparer.OrdinalIgnoreCase);

        // The supported output unit systems — kept in lockstep with the MCP tool schema enum and
        // RevitGeometryConverter.ScaleFromFeet. Validating here means an unknown unit fails fast at
        // the request boundary rather than silently degrading to a default downstream.
        private static readonly HashSet<string> SupportedUnits = new HashSet<string>(
            new[] { "meters", "millimeters", "centimeters", "feet", "inches" },
            StringComparer.OrdinalIgnoreCase);

        public static BimValidationResult ValidateRequestShape(BimExportOutput? output)
        {
            if (output == null)
            {
                return Fail("export output is required.");
            }

            if (!IsFullyQualifiedLocalDirectory(output.Directory))
            {
                return Fail("output.directory must be an absolute, fully-qualified local directory path.");
            }

            if (!IsSafeName(output.Name))
            {
                return Fail(
                    "output.name must be non-empty and contain only [A-Za-z0-9._-] (no separators, no '..').");
            }

            if (string.IsNullOrWhiteSpace(output.Units) || !SupportedUnits.Contains(output.Units))
            {
                return Fail(
                    "output.units must be one of: meters, millimeters, centimeters, feet, inches.");
            }

            return BimValidationResult.Ok;
        }

        public static bool IsSafeName(string? name)
        {
            if (string.IsNullOrWhiteSpace(name))
            {
                return false;
            }

            if (name!.IndexOf("..", StringComparison.Ordinal) >= 0)
            {
                return false;
            }

            if (name.IndexOfAny(DisallowedNameChars) >= 0)
            {
                return false;
            }

            if (!name.All(c => char.IsLetterOrDigit(c) || c == '.' || c == '_' || c == '-'))
            {
                return false;
            }

            // Reject Windows reserved device names (base name, ignoring any extension): CON, NUL, COM1, ...
            var dotIndex = name.IndexOf('.');
            var baseName = dotIndex >= 0 ? name.Substring(0, dotIndex) : name;
            return !ReservedDeviceNames.Contains(baseName);
        }

        public static BimExportArtifactPaths ResolveBundlePaths(string directory, string name)
        {
            return new BimExportArtifactPaths
            {
                Model3dm = Path.Combine(directory, name + ".3dm"),
                Sidecar = Path.Combine(directory, name + ".sidecar.json"),
                Validation = Path.Combine(directory, name + ".validation.json"),
            };
        }

        public static bool EscapesIntendedDirectory(string filePath, string directory)
        {
            var fullFile = Path.GetFullPath(filePath);
            var fullDir = Path.GetFullPath(directory);
            var normalizedDir = fullDir.TrimEnd(Path.DirectorySeparatorChar) + Path.DirectorySeparatorChar;
            return !fullFile.StartsWith(normalizedDir, StringComparison.OrdinalIgnoreCase);
        }

        // net48 has no Path.IsPathFullyQualified, so check manually:
        //  - must be drive-rooted "X:\..." or "X:/..." (NOT drive-relative "X:foo", which
        //    Path.IsPathRooted accepts), and
        //  - must NOT be a UNC path "\\server\share" (ambiguous local target).
        private static bool IsFullyQualifiedLocalDirectory(string? directory)
        {
            if (string.IsNullOrWhiteSpace(directory))
            {
                return false;
            }

            var dir = directory!;
            if (dir.StartsWith(@"\\", StringComparison.Ordinal) || dir.StartsWith("//", StringComparison.Ordinal))
            {
                return false; // UNC
            }

            return dir.Length >= 3 &&
                ((dir[0] >= 'A' && dir[0] <= 'Z') || (dir[0] >= 'a' && dir[0] <= 'z')) &&
                dir[1] == ':' &&
                (dir[2] == '\\' || dir[2] == '/');
        }

        private static BimValidationResult Fail(string message)
        {
            return new BimValidationResult
            {
                Success = false,
                ErrorCode = BimErrorCode.OutputPathInvalid,
                Message = message
            };
        }
    }
}
```

- [ ] **Step 4: Upgrade `Validate()` to delegate to the policy**

Now that `BimExportPathPolicy` exists, replace the local output-shape check in
`BimExportElementsRequest.Validate()` (`src/Rook/Bim/BimContracts.cs`) so the request reuses the
full policy. Replace this block:

```csharp
            // Task 1 does ONLY local output-shape validation so it is independently green.
            // Task 2 swaps this for the full BimExportPathPolicy.ValidateRequestShape.
            if (Output == null ||
                string.IsNullOrWhiteSpace(Output.Directory) ||
                string.IsNullOrWhiteSpace(Output.Name))
            {
                return Fail(
                    BimErrorCode.OutputPathInvalid,
                    "export-elements requires output.directory and output.name.");
            }

            return BimValidationResult.Ok;
```

with:

```csharp
            var outputValidation = BimExportPathPolicy.ValidateRequestShape(Output);
            if (!outputValidation.Success)
            {
                return outputValidation;
            }

            return BimValidationResult.Ok;
```

The Task 1 tests still pass (`ValidateRequestShape` returns `OutputPathInvalid` for a missing
directory/name, the same code Task 1 asserted).

- [ ] **Step 5: Run tests to verify they pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "RookBimExportPathPolicyTests|RookBimExportContractsTests"`
Expected: PASS (all of Task 1 + Task 2).

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Bim/BimExportPathPolicy.cs src/Rook/Bim/BimContracts.cs src/Rook.Tests/Bim/RookBimExportPathPolicyTests.cs
git commit -m "feat(bim): pure path-safety policy + units validation for export bundles"
```

---

## Task 3: Interface + Unavailable runtime

**Files:**
- Modify: `src/Rook/Bim/IRookBimRuntime.cs`
- Modify: `src/Rook/Bim/RookBimUnavailableRuntime.cs`
- Test: `src/Rook.Tests/Bim/RookBimUnavailableExportTests.cs`

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Bim/RookBimUnavailableExportTests.cs`:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public class RookBimUnavailableExportTests
    {
        [Fact]
        public void ExportElements_ReturnsUnavailable()
        {
            var runtime = new RookBimUnavailableRuntime("rookbim_unavailable", "nope");
            var response = runtime.ExportElements(new BimExportElementsRequest());
            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Equal(503, response.HttpStatus);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookBimUnavailableExportTests`
Expected: FAIL — `IRookBimRuntime` has no `ExportElements`.

- [ ] **Step 3: Add to the interface**

In `src/Rook/Bim/IRookBimRuntime.cs`, add after `ClearSelection()`:

```csharp
        BimApiResponse ExportElements(BimExportElementsRequest request);
```

- [ ] **Step 4: Implement on the Unavailable runtime**

In `src/Rook/Bim/RookBimUnavailableRuntime.cs`, add after `ClearSelection()`:

```csharp
        public BimApiResponse ExportElements(BimExportElementsRequest request)
        {
            return Unavailable();
        }
```

- [ ] **Step 5: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookBimUnavailableExportTests`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Bim/IRookBimRuntime.cs src/Rook/Bim/RookBimUnavailableRuntime.cs src/Rook.Tests/Bim/RookBimUnavailableExportTests.cs
git commit -m "feat(bim): add ExportElements to runtime interface + Unavailable impl"
```

---

## Task 4: `RevitGeometryConverter` (reflection Brep → mesh → bbox)

**Files:**
- Create: `src/RookBim/Revit/RevitGeometryConverter.cs`
- Test: `src/RookBim.Tests/RookBimExportSourceTests.cs` (created here; extended by later tasks)

This is Revit/RhinoCommon-coupled — verified by **source-text tests** in CI (the established `RookBimModuleSourceTests` pattern) and exercised end-to-end by the gated live script (Task 11).

- [ ] **Step 1: Write the failing test**

Create `src/RookBim.Tests/RookBimExportSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace RookBim.Tests
{
    public class RookBimExportSourceTests
    {
        private static readonly string RepoRoot = FindRepoRoot();

        [Fact]
        public void GeometryConverter_UsesReflectionBrepThenMeshThenBboxFallback()
        {
            var src = Read("src/RookBim/Revit/RevitGeometryConverter.cs");

            // Reflection Brep path — no hard RhinoInside.Revit reference.
            Assert.Contains("RhinoInside.Revit", src);
            Assert.Contains("GetMethod", src);
            Assert.DoesNotContain("using RhinoInside", src);

            // Mesh fallback via Revit tessellation.
            Assert.Contains("Triangulate", src);
            Assert.Contains("Rhino.Geometry.Mesh", src);

            // Quality vocabulary — no "exact" claims.
            Assert.Contains("\"converted_brep\"", src);
            Assert.Contains("\"mesh_fallback\"", src);
            Assert.Contains("\"bbox_only\"", src);
            Assert.Contains("\"failed\"", src);
            Assert.DoesNotContain("exact_brep", src);

            // Opt-in bbox proxy.
            Assert.Contains("allowBboxProxy", src);

            // Read-only — no Revit transaction.
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

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RookBimExportSourceTests`
Expected: FAIL — `RevitGeometryConverter.cs` does not exist (FileNotFound).

- [ ] **Step 3: Implement the converter**

Create `src/RookBim/Revit/RevitGeometryConverter.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using Autodesk.Revit.DB;

namespace RookBim.Revit
{
    /// <summary>
    /// Converts a Revit element's geometry to RhinoCommon for in-memory File3dm export.
    /// Path: in-process Rhino.Inside.Revit Brep converter (reflection) -> Face.Triangulate mesh
    /// -> bbox proxy (opt-in). Read-only: never opens a Revit Transaction.
    /// </summary>
    internal sealed class RevitGeometryConverter
    {
        // converted_brep: a non-tessellated Revit solid converted to a Rhino Brep via the
        // Rhino.Inside.Revit converter. NOT a geometric-exactness claim.
        public const string QualityConvertedBrep = "converted_brep";
        public const string QualityMeshFallback = "mesh_fallback";
        public const string QualityBboxOnly = "bbox_only";
        public const string QualityFailed = "failed";

        public const string RepresentationBrep = "brep";
        public const string RepresentationMesh = "mesh";
        public const string RepresentationBboxProxy = "bbox_proxy";

        private const string RhinoInsideAssemblyName = "RhinoInside.Revit";
        private const double FeetToMeters = 0.3048;

        private readonly double unitScaleFromFeet;
        private readonly MethodInfo? solidToBrep;

        public RevitGeometryConverter(double unitScaleFromFeet)
        {
            this.unitScaleFromFeet = unitScaleFromFeet;
            this.solidToBrep = ResolveSolidToBrepConverter();
        }

        public static double ScaleFromFeet(string targetUnits)
        {
            switch ((targetUnits ?? "meters").Trim().ToLowerInvariant())
            {
                case "millimeters":
                case "mm":
                    return FeetToMeters * 1000.0;
                case "centimeters":
                case "cm":
                    return FeetToMeters * 100.0;
                case "feet":
                case "ft":
                    return 1.0;
                case "inches":
                case "in":
                    return 12.0;
                case "meters":
                case "m":
                default:
                    return FeetToMeters;
            }
        }

        public RevitGeometryConversion Convert(Element element, bool allowBboxProxy)
        {
            var options = new Options
            {
                ComputeReferences = false,
                IncludeNonVisibleObjects = false,
                DetailLevel = ViewDetailLevel.Fine
            };

            var solids = CollectSolids(element.get_Geometry(options)).ToList();

            // 1. Brep path (reflection).
            if (solidToBrep != null)
            {
                var breps = new List<Rhino.Geometry.Brep>();
                foreach (var solid in solids)
                {
                    var brep = TryConvertSolidToBrep(solid);
                    if (brep != null)
                    {
                        Scale(brep);
                        breps.Add(brep);
                    }
                }

                if (breps.Count > 0)
                {
                    return RevitGeometryConversion.Brep(breps);
                }
            }

            // 2. Mesh fallback (Face.Triangulate).
            var mesh = TryTessellate(solids);
            if (mesh != null && mesh.Faces.Count > 0)
            {
                Scale(mesh);
                return RevitGeometryConversion.Mesh(
                    mesh,
                    solidToBrep == null ? "rhino_inside_converter_unavailable" : "brep_conversion_failed");
            }

            // 3. Bbox proxy (opt-in).
            if (allowBboxProxy)
            {
                var box = TryBoundingBox(element);
                if (box != null)
                {
                    return RevitGeometryConversion.BboxProxy(box);
                }
            }

            return RevitGeometryConversion.Failed(
                allowBboxProxy ? "no_geometry_extractable" : "no_brep_or_mesh_bbox_proxy_disabled");
        }

        private static IEnumerable<Solid> CollectSolids(GeometryElement? geometry)
        {
            if (geometry == null)
            {
                yield break;
            }

            foreach (var obj in geometry)
            {
                if (obj is Solid solid && solid.Volume > 0 && solid.Faces.Size > 0)
                {
                    yield return solid;
                }
                else if (obj is GeometryInstance instance)
                {
                    foreach (var inner in CollectSolids(instance.GetInstanceGeometry()))
                    {
                        yield return inner;
                    }
                }
            }
        }

        private Rhino.Geometry.Brep? TryConvertSolidToBrep(Solid solid)
        {
            try
            {
                return solidToBrep!.Invoke(null, new object[] { solid }) as Rhino.Geometry.Brep;
            }
            catch (Exception)
            {
                return null;
            }
        }

        private static Rhino.Geometry.Mesh? TryTessellate(IEnumerable<Solid> solids)
        {
            var merged = new Rhino.Geometry.Mesh();
            foreach (var solid in solids)
            {
                foreach (Face face in solid.Faces)
                {
                    Mesh triangulated;
                    try
                    {
                        triangulated = face.Triangulate();
                    }
                    catch (Exception)
                    {
                        continue;
                    }

                    if (triangulated == null)
                    {
                        continue;
                    }

                    var baseIndex = merged.Vertices.Count;
                    for (var v = 0; v < triangulated.Vertices.Count; v++)
                    {
                        var p = triangulated.get_Vertex(v);
                        merged.Vertices.Add(p.X, p.Y, p.Z);
                    }

                    for (var t = 0; t < triangulated.NumTriangles; t++)
                    {
                        var tri = triangulated.get_Triangle(t);
                        merged.Faces.AddFace(
                            baseIndex + (int)tri[0],
                            baseIndex + (int)tri[1],
                            baseIndex + (int)tri[2]);
                    }
                }
            }

            if (merged.Vertices.Count == 0)
            {
                return null;
            }

            merged.Normals.ComputeNormals();
            merged.Compact();
            return merged;
        }

        private Rhino.Geometry.Box? TryBoundingBox(Element element)
        {
            var bb = element.get_BoundingBox(null);
            if (bb == null)
            {
                return null;
            }

            var min = new Rhino.Geometry.Point3d(
                bb.Min.X * unitScaleFromFeet, bb.Min.Y * unitScaleFromFeet, bb.Min.Z * unitScaleFromFeet);
            var max = new Rhino.Geometry.Point3d(
                bb.Max.X * unitScaleFromFeet, bb.Max.Y * unitScaleFromFeet, bb.Max.Z * unitScaleFromFeet);
            var bbox = new Rhino.Geometry.BoundingBox(min, max);
            return new Rhino.Geometry.Box(bbox);
        }

        private void Scale(Rhino.Geometry.GeometryBase geometry)
        {
            if (Math.Abs(unitScaleFromFeet - 1.0) < 1e-12)
            {
                return;
            }

            var xform = Rhino.Geometry.Transform.Scale(Rhino.Geometry.Point3d.Origin, unitScaleFromFeet);
            geometry.Transform(xform);
        }

        private static MethodInfo? ResolveSolidToBrepConverter()
        {
            try
            {
                var assembly = AppDomain.CurrentDomain
                    .GetAssemblies()
                    .FirstOrDefault(candidate =>
                        string.Equals(
                            candidate.GetName().Name,
                            RhinoInsideAssemblyName,
                            StringComparison.OrdinalIgnoreCase));
                if (assembly == null)
                {
                    return null;
                }

                // RhinoInside.Revit.Convert.Geometry.GeometryDecoder.ToBrep(this Solid) -> Brep
                var decoder = assembly.GetType(
                    "RhinoInside.Revit.Convert.Geometry.GeometryDecoder",
                    throwOnError: false);

                return decoder?
                    .GetMethods(BindingFlags.Public | BindingFlags.Static)
                    .FirstOrDefault(m =>
                        m.Name == "ToBrep" &&
                        m.GetParameters().Length == 1 &&
                        m.GetParameters()[0].ParameterType == typeof(Solid) &&
                        typeof(Rhino.Geometry.Brep).IsAssignableFrom(m.ReturnType));
            }
            catch (Exception)
            {
                return null;
            }
        }
    }

    internal sealed class RevitGeometryConversion
    {
        private RevitGeometryConversion() { }

        public string Representation { get; private set; } = RevitGeometryConverter.RepresentationBrep;

        public string Quality { get; private set; } = RevitGeometryConverter.QualityFailed;

        public string? FallbackReason { get; private set; }

        public IReadOnlyList<Rhino.Geometry.Brep> Breps { get; private set; } = Array.Empty<Rhino.Geometry.Brep>();

        public Rhino.Geometry.Mesh? Mesh { get; private set; }

        public Rhino.Geometry.Box? Bbox { get; private set; }

        public bool HasGeometry
        {
            get { return Breps.Count > 0 || Mesh != null || Bbox != null; }
        }

        public static RevitGeometryConversion Brep(IReadOnlyList<Rhino.Geometry.Brep> breps)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationBrep,
                Quality = RevitGeometryConverter.QualityConvertedBrep,
                FallbackReason = null,
                Breps = breps
            };
        }

        public static RevitGeometryConversion Mesh(Rhino.Geometry.Mesh mesh, string fallbackReason)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationMesh,
                Quality = RevitGeometryConverter.QualityMeshFallback,
                FallbackReason = fallbackReason,
                Mesh = mesh
            };
        }

        public static RevitGeometryConversion BboxProxy(Rhino.Geometry.Box box)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationBboxProxy,
                Quality = RevitGeometryConverter.QualityBboxOnly,
                FallbackReason = "geometry_unconvertible_bbox_proxy",
                Bbox = box
            };
        }

        public static RevitGeometryConversion Failed(string reason)
        {
            return new RevitGeometryConversion
            {
                Representation = RevitGeometryConverter.RepresentationBboxProxy,
                Quality = RevitGeometryConverter.QualityFailed,
                FallbackReason = reason
            };
        }
    }
}
```

- [ ] **Step 4: Add the RhinoCommon reference to `RookBim.csproj`**

This is the **first** RookBim code to use RhinoCommon (`Rhino.Geometry.*`, `Rhino.FileIO.File3dm`).
RhinoCommon reaches RookBim today only as a transitive `<Reference>` of `Rook.csproj`, and raw
assembly `<Reference>`s do **not** flow transitively through a `ProjectReference` — so RookBim must
reference RhinoCommon directly or it will not compile. In `src/RookBim/RookBim.csproj`, add a
`RhinoSystemDir` default and a `RhinoCommon` reference (verified present at
`C:\Program Files\Rhino 8\System\RhinoCommon.dll`). Add inside the existing
`<PropertyGroup>` that defines `RevitInstallDir`:

```xml
    <RhinoSystemDir Condition="'$(RhinoSystemDir)' == ''">$(ProgramFiles)\Rhino 8\System</RhinoSystemDir>
```

and add to the `<ItemGroup>` that holds the Revit references:

```xml
    <Reference Include="RhinoCommon">
      <HintPath>$(RhinoSystemDir)\RhinoCommon.dll</HintPath>
      <Private>false</Private>
    </Reference>
```

(This does not break `RookBimProject_TargetsNet48AndReferencesRevitApisPrivately` — that test asserts
the two Revit references with `Private=false` and a single `ProjectReference`; a third assembly
`<Reference>` for RhinoCommon is fine, and RhinoCommon ≠ RhinoInside.Revit.)

- [ ] **Step 5: Run the source-text test to verify it passes**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RookBimExportSourceTests`
Expected: PASS.

- [ ] **Step 6: BUILD GATE — compile the real Revit/RhinoCommon code**

The source-text test does NOT compile `RevitGeometryConverter.cs` (`RookBim.Tests` has no
`ProjectReference` to `RookBim`). Compile the actual assembly to catch Revit/RhinoCommon API
signature mismatches:

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds. If the RhinoInside `GeometryDecoder.ToBrep`/`Face.Triangulate`/
`Mesh.get_Triangle` signatures differ on the installed SDKs, fix them here until the build is green.

- [ ] **Step 7: Commit**

```bash
git add src/RookBim/Revit/RevitGeometryConverter.cs src/RookBim/RookBim.csproj src/RookBim.Tests/RookBimExportSourceTests.cs
git commit -m "feat(rookbim): Revit->Rhino geometry converter (brep/mesh/bbox)"
```

---

## Task 5: `RevitLabelExtractor` (provenance-tagged labels)

**Files:**
- Create: `src/RookBim/Revit/RevitLabelExtractor.cs`
- Test: `src/RookBim.Tests/RookBimExportSourceTests.cs` (add a method)

- [ ] **Step 1: Add the failing test**

Add to `src/RookBim.Tests/RookBimExportSourceTests.cs` (inside the class):

```csharp
        [Fact]
        public void LabelExtractor_EmitsProvenanceTaggedLabels()
        {
            var src = Read("src/RookBim/Revit/RevitLabelExtractor.cs");

            Assert.Contains("value", src);
            Assert.Contains("source", src);
            Assert.Contains("confidence", src);
            Assert.Contains("missingReason", src);

            Assert.Contains("\"revit_api\"", src);
            Assert.Contains("\"parameter\"", src);
            Assert.Contains("\"derived\"", src);
            Assert.Contains("\"unavailable\"", src);

            // Relationship labels.
            Assert.Contains("LevelId", src);
            Assert.Contains("HostId", src);
            Assert.Contains("ContainingRoom", src);
            Assert.Contains("ContainingSpace", src);

            Assert.DoesNotContain("Transaction", src);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter LabelExtractor_EmitsProvenanceTaggedLabels`
Expected: FAIL — file missing.

- [ ] **Step 3: Implement the extractor**

Create `src/RookBim/Revit/RevitLabelExtractor.cs`:

```csharp
using System;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;
using Autodesk.Revit.DB.Mechanical;

namespace RookBim.Revit
{
    /// <summary>Extracts provenance-tagged semantic labels for an element (read-only).</summary>
    internal sealed class RevitLabelExtractor
    {
        public RevitElementLabels Extract(Document document, Element element)
        {
            return new RevitElementLabels
            {
                Level = ExtractLevel(document, element),
                HostId = ExtractHost(document, element),
                ContainingRoom = ExtractRoom(element),
                ContainingSpace = ExtractSpace(element)
            };
        }

        private static BimSemanticLabel ExtractLevel(Document document, Element element)
        {
            var levelId = element.LevelId;
            if (levelId != null && levelId != ElementId.InvalidElementId)
            {
                var level = document.GetElement(levelId) as Level;
                if (level != null)
                {
                    return BimSemanticLabel.Present(level.Name, "revit_api", "high");
                }
            }

            var param = element.get_Parameter(BuiltInParameter.SCHEDULE_LEVEL_PARAM)
                ?? element.get_Parameter(BuiltInParameter.FAMILY_LEVEL_PARAM);
            var valueString = param?.AsValueString();
            if (!string.IsNullOrWhiteSpace(valueString))
            {
                return BimSemanticLabel.Present(valueString!, "parameter", "medium");
            }

            return BimSemanticLabel.Missing("no_level_association");
        }

        private static BimSemanticLabel ExtractHost(Document document, Element element)
        {
            if (element is FamilyInstance instance && instance.Host != null)
            {
                return BimSemanticLabel.Present(instance.Host.UniqueId, "revit_api", "high");
            }

            return BimSemanticLabel.Missing("element_is_not_hosted");
        }

        private static BimSemanticLabel ExtractRoom(Element element)
        {
            try
            {
                if (element is FamilyInstance instance)
                {
                    var room = instance.Room;
                    if (room != null)
                    {
                        return BimSemanticLabel.Present(room.UniqueId, "revit_api", "high");
                    }
                }
            }
            catch (Exception)
            {
                return BimSemanticLabel.Missing("room_lookup_unavailable");
            }

            return BimSemanticLabel.Missing("no_room_association");
        }

        private static BimSemanticLabel ExtractSpace(Element element)
        {
            try
            {
                if (element is FamilyInstance instance)
                {
                    var space = instance.Space;
                    if (space != null)
                    {
                        return BimSemanticLabel.Present(space.UniqueId, "revit_api", "high");
                    }
                }
            }
            catch (Exception)
            {
                return BimSemanticLabel.Missing("space_lookup_unavailable");
            }

            return BimSemanticLabel.Missing("no_space_association");
        }
    }

    internal sealed class RevitElementLabels
    {
        public BimSemanticLabel Level { get; set; } = BimSemanticLabel.Missing("not_extracted");

        public BimSemanticLabel HostId { get; set; } = BimSemanticLabel.Missing("not_extracted");

        public BimSemanticLabel ContainingRoom { get; set; } = BimSemanticLabel.Missing("not_extracted");

        public BimSemanticLabel ContainingSpace { get; set; } = BimSemanticLabel.Missing("not_extracted");
    }

    /// <summary>A label that is honest about provenance and absence.</summary>
    internal sealed class BimSemanticLabel
    {
        public string? Value { get; private set; }

        public string Source { get; private set; } = "unavailable";

        public string? Confidence { get; private set; }

        public string? MissingReason { get; private set; }

        public static BimSemanticLabel Present(string value, string source, string confidence)
        {
            return new BimSemanticLabel
            {
                Value = value,
                Source = source,
                Confidence = confidence,
                MissingReason = null
            };
        }

        public static BimSemanticLabel Missing(string reason)
        {
            return new BimSemanticLabel
            {
                Value = null,
                Source = "unavailable",
                Confidence = null,
                MissingReason = reason
            };
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter LabelExtractor_EmitsProvenanceTaggedLabels`
Expected: PASS.

- [ ] **Step 5: BUILD GATE — compile the real code**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds. Fix any Revit API mismatches (`element.LevelId`, `FamilyInstance.Room`/`.Space`, `BuiltInParameter` names, `DB.Architecture`/`DB.Mechanical` namespaces) until green.

- [ ] **Step 6: Commit**

```bash
git add src/RookBim/Revit/RevitLabelExtractor.cs src/RookBim.Tests/RookBimExportSourceTests.cs
git commit -m "feat(rookbim): provenance-tagged label extractor (level/host/room/space)"
```

---

## Task 6: `RevitRoomExporter` (typed reference, per-room degrade)

**Files:**
- Create: `src/RookBim/Revit/RevitRoomExporter.cs`
- Test: `src/RookBim.Tests/RookBimExportSourceTests.cs` (add a method)

- [ ] **Step 1: Add the failing test**

Add to `src/RookBim.Tests/RookBimExportSourceTests.cs`:

```csharp
        [Fact]
        public void RoomExporter_TypesRoomsSeparatelyAndDegradesPerRoom()
        {
            var src = Read("src/RookBim/Revit/RevitRoomExporter.cs");

            // Per-room degrade ladder.
            Assert.Contains("\"room_volume_brep\"", src);
            Assert.Contains("\"room_mesh\"", src);
            Assert.Contains("\"boundary_2d\"", src);
            Assert.Contains("\"label_only\"", src);

            // Separate reference layer + flag.
            Assert.Contains("RookBim::Rooms", src);
            Assert.Contains("referenceGeometry", src);

            // Read-only spatial geometry.
            Assert.Contains("SpatialElementGeometryCalculator", src);
            Assert.DoesNotContain("Transaction", src);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RoomExporter_TypesRoomsSeparatelyAndDegradesPerRoom`
Expected: FAIL — file missing.

- [ ] **Step 3: Implement the room exporter**

Create `src/RookBim/Revit/RevitRoomExporter.cs`:

```csharp
using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Architecture;

namespace RookBim.Revit
{
    /// <summary>
    /// Exports rooms/spaces as typed spatial-structure REFERENCE geometry on a dedicated layer.
    /// Degrades per room: room_volume_brep -> room_mesh -> boundary_2d -> label_only. A room whose
    /// volume cannot be extracted is NOT an export failure as long as its label record is emitted.
    /// Read-only.
    /// </summary>
    internal sealed class RevitRoomExporter
    {
        public const string RoomsLayer = "RookBim::Rooms";

        public const string RepVolumeBrep = "room_volume_brep";
        public const string RepMesh = "room_mesh";
        public const string RepBoundary2d = "boundary_2d";
        public const string RepLabelOnly = "label_only";

        private readonly double unitScaleFromFeet;

        public RevitRoomExporter(double unitScaleFromFeet)
        {
            this.unitScaleFromFeet = unitScaleFromFeet;
        }

        public IReadOnlyList<RevitRoomExport> ExportRooms(Document document)
        {
            var results = new List<RevitRoomExport>();
            var collector = new FilteredElementCollector(document)
                .OfClass(typeof(SpatialElement))
                .WhereElementIsNotElementType();

            foreach (var element in collector)
            {
                if (element is Room room)
                {
                    results.Add(ExportRoom(room));
                }
            }

            return results;
        }

        private RevitRoomExport ExportRoom(Room room)
        {
            var export = new RevitRoomExport
            {
                UniqueId = room.UniqueId,
                Number = room.Number,
                Name = room.Name,
                Representation = RepLabelOnly,
                ReferenceGeometry = true
            };

            try
            {
                var options = new SpatialElementBoundaryOptions();
                var calculator = new SpatialElementGeometryCalculator(room.Document, options);
                var solidResult = calculator.CalculateSpatialElementGeometry(room);
                var solid = solidResult?.GetGeometry();
                if (solid != null && solid.Volume > 0)
                {
                    export.Solid = solid;
                    export.Representation = RepMesh; // assembled to mesh/brep in the export service
                    return export;
                }
            }
            catch (Exception)
            {
                // fall through to boundary / label-only
            }

            if (TryBoundaryLoops(room))
            {
                export.Representation = RepBoundary2d;
            }

            return export;
        }

        private bool TryBoundaryLoops(Room room)
        {
            try
            {
                var loops = room.GetBoundarySegments(new SpatialElementBoundaryOptions());
                return loops != null && loops.Count > 0;
            }
            catch (Exception)
            {
                return false;
            }
        }
    }

    internal sealed class RevitRoomExport
    {
        public string UniqueId { get; set; } = string.Empty;

        public string? Number { get; set; }

        public string? Name { get; set; }

        public string Representation { get; set; } = RevitRoomExporter.RepLabelOnly;

        public bool ReferenceGeometry { get; set; } = true;

        public Solid? Solid { get; set; }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter RoomExporter_TypesRoomsSeparatelyAndDegradesPerRoom`
Expected: PASS.

- [ ] **Step 5: BUILD GATE — compile the real code**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds. Fix any mismatches (`SpatialElementGeometryCalculator`, `SpatialElementGeometryResults.GetGeometry()`, `Room.GetBoundarySegments`, `FilteredElementCollector.OfClass(typeof(SpatialElement))`) until green.

- [ ] **Step 6: Commit**

```bash
git add src/RookBim/Revit/RevitRoomExporter.cs src/RookBim.Tests/RookBimExportSourceTests.cs
git commit -m "feat(rookbim): room/space reference exporter with per-room degrade"
```

---

## Task 7: `RevitExportService` (orchestration + File3dm + sidecar + validation + verification)

**Files:**
- Create: `src/RookBim/Revit/RevitExportService.cs`
- Test: `src/RookBim.Tests/RookBimExportSourceTests.cs` (add a method)

- [ ] **Step 1: Add the failing test**

Add to `src/RookBim.Tests/RookBimExportSourceTests.cs`:

```csharp
        [Fact]
        public void ExportService_FreezesIdentitiesGuardsTruncationWritesBundleAndVerifies()
        {
            var src = Read("src/RookBim/Revit/RevitExportService.cs");

            // Strict one-of already validated upstream; service resolves both selector + identities.
            Assert.Contains("RevitQueryService", src);
            Assert.Contains("RevitIdentitySerializer.Resolve", src);

            // No-silent-truncation guard.
            Assert.Contains("AllowTruncated", src);
            Assert.Contains("BimErrorCode.QueryTruncated", src);

            // Path safety BEFORE writing.
            Assert.Contains("BimExportPathPolicy.ValidateRequestShape", src);
            Assert.Contains("BimExportPathPolicy.ResolveBundlePaths", src);
            Assert.Contains("BimExportPathPolicy.EscapesIntendedDirectory", src);
            Assert.Contains("Overwrite", src);
            Assert.Contains("BimErrorCode.OutputPathInvalid", src);

            // Three-file bundle.
            Assert.Contains(".3dm", src);
            Assert.Contains(".sidecar.json", src);
            Assert.Contains(".validation.json", src);
            Assert.Contains("File3dm", src);

            // Join-key user strings.
            Assert.Contains("revit.uniqueId", src);
            Assert.Contains("rook.source", src);
            Assert.Contains("RookBim::Model", src);

            // Bijection verification + NoExportableGeometry.
            Assert.Contains("BimExportVerification", src);
            Assert.Contains("BimErrorCode.NoExportableGeometry", src);

            // Read-only.
            Assert.DoesNotContain("Transaction", src);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter ExportService_FreezesIdentitiesGuardsTruncationWritesBundleAndVerifies`
Expected: FAIL — file missing.

- [ ] **Step 3: Implement the export service**

Create `src/RookBim/Revit/RevitExportService.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    /// <summary>
    /// Orchestrates a read-only Revit -> Rhino export: resolve the element set, freeze identities,
    /// convert geometry, assemble an in-memory File3dm + sidecar + validation, write the bundle
    /// path-safely, and verify the Rhino-object <-> sidecar-record bijection. Never mutates the
    /// active Rhino document or opens a Revit Transaction.
    /// </summary>
    internal sealed class RevitExportService
    {
        private const string ModelLayer = "RookBim::Model";

        private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            WriteIndented = true,
            DefaultIgnoreCondition = JsonIgnoreCondition.Never
        };

        private readonly RevitQueryService query = new RevitQueryService();
        private readonly RevitLabelExtractor labels = new RevitLabelExtractor();

        public BimApiResponse Export(Document document, View? activeView, BimExportElementsRequest request)
        {
            // 1. Output-path safety (revalidate at the service boundary).
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

            // 2. Resolve the element set + freeze identities.
            var resolution = ResolveElements(document, activeView, request);
            if (resolution.Failure != null)
            {
                return resolution.Failure;
            }

            var requested = resolution.Elements.Count;
            var scale = RevitGeometryConverter.ScaleFromFeet(request.Output.Units);
            var converter = new RevitGeometryConverter(scale);

            // 3. Build the in-memory File3dm + element records.
            var file = new Rhino.FileIO.File3dm();
            file.Settings.ModelUnitSystem = MapUnits(request.Output.Units);
            var modelLayerIndex = EnsureLayer(file, ModelLayer);

            var elementRecords = new List<object>();
            var counts = new BimExportCounts { Requested = requested, Resolved = requested, Truncated = resolution.Truncated };
            var exportedKeys = new HashSet<string>(StringComparer.Ordinal);

            foreach (var element in resolution.Elements)
            {
                var conversion = converter.Convert(element, request.AllowBboxProxy);
                var key = element.UniqueId;
                var labelSet = labels.Extract(document, element);

                if (conversion.HasGeometry)
                {
                    AddGeometry(file, modelLayerIndex, element, conversion);
                    exportedKeys.Add(key);
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
                }

                elementRecords.Add(BuildElementRecord(document, element, conversion, labelSet));
            }

            // 4. Rooms (typed separately).
            var roomRecords = new List<object>();
            if (request.EffectiveRooms != BimRoomsMode.Exclude)
            {
                var includeGeometry = request.EffectiveRooms == BimRoomsMode.Both;
                var roomLayerIndex = EnsureLayer(file, RevitRoomExporter.RoomsLayer);
                var rooms = new RevitRoomExporter(scale).ExportRooms(document);
                counts.Rooms = rooms.Count;
                foreach (var room in rooms)
                {
                    var rep = MaterializeRoom(file, roomLayerIndex, room, scale, includeGeometry);
                    roomRecords.Add(new
                    {
                        roomId = room.UniqueId,
                        uniqueId = room.UniqueId,
                        number = room.Number,
                        name = room.Name,
                        geometryRepresentation = rep,
                        referenceGeometry = true
                    });
                }
            }

            // 5. NoExportableGeometry guard.
            if (requested > 0 && counts.ExportedBrep + counts.ExportedMesh + counts.ExportedBboxProxy == 0)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoExportableGeometry,
                    "No element produced exportable geometry (retry with allowBboxProxy=true or a different selection).",
                    422);
            }

            // 6. Verify the bijection BEFORE writing.
            var verification = VerifyBijection(file, exportedKeys);

            // 7. Assemble sidecar + validation; write all three path-safely.
            var sidecar = BuildSidecar(document, request, resolution, elementRecords, roomRecords);
            var sidecarJson = JsonSerializer.Serialize(sidecar, JsonOptions);

            try
            {
                if (!file.Write(paths.Model3dm, 7))
                {
                    return CleanupAndFail(paths, "Failed to write the .3dm bundle artifact.");
                }

                File.WriteAllText(paths.Sidecar, sidecarJson, new UTF8Encoding(false));

                var validation = BuildValidation(document, counts, scale, request.Output.Units, paths, sidecarJson);
                File.WriteAllText(paths.Validation, JsonSerializer.Serialize(validation, JsonOptions), new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                return CleanupAndFail(paths, $"Bundle write failed: {ex.GetType().Name}: {ex.Message}");
            }

            if (!verification.Ok)
            {
                CleanupBundle(paths);
                var failure = BimApiResponse.Fail(
                    BimErrorCode.ExportFailed, "Export bijection verification failed; bundle is not a trustworthy fixture.", 500);
                failure.Data = new { verification };
                return failure;
            }

            return BimApiResponse.Ok(new BimExportResult
            {
                Paths = paths,
                Counts = counts,
                Verification = verification,
                SourceUnits = "feet",
                TargetUnits = request.Output.Units,
                UnitScaleFactor = scale
            });
        }

        private ElementResolution ResolveElements(Document document, View? activeView, BimExportElementsRequest request)
        {
            if (request.HasIdentities)
            {
                var elements = new List<Element>();
                foreach (var identity in request.Identities!)
                {
                    var resolved = RevitIdentitySerializer.Resolve(document, identity);
                    if (!resolved.Success)
                    {
                        return ElementResolution.Fail(BimApiResponse.Fail(
                            resolved.ErrorCode,
                            resolved.Message ?? "An element identity did not resolve.",
                            404));
                    }

                    elements.Add(resolved.Element!);
                }

                return ElementResolution.Ok(elements, truncated: false);
            }

            var queryResponse = query.Query(document, activeView, request.Selector!);
            if (!queryResponse.Success || !(queryResponse.Data is BimQueryElementsResult queryResult))
            {
                return ElementResolution.Fail(queryResponse);
            }

            if (queryResult.Query.Truncated && !request.AllowTruncated)
            {
                var failure = BimApiResponse.Fail(
                    BimErrorCode.QueryTruncated,
                    $"Selector resolved a truncated set ({queryResult.Query.Returned} of more than {queryResult.Query.Limit}); " +
                    "set allowTruncated=true to export the capped set.",
                    409);
                failure.Data = new { returned = queryResult.Query.Returned, limit = queryResult.Query.Limit };
                return ElementResolution.Fail(failure);
            }

            var resolvedElements = queryResult.Elements
                .Select(summary => RevitIdentitySerializer.Resolve(document, summary.Identity))
                .Where(r => r.Success)
                .Select(r => r.Element!)
                .ToList();

            return ElementResolution.Ok(resolvedElements, queryResult.Query.Truncated);
        }

        private object BuildElementRecord(Document document, Element element, RevitGeometryConversion conversion, RevitElementLabels labelSet)
        {
            var bb = element.get_BoundingBox(null);
            return new
            {
                identity = RevitIdentitySerializer.ElementIdentity(element),
                category = element.Category?.Name,
                family = (document.GetElement(element.GetTypeId()) as ElementType)?.FamilyName,
                type = (document.GetElement(element.GetTypeId()) as ElementType)?.Name,
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

        private static object Label(BimSemanticLabel label)
        {
            return new
            {
                value = label.Value,
                source = label.Source,
                confidence = label.Confidence,
                missingReason = label.MissingReason
            };
        }

        private object BuildSidecar(
            Document document,
            BimExportElementsRequest request,
            ElementResolution resolution,
            List<object> elementRecords,
            List<object> roomRecords)
        {
            return new
            {
                schemaVersion = 1,
                document = RevitIdentitySerializer.DocumentIdentity(document),
                request = new
                {
                    hasSelector = request.HasSelector,
                    hasIdentities = request.HasIdentities,
                    rooms = request.EffectiveRooms.ToString(),
                    allowTruncated = request.AllowTruncated,
                    allowBboxProxy = request.AllowBboxProxy
                },
                resolved = new
                {
                    count = resolution.Elements.Count,
                    truncated = resolution.Truncated,
                    identities = resolution.Elements.Select(RevitIdentitySerializer.ElementIdentity).ToList()
                },
                elements = elementRecords,
                rooms = roomRecords
            };
        }

        private object BuildValidation(
            Document document,
            BimExportCounts counts,
            double scale,
            string targetUnits,
            BimExportArtifactPaths paths,
            string sidecarJson)
        {
            return new
            {
                schemaVersion = 1,
                document = RevitIdentitySerializer.DocumentIdentity(document),
                units = new { source = "feet", target = targetUnits, scaleFactor = scale },
                counts,
                hashes = new
                {
                    model3dm = "sha256:" + Sha256File(paths.Model3dm),
                    sidecar = "sha256:" + Sha256String(sidecarJson)
                }
            };
        }

        private static BimExportVerification VerifyBijection(Rhino.FileIO.File3dm file, HashSet<string> exportedKeys)
        {
            var verification = new BimExportVerification { Ok = true };
            var objectKeys = new HashSet<string>(StringComparer.Ordinal);

            foreach (var obj in file.Objects)
            {
                var key = obj.Attributes.GetUserString("revit.uniqueId");
                if (string.IsNullOrEmpty(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add("A .3dm object has no revit.uniqueId user string.");
                    continue;
                }

                if (!objectKeys.Add(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($"Duplicate .3dm object for key {key}.");
                }

                if (!exportedKeys.Contains(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($".3dm object key {key} has no exported element record.");
                }
            }

            foreach (var key in exportedKeys)
            {
                if (!objectKeys.Contains(key))
                {
                    verification.Ok = false;
                    verification.Discrepancies.Add($"Exported element {key} has no .3dm object.");
                }
            }

            return verification;
        }

        private void AddGeometry(Rhino.FileIO.File3dm file, int layerIndex, Element element, RevitGeometryConversion conversion)
        {
            var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
            attrs.SetUserString("rook.source", "revit");
            attrs.SetUserString("revit.uniqueId", element.UniqueId);
            attrs.SetUserString("revit.elementId", element.Id.Value.ToString());
            attrs.SetUserString("revit.category", element.Category?.Name ?? string.Empty);

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
                file.Objects.AddBox(conversion.Bbox.Value, attrs);
            }
        }

        private string MaterializeRoom(Rhino.FileIO.File3dm file, int layerIndex, RevitRoomExport room, double scale, bool includeGeometry)
        {
            if (!includeGeometry || room.Solid == null)
            {
                return room.Solid == null ? RevitRoomExporter.RepLabelOnly : room.Representation;
            }

            var mesh = new Rhino.Geometry.Mesh();
            foreach (Face face in room.Solid.Faces)
            {
                Mesh triangulated;
                try { triangulated = face.Triangulate(); }
                catch (Exception) { continue; }
                if (triangulated == null) { continue; }

                var baseIndex = mesh.Vertices.Count;
                for (var v = 0; v < triangulated.Vertices.Count; v++)
                {
                    var p = triangulated.get_Vertex(v);
                    mesh.Vertices.Add(p.X * scale, p.Y * scale, p.Z * scale);
                }

                for (var t = 0; t < triangulated.NumTriangles; t++)
                {
                    var tri = triangulated.get_Triangle(t);
                    mesh.Faces.AddFace(baseIndex + (int)tri[0], baseIndex + (int)tri[1], baseIndex + (int)tri[2]);
                }
            }

            if (mesh.Vertices.Count == 0)
            {
                return RevitRoomExporter.RepLabelOnly;
            }

            mesh.Normals.ComputeNormals();
            mesh.Compact();
            var attrs = new Rhino.DocObjects.ObjectAttributes { LayerIndex = layerIndex };
            attrs.SetUserString("rook.source", "revit");
            attrs.SetUserString("revit.uniqueId", room.UniqueId);
            attrs.SetUserString("rookbim.referenceGeometry", "true");
            file.Objects.AddMesh(mesh, attrs);
            return RevitRoomExporter.RepMesh;
        }

        private static int EnsureLayer(Rhino.FileIO.File3dm file, string name)
        {
            var layer = new Rhino.DocObjects.Layer { Name = name };
            return file.AllLayers.Add(layer);
        }

        private static Rhino.UnitSystem MapUnits(string units)
        {
            switch ((units ?? "meters").Trim().ToLowerInvariant())
            {
                case "millimeters": case "mm": return Rhino.UnitSystem.Millimeters;
                case "centimeters": case "cm": return Rhino.UnitSystem.Centimeters;
                case "feet": case "ft": return Rhino.UnitSystem.Feet;
                case "inches": case "in": return Rhino.UnitSystem.Inches;
                default: return Rhino.UnitSystem.Meters;
            }
        }

        private BimApiResponse CleanupAndFail(BimExportArtifactPaths paths, string message)
        {
            CleanupBundle(paths);
            return BimApiResponse.Fail(BimErrorCode.ExportFailed, message, 500);
        }

        private static void CleanupBundle(BimExportArtifactPaths paths)
        {
            foreach (var path in new[] { paths.Model3dm, paths.Sidecar, paths.Validation })
            {
                try { if (File.Exists(path)) { File.Delete(path); } }
                catch (Exception) { /* best-effort cleanup */ }
            }
        }

        private static string Sha256File(string path)
        {
            using var sha = SHA256.Create();
            using var stream = File.OpenRead(path);
            return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", string.Empty).ToLowerInvariant();
        }

        private static string Sha256String(string text)
        {
            using var sha = SHA256.Create();
            return BitConverter.ToString(sha.ComputeHash(Encoding.UTF8.GetBytes(text))).Replace("-", string.Empty).ToLowerInvariant();
        }

        private sealed class ElementResolution
        {
            public IReadOnlyList<Element> Elements { get; private set; } = Array.Empty<Element>();

            public bool Truncated { get; private set; }

            public BimApiResponse? Failure { get; private set; }

            public static ElementResolution Ok(IReadOnlyList<Element> elements, bool truncated)
            {
                return new ElementResolution { Elements = elements, Truncated = truncated };
            }

            public static ElementResolution Fail(BimApiResponse failure)
            {
                return new ElementResolution { Failure = failure };
            }
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter ExportService_FreezesIdentitiesGuardsTruncationWritesBundleAndVerifies`
Expected: PASS.

- [ ] **Step 5: BUILD GATE — compile the real code**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds. This is the largest RhinoCommon surface — fix any mismatches (`File3dm.Objects.AddBrep/AddMesh/AddBox`, `File3dm.AllLayers.Add`, `ObjectAttributes.SetUserString`, `File3dm.Write(path, version)`, `ElementType.FamilyName`) until green.

- [ ] **Step 6: Commit**

```bash
git add src/RookBim/Revit/RevitExportService.cs src/RookBim.Tests/RookBimExportSourceTests.cs
git commit -m "feat(rookbim): export service (resolve/convert/assemble/write/verify)"
```

---

## Task 8: Wire `ExportElements` through the runtime dispatcher

**Files:**
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`
- Test: `src/RookBim.Tests/RookBimExportSourceTests.cs` (add a method)

- [ ] **Step 1: Add the failing test**

Add to `src/RookBim.Tests/RookBimExportSourceTests.cs`:

```csharp
        [Fact]
        public void Runtime_WiresExportElementsThroughDispatcherWithExportTimeout()
        {
            var src = Read("src/RookBim/Revit/RevitRookBimRuntime.cs");

            Assert.Contains("public BimApiResponse ExportElements(BimExportElementsRequest request)", src);
            Assert.Contains("private readonly RevitExportService export", src);
            Assert.Contains("ExportDispatchTimeout", src);
            Assert.Contains("export.Export(", src);
            // Export uses a longer timeout than the default 5s op timeout.
            Assert.Contains("DispatchWithTimeout", src);
        }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter Runtime_WiresExportElementsThroughDispatcherWithExportTimeout`
Expected: FAIL.

- [ ] **Step 3: Implement the wiring**

In `src/RookBim/Revit/RevitRookBimRuntime.cs`:

(a) Add the export timeout constant + service field near the existing fields:

```csharp
        private static readonly TimeSpan ExportDispatchTimeout = TimeSpan.FromSeconds(120);
        private readonly RevitExportService export;
```

(b) In the `internal RevitRookBimRuntime(RevitApiDispatcher dispatcher)` constructor body, add:

```csharp
            this.export = new RevitExportService();
```

(c) Add the public method (after `ClearSelection`):

```csharp
        public BimApiResponse ExportElements(BimExportElementsRequest request)
        {
            if (request == null)
            {
                return BimApiResponse.Fail(BimErrorCode.InvalidScope, "export-elements request is required.", 400);
            }

            var validation = request.Validate();
            if (!validation.Success)
            {
                return BimApiResponse.Fail(
                    validation.ErrorCode, validation.Message ?? "export-elements validation failed.", 400);
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
                        return export.Export(document, view, request);
                    }
                    catch (Exception ex)
                    {
                        return BimApiResponse.Fail(
                            BimErrorCode.ExportFailed,
                            $"RookBIM export failed inside the Revit document context: {DescribeDispatchException(ex)}",
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

(d) Add a timeout-parameterized dispatch overload next to the existing `private T Dispatch<T>`:

```csharp
        private T DispatchWithTimeout<T>(Func<UIApplication, T> work, TimeSpan timeout)
        {
            var dispatch = dispatcher.InvokeAbandonable(work);
            if (Task.WaitAny(new Task[] { dispatch.Task }, timeout) < 0)
            {
                dispatch.Abandon();
                throw new TimeoutException("Timed out waiting for RhinoInside Revit idling-queue execution.");
            }

            return dispatch.Task.GetAwaiter().GetResult();
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/RookBim.Tests/RookBim.Tests.csproj --filter Runtime_WiresExportElementsThroughDispatcherWithExportTimeout`
Expected: PASS.

- [ ] **Step 5: BUILD GATE — compile the real code**

Run: `dotnet build src/RookBim/RookBim.csproj /p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024" /p:RhinoSystemDir="C:\Program Files\Rhino 8\System"`
Expected: build succeeds — `RevitRookBimRuntime` now implements the full `IRookBimRuntime` (including `ExportElements`) and the new `DispatchWithTimeout` overload compiles.

- [ ] **Step 6: Commit**

```bash
git add src/RookBim/Revit/RevitRookBimRuntime.cs src/RookBim.Tests/RookBimExportSourceTests.cs
git commit -m "feat(rookbim): wire ExportElements through dispatcher (120s export timeout)"
```

---

## Task 9: `BimHandler` op + route + error mapping

**Files:**
- Modify: `src/Rook/Handlers/BimHandler.cs`
- Test: `src/Rook.Tests/Handlers/BimHandlerExportSourceTests.cs`

- [ ] **Step 1: Write the failing test**

Create `src/Rook.Tests/Handlers/BimHandlerExportSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class BimHandlerExportSourceTests
    {
        private static string Read(string rel)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, rel.Replace('/', Path.DirectorySeparatorChar));
                if (File.Exists(candidate)) return File.ReadAllText(candidate);
                dir = dir.Parent;
            }
            throw new FileNotFoundException(rel);
        }

        [Fact]
        public void BimHandler_RegistersExportElementsOpRouteAndErrorCodes()
        {
            var src = Read("src/Rook/Handlers/BimHandler.cs");

            Assert.Contains("\"export_elements\"", src);
            Assert.Contains("runtime.ExportElements(", src);
            Assert.Contains("DeserializeRequest<BimExportElementsRequest>(body)", src);
            Assert.Contains("POST /bim/export-elements", src);

            Assert.Contains("BimErrorCode.QueryTruncated => \"query_truncated\"", src);
            Assert.Contains("BimErrorCode.OutputPathInvalid => \"output_path_invalid\"", src);
            Assert.Contains("BimErrorCode.NoExportableGeometry => \"no_exportable_geometry\"", src);
            Assert.Contains("BimErrorCode.ExportFailed => \"export_failed\"", src);
        }
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimHandler_RegistersExportElementsOpRouteAndErrorCodes`
Expected: FAIL.

- [ ] **Step 3: Implement the handler changes**

In `src/Rook/Handlers/BimHandler.cs`:

(a) Add `"export_elements"` to `ExpectedBimOps` (after `"clear_selection"`):

```csharp
            "clear_selection",
            "export_elements",
```

(b) Add the dispatch arm in the `op switch` (after the `clear_selection` arm):

```csharp
                    "export_elements" => FromBimResponse(
                        "export_elements",
                        runtime.ExportElements(DeserializeRequest<BimExportElementsRequest>(body))),
```

(c) Add the new error-code mappings in `MapErrorCode` (before `BimErrorCode.InternalError`):

```csharp
                BimErrorCode.QueryTruncated => "query_truncated",
                BimErrorCode.OutputPathInvalid => "output_path_invalid",
                BimErrorCode.NoExportableGeometry => "no_exportable_geometry",
                BimErrorCode.ExportFailed => "export_failed",
```

(d) Add the route in `RouteForOp` (before the default arm):

```csharp
                "export_elements" => "POST /bim/export-elements",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter BimHandler_RegistersExportElementsOpRouteAndErrorCodes`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Handlers/BimHandler.cs src/Rook.Tests/Handlers/BimHandlerExportSourceTests.cs
git commit -m "feat(bim): BimHandler export_elements op, route, and error mapping"
```

---

## Task 10: Native `/bim/export-elements` route

**Files:**
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/RookServer.cpp`
- Test: `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs` (add InlineData row)

- [ ] **Step 1: Add the failing test row**

In `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`, add one `[InlineData]` row to the `RookServer_RegistersBimRoutesWithCanonicalOps` theory (after the `clear_selection` row):

```csharp
        [InlineData("Post", "/bim/export-elements", "HandleBimExportElements", "export_elements")]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookServer_RegistersBimRoutesWithCanonicalOps`
Expected: FAIL — `HandleBimExportElements` and the route are absent.

- [ ] **Step 3: Add the native handler**

In `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`, add after `HandleBimClearSelection`:

```cpp
void HandleBimExportElements(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (ParseBimPostBody(req, res, "export_elements", body))
        ForwardBimDispatch(req, res, "POST /bim/export-elements", "export_elements", body);
}
```

- [ ] **Step 4: Declare it in the header**

In `src/RookNative/Handlers/GrasshopperProxyHandler.h`, add the declaration alongside the other `HandleBim*` declarations:

```cpp
void HandleBimExportElements(const httplib::Request& req, httplib::Response& res);
```

- [ ] **Step 5: Register the route**

In `src/RookNative/RookServer.cpp`, after the `clear-selection` registration (line ~1089):

```cpp
    m_server->Post("/bim/export-elements", Rook::Handlers::HandleBimExportElements);
```

- [ ] **Step 6: Run test to verify it passes**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter RookServer_RegistersBimRoutesWithCanonicalOps`
Expected: PASS (all rows including export-elements).

- [ ] **Step 7: Build the native plugin to confirm C++ compiles**

Run: `cmd /c scripts\build-native.bat`
Expected: build succeeds (no compile errors in `GrasshopperProxyHandler.cpp` / `RookServer.cpp`).

- [ ] **Step 8: Commit**

```bash
git add src/RookNative/Handlers/GrasshopperProxyHandler.cpp src/RookNative/Handlers/GrasshopperProxyHandler.h src/RookNative/RookServer.cpp src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs
git commit -m "feat(native): /bim/export-elements route forwarding export_elements op"
```

---

## Task 11: MCP `rookbim_export_elements` tool + group + targeting

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/targeting.py`
- Test: `mcp_server/tests/test_rookbim_export_tool.py`

- [ ] **Step 1: Write the failing test**

Create `mcp_server/tests/test_rookbim_export_tool.py`:

```python
from rook.agent import tool_groups
from rook import targeting


def test_export_tool_in_full_group_not_readonly():
    assert "rookbim_export_elements" in tool_groups.TOOL_GROUPS["rookbim"]
    assert "rookbim_export_elements" not in tool_groups.TOOL_GROUPS["rookbim_readonly"]


def test_export_tool_policy_is_rhino_mutate():
    policy = targeting.policy_for_tool("rookbim_export_elements")
    assert policy.requires_rhino is True
    assert policy.risk == "mutate"


def test_export_tool_in_all_known_tools():
    assert "rookbim_export_elements" in targeting._ALL_KNOWN_TOOLS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd mcp_server && python -m pytest tests/test_rookbim_export_tool.py -q`
Expected: FAIL — tool not in group / policy is the unknown fallback.

- [ ] **Step 3: Add the input schema**

In `mcp_server/src/rook/server.py`, after `_rookbim_select_elements_schema` (line ~492), add:

```python
def _rookbim_export_elements_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "selector": _rookbim_query_elements_schema(),
            "identities": {
                "type": "array",
                "items": _rookbim_identity_schema(),
                "minItems": 1,
                "maxItems": 1000,
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
            "rooms": {
                "type": "string",
                "enum": ["both", "labels_only", "exclude"],
                "default": "both",
            },
            "allowTruncated": {"type": "boolean", "default": False},
            "allowBboxProxy": {"type": "boolean", "default": False},
            "port": _rookbim_port_schema(),
        },
        "required": ["output"],
        "additionalProperties": False,
    }
```

- [ ] **Step 4: Add the tool entry**

In `mcp_server/src/rook/server.py`, after the `rookbim_clear_selection` Tool entry (line ~12253):

```python
        Tool(
            name="rookbim_export_elements",
            description=(
                "Export selected Revit elements to a Rhino-consumable .3dm + sidecar + validation "
                "bundle (geometry + identity + semantic labels). Read-only on the Revit/Rhino "
                "documents; writes files to disk. Provide exactly one of 'selector' or 'identities'."
            ),
            inputSchema=_rookbim_export_elements_schema(),
        ),
```

- [ ] **Step 5: Add the dispatch case**

In `mcp_server/src/rook/server.py`, after the `rookbim_clear_selection` case (line ~19530):

```python
        case "rookbim_export_elements":
            result = await call_rhino(
                "/bim/export-elements", "POST", arguments, port=port
            )
```

- [ ] **Step 6: Add to the full tool group only**

In `mcp_server/src/rook/agent/tool_groups.py`, add `"rookbim_export_elements"` to the `"rookbim"` list (after `"rookbim_clear_selection"`), and do NOT add it to `"rookbim_readonly"`:

```python
    "rookbim": [
        "rookbim_status",
        "rookbim_active_document",
        "rookbim_list_categories",
        "rookbim_query_elements",
        "rookbim_element_info",
        "rookbim_element_parameters",
        "rookbim_select_elements",
        "rookbim_clear_selection",
        "rookbim_export_elements",
    ],
```

- [ ] **Step 7: Add to `_ALL_KNOWN_TOOLS` (auto-classified mutate)**

In `mcp_server/src/rook/targeting.py`, add `"rookbim_export_elements"` to `_ALL_KNOWN_TOOLS` (alphabetically near the other `rookbim_*` entries, ~line 540). Do **NOT** add it to the `_RHINO_READ_TOOLS` block (~696). It then falls into `_RHINO_MUTATE_TOOLS` automatically → `RhinoToolPolicy(True, "mutate")`:

```python
    "rookbim_clear_selection",
    "rookbim_element_info",
    "rookbim_element_parameters",
    "rookbim_export_elements",
    "rookbim_list_categories",
    "rookbim_query_elements",
    "rookbim_select_elements",
    "rookbim_status",
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd mcp_server && python -m pytest tests/test_rookbim_export_tool.py -q`
Expected: PASS (3 tests).

- [ ] **Step 9: Run the broader targeting/tool-policy suite to confirm no regression**

Run: `cd mcp_server && python -m pytest tests/ -q -k "targeting or tool_groups or policy"`
Expected: PASS (including any `test_every_exposed_tool_has_policy_entry`-style guard — the new tool now has a policy via `_ALL_KNOWN_TOOLS`).

- [ ] **Step 10: Commit**

```bash
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/targeting.py mcp_server/tests/test_rookbim_export_tool.py
git commit -m "feat(mcp): rookbim_export_elements tool, group, and mutate targeting policy"
```

---

## Task 12: Gated live-verify script

**Files:**
- Create: `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py`

This is **gated** (requires a live Rhino.Inside.Revit session with an open Revit model); it is not part of CI. It proves the contract + bijection end-to-end.

- [ ] **Step 1: Write the script**

Create `docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py`:

```python
"""Gated live verification for rookbim_export_elements.

Run with Rhino.Inside.Revit active and a Revit model open. Resolves the live native
port from the discovery files, exports a small category, and asserts the three-file
bundle, the join bijection, and count reconciliation.

Usage: python docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py <abs_output_dir>
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

from rook.bridge import discover_instances


def _native_port() -> int:
    """Resolve the live native (C++) listener port from the discovery files."""
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
    out_dir = sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp(prefix="rookbim_export_")
    port = _native_port()

    result = _post(port, "/bim/export-elements", {
        "selector": {"scope": "active_view", "category": "Walls", "limit": 50},
        "output": {"directory": out_dir, "name": "walls-fixture", "units": "meters", "overwrite": True},
        "rooms": "both",
        "allowTruncated": True,
        "allowBboxProxy": False,
    })

    assert result.get("success"), f"export failed: {result}"
    data = result["data"]
    paths = data["paths"]
    for key in ("model3dm", "sidecar", "validation"):
        assert Path(paths[key]).exists(), f"missing artifact {key}: {paths[key]}"

    sidecar = json.loads(Path(paths["sidecar"]).read_text(encoding="utf-8"))
    validation = json.loads(Path(paths["validation"]).read_text(encoding="utf-8"))

    assert data["verification"]["ok"], f"bijection failed: {data['verification']['discrepancies']}"

    counts = data["counts"]
    exported = counts["exportedBrep"] + counts["exportedMesh"] + counts["exportedBboxProxy"]
    assert counts["resolved"] == exported + counts["failed"], f"count mismatch: {counts}"
    assert validation["units"]["source"] == "feet"

    print("LIVE VERIFY PASS")
    print(f"  resolved={counts['resolved']} brep={counts['exportedBrep']} "
          f"mesh={counts['exportedMesh']} bbox={counts['exportedBboxProxy']} failed={counts['failed']} "
          f"rooms={counts['rooms']}")
    print(f"  bundle: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Sanity-check it imports (syntax only — full run is gated)**

Run: `cd mcp_server && python -c "import ast; ast.parse(open('../docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py').read())"`
Expected: no output (parses cleanly). `discover_instances` is the real helper in `mcp_server/src/rook/bridge.py` (returns dicts with `port`/`pluginType`); `_native_port()` filters for `pluginType == "native"`.

- [ ] **Step 3: Commit**

```bash
git add docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py
git commit -m "test(rookbim): gated live-verify script for export bundle + bijection"
```

---

## Task 13: Full-suite regression + spec reconciliation

**Files:** none (verification task)

- [ ] **Step 1: Run the C# suites**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj` and `dotnet test src/RookBim.Tests/RookBim.Tests.csproj`
Expected: PASS (including the existing `RookBimModuleSourceTests` invariants — no `Transaction`, no hard `RhinoInside.Revit` reference).

- [ ] **Step 2: Run the Python suite for the bim/targeting surface**

Run: `cd mcp_server && python -m pytest tests/ -q -k "rookbim or targeting or tool_groups"`
Expected: PASS.

- [ ] **Step 3: Confirm the read-only invariants still hold across the new RookBim files**

Run: `cd mcp_server && python - <<'PY'`
```python
import pathlib
bad = []
for p in pathlib.Path("../src/RookBim/Revit").glob("*.cs"):
    text = p.read_text(encoding="utf-8")
    if "Transaction" in text:
        bad.append(p.name)
print("Transaction references:", bad)
assert not bad, bad
print("OK: no Transaction in RookBim/Revit")
PY
```
Expected: `OK: no Transaction in RookBim/Revit`.

- [ ] **Step 4: Commit any final fixups, then run the live-verify script if a Revit session is available**

If a live Rhino.Inside.Revit session is available:
Run: `cd mcp_server && python ../docs/rook_docs/rookbim-export-spike/live_verify_rookbim_export.py C:\Users\<you>\rookbim-fixtures`
Expected: `LIVE VERIFY PASS`.

---

## Self-Review (completed during plan authoring)

**Spec coverage:**
- §3 strict one-of selector + no-silent-truncation → Task 1 (`Validate`), Task 7 (`QueryTruncated` guard).
- §4 output-path safety → Task 2 (policy) + Task 7 (escape/overwrite checks before write).
- §5 locked Brep→mesh→bbox + vocab + units → Task 4 (converter) + Task 7 (units in validation).
- §6 rooms typed separately, per-room degrade → Task 6 + Task 7 (`MaterializeRoom`).
- §7 join key + provenance labels + three-file bundle → Task 5 (labels) + Task 7 (user strings, sidecar, validation).
- §8 bijection verification → Task 7 (`VerifyBijection`) + Task 12 (live).
- §9 registration + error model + `risk="mutate"` → Task 3, 9, 10, 11.
- §10 testing (source-text + pure + live) → Tasks 1–12.

**Placeholder scan:** no TBD/TODO; every code step shows complete code. The live-verify script uses
the real `discover_instances()` bridge API (no invented helper).

**Independent green-per-task:** Task 1's `Validate()` does only local output-shape checks (no
dependency on Task 2's `BimExportPathPolicy`); Task 2 then upgrades `Validate()` to delegate to the
policy. Every task commits green on its own.

**Build gates (not just source-text):** `RookBim.Tests` is source-text only (no `ProjectReference`
to `RookBim`), so Tasks 4–8 each add an explicit `dotnet build src/RookBim/RookBim.csproj` gate that
compiles the real Revit/RhinoCommon code (Task 4 also adds the required `RhinoCommon` reference to
`RookBim.csproj`). The native route adds a `scripts\build-native.bat` gate (Task 10).

**Type consistency:** `BimExportElementsRequest`/`BimExportOutput`/`BimRoomsMode`/`BimExportResult`/`BimExportPathPolicy.{ValidateRequestShape,ResolveBundlePaths,EscapesIntendedDirectory}`/`RevitGeometryConverter.{ScaleFromFeet,Convert}`/`RevitGeometryConversion`/`RevitElementLabels`/`BimSemanticLabel`/`RevitRoomExport`/`RevitExportService.Export`/`ExportElements`/`DispatchWithTimeout` are defined once and referenced consistently. Error-code wire strings (`query_truncated`, `output_path_invalid`, `no_exportable_geometry`, `export_failed`) match between `BimHandler.MapErrorCode` (Task 9) and their `BimErrorCode` enum members (Task 1).

---

## Implementation Reconciliation (post-execution, 2026-06-16)

All 13 tasks executed via subagent-driven development on `feature/spatial-intelligence` with per-task
two-stage review at the gate tasks (2, 4, 7, 10) and the final gate (13). Final regression:
**Rook.Tests 2627 passed / 0 failed; RookBim.Tests 35 passed / 0 failed; RookBim build gate 0 errors;
Python targeting/tool-group/rookbim suite 147 passed** (the lone failure, `rhino_vision_presentation`
missing a policy entry, is pre-existing branch drift from main's #254 — unrelated to this feature and
documented in the pivot checkpoint); **no `Transaction` in `src/RookBim/Revit/*.cs`.**

Deltas from the as-written plan that surfaced during execution (the committed code is the source of
truth; these were verified by the build gates + reviews):

1. **Test-file naming** — the three new `Rook.Tests/Bim` test files use the folder's `RookBim*`
   convention: `RookBimExportContractsTests`, `RookBimExportPathPolicyTests`,
   `RookBimUnavailableExportTests` (plan Task 1/2/3 prose shows the un-prefixed names).
2. **Units validation home** — `output.units` is validated against the supported set
   (`meters|millimeters|centimeters|feet|inches`) inside `BimExportPathPolicy.ValidateRequestShape`
   (Task 2), not in Task 1 — fail-fast, no silent fallback. Spec §3 updated.
3. **`RevitGeometryConversion` factory rename** — the plan declared both a `Mesh` property and a
   `Mesh(...)` factory (illegal C#, CS0102). Factories renamed `FromBrep`/`FromMesh`/`FromBboxProxy`
   (`Failed` kept); the consumed read surface (`Breps`/`Mesh`/`Bbox`/`Quality`/`Representation`/
   `FallbackReason`/`HasGeometry`) is unchanged.
4. **Failed-element representation** — `Failed(...)` reports `geometryRepresentation = "none"`
   (`RepresentationNone`), not `bbox_proxy`, so a no-geometry element is distinguishable from a real
   bbox proxy. Spec §5 updated.
5. **`BimSemanticLabel` is idiomatic PascalCase** (`Value`/`Source`/`Confidence`/`MissingReason`);
   the camelCase JSON contract is produced by `RevitExportService`'s serialization projection, not by
   the property names (plan Task 5 test prose shows the camelCase identifiers).
6. **RhinoCommon `File3dm` API fixes (Task 7)** — `File3dm.Objects.AddBox` doesn't exist →
   `AddBrep(box.ToBrep())`; `File3dmLayerTable.Add` returns void → `EnsureLayer` pins the index via
   `AllLayers.Count`; Revit mesh accessors `Vertices[v]`/`get_Index(n)`.
7. **Export-service robustness (Task 7 review)** — per-element conversion/label/record building is
   wrapped so one bad element is counted `Failed` (with a `none`/`failed` record) instead of aborting
   the export; `BimExportCounts.Requested` reflects the pre-resolution query count (selector drops are
   visible as `Requested - Resolved`); on failure, cleanup deletes only files written *this run*
   (never a pre-existing sibling under `overwrite=true`).
8. **Path policy hardening (Task 2 review)** — rejects trailing-dot names (Windows footgun) in
   addition to the spec'd separators/`..`/reserved-device-names; added prefix-escape (`C:\fixtures-evil`)
   and `..`-traversal regression tests.
9. **Necessary collateral** — adding `ExportElements` to `IRookBimRuntime` required `ExportElements`
   stubs on 6 in-test `IRookBimRuntime` doubles (Task 3); the `BimHandlerTests` exact-ops list gained
   `export_elements` (Task 9); the MCP `BRIDGE_ROUTES` + `ROOKBIM_TOOL_ROUTES` guard dicts gained the
   new tool (Task 11).
10. **Minor accepted-as-is** — `RevitRoomExporter` carries a documentary
    `SidecarKeyReferenceGeometry = "referenceGeometry"` const (the camelCase JSON key is emitted by
    `RevitExportService`; the const is harmless and never read at runtime).

**Live verification still pending** — the gated `live_verify_rookbim_export.py` (Task 12) must be run
against a live Rhino.Inside.Revit session with an open Revit model before the bundle is trusted as a
calibration fixture; static review + build gates cannot exercise the RIR Brep reflection path, real
geometry/room extraction, or `File3dm.Write`.
