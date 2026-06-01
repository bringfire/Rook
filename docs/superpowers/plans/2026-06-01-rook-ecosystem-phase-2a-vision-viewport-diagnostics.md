# Rook Ecosystem Phase 2A Vision And Viewport Diagnostics Implementation Plan

> **For coder:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan.

## Goal

Extend the Phase 2 route diagnostic contract from Slice 1 to the remaining eligible companion-backed native callback-unavailable paths for:

- `vision.media`
- `viewport.capture`

This slice must remain additive. It must preserve existing route ownership, callback dispatch paths, HTTP status codes, headers, legacy data payloads, parse behavior, validation behavior, and companion loading behavior.

## Architecture Boundary

Phase 2A covers dependency/readiness failures only. It does not convert general route failures into diagnostics.

Eligible failures:

- Vision routes that flow through `ForwardVisionDispatch(...)` and receive `ManagedCreateInvokeResult::Unavailable`.
- `POST /viewport` only when `captureBackend == "tier3"` and `InvokeViewportCaptureTier3WithBody(...)` returns `ManagedCreateInvokeResult::Unavailable`.

Not eligible in this slice:

- Block-definition mutation routes.
- Grasshopper routes.
- RookBIM routes.
- MCP behavior or tool-disclosure changes.
- Installer/module manifests.
- Route ownership changes.
- Managed public HTTP surface.
- Companion loading policy changes.
- Generic `/capabilities` preflight checks.
- Provider API failures.
- Payload validation failures.
- Unknown viewport backend failures.
- Native viewport capture failures.
- No-active-view/native geometry failures.
- Managed callback `Failed` results.
- Ordinary internal exceptions.

## Deferred Block Mutation Safety Boundary

Block-definition mutation is intentionally excluded from Phase 2A.

Block mutation callback absence is not a route failure while `DispatchManagedCompanionRouteOrProxy` can still continue through the managed proxy fallback.

That fallback exists because native block-definition mutation has a known Rhino crash history. It is crash-avoidance architecture, not legacy debt. This slice must add source coverage that prevents diagnostics from bypassing or reordering that fallback.

## Reason-Code Catalog Delta

Add one new Phase 2A route diagnostic reason code:

```text
reasonCode: viewport_capture_callback_unavailable
domainId: viewport.capture
failureKind: domain_unavailable
ownedBy: native
evidenceSource: native_callback_registration
emittedBy: native_route
state: not_loaded
retryable: true
userActionRequired: false
```

The existing Slice 1 code remains valid:

```text
reasonCode: vision_dispatch_callback_unavailable
domainId: vision.media
failureKind: domain_unavailable
ownedBy: native
evidenceSource: native_callback_registration
emittedBy: native_route
state: not_loaded
retryable: true
userActionRequired: false
```

No `block_mutation_*`, `bim_*`, or `gh_*` reason code may be introduced in this slice.

## Files

Modify:

- `src/RookNative/Infrastructure/RouteDiagnostics.h`
- `src/RookNative/Handlers/VisionHandler.cpp`
- `src/RookNative/Handlers/ViewportHandler.cpp`
- `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`
- `src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs`

Create:

- `src/Rook.Tests/Handlers/ViewportHandlerSourceTests.cs`

Do not modify:

- `src/RookNative/RookNative.vcxproj`
- `src/RookNative/RookNative.vcxproj.filters`
- installer files
- MCP behavior/tool-disclosure code
- managed companion loading code
- route registrations

## Task 1: Add Failing Catalog And Block-Safety Source Guards

Update `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`.

First, update the existing Slice 1 breadth guard intentionally. Do not delete it wholesale. Rename it to reflect the Phase 2A boundary and allow the viewport code while continuing to reject block, BIM, and GH drift.

Replace the existing Slice 1 breadth guard with this shape:

```csharp
[Fact]
public void Phase2A_DoesNotAdoptBlockBimOrGhDiagnostics()
{
    var visionSource = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
    var viewportSource = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
    var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
    var catalogAndSource = visionSource + viewportSource + header;

    Assert.Contains("vision_dispatch_callback_unavailable", catalogAndSource);
    Assert.Contains("viewport_capture_callback_unavailable", catalogAndSource);
    Assert.DoesNotContain("block_mutation_callback_unavailable", catalogAndSource);
    Assert.DoesNotContain("bim_dispatch_callback_unavailable", catalogAndSource);
    Assert.DoesNotContain("gh_bridge_callback_unavailable", catalogAndSource);
}
```

Add a catalog metadata guard for the viewport helper:

```csharp
[Fact]
public void ViewportCaptureCallbackUnavailableDiagnostic_UsesReviewedCatalogMetadata()
{
    var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
    var helper = ExtractFunction(header, "BuildViewportCaptureCallbackUnavailable");

    Assert.Contains("\"viewport.capture\"", helper);
    Assert.Contains("\"viewport_capture_callback_unavailable\"", helper);
    Assert.Contains("FailureKind::DomainUnavailable", helper);
    Assert.Contains("\"native\"", helper);
    Assert.Contains("\"native_callback_registration\"", helper);
    Assert.Contains("\"native_route\"", helper);
    Assert.Contains("\"not_loaded\"", helper);
    Assert.Contains("diagnostic.retryable = true;", helper);
    Assert.Contains("diagnostic.userActionRequired = false;", helper);
}
```

Add the block fallback safety source guard:

```csharp
[Fact]
public void BlockMutationDiagnostics_DoNotBypassManagedProxyFallback()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var helper = ExtractFunction(source, "DispatchManagedCompanionRouteOrProxy");

    Assert.Contains("callback != nullptr", helper);
    Assert.Contains("DispatchGrasshopperRoute(req, res, path, callback);", helper);
    Assert.Contains("ProxyManagedRequest(req, res, path, isPost);", helper);

    var proxyIndex = helper.IndexOf("ProxyManagedRequest(req, res, path, isPost);", StringComparison.Ordinal);
    Assert.True(proxyIndex >= 0, "Managed proxy fallback must remain present.");

    var beforeProxy = helper[..proxyIndex];
    Assert.DoesNotContain("SendErrorWithDiagnostic", beforeProxy);
    Assert.DoesNotContain("SendErrorDataWithDiagnostic", beforeProxy);
}
```

Add a second block ownership guard so the route handlers keep using the fallback helper. This proves the crash-avoidance invariant at the caller layer, not only inside the shared helper:

```csharp
[Theory]
[InlineData("HandleManagedBlockSetLayers", "\"/block/set-layers\"")]
[InlineData("HandleManagedBlockSetLayersBatch", "\"/block/set-layers-batch\"")]
[InlineData("HandleManagedBlockSetMaterials", "\"/block/set-materials\"")]
[InlineData("HandleManagedBlockSetMaterialsBatch", "\"/block/set-materials-batch\"")]
[InlineData("HandleManagedBlockSetObjectColors", "\"/block/set-object-colors\"")]
[InlineData("HandleManagedBlockSetObjectColorsBatch", "\"/block/set-object-colors-batch\"")]
[InlineData("HandleManagedBlockSetObjectNames", "\"/block/set-object-names\"")]
[InlineData("HandleManagedBlockSetObjectNamesBatch", "\"/block/set-object-names-batch\"")]
[InlineData("HandleManagedBlockSetObjectUserStrings", "\"/block/set-object-user-strings\"")]
[InlineData("HandleManagedBlockSetObjectUserStringsBatch", "\"/block/set-object-user-strings-batch\"")]
[InlineData("HandleManagedBlockReplaceObjectGeometry", "\"/block/replace-object-geometry\"")]
[InlineData("HandleManagedBlockReplaceObjectGeometryBatch", "\"/block/replace-object-geometry-batch\"")]
[InlineData("HandleManagedBlockTransformObject", "\"/block/transform-object\"")]
[InlineData("HandleManagedBlockTransformObjectBatch", "\"/block/transform-object-batch\"")]
[InlineData("HandleManagedBlockTransformInstanceBatch", "\"/block/transform-instance-batch\"")]
public void BlockMutationHandlers_KeepManagedProxyFallbackOwnership(string handlerName, string route)
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var handler = ExtractFunction(source, handlerName);

    Assert.Contains("DispatchManagedCompanionRouteOrProxy(req, res,", handler);
    Assert.Contains(route, handler);
    Assert.DoesNotContain("SendErrorWithDiagnostic", handler);
    Assert.DoesNotContain("SendErrorDataWithDiagnostic", handler);
}
```

If `RouteDiagnosticsSourceTests.cs` does not already have `ExtractFunction(...)` available for the block guard, add a private helper following the local source-test style:

```csharp
private static string ExtractFunction(string source, string functionName)
{
    var signatureIndex = source.IndexOf(functionName, StringComparison.Ordinal);
    Assert.True(signatureIndex >= 0, $"Could not find function {functionName}.");

    var bodyStart = source.IndexOf('{', signatureIndex);
    Assert.True(bodyStart >= 0, $"Could not find body start for {functionName}.");

    var depth = 0;
    for (var i = bodyStart; i < source.Length; i++)
    {
        if (source[i] == '{')
        {
            depth++;
        }
        else if (source[i] == '}')
        {
            depth--;
            if (depth == 0)
            {
                return source.Substring(signatureIndex, i - signatureIndex + 1);
            }
        }
    }

    throw new InvalidOperationException($"Could not extract function {functionName}.");
}
```

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected result: failing test for missing `BuildViewportCaptureCallbackUnavailable` / missing `viewport_capture_callback_unavailable`. The block fallback guard should pass against current code.

Commit:

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
git commit -m "test: pin phase 2a diagnostic catalog boundary"
```

## Task 2: Add The Viewport Diagnostic Catalog Helper

Update `src/RookNative/Infrastructure/RouteDiagnostics.h`.

Add a helper next to `BuildVisionDispatchCallbackUnavailable(...)`. Match the existing helper contract: return `nlohmann::json`, fill a `RouteDiagnostic`, and return `ToJson(diagnostic)`.

```cpp
inline nlohmann::json BuildViewportCaptureCallbackUnavailable(
    const std::string& route,
    const std::string& operation)
{
    RouteDiagnostic diagnostic;
    diagnostic.domainId = "viewport.capture";
    diagnostic.route = route;
    diagnostic.operation = operation;
    diagnostic.reasonCode = "viewport_capture_callback_unavailable";
    diagnostic.failureKind = FailureKind::DomainUnavailable;
    diagnostic.state = "not_loaded";
    diagnostic.retryable = true;
    diagnostic.userActionRequired = false;
    diagnostic.ownedBy = "native";
    diagnostic.evidenceSource = "native_callback_registration";
    diagnostic.emittedBy = "native_route";
    diagnostic.recommendedNextStep =
        "Wait for companion startup, then retry. If it remains unavailable, inspect /capabilities.";
    return ToJson(diagnostic);
}
```

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected result: pass.

Commit:

```powershell
git add src/RookNative/Infrastructure/RouteDiagnostics.h src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
git commit -m "feat: add viewport capture callback diagnostic catalog entry"
```

## Task 3: Add Failing Vision Adoption Source Guards

Update `src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs`.

The Slice 1 test that asserted only one vision diagnostic adoption must be replaced with Phase 2A coverage. Do not remove the unavailable-branch transport preservation test.

Add a route table proving every eligible `/vision/*` handler supplies route and operation context for the callback-unavailable diagnostic path:

```csharp
[Theory]
[InlineData("HandleVisionGenerate", "\"POST /vision/generate\"", "\"generate\"")]
[InlineData("HandleVisionEnhancePrompt", "\"POST /vision/enhance-prompt\"", "\"enhance_prompt\"")]
[InlineData("HandleVisionCaptureDepth", "\"POST /vision/capture-depth\"", "\"capture_depth\"")]
[InlineData("HandleVisionDirectorPublishVideo", "\"POST /vision/director/publish-video\"", "\"publish_director_video\"")]
[InlineData("HandleVisionConsumeApproved", "\"POST /vision/artifacts/consume-approved\"", "\"consume_approved\"")]
[InlineData("HandleVisionApproveArtifact", "\"POST /vision/artifacts/{artifact_id}/approve\"", "\"approve_artifact\"")]
[InlineData("HandleVisionListArtifacts", "\"GET /vision/artifacts\"", "\"list_artifacts\"")]
[InlineData("HandleVisionGetArtifact", "\"GET /vision/artifacts/{artifact_id}\"", "\"get_artifact\"")]
[InlineData("HandleVisionDeleteArtifact", "\"DELETE /vision/artifacts/{artifact_id}\"", "\"delete_artifact\"")]
[InlineData("HandleVisionVideoSubmit", "\"POST /vision/video/jobs\"", "\"submit_video_job\"")]
[InlineData("HandleVisionVideoJobsList", "\"GET /vision/video/jobs\"", "\"list_video_jobs\"")]
[InlineData("HandleVisionVideoModelsList", "\"GET /vision/video/models\"", "\"list_video_models\"")]
[InlineData("HandleVisionVideoEstimate", "\"POST /vision/video/estimate\"", "\"estimate_video_job\"")]
[InlineData("HandleVisionVideoCancel", "\"POST /vision/video/jobs/{job_id}/cancel\"", "\"cancel_video_job\"")]
[InlineData("HandleVisionVideoResult", "\"GET /vision/video/jobs/{job_id}/result\"", "\"get_video_job_result\"")]
[InlineData("HandleVisionVideoStatus", "\"GET /vision/video/jobs/{job_id}\"", "\"get_video_job\"")]
public void VisionRoutes_ProvideDiagnosticRouteAndOperationContext(string handlerName, string route, string operation)
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
    var handler = ExtractFunction(source, handlerName);

    Assert.Contains(route, handler);
    Assert.Contains(operation, handler);
}
```

Update the existing path-route tests for the new `DispatchVisionOpWithPathId(req, res, route, op, field)` signature. The current tests assert the old `(req, res, op, field)` call shape and must be changed intentionally.

Use this shape for artifact paths:

```csharp
[Theory]
[InlineData("HandleVisionGetArtifact", "GET /vision/artifacts/{artifact_id}", "get_artifact", "artifact_id")]
[InlineData("HandleVisionApproveArtifact", "POST /vision/artifacts/{artifact_id}/approve", "approve_artifact", "artifact_id")]
[InlineData("HandleVisionDeleteArtifact", "DELETE /vision/artifacts/{artifact_id}", "delete_artifact", "artifact_id")]
public void ArtifactPathRoutes_InjectArtifactId(
    string handlerName,
    string routeTemplate,
    string op,
    string fieldName)
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
    var handler = ExtractFunction(source, handlerName);

    Assert.Contains(
        $"DispatchVisionOpWithPathId(req, res, \"{routeTemplate}\", \"{op}\", \"{fieldName}\");",
        handler);
}
```

Use this shape for video job paths:

```csharp
[Theory]
[InlineData("HandleVisionVideoStatus", "GET /vision/video/jobs/{job_id}", "get_video_job", "job_id")]
[InlineData("HandleVisionVideoCancel", "POST /vision/video/jobs/{job_id}/cancel", "cancel_video_job", "job_id")]
[InlineData("HandleVisionVideoResult", "GET /vision/video/jobs/{job_id}/result", "get_video_job_result", "job_id")]
public void VideoPathRoutes_InjectJobId(
    string handlerName,
    string routeTemplate,
    string op,
    string fieldName)
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
    var handler = ExtractFunction(source, handlerName);

    Assert.Contains(
        $"DispatchVisionOpWithPathId(req, res, \"{routeTemplate}\", \"{op}\", \"{fieldName}\");",
        handler);
    Assert.DoesNotContain(
        $"DispatchVisionOpWithPathId(req, res, \"{routeTemplate}\", \"{op}\", \"artifact_id\");",
        handler);
}
```

Replace or rewrite the old `VisionDispatchDiagnostic_IsOnlyEmittedForOptedInUnavailablePath` test so it verifies the diagnostic is still emitted only by the unavailable dispatch path, not by parse/validation paths:

```csharp
[Fact]
public void VisionDispatchDiagnostics_RemainUnavailableOnly()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
    var forward = ExtractFunction(source, "ForwardVisionDispatch");
    var parse = ExtractFunction(source, "ParseBodyAsObject");

    Assert.Contains("BuildVisionDispatchCallbackUnavailable", source);
    Assert.Contains("ManagedCreateInvokeResult::Unavailable", forward);
    Assert.Contains("SendErrorWithDiagnostic", forward);
    Assert.DoesNotContain("SendErrorWithDiagnostic", parse);
}
```

Keep the existing transport preservation guard for `ForwardVisionDispatch(...)` and make sure it still asserts:

```text
CRookServer::SendErrorWithDiagnostic
res.status = 503;
res.set_header("X-Rook-Vision-Op", op);
```

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeVisionDispatchSourceTests
```

Expected result: failing tests for route/operation context on handlers that do not yet pass diagnostic context.

Commit:

```powershell
git add src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs
git commit -m "test: require vision unavailable diagnostics across dispatch routes"
```

## Task 4: Extend Vision Unavailable Diagnostics Across ForwardVisionDispatch Routes

Update `src/RookNative/Handlers/VisionHandler.cpp`.

Add a small wrapper near `ForwardVisionDispatch(...)`:

```cpp
void ForwardVisionDispatchWithUnavailableDiagnostic(
    httplib::Response& res,
    const char* route,
    const char* op,
    nlohmann::json& body)
{
    const auto unavailableDiagnostic =
        Rook::Diagnostics::BuildVisionDispatchCallbackUnavailable(route, op);
    ForwardVisionDispatch(res, op, body, &unavailableDiagnostic);
}
```

Change helper signatures so route context is passed only to the final dispatch path:

```cpp
void DispatchVisionOp(
    const httplib::Request& req,
    httplib::Response& res,
    const char* route,
    const char* op)
```

```cpp
void DispatchVisionOpWithPathId(
    const httplib::Request& req,
    httplib::Response& res,
    const char* route,
    const char* op,
    const char* pathIdField)
```

```cpp
void DispatchVisionListWithQuery(
    const httplib::Request& req,
    httplib::Response& res,
    const char* route,
    const char* op)
```

```cpp
void DispatchVideoJobsList(
    httplib::Response& res,
    const httplib::Request& req,
    const char* route,
    const char* op)
```

In each helper, preserve existing parse/validation failures exactly. Only the final call into `ForwardVisionDispatch(...)` should become:

```cpp
ForwardVisionDispatchWithUnavailableDiagnostic(res, route, op, body);
```

Update handler call sites with stable route templates:

```cpp
DispatchVisionOp(req, res, "POST /vision/generate", "generate");
DispatchVisionOp(req, res, "POST /vision/enhance-prompt", "enhance_prompt");
DispatchVisionOp(req, res, "POST /vision/capture-depth", "capture_depth");
DispatchVisionOp(req, res, "POST /vision/director/publish-video", "publish_director_video");
DispatchVisionOp(req, res, "POST /vision/artifacts/consume-approved", "consume_approved");
DispatchVisionOpWithPathId(req, res, "POST /vision/artifacts/{artifact_id}/approve", "approve_artifact", "artifact_id");
DispatchVisionListWithQuery(req, res, "GET /vision/artifacts", "list_artifacts");
DispatchVisionOpWithPathId(req, res, "GET /vision/artifacts/{artifact_id}", "get_artifact", "artifact_id");
DispatchVisionOpWithPathId(req, res, "DELETE /vision/artifacts/{artifact_id}", "delete_artifact", "artifact_id");
DispatchVisionOp(req, res, "POST /vision/video/jobs", "submit_video_job");
DispatchVideoJobsList(res, req, "GET /vision/video/jobs", "list_video_jobs");
ForwardVisionDispatchWithUnavailableDiagnostic(res, "GET /vision/video/models", "list_video_models", body);
DispatchVisionOp(req, res, "POST /vision/video/estimate", "estimate_video_job");
DispatchVisionOpWithPathId(req, res, "POST /vision/video/jobs/{job_id}/cancel", "cancel_video_job", "job_id");
DispatchVisionOpWithPathId(req, res, "GET /vision/video/jobs/{job_id}/result", "get_video_job_result", "job_id");
DispatchVisionOpWithPathId(req, res, "GET /vision/video/jobs/{job_id}", "get_video_job", "job_id");
```

Do not add diagnostics to `ParseBodyAsObject(...)`, path-id validation failures, payload validation failures, provider/model failures, or `ManagedCreateInvokeResult::Failed`.

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~NativeVisionDispatchSourceTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected result: pass.

Commit:

```powershell
git add src/RookNative/Handlers/VisionHandler.cpp src/Rook.Tests/Handlers/NativeVisionDispatchSourceTests.cs
git commit -m "feat: add diagnostics to vision callback unavailable routes"
```

## Task 5: Add Failing Viewport Source Guards

Create `src/Rook.Tests/Handlers/ViewportHandlerSourceTests.cs`.

Use the same source-test style as neighboring handler source tests. Include helpers to read source files and extract functions.

Add:

```csharp
using System;
using System.IO;
using System.Linq;
using Xunit;

namespace Rook.Tests.Handlers;

public sealed class ViewportHandlerSourceTests
{
    [Fact]
    public void ViewportTier3Unavailable_AddsDiagnosticAndPreservesTransportContract()
    {
        var source = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
        var handleViewport = ExtractFunction(source, "HandleViewport");
        var unavailableBranch = ExtractBetween(
            handleViewport,
            "case ManagedCreateInvokeResult::Unavailable:",
            "case ManagedCreateInvokeResult::Failed:");

        Assert.Contains("BuildViewportCaptureCallbackUnavailable", unavailableBranch);
        Assert.Contains("CRookServer::SendErrorWithDiagnostic", unavailableBranch);
        Assert.Contains("res.status = 503;", unavailableBranch);
        Assert.Contains("res.set_header(\"X-Rook-Viewport-Backend\", \"tier3-unavailable\");", unavailableBranch);
    }

    [Fact]
    public void ViewportDiagnostics_DoNotMapUnknownBackendOrManagedFailedBranches()
    {
        var source = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
        var handleViewport = ExtractFunction(source, "HandleViewport");

        var unknownBackendBranch = ExtractBetween(
            handleViewport,
            "if (!captureBackend.empty()",
            "if (captureBackend == \"tier3\")");
        Assert.Contains("Unknown captureBackend '", unknownBackendBranch);
        Assert.Contains("Expected 'legacy' or 'tier3' (or omit the field).", unknownBackendBranch);
        Assert.Contains("CRookServer::SendError(res,", unknownBackendBranch);
        Assert.Contains("res.status = 400;", unknownBackendBranch);
        Assert.DoesNotContain("SendErrorWithDiagnostic", unknownBackendBranch);

        var failedBranch = ExtractBetween(
            handleViewport,
            "case ManagedCreateInvokeResult::Failed:",
            "}");
        Assert.Contains("CRookServer::SendError(res,", failedBranch);
        Assert.Contains("Tier 3 viewport capture failed:", failedBranch);
        Assert.Contains("+ invokeError", failedBranch);
        Assert.Contains("res.status = 500;", failedBranch);
        Assert.Contains("res.set_header(\"X-Rook-Viewport-Backend\", \"tier3-failed\");", failedBranch);
        Assert.DoesNotContain("SendErrorWithDiagnostic", failedBranch);
    }

    private static string ReadSourceFile(params string[] parts)
    {
        var root = FindRepositoryRoot();
        return File.ReadAllText(Path.Combine(new[] { root }.Concat(parts).ToArray()));
    }

    private static string FindRepositoryRoot()
    {
        var current = AppContext.BaseDirectory;
        while (current is not null)
        {
            if (File.Exists(Path.Combine(current, "Rook.sln")))
            {
                return current;
            }

            current = Directory.GetParent(current)?.FullName;
        }

        throw new InvalidOperationException("Could not find repository root.");
    }

    private static string ExtractFunction(string source, string functionName)
    {
        var signatureIndex = source.IndexOf(functionName, StringComparison.Ordinal);
        Assert.True(signatureIndex >= 0, $"Could not find function {functionName}.");

        var bodyStart = source.IndexOf('{', signatureIndex);
        Assert.True(bodyStart >= 0, $"Could not find body start for {functionName}.");

        var depth = 0;
        for (var i = bodyStart; i < source.Length; i++)
        {
            if (source[i] == '{')
            {
                depth++;
            }
            else if (source[i] == '}')
            {
                depth--;
                if (depth == 0)
                {
                    return source.Substring(signatureIndex, i - signatureIndex + 1);
                }
            }
        }

        throw new InvalidOperationException($"Could not extract function {functionName}.");
    }

    private static string ExtractBetween(string source, string start, string end)
    {
        var startIndex = source.IndexOf(start, StringComparison.Ordinal);
        Assert.True(startIndex >= 0, $"Could not find start marker: {start}");

        var endIndex = source.IndexOf(end, startIndex + start.Length, StringComparison.Ordinal);
        Assert.True(endIndex >= 0, $"Could not find end marker: {end}");

        return source.Substring(startIndex, endIndex - startIndex);
    }
}
```

If the project already has a shared source-test helper pattern that differs from this snippet, follow the local pattern instead of introducing duplicate utility style.

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~ViewportHandlerSourceTests
```

Expected result: failing test for missing viewport diagnostic helper call in `HandleViewport`.

Commit:

```powershell
git add src/Rook.Tests/Handlers/ViewportHandlerSourceTests.cs
git commit -m "test: pin viewport unavailable diagnostic behavior"
```

## Task 6: Add Viewport Tier3 Callback-Unavailable Diagnostic

Update `src/RookNative/Handlers/ViewportHandler.cpp`.

Add the include near the other local includes:

```cpp
#include "Infrastructure/RouteDiagnostics.h"
```

In `HandleViewport(...)`, modify only the `ManagedCreateInvokeResult::Unavailable` branch under `captureBackend == "tier3"`:

```cpp
case ManagedCreateInvokeResult::Unavailable:
{
    const auto unavailableDiagnostic =
        Rook::Diagnostics::BuildViewportCaptureCallbackUnavailable(
            "POST /viewport",
            "viewport_capture_tier3");
    CRookServer::SendErrorWithDiagnostic(
        res,
        "Tier 3 viewport capture requires the Rook companion plugin. Ensure Rook.rhp is loaded in Rhino, then retry.",
        unavailableDiagnostic);
    res.status = 503;
    res.set_header("X-Rook-Viewport-Backend", "tier3-unavailable");
    return;
}
```

Do not change:

- unknown backend branch
- native viewport capture path
- no-active-view behavior
- `ManagedCreateInvokeResult::Failed`
- existing `503`
- `X-Rook-Viewport-Backend: tier3-unavailable`

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~ViewportHandlerSourceTests
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected result: pass.

Commit:

```powershell
git add src/RookNative/Handlers/ViewportHandler.cpp src/Rook.Tests/Handlers/ViewportHandlerSourceTests.cs
git commit -m "feat: add viewport callback unavailable diagnostic"
```

## Task 7: Full Source Validation

Run the focused source and contract suite:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeVisionDispatchSourceTests|FullyQualifiedName~ViewportHandlerSourceTests|FullyQualifiedName~CapabilityDiscoverySourceTests|FullyQualifiedName~MainThreadDispatcherSourceTests"
```

Run whitespace validation:

```powershell
git diff --check origin/main...HEAD
```

Check project-file drift:

```powershell
git diff --name-only origin/main...HEAD | Select-String -Pattern '\.vcxproj(\.filters)?$'
```

Expected result: no output.

Commit any test-only fixups if needed.

## Task 8: Native Build Validation

Run the native build with the known-good MSVC toolset:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected result: build succeeds without requiring `.vcxproj` or `.vcxproj.filters` edits.

If MSVC reports a build issue, fix only the local code issue. Do not add project-file changes unless a reviewer explicitly approves a new exception.

## Task 9: Optional Live Smoke After Review

This slice does not require a Rhino live smoke before opening a draft PR, because the touched failures are callback-unavailable branches and the source/native build gates carry the main risk.

If a live smoke is requested before merge, use an installed build from the branch and verify only healthy behavior:

```text
1. Launch Rhino normally.
2. Confirm RookNative starts.
3. Confirm /capabilities still returns live state.
4. Call GET /vision/video/models and confirm the healthy path still succeeds.
5. Call POST /viewport with the existing default/native capture path and confirm healthy behavior is unchanged.
```

Do not force companion unload or intentionally break callback registration inside live Rhino unless a separate reviewer-approved diagnostic test harness exists.

## Final Review Checklist

Before PR processing, confirm:

- `vision_dispatch_callback_unavailable` is emitted for `/vision/*` only when `ForwardVisionDispatch(...)` sees `ManagedCreateInvokeResult::Unavailable`.
- `viewport_capture_callback_unavailable` is emitted only for `POST /viewport` with `captureBackend == "tier3"` and `ManagedCreateInvokeResult::Unavailable`.
- Vision parse/validation failures keep legacy behavior.
- Viewport unknown backend, native capture failures, no-active-view failures, and managed `Failed` keep legacy behavior.
- `DispatchManagedCompanionRouteOrProxy(...)` still calls `ProxyManagedRequest(...)` as fallback before any diagnostic helper can appear.
- No block, BIM, or GH reason codes were added.
- No `/capabilities` preflight sweep was added.
- No route registrations changed.
- No route ownership changed.
- No companion loading code changed.
- No `.vcxproj` or `.vcxproj.filters` files changed.

## Completion Options

After this plan is reviewed and approved:

1. **Subagent-Driven Execution**: use separate implementation workers with review after Task 4 and Task 6. This is recommended because the vision and viewport adoptions are independent, and the block safety guard deserves a review checkpoint before any route code changes.
2. **Inline Execution**: implement all tasks in this session with commits after each task. This is acceptable if the reviewer wants tighter control over the exact source-test wording.
