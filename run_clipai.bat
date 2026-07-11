@echo off
setlocal EnableExtensions EnableDelayedExpansion

echo [clipai] Checking environment...

:: Support multiple common venv directory names
set "VENV_DIRS=.venv venv"
set "PYTHON_EXE="

for %%d in (%VENV_DIRS%) do (
  if exist "%%d\Scripts\python.exe" (
    set "PYTHON_EXE=%%d\Scripts\python.exe"
    goto :found
  )
)

:not_found
echo [clipai] Virtual environment not found.
set /p choice="Would you like to create a virtual environment and install dependencies? (y/n): "

if /i "%choice%"=="y" (
  set "PYTHON_EXE=python"
  call :require_python_310 "!PYTHON_EXE!"
  if errorlevel 1 (
    pause
    exit /b 1
  )

  echo [clipai] Creating virtual environment in .venv...
  "!PYTHON_EXE!" -m venv .venv
  if errorlevel 1 (
    echo [error] Failed to create virtual environment. Make sure Python is installed.
    pause
    exit /b 1
  )

  set "PYTHON_EXE=.venv\Scripts\python.exe"

  echo [clipai] Installing ClipAI from pyproject.toml...
  "!PYTHON_EXE!" -m pip install --upgrade pip
  if !errorlevel! neq 0 (
    echo [error] Failed to upgrade pip.
    pause
    exit /b 1
  )

  "!PYTHON_EXE!" -m pip install -e ".[dev]"
  if !errorlevel! neq 0 (
    echo [error] Failed to install ClipAI from pyproject.toml
    pause
    exit /b 1
  )

) else (
  echo [clipai] Please create a virtual environment manually or use system Python.
  set /p use_system="Try using system python? (y/n): "
  if /i "!use_system!"=="y" (
    set "PYTHON_EXE=python"
    goto :found
  )
  pause
  exit /b 1
)

:found
call :require_python_310 "%PYTHON_EXE%"
if errorlevel 1 (
  pause
  exit /b 1
)

echo [clipai] Starting ClipAI...
"%PYTHON_EXE%" main.py
if errorlevel 1 (
  echo [clipai] Application exited with error code %errorlevel%.
  pause
)

endlocal
exit /b

:require_python_310
"%~1" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
if errorlevel 1 (
  echo [error] ClipAI requires Python 3.10 or newer.
  "%~1" --version
  exit /b 1
)
exit /b 0
