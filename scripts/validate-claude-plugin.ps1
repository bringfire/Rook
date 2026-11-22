<#
.SYNOPSIS
    Strict Claude plugin validation for the release pre-flight, with one named allowance.

.DESCRIPTION
    Runs `claude plugin validate --strict --json` on the repository root and fails on any
    error and on any warning except one: the validator's note that a CLAUDE.md at the plugin
    root is not loaded as plugin context.

    This repository's root CLAUDE.md is contributor guidance. The public promotion copies only
    the skill folders, the two manifests and LICENSE, so that file never ships and the warning
    does not describe the released plugin. Every other warning still fails, as --strict intends.
    A report this script cannot account for also fails.

    -ReportPath evaluates a saved JSON report instead of running the CLI. The tests use it.
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = '',
    [string]$ReportPath = ''
)

$ErrorActionPreference = 'Stop'
$AllowedWarningPrefix = 'CLAUDE.md at the plugin root is not loaded as project context.'

if ([string]::IsNullOrWhiteSpace($RepoRoot)) { $RepoRoot = Join-Path $PSScriptRoot '..' }
$RepoRoot = [IO.Path]::GetFullPath($RepoRoot).TrimEnd('\', '/')
$allowedFile = Join-Path $RepoRoot 'CLAUDE.md'

if ([string]::IsNullOrWhiteSpace($ReportPath)) {
    $raw = (& claude plugin validate --strict --json $RepoRoot 2>$null | Out-String)
    if ($LASTEXITCODE -notin @(0, 1)) { throw "claude plugin validate did not run (exit $LASTEXITCODE)." }
} else {
    $raw = Get-Content -LiteralPath $ReportPath -Raw
}
try { $report = $raw | ConvertFrom-Json } catch { throw 'claude plugin validate did not return a JSON report.' }

$failures = [Collections.Generic.List[string]]::new()
$accepted = 0
$sections = @()
if ($null -ne $report.manifest) { $sections += $report.manifest }
if ($null -ne $report.contents) { $sections += @($report.contents) }
foreach ($section in $sections) {
    foreach ($item in @($section.errors)) {
        if ($null -ne $item) { $failures.Add("error in $($section.file): $($item.message)") }
    }
    foreach ($item in @($section.warnings)) {
        if ($null -eq $item) { continue }
        $isAllowed = $item.path -ceq 'root' -and
            [string]$item.message -and ([string]$item.message).StartsWith($AllowedWarningPrefix, [StringComparison]::Ordinal) -and
            [string]$section.file -and [IO.Path]::GetFullPath([string]$section.file).Equals($allowedFile, [StringComparison]::OrdinalIgnoreCase)
        if ($isAllowed) { $accepted++ } else { $failures.Add("warning in $($section.file): $($item.message)") }
    }
}

if ($failures.Count -gt 0) {
    $failures | ForEach-Object { Write-Host $_ }
    Write-Host "Claude plugin validation failed: $($failures.Count) finding(s)."
    exit 1
}
if ($report.success -eq $true) {
    Write-Host 'Claude plugin validation passed.'
    exit 0
}
if ($accepted -gt 0) {
    Write-Host "Claude plugin validation passed with $accepted accepted warning(s): the root CLAUDE.md is contributor guidance and is not part of the released plugin."
    exit 0
}
Write-Host 'Claude plugin validation failed for a reason this script does not recognise. Run: claude plugin validate --strict .'
exit 1
