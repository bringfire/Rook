# RookVision CanvasDirector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first RookVisionCanvasDirector slice: Grasshopper emits a side-effect-free typed export envelope, Python persists and compiles it into Director runtime truth, and execution goes through existing Director compiler/frame-capture/video primitives rather than treating the GH canvas as runtime truth.

**Architecture:** Native exposes `/director/canvas/extract` as a thin facade over a managed `canvas_director_dispatch` bridge callback. The Companion owns GH solve/export extraction and returns an envelope; Python/MCP owns project `.rook` persistence, restricted canonical hash verification, authoring-spec compilation, run input/provenance files, and orchestration into existing Director compile-motion, frame-capture, and video assembly.

**Tech Stack:** Rhino 8/RhinoCommon, Grasshopper via managed reflection, RookNative C++/httplib/nlohmann::json, C# net48/net7/net8, Python 3.10+, pytest, xUnit.

---

## Scope Split

This plan implements the first slice only:

- `POST /director/canvas/extract`.
- A managed extraction envelope with `canvas_export_state`, `canvas_export_state_sha256`, `diagnostics`, optional `suggested_spec_id`, and `read_only: true`.
- Python persistence under `.rook/director/exports` and `.rook/director/specs`.
- A narrow `DirectorAuthoringSpec` compiler plus a `build_compile_motion_request()` adapter that maps one CanvasDirector payload family into the existing `director_compiler.compile_motion` input shape.
- Run evidence input copying to `<run_directory>/inputs/director_authoring_spec.json` plus `<run_directory>/inputs/provenance.json`.
- Live validation through `director_compiler.compile_motion()`, a new `director.run_compiled_track()` helper over `/director/frame-capture`, and `director_video.assemble_director_video()`. `DirectorAuthoringSpec` must never be passed directly to `director.run_director()`.

Contract chain: `CanvasProposal -> CanvasExportState -> Project DirectorAuthoringSpec -> DirectorTrack -> Run evidence input copy -> DirectorRunArtifacts`.

This plan does not implement a GH-preview capture mode, a custom `.gha`, or a new proposal-creation route. Proposal creation remains Python/MCP orchestration over existing GH edit/canvas tools.

## Existing Director Runtime Contracts To Preserve

CanvasDirector is an adapter into the current Director runtime, not a new runner. Implementation must preserve these contracts:

- Output roots: all explicit `output_root` values must resolve under `resolve_output_root(...)` and the configured Director output root. Tests must pass a `DirectorRuntimePaths` override and choose output roots under that override. Live smoke should omit `output_root` unless `ROOK_DIRECTOR_OUTPUT_ROOT` is explicitly configured.
- Run ids: explicit `run_id` values are opaque tokens, not paths. Validate with `[A-Za-z0-9][A-Za-z0-9_-]{0,127}` and verify the resolved run directory is a child of the resolved output root, not the output root itself, before creating directories.
- Run directories: each run directory is created under the resolved Director output root and contains `manifest.json`, `status.json`, `frames/`, `logs/frame_evidence.jsonl`, and optional `inputs/` evidence files.
- Manifest schema: `director_video.assemble_director_video()` consumes `manifest.json` with positive `frame_count`, `resolution`, `timeline`, `frames`, and per-frame `output_path` entries. CanvasDirector must add compiled-track provenance without removing existing fields video assembly expects.
- Frame evidence: every `/director/frame-capture` call appends one evidence record. Capture failures, missing output files, dirty partial state, and evidence write failures must map to the same terminal states used by the existing Director loop.
- Video assembly: video is assembled from a completed run directory via `director_video.assemble_director_video({"run_root": ...})`; it should not read from project `.rook/director/specs`.
- Typed errors: adapter validation failures raise existing Python `DirectorInputError`/typed CanvasDirector errors, not raw `TypeError`/`ValueError`.
- Test runtime override: unit tests that create runs use `runtime=_runtime(tmp_path)` or equivalent and never write outside the configured test output root.
- Authoring vs runtime storage: project `.rook/director/exports` and `.rook/director/specs` store reusable authoring intent. Run output directories store immutable execution evidence and product artifacts.
- Runtime truth: once capture starts, the compiled track, manifest, frame evidence, run-local input copy, and video manifest are execution truth. The GH canvas and project spec are provenance, not the active runtime.

## File Structure

Native:

- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.h`: declare CanvasDirector bridge readiness and invoke helpers.
- Modify `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`: add ABI callback slot and `InvokeCanvasDirectorDispatchWithBody`.
- Modify `src/RookNative/Handlers/DirectorHandler.h`: declare `HandleDirectorCanvasExtract`.
- Modify `src/RookNative/Handlers/DirectorHandler.cpp`: add the `/director/canvas/extract` facade helper near other Director handlers.
- Modify `src/RookNative/RookServer.cpp`: register `POST /director/canvas/extract`.
- Modify `src/Rook.Tests/Handlers/NativeDirectorCanvasDispatchSourceTests.cs`: source-level route/facade tests.

Managed:

- Modify `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`: add callback registration and `HandleCanvasDirectorDispatch`.
- Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorHandler.cs`: managed validation boundary and op dispatcher.
- Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorModels.cs`: envelope, errors, request, solve-mode names.
- Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorCanonicalJson.cs`: shared C# canonicalizer/hash helper for the subset accepted in slice one.
- Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorExtractor.cs`: GH document/export discovery and read-only extraction.
- Create `src/Rook.Tests/Services/Vision/CanvasDirector/CanvasDirectorHandlerTests.cs`: managed pure dispatch/hash tests.

Python:

- Create `mcp_server/src/rook/canvas_director.py`: native extraction call, restricted RFC 8785/JCS-compatible hash verification, ID/path policy, full extraction envelope/spec persistence, authoring-spec compilation helpers, and run input provenance helpers.
- Modify `mcp_server/src/rook/director.py`: add `run_compiled_track()` for compiled track capture, accept evidence spec/provenance copy data there, and write `<run_directory>/inputs/*` before frame capture.
- Modify `mcp_server/src/rook/server.py`: expose `rhino_director_canvas_extract`.
- Modify `mcp_server/src/rook/agent/tool_groups.py`: add the tool to the `director` group only.
- Create `mcp_server/tests/test_canvas_director.py`: pure Python contract tests.
- Modify `mcp_server/tests/test_director_mcp_tools.py`: tool registration/dispatch tests.
- Modify `mcp_server/tests/test_director.py`: run input/provenance tests.

No `.vcxproj`, `.vcxproj.filters`, or new native `.cpp` files are needed.

---

### Task 1: Native CanvasDirector Facade

**Files:**

- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.h`
- Modify: `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`
- Modify: `src/RookNative/Handlers/DirectorHandler.h`
- Modify: `src/RookNative/Handlers/DirectorHandler.cpp`
- Modify: `src/RookNative/RookServer.cpp`
- Create: `src/Rook.Tests/Handlers/NativeDirectorCanvasDispatchSourceTests.cs`

- [ ] **Step 1: Write source tests for the native route and bridge helper**

Create `src/Rook.Tests/Handlers/NativeDirectorCanvasDispatchSourceTests.cs`:

```csharp
using System;
using System.IO;
using Xunit;

namespace Rook.Tests.Handlers
{
    public class NativeDirectorCanvasDispatchSourceTests
    {
        [Fact]
        public void DirectorCanvasExtractRoute_IsRegisteredUnderDirectorCanvas()
        {
            var server = ReadSourceFile("src", "RookNative", "RookServer.cpp");

            Assert.Contains("\"/director/canvas/extract\"", server);
            Assert.Contains("HandleDirectorCanvasExtract(req, res);", server);
        }

        [Fact]
        public void DirectorCanvasExtractHandler_InjectsExtractOpAndUsesCanvasDirectorDispatch()
        {
            var source = ReadSourceFile("src", "RookNative", "Handlers", "DirectorHandler.cpp");
            var handler = ExtractFunction(source, "HandleDirectorCanvasExtract");

            Assert.Contains("body[\"op\"] = \"extract\";", handler);
            Assert.Contains("InvokeCanvasDirectorDispatchWithBody", handler);
            Assert.Contains("CRookServer::SendErrorData", handler);
            Assert.Contains("MakeErrorData(\"invalid_input\"", handler);
            Assert.Contains("canvas_director_unavailable", handler);
            Assert.Contains("canvas_director_dispatch_failed", handler);
            Assert.Contains("X-Rook-Director-Canvas-Op", handler);
            Assert.DoesNotContain("CMainThreadDispatcher::Instance().Dispatch", handler);
            Assert.DoesNotContain("CRhinoDoc::", handler);
            Assert.DoesNotContain("RunScript", handler);
        }

        [Fact]
        public void GrasshopperProxy_DeclaresCanvasDirectorDispatchCallback()
        {
            var header = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.h");
            var source = ReadSourceFile("src", "RookNative", "Handlers", "GrasshopperProxyHandler.cpp");

            Assert.Contains("bool HasCanvasDirectorDispatchRegistration();", header);
            Assert.Contains("InvokeCanvasDirectorDispatchWithBody", header);
            Assert.Contains("canvas_director_dispatch", source);
            Assert.Contains("HasCanvasDirectorDispatchRegistration", source);
            Assert.Contains("InvokeCanvasDirectorDispatchWithBody", source);
        }

        private static string ExtractFunction(string source, string functionName)
        {
            var signatureStart = source.IndexOf(functionName, StringComparison.Ordinal);
            if (signatureStart < 0)
                throw new InvalidOperationException("Function not found: " + functionName);
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
            throw new FileNotFoundException("Could not locate source file " + string.Join("/", pathParts));
        }
    }
}
```

- [ ] **Step 2: Run the source tests and confirm they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter NativeDirectorCanvasDispatchSourceTests
```

Expected: the three new tests fail because route, callback slot, and handler do not exist.

- [ ] **Step 3: Add the native bridge declarations**

In `src/RookNative/Handlers/GrasshopperProxyHandler.h`, add after `HasVisionDispatchRegistration()`:

```cpp
bool HasCanvasDirectorDispatchRegistration();
```

Add after `InvokeVisionDispatchWithBody(...)`:

```cpp
// Invokes the managed canvas_director_dispatch bridge callback. Native
// /director/canvas/* routes inject only the op discriminator and forward the
// opaque JSON body to the managed CanvasDirector validation boundary.
ManagedCreateInvokeResult InvokeCanvasDirectorDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error);
```

- [ ] **Step 4: Add the native bridge callback slot and invoker**

In `src/RookNative/Handlers/GrasshopperProxyHandler.cpp`, add a callback slot after `vision_dispatch`:

```cpp
// ABI v17: CanvasDirector domain (single generic dispatch; op carried in
// request JSON). Native /director/canvas/* remains the public surface.
GhBridgeCallbackFn canvas_director_dispatch = nullptr;
```

Increment the local `kGhBridgeAbiVersion` by one. Update the matching managed version in Task 2.

Add readiness after `HasVisionDispatchRegistration()`:

```cpp
bool HasCanvasDirectorDispatchRegistration()
{
    std::lock_guard<std::mutex> lock(g_ghBridgeMutex);
    return g_ghBridgeRegistration.version == kGhBridgeAbiVersion
        && g_ghBridgeRegistration.canvas_director_dispatch != nullptr;
}
```

Add invoker after `InvokeVisionDispatchWithBody`:

```cpp
ManagedCreateInvokeResult InvokeCanvasDirectorDispatchWithBody(
    const std::string& requestJson,
    std::string& responseJson,
    int& statusCode,
    std::string& error)
{
    const auto registration = GetGhBridgeRegistrationSnapshot();
    if (registration.canvas_director_dispatch == nullptr)
    {
        error = "CanvasDirector dispatch callback is not registered.";
        return ManagedCreateInvokeResult::Unavailable;
    }

    const auto result = TryInvokeRegisteredCallbackWithBody(
        registration.canvas_director_dispatch,
        requestJson,
        responseJson,
        statusCode,
        error);

    switch (result)
    {
    case BridgeInvokeResult::Completed:
        return ManagedCreateInvokeResult::Ok;
    case BridgeInvokeResult::Unavailable:
        return ManagedCreateInvokeResult::Unavailable;
    case BridgeInvokeResult::Failed:
    default:
        return ManagedCreateInvokeResult::Failed;
    }
}
```

- [ ] **Step 5: Add the Director facade handler**

In `src/RookNative/Handlers/DirectorHandler.h`, add:

```cpp
void HandleDirectorCanvasExtract(const httplib::Request& req, httplib::Response& res);
```

In `src/RookNative/Handlers/DirectorHandler.cpp`, add `#include "Handlers/GrasshopperProxyHandler.h"` if it is not already included. Near the other public handler functions, add:

```cpp
void HandleDirectorCanvasExtract(const httplib::Request& req, httplib::Response& res)
{
    nlohmann::json body = nlohmann::json::object();
    if (!req.body.empty())
    {
        try
        {
            body = nlohmann::json::parse(req.body);
        }
        catch (const std::exception& ex)
        {
            CRookServer::SendErrorData(res, MakeErrorData("invalid_input", ex.what()));
            res.status = 400;
            res.set_header("X-Rook-Director-Canvas-Op", "extract");
            return;
        }
        if (!body.is_object())
        {
            CRookServer::SendErrorData(res, MakeErrorData("invalid_input", "/director/canvas/extract body must be a JSON object."));
            res.status = 400;
            res.set_header("X-Rook-Director-Canvas-Op", "extract");
            return;
        }
    }

    body["op"] = "extract";
    const std::string requestJson = body.dump();

    std::string responseJson;
    int statusCode = 0;
    std::string invokeError;
    const auto result = InvokeCanvasDirectorDispatchWithBody(
        requestJson,
        responseJson,
        statusCode,
        invokeError);

    switch (result)
    {
    case ManagedCreateInvokeResult::Ok:
        res.status = statusCode == 0 ? 200 : statusCode;
        res.set_content(responseJson, "application/json");
        res.set_header("X-Rook-Director-Canvas-Op", "extract");
        return;
    case ManagedCreateInvokeResult::Unavailable:
        CRookServer::SendErrorData(res, MakeErrorData("canvas_director_unavailable", "CanvasDirector routes require the Rook companion plugin."));
        res.status = 503;
        res.set_header("X-Rook-Director-Canvas-Op", "extract");
        return;
    case ManagedCreateInvokeResult::Failed:
    default:
        CRookServer::SendErrorData(res, MakeErrorData("canvas_director_dispatch_failed", invokeError));
        res.status = 500;
        res.set_header("X-Rook-Director-Canvas-Op", "extract");
        return;
    }
}
```

- [ ] **Step 6: Register the route**

In `src/RookNative/RookServer.cpp`, add after the other `/director/...` routes:

```cpp
m_server->Post("/director/canvas/extract", [this](const httplib::Request& req, httplib::Response& res) {
    HandleDirectorCanvasExtract(req, res);
});
```

- [ ] **Step 7: Run native facade source tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter NativeDirectorCanvasDispatchSourceTests
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

Run:

```powershell
git add src/RookNative/Handlers/GrasshopperProxyHandler.h src/RookNative/Handlers/GrasshopperProxyHandler.cpp src/RookNative/Handlers/DirectorHandler.h src/RookNative/Handlers/DirectorHandler.cpp src/RookNative/RookServer.cpp src/Rook.Tests/Handlers/NativeDirectorCanvasDispatchSourceTests.cs
git commit -m "feat(canvas-director): add native extract facade"
```

---

### Task 2: Managed CanvasDirector Dispatch Boundary

**Files:**

- Modify: `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`
- Create: `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorModels.cs`
- Create: `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorCanonicalJson.cs`
- Create: `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorHandler.cs`
- Create: `src/Rook.Tests/Services/Vision/CanvasDirector/CanvasDirectorHandlerTests.cs`
- Modify: `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`

- [ ] **Step 1: Write managed dispatch tests**

Create `src/Rook.Tests/Services/Vision/CanvasDirector/CanvasDirectorHandlerTests.cs`:

```csharp
using System.Text.Json;
using Rook.Services.Vision.CanvasDirector;
using Xunit;

namespace Rook.Tests.Services.Vision.CanvasDirector
{
    public class CanvasDirectorHandlerTests
    {
        [Fact]
        public void Dispatch_MissingOp_ReturnsInvalidInput()
        {
            var handler = new CanvasDirectorHandler(new FakeExtractor());
            var result = handler.Dispatch("{}");

            Assert.False(result.Success);
            Assert.Equal(400, result.HttpStatus);
            var json = JsonSerializer.Serialize(result.Data);
            Assert.Contains("invalid_input", json);
        }

        [Fact]
        public void Dispatch_UnknownOp_ReturnsInvalidInput()
        {
            var handler = new CanvasDirectorHandler(new FakeExtractor());
            var result = handler.Dispatch("{\"op\":\"nope\"}");

            Assert.False(result.Success);
            Assert.Equal(400, result.HttpStatus);
            var json = JsonSerializer.Serialize(result.Data);
            Assert.Contains("invalid_input", json);
            Assert.Contains("nope", json);
        }

        [Fact]
        public void Dispatch_Extract_ReturnsEnvelopeWithReadOnlyAndHash()
        {
            var handler = new CanvasDirectorHandler(new FakeExtractor());
            var result = handler.Dispatch("{\"op\":\"extract\",\"export_id\":\"export_a\"}");

            Assert.True(result.Success);
            Assert.Equal(200, result.HttpStatus);
            var json = JsonSerializer.Serialize(result.Data, new JsonSerializerOptions
            {
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            });
            Assert.Contains("canvas_export_state", json);
            Assert.Contains("canvas_export_state_sha256", json);
            Assert.Contains("read_only", json);
            Assert.DoesNotContain("canvasExportState", json);
            Assert.DoesNotContain("canvasExportStateSha256", json);
        }

        [Fact]
        public void CanonicalHash_IsStableForSortedKeys()
        {
            var left = JsonDocument.Parse("{\"b\":\"2\",\"a\":\"1\"}").RootElement.Clone();
            var right = JsonDocument.Parse("{\"a\":\"1\",\"b\":\"2\"}").RootElement.Clone();

            Assert.Equal(
                CanvasDirectorCanonicalJson.Sha256Hex(left),
                CanvasDirectorCanonicalJson.Sha256Hex(right));
        }

        [Theory]
        [InlineData("{\"b\":\"2\",\"a\":\"1\"}", "{\"a\":\"1\",\"b\":\"2\"}")]
        [InlineData("{\"text\":\"<>&\",\"list\":[true,null,3]}", "{\"list\":[true,null,3],\"text\":\"<>&\"}")]
        public void CanonicalSerialize_MatchesRestrictedCrossLanguageVectors(string input, string expected)
        {
            using var doc = JsonDocument.Parse(input);

            Assert.Equal(expected, CanvasDirectorCanonicalJson.Serialize(doc.RootElement));
        }

        [Fact]
        public void CanonicalSerialize_RejectsNonIntegerNumbersInSliceOne()
        {
            using var doc = JsonDocument.Parse("{\"x\":1.25}");

            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorCanonicalJson.Serialize(doc.RootElement));

            Assert.Equal("invalid_input", ex.Code);
        }

        [Fact]
        public void ParseRequest_PreservesDocumentAndProposalIdentity()
        {
            var request = CanvasDirectorExtractRequest.Parse(
                "{\"op\":\"extract\",\"document_id\":\"gh-doc-1\",\"proposal_id\":\"proposal-1\"}");

            Assert.Equal("gh-doc-1", request.DocumentId);
            Assert.Equal("proposal-1", request.ProposalId);
        }

        private sealed class FakeExtractor : ICanvasDirectorExtractor
        {
            public CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request)
            {
                return CanvasDirectorExtractionEnvelope.FromState(new
                {
                    schema_version = 1,
                    export_id = request.ExportId ?? "export_a",
                    template_id = "canvas_director.basic_motion",
                    template_version = "0.1.0",
                    payload = new { timeline = new { fps = 24, frame_count = 3 } }
                });
            }
        }
    }
}
```

- [ ] **Step 2: Write bridge registration tests**

In `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs`, add:

```csharp
[Fact]
public void Registrar_DeclaresCanvasDirectorDispatchCallback()
{
    var source = File.ReadAllText(Path.Combine(FindRepoRoot(), "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));

    Assert.Contains("CanvasDirectorDispatchCallback", source);
    Assert.Contains("HandleCanvasDirectorDispatch", source);
    Assert.Contains("public IntPtr CanvasDirectorDispatch;", source);
    Assert.Contains("CanvasDirectorDispatch = Marshal.GetFunctionPointerForDelegate(CanvasDirectorDispatchCallback)", source);

    var syncStart = source.IndexOf("private static int ExecuteApiResponseCallback", StringComparison.Ordinal);
    var nextFunction = source.IndexOf("private static uint? ParseDocumentSerialNumber", syncStart, StringComparison.Ordinal);
    var syncExecutor = source.Substring(syncStart, nextFunction - syncStart);
    Assert.Contains("statusCode = MapBridgeStatus(result);", syncExecutor);
    Assert.DoesNotContain("statusCode = result.Success ? 200 : 400;", syncExecutor);
    Assert.Contains("timeoutErrorCode", syncExecutor);
    Assert.Contains("solve_timeout", source);
}
```

- [ ] **Step 3: Run tests and confirm they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "CanvasDirectorHandlerTests|Registrar_DeclaresCanvasDirectorDispatchCallback"
```

Expected: FAIL because managed CanvasDirector files and bridge fields do not exist.

- [ ] **Step 4: Add managed models**

Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorModels.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorExtractRequest
    {
        public string? Op { get; init; }
        public string? ExportId { get; init; }
        public string? DocumentId { get; init; }
        public string? ProposalId { get; init; }
        public string SolveMode { get; init; } = "require_fresh_solve";
        public string? ExpectedSolutionToken { get; init; }

        public static CanvasDirectorExtractRequest Parse(string? requestJson)
        {
            using var doc = string.IsNullOrWhiteSpace(requestJson)
                ? JsonDocument.Parse("{}")
                : JsonDocument.Parse(requestJson);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                throw new CanvasDirectorException("invalid_input", "CanvasDirector request body must be a JSON object.", 400);
            return new CanvasDirectorExtractRequest
            {
                Op = GetString(root, "op"),
                ExportId = GetString(root, "export_id"),
                DocumentId = GetString(root, "document_id"),
                ProposalId = GetString(root, "proposal_id"),
                SolveMode = GetString(root, "solve_mode") ?? "require_fresh_solve",
                ExpectedSolutionToken = GetString(root, "expected_solution_token"),
            };
        }

        private static string? GetString(JsonElement root, string name)
        {
            return root.TryGetProperty(name, out var el) && el.ValueKind == JsonValueKind.String
                ? el.GetString()
                : null;
        }
    }

    internal sealed class CanvasDirectorException : Exception
    {
        public CanvasDirectorException(string code, string message, int httpStatus = 400) : base(message)
        {
            Code = code;
            HttpStatus = httpStatus;
        }

        public string Code { get; }
        public int HttpStatus { get; }
    }

    internal sealed class CanvasDirectorExtractionEnvelope
    {
        [JsonPropertyName("canvas_export_state")]
        public object CanvasExportState { get; init; } = new Dictionary<string, object?>();

        [JsonPropertyName("canvas_export_state_sha256")]
        public string CanvasExportStateSha256 { get; init; } = "";

        [JsonPropertyName("diagnostics")]
        public object[] Diagnostics { get; init; } = Array.Empty<object>();

        [JsonPropertyName("suggested_spec_id")]
        public string? SuggestedSpecId { get; init; }

        [JsonPropertyName("read_only")]
        public bool ReadOnly { get; init; } = true;

        public static CanvasDirectorExtractionEnvelope FromState(object state)
        {
            var element = JsonSerializer.SerializeToElement(state);
            return new CanvasDirectorExtractionEnvelope
            {
                CanvasExportState = element,
                CanvasExportStateSha256 = CanvasDirectorCanonicalJson.Sha256Hex(element),
                Diagnostics = Array.Empty<object>(),
                ReadOnly = true,
            };
        }
    }

    internal interface ICanvasDirectorExtractor
    {
        CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request);
    }
}
```

- [ ] **Step 5: Add managed canonical JSON helper**

Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorCanonicalJson.cs`:

```csharp
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Encodings.Web;
using System.Text.Json;

namespace Rook.Services.Vision.CanvasDirector
{
    internal static class CanvasDirectorCanonicalJson
    {
        // Restricted RFC 8785/JCS-compatible subset for slice one:
        // UTF-8, sorted object keys, no insignificant whitespace, strings
        // serialized without HTML escaping, and integer-only JSON numbers.
        // Non-integer numeric values must be exported as validated strings.
        public static string Sha256Hex(JsonElement element)
        {
            var bytes = Encoding.UTF8.GetBytes(Serialize(element));
            using var sha = SHA256.Create();
            return Convert.ToHexString(sha.ComputeHash(bytes)).ToLowerInvariant();
        }

        public static string Serialize(JsonElement element)
        {
            var sb = new StringBuilder();
            WriteElement(sb, element);
            return sb.ToString();
        }

        private static void WriteElement(StringBuilder sb, JsonElement element)
        {
            switch (element.ValueKind)
            {
                case JsonValueKind.Object:
                    sb.Append('{');
                    var props = new List<JsonProperty>();
                    foreach (var prop in element.EnumerateObject()) props.Add(prop);
                    props.Sort((a, b) => string.CompareOrdinal(a.Name, b.Name));
                    for (var i = 0; i < props.Count; i++)
                    {
                        if (i > 0) sb.Append(',');
                        WriteString(sb, props[i].Name);
                        sb.Append(':');
                        WriteElement(sb, props[i].Value);
                    }
                    sb.Append('}');
                    return;
                case JsonValueKind.Array:
                    sb.Append('[');
                    var first = true;
                    foreach (var item in element.EnumerateArray())
                    {
                        if (!first) sb.Append(',');
                        first = false;
                        WriteElement(sb, item);
                    }
                    sb.Append(']');
                    return;
                case JsonValueKind.String:
                    WriteString(sb, element.GetString() ?? "");
                    return;
                case JsonValueKind.Number:
                    WriteNumber(sb, element);
                    return;
                case JsonValueKind.True:
                    sb.Append("true");
                    return;
                case JsonValueKind.False:
                    sb.Append("false");
                    return;
                case JsonValueKind.Null:
                    sb.Append("null");
                    return;
                default:
                    throw new CanvasDirectorException("invalid_input", "Unsupported JSON value in CanvasExportState.", 400);
            }
        }

        private static void WriteString(StringBuilder sb, string value)
        {
            sb.Append(JsonSerializer.Serialize(value, new JsonSerializerOptions
            {
                Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping
            }));
        }

        private static void WriteNumber(StringBuilder sb, JsonElement element)
        {
            if (element.TryGetInt64(out var integer))
            {
                sb.Append(integer.ToString(CultureInfo.InvariantCulture));
                return;
            }
            throw new CanvasDirectorException(
                "invalid_input",
                "CanvasExportState numeric values must be integers in slice one; non-integer exported values must be encoded as strings.",
                400);
        }
    }
}
```

- [ ] **Step 6: Add managed dispatch handler**

Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorHandler.cs`:

```csharp
using System.Text.Json;
using Rook.Handlers;

namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorHandler
    {
        private readonly ICanvasDirectorExtractor _extractor;

        public CanvasDirectorHandler() : this(new CanvasDirectorExtractor())
        {
        }

        internal CanvasDirectorHandler(ICanvasDirectorExtractor extractor)
        {
            _extractor = extractor;
        }

        public ApiResponse Dispatch(string? requestJson)
        {
            try
            {
                var request = CanvasDirectorExtractRequest.Parse(requestJson);
                if (request.Op != "extract")
                    throw new CanvasDirectorException("invalid_input", $"Unknown CanvasDirector op '{request.Op}'.", 400);

                var envelope = _extractor.Extract(request);
                return new ApiResponse { Success = true, Data = envelope, HttpStatus = 200 };
            }
            catch (JsonException ex)
            {
                return Failure("invalid_input", $"Invalid JSON body: {ex.Message}", 400);
            }
            catch (CanvasDirectorException ex)
            {
                return Failure(ex.Code, ex.Message, ex.HttpStatus);
            }
        }

        private static ApiResponse Failure(string code, string message, int httpStatus)
        {
            return new ApiResponse
            {
                Success = false,
                HttpStatus = httpStatus,
                Data = new { code, message },
            };
        }
    }
}
```

- [ ] **Step 7: Wire the managed callback**

In `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`, add:

```csharp
using Rook.Services.Vision.CanvasDirector;
```

Add a static handler near the Vision static field:

```csharp
private static readonly CanvasDirectorHandler CanvasDirector = new();
```

Add callback field:

```csharp
private static readonly NativeGhBridgeCallback CanvasDirectorDispatchCallback = HandleCanvasDirectorDispatch;
```

Add to `NativeGhBridgeRegistration` after `VisionDispatch`:

```csharp
// ABI v17: CanvasDirector domain.
public IntPtr CanvasDirectorDispatch;
```

In `TryRegister()`, add:

```csharp
CanvasDirectorDispatch = Marshal.GetFunctionPointerForDelegate(CanvasDirectorDispatchCallback),
```

Add handler near `HandleVisionDispatch`:

```csharp
private static int HandleCanvasDirectorDispatch(
    IntPtr requestJsonUtf8,
    int requestJsonLength,
    IntPtr responseJsonUtf8,
    int responseJsonCapacity,
    IntPtr responseJsonLength,
    IntPtr httpStatusCode)
{
    return ExecuteApiResponseCallback(
        requestJsonUtf8,
        requestJsonLength,
        responseJsonUtf8,
        responseJsonCapacity,
        responseJsonLength,
        httpStatusCode,
        requestJson => CanvasDirector.Dispatch(requestJson),
        timeoutSeconds: 120,
        timeoutErrorCode: "solve_timeout",
        timeoutHttpStatus: 504);
}
```

In the shared synchronous `ExecuteApiResponseCallback`, replace the legacy status assignment:

```csharp
statusCode = result.Success ? 200 : 400;
```

with:

```csharp
statusCode = MapBridgeStatus(result);
```

This keeps CanvasDirector errors such as `grasshopper_not_ready` and `canvas_director_unavailable` aligned with the `ApiResponse.HttpStatus` contract.

Extend the same helper signature with structured timeout options:

```csharp
Func<string, ApiResponse> operation,
int timeoutSeconds = 30,
string? timeoutErrorCode = null,
int? timeoutHttpStatus = null)
```

Replace the timeout branch with:

```csharp
if (!waitHandle.Wait(TimeSpan.FromSeconds(timeoutSeconds)))
{
    object data = timeoutErrorCode == null
        ? "GH callback request timed out."
        : new { code = timeoutErrorCode, message = "CanvasDirector extraction timed out while waiting for Grasshopper solve/extract." };
    responseJson = JsonSerializer.Serialize(new
    {
        success = false,
        data
    }, JsonOptions);
    statusCode = timeoutHttpStatus ?? 400;
}
```

This preserves legacy timeout responses by default while making CanvasDirector timeouts typed as `solve_timeout`.

Increment the managed bridge version to match Task 1.

- [ ] **Step 8: Add temporary extractor implementation**

Create `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorExtractor.cs` with a strict not-ready implementation that Task 3 replaces:

```csharp
namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorExtractor : ICanvasDirectorExtractor
    {
        public CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request)
        {
            throw new CanvasDirectorException(
                "grasshopper_not_ready",
                "CanvasDirector extraction requires an active Grasshopper document.",
                503);
        }
    }
}
```

- [ ] **Step 9: Run managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "CanvasDirectorHandlerTests|Registrar_DeclaresCanvasDirectorDispatchCallback"
```

Expected: PASS.

- [ ] **Step 10: Commit Task 2**

Run:

```powershell
git add src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook/Services/Vision/CanvasDirector src/Rook.Tests/Services/Vision/CanvasDirector src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs
git commit -m "feat(canvas-director): add managed dispatch boundary"
```

---

### Task 3: Managed Grasshopper Export Extraction

**Files:**

- Modify: `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorExtractor.cs`
- Modify: `src/Rook/Services/Vision/CanvasDirector/CanvasDirectorModels.cs`
- Create: `src/Rook.Tests/Services/Vision/CanvasDirector/CanvasDirectorExtractorTests.cs`

- [ ] **Step 1: Write pure tests for solve-mode validation and export parsing**

Create `src/Rook.Tests/Services/Vision/CanvasDirector/CanvasDirectorExtractorTests.cs`:

```csharp
using Rook.Services.Vision.CanvasDirector;
using Xunit;

namespace Rook.Tests.Services.Vision.CanvasDirector
{
    public class CanvasDirectorExtractorTests
    {
        [Fact]
        public void ValidateSolveMode_RejectsMissingFreshnessTokenForReuse()
        {
            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorExtractor.ValidateSolveMode("reuse_verified_solution", null, supportsReuseVerification: true));

            Assert.Equal("freshness_token_required", ex.Code);
        }

        [Fact]
        public void ValidateSolveMode_RejectsUnsupportedReuseVerification()
        {
            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorExtractor.ValidateSolveMode("reuse_verified_solution", "serial-1", supportsReuseVerification: false));

            Assert.Equal("unsupported_solve_mode", ex.Code);
        }

        [Fact]
        public void RequireFreshSolve_InvokesNewSolutionAndAdvancesToken()
        {
            var doc = new AdvancingGhDocument();

            CanvasDirectorExtractor.RequireFreshSolve(doc);

            Assert.Equal(1, doc.NewSolutionCalls);
            Assert.True(doc.ExpireAllObjects);
        }

        [Fact]
        public void RequireFreshSolve_FailsWhenSolutionTokenDoesNotAdvance()
        {
            var doc = new StaleGhDocument();

            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorExtractor.RequireFreshSolve(doc));

            Assert.Equal("solution_stale", ex.Code);
        }

        [Fact]
        public void ValidateDocumentIdentity_RejectsWrongDocumentId()
        {
            var request = new CanvasDirectorExtractRequest { DocumentId = "gh-doc-expected" };
            var doc = new IdentityGhDocument { DocumentID = "gh-doc-actual" };

            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorExtractor.ValidateDocumentIdentity(doc, request));

            Assert.Equal("document_mismatch", ex.Code);
        }

        [Fact]
        public void ParseExportPayload_RequiresDeclaredMarker()
        {
            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorExtractor.ParseExportPayload("{\"schema_version\":1}"));

            Assert.Equal("export_schema_mismatch", ex.Code);
        }

        [Fact]
        public void ParseExportPayload_ReturnsEnvelopeForDeclaredPayload()
        {
            var payload = "{" +
                "\"metadata_kind\":\"rook.canvas_director.export\"," +
                "\"schema_version\":1," +
                "\"export_id\":\"export_a\"," +
                "\"proposal_id\":\"proposal-1\"," +
                "\"template_id\":\"canvas_director.basic_motion\"," +
                "\"template_version\":\"0.1.0\"," +
                "\"payload\":{\"timeline\":{\"fps\":24,\"frame_count\":3}}" +
                "}";

            var envelope = CanvasDirectorExtractor.ParseExportPayload(
                payload,
                new CanvasDirectorExtractRequest { ProposalId = "proposal-1" });

            Assert.True(envelope.ReadOnly);
            Assert.NotEmpty(envelope.CanvasExportStateSha256);
        }

        [Fact]
        public void ParseExportPayload_RejectsWrongProposalId()
        {
            var payload = "{" +
                "\"metadata_kind\":\"rook.canvas_director.export\"," +
                "\"schema_version\":1," +
                "\"export_id\":\"export_a\"," +
                "\"proposal_id\":\"proposal-actual\"," +
                "\"template_id\":\"canvas_director.basic_motion\"," +
                "\"template_version\":\"0.1.0\"," +
                "\"payload\":{\"timeline\":{\"fps\":24,\"frame_count\":3}}" +
                "}";

            var ex = Assert.Throws<CanvasDirectorException>(() =>
                CanvasDirectorExtractor.ParseExportPayload(
                    payload,
                    new CanvasDirectorExtractRequest { ProposalId = "proposal-expected" }));

            Assert.Equal("document_mismatch", ex.Code);
        }

        private sealed class AdvancingGhDocument
        {
            public List<TimeSpan> SolutionHistory { get; } = new();
            public TimeSpan SolutionSpan { get; private set; }
            public int NewSolutionCalls { get; private set; }
            public bool ExpireAllObjects { get; private set; }
            public void NewSolution(bool expireAllObjects)
            {
                NewSolutionCalls++;
                ExpireAllObjects = expireAllObjects;
                SolutionSpan = TimeSpan.FromMilliseconds(NewSolutionCalls);
                SolutionHistory.Add(SolutionSpan);
            }
        }

        private sealed class StaleGhDocument
        {
            public List<TimeSpan> SolutionHistory { get; } = new() { TimeSpan.FromMilliseconds(10) };
            public TimeSpan SolutionSpan { get; } = TimeSpan.FromMilliseconds(10);
            public void NewSolution(bool expireAllObjects) { }
        }

        private sealed class IdentityGhDocument
        {
            public string? DocumentID { get; init; }
        }
    }
}
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter CanvasDirectorExtractorTests
```

Expected: FAIL because validation/parser methods do not exist.

- [ ] **Step 3: Implement solve-mode validation and payload parser**

Add to `CanvasDirectorExtractor`:

```csharp
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;

namespace Rook.Services.Vision.CanvasDirector
{
    internal sealed class CanvasDirectorExtractor : ICanvasDirectorExtractor
    {
        public CanvasDirectorExtractionEnvelope Extract(CanvasDirectorExtractRequest request)
        {
            ValidateSolveMode(request.SolveMode, request.ExpectedSolutionToken, supportsReuseVerification: false);
            var document = ResolveActiveGrasshopperDocument();
            ValidateDocumentIdentity(document, request);
            ApplySolveMode(document, request);
            var payload = TryExtractFromDocument(document, request);
            return ParseExportPayload(payload, request);
        }

        internal static void ValidateSolveMode(string solveMode, string? expectedSolutionToken, bool supportsReuseVerification)
        {
            if (solveMode == "require_fresh_solve")
                return;
            if (solveMode == "reuse_verified_solution")
            {
                if (string.IsNullOrWhiteSpace(expectedSolutionToken))
                    throw new CanvasDirectorException("freshness_token_required", "reuse_verified_solution requires expected_solution_token.", 400);
                if (!supportsReuseVerification)
                    throw new CanvasDirectorException("unsupported_solve_mode", "reuse_verified_solution is not supported until GH solution serial verification is implemented.", 400);
                return;
            }
            throw new CanvasDirectorException("unsupported_solve_mode", $"Unsupported solve_mode '{solveMode}'.", 400);
        }

        internal static void ApplySolveMode(object document, CanvasDirectorExtractRequest request)
        {
            if (request.SolveMode == "require_fresh_solve")
            {
                RequireFreshSolve(document);
                return;
            }

            ValidateSolveMode(request.SolveMode, request.ExpectedSolutionToken, supportsReuseVerification: false);
        }

        internal static void RequireFreshSolve(object document)
        {
            var before = ReadSolutionToken(document);
            if (ReadIntProperty(document, "SolutionDepth").GetValueOrDefault() > 0)
                throw new CanvasDirectorException("solve_locked", "Grasshopper document is already solving.", 409);

            var newSolution = document.GetType().GetMethod("NewSolution", new[] { typeof(bool) });
            if (newSolution == null)
                throw new CanvasDirectorException("solve_failed", "Grasshopper document does not expose NewSolution(bool).", 503);

            try
            {
                // First slice uses a guarded synchronous solve on the UI thread.
                // Do not ScheduleSolution and block inside this sync bridge; that can self-deadlock.
                newSolution.Invoke(document, new object[] { true });
            }
            catch (TargetInvocationException ex)
            {
                throw new CanvasDirectorException("solve_failed", ex.InnerException?.Message ?? ex.Message, 503);
            }

            var after = ReadSolutionToken(document);
            if (before == null || after == null)
                throw new CanvasDirectorException("solve_failed", "Grasshopper solution token could not be read before and after solve.", 503);
            if (string.Equals(before, after, StringComparison.Ordinal))
                throw new CanvasDirectorException("solution_stale", "Fresh solve did not advance the Grasshopper solution token.", 409);
        }

        internal static void ValidateDocumentIdentity(object document, CanvasDirectorExtractRequest request)
        {
            if (string.IsNullOrWhiteSpace(request.DocumentId))
                return;

            var actual = ReadStringProperty(document, "DocumentID")
                ?? ReadStringProperty(document, "RuntimeID")
                ?? ReadStringProperty(document, "FilePath");
            if (string.IsNullOrWhiteSpace(actual) ||
                !string.Equals(actual, request.DocumentId, StringComparison.Ordinal))
            {
                throw new CanvasDirectorException("document_mismatch", "Active Grasshopper document does not match document_id.", 409);
            }
        }

        internal static CanvasDirectorExtractionEnvelope ParseExportPayload(string payloadJson, CanvasDirectorExtractRequest? request = null)
        {
            using var doc = JsonDocument.Parse(payloadJson);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                throw new CanvasDirectorException("export_schema_mismatch", "CanvasDirector export payload must be a JSON object.", 400);
            if (!root.TryGetProperty("metadata_kind", out var kind) ||
                kind.ValueKind != JsonValueKind.String ||
                kind.GetString() != "rook.canvas_director.export")
            {
                throw new CanvasDirectorException("export_schema_mismatch", "Export payload missing metadata_kind rook.canvas_director.export.", 400);
            }
            foreach (var required in new[] { "export_id", "template_id", "template_version", "payload" })
            {
                if (!root.TryGetProperty(required, out _))
                    throw new CanvasDirectorException("export_schema_mismatch", $"Export payload missing required field '{required}'.", 400);
            }
            if (!string.IsNullOrWhiteSpace(request?.ExportId))
            {
                if (!root.TryGetProperty("export_id", out var exportId) ||
                    exportId.ValueKind != JsonValueKind.String ||
                    !string.Equals(exportId.GetString(), request.ExportId, StringComparison.Ordinal))
                {
                    throw new CanvasDirectorException("document_mismatch", "CanvasDirector export_id does not match request.", 409);
                }
            }
            if (!string.IsNullOrWhiteSpace(request?.ProposalId))
            {
                if (!root.TryGetProperty("proposal_id", out var proposal) ||
                    proposal.ValueKind != JsonValueKind.String ||
                    !string.Equals(proposal.GetString(), request.ProposalId, StringComparison.Ordinal))
                {
                    throw new CanvasDirectorException("document_mismatch", "CanvasDirector export proposal_id does not match request.", 409);
                }
            }
            return CanvasDirectorExtractionEnvelope.FromState(root.Clone());
        }

        private static object ResolveActiveGrasshopperDocument()
        {
            var instancesType = Type.GetType("Grasshopper.Instances, Grasshopper");
            var activeCanvas = instancesType?.GetProperty("ActiveCanvas")?.GetValue(null);
            var document = activeCanvas?.GetType().GetProperty("Document")?.GetValue(activeCanvas);
            if (document == null)
                throw new CanvasDirectorException("grasshopper_not_ready", "No active Grasshopper document.", 503);
            return document;
        }

        private static string? ReadSolutionToken(object document)
        {
            var history = document.GetType().GetProperty("SolutionHistory")?.GetValue(document) as System.Collections.ICollection;
            var span = document.GetType().GetProperty("SolutionSpan")?.GetValue(document);
            if (history == null && span == null)
                return null;
            var historyCount = history == null ? "?" : history.Count.ToString(System.Globalization.CultureInfo.InvariantCulture);
            return $"{historyCount}|{span}";
        }

        private static int? ReadIntProperty(object target, string name)
        {
            var value = target.GetType().GetProperty(name)?.GetValue(target);
            return value == null ? null : Convert.ToInt32(value, System.Globalization.CultureInfo.InvariantCulture);
        }

        private static string? ReadStringProperty(object target, string name)
        {
            var value = target.GetType().GetProperty(name)?.GetValue(target);
            return value?.ToString();
        }
    }
}
```

- [ ] **Step 4: Implement temporary first-slice GH export marker discovery**

Add `TryExtractFromDocument` with reflection-based discovery. This is a temporary harness for the first implementation slice: the component nickname must be `CanvasDirector Export:<export_id>` and output 0 must be the JSON export string. Do not treat nickname scraping as the durable schema. The next template iteration should replace this with declared CanvasDirector export component/template metadata.

```csharp
private static string TryExtractFromDocument(object document, CanvasDirectorExtractRequest request)
{
    var objects = document.GetType().GetProperty("Objects")?.GetValue(document) as System.Collections.IEnumerable;
    if (objects == null)
        throw new CanvasDirectorException("grasshopper_not_ready", "Active Grasshopper document does not expose Objects.", 503);

    var matches = new List<string>();
    foreach (var obj in objects)
    {
        var nickname = obj.GetType().GetProperty("NickName")?.GetValue(obj)?.ToString() ?? "";
        if (!nickname.StartsWith("CanvasDirector Export:", StringComparison.Ordinal))
            continue;
        var exportId = nickname.Substring("CanvasDirector Export:".Length).Trim();
        if (!string.IsNullOrWhiteSpace(request.ExportId) &&
            !string.Equals(exportId, request.ExportId, StringComparison.Ordinal))
            continue;

        var payload = ReadFirstOutputString(obj);
        if (!string.IsNullOrWhiteSpace(payload))
            matches.Add(payload!);
    }

    if (matches.Count == 0)
        throw new CanvasDirectorException("export_not_found", "No matching CanvasDirector export component was found.", 404);
    if (matches.Count > 1)
        throw new CanvasDirectorException("multiple_exports_ambiguous", "Multiple matching CanvasDirector export components exist; ensure export markers are unique.", 409);
    return matches[0];
}
```

Add `ReadFirstOutputString` in the same class:

```csharp
private static string? ReadFirstOutputString(object component)
{
    var @params = component.GetType().GetProperty("Params")?.GetValue(component);
    var output = @params?.GetType().GetProperty("Output")?.GetValue(@params) as System.Collections.IList;
    if (output == null || output.Count == 0)
        return null;
    var firstParam = output[0];
    var volatileData = firstParam?.GetType().GetProperty("VolatileData")?.GetValue(firstParam);
    var allData = volatileData?.GetType().GetMethod("AllData")?.Invoke(volatileData, Array.Empty<object>()) as System.Collections.IEnumerable;
    if (allData == null)
        return null;
    foreach (var goo in allData)
    {
        var value = goo.GetType().GetProperty("Value")?.GetValue(goo);
        return value?.ToString();
    }
    return null;
}
```

This nickname/output convention is explicitly a temporary first-slice harness. It is acceptable only because the payload itself still has the declared `metadata_kind`, `template_id`, `template_version`, `export_id`, and optional `proposal_id` fields that Companion validates before returning an envelope.

- [ ] **Step 5: Run managed tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "CanvasDirectorExtractorTests|CanvasDirectorHandlerTests"
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

Run:

```powershell
git add src/Rook/Services/Vision/CanvasDirector src/Rook.Tests/Services/Vision/CanvasDirector
git commit -m "feat(canvas-director): extract first-slice grasshopper export markers"
```

---

### Task 4: Python Envelope Persistence And Restricted Canonical Hash Verification

**Files:**

- Create: `mcp_server/src/rook/canvas_director.py`
- Create: `mcp_server/tests/test_canvas_director.py`

- [ ] **Step 1: Write Python tests for IDs, hashes, and collisions**

Create `mcp_server/tests/test_canvas_director.py`:

```python
from __future__ import annotations

import json

import pytest

from rook import canvas_director as cd


def _state(export_id="export_a"):
    return {
        "metadata_kind": "rook.canvas_director.export",
        "schema_version": 1,
        "export_id": export_id,
        "template_id": "canvas_director.basic_motion",
        "template_version": "0.1.0",
        "payload": {"timeline": {"fps": 24, "frame_count": 3}},
    }


def _envelope(state=None, diagnostics=None):
    state = state or _state()
    return {
        "canvas_export_state": state,
        "canvas_export_state_sha256": cd.canvas_export_state_sha256(state),
        "diagnostics": diagnostics or [],
        "suggested_spec_id": "spec_a",
        "read_only": True,
    }


def test_validate_id_accepts_safe_ids():
    assert cd.validate_canvas_director_id("export_01") == "export_01"


@pytest.mark.parametrize("bad", ["", "../x", "x/y", "x.y", "CON", "A", "-x"])
def test_validate_id_rejects_unsafe_ids(bad):
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.validate_canvas_director_id(bad)
    assert ei.value.code in {"invalid_export_id", "invalid_spec_id"}


def test_hash_is_independent_of_object_key_order():
    left = {"b": "2", "a": "1"}
    right = {"a": "1", "b": "2"}
    assert cd.canvas_export_state_sha256(left) == cd.canvas_export_state_sha256(right)


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"b": "2", "a": "1"}, b'{"a":"1","b":"2"}'),
        ({"text": "<>&", "list": [True, None, 3]}, b'{"list":[true,null,3],"text":"<>&"}'),
    ],
)
def test_canonical_json_bytes_match_managed_vectors(payload, expected):
    assert cd._canonical_json_bytes(payload) == expected


def test_canonical_json_rejects_non_integer_numbers():
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.canvas_export_state_sha256({"x": 1.25})
    assert ei.value.code == "invalid_input"


def test_save_export_persists_full_envelope(tmp_path):
    result = cd.save_canvas_export(tmp_path, _envelope(), export_id="export_a")
    path = result["export_path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload) == {
        "canvas_export_state",
        "canvas_export_state_sha256",
        "diagnostics",
        "suggested_spec_id",
        "read_only",
    }


def test_same_state_retry_is_idempotent_and_does_not_overwrite_diagnostics(tmp_path):
    first = _envelope(diagnostics=[{"code": "first"}])
    second = _envelope(diagnostics=[{"code": "second"}])
    cd.save_canvas_export(tmp_path, first, export_id="export_a")
    result = cd.save_canvas_export(tmp_path, second, export_id="export_a")
    persisted = json.loads(result["export_path"].read_text(encoding="utf-8"))
    assert result["idempotent"] is True
    assert persisted["diagnostics"] == [{"code": "first"}]


def test_different_state_same_export_id_fails_with_collision(tmp_path):
    cd.save_canvas_export(tmp_path, _envelope(_state("export_a")), export_id="export_a")
    changed = _state("export_a")
    changed["payload"]["timeline"]["frame_count"] = 4
    with pytest.raises(cd.CanvasDirectorError) as ei:
        cd.save_canvas_export(tmp_path, _envelope(changed), export_id="export_a")
    assert ei.value.code == "id_collision"


@pytest.mark.asyncio
async def test_extract_canvas_export_preserves_structured_solve_timeout():
    async def native(*args, **kwargs):
        return {"success": False, "data": {"code": "solve_timeout", "message": "timed out"}}

    with pytest.raises(cd.CanvasDirectorError) as ei:
        await cd.extract_canvas_export({"export_id": "export_a"}, call_native=native)
    assert ei.value.code == "solve_timeout"
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py -q
```

Expected: FAIL because `rook.canvas_director` does not exist.

- [ ] **Step 3: Implement Python CanvasDirector helpers**

Create `mcp_server/src/rook/canvas_director.py`:

```python
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .bridge import call_rhino

ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


class CanvasDirectorError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message

    def to_data(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message}


def validate_canvas_director_id(value: Any, *, kind: str = "export") -> str:
    code = "invalid_spec_id" if kind == "spec" else "invalid_export_id"
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise CanvasDirectorError(code, f"{kind}_id must match {ID_RE.pattern}")
    if value.lower() in RESERVED:
        raise CanvasDirectorError(code, f"{kind}_id uses a reserved filename token")
    return value


def _assert_restricted_canonical_subset(value: Any) -> None:
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int) and not isinstance(value, bool):
        return
    if isinstance(value, float):
        raise CanvasDirectorError("invalid_input", "CanvasDirector numeric values must be integers in slice one; encode decimals as strings.")
    if isinstance(value, list):
        for item in value:
            _assert_restricted_canonical_subset(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanvasDirectorError("invalid_input", "CanvasDirector object keys must be strings.")
            _assert_restricted_canonical_subset(item)
        return
    raise CanvasDirectorError("invalid_input", f"Unsupported CanvasDirector JSON value: {type(value).__name__}")


def _canonical_json_bytes(value: Any) -> bytes:
    _assert_restricted_canonical_subset(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def canvas_export_state_sha256(state: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(state)).hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
        Path(tmp_name).replace(path)
    except Exception:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        finally:
            raise


def _ensure_under(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    root_resolved = root.resolve()
    try:
        resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise CanvasDirectorError("project_root_missing", "Resolved path escaped project root") from exc
    return resolved


def _director_root(project_root: Path) -> Path:
    root = project_root.resolve() / ".rook" / "director"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _verify_envelope(envelope: dict[str, Any]) -> tuple[dict[str, Any], str]:
    state = envelope.get("canvas_export_state")
    if not isinstance(state, dict):
        raise CanvasDirectorError("export_hash_mismatch", "canvas_export_state must be an object")
    expected = envelope.get("canvas_export_state_sha256")
    actual = canvas_export_state_sha256(state)
    if expected != actual:
        raise CanvasDirectorError("export_hash_mismatch", "canvas_export_state_sha256 does not match state")
    if envelope.get("read_only") is not True:
        raise CanvasDirectorError("export_hash_mismatch", "CanvasDirector extraction envelope must have read_only true")
    return state, actual


def save_canvas_export(project_root: Path | str, envelope: dict[str, Any], *, export_id: str | None = None) -> dict[str, Any]:
    project = Path(project_root).resolve()
    state, state_hash = _verify_envelope(envelope)
    chosen_id = validate_canvas_director_id(export_id or state.get("export_id"), kind="export")
    path = _ensure_under(_director_root(project) / "exports" / f"{chosen_id}.json", project / ".rook" / "director")
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        existing_state, existing_hash = _verify_envelope(existing)
        if _canonical_json_bytes(existing_state) == _canonical_json_bytes(state) and existing_hash == state_hash:
            return {"export_id": chosen_id, "export_path": path, "canvas_export_state_sha256": state_hash, "idempotent": True}
        raise CanvasDirectorError("id_collision", f"export_id already exists with different state: {chosen_id}")
    try:
        _atomic_write_json(path, envelope)
    except OSError as exc:
        raise CanvasDirectorError("export_write_failed", str(exc)) from exc
    return {"export_id": chosen_id, "export_path": path, "canvas_export_state_sha256": state_hash, "idempotent": False}


async def extract_canvas_export(arguments: dict[str, Any], *, call_native=call_rhino, port: int | None = None) -> dict[str, Any]:
    body = dict(arguments)
    result = await call_native("/director/canvas/extract", "POST", body, port=port)
    if not result.get("success"):
        data = result.get("data")
        if isinstance(data, dict) and "code" in data:
            raise CanvasDirectorError(str(data["code"]), str(data.get("message", data["code"])))
        raise CanvasDirectorError("canvas_director_unavailable", str(data))
    data = result.get("data")
    if not isinstance(data, dict):
        raise CanvasDirectorError("export_hash_mismatch", "CanvasDirector extract response data must be an object")
    _verify_envelope(data)
    return data
```

- [ ] **Step 4: Run Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add mcp_server/src/rook/canvas_director.py mcp_server/tests/test_canvas_director.py
git commit -m "feat(canvas-director): persist extraction envelopes"
```

---

### Task 5: Compile CanvasExportState To DirectorAuthoringSpec And Compile-Motion Input

**Files:**

- Modify: `mcp_server/src/rook/canvas_director.py`
- Modify: `mcp_server/tests/test_canvas_director.py`

- [ ] **Step 1: Add compile tests for the narrow template family**

Append to `mcp_server/tests/test_canvas_director.py`:

```python
def test_compile_authoring_spec_maps_payload_to_durable_authoring_spec(tmp_path):
    state = _state()
    state["payload"] = {
        "timeline": {"fps": 24, "frame_count": 3},
        "resolution": {"width": 640, "height": 360},
        "groups": {"actor_a": ["11111111-1111-1111-1111-111111111111"]},
        "motion": [{"target": "actor_a", "keyframes": [{"t": 1.0, "translate": ["1.0", "0.0", "0.0"]}]}],
        "camera": {"strategy": "keyframes", "keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
    }
    spec = cd.compile_authoring_spec(_envelope(state), spec_id="spec_a")
    assert spec["metadata_kind"] == "director_authoring_spec"
    assert spec["schema_version"] == 1
    assert spec["spec_id"] == "spec_a"
    assert spec["timeline"] == {"fps": 24, "frame_count": 3}
    assert spec["motion"][0]["keyframes"][0]["translate"] == [1.0, 0.0, 0.0]


def test_build_compile_motion_request_is_runnable_compiler_shape(tmp_path):
    state = _state()
    state["payload"] = {
        "timeline": {"fps": 24, "frame_count": 3},
        "resolution": {"width": 640, "height": 360},
        "groups": {"actor_a": ["11111111-1111-1111-1111-111111111111"]},
        "motion": [{"target": "actor_a", "keyframes": [{"t": 1.0, "translate": ["1.0", "0.0", "0.0"]}]}],
        "camera": {"strategy": "keyframes", "keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
    }
    spec = cd.compile_authoring_spec(_envelope(state), spec_id="spec_a")
    request = cd.build_compile_motion_request(spec)
    assert set(request) >= {"timeline", "resolution", "groups", "motion", "camera"}
    assert "metadata_kind" not in request
    assert request["motion"][0]["target"] == "actor_a"
    assert request["timeline"]["frame_count"] == 3


@pytest.mark.asyncio
async def test_build_compile_motion_request_is_accepted_by_director_compiler(tmp_path):
    from rook import director_compiler
    object_id = "11111111-1111-1111-1111-111111111111"
    state = _state()
    state["payload"] = {
        "timeline": {"fps": 24, "frame_count": 3},
        "resolution": {"width": 640, "height": 360},
        "groups": {"actor_a": [object_id]},
        "motion": [{"target": "actor_a", "keyframes": [{"t": 1.0, "translate": ["1.0", "0.0", "0.0"]}]}],
        "camera": {"strategy": "keyframes", "keyframes": [{"frame_index": 1, "source": {"kind": "active_view"}}]},
    }
    spec = cd.compile_authoring_spec(_envelope(state), spec_id="spec_a")
    request = cd.build_compile_motion_request(spec)

    async def native(endpoint, method, data, *, port=None):
        if endpoint == "/director/object-states":
            return {
                "success": True,
                "data": {
                    "objects": [{
                        "object_id": object_id,
                        "bbox_min": [0, 0, 0],
                        "bbox_max": [2, 2, 2],
                        "state_hash": "state-a",
                    }],
                    "units": "Meters",
                },
            }
        if endpoint == "/director/view-state":
            return {
                "success": True,
                "data": {
                    "camera": {
                        "projection": "perspective",
                        "location": [0, -10, 5],
                        "target": [0, 0, 0],
                        "direction": [0, 1, 0],
                        "up": [0, 0, 1],
                        "lens_length": 35.0,
                        "fov_degrees": None,
                        "parallel_scale": None,
                        "near_clip": None,
                        "far_clip": None,
                        "aspect": 640 / 360,
                    },
                    "provenance": {"source": "active_view"},
                },
            }
        raise AssertionError(f"unexpected endpoint {endpoint}")

    compiled = await director_compiler.compile_motion(request, call_native=native)
    track = compiled["track"]
    assert track["frame_count"] == 3
    assert len(track["camera_frames"]) == 3
    assert len(track["object_frames"]) == 3
    assert track["animated_object_ids"] == [object_id]


def test_save_authoring_spec_writes_atomic_spec(tmp_path):
    spec = cd.compile_authoring_spec(_envelope(), spec_id="spec_a")
    result = cd.save_authoring_spec(tmp_path, spec, spec_id="spec_a")
    assert result["spec_path"].is_file()
    persisted = json.loads(result["spec_path"].read_text(encoding="utf-8"))
    assert persisted["metadata_kind"] == "director_authoring_spec"
```

- [ ] **Step 2: Run tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py -q
```

Expected: FAIL because compile and spec save helpers do not exist.

- [ ] **Step 3: Implement authoring-spec compilation**

Append to `mcp_server/src/rook/canvas_director.py`:

```python
def _number(value: Any) -> float:
    if isinstance(value, bool):
        raise CanvasDirectorError("spec_compile_failed", "boolean is not numeric")
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError as exc:
            raise CanvasDirectorError("spec_compile_failed", f"invalid numeric string: {value!r}") from exc
    raise CanvasDirectorError("spec_compile_failed", f"invalid numeric value: {value!r}")


def _convert_keyframes(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        if "translate" in item:
            item["translate"] = [_number(v) for v in item["translate"]]
        if "scale" in item:
            item["scale"] = _number(item["scale"])
        out.append(item)
    return out


def compile_authoring_spec(envelope: dict[str, Any], *, spec_id: str | None = None) -> dict[str, Any]:
    state, state_hash = _verify_envelope(envelope)
    payload = state.get("payload")
    if not isinstance(payload, dict):
        raise CanvasDirectorError("spec_compile_failed", "canvas_export_state.payload must be an object")
    chosen_spec_id = validate_canvas_director_id(spec_id or envelope.get("suggested_spec_id") or state.get("export_id"), kind="spec")
    motion = []
    for entry in payload.get("motion") or []:
        item = dict(entry)
        item["keyframes"] = _convert_keyframes(list(item.get("keyframes") or []))
        motion.append(item)
    return {
        "metadata_kind": "director_authoring_spec",
        "schema_version": 1,
        "spec_id": chosen_spec_id,
        "source": {
            "canvas_export_state_sha256": state_hash,
            "export_id": state.get("export_id"),
            "template_id": state.get("template_id"),
            "template_version": state.get("template_version"),
        },
        "timeline": payload.get("timeline"),
        "resolution": payload.get("resolution") or {"width": 1920, "height": 1080},
        "groups": payload.get("groups") or {},
        "motion": motion,
        "camera": payload.get("camera"),
    }


def save_authoring_spec(project_root: Path | str, spec: dict[str, Any], *, spec_id: str | None = None, replace: bool = False) -> dict[str, Any]:
    project = Path(project_root).resolve()
    chosen_id = validate_canvas_director_id(spec_id or spec.get("spec_id"), kind="spec")
    root = _director_root(project)
    path = _ensure_under(root / "specs" / f"{chosen_id}.json", root)
    if path.exists() and not replace:
        existing = json.loads(path.read_text(encoding="utf-8"))
        if _canonical_json_bytes(existing) != _canonical_json_bytes(spec):
            raise CanvasDirectorError("id_collision", f"spec_id already exists with different spec: {chosen_id}")
        return {"spec_id": chosen_id, "spec_path": path, "idempotent": True}
    try:
        _atomic_write_json(path, spec)
    except OSError as exc:
        raise CanvasDirectorError("spec_write_failed", str(exc)) from exc
    return {"spec_id": chosen_id, "spec_path": path, "idempotent": False}


def build_compile_motion_request(spec: dict[str, Any]) -> dict[str, Any]:
    if spec.get("metadata_kind") != "director_authoring_spec":
        raise CanvasDirectorError("spec_compile_failed", "metadata_kind must be director_authoring_spec")
    motion = spec.get("motion")
    if not isinstance(motion, list) or not motion:
        raise CanvasDirectorError("spec_compile_failed", "DirectorAuthoringSpec.motion must be a non-empty array")
    timeline = spec.get("timeline")
    if not isinstance(timeline, dict):
        raise CanvasDirectorError("spec_compile_failed", "DirectorAuthoringSpec.timeline must be an object")
    request = {
        "timeline": timeline,
        "resolution": spec.get("resolution") or {"width": 1920, "height": 1080},
        "groups": spec.get("groups") or {},
        "motion": motion,
    }
    if isinstance(spec.get("camera"), dict):
        request["camera"] = spec["camera"]
    if isinstance(spec.get("default_easing"), str):
        request["default_easing"] = spec["default_easing"]
    return request
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add mcp_server/src/rook/canvas_director.py mcp_server/tests/test_canvas_director.py
git commit -m "feat(canvas-director): compile authoring specs to motion requests"
```

---

### Task 6: Capture Compiled Track As Director Run Artifacts

**Files:**

- Modify: `mcp_server/src/rook/director.py`
- Modify: `mcp_server/src/rook/canvas_director.py`
- Modify: `mcp_server/tests/test_director.py`
- Modify: `mcp_server/tests/test_canvas_director.py`

- [ ] **Step 1: Add compiled-track run artifact tests**

Append to `mcp_server/tests/test_director.py`:

```python
def _compiled_track():
    camera = {
        "projection": "perspective",
        "location": [0, -10, 5],
        "target": [0, 0, 0],
        "direction": [0, 1, 0],
        "up": [0, 0, 1],
        "lens_length": 35.0,
        "fov_degrees": None,
        "parallel_scale": None,
        "near_clip": None,
        "far_clip": None,
        "aspect": 16 / 9,
    }
    return {
        "transform_semantics": "absolute_from_source",
        "fps": 24,
        "frame_count": 2,
        "animated_object_ids": ["11111111-1111-1111-1111-111111111111"],
        "camera_frames": [
            {"frame_index": 1, "camera": camera},
            {"frame_index": 2, "camera": camera},
        ],
        "object_frames": [
            {
                "frame_index": 1,
                "object_transforms": [{
                    "object_id": "11111111-1111-1111-1111-111111111111",
                    "source_state": {"bbox_min": [0, 0, 0], "bbox_max": [1, 1, 1], "state_hash": "s1"},
                    "transform": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                }],
            },
            {
                "frame_index": 2,
                "object_transforms": [{
                    "object_id": "11111111-1111-1111-1111-111111111111",
                    "source_state": {"bbox_min": [0, 0, 0], "bbox_max": [1, 1, 1], "state_hash": "s1"},
                    "transform": [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]],
                }],
            },
        ],
    }


@pytest.mark.asyncio
async def test_run_compiled_track_writes_manifest_frames_inputs_and_evidence(tmp_path):
    from rook import director
    spec = {"metadata_kind": "director_authoring_spec", "schema_version": 1, "spec_id": "spec_a"}
    native = FakeNative(
        [
            {"success": True, "data": {"frame_index": 1}},
            {"success": True, "data": {"frame_index": 2}},
        ],
        create_outputs=True,
    )
    out = await director.run_compiled_track(
        {
            "track": _compiled_track(),
            "resolution": {"width": 320, "height": 180},
            "display": {"mode": "Rendered"},
            "output_root": str(tmp_path / "data" / "rookvision_director" / "canvas_runs"),
            "run_id": "compiled-track-a",
            "run_inputs": {
                "director_authoring_spec": spec,
                "provenance": {
                    "source_spec_id": "spec_a",
                    "canvas_export_state_sha256": "def",
                    "template_version": "0.1.0",
                },
            },
            "compile_provenance": {"frame_count": 2, "fps": 24},
        },
        call_native=native,
        runtime=_runtime(tmp_path),
    )
    assert out["state"] == "complete"
    run_root = Path(out["run_root"])
    assert (run_root / "inputs" / "director_authoring_spec.json").is_file()
    assert (run_root / "inputs" / "provenance.json").is_file()
    provenance = json.loads((run_root / "inputs" / "provenance.json").read_text(encoding="utf-8"))
    assert provenance["source_spec_sha256"] == provenance["copied_spec_sha256"]
    manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["motion"]["strategy"] == "compiled_track"
    assert manifest["frame_count"] == 2
    assert len(manifest["frames"]) == 2
    assert (run_root / "frames" / "frame_0001.png").is_file()
    assert (run_root / "logs" / "frame_evidence.jsonl").is_file()


def test_validate_run_inputs_rejects_malformed_inputs():
    from rook import director
    with pytest.raises(director.DirectorInputError):
        director._validate_run_inputs({"provenance": {}})


def test_write_run_inputs_rejects_conflicting_source_spec_hash(tmp_path):
    from rook import director
    spec = {"metadata_kind": "director_authoring_spec", "schema_version": 1, "spec_id": "spec_a"}
    with pytest.raises(director.DirectorInputError):
        director._write_run_inputs(
            tmp_path,
            director_authoring_spec=spec,
            provenance={"source_spec_sha256": "not-the-copied-spec"},
        )
    assert not (tmp_path / "inputs").exists()


@pytest.mark.parametrize(
    "mutate",
    [
        lambda track: track["camera_frames"][0].pop("frame_index"),
        lambda track: track["camera_frames"][0].__setitem__("frame_index", "one"),
        lambda track: track["camera_frames"][1].__setitem__("frame_index", 1),
        lambda track: track["object_frames"].pop(),
    ],
)
def test_indexed_track_frames_rejects_bad_frame_indexes(mutate):
    from rook import director
    track = _compiled_track()
    mutate(track)
    with pytest.raises(director.DirectorInputError):
        director._indexed_track_frames(track, 2)


@pytest.mark.asyncio
async def test_run_compiled_track_rejects_bad_resolution_before_creating_run(tmp_path):
    from rook import director
    request = {
        "track": _compiled_track(),
        "resolution": {"width": 0, "height": 180},
        "output_root": str(tmp_path / "data" / "rookvision_director" / "canvas_runs"),
        "run_id": "bad-resolution",
    }
    with pytest.raises(director.DirectorInputError):
        await director.run_compiled_track(request, call_native=FakeNative([]), runtime=_runtime(tmp_path))
    assert not (tmp_path / "data" / "rookvision_director" / "canvas_runs" / "bad-resolution").exists()


@pytest.mark.asyncio
async def test_run_compiled_track_rejects_conflicting_provenance_before_creating_run(tmp_path):
    from rook import director
    spec = {"metadata_kind": "director_authoring_spec", "schema_version": 1, "spec_id": "spec_a"}
    request = {
        "track": _compiled_track(),
        "resolution": {"width": 320, "height": 180},
        "output_root": str(tmp_path / "data" / "rookvision_director" / "canvas_runs"),
        "run_id": "bad-provenance",
        "run_inputs": {
            "director_authoring_spec": spec,
            "provenance": {"source_spec_sha256": "not-the-copied-spec"},
        },
    }
    with pytest.raises(director.DirectorInputError):
        await director.run_compiled_track(request, call_native=FakeNative([]), runtime=_runtime(tmp_path))
    assert not (tmp_path / "data" / "rookvision_director" / "canvas_runs" / "bad-provenance").exists()


@pytest.mark.parametrize("bad_run_id", ["../escape", "/tmp/escape", "C:/escape", "bad/slash", "", ".", "..", "bad.name", "_bad"])
@pytest.mark.asyncio
async def test_run_compiled_track_rejects_bad_run_id_before_creating_run(tmp_path, bad_run_id):
    from rook import director
    request = {
        "track": _compiled_track(),
        "resolution": {"width": 320, "height": 180},
        "output_root": str(tmp_path / "data" / "rookvision_director" / "canvas_runs"),
        "run_id": bad_run_id,
    }
    with pytest.raises(director.DirectorInputError):
        await director.run_compiled_track(request, call_native=FakeNative([]), runtime=_runtime(tmp_path))
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "data" / "rookvision_director" / "canvas_runs").exists()


@pytest.mark.parametrize("field,value", [("frame_count", "two"), ("frame_count", 0), ("fps", None), ("fps", -1)])
@pytest.mark.asyncio
async def test_run_compiled_track_rejects_bad_track_positive_ints(tmp_path, field, value):
    from rook import director
    track = _compiled_track()
    track[field] = value
    request = {
        "track": track,
        "resolution": {"width": 320, "height": 180},
        "output_root": str(tmp_path / "data" / "rookvision_director" / "canvas_runs"),
        "run_id": "bad-positive-int",
    }
    with pytest.raises(director.DirectorInputError):
        await director.run_compiled_track(request, call_native=FakeNative([]), runtime=_runtime(tmp_path))
    assert not (tmp_path / "data" / "rookvision_director" / "canvas_runs" / "bad-positive-int").exists()
```

- [ ] **Step 2: Run the specific test and confirm it fails**

Run:

```powershell
python -m pytest mcp_server/tests/test_director.py::test_run_compiled_track_writes_manifest_frames_inputs_and_evidence mcp_server/tests/test_director.py::test_validate_run_inputs_rejects_malformed_inputs mcp_server/tests/test_director.py::test_write_run_inputs_rejects_conflicting_source_spec_hash mcp_server/tests/test_director.py::test_indexed_track_frames_rejects_bad_frame_indexes mcp_server/tests/test_director.py::test_run_compiled_track_rejects_bad_resolution_before_creating_run mcp_server/tests/test_director.py::test_run_compiled_track_rejects_conflicting_provenance_before_creating_run mcp_server/tests/test_director.py::test_run_compiled_track_rejects_bad_run_id_before_creating_run mcp_server/tests/test_director.py::test_run_compiled_track_rejects_bad_track_positive_ints -q
```

Expected: FAIL because `run_compiled_track`, `_write_run_inputs`, `_validate_run_inputs`, `_prepare_run_inputs`, `_indexed_track_frames`, `_validate_director_resolution`, `_resolve_run_root`, and `_positive_int_field` do not exist.

- [ ] **Step 3: Add run evidence input helpers to Director runner**

In `mcp_server/src/rook/director.py`, add near `_atomic_write_json`:

```python
import hashlib
```

`director.py` already imports `re`; reuse that import for `_RUN_ID_RE`.

Add helper:

```python
def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sha256_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _prepare_run_inputs(
    director_authoring_spec: dict[str, Any],
    provenance: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    copied_spec_sha256 = _sha256_payload(director_authoring_spec)
    full_provenance = dict(provenance)
    existing_source_hash = full_provenance.get("source_spec_sha256")
    if existing_source_hash is not None and existing_source_hash != copied_spec_sha256:
        raise DirectorInputError("run_inputs.provenance.source_spec_sha256 does not match copied director_authoring_spec")
    full_provenance["source_spec_sha256"] = copied_spec_sha256
    full_provenance["copied_spec_sha256"] = copied_spec_sha256
    return director_authoring_spec, full_provenance


def _write_run_inputs(
    run_root: Path,
    *,
    director_authoring_spec: dict[str, Any],
    provenance: dict[str, Any],
) -> dict[str, Any]:
    director_authoring_spec, full_provenance = _prepare_run_inputs(director_authoring_spec, provenance)
    copied_spec_sha256 = full_provenance["copied_spec_sha256"]
    inputs_dir = run_root / "inputs"
    _atomic_write_json(inputs_dir / "director_authoring_spec.json", director_authoring_spec)
    _atomic_write_json(inputs_dir / "provenance.json", full_provenance)
    return {"copied_spec_sha256": copied_spec_sha256}


def _validate_run_inputs(run_inputs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(run_inputs, dict):
        raise DirectorInputError("run_inputs must be an object when provided")
    director_authoring_spec = run_inputs.get("director_authoring_spec")
    if not isinstance(director_authoring_spec, dict):
        raise DirectorInputError("run_inputs.director_authoring_spec must be an object")
    provenance = run_inputs.get("provenance")
    if provenance is None:
        provenance = {}
    if not isinstance(provenance, dict):
        raise DirectorInputError("run_inputs.provenance must be an object when provided")
    return director_authoring_spec, provenance
```

- [ ] **Step 4: Add compiled-track run capture helper**

Add helpers near `run_director` in `mcp_server/src/rook/director.py`:

```python
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _positive_int_field(value: Any, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise DirectorInputError(f"{field} must be a positive integer")
    if value < 1:
        raise DirectorInputError(f"{field} must be a positive integer")
    return value


def _resolve_run_root(output_root: Path, run_id: Any) -> tuple[str, Path]:
    if run_id is None:
        run_id = (
            f"director_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_"
            f"{uuid.uuid4().hex[:8]}"
        )
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise DirectorInputError("run_id must be a 1..128 char [A-Za-z0-9][A-Za-z0-9_-]* token")
    run_root = (output_root / run_id).resolve()
    if run_root == output_root or not _is_relative_to(run_root, output_root):
        raise DirectorInputError("run_id must resolve to a child directory under output_root")
    return run_id, run_root


def _track_frame_index(frame: Any, *, kind: str) -> int:
    if not isinstance(frame, dict):
        raise DirectorInputError(f"compiled track {kind} frame must be an object")
    raw = frame.get("frame_index")
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise DirectorInputError(f"compiled track {kind} frame_index must be an integer")
    return raw


def _indexed_track_frames(track: dict[str, Any], frame_count: int) -> tuple[dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    camera_frames = track.get("camera_frames")
    object_frames = track.get("object_frames")
    if not isinstance(camera_frames, list) or not isinstance(object_frames, list):
        raise DirectorInputError("compiled track requires camera_frames and object_frames arrays")
    cameras: dict[int, dict[str, Any]] = {}
    for frame in camera_frames:
        index = _track_frame_index(frame, kind="camera")
        if index in cameras:
            raise DirectorInputError("compiled track contains duplicate camera frame_index")
        cameras[index] = frame
    objects: dict[int, dict[str, Any]] = {}
    for frame in object_frames:
        index = _track_frame_index(frame, kind="object")
        if index in objects:
            raise DirectorInputError("compiled track contains duplicate object frame_index")
        objects[index] = frame
    expected = set(range(1, frame_count + 1))
    if len(cameras) != frame_count or len(objects) != frame_count or set(cameras) != expected or set(objects) != expected:
        raise DirectorInputError("compiled track frame indexes must exactly cover 1..frame_count")
    for index in expected:
        if not isinstance(cameras[index].get("camera"), dict):
            raise DirectorInputError("compiled track camera frame missing camera object")
        if not isinstance(objects[index].get("object_transforms"), list):
            raise DirectorInputError("compiled track object frame missing object_transforms array")
    return cameras, objects


def _validate_director_resolution(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise DirectorInputError("resolution must be an object")
    try:
        width = int(value.get("width", 0))
        height = int(value.get("height", 0))
    except (TypeError, ValueError) as exc:
        raise DirectorInputError("resolution width and height must be positive") from exc
    if width <= 0 or height <= 0:
        raise DirectorInputError("resolution width and height must be positive")
    return {"width": width, "height": height}


async def _capture_manifest_frames(
    *,
    call_native,
    port: int | None,
    run_id: str,
    run_root: Path,
    resolution: dict[str, Any],
    display: dict[str, Any],
    manifest_frames: list[dict[str, Any]],
    should_cancel,
) -> str:
    state = "complete"
    evidence_path = run_root / "logs" / "frame_evidence.jsonl"
    should_cancel = should_cancel or (lambda: False)
    for frame in manifest_frames:
        if should_cancel():
            return "cancelled"
        instruction = {
            "schema_version": SCHEMA_VERSION,
            "director_version": DIRECTOR_VERSION,
            "run_id": run_id,
            "frame_index": frame["frame_index"],
            "frame_id": frame["frame_id"],
            "run_root": str(run_root),
            "output_path": frame["output_path"],
            "resolution": resolution,
            "display": display,
            "camera": frame["camera"],
            "object_transforms": frame["object_transforms"],
        }
        result = await call_native("/director/frame-capture", "POST", instruction, port=port)
        evidence = result.get("data") if isinstance(result.get("data"), dict) else {"error": result.get("data")}
        evidence["success"] = bool(result.get("success"))
        output_path = Path(frame["output_path"])
        if result.get("success") and (not output_path.exists() or output_path.stat().st_size <= 0):
            evidence["success"] = False
            evidence["error"] = {"code": "missing_output", "message": f"Expected frame output was not created: {output_path}"}
        try:
            _append_evidence(evidence_path, evidence)
        except OSError:
            return "evidence_failed"
        if evidence.get("dirty_partial_state"):
            return "unsafe_failed"
        if not result.get("success") or not evidence["success"]:
            state = "failed"
            break
    return state
```

Then add:

```python
async def run_compiled_track(
    request: dict[str, Any],
    *,
    call_native=call_rhino,
    runtime: DirectorRuntimePaths | None = None,
    port: int | None = None,
    should_cancel=None,
) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise DirectorInputError("compiled track run request must be an object")
    track = request.get("track")
    if not isinstance(track, dict):
        raise DirectorInputError("track must be an object")
    frame_count = _positive_int_field(track.get("frame_count"), field="track.frame_count")
    fps = _positive_int_field(track.get("fps"), field="track.fps")
    resolution = _validate_director_resolution(request.get("resolution") or {"width": 1920, "height": 1080})
    display = request.get("display") or {"mode": "Rendered"}
    if not isinstance(display, dict):
        raise DirectorInputError("display must be an object")
    cameras, objects = _indexed_track_frames(track, frame_count)
    run_inputs = None
    if "run_inputs" in request:
        director_authoring_spec, provenance = _validate_run_inputs(request["run_inputs"])
        run_inputs = _prepare_run_inputs(director_authoring_spec, provenance)

    runtime = runtime or _runtime_paths()
    output_root = resolve_output_root(request.get("output_root"), runtime)
    run_id, run_root = _resolve_run_root(output_root, request.get("run_id"))
    frames_dir = run_root / "frames"
    logs_dir = run_root / "logs"
    frames_dir.mkdir(parents=True, exist_ok=False)
    logs_dir.mkdir(parents=True, exist_ok=True)
    if run_inputs is not None:
        director_authoring_spec, provenance = run_inputs
        _write_run_inputs(run_root, director_authoring_spec=director_authoring_spec, provenance=provenance)

    manifest_frames = []
    for index in range(1, frame_count + 1):
        frame_name = _frame_id(index)
        manifest_frames.append({
            "frame_index": index,
            "frame_id": frame_name,
            "camera": cameras[index]["camera"],
            "object_transforms": objects[index]["object_transforms"],
            "output_path": str((frames_dir / f"{frame_name}.png").resolve()),
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "director_version": DIRECTOR_VERSION,
        "run_id": run_id,
        "run_root": str(run_root),
        "output_root": str(output_root),
        "created_at": _utc_now(),
        "frame_count": frame_count,
        "timeline": {"fps": fps, "frame_count": frame_count},
        "motion": {
            "strategy": "compiled_track",
            "transform_semantics": track.get("transform_semantics"),
            "animated_object_ids": list(track.get("animated_object_ids") or []),
            "provenance": request.get("compile_provenance") or {},
        },
        "camera_plan": {"strategy": "compiled_track"},
        "resolution": resolution,
        "display": display,
        "frames": manifest_frames,
        "exclusions": ["true_depth", "edge_pass", "rookvision_artifact_handoff", "grasshopper_nle"],
    }
    _atomic_write_json(run_root / "manifest.json", manifest)
    _atomic_write_json(run_root / "status.json", {"state": "running", "run_id": run_id, "updated_at": _utc_now()})
    state = await _capture_manifest_frames(
        call_native=call_native,
        port=port,
        run_id=run_id,
        run_root=run_root,
        resolution=resolution,
        display=display,
        manifest_frames=manifest_frames,
        should_cancel=should_cancel,
    )
    summary = {"state": state, "run_id": run_id, "run_root": str(run_root), "updated_at": _utc_now()}
    _atomic_write_json(run_root / "status.json", summary)
    return summary
```

- [ ] **Step 5: Add CanvasDirector end-to-end prep helper tests**

Append to `mcp_server/tests/test_canvas_director.py`:

```python
def test_build_run_inputs_uses_spec_and_export_hash():
    envelope = _envelope()
    spec = cd.compile_authoring_spec(envelope, spec_id="spec_a")
    run_inputs = cd.build_run_inputs(envelope, spec)
    assert run_inputs["director_authoring_spec"] == spec
    assert run_inputs["provenance"]["source_spec_id"] == "spec_a"
    assert run_inputs["provenance"]["canvas_export_state_sha256"] == envelope["canvas_export_state_sha256"]
```

- [ ] **Step 6: Implement CanvasDirector run input helper**

Append to `mcp_server/src/rook/canvas_director.py`:

```python
def build_run_inputs(envelope: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    _state, state_hash = _verify_envelope(envelope)
    return {
        "director_authoring_spec": spec,
        "provenance": {
            "source_spec_id": spec.get("spec_id"),
            "source_spec_sha256": hashlib.sha256(_canonical_json_bytes(spec)).hexdigest(),
            "canvas_export_state_sha256": state_hash,
            "template_version": (spec.get("source") or {}).get("template_version"),
        },
    }
```

- [ ] **Step 7: Run Python tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director.py::test_run_compiled_track_writes_manifest_frames_inputs_and_evidence mcp_server/tests/test_director.py::test_validate_run_inputs_rejects_malformed_inputs mcp_server/tests/test_director.py::test_write_run_inputs_rejects_conflicting_source_spec_hash mcp_server/tests/test_director.py::test_run_compiled_track_rejects_conflicting_provenance_before_creating_run mcp_server/tests/test_canvas_director.py -q
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

Run:

```powershell
git add mcp_server/src/rook/director.py mcp_server/src/rook/canvas_director.py mcp_server/tests/test_director.py mcp_server/tests/test_canvas_director.py
git commit -m "feat(canvas-director): capture compiled tracks as director runs"
```

---

### Task 7: MCP Tooling And First Slice Orchestration

**Files:**

- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_groups.py`
- Modify: `mcp_server/tests/test_director_mcp_tools.py`
- Modify: `mcp_server/tests/test_canvas_director.py`

- [ ] **Step 1: Add MCP registration tests**

Append to `mcp_server/tests/test_director_mcp_tools.py`:

```python
@pytest.mark.asyncio
async def test_canvas_director_extract_tool_registered():
    tools = await server.list_tools()
    by_name = {tool.name: tool for tool in tools}
    assert "rhino_director_canvas_extract" in by_name
    schema = by_name["rhino_director_canvas_extract"].inputSchema
    assert schema["type"] == "object"
    assert schema["required"] == ["project_root"]
    assert "export_id" in schema["properties"]
    assert "spec_id" in schema["properties"]
    assert "solve_mode" in schema["properties"]
    assert _find_rejected_schema_keywords(schema) == []


def test_canvas_director_extract_tool_in_director_group_only():
    assert "rhino_director_canvas_extract" in tool_groups.TOOL_GROUPS["director"]
    assert "rhino_director_canvas_extract" not in tool_groups.TOOL_GROUPS["director_readonly"]


@pytest.mark.asyncio
async def test_canvas_director_extract_dispatches_to_python(monkeypatch, tmp_path):
    envelope = {
        "canvas_export_state": {
            "metadata_kind": "rook.canvas_director.export",
            "schema_version": 1,
            "export_id": "export_a",
            "template_id": "canvas_director.basic_motion",
            "template_version": "0.1.0",
            "payload": {"timeline": {"fps": 24, "frame_count": 3}},
        },
        "diagnostics": [],
        "suggested_spec_id": "spec_a",
        "read_only": True,
    }
    from rook import canvas_director
    envelope["canvas_export_state_sha256"] = canvas_director.canvas_export_state_sha256(envelope["canvas_export_state"])

    async def fake_extract(arguments, *, port=None):
        return {
            "export": {"export_id": "export_a", "export_path": str(tmp_path / "export_a.json")},
            "spec": {"spec_id": "spec_a", "spec_path": str(tmp_path / "spec_a.json")},
            "canvas_export_state_sha256": envelope["canvas_export_state_sha256"],
            "compile_motion_request": {"timeline": {"fps": 24, "frame_count": 3}, "motion": []},
        }

    monkeypatch.setattr(server.canvas_director, "extract_persist_and_compile", fake_extract)
    result = await server.call_tool("rhino_director_canvas_extract", {"project_root": str(tmp_path), "export_id": "export_a"})
    payload = json.loads(result[0].text)
    assert payload["export"]["export_id"] == "export_a"
    assert "compile_motion_request" in payload
```

- [ ] **Step 2: Run tool tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q -k "canvas_director"
```

Expected: FAIL because the MCP tool is not registered.

- [ ] **Step 3: Add orchestration helper**

Append to `mcp_server/src/rook/canvas_director.py`:

```python
async def extract_persist_and_compile(arguments: dict[str, Any], *, port: int | None = None) -> dict[str, Any]:
    project_root = arguments.get("project_root")
    if not project_root:
        raise CanvasDirectorError("project_root_missing", "project_root is required")
    extract_args = {
        key: value
        for key, value in arguments.items()
        if key in {"export_id", "solve_mode", "expected_solution_token", "document_id", "proposal_id"}
    }
    envelope = await extract_canvas_export(extract_args, port=port)
    export_result = save_canvas_export(project_root, envelope, export_id=arguments.get("export_id"))
    spec = compile_authoring_spec(envelope, spec_id=arguments.get("spec_id"))
    spec_result = save_authoring_spec(project_root, spec, spec_id=spec["spec_id"], replace=bool(arguments.get("replace_spec")))
    return {
        "export": {
            "export_id": export_result["export_id"],
            "export_path": str(export_result["export_path"]),
            "idempotent": export_result["idempotent"],
        },
        "spec": {
            "spec_id": spec_result["spec_id"],
            "spec_path": str(spec_result["spec_path"]),
            "idempotent": spec_result["idempotent"],
        },
        "canvas_export_state_sha256": export_result["canvas_export_state_sha256"],
        "compile_motion_request": build_compile_motion_request(spec),
    }
```

- [ ] **Step 4: Register the MCP tool schema**

In `mcp_server/src/rook/server.py`, add `canvas_director` to the import line:

```python
from . import artifacts, canvas_director, director, director_actor_metadata, director_compiler, director_preview, director_publish, director_video, merge_execution, script_library, targeting, workbench, work_units
```

Add a `Tool(...)` near other Director tools:

```python
Tool(
    name="rhino_director_canvas_extract",
    description="Extract declared CanvasDirector exports from the active Grasshopper canvas, persist the extraction envelope under project .rook/director/exports, compile a reusable DirectorAuthoringSpec under .rook/director/specs, and return the runnable director_compiler.compile_motion request.",
    inputSchema={
        "type": "object",
        "required": ["project_root"],
        "properties": {
            "project_root": {"type": "string", "description": "Project root containing the .rook directory to write under."},
            "export_id": {"type": "string", "description": "Optional strict export id matching ^[a-z0-9][a-z0-9_-]{0,79}$."},
            "spec_id": {"type": "string", "description": "Optional strict spec id matching ^[a-z0-9][a-z0-9_-]{0,79}$."},
            "solve_mode": {"type": "string", "description": "require_fresh_solve by default; reuse_verified_solution requires expected_solution_token."},
            "expected_solution_token": {"type": "string", "description": "Freshness token required by reuse_verified_solution."},
            "document_id": {"type": "string", "description": "Optional GH/Rhino document identity for extraction validation."},
            "proposal_id": {"type": "string", "description": "Optional CanvasProposal identity for extraction validation."},
            "replace_spec": {"type": "boolean", "description": "True permits replacing an existing spec with the same spec_id."},
        },
    },
),
```

Add a call-tool case near other Director cases:

```python
        case "rhino_director_canvas_extract":
            try:
                result = {
                    "success": True,
                    "data": await canvas_director.extract_persist_and_compile(arguments, port=port),
                }
            except canvas_director.CanvasDirectorError as exc:
                result = {"success": False, "data": exc.to_data()}
```

- [ ] **Step 5: Add tool group membership**

In `mcp_server/src/rook/agent/tool_groups.py`, add `"rhino_director_canvas_extract"` to the `director` group. Do not add it to `director_readonly` because it writes project artifacts.

- [ ] **Step 6: Run MCP tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_director_mcp_tools.py -q -k "canvas_director"
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

Run:

```powershell
git add mcp_server/src/rook/server.py mcp_server/src/rook/agent/tool_groups.py mcp_server/src/rook/canvas_director.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_canvas_director.py
git commit -m "feat(canvas-director): expose extract persistence tool"
```

---

### Task 8: Verification And Live Smoke

**Files:**

- Modify only if a verification failure exposes a real bug in files touched by Tasks 1-7.

- [ ] **Step 1: Run managed source/unit tests**

Run:

```powershell
dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "CanvasDirector|NativeDirectorCanvasDispatchSourceTests|Registrar_DeclaresCanvasDirectorDispatchCallback"
```

Expected: PASS.

- [ ] **Step 2: Run Python unit tests**

Run:

```powershell
python -m pytest mcp_server/tests/test_canvas_director.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director.py -q -k "canvas_director or run_compiled_track or validate_run_inputs"
```

Expected: PASS.

- [ ] **Step 3: Run a focused live route smoke with Rhino/GH open**

Prerequisite: Rhino and Grasshopper are open with a proposal component whose nickname is `CanvasDirector Export:export_a` and whose first output is the declared JSON export string.

Run through MCP or direct Python:

```powershell
@'
import asyncio, json
from rook import canvas_director

async def main():
    result = await canvas_director.extract_persist_and_compile({
        "project_root": r"C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2",
        "export_id": "export_a",
        "spec_id": "spec_a",
        "solve_mode": "require_fresh_solve",
    })
    print(json.dumps(result, indent=2))

asyncio.run(main())
'@ | python -
```

Expected: JSON response contains `export.export_path`, `spec.spec_path`, `canvas_export_state_sha256`, and `compile_motion_request`. Files exist under `C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2\.rook\director\exports` and `...\specs`.

- [ ] **Step 4: Run Director compile-motion, frame capture, and video path after compiling a valid spec**

Use the generated spec to call the existing Director compiler, capture the compiled track through `/director/frame-capture`, and assemble video. Do not pass `DirectorAuthoringSpec` directly to `director.run_director()`: that route expects the older top-level `object_ids`/`frame_count` capture request shape. If the first live export is only an extraction proof and not yet a valid motion/camera payload, record that as a planned follow-up in `C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\.rook\director_planning\TOOLING_GAPS_AND_ISSUES.md` instead of weakening tests.

Command shape once a valid spec is present:

```powershell
@'
import asyncio, json
from pathlib import Path
from rook import canvas_director, director, director_compiler, director_video

async def main():
    project = Path(r"C:\Users\bring\OneDrive\Desktop\Pearson\ANIMATION\V2")
    envelope = json.loads((project / ".rook" / "director" / "exports" / "export_a.json").read_text(encoding="utf-8"))
    spec = json.loads((project / ".rook" / "director" / "specs" / "spec_a.json").read_text(encoding="utf-8"))
    compile_request = canvas_director.build_compile_motion_request(spec)
    compiled = await director_compiler.compile_motion(compile_request)
    run = await director.run_compiled_track({
        "track": compiled["track"],
        "resolution": compile_request["resolution"],
        "display": {"mode": "Rendered"},
        "run_inputs": canvas_director.build_run_inputs(envelope, spec),
        "compile_provenance": compiled["provenance"],
    })
    video = await director_video.assemble_director_video({"run_root": run["run_root"]})
    print(json.dumps({"compile": compiled["provenance"], "run": run, "video": video}, indent=2))

asyncio.run(main())
'@ | python -
```

Expected: compile provenance includes `frame_count`, `fps`, and `animated_object_ids`; `run.state` is `complete`; `video.state` is `complete`; the run directory is under the configured Director output root and contains `inputs/director_authoring_spec.json`, `inputs/provenance.json`, `manifest.json`, `frames`, `logs/frame_evidence.jsonl`, and `video_manifest.json`. Only pass `output_root` here when it is under `ROOK_DIRECTOR_OUTPUT_ROOT`.

- [ ] **Step 5: Run repo status check**

Run:

```powershell
git status --short --branch
```

Expected: clean branch ahead of `origin/main` by the task commits.

- [ ] **Step 6: Final commit if verification required fixes**

If Step 1-4 required fixes, commit them:

```powershell
git add <files changed by verification fixes>
git commit -m "fix(canvas-director): address verification findings"
```

If no fixes were needed, do not create an empty commit.

---

## Self-Review Checklist

- Spec coverage:
  - Native route/facade: Task 1.
  - Managed side-effect-free extraction envelope: Tasks 2-3.
  - Envelope hash excludes envelope fields: Tasks 2 and 4.
  - Export envelope persistence, idempotent retry behavior, and collision behavior: Task 4.
  - Project spec persistence: Task 5.
  - Run evidence input/provenance split: Task 6.
  - MCP orchestration: Task 7.
  - Live smoke: Task 8.
- Type consistency:
  - `canvas_export_state_sha256` is the field name in C#, Python, tests, and evidence.
  - Managed envelope properties use explicit `JsonPropertyName` attributes and bridge-shape tests so the existing camelCase bridge options cannot rewrite them.
  - `run_directory` maps to existing Director `run_root` values in Python outputs; no `<run_root>/<run_id>` nesting is introduced.
  - `require_fresh_solve`, `reuse_verified_solution`, `freshness_token_required`, `solution_stale`, and `unsupported_solve_mode` match the spec.
  - `solve_timeout` is returned as structured CanvasDirector error data on bridge timeout, not remapped to `canvas_director_unavailable`.
  - `require_fresh_solve` performs and verifies a fresh GH solution before reading outputs; `document_id` and `proposal_id` are parsed and validated.
  - Native pre-bridge failures return structured `{ code, message }` data, not stringly error messages.
  - Canonical hashing is a restricted RFC 8785/JCS-compatible subset with shared C#/Python test vectors.
  - Nickname-based export discovery is labeled as a temporary first-slice harness, while payload metadata remains the declared export contract.
  - Duplicate matching export markers fail with `multiple_exports_ambiguous` even when `export_id` is explicit.
  - `DirectorAuthoringSpec` is not passed directly to `director.run_director`; `build_compile_motion_request()` feeds `director_compiler.compile_motion()`, then `director.run_compiled_track()` captures standard Director run artifacts.
  - `run_inputs` are optional, but malformed present `run_inputs` fail fast instead of silently dropping required evidence.
  - Explicit `run_id` values are validated with `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`, and the resolved `run_root` must be a child directory under `output_root` before any directory creation.
  - Compiled track `frame_count`, `fps`, and per-frame indexes use typed `DirectorInputError` validation helpers, not raw `int(...)` conversions.
  - Run provenance `source_spec_sha256` must match the copied authoring spec hash; mismatches are preflighted before any run directory is created.
- Verification commands:
  - Managed: `dotnet test src/Rook.Tests/Rook.Tests.csproj --filter "CanvasDirector|NativeDirectorCanvasDispatchSourceTests|Registrar_DeclaresCanvasDirectorDispatchCallback"`
  - Python: `python -m pytest mcp_server/tests/test_canvas_director.py mcp_server/tests/test_director_mcp_tools.py mcp_server/tests/test_director.py -q -k "canvas_director or run_compiled_track or validate_run_inputs"`
