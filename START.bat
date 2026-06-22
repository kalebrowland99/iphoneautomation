@echo off
cd /d "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
if errorlevel 1 (
    echo Setup failed.
    pause
    exit /b 1
)
powershell -ExecutionPolicy Bypass -File "%~dp0run.ps1"
pause
