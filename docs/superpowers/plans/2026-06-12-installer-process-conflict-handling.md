# Installer Process Conflict Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Rook upgrades complete cleanly when live Claude/Codex Rook MCP sessions are running, while also deleting and rewriting stale companion child chat manifests.

**Architecture:** Inno owns pre-copy consent and invokes a standalone PowerShell helper before `[Files]`; Python owns the testable rebuild guard around venv mutation after `[Files]`. One stable `%LOCALAPPDATA%\Rook\logs\post_install.log` and one stable `%LOCALAPPDATA%\Rook\logs\post_install_summary.json` carry the audit trail from preflight through finalizer exit.

**Tech Stack:** Inno Setup Pascal `[Code]`, Windows PowerShell 5.1, Python 3.11 stdlib only for installer/finalizer code, pytest, PowerShell guard tests.

---

## Source Material

- Spec: `docs/superpowers/specs/2026-06-12-installer-process-conflict-design.md`
- GitHub issues: #237 installer process-conflict handling, #240 stale per-child chat manifests.
- Current installer entry points:
  - `installer/RookSetup.iss`
  - `installer/post_install.py`
  - `installer/python_runtime_install.py`
- Current guard suites:
  - `scripts/tests/release-installer-guards.tests.ps1`
  - `mcp_server/tests/test_python_runtime_install.py`
  - `mcp_server/tests/test_post_install_encoding.py`

Carry-forward reviewer notes for implementation:

- Consent-cancel logging should be done by the helper, not Pascal. Add a helper mode such as `record-outcome` so UTF-8 logging remains in one place and Pascal stays dumb.
- The `[Files]` copy-duration bound is typical-hardware evidence. Live smoke must record actual copy duration and note that slower disks or antivirus scan load can widen the accepted respawn race.

## Scope Check

This plan deliberately keeps #237 and #240 in one implementation because they share the same live installer smoke oracle. The work spans installer policy, a pre-copy helper, a Python rebuild guard, logging/summary artifacts, manifest cleanup, and verification. Do not split #240 unless the manifest fix requires any `src/Rook/**` diff.

## File Structure

Create:

- `installer/rook_process_preflight.ps1`
  Standalone Windows PowerShell 5.1 helper. Modes: `enumerate`, `close`, and `record-outcome`. It enumerates Rook-root image-path matches, counts logical server roots, attributes owners, closes matched roots plus full descendant trees, writes UTF-8 logs, and seeds/updates the stable summary JSON.

- `installer/process_rebuild_guard.py`
  Python stdlib-only process snapshot and rebuild-guard primitive. It exposes testable pure functions for root detection, descendant closure, ancestry validation, finalizer exclusion, per-PID close caps, and guard lifecycle.

- `mcp_server/tests/test_process_rebuild_guard.py`
  Pure unit tests for `process_rebuild_guard.py` using fake process snapshots and fake terminators. These tests must run without killing real processes.

- `scripts/tests/rook-process-preflight.tests.ps1`
  PowerShell helper contract tests. Include pure JSON/log tests and one fabricated pre-bundled-upgrade integration test that uses a temp venv to prove descendant-tree close reaches an out-of-boundary system-Python child.

Modify:

- `installer/RookSetup.iss`
  Add Inno process policy, package/extract the helper, invoke preflight in `PrepareToInstall`, optionally re-sweep during `[Files]`, package `process_rebuild_guard.py`, add #240 `[InstallDelete]` entries, and keep finalizer failure fatal.

- `installer/post_install.py`
  Configure always-on logging early, read/extend `post_install_summary.json`, wrap the script entrypoint in a last-gasp handler, use rebuild guards around Rook and Chirp venv mutation, retry one full rebuild after guarded venv/pip failure, and write root plus child chat manifests byte-identically.

- `scripts/tests/release-installer-guards.tests.ps1`
  Add source-pin checks for Inno directives, helper packaging, `PrepareToInstall` integration, `record-outcome`, optional `[Files]` re-sweep or explicit accepted-race note, #240 delete entries, and zero `src/Rook/**` scope for #240.

- `mcp_server/tests/test_python_runtime_install.py`
  Add tests for guarded rebuild retry, guard stand-down, logging/summary extension, last-gasp failure capture, and chat manifest root/child parity.

- `mcp_server/tests/test_post_install_encoding.py`
  Extend encoding source pins for new summary/log/manifest text IO. Existing `Path.read_text`/`Path.write_text` coverage should remain.

Smoke artifacts:

- `installer/output/installer-conflict-smoke-1.5.12-dev.json`
  Local generated smoke evidence, not necessarily committed. Use it in the PR description.

---

### Task 1: PowerShell Preflight Helper Contract

**Files:**
- Create: `installer/rook_process_preflight.ps1`
- Create: `scripts/tests/rook-process-preflight.tests.ps1`

- [ ] **Step 1: Write the helper contract tests**

Create `scripts/tests/rook-process-preflight.tests.ps1`:

```powershell
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$Helper = Join-Path $RepoRoot 'installer\rook_process_preflight.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Equals {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) { throw "$Message Expected [$Expected], got [$Actual]." }
}

function New-TestRoot {
    $root = Join-Path $env:TEMP ("rook-preflight-test-" + [guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $root -Force | Out-Null
    return $root
}

function Invoke-Helper {
    param(
        [string]$Mode,
        [string]$RookRoot,
        [string]$LogRoot,
        [string]$ExtraArgs = ''
    )
    $summary = Join-Path $LogRoot 'post_install_summary.json'
    $innoSummary = Join-Path $LogRoot 'preflight-summary.txt'
    $log = Join-Path $LogRoot 'post_install.log'
    $helperArgs = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $Helper,
        '-Mode', $Mode,
        '-RookRoot', $RookRoot,
        '-LogRoot', $LogRoot,
        '-SummaryPath', $summary,
        '-InnoSummaryPath', $innoSummary,
        '-LogPath', $log,
        '-SetupVersion', 'test'
    )
    if ($ExtraArgs) {
        $helperArgs += $ExtraArgs.Split(' ')
    }
    & powershell.exe @helperArgs
    return $LASTEXITCODE
}

function Test-EnumerateNoConflictsSeedsSummaryAndLog {
    $root = New-TestRoot
    $logs = Join-Path $root 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null

    $code = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs

    Assert-Equals $code 0 'Enumeration with no matching processes must exit 0.'
    $summaryPath = Join-Path $logs 'post_install_summary.json'
    $innoSummaryPath = Join-Path $logs 'preflight-summary.txt'
    $logPath = Join-Path $logs 'post_install.log'
    Assert-True (Test-Path $summaryPath) 'Enumeration must seed post_install_summary.json.'
    Assert-True (Test-Path $innoSummaryPath) 'Enumeration must write the terse Inno summary file.'
    Assert-True (Test-Path $logPath) 'Enumeration must create post_install.log.'
    $summary = Get-Content -Path $summaryPath -Raw | ConvertFrom-Json
    Assert-Equals $summary.schema_version 1 'Summary schema version must be pinned.'
    Assert-Equals $summary.preflight.server_count 0 'No-conflict enumeration must record zero server roots.'
    Assert-Equals $summary.preflight.conflicts_found $false 'No-conflict enumeration must record conflicts_found=false.'
    $innoSummary = Get-Content -Path $innoSummaryPath -Raw
    Assert-True ($innoSummary.Contains('conflicts_found=false')) 'Inno summary must expose conflicts_found as key=value.'
    Assert-True ($innoSummary.Contains('message=')) 'Inno summary must include the exact dialog/status message.'
    $bytes = [IO.File]::ReadAllBytes($logPath)
    Assert-True ($bytes.Length -gt 0) 'Log must not be empty.'
    Assert-True (-not ($bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF)) 'Log must be UTF-8 without a BOM.'
}

function Test-RecordOutcomeCancelledUsesStableSummary {
    $root = New-TestRoot
    $logs = Join-Path $root 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $null = Invoke-Helper -Mode enumerate -RookRoot $root -LogRoot $logs

    $code = Invoke-Helper -Mode record-outcome -RookRoot $root -LogRoot $logs -ExtraArgs '-Outcome cancelled'

    Assert-Equals $code 0 'record-outcome cancelled must exit 0.'
    $summary = Get-Content -Path (Join-Path $logs 'post_install_summary.json') -Raw | ConvertFrom-Json
    Assert-Equals $summary.outcome 'cancelled' 'Summary must persist cancelled outcome.'
    $log = Get-Content -Path (Join-Path $logs 'post_install.log') -Raw
    Assert-True ($log.Contains('outcome=cancelled')) 'Log must describe consent cancellation.'
}

function Test-CloseModeFailsQuietlyWhenNothingMatches {
    $root = New-TestRoot
    $logs = Join-Path $root 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null

    $code = Invoke-Helper -Mode close -RookRoot $root -LogRoot $logs

    Assert-Equals $code 0 'Close mode with no matches must exit 0.'
}

function Test-PreBundledDescendantTreeCloseKillsOutOfBoundaryChild {
    $python = (Get-Command python -ErrorAction SilentlyContinue).Source
    if (-not $python) {
        Write-Host 'SKIP: python.exe not on PATH for fabricated venv integration test.'
        return
    }

    $root = New-TestRoot
    $logs = Join-Path $root 'logs'
    New-Item -ItemType Directory -Path $logs -Force | Out-Null
    $venv = Join-Path $root 'venv'
    & $python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create temp venv.' }

    $childPidFile = Join-Path $root 'child.pid'
    $script = Join-Path $root 'spawn_child.py'
    @'
import pathlib
import subprocess
import sys
import time

pid_file = pathlib.Path(sys.argv[1])
base = getattr(sys, "_base_executable", sys.executable)
child = subprocess.Popen([base, "-c", "import time; time.sleep(120)"])
pid_file.write_text(str(child.pid), encoding="utf-8")
try:
    time.sleep(120)
finally:
    child.terminate()
'@ | Set-Content -Path $script -Encoding UTF8

    $venvPython = Join-Path $venv 'Scripts\python.exe'
    $parentArgs = '"' + $script + '" "' + $childPidFile + '"'
    $parent = Start-Process -FilePath $venvPython -ArgumentList $parentArgs -PassThru -WindowStyle Hidden
    try {
        $deadline = (Get-Date).AddSeconds(20)
        while ((-not (Test-Path $childPidFile)) -and ((Get-Date) -lt $deadline)) {
            Start-Sleep -Milliseconds 100
        }
        Assert-True (Test-Path $childPidFile) 'Test child PID file was not written.'
        $childPid = [int](Get-Content -Path $childPidFile -Raw)

        $code = Invoke-Helper -Mode close -RookRoot $root -LogRoot $logs

        Assert-Equals $code 0 'Helper close mode must reach quiet.'
        Start-Sleep -Milliseconds 500
        Assert-True (-not (Get-Process -Id $parent.Id -ErrorAction SilentlyContinue)) 'Matched venv root process must be closed.'
        Assert-True (-not (Get-Process -Id $childPid -ErrorAction SilentlyContinue)) 'Out-of-boundary system-Python child must be closed.'
    }
    finally {
        Stop-Process -Id $parent.Id -Force -ErrorAction SilentlyContinue
        if (Test-Path $childPidFile) {
            Stop-Process -Id ([int](Get-Content -Path $childPidFile -Raw)) -Force -ErrorAction SilentlyContinue
        }
    }
}

Test-EnumerateNoConflictsSeedsSummaryAndLog
Test-RecordOutcomeCancelledUsesStableSummary
Test-CloseModeFailsQuietlyWhenNothingMatches
Test-PreBundledDescendantTreeCloseKillsOutOfBoundaryChild
Write-Host 'rook-process-preflight.tests.ps1 PASS'
```

- [ ] **Step 2: Run the helper tests and confirm they fail before the helper exists**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\rook-process-preflight.tests.ps1
```

Expected: FAIL because `installer\rook_process_preflight.ps1` does not exist.

- [ ] **Step 3: Create the PowerShell helper**

Create `installer/rook_process_preflight.ps1` with these concrete requirements:

```powershell
param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('enumerate', 'close', 'record-outcome')]
    [string]$Mode,

    [Parameter(Mandatory=$true)]
    [string]$RookRoot,

    [Parameter(Mandatory=$true)]
    [string]$LogRoot,

    [string]$SummaryPath,
    [string]$InnoSummaryPath,
    [string]$LogPath,
    [string]$SetupVersion = 'unknown',
    [string]$Outcome = ''
)

$ExitQuiet = 0
$ExitNotQuiet = 10
$ExitEnumerationFailure = 20
$ExitCloseFailure = 30
$ExitHelperError = 40

function Normalize-PathPrefix([string]$Path) {
    return ([IO.Path]::GetFullPath($Path).TrimEnd('\') + '\').ToLowerInvariant()
}

function Append-Utf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::AppendAllText($Path, $Text, $encoding)
}

function Write-Utf8([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent) { [IO.Directory]::CreateDirectory($parent) | Out-Null }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    [IO.File]::WriteAllText($Path, $Text, $encoding)
}

function Log-Line([string]$Message) {
    Append-Utf8 -Path $script:LogPathResolved -Text ("{0} {1}`r`n" -f ([DateTime]::UtcNow.ToString("o")), $Message)
}
```

Implementation details that must be present in the helper:

- Resolve `$SummaryPath` to `$LogRoot\post_install_summary.json` when omitted.
- Resolve `$InnoSummaryPath` to `$LogRoot\preflight-summary.txt` when omitted.
- Resolve `$LogPath` to `$LogRoot\post_install.log` when omitted.
- In `enumerate`, rotate `$LogPath` to `$LogRoot\post_install.prev.log` before writing the run header.
- Use `Get-CimInstance Win32_Process` and capture `ProcessId`, `ParentProcessId`, `ExecutablePath`, `CommandLine`, and `CreationDate`.
- A matched process has `ExecutablePath` under the normalized `$RookRoot` prefix.
- A logical server root is a matched process whose creation-time-valid parent is not also matched.
- Owner name is one parent hop from the logical server root. Map `claude.exe` to `Claude`, `codex.exe` to `Codex`, otherwise use raw basename.
- Compose the exact consent/status message in the helper and write it to `$InnoSummaryPath` as UTF-8 key/value text:

```text
conflicts_found=true
server_count=5
owners=Claude, Codex
message=Rook Setup found 5 running Rook agent server(s) started by Claude and Codex.\r\n\r\nSetup will close them now so Rook can be updated. Your AI tools will reconnect after installation.
```

- `close` mode builds the descendant closure for each matched root, including children outside `$RookRoot`, sorts descendants before ancestors, and calls `Stop-Process -Id $pid -Force` for each process.
- Retry close-to-quiet at most three times per PID. Exit `10` if matches remain, `20` for enumeration failure, `30` for close failure.
- `record-outcome` writes the supplied outcome, especially `cancelled`, to both log and summary without touching processes.

The summary JSON shape must include at least:

```json
{
  "schema_version": 1,
  "setup_version": "test",
  "run_start_utc": "2026-06-12T00:00:00Z",
  "phase_reached": "preflight",
  "preflight": {
    "conflicts_found": false,
    "server_count": 0,
    "owners": [],
    "processes": []
  },
  "closed_process_count": 0,
  "outcome": "preflight-enumerated"
}
```

- [ ] **Step 4: Run the helper tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\rook-process-preflight.tests.ps1
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add installer\rook_process_preflight.ps1 scripts\tests\rook-process-preflight.tests.ps1
git commit -m "test: cover installer preflight process helper"
```

---

### Task 2: Inno Preflight Integration And Guard Rails

**Files:**
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Add failing release guard tests**

Append this function to `scripts/tests/release-installer-guards.tests.ps1` near the other installer guard functions:

```powershell
function Test-InstallerUsesRookProcessPreflight {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected 'CloseApplications=no' -Message 'Installer must disable Inno Restart Manager close-app behavior.'
    Assert-Contains -Text $content -Expected 'RestartApplications=no' -Message 'Installer must not restart raw python -m rook processes after install.'
    Assert-Contains -Text $content -Expected 'SetupLogging=yes' -Message 'Installer must enable Inno setup logging as a backstop.'
    Assert-Contains -Text $content -Expected 'Source: "rook_process_preflight.ps1"; Flags: dontcopy' -Message 'Preflight helper must be embedded for ExtractTemporaryFile before [Files].'
    Assert-Contains -Text $content -Expected 'ExtractTemporaryFile(''rook_process_preflight.ps1'')' -Message 'PrepareToInstall must extract the helper to {tmp}.'
    Assert-Contains -Text $content -Expected 'function RunRookProcessPreflight' -Message 'Installer must run Rook process preflight before [Files].'
    Assert-Contains -Text $content -Expected 'RunRookPreflightHelper(''enumerate''' -Message 'Preflight must run helper enumeration mode.'
    Assert-Contains -Text $content -Expected 'RunRookPreflightHelper(''close''' -Message 'Preflight must run helper close mode after consent or silent implied consent.'
    Assert-Contains -Text $content -Expected 'RunRookPreflightHelper(''record-outcome''' -Message 'Consent cancellation must be recorded by the helper, not Pascal SaveStringToFile.'
    Assert-Contains -Text $content -Expected 'WizardSilent' -Message 'Silent and very-silent installs must imply consent.'
    Assert-Contains -Text $content -Expected 'CurInstallProgressChanged' -Message 'Installer must either re-sweep during [Files] or explicitly document the accepted race in the PR.'
    Assert-Contains -Text $content -Expected 'GetTickCount' -Message '[Files] re-sweep must be time-throttled and not spawn PowerShell on every progress tick.'
    Assert-Contains -Text $content -Expected 'Rook agent server' -Message 'Consent dialog must name Rook agent servers in plain language.'
}
```

Add the call at the bottom:

```powershell
Test-InstallerUsesRookProcessPreflight
```

- [ ] **Step 2: Run the release guard and confirm it fails**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: FAIL on missing preflight directives/helper integration.

- [ ] **Step 3: Add Inno setup directives and package helper/module**

Modify `[Setup]` in `installer/RookSetup.iss`:

```ini
CloseApplications=no
RestartApplications=no
SetupLogging=yes
```

Add these `[Files]` entries near the existing `post_install.py` and `python_runtime_install.py` entries:

```ini
Source: "rook_process_preflight.ps1"; Flags: dontcopy
Source: "process_rebuild_guard.py"; DestDir: "{app}"; Flags: ignoreversion
```

`rook_process_preflight.ps1` must be `dontcopy` because it is needed during `PrepareToInstall`, before normal `[Files]` copy has happened. `process_rebuild_guard.py` must be copied to `{app}` because `post_install.py` imports it after `[Files]`.

- [ ] **Step 4: Add Pascal helper invocation functions**

Add these globals in `[Code]`:

```pascal
  RookPreflightHelperPath: String;
  RookPreflightSummaryPath: String;
  RookPreflightInnoSummaryPath: String;
  RookPreflightLogRoot: String;
  RookPreflightConsentGranted: Boolean;
  RookPreflightLastSweepTick: Cardinal;
```

Add a function with this shape:

```pascal
function RunRookPreflightHelper(const Mode, ExtraArgs: String; var ResultCode: Integer): Boolean;
var
  Args: String;
begin
  Args :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + RookPreflightHelperPath + '"' +
    ' -Mode ' + Mode +
    ' -RookRoot "' + ExpandConstant('{localappdata}\Rook') + '"' +
    ' -LogRoot "' + RookPreflightLogRoot + '"' +
    ' -SummaryPath "' + RookPreflightSummaryPath + '"' +
    ' -InnoSummaryPath "' + RookPreflightInnoSummaryPath + '"' +
    ' -SetupVersion "{#MyAppVersion}" ' + ExtraArgs;
  Log('Rook process preflight: powershell.exe ' + Args);
  Result := Exec('powershell.exe', Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
```

Add `RunRookProcessPreflight(var ErrorMessage: String): Boolean`:

- Extract the helper with `ExtractTemporaryFile('rook_process_preflight.ps1')`.
- Set:
  - `RookPreflightHelperPath := ExpandConstant('{tmp}\rook_process_preflight.ps1')`
  - `RookPreflightLogRoot := ExpandConstant('{localappdata}\Rook\logs')`
  - `RookPreflightSummaryPath := RookPreflightLogRoot + '\post_install_summary.json'`
  - `RookPreflightInnoSummaryPath := RookPreflightLogRoot + '\preflight-summary.txt'`
- Run `enumerate`.
- Read `preflight-summary.txt` with `LoadStringsFromFile` and parse `key=value` lines. Do not parse JSON in Pascal.
- If no conflicts, set `Result := True` and do not show a dialog.
- If conflicts and `WizardSilent`, treat consent as granted.
- If conflicts and interactive, show a `MsgBox` using the helper-provided `message` value verbatim. The dialog must use "close", not "kill" or "terminate".
- If the user chooses Cancel, invoke `RunRookPreflightHelper('record-outcome', '-Outcome cancelled', ResultCode)`, set `ErrorMessage`, and return `False`.
- If consent is granted, run `close`. Exit-code-specific messages:
  - `10`: "Rook agent servers could not be closed. Close Claude, Codex, or the listed owner apps and run Setup again."
  - `20`: "Rook Setup could not inspect running processes. See post_install.log and the setup log."
  - `30` or `40`: "Rook Setup could not complete process preflight. See post_install.log and the setup log."

- [ ] **Step 5: Call preflight from `PrepareToInstall`**

Keep the current component dependency check first. Then call preflight:

```pascal
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';

  if (WizardIsComponentSelected('chirp') or WizardIsComponentSelected('claude') or WizardIsComponentSelected('codex')) and (not WizardIsComponentSelected('mcp')) then
  begin
    Result := 'The Claude, Codex, and Chirp options require the "Python MCP Server" component.' + #13#10 + #13#10 + 'Go back and enable "Python MCP Server", or uncheck the dependent options.';
    Exit;
  end;

  if PostInstallSelected() then
  begin
    if not RunRookProcessPreflight(Result) then
      Exit;
  end;
end;
```

- [ ] **Step 6: Add the cuttable `[Files]` re-sweep**

Implement a small `CurInstallProgressChanged(CurProgress, MaxProgress: Integer)` event that re-runs helper close mode after consent while files are copying. Keep this simple:

- no dialog;
- gate with `GetTickCount` so at least 10 seconds elapse between re-sweeps;
- prefer `ewNoWait` for this best-effort re-sweep so the UI thread does not block on a new `powershell.exe` process during every progress tick;
- no retry loop beyond the helper's bounded close mode;
- log the sweep launch through `Log(...)`; if the implementation uses `ewWaitUntilTerminated`, also log the result code;
- do not abort from the progress callback unless the helper returns `10` repeatedly and the implementation can do so safely.

If the Pascal becomes brittle or the event cannot be made compile-clean quickly, remove this event and add an explicit PR-description note: "Accepted race: clients can respawn during `[Files]`; bounded by observed ~2 minute respawn latency versus typical sub-minute copy, slower under AV scan load."

- [ ] **Step 7: Run the release guard**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 8: Commit**

```powershell
git add installer\RookSetup.iss scripts\tests\release-installer-guards.tests.ps1
git commit -m "feat: add installer process preflight"
```

---

### Task 3: Python Rebuild Guard Primitive

**Files:**
- Create: `installer/process_rebuild_guard.py`
- Create: `mcp_server/tests/test_process_rebuild_guard.py`

- [ ] **Step 1: Write pure unit tests for process matching and guard lifecycle**

Create `mcp_server/tests/test_process_rebuild_guard.py`:

```python
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
GUARD_PATH = REPO_ROOT / "installer" / "process_rebuild_guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("process_rebuild_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def proc(module, pid, ppid, image, created):
    return module.ProcessInfo(
        pid=pid,
        parent_pid=ppid,
        image_path=image,
        command_line="",
        created_utc=created,
    )


def test_matching_roots_count_stub_only_when_child_is_also_matched():
    guard = load_guard()
    root = r"C:\Users\me\AppData\Local\Rook"
    processes = [
        proc(guard, 10, 900, root + r"\venv\Scripts\python.exe", 10.0),
        proc(guard, 11, 10, root + r"\python\cpython-3.11.9\python.exe", 11.0),
        proc(guard, 900, 1, r"C:\Program Files\Claude\claude.exe", 1.0),
    ]

    roots = guard.find_matched_roots(processes, root)

    assert [p.pid for p in roots] == [10]


def test_descendant_closure_includes_out_of_boundary_system_python_child():
    guard = load_guard()
    root = r"C:\Users\me\AppData\Local\Rook"
    processes = [
        proc(guard, 10, 900, root + r"\venv\Scripts\python.exe", 10.0),
        proc(guard, 11, 10, r"C:\Python311\python.exe", 11.0),
        proc(guard, 12, 11, r"C:\Python311\python.exe", 12.0),
    ]

    closure = guard.descendant_closure(processes, {10})

    assert [p.pid for p in closure] == [12, 11, 10]


def test_pid_reuse_rejects_parent_created_after_child():
    guard = load_guard()
    parent = proc(guard, 10, 1, r"C:\parent.exe", 20.0)
    child = proc(guard, 11, 10, r"C:\child.exe", 10.0)

    assert guard.is_valid_parent(parent, child) is False


def test_finalizer_exclusion_removes_self_and_descendants():
    guard = load_guard()
    root = r"C:\Users\me\AppData\Local\Rook"
    processes = [
        proc(guard, 100, 50, root + r"\python\cpython-3.11.9\python.exe", 100.0),
        proc(guard, 101, 100, root + r"\venv\Scripts\python.exe", 101.0),
        proc(guard, 200, 900, root + r"\venv\Scripts\python.exe", 200.0),
    ]

    kill_set = guard.compute_kill_order(processes, root, exclude_root_pids={100})

    assert [p.pid for p in kill_set] == [200]


def test_rebuild_guard_stands_down_after_success():
    guard = load_guard()
    events: list[str] = []

    class FakeTerminator:
        def close_processes(self, label, processes):
            events.append(f"{label}:{[p.pid for p in processes]}")
            return guard.CloseResult(ok=True, closed_pids=[p.pid for p in processes], failures=[])

    snapshots = [
        [proc(guard, 10, 900, r"C:\Rook\venv\Scripts\python.exe", 10.0)],
        [],
    ]

    provider = guard.SequenceSnapshotProvider(snapshots)
    guard_instance = guard.RebuildGuard(
        label="rook-mcp",
        rook_root=r"C:\Rook",
        snapshot_provider=provider,
        terminator=FakeTerminator(),
        current_pid=999,
        sweep_interval_seconds=0,
        run_background=False,
    )
    with guard_instance:
        pass

    guard_instance.sweep_once()
    assert events == ["rook-mcp:[10]"]
    assert provider.calls == 1
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_process_rebuild_guard.py -q
```

Expected: FAIL because `installer/process_rebuild_guard.py` does not exist.

- [ ] **Step 3: Create the process guard module**

Create `installer/process_rebuild_guard.py` with:

```python
"""Stdlib-only process matching and rebuild guard for Rook installer finalization."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import threading
import time


@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    parent_pid: int | None
    image_path: str
    command_line: str = ""
    created_utc: float | None = None


@dataclass(frozen=True)
class CloseResult:
    ok: bool
    closed_pids: list[int]
    failures: list[str]


def normalize_root(path: str | Path) -> str:
    return str(Path(path)).replace("/", "\\").rstrip("\\").lower() + "\\"


def is_under_root(process: ProcessInfo, rook_root: str | Path) -> bool:
    image = process.image_path.replace("/", "\\").lower()
    return image.startswith(normalize_root(rook_root))


def by_pid(processes: list[ProcessInfo]) -> dict[int, ProcessInfo]:
    return {p.pid: p for p in processes}


def is_valid_parent(parent: ProcessInfo, child: ProcessInfo) -> bool:
    if child.parent_pid != parent.pid:
        return False
    if parent.created_utc is None or child.created_utc is None:
        return True
    return parent.created_utc <= child.created_utc
```

Continue the implementation with:

- `find_matched_roots(processes, rook_root) -> list[ProcessInfo]`
- `descendant_closure(processes, root_pids) -> list[ProcessInfo]`, descendants before ancestors
- `compute_kill_order(processes, rook_root, exclude_root_pids) -> list[ProcessInfo]`
- `SequenceSnapshotProvider` for tests
  - exposes `calls: int` so tests can assert deterministic sweep counts
- `WindowsSnapshotProvider` using stdlib `ctypes` on Windows:
  - Toolhelp snapshot for PID/PPID
  - `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)`
  - `QueryFullProcessImageNameW`
  - `GetProcessTimes` for creation time
- `WindowsTerminator` using stdlib `ctypes` `OpenProcess(PROCESS_TERMINATE)` and `TerminateProcess`
- `RebuildGuard` context manager:
  - one immediate sweep on entry
  - optional background thread for production, controlled by `run_background=True`
  - `stop()` on exit without a final drain sweep
  - `sweep_once()` is a no-op after stop so tests can pin the stand-down boundary
  - records whether the thread died unexpectedly
  - exposes close failures for `post_install.py`

The pure functions must pass the tests before the Windows adapter is wired into `post_install.py`.

- [ ] **Step 4: Run the guard tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_process_rebuild_guard.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add installer\process_rebuild_guard.py mcp_server\tests\test_process_rebuild_guard.py
git commit -m "test: cover rebuild guard process matching"
```

---

### Task 4: Always-On Logging And Stable Summary

**Files:**
- Modify: `installer/post_install.py`
- Modify: `mcp_server/tests/test_python_runtime_install.py`
- Modify: `mcp_server/tests/test_post_install_encoding.py`

- [ ] **Step 1: Add failing tests for summary extension and last-gasp logging**

Append to `mcp_server/tests/test_python_runtime_install.py`:

```python
def test_post_install_extends_seeded_summary(tmp_path: Path) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    logs = runtime_root / "logs"
    logs.mkdir(parents=True)
    summary = logs / "post_install_summary.json"
    summary.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "phase_reached": "preflight",
                "preflight": {"server_count": 5, "owners": ["Claude", "Codex"]},
            }
        ),
        encoding="utf-8",
    )

    post_install._configure_install_logging(runtime_root)
    post_install._update_install_summary(runtime_root, phase_reached="finalizer-started", final_outcome="running")

    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["preflight"]["server_count"] == 5
    assert payload["phase_reached"] == "finalizer-started"
    assert payload["final_outcome"] == "running"


def test_last_gasp_handler_writes_traceback(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"

    def boom() -> int:
        raise RuntimeError("forced install failure")

    monkeypatch.setattr(post_install, "main", boom)

    result = post_install._run_with_last_gasp(runtime_root=runtime_root)

    assert result == 1
    log = (runtime_root / "logs" / "post_install.log").read_text(encoding="utf-8")
    assert "forced install failure" in log
    assert "Traceback" in log
```

Extend `mcp_server/tests/test_post_install_encoding.py` if the source pin does not already catch the new functions:

```python
def test_post_install_summary_and_log_paths_use_utf8_source_pin():
    raw = POST_INSTALL.read_text(encoding="utf-8")
    assert "encoding=\"utf-8\"" in raw
    assert "post_install_summary.json" in raw
    assert "post_install.log" in raw
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -k "summary or last_gasp" -q
python -m pytest mcp_server\tests\test_post_install_encoding.py -q
```

Expected: FAIL on missing logging helpers.

- [ ] **Step 3: Implement logging and summary helpers**

In `installer/post_install.py`, add imports:

```python
import logging
import time
import traceback
```

Add helpers near `get_runtime_paths`:

```python
_INSTALL_LOGGER = logging.getLogger("rook.post_install")
_INSTALL_LOGGING_CONFIGURED = False


def _summary_path(runtime_root: Path) -> Path:
    return runtime_root / "logs" / "post_install_summary.json"


def _post_install_log_path(runtime_root: Path) -> Path:
    return runtime_root / "logs" / "post_install.log"


def _configure_install_logging(runtime_root: Path) -> None:
    global _INSTALL_LOGGING_CONFIGURED
    if _INSTALL_LOGGING_CONFIGURED:
        return
    log_path = _post_install_log_path(runtime_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for existing in list(_INSTALL_LOGGER.handlers):
        _INSTALL_LOGGER.removeHandler(existing)
        existing.close()
    handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    _INSTALL_LOGGER.setLevel(logging.INFO)
    _INSTALL_LOGGER.addHandler(handler)
    _INSTALL_LOGGING_CONFIGURED = True
    _INSTALL_LOGGER.info("post_install logging configured")
```

Add summary helpers:

```python
def _read_install_summary(runtime_root: Path) -> dict:
    path = _summary_path(runtime_root)
    if not path.exists():
        return {"schema_version": 1}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schema_version": 1}
    return payload if isinstance(payload, dict) else {"schema_version": 1}


def _write_install_summary(runtime_root: Path, payload: dict) -> None:
    payload = {"schema_version": 1, **payload}
    path = _summary_path(runtime_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _update_install_summary(runtime_root: Path, **updates) -> None:
    payload = _read_install_summary(runtime_root)
    payload.update({k: v for k, v in updates.items() if v is not None})
    _write_install_summary(runtime_root, payload)
```

Add last-gasp wrapper:

```python
def _run_with_last_gasp(runtime_root: Path | None = None) -> int:
    root = runtime_root or get_runtime_root()
    try:
        _configure_install_logging(root)
        return main()
    except SystemExit:
        raise
    except Exception:
        _configure_install_logging(root)
        _INSTALL_LOGGER.error("post_install crashed:\n%s", traceback.format_exc())
        _update_install_summary(root, phase_reached="finalizer-crashed", final_outcome="failed")
        return 1
```

Change the script entrypoint:

```python
if __name__ == "__main__":
    sys.exit(_run_with_last_gasp())
```

Inside `main()`, after computing `runtime_root`, call `_configure_install_logging(runtime_root)` and `_update_install_summary(runtime_root, phase_reached="finalizer-started", final_outcome="running")` before any config reads or venv work.

Update `_run_install_command` so command, stdout, and stderr are logged into `_INSTALL_LOGGER` in addition to printing.

- [ ] **Step 4: Run the focused tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -k "summary or last_gasp" -q
python -m pytest mcp_server\tests\test_post_install_encoding.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add installer\post_install.py mcp_server\tests\test_python_runtime_install.py mcp_server\tests\test_post_install_encoding.py
git commit -m "feat: add continuous post-install logging"
```

---

### Task 5: Guarded Venv Rebuild And One Full Retry

**Files:**
- Modify: `installer/post_install.py`
- Modify: `mcp_server/tests/test_python_runtime_install.py`

- [ ] **Step 1: Add failing tests for guard windows and retry**

Append to `mcp_server/tests/test_python_runtime_install.py`:

```python
def test_install_from_wheelhouse_uses_guard_and_retries_full_rebuild(tmp_path: Path, monkeypatch) -> None:
    runtime = load_runtime_install()
    post_install = load_post_install()
    layout = runtime.RuntimeLayout.from_rook_root(tmp_path / "Rook", "3.11.9")

    layout.private_python.parent.mkdir(parents=True)
    layout.private_python.write_text("private python", encoding="utf-8")
    layout.wheelhouse.mkdir(parents=True)
    layout.bootstrap_lock.parent.mkdir(parents=True, exist_ok=True)
    layout.bootstrap_lock.write_text("pip==26.1.2 --hash=sha256:abc\n", encoding="utf-8")
    layout.rook_lock.write_text("rook-mcp==1.5.10 --hash=sha256:def\n", encoding="utf-8")
    layout.runtime_manifest.write_text('{"schema_version":1}', encoding="utf-8")
    stale_python = post_install.get_venv_python(layout.rook_venv)
    stale_python.parent.mkdir(parents=True)
    stale_python.write_text("stale", encoding="utf-8")

    guard_events: list[str] = []

    class FakeGuard:
        def __init__(self, label, **kwargs):
            self.label = label
        def __enter__(self):
            guard_events.append(f"enter:{self.label}")
            return self
        def __exit__(self, exc_type, exc, tb):
            guard_events.append(f"exit:{self.label}")
            return False

    monkeypatch.setattr(post_install, "_make_rebuild_guard", lambda label, runtime_root: FakeGuard(label))

    attempts = {"install": 0}

    def fake_run(command, *, env, timeout=post_install.INSTALL_COMMAND_TIMEOUT_SECONDS):
        if command[:3] == [str(layout.private_python), "-m", "venv"]:
            created_python = post_install.get_venv_python(Path(command[3]))
            created_python.parent.mkdir(parents=True, exist_ok=True)
            created_python.write_text("fresh", encoding="utf-8")
        if "-m" in command and "pip" in command and "install" in command and str(layout.rook_lock) in command:
            attempts["install"] += 1
            if attempts["install"] == 1:
                return subprocess.CompletedProcess(command, 1, stdout="", stderr="access denied")
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="Looking in links: C:/Rook/app/python-wheelhouse\nNo broken requirements found.",
            stderr="",
        )

    monkeypatch.setattr(post_install, "_run_install_command", fake_run)

    venv_python = post_install._install_from_wheelhouse(
        "rook-mcp",
        layout,
        layout.rook_venv,
        layout.rook_lock,
        "rook",
    )

    assert venv_python == stale_python
    assert attempts["install"] == 2
    assert guard_events == ["enter:rook-mcp", "exit:rook-mcp", "enter:rook-mcp", "exit:rook-mcp"]


def test_chirp_install_uses_separate_guard_window(tmp_path: Path, monkeypatch) -> None:
    post_install = load_post_install()
    runtime_root = tmp_path / "Rook"
    chirp_dir = runtime_root / "app" / "chirp"
    chirp_dir.mkdir(parents=True)
    labels: list[str] = []

    monkeypatch.setattr(
        post_install,
        "_install_from_wheelhouse",
        lambda label, layout, venv_dir, lock, runtime_name: labels.append(label) or (venv_dir / "Scripts" / "python.exe"),
    )

    assert post_install.install_chirp(chirp_dir, runtime_root) is True
    assert labels == ["Chirp"]
```

- [ ] **Step 2: Run focused tests and confirm they fail**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -k "guard or retry or chirp_install" -q
```

Expected: FAIL on missing `_make_rebuild_guard` and retry behavior.

- [ ] **Step 3: Integrate `process_rebuild_guard` into `post_install.py`**

Import the module:

```python
import process_rebuild_guard
```

Add:

```python
def _make_rebuild_guard(label: str, runtime_root: Path):
    return process_rebuild_guard.RebuildGuard(
        label=label,
        rook_root=str(runtime_root),
        current_pid=os.getpid(),
    )
```

Refactor `_install_from_wheelhouse` into:

- `_install_from_wheelhouse_once(...) -> tuple[Path | None, str | None]`
  - Returns `(venv_python, None)` on success.
  - Returns `(None, "remove" | "create" | "bootstrap" | "install" | "validation" | "pip-check")` on failure.
- `_install_from_wheelhouse(...) -> Path | None`
  - Opens `with _make_rebuild_guard(label, layout.rook_root):` before stale delete/create/bootstrap/install.
  - If the first attempt fails at `remove`, `create`, `bootstrap`, or `install`, logs the failure stage, runs exactly one full retry from stale delete -> create -> pip.
  - Does not retry `pip-check` or release-validation failures.
  - Updates `post_install_summary.json` with guard label, retry count, and outcome.

Do not run the guard during doctor validation, config writes, manifest writes, or install-state work after pip succeeds.

- [ ] **Step 4: Run focused tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_python_runtime_install.py -k "guard or retry or chirp_install" -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add installer\post_install.py mcp_server\tests\test_python_runtime_install.py
git commit -m "feat: guard installer venv rebuilds"
```

---

### Task 6: Minimal #240 Manifest Cleanup And Parity

**Files:**
- Modify: `installer/RookSetup.iss`
- Modify: `installer/post_install.py`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `mcp_server/tests/test_python_runtime_install.py`

- [ ] **Step 1: Add failing installer guard for child manifest deletes and no C# scope**

Append to `scripts/tests/release-installer-guards.tests.ps1`:

```powershell
function Test-InstallerDeletesStaleChildChatManifests {
    $content = Get-Content -Path $InstallerScript -Raw
    foreach ($runtime in @('net8.0', 'net7.0', 'net48')) {
        Assert-Contains -Text $content -Expected "RookNative\$runtime\RookChatService.json" -Message "Installer must delete stale $runtime child chat manifest before [Files]."
    }
}
```

Add the call at the bottom:

```powershell
Test-InstallerDeletesStaleChildChatManifests
```

- [ ] **Step 2: Add failing manifest parity test**

Append to `mcp_server/tests/test_python_runtime_install.py`:

```python
def test_write_chat_service_manifest_writes_root_and_existing_child_manifests(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    post_install = load_post_install()
    appdata = tmp_path / "AppData" / "Roaming"
    plugin_dir = appdata / "McNeel" / "Rhinoceros" / "8.0" / "Plug-ins" / "RookNative"
    plugin_dir.mkdir(parents=True)
    for runtime in ("net8.0", "net7.0", "net48", "net9.0"):
        (plugin_dir / runtime).mkdir()
    mcp_server_dir = tmp_path / "Rook" / "app" / "mcp_server"
    mcp_server_dir.mkdir(parents=True)
    python_path = tmp_path / "Rook" / "venv" / "Scripts" / "python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_text("fake", encoding="utf-8")
    monkeypatch.setenv("APPDATA", str(appdata))

    assert post_install.write_chat_service_manifest(mcp_server_dir, str(python_path)) is True

    root_payload = (plugin_dir / "RookChatService.json").read_text(encoding="utf-8")
    for runtime in ("net8.0", "net7.0", "net48"):
        child_payload = (plugin_dir / runtime / "RookChatService.json").read_text(encoding="utf-8")
        assert child_payload == root_payload
        assert json.loads(child_payload)["module"] == "rook.agent.chat.service_main"
    assert not (plugin_dir / "net9.0" / "RookChatService.json").exists()
    assert "unknown managed runtime child directory" in capsys.readouterr().out
```

- [ ] **Step 3: Run focused tests and confirm they fail**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
python -m pytest mcp_server\tests\test_python_runtime_install.py -k "chat_service_manifest" -q
```

Expected: FAIL until installer delete entries and multi-write logic exist.

- [ ] **Step 4: Add `[InstallDelete]` entries**

In the existing `[InstallDelete]` section before `[Files]`, add:

```ini
; Remove stale per-runtime chat manifests before post_install writes fresh copies.
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\RookChatService.json"
```

- [ ] **Step 5: Write root and child manifests from one payload**

Replace the single-path write in `write_chat_service_manifest` with:

```python
payload = json.dumps(manifest, indent=2)
targets = [plugin_dir / "RookChatService.json"]
known_children = set(MANAGED_COMPANION_RUNTIMES)
for runtime in MANAGED_COMPANION_RUNTIMES:
    child_dir = plugin_dir / runtime
    if child_dir.is_dir():
        targets.append(child_dir / "RookChatService.json")
for child in plugin_dir.iterdir():
    if child.is_dir() and child.name.startswith("net") and child.name not in known_children:
        print(f"WARNING: unknown managed runtime child directory: {child}")
        _INSTALL_LOGGER.warning("unknown managed runtime child directory: %s", child)
for manifest_path in targets:
    manifest_path.write_text(payload, encoding="utf-8")
    print(f"Wrote chat service manifest: {manifest_path}")
    _INSTALL_LOGGER.info("wrote chat service manifest: %s", manifest_path)
```

Update `_update_install_summary(...)` with the manifest target paths after successful writes.

- [ ] **Step 6: Run focused tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
python -m pytest mcp_server\tests\test_python_runtime_install.py -k "chat_service_manifest" -q
python -m pytest mcp_server\tests\test_post_install_encoding.py -q
```

Expected: PASS.

- [ ] **Step 7: Confirm #240 tripwire**

Run:

```powershell
(@(git diff --name-only main...HEAD) + @(git diff --name-only)) |
    Select-String -Pattern '^src/Rook/'
```

Expected: no output. If any `src/Rook/**` file appears, stop and split #240 out. This check must inspect both already committed task work and any still-uncommitted files.

- [ ] **Step 8: Commit**

```powershell
git add installer\RookSetup.iss installer\post_install.py scripts\tests\release-installer-guards.tests.ps1 mcp_server\tests\test_python_runtime_install.py
git commit -m "fix: refresh companion child chat manifests"
```

---

### Task 7: Final Automated Verification

**Files:**
- Existing files from prior tasks

- [ ] **Step 1: Run focused Python installer tests**

Run:

```powershell
python -m pytest mcp_server\tests\test_process_rebuild_guard.py mcp_server\tests\test_python_runtime_install.py mcp_server\tests\test_post_install_encoding.py -q
```

Expected: PASS.

- [ ] **Step 2: Run PowerShell helper and installer guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\rook-process-preflight.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: PASS.

- [ ] **Step 3: Run broader non-Rhino Python smoke**

Run:

```powershell
python -m pytest mcp_server\tests -m "not requires_rhino" -q
```

Expected: PASS or known existing baseline only. If failures occur, compare to `main` before claiming regressions.

- [ ] **Step 4: Compile the installer script**

Run:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.5.12-dev "C:\Users\aryan\source\repos\Rook\installer\RookSetup.iss"
```

Expected: installer build succeeds, writes `installer\output\Rook-Setup-1.5.12-dev.exe`, and packages `rook_process_preflight.ps1`, `post_install.py`, `python_runtime_install.py`, and `process_rebuild_guard.py`. This assumes the staged private Python runtime and wheelhouse payloads from the v1.5.11 build are still present under `installer\runtime`; on a clean checkout, run the build-release staging steps for those payloads before compiling the installer.

- [ ] **Step 5: Commit any verification-only guard fixes**

Only commit if steps 1-4 required small guard-script or packaging corrections:

```powershell
git add installer\RookSetup.iss installer\post_install.py installer\process_rebuild_guard.py installer\rook_process_preflight.ps1 scripts\tests\release-installer-guards.tests.ps1 scripts\tests\rook-process-preflight.tests.ps1 mcp_server\tests\test_process_rebuild_guard.py mcp_server\tests\test_python_runtime_install.py mcp_server\tests\test_post_install_encoding.py
git commit -m "test: verify installer conflict handling"
```

---

### Task 8: Live Installer Smoke Before PR

**Files:**
- Generated: `installer/output/installer-conflict-smoke-1.5.12-dev.json`

- [ ] **Step 1: Record pre-install process table**

Run a CIM query before launching the installer:

```powershell
$rookRoot = Join-Path $env:LOCALAPPDATA 'Rook'
Get-CimInstance Win32_Process |
  Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($rookRoot, [StringComparison]::OrdinalIgnoreCase) } |
  Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine |
  ConvertTo-Json -Depth 4 |
  Set-Content -Path installer\output\preflight-processes-before.json -Encoding UTF8
```

Expected: existing live MCP server pairs from Claude/Codex are present. If no conflicts exist, start Claude/Codex sessions that use Rook MCP before continuing.

- [ ] **Step 2: Run interactive upgrade smoke**

Run the freshly built installer normally over the current install while Claude and Codex sessions remain open.

Checklist:

- Consent dialog appears only if conflicts exist.
- Dialog shows logical server count and owner names, not raw PID count.
- Continuing closes all matched roots plus descendants.
- No orphaned base interpreter remains after the pre-copy close.
- `post_install.log` starts with the rotated run header and includes preflight, helper close, finalizer start, guard windows, pip output, manifest writes, and final outcome.
- `post_install_summary.json` parses and includes preflight count/owners, closed count, guard windows, retry count, manifest paths, and outcome.
- The `[Files]` copy duration is recorded. State it as observed on this machine and note that slower disks or antivirus scan load can widen the accepted respawn window.
- Root and child `RookChatService.json` files are byte-identical.
- Claude/Codex reconnect after installation.

- [ ] **Step 3: Verify process table after install**

Run:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith((Join-Path $env:LOCALAPPDATA 'Rook'), [StringComparison]::OrdinalIgnoreCase) } |
  Select-Object ProcessId, ParentProcessId, ExecutablePath, CommandLine |
  ConvertTo-Json -Depth 4 |
  Set-Content -Path installer\output\preflight-processes-after.json -Encoding UTF8
```

Expected: no orphaned old process remains; any Rook processes are post-install respawns from owning clients.

- [ ] **Step 4: Run silent smoke**

Run the same installer with `/SILENT`:

```powershell
installer\output\Rook-Setup-1.5.12-dev.exe /SILENT
```

Expected: implied consent branch closes conflicts, logs evidence, and completes without a dialog.

- [ ] **Step 5: Write smoke manifest**

Create `installer/output/installer-conflict-smoke-1.5.12-dev.json` with:

```json
{
  "schema_version": 1,
  "scenario": "installer-process-conflict-upgrade",
  "interactive": {
    "owners": ["Claude", "Codex"],
    "server_count": 5,
    "consent_dialog_seen": true,
    "all_process_pairs_closed": true,
    "orphaned_interpreters_after_preflight": 0,
    "files_copy_duration_seconds": 0,
    "files_respawn_observed": false,
    "rebuild_guard_windows": ["rook-mcp", "chirp"],
    "summary_json_ok": true,
    "chat_manifests_byte_identical": true,
    "clients_reconnected": true
  },
  "silent": {
    "completed": true,
    "implied_consent_logged": true
  },
  "logs": {
    "post_install_log": "%LOCALAPPDATA%/Rook/logs/post_install.log",
    "post_install_summary": "%LOCALAPPDATA%/Rook/logs/post_install_summary.json"
  }
}
```

Fill real values from the run. Do not publish the PR until this manifest and the final logs support the checklist.

- [ ] **Step 6: Final commit if smoke notes are committed**

If the smoke manifest is committed:

```powershell
git add installer\output\installer-conflict-smoke-1.5.12-dev.json
git commit -m "test: record installer conflict smoke"
```

If not committed, paste its contents and the key log excerpts into the PR description.

---

## Final Verification Before PR

Run:

```powershell
git status --short
python -m pytest mcp_server\tests\test_process_rebuild_guard.py mcp_server\tests\test_python_runtime_install.py mcp_server\tests\test_post_install_encoding.py -q
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\rook-process-preflight.tests.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DMyAppVersion=1.5.12-dev "C:\Users\aryan\source\repos\Rook\installer\RookSetup.iss"
```

Expected:

- Worktree contains only intentional implementation, test, and evidence changes.
- Focused pytest suite passes.
- PowerShell helper tests pass.
- Release installer guard tests pass.
- Inno compile succeeds.
- Live interactive and `/SILENT` smoke evidence exists before PR open.
- `(@(git diff --name-only main...HEAD) + @(git diff --name-only)) | Select-String -Pattern '^src/Rook/'` prints nothing for #240.

## PR Notes

The PR description must include:

- #237 conflict handling summary.
- #240 manifest cleanup summary.
- Confirmation that `CloseApplications=no`, `RestartApplications=no`, and `SetupLogging=yes` are set.
- Preflight consent UX screenshot or exact text.
- Whether `CurInstallProgressChanged` re-sweep shipped. If it did not, state the accepted `[Files]` respawn race explicitly with observed copy duration and the slower-disk/AV caveat.
- Summary of interactive and silent smoke results.
- Path to `post_install.log` and `post_install_summary.json`.
- Confirmation that child manifests are byte-identical to root.
