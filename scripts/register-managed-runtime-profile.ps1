# register-managed-runtime-profile.ps1
#
# Developer-only helper that rewrites current-user Rhino registry entries for
# locally installed managed Rhino plug-ins.
#
# Rhino.Inside uses the host application's CLR. Revit-hosted Rhino therefore
# cannot load net7/net8-only .rhp assemblies. Release installers should not rely
# on this profile switcher. The direct-registry multi-runtime install path must
# be proven by live smoke tests that record the physical RHP Rhino loads for
# each host/runtime; this script exists only for local debugging when you
# intentionally want to force one runtime child.
#
# Usage:
#   .\scripts\register-managed-runtime-profile.ps1 -Runtime NetFramework -Deploy
#   .\scripts\register-managed-runtime-profile.ps1 -Runtime NetCore -Deploy
#   .\scripts\register-managed-runtime-profile.ps1 -Runtime NetFramework -DryRun

[CmdletBinding()]
param(
    [ValidateSet('NetCore', 'NetFramework')]
    [string]$Runtime = 'NetFramework',

    [ValidateSet('Rook', 'RookRoads', 'SA_Banana')]
    [string[]]$Plugin = @('Rook', 'RookRoads', 'SA_Banana'),

    [switch]$Deploy,
    [switch]$NoDeploy,
    [switch]$DryRun,

    [string]$RookRoadsRoot,
    [string]$SaBananaRoot
)

$ErrorActionPreference = 'Stop'

if ($Deploy -and $NoDeploy) {
    throw 'Use either -Deploy or -NoDeploy, not both.'
}

$ScriptDir = Split-Path -Parent $PSCommandPath
$RepoRoot = Split-Path -Parent $ScriptDir
$SiblingRoot = Split-Path -Parent $RepoRoot

if (-not $RookRoadsRoot) {
    $RookRoadsRoot = Join-Path $SiblingRoot 'RookRoads'
}

if (-not $SaBananaRoot) {
    $SaBananaRoot = Join-Path $SiblingRoot 'SA_Banana'
}

$RhinoPluginRoot = Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'McNeel\Rhinoceros\8.0\Plug-ins'

function New-ManagedPluginProfile {
    param(
        [string]$Name,
        [string]$Guid,
        [string]$RhpName,
        [string]$PluginDir,
        [string]$NetCoreSourceDir,
        [string]$NetFrameworkSourceDir,
        [int]$LoadMode,
        [string]$Organization,
        [string]$Description
    )

    [pscustomobject]@{
        Name = $Name
        Guid = $Guid
        RhpName = $RhpName
        PluginDir = $PluginDir
        NetCoreSourceDir = $NetCoreSourceDir
        NetFrameworkSourceDir = $NetFrameworkSourceDir
        LoadMode = $LoadMode
        Organization = $Organization
        Description = $Description
    }
}

$Profiles = @{
    Rook = New-ManagedPluginProfile `
        -Name 'Rook' `
        -Guid 'b7e4a8c9-1f62-4c7e-9a2b-5d4e8f1c3a7b' `
        -RhpName 'Rook.rhp' `
        -PluginDir (Join-Path $RhinoPluginRoot 'RookNative') `
        -NetCoreSourceDir (Join-Path $RepoRoot 'src\Rook\bin\Release\net7.0') `
        -NetFrameworkSourceDir (Join-Path $RepoRoot 'src\Rook\bin\Release\net48') `
        -LoadMode 2 `
        -Organization 'Bringfire' `
        -Description 'Rook managed companion'

    RookRoads = New-ManagedPluginProfile `
        -Name 'RookRoads' `
        -Guid 'a9b8c7d6-e5f4-3a2b-1c0d-9e8f7a6b5c4d' `
        -RhpName 'RookRC.rhp' `
        -PluginDir (Join-Path $RhinoPluginRoot 'RookRC') `
        -NetCoreSourceDir (Join-Path $RookRoadsRoot 'bin\Release\net7.0') `
        -NetFrameworkSourceDir (Join-Path $RookRoadsRoot 'bin\Release\net48') `
        -LoadMode 1 `
        -Organization 'Bringfire' `
        -Description 'RookRoads HTTP adapter'

    SA_Banana = New-ManagedPluginProfile `
        -Name 'SA_Banana' `
        -Guid '4c23ee05-6ff3-47f6-acb4-475968e37cde' `
        -RhpName 'SA_Banana.rhp' `
        -PluginDir (Join-Path $RhinoPluginRoot 'SA_Banana') `
        -NetCoreSourceDir (Join-Path $SaBananaRoot 'src\SA_Banana\bin\Release\net7.0-windows') `
        -NetFrameworkSourceDir (Join-Path $SaBananaRoot 'src\SA_Banana\bin\Release\net48') `
        -LoadMode 1 `
        -Organization 'SA' `
        -Description 'SA_Banana image generation plug-in'
}

function Get-ProfileSourceDir {
    param($Profile, [string]$Runtime)
    if ($Runtime -eq 'NetFramework') {
        return $Profile.NetFrameworkSourceDir
    }

    return $Profile.NetCoreSourceDir
}

function Get-ProfileTargetDir {
    param($Profile, [string]$Runtime)
    if ($Runtime -eq 'NetFramework') {
        return Join-Path $Profile.PluginDir (Split-Path -Leaf $Profile.NetFrameworkSourceDir)
    }

    return Join-Path $Profile.PluginDir (Split-Path -Leaf $Profile.NetCoreSourceDir)
}

function Copy-DirectoryContents {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    Get-ChildItem -LiteralPath $Source -Force | ForEach-Object {
        Copy-Item -LiteralPath $_.FullName -Destination $Destination -Recurse -Force
    }
}

function Deploy-ProfilePayload {
    param($Profile, [string]$Runtime)

    $sourceDir = Get-ProfileSourceDir -Profile $Profile -Runtime $Runtime
    $targetDir = Get-ProfileTargetDir -Profile $Profile -Runtime $Runtime
    $sourceRhp = Join-Path $sourceDir $Profile.RhpName
    $targetRhp = Join-Path $targetDir $Profile.RhpName

    if ($DryRun) {
        Write-Host "  [DRYRUN] payload source: $sourceDir"
        Write-Host "  [DRYRUN] payload target: $targetDir"
        return $targetRhp
    }

    if (-not $Deploy) {
        if (Test-Path $targetRhp) {
            Write-Host "  Using existing installed payload: $targetRhp"
            return (Resolve-Path $targetRhp).Path
        }

        throw "Installed payload missing at $targetRhp. Re-run with -Deploy after building $Runtime."
    }

    if (-not (Test-Path $sourceRhp)) {
        throw "Build output missing: $sourceRhp"
    }

    Copy-DirectoryContents -Source $sourceDir -Destination $targetDir

    if (-not (Test-Path $targetRhp)) {
        throw "Deploy did not produce expected target: $targetRhp"
    }

    Write-Host "  Deployed payload: $targetRhp"
    return (Resolve-Path $targetRhp).Path
}

function Write-PluginRegistration {
    param($Profile, [string]$RhpPath)

    $regBase = "HKCU:\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$($Profile.Guid)"
    $plugInKey = "$regBase\PlugIn"
    $commandListKey = "$regBase\CommandList"

    if ($DryRun) {
        Write-Host "  [DRYRUN] registry key: $regBase"
        Write-Host "  [DRYRUN] FileName: $RhpPath"
        Write-Host "  [DRYRUN] LoadMode: $($Profile.LoadMode)"
        return
    }

    if (-not (Test-Path $regBase)) {
        New-Item -Path $regBase -Force | Out-Null
    }

    Set-ItemProperty -Path $regBase -Name 'Name' -Value $Profile.Name -Type String
    Set-ItemProperty -Path $regBase -Name 'EnglishName' -Value $Profile.Name -Type String
    Set-ItemProperty -Path $regBase -Name 'Organization' -Value $Profile.Organization -Type String
    Set-ItemProperty -Path $regBase -Name 'Address' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'Country' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'Phone' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'EMail' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'WebSite' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'UpdateURL' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'Fax' -Value '' -Type String
    Set-ItemProperty -Path $regBase -Name 'Description' -Value $Profile.Description -Type String
    Set-ItemProperty -Path $regBase -Name 'RegPath' -Value "\\HKEY_CURRENT_USER\Software\McNeel\Rhinoceros\8.0\Plug-Ins\$($Profile.Guid)" -Type String
    Set-ItemProperty -Path $regBase -Name 'Type' -Value 0x10 -Type DWord
    Set-ItemProperty -Path $regBase -Name 'IsDotNETPlugIn' -Value 1 -Type DWord
    Set-ItemProperty -Path $regBase -Name 'LoadMode' -Value $Profile.LoadMode -Type DWord
    Set-ItemProperty -Path $regBase -Name 'AddToHelpMenu' -Value 0 -Type DWord
    Set-ItemProperty -Path $regBase -Name 'DirectoryInstall' -Value 0 -Type DWord
    Set-ItemProperty -Path $regBase -Name 'FileName' -Value $RhpPath -Type String

    if (-not (Test-Path $plugInKey)) {
        New-Item -Path $plugInKey -Force | Out-Null
    }
    Set-ItemProperty -Path $plugInKey -Name 'FileName' -Value $RhpPath -Type String

    if (-not (Test-Path $commandListKey)) {
        New-Item -Path $commandListKey -Force | Out-Null
    }

    $verify = Get-ItemProperty -Path $plugInKey -Name 'FileName' -ErrorAction Stop
    if ($verify.FileName -ne $RhpPath) {
        throw "Registration verification failed for $($Profile.Name): expected '$RhpPath', got '$($verify.FileName)'."
    }

    Write-Host "  Registered: $RhpPath"
}

Write-Host "Switching managed Rhino plug-ins to $Runtime profile"
if ($Runtime -eq 'NetFramework') {
    Write-Host '  Intended for Rhino.Inside/Revit and Rhino /netfx sessions.'
} else {
    Write-Host '  Intended for normal Rhino 8 .NET Core sessions.'
}

foreach ($pluginName in $Plugin) {
    $profile = $Profiles[$pluginName]
    if (-not $profile) {
        throw "Unknown plugin profile: $pluginName"
    }

    Write-Host ""
    Write-Host "== $($profile.Name) =="
    $targetRhp = Deploy-ProfilePayload -Profile $profile -Runtime $Runtime
    Write-PluginRegistration -Profile $profile -RhpPath $targetRhp
}

Write-Host ""
Write-Host "Managed runtime profile switch complete: $Runtime"
Write-Host "Restart Rhino/Revit before testing plug-in loading."
