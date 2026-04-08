# register-companion.ps1
#
# Pre-registers the managed Rook companion plugin with Rhino 8.
#
# Rhino builds its in-memory plugin record list from the registry at startup.
# LoadPlugIn(GUID) only searches that list -- runtime registry writes are
# invisible.  This script must be run ONCE after deploy, BEFORE launching
# Rhino, so that native can call LoadPlugIn(companionGuid) successfully.
#
# Usage:
#   .\scripts\register-companion.ps1                              # auto-detect
#   .\scripts\register-companion.ps1 -RhpPath "C:\...\Rook.rhp"  # explicit path
#   .\scripts\register-companion.ps1 -Unregister                  # remove

[CmdletBinding()]
param(
    [string]$RhpPath,
    [switch]$Unregister
)

$ErrorActionPreference = 'Stop'

$CompanionGuid = 'b7e4a8c9-1f62-4c7e-9a2b-5d4e8f1c3a7b'
$RegBase       = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$CompanionGuid"

# ---- Unregister -----------------------------------------------------------

if ($Unregister) {
    if (Test-Path $RegBase) {
        Remove-Item -Path $RegBase -Recurse -Force
        Write-Host "Removed registration at $RegBase"
    } else {
        Write-Host 'Not registered -- nothing to remove.'
    }
    exit 0
}

# ---- Resolve RHP path -----------------------------------------------------

if (-not $RhpPath) {
    $ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepoRoot  = Split-Path -Parent $ScriptDir

    # Priority 1: Colocated with deployed RookNative.rhp.
    # In a deployed package, both plugins live in the same directory.
    $NativeGuid    = 'a38e0e8f-e06e-40d2-a6bd-7edbc2cb1906'
    $NativeRegPath = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$NativeGuid\PlugIn"
    $NativeReg     = Get-ItemProperty -Path $NativeRegPath -Name 'FileName' -ErrorAction SilentlyContinue

    if ($NativeReg -and $NativeReg.FileName) {
        $NativeDir = Split-Path -Parent $NativeReg.FileName
        $Colocated = Join-Path $NativeDir 'Rook.rhp'
        if (Test-Path $Colocated) {
            $RhpPath = (Resolve-Path $Colocated).Path
            Write-Host "Found companion colocated with RookNative: $RhpPath"
        }
    }

    # Priority 2: Repo build outputs (development workflow).
    if (-not $RhpPath) {
        $Candidates = @(
            (Join-Path $RepoRoot 'src\Rook\bin\Debug\net7.0\Rook.rhp'),
            (Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0\Rook.rhp'),
            (Join-Path $RepoRoot 'src\Rook\bin\Debug\net48\Rook.rhp'),
            (Join-Path $RepoRoot 'src\Rook\bin\Release\net48\Rook.rhp')
        )

        foreach ($c in $Candidates) {
            if (Test-Path $c) {
                $RhpPath = (Resolve-Path $c).Path
                Write-Host "Found companion in build output: $RhpPath"
                break
            }
        }
    }

    if (-not $RhpPath) {
        $msg = "Could not find Rook.rhp.`n"
        $msg += "  Checked colocated with registered RookNative (not found or native not registered).`n"
        $msg += "  Checked repo build outputs (not built).`n`n"
        $msg += "Build the managed companion first:`n"
        $msg += "  dotnet build src\Rook\Rook.csproj -c Debug`n`n"
        $msg += "Or pass -RhpPath explicitly:`n"
        $msg += "  .\scripts\register-companion.ps1 -RhpPath 'C:\path\to\Rook.rhp'"
        Write-Error $msg
        exit 1
    }
}

if (-not (Test-Path $RhpPath)) {
    Write-Error "File not found: $RhpPath"
    exit 1
}

$RhpPath = (Resolve-Path $RhpPath).Path
Write-Host "Registering companion: $RhpPath"

# ---- Write registry -------------------------------------------------------

# Main plugin key -- mirrors structure of existing Rhino .NET plugins.
if (-not (Test-Path $RegBase)) {
    New-Item -Path $RegBase -Force | Out-Null
}

# String values
Set-ItemProperty -Path $RegBase -Name 'Name'         -Value 'Rook'         -Type String
Set-ItemProperty -Path $RegBase -Name 'EnglishName'  -Value 'Rook'         -Type String
Set-ItemProperty -Path $RegBase -Name 'Organization' -Value 'Bringfire'    -Type String
Set-ItemProperty -Path $RegBase -Name 'Address'      -Value ''             -Type String
Set-ItemProperty -Path $RegBase -Name 'Country'      -Value ''             -Type String
Set-ItemProperty -Path $RegBase -Name 'Phone'        -Value ''             -Type String
Set-ItemProperty -Path $RegBase -Name 'EMail'        -Value ''             -Type String
Set-ItemProperty -Path $RegBase -Name 'WebSite'      -Value 'https://github.com/bringfire/Rhino_AI'          -Type String
Set-ItemProperty -Path $RegBase -Name 'UpdateURL'    -Value 'https://github.com/bringfire/Rhino_AI/releases' -Type String
Set-ItemProperty -Path $RegBase -Name 'Fax'          -Value ''             -Type String
Set-ItemProperty -Path $RegBase -Name 'RegPath'      -Value "\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$CompanionGuid" -Type String

# DWORD values
Set-ItemProperty -Path $RegBase -Name 'Type'             -Value 0x10 -Type DWord  # utility plugin
Set-ItemProperty -Path $RegBase -Name 'IsDotNETPlugIn'   -Value 1    -Type DWord
Set-ItemProperty -Path $RegBase -Name 'LoadMode'         -Value 2    -Type DWord  # when needed
Set-ItemProperty -Path $RegBase -Name 'AddToHelpMenu'    -Value 0    -Type DWord
Set-ItemProperty -Path $RegBase -Name 'DirectoryInstall' -Value 0    -Type DWord

# PlugIn subkey with FileName -- this is how Rhino locates the .rhp on disk.
$PlugInKey = "$RegBase\PlugIn"
if (-not (Test-Path $PlugInKey)) {
    New-Item -Path $PlugInKey -Force | Out-Null
}
Set-ItemProperty -Path $PlugInKey -Name 'FileName' -Value $RhpPath -Type String

# CommandList subkey (empty -- Rhino expects it to exist).
$CmdKey = "$RegBase\CommandList"
if (-not (Test-Path $CmdKey)) {
    New-Item -Path $CmdKey -Force | Out-Null
}

# ---- Verify ---------------------------------------------------------------

$Errors = @()

# Check PlugIn\FileName
$verifyFile = Get-ItemProperty -Path "$RegBase\PlugIn" -Name 'FileName' -ErrorAction SilentlyContinue
if (-not $verifyFile -or $verifyFile.FileName -ne $RhpPath) {
    $got = '(null)'
    if ($verifyFile) { $got = $verifyFile.FileName }
    $Errors += "PlugIn\FileName: expected '$RhpPath', got '$got'"
}

# Check critical metadata on root key
$verifyRoot = Get-ItemProperty -Path $RegBase -ErrorAction SilentlyContinue
if ($verifyRoot) {
    if ($verifyRoot.IsDotNETPlugIn -ne 1) { $Errors += "IsDotNETPlugIn: expected 1, got $($verifyRoot.IsDotNETPlugIn)" }
    if ($verifyRoot.Name -ne 'Rook')      { $Errors += "Name: expected 'Rook', got '$($verifyRoot.Name)'" }
    if ($verifyRoot.Type -ne 0x10)        { $Errors += "Type: expected 16, got $($verifyRoot.Type)" }
} else {
    $Errors += "Root key not found at $RegBase"
}

# Check CommandList subkey exists
if (-not (Test-Path "$RegBase\CommandList")) {
    $Errors += 'CommandList subkey missing'
}

if ($Errors.Count -gt 0) {
    Write-Error ("Verification failed:`n  " + ($Errors -join "`n  "))
    exit 1
}

Write-Host ''
Write-Host 'Registration verified.'
Write-Host "  GUID:           $CompanionGuid"
Write-Host "  FileName:       $RhpPath"
Write-Host '  IsDotNETPlugIn: 1'
Write-Host '  Type:           0x10 (utility)'
Write-Host ''
Write-Host 'Start Rhino now -- RookNative will auto-load the companion.'
