$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$RegisterSuiteScript = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
$RegisterCompanionScript = Join-Path $RepoRoot 'scripts\register-companion.ps1'
$DeploySkill = Join-Path $RepoRoot '.agents\skills\deploy-local-testing\SKILL.md'
$DoctorScript = Join-Path $RepoRoot 'scripts\rook-dev-doctor.ps1'
$AgentSetup = Join-Path $RepoRoot 'AGENT_SETUP.md'

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

function Assert-Before {
    param(
        [string]$Text,
        [string]$First,
        [string]$Second,
        [string]$Message
    )

    $firstIndex = $Text.IndexOf($First, [System.StringComparison]::Ordinal)
    $secondIndex = $Text.IndexOf($Second, [System.StringComparison]::Ordinal)
    Assert-True -Condition ($firstIndex -ge 0) -Message "Missing first marker for order assertion: $First"
    Assert-True -Condition ($secondIndex -ge 0) -Message "Missing second marker for order assertion: $Second"
    Assert-True -Condition ($firstIndex -lt $secondIndex) -Message $Message
}

function Get-FunctionBodyText {
    param(
        [string]$Text,
        [string]$FunctionName
    )

    $functionMarker = "function $FunctionName"
    $functionStart = $Text.IndexOf($functionMarker, [System.StringComparison]::Ordinal)
    Assert-True -Condition ($functionStart -ge 0) -Message "Missing function marker: $functionMarker"

    $nextFunctionStart = $Text.IndexOf("`nfunction ", $functionStart + $functionMarker.Length, [System.StringComparison]::Ordinal)
    if ($nextFunctionStart -lt 0) {
        return $Text.Substring($functionStart)
    }

    return $Text.Substring($functionStart, $nextFunctionStart - $functionStart)
}

function Get-TextBeforeNextMarker {
    param(
        [string]$Text,
        [string]$StartMarker,
        [string]$EndMarker
    )

    $startIndex = $Text.IndexOf($StartMarker, [System.StringComparison]::Ordinal)
    Assert-True -Condition ($startIndex -ge 0) -Message "Missing start marker: $StartMarker"

    $endIndex = $Text.IndexOf($EndMarker, $startIndex + $StartMarker.Length, [System.StringComparison]::Ordinal)
    Assert-True -Condition ($endIndex -ge 0) -Message "Missing end marker after $StartMarker`: $EndMarker"

    return $Text.Substring($startIndex, $endIndex - $startIndex)
}

function Test-DevDoctorScriptContract {
    Assert-True -Condition (Test-Path $DoctorScript) -Message 'Dev doctor script must exist at scripts\rook-dev-doctor.ps1.'

    $content = Get-Content -Path $DoctorScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$Strict' -Message 'Dev doctor must expose a -Strict switch.'
    Assert-Contains -Text $content -Expected 'function Write-CheckResult' -Message 'Dev doctor must report checks through one explicit result helper.'
    Assert-Contains -Text $content -Expected 'PASS' -Message 'Dev doctor must print PASS statuses.'
    Assert-Contains -Text $content -Expected 'WARN' -Message 'Dev doctor must print WARN statuses.'
    Assert-Contains -Text $content -Expected 'FAIL' -Message 'Dev doctor must print FAIL statuses.'
    Assert-Contains -Text $content -Expected 'OCCT_ROOT' -Message 'Dev doctor must report OCCT_ROOT status.'
    Assert-Contains -Text $content -Expected 'fallback' -Message 'Dev doctor must report whether the existing hardcoded OCCT fallback would be used.'
    Assert-Contains -Text $content -Expected 'mcp_server\.venv\Scripts\python.exe' -Message 'Dev doctor must check the repo MCP venv path.'
    Assert-Contains -Text $content -Expected 'python -m rook' -Message 'Dev doctor must check stale rook MCP processes.'
    Assert-Contains -Text $content -Expected 'RookChatService.json' -Message 'Dev doctor must report installed chat manifest mode.'
    Assert-Contains -Text $content -Expected '$ManagedCompanionRuntimes = @(''net8.0'', ''net7.0'', ''net48'')' -Message 'Dev doctor must know the managed runtime child manifest folders.'
    Assert-Contains -Text $content -Expected 'Chat manifest root' -Message 'Dev doctor must report the root chat manifest.'
    Assert-Contains -Text $content -Expected 'Chat manifest net8.0' -Message 'Dev doctor must report the net8.0 runtime-child chat manifest.'
    Assert-Contains -Text $content -Expected 'Chat manifest net7.0' -Message 'Dev doctor must report the net7.0 runtime-child chat manifest.'
    Assert-Contains -Text $content -Expected 'Chat manifest net48' -Message 'Dev doctor must report the net48 runtime-child chat manifest.'
    Assert-NotContains -Text $content -Unexpected "'OMIT'" -Message 'Dev doctor must warn for missing chat manifests instead of omitting runtime-child checks.'
    Assert-NotContains -Text $content -Unexpected 'Set-ItemProperty -Path' -Message 'Dev doctor must not write registry values.'
    Assert-NotContains -Text $content -Unexpected 'Remove-Item -LiteralPath' -Message 'Dev doctor must not remove files.'
    Assert-NotContains -Text $content -Unexpected 'New-Item -ItemType Directory' -Message 'Dev doctor must not create directories.'
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
    Assert-Contains -Text $content -Expected 'Join-Path $Contract.WorkingDirectory ''src\rook''' -Message 'Local deploy must anchor rook imports to the active runtime contract source tree.'
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
    Assert-Contains -Text $content -Expected 'Test-ChatServiceManifestAtPath' -Message 'Local deploy must verify each chat manifest path independently.'
    Assert-Contains -Text $content -Expected 'Chat service environment missing' -Message 'Local deploy must verify chat manifest environment blocks.'
    Assert-Contains -Text $content -Expected 'Chat service ROOK_MODE mismatch' -Message 'Local deploy must verify chat manifest runtime mode.'
    Assert-Contains -Text $content -Expected 'Chat service ROOK_PROJECT_ROOT mismatch' -Message 'Local deploy must verify dev chat manifests point at the repo root.'
    Assert-Contains -Text $content -Expected 'Skipping release MCP client config and Chirp venv verification because an explicit dev runtime was selected.' -Message 'Explicit dev runtime mode must not run release-only MCP/Chirp verification.'
}

function Test-DeployScriptSeedsChatEnvWithoutOverwriting {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Copy-EnvFileIfMissing' -Message 'Local deploy must have an explicit helper for seeding local secret files without overwriting them.'
    Assert-Contains -Text $content -Expected 'Join-Path $RepoRoot ''mcp_server\.env''' -Message 'Local deploy must use the repo mcp_server .env as the source for the installed chat service.'
    Assert-Contains -Text $content -Expected 'Join-Path $InstallRoot ''mcp_server\.env''' -Message 'Local deploy must seed the installed chat service mcp_server .env path.'
    Assert-Contains -Text $content -Expected '-not (Test-Path $Destination)' -Message 'Local deploy must preserve an existing installed .env file.'
}

function Test-DeployScriptCopiesAllInstallerPythonModules {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected "Get-ChildItem (Join-Path `$RepoRoot 'installer') -Filter '*.py' -File" -Message 'Local deploy must enumerate every top-level installer Python module.'
    Assert-Contains -Text $content -Expected "Copy-RequiredFile `$_.FullName (Join-Path `$InstallRoot `$_.Name)" -Message 'Local deploy must copy every top-level installer Python module into the AppData app root.'
    Assert-Contains -Text $content -Expected 'python_runtime_install.py' -Message 'Local deploy guard must cover post_install.py sibling module copying.'
    Assert-Contains -Text $content -Expected 'process_rebuild_guard.py' -Message 'Local deploy guard must cover rebuild guard module copying.'
}

function Test-DeployScriptHasExplicitDevRuntimeContract {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$UseRepoVenv' -Message 'Local deploy must expose an explicit repo venv dev-runtime flag.'
    Assert-Contains -Text $content -Expected "[string]`$DevPythonRuntime = ''" -Message 'Local deploy must expose an explicit dev Python runtime path override.'
    Assert-Contains -Text $content -Expected '[switch]$ManifestSmokeOnly' -Message 'Local deploy must expose a non-mutating manifest smoke mode.'
    Assert-Contains -Text $content -Expected 'function Resolve-DeployRuntimeContract' -Message 'Local deploy must resolve runtime paths through one explicit contract helper.'
    Assert-Contains -Text $content -Expected '-UseRepoVenv cannot be combined with -DevPythonRuntime' -Message 'Dev runtime flags must be mutually exclusive.'
    Assert-Contains -Text $content -Expected '-NativeOnly cannot be combined with -UseRepoVenv or -DevPythonRuntime' -Message 'Native-only mode must reject dev-runtime flags instead of validating unused Python paths.'
    Assert-Contains -Text $content -Expected '-LiveSmoke cannot be combined with -UseRepoVenv or -DevPythonRuntime' -Message 'Live smoke must stay release-runtime-only until made contract-aware.'
    Assert-Contains -Text $content -Expected '-ManifestSmokeOnly is only useful with -UseRepoVenv or -DevPythonRuntime' -Message 'Manifest smoke must require an explicit dev runtime.'
    Assert-Contains -Text $content -Expected 'Dev Python runtime not found' -Message 'Dev runtime mode must fail loudly when the requested interpreter is missing.'
    Assert-Contains -Text $content -Expected 'mcp_server\.venv\Scripts\python.exe' -Message 'Repo venv mode must resolve the repository MCP venv explicitly.'
    Assert-Contains -Text $content -Expected 'ROOK_PROJECT_ROOT' -Message 'Dev runtime mode must carry ROOK_PROJECT_ROOT into generated manifests/config.'
    Assert-Contains -Text $content -Expected 'Dev manifest smoke' -Message 'Manifest smoke mode must report the resolved contract.'
    Assert-Contains -Text $content -Expected 'exit 0' -Message 'Manifest smoke mode must exit before deploy mutation.'
    Assert-Contains -Text $content -Expected 'Skipping release post_install.py because an explicit dev runtime was selected.' -Message 'Dev runtime mode must be explicit about bypassing release post_install.'
}

function Test-DeployScriptCopiesOcctRuntimeClosure {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '$OcctFallbackRoot = ''C:\Users\aryan\source\repos\OCCT\build-rook''' -Message 'Local deploy must retain the existing OCCT fallback path without reading vcxproj files.'
    Assert-Contains -Text $content -Expected '$OcctRuntimeDlls = @(' -Message 'Local deploy must use an explicit OCCT runtime DLL list.'
    foreach ($dll in @(
        'TKernel.dll',
        'TKMath.dll',
        'TKG2d.dll',
        'TKG3d.dll',
        'TKGeomBase.dll',
        'TKGeomAlgo.dll',
        'TKBRep.dll',
        'TKTopAlgo.dll',
        'TKPrim.dll',
        'TKBO.dll',
        'TKShHealing.dll'
    )) {
        Assert-Contains -Text $content -Expected "'$dll'" -Message "Local deploy must include measured OCCT runtime DLL $dll."
    }
    Assert-NotContains -Text $content -Unexpected "'TKBool.dll'" -Message 'Local deploy must not add linked-but-not-loaded TKBool.dll in PR 1.'
    Assert-NotContains -Text $content -Unexpected "'TKMesh.dll'" -Message 'Local deploy must not add linked-but-not-loaded TKMesh.dll in PR 1.'
    Assert-Contains -Text $content -Expected 'function Resolve-OcctRuntimeRoot' -Message 'Local deploy must resolve OCCT root through an explicit helper.'
    Assert-Contains -Text $content -Expected '$env:OCCT_ROOT' -Message 'Local deploy must prefer OCCT_ROOT.'
    Assert-Contains -Text $content -Expected '$OcctFallbackRoot' -Message 'Local deploy must fall back to the existing hardcoded OCCT path.'
    Assert-Contains -Text $content -Expected 'OCCT root source:' -Message 'Local deploy must report whether OCCT_ROOT or fallback was used.'
    Assert-Contains -Text $content -Expected 'function Copy-OcctRuntimeDlls' -Message 'Local deploy must copy OCCT runtime DLLs through an explicit helper.'
    Assert-Contains -Text $content -Expected 'Join-Path $resolved.Root ''win64\vc14\bin''' -Message 'Local deploy must copy OCCT DLLs from the resolved runtime bin folder.'
    Assert-Contains -Text $content -Expected 'Copy-RequiredFile $source (Join-Path $PluginDir $dll)' -Message 'Local deploy must copy OCCT DLLs next to RookNative.rhp.'

    $deployNativePayloadBody = Get-FunctionBodyText -Text $content -FunctionName 'Deploy-NativePayload'
    Assert-Before -Text $deployNativePayloadBody -First 'Copy-RequiredFile (Join-Path $nativeDir ''RookNative.rhp'')' -Second 'Copy-OcctRuntimeDlls' -Message 'Local deploy must copy RookNative.rhp before copying the OCCT runtime closure inside Deploy-NativePayload.'
}

function Test-DeployScriptWritesChatManifestToRuntimeChildren {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'function Write-ChatServiceManifests' -Message 'Local deploy must write chat manifests through an explicit helper.'
    Assert-Contains -Text $content -Expected '$targets += Join-Path (Join-Path $PluginDir $runtime) ''RookChatService.json''' -Message 'Local deploy must target every managed runtime child manifest.'
    Assert-Contains -Text $content -Expected 'Set-Content -LiteralPath $manifestPath' -Message 'Local deploy must write each manifest path.'
    Assert-Contains -Text $content -Expected 'foreach ($runtime in $ManagedCompanionRuntimes)' -Message 'Manifest writing and verification must iterate the known managed runtime folders.'
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

function Test-DeployScriptNativeOnlyIsNarrow {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$NativeOnly' -Message 'Local deploy must expose a native-only mode for native route iteration.'
    Assert-Contains -Text $content -Expected 'Native-only deploy surfaces' -Message 'Native-only mode must print affected surfaces before doing work.'
    Assert-Contains -Text $content -Expected '-NativeOnly cannot be combined with -PayloadOnly' -Message 'Native-only and payload-only deploy modes must be mutually exclusive.'
    Assert-Contains -Text $content -Expected 'function Assert-NoRunningRhino' -Message 'Native-only mode must keep a hard Rhino-closed guard.'
    Assert-Contains -Text $content -Expected 'function Assert-NoRunningFullDeployBlockers' -Message 'Full deploy must retain the stricter Rhino and MCP process guard.'
    Assert-Contains -Text $content -Expected 'function Deploy-NativePayload' -Message 'Native-only mode must copy native payload through an explicit helper.'
    Assert-Contains -Text $content -Expected 'function Deploy-CompanionPayload' -Message 'Full deploy must keep companion payload copying explicit and separate from native payload copying.'
    Assert-Contains -Text $content -Expected 'Deploy-NativePayload' -Message 'Native-only mode must deploy the native payload.'
    Assert-Contains -Text $content -Expected 'Register-NativeOnlyPlugins' -Message 'Native-only mode must register against existing companion payload without refreshing app/MCP config.'
    Assert-Contains -Text $content -Expected '-NativeOnlyPreserveCompanion' -Message 'Native-only deploy must delegate preserve-companion registration to the suite registration script.'
    Assert-NotContains -Text $content -Unexpected 'Set-ItemProperty -Path $nativeRegBase' -Message 'Native-only deploy must not duplicate native registry writes.'
    Assert-Contains -Text $content -Expected 'Skipping MCP payload, Chirp payload, post-install config, and MCP client config validation.' -Message 'Native-only mode must state it skips MCP/Chirp/config work.'
    Assert-Contains -Text $content -Expected 'Native-only deploy complete.' -Message 'Native-only mode must have a distinct completion message.'
}

function Test-DeployScriptUsesMultiRuntimeCompanionLayout {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '$ManagedCompanionRuntimes = @(''net8.0'', ''net7.0'', ''net48'')' -Message 'Local deploy must know every managed companion runtime folder.'
    Assert-Contains -Text $content -Expected 'dotnet build (Join-Path $RepoRoot ''src\Rook\Rook.csproj'') -c $Configuration' -Message 'Local deploy must build all companion target frameworks.'
    Assert-Contains -Text $content -Expected '[string]$RevitInstallDir' -Message 'Local deploy must expose an explicit Revit install directory override for RookBIM builds.'
    Assert-Contains -Text $content -Expected 'function Assert-RookBimBuildPrerequisites' -Message 'Local deploy must preflight Revit API assemblies before building RookBIM.'
    Assert-Contains -Text $content -Expected 'Full local deploy builds RookBIM and requires Revit API assemblies.' -Message 'Local deploy must document the intentional Revit API requirement in its error text.'
    Assert-Contains -Text $content -Expected 'pass -RevitInstallDir <path>' -Message 'Local deploy RookBIM prerequisite failure must explain how to use a non-default Revit install.'
    Assert-Contains -Text $content -Expected 'run -NativeOnly for native-only iteration' -Message 'Local deploy RookBIM prerequisite failure must point Rhino-only native iteration at -NativeOnly.'
    Assert-Contains -Text $content -Expected 'dotnet build (Join-Path $RepoRoot ''src\RookBim\RookBim.csproj'') -c $Configuration' -Message 'Local deploy must build RookBIM so the net48 companion payload receives the current RookBim.dll.'
    Assert-Contains -Text $content -Expected '"/p:RevitInstallDir=$rookBimRevitInstallDir"' -Message 'Local deploy must pass the preflighted Revit install path into the RookBIM build.'
    Assert-Contains -Text $content -Expected 'RookBIM build failed.' -Message 'Local deploy must fail clearly when the RookBIM build fails.'
    Assert-Contains -Text $content -Expected 'function Deploy-CompanionRuntimePayload' -Message 'Local deploy must copy companion payloads per runtime child.'
    Assert-Contains -Text $content -Expected 'Copy-RequiredFile (Join-Path $sourceDir ''Rook.runtimeconfig.json'')' -Message 'Local deploy must require .NET Core runtime metadata in runtime-child payloads.'
    Assert-Contains -Text $content -Expected 'Remove-StaleRootCompanionPayload' -Message 'Local deploy must remove stale root-level companion payload files from old installs.'
    Assert-Contains -Text $content -Expected 'Join-Path $PluginDir ''net8.0\Rook.rhp''' -Message 'Local deploy must register the net8.0 child RHP anchor.'
    Assert-NotContains -Text $content -Unexpected '& dotnet build (Join-Path $RepoRoot ''src\Rook\Rook.csproj'') -f net7.0' -Message 'Local deploy must not build only the net7.0 companion target.'
    Assert-NotContains -Text $content -Unexpected '-CompanionRhpPath (Join-Path $PluginDir ''Rook.rhp'')' -Message 'Local deploy must not register a root-level companion RHP.'
    Assert-NotContains -Text $content -Unexpected '-CompanionRhpPath (Join-Path $PluginDir ''net7.0\Rook.rhp'')' -Message 'Full local deploy must not register the net7.0 companion anchor.'
}

function Test-RegisterSuiteSupportsNativeOnlyPreserveCompanion {
    $content = Get-Content -Path $RegisterSuiteScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$NativeOnlyPreserveCompanion' -Message 'Suite registration must expose native-only preserve-companion mode.'
    Assert-Contains -Text $content -Expected '-NativeOnlyPreserveCompanion cannot be combined with -CompanionRhpPath' -Message 'Preserve-companion mode must reject explicit companion path rewrites.'
    Assert-Contains -Text $content -Expected '-NativeOnlyPreserveCompanion cannot be combined with -Unregister' -Message 'Preserve-companion mode must reject unregister mode.'
    Assert-Contains -Text $content -Expected 'Resolve-PreservedCompanionRhpPath' -Message 'Preserve-companion mode must resolve existing companion registration before writing native registration.'
    Assert-Contains -Text $content -Expected 'Native-only preserve-companion registration verified.' -Message 'Preserve-companion mode must report its distinct verification path.'
    Assert-Contains -Text $content -Expected 'changed companion registration unexpectedly' -Message 'Preserve-companion mode must verify companion registration remains unchanged.'
}

function Test-RegisterSuitePrefersNet8CompanionFallback {
    $content = Get-Content -Path $RegisterSuiteScript -Raw

    Assert-Contains -Text $content -Expected '$candidateCompanions = @(' -Message 'Suite registration must keep explicit companion fallback discovery.'
    Assert-Contains -Text $content -Expected 'Join-Path $nativeDir ''net8.0\Rook.rhp''' -Message 'Suite registration must discover net8.0 companion payloads.'
    Assert-Contains -Text $content -Expected 'Join-Path $nativeDir ''net7.0\Rook.rhp''' -Message 'Suite registration must preserve net7.0 fallback compatibility.'
    Assert-Contains -Text $content -Expected 'Join-Path $nativeDir ''Rook.rhp''' -Message 'Suite registration must preserve root-level fallback compatibility.'

    $candidateCompanionsBlock = Get-TextBeforeNextMarker -Text $content -StartMarker '$candidateCompanions = @(' -EndMarker "`n    foreach "
    Assert-Before -Text $candidateCompanionsBlock -First 'Join-Path $nativeDir ''net8.0\Rook.rhp''' -Second 'Join-Path $nativeDir ''net7.0\Rook.rhp''' -Message 'Suite registration must prefer net8.0 before net7.0 within candidate companion fallback discovery.'
    Assert-Before -Text $candidateCompanionsBlock -First 'Join-Path $nativeDir ''net7.0\Rook.rhp''' -Second 'Join-Path $nativeDir ''Rook.rhp''' -Message 'Suite registration must prefer runtime child payloads before root fallback within candidate companion fallback discovery.'
}

function Test-RegisterCompanionAcceptsNet8Runtime {
    $content = Get-Content -Path $RegisterCompanionScript -Raw

    Assert-Contains -Text $content -Expected '$UnsupportedRuntimeMetadataMessage = ''Rook companion runtime metadata must identify a net8.0 or net7.0 build for registration.''' -Message 'Companion registration must describe both supported .NET Core companion TFMs.'
    Assert-Contains -Text $content -Expected 'Test-PathHasExactSegment -Path $Path -Segment ''net8.0''' -Message 'Companion registration must accept net8.0 runtime-child RHP paths.'
    Assert-Contains -Text $content -Expected 'Test-PathHasExactSegment -Path $Path -Segment ''net7.0''' -Message 'Companion registration must retain net7.0 runtime-child RHP path support.'
    Assert-Contains -Text $content -Expected '$tfm -eq ''net8.0''' -Message 'Companion registration must accept net8.0 runtime metadata.'
    Assert-Contains -Text $content -Expected '$tfm -eq ''net7.0''' -Message 'Companion registration must retain net7.0 runtime metadata support.'
    Assert-Contains -Text $content -Expected '$tfm -eq ''net48''' -Message 'Companion registration must keep explicit net48 runtime metadata rejection.'
    Assert-Contains -Text $content -Expected '$UnsupportedNet48CompanionMessage' -Message 'Companion registration must keep the net48-specific rejection path.'
}

function Test-DeployScriptNativeOnlySkipBuildFastPath {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'if (-not $SkipBuild)' -Message 'Native-only mode must honor -SkipBuild for fast iteration after a prior build.'
    Assert-Contains -Text $content -Expected 'Skipping native build because -SkipBuild was specified.' -Message 'Native-only -SkipBuild must make the fast path explicit.'
    Assert-Contains -Text $content -Expected 'Deploy-NativePayload' -Message 'Native-only -SkipBuild must still copy the existing native payload.'
    Assert-Contains -Text $content -Expected 'Skipping MCP payload, Chirp payload, post-install config, and MCP client config validation.' -Message 'Native-only -SkipBuild must still skip MCP/Chirp/config work.'
}

function Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks {
    $content = Get-Content -Path $DeploySkill -Raw

    Assert-Contains -Text $content -Expected 'Use the repo script as the authority' -Message 'Skill must keep the script authoritative.'
    Assert-Contains -Text $content -Expected '-LiveSmoke' -Message 'Skill must document the live smoke gate.'
    Assert-Contains -Text $content -Expected '-NativeOnly' -Message 'Skill must document the native-only development deploy path.'
    Assert-Contains -Text $content -Expected '-RevitInstallDir' -Message 'Skill must document the RookBIM Revit API location override.'
    Assert-Contains -Text $content -Expected 'Default deploy intentionally requires Revit API assemblies for the RookBIM build' -Message 'Skill must document the full-deploy RookBIM/Revit API prerequisite.'
    Assert-Contains -Text $content -Expected 'syncs sibling `..\Chirp`' -Message 'Skill must state that default deploy syncs sibling Chirp.'
    Assert-Contains -Text $content -Expected 'Do not claim live plugin capability unless `-LiveSmoke` passes' -Message 'Skill must prevent false live-capability claims.'
    Assert-Contains -Text $content -Expected 'scripts\validate-local-testing-stack.ps1 -ReleaseReadiness' -Message 'Skill must point release-readiness proof at the stack validator.'
    Assert-Contains -Text $content -Expected 'Only `scripts\validate-local-testing-stack.ps1 -ReleaseReadiness` may justify the phrase release-readiness proven' -Message 'Skill must preserve strict pass/fail language.'
}

function Test-AgentSetupDocumentsDevDeployConvention {
    $content = Get-Content -Path $AgentSetup -Raw

    Assert-Contains -Text $content -Expected '## Developer Machine Convention' -Message 'AGENT_SETUP must document the developer-machine convention.'
    Assert-Contains -Text $content -Expected 'scripts\rook-dev-doctor.ps1' -Message 'AGENT_SETUP must tell developers to run the dev doctor.'
    Assert-Contains -Text $content -Expected '-UseRepoVenv' -Message 'AGENT_SETUP must document the repo-venv dev deploy command.'
    Assert-Contains -Text $content -Expected 'OCCT_ROOT' -Message 'AGENT_SETUP must document the OCCT_ROOT expectation.'
    Assert-Contains -Text $content -Expected 'python -m rook' -Message 'AGENT_SETUP must tell developers to close stale rook MCP processes before deploy.'
}

Test-DevDoctorScriptContract
Test-DeployScriptSelectsExplicitMsvcToolset
Test-DeployScriptSyncsChirpFromSiblingRepo
Test-DeployScriptInstallsChirpByDefault
Test-DeployScriptVerifiesChirpRuntimeAndConfig
Test-DeployScriptVerifiesRookImportOrigin
Test-DeployScriptParsesMcpConfigs
Test-DeployScriptVerifiesChatManifest
Test-DeployScriptSeedsChatEnvWithoutOverwriting
Test-DeployScriptCopiesAllInstallerPythonModules
Test-DeployScriptHasExplicitDevRuntimeContract
Test-DeployScriptCopiesOcctRuntimeClosure
Test-DeployScriptWritesChatManifestToRuntimeChildren
Test-DeployScriptLiveSmokeIsExplicit
Test-DeployScriptNativeOnlyIsNarrow
Test-DeployScriptUsesMultiRuntimeCompanionLayout
Test-RegisterSuiteSupportsNativeOnlyPreserveCompanion
Test-RegisterSuitePrefersNet8CompanionFallback
Test-RegisterCompanionAcceptsNet8Runtime
Test-DeployScriptNativeOnlySkipBuildFastPath
Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks
Test-AgentSetupDocumentsDevDeployConvention

Write-Host 'Local testing deploy guard tests passed.'
