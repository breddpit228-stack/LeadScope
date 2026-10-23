@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LeadScope - Launcher

echo ==========================================
echo             LeadScope launcher
echo ==========================================
echo.

REM Find a usable Python installation.
where py >nul 2>nul
if %errorlevel%==0 (
  set "BASEPY=py"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "BASEPY=python"
  ) else (
    echo [ERROR] Python was not found.
    echo Install Python 3.11+ from https://www.python.org/downloads/
    echo During installation enable "Add python.exe to PATH".
    pause
    exit /b 1
  )
)

REM Create an isolated environment on first run.
if not exist ".venv\Scripts\python.exe" (
  echo [1/4] First run: creating a local Python environment...
  %BASEPY% -m venv .venv
  if errorlevel 1 goto :venv_error
) else (
  echo [1/4] Local Python environment found.
)

set "VPY=%CD%\.venv\Scripts\python.exe"

REM Install dependencies only when they are missing.
"%VPY%" -c "import fastapi, uvicorn, requests, bs4, dotenv, trafilatura" >nul 2>nul
if errorlevel 1 (
  echo [2/4] Installing required packages. This happens only on first setup...
  "%VPY%" -m pip install --disable-pip-version-check -r requirements.txt
  if errorlevel 1 goto :pip_error
) else (
  echo [2/4] Required packages are already installed.
)

REM Apply idempotent UI patches shipped with the current release.
echo [3/4] Applying latest interface updates...
if exist "ui_patch_v56.py" "%VPY%" ui_patch_v56.py >nul 2>nul

if not exist ".env" (
  echo.
  echo [NOTE] AI is not configured yet. Run configure_ai_windows.bat to enable research.
  echo.
)

echo [4/4] Starting LeadScope at http://127.0.0.1:8000 ...
start "LeadScope Server" cmd /k ""%VPY%" -m uvicorn app:app --host 127.0.0.1 --port 8000"

REM Wait until the server is actually responding before opening the browser.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$u='http://127.0.0.1:8000'; for($i=0;$i -lt 45;$i++){ try { $r=Invoke-WebRequest -UseBasicParsing -Uri $u -TimeoutSec 1; if($r.StatusCode -ge 200){ exit 0 } } catch {}; Start-Sleep -Milliseconds 500 }; exit 1"
if errorlevel 1 (
  echo.
  echo [WARNING] The server did not answer in time.
  echo Check the separate "LeadScope Server" window for the error message.
  pause
  exit /b 1
)

start "" http://127.0.0.1:8000
exit /b 0

:venv_error
echo.
echo [ERROR] Could not create the local environment.
echo Try running: %BASEPY% -m pip install --upgrade pip
pause
exit /b 1

:pip_error
echo.
echo [ERROR] Required packages could not be installed.
echo Check your internet connection and try again.
pause
exit /b 1
