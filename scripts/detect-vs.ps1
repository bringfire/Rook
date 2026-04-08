# detect-vs.ps1
#
# Single source of truth for Visual Studio 2022 toolchain detection.
# Dot-source this from install.ps1 or build_native.ps1.
#
# Usage:
#   . "$PSScriptRoot\scripts\detect-vs.ps1"
#   $tc = Get-RookVisualStudioToolchain
#   $tc = Get-RookVisualStudioToolchain -PreferredVersion "14.44.35207"
#   $tc = Get-RookVisualStudioToolchain -OverrideVersion "14.43.34808"

function Get-RookVisualStudioToolchain {
    [CmdletBinding()]
    param(
        [string]$PreferredVersion = "14.44.35207",
        [string]$OverrideVersion = ""
    )

    $result = @{
        FoundVisualStudio = $false
        FoundMfc          = $false
        UsedPinnedVersion = $false
        Edition           = $null
        VcvarsallPath     = $null
        VCToolsVersion    = $null
        MfcPath           = $null
        Warnings          = @()
    }

    # Detect VS 2022 edition
    foreach ($edition in @("Community", "Professional", "Enterprise")) {
        $vcvarsall = "C:\Program Files\Microsoft Visual Studio\2022\$edition\VC\Auxiliary\Build\vcvarsall.bat"
        if (Test-Path $vcvarsall) {
            $result.FoundVisualStudio = $true
            $result.Edition = $edition
            $result.VcvarsallPath = $vcvarsall
            break
        }
    }

    if (-not $result.FoundVisualStudio) {
        return $result
    }

    $msvcRoot = "C:\Program Files\Microsoft Visual Studio\2022\$($result.Edition)\VC\Tools\MSVC"

    # If override is specified, use it directly
    if ($OverrideVersion) {
        $overrideMfc = Join-Path $msvcRoot "$OverrideVersion\atlmfc"
        if (Test-Path $overrideMfc) {
            $result.FoundMfc = $true
            $result.VCToolsVersion = $OverrideVersion
            $result.MfcPath = $overrideMfc
            $result.UsedPinnedVersion = ($OverrideVersion -eq $PreferredVersion)
            return $result
        }
        $result.Warnings += @{
            code        = "native.override_missing"
            message     = "Override toolset $OverrideVersion not found or lacks MFC at $overrideMfc."
            remediation = "Check installed MSVC versions: ls '$msvcRoot'"
        }
        # Fall through to auto-detection
    }

    # Check for pinned/preferred version first
    $pinnedMfc = Join-Path $msvcRoot "$PreferredVersion\atlmfc"
    if (Test-Path $pinnedMfc) {
        $result.FoundMfc = $true
        $result.UsedPinnedVersion = $true
        $result.VCToolsVersion = $PreferredVersion
        $result.MfcPath = $pinnedMfc
        return $result
    }

    # Fallback: find newest installed toolset with atlmfc
    if (Test-Path $msvcRoot) {
        $candidates = Get-ChildItem -Path $msvcRoot -Directory |
            Where-Object { Test-Path (Join-Path $_.FullName "atlmfc") } |
            Sort-Object Name -Descending
        if ($candidates.Count -gt 0) {
            $chosen = $candidates[0]
            $result.FoundMfc = $true
            $result.UsedPinnedVersion = $false
            $result.VCToolsVersion = $chosen.Name
            $result.MfcPath = Join-Path $chosen.FullName "atlmfc"
            $result.Warnings += @{
                code        = "native.mfc_pinned_missing"
                message     = "Pinned toolset $PreferredVersion not found. Using $($chosen.Name) instead."
                remediation = "Install MSVC v$PreferredVersion via VS Installer for exact version match."
            }
            return $result
        }
    }

    # VS found but no MFC anywhere
    $result.Warnings += @{
        code        = "native.mfc_missing"
        message     = "VS 2022 ($($result.Edition)) found but no MSVC toolset has MFC."
        remediation = "In VS Installer > Individual Components, add 'C++ MFC for latest v143 build tools (x86 & x64)'."
    }
    return $result
}
