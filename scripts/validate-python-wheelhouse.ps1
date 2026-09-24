<#
.SYNOPSIS
    Fail-closed release guard for Rook's bundled Python wheelhouse.

.DESCRIPTION
    The installer bundles a prebuilt, offline Python wheelhouse
    (installer\runtime\python-wheelhouse) plus its hash-pinned lockfiles and a
    provenance manifest (installer\runtime\python-runtime-manifest.json),
    produced by scripts\python-runtime\build-rook-python-wheelhouse.ps1.

    Unlike the FFmpeg bundle, the wheelhouse is a gitignored local build
    artifact, so nothing in version control proves it matches the release being
    built. Before this guard existed, ISCC would silently package whatever
    wheelhouse happened to be on disk -- including a stale one from a prior
    version. This script makes that impossible: it fails closed unless the
    staged wheelhouse is internally consistent with its manifest AND stamped
    with the exact release version being built (strict version-equality).

    Run from the build-release pipeline before compiling the installer.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Version,
    [string]$RepoRoot = '',
    [string]$WheelhouseDir = '',
    [string]$ManifestPath = '',
    [string]$InstallerScriptPath = ''
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Python wheelhouse validation failed: $Message"
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Require-NonEmptyField {
    param(
        [object]$Object,
        [string]$Field,
        [string]$Context
    )

    $property = $Object.PSObject.Properties[$Field]
    if ($null -eq $property -or $null -eq $property.Value) {
        Fail "$Context field '$Field' is missing"
    }
    if ($property.Value -is [string] -and [string]::IsNullOrWhiteSpace($property.Value)) {
        Fail "$Context field '$Field' is empty"
    }
}

function Get-NormalizedPackageName {
    param([string]$Name)
    return ($Name -replace '[-_.]+', '-').ToLowerInvariant()
}

# --- Resolve paths --------------------------------------------------------

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent $PSScriptRoot
}
$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)

if ([string]::IsNullOrWhiteSpace($WheelhouseDir)) {
    $WheelhouseDir = Join-Path $RepoRoot 'installer\runtime\python-wheelhouse'
}
if ([string]::IsNullOrWhiteSpace($ManifestPath)) {
    $ManifestPath = Join-Path $RepoRoot 'installer\runtime\python-runtime-manifest.json'
}
if ([string]::IsNullOrWhiteSpace($InstallerScriptPath)) {
    $InstallerScriptPath = Join-Path $RepoRoot 'installer\RookSetup.iss'
}

$WheelhouseDir = [System.IO.Path]::GetFullPath($WheelhouseDir)
$ManifestPath = [System.IO.Path]::GetFullPath($ManifestPath)
$InstallerScriptPath = [System.IO.Path]::GetFullPath($InstallerScriptPath)

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    Fail "release version must be X.Y.Z; actual value: $Version"
}

# --- Manifest -------------------------------------------------------------

if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
    Fail "python-runtime-manifest.json is missing: $ManifestPath"
}

try {
    $manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
} catch {
    Fail "python-runtime-manifest.json is malformed: $($_.Exception.Message)"
}

foreach ($field in @('schema_version', 'release_version', 'rook_git_sha', 'wheelhouse', 'lockfiles')) {
    Require-NonEmptyField -Object $manifest -Field $field -Context 'manifest'
}

# Strict version-equality: the staged wheelhouse must be built for THIS release.
if ([string]$manifest.release_version -ne $Version) {
    Fail "wheelhouse manifest release_version '$($manifest.release_version)' does not match release version '$Version' (rebuild the wheelhouse: scripts\python-runtime\build-rook-python-wheelhouse.ps1 -Version $Version)"
}

Require-NonEmptyField -Object $manifest.wheelhouse -Field 'wheels' -Context 'manifest wheelhouse'

# --- Wheelhouse directory + on-disk inventory -----------------------------

if (-not (Test-Path -LiteralPath $WheelhouseDir -PathType Container)) {
    Fail "wheelhouse directory is missing: $WheelhouseDir"
}

$diskWheels = @(Get-ChildItem -LiteralPath $WheelhouseDir -Filter '*.whl' -File)
if ($diskWheels.Count -eq 0) {
    Fail "wheelhouse directory contains no wheels: $WheelhouseDir"
}

$diskSdists = @(Get-ChildItem -LiteralPath $WheelhouseDir -File | Where-Object { $_.Name -match '\.(tar\.gz|zip)$' })
if ($diskSdists.Count -gt 0) {
    $diskSdists | ForEach-Object { Write-Host "Source distribution rejected: $($_.Name)" }
    Fail "source distributions are not allowed in the wheelhouse"
}

$diskWheelNames = New-Object System.Collections.Generic.HashSet[string]
foreach ($wheel in $diskWheels) {
    $null = $diskWheelNames.Add($wheel.Name)
}

# --- Manifest inventory <-> disk reconciliation ---------------------------

$manifestWheelNames = New-Object System.Collections.Generic.HashSet[string]
foreach ($record in @($manifest.wheelhouse.wheels)) {
    Require-NonEmptyField -Object $record -Field 'file' -Context 'manifest wheel record'
    Require-NonEmptyField -Object $record -Field 'sha256' -Context "manifest wheel record '$($record.file)'"

    $fileName = [string]$record.file
    $null = $manifestWheelNames.Add($fileName)

    $diskPath = Join-Path $WheelhouseDir $fileName
    if (-not (Test-Path -LiteralPath $diskPath -PathType Leaf)) {
        Fail "wheel listed in manifest is missing from the wheelhouse: $fileName"
    }

    $actual = Get-Sha256 -Path $diskPath
    $expected = ([string]$record.sha256).ToUpperInvariant()
    if ($actual -ne $expected) {
        Fail "wheel checksum mismatch for ${fileName}: expected $expected, actual $actual"
    }
}

# No extra wheels on disk beyond the manifest (catches contamination / leftovers).
foreach ($name in $diskWheelNames) {
    if (-not $manifestWheelNames.Contains($name)) {
        Fail "wheelhouse contains a wheel not recorded in the manifest: $name"
    }
}

# --- Release-coupled first-party wheels -----------------------------------

$rookMatch = @($manifest.wheelhouse.wheels | Where-Object {
    (Get-NormalizedPackageName ([string]$_.project)) -eq 'rook-mcp'
})
if ($rookMatch.Count -eq 0) {
    Fail "manifest wheel inventory does not contain the rook-mcp wheel"
}
foreach ($record in $rookMatch) {
    if ([string]$record.version -ne $Version) {
        Fail "rook-mcp wheel version '$($record.version)' does not match release version '$Version'"
    }
}

$rookWheelOnDisk = @(Get-ChildItem -LiteralPath $WheelhouseDir -Filter "rook_mcp-$Version-*.whl" -File)
if ($rookWheelOnDisk.Count -eq 0) {
    Fail "rook_mcp-$Version-*.whl is missing from the wheelhouse"
}

# --- Lockfiles ------------------------------------------------------------

foreach ($lockName in @('bootstrap', 'installer_tools', 'rook', 'chirp')) {
    Require-NonEmptyField -Object $manifest.lockfiles -Field $lockName -Context 'manifest lockfiles'
    $lock = $manifest.lockfiles.$lockName
    Require-NonEmptyField -Object $lock -Field 'path' -Context "manifest lockfile '$lockName'"
    Require-NonEmptyField -Object $lock -Field 'sha256' -Context "manifest lockfile '$lockName'"

    $lockPath = Join-Path $RepoRoot ([string]$lock.path)
    if (-not (Test-Path -LiteralPath $lockPath -PathType Leaf)) {
        Fail "lockfile '$lockName' is missing: $lockPath"
    }

    $actual = Get-Sha256 -Path $lockPath
    $expected = ([string]$lock.sha256).ToUpperInvariant()
    if ($actual -ne $expected) {
        Fail "lockfile '$lockName' checksum mismatch: expected $expected, actual $actual"
    }
}

# The rook lockfile must pin the release version of rook-mcp.
$rookLockPath = Join-Path $RepoRoot ([string]$manifest.lockfiles.rook.path)
$rookLockContent = Get-Content -LiteralPath $rookLockPath -Raw
if ($rookLockContent -notmatch "(?im)^\s*rook[-_]mcp==$([regex]::Escape($Version))\b") {
    Fail "rook lockfile does not pin rook-mcp==$Version"
}

# --- Installer packaging (fail closed) ------------------------------------

if (-not (Test-Path -LiteralPath $InstallerScriptPath -PathType Leaf)) {
    Fail "installer script is missing: $InstallerScriptPath"
}

$installerSourceLines = (Get-Content -LiteralPath $InstallerScriptPath -Raw) -split "`r?`n" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -match '(?i)^Source:\s*"' }

function Assert-InstallerSourceEntry {
    param(
        [string[]]$SourceLines,
        [string]$Needle,
        [string]$Label
    )

    $matches = @($SourceLines | Where-Object { $_ -match [regex]::Escape($Needle) })
    if ($matches.Count -eq 0) {
        Fail "installer script is missing a Source entry for $Label"
    }
    foreach ($match in $matches) {
        if ($match -match '(?i)\bskipifsourcedoesntexist\b') {
            Fail "installer Source entry for $Label must fail closed and must not use skipifsourcedoesntexist"
        }
    }
}

Assert-InstallerSourceEntry -SourceLines $installerSourceLines -Needle 'PythonWheelhouseDir' -Label 'the python wheelhouse'
Assert-InstallerSourceEntry -SourceLines $installerSourceLines -Needle 'PythonRuntimeManifest' -Label 'the python runtime manifest'
Assert-InstallerSourceEntry -SourceLines $installerSourceLines -Needle 'BootstrapLockfile' -Label 'the bootstrap lockfile'
Assert-InstallerSourceEntry -SourceLines $installerSourceLines -Needle 'InstallerToolsLockfile' -Label 'the installer tools lockfile'
Assert-InstallerSourceEntry -SourceLines $installerSourceLines -Needle 'RookLockfile' -Label 'the rook lockfile'
Assert-InstallerSourceEntry -SourceLines $installerSourceLines -Needle 'ChirpLockfile' -Label 'the chirp lockfile'

Write-Host "Python wheelhouse validation passed: $Version ($($diskWheels.Count) wheels)"
