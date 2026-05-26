---
name: build-release
description: |
  Build and release the full Rook plugin suite (C++ native, C# companion,
  Python MCP, Chirp, knowledge stores) as a Windows installer. Use when user
  mentions: build release, package release, bump version, build installer,
  ship it, make a release, cut a release, build the plugins, package for release,
  create installer, ISCC, Inno Setup, version bump. Requires a semver version
  string (X.Y.Z).
---

# Build & Release

Build the full Rook plugin suite and produce a Windows installer.

## Usage

```
/build-release 1.2.3
```

The argument is a semver version (X.Y.Z). If omitted, ask the user.

## Pipeline Overview

| Step | Action | Abort if |
|------|--------|----------|
| 0 | Pre-flight checks | Any check fails |
| 1 | Release branch version bump (6 files / 8 edits) | Verification fails |
| 2 | Merge the release PR and check out the exact main SHA to tag | Main HEAD is not the intended release commit |
| 3 | Build and validate bundled FFmpeg payload/source bundle | Validation fails |
| 4 | Build C++ native plugin | Exit code != 0 |
| 5 | Build C# companion plugin for all managed runtimes | Exit code != 0 |
| 6 | Verify all .iss source paths | Any required file missing or stale |
| 7 | Run ISCC compiler | Exit code != 0 or output missing |
| 8 | Installer live smoke + release artifact validation manifest | Smoke or validation fails |
| 9 | Create GitHub release with all required assets | gh command fails |

**HARD RULE: Abort the entire pipeline on any step failure. No partial releases.**

## Step 0: Pre-flight Checks

Run all of these before touching any files:

```powershell
# 1. Parse version from argument - must match X.Y.Z
if ($VERSION -notmatch '^[0-9]+\.[0-9]+\.[0-9]+$') { throw "Version must be X.Y.Z" }

# 2. Clean git status (no uncommitted changes)
$dirty = git status --porcelain
if ($dirty) { git status --short; throw "Working tree is dirty" }

# 3. Rhino not running (would lock DLLs)
$rhino = Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
if ($rhino) { $rhino | Select-Object ProcessName, Id; throw "Close Rhino before building" }

# 4. VS build tools exist
$requiredPaths = @(
  "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat",
  "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\atlmfc",
  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
  "..\Chirp\pyproject.toml"
)

foreach ($path in $requiredPaths) {
  if (-not (Test-Path $path)) { throw "Missing required release path: $path" }
}
```

If Rhino is running, tell the user to close it — DLL locks will cause build failures.
If git is dirty, tell the user to commit or stash first.

### Bundled FFmpeg

Rook release installers bundle an LGPL-only `ffmpeg.exe` for generated-video
thumbnail and frame sidecar extraction. The bundled binary must be produced from
the committed Rook minimal build recipe, and the release source bundle generated
by that recipe must be staged and published beside the installer.

Before building an installer, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ffmpeg\build-rook-ffmpeg.ps1 -InstallPayload
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json
```

The guard fails closed for missing metadata, checksum mismatch, GPL/nonfree
configure flags, unexpected `--enable-*` flags outside
`scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json`, unverified official source
signatures from `scripts\ffmpeg\rook-ffmpeg-source.json`, missing compliance
files, missing source-bundle manifest/content, or failure to extract poster,
first-frame, and last-frame JPEGs from the required smoke fixtures.
PATH-discovered FFmpeg is allowed for development smoke only and cannot satisfy
release validation.

## Step 1: Release Branch Version Bump

Read the reference file for exact locations and patterns:

```
Read references/version-locations.md
```

Create a release branch from updated `main` before editing:

```powershell
git switch main
git pull --ff-only origin main
git switch -c release/vX.Y.Z
```

Update all 6 files using the Edit tool. The .rc file requires 4 separate edits
(FILEVERSION binary, PRODUCTVERSION binary, FileVersion string, ProductVersion string).

After all edits, verify with:

```powershell
Select-String -Path `
  mcp_server\pyproject.toml, `
  installer\RookSetup.iss, `
  src\Rook\Rook.csproj, `
  src\RookNative\RookNative.rc, `
  src\RookNative\RookNativePlugin.cpp, `
  src\RookNative\RookServer.cpp `
  -Pattern "X.Y.Z"
```

Expect 7 string matches (`pyproject.toml`, `RookSetup.iss`, `Rook.csproj`, the two
string values in `RookNative.rc`, `RookNativePlugin.cpp`, and `RookServer.cpp`).
Then verify the binary version lines in `RookNative.rc` separately.

Commit and push only the version-bumped files on the release branch:

```powershell
git add mcp_server\pyproject.toml installer\RookSetup.iss src\Rook\Rook.csproj src\RookNative\RookNative.rc src\RookNative\RookNativePlugin.cpp src\RookNative\RookServer.cpp
git commit -m "release: bump versions to X.Y.Z"
git push -u origin release/vX.Y.Z
```

Open a release PR and merge it before building publishable artifacts. Do not
publish artifacts built from a branch SHA if the PR creates a different merge
commit.

## Step 2: Check Out Exact Release SHA

After the release PR is merged, update local `main` and record the exact commit
that will be tagged. All publishable artifacts must be built from this SHA.

```powershell
git switch main
git pull --ff-only origin main
$gitSha = (git rev-parse HEAD).Trim()
$buildStartedAt = [DateTimeOffset]::Now.ToString('o')
```

If the commit changes after any artifact is built, discard those artifacts,
rebuild from the new `main` SHA, rerun smoke, and regenerate the release
manifest.

## Step 3: Build and Validate Bundled FFmpeg

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ffmpeg\build-rook-ffmpeg.ps1 -InstallPayload
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json
```

## Step 4: Build C++ Native Plugin

Write an ephemeral batch file and execute it from PowerShell:

```powershell
$buildBat = Join-Path $env:TEMP "rook_build_native_release.bat"
@'
@echo off
set "VSCMD_START_DIR=%CD%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 -vcvars_ver=14.44
set VCToolsVersion=14.44.35207
msbuild "%~1" /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207 /m /v:minimal
echo EXIT_CODE=%ERRORLEVEL%
'@ | Set-Content -Path $buildBat -Encoding ASCII

& $buildBat "C:\Users\aryan\source\repos\Rook\src\RookNative\RookNative.vcxproj" 2>&1 |
  Select-String -Pattern "EXIT_CODE|Build succeeded|Build FAILED|error MSB|error C[0-9]"
```

**Key gotchas:**
- Must call vcvarsall.bat FIRST with `-vcvars_ver=14.44` — without it, MSBuild can pick the incomplete 14.38 MFC payload
- Must set VCToolsVersion=14.44.35207 explicitly — the default may pick a toolset without MFC
- Must use a .bat file — bash can't source vcvarsall.bat directly
- The /p: flags with forward slashes get mangled by bash — route through .bat to avoid this

Verify: `EXIT_CODE=0` in output and file exists:
```powershell
Test-Path src\RookNative\bin\Release\x64\RookNative.rhp
```

## Step 5: Build C# Companion Plugin

Call `dotnet build` directly (C# doesn't need MFC):

```powershell
dotnet build src\Rook\Rook.csproj -c Release
```

**Key gotcha:** The release installer must package all companion runtime
outputs. Rhino 8 standalone loads a .NET Core payload; Rhino.Inside.Revit on
Revit 2025+ needs the sibling `net8.0` payload, and .NET Framework hosts need
the sibling `net48` payload. The Inno direct-registry sibling layout is a
release hypothesis, not proof; only the live Inno-install smoke can prove Rhino
redirected from the registered child to the physical runtime sibling.

Verify:
```powershell
Test-Path src\Rook\bin\Release\net8.0\Rook.rhp
Test-Path src\Rook\bin\Release\net8.0\Rook.deps.json
Test-Path src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json
Test-Path src\Rook\bin\Release\net8.0\runtimes
Test-Path src\Rook\bin\Release\net7.0\Rook.rhp
Test-Path src\Rook\bin\Release\net7.0\Rook.deps.json
Test-Path src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json
Test-Path src\Rook\bin\Release\net7.0\runtimes
Test-Path src\Rook\bin\Release\net48\Rook.rhp
Test-Path src\Rook\bin\Release\net48\runtimes
```

## Step 6: Verify All .iss Source Paths

Read the reference file for the full checklist:

```
Read references/iss-source-paths.md
```

Every required file listed there must exist. Additionally, verify build outputs
are **newer than the version bump** (not stale from a previous build).

## Step 7: Run Inno Setup Compiler

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "C:\Users\aryan\source\repos\Rook\installer\RookSetup.iss"
```

Check the tail of the output for `Successful compile`. Verify:

```powershell
$installer = Get-Item installer\output\Rook-Setup-X.Y.Z.exe
$installer.Length
```

Sanity check: file size should be > 5MB (current baseline is ~12MB). If significantly
smaller, something was excluded.

## Step 8: Installer Live Smoke and Artifact Validation

Install the generated EXE on the release machine and verify both Rhino hosts:

```powershell
# Standalone Rhino smoke
python scripts\run_rhino_runtime_harness.py --smoke ping-only

# Manual release gate
# 1. Launch Revit with Rhino.Inside.Revit.
# 2. Start Rhino from the Rhino.Inside.Revit tab.
# 3. Confirm RookNative and Rook load without CLR binding or TypeLoad errors.
# 4. Run a non-mutating Rook ping from the discovered native port.
# 5. Record the managed companion self-report from %LOCALAPPDATA%\Rook\discovery\companion-<pid>.json.
```

Do not publish the installer if the Rhino.Inside.Revit smoke was not run or did
not pass. Do not cite Yak/package-manager layout docs as proof for this Inno
installer shape. Record the Rhino, Revit, Rhino.Inside.Revit, Rook versions,
and companion self-report evidence in the release notes. Do not use registry
`FileName` values or `Get-Process.Modules` absence as proof of managed
companion load.

Write a structured smoke manifest at `installer\output\release-smoke-X.Y.Z.json`
with at least:

```
git_sha
installer_sha256
rook_version
smoke_started_utc
standalone_rhino:
  rhino_version
  host_runtime
  native_port
  ping_result
  plugin_manager_listed
  chat_service_manifest_path
  chat_service_health
  loaded_native_path
  companion_self_report:
    processId
    processName
    rhinoInside
    assemblyLocation
    runtimeChild
    targetFramework
    startupGateAttached
    deferredLocalStartupComplete
    startupComplete
    bridgeRegistered
    onLoadUtc
    startupCompleteUtc
    statusUpdatedUtc
rhino_inside_revit:
  rhino_version
  revit_version
  rhino_inside_version
  host_runtime
  native_port
  ping_result
  plugin_manager_listed
  chat_service_manifest_path
  chat_service_health
  loaded_native_path
  companion_self_report:
    processId
    processName
    rhinoInside
    assemblyLocation
    runtimeChild
    targetFramework
    startupGateAttached
    deferredLocalStartupComplete
    startupComplete
    bridgeRegistered
    onLoadUtc
    startupCompleteUtc
    statusUpdatedUtc
```

Then validate artifact identity and emit the release manifest:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-release-artifacts.ps1 `
  -Version X.Y.Z `
  -GitSha $gitSha `
  -InstallerPath installer\output\Rook-Setup-X.Y.Z.exe `
  -FfmpegSourceBundleManifestPath artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json `
  -SmokeManifestPath installer\output\release-smoke-X.Y.Z.json `
  -OutputManifestPath installer\output\release-manifest-X.Y.Z.json `
  -BuildStartedAt $buildStartedAt
```

The release manifest must include `git_sha`, `installer_sha256`,
`ffmpeg_source_bundle_sha256`, and smoke evidence. Do not create the GitHub
release if validation fails.

## Step 9: GitHub Release

Attach the installer, FFmpeg source bundle zip, FFmpeg source-bundle manifest,
smoke manifest, and release manifest:

```powershell
$sourceBundleManifestPath = "artifacts\ffmpeg\ffmpeg-8.1.1-rook-minimal\rook-ffmpeg-source-bundle-manifest.json"
$sourceBundleZip = (Get-Content $sourceBundleManifestPath -Raw | ConvertFrom-Json).bundle_path
if ((Split-Path -Leaf $sourceBundleZip) -ne "rook-ffmpeg-8.1.1-source-bundle.zip") { throw "Unexpected FFmpeg source bundle path: $sourceBundleZip" }

gh release create vX.Y.Z `
  "installer/output/Rook-Setup-X.Y.Z.exe" `
  $sourceBundleZip `
  $sourceBundleManifestPath `
  "installer/output/release-smoke-X.Y.Z.json" `
  "installer/output/release-manifest-X.Y.Z.json" `
  --target $gitSha `
  --title "Rook vX.Y.Z" `
  --generate-notes
```

Report the release URL to the user when done.

## Cleanup

Delete the ephemeral .bat file:
```powershell
Remove-Item (Join-Path $env:TEMP "rook_build_native_release.bat") -Force -ErrorAction SilentlyContinue
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `error MSB8041: MFC libraries are required` | vcvarsall.bat not sourced, or wrong VCToolsVersion | Must call vcvarsall.bat before msbuild, and set VCToolsVersion=14.44.35207 |
| C# output at wrong path | Installer expects sibling net8.0, net7.0, and net48 outputs | Build with `dotnet build src\Rook\Rook.csproj -c Release`; outputs are at `bin\Release\net8.0\`, `bin\Release\net7.0\`, and `bin\Release\net48\` |
| MSBuild `/p:` flags ignored | Bash mangles forward-slash flags | Use .bat file or quote as `"-p:Configuration=Release"` |
| ISCC can't find source file | Path mismatch in .iss | Check CompanionDir matches actual build output path |
| `error MSB1008: Only one project` | MSBuild.exe invoked from bash with /p flags | Bash interprets /p as a path; use `-p:` or route through .bat |
| DLL locked / access denied | Rhino has the plugin loaded | Close Rhino before building |
| Installer too small (<5MB) | Missing knowledge stores or Chirp | Verify all .iss source paths in Step 4 |
