@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=C:\Users\jean.martimiano\Desktop\WPy64-3.13.12.0\python\python.exe"
set "PYW_EXE=C:\Users\jean.martimiano\Desktop\WPy64-3.13.12.0\python\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=%LocalAppData%\Microsoft\WindowsApps\python.exe"
if not exist "%PYW_EXE%" set "PYW_EXE=%LocalAppData%\Microsoft\WindowsApps\pythonw.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"
if not exist "%PYW_EXE%" set "PYW_EXE=%PY_EXE%"

"%PYW_EXE%" "scripts\preparar_release_automus.py"
