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

Test-ValidateLocalTestingStackScriptContract
Test-ProofModuleDoesNotInjectRepoSource

Write-Host 'Local testing stack guard tests passed.'
