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

set "ENV_FILE=%ROOT%\_local_secrets\sql_auth_runtime.env"
if not exist "%ENV_FILE%" if exist "%USERPROFILE%\Desktop\Dark-Jutsu\_local_secrets\sql_auth_runtime.env" set "ENV_FILE=%USERPROFILE%\Desktop\Dark-Jutsu\_local_secrets\sql_auth_runtime.env"
if exist "%ENV_FILE%" (
  for /f "usebackq tokens=1,* delims==" %%A in ("%ENV_FILE%") do (
    if not "%%A"=="" set "%%A=%%B"
  )
)

if "%DATABASE_URL%"=="" set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
if "%DARK_JUTSU_API_HOST%"=="" set "DARK_JUTSU_API_HOST=0.0.0.0"
if "%DARK_JUTSU_API_PORT%"=="" set "DARK_JUTSU_API_PORT=8765"

cd /d "%ROOT%"
curl -fsS --max-time 2 "http://127.0.0.1:%DARK_JUTSU_API_PORT%/health" >nul 2>&1
if %errorlevel%==0 (
  echo API SQL ja esta respondendo em http://127.0.0.1:%DARK_JUTSU_API_PORT%
  exit /b 0
)
for /f "tokens=5" %%P in ('netstat -ano -p tcp ^| findstr /R /C:":%DARK_JUTSU_API_PORT% .*LISTENING"') do (
  taskkill /PID %%P /F >nul 2>&1
)
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
