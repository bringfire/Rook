# FFmpeg Bundling Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the broad BtbN FFmpeg payload in PR #148 with a release-blocking, Rook-owned minimal LGPL-only FFmpeg build flow for video sidecars.

**Architecture:** Keep FFmpeg as an external `ffmpeg.exe` subprocess dependency. The repo owns the pinned source metadata, minimal configure recipe, machine-readable `--enable-*` allowlist, build/source-bundle scripts, release validator, installer plumbing, runtime resolver, and policy tests. The installer ships only the validated minimal binary and installed notice files; the release process generates and publishes the matching source bundle beside the installer.

**Tech Stack:** PowerShell release/build scripts, MSYS2 UCRT64/MinGW for the FFmpeg build recipe, Inno Setup installer, C# managed companion resolver, xUnit tests, Git LFS for `ffmpeg.exe` only.

---

## Source Spec

Implement this plan against:

- `docs/superpowers/specs/2026-05-12-ffmpeg-bundling-policy-design.md`

The key post-review constraint is that the release validator must consume a committed machine-readable allowlist for **all** `--enable-*` flags. It must not rely on prose or only screen `--enable-lib*`.

## Execution Boundary

Do not execute this plan on `main`. Continue using the PR worktree:

```powershell
Set-Location C:\Users\aryan\source\repos\Rook\.worktrees\ffmpeg-bundling-policy-pr
git status -sb
```

Expected:

```text
## codex/ffmpeg-bundling-policy-pr...origin/codex/ffmpeg-bundling-policy-pr
```

The current broad BtbN binary is still present in this draft PR. This plan removes it as a shippable compliance model and replaces it with the Rook-owned minimal-build contract.

## File Map

- Create `scripts/ffmpeg/rook-ffmpeg-source.json`: pinned official FFmpeg source archive, signature URL, SHA-256, and signing key metadata.
- Create `scripts/ffmpeg/rook-ffmpeg-configure.txt`: exact minimal configure arguments, one argument per line.
- Create `scripts/ffmpeg/rook-ffmpeg-enable-allowlist.json`: validator source of truth for allowed `--enable-*` flags.
- Create `scripts/ffmpeg/README.md`: build/release workflow notes.
- Create `scripts/ffmpeg/build-rook-ffmpeg.ps1`: PowerShell wrapper that verifies source, invokes MSYS2, builds `ffmpeg.exe`, generates `changes.diff`, and stages the source bundle manifest.
- Modify `scripts/validate-ffmpeg-bundle.ps1`: validate source signature status, configure allowlist, source bundle manifest, staged source bundle, installer payload, and functional smoke.
- Modify `scripts/tests/ffmpeg-bundle-validation.tests.ps1`: policy tests for the new allowlist and source-bundle contract.
- Modify `scripts/tests/release-installer-guards.tests.ps1`: stop treating the committed repo as a complete release-staging directory; verify release docs require the validator with a source-bundle manifest.
- Modify `installer/RookSetup.iss`: keep plugin-local FFmpeg packaging but remove broad dependency-manifest files that no longer apply.
- Modify `third_party/ffmpeg/*`: replace BtbN metadata with Rook-owned minimal metadata; remove `ffmpeg-dependencies.json` and `DEPENDENCIES.FFmpeg.txt`.
- Create or replace fixtures under `third_party/ffmpeg/fixtures/`: at least H.264 MP4 plus one WebM/VP9 or AV1 fixture.
- Preserve `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs` and producer resolver wiring unless tests reveal a regression; the existing plugin-local resolver shape is correct.
- Update build-release docs and work queue after validation passes.

## Manual Build Prerequisite

Task 6 requires a Windows FFmpeg build environment. Use MSYS2 UCRT64 unless release ownership chooses another repeatable Windows build environment before execution.

Expected build tools:

```powershell
Test-Path C:\msys64\usr\bin\bash.exe
C:\msys64\usr\bin\bash.exe -lc "pacman -Q --needed base-devel mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-pkgconf nasm yasm git gpg"
```

If MSYS2 or packages are missing, install them manually before Task 6. Do not add those tools as Rook runtime dependencies.

## Task 1: Add the Minimal Build Recipe Contract

**Files:**

- Create: `scripts/ffmpeg/rook-ffmpeg-source.json`
- Create: `scripts/ffmpeg/rook-ffmpeg-configure.txt`
- Create: `scripts/ffmpeg/rook-ffmpeg-enable-allowlist.json`
- Create: `scripts/ffmpeg/README.md`

- [ ] **Step 1: Add official source metadata**

Create `scripts/ffmpeg/rook-ffmpeg-source.json`:

```json
{
  "schema_version": 1,
  "name": "FFmpeg",
  "version": "8.1.1",
  "release_name": "Hoare",
  "source_url": "https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz",
  "source_archive": "ffmpeg-8.1.1.tar.xz",
  "source_sha256": "B6863ADDE98898F42602017462871B5F6333E65AEC803FDD7A6308639C52EDF3",
  "source_signature_url": "https://ffmpeg.org/releases/ffmpeg-8.1.1.tar.xz.asc",
  "signing_key_url": "https://ffmpeg.org/ffmpeg-devel.asc",
  "signing_key_fingerprint": "FCF986EA15E6E293A5644F10B4322F04D67658D8",
  "source_signature_status_required": "verified"
}
```

- [ ] **Step 2: Add the first minimal configure recipe**

Create `scripts/ffmpeg/rook-ffmpeg-configure.txt`:

```text
--disable-everything
--disable-autodetect
--disable-network
--disable-doc
--disable-debug
--enable-ffmpeg
--enable-protocol=file
--enable-demuxer=mov
--enable-demuxer=matroska
--enable-muxer=image2
--enable-decoder=h264
--enable-decoder=hevc
--enable-decoder=mpeg4
--enable-decoder=vp8
--enable-decoder=vp9
--enable-decoder=av1
--enable-decoder=mjpeg
--enable-parser=h264
--enable-parser=hevc
--enable-parser=mpeg4video
--enable-parser=vp8
--enable-parser=vp9
--enable-parser=av1
--enable-parser=mjpeg
--enable-filter=select
--enable-filter=reverse
--enable-encoder=mjpeg
```

If the codec reality check in Task 6 proves a native FFmpeg component is missing, update this file and the allowlist together. Do not add external libraries as convenience guesses.

- [ ] **Step 3: Add the committed `--enable-*` allowlist**

Create `scripts/ffmpeg/rook-ffmpeg-enable-allowlist.json`:

```json
{
  "schema_version": 1,
  "description": "Allowed --enable-* flags for the Rook-owned minimal FFmpeg build. Release validation rejects any runtime --enable-* flag not listed here unless explicit external/system provenance is supplied.",
  "allowed_enable_flags": [
    "--enable-ffmpeg",
    "--enable-protocol=file",
    "--enable-demuxer=mov",
    "--enable-demuxer=matroska",
    "--enable-muxer=image2",
    "--enable-decoder=h264",
    "--enable-decoder=hevc",
    "--enable-decoder=mpeg4",
    "--enable-decoder=vp8",
    "--enable-decoder=vp9",
    "--enable-decoder=av1",
    "--enable-decoder=mjpeg",
    "--enable-parser=h264",
    "--enable-parser=hevc",
    "--enable-parser=mpeg4video",
    "--enable-parser=vp8",
    "--enable-parser=vp9",
    "--enable-parser=av1",
    "--enable-parser=mjpeg",
    "--enable-filter=select",
    "--enable-filter=reverse",
    "--enable-encoder=mjpeg"
  ],
  "external_provenance_overrides": []
}
```

- [ ] **Step 4: Add recipe README**

Create `scripts/ffmpeg/README.md`:

```markdown
# Rook Minimal FFmpeg Build

Rook ships `ffmpeg.exe` only for generated-video sidecar extraction. The build
is LGPL-only, subprocess-only, and intentionally minimal.

The release recipe uses official FFmpeg source metadata from
`rook-ffmpeg-source.json`, configure arguments from
`rook-ffmpeg-configure.txt`, and the release validation allowlist from
`rook-ffmpeg-enable-allowlist.json`.

The repository commits the recipe and the validated `ffmpeg.exe` payload. It
does not commit generated source bundles. Release prep generates the matching
source bundle and publishes it beside the installer.

Normal release validation must reject:

- missing or unverified official source signature;
- `--enable-gpl`;
- `--enable-nonfree`;
- any runtime `--enable-*` flag not in the committed allowlist;
- missing generated source-bundle manifest;
- functional smoke failure for poster, first frame, or last frame.
```

- [ ] **Step 5: Run a diff check**

Run:

```powershell
git diff --check
```

Expected: no output and exit code `0`.

- [ ] **Step 6: Commit Task 1**

Run:

```powershell
git add scripts\ffmpeg\rook-ffmpeg-source.json scripts\ffmpeg\rook-ffmpeg-configure.txt scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json scripts\ffmpeg\README.md
git commit -m "Add minimal FFmpeg build recipe contract"
```

## Task 2: Add the Rook FFmpeg Build and Source-Bundle Script

**Files:**

- Create: `scripts/ffmpeg/build-rook-ffmpeg.ps1`

- [ ] **Step 1: Add script parameters and metadata loading**

Create `scripts/ffmpeg/build-rook-ffmpeg.ps1` with this header:

```powershell
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
```

- [ ] **Step 2: Add source download/hash/signature verification helpers**

Add:

```powershell
function Assert-Tool {
    param([string]$Path, [string]$Name)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "$Name was not found at $Path"
    }
}

function Invoke-Checked {
    param([string]$FilePath, [string[]]$Arguments)
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FilePath failed with exit code $LASTEXITCODE"
    }
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
    return $Path.Replace('\', '/').Replace('C:', '/c')
}

function Invoke-Msys2 {
    param([string]$Command)
    $env:MSYSTEM = 'UCRT64'
    $env:CHERE_INVOKING = '1'
    Invoke-Checked -FilePath $Msys2Bash -Arguments @('-lc', $Command)
}
```

- [ ] **Step 3: Add the build/stage flow**

Continue the script:

```powershell
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

$gpgHome = Join-Path $StageRoot 'gnupg'
New-Item -ItemType Directory -Force $gpgHome | Out-Null
Invoke-Msys2 -Command "gpg --homedir '$(Convert-ToMsysPath $gpgHome)' --import '$(Convert-ToMsysPath $SigningKeyPath)'"
Invoke-Msys2 -Command "gpg --homedir '$(Convert-ToMsysPath $gpgHome)' --verify '$(Convert-ToMsysPath $SignaturePath)' '$(Convert-ToMsysPath $ArchivePath)'"
$SignatureStatus = 'verified'
```

- [ ] **Step 4: Add the MSYS2 compile invocation**

Add:

```powershell
$configureText = ($ConfigureArgs -join "`n")
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
make -j`$(nproc) ffmpeg
"@

$bashScriptPath = Join-Path $StageRoot 'build-ffmpeg.sh'
Set-Content -LiteralPath $bashScriptPath -Value $bashScript -Encoding UTF8

Invoke-Msys2 -Command (Convert-ToMsysPath $bashScriptPath)
```

- [ ] **Step 5: Generate payload metadata and source bundle**

Add:

```powershell
$BuiltExe = Join-Path $BuildRoot 'src\ffmpeg.exe'
if (-not (Test-Path -LiteralPath $BuiltExe -PathType Leaf)) {
    throw "Built ffmpeg.exe was not found: $BuiltExe"
}

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
    configure_line = ($ConfigureArgs -join ' ')
    changes_diff_path = 'changes.diff'
    build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
    generated_at = [DateTimeOffset]::UtcNow.ToString('o')
    generated_by = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $BundleManifestPath -Encoding UTF8
```

- [ ] **Step 6: Support installing the generated payload into the repo**

Add:

```powershell
if ($InstallPayload) {
    New-Item -ItemType Directory -Force $PayloadDir | Out-Null
    Copy-Item -LiteralPath $BuiltExe -Destination (Join-Path $PayloadDir 'ffmpeg.exe') -Force

    $BinaryHash = (Get-FileHash -LiteralPath (Join-Path $PayloadDir 'ffmpeg.exe') -Algorithm SHA256).Hash
    [ordered]@{
        name = 'FFmpeg'
        version = "n$($SourceMetadata.version)-rook-minimal"
        license = 'LGPL-only'
        binary_path = 'third_party/ffmpeg/ffmpeg.exe'
        binary_sha256 = $BinaryHash
        source_url = $SourceMetadata.source_url
        source_archive = $SourceMetadata.source_archive
        source_sha256 = $SourceMetadata.source_sha256
        source_signature_url = $SourceMetadata.source_signature_url
        source_signature_status = $SignatureStatus
        build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
        configure_recipe_path = 'scripts/ffmpeg/rook-ffmpeg-configure.txt'
        configure_line = ($ConfigureArgs -join ' ')
        changes_diff_path = 'changes.diff'
        source_bundle_manifest_name = 'rook-ffmpeg-source-bundle-manifest.json'
        validated_command_surfaces = @('poster', 'first_frame', 'last_frame')
        validated_fixtures = @()
        verified_at = [DateTimeOffset]::UtcNow.ToString('o')
        verified_by = 'Rook minimal FFmpeg build recipe'
        notes = 'Built by Rook from official FFmpeg source for video sidecar extraction via ffmpeg.exe subprocess only.'
    } | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $PayloadDir 'ffmpeg-provenance.json') -Encoding UTF8
}

Write-Host "Built FFmpeg: $BuiltExe"
Write-Host "Source bundle manifest: $BundleManifestPath"
```

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add scripts\ffmpeg\build-rook-ffmpeg.ps1
git commit -m "Add minimal FFmpeg build script"
```

## Task 3: Rewrite Validation Policy Tests First

**Files:**

- Modify: `scripts/tests/ffmpeg-bundle-validation.tests.ps1`

- [ ] **Step 1: Update the fake configure line to the minimal allowlist**

In `New-FakeFFmpeg`, replace the `-version` configure output with:

```csharp
Console.WriteLine("ffmpeg version n8.1.1-rook-minimal");
Console.WriteLine("configuration: --disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug --enable-ffmpeg --enable-protocol=file --enable-demuxer=mov --enable-demuxer=matroska --enable-muxer=image2 --enable-decoder=h264 --enable-parser=h264 --enable-filter=select --enable-filter=reverse --enable-encoder=mjpeg");
```

- [ ] **Step 2: Replace the temp payload metadata shape**

In `New-TestPayload`, create:

```powershell
$allowlist = [ordered]@{
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
}
$allowlistPath = Join-Path $root 'scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json'
New-Item -ItemType Directory -Force (Split-Path -Parent $allowlistPath) | Out-Null
$allowlist | ConvertTo-Json -Depth 5 | Set-Content -Path $allowlistPath -Encoding UTF8

$sourceBundle = Join-Path $root 'release\rook-ffmpeg-source-bundle.zip'
New-Item -ItemType Directory -Force (Split-Path -Parent $sourceBundle) | Out-Null
Set-Content -Path $sourceBundle -Value 'fake source bundle' -Encoding ASCII
$sourceBundleHash = (Get-FileHash -LiteralPath $sourceBundle -Algorithm SHA256).Hash
$sourceBundleManifest = Join-Path $root 'release\rook-ffmpeg-source-bundle-manifest.json'
[ordered]@{
    schema_version = 1
    bundle_path = $sourceBundle
    bundle_sha256 = $sourceBundleHash
    ffmpeg_source_archive = 'ffmpeg-8.1.1.tar.xz'
    ffmpeg_source_sha256 = 'B6863ADDE98898F42602017462871B5F6333E65AEC803FDD7A6308639C52EDF3'
    configure_line = '--disable-everything --disable-autodetect --disable-network --disable-doc --disable-debug --enable-ffmpeg --enable-protocol=file --enable-demuxer=mov --enable-demuxer=matroska --enable-muxer=image2 --enable-decoder=h264 --enable-parser=h264 --enable-filter=select --enable-filter=reverse --enable-encoder=mjpeg'
    changes_diff_path = 'changes.diff'
    build_recipe_path = 'scripts/ffmpeg/build-rook-ffmpeg.ps1'
    generated_at = '2026-05-12T00:00:00Z'
    generated_by = 'test'
} | ConvertTo-Json -Depth 5 | Set-Content -Path $sourceBundleManifest -Encoding UTF8
```

Return `AllowlistPath` and `SourceBundleManifestPath` from `New-TestPayload`.

- [ ] **Step 3: Make every validator invocation pass allowlist and source-bundle manifest paths**

Use this helper:

```powershell
function Invoke-Validator {
    param(
        [object]$Payload,
        [string[]]$ExtraArgs = @()
    )

    $args = @(
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-File', $ValidatorScript,
        '-RepoRoot', $Payload.Root,
        '-PayloadDir', $Payload.PayloadDir,
        '-InstallerScriptPath', $Payload.InstallerScriptPath,
        '-AllowlistPath', $Payload.AllowlistPath,
        '-SourceBundleManifestPath', $Payload.SourceBundleManifestPath
    ) + $ExtraArgs

    & powershell @args 2>&1
}
```

- [ ] **Step 4: Add red tests for the new blockers**

Add tests named:

```powershell
Test-RejectsUnexpectedEnableZlib
Test-RejectsMissingSourceSignatureVerification
Test-RejectsMissingSourceBundleManifest
Test-RejectsSourceBundleHashMismatch
```

Each test should mutate one temp payload and assert the error text:

```powershell
Assert-Contains -Text $output -Expected 'unexpected FFmpeg configure enable flag --enable-zlib' -Message 'Validator must reject broad non-allowlisted enable flags.'
Assert-Contains -Text $output -Expected 'source_signature_status must be verified' -Message 'Validator must require verified official FFmpeg source signatures.'
Assert-Contains -Text $output -Expected 'source bundle manifest is missing' -Message 'Validator must require release source-bundle staging.'
Assert-Contains -Text $output -Expected 'source bundle checksum mismatch' -Message 'Validator must verify the staged source bundle hash.'
```

- [ ] **Step 5: Run the policy tests and confirm they fail**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\ffmpeg-bundle-validation.tests.ps1
```

Expected before Task 4: FAIL with at least the new allowlist/signature/source-bundle assertions.

- [ ] **Step 6: Keep the failing tests uncommitted**

Do not commit the red state. Confirm the test file is modified and leave it for Task 4:

```powershell
git status -sb
```

Expected: `scripts/tests/ffmpeg-bundle-validation.tests.ps1` is modified.

## Task 4: Rewrite the Release Validator Around Allowlist and Source Bundle

**Files:**

- Modify: `scripts/validate-ffmpeg-bundle.ps1`

- [ ] **Step 1: Add new parameters**

Change the parameter block to include:

```powershell
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$PayloadDir = '',
    [string]$InstallerScriptPath = '',
    [string]$AllowlistPath = '',
    [string]$SourceBundleManifestPath = '',
    [switch]$SkipFunctionalSmoke
)
```

Default empty paths after repo root resolution:

```powershell
if ([string]::IsNullOrWhiteSpace($PayloadDir)) {
    $PayloadDir = Join-Path $RepoRoot 'third_party\ffmpeg'
}
if ([string]::IsNullOrWhiteSpace($InstallerScriptPath)) {
    $InstallerScriptPath = Join-Path $RepoRoot 'installer\RookSetup.iss'
}
if ([string]::IsNullOrWhiteSpace($AllowlistPath)) {
    $AllowlistPath = Join-Path $RepoRoot 'scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json'
}
```

- [ ] **Step 2: Replace dependency-manifest validation with allowlist validation**

Remove `Assert-DependencyManifest`. Add:

```powershell
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
```

- [ ] **Step 3: Require verified official source signatures**

Add:

```powershell
function Assert-SourceSignatureVerified {
    param([object]$Provenance)

    Require-NonEmptyField -Provenance $Provenance -Field 'source_signature_url'
    Require-NonEmptyField -Provenance $Provenance -Field 'source_signature_status'

    if ($Provenance.source_signature_status -ne 'verified') {
        Fail "source_signature_status must be verified for official FFmpeg release source"
    }
}
```

- [ ] **Step 4: Validate the staged source bundle manifest**

Add:

```powershell
function Assert-SourceBundleManifest {
    param(
        [string]$Path,
        [object]$Provenance
    )

    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        Fail "source bundle manifest is missing"
    }

    try {
        $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    } catch {
        Fail "source bundle manifest is malformed: $($_.Exception.Message)"
    }

    foreach ($field in @('bundle_path', 'bundle_sha256', 'ffmpeg_source_archive', 'ffmpeg_source_sha256', 'configure_line', 'changes_diff_path', 'build_recipe_path', 'generated_at', 'generated_by')) {
        Require-NonEmptyField -Provenance $manifest -Field $field
    }

    if ($manifest.ffmpeg_source_archive -ne $Provenance.source_archive) {
        Fail "source bundle manifest source archive does not match provenance"
    }

    if ($manifest.ffmpeg_source_sha256 -ne $Provenance.source_sha256) {
        Fail "source bundle manifest source checksum does not match provenance"
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
}
```

- [ ] **Step 5: Wire the new checks into the main validation flow**

In the main flow, after parsing provenance and runtime configure output, call:

```powershell
Assert-SourceSignatureVerified -Provenance $provenance
Assert-ConfigureEnableAllowlist -ConfigureLine $runtimeConfigureLine -AllowlistPath $AllowlistPath
Assert-ConfigureEnableAllowlist -ConfigureLine $provenance.configure_line -AllowlistPath $AllowlistPath
Assert-SourceBundleManifest -Path $SourceBundleManifestPath -Provenance $provenance
```

Delete any requirement for `ffmpeg-dependencies.json` or `DEPENDENCIES.FFmpeg.txt`.

- [ ] **Step 6: Run the policy tests and confirm they pass**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\ffmpeg-bundle-validation.tests.ps1
```

Expected: `FFmpeg bundle validation policy tests passed.`

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add scripts\validate-ffmpeg-bundle.ps1 scripts\tests\ffmpeg-bundle-validation.tests.ps1
git commit -m "Validate minimal FFmpeg provenance and allowlist"
```

## Task 5: Update Installer Guards and Release Docs for Staged Source Bundles

**Files:**

- Modify: `scripts/tests/release-installer-guards.tests.ps1`
- Modify: `installer/RookSetup.iss`
- Modify: `BUILDING.md`
- Modify: `.agents/skills/build-release/SKILL.md`
- Modify: `.agents/skills/build-release/references/iss-source-paths.md`
- Modify: `.claude/skills/build-release/SKILL.md`
- Modify: `.claude/skills/build-release/references/iss-source-paths.md`

- [ ] **Step 1: Remove obsolete installed dependency-manifest packaging**

In `installer/RookSetup.iss`, remove `Source` lines for:

```text
ffmpeg-dependencies.json
DEPENDENCIES.FFmpeg.txt
```

Keep `ffmpeg.exe`, `ffmpeg-provenance.json`, `LICENSE.FFmpeg.txt`, `NOTICE.FFmpeg.txt`, `SOURCE.FFmpeg.txt`, and `README.md`.

- [ ] **Step 2: Update installer guard expected files**

In `Test-InstallerPackagesBundledFfmpegPayload`, replace the FFmpeg file list with:

```powershell
foreach ($fileName in @(
    'ffmpeg.exe',
    'ffmpeg-provenance.json',
    'LICENSE.FFmpeg.txt',
    'NOTICE.FFmpeg.txt',
    'SOURCE.FFmpeg.txt',
    'README.md'
)) {
    Assert-FfmpegInstallerLine -FileName $fileName
}
```

- [ ] **Step 3: Stop running full release validation without a staged source bundle**

Replace `Test-FfmpegBundleValidationPasses` with:

```powershell
function Test-FfmpegValidatorRequiresReleaseSourceBundleArgument {
    Assert-True -Condition (Test-Path $FfmpegValidationScript) -Message "FFmpeg validation script is missing: $FfmpegValidationScript"

    $script = Get-Content -Path $FfmpegValidationScript -Raw
    Assert-Contains -Text $script -Expected 'SourceBundleManifestPath' -Message 'FFmpeg validator must require a release source-bundle manifest path.'
    Assert-Contains -Text $script -Expected 'Assert-SourceBundleManifest' -Message 'FFmpeg validator must verify the staged release source bundle.'
}
```

Update the invocation at the bottom to call `Test-FfmpegValidatorRequiresReleaseSourceBundleArgument`.

- [ ] **Step 4: Update release docs to show the two release commands**

Where release docs currently say to run only `scripts\validate-ffmpeg-bundle.ps1`, replace with:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ffmpeg\build-rook-ffmpeg.ps1 -InstallPayload
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json
```

If the exact staging directory differs after Task 6, update the docs to the real path produced by the script.

- [ ] **Step 5: Run release installer guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: `Release installer guard tests passed.`

- [ ] **Step 6: Commit Task 5**

Run:

```powershell
git add installer\RookSetup.iss scripts\tests\release-installer-guards.tests.ps1 BUILDING.md .agents\skills\build-release\SKILL.md .agents\skills\build-release\references\iss-source-paths.md .claude\skills\build-release\SKILL.md .claude\skills\build-release\references\iss-source-paths.md
git commit -m "Require staged FFmpeg source bundle in release docs"
```

## Task 6: Build the Minimal FFmpeg Payload and Replace BtbN

**Files:**

- Modify: `third_party/ffmpeg/ffmpeg.exe`
- Modify: `third_party/ffmpeg/ffmpeg-provenance.json`
- Modify: `third_party/ffmpeg/README.md`
- Modify: `third_party/ffmpeg/LICENSE.FFmpeg.txt`
- Modify: `third_party/ffmpeg/NOTICE.FFmpeg.txt`
- Modify: `third_party/ffmpeg/SOURCE.FFmpeg.txt`
- Delete: `third_party/ffmpeg/ffmpeg-dependencies.json`
- Delete: `third_party/ffmpeg/DEPENDENCIES.FFmpeg.txt`
- Create/modify: `third_party/ffmpeg/fixtures/*`

- [ ] **Step 1: Build and install the Rook minimal payload**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ffmpeg\build-rook-ffmpeg.ps1 -InstallPayload
```

Expected:

```text
Built FFmpeg: ...
Source bundle manifest: ...
```

Save the printed source bundle manifest path for validation.

- [ ] **Step 2: Inspect the built configure line**

Run:

```powershell
third_party\ffmpeg\ffmpeg.exe -version | Select-String -Pattern '^configuration:'
```

Expected: no `--enable-gpl`, no `--enable-nonfree`, and no `--enable-*` flags outside `scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json`.

- [ ] **Step 3: Remove BtbN-only compliance files**

Run:

```powershell
git rm third_party\ffmpeg\ffmpeg-dependencies.json third_party\ffmpeg\DEPENDENCIES.FFmpeg.txt
```

- [ ] **Step 4: Update installed compliance files**

Update `third_party/ffmpeg/README.md` to say:

```markdown
# Rook Minimal FFmpeg Payload

This directory contains the validated Rook-owned minimal LGPL-only FFmpeg
binary used for generated-video sidecar extraction.

The binary is built from official FFmpeg source using:

- `scripts/ffmpeg/rook-ffmpeg-source.json`
- `scripts/ffmpeg/rook-ffmpeg-configure.txt`
- `scripts/ffmpeg/build-rook-ffmpeg.ps1`

The matching source bundle is generated during release prep and published
beside the Rook installer.
```

Update `SOURCE.FFmpeg.txt` to name the official source URL, source SHA-256, signature URL, signing key fingerprint, build recipe path, configure recipe path, and state that the release source bundle is published beside the installer.

- [ ] **Step 5: Add or regenerate smoke fixtures**

Use the newly built FFmpeg if it can encode the fixtures; otherwise use a development FFmpeg and then validate decode/extraction using the minimal binary.

Commands:

```powershell
New-Item -ItemType Directory -Force third_party\ffmpeg\fixtures
third_party\ffmpeg\ffmpeg.exe -hide_banner -y -f lavfi -i testsrc2=size=64x64:rate=3:duration=1 -c:v h264 third_party\ffmpeg\fixtures\sidecar-smoke-h264.mp4
third_party\ffmpeg\ffmpeg.exe -hide_banner -y -f lavfi -i testsrc2=size=64x64:rate=3:duration=1 -c:v vp9 third_party\ffmpeg\fixtures\sidecar-smoke-vp9.webm
```

If this fails because the minimal binary intentionally lacks lavfi or encoders for fixture generation, generate fixtures with the prior development FFmpeg and keep only decode/extraction capability in the Rook minimal binary. Do not add lavfi or broad encoders to the shipped binary just for fixture generation.

- [ ] **Step 6: Run full release validation with the generated source bundle manifest**

Run with the real manifest path printed by Step 1:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json
```

Expected:

```text
FFmpeg bundle validation passed: ...
```

- [ ] **Step 7: Confirm Git LFS still tracks only `ffmpeg.exe`**

Run:

```powershell
git lfs ls-files
git check-attr -a -- third_party\ffmpeg\ffmpeg.exe
```

Expected: `third_party/ffmpeg/ffmpeg.exe` uses `filter=lfs`, `diff=lfs`, `merge=lfs`, and `text: unset`.

- [ ] **Step 8: Commit Task 6**

Run:

```powershell
git add third_party\ffmpeg .gitattributes
git commit -m "Replace broad FFmpeg payload with Rook minimal build"
```

## Task 7: Preserve Runtime Resolver Behavior

**Files:**

- Review/modify only if needed: `src/Rook/Services/Vision/Video/Extraction/FfmpegBinaryResolver.cs`
- Review/modify only if needed: `src/Rook/Services/Vision/Video/VideoPosterSidecarProducer.cs`
- Review/modify only if needed: `src/Rook/Services/Vision/Video/VideoFrameSidecarProducer.cs`
- Test: `src/Rook.Tests/Services/Vision/Video/Extraction/FfmpegBinaryResolverTests.cs`

- [ ] **Step 1: Run resolver tests before touching runtime code**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests"
```

Expected: resolver tests pass. If they pass, do not rewrite resolver code.

- [ ] **Step 2: Verify the installed path remains plugin-local**

Ensure `FfmpegBundledBinaryLocator.GetInstalledFfmpegPath` still returns:

```csharp
Path.Combine(pluginDirectory, "ffmpeg", "ffmpeg.exe")
```

This path matches the Inno destination:

```text
{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg
```

- [ ] **Step 3: Commit only if code changed**

If no runtime files changed, skip this commit. If a small resolver/test adjustment was required, run:

```powershell
git add src\Rook\Services\Vision\Video\Extraction\FfmpegBinaryResolver.cs src\Rook\Services\Vision\Video\VideoPosterSidecarProducer.cs src\Rook\Services\Vision\Video\VideoFrameSidecarProducer.cs src\Rook.Tests\Services\Vision\Video\Extraction\FfmpegBinaryResolverTests.cs
git commit -m "Preserve bundled FFmpeg runtime resolution"
```

## Task 8: Update Roadmap and Work Queue

**Files:**

- Modify: `docs/rook_docs/video-thumbnail-roadmap.md`
- Modify: `docs/rook_docs/work-queue.md`

- [ ] **Step 1: Update roadmap Slice 6 language**

Ensure the roadmap says Slice 6 ships a Rook-owned minimal LGPL FFmpeg build recipe and release gate, not a broad third-party binary.

- [ ] **Step 2: Update the work queue**

Add a note that PR #148 remains draft until:

```text
- broad BtbN payload is removed from the shippable path;
- Rook minimal FFmpeg binary is built and validated;
- release source-bundle manifest is generated during release prep;
- validator passes against the minimal binary and source bundle manifest.
```

- [ ] **Step 3: Commit Task 8**

Run:

```powershell
git add docs\rook_docs\video-thumbnail-roadmap.md docs\rook_docs\work-queue.md
git commit -m "Update FFmpeg bundling roadmap"
```

## Task 9: Final Verification and PR Preparation

**Files:** no edits unless verification reveals a defect.

- [ ] **Step 1: Run policy tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\ffmpeg-bundle-validation.tests.ps1
```

Expected: `FFmpeg bundle validation policy tests passed.`

- [ ] **Step 2: Run installer guard tests**

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\tests\release-installer-guards.tests.ps1
```

Expected: `Release installer guard tests passed.`

- [ ] **Step 3: Run full release FFmpeg validation with the generated manifest**

Run with the actual manifest path from Task 6:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json
```

Expected: `FFmpeg bundle validation passed: ...`

- [ ] **Step 4: Run focused managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore --filter "FullyQualifiedName~FfmpegBinaryResolverTests|FullyQualifiedName~FfmpegPosterFrameExtractorTests|FullyQualifiedName~FfmpegVideoFrameExtractorTests|FullyQualifiedName~VideoPosterSidecarProducerTests|FullyQualifiedName~VideoFrameSidecarProducerTests"
```

Expected: all focused tests pass.

- [ ] **Step 5: Run full managed tests**

Run:

```powershell
dotnet test src\Rook.Tests\Rook.Tests.csproj -f net48 --no-restore
```

Expected: all managed tests pass.

- [ ] **Step 6: Run the net7 managed build**

Run:

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 --no-restore /p:RhinoPluginDir=C:\__rook_missing_rhino_plugin_dir__
```

Expected: build exits `0`; existing warnings are acceptable.

- [ ] **Step 7: Run Git hygiene checks**

Run:

```powershell
git diff --check origin/main...HEAD
git status -sb
git lfs ls-files
```

Expected: diff check clean, only intentional files in branch diff, and `third_party/ffmpeg/ffmpeg.exe` is the LFS-tracked binary.

- [ ] **Step 8: Push PR branch**

Run:

```powershell
git push
```

Expected: PR #148 updates successfully. Keep PR #148 draft until review confirms the minimal binary and source-bundle validation are correct.
