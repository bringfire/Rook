# Tests for scripts\validate-claude-plugin.ps1: strict validation with exactly one named allowance.
$ErrorActionPreference = 'Stop'
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Script = Join-Path $RepoRoot 'scripts\validate-claude-plugin.ps1'
$root = Join-Path ([IO.Path]::GetTempPath()) ('rook-plugin-validate-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
$failures = 0

function Invoke-Case([string]$Name, [int]$ExpectedExit, [hashtable]$Report) {
    $path = Join-Path $root ($Name + '.json')
    $Report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
    $output = (& powershell -NoProfile -ExecutionPolicy Bypass -File $Script -RepoRoot $root -ReportPath $path 2>&1 | Out-String)
    if ($LASTEXITCODE -ne $ExpectedExit) {
        Write-Host "FAIL $Name : expected exit $ExpectedExit, got $LASTEXITCODE. $output"
        $script:failures++
    } else { Write-Host "ok   $Name" }
}

$allowed = @{ path = 'root'; message = 'CLAUDE.md at the plugin root is not loaded as project context. To ship context with your plugin, use a skill.'; code = $null }
function New-Report([bool]$Success, [object[]]$ManifestWarnings, [object[]]$ManifestErrors, [object[]]$Contents) {
    @{ success = $Success; strict = $true
       manifest = @{ file = (Join-Path $root '.claude-plugin\marketplace.json'); type = 'marketplace'; errors = $ManifestErrors; warnings = $ManifestWarnings }
       contents = $Contents }
}

try {
    Invoke-Case 'clean-report-passes' 0 (New-Report $true @() @() @())
    Invoke-Case 'only-the-root-claude-md-warning-passes' 0 (New-Report $false @() @() @(
        @{ file = (Join-Path $root 'CLAUDE.md'); type = 'plugin'; errors = @(); warnings = @($allowed) }))
    Invoke-Case 'another-warning-fails' 1 (New-Report $false @(@{ path = 'plugins[0]'; message = 'Unrecognized field.'; code = $null }) @() @(
        @{ file = (Join-Path $root 'CLAUDE.md'); type = 'plugin'; errors = @(); warnings = @($allowed) }))
    Invoke-Case 'same-text-on-another-file-fails' 1 (New-Report $false @() @() @(
        @{ file = (Join-Path $root 'nested\CLAUDE.md'); type = 'plugin'; errors = @(); warnings = @($allowed) }))
    Invoke-Case 'an-error-fails' 1 (New-Report $false @() @(@{ path = 'name'; message = 'Required.'; code = $null }) @())
    Invoke-Case 'unexplained-failure-fails' 1 (New-Report $false @() @() @())
} finally {
    Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}

if ($failures) { Write-Host "validate-claude-plugin tests failed: $failures"; exit 1 }
Write-Host 'validate-claude-plugin tests passed.'
exit 0
