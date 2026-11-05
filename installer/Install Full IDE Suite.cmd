@echo off
setlocal
title Cleanroom Rebuild - Full IDE Suite
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-CleanroomRebuild.ps1" -IDEProfile Full
set "INSTALL_EXIT=%ERRORLEVEL%"
echo.
if not "%INSTALL_EXIT%"=="0" echo Installation did not complete. See install.log.
pause
exit /b %INSTALL_EXIT%
