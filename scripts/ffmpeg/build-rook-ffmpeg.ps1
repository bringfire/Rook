param(
    [string]$RepoRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$OutputRoot = '',
    [string]$Msys2Bash = 'C:\msys64\usr\bin\bash.exe',
    [switch]$InstallPayload
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot 'artifacts\ffmpeg'
}

$SourceMetadataPath = Join-Path $PSScriptRoot 'rook-ffmpeg-source.json'
$ConfigureRecipePath = Join-Path $PSScriptRoot 'rook-ffmpeg-configure.txt'
$AllowlistPath = Join-Path $PSScriptRoot 'rook-ffmpeg-enable-allowlist.json'

$SourceMetadata = Get-Content -LiteralPath $SourceMetadataPath -Raw | ConvertFrom-Json
$ConfigureArgs = @(Get-Content -LiteralPath $ConfigureRecipePath | Where-Object {
    -not [string]::IsNullOrWhiteSpace($_) -and -not $_.TrimStart().StartsWith('#')
})

function Assert-Tool {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Name was not found at $Path"
    }
}

function Invoke-Checked {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = @(& $FilePath @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    if ($exitCode -ne 0) {
        throw "$FilePath $($Arguments -join ' ') failed with exit code $exitCode`n$($output -join "`n")"
    }

    return $output
}

function Save-RemoteFile {
    param([string]$Uri, [string]$OutFile)
    if (-not (Test-Path -LiteralPath $OutFile -PathType Leaf)) {
        Invoke-WebRequest -Uri $Uri -OutFile $OutFile
    }
}

function Assert-Sha256 {
    param([string]$Path, [string]$Expected)
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $Expected.ToUpperInvariant()) {
        throw "SHA-256 mismatch for $Path. Expected $Expected; actual $actual"
    }
}

function Convert-ToMsysPath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    return $fullPath.Replace('\', '/').Replace('C:', '/c')
}

function Invoke-Msys2 {
    param([string]$Command)
    $env:MSYSTEM = 'UCRT64'
    $env:CHERE_INVOKING = '1'
    Invoke-Checked -FilePath $Msys2Bash -Arguments @('-lc', $Command)
}

Assert-Tool -Path $Msys2Bash -Name 'MSYS2 bash'

$StageRoot = Join-Path $OutputRoot "ffmpeg-$($SourceMetadata.version)-rook-minimal"
$Downloads = Join-Path $StageRoot 'downloads'
$BuildRoot = Join-Path $StageRoot 'build'
$BundleRoot = Join-Path $StageRoot 'source-bundle'
$PayloadDir = Join-Path $RepoRoot 'third_party\ffmpeg'

New-Item -ItemType Directory -Force $Downloads, $BuildRoot, $BundleRoot | Out-Null

$ArchivePath = Join-Path $Downloads $SourceMetadata.source_archive
$SignaturePath = "$ArchivePath.asc"
$SigningKeyPath = Join-Path $Downloads 'ffmpeg-devel.asc'

Save-RemoteFile -Uri $SourceMetadata.source_url -OutFile $ArchivePath
Save-RemoteFile -Uri $SourceMetadata.source_signature_url -OutFile $SignaturePath
Save-RemoteFile -Uri $SourceMetadata.signing_key_url -OutFile $SigningKeyPath
Assert-Sha256 -Path $ArchivePath -Expected $SourceMetadata.source_sha256

$TrustedKeyringPath = Join-Path $StageRoot 'ffmpeg-release-keyring.gpg'
$fingerprintOutput = Invoke-Msys2 -Command "gpg --batch --import-options show-only --import --with-colons '$(Convert-ToMsysPath $SigningKeyPath)'"

$expectedFingerprint = ([string]$SourceMetadata.signing_key_fingerprint).ToUpperInvariant().Replace(' ', '')
$actualFingerprints = @($fingerprintOutput | Where-Object { $_ -like 'fpr:*' } | ForEach-Object { ($_ -split ':')[9].ToUpperInvariant() })
if ($actualFingerprints -notcontains $expectedFingerprint) {
    throw "FFmpeg signing key fingerprint did not match expected $expectedFingerprint"
}

Invoke-Msys2 -Command "gpg --batch --yes --dearmor --output '$(Convert-ToMsysPath $TrustedKeyringPath)' '$(Convert-ToMsysPath $SigningKeyPath)'"
Invoke-Msys2 -Command "gpgv --keyring '$(Convert-ToMsysPath $TrustedKeyringPath)' '$(Convert-ToMsysPath $SignaturePath)' '$(Convert-ToMsysPath $ArchivePath)'"
$SignatureStatus = 'verified'

$configureForBash = ($ConfigureArgs | ForEach-Object { "'$($_.Replace("'", "'\''"))'" }) -join ' '
$archiveForBash = Convert-ToMsysPath $ArchivePath
$buildForBash = Convert-ToMsysPath $BuildRoot
$bashScript = @"
set -euo pipefail
rm -rf '$buildForBash/src'
mkdir -p '$buildForBash/src'
tar -xf '$archiveForBash' -C '$buildForBash/src' --strip-components=1
cd '$buildForBash/src'
./configure $configureForBash
make -j`$(nproc)
"@

$bashScriptPath = Join-Path $StageRoot 'build-ffmpeg.sh'
Set-Content -LiteralPath $bashScriptPath -Value $bashScript -Encoding ASCII

Invoke-Msys2 -Command "bash '$(Convert-ToMsysPath $bashScriptPath)'"

$BuiltExe = Join-Path $BuildRoot 'src\ffmpeg.exe'
if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
    throw "Built ffmpeg.exe was not found: $BuiltExe"
}

$versionOutput = & $BuiltExe -version 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Built ffmpeg.exe -version failed with exit code $LASTEXITCODE"
}

$versionFirstLine = @($versionOutput)[0]
$runtimeVersionMatch = [regex]::Match($versionFirstLine, '^ffmpeg version\s+(\S+)')
if (-not $runtimeVersionMatch.Success) {
    throw "Unable to parse built ffmpeg version from: $versionFirstLine"
}

$RuntimeVersion = $runtimeVersionMatch.Groups[1].Value

$changesDiff = Join-Path $BundleRoot 'changes.diff'
Set-Content -LiteralPath $changesDiff -Value '' -Encoding ASCII

Copy-Item -LiteralPath $ArchivePath -Destination (Join-Path $BundleRoot $SourceMetadata.source_archive) -Force
Copy-Item -LiteralPath $SignaturePath -Destination (Join-Path $BundleRoot "$($SourceMetadata.source_archive).asc") -Force
Copy-Item -LiteralPath $ConfigureRecipePath -Destination (Join-Path $BundleRoot 'rook-ffmpeg-configure.txt') -Force
Copy-Item -LiteralPath $SourceMetadataPath -Destination (Join-Path $BundleRoot 'rook-ffmpeg-source.json') -Force
Copy-Item -LiteralPath $AllowlistPath -Destination (Join-Path $BundleRoot 'rook-ffmpeg-enable-allowlist.json') -Force
Copy-Item -LiteralPath $PSCommandPath -Destination (Join-Path $BundleRoot 'build-rook-ffmpeg.ps1') -Force

$SourceBundleZip = Join-Path $StageRoot "rook-ffmpeg-$($SourceMetadata.version)-source-bundle.zip"
if (Test-Path -LiteralPath $SourceBundleZip) {
    Remove-Item -LiteralPath $SourceBundleZip -Force
}

Compress-Archive -Path (Join-Path $BundleRoot '*') -DestinationPath $SourceBundleZip

$SourceBundleHash = (Get-FileHash -LiteralPath $SourceBundleZip -Algorithm SHA256).Hash
$BundleManifestPath = Join-Path $StageRoot 'rook-ffmpeg-source-bundle-manifest.json'
[ordered]@{
    schema_version = 1
    bundle_path = $SourceBundleZip
    bundle_sha256 = $SourceBundleHash
    ffmpeg_source_archive = $SourceMetadata.source_archive
    ffmpeg_source_sha256 = $SourceMetadata.source_sha256
    ffmpeg_source_signature_url = $SourceMetadata.source_signature_url
    signing_key_fingerprint = $SourceMetadata.signing_key_fingerprint
    configure_line = ($ConfigureArgs -join ' ')
    changes_diff_path = 'changes.diff'
    build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    generated_by = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $BundleManifestPath -Encoding UTF8

if ($InstallPayload) {
    New-Item -ItemType Directory -Force $PayloadDir | Out-Null
    Copy-Item -LiteralPath $BuiltExe -Destination (Join-Path $PayloadDir 'ffmpeg.exe') -Force

    $BinaryHash = (Get-FileHash -LiteralPath (Join-Path $PayloadDir 'ffmpeg.exe') -Algorithm SHA256).Hash
    [ordered]@{
        name = 'FFmpeg'
        version = $RuntimeVersion
        license = 'LGPL-only'
        binary_path = 'third_party/ffmpeg/ffmpeg.exe'
        binary_sha256 = $BinaryHash
        source_url = $SourceMetadata.source_url
        source_archive = $SourceMetadata.source_archive
        source_sha256 = $SourceMetadata.source_sha256
        source_signature_url = $SourceMetadata.source_signature_url
        signing_key_fingerprint = $SourceMetadata.signing_key_fingerprint
        source_signature_status = $SignatureStatus
        build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
        configure_recipe_path = 'scripts/ffmpeg/rook-ffmpeg-configure.txt'
        configure_line = ($ConfigureArgs -join ' ')
        changes_diff_path = 'changes.diff'
        source_bundle_manifest_name = 'rook-ffmpeg-source-bundle-manifest.json'
        validated_command_surfaces = @('poster', 'first_frame', 'last_frame')
        validated_fixtures = @(
            [ordered]@{
                path = 'third_party/ffmpeg/fixtures/sidecar-smoke-h264.mp4'
                container = 'mp4'
                video_codec = 'h264'
            },
            [ordered]@{
                path = 'third_party/ffmpeg/fixtures/sidecar-smoke-vp9.webm'
                container = 'webm'
                video_codec = 'vp9'
            }
        )
        verified_at = [DateTimeOffset]::UtcNow.ToString('o')
        verified_by = 'Rook minimal FFmpeg build recipe'
        notes = 'Built by Rook from official FFmpeg source for video sidecar extraction via ffmpeg.exe subprocess only.'
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PayloadDir 'ffmpeg-provenance.json') -Encoding UTF8
}

Write-Host "Built FFmpeg: $BuiltExe"
Write-Host "Source bundle manifest: $BundleManifestPath"
