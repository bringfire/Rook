@echo off
REM Build and deploy RookNative to Rhino 8 plugin directory.
REM Usage: deploy-native.bat [Debug|Release]
REM Default: Release

setlocal
set CONFIG=%~1
if "%CONFIG%"=="" set CONFIG=Release

call "%~dp0build-native.bat" %CONFIG%
if errorlevel 1 exit /b 1

set SRC=%~dp0..\src\RookNative\bin\%CONFIG%\x64\RookNative.rhp
set DST=%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.rhp

echo Deploying to %DST%...
copy /Y "%SRC%" "%DST%" >nul
if errorlevel 1 (
    echo DEPLOY FAILED — is Rhino running?
    exit /b 1
)

REM Also copy debug symbols so stack traces resolve to source.
REM Non-fatal: the .rhp copy already succeeded — symbol drift is cosmetic.
set SRC_PDB=%~dp0..\src\RookNative\bin\%CONFIG%\x64\RookNative.pdb
set DST_PDB=%APPDATA%\McNeel\Rhinoceros\8.0\Plug-ins\RookNative\RookNative.pdb
if exist "%SRC_PDB%" copy /Y "%SRC_PDB%" "%DST_PDB%" >nul

echo Deploy succeeded.
