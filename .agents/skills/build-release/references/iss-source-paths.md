# Inno Setup Source Path Checklist

Every file listed here is referenced by `installer/RookSetup.iss`. If any file
is missing, ISCC will either fail or silently exclude the component (if
`skipifsourcedoesntexist` is set).

All paths are relative to the repo root.

## Build Outputs (must be fresh — rebuilt after version bump)

| File | Source |
|------|--------|
| `src/RookNative/bin/Release/x64/RookNative.rhp` | C++ build output |
| `src/RookNative/bin/Release/x64/RookNative.pdb` | C++ debug symbols |
| `src/Rook/bin/Release/net7.0/Rook.rhp` | C# build output |
| `src/Rook/bin/Release/net7.0/Rook.rui` | Rhino toolbar file |
| `src/Rook/bin/Release/net7.0/Rook.deps.json` | C# dependency manifest |
| `src/Rook/bin/Release/net7.0/Rook.runtimeconfig.json` | C# runtime metadata; must declare net7.0 |
| `src/Rook/bin/Release/net7.0/*.dll` | C# dependency DLLs |
| `src/Rook/bin/Release/net7.0/runtimes/` | C# runtime assets |

**CRITICAL:** The installer must package the net7.0 companion output from
`src/Rook/bin/Release/net7.0/`. Older framework outputs are not supported for
registration or release packaging.

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

## Bundled FFmpeg Payload

Installer Source paths must include `third_party\ffmpeg` and package the
LGPL-only subprocess payload plus its compliance files:

| File | Notes |
|------|-------|
| `third_party/ffmpeg/ffmpeg.exe` | Vetted bundled Windows FFmpeg binary |
| `third_party/ffmpeg/ffmpeg-provenance.json` | Machine-readable provenance, checksum, version, and configure metadata |
| `third_party/ffmpeg/ffmpeg-dependencies.json` | Machine-readable dependency manifest for the enabled static build flags |
| `third_party/ffmpeg/LICENSE.FFmpeg.txt` | License file for the bundled payload |
| `third_party/ffmpeg/NOTICE.FFmpeg.txt` | Attribution and notice text |
| `third_party/ffmpeg/SOURCE.FFmpeg.txt` | Corresponding source-compliance information |
| `third_party/ffmpeg/DEPENDENCIES.FFmpeg.txt` | External dependency source/build compliance notes |
| `third_party/ffmpeg/README.md` | Installed payload summary |

## Knowledge Stores

| Dir | Notes |
|-----|-------|
| `knowledge/commands/` | Must be non-empty (196+ Rhino command files) |
| `knowledge/gh/` | Must be non-empty; excludes `sessions/` subdir |

## Claude / Codex Agent Assets

| File/Dir | Notes |
|----------|-------|
| `.claude-plugin/plugin.json` | Plugin manifest |
| `.claude-plugin/marketplace.json` | Marketplace registration |
| `.claude/skills/` | Claude Code skill payload (recursesubdirs) |
| `.claude/agents/` | Claude agent payload (recursesubdirs) |
| `.agents/skills/` | Codex skill payload (recursesubdirs) |
| `hooks/hooks.json` | Hook definitions |
| `scripts/session-start.sh` | Session startup script |

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
| `BUILDING.md` | Build and source-install guide |
| `LICENSE` | License file |

## Verification Script

Run this to check all paths at once:

```powershell
$Repo = "C:\Users\aryan\source\repos\Rook"
$missing = New-Object System.Collections.Generic.List[string]

$files = @(
  "src\RookNative\bin\Release\x64\RookNative.rhp",
  "src\RookNative\bin\Release\x64\RookNative.pdb",
  "src\Rook\bin\Release\net7.0\Rook.rhp",
  "src\Rook\bin\Release\net7.0\Rook.rui",
  "src\Rook\bin\Release\net7.0\Rook.deps.json",
  "src\Rook\bin\Release\net7.0\Rook.runtimeconfig.json",
  "mcp_server\pyproject.toml",
  "..\Chirp\pyproject.toml",
  ".claude-plugin\plugin.json",
  ".claude-plugin\marketplace.json",
  "hooks\hooks.json",
  "scripts\session-start.sh",
  "installer\post_install.py",
  "installer\rook-icon.ico",
  "installer\pre-install-readme.txt",
  "installer\CLAUDE.md",
  "installer\AGENTS.md",
  "mcp_server\README.md",
  "third_party\ffmpeg\ffmpeg.exe",
  "third_party\ffmpeg\ffmpeg-provenance.json",
  "third_party\ffmpeg\ffmpeg-dependencies.json",
  "third_party\ffmpeg\LICENSE.FFmpeg.txt",
  "third_party\ffmpeg\NOTICE.FFmpeg.txt",
  "third_party\ffmpeg\SOURCE.FFmpeg.txt",
  "third_party\ffmpeg\DEPENDENCIES.FFmpeg.txt",
  "third_party\ffmpeg\README.md",
  "docs\ONBOARDING_NEW_CLAUDE.md",
  "docs\CURRENT_ARCHITECTURE.md",
  "docs\AGENT_ARCHITECTURE.md",
  "docs\TROUBLESHOOTING.md",
  "QUICK_START.md",
  "AGENT_SETUP.md",
  "BUILDING.md",
  "LICENSE"
)

foreach ($file in $files) {
  $path = Join-Path $Repo $file
  if (-not (Test-Path $path)) { $missing.Add("MISSING: $path") }
}

$directories = @(
  "mcp_server\src\rook",
  "..\Chirp\src\chirp",
  "knowledge\commands",
  "knowledge\gh",
  ".claude\skills",
  ".claude\agents",
  ".agents\skills",
  "src\Rook\bin\Release\net7.0\runtimes"
)

foreach ($directory in $directories) {
  $path = Join-Path $Repo $directory
  if (-not (Test-Path $path) -or -not (Get-ChildItem -Path $path -Force | Select-Object -First 1)) {
    $missing.Add("MISSING OR EMPTY: $path")
  }
}

$dllCount = @(Get-ChildItem -Path (Join-Path $Repo "src\Rook\bin\Release\net7.0") -Filter *.dll).Count
if ($dllCount -lt 1) { $missing.Add("MISSING: C# dependency DLLs") }

if ($missing.Count -eq 0) {
  "ALL CHECKS PASSED"
} else {
  $missing
  throw "FAILED: $($missing.Count) items missing"
}
```
