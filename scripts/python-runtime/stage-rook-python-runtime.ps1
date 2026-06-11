param(
    [string]$RepoRoot = '',
    [string]$RuntimeConfigPath = '',
    [string]$OutputRoot = '',
    [string]$DownloadRoot = ''
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "Python runtime staging failed: $Message"
}

function Resolve-FullPath {
    param([string]$Path)
    return [System.IO.Path]::GetFullPath($Path).TrimEnd('\')
}

if ([string]::IsNullOrWhiteSpace($RepoRoot)) {
    $RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
}
if ([string]::IsNullOrWhiteSpace($RuntimeConfigPath)) {
    $RuntimeConfigPath = Join-Path $RepoRoot 'installer\python-runtime\python-runtime.json'
}
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot 'installer\runtime\python'
}
if ([string]::IsNullOrWhiteSpace($DownloadRoot)) {
    $DownloadRoot = Join-Path $RepoRoot 'artifacts\python-runtime'
}

if (-not (Test-Path -LiteralPath $RuntimeConfigPath -PathType Leaf)) {
    Fail "runtime config missing: $RuntimeConfigPath"
}

$config = Get-Content -LiteralPath $RuntimeConfigPath -Raw | ConvertFrom-Json
if ($config.schema_version -ne 1) { Fail 'runtime config schema_version must be 1' }
if ($config.python_nuget_package -ne 'python') { Fail 'only the official python NuGet package is supported' }
if ($config.python_version -ne '3.11.9') { Fail 'python_version must be pinned to 3.11.9 for this release' }
if ($config.target_platform -ne 'win_amd64') { Fail 'target_platform must be win_amd64' }
if ($config.python_abi -ne 'cp311') { Fail 'python_abi must be cp311' }
if ($config.expected_executable -ne 'tools\python.exe') { Fail 'expected_executable must be tools\python.exe' }
if ($config.nupkg_sha256 -notmatch '^[A-F0-9]{64}$') { Fail 'nupkg_sha256 must be uppercase SHA256 hex' }

New-Item -ItemType Directory -Force -Path $DownloadRoot | Out-Null
New-Item -ItemType Directory -Force -Path $OutputRoot | Out-Null

$nupkgName = "$($config.python_nuget_package).$($config.python_version).nupkg"
$nupkgPath = Join-Path $DownloadRoot $nupkgName
$downloadUrl = "https://www.nuget.org/api/v2/package/$($config.python_nuget_package)/$($config.python_version)"

if (-not (Test-Path -LiteralPath $nupkgPath -PathType Leaf)) {
    Invoke-WebRequest -Uri $downloadUrl -OutFile $nupkgPath
}

$actualHash = (Get-FileHash -LiteralPath $nupkgPath -Algorithm SHA256).Hash.ToUpperInvariant()
if ($actualHash -ne $config.nupkg_sha256) {
    Fail "nupkg hash mismatch. Expected $($config.nupkg_sha256), actual $actualHash"
}

$extractArchivePath = Join-Path $DownloadRoot "$($config.python_nuget_package).$($config.python_version)-extract.zip"
Copy-Item -LiteralPath $nupkgPath -Destination $extractArchivePath -Force

$extractRoot = Join-Path $DownloadRoot "extract-$($config.python_version)"
if (Test-Path -LiteralPath $extractRoot) {
    Remove-Item -LiteralPath $extractRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $extractRoot | Out-Null
Expand-Archive -LiteralPath $extractArchivePath -DestinationPath $extractRoot -Force

$toolsRoot = Join-Path $extractRoot 'tools'
$pythonExe = Join-Path $toolsRoot 'python.exe'
if (-not (Test-Path -LiteralPath $pythonExe -PathType Leaf)) {
    Fail "NuGet tools\python.exe missing after extraction"
}

$stagedRoot = Join-Path $OutputRoot "cpython-$($config.python_version)"
if (Test-Path -LiteralPath $stagedRoot) {
    Remove-Item -LiteralPath $stagedRoot -Recurse -Force
}
Copy-Item -LiteralPath $toolsRoot -Destination $stagedRoot -Recurse

$stagedPython = Join-Path $stagedRoot 'python.exe'
$versionOutput = (& $stagedPython -V 2>&1) -join ''
if ($LASTEXITCODE -ne 0 -or $versionOutput -notmatch [regex]::Escape($config.python_version)) {
    Fail "staged python version check failed: $versionOutput"
}

$identityJson = (& $stagedPython -c "import json, sys; print(json.dumps({'executable': sys.executable, 'prefix': sys.prefix}))" 2>&1) -join ''
if ($LASTEXITCODE -ne 0) {
    Fail "staged python identity check failed: $identityJson"
}
$identity = $identityJson | ConvertFrom-Json
$actualExecutable = Resolve-FullPath -Path $identity.executable
$expectedExecutable = Resolve-FullPath -Path $stagedPython
if (-not $actualExecutable.Equals($expectedExecutable, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail "staged python sys.executable mismatch. Expected $expectedExecutable, actual $actualExecutable"
}

$actualPrefix = Resolve-FullPath -Path $identity.prefix
$expectedPrefix = Resolve-FullPath -Path $stagedRoot
if (-not $actualPrefix.Equals($expectedPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
    Fail "staged python sys.prefix mismatch. Expected $expectedPrefix, actual $actualPrefix"
}

$tempVenv = Join-Path $DownloadRoot 'venv-check'
if (Test-Path -LiteralPath $tempVenv) {
    Remove-Item -LiteralPath $tempVenv -Recurse -Force
}
& $stagedPython -m venv $tempVenv
if ($LASTEXITCODE -ne 0) { Fail 'python -m venv failed for staged runtime' }

$tempVenvPython = Join-Path $tempVenv 'Scripts\python.exe'
$pipOutput = (& $tempVenvPython -m pip --version 2>&1) -join ''
if ($LASTEXITCODE -ne 0 -or $pipOutput -notmatch 'pip') {
    Fail "temp venv pip check failed: $pipOutput"
}

Write-Host "Staged Python runtime: $stagedRoot"
