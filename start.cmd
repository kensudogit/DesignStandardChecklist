@echo off
setlocal
cd /d "%~dp0"
REM From cmd.exe, do not run start.ps1 directly.
REM Association opens a new window and returns immediately.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
exit /b %ERRORLEVEL%
