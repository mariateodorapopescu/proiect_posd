@echo off
setlocal
rem Start with no arguments for the menu, or pass start / stop / status.
rem Arguments go to a PowerShell file with validated parameters, never to -Command.
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\manage-app.ps1" %*
exit /b %errorlevel%
