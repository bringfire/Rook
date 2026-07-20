$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$StackScript = Join-Path $RepoRoot 'scripts\validate-local-testing-stack.ps1'
$ProofModule = Join-Path $RepoRoot 'mcp_server\src\rook\local_testing_proof.py'
$DeployGuards = Join-Path $RepoRoot 'scripts\tests\deploy-local-testing-guards.tests.ps1'
$ReleaseGuards = Join-Path $RepoRoot 'scripts\tests\release-installer-guards.tests.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-Contains {
    param([string]$Text, [string]$Expected, [string]$Message)
    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param([string]$Text, [string]$Unexpected, [string]$Message)
    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message $Message
}

function Import-StackFunctionsForBehaviorTest {
    $tokens = $null
    $parseErrors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile(
        $StackScript,
        [ref]$tokens,
        [ref]$parseErrors
    )
    Assert-True -Condition ($parseErrors.Count -eq 0) -Message 'Stack validator must parse before behavioral tests run.'

    $required = @(
        'New-GateEnvelope',
        'Save-GateEnvelope',
        'ConvertTo-CommandParts',
        'Invoke-ExternalChecked',
        'Invoke-GateCommand'
    )
    $definitions = @($ast.FindAll({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
        $required -contains $node.Name
    }, $true))
    Assert-True -Condition ($definitions.Count -eq $required.Count) -Message 'Could not load every required production stack-validator function.'
    return @($definitions | ForEach-Object { $_.Extent.Text })
}

foreach ($definition in (Import-StackFunctionsForBehaviorTest)) {
    Invoke-Expression $definition
}

$GateResults = New-Object System.Collections.Generic.List[object]

function Test-ValidateLocalTestingStackScriptContract {
    Assert-True -Condition (Test-Path $StackScript) -Message "Missing validate-local-testing-stack.ps1"
    $content = Get-Content -LiteralPath $StackScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$ReleaseReadiness' -Message 'Release-readiness mode must be explicit.'
    Assert-Contains -Text $content -Expected '[switch]$KeepRhinoOnFailure' -Message 'Diagnostic keep-open mode must be explicit.'
    Assert-Contains -Text $content -Expected "FailureLabel 'static_guard_failed'" -Message 'Static guard failures must have a stable label.'
    Assert-Contains -Text $content -Expected "FailureLabel 'release_non_interference_failed'" -Message 'Release non-interference failures must have a stable label.'
    Assert-Contains -Text $content -Expected "FailureLabel 'local_deploy_failed'" -Message 'Local deploy failures must have a stable label.'
    Assert-Contains -Text $content -Expected "FailureLabel 'installed_runtime_failed'" -Message 'Installed runtime failures must have a stable label.'
    Assert-Contains -Text $content -Expected 'Invoke-ExternalChecked' -Message 'Every external guard command must be checked independently.'
    Assert-Contains -Text $content -Expected 'ConvertTo-CommandParts' -Message 'Nested PowerShell command arrays must be normalized before invocation.'
    Assert-Contains -Text $content -Expected '$GateResults.ToArray()' -Message 'Top-level manifest must serialize concrete gate result entries.'
    Assert-Contains -Text $content -Expected 'Reset-InstalledChirpForReleaseReadiness' -Message 'Release-readiness must not reuse stale installed Chirp sidecars.'
    Assert-Contains -Text $content -Expected 'chirp_preflight' -Message 'Release-readiness must record Chirp preflight cleanup as a gate.'
    Assert-Contains -Text $content -Expected '@(''powershell'', ''-NoProfile'', ''-ExecutionPolicy'', ''Bypass'', ''-File'', $DeployGuards)' -Message 'Release-readiness must run deploy guards.'
    Assert-Contains -Text $content -Expected '@(''powershell'', ''-NoProfile'', ''-ExecutionPolicy'', ''Bypass'', ''-File'', $ReleaseGuards)' -Message 'Release-readiness must run release guards.'
    Assert-Contains -Text $content -Expected '@(''powershell'', ''-NoProfile'', ''-ExecutionPolicy'', ''Bypass'', ''-File'', $DeployScript)' -Message 'Release-readiness must perform a fresh local deploy.'
    Assert-Contains -Text $content -Expected 'rook.local_testing_proof' -Message 'Owned proof must run through installed rook module.'
    Assert-Contains -Text $content -Expected 'owned-release-readiness' -Message 'Owned proof must run the owned release-readiness subcommand.'
    Assert-Contains -Text $content -Expected 'Write-TopLevelManifest' -Message 'Release-readiness must always write a top-level manifest.'
    Assert-Contains -Text $content -Expected 'manifest.json' -Message 'Release-readiness must aggregate gate results into manifest.json.'
    Assert-Contains -Text $content -Expected '$VenvPython = Join-Path $RuntimeRoot ''venv\Scripts\python.exe''' -Message 'Installed AppData venv must be the Python authority.'
    Assert-Contains -Text $content -Expected 'artifacts\local-testing' -Message 'Release-readiness must write deterministic artifacts.'
    Assert-Contains -Text $content -Expected "Gate 'progressive_discovery'" -Message 'Release readiness must record the progressive gate.'
    Assert-Contains -Text $content -Expected "FailureLabel 'progressive_discovery_failed'" -Message 'Progressive failure label must be stable.'
    Assert-Contains -Text $content -Expected "'lm_surface_smoke.py'" -Message 'Release readiness must invoke the standalone smoke script.'
    Assert-Contains -Text $content -Expected "'progressive'" -Message 'Release readiness must select progressive mode.'
    Assert-Contains -Text $content -Expected "-ScopedEnvironment @{ PYTHONPATH = '' }" -Message 'The deployed gate must explicitly clear PYTHONPATH.'
    $owned = $content.IndexOf("Invoke-ProofModuleGate -ArtifactDir `$artifactDir -Gate 'owned_release_readiness'")
    $progressive = $content.IndexOf('Invoke-ProgressiveDiscoveryGate -ArtifactDir $artifactDir')
    $successManifest = $content.IndexOf('Write-TopLevelManifest -ArtifactDir $artifactDir -Success $true')
    Assert-True -Condition ($owned -ge 0 -and $owned -lt $progressive -and $progressive -lt $successManifest) -Message 'Progressive discovery must be the final release gate.'
}

function Test-ProofModuleDoesNotInjectRepoSource {
    Assert-True -Condition (Test-Path $ProofModule) -Message "Missing local_testing_proof.py"
    $content = Get-Content -LiteralPath $ProofModule -Raw

    Assert-NotContains -Text $content -Unexpected 'sys.path.insert' -Message 'Installed-runtime proof must not inject repo source.'
    Assert-NotContains -Text $content -Unexpected 'mcp_server/src' -Message 'Installed-runtime proof must not hard-code repo MCP source.'
    Assert-Contains -Text $content -Expected 'rook_import_leakage' -Message 'Installed-runtime proof must reject stale rook imports.'
    Assert-Contains -Text $content -Expected 'chirp_import_leakage' -Message 'Installed-runtime proof must reject stale chirp imports.'
    Assert-Contains -Text $content -Expected 'mcp_config_stale' -Message 'Installed-runtime proof must reject stale MCP configs.'
    Assert-Contains -Text $content -Expected 'verify_codex_mcp_config' -Message 'Installed-runtime proof must verify Codex TOML MCP config.'
    Assert-Contains -Text $content -Expected 'chat_manifest_stale' -Message 'Installed-runtime proof must reject stale chat manifests.'
    Assert-Contains -Text $content -Expected 'chirp_component_compile_error' -Message 'Live proof must reject Chirp compile errors.'
    Assert-Contains -Text $content -Expected 'component_guid' -Message 'Live proof must require Chirp component identity before checking gh_errors.'
    Assert-Contains -Text $content -Expected 'cleanup_failed' -Message 'Live proof must expose cleanup failures.'
    Assert-Contains -Text $content -Expected 'GateResult' -Message 'Proof module must emit machine-verifiable gate envelopes.'
}

function Test-ExternalRunnerCapturesNativeStderrAndRestoresProcessState {
    Assert-True -Condition ($PSVersionTable.PSEdition -eq 'Desktop' -and $PSVersionTable.PSVersion.Major -eq 5) -Message 'Behavioral external-runner coverage must execute under Windows PowerShell 5.1.'

    $artifactDir = Join-Path ([System.IO.Path]::GetTempPath()) ("rook-stack-runner-{0}" -f [guid]::NewGuid().ToString('N'))
    $scopeName = 'ROOK_STACK_RUNNER_BEHAVIOR_SCOPE'
    $initialScopeValue = [Environment]::GetEnvironmentVariable($scopeName, 'Process')
    $initialErrorActionPreference = $ErrorActionPreference
    $powershellExe = (Get-Command powershell.exe -ErrorAction Stop).Source
    New-Item -ItemType Directory -Path $artifactDir | Out-Null

    try {
        $ErrorActionPreference = 'Stop'
        [Environment]::SetEnvironmentVariable($scopeName, 'before-success', 'Process')
        $successScript = Join-Path $artifactDir 'native-stderr-success.ps1'
        @'
[Console]::Out.WriteLine("stdout-success:" + $env:ROOK_STACK_RUNNER_BEHAVIOR_SCOPE)
[Console]::Error.WriteLine("stderr-success")
exit 0
'@ | Set-Content -LiteralPath $successScript -Encoding UTF8
        Invoke-GateCommand `
            -Gate 'native_stderr_success' `
            -FailureLabel 'native_stderr_success_failed' `
            -ArtifactDir $artifactDir `
            -ScopedEnvironment @{ ROOK_STACK_RUNNER_BEHAVIOR_SCOPE = 'during-success' } `
            -Commands @(,@($powershellExe, '-NoProfile', '-File', $successScript))

        Assert-True -Condition ($ErrorActionPreference -eq 'Stop') -Message 'ErrorActionPreference must be restored after a successful native command.'
        Assert-True -Condition ([Environment]::GetEnvironmentVariable($scopeName, 'Process') -eq 'before-success') -Message 'Scoped environment must be restored after success.'
        $successEnvelope = Get-Content -LiteralPath (Join-Path $artifactDir 'native_stderr_success.json') -Raw | ConvertFrom-Json
        Assert-True -Condition ($successEnvelope.success -eq $true) -Message 'Exit 0 with native stderr must remain successful.'
        Assert-True -Condition ($successEnvelope.details.scoped_env.ROOK_STACK_RUNNER_BEHAVIOR_SCOPE -eq 'during-success') -Message 'Successful gate details must persist the scoped environment.'
        Assert-Contains -Text (Get-Content -LiteralPath $successEnvelope.stdout_path -Raw) -Expected 'stdout-success:during-success' -Message 'Successful native stdout must be persisted.'
        Assert-Contains -Text (Get-Content -LiteralPath $successEnvelope.stderr_path -Raw) -Expected 'stderr-success' -Message 'Successful native stderr must be persisted.'

        [Environment]::SetEnvironmentVariable($scopeName, $null, 'Process')
        $failureScript = Join-Path $artifactDir 'native-stderr-failure.ps1'
        @'
[Console]::Out.WriteLine("stdout-failure:" + $env:ROOK_STACK_RUNNER_BEHAVIOR_SCOPE)
[Console]::Error.WriteLine("stderr-failure")
exit 7
'@ | Set-Content -LiteralPath $failureScript -Encoding UTF8
        $failureMessage = $null
        try {
            Invoke-GateCommand `
                -Gate 'native_stderr_failure' `
                -FailureLabel 'native_stderr_failure_failed' `
                -ArtifactDir $artifactDir `
                -ScopedEnvironment @{ ROOK_STACK_RUNNER_BEHAVIOR_SCOPE = 'during-failure' } `
                -Commands @(,@($powershellExe, '-NoProfile', '-File', $failureScript))
        } catch {
            $failureMessage = $_.Exception.Message
        }

        Assert-Contains -Text $failureMessage -Expected 'native_stderr_failure_failed:' -Message 'Nonzero native exit must keep the stable gate failure label.'
        Assert-Contains -Text $failureMessage -Expected 'exited with code 7' -Message 'Nonzero native exit must report the captured exit code.'
        Assert-True -Condition ($ErrorActionPreference -eq 'Stop') -Message 'ErrorActionPreference must be restored after a failing native command.'
        Assert-True -Condition ($null -eq [Environment]::GetEnvironmentVariable($scopeName, 'Process')) -Message 'Scoped environment must be restored after failure.'
        $failureEnvelope = Get-Content -LiteralPath (Join-Path $artifactDir 'native_stderr_failure.json') -Raw | ConvertFrom-Json
        Assert-True -Condition ($failureEnvelope.success -eq $false) -Message 'Nonzero native exit must persist a failed gate envelope.'
        Assert-True -Condition ($failureEnvelope.failure_label -eq 'native_stderr_failure_failed') -Message 'Failed gate envelope must persist the stable failure label.'
        Assert-Contains -Text $failureEnvelope.details.error -Expected 'exited with code 7' -Message 'Failed gate details must persist the native exit code.'
        Assert-True -Condition ($failureEnvelope.details.scoped_env.ROOK_STACK_RUNNER_BEHAVIOR_SCOPE -eq 'during-failure') -Message 'Failed gate details must persist the scoped environment.'
        Assert-Contains -Text (Get-Content -LiteralPath $failureEnvelope.stdout_path -Raw) -Expected 'stdout-failure:during-failure' -Message 'Failing native stdout must be persisted.'
        Assert-Contains -Text (Get-Content -LiteralPath $failureEnvelope.stderr_path -Raw) -Expected 'stderr-failure' -Message 'Failing native stderr must be persisted.'
    } finally {
        $ErrorActionPreference = $initialErrorActionPreference
        [Environment]::SetEnvironmentVariable($scopeName, $initialScopeValue, 'Process')
        Remove-Item -LiteralPath $artifactDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Test-ValidateLocalTestingStackScriptContract
Test-ProofModuleDoesNotInjectRepoSource
Test-ExternalRunnerCapturesNativeStderrAndRestoresProcessState

Write-Host 'Local testing stack guard tests passed.'
