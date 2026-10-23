@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title LeadScope - Update and Start

echo ==========================================
echo         LeadScope - Update and Start
echo ==========================================
echo.

echo [1/3] Checking for the latest LeadScope version...
set "LS_ZIP=%TEMP%\leadscope-main.zip"
set "LS_TMP=%TEMP%\leadscope-update-%RANDOM%-%RANDOM%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ErrorActionPreference='Stop';" ^
  "$zip='%LS_ZIP%'; $tmp='%LS_TMP%';" ^
  "if(Test-Path $zip){Remove-Item $zip -Force}; if(Test-Path $tmp){Remove-Item $tmp -Recurse -Force};" ^
  "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/breddpit228-stack/LeadScope/archive/refs/heads/main.zip' -OutFile $zip;" ^
  "Expand-Archive -LiteralPath $zip -DestinationPath $tmp -Force;"
if errorlevel 1 goto :update_error

set "LS_SRC=%LS_TMP%\LeadScope-main"
if not exist "%LS_SRC%\app.py" goto :update_error

echo [2/3] Applying update while keeping your local key and database...
robocopy "%LS_SRC%" "%CD%" /E /NFL /NDL /NJH /NJS /NP /XF ".env" "lead_studio.db" /XD ".venv" ".git" >nul
set "RC=%ERRORLEVEL%"
if %RC% GEQ 8 goto :update_error

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Remove-Item -LiteralPath '%LS_ZIP%' -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath '%LS_TMP%' -Recurse -Force -ErrorAction SilentlyContinue"

echo [3/3] Starting LeadScope...
call start_windows.bat
exit /b %ERRORLEVEL%

:update_error
echo.
echo [WARNING] Could not update LeadScope from GitHub.
echo Your local files were kept. Starting the installed version instead...
echo.
if exist "%LS_TMP%" powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath '%LS_TMP%' -Recurse -Force -ErrorAction SilentlyContinue"
if exist "%LS_ZIP%" del /q "%LS_ZIP%" >nul 2>nul
call start_windows.bat
exit /b %ERRORLEVEL%
