$ErrorActionPreference = 'Stop'

if ($PSVersionTable.PSEdition -eq 'Core') {
    $windowsPowerShell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
    if (-not (Test-Path -LiteralPath $windowsPowerShell -PathType Leaf)) {
        throw "Windows PowerShell is required to run this test script, but was not found at: $windowsPowerShell"
    }

    & $windowsPowerShell -NoProfile -ExecutionPolicy Bypass -File $PSCommandPath @args
    exit $LASTEXITCODE
}

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$ValidatorScript = Join-Path $RepoRoot 'scripts\validate-ffmpeg-bundle.ps1'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Message
    )

    $normalizedText = (($Text -replace '\s+', ' ').Trim())
    $normalizedExpected = (($Expected -replace '\s+', ' ').Trim())
    Assert-True -Condition $normalizedText.Contains($normalizedExpected) -Message "$Message`nExpected to find: $Expected`nActual output:`n$Text"
}

function New-FakeFFmpeg {
    param([string]$OutputPath)

    $source = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;

public static class Program
{
    public static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "-version")
        {
            Console.WriteLine("ffmpeg version n8.1.1-rook-minimal");
            Console.WriteLine("configuration: --disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug --disable-programs --enable-ffmpeg --enable-protocol=file --enable-demuxer=mov --enable-demuxer=matroska --enable-muxer=image2 --enable-decoder=h264 --enable-parser=h264 --enable-filter=select --enable-filter=reverse --enable-encoder=mjpeg");
            return 0;
        }

        if (Environment.GetEnvironmentVariable("ROOK_FAKE_FFMPEG_FAIL") == "1")
        {
            return 42;
        }

        string outputPath = args.Length == 0 ? "output.jpg" : args[args.Length - 1];
        using (Bitmap bitmap = new Bitmap(2, 2))
        {
            bitmap.SetPixel(0, 0, Color.Red);
            bitmap.SetPixel(1, 0, Color.Green);
            bitmap.SetPixel(0, 1, Color.Blue);
            bitmap.SetPixel(1, 1, Color.White);
            bitmap.Save(outputPath, ImageFormat.Jpeg);
        }

        return 0;
    }
}
'@

    Add-Type `
        -TypeDefinition $source `
        -OutputAssembly $OutputPath `
        -OutputType ConsoleApplication `
        -ReferencedAssemblies @('System.Drawing.dll')
}

function Get-TestInstallerContent {
    return @'
Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\ffmpeg-provenance.json"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\LICENSE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\NOTICE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\SOURCE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\README.md"; DestDir: "{app}\third_party\ffmpeg"
'@
}

function Compress-TestSourceBundle {
    param(
        [object]$Payload,
        [bool]$UpdateManifestHash = $true
    )

    if (Test-Path -LiteralPath $Payload.SourceBundleZip) {
        Remove-Item -LiteralPath $Payload.SourceBundleZip -Force
    }

    Compress-Archive -Path (Join-Path $Payload.SourceBundleDir '*') -DestinationPath $Payload.SourceBundleZip

    if ($UpdateManifestHash) {
        $manifest = Get-Content -LiteralPath $Payload.SourceBundleManifestPath -Raw | ConvertFrom-Json
        $manifest.bundle_sha256 = (Get-FileHash -LiteralPath $Payload.SourceBundleZip -Algorithm SHA256).Hash
        $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Payload.SourceBundleManifestPath -Encoding UTF8
    }
}

function New-TestPayload {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) "rook-ffmpeg-policy-$([System.Guid]::NewGuid().ToString('N'))"
    $payload = Join-Path $root 'third_party\ffmpeg'
    $fixtures = Join-Path $payload 'fixtures'
    $installerDir = Join-Path $root 'installer'
    $installer = Join-Path $installerDir 'RookSetup.iss'
    $ffmpeg = Join-Path $payload 'ffmpeg.exe'
    $scriptMetadataDir = Join-Path $root 'scripts\ffmpeg'
    $releaseDir = Join-Path $root 'release'
    $sourceBundleDir = Join-Path $releaseDir 'source-bundle'
    $sourceBundleZip = Join-Path $releaseDir 'rook-ffmpeg-source-bundle.zip'
    $sourceBundleManifest = Join-Path $releaseDir 'rook-ffmpeg-source-bundle-manifest.json'

    New-Item -ItemType Directory -Path $fixtures | Out-Null
    New-Item -ItemType Directory -Path $installerDir | Out-Null
    New-Item -ItemType Directory -Path $scriptMetadataDir | Out-Null
    New-Item -ItemType Directory -Path $sourceBundleDir | Out-Null

    New-FakeFFmpeg -OutputPath $ffmpeg
    Set-Content -Path (Join-Path $fixtures 'sidecar-smoke-h264.mp4') -Value 'fake h264 fixture' -Encoding ASCII
    Set-Content -Path (Join-Path $fixtures 'sidecar-smoke-vp9.webm') -Value 'fake vp9 fixture' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'LICENSE.FFmpeg.txt') -Value 'LGPL license text for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'NOTICE.FFmpeg.txt') -Value 'FFmpeg attribution notice for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'SOURCE.FFmpeg.txt') -Value 'Corresponding source URL and checksum for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'README.md') -Value 'Bundled FFmpeg test payload summary.' -Encoding ASCII
    Set-Content -Path $installer -Value (Get-TestInstallerContent) -Encoding ASCII

    $configureLine = '--disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug --disable-programs --enable-ffmpeg --enable-protocol=file --enable-demuxer=mov --enable-demuxer=matroska --enable-muxer=image2 --enable-decoder=h264 --enable-parser=h264 --enable-filter=select --enable-filter=reverse --enable-encoder=mjpeg'
    $configureRecipePath = Join-Path $scriptMetadataDir 'rook-ffmpeg-configure.txt'
    ($configureLine -split ' ') | Set-Content -Path $configureRecipePath -Encoding ASCII

    $buildScriptPath = Join-Path $scriptMetadataDir 'build-rook-ffmpeg.ps1'
    Set-Content -Path $buildScriptPath -Value 'fake build script' -Encoding ASCII

    Set-Content -Path (Join-Path $sourceBundleDir 'ffmpeg-8.1.1.tar.xz') -Value 'fake source archive' -Encoding ASCII
    Set-Content -Path (Join-Path $sourceBundleDir 'ffmpeg-8.1.1.tar.xz.asc') -Value 'fake source signature' -Encoding ASCII
    $sourceArchiveHash = (Get-FileHash -LiteralPath (Join-Path $sourceBundleDir 'ffmpeg-8.1.1.tar.xz') -Algorithm SHA256).Hash
    $sourceSignatureHash = (Get-FileHash -LiteralPath (Join-Path $sourceBundleDir 'ffmpeg-8.1.1.tar.xz.asc') -Algorithm SHA256).Hash

    $allowlistPath = Join-Path $scriptMetadataDir 'rook-ffmpeg-enable-allowlist.json'
    [ordered]@{
        schema_version = 1
        allowed_enable_flags = @(
            '--enable-ffmpeg',
            '--enable-protocol=file',
            '--enable-demuxer=mov',
            '--enable-demuxer=matroska',
            '--enable-muxer=image2',
            '--enable-decoder=h264',
            '--enable-parser=h264',
            '--enable-filter=select',
            '--enable-filter=reverse',
            '--enable-encoder=mjpeg'
        )
        external_provenance_overrides = @()
    } | ConvertTo-Json -Depth 5 | Set-Content -Path $allowlistPath -Encoding UTF8

    $sourceMetadataPath = Join-Path $scriptMetadataDir 'rook-ffmpeg-source.json'
    [ordered]@{
        schema_version = 1
        name = 'FFmpeg'
        version = '8.1.1'
        source_url = 'https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz'
        source_archive = 'ffmpeg-8.1.1.tar.xz'
        source_sha256 = $sourceArchiveHash
        source_signature_url = 'https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz.asc'
        signing_key_url = 'https://ffmpeg.org/ffmpeg-devel.asc'
        signing_key_fingerprint = 'FCF986EA15E6E293A5644F10B4322F04D67658D8'
        source_signature_status_required = 'verified'
    } | ConvertTo-Json -Depth 5 | Set-Content -Path $sourceMetadataPath -Encoding UTF8

    Set-Content -Path (Join-Path $sourceBundleDir 'changes.diff') -Value '' -Encoding ASCII
    Copy-Item -LiteralPath $configureRecipePath -Destination (Join-Path $sourceBundleDir 'rook-ffmpeg-configure.txt') -Force
    Copy-Item -LiteralPath $sourceMetadataPath -Destination (Join-Path $sourceBundleDir 'rook-ffmpeg-source.json') -Force
    Copy-Item -LiteralPath $allowlistPath -Destination (Join-Path $sourceBundleDir 'rook-ffmpeg-enable-allowlist.json') -Force
    Copy-Item -LiteralPath $buildScriptPath -Destination (Join-Path $sourceBundleDir 'build-rook-ffmpeg.ps1') -Force
    Compress-Archive -Path (Join-Path $sourceBundleDir '*') -DestinationPath $sourceBundleZip
    $sourceBundleHash = (Get-FileHash -LiteralPath $sourceBundleZip -Algorithm SHA256).Hash

    [ordered]@{
        schema_version = 1
        bundle_path = $sourceBundleZip
        bundle_sha256 = $sourceBundleHash
        ffmpeg_source_archive = 'ffmpeg-8.1.1.tar.xz'
        ffmpeg_source_sha256 = $sourceArchiveHash
        ffmpeg_source_signature_url = 'https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz.asc'
        ffmpeg_source_signature_sha256 = $sourceSignatureHash
        signing_key_fingerprint = 'FCF986EA15E6E293A5644F10B4322F04D67658D8'
        configure_line = $configureLine
        changes_diff_path = 'changes.diff'
        build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
        generated_at = '2026-05-12T00:00:00Z'
        generated_by = 'test'
    } | ConvertTo-Json -Depth 5 | Set-Content -Path $sourceBundleManifest -Encoding UTF8

    $hash = (Get-FileHash -LiteralPath $ffmpeg -Algorithm SHA256).Hash
    $provenance = [ordered]@{
        name = 'FFmpeg'
        version = 'n8.1.1-rook-minimal'
        license = 'LGPL-only'
        binary_path = 'third_party/ffmpeg/ffmpeg.exe'
        binary_sha256 = $hash
        source_url = 'https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz'
        source_archive = 'ffmpeg-8.1.1.tar.xz'
        source_sha256 = $sourceArchiveHash
        source_signature_url = 'https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz.asc'
        signing_key_fingerprint = 'FCF986EA15E6E293A5644F10B4322F04D67658D8'
        source_signature_status = 'verified'
        build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
        configure_recipe_path = 'scripts/ffmpeg/rook-ffmpeg-configure.txt'
        configure_line = $configureLine
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
        verified_at = '2026-05-12T00:00:00Z'
        verified_by = 'policy-test'
    }

    $provenance | ConvertTo-Json -Depth 8 | Set-Content -Path (Join-Path $payload 'ffmpeg-provenance.json') -Encoding UTF8

    return [pscustomobject]@{
        Root = $root
        Payload = $payload
        Installer = $installer
        Provenance = Join-Path $payload 'ffmpeg-provenance.json'
        Ffmpeg = $ffmpeg
        AllowlistPath = $allowlistPath
        SourceMetadataPath = $sourceMetadataPath
        SourceBundleDir = $sourceBundleDir
        SourceBundleZip = $sourceBundleZip
        SourceBundleManifestPath = $sourceBundleManifest
    }
}

function Read-Provenance {
    param([object]$Payload)
    return Get-Content -LiteralPath $Payload.Provenance -Raw | ConvertFrom-Json
}

function Write-Provenance {
    param(
        [object]$Payload,
        [object]$Provenance
    )

    $Provenance | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $Payload.Provenance -Encoding UTF8
}

function Read-SourceMetadata {
    param([object]$Payload)
    return Get-Content -LiteralPath $Payload.SourceMetadataPath -Raw | ConvertFrom-Json
}

function Write-SourceMetadata {
    param(
        [object]$Payload,
        [object]$SourceMetadata
    )

    $SourceMetadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Payload.SourceMetadataPath -Encoding UTF8
}

function Read-SourceBundleManifest {
    param([object]$Payload)
    return Get-Content -LiteralPath $Payload.SourceBundleManifestPath -Raw | ConvertFrom-Json
}

function Write-SourceBundleManifest {
    param(
        [object]$Payload,
        [object]$Manifest
    )

    $Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Payload.SourceBundleManifestPath -Encoding UTF8
}

function Invoke-Validation {
    param([object]$Payload)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & powershell `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File $ValidatorScript `
            -RepoRoot $Payload.Root `
            -PayloadDir $Payload.Payload `
            -InstallerScriptPath $Payload.Installer `
            -AllowlistPath $Payload.AllowlistPath `
            -SourceMetadataPath $Payload.SourceMetadataPath `
            -SourceBundleManifestPath $Payload.SourceBundleManifestPath 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $text = $output -join "`n"
    if ($exitCode -ne 0) {
        throw $text
    }

    return $text
}

function Invoke-ValidationExpectFailure {
    param([object]$Payload)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & powershell `
            -NoProfile `
            -ExecutionPolicy Bypass `
            -File $ValidatorScript `
            -RepoRoot $Payload.Root `
            -PayloadDir $Payload.Payload `
            -InstallerScriptPath $Payload.Installer `
            -AllowlistPath $Payload.AllowlistPath `
            -SourceMetadataPath $Payload.SourceMetadataPath `
            -SourceBundleManifestPath $Payload.SourceBundleManifestPath 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    $text = $output -join "`n"
    if ($exitCode -eq 0) {
        throw "Expected validation to fail, but it passed:`n$text"
    }

    return $text
}

function Invoke-PayloadTest {
    param(
        [scriptblock]$Body
    )

    $payload = New-TestPayload
    try {
        & $Body $payload
    } finally {
        if (Test-Path -LiteralPath $payload.Root) {
            Remove-Item -LiteralPath $payload.Root -Recurse -Force
        }
    }
}

function Test-ValidPayloadPasses {
    Invoke-PayloadTest {
        param($payload)
        $output = Invoke-Validation -Payload $payload
        Assert-Contains -Text $output -Expected 'FFmpeg bundle validation passed: n8.1.1-rook-minimal' -Message 'Valid payload should pass.'
    }
}

function Test-ProvenanceEnableGplFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = "$($provenance.configure_line) --enable-gpl"
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected '--enable-gpl' -Message 'Forbidden GPL configure flag should be reported.'
    }
}

function Test-ProvenanceEnableNonfreeFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = "$($provenance.configure_line) --enable-nonfree"
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected '--enable-nonfree' -Message 'Forbidden nonfree configure flag should be reported.'
    }
}

function Test-MissingConfigureLineFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.PSObject.Properties.Remove('configure_line')
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'configure_line' -Message 'Missing configure_line should be reported.'
    }
}

function Test-BinarySha256MismatchFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.binary_sha256 = '0' * 64
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'checksum mismatch' -Message 'Checksum mismatch should be reported.'
    }
}

function Test-StaleConfigureLineFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = "$($provenance.configure_line) --enable-ffmpeg"
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'configure_line does not match' -Message 'Stale configure_line should be reported.'
    }
}

function Test-StaleVersionFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.version = 'stale-version'
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'provenance version does not match runtime ffmpeg version' -Message 'Stale provenance version should be reported.'
    }
}

function Test-MissingNoticeFails {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath (Join-Path $payload.Payload 'NOTICE.FFmpeg.txt') -Force

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'NOTICE.FFmpeg.txt is missing' -Message 'Missing notice file should be reported.'
    }
}

function Test-RejectsUnexpectedEnableZlib {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = "$($provenance.configure_line) --enable-zlib"
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'unexpected FFmpeg configure enable flag --enable-zlib' -Message 'Validator must reject broad non-allowlisted enable flags.'
    }
}

function Test-RejectsMissingSourceSignatureVerification {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.source_signature_status = 'not-checked'
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source_signature_status must be verified' -Message 'Validator must require verified official FFmpeg source signatures.'
    }
}

function Test-RejectsMissingSourceBundleManifest {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath $payload.SourceBundleManifestPath -Force

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle manifest is missing' -Message 'Validator must require release source-bundle staging.'
    }
}

function Test-RejectsSourceBundleHashMismatch {
    Invoke-PayloadTest {
        param($payload)
        Add-Content -LiteralPath $payload.SourceBundleZip -Value 'tamper'

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle checksum mismatch' -Message 'Validator must verify the staged source bundle hash.'
    }
}

function Test-RejectsMissingRequiredH264FixtureMetadata {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.validated_fixtures = @($provenance.validated_fixtures | Where-Object { $_.video_codec -ne 'h264' })
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'validated_fixtures must include h264 mp4 coverage' -Message 'Validator must require H.264 MP4 fixture metadata.'
    }
}

function Test-RejectsMissingRequiredVp9OrAv1FixtureMetadata {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.validated_fixtures = @($provenance.validated_fixtures | Where-Object { $_.video_codec -ne 'vp9' -and $_.video_codec -ne 'av1' })
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'validated_fixtures must include vp9 webm or av1 coverage' -Message 'Validator must require WebM/VP9 or AV1 fixture metadata.'
    }
}

function Test-RejectsMissingChangesDiffInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath (Join-Path $payload.SourceBundleDir 'changes.diff') -Force
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle is missing required entry changes.diff' -Message 'Validator must inspect source bundle contents.'
    }
}

function Test-RejectsMissingSourceArchiveInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath (Join-Path $payload.SourceBundleDir 'ffmpeg-8.1.1.tar.xz') -Force
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle is missing required entry ffmpeg-8.1.1.tar.xz' -Message 'Validator must include the FFmpeg source archive in the bundle.'
    }
}

function Test-RejectsMissingSourceSignatureInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath (Join-Path $payload.SourceBundleDir 'ffmpeg-8.1.1.tar.xz.asc') -Force
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle is missing required entry ffmpeg-8.1.1.tar.xz.asc' -Message 'Validator must include the FFmpeg source signature in the bundle.'
    }
}

function Test-RejectsTamperedSourceArchiveInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Set-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'ffmpeg-8.1.1.tar.xz') -Value 'tampered source archive' -Encoding ASCII
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle source archive checksum mismatch' -Message 'Validator must hash the source archive inside the staged source bundle.'
    }
}

function Test-RejectsTamperedSourceSignatureInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Set-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'ffmpeg-8.1.1.tar.xz.asc') -Value 'tampered source signature' -Encoding ASCII
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle source signature checksum mismatch' -Message 'Validator must hash the source signature inside the staged source bundle.'
    }
}

function Test-RejectsMismatchedConfigureRecipeInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Set-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'rook-ffmpeg-configure.txt') -Value '--disable-everything --enable-ffmpeg' -Encoding ASCII
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle configure recipe does not match committed FFmpeg configure recipe' -Message 'Validator must compare the embedded configure recipe to the committed recipe.'
    }
}

function Test-RejectsMismatchedSourceMetadataInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        $metadata = Get-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'rook-ffmpeg-source.json') -Raw | ConvertFrom-Json
        $metadata.source_url = 'https://example.test/tampered-source.tar.xz'
        $metadata | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'rook-ffmpeg-source.json') -Encoding UTF8
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle source metadata does not match committed FFmpeg source metadata' -Message 'Validator must compare the embedded source metadata to the committed metadata.'
    }
}

function Test-RejectsMismatchedAllowlistInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Add-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'rook-ffmpeg-enable-allowlist.json') -Value ' '
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle enable allowlist does not match committed FFmpeg allowlist' -Message 'Validator must compare the embedded allowlist to the committed allowlist.'
    }
}

function Test-RejectsMismatchedBuildScriptInsideSourceBundle {
    Invoke-PayloadTest {
        param($payload)
        Add-Content -LiteralPath (Join-Path $payload.SourceBundleDir 'build-rook-ffmpeg.ps1') -Value 'tampered build script'
        Compress-TestSourceBundle -Payload $payload

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle build script does not match committed FFmpeg build recipe' -Message 'Validator must compare the embedded build script to the committed build recipe.'
    }
}

function Test-RejectsProvenanceSourceUrlMismatch {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.source_url = 'https://example.test/stale-source.tar.xz'
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'provenance source_url does not match committed FFmpeg source metadata' -Message 'Validator must anchor provenance to committed source metadata.'
    }
}

function Test-RejectsProvenanceSigningKeyFingerprintMismatch {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.signing_key_fingerprint = '0000000000000000000000000000000000000000'
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'provenance signing_key_fingerprint does not match committed FFmpeg source metadata' -Message 'Validator must anchor signing key expectations to committed source metadata.'
    }
}

function Test-RejectsSourceBundleSignatureUrlMismatch {
    Invoke-PayloadTest {
        param($payload)
        $manifest = Read-SourceBundleManifest -Payload $payload
        $manifest.ffmpeg_source_signature_url = 'https://example.test/stale.asc'
        Write-SourceBundleManifest -Payload $payload -Manifest $manifest

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle manifest source signature URL does not match committed FFmpeg source metadata' -Message 'Validator must anchor source-bundle signature metadata to committed source metadata.'
    }
}

function Test-RejectsSourceBundleSigningKeyFingerprintMismatch {
    Invoke-PayloadTest {
        param($payload)
        $manifest = Read-SourceBundleManifest -Payload $payload
        $manifest.signing_key_fingerprint = '0000000000000000000000000000000000000000'
        Write-SourceBundleManifest -Payload $payload -Manifest $manifest

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'source bundle manifest signing key fingerprint does not match committed FFmpeg source metadata' -Message 'Validator must anchor source-bundle signing key metadata to committed source metadata.'
    }
}

function Test-SmokeFailureFails {
    Invoke-PayloadTest {
        param($payload)
        $env:ROOK_FAKE_FFMPEG_FAIL = '1'
        try {
            $output = Invoke-ValidationExpectFailure -Payload $payload
        } finally {
            Remove-Item Env:\ROOK_FAKE_FFMPEG_FAIL -ErrorAction SilentlyContinue
        }

        Assert-Contains -Text $output -Expected 'poster smoke extraction failed' -Message 'Poster smoke extraction failure should be reported.'
    }
}

function Test-StagedPayloadMissingOwnFfmpegFails {
    $payload = New-TestPayload
    try {
        $stagedPayload = Join-Path $payload.Root 'staged\third_party\ffmpeg'
        New-Item -ItemType Directory -Path (Join-Path $stagedPayload 'fixtures') | Out-Null

        foreach ($fileName in @('ffmpeg-provenance.json', 'LICENSE.FFmpeg.txt', 'NOTICE.FFmpeg.txt', 'SOURCE.FFmpeg.txt', 'README.md')) {
            Copy-Item -LiteralPath (Join-Path $payload.Payload $fileName) -Destination (Join-Path $stagedPayload $fileName)
        }

        Copy-Item -LiteralPath (Join-Path $payload.Payload 'fixtures\sidecar-smoke-h264.mp4') -Destination (Join-Path $stagedPayload 'fixtures\sidecar-smoke-h264.mp4')
        Copy-Item -LiteralPath (Join-Path $payload.Payload 'fixtures\sidecar-smoke-vp9.webm') -Destination (Join-Path $stagedPayload 'fixtures\sidecar-smoke-vp9.webm')

        $staged = [pscustomobject]@{
            Root = $payload.Root
            Payload = $stagedPayload
            Installer = $payload.Installer
            Provenance = Join-Path $stagedPayload 'ffmpeg-provenance.json'
            Ffmpeg = Join-Path $stagedPayload 'ffmpeg.exe'
            AllowlistPath = $payload.AllowlistPath
            SourceMetadataPath = $payload.SourceMetadataPath
            SourceBundleManifestPath = $payload.SourceBundleManifestPath
        }

        $output = Invoke-ValidationExpectFailure -Payload $staged
        Assert-Contains -Text $output -Expected 'bundled ffmpeg.exe is missing from PayloadDir' -Message 'Validation must use PayloadDir ffmpeg.exe, not a repo-root binary.'
    } finally {
        if (Test-Path -LiteralPath $payload.Root) {
            Remove-Item -LiteralPath $payload.Root -Recurse -Force
        }
    }
}

function Test-MissingInstallerSourceEntryFails {
    Invoke-PayloadTest {
        param($payload)
        $installerContent = @'
; third_party\ffmpeg\SOURCE.FFmpeg.txt appears only in a comment and must not satisfy validation.
Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\ffmpeg-provenance.json"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\LICENSE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\NOTICE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
'@
        Set-Content -LiteralPath $payload.Installer -Value $installerContent -Encoding ASCII

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'installer script is missing Source entry for third_party\ffmpeg\SOURCE.FFmpeg.txt' -Message 'Missing installer Source entry should be reported.'
    }
}

function Test-InstallerSourceEntryIgnoresPathOutsideSourceValue {
    Invoke-PayloadTest {
        param($payload)
        $installerContent = @'
Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\ffmpeg-provenance.json"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\LICENSE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\NOTICE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#RepoRoot}\README.md"; DestDir: "{app}"; Check: True or FileExists('third_party\ffmpeg\SOURCE.FFmpeg.txt')
'@
        Set-Content -LiteralPath $payload.Installer -Value $installerContent -Encoding ASCII

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'installer script is missing Source entry for third_party\ffmpeg\SOURCE.FFmpeg.txt' -Message 'Only the quoted Source value should satisfy installer validation.'
    }
}

function Test-InstallerSourceEntryWithSkipIfSourceDoesNotExistFails {
    Invoke-PayloadTest {
        param($payload)
        $installerContent = (Get-TestInstallerContent).Replace(
            'Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{app}\third_party\ffmpeg"',
            'Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{app}\third_party\ffmpeg"; Flags: ignoreversion skipifsourcedoesntexist'
        )
        Set-Content -LiteralPath $payload.Installer -Value $installerContent -Encoding ASCII

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'must fail closed and must not use skipifsourcedoesntexist' -Message 'FFmpeg installer Source entries must not allow missing payload files.'
    }
}

Test-ValidPayloadPasses
Test-ProvenanceEnableGplFails
Test-ProvenanceEnableNonfreeFails
Test-MissingConfigureLineFails
Test-BinarySha256MismatchFails
Test-StaleConfigureLineFails
Test-StaleVersionFails
Test-MissingNoticeFails
Test-RejectsUnexpectedEnableZlib
Test-RejectsMissingSourceSignatureVerification
Test-RejectsMissingSourceBundleManifest
Test-RejectsSourceBundleHashMismatch
Test-RejectsMissingRequiredH264FixtureMetadata
Test-RejectsMissingRequiredVp9OrAv1FixtureMetadata
Test-RejectsMissingChangesDiffInsideSourceBundle
Test-RejectsMissingSourceArchiveInsideSourceBundle
Test-RejectsMissingSourceSignatureInsideSourceBundle
Test-RejectsTamperedSourceArchiveInsideSourceBundle
Test-RejectsTamperedSourceSignatureInsideSourceBundle
Test-RejectsMismatchedConfigureRecipeInsideSourceBundle
Test-RejectsMismatchedSourceMetadataInsideSourceBundle
Test-RejectsMismatchedAllowlistInsideSourceBundle
Test-RejectsMismatchedBuildScriptInsideSourceBundle
Test-RejectsProvenanceSourceUrlMismatch
Test-RejectsProvenanceSigningKeyFingerprintMismatch
Test-RejectsSourceBundleSignatureUrlMismatch
Test-RejectsSourceBundleSigningKeyFingerprintMismatch
Test-SmokeFailureFails
Test-StagedPayloadMissingOwnFfmpegFails
Test-MissingInstallerSourceEntryFails
Test-InstallerSourceEntryIgnoresPathOutsideSourceValue
Test-InstallerSourceEntryWithSkipIfSourceDoesNotExistFails

Remove-Item Env:\ROOK_FAKE_FFMPEG_FAIL -ErrorAction SilentlyContinue

Write-Host 'FFmpeg bundle validation policy tests passed.'
