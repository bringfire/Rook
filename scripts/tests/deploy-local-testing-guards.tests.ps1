$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$DeploySkill = Join-Path $RepoRoot '.agents\skills\deploy-local-testing\SKILL.md'

function Assert-True {
    param(
        [bool]$Condition,
        [string]$Message
    )

    if (-not $Condition) {
        throw $Message
    }
}

function Assert-Contains {
    param(
        [string]$Text,
        [string]$Expected,
        [string]$Message
    )

    Assert-True -Condition $Text.Contains($Expected) -Message $Message
}

function Assert-NotContains {
    param(
        [string]$Text,
        [string]$Unexpected,
        [string]$Message
    )

    Assert-True -Condition (-not $Text.Contains($Unexpected)) -Message $Message
}

function Test-DeployScriptSelectsExplicitMsvcToolset {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '$vcvarsVersion = (($VCToolsVersion -split' -Message 'Local deploy must derive a vcvars version from the selected MSVC toolset.'
    Assert-Contains -Text $content -Expected 'vcvarsall.bat" x64 -vcvars_ver=$vcvarsVersion' -Message 'Local deploy must explicitly select the MSVC toolset for MFC builds.'
    Assert-Contains -Text $content -Expected '/p:VCToolsVersion=$VCToolsVersion' -Message 'Local deploy must pass VCToolsVersion through to MSBuild.'
}

function Test-DeployScriptSyncsChirpFromSiblingRepo {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Resolve-ChirpSourceRoot' -Message 'Local deploy must resolve Chirp source through an explicit helper.'
    Assert-Contains -Text $content -Expected 'git -C $RepoRoot rev-parse --git-common-dir' -Message 'Local deploy must resolve the canonical repo root when running from a git worktree.'
    Assert-Contains -Text $content -Expected '$ChirpSourceRoot = Resolve-ChirpSourceRoot -RepoRoot $RepoRoot' -Message 'Local deploy must use the resolved Chirp repo as the source payload.'
    Assert-Contains -Text $content -Expected '$ChirpInstallRoot = Join-Path $InstallRoot ''chirp''' -Message 'Local deploy must install Chirp under the AppData app payload.'
    Assert-Contains -Text $content -Expected 'function Sync-ChirpPayload' -Message 'Local deploy must have an explicit Chirp sync step.'
    Assert-Contains -Text $content -Expected 'Sync-Directory $ChirpSourceRoot $ChirpInstallRoot' -Message 'Local deploy must mirror sibling Chirp into AppData.'
    Assert-Contains -Text $content -Expected 'Chirp_API_Key.txt' -Message 'Local deploy must preserve local Chirp secrets by excluding key files.'
}

function Test-DeployScriptInstallsChirpByDefault {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$SkipChirpInstall' -Message 'A fast Chirp skip may exist, but must be explicit.'
    Assert-Contains -Text $content -Expected '$args += @(''--chirp-dir'', $ChirpInstallRoot)' -Message 'Local deploy must pass Chirp into post_install.py.'
    Assert-Contains -Text $content -Expected 'if ($SkipChirpInstall)' -Message 'Skipping Chirp installation must require an explicit flag.'
    Assert-NotContains -Text $content -Unexpected '$args += @(''--chirp-dir'', $ChirpInstallRoot, ''--skip-chirp-install'')' -Message 'Local deploy must not skip Chirp install by default.'
}

function Test-DeployScriptVerifiesChirpRuntimeAndConfig {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Test-ChirpRuntime' -Message 'Local deploy must verify the installed Chirp runtime.'
    Assert-Contains -Text $content -Expected '.venv\Scripts\python.exe' -Message 'Local deploy must require the installed Chirp venv Python.'
    Assert-Contains -Text $content -Expected 'import chirp' -Message 'Local deploy must prove Chirp imports from the installed venv.'
}

function Test-DeployScriptVerifiesRookImportOrigin {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'expected_rook_prefix' -Message 'Local deploy must compute the expected installed rook package path.'
    Assert-Contains -Text $content -Expected 'rook imported from stale location' -Message 'Local deploy must reject stale repo/worktree rook imports.'
    Assert-Contains -Text $content -Expected 'mcp_server\src\rook' -Message 'Local deploy must anchor rook imports to the installed AppData MCP source tree.'
}

function Test-DeployScriptParsesMcpConfigs {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Test-McpClientConfigs' -Message 'Local deploy must structurally verify MCP client config entries.'
    Assert-Contains -Text $content -Expected 'function Assert-RookMcpEntry' -Message 'Local deploy must validate the Rook MCP entry fields.'
    Assert-Contains -Text $content -Expected 'function Get-JsonRookMcpEntry' -Message 'Local deploy must parse JSON MCP config entries without PowerShell case-insensitive duplicate-key failure.'
    Assert-Contains -Text $content -Expected 'function Get-CodexRookMcpEntry' -Message 'Local deploy must parse the Codex TOML Rook MCP section.'
    Assert-Contains -Text $content -Expected 'json.loads(Path(sys.argv[1]).read_text' -Message 'Local deploy must use Python JSON extraction for Claude config files.'
    Assert-Contains -Text $content -Expected 'mcpServers.rook' -Message 'Local deploy must extract the exact Rook MCP entry from JSON configs.'
    Assert-Contains -Text $content -Expected 'ROOK_INSTALL_ROOT = $expectedInstallRoot' -Message 'Local deploy must verify ROOK_INSTALL_ROOT points at AppData app.'
    Assert-Contains -Text $content -Expected 'ROOK_DATA_DIR = $expectedDataRoot' -Message 'Local deploy must verify ROOK_DATA_DIR points at AppData data.'
    Assert-Contains -Text $content -Expected 'ROOK_MODE = ''release''' -Message 'Local deploy must verify ROOK_MODE is release.'
    Assert-Contains -Text $content -Expected 'CHIRP_HOME = $expectedChirpHome' -Message 'Local deploy must verify CHIRP_HOME points at AppData Chirp.'
    Assert-Contains -Text $content -Expected 'Rook MCP command mismatch' -Message 'Local deploy must reject stale MCP command paths.'
    Assert-Contains -Text $content -Expected 'Rook MCP cwd mismatch' -Message 'Local deploy must reject stale MCP cwd paths.'
}

function Test-DeployScriptVerifiesChatManifest {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Test-ChatServiceManifest' -Message 'Local deploy must verify the Rhino chat panel manifest.'
    Assert-Contains -Text $content -Expected 'RookChatService.json' -Message 'Local deploy must read the deployed chat service manifest.'
    Assert-Contains -Text $content -Expected 'Chat service pythonPath mismatch' -Message 'Local deploy must reject stale chat service Python paths.'
    Assert-Contains -Text $content -Expected 'Chat service workingDirectory mismatch' -Message 'Local deploy must reject stale chat service working directories.'
    Assert-Contains -Text $content -Expected 'rook.agent.chat.service_main' -Message 'Local deploy must verify the chat service module.'
    Assert-Contains -Text $content -Expected 'pythonPathEntries' -Message 'Local deploy must verify the chat service source path entry.'
}

function Test-DeployScriptLiveSmokeIsExplicit {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$LiveSmoke' -Message 'Local deploy must expose an explicit live smoke flag.'
    Assert-Contains -Text $content -Expected '-LiveSmoke requires -PayloadOnly -AllowRunning' -Message 'Live smoke must be explicit and must not run during DLL-copy deploy.'
    Assert-Contains -Text $content -Expected 'function Test-LiveSmoke' -Message 'Local deploy must implement a live smoke gate.'
    Assert-Contains -Text $content -Expected '"rhino_ping"' -Message 'Live smoke must verify Rhino connectivity.'
    Assert-Contains -Text $content -Expected '"gh_status"' -Message 'Live smoke must verify Grasshopper connectivity.'
    Assert-Contains -Text $content -Expected '"chirp_create"' -Message 'Live smoke must exercise the Chirp creation path.'
    Assert-Contains -Text $content -Expected '"deterministic_only": True' -Message 'Live smoke must exercise Chirp without external LLM/API-key dependency.'
    Assert-Contains -Text $content -Expected 'compilation_errors' -Message 'Live smoke must fail if chirp_create returns component compilation errors.'
    Assert-Contains -Text $content -Expected 'created Chirp component has Grasshopper errors' -Message 'Live smoke must check gh_errors for the created component.'
    Assert-Contains -Text $content -Expected 'gh_undo cleanup failed' -Message 'Live smoke must fail if cleanup undo fails.'
    Assert-Contains -Text $content -Expected 'Live Rhino/Grasshopper/Chirp smoke not run' -Message 'Default deploy must not claim live functionality when live smoke is skipped.'
}

function Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks {
    $content = Get-Content -Path $DeploySkill -Raw

    Assert-Contains -Text $content -Expected 'Use the repo script as the authority' -Message 'Skill must keep the script authoritative.'
    Assert-Contains -Text $content -Expected '-LiveSmoke' -Message 'Skill must document the live smoke gate.'
    Assert-Contains -Text $content -Expected 'syncs sibling `..\Chirp`' -Message 'Skill must state that default deploy syncs sibling Chirp.'
    Assert-Contains -Text $content -Expected 'Do not claim live plugin capability unless `-LiveSmoke` passes' -Message 'Skill must prevent false live-capability claims.'
    Assert-Contains -Text $content -Expected 'scripts\validate-local-testing-stack.ps1 -ReleaseReadiness' -Message 'Skill must point release-readiness proof at the stack validator.'
    Assert-Contains -Text $content -Expected 'Only `scripts\validate-local-testing-stack.ps1 -ReleaseReadiness` may justify the phrase release-readiness proven' -Message 'Skill must preserve strict pass/fail language.'
}

Test-DeployScriptSelectsExplicitMsvcToolset
Test-DeployScriptSyncsChirpFromSiblingRepo
Test-DeployScriptInstallsChirpByDefault
Test-DeployScriptVerifiesChirpRuntimeAndConfig
Test-DeployScriptVerifiesRookImportOrigin
Test-DeployScriptParsesMcpConfigs
Test-DeployScriptVerifiesChatManifest
Test-DeployScriptLiveSmokeIsExplicit
Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks

Write-Host 'Local testing deploy guard tests passed.'
