@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\davi.souza\AppData\Local\Microsoft\WindowsApps\python.exe"
set "SCRIPT_PATH=%cd%\scripts\executar_tudo.py"

if not exist "%PYTHON_EXE%" (
  echo Python nao encontrado em:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)

if not exist "%SCRIPT_PATH%" (
  echo Script nao encontrado em:
  echo %SCRIPT_PATH%
  pause
  exit /b 1
)

echo Executando automacao completa...
"%PYTHON_EXE%" "%SCRIPT_PATH%"

echo.
echo Execucao finalizada.
pause

