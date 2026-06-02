# Rook Phase 2B Block Mutation Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Phase 2 diagnostics for terminal native proxy failures in `block.definition_mutation` routes, after the managed proxy fallback has already been selected and attempted.

**Architecture:** Keep `RookNative` as the public HTTP surface and preserve the block mutation crash-avoidance fallback. Add explicit optional diagnostic context to the shared proxy path; only block mutation handlers pass that context. Non-block proxy callers keep absent context and preserve their existing response shape.

**Tech Stack:** C++17, Rhino 8 native plugin, `httplib`, `nlohmann::json`, existing C# source-guard tests in `src/Rook.Tests`.

---

## Design Source

Implement only what is authorized by:

`docs/superpowers/specs/2026-06-01-rook-ecosystem-phase-2b-block-mutation-diagnostics-design.md`

Do not implement Phase 2C, BIM, GH, MCP behavior, installer/module manifests, route ownership changes, managed public HTTP, companion loading-policy changes, or `/capabilities` preflight.

## File Structure

- Modify: `src/RookNative/Infrastructure/RouteDiagnostics.h`
  - Add reviewed `block.definition_mutation` terminal proxy diagnostic builders.
  - Keep header-only; do not add `.cpp`, `.vcxproj`, or `.vcxproj.filters` entries.

- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
  - Include `Infrastructure/RouteDiagnostics.h`.
  - Add optional proxy diagnostic context in the anonymous namespace.
  - Keep callback-present branch unchanged.
  - Keep callback-absent fallback ordering through `ProxyManagedRequest`.
  - Emit diagnostics only for terminal proxy failures when context is present.
  - Pass block context only from native block mutation handler functions.

- Modify: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`
  - Add source guards for reason-code catalog entries.
  - Add source guards for fallback ordering, non-block default behavior, block-only context, and pass-through preservation.

## Operation Mapping

Use `/capabilities` operation vocabulary. Batch routes reuse the base operation name because Phase 2B must not add capability operations.

| Route | Diagnostic route | Diagnostic operation |
| --- | --- | --- |
| `/block/set-layers` | `POST /block/set-layers` | `set_layers` |
| `/block/set-layers-batch` | `POST /block/set-layers-batch` | `set_layers` |
| `/block/set-materials` | `POST /block/set-materials` | `set_materials` |
| `/block/set-materials-batch` | `POST /block/set-materials-batch` | `set_materials` |
| `/block/set-object-colors` | `POST /block/set-object-colors` | `set_object_colors` |
| `/block/set-object-colors-batch` | `POST /block/set-object-colors-batch` | `set_object_colors` |
| `/block/set-object-names` | `POST /block/set-object-names` | `set_object_names` |
| `/block/set-object-names-batch` | `POST /block/set-object-names-batch` | `set_object_names` |
| `/block/set-object-user-strings` | `POST /block/set-object-user-strings` | `set_object_user_strings` |
| `/block/set-object-user-strings-batch` | `POST /block/set-object-user-strings-batch` | `set_object_user_strings` |
| `/block/replace-object-geometry` | `POST /block/replace-object-geometry` | `replace_object_geometry` |
| `/block/replace-object-geometry-batch` | `POST /block/replace-object-geometry-batch` | `replace_object_geometry` |
| `/block/transform-object` | `POST /block/transform-object` | `transform_object` |
| `/block/transform-object-batch` | `POST /block/transform-object-batch` | `transform_object` |
| `/block/transform-instance-batch` | `POST /block/transform-instance-batch` | `transform_object` |

`/block/transform-instance-batch` remains companion-backed and uses the closest existing `block.definition_mutation` operation vocabulary. Do not add `transform_instance_batch` to `/capabilities` in this slice.

---

### Task 1: Add Failing Source Guards

**Files:**
- Modify: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`

- [ ] **Step 1: Add reason-code catalog source test**

Insert this test after `ViewportCaptureCallbackUnavailableDiagnostic_UsesReviewedCatalogMetadata`:

```csharp
[Fact]
public void BlockMutationProxyDiagnostics_UseReviewedCatalogMetadata()
{
    var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
    var unavailable = ExtractFunction(header, "BuildBlockMutationManagedProxyUnavailable");
    var forwardFailed = ExtractFunction(header, "BuildBlockMutationManagedProxyForwardFailed");

    Assert.Contains("\"block.definition_mutation\"", unavailable);
    Assert.Contains("\"block_mutation_managed_proxy_unavailable\"", unavailable);
    Assert.Contains("FailureKind::DependencyUnavailable", unavailable);
    Assert.Contains("\"native\"", unavailable);
    Assert.Contains("\"native_managed_proxy_discovery\"", unavailable);
    Assert.Contains("\"native_route\"", unavailable);
    Assert.Contains("diagnostic.retryable = true;", unavailable);
    Assert.Contains("diagnostic.userActionRequired = false;", unavailable);
    Assert.DoesNotContain("diagnostic.state", unavailable);

    Assert.Contains("\"block.definition_mutation\"", forwardFailed);
    Assert.Contains("\"block_mutation_managed_proxy_forward_failed\"", forwardFailed);
    Assert.Contains("FailureKind::DependencyDegraded", forwardFailed);
    Assert.Contains("\"native\"", forwardFailed);
    Assert.Contains("\"native_managed_proxy_transport\"", forwardFailed);
    Assert.Contains("\"native_route\"", forwardFailed);
    Assert.Contains("diagnostic.retryable = true;", forwardFailed);
    Assert.Contains("diagnostic.userActionRequired = false;", forwardFailed);
    Assert.DoesNotContain("diagnostic.state", forwardFailed);
}
```

- [ ] **Step 2: Replace the existing fallback-ordering test with context-aware guards**

Replace `BlockMutationDiagnostics_DoNotBypassManagedProxyFallback` with:

```csharp
[Fact]
public void BlockMutationDiagnostics_DoNotBypassManagedProxyFallback()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var helper = ExtractFunction(source, "DispatchManagedCompanionRouteOrProxy");

    Assert.Contains("callback != nullptr", helper);
    Assert.Contains("DispatchGrasshopperRoute(req, res, path, callback);", helper);
    Assert.Contains("ProxyManagedRequest(req, res, path, isPost", helper);

    var callbackIndex = helper.IndexOf("DispatchGrasshopperRoute(req, res, path, callback);", StringComparison.Ordinal);
    var proxyIndex = helper.IndexOf("ProxyManagedRequest(req, res, path, isPost", StringComparison.Ordinal);
    Assert.True(callbackIndex >= 0, "Callback dispatch branch must remain present.");
    Assert.True(proxyIndex > callbackIndex, "Managed proxy fallback must remain after callback selection.");

    var beforeProxy = helper.Substring(0, proxyIndex);
    Assert.DoesNotContain("SendErrorWithDiagnostic", beforeProxy);
    Assert.DoesNotContain("SendErrorDataWithDiagnostic", beforeProxy);
}
```

- [ ] **Step 3: Add proxy context and pass-through source guards**

Insert these tests after `BlockMutationHandlers_KeepManagedProxyFallbackOwnership`:

```csharp
[Fact]
public void BlockMutationDiagnostics_OnlyBlockHandlersPassDiagnosticContext()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

    Assert.Contains("struct ProxyDiagnosticContext", source);
    Assert.Contains("BuildBlockMutationProxyDiagnosticContext", source);

    var uvPlanar = ExtractFunction(source, "HandleManagedUvPlanar");
    var gameExport = ExtractFunction(source, "HandleManagedGameExportPrepare");
    var proxyCompanion = ExtractFunction(source, "ProxyManagedCompanionRequest");

    Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", uvPlanar);
    Assert.DoesNotContain("&diagnosticContext", uvPlanar);
    Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", gameExport);
    Assert.DoesNotContain("&diagnosticContext", gameExport);
    Assert.DoesNotContain("BuildBlockMutationProxyDiagnosticContext", proxyCompanion);
    Assert.DoesNotContain("&diagnosticContext", proxyCompanion);
}

[Fact]
public void BlockMutationDiagnostics_DoNotInspectSuccessfulManagedProxyResponses()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var forward = ExtractFunction(source, "TryForwardGrasshopperRequest");

    Assert.Contains("res.status = statusCode;", forward);
    Assert.Contains("res.set_content(responseBody, contentType.empty() ? \"application/json\" : contentType.c_str());", forward);

    var successIndex = forward.IndexOf("res.status = statusCode;", StringComparison.Ordinal);
    Assert.True(successIndex >= 0, "Successful proxy response pass-through must remain present.");
    var successTail = forward.Substring(successIndex);

    Assert.DoesNotContain("SendErrorWithDiagnostic", successTail);
    Assert.DoesNotContain("SendErrorDataWithDiagnostic", successTail);
    Assert.DoesNotContain("BuildBlockMutationManagedProxyUnavailable", successTail);
    Assert.DoesNotContain("BuildBlockMutationManagedProxyForwardFailed", successTail);
    Assert.DoesNotContain("nlohmann::json::parse", successTail);
}
```

- [ ] **Step 4: Update block handler ownership guard to require context**

Replace the body of `BlockMutationHandlers_KeepManagedProxyFallbackOwnership` with:

```csharp
var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
var handler = ExtractFunction(source, handlerName);

Assert.Contains("BuildBlockMutationProxyDiagnosticContext(", handler);
Assert.Contains("DispatchManagedCompanionRouteOrProxy(req, res,", handler);
Assert.Contains(route, handler);
Assert.Contains("&diagnosticContext", handler);
Assert.DoesNotContain("SendErrorWithDiagnostic", handler);
Assert.DoesNotContain("SendErrorDataWithDiagnostic", handler);
```

- [ ] **Step 5: Run source tests and verify expected failure**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected: FAIL. The new tests should fail because the block diagnostic helpers and context plumbing do not exist yet.

- [ ] **Step 6: Commit failing tests**

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
git commit -m "test: guard block mutation proxy diagnostics"
```

---

### Task 2: Add Block Diagnostic Catalog Helpers

**Files:**
- Modify: `src/RookNative/Infrastructure/RouteDiagnostics.h`

- [ ] **Step 1: Add block diagnostic helper functions**

Add these functions after `BuildViewportCaptureCallbackUnavailable`:

```cpp
inline nlohmann::json BuildBlockMutationManagedProxyUnavailable(
    const std::string& route,
    const std::string& operation)
{
    RouteDiagnostic diagnostic;
    diagnostic.domainId = "block.definition_mutation";
    diagnostic.route = route;
    diagnostic.operation = operation;
    diagnostic.reasonCode = "block_mutation_managed_proxy_unavailable";
    diagnostic.failureKind = FailureKind::DependencyUnavailable;
    diagnostic.retryable = true;
    diagnostic.userActionRequired = false;
    diagnostic.recommendedNextStep =
        "Wait for managed companion startup, then retry. If the route remains unavailable, inspect /capabilities.";
    diagnostic.ownedBy = "native";
    diagnostic.evidenceSource = "native_managed_proxy_discovery";
    diagnostic.emittedBy = "native_route";
    return ToJson(diagnostic);
}

inline nlohmann::json BuildBlockMutationManagedProxyForwardFailed(
    const std::string& route,
    const std::string& operation)
{
    RouteDiagnostic diagnostic;
    diagnostic.domainId = "block.definition_mutation";
    diagnostic.route = route;
    diagnostic.operation = operation;
    diagnostic.reasonCode = "block_mutation_managed_proxy_forward_failed";
    diagnostic.failureKind = FailureKind::DependencyDegraded;
    diagnostic.retryable = true;
    diagnostic.userActionRequired = false;
    diagnostic.recommendedNextStep =
        "Retry after companion startup has stabilized. If forwarding continues to fail, inspect native and managed logs.";
    diagnostic.ownedBy = "native";
    diagnostic.evidenceSource = "native_managed_proxy_transport";
    diagnostic.emittedBy = "native_route";
    return ToJson(diagnostic);
}
```

Do not set `diagnostic.state`; the route-local evidence does not prove `not_loaded`.

- [ ] **Step 2: Run source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected: Some tests still FAIL because the proxy context implementation is not present. The catalog metadata test should pass.

- [ ] **Step 3: Commit helper functions**

```powershell
git add src/RookNative/Infrastructure/RouteDiagnostics.h
git commit -m "feat: add block mutation proxy diagnostic catalog"
```

---

### Task 3: Add Optional Proxy Diagnostic Context

**Files:**
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`

- [ ] **Step 1: Include the diagnostics header**

Add this include after `Infrastructure/JsonHelpers.h`:

```cpp
#include "Infrastructure/RouteDiagnostics.h"
```

- [ ] **Step 2: Add proxy diagnostic context type**

Add this struct after `enum class BridgeInvokeResult`:

```cpp
struct ProxyDiagnosticContext
{
    std::string route;
    std::string operation;
};
```

- [ ] **Step 3: Update forward declarations**

Replace:

```cpp
void ProxyManagedRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost);

void SendProxyFailure(httplib::Response& res, int status, const std::string& message);
```

with:

```cpp
void ProxyManagedRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost,
    const ProxyDiagnosticContext* diagnosticContext = nullptr);

void SendProxyFailure(
    httplib::Response& res,
    int status,
    const std::string& message,
    const nlohmann::json* diagnostic = nullptr);
```

- [ ] **Step 4: Update `SendProxyFailure`**

Replace the existing `SendProxyFailure` implementation with:

```cpp
void SendProxyFailure(
    httplib::Response& res,
    int status,
    const std::string& message,
    const nlohmann::json* diagnostic)
{
    if (diagnostic != nullptr)
    {
        CRookServer::SendErrorWithDiagnostic(res, message, *diagnostic);
        res.status = status;
        return;
    }

    nlohmann::json envelope;
    envelope["success"] = false;
    envelope["data"] = message;

    res.status = status;
    res.set_content(envelope.dump(), "application/json");
}
```

This preserves the exact old envelope for absent diagnostic context.

- [ ] **Step 5: Add diagnostic helpers local to proxy context**

Add this helper before `ProxyManagedRequest`:

```cpp
nlohmann::json BuildProxyUnavailableDiagnostic(const ProxyDiagnosticContext& context)
{
    return Rook::Diagnostics::BuildBlockMutationManagedProxyUnavailable(
        context.route,
        context.operation);
}

nlohmann::json BuildProxyForwardFailedDiagnostic(const ProxyDiagnosticContext& context)
{
    return Rook::Diagnostics::BuildBlockMutationManagedProxyForwardFailed(
        context.route,
        context.operation);
}
```

- [ ] **Step 6: Update `ProxyManagedRequest` terminal failures**

Replace the existing `ProxyManagedRequest` implementation with:

```cpp
void ProxyManagedRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost,
    const ProxyDiagnosticContext* diagnosticContext)
{
    int managedPort = 0;
    std::string managedHost = "127.0.0.1";
    std::string error;
    if (!TryGetManagedPort(managedPort, managedHost, error))
    {
        if (diagnosticContext != nullptr)
        {
            const auto diagnostic = BuildProxyUnavailableDiagnostic(*diagnosticContext);
            SendProxyFailure(res, 503, error, &diagnostic);
            return;
        }

        SendProxyFailure(res, 503, error);
        return;
    }

    if (!TryForwardGrasshopperRequest(managedPort, managedHost, req, res, path, isPost, error))
    {
        if (diagnosticContext != nullptr)
        {
            const auto diagnostic = BuildProxyForwardFailedDiagnostic(*diagnosticContext);
            SendProxyFailure(res, 502, error, &diagnostic);
            return;
        }

        SendProxyFailure(res, 502, error);
    }
}
```

Do not add any code after successful `TryForwardGrasshopperRequest`; pass-through remains unchanged.

- [ ] **Step 7: Update `DispatchManagedCompanionRouteOrProxy` signature**

Replace the signature and fallback call with:

```cpp
void DispatchManagedCompanionRouteOrProxy(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    GhBridgeCallbackFn callback,
    bool isPost,
    const ProxyDiagnosticContext* diagnosticContext = nullptr)
{
    if (callback != nullptr)
    {
        DispatchGrasshopperRoute(req, res, path, callback);
        return;
    }

    ProxyManagedRequest(req, res, path, isPost, diagnosticContext);
}
```

- [ ] **Step 8: Keep public proxy helper without context**

Ensure `ProxyManagedCompanionRequest` remains:

```cpp
void ProxyManagedCompanionRequest(
    const httplib::Request& req,
    httplib::Response& res,
    const std::string& path,
    bool isPost)
{
    ProxyManagedRequest(req, res, path, isPost);
}
```

- [ ] **Step 9: Run source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected: Some tests still FAIL because block handlers do not yet pass diagnostic context.

- [ ] **Step 10: Commit context plumbing**

```powershell
git add src/RookNative/Handlers/GrasshopperProxyHandler.cpp
git commit -m "feat: add scoped proxy diagnostic context"
```

---

### Task 4: Pass Context Only From Block Mutation Handlers

**Files:**
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`

- [ ] **Step 1: Add block context factory**

Add this helper before `DispatchManagedCompanionRouteOrProxy`:

```cpp
ProxyDiagnosticContext BuildBlockMutationProxyDiagnosticContext(
    const std::string& route,
    const std::string& operation)
{
    ProxyDiagnosticContext context;
    context.route = route;
    context.operation = operation;
    return context;
}
```

- [ ] **Step 2: Update block handler call sites**

For each managed block mutation handler, create a local context and pass it to
`DispatchManagedCompanionRouteOrProxy`.

Example for `HandleManagedBlockSetLayers`:

```cpp
void HandleManagedBlockSetLayers(const httplib::Request& req, httplib::Response& res)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    const auto diagnosticContext =
        BuildBlockMutationProxyDiagnosticContext("POST /block/set-layers", "set_layers");
    DispatchManagedCompanionRouteOrProxy(
        req,
        res,
        "/block/set-layers",
        registration.block_set_layers,
        true,
        &diagnosticContext);
}
```

Apply the same pattern to all 15 companion-backed block mutation handlers using the operation mapping table in this plan.

- [ ] **Step 3: Do not update non-block proxy call sites**

Confirm these functions still call `DispatchManagedCompanionRouteOrProxy` or
`ProxyManagedRequest` without diagnostic context:

```cpp
void HandleManagedUvPlanar(const httplib::Request& req, httplib::Response& res)
void HandleManagedGameExportPrepare(const httplib::Request& req, httplib::Response& res)
void ProxyManagedCompanionRequest(const httplib::Request& req, httplib::Response& res, const std::string& path, bool isPost)
```

- [ ] **Step 4: Run source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~RouteDiagnosticsSourceTests
```

Expected: PASS.

- [ ] **Step 5: Commit block handler context**

```powershell
git add src/RookNative/Handlers/GrasshopperProxyHandler.cpp
git commit -m "feat: scope block mutation proxy diagnostics"
```

---

### Task 5: Add Focused Transport-Preservation Guards

**Files:**
- Modify: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`

- [ ] **Step 1: Add non-block failure-shape source guard**

Insert this test after `BlockMutationDiagnostics_OnlyBlockHandlersPassDiagnosticContext`:

```csharp
[Fact]
public void NonBlockProxyFailures_KeepLegacyEnvelopeWhenContextAbsent()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var proxyCompanion = ExtractFunction(source, "ProxyManagedCompanionRequest");
    var normalized = source.Replace("\r\n", "\n");
    const string marker =
        "void SendProxyFailure(\n" +
        "    httplib::Response& res,\n" +
        "    int status,\n" +
        "    const std::string& message,\n" +
        "    const nlohmann::json* diagnostic)\n" +
        "{";
    var start = normalized.IndexOf(marker, StringComparison.Ordinal);
    Assert.True(start >= 0, "SendProxyFailure implementation must use the reviewed diagnostic-aware signature.");
    var end = normalized.IndexOf("\nvoid CopyManagedResponse", start, StringComparison.Ordinal);
    Assert.True(end > start, "SendProxyFailure implementation must remain before CopyManagedResponse.");
    var sendProxyFailure = normalized.Substring(start, end - start);

    Assert.Contains("if (diagnostic != nullptr)", sendProxyFailure);
    Assert.Contains("CRookServer::SendErrorWithDiagnostic(res, message, *diagnostic);", sendProxyFailure);
    Assert.Contains("envelope[\"success\"] = false;", sendProxyFailure);
    Assert.Contains("envelope[\"data\"] = message;", sendProxyFailure);
    Assert.Contains("res.status = status;", sendProxyFailure);
    Assert.Contains("res.set_content(envelope.dump(), \"application/json\");", sendProxyFailure);

    Assert.Contains("ProxyManagedRequest(req, res, path, isPost);", proxyCompanion);
    Assert.DoesNotContain("&diagnosticContext", proxyCompanion);
}
```

- [ ] **Step 2: Add managed handler legacy/local guard**

Insert this test after `NonBlockProxyFailures_KeepLegacyEnvelopeWhenContextAbsent`:

```csharp
[Fact]
public void ManagedBlockHandlers_DoNotMintPhase2BReasonCodes()
{
    var blocks = ReadSourceFile("src", "Rook", "Handlers", "BlocksHandler.cs");

    Assert.DoesNotContain("block_mutation_managed_proxy_unavailable", blocks);
    Assert.DoesNotContain("block_mutation_managed_proxy_forward_failed", blocks);
    Assert.DoesNotContain("RouteDiagnostic", blocks);
    Assert.Contains("new ApiResponse { Success = false, Data =", blocks);
}
```

- [ ] **Step 3: Run full focused source suite**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeVisionDispatchSourceTests|FullyQualifiedName~ViewportHandlerSourceTests"
```

Expected: PASS.

- [ ] **Step 4: Commit final source guards**

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
git commit -m "test: guard block proxy transport preservation"
```

---

### Task 6: Build And Diff Validation

**Files:**
- No planned edits.

- [ ] **Step 1: Check no project-file churn**

Run:

```powershell
git diff --name-only origin/main...HEAD
```

Expected: changed files are limited to:

```text
docs/superpowers/specs/2026-06-01-rook-ecosystem-phase-2b-block-mutation-diagnostics-design.md
docs/superpowers/plans/2026-06-01-rook-ecosystem-phase-2b-block-mutation-diagnostics.md
src/RookNative/Infrastructure/RouteDiagnostics.h
src/RookNative/Handlers/GrasshopperProxyHandler.cpp
src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
```

No `.vcxproj` or `.vcxproj.filters` files should appear.

- [ ] **Step 2: Run diff whitespace check**

Run:

```powershell
git diff --check origin/main...HEAD
```

Expected: PASS.

- [ ] **Step 3: Run focused managed/source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeVisionDispatchSourceTests|FullyQualifiedName~ViewportHandlerSourceTests"
```

Expected: PASS.

- [ ] **Step 4: Run native MSVC build**

Run from a Visual Studio developer shell or through `vcvarsall`:

```powershell
cmd /c "call \"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat\" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected: native build succeeds with MSVC 14.44.

- [ ] **Step 5: Run live confidence smoke**

Deploy locally using the current repo-local deploy workflow, then run a healthy block route where the callback or proxy path is available.

Expected:

```text
healthy block mutation route still succeeds, or returns its existing managed failure shape
no native diagnostic wrapper appears around a successfully proxied managed response
RookNative remains responsive on /ping
/capabilities still reports block.definition_mutation
```

If a safe harness exists to temporarily make managed proxy discovery unavailable without destabilizing Rhino, also verify:

```text
terminal proxy discovery failure returns legacy data plus diagnostic.reasonCode = block_mutation_managed_proxy_unavailable
terminal proxy forwarding failure returns legacy data plus diagnostic.reasonCode = block_mutation_managed_proxy_forward_failed
```

Do not invent a risky live repro if the safe harness does not exist.

- [ ] **Step 6: Final commit if validation changed only docs/evidence**

If validation updates only the plan or PR notes, commit those changes:

```powershell
git add docs/superpowers/plans/2026-06-01-rook-ecosystem-phase-2b-block-mutation-diagnostics.md
git commit -m "docs: record phase 2b validation notes"
```

Skip this commit if no files changed.

---

## PR Scope Boundaries

The PR body must state:

- Phase 2B only.
- Diagnostics only for terminal native proxy failures after block fallback is selected.
- Callback absence remains evidence before fallback, not a route failure.
- Managed proxy success pass-through is unchanged for managed success and managed failure responses.
- Only block mutation handlers pass diagnostic context.
- Non-block proxy callers preserve current failure behavior.
- Managed `BlocksHandler` operation failures remain legacy/local.
- No `/capabilities` preflight.
- No route ownership, companion loading, installer, MCP behavior, or managed public HTTP changes.

## Self-Review Checklist

- [ ] Every new reason code has `ownedBy`, `evidenceSource`, and `emittedBy`.
- [ ] `block_mutation_managed_proxy_forward_failed` uses `dependency_degraded`.
- [ ] No helper sets `diagnostic.state` for Phase 2B block diagnostics.
- [ ] `ProxyManagedRequest` with absent context preserves the old `SendProxyFailure` envelope.
- [ ] Successful `TryForwardGrasshopperRequest` still only copies managed status/body/content-type.
- [ ] No managed block handler code emits Phase 2B diagnostics.
- [ ] No non-block proxy caller passes diagnostic context.
- [ ] No `.vcxproj` or `.vcxproj.filters` file changed.
