@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "ROOT=%~dp0.."

set "PYTHON_EXE="

call :try_python "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"

if not defined PYTHON_EXE (
  for /d %%D in ("%USERPROFILE%\Desktop\aplica* code") do (
    if not defined PYTHON_EXE call :try_python "%%~fD\WPy64-3.13.12.0\python\python.exe"
  )
)

if "%PYTHON_EXE%"=="" (
  echo Python portatil valido nao encontrado no Desktop.
  exit /b 1
)

if exist "%ROOT%\_local_secrets\sql_auth_runtime.env" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ROOT%\_local_secrets\sql_auth_runtime.env") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

if "%DATABASE_URL%"=="" set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
if "%DARK_JUTSU_API_HOST%"=="" set "DARK_JUTSU_API_HOST=0.0.0.0"
if "%DARK_JUTSU_API_PORT%"=="" set "DARK_JUTSU_API_PORT=8765"

cd /d "%ROOT%"
echo Iniciando API SQL em http://%DARK_JUTSU_API_HOST%:%DARK_JUTSU_API_PORT%
"%PYTHON_EXE%" api\dark_jutsu_api.py
exit /b %errorlevel%

:try_python
if defined PYTHON_EXE exit /b 0
set "CANDIDATE=%~1"
if not exist "%CANDIDATE%" exit /b 0
if not exist "%~dp1Lib\encodings\__init__.py" exit /b 0
if not exist "%~dp1Lib\site-packages\psycopg\__init__.py" exit /b 0
set "PYTHON_EXE=%CANDIDATE%"
exit /b 0
