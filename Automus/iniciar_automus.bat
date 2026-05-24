@echo off
setlocal
cd /d "%~dp0"

set "PY_EXE=%LocalAppData%\Microsoft\WindowsApps\python.exe"
if not exist "%PY_EXE%" set "PY_EXE=python"

if exist "requirements.txt" "%PY_EXE%" -m pip install -r "requirements.txt"

for %%F in ("scripts\controladordeatualiza*.py") do (
  "%PY_EXE%" "%%~F"
  exit /b
)

echo Arquivo principal do Automus nao encontrado.
pause
