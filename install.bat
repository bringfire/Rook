@echo off
REM Rook Installer - thin wrapper that calls install.ps1
REM Double-click this file or run from cmd.exe to install Rook.
REM For Git Bash / MINGW64, run instead: powershell -ExecutionPolicy Bypass -File install.ps1
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Installation encountered errors. See output above.
    echo.
)
REM Only pause if running interactively (double-click from Explorer).
REM Detect by checking if the parent process is explorer.exe.
echo Press any key to close this window...
pause >nul 2>&1
