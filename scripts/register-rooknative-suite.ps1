# register-rooknative-suite.ps1
#
# Registers the full RookNative plugin suite with Rhino 8:
#   - RookNative.rhp as the public native plugin (startup-loaded)
#   - Rook.rhp as the managed companion (when-needed)
#
# This avoids relying on transient PlugInManager state. Rhino sees the native
# plugin at startup every session, and native then auto-loads the companion.
#
# Usage:
#   .\scripts\register-rooknative-suite.ps1
#   .\scripts\register-rooknative-suite.ps1 -NativeRhpPath "C:\...\RookNative.rhp"
#   .\scripts\register-rooknative-suite.ps1 -CompanionRhpPath "C:\...\Rook.rhp"
#   .\scripts\register-rooknative-suite.ps1 -Unregister

[CmdletBinding()]
param(
    [string]$NativeRhpPath,
    [string]$CompanionRhpPath,
    [switch]$NativeOnlyPreserveCompanion,
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'

$NativeGuid    = 'a38e0e8f-e06e-40d2-a6bd-7edbc2cb1906'
$CompanionGuid = 'b7e4a8c9-1f62-4c7e-9a2b-5d4e8f1c3a7b'
$NativeRegBase = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$NativeGuid"
$ScriptDir     = Split-Path -Parent $PSCommandPath
$RepoRoot      = Split-Path -Parent $ScriptDir

function Resolve-NativeRhpPath {
    param([string]$ExplicitPath)

    if ($ExplicitPath) {
        if (-not (Test-Path $ExplicitPath)) {
            throw "File not found: $ExplicitPath"
        }
        return (Resolve-Path $ExplicitPath).Path
    }

    $rhinoPluginDir = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.rhp'
    $candidates = @(
        $rhinoPluginDir,
        (Join-Path $RepoRoot 'src\RookNative\bin\Debug\x64\RookNative.rhp'),
        (Join-Path $RepoRoot 'src\RookNative\bin\Release\x64\RookNative.rhp')
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return (Resolve-Path $candidate).Path
        }
    }

    throw "Could not find RookNative.rhp. Pass -NativeRhpPath explicitly."
}

function Write-NativeRegistration {
    param([string]$RhpPath)

    if (-not (Test-Path $NativeRegBase)) {
        New-Item -Path $NativeRegBase -Force | Out-Null
    }

    Set-ItemProperty -Path $NativeRegBase -Name 'Name'         -Value 'RookNative' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'EnglishName'  -Value 'RookNative' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'Organization' -Value 'Bringfire' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'Address'      -Value '' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'Country'      -Value '' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'Phone'        -Value '' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'EMail'        -Value '' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'WebSite'      -Value 'https://github.com/bringfire/Rhino_AI' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'UpdateURL'    -Value 'https://github.com/bringfire/Rhino_AI/releases' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'Fax'          -Value '' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'Description'  -Value 'RookNative - High-performance Rhino bridge for Claude Code' -Type String
    Set-ItemProperty -Path $NativeRegBase -Name 'RegPath'      -Value "\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$NativeGuid" -Type String

    # Startup load is the key difference from our ad hoc manual loading.
    Set-ItemProperty -Path $NativeRegBase -Name 'Type'             -Value 0x10 -Type DWord
    Set-ItemProperty -Path $NativeRegBase -Name 'IsDotNETPlugIn'   -Value 0 -Type DWord
    Set-ItemProperty -Path $NativeRegBase -Name 'LoadMode'         -Value 1 -Type DWord
    Set-ItemProperty -Path $NativeRegBase -Name 'AddToHelpMenu'    -Value 0 -Type DWord
    Set-ItemProperty -Path $NativeRegBase -Name 'DirectoryInstall' -Value 0 -Type DWord

    $plugInKey = "$NativeRegBase\PlugIn"
    if (-not (Test-Path $plugInKey)) {
        New-Item -Path $plugInKey -Force | Out-Null
    }
    Set-ItemProperty -Path $plugInKey -Name 'FileName' -Value $RhpPath -Type String

    $cmdKey = "$NativeRegBase\CommandList"
    if (-not (Test-Path $cmdKey)) {
        New-Item -Path $cmdKey -Force | Out-Null
    }
}

function Verify-NativeRegistration {
    param([string]$ExpectedPath)

    $errors = @()
    $root = Get-ItemProperty -Path $NativeRegBase -ErrorAction SilentlyContinue
    $plugIn = Get-ItemProperty -Path "$NativeRegBase\PlugIn" -ErrorAction SilentlyContinue

    if (-not $root) {
        $errors += "Native root key not found at $NativeRegBase"
    } else {
        if ($root.Name -ne 'RookNative')      { $errors += "Name: expected 'RookNative', got '$($root.Name)'" }
        if ($root.Type -ne 0x10)              { $errors += "Type: expected 16, got $($root.Type)" }
        if ($root.IsDotNETPlugIn -ne 0)       { $errors += "IsDotNETPlugIn: expected 0, got $($root.IsDotNETPlugIn)" }
        if ($root.LoadMode -ne 1)             { $errors += "LoadMode: expected 1, got $($root.LoadMode)" }
    }

    if (-not $plugIn -or $plugIn.FileName -ne $ExpectedPath) {
        $got = '(null)'
        if ($plugIn) { $got = $plugIn.FileName }
        $errors += "PlugIn\\FileName: expected '$ExpectedPath', got '$got'"
    }

    if (-not (Test-Path "$NativeRegBase\CommandList")) {
        $errors += 'CommandList subkey missing'
    }

    if ($errors.Count -gt 0) {
        throw ("Native registration verification failed:`n  " + ($errors -join "`n  "))
    }
}

function Resolve-PreservedCompanionRhpPath {
    $companionPluginKey = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$CompanionGuid\PlugIn"
    $companion = Get-ItemProperty -Path $companionPluginKey -Name 'FileName' -ErrorAction SilentlyContinue
    if (-not $companion -or -not $companion.FileName) {
        throw "Native-only preserve-companion registration requires an existing companion registration. Run the default full deploy once first."
    }

    $path = $companion.FileName
    if (-not (Test-Path $path)) {
        throw "Existing companion registration points to a missing file: $path"
    }

    return (Resolve-Path $path).Path
}

if ($NativeOnlyPreserveCompanion -and $CompanionRhpPath) {
    throw "-NativeOnlyPreserveCompanion cannot be combined with -CompanionRhpPath."
}

if ($NativeOnlyPreserveCompanion -and $Unregister) {
    throw "-NativeOnlyPreserveCompanion cannot be combined with -Unregister."
}

if ($Unregister) {
    if (Test-Path $NativeRegBase) {
        Remove-Item -Path $NativeRegBase -Recurse -Force
        Write-Host "Removed native registration at $NativeRegBase"
    } else {
        Write-Host 'Native plugin not registered -- nothing to remove.'
    }

    $companionScript = Join-Path $ScriptDir 'register-companion.ps1'
    & $companionScript -Unregister
    exit 0
}

$resolvedNative = Resolve-NativeRhpPath -ExplicitPath $NativeRhpPath
$preservedCompanionPath = $null
if ($NativeOnlyPreserveCompanion) {
    $preservedCompanionPath = Resolve-PreservedCompanionRhpPath
}

Write-Host "Registering native plugin: $resolvedNative"

Write-NativeRegistration -RhpPath $resolvedNative
Verify-NativeRegistration -ExpectedPath $resolvedNative

if ($NativeOnlyPreserveCompanion) {
    $companionAfter = Resolve-PreservedCompanionRhpPath
    if ($companionAfter -ne $preservedCompanionPath) {
        throw "Native-only preserve-companion registration changed companion registration unexpectedly."
    }

    Write-Host ''
    Write-Host 'Native-only preserve-companion registration verified.'
    Write-Host "  Native GUID:    $NativeGuid"
    Write-Host "  Companion GUID: $CompanionGuid"
    Write-Host "  Native path:    $resolvedNative"
    Write-Host "  Companion path: $preservedCompanionPath"
    Write-Host ''
    Write-Host 'Start Rhino now -- RookNative should load automatically each session.'
    exit 0
}

$nativeDir = Split-Path -Parent $resolvedNative
if (-not $CompanionRhpPath) {
    $candidateCompanions = @(
        (Join-Path $nativeDir 'net7.0\Rook.rhp'),
        (Join-Path $nativeDir 'Rook.rhp')
    )

    foreach ($candidateCompanion in $candidateCompanions) {
        if (Test-Path $candidateCompanion) {
            $CompanionRhpPath = (Resolve-Path $candidateCompanion).Path
            break
        }
    }
}

$companionScriptPath = Join-Path $ScriptDir 'register-companion.ps1'
if ($CompanionRhpPath) {
    & $companionScriptPath -RhpPath $CompanionRhpPath
} else {
    & $companionScriptPath
}

$nativeDir = Split-Path -Parent $resolvedNative

# --- Python discovery (priority: venv → PATH → py launcher → well-known installs) ---
$pythonResolved = $null

# 1. Project venv
$pythonCandidate = Join-Path $RepoRoot "mcp_server\.venv\Scripts\python.exe"
if (Test-Path $pythonCandidate) {
    $pythonResolved = $pythonCandidate
}

# 2. PATH lookup (skip the Windows Store stub — it opens the Store, not Python)
if (-not $pythonResolved) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand -and $pythonCommand.Source -notlike '*WindowsApps*') {
        $pythonResolved = $pythonCommand.Source
    }
}

# 3. Windows Python Launcher
if (-not $pythonResolved) {
    try {
        $pyOutput = & py -3 -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $pyOutput -and (Test-Path $pyOutput)) {
            $pythonResolved = $pyOutput.Trim()
        }
    } catch { }
}

# 4. Well-known Windows install locations
if (-not $pythonResolved) {
    $localAppData = [Environment]::GetFolderPath('LocalApplicationData')
    foreach ($minor in 14, 13, 12, 11) {
        $candidate = Join-Path $localAppData "Programs\Python\Python3$minor\python.exe"
        if (Test-Path $candidate) {
            $pythonResolved = $candidate
            break
        }
    }
}

$workingDir = Join-Path $RepoRoot "mcp_server"
if ($pythonResolved -and (Test-Path $workingDir)) {
    $manifestScriptPath = Join-Path $ScriptDir 'write-chat-service-manifest.ps1'
    & $manifestScriptPath -PluginDir $nativeDir -PythonPath $pythonResolved -WorkingDirectory $workingDir
} elseif (-not $pythonResolved) {
    Write-Warning "Python not found. Chat service manifest not written. Install Python 3.11+ and re-run."
} else {
    Write-Warning "mcp_server directory not found at $workingDir. Chat service manifest not written."
}

Write-Host ''
Write-Host 'RookNative suite registration verified.'
Write-Host "  Native GUID:    $NativeGuid"
Write-Host "  Companion GUID: $CompanionGuid"
Write-Host "  Native path:    $resolvedNative"
if ($CompanionRhpPath) {
    Write-Host "  Companion path: $CompanionRhpPath"
}
if ($pythonResolved) {
    Write-Host "  Python:         $pythonResolved"
}
Write-Host ''
Write-Host 'Start Rhino now -- RookNative should load automatically each session.'
