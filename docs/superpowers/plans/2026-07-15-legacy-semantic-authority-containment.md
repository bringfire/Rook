# Legacy Semantic-Authority Containment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the six approved legacy semantic tool identities undiscoverable and impossible to execute through every current Rook runtime path, while preserving exact stale-client tombstones, privacy-bounded denial evidence, and verified supported Rhino/Grasshopper workflows.

**Architecture:** Add one pure lifecycle leaf plus one tiny runtime denial adapter. Apply narrow lifecycle projections at existing catalog boundaries and shallow early returns at each inventoried execution seam; do not introduce a generalized authorization or executor framework. Reuse the existing metrics persistence for a bounded process-local denial ring. Certify the installed artifact with real MCP transport probes and a focused installed internal matrix, then run two separately authorized live preservation scenarios in gate-owned Rhino processes.

**Tech Stack:** Python 3.10+, pytest/pytest-asyncio, MCP `Server`/`ClientSession`/stdio transport, LiteLLM tool schemas, aiohttp RookChat service, Windows PowerShell 5.1, existing Rook runtime/deployment harnesses, Rhino 8 and Grasshopper.

## Global Constraints

- Design baseline: commit `e2e5c914e6e2db341e207d8b6d424234f8cf03e6` and `docs/superpowers/specs/2026-07-15-legacy-semantic-authority-containment-design.md` at that exact commit.
- Work only in `C:/Users/aryan/source/repos/Rook/.worktrees/gh-execute-intent-root-fix` on branch `codex/gh-execute-intent-root-fix`.
- Do not begin production implementation until this plan receives user and senior-reviewer approval.
- The six exact identities are:
  - retired: `gh_execute_intent`, `rhino_execute_intent`;
  - suspended: `plan_and_execute`, `spawn_agent`, `gh_explore_workflow`, `gh_replay_recipe`.
- No environment flag, maintenance profile, hidden direct-call allowance, packaged bypass, or test registration may reactivate a contained identity.
- Retired entries remain stale-client tombstones even if their bodies are later deleted. A suspended entry has no runtime removal path and may leave the manifest only through a separately reviewed change backed by approved durable restoration evidence outside the manifest.
- Do not rename, proxy, re-export, or delegate a contained semantic executor behind an admitted identity. Admitted tools may reuse only bounded mechanical primitives while preserving explicit arguments/code, deterministic checks, and observable host verification.
- Exact matching means `type(name) is str` and exact case-sensitive equality. Never call `str()`, trim, case-fold, normalize, prefix-match, substring-match, or fuzzy-match before lifecycle resolution.
- The binding interpretation of “before argument decoding” is: after only upstream transport framing/authentication needed to obtain the raw name, but before any Rook-owned or tool-specific parsing, copying, field access, logging, validation, or execution. Streamed argument assembly and protocol-history retention remain permitted.
- Pure catalog filtering never emits containment telemetry. Invocation guards resolve, make one best-effort recording attempt, and return immediately.
- `readonly` remains unchanged for active tools. Exact lifecycle tombstones precede every profile wall; malformed and near-match names keep ordinary non-enumerating behavior.
- Preserve latent profile/group/risk/targeting memberships where they are historical classification rather than runtime authority. Runtime projections must filter through the lifecycle manifest.
- Do not add external dependencies.
- Do not introduce active-catalog/build fingerprints, cache generations, quarantine, ambient denial scopes, a universal executor wrapper, a generic authorization platform, broad RookAgent/RookChat/PlanGraph redesign, or new Rhino/Grasshopper document-lifecycle authority.
- Historical plans, specifications, and postmortems remain intact unless they present themselves as current instructions. Current guidance must stop recommending contained tools.
- Implementation is sequential. Use a fresh implementer for each Task 1–10 in this same worktree. After each task, use a fresh spec-compliance reviewer, then a fresh code-quality reviewer. Fix every important finding and repeat the applicable review before advancing. Never run multiple implementation agents concurrently.
- A commit at the end of a task is a review checkpoint, not a releasable partial candidate. No partially filtered or partially guarded commit may be deployed or promoted.
- Task 10 ends with a fresh whole-branch spec review, a fresh whole-branch code-quality review, and the complete acceptance sequence.
- Every task is self-contained for a fresh implementer: start from the exact strict-shell worktree/Python/`PYTHONPATH` block repeated in that task; stage only its explicit file list; and do not rely on shell variables or unstated scan results from an earlier task. Every later PowerShell block in that task runs in that same verified shell; if a block is copied into a new shell, repeat the task environment block first.
- Every fresh PowerShell task block begins with `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'`, resolves and compares the exact working directory, proves the configured Python file exists, invokes it to report `sys.executable`, and compares the canonical executable paths case-insensitively before setting `PYTHONPATH`. Capture and test `$LASTEXITCODE` immediately after every native executable invocation—including Python/pytest, child PowerShell, Git, build tools, candidate tools, validators, and verifiers—before running any other command. All new production and test `.ps1` files put the same two fail-fast settings in their first executable lines after any `param(...)` block and inspect each child `Process.ExitCode` before the next stage.
- An expected-red command is valid only when the test/manual guard is collected or loaded successfully, exits exactly `1`, and emits its task's pinned `EXPECTED_RED:<task>:<case>` assertion marker. Because Windows PowerShell 5.1 turns redirected native stderr into a terminating `NativeCommandError` under `Stop`, each deliberate-red native capture saves the preference, uses `Continue` only inside a `try` around that one invocation, captures `$LASTEXITCODE` immediately, and restores `Stop` in `finally` before judging evidence. Pytest reds also write a fresh JUnit report; the task shell's `Assert-ExpectedRedResult` requires zero errors, at least one failure, and the pinned marker in every failure node, while rejecting collection, import, missing-path, no-tests, usage, and internal/infrastructure signatures. Tests for not-yet-created Python modules use `importlib.util.find_spec` inside a collected test; PowerShell guards test for an absent production script and throw the pinned marker themselves. A raw import error, parser error, missing command/file, timeout, unmarked assertion, or arbitrary nonzero exit is never an accepted red result.

## Fixed Runtime Contracts

The implementation must use these exact shapes.

Stable inner denial payload:

```json
{
  "code": "legacy_semantic_tool_contained",
  "tool": "<canonical-name>",
  "disposition": "retired|suspended",
  "retryable": false,
  "verified": false,
  "recovery": "<manifest-owned guidance>"
}
```

Internal envelope:

```json
{
  "success": false,
  "data": { "...": "stable inner denial payload" }
}
```

Public MCP wire result: exactly one `TextContent` whose text is `Error: <JSON inner payload>`.

Containment event payload, with no additional fields:

```json
{
  "tool": "<canonical-name>",
  "disposition": "retired|suspended",
  "origin": "<fixed-enum-origin>",
  "timestamp": "YYYY-MM-DDTHH:MM:SS.ffffffZ"
}
```

Fixed origins: `public_mcp`, `progressive_meta`, `server_dispatch`, `rook_agent`, `rook_chat`, `plan_graph`, `tool_dispatcher`, `internal_handler`.

Expected public discovery snapshots after filtering:

| Surface | Count |
|---|---:|
| Default/full | 422 |
| Interactive-enabled full | 425 |
| Lean | 20 |
| Readonly | 148 |

## File Responsibility Map

### Lifecycle and telemetry

- Create `mcp_server/src/rook/tool_lifecycle.py`: pure manifest, validation, exact resolver, fingerprint, payload/envelope builders, and narrow projection helpers.
- Create `mcp_server/src/rook/tool_lifecycle_runtime.py`: best-effort recording plus internal denial construction.
- Modify `mcp_server/src/rook/learning/metrics_store.py`: bounded `containment_denials` ring, persistence, process identity/start token, defensive accessor.
- Modify `mcp_server/src/rook/server.py`: expose the same-process accessor through the existing `metrics_summary` inspection result.
- Create `mcp_server/tests/test_tool_lifecycle.py` and `mcp_server/tests/test_containment_telemetry.py`.

### Catalogs, profiles, and startup refresh

- Modify `mcp_server/src/rook/server.py`: `_all_live_tools`, `list_tools`, AST dispatch-name projection, capability-index construction, startup refresh, and removal of handler-owned cache writes.
- Modify `mcp_server/src/rook/capability_index.py`.
- Modify `mcp_server/src/rook/agent/tool_registry.py`.
- Modify `mcp_server/src/rook/agent/capability_inventory.py` and `mcp_server/src/rook/agent/profile_reconciliation.py`.
- Modify `mcp_server/src/rook/agent/base_agent.py`, `mcp_server/src/rook/agent/chat/chat_runner.py`, `mcp_server/src/rook/agent/chat/server.py`, `mcp_server/src/rook/agent/tool_dispatcher.py`, and `mcp_server/src/rook/agent/spawn.py` at their existing schema/registration/cache boundaries.
- Use exactly the 14 pytest files and two manual guards listed under Task 2 **Files**—including creation of `test_tool_catalog_cache.py` and no scan-discovered additions.

### Server and dispatcher execution boundaries

- Modify `mcp_server/src/rook/server.py` at public MCP, progressive meta, server dispatch, `_mcp_tool_executor`, and private spawn/plan handlers.
- Modify `mcp_server/src/rook/agent/tool_dispatcher.py` at all four arbitrary-name execution seams and remove local `rhino_execute_intent` registration.
- Create `mcp_server/tests/test_containment_execution.py` and `mcp_server/tests/test_containment_supported_paths.py`; invert the exact obsolete positive public-path tests named in Task 3 before implementation.

### Packaged executor and learning boundaries

- Modify `mcp_server/src/rook/bootstrap/runner.py`, `mcp_server/src/rook/bootstrap/executor.py`, `mcp_server/src/rook/learning/agent.py`, `mcp_server/src/rook/learning/investigator.py`, `mcp_server/src/rook/learning/hybrid_investigator.py`, `mcp_server/src/rook/learning/session.py`, and `mcp_server/src/rook/explorer/executor.py`.
- Create `mcp_server/tests/test_containment_packaged_executors.py`.

### Model loops and PlanGraph

- Modify `mcp_server/src/rook/agent/base_agent.py`, `mcp_server/src/rook/agent/chat/chat_runner.py`, and `mcp_server/src/rook/agent/plan_graph_live.py`.
- Create `mcp_server/tests/test_containment_agent_protocols.py`; update `test_chat_runner.py`, `test_plan_graph_live.py`, and `test_plan_graph_live_dispatch.py`.

### Guidance, installed acceptance, live preservation, and standalone candidate acceptance

- Create `mcp_server/src/rook/containment_acceptance.py`: installed origin checks, discovery evidence, 36 real-transport probes, and installed internal bypass matrix.
- Create `mcp_server/src/rook/containment_live_gate.py`: interactive Rhino and Grasshopper preservation scenarios.
- Create `mcp_server/src/rook/resources/containment_empty.ghx` from the exact 2,708-byte UTF-8/LF fixture and SHA-256 pinned in Task 8, then prove it opens as empty before using it.
- Create `scripts/build-containment-candidate.ps1`: non-publishing installer build from the reviewed worktree SHA.
- Create `scripts/validate-containment-candidate.ps1` and `scripts/verify-containment-safe-rollback.ps1`.
- Do **not** modify `installer/RookSetup.iss`, `scripts/validate-release-artifacts.ps1`, its tests, the release-manifest schema, or either build-release skill. Tasks 9–10 stage the existing installer layout unchanged and produce a standalone non-publishable candidate, retained acceptance record, digest binding, and rollback verifier. Normal release-pipeline integration is deferred for separate approval.

---

### Task 1: Add the immutable lifecycle kernel and bounded denial telemetry

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files:**
- Create: `mcp_server/src/rook/tool_lifecycle.py`
- Create: `mcp_server/src/rook/tool_lifecycle_runtime.py`
- Modify: `mcp_server/src/rook/learning/metrics_store.py:140-370`
- Modify: `mcp_server/src/rook/server.py:19935-19943`
- Create: `mcp_server/tests/test_tool_lifecycle.py`
- Create: `mcp_server/tests/test_containment_telemetry.py`

**Interfaces produced for Tasks 2–10:**

```python
# rook.tool_lifecycle
class LifecycleDisposition(str, Enum): ...
class DispatchOrigin(str, Enum): ...

@dataclass(frozen=True)
class LifecycleEntry:
    name: str
    disposition: LifecycleDisposition
    recovery: str
    restoration_criteria: tuple[str, ...]
    aliases: tuple[str, ...]

def lifecycle_manifest() -> Mapping[str, LifecycleEntry]: ...
def contained_names() -> frozenset[str]: ...
def resolve_contained_identity(raw_name: object) -> LifecycleEntry | None: ...
def canonical_manifest_json() -> str: ...
def lifecycle_fingerprint() -> str: ...
def containment_payload(entry: LifecycleEntry) -> dict[str, object]: ...
def containment_envelope(entry: LifecycleEntry) -> dict[str, object]: ...
def filter_mcp_records(records: Iterable[object]) -> list[object]: ...
def filter_litellm_catalog(catalog: Mapping[object, object]) -> dict[object, object]: ...
def filter_litellm_schemas(schemas: Iterable[object]) -> list[object]: ...
def filter_local_registrations(registrations: Mapping[object, object]) -> dict[object, object]: ...

# rook.tool_lifecycle_runtime
def deny_if_contained(
    raw_name: object,
    origin: DispatchOrigin,
) -> dict[str, object] | None: ...

# rook.learning.metrics_store
class MetricsStore:
    def get_containment_denials_snapshot(self) -> dict[str, object]: ...

def get_metrics_store() -> MetricsStore: ...
```

**Manifest data (transcribe exactly; all V1 aliases are empty):**

```yaml
gh_execute_intent:
  disposition: retired
  recovery: "Rediscover the current Grasshopper surface; inspect state and components, then use explicit gh_edit or supported script tools and verify solve state, outputs, and errors."
  restoration_criteria: []

rhino_execute_intent:
  disposition: retired
  recovery: "Rediscover the current Rhino surface; use explicit typed Rhino tools, rhino_execute, or a sanctioned preflighted rhino_command, then verify the host result."
  restoration_criteria: []

plan_and_execute:
  disposition: suspended
  recovery: "Rediscover the current surface and perform bounded steps through explicit admitted tools; autonomous plan execution is suspended."
  restoration_criteria:
    - "A bounded plan contract limits admitted node identities, call counts, targets, and mutation scope."
    - "Every live node re-enters lifecycle and profile guards before parameters are copied or execution begins."
    - "Readiness, host verification, failure, and restoration evidence are deterministic and independently reviewed."

spawn_agent:
  disposition: suspended
  recovery: "Rediscover the current surface and use the connected model to call explicit admitted tools directly; autonomous agent spawning is suspended."
  restoration_criteria:
    - "Agent authority is bounded by admitted tool identities, explicit targets, deterministic call budgets, and stop conditions."
    - "Injected and local registries are filtered and every invocation independently re-enters lifecycle and profile guards."
    - "Live readiness, verification, restoration, and runaway-control evidence is recorded and independently approved."

gh_explore_workflow:
  disposition: suspended
  recovery: "Rediscover the current Grasshopper inspection surface and use explicit snapshot, component, or knowledge tools; semantic workflow exploration is suspended."
  restoration_criteria:
    - "The contract is proven host-read-only or every possible mutation is explicit, bounded, authorized, and verified."
    - "Knowledge or model output cannot directly carry mutation authority into a hidden executor."
    - "Deterministic tests and live evidence prove the bounded contract and absence of undeclared host mutation."

gh_replay_recipe:
  disposition: suspended
  recovery: "Rediscover the current Grasshopper surface and apply reviewed explicit gh_edit operations; recipe replay is suspended."
  restoration_criteria:
    - "Recipes use a versioned bounded schema containing only explicit admitted operations and validated arguments."
    - "Preflight establishes target ownership, readiness, mutation bounds, and a restoration plan before execution."
    - "Execution produces deterministic host verification and verified restoration or an approved durable recovery receipt."
```

- [ ] **Step 1: Write failing manifest, resolver, projection, and denial-contract tests**

Pin all six entries, dispositions, exact recovery strings, suspended criteria, empty aliases, and immutability. Parameterize every mechanical limit: name grammar/ASCII/128 bytes, 16 aliases, recovery 1–512 UTF-8 bytes and single-line/control-free, suspended criteria 1–16 and 256 UTF-8 bytes each, retired criteria empty, and identity collision rejection. Independently reject restoration criteria containing `\n`, `\r`, `\t`, NUL, or any other Unicode control character so the content rule is proven separately from the byte bound.

Use explicit non-coercion cases:

```python
@pytest.mark.parametrize("raw", [None, 1, b"gh_execute_intent", " GH_EXECUTE_INTENT", "gh_execute_intent ", "GH_EXECUTE_INTENT", "gh_execute"])
def test_resolver_never_coerces_or_normalizes(raw):
    assert resolve_contained_identity(raw) is None

@pytest.mark.parametrize("name", sorted(EXPECTED_NAMES))
def test_exact_identity_resolves(name):
    assert resolve_contained_identity(name).name == name
```

Test the anti-hiding projection independently:

```python
def test_mapping_projection_checks_raw_key_and_embedded_name():
    records = {
        "safe_key": schema("gh_execute_intent"),
        "rhino_execute_intent": schema("safe_embedded"),
        "safe": schema("safe"),
    }
    assert filter_litellm_catalog(records) == {"safe": schema("safe")}
```

Pin canonical JSON with entries sorted by canonical name, aliases sorted, object keys sorted, fixed separators, UTF-8 SHA-256, and declared restoration-criteria order. Pin the exact inner payload and internal envelope and assert restoration criteria never appear in either.

- [ ] **Step 2: Run the lifecycle tests and confirm the expected failure**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t1-lifecycle.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest mcp_server/tests/test_tool_lifecycle.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T1:LIFECYCLE' -JunitPath $RedJunit
```

Expected: FAIL because `rook.tool_lifecycle` does not exist.

- [ ] **Step 3: Implement the pure lifecycle leaf exactly as specified**

Use `MappingProxyType` for the manifest and identity index, frozen dataclasses, tuple fields, and import-time validation. The resolver must be structurally non-coercing:

```python
def resolve_contained_identity(raw_name: object) -> LifecycleEntry | None:
    if type(raw_name) is not str:
        return None
    return _IDENTITY_INDEX.get(raw_name)
```

The mapping projection must inspect raw key and embedded raw `function.name` before calling any normalizer:

```python
def filter_litellm_catalog(catalog: Mapping[object, object]) -> dict[object, object]:
    admitted: dict[object, object] = {}
    for raw_key, raw_record in catalog.items():
        function = raw_record.get("function") if isinstance(raw_record, Mapping) else None
        embedded = function.get("name") if isinstance(function, Mapping) else None
        if resolve_contained_identity(raw_key) or resolve_contained_identity(embedded):
            continue
        admitted[raw_key] = raw_record
    return admitted
```

Keep MCP-record, schema-list, and local-registration helpers equally narrow; do not add generalized mismatch or malformed-record validation.

- [ ] **Step 4: Write failing metrics-ring and runtime-denial tests**

Pin:

- `deque(maxlen=50)` eviction order;
- exact four event keys and UTC `Z` timestamp regex;
- no changes to `_recent`, period/tool aggregates, substrate, or `Observation` paths;
- existing `metrics.json` load/save round-trip under a temporary path;
- one module-level opaque start token generated exactly once per Python interpreter, shared by the canonical process-local `get_metrics_store()` singleton/accessor, and stable for the interpreter lifetime;
- defensive-copy behavior;
- restart/token mismatch invalidates a comparison helper;
- ring delta comparison proves one appended tail event while allowing the single expected head eviction when the bounded ring is already full; it must not use only `len(after) - len(before)`;
- one recording attempt/one ring event when healthy;
- forced recording failure/zero event/unchanged denial;
- `metrics_summary` reports only its own process snapshot and accessor reads emit no containment event;
- the existing `metrics_summary` result includes the defensive snapshot wherever ordinary profile rules already admit that call, without adding it to lean advertisement, changing the pinned 20-tool lean catalog, or creating a containment-specific profile exception;
- installed in-process RookChat probes use the accessor directly rather than adding a new chat-service endpoint.

Use a strict recorder spy:

```python
def test_denial_is_unchanged_when_recording_raises(monkeypatch):
    attempts = 0
    def explode(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        raise OSError("sink unavailable")
    monkeypatch.setattr(runtime, "_record_containment_denial", explode)
    actual = runtime.deny_if_contained("gh_execute_intent", DispatchOrigin.PUBLIC_MCP)
    assert attempts == 1
    assert actual == containment_envelope(resolve_contained_identity("gh_execute_intent"))
```

- [ ] **Step 5: Run telemetry tests and confirm the expected failure**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t1-telemetry.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest mcp_server/tests/test_containment_telemetry.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T1:TELEMETRY' -JunitPath $RedJunit
```

Expected: FAIL because the dedicated ring, accessor, and runtime adapter do not exist.

- [ ] **Step 6: Implement the ring, accessor, and best-effort runtime adapter**

`MetricsStore` owns a dedicated ring. Process identity is interpreter-owned, not store-instance-owned:

```python
_PROCESS_START_TOKEN = uuid.uuid4().hex  # once at module import per interpreter

self._containment_denials: deque[dict[str, str]] = deque(maxlen=50)
```

`record_containment_denial` accepts a validated `LifecycleEntry` and `DispatchOrigin`, generates the timestamp internally, appends once, and participates in the existing dirty/save lifecycle. It never calls `record(Observation)`.

The accessor shape is:

```python
{
    "process_id": os.getpid(),
    "process_start_token": _PROCESS_START_TOKEN,
    "events": copy.deepcopy(list(self._containment_denials)),
}
```

Pin `get_metrics_store()` as the only production store accessor and `MetricsStore.get_containment_denials_snapshot()` as the small read-only defensive snapshot used by tests and acceptance gates. Prove repeated calls return the same process-local singleton, PID, and interpreter token. Separate test stores may inject file paths, but may not mint replacement process tokens. Persist only the event list under `containment_denials`; PID/start token are live accessor metadata and are not persisted in events. Extend existing `metrics_summary` output with the same `containment_denials` snapshot for ordinary inspection, but installed acceptance must call the in-process read-only method directly rather than depend on a profile's advertised surface. RookChat tests and installed internal probes run in the importing process and call that method directly; do not add containment data to the unauthenticated health response.

The runtime adapter resolves first, attempts recording once, swallows every telemetry exception without argument-bearing logging, and returns the same code-owned envelope.

- [ ] **Step 7: Run Task 1 tests and focused regression tests**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_tool_lifecycle.py `
  mcp_server/tests/test_containment_telemetry.py `
  mcp_server/tests/test_chat_server.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 1 tests failed with exit code $LASTEXITCODE" }
```

Expected: PASS.

- [ ] **Step 8: Commit Task 1**

```powershell
git add mcp_server/src/rook/tool_lifecycle.py `
  mcp_server/src/rook/tool_lifecycle_runtime.py `
  mcp_server/src/rook/learning/metrics_store.py `
  mcp_server/src/rook/server.py `
  mcp_server/tests/test_tool_lifecycle.py `
  mcp_server/tests/test_containment_telemetry.py
if ($LASTEXITCODE -ne 0) { throw "Task 1 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask1 = @(
  'mcp_server/src/rook/tool_lifecycle.py', 'mcp_server/src/rook/tool_lifecycle_runtime.py',
  'mcp_server/src/rook/learning/metrics_store.py', 'mcp_server/src/rook/server.py',
  'mcp_server/tests/test_tool_lifecycle.py', 'mcp_server/tests/test_containment_telemetry.py'
) | Sort-Object
$ActualTask1 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 1 staged-file inspection failed with exit code $LASTEXITCODE" }
if (@(Compare-Object $ExpectedTask1 ($ActualTask1 | Sort-Object)).Count -ne 0) { throw 'Task 1 staged-file set mismatch' }
git commit -m "feat(containment): add lifecycle kernel and denial telemetry"
if ($LASTEXITCODE -ne 0) { throw "Task 1 commit failed with exit code $LASTEXITCODE" }
```

- [ ] **Step 9: Run the required Task 1 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 2 until both are clear.

---

### Task 2: Remove contained identities from every catalog and add safe startup refresh

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/capability_index.py`
- Modify: `mcp_server/src/rook/agent/tool_registry.py`
- Modify: `mcp_server/src/rook/agent/capability_inventory.py`
- Modify: `mcp_server/src/rook/agent/profile_reconciliation.py`
- Modify: `mcp_server/src/rook/agent/base_agent.py`
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/src/rook/agent/chat/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Modify: `mcp_server/src/rook/agent/spawn.py`
- Create: `mcp_server/tests/test_tool_catalog_cache.py`
- Modify: `mcp_server/tests/test_mcp_tool_profiles.py`
- Modify: `mcp_server/tests/test_server_tool_profiles.py`
- Modify: `mcp_server/tests/test_rook_tools_meta.py`
- Modify: `mcp_server/tests/test_capability_index.py`
- Modify: `mcp_server/tests/test_capability_inventory.py`
- Modify: `mcp_server/tests/test_profile_reconciliation.py`
- Modify: `mcp_server/tests/test_rookchat_tool_contracts.py`
- Modify: `mcp_server/tests/test_rookchat_tool_schema_golden.py`
- Modify: `mcp_server/tests/test_rookchat_visible_dispatchability.py`
- Modify: `mcp_server/tests/test_chat_runner.py`
- Modify: `mcp_server/tests/test_chat_server.py`
- Modify: `mcp_server/tests/test_base_agent_live_producer.py`
- Modify: `mcp_server/tests/test_dispatcher_safety.py`
- Modify: `mcp_server/tests/manual_phase2_dispatcher.py`
- Modify: `mcp_server/tests/manual_phase3_catalog.py`

**Cache interfaces:**

```python
@dataclass(frozen=True)
class CatalogCacheState:
    catalog: dict[str, dict] | None
    refresh_requested: bool
    source: Literal["current", "legacy", "fingerprint_mismatch", "missing", "unreadable"]

@dataclass(frozen=True)
class CatalogStartupResult:
    catalog: dict[str, dict] | None
    status: Literal["fresh", "degraded_cache", "degraded_fallback", "unavailable"]
    persisted: bool
    refresh_requested: bool

def load_catalog_cache_state(path: Path | None = None) -> CatalogCacheState: ...
def load_catalog_from_cache(path: Path | None = None) -> dict[str, dict] | None: ...
def save_catalog_to_cache(catalog: Mapping[str, dict], path: Path) -> bool: ...
async def refresh_catalog_at_startup(tool_loader, *, cache_path=None, fallback=None) -> CatalogStartupResult: ...
```

- [ ] **Step 1: Write failing projection tests at every concrete admission site**

Tests must independently inject a contained identity through:

- `_all_live_tools` and post-profile `list_tools`;
- AST-derived dispatch labels and `CapabilityIndex.build_index`;
- capability-inventory tier/group/route/local unions and profile reconciliation;
- `ToolRegistry` constructor, `register_local_catalog`, and `get_active_schemas`;
- RookAgent constructor schemas, `set_tool_schemas`, `register_local_tools`, and `_get_tool_schemas`;
- RookChat cached, fallback, local, overlay, injected registry, tool-section, and final `litellm.acompletion` schemas;
- `ToolDispatcher(local_tools=...)`, `register_local`, `register_locals`, and `all_known_tools`;
- planner/spawn injected registries.

For mapping records, include one key-hidden and one embedded-name-hidden case. Assert zero telemetry delta for every omission.

Pin consumer policy separately: lifecycle filtering must not reintroduce agent-management tools into consumers that already exclude them.

- [ ] **Step 2: Write failing cache/startup tests**

Cover:

- matching fingerprint still revalidates and removes a contained record;
- missing fingerprint legacy mapping remains safely readable and requests refresh;
- changed fingerprint requests refresh;
- corrupt, wrong-type, and empty cache handling;
- raw key/embedded-name hiding in cache data;
- save-path filtering before persistence: pass a dirty catalog containing one contained raw key with a safe embedded name and one safe raw key with a contained `function.name`, read the resulting JSON directly, and prove neither dirty record was written, the safe record remains, the caller input is unchanged, and telemetry is unchanged;
- refresh success and persistence success;
- fresh construction plus persistence failure returns fresh in-memory catalog;
- construction failure retains only safely revalidated older cache;
- rejected cache content never merges into fallback;
- no safe cache plus code-owned fallback uses filtered fallback;
- no safe cache/fallback returns explicit unavailable rather than an empty registry;
- `list_tools()` performs no file write;
- MCP and RookChat entrypoints call the explicit startup refresh once;
- canonical refresh uses unprofiled `_all_live_tools`, not profile-filtered `list_tools`.

Pin the on-disk envelope to only:

```json
{
  "lifecycle_fingerprint": "<sha256>",
  "catalog": { "...": "filtered LiteLLM records" }
}
```

No generation, active-catalog, schema, build, or cache-freshness fingerprint is allowed.

- [ ] **Step 3: Invert profile, golden, and manual exposure expectations before implementation**

Update `test_server_tool_profiles.py` to pin `422`, `425`, `20`, and `148` plus independent exact absence. Keep `test_mcp_tool_profiles.py` pinning the latent raw lean set at 22. Invert `test_rookchat_tool_schema_golden.py::test_local_catalog_rhino_execute_intent_schema_is_actionable` to assert omission. Replace the contradictory positive assertions in `manual_phase2_dispatcher.py` and `manual_phase3_catalog.py` with explicit containment expectations and port their useful cache assertions into `test_tool_catalog_cache.py`.

- [ ] **Step 4: Run every changed expectation and confirm the expected red state**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t2-projections.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest `
    mcp_server/tests/test_tool_catalog_cache.py `
    mcp_server/tests/test_mcp_tool_profiles.py `
    mcp_server/tests/test_server_tool_profiles.py `
    mcp_server/tests/test_rook_tools_meta.py `
    mcp_server/tests/test_capability_index.py `
    mcp_server/tests/test_capability_inventory.py `
    mcp_server/tests/test_profile_reconciliation.py `
    mcp_server/tests/test_rookchat_tool_contracts.py `
    mcp_server/tests/test_rookchat_tool_schema_golden.py `
    mcp_server/tests/test_rookchat_visible_dispatchability.py `
    mcp_server/tests/test_chat_runner.py `
    mcp_server/tests/test_chat_server.py `
    mcp_server/tests/test_base_agent_live_producer.py `
    mcp_server/tests/test_dispatcher_safety.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T2:PYTEST' -JunitPath $RedJunit
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python mcp_server/tests/manual_phase2_dispatcher.py 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T2:MANUAL_PHASE2'
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python mcp_server/tests/manual_phase3_catalog.py 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T2:MANUAL_PHASE3'
```

Expected: FAIL on current exposure and plain cache behavior.

- [ ] **Step 5: Apply lifecycle projection before normalization and at final model projection**

Required ordering examples:

```python
def build_catalog_from_mcp_tools(tools: list) -> dict[str, dict]:
    tools = filter_mcp_records(tools)
    ...

class ToolRegistry:
    def __init__(..., catalog=None, ...):
        raw_catalog = filter_litellm_catalog({} if catalog is None else catalog)
        self._catalog = normalize_catalog(raw_catalog)

    def register_local_catalog(self, catalog):
        admitted = filter_litellm_catalog(catalog)
        normalized = normalize_catalog(admitted)
        ...

    def get_active_schemas(self):
        return filter_litellm_schemas(existing_projection)
```

Filter `_all_live_tools` after the deprecated-interactive gate, and filter `list_tools` again after profile projection. Filter `_scan_dispatch_case_labels()` before caching `_DISPATCHABLE_TOOL_NAMES`. Add a defensive filter in `capability_index.build_index()` for direct/injected callers.

Preserve raw `PUBLIC_LEAN_TOOL_NAMES`, `PUBLIC_READONLY_TOOL_NAMES`, `TIER_0`, `TOOL_GROUPS`, targeting, and risk constants; filter only their runtime projections.

Remove the production `rhino_execute_intent` local registration block from `build_local_tools`; do not delete dormant implementation modules.

- [ ] **Step 6: Implement filtered persistence, load-time revalidation, and explicit startup refresh**

Every cache load must call `filter_litellm_catalog` before normalization regardless of stored fingerprint. The fingerprint only sets `refresh_requested`.

`save_catalog_to_cache` must independently call `filter_litellm_catalog` on the caller's raw mapping before constructing the fingerprint envelope and before writing its temporary file. Persist only the filtered copy; never mutate the caller mapping. Atomic replacement may occur only after the filtered envelope is serialized successfully. This closes both key-hidden and embedded-name-hidden dirty inputs on save instead of relying on a later load to repair them.

`refresh_catalog_at_startup` must load/revalidate the old cache first, then attempt fresh construction. A successful fresh build is returned even if atomic persistence fails. A failed build may return the revalidated old catalog or caller-provided code-owned fallback, never rejected content or `{}`.

Call the hook from:

- `server.main()` before entering MCP transport; failure logs degraded health but does not kill transport;
- RookChat `start_chat_server()` before constructing its runner; pass fresh in-memory catalog into the runner when persistence failed.

Remove catalog writes from `_handle_spawn_agent` and `_handle_plan_and_execute`. Keep `list_tools()` read-only. Update `spawn.py` cache consumers to use safe state and return `catalog_unavailable` when neither safe cache nor their existing code-owned fallback exists.

- [ ] **Step 7: Run Task 2 tests**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_tool_catalog_cache.py `
  mcp_server/tests/test_mcp_tool_profiles.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_capability_inventory.py `
  mcp_server/tests/test_profile_reconciliation.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_base_agent_live_producer.py `
  mcp_server/tests/test_dispatcher_safety.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 2 pytest set failed with exit code $LASTEXITCODE" }
& $Python mcp_server/tests/manual_phase2_dispatcher.py
if ($LASTEXITCODE -ne 0) { throw "manual_phase2_dispatcher failed with exit code $LASTEXITCODE" }
& $Python mcp_server/tests/manual_phase3_catalog.py
if ($LASTEXITCODE -ne 0) { throw "manual_phase3_catalog failed with exit code $LASTEXITCODE" }
```

Expected: PASS with runtime counts `422/425/20/148` and no containment telemetry from discovery filtering.

- [ ] **Step 8: Commit Task 2**

```powershell
git add mcp_server/src/rook/server.py `
  mcp_server/src/rook/capability_index.py `
  mcp_server/src/rook/agent/tool_registry.py `
  mcp_server/src/rook/agent/capability_inventory.py `
  mcp_server/src/rook/agent/profile_reconciliation.py `
  mcp_server/src/rook/agent/base_agent.py `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  mcp_server/src/rook/agent/chat/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/src/rook/agent/spawn.py `
  mcp_server/tests/test_tool_catalog_cache.py `
  mcp_server/tests/test_mcp_tool_profiles.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_capability_inventory.py `
  mcp_server/tests/test_profile_reconciliation.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_base_agent_live_producer.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/manual_phase2_dispatcher.py `
  mcp_server/tests/manual_phase3_catalog.py
if ($LASTEXITCODE -ne 0) { throw "Task 2 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask2 = @(
  'mcp_server/src/rook/server.py', 'mcp_server/src/rook/capability_index.py',
  'mcp_server/src/rook/agent/tool_registry.py', 'mcp_server/src/rook/agent/capability_inventory.py',
  'mcp_server/src/rook/agent/profile_reconciliation.py', 'mcp_server/src/rook/agent/base_agent.py',
  'mcp_server/src/rook/agent/chat/chat_runner.py', 'mcp_server/src/rook/agent/chat/server.py',
  'mcp_server/src/rook/agent/tool_dispatcher.py', 'mcp_server/src/rook/agent/spawn.py',
  'mcp_server/tests/test_tool_catalog_cache.py', 'mcp_server/tests/test_mcp_tool_profiles.py',
  'mcp_server/tests/test_server_tool_profiles.py', 'mcp_server/tests/test_rook_tools_meta.py',
  'mcp_server/tests/test_capability_index.py', 'mcp_server/tests/test_capability_inventory.py',
  'mcp_server/tests/test_profile_reconciliation.py', 'mcp_server/tests/test_rookchat_tool_contracts.py',
  'mcp_server/tests/test_rookchat_tool_schema_golden.py', 'mcp_server/tests/test_rookchat_visible_dispatchability.py',
  'mcp_server/tests/test_chat_runner.py', 'mcp_server/tests/test_chat_server.py',
  'mcp_server/tests/test_base_agent_live_producer.py', 'mcp_server/tests/test_dispatcher_safety.py',
  'mcp_server/tests/manual_phase2_dispatcher.py', 'mcp_server/tests/manual_phase3_catalog.py'
) | Sort-Object
$ActualTask2 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 2 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task2Delta = @(Compare-Object $ExpectedTask2 ($ActualTask2 | Sort-Object))
if ($Task2Delta.Count -ne 0) { throw "Task 2 staged-file set mismatch: $($Task2Delta | Out-String)" }
git commit -m "feat(containment): filter catalogs and refresh them safely"
if ($LASTEXITCODE -ne 0) { throw "Task 2 commit failed with exit code $LASTEXITCODE" }
```

- [ ] **Step 9: Run the required Task 2 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 3 until both are clear.

---

### Task 3: Deny public MCP, server, private-handler, and ToolDispatcher calls

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files:**
- Modify: `mcp_server/src/rook/server.py`
- Modify: `mcp_server/src/rook/agent/tool_dispatcher.py`
- Create: `mcp_server/tests/test_containment_execution.py`
- Create: `mcp_server/tests/test_containment_supported_paths.py`
- Modify: `mcp_server/tests/test_dispatcher_safety.py`
- Modify: `mcp_server/tests/test_rook_tools_meta.py`
- Modify: `mcp_server/tests/test_server_contract_hardening.py`
- Modify: `mcp_server/tests/test_gh_edit_postmortem.py`
- Modify: `mcp_server/tests/test_bridge.py`
- Delete/replace coverage from: `mcp_server/tests/test_gh_execute_intent_handoff_live.py`

- [ ] **Step 1: Write the failing boundary matrix and invert obsolete positive tests**

Parameterize all six exact names over full, lean, and readonly for direct `call_tool`, and again as the raw `rook_tools_call.name`. Exercise the real registered `server.mcp.request_handlers[mcp_types.CallToolRequest]` for both forms before testing the lower Python functions. Independently probe `_handle_meta_tool`, `_call_tool_dispatch`, `_mcp_tool_executor`, `_handle_spawn_agent`, `_handle_plan_and_execute`, and all four ToolDispatcher seams: `dispatch`, `_dispatch_inner`, `_call_local`, and `_dispatch_with_knowledge`. Pin the complete `(seam, tool)` keyset; arbitrary-name seams get six probes, while the two identity-specific handlers get only their own canonical name.

For each attempt assert the exact boundary adapter, origin, one recording attempt and one healthy-ring event, and zero argument/schema/profile/capability/knowledge/model/target/host/observation/substrate/receipt spy entries. Use poison mappings that permit only the raw outer target-name read. At the registered MCP handler, poison `mcp.server.lowlevel.server.Server._get_cached_tool_definition`, the SDK module's `jsonschema.validate`, and the nested progressive `arguments`; exact direct/meta tombstones must bypass all three. An admitted active tool must still delegate to the retained SDK handler and preserve its existing schema-validation error, proving the bypass is tombstone-only. Add sequential, sibling, nested-meta, and direct-deeper-boundary cases to prove structural exact-once behavior without ambient state.

Before any production edit, replace public `gh_execute_intent` handoff expectations in `test_server_contract_hardening.py` with tombstones, invert the positive `gh_replay_recipe` public case in `test_gh_edit_postmortem.py`, invert local `rhino_execute_intent` dispatcher cases, and remove the obsolete live intent-handoff test in favor of `test_containment_supported_paths.py`. In `test_bridge.py`, rename/invert `test_panel_lock_blocks_spawn_agent_before_background_task`: exact `spawn_agent` must return `legacy_semantic_tool_contained` before target discovery or background-task entry. Preserve the profile/target wall regression with a separate admitted `rhino_workbench_list` call that still returns `panel_target_locked`. Dormant bodies remain directly testable only with mocked model and host boundaries.

`test_containment_supported_paths.py` must already describe the intended green state for admitted typed Rhino tools, `rhino_execute`, a sanctioned preflighted `rhino_command`, `gh_edit`, `gh_snapshot`, `gh_errors`, `gh_create_script`, `gh_update_script`, and `gh_set_script`. Include the supported typed route that reuses the safe bounded Rhino primitive formerly reachable beneath `rhino_execute_intent`; it must emit no containment event.

- [ ] **Step 2: Run the changed tests and confirm the expected red state**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t3-boundaries.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest `
    mcp_server/tests/test_containment_execution.py `
    mcp_server/tests/test_containment_supported_paths.py `
    mcp_server/tests/test_rook_tools_meta.py `
    mcp_server/tests/test_dispatcher_safety.py `
    mcp_server/tests/test_server_contract_hardening.py `
    mcp_server/tests/test_gh_edit_postmortem.py `
    mcp_server/tests/test_bridge.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T3:BOUNDARIES' -JunitPath $RedJunit
```

Expected: FAIL because the current execution paths remain reachable and the newly inverted expectations are not implemented.

- [ ] **Step 3: Add the shallow server guards in the required order**

`call_tool` guards its raw outer name before argument copying, profile checks, name-prefix logic, targeting, or tool-specific validation. A direct denial calls `_format_tool_result` once. For outer `rook_tools_call`, pass the original mapping unchanged to `_handle_meta_tool`; there, read only raw `arguments.get("name")`, guard with `progressive_meta` before capability-index construction or nested `arguments`, format once, and return that same `TextContent` list unchanged through `call_tool`.

The MCP SDK's registered handler currently performs cached-schema lookup and `jsonschema.validate` before invoking `call_tool`, so import `from mcp import types as mcp_types` and add one concrete transport pre-guard after `@mcp.call_tool()` registration. Retain the original `mcp.request_handlers[mcp_types.CallToolRequest]` and install an idempotent wrapper at that exact key. After reading only `req.params.name`, an exact direct contained name calls the Rook `call_tool` function with `arguments=None` (and `call_tool`'s annotation explicitly permits `dict[str, Any] | None`); after reading only the raw outer mapping and raw `name` field, exact `rook_tools_call` plus an exact contained nested name calls `call_tool("rook_tools_call", raw_outer_mapping)`. Both paths convert the already formatted `list[TextContent]` exactly once to `mcp_types.ServerResult(mcp_types.CallToolResult(content=contents, isError=False))`. They do not call the retained SDK handler, schema cache, or validator. Every malformed, near-match, unknown, or admitted call delegates unchanged to the retained SDK handler, preserving all existing SDK validation and normalization. This is a single boundary adapter for the known SDK ordering—not a general request framework, profile exception, or alternate dispatcher.

Guard `_call_tool_dispatch` before timer/argument/port/phase/knowledge/dispatch/observation work, `_mcp_tool_executor` before its `try` or redispatch, and the private spawn/plan handlers at their constant identity before imports, tasks, models, plans, or `arguments.get`. Preserve exact tombstone precedence over all profiles and ordinary behavior for malformed or near-match names.

- [ ] **Step 4: Add the four independent ToolDispatcher guards**

Guard `dispatch` before counters or params; guard `_dispatch_inner`, `_call_local`, and `_dispatch_with_knowledge` independently before lookup, transformation, knowledge, routing, logging, or host work. The first denying boundary returns, so an outer call never reaches a downstream guard; a separately invoked deeper seam is a new attempt. Verify Task 2 removed the `rhino_execute_intent` local registration and do not recreate it under another key.

- [ ] **Step 5: Run Task 3 tests**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_gh_edit_postmortem.py `
  mcp_server/tests/test_bridge.py `
  mcp_server/tests/test_substrate_analytics.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 3 tests failed with exit code $LASTEXITCODE" }
```

Expected: PASS, including unchanged `tool_profile_blocked` behavior for active readonly-blocked tools.

- [ ] **Step 6: Commit only Task 3 files**

```powershell
git add mcp_server/src/rook/server.py `
  mcp_server/src/rook/agent/tool_dispatcher.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_gh_edit_postmortem.py `
  mcp_server/tests/test_bridge.py `
  mcp_server/tests/test_gh_execute_intent_handoff_live.py
if ($LASTEXITCODE -ne 0) { throw "Task 3 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask3 = @(
  'mcp_server/src/rook/server.py', 'mcp_server/src/rook/agent/tool_dispatcher.py',
  'mcp_server/tests/test_containment_execution.py', 'mcp_server/tests/test_containment_supported_paths.py',
  'mcp_server/tests/test_dispatcher_safety.py', 'mcp_server/tests/test_rook_tools_meta.py',
  'mcp_server/tests/test_server_contract_hardening.py', 'mcp_server/tests/test_gh_edit_postmortem.py',
  'mcp_server/tests/test_bridge.py', 'mcp_server/tests/test_gh_execute_intent_handoff_live.py'
) | Sort-Object
$ActualTask3 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 3 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task3Delta = @(Compare-Object $ExpectedTask3 ($ActualTask3 | Sort-Object))
if ($Task3Delta.Count -ne 0) { throw "Task 3 staged-file set mismatch: $($Task3Delta | Out-String)" }
git commit -m "feat(containment): deny server and dispatcher seams"
if ($LASTEXITCODE -ne 0) { throw "Task 3 commit failed with exit code $LASTEXITCODE" }
```

- [ ] **Step 7: Run the Task 3 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 4 until both are clear.

---

### Task 4: Deny packaged bootstrap, learning, and explorer execution paths

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files:**
- Modify: `mcp_server/src/rook/bootstrap/runner.py`
- Modify: `mcp_server/src/rook/bootstrap/executor.py`
- Modify: `mcp_server/src/rook/learning/agent.py`
- Modify: `mcp_server/src/rook/learning/investigator.py`
- Modify: `mcp_server/src/rook/learning/hybrid_investigator.py`
- Modify: `mcp_server/src/rook/learning/session.py`
- Modify: `mcp_server/src/rook/explorer/executor.py`
- Create: `mcp_server/tests/test_containment_packaged_executors.py`

- [ ] **Step 1: Write the complete failing packaged-boundary matrix**

Probe all six names independently through:

- `BootstrapRunner.run_test` and `_mock_executor`;
- bootstrap `HttpExecutor.execute` and the callable returned by `create_mock_executor()`;
- the callable returned by learning `create_tool_executor()`;
- `Investigator.investigate_tool`, `investigate_gap`, `investigate_workflow`, and `_run_experiment`;
- `HybridInvestigator.investigate_tool` and `investigate_gap`;
- `LearningSession.run_investigation_cycle("tool:<name>")`; and
- explorer `HttpExecutor.execute`, `MockExecutor.execute`, and both sync-delegation paths.

Every guard uses `internal_handler`. Pin the exact `(seam, tool)` keyset and all-six cardinality. Poison params, gap fields after `gap.tool`, workflow parameter tuples, knowledge stores, DSPy planners, MAB selectors, schema/parameter generators, timers, endpoints, HTTP clients, viewport capture, executors, knowledge/adaptation recorders, and host calls. A denial must read only the identity needed at that seam and return before every poison spy.

Pin adapters exactly:

- `BootstrapRunner.run_test`: after reading only `test.tool`, return `TestResult(test_id=f"containment:{canonical_name}", tool=canonical_name, params={}, expected=ExpectedOutcome.EITHER, actual=TestOutcome.ERROR, response=internal_envelope, error_message="legacy_semantic_tool_contained", duration_ms=0.0, timestamp=<system-generated UTC ISO 8601 ending Z>, created_object_ids=[])`. The ID and expected value are code-owned; do not read `test.id`, `test.expected`, or any further `TestCase` field. Do not update `completed_tests` or any knowledge/MAB/adaptive record.
- Explorer HTTP/mock: `ExecutionResult(tool_name=canonical_name, params={}, success=False, response=internal_envelope, error="legacy_semantic_tool_contained", duration_ms=0.0)`. There is no `refusal_detail` field and no claimed host result. Sync methods only delegate to the guarded async method and therefore record once.
- `Investigator._run_experiment`: canonical tool, `params={}`, `success=False`, internal envelope in `response`, `error="legacy_semantic_tool_contained"`, and `execution_time_ms=0`.

Add `containment_denial: dict[str, object] | None = None` to both `InvestigationResult` and `HybridInvestigationResult`; include it in `HybridInvestigationResult.to_dict()`. Higher learning boundaries return their established result type with canonical tool, the internal envelope in `containment_denial`, and every experiment/evidence/selection/adaptation list empty, attempts/time zero, optional diagnosis/hash/selection fields `None`, and verification/gap-resolution flags false. This is a local return adapter, not a new execution framework.

- [ ] **Step 2: Run the packaged matrix and confirm it fails**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t4-packaged.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest mcp_server/tests/test_containment_packaged_executors.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T4:PACKAGED_EXECUTORS' -JunitPath $RedJunit
```

Expected: FAIL because current bootstrap mocks can succeed and learning paths reach knowledge, DSPy, parameter generation, or host work before the lower executor seam.

- [ ] **Step 3: Add shallow guards at the packaged executors**

Guard `BootstrapRunner.run_test` immediately after reading only `test.tool`, before dependency checks or `test.params`; independently guard its `_mock_executor`. Guard bootstrap HTTP/mock callables and the learning-agent returned callable before params, endpoint selection, timing, transformation, or host work. Guard explorer HTTP and mock async methods before the current timer and endpoint mapping; leave sync wrappers as delegates only.

- [ ] **Step 4: Guard every pre-executor learning entry**

At the first line of both `investigate_tool` methods, resolve the raw `tool_name` and return the typed refusal before result construction, logging, knowledge, setup, DSPy/MAB, schema lookup, parameter generation, viewport capture, or execution. Keep `_run_experiment` as an independently guarded deeper seam.

For both `investigate_gap` methods, read only `gap.tool`, guard, and return before `gap.id`, hypotheses, knowledge mutation, DSPy, setup, params, or executor access. `Investigator.investigate_workflow` first preflights only every raw step name without reading or copying any step params; if any is contained, return its typed refusal before the first supported step can mutate. Only after the entire name preflight passes may the ordinary workflow resolve parameters.

At the beginning of `LearningSession.run_investigation_cycle`, identify an exact `tool:<name>` target and guard the extracted name before updating `progress`, reporter state, logs, or either investigator. Return the basic or hybrid typed refusal according to the session's existing `use_hybrid` selection; do not call a downstream investigator and do not record twice.

- [ ] **Step 5: Run Task 4 tests**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_supported_paths.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 4 tests failed with exit code $LASTEXITCODE" }
```

Expected: PASS with one event per direct attempt and no mock success, model, knowledge, generated params, target, or host entry.

- [ ] **Step 6: Commit only Task 4 files**

```powershell
git add mcp_server/src/rook/bootstrap/runner.py `
  mcp_server/src/rook/bootstrap/executor.py `
  mcp_server/src/rook/learning/agent.py `
  mcp_server/src/rook/learning/investigator.py `
  mcp_server/src/rook/learning/hybrid_investigator.py `
  mcp_server/src/rook/learning/session.py `
  mcp_server/src/rook/explorer/executor.py `
  mcp_server/tests/test_containment_packaged_executors.py
if ($LASTEXITCODE -ne 0) { throw "Task 4 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask4 = @(
  'mcp_server/src/rook/bootstrap/runner.py', 'mcp_server/src/rook/bootstrap/executor.py',
  'mcp_server/src/rook/learning/agent.py', 'mcp_server/src/rook/learning/investigator.py',
  'mcp_server/src/rook/learning/hybrid_investigator.py', 'mcp_server/src/rook/learning/session.py',
  'mcp_server/src/rook/explorer/executor.py', 'mcp_server/tests/test_containment_packaged_executors.py'
) | Sort-Object
$ActualTask4 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 4 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task4Delta = @(Compare-Object $ExpectedTask4 ($ActualTask4 | Sort-Object))
if ($Task4Delta.Count -ne 0) { throw "Task 4 staged-file set mismatch: $($Task4Delta | Out-String)" }
git commit -m "feat(containment): deny packaged executor seams"
if ($LASTEXITCODE -ne 0) { throw "Task 4 commit failed with exit code $LASTEXITCODE" }
```

- [ ] **Step 7: Run the Task 4 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 5 until both are clear.

---

### Task 5: Preserve RookAgent, RookChat, and PlanGraph refusal semantics

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files:**
- Modify: `mcp_server/src/rook/agent/base_agent.py`
- Modify: `mcp_server/src/rook/agent/chat/chat_runner.py`
- Modify: `mcp_server/src/rook/agent/plan_graph_live.py`
- Create: `mcp_server/tests/test_containment_agent_protocols.py`
- Modify: `mcp_server/tests/test_chat_runner.py`
- Modify: `mcp_server/tests/test_plan_graph_live.py`
- Modify: `mcp_server/tests/test_plan_graph_live_dispatch.py`
- Modify: `mcp_server/tests/test_base_agent_live_producer.py`

- [ ] **Step 1: Write failing RookAgent protocol tests**

Pin three classes of model-loop behavior:

1. Abort, steering, and exhausted-call-budget checks skip before containment: no argument parse and no event.
2. Eligible denial increments `calls_this_turn`, appends exactly one `role: tool` message using the original tool-call ID and serialized internal envelope, then allows ordinary primary-model continuation under existing budgets.
3. Denial never enters `tool_names_used`, tool-start/end events, substrate, observations, created IDs, failure adaptation, or successful/adaptive history. A denial-only round never calls `_post_turn_adapt`; a mixed round calls it once with admitted names only.

Patch `json.loads`, executor, knowledge, observation, event, substrate, and adaptation functions with fail-fast spies. Retain raw argument text only in the pre-existing assistant protocol message.

Directly call `_execute_tool` and `_execute_local_tool`; each direct call is its own one-record attempt with origin `rook_agent`.

- [ ] **Step 2: Write failing RookChat and PlanGraph tests**

For RookChat, assert denial:

- consumes the current tool round;
- sets `meta_only_round=False`;
- appends one protocol result with original ID;
- stays out of `tools_used` and progressive adaptation;
- yields no `tool_start`/`tool_result` events;
- never parses raw arguments or invokes executor/host/model from containment;
- is detected on each raw `tool_calls_list` entry before `_ToolCall` construction or any second copy of `arguments`; only the earlier assistant protocol message may retain the streamed raw text;
- permits the already-connected primary model to continue on the next ordinary round.

For PlanGraph, use a parameter mapping that raises on get/copy/deepcopy. A contained `execution_ref` must return `tool_lifecycle_denied`, `applied=False`, `outcome_status=None`, and the identical input graph object before `_resolve_params`, dispatch, outcome projection, or receipt creation. Origin is `plan_graph`.

- [ ] **Step 3: Run the protocol tests and confirm they fail**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t5-protocols.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest `
    mcp_server/tests/test_containment_agent_protocols.py `
    mcp_server/tests/test_chat_runner.py `
    mcp_server/tests/test_plan_graph_live.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T5:AGENT_PROTOCOLS' -JunitPath $RedJunit
```

Expected: FAIL because current loops parse and emit normal execution events first.

- [ ] **Step 4: Implement RookAgent loop and direct-seam refusals**

In the model loop, preserve existing skip checks first. Then resolve only the raw function name:

```python
raw_name = tool_call.function.name

# Existing abort/steering/budget skip handling remains here and returns no denial.

denial = deny_if_contained(raw_name, DispatchOrigin.ROOK_AGENT)
if denial is not None:
    calls_this_turn += 1
    self.messages.append({
        "role": "tool",
        "tool_call_id": tool_call.id,
        "content": json.dumps(denial, separators=(",", ":")),
    })
    continue
```

Only after that branch fails to match may the loop assign `tool_name = raw_name` and call `json.loads`. Do not route denial through ordinary result normalization. After the loop call `_post_turn_adapt(tool_names_used)` only when `tool_names_used` is non-empty; this suppresses denial-only adaptation and lets mixed rounds adapt admitted tools only.

Add independent early guards to `_execute_tool` and `_execute_local_tool` before registry/meta/local checks, gotchas, timing, params, observations, or counters.

- [ ] **Step 5: Implement RookChat refusal semantics**

Remove the eager `choice_tool_calls = [_ToolCall(...)]` adaptation. Iterate each raw `tool_calls_list` mapping, read only `raw_tc["name"]`, and guard before constructing any wrapper or reading/copying `raw_tc["arguments"]`. On denial, set `meta_only_round=False`, then read only `raw_tc["id"]` to append the protocol result and continue without adding `tools_used` or emitting normal events. The already-assembled assistant protocol message may retain raw argument text; containment creates no second copy. Adapt and decode admitted entries only after their guard misses.

Do not prohibit the next ordinary `litellm.acompletion`; the already-connected primary model may continue. Test that no model is invoked by containment itself or a dormant implementation.

- [ ] **Step 6: Implement the narrow PlanGraph refusal**

Add `tool_lifecycle_denied` to `LiveProducerReason`. Immediately after `_resolve_tool_name(node.execution_ref)` returns the existing `tool_name` and before `_resolve_params`, call the guard. Return `_not_applied(graph, node_id, tool_name, "tool_lifecycle_denied")` with the identical graph object. `LiveProducerResult` has no refusal-detail field, so do not invent one; telemetry and the typed reason carry the refusal. Do not pass denial through host-result projection or create a receipt.

`plan_graph_live_dispatch.py` remains a delegating adapter and does not add a second guard. Update the import-boundary test to permit only the pure lifecycle/runtime modules while retaining server/dispatcher/chat prohibitions.

- [ ] **Step 7: Run Task 5 tests**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_base_agent_live_producer.py `
  mcp_server/tests/test_plan_graph_live.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  mcp_server/tests/test_substrate_analytics.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 5 tests failed with exit code $LASTEXITCODE" }
```

Expected: PASS with exact protocol history and no ordinary execution/adaptation evidence.

- [ ] **Step 8: Commit Task 5**

```powershell
git add mcp_server/src/rook/agent/base_agent.py `
  mcp_server/src/rook/agent/chat/chat_runner.py `
  mcp_server/src/rook/agent/plan_graph_live.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_base_agent_live_producer.py `
  mcp_server/tests/test_plan_graph_live.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py
if ($LASTEXITCODE -ne 0) { throw "Task 5 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask5 = @(
  'mcp_server/src/rook/agent/base_agent.py', 'mcp_server/src/rook/agent/chat/chat_runner.py',
  'mcp_server/src/rook/agent/plan_graph_live.py', 'mcp_server/tests/test_containment_agent_protocols.py',
  'mcp_server/tests/test_chat_runner.py', 'mcp_server/tests/test_base_agent_live_producer.py',
  'mcp_server/tests/test_plan_graph_live.py', 'mcp_server/tests/test_plan_graph_live_dispatch.py'
) | Sort-Object
$ActualTask5 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 5 staged-file inspection failed with exit code $LASTEXITCODE" }
if (@(Compare-Object $ExpectedTask5 ($ActualTask5 | Sort-Object)).Count -ne 0) { throw 'Task 5 staged-file set mismatch' }
git commit -m "feat(containment): preserve agent and plangraph refusals"
if ($LASTEXITCODE -ne 0) { throw "Task 5 commit failed with exit code $LASTEXITCODE" }
```

- [ ] **Step 9: Run the required Task 5 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 6 until both are clear.

---

### Task 6: Remove current guidance that recommends contained identities

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files (this is the complete scan and allowed-edit set):**

- Create: `mcp_server/tests/test_containment_guidance.py`
- Top/current files: `AGENTS.md`, `CLAUDE.md`, `AGENT_SETUP.md`, `README.md`, `.claude/hookify.rhino-command-safety.local.md`, `.claude/hookify.rhino-execute-safety.local.md`, `installer/CLAUDE.md`, `installer/AGENTS.md`, `docs/ONBOARDING_NEW_CLAUDE.md`, `docs/TROUBLESHOOTING.md`, `docs/AGENT_ARCHITECTURE.md`, `docs/CURRENT_ARCHITECTURE.md`, `docs/rook_docs/POSITIONING.md`, `docs/rook_docs/work-queue.md`, `scripts/session-start.sh`, `mcp_server/src/rook/server.py`, `mcp_server/src/rook/learning/dspy_signatures.py`, `mcp_server/src/rook/agent/chat/prompt_builder.py`, `mcp_server/src/rook/agent/chat/chat_runner.py`, `mcp_server/src/rook/agent/prompts/WORKER.md`, `mcp_server/src/rook/agent/personas/architect/role.md`, `mcp_server/src/rook/agent/personas/explorer/role.md`, `mcp_server/src/rook/agent/personas/worker/role.md`, and `mcp_server/tests/test_e2e_agents.py`.
- Under **both** `.agents/skills/` and `.claude/skills/`, these exact relative files: `_template/SKILL.md`, `_template/references/gotchas.md`, `_template/references/knowledge-integration.md`, `chirp-cascade/references/wasp-grammar-authoring.md`, `consolidate/SKILL.md`, `consolidate/references/consolidation-paths.md`, `design-grasshopper/references/wasp-domain-context.md`, `design-grasshopper/references/wasp-rhino-scaffold.md`, `design-road/references/road-rhino-scaffold.md`, `execute-grasshopper/SKILL.md`, `execute-grasshopper/references/checkpoint-protocol.md`, `plan-grasshopper/SKILL.md`, `plan-grasshopper/references/tool-call-patterns.md`, `plan-grasshopper/references/wasp/wasp-aggregate.md`, `plan-grasshopper/references/wasp/wasp-catalog.md`, `plan-grasshopper/references/wasp/wasp-constraints.md`, `plan-grasshopper/references/wasp/wasp-disco-export.md`, `plan-grasshopper/references/wasp/wasp-field.md`, `plan-grasshopper/references/wasp/wasp-grammar-aggregate.md`, `plan-grasshopper/references/wasp/wasp-hierarchy.md`, `plan-grasshopper/references/wasp/wasp-learn.md`, `plan-grasshopper/references/wasp/wasp-parts.md`, `plan-grasshopper/references/wasp/wasp-rules.md`, `plan-grasshopper/references/wasp/wasp-save-load.md`, `twisted-column/SKILL.md`, `twisted-column/references/hollowing-gotchas.md`, and `validate-security/SKILL.md`.
- Installed mirrors (the complete current affected set under the recursively shipped tree): `installer/agent-assets/codex-skills/chirp-cascade/references/wasp-grammar-authoring.md`, `installer/agent-assets/codex-skills/design-grasshopper/references/wasp-domain-context.md`, `installer/agent-assets/codex-skills/design-grasshopper/references/wasp-rhino-scaffold.md`, `installer/agent-assets/codex-skills/design-road/references/road-rhino-scaffold.md`, `installer/agent-assets/codex-skills/execute-grasshopper/references/checkpoint-protocol.md`, `installer/agent-assets/codex-skills/execute-grasshopper/SKILL.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/tool-call-patterns.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-aggregate.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-catalog.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-constraints.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-disco-export.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-field.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-grammar-aggregate.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-hierarchy.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-learn.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-parts.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-rules.md`, `installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-save-load.md`, `installer/agent-assets/codex-skills/plan-grasshopper/SKILL.md`, `installer/agent-assets/codex-skills/twisted-column/references/hollowing-gotchas.md`, and `installer/agent-assets/codex-skills/twisted-column/SKILL.md`.

- [ ] **Step 1: Use the writing-skills discipline and write the failing current-guidance scan**

The implementer must read and use `superpowers:writing-skills` before editing any skill. `test_containment_guidance.py` scans exactly the top/current and paired-skill file sets above for positive call syntax and recommendation phrases involving all six identities. It must also use direct `Path.rglob` traversal—not default `rg` or ignore-aware globbing—to scan every regular text file under `installer/agent-assets/codex-skills`, because `RookSetup.iss` recursively ships that whole tree and broad repository ignore rules hide some `references/` paths from ordinary search. The test reads `RookSetup.iss` as an unchanged audit input and fails if the recursive shipment contract is no longer present; the installer file is not edited or staged. The explicit 21-file affected inventory above is the allowed edit/stage set; any newly discovered shipped match fails the test and requires plan/review rather than a dynamic edit. This includes both enabled Hookify rules, active DSPy signature instructions, and the real model-facing instructions in `test_e2e_agents.py`. It separately builds the final advertised schemas and scans model-visible names/descriptions, including the current `gh_session_history` example in `server.py`. It may allow explicit lifecycle wording containing `contained`, `retired`, or `suspended`, plus negative tests that prove a contained identity is absent/unavailable; it must not treat dormant implementation comments as model guidance.

Dated evidence under `docs/superpowers`, dated `docs/rook_docs`, versioned development-practice history, and knowledge JSON/JSONL is outside this task. Do not rewrite incident evidence. `docs/AGENT_ARCHITECTURE.md` is current-looking and must receive a visible supersession note; the active row in mixed-history `docs/rook_docs/work-queue.md` and the canonical/current lifecycle statement in `docs/rook_docs/POSITIONING.md` must be corrected without rewriting their dated history. Update `AGENTS.md`'s current public-surface count to 422 by default and 425 with the interactive gate.

- [ ] **Step 2: Run the new scan immediately and confirm it fails before guidance edits**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t6-guidance.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest mcp_server/tests/test_containment_guidance.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T6:GUIDANCE' -JunitPath $RedJunit
```

Expected: FAIL on the current positive recommendations and model-visible examples.

- [ ] **Step 3: Replace only active recommendations**

Direct current callers to rediscover the admitted surface, inspect state, use explicit typed tools or explicit code/script tools, verify the host result, and restore as appropriate. Never claim a replacement exists under readonly, that LM9A executes a replacement, or that `spawn_agent` refreshes a catalog. Preserve each skill's triggers and bounded workflow while replacing contained calls with currently admitted explicit operations. Keep the `.agents` and `.claude` copies of every paired file byte-identical. Remove the fallback `rhino_execute_intent` schema/description and `spawn_agent` refresh advice from RookChat; Task 2's lifecycle projection remains the authority.

- [ ] **Step 4: Run guidance and prompt regressions**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_containment_guidance.py `
  mcp_server/tests/test_chat_prompt_builder.py `
  mcp_server/tests/test_chat_runner.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 6 guidance regressions failed with exit code $LASTEXITCODE" }
```

Expected: PASS, with no positive current recommendation and no stale installer mirror.

- [ ] **Step 5: Stage the exact Task 6 set and commit**

```powershell
$TopFiles = @(
  'mcp_server/tests/test_containment_guidance.py', 'AGENTS.md', 'CLAUDE.md', 'AGENT_SETUP.md', 'README.md',
  '.claude/hookify.rhino-command-safety.local.md',
  '.claude/hookify.rhino-execute-safety.local.md',
  'installer/CLAUDE.md', 'installer/AGENTS.md', 'docs/ONBOARDING_NEW_CLAUDE.md',
  'docs/TROUBLESHOOTING.md', 'docs/AGENT_ARCHITECTURE.md', 'docs/CURRENT_ARCHITECTURE.md',
  'docs/rook_docs/POSITIONING.md', 'docs/rook_docs/work-queue.md',
  'scripts/session-start.sh', 'mcp_server/src/rook/server.py',
  'mcp_server/src/rook/learning/dspy_signatures.py',
  'mcp_server/src/rook/agent/chat/prompt_builder.py', 'mcp_server/src/rook/agent/chat/chat_runner.py',
  'mcp_server/src/rook/agent/prompts/WORKER.md',
  'mcp_server/src/rook/agent/personas/architect/role.md',
  'mcp_server/src/rook/agent/personas/explorer/role.md',
  'mcp_server/src/rook/agent/personas/worker/role.md',
  'mcp_server/tests/test_e2e_agents.py'
)
$SkillSuffixes = @(
  '_template/SKILL.md', '_template/references/gotchas.md', '_template/references/knowledge-integration.md',
  'chirp-cascade/references/wasp-grammar-authoring.md', 'consolidate/SKILL.md',
  'consolidate/references/consolidation-paths.md', 'design-grasshopper/references/wasp-domain-context.md',
  'design-grasshopper/references/wasp-rhino-scaffold.md', 'design-road/references/road-rhino-scaffold.md',
  'execute-grasshopper/SKILL.md', 'execute-grasshopper/references/checkpoint-protocol.md',
  'plan-grasshopper/SKILL.md', 'plan-grasshopper/references/tool-call-patterns.md',
  'plan-grasshopper/references/wasp/wasp-aggregate.md', 'plan-grasshopper/references/wasp/wasp-catalog.md',
  'plan-grasshopper/references/wasp/wasp-constraints.md', 'plan-grasshopper/references/wasp/wasp-disco-export.md',
  'plan-grasshopper/references/wasp/wasp-field.md', 'plan-grasshopper/references/wasp/wasp-grammar-aggregate.md',
  'plan-grasshopper/references/wasp/wasp-hierarchy.md', 'plan-grasshopper/references/wasp/wasp-learn.md',
  'plan-grasshopper/references/wasp/wasp-parts.md', 'plan-grasshopper/references/wasp/wasp-rules.md',
  'plan-grasshopper/references/wasp/wasp-save-load.md', 'twisted-column/SKILL.md',
  'twisted-column/references/hollowing-gotchas.md', 'validate-security/SKILL.md'
)
$SkillFiles = foreach ($root in @('.agents/skills', '.claude/skills')) {
  foreach ($suffix in $SkillSuffixes) { "$root/$suffix" }
}
$InstalledFiles = @(
  'installer/agent-assets/codex-skills/chirp-cascade/references/wasp-grammar-authoring.md',
  'installer/agent-assets/codex-skills/design-grasshopper/references/wasp-domain-context.md',
  'installer/agent-assets/codex-skills/design-grasshopper/references/wasp-rhino-scaffold.md',
  'installer/agent-assets/codex-skills/design-road/references/road-rhino-scaffold.md',
  'installer/agent-assets/codex-skills/execute-grasshopper/references/checkpoint-protocol.md',
  'installer/agent-assets/codex-skills/execute-grasshopper/SKILL.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/tool-call-patterns.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-aggregate.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-catalog.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-constraints.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-disco-export.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-field.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-grammar-aggregate.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-hierarchy.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-learn.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-parts.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-rules.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/references/wasp/wasp-save-load.md',
  'installer/agent-assets/codex-skills/plan-grasshopper/SKILL.md',
  'installer/agent-assets/codex-skills/twisted-column/references/hollowing-gotchas.md',
  'installer/agent-assets/codex-skills/twisted-column/SKILL.md'
)
git add -f -- @($TopFiles + $SkillFiles + $InstalledFiles)
if ($LASTEXITCODE -ne 0) { throw "Task 6 staging failed with exit code $LASTEXITCODE" }
$ActualStaged = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 6 staged-file inspection failed with exit code $LASTEXITCODE" }
$ExpectedStaged = @($TopFiles + $SkillFiles + $InstalledFiles) | Sort-Object -Unique
$StagingDelta = @(Compare-Object $ExpectedStaged ($ActualStaged | Sort-Object -Unique))
if ($StagingDelta.Count -ne 0) { throw "Task 6 staged-file set mismatch: $($StagingDelta | Out-String)" }
git commit -m "docs(containment): remove legacy semantic guidance"
if ($LASTEXITCODE -ne 0) { throw "Task 6 commit failed with exit code $LASTEXITCODE" }
```

- [ ] **Step 6: Run the Task 6 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 7 until both are clear.

---

### Task 7: Add installed-runtime containment certification

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Task 7 prerequisite — repair the cold baseline JSON spy in a separate commit:**

Before creating, resuming, or staging either Task 7 implementation file, repair only
`mcp_server/tests/test_containment_agent_protocols.py`. The steering parameter
currently patches `base_agent_module.json.loads`, which mutates the process-wide
stdlib `json` module and counts legitimate lazy `UnifiedStore` reads as tool
argument decoding. Preserve the admitted `safe_tool` path and its blocking-gotcha
middleware; do not prewarm knowledge state or stub `_check_blocking_gotchas`.

First run the cold steering case and require its existing marked assertion
failure:

```powershell
$PrerequisiteRedJunit = Join-Path $env:TEMP 'rook-containment-t7-prerequisite.xml'
if (Test-Path -LiteralPath $PrerequisiteRedJunit) { Remove-Item -LiteralPath $PrerequisiteRedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $PrerequisiteRedOutput = @(
    & $Python -m pytest `
      'mcp_server/tests/test_containment_agent_protocols.py::test_rook_agent_skips_before_containment_and_argument_decode[steering]' `
      --junitxml $PrerequisiteRedJunit -q 2>&1
  )
  $PrerequisiteRedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult `
  -ExitCode $PrerequisiteRedExit `
  -Output $PrerequisiteRedOutput `
  -Marker 'EXPECTED_RED:T5:AGENT_PROTOCOLS' `
  -JunitPath $PrerequisiteRedJunit
```

Then replace the shared-module mutation with this module-local proxy:

```python
real_json = base_agent_module.json

def tracking_loads(raw, *args, **kwargs):
    parsed_arguments.append(raw)
    return real_json.loads(raw, *args, **kwargs)

monkeypatch.setattr(
    base_agent_module,
    "json",
    SimpleNamespace(
        load=real_json.load,
        loads=tracking_loads,
        dumps=real_json.dumps,
        JSONDecodeError=real_json.JSONDecodeError,
    ),
)
```

Use `real_json.loads(...)` for the later skipped-result assertion. This keeps
the spy scoped to `RookAgent`'s JSON lookup while all other importers retain the
real stdlib module. Verify all three skip modes and the complete protocol file,
then commit and review this one-file prerequisite independently:

```powershell
& $Python -m pytest `
  'mcp_server/tests/test_containment_agent_protocols.py::test_rook_agent_skips_before_containment_and_argument_decode' -q
if ($LASTEXITCODE -ne 0) { throw "Task 7 prerequisite skip-order tests failed with exit code $LASTEXITCODE" }
& $Python -m pytest mcp_server/tests/test_containment_agent_protocols.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 7 prerequisite protocol tests failed with exit code $LASTEXITCODE" }
git add mcp_server/tests/test_containment_agent_protocols.py
if ($LASTEXITCODE -ne 0) { throw "Task 7 prerequisite staging failed with exit code $LASTEXITCODE" }
$ExpectedTask7Prerequisite = @('mcp_server/tests/test_containment_agent_protocols.py')
$ActualTask7Prerequisite = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 7 prerequisite staged-file inspection failed with exit code $LASTEXITCODE" }
$Task7PrerequisiteDelta = @(Compare-Object $ExpectedTask7Prerequisite ($ActualTask7Prerequisite | Sort-Object))
if ($Task7PrerequisiteDelta.Count -ne 0) { throw "Task 7 prerequisite staged-file set mismatch: $($Task7PrerequisiteDelta | Out-String)" }
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "Task 7 prerequisite staged diff check failed with exit code $LASTEXITCODE" }
git commit -m "test(containment): isolate agent JSON decode spy"
if ($LASTEXITCODE -ne 0) { throw "Task 7 prerequisite commit failed with exit code $LASTEXITCODE" }
```

Run a fresh spec-compliance review and then a fresh code-quality review of that
prerequisite commit. Fix and re-review every important finding before resuming
the two-file Task 7 implementation. The Task 7 implementation staging allowlist
below remains unchanged.

**Files:**
- Create: `mcp_server/src/rook/containment_acceptance.py`
- Create: `mcp_server/tests/test_containment_acceptance.py`

**Installed commands produced:**

```text
<installed-python.exe> -m rook.containment_acceptance transport-profile --profile full --artifact-dir <dir>
<installed-python.exe> -m rook.containment_acceptance transport-profile --profile lean --artifact-dir <dir>
<installed-python.exe> -m rook.containment_acceptance transport-profile --profile readonly --artifact-dir <dir>
<installed-python.exe> -m rook.containment_acceptance discovery-default --artifact-dir <dir>
<installed-python.exe> -m rook.containment_acceptance discovery-interactive --artifact-dir <dir>
<installed-python.exe> -m rook.containment_acceptance internal-matrix --artifact-dir <dir>
```

The three transport-profile parents start this private acceptance-only installed child as their MCP stdio command; users do not invoke it directly:

```text
<installed-python.exe> -m rook.containment_acceptance _transport-child --profile <full|lean|readonly> --run-id <32-hex> --spy-path <fresh-absolute-json>
```

- [ ] **Step 1: Write failing installed-harness contract tests**

Pin deterministic JSON artifacts containing the executable, installed root, cwd, relevant environment, full `sys.path`, all loaded `rook.*` origins, PID/start token, discovery schemas/counts, ordered probes, adjacent telemetry snapshots, fixed-stage spy counters, and exact results. Reject any repo/worktree path or module origin. Contract tests must exercise the private stdio child end to end, reject source imports or an absent/malformed spy artifact, and prove there is no caller-supplied spy module, tool list, handler, or bypass option.

Each profile artifact has twelve ordered real-transport probes: six direct public MCP calls and six public `rook_tools_call` calls. Across explicit full/lean/readonly that is exactly 36. Direct probes expect one `TextContent`, exact payload, `public_mcp`, one recording attempt/ring append, stable process identity, and zero downstream spies. Progressive probes expect the same except `progressive_meta`; the transport pre-guard routes the unchanged raw outer mapping through `call_tool`, `_handle_meta_tool` reads the exact contained nested identity and denies before any outer or nested profile work or capability-index construction, formats once, and `call_tool` returns that same result unchanged. Both direct and progressive probes therefore require zero profile-stage entries. Two additional discovery-only children are outside the 36: `discovery-default` runs with `ROOK_MCP_TOOL_PROFILE` genuinely absent and proves count 422; `discovery-interactive` runs with full plus only the interactive gate enabled and proves count 425. Both prove all six names absent and zero containment-event delta through the direct in-process accessor.

Pin this installed internal seam set rather than accepting self-registration:

```text
server._call_tool_dispatch
server._mcp_tool_executor
ToolDispatcher.dispatch
ToolDispatcher._dispatch_inner
ToolDispatcher._call_local
ToolDispatcher._dispatch_with_knowledge
RookAgent._run_loop
RookAgent._execute_tool
RookAgent._execute_local_tool
ChatRunner.run_turn
rook.agent.plan_graph_live.apply_live_producer_node
server._handle_spawn_agent              # spawn_agent only
server._handle_plan_and_execute          # plan_and_execute only
BootstrapRunner.run_test
BootstrapRunner._mock_executor
bootstrap.HttpExecutor.execute
bootstrap.create_mock_executor.callable
learning.create_tool_executor.callable
Investigator.investigate_tool
Investigator.investigate_gap
Investigator.investigate_workflow
Investigator._run_experiment
HybridInvestigator.investigate_tool
HybridInvestigator.investigate_gap
LearningSession.run_investigation_cycle.tool_target
explorer.HttpExecutor.execute
explorer.HttpExecutor.execute_sync
explorer.MockExecutor.execute
explorer.MockExecutor.execute_sync
```

The 27 arbitrary-name seams each get six probes (162); the two private constant handlers add one each, for exactly 164 internal probes. Tests compare the exact `(seam, tool)` set and reject missing or extra entries. Each probe records its adapter, origin, adjacent ring delta from `get_metrics_store().get_containment_denials_snapshot()`, recording-attempt count, and untouched argument/schema/knowledge/downstream-model/target/HTTP/host/observation/adaptation/receipt spies. Construct `rook.bootstrap.executor.HttpExecutor` directly with the pinned inert literal `base_url="http://127.0.0.1:9"`; never use `create_http_executor`, which pings during factory construction. Give the explorer HTTP executor the same inert literal. Invoke both explorer `execute_sync` probes as top-level synchronous calls outside an active event loop. Every delegated guard must fire before discovery, endpoint construction, HTTP, or params.

The loop fixtures are explicit and have a separate `primary_model_calls` counter. For `RookAgent._run_loop`, construct a real installed `RookAgent`, preseed its normal message state, and replace only that instance's `_call_model` with a code-owned bounded stub: call 1 returns one denied tool call, call 2 returns a terminal no-tool response, and any third call raises. Then await `_run_loop()` and require exactly two primary calls. For `ChatRunner.run_turn`, construct the installed runner/conversation and install a code-owned streaming-provider stub with exactly two rounds: round 1 assembles one raw denied call and round 2 is terminal; any additional provider/model call raises. Consume the async generator and require exactly two primary calls. These are the already-connected primary model's ordinary request/continuation, not a model invoked by containment. Every other internal probe requires `primary_model_calls=0`, and all probes keep separate downstream/containment-triggered/dormant-model spies armed at zero.

Add negative harness tests for source contamination, profile/count drift, malformed payload, wrong origin, missing/duplicate ring entry, PID/start-token replacement, spy entry, unexpected call-tool requests, and internal seam-set drift. Give both the production transport pre-guard and acceptance bracketing wrapper an outer mapping whose `name` read succeeds but whose nested `arguments` access raises; both must return the tombstone without touching the poison field. Pin the fixed patchpoint table below as an exact unit-test value: removing, replacing, or adding any target must make child setup fail rather than leave a zero-filled counter. Exercise every installed wrapper's private code-owned self-test sentinel and the wrapper factory's scoped/unscoped paths before live counters are reset. Ring comparison must recognize one tail append plus the corresponding oldest eviction at capacity.

- [ ] **Step 2: Run the harness tests and confirm they fail**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t7-installed.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest mcp_server/tests/test_containment_acceptance.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T7:INSTALLED_HARNESS' -JunitPath $RedJunit
```

Expected: FAIL because the installed acceptance module does not exist.

- [ ] **Step 3: Implement real installed MCP transport and origin proof**

Follow `rook.doctor::_probe_mcp` with `StdioServerParameters`, `stdio_client`, and `ClientSession`; do not call `server.call_tool` directly for transport evidence. For each profile, the parent creates a fresh private spy path and uses the exact `_transport-child` command above as `StdioServerParameters.command/args`. The child imports only the installed `rook.server`, validates its own source-free origins, installs the code-owned fixed-stage spies described below, calls the same explicit catalog-startup refresh, and then runs the installed `server.mcp` with `stdio_server()` and `mcp.run(...)`. Its stdout is exclusively MCP framing; diagnostics go to stderr and its spy artifact. It accepts no arbitrary module, callable, tool identity, or argument-capture hook.

Every installed-Python process in Tasks 7–10—transport-profile parents, their private stdio children, both discovery children, the internal matrix, and both live-gate children—starts from a sanitized environment before Python imports `rook`. Remove `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`, `DSPY_CACHEDIR`, `CHIRP_HOME`, and every inherited key whose name begins `ROOK_` case-insensitively; then add only code-owned `PYTHONNOUSERSITE=1`, the validated installed-runtime values `ROOK_INSTALL_ROOT`, `ROOK_DATA_DIR`, `ROOK_MODE=release`, and `ROOK_DSPY_RESTRICT_PICKLE=1`, plus validated code-owned `DSPY_CACHEDIR` and optional code-owned `CHIRP_HOME`. `PYTHONUSERBASE` and `DSPY_MODEL` remain absent from every acceptance command; `PYTHONNOUSERSITE` is always the exact string `1`, never inherited, empty, or caller-supplied. A profile command may additionally add its exact `ROOK_MCP_TOOL_PROFILE`; only the interactive discovery command may add `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1`. Default discovery, the internal matrix, and both live gates leave profile, interactive, target/process/document, Rhino port/executable, harness, bridge, and model override variables absent. The transport parent applies the same wipe/re-add policy explicitly to `StdioServerParameters.env` for `_transport-child`; inheritance is not evidence of sanitization.

Each standard profile child therefore launches with explicit `ROOK_MCP_TOOL_PROFILE` before Python starts and cwd `%TEMP%/rook-containment/<run-id>/<profile>`. The default discovery child keeps `ROOK_MCP_TOOL_PROFILE` genuinely absent—an empty string is not acceptable—and records `profile_env_present: false`. The separate interactive child sets explicit full plus only `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1`. Add hostile-inheritance regressions that seed worktree `PYTHONPATH`, fake `PYTHONHOME`, mixed-case `PYTHONUSERBASE=<owned-base>`, and, beneath the version-specific user-site directory derived from that base (`<owned-base>\Python311\site-packages` for the installed 3.11 runtime), `sitecustomize.py` and `usercustomize.py`, each with the exact code `from pathlib import Path; Path(__file__).with_suffix('.hit').write_text('executed', encoding='ascii')`. Also seed mixed-case `PYTHONNOUSERSITE=0`, source-tree `CHIRP_HOME`, `DSPY_MODEL`, `DSPY_CACHEDIR`, and representative profile/target/process/document/Rhino/bridge/harness/model `ROOK_*` values. Before any Rook import, have every child policy—including Rhino and Grasshopper live modes—report its sanitized environment and have the parent inspect both external `.hit` markers; prove both markers absent, `PYTHONUSERBASE` absent, `PYTHONNOUSERSITE` exactly `1`, all other hostile values absent, `DSPY_CACHEDIR` replaced by its validated code-owned path, only each command's exact allowlist present, absent/default=422, explicit full=422, isolated interactive full=425, installed origins, and a source-free `sys.path`.

Do not use public `metrics_summary` as an acceptance control. Before opening stdio, execute `from mcp import types as mcp_types`, retain the already-installed production transport pre-guard at `server.mcp.request_handlers[mcp_types.CallToolRequest]`, and replace only that acceptance child's registered request handler with a thin private bracketing wrapper. Other request types, including initialize and list-tools, remain untouched. The wrapper accepts only (a) an exact contained direct `req.params.name`, or (b) exact outer `rook_tools_call` whose raw outer arguments have `type(...) is dict` and whose raw `name` field is an exact contained identity. It reads no nested `arguments` field. Any other call-tool request is an acceptance-harness error and never reaches the installed handler.

For every accepted request, the wrapper clears per-probe counters, takes `get_metrics_store().get_containment_denials_snapshot()` immediately before invoking the retained installed request handler, sets a private acceptance-only probe phase (`direct` or `progressive`) for exactly that await, takes the same accessor snapshot in `finally`, atomically writes the correlated probe record, and resets the phase. The phase is local to `containment_acceptance.py`; it is neither a production denial scope nor authorization/deduplication state. The wrapper never changes the installed result. This places the two telemetry snapshots around the real SDK/MCP request path in the same PID/interpreter without relying on a hidden profile tool or adding a new runtime endpoint.

The child owns one literal, immutable patchpoint table; these are the complete installed lookups, and no caller may replace or extend them:

```text
recording_attempt = rook.tool_lifecycle_runtime._record_containment_denial  [sync]
format_result     = rook.server._format_tool_result                         [sync]
argument_access   = rook.server.validate_arguments                          [sync]
argument_access   = mcp.server.lowlevel.server.Server._get_cached_tool_definition [async]
argument_access   = mcp.server.lowlevel.server.jsonschema.validate          [sync]
profile           = rook.server.tool_blocked                                [sync]
capability        = rook.server._get_capability_index                        [async]
knowledge         = rook.server.inject_knowledge                             [async]
model             = rook.agent.base_agent.RookAgent._call_model              [async]
target            = rook.server.targeting.policy_for_tool                    [sync]
http              = httpx.AsyncClient.get                                    [async]
http              = httpx.AsyncClient.post                                   [async]
http              = httpx.AsyncClient.request                                [async]
http              = rook.bootstrap.executor.urllib.request.urlopen           [sync]
host              = rook.server.call_rhino                                   [async]
observation       = rook.server._record_observation                           [sync]
adaptation        = rook.server.get_phase_tracker                             [sync]
receipt           = rook.server.build_script_receipt                          [sync]
```

Resolve every owner and attribute after the installed-origin checks and require its pinned sync/async kind. Preserve descriptors when replacing class attributes. With no probe phase, every wrapper calls its original and records nothing. In a direct/progressive phase, `recording_attempt` and `format_result` count and call through. Every other wrapper, including `profile`, counts and raises private `InstalledSpyTripped(stage)` before its original. Both direct and progressive probes require `profile=0`; any profile invocation proves the exact tombstone was not resolved before profile eligibility. `capability=0` additionally proves progressive denial occurred inside `_handle_meta_tool` before capability-index construction.

Each wrapper also recognizes one module-private object-identity trip sentinel before normal signature handling. Before opening stdio, the child (1) tests the wrapper factory with code-owned pure sync and async originals, proving unscoped pass-through returns the exact marker with zero count and scoped invocation trips, then (2) invokes every installed wrapper with only the trip sentinel in a scoped self-test (awaiting async wrappers), requires the matching `InstalledSpyTripped`, and proves exactly that patchpoint's declared stage changed. Reset all live counters afterward. Missing targets, duplicate patchpoint identifiers, kind drift, a wrong-stage trip, unscoped count, or any failed self-test aborts child startup. Unit tests delete/replace each target one at a time and require refusal, exercise both generic sync/async pass-through branches, and prove each installed wrapper's scoped sentinel reports the correct stage. No self-test calls a real model, network, target, host, observation, or receipt body.

The child's only side channel is an atomically replaced canonical `spy-path` JSON record with exact keys `schema_version`, `run_id`, `process_id`, `process_start_token`, `self_test`, and `probe`. `self_test` contains exactly `patchpoints` (the fully qualified identifiers above, including distinct `.get`, `.post`, `.request`, and `rook.bootstrap.executor.urllib.request.urlopen` keys, all `true`) and `wrapper_factory` (exact booleans `sync_scoped_trip`, `sync_unscoped_passthrough`, `async_scoped_trip`, and `async_unscoped_passthrough`, all `true`). `probe` contains exactly `index`, `adapter`, `tool`, `origin`, `telemetry_before`, `telemetry_after`, and `stages`. `stages` has the fixed keyspace `recording_attempt`, `format_result`, `argument_access`, `profile`, `capability`, `knowledge`, `model`, `target`, `http`, `host`, `observation`, `adaptation`, and `receipt`; values are nonnegative integers. Direct and progressive probes both require recording/format `1`, profile `0`, and every other stage `0`. The synchronous `urllib.request.urlopen` patchpoint contributes only to the existing `http` counter, so the 36/164 probe counts and stage schema do not change. Each adjacent accessor pair must keep PID/start token stable and show exactly one matching appended event, including the permitted head eviction at ring capacity. The record never contains tool arguments, prompts, content, user identifiers, document data, or stack traces.

After each MCP result, the parent reads the corresponding atomically completed sidecar, requires the exact next probe index/adapter/canonical tool/origin/result, and copies that record into the ordered profile evidence. A missing record, PID/token/run mismatch, unexpected key, failed self-test, wrong stage count, or ring drift fails. The final spy artifact and SHA-256 are copied into the profile evidence after child shutdown. This is an acceptance-only CLI branch, not a model-visible tool, environment hook, exported runtime flag, or normal server entrypoint.

Build and inspect installed RookAgent and RookChat final model-visible projections as additional omission evidence while preserving their independent consumer exclusions.

- [ ] **Step 4: Implement the exact installed internal matrix**

Run under installed Python with the same cwd/environment/origin assertions. Import only installed modules, arm the per-probe fail-fast policy above, and invoke every exact pair in the 164-probe set. Take `get_metrics_store().get_containment_denials_snapshot()` immediately before and after each probe. The two model-loop seams use only their exact two-call code-owned primary-model stubs; every extra call and every dormant/downstream model path remains fail-fast, while all other seams allow no model call at all. Proof-only delegates such as `local_testing_proof._call_tool_dispatch` are documented as delegates and are not counted as separate seams.

- [ ] **Step 5: Run Task 7 unit tests and commit**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_containment_acceptance.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_agent_protocols.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 7 tests failed with exit code $LASTEXITCODE" }
git add mcp_server/src/rook/containment_acceptance.py `
  mcp_server/tests/test_containment_acceptance.py
if ($LASTEXITCODE -ne 0) { throw "Task 7 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask7 = @(
  'mcp_server/src/rook/containment_acceptance.py',
  'mcp_server/tests/test_containment_acceptance.py'
) | Sort-Object
$ActualTask7 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 7 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task7Delta = @(Compare-Object $ExpectedTask7 ($ActualTask7 | Sort-Object))
if ($Task7Delta.Count -ne 0) { throw "Task 7 staged-file set mismatch: $($Task7Delta | Out-String)" }
git commit -m "test(containment): add installed denial certification"
if ($LASTEXITCODE -ne 0) { throw "Task 7 commit failed with exit code $LASTEXITCODE" }
```

Expected: unit/contract tests PASS without installing a candidate or launching Rhino. The actual installed commands run only in Task 10.

- [ ] **Step 6: Run the Task 7 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 8 until both are clear.

---

### Task 8: Add the two authorized live-preservation scenarios

**Task environment (run first in a fresh shell):**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
```

**Files:**
- Create: `mcp_server/src/rook/containment_live_gate.py`
- Create: `mcp_server/src/rook/resources/containment_empty.ghx`
- Create: `mcp_server/tests/test_containment_live_gate.py`

**Installed CLI and callable produced:**

```text
<installed-python.exe> -m rook.containment_live_gate run --scenario rhino --rhino-exe <absolute-path> --artifact-dir <new-empty-dir>
<installed-python.exe> -m rook.containment_live_gate run --scenario grasshopper --rhino-exe <absolute-path> --artifact-dir <new-empty-dir>
```

```python
def run_live_scenario(
    *,
    scenario: Literal["rhino", "grasshopper"],
    rhino_exe: Path,
    artifact_dir: Path,
) -> LiveScenarioResult: ...

def main(argv: Sequence[str] | None = None) -> int: ...
```

`<installed-python.exe>` is the exact executable from the candidate's installed runtime manifest and must pass the same source-free origin checks as Task 7. There is no `--yes`, injectable authorization reader, authorization argument/environment variable, cached authorization, or autoapproval path. The production callable reads one line from `sys.stdin` through a narrow private `_read_authorization_line()` seam; tests patch only that private seam or exercise a subprocess, so no installed caller can supply a callback that returns `required_response`. `main` delegates once to `run_live_scenario`; unit tests patch only private stdin and the concrete launch/discovery/adapter factories, not a generic executor framework. Before runtime import or host launch, reject a missing-parent, symlink/reparse, already-owned, or nonempty artifact path with bounded stderr and exit `2`, making no filesystem or host change. Otherwise atomically claim the empty directory with a run-ownership marker; only post-claim execution emits the JSONL/artifact contract below. Stdout then contains only the flushed canonical JSONL authorization challenge and final result record; diagnostics go to stderr and retained files. Exit `0` means the scenario passed with verified restoration and zero telemetry delta; `2` means blocked before forward mutation; `3` means failed or restoration unverified.

After artifact ownership and installed-origin validation, obtain and persist `get_metrics_store().get_containment_denials_snapshot()` as the process-local baseline **before** `rhino_launch`, adapter construction, `rhino_ping`, either runtime-serial probe, `rhino_document`, `gh_status`, `gh_library`, `_Grasshopper`, or any other supported tool/target/host call. The baseline PID/start token must equal the installed gate process for the entire scenario. Take the final snapshot through that same accessor only after verified restoration, scratch disposal, owned-process shutdown, and discovery removal, but before writing final evidence. Any accessor replacement/restart, nonzero ring delta, or event added after that baseline fails. Unit tests must make the first launch/adapter/call fake assert that the baseline already exists, accept an event seeded before the baseline, reject the same event seeded after it, and reject process-token drift. This ordering ensures the zero-delta claim covers the complete supported workflow rather than only its mutation tail.

**Authorization protocol:** After launching/binding the owned process and completing read-only preflight, emit and flush exactly one canonical JSONL `authorization_required` record containing `schema_version`, `scenario`, `run_id`, a fresh `nonce`, the named scratch target, exact code-owned mutation/verification/restoration descriptions, their SHA-256 tokens, and `required_response`. The required response is exactly `AUTHORIZE scenario=<scenario> run=<run_id> nonce=<nonce> target=<target-sha256> mutation=<mutation-sha256> verify=<verification-sha256> restore=<restoration-sha256>`. Read exactly one line from stdin and require byte-for-byte equality after removing only the protocol line terminator; do not otherwise trim, case-fold, retry, or retain the operator input. EOF or mismatch blocks with no document/GH mutation. After a match, repeat the read-only target/state projection and require its hash unchanged immediately before the first mutation. Target/state drift invalidates the authorization. Task 10 must display this record, obtain the response interactively for that scenario, and relay the one response to the child; it may not synthesize, cache, or carry it across a target or rerun.

Pin the two JSONL record schemas exactly; unknown or missing keys, wrong types, noncanonical JSON, or mismatched scenario/run/hash values fail closed:

```json
{
  "type": "authorization_required",
  "schema_version": 1,
  "scenario": "rhino|grasshopper",
  "run_id": "<32 lowercase hex>",
  "nonce": "<32 lowercase hex>",
  "target": {"label": "<code-owned>", "process_id": 123, "port": 123, "scratch_path": "<absolute>"},
  "target_sha256": "<64 lowercase hex>",
  "mutation": "<code-owned description>",
  "mutation_sha256": "<64 lowercase hex>",
  "verification": "<code-owned description>",
  "verification_sha256": "<64 lowercase hex>",
  "restoration": "<code-owned description>",
  "restoration_sha256": "<64 lowercase hex>",
  "required_response": "<exact response defined above>"
}
```

```json
{
  "type": "scenario_result",
  "schema_version": 1,
  "scenario": "rhino|grasshopper",
  "run_id": "<same 32 lowercase hex>",
  "success": true,
  "failure_label": null,
  "evidence_path": "rhino-scenario.json|grasshopper-scenario.json",
  "evidence_sha256": "<64 lowercase hex>"
}
```

The shown `scenario_result` is the success variant. For a represented failure it has the identical key set with `success: false` and the matching non-null fixed-enum `failure_label`; `success` and `failure_label` must satisfy that inverse relationship.

**Bound adapter:** Implement only a concrete `BoundInstalledToolAdapter(port: int, process_id: int)` with `async call(name: str, arguments: Mapping[str, Any]) -> dict[str, Any]`. It wraps installed `server._call_tool_dispatch` in `bridge.rhino_request_context(port=..., process_id=...)`, passes only code-owned arguments plus the explicit port, rechecks the owned discovery PID/port before and after every call, and returns the internal `{success, data}` envelope unchanged. Reject names outside these fixed allowlists:

- Rhino: `rhino_ping`, `rhino_document`, `rhino_objects`, `rhino_geometry`, `rhino_document_ops`, `rhino_create`, `rhino_execute`, `rhino_delete`.
- Grasshopper: `rhino_ping`, `rhino_document`, `rhino_command`, `gh_status`, `gh_document_open`, `gh_library`, `gh_snapshot`, `gh_edit`, `gh_errors`, `gh_undo`.

Do not use `gh_solve`: it has no public tool schema, and `gh_edit` schedules the solve. Verify settling with bounded read-only `gh_snapshot`/`gh_errors` polling.

**Result/evidence contract:** After artifact-directory ownership is established, each run atomically writes one final evidence pair, `<scenario>-scenario.json` plus `<scenario>-scenario.sha256`, then prints one final canonical JSONL `scenario_result` record. The directory may additionally contain its ownership marker, canonical per-operation evidence, scratch artifacts, and diagnostic files only when each is enumerated in the final evidence. JSON is UTF-8 with sorted keys and fixed compact separators; the sidecar is one lowercase SHA-256 hex digest of the exact file bytes plus one final LF. `LiveScenarioResult` has exactly these top-level fields: `schema_version`, `scenario`, `success`, `failure_label`, `run_id`, `started_at`, `ended_at`, `runtime`, `target`, `authorization`, `pre_state`, `operations`, `verification`, `restoration`, `telemetry`, `artifacts`, and `diagnostics`. Pin `schema_version=1`, `scenario` to the two-value enum, UTC timestamps ending in `Z`, and `failure_label` to `null` on success or one of `runtime_origin_invalid`, `launch_failed`, `readiness_failed`, `fixture_invalid`, `preflight_blocked`, `authorization_rejected`, `state_drift`, `mutation_failed`, `verification_failed`, `ownership_ambiguous`, `restoration_failed`, `telemetry_changed`, or `cleanup_failed`. If the final evidence pair itself cannot be atomically persisted, emit only bounded stderr, remove any partial final pair, exit `3`, and let Task 10 retain its parent diagnostics; no `scenario_result` is fabricated.

- `runtime`: installed executable/root, cwd, full `sys.path`, and all loaded `rook.*` origins; source/worktree origins fail.
- `target`: owned PID/port/process-start token, discovery-record hash, scratch path, and ownership evidence.
- `authorization`: nonce, challenge hash, authorization time, preflight hash, immediate-pre-mutation hash, and equality result; never operator input.
- `operations`: ordered admitted tool names plus canonical per-operation argument/result artifact paths, hashes, and normalized success; no prompts or user content. Before each adapter call, atomically persist its exact code-owned arguments as `operations/<index-3-digits>-<tool>-arguments.json`; immediately after return, persist the unchanged internal envelope as the paired `-result.json`. Both use the final canonical JSON encoding. Enumerate both files in `artifacts`, and set the operation hashes to the exact file-byte digests so Task 10 can recompute rather than trust them. A write failure stops further forward mutation; when ownership remains certain, only the already-authorized restoration path may continue, and the scenario cannot pass.
- `telemetry`: accessor PID/start token, adjacent before/after snapshots, and exact zero delta.
- `restoration`: ownership certainty, attempted/verified flags, equality to the declared in-process scratch projection, prior global identity/absence restoration, scratch disposal, and discovery removal.

The nested mappings are also fixed, with no additional keys:

- `runtime`: `python_executable: string`, `installed_root: string`, `cwd: string`, `sys_path: array[string]`, `rook_origins: object[string,string]`.
- `target`: `null` until a process is successfully bound; otherwise exactly `process_id: integer`, `port: integer`, `process_start_token: string`, `discovery_record_sha256: string`, `scratch_path: string`, `ownership_certain: boolean`.
- `authorization`: `null` until a challenge is constructed; otherwise exactly `nonce: string`, `challenge_sha256: string`, `authorized_at: string|null`, `preflight_sha256: string`, `pre_mutation_sha256: string|null`, `state_unchanged: boolean`.
- `pre_state`: `null` until an observable projection exists; otherwise exactly `host_projection: object`, `host_sha256: string`, `scratch_projection: object|null`, `scratch_sha256: string|null`. Rhino's host projection contains only `prior_active_document_runtime_serial`, `prior_path`, and `prior_modified`; its scratch projection contains only `runtime_serial`, `path`, `modified`, `object_count`, and `object_ids`. The runtime serial is obtained with the fixed read-only `rhino_execute` probe below, not inferred from `/document`. Grasshopper's host projection contains only `has_active_canvas: false` and `document_id: null`; its opened scratch projection contains only `document_id`, `has_active_canvas: true`, `gate_canvas_token`, `path`, `object_count`, `component_ids`, `wires`, `errors`, and `warnings`. `gate_canvas_token` is the SHA-256 of the code-owned canonical tuple `(owned process_id, process_start_token, port, true, document_id)`, not a claimed host canvas ID.
- Every `operations` item: `index: integer`, `name: string`, `arguments_path: string`, `arguments_sha256: string`, `result_path: string`, `result_sha256: string`, `success: boolean`. Paths are the deterministic relative names above, remain beneath the owned artifact directory, and correspond one-to-one to `artifacts` entries.
- `verification`: `passed: boolean`, `projection: object|null`, `projection_sha256: string|null`, `errors: array`, `warnings: array`.
- `restoration`: `ownership_certain: boolean`, `attempted: boolean`, `verified: boolean`, `in_process_projection_matches_declared: boolean`, `prior_identity_or_absence_restored: boolean`, `scratch_disposed: boolean`, `discovery_removed: boolean`.
- `telemetry`: `null` until the accessor/baseline is obtained; otherwise exactly `process_id: integer`, `process_start_token: string`, `before_sha256: string`, `after_sha256: string|null`, `delta_count: integer|null`, `events_added: array|null`.
- Every `artifacts` item: `kind: string`, `relative_path: string`, `sha256: string`, `size: integer`; every `diagnostics` item: `stage: string`, `label: string`, `relative_path: string`, `sha256: string`.

Every post-claim failure other than the explicitly unrepresentable final-evidence-write failure writes scenario diagnostic evidence and its sidecar, but can never be consumed as successful acceptance. Nulls follow the execution state machine and may never be replaced with fabricated evidence: `runtime_origin_invalid` has null target/authorization/pre-state/telemetry; `launch_failed` has null target/authorization/pre-state; `readiness_failed` may have a bound target but null authorization/pre-state; preflight and authorization failures have no operation entries; success requires non-null target, authorization, pre-state, telemetry, final verification, and restoration. Tests pin each early-failure invariant. Task 10 must parse both scenario files and sidecars, load every operation artifact, require canonical bytes/path containment/artifact enumeration, recompute both operation hashes, and independently reassert origins, sets, operation order, exact code-owned inputs, result/verification consistency, restoration, and zero event delta rather than trust exit status.

- [ ] **Step 1: Write failing fixture, authorization, mutation, and restoration tests**

Tests use fake owned-process/discovery/tool adapters and prove:

- Rhino and Grasshopper use separate newly launched Rhino processes and PID/port locks; no ambient open Rhino can be selected.
- Grasshopper preflight requires verified absence of the Grasshopper assembly/canvas/definition in its fresh owned process; an unexpected ambient identity blocks rather than being reused or requiring new reopen/reselection authority. After authorization, only the fixed preflighted `_Grasshopper` command may bootstrap the gate-owned canvas.
- Read-only preflight precedes the challenge. The one eligible unsaved state is the newly launched, gate-owned Untitled Rhino document with zero objects, `modified=false`, and a stable positive runtime serial; it becomes the named scratch document only after authorization. Any other unsaved/ambient, dirty, unknown, non-restorable, or drifting state blocks before mutation.
- Each scenario has a fresh nonce and exact authorization phrase naming target, bounded mutation, verification, and restoration. Authorization cannot cross targets or reruns.
- Every host call after binding—including pre-state, mutation, solve/error checks, undo, and restoration—uses the bound installed explicit-tool adapter; no contained identity or dormant body is referenced.
- Forward failure stops new mutation. Certain ownership enters only the already-authorized restoration path; ambiguous ownership performs no mutation. Cleanup attempted is never PASS.
- Rhino restoration proves object deletion alone leaves the scratch document dirty, performs the authorized final save, then requires `modified=false` and graceful close without a save prompt; a force-kill cannot turn that scenario green.
- Rhino preflight and restoration parse exactly one `ROOK_DOC_RUNTIME_SERIAL=<positive integer>` line from fixed read-only `rhino_execute` code; malformed/multiple output blocks before mutation or fails restoration.
- Every participating Python process has an adjacent before/after containment-ring snapshot with stable PID/start token and zero event delta; the first launch/adapter/tool fake asserts the baseline already exists, and before-baseline versus after-baseline seeded-event cases pin the boundary.
- The Rhino sphere arguments, complete point script/coordinates/name, Grasshopper library query, fixed Sphere GUID `dabc854d-f50e-408a-b001-d043c7de151d`, and resulting canonical operation hashes match the literals in Steps 4–5 with no alternate fixture inputs.
- The exact fixture bytes, length, SHA-256, XML counts, package-resource lookup, and live-open empty-state validation are mandatory.
- CLI/parser, pre-ownership invalid/nonempty/reparse rejection with zero writes, single-line challenge/response, EOF/wrong-response/drift blocking, absence of an injectable authorization callback, adapter binding/allowlist/envelope preservation, exact result schema/canonical sidecar, deterministic per-operation argument/result artifacts, missing/tampered/noncanonical/path-escaping artifact rejection, installed-origin rejection, and Task 10's fake-consumer parsing are all covered.

- [ ] **Step 2: Run the new tests and confirm they fail**

```powershell
$RedJunit = Join-Path $env:TEMP 'rook-containment-t8-live.xml'
if (Test-Path -LiteralPath $RedJunit) { Remove-Item -LiteralPath $RedJunit -Force }
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& $Python -m pytest mcp_server/tests/test_containment_live_gate.py --junitxml $RedJunit -q 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T8:LIVE_GATE' -JunitPath $RedJunit
```

Expected: FAIL because the live-gate module and fixture do not exist.

- [ ] **Step 3: Create the exact approved empty GHX fixture**

Create `containment_empty.ghx` as UTF-8 **without BOM**, LF line endings, and one final LF. It must be exactly 2,708 bytes with SHA-256 `2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df`. The complete bytes are this ASCII text:

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<Archive name="Root">
  <items count="1">
    <item name="ArchiveVersion" type_name="gh_version" type_code="80">
      <Major>0</Major><Minor>2</Minor><Revision>2</Revision>
    </item>
  </items>
  <chunks count="2">
    <chunk name="Definition">
      <items count="1">
        <item name="plugin_version" type_name="gh_version" type_code="80">
          <Major>1</Major><Minor>0</Minor><Revision>7</Revision>
        </item>
      </items>
      <chunks count="5">
        <chunk name="DocumentHeader">
          <items count="5">
            <item name="DocumentID" type_name="gh_guid" type_code="9">4d918037-395b-4c62-92d7-155f8f301501</item>
            <item name="Preview" type_name="gh_string" type_code="10">Shaded</item>
            <item name="PreviewMeshType" type_name="gh_int32" type_code="3">2</item>
            <item name="PreviewNormal" type_name="gh_drawing_color" type_code="36"><ARGB>100;150;0;0</ARGB></item>
            <item name="PreviewSelected" type_name="gh_drawing_color" type_code="36"><ARGB>100;0;150;0</ARGB></item>
          </items>
        </chunk>
        <chunk name="DefinitionProperties">
          <items count="3">
            <item name="Date" type_name="gh_date" type_code="8">638881344000000000</item>
            <item name="Description" type_name="gh_string" type_code="10">Rook containment live-gate empty fixture</item>
            <item name="Name" type_name="gh_string" type_code="10">Rook Containment Empty</item>
          </items>
          <chunks count="3">
            <chunk name="Revisions"><items count="1"><item name="RevisionCount" type_name="gh_int32" type_code="3">0</item></items></chunk>
            <chunk name="Projection"><items count="2"><item name="Target" type_name="gh_drawing_point" type_code="30"><X>0</X><Y>0</Y></item><item name="Zoom" type_name="gh_single" type_code="5">1</item></items></chunk>
            <chunk name="Views"><items count="1"><item name="ViewCount" type_name="gh_int32" type_code="3">0</item></items></chunk>
          </chunks>
        </chunk>
        <chunk name="RcpLayout"><items count="1"><item name="GroupCount" type_name="gh_int32" type_code="3">0</item></items></chunk>
        <chunk name="GHALibraries"><items count="1"><item name="Count" type_name="gh_int32" type_code="3">0</item></items></chunk>
        <chunk name="DefinitionObjects"><items count="1"><item name="ObjectCount" type_name="gh_int32" type_code="3">0</item></items><chunks count="0"></chunks></chunk>
      </chunks>
    </chunk>
    <chunk name="Thumbnail"><items count="1"><item name="Width" type_name="gh_int32" type_code="3">0</item></items></chunk>
  </chunks>
</Archive>
```

The static XML check is not enough. During the authorized GH scenario, copy these exact packaged bytes to a unique `RookContainmentGH-<run-id>.ghx`, open that path with `gh_document_open`, then require `objectCount=0`, a new expected document identity, an empty `gh_snapshot` (components/flows/topology), and empty `gh_errors` before the Sphere/Slider mutation is eligible. A hash/open/state mismatch fails and enters restoration.

- [ ] **Step 4: Implement the Rhino scenario**

Shallowly compose existing `rhino_launch.build_launch_env`, `rhino_launch.start_rhino_process`, `rhino_launch.OwnedRhinoDiscovery`, and `rhino_launch.wait_for_rook_readiness` in the same installed CLI process; do not put the interactive gate inside a runtime-harness smoke callback. Bind all tool calls to the resulting PID/port/discovery record. Cleanup uses `runtime_harness.request_external_graceful_close`, with `force_owned_process_cleanup` only if that certainly owned process remains. The read-only preflight calls admitted `rhino_execute` with exactly `import Rhino\nprint('ROOK_DOC_RUNTIME_SERIAL={0}'.format(Rhino.RhinoDoc.ActiveDoc.RuntimeSerialNumber))`, parses the one positive integer, and combines it with admitted `rhino_document` state to record the process's fresh active-document identity. Require the declared object/document projection to be empty and restorable. Present the one-time challenge only then.

After authorization, name the fresh process-owned document by saving it to unique `RookContainmentRhino-<run-id>.3dm`; this is the first host mutation and must preserve the same runtime serial. Record the resulting declared in-process scratch projection: that serial, the expected scratch path, zero objects, and `modified=false`. This is distinct from the pre-authorization Untitled host projection whose path was empty.

The typed mutation is exactly `rhino_create` with canonical arguments `{"type":"SPHERE","center":[0,0,0],"radius":4,"name":"RookContainmentSphere-<run-id>"}`. The sanctioned-script mutation is exactly `rhino_execute` with the sole `code` value below, substituting only the already validated 32-lowercase-hex run ID in the code-owned name:

```python
import Rhino
import scriptcontext as sc
point = Rhino.Geometry.Point3d(10.0, 0.0, 0.0)
attributes = Rhino.DocObjects.ObjectAttributes()
attributes.Name = "RookContainmentPoint-<run-id>"
object_id = sc.doc.Objects.AddPoint(point, attributes)
sc.doc.Views.Redraw()
print("ROOK_POINT_ID={0}".format(object_id))
```

No other code, coordinates, or creation arguments are permitted. Compute each operation's argument hash from canonical UTF-8 JSON containing those exact runtime-expanded arguments. Require exactly one valid sphere GUID and exactly one `ROOK_POINT_ID=<guid>` line, then verify exact IDs/names/types, sphere center `[0,0,0]`, radius `4`, bounding box `[-4,-4,-4]` to `[4,4,4]`, point `[10,0,0]`, document count `2`, and script result. Delete only those IDs, then use admitted `rhino_document_ops` with the fixed `save` action and the same scratch path to complete restoration. Repeat the fixed runtime-serial probe and require the original runtime serial, expected scratch path, zero objects, empty ID set, successful save, and `modified=false`; verify the saved scratch file exists and the host's saved projection is empty. Only that in-process scratch projection must compare equal. Then close gracefully without a save prompt, require process/discovery removal, delete the scratch file, and verify the gate's prior global process/file absence. A forced cleanup is diagnostic failure, not successful restoration. This exercises both typed and sanctioned script substrates without the retired identity.

- [ ] **Step 5: Implement the Grasshopper scenario**

Launch a separate owned Rhino process and use read-only status to require verified absence of the Grasshopper assembly/canvas/definition; if an ambient identity exists, block before authorization. Copy and hash the packaged fixture before authorization. The authorization text must cover bootstrapping the gate-owned canvas, opening the named scratch definition, the bounded edit/verification, the undo loop, and disposal. As the first host mutation after authorization, call admitted `rhino_command` with exactly `{"command":"_Grasshopper","echo":false}` through its existing preflight. Poll admitted read-only `gh_status` with a fixed timeout until the newly gate-created canvas is ready, then open the fixture with `gh_document_open` and perform the live validation from Step 3. Never call `gh_document_new`, reuse an ambient canvas, or perform a GH mutation before authorization.

Call admitted `gh_library` with exactly `{"search":"Sphere","exact":true}` and require exactly one eligible built-in result whose canonical component GUID is `dabc854d-f50e-408a-b001-d043c7de151d`; zero, multiple, or any other GUID fails before `gh_edit`. Take an empty `gh_snapshot` and use its epoch in one `gh_edit` batch that creates exactly:

- `T1`: Number Slider, nickname `RookContainmentRadius-<run-id>`, min `1`, max `9`, value `4`, position `[100,100]`;
- `T2`: GUID `dabc854d-f50e-408a-b001-d043c7de151d` at `[400,100]`; and
- wire `T1.O0>T2.I1`.

Require exactly those two components, exact slider settings/value, exactly that wire/topology, a fresh solve, Sphere output corresponding to radius 4, no GH errors or warnings, and no unrelated components. Restore with a bounded authorized `gh_undo` loop: at most four undo calls, stopping as soon as the exact declared empty projection is observed. Record every undo and require the exact empty component/settings/wire/topology/error projection before process cleanup; do not assume one `gh_edit` batch produces one host undo record. Close the owned process to dispose the scratch canvas and restore the prior verified absence, require discovery removal, delete the copied GHX, and verify absence.

- [ ] **Step 6: Run Task 8 tests and commit**

```powershell
& $Python -m pytest `
  mcp_server/tests/test_containment_live_gate.py `
  mcp_server/tests/test_runtime_harness.py `
  mcp_server/tests/test_local_testing_proof.py -q
if ($LASTEXITCODE -ne 0) { throw "Task 8 tests failed with exit code $LASTEXITCODE" }
git add mcp_server/src/rook/containment_live_gate.py `
  mcp_server/src/rook/resources/containment_empty.ghx `
  mcp_server/tests/test_containment_live_gate.py
if ($LASTEXITCODE -ne 0) { throw "Task 8 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask8 = @(
  'mcp_server/src/rook/containment_live_gate.py',
  'mcp_server/src/rook/resources/containment_empty.ghx',
  'mcp_server/tests/test_containment_live_gate.py'
) | Sort-Object
$ActualTask8 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 8 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task8Delta = @(Compare-Object $ExpectedTask8 ($ActualTask8 | Sort-Object))
if ($Task8Delta.Count -ne 0) { throw "Task 8 staged-file set mismatch: $($Task8Delta | Out-String)" }
git commit -m "test(containment): add authorized live preservation"
if ($LASTEXITCODE -ne 0) { throw "Task 8 commit failed with exit code $LASTEXITCODE" }
```

Expected: unit/fake-host tests PASS without launching Rhino. Actual authorized mutation runs only in Task 10.

- [ ] **Step 7: Run the Task 8 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 9 until both are clear.

---

### Task 9: Build an immutable, standalone containment candidate

**Files:**

- Create: `scripts/build-containment-candidate.ps1`
- Create: `scripts/tests/build-containment-candidate-guards.tests.ps1`

This task does not edit `installer/RookSetup.iss`, the normal release validator, either build-release skill, or any release-manifest schema. It produces a non-publishable candidate for Task 10 only.

- [ ] **Step 1: Re-establish the task environment**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
$Task9Branch = git branch --show-current
if ($LASTEXITCODE -ne 0) { throw "Task 9 branch check failed with exit code $LASTEXITCODE" }
if ($Task9Branch -ne 'codex/gh-execute-intent-root-fix') { throw "unexpected Task 9 branch: $Task9Branch" }
$Task9Status = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw "Task 9 status check failed with exit code $LASTEXITCODE" }
if ($Task9Status.Count -ne 0) { throw "Task 9 worktree is not clean: $($Task9Status -join '; ')" }
```

Expected: branch `codex/gh-execute-intent-root-fix`; only prior reviewed task commits; clean worktree.

- [ ] **Step 2: Write the failing builder guards**

The builder and its guard script put `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'` in their first executable lines after `param(...)`. The guard injects a normally nonterminating cmdlet error and proves the next builder stage is never reached. It uses temporary local Git repositories and stub executables; it must not compile, download, install, launch Rhino, or modify the real worktree. It launches the fake builder with child `APPDATA` redirected to a temporary tree containing a sentinel plug-in directory, then proves the sentinel projection is unchanged. Pin tests for:

- exact Rook root, branch, reviewed SHA, and clean source checks;
- a separately supplied, clean Chirp root and exact Chirp SHA;
- local, detached staging clones at `<artifact>\stage\Rook` and `<artifact>\stage\Chirp` with no network fetch;
- rejection of dirty inputs, SHA drift, wrong branch/root, stale output, a missing/unrecorded external executable or root, or a source change during the build;
- required use and identity recording of explicit `GitPath`, `PowerShellPath`, `CmdPath`, `Msys2Bash`, `VcvarsallPath`, `MsbuildPath`, `DotnetPath`, `IsccPath`, `RhinoSystemDir`, `RevitInstallDir`, `VcRedistRoot`, `OcctRoot`, and `OcctRuntimeRoot` inputs, plus the registry-resolved native Rhino SDK/property-sheet input;
- canonical absolute `OcctRoot` validation for `inc\Standard.hxx` and exactly `TKernel.lib`, `TKMath.lib`, `TKG2d.lib`, `TKG3d.lib`, `TKGeomBase.lib`, `TKGeomAlgo.lib`, `TKBRep.lib`, `TKTopAlgo.lib`, `TKPrim.lib`, `TKBO.lib`, `TKBool.lib`, `TKShHealing.lib`, and `TKMesh.lib` under `win64\vc14\lib`; canonical `OcctRuntimeRoot` must equal `OcctRoot\win64\vc14\bin`, with every installer-consumed DLL present;
- poisoning ambient `OCCT_ROOT` with a decoy while proving the captured native command still contains exactly `/p:OcctRoot=<canonical-explicit-root>`; omitted/malformed roots, missing required inputs, root disagreement, or identity drift fail before MSBuild;
- a case-insensitive, fixed pre-`vcvarsall` native-authority scrub: seed every pinned compiler/linker/MSBuild name and a decoy `PATH`, place trip files at every path-bearing import override, and prove every seeded key is absent from the batch input, the path is the code-owned baseline, no trip file executes, the explicit MSBuild executable is used, and the captured command contains the pinned toolset, OCCT, and import-disable properties;
- exact subprocess arguments, including `validate-python-wheelhouse.ps1 -Version <reviewed-version>` and `validate-ffmpeg-bundle.ps1 -RepoRoot <staged-rook> -SourceBundleManifestPath <generated-manifest>`;
- byte-identical staged `installer/RookSetup.iss` versus `git show <rook-sha>:installer/RookSetup.iss`;
- use of only the existing `MyAppVersion`, `VcRedistRoot`, and `OcctRuntimeRoot` Inno defines;
- source/build/output inventories and SHA-256 digests in the candidate identity;
- candidate identity binding for `stage/Rook/installer/runtime/python/cpython-3.11.9/python.exe`: exact version, executable SHA-256, and a sorted `*._pth` projection that is empty for this full runtime; the existing payload inventory retains the remaining runtime-file hashes;
- both managed builds receive the same absolute, fresh, nonexistent `<artifact>\_no_rhino_deploy_<run-id>` through `-p:RhinoPluginDir=<path>`; both also receive the explicit `RhinoSystemDir`, and the RookBim build receives the explicit `RevitInstallDir`;
- the inert path is absent before and after both builds, and a relative-path/size/SHA-256 projection of the real `%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative` directory is byte-for-byte unchanged before versus after candidate construction;
- `non_publishable: true`; and
- no invocation of publishing, version mutation, normal release validation, or either build-release skill.

Run it immediately, before creating the builder:

```powershell
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    -NoProfile -ExecutionPolicy Bypass `
    -File scripts\tests\build-containment-candidate-guards.tests.ps1 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T9:BUILDER_MISSING'
```

Expected: FAIL because `scripts/build-containment-candidate.ps1` does not exist.

- [ ] **Step 3: Implement the standalone builder**

Give the script explicit parameters for `RookRoot`, `ExpectedBranch`, `ExpectedRookSha`, `ChirpRoot`, `ExpectedChirpSha`, `ArtifactDirectory`, `GitPath`, `PowerShellPath`, `CmdPath`, `Msys2Bash`, `VcvarsallPath`, `MsbuildPath`, `DotnetPath`, `RhinoSystemDir`, `RevitInstallDir`, `VcRedistRoot`, `OcctRoot`, `OcctRuntimeRoot`, and `IsccPath`. Resolve every path and reject missing, ambiguous, or overlapping roots. Resolve `OcctRoot` independently from the environment, validate its header/import-library projection above, require `OcctRuntimeRoot` to be its exact `win64\vc14\bin` child, and record canonical roots plus sorted relative-path/size/SHA-256 projections for the consumed header, import libraries, and runtime DLLs. Use only those executable paths for child processes and record each exact file version/hash in the identity. Use `PowerShellPath` for every subordinate `.ps1`; do not invoke an ambient shell. Record both original input-worktree HEADs/clean states before staging and recheck those same original inputs before writing the final identity; generated files inside the detached staging clones are inventoried build output, not input dirtiness.

Before any build, derive the real live plug-in directory from the builder's `%APPDATA%`, record whether it exists and a sorted relative-path/size/SHA-256 tree projection, and create only the parent—not the leaf—of a unique absolute inert `RhinoPluginDir` beneath the artifact directory. Require the inert leaf not to exist before either managed build and still not to exist afterward. Recompute the live directory projection after all build stages and fail if any existence, path, size, or hash changed.

Before `vcvarsall`, construct the private child environment from an empty map rather than mutating or forwarding the ambient map. Add exactly `SystemRoot`, `windir`, `TEMP`, `TMP`, `ComSpec`, `PATHEXT`, `PROCESSOR_ARCHITECTURE`, `ProgramFiles`, `ProgramFiles(x86)`, `ProgramData`, `SystemDrive`, `NUMBER_OF_PROCESSORS`, `OS`, and `PATH`—no user-profile, application-data, home, source, compiler, linker, or MSBuild variables. Derive `SystemRoot`/`windir` and `SystemDrive` from the canonical explicit `CmdPath`; set `ComSpec` to that same path; derive `ProgramFiles`, `ProgramFiles(x86)`, and `ProgramData` from the corresponding .NET known-folder APIs and require canonical absolute non-reparse directories; require a 64-bit Windows process, set `PROCESSOR_ARCHITECTURE=AMD64`, set `NUMBER_OF_PROCESSORS` from `[Environment]::ProcessorCount`, set `OS=Windows_NT`, and set `PATHEXT` to the code-owned `.COM;.EXE;.BAT;.CMD`. Create fresh artifact-owned non-reparse `TEMP`/`TMP` directories and set `PATH` to exactly `<validated-SystemRoot>\System32;<validated-SystemRoot>;<validated-SystemRoot>\System32\Wbem`. As a defense-in-depth final scrub, remove the following case-insensitive exact names from any intermediate dictionary and assert none is present before the batch starts:

```text
CL, _CL_, LINK, _LINK_, INCLUDE, LIB, LIBPATH,
VCTargetsPath, VCTargetsPath10, VCTargetsPath11, VCTargetsPath12,
VCTargetsPath14, VCTargetsPath15, VCTargetsPath16, VCTargetsPath17,
MSBUILD_EXE_PATH, MSBuildExtensionsPath, MSBuildExtensionsPath32,
MSBuildExtensionsPath64, MSBuildSDKsPath, MSBuildToolsPath,
MSBuildToolsPath32, MSBuildToolsPath64, MSBuildToolsRoot,
MSBuildUserExtensionsPath, MSBuildProjectExtensionsPath,
MSBUILDLEGACYEXTENSIONSPATH, DirectoryBuildPropsPath,
DirectoryBuildTargetsPath, AlternateCommonProps,
CustomBeforeMicrosoftCommonProps, CustomAfterMicrosoftCommonProps,
CustomBeforeMicrosoftCommonTargets, CustomAfterMicrosoftCommonTargets,
CustomBeforeDirectoryBuildProps, CustomAfterDirectoryBuildProps,
CustomBeforeDirectoryBuildTargets, CustomAfterDirectoryBuildTargets,
ForceImportAfterCppDefaultProps, ForceImportBeforeCppProps,
ForceImportAfterCppProps, ForceImportBeforeCppTargets,
ForceImportAfterCppTargets, BaseIntermediateOutputPath,
ProjectExtensionsPathForSpecifiedProject,
ProjectToOverrideProjectExtensionsPath, NuGetPropsFile,
NuGetRestoreTargets, AdditionalVCTargetsPath,
DisableInstalledVCTargetsUse, DisableInstalledVCTargetsDefaultsUse,
VcpkgInstalledVCTargets, VcpkgManifestDirectory, ImportBeforeCppProps,
ImportAfterCppProps, ImportBeforeCppTargets, ImportAfterCppTargets,
ImportDirectoryBuildProps, ImportDirectoryBuildTargets,
ImportProjectExtensionProps, ImportProjectExtensionTargets,
ImportUserLocationsByWildcardBeforeMicrosoftCommonProps,
ImportUserLocationsByWildcardAfterMicrosoftCommonProps,
ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets,
ImportUserLocationsByWildcardAfterMicrosoftCommonTargets
```

Here `*CL*` and `*LINK*` mean the documented option variables `CL`/`_CL_` and `LINK`/`_LINK_`; do not wildcard-delete unrelated variable names. Invoke the explicit `CmdPath` and `VcvarsallPath` with that map and require exit zero before parsing the resulting environment. In the captured map, `CL`, `_CL_`, `LINK`, `_LINK_`, and the direct file/import-hook names from `DirectoryBuildPropsPath` through `ImportUserLocationsByWildcardAfterMicrosoftCommonTargets` in the fixed list must remain absent or empty. `vcvarsall` may repopulate `INCLUDE`, `LIB`, `LIBPATH`, `PATH`, `VCTargetsPath*`, and the MSBuild tool/root names; accept those only when they contain no seeded sentinel and every path-bearing segment resolves beneath the explicit VS installation, the selected Windows SDK/UCRT roots, or the validated SystemRoot baseline. Require the captured `VCToolsInstallDir` to identify `14.44.35207`. Invoke only the explicit `MsbuildPath`, additionally passing exactly `/p:ImportDirectoryBuildProps=false`, `/p:ImportDirectoryBuildTargets=false`, `/p:ImportProjectExtensionProps=false`, `/p:ImportProjectExtensionTargets=false`, `/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonProps=false`, `/p:ImportUserLocationsByWildcardAfterMicrosoftCommonProps=false`, `/p:ImportUserLocationsByWildcardBeforeMicrosoftCommonTargets=false`, and `/p:ImportUserLocationsByWildcardAfterMicrosoftCommonTargets=false`. The guard test seeds every fixed name, poisons inherited `INCLUDE`/`LIB`/`LIBPATH`/`PATH`, and proves the fake compiler, linker, MSBuild, and import trip files are never reached. This is a Task 9-local build-environment contract, not a general process framework.

Materialize committed sources as clean, detached local clones at the exact SHAs under the stage layout; do not copy the working trees and do not fetch. Read the candidate version from staged `mcp_server/pyproject.toml` and require exact agreement with the staged `installer/RookSetup.iss`, `src/Rook/Rook.csproj`, and `src/RookBim/RookBim.csproj`; do not change any of them. The sibling layout intentionally satisfies the tracked installer's existing `RepoRoot` and `ChirpDir` definitions. Build only inside those clones:

1. stage the private Python runtime with `scripts/python-runtime/stage-rook-python-runtime.ps1 -RepoRoot <staged-rook>`;
2. build the wheelhouse with `scripts/python-runtime/build-rook-python-wheelhouse.ps1 -Version <version> -RepoRoot <staged-rook> -ChirpRoot <staged-chirp>`;
3. validate it with `scripts/validate-python-wheelhouse.ps1 -Version <version> -RepoRoot <staged-rook>` and require that the built Rook wheel contains `rook/resources/containment_empty.ghx` as exactly 2,708 UTF-8 bytes, no BOM, LF endings with one final LF, and SHA-256 `2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df`;
4. build/install the bundled FFmpeg payload with `scripts/ffmpeg/build-rook-ffmpeg.ps1 -RepoRoot <staged-rook> -Msys2Bash <Msys2Bash> -InstallPayload`. Read the FFmpeg version from staged `scripts/ffmpeg/rook-ffmpeg-source.json`, require the generated manifest at `<staged-rook>\artifacts\ffmpeg\ffmpeg-<ffmpeg-version>-rook-minimal\rook-ffmpeg-source-bundle-manifest.json`, then call `scripts/validate-ffmpeg-bundle.ps1 -RepoRoot <staged-rook> -SourceBundleManifestPath <that-exact-path>`;
5. use the scrubbed private environment plus explicit `CmdPath` and `VcvarsallPath` to create the VS 2022 environment with `x64 -vcvars_ver=14.44`, then invoke the explicit `MsbuildPath` on `src/RookNative/RookNative.vcxproj` in Release/x64 with `/p:VCToolsVersion=14.44.35207`, `/p:OcctRoot=<canonical-explicit-root>`, and the eight pinned import-disable properties above, with no inherited compiler, linker, MSBuild-import, or ambient `OCCT_ROOT` authority;
6. use the explicit `DotnetPath` to build `src/Rook/Rook.csproj -c Release -p:RhinoPluginDir=<inert> -p:RhinoSystemDir=<explicit>`, then `src/RookBim/RookBim.csproj -c Release -p:RhinoPluginDir=<same-inert> -p:RhinoSystemDir=<explicit> -p:RevitInstallDir=<explicit>`, preserving that order; and
7. invoke `ISCC.exe` on the byte-identical staged `installer/RookSetup.iss`, supplying only `/DMyAppVersion`, `/DVcRedistRoot`, and `/DOcctRuntimeRoot`.

Every subprocess exit code is checked immediately, bounded, and logged under the artifact directory before the next stage starts. The builder may use existing build scripts but may not edit source, versions, or the tracked installer. It must fail if a required installer source is absent, if any input SHA changes, if the inert plug-in leaf is created, or if the live plug-in projection changes.

- [ ] **Step 4: Freeze the candidate identity contract**

Write `containment-candidate.json` only after all builds succeed. It contains:

- schema version and `non_publishable: true`;
- Rook branch, exact SHA, clean-state proof, local source-clone path, and source-tree/archive digest;
- Chirp exact SHA, clean-state proof, local source-clone path, and source-tree/archive digest;
- product version read from the reviewed source;
- build start/end UTC timestamps;
- exact MSVC, native Rhino SDK/property sheet, .NET, Rhino managed-reference, Revit-reference, Python-runtime, FFmpeg, Inno, VC-redist, canonical OCCT build/runtime roots, exact MSBuild `OcctRoot` property, and consumed OCCT header/import-library/runtime-DLL projections with file digests;
- `private_python: {relative_path, version, sha256, pth_files}` for the exact staged `cpython-3.11.9` executable, with `pth_files` pinned to an empty sorted array;
- native-environment contract version, sorted fixed input-allowlist and scrub-name sets, validated minimal pre-`vcvarsall` environment projection, captured toolchain/import-root projection, and exact MSBuild import-disable arguments, recording no hostile values;
- the exact inert `RhinoPluginDir` argument used on both managed commands and the unchanged before/after live-directory projection hash;
- staged installer source hash and byte-identical staged hash;
- `installer: {relative_path, sha256}` for the built installer;
- a sorted relative-path/SHA-256/size inventory of the staged payload and retained logs; and
- no self-digest field: the exact canonical JSON bytes are hashed only after serialization and the digest is written alongside as `containment-candidate.sha256`.

Canonical JSON uses UTF-8, sorted object keys, stable array ordering, and fixed separators. The sidecar hashes the exact bytes on disk. Re-running into a nonempty artifact directory fails; the script never overwrites a prior candidate.

- [ ] **Step 5: Run Task 9 tests and commit**

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\build-containment-candidate-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw "Task 9 guard tests failed with exit code $LASTEXITCODE" }
git add scripts/build-containment-candidate.ps1 `
  scripts/tests/build-containment-candidate-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw "Task 9 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask9 = @(
  'scripts/build-containment-candidate.ps1',
  'scripts/tests/build-containment-candidate-guards.tests.ps1'
) | Sort-Object
$ActualTask9 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 9 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task9Delta = @(Compare-Object $ExpectedTask9 ($ActualTask9 | Sort-Object))
if ($Task9Delta.Count -ne 0) { throw "Task 9 staged-file set mismatch: $($Task9Delta | Out-String)" }
git commit -m "build(containment): add standalone candidate builder"
if ($LASTEXITCODE -ne 0) { throw "Task 9 commit failed with exit code $LASTEXITCODE" }
```

Expected: guard tests PASS using only fakes and temporary repositories. Do not build the real candidate yet.

- [ ] **Step 6: Run the Task 9 review checkpoint**

Fresh spec reviewer first, then fresh code-quality reviewer. Fix and re-review every important finding. Do not start Task 10 until both are clear.

---

### Task 10: Validate the candidate, prove rollback identity, and run final acceptance

**Files:**

- Create: `scripts/validate-containment-candidate.ps1`
- Create: `scripts/verify-containment-safe-rollback.ps1`
- Create: `scripts/tests/validate-containment-candidate.tests.ps1`
- Create: `scripts/tests/containment-safe-rollback.tests.ps1`

These remain standalone containment-campaign tools. They do not alter the normal installer, release validator, release manifest, or build-release skills, and they do not publish or promote a build. All four Task 10 production/test scripts put `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'` in their first executable lines after `param(...)`; tests inject a normally nonterminating cmdlet error and prove the next validation stage is not reached.

- [ ] **Step 1: Re-establish the task environment**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
$ActualWorktree = (Get-Location).ProviderPath
if (-not [string]::Equals($ActualWorktree, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong cwd: $ActualWorktree" }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = ($PythonIdentityOutput -join "`n").Trim()
if (-not $ReportedPython) { throw 'Python identity probe returned an empty path' }
$ReportedPython = (Resolve-Path -LiteralPath $ReportedPython).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
function Assert-ExpectedRedResult {
  param([int]$ExitCode, [object[]]$Output, [string]$Marker, [string]$JunitPath = '')
  $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
  $Output | ForEach-Object { Write-Host ([string]$_) }
  if ($ExitCode -ne 1) { throw "expected-red '$Marker' exited $ExitCode instead of 1" }
  if (-not $Text.Contains($Marker)) { throw "expected-red '$Marker' did not emit its assertion marker" }
  if ($Text -match '(?im)(ERROR collecting|INTERNALERROR|ModuleNotFoundError|ImportError|SyntaxError|IndentationError|TabError|file or directory not found|no tests ran|pytest: error|UsageError|ParserError|CommandNotFoundException|PathNotFound|timed out|Traceback \(most recent call last\))') { throw "expected-red '$Marker' was an infrastructure failure" }
  if ($JunitPath) {
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw "expected-red '$Marker' did not write JUnit evidence" }
    [xml]$Junit = Get-Content -Raw -LiteralPath $JunitPath
    $Suites = @($Junit.SelectNodes('//testsuite'))
    [int]$Errors = 0
    [int]$Failures = 0
    foreach ($Suite in $Suites) { $Errors += [int]$Suite.errors; $Failures += [int]$Suite.failures }
    $FailureNodes = @($Junit.SelectNodes('//testcase/failure'))
    if ($Errors -ne 0 -or $Failures -lt 1 -or $FailureNodes.Count -ne $Failures) { throw "expected-red '$Marker' had collection/error or malformed JUnit evidence" }
    foreach ($Failure in $FailureNodes) {
      if (-not (([string]$Failure.message + "`n" + [string]$Failure.InnerText).Contains($Marker))) { throw "expected-red '$Marker' had an unmarked assertion failure" }
    }
  }
}
$PrivatePythonFixtureOutput = @(& $Python -c "import os,sys; print(os.path.realpath(getattr(sys, '_base_executable', sys.executable)))" 2>&1)
$PrivatePythonFixtureExit = $LASTEXITCODE
if ($PrivatePythonFixtureExit -ne 0) { throw "base Python probe failed with exit code $PrivatePythonFixtureExit" }
$PrivatePythonFixture = ($PrivatePythonFixtureOutput -join "`n").Trim()
if (-not $PrivatePythonFixture -or -not (Test-Path -LiteralPath $PrivatePythonFixture -PathType Leaf)) { throw "full-CPython fixture is missing: $PrivatePythonFixture" }
$PrivatePythonFixture = (Resolve-Path -LiteralPath $PrivatePythonFixture).Path
$Task10Branch = git branch --show-current
if ($LASTEXITCODE -ne 0) { throw "Task 10 branch check failed with exit code $LASTEXITCODE" }
if ($Task10Branch -ne 'codex/gh-execute-intent-root-fix') { throw "unexpected Task 10 branch: $Task10Branch" }
$Task10Status = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw "Task 10 status check failed with exit code $LASTEXITCODE" }
if ($Task10Status.Count -ne 0) { throw "Task 10 worktree is not clean: $($Task10Status -join '; ')" }
```

Expected: branch `codex/gh-execute-intent-root-fix`; Tasks 1–9 reviewed; clean worktree.

- [ ] **Step 2: Write and immediately run the failing PowerShell tests**

The tests use only fake installers, temporary directories, fake telemetry/accessors, fake Rhino/GH gates, and short child processes. Cover success, read-only `-VerifyEvidenceOnly`, Windows quoting of empty strings/spaces/quotes/trailing backslashes, concurrent stdout/stderr larger than pipe capacity, timeout termination, candidate-installer and inherited fake-post-install environment sanitization, private-Python user-site startup isolation, the exact Task 8 JSONL challenge/response/result protocol, and every fail-closed branch: corrupt identity or sidecar, installer/hash drift, source-SHA mismatch, nonempty/reparse evidence directory with zero writes, stale process, failed preflight quiescence, failed install, wrong installed origin, discovery leak, denial mismatch, telemetry mismatch, child-process replacement, wrong/EOF/replayed authorization, target/state drift, malformed scenario artifact/sidecar, live failure, uncertain ownership, unverified restoration, supported-path denial activity, cleanup failure after otherwise-green checks, durable-hold move/collision/projection/receipt failures, and post-run artifact drift.

`validate-containment-candidate.tests.ps1` declares mandatory `-PrivatePythonPath`, receives the canonical `sys._base_executable` resolved in Step 1, rejects a venv/embedded/`._pth`-isolated fixture, and requires its unsanitized user-site control to fire; no skip or simulated startup result is allowed. This full-CPython fixture tests the local process policy before a candidate exists, but it is not release evidence—the normal validator derives and attests the identity-bound candidate runtime itself.

They also pin rollback to an immutable installer digest plus a retained successful acceptance record; a candidate identity alone is insufficient.

```powershell
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    -NoProfile -ExecutionPolicy Bypass `
    -File scripts\tests\validate-containment-candidate.tests.ps1 `
    -PrivatePythonPath $PrivatePythonFixture 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T10:VALIDATOR_MISSING'
$SavedErrorActionPreference = $ErrorActionPreference
try {
  $ErrorActionPreference = 'Continue'
  $RedOutput = @(& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
    -NoProfile -ExecutionPolicy Bypass `
    -File scripts\tests\containment-safe-rollback.tests.ps1 2>&1)
  $RedExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $SavedErrorActionPreference }
Assert-ExpectedRedResult -ExitCode $RedExit -Output $RedOutput -Marker 'EXPECTED_RED:T10:ROLLBACK_MISSING'
```

Expected: both FAIL because their production scripts do not exist.

- [ ] **Step 3: Implement the Windows PowerShell 5.1 child-process boundary**

Use one small local helper in `validate-containment-candidate.ps1`, not a shared process framework. Its public input is an executable plus `string[]` arguments. Adapt the Windows-safe `ConvertTo-ProcessArgument` algorithm from `scripts/tests/managed-runtime-profile-guards.tests.ps1`, but declare `[AllowNull()][AllowEmptyString()][string]$Value` and return the literal `""` when `$null -eq $Value -or $Value.Length -eq 0` before the whitespace fast path. Join converted values and assign the result to `ProcessStartInfo.Arguments`; Windows PowerShell 5.1 does not provide the modern `ProcessStartInfo.ArgumentList` API. Set `UseShellExecute = $false`, redirect both streams, use a bounded timeout, and assign a unique temporary working directory.

Drain stdout and stderr concurrently with `BeginOutputReadLine`/`BeginErrorReadLine` (or equivalent asynchronous handlers) into bounded in-memory summaries plus retained diagnostic files before waiting. On timeout, terminate the child, wait for exit and both drains to complete within a second bound, and fail; never perform sequential `ReadToEnd()` calls that can deadlock on a full sibling pipe. Tests emit more than one pipe buffer on both streams and prove timeout cleanup. All ordinary children have stdin closed. For the two live-gate children only, enable redirected stdin, accept exactly one parsed `authorization_required` stdout record through a bounded one-shot callback, show its fields, call `Read-Host`, write that response plus one newline, flush, and close stdin; reject a second challenge or any noncanonical stdout record.

Before `Process.Start()` for **every** installed-Python child, including both live gates, enumerate `ProcessStartInfo.EnvironmentVariables`; remove `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`, `DSPY_CACHEDIR`, `CHIRP_HOME`, and every case-insensitive `ROOK_*` key; then re-add code-owned `PYTHONNOUSERSITE=1` plus only the exact command allowlist pinned in Task 7. `PYTHONUSERBASE` and `DSPY_MODEL` remain absent, `PYTHONNOUSERSITE` is exactly the string `1`, `DSPY_CACHEDIR` is exactly the validated code-owned path, and `CHIRP_HOME` is absent unless the command re-adds the validated installed path. Do not retain an empty variable as a substitute for removal. The default discovery child and both live gates add no profile/interactive/target/model/bridge overrides; the dedicated interactive probe explicitly opts in only to its two pinned values. Record sorted removed names and final allowlisted names, never values containing user content. Never use `Start-Process -Environment`, `.ArgumentList`, ambient inherited gate state, or a parent worktree `PYTHONPATH` as the child's import path.

The candidate installer also launches through this same local bounded `ProcessStartInfo` helper. Its fixed, non-exported installer branch removes `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`, `DSPY_CACHEDIR`, `CHIRP_HOME`, and every case-insensitive `ROOK_*` key immediately before `Process.Start()`, then re-adds only code-owned `PYTHONNOUSERSITE=1`; every other listed control remains absent. This exact environment is inherited through Inno `Exec()` by the bundled private-Python `post_install.py` descendant. No caller supplies an environment map or replacement value for this branch; record only the sorted removed and final controlled-variable names, never their values.

The tests must launch the exact executable below through the production helper and have a temporary child script report its environment before any Rook import, working directory, and JSON-encoded `$args`, proving the contract under Windows PowerShell 5.1. Seed hostile worktree `PYTHONPATH`, fake `PYTHONHOME`, mixed-case `PYTHONUSERBASE`, mixed-case `PYTHONNOUSERSITE=0`, mixed-case source-tree `CHIRP_HOME`, `DSPY_MODEL`, `DSPY_CACHEDIR`, and representative runtime/profile/target/process/document/Rhino/bridge/harness/model `ROOK_*` variables; exercise every Task 7 child policy plus both live modes and require only the command's code-owned allowlist remains. Prove `PYTHONUSERBASE` absent, `PYTHONNOUSERSITE` exactly `1`, `DSPY_MODEL` absent, `DSPY_CACHEDIR` exactly the validated code-owned path, and `CHIRP_HOME` either absent or exactly the validated installed path. Launch a fake candidate installer through the fixed installer branch, make it report its environment and launch its fake `post_install` grandchild without changing that environment, and require both projections show `PYTHONUSERBASE` absent, `PYTHONNOUSERSITE=1`, and every other controlled name absent. Deleting either removal, deleting the code-owned re-add, substituting an empty/other value, or allowing duplicate case variants must trip the test. Then require each real installed child to prove installed `rook.*` origins and source-free `sys.path`. Pass positional sentinels `left`, empty string, and `right` and require count 3 with the empty value at index 1; also round-trip spaces, quotes, and trailing backslashes and directly assert `ConvertTo-ProcessArgument ''` is the literal `""`:

```text
C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe
```

Pin one parent-observed startup-isolation probe that never trusts a post-startup child report as its sole evidence. The final normal-mode run uses the exact identity-inventoried candidate runtime at `<artifact>\stage\Rook\installer\runtime\python\cpython-3.11.9\python.exe`, requires its recorded hash/version, and requires both `python311._pth` and `python._pth` absent; no repository, venv, system, or previously installed Python may substitute. Under a fresh evidence-owned non-reparse directory, set an owned hostile user base, use that private Python with `-S` only to derive its `Python311\site-packages` path, and create exact code-owned `sitecustomize.py` and `usercustomize.py` files that each execute only `from pathlib import Path; Path(__file__).with_suffix('.hit').write_text('executed', encoding='ascii')`. A separate probe script outside the hostile site emits canonical JSON for executable/version identity, `sys.flags.no_user_site`, `site.ENABLE_USER_SITE`, controlled-variable presence/value, hostile-site membership in `sys.path`, and both customization-module origins.

First launch that exact private Python directly in a bounded fixture-validity control with the ordinary source/model/Rook controls removed, only `PYTHONUSERBASE=<owned-base>` deliberately restored, `PYTHONNOUSERSITE` absent, and no `-S`, `-s`, `-I`, or `-E`; require both external `.hit` files before accepting the probe output, `no_user_site=0`, `ENABLE_USER_SITE=true`, hostile-site membership, and both module origins beneath the owned site. This one test-only control imports no Rook code and has no network, target, host, or user-state authority. Remove only the two hit files. Then launch the same executable through the production installed-Python policy and require, from the parent plus canonical probe record, both hit files absent, `PYTHONUSERBASE` absent, exactly one canonical `PYTHONNOUSERSITE=1`, `no_user_site=1`, `ENABLE_USER_SITE=false`, hostile site absent from `sys.path`, and neither customization module resolved from it. The non-live PowerShell suite exercises the same logic through its injected full-CPython fixture and fake installer/grandchild, deriving that fixture's version-specific user-site path rather than assuming `Python311`; it may mock candidate identity and installation but may not skip the fixture-validity control or trust only child-reported environment.

- [ ] **Step 4: Implement candidate validation and installed certification**

The validator exposes `-ArtifactDirectory`, `-CandidateIdentityPath`, `-CandidateSidecarPath`, `-EvidenceDirectory`, and `-RhinoExe`. Normal mode requires a new empty, non-reparse evidence directory. Before installation, process termination, or any write, reject an invalid/nonempty evidence path with bounded stderr and no evidence artifact. Otherwise atomically claim the directory with this run's ownership marker; only post-claim failures use the diagnostic contract below. A mutually exclusive `-VerifyEvidenceOnly` mode accepts only `-EvidenceDirectory`, requires a successful acceptance record rather than failure diagnostics, performs every hash/count/set/restoration assertion below without installation, process termination, telemetry writes, or host mutation, and exits nonzero on any mismatch. In normal mode, it:

1. validates canonical identity bytes, sidecar, installer digest, source SHAs, non-publishable marker, payload inventory, and the unchanged staged installer hash; locates the candidate-bound private Python and runs both the fixture-validity control and sanitized installed-child startup-isolation probe above before any Rook import;
2. runs the existing `installer/rook_process_preflight.ps1`, terminates only its enumerated stale Rook-owned child processes, and requires a quiet resweep before install;
3. arms a distinct owned copy of both startup tripwires, seeds the installer `ProcessStartInfo` with hostile mixed-case `PYTHONUSERBASE` and mixed-case `PYTHONNOUSERSITE=0` before the fixed sanitizer, records the immutable installer digest, and installs that exact candidate silently through the sanitized installer branch; successful return additionally requires both parent-observed hit files absent, the installer projection showing `PYTHONUSERBASE` absent and canonical `PYTHONNOUSERSITE=1`, and installed files/runtime manifest corresponding to the candidate and created after install start;
4. pins each participating installed process identity and start token, then runs Task 7's source-free public/progressive probes under explicit full, lean, and readonly, its discovery-only child with `ROOK_MCP_TOOL_PROFILE` absent, its isolated interactive-full child, and its installed 164-probe internal bypass matrix;
5. requires the inner payload/origins, one healthy-ring record per denial, zero downstream model/target/host calls, installed module origins, discovery omission, and current surface snapshots (absent/default `422`, explicit full `422`, lean `20`, readonly `148`, interactive full `425`);
6. invokes Task 8's installed CLI once for Rhino and once for Grasshopper in separate new empty scenario directories. For each child, parse only canonical JSONL stdout, display the emitted `authorization_required` record and its complete target/mutation/verification/restoration text, use `Read-Host` immediately for that one scenario, write exactly one response line to the child's redirected stdin, then parse the final `scenario_result`. Never place authorization in argv/environment or auto-answer it; and
7. independently load each `<scenario>-scenario.json` and sidecar, reassert the exact Task 8 schema, installed origins, target ownership, and challenge/preflight hashes; load every enumerated per-operation argument/result file, require canonical bytes and owned relative paths, recompute its SHA-256, match the exact admitted operation sequence/code-owned inputs, and validate each result against the final host projection; then reassert host verification, declared restoration, scratch disposal, discovery removal, and zero telemetry delta. Rehash the installer/identity and defer acceptance until final cleanup and a quiet process resweep also pass.

Each telemetry baseline is tied to the same process identity/start token as its corresponding probe. A restart or replacement invalidates the evidence and fails the run. Ordinary continuation by an already-connected model remains governed by existing budgets; the validator only prohibits downstream or containment-triggered model invocation.

- [ ] **Step 5: Pin failure and restoration behavior**

On failure, stop all forward work. If an authorized live scenario owns its scratch target with certainty, enter only that scenario's already authorized restoration path. If ownership is ambiguous, make no further host mutation. Passing requires verified declared-state restoration; attempted cleanup is never enough.

For a failure before the candidate installer starts, stop owned processes, require the ordinary quiet resweep, preserve diagnostics, and do not change installed startup state. For **every** failure after installer start, process cleanup alone is insufficient. After any authorized restoration, stop candidate-owned MCP/Rhino/Chirp processes and establish this campaign-owned durable hold before the validator returns:

1. create a new non-reparse `%LOCALAPPDATA%\Rook\containment-hold\<candidate-identity-sha256>\<run-id>` whose leaf did not previously exist; the path component is the lowercase 64-hex digest of the exact canonical candidate identity bytes, not a branch name or mutable version;
2. atomically move the complete `%LOCALAPPDATA%\Rook\venv` to that same-volume hold. Atomically rename the installed companion entry assemblies `RookNative\net8.0\Rook.rhp`, `RookNative\net7.0\Rook.rhp`, and `RookNative\net48\Rook.rhp` in place to unique names ending `.rhp.contained.<candidate-identity-sha256>.<run-id>`; the held names do not end in `.rhp`, and the registered original paths become absent without assuming `%APPDATA%` and `%LOCALAPPDATA%` share a volume. Record a code-owned absent source as absent; reject a preexisting destination, reparse point, partial move, or hash/size drift. Attempt every hold action even if an earlier one fails, but never rename or move held bytes back;
3. prove the original venv and all three entry-assembly paths are absent, held projections match their pre-move hashes, and a second idempotent same-run verification performs no mutation;
4. inspect `~/.claude.json`, optional `~/.claude/.mcp.json`, `%APPDATA%\Claude\claude_desktop_config.json`, `~/.codex/config.toml`, root/net8/net7/net48 `RookChatService.json`, and the companion plug-in registry `FileName`. Every present Rook MCP/chat startup record must resolve to the now-missing original venv/entry assembly; any alternate executable, assembly, or still-runnable Rook registration fails the hold; and
5. require a final quiet resweep, then write canonical `containment-hold.json` plus SHA-256 sidecar inside the hold directory and bind both hashes into failure evidence. The receipt records the candidate/run identities, exact original/held paths and file/tree hashes, all config/manifest/registry projections, and both quiet-resweep results without copying user configuration content.

Moving the venv durably blocks the configured MCP and packaged internal-agent entrypoints; holding all three managed `Rook.rhp` assemblies under non-`.rhp` names blocks RookChat, including manifest regeneration or Python fallback. There is no separately installed internal-agent daemon. Before installation, the validator inventories these exact startup surfaces, requires each present Rook config/manifest/registry record to be parseable and point only to the canonical venv/entry paths covered by the hold, and rejects alternate authority before installer start. Tests freeze that startup-surface inventory against the unchanged installer/post-install wiring, simulate a respawn after the first resweep and again after validator exit, and prove both attempts fail because the original executable/assembly paths remain absent. They cover hold collisions, cross-volume-safe rename behavior, partial failures, idempotent verification, exact receipt/sidecar checks, and prove no failure path restores preinstall or otherwise unverified bytes. A later installer may recreate active paths only after `verify-containment-safe-rollback.ps1` approves that installer digest against a retained successful acceptance record; absent that proof, the hold remains.

In `finally`, preserve all diagnostics and never alter the installer or candidate evidence. Any restoration, process cleanup, durable-hold, or receipt failure keeps the run failed and is recorded as an emergency quiescence failure; the candidate is never promoted or treated as inactive without the verified hold. Do not fall back to an older build automatically. On any failure after evidence-directory ownership, write canonical `containment-failure.json` plus `containment-failure.sha256` with status/failure stage, durable-hold status/path/hash when installation started, and hashes of retained diagnostics, but create neither `containment-acceptance.json` nor `containment-acceptance.sha256`. Pre-ownership path rejection writes nothing. Because every normal run claims a previously empty directory and never overwrites one, stale successful evidence cannot survive a failed rerun.

- [ ] **Step 6: Freeze the retained acceptance and rollback contracts**

Only after every proof, both verified restorations, final cleanup, and the quiet resweep pass, atomically write `containment-acceptance.json` with `success: true` and its SHA-256 sidecar. It contains:

- schema version, fixed `success: true`, UTC start/end, validator SHA, candidate identity hash, installer hash, and installed-runtime identity;
- quiescence/preflight evidence;
- identity-bound private-Python hash/version/`._pth` projection, fixture-validity control, installed-child and real-installer startup-isolation probe records, controlled-variable projections, external tripwire-marker absence, and hashes of the owned probe/scripts;
- absent/default plus explicit per-profile discovery counts and all 36 public/progressive denial records;
- all 164 focused internal-boundary records;
- telemetry baselines, process identities/start tokens, origins, payload checks, and downstream-spy totals;
- independently parsed Rhino and GH scenario-record/sidecar hashes, authorization, admitted operations, host verification, declared restoration, and zero-containment-event records; and
- diagnostic artifact paths and hashes.

Successful acceptance additionally requires that no containment hold was activated for this candidate/run and that no hold receipt is present in its evidence. A post-install failure may never produce acceptance, even when the durable hold succeeds.

The rollback verifier is read-only. It accepts an installer plus a retained successful acceptance record and requires the installer digest, candidate identity digest, fixed successful validator result, and acceptance sidecar to match. It rejects a failure diagnostic, missing acceptance, mutable/differently hashed evidence, or any record without `success: true`. `-VerifyEvidenceOnly` applies the same distinction. This proves eligibility only; it does not install, roll back, publish, or reactivate any contained identity.

- [ ] **Step 7: Run Task 10's non-live tests and commit**

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\validate-containment-candidate.tests.ps1 `
  -PrivatePythonPath $PrivatePythonFixture
if ($LASTEXITCODE -ne 0) { throw "Task 10 validator tests failed with exit code $LASTEXITCODE" }
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\containment-safe-rollback.tests.ps1
if ($LASTEXITCODE -ne 0) { throw "Task 10 rollback tests failed with exit code $LASTEXITCODE" }
git add scripts/validate-containment-candidate.ps1 `
  scripts/verify-containment-safe-rollback.ps1 `
  scripts/tests/validate-containment-candidate.tests.ps1 `
  scripts/tests/containment-safe-rollback.tests.ps1
if ($LASTEXITCODE -ne 0) { throw "Task 10 staging failed with exit code $LASTEXITCODE" }
$ExpectedTask10 = @(
  'scripts/validate-containment-candidate.ps1', 'scripts/verify-containment-safe-rollback.ps1',
  'scripts/tests/validate-containment-candidate.tests.ps1', 'scripts/tests/containment-safe-rollback.tests.ps1'
) | Sort-Object
$ActualTask10 = @(git diff --cached --name-only)
if ($LASTEXITCODE -ne 0) { throw "Task 10 staged-file inspection failed with exit code $LASTEXITCODE" }
$Task10Delta = @(Compare-Object $ExpectedTask10 ($ActualTask10 | Sort-Object))
if ($Task10Delta.Count -ne 0) { throw "Task 10 staged-file set mismatch: $($Task10Delta | Out-String)" }
git commit -m "test(containment): add standalone candidate acceptance"
if ($LASTEXITCODE -ne 0) { throw "Task 10 commit failed with exit code $LASTEXITCODE" }
```

Expected: fake/stub tests PASS; no real installation or live mutation occurs yet.

- [ ] **Step 8: Run whole-branch reviews before any real build or install**

Run a fresh whole-branch spec-compliance review against approved design commit `e2e5c914e6e2db341e207d8b6d424234f8cf03e6`, followed by a fresh whole-branch code-quality/security review. Fix every important finding and repeat both reviews. Do not build or install until both are clear.

- [ ] **Step 9: Run the complete non-live acceptance sequence**

Open a fresh shell after the reviews. Re-establish strict mode, exact cwd, and exact Python identity before running this focused set, the two Task 2 manual guards, all three new PowerShell guard suites through Windows PowerShell 5.1, then the complete Python suite:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
if (-not [string]::Equals((Get-Location).ProviderPath, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) { throw 'wrong acceptance cwd' }
$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python is missing: $Python" }
$ExpectedPython = (Resolve-Path -LiteralPath $Python).Path
$PythonIdentityOutput = @(& $Python -c "import os,sys; print(os.path.realpath(sys.executable))" 2>&1)
$PythonIdentityExit = $LASTEXITCODE
if ($PythonIdentityExit -ne 0) { throw "Python identity probe failed with exit code $PythonIdentityExit" }
$ReportedPython = (Resolve-Path -LiteralPath (($PythonIdentityOutput -join "`n").Trim())).Path
if (-not [string]::Equals($ReportedPython, $ExpectedPython, [StringComparison]::OrdinalIgnoreCase)) { throw "wrong Python: $ReportedPython" }
$PrivatePythonFixtureOutput = @(& $Python -c "import os,sys; print(os.path.realpath(getattr(sys, '_base_executable', sys.executable)))" 2>&1)
$PrivatePythonFixtureExit = $LASTEXITCODE
if ($PrivatePythonFixtureExit -ne 0) { throw "base Python probe failed with exit code $PrivatePythonFixtureExit" }
$PrivatePythonFixture = ($PrivatePythonFixtureOutput -join "`n").Trim()
if (-not $PrivatePythonFixture -or -not (Test-Path -LiteralPath $PrivatePythonFixture -PathType Leaf)) { throw "full-CPython fixture is missing: $PrivatePythonFixture" }
$PrivatePythonFixture = (Resolve-Path -LiteralPath $PrivatePythonFixture).Path
$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
& $Python -m pytest `
  mcp_server/tests/test_tool_lifecycle.py `
  mcp_server/tests/test_containment_telemetry.py `
  mcp_server/tests/test_tool_catalog_cache.py `
  mcp_server/tests/test_mcp_tool_profiles.py `
  mcp_server/tests/test_server_tool_profiles.py `
  mcp_server/tests/test_rook_tools_meta.py `
  mcp_server/tests/test_capability_index.py `
  mcp_server/tests/test_capability_inventory.py `
  mcp_server/tests/test_profile_reconciliation.py `
  mcp_server/tests/test_rookchat_tool_contracts.py `
  mcp_server/tests/test_rookchat_tool_schema_golden.py `
  mcp_server/tests/test_rookchat_visible_dispatchability.py `
  mcp_server/tests/test_chat_runner.py `
  mcp_server/tests/test_chat_server.py `
  mcp_server/tests/test_base_agent_live_producer.py `
  mcp_server/tests/test_dispatcher_safety.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_server_contract_hardening.py `
  mcp_server/tests/test_gh_edit_postmortem.py `
  mcp_server/tests/test_bridge.py `
  mcp_server/tests/test_substrate_analytics.py `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_plan_graph_live.py `
  mcp_server/tests/test_plan_graph_live_dispatch.py `
  mcp_server/tests/test_containment_guidance.py `
  mcp_server/tests/test_chat_prompt_builder.py `
  mcp_server/tests/test_containment_acceptance.py `
  mcp_server/tests/test_containment_live_gate.py `
  mcp_server/tests/test_runtime_harness.py `
  mcp_server/tests/test_local_testing_proof.py -q
if ($LASTEXITCODE -ne 0) { throw 'focused Python containment tests failed' }
& $Python mcp_server/tests/manual_phase2_dispatcher.py
if ($LASTEXITCODE -ne 0) { throw 'manual_phase2_dispatcher failed' }
& $Python mcp_server/tests/manual_phase3_catalog.py
if ($LASTEXITCODE -ne 0) { throw 'manual_phase3_catalog failed' }
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\build-containment-candidate-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'candidate builder guards failed' }
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\validate-containment-candidate.tests.ps1 `
  -PrivatePythonPath $PrivatePythonFixture
if ($LASTEXITCODE -ne 0) { throw 'candidate validator guards failed' }
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\containment-safe-rollback.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'rollback verifier guards failed' }
& $Python -m pytest mcp_server/tests -m "not requires_rhino" -q
if ($LASTEXITCODE -ne 0) { throw 'complete Python test suite failed' }
git diff --check e2e5c914e6e2db341e207d8b6d424234f8cf03e6..HEAD
if ($LASTEXITCODE -ne 0) { throw 'committed branch diff check failed' }
$UnexpectedStatus = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
if ($UnexpectedStatus.Count -ne 0) { throw "worktree is not clean: $($UnexpectedStatus -join '; ')" }
```

Expected: all tests PASS, every `requires_rhino` test remains deselected from this non-live sequence, no unexpected modified/untracked files, and no production process or host mutation.

- [ ] **Step 10: Build the immutable candidate**

Invoke the builder with the exact reviewed Rook SHA, exact clean Chirp SHA/root, empty artifact directory, and explicit external tool roots. Preserve its full logs:

```powershell
$ArtifactDirectory = '<absolute-new-empty-candidate-directory>'
$EvidenceDirectory = '<absolute-new-empty-evidence-directory>'
$CandidateIdentityPath = Join-Path $ArtifactDirectory 'containment-candidate.json'
$CandidateSidecarPath = Join-Path $ArtifactDirectory 'containment-candidate.sha256'
$RhinoExe = '<absolute-rhino-exe>'
foreach ($Path in @($ArtifactDirectory, $EvidenceDirectory)) {
  if (-not [System.IO.Path]::IsPathRooted($Path)) { throw "campaign path is not absolute: $Path" }
  if (Test-Path -LiteralPath $Path) {
    $Item = Get-Item -LiteralPath $Path -Force
    if (-not $Item.PSIsContainer -or ($Item.Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw "campaign path is not a plain directory: $Path" }
    if (@(Get-ChildItem -LiteralPath $Path -Force).Count -ne 0) { throw "campaign path is not empty: $Path" }
  }
}
if (-not [System.IO.Path]::IsPathRooted($RhinoExe) -or -not (Test-Path -LiteralPath $RhinoExe -PathType Leaf)) { throw 'RhinoExe must be an existing absolute file' }
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\build-containment-candidate.ps1 `
  -RookRoot $Worktree `
  -ExpectedBranch 'codex/gh-execute-intent-root-fix' `
  -ExpectedRookSha '<reviewed-rook-sha>' `
  -ChirpRoot '<clean-chirp-root>' `
  -ExpectedChirpSha '<reviewed-chirp-sha>' `
  -ArtifactDirectory $ArtifactDirectory `
  -GitPath '<git-exe>' `
  -PowerShellPath 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -CmdPath '<cmd-exe>' `
  -Msys2Bash '<msys2-bash-exe>' `
  -VcvarsallPath '<vcvarsall-bat>' `
  -MsbuildPath '<msbuild-exe>' `
  -DotnetPath '<dotnet-exe>' `
  -RhinoSystemDir '<rhino-system-dir>' `
  -RevitInstallDir '<revit-install-dir>' `
  -VcRedistRoot '<vc-redist-root>' `
  -OcctRoot '<occt-build-root>' `
  -OcctRuntimeRoot '<occt-runtime-root>' `
  -IsccPath '<iscc-exe>'
if ($LASTEXITCODE -ne 0) { throw "containment candidate build failed with exit code $LASTEXITCODE" }
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\tests\build-containment-candidate-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw "post-build candidate guards failed with exit code $LASTEXITCODE" }
$CandidateIdentity = Get-Content -Raw -LiteralPath $CandidateIdentityPath | ConvertFrom-Json
$InstallerPath = Join-Path $ArtifactDirectory ([string]$CandidateIdentity.installer.relative_path)
if (-not (Test-Path -LiteralPath $InstallerPath -PathType Leaf)) { throw 'candidate identity installer path is missing' }
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $InstallerPath).Hash.ToLowerInvariant() -ne ([string]$CandidateIdentity.installer.sha256).ToLowerInvariant()) { throw 'candidate identity installer hash mismatch' }
```

Independently recompute the identity sidecar, staged-installer hash, installer hash, source SHAs, payload inventory, packaged empty-GHX digest, candidate-staged private-Python executable hash and empty `*._pth` projection, recorded managed-reference inputs, canonical OCCT build/runtime relationship and consumed-file projections, inert `RhinoPluginDir` absence, and unchanged live plug-in-directory projection.

Expected: one non-publishable immutable candidate; the source worktree remains clean.

- [ ] **Step 11: Run authorized installed/live acceptance**

With Rhino and Grasshopper initially closed, invoke the validator exactly as follows. It must pause for the two scenario-specific authorizations immediately before each first mutation. Complete no other user work in the owned processes.

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\validate-containment-candidate.ps1 `
  -ArtifactDirectory $ArtifactDirectory `
  -CandidateIdentityPath $CandidateIdentityPath `
  -CandidateSidecarPath $CandidateSidecarPath `
  -EvidenceDirectory $EvidenceDirectory `
  -RhinoExe $RhinoExe
if ($LASTEXITCODE -ne 0) { throw "installed/live containment acceptance failed with exit code $LASTEXITCODE" }
```

After it exits, run the read-only evidence mode—not prose inspection—to assert `containment-acceptance.json`:

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\validate-containment-candidate.ps1 `
  -VerifyEvidenceOnly `
  -EvidenceDirectory $EvidenceDirectory
if ($LASTEXITCODE -ne 0) { throw "read-only containment evidence verification failed with exit code $LASTEXITCODE" }
```

That command must prove:

- success and candidate/installer/sidecar hashes match;
- the identity-bound private-Python control fired both owned startup hooks, while the sanitized installed-child and real installer-to-`post_install.py` boundaries retained no hit marker, kept `PYTHONUSERBASE` absent, and set exactly `PYTHONNOUSERSITE=1` with matching probe/script hashes;
- discovery proves absent/default `422`, explicit full `422`, lean `20`, readonly `148`, and interactive full `425` in distinct installed children;
- exactly 12 installed public/progressive denials per explicit profile and 164 installed internal-boundary denials are present;
- every denial has the stable payload, expected fixed origin, healthy exact-one telemetry record, and zero downstream spy totals;
- both supported live scenarios have verified declared-state restoration and zero containment-event delta; and
- final process quiescence and post-run artifact hashes pass.

Then run the read-only rollback eligibility check:

```powershell
& 'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe' `
  -NoProfile -ExecutionPolicy Bypass `
  -File scripts\verify-containment-safe-rollback.ps1 `
  -InstallerPath $InstallerPath `
  -CandidateIdentityPath $CandidateIdentityPath `
  -AcceptancePath (Join-Path $EvidenceDirectory 'containment-acceptance.json') `
  -AcceptanceSidecarPath (Join-Path $EvidenceDirectory 'containment-acceptance.sha256')
if ($LASTEXITCODE -ne 0) { throw "containment-safe rollback verification failed with exit code $LASTEXITCODE" }
```

Expected: PASS. A failing candidate is never promoted; diagnostic evidence is retained. Withdrawal may target only an installer digest with a matching successful retained acceptance record. If none exists, affected surfaces remain quiesced.

- [ ] **Step 12: Final housekeeping and handoff**

```powershell
git diff --check e2e5c914e6e2db341e207d8b6d424234f8cf03e6..HEAD
if ($LASTEXITCODE -ne 0) { throw "final committed branch diff check failed with exit code $LASTEXITCODE" }
$FinalBranch = git branch --show-current
if ($LASTEXITCODE -ne 0) { throw "final branch check failed with exit code $LASTEXITCODE" }
if ($FinalBranch -ne 'codex/gh-execute-intent-root-fix') { throw "unexpected final branch: $FinalBranch" }
$FinalStatus = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw "final git status failed with exit code $LASTEXITCODE" }
if ($FinalStatus.Count -ne 0) { throw "final worktree is not clean: $($FinalStatus -join '; ')" }
git log --oneline --decorate -30
if ($LASTEXITCODE -ne 0) { throw "final git log failed with exit code $LASTEXITCODE" }
```

Expected: ten sequential reviewed task checkpoints, plus any necessary review-fix commits, after the approved specification/plan commits; clean worktree; no push, merge, PR, publication, promotion, or normal release-pipeline change. Hand off the candidate digest, acceptance-record digest, exact commands, retained evidence directory, and any operational caveats for senior approval.

---
