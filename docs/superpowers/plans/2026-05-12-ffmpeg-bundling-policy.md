# FFmpeg Bundling Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bundle a vetted LGPL-only `ffmpeg.exe` with Rook, make release packaging fail closed for unacceptable payloads, and make runtime sidecar extraction prefer the bundled binary.

**Architecture:** Keep FFmpeg as an external subprocess dependency. Add a machine-readable third-party FFmpeg payload manifest, a release validation script that checks provenance/license flags/checksums/compliance files plus a functional command smoke, installer packaging lines for the binary and compliance files, and a runtime resolver source for the installed bundled path. Do not link FFmpeg libraries, do not download FFmpeg during install, and do not change provider or GH NLE behavior.

**Tech Stack:** C# managed companion (`src/Rook`), xUnit tests (`src/Rook.Tests`), PowerShell release guards (`scripts/tests`), Inno Setup installer (`installer/RookSetup.iss`), Markdown docs.

---

## Manual Payload Prerequisite

Task 3 requires a human release owner to provide the vetted third-party payload
inputs before an implementation agent runs the mechanical ingestion steps.
Do not assign FFmpeg build selection, license interpretation, or provenance
approval to a fresh implementation subagent.

Before Task 3 starts, the release owner must provide:

- absolute path to the vetted LGPL-only Windows `ffmpeg.exe`;
- exact FFmpeg version string;
- exact binary URL or internal artifact URL;
- build source identity, vendor, or reproducible build description;
- exact corresponding source URL;
- exact corresponding source archive filename or artifact identity;
- SHA-256 of the exact corresponding source archive;
- absolute path to the FFmpeg license text for the vetted payload.

The implementation agent may then copy files, compute the binary checksum, read
`ffmpeg.exe -version`, write metadata, and run validation. If any prerequisite
input is missing, stop Task 3 and ask the release owner for the missing value.

## File Map

- Create `third_party/ffmpeg/README.md`: explains the bundled FFmpeg policy, exact provenance requirements, and update procedure.
- Create `third_party/ffmpeg/ffmpeg-provenance.json`: machine-readable metadata for release validation.
- Create `third_party/ffmpeg/LICENSE.FFmpeg.txt`: FFmpeg license text or pointer text for the exact bundled package.
- Create `third_party/ffmpeg/NOTICE.FFmpeg.txt`: Rook-visible attribution and notice text.
- Create `third_party/ffmpeg/SOURCE.FFmpeg.txt`: exact corresponding source URL/archive/checksum/build notes.
- Add `third_party/ffmpeg/ffmpeg.exe`: the vetted LGPL-only Windows binary.
- Add `third_party/ffmpeg/fixtures/sidecar-smoke.mp4`: tiny MP4 fixture used only by the release validation smoke.
- Create `scripts/validate-ffmpeg-bundle.ps1`: fail-closed release validation for metadata, checksums, configure flags, compliance files, installer inclusion, and functional extraction smoke.
- Create `scripts/tests/ffmpeg-bundle-validation.tests.ps1`: policy tests for the validation script using a temp payload and fake `ffmpeg.exe`.
- Modify `scripts/tests/release-installer-guards.tests.ps1`: invoke or source the new FFmpeg validation guard and assert installer packaging lines.
- Modify `installer/RookSetup.iss`: package `ffmpeg.exe` and compliance files with the plugin component.
- Modify `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`: add `Bundled` to `FfmpegBinaryResolutionSource`.
- Modify `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`: add bundled path input and bundled-first resolution.
- Modify `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`: pass the installed bundled path provider into resolution.
- Modify `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`: pass the installed bundled path provider into resolution.
- Modify `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`: cover bundled-first and dev fallback behavior.
- Modify `docs/rook_docs/video-thumbnail-roadmap.md`: mark Slice 6 complete once implementation is done.
- Modify `docs/rook_docs/work-queue.md`: record implementation and verification.

## Policy Decisions Locked by This Plan

- Release packaging must use the bundled payload, not PATH.
- Release validation must reject `--enable-gpl`, `--enable-nonfree`, missing configure output, checksum mismatch, unknown provenance, missing compliance files, and functional smoke failure.
- Runtime production resolution prefers bundled installed FFmpeg.
- Configured/PATH fallback remains for development/test convenience only.
- FFmpeg is invoked as `ffmpeg.exe` subprocess only.

## Task 1: Add FFmpeg Payload Metadata and Compliance Scaffold

**Files:**
- Create: `third_party/ffmpeg/README.md`
- Create: `third_party/ffmpeg/ffmpeg-provenance.json`
- Create: `third_party/ffmpeg/LICENSE.FFmpeg.txt`
- Create: `third_party/ffmpeg/NOTICE.FFmpeg.txt`
- Create: `third_party/ffmpeg/SOURCE.FFmpeg.txt`

- [ ] **Step 1: Create the third-party FFmpeg directory**

Run:

```powershell
New-Item -ItemType Directory -Force third_party\ffmpeg
```

Expected: directory exists.

- [ ] **Step 2: Add `third_party/ffmpeg/README.md`**

Create:

```markdown
# Bundled FFmpeg Payload

Rook bundles a vetted LGPL-only Windows `ffmpeg.exe` so generated-video
`poster`, `start_frame`, and `end_frame` sidecars work without user setup.

This payload is third-party software. Rook invokes `ffmpeg.exe` as a subprocess
and does not link FFmpeg libraries.

Release packaging must run `scripts\validate-ffmpeg-bundle.ps1` before building
the installer. The release guard must fail closed if:

- `ffmpeg-provenance.json` is missing or malformed;
- `ffmpeg.exe` is missing;
- the binary checksum does not match metadata;
- `ffmpeg.exe -version` cannot be read;
- the configure line is missing;
- the configure line contains `--enable-gpl`;
- the configure line contains `--enable-nonfree`;
- compliance files are missing;
- the bundled binary cannot extract poster, first-frame, and last-frame JPEGs
  from the smoke fixture.

Development builds may use PATH/configured FFmpeg. Release validation may not.
```

- [ ] **Step 3: Add non-release-valid compliance scaffold files**

Create `third_party/ffmpeg/LICENSE.FFmpeg.txt`:

```text
FFmpeg license text for the vetted bundled FFmpeg build belongs here.

This scaffold is not release-valid. The release guard must fail until this
file is replaced with the license text for the exact bundled payload.
```

Create `third_party/ffmpeg/NOTICE.FFmpeg.txt`:

```text
Rook includes FFmpeg for video thumbnail and frame sidecar extraction.
FFmpeg is third-party software. Rook invokes ffmpeg.exe as a subprocess.

This scaffold is not release-valid. Replace it with attribution text for the
exact bundled FFmpeg payload before release packaging.
```

Create `third_party/ffmpeg/SOURCE.FFmpeg.txt`:

```text
Exact corresponding FFmpeg source archive URL, source archive identity, source
checksum, binary source/provenance, configure line, and build notes belong here.

This scaffold is not release-valid. The release guard must fail until exact
source-compliance details are provided for the bundled payload.
```

- [ ] **Step 4: Add initial `ffmpeg-provenance.json` scaffold**

Create:

```json
{
  "name": "FFmpeg",
  "version": "",
  "license": "LGPL-only",
  "binary_path": "third_party/ffmpeg/ffmpeg.exe",
  "binary_sha256": "",
  "binary_url": "",
  "build_source": "",
  "source_url": "",
  "source_archive": "",
  "source_sha256": "",
  "configure_line": "",
  "validated_command_surfaces": [
    "poster",
    "first_frame",
    "last_frame"
  ],
  "verified_at": "",
  "verified_by": "",
  "notes": "Release validation must fail until all fields are populated for a vetted LGPL-only Windows FFmpeg payload."
}
```

- [ ] **Step 5: Commit the scaffold**

Run:

```powershell
git add third_party\ffmpeg\README.md third_party\ffmpeg\ffmpeg-provenance.json third_party\ffmpeg\LICENSE.FFmpeg.txt third_party\ffmpeg\NOTICE.FFmpeg.txt third_party\ffmpeg\SOURCE.FFmpeg.txt
git commit -m "Add FFmpeg bundle metadata scaffold"
```

Expected: commit succeeds. Do not add unrelated proto-skills files.

## Task 2: Build Fail-Closed FFmpeg Bundle Validation Script

**Files:**
- Create: `scripts/validate-ffmpeg-bundle.ps1`
- Create: `scripts/tests/ffmpeg-bundle-validation.tests.ps1`

- [ ] **Step 1: Create validation script skeleton**

Create `scripts/validate-ffmpeg-bundle.ps1`:

```powershell
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PayloadDir = '',
    [string]$InstallerScriptPath = '',
    [switch]$SkipFunctionalSmoke
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($PayloadDir)) {
    $PayloadDir = Join-Path $RepoRoot 'third_party\ffmpeg'
}
if ([string]::IsNullOrWhiteSpace($InstallerScriptPath)) {
    $InstallerScriptPath = Join-Path $RepoRoot 'installer\RookSetup.iss'
}

$ProvenancePath = Join-Path $PayloadDir 'ffmpeg-provenance.json'
$SmokeFixture = Join-Path $PayloadDir 'fixtures\sidecar-smoke.mp4'
$SmokeOutput = Join-Path ([System.IO.Path]::GetTempPath()) ('rook-ffmpeg-smoke-' + [Guid]::NewGuid().ToString('N'))

function Fail {
    param([string]$Message)
    throw "FFmpeg bundle validation failed: $Message"
}

function Require-File {
    param([string]$Path, [string]$Label)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "$Label is missing: $Path"
    }
}

function Read-Provenance {
    Require-File $ProvenancePath 'ffmpeg-provenance.json'
    try {
        return Get-Content -LiteralPath $ProvenancePath -Raw | ConvertFrom-Json
    } catch {
        Fail "ffmpeg-provenance.json is malformed JSON: $($_.Exception.Message)"
    }
}

function Require-TextField {
    param($Object, [string]$Name)
    $value = $Object.$Name
    if ($null -eq $value -or [string]::IsNullOrWhiteSpace([string]$value)) {
        Fail "required provenance field '$Name' is missing or empty"
    }
    return [string]$value
}

function Get-Sha256 {
    param([string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToUpperInvariant()
}

function Assert-NoForbiddenFlags {
    param([string]$ConfigureLine)
    if ($ConfigureLine -match '(^|\s)--enable-gpl(\s|$)') {
        Fail 'configure line contains --enable-gpl'
    }
    if ($ConfigureLine -match '(^|\s)--enable-nonfree(\s|$)') {
        Fail 'configure line contains --enable-nonfree'
    }
}

function Normalize-ConfigureLine {
    param([string]$Line)
    return (($Line.Trim()) -replace '\s+', ' ')
}

function Get-RuntimeConfigureLine {
    param([string]$FfmpegPath)
    $output = & $FfmpegPath -version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail "ffmpeg -version exited with code $LASTEXITCODE"
    }
    $line = $output | Where-Object { $_ -like 'configuration:*' } | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($line)) {
        Fail 'ffmpeg -version did not report a configuration line'
    }
    return [string]$line
}

function Run-FfmpegSmoke {
    param([string]$FfmpegPath)

    Require-File $SmokeFixture 'functional smoke MP4 fixture'
    New-Item -ItemType Directory -Force -Path $SmokeOutput | Out-Null

    $poster = Join-Path $SmokeOutput 'poster.jpg'
    $first = Join-Path $SmokeOutput 'first.jpg'
    $last = Join-Path $SmokeOutput 'last.jpg'

    & $FfmpegPath -hide_banner -y -ss '00:00:00.100' -i $SmokeFixture -frames:v 1 -q:v 2 $poster 2>&1 | Out-String | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "poster smoke extraction failed with exit code $LASTEXITCODE" }

    & $FfmpegPath -hide_banner -y -i $SmokeFixture -map '0:v:0' -an -vf 'select=eq(n\,0)' -vsync 0 -frames:v 1 -q:v 2 $first 2>&1 | Out-String | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "first-frame smoke extraction failed with exit code $LASTEXITCODE" }

    & $FfmpegPath -hide_banner -y -i $SmokeFixture -map '0:v:0' -an -vf 'reverse,select=eq(n\,0)' -vsync 0 -frames:v 1 -q:v 2 $last 2>&1 | Out-String | Out-Null
    if ($LASTEXITCODE -ne 0) { Fail "last-frame smoke extraction failed with exit code $LASTEXITCODE" }

    foreach ($image in @($poster, $first, $last)) {
        Require-File $image 'smoke output JPEG'
        if ((Get-Item -LiteralPath $image).Length -le 0) {
            Fail "smoke output JPEG is empty: $image"
        }
        Add-Type -AssemblyName System.Drawing
        try {
            $img = [System.Drawing.Image]::FromFile($image)
            try {
                if ($img.Width -le 0 -or $img.Height -le 0) {
                    Fail "smoke output JPEG has invalid dimensions: $image"
                }
            } finally {
                $img.Dispose()
            }
        } catch {
            Fail "smoke output JPEG is unreadable: $image ($($_.Exception.Message))"
        }
    }
}

$provenance = Read-Provenance
$required = @(
    'name',
    'version',
    'license',
    'binary_path',
    'binary_sha256',
    'source_url',
    'source_archive',
    'source_sha256',
    'configure_line',
    'verified_at',
    'verified_by'
)
foreach ($field in $required) {
    [void](Require-TextField $provenance $field)
}

if ([string]$provenance.license -ne 'LGPL-only') {
    Fail "license must be LGPL-only; actual: $($provenance.license)"
}

$surfaces = @($provenance.validated_command_surfaces)
foreach ($surface in @('poster', 'first_frame', 'last_frame')) {
    if ($surfaces -notcontains $surface) {
        Fail "validated_command_surfaces must include '$surface'"
    }
}

$ffmpegPath = Join-Path $RepoRoot ([string]$provenance.binary_path)
Require-File $ffmpegPath 'ffmpeg.exe'

$actualHash = Get-Sha256 $ffmpegPath
$expectedHash = ([string]$provenance.binary_sha256).ToUpperInvariant()
if ($actualHash -ne $expectedHash) {
    Fail "ffmpeg.exe checksum mismatch. Expected $expectedHash, actual $actualHash"
}

$metadataConfigure = [string]$provenance.configure_line
Assert-NoForbiddenFlags $metadataConfigure
$runtimeConfigure = Get-RuntimeConfigureLine $ffmpegPath
Assert-NoForbiddenFlags $runtimeConfigure
if ((Normalize-ConfigureLine $metadataConfigure) -ne (Normalize-ConfigureLine $runtimeConfigure)) {
    Fail 'provenance configure_line does not match ffmpeg -version configuration output'
}

foreach ($file in @('LICENSE.FFmpeg.txt', 'NOTICE.FFmpeg.txt', 'SOURCE.FFmpeg.txt')) {
    $path = Join-Path $PayloadDir $file
    Require-File $path $file
    $text = Get-Content -LiteralPath $path -Raw
    if ($text -match 'scaffold|not release-valid') {
        Fail "$file still contains scaffold/non-release-valid text"
    }
}

if (-not $SkipFunctionalSmoke) {
    try {
        Run-FfmpegSmoke $ffmpegPath
    } finally {
        if (Test-Path -LiteralPath $SmokeOutput) {
            Remove-Item -LiteralPath $SmokeOutput -Recurse -Force
        }
    }
}

$installer = Get-Content -LiteralPath $InstallerScriptPath -Raw
if ($installer -notlike '*third_party\ffmpeg*') {
    Fail 'installer script does not include third_party\ffmpeg payload'
}

Write-Host "FFmpeg bundle validation passed: $($provenance.version) $actualHash"
```

- [ ] **Step 2: Add validation policy tests**

Create `scripts/tests/ffmpeg-bundle-validation.tests.ps1`:

```powershell
$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$ValidationScript = Join-Path $RepoRoot 'scripts\validate-ffmpeg-bundle.ps1'

function Assert-True {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Assert-FailsWith {
    param([scriptblock]$Action, [string]$Expected)
    try {
        & $Action
    } catch {
        $message = $_.Exception.Message
        Assert-True -Condition ($message -like "*$Expected*") -Message "Expected failure containing '$Expected', actual: $message"
        return
    }
    throw "Expected failure containing '$Expected', but command succeeded."
}

function New-FakeFfmpeg {
    param([string]$Path)

    $source = @'
using System;
using System.Drawing;
using System.Drawing.Imaging;

internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "-version")
        {
            Console.WriteLine("ffmpeg version test-lgpl");
            Console.WriteLine("configuration: --disable-gpl --disable-nonfree");
            return 0;
        }

        if (Environment.GetEnvironmentVariable("ROOK_FAKE_FFMPEG_FAIL") == "1")
            return 2;

        if (args.Length == 0)
            return 3;

        var output = args[args.Length - 1];
        using (var image = new Bitmap(2, 2))
        {
            image.SetPixel(0, 0, Color.Red);
            image.SetPixel(1, 0, Color.Green);
            image.SetPixel(0, 1, Color.Blue);
            image.SetPixel(1, 1, Color.White);
            image.Save(output, ImageFormat.Jpeg);
        }

        return 0;
    }
}
'@

    Add-Type `
        -TypeDefinition $source `
        -OutputAssembly $Path `
        -OutputType ConsoleApplication `
        -ReferencedAssemblies 'System.Drawing.dll'
}

function New-TestPayload {
    param([string]$Name)

    $root = Join-Path ([System.IO.Path]::GetTempPath()) ('rook-ffmpeg-validation-' + $Name + '-' + [Guid]::NewGuid().ToString('N'))
    $payload = Join-Path $root 'third_party\ffmpeg'
    $fixtures = Join-Path $payload 'fixtures'
    New-Item -ItemType Directory -Force -Path $fixtures | Out-Null

    $ffmpeg = Join-Path $payload 'ffmpeg.exe'
    New-FakeFfmpeg $ffmpeg
    Set-Content -Path (Join-Path $fixtures 'sidecar-smoke.mp4') -Value 'fake mp4 fixture' -Encoding ASCII
    Set-Content -Path (Join-Path $root 'RookSetup.iss') -Value 'Source: "third_party\ffmpeg\ffmpeg.exe"' -Encoding ASCII
    Set-Content -Path (Join-Path $payload 'LICENSE.FFmpeg.txt') -Value 'LGPL license text for test payload' -Encoding UTF8
    Set-Content -Path (Join-Path $payload 'NOTICE.FFmpeg.txt') -Value 'FFmpeg notice text for test payload' -Encoding UTF8
    Set-Content -Path (Join-Path $payload 'SOURCE.FFmpeg.txt') -Value 'FFmpeg source text for test payload' -Encoding UTF8

    $hash = (Get-FileHash -LiteralPath $ffmpeg -Algorithm SHA256).Hash.ToUpperInvariant()
    $provenance = [ordered]@{
        name = 'FFmpeg'
        version = 'test-lgpl'
        license = 'LGPL-only'
        binary_path = 'third_party/ffmpeg/ffmpeg.exe'
        binary_sha256 = $hash
        binary_url = 'https://example.invalid/ffmpeg.exe'
        build_source = 'test fake build'
        source_url = 'https://example.invalid/ffmpeg-source.tar.xz'
        source_archive = 'ffmpeg-source.tar.xz'
        source_sha256 = ('A' * 64)
        configure_line = 'configuration: --disable-gpl --disable-nonfree'
        validated_command_surfaces = @('poster', 'first_frame', 'last_frame')
        verified_at = '2026-05-12T00:00:00Z'
        verified_by = 'test'
        notes = 'test payload'
    }
    $provenance | ConvertTo-Json -Depth 4 | Set-Content -Path (Join-Path $payload 'ffmpeg-provenance.json') -Encoding UTF8

    return [pscustomobject]@{
        Root = $root
        Payload = $payload
        Installer = Join-Path $root 'RookSetup.iss'
        Provenance = Join-Path $payload 'ffmpeg-provenance.json'
        Ffmpeg = $ffmpeg
    }
}

function Invoke-Validation {
    param($Payload)
    $output = & powershell -ExecutionPolicy Bypass -File $ValidationScript -RepoRoot $Payload.Root -PayloadDir $Payload.Payload -InstallerScriptPath $Payload.Installer 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ($output -join "`n")
    }
}

function Set-ProvenanceField {
    param($Payload, [string]$Field, $Value)
    $json = Get-Content -LiteralPath $Payload.Provenance -Raw | ConvertFrom-Json
    $json.$Field = $Value
    $json | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $Payload.Provenance -Encoding UTF8
}

$valid = New-TestPayload 'valid'
try {
    Invoke-Validation $valid
} finally {
    Remove-Item -LiteralPath $valid.Root -Recurse -Force
}

$gpl = New-TestPayload 'gpl'
try {
    Set-ProvenanceField $gpl 'configure_line' 'configuration: --enable-gpl'
    Assert-FailsWith { Invoke-Validation $gpl } '--enable-gpl'
} finally {
    Remove-Item -LiteralPath $gpl.Root -Recurse -Force
}

$nonfree = New-TestPayload 'nonfree'
try {
    Set-ProvenanceField $nonfree 'configure_line' 'configuration: --enable-nonfree'
    Assert-FailsWith { Invoke-Validation $nonfree } '--enable-nonfree'
} finally {
    Remove-Item -LiteralPath $nonfree.Root -Recurse -Force
}

$missingConfigure = New-TestPayload 'missing-configure'
try {
    Set-ProvenanceField $missingConfigure 'configure_line' ''
    Assert-FailsWith { Invoke-Validation $missingConfigure } "configure_line"
} finally {
    Remove-Item -LiteralPath $missingConfigure.Root -Recurse -Force
}

$checksum = New-TestPayload 'checksum'
try {
    Set-ProvenanceField $checksum 'binary_sha256' ('B' * 64)
    Assert-FailsWith { Invoke-Validation $checksum } 'checksum mismatch'
} finally {
    Remove-Item -LiteralPath $checksum.Root -Recurse -Force
}

$staleConfigure = New-TestPayload 'stale-configure'
try {
    Set-ProvenanceField $staleConfigure 'configure_line' 'configuration: --disable-gpl --disable-nonfree --enable-libx264'
    Assert-FailsWith { Invoke-Validation $staleConfigure } 'configure_line does not match'
} finally {
    Remove-Item -LiteralPath $staleConfigure.Root -Recurse -Force
}

$missingCompliance = New-TestPayload 'missing-compliance'
try {
    Remove-Item -LiteralPath (Join-Path $missingCompliance.Payload 'NOTICE.FFmpeg.txt') -Force
    Assert-FailsWith { Invoke-Validation $missingCompliance } 'NOTICE.FFmpeg.txt is missing'
} finally {
    Remove-Item -LiteralPath $missingCompliance.Root -Recurse -Force
}

$smokeFailure = New-TestPayload 'smoke-failure'
try {
    $env:ROOK_FAKE_FFMPEG_FAIL = '1'
    Assert-FailsWith { Invoke-Validation $smokeFailure } 'poster smoke extraction failed'
} finally {
    Remove-Item Env:\ROOK_FAKE_FFMPEG_FAIL -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $smokeFailure.Root -Recurse -Force
}

Write-Host 'FFmpeg bundle validation policy tests passed.'
```

- [ ] **Step 3: Run policy tests and verify they pass**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tests\ffmpeg-bundle-validation.tests.ps1
```

Expected: PASS and prints `FFmpeg bundle validation policy tests passed.`

- [ ] **Step 4: Run script and verify scaffold fails closed**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1
```

Expected: FAIL with a message about missing/empty provenance fields or missing `ffmpeg.exe`. This failure is correct until the real payload is added.

- [ ] **Step 5: Commit validation script and policy tests**

Run:

```powershell
git add scripts\validate-ffmpeg-bundle.ps1 scripts\tests\ffmpeg-bundle-validation.tests.ps1
git commit -m "Add FFmpeg bundle validation guard"
```

Expected: commit succeeds.

## Task 3: Ingest Human-Approved LGPL FFmpeg Binary and Smoke Fixture

**Files:**
- Add: `third_party/ffmpeg/ffmpeg.exe`
- Add: `third_party/ffmpeg/fixtures/sidecar-smoke.mp4`
- Modify: `third_party/ffmpeg/ffmpeg-provenance.json`
- Modify: `third_party/ffmpeg/LICENSE.FFmpeg.txt`
- Modify: `third_party/ffmpeg/NOTICE.FFmpeg.txt`
- Modify: `third_party/ffmpeg/SOURCE.FFmpeg.txt`

- [ ] **Step 1: Confirm release-owner inputs are available**

This task is mechanical ingestion only. A release owner must already have
selected and approved the payload described in `Manual Payload Prerequisite`.

Create a local, uncommitted Task 3 input file at
`$env:TEMP\rook-ffmpeg-payload-input.json`:

```powershell
$PayloadInputPath = Join-Path $env:TEMP 'rook-ffmpeg-payload-input.json'
@{
    ffmpegExePath = ''
    ffmpegVersion = ''
    binaryUrl = ''
    buildSource = ''
    sourceUrl = ''
    sourceArchive = ''
    sourceSha256 = ''
    licenseTextPath = ''
} | ConvertTo-Json -Depth 3 | Set-Content -Path $PayloadInputPath -Encoding UTF8
```

The release owner must replace every empty value. Then validate the input:

```powershell
$PayloadInputPath = Join-Path $env:TEMP 'rook-ffmpeg-payload-input.json'
$PayloadInput = Get-Content -LiteralPath $PayloadInputPath -Raw | ConvertFrom-Json
$RequiredPayloadFields = @(
    'ffmpegExePath',
    'ffmpegVersion',
    'binaryUrl',
    'buildSource',
    'sourceUrl',
    'sourceArchive',
    'sourceSha256',
    'licenseTextPath'
)
foreach ($field in $RequiredPayloadFields) {
    if ([string]::IsNullOrWhiteSpace([string]$PayloadInput.$field)) {
        throw "Task 3 release-owner input is missing: $field"
    }
}
if (-not (Test-Path -LiteralPath ([string]$PayloadInput.ffmpegExePath) -PathType Leaf)) {
    throw "ffmpegExePath does not exist: $($PayloadInput.ffmpegExePath)"
}
if (-not (Test-Path -LiteralPath ([string]$PayloadInput.licenseTextPath) -PathType Leaf)) {
    throw "licenseTextPath does not exist: $($PayloadInput.licenseTextPath)"
}
```

Expected: validation succeeds only after human-approved payload inputs are
provided. If this step fails, stop and ask the release owner for the missing
input.

- [ ] **Step 2: Copy `ffmpeg.exe` into the payload**

Run:

```powershell
$PayloadInputPath = Join-Path $env:TEMP 'rook-ffmpeg-payload-input.json'
$PayloadInput = Get-Content -LiteralPath $PayloadInputPath -Raw | ConvertFrom-Json
Copy-Item -LiteralPath ([string]$PayloadInput.ffmpegExePath) -Destination third_party\ffmpeg\ffmpeg.exe -Force
Get-FileHash third_party\ffmpeg\ffmpeg.exe -Algorithm SHA256
third_party\ffmpeg\ffmpeg.exe -version
```

Expected:
- `ffmpeg.exe` exists.
- SHA-256 prints.
- `-version` prints a `configuration:` line.
- no `--enable-gpl` and no `--enable-nonfree` appear.

- [ ] **Step 3: Add tiny smoke MP4 fixture**

Preferred: create a tiny 2-3 frame H.264/AAC-free MP4 once using the vetted binary, then commit the fixture.

Run:

```powershell
New-Item -ItemType Directory -Force third_party\ffmpeg\fixtures
third_party\ffmpeg\ffmpeg.exe -hide_banner -y -f lavfi -i testsrc=size=64x64:rate=1:duration=3 -pix_fmt yuv420p -an third_party\ffmpeg\fixtures\sidecar-smoke.mp4
```

Expected: `third_party\ffmpeg\fixtures\sidecar-smoke.mp4` exists and is small.

- [ ] **Step 4: Populate provenance and compliance files**

Generate `ffmpeg-provenance.json` from explicit release variables:

```powershell
$PayloadInputPath = Join-Path $env:TEMP 'rook-ffmpeg-payload-input.json'
$PayloadInput = Get-Content -LiteralPath $PayloadInputPath -Raw | ConvertFrom-Json

$FfmpegVersion = [string]$PayloadInput.ffmpegVersion
$BinaryUrl = [string]$PayloadInput.binaryUrl
$BuildSource = [string]$PayloadInput.buildSource
$SourceUrl = [string]$PayloadInput.sourceUrl
$SourceArchive = [string]$PayloadInput.sourceArchive
$SourceSha256 = [string]$PayloadInput.sourceSha256

foreach ($name in 'FfmpegVersion','BinaryUrl','BuildSource','SourceUrl','SourceArchive','SourceSha256') {
    if ([string]::IsNullOrWhiteSpace((Get-Variable -Name $name).Value)) {
        throw "Set `$$name before writing ffmpeg-provenance.json."
    }
}

$BinarySha256 = (Get-FileHash third_party\ffmpeg\ffmpeg.exe -Algorithm SHA256).Hash.ToUpperInvariant()
$VersionOutput = & third_party\ffmpeg\ffmpeg.exe -version 2>&1
$ConfigureLine = ($VersionOutput | Where-Object { $_ -like 'configuration:*' } | Select-Object -First 1)
if ([string]::IsNullOrWhiteSpace($ConfigureLine)) {
    throw 'ffmpeg -version did not print a configuration line.'
}

$Provenance = [ordered]@{
    name = 'FFmpeg'
    version = $FfmpegVersion
    license = 'LGPL-only'
    binary_path = 'third_party/ffmpeg/ffmpeg.exe'
    binary_sha256 = $BinarySha256
    binary_url = $BinaryUrl
    build_source = $BuildSource
    source_url = $SourceUrl
    source_archive = $SourceArchive
    source_sha256 = $SourceSha256
    configure_line = [string]$ConfigureLine
    validated_command_surfaces = @('poster', 'first_frame', 'last_frame')
    verified_at = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
    verified_by = 'Rook release validation'
    notes = 'Bundled for Rook video sidecar extraction via ffmpeg.exe subprocess only.'
}

$Provenance |
    ConvertTo-Json -Depth 4 |
    Set-Content -Path third_party\ffmpeg\ffmpeg-provenance.json -Encoding UTF8
```

Write the compliance files from the vetted payload details:

```powershell
$PayloadInputPath = Join-Path $env:TEMP 'rook-ffmpeg-payload-input.json'
$PayloadInput = Get-Content -LiteralPath $PayloadInputPath -Raw | ConvertFrom-Json
$LicenseTextPath = [string]$PayloadInput.licenseTextPath
if (-not (Test-Path -LiteralPath $LicenseTextPath -PathType Leaf)) {
    throw "License text path does not exist: $LicenseTextPath"
}

Copy-Item -LiteralPath $LicenseTextPath -Destination third_party\ffmpeg\LICENSE.FFmpeg.txt -Force

@"
Rook includes FFmpeg for generated-video thumbnail and frame sidecar extraction.
FFmpeg is third-party software. Rook invokes ffmpeg.exe as a subprocess and does
not link FFmpeg libraries.

Bundled FFmpeg version: $FfmpegVersion
Bundled binary provenance: $BinaryUrl
License policy for Rook release packaging: LGPL-only; release validation rejects
GPL-enabled and nonfree FFmpeg builds.
"@ | Set-Content -Path third_party\ffmpeg\NOTICE.FFmpeg.txt -Encoding UTF8

@"
Exact corresponding FFmpeg source for the bundled Rook payload:

Version: $FfmpegVersion
Binary provenance: $BinaryUrl
Build source: $BuildSource
Source URL: $SourceUrl
Source archive: $SourceArchive
Source SHA-256: $SourceSha256

Configure line:
$ConfigureLine

Rook uses this payload only as an ffmpeg.exe subprocess for generated-video
poster, start_frame, and end_frame sidecar extraction.
"@ | Set-Content -Path third_party\ffmpeg\SOURCE.FFmpeg.txt -Encoding UTF8

$ScaffoldMatches = Select-String -Path third_party\ffmpeg\LICENSE.FFmpeg.txt,third_party\ffmpeg\NOTICE.FFmpeg.txt,third_party\ffmpeg\SOURCE.FFmpeg.txt -Pattern 'scaffold|not release-valid'
if ($ScaffoldMatches) {
    throw 'Compliance files still contain scaffold/non-release-valid text.'
}
```

- [ ] **Step 5: Run bundle validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1
```

Expected: likely FAIL until the installer includes `third_party\ffmpeg`. If it fails only for installer inclusion, proceed to Task 4. Any license, checksum, configure, compliance, or smoke failure must be fixed in this task before continuing.

- [ ] **Step 6: Commit payload**

Run:

```powershell
git add third_party\ffmpeg
git commit -m "Add vetted LGPL FFmpeg payload"
```

Expected: commit succeeds.

## Task 4: Package FFmpeg in the Installer and Release Guards

**Files:**
- Modify: `installer/RookSetup.iss`
- Modify: `scripts/tests/release-installer-guards.tests.ps1`

- [ ] **Step 1: Add installer source define**

In `installer/RookSetup.iss`, near the other source path defines, add:

```iss
#define FfmpegDir   RepoRoot + "\third_party\ffmpeg"
```

- [ ] **Step 2: Add installer file entries**

In `[Files]`, after the companion runtime entries, add:

```iss
; Bundled LGPL-only FFmpeg for video sidecar extraction
Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\ffmpeg-provenance.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\LICENSE.FFmpeg.txt"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\NOTICE.FFmpeg.txt"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\SOURCE.FFmpeg.txt"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
```

Do not use `skipifsourcedoesntexist` for `ffmpeg.exe`.

- [ ] **Step 3: Update release installer guard tests**

In `scripts/tests/release-installer-guards.tests.ps1`, add:

```powershell
$FfmpegValidationScript = Join-Path $RepoRoot 'scripts\validate-ffmpeg-bundle.ps1'
```

Add function:

```powershell
function Test-InstallerPackagesBundledFfmpegPayload {
    $content = Get-Content -Path $InstallerScript -Raw

    Assert-Contains -Text $content -Expected '#define FfmpegDir   RepoRoot + "\third_party\ffmpeg"' -Message 'Installer must define the bundled FFmpeg payload directory.'
    Assert-Contains -Text $content -Expected '{#FfmpegDir}\ffmpeg.exe' -Message 'Installer must package bundled ffmpeg.exe.'
    Assert-Contains -Text $content -Expected '{#FfmpegDir}\ffmpeg-provenance.json' -Message 'Installer must package FFmpeg provenance metadata.'
    Assert-Contains -Text $content -Expected '{#FfmpegDir}\LICENSE.FFmpeg.txt' -Message 'Installer must package FFmpeg license text.'
    Assert-Contains -Text $content -Expected '{#FfmpegDir}\NOTICE.FFmpeg.txt' -Message 'Installer must package FFmpeg notice text.'
    Assert-Contains -Text $content -Expected '{#FfmpegDir}\SOURCE.FFmpeg.txt' -Message 'Installer must package FFmpeg source-compliance text.'

    $ffmpegLine = (Get-Content -Path $InstallerScript | Where-Object { $_ -like 'Source: "{#FfmpegDir}\ffmpeg.exe"*' }) -join "`n"
    Assert-NotContains -Text $ffmpegLine -Unexpected 'skipifsourcedoesntexist' -Message 'Release installer must fail packaging when bundled ffmpeg.exe is missing.'
}

function Test-FfmpegBundleValidationPasses {
    Assert-True -Condition (Test-Path $FfmpegValidationScript) -Message "FFmpeg validation script is missing: $FfmpegValidationScript"
    & powershell -ExecutionPolicy Bypass -File $FfmpegValidationScript
    if ($LASTEXITCODE -ne 0) {
        throw "FFmpeg bundle validation failed with exit code $LASTEXITCODE"
    }
}
```

Before the final `Write-Host`, call:

```powershell
Test-InstallerPackagesBundledFfmpegPayload
Test-FfmpegBundleValidationPasses
```

- [ ] **Step 4: Run guard tests**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: `Release installer guard tests passed.`

- [ ] **Step 5: Commit installer and release guard changes**

Run:

```powershell
git add installer\RookSetup.iss scripts\tests\release-installer-guards.tests.ps1
git commit -m "Package bundled FFmpeg in release installer"
```

Expected: commit succeeds.

## Task 5: Prefer Bundled FFmpeg at Runtime

**Files:**
- Modify: `src/Rook/Services/Vision/Video/Extraction/VideoExtractionSpikeModels.cs`
- Modify: `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`
- Modify: `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`
- Modify: `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`

- [ ] **Step 1: Add failing resolver tests**

Append tests to `FfmpegBinaryResolverTests.cs`:

```csharp
[Fact]
public void Resolve_BundledExistingPath_WinsOverConfiguredAndPathLookup()
{
    var bundledPath = TouchExe(Path.Combine(_root, "bundled", "ffmpeg.exe"));
    var configuredPath = TouchExe(Path.Combine(_root, "configured", "ffmpeg.exe"));
    var pathExe = TouchExe(Path.Combine(_root, "path", "ffmpeg.exe"));

    var result = FfmpegBinaryResolver.Resolve(
        bundledPath: bundledPath,
        configuredPath: configuredPath,
        pathEnvironment: Path.GetDirectoryName(pathExe));

    Assert.True(result.Success);
    Assert.Equal(bundledPath, result.Path);
    Assert.Equal(FfmpegBinaryResolutionSource.Bundled, result.Source);
    Assert.Null(result.ErrorCode);
}

[Fact]
public void Resolve_BundledMissingPath_FallsBackToConfiguredForDevConvenience()
{
    var bundledPath = Path.Combine(_root, "bundled", "missing-ffmpeg.exe");
    var configuredPath = TouchExe(Path.Combine(_root, "configured", "ffmpeg.exe"));

    var result = FfmpegBinaryResolver.Resolve(
        bundledPath: bundledPath,
        configuredPath: configuredPath,
        pathEnvironment: null);

    Assert.True(result.Success);
    Assert.Equal(configuredPath, result.Path);
    Assert.Equal(FfmpegBinaryResolutionSource.ConfiguredPath, result.Source);
}
```

- [ ] **Step 2: Run resolver tests and verify failure**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests"
```

Expected: FAIL because `bundledPath` parameter/source enum do not exist.

- [ ] **Step 3: Add bundled resolution source**

In `VideoExtractionSpikeModels.cs`, change:

```csharp
internal enum FfmpegBinaryResolutionSource
{
    ConfiguredPath,
    PathLookup,
}
```

to:

```csharp
internal enum FfmpegBinaryResolutionSource
{
    Bundled,
    ConfiguredPath,
    PathLookup,
}
```

- [ ] **Step 4: Update `FfmpegBinaryResolver.Resolve`**

Replace the method signature and first block in `FfmpegBinaryResolver.cs` with:

```csharp
public static FfmpegBinaryResolution Resolve(
    string? bundledPath = null,
    string? configuredPath = null,
    string? pathEnvironment = null)
{
    if (!string.IsNullOrWhiteSpace(bundledPath))
    {
        var full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(bundledPath));
        if (File.Exists(full))
            return FfmpegBinaryResolution.Found(full, FfmpegBinaryResolutionSource.Bundled);
    }

    if (!string.IsNullOrWhiteSpace(configuredPath))
    {
        var full = Path.GetFullPath(Environment.ExpandEnvironmentVariables(configuredPath));
        return File.Exists(full)
            ? FfmpegBinaryResolution.Found(full, FfmpegBinaryResolutionSource.ConfiguredPath)
            : FfmpegBinaryResolution.Failed(
                FfmpegBinaryResolutionError.ConfiguredPathMissing,
                $"Configured ffmpeg path does not exist: {full}");
    }

    foreach (var dir in SplitPath(pathEnvironment ?? Environment.GetEnvironmentVariable("PATH")))
    {
        var candidate = Path.Combine(dir, BinaryName);
        if (File.Exists(candidate))
            return FfmpegBinaryResolution.Found(
                Path.GetFullPath(candidate),
                FfmpegBinaryResolutionSource.PathLookup);
    }

    return FfmpegBinaryResolution.Failed(
        FfmpegBinaryResolutionError.NotFound,
        "ffmpeg.exe was not found. Provide bundled ffmpeg.exe, an explicit path, or add ffmpeg.exe to PATH.");
}
```

- [ ] **Step 5: Add installed bundled path helpers to production resolvers**

In `VideoPosterSidecarProducer.cs`, replace `DefaultVideoPosterFfmpegResolver` with:

```csharp
internal sealed class DefaultVideoPosterFfmpegResolver : IVideoPosterFfmpegResolver
{
    public FfmpegBinaryResolution Resolve()
        => FfmpegBinaryResolver.Resolve(
            bundledPath: InstalledBundledFfmpegPath());

    private static string InstalledBundledFfmpegPath()
        => Path.Combine(
            AppContext.BaseDirectory,
            "ffmpeg",
            "ffmpeg.exe");
}
```

In `VideoFrameSidecarProducer.cs`, replace `DefaultVideoFrameFfmpegResolver` with:

```csharp
internal sealed class DefaultVideoFrameFfmpegResolver : IVideoFrameFfmpegResolver
{
    public FfmpegBinaryResolution Resolve()
        => FfmpegBinaryResolver.Resolve(
            bundledPath: InstalledBundledFfmpegPath());

    private static string InstalledBundledFfmpegPath()
        => Path.Combine(
            AppContext.BaseDirectory,
            "ffmpeg",
            "ffmpeg.exe");
}
```

Preserve the existing test seams: the producers continue accepting
`IVideoPosterFfmpegResolver` and `IVideoFrameFfmpegResolver`, and tests that
inject fake resolvers should not need to know about bundled-path resolution.

- [ ] **Step 6: Run resolver and producer tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests|FullyQualifiedName~VideoPosterSidecarProducerTests|FullyQualifiedName~VideoFrameSidecarProducerTests"
```

Expected: PASS.

- [ ] **Step 7: Commit runtime resolver changes**

Run:

```powershell
git add src\Rook\Services\Vision\Video\Extraction\VideoExtractionSpikeModels.cs src\Rook\Services\Vision\Video\Extraction\FfmpegBinaryResolver.cs src\Rook\Services\Vision\Video\VideoPosterSidecarProducer.cs src\Rook\Services\Vision\Video\VideoFrameSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\Extraction\FfmpegBinaryResolverTests.cs
git commit -m "Prefer bundled FFmpeg for video sidecars"
```

Expected: commit succeeds.

## Task 6: Update Release Docs and Queue

**Files:**
- Modify: `BUILDING.md`
- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.agents/skills/build-release/references/iss-source-paths.md`
- Modify: `docs/rook_docs/video-thumbnail-roadmap.md`
- Modify: `docs/rook_docs/work-queue.md`

- [ ] **Step 1: Update release docs**

In `BUILDING.md` and the build-release skill docs, add a short release prerequisite section:

```markdown
### Bundled FFmpeg

Rook release installers bundle an LGPL-only `ffmpeg.exe` for generated-video
thumbnail and frame sidecar extraction. Before building an installer, run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1
```

The guard fails closed for missing metadata, checksum mismatch, GPL/nonfree
configure flags, missing compliance files, or failure to extract poster,
first-frame, and last-frame JPEGs from the smoke fixture. PATH-discovered
FFmpeg is allowed for development smoke only and cannot satisfy release
validation.
```

- [ ] **Step 2: Mark Slice 6 complete in roadmap after implementation**

In `docs/rook_docs/video-thumbnail-roadmap.md`, change Slice 6 status from `Current` to `Done` only after all verification passes.

- [ ] **Step 3: Update work queue after implementation**

In `docs/rook_docs/work-queue.md`, add a top entry stating:

```markdown
**Last triaged:** 2026-05-12 (**RookVision video thumbnail Slice 6 FFmpeg bundling implemented.** Rook now packages a vetted LGPL-only `ffmpeg.exe` subprocess payload for video sidecar extraction, release validation fails closed for GPL/nonfree/unknown/checksum/compliance failures, and runtime sidecar extraction prefers the installed bundled FFmpeg while development PATH/config fallback remains non-shippable. Verification covered release guard, installer guard, focused resolver/producer tests, full managed suite, and managed `net7.0` build. **Next:** choose between provider/model payload audit and Grasshopper NLE token behavior; do not combine them.)
```

Adjust verification counts to actual outputs.

- [ ] **Step 4: Run release and validation guards**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tests\ffmpeg-bundle-validation.tests.ps1
powershell -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: both PASS.

- [ ] **Step 5: Commit docs**

Run:

```powershell
git add BUILDING.md .agents\skills\build-release\SKILL.md .agents\skills\build-release\references\iss-source-paths.md docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
git commit -m "Document bundled FFmpeg release policy"
```

Expected: commit succeeds.

## Task 7: Final Verification

**Files:** no code changes expected.

- [ ] **Step 1: Run FFmpeg validation policy tests**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tests\ffmpeg-bundle-validation.tests.ps1
```

Expected: PASS and prints `FFmpeg bundle validation policy tests passed.`

- [ ] **Step 2: Run FFmpeg bundle validation**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1
```

Expected: PASS and prints `FFmpeg bundle validation passed`.

- [ ] **Step 3: Run installer guard tests**

Run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: PASS and prints `Release installer guard tests passed.`

- [ ] **Step 4: Run focused managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests|FullyQualifiedName~VideoPosterSidecarProducerTests|FullyQualifiedName~VideoFrameSidecarProducerTests"
```

Expected: PASS.

- [ ] **Step 5: Run full managed suite**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore
```

Expected: PASS.

- [ ] **Step 6: Run managed net7 build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore /p:RhinoPluginDir=C:\__rook_missing_rhino_plugin_dir__
```

Expected: PASS with existing warnings only.

- [ ] **Step 7: Run diff check**

Run:

```powershell
git diff --check
```

Expected: PASS. Ignore unrelated dirty proto-skills files only if they remain outside the staged/committed scope.

- [ ] **Step 8: Inspect final status**

Run:

```powershell
git status --short --branch
```

Expected: implementation files are clean. Unrelated proto-skills files may remain dirty and must not be committed by this slice.

## Self-Review Checklist

- [ ] Release validation uses the bundled payload path directly, not resolver fallback.
- [ ] Release validation rejects GPL and nonfree configure flags from both metadata and runtime `ffmpeg -version`.
- [ ] Functional smoke covers poster, first-frame, and last-frame command shapes.
- [ ] Installer packages `ffmpeg.exe`, provenance, license, notice, and source-compliance files.
- [ ] Runtime sidecar extraction prefers installed bundled FFmpeg.
- [ ] Dev configured/PATH fallback remains possible but cannot satisfy release validation.
- [ ] No FFmpeg libraries are linked.
- [ ] No provider payload ingestion is added.
- [ ] No GH NLE token behavior is added.
