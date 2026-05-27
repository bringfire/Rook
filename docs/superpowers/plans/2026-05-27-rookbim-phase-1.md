# RookBIM Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build Phase 1 RookBIM as live, read-only, auditable Revit model interrogation through RookNative's existing public HTTP surface.

**Architecture:** RookNative registers public `/bim/*` routes and opaque JSON-proxies them through a new managed callback. Core `src/Rook` owns BIM DTOs, fallback behavior, module activation, and callback routing without referencing Revit assemblies. Optional `src/RookBim` owns all Autodesk Revit API references and registers a runtime with core only when loaded inside RhinoInside/Revit.

**Tech Stack:** C++ Rhino 8 native plugin with `httplib` and `nlohmann::json`, C# `net48` managed companion, optional Revit 2024 managed module, xUnit, pytest, PowerShell source guards, MCP Python server.

---

## Source References

- Primary design spec: `docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md`
- Current boundary reference: `docs/CURRENT_ARCHITECTURE.md`
- Local Revit SDK reference: `C:/Revit 2024.2 SDK`
- Revit API docs/samples to verify before using API names:
  - `C:/Revit 2024.2 SDK/Samples/ModelessDialog/ModelessForm_ExternalEvent`
  - `C:/Revit 2024.2 SDK/Samples/Selections`
  - `C:/Revit 2024.2 SDK/Samples/ParameterUtils`
  - SDK samples containing `FilteredElementCollector`, `ElementId`, `UniqueId`, `AsValueString`, `StorageType`, `ExternalEvent`

## File Structure

### Created Files

- `scripts/tests/rookbim-boundary-guards.tests.ps1`
  - PowerShell source guard for architecture drift: no Revit references in `src/Rook`, no new C++ project-file entries for BIM route handlers, and BIM route names stay on `/bim/*`.
- `src/Rook/Bim/BimContracts.cs`
  - Core DTOs/enums for documents, views, identities, query filters, parameters, selection, response envelopes, and error codes. No Revit references.
- `src/Rook/Bim/IRookBimRuntime.cs`
  - Core runtime interface implemented by fallback and optional RookBim module.
- `src/Rook/Bim/RookBimRuntimeRegistry.cs`
  - Process-local runtime registry with fallback default and optional module installation.
- `src/Rook/Bim/RookBimUnavailableRuntime.cs`
  - Structured unavailable runtime for standalone Rhino and missing module states.
- `src/Rook/Bim/RookBimModuleLoader.cs`
  - Reflection-only activation of `RookBim.dll`; no compile-time Revit or RookBim reference.
- `src/Rook/Handlers/BimHandler.cs`
  - Managed dispatch boundary for `bim_dispatch`; validates `op`, routes to `IRookBimRuntime`, serializes envelopes.
- `src/Rook.Tests/Bim/RookBimContractsTests.cs`
  - Unit tests for default limits, hard max, scope/filter validation, missing parameter semantics constants, and identity caveat fields.
- `src/Rook.Tests/Bim/RookBimUnavailableRuntimeTests.cs`
  - Unit tests for fallback status and document-bound unavailable failures.
- `src/Rook.Tests/Handlers/BimHandlerTests.cs`
  - Unit/source tests for op allowlist, unknown op, fallback dispatch, and no write operations.
- `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`
  - Source tests that pin native `/bim/*` route registration and op injection in `RookServer.cpp`.
- `mcp_server/tests/test_rookbim_mcp_tools.py`
  - Python tests for `rookbim_*` tool schemas, `BRIDGE_ROUTES`, group registration, default scope, hard max, and read-only grouping.
- `src/RookBim/RookBim.csproj`
  - Optional `net48` module that references `src/Rook` and Autodesk Revit 2024 assemblies with `Private=false`.
- `src/RookBim/RookBimModule.cs`
  - Reflection activation entry point called by core loader; installs Revit runtime when module can initialize.
- `src/RookBim/Revit/RevitRookBimRuntime.cs`
  - Runtime implementation for Phase 1 operations.
- `src/RookBim/Revit/RevitApiDispatcher.cs`
  - ExternalEvent-backed dispatcher for Revit API context execution.
- `src/RookBim/Revit/RevitContext.cs`
  - Runtime detection and `UIApplication`/document evidence helpers.
- `src/RookBim/Revit/RevitIdentitySerializer.cs`
  - Document/view/element identity envelopes.
- `src/RookBim/Revit/RevitQueryService.cs`
  - Bounded active-view/document query logic.
- `src/RookBim/Revit/RevitParameterSerializer.cs`
  - Phase 1 string/display parameter serialization plus raw/storage metadata where safe.
- `src/RookBim/Revit/RevitSelectionService.cs`
  - UI-selection-only select and clear operations.
- `src/RookBim.Tests/RookBim.Tests.csproj`
  - Optional module tests that can run where Revit assemblies are present; source/contract tests run without launching Revit.

### Modified Files

- `Rook.sln`
  - Do not modify. The optional Revit module stays out of the main solution so ordinary Rook solution builds do not require Revit to be installed.
- `src/Rook/Rook.csproj`
  - No reference to `RookBim.csproj`. Add only a `None` copy item if the optional `RookBim.dll` exists beside the managed runtime during local/release packaging.
- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
  - Add `BimDispatch` callback slot and route to `Rook.Handlers.BimHandler`; bump bridge ABI in lockstep with native.
- `src/RookNative/Handlers/GrasshopperProxyHandler.h`
  - Add `InvokeBimDispatchWithBody` declaration.
- `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
  - Add `bim_dispatch` callback field, ABI bump, registration validation, and invocation helper.
- `src/RookNative/RookServer.cpp`
  - Register `/bim/*` public routes and local helpers to parse/inject `op` and proxy to `InvokeBimDispatchWithBody`. Keep BIM helpers here to avoid new native `.cpp/.h` project-file entries.
- `mcp_server/src/rook/agent/tool_dispatcher.py`
  - Add `rookbim_*` names to `BRIDGE_ROUTES`.
- `mcp_server/src/rook/server.py`
  - Add `rookbim_*` MCP tool definitions.
- `mcp_server/src/rook/agent/tool_groups.py`
  - Add `rookbim` and `rookbim_readonly` groups; mark selection tools separately because they mutate UI selection but not the Revit document.
- `mcp_server/src/rook/context.py`
  - Add BIM tool category metadata if existing category tables require explicit registration.

---

## Task 1: Architecture Source Guards

**Files:**
- Create: `scripts/tests/rookbim-boundary-guards.tests.ps1`

- [ ] **Step 1: Write the failing source guard**

Create `scripts/tests/rookbim-boundary-guards.tests.ps1` with:

```powershell
$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

function Fail($message) {
    Write-Error $message
    exit 1
}

$coreFiles = Get-ChildItem -Path "src/Rook" -Recurse -Include *.cs -File
$coreRevitMatches = $coreFiles | Select-String -Pattern "Autodesk\.Revit|RevitAPI|RevitAPIUI" -CaseSensitive
if ($coreRevitMatches) {
    $formatted = $coreRevitMatches | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    Fail "src/Rook must not reference Revit APIs:`n$($formatted -join "`n")"
}

$nativeProjectFiles = @(
    "src/RookNative/RookNative.vcxproj",
    "src/RookNative/RookNative.vcxproj.filters"
)
foreach ($path in $nativeProjectFiles) {
    $text = Get-Content $path -Raw
    if ($text -match "BimHandler\.(cpp|h)") {
        Fail "$path must not gain BIM handler project-file entries; keep Phase 1 native BIM routing in RookServer.cpp or explicitly approve project-file churn."
    }
}

$routeText = Get-Content "src/RookNative/RookServer.cpp" -Raw
$badRoutes = Select-String -Path "src/RookNative/RookServer.cpp" -Pattern '"/revit/|"/rookbim/|"/rhino/bim/' -AllMatches
if ($badRoutes) {
    $formatted = $badRoutes | ForEach-Object { "$($_.Path):$($_.LineNumber): $($_.Line.Trim())" }
    Fail "BIM public routes must use /bim/* only:`n$($formatted -join "`n")"
}

Write-Host "rookbim boundary guards passed"
```

- [ ] **Step 2: Run the guard before implementation**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/rookbim-boundary-guards.tests.ps1
```

Expected:

```text
rookbim boundary guards passed
```

- [ ] **Step 3: Commit**

Run:

```powershell
git add scripts/tests/rookbim-boundary-guards.tests.ps1
git commit -m "test: add rookbim boundary guards"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] test: add rookbim boundary guards
```

---

## Task 2: Core BIM Contracts and Fallback Runtime

**Files:**
- Create: `src/Rook/Bim/BimContracts.cs`
- Create: `src/Rook/Bim/IRookBimRuntime.cs`
- Create: `src/Rook/Bim/RookBimRuntimeRegistry.cs`
- Create: `src/Rook/Bim/RookBimUnavailableRuntime.cs`
- Create: `src/Rook.Tests/Bim/RookBimContractsTests.cs`
- Create: `src/Rook.Tests/Bim/RookBimUnavailableRuntimeTests.cs`

- [ ] **Step 1: Write contract tests**

Create `src/Rook.Tests/Bim/RookBimContractsTests.cs` with:

```csharp
using System.Collections.Generic;
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public sealed class RookBimContractsTests
    {
        [Fact]
        public void QueryDefaults_AreActiveViewAndSmallLimit()
        {
            var request = new BimQueryElementsRequest();

            Assert.Equal(BimQueryScope.ActiveView, request.EffectiveScope);
            Assert.Equal(100, request.EffectiveLimit);
            Assert.Equal(1000, BimQueryElementsRequest.HardMaxLimit);
        }

        [Fact]
        public void DocumentScope_RequiresCategory()
        {
            var request = new BimQueryElementsRequest
            {
                Scope = BimQueryScope.Document,
                Filters = new List<BimQueryFilter>
                {
                    new()
                    {
                        Parameter = "Fire Rating",
                        Operation = BimFilterOperation.IsNotEmpty
                    }
                }
            };

            var result = request.Validate();

            Assert.False(result.Success);
            Assert.Equal(BimErrorCode.UnboundedDocumentQuery, result.ErrorCode);
            Assert.Contains("document scope requires category", result.Message);
        }

        [Theory]
        [InlineData(BimFilterOperation.Equals, false)]
        [InlineData(BimFilterOperation.Contains, false)]
        [InlineData(BimFilterOperation.NotEquals, true)]
        [InlineData(BimFilterOperation.IsEmpty, true)]
        [InlineData(BimFilterOperation.IsNotEmpty, false)]
        public void MissingParameterSemantics_ArePinned(BimFilterOperation op, bool expected)
        {
            Assert.Equal(expected, BimFilterSemantics.MissingParameterMatches(op));
        }

        [Fact]
        public void IdentityEnvelope_MatchesApprovedSpecShape()
        {
            var document = new BimDocumentIdentity
            {
                Guid = null,
                GuidSource = BimDocumentGuidSource.Unavailable,
                Title = "Model.rvt",
                Path = "C:/Models/Model.rvt",
                IsFamilyDocument = false,
                IsWorkshared = true
            };
            var identity = new BimElementIdentity
            {
                Source = "revit",
                DocumentGuid = null,
                DocumentGuidSource = BimDocumentGuidSource.Unavailable,
                DocumentTitle = "Model.rvt",
                DocumentPath = "C:/Models/Model.rvt",
                ElementId = 123,
                UniqueId = "abc",
                FullUniqueId = "abc",
                Linked = false,
                LinkInstanceId = null,
                LinkInstanceUniqueId = null,
                LinkedDocumentGuid = null,
                LinkedElementId = null,
                LinkedElementUniqueId = null,
                Resolved = true,
                Confidence = BimIdentityConfidence.Exact
            };

            Assert.False(document.IsFamilyDocument);
            Assert.True(document.IsWorkshared);
            Assert.Equal("revit", identity.Source);
            Assert.Null(identity.DocumentGuid);
            Assert.Equal(BimDocumentGuidSource.Unavailable, identity.DocumentGuidSource);
            Assert.Equal("C:/Models/Model.rvt", identity.DocumentPath);
            Assert.Equal("abc", identity.FullUniqueId);
            Assert.False(identity.Linked);
            Assert.Equal(BimIdentityConfidence.Exact, identity.Confidence);
        }

        [Fact]
        public void QueryResultEnvelope_UsesQueryObjectAndCategoryTypeObjects()
        {
            var result = new BimQueryElementsResult
            {
                Document = new BimDocumentIdentity { Title = "Model.rvt" },
                Scope = BimQueryScope.ActiveView,
                Query = new BimQuerySummary
                {
                    Category = "Walls",
                    Limit = 100,
                    Returned = 1,
                    Truncated = false
                },
                Elements =
                {
                    new BimElementSummary
                    {
                        Identity = new BimElementIdentity { Source = "revit", ElementId = 123 },
                        Name = "Basic Wall",
                        Category = new BimCategorySummary { Id = -2000011, Name = "Walls" },
                        Type = new BimElementTypeSummary { Id = 67890, Name = "Generic - 8 inch" }
                    }
                }
            };

            Assert.Equal("Walls", result.Query.Category);
            Assert.Equal(1, result.Query.Returned);
            Assert.Equal(-2000011, result.Elements[0].Category.Id);
            Assert.Equal("Generic - 8 inch", result.Elements[0].Type.Name);
        }
    }
}
```

- [ ] **Step 2: Write fallback runtime tests**

Create `src/Rook.Tests/Bim/RookBimUnavailableRuntimeTests.cs` with:

```csharp
using Rook.Bim;
using Xunit;

namespace Rook.Tests.Bim
{
    public sealed class RookBimUnavailableRuntimeTests
    {
        [Fact]
        public void Status_ReturnsStructuredUnavailableEvidence()
        {
            var runtime = new RookBimUnavailableRuntime("not_rhino_inside", "Rhino is not running inside Revit.");

            var response = runtime.Status();

            Assert.False(response.Available);
            Assert.Equal("not_rhino_inside", response.ErrorCode);
            Assert.Equal("Rhino is not running inside Revit.", response.Message);
            Assert.Equal("unavailable", response.Runtime);
        }

        [Theory]
        [InlineData("ActiveDocument")]
        [InlineData("QueryElements")]
        [InlineData("ElementInfo")]
        [InlineData("ElementParameters")]
        [InlineData("SelectElements")]
        [InlineData("ClearSelection")]
        public void DocumentBoundOperations_FailWithRookBimUnavailable(string operation)
        {
            var runtime = new RookBimUnavailableRuntime("rookbim_unavailable", "RookBIM runtime is unavailable.");

            BimApiResponse response = operation switch
            {
                "ActiveDocument" => runtime.ActiveDocument(),
                "QueryElements" => runtime.QueryElements(new BimQueryElementsRequest()),
                "ElementInfo" => runtime.ElementInfo(new BimElementRequest()),
                "ElementParameters" => runtime.ElementParameters(new BimElementRequest()),
                "SelectElements" => runtime.SelectElements(new BimSelectElementsRequest()),
                "ClearSelection" => runtime.ClearSelection(),
                _ => throw new System.InvalidOperationException(operation)
            };

            Assert.False(response.Success);
            Assert.Equal(BimErrorCode.RookBimUnavailable, response.ErrorCode);
            Assert.Contains("RookBIM runtime is unavailable", response.Message);
        }
    }
}
```

- [ ] **Step 3: Run tests to verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Bim" --no-restore
```

Expected:

```text
error CS0234: The type or namespace name 'Bim' does not exist in the namespace 'Rook'
```

- [ ] **Step 4: Implement contracts**

Create `src/Rook/Bim/BimContracts.cs` with the following shape. Keep this file free of `Autodesk.Revit`, `RevitAPI`, and `RevitAPIUI`.

```csharp
using System.Collections.Generic;

namespace Rook.Bim
{
    public enum BimErrorCode
    {
        None,
        RookBimUnavailable,
        NotRhinoInside,
        RevitUnavailable,
        NoActiveDocument,
        NoActiveView,
        InvalidScope,
        UnboundedDocumentQuery,
        InvalidCategory,
        AmbiguousParameter,
        QueryLimitExceeded,
        ElementNotFound,
        DocumentMismatch,
        LinkedElementUnsupported,
        CapabilityUnavailable,
        SelectionFailed,
        InternalError
    }

    public enum BimDocumentGuidSource
    {
        RevitPersistentGuid,
        PathFallback,
        Unavailable
    }

    public enum BimIdentityConfidence
    {
        Exact,
        Inferred,
        Unresolved,
        Unsupported
    }

    public enum BimQueryScope
    {
        ActiveView,
        Document
    }

    public enum BimFilterOperation
    {
        Equals,
        NotEquals,
        Contains,
        IsEmpty,
        IsNotEmpty
    }

    public sealed class BimValidationResult
    {
        public static readonly BimValidationResult Ok = new(true, BimErrorCode.None, string.Empty);

        public BimValidationResult(bool success, BimErrorCode errorCode, string message)
        {
            Success = success;
            ErrorCode = errorCode;
            Message = message;
        }

        public bool Success { get; }
        public BimErrorCode ErrorCode { get; }
        public string Message { get; }
    }

    public static class BimFilterSemantics
    {
        public static bool MissingParameterMatches(BimFilterOperation operation)
        {
            return operation switch
            {
                BimFilterOperation.IsEmpty => true,
                BimFilterOperation.IsNotEmpty => false,
                BimFilterOperation.Equals => false,
                BimFilterOperation.Contains => false,
                BimFilterOperation.NotEquals => true,
                _ => false
            };
        }
    }

    public sealed class BimApiResponse
    {
        public bool Success { get; set; }
        public BimErrorCode ErrorCode { get; set; }
        public string Message { get; set; } = string.Empty;
        public object? Data { get; set; }
        public int HttpStatus { get; set; } = 200;

        public static BimApiResponse Ok(object data) => new()
        {
            Success = true,
            ErrorCode = BimErrorCode.None,
            Data = data,
            HttpStatus = 200
        };

        public static BimApiResponse Fail(BimErrorCode code, string message, int httpStatus) => new()
        {
            Success = false,
            ErrorCode = code,
            Message = message,
            HttpStatus = httpStatus
        };
    }

    public sealed class BimStatusResponse
    {
        public bool Available { get; set; }
        public string Runtime { get; set; } = "unavailable";
        public string? ErrorCode { get; set; }
        public string Message { get; set; } = string.Empty;
        public string Host { get; set; } = "unknown";
        public string Module { get; set; } = "core";
    }

    public sealed class BimDocumentIdentity
    {
        public string? Guid { get; set; }
        public BimDocumentGuidSource GuidSource { get; set; } = BimDocumentGuidSource.Unavailable;
        public string Title { get; set; } = string.Empty;
        public string? Path { get; set; }
        public bool IsFamilyDocument { get; set; }
        public bool IsWorkshared { get; set; }
    }

    public sealed class BimViewIdentity
    {
        public int Id { get; set; }
        public string? UniqueId { get; set; }
        public string Name { get; set; } = string.Empty;
    }

    public sealed class BimElementIdentity
    {
        public string Source { get; set; } = "revit";
        public string? DocumentGuid { get; set; }
        public BimDocumentGuidSource DocumentGuidSource { get; set; } = BimDocumentGuidSource.Unavailable;
        public string DocumentTitle { get; set; } = string.Empty;
        public string? DocumentPath { get; set; }
        public int? ElementId { get; set; }
        public string? UniqueId { get; set; }
        public string? FullUniqueId { get; set; }
        public bool Linked { get; set; }
        public int? LinkInstanceId { get; set; }
        public string? LinkInstanceUniqueId { get; set; }
        public string? LinkedDocumentGuid { get; set; }
        public int? LinkedElementId { get; set; }
        public string? LinkedElementUniqueId { get; set; }
        public bool Resolved { get; set; }
        public BimIdentityConfidence Confidence { get; set; } = BimIdentityConfidence.Unresolved;
    }

    public sealed class BimCategorySummary
    {
        public int? Id { get; set; }
        public string? Name { get; set; }
    }

    public sealed class BimElementTypeSummary
    {
        public int? Id { get; set; }
        public string? UniqueId { get; set; }
        public string? FamilyName { get; set; }
        public string? Name { get; set; }
    }

    public sealed class BimElementSummary
    {
        public BimElementIdentity Identity { get; set; } = new();
        public string? Name { get; set; }
        public BimCategorySummary Category { get; set; } = new();
        public BimElementTypeSummary Type { get; set; } = new();
    }

    public sealed class BimQuerySummary
    {
        public string? Category { get; set; }
        public int Limit { get; set; }
        public int Returned { get; set; }
        public bool Truncated { get; set; }
        public Dictionary<string, int> MissingParameterCounts { get; set; } = new();
    }

    public sealed class BimQueryElementsResult
    {
        public BimDocumentIdentity Document { get; set; } = new();
        public BimQueryScope Scope { get; set; } = BimQueryScope.ActiveView;
        public BimViewIdentity? View { get; set; }
        public BimQuerySummary Query { get; set; } = new();
        public List<BimElementSummary> Elements { get; set; } = new();
    }

    public sealed class BimQueryFilter
    {
        public string Parameter { get; set; } = string.Empty;
        public BimFilterOperation Operation { get; set; }
        public string? Value { get; set; }
    }

    public sealed class BimQueryElementsRequest
    {
        public const int DefaultLimit = 100;
        public const int HardMaxLimit = 1000;

        public BimQueryScope? Scope { get; set; }
        public string? Category { get; set; }
        public int? Limit { get; set; }
        public List<BimQueryFilter> Filters { get; set; } = new();

        public BimQueryScope EffectiveScope => Scope ?? BimQueryScope.ActiveView;
        public int EffectiveLimit => Limit ?? DefaultLimit;

        public BimValidationResult Validate()
        {
            if (EffectiveLimit < 1 || EffectiveLimit > HardMaxLimit)
            {
                return new BimValidationResult(
                    false,
                    BimErrorCode.QueryLimitExceeded,
                    $"limit must be between 1 and {HardMaxLimit}");
            }

            if (EffectiveScope == BimQueryScope.Document && string.IsNullOrWhiteSpace(Category))
            {
                return new BimValidationResult(
                    false,
                    BimErrorCode.UnboundedDocumentQuery,
                    "document scope requires category in Phase 1");
            }

            foreach (var filter in Filters)
            {
                if (string.IsNullOrWhiteSpace(filter.Parameter))
                {
                    return new BimValidationResult(
                        false,
                        BimErrorCode.InvalidScope,
                        "filter parameter is required");
                }
            }

            return BimValidationResult.Ok;
        }
    }

    public sealed class BimElementRequest
    {
        public BimElementIdentity Identity { get; set; } = new();
    }

    public sealed class BimSelectElementsRequest
    {
        public List<BimElementIdentity> Identities { get; set; } = new();
    }
}
```

- [ ] **Step 5: Implement runtime interface and fallback**

Create `src/Rook/Bim/IRookBimRuntime.cs`:

```csharp
namespace Rook.Bim
{
    public interface IRookBimRuntime
    {
        BimStatusResponse Status();
        BimApiResponse ActiveDocument();
        BimApiResponse QueryElements(BimQueryElementsRequest request);
        BimApiResponse ElementInfo(BimElementRequest request);
        BimApiResponse ElementParameters(BimElementRequest request);
        BimApiResponse SelectElements(BimSelectElementsRequest request);
        BimApiResponse ClearSelection();
    }
}
```

Create `src/Rook/Bim/RookBimUnavailableRuntime.cs`:

```csharp
namespace Rook.Bim
{
    public sealed class RookBimUnavailableRuntime : IRookBimRuntime
    {
        private readonly string _statusCode;
        private readonly string _message;

        public RookBimUnavailableRuntime(string statusCode, string message)
        {
            _statusCode = statusCode;
            _message = message;
        }

        public BimStatusResponse Status() => new()
        {
            Available = false,
            Runtime = "unavailable",
            ErrorCode = _statusCode,
            Message = _message,
            Host = "unknown",
            Module = "core"
        };

        public BimApiResponse ActiveDocument() => Unavailable();
        public BimApiResponse QueryElements(BimQueryElementsRequest request) => Unavailable();
        public BimApiResponse ElementInfo(BimElementRequest request) => Unavailable();
        public BimApiResponse ElementParameters(BimElementRequest request) => Unavailable();
        public BimApiResponse SelectElements(BimSelectElementsRequest request) => Unavailable();
        public BimApiResponse ClearSelection() => Unavailable();

        private BimApiResponse Unavailable()
        {
            return BimApiResponse.Fail(
                BimErrorCode.RookBimUnavailable,
                _message,
                503);
        }
    }
}
```

Create `src/Rook/Bim/RookBimRuntimeRegistry.cs`:

```csharp
using System;

namespace Rook.Bim
{
    public static class RookBimRuntimeRegistry
    {
        private static readonly object Sync = new();
        private static IRookBimRuntime _current =
            new RookBimUnavailableRuntime("rookbim_unavailable", "RookBIM runtime is unavailable.");
        private static string _source = "core-fallback";

        public static IRookBimRuntime Current
        {
            get
            {
                lock (Sync) return _current;
            }
        }

        public static string Source
        {
            get
            {
                lock (Sync) return _source;
            }
        }

        public static void Install(IRookBimRuntime runtime, string source)
        {
            if (runtime == null) throw new ArgumentNullException(nameof(runtime));
            if (string.IsNullOrWhiteSpace(source)) throw new ArgumentException("source is required", nameof(source));

            lock (Sync)
            {
                _current = runtime;
                _source = source;
            }
        }

        internal static void ResetForTests()
        {
            lock (Sync)
            {
                _current = new RookBimUnavailableRuntime("rookbim_unavailable", "RookBIM runtime is unavailable.");
                _source = "core-fallback";
            }
        }
    }
}
```

- [ ] **Step 6: Run tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Bim"
```

Expected:

```text
Passed!
```

- [ ] **Step 7: Run source guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/rookbim-boundary-guards.tests.ps1
```

Expected:

```text
rookbim boundary guards passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/Rook/Bim src/Rook.Tests/Bim
git commit -m "feat: add rookbim core contracts"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: add rookbim core contracts
```

---

## Task 3: Managed BIM Dispatch Boundary

**Files:**
- Create: `src/Rook/Handlers/BimHandler.cs`
- Create: `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`

- [ ] **Step 1: Write handler tests**

Create `src/Rook.Tests/Handlers/BimHandlerTests.cs`:

```csharp
using System.Text.Json;
using Rook.Bim;
using Rook.Handlers;
using Rook.InternalBridge;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class BimHandlerTests
    {
        [Fact]
        public void ExpectedBimOps_HasExactlyPhase1Ops()
        {
            Assert.Equal(7, BimHandler.ExpectedBimOps.Count);
            Assert.Contains("status", BimHandler.ExpectedBimOps);
            Assert.Contains("active_document", BimHandler.ExpectedBimOps);
            Assert.Contains("query_elements", BimHandler.ExpectedBimOps);
            Assert.Contains("element_info", BimHandler.ExpectedBimOps);
            Assert.Contains("element_parameters", BimHandler.ExpectedBimOps);
            Assert.Contains("select_elements", BimHandler.ExpectedBimOps);
            Assert.Contains("clear_selection", BimHandler.ExpectedBimOps);
        }

        [Fact]
        public void Dispatch_UnknownOp_ReturnsStructured400()
        {
            RookBimRuntimeRegistry.ResetForTests();
            var handler = new BimHandler();

            var response = handler.Dispatch("""{"op":"write_wall"}""");
            using var doc = JsonDocument.Parse(response.Json);

            Assert.Equal(400, response.HttpStatus);
            Assert.False(doc.RootElement.GetProperty("success").GetBoolean());
            Assert.Equal("invalid_scope", doc.RootElement.GetProperty("errorCode").GetString());
            Assert.Contains("Unknown BIM op", doc.RootElement.GetProperty("message").GetString());
        }

        [Fact]
        public void Dispatch_Status_UsesFallbackRuntime()
        {
            RookBimRuntimeRegistry.ResetForTests();
            var handler = new BimHandler();

            var response = handler.Dispatch("""{"op":"status"}""");
            using var doc = JsonDocument.Parse(response.Json);

            Assert.Equal(200, response.HttpStatus);
            Assert.True(doc.RootElement.GetProperty("success").GetBoolean());
            var data = doc.RootElement.GetProperty("data");
            Assert.False(data.GetProperty("available").GetBoolean());
            Assert.Equal("rookbim_unavailable", data.GetProperty("errorCode").GetString());
        }

        [Fact]
        public void Dispatch_QueryElements_RejectsDocumentScopeWithoutCategory()
        {
            RookBimRuntimeRegistry.ResetForTests();
            var handler = new BimHandler();

            var response = handler.Dispatch("""{"op":"query_elements","scope":"document","filters":[{"parameter":"Fire Rating","operation":"not_equals","value":"2HR"}]}""");
            using var doc = JsonDocument.Parse(response.Json);

            Assert.Equal(400, response.HttpStatus);
            Assert.False(doc.RootElement.GetProperty("success").GetBoolean());
            Assert.Equal("unbounded_document_query", doc.RootElement.GetProperty("errorCode").GetString());
            Assert.Contains("document scope requires category", doc.RootElement.GetProperty("message").GetString());
        }

        [Fact]
        public void NativeRegistrar_SourceDeclaresBimDispatchCallback()
        {
            var source = System.IO.File.ReadAllText(System.IO.Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));

            Assert.Contains("BimDispatchCallback = HandleBimDispatch", source);
            Assert.Contains("public IntPtr BimDispatch;", source);
            Assert.Contains("BimDispatch = Marshal.GetFunctionPointerForDelegate(BimDispatchCallback)", source);
            Assert.Contains("private static int HandleBimDispatch(", source);
        }

        private static string FindRepoRoot()
        {
            var dir = new System.IO.DirectoryInfo(System.AppContext.BaseDirectory);
            while (dir != null)
            {
                if (System.IO.File.Exists(System.IO.Path.Combine(dir.FullName, "Rook.sln")))
                    return dir.FullName;
                dir = dir.Parent;
            }
            throw new System.IO.DirectoryNotFoundException("Could not find repo root");
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Handlers.BimHandlerTests"
```

Expected:

```text
error CS0246: The type or namespace name 'BimHandler' could not be found
```

- [ ] **Step 3: Implement `BimHandler`**

Create `src/Rook/Handlers/BimHandler.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;
using Rook.Bim;

namespace Rook.Handlers
{
    public sealed class BimDispatchResult
    {
        public BimDispatchResult(string json, int httpStatus)
        {
            Json = json;
            HttpStatus = httpStatus;
        }

        public string Json { get; }
        public int HttpStatus { get; }
    }

    public sealed class BimHandler
    {
        internal static readonly IReadOnlyCollection<string> ExpectedBimOps =
            new HashSet<string>(StringComparer.Ordinal)
            {
                "status",
                "active_document",
                "query_elements",
                "element_info",
                "element_parameters",
                "select_elements",
                "clear_selection"
            };

        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            Converters = { new JsonStringEnumConverter(JsonNamingPolicy.SnakeCaseLower) }
        };

        public BimDispatchResult Dispatch(string requestJson)
        {
            try
            {
                using var doc = JsonDocument.Parse(requestJson);
                if (!doc.RootElement.TryGetProperty("op", out var opElement) || opElement.ValueKind != JsonValueKind.String)
                    return Error(BimErrorCode.InvalidScope, "BIM request missing required 'op' discriminator.", 400);

                var op = opElement.GetString() ?? string.Empty;
                if (!ExpectedBimOps.Contains(op))
                    return Error(BimErrorCode.InvalidScope, BuildUnknownOpMessage(op), 400);

                RookBimModuleLoader.TryActivate();
                var runtime = RookBimRuntimeRegistry.Current;

                return op switch
                {
                    "status" => Ok(runtime.Status(), 200),
                    "active_document" => FromApiResponse(runtime.ActiveDocument()),
                    "query_elements" => DispatchQueryElements(requestJson, runtime),
                    "element_info" => DispatchElementInfo(requestJson, runtime),
                    "element_parameters" => DispatchElementParameters(requestJson, runtime),
                    "select_elements" => DispatchSelectElements(requestJson, runtime),
                    "clear_selection" => FromApiResponse(runtime.ClearSelection()),
                    _ => Error(BimErrorCode.InvalidScope, BuildUnknownOpMessage(op), 400)
                };
            }
            catch (JsonException ex)
            {
                return Error(BimErrorCode.InvalidScope, $"Invalid BIM JSON request: {ex.Message}", 400);
            }
            catch (Exception ex)
            {
                return Error(BimErrorCode.InternalError, $"BIM dispatch failed: {ex.Message}", 500);
            }
        }

        internal static string BuildUnknownOpMessage(string op)
        {
            return $"Unknown BIM op '{op}'. Expected one of: {string.Join(", ", ExpectedBimOps)}.";
        }

        private static BimDispatchResult DispatchQueryElements(string requestJson, IRookBimRuntime runtime)
        {
            var request = JsonSerializer.Deserialize<BimQueryElementsRequest>(requestJson, JsonOptions)
                ?? new BimQueryElementsRequest();
            var validation = request.Validate();
            if (!validation.Success)
                return Error(validation.ErrorCode, validation.Message, validation.ErrorCode == BimErrorCode.QueryLimitExceeded ? 400 : 400);
            return FromApiResponse(runtime.QueryElements(request));
        }

        private static BimDispatchResult DispatchElementInfo(string requestJson, IRookBimRuntime runtime)
        {
            var request = JsonSerializer.Deserialize<BimElementRequest>(requestJson, JsonOptions)
                ?? new BimElementRequest();
            return FromApiResponse(runtime.ElementInfo(request));
        }

        private static BimDispatchResult DispatchElementParameters(string requestJson, IRookBimRuntime runtime)
        {
            var request = JsonSerializer.Deserialize<BimElementRequest>(requestJson, JsonOptions)
                ?? new BimElementRequest();
            return FromApiResponse(runtime.ElementParameters(request));
        }

        private static BimDispatchResult DispatchSelectElements(string requestJson, IRookBimRuntime runtime)
        {
            var request = JsonSerializer.Deserialize<BimSelectElementsRequest>(requestJson, JsonOptions)
                ?? new BimSelectElementsRequest();
            return FromApiResponse(runtime.SelectElements(request));
        }

        private static BimDispatchResult FromApiResponse(BimApiResponse response)
        {
            if (response.Success)
                return Ok(response.Data ?? new { }, response.HttpStatus);

            return Error(response.ErrorCode, response.Message, response.HttpStatus, response.Data);
        }

        private static BimDispatchResult Ok(object data, int httpStatus)
        {
            var json = JsonSerializer.Serialize(new
            {
                success = true,
                data
            }, JsonOptions);
            return new BimDispatchResult(json, httpStatus);
        }

        private static BimDispatchResult Error(BimErrorCode code, string message, int httpStatus, object? data = null)
        {
            var json = JsonSerializer.Serialize(new
            {
                success = false,
                errorCode = ToWireCode(code),
                message,
                data
            }, JsonOptions);
            return new BimDispatchResult(json, httpStatus);
        }

        private static string ToWireCode(BimErrorCode code)
        {
            return code switch
            {
                BimErrorCode.RookBimUnavailable => "rookbim_unavailable",
                BimErrorCode.NotRhinoInside => "not_rhino_inside",
                BimErrorCode.RevitUnavailable => "revit_unavailable",
                BimErrorCode.NoActiveDocument => "no_active_document",
                BimErrorCode.NoActiveView => "no_active_view",
                BimErrorCode.InvalidScope => "invalid_scope",
                BimErrorCode.UnboundedDocumentQuery => "unbounded_document_query",
                BimErrorCode.InvalidCategory => "invalid_category",
                BimErrorCode.QueryLimitExceeded => "query_limit_exceeded",
                BimErrorCode.AmbiguousParameter => "ambiguous_parameter",
                BimErrorCode.ElementNotFound => "element_not_found",
                BimErrorCode.DocumentMismatch => "document_mismatch",
                BimErrorCode.LinkedElementUnsupported => "linked_element_unsupported",
                BimErrorCode.CapabilityUnavailable => "capability_unavailable",
                BimErrorCode.SelectionFailed => "selection_failed",
                BimErrorCode.InternalError => "internal_error",
                _ => "internal_error"
            };
        }
    }
}
```

- [ ] **Step 4: Implement reflection module loader**

Create `src/Rook/Bim/RookBimModuleLoader.cs`:

```csharp
using System;
using System.IO;
using System.Reflection;

namespace Rook.Bim
{
    internal static class RookBimModuleLoader
    {
        private static readonly object Sync = new();
        private static bool _attempted;

        public static void TryActivate()
        {
            lock (Sync)
            {
                if (_attempted)
                    return;

                _attempted = true;
                var baseDir = AppContext.BaseDirectory;
                var modulePath = Path.Combine(baseDir, "RookBim.dll");
                if (!File.Exists(modulePath))
                    return;

                try
                {
                    var assembly = Assembly.LoadFrom(modulePath);
                    var moduleType = assembly.GetType("RookBim.RookBimModule", throwOnError: false);
                    var activate = moduleType?.GetMethod("Activate", BindingFlags.Public | BindingFlags.Static);
                    activate?.Invoke(null, Array.Empty<object>());
                }
                catch
                {
                    RookBimRuntimeRegistry.Install(
                        new RookBimUnavailableRuntime("rookbim_unavailable", "RookBIM module failed to activate."),
                        "module-load-failed");
                }
            }
        }
    }
}
```

- [ ] **Step 5: Add managed callback slot**

Modify `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`:

```csharp
private const uint BridgeAbiVersion = 15;
```

Add a static handler field near `VisionDispatchCallback`:

```csharp
private static readonly BimHandler Bim = new();
private static readonly NativeGhBridgeCallback BimDispatchCallback = HandleBimDispatch;
```

Add a struct field after `VisionDispatch`:

```csharp
// ABI v15: BIM domain — single generic dispatch; op discriminator
// is carried in request JSON and routed inside BimHandler.cs.
public IntPtr BimDispatch;
```

Add the registration assignment:

```csharp
BimDispatch = Marshal.GetFunctionPointerForDelegate(BimDispatchCallback),
```

Add callback implementation beside `HandleVisionDispatch`:

```csharp
private static int HandleBimDispatch(
    IntPtr requestJsonUtf8,
    int requestJsonLength,
    IntPtr responseJsonUtf8,
    int responseJsonCapacity,
    IntPtr responseJsonLength,
    IntPtr httpStatusCode)
{
    return ExecuteBimDispatchCallback(
        requestJsonUtf8,
        requestJsonLength,
        responseJsonUtf8,
        responseJsonCapacity,
        responseJsonLength,
        httpStatusCode);
}

private static int ExecuteBimDispatchCallback(
    IntPtr requestJsonUtf8,
    int requestJsonLength,
    IntPtr responseJsonUtf8,
    int responseJsonCapacity,
    IntPtr responseJsonLength,
    IntPtr httpStatusCode)
{
    try
    {
        var requestJson = ReadUtf8(requestJsonUtf8, requestJsonLength);
        var result = Bim.Dispatch(requestJson);
        return WriteUtf8Response(
            responseJsonUtf8,
            responseJsonCapacity,
            responseJsonLength,
            httpStatusCode,
            result.Json,
            result.HttpStatus);
    }
    catch (Exception ex)
    {
        return WriteUtf8Response(
            responseJsonUtf8,
            responseJsonCapacity,
            responseJsonLength,
            httpStatusCode,
            JsonSerializer.Serialize(new
            {
                success = false,
                errorCode = "internal_error",
                message = $"BIM dispatch failed: {ex.Message}"
            }, JsonOptions),
            500);
    }
}
```

- [ ] **Step 6: Run tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~BimHandlerTests|FullyQualifiedName~Rook.Tests.Bim"
```

Expected:

```text
Passed!
```

- [ ] **Step 7: Run source guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/rookbim-boundary-guards.tests.ps1
```

Expected:

```text
rookbim boundary guards passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/Rook/Bim/RookBimModuleLoader.cs src/Rook/Handlers/BimHandler.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook.Tests/Handlers/BimHandlerTests.cs
git commit -m "feat: add rookbim managed dispatch"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: add rookbim managed dispatch
```

---

## Task 4: Native `/bim/*` Proxy Routes

**Files:**
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Create: `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`

- [ ] **Step 1: Write native source tests**

Create `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public sealed class NativeBimDispatchSourceTests
    {
        [Theory]
        [InlineData("Get", "\"/bim/status\"", "status")]
        [InlineData("Get", "\"/bim/active-document\"", "active_document")]
        [InlineData("Post", "\"/bim/query-elements\"", "query_elements")]
        [InlineData("Post", "\"/bim/element-info\"", "element_info")]
        [InlineData("Post", "\"/bim/element-parameters\"", "element_parameters")]
        [InlineData("Post", "\"/bim/select-elements\"", "select_elements")]
        [InlineData("Post", "\"/bim/clear-selection\"", "clear_selection")]
        public void RookServer_RegistersBimRoutes(string method, string routeLiteral, string op)
        {
            var source = Read("src", "RookNative", "RookServer.cpp");

            Assert.Contains($"m_server->{method}({routeLiteral}", source);
            Assert.Contains($"ForwardBimDispatch(res, \"{op}\"", source);
        }

        [Fact]
        public void BimRoutes_UseSingleOpaqueManagedDispatch()
        {
            var source = Read("src", "RookNative", "RookServer.cpp");

            Assert.Contains("InvokeBimDispatchWithBody(", source);
            Assert.Contains("body[\"op\"] = op;", source);
            Assert.DoesNotContain("Autodesk.Revit", source);
            Assert.DoesNotContain("/revit/", source);
            Assert.DoesNotContain("/rookbim/", source);
        }

        [Fact]
        public void NativeBridge_ABI15CarriesBimDispatch()
        {
            var source = Read("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

            Assert.Contains("constexpr uint32_t kGhBridgeAbiVersion = 15;", source);
            Assert.Contains("GhBridgeCallbackFn bim_dispatch = nullptr;", source);
            Assert.Contains("registration.bim_dispatch == nullptr", source);
            Assert.Contains("InvokeBimDispatchWithBody", source);
        }

        private static string Read(params string[] parts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var path = Path.Combine(dir.FullName, Path.Combine(parts));
                if (File.Exists(path))
                    return File.ReadAllText(path);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(string.Join("/", parts));
        }
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeBimDispatchSourceTests"
```

Expected:

```text
Failed! - Failed: 3
```

- [ ] **Step 3: Add native callback registration**

In `src/RookNative/Handlers/GrasshopperProxyHandler.h`, add:

```cpp
// Invokes the managed BIM dispatch bridge callback (ABI v15). Single
// generic dispatch for all /bim/* routes; the op discriminator is
// carried in request JSON and routed inside BimHandler.cs.
ManagedCreateInvokeResult InvokeBimDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);
```

In `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`, update:

```cpp
constexpr uint32_t kGhBridgeAbiVersion = 15;
```

Add field to `GhBridgeRegistration` after `vision_dispatch`:

```cpp
GhBridgeCallbackFn bim_dispatch = nullptr;
```

Update the registration completeness check so it requires BIM dispatch:

```cpp
&& registration.vision_dispatch != nullptr
&& registration.bim_dispatch != nullptr;
```

Add invocation helper near `InvokeVisionDispatchWithBody`:

```cpp
ManagedCreateInvokeResult InvokeBimDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error)
{
    auto registration = SnapshotGhBridgeRegistration();
    if (registration.bim_dispatch == nullptr)
    {
        error = "BIM dispatch callback is not registered.";
        return ManagedCreateInvokeResult::Unavailable;
    }

    return InvokeManagedCallback(
        registration.bim_dispatch,
        requestJson,
        responseJson,
        statusCode,
        error);
}
```

- [ ] **Step 4: Add local BIM proxy helpers in `RookServer.cpp`**

In `src/RookNative/RookServer.cpp`, add anonymous-namespace helpers near the existing local helpers:

```cpp
bool ParseBimBodyAsObject(
    const httplib::Request& req,
    httplib::Response& res,
    const char* op,
    nlohmann::json& out)
{
    if (req.body.empty())
    {
        out = nlohmann::json::object();
        return true;
    }

    try
    {
        out = nlohmann::json::parse(req.body);
    }
    catch (const std::exception& ex)
    {
        CRookServer::SendError(
            res,
            std::string("Invalid JSON body for /bim/") + op + ": " + ex.what());
        res.status = 400;
        res.set_header("X-Rook-Bim-Op", op);
        return false;
    }

    if (!out.is_object())
    {
        CRookServer::SendError(
            res,
            std::string("BIM request body must be a JSON object (got ") +
                out.type_name() + ").");
        res.status = 400;
        res.set_header("X-Rook-Bim-Op", op);
        return false;
    }

    return true;
}

void ForwardBimDispatch(httplib::Response& res, const char* op, nlohmann::json& body)
{
    body["op"] = op;

    const std::string requestJson = body.dump();
    std::string responseJson;
    int statusCode = 0;
    std::string invokeError;
    const auto result = Rook::Handlers::InvokeBimDispatchWithBody(
        requestJson,
        responseJson,
        statusCode,
        invokeError);

    switch (result)
    {
    case Rook::Handlers::ManagedCreateInvokeResult::Ok:
        res.status = statusCode == 0 ? 200 : statusCode;
        res.set_content(responseJson, "application/json");
        res.set_header("X-Rook-Bim-Op", op);
        return;
    case Rook::Handlers::ManagedCreateInvokeResult::Unavailable:
        CRookServer::SendError(
            res,
            "BIM routes require the Rook companion plugin and BIM dispatch callback.");
        res.status = 503;
        res.set_header("X-Rook-Bim-Op", op);
        return;
    case Rook::Handlers::ManagedCreateInvokeResult::Failed:
    default:
        CRookServer::SendError(
            res,
            std::string("BIM dispatch failed for /bim/") + op + ": " + invokeError);
        res.status = 500;
        res.set_header("X-Rook-Bim-Op", op);
        return;
    }
}

void DispatchBimOp(const httplib::Request& req, httplib::Response& res, const char* op)
{
    nlohmann::json body;
    if (!ParseBimBodyAsObject(req, res, op, body)) return;
    ForwardBimDispatch(res, op, body);
}
```

If `InvokeBimDispatchWithBody` is not visible through `Handlers/GrasshopperProxyHandler.h`, include that header before using the helper.

- [ ] **Step 5: Register `/bim/*` routes in `CRookServer::RegisterRoutes`**

In `src/RookNative/RookServer.cpp`, add route registration near other companion-backed domains:

```cpp
// RookBIM Phase 1: public /bim/* route surface. Native owns HTTP
// transport and op injection only; managed BimHandler.cs owns schema
// validation and runtime dispatch. Selection routes mutate Revit UI
// selection only, not the Revit document.
m_server->Get("/bim/status", [](const httplib::Request& req, httplib::Response& res) {
    nlohmann::json body = nlohmann::json::object();
    ForwardBimDispatch(res, "status", body);
});
m_server->Get("/bim/active-document", [](const httplib::Request& req, httplib::Response& res) {
    nlohmann::json body = nlohmann::json::object();
    ForwardBimDispatch(res, "active_document", body);
});
m_server->Post("/bim/query-elements", [](const httplib::Request& req, httplib::Response& res) {
    DispatchBimOp(req, res, "query_elements");
});
m_server->Post("/bim/element-info", [](const httplib::Request& req, httplib::Response& res) {
    DispatchBimOp(req, res, "element_info");
});
m_server->Post("/bim/element-parameters", [](const httplib::Request& req, httplib::Response& res) {
    DispatchBimOp(req, res, "element_parameters");
});
m_server->Post("/bim/select-elements", [](const httplib::Request& req, httplib::Response& res) {
    DispatchBimOp(req, res, "select_elements");
});
m_server->Post("/bim/clear-selection", [](const httplib::Request& req, httplib::Response& res) {
    nlohmann::json body = nlohmann::json::object();
    ForwardBimDispatch(res, "clear_selection", body);
});
```

- [ ] **Step 6: Run managed/source tests and guard**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~NativeBimDispatchSourceTests|FullyQualifiedName~BimHandlerTests"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/rookbim-boundary-guards.tests.ps1
```

Expected:

```text
Passed!
rookbim boundary guards passed
```

- [ ] **Step 7: Build native only if Rhino/MFC toolchain is available**

Run from a fresh Developer Command Prompt or through `cmd /c`:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected on this machine when the Rhino 8 C++ SDK and complete MFC payload are installed:

```text
Build succeeded.
```

If this command fails because Rhino SDK or MFC is unavailable, keep the exact error in the task notes and do not claim native build verification.

- [ ] **Step 8: Commit**

Run:

```powershell
git add src/RookNative/Handlers/GrasshopperProxyHandler.h src/RookNative/Handlers/GrasshopperProxyHandler.cpp src/RookNative/RookServer.cpp src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs
git commit -m "feat: proxy rookbim native routes"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: proxy rookbim native routes
```

---

## Task 5: MCP `rookbim_*` Tool Surface

**Files:**
- Create: `mcp_server/tests/test_rookbim_mcp_tools.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/src/rook/context.py` if the context registry requires explicit categories.

- [ ] **Step 1: Write MCP tests**

Create `mcp_server/tests/test_rookbim_mcp_tools.py`:

```python
import asyncio

from rook import server
from rook.agent import tool_dispatcher, tool_groups

ROOKBIM_ROUTES = {
    "rookbim_status": ("/bim/status", "GET"),
    "rookbim_active_document": ("/bim/active-document", "GET"),
    "rookbim_query_elements": ("/bim/query-elements", "POST"),
    "rookbim_element_info": ("/bim/element-info", "POST"),
    "rookbim_element_parameters": ("/bim/element-parameters", "POST"),
    "rookbim_select_elements": ("/bim/select-elements", "POST"),
    "rookbim_clear_selection": ("/bim/clear-selection", "POST"),
}


def _tool_map():
    tools = asyncio.run(server.list_tools())
    return {tool.name: tool for tool in tools}


def test_rookbim_tools_are_registered():
    tools = _tool_map()
    for name in ROOKBIM_ROUTES:
        assert name in tools


def test_rookbim_bridge_routes():
    for name, route in ROOKBIM_ROUTES.items():
        assert tool_dispatcher.BRIDGE_ROUTES[name] == route


def test_query_elements_schema_defaults_and_bounds():
    schema = _tool_map()["rookbim_query_elements"].inputSchema
    props = schema["properties"]

    assert props["scope"]["enum"] == ["active_view", "document"]
    assert props["scope"]["default"] == "active_view"
    assert props["limit"]["default"] == 100
    assert props["limit"]["maximum"] == 1000
    assert props["filters"]["items"]["properties"]["operation"]["enum"] == [
        "equals",
        "not_equals",
        "contains",
        "is_empty",
        "is_not_empty",
    ]


def test_identity_envelope_schema_carries_document_guid_source():
    tools = _tool_map()
    for name in ("rookbim_element_info", "rookbim_element_parameters"):
        identity = tools[name].inputSchema["properties"]["identity"]["properties"]
        assert identity["source"]["const"] == "revit"
        assert "documentGuid" in identity
        assert identity["documentGuid"].get("type") == ["string", "null"]
        assert identity["documentGuidSource"]["enum"] == [
            "revit_persistent_guid",
            "path_fallback",
            "unavailable",
        ]
        assert "documentPath" in identity
        assert "elementId" in identity
        assert "uniqueId" in identity
        assert "fullUniqueId" in identity
        assert "linked" in identity
        assert "linkInstanceId" in identity
        assert "linkedElementUniqueId" in identity


def test_rookbim_tool_groups_are_registered():
    assert "rookbim" in tool_groups.TOOL_GROUPS
    assert set(tool_groups.TOOL_GROUPS["rookbim"]) == set(ROOKBIM_ROUTES)

    assert "rookbim_readonly" in tool_groups.TOOL_GROUPS
    readonly = set(tool_groups.TOOL_GROUPS["rookbim_readonly"])
    assert "rookbim_select_elements" not in readonly
    assert "rookbim_clear_selection" not in readonly
    assert readonly == set(ROOKBIM_ROUTES) - {
        "rookbim_select_elements",
        "rookbim_clear_selection",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
pytest mcp_server/tests/test_rookbim_mcp_tools.py -q
```

Expected:

```text
FAILED mcp_server/tests/test_rookbim_mcp_tools.py
```

- [ ] **Step 3: Add bridge routes**

Modify `mcp_server/src/rook/agent/tool_dispatcher.py` in `BRIDGE_ROUTES`:

```python
    # --- RookBIM Phase 1 ---
    "rookbim_status":             ("/bim/status", "GET"),
    "rookbim_active_document":    ("/bim/active-document", "GET"),
    "rookbim_query_elements":     ("/bim/query-elements", "POST"),
    "rookbim_element_info":       ("/bim/element-info", "POST"),
    "rookbim_element_parameters": ("/bim/element-parameters", "POST"),
    "rookbim_select_elements":    ("/bim/select-elements", "POST"),
    "rookbim_clear_selection":    ("/bim/clear-selection", "POST"),
```

- [ ] **Step 4: Add MCP tool schemas**

Modify `mcp_server/src/rook/server.py` in `list_tools()` by adding these BIM tool definitions:

```python
        Tool(
            name="rookbim_status",
            description="Return structured RookBIM availability and host evidence.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="rookbim_active_document",
            description="Return active Revit document identity and host evidence.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="rookbim_query_elements",
            description="Query bounded live Revit elements by active view or document scope. Returns summary identities only.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["active_view", "document"],
                        "default": "active_view",
                    },
                    "category": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1000,
                        "default": 100,
                    },
                    "filters": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "parameter": {"type": "string"},
                                "operation": {
                                    "type": "string",
                                    "enum": [
                                        "equals",
                                        "not_equals",
                                        "contains",
                                        "is_empty",
                                        "is_not_empty",
                                    ],
                                },
                                "value": {"type": "string"},
                            },
                            "required": ["parameter", "operation"],
                            "additionalProperties": False,
                        },
                        "default": [],
                    },
                },
                "additionalProperties": False,
            },
        ),
        Tool(
            name="rookbim_element_info",
            description="Resolve one live Revit element identity envelope and return category/type/location-ish summary.",
            inputSchema=_rookbim_identity_tool_schema(),
        ),
        Tool(
            name="rookbim_element_parameters",
            description="Return serialized parameter evidence for one live Revit element identity envelope.",
            inputSchema=_rookbim_identity_tool_schema(),
        ),
        Tool(
            name="rookbim_select_elements",
            description="Select exact returned Revit element identities in the Revit UI. Mutates UI selection only, not the Revit document.",
            inputSchema={
                "type": "object",
                "properties": {
                    "identities": {
                        "type": "array",
                        "items": _rookbim_identity_schema(),
                        "minItems": 1,
                        "maxItems": 1000,
                    }
                },
                "required": ["identities"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="rookbim_clear_selection",
            description="Clear Revit UI selection. Mutates UI selection only, not the Revit document.",
            inputSchema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
```

Add helpers near other schema helper functions in `server.py`:

```python
def _rookbim_identity_schema():
    return {
        "type": "object",
        "properties": {
            "source": {"type": "string", "const": "revit"},
            "documentGuid": {"type": ["string", "null"]},
            "documentGuidSource": {
                "type": "string",
                "enum": ["revit_persistent_guid", "path_fallback", "unavailable"],
            },
            "documentTitle": {"type": "string"},
            "documentPath": {"type": ["string", "null"]},
            "elementId": {"type": ["integer", "null"]},
            "uniqueId": {"type": ["string", "null"]},
            "fullUniqueId": {"type": ["string", "null"]},
            "linked": {"type": "boolean"},
            "linkInstanceId": {"type": ["integer", "null"]},
            "linkInstanceUniqueId": {"type": ["string", "null"]},
            "linkedDocumentGuid": {"type": ["string", "null"]},
            "linkedElementId": {"type": ["integer", "null"]},
            "linkedElementUniqueId": {"type": ["string", "null"]},
            "resolved": {"type": "boolean"},
            "confidence": {
                "type": "string",
                "enum": ["exact", "inferred", "unresolved", "unsupported"],
            },
        },
        "required": ["documentGuidSource"],
        "additionalProperties": False,
    }


def _rookbim_identity_tool_schema():
    return {
        "type": "object",
        "properties": {
            "identity": _rookbim_identity_schema(),
        },
        "required": ["identity"],
        "additionalProperties": False,
    }
```

- [ ] **Step 5: Add tool groups**

Modify `mcp_server/src/rook/agent/tool_groups.py`:

```python
    "rookbim": [
        "rookbim_status",
        "rookbim_active_document",
        "rookbim_query_elements",
        "rookbim_element_info",
        "rookbim_element_parameters",
        "rookbim_select_elements",
        "rookbim_clear_selection",
    ],
    "rookbim_readonly": [
        "rookbim_status",
        "rookbim_active_document",
        "rookbim_query_elements",
        "rookbim_element_info",
        "rookbim_element_parameters",
    ],
```

Add `"rookbim_readonly"` to `READONLY_ALLOWED_GROUPS`. Do not add `rookbim_select_elements` or `rookbim_clear_selection` to a readonly group because they mutate UI selection.

- [ ] **Step 6: Update context metadata if required**

If `mcp_server/src/rook/context.py` has explicit tool-category maps, add:

```python
"rookbim_status": "rookbim",
"rookbim_active_document": "rookbim",
"rookbim_query_elements": "rookbim",
"rookbim_element_info": "rookbim",
"rookbim_element_parameters": "rookbim",
"rookbim_select_elements": "rookbim",
"rookbim_clear_selection": "rookbim",
```

If the file has no explicit registry for bridge tools, do not edit it.

- [ ] **Step 7: Run MCP tests**

Run:

```powershell
pytest mcp_server/tests/test_rookbim_mcp_tools.py -q
pytest mcp_server/tests/test_dispatcher_safety.py -q
```

Expected:

```text
passed
```

- [ ] **Step 8: Commit**

Run:

```powershell
git add mcp_server/src/rook/agent/tool_dispatcher.py mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/context.py mcp_server/tests/test_rookbim_mcp_tools.py
git commit -m "feat: add rookbim mcp tools"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: add rookbim mcp tools
```

---

## Task 6: Optional `src/RookBim` Module Skeleton

**Files:**
- Create: `src/RookBim/RookBim.csproj`
- Create: `src/RookBim/RookBimModule.cs`
- Create: `src/RookBim/Revit/RevitRookBimRuntime.cs`
- Create: `src/RookBim.Tests/RookBim.Tests.csproj`
- Create: `src/RookBim.Tests/RookBimModuleSourceTests.cs`
- Modify: `src/Rook/Rook.csproj`

- [ ] **Step 1: Write optional module source tests**

Create `src/RookBim.Tests/RookBimModuleSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace RookBim.Tests
{
    public sealed class RookBimModuleSourceTests
    {
        [Fact]
        public void RookBimProject_TargetsNet48AndReferencesRevitOnlyHere()
        {
            var project = Read("src", "RookBim", "RookBim.csproj");

            Assert.Contains("<TargetFramework>net48</TargetFramework>", project);
            Assert.Contains("Include=\"RevitAPI\"", project);
            Assert.Contains("Include=\"RevitAPIUI\"", project);
            Assert.Contains("<Private>false</Private>", project);
        }

        [Fact]
        public void CoreProject_DoesNotReferenceRookBimProject()
        {
            var project = Read("src", "Rook", "Rook.csproj");

            Assert.DoesNotContain("RookBim.csproj", project);
            Assert.DoesNotContain("Autodesk.Revit", project);
            Assert.DoesNotContain("RevitAPI", project);
        }

        [Fact]
        public void MainSolution_DoesNotIncludeOptionalRookBimProjects()
        {
            var solution = Read("Rook.sln");

            Assert.DoesNotContain("RookBim.csproj", solution);
            Assert.DoesNotContain("RookBim.Tests.csproj", solution);
        }

        [Fact]
        public void ModuleActivation_InstallsRuntimeThroughCoreRegistry()
        {
            var source = Read("src", "RookBim", "RookBimModule.cs");

            Assert.Contains("public static void Activate()", source);
            Assert.Contains("RookBimRuntimeRegistry.Install", source);
            Assert.Contains("new RevitRookBimRuntime()", source);
        }

        private static string Read(params string[] parts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var path = Path.Combine(dir.FullName, Path.Combine(parts));
                if (File.Exists(path))
                    return File.ReadAllText(path);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(string.Join("/", parts));
        }
    }
}
```

- [ ] **Step 2: Create project files**

Create `src/RookBim/RookBim.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <Nullable>enable</Nullable>
    <LangVersion>latest</LangVersion>
    <RevitInstallDir Condition="'$(RevitInstallDir)' == ''">$(ProgramFiles)\Autodesk\Revit 2024</RevitInstallDir>
  </PropertyGroup>

  <ItemGroup>
    <ProjectReference Include="..\Rook\Rook.csproj" />
  </ItemGroup>

  <ItemGroup>
    <Reference Include="RevitAPI">
      <HintPath>$(RevitInstallDir)\RevitAPI.dll</HintPath>
      <Private>false</Private>
    </Reference>
    <Reference Include="RevitAPIUI">
      <HintPath>$(RevitInstallDir)\RevitAPIUI.dll</HintPath>
      <Private>false</Private>
    </Reference>
  </ItemGroup>

  <Target Name="CopyRookBimToRookRuntime" AfterTargets="Build"
          Condition="Exists('..\Rook\bin\$(Configuration)\$(TargetFramework)')">
    <Copy SourceFiles="$(TargetPath)"
          DestinationFolder="..\Rook\bin\$(Configuration)\$(TargetFramework)"
          SkipUnchangedFiles="true" />
    <Copy SourceFiles="$(TargetDir)$(TargetName).pdb"
          DestinationFolder="..\Rook\bin\$(Configuration)\$(TargetFramework)"
          SkipUnchangedFiles="true"
          Condition="Exists('$(TargetDir)$(TargetName).pdb')" />
  </Target>
</Project>
```

Create `src/RookBim.Tests/RookBim.Tests.csproj`:

```xml
<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net48</TargetFramework>
    <Nullable>enable</Nullable>
    <LangVersion>latest</LangVersion>
    <IsPackable>false</IsPackable>
    <IsTestProject>true</IsTestProject>
  </PropertyGroup>

  <ItemGroup>
    <PackageReference Include="Microsoft.NET.Test.Sdk" Version="17.11.1" />
    <PackageReference Include="xunit" Version="2.9.2" />
    <PackageReference Include="xunit.runner.visualstudio" Version="2.8.2" />
  </ItemGroup>
</Project>
```

- [ ] **Step 3: Add module activation skeleton**

Create `src/RookBim/RookBimModule.cs`:

```csharp
using Rook.Bim;
using RookBim.Revit;

namespace RookBim
{
    public static class RookBimModule
    {
        public static void Activate()
        {
            RookBimRuntimeRegistry.Install(
                new RevitRookBimRuntime(),
                "RookBim.dll");
        }
    }
}
```

Create `src/RookBim/Revit/RevitRookBimRuntime.cs`:

```csharp
using Rook.Bim;

namespace RookBim.Revit
{
    public sealed class RevitRookBimRuntime : IRookBimRuntime
    {
        private readonly RookBimUnavailableRuntime _fallback =
            new("not_rhino_inside", "RookBIM is loaded, but Rhino is not running inside Revit.");

        public BimStatusResponse Status() => _fallback.Status();
        public BimApiResponse ActiveDocument() => _fallback.ActiveDocument();
        public BimApiResponse QueryElements(BimQueryElementsRequest request) => _fallback.QueryElements(request);
        public BimApiResponse ElementInfo(BimElementRequest request) => _fallback.ElementInfo(request);
        public BimApiResponse ElementParameters(BimElementRequest request) => _fallback.ElementParameters(request);
        public BimApiResponse SelectElements(BimSelectElementsRequest request) => _fallback.SelectElements(request);
        public BimApiResponse ClearSelection() => _fallback.ClearSelection();
    }
}
```

- [ ] **Step 4: Preserve main solution build isolation**

Run:

```powershell
Select-String -Path Rook.sln -Pattern "RookBim" -Quiet
```

Expected:

```text
False
```

Do not add `RookBim.csproj` or `RookBim.Tests.csproj` to `Rook.sln`. Build and test the optional module by direct project path so ordinary solution builds keep working on machines without Revit installed.

- [ ] **Step 5: Add optional copy item to `Rook.csproj`**

Add to `src/Rook/Rook.csproj`:

```xml
  <ItemGroup>
    <None Include="..\RookBim\bin\$(Configuration)\$(TargetFramework)\RookBim.dll"
          Link="RookBim.dll"
          CopyToOutputDirectory="PreserveNewest"
          Condition="Exists('..\RookBim\bin\$(Configuration)\$(TargetFramework)\RookBim.dll')" />
    <None Include="..\RookBim\bin\$(Configuration)\$(TargetFramework)\RookBim.pdb"
          Link="RookBim.pdb"
          CopyToOutputDirectory="PreserveNewest"
          Condition="Exists('..\RookBim\bin\$(Configuration)\$(TargetFramework)\RookBim.pdb')" />
  </ItemGroup>
```

This copies an already-built optional module when present; it does not create a project reference from `src/Rook` to `src/RookBim`.

- [ ] **Step 6: Run tests and build**

Run:

```powershell
dotnet test src/RookBim.Tests/RookBim.Tests.csproj
dotnet build src/RookBim/RookBim.csproj -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/rookbim-boundary-guards.tests.ps1
```

Expected:

```text
Passed!
Build succeeded.
rookbim boundary guards passed
```

If `C:\Program Files\Autodesk\Revit 2024\RevitAPI.dll` is absent, first run:

```powershell
Get-ChildItem "C:\Program Files\Autodesk" -Recurse -Filter RevitAPI.dll -ErrorAction SilentlyContinue | Select-Object -First 5 FullName
```

Use the containing Revit install directory as the `-p:RevitInstallDir` value.

- [ ] **Step 7: Commit**

Run:

```powershell
git add src/Rook/Rook.csproj src/RookBim src/RookBim.Tests
git commit -m "feat: add optional rookbim module"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: add optional rookbim module
```

---

## Task 7: Revit API Dispatch Proof, Status, and Active Document

**Files:**
- Create: `src/RookBim/Revit/RevitApiDispatcher.cs`
- Create: `src/RookBim/Revit/RevitContext.cs`
- Create: `src/RookBim/Revit/RevitIdentitySerializer.cs`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`

- [ ] **Step 1: Verify SDK patterns before coding**

Run:

```powershell
rg -n "ExternalEvent|IExternalEventHandler|UIApplication|ActiveUIDocument|Document" "C:/Revit 2024.2 SDK/Samples/ModelessDialog" "C:/Revit 2024.2 SDK/Samples"
```

Expected evidence to capture in implementation notes:

```text
ExternalEvent.Create(handler)
IExternalEventHandler.Execute(UIApplication app)
UIApplication.ActiveUIDocument
UIDocument.Document
```

- [ ] **Step 2: Implement dispatcher**

Create `src/RookBim/Revit/RevitApiDispatcher.cs`:

```csharp
using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.UI;

namespace RookBim.Revit
{
    internal sealed class RevitApiDispatcher : IExternalEventHandler
    {
        private readonly ConcurrentQueue<WorkItem> _queue = new();
        private readonly ExternalEvent _externalEvent;

        public RevitApiDispatcher()
        {
            _externalEvent = ExternalEvent.Create(this);
        }

        public string GetName() => "RookBIM Revit API Dispatcher";

        public void Execute(UIApplication app)
        {
            while (_queue.TryDequeue(out var item))
            {
                try
                {
                    item.Complete(item.Execute(app));
                }
                catch (Exception ex)
                {
                    item.Fail(ex);
                }
            }
        }

        public T Invoke<T>(Func<UIApplication, T> action, TimeSpan timeout)
        {
            var item = new WorkItem(app => action(app));
            _queue.Enqueue(item);
            _externalEvent.Raise();

            if (!item.Task.Wait(timeout))
                throw new TimeoutException("Timed out waiting for Revit API ExternalEvent.");

            return (T)item.Task.Result;
        }

        private sealed class WorkItem
        {
            private readonly TaskCompletionSource<object> _completion =
                new(TaskCreationOptions.RunContinuationsAsynchronously);

            public WorkItem(Func<UIApplication, object> execute)
            {
                Execute = execute;
            }

            public Func<UIApplication, object> Execute { get; }
            public Task<object> Task => _completion.Task;
            public void Complete(object result) => _completion.TrySetResult(result);
            public void Fail(Exception ex) => _completion.TrySetException(ex);
        }
    }
}
```

If `ExternalEvent.Create(this)` fails outside a valid Revit API context during live validation, replace eager construction with a `TryCreate(UIApplication app)` path discovered from SDK/RhinoInside validation and keep `Status()` unavailable until dispatcher creation succeeds.

- [ ] **Step 3: Implement context and identity serializer**

Create `src/RookBim/Revit/RevitContext.cs`:

```csharp
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;

namespace RookBim.Revit
{
    internal static class RevitContext
    {
        public static Document? ActiveDocument(UIApplication app)
        {
            return app.ActiveUIDocument?.Document;
        }

        public static UIDocument? ActiveUiDocument(UIApplication app)
        {
            return app.ActiveUIDocument;
        }
    }
}
```

Create `src/RookBim/Revit/RevitIdentitySerializer.cs`:

```csharp
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal static class RevitIdentitySerializer
    {
        public static BimDocumentIdentity Document(Document document)
        {
            var guid = TryGetPersistentGuid(document, out var source);
            return new BimDocumentIdentity
            {
                Guid = guid,
                GuidSource = source,
                Title = document.Title ?? string.Empty,
                Path = string.IsNullOrWhiteSpace(document.PathName) ? null : document.PathName,
                IsFamilyDocument = document.IsFamilyDocument,
                IsWorkshared = document.IsWorkshared
            };
        }

        public static BimViewIdentity View(View view)
        {
            return new BimViewIdentity
            {
                Id = view.Id.IntegerValue,
                UniqueId = string.IsNullOrWhiteSpace(view.UniqueId) ? null : view.UniqueId,
                Name = view.Name ?? string.Empty
            };
        }

        public static BimElementIdentity Element(Document document, Element element)
        {
            var doc = Document(document);
            return new BimElementIdentity
            {
                Source = "revit",
                DocumentGuid = doc.Guid,
                DocumentGuidSource = doc.GuidSource,
                DocumentTitle = doc.Title,
                DocumentPath = doc.Path,
                ElementId = element.Id.IntegerValue,
                UniqueId = element.UniqueId,
                FullUniqueId = element.UniqueId,
                Linked = false,
                Resolved = true,
                Confidence = BimIdentityConfidence.Exact
            };
        }

        private static string? TryGetPersistentGuid(Document document, out BimDocumentGuidSource source)
        {
            var centralGuid = document.GetWorksharingCentralGUID();
            if (centralGuid != System.Guid.Empty)
            {
                source = BimDocumentGuidSource.RevitPersistentGuid;
                return centralGuid.ToString("D");
            }

            source = BimDocumentGuidSource.Unavailable;
            return null;
        }
    }
}
```

If SDK validation shows `GetWorksharingCentralGUID()` is not appropriate for non-workshared documents, keep `Guid = null` and `GuidSource = Unavailable` rather than inventing a path-derived stable identity.

- [ ] **Step 4: Implement status and active document**

Modify `src/RookBim/Revit/RevitRookBimRuntime.cs`:

```csharp
using System;
using Rook.Bim;

namespace RookBim.Revit
{
    public sealed class RevitRookBimRuntime : IRookBimRuntime
    {
        private readonly Lazy<RevitApiDispatcher> _dispatcher =
            new(() => new RevitApiDispatcher());

        public BimStatusResponse Status()
        {
            try
            {
                return _dispatcher.Value.Invoke(app =>
                {
                    var doc = RevitContext.ActiveDocument(app);
                    return new BimStatusResponse
                    {
                        Available = doc != null,
                        Runtime = "rookbim",
                        ErrorCode = doc == null ? "no_active_document" : null,
                        Message = doc == null ? "RhinoInside/Revit is available but no active Revit document is open." : "RookBIM is available.",
                        Host = "revit",
                        Module = "RookBim.dll"
                    };
                }, TimeSpan.FromSeconds(5));
            }
            catch (Exception ex)
            {
                return new BimStatusResponse
                {
                    Available = false,
                    Runtime = "rookbim",
                    ErrorCode = "not_rhino_inside",
                    Message = "RookBIM could not enter Revit API context: " + ex.Message,
                    Host = "unknown",
                    Module = "RookBim.dll"
                };
            }
        }

        public BimApiResponse ActiveDocument()
        {
            return InvokeRead(app =>
            {
                var doc = RevitContext.ActiveDocument(app);
                if (doc == null)
                    return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);

                var view = app.ActiveUIDocument?.ActiveView;
                return BimApiResponse.Ok(new
                {
                    document = RevitIdentitySerializer.Document(doc),
                    view = view == null ? null : RevitIdentitySerializer.View(view)
                });
            });
        }

        public BimApiResponse QueryElements(BimQueryElementsRequest request) =>
            BimApiResponse.Fail(BimErrorCode.CapabilityUnavailable, "query_elements is not implemented in this slice.", 501);

        public BimApiResponse ElementInfo(BimElementRequest request) =>
            BimApiResponse.Fail(BimErrorCode.CapabilityUnavailable, "element_info is not implemented in this slice.", 501);

        public BimApiResponse ElementParameters(BimElementRequest request) =>
            BimApiResponse.Fail(BimErrorCode.CapabilityUnavailable, "element_parameters is not implemented in this slice.", 501);

        public BimApiResponse SelectElements(BimSelectElementsRequest request) =>
            BimApiResponse.Fail(BimErrorCode.CapabilityUnavailable, "select_elements is not implemented in this slice.", 501);

        public BimApiResponse ClearSelection() =>
            BimApiResponse.Fail(BimErrorCode.CapabilityUnavailable, "clear_selection is not implemented in this slice.", 501);

        private BimApiResponse InvokeRead(Func<Autodesk.Revit.UI.UIApplication, BimApiResponse> action)
        {
            try
            {
                return _dispatcher.Value.Invoke(action, TimeSpan.FromSeconds(10));
            }
            catch (Exception ex)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NotRhinoInside,
                    "RookBIM could not enter Revit API context: " + ex.Message,
                    503);
            }
        }
    }
}
```

- [ ] **Step 5: Build and live-validate before continuing**

Run:

```powershell
dotnet build src/RookBim/RookBim.csproj -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
dotnet build src/Rook/Rook.csproj -f net48
```

Expected:

```text
Build succeeded.
Build succeeded.
```

Then deploy locally using the repo's existing local deployment workflow. If using the Rook deploy skill, run the local deploy process for `net48` and copy `RookBim.dll` into the installed Rook managed runtime folder.

Manual live validation inside RhinoInside/Revit:

```powershell
$env:PYTHONPATH = "mcp_server/src"
@'
import asyncio, json
from rook.bridge import call_rhino, discovery_diagnostics

async def main():
    print(json.dumps(discovery_diagnostics(), indent=2))
    print(json.dumps(await call_rhino("/bim/status", "GET"), indent=2))
    print(json.dumps(await call_rhino("/bim/active-document", "GET"), indent=2))

asyncio.run(main())
'@ | python -
```

Expected successful status shape:

```json
{
  "success": true,
  "data": {
    "available": true,
    "runtime": "rookbim",
    "errorCode": null,
    "host": "revit",
    "module": "RookBim.dll"
  }
}
```

Expected standalone Rhino status shape:

```json
{
  "success": true,
  "data": {
    "available": false,
    "errorCode": "not_rhino_inside"
  }
}
```

Do not proceed to query services until this live validation proves either `ExternalEvent` works or a validated RhinoInside API context path replaces it.

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/RookBim/Revit
git commit -m "feat: prove rookbim revit context"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: prove rookbim revit context
```

---

## Task 8: Query Elements Service

**Files:**
- Create: `src/RookBim/Revit/RevitQueryService.cs`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`

- [ ] **Step 1: Verify collector and category APIs in SDK**

Run:

```powershell
rg -n "FilteredElementCollector|OfCategory|WhereElementIsNotElementType|OwnedByView|BuiltInCategory|Category" "C:/Revit 2024.2 SDK/Samples"
```

Expected evidence to capture in implementation notes:

```text
new FilteredElementCollector(document)
new FilteredElementCollector(document, view.Id)
collector.WhereElementIsNotElementType()
collector.OfCategory(builtInCategory)
```

- [ ] **Step 2: Implement query service**

Create `src/RookBim/Revit/RevitQueryService.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitQueryService
    {
        public BimApiResponse Query(Document document, View? activeView, BimQueryElementsRequest request)
        {
            if (request.EffectiveScope == BimQueryScope.ActiveView && activeView == null)
            {
                return BimApiResponse.Fail(
                    BimErrorCode.NoActiveView,
                    "active_view scope requires an active Revit view.",
                    409);
            }

            var collector = request.EffectiveScope == BimQueryScope.ActiveView
                ? new FilteredElementCollector(document, activeView!.Id)
                : new FilteredElementCollector(document);

            collector.WhereElementIsNotElementType();

            if (!string.IsNullOrWhiteSpace(request.Category))
            {
                var category = ResolveBuiltInCategory(request.Category);
                if (category == null)
                    return BimApiResponse.Fail(BimErrorCode.InvalidCategory, $"Unknown Revit category '{request.Category}'.", 400);
                collector.OfCategory(category.Value);
            }

            var allCandidates = collector.ToElements();
            var parameterAmbiguity = PreflightFilterParameterAmbiguity(allCandidates, request.Filters);
            if (parameterAmbiguity != null)
                return parameterAmbiguity;

            var missingCounts = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);
            var matched = new List<Element>();

            foreach (var element in allCandidates)
            {
                if (MatchesAllFilters(element, request.Filters, missingCounts))
                {
                    matched.Add(element);
                    if (matched.Count >= request.EffectiveLimit)
                        break;
                }
            }

            var totalMatchedUpToCap = matched.Count;
            var truncated = totalMatchedUpToCap >= request.EffectiveLimit && allCandidates.Count > totalMatchedUpToCap;

            var results = matched.Select(element => new
            {
                identity = RevitIdentitySerializer.Element(document, element),
                name = element.Name,
                category = new
                {
                    id = element.Category?.Id.IntegerValue,
                    name = element.Category?.Name
                },
                type = BuildTypeSummary(document, element)
            }).ToList();

            return BimApiResponse.Ok(new
            {
                document = RevitIdentitySerializer.Document(document),
                scope = request.EffectiveScope == BimQueryScope.ActiveView ? "active_view" : "document",
                view = request.EffectiveScope == BimQueryScope.ActiveView
                    ? RevitIdentitySerializer.View(activeView!)
                    : null,
                query = new
                {
                    category = request.Category,
                    limit = request.EffectiveLimit,
                    returned = results.Count,
                    truncated,
                    missingParameterCounts = missingCounts
                },
                elements = results
            });
        }

        private static bool MatchesAllFilters(
            Element element,
            IReadOnlyList<BimQueryFilter> filters,
            Dictionary<string, int> missingCounts)
        {
            foreach (var filter in filters)
            {
                var lookup = FindParameter(element, filter.Parameter);
                if (lookup == null)
                {
                    missingCounts.TryGetValue(filter.Parameter, out var count);
                    missingCounts[filter.Parameter] = count + 1;
                    if (!BimFilterSemantics.MissingParameterMatches(filter.Operation))
                        return false;
                    continue;
                }

                var display = DisplayValue(lookup);
                var isEmpty = string.IsNullOrWhiteSpace(display);
                var expected = filter.Value ?? string.Empty;

                var matches = filter.Operation switch
                {
                    BimFilterOperation.IsEmpty => isEmpty,
                    BimFilterOperation.IsNotEmpty => !isEmpty,
                    BimFilterOperation.Equals => string.Equals(display, expected, StringComparison.OrdinalIgnoreCase),
                    BimFilterOperation.NotEquals => !string.Equals(display, expected, StringComparison.OrdinalIgnoreCase),
                    BimFilterOperation.Contains => display?.IndexOf(expected, StringComparison.OrdinalIgnoreCase) >= 0,
                    _ => false
                };

                if (!matches)
                    return false;
            }

            return true;
        }

        private static BimApiResponse? PreflightFilterParameterAmbiguity(
            IReadOnlyCollection<Element> candidates,
            IReadOnlyList<BimQueryFilter> filters)
        {
            foreach (var filter in filters)
            {
                var identities = new Dictionary<ParameterIdentityKey, object>();
                foreach (var element in candidates)
                {
                    foreach (Parameter parameter in element.Parameters)
                    {
                        if (!string.Equals(parameter.Definition?.Name, filter.Parameter, StringComparison.OrdinalIgnoreCase))
                            continue;

                        var identity = ParameterIdentity(parameter);
                        identities.TryAdd(identity.Key, identity.Candidate);
                    }
                }

                if (identities.Count > 1)
                {
                    var response = BimApiResponse.Fail(
                        BimErrorCode.AmbiguousParameter,
                        $"Parameter '{filter.Parameter}' is ambiguous in the target candidate set.",
                        400);
                    response.Data = new
                    {
                        error = "ambiguous_parameter",
                        parameter = filter.Parameter,
                        candidates = identities.Values.ToList()
                    };
                    return response;
                }
            }

            return null;
        }

        private static Parameter? FindParameter(Element element, string name)
        {
            foreach (Parameter parameter in element.Parameters)
            {
                if (!string.Equals(parameter.Definition?.Name, name, StringComparison.OrdinalIgnoreCase))
                    continue;

                return parameter;
            }

            return null;
        }

        private static string? DisplayValue(Parameter parameter)
        {
            return parameter.AsValueString() ?? parameter.AsString();
        }

        private static BuiltInCategory? ResolveBuiltInCategory(string category)
        {
            var normalized = category.Replace(" ", string.Empty).Replace("_", string.Empty);
            foreach (BuiltInCategory value in Enum.GetValues(typeof(BuiltInCategory)))
            {
                var name = value.ToString();
                if (string.Equals(name, category, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(name.Replace("OST_", string.Empty), category, StringComparison.OrdinalIgnoreCase) ||
                    string.Equals(name.Replace("OST_", string.Empty), normalized, StringComparison.OrdinalIgnoreCase))
                {
                    return value;
                }
            }
            return null;
        }

        private static object? BuildTypeSummary(Document document, Element element)
        {
            var typeId = element.GetTypeId();
            var type = typeId == ElementId.InvalidElementId ? null : document.GetElement(typeId);
            return type == null
                ? null
                : new
                {
                    id = type.Id.IntegerValue,
                    uniqueId = type.UniqueId,
                    familyName = type.get_Parameter(BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)?.AsString(),
                    name = type.Name
                };
        }

        private static string? TryBuiltInName(Parameter parameter)
        {
            var builtIn = (parameter.Definition as InternalDefinition)?.BuiltInParameter;
            return builtIn.HasValue ? builtIn.Value.ToString() : null;
        }

        private static string? TryGuid(Parameter parameter)
        {
            return parameter.GUID == System.Guid.Empty ? null : parameter.GUID.ToString("D");
        }

        private static ParameterIdentity ParameterIdentity(Parameter parameter)
        {
            var candidate = new
            {
                name = parameter.Definition?.Name,
                builtIn = TryBuiltInName(parameter),
                guid = TryGuid(parameter)
            };
            return new ParameterIdentity(
                new ParameterIdentityKey(candidate.name, candidate.builtIn, candidate.guid),
                candidate);
        }

        private readonly record struct ParameterIdentityKey(string? Name, string? BuiltIn, string? Guid);

        private readonly record struct ParameterIdentity(ParameterIdentityKey Key, object Candidate);
    }
}
```

Ambiguous parameter detection is committed behavior for Phase 1: before filter evaluation, preflight the requested parameter display names across the full target candidate set. If more than one distinct parameter identity is found for a requested display name, return `ambiguous_parameter` with candidate `name`, `builtIn`, and `guid` fields where available. It must not surface as an untyped exception, per-element partial failure, or a silent zero-result query.

- [ ] **Step 3: Wire query service into runtime**

Modify `src/RookBim/Revit/RevitRookBimRuntime.cs`:

```csharp
private readonly RevitQueryService _query = new();
```

Replace `QueryElements`:

```csharp
public BimApiResponse QueryElements(BimQueryElementsRequest request)
{
    return InvokeRead(app =>
    {
        var doc = RevitContext.ActiveDocument(app);
        if (doc == null)
            return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);

        return _query.Query(doc, app.ActiveUIDocument?.ActiveView, request);
    });
}
```

- [ ] **Step 4: Build and live validate active-view and document queries**

Run:

```powershell
dotnet build src/RookBim/RookBim.csproj -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
```

Expected:

```text
Build succeeded.
```

Live validation inside RhinoInside/Revit:

```powershell
$env:PYTHONPATH = "mcp_server/src"
@'
import asyncio, json
from rook.bridge import call_rhino

async def main():
    active = await call_rhino("/bim/query-elements", "POST", {
        "scope": "active_view",
        "category": "Walls",
        "limit": 10,
    })
    document = await call_rhino("/bim/query-elements", "POST", {
        "scope": "document",
        "category": "Doors",
        "limit": 10,
        "filters": [{"parameter": "Mark", "operation": "is_not_empty"}],
    })
    print(json.dumps(active, indent=2))
    print(json.dumps(document, indent=2))

asyncio.run(main())
'@ | python -
```

Expected:

```text
success true
data.elements[*].identity.elementId populated
data.query.truncated is boolean
document scope without category returns unbounded_document_query
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/RookBim/Revit/RevitQueryService.cs src/RookBim/Revit/RevitRookBimRuntime.cs
git commit -m "feat: query live revit elements"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: query live revit elements
```

---

## Task 9: Element Info and Parameters

**Files:**
- Create: `src/RookBim/Revit/RevitParameterSerializer.cs`
- Modify: `src/RookBim/Revit/RevitIdentitySerializer.cs`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`

- [ ] **Step 1: Verify parameter APIs in SDK**

Run:

```powershell
rg -n "StorageType|AsValueString|AsString|AsDouble|AsInteger|AsElementId|Definition.Name|SpecTypeId|UnitTypeId" "C:/Revit 2024.2 SDK/Samples"
```

Expected evidence to capture in implementation notes:

```text
StorageType.String
StorageType.Double
StorageType.Integer
StorageType.ElementId
Parameter.AsValueString()
Parameter.AsString()
```

- [ ] **Step 2: Add element resolver**

Add to `src/RookBim/Revit/RevitIdentitySerializer.cs`:

```csharp
public static Element? Resolve(Document document, BimElementIdentity identity)
{
    if (!string.IsNullOrWhiteSpace(identity.UniqueId))
    {
        var byUniqueId = document.GetElement(identity.UniqueId);
        if (byUniqueId != null)
            return byUniqueId;
    }

    if (identity.ElementId.HasValue)
    {
        return document.GetElement(new ElementId(identity.ElementId.Value));
    }

    return null;
}
```

- [ ] **Step 3: Implement parameter serializer**

Create `src/RookBim/Revit/RevitParameterSerializer.cs`:

```csharp
using System.Collections.Generic;
using Autodesk.Revit.DB;

namespace RookBim.Revit
{
    internal static class RevitParameterSerializer
    {
        public static IReadOnlyList<object> Serialize(Element element)
        {
            var result = new List<object>();
            foreach (Parameter parameter in element.Parameters)
            {
                var definition = parameter.Definition;
                result.Add(new
                {
                    name = definition?.Name ?? string.Empty,
                    storageType = parameter.StorageType.ToString(),
                    displayValue = DisplayValue(parameter),
                    rawValue = RawValue(parameter),
                    isReadOnly = parameter.IsReadOnly,
                    builtIn = TryBuiltInName(parameter),
                    guid = TryGuid(parameter),
                    canCompareNumeric = false
                });
            }
            return result;
        }

        private static string? DisplayValue(Parameter parameter)
        {
            return parameter.AsValueString() ?? parameter.AsString();
        }

        private static object? RawValue(Parameter parameter)
        {
            return parameter.StorageType switch
            {
                StorageType.String => parameter.AsString(),
                StorageType.Integer => parameter.AsInteger(),
                StorageType.Double => parameter.AsDouble(),
                StorageType.ElementId => parameter.AsElementId()?.IntegerValue,
                _ => null
            };
        }

        private static string? TryBuiltInName(Parameter parameter)
        {
            var builtIn = (parameter.Definition as InternalDefinition)?.BuiltInParameter;
            return builtIn.HasValue ? builtIn.Value.ToString() : null;
        }

        private static string? TryGuid(Parameter parameter)
        {
            return parameter.GUID == System.Guid.Empty ? null : parameter.GUID.ToString("D");
        }
    }
}
```

Use `parameter.Definition as InternalDefinition` for built-in parameter identity. Base `Definition` does not expose `BuiltInParameter` in Revit 2024.

- [ ] **Step 4: Wire info and parameters**

Modify `src/RookBim/Revit/RevitRookBimRuntime.cs`:

```csharp
public BimApiResponse ElementInfo(BimElementRequest request)
{
    return InvokeRead(app =>
    {
        var doc = RevitContext.ActiveDocument(app);
        if (doc == null)
            return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);

        var element = RevitIdentitySerializer.Resolve(doc, request.Identity);
        if (element == null)
            return BimApiResponse.Fail(BimErrorCode.ElementNotFound, "Element identity did not resolve in the active Revit document.", 404);

        return BimApiResponse.Ok(new
        {
            identity = RevitIdentitySerializer.Element(doc, element),
            name = element.Name,
            category = new
            {
                id = element.Category?.Id.IntegerValue,
                name = element.Category?.Name
            },
            type = BuildElementTypeSummary(doc, element),
            className = element.GetType().Name,
            location = element.Location?.GetType().Name
        });
    });
}

public BimApiResponse ElementParameters(BimElementRequest request)
{
    return InvokeRead(app =>
    {
        var doc = RevitContext.ActiveDocument(app);
        if (doc == null)
            return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);

        var element = RevitIdentitySerializer.Resolve(doc, request.Identity);
        if (element == null)
            return BimApiResponse.Fail(BimErrorCode.ElementNotFound, "Element identity did not resolve in the active Revit document.", 404);

        return BimApiResponse.Ok(new
        {
            identity = RevitIdentitySerializer.Element(doc, element),
            parameters = RevitParameterSerializer.Serialize(element)
        });
    });
}

private static object? BuildElementTypeSummary(Autodesk.Revit.DB.Document document, Autodesk.Revit.DB.Element element)
{
    var typeId = element.GetTypeId();
    var type = typeId == Autodesk.Revit.DB.ElementId.InvalidElementId ? null : document.GetElement(typeId);
    return type == null
        ? null
        : new
        {
            id = type.Id.IntegerValue,
            uniqueId = type.UniqueId,
            familyName = type.get_Parameter(Autodesk.Revit.DB.BuiltInParameter.SYMBOL_FAMILY_NAME_PARAM)?.AsString(),
            name = type.Name
        };
}
```

- [ ] **Step 5: Build and live validate identity round trip**

Run:

```powershell
dotnet build src/RookBim/RookBim.csproj -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
```

Expected:

```text
Build succeeded.
```

Live validation inside RhinoInside/Revit:

```powershell
$env:PYTHONPATH = "mcp_server/src"
@'
import asyncio, json
from rook.bridge import call_rhino

async def main():
    result = await call_rhino("/bim/query-elements", "POST", {
        "scope": "active_view",
        "category": "Walls",
        "limit": 1,
    })
    identity = result["data"]["elements"][0]["identity"]
    info = await call_rhino("/bim/element-info", "POST", {"identity": identity})
    parameters = await call_rhino("/bim/element-parameters", "POST", {"identity": identity})
    print(json.dumps(info, indent=2))
    print(json.dumps(parameters, indent=2))

asyncio.run(main())
'@ | python -
```

Expected:

```text
element-info returns same elementId and uniqueId
element-parameters returns parameter names, storageType, displayValue, rawValue
no transaction is opened
```

- [ ] **Step 6: Commit**

Run:

```powershell
git add src/RookBim/Revit/RevitIdentitySerializer.cs src/RookBim/Revit/RevitParameterSerializer.cs src/RookBim/Revit/RevitRookBimRuntime.cs
git commit -m "feat: inspect rookbim element evidence"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: inspect rookbim element evidence
```

---

## Task 10: Revit UI Selection Tools

**Files:**
- Create: `src/RookBim/Revit/RevitSelectionService.cs`
- Modify: `src/RookBim/Revit/RevitRookBimRuntime.cs`

- [ ] **Step 1: Verify selection APIs in SDK**

Run:

```powershell
rg -n "Selection|SetElementIds|GetElementIds|UIDocument" "C:/Revit 2024.2 SDK/Samples"
```

Expected evidence to capture in implementation notes:

```text
UIDocument.Selection.SetElementIds(ICollection<ElementId>)
UIDocument.Selection.GetElementIds()
```

- [ ] **Step 2: Implement selection service**

Create `src/RookBim/Revit/RevitSelectionService.cs`:

```csharp
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using Rook.Bim;

namespace RookBim.Revit
{
    internal sealed class RevitSelectionService
    {
        public BimApiResponse Select(UIDocument uiDocument, BimSelectElementsRequest request)
        {
            var ids = new List<ElementId>();
            foreach (var identity in request.Identities)
            {
                var element = RevitIdentitySerializer.Resolve(uiDocument.Document, identity);
                if (element == null)
                    return BimApiResponse.Fail(BimErrorCode.ElementNotFound, "One or more element identities did not resolve in the active Revit document.", 404);
                ids.Add(element.Id);
            }

            uiDocument.Selection.SetElementIds(ids);
            return BimApiResponse.Ok(new
            {
                selectedCount = ids.Count,
                document = RevitIdentitySerializer.Document(uiDocument.Document)
            });
        }

        public BimApiResponse Clear(UIDocument uiDocument)
        {
            uiDocument.Selection.SetElementIds(new List<ElementId>());
            return BimApiResponse.Ok(new
            {
                selectedCount = 0,
                document = RevitIdentitySerializer.Document(uiDocument.Document)
            });
        }
    }
}
```

- [ ] **Step 3: Wire runtime selection**

Modify `src/RookBim/Revit/RevitRookBimRuntime.cs`:

```csharp
private readonly RevitSelectionService _selection = new();
```

Replace selection methods:

```csharp
public BimApiResponse SelectElements(BimSelectElementsRequest request)
{
    return InvokeRead(app =>
    {
        var uiDoc = RevitContext.ActiveUiDocument(app);
        if (uiDoc == null)
            return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);

        return _selection.Select(uiDoc, request);
    });
}

public BimApiResponse ClearSelection()
{
    return InvokeRead(app =>
    {
        var uiDoc = RevitContext.ActiveUiDocument(app);
        if (uiDoc == null)
            return BimApiResponse.Fail(BimErrorCode.NoActiveDocument, "No active Revit document is open.", 409);

        return _selection.Clear(uiDoc);
    });
}
```

- [ ] **Step 4: Build and live validate UI selection**

Run:

```powershell
dotnet build src/RookBim/RookBim.csproj -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
```

Expected:

```text
Build succeeded.
```

Live validation inside RhinoInside/Revit:

```powershell
$env:PYTHONPATH = "mcp_server/src"
@'
import asyncio, json
from rook.bridge import call_rhino

async def main():
    result = await call_rhino("/bim/query-elements", "POST", {
        "scope": "active_view",
        "category": "Walls",
        "limit": 3,
    })
    identities = [row["identity"] for row in result["data"]["elements"]]
    selected = await call_rhino("/bim/select-elements", "POST", {"identities": identities})
    cleared = await call_rhino("/bim/clear-selection", "POST", {})
    print(json.dumps(selected, indent=2))
    print(json.dumps(cleared, indent=2))

asyncio.run(main())
'@ | python -
```

Expected:

```text
select-elements selects exact Revit elements in the UI
clear-selection clears Revit UI selection
no Revit write transaction is opened
no graphic override or temporary isolate is used
```

- [ ] **Step 5: Commit**

Run:

```powershell
git add src/RookBim/Revit/RevitSelectionService.cs src/RookBim/Revit/RevitRookBimRuntime.cs
git commit -m "feat: select rookbim evidence in revit"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] feat: select rookbim evidence in revit
```

---

## Task 11: Final Verification and Documentation Notes

**Files:**
- Modify: `docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md` only if implementation validation discovers a needed clarification.
- No code file changes unless verification exposes a bug.

- [ ] **Step 1: Run source guards**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/rookbim-boundary-guards.tests.ps1
```

Expected:

```text
rookbim boundary guards passed
```

- [ ] **Step 2: Run managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "FullyQualifiedName~Rook.Tests.Bim|FullyQualifiedName~BimHandlerTests|FullyQualifiedName~NativeBimDispatchSourceTests"
dotnet test src/RookBim.Tests/RookBim.Tests.csproj
```

Expected:

```text
Passed!
Passed!
```

- [ ] **Step 3: Run MCP tests**

Run:

```powershell
pytest mcp_server/tests/test_rookbim_mcp_tools.py -q
pytest mcp_server/tests/test_dispatcher_safety.py -q
```

Expected:

```text
passed
passed
```

- [ ] **Step 4: Build managed and optional BIM module**

Run:

```powershell
dotnet build src/Rook/Rook.csproj -f net48
dotnet build src/RookBim/RookBim.csproj -p:RevitInstallDir="C:\Program Files\Autodesk\Revit 2024"
```

Expected:

```text
Build succeeded.
Build succeeded.
```

- [ ] **Step 5: Build native when toolchain is available**

Run:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected on a correctly configured Windows/Rhino/MFC machine:

```text
Build succeeded.
```

If this fails due to toolchain availability, record the exact failure and do not report native build as verified.

- [ ] **Step 6: Live standalone Rhino validation**

Run against standalone Rhino with RookNative loaded:

```powershell
$env:PYTHONPATH = "mcp_server/src"
@'
import asyncio, json
from rook.bridge import call_rhino, discovery_diagnostics

async def main():
    print(json.dumps(discovery_diagnostics(), indent=2))
    print(json.dumps(await call_rhino("/bim/status", "GET"), indent=2))
    print(json.dumps(await call_rhino("/bim/query-elements", "POST", {
        "scope": "active_view",
        "category": "Walls",
        "limit": 1,
    }), indent=2))

asyncio.run(main())
'@ | python -
```

Expected:

```text
status returns success true with available false and errorCode rookbim_unavailable or not_rhino_inside
query-elements fails with rookbim_unavailable or not_rhino_inside
no native/managed callback failure leaks to the user
```

- [ ] **Step 7: Live RhinoInside/Revit validation**

Run inside RhinoInside/Revit with an open model:

```powershell
$env:PYTHONPATH = "mcp_server/src"
@'
import asyncio, json
from rook.bridge import call_rhino, discovery_diagnostics

async def main():
    print(json.dumps(discovery_diagnostics(), indent=2))
    print(json.dumps(await call_rhino("/bim/status", "GET"), indent=2))
    print(json.dumps(await call_rhino("/bim/active-document", "GET"), indent=2))
    result = await call_rhino("/bim/query-elements", "POST", {
        "scope": "active_view",
        "category": "Walls",
        "limit": 5,
    })
    print(json.dumps(result, indent=2))
    identity = result["data"]["elements"][0]["identity"]
    print(json.dumps(await call_rhino("/bim/element-info", "POST", {"identity": identity}), indent=2))
    print(json.dumps(await call_rhino("/bim/element-parameters", "POST", {"identity": identity}), indent=2))
    print(json.dumps(await call_rhino("/bim/select-elements", "POST", {"identities": [identity]}), indent=2))
    print(json.dumps(await call_rhino("/bim/clear-selection", "POST", {}), indent=2))

asyncio.run(main())
'@ | python -
```

Expected:

```text
status available true
active-document returns document title/path/guid/guidSource/isFamilyDocument/isWorkshared and active view id/name/optional uniqueId
query returns exact element identities with confidence exact and resolved true
document query without category returns unbounded_document_query
parameters return storageType, displayValue, rawValue where safe, canCompareNumeric false
selection mutates UI selection only
no Grasshopper document or canvas is required
no Revit write transaction is opened
```

- [ ] **Step 8: Final diff review**

Run:

```powershell
git status --short
git diff --stat HEAD
git diff -- src/Rook src/RookNative mcp_server/src/rook src/RookBim src/RookBim.Tests scripts/tests docs/superpowers
```

Expected:

```text
Only RookBIM Phase 1 files changed.
No .vcxproj or .vcxproj.filters changes.
No Autodesk.Revit references in src/Rook.
```

- [ ] **Step 9: Commit verification notes if docs changed**

If implementation validation required a spec clarification, run:

```powershell
git add docs/superpowers/specs/2026-05-27-rookbim-phase-1-design.md
git commit -m "docs: record rookbim validation notes"
```

Expected:

```text
[codex/rookbim-phase1 abc1234] docs: record rookbim validation notes
```

If no docs changed, skip this commit.

---

## Implementation Constraints to Preserve

- `RookNative` remains the only public HTTP surface.
- Public BIM routes are `/bim/*`; there is no public `RookBim` HTTP listener.
- `src/Rook` must not reference `Autodesk.Revit`, `RevitAPI.dll`, `RevitAPIUI.dll`, or Revit namespaces.
- `src/RookBim` is the only production module that references Revit APIs.
- No Revit write transactions are opened in Phase 1.
- `rookbim_select_elements` and `rookbim_clear_selection` mutate UI selection only; they do not mutate the Revit document.
- No Grasshopper document, Grasshopper canvas, or GH component is required for any Phase 1 operation.
- Temporary view isolation/highlighting is excluded from Phase 1 unless plain Revit selection fails live validation and the spec is explicitly amended.
- Numeric comparisons are excluded from Phase 1 filter language.
- Linked model support is not flattened into loose IDs; unresolved linked identities return structured `linked_element_unsupported` or `capability_unavailable`.

## Self-Review

- Spec coverage: The plan covers route/tool set, native/managed/module ownership, `scope` defaults and document category bound, string/presence-only filters, nullable/source-labeled document GUIDs, identity envelopes, unavailable/error semantics, live validation, source guard, and no-GH/no-transaction boundaries.
- Placeholder scan: The plan contains exact paths, commands, expected outputs, route names, enum values, and code shapes. No task asks for generic error handling or unspecified tests.
- Type consistency: Wire names use `rookbim_*` for MCP tools, `/bim/*` for HTTP routes, `snake_case` op values on the wire, PascalCase C# DTO names, and the same identity field names across MCP schemas and C# JSON serialization.
