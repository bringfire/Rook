param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PayloadDir = '',
    [string]$InstallerScriptPath = '',
    [string]$AllowlistPath = '',
    [string]$SourceMetadataPath = '',
    [string]$SourceBundleManifestPath = '',
    [switch]$SkipFunctionalSmoke
)

$ErrorActionPreference = 'Stop'

function Fail {
    param([string]$Message)
    throw "FFmpeg bundle validation failed: $Message"
}

function Require-NonEmptyField {
    param(
        [object]$Provenance,
        [string]$Field
    )

    $property = $Provenance.PSObject.Properties[$Field]
    if ($null -eq $property) {
        Fail "provenance field '$Field' is missing"
    }

    if ($null -eq $property.Value) {
        Fail "provenance field '$Field' is empty"
    }

    if ($property.Value -is [string] -and [string]::IsNullOrWhiteSpace($property.Value)) {
        Fail "provenance field '$Field' is empty"
    }
}

function Require-NonEmptyManifestField {
    param(
        [object]$Manifest,
        [string]$Field
    )

    $property = $Manifest.PSObject.Properties[$Field]
    if ($null -eq $property -or $null -eq $property.Value) {
        Fail "source bundle manifest field '$Field' is missing"
    }

    if ($property.Value -is [string] -and [string]::IsNullOrWhiteSpace($property.Value)) {
        Fail "source bundle manifest field '$Field' is empty"
    }
}

function Normalize-ConfigureLine {
    param([string]$Value)
    return (($Value -replace '\s+', ' ').Trim())
}

function Get-ConfigureLineFromRecipeText {
    param([string]$Value)

    return Normalize-ConfigureLine ((@($Value -split "`r?`n" | Where-Object {
        -not [string]::IsNullOrWhiteSpace($_) -and -not $_.TrimStart().StartsWith('#')
    }) | ForEach-Object { $_.Trim() }) -join ' ')
}

function Get-ConfigureEnableFlags {
    param([string]$ConfigureLine)

    return [regex]::Matches($ConfigureLine, '(?<!\S)--enable-[^\s]+') |
        ForEach-Object { $_.Value } |
        Sort-Object -Unique
}

function Assert-NoForbiddenConfigureFlag {
    param(
        [string]$ConfigureLine,
        [string]$Source
    )

    foreach ($flag in @('--enable-gpl', '--enable-nonfree')) {
        if ($ConfigureLine -match "(^|\s)$([regex]::Escape($flag))(\s|$)") {
            Fail "$Source contains forbidden FFmpeg configure flag $flag"
        }
    }
}

function Get-AllowedEnableFlags {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "FFmpeg enable allowlist is missing: $Path"
    }

    try {
        $allowlist = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Fail "FFmpeg enable allowlist is malformed: $($_.Exception.Message)"
    }

    $flags = @($allowlist.allowed_enable_flags | Sort-Object -Unique)
    if ($flags.Count -eq 0) {
        Fail "FFmpeg enable allowlist is empty"
    }

    return $flags
}

function Assert-ConfigureEnableAllowlist {
    param(
        [string]$ConfigureLine,
        [string]$AllowlistPath
    )

    $actual = @(Get-ConfigureEnableFlags -ConfigureLine $ConfigureLine)
    $allowed = @(Get-AllowedEnableFlags -Path $AllowlistPath)

    foreach ($flag in $actual) {
        if ($allowed -notcontains $flag) {
            Fail "unexpected FFmpeg configure enable flag $flag"
        }
    }
}

function Get-CommittedSourceMetadata {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "committed FFmpeg source metadata is missing: $Path"
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Fail "committed FFmpeg source metadata is malformed: $($_.Exception.Message)"
    }
}

function Assert-ProvenanceMatchesSourceMetadata {
    param(
        [object]$Provenance,
        [object]$SourceMetadata
    )

    foreach ($field in @('source_url', 'source_archive', 'source_sha256', 'source_signature_url', 'signing_key_fingerprint')) {
        Require-NonEmptyField -Provenance $SourceMetadata -Field $field
        Require-NonEmptyField -Provenance $Provenance -Field $field
        if ($Provenance.$field -ne $SourceMetadata.$field) {
            Fail "provenance $field does not match committed FFmpeg source metadata"
        }
    }

    Require-NonEmptyField -Provenance $SourceMetadata -Field 'source_signature_status_required'
    if ($SourceMetadata.source_signature_status_required -ne 'verified') {
        Fail "committed FFmpeg source metadata must require verified signatures"
    }
}

function Assert-SourceSignatureVerified {
    param([object]$Provenance)

    Require-NonEmptyField -Provenance $Provenance -Field 'source_signature_url'
    Require-NonEmptyField -Provenance $Provenance -Field 'source_signature_status'

    if ($Provenance.source_signature_status -ne 'verified') {
        Fail "source_signature_status must be verified for official FFmpeg release source"
    }
}

function Assert-ValidatedFixtureCoverage {
    param([object]$Provenance)

    Require-NonEmptyField -Provenance $Provenance -Field 'validated_fixtures'
    $fixtures = @($Provenance.validated_fixtures)
    if ($fixtures.Count -eq 0) {
        Fail "validated_fixtures is empty"
    }

    $hasH264Mp4 = $false
    $hasVp9WebmOrAv1 = $false

    foreach ($fixture in $fixtures) {
        $container = [string]$fixture.container
        $codec = [string]$fixture.video_codec

        if ($container -eq 'mp4' -and $codec -eq 'h264') {
            $hasH264Mp4 = $true
        }

        if (($container -eq 'webm' -and $codec -eq 'vp9') -or $codec -eq 'av1') {
            $hasVp9WebmOrAv1 = $true
        }
    }

    if (-not $hasH264Mp4) {
        Fail "validated_fixtures must include h264 mp4 coverage"
    }

    if (-not $hasVp9WebmOrAv1) {
        Fail "validated_fixtures must include vp9 webm or av1 coverage"
    }
}

function Read-ZipEntryBytes {
    param(
        [string]$ZipPath,
        [string]$EntryName
    )

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $match = @($zip.Entries | Where-Object { $_.FullName.Replace('\', '/') -eq $EntryName })
        if ($match.Count -eq 0) {
            Fail "source bundle is missing required entry $EntryName"
        }

        if ($match.Count -ne 1) {
            Fail "source bundle has duplicate required entry $EntryName"
        }

        $stream = $match[0].Open()
        try {
            $memory = New-Object System.IO.MemoryStream
            try {
                $stream.CopyTo($memory)
                return ,$memory.ToArray()
            } finally {
                $memory.Dispose()
            }
        } finally {
            $stream.Dispose()
        }
    } finally {
        $zip.Dispose()
    }
}

function Read-ZipEntryText {
    param(
        [string]$ZipPath,
        [string]$EntryName
    )

    $bytes = Read-ZipEntryBytes -ZipPath $ZipPath -EntryName $EntryName
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

function Get-Sha256Hex {
    param([byte[]]$Bytes)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($sha.ComputeHash($Bytes)).Replace('-', '').ToUpperInvariant()
    } finally {
        $sha.Dispose()
    }
}

function Assert-ZipEntrySha256 {
    param(
        [string]$ZipPath,
        [string]$EntryName,
        [string]$Expected,
        [string]$Message
    )

    $actual = Get-Sha256Hex -Bytes (Read-ZipEntryBytes -ZipPath $ZipPath -EntryName $EntryName)
    if ($actual -ne $Expected.ToUpperInvariant()) {
        Fail $Message
    }
}

function Assert-ZipEntryMatchesFile {
    param(
        [string]$ZipPath,
        [string]$EntryName,
        [string]$ExpectedPath,
        [string]$Message
    )

    if (-not (Test-Path -LiteralPath $ExpectedPath -PathType Leaf)) {
        Fail "committed release input is missing: $ExpectedPath"
    }

    $actual = Get-Sha256Hex -Bytes (Read-ZipEntryBytes -ZipPath $ZipPath -EntryName $EntryName)
    $expected = (Get-FileHash -LiteralPath $ExpectedPath -Algorithm SHA256).Hash.ToUpperInvariant()
    if ($actual -ne $expected) {
        Fail $Message
    }
}

function Assert-SourceBundleManifest {
    param(
        [string]$Path,
        [object]$Provenance,
        [object]$SourceMetadata,
        [string]$RuntimeConfigureLine,
        [string]$SourceMetadataPath,
        [string]$AllowlistPath,
        [string]$ConfigureRecipePath,
        [string]$BuildScriptPath
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "source bundle manifest is missing"
    }

    try {
        $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Fail "source bundle manifest is malformed: $($_.Exception.Message)"
    }

    foreach ($field in @('bundle_path', 'bundle_sha256', 'ffmpeg_source_archive', 'ffmpeg_source_sha256', 'ffmpeg_source_signature_url', 'signing_key_fingerprint', 'configure_line', 'changes_diff_path', 'build_recipe_path', 'generated_at', 'generated_by')) {
        Require-NonEmptyField -Provenance $manifest -Field $field
    }

    if ($manifest.ffmpeg_source_archive -ne $SourceMetadata.source_archive) {
        Fail "source bundle manifest source archive does not match committed FFmpeg source metadata"
    }

    if ($manifest.ffmpeg_source_sha256 -ne $SourceMetadata.source_sha256) {
        Fail "source bundle manifest source checksum does not match committed FFmpeg source metadata"
    }

    Require-NonEmptyManifestField -Manifest $manifest -Field 'ffmpeg_source_signature_sha256'

    if ($manifest.ffmpeg_source_signature_url -ne $SourceMetadata.source_signature_url) {
        Fail "source bundle manifest source signature URL does not match committed FFmpeg source metadata"
    }

    if ($manifest.signing_key_fingerprint -ne $SourceMetadata.signing_key_fingerprint) {
        Fail "source bundle manifest signing key fingerprint does not match committed FFmpeg source metadata"
    }

    if ($manifest.ffmpeg_source_archive -ne $Provenance.source_archive) {
        Fail "source bundle manifest source archive does not match provenance"
    }

    if ($manifest.ffmpeg_source_sha256 -ne $Provenance.source_sha256) {
        Fail "source bundle manifest source checksum does not match provenance"
    }

    if ($manifest.ffmpeg_source_signature_url -ne $Provenance.source_signature_url) {
        Fail "source bundle manifest source signature URL does not match provenance"
    }

    if ($manifest.signing_key_fingerprint -ne $Provenance.signing_key_fingerprint) {
        Fail "source bundle manifest signing key fingerprint does not match provenance"
    }

    if ((Normalize-ConfigureLine $manifest.configure_line) -ne (Normalize-ConfigureLine $Provenance.configure_line)) {
        Fail "source bundle manifest configure line does not match provenance"
    }

    if (-not (Test-Path -LiteralPath $manifest.bundle_path -PathType Leaf)) {
        Fail "source bundle is missing: $($manifest.bundle_path)"
    }

    $actualHash = (Get-FileHash -LiteralPath $manifest.bundle_path -Algorithm SHA256).Hash
    if ($actualHash -ne $manifest.bundle_sha256) {
        Fail "source bundle checksum mismatch"
    }

    Assert-ZipEntrySha256 `
        -ZipPath $manifest.bundle_path `
        -EntryName $Provenance.source_archive `
        -Expected $SourceMetadata.source_sha256 `
        -Message 'source bundle source archive checksum mismatch'

    Assert-ZipEntrySha256 `
        -ZipPath $manifest.bundle_path `
        -EntryName "$($Provenance.source_archive).asc" `
        -Expected $manifest.ffmpeg_source_signature_sha256 `
        -Message 'source bundle source signature checksum mismatch'

    $null = Read-ZipEntryBytes -ZipPath $manifest.bundle_path -EntryName 'changes.diff'

    Assert-ZipEntryMatchesFile `
        -ZipPath $manifest.bundle_path `
        -EntryName 'rook-ffmpeg-source.json' `
        -ExpectedPath $SourceMetadataPath `
        -Message 'source bundle source metadata does not match committed FFmpeg source metadata'

    Assert-ZipEntryMatchesFile `
        -ZipPath $manifest.bundle_path `
        -EntryName 'rook-ffmpeg-enable-allowlist.json' `
        -ExpectedPath $AllowlistPath `
        -Message 'source bundle enable allowlist does not match committed FFmpeg allowlist'

    Assert-ZipEntryMatchesFile `
        -ZipPath $manifest.bundle_path `
        -EntryName 'build-rook-ffmpeg.ps1' `
        -ExpectedPath $BuildScriptPath `
        -Message 'source bundle build script does not match committed FFmpeg build recipe'

    Assert-ZipEntryMatchesFile `
        -ZipPath $manifest.bundle_path `
        -EntryName 'rook-ffmpeg-configure.txt' `
        -ExpectedPath $ConfigureRecipePath `
        -Message 'source bundle configure recipe does not match committed FFmpeg configure recipe'

    $embeddedConfigureLine = Get-ConfigureLineFromRecipeText (
        Read-ZipEntryText -ZipPath $manifest.bundle_path -EntryName 'rook-ffmpeg-configure.txt')
    if ($embeddedConfigureLine -ne (Normalize-ConfigureLine $manifest.configure_line)) {
        Fail "source bundle configure recipe does not match source bundle manifest configure line"
    }

    if ($embeddedConfigureLine -ne (Normalize-ConfigureLine $Provenance.configure_line)) {
        Fail "source bundle configure recipe does not match provenance configure line"
    }

    if ($embeddedConfigureLine -ne (Normalize-ConfigureLine $RuntimeConfigureLine)) {
        Fail "source bundle configure recipe does not match runtime configuration line"
    }
}

function Invoke-FFmpegCommand {
    param(
        [string]$ExePath,
        [string[]]$Arguments
    )

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & $ExePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    return [pscustomobject]@{
        ExitCode = $exitCode
        Output = ($output -join "`n")
    }
}

function Assert-ReleaseValidTextFile {
    param(
        [string]$Path,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "$Name is missing"
    }

    $content = Get-Content -LiteralPath $Path -Raw
    if ([string]::IsNullOrWhiteSpace($content)) {
        Fail "$Name is empty"
    }

    if ($content -match '(?i)scaffold|not\s+release-valid|belongs here|replace it') {
        Fail "$Name contains scaffold text and is not release-valid"
    }
}

function Assert-InstallerSourceEntry {
    param(
        [string[]]$SourceLines,
        [string]$FileName
    )

    $acceptedSources = @(
        "{#FfmpegDir}\$FileName",
        "{#RepoRoot}\third_party\ffmpeg\$FileName",
        "third_party\ffmpeg\$FileName"
    )

    $matches = $SourceLines | Where-Object {
        if ($_ -notmatch '(?i)^Source:\s*"([^"]+)"') {
            return $false
        }

        $sourceValue = $Matches[1] -replace '/', '\'
        foreach ($acceptedSource in $acceptedSources) {
            if ($sourceValue -ieq $acceptedSource) {
                return $true
            }
        }

        return $false
    }

    if (@($matches).Count -eq 0) {
        Fail "installer script is missing Source entry for third_party\ffmpeg\$FileName"
    }

    foreach ($match in $matches) {
        if ($match -match '(?i)\bskipifsourcedoesntexist\b') {
            Fail "installer Source entry for third_party\ffmpeg\$FileName must fail closed and must not use skipifsourcedoesntexist"
        }
    }
}

function Assert-ReadableJpeg {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "$Label smoke output is missing: $Path"
    }

    $item = Get-Item -LiteralPath $Path
    if ($item.Length -le 0) {
        Fail "$Label smoke output is empty: $Path"
    }

    Add-Type -AssemblyName System.Drawing
    $image = $null
    try {
        $image = [System.Drawing.Image]::FromFile($Path)
        if ($image.Width -le 0 -or $image.Height -le 0) {
            Fail "$Label smoke output has invalid dimensions: $($image.Width)x$($image.Height)"
        }
    } catch {
        Fail "$Label smoke output is not a readable JPEG image: $($_.Exception.Message)"
    } finally {
        if ($null -ne $image) {
            $image.Dispose()
        }
    }
}

function Invoke-SmokeExtraction {
    param(
        [string]$ExePath,
        [string]$Label,
        [string[]]$Arguments,
        [string]$OutputPath
    )

    $result = Invoke-FFmpegCommand -ExePath $ExePath -Arguments $Arguments
    if ($result.ExitCode -ne 0) {
        Fail "$Label smoke extraction failed with exit code $($result.ExitCode): $($result.Output)"
    }

    Assert-ReadableJpeg -Path $OutputPath -Label $Label
}

function Invoke-SmokeForFixture {
    param(
        [string]$FfmpegPath,
        [string]$FixturePath
    )

    $smokeTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "rook-ffmpeg-smoke-$([System.Guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $smokeTempDir | Out-Null

    try {
        $posterPath = Join-Path $smokeTempDir 'poster.jpg'
        Invoke-SmokeExtraction `
            -ExePath $FfmpegPath `
            -Label 'poster' `
            -OutputPath $posterPath `
            -Arguments @('-hide_banner', '-y', '-ss', '00:00:00.100', '-i', $FixturePath, '-frames:v', '1', '-q:v', '2', $posterPath)

        $firstPath = Join-Path $smokeTempDir 'first.jpg'
        Invoke-SmokeExtraction `
            -ExePath $FfmpegPath `
            -Label 'first frame' `
            -OutputPath $firstPath `
            -Arguments @('-hide_banner', '-y', '-i', $FixturePath, '-map', '0:v:0', '-an', '-vf', 'select=eq(n\,0)', '-vsync', '0', '-frames:v', '1', '-q:v', '2', $firstPath)

        $lastPath = Join-Path $smokeTempDir 'last.jpg'
        Invoke-SmokeExtraction `
            -ExePath $FfmpegPath `
            -Label 'last frame' `
            -OutputPath $lastPath `
            -Arguments @('-hide_banner', '-y', '-i', $FixturePath, '-map', '0:v:0', '-an', '-vf', 'reverse,select=eq(n\,0)', '-vsync', '0', '-frames:v', '1', '-q:v', '2', $lastPath)
    } finally {
        if (Test-Path -LiteralPath $smokeTempDir) {
            Remove-Item -LiteralPath $smokeTempDir -Recurse -Force
        }
    }
}

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
if ([string]::IsNullOrWhiteSpace($PayloadDir)) {
    $PayloadDir = Join-Path $RepoRoot 'third_party\ffmpeg'
}

if ([string]::IsNullOrWhiteSpace($InstallerScriptPath)) {
    $InstallerScriptPath = Join-Path $RepoRoot 'installer\RookSetup.iss'
}

if ([string]::IsNullOrWhiteSpace($AllowlistPath)) {
    $AllowlistPath = Join-Path $RepoRoot 'scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json'
}

if ([string]::IsNullOrWhiteSpace($SourceMetadataPath)) {
    $SourceMetadataPath = Join-Path $RepoRoot 'scripts\ffmpeg\rook-ffmpeg-source.json'
}

$PayloadDir = [System.IO.Path]::GetFullPath($PayloadDir)
$InstallerScriptPath = [System.IO.Path]::GetFullPath($InstallerScriptPath)
$AllowlistPath = [System.IO.Path]::GetFullPath($AllowlistPath)
$SourceMetadataPath = [System.IO.Path]::GetFullPath($SourceMetadataPath)
$FfmpegScriptMetadataDir = Split-Path -Parent $SourceMetadataPath
$ConfigureRecipePath = Join-Path $FfmpegScriptMetadataDir 'rook-ffmpeg-configure.txt'
$BuildScriptPath = Join-Path $FfmpegScriptMetadataDir 'build-rook-ffmpeg.ps1'
$provenancePath = Join-Path $PayloadDir 'ffmpeg-provenance.json'

if (-not (Test-Path -LiteralPath $provenancePath -PathType Leaf)) {
    Fail "ffmpeg-provenance.json is missing: $provenancePath"
}

try {
    $provenance = Get-Content -LiteralPath $provenancePath -Raw | ConvertFrom-Json
} catch {
    Fail "ffmpeg-provenance.json is malformed: $($_.Exception.Message)"
}

$requiredFields = @(
    'name',
    'version',
    'license',
    'binary_path',
    'binary_sha256',
    'source_url',
    'source_archive',
    'source_sha256',
    'source_signature_url',
    'signing_key_fingerprint',
    'source_signature_status',
    'build_recipe_path',
    'configure_recipe_path',
    'configure_line',
    'changes_diff_path',
    'source_bundle_manifest_name',
    'verified_at',
    'verified_by'
)

foreach ($field in $requiredFields) {
    Require-NonEmptyField -Provenance $provenance -Field $field
}

if ($provenance.license -ne 'LGPL-only') {
    Fail "provenance license must be exactly LGPL-only; actual value: $($provenance.license)"
}

$surfacesProperty = $provenance.PSObject.Properties['validated_command_surfaces']
if ($null -eq $surfacesProperty -or $null -eq $surfacesProperty.Value) {
    Fail "provenance field 'validated_command_surfaces' is missing"
}

$surfaces = @($surfacesProperty.Value)
foreach ($surface in @('poster', 'first_frame', 'last_frame')) {
    if ($surfaces -notcontains $surface) {
        Fail "validated_command_surfaces must include $surface"
    }
}

$sourceMetadata = Get-CommittedSourceMetadata -Path $SourceMetadataPath
Assert-ProvenanceMatchesSourceMetadata -Provenance $provenance -SourceMetadata $sourceMetadata
Assert-SourceSignatureVerified -Provenance $provenance
Assert-ValidatedFixtureCoverage -Provenance $provenance
Assert-NoForbiddenConfigureFlag -ConfigureLine $provenance.configure_line -Source 'provenance configure_line'

$declaredBinaryPath = ([string]$provenance.binary_path).Replace('\', '/')
if ($declaredBinaryPath -ne 'third_party/ffmpeg/ffmpeg.exe') {
    Fail "provenance binary_path must be exactly third_party/ffmpeg/ffmpeg.exe; actual value: $($provenance.binary_path)"
}

$ffmpegPath = Join-Path $PayloadDir 'ffmpeg.exe'
if (-not (Test-Path -LiteralPath $ffmpegPath -PathType Leaf)) {
    Fail "bundled ffmpeg.exe is missing from PayloadDir: $ffmpegPath"
}

$actualHash = (Get-FileHash -LiteralPath $ffmpegPath -Algorithm SHA256).Hash.ToUpperInvariant()
$expectedHash = ([string]$provenance.binary_sha256).ToUpperInvariant()
if ($actualHash -ne $expectedHash) {
    Fail "ffmpeg.exe checksum mismatch: expected $expectedHash, actual $actualHash"
}

$versionResult = Invoke-FFmpegCommand -ExePath $ffmpegPath -Arguments @('-version')
if ($versionResult.ExitCode -ne 0) {
    Fail "ffmpeg.exe -version failed with exit code $($versionResult.ExitCode): $($versionResult.Output)"
}

$runtimeVersionLine = ($versionResult.Output -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($runtimeVersionLine) -or $runtimeVersionLine -notmatch '^ffmpeg version\s+(\S+)') {
    Fail "ffmpeg.exe -version output did not include a parseable first line"
}

$runtimeVersion = $Matches[1]
if ($runtimeVersion -ne [string]$provenance.version) {
    Fail "provenance version does not match runtime ffmpeg version: expected $($provenance.version), actual $runtimeVersion"
}

$runtimeConfigurationLine = ($versionResult.Output -split "`r?`n" | Where-Object { $_ -like 'configuration:*' } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($runtimeConfigurationLine)) {
    Fail "ffmpeg.exe -version output did not include a configuration: line"
}

$runtimeConfigure = $runtimeConfigurationLine.Substring('configuration:'.Length).Trim()
Assert-NoForbiddenConfigureFlag -ConfigureLine $runtimeConfigure -Source 'runtime configuration line'
Assert-ConfigureEnableAllowlist -ConfigureLine $runtimeConfigure -AllowlistPath $AllowlistPath
Assert-ConfigureEnableAllowlist -ConfigureLine $provenance.configure_line -AllowlistPath $AllowlistPath

if ((Normalize-ConfigureLine $provenance.configure_line) -ne (Normalize-ConfigureLine $runtimeConfigure)) {
    Fail "provenance configure_line does not match runtime configuration line"
}

Assert-SourceBundleManifest `
    -Path $SourceBundleManifestPath `
    -Provenance $provenance `
    -SourceMetadata $sourceMetadata `
    -RuntimeConfigureLine $runtimeConfigure `
    -SourceMetadataPath $SourceMetadataPath `
    -AllowlistPath $AllowlistPath `
    -ConfigureRecipePath $ConfigureRecipePath `
    -BuildScriptPath $BuildScriptPath

Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'LICENSE.FFmpeg.txt') -Name 'LICENSE.FFmpeg.txt'
Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'NOTICE.FFmpeg.txt') -Name 'NOTICE.FFmpeg.txt'
Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'SOURCE.FFmpeg.txt') -Name 'SOURCE.FFmpeg.txt'

if (-not (Test-Path -LiteralPath $InstallerScriptPath -PathType Leaf)) {
    Fail "installer script is missing: $InstallerScriptPath"
}

$installerContent = Get-Content -LiteralPath $InstallerScriptPath -Raw
$installerSourceLines = $installerContent -split "`r?`n" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -match '(?i)^Source:\s*"' }

foreach ($requiredInstallerFile in @('ffmpeg.exe', 'ffmpeg-provenance.json', 'LICENSE.FFmpeg.txt', 'NOTICE.FFmpeg.txt', 'SOURCE.FFmpeg.txt', 'README.md')) {
    Assert-InstallerSourceEntry -SourceLines $installerSourceLines -FileName $requiredInstallerFile
}

if (-not $SkipFunctionalSmoke) {
    foreach ($fixture in @($provenance.validated_fixtures)) {
        Require-NonEmptyField -Provenance $fixture -Field 'path'
        Require-NonEmptyField -Provenance $fixture -Field 'container'
        Require-NonEmptyField -Provenance $fixture -Field 'video_codec'

        $fixturePath = Join-Path $RepoRoot ([string]$fixture.path)
        if (-not (Test-Path -LiteralPath $fixturePath -PathType Leaf)) {
            Fail "validated fixture is missing: $fixturePath"
        }

        Invoke-SmokeForFixture -FfmpegPath $ffmpegPath -FixturePath $fixturePath
    }
}

Write-Host "FFmpeg bundle validation passed: $($provenance.version) $actualHash"
