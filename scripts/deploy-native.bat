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

echo Deploy succeeded.
