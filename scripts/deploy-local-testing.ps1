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

    [switch]$PayloadOnly,
    [switch]$AllowRunning,
    [switch]$SkipBuild,
    [switch]$SkipChirpInstall,
    [switch]$LiveSmoke
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

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message =="
}

function Assert-NoRunningRook {
    $rhino = Get-Process | Where-Object { $_.ProcessName -match '^(Rhino|Rhinoceros)$' }
    $rookPython = Get-CimInstance Win32_Process -Filter "Name = 'python.exe'" |
        Where-Object { $_.CommandLine -match '(^|\s)-m\s+rook(\s|$)' }

    if (($rhino -or $rookPython) -and -not $AllowRunning) {
        if ($rhino) {
            $rhino | Select-Object ProcessName, Id, Path | Format-Table | Out-String | Write-Host
        }
        if ($rookPython) {
            $rookPython | Select-Object ProcessId, CommandLine | Format-Table -Wrap | Out-String | Write-Host
        }
        throw "Refusing deploy while Rhino or python -m rook is running. Close them first, or use -PayloadOnly -AllowRunning for payload-only sync."
    }

    if ($AllowRunning -and -not $PayloadOnly) {
        throw "-AllowRunning is only permitted with -PayloadOnly. Full plugin deploy requires Rhino and rook MCP processes to be stopped."
    }

    if ($LiveSmoke -and -not ($PayloadOnly -and $AllowRunning)) {
        throw "-LiveSmoke requires -PayloadOnly -AllowRunning. Run the full deploy first, restart Rhino/Grasshopper, then run payload-only live smoke."
    }
}

function Resolve-BootstrapPython {
    $candidates = @()
    if (Test-Path $VenvPython) {
        $candidates += $VenvPython
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
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Python 3.10+ was not found."
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
    & dotnet build (Join-Path $RepoRoot 'src\Rook\Rook.csproj') -f net7.0 -c $Configuration
    if ($LASTEXITCODE -ne 0) {
        throw "Managed build failed."
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

function Deploy-PluginPayload {
    New-Item -ItemType Directory -Force -Path $PluginDir | Out-Null

    $nativeDir = Join-Path $RepoRoot "src\RookNative\bin\$Configuration\x64"
    $companionDir = Join-Path $RepoRoot "src\Rook\bin\$Configuration\net7.0"
    $ffmpegDir = Join-Path $RepoRoot 'third_party\ffmpeg'

    Copy-RequiredFile (Join-Path $nativeDir 'RookNative.rhp') (Join-Path $PluginDir 'RookNative.rhp')
    Copy-OptionalFile (Join-Path $nativeDir 'RookNative.pdb') (Join-Path $PluginDir 'RookNative.pdb')

    foreach ($name in @('Rook.rhp', 'Rook.rui', 'Rook.deps.json', 'Rook.runtimeconfig.json')) {
        Copy-RequiredFile (Join-Path $companionDir $name) (Join-Path $PluginDir $name)
    }
    Get-ChildItem $companionDir -Filter '*.dll' -File | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $PluginDir $_.Name) -Force
    }
    Sync-Directory (Join-Path $companionDir 'runtimes') (Join-Path $PluginDir 'runtimes')

    if (Test-Path $ffmpegDir) {
        Sync-Directory $ffmpegDir (Join-Path $PluginDir 'ffmpeg')
    }
}

function Sync-AppPayload {
    New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $DataRoot | Out-Null
    New-Item -ItemType Directory -Force -Path $LogsRoot | Out-Null

    Sync-Directory (Join-Path $RepoRoot 'mcp_server') (Join-Path $InstallRoot 'mcp_server')
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
    Copy-RequiredFile (Join-Path $RepoRoot 'installer\post_install.py') (Join-Path $InstallRoot 'post_install.py')
    Copy-OptionalFile (Join-Path $RepoRoot 'installer\rook-icon.ico') (Join-Path $InstallRoot 'rook-icon.ico')
    Copy-OptionalFile (Join-Path $RepoRoot 'installer\CLAUDE.md') (Join-Path $InstallRoot 'CLAUDE.md')
    Copy-OptionalFile (Join-Path $RepoRoot 'installer\AGENTS.md') (Join-Path $InstallRoot 'AGENTS.md')
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

function Invoke-PostInstallConfig {
    $python = Resolve-BootstrapPython
    $postInstall = Join-Path $InstallRoot 'post_install.py'
    $args = @(
        $postInstall,
        '--install-dir', $InstallRoot,
        '--runtime-root', $RuntimeRoot,
        '--mcp-server-dir', (Join-Path $InstallRoot 'mcp_server'),
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

function Register-Plugins {
    $register = Join-Path $RepoRoot 'scripts\register-rooknative-suite.ps1'
    & $register -NativeRhpPath (Join-Path $PluginDir 'RookNative.rhp') -CompanionRhpPath (Join-Path $PluginDir 'Rook.rhp')
}

function Test-EffectiveRuntime {
    if (-not (Test-Path $VenvPython)) {
        throw "Installed venv Python not found: $VenvPython"
    }

    $env:ROOK_INSTALL_ROOT = $InstallRoot.Replace('\', '/')
    $env:ROOK_DATA_DIR = $DataRoot.Replace('\', '/')
    $env:ROOK_MODE = 'release'

    $check = @"
import json
from rook.runtime_paths import resolve_runtime_paths
import rook
paths = resolve_runtime_paths()
payload = {
    "rook_file": rook.__file__,
    "mode": paths.mode,
    "install_root": str(paths.install_root),
    "data_root": str(paths.data_root),
    "mcp_server_dir": str(paths.mcp_server_dir),
}
print(json.dumps(payload, sort_keys=True))
if paths.mode != "release":
    raise SystemExit("ROOK_MODE did not resolve to release")
if str(paths.install_root).replace("\\", "/").lower() != r"$($InstallRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_INSTALL_ROOT mismatch")
if str(paths.data_root).replace("\\", "/").lower() != r"$($DataRoot.Replace('\','/').ToLowerInvariant())":
    raise SystemExit("ROOK_DATA_DIR mismatch")
expected_rook_prefix = r"$(((Join-Path $InstallRoot 'mcp_server\src\rook').Replace('\','/')).ToLowerInvariant())"
actual_rook_file = str(rook.__file__).replace("\\", "/").lower()
if not actual_rook_file.startswith(expected_rook_prefix):
    raise SystemExit(f"rook imported from stale location: {rook.__file__}")
"@

    $checkPath = Join-Path $env:TEMP 'rook_deploy_local_testing_check.py'
    Set-Content -Path $checkPath -Value $check -Encoding UTF8
    try {
        & $VenvPython $checkPath
        if ($LASTEXITCODE -ne 0) {
            throw "Installed runtime verification failed."
        }
    } finally {
        Remove-Item -LiteralPath $checkPath -ErrorAction SilentlyContinue
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

function Test-ChatServiceManifest {
    $manifestPath = Join-Path $PluginDir 'RookChatService.json'
    if (-not (Test-Path $manifestPath)) {
        throw "Chat service manifest not found: $manifestPath"
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $expectedPython = Normalize-PathForCompare $VenvPython
    $expectedWorkingDirectory = Normalize-PathForCompare (Join-Path $InstallRoot 'mcp_server')
    $expectedSourcePath = Normalize-PathForCompare (Join-Path $InstallRoot 'mcp_server\src')

    if ((Normalize-PathForCompare ([string]$manifest.pythonPath)) -ne $expectedPython) {
        throw "Chat service pythonPath mismatch: $($manifest.pythonPath)"
    }
    if ((Normalize-PathForCompare ([string]$manifest.workingDirectory)) -ne $expectedWorkingDirectory) {
        throw "Chat service workingDirectory mismatch: $($manifest.workingDirectory)"
    }
    if ($manifest.module -ne 'rook.agent.chat.service_main') {
        throw "Chat service module mismatch: $($manifest.module)"
    }

    $entries = @($manifest.pythonPathEntries)
    if ($entries.Count -lt 1 -or (Normalize-PathForCompare ([string]$entries[0])) -ne $expectedSourcePath) {
        throw "Chat service pythonPathEntries mismatch: $($entries -join ', ')"
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
    $env:ROOK_INSTALL_ROOT = $InstallRoot.Replace('\', '/')
    $env:ROOK_DATA_DIR = $DataRoot.Replace('\', '/')
    $env:ROOK_MODE = 'release'
    $env:CHIRP_HOME = $ChirpInstallRoot.Replace('\', '/')

    $smoke = @"
import asyncio
import json
from rook.server import _call_tool_dispatch

async def main():
    ping = await _call_tool_dispatch("rhino_ping", {})
    if not ping.get("success"):
        raise SystemExit(f"rhino_ping failed: {ping}")

    status = await _call_tool_dispatch("gh_status", {})
    if not status.get("success"):
        raise SystemExit(f"gh_status failed: {status}")

    chirp = await _call_tool_dispatch("chirp_create", {
        "category": "classifier",
        "name": "Rook Local Deploy Smoke",
        "pins_in": [{"name": "Input", "type": "string", "optional": True}],
        "pins_out": [{"name": "Result", "type": "string"}],
        "signature": "input -> result",
        "deterministic_code": "Result = Input ?? string.Empty;",
        "x": 40,
        "y": 40,
    })
    print(json.dumps({"rhino_ping": ping, "gh_status": status, "chirp_create": chirp}, default=str))
    if not chirp.get("success"):
        raise SystemExit(f"chirp_create failed: {chirp}")
    chirp_data = chirp.get("data") or {}
    if chirp_data.get("compilation_errors") or chirp_data.get("warning"):
        raise SystemExit(f"chirp_create produced component warnings/errors: {chirp_data}")

    component_guid = chirp_data.get("component_guid")
    errors = await _call_tool_dispatch("gh_errors", {})
    if not errors.get("success"):
        raise SystemExit(f"gh_errors failed after chirp_create: {errors}")
    for item in (errors.get("data") or {}).get("errors", []):
        if item.get("guid") == component_guid and item.get("errors"):
            raise SystemExit(f"created Chirp component has Grasshopper errors: {item}")

    undo = await _call_tool_dispatch("gh_undo", {})
    if not undo.get("success"):
        raise SystemExit(f"gh_undo cleanup failed: {undo}")

asyncio.run(main())
"@

    $smokePath = Join-Path $env:TEMP 'rook_deploy_local_testing_live_smoke.py'
    Set-Content -Path $smokePath -Value $smoke -Encoding UTF8
    try {
        & $VenvPython $smokePath
        if ($LASTEXITCODE -ne 0) {
            throw "Live Rhino/Grasshopper/Chirp smoke failed."
        }
    } finally {
        Remove-Item -LiteralPath $smokePath -ErrorAction SilentlyContinue
    }
}

Set-Location $RepoRoot
Assert-NoRunningRook

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

Write-Step "Refresh MCP, Chirp, and config installs"
Invoke-PostInstallConfig

Write-Step "Verify effective installed runtime"
Test-EffectiveRuntime

Write-Step "Verify installed Chirp runtime"
Test-ChirpRuntime

Write-Step "Verify MCP client config and chat manifest"
Test-McpClientConfigs
Test-ChatServiceManifest

if ($LiveSmoke) {
    Write-Step "Run live Rhino/Grasshopper/Chirp smoke"
    Test-LiveSmoke
} else {
    Write-Host ""
    Write-Host "Live Rhino/Grasshopper/Chirp smoke not run. Use -PayloadOnly -AllowRunning -LiveSmoke after restarting Rhino."
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
