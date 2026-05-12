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

    Assert-True -Condition $Text.Contains($Expected) -Message "$Message`nExpected to find: $Expected`nActual output:`n$Text"
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
            Console.WriteLine("ffmpeg version test-lgpl");
            Console.WriteLine("configuration: --disable-gpl --disable-nonfree --enable-libopus");
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
Source: "{#FfmpegDir}\ffmpeg-dependencies.json"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\LICENSE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\NOTICE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\SOURCE.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\DEPENDENCIES.FFmpeg.txt"; DestDir: "{app}\third_party\ffmpeg"
Source: "{#FfmpegDir}\README.md"; DestDir: "{app}\third_party\ffmpeg"
'@
}

function New-TestPayload {
    $root = Join-Path ([System.IO.Path]::GetTempPath()) "rook-ffmpeg-policy-$([System.Guid]::NewGuid().ToString('N'))"
    $payload = Join-Path $root 'third_party\ffmpeg'
    $fixtures = Join-Path $payload 'fixtures'
    $installerDir = Join-Path $root 'installer'
    $installer = Join-Path $installerDir 'RookSetup.iss'
    $ffmpeg = Join-Path $payload 'ffmpeg.exe'

    New-Item -ItemType Directory -Path $fixtures | Out-Null
    New-Item -ItemType Directory -Path $installerDir | Out-Null

    New-FakeFFmpeg -OutputPath $ffmpeg
    Set-Content -Path (Join-Path $fixtures 'sidecar-smoke.mp4') -Value 'fake fixture' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'LICENSE.FFmpeg.txt') -Value 'LGPL license text for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'NOTICE.FFmpeg.txt') -Value 'FFmpeg attribution notice for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'SOURCE.FFmpeg.txt') -Value 'Corresponding source URL and checksum for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'DEPENDENCIES.FFmpeg.txt') -Value 'Dependency source and license manifest for test payload.' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'README.md') -Value 'Bundled FFmpeg test payload summary.' -Encoding ASCII
    Set-Content -Path $installer -Value (Get-TestInstallerContent) -Encoding ASCII

    $hash = (Get-FileHash -LiteralPath $ffmpeg -Algorithm SHA256).Hash
    $provenance = [ordered]@{
        name = 'FFmpeg'
        version = 'test-lgpl'
        license = 'LGPL-only'
        binary_path = 'third_party/ffmpeg/ffmpeg.exe'
        binary_sha256 = $hash
        binary_url = 'https://example.test/ffmpeg/binary'
        build_source = 'test build system'
        source_url = 'https://example.test/ffmpeg/source'
        source_archive = 'ffmpeg-test.tar.xz'
        source_sha256 = ('a' * 64)
        configure_line = '--disable-gpl --disable-nonfree --enable-libopus'
        validated_command_surfaces = @('poster', 'first_frame', 'last_frame')
        verified_at = '2026-05-12T00:00:00Z'
        verified_by = 'policy-test'
    }

    $provenance | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $payload 'ffmpeg-provenance.json') -Encoding UTF8

    $dependencies = [ordered]@{
        name = 'test dependency manifest'
        binary_url = 'https://example.test/ffmpeg/binary'
        binary_archive_sha256 = ('c' * 64)
        build_system = [ordered]@{
            name = 'test build system'
            release = 'test-release'
            commit = 'test-commit'
            source_url = 'https://example.test/build-system/source.zip'
            source_sha256 = ('b' * 64)
        }
        dependency_source_basis = 'test build scripts define dependencies'
        enabled_configure_flags = @('--enable-libopus')
        verified_at = '2026-05-12T00:00:00Z'
        verified_by = 'policy-test'
    }

    $dependencies | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $payload 'ffmpeg-dependencies.json') -Encoding UTF8

    return [pscustomobject]@{
        Root = $root
        Payload = $payload
        Installer = $installer
        Provenance = Join-Path $payload 'ffmpeg-provenance.json'
        Dependencies = Join-Path $payload 'ffmpeg-dependencies.json'
        Ffmpeg = $ffmpeg
    }
}

function Read-DependencyManifest {
    param([object]$Payload)
    return Get-Content -LiteralPath $Payload.Dependencies -Raw | ConvertFrom-Json
}

function Write-DependencyManifest {
    param(
        [object]$Payload,
        [object]$Manifest
    )

    $Manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Payload.Dependencies -Encoding UTF8
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

    $Provenance | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Payload.Provenance -Encoding UTF8
}

function Invoke-Validation {
    param([object]$Payload)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & powershell -ExecutionPolicy Bypass -File $ValidatorScript -RepoRoot $Payload.Root -PayloadDir $Payload.Payload -InstallerScriptPath $Payload.Installer 2>&1
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
        $output = & powershell -ExecutionPolicy Bypass -File $ValidatorScript -RepoRoot $Payload.Root -PayloadDir $Payload.Payload -InstallerScriptPath $Payload.Installer 2>&1
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
        Assert-Contains -Text $output -Expected 'FFmpeg bundle validation passed: test-lgpl' -Message 'Valid payload should pass.'
    }
}

function Test-ProvenanceEnableGplFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = '--disable-nonfree --enable-gpl'
        Write-Provenance -Payload $payload -Provenance $provenance

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected '--enable-gpl' -Message 'Forbidden GPL configure flag should be reported.'
    }
}

function Test-ProvenanceEnableNonfreeFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = '--disable-gpl --enable-nonfree'
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
        $provenance.configure_line = '--disable-gpl --disable-nonfree --enable-small'
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

function Test-MissingDependencyManifestFails {
    Invoke-PayloadTest {
        param($payload)
        Remove-Item -LiteralPath $payload.Dependencies -Force

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'ffmpeg-dependencies.json is missing' -Message 'Missing dependency manifest should be reported.'
    }
}

function Test-StaleDependencyManifestFails {
    Invoke-PayloadTest {
        param($payload)
        $provenance = Read-Provenance -Payload $payload
        $provenance.configure_line = '--disable-gpl --disable-nonfree --enable-libopus'
        Write-Provenance -Payload $payload -Provenance $provenance

        $manifest = Read-DependencyManifest -Payload $payload
        $manifest.enabled_configure_flags = @('--enable-libvpx')
        Write-DependencyManifest -Payload $payload -Manifest $manifest

        $output = Invoke-ValidationExpectFailure -Payload $payload
        Assert-Contains -Text $output -Expected 'ffmpeg-dependencies.json is missing enabled configure flags: --enable-libopus' -Message 'Stale dependency manifest should be reported.'
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

        foreach ($fileName in @('ffmpeg-provenance.json', 'ffmpeg-dependencies.json', 'LICENSE.FFmpeg.txt', 'NOTICE.FFmpeg.txt', 'SOURCE.FFmpeg.txt', 'DEPENDENCIES.FFmpeg.txt', 'README.md')) {
            Copy-Item -LiteralPath (Join-Path $payload.Payload $fileName) -Destination (Join-Path $stagedPayload $fileName)
        }

        Copy-Item -LiteralPath (Join-Path $payload.Payload 'fixtures\sidecar-smoke.mp4') -Destination (Join-Path $stagedPayload 'fixtures\sidecar-smoke.mp4')

        $staged = [pscustomobject]@{
            Root = $payload.Root
            Payload = $stagedPayload
            Installer = $payload.Installer
            Provenance = Join-Path $stagedPayload 'ffmpeg-provenance.json'
            Ffmpeg = Join-Path $stagedPayload 'ffmpeg.exe'
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
Source: "{#FfmpegDir}\ffmpeg-dependencies.json"; DestDir: "{app}\third_party\ffmpeg"
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
Source: "{#FfmpegDir}\ffmpeg-dependencies.json"; DestDir: "{app}\third_party\ffmpeg"
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
Test-MissingDependencyManifestFails
Test-StaleDependencyManifestFails
Test-SmokeFailureFails
Test-StagedPayloadMissingOwnFfmpegFails
Test-MissingInstallerSourceEntryFails
Test-InstallerSourceEntryIgnoresPathOutsideSourceValue
Test-InstallerSourceEntryWithSkipIfSourceDoesNotExistFails

Remove-Item Env:\ROOK_FAKE_FFMPEG_FAIL -ErrorAction SilentlyContinue

Write-Host 'FFmpeg bundle validation policy tests passed.'
