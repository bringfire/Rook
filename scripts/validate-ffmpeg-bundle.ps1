param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PayloadDir = '',
    [string]$InstallerScriptPath = '',
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

function Normalize-ConfigureLine {
    param([string]$Value)
    return (($Value -replace '\s+', ' ').Trim())
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

function Assert-DependencyManifest {
    param(
        [string]$Path,
        [object]$Provenance
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "ffmpeg-dependencies.json is missing"
    }

    try {
        $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Fail "ffmpeg-dependencies.json is malformed: $($_.Exception.Message)"
    }

    foreach ($field in @('name', 'binary_url', 'binary_archive_sha256', 'dependency_source_basis', 'enabled_configure_flags', 'verified_at', 'verified_by')) {
        Require-NonEmptyField -Provenance $manifest -Field $field
    }

    foreach ($field in @('name', 'release', 'commit', 'source_url', 'source_sha256')) {
        Require-NonEmptyField -Provenance $manifest.build_system -Field $field
    }

    if ($manifest.binary_url -ne $Provenance.binary_url) {
        Fail "ffmpeg-dependencies.json binary_url does not match ffmpeg-provenance.json"
    }

    $expectedFlags = @(Get-ConfigureEnableFlags -ConfigureLine $Provenance.configure_line)
    $manifestFlags = @($manifest.enabled_configure_flags | Sort-Object -Unique)

    if ($expectedFlags.Count -eq 0) {
        Fail "provenance configure_line did not contain any --enable-* flags for dependency manifest validation"
    }

    $missing = @(Compare-Object -ReferenceObject $expectedFlags -DifferenceObject $manifestFlags |
        Where-Object { $_.SideIndicator -eq '<=' } |
        ForEach-Object { $_.InputObject })
    if ($missing.Count -gt 0) {
        Fail "ffmpeg-dependencies.json is missing enabled configure flags: $($missing -join ', ')"
    }

    $extra = @(Compare-Object -ReferenceObject $expectedFlags -DifferenceObject $manifestFlags |
        Where-Object { $_.SideIndicator -eq '=>' } |
        ForEach-Object { $_.InputObject })
    if ($extra.Count -gt 0) {
        Fail "ffmpeg-dependencies.json contains flags not present in configure_line: $($extra -join ', ')"
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
        [string]$FixturePath,
        [string]$TempDir,
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

$RepoRoot = [System.IO.Path]::GetFullPath($RepoRoot)
if ([string]::IsNullOrWhiteSpace($PayloadDir)) {
    $PayloadDir = Join-Path $RepoRoot 'third_party\ffmpeg'
}

if ([string]::IsNullOrWhiteSpace($InstallerScriptPath)) {
    $InstallerScriptPath = Join-Path $RepoRoot 'installer\RookSetup.iss'
}

$PayloadDir = [System.IO.Path]::GetFullPath($PayloadDir)
$InstallerScriptPath = [System.IO.Path]::GetFullPath($InstallerScriptPath)
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
    'binary_url',
    'build_source',
    'source_url',
    'source_archive',
    'source_sha256',
    'configure_line',
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

if ((Normalize-ConfigureLine $provenance.configure_line) -ne (Normalize-ConfigureLine $runtimeConfigure)) {
    Fail "provenance configure_line does not match runtime configuration line"
}

Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'LICENSE.FFmpeg.txt') -Name 'LICENSE.FFmpeg.txt'
Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'NOTICE.FFmpeg.txt') -Name 'NOTICE.FFmpeg.txt'
Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'SOURCE.FFmpeg.txt') -Name 'SOURCE.FFmpeg.txt'
Assert-ReleaseValidTextFile -Path (Join-Path $PayloadDir 'DEPENDENCIES.FFmpeg.txt') -Name 'DEPENDENCIES.FFmpeg.txt'
Assert-DependencyManifest -Path (Join-Path $PayloadDir 'ffmpeg-dependencies.json') -Provenance $provenance

if (-not (Test-Path -LiteralPath $InstallerScriptPath -PathType Leaf)) {
    Fail "installer script is missing: $InstallerScriptPath"
}

$installerContent = Get-Content -LiteralPath $InstallerScriptPath -Raw
$installerSourceLines = $installerContent -split "`r?`n" |
    ForEach-Object { $_.Trim() } |
    Where-Object { $_ -match '(?i)^Source:\s*"' }

foreach ($requiredInstallerFile in @('ffmpeg.exe', 'ffmpeg-provenance.json', 'ffmpeg-dependencies.json', 'LICENSE.FFmpeg.txt', 'NOTICE.FFmpeg.txt', 'SOURCE.FFmpeg.txt', 'DEPENDENCIES.FFmpeg.txt', 'README.md')) {
    Assert-InstallerSourceEntry -SourceLines $installerSourceLines -FileName $requiredInstallerFile
}

if (-not $SkipFunctionalSmoke) {
    $fixturePath = Join-Path $PayloadDir 'fixtures\sidecar-smoke.mp4'
    if (-not (Test-Path -LiteralPath $fixturePath -PathType Leaf)) {
        Fail "functional smoke fixture is missing: $fixturePath"
    }

    $smokeTempDir = Join-Path ([System.IO.Path]::GetTempPath()) "rook-ffmpeg-smoke-$([System.Guid]::NewGuid().ToString('N'))"
    New-Item -ItemType Directory -Path $smokeTempDir | Out-Null

    try {
        $posterPath = Join-Path $smokeTempDir 'poster.jpg'
        Invoke-SmokeExtraction `
            -ExePath $ffmpegPath `
            -FixturePath $fixturePath `
            -TempDir $smokeTempDir `
            -Label 'poster' `
            -OutputPath $posterPath `
            -Arguments @('-hide_banner', '-y', '-ss', '00:00:00.100', '-i', $fixturePath, '-frames:v', '1', '-q:v', '2', $posterPath)

        $firstPath = Join-Path $smokeTempDir 'first.jpg'
        Invoke-SmokeExtraction `
            -ExePath $ffmpegPath `
            -FixturePath $fixturePath `
            -TempDir $smokeTempDir `
            -Label 'first frame' `
            -OutputPath $firstPath `
            -Arguments @('-hide_banner', '-y', '-i', $fixturePath, '-map', '0:v:0', '-an', '-vf', 'select=eq(n\,0)', '-vsync', '0', '-frames:v', '1', '-q:v', '2', $firstPath)

        $lastPath = Join-Path $smokeTempDir 'last.jpg'
        Invoke-SmokeExtraction `
            -ExePath $ffmpegPath `
            -FixturePath $fixturePath `
            -TempDir $smokeTempDir `
            -Label 'last frame' `
            -OutputPath $lastPath `
            -Arguments @('-hide_banner', '-y', '-i', $fixturePath, '-map', '0:v:0', '-an', '-vf', 'reverse,select=eq(n\,0)', '-vsync', '0', '-frames:v', '1', '-q:v', '2', $lastPath)
    } finally {
        if (Test-Path -LiteralPath $smokeTempDir) {
            Remove-Item -LiteralPath $smokeTempDir -Recurse -Force
        }
    }
}

Write-Host "FFmpeg bundle validation passed: $($provenance.version) $actualHash"
