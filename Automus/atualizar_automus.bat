@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=%LocalAppData%\Microsoft\WindowsApps\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

"%PY_EXE%" "scripts\preparar_release_automus.py"
pause
