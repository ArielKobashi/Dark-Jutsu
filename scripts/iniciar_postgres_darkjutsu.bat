@echo off
setlocal EnableExtensions

set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
set "PGDATA=C:\DarkJutsu\postgres-data"
set "PGPORT=5433"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_startup.log"
set "RUNTIME_LOG=%LOGDIR%\postgres_runtime.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Verificando PostgreSQL Dark-Jutsu... >> "%LOGFILE%"

netstat -ano -p tcp | findstr /R /C:":%PGPORT% .*LISTENING" >nul
if %errorlevel%==0 (
    echo [%date% %time%] PostgreSQL ja esta rodando na porta %PGPORT%. >> "%LOGFILE%"
    exit /b 0
)

if not exist "%PG_BIN%\pg_ctl.exe" (
    echo [%date% %time%] ERRO: pg_ctl.exe nao encontrado em %PG_BIN%. >> "%LOGFILE%"
    exit /b 1
)

if not exist "%PGDATA%\postgresql.conf" (
    echo [%date% %time%] ERRO: PGDATA invalido ou nao inicializado em %PGDATA%. >> "%LOGFILE%"
    exit /b 1
)

echo [%date% %time%] PostgreSQL nao encontrado. Iniciando... >> "%LOGFILE%"
"%PG_BIN%\pg_ctl.exe" -D "%PGDATA%" -l "%RUNTIME_LOG%" start >> "%LOGFILE%" 2>&1

timeout /t 5 /nobreak >nul

netstat -ano -p tcp | findstr /R /C:":%PGPORT% .*LISTENING" >nul
if %errorlevel%==0 (
    echo [%date% %time%] PostgreSQL iniciado com sucesso na porta %PGPORT%. >> "%LOGFILE%"
    exit /b 0
)

echo [%date% %time%] ERRO: PostgreSQL nao iniciou corretamente. >> "%LOGFILE%"
exit /b 1
