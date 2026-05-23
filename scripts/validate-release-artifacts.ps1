param(
    [Parameter(Mandatory = $true)]
    [string]$Version,

    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$GitSha = '',
    [string]$InstallerPath = '',
    [string]$FfmpegSourceBundleManifestPath = '',
    [Parameter(Mandatory = $true)]
    [string]$SmokeManifestPath,
    [string]$OutputManifestPath = '',
    [long]$MinInstallerBytes = 5242880,
    [string]$BuildStartedAt = ''
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Release artifact validation failed: $Message"
}

function Require-File {
    param([string]$Path, [string]$Label)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "$Label is missing: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Require-Directory {
    param([string]$Path, [string]$Label)
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Container)) {
        Fail "$Label is missing: $Path"
    }
    return (Resolve-Path -LiteralPath $Path).Path
}

function Require-JsonField {
    param([object]$Json, [string]$Field, [string]$Label)
    $property = $Json.PSObject.Properties[$Field]
    if ($null -eq $property -or $null -eq $property.Value) {
        Fail "$Label field '$Field' is missing"
    }
    if ($property.Value -is [string] -and [string]::IsNullOrWhiteSpace($property.Value)) {
        Fail "$Label field '$Field' is empty"
    }
    return $property.Value
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Assert-FileNewerThanBuildStart {
    param([string]$Path, [Nullable[DateTimeOffset]]$StartedAt)
    if ($null -eq $StartedAt) {
        return
    }
    $item = Get-Item -LiteralPath $Path
    if ([DateTimeOffset]$item.LastWriteTime -lt $StartedAt) {
        Fail "$Path is older than the recorded build start time $($StartedAt.ToString('o'))"
    }
}

function Assert-ManagedAssemblyVersion {
    param([string]$Path, [string]$Expected)
    try {
        $assemblyName = [System.Reflection.AssemblyName]::GetAssemblyName($Path)
    } catch {
        Fail "managed assembly version could not be read from $Path`: $($_.Exception.Message)"
    }
    $actual = $assemblyName.Version.ToString()
    if ($actual -ne $Expected) {
        Fail "managed assembly version mismatch for $Path. Expected $Expected, actual $actual"
    }
}

function Assert-NativeFileVersion {
    param([string]$Path, [string]$Expected)
    $versionInfo = (Get-Item -LiteralPath $Path).VersionInfo
    if ($versionInfo.FileVersion -ne $Expected) {
        Fail "native FileVersion mismatch for $Path. Expected $Expected, actual $($versionInfo.FileVersion)"
    }
    if ($versionInfo.ProductVersion -ne $Expected) {
        Fail "native ProductVersion mismatch for $Path. Expected $Expected, actual $($versionInfo.ProductVersion)"
    }
}

function Assert-RuntimeConfigTfm {
    param([string]$Path, [string]$ExpectedTfm)
    $runtimeConfig = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    $actual = $runtimeConfig.runtimeOptions.tfm
    if ($actual -ne $ExpectedTfm) {
        Fail "$Path must declare runtimeOptions.tfm == $ExpectedTfm; actual value: $actual"
    }
}

if ($Version -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
    Fail "version must be X.Y.Z; actual value: $Version"
}

$RepoRoot = Require-Directory -Path $RepoRoot -Label 'RepoRoot'

if ([string]::IsNullOrWhiteSpace($GitSha)) {
    $GitSha = ((& git -C $RepoRoot rev-parse HEAD) -join '').Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($GitSha)) {
        Fail 'could not resolve git SHA'
    }
}

if ([string]::IsNullOrWhiteSpace($InstallerPath)) {
    $InstallerPath = Join-Path $RepoRoot "installer\output\Rook-Setup-$Version.exe"
}
if ([string]::IsNullOrWhiteSpace($FfmpegSourceBundleManifestPath)) {
    $FfmpegSourceBundleManifestPath = Join-Path $RepoRoot 'artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json'
}
if ([string]::IsNullOrWhiteSpace($OutputManifestPath)) {
    $OutputManifestPath = Join-Path $RepoRoot "installer\output\release-manifest-$Version.json"
}

$buildStartedAtValue = $null
if (-not [string]::IsNullOrWhiteSpace($BuildStartedAt)) {
    $parsedBuildStart = [DateTimeOffset]::MinValue
    if (-not [DateTimeOffset]::TryParse($BuildStartedAt, [ref]$parsedBuildStart)) {
        Fail "BuildStartedAt is not a valid timestamp: $BuildStartedAt"
    }
    $buildStartedAtValue = $parsedBuildStart
}

$expectedFileVersion = "$Version.0"
$installerPathResolved = Require-File -Path $InstallerPath -Label 'installer'
$installerItem = Get-Item -LiteralPath $installerPathResolved
if ($installerItem.Name -ne "Rook-Setup-$Version.exe") {
    Fail "installer filename must be Rook-Setup-$Version.exe; actual value: $($installerItem.Name)"
}
if ($installerItem.Length -lt $MinInstallerBytes) {
    Fail "installer is smaller than expected: $($installerItem.Length) bytes"
}
Assert-FileNewerThanBuildStart -Path $installerPathResolved -StartedAt $buildStartedAtValue
$installerSha256 = Get-Sha256 -Path $installerPathResolved

$nativePath = Require-File -Path (Join-Path $RepoRoot 'src\RookNative\bin\Release\x64\RookNative.rhp') -Label 'native RHP'
Assert-NativeFileVersion -Path $nativePath -Expected $expectedFileVersion
Assert-FileNewerThanBuildStart -Path $nativePath -StartedAt $buildStartedAtValue

$managedArtifacts = @(
    @{ Runtime = 'net8.0'; Path = Join-Path $RepoRoot 'src\Rook\bin\Release\net8.0\Rook.rhp'; RuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json' },
    @{ Runtime = 'net7.0'; Path = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.rhp'; RuntimeConfig = Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json' },
    @{ Runtime = 'net48'; Path = Join-Path $RepoRoot 'src\Rook\bin\Release\net48\Rook.rhp'; RuntimeConfig = $null }
)

foreach ($artifact in $managedArtifacts) {
    $managedPath = Require-File -Path $artifact.Path -Label "$($artifact.Runtime) managed RHP"
    Assert-ManagedAssemblyVersion -Path $managedPath -Expected $expectedFileVersion
    Assert-FileNewerThanBuildStart -Path $managedPath -StartedAt $buildStartedAtValue
    if ($artifact.RuntimeConfig) {
        $runtimeConfigPath = Require-File -Path $artifact.RuntimeConfig -Label "$($artifact.Runtime) runtimeconfig"
        Assert-RuntimeConfigTfm -Path $runtimeConfigPath -ExpectedTfm $artifact.Runtime
    }
}

$sourceBundleManifestPathResolved = Require-File -Path $FfmpegSourceBundleManifestPath -Label 'FFmpeg source-bundle manifest'
$sourceBundleManifest = Get-Content -LiteralPath $sourceBundleManifestPathResolved -Raw | ConvertFrom-Json
$sourceBundlePath = Require-File -Path (Require-JsonField -Json $sourceBundleManifest -Field 'bundle_path' -Label 'FFmpeg source-bundle manifest') -Label 'FFmpeg source bundle'
$sourceBundleSha256 = Get-Sha256 -Path $sourceBundlePath
$manifestSourceBundleSha = ([string](Require-JsonField -Json $sourceBundleManifest -Field 'bundle_sha256' -Label 'FFmpeg source-bundle manifest')).ToUpperInvariant()
if ($sourceBundleSha256 -ne $manifestSourceBundleSha) {
    Fail "FFmpeg source bundle checksum mismatch. Expected $manifestSourceBundleSha, actual $sourceBundleSha256"
}

$smokeManifestPathResolved = Require-File -Path $SmokeManifestPath -Label 'release smoke manifest'
$smokeManifest = Get-Content -LiteralPath $smokeManifestPathResolved -Raw | ConvertFrom-Json
foreach ($field in @(
    'git_sha',
    'installer_sha256',
    'rhino_version',
    'revit_version',
    'rhino_inside_version',
    'rook_version',
    'native_port',
    'ping_result',
    'loaded_native_path',
    'loaded_companion_path'
)) {
    $null = Require-JsonField -Json $smokeManifest -Field $field -Label 'release smoke manifest'
}

if ([string]$smokeManifest.git_sha -ne $GitSha) {
    Fail "smoke manifest git_sha does not match release git SHA. Expected $GitSha, actual $($smokeManifest.git_sha)"
}
if (([string]$smokeManifest.installer_sha256).ToUpperInvariant() -ne $installerSha256) {
    Fail "smoke manifest installer_sha256 does not match installer hash"
}
if ([string]$smokeManifest.rook_version -ne $Version) {
    Fail "smoke manifest rook_version does not match release version. Expected $Version, actual $($smokeManifest.rook_version)"
}

$outputManifestParent = Split-Path -Parent $OutputManifestPath
if ($outputManifestParent) {
    New-Item -ItemType Directory -Path $outputManifestParent -Force | Out-Null
}

$releaseManifest = [ordered]@{
    schema_version = 1
    version = $Version
    git_sha = $GitSha
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    installer_path = $installerPathResolved
    installer_sha256 = $installerSha256
    ffmpeg_source_bundle_path = $sourceBundlePath
    ffmpeg_source_bundle_sha256 = $sourceBundleSha256
    ffmpeg_source_bundle_manifest_path = $sourceBundleManifestPathResolved
    smoke_manifest_path = $smokeManifestPathResolved
    smoke = $smokeManifest
    native = [ordered]@{
        path = $nativePath
        file_version = $expectedFileVersion
        sha256 = Get-Sha256 -Path $nativePath
    }
    managed = @($managedArtifacts | ForEach-Object {
        $path = (Resolve-Path -LiteralPath $_.Path).Path
        [ordered]@{
            runtime = $_.Runtime
            path = $path
            assembly_version = $expectedFileVersion
            sha256 = Get-Sha256 -Path $path
        }
    })
}

$releaseManifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $OutputManifestPath -Encoding UTF8

Write-Host "Release artifact validation passed: $Version $GitSha"
Write-Host "Release manifest: $OutputManifestPath"
