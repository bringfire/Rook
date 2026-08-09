# Enterprise Vertex Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent, project-based `vertex_ai/...` text provider for Rook Chat, Rook agents/DSPy, and Rook-managed Chirp while preserving Gemini AI Studio and RookVision exactly.

**Architecture:** One Rook Python authorization owner persists a versioned Vertex record, protects OAuth refresh authorization with Windows DPAPI, and serializes mutations through one named Windows mutex. Rook processes resolve Vertex arguments immediately before calls; managed Chirp receives one memory-only bootstrap through anonymous stdin and rejects stale generations before provider work. Phase 1 exposes no production UI, public HTTP login route, or MCP login tool.

**Tech Stack:** Python 3.10-compatible code on shipped CPython 3.11.9, LiteLLM 1.89.4, DSPy 3.3.0, proposed `google-auth==2.56.0`, `httpx`, Windows DPAPI/named synchronization through `ctypes`, FastAPI, pytest, and PowerShell packaging guards.

## Global Constraints

- Approved specification head: `1577d0ec8284cf2d6c83980e77702975edcd2473`.
- Chirp implementation base: `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`.
- Execution starts from clean isolated worktrees. The reviewed plan tag must resolve exactly to the execution plan; current Rook `origin/main` must merge cleanly with zero production-path overlap.
- Preserve Python `>=3.10`, shipped CPython `3.11.9`, LiteLLM `1.89.4`, DSPy `3.3.0`, and MCP `1.28.1`.
- Task 0 requires explicit reviewer admission for one direct dependency, `google-auth==2.56.0`, in both sealed environments. Stop if the resolved transitive set is not approved. Do not add `google-auth-oauthlib`, a login framework, broker, or generic secret store.
- `gemini/...` remains the existing Gemini Developer API / AI Studio provider. `vertex_ai/...` is separate. No migration, alias, shared credential, fallback, or implicit routing is allowed.
- RookVision image/Veo source, endpoints, models, settings, and provider registries are no-touch surfaces.
- The only OAuth scope is `https://www.googleapis.com/auth/cloud-platform`.
- Production store: `%LOCALAPPDATA%\Rook\data\provider_auth\vertex.json`. Tests inject a temporary store path; `ROOK_DATA_DIR` never redirects production credentials.
- Mutation mutex: `Local\BringFire.Rook.VertexAuth.v1`, `10,000` ms acquisition ceiling, `WAIT_OBJECT_0` and `WAIT_ABANDONED` accepted. Timeout changes no bytes.
- Managed-Chirp retirement event: `Local\BringFire.Rook.Chirp.VertexGenerationChanged.v1`, manual-reset, with a `10`-second retirement ceiling. A replacement rebinds the exact prior port because generated Chirp components embed it; failure to reclaim that port fails closed.
- Record schema version is `1`; each commit gets a fresh `secrets.token_hex(16)` generation.
- DPAPI is CurrentUser with `CRYPTPROTECT_UI_FORBIDDEN` and entropy bytes `BringFire.Rook.VertexAuth.v1`.
- Desktop OAuth binds `127.0.0.1` on OS port `0`, uses S256 PKCE and exact state, accepts one callback, and has a `180`-second ceiling.
- Login replaces a record only after a nonempty refresh token, usable access token, exact granted-scope set, and one successful `google-auth` refresh. Failure preserves prior bytes.
- Readiness is one non-generating `countTokens` request containing only the literal `Rook Vertex readiness probe`.
- Plaintext authorization never enters files, arguments, environment, logs, health, discovery, diagnostics, manifests, errors, or acceptance evidence.
- Phase 1 adds no Provider Setup card, installer credential page, OAuth MCP tool, OAuth HTTP route, model-default change, version bump, release build, or public promotion.
- Phase 3 owns Provider Setup and installer upgrade/repair/uninstall behavior.
- No live Google login or billable inference runs without reviewer approval naming a managed business identity, organization project, region, and model.

---

## File Map

### Rook

| Path | Responsibility |
| --- | --- |
| `mcp_server/pyproject.toml`, `mcp_server/uv.lock` | Admitted Google auth dependency and normal lock. |
| `mcp_server/src/rook/providers/vertex_auth.py` | Closed records, fixed store, DPAPI, mutex, atomic mutation, generation, runtime args. |
| `mcp_server/src/rook/providers/vertex_oauth.py` | Desktop OAuth, refresh admission, revocation, readiness, structured errors. |
| `mcp_server/src/rook/providers/vertex_backend.py` | Backend-only connect/save/disconnect plus Chirp recycle. |
| `mcp_server/src/rook/agent/model_profiles.py` | Read-only verification of existing native-cloud classification and no API-key slot. |
| `mcp_server/src/rook/agent/{base_agent.py,guardian.py,local_worker_model_transport.py}` | Fresh Vertex args at agent calls. |
| `mcp_server/src/rook/agent/chat/{chat_runner.py,runtime_health.py,model_status.py}` | Chat call and bounded Vertex status. |
| `mcp_server/src/rook/learning/dspy_config.py` | Vertex args for all DSPy LM constructors. |
| `mcp_server/src/rook/chirp_manager.py`, `mcp_server/src/rook/server.py` | Model-aware pipe bootstrap, recycling, and Chirp model forwarding. |
| `scripts/vertex_oauth_acceptance.py` | Source-only, non-MCP installed acceptance entry point. |
| `scripts/tests/python-runtime-packaging.tests.ps1` | Exact dependency in both sealed payloads. |
| `mcp_server/tests/test_vertex_*.py` | Store, OAuth, backend, runtime, and harness contracts. |
| `mcp_server/tests/test_chirp_manager.py`, `mcp_server/tests/test_server_contract_hardening.py` | Chirp bridge contracts. |
| `docs/superpowers/reports/2026-08-09-enterprise-vertex-*.md` | Probe and acceptance evidence. |

### Chirp

| Path | Responsibility |
| --- | --- |
| `pyproject.toml` | Admitted Google auth dependency. |
| `src/chirp/vertex_bootstrap.py` | One-time stdin envelope, runtime args, generation check, retirement event. |
| `src/chirp/__main__.py` | Private bootstrap admission before server import and bounded managed shutdown. |
| `src/chirp/server.py`, `src/chirp/adapter.py` | Vertex health, Vertex-only kwargs, and pre-call generation check. |
| `tests/test_vertex_bootstrap.py`, `tests/test_main.py`, `tests/test_server.py`, `tests/test_adapter.py` | Closed Chirp contracts. |

No other production file is pre-authorized. Stop for review if another file is required.

---

### Task 0: Pin provenance and admit the required Google dependency

**Files:**
- Create: `docs/superpowers/reports/2026-08-09-enterprise-vertex-task0-probe.md`
- Read only: installed LiteLLM Vertex source and both project metadata sets

**Interfaces:**
- Consumes: this isolated approved Rook planning worktree, current Rook `origin/main`, and Chirp `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`.
- Produces: a synchronized clean Rook implementation branch, a clean Chirp worktree, and a reviewer-approved dependency/runtime probe.

- [ ] **Step 1: Verify the plan tag and one-file planning scope**

```powershell
$specHead = '1577d0ec8284cf2d6c83980e77702975edcd2473'
$tag = 'plan/enterprise-vertex-provider-2026-08-09-approved'
$head = (git rev-parse HEAD).Trim()
if ((git rev-parse "$tag^{}").Trim() -ne $head) { throw 'Approval tag mismatch' }
if (-not (git merge-base --is-ancestor $specHead $head)) { throw 'Specification is not an ancestor' }
$paths = @(git diff --name-only "$specHead..$head")
if ($paths.Count -ne 1 -or $paths[0] -ne 'docs/superpowers/plans/2026-08-09-enterprise-vertex-provider.md') { throw "Unexpected planning scope: $($paths -join ', ')" }
if (git status --porcelain) { throw 'Planning worktree is dirty' }
```

- [ ] **Step 2: Synchronize this Rook worktree and create Chirp's worktree**

```powershell
$rookRepo = 'C:\Users\aryan\source\repos\Rook'
$rookWorktree = (Get-Location).Path
$chirpRepo = 'C:\Users\aryan\source\repos\Chirp'
$chirpWorktree = 'C:\Users\aryan\source\repos\Chirp\.worktrees\enterprise-vertex-provider'
$chirpBase = 'c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468'
git -C $rookRepo fetch origin --prune
$mergeBase = (git -C $rookWorktree merge-base HEAD origin/main).Trim()
$mainPaths = @(git -C $rookWorktree diff --name-only "$mergeBase..origin/main")
$plannedRoots = @('mcp_server', 'scripts/vertex_oauth_acceptance.py', 'scripts/tests/python-runtime-packaging.tests.ps1', 'docs/superpowers/reports')
foreach ($path in $mainPaths) {
    if ($plannedRoots | Where-Object { $path -eq $_ -or $path.StartsWith("$_/") }) {
        throw "Current main overlaps approved scope: $path"
    }
}
if ((git -C $rookWorktree rev-parse HEAD).Trim() -ne (git -C $rookWorktree rev-parse origin/main).Trim()) {
    git -C $rookWorktree merge --no-edit origin/main
    if ($LASTEXITCODE -ne 0) { throw 'Rook main synchronization failed' }
}
git -C $chirpRepo fetch origin --prune
if ((git -C $chirpRepo cat-file -t $chirpBase).Trim() -ne 'commit') { throw 'Chirp base unavailable' }
if (Test-Path -LiteralPath $chirpWorktree) { throw 'Chirp worktree already exists' }
git -C $chirpRepo worktree add $chirpWorktree -b codex/enterprise-vertex-provider $chirpBase
if (git -C $rookWorktree status --porcelain) { throw 'Rook worktree dirty after synchronization' }
if (git -C $chirpWorktree status --porcelain) { throw 'Chirp worktree dirty' }
```

If Rook `main` moved beyond the spec baseline, require a clean synthetic merge and zero overlap with the File Map before continuing.

- [ ] **Step 3: Prove current absence and LiteLLM's dependency**

```powershell
$pythons = @("$env:LOCALAPPDATA\Rook\venv\Scripts\python.exe", "$env:LOCALAPPDATA\Rook\app\chirp\.venv\Scripts\python.exe")
foreach ($python in $pythons) {
    & $python -c "import importlib.util, litellm; assert litellm.__version__ == '1.89.4'; assert importlib.util.find_spec('google.auth') is None"
}
$source = Get-Content -Raw "$env:LOCALAPPDATA\Rook\venv\Lib\site-packages\litellm\llms\vertex_ai\vertex_llm_base.py"
foreach ($needle in @('google.oauth2.credentials', 'google.auth.transport.requests', 'vertex_credentials')) {
    if (-not $source.Contains($needle)) { throw "Missing LiteLLM seam: $needle" }
}
```

- [ ] **Step 4: Resolve `google-auth==2.56.0` in disposable project copies**

```powershell
$probeRoot = Join-Path $env:TEMP ("rook-vertex-dependency-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $probeRoot | Out-Null
try {
    git -C $rookWorktree archive --format=zip --output="$probeRoot\rook.zip" HEAD mcp_server
    if ($LASTEXITCODE -ne 0) { throw 'Rook probe archive failed' }
    Expand-Archive -LiteralPath "$probeRoot\rook.zip" -DestinationPath $probeRoot
    git -C $chirpWorktree archive --format=zip --output="$probeRoot\chirp.zip" HEAD
    if ($LASTEXITCODE -ne 0) { throw 'Chirp probe archive failed' }
    New-Item -ItemType Directory -Path "$probeRoot\Chirp" | Out-Null
    Expand-Archive -LiteralPath "$probeRoot\chirp.zip" -DestinationPath "$probeRoot\Chirp"
    foreach ($project in @("$probeRoot\mcp_server\pyproject.toml", "$probeRoot\Chirp\pyproject.toml")) {
        $text = Get-Content -Raw -LiteralPath $project
        $text = $text -replace '(dependencies = \[\r?\n)', "`$1    `"google-auth==2.56.0`",`r`n"
        Set-Content -LiteralPath $project -Value $text -Encoding UTF8
    }

    Push-Location "$probeRoot\mcp_server"
    uv lock
    uv sync --frozen --extra test --python "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
    .\.venv\Scripts\python.exe -c "import google.auth, google.oauth2.credentials, litellm; print(google.auth.__version__, litellm.__version__)"
    .\.venv\Scripts\python.exe -m pip check
    Pop-Location

    & "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe" -m venv "$probeRoot\Chirp\.venv"
    & "$probeRoot\Chirp\.venv\Scripts\python.exe" -m pip install -e "$probeRoot\Chirp[dev]"
    & "$probeRoot\Chirp\.venv\Scripts\python.exe" -c "import google.auth, google.oauth2.credentials, litellm; print(google.auth.__version__, litellm.__version__)"
    & "$probeRoot\Chirp\.venv\Scripts\python.exe" -m pip check
}
finally {
    if (Test-Path -LiteralPath $probeRoot) { Remove-Item -LiteralPath $probeRoot -Recurse -Force }
}
```

Record the direct/transitive package delta. Stop if any existing package version/source/hash moves unexpectedly. If automated cleanup is blocked, report the exact resolved temporary path for bounded manual removal rather than changing deletion policy.

- [ ] **Step 5: Record exact probe outcomes**

The report must pin:

```text
google-auth: 2.56.0 in Rook and Chirp
LiteLLM kwargs: vertex_project, vertex_location, vertex_credentials
credential shape: in-memory authorized_user dictionary
readiness: Vertex countTokens with constant Rook-owned text
mutex: Local\BringFire.Rook.VertexAuth.v1 / 10000 ms
event: Local\BringFire.Rook.Chirp.VertexGenerationChanged.v1 / manual reset
```

It must contain no client material, credential values, user/project identity, raw provider body, or service-account path.

- [ ] **Step 6: Commit evidence and stop for review**

```powershell
git -C $rookWorktree add docs/superpowers/reports/2026-08-09-enterprise-vertex-task0-probe.md
git -C $rookWorktree diff --cached --check
git -C $rookWorktree commit -m "docs: record Vertex dependency probe"
```

Do not begin Task 1 until the reviewer explicitly admits the one direct dependency and recorded transitive set.

---

### Task 1: Implement the Rook store, DPAPI, and cross-process kernel

**Files:**
- Create: `mcp_server/src/rook/providers/vertex_auth.py`
- Create: `mcp_server/tests/test_vertex_auth.py`
- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`

**Interfaces:**
- Produces: `VertexMode`, `VertexRecord`, `VertexRuntimeArguments`, `VertexAuthError`, `VertexStore`, `is_vertex_model()`, and `apply_vertex_litellm_arguments()`.
- Consumes: admitted `google-auth==2.56.0` and the fixed Windows contracts from Task 0.

- [ ] **Step 1: Write RED record and model-admission tests**

Require these closed shapes:

```python
assert is_vertex_model("vertex_ai/gemini-2.5-pro") is True
assert is_vertex_model("gemini/gemini-2.5-pro") is False

record = VertexRecord(
    schema_version=1,
    generation="0123456789abcdef0123456789abcdef",
    mode=VertexMode.OAUTH,
    project_id="company-ai-project",
    region="us-central1",
    oauth_ciphertext="ciphertext",
    service_account_path=None,
)
assert record.to_json_object()["schema_version"] == 1
```

Reject unknown fields/schema, malformed generation/project/region, unknown mode, OAuth without ciphertext, ADC with secret fields, and service-account mode without an absolute regular file.

- [ ] **Step 2: Write RED atomicity, DPAPI, and multi-process tests**

Use injected fake protection for ordinary unit tests and one Windows-only real DPAPI round trip. A seeded plaintext sentinel must decrypt correctly but be absent from store bytes.

For write failure:

```python
before = store_path.read_bytes()
with pytest.raises(VertexAuthError) as exc:
    store.replace_for_test(record, fail_before_replace=True)
assert exc.value.code == "vertex_request_failed"
assert store_path.read_bytes() == before
assert not list(store_path.parent.glob("vertex.json.*.tmp"))
```

Spawn one process holding the test mutex and prove a second times out without touching bytes. Add an abandoned-owner process; its successor must acquire, re-read, and safely commit.

- [ ] **Step 3: Implement the minimal closed types and Windows primitives**

```python
VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
VERTEX_SCHEMA_VERSION = 1
VERTEX_MUTEX_NAME = r"Local\BringFire.Rook.VertexAuth.v1"
VERTEX_MUTEX_TIMEOUT_MS = 10_000

class VertexMode(str, Enum):
    OAUTH = "oauth"
    ADC = "adc"
    SERVICE_ACCOUNT = "service_account"

@dataclass(frozen=True)
class VertexRuntimeArguments:
    generation: str
    project_id: str
    region: str
    vertex_credentials: dict[str, str] | str | None

class VertexAuthError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.public_message = message
        super().__init__(message)
```

`VertexStore.production()` alone resolves the canonical path. Tests pass explicit paths and protectors. Use `CreateMutexW`, `WaitForSingleObject`, `ReleaseMutex`, and `CloseHandle`; `WAIT_ABANDONED` forces a re-read. Write a sibling temporary file, flush, `os.fsync`, and `os.replace`. Generate a new 32-hex generation inside the lock for every committed replacement. Unknown records fail closed without rewrite.

- [ ] **Step 4: Add the admitted dependency and regenerate normally**

Add exactly:

```toml
"google-auth==2.56.0",
```

Run:

```powershell
Set-Location "$rookWorktree\mcp_server"
uv lock
uv lock --check
```

Require exactly the Task 0-approved package movement.

- [ ] **Step 5: Implement runtime argument resolution**

OAuth decrypts one authorized-user dictionary in memory. ADC returns `vertex_credentials=None`; service account returns the revalidated canonical file path. The helper copies the caller's kwargs and changes only Vertex:

```python
def apply_vertex_litellm_arguments(model, kwargs, *, store=None):
    result = dict(kwargs)
    if not is_vertex_model(model):
        return result
    runtime = (store or VertexStore.production()).resolve_runtime()
    result["vertex_project"] = runtime.project_id
    result["vertex_location"] = runtime.region
    if runtime.vertex_credentials is not None:
        result["vertex_credentials"] = runtime.vertex_credentials
    return result
```

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
Set-Location "$rookWorktree\mcp_server"
uv sync --frozen --extra test --python "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
.\.venv\Scripts\python.exe -m pytest tests/test_vertex_auth.py -q
.\.venv\Scripts\python.exe -m pip check
Set-Location $rookWorktree
git diff --check
git add mcp_server/pyproject.toml mcp_server/uv.lock mcp_server/src/rook/providers/vertex_auth.py mcp_server/tests/test_vertex_auth.py
git commit -m "feat(vertex): add protected authorization store"
```

---

### Task 2: Implement backend-only OAuth, readiness, and disconnect

**Files:**
- Create: `mcp_server/src/rook/providers/vertex_oauth.py`
- Create: `mcp_server/src/rook/providers/vertex_backend.py`
- Create: `mcp_server/tests/test_vertex_oauth.py`
- Create: `mcp_server/tests/test_vertex_backend.py`

**Interfaces:**
- Consumes: Task 1 store/types and a post-commit recycler callback implemented in Task 5.
- Produces: `DesktopOAuthClient`, `VertexOperationResult`, `connect_vertex_oauth()`, `save_vertex_configuration()`, `disconnect_vertex()`, and `probe_vertex_readiness()`.

- [ ] **Step 1: Write RED PKCE/loopback tests**

Inject browser, random, clock, listener, and HTTP dependencies. Require:

```python
assert query["code_challenge_method"] == "S256"
assert query["scope"] == VERTEX_SCOPE
assert query["access_type"] == "offline"
assert query["redirect_uri"].startswith("http://127.0.0.1:")
assert callback.state == issued_state
```

Reject wrong/missing state, missing code, denial, malformed/second callback, non-loopback binding, and timeout. Every case closes the listener and preserves prior bytes.

- [ ] **Step 2: Write RED token-admission preservation tests**

Commit only when token type is Bearer, access token is nonempty/unexpired, refresh token is nonempty, normalized scope set is exactly `{VERTEX_SCOPE}`, and `google.oauth2.credentials.Credentials.refresh(Request())` succeeds once. Missing/extra/reduced scope, missing refresh authorization, expired access token, or refresh failure must produce:

```python
assert result.success is False
assert store_path.read_bytes() == prior_bytes
assert recycler.calls == []
```

- [ ] **Step 3: Write RED readiness/error tests**

Pin this non-generating request:

```python
url = (
    f"https://{region}-aiplatform.googleapis.com/v1/"
    f"projects/{project}/locations/{region}/publishers/google/models/{model}:countTokens"
)
body = {"contents": [{"role": "user", "parts": [{"text": "Rook Vertex readiness probe"}]}]}
```

Assert no tools, generation settings, streaming, or user content. Classify only documented structured status/reason fields. Unknown/malformed responses become `vertex_request_failed`; raw bodies and exception messages never escape.

Parameterize the full closed vocabulary. Local deterministic states cover
`vertex_signed_out`, `vertex_adc_unavailable`,
`vertex_service_account_unavailable`, `vertex_project_required`,
`vertex_region_required`, and `vertex_auth_dependency_missing`. OAuth callback
fields cover `vertex_authorization_declined` and
`vertex_oauth_admin_blocked`. Refresh failure covers
`vertex_authorization_revoked`. Structured readiness fixtures cover
`vertex_project_inaccessible`, `vertex_api_disabled`,
`vertex_billing_unavailable`, `vertex_permission_missing`,
`vertex_region_invalid`, and `vertex_model_unavailable`. Any fixture lacking the
required structured discriminator maps to `vertex_request_failed`, even when
free text suggests a narrower cause.

- [ ] **Step 4: Write RED disconnect tests**

OAuth disconnect makes one bounded best-effort revocation request, then exact-deletes `vertex.json` even after timeout/failure. Return separate revocation/local-deletion states. ADC and service-account disconnect do no network revocation. Sibling provider files and Gemini settings remain byte-identical.

- [ ] **Step 5: Implement the backend operation**

```python
@dataclass(frozen=True)
class DesktopOAuthClient:
    client_id: str
    client_secret: str

@dataclass(frozen=True)
class VertexOperationResult:
    success: bool
    code: str | None
    message: str
    generation: str | None
    revocation: str | None = None
    local_deletion: str | None = None
```

Connect requires an explicit recycler callback and holds the mutation mutex from
prior-record read through browser flow, exchange, refresh verification, atomic
replacement, and recycler invocation. Save/disconnect require the same callback
and serialized operation. Recycler failure after commit reports
`vertex_restart_required` without rolling the accepted record back; the stale
child rejects before provider work. No route, tool, startup hook, or import-time
browser action is registered.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
Set-Location "$rookWorktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_vertex_auth.py tests/test_vertex_oauth.py tests/test_vertex_backend.py -q
Set-Location $rookWorktree
git diff --check
git add mcp_server/src/rook/providers/vertex_oauth.py mcp_server/src/rook/providers/vertex_backend.py mcp_server/tests/test_vertex_oauth.py mcp_server/tests/test_vertex_backend.py
git commit -m "feat(vertex): add desktop authorization backend"
```

---

### Task 3: Route Vertex through Rook Chat, agents, and DSPy

**Files:**
- Read/verify unchanged: `mcp_server/src/rook/agent/model_profiles.py`
- Modify: `mcp_server/src/rook/agent/base_agent.py`
- Modify: `mcp_server/src/rook/agent/guardian.py`
- Modify: `mcp_server/src/rook/agent/local_worker_model_transport.py`
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/src/rook/agent/chat/runtime_health.py`
- Modify: `mcp_server/src/rook/agent/chat/model_status.py`
- Modify: `mcp_server/src/rook/learning/dspy_config.py`
- Create: `mcp_server/tests/test_vertex_runtime_integration.py`

**Interfaces:**
- Consumes: `apply_vertex_litellm_arguments()` and `VertexAuthError`.
- Produces: fresh per-call Vertex args at every LiteLLM/DSPy boundary and Vertex-specific health.

- [ ] **Step 1: Write RED separation tests**

```python
vertex = apply_vertex_litellm_arguments("vertex_ai/gemini-2.5-pro", {"model": "vertex_ai/gemini-2.5-pro"}, store=fake_store)
assert vertex["vertex_project"] == "company-ai-project"
assert vertex["vertex_location"] == "us-central1"
assert vertex["vertex_credentials"]["type"] == "authorized_user"

gemini = apply_vertex_litellm_arguments("gemini/gemini-2.5-pro", {"model": "gemini/gemini-2.5-pro"}, store=untouchable_store)
assert "vertex_credentials" not in gemini
assert untouchable_store.calls == []
```

- [ ] **Step 2: Write RED call-site tests**

Capture final kwargs for Chat, base agent, guardian, local worker, default DSPy, and teacher/student DSPy. Vertex gets exactly project/location/credential arguments. Gemini, Anthropic, OpenAI, OpenRouter, Ollama, LM Studio, and bare local models retain base-equivalent kwargs.

- [ ] **Step 3: Update each call boundary locally**

Call the Task 1 helper immediately before each `litellm.acompletion`, `litellm.completion`, or `dspy.LM` construction named in the File Map. Do not place Vertex authorization in global LiteLLM settings or process environment.

- [ ] **Step 4: Correct only Vertex health/eligibility**

When the active model begins with `vertex_ai/`, `runtime_health._llm_state()` uses bounded Vertex status instead of treating multi-auth as configured. `model_status` admits declared Vertex options only when ready. Do not add dynamic model discovery.

- [ ] **Step 5: Add Gemini/RookVision no-touch guards**

Hash the exact RookVision Gemini/Veo files against the Task 0 Rook base and require identical bytes. Assert existing `GEMINI_API_KEY` and `generativelanguage.googleapis.com` ownership remains unchanged and no `vertex_ai` text enters those files.

- [ ] **Step 6: Run GREEN tests and commit**

```powershell
Set-Location "$rookWorktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_vertex_runtime_integration.py tests/test_model_profiles_openrouter.py tests/test_runtime_health_providers.py tests/test_chat_runner.py tests/test_local_worker_model_transport.py -q
Set-Location $rookWorktree
git diff --check
git add `
    mcp_server/src/rook/agent/base_agent.py `
    mcp_server/src/rook/agent/guardian.py `
    mcp_server/src/rook/agent/local_worker_model_transport.py `
    mcp_server/src/rook/agent/chat/chat_runner.py `
    mcp_server/src/rook/agent/chat/runtime_health.py `
    mcp_server/src/rook/agent/chat/model_status.py `
    mcp_server/src/rook/learning/dspy_config.py `
    mcp_server/tests/test_vertex_runtime_integration.py
git commit -m "feat(vertex): route enterprise text consumers"
```

---

### Task 4: Add the memory-only Vertex bootstrap to Chirp

**Files:**
- Modify: `pyproject.toml`
- Create: `src/chirp/vertex_bootstrap.py`
- Modify: `src/chirp/__main__.py`
- Modify: `src/chirp/server.py`
- Modify: `src/chirp/adapter.py`
- Create: `tests/test_vertex_bootstrap.py`
- Create: `tests/test_main.py`
- Modify: `tests/test_server.py`
- Modify: `tests/test_adapter.py`

**Interfaces:**
- Consumes: one stdin JSON envelope `{schema_version,generation,mode,project_id,region,vertex_credentials}`.
- Produces: `VertexBootstrap`, `VertexRestartRequired`, `read_managed_bootstrap()`, `vertex_kwargs_for_model()`, `assert_current_generation()`, and nonsecret health `ready|absent|stale`.

- [ ] **Step 1: Write RED bootstrap and redaction tests**

The flag is exactly `--rook-vertex-bootstrap-stdin`. With it, read one UTF-8
JSON line capped at `65,536` bytes and require EOF. Reject malformed JSON,
extra fields, wrong schema, malformed generation, duplicate data, and incoherent
mode/credential pairs. OAuth requires an `authorized_user` dictionary; ADC
requires null credentials; service-account mode requires an absolute regular-file
path string. Without the flag, never read stdin.

Capture logs, exceptions, health, discovery, and traces with unique token/client sentinels; none may appear.

- [ ] **Step 2: Write RED generation and Vertex-only tests**

```python
assert bootstrap.vertex_kwargs_for_model("gemini/gemini-2.5-pro") == {}
assert bootstrap.vertex_kwargs_for_model("vertex_ai/gemini-2.5-pro") == {
    "vertex_project": "company-ai-project",
    "vertex_location": "us-central1",
    "vertex_credentials": authorized_user,
}
```

Delete/change the temporary store generation immediately before a Vertex call. Require `VertexRestartRequired.code == "vertex_restart_required"` and prove the fake provider was not called.

- [ ] **Step 3: Write RED retirement-event tests**

Inject a fake event waiter. Signaling the fixed event sets `uvicorn.Server.should_exit=True`. Non-managed Chirp neither creates nor waits on the event.

- [ ] **Step 4: Implement strict immutable bootstrap state**

```python
@dataclass(frozen=True)
class VertexBootstrap:
    schema_version: int
    generation: str
    mode: str
    project_id: str
    region: str
    vertex_credentials: dict[str, str] | str | None

class VertexRestartRequired(RuntimeError):
    code = "vertex_restart_required"
```

Parse before importing `chirp.server`, retain only in memory, and inject into `ChirpAdapter`. `_make_lm()` adds Vertex kwargs only for `vertex_ai/...`; `acall()` repeats generation validation immediately before provider work.

- [ ] **Step 5: Implement bounded health**

Health retains top-level `status` and `version` and adds only
`{"vertex":{"status":"ready|absent|stale"}}`. A non-Vertex active/default model
remains top-level healthy when Vertex is absent or stale. A Vertex active/default
model reports top-level disabled with `vertex_signed_out` or
`vertex_restart_required`. Never return generation, project, region, client
identity, credential mode, path, or ciphertext.

- [ ] **Step 6: Add the admitted dependency and run GREEN**

Add exactly `google-auth==2.56.0`, then:

```powershell
Set-Location $chirpWorktree
& "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe" -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip check
git diff --check
git add `
    pyproject.toml `
    src/chirp/vertex_bootstrap.py `
    src/chirp/__main__.py `
    src/chirp/server.py `
    src/chirp/adapter.py `
    tests/test_vertex_bootstrap.py `
    tests/test_main.py `
    tests/test_server.py `
    tests/test_adapter.py
git commit -m "feat(vertex): accept managed in-memory authorization"
```

Require current Opus 5/Sonnet 5 and inference-timeout tests to remain green.

- [ ] **Step 7: Review and merge Chirp first**

Push the exact reviewed Chirp head, open a dedicated PR, and merge normally. Record its two-parent merge SHA. Do not stage Rook payloads from an unmerged Chirp head.

---

### Task 5: Make Rook's Chirp manager model- and generation-aware

**Files:**
- Modify: `mcp_server/src/rook/chirp_manager.py`
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/providers/vertex_backend.py`
- Modify: `mcp_server/tests/test_chirp_manager.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/tests/test_vertex_backend.py`

**Interfaces:**
- Consumes: Vertex runtime envelope, Chirp `vertex.status`, private flag, and retirement event.
- Produces: `ensure_chirp_running(required_model: str | None = None)` and `recycle_after_vertex_commit()`.

- [ ] **Step 1: Write RED process-surface tests**

For a Vertex launch:

```python
assert "--rook-vertex-bootstrap-stdin" in argv
assert "refresh_token" not in " ".join(argv)
assert all("refresh_token" not in f"{k}={v}" for k, v in env.items())
assert popen_kwargs["stdin"] == subprocess.PIPE
```

The fake child receives exactly one bounded envelope and EOF. Non-Vertex launch retains `stdin=DEVNULL` with no flag.

- [ ] **Step 2: Write RED health/recycle tests**

For a required Vertex model, health `absent` or `stale` must capture the exact
discovery port, signal the event, wait for the exact PID to disappear, reset only
after retirement, resolve the new generation, start once on that same port, and
wait for ready. Retirement timeout or inability to reclaim the port returns
bounded `vertex_restart_required` and never starts a process on a different port.

- [ ] **Step 3: Write RED post-commit tests**

Connect/save with a previously live Rook-managed sidecar retires and starts one
replacement on the same port before the backend operation returns. Preserve its
prior Vertex-bootstrap state: supply the new envelope only when the old sidecar
was Vertex-ready or its configured default is Vertex. Disconnect also restarts a
previously live sidecar on the same port, but without an OAuth bootstrap, so
non-Vertex Chirps remain usable and Vertex fails signed out. If no sidecar was
live, mutation starts none.

When retirement times out after a committed connect/save, require
`vertex_restart_required`, retain the newly committed store, and prove the stale
sidecar rejects the new generation before provider work. Never attempt a store
rollback after its generation was published.

- [ ] **Step 4: Implement model-aware startup**

Change the existing signature from `async def ensure_chirp_running() -> dict`
to `async def ensure_chirp_running(required_model: str | None = None) -> dict`.

Resolve the effective model from explicit request, process `CHIRP_MODEL`,
canonical Chirp `.env`, then current Chirp defaults. A `vertex_ai/...` model
requires fresh bootstrap. Existing live health `absent|stale` triggers bounded
same-port recycle. Extend `_start_chirp` with an optional requested port used only
for verified recycle; ordinary cold start remains OS-assigned port `0`.

- [ ] **Step 5: Forward the existing Chirp model contract**

Add optional string `model` to `chirp_create`, pass it to `ensure_chirp_running(model)`, and forward unchanged to `/chirp/create`. Do not add provider credentials or OAuth fields to MCP.

- [ ] **Step 6: Add auth-surface guards**

Reject any new MCP tool, public/native route, or schema named `vertex_login`, `vertex_connect`, `oauth_login`, or containing client/credential/token fields. The optional Chirp `model` field is the only MCP schema addition.

- [ ] **Step 7: Run GREEN tests and commit**

```powershell
Set-Location "$rookWorktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_vertex_backend.py tests/test_chirp_manager.py tests/test_server_contract_hardening.py -q
Set-Location $rookWorktree
git diff --check
git add mcp_server/src/rook/chirp_manager.py mcp_server/src/rook/server.py mcp_server/src/rook/providers/vertex_backend.py mcp_server/tests/test_chirp_manager.py mcp_server/tests/test_server_contract_hardening.py mcp_server/tests/test_vertex_backend.py
git commit -m "feat(vertex): bind managed Chirp to authorization generation"
```

---

### Task 6: Add the source-only acceptance entry and sealed-payload guard

**Files:**
- Create: `scripts/vertex_oauth_acceptance.py`
- Create: `mcp_server/tests/test_vertex_acceptance_harness.py`
- Modify: `scripts/tests/python-runtime-packaging.tests.ps1`

**Interfaces:**
- Consumes: installed backend connect/readiness/disconnect operations.
- Produces: bounded redacted `result.json`; no installed command, UI, route, or MCP tool.

- [ ] **Step 1: Write RED harness-boundary tests**

Require installed Rook Python, explicit project/region/model, application client material, an owned temporary evidence root, and positive watchdog. Refuse source-tree Python, missing ownership sentinel, arbitrary output paths, or absent managed-business acknowledgement before browser launch.

The result allowlist is exactly:

```python
{
    "schema_version",
    "success",
    "stages",
    "error_code",
    "rook_commit",
    "chirp_commit",
    "installed_versions",
}
```

No project, region, model, client identity, token, credential path, raw exception, or provider body is recorded.

- [ ] **Step 2: Implement one non-MCP sequence**

The harness verifies installed provenance, calls backend connect, calls readiness, and stops for the consumer matrix. It calls disconnect only with explicit `--disconnect`. It never imports the MCP dispatcher or opens a production UI.

- [ ] **Step 3: Strengthen packaging guards**

Require both generated Rook and Chirp locks to contain `google-auth==2.56.0` with the staged hash. Require exactly one matching wheel and reject another Google auth version. Derive total wheel count from the manifest rather than hardcoding it.

- [ ] **Step 4: Run GREEN tests and commit**

```powershell
Set-Location "$rookWorktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest tests/test_vertex_acceptance_harness.py -q
Set-Location $rookWorktree
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
git diff --check
git add scripts/vertex_oauth_acceptance.py scripts/tests/python-runtime-packaging.tests.ps1 mcp_server/tests/test_vertex_acceptance_harness.py
git commit -m "test(vertex): add bounded installed acceptance entry"
```

---

### Task 7: Review, merge, deploy, and run installed acceptance

**Files:**
- Create: `docs/superpowers/reports/2026-08-09-enterprise-vertex-acceptance.md`
- No production edits after reviewed heads

**Interfaces:**
- Consumes: reviewed Rook production head, merged Chirp head, approved desktop client, business identity, organization project, region, and model.
- Produces: exact installed provenance and redacted PASS/FAIL evidence; no published release.

- [ ] **Step 1: Run the complete focused gate**

```powershell
Set-Location "$rookWorktree\mcp_server"
.\.venv\Scripts\python.exe -m pytest `
    tests/test_vertex_auth.py `
    tests/test_vertex_oauth.py `
    tests/test_vertex_backend.py `
    tests/test_vertex_runtime_integration.py `
    tests/test_chirp_manager.py `
    tests/test_server_contract_hardening.py `
    tests/test_vertex_acceptance_harness.py -q
.\.venv\Scripts\python.exe -m pip check

Set-Location $chirpWorktree
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe -m pip check

Set-Location $rookWorktree
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/tests/python-runtime-packaging.tests.ps1
uv --directory mcp_server lock --check
git diff --check
```

Do not substitute the known repository-wide suite for this closed gate.

- [ ] **Step 2: Enforce exact scope and no-touch hashes**

Compare Rook production paths to the Rook File Map, excluding only spec/plan/reports. Compare Chirp paths to the Chirp File Map. Require all pinned Gemini/RookVision hashes to match the Rook base. Stop on any unexpected path.

- [ ] **Step 3: Review and merge Rook normally**

Push the exact reviewed Rook head, open a private PR, fetch current `main`, require a clean synthetic merge and no conflicting path movement, then merge with a regular two-parent merge. Record the merge SHA. Do not squash or build from the feature head after merge.

- [ ] **Step 4: Create detached source checkouts at the two merge SHAs**

```powershell
$rookRepo = 'C:\Users\aryan\source\repos\Rook'
$chirpRepo = 'C:\Users\aryan\source\repos\Chirp'
$rookMerge = (git -C $rookRepo rev-parse origin/main).Trim()
$chirpMerge = (git -C $chirpRepo rev-parse origin/master).Trim()
$rookRelease = "C:\Users\aryan\source\repos\Rook\.worktrees\vertex-release-$($rookMerge.Substring(0,8))"
$chirpRelease = "C:\Users\aryan\source\repos\Chirp\.worktrees\vertex-release-$($chirpMerge.Substring(0,8))"
if (Test-Path -LiteralPath $rookRelease) { throw 'Rook release checkout exists' }
if (Test-Path -LiteralPath $chirpRelease) { throw 'Chirp release checkout exists' }
git -C $rookRepo worktree add --detach $rookRelease $rookMerge
git -C $chirpRepo worktree add --detach $chirpRelease $chirpMerge
if (git -C $rookRelease status --porcelain) { throw 'Rook release checkout dirty' }
if (git -C $chirpRelease status --porcelain) { throw 'Chirp release checkout dirty' }
```

Verify the recorded reviewed heads are the second parents of these merges before staging.

- [ ] **Step 5: Stage and validate the sealed Python payload once**

```powershell
$releaseVersion = '1.5.18'
powershell -NoProfile -ExecutionPolicy Bypass -File "$rookRelease\scripts\python-runtime\stage-rook-python-runtime.ps1" -RepoRoot $rookRelease
powershell -NoProfile -ExecutionPolicy Bypass -File "$rookRelease\scripts\python-runtime\build-rook-python-wheelhouse.ps1" -Version $releaseVersion -RepoRoot $rookRelease -ChirpRoot $chirpRelease
powershell -NoProfile -ExecutionPolicy Bypass -File "$rookRelease\scripts\validate-python-wheelhouse.ps1" -Version $releaseVersion -RepoRoot $rookRelease
```

Require manifest SHAs to equal `$rookMerge` and `$chirpMerge`, both locks to contain the exact admitted Google auth version, one matching wheel, clean temporary imports/audits, and no tracked changes.

- [ ] **Step 6: Deploy payload-only and verify installed parity**

Close Rhino, Grasshopper, Revit, Rook MCP, Rook Chat, and Chirp, require the repository process guard to report zero, then run:

```powershell
Set-Location $rookRelease
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/rook-mcp-processes.ps1 -Stop
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/rook-mcp-processes.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/deploy-local-testing.ps1 -Configuration Release -PayloadOnly -SkipBuild
```

Require the second process command to report zero before deployment. Compare installed wheel/control inventories and hashes with the staged manifest, then run `pip check` in both installed environments. Do not rebuild native, managed, or RookBIM code.

- [ ] **Step 7: Stop for live-provider authorization**

Record reviewer approval without recording identities or configuration values:

```text
managed business identity approved: yes
organization project approved: yes
region and model approved: yes
readiness plus three benign text calls approved: yes
```

- [ ] **Step 8: Run installed OAuth/readiness and three consumers**

Run `scripts/vertex_oauth_acceptance.py` with installed Rook Python under an owned temporary evidence root. Complete browser OAuth, then readiness. Run one fixed benign Rook Chat call, one fixed benign agent/DSPy call, and one disposable Chirp component with an explicit `vertex_ai/...` model. Verify its output, remove only the owned component, and restore the canvas.

While Vertex is configured, prove existing `gemini/...` configuration still resolves independently and RookVision Gemini/Veo settings remain unchanged. Do not issue image/video generation for this acceptance.

- [ ] **Step 9: Disconnect, scan, clean, and record evidence**

Call backend disconnect. Prove subsequent Vertex resolution fails closed, `vertex.json` is absent, sibling Rook data is unchanged, and Gemini/local/Rook remain healthy. Scan logs, health, diagnostics, process command lines/environments, discovery, manifests, and report artifacts for credential sentinels. Close owned hosts and sidecars gracefully and require zero owned processes/discovery entries.

Create the evidence branch from the exact merge, then use `apply_patch` to write
exact Rook/Chirp merge SHAs, installed inventory hashes, test counts, and
PASS/FAIL without identity/project/region/model/client/token details:

```powershell
$evidenceWorktree = "C:\Users\aryan\source\repos\Rook\.worktrees\vertex-acceptance-$($rookMerge.Substring(0,8))"
if (Test-Path -LiteralPath $evidenceWorktree) { throw 'Evidence worktree exists' }
git -C $rookRepo worktree add $evidenceWorktree -b codex/enterprise-vertex-acceptance-evidence $rookMerge
Set-Location $evidenceWorktree
```

- [ ] **Step 10: Commit evidence only**

```powershell
Set-Location $evidenceWorktree
git add docs/superpowers/reports/2026-08-09-enterprise-vertex-acceptance.md
git diff --cached --check
git commit -m "docs: record enterprise Vertex acceptance"
```

Phase 3 Provider Setup, installer lifecycle, the 1.5.19 bump, release notes, release build, and public promotion remain separate.

---

## Self-Review Checklist

- Provider split/no fallback: Tasks 3 and 7.
- Operating ownership and immutable store: Task 1.
- Cross-process mutation and generation: Tasks 1 and 5.
- OAuth admission, readiness, errors, and disconnect: Task 2.
- Rook Chat, agents, DSPy, and Chirp consumers: Tasks 3 through 5.
- Backend-only Phase 1 entry point: Task 6.
- Exact dependency admission and sealed delivery: Tasks 0, 1, 4, 6, and 7.
- Managed-business installed acceptance and redaction: Task 7.
- Phase 3 installer lifecycle remains specified but unimplemented here.
- No Provider Setup UI, installer credential page, OAuth route/tool, generic broker/store, Google Cloud administration, RookVision Vertex path, model default, version bump, release artifact, or public promotion enters this plan.
