# ============================================================================
# Rook Installer for Windows (PowerShell)
# ============================================================================
# Deterministic installer with a stable result contract.
# Primary caller: AI agents. See docs/plans/2026-04-02-install-ps1-refactor-design.md
#
# Exit codes:
#   0 - fully functional install (rhino_ping will work)
#   1 - hard failure
#   2 - partial install (runtime may exist, Rhino bridge not functional)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#   powershell -ExecutionPolicy Bypass -File install.ps1 -UserConfig
#   powershell -ExecutionPolicy Bypass -File install.ps1 -DryRun -Json
#   powershell -ExecutionPolicy Bypass -File install.ps1 -RequireNative
# ============================================================================

param(
    # Existing
    [switch]$UserConfig,

    # Mode controls
    [switch]$RequireNative,       # exit 1 if C++ prerequisites missing
    [switch]$SkipNative,          # don't attempt C++ build
    [switch]$SkipChirp,           # don't set up Chirp adapter
    [switch]$SkipConfig,          # don't write MCP client configs
    [switch]$NoVerify,            # skip final verification pass
    [switch]$DryRun,              # check prerequisites, report planned actions

    # Output
    [switch]$Json,                # print summary JSON to stdout at end
    [string]$SummaryPath,         # override summary file location

    # Toolchain override
    [string]$VCToolsVersion       # override MSVC toolset version
)

# Note: We intentionally do NOT set $ErrorActionPreference = "Stop" here
# because external tools (uv, dotnet) write info messages to stderr, and
# PowerShell treats any stderr output as a non-terminating error that would
# kill the script under "Stop" mode. We handle errors explicitly instead.

# ============================================================================
# Summary Helpers
# ============================================================================

function New-StepResult {
    param([string]$State = "pending")
    return @{ state = $State }
}

function New-InstallSummary {
    param(
        [string]$Mode,
        [bool]$IsDryRun,
        [string]$SummaryFilePath
    )
    return @{
        success                 = $false
        exit_code               = 1
        dry_run                 = $IsDryRun
        mode                    = $Mode
        timestamp               = (Get-Date -Format "o")
        rhino_bridge_functional = $false
        full_stack_functional   = $false
        steps                   = @{
            python       = New-StepResult
            chirp        = New-StepResult
            native       = @{
                state            = "pending"
                build_attempted  = $false
                built            = $false
                installed        = $false
                registered       = $false
                ready            = $false
            }
            companion    = @{
                state            = "pending"
                build_attempted  = $false
                built            = $false
                installed        = $false
                registered       = $false
                ready            = $false
            }
            config       = @{
                state               = "pending"
                repo_config_written = $false
                user_config_written = $false
            }
            verification = New-StepResult
        }
        toolchain               = @{
            vs_edition          = $null
            vc_tools_version    = $null
            native_build_script = $null
        }
        paths                   = @{
            python           = $null
            venv             = $null
            native_rhp       = $null
            companion_rhp    = $null
            plugin_dir       = $null
            repo_mcp_config  = $null
            user_mcp_config  = $null
        }
        warnings                = @()
        errors                  = @()
        next_actions            = @()
        planned_actions         = @()
        _summary_path           = $SummaryFilePath
    }
}

function Add-InstallWarning {
    param(
        [hashtable]$Summary,
        [string]$Code,
        [string]$Message,
        [string]$Remediation = ""
    )
    $Summary.warnings += @{
        code        = $Code
        message     = $Message
        remediation = $Remediation
    }
    Write-Host "      [WARN] $Message" -ForegroundColor Yellow
}

function Add-InstallError {
    param(
        [hashtable]$Summary,
        [string]$Code,
        [string]$Message,
        [string]$Remediation = ""
    )
    $Summary.errors += @{
        code        = $Code
        message     = $Message
        remediation = $Remediation
    }
    Write-Host "      [ERROR] $Message" -ForegroundColor Red
}

function Write-InstallSummary {
    param([hashtable]$Summary)
    if ($Summary.dry_run) { return }
    $path = $Summary._summary_path
    if (-not $path) { return }
    $parentDir = Split-Path -Parent $path
    if ($parentDir -and -not (Test-Path $parentDir)) {
        New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
    }
    # Remove internal fields before serialization
    $export = @{}
    foreach ($key in $Summary.Keys) {
        if ($key -notlike '_*') { $export[$key] = $Summary[$key] }
    }
    $export | ConvertTo-Json -Depth 10 | Set-Content -Path $path -Encoding UTF8
}

function Complete-InstallSummary {
    param([hashtable]$Summary)

    $ns = $Summary.steps.native
    $cs = $Summary.steps.companion

    if (-not $Summary.dry_run) {
        # Derive readiness from step outcomes
        $ns.ready = $ns.built -and $ns.installed -and $ns.registered
        $cs.ready = $cs.built -and $cs.installed -and $cs.registered

        # rhino_bridge_functional depends ONLY on native readiness
        $Summary.rhino_bridge_functional = $ns.ready
        # full_stack_functional requires both
        $Summary.full_stack_functional = $ns.ready -and $cs.ready
    }

    # Derive exit code
    if ($Summary.dry_run) {
        # Dry-run: 0 unless prerequisite errors were found
        if ($Summary.errors.Count -gt 0) {
            $Summary.exit_code = 1
            $Summary.success = $false
        } else {
            $Summary.exit_code = 0
            $Summary.success = $true
        }
    } elseif ($Summary.rhino_bridge_functional) {
        $Summary.exit_code = 0
        $Summary.success = $true
    } elseif ($Summary.errors.Count -gt 0) {
        # Hard errors present (e.g., -RequireNative with missing prereqs)
        $Summary.exit_code = 1
        $Summary.success = $false
    } elseif ($Summary.steps.python.state -eq "completed") {
        # Partial: runtime exists but bridge not functional
        $Summary.exit_code = 2
        $Summary.success = $false
    } else {
        $Summary.exit_code = 1
        $Summary.success = $false
    }

    $Summary.timestamp = (Get-Date -Format "o")
    Write-InstallSummary $Summary

    if ($Json) {
        $export = @{}
        foreach ($key in $Summary.Keys) {
            if ($key -notlike '_*') { $export[$key] = $Summary[$key] }
        }
        $export | ConvertTo-Json -Depth 10
    }
}

# ============================================================================
# Shared Toolchain Detection
# ============================================================================
. (Join-Path $PSScriptRoot "scripts\detect-vs.ps1")

# ============================================================================
# Step Functions
# ============================================================================

function Step-DetectEnvironment {
    param([hashtable]$Context)

    Write-Host "[1/10] Detecting environment..." -ForegroundColor White

    $installDir = $Context.InstallDir
    $isSourceClone = Test-Path (Join-Path $installDir "src\Rook\Rook.csproj")
    $isRelease = Test-Path (Join-Path $installDir "plugin\Rook.rhp")

    if (-not $isSourceClone -and -not $isRelease) {
        Write-Host "      ERROR: Cannot determine install type." -ForegroundColor Red
        Write-Host "      Expected either src/Rook/Rook.csproj (source) or plugin/Rook.rhp (release)." -ForegroundColor Red
        return
    }

    if ($isSourceClone) {
        Write-Host "      Source clone detected (src/Rook/ found)" -ForegroundColor Gray
    } else {
        Write-Host "      Release download detected (plugin/ found)" -ForegroundColor Gray
    }

    $Context.IsSourceClone = $isSourceClone
    $Context.IsRelease = $isRelease
    $Context.RookMode = if ($isSourceClone) { "dev" } else { "release" }
    $Context.RuntimeRoot = if ($isSourceClone) { $installDir } else { Join-Path $env:LOCALAPPDATA "Rook" }
    $Context.RuntimeDataDir = if ($isSourceClone) { Join-Path $installDir "knowledge" } else { Join-Path $Context.RuntimeRoot "data" }
    $Context.RuntimeLogsDir = if ($isSourceClone) { Join-Path $installDir "logs" } else { Join-Path $Context.RuntimeRoot "logs" }
    $Context.McpServerDir = Join-Path $installDir "mcp_server"
    $Context.ConfigureUserScope = $isRelease -or $UserConfig

    if (-not $DryRun) {
        foreach ($dir in @($Context.RuntimeDataDir, $Context.RuntimeLogsDir)) {
            if (-not (Test-Path $dir)) {
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
            }
        }
    }

    Write-Host "      [OK] Mode: $($Context.RookMode)" -ForegroundColor Green
}

function Step-SetupPython {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[2/10] Setting up Python environment..." -ForegroundColor White

    if ($DryRun) {
        $Summary.steps.python.state = "planned"
        $Summary.planned_actions += "Create Python venv and install MCP server dependencies via uv"
        Write-Host "      [PLAN] Would create venv and install dependencies" -ForegroundColor Cyan
        return
    }

    # Check if uv is installed
    $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uvCmd) {
        Write-Host "      uv not found. Installing uv package manager..." -ForegroundColor Yellow
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
        $uvCmd = Get-Command uv -ErrorAction SilentlyContinue
        if (-not $uvCmd) {
            Add-InstallError -Summary $Summary -Code "python.not_found" `
                -Message "Failed to install uv package manager." `
                -Remediation "Install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
            $Summary.steps.python.state = "failed"
            return
        }
        Write-Host "      [OK] uv installed" -ForegroundColor Green
    } else {
        Write-Host "      [OK] uv is available" -ForegroundColor Green
    }

    $mcpDir = $Context.McpServerDir
    $venvDir = if ($Context.IsSourceClone) { Join-Path $mcpDir ".venv" } else { Join-Path $Context.RuntimeRoot "venv" }

    Push-Location $mcpDir
    try {
        Write-Host "      Creating virtual environment..."
        & uv venv $venvDir --python 3.12 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "      Python 3.12 not found, trying default..." -ForegroundColor Yellow
            & uv venv $venvDir 2>$null
            if ($LASTEXITCODE -ne 0) {
                Add-InstallError -Summary $Summary -Code "python.venv_failed" `
                    -Message "Failed to create Python virtual environment." `
                    -Remediation "Ensure network access (uv downloads Python automatically), or install Python 3.10+ manually."
                $Summary.steps.python.state = "failed"
                return
            }
        }

        $pythonPath = Join-Path $venvDir "Scripts\python.exe"

        Write-Host "      Installing dependencies..."
        & uv pip install -q -e $mcpDir --python $pythonPath 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "      Retrying with verbose output..." -ForegroundColor Yellow
            & uv pip install -e $mcpDir --python $pythonPath
            if ($LASTEXITCODE -ne 0) {
                Add-InstallError -Summary $Summary -Code "python.pip_failed" `
                    -Message "Failed to install MCP server dependencies." `
                    -Remediation "Check network access, then re-run install.ps1."
                $Summary.steps.python.state = "failed"
                return
            }
        }

        $Context.PythonPath = $pythonPath
        $Context.VenvDir = $venvDir
        $Summary.paths.python = $pythonPath
        $Summary.paths.venv = $venvDir
        $Summary.steps.python.state = "completed"
        Write-Host "      [OK] Python environment ready" -ForegroundColor Green
    } finally {
        Pop-Location
    }
}

function Step-SetupChirp {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[3/10] Setting up Chirp adapter..." -ForegroundColor White

    if ($SkipChirp) {
        $Summary.steps.chirp.state = "skipped"
        Add-InstallWarning -Summary $Summary -Code "chirp.skipped" `
            -Message "Chirp setup skipped via -SkipChirp flag." `
            -Remediation "Re-run without -SkipChirp to enable LLM-powered GH components."
        return
    }

    $chirpDir = Join-Path (Split-Path $Context.InstallDir -Parent) "Chirp"
    $Context.ChirpDir = $chirpDir

    if (-not (Test-Path (Join-Path $chirpDir "pyproject.toml"))) {
        $Summary.steps.chirp.state = "skipped"
        Add-InstallWarning -Summary $Summary -Code "chirp.not_found" `
            -Message "Chirp repo not found at $chirpDir." `
            -Remediation "git clone git@github.com:bringfire/Chirp.git $(Split-Path $Context.InstallDir -Parent)\Chirp"
        Write-Host "      [SKIP] Chirp not found at $chirpDir" -ForegroundColor Gray
        return
    }

    if ($DryRun) {
        $Summary.steps.chirp.state = "planned"
        $Summary.planned_actions += "Create Chirp venv and install dependencies at $chirpDir"
        Write-Host "      [PLAN] Would create Chirp venv and install dependencies" -ForegroundColor Cyan
        return
    }

    $chirpVenvDir = Join-Path $chirpDir ".venv"
    $chirpVenvPython = Join-Path $chirpVenvDir "Scripts\python.exe"

    if (Test-Path $chirpVenvPython) {
        Write-Host "      [OK] Chirp venv already exists" -ForegroundColor Green
        $Context.ChirpVenv = $chirpVenvDir
        $Summary.steps.chirp.state = "completed"
        return
    }

    if (-not $Context.PythonPath) {
        Add-InstallWarning -Summary $Summary -Code "chirp.venv_failed" `
            -Message "Cannot create Chirp venv: Python not available from previous step." `
            -Remediation "Fix Python setup first, then re-run install.ps1."
        $Summary.steps.chirp.state = "failed"
        return
    }

    Write-Host "      Creating Chirp virtual environment..."
    & $Context.PythonPath -m venv $chirpVenvDir 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Add-InstallWarning -Summary $Summary -Code "chirp.venv_failed" `
            -Message "Failed to create Chirp virtual environment." `
            -Remediation "Check Python installation, then re-run install.ps1."
        $Summary.steps.chirp.state = "failed"
        return
    }

    Write-Host "      Installing Chirp dependencies..."
    & $chirpVenvPython -m pip install -q -e $chirpDir 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      Retrying with verbose output..." -ForegroundColor Yellow
        & $chirpVenvPython -m pip install -e $chirpDir
        if ($LASTEXITCODE -ne 0) {
            Add-InstallWarning -Summary $Summary -Code "chirp.pip_failed" `
                -Message "Chirp dependency install failed. LLM-powered GH components unavailable." `
                -Remediation "Run 'pip install -e $chirpDir' manually from the Chirp venv."
            $Summary.steps.chirp.state = "failed"
            return
        }
    }

    $Context.ChirpVenv = $chirpVenvDir
    $Summary.steps.chirp.state = "completed"
    Write-Host "      [OK] Chirp ready at $chirpDir" -ForegroundColor Green
}

function Step-DetectToolchain {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[4/10] Detecting C++ toolchain..." -ForegroundColor White

    if ($SkipNative) {
        $Summary.steps.native.state = "skipped"
        $nativeSkippedMessage = "Native build skipped via -SkipNative flag."
        $nativeSkippedRemediation = "Re-run without -SkipNative to build the C++ plugin."
        Add-InstallWarning -Summary $Summary -Code "native.skipped" -Message $nativeSkippedMessage -Remediation $nativeSkippedRemediation
        Write-Host "      [SKIP] Native build skipped" -ForegroundColor Gray
        return
    }

    if ($Context.IsRelease) {
        Write-Host "      [SKIP] Release download - using pre-built plugins" -ForegroundColor Gray
        return
    }

    # Resolve override: param > env > auto-detect
    $overrideFromEnv = $env:ROOK_VC_TOOLS_VERSION
    $effectiveOverride = if ($VCToolsVersion) { $VCToolsVersion } elseif ($overrideFromEnv) { $overrideFromEnv } else { "" }

    $tc = Get-RookVisualStudioToolchain -OverrideVersion $effectiveOverride
    $Context.Toolchain = $tc

    # Forward toolchain warnings into the summary
    foreach ($w in $tc.Warnings) {
        Add-InstallWarning -Summary $Summary -Code $w.code -Message $w.message -Remediation $w.remediation
    }

    if (-not $tc.FoundVisualStudio) {
        $vsMissingMessage = 'Visual Studio 2022 not found.'
        $vsMissingRemediation = 'Install VS 2022 (Community, Professional, or Enterprise) with the C++ Desktop workload.'
        Add-InstallWarning -Summary $Summary -Code 'native.vs_not_found' -Message $vsMissingMessage -Remediation $vsMissingRemediation
        Write-Host "      [SKIP] VS 2022 not found" -ForegroundColor Yellow
        if ($RequireNative) {
            $vsRequiredMessage = 'C++ prerequisites missing and -RequireNative was set.'
            $vsRequiredRemediation = 'Install Visual Studio 2022 with C++ Desktop workload and MFC.'
            Add-InstallError -Summary $Summary -Code 'native.required_missing' -Message $vsRequiredMessage -Remediation $vsRequiredRemediation
            $Summary.steps.native.state = "failed"
        }
        return
    }

    if (-not $tc.FoundMfc) {
        $mfcMissingMessage = "VS 2022 ($($tc.Edition)) found but no MSVC toolset has MFC."
        $mfcMissingRemediation = 'In VS Installer > Individual Components, add "C++ MFC for latest v143 build tools (x86 and x64)".'
        Add-InstallWarning -Summary $Summary -Code "native.mfc_missing" -Message $mfcMissingMessage -Remediation $mfcMissingRemediation
        Write-Host "      [SKIP] MFC not found" -ForegroundColor Yellow
        if ($RequireNative) {
            $mfcRequiredMessage = 'MFC libraries missing and -RequireNative was set.'
            $mfcRequiredRemediation = 'Install MFC via VS Installer Individual Components.'
            Add-InstallError -Summary $Summary -Code 'native.required_missing' -Message $mfcRequiredMessage -Remediation $mfcRequiredRemediation
            $Summary.steps.native.state = "failed"
        }
        return
    }

    $Summary.toolchain.vs_edition = $tc.Edition
    $Summary.toolchain.vc_tools_version = $tc.VCToolsVersion
    $Summary.toolchain.native_build_script = "build_native.ps1"

    Write-Host "      [OK] VS 2022 $($tc.Edition), MSVC $($tc.VCToolsVersion), MFC found" -ForegroundColor Green
}

function Step-BuildNative {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[5/10] Building native plugin (C++)..." -ForegroundColor White

    if ($SkipNative -or $Summary.steps.native.state -eq "skipped" -or $Summary.steps.native.state -eq "failed") {
        if ($Summary.steps.native.state -ne "failed") {
            Write-Host "      [SKIP] Native build skipped" -ForegroundColor Gray
        }
        return
    }

    if ($DryRun) {
        $Summary.steps.native.state = "planned"
        if ($Context.IsRelease) {
            $Summary.planned_actions += "Use pre-built native plugin from release package if present"
        } else {
            $builtRelease = Join-Path $Context.InstallDir "src\RookNative\bin\Release\x64\RookNative.rhp"
            $builtDebug = Join-Path $Context.InstallDir "src\RookNative\bin\Debug\x64\RookNative.rhp"
            if (Test-Path $builtRelease) {
                $Summary.planned_actions += "Reuse existing RookNative Release build at $builtRelease"
            } elseif (Test-Path $builtDebug) {
                $Summary.planned_actions += "Reuse existing RookNative Debug build at $builtDebug"
            } elseif ($Context.Toolchain -and $Context.Toolchain.FoundMfc) {
                $Summary.planned_actions += "Build RookNative C++ plugin via build_native.ps1 (VS $($Context.Toolchain.Edition), MSVC $($Context.Toolchain.VCToolsVersion))"
            } else {
                $Summary.planned_actions += "Build RookNative C++ plugin after toolchain prerequisites are available"
            }
        }
        Write-Host "      [PLAN] Would prepare native plugin" -ForegroundColor Cyan
        return
    }

    if ($Context.IsRelease) {
        $releaseNative = Join-Path $Context.InstallDir "plugin\RookNative.rhp"
        if (Test-Path $releaseNative) {
            $Context.NativeBuildDir = Join-Path $Context.InstallDir "plugin"
            $Summary.steps.native.built = $true
            $Summary.steps.native.state = "completed"
            Write-Host "      [OK] Pre-built native plugin found" -ForegroundColor Green
        } else {
            Write-Host "      [SKIP] No pre-built RookNative in release package" -ForegroundColor Yellow
        }
        return
    }

    # Check if already built
    $builtRelease = Join-Path $Context.InstallDir "src\RookNative\bin\Release\x64\RookNative.rhp"
    $builtDebug = Join-Path $Context.InstallDir "src\RookNative\bin\Debug\x64\RookNative.rhp"

    if (Test-Path $builtRelease) {
        Write-Host "      [OK] RookNative already built (Release)" -ForegroundColor Green
        $Context.NativeBuildDir = Split-Path -Parent $builtRelease
        $Summary.steps.native.built = $true
        $Summary.steps.native.state = "completed"
        return
    }
    if (Test-Path $builtDebug) {
        Write-Host "      [OK] RookNative already built (Debug)" -ForegroundColor Green
        $Context.NativeBuildDir = Split-Path -Parent $builtDebug
        $Summary.steps.native.built = $true
        $Summary.steps.native.state = "completed"
        return
    }

    if (-not $Context.Toolchain -or -not $Context.Toolchain.FoundMfc) {
        Write-Host "      [SKIP] C++ toolchain not available" -ForegroundColor Yellow
        return
    }

    # Build via canonical build_native.ps1 (subprocess to isolate its exit calls)
    $Summary.steps.native.build_attempted = $true
    Write-Host "      Building RookNative from source (C++ with MFC)..."

    $buildScript = Join-Path $Context.InstallDir "build_native.ps1"
    if ($Context.Toolchain.VCToolsVersion) {
        & powershell -ExecutionPolicy Bypass -File "$buildScript" -Configuration Release -VCToolsVersion "$($Context.Toolchain.VCToolsVersion)" 2>&1 | ForEach-Object {
            $line = "$_"
            if ($line -match "BUILD FAILED|error MSB|error C[0-9]|fatal error") {
                Write-Host "      $line" -ForegroundColor Red
            }
        }
    } else {
        & powershell -ExecutionPolicy Bypass -File "$buildScript" -Configuration Release 2>&1 | ForEach-Object {
            $line = "$_"
            if ($line -match "BUILD FAILED|error MSB|error C[0-9]|fatal error") {
                Write-Host "      $line" -ForegroundColor Red
            }
        }
    }

    if (Test-Path $builtRelease) {
        $Context.NativeBuildDir = Split-Path -Parent $builtRelease
        $Summary.steps.native.built = $true
        $Summary.steps.native.state = "completed"
        Write-Host "      [OK] RookNative built successfully" -ForegroundColor Green
    } else {
        Add-InstallError -Summary $Summary -Code "native.build_failed" `
            -Message "RookNative build failed. MCP tools will NOT work without it." `
            -Remediation "Run 'powershell -File build_native.ps1 -Configuration Release' manually to see full output."
        $Summary.steps.native.state = "failed"
    }
}

function Step-BuildCompanion {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[6/10] Building companion plugin (C#)..." -ForegroundColor White

    if ($DryRun) {
        $Summary.steps.companion.state = "planned"
        if ($Context.IsRelease) {
            $Summary.planned_actions += "Use pre-built companion plugin from release package if present"
        } else {
            $built48 = Join-Path $Context.InstallDir "src\Rook\bin\Release\net48\Rook.rhp"
            $built70 = Join-Path $Context.InstallDir "src\Rook\bin\Release\net7.0\Rook.rhp"
            if (Test-Path $built70) {
                $Summary.planned_actions += "Reuse existing companion net7.0 build at $built70"
            } elseif (Test-Path $built48) {
                $Summary.planned_actions += "Reuse existing companion net48 build at $built48"
            } else {
                $Summary.planned_actions += "Build companion C# plugin via dotnet build src/Rook -c Release"
            }
        }
        Write-Host "      [PLAN] Would prepare companion plugin" -ForegroundColor Cyan
        return
    }

    if ($Context.IsRelease) {
        $releaseCompanion = Join-Path $Context.InstallDir "plugin\Rook.rhp"
        if (Test-Path $releaseCompanion) {
            $Context.CompanionBuildDir = Join-Path $Context.InstallDir "plugin"
            $Summary.steps.companion.built = $true
            $Summary.steps.companion.state = "completed"
            Write-Host "      [OK] Pre-built companion plugin found" -ForegroundColor Green
        }
        return
    }

    # Check if already built
    $built48 = Join-Path $Context.InstallDir "src\Rook\bin\Release\net48\Rook.rhp"
    $built70 = Join-Path $Context.InstallDir "src\Rook\bin\Release\net7.0\Rook.rhp"

    if (Test-Path $built70) {
        Write-Host "      [OK] Companion already built (net7.0)" -ForegroundColor Green
        $Context.CompanionBuildDir = Split-Path -Parent $built70
        $Summary.steps.companion.built = $true
        $Summary.steps.companion.state = "completed"
        return
    }
    if (Test-Path $built48) {
        Write-Host "      [OK] Companion already built (net48)" -ForegroundColor Green
        $Context.CompanionBuildDir = Split-Path -Parent $built48
        $Summary.steps.companion.built = $true
        $Summary.steps.companion.state = "completed"
        return
    }

    $dotnetCmd = Get-Command dotnet -ErrorAction SilentlyContinue
    if (-not $dotnetCmd) {
        $dotnetMissingMessage = 'dotnet SDK not found - cannot build companion plugin.'
        $dotnetMissingRemediation = 'Install .NET SDK: https://dotnet.microsoft.com/download'
        Add-InstallWarning -Summary $Summary -Code "companion.dotnet_not_found" -Message $dotnetMissingMessage -Remediation $dotnetMissingRemediation
        $Summary.steps.companion.state = "failed"
        return
    }

    $Summary.steps.companion.build_attempted = $true
    $buildTarget = Join-Path $Context.InstallDir "src\Rook"

    Write-Host "      Building from source (dotnet build src/Rook -c Release)..."
    & dotnet build $buildTarget -c Release --verbosity quiet 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "      Retrying with full output..." -ForegroundColor Yellow
        & dotnet build $buildTarget -c Release
        if ($LASTEXITCODE -ne 0) {
            Add-InstallError -Summary $Summary -Code "companion.build_failed" `
                -Message "Companion plugin build failed." `
                -Remediation "Run 'dotnet build src/Rook -c Release' manually to see full output."
            $Summary.steps.companion.state = "failed"
            return
        }
    }

    if (Test-Path $built70) {
        $Context.CompanionBuildDir = Split-Path -Parent $built70
        $Summary.steps.companion.built = $true
        $Summary.steps.companion.state = "completed"
        Write-Host "      [OK] Companion built successfully (net7.0)" -ForegroundColor Green
    } elseif (Test-Path $built48) {
        $Context.CompanionBuildDir = Split-Path -Parent $built48
        $Summary.steps.companion.built = $true
        $Summary.steps.companion.state = "completed"
        Write-Host "      [OK] Companion built successfully (net48)" -ForegroundColor Green
    } else {
        Add-InstallError -Summary $Summary -Code "companion.build_failed" `
            -Message "Build reported success but output not found." `
            -Remediation "Check dotnet build output manually."
        $Summary.steps.companion.state = "failed"
    }
}

function Step-DeployPlugins {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[7/10] Deploying plugins to Rhino..." -ForegroundColor White

    $rhinoPlugins = Join-Path $env:APPDATA "McNeel\Rhinoceros\8.0\Plug-ins"

    if (-not (Test-Path $rhinoPlugins)) {
        Add-InstallWarning -Summary $Summary -Code "deploy.rhino_dir_missing" `
            -Message "Rhino 8 plugins folder not found." `
            -Remediation "Install and run Rhino 8 once to create the plugins folder, then re-run install.ps1."
        Write-Host "      [WARN] Rhino 8 plugins folder not found" -ForegroundColor Yellow
        return
    }

    if (-not $Context.CompanionBuildDir -and -not $Context.NativeBuildDir) {
        Write-Host "      [SKIP] No plugin files available to deploy" -ForegroundColor Yellow
        return
    }

    $pluginDest = Join-Path $rhinoPlugins "RookNative"

    if ($DryRun) {
        $Summary.planned_actions += "Deploy plugins to $pluginDest"
        if ($Context.NativeBuildDir) { $Summary.planned_actions += "  - RookNative.rhp from $($Context.NativeBuildDir)" }
        if ($Context.CompanionBuildDir) { $Summary.planned_actions += "  - Rook.rhp + deps from $($Context.CompanionBuildDir)" }
        Write-Host "      [PLAN] Would deploy plugins to $pluginDest" -ForegroundColor Cyan
        return
    }

    if (-not (Test-Path $pluginDest)) {
        New-Item -ItemType Directory -Path $pluginDest -Force | Out-Null
    }
    $Context.PluginDest = $pluginDest
    $Summary.paths.plugin_dir = $pluginDest

    # Deploy companion files
    if ($Context.CompanionBuildDir) {
        try {
            Copy-Item (Join-Path $Context.CompanionBuildDir "*.rhp") $pluginDest -Force
            Copy-Item (Join-Path $Context.CompanionBuildDir "*.dll") $pluginDest -Force -ErrorAction SilentlyContinue
            Copy-Item (Join-Path $Context.CompanionBuildDir "*.rui") $pluginDest -Force -ErrorAction SilentlyContinue
            Copy-Item (Join-Path $Context.CompanionBuildDir "*.deps.json") $pluginDest -Force -ErrorAction SilentlyContinue
            Copy-Item (Join-Path $Context.CompanionBuildDir "*.runtimeconfig.json") $pluginDest -Force -ErrorAction SilentlyContinue
            $runtimesDir = Join-Path $Context.CompanionBuildDir "runtimes"
            if (Test-Path $runtimesDir) {
                Copy-Item $runtimesDir $pluginDest -Recurse -Force
            }
            $Summary.steps.companion.installed = $true
            Write-Host "      [OK] Companion plugin deployed" -ForegroundColor Green
        } catch {
            Add-InstallError -Summary $Summary -Code "companion.deploy_failed" `
                -Message "Failed to deploy companion plugin: $_" `
                -Remediation "Close Rhino if running, then re-run install.ps1."
        }
    }

    # Deploy native files
    if ($Context.NativeBuildDir) {
        try {
            Copy-Item (Join-Path $Context.NativeBuildDir "RookNative.rhp") $pluginDest -Force
            Copy-Item (Join-Path $Context.NativeBuildDir "RookNative.pdb") $pluginDest -Force -ErrorAction SilentlyContinue
            $Summary.steps.native.installed = $true
            Write-Host "      [OK] Native plugin deployed" -ForegroundColor Green
        } catch {
            Add-InstallError -Summary $Summary -Code "native.deploy_failed" `
                -Message "Failed to deploy native plugin: $_" `
                -Remediation "Close Rhino if running, then re-run install.ps1."
        }
    } elseif (-not $SkipNative) {
        Write-Host '      [WARN] RookNative (C++) not built - MCP tools will NOT work without it.' -ForegroundColor Yellow
    }
}

function Step-RegisterPlugins {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[8/10] Registering plugins with Rhino..." -ForegroundColor White

    $pluginDest = $Context.PluginDest
    if (-not $pluginDest) {
        Write-Host "      [SKIP] No deployed plugins to register" -ForegroundColor Gray
        return
    }

    if ($DryRun) {
        $Summary.planned_actions += "Register plugins with Rhino via registry scripts"
        Write-Host "      [PLAN] Would register plugins with Rhino" -ForegroundColor Cyan
        return
    }

    $hasNative = Test-Path (Join-Path $pluginDest "RookNative.rhp")
    $hasCompanion = Test-Path (Join-Path $pluginDest "Rook.rhp")

    if ($hasNative) {
        $suiteScript = Join-Path $Context.InstallDir "scripts\register-rooknative-suite.ps1"
        if (Test-Path $suiteScript) {
            try {
                $regArgs = @{ NativeRhpPath = Join-Path $pluginDest "RookNative.rhp" }
                if ($hasCompanion) {
                    $regArgs["CompanionRhpPath"] = Join-Path $pluginDest "Rook.rhp"
                }
                & $suiteScript @regArgs | Out-Null
                $Summary.steps.native.registered = $true
                $Summary.paths.native_rhp = Join-Path $pluginDest "RookNative.rhp"
                if ($hasCompanion) {
                    $Summary.steps.companion.registered = $true
                    $Summary.paths.companion_rhp = Join-Path $pluginDest "Rook.rhp"
                }
                Write-Host "      [OK] Plugin suite registered with Rhino" -ForegroundColor Green
            } catch {
                Add-InstallError -Summary $Summary -Code "native.register_failed" `
                    -Message "Plugin suite registration failed: $_" `
                    -Remediation "Run scripts\register-rooknative-suite.ps1 manually."
            }
        }
    } elseif ($hasCompanion) {
        $companionScript = Join-Path $Context.InstallDir "scripts\register-companion.ps1"
        if (Test-Path $companionScript) {
            try {
                & $companionScript -RhpPath (Join-Path $pluginDest "Rook.rhp") | Out-Null
                $Summary.steps.companion.registered = $true
                $Summary.paths.companion_rhp = Join-Path $pluginDest "Rook.rhp"
                Write-Host "      [OK] Companion plugin registered" -ForegroundColor Green
            } catch {
                Add-InstallError -Summary $Summary -Code "companion.register_failed" `
                    -Message "Companion registration failed: $_" `
                    -Remediation "Run scripts\register-companion.ps1 manually."
            }
        }
        Write-Host '      [WARN] RookNative (C++) missing - MCP tools will NOT function.' -ForegroundColor Yellow
        Write-Host '      The companion has no HTTP server; it requires RookNative.' -ForegroundColor Yellow
    }
}

function Step-WriteConfig {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[9/10] Writing configuration..." -ForegroundColor White

    if ($SkipConfig) {
        $Summary.steps.config.state = "skipped"
        Write-Host "      [SKIP] Config writing skipped via -SkipConfig flag" -ForegroundColor Gray
        return
    }

    if ($DryRun) {
        $Summary.steps.config.state = "planned"
        $Summary.planned_actions += 'Write MCP configuration files (.mcp.json, .claude.json, Codex TOML)'
        if ($Context.ConfigureUserScope) {
            $Summary.planned_actions += 'Write user-scope configs (~/.claude.json, Claude Desktop, Codex)'
        }
        Write-Host "      [PLAN] Would write MCP configuration files" -ForegroundColor Cyan
        return
    }

    if (-not $Context.PythonPath) {
        Add-InstallWarning -Summary $Summary -Code "config.repo_write_failed" `
            -Message "Cannot write configuration: Python not available." `
            -Remediation "Fix Python setup first, then re-run install.ps1."
        $Summary.steps.config.state = "failed"
        return
    }

    $configFailed = $false

    # Compute forward-slash paths for JSON/TOML
    $pythonFwd = $Context.PythonPath.Replace('\', '/')
    $cwdFwd = $Context.McpServerDir.Replace('\', '/')
    $installRootFwd = $Context.InstallDir.Replace('\', '/')
    $dataDirFwd = $Context.RuntimeDataDir.Replace('\', '/')
    $chirpHomeFwd = if ($Context.ChirpVenv) { $Context.ChirpDir.Replace('\', '/') } else { "" }

    # --- .env.example creation ---
    $envExample = Join-Path $Context.McpServerDir ".env.example"
    if (-not (Test-Path $envExample)) {
        $envContent = @(
            "# Rook MCP Server Configuration"
            "# Copy this file to .env and fill in your API key:"
            "#   cp .env.example .env"
            "#"
            "# Required for DSPy-powered intent resolution and knowledge evolution."
            "# Without this key, Rook still works but falls back to simpler lookup."
            "ANTHROPIC_API_KEY=your-key-here"
            ""
            "# Optional overrides (uncomment to customize):"
            "# ROOK_LOG_LEVEL=INFO"
            "# ROOK_BRIDGE_URL=http://localhost:9876"
            "# ROOK_PLANNER_MODEL=claude-sonnet-4-20250514"
            "# ROOK_WORKER_MODEL=claude-haiku-4-5-20251001"
            "# ROOK_MODEL_PROFILE=default"
            "# DSPY_MODEL=anthropic/claude-haiku-4-5-20251001"
        ) -join "`n"
        $envContent | Set-Content $envExample -Encoding UTF8 -NoNewline
        Write-Host "      [OK] Created .env.example" -ForegroundColor Green
    }

    $envFile = Join-Path $Context.McpServerDir ".env"
    if (Test-Path $envFile) {
        Write-Host "      [OK] .env file found" -ForegroundColor Green
    } else {
        Write-Host "      [NOTE] No .env file found. DSPy features will be disabled." -ForegroundColor Yellow
        Write-Host "      To enable: cp mcp_server/.env.example mcp_server/.env and add your API key." -ForegroundColor Yellow
    }

    # --- Project-level .mcp.json ---
    $projectConfigScript = @'
import json, sys; from pathlib import Path
out_path, python_cmd, cwd = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
install_root, data_dir, rook_mode = sys.argv[4], sys.argv[5], sys.argv[6]
chirp_home = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
env = {'PYTHONPATH': '', 'PYTHONHOME': '', 'ROOK_INSTALL_ROOT': install_root, 'ROOK_DATA_DIR': data_dir, 'ROOK_MODE': rook_mode}
if chirp_home: env['CHIRP_HOME'] = chirp_home
cfg = {'mcpServers': {'rook': {'type': 'stdio', 'command': python_cmd, 'args': ['-m', 'rook'], 'cwd': cwd, 'env': env}}}
out_path.write_text(json.dumps(cfg, indent=2), encoding='utf-8')
'@

    if ($Context.IsSourceClone) {
        $projectMcpJson = Join-Path $Context.InstallDir ".mcp.json"
        & $Context.PythonPath -c $projectConfigScript $projectMcpJson $pythonFwd $cwdFwd $installRootFwd $dataDirFwd $Context.RookMode $chirpHomeFwd 2>$null
        if ($LASTEXITCODE -eq 0) {
            $Summary.steps.config.repo_config_written = $true
            $Summary.paths.repo_mcp_config = $projectMcpJson
            Write-Host "      [OK] .mcp.json generated (repo-level)" -ForegroundColor Green
        } else {
            Add-InstallWarning -Summary $Summary -Code "config.repo_write_failed" `
                -Message "Failed to write repo-level .mcp.json." `
                -Remediation "Run install.ps1 again or create .mcp.json manually."
            $configFailed = $true
        }
    }

    # --- JSON merge helper (used for user-level configs) ---
    $mergeScript = @'
import json, shutil, sys
from pathlib import Path
config_path, python_path, cwd_path = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
install_root, data_dir, rook_mode = sys.argv[4], sys.argv[5], sys.argv[6]
chirp_home = sys.argv[7] if len(sys.argv) > 7 and sys.argv[7] else None
try:
    config = json.loads(config_path.read_text(encoding='utf-8')) if config_path.exists() else {}
    if config_path.exists(): shutil.copy2(config_path, config_path.with_suffix('.json.bak'))
    config.setdefault('mcpServers', {})
    env = {'PYTHONPATH': '', 'PYTHONHOME': '', 'ROOK_INSTALL_ROOT': install_root, 'ROOK_DATA_DIR': data_dir, 'ROOK_MODE': rook_mode}
    if chirp_home: env['CHIRP_HOME'] = chirp_home
    config['mcpServers']['rook'] = {'type': 'stdio', 'command': python_path, 'args': ['-m', 'rook'], 'cwd': cwd_path, 'env': env}
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    print('ok')
except Exception as e: print(f'error: {e}')
'@

    # --- User-level Claude Code config ---
    if ($Context.ConfigureUserScope) {
        $userMcpConfig = Join-Path $env:USERPROFILE ".claude.json"
        $Context.UserMcpConfig = $userMcpConfig
        $result = & $Context.PythonPath -c $mergeScript $userMcpConfig $pythonFwd $cwdFwd $installRootFwd $dataDirFwd $Context.RookMode $chirpHomeFwd 2>&1
        if ($result -match "ok") {
            $Summary.steps.config.user_config_written = $true
            $Summary.paths.user_mcp_config = $userMcpConfig
            Write-Host "      [OK] User-level Claude Code config updated (~/.claude.json)" -ForegroundColor Green
        } else {
            Add-InstallWarning -Summary $Summary -Code "config.user_write_failed" `
                -Message "User-level Claude config failed: $result" `
                -Remediation "Run install.ps1 -UserConfig again."
            $configFailed = $true
        }
    } else {
        Write-Host "      [SKIP] User-level Claude Code config not requested" -ForegroundColor Gray
    }

    # --- Claude Desktop config ---
    $desktopConfigDir = Join-Path $env:APPDATA "Claude"
    $desktopConfig = Join-Path $desktopConfigDir "claude_desktop_config.json"
    $Context.DesktopConfig = $desktopConfig

    if ($Context.ConfigureUserScope -and (Test-Path $desktopConfigDir)) {
        $desktopRunning = Get-Process -Name "Claude" -ErrorAction SilentlyContinue
        if ($desktopRunning) {
            Write-Host "      [WARN] Claude Desktop is running! It may overwrite config changes on exit." -ForegroundColor Yellow
            Write-Host "      Close Claude Desktop, re-run this installer, then reopen Desktop." -ForegroundColor Yellow
        }

        $result = & $Context.PythonPath -c $mergeScript $desktopConfig $pythonFwd $cwdFwd $installRootFwd $dataDirFwd $Context.RookMode $chirpHomeFwd 2>&1
        if ($result -match "ok") {
            $verifyScript = @'
import json, sys
from pathlib import Path
c = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('verified' if 'rook' in c.get('mcpServers', {}) else 'missing')
'@
            $verify = & $Context.PythonPath -c $verifyScript $desktopConfig 2>&1
            if ($verify -match "verified") {
                if ($desktopRunning) {
                    Write-Host "      [OK] Claude Desktop config written (but Desktop may overwrite it!)" -ForegroundColor Yellow
                } else {
                    Write-Host "      [OK] Claude Desktop configured" -ForegroundColor Green
                }
            } else {
                Write-Host "      [WARN] Claude Desktop config written but rook entry not found on re-read." -ForegroundColor Yellow
                Write-Host "      Claude Desktop may have overwritten it. Close Desktop and re-run." -ForegroundColor Yellow
                $configFailed = $true
            }
        } else {
            Write-Host "      [WARN] Claude Desktop config failed: $result" -ForegroundColor Yellow
            $configFailed = $true
        }

        if (-not ($result -match "ok") -or ($verify -match "missing") -or $desktopRunning) {
            Write-Host ""
            Write-Host "      To configure Claude Desktop manually:" -ForegroundColor Cyan
            Write-Host "        1. Quit Claude Desktop completely" -ForegroundColor Gray
            Write-Host "        2. Open: $desktopConfig" -ForegroundColor Gray
            Write-Host "        3. Add this to the mcpServers object:" -ForegroundColor Gray
            $desktopManualBlock = @(
                '           "rook": {'
                '             "type": "stdio",'
                ('             "command": "{0}",' -f $pythonFwd)
                '             "args": ["-m", "rook"],'
                ('             "cwd": "{0}",' -f $cwdFwd)
                '             "env": {'
                '               "PYTHONPATH": "",'
                '               "PYTHONHOME": "",'
                ('               "ROOK_INSTALL_ROOT": "{0}",' -f $installRootFwd)
                ('               "ROOK_DATA_DIR": "{0}",' -f $dataDirFwd)
                ('               "ROOK_MODE": "{0}"' -f $Context.RookMode)
                '             }'
                '           }'
            )
            foreach ($line in $desktopManualBlock) {
                Write-Host $line -ForegroundColor Gray
            }
            Write-Host "        4. Restart Claude Desktop" -ForegroundColor Gray
        }
    } elseif ($Context.ConfigureUserScope) {
        Write-Host "      [SKIP] Claude Desktop not found" -ForegroundColor Gray
    } else {
        Write-Host "      [SKIP] User-level Claude Desktop config not requested" -ForegroundColor Gray
    }

    # --- OpenAI Codex CLI config ---
    $codexConfigDir = Join-Path $env:USERPROFILE ".codex"
    $codexOnPath = Get-Command codex -ErrorAction SilentlyContinue

    if ($Context.IsSourceClone -or (Test-Path $codexConfigDir) -or $codexOnPath -or $Context.ConfigureUserScope) {
        Write-Host ""
        Write-Host "      Codex CLI detected - configuring..." -ForegroundColor White

        $codexTomlScript = @'
import re, sys
from pathlib import Path
python_path = sys.argv[1].replace('\\', '/').replace('"', '\\"')
cwd_path = sys.argv[2].replace('\\', '/').replace('"', '\\"')
install_root = sys.argv[3].replace('\\', '/').replace('"', '\\"')
data_dir = sys.argv[4].replace('\\', '/').replace('"', '\\"')
rook_mode = sys.argv[5]
out_path = sys.argv[6]
lines = [
    '# Rook MCP Server configuration for OpenAI Codex CLI',
    '# Auto-generated by Rook installer',
    '',
    '[mcp_servers.rook]',
    f'command = "{python_path}"',
    'args = ["-m", "rook"]',
    f'cwd = "{cwd_path}"',
    'startup_timeout_sec = 30',
    'tool_timeout_sec = 120',
    '',
    '[mcp_servers.rook.env]',
    'PYTHONPATH = ""',
    'PYTHONHOME = ""',
    f'ROOK_INSTALL_ROOT = "{install_root}"',
    f'ROOK_DATA_DIR = "{data_dir}"',
    f'ROOK_MODE = "{rook_mode}"',
    '',
]
content = '\n'.join(lines)
out = Path(out_path)
out.parent.mkdir(parents=True, exist_ok=True)
if out.exists():
    existing = out.read_text(encoding='utf-8')
    if '[mcp_servers.rook]' in existing:
        content = re.sub(r'\[mcp_servers\.rook\].*?(?=\n\[(?!mcp_servers\.rook[.\]])|$)', content.strip(), existing, flags=re.DOTALL)
    else:
        content = existing.rstrip() + '\n\n' + content
out.write_text(content, encoding='utf-8')
print('ok')
'@

        if ($Context.IsSourceClone) {
            $projectCodexDir = Join-Path $Context.InstallDir ".codex"
            if (-not (Test-Path $projectCodexDir)) {
                New-Item -ItemType Directory -Path $projectCodexDir -Force | Out-Null
            }
            $projectCodexConfig = Join-Path $projectCodexDir "config.toml"
            $result = & $Context.PythonPath -c $codexTomlScript $pythonFwd $cwdFwd $installRootFwd $dataDirFwd $Context.RookMode $projectCodexConfig 2>&1
            if ($result -match "ok") {
                Write-Host "      [OK] .codex/config.toml generated (repo-level)" -ForegroundColor Green
            } else {
                Write-Host "      [WARN] Project-level Codex config failed: $result" -ForegroundColor Yellow
                $configFailed = $true
            }
        }

        if ($Context.ConfigureUserScope) {
            $userCodexConfig = Join-Path $codexConfigDir "config.toml"
            $result = & $Context.PythonPath -c $codexTomlScript $pythonFwd $cwdFwd $installRootFwd $dataDirFwd $Context.RookMode $userCodexConfig 2>&1
            if ($result -match "ok") {
                Write-Host "      [OK] User-level Codex config updated (~/.codex/config.toml)" -ForegroundColor Green
            } else {
                Write-Host "      [WARN] User-level Codex config failed: $result" -ForegroundColor Yellow
                $configFailed = $true
            }
        } else {
            Write-Host "      [SKIP] User-level Codex config not requested" -ForegroundColor Gray
        }
    } else {
        Write-Host "      [SKIP] Codex CLI not detected" -ForegroundColor Gray
    }

    # --- User-level skills/agents (release installs, optional for dev) ---
    $claudeSkillsSource = Join-Path $Context.InstallDir ".claude\skills"
    $claudeAgentsSource = Join-Path $Context.InstallDir ".claude\agents"
    $codexSkillsSource = Join-Path $Context.InstallDir ".agents\skills"
    if (($Context.IsRelease -or $UserConfig) -and ((Test-Path $claudeSkillsSource) -or (Test-Path $claudeAgentsSource) -or (Test-Path $codexSkillsSource))) {
        $claudeSkillsDest = Join-Path $env:USERPROFILE ".claude\skills"
        $claudeAgentsDest = Join-Path $env:USERPROFILE ".claude\agents"
        $codexSkillsDest = Join-Path $env:USERPROFILE ".codex\skills"

        if (Test-Path $claudeSkillsSource) {
            New-Item -ItemType Directory -Path $claudeSkillsDest -Force | Out-Null
            Copy-Item (Join-Path $claudeSkillsSource "*") $claudeSkillsDest -Recurse -Force
        }
        if (Test-Path $claudeAgentsSource) {
            New-Item -ItemType Directory -Path $claudeAgentsDest -Force | Out-Null
            Copy-Item (Join-Path $claudeAgentsSource "*") $claudeAgentsDest -Recurse -Force
        }
        if (Test-Path $codexSkillsSource) {
            New-Item -ItemType Directory -Path $codexSkillsDest -Force | Out-Null
            Copy-Item (Join-Path $codexSkillsSource "*") $codexSkillsDest -Recurse -Force
        }
        Write-Host "      [OK] User-level Claude/Codex skills and Claude agents installed" -ForegroundColor Green
    } elseif ((Test-Path $claudeSkillsSource) -or (Test-Path $claudeAgentsSource) -or (Test-Path $codexSkillsSource)) {
        Write-Host "      [SKIP] Repo skill/agent payload retained (user-level install not requested)" -ForegroundColor Gray
    }

    $Summary.steps.config.state = if ($configFailed) { "failed" } else { "completed" }
}

function Step-Verify {
    param([hashtable]$Summary, [hashtable]$Context)

    Write-Host ""
    Write-Host "[10/10] Verifying installation..." -ForegroundColor White

    if ($NoVerify) {
        $Summary.steps.verification.state = "skipped"
        Write-Host "      [SKIP] Verification skipped via -NoVerify flag" -ForegroundColor Gray
        return
    }

    if ($DryRun) {
        $Summary.steps.verification.state = "planned"
        $Summary.planned_actions += "Verify installation (module load, knowledge store, plugins, configs)"
        Write-Host "      [PLAN] Would verify installation" -ForegroundColor Cyan
        return
    }

    # ---- Filesystem verification ----
    $pluginDest = $Context.PluginDest

    if ($Summary.steps.native.installed) {
        $nativeRhp = Join-Path $pluginDest "RookNative.rhp"
        if ((Test-Path $nativeRhp) -and (Get-Item $nativeRhp).Length -gt 0) {
            Write-Host "      [OK] RookNative.rhp exists and is non-zero" -ForegroundColor Green
        } else {
            Add-InstallWarning -Summary $Summary -Code "verify.file_missing" `
                -Message "RookNative.rhp missing or empty at $pluginDest." `
                -Remediation "Re-run install.ps1 to rebuild and deploy."
        }
    }

    if ($Summary.steps.companion.installed) {
        $companionRhp = Join-Path $pluginDest "Rook.rhp"
        if ((Test-Path $companionRhp) -and (Get-Item $companionRhp).Length -gt 0) {
            Write-Host "      [OK] Rook.rhp exists and is non-zero" -ForegroundColor Green
        } else {
            Add-InstallWarning -Summary $Summary -Code "verify.file_missing" `
                -Message "Rook.rhp missing or empty at $pluginDest." `
                -Remediation "Re-run install.ps1 to rebuild and deploy."
        }
    }

    # ---- Registry verification ----
    $NativeGuid    = "a38e0e8f-e06e-40d2-a6bd-7edbc2cb1906"
    $CompanionGuid = "b7e4a8c9-1f62-4c7e-9a2b-5d4e8f1c3a7b"

    if ($Summary.steps.native.registered) {
        $nativeRegKey = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$NativeGuid\PlugIn"
        $nativeReg = Get-ItemProperty -Path $nativeRegKey -Name "FileName" -ErrorAction SilentlyContinue
        if ($nativeReg -and $nativeReg.FileName -and (Test-Path $nativeReg.FileName)) {
            Write-Host "      [OK] Native registry key points to existing file" -ForegroundColor Green
        } else {
            $got = if ($nativeReg -and $nativeReg.FileName) { $nativeReg.FileName } else { "(not set)" }
            $nativeRegistryMessage = "Native plugin registry FileName is '{0}' - file does not exist." -f $got
            $registryRemediation = "Run scripts\register-rooknative-suite.ps1 to fix registration."
            Add-InstallWarning -Summary $Summary -Code "verify.registry_mismatch" -Message $nativeRegistryMessage -Remediation $registryRemediation
        }
    }

    if ($Summary.steps.companion.registered) {
        $companionRegKey = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$CompanionGuid\PlugIn"
        $companionReg = Get-ItemProperty -Path $companionRegKey -Name "FileName" -ErrorAction SilentlyContinue
        if ($companionReg -and $companionReg.FileName -and (Test-Path $companionReg.FileName)) {
            Write-Host "      [OK] Companion registry key points to existing file" -ForegroundColor Green
        } else {
            $got = if ($companionReg -and $companionReg.FileName) { $companionReg.FileName } else { "(not set)" }
            $companionRegistryMessage = "Companion plugin registry FileName is '{0}' - file does not exist." -f $got
            $registryRemediation = "Run scripts\register-rooknative-suite.ps1 to fix registration."
            Add-InstallWarning -Summary $Summary -Code "verify.registry_mismatch" -Message $companionRegistryMessage -Remediation $registryRemediation
        }
    }

    # ---- Config verification (parse JSON, check command/cwd paths) ----
    if ($Summary.steps.config.state -ne "skipped") {
        function Test-McpConfig {
            param([string]$Path, [string]$Label)
            if (-not (Test-Path $Path)) {
                Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                    -Message "$Label config missing at $Path." `
                    -Remediation "Re-run install.ps1 to regenerate."
                return
            }
            try {
                $cfg = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json
            } catch {
                Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                    -Message "$Label config at $Path is not valid JSON: $_" `
                    -Remediation "Delete the file and re-run install.ps1."
                return
            }
            $rook = $cfg.mcpServers.rook
            if (-not $rook) {
                Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                    -Message "$Label config has no mcpServers.rook entry." `
                    -Remediation "Re-run install.ps1 to regenerate."
                return
            }
            $cmdPath = $rook.command
            if ($cmdPath) {
                # Normalize forward slashes back to backslashes for Test-Path
                $cmdPathNative = $cmdPath.Replace('/', '\')
                if (-not (Test-Path $cmdPathNative)) {
                    Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                        -Message "$Label config command path does not exist: $cmdPath" `
                        -Remediation "Re-run install.ps1 or update the path in $Path."
                    return
                }
            }
            $cwdPath = $rook.cwd
            if ($cwdPath) {
                $cwdPathNative = $cwdPath.Replace('/', '\')
                if (-not (Test-Path $cwdPathNative)) {
                    Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                        -Message "$Label config cwd does not exist: $cwdPath" `
                        -Remediation "Re-run install.ps1 or update the cwd in $Path."
                    return
                }
            }
            Write-Host "      [OK] $Label config valid (JSON parses, command and cwd exist)" -ForegroundColor Green
        }

        if ($Context.IsSourceClone) {
            $mcpJsonPath = Join-Path $Context.InstallDir ".mcp.json"
            Test-McpConfig -Path $mcpJsonPath -Label "Repo .mcp.json"
        }

        if ($Summary.steps.config.user_config_written) {
            if ($Context.UserMcpConfig) {
                Test-McpConfig -Path $Context.UserMcpConfig -Label "User Claude Code"
            }
        }

        if ($Context.DesktopConfig) {
            $desktopConfigDir = Join-Path $env:APPDATA "Claude"
            if ($Context.ConfigureUserScope -and (Test-Path $desktopConfigDir)) {
                Test-McpConfig -Path $Context.DesktopConfig -Label "Claude Desktop"
            }
        }

        # Codex TOML: validate section exists and command/cwd paths are real
        function Get-TomlQuotedValue {
            param([string[]]$Lines, [string]$Key)

            $line = $Lines | Where-Object { $_ -match "^\s*$Key\s*=" } | Select-Object -First 1
            if (-not $line) { return $null }

            $parts = $line.Split('=', 2)
            if ($parts.Count -lt 2) { return $null }

            $value = $parts[1].Trim()
            if ($value.StartsWith('"') -and $value.EndsWith('"') -and $value.Length -ge 2) {
                return $value.Substring(1, $value.Length - 2)
            }

            return $null
        }

        function Test-CodexToml {
            param([string]$Path, [string]$Label)
            if (-not (Test-Path $Path)) {
                Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                    -Message "$Label config missing at $Path." `
                    -Remediation "Re-run install.ps1 to regenerate."
                return
            }
            $content = Get-Content -Path $Path -Raw -Encoding UTF8
            if (-not $content.Contains('[mcp_servers.rook]')) {
                Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                    -Message "$Label config missing [mcp_servers.rook] section." `
                    -Remediation "Re-run install.ps1 to regenerate."
                return
            }
            $lines = $content -split "\r?\n"

            $commandValue = Get-TomlQuotedValue -Lines $lines -Key "command"
            if ($commandValue) {
                $cmdPath = $commandValue.Replace('/', '\')
                if (-not (Test-Path $cmdPath)) {
                    Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                        -Message "$Label config command path does not exist: $commandValue" `
                        -Remediation "Re-run install.ps1 or update the path in $Path."
                    return
                }
            }

            $cwdValue = Get-TomlQuotedValue -Lines $lines -Key "cwd"
            if ($cwdValue) {
                $cwdPath = $cwdValue.Replace('/', '\')
                if (-not (Test-Path $cwdPath)) {
                    Add-InstallWarning -Summary $Summary -Code "verify.config_invalid" `
                        -Message "$Label config cwd does not exist: $cwdValue" `
                        -Remediation "Re-run install.ps1 or update the cwd in $Path."
                    return
                }
            }
            Write-Host "      [OK] $Label config valid (rook section, command and cwd exist)" -ForegroundColor Green
        }

        if ($Context.IsSourceClone) {
            $repoCodexConfig = Join-Path $Context.InstallDir ".codex\config.toml"
            Test-CodexToml -Path $repoCodexConfig -Label "Repo Codex"
        }

        if ($Context.ConfigureUserScope) {
            $userCodexConfig = Join-Path $env:USERPROFILE ".codex\config.toml"
            Test-CodexToml -Path $userCodexConfig -Label "User Codex"
        }
    } else {
        Write-Host "      [SKIP] Config verification skipped because config writing was skipped" -ForegroundColor Gray
    }

    $Summary.steps.verification.state = "completed"
}

# ============================================================================
# Preflight Checks
# ============================================================================

if ($RequireNative -and $SkipNative) {
    Write-Error "Cannot use -RequireNative and -SkipNative together."
    exit 1
}

$rhinoProc = Get-Process -Name "Rhinoceros" -ErrorAction SilentlyContinue
if ($rhinoProc -and $RequireNative) {
    Write-Error "Rhino is running. Close Rhino before building - DLL locks will cause failures."
    exit 1
}

$InstallDir = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host "                          Rook Installer" -ForegroundColor Cyan
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# Main Pipeline
# ============================================================================

$Context = @{ InstallDir = $InstallDir }

# Step 1: Detect environment (populates Context - no Summary yet)
Step-DetectEnvironment -Context $Context
if (-not $Context.RookMode) {
    # Detection failed — error already printed
    exit 1
}

# Initialize summary now that we know the mode
$summaryFile = if ($SummaryPath) { $SummaryPath } else { Join-Path $InstallDir "install-summary.json" }
$Summary = New-InstallSummary -Mode $Context.RookMode -IsDryRun:$DryRun -SummaryFilePath $summaryFile

# Record Rhino warning in summary if detected earlier
if ($rhinoProc) {
    Add-InstallWarning -Summary $Summary -Code "rhino.running" `
        -Message "Rhino is running. Plugin deploy/registration may fail due to DLL locks." `
        -Remediation "Close Rhino before re-running install.ps1."
}

Write-InstallSummary $Summary

# Steps 2-10: each updates Summary in place, summary written after each step
Step-SetupPython -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-SetupChirp -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-DetectToolchain -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-BuildNative -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-BuildCompanion -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-DeployPlugins -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-RegisterPlugins -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-WriteConfig -Summary $Summary -Context $Context
Write-InstallSummary $Summary

Step-Verify -Summary $Summary -Context $Context
Write-InstallSummary $Summary

# ============================================================================
# Compute Next Actions
# ============================================================================

$ns = $Summary.steps.native
$cs = $Summary.steps.companion

if (-not $Context.Toolchain -or -not $Context.Toolchain.FoundVisualStudio) {
    if (-not $SkipNative -and $Context.IsSourceClone) {
        $Summary.next_actions += "Install VS 2022 with C++ Desktop workload and MFC"
    }
} elseif ($Context.Toolchain -and -not $Context.Toolchain.FoundMfc) {
    $Summary.next_actions += "VS Installer > Individual Components > C++ MFC for latest v143 build tools"
}

if ($ns.state -eq "failed" -and $ns.build_attempted) {
    $Summary.next_actions += "Fix native build errors, then re-run install.ps1"
}

if ($cs.state -eq "failed") {
    $Summary.next_actions += "Install .NET SDK or run dotnet build src/Rook -c Release"
}

if ($ns.built -and $ns.installed -and -not $ns.registered) {
    $Summary.next_actions += "Run scripts\register-rooknative-suite.ps1 manually"
}

if ($rhinoProc) {
    $Summary.next_actions += "Close Rhino, then re-run install.ps1"
}

if ($Summary.steps.config.state -eq "failed") {
    $Summary.next_actions += "Run install.ps1 -UserConfig"
}

if ($Summary.next_actions.Count -eq 0 -and -not $DryRun) {
    $Summary.next_actions += "Start Rhino 8"
    $Summary.next_actions += "Run /mcp in Claude Code to verify"
}

# ============================================================================
# Finalize Summary and Exit
# ============================================================================

Complete-InstallSummary $Summary

Write-Host ""
Write-Host "============================================================================" -ForegroundColor Cyan
if ($DryRun) {
    Write-Host "                     Dry Run Complete" -ForegroundColor Cyan
} elseif ($Summary.exit_code -eq 0) {
    Write-Host "                    Installation Complete!" -ForegroundColor Green
} elseif ($Summary.exit_code -eq 2) {
    Write-Host "              Installation Partial (exit code 2)" -ForegroundColor Yellow
} else {
    Write-Host "                  Installation Failed (exit code 1)" -ForegroundColor Red
}
Write-Host "============================================================================" -ForegroundColor Cyan
Write-Host ""

if ($DryRun) {
    Write-Host "  Planned actions:" -ForegroundColor White
    foreach ($action in $Summary.planned_actions) {
        Write-Host "    - $action"
    }
    Write-Host ""
} else {
    Write-Host "  NEXT STEPS:" -ForegroundColor White
    Write-Host ""
    foreach ($action in $Summary.next_actions) {
        Write-Host "    - $action"
    }
    Write-Host ""

    $envFile = Join-Path $Context.McpServerDir ".env"
    if (-not (Test-Path $envFile)) {
        Write-Host "  For DSPy features: cp mcp_server/.env.example mcp_server/.env" -ForegroundColor Yellow
        Write-Host "  Then add your ANTHROPIC_API_KEY" -ForegroundColor Yellow
        Write-Host ""
    }
}

Write-Host "  Summary: $($Summary._summary_path)" -ForegroundColor Gray
Write-Host "  Install directory: $InstallDir"
if ($Context.PluginDest) {
    Write-Host "  Plugin location:   $($Context.PluginDest)"
}
Write-Host ""

exit $Summary.exit_code
