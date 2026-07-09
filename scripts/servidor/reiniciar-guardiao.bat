@echo off
setlocal EnableExtensions

set "SCRIPTS_DIR=%~dp0.."
set "TASK_NAME=Dark-Jutsu Guardiao Servidor"

pushd "%SCRIPTS_DIR%" || exit /b 1

schtasks /End /TN "%TASK_NAME%" >nul 2>nul
schtasks /Delete /F /TN "%TASK_NAME%" >nul 2>nul

call instalar_atualizar_guardiao_monitor_darkjutsu.bat
set "RESULT=%errorlevel%"

popd
exit /b %RESULT%
