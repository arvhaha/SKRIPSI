@echo off
set SCRIPT_DIR=%~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%start_webgis_server.ps1" -AppEnvironment staging -AppEnvironmentLabel STAGING -Port 8010
