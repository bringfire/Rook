# deploy-local-testing.ps1
#
# Fast local deploy for testing the installed Rook runtime without compiling a
# full installer. This updates the per-user Rhino plugin folder and the bundled
# AppData Rook runtime, while preserving mutable runtime data and local secrets.

[CmdletBinding()]
param(
    [ValidateSet('Debug', 'Release')]
    [string]$Configuration = 'Release',

    [string]$VCToolsVersion = '14.44.35207',

    [string]$RevitInstallDir = '',

    [switch]$NativeOnly,
    [switch]$ManagedOnly,
    [switch]$PayloadOnly,
    [switch]$AllowRunning,
    [switch]$SkipBuild,
    [switch]$SkipChirpInstall,
    [switch]$UseRepoVenv,
    [string]$DevPythonRuntime = '',
    [string]$PrimeRuntimePayload = '',
    [string]$PythonBuildRoot = '',
    [switch]$LiveSmoke,
    [switch]$ManifestSmokeOnly
)

$ErrorActionPreference = 'Stop'

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir

function Resolve-ChirpSourceRoot {
    param([Parameter(Mandatory = $true)][string]$RepoRoot)

    $directSibling = Join-Path (Split-Path -Parent $RepoRoot) 'Chirp'
    if (Test-Path (Join-Path $directSibling 'pyproject.toml')) {
        return $directSibling
    }

    try {
        $commonDir = ((& git -C $RepoRoot rev-parse --git-common-dir 2>$null) -join '').Trim()
        if ($LASTEXITCODE -eq 0 -and $commonDir) {
            if (-not [System.IO.Path]::IsPathRooted($commonDir)) {
                $commonDir = Join-Path $RepoRoot $commonDir
            }
            $resolvedCommon = (Resolve-Path $commonDir).Path
            $commonLeaf = Split-Path -Leaf $resolvedCommon
            $canonicalRepoRoot = if ($commonLeaf -eq '.git') {
                Split-Path -Parent $resolvedCommon
            } else {
                Split-Path -Parent $resolvedCommon
            }
            $gitSibling = Join-Path (Split-Path -Parent $canonicalRepoRoot) 'Chirp'
            if (Test-Path (Join-Path $gitSibling 'pyproject.toml')) {
                return $gitSibling
            }
        }
    } catch { }

    return $directSibling
}

$ChirpSourceRoot = Resolve-ChirpSourceRoot -RepoRoot $RepoRoot
$InstallRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Rook\app'
$RuntimeRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Rook'
$DataRoot = Join-Path $RuntimeRoot 'data'
$LogsRoot = Join-Path $RuntimeRoot 'logs'
$VenvPython = Join-Path $RuntimeRoot 'venv\Scripts\python.exe'
$PluginDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative'
$ChirpInstallRoot = Join-Path $InstallRoot 'chirp'
$ManagedCompanionRuntimes = @('net8.0', 'net7.0', 'net48')
$OcctRuntimeDlls = @(
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
)

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Get-RunningRhinoProcesses {
    return Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
}

function Get-RunningRookMcpProcesses {
    return Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match '(^|\s)-m\s+rook(\s|$)' }
}

function Assert-NoRunningRhino {
    $rhino = Get-RunningRhinoProcesses
    if ($rhino) {
        $rhino | Select-Object ProcessName, Id, Path | Format-Table | Out-String | Write-Host
        throw "Refusing plugin deploy while Rhino is running. Close Rhino first."
    }
}

function Assert-DeployMode {
    if ($ManagedOnly -and ($NativeOnly -or $PayloadOnly -or $AllowRunning -or $LiveSmoke -or
        $UseRepoVenv -or $ManifestSmokeOnly -or $SkipChirpInstall -or $DevPythonRuntime -or
        $PrimeRuntimePayload -or $PythonBuildRoot -or $RevitInstallDir)) {
        throw "-ManagedOnly accepts only -Configuration and -SkipBuild; it does not deploy other payloads or run live checks."
    }

    if ($NativeOnly -and $PayloadOnly) {
        throw "-NativeOnly cannot be combined with -PayloadOnly."
    }

    if ($NativeOnly -and $LiveSmoke) {
        throw "-LiveSmoke cannot be combined with -NativeOnly. Run live smoke after restarting Rhino with the deployed native plugin."
    }

    if ($AllowRunning -and -not $PayloadOnly) {
        throw "-AllowRunning is only permitted with -PayloadOnly. Full plugin deploy requires Rhino and rook MCP processes to be stopped."
    }

    if ($LiveSmoke -and -not ($PayloadOnly -and $AllowRunning)) {
        throw "-LiveSmoke requires -PayloadOnly -AllowRunning. Run the full deploy first, restart Rhino/Grasshopper, then run payload-only live smoke."
    }

    if ($UseRepoVenv -and -not [string]::IsNullOrWhiteSpace($DevPythonRuntime)) {
        throw "-UseRepoVenv cannot be combined with -DevPythonRuntime. Pick one explicit dev runtime source."
    }

    $hasDevRuntime = $UseRepoVenv -or -not [string]::IsNullOrWhiteSpace($DevPythonRuntime)
    if ($NativeOnly -and $hasDevRuntime) {
        throw "-NativeOnly cannot be combined with -UseRepoVenv or -DevPythonRuntime. Native-only deploy does not use Python, MCP, or chat manifests."
    }

    if ($ManifestSmokeOnly -and -not $hasDevRuntime) {
        throw "-ManifestSmokeOnly is only useful with -UseRepoVenv or -DevPythonRuntime."
    }
}

function Assert-NoRunningFullDeployBlockers {
    $rhino = Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
    $rookPython = Get-RunningRookMcpProcesses

    if (($rhino -or $rookPython) -and -not $AllowRunning) {
        if ($rhino) {
            $rhino | Select-Object ProcessName, Id, Path | Format-Table | Out-String | Write-Host
        }
        if ($rookPython) {
            $rookPython | Select-Object ProcessId, CommandLine | Format-Table -Wrap | Out-String | Write-Host
        }
        throw "Refusing deploy while Rhino or python -m rook is running. Close them first, or use -PayloadOnly -AllowRunning for payload-only sync."
    }
}

function Resolve-RookBimRevitInstallDir {
    if (-not [string]::IsNullOrWhiteSpace($RevitInstallDir)) {
        return $RevitInstallDir
    }

    if (-not [string]::IsNullOrWhiteSpace($env:RevitInstallDir)) {
        return $env:RevitInstallDir
    }

    return (Join-Path $env:ProgramFiles 'Autodesk\Revit 2024')
}

function Assert-RookBimBuildPrerequisites {
    $resolvedRevitInstallDir = Resolve-RookBimRevitInstallDir
    $requiredFiles = @(
        (Join-Path $resolvedRevitInstallDir 'RevitAPI.dll'),
        (Join-Path $resolvedRevitInstallDir 'RevitAPIUI.dll')
    )
    $missingFiles = @($requiredFiles | Where-Object { -not (Test-Path $_) })

    if ($missingFiles.Count -gt 0) {
        $missingText = $missingFiles -join ', '
        throw "Full local deploy builds RookBIM and requires Revit API assemblies. Missing: $missingText. Install Revit, pass -RevitInstallDir <path>, run -NativeOnly for native-only iteration, run -PayloadOnly -AllowRunning after a successful build, or run -SkipBuild to deploy existing build outputs."
    }

    return (Resolve-Path $resolvedRevitInstallDir).Path
}

function Resolve-BootstrapPython {
    # post_install.py recreates the rook release venv (shutil.rmtree in
    # _create_venv) whenever the runtime payload/lock changes. It must NOT be
    # bootstrapped with that same venv's interpreter, or it deletes the running
    # process mid-run -> silent exit 1, no traceback. Exclude $VenvPython by
    # normalized, resolved, case-insensitive path. Prefer system/bundled Python.
    $venvNormalized = $null
    if (Test-Path $VenvPython) {
        $venvNormalized = (Resolve-Path $VenvPython).Path.Replace('\', '/').ToLowerInvariant()
    }

    $candidates = @()

    # Bundled Rook runtime Python: the base interpreter that created the release
    # venv. It is always present after install, version-matched, and is NOT the
    # venv that post_install recreates, so it is the most portable bootstrap on a
    # machine that lacks a system Python (the other dev box). Discover by glob so
    # a runtime version bump (cpython-3.11.x -> ...) does not break this.
    $bundledPythonRoot = Join-Path $RuntimeRoot 'python'
    if (Test-Path $bundledPythonRoot) {
        Get-ChildItem -Path $bundledPythonRoot -Directory -Filter 'cpython-*' -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending |
            ForEach-Object {
                $bundledPython = Join-Path $_.FullName 'python.exe'
                if (Test-Path $bundledPython) {
                    $candidates += $bundledPython
                }
            }
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
        $candidates += $pythonCommand.Source
    }

    try {
        $pyOutput = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $pyOutput -and (Test-Path $pyOutput.Trim())) {
            $candidates += $pyOutput.Trim()
        }
    } catch { }

    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    foreach ($minor in 14, 13, 12, 11, 10) {
        $candidate = Join-Path $localAppData "Programs\Python\Python3$minor\python.exe"
        if (Test-Path $candidate) {
            $candidates += $candidate
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            $resolved = (Resolve-Path $candidate).Path
            if ($venvNormalized -and ($resolved.Replace('\', '/').ToLowerInvariant() -eq $venvNormalized)) {
                continue  # never bootstrap with the venv post_install recreates
            }
            return $resolved
        }
    }

    throw "Python 3.10+ was not found for the post_install bootstrap (the release venv at $VenvPython is intentionally excluded because post_install recreates it; install a system Python 3.10+ or ensure 'py -3' resolves)."
}

function Resolve-DevPythonRuntime {
    if ($UseRepoVenv) {
        $candidate = Join-Path $RepoRoot 'mcp_server\.venv\Scripts\python.exe'
    } else {
        $candidate = $DevPythonRuntime
    }

    if ([string]::IsNullOrWhiteSpace($candidate)) {
        return $null
    }

    if (-not (Test-Path $candidate)) {
        throw "Dev Python runtime not found: $candidate"
    }

    return (Resolve-Path $candidate).Path
}

function New-DeployRuntimeEnvironment {
    param(
        [Parameter(Mandatory = $true)][string]$Mode,
        [Parameter(Mandatory = $true)][string]$InstallRoot,
        [Parameter(Mandatory = $true)][string]$DataRoot,
        # AllowEmptyCollection: release passes @() (empty PYTHONPATH); a mandatory
        # [string[]] otherwise rejects an empty array at binding time.
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$PythonPathEntries,
        [string]$ProjectRoot = ''
    )

    $environment = [ordered]@{
        ROOK_MODE = $Mode
        ROOK_INSTALL_ROOT = $InstallRoot.Replace('\', '/')
        ROOK_DATA_DIR = $DataRoot.Replace('\', '/')
        CHIRP_HOME = $ChirpInstallRoot.Replace('\', '/')
        PYTHONPATH = ($PythonPathEntries -join [IO.Path]::PathSeparator)
    }

    if (-not [string]::IsNullOrWhiteSpace($ProjectRoot)) {
        $environment.ROOK_PROJECT_ROOT = $ProjectRoot.Replace('\', '/')
    }

    return [pscustomobject]$environment
}

function Resolve-DeployRuntimeContract {
    $devPython = Resolve-DevPythonRuntime
    if ($devPython) {
        $devMcpServerDir = Join-Path $RepoRoot 'mcp_server'
        $devSrcDir = Join-Path $devMcpServerDir 'src'
        if (-not (Test-Path $devMcpServerDir)) {
            throw "Dev MCP server directory not found: $devMcpServerDir"
        }
        if (-not (Test-Path $devSrcDir)) {
            throw "Dev MCP source directory not found: $devSrcDir"
        }

        $devWorkingDirectory = (Resolve-Path $devMcpServerDir).Path
        $devPythonPathEntries = @((Resolve-Path $devSrcDir).Path)
        # Source imports come from the checkout; Prime and bundled resources
        # remain under the existing installed app, not a second repo payload.
        $devInstallRoot = $InstallRoot
        $devProjectRoot = (Resolve-Path $RepoRoot).Path

        return [pscustomobject]@{
            Mode = 'dev'
            IsDev = $true
            PythonPath = $devPython
            WorkingDirectory = $devWorkingDirectory
            PythonPathEntries = $devPythonPathEntries
            InstallRoot = $devInstallRoot
            DataRoot = $DataRoot
            ProjectRoot = $devProjectRoot
            Environment = New-DeployRuntimeEnvironment `
                -Mode 'dev' `
                -InstallRoot $devInstallRoot `
                -DataRoot $DataRoot `
                -PythonPathEntries $devPythonPathEntries `
                -ProjectRoot $devProjectRoot
        }
    }

    $releaseWorkingDirectory = Join-Path $InstallRoot 'mcp_server'
    # Release imports rook from site-packages (Install-ReleaseSourceIntoVenv keeps
    # it current). Empty PYTHONPATH matches the written MCP config
    # (build_release_mcp_env sets PYTHONPATH="") and removes the source-tree
    # shadow that previously masked stale-wheel drift during verification.
    $releasePythonPathEntries = @()

    return [pscustomobject]@{
        Mode = 'release'
        IsDev = $false
        PythonPath = $VenvPython
        WorkingDirectory = $releaseWorkingDirectory
        PythonPathEntries = $releasePythonPathEntries
        InstallRoot = $InstallRoot
        DataRoot = $DataRoot
        ProjectRoot = ''
        Environment = New-DeployRuntimeEnvironment `
            -Mode 'release' `
            -InstallRoot $InstallRoot `
            -DataRoot $DataRoot `
            -PythonPathEntries $releasePythonPathEntries
    }
}

function Invoke-NativeBuild {
    $project = Join-Path $RepoRoot 'src\RookNative\RookNative.vcxproj'
    $buildBat = Join-Path $env:TEMP 'rook_local_testing_native_build.bat'
    $vcvarsVersion = (($VCToolsVersion -split '\.')[0..1] -join '.')
    @"
@echo off
set "VSCMD_START_DIR=%CD%"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x64 -vcvars_ver=$vcvarsVersion
set VCToolsVersion=$VCToolsVersion
msbuild "%~1" /p:Configuration=$Configuration /p:Platform=x64 /p:VCToolsVersion=$VCToolsVersion /m /v:minimal
echo EXIT_CODE=%ERRORLEVEL%
"@ | Set-Content -Path $buildBat -Encoding ASCII

    $output = & $buildBat $project 2>&1
    $output | Select-String -Pattern 'EXIT_CODE|Build succeeded|Build FAILED|error MSB|error C[0-9]|fatal error'
    if ($LASTEXITCODE -ne 0 -or -not ($output -match 'EXIT_CODE=0')) {
        throw "Native build failed."
    }
}

function Invoke-ManagedBuild {
    param([switch]$CompanionOnly)

    # Release's existing MSBuild target must not deploy before our admission checks.
    $buildOptions = if ($CompanionOnly) { @('--no-restore', '-p:RhinoPluginDir=') } else { @() }
    & dotnet build (Join-Path $RepoRoot 'src\Rook\Rook.csproj') -c $Configuration @buildOptions
    if ($LASTEXITCODE -ne 0) {
        throw "Managed build failed."
    }
    if ($CompanionOnly) { return }

    $rookBimRevitInstallDir = Assert-RookBimBuildPrerequisites
    & dotnet build (Join-Path $RepoRoot 'src\RookBim\RookBim.csproj') -c $Configuration "/p:RevitInstallDir=$rookBimRevitInstallDir"
    if ($LASTEXITCODE -ne 0) {
        throw "RookBIM build failed."
    }
}

function Copy-RequiredFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (-not (Test-Path $Source)) {
        throw "Required file not found: $Source"
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

function Copy-OptionalFile {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (Test-Path $Source) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

function Resolve-OcctRuntimeRoot {
    if (-not [string]::IsNullOrWhiteSpace($env:OCCT_ROOT)) {
        return [pscustomobject]@{ Root = $env:OCCT_ROOT; Source = 'OCCT_ROOT' }
    }
    throw "OCCT_ROOT is not set. Set OCCT_ROOT to a valid OCCT build root before native deploy."
}

function Copy-OcctRuntimeDlls {
    $resolved = Resolve-OcctRuntimeRoot
    Write-Host "OCCT root source: $($resolved.Source)"
    Write-Host "OCCT root:        $($resolved.Root)"

    if (-not (Test-Path $resolved.Root)) {
        throw "OCCT root not found: $($resolved.Root). Set OCCT_ROOT to a valid OCCT build root."
    }

    $sourceDir = Join-Path $resolved.Root 'win64\vc14\bin'
    if (-not (Test-Path $sourceDir)) {
        throw "OCCT runtime bin directory not found: $sourceDir"
    }

    foreach ($dll in $OcctRuntimeDlls) {
        $source = Join-Path $sourceDir $dll
        Copy-RequiredFile $source (Join-Path $PluginDir $dll)
    }
}

function Copy-EnvFileIfMissing {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if ((Test-Path $Source) -and -not (Test-Path $Destination)) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination
        Write-Host "Seeded local secret file: $Destination"
    }
}

function Sync-Directory {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination,
        [string[]]$ExtraExcludeDirs = @(),
        [string[]]$ExtraExcludeFiles = @()
    )
    if (-not (Test-Path $Source)) {
        throw "Source directory not found: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null

    $excludeDirs = @('.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'node_modules', 'logs', 'data') + $ExtraExcludeDirs
    $excludeFiles = @('.env', '*.pyc', '*.pyo') + $ExtraExcludeFiles

    $args = @($Source, $Destination, '/MIR', '/NFL', '/NDL', '/NJH', '/NJS', '/NP')
    if ($excludeDirs.Count -gt 0) {
        $args += '/XD'
        $args += $excludeDirs
    }
    if ($excludeFiles.Count -gt 0) {
        $args += '/XF'
        $args += $excludeFiles
    }

    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed from $Source to $Destination with exit code $LASTEXITCODE"
    }
}

function Deploy-NativePayload {
    New-Item -ItemType Directory -Force -Path $PluginDir | Out-Null

    $nativeDir = Join-Path $RepoRoot "src\RookNative\bin\$Configuration\x64"

    Copy-RequiredFile (Join-Path $nativeDir 'RookNative.rhp') (Join-Path $PluginDir 'RookNative.rhp')
    Copy-OptionalFile (Join-Path $nativeDir 'RookNative.pdb') (Join-Path $PluginDir 'RookNative.pdb')
    Copy-OcctRuntimeDlls
}

function Remove-StaleRootCompanionPayload {
    foreach ($name in @('Rook.rhp', 'Rook.rui', 'Rook.deps.json', 'Rook.runtimeconfig.json')) {
        $path = Join-Path $PluginDir $name
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }

    $staleRootRuntimes = Join-Path $PluginDir 'runtimes'
    if (Test-Path $staleRootRuntimes) {
        Remove-Item -LiteralPath $staleRootRuntimes -Recurse -Force
    }

    $rootDllNames = [System.Collections.Generic.HashSet[string]]::new([System.StringComparer]::OrdinalIgnoreCase)
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $source = Join-Path $RepoRoot "src\Rook\bin\$Configuration\$runtime"
        if (Test-Path $source) {
            Get-ChildItem $source -Filter '*.dll' -File | ForEach-Object {
                [void]$rootDllNames.Add($_.Name)
            }
        }
    }

    foreach ($dllName in $rootDllNames) {
        $path = Join-Path $PluginDir $dllName
        if (Test-Path $path) {
            Remove-Item -LiteralPath $path -Force
        }
    }
}

function Deploy-CompanionRuntimePayload {
    param([Parameter(Mandatory = $true)][string]$Runtime)

    $sourceDir = Join-Path $RepoRoot "src\Rook\bin\$Configuration\$Runtime"
    $targetDir = Join-Path $PluginDir $Runtime

    Copy-RequiredFile (Join-Path $sourceDir 'Rook.rhp') (Join-Path $targetDir 'Rook.rhp')
    Remove-Item -LiteralPath (Join-Path $targetDir 'Rook.rui') -Force -ErrorAction SilentlyContinue
    if ($Runtime -ne 'net48') {
        Copy-RequiredFile (Join-Path $sourceDir 'Rook.deps.json') (Join-Path $targetDir 'Rook.deps.json')
        Copy-RequiredFile (Join-Path $sourceDir 'Rook.runtimeconfig.json') (Join-Path $targetDir 'Rook.runtimeconfig.json')
    } else {
        Copy-OptionalFile (Join-Path $sourceDir 'Rook.deps.json') (Join-Path $targetDir 'Rook.deps.json')
        Copy-OptionalFile (Join-Path $sourceDir 'Rook.runtimeconfig.json') (Join-Path $targetDir 'Rook.runtimeconfig.json')
    }

    Get-ChildItem $sourceDir -Filter '*.dll' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $targetDir $_.Name) -Force
    }

    Sync-Directory (Join-Path $sourceDir 'runtimes') (Join-Path $targetDir 'runtimes')
}

function Deploy-CompanionPayload {
    New-Item -ItemType Directory -Force -Path $PluginDir | Out-Null

    $ffmpegDir = Join-Path $RepoRoot 'third_party\ffmpeg'

    Remove-StaleRootCompanionPayload

    foreach ($runtime in $ManagedCompanionRuntimes) {
        Deploy-CompanionRuntimePayload -Runtime $runtime
    }

    if (Test-Path $ffmpegDir) {
        Sync-Directory $ffmpegDir (Join-Path $PluginDir 'ffmpeg')
    }
}

function Deploy-PluginPayload {
    Deploy-NativePayload
    Deploy-CompanionPayload
}

function Sync-AppPayload {
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $LogsRoot | Out-Null

    Sync-Directory (Join-Path $RepoRoot 'mcp_server') (Join-Path $InstallRoot 'mcp_server')
    Copy-EnvFileIfMissing (Join-Path $RepoRoot 'mcp_server\.env') (Join-Path $InstallRoot 'mcp_server\.env')
    Sync-Directory (Join-Path $RepoRoot 'knowledge') (Join-Path $InstallRoot 'knowledge')
    Sync-Directory (Join-Path $RepoRoot 'scripts') (Join-Path $InstallRoot 'scripts')

    foreach ($dir in @('.agents', '.claude', '.claude-plugin', 'hooks')) {
        $source = Join-Path $RepoRoot $dir
        if (Test-Path $source) {
            Sync-Directory $source (Join-Path $InstallRoot $dir) -ExtraExcludeDirs @('worktrees')
        }
    }

    foreach ($file in @('AGENT_SETUP.md', 'BUILDING.md', 'LICENSE', 'QUICK_START.md')) {
        Copy-OptionalFile (Join-Path $RepoRoot $file) (Join-Path $InstallRoot $file)
    }
    $requiredInstallerModules = @('post_install.py', 'python_runtime_install.py', 'process_rebuild_guard.py')
    foreach ($module in $requiredInstallerModules) {
        $modulePath = Join-Path $RepoRoot "installer\$module"
        if (-not (Test-Path $modulePath)) {
            throw "Required installer Python module not found: $modulePath"
        }
    }

    Get-ChildItem (Join-Path $RepoRoot 'installer') -Filter '*.py' -File | ForEach-Object {
        Copy-RequiredFile $_.FullName (Join-Path $InstallRoot $_.Name)
    }
    Copy-OptionalFile (Join-Path $RepoRoot 'installer\rook-icon.ico') (Join-Path $InstallRoot 'rook-icon.ico')
    Copy-OptionalFile (Join-Path $RepoRoot 'installer\CLAUDE.md') (Join-Path $InstallRoot 'CLAUDE.md')
    Copy-OptionalFile (Join-Path $RepoRoot 'installer\AGENTS.md') (Join-Path $InstallRoot 'AGENTS.md')
}

function Sync-ReleasePythonPayload {
    $sourceRuntime = Join-Path $RepoRoot 'installer\runtime'
    $sourceWheelhouse = Join-Path $sourceRuntime 'python-wheelhouse'

    if (-not (Test-Path -LiteralPath $sourceWheelhouse -PathType Container)) {
        throw "Staged release wheelhouse not found: $sourceWheelhouse"
    }

    $wheelFiles = @(Get-ChildItem -LiteralPath $sourceWheelhouse -Filter '*.whl' -File)
    if ($wheelFiles.Count -eq 0) {
        throw "Staged release wheelhouse contains no .whl files: $sourceWheelhouse"
    }

    $controlFiles = @(
        'requirements-bootstrap-lock.txt',
        'requirements-rook-lock.txt',
        'requirements-chirp-lock.txt',
        'python-runtime-manifest.json'
    )
    foreach ($file in $controlFiles) {
        $source = Join-Path $sourceRuntime $file
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Required staged release control file not found: $source"
        }
    }

    Sync-Directory $sourceWheelhouse (Join-Path $InstallRoot 'python-wheelhouse')
    foreach ($file in $controlFiles) {
        $source = Join-Path $sourceRuntime $file
        Copy-RequiredFile $source (Join-Path $InstallRoot $file)
    }
}

function Sync-ChirpPayload {
    if (-not (Test-Path (Join-Path $ChirpSourceRoot 'pyproject.toml'))) {
        throw "Chirp sibling repo not found or incomplete: $ChirpSourceRoot"
    }
    if (-not (Test-Path (Join-Path $ChirpSourceRoot 'src\chirp'))) {
        throw "Chirp source package not found: $(Join-Path $ChirpSourceRoot 'src\chirp')"
    }

    Sync-Directory $ChirpSourceRoot $ChirpInstallRoot -ExtraExcludeDirs @('traces') -ExtraExcludeFiles @('Chirp_API_Key.txt')
}

function Assert-PrimeRuntimePayload {
    if ([string]::IsNullOrWhiteSpace($PrimeRuntimePayload)) {
        throw 'A complete release deploy requires -PrimeRuntimePayload.'
    }
    $payload = Get-Item -LiteralPath $PrimeRuntimePayload -Force
    if (-not $payload.PSIsContainer -or ($payload.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Prime runtime payload must be a direct directory.'
    }
    if ($payload.Name -cnotmatch '^[A-F0-9]{64}$' -or $payload.Parent.Name -cne 'runtimes') {
        throw 'Prime payload must be an assembled runtimes/<runtime-id> directory.'
    }
    $siblings = @(Get-ChildItem -LiteralPath $payload.Parent.FullName -Directory | Where-Object { $_.Name -cmatch '^[A-F0-9]{64}$' })
    if ($siblings.Count -ne 1) { throw 'Select an assembly attempt containing exactly one runtime.' }
    $script:PrimeRuntimePayload = $payload.FullName
    if ([string]::IsNullOrWhiteSpace($PythonBuildRoot) -or -not [IO.Path]::IsPathRooted($PythonBuildRoot)) {
        throw 'Release payload admission requires an explicit absolute -PythonBuildRoot.'
    }
    $buildDirectory = Get-Item -LiteralPath $PythonBuildRoot -ErrorAction Stop
    if (-not $buildDirectory.PSIsContainer -or ($buildDirectory.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw 'Python build generation must be a direct directory.'
    }
    $verificationVenv = Join-Path $buildDirectory.FullName 'verify-rook-venv'
    $verificationRecord = Join-Path $buildDirectory.FullName 'verification-rook.json'
    $verificationPython = Join-Path $verificationVenv 'Scripts/python.exe'
    foreach ($path in @($verificationPython, $verificationRecord)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Sealed wheel verification input missing: $path" }
        if ((Get-Item -LiteralPath $path).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Sealed wheel verification input is a link: $path" }
    }
    if (Test-Path Env:PYTHONPATH) { throw 'PYTHONPATH must be absent for release payload admission.' }
    $wheelManifest = Get-Content -LiteralPath (Join-Path $RepoRoot 'installer/runtime/python-runtime-manifest.json') -Raw | ConvertFrom-Json
    $sourceCommit = (& git -C $RepoRoot rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or $wheelManifest.rook_git_sha -cne $sourceCommit) { throw 'Sealed wheel source commit differs.' }
    $project = Get-Content -LiteralPath (Join-Path $RepoRoot 'mcp_server/pyproject.toml') -Raw
    $sourceVersion = [regex]::Match($project, '(?m)^version\s*=\s*"([^"]+)"').Groups[1].Value
    if (-not $sourceVersion -or $wheelManifest.release_version -cne $sourceVersion) { throw 'Sealed wheel version differs.' }
    $originProbe = @'
import importlib.util, json, pathlib, sys
site = pathlib.Path(sys.argv[1]).resolve() / 'Lib' / 'site-packages'
record = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8'))
assert pathlib.Path(record["audit_site_packages"]).resolve() == site
manifest = json.loads(pathlib.Path(sys.argv[3]).read_text(encoding='utf-8'))
assert {key: value for key, value in record.items() if key != "audit_site_packages"} == manifest["verification"]["rook"], 'selected verification record differs from wheel manifest'
assert record["pip_install_no_index"] is True and record["pip_install_looked_in_links"] is True
assert record["pip_install_looked_in_indexes"] is False
assert record["pip_check"] == "No broken requirements found."
assert record["import_record"]["module"] == "rook" and record["import_record"]["origin"] == "site-packages"
spec = importlib.util.find_spec('rook.agent.chat.prime_runtime_artifact')
assert spec is not None and spec.origin and pathlib.Path(spec.origin).resolve().is_relative_to(site), 'verifier is not from sealed-wheel site-packages'
'@
    # Run the probe from a temp file: Windows PowerShell 5.1 re-quotes native arguments and
    # splits an inline script at its embedded double quotes.
    $originProbePath = Join-Path ([IO.Path]::GetTempPath()) ('rook-origin-probe-' + [Guid]::NewGuid().ToString('N') + '.py')
    [IO.File]::WriteAllText($originProbePath, $originProbe)
    try {
        & $verificationPython -I $originProbePath $verificationVenv $verificationRecord (Join-Path $RepoRoot 'installer/runtime/python-runtime-manifest.json')
        $originProbeExit = $LASTEXITCODE
    } finally {
        if (Test-Path -LiteralPath $originProbePath) { [IO.File]::Delete($originProbePath) }
    }
    if ($originProbeExit -ne 0) { throw 'Sealed-wheel verifier origin refused.' }
    & $verificationPython -I -m rook.agent.chat.prime_runtime_artifact verify --runtime-root $PrimeRuntimePayload --expected-runtime-id $payload.Name
    if ($LASTEXITCODE -ne 0) { throw 'Prime runtime payload verification refused.' }
}

function Deploy-ManagedOnlyPayload {
    # This is a code/resource update, not a dependency or first-install path.
    # Admit all three runtime outputs before replacing any installed bytes.
    $copies = @()
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $sourceDir = Join-Path $RepoRoot "src\Rook\bin\$Configuration\$runtime"
        $targetDir = Join-Path $PluginDir $runtime
        foreach ($path in @((Join-Path $sourceDir 'Rook.rhp'), (Join-Path $targetDir 'Rook.rhp'))) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                throw "Managed-only requires existing build and installed companions: $path"
            }
        }
        $dependencies = @(Get-ChildItem -LiteralPath $sourceDir -File -Filter '*.dll' |
            Where-Object { $_.Name -ne 'RookBim.dll' })
        foreach ($name in @('Rook.deps.json', 'Rook.runtimeconfig.json')) {
            $path = Join-Path $sourceDir $name
            if ($runtime -ne 'net48' -or (Test-Path -LiteralPath $path)) {
                $dependencies += Get-Item -LiteralPath $path
            }
        }
        $assets = Join-Path $sourceDir 'runtimes'
        if (Test-Path -LiteralPath $assets) {
            $dependencies += Get-ChildItem -LiteralPath $assets -Recurse -File
        }
        foreach ($dependency in $dependencies) {
            $relative = $dependency.FullName.Substring($sourceDir.Length + 1)
            $installed = Join-Path $targetDir $relative
            if (-not (Test-Path -LiteralPath $installed -PathType Leaf) -or
                (Get-FileHash -LiteralPath $dependency.FullName -Algorithm SHA256).Hash -ne
                (Get-FileHash -LiteralPath $installed -Algorithm SHA256).Hash) {
                throw "Managed-only dependency differs: $relative ($runtime). Use the full deployment workflow for dependency changes."
            }
        }
        foreach ($name in @('Rook.rhp', 'Rook.pdb')) {
            $source = Join-Path $sourceDir $name
            if (Test-Path -LiteralPath $source -PathType Leaf) {
                $copies += [pscustomobject]@{
                    Source = $source
                    Destination = Join-Path $targetDir $name
                    Hash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
                }
            }
        }
    }
    Assert-NoRunningRhino
    foreach ($copy in $copies) {
        Copy-RequiredFile $copy.Source $copy.Destination
        if ((Get-FileHash -LiteralPath $copy.Destination -Algorithm SHA256).Hash -ne $copy.Hash) {
            throw "Managed-only installed byte verification failed: $($copy.Destination)"
        }
        Write-Host "Verified SHA256 $($copy.Hash) $($copy.Destination)"
    }
}

function Stage-PrimeRuntimePayload {
    $parent = Join-Path $InstallRoot 'prime/.incoming'
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    $incoming = Join-Path $parent ([Guid]::NewGuid().ToString('N'))
    if (Test-Path -LiteralPath $incoming) { throw 'Incoming Prime generation already exists.' }
    Copy-Item -LiteralPath $PrimeRuntimePayload -Destination $incoming -Recurse
    return $incoming
}

function Invoke-PostInstallConfig {
    $python = Resolve-BootstrapPython
    $postInstall = Join-Path $InstallRoot 'post_install.py'
    $args = @(
        $postInstall,
        '--install-dir', $InstallRoot,
        '--runtime-root', $RuntimeRoot,
        '--mcp-server-dir', (Join-Path $InstallRoot 'mcp_server'),
        '--prime-incoming-dir', $PrimeIncomingDir,
        '--claude',
        '--codex',
        '--plugins',
        '--skip-validation'
    )
    if (Test-Path $ChirpInstallRoot) {
        $args += @('--chirp-dir', $ChirpInstallRoot)
        if ($SkipChirpInstall) {
            $args += '--skip-chirp-install'
        }
    }

    & $python @args
    if ($LASTEXITCODE -ne 0) {
        throw "post_install.py config refresh failed with exit code $LASTEXITCODE"
    }
}

function Install-ReleaseSourceIntoVenv {
    # Local-deploy coherence: make the release venv's importable `rook` match the
    # just-synced source. Invoke-PostInstallConfig installs the current sealed rook
    # wheel, while local source edits may be newer than that staged release payload.
    # The real release MCP config runs with empty PYTHONPATH and imports from
    # site-packages, so site-packages must hold the current local source.
    #
    # We MIRROR the package directory rather than pip-building from source:
    # mcp_server declares the hatchling build backend, which the release venv
    # does not carry, so `pip install --no-build-isolation --no-index` from
    # source would fail. A directory mirror is deterministic and fully offline.
    # Only the `rook` package dir is mirrored; the wheelhouse `rook-*.dist-info`
    # sibling is left intact for metadata. /MIR removes stale modules in the dest.
    $sourceRook = Join-Path $InstallRoot 'mcp_server\src\rook'
    $venvRoot = Split-Path -Parent (Split-Path -Parent $VenvPython)
    $destRook = Join-Path $venvRoot 'Lib\site-packages\rook'

    if (-not (Test-Path (Join-Path $sourceRook 'server.py'))) {
        throw "Release source mirror: rook package not found at $sourceRook (Sync-AppPayload must run first)."
    }
    if (-not (Test-Path $VenvPython)) {
        throw "Release source mirror: release venv python not found at $VenvPython (Invoke-PostInstallConfig must run first)."
    }

    Write-Host "Mirroring current rook source into the release venv site-packages (offline; robocopy /MIR)..."
    Write-Host "  source: $sourceRook"
    Write-Host "  dest:   $destRook"
    Sync-Directory $sourceRook $destRook
}

function Register-Plugins {
    $register = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
    & $register -NativeRhpPath (Join-Path $PluginDir 'RookNative.rhp') -CompanionRhpPath (Join-Path $PluginDir 'net8.0\Rook.rhp')
}

function Register-NativeOnlyPlugins {
    $register = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
    & $register -NativeRhpPath (Join-Path $PluginDir 'RookNative.rhp') -NativeOnlyPreserveCompanion
}

function Write-ChatServiceManifests {
    param([Parameter(Mandatory = $true)]$Contract)

    $manifest = [ordered]@{
        pythonPath = $Contract.PythonPath
        workingDirectory = $Contract.WorkingDirectory
        module = 'rook.agent.chat.service_main'
        owner = 'rhino-panel'
        pythonPathEntries = @($Contract.PythonPathEntries)
        environment = [ordered]@{
            PYTHONHOME = ''
            ROOK_INSTALL_ROOT = $Contract.InstallRoot.Replace('\', '/')
            ROOK_DATA_DIR = $Contract.DataRoot.Replace('\', '/')
            ROOK_MODE = $Contract.Mode
            DSPY_CACHEDIR = (Join-Path $Contract.DataRoot 'dspy-cache').Replace('\', '/')
            ROOK_DSPY_RESTRICT_PICKLE = '1'
            CHIRP_HOME = $ChirpInstallRoot.Replace('\', '/')
        }
    }

    if ($Contract.IsDev) {
        $manifest.environment.ROOK_PROJECT_ROOT = $Contract.ProjectRoot.Replace('\', '/')
    } else {
        $manifest.environment.PYTHONPATH = ''
    }

    $json = $manifest | ConvertTo-Json -Depth 6
    $targets = @((Join-Path $PluginDir 'RookChatService.json'))
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $runtimeDir = Join-Path $PluginDir $runtime
        if (Test-Path $runtimeDir) {
            $targets += Join-Path (Join-Path $PluginDir $runtime) 'RookChatService.json'
        }
    }

    foreach ($manifestPath in $targets) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $manifestPath) | Out-Null
        Set-Content -LiteralPath $manifestPath -Value $json -Encoding UTF8
        Write-Host "Wrote chat service manifest: $manifestPath"
    }
}

function Test-EffectiveRuntime {
    param([Parameter(Mandatory = $true)]$Contract)

    if (-not (Test-Path $Contract.PythonPath)) {
        throw "Runtime Python not found: $($Contract.PythonPath)"
    }

    $envKeys = @('ROOK_INSTALL_ROOT', 'ROOK_DATA_DIR', 'ROOK_MODE', 'ROOK_PROJECT_ROOT', 'PYTHONPATH')
    $savedEnv = @{}
    foreach ($key in $envKeys) {
        $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key)
    }

    $checkPath = $null
    try {
        $env:ROOK_INSTALL_ROOT = $Contract.InstallRoot.Replace('\', '/')
        $env:ROOK_DATA_DIR = $Contract.DataRoot.Replace('\', '/')
        $env:ROOK_MODE = $Contract.Mode
        if ($Contract.IsDev) {
            $env:ROOK_PROJECT_ROOT = $Contract.ProjectRoot.Replace('\', '/')
        } else {
            Remove-Item Env:\ROOK_PROJECT_ROOT -ErrorAction SilentlyContinue
        }
        $env:PYTHONPATH = (@($Contract.PythonPathEntries) -join [IO.Path]::PathSeparator)

        if ($Contract.IsDev) {
            $expectedRookPrefix = Join-Path $Contract.WorkingDirectory 'src\rook'
        } else {
            # Release venv site-packages: <PythonPath>\..\..\Lib\site-packages\rook
            $venvRoot = Split-Path -Parent (Split-Path -Parent $Contract.PythonPath)
            $expectedRookPrefix = Join-Path $venvRoot 'Lib\site-packages\rook'
        }
        $requireTools = if ($Contract.IsDev) { 'False' } else { 'True' }
        $check = @"
import json
from rook.runtime_paths import resolve_runtime_paths
import rook
import rook.server
paths = resolve_runtime_paths()
payload = {
    "rook_file": rook.__file__,
    "rook_server_file": rook.server.__file__,
    "mode": paths.mode,
    "install_root": str(paths.install_root),
    "data_root": str(paths.data_root),
    "mcp_server_dir": str(paths.mcp_server_dir),
}
print(json.dumps(payload, sort_keys=True))
if paths.mode != "$($Contract.Mode)":
    raise SystemExit("ROOK_MODE did not resolve to $($Contract.Mode)")
if str(paths.install_root).replace("\\", "/").lower() != r"$($Contract.InstallRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_INSTALL_ROOT mismatch")
if str(paths.data_root).replace("\\", "/").lower() != r"$($Contract.DataRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_DATA_DIR mismatch")
expected_rook_prefix = r"$($expectedRookPrefix.Replace('\','/').ToLowerInvariant())"
actual_rook_file = str(rook.__file__).replace("\\", "/").lower()
actual_server_file = str(rook.server.__file__).replace("\\", "/").lower()
if not actual_rook_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook imported from stale location: {rook.__file__}")
if not actual_server_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook.server imported from stale location: {rook.server.__file__}")
if $($requireTools):
    import asyncio
    from rook.server import list_tools
    names = {t.name for t in asyncio.run(list_tools())}
    required = {
        "rhino_2d_to_3d_models",
        "rhino_2d_to_3d_submit",
        "rhino_2d_to_3d_jobs",
        "rhino_2d_to_3d_status",
        "rhino_2d_to_3d_cancel",
        "rhino_2d_to_3d_result",
        "rhino_2d_to_3d_import",
    }
    missing = sorted(required - names)
    if missing:
        raise SystemExit(f"release MCP missing reconstruction tools: {missing}")
"@

        $checkPath = Join-Path $env:TEMP 'rook_deploy_local_testing_check.py'
        Set-Content -Path $checkPath -Value $check -Encoding UTF8
        & $Contract.PythonPath $checkPath
        if ($LASTEXITCODE -ne 0) {
            throw "Runtime verification failed."
        }
    } finally {
        if ($checkPath) {
            Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
        }
        foreach ($key in $envKeys) {
            [Environment]::SetEnvironmentVariable($key, $savedEnv[$key])
        }
    }
}

function Normalize-PathForCompare {
    param([string]$PathValue)
    return $PathValue.Replace('\', '/').TrimEnd('/').ToLowerInvariant()
}

function Assert-RookMcpEntry {
    param(
        [Parameter(Mandatory = $true)][string]$ConfigPath,
        [Parameter(Mandatory = $true)]$Entry
    )

    $expectedCommand = Normalize-PathForCompare $VenvPython
    $expectedCwd = Normalize-PathForCompare (Join-Path $InstallRoot 'mcp_server')
    $expectedInstallRoot = Normalize-PathForCompare $InstallRoot
    $expectedDataRoot = Normalize-PathForCompare $DataRoot
    $expectedChirpHome = Normalize-PathForCompare $ChirpInstallRoot

    if (-not $Entry) {
        throw "Missing Rook MCP entry in $ConfigPath"
    }

    $command = Get-ObjectValue -ObjectValue $Entry -Key 'command'
    $argsValue = Get-ObjectValue -ObjectValue $Entry -Key 'args'
    $cwd = Get-ObjectValue -ObjectValue $Entry -Key 'cwd'
    $envBlock = Get-ObjectValue -ObjectValue $Entry -Key 'env'

    if ((Normalize-PathForCompare ([string]$command)) -ne $expectedCommand) {
        throw "Rook MCP command mismatch in $ConfigPath`: $command"
    }

    $args = @($argsValue)
    if ($args.Count -ne 2 -or $args[0] -ne '-m' -or $args[1] -ne 'rook') {
        throw "Rook MCP args mismatch in $ConfigPath`: $($args -join ' ')"
    }

    if ((Normalize-PathForCompare ([string]$cwd)) -ne $expectedCwd) {
        throw "Rook MCP cwd mismatch in $ConfigPath`: $cwd"
    }

    if (-not $envBlock) {
        throw "Missing Rook MCP env block in $ConfigPath"
    }

    $expectedEnv = @{
        ROOK_INSTALL_ROOT = $expectedInstallRoot
        ROOK_DATA_DIR = $expectedDataRoot
        ROOK_MODE = 'release'
        CHIRP_HOME = $expectedChirpHome
    }

    foreach ($key in $expectedEnv.Keys) {
        $actual = [string](Get-ObjectValue -ObjectValue $envBlock -Key $key)
        if ($key -eq 'ROOK_MODE') {
            if ($actual -ne $expectedEnv[$key]) {
                throw "Rook MCP env $key mismatch in $ConfigPath`: $actual"
            }
        } elseif ((Normalize-PathForCompare $actual) -ne $expectedEnv[$key]) {
            throw "Rook MCP env $key mismatch in $ConfigPath`: $actual"
        }
    }
}

function Get-ObjectValue {
    param(
        [Parameter(Mandatory = $true)]$ObjectValue,
        [Parameter(Mandatory = $true)][string]$Key
    )

    if ($ObjectValue -is [System.Collections.IDictionary]) {
        return $ObjectValue[$Key]
    }

    $property = $ObjectValue.PSObject.Properties[$Key]
    if ($property) {
        return $property.Value
    }

    return $null
}

function Get-CodexRookMcpEntry {
    param([string]$ConfigPath)

    $entry = [ordered]@{
        command = $null
        args = @()
        cwd = $null
        env = [ordered]@{}
    }

    $section = ''
    foreach ($line in Get-Content -LiteralPath $ConfigPath) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith('#')) {
            continue
        }
        if ($trimmed -match '^\[(.+)\]$') {
            $section = $matches[1]
            continue
        }
        if ($section -ne 'mcp_servers.rook' -and $section -ne 'mcp_servers.rook.env') {
            continue
        }
        if ($trimmed -notmatch '^([A-Za-z0-9_]+)\s*=\s*(.+)$') {
            continue
        }

        $key = $matches[1]
        $rawValue = $matches[2].Trim()
        if ($rawValue.StartsWith('"') -and $rawValue.EndsWith('"')) {
            $value = $rawValue.Substring(1, $rawValue.Length - 2).Replace('\\"', '"').Replace('\\\\', '\')
        } elseif ($rawValue.StartsWith('[') -and $rawValue.EndsWith(']')) {
            $inner = $rawValue.Substring(1, $rawValue.Length - 2)
            $value = @()
            if ($inner.Trim()) {
                $value = @($inner.Split(',') | ForEach-Object { $_.Trim().Trim('"') })
            }
        } else {
            $value = $rawValue
        }

        if ($section -eq 'mcp_servers.rook.env') {
            $entry.env[$key] = $value
        } else {
            $entry[$key] = $value
        }
    }

    return [pscustomobject]$entry
}

function Get-JsonRookMcpEntry {
    param([string]$ConfigPath)

    $extract = @"
import json
import sys
from pathlib import Path
data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
entry = data.get("mcpServers", {}).get("rook")
if entry is None:
    raise SystemExit("missing mcpServers.rook")
print(json.dumps(entry))
"@

    $extractPath = Join-Path $env:TEMP 'rook_deploy_local_testing_json_entry.py'
    Set-Content -Path $extractPath -Value $extract -Encoding UTF8
    try {
        $entryJson = & $VenvPython $extractPath $ConfigPath
        if ($LASTEXITCODE -ne 0 -or -not $entryJson) {
            throw "Could not extract mcpServers.rook from $ConfigPath"
        }
        return ($entryJson -join "`n") | ConvertFrom-Json
    } finally {
        Remove-Item -LiteralPath $extractPath -ErrorAction SilentlyContinue
    }
}

function Test-McpClientConfigs {
    $claudeUserConfig = Join-Path $HOME '.claude.json'
    $claudeDesktopConfig = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Claude\claude_desktop_config.json'
    $codexConfig = Join-Path $HOME '.codex\config.toml'
    $checked = 0

    if (Test-Path $claudeUserConfig) {
        Assert-RookMcpEntry -ConfigPath $claudeUserConfig -Entry (Get-JsonRookMcpEntry -ConfigPath $claudeUserConfig)
        $checked += 1
    }

    if (Test-Path $claudeDesktopConfig) {
        Assert-RookMcpEntry -ConfigPath $claudeDesktopConfig -Entry (Get-JsonRookMcpEntry -ConfigPath $claudeDesktopConfig)
        $checked += 1
    }

    if (Test-Path $codexConfig) {
        Assert-RookMcpEntry -ConfigPath $codexConfig -Entry (Get-CodexRookMcpEntry -ConfigPath $codexConfig)
        $checked += 1
    }

    if ($checked -eq 0) {
        throw "No MCP client config files were found to verify."
    }
}

function Test-ChatServiceManifestAtPath {
    param(
        [Parameter(Mandatory = $true)][string]$ManifestPath,
        [Parameter(Mandatory = $true)]$Contract
    )

    if (-not (Test-Path $manifestPath)) {
        throw "Chat service manifest not found: $manifestPath"
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $expectedPython = Normalize-PathForCompare $Contract.PythonPath
    $expectedWorkingDirectory = Normalize-PathForCompare $Contract.WorkingDirectory

    if ((Normalize-PathForCompare ([string]$manifest.pythonPath)) -ne $expectedPython) {
        throw "Chat service pythonPath mismatch in $ManifestPath`: $($manifest.pythonPath)"
    }
    if ((Normalize-PathForCompare ([string]$manifest.workingDirectory)) -ne $expectedWorkingDirectory) {
        throw "Chat service workingDirectory mismatch in $ManifestPath`: $($manifest.workingDirectory)"
    }
    if ($manifest.module -ne 'rook.agent.chat.service_main') {
        throw "Chat service module mismatch in $ManifestPath`: $($manifest.module)"
    }

    $entries = @($manifest.pythonPathEntries)
    if ($Contract.IsDev) {
        $expectedSourcePath = Normalize-PathForCompare ([string]@($Contract.PythonPathEntries)[0])
        if ($entries.Count -lt 1 -or (Normalize-PathForCompare ([string]$entries[0])) -ne $expectedSourcePath) {
            throw "Chat service pythonPathEntries mismatch in $ManifestPath`: $($entries -join ', ')"
        }
    } else {
        # Release imports rook from site-packages, so pythonPathEntries must be
        # empty/absent (matching the empty-PYTHONPATH MCP config).
        $nonEmptyEntries = @($entries | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        if ($nonEmptyEntries.Count -gt 0) {
            throw "Chat service pythonPathEntries must be empty in release in $ManifestPath`: $($entries -join ', ')"
        }
    }

    $envBlock = $manifest.environment
    if (-not $envBlock) {
        throw "Chat service environment missing in $ManifestPath"
    }
    if ([string]$envBlock.ROOK_MODE -ne $Contract.Mode) {
        throw "Chat service ROOK_MODE mismatch in $ManifestPath`: $($envBlock.ROOK_MODE)"
    }
    if ((Normalize-PathForCompare ([string]$envBlock.ROOK_INSTALL_ROOT)) -ne (Normalize-PathForCompare $Contract.InstallRoot)) {
        throw "Chat service ROOK_INSTALL_ROOT mismatch in $ManifestPath`: $($envBlock.ROOK_INSTALL_ROOT)"
    }
    if ((Normalize-PathForCompare ([string]$envBlock.ROOK_DATA_DIR)) -ne (Normalize-PathForCompare $Contract.DataRoot)) {
        throw "Chat service ROOK_DATA_DIR mismatch in $ManifestPath`: $($envBlock.ROOK_DATA_DIR)"
    }
    if ($Contract.IsDev) {
        if ((Normalize-PathForCompare ([string]$envBlock.ROOK_PROJECT_ROOT)) -ne (Normalize-PathForCompare $Contract.ProjectRoot)) {
            throw "Chat service ROOK_PROJECT_ROOT mismatch in $ManifestPath`: $($envBlock.ROOK_PROJECT_ROOT)"
        }
    } else {
        if (-not [string]::IsNullOrEmpty([string]$envBlock.PYTHONPATH)) {
            throw "Chat service PYTHONPATH must be empty in release in $ManifestPath`: $($envBlock.PYTHONPATH)"
        }
    }
}

function Test-ChatServiceManifest {
    param([Parameter(Mandatory = $true)]$Contract)

    Test-ChatServiceManifestAtPath -ManifestPath (Join-Path $PluginDir 'RookChatService.json') -Contract $Contract
    foreach ($runtime in $ManagedCompanionRuntimes) {
        $runtimeDir = Join-Path $PluginDir $runtime
        if (Test-Path $runtimeDir) {
            Test-ChatServiceManifestAtPath -ManifestPath (Join-Path $runtimeDir 'RookChatService.json') -Contract $Contract
        }
    }
}

function Test-ChirpRuntime {
    $chirpPython = Join-Path $ChirpInstallRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path (Join-Path $ChirpInstallRoot 'pyproject.toml'))) {
        throw "Installed Chirp pyproject.toml not found: $ChirpInstallRoot"
    }
    if (-not (Test-Path (Join-Path $ChirpInstallRoot 'src\chirp'))) {
        throw "Installed Chirp source package not found: $(Join-Path $ChirpInstallRoot 'src\chirp')"
    }
    if (-not (Test-Path $chirpPython)) {
        throw "Installed Chirp venv Python not found: $chirpPython"
    }

    $expected = $ChirpInstallRoot.Replace('\', '/').ToLowerInvariant()
    $check = @"
import json
import chirp
from pathlib import Path
payload = {
    "chirp_file": chirp.__file__,
    "chirp_root": str(Path(chirp.__file__).resolve().parents[2]),
}
print(json.dumps(payload, sort_keys=True))
if not str(Path(chirp.__file__).resolve()).replace("\\", "/").lower().startswith(r"$expected"):
    raise SystemExit("chirp did not import from installed AppData Chirp")
"@

    $checkPath = Join-Path $env:TEMP 'rook_deploy_local_testing_chirp_check.py'
    Set-Content -Path $checkPath -Value $check -Encoding UTF8
    try {
        & $chirpPython $checkPath
        if ($LASTEXITCODE -ne 0) {
            throw "Installed Chirp verification failed."
        }
    } finally {
        Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
    }

}

function Test-LiveSmoke {
    param([Parameter(Mandatory = $true)][pscustomobject]$Contract)

    $smoke = @"
import asyncio
import json
from rook.bridge import call_rhino
from rook.local_testing_proof import ProofFailure, _run_chirp_smoke_mutation
from rook.server import _call_tool_dispatch, call_tool, list_tools

async def public_call(name, arguments):
    response = await call_tool(name, arguments)
    if not response:
        raise SystemExit(f"{name} returned no content")
    text = str(response[0].text)
    if text.startswith("Error:"):
        raise SystemExit(f"{name} failed: {text}")
    return json.loads(text)

async def main():
    ping = await _call_tool_dispatch("rhino_ping", {})
    if not ping.get("success"):
        raise SystemExit(f"rhino_ping failed: {ping}")

    status = await _call_tool_dispatch("gh_status", {})
    if not status.get("success"):
        raise SystemExit(f"gh_status failed: {status}")

    tools = await list_tools()
    names = {tool.name for tool in tools}
    gateways = {"rook_tools_ls", "rook_tools_search", "rook_tools_read", "rook_tools_call"}
    if not gateways <= names or "gh_status" in names:
        raise SystemExit(f"lean progressive catalog failed: names={sorted(names)}")
    search = await public_call("rook_tools_search", {"query": "gh_status", "limit": 10})
    if not any(item.get("name") == "gh_status" for item in search):
        raise SystemExit(f"gh_status exact-name search failed: {search}")
    read = await public_call("rook_tools_read", {"name": "gh_status"})
    if not (read.get("name") == "gh_status" and read.get("mcp_dispatchable") is True
            and isinstance(read.get("input_schema"), dict)
            and read["input_schema"].get("type") == "object"):
        raise SystemExit(f"gh_status read contract failed: {read}")
    called = await public_call("rook_tools_call", {"name": "gh_status", "arguments": {}})
    progressive_discovery = {
        "profile": "lean", "gateways": sorted(gateways), "target": "gh_status",
        "target_hidden": True, "search": search, "read": read, "call": called,
    }

    try:
        mutation = await _run_chirp_smoke_mutation(
            {},
            component_name="Rook Local Deploy Smoke",
            dispatch_fn=_call_tool_dispatch,
            call_rhino_fn=call_rhino,
        )
    except ProofFailure as exc:
        failure_payload = {
            "failure_label": exc.failure_label,
            "message": str(exc),
            "details": exc.details,
        }
        raise SystemExit(json.dumps(failure_payload, default=str, sort_keys=True))

    live_evidence = {
        "rhino_ping": ping,
        "gh_status": status,
        "progressive_discovery": progressive_discovery,
        "chirp_create": mutation["chirp_create"],
        "gh_errors": mutation["gh_errors"],
        "gh_undo": mutation["gh_undo"],
    }
    print(json.dumps(live_evidence, default=str, sort_keys=True))

asyncio.run(main())
"@

    $smokePath = Join-Path $env:TEMP 'rook_deploy_local_testing_live_smoke.py'
    $environmentNames = @(
        'ROOK_MODE',
        'ROOK_INSTALL_ROOT',
        'ROOK_DATA_DIR',
        'CHIRP_HOME',
        'ROOK_PROJECT_ROOT',
        'ROOK_MCP_TOOL_PROFILE',
        'PYTHONPATH'
    )
    $previousEnvironment = @{}
    foreach ($name in $environmentNames) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }

    $locationPushed = $false
    Set-Content -Path $smokePath -Value $smoke -Encoding UTF8
    try {
        $environmentPropertyNames = @($Contract.Environment.PSObject.Properties.Name)
        foreach ($name in $environmentNames) {
            if ($environmentPropertyNames -contains $name) {
                [Environment]::SetEnvironmentVariable($name, [string]$Contract.Environment.$name, 'Process')
            } else {
                [Environment]::SetEnvironmentVariable($name, $null, 'Process')
            }
        }

        [Environment]::SetEnvironmentVariable('ROOK_MCP_TOOL_PROFILE', 'lean', 'Process')

        Push-Location $Contract.WorkingDirectory
        $locationPushed = $true
        & $Contract.PythonPath $smokePath
        if ($LASTEXITCODE -ne 0) {
            throw "Live Rhino/Grasshopper/Chirp smoke failed."
        }
    } finally {
        if ($locationPushed) {
            Pop-Location
        }

        foreach ($name in $environmentNames) {
            [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name], 'Process')
        }

        Remove-Item -LiteralPath $smokePath -ErrorAction SilentlyContinue
    }
}

Set-Location $RepoRoot
Assert-DeployMode
if ($ManagedOnly) {
    Assert-NoRunningRhino
    if (-not $SkipBuild) {
        Write-Step "Build managed companion only (no restore or automatic deploy)"
        Invoke-ManagedBuild -CompanionOnly
    }
    Deploy-ManagedOnlyPayload
    Write-Host "Managed-only deploy complete. Only Rook.rhp and available Rook.pdb files were replaced."
    Write-Host "Native, BIM, Python, Prime, Chirp, manifests and registration remain unchanged."
    Write-Host "This local mixed-version installation is not a full release qualification. Restart Rhino to test."
    exit 0
}
$RuntimeContract = Resolve-DeployRuntimeContract

if ($ManifestSmokeOnly) {
    Write-Step "Dev manifest smoke"
    Write-Host "Mode:             $($RuntimeContract.Mode)"
    Write-Host "Python:           $($RuntimeContract.PythonPath)"
    Write-Host "WorkingDirectory: $($RuntimeContract.WorkingDirectory)"
    Write-Host "ProjectRoot:      $($RuntimeContract.ProjectRoot)"
    Write-Host "SourcePath:       $(@($RuntimeContract.PythonPathEntries)[0])"
    exit 0
}

if ($NativeOnly) {
    Write-Step "Native-only deploy surfaces"
    Write-Host "  Builds native:           $(-not $SkipBuild)"
    Write-Host "  Copies native payload:   true"
    Write-Host "  Updates native registry: true"
    Write-Host "  Copies companion:        false"
    Write-Host "  Syncs MCP payload:       false"
    Write-Host "  Syncs Chirp payload:     false"
    Write-Host "  Refreshes MCP config:    false"
    Write-Host "  Checks MCP processes:    false"

    Assert-NoRunningRhino

    if (-not $SkipBuild) {
        Write-Step "Build native plugin"
        Invoke-NativeBuild
    } else {
        Write-Step "Build native plugin"
        Write-Host "Skipping native build because -SkipBuild was specified."
    }

    Write-Step "Deploy native plugin payload"
    Deploy-NativePayload

    Write-Step "Register native plugin"
    Register-NativeOnlyPlugins

    Write-Host ""
    Write-Host "Skipping MCP payload, Chirp payload, post-install config, and MCP client config validation."
    Write-Host ""
    Write-Host "Native-only deploy complete."
    Write-Host "  Repo:       $RepoRoot"
    Write-Host "  PluginDir:  $PluginDir"
    Write-Host ""
    Write-Host "Restart Rhino before testing native plugin changes loaded before this deploy."
    exit 0
}

if (-not $RuntimeContract.IsDev) { Assert-PrimeRuntimePayload }
Assert-NoRunningFullDeployBlockers

if (-not $PayloadOnly) {
    if (-not $SkipBuild) {
        Write-Step "Build native plugin"
        Invoke-NativeBuild

        Write-Step "Build managed companion"
        Invoke-ManagedBuild
    }

    Write-Step "Deploy Rhino plugin payload"
    Deploy-PluginPayload

    Write-Step "Register Rhino plugins"
    Register-Plugins
} else {
    Write-Step "Payload-only deploy"
    Write-Host "Skipping native/managed build, plugin copy, and Rhino registration."
}

Write-Step "Sync installed AppData runtime payload"
Sync-AppPayload

Write-Step "Sync installed Chirp payload"
Sync-ChirpPayload

if ($RuntimeContract.IsDev) {
    Write-Step "Refresh dev chat runtime manifest"
    Write-Host "Skipping release post_install.py because an explicit dev runtime was selected."
    Write-ChatServiceManifests -Contract $RuntimeContract
} else {
    Write-Step "Sync sealed Python release payload"
    Sync-ReleasePythonPayload
    $PrimeIncomingDir = Stage-PrimeRuntimePayload
    Write-Step "Refresh MCP, Chirp, and config installs"
    Invoke-PostInstallConfig
    Write-Step "Mirror current source into release venv site-packages"
    Install-ReleaseSourceIntoVenv
    Write-ChatServiceManifests -Contract $RuntimeContract
}

Write-Step "Verify effective runtime"
Test-EffectiveRuntime -Contract $RuntimeContract

if ($RuntimeContract.IsDev) {
    Write-Step "Verify dev chat manifest"
    Write-Host "Skipping release MCP client config and Chirp venv verification because an explicit dev runtime was selected."
    Test-ChatServiceManifest -Contract $RuntimeContract
} else {
    Write-Step "Verify installed Chirp runtime"
    Test-ChirpRuntime

    Write-Step "Verify MCP client config and chat manifest"
    Test-McpClientConfigs
    Test-ChatServiceManifest -Contract $RuntimeContract
}

if ($LiveSmoke) {
    Write-Step "Run live Rhino/Grasshopper/Chirp smoke"
    Test-LiveSmoke -Contract $RuntimeContract
} else {
    Write-Host ""
    Write-Host "Live Rhino/Grasshopper/Chirp smoke not run. Use -PayloadOnly -AllowRunning -LiveSmoke after restarting Rhino."
    Write-Host "Dev runtime smoke: use -PayloadOnly -AllowRunning -UseRepoVenv -LiveSmoke, or pass -DevPythonRuntime with a Python executable path."
}

Write-Host ""
Write-Host "Local testing deploy complete."
Write-Host "  Repo:         $RepoRoot"
Write-Host "  InstallRoot:  $InstallRoot"
Write-Host "  DataRoot:     $DataRoot"
Write-Host "  PluginDir:    $PluginDir"
Write-Host "  ChirpRoot:    $ChirpInstallRoot"
Write-Host "  Python:       $VenvPython"
Write-Host ""
Write-Host "Restart Rhino and MCP clients before testing changes loaded before this deploy."
