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
  echo [clipai] Creating virtual environment in .venv...
  python -m venv .venv
  if !errorlevel! neq 0 (
    echo [error] Failed to create virtual environment. Make sure Python is installed.
    pause
    exit /b 1
  )

  set "PYTHON_EXE=.venv\Scripts\python.exe"

  echo [clipai] Installing requirements...
  "!PYTHON_EXE!" -m pip install --upgrade pip
  if !errorlevel! neq 0 (
    echo [error] Failed to upgrade pip.
    pause
    exit /b 1
  )

  if exist "requirements.txt" (
    "!PYTHON_EXE!" -m pip install -r requirements.txt
    if !errorlevel! neq 0 (
      echo [error] Failed to install dependencies from requirements.txt
      pause
      exit /b 1
    )
  ) else (
    echo [warning] requirements.txt not found. Skipping dependency install.
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
echo [clipai] Starting ClipAI...
"%PYTHON_EXE%" main.py
if %errorlevel% neq 0 (
  echo [clipai] Application exited with error code %errorlevel%.
  pause
)

endlocal