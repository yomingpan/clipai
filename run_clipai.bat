@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [clipai] Checking environment...

set "PYTHON_EXE="
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "venv\Scripts\python.exe" set "PYTHON_EXE=venv\Scripts\python.exe"
if not defined PYTHON_EXE where python >nul 2>nul && set "PYTHON_EXE=python"

if not defined PYTHON_EXE (
  echo [error] Python was not found. Install Python 3.10 through 3.13 and try again.
  pause
  exit /b 1
)

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] in [(3,10),(3,11),(3,12),(3,13)] else 1)"
if errorlevel 1 (
  echo [error] ClipAI requires Python 3.10 through 3.13.
  "%PYTHON_EXE%" --version
  pause
  exit /b 1
)

"%PYTHON_EXE%" scripts\bootstrap.py
if errorlevel 1 (
  echo [clipai] Startup failed with error code %errorlevel%.
  pause
  exit /b 1
)

endlocal
