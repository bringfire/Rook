# Vertex RookVision Nano Banana 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task with the stated review checkpoints. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one explicit `vertex_ai/gemini-3.1-flash-image` RookVision provider that obtains short-lived Vertex credentials from Rook's existing owned Python service, while moving the existing AI Studio image models to their GA IDs.

**Architecture:** Keep Python as the sole Vertex credential owner and C# as the RookVision image owner. A manager-owned atomic URI/nonce snapshot feeds one narrow token-source adapter; one exact internal Python route returns a generation-checked short-lived lease; one single-step asynchronous C# provider sends the Vertex `generateContent` request and returns the completed image without polling.

**Tech Stack:** Python 3.11.9, aiohttp, google-auth 2.56.3, C#/.NET 8/7/net48, HttpClient, System.Text.Json, xUnit, pytest, Rhino 8 local deployment.

## Global Constraints

- Approved specification: `docs/superpowers/specs/2026-08-14-vertex-rookvision-nano-banana-2-design.md` at `53ed5b63d6363a3f2ec2326ee3fe2686dc8d46a2`.
- Specification parent and planning baseline: `61c686c5e1204ded860fc9a22f8acc65c4f99db6`.
- Preserve exactly two production commits: AI Studio GA-ID prerequisite, then complete Vertex RookVision integration.
- The first Vertex image catalog contains exactly `vertex_ai/gemini-3.1-flash-image`; do not add Vertex Pro, Veo, partner models, aliases, or fallback.
- AI Studio remains provider `gemini`, keeps its API-key transport, short names, default, options, and limits, but uses the two GA model IDs.
- Vertex Nano Banana 2 accepts only configured location `global` and uses `https://aiplatform.googleapis.com/v1/projects/{project}/locations/global/publishers/google/models/gemini-3.1-flash-image:generateContent`.
- The managed provider is asynchronous and single-step: `SubmitAsync` returns a completed result; no polling, blocking `.Result`, or `GetAwaiter().GetResult()` is introduced.
- Python owns credential resolution and refresh. C# receives only access token, expiry, project, location, and authorization generation and never persists them.
- The internal route rejects every `Origin`, requires the exact nonce, has a closed HTTP/status/envelope contract, sets `Cache-Control: no-store` for every result, and has no MCP tool.
- Vertex errors retain only an allowlisted status identifier and fixed Rook message. `ProviderDetail` is null; raw Google bodies/messages never persist.
- No new dependency, lockfile, installer behavior, credential store, generic lifecycle abstraction, service locator, provider framework, or token broker.
- No Chirp, native C++, RookBIM, Grasshopper, video/Veo, chat-model, DSPy, public-repository, version-bump, or release-publication work.
- Deselect only `mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload` and `mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found` from Vertex Python gates. They are independently reproduced baseline debt; their allowlisted test file does not authorize changing either knowledge contract or its implementation in this branch.
- Installed acceptance uses 1K or 2K, never 4K; 4K remains explicitly Preview while the model is GA.
- Stop on scope drift, baseline drift affecting an approved production path, unexpected dependency movement, or an environmental failure. Do not absorb adjacent repairs.

---

## File Map and Exact Scope

The implementation may change only the following paths in addition to the approved specification and this plan.

### Production commit 1: AI Studio GA identifiers

| Path | Responsibility |
| --- | --- |
| `src/Rook/Services/Vision/Image/Gemini/GeminiImageCapabilities.cs` | Replace retired IDs and mark both models GA; retain all other capabilities/defaults. |
| `src/Rook.Tests/Handlers/VisionHandlerTests.cs` | Pin short-name resolution and generated AI Studio URL to the GA IDs. |
| `src/Rook.Tests/Services/Vision/Generation/GeminiSyncShapeProviderFake.cs` | Keep active fake response metadata current. |
| `src/Rook.Tests/Services/Vision/Generation/MetadataPreservationFixture.cs` | Keep active metadata fixture current. |
| `src/Rook.Tests/Services/Vision/Image/GeminiImageProviderTests.cs` | Pin current model metadata and API-key request to the GA ID. |

### Production commit 2: Vertex RookVision integration

| Path | Responsibility |
| --- | --- |
| `mcp_server/src/rook/providers/vertex_token_lease.py` | New generation-aware in-memory token lease and bounded google-auth refresh. |
| `mcp_server/src/rook/providers/vertex_backend.py` | Reuse the token refresh primitive for existing readiness without changing its contract. |
| `mcp_server/src/rook/agent/chat/server.py` | Exact internal route, route-specific admission, fixed envelope/no-store response. |
| `mcp_server/tests/test_vertex_token_lease.py` | Token cache, concurrency, timeout, generation, disconnect, and redaction contracts. |
| `mcp_server/tests/test_vertex_backend.py` | Preserve readiness behavior through the shared refresh primitive. |
| `mcp_server/tests/test_chat_server.py` | Exact internal-route status/envelope/security contracts and no MCP exposure. |
| `src/Rook/Services/Vision/Image/Gemini/GeminiImageProvider.cs` | Delegate only pure successful Gemini wire encoding/parsing; retain AI Studio transport/error behavior. |
| `src/Rook/Services/Vision/Image/Gemini/GeminiImageWireCodec.cs` | New pure shared request/success-response codec; no error mapping. |
| `src/Rook/Services/Vision/Image/Vertex/VertexAccessTokenContract.cs` | Narrow token lease/result/source interface and unavailable default. |
| `src/Rook/Services/Vision/Image/Vertex/VertexImageCapabilities.cs` | Exact provider-qualified model identity, Google ID, global location, and one capability. |
| `src/Rook/Services/Vision/Image/Vertex/VertexImageProvider.cs` | Single-step async Bearer transport, global endpoint, success parsing, bounded error mapping. |
| `src/Rook/Services/Vision/Image/Vertex/VertexImageProviderRegistration.cs` | One model registration, zero API-key requirements, and Vertex-specific unverified pricing provenance. |
| `src/Rook/Services/Vision/VisionProviderRegistrations.cs` | Compose the Vertex registration without adding a credential slot. |
| `src/Rook/UI/Chat/ChatServiceManager.cs` | Ensure/start and return one atomic owned URI/nonce snapshot under the lifecycle gate. |
| `src/Rook/UI/Chat/ChatServiceVertexAccessTokenSource.cs` | Concrete internal HTTP adapter implementing the neutral token-source interface. |
| `src/Rook/RookSubsystemRoot.cs` | Hold only the neutral token-source dependency and include Vertex in the lazy image registry. |
| `src/Rook/RookPlugin.cs` | One-time outer composition of the Chat adapter before image subsystem access. |
| `src/Rook/UI/Vision/VisionWebSurface.cs` | Reuse the root's image registry for catalog/handler parity instead of constructing an unavailable duplicate. |
| `src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs` | Reuse the same root image registry on the existing managed Vision callback path. |
| `src/Rook/UI/Vision/Resources/app.js` | Render the one Vertex option exactly without a duplicate provider suffix. |
| `src/Rook.Tests/Services/Vision/Image/VertexImageProviderTests.cs` | Managed contract, transport, endpoint, cancellation, parsing, and redacted error tests. |
| `src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs` | Prove qualified Vertex/unqualified AI Studio coexist and Vertex catalog count is one. |
| `src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs` | Prove composition includes Vertex and credential metadata still has no Vertex key slot. |
| `src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs` | Prove the connection snapshot is created only from one verified owned-service lifetime. |
| `src/Rook.Tests/UI/Chat/ChatServiceVertexAccessTokenSourceTests.cs` | Prove cold acquisition, request shape, response validation, timeout, and no persistence. |
| `src/Rook.Tests/RookSubsystemRootTests.cs` | Prove neutral one-time token-source injection and no UI/process dependency in the root. |
| `src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs` | Prove outer composition occurs before image reconciliation/access. |
| `src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs` | Prove the callback handler uses the exact shared image registry. |
| `src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs` | Pin exact display and preserve AI Studio default behavior. |

Do not add a path during execution merely because implementation would be easier. Stop and return for review if an additional production or test path is genuinely required.

---

### Task 0: Bootstrap the approved plan and capture the immutable RED baseline

**Files:**
- Verify only; no source edits.

**Interfaces:**
- Consumes: approved plan tag, spec `53ed5b63`, baseline `61c686c5`, the release Python 3.11.9 interpreter.
- Produces: clean isolated worktree, locked test environment, baseline test evidence, and a no-edit drift decision.

- [ ] **Step 1: Verify plan ancestry and approval tag**

After reviewer approval of this amendment, preserve the original approval tag at `b2857a0fd4e75f757d404aefd2d0ded71f88e778` and create a second annotated tag locally at the amended plan commit:

```powershell
$worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\vertex-rookvision-nano-banana-2-design'
$spec = '53ed5b63d6363a3f2ec2326ee3fe2686dc8d46a2'
$priorPlan = 'b2857a0fd4e75f757d404aefd2d0ded71f88e778'
$priorTag = 'plan/vertex-rookvision-nano-banana-2-2026-08-17-approved'
$tag = 'plan/vertex-rookvision-nano-banana-2-2026-08-27-approved'
Set-Location $worktree
if ((git rev-parse "$priorTag^{}").Trim() -ne $priorPlan) { throw 'Original approval tag moved' }
if ((git rev-parse "$priorPlan^").Trim() -ne $spec) { throw 'Original approved plan is not directly atop the approved spec' }
if (git tag --list $tag) { throw 'Amended approval tag already exists unexpectedly' }
git tag -a $tag -m 'Approved amended Vertex RookVision Nano Banana 2 implementation plan'
$planCommit = (git rev-parse "$tag^{}" ).Trim()
$executionHead = (git rev-parse HEAD).Trim()
if ($executionHead -ne $planCommit) {
    throw "Execution HEAD does not equal the approved plan tag: HEAD=$executionHead tag=$planCommit"
}
$parent = (git rev-parse "$planCommit^" ).Trim()
if ($parent -ne $priorPlan) { throw "Amended plan is not directly atop the original approved plan: $parent" }
$planPaths = @(git diff-tree --no-commit-id --name-only -r $planCommit)
if ($planPaths.Count -ne 1 -or $planPaths[0] -ne 'docs/superpowers/plans/2026-08-17-vertex-rookvision-nano-banana-2.md') {
    throw "Approved plan commit scope is invalid: $($planPaths -join ', ')"
}
if (git status --porcelain) { throw 'Execution worktree is dirty before Task 0' }
```

Do not generalize this bootstrap. The tag is the immutable execution pin because the plan cannot embed its own SHA.

- [ ] **Step 2: Refresh main and apply the drift gate**

```powershell
git fetch origin --prune
$main = (git rev-parse origin/main).Trim()
$baseline = '61c686c5e1204ded860fc9a22f8acc65c4f99db6'
$approvedPaths = @(
    'src/Rook/Services/Vision/Image/Gemini/GeminiImageCapabilities.cs',
    'src/Rook.Tests/Handlers/VisionHandlerTests.cs',
    'src/Rook.Tests/Services/Vision/Generation/GeminiSyncShapeProviderFake.cs',
    'src/Rook.Tests/Services/Vision/Generation/MetadataPreservationFixture.cs',
    'src/Rook.Tests/Services/Vision/Image/GeminiImageProviderTests.cs',
    'mcp_server/src/rook/providers/vertex_token_lease.py',
    'mcp_server/src/rook/providers/vertex_backend.py',
    'mcp_server/src/rook/agent/chat/server.py',
    'mcp_server/tests/test_vertex_token_lease.py',
    'mcp_server/tests/test_vertex_backend.py',
    'mcp_server/tests/test_chat_server.py',
    'src/Rook/Services/Vision/Image/Gemini/GeminiImageProvider.cs',
    'src/Rook/Services/Vision/Image/Gemini/GeminiImageWireCodec.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexAccessTokenContract.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexImageCapabilities.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexImageProvider.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexImageProviderRegistration.cs',
    'src/Rook/Services/Vision/VisionProviderRegistrations.cs',
    'src/Rook/UI/Chat/ChatServiceManager.cs',
    'src/Rook/UI/Chat/ChatServiceVertexAccessTokenSource.cs',
    'src/Rook/RookSubsystemRoot.cs',
    'src/Rook/RookPlugin.cs',
    'src/Rook/UI/Vision/VisionWebSurface.cs',
    'src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs',
    'src/Rook/UI/Vision/Resources/app.js',
    'src/Rook.Tests/Services/Vision/Image/VertexImageProviderTests.cs',
    'src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs',
    'src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs',
    'src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs',
    'src/Rook.Tests/UI/Chat/ChatServiceVertexAccessTokenSourceTests.cs',
    'src/Rook.Tests/RookSubsystemRootTests.cs',
    'src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs',
    'src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs',
    'src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs'
)
if ($main -ne $baseline) {
    $moved = @(git diff --name-only "${baseline}..${main}")
    $overlap = @($moved | Where-Object { $approvedPaths -contains $_ })
    if ($overlap.Count) { throw "Current main overlaps approved implementation paths: $($overlap -join ', ')" }
}
```

If `main` moved without overlap, record the new SHA and continue without rebasing the approved documents. If there is overlap, stop for review.

Amendment-time observation: after a fresh fetch, `origin/main` was `f840069a58d0a5ee297ae817f0b3efe7a9287512`, 13 commits beyond the recorded baseline, with zero overlap against the 34 approved implementation paths. Task 0 must still fetch, recompute, and record the then-current tip and overlap result rather than treating this observation as a new baseline.

- [ ] **Step 3: Create the ignored locked Python environment**

```powershell
$releasePython = "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
if (-not (Test-Path -LiteralPath $releasePython -PathType Leaf)) { throw 'Pinned Python 3.11.9 is missing' }
Set-Location "$worktree\mcp_server"
uv sync --frozen --extra test --python $releasePython
.\.venv\Scripts\python.exe -c "import sys, importlib.metadata as m; assert sys.version_info[:3] == (3,11,9); print(m.version('google-auth'))"
uv pip check --python .\.venv\Scripts\python.exe
if ($LASTEXITCODE -ne 0) { throw 'Locked Python environment is invalid' }
Set-Location $worktree
if (git status --porcelain) { throw 'Tracked files changed while creating the ignored environment' }
```

Expected Google auth version: `2.56.3`.

- [ ] **Step 4: Run the current focused baseline**

```powershell
$noDeploy = Join-Path $env:TEMP 'rook-vertex-vision-no-deploy'
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~GeminiImageProviderTests|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~ChatServiceManagerTests|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~VisionWebSurfaceTests" `
    --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'Managed baseline failed' }

Set-Location "$worktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_vertex_backend.py `
    tests/test_chat_server.py `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload" `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found" -q
if ($LASTEXITCODE -ne 0) { throw 'Python baseline failed' }
Set-Location $worktree
```

The unfiltered baseline produced `113 passed / 2 known baseline failures`. With only the two exact node IDs above deselected, require `113 passed / 2 deselected / 0 failed`. Do not change or reinterpret either knowledge test in this branch.

- [ ] **Step 5: Capture immutable RED facts without editing**

```powershell
$activePreview = @(rg -l 'gemini-3\.1-flash-image-preview|gemini-3-pro-image-preview' src/Rook src/Rook.Tests)
if ($activePreview.Count -ne 5) { throw "Unexpected preview-ID baseline: $($activePreview -join ', ')" }
if (Test-Path 'mcp_server/src/rook/providers/vertex_token_lease.py') { throw 'Token lease unexpectedly exists at RED baseline' }
if (Test-Path 'src/Rook/Services/Vision/Image/Vertex/VertexImageProvider.cs') { throw 'Vertex image provider unexpectedly exists at RED baseline' }
$server = Get-Content -LiteralPath 'mcp_server/src/rook/agent/chat/server.py' -Raw
if ($server.Contains('/internal/providers/vertex/access-token')) { throw 'Internal token route unexpectedly exists at RED baseline' }
```

Record these facts in the Task 0 checkpoint. Do not commit a baseline report and do not edit code.

---

### Task 1: Replace the retired AI Studio IDs with GA IDs

**Files:**
- Modify: `src/Rook/Services/Vision/Image/Gemini/GeminiImageCapabilities.cs`
- Modify: `src/Rook.Tests/Handlers/VisionHandlerTests.cs`
- Modify: `src/Rook.Tests/Services/Vision/Generation/GeminiSyncShapeProviderFake.cs`
- Modify: `src/Rook.Tests/Services/Vision/Generation/MetadataPreservationFixture.cs`
- Modify: `src/Rook.Tests/Services/Vision/Image/GeminiImageProviderTests.cs`

**Interfaces:**
- Consumes: current provider `gemini`, short names `nano-banana-2`/`nano-banana-pro`, API-key transport.
- Produces: `GeminiImageCapabilities.NanoBanana2 == "gemini-3.1-flash-image"`, `NanoBananaPro == "gemini-3-pro-image"`, both status `ga`, unchanged default/short names.

- [ ] **Step 1: Change focused expectations first**

Update the active tests and fixtures so their exact values are:

```csharp
Assert.Equal("gemini-3.1-flash-image", GeminiImageCapabilities.ResolveShortName("nano-banana-2"));
Assert.Equal("gemini-3-pro-image", GeminiImageCapabilities.ResolveShortName("nano-banana-pro"));
```

The AI Studio request expectation must end with:

```text
/v1beta/models/gemini-3.1-flash-image:generateContent
```

Every active fake `modelVersion` becomes `gemini-3.1-flash-image`. Do not change historical files under `docs/`.

- [ ] **Step 2: Run the narrow RED test**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~GeminiImageProviderTests" `
    --verbosity minimal
```

Expected: failures show the existing preview IDs or preview URL. Stop if failures concern another behavior.

- [ ] **Step 3: Make the minimal production correction**

In `GeminiImageCapabilities.cs`, make only these semantic changes:

```csharp
public const string NanoBanana2 = "gemini-3.1-flash-image";
public const string NanoBananaPro = "gemini-3-pro-image";
```

For both existing `ImageCapability` records, change only `Status: "preview"` to `Status: "ga"`. Preserve provider, default, short names, resolutions, aspect ratios, maximum references, and generation/editing flags byte-for-byte otherwise.

- [ ] **Step 4: Run GREEN tests and the active-surface scan**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~VisionHandlerTests|FullyQualifiedName~GeminiImageProviderTests|FullyQualifiedName~GeminiImageOptionsCodecTests|FullyQualifiedName~DefaultImageProviderRegistryTests" `
    --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'AI Studio GA-ID gate failed' }

$remaining = @(rg -n 'gemini-3\.1-flash-image-preview|gemini-3-pro-image-preview' src/Rook src/Rook.Tests)
if ($remaining.Count) { throw "Retired active ID remains: $($remaining -join '; ')" }
git diff --check
```

- [ ] **Step 5: Enforce exact Task 1 scope and commit production commit 1**

```powershell
$expected = @(
    'src/Rook/Services/Vision/Image/Gemini/GeminiImageCapabilities.cs',
    'src/Rook.Tests/Handlers/VisionHandlerTests.cs',
    'src/Rook.Tests/Services/Vision/Generation/GeminiSyncShapeProviderFake.cs',
    'src/Rook.Tests/Services/Vision/Generation/MetadataPreservationFixture.cs',
    'src/Rook.Tests/Services/Vision/Image/GeminiImageProviderTests.cs'
) | Sort-Object
$actual = @(git diff --name-only | Sort-Object)
if (($actual -join "`n") -ne ($expected -join "`n")) { throw "Task 1 scope mismatch: $($actual -join ', ')" }
git add -- $expected
git commit -m "fix(vision): move AI Studio image models to GA IDs"
```

Checkpoint for review. Do not amend this commit during Task 2 except to correct a concrete Task 1 defect.

---

### Task 2: Add the complete Vertex RookVision integration

This task has three RED/GREEN checkpoints but ends in one production commit. Do not create intermediate commits or later squash unrelated commits.

**Files:**
- Create/modify exactly the Production commit 2 paths in the File Map.

**Interfaces:**
- Consumes:
  - `VertexStore.production()` and `VertexRuntimeArguments` from the accepted Python Vertex implementation.
  - `ChatServiceManager.AcquireOwnedConnectionAsync(CancellationToken)` from managed lifecycle ownership.
  - `IVertexAccessTokenSource.AcquireAsync(string, CancellationToken)` from neutral RookVision composition.
  - Existing `GeminiImageOptions`, image request/artifact pipeline, and `GenerationError`.
- Produces:
  - Python `VertexTokenLeaseService.acquire(model: str) -> VertexTokenLease` through the exact internal route.
  - Managed `VertexAccessTokenResult` and one single-step asynchronous `VertexImageProvider`.
  - One `vertex_ai` registration and exact RookVision display.

#### Checkpoint A: Python token lease and exact internal route

- [ ] **Step 1: Write `test_vertex_token_lease.py` RED contracts**

Define fakes for a store, injected UTC clock, injected monotonic clock, and blocking refresher. Pin these behaviors:

```python
async def test_cache_hit_re_reads_current_record_before_returning(): ...
async def test_signed_out_record_clears_cache_and_rejects(): ...
async def test_regional_record_fails_before_refresh(): ...
async def test_wrong_model_fails_before_store_access(): ...
async def test_matching_token_with_more_than_300_seconds_is_reused(): ...
async def test_token_at_300_second_boundary_is_refreshed(): ...
async def test_concurrent_misses_share_one_refresh(): ...
async def test_generation_change_during_refresh_discards_token(): ...
async def test_refresh_transport_is_20_seconds_and_outer_budget_is_30(): ...
async def test_lock_wait_and_refresh_share_the_same_30_second_budget(): ...
async def test_lock_wait_leaves_only_remaining_budget_for_each_google_request(): ...
async def test_expiry_must_be_finite_and_future(): ...
async def test_access_token_never_appears_in_failure_or_log_projection(): ...
```

Use the exact data contracts:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class RefreshedVertexAccessToken:
    access_token: str = field(repr=False)
    expires_at_unix_seconds: int

@dataclass(frozen=True)
class VertexTokenLease:
    access_token: str = field(repr=False)
    expires_at_unix_seconds: int
    project_id: str
    location: str
    generation: str
```

- [ ] **Step 2: Add exact-route RED tests to `test_chat_server.py`**

Inject a fake token service into `create_chat_app`. Add one parameterized status table covering:

```python
[
    ("origin", 403, "vertex_internal_access_denied"),
    ("nonce_absent", 403, "vertex_internal_access_denied"),
    ("nonce_wrong", 403, "vertex_internal_access_denied"),
    ("method", 405, "vertex_internal_method_not_allowed"),
    ("malformed", 400, "vertex_internal_request_invalid"),
    ("unknown_field", 400, "vertex_internal_request_invalid"),
    ("wrong_model", 400, "vertex_image_model_unsupported"),
    ("regional", 400, "vertex_model_region_unsupported"),
    ("signed_out", 409, "vertex_signed_out"),
    ("oauth_revoked", 409, "vertex_authorization_revoked"),
    ("adc_unavailable", 409, "vertex_adc_unavailable"),
    ("service_account_unavailable", 409, "vertex_service_account_unavailable"),
    ("record_invalid", 409, "vertex_request_failed"),
    ("generation_changed", 409, "vertex_authorization_changed"),
    ("dependency", 503, "vertex_auth_dependency_missing"),
    ("timeout", 504, "vertex_token_issuance_timeout"),
    ("internal", 500, "vertex_token_issuance_failed"),
]
```

Every case asserts JSON `success is False`, exact `error.code`, fixed bounded `error.message`, `Cache-Control == "no-store"`, and zero refresh for rejections before local configuration. Test both the allowed WebView Origin and an arbitrary Origin; both must receive 403. Test `OPTIONS` with Origin receives 403. The JSON 405 test must send `GET` without an `Origin` header and with the exact valid `X-Rook-Session` nonce so it passes nonce admission and reaches method admission; require `Allow: POST`. A missing or incorrect nonce remains a shaped 403 even for `GET`.

The 200 test asserts a future integer expiry and exact five lease fields. Add a source/schema assertion that no raw MCP tool name or schema exposes `vertex_access_token`, `vertex_token`, or the internal path.

- [ ] **Step 3: Run Python RED tests**

```powershell
Set-Location "$worktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_vertex_token_lease.py `
    tests/test_chat_server.py `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload" `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found" -q
```

Expected: missing module, missing route, or missing injected service failures only.

- [ ] **Step 4: Implement the minimal token lease**

Create `vertex_token_lease.py` with these constants and boundaries:

```python
VERTEX_IMAGE_MODEL_KEY = "vertex_ai/gemini-3.1-flash-image"
VERTEX_IMAGE_LOCATION = "global"
TOKEN_REUSE_SLACK_SECONDS = 300
TOKEN_TRANSPORT_TIMEOUT_SECONDS = 20.0
TOKEN_ISSUANCE_TIMEOUT_SECONDS = 30.0
```

`VertexTokenLeaseService.acquire()` must establish one monotonic 30-second deadline for the complete operation—including refresh-lock waiting and all Google transport calls—then execute the admitted work in this order:

```python
async def acquire(self, model: str) -> VertexTokenLease:
    deadline = monotonic() + TOKEN_ISSUANCE_TIMEOUT_SECONDS
    return await asyncio.wait_for(
        self._acquire_admitted(model, deadline),
        timeout=remaining_seconds(deadline),
    )

async def _acquire_admitted(self, model: str, deadline: float) -> VertexTokenLease:
    validate_exact_model(model)               # no generic family admission
    record = store.read()                     # every admitted request
    require_record_or_clear_cache(record)     # signed out fails before cache reuse
    require_global(record.region)             # before refresh
    async with refresh_lock:                  # lock wait is inside outer budget
        record = store.read()                 # recheck after waiting
        require_record_or_clear_cache(record)
        if cache_matches_and_is_fresh(record):
            return cached_lease
        runtime = store.resolve_runtime()
        refreshed = await asyncio.to_thread(
            refresh_access_token,
            runtime,
            deadline,
            monotonic,
        )
        current = store.read()                # post-refresh race fence
        require_same_generation(record, current)
        validate_token_and_expiry(refreshed)
        cache = refreshed + project/location/generation
        return cache
```

The google-auth request callable must share that exact monotonic deadline. On every Google request invocation, recompute `remaining = deadline - monotonic()`; fail immediately when it is non-positive, otherwise replace the incoming/default transport timeout with `min(TOKEN_TRANSPORT_TIMEOUT_SECONDS, remaining)`. A refresher that begins after 29 seconds of lock waiting therefore receives at most the remaining approximately one second, never a fresh 20-second allowance. The outer `wait_for` bounds the async caller while the per-request cap bounds work in the worker thread; neither creates an independent deadline. Test multiple request invocations against the same deadline and prove no request resets the aggregate budget. Convert google-auth's UTC credential expiry to a finite integer Unix timestamp. Preserve external cancellation. Map only stable `VertexAuthError` codes and fixed messages, and never interpolate the caught exception into route logs or responses.

Modify `vertex_backend._default_token_loader(runtime)` to establish the same bounded monotonic refresh deadline, call the shared refresh primitive, and return only `.access_token`, preserving all existing readiness callers and tests.

- [ ] **Step 5: Implement the exact route without changing other CORS behavior**

In `server.py`:

- add an injected `VertexTokenLeaseService` app key and optional `create_chat_app(..., vertex_token_service=None)` test seam; when omitted, construct the production service without reading credentials or performing network work;
- add one exact path constant and `app.router.add_route("*", path, handler)` so aiohttp never generates an unshaped 405 for it;
- branch at the start of the existing middleware for this exact path only;
- apply admission in the order Origin, expected nonce, method, body/model, local configuration, refresh;
- return through one helper that always sets `Cache-Control: no-store` and never adds CORS headers to this path;
- reject unknown top-level fields;
- return only the two fixed envelopes from the specification.

Do not alter existing WebView route behavior: the trusted WebView Origin remains valid for `/agent/chat/*` and `/knowledge/*`.

- [ ] **Step 6: Run Checkpoint A GREEN**

```powershell
.\.venv\Scripts\python.exe -m pytest `
    tests/test_vertex_token_lease.py `
    tests/test_vertex_backend.py `
    tests/test_chat_server.py `
    tests/test_vertex_runtime_integration.py `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload" `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found" -q
uv pip check --python .\.venv\Scripts\python.exe
Set-Location $worktree
git diff --check
```

Pause for checkpoint review. Do not commit yet.

#### Checkpoint B: Managed cold-start token source and neutral composition

- [ ] **Step 7: Write managed RED tests for the lease contract and adapter**

Create `VertexImageProviderTests.cs` and `ChatServiceVertexAccessTokenSourceTests.cs`; extend the existing lifecycle/root tests. Pin these exact managed signatures. `VertexAccessTokenLease` must use a redacted `ToString()` implementation rather than a compiler-generated record representation that would print the bearer token:

```csharp
internal sealed record VertexAccessTokenLease(
    string AccessToken,
    long ExpiresAtUnixSeconds,
    string ProjectId,
    string Location,
    string Generation)
{
    public override string ToString() => "VertexAccessTokenLease(<redacted>)";
}

internal sealed record VertexAccessTokenFailure(
    string Code,
    string Message,
    bool Retryable);

internal sealed record VertexAccessTokenResult(
    VertexAccessTokenLease? Lease,
    VertexAccessTokenFailure? Failure);

internal interface IVertexAccessTokenSource
{
    Task<VertexAccessTokenResult> AcquireAsync(
        string qualifiedModelKey,
        CancellationToken cancellationToken);
}

// Defined at the UI lifecycle boundary in ChatServiceManager.cs, not in
// the neutral Vision token contract.
internal sealed record ChatServiceConnectionSnapshot(
    Uri BaseUri,
    string SessionNonce);
```

Tests must prove:

- cold acquisition calls the manager-owned ensure/snapshot operation exactly once;
- URI and nonce come from one snapshot, not separate delegates/properties;
- the adapter never reads discovery and never reads `ChatServiceManager.SessionNonce` directly;
- the POST has no `Origin`, uses `X-Rook-Session`, exact model JSON, and a 35-second client ceiling;
- malformed, expired, non-global, invalid-generation, wrong-shape, failed, and timeout responses become fixed `VertexAccessTokenFailure` values;
- success tokens are held only in the returned lease and are absent from `ToString()`, exception messages, and logs;
- `RookSubsystemRoot` accepts only `IVertexAccessTokenSource` and contains no `Rook.UI.Chat` reference;
- `RookPlugin.OnLoad` supplies the one concrete adapter before any image reconciliation/access.
- both `VisionWebSurface` and `NativeGhBridgeRegistrar` inject the exact root image registry into their `VisionHandler`, so no duplicate unavailable Vertex registration is created.

- [ ] **Step 8: Run managed lifecycle RED tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~ChatServiceManagerTests|FullyQualifiedName~ChatServiceVertexAccessTokenSourceTests|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~RookPluginLifecycleSourceTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~VisionWebSurfaceTests" `
    --verbosity minimal
```

Expected: missing contract, snapshot method, adapter, and composition failures only.

- [ ] **Step 9: Implement the atomic manager snapshot**

Refactor only enough of `EnsureStartedAsync` to share one under-gate core. Add:

```csharp
internal async Task<ChatServiceConnectionSnapshot?>
    AcquireOwnedConnectionAsync(CancellationToken ct)
```

It must acquire `_gate` once, ensure/start and validate the owned service while still holding the gate, require `ServiceAvailable`, non-null `BaseUri`, and a non-empty current `SessionNonce`, then construct the immutable pair before releasing the gate. It must not expose discovery paths, process handles, or a separately mutable nonce.

- [ ] **Step 10: Implement the neutral token-source contract and adapter**

Create `VertexAccessTokenContract.cs` with the lease, failure, result, and source signatures above plus one unavailable implementation returning `vertex_token_service_unavailable`; it must not throw during registry creation. Define `ChatServiceConnectionSnapshot` in `ChatServiceManager.cs` under `Rook.UI.Chat`, because it is manager-owned lifecycle state rather than part of the neutral Vision contract.

Create `ChatServiceVertexAccessTokenSource.cs` in `Rook.UI.Chat`. Its constructor accepts:

```csharp
Func<CancellationToken, Task<ChatServiceConnectionSnapshot?>> acquireConnection;
HttpClient httpClient;
Func<DateTimeOffset> utcNow;
```

Production exposes one reusable `Instance`. The adapter obtains one snapshot, posts once, strictly parses the fixed envelope, validates future expiry/location/generation shape, and returns a typed result. It never caches a token.
Apply the 35-second route ceiling with a linked cancellation-token source around the HTTP send, so an injected `HttpClient` cannot silently weaken it. Preserve caller cancellation as interruption; translate only expiry of the adapter-owned ceiling into the fixed token-service timeout failure.

- [ ] **Step 11: Compose once without making the root UI-aware**

Add an optional `IVertexAccessTokenSource` to the internal test constructor of `RookSubsystemRoot`; the private singleton begins with the unavailable source. Add one exact, thread-safe, idempotent production configuration method that:

- accepts only `IVertexAccessTokenSource`;
- permits the same instance to be supplied again;
- rejects a different replacement;
- rejects first configuration after `_imageJobs.IsValueCreated`;
- contains no UI/process/discovery logic.

In `RookPlugin.OnLoad`, before attaching deferred startup hooks, configure the root with `ChatServiceVertexAccessTokenSource.Instance`. This is exact feature composition, not a generic service registry.

The two existing managed Vision composition helpers in `VisionWebSurface` and `NativeGhBridgeRegistrar` must pass `RookSubsystemRoot.Instance.ImageJobs.Registry` into their `VisionHandler` instances. This keeps model enumeration, UI image jobs, and the existing managed Vision callback on the same configured registry; do not construct a second Vertex provider with the unavailable default. Extend their existing shared-singleton tests to assert reference equality for the private `_imageProviderRegistry` field.

- [ ] **Step 12: Run Checkpoint B GREEN**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~ChatServiceManagerTests|FullyQualifiedName~ChatServiceVertexAccessTokenSourceTests|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~RookPluginLifecycleSourceTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~VisionWebSurfaceTests" `
    --verbosity minimal
git diff --check
```

Pause for checkpoint review. Do not commit yet.

#### Checkpoint C: Vertex provider, catalog, UI, and persistence boundary

- [ ] **Step 13: Write provider/catalog RED tests**

Add tests that require:

```csharp
VertexImageCapabilities.ProviderName == "vertex_ai"
VertexImageCapabilities.RookModelKey == "vertex_ai/gemini-3.1-flash-image"
VertexImageCapabilities.GoogleModelId == "gemini-3.1-flash-image"
VertexImageCapabilities.RequiredLocation == "global"
```

The provider tests must cover:

- token failure returns before Google transport;
- prefix stripping accepts only the exact key;
- non-global lease fails before Google transport;
- URL host/path is the exact global endpoint;
- one Bearer header is sent and never logged;
- request body and inline-image success parsing match AI Studio semantics;
- caller cancellation remains `Interrupted`;
- provider timeout/5xx is retryable `DependencyUnavailable`;
- 429 maps to `QuotaExceeded`;
- allowlisted Google status identifiers survive with fixed messages;
- hostile message/body/header/token sentinels do not occur in `Message`, `ProviderErrorCode`, `ProviderDetail`, outcome serialization, or job ledger projection;
- unknown/malformed errors become `UNKNOWN` and `ProviderDetail` is null;
- `SubmitAsync` returns the completed `SyncSubmitOutcome` without polling.

Registry/composition/UI tests require:

- unqualified `gemini-3.1-flash-image` resolves provider `gemini`;
- qualified `vertex_ai/gemini-3.1-flash-image` resolves provider `vertex_ai`;
- Vertex registration has exactly one model and zero secret requirements;
- credential metadata remains exactly `gemini`, `fal`, and `replicate`;
- AI Studio short-name default remains selected;
- the rendered Vertex option is exactly `Vertex AI — Nano Banana 2`, not `Vertex AI — Nano Banana 2 · Vertex AI`;
- for the exact AI Studio and Vertex Nano Banana 2 keys, the `4K` resolution option is rendered as `4K (Preview)` while its submitted value remains `4K`; acceptance defaults to 1K/2K.

- [ ] **Step 14: Run provider/catalog RED tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~VertexImageProviderTests|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~VisionWebSurfaceTests" `
    --verbosity minimal
```

Expected: missing Vertex types/registration/display failures only.

- [ ] **Step 15: Extract only the pure Gemini wire codec**

Move the existing request-body builder and successful inline-image parser from `GeminiImageProvider` into `GeminiImageWireCodec` as internal static operations. Both providers may call:

```csharp
internal static string BuildRequestJson(
    ImageGenerationRequest request,
    IReadOnlyDictionary<MediaRef, ResolvedMedia> resolvedMedia);

internal static ProviderSubmitOutcome ParseSuccess(string responseJson);
```

Do not move or share `GeminiImageProvider.MapProviderError`. Run `GeminiImageProviderTests` immediately after the extraction to prove AI Studio behavior remains unchanged.

- [ ] **Step 16: Implement the one-model Vertex registration and provider**

`VertexImageCapabilities` contains one `ImageCapability` whose `Id` is the qualified Rook key and whose display name is `Vertex AI — Nano Banana 2`. Preserve the existing Nano Banana 2 resolutions, ratios, reference limit, and generation/editing flags. Set the model status to `ga`; in `app.js`, annotate the `4K` resolution label as `4K (Preview)` for the exact AI Studio and Vertex Nano Banana 2 keys without changing the submitted value or adding another model.

`VertexImageProviderRegistration`:

- provider name `vertex_ai`;
- `ImageSubmissionMode.Sync` because the async submit completes in one step;
- one model dictionary entry;
- `Array.Empty<ProviderSecretRequirement>()`;
- existing `GeminiImageOptionsCodec`;
- a small Vertex-specific pricing model that reports an unverified zero estimate with distinct provenance and no AI Studio pricing label.

`VertexImageProvider.SubmitAsync` must:

1. validate exact request/options/model;
2. await one token-source acquisition with caller cancellation;
3. validate `global`, project, expiry, and generation;
4. strip only exact `vertex_ai/` and require the one Google model ID;
5. construct the exact global URL using escaped path segments;
6. send one Bearer-authenticated request with the existing five-minute HttpClient ceiling;
7. parse success through `GeminiImageWireCodec`;
8. map failure through a new local allowlist and fixed messages with null `ProviderDetail`.

Never include `responseJson`, raw Google message, headers, token, prompt, or URL in a `GenerationError` or log.

- [ ] **Step 17: Register and render the provider**

Add an optional `IVertexAccessTokenSource? vertexTokenSource = null` final parameter to `CreateImageRegistrations`; map null only to the unavailable implementation so existing isolated/default `VisionHandler` construction remains source-compatible and cannot start a service. The production root must always pass its explicitly configured source. Append one `VertexImageProviderRegistration`, and do not add `vertex_ai` to `CreateCredentialMetadata`.

Pass the configured neutral source from the root's image lazy initializer. In `app.js`, map `vertex_ai` to `Vertex AI`, render the already-qualified display exactly once, and apply the exact Nano Banana 2 `4K (Preview)` label rule to both provider keys. Do not change the static fallback catalog or AI Studio default.

- [ ] **Step 18: Run Checkpoint C GREEN and all Task 2 focused tests**

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release `
    -p:RhinoPluginDir="$noDeploy" `
    --filter "FullyQualifiedName~GeminiImageProviderTests|FullyQualifiedName~VertexImageProviderTests|FullyQualifiedName~DefaultImageProviderRegistryTests|FullyQualifiedName~VisionProviderRegistrationsTests|FullyQualifiedName~ChatServiceManagerTests|FullyQualifiedName~ChatServiceVertexAccessTokenSourceTests|FullyQualifiedName~RookSubsystemRootTests|FullyQualifiedName~RookPluginLifecycleSourceTests|FullyQualifiedName~NativeGhBridgeRegistrarTests|FullyQualifiedName~VisionWebSurfaceTests" `
    --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'Managed Vertex RookVision gate failed' }

Set-Location "$worktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_vertex_token_lease.py `
    tests/test_vertex_backend.py `
    tests/test_chat_server.py `
    tests/test_vertex_runtime_integration.py `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload" `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found" -q
uv pip check --python .\.venv\Scripts\python.exe
Set-Location $worktree
uv --directory mcp_server lock --check
git diff --check
```

- [ ] **Step 19: Run fail-closed source/security guards**

```powershell
$forbiddenModels = @(rg -n 'vertex_ai/gemini-3-pro-image|vertex_ai/veo|vertex_ai/.+preview' src/Rook mcp_server/src/rook)
if ($forbiddenModels.Count) { throw "Unexpected Vertex model surface: $($forbiddenModels -join '; ')" }
$previewIds = @(rg -n 'gemini-3\.1-flash-image-preview|gemini-3-pro-image-preview' src/Rook src/Rook.Tests)
if ($previewIds.Count) { throw "Retired active ID returned: $($previewIds -join '; ')" }
$mcpExposure = @(rg -n 'vertex_access_token|vertex_token' mcp_server/src/rook/server.py)
if ($mcpExposure.Count) { throw "Token route leaked into MCP surface: $($mcpExposure -join '; ')" }
$rawPersistence = @(rg -n 'ProviderDetail:\s*(detail|response|root)|responseJson.*ProviderDetail' src/Rook/Services/Vision/Image/Vertex)
if ($rawPersistence.Count) { throw "Raw Vertex provider detail can persist: $($rawPersistence -join '; ')" }
```

Inspect the complete diff after the mechanical guards. Confirm no credential, access token, project ID, test identity, or desktop OAuth client content exists in tracked files.

- [ ] **Step 20: Enforce exact Task 2 scope and commit production commit 2**

Use this exact Production commit 2 set. Compare `git diff --name-only HEAD` against it and stop on every missing or additional path. Then stage those same paths:

```powershell
$task2Expected = @(
    'mcp_server/src/rook/providers/vertex_token_lease.py',
    'mcp_server/src/rook/providers/vertex_backend.py',
    'mcp_server/src/rook/agent/chat/server.py',
    'mcp_server/tests/test_vertex_token_lease.py',
    'mcp_server/tests/test_vertex_backend.py',
    'mcp_server/tests/test_chat_server.py',
    'src/Rook/Services/Vision/Image/Gemini/GeminiImageProvider.cs',
    'src/Rook/Services/Vision/Image/Gemini/GeminiImageWireCodec.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexAccessTokenContract.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexImageCapabilities.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexImageProvider.cs',
    'src/Rook/Services/Vision/Image/Vertex/VertexImageProviderRegistration.cs',
    'src/Rook/Services/Vision/VisionProviderRegistrations.cs',
    'src/Rook/UI/Chat/ChatServiceManager.cs',
    'src/Rook/UI/Chat/ChatServiceVertexAccessTokenSource.cs',
    'src/Rook/RookSubsystemRoot.cs',
    'src/Rook/RookPlugin.cs',
    'src/Rook/UI/Vision/VisionWebSurface.cs',
    'src/Rook/InternalBridge/NativeGhBridgeRegistrar.cs',
    'src/Rook/UI/Vision/Resources/app.js',
    'src/Rook.Tests/Services/Vision/Image/VertexImageProviderTests.cs',
    'src/Rook.Tests/Services/Vision/Image/DefaultImageProviderRegistryTests.cs',
    'src/Rook.Tests/Services/Vision/VisionProviderRegistrationsTests.cs',
    'src/Rook.Tests/UI/Chat/ChatServiceManagerTests.cs',
    'src/Rook.Tests/UI/Chat/ChatServiceVertexAccessTokenSourceTests.cs',
    'src/Rook.Tests/RookSubsystemRootTests.cs',
    'src/Rook.Tests/Plugin/RookPluginLifecycleSourceTests.cs',
    'src/Rook.Tests/InternalBridge/NativeGhBridgeRegistrarTests.cs',
    'src/Rook.Tests/UI/Vision/VisionWebSurfaceTests.cs'
) | Sort-Object
$task2Actual = @(git diff --name-only HEAD | Sort-Object)
if (($task2Actual -join "`n") -ne ($task2Expected -join "`n")) {
    throw "Task 2 scope mismatch: $($task2Actual -join ', ')"
}
git add -- $task2Expected
git commit -m "feat(vision): add Vertex Nano Banana 2 provider"
```

After commit, require:

```powershell
$planCommit = (git rev-parse 'plan/vertex-rookvision-nano-banana-2-2026-08-27-approved^{}').Trim()
$task1 = (git rev-parse HEAD^).Trim()
$task2 = (git rev-parse HEAD).Trim()
if ((git rev-list --count "$planCommit..$task2") -ne 2) { throw 'Production boundary is not exactly two commits' }
git diff --check "$planCommit..$task2"
if (git status --porcelain) { throw 'Worktree dirty after Task 2 commit' }
```

Return both exact production SHAs for review before PR work.

---

### Task 3: Review, merge, build from immutable provenance, and run installed acceptance

**Files:**
- No production changes.
- Optional docs-only evidence after acceptance: `docs/superpowers/reports/2026-08-17-vertex-rookvision-nano-banana-2-acceptance.md` in a separately reviewed evidence commit.

**Interfaces:**
- Consumes: reviewed two-commit feature head, approved AI Studio test key, approved Vertex identity/project with location `global`, existing release/deploy workflow.
- Produces: regular private merge SHA, installed payload derived from that SHA, two explicit 1K/2K billing-path results, redacted acceptance evidence.

- [ ] **Step 1: Run final pre-PR focused gates**

Run the complete Task 1 and Task 2 test commands again at the reviewed head. Also run the full managed layer and the closed Python files—not the repository-wide multi-language suite:

```powershell
$worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\vertex-rookvision-nano-banana-2-design'
$noDeploy = Join-Path $env:TEMP 'rook-vertex-vision-no-deploy'
Set-Location $worktree
dotnet test src\Rook.Tests\Rook.Tests.csproj -c Release -p:RhinoPluginDir="$noDeploy" --verbosity minimal
if ($LASTEXITCODE -ne 0) { throw 'Full managed suite failed' }
Set-Location "$worktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_vertex_token_lease.py `
    tests/test_vertex_backend.py `
    tests/test_chat_server.py `
    tests/test_vertex_runtime_integration.py `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_graph_returns_valid_payload" `
    --deselect "mcp_server/tests/test_chat_server.py::TestKnowledgeGraphRoutes::test_knowledge_note_found" -q
uv pip check --python .\.venv\Scripts\python.exe
Set-Location $worktree
uv --directory mcp_server lock --check
git diff --check
```

- [ ] **Step 2: Enforce complete plan-to-head scope**

Compare every `git diff --name-only $planCommit..HEAD` path to the union of the two production path tables. Require exactly two commits in that range and inspect both diffs. The first commit may contain only the five GA-ID paths; the second may contain only the Vertex integration paths. No fixup, generated output, `.env`, key, token, artifact, or unrelated documentation is permitted.

- [ ] **Step 3: Recheck current main, open the PR, and merge normally**

Fetch current `origin/main`. If it moved, compare all moved paths to the complete approved production set. Stop on overlap. Otherwise require a clean synthetic merge, push the exact reviewed head, and open a private PR against current `main`.

After review, use a regular merge commit—no squash or rebase. Record and verify:

```powershell
$rookMerge = $env:ROOK_VERTEX_VISION_MERGE_SHA
$reviewedHead = $env:ROOK_VERTEX_VISION_REVIEWED_HEAD_SHA
$currentMainBeforeMerge = $env:ROOK_VERTEX_VISION_PREMERGE_MAIN_SHA
foreach ($entry in @($rookMerge, $reviewedHead, $currentMainBeforeMerge)) {
    if ($entry -notmatch '^[0-9a-f]{40}$') { throw 'Recorded merge provenance must use exact 40-hex SHAs' }
}
$parents = @((git rev-list --parents -n 1 $rookMerge).Trim().Split(' '))
if ($parents.Count -ne 3 -or $parents[1] -ne $currentMainBeforeMerge -or $parents[2] -ne $reviewedHead) {
    throw 'Private merge provenance mismatch'
}
git fetch origin
if ((git rev-parse origin/main).Trim() -ne $rookMerge) { throw 'origin/main does not point to the private merge' }
```

- [ ] **Step 4: Create a detached build checkout at the merge SHA**

```powershell
$rookMerge = $env:ROOK_VERTEX_VISION_MERGE_SHA
if ($rookMerge -notmatch '^[0-9a-f]{40}$') { throw 'ROOK_VERTEX_VISION_MERGE_SHA must be an exact 40-hex SHA' }
$rookRepo = 'C:\Users\aryan\source\repos\Rook'
$releaseRook = "C:\Users\aryan\source\repos\Rook\.worktrees\vertex-vision-release-$($rookMerge.Substring(0,8))"
if (Test-Path -LiteralPath $releaseRook) { throw 'Detached release checkout already exists' }
git -C $rookRepo worktree add --detach $releaseRook $rookMerge
if (git -C $releaseRook status --porcelain) { throw 'Detached release checkout is dirty' }

$chirpRepo = 'C:\Users\aryan\source\repos\Chirp'
$chirpSha = '1f954c27f796ecfe830d02a76497deffcf31cfc2'
$releaseChirp = "C:\Users\aryan\source\repos\Chirp\.worktrees\vertex-vision-release-$($chirpSha.Substring(0,8))"
if (Test-Path -LiteralPath $releaseChirp) { throw 'Detached Chirp release checkout already exists' }
git -C $chirpRepo fetch origin --prune
git -C $chirpRepo cat-file -e "$chirpSha^{commit}"
if ($LASTEXITCODE -ne 0) { throw 'Accepted Chirp merge commit is unavailable locally' }
git -C $chirpRepo worktree add --detach $releaseChirp $chirpSha
if ((git -C $releaseChirp rev-parse HEAD).Trim() -ne $chirpSha) { throw 'Detached Chirp checkout is not at the accepted merge' }
if (git -C $releaseChirp status --porcelain) { throw 'Detached Chirp release checkout is dirty' }
```

Chirp is unchanged by this feature. Build only from the detached clean checkout at accepted merge `1f954c27f796ecfe830d02a76497deffcf31cfc2`; do not select a mutable branch tip or require the canonical checkout to be clean.

- [ ] **Step 5: Stage the sealed Python payload from the detached checkout**

Derive the current version; do not bump it in this PR:

```powershell
$rookMerge = $env:ROOK_VERTEX_VISION_MERGE_SHA
if ($rookMerge -notmatch '^[0-9a-f]{40}$') { throw 'ROOK_VERTEX_VISION_MERGE_SHA must be an exact 40-hex SHA' }
$releaseRook = "C:\Users\aryan\source\repos\Rook\.worktrees\vertex-vision-release-$($rookMerge.Substring(0,8))"
$chirpSha = '1f954c27f796ecfe830d02a76497deffcf31cfc2'
$releaseChirp = "C:\Users\aryan\source\repos\Chirp\.worktrees\vertex-vision-release-$($chirpSha.Substring(0,8))"
if ((git -C $releaseChirp rev-parse HEAD).Trim() -ne $chirpSha) { throw 'Detached Chirp checkout moved after admission' }
if (git -C $releaseChirp status --porcelain) { throw 'Detached Chirp release checkout is dirty before packaging' }
$releasePython = "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
$pyproject = Join-Path $releaseRook 'mcp_server\pyproject.toml'
$releaseVersion = (& $releasePython -c "import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))['project']['version'])" $pyproject).Trim()
if ($releaseVersion -notmatch '^\d+\.\d+\.\d+$') { throw 'Could not derive current release version' }
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\python-runtime\stage-rook-python-runtime.ps1" -RepoRoot $releaseRook
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\python-runtime\build-rook-python-wheelhouse.ps1" -Version $releaseVersion -RepoRoot $releaseRook -ChirpRoot $releaseChirp
powershell -NoProfile -ExecutionPolicy Bypass -File "$releaseRook\scripts\validate-python-wheelhouse.ps1" -Version $releaseVersion -RepoRoot $releaseRook
```

Require manifest `rook_git_sha == $rookMerge`, `chirp_git_sha == $chirpSha`, `google-auth==2.56.3`, exact wheel inventory/hash parity, both temporary `pip check`s, and no tracked changes.

- [ ] **Step 6: Close hosts, build, and deploy the merged candidate once**

Require Rhino, Grasshopper, Revit, Rook Chat, Chirp, and Rook MCP closed. Use the repository process guard twice and require the second result to report zero. Then run the canonical local deployment from the detached checkout:

```powershell
$rookMerge = $env:ROOK_VERTEX_VISION_MERGE_SHA
if ($rookMerge -notmatch '^[0-9a-f]{40}$') { throw 'ROOK_VERTEX_VISION_MERGE_SHA must be an exact 40-hex SHA' }
$releaseRook = "C:\Users\aryan\source\repos\Rook\.worktrees\vertex-vision-release-$($rookMerge.Substring(0,8))"
$releasePython = "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
$pyproject = Join-Path $releaseRook 'mcp_server\pyproject.toml'
$releaseVersion = (& $releasePython -c "import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))['project']['version'])" $pyproject).Trim()
Set-Location $releaseRook
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-mcp-processes.ps1 -Stop
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\rook-mcp-processes.ps1
if ($LASTEXITCODE -ne 0) { throw 'Rook MCP process guard is not clean' }
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\deploy-local-testing.ps1 -Configuration Release
```

This follows the existing build-release ordering, including RookBIM after Rook, but does not bump a version, compile an installer, publish, or modify public repositories. Stop on any environmental prerequisite rather than copying stale build outputs.

Verify installed provenance, exact source/wheelhouse/control-file hashes, `rook-mcp` version equal to `$releaseVersion`, `google-auth==2.56.3`, and `pip check` in both installed Rook and Chirp environments.

- [ ] **Step 7: Prepare the two explicit provider credentials without recording secrets**

Use the existing RookVision settings to configure an approved AI Studio test key. Configure the existing Vertex authorization record for an approved organization project with location exactly `global`, using the already accepted OAuth/ADC/service-account path. Record only:

```text
AI Studio test credential present: yes
Vertex authorization mode: oauth | adc | service_account
Vertex project approved: yes
Vertex location: global
Vertex billing/IAM/API approved: yes
```

Do not record key values, identity, project ID, client JSON, refresh tokens, access tokens, or environment contents. Stop if either billing path is unavailable; do not reinterpret one provider as proof of the other.

- [ ] **Step 8: Run the cold-start Vertex RookVision acceptance**

Start standalone Rhino from the installed candidate. Do not open Rook Chat. Verify no Rhino-owned chat-service process/discovery record exists before the request.

In RookVision:

1. capture an acceptance-owned disposable viewport/image;
2. select exactly `Vertex AI — Nano Banana 2`;
3. select `1K` (preferred) or `2K`, never `4K`;
4. use fixed prompt `Create a clean architectural concept variation with one unmistakable cobalt-blue circular marker.`;
5. submit once and require a terminal result within the existing 180-second RookVision UI polling bound, with a separate 60-second cleanup bound.

The five-minute provider HTTP ceiling remains unchanged. If the installed request does not finish inside the existing UI bound, acceptance fails and stops; do not change polling/timeout policy in this feature PR.

Require:

- one manager-owned Python service starts after submission;
- its discovery owner/PID match the current Rhino process;
- one non-empty image artifact completes;
- job evidence records provider `vertex_ai` and model `vertex_ai/gemini-3.1-flash-image`;
- no fallback or second provider request occurs;
- no `access_token`, `Authorization: Bearer`, OAuth client material, or token-like value appears in logs, artifacts, ledger, diagnostics, or evidence.

- [ ] **Step 9: Run the AI Studio GA-ID acceptance**

Using the same acceptance-owned input and fixed prompt:

1. explicitly select the separate AI Studio Nano Banana 2 entry;
2. keep `1K` or `2K`;
3. submit exactly once.

Require one non-empty artifact whose evidence records provider `gemini` and model `gemini-3.1-flash-image`. Confirm AI Studio remains the default selection on a fresh panel load. Do not call Nano Banana Pro and do not use Vertex fallback.

- [ ] **Step 10: Record bounded evidence and cleanup**

In `finally`, remove only acceptance-owned artifacts and close only the acceptance-owned Rhino/service processes. Preserve body and cleanup failures separately. A body failure is never converted to a pass by successful cleanup.

Record:

- private merge SHA and reviewed second parent;
- installed managed/Python provenance and dependency checks;
- exact two provider/model pairs;
- resolutions, success/failure, bounded durations, and artifact IDs/hashes;
- cold-start owner/PID evidence;
- redaction scan result;
- cleanup result;
- `technical_pass` versus `production_ready` using the already approved enterprise Vertex distinction.

If a durable repository report is required, create it afterward as a separate docs-only evidence commit. It must not alter or squash the two production commits and requires its own review. Public promotion and the 1.5.19 version/release sequence remain separate.

---

## Plan Self-Review Checklist

- [x] Every requirement in specification Sections 1–12 maps to Task 1, Task 2, or Task 3.
- [x] “Synchronous provider” does not appear; the provider is described as asynchronous and single-step.
- [x] Production history contains exactly two commits after the approved plan.
- [x] Task 1 changes exactly five active GA-ID paths.
- [x] Task 2 changes only the exact token-route, lifecycle, provider/catalog/UI, and focused-test paths.
- [x] The provider depends only on `IVertexAccessTokenSource`; UI/process ownership stays in the adapter/manager.
- [x] Every internal-route rejection has an exact status, fixed JSON, and `no-store` behavior.
- [x] No raw Google error body can reach `ProviderDetail` or another persistent surface.
- [x] Both installed billing paths are tested at 1K/2K from the merged candidate.
- [x] No installer, dependency, version, public promotion, Pro/Veo, Chirp, native C++, RookBIM, Grasshopper, or generic-framework change entered implementation scope.
