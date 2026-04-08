# build_native.ps1
#
# Canonical PowerShell script for building the RookNative C++ plugin.
# Uses shared toolchain detection from scripts/detect-vs.ps1.
#
# Usage:
#   .\build_native.ps1                           # Release, auto-detect toolset
#   .\build_native.ps1 -Configuration Debug      # Debug build
#   .\build_native.ps1 -VCToolsVersion 14.43.x   # Override toolset version

[CmdletBinding()]
param(
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Release",

    [string]$VCToolsVersion = ""
)

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

# --- Toolchain detection (single source of truth) ---
. "$ScriptRoot\scripts\detect-vs.ps1"

$overrideFromEnv = $env:ROOK_VC_TOOLS_VERSION
$effectiveOverride = if ($VCToolsVersion) { $VCToolsVersion } elseif ($overrideFromEnv) { $overrideFromEnv } else { "" }

$tc = Get-RookVisualStudioToolchain -OverrideVersion $effectiveOverride

if (-not $tc.FoundVisualStudio) {
    Write-Error "Visual Studio 2022 not found. Install Community, Professional, or Enterprise with the C++ Desktop workload."
    exit 1
}

if (-not $tc.FoundMfc) {
    Write-Error "No MSVC toolset with MFC found. In VS Installer > Individual Components, add 'C++ MFC for latest v143 build tools (x86 & x64)'."
    foreach ($w in $tc.Warnings) {
        Write-Warning "$($w.code): $($w.message)"
    }
    exit 1
}

foreach ($w in $tc.Warnings) {
    Write-Warning "$($w.code): $($w.message)"
}

$vcxproj = Join-Path $ScriptRoot "src\RookNative\RookNative.vcxproj"
if (-not (Test-Path $vcxproj)) {
    Write-Error "Project file not found: $vcxproj"
    exit 1
}

Write-Host "Building RookNative ($Configuration x64)"
Write-Host "  VS Edition:      $($tc.Edition)"
Write-Host "  VCToolsVersion:  $($tc.VCToolsVersion)"
Write-Host "  MFC:             $($tc.MfcPath)"
Write-Host ""

# --- Build via cmd subprocess (vcvarsall.bat requires cmd.exe) ---
$buildBat = [System.IO.Path]::GetTempFileName() + ".bat"
try {
    @"
@echo off
set "VSCMD_START_DIR=%CD%"
call "$($tc.VcvarsallPath)" x64 >nul 2>&1
set VCToolsVersion=$($tc.VCToolsVersion)
msbuild "%~1" /p:Configuration=$Configuration /p:Platform=x64 /p:VCToolsVersion=$($tc.VCToolsVersion) /m /v:minimal
exit /b %ERRORLEVEL%
"@ | Set-Content -Path $buildBat -Encoding ASCII

    & cmd /c "`"$buildBat`" `"$vcxproj`""
    $buildExitCode = $LASTEXITCODE
}
finally {
    Remove-Item -Path $buildBat -ErrorAction SilentlyContinue
}

if ($buildExitCode -ne 0) {
    Write-Error "BUILD FAILED (exit code $buildExitCode)"
    exit $buildExitCode
}

$outputPath = Join-Path $ScriptRoot "src\RookNative\bin\$Configuration\x64\RookNative.rhp"
if (Test-Path $outputPath) {
    Write-Host ""
    Write-Host "Build succeeded: $outputPath"
} else {
    Write-Error "Build reported success but output not found at $outputPath"
    exit 1
}
