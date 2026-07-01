@echo off
setlocal
set "ROOT=%~dp0.."
set "PYTHON_EXE=C:\Users\Davi.souza\Desktop\aplicações code\WPy64-3.13.12.0\python\python.exe"
if not exist "%PYTHON_EXE%" (
  echo Python portatil nao encontrado em:
  echo %PYTHON_EXE%
  pause
  exit /b 1
)
if "%DATABASE_URL%"=="" set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
if "%DARK_JUTSU_API_PORT%"=="" set "DARK_JUTSU_API_PORT=8765"
cd /d "%ROOT%"
"%PYTHON_EXE%" api\dark_jutsu_api.py
pause
