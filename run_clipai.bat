@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"

set "VENV_DIR=%ROOT%.venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python is not installed or not in PATH.
  echo Please install Python 3.11+ first: https://www.python.org/downloads/
  exit /b 1
)

if not exist "%VENV_PY%" (
  echo [INFO] Creating virtual environment in .venv ...
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    exit /b 1
  )

  echo [INFO] Installing dependencies ...
  "%VENV_PY%" -m pip install --upgrade pip
  if exist "%ROOT%requirements.txt" (
    "%VENV_PIP%" install -r "%ROOT%requirements.txt"
  )
  "%VENV_PIP%" install pytest mypy
)

echo [INFO] Starting ClipAI ...
"%VENV_PY%" "%ROOT%main.py" %*
exit /b %errorlevel%
