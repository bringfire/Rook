; -- RookSetup.iss --
; Rook Installer — AI Bridge for Rhino 3D & Grasshopper
;
; Installs:
;   1. RookNative.rhp (C++ plugin) + Rook.rhp (C# companion) → Rhino plugin dir
;   2. Registers both plugins in Rhino 8 registry
;   3. Python MCP server payload + knowledge stores
;   4. Chirp adapter service from bundled private Python runtime
;   5. Claude Code / Claude Desktop / Codex user-scope MCP configuration + skills
;   6. Claude Code user agents
;
; Build with: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" RookSetup.iss
; Or open in Inno Setup GUI and press Ctrl+F9.

#define MyAppName "Rook"
#ifndef MyAppVersion
#define MyAppVersion "1.5.18"
#endif
#define MyAppPublisher "Bringfire"
#define MyAppURL "https://github.com/bringfire/rook-release"

; Paths relative to this .iss file — adjust if your build layout differs.
; These assume a Release build has been run before packaging.
#define RepoRoot ".."
#define NativePlugin RepoRoot + "\src\RookNative\bin\Release\x64\RookNative.rhp"
#define NativePdb    RepoRoot + "\src\RookNative\bin\Release\x64\RookNative.pdb"
#define CompanionNet8Dir RepoRoot + "\src\Rook\bin\Release\net8.0"
#define CompanionNet7Dir RepoRoot + "\src\Rook\bin\Release\net7.0"
#define CompanionNet48Dir RepoRoot + "\src\Rook\bin\Release\net48"
#define McpServerDir RepoRoot + "\mcp_server"
#define KnowledgeDir RepoRoot + "\knowledge"
#define ScriptsDir   RepoRoot + "\scripts"
#define FfmpegDir   RepoRoot + "\third_party\ffmpeg"
#define CodexCuratedSkillsDir RepoRoot + "\installer\agent-assets\codex-skills"
#define ChirpDir     RepoRoot + "\..\Chirp"
#define PythonRuntimeDir RepoRoot + "\installer\runtime\python\cpython-3.11.9"
#define PythonWheelhouseDir RepoRoot + "\installer\runtime\python-wheelhouse"
#define PythonRuntimeManifest RepoRoot + "\installer\runtime\python-runtime-manifest.json"
#define BootstrapLockfile RepoRoot + "\installer\runtime\requirements-bootstrap-lock.txt"
#define RookLockfile RepoRoot + "\installer\runtime\requirements-rook-lock.txt"
#define ChirpLockfile RepoRoot + "\installer\runtime\requirements-chirp-lock.txt"
#ifndef PrimeRuntimePayload
  #error PrimeRuntimePayload must identify the complete verified Prime runtime payload
#endif
#ifndef VcRedistRoot
#define VcRedistRoot "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Redist\MSVC\14.44.35112\x64"
#endif
#define VcRedistCrtDir VcRedistRoot + "\Microsoft.VC143.CRT"
#define VcRedistMfcDir VcRedistRoot + "\Microsoft.VC143.MFC"
#ifndef OcctRuntimeRoot
#define OcctRuntimeRoot RepoRoot + "\..\OCCT\build-rook\win64\vc14\bin"
#endif

[Setup]
AppId={{E9A3F2B1-4C5D-6E7F-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
DefaultDirName={localappdata}\Rook\app
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputBaseFilename=Rook-Setup-{#MyAppVersion}
OutputDir=output
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
SetupIconFile=rook-icon.ico
UninstallDisplayIcon={app}\rook-icon.ico
InfoBeforeFile={#RepoRoot}\installer\pre-install-readme.txt
CloseApplications=no
RestartApplications=no
SetupLogging=yes

; Don't create an uninstall entry in Add/Remove Programs — we handle it ourselves
; Actually, DO create it so users can uninstall normally:
; (default behavior)

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Full installation (Rhino plugins + MCP + Chirp + knowledge)"
Name: "pluginsonly"; Description: "Rhino plugins only (no Python/MCP server)"
Name: "custom"; Description: "Custom installation"; Flags: iscustom

[Components]
Name: "plugins"; Description: "Rhino 8 Plugins (RookNative + Companion)"; Types: full pluginsonly custom; Flags: fixed
Name: "mcp"; Description: "Python MCP Server (bundled private runtime)"; Types: full custom
Name: "chirp"; Description: "Chirp — LLM-powered Grasshopper components (bundled private runtime)"; Types: full custom
Name: "knowledge"; Description: "Knowledge Stores (commands + Grasshopper)"; Types: full custom
Name: "claude"; Description: "Claude Code / Claude Desktop MCP configuration (requires MCP)"; Types: full custom
Name: "codex"; Description: "OpenAI Codex CLI MCP configuration + curated skills (requires MCP)"; Types: full custom

; ---------------------------------------------------------------------------
; Upgrade cleanup — remove stale payload from older installs
; ---------------------------------------------------------------------------

[InstallDelete]
; Historical prime/runtimes and persistent data/rookchat/acp/v1 are never repair targets.
; Remove stale agent payload from older installs (pre-curated-payload versions)
Type: filesandordirs; Name: "{app}\.claude-plugin"
Type: filesandordirs; Name: "{app}\.claude"
Type: filesandordirs; Name: "{app}\hooks"
Type: files; Name: "{app}\scripts\session-start.sh"
Type: filesandordirs; Name: "{app}\.agents\skills"
Type: filesandordirs; Name: "{app}\Skills"
Type: filesandordirs; Name: "{app}\.codex"
Type: files; Name: "{app}\.mcp.json"
Type: files; Name: "{app}\LICENSE"
Type: files; Name: "{app}\BUILDING.md"
; Replace the installer-owned sealed wheelhouse instead of overlaying stale wheels.
Type: filesandordirs; Name: "{app}\python-wheelhouse"; Components: mcp chirp
; Remove stale per-runtime chat manifests before post_install writes fresh copies.
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\RookChatService.json"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rui"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui"
Type: files; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rui"

; ---------------------------------------------------------------------------
; Files
; ---------------------------------------------------------------------------

[Files]
; --- Rhino Plugins ---
; C++ native plugin (x64 only) — required public Rhino surface
Source: "{#NativePlugin}"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#NativePdb}"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion skipifsourcedoesntexist
Source: "{#VcRedistCrtDir}\concrt140.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#VcRedistCrtDir}\msvcp140.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#VcRedistCrtDir}\vcruntime140.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#VcRedistCrtDir}\vcruntime140_1.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#VcRedistMfcDir}\mfc140.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#VcRedistMfcDir}\mfc140u.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKernel.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKMath.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKG2d.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKG3d.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKGeomBase.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKGeomAlgo.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKBRep.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKTopAlgo.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKPrim.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKBO.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#OcctRuntimeRoot}\TKShHealing.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion

; C# companion plugin: package sibling runtime payloads for direct-registry
; install smoke validation. Release is blocked until Rhino proves which physical
; Rook.rhp path it loads for standalone and Rhino.Inside hosts.
Source: "{#CompanionNet8Dir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\Rook.deps.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\Rook.runtimeconfig.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\*.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\runtimes\*"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\runtimes"; Components: plugins; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "{#CompanionNet7Dir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\Rook.deps.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\Rook.runtimeconfig.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\*.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\runtimes\*"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\runtimes"; Components: plugins; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "{#CompanionNet48Dir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet48Dir}\*.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet48Dir}\runtimes\*"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\runtimes"; Components: plugins; Flags: ignoreversion recursesubdirs createallsubdirs

; Bundled LGPL-only FFmpeg for video sidecar extraction
Source: "{#FfmpegDir}\ffmpeg.exe"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\ffmpeg-provenance.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\LICENSE.FFmpeg.txt"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\NOTICE.FFmpeg.txt"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\SOURCE.FFmpeg.txt"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion
Source: "{#FfmpegDir}\README.md"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\ffmpeg"; Components: plugins; Flags: ignoreversion

; --- Python MCP Server ---
Source: "{#McpServerDir}\pyproject.toml"; DestDir: "{app}\mcp_server"; Components: mcp; Flags: ignoreversion
Source: "{#McpServerDir}\README.md"; DestDir: "{app}\mcp_server"; Components: mcp; Flags: ignoreversion
Source: "{#McpServerDir}\src\rook\*"; DestDir: "{app}\mcp_server\src\rook"; Components: mcp; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PythonRuntimeDir}\*"; DestDir: "{localappdata}\Rook\python\cpython-3.11.9"; Components: mcp; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#PythonWheelhouseDir}\*"; DestDir: "{app}\python-wheelhouse"; Components: mcp chirp; Flags: ignoreversion
Source: "{#PythonRuntimeManifest}"; DestDir: "{app}"; Components: mcp; Flags: ignoreversion
Source: "{#BootstrapLockfile}"; DestDir: "{app}"; Components: mcp chirp; Flags: ignoreversion
Source: "{#RookLockfile}"; DestDir: "{app}"; Components: mcp; Flags: ignoreversion
Source: "{#ChirpLockfile}"; DestDir: "{app}"; Components: chirp; Flags: ignoreversion

; --- Chirp Adapter Service ---
Source: "{#ChirpDir}\pyproject.toml"; DestDir: "{app}\chirp"; Components: chirp; Flags: ignoreversion
Source: "{#ChirpDir}\src\chirp\*"; DestDir: "{app}\chirp\src\chirp"; Components: chirp; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Knowledge Stores ---
Source: "{#KnowledgeDir}\commands\*"; DestDir: "{app}\knowledge\commands"; Components: knowledge; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#KnowledgeDir}\gh\*"; DestDir: "{app}\knowledge\gh"; Components: knowledge; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "sessions"

; --- Durable Script Library ---
Source: "{#ScriptsDir}\rook-library\*"; DestDir: "{app}\scripts\rook-library"; Components: mcp; Flags: ignoreversion recursesubdirs createallsubdirs

; --- Curated Codex skill payload + post-install prompts ---
Source: "{#CodexCuratedSkillsDir}\*"; DestDir: "{app}\.agents\skills"; Components: codex; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#RepoRoot}\installer\agent-assets\ROOK_CLAUDE_POST_INSTALL.md"; DestDir: "{localappdata}\Rook"; Flags: ignoreversion
Source: "{#RepoRoot}\installer\agent-assets\ROOK_CODEX_POST_INSTALL.md"; DestDir: "{localappdata}\Rook"; Flags: ignoreversion

; --- Post-install setup script (always included, launched from Pascal script) ---
Source: "post_install.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#PrimeRuntimePayload}\*"; DestDir: "{code:GetPrimeIncomingDir}"; Components: mcp; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "python_runtime_install.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "rook_process_preflight.ps1"; Flags: dontcopy
Source: "process_rebuild_guard.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "rook-icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; --- Docs ---
Source: "{#RepoRoot}\QUICK_START.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\AGENT_SETUP.md"; DestDir: "{app}"; Flags: ignoreversion

; --- Agent-facing documentation (referenced by CLAUDE.md) ---
Source: "{#RepoRoot}\docs\ONBOARDING_NEW_CLAUDE.md"; DestDir: "{localappdata}\Rook\docs"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\CURRENT_ARCHITECTURE.md"; DestDir: "{localappdata}\Rook\docs"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\AGENT_ARCHITECTURE.md"; DestDir: "{localappdata}\Rook\docs"; Flags: ignoreversion
Source: "{#RepoRoot}\docs\TROUBLESHOOTING.md"; DestDir: "{localappdata}\Rook\docs"; Flags: ignoreversion

; --- Agent instruction files (user-facing, stripped of contributor internals) ---
; Installed to Rook root (one level above {app}) so users working from
; %LOCALAPPDATA%\Rook get auto-loading, and can easily find it to copy
; to their own project folders.
; CLAUDE.md → Claude Code / Claude Desktop
; AGENTS.md → OpenAI Codex CLI
Source: "CLAUDE.md"; DestDir: "{localappdata}\Rook"; Flags: ignoreversion
Source: "AGENTS.md"; DestDir: "{localappdata}\Rook"; Components: codex; Flags: ignoreversion

; ---------------------------------------------------------------------------
; Registry — Plugin registration for Rhino 8
; ---------------------------------------------------------------------------

[Registry]
; RookNative (C++ plugin) — load at startup
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Name"; ValueData: "RookNative"; Components: plugins; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "EnglishName"; ValueData: "RookNative"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Organization"; ValueData: "Bringfire"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Address"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Country"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Phone"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "EMail"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "WebSite"; ValueData: "https://github.com/bringfire/rook-release"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "UpdateURL"; ValueData: "https://github.com/bringfire/rook-release/releases"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Fax"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "Description"; ValueData: "RookNative - High-performance Rhino bridge for Claude Code"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: string; ValueName: "RegPath"; ValueData: "\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\PlugIn"; ValueType: string; ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.rhp"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "Type"; ValueData: "16"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "IsDotNETPlugIn"; ValueData: "0"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "LoadMode"; ValueData: "1"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "AddToHelpMenu"; ValueData: "0"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "DirectoryInstall"; ValueData: "0"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\CommandList"; Flags: uninsdeletekey; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\CommandList"; ValueType: string; ValueName: "AIGumball"; ValueData: "2;AIGumball"; Components: plugins

; Rook Companion (C# plugin) — load when needed
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Name"; ValueData: "Rook"; Components: plugins; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "EnglishName"; ValueData: "Rook"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Organization"; ValueData: "Bringfire"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Address"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Country"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Phone"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "EMail"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "WebSite"; ValueData: "https://github.com/bringfire/rook-release"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "UpdateURL"; ValueData: "https://github.com/bringfire/rook-release/releases"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Fax"; ValueData: ""; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Description"; ValueData: "Rook for Rhino 3D - HTTP server enabling AI-powered CAD operations"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: none; ValueName: "RuiFile"; Flags: deletevalue dontcreatekey
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "RegPath"; ValueData: "\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn"; ValueType: string; ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "Type"; ValueData: "16"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "IsDotNETPlugIn"; ValueData: "1"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "LoadMode"; ValueData: "2"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "LoadProtection"; ValueData: "1"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "AddToHelpMenu"; ValueData: "0"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "DirectoryInstall"; ValueData: "0"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; Flags: uninsdeletekey; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; ValueType: string; ValueName: "RestartRookChatService"; ValueData: "2;RestartRookChatService"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; ValueType: string; ValueName: "ShowRookChat"; ValueData: "2;ShowRookChat"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; ValueType: string; ValueName: "ShowRookKnowledgeGraph"; ValueData: "2;ShowRookKnowledgeGraph"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; ValueType: string; ValueName: "ShowRookVision"; ValueData: "2;ShowRookVision"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; ValueType: string; ValueName: "UVBoxMapping"; ValueData: "2;UVBoxMapping"; Components: plugins

; ---------------------------------------------------------------------------
; Post-install Python setup is run from [Code] so child exit codes are fatal.
; ---------------------------------------------------------------------------

; ---------------------------------------------------------------------------
; Uninstall cleanup
; ---------------------------------------------------------------------------

[UninstallDelete]
; Preserve user data and RookVision artifact stores. Do not delete:
;   {userappdata}\Rook\artifacts
;   {localappdata}\Rook\rookvision_director
;   {localappdata}\Rook\data
Type: filesandordirs; Name: "{app}\mcp_server"
Type: filesandordirs; Name: "{app}\chirp"
Type: filesandordirs; Name: "{app}\knowledge"
Type: filesandordirs; Name: "{localappdata}\Rook\app"
Type: filesandordirs; Name: "{localappdata}\Rook\python"
Type: filesandordirs; Name: "{localappdata}\Rook\venv"
Type: filesandordirs; Name: "{localappdata}\Rook\logs"
Type: filesandordirs; Name: "{localappdata}\Rook\discovery"
Type: filesandordirs; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
Type: filesandordirs; Name: "{localappdata}\Temp\rook"
Type: files; Name: "{localappdata}\Rook\CLAUDE.md"
Type: files; Name: "{localappdata}\Rook\AGENTS.md"
Type: files; Name: "{localappdata}\Rook\ROOK_CLAUDE_POST_INSTALL.md"
Type: files; Name: "{localappdata}\Rook\ROOK_CODEX_POST_INSTALL.md"
Type: filesandordirs; Name: "{localappdata}\Rook\docs"

; ---------------------------------------------------------------------------
; Pascal Script — Python detection, prerequisite checks
; ---------------------------------------------------------------------------

[Code]
var
  PrimeIncomingDir: String;
  PythonPath: String;
  PythonDetected: Boolean;
  RookPreflightHelperPath: String;
  RookPreflightSummaryPath: String;
  RookPreflightInnoSummaryPath: String;
  RookPreflightLogRoot: String;
  RookPreflightResweepEnabled: Boolean;
  RookPreflightLastSweepTick: Cardinal;
  FinalizingRookPage: TOutputMarqueeProgressWizardPage;

function GetTickCount: Cardinal; external 'GetTickCount@kernel32.dll stdcall';

// Resolve the actual python.exe path by running the candidate and capturing sys.executable.
// This avoids the problem where compound commands like 'py -3' can't be used as a Filename.
function ResolvePythonExe(const Candidate, ExtraArgs: String): Boolean;
var
  TmpFile: String;
  Lines: TArrayOfString;
  ResultCode: Integer;
  CmdLine: String;
begin
  Result := False;
  TmpFile := ExpandConstant('{tmp}') + '\rook_python_path.txt';

  if ExtraArgs <> '' then
    CmdLine := '/c ' + Candidate + ' ' + ExtraArgs + ' -c "import sys; print(sys.executable)" > "' + TmpFile + '"'
  else
    CmdLine := '/c ' + Candidate + ' -c "import sys; print(sys.executable)" > "' + TmpFile + '"';

  if Exec('cmd.exe', CmdLine, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
  begin
    if (ResultCode = 0) and LoadStringsFromFile(TmpFile, Lines) then
    begin
      if (GetArrayLength(Lines) > 0) and (Lines[0] <> '') and FileExists(Lines[0]) then
      begin
        PythonPath := Lines[0];
        PythonDetected := True;
        Result := True;
      end;
    end;
  end;

  DeleteFile(TmpFile);
end;

function FindPython(): Boolean;
begin
  Result := False;
  PythonDetected := False;

  // Try each candidate in order; ResolvePythonExe captures the real python.exe path
  if ResolvePythonExe('python', '') then begin Result := True; Exit; end;
  if ResolvePythonExe('python3', '') then begin Result := True; Exit; end;
  if ResolvePythonExe('py', '-3') then begin Result := True; Exit; end;
end;

function PythonFound(): Boolean;
begin
  Result := PythonDetected;
end;

function GetPythonPath(Param: String): String;
begin
  Result := PythonPath;
end;

function BundledPythonFound(): Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe'));
end;

function GetChirpArgs(Param: String): String;
begin
  if WizardIsComponentSelected('chirp') then
    Result := '--chirp-dir "' + ExpandConstant('{app}') + '\chirp"'
  else
    Result := '';
end;

function GetCodexArgs(Param: String): String;
begin
  if WizardIsComponentSelected('codex') then
    Result := '--codex'
  else
    Result := '';
end;

function GetClaudeArgs(Param: String): String;
begin
  if WizardIsComponentSelected('claude') then
    Result := '--claude'
  else
    Result := '';
end;

function GetPluginsArgs(Param: String): String;
begin
  if WizardIsComponentSelected('plugins') then
    Result := '--plugins'
  else
    Result := '';
end;

function PostInstallSelected(): Boolean;
begin
  Result :=
    WizardIsComponentSelected('mcp') or
    WizardIsComponentSelected('chirp') or
    WizardIsComponentSelected('claude') or
    WizardIsComponentSelected('codex');
end;

function RunRookPreflightHelper(const Mode, ExtraArgs: String; var ResultCode: Integer): Boolean;
var
  Args: String;
begin
  Args :=
    '-NoProfile -ExecutionPolicy Bypass -File "' + RookPreflightHelperPath + '"' +
    ' -Mode ' + Mode +
    ' -RookRoot "' + ExpandConstant('{localappdata}\Rook') + '"' +
    ' -LogRoot "' + RookPreflightLogRoot + '"' +
    ' -SummaryPath "' + RookPreflightSummaryPath + '"' +
    ' -InnoSummaryPath "' + RookPreflightInnoSummaryPath + '"' +
    ' -SetupVersion "{#MyAppVersion}" ' + ExtraArgs;
  Log('Rook process preflight: powershell.exe ' + Args);
  Result := Exec('powershell.exe', Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

function TryGetPreflightSummaryValue(const Lines: TArrayOfString; const Key: String; var Value: String): Boolean;
var
  I: Integer;
  Prefix: String;
begin
  Result := False;
  Prefix := Key + '=';
  for I := 0 to GetArrayLength(Lines) - 1 do
  begin
    if Pos(Prefix, Lines[I]) = 1 then
    begin
      Value := Copy(Lines[I], Length(Prefix) + 1, Length(Lines[I]) - Length(Prefix));
      Result := True;
      Exit;
    end;
  end;
end;

function RookPreflightFailureMessage(ResultCode: Integer): String;
begin
  case ResultCode of
    10:
      Result := 'Rook agent servers could not be closed. Close Claude, Codex, or the listed owner apps and run Setup again.';
    20:
      Result := 'Rook Setup could not inspect running processes. See post_install.log and the setup log.';
    30, 40:
      Result := 'Rook Setup could not complete process preflight. See post_install.log and the setup log.';
  else
    Result := 'Rook Setup could not complete process preflight. See post_install.log and the setup log.';
  end;
end;

function RunRookProcessPreflight(var ErrorMessage: String): Boolean;
var
  Lines: TArrayOfString;
  ResultCode: Integer;
  ConflictsFound: String;
  MessageText: String;
begin
  Result := False;
  ErrorMessage := '';
  RookPreflightResweepEnabled := False;
  RookPreflightLastSweepTick := 0;

  ExtractTemporaryFile('rook_process_preflight.ps1');
  RookPreflightHelperPath := ExpandConstant('{tmp}\rook_process_preflight.ps1');
  RookPreflightLogRoot := ExpandConstant('{localappdata}\Rook\logs');
  RookPreflightSummaryPath := RookPreflightLogRoot + '\post_install_summary.json';
  RookPreflightInnoSummaryPath := RookPreflightLogRoot + '\preflight-summary.txt';

  if not RunRookPreflightHelper('enumerate', '', ResultCode) then
  begin
    ErrorMessage := 'Rook Setup could not launch process preflight. See the setup log.';
    Exit;
  end;

  if (ResultCode <> 0) and (ResultCode <> 10) then
  begin
    ErrorMessage := RookPreflightFailureMessage(ResultCode);
    Exit;
  end;

  if not LoadStringsFromFile(RookPreflightInnoSummaryPath, Lines) then
  begin
    ErrorMessage := 'Rook Setup could not read process preflight results. See post_install.log and the setup log.';
    Exit;
  end;

  if not TryGetPreflightSummaryValue(Lines, 'conflicts_found', ConflictsFound) then
  begin
    ErrorMessage := 'Rook Setup could not read process preflight conflict status. See post_install.log and the setup log.';
    Exit;
  end;

  if CompareText(ConflictsFound, 'true') <> 0 then
  begin
    Result := True;
    Exit;
  end;

  if not TryGetPreflightSummaryValue(Lines, 'message', MessageText) then
    MessageText := 'Rook Setup found running Rook agent server(s).' + #13#10 + #13#10 + 'Setup will close them now so Rook can be updated.';
  StringChangeEx(MessageText, '\r\n', #13#10, True);

  if not WizardSilent then
  begin
    if MsgBox(MessageText, mbConfirmation, MB_OKCANCEL) = IDCANCEL then
    begin
      RunRookPreflightHelper('record-outcome', '-Outcome cancelled', ResultCode);
      ErrorMessage := 'Rook Setup cannot continue while Rook agent servers are running.';
      Exit;
    end;
  end;

  if not RunRookPreflightHelper('close', '', ResultCode) then
  begin
    ErrorMessage := 'Rook Setup could not launch process preflight close mode. See the setup log.';
    Exit;
  end;

  if ResultCode <> 0 then
  begin
    ErrorMessage := RookPreflightFailureMessage(ResultCode);
    Exit;
  end;

  RookPreflightResweepEnabled := True;
  Result := True;
end;

procedure ShowFinalizingRookPage();
begin
  if FinalizingRookPage = nil then
  begin
    FinalizingRookPage :=
      CreateOutputMarqueeProgressPage(
        'Finalizing Rook',
        'First-time setup can take 10-12 minutes. The installer is still working.');
  end;

  FinalizingRookPage.SetText(
    'This step configures private Python, bundled wheels, MCP entries, skills, and validation.',
    '');
  FinalizingRookPage.Show;
  FinalizingRookPage.Animate;
  WizardForm.Update;
end;

procedure HideFinalizingRookPage();
begin
  if FinalizingRookPage <> nil then
    FinalizingRookPage.Hide;
end;

function CoCreateGuid(var Guid: TGUID): Integer;
  external 'CoCreateGuid@ole32.dll stdcall';
function StringFromGUID2(const Guid: TGUID; Buffer: String; BufferLength: Integer): Integer;
  external 'StringFromGUID2@ole32.dll stdcall';

function GetPrimeIncomingDir(Param: String): String;
var
  Guid: TGUID;
  Text: String;
begin
  if PrimeIncomingDir = '' then
  begin
    OleCheck(CoCreateGuid(Guid));
    SetLength(Text, 39);
    if StringFromGUID2(Guid, Text, 39) <> 39 then
      RaiseException('Cannot create Prime incoming generation.');
    PrimeIncomingDir := ExpandConstant('{app}\prime\.incoming\') + LowerCase(Copy(Text, 2, 36));
    if DirExists(PrimeIncomingDir) or FileExists(PrimeIncomingDir) then
      RaiseException('Prime incoming generation already exists.');
  end;
  Result := PrimeIncomingDir;
end;

function RunPostInstallSetup(): Boolean;
var
  PythonExe: String;
  Args: String;
  ResultCode: Integer;
begin
  Result := True;

  if not PostInstallSelected() then
    Exit;

  PythonExe := ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe');
  if not FileExists(PythonExe) then
  begin
    Log('Post-install failed: bundled private Python is missing: ' + PythonExe);
    MsgBox(
      'Rook could not find its bundled private Python runtime.' + #13#10 + #13#10 +
      'Repair the installation or rebuild the installer with the staged Python runtime payload.',
      mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  Args :=
    '"' + ExpandConstant('{app}') + '\post_install.py"' +
    ' --install-dir "' + ExpandConstant('{app}') + '"' +
    ' --runtime-root "' + ExpandConstant('{localappdata}\Rook') + '"' +
    ' --mcp-server-dir "' + ExpandConstant('{app}') + '\mcp_server"' +
    ' --prime-incoming-dir "' + GetPrimeIncomingDir('') + '"' +
    ' ' + GetChirpArgs('') +
    ' ' + GetClaudeArgs('') +
    ' ' + GetCodexArgs('') +
    ' ' + GetPluginsArgs('');

  WizardForm.StatusLabel.Caption :=
    'Finalizing Rook: creating private Python environments and installing bundled wheels offline (no internet download required). This can take several minutes.';
  WizardForm.StatusLabel.Update;
  Log('Post-install: running post_install.py with private Python: ' + PythonExe);
  ShowFinalizingRookPage();
  try
    if not Exec(PythonExe, Args, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
    begin
      Log('Post-install failed: could not launch post_install.py');
      MsgBox(
        'Rook could not launch its post-install Python setup.' + #13#10 + #13#10 +
        'Close Rhino/Revit, then rerun the installer repair flow.',
        mbCriticalError, MB_OK);
      Result := False;
      Exit;
    end;
  finally
    HideFinalizingRookPage();
  end;

  if ResultCode <> 0 then
  begin
    Log('Post-install failed: post_install.py exited with code ' + IntToStr(ResultCode));
    MsgBox(
      'Rook post-install finalization failed and the installation cannot be treated as complete.' + #13#10 + #13#10 +
      'This final step configures the bundled Python runtime, MCP client entries, Codex skills, and Rhino chat manifest.' + #13#10 + #13#10 +
      'Close Rhino/Revit and any Rook Python processes, then rerun the installer repair flow. ' +
      'If the failure repeats, collect the installer log before publishing this build.',
      mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  Log('Post-install: setup completed via post_install.py');
end;

function RhinoInstalled(): Boolean;
begin
  Result := RegKeyExists(HKCU, 'Software\McNeel\Rhinoceros\8.0');
end;

function IsProcessRunning(const ImageName: String): Boolean;
var
  ResultCode: Integer;
  CmdLine: String;
begin
  CmdLine := '/C tasklist /FI "IMAGENAME eq ' + ImageName + '" /NH | find /I "' + ImageName + '" >NUL';
  Result := Exec('cmd.exe', CmdLine, '', SW_HIDE, ewWaitUntilTerminated, ResultCode) and (ResultCode = 0);
end;

function IsRhinoHostRunning(): Boolean;
begin
  Result :=
    IsProcessRunning('Rhino.exe') or
    IsProcessRunning('Rhinoceros.exe') or
    IsProcessRunning('Revit.exe');
end;

function VerifyRegistryStringValue(const BaseKey, ValueName, ExpectedValue: String): Boolean;
var
  ActualValue: String;
begin
  Result := False;

  if not RegQueryStringValue(HKCU, BaseKey, ValueName, ActualValue) then
  begin
    Log('Rhino plugin verification failed: missing ' + BaseKey + '\' + ValueName);
    Exit;
  end;

  if CompareText(ActualValue, ExpectedValue) <> 0 then
  begin
    Log('Rhino plugin verification failed: ' + BaseKey + '\' + ValueName + ' expected "' + ExpectedValue + '", got "' + ActualValue + '"');
    Exit;
  end;

  Result := True;
end;

function VerifyRegistryDWordValue(const BaseKey, ValueName: String; ExpectedValue: Cardinal): Boolean;
var
  ActualValue: Cardinal;
begin
  Result := False;

  if not RegQueryDWordValue(HKCU, BaseKey, ValueName, ActualValue) then
  begin
    Log('Rhino plugin verification failed: missing ' + BaseKey + '\' + ValueName);
    Exit;
  end;

  if ActualValue <> ExpectedValue then
  begin
    Log('Rhino plugin verification failed: ' + BaseKey + '\' + ValueName + ' had unexpected value');
    Exit;
  end;

  Result := True;
end;

function VerifyCommandListValue(const Guid, CommandName: String): Boolean;
begin
  Result := VerifyRegistryStringValue(
    'Software\McNeel\Rhinoceros\8.0\Plug-Ins\' + Guid + '\CommandList',
    CommandName,
    '2;' + CommandName);
end;

function VerifyPluginRegistration(const Guid, FileName: String; IsDotNet: Cardinal; LoadMode: Cardinal): Boolean;
var
  BaseKey: String;
  PluginName: String;
  Description: String;
  RegPath: String;
  RequiredStringValues: TArrayOfString;
  RequiredCommandValues: TArrayOfString;
  I: Integer;
begin
  Result := False;
  BaseKey := 'Software\McNeel\Rhinoceros\8.0\Plug-Ins\' + Guid;

  if not FileExists(FileName) then
  begin
    Log('Rhino plugin verification failed: file missing: ' + FileName);
    Exit;
  end;

  if CompareText(Guid, 'A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906') = 0 then
  begin
    PluginName := 'RookNative';
    Description := 'RookNative - High-performance Rhino bridge for Claude Code';
    SetArrayLength(RequiredCommandValues, 1);
    RequiredCommandValues[0] := 'AIGumball';
  end
  else
  begin
    PluginName := 'Rook';
    Description := 'Rook for Rhino 3D - HTTP server enabling AI-powered CAD operations';
    SetArrayLength(RequiredCommandValues, 5);
    RequiredCommandValues[0] := 'RestartRookChatService';
    RequiredCommandValues[1] := 'ShowRookChat';
    RequiredCommandValues[2] := 'ShowRookKnowledgeGraph';
    RequiredCommandValues[3] := 'ShowRookVision';
    RequiredCommandValues[4] := 'UVBoxMapping';
  end;

  RegPath := '\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\' + Guid;

  SetArrayLength(RequiredStringValues, 16);
  RequiredStringValues[0] := 'Name';
  RequiredStringValues[1] := PluginName;
  RequiredStringValues[2] := 'EnglishName';
  RequiredStringValues[3] := PluginName;
  RequiredStringValues[4] := 'Organization';
  RequiredStringValues[5] := 'Bringfire';
  RequiredStringValues[6] := 'Description';
  RequiredStringValues[7] := Description;
  RequiredStringValues[8] := 'RegPath';
  RequiredStringValues[9] := RegPath;
  RequiredStringValues[10] := 'WebSite';
  RequiredStringValues[11] := 'https://github.com/bringfire/rook-release';
  RequiredStringValues[12] := 'UpdateURL';
  RequiredStringValues[13] := 'https://github.com/bringfire/rook-release/releases';
  RequiredStringValues[14] := 'PlugIn\FileName';
  RequiredStringValues[15] := FileName;

  for I := 0 to (GetArrayLength(RequiredStringValues) div 2) - 1 do
  begin
    if RequiredStringValues[I * 2] = 'PlugIn\FileName' then
    begin
      if not VerifyRegistryStringValue(BaseKey + '\PlugIn', 'FileName', RequiredStringValues[(I * 2) + 1]) then
        Exit;
    end
    else if not VerifyRegistryStringValue(BaseKey, RequiredStringValues[I * 2], RequiredStringValues[(I * 2) + 1]) then
      Exit;
  end;

  if (IsDotNet = 1) and RegValueExists(HKCU, BaseKey, 'RuiFile') then
  begin
    Log('Rhino plugin verification failed: obsolete RuiFile value remains at ' + BaseKey);
    Exit;
  end;

  if not VerifyRegistryDWordValue(BaseKey, 'Type', 16) then
    Exit;
  if not VerifyRegistryDWordValue(BaseKey, 'IsDotNETPlugIn', IsDotNet) then
    Exit;
  if not VerifyRegistryDWordValue(BaseKey, 'LoadMode', LoadMode) then
    Exit;
  if not VerifyRegistryDWordValue(BaseKey, 'AddToHelpMenu', 0) then
    Exit;
  if not VerifyRegistryDWordValue(BaseKey, 'DirectoryInstall', 0) then
    Exit;

  for I := 0 to GetArrayLength(RequiredCommandValues) - 1 do
  begin
    if not VerifyCommandListValue(Guid, RequiredCommandValues[I]) then
      Exit;
  end;

  Result := True;
end;

procedure VerifyRhinoPluginInstall();
var
  NativePath: String;
  CompanionPath: String;
  CompanionNet8Path: String;
  CompanionNet48Path: String;
begin
  if not WizardIsComponentSelected('plugins') then
    Exit;

  NativePath := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.rhp');
  CompanionPath := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp');
  CompanionNet8Path := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp');
  CompanionNet48Path := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp');

  if not FileExists(CompanionNet8Path) then
  begin
    Log('Rhino plugin verification failed: net8.0 companion file missing: ' + CompanionNet8Path);
    MsgBox(
      'Rook copied the plug-in files, but the .NET 8 companion payload is missing.' + #13#10 + #13#10 +
      'Standalone Rhino and Rhino.Inside/Revit .NET 8 hosts will not be able to load the runtime-specific Rook payload. Rebuild the installer from all companion target frameworks and reinstall.',
      mbError, MB_OK);
    Exit;
  end;

  if not FileExists(CompanionNet48Path) then
  begin
    Log('Rhino plugin verification failed: net48 companion file missing: ' + CompanionNet48Path);
    MsgBox(
      'Rook copied the plug-in files, but the .NET Framework companion payload is missing.' + #13#10 + #13#10 +
      'Rhino.Inside.Revit on .NET Framework hosts will not be able to load Rook. Rebuild the installer from both companion target frameworks and reinstall.',
      mbError, MB_OK);
    Exit;
  end;

  if not (
    VerifyPluginRegistration('A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906', NativePath, 0, 1) and
    VerifyPluginRegistration('B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B', CompanionPath, 1, 2)) then
  begin
    MsgBox(
      'Rook copied the plug-in files, but Rhino registration verification failed.' + #13#10 + #13#10 +
      'This usually means the installer was run from a different Windows user account than the one that runs Rhino, or registry writes were blocked.' + #13#10 + #13#10 +
      'Run the installer again as the same Windows user who runs Rhino/Revit. Then restart Rhino after installation.',
      mbError, MB_OK);
  end
  else
  begin
    Log('Rook Rhino plugin registration verified for current Windows user. Restart Rhino after installation.');
  end;
end;

// --- Setup lifecycle ---

function InitializeSetup(): Boolean;
begin
  Result := True;

  if IsRhinoHostRunning() then
  begin
    MsgBox(
      'Close Rhino, Rhino.Inside.Revit, and Revit before installing Rook.' + #13#10 + #13#10 +
      'Rhino reads plug-in registry registration at startup. Installing while Rhino or Revit is running can leave this session unaware of Rook until users manually repair it in PluginManager.',
      mbCriticalError, MB_OK);
    Result := False;
    Exit;
  end;

  // Check Rhino 8
  if not RhinoInstalled() then
  begin
    if MsgBox('Rhino 8 was not detected on this system.' + #13#10 + #13#10 + 'Rook requires Rhino 8 to function. Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;

  if not WizardSilent then
  begin
    MsgBox(
      'Rook installs Rhino plug-ins for the current Windows user only.' + #13#10 + #13#10 +
      'If an administrator installs Rook for someone else, Rhino will not see the plug-ins in that user profile.' + #13#10 + #13#10 +
      'Run this installer as the same Windows user who runs Rhino/Revit.',
      mbInformation, MB_OK);
  end;

end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';

  if (WizardIsComponentSelected('chirp') or WizardIsComponentSelected('claude') or WizardIsComponentSelected('codex')) and (not WizardIsComponentSelected('mcp')) then
  begin
    Result := 'The Claude, Codex, and Chirp options require the "Python MCP Server" component.' + #13#10 + #13#10 + 'Go back and enable "Python MCP Server", or uncheck the dependent options.';
    Exit;
  end;

  if PostInstallSelected() then
  begin
    if not RunRookProcessPreflight(Result) then
      Exit;
  end;
end;

procedure RecordPrivatePythonPath();
begin
  SaveStringToFile(
    ExpandConstant('{app}') + '\python_path.txt',
    ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe'),
    False);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    RookPreflightResweepEnabled := False;

    RecordPrivatePythonPath();

    if not RunPostInstallSetup() then
      Abort;

    VerifyRhinoPluginInstall();
  end;
end;

procedure CurInstallProgressChanged(CurProgress, MaxProgress: Integer);
var
  CurrentTick: Cardinal;
  ResultCode: Integer;
  ResweepOk: Boolean;
  FailureMessage: String;
begin
  if not RookPreflightResweepEnabled then
    Exit;

  if RookPreflightHelperPath = '' then
    Exit;

  CurrentTick := GetTickCount;
  if (RookPreflightLastSweepTick <> 0) and ((CurrentTick - RookPreflightLastSweepTick) < 10000) then
    Exit;

  RookPreflightLastSweepTick := CurrentTick;
  ResultCode := 40;
  ResweepOk := RunRookPreflightHelper('close', '', ResultCode);
  if ResweepOk then
    Log('Rook process preflight re-sweep exit code: ' + IntToStr(ResultCode))
  else
    Log('Rook process preflight re-sweep failed to launch; assumed exit code: ' + IntToStr(ResultCode));

  if ((not ResweepOk) or (ResultCode <> 0)) then
  begin
    RookPreflightResweepEnabled := False;
    FailureMessage := RookPreflightFailureMessage(ResultCode);
    Log('Rook process preflight re-sweep failed: ' + FailureMessage);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PythonExe: String;
  PythonPathFile: String;
  Lines: TArrayOfString;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Run cleanup before files are deleted
    PythonExe := ExpandConstant('{localappdata}\Rook\python\cpython-3.11.9\python.exe');
    PythonPathFile := ExpandConstant('{app}') + '\python_path.txt';
    if LoadStringsFromFile(PythonPathFile, Lines) then
    begin
      if GetArrayLength(Lines) > 0 then
      begin
        PythonExe := Lines[0];
      end;
    end;

    if FileExists(PythonExe) then
    begin
      Exec(PythonExe, '"' + ExpandConstant('{app}') + '\post_install.py" --uninstall', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
