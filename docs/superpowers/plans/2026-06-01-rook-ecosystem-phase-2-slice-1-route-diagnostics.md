# Rook Ecosystem Phase 2 Slice 1 Route Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the Phase 2 additive route diagnostic contract, catalog/source guards, and one minimal non-mutating example adoption without changing route ownership, loading policy, installer structure, or broad route behavior.

**Architecture:** Add a small header-only native diagnostic helper so no `.vcxproj` or `.vcxproj.filters` edits are needed. Preserve existing error envelopes by adding a top-level `diagnostic` sibling only on the selected example path. Use source/contract tests to pin the fixed `failureKind` enum, structured diagnostic route, catalog metadata, and anti-drift rules.

**Tech Stack:** C++17/MFC native plugin, `httplib`, `nlohmann::json`, xUnit source tests in `src/Rook.Tests`, PowerShell test commands.

---

## Scope

This plan implements only Phase 2 Slice 1 from `docs/superpowers/specs/2026-06-01-rook-ecosystem-phase-2-diagnostics-design.md`.

Allowed:

- Add the additive native diagnostic response helper.
- Add fixed v1 `failureKind` validation through source tests.
- Add the first reviewed reason-code catalog entry.
- Adopt one minimal existing route failure path.

Not allowed:

- No Phase 2 Slice 2 companion-backed route sweep.
- No RookBIM, GH, or MCP behavior work.
- No route ownership changes.
- No companion loading changes.
- No installer/module manifest work.
- No public managed HTTP surface.
- No `.vcxproj` or `.vcxproj.filters` edits.
- No generic `/capabilities` preflight.

## File Structure

- Create `src/RookNative/Infrastructure/RouteDiagnostics.h`
  - Header-only helper for building route diagnostic JSON.
  - Defines the fixed v1 `FailureKind` enum and `RouteDiagnostic` struct.
  - Defines catalog-backed builders for Slice 1 reason codes.

- Modify `src/RookNative/RookServer.h`
  - Add `SendErrorWithDiagnostic(...)` overloads next to existing response helpers.

- Modify `src/RookNative/RookServer.cpp`
  - Implement `SendErrorWithDiagnostic(...)`.
  - Preserve `success:false` and legacy `data`.
  - Add only a top-level `diagnostic` sibling.

- Modify `src/RookNative/Handlers/VisionHandler.cpp`
  - Include `Infrastructure/RouteDiagnostics.h`.
  - Let `ForwardVisionDispatch(...)` optionally receive diagnostic route context.
  - Adopt only `GET /vision/video/models` unavailable path as the Slice 1 example.

- Create `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`
  - Source guards for helper shape, fixed enum, catalog metadata, schema version independence, anti-drift, and no project-file edits.

- Modify `src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs`
  - Source guards proving the example adoption is narrow and non-mutating.

## Reason-Code Catalog Delta

Add exactly one Slice 1 reason code:

```text
reasonCode: vision_dispatch_callback_unavailable
failureKind: domain_unavailable
domainId: vision.media
ownedBy: native
evidenceSource: native_callback_registration
emittedBy: native_route
retryableDefault: true
userActionRequiredDefault: false
recommendedNextStep: Wait for companion startup, then retry. If it remains unavailable, inspect /capabilities.
diagnosticRoute: GET /capabilities domain vision.media
```

The example adoption route is:

```text
GET /vision/video/models
operation: list_video_models
```

This is the smallest stable existing failure path because it is a list-style GET route, has no request body, and does not mutate the Rhino document.

---

### Task 1: Add Failing Source Tests For The Diagnostic Contract

**Files:**
- Create: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`

- [ ] **Step 1: Create the source test file**

Add this file:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Diagnostics
{
    public class RouteDiagnosticsSourceTests
    {
        [Fact]
        public void RouteDiagnosticsHelper_DefinesFixedFailureKindEnumAndDiagnosticShape()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");

            Assert.Contains("enum class FailureKind", header);
            Assert.Contains("DomainUnavailable", header);
            Assert.Contains("HostBlocked", header);
            Assert.Contains("DependencyUnavailable", header);
            Assert.Contains("DependencyDegraded", header);
            Assert.Contains("OperationUnavailable", header);
            Assert.Contains("ConfigurationRequired", header);
            Assert.Contains("AuthorizationRequired", header);
            Assert.Contains("Unknown", header);

            Assert.Contains("\"schemaVersion\"", header);
            Assert.Contains("\"domainId\"", header);
            Assert.Contains("\"route\"", header);
            Assert.Contains("\"operation\"", header);
            Assert.Contains("\"reasonCode\"", header);
            Assert.Contains("\"failureKind\"", header);
            Assert.Contains("\"retryable\"", header);
            Assert.Contains("\"userActionRequired\"", header);
            Assert.Contains("\"diagnosticRoute\"", header);
            Assert.Contains("\"recommendedNextStep\"", header);
            Assert.Contains("\"method\"", header);
            Assert.Contains("\"path\"", header);
            Assert.Contains("\"domainId\"", header);
        }

        [Fact]
        public void RouteDiagnosticsHelper_TracksCatalogMetadataForSliceOneReasonCode()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");

            Assert.Contains("BuildVisionDispatchCallbackUnavailable", header);
            Assert.Contains("\"vision_dispatch_callback_unavailable\"", header);
            Assert.Contains("\"vision.media\"", header);
            Assert.Contains("\"ownedBy\"", header);
            Assert.Contains("\"native\"", header);
            Assert.Contains("\"evidenceSource\"", header);
            Assert.Contains("\"native_callback_registration\"", header);
            Assert.Contains("\"emittedBy\"", header);
            Assert.Contains("\"native_route\"", header);
            Assert.Contains("\"/capabilities\"", header);
        }

        [Fact]
        public void RouteDiagnosticsHelper_KeepsSchemaVersionIndependentFromCapabilitiesSchema()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
            var serverSource = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("kRouteDiagnosticSchemaVersion = 1", header);
            Assert.Contains("BuildRookCapabilitiesDocument", serverSource);
            Assert.DoesNotContain("kRouteDiagnosticSchemaVersion", serverSource.Substring(
                serverSource.IndexOf("BuildRookCapabilitiesDocument", StringComparison.Ordinal)));
        }

        [Fact]
        public void RookServer_AddsDiagnosticAsTopLevelSiblingWithoutReplacingLegacyData()
        {
            var header = ReadSourceFile("src", "RookNative", "RookServer.h");
            var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
            var helper = ExtractFunction(source, "CRookServer::SendErrorWithDiagnostic");

            Assert.Contains("SendErrorWithDiagnostic", header);
            Assert.Contains("envelope[\"success\"] = false;", helper);
            Assert.Contains("envelope[\"data\"] = message;", helper);
            Assert.Contains("envelope[\"diagnostic\"] = diagnostic;", helper);
            Assert.DoesNotContain("envelope[\"data\"] = diagnostic;", helper);
            Assert.DoesNotContain("legacyMessage", helper);
        }

        [Fact]
        public void RouteDiagnostics_DoNotIntroduceProjectFileOrBroadArchitectureChanges()
        {
            var project = ReadSourceFile("src", "RookNative", "RookNative.vcxproj");
            var filters = ReadSourceFile("src", "RookNative", "RookNative.vcxproj.filters");
            var nativePlugin = ReadSourceFile("src", "RookNative", "RookNativePlugin.cpp");
            var serverSource = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.DoesNotContain("RouteDiagnostics.cpp", project);
            Assert.DoesNotContain("RouteDiagnostics.cpp", filters);
            Assert.DoesNotContain("installed-modules.json", serverSource);
            Assert.Contains("StartCompanionLoadDeferred();", nativePlugin);
            Assert.DoesNotContain("DispatchPolicy::CommandControl", ExtractFunction(nativePlugin, "StartCompanionLoadDeferred"));
        }

        [Fact]
        public void RouteDiagnosticReasonCodes_DoNotUseBroadFallbackCodesAsCatalogEntries()
        {
            var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");

            Assert.DoesNotContain("\"bridge_unavailable\"", header);
            Assert.DoesNotContain("\"plugin_not_ready\"", header);
            Assert.DoesNotContain("\"service_failed\"", header);
            Assert.DoesNotContain("\"not_available\"", header);
            Assert.DoesNotContain("\"managed_dependency_unavailable\"", header);
        }

        [Fact]
        public void NativeSources_DoNotUseCapabilitiesAsGenericRoutePreflight()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var helper = ExtractFunction(source, "ForwardVisionDispatch");

            Assert.DoesNotContain("BuildRookCapabilitiesDocument", helper);
            Assert.DoesNotContain("HandleCapabilities", helper);
            Assert.DoesNotContain("/capabilities", helper);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName + "(", StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);

            while (signatureStart > 0 && source[signatureStart - 1] != '\n')
                signatureStart--;

            var bodyStart = source.IndexOf('{', signatureStart);
            if (bodyStart < 0)
                throw new InvalidOperationException("Function body not found: " + functionName);

            var depth = 0;
            for (var i = bodyStart; i < source.Length; i++)
            {
                if (source[i] == '{') depth++;
                else if (source[i] == '}')
                {
                    depth--;
                    if (depth == 0)
                        return source.Substring(signatureStart, i - signatureStart + 1);
                }
            }

            throw new InvalidOperationException("Function body did not close: " + functionName);
        }

        private static string ReadSourceFile(params string[] pathParts)
        {
            var dir = new DirectoryInfo(AppContext.BaseDirectory);
            while (dir != null)
            {
                var candidate = Path.Combine(dir.FullName, Path.Combine(pathParts));
                if (File.Exists(candidate))
                    return File.ReadAllText(candidate);
                dir = dir.Parent;
            }

            throw new FileNotFoundException(
                "Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected:

```text
Failed!  - Failed: 7
```

The failures should be missing `RouteDiagnostics.h` and missing `SendErrorWithDiagnostic`.

- [ ] **Step 3: Commit the failing tests**

Run:

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
git commit -m "test: pin phase 2 route diagnostic contract"
```

---

### Task 2: Add The Header-Only Native Diagnostic Helper

**Files:**
- Create: `src/RookNative/Infrastructure/RouteDiagnostics.h`

- [ ] **Step 1: Add the helper header**

Create `src/RookNative/Infrastructure/RouteDiagnostics.h`:

```cpp
// RouteDiagnostics.h
//
// Phase 2 additive route diagnostics. Header-only by design so Slice 1
// does not require .vcxproj or .vcxproj.filters edits.

#pragma once

#include <string>

namespace Rook {
namespace Diagnostics {

constexpr int kRouteDiagnosticSchemaVersion = 1;

enum class FailureKind
{
    DomainUnavailable,
    HostBlocked,
    DependencyUnavailable,
    DependencyDegraded,
    OperationUnavailable,
    ConfigurationRequired,
    AuthorizationRequired,
    Unknown,
};

inline const char* FailureKindToString(FailureKind kind)
{
    switch (kind)
    {
    case FailureKind::DomainUnavailable:
        return "domain_unavailable";
    case FailureKind::HostBlocked:
        return "host_blocked";
    case FailureKind::DependencyUnavailable:
        return "dependency_unavailable";
    case FailureKind::DependencyDegraded:
        return "dependency_degraded";
    case FailureKind::OperationUnavailable:
        return "operation_unavailable";
    case FailureKind::ConfigurationRequired:
        return "configuration_required";
    case FailureKind::AuthorizationRequired:
        return "authorization_required";
    case FailureKind::Unknown:
    default:
        return "unknown";
    }
}

struct RouteDiagnostic
{
    std::string domainId;
    std::string route;
    std::string operation;
    std::string reasonCode;
    FailureKind failureKind = FailureKind::Unknown;
    bool retryable = false;
    bool userActionRequired = false;
    std::string recommendedNextStep;
    std::string ownedBy;
    std::string evidenceSource;
    std::string emittedBy;
    std::string state;
};

inline nlohmann::json ToJson(const RouteDiagnostic& diagnostic)
{
    nlohmann::json result;
    result["schemaVersion"] = kRouteDiagnosticSchemaVersion;
    result["domainId"] = diagnostic.domainId;
    result["route"] = diagnostic.route;
    result["operation"] = diagnostic.operation;
    result["reasonCode"] = diagnostic.reasonCode;
    result["failureKind"] = FailureKindToString(diagnostic.failureKind);
    result["retryable"] = diagnostic.retryable;
    result["userActionRequired"] = diagnostic.userActionRequired;

    nlohmann::json diagnosticRoute;
    diagnosticRoute["method"] = "GET";
    diagnosticRoute["path"] = "/capabilities";
    diagnosticRoute["domainId"] = diagnostic.domainId;
    result["diagnosticRoute"] = diagnosticRoute;

    if (!diagnostic.recommendedNextStep.empty())
        result["recommendedNextStep"] = diagnostic.recommendedNextStep;

    result["ownedBy"] = diagnostic.ownedBy;
    result["evidenceSource"] = diagnostic.evidenceSource;
    result["emittedBy"] = diagnostic.emittedBy;

    if (!diagnostic.state.empty())
        result["state"] = diagnostic.state;

    return result;
}

inline nlohmann::json BuildVisionDispatchCallbackUnavailable(
    const std::string& route,
    const std::string& operation)
{
    RouteDiagnostic diagnostic;
    diagnostic.domainId = "vision.media";
    diagnostic.route = route;
    diagnostic.operation = operation;
    diagnostic.reasonCode = "vision_dispatch_callback_unavailable";
    diagnostic.failureKind = FailureKind::DomainUnavailable;
    diagnostic.retryable = true;
    diagnostic.userActionRequired = false;
    diagnostic.recommendedNextStep =
        "Wait for companion startup, then retry. If it remains unavailable, inspect /capabilities.";
    diagnostic.ownedBy = "native";
    diagnostic.evidenceSource = "native_callback_registration";
    diagnostic.emittedBy = "native_route";
    diagnostic.state = "not_loaded";
    return ToJson(diagnostic);
}

} // namespace Diagnostics
} // namespace Rook
```

- [ ] **Step 2: Run the source tests and verify partial failure remains**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected:

```text
Failed!
```

The helper-related assertions should pass. The remaining failures should be about missing `SendErrorWithDiagnostic` and missing route adoption.

- [ ] **Step 3: Commit the helper**

Run:

```powershell
git add src/RookNative/Infrastructure/RouteDiagnostics.h
git commit -m "feat: add native route diagnostic helper"
```

---

### Task 3: Add The Additive Error Helper To CRookServer

**Files:**
- Modify: `src/RookNative/RookServer.h`
- Modify: `src/RookNative/RookServer.cpp`

- [ ] **Step 1: Add declarations to `RookServer.h`**

Add these declarations immediately after `SendErrorData(...)`:

```cpp
    // SendErrorWithDiagnostic: preserves legacy data while adding the
    // additive Phase 2 route diagnostic sibling. Callers may override
    // res.status after this helper to preserve established route status.
    static void SendErrorWithDiagnostic(
        httplib::Response& res,
        const std::string& message,
        const nlohmann::json& diagnostic);
    static void SendErrorWithDiagnostic(
        httplib::Response& res,
        const nlohmann::json& data,
        const nlohmann::json& diagnostic);
```

- [ ] **Step 2: Add implementations to `RookServer.cpp`**

Add these implementations immediately after `SendErrorData(...)`:

```cpp
void CRookServer::SendErrorWithDiagnostic(
    httplib::Response& res,
    const std::string& message,
    const nlohmann::json& diagnostic)
{
    nlohmann::json envelope;
    envelope["success"] = false;
    envelope["data"] = message;
    envelope["diagnostic"] = diagnostic;

    res.status = 400;
    res.set_content(envelope.dump(), "application/json");
}

void CRookServer::SendErrorWithDiagnostic(
    httplib::Response& res,
    const nlohmann::json& data,
    const nlohmann::json& diagnostic)
{
    nlohmann::json envelope;
    envelope["success"] = false;
    envelope["data"] = data;
    envelope["diagnostic"] = diagnostic;

    res.status = 400;
    res.set_content(envelope.dump(), "application/json");
}
```

- [ ] **Step 3: Run the route diagnostics tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected:

```text
Failed!
```

Only the route-adoption assertions should remain failing.

- [ ] **Step 4: Commit the server helper**

Run:

```powershell
git add src/RookNative/RookServer.h src/RookNative/RookServer.cpp
git commit -m "feat: add additive route diagnostic response helper"
```

---

### Task 4: Add Failing Source Tests For The Minimal Vision Example Adoption

**Files:**
- Modify: `src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs`

- [ ] **Step 1: Add tests to `NativeVisionDispatchSourceTests`**

Add these test methods before the existing private helpers:

```csharp
        [Fact]
        public void VisionVideoModelsRoute_IsSliceOneDiagnosticExample()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var handler = ExtractFunction(source, "HandleVisionVideoModelsList");

            Assert.Contains("BuildVisionDispatchCallbackUnavailable", source);
            Assert.Contains("\"GET /vision/video/models\"", handler);
            Assert.Contains("\"list_video_models\"", handler);
            Assert.Contains("ForwardVisionDispatch", handler);
            Assert.DoesNotContain("CMainThreadDispatcher::Instance().Dispatch", handler);
            Assert.DoesNotContain("CRhinoDoc::", handler);
            Assert.DoesNotContain("RunScript", handler);
        }

        [Fact]
        public void VisionDispatchDiagnostic_IsOnlyEmittedForOptedInUnavailablePath()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
            var helper = ExtractFunction(source, "ForwardVisionDispatch");
            var generateHandler = ExtractFunction(source, "HandleVisionGenerate");
            var modelsHandler = ExtractFunction(source, "HandleVisionVideoModelsList");

            Assert.Contains("const nlohmann::json* unavailableDiagnostic", helper);
            Assert.Contains("if (unavailableDiagnostic != nullptr)", helper);
            Assert.Contains("CRookServer::SendErrorWithDiagnostic", helper);
            Assert.Contains("CRookServer::SendError(", helper);
            Assert.DoesNotContain("BuildVisionDispatchCallbackUnavailable", generateHandler);
            Assert.Contains("BuildVisionDispatchCallbackUnavailable", modelsHandler);
        }
```

- [ ] **Step 2: Run the vision source tests and verify they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeVisionDispatchSourceTests
```

Expected:

```text
Failed!
```

The failures should be missing `BuildVisionDispatchCallbackUnavailable`, missing optional diagnostic parameter in `ForwardVisionDispatch`, and missing route context in `HandleVisionVideoModelsList`.

- [ ] **Step 3: Commit the failing example-adoption tests**

Run:

```powershell
git add src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs
git commit -m "test: pin slice 1 vision diagnostic adoption"
```

---

### Task 5: Adopt Diagnostics On The Minimal Vision Unavailable Path

**Files:**
- Modify: `src/RookNative/Handlers/VisionHandler.cpp`

- [ ] **Step 1: Include the diagnostic helper**

Add this include after `#include "Infrastructure/JsonHelpers.h"`:

```cpp
#include "Infrastructure/RouteDiagnostics.h"
```

- [ ] **Step 2: Update `ForwardVisionDispatch` signature**

Replace:

```cpp
void ForwardVisionDispatch(
    httplib::Response& res,
    const char* op,
    nlohmann::json& body)
```

with:

```cpp
void ForwardVisionDispatch(
    httplib::Response& res,
    const char* op,
    nlohmann::json& body,
    const nlohmann::json* unavailableDiagnostic = nullptr)
```

- [ ] **Step 3: Update only the unavailable branch**

Replace the `ManagedCreateInvokeResult::Unavailable` branch in `ForwardVisionDispatch` with:

```cpp
    case ManagedCreateInvokeResult::Unavailable:
    {
        const std::string message =
            "Vision routes require the Rook companion plugin. "
            "Ensure Rook.rhp is loaded in Rhino, then retry.";
        if (unavailableDiagnostic != nullptr)
        {
            CRookServer::SendErrorWithDiagnostic(res, message, *unavailableDiagnostic);
        }
        else
        {
            CRookServer::SendError(res, message);
        }
        res.status = 503;
        res.set_header("X-Rook-Vision-Op", op);
        return;
    }
```

- [ ] **Step 4: Adopt only `GET /vision/video/models`**

Replace `HandleVisionVideoModelsList` with:

```cpp
void HandleVisionVideoModelsList(const httplib::Request& /*req*/, httplib::Response& res)
{
    // No params, no body — forward an empty JSON object. Managed
    // VideoOpHandler.ListModels reads no fields beyond `op`.
    nlohmann::json body = nlohmann::json::object();
    const auto unavailableDiagnostic =
        Rook::Diagnostics::BuildVisionDispatchCallbackUnavailable(
            "GET /vision/video/models",
            "list_video_models");
    ForwardVisionDispatch(
        res,
        "list_video_models",
        body,
        &unavailableDiagnostic);
}
```

- [ ] **Step 5: Run the focused source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeVisionDispatchSourceTests"
```

Expected:

```text
Passed!
```

- [ ] **Step 6: Commit the example adoption**

Run:

```powershell
git add src/RookNative/Handlers/VisionHandler.cpp
git commit -m "feat: add slice 1 vision route diagnostic"
```

---

### Task 6: Add Final Phase-Boundary Guards

**Files:**
- Modify: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`

- [ ] **Step 1: Add a guard for no broad Slice 2 adoption**

Add this test before the private helpers:

```csharp
        [Fact]
        public void SliceOne_DoesNotAdoptDiagnosticsAcrossAllVisionRoutes()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");

            Assert.Single(FindAll(source, "BuildVisionDispatchCallbackUnavailable("));
            Assert.DoesNotContain("viewport_capture_callback_unavailable", source);
            Assert.DoesNotContain("block_mutation_callback_unavailable", source);
            Assert.DoesNotContain("bim_dispatch_callback_unavailable", source);
            Assert.DoesNotContain("gh_bridge_callback_unavailable", source);
        }
```

Also add this helper method before `ReadSourceFile`:

```csharp
        private static string[] FindAll(string source, string needle)
        {
            var matches = new System.Collections.Generic.List<string>();
            var index = 0;
            while (true)
            {
                index = source.IndexOf(needle, index, StringComparison.Ordinal);
                if (index < 0)
                    return matches.ToArray();
                matches.Add(needle);
                index += needle.Length;
            }
        }
```

- [ ] **Step 2: Run the focused tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeVisionDispatchSourceTests"
```

Expected:

```text
Passed!
```

- [ ] **Step 3: Commit the phase-boundary guard**

Run:

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
git commit -m "test: guard slice 1 diagnostic boundary"
```

---

### Task 7: Native Build And Regression Validation

**Files:**
- No file edits.

- [ ] **Step 1: Run focused managed/source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeVisionDispatchSourceTests|FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~MainThreadDispatcherSourceTests"
```

Expected:

```text
Passed!
```

- [ ] **Step 2: Run the native MSVC 14.44 Debug x64 build**

Run:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected:

```text
Build succeeded.
```

- [ ] **Step 3: Run whitespace check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected:

```text
<no output>
```

- [ ] **Step 4: Commit nothing if clean**

Run:

```powershell
git status --short
```

Expected:

```text
<no output>
```

If files are dirty, inspect them and either commit intentional changes or revert only files changed by this implementation.

---

## Manual Review Checklist

Before opening or updating a PR, verify:

- The only example route adoption is `GET /vision/video/models`.
- Existing `data` is still the legacy string for the adopted unavailable path.
- Existing 503 status is preserved for the adopted unavailable path.
- Existing `X-Rook-Vision-Op` header is preserved.
- No success path changed.
- No managed callback signature changed.
- No route registration changed.
- No `.vcxproj` or `.vcxproj.filters` changed.
- No generic `/capabilities` preflight was added.
- No MCP behavior/tool-disclosure changes were added.

## PR Checklist Text

Use this text in the PR body:

```text
Phase 2 Slice 1 only.

Catalog delta:
- reasonCode: vision_dispatch_callback_unavailable
- failureKind: domain_unavailable
- domainId: vision.media
- ownedBy: native
- evidenceSource: native_callback_registration
- emittedBy: native_route
- adopting route: GET /vision/video/models

Validation:
- focused managed/source tests passed
- native MSVC 14.44 Debug x64 build passed
- git diff --check origin/main...HEAD passed

Non-changes:
- no route ownership changes
- no companion loading changes
- no installer/module manifest work
- no public managed HTTP surface
- no MCP behavior/tool-disclosure changes
- no generic /capabilities preflight
```

## Execution Recommendation

Use **Subagent-Driven** execution.

Reason: the task is small but has important phase-boundary guardrails. A fresh worker per task plus review checkpoints helps keep Slice 1 from growing into Slice 2.
