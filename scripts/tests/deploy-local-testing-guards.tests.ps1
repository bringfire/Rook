$ErrorActionPreference = 'Stop'

$TestRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent (Split-Path -Parent $TestRoot)
$DeployScript = Join-Path $RepoRoot 'scripts\deploy-local-testing.ps1'
$RegisterSuiteScript = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
$RegisterCompanionScript = Join-Path $RepoRoot 'scripts\register-companion.ps1'
$RookProject = Join-Path $RepoRoot 'src\Rook\Rook.csproj'
$SourceInstall = Join-Path $RepoRoot 'install.ps1'
$DeploySkill = Join-Path $RepoRoot '.agents\skills\deploy-local-testing\SKILL.md'
$DoctorScript = Join-Path $RepoRoot 'scripts\rook-dev-doctor.ps1'
$McpProcessScript = Join-Path $RepoRoot 'scripts\rook-mcp-processes.ps1'
$AgentSetup = Join-Path $RepoRoot 'AGENT_SETUP.md'
$RookNativeProject = Join-Path $RepoRoot 'src\RookNative\RookNative.vcxproj'
$OcctPrimitiveTestsProject = Join-Path $RepoRoot 'src\RookNative\OcctPrimitiveTests.vcxproj'
$OcctOfflineReproProject = Join-Path $RepoRoot 'src\RookNative\OcctOfflineRepro.vcxproj'

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
    Assert-Contains -Text $content -Expected 'OCCT_ROOT is not set' -Message 'Dev doctor must fail clearly when OCCT_ROOT is missing.'
    Assert-Contains -Text $content -Expected '$OcctRequiredHeaders = @(' -Message 'Dev doctor must validate actual OCCT headers used by Rook.'
    Assert-Contains -Text $content -Expected "'Standard.hxx'" -Message 'Dev doctor must validate a real OCCT core header, not a toolkit/library name.'
    Assert-Contains -Text $content -Expected "'TopoDS_Shape.hxx'" -Message 'Dev doctor must validate a real OCCT shape header used by Rook.'
    Assert-NotContains -Text $content -Unexpected 'inc\TKernel.hxx' -Message 'Dev doctor must not check TKernel.hxx; TKernel is a toolkit/library, not the install header sentinel.'
    Assert-Contains -Text $content -Expected 'mcp_server\.venv\Scripts\python.exe' -Message 'Dev doctor must check the repo MCP venv path.'
    Assert-Contains -Text $content -Expected 'python -m rook' -Message 'Dev doctor must check stale rook MCP processes.'
    Assert-Contains -Text $content -Expected 'scripts\rook-mcp-processes.ps1' -Message 'Dev doctor must point developers at the safe Rook MCP process helper.'
    Assert-Contains -Text $content -Expected "^pythonw?\.exe$" -Message 'Dev doctor must inspect python.exe and pythonw.exe Rook MCP processes.'
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

function Test-RookMcpProcessHelperContract {
    Assert-True -Condition (Test-Path $McpProcessScript) -Message 'Rook MCP process helper must exist at scripts\rook-mcp-processes.ps1.'

    $content = Get-Content -Path $McpProcessScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$Stop' -Message 'Rook MCP process helper must be read-only by default and require -Stop to stop processes.'
    Assert-Contains -Text $content -Expected 'SupportsShouldProcess = $true' -Message 'Rook MCP process helper must support -WhatIf/-Confirm safety.'
    Assert-Contains -Text $content -Expected 'function Get-RookMcpProcess' -Message 'Rook MCP process helper must centralize process matching.'
    Assert-Contains -Text $content -Expected "^pythonw?\.exe$" -Message 'Rook MCP process helper must only target python.exe/pythonw.exe processes.'
    Assert-Contains -Text $content -Expected '(^|\s)-m\s+rook(\s|$)' -Message 'Rook MCP process helper must match only exact python -m rook command lines.'
    Assert-Contains -Text $content -Expected 'if (-not $Stop)' -Message 'Rook MCP process helper must list only unless -Stop is supplied.'
    Assert-Contains -Text $content -Expected '$PSCmdlet.ShouldProcess' -Message 'Rook MCP process helper must use ShouldProcess before stopping.'
    Assert-Contains -Text $content -Expected 'Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop' -Message 'Rook MCP process helper must stop only the explicitly matched process IDs.'
    Assert-Contains -Text $content -Expected '$WhatIfPreference' -Message 'Rook MCP process helper must let -Stop -WhatIf preview without failing verification.'
    Assert-Contains -Text $content -Expected 'Some python -m rook processes are still running' -Message 'Rook MCP process helper must verify stop results.'
    Assert-NotContains -Text $content -Unexpected 'Stop-Process -Name python' -Message 'Rook MCP process helper must never stop all python processes by name.'
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

function Test-DeployScriptPreservesInstalledChirpEnvironment {
    $content = Get-Content -Path $DeployScript -Raw
    $syncMatch = [regex]::Match(
        $content,
        '(?ms)^function Sync-ChirpPayload \{(?<body>.*?)(?=^function Invoke-PostInstallConfig)'
    )
    Assert-True -Condition $syncMatch.Success -Message 'Local deploy must expose the bounded Sync-ChirpPayload function.'
    $syncBody = $syncMatch.Groups['body'].Value

    Assert-Contains -Text $content -Expected "`$excludeFiles = @('.env', '*.pyc', '*.pyo') + `$ExtraExcludeFiles" -Message 'Shared exact directory sync must exclude .env files.'
    Assert-Contains -Text $syncBody -Expected 'Sync-Directory $ChirpSourceRoot $ChirpInstallRoot' -Message 'Chirp payload must continue through the shared exact mirror.'
    Assert-NotContains -Text $syncBody -Unexpected 'Copy-EnvFileIfMissing' -Message 'Chirp sync must not seed or overwrite the installed .env.'
    Assert-NotContains -Text $syncBody -Unexpected 'Remove-Item' -Message 'Chirp sync must not delete the installed .env.'
    Assert-NotContains -Text $syncBody -Unexpected '.env' -Message 'Chirp-specific sync must not inspect, copy, delete, or validate .env.'
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

function Test-DeployScriptSyncsSealedReleasePythonPayload {
    $content = Get-Content -Path $DeployScript -Raw
    $syncBody = Get-FunctionBodyText -Text $content -FunctionName 'Sync-ReleasePythonPayload'

    Assert-Contains -Text $syncBody -Expected "Join-Path `$RepoRoot 'installer\runtime'" -Message 'Release payload sync must source the staged installer runtime.'
    Assert-Contains -Text $syncBody -Expected "Join-Path `$sourceRuntime 'python-wheelhouse'" -Message 'Release payload sync must use the staged wheelhouse directory.'
    Assert-Contains -Text $syncBody -Expected 'Test-Path -LiteralPath $sourceWheelhouse -PathType Container' -Message 'Release payload sync must require the staged wheelhouse directory.'
    Assert-Contains -Text $syncBody -Expected "Get-ChildItem -LiteralPath `$sourceWheelhouse -Filter '*.whl' -File" -Message 'Release payload sync must inspect staged wheel files.'
    Assert-Contains -Text $syncBody -Expected 'if ($wheelFiles.Count -eq 0)' -Message 'Release payload sync must reject an empty staged wheelhouse before mirroring.'

    foreach ($file in @(
        'requirements-bootstrap-lock.txt',
        'requirements-rook-lock.txt',
        'requirements-chirp-lock.txt',
        'python-runtime-manifest.json'
    )) {
        Assert-Contains -Text $syncBody -Expected "'$file'" -Message "Release payload sync must require $file."
    }

    Assert-Contains -Text $syncBody -Expected 'Test-Path -LiteralPath $source -PathType Leaf' -Message 'Release payload sync must preflight every control file.'
    Assert-Before -Text $syncBody -First 'Test-Path -LiteralPath $source -PathType Leaf' -Second 'Sync-Directory $sourceWheelhouse' -Message 'All control files must be validated before the installed wheelhouse is mirrored.'
    Assert-Contains -Text $syncBody -Expected "Sync-Directory `$sourceWheelhouse (Join-Path `$InstallRoot 'python-wheelhouse')" -Message 'Release payload sync must exactly mirror the wheelhouse so stale wheels are removed.'
    Assert-Contains -Text $syncBody -Expected 'Copy-RequiredFile $source (Join-Path $InstallRoot $file)' -Message 'Release payload sync must copy each control file as required.'
    Assert-NotContains -Text $syncBody -Unexpected 'Copy-OptionalFile' -Message 'Sealed release control files must never be optional.'

    $modeFlow = Get-TextBeforeNextMarker `
        -Text $content `
        -StartMarker 'if ($RuntimeContract.IsDev) {' `
        -EndMarker 'Write-Step "Verify effective runtime"'
    $elseIndex = $modeFlow.IndexOf('} else {', [System.StringComparison]::Ordinal)
    Assert-True -Condition ($elseIndex -ge 0) -Message 'Runtime mode flow must contain an explicit release branch.'
    $devBranch = $modeFlow.Substring(0, $elseIndex)
    $releaseBranch = $modeFlow.Substring($elseIndex)

    Assert-NotContains -Text $devBranch -Unexpected 'Sync-ReleasePythonPayload' -Message 'Explicit dev runtime mode must not reach or inspect the sealed release payload.'
    Assert-Contains -Text $releaseBranch -Expected 'Sync-ReleasePythonPayload' -Message 'Release runtime mode must synchronize the sealed Python payload.'
    Assert-Before -Text $releaseBranch -First 'Sync-ReleasePythonPayload' -Second 'Invoke-PostInstallConfig' -Message 'Release payload synchronization must complete before post_install.py runs.'
}

function Test-DeployScriptHasExplicitDevRuntimeContract {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected '[switch]$UseRepoVenv' -Message 'Local deploy must expose an explicit repo venv dev-runtime flag.'
    Assert-Contains -Text $content -Expected "[string]`$DevPythonRuntime = ''" -Message 'Local deploy must expose an explicit dev Python runtime path override.'
    Assert-Contains -Text $content -Expected '[switch]$ManifestSmokeOnly' -Message 'Local deploy must expose a non-mutating manifest smoke mode.'
    Assert-Contains -Text $content -Expected 'function Resolve-DeployRuntimeContract' -Message 'Local deploy must resolve runtime paths through one explicit contract helper.'
    Assert-Contains -Text $content -Expected '-UseRepoVenv cannot be combined with -DevPythonRuntime' -Message 'Dev runtime flags must be mutually exclusive.'
    Assert-Contains -Text $content -Expected '-NativeOnly cannot be combined with -UseRepoVenv or -DevPythonRuntime' -Message 'Native-only mode must reject dev-runtime flags instead of validating unused Python paths.'
    Assert-NotContains -Text $content -Unexpected '-LiveSmoke cannot be combined with -UseRepoVenv or -DevPythonRuntime' -Message 'Dev runtime live smoke must be allowed when -PayloadOnly -AllowRunning are also selected.'
    Assert-Contains -Text $content -Expected '-ManifestSmokeOnly is only useful with -UseRepoVenv or -DevPythonRuntime' -Message 'Manifest smoke must require an explicit dev runtime.'
    Assert-Contains -Text $content -Expected 'Dev Python runtime not found' -Message 'Dev runtime mode must fail loudly when the requested interpreter is missing.'
    Assert-Contains -Text $content -Expected 'mcp_server\.venv\Scripts\python.exe' -Message 'Repo venv mode must resolve the repository MCP venv explicitly.'
    Assert-Contains -Text $content -Expected 'ROOK_PROJECT_ROOT' -Message 'Dev runtime mode must carry ROOK_PROJECT_ROOT into generated manifests/config.'
    Assert-Contains -Text $content -Expected 'Dev manifest smoke' -Message 'Manifest smoke mode must report the resolved contract.'
    Assert-Contains -Text $content -Expected 'exit 0' -Message 'Manifest smoke mode must exit before deploy mutation.'
    Assert-Contains -Text $content -Expected 'Skipping release post_install.py because an explicit dev runtime was selected.' -Message 'Dev runtime mode must be explicit about bypassing release post_install.'
}

function Test-DeployScriptAllowsDevLiveSmoke {
    $content = Get-Content -Path $DeployScript -Raw

    Assert-Contains -Text $content -Expected 'Environment = New-DeployRuntimeEnvironment' -Message 'Runtime contracts must carry the environment used by live smoke subprocesses.'
    Assert-Contains -Text $content -Expected 'function New-DeployRuntimeEnvironment' -Message 'Local deploy must build runtime environment through one explicit helper.'
    Assert-Contains -Text $content -Expected 'PYTHONPATH = ($PythonPathEntries -join [IO.Path]::PathSeparator)' -Message 'Live smoke PYTHONPATH must come from contract PythonPathEntries.'
    Assert-Contains -Text $content -Expected 'if (-not [string]::IsNullOrWhiteSpace($ProjectRoot))' -Message 'ROOK_PROJECT_ROOT must only be set for non-empty project roots.'
    Assert-Contains -Text $content -Expected '$environment.ROOK_PROJECT_ROOT = $ProjectRoot.Replace(''\'', ''/'')' -Message 'Dev live smoke must pass ROOK_PROJECT_ROOT from the contract.'
    Assert-Contains -Text $content -Expected 'Test-LiveSmoke -Contract $RuntimeContract' -Message 'Live smoke must consume the resolved runtime contract.'
    Assert-Contains -Text $content -Expected 'param([Parameter(Mandatory = $true)][pscustomobject]$Contract)' -Message 'Test-LiveSmoke must require an explicit runtime contract.'
    Assert-Contains -Text $content -Expected '$environmentPropertyNames = @($Contract.Environment.PSObject.Properties.Name)' -Message 'Test-LiveSmoke must read environment values from the contract.'
    Assert-Contains -Text $content -Expected '& $Contract.PythonPath $smokePath' -Message 'Live smoke must run with the selected runtime Python.'
    Assert-NotContains -Text $content -Unexpected '& $VenvPython $smokePath' -Message 'Live smoke must not hardcode the release venv Python.'
    Assert-Contains -Text $content -Expected 'Push-Location $Contract.WorkingDirectory' -Message 'Live smoke must run from the selected runtime working directory.'
    Assert-Contains -Text $content -Expected 'Pop-Location' -Message 'Live smoke must restore the prior working directory.'
    Assert-Contains -Text $content -Expected '[Environment]::SetEnvironmentVariable($name, $null, ''Process'')' -Message 'Live smoke must remove variables that were originally absent.'
    Assert-Contains -Text $content -Expected 'Remove-Item -LiteralPath $smokePath -ErrorAction SilentlyContinue' -Message 'Live smoke must remove its temporary smoke script.'
    Assert-Contains -Text $content -Expected '-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke' -Message 'Deploy script guidance must document the dev repo-venv live smoke command.'
    Assert-Contains -Text $content -Expected 'pass -DevPythonRuntime with a Python executable path' -Message 'Deploy script guidance must document the explicit dev Python live smoke command.'
}

function Test-DeployScriptCopiesOcctRuntimeClosure {
    $content = Get-Content -Path $DeployScript -Raw

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
    Assert-Contains -Text $content -Expected '$env:OCCT_ROOT' -Message 'Local deploy must read OCCT_ROOT.'
    Assert-Contains -Text $content -Expected 'OCCT_ROOT is not set' -Message 'Local deploy must fail clearly when OCCT_ROOT is missing.'
    Assert-NotContains -Text $content -Unexpected '$OcctFallbackRoot' -Message 'Local deploy must not retain the hardcoded OCCT fallback root.'
    Assert-Contains -Text $content -Expected 'OCCT root source:' -Message 'Local deploy must report OCCT_ROOT as the runtime source.'
    Assert-Contains -Text $content -Expected 'function Copy-OcctRuntimeDlls' -Message 'Local deploy must copy OCCT runtime DLLs through an explicit helper.'
    Assert-Contains -Text $content -Expected 'Join-Path $resolved.Root ''win64\vc14\bin''' -Message 'Local deploy must copy OCCT DLLs from the resolved runtime bin folder.'
    Assert-Contains -Text $content -Expected 'Copy-RequiredFile $source (Join-Path $PluginDir $dll)' -Message 'Local deploy must copy OCCT DLLs next to RookNative.rhp.'

    $deployNativePayloadBody = Get-FunctionBodyText -Text $content -FunctionName 'Deploy-NativePayload'
    Assert-Before -Text $deployNativePayloadBody -First 'Copy-RequiredFile (Join-Path $nativeDir ''RookNative.rhp'')' -Second 'Copy-OcctRuntimeDlls' -Message 'Local deploy must copy RookNative.rhp before copying the OCCT runtime closure inside Deploy-NativePayload.'
}

function Test-OcctRootRequiresExplicitConfiguration {
    $activeFiles = @(
        $DeployScript,
        $DoctorScript,
        $RookNativeProject,
        $OcctPrimitiveTestsProject,
        $OcctOfflineReproProject
    )

    foreach ($path in $activeFiles) {
        $content = Get-Content -Path $path -Raw
        Assert-NotContains -Text $content -Unexpected 'C:\Users\aryan\source\repos\OCCT\build-rook' -Message "Active OCCT config must not contain hardcoded fallback path: $path"
    }

    foreach ($path in @($RookNativeProject, $OcctPrimitiveTestsProject, $OcctOfflineReproProject)) {
        $content = Get-Content -Path $path -Raw
        Assert-Contains -Text $content -Expected '<OcctRoot Condition="''$(OcctRoot)''==''''">$(OCCT_ROOT)</OcctRoot>' -Message "Project must resolve OcctRoot from OCCT_ROOT: $path"
        Assert-Contains -Text $content -Expected '<Target Name="ValidateOcctRoot" BeforeTargets="PrepareForBuild" Condition="''$(OcctRoot)''==''''">' -Message "Project must fail clearly when OcctRoot is missing: $path"
        Assert-Contains -Text $content -Expected 'Set OCCT_ROOT or pass /p:OcctRoot=' -Message "Project missing-OCCT message must document both supported configuration paths: $path"
    }

    $offline = Get-Content -Path $OcctOfflineReproProject -Raw
    Assert-Contains -Text $offline -Expected '$(OcctRoot)\inc;$(RhinoSdkDir)openNURBS' -Message 'Offline repro must use $(OcctRoot) for OCCT includes.'
    Assert-Contains -Text $offline -Expected '$(OcctRoot)\win64\vc14\lib;$(RhinoSdkDir)lib\Release' -Message 'Offline repro must use $(OcctRoot) for OCCT libraries.'
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
    Assert-Contains -Text $content -Expected 'from rook.bridge import call_rhino' -Message 'Embedded live smoke must use the internal bridge for debug inventory probes.'
    Assert-Contains -Text $content -Expected 'from rook.local_testing_proof import ProofFailure, _run_chirp_smoke_mutation' -Message 'Embedded live smoke must execute the same mutation and cleanup helper as owned release readiness.'
    Assert-Contains -Text $content -Expected 'mutation = await _run_chirp_smoke_mutation(' -Message 'Embedded live smoke must delegate the entire post-attempt validation and cleanup flow.'
    Assert-Contains -Text $content -Expected 'call_rhino_fn=call_rhino' -Message 'Embedded live smoke must provide the real internal inventory probe.'
    Assert-Contains -Text $content -Expected '"failure_label": exc.failure_label' -Message 'Embedded cleanup failures must serialize a stable structured failure label.'
    Assert-Contains -Text $content -Expected 'raise SystemExit(json.dumps(failure_payload, default=str, sort_keys=True))' -Message 'Embedded cleanup failures must serialize deterministic structured evidence.'
    Assert-NotContains -Text $content -Unexpected 'item.get("componentGuid")' -Message 'Cleanup must never compare a Chirp instance GUID with snapshot component type GUIDs.'
    Assert-NotContains -Text $content -Unexpected 'snapshot.get("diagnostics")' -Message 'Cleanup must never use snapshot diagnostics as the GH document object count.'
    Assert-Contains -Text $content -Expected "'ROOK_MCP_TOOL_PROFILE'" -Message 'Live smoke must save and restore the MCP profile.'
    Assert-Contains -Text $content -Expected "[Environment]::SetEnvironmentVariable('ROOK_MCP_TOOL_PROFILE', 'lean', 'Process')" -Message 'Live smoke must force lean.'
    foreach ($gateway in @('rook_tools_ls', 'rook_tools_search', 'rook_tools_read', 'rook_tools_call')) {
        Assert-Contains -Text $content -Expected $gateway -Message "Live smoke must require gateway $gateway."
    }
    $directStatus = $content.IndexOf('status = await _call_tool_dispatch("gh_status", {})')
    $progressiveSearch = $content.IndexOf('await public_call("rook_tools_search"')
    $mutationCall = $content.IndexOf('mutation = await _run_chirp_smoke_mutation(')
    Assert-True -Condition ($directStatus -ge 0 -and $directStatus -lt $progressiveSearch -and $progressiveSearch -lt $mutationCall) -Message 'Direct controls must precede the progressive chain, which must precede Chirp mutation.'
    $cleanupCall = $content.IndexOf('mutation = await _run_chirp_smoke_mutation(')
    $evidenceStart = $content.IndexOf('live_evidence = {')
    $finalPrint = $content.IndexOf('print(json.dumps(live_evidence, default=str, sort_keys=True))')
    Assert-True -Condition ($cleanupCall -ge 0 -and $cleanupCall -lt $evidenceStart -and $evidenceStart -lt $finalPrint) -Message 'Final evidence must be built and printed only after the shared cleanup helper succeeds.'
    $evidenceBlock = $content.Substring($evidenceStart, $finalPrint - $evidenceStart)
    foreach ($field in @('"rhino_ping"', '"gh_status"', '"progressive_discovery"', '"chirp_create"', '"gh_errors"', '"gh_undo"')) {
        Assert-Contains -Text $evidenceBlock -Expected $field -Message "Final live evidence must include $field."
    }
    Assert-NotContains -Text $content -Unexpected 'print(json.dumps({"rhino_ping": ping, "gh_status": status, "chirp_create": chirp}, default=str))' -Message 'The pre-validation partial evidence print must be removed.'
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

function Test-LegacyRuiIsSuppressedFromSourceDeployments {
    $project = Get-Content -Path $RookProject -Raw
    $deploy = Get-Content -Path $DeployScript -Raw
    $sourceInstall = Get-Content -Path $SourceInstall -Raw
    $registration = Get-Content -Path $RegisterCompanionScript -Raw

    Assert-NotContains -Text $project -Unexpected '<None Include="UI\Rook.rui"' -Message 'Build must not emit RUI.'
    Assert-NotContains -Text $project -Unexpected '<Copy SourceFiles="$(TargetDir)$(TargetName).rui"' -Message 'MSBuild must not copy RUI.'
    Assert-Contains -Text $project -Expected '<Delete Files="$(RhinoManagedRuntimeDir)\$(TargetName).rui" />' -Message 'MSBuild must exact-delete RUI.'

    Assert-NotContains -Text $deploy -Unexpected "Copy-OptionalFile (Join-Path `$sourceDir 'Rook.rui')" -Message 'Local deploy must not copy RUI.'
    Assert-Contains -Text $deploy -Expected "Remove-Item -LiteralPath (Join-Path `$targetDir 'Rook.rui') -Force -ErrorAction SilentlyContinue" -Message 'Local deploy must exact-delete RUI.'

    Assert-NotContains -Text $sourceInstall -Unexpected 'Copy-Item (Join-Path $sourceDir "Rook.rui")' -Message 'Source installer must not copy RUI.'
    Assert-Contains -Text $sourceInstall -Expected 'Remove-Item -LiteralPath (Join-Path $targetDir "Rook.rui") -Force -ErrorAction SilentlyContinue' -Message 'Source installer must exact-delete RUI.'

    Assert-Contains -Text $registration -Expected "Remove-ItemProperty -LiteralPath `$RegBase -Name 'RuiFile' -ErrorAction SilentlyContinue" -Message 'Registration must remove RuiFile.'
    Assert-Contains -Text $registration -Expected "Get-ItemProperty -LiteralPath `$RegBase -Name 'RuiFile' -ErrorAction SilentlyContinue" -Message 'Registration must verify RuiFile absence.'
    Assert-Contains -Text $registration -Expected "`$Errors += 'RuiFile: expected absent'" -Message 'Retained RuiFile must fail verification.'
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
    Assert-Contains -Text $content -Expected '$UnsupportedNet48CompanionMessage = ''net48 Rook companion builds are not supported; use net8.0 Rook.rhp. net7.0 is accepted as fallback.''' -Message 'Companion registration net48 guidance must prefer net8.0 and describe net7.0 as fallback only.'
    Assert-Contains -Text $content -Expected '$UnsupportedNet48CompanionMessage' -Message 'Companion registration must keep the net48-specific rejection path.'
    Assert-Contains -Text $content -Expected 'Join-Path $NativeDir ''net8.0\Rook.rhp''' -Message 'Companion registration must discover installed net8.0 payloads beside RookNative.'
    Assert-Contains -Text $content -Expected 'Join-Path $NativeDir ''net7.0\Rook.rhp''' -Message 'Companion registration must preserve installed net7.0 fallback discovery beside RookNative.'
    Assert-Contains -Text $content -Expected 'src\Rook\bin\Debug\net8.0\Rook.rhp' -Message 'Companion registration must discover repo Debug net8.0 build output.'
    Assert-Contains -Text $content -Expected 'src\Rook\bin\Release\net8.0\Rook.rhp' -Message 'Companion registration must discover repo Release net8.0 build output.'

    $colocatedCandidatesBlock = Get-TextBeforeNextMarker -Text $content -StartMarker '$ColocatedCandidates = @(' -EndMarker "`n        foreach "
    Assert-Before -Text $colocatedCandidatesBlock -First 'Join-Path $NativeDir ''net8.0\Rook.rhp''' -Second 'Join-Path $NativeDir ''net7.0\Rook.rhp''' -Message 'Companion registration must prefer installed net8.0 before net7.0 beside RookNative.'

    $repoCandidatesBlock = Get-TextBeforeNextMarker -Text $content -StartMarker '$Candidates = @(' -EndMarker "`n        foreach "
    Assert-Before -Text $repoCandidatesBlock -First 'src\Rook\bin\Debug\net8.0\Rook.rhp' -Second 'src\Rook\bin\Debug\net7.0\Rook.rhp' -Message 'Companion registration must prefer repo Debug net8.0 before Debug net7.0.'
    Assert-Before -Text $repoCandidatesBlock -First 'src\Rook\bin\Release\net8.0\Rook.rhp' -Second 'src\Rook\bin\Release\net7.0\Rook.rhp' -Message 'Companion registration must prefer repo Release net8.0 before Release net7.0.'
    Assert-Before -Text $repoCandidatesBlock -First 'src\Rook\bin\Release\net8.0\Rook.rhp' -Second 'src\Rook\bin\Debug\net7.0\Rook.rhp' -Message 'Companion registration must check all repo net8.0 candidates before net7.0 fallbacks.'
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
    Assert-Contains -Text $content -Expected '-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke' -Message 'Skill must document the dev-runtime live smoke command.'
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
    Assert-Contains -Text $content -Expected 'scripts\rook-mcp-processes.ps1' -Message 'AGENT_SETUP must document the safe Rook MCP process helper.'
    Assert-Contains -Text $content -Expected '-UseRepoVenv' -Message 'AGENT_SETUP must document the repo-venv dev deploy command.'
    Assert-Contains -Text $content -Expected '-PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke' -Message 'AGENT_SETUP must document the dev-runtime live smoke proof command.'
    Assert-Contains -Text $content -Expected 'OCCT_ROOT' -Message 'AGENT_SETUP must document the OCCT_ROOT expectation.'
    Assert-Contains -Text $content -Expected 'To prove a second dev machine is ready' -Message 'AGENT_SETUP must document the two-machine proof checklist.'
    Assert-Contains -Text $content -Expected 'OCCT root source' -Message 'AGENT_SETUP two-machine proof must capture the OCCT source line.'
    Assert-Contains -Text $content -Expected 'python -m rook' -Message 'AGENT_SETUP must tell developers to close stale rook MCP processes before deploy.'
}

function Test-DeployScriptReleaseSitePackagesCoherence {
    $content = Get-Content -Path $DeployScript -Raw

    # Bootstrap must offer the bundled Rook runtime Python (portable to a machine
    # without a system Python) and must NOT seed the release venv it recreates.
    Assert-Contains -Text $content -Expected "Join-Path `$RuntimeRoot 'python'" -Message 'Bootstrap must consider the bundled Rook runtime Python directory.'
    Assert-Contains -Text $content -Expected "-Filter 'cpython-*'" -Message 'Bootstrap must glob bundled cpython runtimes (version-resilient).'
    Assert-Contains -Text $content -Expected 'never bootstrap with the venv post_install recreates' -Message 'Bootstrap must skip the release venv that post_install recreates.'
    Assert-NotContains -Text $content -Unexpected '$candidates += $VenvPython' -Message 'Bootstrap must not seed the release venv as a candidate.'

    # New-DeployRuntimeEnvironment must accept the empty release PythonPathEntries.
    Assert-Contains -Text $content -Expected '[AllowEmptyCollection()][string[]]$PythonPathEntries' -Message 'Runtime environment must allow empty PythonPathEntries (release uses @()).'
    Assert-Contains -Text $content -Expected '$releasePythonPathEntries = @()' -Message 'Release must use an empty PythonPathEntries (empty PYTHONPATH).'

    # Release source coherence: mirror rook into the release venv site-packages.
    Assert-Contains -Text $content -Expected 'function Install-ReleaseSourceIntoVenv' -Message 'Local deploy must mirror current source into the release venv.'
    Assert-Contains -Text $content -Expected 'Sync-Directory $sourceRook $destRook' -Message 'Release source mirror must use the robocopy /MIR directory sync.'
    Assert-Contains -Text $content -Expected 'Lib\site-packages\rook' -Message 'Release source mirror/verify must target the release venv site-packages rook package.'
    Assert-Contains -Text $content -Expected 'Mirror current source into release venv site-packages' -Message 'Main flow must run the release source mirror step.'

    # Verification must prove the release runtime imports rook.server from
    # site-packages and advertises all seven reconstruction tools.
    Assert-Contains -Text $content -Expected 'rook.server.__file__' -Message 'Verification must assert rook.server import origin (the decisive stale-wheel proof).'
    Assert-Contains -Text $content -Expected 'rook.server imported from stale location' -Message 'Verification must reject a stale rook.server import.'
    foreach ($tool in @(
        'rhino_2d_to_3d_models',
        'rhino_2d_to_3d_submit',
        'rhino_2d_to_3d_jobs',
        'rhino_2d_to_3d_status',
        'rhino_2d_to_3d_cancel',
        'rhino_2d_to_3d_result',
        'rhino_2d_to_3d_import'
    )) {
        Assert-Contains -Text $content -Expected "`"$tool`"" -Message "Release verification must assert the $tool reconstruction tool."
    }

    # Chat-manifest validation must branch by mode for the empty release PYTHONPATH.
    Assert-Contains -Text $content -Expected 'Chat service pythonPathEntries must be empty in release' -Message 'Chat manifest verify must require empty release pythonPathEntries.'
    Assert-Contains -Text $content -Expected 'Chat service PYTHONPATH must be empty in release' -Message 'Chat manifest verify must require empty release PYTHONPATH.'
}

function Test-PrimePayloadConsumerHandoff {
    $tokens = $null
    $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile($DeployScript, [ref]$tokens, [ref]$errors)
    Assert-True ($errors.Count -eq 0) 'Deployment script must parse.'
    Assert-True ($ast.ParamBlock.Parameters.Name.VariablePath.UserPath -contains 'PrimeRuntimePayload') 'Explicit Prime payload is required.'
    $calls = @($ast.EndBlock.Statements | Where-Object { $_ -isnot [System.Management.Automation.Language.FunctionDefinitionAst] } | ForEach-Object { $_.Extent.Text }) -join "`n"
    Assert-Before $calls 'Assert-PrimeRuntimePayload' 'Assert-NoRunningFullDeployBlockers' 'Prime admission must precede deployment side effects.'
    Assert-Before $calls 'Stage-PrimeRuntimePayload' 'Invoke-PostInstallConfig' 'Staging must feed post-install.'
    $post = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Invoke-PostInstallConfig' }, $true)
    $literals = @($post.FindAll({ param($node) $node -is [System.Management.Automation.Language.StringConstantExpressionAst] }, $true).Value)
    Assert-True ($literals -contains '--prime-incoming-dir') 'Post-install must consume the exact incoming root.'
    Assert-Contains $post.Extent.Text '$PrimeIncomingDir' 'The staged generation must reach the post-install argv.'
    $commands = $ast.FindAll({ param($node) $node -is [System.Management.Automation.Language.CommandAst] }, $true)
    foreach ($command in $commands) {
        if ($command.GetCommandName() -in @('Copy-Item', 'Move-Item', 'Remove-Item', 'Set-Content', 'Out-File')) {
            Assert-True (-not ($command.Extent.Text -match '(?i)prime[\\/]runtimes|prime[\\/]current\.json')) 'Deployment cannot publish Prime authority independently.'
        }
    }
}

Test-PrimePayloadConsumerHandoff
Test-DevDoctorScriptContract
Test-RookMcpProcessHelperContract
Test-DeployScriptSelectsExplicitMsvcToolset
Test-DeployScriptSyncsChirpFromSiblingRepo
Test-DeployScriptPreservesInstalledChirpEnvironment
Test-DeployScriptInstallsChirpByDefault
Test-DeployScriptVerifiesChirpRuntimeAndConfig
Test-DeployScriptVerifiesRookImportOrigin
Test-DeployScriptParsesMcpConfigs
Test-DeployScriptVerifiesChatManifest
Test-DeployScriptSeedsChatEnvWithoutOverwriting
Test-DeployScriptCopiesAllInstallerPythonModules
Test-DeployScriptSyncsSealedReleasePythonPayload
Test-DeployScriptHasExplicitDevRuntimeContract
Test-DeployScriptAllowsDevLiveSmoke
Test-DeployScriptCopiesOcctRuntimeClosure
Test-OcctRootRequiresExplicitConfiguration
Test-DeployScriptWritesChatManifestToRuntimeChildren
Test-DeployScriptLiveSmokeIsExplicit
Test-DeployScriptNativeOnlyIsNarrow
Test-DeployScriptUsesMultiRuntimeCompanionLayout
Test-LegacyRuiIsSuppressedFromSourceDeployments
Test-RegisterSuiteSupportsNativeOnlyPreserveCompanion
Test-RegisterSuitePrefersNet8CompanionFallback
Test-RegisterCompanionAcceptsNet8Runtime
Test-DeployScriptNativeOnlySkipBuildFastPath
Test-DeploySkillPointsToAuthoritativeScriptAndChirpChecks
Test-AgentSetupDocumentsDevDeployConvention
Test-DeployScriptReleaseSitePackagesCoherence

Write-Host 'Local testing deploy guard tests passed.'
