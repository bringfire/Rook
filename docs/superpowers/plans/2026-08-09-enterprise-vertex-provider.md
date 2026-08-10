# Enterprise Vertex Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an independent, project-based `vertex_ai/gemini-*` text provider for Rook Chat, Rook agents/DSPy, and Rook-managed Chirp while preserving Gemini AI Studio and RookVision exactly.

**Architecture:** One Rook Python authorization owner persists a versioned Vertex record, protects OAuth refresh authorization with Windows DPAPI, and serializes mutations through one named Windows mutex. One closed parser admits only Gemini publisher models on Vertex and rejects every other `vertex_ai/*` family before provider work. Every Rook-launched Chirp is marked managed; only a managed Vertex child receives a memory-only bootstrap through anonymous stdin. Phase 1 exposes no production UI, public HTTP login route, or MCP login tool.

**Tech Stack:** Python 3.10-compatible code on shipped CPython 3.11.9, LiteLLM 1.89.4, DSPy 3.3.0, proposed current patch `google-auth==2.56.3` pending Task 0 reviewer admission, `httpx`, Windows DPAPI/named synchronization through `ctypes`, FastAPI, pytest, and PowerShell packaging guards.

## Global Constraints

- Reviewed specification head: `4a16658b77bbb00a29146b7d2853c5484add044b`.
- Chirp implementation base: `c7b1aacec6b1ae23514cb9fb0d2a365e1fb7a468`.
- Execution starts from clean isolated worktrees. The reviewed plan tag must resolve exactly to the execution plan; current Rook `origin/main` must merge cleanly with zero production-path overlap.
- Preserve Python `>=3.10`, shipped CPython `3.11.9`, LiteLLM `1.89.4`, DSPy `3.3.0`, and MCP `1.28.1`.
- Task 0 probes the current patch `google-auth==2.56.3` in both sealed environments and records why it supersedes the earlier `2.56.0` candidate. The exact pin and resolved transitive set require explicit reviewer admission. Stop if they are not approved. Do not add `google-auth-oauthlib`, a login framework, broker, or generic secret store.
- `gemini/...` remains the existing Gemini Developer API / AI Studio provider. This slice admits only `vertex_ai/gemini-*`; every other `vertex_ai/*` family fails with `vertex_model_family_unsupported`. No migration, alias, shared credential, fallback, partner-model support, or implicit routing is allowed.
- RookVision image/Veo source, endpoints, models, settings, and provider registries are no-touch surfaces.
- The only OAuth scope is `https://www.googleapis.com/auth/cloud-platform`.
- Production store: `%LOCALAPPDATA%\Rook\data\provider_auth\vertex.json`. Tests inject a temporary store path; `ROOK_DATA_DIR` never redirects production credentials.
- Mutation mutex: `Local\BringFire.Rook.VertexAuth.v1`, `10,000` ms acquisition ceiling, `WAIT_OBJECT_0` and `WAIT_ABANDONED` accepted. Timeout changes no bytes.
- Managed-Chirp retirement event: `Local\BringFire.Rook.Chirp.VertexGenerationChanged.v1`, manual-reset, with a `10`-second retirement ceiling. Every Rook-launched child gets `--rook-managed`; only an admitted Vertex launch gets `--rook-vertex-bootstrap-stdin`. A rediscovered managed process may be signaled and observed, but force termination requires the exact current-manager launch handle plus matching PID, discovery record, and port. A replacement rebinds the exact prior port because generated Chirp components embed it; ambiguous ownership or failure to reclaim that port fails closed.
- Record schema version is `1`; each commit gets a fresh `secrets.token_hex(16)` generation.
- DPAPI is CurrentUser with `CRYPTPROTECT_UI_FORBIDDEN` and entropy bytes `BringFire.Rook.VertexAuth.v1`.
- Desktop OAuth binds `127.0.0.1` on OS port `0`, uses S256 PKCE and exact state, accepts one callback, and has a `180`-second ceiling.
- Login replaces a record only after a nonempty refresh token, usable access token, exact granted-scope set, and one successful `google-auth` refresh. Failure preserves prior bytes.
- Explicit readiness is one non-generating `countTokens` request containing only the literal `Rook Vertex readiness probe`. Passive health and model enumeration are local and network-free. Normal admitted inference may refresh credentials and contact Vertex.
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
| `mcp_server/src/rook/agent/chat/{chat_runner.py,runtime_health.py,model_status.py}` | Chat call and network-free local Vertex status. |
| `mcp_server/src/rook/learning/dspy_config.py` | Vertex args for all DSPy LM constructors. |
| `mcp_server/src/rook/chirp_manager.py`, `mcp_server/src/rook/server.py` | Model-aware pipe bootstrap, ownership-aware recycling, and Chirp model forwarding. |
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
| `src/chirp/server.py`, `src/chirp/adapter.py` | Network-free Vertex health, admitted Vertex-only kwargs, and pre-call generation check. |
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
$specHead = '4a16658b77bbb00a29146b7d2853c5484add044b'
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
$absenceProbe = @'
from importlib import metadata

assert metadata.version("litellm") == "1.89.4"
try:
    import google.auth  # noqa: F401
except ModuleNotFoundError:
    pass
else:
    raise AssertionError("google-auth is already installed")
'@
foreach ($python in $pythons) {
    $absenceProbe | & $python -
    if ($LASTEXITCODE -ne 0) { throw "Dependency absence probe failed: $python" }
}
$source = Get-Content -Raw "$env:LOCALAPPDATA\Rook\venv\Lib\site-packages\litellm\llms\vertex_ai\vertex_llm_base.py"
foreach ($needle in @('google.oauth2.credentials', 'google.auth.transport.requests', 'vertex_credentials')) {
    if (-not $source.Contains($needle)) { throw "Missing LiteLLM seam: $needle" }
}
```

- [ ] **Step 4: Resolve `google-auth==2.56.3` in Rook and the sealed Chirp environment**

`2.56.0` was the original reviewed candidate. `2.56.3` is the current patch in
the same supported line at this amendment and is probed explicitly rather than
silently substituted. Task 0 does not admit either version by itself; the report
must show the exact direct/transitive delta and the reviewer selects the final
pin before Task 1.

```powershell
$probeRoot = Join-Path $env:TEMP ("rook-vertex-dependency-" + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $probeRoot | Out-Null
try {
    git -C $rookWorktree archive --format=zip --output="$probeRoot\rook.zip" HEAD mcp_server
    if ($LASTEXITCODE -ne 0) { throw 'Rook probe archive failed' }
    Expand-Archive -LiteralPath "$probeRoot\rook.zip" -DestinationPath $probeRoot
    $project = "$probeRoot\mcp_server\pyproject.toml"
    $text = Get-Content -Raw -LiteralPath $project
    $text = $text -replace '(dependencies = \[\r?\n)', "`$1    `"google-auth==2.56.3`",`r`n"
    Set-Content -LiteralPath $project -Value $text -Encoding UTF8

    Push-Location "$probeRoot\mcp_server"
    uv lock
    uv sync --frozen --extra test --python "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
    .\.venv\Scripts\python.exe -c "from importlib.metadata import version; import google.auth, google.oauth2.credentials; assert version('google-auth') == '2.56.3'; assert version('litellm') == '1.89.4'; print(version('google-auth'), version('litellm'))"
    uv pip check --python .\.venv\Scripts\python.exe
    Pop-Location

    # Chirp ships from Rook's one sealed wheelhouse and Chirp lock. A standalone
    # editable Chirp resolution is not an accepted release comparison boundary.
    $sealedRoot = "$env:LOCALAPPDATA\Rook\app"
    $wheelhouse = Join-Path $sealedRoot 'python-wheelhouse'
    $manifest = Get-Content -Raw -LiteralPath (Join-Path $sealedRoot 'python-runtime-manifest.json') | ConvertFrom-Json
    if ($manifest.chirp_git_sha -ne $chirpBase) { throw 'Sealed Chirp provenance mismatch' }
    $expectedWheels = @{}
    foreach ($item in $manifest.wheelhouse.wheels) { $expectedWheels[$item.file] = $item.sha256 }
    $actualWheels = @(Get-ChildItem -LiteralPath $wheelhouse -Filter '*.whl' -File)
    if ($actualWheels.Count -ne $expectedWheels.Count) { throw 'Sealed wheel count mismatch' }
    foreach ($wheel in $actualWheels) {
        if (-not $expectedWheels.ContainsKey($wheel.Name) -or
            (Get-FileHash -LiteralPath $wheel.FullName -Algorithm SHA256).Hash -ne $expectedWheels[$wheel.Name]) {
            throw "Sealed wheel mismatch: $($wheel.Name)"
        }
    }
    foreach ($lockName in @('bootstrap', 'rook', 'chirp')) {
        $entry = $manifest.lockfiles.$lockName
        $path = Join-Path $sealedRoot (Split-Path -Leaf $entry.path)
        if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $entry.sha256) {
            throw "Sealed lock mismatch: $lockName"
        }
    }

    $basePython = "$env:LOCALAPPDATA\Rook\python\cpython-3.11.9\python.exe"
    $chirpVenv = "$probeRoot\chirp-sealed-venv"
    & $basePython -m venv $chirpVenv
    $chirpPython = Join-Path $chirpVenv 'Scripts\python.exe'
    & $chirpPython -m pip --isolated install --no-index --find-links $wheelhouse --require-hashes -r (Join-Path $sealedRoot 'requirements-bootstrap-lock.txt')
    & $chirpPython -m pip --isolated install --no-index --find-links $wheelhouse --require-hashes -r (Join-Path $sealedRoot 'requirements-chirp-lock.txt')
    & $chirpPython -c "from importlib.metadata import version; assert version('litellm') == '1.89.4'; assert version('dspy') == '3.3.0'"
    & $chirpPython -m pip check
    $before = @((& $chirpPython -m pip list --format=json) | ConvertFrom-Json)

    $addon = New-Item -ItemType Directory -Path "$probeRoot\addon-wheels"
    & $basePython -m pip download --dest $addon.FullName --only-binary=:all: --no-deps google-auth==2.56.3 pyasn1-modules==0.4.2 pyasn1==0.6.4
    $newWheelHashes = @{
        'google_auth-2.56.3-py3-none-any.whl' = '8EC438808F813AD034535000261EED1067475D229D05BBF4216E78C3F2362E53'
        'pyasn1_modules-0.4.2-py3-none-any.whl' = '29253A9207CE32B64C3AC6600EDC75368F98473906E8FD1043BD6B5B1DE2C14A'
        'pyasn1-0.6.4-py3-none-any.whl' = 'DEDA9277CFD454080EC40B207FB6DF82206A3A2688735233CDCD8D3D565F088B'
    }
    $newWheels = @(Get-ChildItem -LiteralPath $addon.FullName -Filter '*.whl' -File)
    if ($newWheels.Count -ne 3) { throw 'Unexpected new wheel count' }
    foreach ($wheel in $newWheels) {
        if (-not $newWheelHashes.ContainsKey($wheel.Name) -or
            (Get-FileHash -LiteralPath $wheel.FullName -Algorithm SHA256).Hash -ne $newWheelHashes[$wheel.Name]) {
            throw "New wheel mismatch: $($wheel.Name)"
        }
    }
    $candidateWheels = @(
        "$($addon.FullName)\google_auth-2.56.3-py3-none-any.whl",
        "$($addon.FullName)\pyasn1_modules-0.4.2-py3-none-any.whl",
        "$($addon.FullName)\pyasn1-0.6.4-py3-none-any.whl",
        "$wheelhouse\cryptography-50.0.0-cp311-abi3-win_amd64.whl",
        "$wheelhouse\cffi-2.1.1-cp311-cp311-win_amd64.whl",
        "$wheelhouse\pycparser-3.0-py3-none-any.whl"
    )
    & $chirpPython -m pip --isolated install --no-index --no-deps @candidateWheels
    & $chirpPython -c "from importlib.metadata import version; import google.auth, google.oauth2.credentials; assert version('google-auth') == '2.56.3'; assert version('litellm') == '1.89.4'; assert version('dspy') == '3.3.0'"
    & $chirpPython -m pip check
    $after = @((& $chirpPython -m pip list --format=json) | ConvertFrom-Json)

    # Canonicalize names and require six additions, zero removals, and zero
    # existing-version changes. Only google-auth, pyasn1-modules, and pyasn1
    # are new wheelhouse artifacts; cryptography, cffi, and pycparser are reused.
    $normalize = { param($name) ($name.ToLowerInvariant() -replace '[-_.]+', '-') }
    $beforeMap = @{}; foreach ($item in $before) { $beforeMap[(& $normalize $item.name)] = $item.version }
    $afterMap = @{}; foreach ($item in $after) { $afterMap[(& $normalize $item.name)] = $item.version }
    $expectedAdditions = @{
        'google-auth' = '2.56.3'; 'pyasn1-modules' = '0.4.2'; 'pyasn1' = '0.6.4'
        'cryptography' = '50.0.0'; 'cffi' = '2.1.1'; 'pycparser' = '3.0'
    }
    $added = @($afterMap.Keys | Where-Object { -not $beforeMap.ContainsKey($_) })
    if ($added.Count -ne 6) { throw "Unexpected Chirp additions: $($added -join ', ')" }
    foreach ($entry in $expectedAdditions.GetEnumerator()) {
        if ($beforeMap.ContainsKey($entry.Key) -or $afterMap[$entry.Key] -ne $entry.Value) {
            throw "Chirp addition mismatch: $($entry.Key)"
        }
    }
    foreach ($entry in $beforeMap.GetEnumerator()) {
        if (-not $afterMap.ContainsKey($entry.Key) -or $afterMap[$entry.Key] -ne $entry.Value) {
            throw "Existing Chirp package changed: $($entry.Key)"
        }
    }
}
finally {
    if (Test-Path -LiteralPath $probeRoot) { Remove-Item -LiteralPath $probeRoot -Recurse -Force }
}
```

Record the direct/transitive package delta. Stop if any existing package version/source/hash moves unexpectedly. If automated cleanup is blocked, report the exact resolved temporary path for bounded manual removal rather than changing deletion policy.

- [ ] **Step 5: Record exact probe outcomes**

The report must pin:

```text
google-auth candidate: 2.56.3 in Rook and Chirp
prior candidate: 2.56.0; exact current-patch rationale and dependency delta recorded
LiteLLM kwargs: vertex_project, vertex_location, vertex_credentials
credential shape: in-memory authorized_user dictionary
model admission: vertex_ai/gemini-* only; provider-relative name in Google URL
readiness: explicit Vertex countTokens with constant Rook-owned text; passive status network-free
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

Do not begin Task 1 until the reviewer explicitly records the exact admitted
`google-auth` patch and accepts the recorded transitive set. If `2.56.3` is not
admitted, stop and amend this plan; do not silently fall back to `2.56.0`.

---

### Task 1: Implement the Rook store, DPAPI, and cross-process kernel

**Files:**
- Create: `mcp_server/src/rook/providers/vertex_auth.py`
- Create: `mcp_server/tests/test_vertex_auth.py`
- Modify: `mcp_server/pyproject.toml`
- Modify: `mcp_server/uv.lock`

**Interfaces:**
- Produces: `VertexMode`, `VertexRecord`, `VertexRuntimeArguments`, `VertexAuthError`, `VertexStore`, `vertex_gemini_model_name()`, and `apply_vertex_litellm_arguments()`.
- Consumes: the exact reviewer-admitted `google-auth` patch and the fixed Windows contracts from Task 0.

- [ ] **Step 1: Write RED record and model-admission tests**

Require these closed shapes:

```python
assert vertex_gemini_model_name("vertex_ai/gemini-2.5-pro") == "gemini-2.5-pro"
assert vertex_gemini_model_name("gemini/gemini-2.5-pro") is None
with pytest.raises(VertexAuthError) as exc:
    vertex_gemini_model_name("vertex_ai/claude-sonnet")
assert exc.value.code == "vertex_model_family_unsupported"
assert exc.value.public_message == (
    "This release supports only Gemini publisher models on Vertex AI "
    "(vertex_ai/gemini-*)."
)

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

Reject blank/malformed `vertex_ai/gemini-*` names and every other `vertex_ai/*`
family before store access. Reject unknown record fields/schema, malformed
generation/project/region, unknown mode, OAuth without ciphertext, ADC with
secret fields, and service-account mode without an absolute regular file.

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

After Task 0 reviewer admission, add exactly the admitted pin. The expected
current-patch outcome is:

```toml
"google-auth==2.56.3",
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
    publisher_model = vertex_gemini_model_name(model)
    if publisher_model is None:
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
uv pip check --python .\.venv\Scripts\python.exe
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

Pin this non-generating request. `vertex_gemini_model_name()` must produce
`publisher_model`; the literal `vertex_ai/` prefix must never enter the URL:

```python
url = (
    f"https://{region}-aiplatform.googleapis.com/v1/"
    f"projects/{project}/locations/{region}/publishers/google/models/{publisher_model}:countTokens"
)
body = {"contents": [{"role": "user", "parts": [{"text": "Rook Vertex readiness probe"}]}]}
```

Assert `publisher_model == "gemini-2.5-pro"` for
`vertex_ai/gemini-2.5-pro`; reject `vertex_ai/claude-*`, partner, and model-garden
identifiers with `vertex_model_family_unsupported` before token refresh or HTTP.
Assert no tools, generation settings, streaming, or user content. Classify only
documented structured status/reason fields. Unknown/malformed responses become
`vertex_request_failed`; raw bodies and exception messages never escape.

Parameterize the full closed vocabulary. Local deterministic states cover
`vertex_signed_out`, `vertex_adc_unavailable`,
`vertex_service_account_unavailable`, `vertex_project_required`,
`vertex_region_required`, `vertex_model_family_unsupported`, and
`vertex_auth_dependency_missing`. OAuth callback
fields cover `vertex_authorization_declined` and
`vertex_oauth_admin_blocked`. Refresh failure covers
`vertex_authorization_revoked`. Structured readiness fixtures cover
`vertex_project_inaccessible`, `vertex_api_disabled`,
`vertex_billing_unavailable`, `vertex_permission_missing`,
`vertex_region_invalid`, and `vertex_model_unavailable`. Any fixture lacking the
required structured discriminator maps to `vertex_request_failed`, even when
free text suggests a narrower cause.

Add hostile network doubles proving passive health and model enumeration never
decrypt or refresh OAuth credentials and never call `countTokens`. Only the
explicit backend readiness operation may invoke this probe. Ordinary admitted
Chat, DSPy, and Chirp inference may refresh and contact Vertex at their existing
call boundaries.

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
- Produces: fresh per-call Vertex args at every LiteLLM/DSPy boundary and network-free local Vertex health.

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

Capture final kwargs for Chat, base agent, guardian, local worker, default DSPy,
and teacher/student DSPy. Admitted `vertex_ai/gemini-*` calls get exactly
project/location/credential arguments. Unsupported `vertex_ai/*` calls fail with
`vertex_model_family_unsupported` before store or provider access. Gemini,
Anthropic, OpenAI, OpenRouter, Ollama, LM Studio, and bare local models retain
base-equivalent kwargs.

- [ ] **Step 3: Update each call boundary locally**

Call the Task 1 helper immediately before each `litellm.acompletion`, `litellm.completion`, or `dspy.LM` construction named in the File Map. Do not place Vertex authorization in global LiteLLM settings or process environment.

- [ ] **Step 4: Correct only Vertex health/eligibility**

When the active model is admitted as `vertex_ai/gemini-*`,
`runtime_health._llm_state()` reports bounded local Vertex configuration state
instead of treating multi-auth as configured. `model_status` locally admits only
declared Gemini-on-Vertex options. Both paths use hostile network/refresh doubles
and must remain network-free; they do not call readiness or claim remote project
availability. An unsupported `vertex_ai/*` model reports
`vertex_model_family_unsupported`. Do not add dynamic model discovery.

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
- Produces: `VertexBootstrap`, `VertexRestartRequired`, `read_managed_bootstrap()`, `vertex_kwargs_for_model()`, `assert_current_generation()`, managed retirement, and nonsecret health `ready|absent|stale`.

- [ ] **Step 1: Write RED bootstrap and redaction tests**

The management flag is exactly `--rook-managed`. Every Rook-launched child has
it; a standalone child does not. The authorization flag is exactly
`--rook-vertex-bootstrap-stdin` and is valid only together with
`--rook-managed`. With both flags, read one UTF-8 JSON line capped at `65,536`
bytes and require EOF. Reject the bootstrap flag without managed mode, malformed
JSON, extra fields, wrong schema, malformed generation, duplicate data, and
incoherent mode/credential pairs. OAuth requires an `authorized_user`
dictionary; ADC requires null credentials; service-account mode requires an
absolute regular-file path string. Without the bootstrap flag, never read
stdin.

Capture logs, exceptions, health, discovery, and traces with unique token/client sentinels; none may appear.

- [ ] **Step 2: Write RED generation and Vertex-only tests**

```python
assert bootstrap.vertex_kwargs_for_model("gemini/gemini-2.5-pro") == {}
assert bootstrap.vertex_kwargs_for_model("vertex_ai/gemini-2.5-pro") == {
    "vertex_project": "company-ai-project",
    "vertex_location": "us-central1",
    "vertex_credentials": authorized_user,
}
with pytest.raises(VertexAuthError) as exc:
    bootstrap.vertex_kwargs_for_model("vertex_ai/claude-sonnet")
assert exc.value.code == "vertex_model_family_unsupported"
```

Delete/change the temporary store generation immediately before a Vertex call. Require `VertexRestartRequired.code == "vertex_restart_required"` and prove the fake provider was not called.

- [ ] **Step 3: Write RED retirement-event tests**

Inject a fake event waiter. Signaling the fixed event sets
`uvicorn.Server.should_exit=True` for every `--rook-managed` process, including
a non-Vertex child. Standalone Chirp neither creates nor waits on the event.

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

Parse before importing `chirp.server`, retain only in memory, and inject into
`ChirpAdapter`. `_make_lm()` adds Vertex kwargs only for admitted
`vertex_ai/gemini-*`; unsupported `vertex_ai/*` fails locally. `acall()` repeats
generation validation immediately before provider work.

- [ ] **Step 5: Implement bounded health**

Health retains top-level `status` and `version`, adds the nonsecret boolean
`rook_managed`, and adds only
`{"vertex":{"status":"ready|absent|stale"}}`. It performs local checks only:
no refresh, `countTokens`, or provider traffic. A non-Vertex active/default model
remains top-level healthy when Vertex is absent or stale. An admitted Vertex
active/default model reports top-level disabled with `vertex_signed_out` or
`vertex_restart_required`. An unsupported Vertex family reports
`vertex_model_family_unsupported`. Never return generation, project, region,
client identity, credential mode, path, or ciphertext.

- [ ] **Step 6: Add the admitted dependency and run GREEN**

Add exactly the Task 0 reviewer-admitted pin. The expected outcome is
`google-auth==2.56.3`, then:

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
- Consumes: Vertex runtime envelope, Chirp local `vertex.status`, nonsecret managed marker, current-process child handle, discovery PID/port, and retirement event.
- Produces: `ensure_chirp_running(required_model: str | None = None)` and `recycle_after_vertex_commit()`.

- [ ] **Step 1: Write RED process-surface tests**

For every Rook launch:

```python
assert "--rook-managed" in argv
```

For an admitted Vertex launch:

```python
assert "--rook-vertex-bootstrap-stdin" in argv
assert "refresh_token" not in " ".join(argv)
assert all("refresh_token" not in f"{k}={v}" for k, v in env.items())
assert popen_kwargs["stdin"] == subprocess.PIPE
```

The fake Vertex child receives exactly one bounded envelope and EOF. A
non-Vertex Rook launch retains `stdin=DEVNULL`, includes `--rook-managed`, and
omits `--rook-vertex-bootstrap-stdin`. A standalone/manual process is never
retroactively labeled managed.

- [ ] **Step 2: Write RED health/recycle tests**

For a required admitted Vertex model, health `absent` or `stale` must capture
the exact discovery port and PID. A process reporting `rook_managed=true` may be
signaled and observed for graceful disappearance. Forceful termination after
the bounded retirement wait is allowed only when the current module's live
`Popen` handle identifies that same PID and its discovery record and port still
match. A rediscovered managed process without that exact current-process launch
ownership is never force-terminated. An unmanaged process is neither signaled
nor terminated. Ambiguous ownership, retirement timeout, or inability to
reclaim the port returns bounded `vertex_restart_required` and never starts a
process on another port. Reset the event only after the exact process has
retired; then resolve the new generation, start once on the same port, and wait
for local ready state.

- [ ] **Step 3: Write RED post-commit tests**

Connect/save with a previously live, safely retired Rook-managed sidecar starts
one replacement on the same port before the backend operation returns. Preserve
its prior Vertex-bootstrap state: supply the new envelope only when the old
sidecar was Vertex-ready or its configured default is an admitted Vertex model.
Disconnect also restarts a safely retired sidecar on the same port, always with
`--rook-managed` but without an OAuth bootstrap, so non-Vertex Chirps remain
usable and Vertex fails signed out. If no sidecar was live, mutation starts none.
If ownership or retirement is not conclusive, the committed authorization state
remains authoritative but no replacement is started.

When retirement times out after a committed connect/save, require
`vertex_restart_required`, retain the newly committed store, and prove the stale
sidecar rejects the new generation before provider work. Never attempt a store
rollback after its generation was published.

- [ ] **Step 4: Implement model-aware startup**

Change the existing signature from `async def ensure_chirp_running() -> dict`
to `async def ensure_chirp_running(required_model: str | None = None) -> dict`.

Resolve the effective model from explicit request, process `CHIRP_MODEL`,
canonical Chirp `.env`, then current Chirp defaults. An admitted
`vertex_ai/gemini-*` model requires fresh bootstrap; another `vertex_ai/*`
family fails before launch. Existing managed live health `absent|stale` triggers
the bounded ownership-aware same-port recycle above. Extend `_start_chirp` with
an optional requested port used only after verified retirement; ordinary cold
start remains OS-assigned port `0`.

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

Require the exact installed interpreter
`%LOCALAPPDATA%\Rook\venv\Scripts\python.exe`, explicit project/region/admitted
`vertex_ai/gemini-*` model, application client material, an owned temporary
evidence root, and positive watchdogs. Refuse source-tree imports, unsupported
Vertex families, missing ownership sentinel, arbitrary output paths, or absent
live-call acknowledgement before browser launch. `--acceptance-level technical`
permits an explicitly approved test OAuth client. `--acceptance-level
production` additionally requires separate acknowledgements for the production
client, completed applicable Google verification, published enterprise-admin
guidance, and managed-business validation.

The result allowlist is exactly:

```python
{
    "schema_version",
    "success",
    "acceptance_level",
    "stages",
    "error_code",
    "rook_commit",
    "chirp_commit",
    "installed_versions",
}
```

`acceptance_level` is exactly `failed`, `technical_pass`, or
`production_ready`. A test client can never produce `production_ready`. No
project, region, model, client identity, token, credential path, raw exception,
provider body, prompt, or model response is recorded.

- [ ] **Step 2: Implement one mechanically bounded non-MCP sequence**

The harness verifies installed provenance, calls backend connect, and calls the
explicit readiness operation. Passive status is tested separately with network
and refresh doubles and never substitutes for readiness. The live sequence then
uses these exact installed consumer seams:

| Consumer | Invocation seam | Fixed prompt/input | Machine success predicate | Ceiling |
| --- | --- | --- | --- | --- |
| Rook Chat | `ChatRunner.run_turn()` from the installed `rook-mcp` distribution with the explicit model and a no-op tool executor | `Return the marker {run_marker} in a short sentence. Do not call tools.` | At least one `text_delta`, one terminal `done`, no `error` or `tool_start`, and concatenated text contains `run_marker` | 180 s |
| DSPy/agent | installed `configure_dspy(model=..., temperature=0, max_tokens=64, cache=False)` followed by one `dspy.Predict` signature `marker -> echoed_marker` | unique `run_marker` | result field is a nonempty string containing `run_marker`; no fallback model or API key was resolved | 180 s |
| Chirp | installed `rook.server._call_tool_dispatch("chirp_create", ...)`, using the existing owned `_run_chirp_smoke_mutation` cleanup path inside a dedicated Rhino runtime-harness child | classifier component, fixed `input -> result` signature, one optional string input left empty, explicit Vertex model | new component GUID, inspected `Result` is a nonempty string, `gh_errors` has no entry for it, and final snapshot exactly restores the pre-run instance set | 360 s |

The fixed structure—not the generated prose—is normative. Each run creates a
fresh non-secret marker and checks containment rather than byte-exact model
output. The complete outer sequence has a `900`-second watchdog and the owned
Rhino cleanup has a `30`-second ceiling. The script preserves body and cleanup
failures separately when both occur. It calls disconnect only with explicit
`--disconnect`. It never invokes an MCP login tool, opens a production UI, or
uses Codex/Claude CLI mediation.

- [ ] **Step 3: Strengthen packaging guards**

Require both generated Rook and Chirp locks to contain the exact Task 0-admitted
`google-auth` pin (expected `2.56.3`) with the staged hash. Require exactly one
matching wheel and reject another Google auth version. Derive total wheel count
from the manifest rather than hardcoding it.

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
- Consumes: reviewed Rook production head, merged Chirp head, approved test or production desktop client, approved identity, organization project, region, and admitted `vertex_ai/gemini-*` model.
- Produces: exact installed provenance and redacted `failed|technical_pass|production_ready` evidence; no published release.

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
uv pip check --python .\.venv\Scripts\python.exe

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

Push the exact reviewed Rook head, open a private PR, fetch current `main`,
require a clean synthetic merge and no conflicting path movement, then merge
with a regular two-parent merge. Record the Rook and earlier Chirp merge SHA,
each merge's first parent, and each reviewed second parent as immutable 40-hex
values. Do not squash or build from a feature head after merge. Supply those six
recorded values to Step 4; do not derive them from a branch tip.

- [ ] **Step 4: Create detached source checkouts at the two merge SHAs**

```powershell
$rookRepo = 'C:\Users\aryan\source\repos\Rook'
$chirpRepo = 'C:\Users\aryan\source\repos\Chirp'
$rookMerge = $env:ROOK_VERTEX_MERGE_SHA
$rookFirstParent = $env:ROOK_VERTEX_FIRST_PARENT_SHA
$rookReviewedHead = $env:ROOK_VERTEX_REVIEWED_HEAD_SHA
$chirpMerge = $env:CHIRP_VERTEX_MERGE_SHA
$chirpFirstParent = $env:CHIRP_VERTEX_FIRST_PARENT_SHA
$chirpReviewedHead = $env:CHIRP_VERTEX_REVIEWED_HEAD_SHA
foreach ($entry in @{
    rook_merge = $rookMerge
    rook_first_parent = $rookFirstParent
    rook_reviewed_head = $rookReviewedHead
    chirp_merge = $chirpMerge
    chirp_first_parent = $chirpFirstParent
    chirp_reviewed_head = $chirpReviewedHead
}.GetEnumerator()) {
    if ($entry.Value -notmatch '^[0-9a-f]{40}$') { throw "Missing/invalid recorded SHA: $($entry.Key)" }
}
git -C $rookRepo fetch origin --prune
git -C $chirpRepo fetch origin --prune
$rookParents = @((git -C $rookRepo rev-list --parents -n 1 $rookMerge).Trim().Split(' '))
$chirpParents = @((git -C $chirpRepo rev-list --parents -n 1 $chirpMerge).Trim().Split(' '))
if ($rookParents.Count -ne 3 -or $rookParents[1] -ne $rookFirstParent -or $rookParents[2] -ne $rookReviewedHead) { throw 'Recorded Rook merge parent mismatch' }
if ($chirpParents.Count -ne 3 -or $chirpParents[1] -ne $chirpFirstParent -or $chirpParents[2] -ne $chirpReviewedHead) { throw 'Recorded Chirp merge parent mismatch' }
git -C $rookRepo merge-base --is-ancestor $rookMerge origin/main
if ($LASTEXITCODE -ne 0) { throw 'Recorded Rook merge is not reachable from origin/main' }
git -C $chirpRepo merge-base --is-ancestor $chirpMerge origin/master
if ($LASTEXITCODE -ne 0) { throw 'Recorded Chirp merge is not reachable from origin/master' }
$rookRelease = "C:\Users\aryan\source\repos\Rook\.worktrees\vertex-release-$($rookMerge.Substring(0,8))"
$chirpRelease = "C:\Users\aryan\source\repos\Chirp\.worktrees\vertex-release-$($chirpMerge.Substring(0,8))"
if (Test-Path -LiteralPath $rookRelease) { throw 'Rook release checkout exists' }
if (Test-Path -LiteralPath $chirpRelease) { throw 'Chirp release checkout exists' }
git -C $rookRepo worktree add --detach $rookRelease $rookMerge
git -C $chirpRepo worktree add --detach $chirpRelease $chirpMerge
if (git -C $rookRelease status --porcelain) { throw 'Rook release checkout dirty' }
if (git -C $chirpRelease status --porcelain) { throw 'Chirp release checkout dirty' }
```

The block above is the required parent/reachability verification. Do not replace
the supplied values with `rev-parse origin/main` or `rev-parse origin/master`.

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

Record reviewer approval without recording identities or configuration values.
Choose exactly one acceptance level. Technical acceptance may use an approved
test client. Production readiness additionally requires all four production
prerequisites:

```text
managed business identity approved: yes
organization project approved: yes
region and model approved: yes
readiness plus three benign text calls approved: yes
acceptance level: technical | production
production OAuth client ready: yes | not_applicable
Google verification complete: yes | not_applicable
enterprise-admin guidance published: yes | not_applicable
managed-business production-client validation approved: yes | not_applicable
```

Any `not_applicable` production prerequisite limits the result to
`technical_pass`.

- [ ] **Step 8: Run installed OAuth/readiness and three consumers**

Run the source-controlled harness with the installed interpreter. The harness
internally uses the exact seams, prompts, predicates, and watchdogs from Task 6;
it launches and owns the Rhino process used for the Chirp stage and refuses a
preexisting canvas or an unverified PID/port pair.

```powershell
$installedPython = "$env:LOCALAPPDATA\Rook\venv\Scripts\python.exe"
$acceptanceScript = Join-Path $rookRelease 'scripts\vertex_oauth_acceptance.py'
$evidenceRoot = Join-Path $env:TEMP ("rook-vertex-acceptance-" + [guid]::NewGuid().ToString('N'))
$resultPath = Join-Path $evidenceRoot 'result.json'
$required = @(
    'ROOK_VERTEX_ACCEPTANCE_PROJECT',
    'ROOK_VERTEX_ACCEPTANCE_REGION',
    'ROOK_VERTEX_ACCEPTANCE_MODEL',
    'ROOK_VERTEX_DESKTOP_CLIENT_JSON'
)
foreach ($name in $required) {
    $value = [Environment]::GetEnvironmentVariable($name, 'Process')
    if ([string]::IsNullOrWhiteSpace($value)) { throw "Missing process-scoped acceptance input: $name" }
}
if ($env:ROOK_VERTEX_ACCEPTANCE_MODEL -notmatch '^vertex_ai/gemini-[A-Za-z0-9._-]+$') { throw 'Acceptance model is outside the admitted family' }
if (-not (Test-Path -LiteralPath $env:ROOK_VERTEX_DESKTOP_CLIENT_JSON -PathType Leaf)) { throw 'Desktop client fixture is missing' }
New-Item -ItemType Directory -Path $evidenceRoot | Out-Null
& $installedPython $acceptanceScript `
    --acceptance-level technical `
    --project $env:ROOK_VERTEX_ACCEPTANCE_PROJECT `
    --region $env:ROOK_VERTEX_ACCEPTANCE_REGION `
    --model $env:ROOK_VERTEX_ACCEPTANCE_MODEL `
    --desktop-client-json $env:ROOK_VERTEX_DESKTOP_CLIENT_JSON `
    --evidence-root $evidenceRoot `
    --watchdog-seconds 900 `
    --run-consumers
if ($LASTEXITCODE -ne 0) { throw 'Installed Vertex acceptance failed' }
$result = Get-Content -Raw -LiteralPath $resultPath | ConvertFrom-Json
if ($result.success -ne $true -or $result.acceptance_level -ne 'technical_pass') { throw 'Technical acceptance result was not green' }
$requiredStages = @('installed_provenance','oauth','readiness','chat','dspy','chirp','canvas_cleanup','process_cleanup')
foreach ($stage in $requiredStages) {
    if ($result.stages.$stage -ne 'passed') { throw "Acceptance stage failed: $stage" }
}
```

For a production-readiness run, replace `--acceptance-level technical` with
`--acceptance-level production` and add exactly
`--production-client-ready --google-verification-complete
--enterprise-admin-guidance-published
--managed-business-production-validated`; then require
`$result.acceptance_level -eq 'production_ready'`. Do not reinterpret a
technical run afterward. Complete browser OAuth and explicit readiness before
the three consumers. The fixed Chat and DSPy predicates must pass; the Chirp
component must produce a nonempty inspected result, then the harness removes
only its owned component and proves exact canvas restoration.

While Vertex is configured, prove existing `gemini/...` configuration still
resolves independently and RookVision Gemini/Veo settings remain unchanged. Do
not issue image/video generation for this acceptance. Also issue one local
unsupported-family probe and require `vertex_model_family_unsupported` with
zero token-refresh/provider calls.

- [ ] **Step 9: Disconnect, scan, clean, and record evidence**

Call the same harness exactly as follows:

```powershell
& $installedPython $acceptanceScript `
    --desktop-client-json $env:ROOK_VERTEX_DESKTOP_CLIENT_JSON `
    --evidence-root $evidenceRoot `
    --watchdog-seconds 60 `
    --disconnect
if ($LASTEXITCODE -ne 0) { throw 'Installed Vertex disconnect failed' }
```

Prove
subsequent Vertex resolution fails closed, `vertex.json` is absent, sibling Rook
data is unchanged, and Gemini/local/Rook remain healthy. Scan logs, passive
health, diagnostics, process command lines/environments, discovery, manifests,
and report artifacts for credential sentinels. Close owned hosts and sidecars
gracefully and require zero owned processes/discovery entries. Preserve and
report both body and cleanup failure codes if both occur.

Create the evidence branch from the exact merge, then use `apply_patch` to write
exact Rook/Chirp merge SHAs, installed inventory hashes, test counts, and
`failed|technical_pass|production_ready` without
identity/project/region/model/client/token details:

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

- Gemini-only Vertex admission, provider split, and no fallback: Tasks 1 through 7.
- Operating ownership and immutable store: Task 1.
- Cross-process mutation, generation, and exact Chirp process ownership: Tasks 1, 4, and 5.
- OAuth admission, readiness, errors, and disconnect: Task 2.
- Rook Chat, agents, DSPy, and Chirp consumers: Tasks 3 through 5.
- Backend-only Phase 1 entry point: Task 6.
- Exact dependency admission and sealed delivery: Tasks 0, 1, 4, 6, and 7.
- Mechanical installed consumer acceptance, technical/production distinction, managed-business gate, and redaction: Tasks 6 and 7.
- Phase 3 installer lifecycle remains specified but unimplemented here.
- No Provider Setup UI, installer credential page, OAuth route/tool, generic broker/store, Google Cloud administration, RookVision Vertex path, model default, version bump, release artifact, or public promotion enters this plan.
