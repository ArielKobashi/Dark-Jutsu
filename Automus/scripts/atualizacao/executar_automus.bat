@echo off
setlocal
cd /d "%~dp0\..\.."

set "PYTHON_EXE=C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe"
set "SCRIPT_PATH=%cd%\scripts\atualizacao\automus_update.py"

if not exist "%PYTHON_EXE%" (
  echo Python nao encontrado em:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

"%PYTHON_EXE%" "%SCRIPT_PATH%" --config "%cd%\scripts\atualizacao\automus_config.json" --project-root "%cd%"

echo.
echo Finalizado.
pause
