@echo off
setlocal
title Cleanroom Rebuild Installer
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-CleanroomRebuild.ps1"
set "INSTALL_EXIT=%ERRORLEVEL%"
echo.
if not "%INSTALL_EXIT%"=="0" (
  echo Installation did not complete. See install.log in this folder.
) else (
  echo Installation and verification completed successfully.
)
echo.
pause
exit /b %INSTALL_EXIT%
