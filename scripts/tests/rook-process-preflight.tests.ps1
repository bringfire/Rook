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
