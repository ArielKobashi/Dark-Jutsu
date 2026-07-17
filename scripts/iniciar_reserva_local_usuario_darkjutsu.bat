@echo off
setlocal EnableExtensions

set "ROOT=%~dp0.."
set "PG_BIN=%USERPROFILE%\Desktop\aplicacoes code\pgsql\bin"
set "PGDATA=%USERPROFILE%\Desktop\aplicacoes code\pgsql\data"
set "PYTHON_EXE=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe"
set "LOGDIR=%USERPROFILE%\Desktop\DarkJutsu-reserva\logs"
set "DATABASE_URL=postgresql://dark_jutsu:dark_jutsu_dev@127.0.0.1:5433/dark_jutsu"
set "DARK_JUTSU_API_HOST=0.0.0.0"
set "DARK_JUTSU_API_PORT=8765"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%PG_BIN%\pg_ctl.exe" (
  echo PostgreSQL portable nao encontrado em "%PG_BIN%".
  exit /b 1
)
if not exist "%PGDATA%\PG_VERSION" (
  echo PGDATA nao inicializado em "%PGDATA%".
  exit /b 1
)
if not exist "%PYTHON_EXE%" (
  echo Python portable nao encontrado em "%PYTHON_EXE%".
  exit /b 1
)

netstat -ano -p tcp | findstr /R /C:":5433 .*LISTENING" >nul
if errorlevel 1 (
  "%PG_BIN%\pg_ctl.exe" -D "%PGDATA%" -l "%LOGDIR%\postgres_runtime.log" start
  if errorlevel 1 exit /b 1
)

curl -fsS --max-time 2 "http://127.0.0.1:%DARK_JUTSU_API_PORT%/health" >nul 2>&1
if not errorlevel 1 (
  echo API ja esta online em http://127.0.0.1:%DARK_JUTSU_API_PORT%
  exit /b 0
)

set "Path=%PG_BIN%;%Path%"
cd /d "%ROOT%"
echo Iniciando API reserva em http://0.0.0.0:%DARK_JUTSU_API_PORT%
"%PYTHON_EXE%" api\dark_jutsu_api.py >> "%LOGDIR%\api_stdout.log" 2>> "%LOGDIR%\api_stderr.log"
