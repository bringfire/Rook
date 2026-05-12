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
| 1 | Version bump (6 files / 8 edits) | Grep verification fails |
| 2 | Build C++ native plugin | Exit code != 0 |
| 3 | Build C# companion plugin | Exit code != 0 |
| 4 | Verify all .iss source paths | Any file missing or stale |
| 5 | Run ISCC compiler | Exit code != 0 or output missing |
| 6 | Commit & push | Push fails |
| 7 | Create GitHub release | gh command fails |

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
thumbnail and frame sidecar extraction. Before building an installer, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\validate-ffmpeg-bundle.ps1
```

The guard fails closed for missing metadata, checksum mismatch, GPL/nonfree
configure flags, stale dependency-manifest coverage, missing compliance files,
or failure to extract poster, first-frame, and last-frame JPEGs from the smoke
fixture. PATH-discovered FFmpeg is allowed for development smoke only and cannot
satisfy release validation.

## Step 1: Version Bump

Read the reference file for exact locations and patterns:

```
Read references/version-locations.md
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

Expect 6 string matches (`pyproject.toml`, `RookSetup.iss`, `Rook.csproj`, the two
string values in `RookNative.rc`, `RookNativePlugin.cpp`, and `RookServer.cpp`).
Then verify the binary version lines in `RookNative.rc` separately.

## Step 2: Build C++ Native Plugin

Write an ephemeral batch file and execute it from PowerShell:

```powershell
$buildBat = Join-Path $env:TEMP "rook_build_native_release.bat"
@'
@echo off
set "VSCMD_START_DIR=%CD%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
set VCToolsVersion=14.44.35207
msbuild "%~1" /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207 /m /v:minimal
echo EXIT_CODE=%ERRORLEVEL%
'@ | Set-Content -Path $buildBat -Encoding ASCII

& $buildBat "C:\Users\aryan\source\repos\Rook\src\RookNative\RookNative.vcxproj" 2>&1 |
  Select-String -Pattern "EXIT_CODE|Build succeeded|Build FAILED|error MSB|error C[0-9]"
```

**Key gotchas:**
- Must call vcvarsall.bat FIRST — without it, MSBuild can't find MFC headers
- Must set VCToolsVersion=14.44.35207 explicitly — the default may pick a toolset without MFC
- Must use a .bat file — bash can't source vcvarsall.bat directly
- The /p: flags with forward slashes get mangled by bash — route through .bat to avoid this

Verify: `EXIT_CODE=0` in output and file exists:
```powershell
Test-Path src\RookNative\bin\Release\x64\RookNative.rhp
```

## Step 3: Build C# Companion Plugin

Call `dotnet build` directly (C# doesn't need MFC):

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 -c Release
```

**Key gotcha:** The release installer must package the net7.0 companion output.
Do not package or register older framework outputs.

Verify:
```powershell
Test-Path src\Rook\bin\Release\net7.0\Rook.rhp
Test-Path src\Rook\bin\Release\net7.0\Rook.deps.json
Test-Path src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json
Test-Path src\Rook\bin\Release\net7.0\runtimes
```

## Step 4: Verify All .iss Source Paths

Read the reference file for the full checklist:

```
Read references/iss-source-paths.md
```

Every file listed there must exist. Additionally, verify build outputs are **newer than
the version bump** (not stale from a previous build).

## Step 5: Run Inno Setup Compiler

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

## Step 6: Commit & Push

```powershell
# Stage only the version-bumped files
git add mcp_server\pyproject.toml installer\RookSetup.iss src\Rook\Rook.csproj src\RookNative\RookNative.rc src\RookNative\RookNativePlugin.cpp src\RookNative\RookServer.cpp

git commit -m "release: bump versions to X.Y.Z"

git push origin main
```

## Step 7: GitHub Release

```powershell
gh release create vX.Y.Z "installer/output/Rook-Setup-X.Y.Z.exe" --title "Rook vX.Y.Z" --generate-notes
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
| C# output at wrong path | Installer expects the dotnet net7.0 output | Build with `dotnet build src\Rook\Rook.csproj -f net7.0 -c Release`; output is at `bin\Release\net7.0\` |
| MSBuild `/p:` flags ignored | Bash mangles forward-slash flags | Use .bat file or quote as `"-p:Configuration=Release"` |
| ISCC can't find source file | Path mismatch in .iss | Check CompanionDir matches actual build output path |
| `error MSB1008: Only one project` | MSBuild.exe invoked from bash with /p flags | Bash interprets /p as a path; use `-p:` or route through .bat |
| DLL locked / access denied | Rhino has the plugin loaded | Close Rhino before building |
| Installer too small (<5MB) | Missing knowledge stores or Chirp | Verify all .iss source paths in Step 4 |
