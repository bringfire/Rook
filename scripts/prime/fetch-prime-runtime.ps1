# fetch-prime-runtime.ps1
#
# Download, verify, and extract the pinned Prime ACP runtime that backs RookChat.
# The pin lives next to this script in rook-prime-runtime-source.json and is kept
# in sync with the commits pinned in mcp_server/src/rook/agent/chat/prime_runtime_artifact.py
# by mcp_server/tests/test_prime_runtime_source_pin.py.
#
# Result: <repo>\installer\runtime\prime\staging\<release_tag>\runtimes\<runtime_id>\
# which is the exact directory shape that scripts\deploy-local-testing.ps1
# (-PrimeRuntimePayload) and the release build (PrimeRuntimePayload) accept.
#
# Usage (from the repo root):
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\prime\fetch-prime-runtime.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\prime\fetch-prime-runtime.ps1 -Python .\mcp_server\.venv\Scripts\python.exe
#
# Nothing here selects a "latest" release or touches an installed Rook; it only
# stages a verified payload under installer\runtime (gitignored).

[CmdletBinding()]
param(
    [string]$StagingRoot = '',
    [string]$Python = '',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$PinPath = Join-Path $PSScriptRoot 'rook-prime-runtime-source.json'
$pin = Get-Content -LiteralPath $PinPath -Raw | ConvertFrom-Json

foreach ($field in 'release_tag', 'runtime_asset', 'runtime_asset_url', 'runtime_asset_bytes', 'runtime_asset_sha256', 'runtime_id') {
    if (-not $pin.PSObject.Properties[$field] -or [string]::IsNullOrWhiteSpace([string]$pin.$field)) {
        throw "Pin file is missing '$field': $PinPath"
    }
}
if ($pin.runtime_asset_sha256 -cnotmatch '^[A-F0-9]{64}$') { throw 'Pinned archive SHA-256 must be 64 uppercase hex characters.' }
if ($pin.runtime_id -cnotmatch '^[A-F0-9]{64}$') { throw 'Pinned runtime id must be 64 uppercase hex characters.' }

if ([string]::IsNullOrWhiteSpace($StagingRoot)) {
    $StagingRoot = Join-Path $RepoRoot 'installer\runtime\prime\staging'
}
$stage = Join-Path $StagingRoot $pin.release_tag
$inputs = Join-Path $stage 'inputs'
$runtimesRoot = Join-Path $stage 'runtimes'
$payload = Join-Path $runtimesRoot $pin.runtime_id
$archive = Join-Path $inputs $pin.runtime_asset
New-Item -ItemType Directory -Force -Path $inputs | Out-Null

function Test-ArchiveMatchesPin {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $false }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ne [int64]$pin.runtime_asset_bytes) { return $false }
    $hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    return $hash -ceq $pin.runtime_asset_sha256
}

if ($Force -or -not (Test-ArchiveMatchesPin -Path $archive)) {
    Write-Host "Downloading $($pin.runtime_asset_url)"
    $tmp = "$archive.partial"
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
    Invoke-WebRequest -Uri $pin.runtime_asset_url -OutFile $tmp -UseBasicParsing
    if (-not (Test-ArchiveMatchesPin -Path $tmp)) {
        Remove-Item -LiteralPath $tmp -Force
        throw "Downloaded archive does not match the pinned size/SHA-256 ($($pin.runtime_asset_sha256))."
    }
    Move-Item -LiteralPath $tmp -Destination $archive -Force
}
Write-Host "Archive verified: $archive"

if ($Force -and (Test-Path -LiteralPath $runtimesRoot)) {
    Remove-Item -LiteralPath $runtimesRoot -Recurse -Force
}

if (-not (Test-Path -LiteralPath (Join-Path $payload 'runtime-manifest.json') -PathType Leaf)) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [IO.Compression.ZipFile]::OpenRead($archive)
    try {
        $expectedPrefix = "runtimes/$($pin.runtime_id)/"
        foreach ($entry in $zip.Entries) {
            $name = $entry.FullName.Replace('\', '/')
            if ($name.StartsWith('/') -or ($name -split '/') -contains '..' -or -not $name.StartsWith($expectedPrefix)) {
                throw "Refusing archive entry outside runtimes/<runtime_id>/: $name"
            }
        }
        New-Item -ItemType Directory -Force -Path $runtimesRoot | Out-Null
        [IO.Compression.ZipFile]::ExtractToDirectory($archive, $stage)
    }
    finally {
        $zip.Dispose()
    }
}

$siblings = @(Get-ChildItem -LiteralPath $runtimesRoot -Directory | Where-Object { $_.Name -cmatch '^[A-F0-9]{64}$' })
if ($siblings.Count -ne 1 -or $siblings[0].Name -cne $pin.runtime_id) {
    throw "Expected exactly one runtime directory named $($pin.runtime_id) under $runtimesRoot."
}
$manifestHash = (Get-FileHash -LiteralPath (Join-Path $payload 'runtime-manifest.json') -Algorithm SHA256).Hash.ToUpperInvariant()
if ($manifestHash -cne $pin.runtime_id) {
    throw "runtime-manifest.json SHA-256 ($manifestHash) differs from the pinned runtime id."
}

if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw "Python with the rook package installed is required for manifest verification: $Python (see BUILDING.md, 'Setup MCP Server')."
}
& $Python -I -m rook.agent.chat.prime_runtime_artifact verify --runtime-root $payload --expected-runtime-id $pin.runtime_id
if ($LASTEXITCODE -ne 0) { throw 'Prime runtime manifest verification refused the extracted payload.' }

Write-Host ''
Write-Host "Prime runtime ready: $payload"
Write-Host 'Use it as -PrimeRuntimePayload for scripts\deploy-local-testing.ps1 or as PrimeRuntimePayload in the release build.'
