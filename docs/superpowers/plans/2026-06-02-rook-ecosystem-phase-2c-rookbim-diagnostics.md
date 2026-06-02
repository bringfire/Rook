# Rook Ecosystem Phase 2C RookBIM Diagnostics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Phase 2C additive route diagnostics for RookBIM readiness, host, module, and active-document failures while preserving existing BIM route behavior.

**Architecture:** Implement two reviewed sub-slices under one Phase 2C PR. Native emits only `bim_dispatch_callback_unavailable` from callback-registration evidence; managed `BimHandler` emits BIM-only diagnostics from existing RookBIM runtime/module evidence. Native callback-success responses remain opaque pass-through, and non-BIM managed bridge serializers keep their current response shape.

**Tech Stack:** C++17 RookNative with `httplib` and `nlohmann::json`; C#/.NET managed companion with `System.Text.Json` / `JsonNode`; xUnit source/contract tests.

---

## Scope Source

Approved design:

- `docs/superpowers/specs/2026-06-02-rook-ecosystem-phase-2c-rookbim-diagnostics-design.md`

This plan implements only the design-approved Phase 2C scope:

- native `bim_dispatch_callback_unavailable`;
- BIM-only managed diagnostic serialization;
- reviewed managed/RookBIM readiness codes;
- no BIM operation taxonomy expansion.

## File Structure

Modify:

- `src/RookNative/Infrastructure/RouteDiagnostics.h`
  - Add one native BIM diagnostic helper for `bim_dispatch_callback_unavailable`.
- `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
  - Add BIM route string context to `ForwardBimDispatch`.
  - Add optional diagnostic support to `SendBimDispatchError`.
  - Emit native diagnostic only for `ManagedCreateInvokeResult::Unavailable`.
  - Preserve `Failed`, parse/body failures, and callback-success pass-through.
- `src/Rook/ApiResponse.cs`
  - Add optional `Diagnostic` property. It is not serialized by default bridge paths.
- `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
  - Add BIM-only response-envelope serialization that includes `diagnostic` only for `ExecuteBimDispatchCallback`.
  - Keep `ExecuteApiResponseCallback`, `ExecuteAsyncApiResponseCallback`, and `ExecuteOffUiApiResponseCallback` unchanged.
- `src/Rook/Handlers/BimHandler.cs`
  - Add BIM diagnostic builders for reviewed readiness/host/module/document codes.
  - Attach diagnostics only when existing runtime/module evidence permits it.

Test:

- `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`
- `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`
- `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- `src/RookBim.Tests/RookBimModuleSourceTests.cs` only if an existing boundary guard needs a precise assertion update.

Do not modify:

- `src/RookNative/RookNative.vcxproj`
- `src/RookNative/RookNative.vcxproj.filters`
- installer files
- MCP behavior/tool-disclosure files
- route registration code except source-test assertions that inspect it

---

### Task 1: Native Phase 2C Source Guards

**Files:**
- Modify: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`
- Modify: `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`

- [ ] **Step 1: Add the diagnostic catalog source guard**

Add this test to `RouteDiagnosticsSourceTests` after `BlockMutationProxyDiagnostics_UseReviewedCatalogMetadata`.

```csharp
[Fact]
public void BimDispatchCallbackUnavailableDiagnostic_UsesReviewedCatalogMetadata()
{
    var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
    var helper = ExtractFunction(header, "BuildBimDispatchCallbackUnavailable");

    Assert.Contains("\"bim.rhino_inside_revit\"", helper);
    Assert.Contains("\"bim_dispatch_callback_unavailable\"", helper);
    Assert.Contains("FailureKind::DomainUnavailable", helper);
    Assert.Contains("\"native\"", helper);
    Assert.Contains("\"native_callback_registration\"", helper);
    Assert.Contains("\"native_route\"", helper);
    Assert.Contains("\"not_loaded\"", helper);
    Assert.Contains("diagnostic.retryable = true;", helper);
    Assert.Contains("diagnostic.userActionRequired = false;", helper);
}
```

- [ ] **Step 2: Update the unsafe-code guard to allow the reviewed BIM code**

Replace the current `RouteDiagnostics_DoNotMintUnsafeCallbackBimOrGhReasonCodes` body with this version. It permits the reviewed native BIM callback reason but still rejects broad or wrong BIM/GH reason codes.

```csharp
[Fact]
public void RouteDiagnostics_DoNotMintUnsafeCallbackBimOrGhReasonCodes()
{
    var visionSource = ReadSourceFile("src", "RookNative", "Handlers", "VisionHandler.cpp");
    var viewportSource = ReadSourceFile("src", "RookNative", "Handlers", "ViewportHandler.cpp");
    var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
    var catalogAndSource = visionSource + viewportSource + header;

    Assert.Contains("vision_dispatch_callback_unavailable", catalogAndSource);
    Assert.Contains("viewport_capture_callback_unavailable", catalogAndSource);
    Assert.Contains("bim_dispatch_callback_unavailable", catalogAndSource);
    Assert.DoesNotContain("block_mutation_callback_unavailable", catalogAndSource);
    Assert.DoesNotContain("gh_bridge_callback_unavailable", catalogAndSource);
    Assert.DoesNotContain("bim_unavailable", catalogAndSource);
    Assert.DoesNotContain("bridge_unavailable", catalogAndSource);
    Assert.DoesNotContain("managed_dependency_unavailable", catalogAndSource);
}
```

- [ ] **Step 3: Add native BIM response-branch guards**

Add these tests to `NativeBimDispatchSourceTests` after `RookServer_BimDispatchErrorCallSitesUseStableErrorCodes`.

```csharp
[Fact]
public void RookServer_BimUnavailableBranchAddsDiagnosticAndPreservesLegacyTransport()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var forward = ExtractFunction(source, "ForwardBimDispatch");
    var sendError = ExtractFunction(source, "SendBimDispatchError");

    Assert.Contains("BuildBimDispatchCallbackUnavailable(route, op)", forward);
    Assert.Contains("ManagedCreateInvokeResult::Unavailable", forward);
    Assert.Contains("\"rookbim_unavailable\"", forward);
    Assert.Contains("503,", forward);
    Assert.Contains("&diagnostic", forward);
    Assert.Contains("envelope[\"diagnostic\"] = *diagnostic;", sendError);
    Assert.Contains("res.set_header(\"X-Rook-Bim-Op\", op);", sendError);
}

[Fact]
public void RookServer_BimFailedAndParseBranchesRemainLegacyLocal()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var forward = ExtractFunction(source, "ForwardBimDispatch");
    var parse = ExtractFunction(source, "ParseBimPostBody");

    var failedBranchStart = forward.IndexOf("case ManagedCreateInvokeResult::Failed:", StringComparison.Ordinal);
    Assert.True(failedBranchStart >= 0, "ForwardBimDispatch must keep a Failed branch.");
    var failedBranch = forward.Substring(failedBranchStart);

    Assert.Contains("\"internal_error\"", failedBranch);
    Assert.DoesNotContain("BuildBimDispatchCallbackUnavailable", failedBranch);
    Assert.DoesNotContain("SendErrorWithDiagnostic", failedBranch);
    Assert.DoesNotContain("SendErrorDataWithDiagnostic", failedBranch);

    Assert.Contains("\"invalid_scope\"", parse);
    Assert.DoesNotContain("BuildBimDispatchCallbackUnavailable", parse);
    Assert.DoesNotContain("SendErrorWithDiagnostic", parse);
    Assert.DoesNotContain("SendErrorDataWithDiagnostic", parse);
}

[Fact]
public void RookServer_BimSuccessDispatchRemainsOpaquePassThrough()
{
    var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");
    var forward = ExtractFunction(source, "ForwardBimDispatch");

    var okBranchStart = forward.IndexOf("case ManagedCreateInvokeResult::Ok:", StringComparison.Ordinal);
    var unavailableBranchStart = forward.IndexOf("case ManagedCreateInvokeResult::Unavailable:", StringComparison.Ordinal);
    Assert.True(okBranchStart >= 0, "ForwardBimDispatch must keep an Ok branch.");
    Assert.True(unavailableBranchStart > okBranchStart, "Unavailable branch must follow Ok branch.");
    var okBranch = forward.Substring(okBranchStart, unavailableBranchStart - okBranchStart);

    Assert.Contains("res.status = statusCode;", okBranch);
    Assert.Contains("res.set_content(responseJson, \"application/json\");", okBranch);
    Assert.Contains("res.set_header(\"X-Rook-Bim-Op\", op);", okBranch);
    Assert.DoesNotContain("nlohmann::json::parse", okBranch);
    Assert.DoesNotContain("data.errorCode", okBranch);
    Assert.DoesNotContain("BuildBim", okBranch);
}
```

- [ ] **Step 4: Update canonical op tests for route string context**

Update the assertion inside `RookServer_RegistersBimRoutesWithCanonicalOps` to require the route string passed into `ForwardBimDispatch`. The current test data uses `Get`/`Post`, so add this helper inside the test class to avoid `GET`/`POST` drift:

```csharp
private static string HttpVerb(string method) =>
    string.Equals(method, "Get", StringComparison.Ordinal) ? "GET" : "POST";
```

Then use:

```csharp
Assert.Contains($"ForwardBimDispatch(req, res, \"{HttpVerb(method)} {route}\", \"{op}\"", handler);
```

- [ ] **Step 5: Tighten the native forbidden-reference guard**

Replace `NativeBimSources_DoNotExposeForbiddenRoutesOrReferences` with this precise guard. Plain `bim.rhino_inside_revit` or user-facing BIM/Revit strings are allowed; direct native/Revit API coupling is not.

```csharp
[Fact]
public void NativeBimSources_DoNotExposeForbiddenRoutesOrApiReferences()
{
    var source = ReadSourceFile("src", "RookNative", "RookServer.cpp");
    source += ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.h");
    source += ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

    Assert.DoesNotContain("/revit", source, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("/rhino/bim", source, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("/rookbim", source, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("Autodesk.", source, StringComparison.Ordinal);
    Assert.DoesNotContain("RevitAPI", source, StringComparison.Ordinal);
    Assert.DoesNotContain("RhinoInside.Revit", source, StringComparison.Ordinal);
}
```

- [ ] **Step 6: Run tests and verify they fail for missing implementation**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeBimDispatchSourceTests"
```

Expected:

```text
Failed: BimDispatchCallbackUnavailableDiagnostic_UsesReviewedCatalogMetadata
Failed: RookServer_BimUnavailableBranchAddsDiagnosticAndPreservesLegacyTransport
Failed or updated: RookServer_RegistersBimRoutesWithCanonicalOps
```

- [ ] **Step 7: Commit failing native source guards**

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs
git commit -m "test: guard phase 2c native bim diagnostics"
```

---

### Task 2: Native BIM Callback-Unavailable Diagnostic

**Files:**
- Modify: `src/RookNative/Infrastructure/RouteDiagnostics.h`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`

- [ ] **Step 1: Add native BIM diagnostic helper**

Add this helper to `RouteDiagnostics.h` after `BuildBlockMutationManagedProxyForwardFailed`.

```cpp
inline nlohmann::json BuildBimDispatchCallbackUnavailable(
    const std::string& route,
    const std::string& operation)
{
    RouteDiagnostic diagnostic;
    diagnostic.domainId = "bim.rhino_inside_revit";
    diagnostic.route = route;
    diagnostic.operation = operation;
    diagnostic.reasonCode = "bim_dispatch_callback_unavailable";
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
```

- [ ] **Step 2: Make BIM error sender diagnostic-aware**

Replace the `SendBimDispatchError` signature and body in `GrasshopperProxyHandler.cpp` with this version.

```cpp
void SendBimDispatchError(
    httplib::Response& res,
    const std::string& op,
    int status,
    const std::string& errorCode,
    const std::string& message,
    const nlohmann::json* diagnostic = nullptr)
{
    nlohmann::json envelope;
    nlohmann::json data;
    data["errorCode"] = errorCode;
    data["message"] = message;
    envelope["success"] = false;
    envelope["data"] = data;
    if (diagnostic != nullptr)
    {
        envelope["diagnostic"] = *diagnostic;
    }

    res.status = status;
    res.set_content(envelope.dump(), "application/json");
    res.set_header("X-Rook-Bim-Op", op);
}
```

- [ ] **Step 3: Thread route context through `ForwardBimDispatch`**

Change the `ForwardBimDispatch` signature from:

```cpp
void ForwardBimDispatch(
    const httplib::Request& /*req*/,
    httplib::Response& res,
    const std::string& op,
    nlohmann::json body)
```

to:

```cpp
void ForwardBimDispatch(
    const httplib::Request& /*req*/,
    httplib::Response& res,
    const std::string& route,
    const std::string& op,
    nlohmann::json body)
```

In the `ManagedCreateInvokeResult::Unavailable` branch, replace the existing call with:

```cpp
{
    const auto diagnostic = Rook::Diagnostics::BuildBimDispatchCallbackUnavailable(route, op);
    SendBimDispatchError(
        res,
        op,
        503,
        "rookbim_unavailable",
        error.empty() ? "BIM dispatch callback is not registered." : error,
        &diagnostic);
    return;
}
```

Leave the `Ok` branch as:

```cpp
case ManagedCreateInvokeResult::Ok:
    res.status = statusCode;
    res.set_content(responseJson, "application/json");
    res.set_header("X-Rook-Bim-Op", op);
    return;
```

Leave the `Failed` branch as:

```cpp
case ManagedCreateInvokeResult::Failed:
default:
    SendBimDispatchError(
        res,
        op,
        500,
        "internal_error",
        error.empty() ? "BIM dispatch failed." : error);
    return;
```

- [ ] **Step 4: Update all BIM handlers with explicit route context**

Update each BIM handler in `GrasshopperProxyHandler.cpp`:

```cpp
void HandleBimStatus(const httplib::Request& req, httplib::Response& res)
{
    ForwardBimDispatch(req, res, "GET /bim/status", "status", nlohmann::json::object());
}

void HandleBimActiveDocument(const httplib::Request& req, httplib::Response& res)
{
    ForwardBimDispatch(req, res, "GET /bim/active-document", "active_document", nlohmann::json::object());
}

void HandleBimCategories(const httplib::Request& req, httplib::Response& res)
{
    ForwardBimDispatch(req, res, "GET /bim/categories", "list_categories", nlohmann::json::object());
}

void HandleBimQueryElements(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (!ParseBimPostBody(req, res, "query_elements", body))
        return;
    ForwardBimDispatch(req, res, "POST /bim/query-elements", "query_elements", std::move(body));
}

void HandleBimElementInfo(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (!ParseBimPostBody(req, res, "element_info", body))
        return;
    ForwardBimDispatch(req, res, "POST /bim/element-info", "element_info", std::move(body));
}

void HandleBimElementParameters(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (!ParseBimPostBody(req, res, "element_parameters", body))
        return;
    ForwardBimDispatch(req, res, "POST /bim/element-parameters", "element_parameters", std::move(body));
}

void HandleBimSelectElements(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (!ParseBimPostBody(req, res, "select_elements", body))
        return;
    ForwardBimDispatch(req, res, "POST /bim/select-elements", "select_elements", std::move(body));
}

void HandleBimClearSelection(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body;
    if (!ParseBimPostBody(req, res, "clear_selection", body))
        return;
    ForwardBimDispatch(req, res, "POST /bim/clear-selection", "clear_selection", std::move(body));
}
```

- [ ] **Step 5: Run native source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeBimDispatchSourceTests"
```

Expected:

```text
Passed
```

- [ ] **Step 6: Commit native Phase 2C adoption**

```powershell
git add src/RookNative/Infrastructure/RouteDiagnostics.h src/RookNative/Handlers/GrasshopperProxyHandler.cpp
git commit -m "feat: add native bim dispatch diagnostic"
```

---

### Task 3: Managed BIM Diagnostic Serialization Guards

**Files:**
- Modify: `src/Rook.Tests/Handlers/BimHandlerTests.cs`

- [ ] **Step 1: Add source guard for optional `ApiResponse.Diagnostic`**

Add this test after `NativeRegistrar_SourceDeclaresBimDispatchCallback`.

```csharp
[Fact]
public void ApiResponse_DiagnosticIsOptionalAndBridgeStatusIgnoresIt()
{
    var apiResponse = ReadSourceFile("src", "Rook", "ApiResponse.cs");
    var registrar = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
    var mapBridgeStatus = ExtractFunction(registrar, "MapBridgeStatus");

    Assert.Contains("public object? Diagnostic { get; set; }", apiResponse);
    Assert.Contains("public int? HttpStatus { get; set; }", apiResponse);
    Assert.DoesNotContain("Diagnostic", mapBridgeStatus);
    Assert.Contains("result.HttpStatus ?? (result.Success ? 200 : 400)", mapBridgeStatus);
}
```

- [ ] **Step 2: Add source guard for BIM-only diagnostic serialization**

Add this test after `ApiResponse_DiagnosticIsOptionalAndBridgeStatusIgnoresIt`.

```csharp
[Fact]
public void ManagedBridge_OnlyBimDispatchSerializesApiResponseDiagnostic()
{
    var source = ReadSourceFile("src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs");
    var bim = ExtractFunction(source, "ExecuteBimDispatchCallback");
    var api = ExtractFunction(source, "ExecuteApiResponseCallback");
    var async = ExtractFunction(source, "ExecuteAsyncApiResponseCallback");
    var offUi = ExtractFunction(source, "ExecuteOffUiApiResponseCallback");

    Assert.Contains("SerializeBimDispatchEnvelope(result)", bim);
    Assert.Contains("\"diagnostic\"", ExtractFunction(source, "SerializeBimDispatchEnvelope"));
    Assert.DoesNotContain("Diagnostic", api);
    Assert.DoesNotContain("Diagnostic", async);
    Assert.DoesNotContain("Diagnostic", offUi);
    Assert.DoesNotContain("\"diagnostic\"", api);
    Assert.DoesNotContain("\"diagnostic\"", async);
    Assert.DoesNotContain("\"diagnostic\"", offUi);
}
```

- [ ] **Step 3: Add extractor overload if the test file lacks it**

`BimHandlerTests` currently has `ReadSourceFile` but no `ExtractFunction`. Add this helper before `ReadSourceFile`.

```csharp
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
```

- [ ] **Step 4: Run tests and verify they fail for missing implementation**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~BimHandlerTests
```

Expected:

```text
Failed: ApiResponse_DiagnosticIsOptionalAndBridgeStatusIgnoresIt
Failed: ManagedBridge_OnlyBimDispatchSerializesApiResponseDiagnostic
```

- [ ] **Step 5: Commit failing managed serialization guards**

```powershell
git add src/Rook.Tests/Handlers/BimHandlerTests.cs
git commit -m "test: guard bim-only diagnostic serialization"
```

---

### Task 4: Managed BIM Diagnostic Serialization Implementation

**Files:**
- Modify: `src/Rook/ApiResponse.cs`
- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`

- [ ] **Step 1: Add optional diagnostic to `ApiResponse`**

Add this property after `Data` in `ApiResponse.cs`.

```csharp
public object? Diagnostic { get; set; }
```

Keep `HttpStatus` unchanged.

- [ ] **Step 2: Add `JsonNode` import to the registrar**

Add this using to `NativeGhBridgeRegistrar.cs`.

```csharp
using System.Text.Json.Nodes;
```

- [ ] **Step 3: Replace BIM dispatch envelope serialization**

In `ExecuteBimDispatchCallback`, replace:

```csharp
var responseJson = JsonSerializer.Serialize(new
{
    success = result.Success,
    data = result.Data,
}, JsonOptions);
```

with:

```csharp
var responseJson = SerializeBimDispatchEnvelope(result);
```

- [ ] **Step 4: Add BIM-only envelope helpers**

Add these helpers after `ExecuteBimDispatchCallback` and before `MapBridgeStatus`.

```csharp
private static string SerializeBimDispatchEnvelope(ApiResponse result)
{
    var envelope = new JsonObject
    {
        ["success"] = result.Success,
        ["data"] = CloneToJsonNode(result.Data),
    };

    if (result.Diagnostic != null)
    {
        envelope["diagnostic"] = CloneToJsonNode(result.Diagnostic);
    }

    return envelope.ToJsonString(JsonOptions);
}

private static JsonNode? CloneToJsonNode(object? value)
{
    if (value == null)
    {
        return null;
    }

    if (value is JsonNode node)
    {
        return JsonNode.Parse(node.ToJsonString(JsonOptions));
    }

    return JsonSerializer.SerializeToNode(value, JsonOptions);
}
```

- [ ] **Step 5: Run managed serialization tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~BimHandlerTests
```

Expected:

```text
Passed for serialization guards
Remaining failures may exist only from Task 5 tests if already added
```

- [ ] **Step 6: Commit managed serialization implementation**

```powershell
git add src/Rook/ApiResponse.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs
git commit -m "feat: serialize bim route diagnostics"
```

---

### Task 5: Managed BIM Diagnostic Mapping Tests

**Files:**
- Modify: `src/Rook.Tests/Handlers/BimHandlerTests.cs`

- [ ] **Step 1: Add test helper for diagnostics**

Add these helpers near `ToJsonElement`.

```csharp
private static JsonElement Diagnostic(ApiResponse response)
{
    Assert.NotNull(response.Diagnostic);
    return ToJsonElement(response.Diagnostic);
}

private static void AssertDiagnostic(
    ApiResponse response,
    string reasonCode,
    string failureKind,
    string ownedBy,
    string evidenceSource,
    string emittedBy,
    string operation)
{
    var diagnostic = Diagnostic(response);
    Assert.Equal(1, diagnostic.GetProperty("schemaVersion").GetInt32());
    Assert.Equal("bim.rhino_inside_revit", diagnostic.GetProperty("domainId").GetString());
    Assert.Equal(reasonCode, diagnostic.GetProperty("reasonCode").GetString());
    Assert.Equal(failureKind, diagnostic.GetProperty("failureKind").GetString());
    Assert.Equal(ownedBy, diagnostic.GetProperty("ownedBy").GetString());
    Assert.Equal(evidenceSource, diagnostic.GetProperty("evidenceSource").GetString());
    Assert.Equal(emittedBy, diagnostic.GetProperty("emittedBy").GetString());
    Assert.Equal(operation, diagnostic.GetProperty("operation").GetString());
    Assert.Equal("/capabilities", diagnostic.GetProperty("diagnosticRoute").GetProperty("path").GetString());
    Assert.Equal("bim.rhino_inside_revit", diagnostic.GetProperty("diagnosticRoute").GetProperty("domainId").GetString());
    Assert.False(diagnostic.TryGetProperty("state", out _));
}
```

- [ ] **Step 2: Add status diagnostic test for `not_rhino_inside`**

Add this test after `Dispatch_Status_ReturnsStructuredUnavailableRuntime`.

`/bim/status` is a status-reporting route, so it may return `success: true`
while carrying a readiness diagnostic that describes the reported BIM state.
This is the only Phase 2C success-with-failure-diagnostic exception.
Non-status successful BIM operations must not emit failure diagnostics.

```csharp
[Fact]
public void Dispatch_Status_AddsNotRhinoInsideDiagnosticFromRuntimeStatus()
{
    RookBimRuntimeRegistry.Install(
        new StatusRuntime("not_rhino_inside", "RookBIM requires RhinoInside.Revit and RevitAPIUI to be loaded."),
        "RookBim.dll");

    try
    {
        var handler = new BimHandler();
        var response = handler.Dispatch("{\"op\":\"status\"}");
        var data = ToJsonElement(response.Data);

        Assert.Equal(200, response.HttpStatus);
        Assert.True(response.Success);
        Assert.Equal("not_rhino_inside", data.GetProperty("errorCode").GetString());
        AssertDiagnostic(
            response,
            "not_rhino_inside",
            "host_blocked",
            "rookbim",
            "rookbim_host_runtime",
            "managed_route",
            "status");
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}
```

- [ ] **Step 2a: Add guard that non-status successes do not emit diagnostics**

Add this test after `Dispatch_Status_AddsNotRhinoInsideDiagnosticFromRuntimeStatus`.

```csharp
[Fact]
public void Dispatch_NonStatusSuccessDoesNotEmitFailureDiagnostic()
{
    RookBimRuntimeRegistry.Install(new DetailFailureRuntime(), "test-list-categories");
    try
    {
        var handler = new BimHandler();
        var response = handler.Dispatch("{\"op\":\"list_categories\"}");

        Assert.True(response.Success);
        Assert.Null(response.Diagnostic);
        Assert.Contains("document_category_table", ((JsonNode)response.Data!).ToJsonString());
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}
```

- [ ] **Step 3: Add module-source diagnostic tests**

Add this theory after the `not_rhino_inside` test.

```csharp
[Theory]
[InlineData("module-not-found", "rookbim_module_not_found", "dependency_unavailable", "managed_rookbim_module_loader", true)]
[InlineData("module-load-failed", "rookbim_module_load_failed", "dependency_degraded", "managed_rookbim_module_loader", true)]
public void Dispatch_DocumentOperation_AddsModuleReadinessDiagnosticsFromRegistrySource(
    string source,
    string reasonCode,
    string failureKind,
    string evidenceSource,
    bool userActionRequired)
{
    RookBimRuntimeRegistry.Install(
        new RookBimUnavailableRuntime(
            "rookbim_unavailable",
            "Configured unavailable runtime message.",
            "module-loader"),
        source);

    try
    {
        var handler = new BimHandler();
        var response = handler.Dispatch("{\"op\":\"active_document\"}");
        var data = ToJsonElement(response.Data);
        var diagnostic = Diagnostic(response);

        Assert.Equal(503, response.HttpStatus);
        Assert.False(response.Success);
        Assert.Equal("rookbim_unavailable", data.GetProperty("errorCode").GetString());
        Assert.Equal(reasonCode, diagnostic.GetProperty("reasonCode").GetString());
        Assert.Equal(failureKind, diagnostic.GetProperty("failureKind").GetString());
        Assert.Equal("managed", diagnostic.GetProperty("ownedBy").GetString());
        Assert.Equal(evidenceSource, diagnostic.GetProperty("evidenceSource").GetString());
        Assert.Equal("managed_route", diagnostic.GetProperty("emittedBy").GetString());
        Assert.Equal(userActionRequired, diagnostic.GetProperty("userActionRequired").GetBoolean());
        Assert.Equal("active_document", diagnostic.GetProperty("operation").GetString());
        Assert.False(diagnostic.TryGetProperty("state", out _));
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}
```

Do not add a route-level `core-fallback` test through `BimHandler.Dispatch`. `Dispatch` calls `RookBimModuleLoader.TryActivate()`, so `core-fallback` can legitimately transition before the response is produced. Task 7 adds a source guard proving the `core-fallback` mapping exists in `DiagnosticReasonFromRegistrySource`.

- [ ] **Step 4: Add runtime active-document diagnostic test**

Add this test after the module-source diagnostic theory.

```csharp
[Fact]
public void Dispatch_DocumentOperation_AddsNoActiveDocumentDiagnosticFromRuntimeResponse()
{
    RookBimRuntimeRegistry.Install(new NoActiveDocumentRuntime(), "RookBim.dll");

    try
    {
        var handler = new BimHandler();
        var response = handler.Dispatch("{\"op\":\"active_document\"}");
        var data = ToJsonElement(response.Data);

        Assert.Equal(409, response.HttpStatus);
        Assert.False(response.Success);
        Assert.Equal("no_active_document", data.GetProperty("errorCode").GetString());
        AssertDiagnostic(
            response,
            "no_active_document",
            "operation_unavailable",
            "rookbim",
            "rookbim_revit_runtime",
            "managed_route",
            "active_document");
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}
```

- [ ] **Step 5: Add no-diagnostic tests for excluded errors**

Add this test after the existing category failure test.

```csharp
[Fact]
public void Dispatch_ValidationAndOperationTaxonomyErrorsDoNotEmitPhase2CDiagnostics()
{
    var handler = new BimHandler();

    var unknownOp = handler.Dispatch("{\"op\":\"write_wall\"}");
    Assert.Null(unknownOp.Diagnostic);
    Assert.Equal("invalid_scope", ToJsonElement(unknownOp.Data).GetProperty("errorCode").GetString());

    var malformed = handler.Dispatch("{");
    Assert.Null(malformed.Diagnostic);
    Assert.Equal("invalid_scope", ToJsonElement(malformed.Data).GetProperty("errorCode").GetString());

    var unbounded = handler.Dispatch(
        "{\"op\":\"query_elements\",\"scope\":\"document\",\"filters\":[{\"parameter\":\"Fire Rating\",\"operation\":\"not_equals\",\"value\":\"2HR\"}]}");
    Assert.Null(unbounded.Diagnostic);
    Assert.Equal("unbounded_document_query", ToJsonElement(unbounded.Data).GetProperty("errorCode").GetString());

    RookBimRuntimeRegistry.Install(new CategoryFailureRuntime(), "test-category-failure");
    try
    {
        var invalidCategory = handler.Dispatch("{\"op\":\"query_elements\",\"scope\":\"document\",\"category\":\"Pipe Accessoryz\"}");
        Assert.Null(invalidCategory.Diagnostic);
        Assert.Equal("invalid_category", ToJsonElement(invalidCategory.Data).GetProperty("errorCode").GetString());
    }
    finally
    {
        RookBimRuntimeRegistry.ResetForTests();
    }
}
```

- [ ] **Step 6: Add test runtimes**

Add these private runtime classes near the existing private runtimes.

```csharp
private sealed class StatusRuntime : IRookBimRuntime
{
    private readonly string errorCode;
    private readonly string message;

    public StatusRuntime(string errorCode, string message)
    {
        this.errorCode = errorCode;
        this.message = message;
    }

    public BimStatusResponse Status()
    {
        return new BimStatusResponse
        {
            Available = false,
            Runtime = "rookbim",
            ErrorCode = errorCode,
            Message = message,
            Host = "unknown",
            Module = "RookBim.dll"
        };
    }

    public BimApiResponse ActiveDocument() => BimApiResponse.Ok(null);
    public BimApiResponse ListCategories() => BimApiResponse.Ok(null);
    public BimApiResponse QueryElements(BimQueryElementsRequest request) => BimApiResponse.Ok(null);
    public BimApiResponse ElementInfo(BimElementRequest request) => BimApiResponse.Ok(null);
    public BimApiResponse ElementParameters(BimElementRequest request) => BimApiResponse.Ok(null);
    public BimApiResponse SelectElements(BimSelectElementsRequest request) => BimApiResponse.Ok(null);
    public BimApiResponse ClearSelection() => BimApiResponse.Ok(null);
}

private sealed class NoActiveDocumentRuntime : IRookBimRuntime
{
    public BimStatusResponse Status()
    {
        return new BimStatusResponse
        {
            Available = false,
            Runtime = "rookbim",
            ErrorCode = "no_active_document",
            Message = "RookBIM is connected to Revit, but no active document is open.",
            Host = "revit",
            Module = "RookBim.dll"
        };
    }

    public BimApiResponse ActiveDocument()
    {
        return BimApiResponse.Fail(
            BimErrorCode.NoActiveDocument,
            "No active Revit document is open.",
            409);
    }

    public BimApiResponse ListCategories() => ActiveDocument();
    public BimApiResponse QueryElements(BimQueryElementsRequest request) => ActiveDocument();
    public BimApiResponse ElementInfo(BimElementRequest request) => ActiveDocument();
    public BimApiResponse ElementParameters(BimElementRequest request) => ActiveDocument();
    public BimApiResponse SelectElements(BimSelectElementsRequest request) => ActiveDocument();
    public BimApiResponse ClearSelection() => ActiveDocument();
}
```

- [ ] **Step 7: Run tests and verify they fail for missing mapping**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~BimHandlerTests
```

Expected:

```text
Failed: Dispatch_Status_AddsNotRhinoInsideDiagnosticFromRuntimeStatus
Failed: Dispatch_DocumentOperation_AddsModuleReadinessDiagnosticsFromRegistrySource
Failed: Dispatch_DocumentOperation_AddsNoActiveDocumentDiagnosticFromRuntimeResponse
```

- [ ] **Step 8: Commit failing managed mapping tests**

```powershell
git add src/Rook.Tests/Handlers/BimHandlerTests.cs
git commit -m "test: guard managed bim readiness diagnostics"
```

---

### Task 6: Managed BIM Diagnostic Mapping Implementation

**Files:**
- Modify: `src/Rook/Handlers/BimHandler.cs`

- [ ] **Step 1: Add route map helper**

Add these helpers near `GetStringArg`.

```csharp
private static string RouteForOp(string op)
{
    return op switch
    {
        "status" => "GET /bim/status",
        "active_document" => "GET /bim/active-document",
        "list_categories" => "GET /bim/categories",
        "query_elements" => "POST /bim/query-elements",
        "element_info" => "POST /bim/element-info",
        "element_parameters" => "POST /bim/element-parameters",
        "select_elements" => "POST /bim/select-elements",
        "clear_selection" => "POST /bim/clear-selection",
        _ => "POST /bim"
    };
}

private static JsonObject DiagnosticRoute()
{
    return new JsonObject
    {
        ["method"] = "GET",
        ["path"] = "/capabilities",
        ["domainId"] = "bim.rhino_inside_revit",
    };
}
```

- [ ] **Step 2: Add diagnostic builder**

Add this helper after `RouteForOp`.

```csharp
private static JsonObject? BuildDiagnosticForReason(string op, string? reasonCode)
{
    if (string.IsNullOrWhiteSpace(reasonCode))
    {
        return null;
    }

    string failureKind;
    string ownedBy;
    string evidenceSource;
    bool retryable;
    bool userActionRequired;
    string recommendedNextStep;

    switch (reasonCode)
    {
        case "not_rhino_inside":
            failureKind = "host_blocked";
            ownedBy = "rookbim";
            evidenceSource = "rookbim_host_runtime";
            retryable = false;
            userActionRequired = true;
            recommendedNextStep = "Open Rhino through Rhino.Inside.Revit, then retry.";
            break;

        case "rookbim_runtime_not_activated":
            failureKind = "dependency_unavailable";
            ownedBy = "managed";
            evidenceSource = "managed_rookbim_runtime_registry";
            retryable = true;
            userActionRequired = false;
            recommendedNextStep = "Wait for RookBIM runtime activation, then retry.";
            break;

        case "rookbim_module_not_found":
            failureKind = "dependency_unavailable";
            ownedBy = "managed";
            evidenceSource = "managed_rookbim_module_loader";
            retryable = false;
            userActionRequired = true;
            recommendedNextStep = "Verify the RookBIM module payload is present, then restart Rhino.";
            break;

        case "rookbim_module_load_failed":
            failureKind = "dependency_degraded";
            ownedBy = "managed";
            evidenceSource = "managed_rookbim_module_loader";
            retryable = true;
            userActionRequired = true;
            recommendedNextStep = "Inspect RookBIM module load diagnostics, then restart Rhino.";
            break;

        case "no_active_document":
            failureKind = "operation_unavailable";
            ownedBy = "rookbim";
            evidenceSource = "rookbim_revit_runtime";
            retryable = true;
            userActionRequired = true;
            recommendedNextStep = "Open an active Revit document, then retry.";
            break;

        default:
            return null;
    }

    return new JsonObject
    {
        ["schemaVersion"] = 1,
        ["domainId"] = "bim.rhino_inside_revit",
        ["route"] = RouteForOp(op),
        ["operation"] = op,
        ["reasonCode"] = reasonCode,
        ["failureKind"] = failureKind,
        ["retryable"] = retryable,
        ["userActionRequired"] = userActionRequired,
        ["diagnosticRoute"] = DiagnosticRoute(),
        ["recommendedNextStep"] = recommendedNextStep,
        ["ownedBy"] = ownedBy,
        ["evidenceSource"] = evidenceSource,
        ["emittedBy"] = "managed_route",
    };
}
```

- [ ] **Step 3: Add registry-source reason helper**

Add this helper after `BuildDiagnosticForReason`.

```csharp
private static string? DiagnosticReasonFromRegistrySource()
{
    return RookBimRuntimeRegistry.Source switch
    {
        "core-fallback" => "rookbim_runtime_not_activated",
        "module-not-found" => "rookbim_module_not_found",
        "module-load-failed" => "rookbim_module_load_failed",
        _ => null
    };
}
```

- [ ] **Step 4: Update status dispatch to attach status diagnostics**

In the `op switch`, replace:

```csharp
"status" => Ok(runtime.Status()),
```

with:

```csharp
"status" => DispatchStatus(runtime),
```

Add this helper near `DispatchQueryElements`.

```csharp
private static ApiResponse DispatchStatus(IRookBimRuntime runtime)
{
    var status = runtime.Status();
    var reasonCode = status.ErrorCode;
    if (string.Equals(reasonCode, "rookbim_unavailable", StringComparison.Ordinal))
    {
        reasonCode = DiagnosticReasonFromRegistrySource();
    }

    return Ok(status, BuildDiagnosticForReason("status", reasonCode));
}
```

- [ ] **Step 5: Pass op into `FromBimResponse`**

Change all non-status switch arms from:

```csharp
"active_document" => FromBimResponse(runtime.ActiveDocument()),
"list_categories" => FromBimResponse(runtime.ListCategories()),
```

to:

```csharp
"active_document" => FromBimResponse("active_document", runtime.ActiveDocument()),
"list_categories" => FromBimResponse("list_categories", runtime.ListCategories()),
```

Update the remaining arms:

```csharp
"query_elements" => DispatchQueryElements(runtime, body),
"element_info" => FromBimResponse(
    "element_info",
    runtime.ElementInfo(DeserializeRequest<BimElementRequest>(body))),
"element_parameters" => FromBimResponse(
    "element_parameters",
    runtime.ElementParameters(DeserializeRequest<BimElementRequest>(body))),
"select_elements" => FromBimResponse(
    "select_elements",
    runtime.SelectElements(DeserializeRequest<BimSelectElementsRequest>(body))),
"clear_selection" => FromBimResponse("clear_selection", runtime.ClearSelection()),
```

Change `DispatchQueryElements` to:

```csharp
private static ApiResponse DispatchQueryElements(IRookBimRuntime runtime, string? body)
{
    var request = DeserializeRequest<BimQueryElementsRequest>(body);
    var validation = request.Validate();
    if (!validation.Success)
    {
        return Fail(
            validation.ErrorCode,
            validation.Message ?? "BIM query validation failed.",
            400);
    }

    return FromBimResponse("query_elements", runtime.QueryElements(request));
}
```

- [ ] **Step 6: Update `FromBimResponse`, `Ok`, and `Fail`**

Replace `FromBimResponse` with:

```csharp
private static ApiResponse FromBimResponse(string op, BimApiResponse response)
{
    if (response.Success)
    {
        return new ApiResponse
        {
            Success = true,
            Data = ToWireData(response.Data),
            HttpStatus = response.HttpStatus,
        };
    }

    var reasonCode = MapErrorCode(response.ErrorCode);
    if (string.Equals(reasonCode, "rookbim_unavailable", StringComparison.Ordinal))
    {
        reasonCode = DiagnosticReasonFromRegistrySource();
    }

    return Fail(
        response.ErrorCode,
        response.Message ?? "BIM operation failed.",
        response.HttpStatus,
        response.Data,
        BuildDiagnosticForReason(op, reasonCode));
}
```

Replace `Ok` with:

```csharp
private static ApiResponse Ok(object? data, object? diagnostic = null)
{
    return new ApiResponse
    {
        Success = true,
        Data = ToWireData(data),
        Diagnostic = diagnostic,
        HttpStatus = 200,
    };
}
```

Change the `Fail` signature to:

```csharp
private static ApiResponse Fail(
    BimErrorCode code,
    string message,
    int httpStatus,
    object? details = null,
    object? diagnostic = null)
```

Set `Diagnostic` in the returned response:

```csharp
return new ApiResponse
{
    Success = false,
    Data = data,
    Diagnostic = diagnostic,
    HttpStatus = httpStatus,
};
```

- [ ] **Step 7: Run managed BIM tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter FullyQualifiedName~BimHandlerTests
```

Expected:

```text
Passed
```

- [ ] **Step 8: Commit managed BIM diagnostic mapping**

```powershell
git add src/Rook/Handlers/BimHandler.cs
git commit -m "feat: add managed bim readiness diagnostics"
```

---

### Task 7: Boundary Guards And Focused Validation

**Files:**
- Modify: `src/Rook.Tests/Handlers/BimHandlerTests.cs`
- Modify: `src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs`
- Modify: `src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs`
- Modify: `src/RookBim.Tests/RookBimModuleSourceTests.cs` only if needed for precise isolation wording

- [ ] **Step 1: Tighten `src/Rook` Revit boundary source guard if needed**

If existing tests reject plain Revit-facing strings in `src/Rook`, replace that broad check with the precise Phase 2C boundary. Add or update a source test to inspect project references and source imports rather than user-facing text.

Use this pattern in the appropriate BIM boundary test file:

```csharp
[Fact]
public void RookProject_DoesNotReferenceAutodeskOrBindRhinoInsideRevitRuntime()
{
    var project = Read("src/Rook/Rook.csproj");
    var sourceFiles = Directory
        .GetFiles(Path.Combine(RepoRoot, "src", "Rook"), "*.cs", SearchOption.AllDirectories)
        .Where(path =>
        {
            var normalized = path.Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);
            return !normalized.Contains(Path.DirectorySeparatorChar + "obj" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase)
                && !normalized.Contains(Path.DirectorySeparatorChar + "bin" + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase);
        })
        .ToArray();
    var source = string.Join("\n", sourceFiles.Select(File.ReadAllText));

    Assert.DoesNotContain("<Reference Include=\"RevitAPI", project, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("<Reference Include=\"Autodesk.Revit", project, StringComparison.OrdinalIgnoreCase);
    Assert.DoesNotContain("using Autodesk.", source, StringComparison.Ordinal);
    Assert.DoesNotContain("Autodesk.Revit.", source, StringComparison.Ordinal);
    Assert.DoesNotContain("Type.GetType(\"RhinoInside.Revit", source, StringComparison.Ordinal);
    Assert.DoesNotContain("Assembly.Load(\"RhinoInside.Revit", source, StringComparison.Ordinal);
}
```

Keep existing `src/RookBim` tests that require Revit API references to remain isolated there.

- [ ] **Step 2: Add final Phase 2C anti-scope source guard**

Add this test to `RouteDiagnosticsSourceTests`.

```csharp
[Fact]
public void Phase2C_DoesNotIntroduceBroadOrAliasBimDiagnosticReasonCodes()
{
    var header = ReadSourceFile("src", "RookNative", "Infrastructure", "RouteDiagnostics.h");
    var bimHandler = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
    var nativeBim = ExtractFunction(header, "BuildBimDispatchCallbackUnavailable");
    var managedBim = ExtractFunction(bimHandler, "BuildDiagnosticForReason");
    var catalog = nativeBim + managedBim;

    Assert.DoesNotContain("\"rookbim_unavailable\"", catalog);
    Assert.DoesNotContain("\"bim_unavailable\"", catalog);
    Assert.DoesNotContain("\"bridge_unavailable\"", catalog);
    Assert.DoesNotContain("\"managed_dependency_unavailable\"", catalog);
    Assert.DoesNotContain("\"rookbim_module_not_activated\"", catalog);
    Assert.DoesNotContain("\"no_active_revit_document\"", catalog);
    Assert.DoesNotContain("\"missing_revit_api\"", catalog);
}
```

Note: this checks catalog/diagnostic builder source only, not arbitrary legacy
`data.errorCode` text across the repo.

- [ ] **Step 2a: Add positive guard for legacy `rookbim_unavailable` compatibility**

Add this test to `BimHandlerTests`.

```csharp
[Fact]
public void BimHandler_PreservesRookBimUnavailableAsLegacyDataErrorCodeOnly()
{
    var source = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
    var mapErrorCode = ExtractFunction(source, "MapErrorCode");
    var diagnosticBuilder = ExtractFunction(source, "BuildDiagnosticForReason");

    Assert.Contains("\"rookbim_unavailable\"", mapErrorCode);
    Assert.DoesNotContain("\"rookbim_unavailable\"", diagnosticBuilder);
}
```

- [ ] **Step 3: Add source guard for runtime-not-activated mapping**

Add this test to `BimHandlerTests`.

```csharp
[Fact]
public void BimHandler_MapsCoreFallbackRegistrySourceToRuntimeNotActivatedDiagnostic()
{
    var source = ReadSourceFile("src", "Rook", "Handlers", "BimHandler.cs");
    var helper = ExtractFunction(source, "DiagnosticReasonFromRegistrySource");

    Assert.Contains("\"core-fallback\"", helper);
    Assert.Contains("\"rookbim_runtime_not_activated\"", helper);
    Assert.Contains("\"module-not-found\"", helper);
    Assert.Contains("\"rookbim_module_not_found\"", helper);
    Assert.Contains("\"module-load-failed\"", helper);
    Assert.Contains("\"rookbim_module_load_failed\"", helper);
}
```

- [ ] **Step 4: Run focused managed/source suites**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeBimDispatchSourceTests|FullyQualifiedName~BimHandlerTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests|FullyQualifiedName~CompanionRuntimeStatusTests"
```

Expected:

```text
Passed
```

- [ ] **Step 5: Run RookBIM boundary tests**

Run:

```powershell
dotnet test src/RookBim.Tests/RookBim.Tests.csproj --no-restore
```

Expected:

```text
Passed
```

If this command cannot run because Revit reference paths are unavailable on the machine, run the existing source-only boundary tests command used by recent RookBIM work and record the exact limitation in the PR body.

- [ ] **Step 6: Run whitespace and project-file drift checks**

Run:

```powershell
git diff --check origin/main...HEAD
git diff --name-only origin/main...HEAD
```

Expected changed files:

```text
docs/superpowers/plans/2026-06-02-rook-ecosystem-phase-2c-rookbim-diagnostics.md
docs/superpowers/specs/2026-06-02-rook-ecosystem-phase-2c-rookbim-diagnostics-design.md
src/Rook/ApiResponse.cs
src/Rook/Handlers/BimHandler.cs
src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs
src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs
src/Rook.Tests/Handlers/BimHandlerTests.cs
src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs
src/RookBim.Tests/RookBimModuleSourceTests.cs
src/RookNative/Handlers/GrasshopperProxyHandler.cpp
src/RookNative/Infrastructure/RouteDiagnostics.h
```

If `src/RookBim.Tests/RookBimModuleSourceTests.cs` was not needed, it must not appear in the changed-file list.

The changed-file list must not include:

```text
src/RookNative/RookNative.vcxproj
src/RookNative/RookNative.vcxproj.filters
installer/
mcp_server/
```

- [ ] **Step 7: Native build validation**

Run:

```powershell
cmd /c "call ""C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"" x64 -vcvars_ver=14.44 && msbuild src\RookNative\RookNative.vcxproj /t:Build /p:Configuration=Debug /p:Platform=x64 /p:VCToolsVersion=14.44.35207"
```

Expected:

```text
Build succeeded.
0 errors
```

- [ ] **Step 8: Commit validation guard updates**

```powershell
git add src/Rook.Tests/Diagnostics/RouteDiagnosticsSourceTests.cs src/Rook.Tests/Handlers/BimHandlerTests.cs src/Rook.Tests/Handlers/NativeBimDispatchSourceTests.cs src/RookBim.Tests/RookBimModuleSourceTests.cs
git commit -m "test: guard phase 2c bim boundaries"
```

If `src/RookBim.Tests/RookBimModuleSourceTests.cs` was not changed, omit it from `git add`.

---

### Task 8: Local Deploy And Live Standalone Rhino Smoke

**Files:**
- No source changes expected.

- [ ] **Step 1: Deploy locally after native build**

Use the deploy-local-testing skill or run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -SkipBuild
```

Expected:

```text
RookNative.rhp copied to the Rhino 8 Plug-ins RookNative folder
managed companion payload copied/preserved
RookBim.dll copied/preserved where the companion can load it
```

- [ ] **Step 2: Ask user to open standalone Rhino**

Rhino should be standalone Rhino, not Rhino.Inside/Revit, for the required live gate. The managed callback should be allowed to register normally.

- [ ] **Step 3: Discover active native port**

Run:

```powershell
$native = Get-ChildItem "$env:LOCALAPPDATA\Rook\discovery" -Filter "instance-*-native.json" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1 |
  Get-Content -Raw |
  ConvertFrom-Json
$port = [int]$native.port
$base = "http://127.0.0.1:$port"
$base
```

Expected:

```text
http://127.0.0.1:<active-port>
```

- [ ] **Step 4: Verify ping and capabilities**

Run:

```powershell
$ping = Invoke-RestMethod "$base/ping"
$caps = Invoke-RestMethod "$base/capabilities"
$bim = $caps.domains | Where-Object { $_.domainId -eq "bim.rhino_inside_revit" }
[pscustomobject]@{
  Ping = $ping.data
  SchemaVersion = $caps.schemaVersion
  DomainCount = ($caps.domains | Measure-Object).Count
  BimState = $bim.state
  BimReason = $bim.reasonCode
  BimRoutes = ($bim.routes -join ", ")
} | ConvertTo-Json -Depth 4
```

Expected when the managed callback has registered in standalone Rhino:

```text
Ping: pong
SchemaVersion: 1
DomainCount: 13
BimState: blocked_by_host
BimReason: not_rhino_inside
```

If `BimState` is `not_loaded`, wait for companion startup to settle and retry. Do not type Rook commands unless diagnosing callback registration.

- [ ] **Step 5: Verify `/bim/status` diagnostic**

Run:

```powershell
$response = Invoke-WebRequest "$base/bim/status" -Method GET -SkipHttpErrorCheck
$body = $response.Content | ConvertFrom-Json
[pscustomobject]@{
  Status = [int]$response.StatusCode
  Header = ($response.Headers["X-Rook-Bim-Op"] -join ",")
  Success = $body.success
  DataErrorCode = $body.data.errorCode
  DiagnosticReason = $body.diagnostic.reasonCode
  DiagnosticDomain = $body.diagnostic.domainId
  DiagnosticFailureKind = $body.diagnostic.failureKind
  DiagnosticOwnedBy = $body.diagnostic.ownedBy
  DiagnosticEmittedBy = $body.diagnostic.emittedBy
} | ConvertTo-Json -Depth 5
```

Expected:

```text
Status: 200
Header: status
Success: true
DataErrorCode: not_rhino_inside
DiagnosticReason: not_rhino_inside
DiagnosticDomain: bim.rhino_inside_revit
DiagnosticFailureKind: host_blocked
DiagnosticOwnedBy: rookbim
DiagnosticEmittedBy: managed_route
```

This success-with-diagnostic shape is allowed only for `/bim/status` because it
is a status-reporting route. Non-status successful BIM operations must not emit
failure diagnostics.

- [ ] **Step 6: Verify parse failure stays legacy/local**

Run:

```powershell
$response = Invoke-WebRequest "$base/bim/query-elements" -Method POST -Body "{" -ContentType "application/json" -SkipHttpErrorCheck
$body = $response.Content | ConvertFrom-Json
[pscustomobject]@{
  Status = [int]$response.StatusCode
  Header = ($response.Headers["X-Rook-Bim-Op"] -join ",")
  Success = $body.success
  DataErrorCode = $body.data.errorCode
  HasDiagnostic = $body.PSObject.Properties.Name -contains "diagnostic"
} | ConvertTo-Json -Depth 4
```

Expected:

```text
Status: 400
Header: query_elements
Success: false
DataErrorCode: invalid_scope
HasDiagnostic: false
```

- [ ] **Step 7: Record Rhino.Inside/Revit validation status**

If Rhino.Inside/Revit is available, run `/bim/status` inside a Revit-hosted Rhino session and record whether active document success has no failure diagnostic or no-active-document produces `no_active_document`.

If Rhino.Inside/Revit is not available, record:

```text
Rhino.Inside/Revit live validation not run in this PR. Standalone Rhino not_rhino_inside live gate passed; Revit-hosted validation remains a later confidence gate per the Phase 2C design.
```

- [ ] **Step 8: Commit nothing**

This task should not modify source files. If local deploy or live smoke creates generated artifacts in the repo, remove only generated artifacts produced by this task and preserve user files.

---

### Task 9: PR Readiness Checklist

**Files:**
- No source changes expected unless a validation finding requires a reviewed fix.

- [ ] **Step 1: Final automated checks**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --no-restore --filter "FullyQualifiedName~RouteDiagnosticsSourceTests|FullyQualifiedName~NativeBimDispatchSourceTests|FullyQualifiedName~BimHandlerTests|FullyQualifiedName~ManagedCapabilityDomainStatusTests|FullyQualifiedName~CompanionRuntimeStatusTests"
git diff --check origin/main...HEAD
git status --short --branch
```

Expected:

```text
All selected tests passed
git diff --check has no output
worktree clean
```

- [ ] **Step 2: Confirm branch diff scope**

Run:

```powershell
git diff --name-only origin/main...HEAD
```

Expected:

```text
Only Phase 2C docs/plans, BIM diagnostics source/tests, ApiResponse, NativeGhBridgeRegistrar, and native BIM diagnostics files changed.
No installer, MCP behavior, route registration, project-file, or loading-policy files changed.
```

- [ ] **Step 3: Prepare PR body evidence**

The PR body must include:

```text
Scope:
- Phase 2C RookBIM diagnostics only.
- Native emits only bim_dispatch_callback_unavailable.
- Managed emits only reviewed RookBIM readiness diagnostics.
- rookbim_unavailable remains legacy data.errorCode only.
- Native successful callback dispatch remains opaque pass-through.
- Operation taxonomy errors remain legacy/local.

Validation:
- focused Rook.Tests suite passed.
- RookBim boundary tests passed or documented limitation.
- native MSVC 14.44 Debug x64 build passed.
- git diff --check passed.
- standalone Rhino live /bim/status not_rhino_inside smoke passed.
- Rhino.Inside/Revit live validation status recorded.
```

- [ ] **Step 4: Push and open PR**

```powershell
git push -u origin HEAD
gh pr create --base main --title "[codex] Add Phase 2C RookBIM diagnostics" --body-file <prepared-body-file>
```

Expected:

```text
PR URL printed
```

Open as ready only if all required validation gates passed. Open as draft if live validation or native build is still pending.

## Self-Review Notes

Spec coverage:

- Native callback unavailable is covered by Tasks 1-2.
- Managed BIM-only diagnostic serialization is covered by Tasks 3-4.
- Managed/RookBIM readiness code mapping is covered by Tasks 5-6.
- Boundary and anti-drift guards are covered by Task 7.
- Live standalone Rhino smoke is covered by Task 8.
- PR evidence and scope boundaries are covered by Task 9.

Placeholder scan:

- This plan intentionally avoids placeholder steps and includes exact files, snippets, commands, and expected outcomes.

Type consistency:

- Native helpers return `nlohmann::json`, matching existing `RouteDiagnostics.h`.
- Managed diagnostics use optional `ApiResponse.Diagnostic` and BIM-only bridge serialization.
- `diagnostic.reasonCode` values match the approved Phase 2C design and existing `/capabilities` vocabulary.
