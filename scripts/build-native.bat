@echo off
REM Thin compatibility wrapper — delegates to PowerShell for all logic.
REM Usage: build-native.bat [Debug|Release] [VCToolsVersion]
REM Default: Release, auto-detect toolset

set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=Release

set VCTOOLS=%~2

if "%VCTOOLS%"=="" (
    powershell -ExecutionPolicy Bypass -File "%~dp0..\build_native.ps1" -Configuration %CONFIG%
) else (
    powershell -ExecutionPolicy Bypass -File "%~dp0..\build_native.ps1" -Configuration %CONFIG% -VCToolsVersion %VCTOOLS%
)
exit /b %ERRORLEVEL%
