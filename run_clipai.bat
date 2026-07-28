@echo off
setlocal EnableExtensions
cd /d "%~dp0"

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "scripts\bootstrap_windows.ps1"
if errorlevel 1 (
  echo [clipai] Startup failed with error code %errorlevel%.
  pause
  exit /b 1
)

endlocal
