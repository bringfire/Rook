# validate-local-testing-stack.ps1
#
# Orchestrates the installed-runtime and live proof gates for local Rook testing.

[CmdletBinding()]
param(
    [switch]$ReleaseReadiness,
    [switch]$KeepRhinoOnFailure,
    [string]$RhinoExe = 'C:\Program Files\Rhino 8\System\Rhino.exe'
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$DeployGuards = Join-Path $RepoRoot 'scripts\tests\deploy-local-testing-guards.tests.ps1'
$ReleaseGuards = Join-Path $RepoRoot 'scripts\tests\release-installer-guards.tests.ps1'
$StackGuards = Join-Path $RepoRoot 'scripts\tests\local-testing-stack-guards.tests.ps1'
$RuntimeRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Rook'
$InstallRoot = Join-Path $RuntimeRoot 'app'
$DataRoot = Join-Path $RuntimeRoot 'data'
$ChirpHome = Join-Path $InstallRoot 'chirp'
$VenvPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
$ArtifactRoot = Join-Path $RepoRoot 'artifacts\local-testing'
$GateResults = New-Object System.Collections.Generic.List[object]

function New-GateArtifactDir {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $path = Join-Path $ArtifactRoot "$stamp-release-readiness"
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    return $path
}

function New-GateEnvelope {
    param(
        [Parameter(Mandatory = $true)][string]$Gate,
        [bool]$Success,
        [AllowNull()][string]$FailureLabel,
        [Parameter(Mandatory = $true)][string[]]$Command,
        [datetime]$Started,
        [datetime]$Ended,
        [AllowNull()][string]$StdoutPath,
        [AllowNull()][string]$StderrPath,
        [hashtable]$Details = @{},
        [hashtable]$Cleanup = @{ attempted = $false; success = $null; label = $null; details = @{} }
    )

    return [ordered]@{
        gate = $Gate
        success = $Success
        failure_label = $FailureLabel
        command = $Command
        duration_seconds = ($Ended - $Started).TotalSeconds
        stdout_path = $StdoutPath
        stderr_path = $StderrPath
        details = $Details
        cleanup = $Cleanup
    }
}

function Save-GateEnvelope {
    param(
        [Parameter(Mandatory = $true)][string]$ArtifactDir,
        [Parameter(Mandatory = $true)]$Envelope
    )

    $GateResults.Add($Envelope) | Out-Null
    $Envelope | ConvertTo-Json -Depth 12 | Set-Content -Path (Join-Path $ArtifactDir "$($Envelope.gate).json") -Encoding UTF8
}

function Write-TopLevelManifest {
    param(
        [Parameter(Mandatory = $true)][string]$ArtifactDir,
        [bool]$Success,
        [AllowNull()][string]$FailureLabel
    )

    $branch = ((& git -C $RepoRoot rev-parse --abbrev-ref HEAD 2>$null) -join '').Trim()
    $commit = ((& git -C $RepoRoot rev-parse HEAD 2>$null) -join '').Trim()
    $dirtyText = ((& git -C $RepoRoot status --short 2>$null) -join '')
    $manifest = [ordered]@{
        source_repo = $RepoRoot
        git_commit = $commit
        git_branch = $branch
        dirty_tree = -not [string]::IsNullOrWhiteSpace($dirtyText)
        success = $Success
        failure_label = $FailureLabel
        keep_rhino_on_failure = [bool]$KeepRhinoOnFailure
        appdata = @{
            runtime_root = $RuntimeRoot
            install_root = $InstallRoot
            data_root = $DataRoot
            chirp_home = $ChirpHome
            venv_python = $VenvPython
        }
        gates = @($GateResults.ToArray())
    }
    $manifest | ConvertTo-Json -Depth 14 | Set-Content -Path (Join-Path $ArtifactDir 'manifest.json') -Encoding UTF8
}

function ConvertTo-CommandParts {
    param([Parameter(Mandatory = $true)]$Command)

    $parts = $Command
    while (($parts -is [array]) -and $parts.Count -eq 1 -and ($parts[0] -is [array])) {
        $parts = $parts[0]
    }
    return [string[]]@($parts)
}

function Invoke-ExternalChecked {
    param(
        [Parameter(Mandatory = $true)][string[]]$Command,
        [Parameter(Mandatory = $true)][string]$StdoutPath,
        [Parameter(Mandatory = $true)][string]$StderrPath
    )

    $exe = $Command[0]
    $args = @()
    if ($Command.Count -gt 1) {
        $args = @($Command[1..($Command.Count - 1)])
    }
    & $exe @args 1>> $StdoutPath 2>> $StderrPath
    if ($LASTEXITCODE -ne 0) {
        throw "$($Command -join ' ') exited with code $LASTEXITCODE"
    }
}

function Invoke-GateCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Gate,
        [Parameter(Mandatory = $true)][string]$FailureLabel,
        [Parameter(Mandatory = $true)][string]$ArtifactDir,
        [Parameter(Mandatory = $true)][object[]]$Commands
    )

    $stdout = Join-Path $ArtifactDir "$Gate.stdout.log"
    $stderr = Join-Path $ArtifactDir "$Gate.stderr.log"
    $started = Get-Date
    try {
        foreach ($command in $Commands) {
            Invoke-ExternalChecked -Command (ConvertTo-CommandParts -Command $command) -StdoutPath $stdout -StderrPath $stderr
        }
        $success = $true
        $label = $null
        $details = @{}
    } catch {
        $success = $false
        $label = $FailureLabel
        $details = @{ error = $_.Exception.Message }
    }
    $ended = Get-Date
    $commandText = @($Commands | ForEach-Object { (ConvertTo-CommandParts -Command $_) -join ' ' })
    $payload = New-GateEnvelope -Gate $Gate -Success $success -FailureLabel $label -Command $commandText -Started $started -Ended $ended -StdoutPath $stdout -StderrPath $stderr -Details $details
    Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
    if (-not $success) {
        throw "$FailureLabel`: $($details.error)"
    }
}

function Assert-NoRhinoRunningForReleaseReadiness {
    param([Parameter(Mandatory = $true)][string]$ArtifactDir)

    $started = Get-Date
    $rhino = Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
    $ended = Get-Date
    if ($rhino) {
        $details = @{ processes = @($rhino | Select-Object ProcessName, Id, Path) }
        $payload = New-GateEnvelope -Gate 'rhino_preflight' -Success $false -FailureLabel 'rhino_already_running' -Command @('Get-Process Rhino') -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details $details
        Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
        throw 'rhino_already_running'
    }

    $payload = New-GateEnvelope -Gate 'rhino_preflight' -Success $true -FailureLabel $null -Command @('Get-Process Rhino') -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details @{}
    Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
}

function Reset-InstalledChirpForReleaseReadiness {
    param([Parameter(Mandatory = $true)][string]$ArtifactDir)

    $started = Get-Date
    $chirpPython = Join-Path $ChirpHome '.venv\Scripts\python.exe'
    $terminated = @()
    $removedDiscovery = @()
    try {
        $escapedChirpPython = [regex]::Escape($chirpPython)
        $processes = Get-CimInstance Win32_Process | Where-Object {
            $_.CommandLine -and
            $_.CommandLine -match $escapedChirpPython -and
            $_.CommandLine -match '(^|\s|")-m\s+chirp(\s|$)'
        }
        foreach ($process in $processes) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            $terminated += [int]$process.ProcessId
        }

        $discoveryRoot = Join-Path ([System.IO.Path]::GetTempPath()) 'rook'
        if (Test-Path -LiteralPath $discoveryRoot) {
            foreach ($file in Get-ChildItem -LiteralPath $discoveryRoot -Filter 'chirp-service-*.json' -ErrorAction SilentlyContinue) {
                $removedDiscovery += $file.FullName
                Remove-Item -LiteralPath $file.FullName -Force -ErrorAction Stop
            }
        }

        $ended = Get-Date
        $payload = New-GateEnvelope -Gate 'chirp_preflight' -Success $true -FailureLabel $null -Command @('Stop installed Chirp sidecars') -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details @{
            chirp_python = $chirpPython
            terminated_pids = $terminated
            removed_discovery_files = $removedDiscovery
        }
        Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
    } catch {
        $ended = Get-Date
        $payload = New-GateEnvelope -Gate 'chirp_preflight' -Success $false -FailureLabel 'chirp_cleanup_failed' -Command @('Stop installed Chirp sidecars') -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details @{
            chirp_python = $chirpPython
            error = $_.Exception.Message
        }
        Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
        throw "chirp_cleanup_failed: $($_.Exception.Message)"
    }
}

function Invoke-ProofModuleGate {
    param(
        [Parameter(Mandatory = $true)][string]$ArtifactDir,
        [Parameter(Mandatory = $true)][string]$Gate,
        [Parameter(Mandatory = $true)][string]$FailureLabel,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$OutPath
    )

    & $VenvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        if (Test-Path $OutPath) {
            $payload = Get-Content -LiteralPath $OutPath -Raw | ConvertFrom-Json
            $GateResults.Add($payload) | Out-Null
        } else {
            $started = Get-Date
            $ended = Get-Date
            $payload = New-GateEnvelope -Gate $Gate -Success $false -FailureLabel $FailureLabel -Command @($VenvPython + ' ' + ($Arguments -join ' ')) -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details @{ error = "$Gate failed without writing $OutPath" }
            Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
        }
        throw $FailureLabel
    }

    if (Test-Path $OutPath) {
        $payload = Get-Content -LiteralPath $OutPath -Raw | ConvertFrom-Json
        $GateResults.Add($payload) | Out-Null
    } else {
        $started = Get-Date
        $ended = Get-Date
        $payload = New-GateEnvelope -Gate $Gate -Success $false -FailureLabel $FailureLabel -Command @($VenvPython + ' ' + ($Arguments -join ' ')) -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details @{ error = "$Gate succeeded without writing $OutPath" }
        Save-GateEnvelope -ArtifactDir $ArtifactDir -Envelope $payload
        throw $FailureLabel
    }
}

function Invoke-ReleaseReadiness {
    $artifactDir = New-GateArtifactDir
    Write-Host "Artifact directory: $artifactDir"
    try {
        Invoke-GateCommand -Gate 'static_guard' -FailureLabel 'static_guard_failed' -ArtifactDir $artifactDir -Commands @(
            ,@('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $DeployGuards),
            ,@('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $StackGuards)
        )

        Invoke-GateCommand -Gate 'release_non_interference' -FailureLabel 'release_non_interference_failed' -ArtifactDir $artifactDir -Commands @(
            ,@('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ReleaseGuards)
        )

        Assert-NoRhinoRunningForReleaseReadiness -ArtifactDir $artifactDir

        Invoke-GateCommand -Gate 'local_deploy' -FailureLabel 'local_deploy_failed' -ArtifactDir $artifactDir -Commands @(
            ,@('powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $DeployScript)
        )

        if (-not (Test-Path $VenvPython)) {
            $started = Get-Date
            $ended = Get-Date
            $payload = New-GateEnvelope -Gate 'installed_runtime' -Success $false -FailureLabel 'installed_runtime_failed' -Command @($VenvPython, '-m', 'rook.local_testing_proof', 'installed-runtime') -Started $started -Ended $ended -StdoutPath $null -StderrPath $null -Details @{ error = "Installed venv Python not found: $VenvPython" }
            Save-GateEnvelope -ArtifactDir $artifactDir -Envelope $payload
            throw 'installed_runtime_failed'
        }

        $env:ROOK_INSTALL_ROOT = $InstallRoot.Replace('\', '/')
        $env:ROOK_DATA_DIR = $DataRoot.Replace('\', '/')
        $env:ROOK_MODE = 'release'
        $env:CHIRP_HOME = $ChirpHome.Replace('\', '/')

        $installedRuntimeJson = Join-Path $artifactDir 'installed-runtime.json'
        Invoke-ProofModuleGate -ArtifactDir $artifactDir -Gate 'installed_runtime' -FailureLabel 'installed_runtime_failed' -Arguments @('-m', 'rook.local_testing_proof', 'installed-runtime', '--out', $installedRuntimeJson) -OutPath $installedRuntimeJson

        Reset-InstalledChirpForReleaseReadiness -ArtifactDir $artifactDir

        Assert-NoRhinoRunningForReleaseReadiness -ArtifactDir $artifactDir

        $ownedJson = Join-Path $artifactDir 'owned-release-readiness.json'
        $args = @(
            '-m', 'rook.local_testing_proof',
            'owned-release-readiness',
            '--out', $ownedJson,
            '--rhino-exe', $RhinoExe,
            '--artifact-root', $artifactDir
        )
        if ($KeepRhinoOnFailure) {
            $args += '--keep-rhino-on-failure'
        }
        Invoke-ProofModuleGate -ArtifactDir $artifactDir -Gate 'owned_release_readiness' -FailureLabel 'owned_release_readiness_failed' -Arguments $args -OutPath $ownedJson

        Write-TopLevelManifest -ArtifactDir $artifactDir -Success $true -FailureLabel $null
        Write-Host 'release-readiness proven'
    } catch {
        $finalFailureLabel = [string](($_.Exception.Message -split ':', 2)[0])
        Write-TopLevelManifest -ArtifactDir $artifactDir -Success $false -FailureLabel $finalFailureLabel
        throw
    }
}

if (-not $ReleaseReadiness) {
    throw 'Specify -ReleaseReadiness. No default live action is provided.'
}

Invoke-ReleaseReadiness
