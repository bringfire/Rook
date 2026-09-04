# Inno Setup Source Path Checklist

Every required file listed here is referenced by `installer/RookSetup.iss`. If any file
is missing, ISCC will either fail or silently exclude the component (if
`skipifsourcedoesntexist` is set).

Unless marked as a build-machine prerequisite, paths are relative to the repo root.

## Qualified Prime Runtime Payload

`PrimeRuntimePayload` is an explicit canonical assembly-attempt
`runtimes/<runtime-id>` directory, not a source checkout or a global installation.
The sealed-wheel verification Python must verify the complete closed manifest
before ISCC receives `/DPrimeRuntimePayload=<path>`. Inno copies the whole tree
only to its unique `prime/.incoming` generation. Installed Rook promotion owns
final runtime publication and `current.json`; file-copy rules never write them.

| Required relative path | Producer |
| --- | --- |
| `pi.exe` | Complete upstream Windows ZIP |
| `skills/goal/SKILL.md` | Complete upstream skills |
| `dist/prime-agent-runtime/**` | Complete upstream Python runtime subtree |
| `skills/rook-full/**` | Tracked Rook Markdown skill |
| `tools/uv/uv.exe` | Preadmitted official uv archive |
| `tools/uv/LICENSE-APACHE` and `tools/uv/LICENSE-MIT` | Preadmitted uv notices |
| `notices/prime-agent/LICENSE` | Reviewed tracked Prime legal notice |
| `runtime-manifest.json` | Rook Windows assembly over all payload bytes |

These paths are a checklist, not a selected-file copy list. WSL, Node, npm, Bun,
zip, unzip, and build scripts do not become customer prerequisites.

## Build Outputs (must be fresh — rebuilt after version bump)

| File | Source |
|------|--------|
| `src/RookNative/bin/Release/x64/RookNative.rhp` | C++ build output |
| `src/RookNative/bin/Release/x64/RookNative.pdb` | Optional C++ debug symbols; installer uses `skipifsourcedoesntexist` |
| `src/Rook/bin/Release/net8.0/Rook.rhp` | C# .NET 8 build output |
| `src/Rook/bin/Release/net8.0/Rook.deps.json` | C# .NET 8 dependency manifest |
| `src/Rook/bin/Release/net8.0/Rook.runtimeconfig.json` | C# runtime metadata; must declare net8.0 |
| `src/Rook/bin/Release/net8.0/*.dll` | C# .NET 8 dependency DLLs |
| `src/Rook/bin/Release/net8.0/runtimes/` | C# .NET 8 runtime assets |
| `src/Rook/bin/Release/net7.0/Rook.rhp` | C# .NET Core build output |
| `src/Rook/bin/Release/net7.0/Rook.deps.json` | C# .NET Core dependency manifest |
| `src/Rook/bin/Release/net7.0/Rook.runtimeconfig.json` | C# runtime metadata; must declare net7.0 |
| `src/Rook/bin/Release/net7.0/*.dll` | C# .NET Core dependency DLLs |
| `src/Rook/bin/Release/net7.0/runtimes/` | C# .NET Core runtime assets |
| `src/Rook/bin/Release/net48/Rook.rhp` | C# .NET Framework build output for Rhino.Inside.Revit hosts |
| `src/Rook/bin/Release/net48/RookBim.dll` | RookBIM Rhino.Inside/Revit module; produced by `src/RookBim/RookBim.csproj` post-build copy |
| `src/Rook/bin/Release/net48/*.dll` | C# .NET Framework dependency DLLs |
| `src/Rook/bin/Release/net48/runtimes/` | C# .NET Framework runtime assets, including WebView2 native loader |

**CRITICAL:** The installer must package sibling `net8.0`, `net7.0`, and `net48`
companion outputs. The registry `FileName` points at the `net7.0` child RHP.
For direct registry installs, sibling-runtime redirection is not release-proven
by package-manager/Yak layout docs. The live Inno-install smoke must prove which
physical `Rook.rhp` path Rhino loads under standalone Rhino, Rhino.Inside.Revit
on Revit 2025+, and Rhino.Inside.Revit on Revit 2024 or older.

## Native VC Runtime Payload (build-machine prerequisite)

The native plugin is built with dynamic MSVC/MFC runtime linkage, and the public
installer is per-user (`PrivilegesRequired=lowest`). Package the required VC143
runtime DLLs app-local beside `RookNative.rhp`; do not rely on a machine-wide
Visual C++ Redistributable already being installed.

Default source root:
`C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Redist\MSVC\14.44.35112\x64`

| File | Source |
|------|--------|
| `Microsoft.VC143.CRT\concrt140.dll` | VS 14.44 x64 redistributable payload |
| `Microsoft.VC143.CRT\msvcp140.dll` | VS 14.44 x64 redistributable payload |
| `Microsoft.VC143.CRT\vcruntime140.dll` | VS 14.44 x64 redistributable payload |
| `Microsoft.VC143.CRT\vcruntime140_1.dll` | VS 14.44 x64 redistributable payload |
| `Microsoft.VC143.MFC\mfc140.dll` | VS 14.44 x64 redistributable payload |
| `Microsoft.VC143.MFC\mfc140u.dll` | VS 14.44 x64 redistributable payload |

## Native OCCT Runtime Payload (build-machine prerequisite)

The native plugin directly imports the OCCT runtime DLLs used by the exact
topology/adjacency code. Package these DLLs app-local beside `RookNative.rhp`;
do not rely on a prior developer deploy, PATH entry, or machine-wide OCCT
installation.

Default source root:
`C:\Users\aryan\source\repos\OCCT\build-rook\win64\vc14\bin`

| File | Source |
|------|--------|
| `TKernel.dll` | OCCT 8 runtime payload |
| `TKMath.dll` | OCCT 8 runtime payload |
| `TKG2d.dll` | OCCT 8 runtime payload |
| `TKG3d.dll` | OCCT 8 runtime payload |
| `TKGeomBase.dll` | OCCT 8 runtime payload |
| `TKGeomAlgo.dll` | OCCT 8 runtime payload |
| `TKBRep.dll` | OCCT 8 runtime payload |
| `TKTopAlgo.dll` | OCCT 8 runtime payload |
| `TKPrim.dll` | OCCT 8 runtime payload |
| `TKBO.dll` | OCCT 8 runtime payload |
| `TKShHealing.dll` | OCCT 8 runtime payload |

## Python MCP Server

| File/Dir | Notes |
|----------|-------|
| `mcp_server/pyproject.toml` | Package definition |
| `mcp_server/README.md` | Package readme |
| `mcp_server/src/rook/` | Full source tree (recursesubdirs) |

## Chirp Adapter (sibling repo)

| File/Dir | Notes |
|----------|-------|
| `../Chirp/pyproject.toml` | Chirp package definition |
| `../Chirp/src/chirp/` | Chirp source tree (recursesubdirs) |

The .iss references `ChirpDir = RepoRoot + "\..\Chirp"`. This is a sibling repo
at the same directory level as Rook.

## Bundled Python Runtime Payload

Installer Source paths must include the staged private CPython runtime and the
offline, hash-locked wheelhouse generated from the exact release SHA. Public
installer builds must not depend on user Python, PyPI, editable installs, or
source-tree `PYTHONPATH` entries.

| File/Dir | Notes |
|----------|-------|
| `installer/runtime/python/cpython-3.11.9/python.exe` | Private CPython runtime staged from the pinned official Python NuGet package |
| `installer/runtime/python/cpython-3.11.9/Lib/` | Private runtime standard library |
| `installer/runtime/python-wheelhouse/` | Union wheelhouse; wheels only, no sdists |
| `installer/runtime/requirements-bootstrap-lock.txt` | Fully pinned hash-locked pip/setuptools bootstrap requirements |
| `installer/runtime/requirements-rook-lock.txt` | Fully pinned hash-locked Rook MCP/chat requirements |
| `installer/runtime/requirements-chirp-lock.txt` | Fully pinned hash-locked Chirp requirements |
| `installer/runtime/python-runtime-manifest.json` | Runtime, wheelhouse, lockfile, audit, license/provenance, source provenance, and import-origin manifest |
| `installer/python_runtime_install.py` | Stdlib post-install helper for private runtime installs |

## Bundled FFmpeg Payload

Installer Source paths must include `third_party\ffmpeg` and package the
LGPL-only subprocess payload plus its compliance files. The release source
bundle is not installed with the plugin; it is generated by
`scripts\ffmpeg\build-rook-ffmpeg.ps1`, validated with
`scripts\validate-ffmpeg-bundle.ps1 -SourceBundleManifestPath ...`, and
published beside the installer.

| File | Notes |
|------|-------|
| `third_party/ffmpeg/ffmpeg.exe` | Rook-owned minimal LGPL-only Windows FFmpeg binary |
| `third_party/ffmpeg/ffmpeg-provenance.json` | Machine-readable provenance, checksum, version, configure, source-bundle, and fixture metadata |
| `third_party/ffmpeg/LICENSE.FFmpeg.txt` | License file for the bundled payload |
| `third_party/ffmpeg/NOTICE.FFmpeg.txt` | Attribution and notice text |
| `third_party/ffmpeg/SOURCE.FFmpeg.txt` | Corresponding source-compliance information |
| `third_party/ffmpeg/README.md` | Installed payload summary |

The committed recipe and policy files are release inputs and must also exist:

| File | Notes |
|------|-------|
| `scripts/ffmpeg/build-rook-ffmpeg.ps1` | Generates the minimal binary payload and release source bundle |
| `scripts/ffmpeg/rook-ffmpeg-configure.txt` | Minimal configure recipe |
| `scripts/ffmpeg/rook-ffmpeg-enable-allowlist.json` | Machine-readable allowed `--enable-*` policy |
| `scripts/ffmpeg/rook-ffmpeg-source.json` | Pinned source URL, hash, signature URL, and signing-key fingerprint |
| `scripts/validate-ffmpeg-bundle.ps1` | Release validation guard; must be run with `-SourceBundleManifestPath` |

## Knowledge Stores

| Dir | Notes |
|-----|-------|
| `knowledge/commands/` | Must be non-empty (196+ Rhino command files) |
| `knowledge/gh/` | Must be non-empty; excludes `sessions/` subdir |

## Claude / Codex Agent Assets

| File/Dir | Notes |
|----------|-------|
| `installer/agent-assets/codex-skills/` | Curated Codex skill payload (recursesubdirs) |
| `installer/agent-assets/ROOK_CLAUDE_POST_INSTALL.md` | Post-install agent prompt |
| `installer/agent-assets/ROOK_CODEX_POST_INSTALL.md` | Post-install agent prompt |

## Installer Assets

| File | Notes |
|------|-------|
| `installer/post_install.py` | Post-install automation |
| `installer/rook-icon.ico` | Application icon |
| `installer/pre-install-readme.txt` | Pre-install information |
| `installer/CLAUDE.md` | Installed Claude instruction file |
| `installer/AGENTS.md` | Installed Codex instruction file |

## Agent-Facing Documentation

These are installed to `{localappdata}\Rook\docs\` and referenced by the
installed CLAUDE.md.

| File | Notes |
|------|-------|
| `docs/ONBOARDING_NEW_CLAUDE.md` | Quick decision tree for tool selection |
| `docs/CURRENT_ARCHITECTURE.md` | Runtime architecture description |
| `docs/AGENT_ARCHITECTURE.md` | Agent system, intent runtime, chat service |
| `docs/TROUBLESHOOTING.md` | Common issues and recovery |

## User Documentation

| File | Notes |
|------|-------|
| `QUICK_START.md` | User quick start guide |
| `AGENT_SETUP.md` | Agent setup guide |

## Verification Script

Run this to check all paths at once:

```powershell
$Repo = "C:\Users\aryan\source\repos\Rook"
$VcRedistRoot = "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Redist\MSVC\14.44.35112\x64"
$OcctRuntimeRoot = "C:\Users\aryan\source\repos\OCCT\build-rook\win64\vc14\bin"
$missing = New-Object System.Collections.Generic.List[string]

$files = @(
  "src\RookNative\bin\Release\x64\RookNative.rhp",
  "src\Rook\bin\Release\net8.0\Rook.rhp",
  "src\Rook\bin\Release\net8.0\Rook.deps.json",
  "src\Rook\bin\Release\net8.0\Rook.runtimeconfig.json",
  "src\Rook\bin\Release\net7.0\Rook.rhp",
  "src\Rook\bin\Release\net7.0\Rook.deps.json",
  "src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json",
  "src\Rook\bin\Release\net48\Rook.rhp",
  "src\Rook\bin\Release\net48\RookBim.dll",
  "mcp_server\pyproject.toml",
  "..\Chirp\pyproject.toml",
  "installer\runtime\python\cpython-3.11.9\python.exe",
  "installer\runtime\requirements-bootstrap-lock.txt",
  "installer\runtime\requirements-rook-lock.txt",
  "installer\runtime\requirements-chirp-lock.txt",
  "installer\runtime\python-runtime-manifest.json",
  "installer\agent-assets\ROOK_CLAUDE_POST_INSTALL.md",
  "installer\agent-assets\ROOK_CODEX_POST_INSTALL.md",
  "installer\post_install.py",
  "installer\python_runtime_install.py",
  "installer\rook-icon.ico",
  "installer\pre-install-readme.txt",
  "installer\CLAUDE.md",
  "installer\AGENTS.md",
  "mcp_server\README.md",
  "third_party\ffmpeg\ffmpeg.exe",
  "third_party\ffmpeg\ffmpeg-provenance.json",
  "third_party\ffmpeg\LICENSE.FFmpeg.txt",
  "third_party\ffmpeg\NOTICE.FFmpeg.txt",
  "third_party\ffmpeg\SOURCE.FFmpeg.txt",
  "third_party\ffmpeg\README.md",
  "scripts\ffmpeg\build-rook-ffmpeg.ps1",
  "scripts\ffmpeg\rook-ffmpeg-configure.txt",
  "scripts\ffmpeg\rook-ffmpeg-enable-allowlist.json",
  "scripts\ffmpeg\rook-ffmpeg-source.json",
  "scripts\validate-ffmpeg-bundle.ps1",
  "docs\ONBOARDING_NEW_CLAUDE.md",
  "docs\CURRENT_ARCHITECTURE.md",
  "docs\AGENT_ARCHITECTURE.md",
  "docs\TROUBLESHOOTING.md",
  "QUICK_START.md",
  "AGENT_SETUP.md"
)

$optionalFiles = @(
  "src\RookNative\bin\Release\x64\RookNative.pdb"
)

foreach ($file in $files) {
  $path = Join-Path $Repo $file
  if (-not (Test-Path $path)) { $missing.Add("MISSING: $path") }
}

foreach ($file in $optionalFiles) {
  $path = Join-Path $Repo $file
  if (-not (Test-Path $path)) { Write-Warning "OPTIONAL MISSING: $path" }
}

$vcRuntimeFiles = @(
  "Microsoft.VC143.CRT\concrt140.dll",
  "Microsoft.VC143.CRT\msvcp140.dll",
  "Microsoft.VC143.CRT\vcruntime140.dll",
  "Microsoft.VC143.CRT\vcruntime140_1.dll",
  "Microsoft.VC143.MFC\mfc140.dll",
  "Microsoft.VC143.MFC\mfc140u.dll"
)

foreach ($file in $vcRuntimeFiles) {
  $path = Join-Path $VcRedistRoot $file
  if (-not (Test-Path $path)) { $missing.Add("MISSING VC RUNTIME: $path") }
}

$occtRuntimeFiles = @(
  "TKernel.dll",
  "TKMath.dll",
  "TKG2d.dll",
  "TKG3d.dll",
  "TKGeomBase.dll",
  "TKGeomAlgo.dll",
  "TKBRep.dll",
  "TKTopAlgo.dll",
  "TKPrim.dll",
  "TKBO.dll",
  "TKShHealing.dll"
)

foreach ($file in $occtRuntimeFiles) {
  $path = Join-Path $OcctRuntimeRoot $file
  if (-not (Test-Path $path)) { $missing.Add("MISSING OCCT RUNTIME: $path") }
}

$directories = @(
  "mcp_server\src\rook",
  "..\Chirp\src\chirp",
  "installer\runtime\python\cpython-3.11.9\Lib",
  "installer\runtime\python-wheelhouse",
  "knowledge\commands",
  "knowledge\gh",
  "installer\agent-assets\codex-skills",
  "src\Rook\bin\Release\net8.0\runtimes",
  "src\Rook\bin\Release\net7.0\runtimes",
  "src\Rook\bin\Release\net48\runtimes"
)

foreach ($directory in $directories) {
  $path = Join-Path $Repo $directory
  if (-not (Test-Path $path) -or -not (Get-ChildItem -Path $path -Force | Select-Object -First 1)) {
    $missing.Add("MISSING OR EMPTY: $path")
  }
}

$net8DllCount = @(Get-ChildItem -Path (Join-Path $Repo "src\Rook\bin\Release\net8.0") -Filter *.dll).Count
if ($net8DllCount -lt 1) { $missing.Add("MISSING: C# net8.0 dependency DLLs") }

$net7DllCount = @(Get-ChildItem -Path (Join-Path $Repo "src\Rook\bin\Release\net7.0") -Filter *.dll).Count
if ($net7DllCount -lt 1) { $missing.Add("MISSING: C# net7.0 dependency DLLs") }

$net48DllCount = @(Get-ChildItem -Path (Join-Path $Repo "src\Rook\bin\Release\net48") -Filter *.dll).Count
if ($net48DllCount -lt 1) { $missing.Add("MISSING: C# net48 dependency DLLs") }

if ($missing.Count -eq 0) {
  "ALL CHECKS PASSED"
} else {
  $missing
  throw "FAILED: $($missing.Count) items missing"
}
```
