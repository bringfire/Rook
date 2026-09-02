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

$abiTestSource = Join-Path $ScriptRoot "src\RookNative\GrasshopperBridgeAbiValidationTests.cpp"
if (-not (Test-Path $abiTestSource)) {
    Write-Error "Grasshopper bridge ABI validation test not found: $abiTestSource"
    exit 1
}

$abiTestOutputDir = Join-Path $ScriptRoot "src\RookNative\obj\$Configuration\x64\GrasshopperBridgeAbiValidationTests"
$abiTestObject = Join-Path $abiTestOutputDir "GrasshopperBridgeAbiValidationTests.obj"
$abiTestExecutable = Join-Path $abiTestOutputDir "GrasshopperBridgeAbiValidationTests.exe"

$hostGenerationTestSource = Join-Path $ScriptRoot "src\RookNative\HostGenerationIdValidationTests.cpp"
if (-not (Test-Path $hostGenerationTestSource)) {
    Write-Error "Host generation ID validation test not found: $hostGenerationTestSource"
    exit 1
}

$hostGenerationTestOutputDir = Join-Path $ScriptRoot "src\RookNative\obj\$Configuration\x64\HostGenerationIdValidationTests"
$hostGenerationTestObject = Join-Path $hostGenerationTestOutputDir "HostGenerationIdValidationTests.obj"
$hostGenerationTestExecutable = Join-Path $hostGenerationTestOutputDir "HostGenerationIdValidationTests.exe"

Write-Host "Building RookNative ($Configuration x64)"
Write-Host "  VS Edition:      $($tc.Edition)"
Write-Host "  VCToolsVersion:  $($tc.VCToolsVersion)"
Write-Host "  MFC:             $($tc.MfcPath)"
Write-Host ""

# --- Build via cmd subprocess (vcvarsall.bat requires cmd.exe) ---
$buildBat = [System.IO.Path]::GetTempFileName() + ".bat"
try {
    $vcvarsVersion = (($tc.VCToolsVersion -split '\.')[0..1] -join '.')
    @"
@echo off
set "VSCMD_START_DIR=%CD%"
call "$($tc.VcvarsallPath)" x64 -vcvars_ver=$vcvarsVersion >nul 2>&1
set VCToolsVersion=$($tc.VCToolsVersion)
if not exist "$abiTestOutputDir" mkdir "$abiTestOutputDir"
echo Running Grasshopper bridge ABI validation tests
cl /nologo /std:c++17 /EHsc /W4 /WX /I"$ScriptRoot\src\RookNative" /Fo:"$abiTestObject" /Fe:"$abiTestExecutable" "$abiTestSource"
if errorlevel 1 exit /b %ERRORLEVEL%
"$abiTestExecutable"
if errorlevel 1 exit /b %ERRORLEVEL%
if not exist "$hostGenerationTestOutputDir" mkdir "$hostGenerationTestOutputDir"
echo Running host generation ID validation tests
cl /nologo /std:c++17 /EHsc /W4 /WX /I"$ScriptRoot\src\RookNative" /Fo:"$hostGenerationTestObject" /Fe:"$hostGenerationTestExecutable" "$hostGenerationTestSource"
if errorlevel 1 exit /b %ERRORLEVEL%
"$hostGenerationTestExecutable"
if errorlevel 1 exit /b %ERRORLEVEL%
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
