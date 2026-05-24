@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=%LocalAppData%\Microsoft\WindowsApps\python.exe"
set "PYW_EXE=%LocalAppData%\Microsoft\WindowsApps\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"
if not exist "%PYW_EXE%" set "PYW_EXE=%PY_EXE%"

"%PYW_EXE%" "scripts\preparar_release_automus.py"
