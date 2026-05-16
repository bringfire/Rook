# Building Rook from Source

> **For AI agents and developers.** This document contains the exact build chain
> for compiling both Rook plugins from source. Every version, path, and flag is
> grounded in the working build scripts in this repo. If you are an AI agent
> helping a user build Rook, follow these instructions exactly.
>
> **Rook requires [Claude Code](https://code.claude.com)** (CLI, Desktop app, or
> VS Code extension). The older Claude Desktop chat app does not support hooks,
> plugins, or skills. See [AGENT_SETUP.md](AGENT_SETUP.md) for full client requirements.

---

## Prerequisites

### Required Software

| Software | Version | What It Provides | How to Verify |
|----------|---------|-----------------|---------------|
| **Rhino 8 C++ SDK** | 8.x (matches your Rhino) | Headers, libs, and `.props` files for C++ plugin builds | Registry: `reg query "HKLM\SOFTWARE\McNeel\Rhinoceros\SDK\8.0" /v InstallPath` |
| **Visual Studio 2022** | Community, Pro, or Enterprise | MSBuild, C++ compiler, .NET Framework build tools | `ls "C:/Program Files/Microsoft Visual Studio/2022/*/VC/Auxiliary/Build/vcvarsall.bat"` |
| **C++ Desktop workload** | Installed via VS Installer | MSVC v143 toolset, Windows SDK 10.0 | VS Installer > Modify > "Desktop development with C++" checked |
| **MFC libraries** | MSVC v14.44.35207 | Dynamic MFC (required by RookNative) | `ls "C:/Program Files/Microsoft Visual Studio/2022/*/VC/Tools/MSVC/14.44.35207/atlmfc/"` |
| **.NET Framework 4.8** | Targeting pack | C# companion plugin target | `ls "C:/Program Files (x86)/Reference Assemblies/Microsoft/Framework/.NETFramework/v4.8/"` |
| **Python 3.10+** | 3.10, 3.11, 3.12, or 3.13 | MCP server runtime | `python --version` |

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

### Installing the Rhino 8 C++ SDK

The C++ plugin (`RookNative`) imports build properties via a registry key set by
the Rhino 8 SDK installer. **Without the SDK, the build fails immediately** with:

```
error MSB4019: The imported project "PropertySheets\Rhino.Cpp.PlugIn.props" was not found.
```

1. Download the SDK installer (`rh80sdk_*.msi`) from the
   [Rhino Developer page](https://www.rhino3d.com/download/rhino/8/sdk)
2. **Run the MSI as Administrator** — it requires elevated privileges (a non-admin
   install exits silently with error code 1603)
3. Verify the registry key exists:
   ```powershell
   reg query "HKLM\SOFTWARE\McNeel\Rhinoceros\SDK\8.0" /v InstallPath
   ```

### Installing MFC Libraries

MFC is **not installed by default** with the C++ workload. You must add it explicitly:

1. Open **Visual Studio Installer**
2. Click **Modify** on your VS 2022 installation
3. Go to **Individual Components** tab
4. Search for **"MFC"**
5. Check: **C++ MFC for latest v143 build tools (x86 & x64)**
6. Click **Modify** to install

The specific toolset version required is **14.44.35207**. After installing MFC,
verify the directory exists (substitute your edition):

```
C:\Program Files\Microsoft Visual Studio\2022\<edition>\VC\Tools\MSVC\14.44.35207\atlmfc\
```

If this exact version is not available, check what versions you have (substitute
your edition — Community, Professional, or Enterprise):
```powershell
ls "C:\Program Files\Microsoft Visual Studio\2022\<edition>\VC\Tools\MSVC\"
```

If a different version is present (e.g., 14.43.xxxxx), the build will fail with
`error MSB8041: MFC libraries are required`. You need the exact version or must
update the `VCToolsVersion` in the build commands below and in
`scripts/build-native.bat`.

### Why These Specific Versions?

The C++ plugin (`RookNative`) uses **dynamic MFC** (`UseOfMfc=Dynamic` in the
`.vcxproj`) and the **v143 platform toolset**. MFC headers and libraries are
version-locked to a specific MSVC tools version. The build scripts pin
`VCToolsVersion=14.44.35207` to ensure the correct MFC libraries are found.
Without this pin, MSBuild may pick a default toolset that lacks MFC.

### Using Visual Studio 2026 (Preview) or Newer

VS2026 (internal version 18) installs to `C:\Program Files\Microsoft Visual Studio\18\`
instead of `...\2022\`. The automated build scripts (`install.ps1`,
`build_native.ps1`, `scripts\detect-vs.ps1`) currently detect VS 2022 only.
If you only have VS2026:

1. **Install the v143 toolset** — VS2026 ships with v145; the `.vcxproj` requires
   v143. Open VS Installer > Modify > Individual Components > search "MSVC v143" >
   install **"MSVC v143 - VS 2022 C++ x64/x86 build tools (Latest)"**.
2. **Install MFC for v143** — MFC is only available for v141/v142/v143, not v145.
   Install **"C++ MFC for latest v143 build tools (x86 & x64)"** from Individual
   Components.
3. **Patch `scripts\detect-vs.ps1`** — add `\18\Community\` (or your edition) to
   the edition loop, before the `\2022\` entries. All build scripts use this shared
   detection, so one patch fixes all of them.
4. The manual MSBuild commands in this document use `\2022\Community\` in paths —
   substitute your actual VS install path.

---

## Quick Build (Recommended)

If you just want to build everything and install:

```powershell
# From the repo root
powershell -ExecutionPolicy Bypass -File install.ps1
```

This script:
- Creates a Python venv and installs the MCP server
- Builds the **C++ native** plugin via `build_native.ps1`
- Builds the **C# companion** plugin via `dotnet build`
- Deploys plugins to the Rhino plugin directory
- Registers plugins with Rhino via registry scripts
- Writes MCP configuration for Claude Code, Codex, and Claude Desktop
- Writes `install-summary.json` with structured step results

**`install.ps1` builds both plugins** when prerequisites are met. It dot-sources
`scripts\detect-vs.ps1` for toolchain detection and calls `build_native.ps1`
for C++. If VS or MFC is missing, it skips the C++ build with a diagnostic
message and continues with the C# plugin and MCP server.

### Agent Flags

| Flag | Effect |
|------|--------|
| `-DryRun` | Check prerequisites and report planned actions. Zero side effects. |
| `-Json` | Print final `install-summary.json` to stdout. |
| `-RequireNative` | Exit `1` if C++ prerequisites are missing (default: skip gracefully). |
| `-SkipNative` | Don't attempt C++ build. |
| `-SkipChirp` | Don't set up the Chirp LLM adapter. |
| `-SkipConfig` | Don't write MCP client configs. |
| `-NoVerify` | Skip the final verification pass. |
| `-VCToolsVersion <ver>` | Override the MSVC toolset version for native build. |
| `-SummaryPath <path>` | Override location of `install-summary.json`. |

### Exit Codes

| Code | Meaning |
|------|---------|
| `0` | Fully functional. `rhino_ping` will work. |
| `1` | Hard failure. Nothing usable. |
| `2` | Partial install. Runtime/config may exist but Rhino bridge is **not functional**. |

### Summary File

`install-summary.json` (in the repo root by default) is written incrementally
after each step. Key fields:

- **`rhino_bridge_functional`** — can `rhino_ping` work? Depends only on native
  plugin readiness (built + deployed + registered).
- **`full_stack_functional`** — native + companion both ready (GH + chat + all tools).
- **`exit_code`** — matches the process exit code.
- **`steps.*`** — per-step state: `completed`, `skipped`, `failed`, or `planned` (dry-run).
- **`warnings`** / **`errors`** — structured objects with stable `code`, `message`, `remediation`.

For manual control, see the steps below.

---

## Manual Build: C++ Native Plugin (RookNative)

RookNative is the core plugin — it runs the HTTP server inside Rhino. It requires
the Visual Studio C++ toolchain with MFC.

> **Note:** The manual commands below show `Community` in paths. If you have
> Professional or Enterprise, substitute accordingly. The automated build scripts
> detect all three editions.

### Option A: Use the Build Script (Canonical)

```powershell
.\build_native.ps1                           # Release, auto-detect toolset
.\build_native.ps1 -Configuration Debug      # Debug build
.\build_native.ps1 -VCToolsVersion 14.43.x   # Override toolset
```

`build_native.ps1` is the canonical native build script. It:
1. Dot-sources `scripts\detect-vs.ps1` for shared toolchain detection
2. Resolves VS edition (Community, Professional, Enterprise)
3. Pins `VCToolsVersion` for MFC, with fallback to newest MFC-capable toolset
4. Runs `msbuild` via a `vcvarsall.bat` subprocess

Output: `src\RookNative\bin\Release\x64\RookNative.rhp`

**Batch wrapper:** `scripts\build-native.bat` is a thin compatibility wrapper
that delegates to `build_native.ps1`. Existing callers (`cmd /c scripts\build-native.bat Release`)
still work.

### Option B: Manual MSBuild

If you need to run the build yourself (e.g., from a script or CI):

**From a Windows Command Prompt (cmd.exe):**
```cmd
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64
set VCToolsVersion=14.44.35207
msbuild src\RookNative\RookNative.vcxproj /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207 /v:minimal
```

**From PowerShell:**
```powershell
& 'C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\Tools\Launch-VsDevShell.ps1' -Arch amd64 -HostArch amd64 *> $null
$env:VCToolsVersion = '14.44.35207'
msbuild src\RookNative\RookNative.vcxproj /p:Configuration=Release /p:Platform=x64 /p:VCToolsVersion=14.44.35207 /verbosity:minimal
```

### Verify C++ Build

```powershell
Get-Item src\RookNative\bin\Release\x64\RookNative.rhp
```

---

## Manual Build: C# Companion Plugin (Rook)

The C# companion handles Grasshopper operations and the embedded chat panel.
It targets .NET Framework 4.8 and .NET 7.0 (multi-target).

### Option A: release build

```powershell
dotnet build src\Rook\Rook.csproj -f net7.0 -c Release
```

Output: `src\Rook\bin\Release\net7.0\Rook.rhp`

**Critical:** Rook's source installer and release installer register the net7.0
companion output. Older framework outputs are not supported for registration.

### Option B: build both target frameworks for development

```powershell
dotnet build src\Rook\Rook.csproj -c Release
```

Use this only when you need to compile all project targets. Deploy and release
from the net7.0 output.

### Verify C# Build

```powershell
Test-Path src\Rook\bin\Release\net7.0\Rook.rhp
Test-Path src\Rook\bin\Release\net7.0\Rook.deps.json
Test-Path src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json
Test-Path src\Rook\bin\Release\net7.0\runtimes
```

---

## Deploy Plugins to Rhino

After building, copy both plugins to the Rhino plugin directory:

```powershell
$dest = "$env:APPDATA\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
New-Item -ItemType Directory -Path $dest -Force | Out-Null

# C++ plugin
Copy-Item "src\RookNative\bin\Release\x64\RookNative.rhp" $dest -Force
Copy-Item "src\RookNative\bin\Release\x64\RookNative.pdb" $dest -Force -ErrorAction SilentlyContinue

# C# companion plugin (net7.0)
Copy-Item "src\Rook\bin\Release\net7.0\Rook.rhp" $dest -Force
Copy-Item "src\Rook\bin\Release\net7.0\Rook.rui" $dest -Force -ErrorAction SilentlyContinue
Copy-Item "src\Rook\bin\Release\net7.0\Rook.deps.json" $dest -Force
Copy-Item "src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json" $dest -Force
Copy-Item "src\Rook\bin\Release\net7.0\*.dll" $dest -Force
Copy-Item "src\Rook\bin\Release\net7.0\runtimes" $dest -Recurse -Force
```

Then register the plugins with Rhino:
```powershell
powershell -ExecutionPolicy Bypass -File scripts\register-rooknative-suite.ps1 -NativeRhpPath "$dest\RookNative.rhp"
```

Or run `install.ps1` which handles deployment and registration automatically
(it will skip building if binaries already exist).

---

## Setup MCP Server (Python)

After plugins are deployed, set up the Python MCP server:

```bash
cd mcp_server
pip install -e .
```

Or using uv (faster, auto-downloads Python if needed):
```bash
uv venv mcp_server/.venv
uv pip install -e mcp_server --python mcp_server/.venv/Scripts/python.exe
```

The `install.ps1` script does this automatically.

---

## Running Tests

The test suite is split into two tiers by pytest marker. CI runs only the unit
tier; the live tier is local-only because it requires a running Rhino instance
with the Rook plugins loaded.

### Unit tests (no Rhino required)

```bash
cd mcp_server
pytest tests -m "not requires_rhino"
```

This is what CI runs and what `CONTRIBUTING.md` expects before every PR.

### Live integration tests (Rhino required)

These tests call MCP tools against a live Rhino and assert on real geometry
results. They codify the regression matrix from PR #30 (Issue #27 fix).

**Preconditions:**
1. Rhino 8 running with RookNative + Rook companion loaded (see deploy steps
   above).
2. The Rhino document is **throwaway** — the fixture enumerates all block
   definitions and deletes them before each test, then creates test-specific
   objects. Any work in the current document will be lost.

```bash
cd mcp_server
pytest tests -m requires_rhino
```

To run a single live-test module (still from `mcp_server/`):

```bash
pytest tests/test_block_replace_object_geometry_live.py -m requires_rhino -v
```

If Rhino is not reachable, each test is skipped cleanly (not failed) — the
`requires_rhino` marker is a capability hint, not a hard gate.

### Owned Rhino runtime harness

The owned Rhino runtime harness is an opt-in helper for focused live smoke
verification when you want the test runner to own the Rhino process lifecycle:

```powershell
# From the repo root
python scripts\run_rhino_runtime_harness.py --smoke pytest-select

# Non-mutating readiness/cleanup diagnostic
python scripts\run_rhino_runtime_harness.py --smoke ping-only

# Focused GH Python geometry-output proof
python scripts\run_rhino_runtime_harness.py --smoke gh-python-geometry-output
```

The harness starts one Rhino process, waits only for
`%TEMP%\rook\instance-{PID}-native.json` matching the Rhino process ID it owns,
then pings the exact RookNative port discovered from that manifest. It runs the
selected live smoke tests with `ROOK_RHINO_PORT` and `ROOK_RHINO_PROCESS_ID`
set so tests target that owned runtime. Validation scripts that still accept the
older compatibility name may also receive `NATIVE_PORT`, but the scoped harness
contract is the `ROOK_RHINO_*` environment pair.

Harness run artifacts from `%TEMP%\rook` are captured under
`.scratch\rhino-runtime-harness` for inspection. When the run finishes, the
harness saves the owned document into the run artifact folder before external
close for smoke modes that may dirty the document, then closes only the Rhino
process it started. `ping-only` skips the save step so it remains a pure
readiness and cleanup diagnostic.

`gh-python-geometry-output` prepares Grasshopper in the owned Rhino process
using the existing GH readiness flow, creates a blank document, then runs the
focused live regression that creates a Python component with a typed
`Point3d` list output and proves `gh_bake_output` bakes three point geometries.

Ambient pytest behavior is unchanged. Without harness environment variables,
`pytest -m requires_rhino` continues to discover or skip live tests as before.
When harness environment variables are present, both `ROOK_RHINO_PORT` and
`ROOK_RHINO_PROCESS_ID` must be valid and reachable; otherwise the tests fail
instead of silently skipping.

The harness does not build, deploy, register, or modify plugins. Keep install
and deployment steps opt-in using the build and registration commands above.
This v1 is intentionally non-invasive: there is no native shutdown/control
route, and external close targets only the owned Rhino process.

---

## Rhino Must Be Closed During Build

**Rhino locks plugin DLLs while running.** If Rhino is open, the build or deploy
will fail with "file in use" errors. Always close Rhino before building.

Check if Rhino is running:
```powershell
Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
```

---

## Common Build Errors

| Error | Cause | Fix |
|-------|-------|-----|
| `error MSB8041: MFC libraries are required` | MFC not installed or wrong VCToolsVersion | Install "C++ MFC for latest v143 build tools" in VS Installer. Verify `VCToolsVersion=14.44.35207` |
| `error MSB4019: ... "PropertySheets\Rhino.Cpp.PlugIn.props" was not found` | Rhino 8 C++ SDK not installed | Download and install the SDK MSI as Administrator (see above) |
| `error MSB4019: The imported project was not found` (other) | C++ Desktop workload not installed | Open VS Installer, add "Desktop development with C++" |
| `LNK1104: cannot open file 'mfc140u.lib'` | MFC libs missing for the pinned toolset | Install the exact MFC component matching v14.44.35207 |
| `error CS0246: type or namespace not found` | Missing NuGet packages for C# build | Run `dotnet restore src/Rook` before building |
| C# output not found at expected path | Wrong target framework or output path | Build with `dotnet build src\Rook\Rook.csproj -f net7.0 -c Release`; release output is `bin\Release\net7.0\` |
| Access denied / file in use | Rhino has the DLL loaded | Close Rhino, then rebuild |
| `error MSB8020: ... v143 ... cannot be found` | v143 toolset not installed (common on VS2026) | VS Installer > Individual Components > install "MSVC v143 - VS 2022 C++ x64/x86 build tools" |
| `vcvarsall.bat` not found | VS not at expected path | May be Professional/Enterprise instead of Community, or VS2026 (`\18\` instead of `\2022\`) |

## Project Files

| File | Purpose |
|------|---------|
| `src/RookNative/RookNative.vcxproj` | C++ project — v143 toolset, dynamic MFC, Windows SDK 10.0 |
| `src/Rook/Rook.csproj` | C# project — multi-target net48 + net7.0, NuGet dependencies |
| `src/Rook.sln` | Solution file containing both projects |
| `build_native.ps1` | Canonical C++ build script (dot-sources `scripts/detect-vs.ps1`) |
| `scripts/detect-vs.ps1` | Shared VS 2022 toolchain detection (dot-sourced) |
| `scripts/build-native.bat` | Thin batch wrapper — delegates to `build_native.ps1` |
| `install.ps1` | Full install script (step functions, summary contract, exit codes) |
| `mcp_server/pyproject.toml` | Python MCP server package definition |
