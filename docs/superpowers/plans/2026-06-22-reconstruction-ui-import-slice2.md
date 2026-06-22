# Reconstruction One-Click Import (Slice 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click **Import to Rhino** button to the Reconstruct view that imports a completed reconstruction package into the active document, by routing `{package_id}` through a new async/off-UI `import_package` op → an injected managed import client that loopback-POSTs to the unchanged native import route.

**Architecture:** Managed bridge adapter (C1) over the existing native importer. `VisionWebSurface` routes `import_package` (async) → `ReconstructionOpHandler.DispatchAsync` (new adapter case) → injected `IReconstructionImportClient` → loopback HTTP POST to the fixed `/reconstruction/2d-to-3d/import` route. Native importer is unchanged and authoritative. Off-UI classification on **both** dispatch surfaces is the deadlock invariant, pinned by source-assertion tests.

**Tech Stack:** C# (.NET Framework 4.8, `System.Text.Json`, `HttpClient`), vanilla JS/HTML/CSS (no JS test harness), xUnit (`Rook.Tests`, net48).

## Global Constraints

- Base: `origin/main` @ `b0564bb8`; worktree `.worktrees/reconstruction-import`, branch `feature/reconstruction-ui-import-slice2`.
- **No second importer.** Native importer stays authoritative; the managed side only adapts/loops back.
- **No WebView HTTP.** Only the managed companion performs loopback; CSP `connect-src 'none'` untouched.
- **Off-UI invariant (deadlock gate):** `import_package` MUST be async on BOTH surfaces — `VisionWebSurface.ReconstructionAsyncOps` AND `NativeGhBridgeRegistrar.HandleReconstructionDispatch` async branch — and handled by `ReconstructionOpHandler.DispatchAsync`, rejected by `DispatchOffUi`.
- **Discovery key is `processId`** (the native discovery file field) — match `processId == Process.GetCurrentProcess().Id`. NOT `rhinoProcessId`.
- **Native envelope** is `{success, data}` — the client unwraps once and returns inner `data`; no double-wrap.
- **`association_failed`** is a structured failure (HTTP 500, `success:false`), not a success.
- **Fixed route only:** the client POSTs only to `/reconstruction/2d-to-3d/import`. No arbitrary URL.
- **Request is `{ package_id }` only** — no `targetLayer`, no `assetRole`.
- **Copy:** button `Import to Rhino` → in-flight `Importing…` (disabled) → success `Imported N object(s) as {asset_role}` (re-enabled) → failure: structured native message. Re-import allowed; status-only; relabel result-panel `Preferred:` → `Catalog preferred:`.
- Auth isolation lives only in the client (native has no route auth today).
- `dotnet test -c Debug` stays green (Debug skips the `%AppData%` deploy). JS verified via the **panel-dark gate** (node --check, no dup ids, every Reconstruct-module `$()` id exists in index.html, no stale symbols).

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `src/Rook/Services/Reconstruction/ReconstructionImportClient.cs` | Import client contract + impl | **Create** — `IReconstructionImportClient`, `NativeImportOutcome`, `NativeReconstructionImportClient` |
| `src/Rook/Services/Reconstruction/NativeEndpointResolver.cs` | Native endpoint discovery | **Create** — `INativeEndpointResolver`, `DiscoveryFileNativeEndpointResolver`, pure `SelectNativePort` |
| `src/Rook/Handlers/ReconstructionOpHandler.cs` | Reconstruction op dispatch | `OpImportPackage` const; ctor optional client; `ImportAsync` case in `DispatchAsync`; reject in `DispatchOffUi` |
| `src/Rook/UI/Vision/VisionWebSurface.cs` | WebView bridge routing | add `"import_package"` to `ReconstructionAsyncOps` |
| `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` | Native dispatch trampoline | add `OpImportPackage` to the async branch |
| `src/Rook/RookSubsystemRoot.cs` | DI wiring | build + inject `NativeReconstructionImportClient` |
| `src/Rook/UI/Vision/Resources/{index.html,app.js,styles.css}` | Reconstruct view | import button + status; copy; relabel Preferred |
| `src/Rook.Tests/Services/Reconstruction/ReconstructionImportClientTests.cs` | client + discovery tests | **Create** |
| `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs` | handler import case test | extend |
| `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs` | routing source-assertion | extend |
| `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs` | native-trampoline source-assertion | extend |

---

## Task 1: `import_package` contract + dual-surface async routing (routing tests first)

**Files:**
- Modify: `src/Rook/Handlers/ReconstructionOpHandler.cs`
- Create: `src/Rook/Services/Reconstruction/ReconstructionImportClient.cs` (contract only this task)
- Modify: `src/Rook/UI/Vision/VisionWebSurface.cs`, `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs`, `src/Rook/RookSubsystemRoot.cs`
- Test: `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`, `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`, `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`

**Interfaces:**
- Produces: `ReconstructionOpHandler.OpImportPackage = "import_package"`; `IReconstructionImportClient { Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken ct) }`; `NativeImportOutcome` (Data JsonObject? / Failure ReconstructionFailure?).
- Consumes: existing `ReconstructionFailure(Code, Message, Retryable, Field, Details)`, `ApiResponse`, `Ok`/`Fail`/`Failure`/`StatusFor`/`TryParseGuid` helpers in the handler; `RepoRoot` source-guard convention.

- [ ] **Step 1: Write the routing source-assertion tests (they fail to compile — the op doesn't exist)**

In `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs`, add (the file already has `RepoRoot` + `System.Linq` from slice 1):

```csharp
[Fact]
public void ReconstructionAsyncOps_Includes_ImportPackage()
{
    Assert.Contains("import_package", VisionWebSurface.ReconstructionAsyncOps);
}
```

In `src/Rook.Tests/Handlers/NativeReconstructionDispatchSourceTests.cs`, add a test that pins `import_package` into the native trampoline's **async** branch (not off-UI). This reuses the file's `RepoRoot` + `ExtractFunction` helpers:

```csharp
[Fact]
public void NativeBridge_RoutesImportPackageThroughAsyncDispatch()
{
    var managed = File.ReadAllText(Path.Combine(
        RepoRoot, "src", "Rook", "InternalBridge", "NativeGhBridgeRegistrar.cs"));
    var fn = ExtractFunction(managed, "HandleReconstructionDispatch");

    var submitIdx = fn.IndexOf("case ReconstructionOpHandler.OpSubmit:", System.StringComparison.Ordinal);
    var asyncCallIdx = fn.IndexOf("(reqJson, ct) => RookSubsystemRoot.Instance.Reconstruction.DispatchAsync", System.StringComparison.Ordinal);
    var importIdx = fn.IndexOf("case ReconstructionOpHandler.OpImportPackage:", System.StringComparison.Ordinal);

    Assert.True(importIdx >= 0, "OpImportPackage case not found in HandleReconstructionDispatch.");
    // import case must sit in the async group: after OpSubmit, before the async DispatchAsync lambda.
    Assert.True(importIdx > submitIdx && importIdx < asyncCallIdx,
        "OpImportPackage must be in the async dispatch branch.");
}
```

In `src/Rook.Tests/Handlers/ReconstructionOpHandlerTests.cs`, add a handler-level test that `import_package` routes to the injected client (async) and is rejected off-UI. Add a fake client at the top of the test class:

```csharp
private sealed class FakeImportClient : IReconstructionImportClient
{
    public Guid? LastPackageId;
    public NativeImportOutcome Outcome = NativeImportOutcome.Ok(new System.Text.Json.Nodes.JsonObject
    {
        ["asset_role"] = "model_obj",
        ["imported_ids"] = new System.Text.Json.Nodes.JsonArray { "id-1" },
    });
    public Task<NativeImportOutcome> ImportAsync(Guid packageId, System.Threading.CancellationToken ct)
    {
        LastPackageId = packageId;
        return Task.FromResult(Outcome);
    }
}

[Fact]
public async Task ImportPackage_Async_RoutesToClient_AndReturnsData()
{
    var fake = new FakeImportClient();
    var handler = NewHandler(importClient: fake);   // NewHandler defined in Step 4 below
    var pkg = Guid.NewGuid();
    var body = $"{{\"op\":\"import_package\",\"package_id\":\"{pkg:D}\"}}";

    var resp = await handler.DispatchAsync(body);

    Assert.True(resp.Success);
    Assert.Equal(pkg, fake.LastPackageId);
}

[Fact]
public void ImportPackage_OffUi_IsRejected_WithoutInvokingClient()
{
    var fake = new FakeImportClient();
    var handler = NewHandler(importClient: fake);
    var body = $"{{\"op\":\"import_package\",\"package_id\":\"{Guid.NewGuid():D}\"}}";

    var resp = handler.DispatchOffUi(body);

    Assert.False(resp.Success);
    Assert.Equal(400, resp.HttpStatus);
    // Structured invalid-op failure (must route through async dispatcher) — NOT an accidental client run:
    var data = Assert.IsType<Dictionary<string, object?>>(resp.Data);
    Assert.Equal("invalid_request", data["code"]);
    Assert.Null(fake.LastPackageId);   // client must NOT be invoked off-UI
}
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionAsyncOps_Includes_ImportPackage|FullyQualifiedName~NativeBridge_RoutesImportPackageThroughAsyncDispatch|FullyQualifiedName~ImportPackage_"`
Expected: FAIL — `IReconstructionImportClient`/`NativeImportOutcome`/`OpImportPackage`/`NewHandler` undefined.

- [ ] **Step 3: Create the client contract** (`src/Rook/Services/Reconstruction/ReconstructionImportClient.cs`)

```csharp
using System;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;

namespace Rook.Services.Reconstruction
{
    /// <summary>
    /// Managed adapter over the native reconstruction import route. The native
    /// importer stays authoritative; this just loops a request back to it.
    /// </summary>
    public interface IReconstructionImportClient
    {
        Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken);
    }

    /// <summary>
    /// Either the unwrapped native <c>data</c> object (success) or a structured failure.
    /// </summary>
    public sealed record NativeImportOutcome(JsonObject? Data, ReconstructionFailure? Failure)
    {
        public bool Success => Failure is null;
        public static NativeImportOutcome Ok(JsonObject data) => new(data, null);
        public static NativeImportOutcome Fail(ReconstructionFailure failure) => new(null, failure);
    }
}
```

- [ ] **Step 4: Wire the handler** — add the const, ctor param (optional, null-guarded), the async case, and the off-UI rejection.

In `ReconstructionOpHandler.cs`, add the const after `OpCleanupPreparedImport`:

```csharp
        public const string OpImportPackage = "import_package";
```

Add the field + extend the ctor (keep the param **optional** so existing 3-arg test/ctor call sites still compile; production injects the real client):

```csharp
        private readonly IReconstructionImportClient? _importClient;

        public ReconstructionOpHandler(
            ReconstructionModelCatalog catalog,
            ReconstructionJobManager manager,
            ArtifactStore store,
            IReconstructionImportClient? importClient = null)
        {
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _manager = manager ?? throw new ArgumentNullException(nameof(manager));
            _store = store ?? throw new ArgumentNullException(nameof(store));
            _importClient = importClient;
        }
```

In `DispatchAsync`'s `op switch`, add the `OpImportPackage` case before the off-UI group:

```csharp
                    OpImportPackage => await ImportAsync(args, cancellationToken).ConfigureAwait(false),
```

Implement `ImportAsync` (place near `SubmitAsync`):

```csharp
        private async Task<ApiResponse> ImportAsync(
            Dictionary<string, JsonElement> args,
            CancellationToken ct)
        {
            if (!TryParseGuid(args, "package_id", out var packageId, out var failure))
                return Fail(failure!, 400);
            if (_importClient is null)
                return Fail(Failure("native_unavailable", "Reconstruction import client is not configured.", null, retryable: true), 503);

            var outcome = await _importClient.ImportAsync(packageId, ct).ConfigureAwait(false);
            if (!outcome.Success)
                return Fail(outcome.Failure!, StatusFor(outcome.Failure!));
            return Ok(outcome.Data!);
        }
```

In `DispatchOffUi`'s `op switch`, add `OpImportPackage` to the rejected-async group:

```csharp
                    OpSubmit or OpStatus or OpCancel or OpImportPackage => Fail(
                        Failure("invalid_request", $"op '{op}' must be routed through the async dispatcher, not the off-UI dispatcher.", "op"),
                        400),
```

> Note: `StatusFor` has no `native_unavailable` case → defaults to 500; the explicit `503` above is only the direct-Fail path. Add `"native_unavailable" => 503` to `StatusFor` for consistency:

```csharp
                "provider_unavailable" or "native_unavailable" => 503,
```

(Replace the existing `"provider_unavailable" => 503,` line.)

- [ ] **Step 5: Add `import_package` to `ReconstructionAsyncOps`** (`VisionWebSurface.cs`, the set near line 263):

```csharp
        internal static readonly HashSet<string> ReconstructionAsyncOps =
            new(StringComparer.Ordinal)
            {
                "submit_job",
                "job_status",
                "cancel_job",
                "import_package",
            };
```

(No other change in `HandleReconstructionBridgeCallAsync` — `ReconstructionAsyncOps.Contains(op)` already routes it through `DispatchWithTimeoutAsync` → `Reconstruction.DispatchAsync`.)

- [ ] **Step 6: Add the native-trampoline async case** (`NativeGhBridgeRegistrar.cs`, `HandleReconstructionDispatch`):

```csharp
                case ReconstructionOpHandler.OpSubmit:
                case ReconstructionOpHandler.OpStatus:
                case ReconstructionOpHandler.OpCancel:
                case ReconstructionOpHandler.OpImportPackage:
                    return ExecuteAsyncApiResponseCallback(
```

- [ ] **Step 7: Inject the client in `RookSubsystemRoot.CreateReconstruction`** — temporary skeleton client so it compiles; real impl lands in Tasks 2–3.

In `ReconstructionImportClient.cs`, add a minimal `NativeReconstructionImportClient` that compiles and returns `native_unavailable` (completed in Task 3):

```csharp
    /// <summary>Loopback adapter to the native /reconstruction/2d-to-3d/import route. (Discovery + POST land in Tasks 2–3.)</summary>
    public sealed class NativeReconstructionImportClient : IReconstructionImportClient
    {
        public Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken)
            => Task.FromResult(NativeImportOutcome.Fail(new ReconstructionFailure(
                "native_unavailable",
                "Reconstruction import endpoint not yet available.",
                Retryable: true, Field: null,
                Details: new System.Collections.Generic.Dictionary<string, object?>())));
    }
```

In `RookSubsystemRoot.cs` `CreateReconstruction`, change the return line:

```csharp
            return new ReconstructionOpHandler(catalog, manager, SharedArtifactStore, new NativeReconstructionImportClient());
```

- [ ] **Step 8: Add the `NewHandler` test helper** in `ReconstructionOpHandlerTests.cs` (if the class lacks one). It must mirror how the existing tests build a handler; add the optional client:

```csharp
private static ReconstructionOpHandler NewHandler(IReconstructionImportClient importClient = null)
    => new ReconstructionOpHandler(TestCatalog(), TestManager(), TestStore(), importClient);
```

> If the test class already constructs handlers inline (not via a helper), instead add `NewHandler` alongside those and reuse the existing `TestCatalog()/TestManager()/TestStore()` builders the file already uses. Match the existing fixture names — do not invent new ones.

- [ ] **Step 9: Run the Task-1 tests + the broader suites**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionAsyncOps_Includes_ImportPackage|FullyQualifiedName~NativeBridge_RoutesImportPackageThroughAsyncDispatch|FullyQualifiedName~ImportPackage_|FullyQualifiedName~VisionWebSurfaceTests|FullyQualifiedName~NativeReconstructionDispatchSourceTests|FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/Rook/Handlers/ReconstructionOpHandler.cs src/Rook/Services/Reconstruction/ReconstructionImportClient.cs src/Rook/UI/Vision/VisionWebSurface.cs src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs src/Rook/RookSubsystemRoot.cs src/Rook.Tests/
git commit -m "feat(reconstruction-import): import_package contract + dual-surface async routing (off-UI invariant tests)"
```

---

## Task 2: Native endpoint discovery selection (pure, `processId`-scoped)

**Files:**
- Create: `src/Rook/Services/Reconstruction/NativeEndpointResolver.cs`
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionImportClientTests.cs` (create)

**Interfaces:**
- Produces: `INativeEndpointResolver { int? ResolveNativePort() }`; `DiscoveryFileNativeEndpointResolver`; `internal static int? NativeEndpointResolver.SelectNativePort(IEnumerable<JsonObject> docs, int currentProcessId)`.

- [ ] **Step 1: Write the selection test (pure, no file I/O)**

In `src/Rook.Tests/Services/Reconstruction/ReconstructionImportClientTests.cs`:

```csharp
using System.Collections.Generic;
using System.Text.Json.Nodes;
using Rook.Services.Reconstruction;
using Xunit;

namespace Rook.Tests.Services.Reconstruction
{
    public class NativeEndpointSelectionTests
    {
        private static JsonObject Doc(string pluginType, int processId, int port) => new()
        {
            ["pluginType"] = pluginType,
            ["processId"] = processId,
            ["port"] = port,
            ["host"] = "127.0.0.1",
        };

        [Fact]
        public void Selects_Native_Entry_For_Current_Process()
        {
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 9999, 52000), Doc("chat", 4242, 53000) };
            Assert.Equal(51000, NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Returns_Null_When_No_Native_Entry_For_This_Process()
        {
            var docs = new[] { Doc("native", 9999, 52000), Doc("chat", 4242, 53000) };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }

        [Fact]
        public void Returns_Null_For_Empty()
        {
            Assert.Null(NativeEndpointResolver.SelectNativePort(new JsonObject[0], currentProcessId: 4242));
        }

        [Fact]
        public void Ambiguous_Same_Process_Native_Entries_Return_Null()
        {
            // Two native entries for THIS pid (stale/duplicate) — fail closed, don't guess.
            var docs = new[] { Doc("native", 4242, 51000), Doc("native", 4242, 52000) };
            Assert.Null(NativeEndpointResolver.SelectNativePort(docs, currentProcessId: 4242));
        }
    }
}
```

- [ ] **Step 2: Run to confirm it fails**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~NativeEndpointSelectionTests"`
Expected: FAIL — `NativeEndpointResolver` undefined.

- [ ] **Step 3: Create the resolver** (`src/Rook/Services/Reconstruction/NativeEndpointResolver.cs`)

```csharp
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;

namespace Rook.Services.Reconstruction
{
    public interface INativeEndpointResolver
    {
        /// <summary>Port of the native HTTP server for THIS Rhino process, or null if not found.</summary>
        int? ResolveNativePort();
    }

    public sealed class DiscoveryFileNativeEndpointResolver : INativeEndpointResolver
    {
        private readonly IReadOnlyList<string> _folders;

        public DiscoveryFileNativeEndpointResolver(IReadOnlyList<string>? folders = null)
        {
            // Native writes its discovery file under SharedDiscoveryFolder, with a legacy
            // fallback under %TEMP%\rook. Read both, most-specific first.
            _folders = folders ?? new[] { RookPaths.SharedDiscoveryFolder, RookPaths.DiscoveryFolder };
        }

        public int? ResolveNativePort()
        {
            var docs = new List<JsonObject>();
            foreach (var folder in _folders)
            {
                if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder)) continue;
                foreach (var file in Directory.EnumerateFiles(folder, "*.json"))
                {
                    try
                    {
                        if (JsonNode.Parse(File.ReadAllText(file)) is JsonObject obj)
                            docs.Add(obj);
                    }
                    catch (Exception ex) when (ex is IOException or System.Text.Json.JsonException) { /* skip unreadable */ }
                }
            }
            return NativeEndpointResolver.SelectNativePort(docs, Process.GetCurrentProcess().Id);
        }
    }

    public static class NativeEndpointResolver
    {
        /// <summary>
        /// Pure selection: the native (pluginType=="native") discovery entry whose
        /// processId matches THIS OS process (native + companion share the process).
        /// Load-bearing multi-Rhino safety gate.
        /// </summary>
        public static int? SelectNativePort(IEnumerable<JsonObject> docs, int currentProcessId)
        {
            var ports = new List<int>();
            foreach (var doc in docs)
            {
                if (!string.Equals(ReadString(doc, "pluginType"), "native", StringComparison.Ordinal)) continue;
                if (ReadInt(doc, "processId") != currentProcessId) continue;
                var port = ReadInt(doc, "port");
                if (port is > 0) ports.Add(port.Value);
            }
            // Exactly one native endpoint per process is expected. 0 matches, or an
            // ambiguous >1 (stale/duplicate discovery files for this PID), fails closed
            // → caller maps to native_unavailable rather than guessing.
            return ports.Count == 1 ? ports[0] : (int?)null;
        }

        private static string? ReadString(JsonObject obj, string key)
            => obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<string>(out var s) ? s : null;

        private static int? ReadInt(JsonObject obj, string key)
            => obj.TryGetPropertyValue(key, out var n) && n is JsonValue v && v.TryGetValue<int>(out var i) ? i : (int?)null;
    }
}
```

- [ ] **Step 4: Run to confirm pass**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~NativeEndpointSelectionTests"`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/Rook/Services/Reconstruction/NativeEndpointResolver.cs src/Rook.Tests/Services/Reconstruction/ReconstructionImportClientTests.cs
git commit -m "feat(reconstruction-import): processId-scoped native endpoint discovery selection"
```

---

## Task 3: Native import client — loopback POST, envelope unwrap, failure mapping

**Files:**
- Modify: `src/Rook/Services/Reconstruction/ReconstructionImportClient.cs` (complete `NativeReconstructionImportClient`)
- Modify: `src/Rook/RookSubsystemRoot.cs` (inject `HttpClient` + resolver)
- Test: `src/Rook.Tests/Services/Reconstruction/ReconstructionImportClientTests.cs` (extend)

**Interfaces:**
- Consumes: `INativeEndpointResolver`, `NativeImportOutcome`, `ReconstructionFailure`.
- Produces: `NativeReconstructionImportClient(HttpClient http, INativeEndpointResolver resolver)`.

- [ ] **Step 1: Write the client mapping tests (fake transport + stub resolver)**

Append to `ReconstructionImportClientTests.cs`:

```csharp
using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;

public class NativeReconstructionImportClientTests
{
    private sealed class StubResolver : INativeEndpointResolver
    {
        private readonly int? _port;
        public StubResolver(int? port) { _port = port; }
        public int? ResolveNativePort() => _port;
    }

    private sealed class CapturingHandler : HttpMessageHandler
    {
        private readonly HttpStatusCode _status;
        private readonly string _body;
        public string? RequestPath;
        public string? RequestBody;
        public CapturingHandler(HttpStatusCode status, string body) { _status = status; _body = body; }
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            RequestPath = request.RequestUri!.AbsolutePath;
            RequestBody = request.Content is null ? null : await request.Content.ReadAsStringAsync().ConfigureAwait(false);
            return new HttpResponseMessage(_status) { Content = new StringContent(_body) };
        }
    }

    private sealed class ThrowingHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
            => throw new HttpRequestException("connection refused");
    }

    [Fact]
    public async Task Posts_PackageId_To_Fixed_Route_And_Unwraps_Data()
    {
        var cap = new CapturingHandler(HttpStatusCode.OK,
            "{\"success\":true,\"data\":{\"asset_role\":\"model_obj\",\"imported_ids\":[\"a\",\"b\"]}}");
        var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(51000));
        var pkg = Guid.NewGuid();

        var outcome = await client.ImportAsync(pkg, CancellationToken.None);

        Assert.True(outcome.Success);
        Assert.Equal("/reconstruction/2d-to-3d/import", cap.RequestPath);
        Assert.Contains(pkg.ToString("D"), cap.RequestBody);
        Assert.Equal("model_obj", (string?)outcome.Data!["asset_role"]);
        Assert.Equal(2, outcome.Data!["imported_ids"]!.AsArray().Count);
        // Exactly one unwrap — the native envelope keys must NOT leak into the UI data.
        Assert.False(outcome.Data!.ContainsKey("success"), "'success' leaked into UI data (double-wrap)");
        Assert.False(outcome.Data!.ContainsKey("data"), "'data' leaked into UI data (double-wrap)");
    }

    [Fact]
    public async Task Maps_AssociationFailed_To_Structured_Failure()
    {
        var cap = new CapturingHandler(HttpStatusCode.InternalServerError,
            "{\"success\":false,\"data\":{\"code\":\"association_failed\",\"message\":\"user-string association failed\"}}");
        var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(51000));

        var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

        Assert.False(outcome.Success);
        Assert.Equal("association_failed", outcome.Failure!.Code);
    }

    [Fact]
    public async Task No_Endpoint_Returns_NativeUnavailable_Without_Posting()
    {
        var cap = new CapturingHandler(HttpStatusCode.OK, "{}");
        var client = new NativeReconstructionImportClient(new HttpClient(cap), new StubResolver(null));

        var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

        Assert.False(outcome.Success);
        Assert.Equal("native_unavailable", outcome.Failure!.Code);
        Assert.Null(cap.RequestPath);   // never posted
    }

    [Fact]
    public async Task Transport_Fault_Maps_To_NativeUnavailable()
    {
        var client = new NativeReconstructionImportClient(new HttpClient(new ThrowingHandler()), new StubResolver(51000));

        var outcome = await client.ImportAsync(Guid.NewGuid(), CancellationToken.None);

        Assert.False(outcome.Success);
        Assert.Equal("native_unavailable", outcome.Failure!.Code);
    }
}
```

- [ ] **Step 2: Run to confirm fail**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~NativeReconstructionImportClientTests"`
Expected: FAIL — the 2-arg `NativeReconstructionImportClient` ctor doesn't exist yet.

- [ ] **Step 3: Complete `NativeReconstructionImportClient`** — replace the Task-1 skeleton in `ReconstructionImportClient.cs`:

```csharp
    public sealed class NativeReconstructionImportClient : IReconstructionImportClient
    {
        private const string ImportPath = "/reconstruction/2d-to-3d/import";
        private readonly HttpClient _http;
        private readonly INativeEndpointResolver _resolver;

        public NativeReconstructionImportClient(HttpClient http, INativeEndpointResolver resolver)
        {
            _http = http ?? throw new ArgumentNullException(nameof(http));
            _resolver = resolver ?? throw new ArgumentNullException(nameof(resolver));
        }

        public async Task<NativeImportOutcome> ImportAsync(Guid packageId, CancellationToken cancellationToken)
        {
            var port = _resolver.ResolveNativePort();
            if (port is not > 0)
                return NativeImportOutcome.Fail(Failure("native_unavailable",
                    "The Rook native plugin endpoint could not be found for this Rhino instance."));

            var url = $"http://127.0.0.1:{port}{ImportPath}";
            var requestBody = new JsonObject { ["package_id"] = packageId.ToString("D") }.ToJsonString();

            HttpResponseMessage response;
            try
            {
                using var content = new StringContent(requestBody, System.Text.Encoding.UTF8, "application/json");
                response = await _http.PostAsync(url, content, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException && !cancellationToken.IsCancellationRequested)
            {
                return NativeImportOutcome.Fail(Failure("native_unavailable",
                    "The Rook native plugin import endpoint did not respond."));
            }

            string payload;
            using (response)
                payload = await response.Content.ReadAsStringAsync().ConfigureAwait(false);

            JsonObject? envelope;
            try { envelope = JsonNode.Parse(payload) as JsonObject; }
            catch (System.Text.Json.JsonException) { envelope = null; }
            if (envelope is null)
                return NativeImportOutcome.Fail(Failure("import_failed", "Native import returned an unreadable response."));

            var success = envelope.TryGetPropertyValue("success", out var s) && s is JsonValue sv && sv.TryGetValue<bool>(out var b) && b;
            var data = envelope.TryGetPropertyValue("data", out var d) ? d as JsonObject : null;

            if (success && data is not null)
                return NativeImportOutcome.Ok((JsonObject)data.DeepClone());

            // Failure envelope: surface the native code/message.
            var code = data is not null && data.TryGetPropertyValue("code", out var c) && c is JsonValue cv && cv.TryGetValue<string>(out var cs) ? cs : "import_failed";
            var message = data is not null && data.TryGetPropertyValue("message", out var m) && m is JsonValue mv && mv.TryGetValue<string>(out var ms) ? ms : "Native reconstruction import failed.";
            return NativeImportOutcome.Fail(Failure(code, message));
        }

        private static ReconstructionFailure Failure(string code, string message)
            => new(code, message, Retryable: code is "native_unavailable", Field: null,
                   new System.Collections.Generic.Dictionary<string, object?>());
    }
```

Add to the file's usings: `using System.Collections.Generic;`, `using System.Net.Http;`, `using System.Text;` (if not present from the contract).

- [ ] **Step 4: Inject the real client in `RookSubsystemRoot.CreateReconstruction`**

```csharp
            return new ReconstructionOpHandler(
                catalog, manager, SharedArtifactStore,
                new NativeReconstructionImportClient(new HttpClient(), new DiscoveryFileNativeEndpointResolver()));
```

- [ ] **Step 5: Run client tests + full reconstruction suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug --filter "FullyQualifiedName~ReconstructionImportClient|FullyQualifiedName~NativeReconstructionImportClientTests|FullyQualifiedName~NativeEndpointSelectionTests|FullyQualifiedName~ReconstructionOpHandlerTests"`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/Rook/Services/Reconstruction/ReconstructionImportClient.cs src/Rook/RookSubsystemRoot.cs src/Rook.Tests/Services/Reconstruction/ReconstructionImportClientTests.cs
git commit -m "feat(reconstruction-import): native import client — fixed-route POST, envelope unwrap, failure mapping"
```

---

## Task 4: Reconstruct view — Import button + copy + relabel

**Files:** `src/Rook/UI/Vision/Resources/{index.html,app.js,styles.css}`

**Interfaces:**
- Consumes: `reconstructionBridgeCall("import_package", {package_id})` → `{ asset_role, imported_ids[], … }` (unwrapped); `errorToText`, `escapeHtml`.
- Produces: `re.importBtn`, `re.importStatus`; module fns `importPackage()`, `setImportStatus()`; module state `currentPackageId`, `currentResultAvailable`.

- [ ] **Step 1: Replace the handoff div with the import action** (`index.html`, the result panel ~line 696)

Replace:
```html
                        <div id="reconstruct-result-handoff" class="reconstruct-handoff"></div>
```
with:
```html
                        <div class="reconstruct-import">
                            <button id="reconstruct-import-btn" class="btn btn-primary" disabled>Import to Rhino</button>
                            <span id="reconstruct-import-status" class="reconstruct-import-status"></span>
                        </div>
```

- [ ] **Step 2: Update the DOM cache** (`app.js`) — in `cacheEls()`, replace `re.resultHandoff = $("reconstruct-result-handoff");` with:

```javascript
        re.importBtn = $("reconstruct-import-btn");
        re.importStatus = $("reconstruct-import-status");
```

- [ ] **Step 3: Add module state** — near the other `Reconstruct` module `let` declarations (top of the IIFE):

```javascript
    let currentPackageId = null;
    let currentResultAvailable = false;
```

- [ ] **Step 4: Update `renderResult`** — relabel Preferred, capture package id, reset the button, drop the agent-tool handoff line.

In `renderResult`, change the preferred line:
```javascript
            preferred
                ? `<div class="reconstruct-result-preferred">Catalog preferred: ${escapeHtml(preferred)}</div>`
                : "",
```

Replace the handoff block:
```javascript
        re.resultHandoff.innerHTML = packageId
            ? `Import this package into Rhino with the agent tool <code>rhino_2d_to_3d_import</code> (package id above).`
            : "";
```
with:
```javascript
        currentPackageId = packageId || null;
        currentResultAvailable = !!(packageId && result.result_available);
        re.importBtn.disabled = !currentResultAvailable;
        re.importBtn.textContent = "Import to Rhino";
        setImportStatus("", "");
```

- [ ] **Step 5: Add `importPackage` + `setImportStatus`** (inside the module, e.g. after `renderResult`):

```javascript
    function setImportStatus(message, type) {
        if (!re.importStatus) return;
        re.importStatus.textContent = message || "";
        re.importStatus.className = `reconstruct-import-status ${type || ""}`;
    }

    async function importPackage() {
        if (!currentPackageId) return;
        try {
            re.importBtn.disabled = true;
            re.importBtn.textContent = "Importing…";
            setImportStatus("", "");
            const data = await reconstructionBridgeCall("import_package", { package_id: currentPackageId });
            const ids = Array.isArray(data && data.imported_ids) ? data.imported_ids : [];
            const role = (data && data.asset_role) || "model";
            const n = ids.length;
            setImportStatus(`Imported ${n} object${n === 1 ? "" : "s"} as ${role}`, "success");
        } catch (e) {
            setImportStatus(errorToText(e), "error");
        } finally {
            re.importBtn.textContent = "Import to Rhino";
            re.importBtn.disabled = !currentResultAvailable;
        }
    }
```

- [ ] **Step 6: Wire the button** — in `wireEvents()`:

```javascript
        re.importBtn.addEventListener("click", importPackage);
```

- [ ] **Step 7: Styles** (`styles.css`, after the `.reconstruct-handoff` rules):

```css
.reconstruct-import { display: flex; align-items: center; gap: var(--space-3); }
.reconstruct-import-status { font-size: 13px; color: var(--ink-soft); }
.reconstruct-import-status.success { color: var(--accent-green); }
.reconstruct-import-status.error { color: var(--accent-red); }
```

- [ ] **Step 8: Panel-dark gate**

Run (reuse the slice-1 gate logic):
```bash
JS=src/Rook/UI/Vision/Resources/app.js; IDX=src/Rook/UI/Vision/Resources/index.html
node --check "$JS" && echo "syntax OK"
grep -oE 'id="[^"]+"' "$IDX" | sort | uniq -d   # expect empty
# every Reconstruct-module $() id exists in index.html:
start=$(grep -nE "^const Reconstruct = \(\(\) => \{" "$JS" | cut -d: -f1)
sed -n "${start},\$p" "$JS" | grep -oE '\$\("[^"]+"\)' | sed -E 's/\$\("([^"]+)"\)/\1/' | sort -u | while read id; do grep -q "id=\"$id\"" "$IDX" || echo "MISSING: $id"; done
grep -nE "resultHandoff|reconstruct-result-handoff" "$JS" "$IDX"   # expect empty (removed)
```
Expected: syntax OK; no duplicate ids; no MISSING; no `resultHandoff` stragglers.

- [ ] **Step 9: Commit**

```bash
git add src/Rook/UI/Vision/Resources/index.html src/Rook/UI/Vision/Resources/app.js src/Rook/UI/Vision/Resources/styles.css
git commit -m "feat(reconstruction-import): Import to Rhino button + response-driven copy; relabel Catalog preferred"
```

---

## Task 5: Full verification + manual smoke + finish

**Files:** none (verification only).

- [ ] **Step 1: Full managed suite**

Run: `dotnet test src/Rook.Tests/Rook.Tests.csproj -c Debug`
Expected: all green; no "Deployed Rook.rhp" line (Debug skips deploy).

- [ ] **Step 2: §9 verify-on-base re-confirmation** — confirm against `b0564bb8` that the discovery schema and import envelope match the client's assumptions:
```bash
git show HEAD:src/RookNative/RookServer.cpp | grep -nE '"pluginType"|"processId"|"port"'   # native discovery fields
git show HEAD:src/RookNative/Handlers/ImportExportHandler.cpp | grep -nE '"success", true|"asset_role"|"imported_ids"|association_failed'
```
Expected: `processId`/`pluginType`/`port` present; success envelope `{success:true,data:{…}}` + `association_failed` present. If field names differ, fix the client/resolver before smoke.

- [ ] **Step 3: Manual Rhino smoke (merge gate)** — deploy the managed build, then exercise:
```bash
# Rhino MUST be closed first (loaded .rhp is locked):
dotnet build src/Rook/Rook.csproj -c Release   # DeployToRhino → RookNative\{net48,net7.0,net8.0}
```
Checklist (record results): ShowRookVision → Reconstruct → load a completed package (fresh job or job-history click) → **Import to Rhino**: objects appear in the active doc; status reads "Imported N object(s) as model_obj"; button returns to idle; re-import duplicates. Failure path: with no native endpoint match (or a bad package id) the status shows the structured native message and nothing imports.

- [ ] **Step 4: Finish the branch** — announce and use **superpowers:finishing-a-development-branch**; push + open a ready PR into `main` (do not merge locally). PR body must state the live smoke is the merge gate and was/was-not run.

---

## Self-review

**Spec coverage:** C1 adapter (T1/T3), off-UI invariant on both surfaces + handler (T1, tests), processId discovery (T2), envelope unwrap + association_failed + transport mapping (T3), fixed-route/{package_id}-only (T3 test), button + copy + relabel + re-import + status-only (T4), no WebView HTTP / no second importer (architecture, all tasks). §7 tests → T1 (routing ×3 surfaces), T2 (discovery), T3 (client mapping), T4 (panel-dark), T5 (suite + smoke). §9 verify items → T5 Step 2. Deferred items (layer/role UI, select/zoom, idempotency confirm, pre-import preview, C2) — not implemented.

**Placeholder scan:** no TBD/"add error handling"; every code step shows real code. The Task-1 skeleton client is explicitly temporary and replaced in Task 3 (no dangling placeholder).

**Type/name consistency:** `IReconstructionImportClient.ImportAsync(Guid, CancellationToken) → Task<NativeImportOutcome>` used identically in T1 handler, T1 fake, T3 impl. `NativeImportOutcome.Ok/Fail`, `.Success`, `.Data`, `.Failure` consistent. `NativeEndpointResolver.SelectNativePort(IEnumerable<JsonObject>, int)` and `INativeEndpointResolver.ResolveNativePort()` consistent between T2 def and T3 use. `OpImportPackage = "import_package"` consistent across handler, VisionWebSurface set literal, native trampoline, and JS op string. `re.importBtn`/`re.importStatus`/`currentPackageId` consistent across T4 steps. `ReconstructionFailure(Code, Message, Retryable, Field, Details)` positional args match the record.
