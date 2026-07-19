# Legacy Semantic-Authority Containment Completion and Pruning Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Preserve the completed six-name runtime containment, replace the accidental release-certification platform with thin external release proof, migrate dangerous legacy uninstall authority during ordinary upgrades, and prove the normal Rook installer without risking the RookVision gallery.

**Architecture:** The runtime implementation already has the approved manifest, catalog filtering, shallow execution guards, bounded telemetry, guidance cleanup, and exhaustive source coverage. Do not redesign those surfaces. Add exactly one setup directive to the existing installer so eligible same-application upgrades overwrite unsafe legacy uninstall logs. Add three campaign-only release tools outside `rook-mcp`: a reduced installed probe, a paired live-preservation gate, and a small coordinator around the existing installer, smoke workflow, and release validator. Then delete the alternate builder, generalized validator, durable-hold/rollback machinery, and package-resident release harnesses.

**Tech Stack:** Python 3.11, pytest/pytest-asyncio, MCP stdio transport, Windows PowerShell 5.1, .NET/Windows known-folder and file-attribute APIs already available to PowerShell, the existing Inno Setup installer, Rhino 8, Grasshopper, and the existing Rook release scripts.

## Approved Baseline and Stop Rules

- [ ] Treat specification commit `5c37f2d6f30344648c9b7dcb39ccd3b92121a18d` as immutable. The implementation-plan commit must have that exact parent and change only this plan.
- [ ] Work only in `C:/Users/aryan/source/repos/Rook/.worktrees/gh-execute-intent-root-fix` on `codex/gh-execute-intent-root-fix`.
- [ ] Do not begin implementation or pruning until this rewritten plan receives user and senior-reviewer approval.
- [ ] Execute Tasks 1-6 sequentially. Use a fresh implementer for each task, then a fresh spec-compliance reviewer, then a fresh code-quality reviewer. Fix and re-review every important finding before advancing. Never run two implementation agents concurrently.
- [ ] Task commits are review checkpoints, not deployable candidates. Do not install, publish, or promote an intermediate commit.
- [ ] After Task 6, run the whole-branch review and source acceptance in Task 7. Actual installer/live release acceptance happens only after the containment PR and the normal version-bump PR are merged to `main`.
- [ ] A material change to the approved runtime containment contract, any normal-installer behavior beyond the exact `UninstallLogMode=overwrite` migration, the release-manifest schema, or the approved 36/29/live proof returns to design review instead of being improvised in implementation.

The six identities remain:

| Tool | Disposition |
|---|---|
| `gh_execute_intent` | retired |
| `rhino_execute_intent` | retired |
| `plan_and_execute` | suspended |
| `spawn_agent` | suspended |
| `gh_explore_workflow` | suspended |
| `gh_replay_recipe` | suspended |

## Scope Guardrails

Retain the existing runtime containment implementation and its source tests. In particular, do not reimplement or broadly refactor:

- `mcp_server/src/rook/tool_lifecycle.py`
- `mcp_server/src/rook/tool_lifecycle_runtime.py`
- the bounded containment ring in `mcp_server/src/rook/learning/metrics_store.py`
- catalog/profile/cache filtering in `mcp_server/src/rook/server.py`, `capability_index.py`, and `mcp_server/src/rook/agent/*`
- execution guards in `server.py`, `RookAgent`, `RookChat`, PlanGraph, `ToolDispatcher`, bootstrap, learning, and explorer executors
- the current containment, catalog, protocol, telemetry, guidance, and supported-path source tests

If a focused regression exposes a genuine defect in those files, stop that task and return the proposed runtime change for review. This completion plan does not authorize opportunistic runtime redesign.

The sole authorized normal-installer edit is one added line, `UninstallLogMode=overwrite`, in the existing `[Setup]` section of `installer/RookSetup.iss`. Preserve the exact public `AppId`, privilege/architecture mode, directories, payload, `[Code]`, and every other installer byte. This is a legacy-log migration, not an installer redesign.

Do not modify any of these other release surfaces:

- `installer/post_install.py`
- `installer/python_runtime_install.py`
- `scripts/validate-release-artifacts.ps1`
- `scripts/tests/validate-release-artifacts.tests.ps1`
- the release-manifest schema
- normal Python/wheelhouse, FFmpeg, native, managed, RookBIM, or ISCC build scripts
- `mcp_server/pyproject.toml`

Do not add:

- another installer or candidate builder;
- a generalized release validator or evidence store;
- durable hold, quarantine, rollback, backup, or gallery-repair machinery;
- a generic process/executor/authorization framework;
- a VM, disposable Windows profile, or isolated user gallery requirement;
- new dependencies;
- force-kill behavior for a user host; or
- production flags, registrations, or packaged callables that can bypass containment.

Excluding the frozen specification and this plan-only commit, the completed implementation must delete more lines than it adds. This is a pruning campaign; documentation deletion in this plan cannot make that gate pass.

## Task Shell and Commit Discipline

Run this block at the start of every task in a fresh Windows PowerShell 5.1 shell:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$Worktree = 'C:\Users\aryan\source\repos\Rook\.worktrees\gh-execute-intent-root-fix'
$ExpectedWorktree = (Resolve-Path -LiteralPath $Worktree).Path
Set-Location -LiteralPath $ExpectedWorktree
if (-not [string]::Equals((Get-Location).ProviderPath, $ExpectedWorktree, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'Wrong worktree'
}
$Branch = (git branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) { throw 'Branch identity probe failed' }
if ($Branch -ne 'codex/gh-execute-intent-root-fix') { throw "Wrong branch: $Branch" }

$Python = 'C:\Users\aryan\source\repos\Rook\mcp_server\.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Missing test Python: $Python" }
$ReportedPython = (& $Python -c "import os,sys; print(os.path.realpath(sys.executable))").Trim()
if ($LASTEXITCODE -ne 0) { throw 'Python identity probe failed' }
if (-not [string]::Equals((Resolve-Path -LiteralPath $ReportedPython).Path, (Resolve-Path -LiteralPath $Python).Path, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Wrong Python: $ReportedPython"
}

$WindowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
if (-not (Test-Path -LiteralPath $WindowsPowerShell -PathType Leaf)) { throw 'Windows PowerShell 5.1 is missing' }

function Resolve-PinnedPrivatePythonFixtureSource {
    $Path = Join-Path $ExpectedWorktree 'installer\runtime\python\cpython-3.11.9\python.exe'
    $StageOutput = @(& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File 'scripts\python-runtime\stage-rook-python-runtime.ps1' -RepoRoot $ExpectedWorktree 2>&1)
    $StageCode = $LASTEXITCODE
    $StageOutput | ForEach-Object { Write-Host ([string]$_) }
    if ($StageCode -ne 0) { throw 'Pinned CPython 3.11.9 staging failed' }
    $Path = (Resolve-Path -LiteralPath $Path).Path
    $Version = (& $Path -c "import platform; print(platform.python_version())").Trim()
    if ($LASTEXITCODE -ne 0 -or $Version -cne '3.11.9') { throw "Wrong private-Python fixture version: $Version" }
    return $Path
}

function Resolve-PinnedInnoCompiler {
    $Path = 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "Missing normal-release Inno compiler: $Path" }
    $Item = Get-Item -LiteralPath $Path -Force
    if (($Item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) { throw 'Inno compiler is a reparse point' }
    return (Resolve-Path -LiteralPath $Path).Path
}

$env:PYTHONPATH = (Resolve-Path -LiteralPath 'mcp_server\src').Path
[void][IO.Directory]::CreateDirectory((Join-Path $ExpectedWorktree '.pytest_tmp'))

$Dirty = @(git status --porcelain)
if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
if ($Dirty.Count -ne 0) { $Dirty | Write-Host; throw 'Task must start from a clean worktree' }

function Invoke-ExpectedPytestRed {
    param([string]$Path, [string]$Marker, [string]$JunitPath)
    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $Output = @(& $Python -m pytest $Path --junitxml $JunitPath -q 2>&1)
        $Code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }
    $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
    $Output | ForEach-Object { Write-Host ([string]$_) }
    if ($Code -ne 1) { throw "Expected-red exited $Code instead of 1" }
    if ($Text -notmatch [regex]::Escape($Marker)) { throw "Expected-red marker missing: $Marker" }
    if ($Text -match 'ERROR collecting|ImportError|ModuleNotFoundError|SyntaxError|IndentationError|TabError|INTERNALERROR|file or directory not found|no tests ran|unrecognized arguments') {
        throw 'Expected-red was an infrastructure failure'
    }
    if (-not (Test-Path -LiteralPath $JunitPath -PathType Leaf)) { throw 'Expected-red JUnit is missing' }
    [xml]$Report = Get-Content -LiteralPath $JunitPath -Raw
    $Suites = @($Report.SelectNodes('//testsuite'))
    $Failures = 0; $Errors = 0
    foreach ($Suite in $Suites) { $Failures += [int]$Suite.failures; $Errors += [int]$Suite.errors }
    if ($Failures -lt 1 -or $Errors -ne 0) { throw "Invalid expected-red JUnit: failures=$Failures errors=$Errors" }
}

function Invoke-ExpectedPowerShellRed {
    param([string]$Path, [string]$Marker, [string[]]$Arguments = @())
    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $Output = @(& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $Path @Arguments 2>&1)
        $Code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }
    $Text = (@($Output | ForEach-Object { [string]$_ }) -join "`n")
    $Output | ForEach-Object { Write-Host ([string]$_) }
    if ($Code -ne 1) { throw "Expected-red exited $Code instead of 1" }
    if ($Text -notmatch [regex]::Escape($Marker)) { throw "Expected-red marker missing: $Marker" }
    if ($Text -match 'ParserError|SyntaxError|IndentationError|TabError|CommandNotFoundException|cannot find path|is not recognized') {
        throw 'Expected-red was an infrastructure failure'
    }
}

function Stage-ExactFiles {
    param([string[]]$Paths)
    $Expected = @($Paths | Sort-Object)
    if (@($Expected | Select-Object -Unique).Count -ne $Expected.Count) { throw 'Duplicate staged path' }
    git add -A -- $Expected
    if ($LASTEXITCODE -ne 0) { throw 'git add failed' }
    $Actual = @(git diff --cached --name-only) | Sort-Object
    $Delta = @(Compare-Object -CaseSensitive -ReferenceObject $Expected -DifferenceObject $Actual)
    if ($Delta.Count -ne 0) { $Delta | Format-Table | Out-String | Write-Host; throw 'Staged path allowlist mismatch' }
    git diff --cached --check
    if ($LASTEXITCODE -ne 0) { throw 'Staged diff check failed' }
}
```

Use the two expected-red helpers exactly. A parser/import/collection failure is not TDD evidence. Use `Stage-ExactFiles` with each task's literal array before every commit.

Commit only after focused tests pass. Reviewers inspect that task commit. Amend or add a tightly scoped correction commit, rerun the focused suite, and repeat the failed review before advancing.

## Fixed External Release Contracts

### Denial and telemetry shapes

The external release tool pins this literal expected-value oracle. It must not import or call candidate lifecycle helpers, `lifecycle_manifest()`, `resolve_contained_identity()`, or `containment_envelope()` to construct expected values:

```python
EXPECTED_DENIALS = {
    "gh_execute_intent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_execute_intent",
        "disposition": "retired",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper surface; inspect state and "
            "components, then use explicit gh_edit or supported script tools "
            "and verify solve state, outputs, and errors."
        ),
    },
    "rhino_execute_intent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "rhino_execute_intent",
        "disposition": "retired",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Rhino surface; use explicit typed Rhino "
            "tools, rhino_execute, or a sanctioned preflighted rhino_command, "
            "then verify the host result."
        ),
    },
    "plan_and_execute": {
        "code": "legacy_semantic_tool_contained",
        "tool": "plan_and_execute",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current surface and perform bounded steps through "
            "explicit admitted tools; autonomous plan execution is suspended."
        ),
    },
    "spawn_agent": {
        "code": "legacy_semantic_tool_contained",
        "tool": "spawn_agent",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current surface and use the connected model to call "
            "explicit admitted tools directly; autonomous agent spawning is "
            "suspended."
        ),
    },
    "gh_explore_workflow": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_explore_workflow",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper inspection surface and use "
            "explicit snapshot, component, or knowledge tools; semantic "
            "workflow exploration is suspended."
        ),
    },
    "gh_replay_recipe": {
        "code": "legacy_semantic_tool_contained",
        "tool": "gh_replay_recipe",
        "disposition": "suspended",
        "retryable": False,
        "verified": False,
        "recovery": (
            "Rediscover the current Grasshopper surface and apply reviewed "
            "explicit gh_edit operations; recipe replay is suspended."
        ),
    },
}
```

Dictionary-adapter seams return exactly `{"success": false, "data": EXPECTED_DENIALS[name]}`. The other internal boundaries preserve the typed/protocol adapters pinned below. Public MCP returns exactly one `TextContent` whose text equals `"Error: " + json.dumps(EXPECTED_DENIALS[name], indent=2)`. The telemetry delta contains exactly one event with only `tool`, `disposition`, fixed `origin`, and a timestamp matching `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$`; parse it with `%Y-%m-%dT%H:%M:%S.%fZ` to prove a real UTC timestamp. The installed gate requires an operational ring and exactly one observed event; a production telemetry-sink failure still may not weaken denial.

### Discovery and transport

The external installed probe pins:

```python
CONTAINED_TOOLS = (
    "gh_execute_intent",
    "rhino_execute_intent",
    "plan_and_execute",
    "spawn_agent",
    "gh_explore_workflow",
    "gh_replay_recipe",
)
DISCOVERY_COUNTS = {"unprofiled": 422, "lean": 20, "readonly": 148}
INTERACTIVE_FULL_COUNT = 425
TRANSPORT_INGRESSES = ("public_mcp", "progressive_meta")
```

The `422` snapshot is the default unprofiled surface: its child must have `ROOK_MCP_TOOL_PROFILE` genuinely absent and must record `profile_env_present: false`. The `425` interactive snapshot explicitly sets `ROOK_MCP_TOOL_PROFILE=full` plus `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1`. The lean and readonly discovery children set their corresponding profiles. The transport set is exactly `6 tools x 3 explicit profiles x 2 ingresses = 36`; its profiles remain `full`, `lean`, and `readonly`. Every record contains the tool, profile, ingress, exact stable denial payload, fixed telemetry origin, same PID/start token before and after, one adjacent containment-ring record, and zero downstream-spy entries.

### Literal 29-seam installed snapshot

The release tool and its test both pin this literal ordered table. It is not generated from candidate code, CLI input, a catalog, or reflection.

| # | Seam | Representative tool | Expected origin | Result adapter |
|---:|---|---|---|---|
| 1 | `server._call_tool_dispatch` | `gh_execute_intent` | `server_dispatch` | `dictionary_envelope` |
| 2 | `server._mcp_tool_executor` | `rhino_execute_intent` | `server_dispatch` | `dictionary_envelope` |
| 3 | `ToolDispatcher.dispatch` | `plan_and_execute` | `tool_dispatcher` | `dictionary_envelope` |
| 4 | `ToolDispatcher._dispatch_inner` | `spawn_agent` | `tool_dispatcher` | `dictionary_envelope` |
| 5 | `ToolDispatcher._call_local` | `gh_explore_workflow` | `tool_dispatcher` | `dictionary_envelope` |
| 6 | `ToolDispatcher._dispatch_with_knowledge` | `gh_replay_recipe` | `tool_dispatcher` | `dictionary_envelope` |
| 7 | `RookAgent._run_loop` | `gh_execute_intent` | `rook_agent` | `rook_agent_protocol` |
| 8 | `RookAgent._execute_tool` | `rhino_execute_intent` | `rook_agent` | `dictionary_envelope` |
| 9 | `RookAgent._execute_local_tool` | `plan_and_execute` | `rook_agent` | `dictionary_envelope` |
| 10 | `ChatRunner.run_turn` | `spawn_agent` | `rook_chat` | `rook_chat_protocol` |
| 11 | `rook.agent.plan_graph_live.apply_live_producer_node` | `gh_explore_workflow` | `plan_graph` | `plan_graph_refusal` |
| 12 | `BootstrapRunner.run_test` | `gh_replay_recipe` | `internal_handler` | `bootstrap_test_result` |
| 13 | `BootstrapRunner._mock_executor` | `gh_execute_intent` | `internal_handler` | `dictionary_envelope` |
| 14 | `bootstrap.HttpExecutor.execute` | `rhino_execute_intent` | `internal_handler` | `dictionary_envelope` |
| 15 | `bootstrap.create_mock_executor.callable` | `plan_and_execute` | `internal_handler` | `dictionary_envelope` |
| 16 | `learning.create_tool_executor.callable` | `spawn_agent` | `internal_handler` | `dictionary_envelope` |
| 17 | `Investigator.investigate_tool` | `gh_explore_workflow` | `internal_handler` | `investigation_result` |
| 18 | `Investigator.investigate_gap` | `gh_replay_recipe` | `internal_handler` | `investigation_result` |
| 19 | `Investigator.investigate_workflow` | `gh_execute_intent` | `internal_handler` | `investigation_result` |
| 20 | `Investigator._run_experiment` | `rhino_execute_intent` | `internal_handler` | `experiment_result` |
| 21 | `HybridInvestigator.investigate_tool` | `plan_and_execute` | `internal_handler` | `hybrid_investigation_result` |
| 22 | `HybridInvestigator.investigate_gap` | `spawn_agent` | `internal_handler` | `hybrid_investigation_result` |
| 23 | `LearningSession.run_investigation_cycle.tool_target` | `gh_explore_workflow` | `internal_handler` | `investigation_result` |
| 24 | `explorer.HttpExecutor.execute` | `gh_replay_recipe` | `internal_handler` | `explorer_execution_result` |
| 25 | `explorer.HttpExecutor.execute_sync` | `gh_execute_intent` | `internal_handler` | `explorer_execution_result` |
| 26 | `explorer.MockExecutor.execute` | `rhino_execute_intent` | `internal_handler` | `explorer_execution_result` |
| 27 | `explorer.MockExecutor.execute_sync` | `plan_and_execute` | `internal_handler` | `explorer_execution_result` |
| 28 | `server._handle_spawn_agent` | `spawn_agent` | `internal_handler` | `dictionary_envelope` |
| 29 | `server._handle_plan_and_execute` | `plan_and_execute` | `internal_handler` | `dictionary_envelope` |

The result adapters are also external literal expectations, never candidate-derived:

- `dictionary_envelope`: exact `dict` type and exact `success`/`data` keys with `success is False` and the literal expected denial.
- `rook_agent_protocol`: `_run_loop` returns `None`; history is exactly user, assistant tool call, one `role: tool` denial with the original call ID, then terminal assistant; the denial-only turn reports one call and no successful tools, tool start/end events, adaptation, observation, or failure-count entry.
- `rook_chat_protocol`: collect the async-generator event stream; conversation history has that same four-role causal sequence and exact denial, with no tool start/result or error event, no `tools_used`/surface adaptation, and no false meta-only/stuck diagnosis.
- `plan_graph_refusal`: exact `LiveProducerResult` with the original graph object unchanged, `applied is False`, requested node/tool, `outcome_status is None`, and `reason == "tool_lifecycle_denied"`.
- `bootstrap_test_result`: exact `TestResult` with `test_id == f"containment:{tool}"`, canonical tool, empty params/created IDs, `ExpectedOutcome.EITHER`, `TestOutcome.ERROR`, exact denial in `response`, code in `error_message`, zero duration, exact timestamp form, and unchanged `completed_tests`.
- `investigation_result`: exact `InvestigationResult` with canonical tool, exact denial in `containment_denial`, unresolved/default status, and empty discovery/experiment/insight collections.
- `experiment_result`: exact `ExperimentResult` with canonical tool, empty params, `success is False`, exact denial in `response`, code in `error`, `error_category == "unknown"`, and zero execution time.
- `hybrid_investigation_result`: exact `HybridInvestigationResult` with canonical tool, `success is False`, exact denial in `containment_denial`; all collection fields empty; diagnosis, selections, consolidation, workflow, reward, visual descriptions/hashes, gap, and resolution `None`; verification/gap booleans false; attempts/time zero; and serialized denial exact.
- `explorer_execution_result`: exact explorer `ExecutionResult` with canonical `tool_name`, empty params, `success is False`, exact denial in `response`, code in `error`, and zero duration.

Tests mutate each outer adapter independently and must reject a correct inner denial inside a wrong type, missing/wrong wrapper field, or malformed protocol transcript; generic `.response`/`.containment_denial` extraction is not acceptance. Row 23 constructs `LearningSession` with `use_hybrid=False` so its literal `investigation_result` adapter is deterministic. Each representative also verifies one adjacent event in the same PID/start token and zero tool validation, implementation, downstream or containment-triggered model, target, HTTP, host, observation, adaptation, or receipt entry. `RookAgent._run_loop` and `ChatRunner.run_turn` use separate bounded primary-model stubs with exactly two calls: the upstream response containing the denied tool call, then the permitted terminal continuation. The other 27 representatives require zero primary-model calls. All 29 require zero downstream/dormant model calls.

### Release-only file placement

Release proof lives only in:

- `scripts/containment_release/__init__.py`
- `scripts/containment_release/installed_probe.py`
- `scripts/containment_release/live_gate.py`
- `scripts/containment_release/fixtures/containment_empty.ghx`
- `scripts/run-containment-release-acceptance.ps1`

The coordinator copies only the four literal release-tool files listed above (`__init__.py`, both Python scripts, and the GHX fixture) into matching paths in its fresh diagnostics directory before installation. Installed-Python probes execute that copy, with a fresh working directory, so the checkout/worktree is absent from effective `sys.path`. It never recursively copies cache residue. None of these files is copied into the Rook installer or wheel.

---

## Task 1: Add the thin external installed-runtime probe

**Files:**

- Create: `scripts/containment_release/__init__.py`
- Create: `scripts/containment_release/installed_probe.py`
- Create: `scripts/tests/test_containment_release_probe.py`

- [ ] Run the Task Shell block.

- [ ] Write `test_containment_release_probe.py` first. Import the script package from `scripts/`, and fail with `EXPECTED_RED:containment-release-probe:missing` while the new module is absent. Then pin tests for:

  - the literal six-entry `EXPECTED_DENIALS` oracle, including exact dispositions and recovery strings, with no candidate helper/manifest input;
  - mutation rejection for wrong/missing/extra payload fields, tool, disposition, recovery, retryability, verification flag, and telemetry timestamp format;
  - the six tools and four discovery snapshots, including the unprofiled child's absent profile variable and reported `profile_env_present: false`;
  - all six names absent from every catalog and actual RookAgent/RookChat model projection, zero discovery telemetry, and rejection of a wrong-member/right-count catalog or projection;
  - the installed normal startup-refresh helper retaining a safely revalidated gate-owned cache on refresh failure without unlinking or recursively deleting it;
  - exactly 36 unique transport tuples and no candidate-supplied matrix override;
  - the exact ordered 29-row table above, unique seam names, all six representatives present, exact origins, and literal result adapters;
  - stable public denial formatting plus exact outer type/field/protocol validation for every internal adapter, including mutation rejection when only the inner denial is correct;
  - adjacent telemetry, same PID/start token, and zero downstream-spy evidence;
  - the real installed MCP process boundary: `stdio_client`/`ClientSession` in the parent and the public `stdio_server`/`call_tool` handler in the child, never in-process dispatch;
  - RookAgent and RookChat protocol assertions plus exact two-call upstream-primary-model counters inside their two loop records, zero primary-model calls for the other 27, and zero downstream/dormant model calls for all 29;
  - rejection of missing, duplicate, extra, reordered, or malformed 36/29 records;
  - case-insensitive installed-child environment scrubbing;
  - source/worktree-free `sys.path` and all loaded `rook.*` origins under the installed package root;
  - packaged/installed runtime-manifest byte equality, install-state manifest identity, wheel hashes, wheel `RECORD`, and installed Rook file matching; and
  - atomic output: a failed probe cannot leave a passing JSON result.

- [ ] Run the focused pytest and prove the intended red, not an import/collection/parser failure:

```powershell
Invoke-ExpectedPytestRed `
  -Path 'scripts/tests/test_containment_release_probe.py' `
  -Marker 'EXPECTED_RED:containment-release-probe:missing' `
  -JunitPath '.pytest_tmp/containment-release-probe-red.xml'
```

Expected: exit `1` with `EXPECTED_RED:containment-release-probe:missing` and zero JUnit errors.

- [ ] Implement `installed_probe.py` as one campaign-specific script. It may extract the necessary process/spy mechanics from the current `rook.containment_acceptance` module, but it must not import that module, use candidate lifecycle helpers as an expected-value oracle, retain generic `.response`/`.containment_denial` extraction, or preserve its 164-call matrix/general artifact-validation layers.

The script exposes these code-owned interfaces:

```python
def build_installed_child_environment(base: Mapping[str, str], *, profile: str | None = None, interactive: bool = False) -> dict[str, str]: ...
def validate_installed_runtime(inputs: RuntimeInputs) -> dict[str, object]: ...
def run_discovery_snapshots(inputs: RuntimeInputs) -> list[dict[str, object]]: ...
def run_transport_probes(inputs: RuntimeInputs) -> list[dict[str, object]]: ...
def run_internal_probes(inputs: RuntimeInputs) -> list[dict[str, object]]: ...
def run_all(inputs: RuntimeInputs, output_path: Path) -> dict[str, object]: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

`RuntimeInputs` is a small frozen dataclass containing only expected release SHA/version, expected installed Python/venv/package roots, packaged and installed runtime manifests, install state, packaged wheelhouse, forbidden source roots, and staged script path. Output ownership is exclusively the separate `run_all(..., output_path)`/CLI argument; do not also store it in `RuntimeInputs`. Do not add a general probe registry or plugin system.

The top-level CLI is:

```text
installed_probe.py run
  --expected-release-sha <40-hex>
  --expected-version <X.Y.Z>
  --expected-python <absolute installed venv python>
  --expected-venv <absolute installed venv>
  --expected-package-root <absolute installed site-packages/rook>
  --packaged-runtime-manifest <absolute file>
  --installed-runtime-manifest <absolute file>
  --install-state <absolute file>
  --packaged-wheelhouse <absolute directory>
  --forbidden-source-root <absolute path> [repeatable]
  --output <new absolute JSON file>
```

The script internally launches fresh installed-Python children for unprofiled, lean, readonly, and interactive-full discovery, real MCP transport, and representative internal probing. It does not accept seam/tool/origin assignments from the caller. Every child:

- removes inherited `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`, `DSPY_CACHEDIR`, `CHIRP_HOME`, and all `ROOK_*` keys case-insensitively;
- sets code-owned `PYTHONNOUSERSITE=1`, validated installed values for `ROOK_INSTALL_ROOT`, `ROOK_DATA_DIR`, `ROOK_MODE=release`, and `ROOK_DSPY_RESTRICT_PICKLE=1`, a validated code-owned `DSPY_CACHEDIR`, optional code-owned `CHIRP_HOME`, and only the exact profile/interactive controls needed for that child. Discovery `unprofiled` sets neither profile nor interactive control; discovery `interactive-full` sets `ROOK_MCP_TOOL_PROFILE=full` and `ROOK_ENABLE_INTERACTIVE_COMMAND_LEARNING=1`; discovery lean/readonly and all transport children set only their explicit profile;
- uses a fresh working directory outside the checkout, install roots, and gallery; and
- reports `sys.executable`, `sys.path`, loaded module origins, PID, and process start token before proof is accepted.

The private child protocol is also fixed. The parent invokes the same staged script only as:

```text
installed_probe.py _child-discovery --surface <unprofiled|interactive-full|lean|readonly> --output <new JSON>
installed_probe.py _child-transport --profile <full|lean|readonly> --output <new JSON>
installed_probe.py _child-internal --probe-index <1..29> --output <new JSON>
```

For transport, the parent uses the installed MCP SDK's `mcp.client.stdio.stdio_client` and `ClientSession` to launch the staged `_child-transport` command. The child runs the installed public `mcp.server.stdio.stdio_server` and the real Rook `call_tool` request handler. Child stdout is reserved exclusively for MCP JSON-RPC; no evidence or diagnostics are printed there. The parent sends the exact twelve ordered calls (`6 tools x 2 ingresses`) and validates every wire response. The server child accumulates its own adjacent telemetry and downstream-spy snapshots, then writes one atomic canonical evidence object to the fresh output file only after protocol completion. That artifact file is the sole non-protocol result/evidence channel; stderr is diagnostics-only and any traceback fails the probe. An in-process substitute is forbidden and tested.

Each internal child reads its literal row by one-based index; it does not accept a seam, tool, origin, or result-adapter string. Discovery and internal children likewise write one canonical JSON object to the new output file and expose no other machine-readable channel. The parent requires every child exit zero, rejects a missing/pre-existing/reparse output, parses once, validates the exact mode-specific shape and PID/start-token identity, and only then aggregates it. No child may import candidate-provided expected denials, probe configuration, or result-adapter expectations.

Every discovery child snapshots the containment ring before startup refresh/catalog/projection work and after it, requiring exact equality and the same PID/start token. It records the full catalog name set plus the actual final `RookAgent._get_tool_schemas()` and `ChatRunner._active_schemas()` name sets; count-only evidence is invalid. Within the unprofiled child only, create a gate-owned cache containing one admitted record, one record hidden by a contained mapping key, and one record hidden by an embedded contained `function.name`. Invoke the installed `refresh_catalog_at_startup` helper with injected construction failure; require `status == "degraded_cache"`, `persisted is False`, `refresh_requested is True`, only the safely revalidated admitted record in memory, raw cache bytes/path unchanged, zero telemetry, and zero unlink/rmtree calls for that path. Then invoke the same installed startup helper with the normal `_all_live_tools` loader on that gate-owned path and require a nonempty lifecycle-filtered outcome before collecting catalog/projection evidence. The subprobe exercises the real startup-refresh implementation without reading, test-seeding, deleting, or replacing the user's default catalog cache.

Use the current focused spy patchpoints already proven by the old harness, including both `httpx` and bootstrap's module-local `urllib.request.urlopen`. Construct both bootstrap and explorer `HttpExecutor` probes with the explicit inert base URL `http://127.0.0.1:9`; construction itself may not perform discovery. Invoke explorer `execute_sync` probes from the child's top-level synchronous path, outside any active event loop. Test both mechanics so setup cannot reach a target/network or fail before the lifecycle guard. Keep only spies necessary to establish zero downstream entry for the 36 and 29 approved records.

The successful output is one canonical JSON object with exactly these top-level keys:

```text
schema_version, success, runtime, discovery, transport, internal
```

`success` is true only for 4 exact discovery snapshots, 36 exact transport records, and 29 exact internal records. Write through a same-directory temporary file and `os.replace`; never emit a passing result after any failure.

- [ ] Run focused green verification:

```powershell
& $Python -m pytest scripts/tests/test_containment_release_probe.py -q
if ($LASTEXITCODE -ne 0) { throw 'Installed containment probe tests failed' }
& $Python -m py_compile scripts/containment_release/installed_probe.py
if ($LASTEXITCODE -ne 0) { throw 'Installed containment probe compile failed' }
```

Expected: both exit `0`.

- [ ] Stage exactly the three Task 1 files, run the staged allowlist comparison, and commit:

```powershell
$Expected = @(
  'scripts/containment_release/__init__.py',
  'scripts/containment_release/installed_probe.py',
  'scripts/tests/test_containment_release_probe.py'
)
Stage-ExactFiles -Paths $Expected
git commit -m "test(release): add thin installed containment probe"
if ($LASTEXITCODE -ne 0) { throw 'Task 1 commit failed' }
```

- [ ] Obtain fresh spec-compliance and code-quality reviews; fix and re-review before Task 2.

---

## Task 2: Add the external paired live-preservation gate

**Files:**

- Modify: `.gitattributes`
- Create: `scripts/containment_release/live_gate.py`
- Create: `scripts/containment_release/fixtures/containment_empty.ghx`
- Create: `scripts/tests/test_containment_release_live_gate.py`

- [ ] Run the Task Shell block.

- [ ] Write the new tests first and require `EXPECTED_RED:containment-release-live:missing`. Pin:

  - fixture size `2708`, UTF-8/no BOM/LF/one final LF, and SHA-256 `2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df`;
  - exactly two scenarios, `rhino` and `grasshopper`;
  - read-only preflight before authorization and no mutation before the exact authorization response;
  - a fresh gate-owned target and fresh authorization for every scenario/rerun;
  - admitted-tool allowlists only and exact argument contracts;
  - Rhino radius-4 named sphere plus marked scripted point, observed geometry/identity, deletion of only owned objects, exact declared restoration, and prior active-document restoration;
  - Grasshopper exact Sphere GUID `dabc854d-f50e-408a-b001-d043c7de151d`, one Number Slider with range `1..9` and value `4`, wire `T1.O0>T2.I1`, solve/output/topology/error verification, bounded `gh_undo`, scratch disposal, and prior definition/canvas restoration;
  - zero containment-ring delta in every participating process;
  - exact installed Python/package origins and source/worktree-free `sys.path` before host launch;
  - stop-forward-work semantics, restoration only while ownership is certain, and no force-kill;
  - no contained tool or dormant implementation call; and
  - one small atomic scenario result, with no generic artifact schema/lease registry.

- [ ] Run the intended red:

```powershell
Invoke-ExpectedPytestRed `
  -Path 'scripts/tests/test_containment_release_live_gate.py' `
  -Marker 'EXPECTED_RED:containment-release-live:missing' `
  -JunitPath '.pytest_tmp/containment-release-live-red.xml'
```

Expected: exit `1` with the exact marker and zero JUnit errors.

- [ ] Add the new fixture by copying the exact existing bytes, not by regenerating GHX XML. Add both fixture paths temporarily to `.gitattributes` as `-text`; Task 5 removes the old package path after the package harness is deleted. Verify size and digest immediately.

- [ ] Implement `live_gate.py` by extracting only the approved scenario behavior from the current `rook.containment_live_gate`. Do not carry forward Windows path leases, retained-lease registries, generalized artifact claims, nested generic evidence validators, immutable sidecars, or forced process cleanup.

The external script exposes:

```python
def run_rhino_scenario(inputs: ScenarioInputs) -> dict[str, object]: ...
def run_grasshopper_scenario(inputs: ScenarioInputs) -> dict[str, object]: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

The CLI is:

```text
live_gate.py run
  --scenario <rhino|grasshopper>
  --rhino-exe <absolute Rhino 8 executable>
  --expected-python <absolute installed venv python>
  --expected-package-root <absolute installed site-packages/rook>
  --forbidden-source-root <absolute path> [repeatable]
  --output <new absolute JSON file>
```

The staged fixture is resolved relative to `live_gate.py`. Before host launch, the script requires its exact installed interpreter, source-free `sys.path`, and every loaded `rook.*` module beneath the expected installed package root. It then launches a fresh gate-owned Rhino process, validates its discovery record and PID/start token, performs read-only preflight, prints a complete authorization challenge, and requires the operator to echo that exact challenge. Authorization names the scratch target, bounded mutation/verification sequence, and restoration method. It never carries to another scenario or rerun.

Use only the existing admitted calls:

- Rhino: `rhino_ping`, `rhino_document`, `rhino_objects`, `rhino_geometry`, `rhino_document_ops`, `rhino_create`, `rhino_execute`, `rhino_delete`.
- Grasshopper: `rhino_ping`, `rhino_document`, `rhino_command`, `gh_status`, `gh_document_open`, `gh_library`, `gh_snapshot`, `gh_edit`, `gh_errors`, `gh_undo`.

On failure, stop forward mutation. If target ownership is still certain, use only the already-authorized restoration sequence. If ownership is ambiguous, do not mutate again; return `manual_restoration_required`. A pass requires observed restoration and zero containment telemetry. Gracefully close only the gate-owned Rhino process; never force-kill it.

The successful scenario JSON has exactly:

```text
schema_version, scenario, success, run_id, target, authorization,
pre_state, operations, verification, restoration, telemetry, diagnostics
```

- [ ] Run focused green verification:

```powershell
& $Python -m pytest scripts/tests/test_containment_release_live_gate.py -q
if ($LASTEXITCODE -ne 0) { throw 'Live gate tests failed' }
& $Python -m py_compile scripts/containment_release/live_gate.py
if ($LASTEXITCODE -ne 0) { throw 'Live gate compile failed' }
$Fixture = Get-Item 'scripts/containment_release/fixtures/containment_empty.ghx'
if ($Fixture.Length -ne 2708) { throw 'Fixture size drift' }
if ((Get-FileHash -LiteralPath $Fixture.FullName -Algorithm SHA256).Hash.ToLowerInvariant() -ne '2def4c0009b3b41de681fe23880f741189c0119820260a35a48f048d2b8830df') { throw 'Fixture digest drift' }
```

- [ ] Stage exactly the four Task 2 files, verify the allowlist, and commit:

```powershell
$Expected = @(
  '.gitattributes',
  'scripts/containment_release/fixtures/containment_empty.ghx',
  'scripts/containment_release/live_gate.py',
  'scripts/tests/test_containment_release_live_gate.py'
)
Stage-ExactFiles -Paths $Expected
git commit -m "test(release): add thin live containment gate"
if ($LASTEXITCODE -ne 0) { throw 'Task 2 commit failed' }
```

- [ ] Obtain fresh spec-compliance and code-quality reviews; fix and re-review before Task 3.

---

## Task 3: Add the thin normal-release coordinator and gallery guard

**Files:**

- Create: `scripts/run-containment-release-acceptance.ps1`
- Create: `scripts/tests/containment-release-acceptance.tests.ps1`

**Responsibility:** Task 3 sequences existing release components. It does not recreate their validation and does not implement Task 4 withdrawal.

- [ ] Run the Task Shell block. Do not call `Resolve-PinnedPrivatePythonFixtureSource` or `Resolve-PinnedInnoCompiler`; Task 3 has no private-CPython or Inno dependency.

- [ ] Write `containment-release-acceptance.tests.ps1` first. It begins with `Set-StrictMode -Version Latest` and `$ErrorActionPreference = 'Stop'`, fails with `EXPECTED_RED:containment-release-coordinator:missing` while the coordinator is absent, and uses only synthetic directories plus injected fake child results. Pin these behaviors:

  - the coordinator and its test are the only Task 3 files, and the production script remains below 1,000 lines;
  - a new absolute output directory is required outside `%LOCALAPPDATA%\Rook\app`, `python`, `venv`, `data`, and `%APPDATA%\Rook\artifacts`;
  - existing Rook processes are checked with `installer/rook_process_preflight.ps1 -Mode enumerate`, and direct exact-name checks reject running Rhino or Revit;
  - the gallery baseline records relative path, entry type, and file size without reading file contents or following reparses;
  - the immediate pre-install uninstaller inventory records only case-insensitive `unins*.exe`, `unins*.dat`, and `unins*.msg` entries beneath `%LOCALAPPDATA%\Rook\app` for Task 4;
  - the installer is invoked once with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /TYPE=full`, a scrubbed Python/Rook environment, and its actual exit code is checked;
  - exact gallery equality is required after installation while processes remain quiescent;
  - the coordinator prints one run-bound operator continuation/abort token but does not create or own a smoke shell;
  - `validate-release-artifacts.ps1` receives the exact expected SHA, version, installer, smoke manifest, output manifest, build timestamp, and existing FFmpeg manifest; its exit code is authoritative and its schema logic is not reproduced;
  - exactly `__init__.py`, `installed_probe.py`, `live_gate.py`, and `fixtures/containment_empty.ghx` are copied to `<output>/tooling`, byte-compared, and used for later calls;
  - `installed_probe.py` runs once, then `live_gate.py` runs once for `rhino` and once for `grasshopper`, in that order, with separate gate-owned authorization handled by `live_gate.py`;
  - the approved live-gallery comparison runs after the existing smoke workflow and after each live scenario;
  - a failing fake child stops all later calls and never writes a passing record;
  - a failure after the installer starts writes one small atomic failure record with `withdrawal_required: true` and the captured pre-existing-uninstaller inventory, but performs no uninstall, deletion, configuration cleanup, or repair; and
  - only a complete ordered success writes one small atomic success record with the three recomputed file digests.

The tests dot-source the coordinator with synthetic required arguments and call its private core through one coordinator-local injected hook table for process preflight, child launch, and operator input. The public `-File` path does not accept hooks or test paths. Synthetic tests create fake installer, smoke, release, probe, and live result files; they do not invoke an installer, Rhino, Inno, CPython staging, the real validator, or any user-owned path.

- [ ] Run the intended red under Windows PowerShell 5.1:

```powershell
Invoke-ExpectedPowerShellRed `
  -Path 'scripts\tests\containment-release-acceptance.tests.ps1' `
  -Marker 'EXPECTED_RED:containment-release-coordinator:missing'
```

Expected: exit `1` with the exact marker, not `ParserError`, a missing test dependency, or a live-process failure.

- [ ] Implement `scripts/run-containment-release-acceptance.ps1` as a sequencing-only script. Its first executable statements after `param(...)` are:

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
```

Its public parameters remain limited to:

```text
-ExpectedReleaseSha <40-hex>
-Version <X.Y.Z>
-BuildStartedAt <normal-build UTC/offset ISO-8601 timestamp>
-InstallerPath <absolute existing EXE>
-SmokeManifestPath <absolute expected JSON path>
-ReleaseManifestPath <absolute expected JSON path>
-RhinoExe <absolute Rhino 8 executable>
-OutputDirectory <absolute path that does not yet exist>
```

Derive the repository root from `$PSScriptRoot` and runtime/gallery paths from Windows known folders. Do not accept caller-supplied install, gallery, deletion, probe-matrix, or tool paths. Keep all coordinator helpers in this file; do not add a third implementation file or a reusable validation/process framework.

- [ ] Implement this exact ordered flow:

1. Validate scalar arguments and create the fresh output directory outside the five protected roots above.
2. Run the existing read-only Rook process preflight and direct Rhino/Revit name check. A nonquiet result stops before installation.
3. Capture the gallery path/type/size baseline and the small immediate-entry uninstaller inventory.
4. Launch the ordinary installer through `System.Diagnostics.ProcessStartInfo` with `UseShellExecute = false`, the fixed arguments above, and an environment formed by removing `PYTHONPATH`, `PYTHONHOME`, `PYTHONUSERBASE`, `PYTHONNOUSERSITE`, `DSPY_MODEL`, `DSPY_CACHEDIR`, `CHIRP_HOME`, and every `ROOK_*` key case-insensitively, then setting only `PYTHONNOUSERSITE=1`. Wait for the launched process and require exit `0`.
5. Re-run the read-only quiescence check and require exact gallery equality with the pre-install baseline.
6. Print `READY_FOR_NORMAL_RELEASE_SMOKE <run-id>`. The operator runs the existing Rhino/Revit smoke workflow outside the coordinator, closes those hosts, then enters exactly `CONTINUE_AFTER_NORMAL_RELEASE_SMOKE <run-id>` or `ABORT_NORMAL_RELEASE_SMOKE <run-id>`. The coordinator creates no shell and runs no smoke implementation.
7. On continue, require fresh quiescence and the smoke manifest, apply the approved live-gallery comparison, then invoke unchanged `scripts/validate-release-artifacts.ps1` with `-Version`, `-RepoRoot`, `-GitSha`, `-InstallerPath`, the code-owned FFmpeg source-bundle manifest, `-SmokeManifestPath`, `-OutputManifestPath`, `-BuildStartedAt`, and `-RequireInstallerNewerThanScript`. Require exit `0`; do not parse or reproduce its release-validation schema.
8. Copy and byte-compare only the four containment release files into `<output>/tooling` with their relative layout. Invoke only those copies.
9. Run the installed venv Python with staged `installed_probe.py run` and its existing fixed CLI. Derive `%LOCALAPPDATA%\Rook\app`, `data`, `venv`, installed `site-packages\rook`, installed/packaged runtime manifests, install state, and packaged wheelhouse from known folders and the repository. Require exit `0` and `success: true`.
10. Run staged `live_gate.py run --scenario rhino` with its existing fixed CLI; require exit `0`, `success: true`, and then the approved live-gallery comparison.
11. Run staged `live_gate.py run --scenario grasshopper` with a new output path and its existing fixed CLI; require exit `0`, `success: true`, and then the approved live-gallery comparison.
12. Recompute SHA-256 for the installer, smoke manifest, and release manifest. Write `<output>/containment-release-acceptance.json` by same-directory temporary file plus atomic rename only after every preceding step succeeds.

The success record has only:

```text
schema_version, success, expected_release_sha, version, installer_sha256,
smoke_manifest_sha256, release_manifest_sha256, installed_probe,
rhino_scenario, grasshopper_scenario, gallery, completed_utc
```

The three evidence fields contain only relative output paths, SHA-256 values, and pass/count summaries. They do not copy probe records or user content.

If any failure occurs after the installer process was successfully started, stop forward work and atomically write `<output>/containment-release-failure.json` with only:

```text
schema_version, success, stage, withdrawal_required, installer_exit_code,
preexisting_uninstaller, message, failed_utc
```

Set `success: false` and `withdrawal_required: true`. Do not invoke an uninstaller, remove files, edit configuration, repair the gallery, restore an older build, or write a passing record. Task 4 owns withdrawal.

Task 3 explicitly excludes private-CPython fixtures, Inno compilation, user-site or Claude tripwires, TEMP-clone/process-watch logic, a generalized uninstall mutation map, coordinator-owned smoke shells, duplicate wheel/`RECORD`/runtime-manifest/release-schema validation, fallback deletion, configuration repair, and hostile-workstation certification.

The live-gallery comparison is fixed and local, not delegated to a new validator:

- never follow a reparse point;
- exclude only pre-existing `*.deleting.tmp` trees and empty GUID directories from the baseline;
- require every other pre-existing path to remain present with the same entry type;
- require every pre-existing non-`manifest.json` file to retain its size;
- allow a pre-existing `manifest.json` to change size;
- allow new `poster.jpg`, `start_frame.jpg`, or `end_frame.jpg` files only directly beneath a pre-existing finalized `{YYYY-MM-DD}/{uuid}` artifact directory whose regular `manifest.json` existed in the baseline;
- allow no new directories or other new files; and
- on mismatch, report `artifact_preservation_failed`, stop forward work, and perform no gallery repair.

- [ ] Run focused green verification and PS5.1 parsing:

```powershell
& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -Command "[void][scriptblock]::Create((Get-Content -LiteralPath 'scripts\run-containment-release-acceptance.ps1' -Raw))"
if ($LASTEXITCODE -ne 0) { throw 'Coordinator parse failed' }
& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\containment-release-acceptance.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Coordinator tests failed' }
$CoordinatorLines = @(Get-Content -LiteralPath 'scripts\run-containment-release-acceptance.ps1').Count
if ($CoordinatorLines -ge 1000) { throw "Coordinator exceeded the KISS limit: $CoordinatorLines lines" }
```

- [ ] Stage exactly the two Task 3 files, verify the allowlist, and commit:

```powershell
$Expected = @(
  'scripts/run-containment-release-acceptance.ps1',
  'scripts/tests/containment-release-acceptance.tests.ps1'
)
Stage-ExactFiles -Paths $Expected
git commit -m "test(release): add thin containment coordinator"
if ($LASTEXITCODE -ne 0) { throw 'Task 3 commit failed' }
```

- [ ] Task 3 closes after the focused offline verification and exact two-file commit. Do not initiate an open-ended implementation review. The one final whole-branch verification remains Task 7.

---
## Task 4: Migrate legacy uninstall authority and add bounded withdrawal

**Files:**

- Modify: `installer/RookSetup.iss`
- Modify: `scripts/run-containment-release-acceptance.ps1`
- Modify: `scripts/tests/containment-release-acceptance.tests.ps1`

- [ ] Run the Task Shell block.

- [ ] Extend the existing PowerShell test first. The fixture-generator reads only `UninstallLogMode` assignments from the production `RookSetup.iss` `[Setup]` section: absent means omit it from the candidate fixture and exercise default append; exactly one raw `UninstallLogMode=overwrite` line is projected verbatim; any other value, duplicate, malformed placement, or hardcoded independent fixture mode is infrastructure failure. Add these tests before editing `RookSetup.iss`:

  - resolve the mandatory `-IsccPath` only to the normal-release `C:\Program Files (x86)\Inno Setup 6\ISCC.exe`, reject missing/reparse/wrong-version input, and compile with no PATH lookup or skip;
  - generate one disposable Inno Setup 6 legacy/candidate fixture pair beneath a canonical non-reparse GUID root under the real known-folder LocalAppData `Temp`; use one fresh synthetic AppId shared only by those two versions, require it to differ from Rook's public `{{E9A3F2B1-4C5D-6E7F-8A9B-0C1D2E3F4A5B}` source identity, and give both versions identical literal `DefaultDirName`, `UninstallFilesDir`, `PrivilegesRequired=lowest`, x64 mode, and `UsePreviousAppDir=no` values;
  - permit no real Rook GUID/path, Inno known-folder constant, `[Registry]`, `[Icons]`, `[Run]`, plugin registration, or caller-selected destination in generated source. Use compile-time absolute synthetic paths. Snapshot the real Rook uninstall key before/after without mutation; inspect the unique fixture HKCU uninstall identity in both registry views and require no matching HKLM key;
  - put the control and preservation sentinels in one ordinary non-reparse sibling root outside every candidate application/runtime/configuration/Temp/setup/uninstall/`post_install.py` target. Statically prove only the legacy fixture's exact unsafe recursive-delete entry names it, and delay final test-root teardown until every assertion completes;
  - legacy positive control: install the compiled legacy fixture, create a byte-pinned control sentinel, run its ordinary real Inno uninstaller, and require sentinel deletion plus removal of the synthetic registry/app-root uninstaller authority;
  - overwrite proof: reinstall that same compiled legacy fixture, create a distinct byte-pinned preservation sentinel, record the coherent `unins000.exe`/`unins000.dat` state, install the generated candidate over the same eligible identity, require candidate `DisplayVersion`/registered uninstall path, a changed synthetic `.dat` digest, exactly one current app-root uninstaller/log set and no `unins001*`, then run ordinary candidate uninstall and require exact preservation plus no fixture registry/app-root authority;
  - launch both fixture uninstallers through the real bounded `ManagementEventWatcher` path described below, never an injected record or Python parent substitute, and require the actual original-to-TEMP-clone identities and completion barriers;
  - copy and byte-verify the pinned CPython 3.11.9 runtime plus the unchanged real `post_install.py`, `process_rebuild_guard.py`, and `python_runtime_install.py`; both compiled fixture installers must lay down fresh byte-identical copies of all three scripts plus `python_path.txt` on every install/reinstall, with that file selecting only the copied interpreter, so the first uninstall cannot consume the second cycle's payload;
  - construct every fixture installer/uninstaller/private-Python environment case-insensitively: remove the complete source/model/cache/`ROOK_*` set, all profile/AppData/home/temp variables, `PATH`, and `NoDefaultCurrentDirectoryInExePath`; re-add only the synthetic profile/AppData/LocalAppData/home-drive/home-path values, a test-owned Temp child beneath validated real LocalAppData `Temp`, code-owned `PYTHONNOUSERSITE=1`, present-but-empty `PATH`, and `NoDefaultCurrentDirectoryInExePath=1`; keep `HOME` absent;
  - before unchanged `post_install.py --uninstall` continues, its test-only startup guard must require `Path.home()`, `get_runtime_root()`, `APPDATA`, `tempfile.gettempdir()`, `sys.executable`, cwd, and every touched runtime/config destination to remain under canonical ordinary non-reparse synthetic roots; mismatch exits before lookup or cleanup;
  - positively fire the copied-runtime `claude.exe`/`sitecustomize.py` tripwire, require exit `97`, clear its external marker, then require zero hits and `shutil.which("claude") is None` through the real uninstall chains; and
  - on fixture failure, stop forward work, terminate only recorded fixture PID/creation identities, and remove only the exact synthetic key/root after revalidating the key's values plus every root descendant without following reparses. Ambiguity retains the fixture and reports its exact manual-cleanup identity; no real Rook uninstaller, runtime, config, registry, or gallery state is mutated. Do not require delayed Inno TEMP self-delete residue to disappear; and
  - withhold every migration expected-red/PASS marker until the cycle's observer/environment assertions, original/clone/private-Python completion, registry/app-root checks, and exact fixture teardown have all succeeded. Cleanup ambiguity or failure emits no expected marker and is infrastructure failure even if the semantic assertion already failed as expected.

- [ ] Add the remaining failing tests with `EXPECTED_RED:containment-release-withdrawal:bounded` for:

  - every `pre_install` failure leaving a seeded existing runtime/config untouched with zero uninstaller, fallback, configuration, or startup-authority mutation calls;
  - each pre-existing immediate `unins*.exe`, `unins*.dat`, or `unins*.msg` match—including mixed-case names and combinations—remaining a sticky `manual_withdrawal_required` disqualifier after candidate overwrite or removal, with zero uninstaller, fallback, configuration, or startup-authority mutation calls;
  - automatic normal-uninstaller admission only for an empty baseline followed, after the exact candidate process exits, by ordinary non-reparse `unins000.exe` plus `unins000.dat`, optionally the same-stem `unins000.msg`, and no other matching entry; missing pairs, extra stems or matches, mismatched message names, directories, reparses, inspection failure, or immediate prelaunch path/type/size drift must fail manual with zero destructive calls, and spies must prove no uninstall-log content is read or parsed;
  - `installer_started` only after a returned handle plus PID/creation identity, and `verified_partial_installation` only after an observed nonzero exit from that same identity; filesystem residue, missing identity, or unobservable exit status never qualifies;
  - an attempted launch without verified identity returning `manual_withdrawal_required` with zero destructive calls;
  - no destructive action until the operator closes Rhino, Revit, Claude, Codex, and other configured Rook launchers;
  - graceful close only for a gate-owned host and PID plus creation-identity matching for any candidate process the coordinator stops;
  - no force-kill of a user host;
  - ambiguous ownership, enumeration, or closure returning failed/manual withdrawal without deletion;
  - normal Inno uninstaller first, only after uninstall-state admission, with exact silent arguments, synchronous original exit-code inspection, and no false success from exit zero alone;
  - a bounded process-start observer active before uninstaller launch admitting exactly one new direct child of the recorded original identity, attaching a live handle only when its creation does not predate the parent and its canonical ordinary non-reparse executable is strictly beneath the validated known-folder-derived Temp root, then requiring that exact TEMP-clone identity to exit before post-withdrawal checks or fallback;
  - the generated legacy/candidate Inno regression above as the sole real-process green control, with no injected observer records or substitute parent. Give each uninstall cycle a fresh nonce and distinct ready, release, observation, and completion paths outside every deletion target. Before `post_install.py` continues, `sitecustomize.py` atomically writes a ready record containing that nonce plus its PID, `os.getppid()`, and its own Windows process-start identity obtained through stdlib `ctypes`, then waits on only its cycle's release path with a hard timeout. The private test hook runs only after the live watcher has attached and validated the actual Inno TEMP clone; it waits for and validates the ready record, attaches the exact private-Python PID/start identity, requires that Python's PPID equal the attached clone PID, and only then atomically creates the release marker. Register a test-only `atexit` completion record and retain the Python handle; require the environment observation, normal Python completion, original exit observation, and exact clone completion before advancing;
  - zero, multiple, wrong-parent, pre-parent, outside-Temp, reparse, unattachable, PID-reused, lost-before-handle, enumeration/observer-error, capture-timeout, and exit-timeout clone cases returning `manual_withdrawal_required` with no further destructive calls; a green Rook-root process preflight while the clone remains alive must not advance the state;
  - a successful install requiring `{app}\python_path.txt` to be an ordinary non-reparse file with exactly the code-owned `%LOCALAPPDATA%\Rook\python\cpython-3.11.9\python.exe` effective value; only `verified_partial_installation` may omit it and use Inno's same fixed fallback, while alternate values, extra effective lines, or any path ambiguity return `manual_withdrawal_required` before uninstaller or fallback mutation and never probe the alternate target;
  - the production uninstaller and the real synthetic Inno fixture both proving that private-Python `post_install.py --uninstall` receives the complete scrubbed environment, code-owned `PYTHONNOUSERSITE=1`, and pinned profile/AppData/temp authority, with hostile inherited paths unable to redirect cleanup;
  - hostile `claude.exe` tripwires first on inherited `PATH`, in the former working directory, and in the actual private-Python effective working directory receiving zero execution attempts. Inside the real fixture's private-CPython child, assert exactly one case-insensitive `PATH` entry equal to `""`, exactly one `NoDefaultCurrentDirectoryInExePath` entry equal to `"1"`, canonical `sys.executable` equality with the copied interpreter, canonical cwd equality with that interpreter's parent and inequality with the gate-owned uninstaller cwd/former cwd, presence of the cwd tripwire, and `shutil.which("claude") is None`; keep observation/hit markers outside every uninstall deletion root, require the controlled marker to remain absent, and prove the unchanged direct JSON/TOML cleanup removes only seeded synthetic `rook` entries;
  - exact equality between the pinned 11-name Codex payload and the current curated installer source, no packaged or installed Claude source payload, exact 11-name installed Codex source after a successful install, and an absent/allowlisted-subset Codex source accepted only under `verified_partial_installation`;
  - ancestor/descendant no-reparse preflight across every affected normal-uninstaller destination before launch, with a Claude source tree, unknown Codex source child, or other source drift failing manual rather than broadening the map;
  - four and only four fallback roots derived from Windows known folders;
  - every component below the known-folder anchor and every traversed descendant checked for reparse attributes without following them;
  - exact canonical-root identity and no caller/candidate/manifest-supplied deletion path;
  - parent Rook directories, gallery, persistent data, and all non-allowlisted paths categorically excluded;
  - exact quiesced pre/post-withdrawal gallery inventory plus exact sentinel bytes;
  - removal/absence of configured MCP, RookChat, internal-agent, native-plugin, and managed-plugin startup authority; and
  - fresh post-uninstaller and post-fallback process enumeration, including races that introduce a process after either cleanup phase, always yielding manual withdrawal; and
  - no durable hold, quarantine receipt, rollback record, or restoration of an earlier build.

- [ ] Run the new observer/withdrawal tests before any production edit. This first red proves that the private production observer/invocation seam does not exist yet; it runs before the fixture and may not be satisfied by a parser/path/compiler failure:

```powershell
$BasePython = Resolve-PinnedPrivatePythonFixtureSource
$IsccPath = Resolve-PinnedInnoCompiler
Invoke-ExpectedPowerShellRed `
  -Path 'scripts\tests\containment-release-acceptance.tests.ps1' `
  -Marker 'EXPECTED_RED:containment-release-withdrawal:observer-missing' `
  -Arguments @('-PrivatePythonPath', $BasePython, '-IsccPath', $IsccPath)
```

- [ ] Implement only the coordinator-local bounded uninstaller invocation and TEMP-clone observer needed by both production withdrawal and the real fixture. It receives only already-validated internal path/environment values, is not a public or CLI seam, starts the watcher before `Process.Start`, attaches the exact child handle, enforces the parent/start/path/no-reparse rules and timeouts below, waits for the original and clone, and supports the private `OnCloneAttachedForTest` hook that production never supplies. Do not implement fallback deletion or the remaining withdrawal state machine yet.

- [ ] Rerun the full test against the still-unchanged installer. The observer tests and real original/clone barrier must now pass. The expected-red marker may be emitted only after the legacy-only control deleted its control sentinel, the default-append candidate cycle deleted the preservation sentinel, and every fixture process/key/root teardown assertion succeeded; compiler, install, observer, path, or cleanup failure is infrastructure failure:

```powershell
$BasePython = Resolve-PinnedPrivatePythonFixtureSource
$IsccPath = Resolve-PinnedInnoCompiler
Invoke-ExpectedPowerShellRed `
  -Path 'scripts\tests\containment-release-acceptance.tests.ps1' `
  -Marker 'EXPECTED_RED:legacy-uninstall-log-migration:append' `
  -Arguments @('-PrivatePythonPath', $BasePython, '-IsccPath', $IsccPath)
```

- [ ] Add exactly one line to the existing `[Setup]` section of `installer/RookSetup.iss`:

```ini
UninstallLogMode=overwrite
```

Do not alter the public `AppId`, privilege/architecture mode, directories, payload, `[Code]`, line endings, or any other installer byte.

- [ ] Rerun the full PowerShell test as an intended red. The exact combined marker is emitted only after the real fixture completes both cycles, preserves the second sentinel, proves the current/stale authority postconditions, completes every fixture teardown assertion, and then reaches the still-unimplemented bounded-withdrawal assertions:

```powershell
$BasePython = Resolve-PinnedPrivatePythonFixtureSource
$IsccPath = Resolve-PinnedInnoCompiler
Invoke-ExpectedPowerShellRed `
  -Path 'scripts\tests\containment-release-acceptance.tests.ps1' `
  -Marker 'EXPECTED_RED:legacy-uninstall-log-migration-pass:containment-release-withdrawal:bounded' `
  -Arguments @('-PrivatePythonPath', $BasePython, '-IsccPath', $IsccPath)
```

- [ ] Implement the remaining bounded withdrawal branch around the already-green coordinator-local observer; do not add a second observer or invocation path. The four fallback roots are exactly:

```text
%LOCALAPPDATA%\Rook\app
%LOCALAPPDATA%\Rook\python
%LOCALAPPDATA%\Rook\venv
%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative
```

Before any normal uninstaller, fallback deletion, configuration cleanup, or startup-authority mutation, consult the immutable Task 3 uninstall-state baseline. Any pre-existing case-insensitive `unins*.exe`, `unins*.dat`, or `unins*.msg` match is a sticky `manual_withdrawal_required` result even if the candidate overwrote or removed it. Never invoke or parse that state and perform zero automatic destructive action. With an empty baseline, require the post-installer inventory recorded only after the exact candidate process exited to contain ordinary non-reparse `unins000.exe` and `unins000.dat`, at most `unins000.msg`, and no other matching entry. Immediately before normal-uninstaller launch, recapture the immediate-entry inventory and require exact case-insensitive path/type/size equality with that recorded candidate-created state. Missing pairs, extra/mismatched entries, directories, reparses, drift, or inspection failure return `manual_withdrawal_required` with no destructive action. This empty-to-created transition never establishes `installer_started` or `verified_partial_installation`.

Derive them from `[Environment]::GetFolderPath(...)`; do not read them from `$env:LOCALAPPDATA`, `$env:APPDATA`, a manifest, or CLI input. The normal uninstaller is exactly `%LOCALAPPDATA%\Rook\app\unins000.exe` when present and valid under the preflight. Before launch, derive the one permitted private interpreter as `%LOCALAPPDATA%\Rook\python\cpython-3.11.9\python.exe`. After a successful installation, require `{app}\python_path.txt` to be an ordinary non-reparse file whose sole effective line has exact Windows canonical equality with that interpreter. Only `verified_partial_installation` as mechanically defined in Task 3 may relax this: the file may then be absent, causing the existing Inno code to use the same fixed interpreter, or may contain that same exact value. Any alternate/extra value, reparse, decoding ambiguity, inspection failure, missing process identity, or unobservable exit returns `manual_withdrawal_required` with zero uninstaller or fallback mutation; never resolve, execute, or inspect the alternate target.

Before invoking the normal uninstaller, preflight every fixed or candidate-named destination in Task 3's code-owned affected map: every existing component below its known-folder anchor, the destination itself, and every descendant a recursive delete would traverse, without following reparses. Installed `.claude/skills` and `.claude/agents` must be absent. Installed `.agents/skills` must be the exact pinned 11-name set after a successful installation; only under `verified_partial_installation` may it instead be absent or an allowlisted subset, and every present child must be ordinary/non-reparse with no unknown name admitted. Preflight only the corresponding allowlisted user destination for each present source child. Candidate drift is a manual-withdrawal failure and never expands the map. This larger map models existing normal-uninstaller effects only. Fallback deletion remains closed to the four roots above. All uninstall-state, interpreter, and affected-destination preflights must pass before the observer starts or `Process.Start` is called.

Prepare the unchanged uninstaller's `ProcessStartInfo` with fixed arguments `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` and the same case-insensitive scrub/re-add policy as installation. In addition to the source/model/user-site controls, remove inherited `APPDATA`, `LOCALAPPDATA`, `USERPROFILE`, `HOMEDRIVE`, `HOMEPATH`, `HOME`, `TEMP`, `TMP`, and `TMPDIR`, then supply only the already validated code-owned AppData/LocalAppData/profile/home-drive/home-path/temp values described in Task 3. Remove inherited `PATH` and `NoDefaultCurrentDirectoryInExePath`, then set `PATH` to the present-but-empty string and `NoDefaultCurrentDirectoryInExePath=1`. Create a dedicated working directory beneath the already validated diagnostics/output root, require it to be ordinary, non-reparse, and empty immediately before launch, and set it as `ProcessStartInfo.WorkingDirectory`; never use the caller's or coordinator's former working directory. That cwd controls `unins000.exe` only: unchanged Inno `Exec(PythonExe, ..., '', ...)` starts the validated private-Python `post_install.py --uninstall` process in the interpreter's parent directory. The actual-process test runs there and performs every environment, executable, cwd, `shutil.which`, tripwire, and direct-configuration assertion pinned above. For CPython 3.11.9, present-but-empty `PATH` is the operative lookup suppression; `NoDefaultCurrentDirectoryInExePath=1` remains defense-in-depth and future-runtime policy.

Immediately before starting the original uninstaller, start one local `System.Management.ManagementEventWatcher` for `Win32_ProcessStartTrace`; dispose it in `finally` and do not add or modify a shared process helper. Then call `Process.Start` exactly once. After recording the original process handle, PID, and creation identity, admit exactly one observed direct child whose `ParentProcessID` equals that PID, whose attached process start identity does not predate the parent, and whose canonical ordinary non-reparse executable is strictly beneath the already validated known-folder-derived LocalAppData `Temp` root. Attach and retain the exact `System.Diagnostics.Process` handle before the child can count as observed, continue rejecting a second matching child until the original exits, use a code-owned 30-second capture deadline and 600-second clone-exit deadline, and treat watcher/enumeration/access failure, zero or multiple candidates, wrong parent, pre-parent identity, outside-Temp path, reparse path, lost-before-handle race, PID/start-token reuse, or either timeout as `manual_withdrawal_required`. Wait for and record the original exit code, then wait for that retained TEMP-clone identity to exit before any process preflight, post-withdrawal verification, or fallback. The original exit code remains the uninstall status; clone exit is only the completion barrier. Exit zero does not replace post-withdrawal verification; nonzero may proceed only to the already-bounded fallback when every ownership/state/no-reparse precondition remains satisfied.

The watcher tests use synthetic records for the fail-closed fault matrix but never for the green control. Under Windows PowerShell 5.1, the generated Inno fixture is that control. Keep the coordinator helper local and give it one private optional `OnCloneAttachedForTest` scriptblock that production never supplies; invoke it only after the real watcher has attached and fully validated the live Inno TEMP-clone identity, and treat hook failure as test failure without changing admission. The hook atomically creates the private-Python release marker, after which the copied interpreter and clone may exit normally. The real watcher must deliver the event and observe both original and clone completion. Failure to compile, install, receive, attach, signal, or complete fails the suite; no skip, injected event, Python-process substitute, or fake fallback is allowed.

The post-withdrawal startup-authority check covers the concrete existing surfaces only:

- installed venv/Python, native `RookNative.rhp`, and the three managed `net8.0`, `net7.0`, and `net48` `Rook.rhp` entries;
- Rhino registry keys `A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906` and `B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B`;
- `RookChatService.json` at the plugin root and `net8.0`, `net7.0`, and `net48` children;
- `rook` MCP entries in `~/.claude.json`, `~/.claude/.mcp.json`, `%APPDATA%\Claude\claude_desktop_config.json`, and `~/.codex/config.toml`.

Only after the exact TEMP-clone completion barrier, run a fresh `installer/rook_process_preflight.ps1 -Mode enumerate` with unique new log/summary paths beneath diagnostics; require exit zero, `conflicts_found == false`, and `server_count == 0`, then recheck recorded candidate/original-uninstaller/TEMP-clone/gate-host PID plus creation identities and direct Rhino/Revit/launcher absence. Never reuse a prior summary, infer clone completion from a green Rook-root scan, or infer absence from deleted files/configuration. If authority is absent and this fresh process proof passes, do not run fallback deletion. If cleanup is incomplete, run the closed fallback only after its no-reparse preflight, then repeat the same fresh process enumeration and identity/host checks with another unique evidence set. Any surviving/reappearing process, enumeration failure, uncertain cleanup, or final verification failure returns `manual_withdrawal_required`, never broadens deletion, never writes a passing record, and never touches the gallery.

- [ ] Run focused green verification:

```powershell
$BasePython = Resolve-PinnedPrivatePythonFixtureSource
$IsccPath = Resolve-PinnedInnoCompiler
& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\containment-release-acceptance.tests.ps1 -PrivatePythonPath $BasePython -IsccPath $IsccPath
if ($LASTEXITCODE -ne 0) { throw 'Withdrawal tests failed' }
```

- [ ] Stage exactly the three Task 4 files, mechanically prove the installer diff is the single authorized insertion, verify the allowlist, and commit:

```powershell
$Expected = @(
  'installer/RookSetup.iss',
  'scripts/run-containment-release-acceptance.ps1',
  'scripts/tests/containment-release-acceptance.tests.ps1'
)
Stage-ExactFiles -Paths $Expected
$InstallerNumstat = @(git diff --cached --numstat -- 'installer/RookSetup.iss')
if ($LASTEXITCODE -ne 0 -or $InstallerNumstat.Count -ne 1 -or $InstallerNumstat[0] -cne "1`t0`tinstaller/RookSetup.iss") {
    $InstallerNumstat | Write-Host
    throw 'Installer migration must be exactly one insertion and zero deletions'
}
$InstallerPatch = @(git diff --cached --unified=0 -- 'installer/RookSetup.iss')
if ($LASTEXITCODE -ne 0) { throw 'Installer patch read failed' }
$AddedInstallerLines = @($InstallerPatch | Where-Object { $_ -cmatch '^\+(?!\+\+)' })
$RemovedInstallerLines = @($InstallerPatch | Where-Object { $_ -cmatch '^-(?!--)' })
if ($AddedInstallerLines.Count -ne 1 -or $AddedInstallerLines[0] -cne '+UninstallLogMode=overwrite' -or $RemovedInstallerLines.Count -ne 0) {
    $InstallerPatch | Write-Host
    throw 'Installer migration content drift'
}
git commit -m "fix(installer): replace unsafe legacy uninstall authority"
if ($LASTEXITCODE -ne 0) { throw 'Task 4 commit failed' }
```

- [ ] Obtain fresh spec-compliance and code-quality reviews; fix and re-review before Task 5.

---

## Task 5: Delete the accidental proof platform and package-resident gates

**Files:**

- Modify: `.gitattributes`
- Create: `scripts/tests/test_containment_release_boundary.py`
- Delete: `mcp_server/src/rook/containment_acceptance.py`
- Delete: `mcp_server/src/rook/containment_live_gate.py`
- Delete: `mcp_server/src/rook/resources/containment_empty.ghx`
- Delete: `mcp_server/tests/test_containment_acceptance.py`
- Delete: `mcp_server/tests/test_containment_live_gate.py`
- Delete: `scripts/build-containment-candidate.ps1`
- Delete: `scripts/tests/build-containment-candidate-guards.tests.ps1`
- Delete: `scripts/validate-containment-candidate.ps1`
- Delete: `scripts/tests/validate-containment-candidate.tests.ps1`
- Delete: `scripts/verify-containment-safe-rollback.ps1`
- Delete: `scripts/tests/containment-safe-rollback.tests.ps1`

- [ ] Run the Task Shell block.

- [ ] Add `test_containment_release_boundary.py` first. Make it fail with `EXPECTED_RED:containment-release-boundary:old-platform-present` while any old file exists. It also asserts:

  - `rook.containment_acceptance` and `rook.containment_live_gate` are absent;
  - no containment fixture remains under `mcp_server/src/rook`;
  - external release tooling stays under `scripts/containment_release`;
  - no external release tool is registered as an MCP tool, agent local tool, project script, or package export;
  - no alternate builder, generalized validator, durable hold, or rollback verifier name remains in current release instructions; and
  - `.gitattributes` retains the unrelated FFmpeg LFS rule plus the new external GHX binary rule and no old package-fixture rule; and
  - the approved lifecycle/runtime containment modules and source tests still exist.

- [ ] Run the intended red:

```powershell
Invoke-ExpectedPytestRed `
  -Path 'scripts/tests/test_containment_release_boundary.py' `
  -Marker 'EXPECTED_RED:containment-release-boundary:old-platform-present' `
  -JunitPath '.pytest_tmp/containment-release-boundary-red.xml'
```

- [ ] Delete the eleven overbuilt source/test/platform files listed above. Do not revert the core containment implementation or source tests.

For the preceding scan, “current release instructions” means the two active build-release skill copies, not the approved specification, this implementation plan, or historical design records.

- [ ] Replace only the old package-fixture rule in `.gitattributes`. Preserve the unrelated FFmpeg LFS authority. The resulting file retains both exact lines:

```text
third_party/ffmpeg/ffmpeg.exe filter=lfs diff=lfs merge=lfs -text
scripts/containment_release/fixtures/containment_empty.ghx -text
```

- [ ] Run the boundary, new external, and core containment suites:

```powershell
& $Python -m pytest `
  scripts/tests/test_containment_release_boundary.py `
  scripts/tests/test_containment_release_probe.py `
  scripts/tests/test_containment_release_live_gate.py `
  mcp_server/tests/test_tool_lifecycle.py `
  mcp_server/tests/test_containment_telemetry.py `
  mcp_server/tests/test_tool_catalog_cache.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_containment_guidance.py -q
if ($LASTEXITCODE -ne 0) { throw 'Boundary/core containment suite failed' }
```

Expected: exit `0`.

- [ ] Stage exactly the thirteen Task 5 paths, verify the allowlist, and commit:

```powershell
$Expected = @(
  '.gitattributes',
  'mcp_server/src/rook/containment_acceptance.py',
  'mcp_server/src/rook/containment_live_gate.py',
  'mcp_server/src/rook/resources/containment_empty.ghx',
  'mcp_server/tests/test_containment_acceptance.py',
  'mcp_server/tests/test_containment_live_gate.py',
  'scripts/build-containment-candidate.ps1',
  'scripts/tests/build-containment-candidate-guards.tests.ps1',
  'scripts/tests/containment-safe-rollback.tests.ps1',
  'scripts/tests/test_containment_release_boundary.py',
  'scripts/tests/validate-containment-candidate.tests.ps1',
  'scripts/validate-containment-candidate.ps1',
  'scripts/verify-containment-safe-rollback.ps1'
)
Stage-ExactFiles -Paths $Expected
git commit -m "refactor(release): remove containment proof platform"
if ($LASTEXITCODE -ne 0) { throw 'Task 5 commit failed' }
```

- [ ] Obtain fresh spec-compliance and code-quality reviews. Review the deletion diff specifically for accidental loss of runtime containment or supported-path coverage. Fix and re-review before Task 6.

---

## Task 6: Wire the thin gate into the existing release instructions

**Files:**

- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.claude/skills/build-release/SKILL.md`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] Run the Task Shell block.

- [ ] Add failing guard assertions first with `EXPECTED_RED:containment-normal-release-sequence`. Pin both skill copies to the same sequence:

  1. merge containment to `main` without publishing;
  2. create and merge the normal reviewed version-bump release PR;
  3. build once from the resulting version-bumped `main` SHA with existing Steps 3A-7;
  4. start the coordinator before the first installer launch;
  5. let the operator run the existing standalone Rhino and Rhino.Inside/Revit smoke outside the coordinator, produce the external smoke manifest, close those hosts, and enter the run-bound continuation token;
  6. let the already-running coordinator pass that exact file to unchanged `validate-release-artifacts.ps1`, which produces the release manifest; and
  7. let that coordinator continue with installed containment and paired live proof; and
  8. immediately before upload, read the acceptance record and independently recompute all three accepted digests; then publish those exact installer, smoke-manifest, and release-manifest bytes with the normal FFmpeg assets, without rebuild/repack/rewrite.

The guard also requires `-BuildStartedAt $buildStartedAt`, an absolute resolved coordinator path, and the immediate coordinator `$LASTEXITCODE` check. It rejects references to deleted alternate builder/validator/rollback tools and requires both skill copies to remain byte-identical for the containment addition.

- [ ] Run the intended red:

```powershell
Invoke-ExpectedPowerShellRed `
  -Path 'scripts\tests\release-installer-guards.tests.ps1' `
  -Marker 'EXPECTED_RED:containment-normal-release-sequence'
```

- [ ] Update only the release instructions around existing Step 8. Do not duplicate the normal build, smoke schema, release validator, or publication logic. Add this coordinator invocation template after the normal installer is built and before installation:

```powershell
$AcceptanceRoot = Join-Path $env:TEMP ("rook-containment-acceptance-{0}-{1}" -f $VERSION, [Guid]::NewGuid().ToString('N'))
$WindowsPowerShell = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
$CoordinatorPath = (Resolve-Path -LiteralPath 'scripts\run-containment-release-acceptance.ps1').Path
$InstallerPath = (Resolve-Path -LiteralPath "installer\output\Rook-Setup-$VERSION.exe").Path
$SmokeManifestPath = [IO.Path]::GetFullPath("installer\output\release-smoke-$VERSION.json")
$ReleaseManifestPath = [IO.Path]::GetFullPath("installer\output\release-manifest-$VERSION.json")
if ((Test-Path -LiteralPath $SmokeManifestPath) -or (Test-Path -LiteralPath $ReleaseManifestPath)) {
  throw 'Remove stale release smoke/manifest outputs before starting this acceptance session'
}

& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass `
  -File $CoordinatorPath `
  -ExpectedReleaseSha $gitSha `
  -Version $VERSION `
  -BuildStartedAt $buildStartedAt `
  -InstallerPath $InstallerPath `
  -SmokeManifestPath $SmokeManifestPath `
  -ReleaseManifestPath $ReleaseManifestPath `
  -RhinoExe "C:\Program Files\Rhino 8\System\Rhino.exe" `
  -OutputDirectory $AcceptanceRoot
if ($LASTEXITCODE -ne 0) { throw "Containment release acceptance failed with exit code $LASTEXITCODE" }
```

The coordinator waits after installation and prints `READY_FOR_NORMAL_RELEASE_SMOKE <run-id>`. In the existing release shell, the operator runs the ordinary standalone Rhino and Rhino.Inside/Revit smoke workflow, closes those hosts and their Rook children, then enters `CONTINUE_AFTER_NORMAL_RELEASE_SMOKE <run-id>` or `ABORT_NORMAL_RELEASE_SMOKE <run-id>` in the coordinator console. The coordinator owns no smoke shell and runs no smoke implementation. On continue it invokes the unchanged validator itself, then advances to the installed probe and the two separately authorized live gates. No skill step tells the coordinator to build, merge, version, publish, generate the smoke schema, or replace the validator.

Immediately before the existing `gh release create`, the skill reads `$AcceptanceRoot\containment-release-acceptance.json`, requires `success: true` plus the expected SHA/version, recomputes SHA-256 for `$InstallerPath`, `$SmokeManifestPath`, and `$ReleaseManifestPath`, and compares each to its recorded digest. Any drift blocks upload. The skill does not rewrite any accepted file.

- [ ] Run green guards:

```powershell
& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Release installer guards failed' }
```

- [ ] Stage exactly the three Task 6 files, verify the allowlist, and commit:

```powershell
$Expected = @(
  '.agents/skills/build-release/SKILL.md',
  '.claude/skills/build-release/SKILL.md',
  'scripts/tests/release-installer-guards.tests.ps1'
)
Stage-ExactFiles -Paths $Expected
git commit -m "docs(release): add thin containment acceptance gate"
if ($LASTEXITCODE -ne 0) { throw 'Task 6 commit failed' }
```

- [ ] Obtain fresh spec-compliance and code-quality reviews; fix and re-review before whole-branch verification.

---

## Task 7: Whole-branch verification and review

Task 7 changes no files unless a reviewer finds a defect. Any correction receives its own narrow commit, focused test, and repeated review.

- [ ] Run the Task Shell block.

- [ ] Derive the implementation baseline and enforce the exact branch-wide changed-path allowlist. This catches every task and correction commit; do not broaden it for an unplanned fix:

```powershell
$Spec = '5c37f2d6f30344648c9b7dcb39ccd3b92121a18d'
$PlanPath = 'docs/superpowers/plans/2026-07-15-legacy-semantic-authority-containment.md'
$FirstParentDescendants = @(git rev-list --first-parent --reverse "$Spec..HEAD")
if ($LASTEXITCODE -ne 0 -or $FirstParentDescendants.Count -lt 1) { throw 'Implementation baseline resolution failed' }
$ImplementationBaseline = $FirstParentDescendants[0].Trim()
if ((git rev-parse "$ImplementationBaseline^").Trim() -ne $Spec) { throw 'Plan commit parent drift' }
$PlanCommitPaths = @(git diff-tree --no-commit-id --name-only -r $ImplementationBaseline)
if ($PlanCommitPaths.Count -ne 1 -or $PlanCommitPaths[0] -cne $PlanPath) { throw 'Implementation baseline is not the approved plan-only commit' }

$ExpectedChangedPaths = @(
  $PlanPath,
  '.agents/skills/build-release/SKILL.md',
  '.claude/skills/build-release/SKILL.md',
  '.gitattributes',
  'installer/RookSetup.iss',
  'mcp_server/src/rook/containment_acceptance.py',
  'mcp_server/src/rook/containment_live_gate.py',
  'mcp_server/src/rook/resources/containment_empty.ghx',
  'mcp_server/tests/test_containment_acceptance.py',
  'mcp_server/tests/test_containment_live_gate.py',
  'scripts/build-containment-candidate.ps1',
  'scripts/containment_release/__init__.py',
  'scripts/containment_release/fixtures/containment_empty.ghx',
  'scripts/containment_release/installed_probe.py',
  'scripts/containment_release/live_gate.py',
  'scripts/run-containment-release-acceptance.ps1',
  'scripts/tests/build-containment-candidate-guards.tests.ps1',
  'scripts/tests/containment-release-acceptance.tests.ps1',
  'scripts/tests/containment-safe-rollback.tests.ps1',
  'scripts/tests/release-installer-guards.tests.ps1',
  'scripts/tests/test_containment_release_boundary.py',
  'scripts/tests/test_containment_release_live_gate.py',
  'scripts/tests/test_containment_release_probe.py',
  'scripts/tests/validate-containment-candidate.tests.ps1',
  'scripts/validate-containment-candidate.ps1',
  'scripts/verify-containment-safe-rollback.ps1'
) | Sort-Object
if ($ExpectedChangedPaths.Count -ne 26) { throw 'Expected changed-path snapshot must contain exactly 26 paths' }
$ActualChangedPaths = @(git diff --no-renames --name-only "$ImplementationBaseline..HEAD") | Sort-Object
if ($LASTEXITCODE -ne 0) { throw 'Branch changed-path read failed' }
$PathDelta = @(Compare-Object -CaseSensitive -ReferenceObject $ExpectedChangedPaths -DifferenceObject $ActualChangedPaths)
if ($PathDelta.Count -ne 0) {
    $PathDelta | Format-Table | Out-String | Write-Host
    throw 'Branch-wide changed-path allowlist mismatch'
}

$NoTouch = @(
  'installer/post_install.py',
  'installer/python_runtime_install.py',
  'installer/rook_process_preflight.ps1',
  'scripts/validate-release-artifacts.ps1',
  'scripts/tests/validate-release-artifacts.tests.ps1',
  'mcp_server/pyproject.toml'
)
$Forbidden = @($ActualChangedPaths | Where-Object { $_ -in $NoTouch })
if ($Forbidden.Count -ne 0) { $Forbidden | Write-Host; throw 'No-touch release surface changed' }

$InstallerNumstat = @(git diff --no-renames --numstat "$ImplementationBaseline..HEAD" -- 'installer/RookSetup.iss')
if ($LASTEXITCODE -ne 0 -or $InstallerNumstat.Count -ne 1 -or $InstallerNumstat[0] -cne "1`t0`tinstaller/RookSetup.iss") {
    $InstallerNumstat | Write-Host
    throw 'Branch-wide installer migration must be exactly one insertion and zero deletions'
}
$InstallerPatch = @(git diff --no-renames --unified=0 "$ImplementationBaseline..HEAD" -- 'installer/RookSetup.iss')
if ($LASTEXITCODE -ne 0) { throw 'Branch-wide installer patch read failed' }
$AddedInstallerLines = @($InstallerPatch | Where-Object { $_ -cmatch '^\+(?!\+\+)' })
$RemovedInstallerLines = @($InstallerPatch | Where-Object { $_ -cmatch '^-(?!--)' })
if ($AddedInstallerLines.Count -ne 1 -or $AddedInstallerLines[0] -cne '+UninstallLogMode=overwrite' -or $RemovedInstallerLines.Count -ne 0) {
    $InstallerPatch | Write-Host
    throw 'Branch-wide installer migration content drift'
}
```

- [ ] Run all campaign-focused tests:

```powershell
& $Python -m pytest `
  scripts/tests/test_containment_release_boundary.py `
  scripts/tests/test_containment_release_probe.py `
  scripts/tests/test_containment_release_live_gate.py `
  mcp_server/tests/test_tool_lifecycle.py `
  mcp_server/tests/test_containment_telemetry.py `
  mcp_server/tests/test_tool_catalog_cache.py `
  mcp_server/tests/test_containment_execution.py `
  mcp_server/tests/test_containment_packaged_executors.py `
  mcp_server/tests/test_containment_agent_protocols.py `
  mcp_server/tests/test_containment_supported_paths.py `
  mcp_server/tests/test_containment_guidance.py -q
if ($LASTEXITCODE -ne 0) { throw 'Focused containment suite failed' }

$BasePython = Resolve-PinnedPrivatePythonFixtureSource
$IsccPath = Resolve-PinnedInnoCompiler
& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\containment-release-acceptance.tests.ps1 -PrivatePythonPath $BasePython -IsccPath $IsccPath
if ($LASTEXITCODE -ne 0) { throw 'Thin coordinator suite failed' }

& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Release installer guard suite failed' }

& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\validate-release-artifacts.tests.ps1
if ($LASTEXITCODE -ne 0) { throw 'Existing release validator suite failed' }
```

- [ ] Run the complete non-live Python suite. Live Rhino tests are explicitly excluded from this source phase:

```powershell
& $Python -m pytest mcp_server/tests -m "not requires_rhino" -q
if ($LASTEXITCODE -ne 0) { throw 'Non-live Python suite failed' }
```

- [ ] Run mechanical proof:

```powershell
& $Python -m py_compile `
  scripts/containment_release/installed_probe.py `
  scripts/containment_release/live_gate.py
if ($LASTEXITCODE -ne 0) { throw 'External Python compile failed' }

& $WindowsPowerShell -NoProfile -ExecutionPolicy Bypass -Command "[void][scriptblock]::Create((Get-Content -LiteralPath 'scripts\run-containment-release-acceptance.ps1' -Raw))"
if ($LASTEXITCODE -ne 0) { throw 'Coordinator PS5.1 parse failed' }

git diff --check "$Spec..HEAD"
if ($LASTEXITCODE -ne 0) { throw 'Committed branch diff check failed' }

$Numstat = @(git diff --no-renames --numstat "$ImplementationBaseline..HEAD" -- . ":(exclude)$PlanPath")
if ($LASTEXITCODE -ne 0) { throw 'Implementation numstat failed' }
$Added = 0; $Deleted = 0
$ReleaseProofRows = @()
foreach ($Line in $Numstat) {
    $Parts = $Line -split "`t"
    if ($Parts.Count -lt 3) { throw "Malformed numstat line: $Line" }
    if ($Parts[0] -match '^\d+$') {
        $Added += [int]$Parts[0]
        $Path = $Parts[2]
        if (
            [int]$Parts[0] -gt 0 -and
            $Path -notmatch '\.ghx$' -and
            $Path -ne '.gitattributes'
        ) {
            $DeletedForPath = 0
            if ($Parts[1] -match '^\d+$') { $DeletedForPath = [int]$Parts[1] }
            $ReleaseProofRows += [pscustomobject]@{ Path = $Path; Added = [int]$Parts[0]; Deleted = $DeletedForPath }
        }
    }
    if ($Parts[1] -match '^\d+$') { $Deleted += [int]$Parts[1] }
}
if ($Deleted -le $Added) { throw "Pruning failed: added=$Added deleted=$Deleted" }
$ReleaseProofRows | Sort-Object Path | Format-Table -AutoSize | Out-String | Write-Host
$ReleaseProofAdded = [int](($ReleaseProofRows | Measure-Object -Property Added -Sum).Sum)
$FourDigitRows = @($ReleaseProofRows | Where-Object { $_.Added -ge 1000 })
$KissReviewRequired = ($FourDigitRows.Count -gt 0 -or $ReleaseProofAdded -ge 1000)
Write-Host "Aggregate release-tool/instruction/test additions: $ReleaseProofAdded"
if ($KissReviewRequired) {
    $FourDigitRows | Format-Table -AutoSize | Out-String | Write-Host
    Write-Warning 'Four-digit per-file or aggregate release-proof additions require explicit KISS review before completion'
}

$Status = @(git status --short)
if ($LASTEXITCODE -ne 0) { throw 'git status failed' }
if ($Status.Count -ne 0) { $Status | Write-Host; throw 'Whole-branch verification left a dirty tree' }
```

- [ ] If `$KissReviewRequired` is true, stop Task 7 until the whole-branch reviewers explicitly approve both the exact per-file rows and aggregate release-tool/instruction/test additions as proportionate, or simplify them below the four-digit thresholds. Tests are included; bulk deletions cannot waive this review.

- [ ] Request a fresh whole-branch spec-compliance review against `5c37f2d6`.

- [ ] Request a fresh whole-branch code-quality/security review focused on containment bypasses, installed-proof non-vacuity, the legacy-log migration, gallery safety, and withdrawal bounds.

- [ ] Fix and re-review all important findings. Rerun the complete Task 7 sequence after the final correction.

- [ ] Present the clean branch and evidence for merge review. Do not build or install a publishable release candidate from this feature-branch SHA.

## Post-Merge Release Acceptance (Required Before Publication)

This phase is operational release work, not another implementation task.

- [ ] Merge the reviewed containment branch to `main` without publishing.
- [ ] Create the normal `release/vX.Y.Z` branch from updated `main`, make only the normal version edits, merge its reviewed PR, and record the resulting version-bumped `main` SHA as `$gitSha`.
- [ ] From that exact clean version-bumped `main`, rerun the Task 4 PowerShell suite with the pinned full CPython 3.11.9 source and normal-release Inno Setup 6 compiler. Require the real legacy-only deletion control, overwrite/preservation cycle, TEMP-clone/private-Python proof, and all coordinator tests to pass before building the release installer.
- [ ] Follow the existing build-release skill through its normal Python/wheelhouse, FFmpeg, native, managed/RookBIM, installer-source, and ISCC steps. Build the installer once from `$gitSha`.
- [ ] Start `run-containment-release-acceptance.ps1` with the command in Task 6. It records the pre-install gallery baseline and launches the existing installer.
- [ ] When it prints `READY_FOR_NORMAL_RELEASE_SMOKE`, use the existing release workflow outside the coordinator to run the standalone Rhino and Rhino.Inside/Revit smoke workflows. Those workflows produce the previously absent `release-smoke-X.Y.Z.json`.
- [ ] Close the normal-smoke Rhino/Revit hosts and their Rook children, then enter `CONTINUE_AFTER_NORMAL_RELEASE_SMOKE <run-id>` in the still-running coordinator only after fresh quiescence; use its exact abort token if smoke failed. The coordinator passes that smoke file to unchanged `scripts/validate-release-artifacts.ps1`, which emits `release-manifest-X.Y.Z.json`, then proceeds to containment proof.
- [ ] Grant separate explicit authorization for the Rhino and Grasshopper live scenarios only after reading each named target/mutation/restoration challenge.
- [ ] Require the coordinator's atomic success record, exact `422/425/20/148` discovery, complete 36 transport records, complete literal 29 internal records, both restored live scenarios, zero containment activity on supported paths, and the phase-aware gallery result.
- [ ] If the coordinator fails, do not publish. Follow only its bounded withdrawal result. A manual-withdrawal result remains a release failure and authorizes no broader deletion.
- [ ] Immediately before publication, reread the acceptance record and independently recompute the installer, external smoke-manifest, and release-manifest SHA-256 values. Publish only the normal release asset set and those exact accepted bytes. Do not rebuild, rewrite, or repack the three files.
