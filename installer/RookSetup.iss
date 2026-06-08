; -- RookSetup.iss --
; Rook Installer — AI Bridge for Rhino 3D & Grasshopper
;
; Installs:
;   1. RookNative.rhp (C++ plugin) + Rook.rhp (C# companion) → Rhino plugin dir
;   2. Registers both plugins in Rhino 8 registry
;   3. Python MCP server payload + knowledge stores
;   4. Chirp adapter service (venv + pip install) for LLM-powered GH components
;   5. Claude Code / Claude Desktop / Codex user-scope MCP configuration + skills
;   6. Claude Code user agents
;
; Build with: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" RookSetup.iss
; Or open in Inno Setup GUI and press Ctrl+F9.

#define MyAppName "Rook"
#define MyAppVersion "1.5.9"
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
LicenseFile={#RepoRoot}\LICENSE
InfoBeforeFile=pre-install-readme.txt

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
Name: "mcp"; Description: "Python MCP Server (requires Python 3.10+)"; Types: full custom
Name: "chirp"; Description: "Chirp — LLM-powered Grasshopper components (requires MCP + Python 3.10+)"; Types: full custom
Name: "knowledge"; Description: "Knowledge Stores (commands + Grasshopper)"; Types: full custom
Name: "claude"; Description: "Claude Code / Claude Desktop MCP configuration (requires MCP)"; Types: full custom
Name: "codex"; Description: "OpenAI Codex CLI MCP configuration + curated skills (requires MCP)"; Types: full custom

; ---------------------------------------------------------------------------
; Files
; ---------------------------------------------------------------------------

[Files]
; --- Rhino Plugins ---
; C++ native plugin (x64 only) — required public Rhino surface
Source: "{#NativePlugin}"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#NativePdb}"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion skipifsourcedoesntexist

; C# companion plugin: package sibling runtime payloads for direct-registry
; install smoke validation. Release is blocked until Rhino proves which physical
; Rook.rhp path it loads for standalone and Rhino.Inside hosts.
Source: "{#CompanionNet8Dir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\Rook.rui"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\Rook.deps.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\Rook.runtimeconfig.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\*.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet8Dir}\runtimes\*"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\runtimes"; Components: plugins; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "{#CompanionNet7Dir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\Rook.rui"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\Rook.deps.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\Rook.runtimeconfig.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\*.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet7Dir}\runtimes\*"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\runtimes"; Components: plugins; Flags: ignoreversion recursesubdirs createallsubdirs

Source: "{#CompanionNet48Dir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionNet48Dir}\Rook.rui"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48"; Components: plugins; Flags: ignoreversion
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

; --- Post-install setup script (always included, used by [Run]) ---
Source: "post_install.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "rook-icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; --- Docs ---
Source: "{#RepoRoot}\QUICK_START.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\AGENT_SETUP.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\BUILDING.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#RepoRoot}\LICENSE"; DestDir: "{app}"; Flags: ignoreversion

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
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "RuiFile"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "RegPath"; ValueData: "\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn"; ValueType: string; ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rhp"; Components: plugins
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
; Post-install: run Python setup
; ---------------------------------------------------------------------------

[Run]
Filename: "{code:GetPythonPath}"; Parameters: """{app}\post_install.py"" --install-dir ""{app}"" --runtime-root ""{localappdata}\Rook"" --mcp-server-dir ""{app}\mcp_server"" {code:GetChirpArgs} {code:GetClaudeArgs} {code:GetCodexArgs} {code:GetPluginsArgs}"; StatusMsg: "Setting up Python MCP server, Chirp, and Claude/Codex configuration..."; Components: mcp chirp claude codex; Flags: runhidden waituntilterminated; Check: PythonFound

; ---------------------------------------------------------------------------
; Uninstall cleanup
; ---------------------------------------------------------------------------

[UninstallDelete]
Type: filesandordirs; Name: "{app}\mcp_server"
Type: filesandordirs; Name: "{app}\chirp"
Type: filesandordirs; Name: "{app}\knowledge"
Type: filesandordirs; Name: "{localappdata}\Rook\app"
Type: filesandordirs; Name: "{localappdata}\Rook\venv"
Type: filesandordirs; Name: "{localappdata}\Rook\data"
Type: filesandordirs; Name: "{localappdata}\Rook\logs"
Type: filesandordirs; Name: "{localappdata}\Rook\discovery"
Type: filesandordirs; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
Type: filesandordirs; Name: "{userappdata}\Rook"
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
  PythonPath: String;
  PythonDetected: Boolean;
  ApiKeyPage: TInputQueryWizardPage;

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
  RuiFile: String;
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
    RuiFile := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rui');
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

  if (IsDotNet = 1) and (not VerifyRegistryStringValue(BaseKey, 'RuiFile', RuiFile)) then
    Exit;

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
  CompanionPath := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net7.0\Rook.rhp');
  CompanionNet8Path := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net8.0\Rook.rhp');
  CompanionNet48Path := ExpandConstant('{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\net48\Rook.rhp');

  if not FileExists(CompanionNet8Path) then
  begin
    Log('Rhino plugin verification failed: net8.0 companion file missing: ' + CompanionNet8Path);
    MsgBox(
      'Rook copied the plug-in files, but the .NET 8 companion payload is missing.' + #13#10 + #13#10 +
      'Rhino.Inside.Revit on .NET 8 hosts will not be able to load the runtime-specific Rook payload. Rebuild the installer from all companion target frameworks and reinstall.',
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

// --- API Key wizard page ---

procedure InitializeWizard();
begin
  ApiKeyPage := CreateInputQueryPage(wpSelectComponents,
    'API Key Configuration',
    'Enter your Anthropic API key to enable AI-powered features.',
    'This key powers AI chat, Chirp components, and knowledge consolidation.' + #13#10 + #13#10 + 'Leave blank to configure later via .env files.' + #13#10 + 'Get your key at: console.anthropic.com/settings/keys');
  ApiKeyPage.Add('Anthropic API Key (sk-ant-...):', True);
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  // Only show the API key page when MCP or Chirp is selected
  if PageID = ApiKeyPage.ID then
    Result := not (WizardIsComponentSelected('mcp') or WizardIsComponentSelected('chirp'));
end;

procedure WriteEnvFile(const Dir, ApiKey: String);
var
  Content: String;
begin
  Content := '# Auto-generated by Rook installer' + #13#10 + 'ANTHROPIC_API_KEY=' + ApiKey + #13#10;
  ForceDirectories(Dir);
  SaveStringToFile(Dir + '\.env', Content, False);
  Log('Wrote .env to ' + Dir);
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

  MsgBox(
    'Rook installs Rhino plug-ins for the current Windows user only.' + #13#10 + #13#10 +
    'If an administrator installs Rook for someone else, Rhino will not see the plug-ins in that user profile.' + #13#10 + #13#10 +
    'Run this installer as the same Windows user who runs Rhino/Revit.',
    mbInformation, MB_OK);

  // Detect Python
  FindPython();
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';

  if (WizardIsComponentSelected('mcp') or WizardIsComponentSelected('chirp')) and (not PythonDetected) then
  begin
    Result := 'Python 3.10+ is required for the MCP server and Chirp but was not found.' + #13#10 + 'Please install Python from https://www.python.org/downloads/ and try again.' + #13#10 + #13#10 + 'Or go back and uncheck "Python MCP Server" and "Chirp" to install plugins only.';
    Exit;
  end;

  if (WizardIsComponentSelected('chirp') or WizardIsComponentSelected('claude') or WizardIsComponentSelected('codex')) and (not WizardIsComponentSelected('mcp')) then
  begin
    Result := 'The Claude, Codex, and Chirp options require the "Python MCP Server" component.' + #13#10 + #13#10 + 'Go back and enable "Python MCP Server", or uncheck the dependent options.';
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ApiKey: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Write .env files with API key if the user provided one
    ApiKey := ApiKeyPage.Values[0];
    if ApiKey <> '' then
    begin
      if WizardIsComponentSelected('mcp') then
        WriteEnvFile(ExpandConstant('{app}') + '\mcp_server', ApiKey);
      if WizardIsComponentSelected('chirp') then
        WriteEnvFile(ExpandConstant('{app}') + '\chirp', ApiKey);
    end;

    // Save resolved Python path so uninstall can run cleanup
    if PythonDetected then
      SaveStringToFile(ExpandConstant('{app}') + '\python_path.txt', PythonPath, False);

    if PythonDetected and (WizardIsComponentSelected('mcp') or WizardIsComponentSelected('chirp') or WizardIsComponentSelected('claude')) then
      Log('Post-install: setup completed via post_install.py')
    else if not PythonDetected then
      Log('Post-install: Python not found, MCP server setup skipped');

    VerifyRhinoPluginInstall();
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  PythonFile: String;
  Lines: TArrayOfString;
  ResultCode: Integer;
begin
  if CurUninstallStep = usUninstall then
  begin
    // Run cleanup before files are deleted
    PythonFile := ExpandConstant('{app}') + '\python_path.txt';
    if LoadStringsFromFile(PythonFile, Lines) and (GetArrayLength(Lines) > 0) and FileExists(Lines[0]) then
    begin
      Exec(Lines[0], '"' + ExpandConstant('{app}') + '\post_install.py" --uninstall', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode);
    end;
  end;
end;
