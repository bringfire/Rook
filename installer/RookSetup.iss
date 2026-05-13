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
#define MyAppVersion "1.5.5"
#define MyAppPublisher "Bringfire"
#define MyAppURL "https://github.com/bringfire/Rook"

; Paths relative to this .iss file — adjust if your build layout differs.
; These assume a Release build has been run before packaging.
#define RepoRoot ".."
#define NativePlugin RepoRoot + "\src\RookNative\bin\Release\x64\RookNative.rhp"
#define NativePdb    RepoRoot + "\src\RookNative\bin\Release\x64\RookNative.pdb"
#define CompanionDir RepoRoot + "\src\Rook\bin\Release\net7.0"
#define McpServerDir RepoRoot + "\mcp_server"
#define KnowledgeDir RepoRoot + "\knowledge"
#define ScriptsDir   RepoRoot + "\scripts"
#define FfmpegDir   RepoRoot + "\third_party\ffmpeg"
#define ClaudeSkillsDir RepoRoot + "\.claude\skills"
#define CodexSkillsDir  RepoRoot + "\.agents\skills"
#define ClaudeAgentsDir RepoRoot + "\.claude\agents"
#define PluginDir    RepoRoot + "\.claude-plugin"
#define HooksDir     RepoRoot + "\hooks"
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
Name: "claude"; Description: "Claude Code / Desktop Configuration + user skills/agents (requires MCP)"; Types: full custom
Name: "codex"; Description: "OpenAI Codex CLI Configuration + user skills (requires MCP)"; Types: full custom

; ---------------------------------------------------------------------------
; Files
; ---------------------------------------------------------------------------

[Files]
; --- Rhino Plugins ---
; C++ native plugin (x64 only) — required public Rhino surface
Source: "{#NativePlugin}"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#NativePdb}"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion skipifsourcedoesntexist

; C# companion plugin (net7.0) + dependencies
Source: "{#CompanionDir}\Rook.rhp"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionDir}\Rook.rui"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionDir}\Rook.deps.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionDir}\Rook.runtimeconfig.json"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionDir}\*.dll"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"; Components: plugins; Flags: ignoreversion
Source: "{#CompanionDir}\runtimes\*"; DestDir: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\runtimes"; Components: plugins; Flags: ignoreversion recursesubdirs createallsubdirs

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

; --- Optional Claude/Codex agent payloads ---
Source: "{#PluginDir}\plugin.json"; DestDir: "{app}\.claude-plugin"; Components: claude; Flags: ignoreversion
Source: "{#PluginDir}\marketplace.json"; DestDir: "{app}\.claude-plugin"; Components: claude; Flags: ignoreversion
Source: "{#ClaudeSkillsDir}\*"; DestDir: "{app}\.claude\skills"; Components: claude; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#CodexSkillsDir}\*"; DestDir: "{app}\.agents\skills"; Components: codex; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ClaudeAgentsDir}\*"; DestDir: "{app}\.claude\agents"; Components: claude; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#HooksDir}\hooks.json"; DestDir: "{app}\hooks"; Components: claude; Flags: ignoreversion
Source: "{#RepoRoot}\scripts\session-start.sh"; DestDir: "{app}\scripts"; Components: claude; Flags: ignoreversion

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
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\PlugIn"; ValueType: string; ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.rhp"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "Type"; ValueData: "16"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "IsDotNETPlugIn"; ValueData: "0"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906"; ValueType: dword; ValueName: "LoadMode"; ValueData: "1"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\A38E0E8F-E06E-40D2-A6BD-7EDBC2CB1906\CommandList"; Flags: uninsdeletekey; Components: plugins

; Rook Companion (C# plugin) — load when needed
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: string; ValueName: "Name"; ValueData: "Rook"; Components: plugins; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\PlugIn"; ValueType: string; ValueName: "FileName"; ValueData: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\Rook.rhp"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "Type"; ValueData: "16"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "IsDotNETPlugIn"; ValueData: "1"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "LoadMode"; ValueData: "2"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B"; ValueType: dword; ValueName: "LoadProtection"; ValueData: "1"; Components: plugins
Root: HKCU; Subkey: "Software\McNeel\Rhinoceros\8.0\Plug-Ins\B7E4A8C9-1F62-4C7E-9A2B-5D4E8F1C3A7B\CommandList"; Flags: uninsdeletekey; Components: plugins

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
Type: filesandordirs; Name: "{userappdata}\McNeel\Rhinoceros\8.0\Plug-ins\RookNative"
Type: files; Name: "{localappdata}\Rook\CLAUDE.md"
Type: files; Name: "{localappdata}\Rook\AGENTS.md"
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

  // Check Rhino 8
  if not RhinoInstalled() then
  begin
    if MsgBox('Rhino 8 was not detected on this system.' + #13#10 + #13#10 + 'Rook requires Rhino 8 to function. Continue anyway?', mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;

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
