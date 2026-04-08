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
| 1 | Version bump (7 files) | Grep verification fails |
| 2 | Build C++ native plugin | Exit code != 0 |
| 3 | Build C# companion plugin | Exit code != 0 |
| 4 | Verify all .iss source paths | Any file missing or stale |
| 5 | Run ISCC compiler | Exit code != 0 or output missing |
| 6 | Commit & push | Push fails |
| 7 | Create GitHub release | gh command fails |

**HARD RULE: Abort the entire pipeline on any step failure. No partial releases.**

## Step 0: Pre-flight Checks

Run all of these before touching any files:

```bash
# 1. Parse version from argument — must match X.Y.Z
echo "$VERSION" | grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$'

# 2. Clean git status (no uncommitted changes)
git status --porcelain

# 3. Rhino not running (would lock DLLs)
tasklist | grep -i rhinoceros || echo "Rhino not running - OK"

# 4. VS build tools exist
ls "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Auxiliary/Build/vcvarsall.bat"

# 5. MFC libraries exist for the required toolset
ls "C:/Program Files/Microsoft Visual Studio/2022/Community/VC/Tools/MSVC/14.44.35207/atlmfc/"

# 6. Inno Setup exists
ls "C:/Program Files (x86)/Inno Setup 6/ISCC.exe"

# 7. Chirp sibling repo exists
ls "../Chirp/pyproject.toml"
```

If Rhino is running, tell the user to close it — DLL locks will cause build failures.
If git is dirty, tell the user to commit or stash first.

## Step 1: Version Bump

Read the reference file for exact locations and patterns:

```
Read references/version-locations.md
```

Update all 7 files using the Edit tool. The .rc file requires 4 separate edits
(FILEVERSION binary, PRODUCTVERSION binary, FileVersion string, ProductVersion string).

After all edits, verify with:

```bash
grep -rn "X.Y.Z" --include="*.toml" --include="*.iss" --include="*.csproj" --include="*.rc" --include="*.cpp" --include="*.py" installer/ mcp_server/pyproject.toml src/
```

Expect 8 matches (the .rc file has 4). If count differs, stop and investigate.

## Step 2: Build C++ Native Plugin

Write an ephemeral batch file and execute it:

```bash
cat > /tmp/rook_build.bat << 'BEOF'
@echo off
set "VSCMD_START_DIR=%CD%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
set VCToolsVersion=14.44.35207
msbuild "%~1" /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207 /m /v:minimal
echo EXIT_CODE=%ERRORLEVEL%
BEOF

"/tmp/rook_build.bat" "c:\\Users\\aryan\\source\\repos\\Rook\\src\\RookNative\\RookNative.vcxproj" 2>&1 | grep -E "(EXIT_CODE|Build succeeded|Build FAILED|error MSB|error C[0-9])"
```

**Key gotchas:**
- Must call vcvarsall.bat FIRST — without it, MSBuild can't find MFC headers
- Must set VCToolsVersion=14.44.35207 explicitly — the default may pick a toolset without MFC
- Must use a .bat file — bash can't source vcvarsall.bat directly
- The /p: flags with forward slashes get mangled by bash — route through .bat to avoid this

Verify: `EXIT_CODE=0` in output and file exists:
```bash
ls -la src/RookNative/bin/Release/x64/RookNative.rhp
```

## Step 3: Build C# Companion Plugin

Reuse the same batch file approach, or call MSBuild directly (C# doesn't need MFC):

```bash
"C:/Program Files/Microsoft Visual Studio/2022/Community/MSBuild/Current/Bin/MSBuild.exe" \
  "src\\Rook\\Rook.csproj" \
  "-p:Configuration=Release" "-p:Platform=x64" "-p:TargetFramework=net48" "-v:minimal" \
  2>&1 | grep -E "(EXIT_CODE|Build succeeded|Build FAILED|error MSB|Rook ->)"
```

Or append the C# build to the same .bat file from Step 2 (preferred — keeps vcvarsall active).

**Key gotcha:** With `/p:Platform=x64`, the output goes to `bin\x64\Release\net48\`,
NOT `bin\Release\net48\`. The .iss file's CompanionDir must point to the correct path.

Verify:
```bash
ls -la src/Rook/bin/x64/Release/net48/Rook.rhp
```

## Step 4: Verify All .iss Source Paths

Read the reference file for the full checklist:

```
Read references/iss-source-paths.md
```

Every file listed there must exist. Additionally, verify build outputs are **newer than
the version bump** (not stale from a previous build).

## Step 5: Run Inno Setup Compiler

```bash
"C:/Program Files (x86)/Inno Setup 6/ISCC.exe" "c:\\Users\\aryan\\source\\repos\\Rook\\installer\\RookSetup.iss" 2>&1
```

Check the tail of the output for `Successful compile`. Verify:

```bash
ls -la installer/output/Rook-Setup-X.Y.Z.exe
```

Sanity check: file size should be > 5MB (current baseline is ~12MB). If significantly
smaller, something was excluded.

## Step 6: Commit & Push

```bash
# Stage only the version-bumped files
git add \
  mcp_server/pyproject.toml \
  installer/RookSetup.iss \
  installer/post_install.py \
  src/Rook/Rook.csproj \
  src/RookNative/RookNative.rc \
  src/RookNative/RookNativePlugin.cpp \
  src/RookNative/RookServer.cpp

git commit -m "$(cat <<'EOF'
release: Bump all versions to X.Y.Z

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"

git push origin main
```

## Step 7: GitHub Release

```bash
gh release create vX.Y.Z \
  "installer/output/Rook-Setup-X.Y.Z.exe" \
  --title "Rook vX.Y.Z" \
  --generate-notes
```

Report the release URL to the user when done.

## Cleanup

Delete the ephemeral .bat file:
```bash
rm -f /tmp/rook_build.bat
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `error MSB8041: MFC libraries are required` | vcvarsall.bat not sourced, or wrong VCToolsVersion | Must call vcvarsall.bat before msbuild, and set VCToolsVersion=14.44.35207 |
| C# output at wrong path | Platform=x64 changes output dir | Output is at `bin\x64\Release\net48\`, not `bin\Release\net48\` |
| MSBuild `/p:` flags ignored | Bash mangles forward-slash flags | Use .bat file or quote as `"-p:Configuration=Release"` |
| ISCC can't find source file | Path mismatch in .iss | Check CompanionDir matches actual build output path |
| `error MSB1008: Only one project` | MSBuild.exe invoked from bash with /p flags | Bash interprets /p as a path; use `-p:` or route through .bat |
| DLL locked / access denied | Rhino has the plugin loaded | Close Rhino before building |
| Installer too small (<5MB) | Missing knowledge stores or Chirp | Verify all .iss source paths in Step 4 |
