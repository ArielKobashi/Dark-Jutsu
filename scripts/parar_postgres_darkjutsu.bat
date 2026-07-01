@echo off
setlocal EnableExtensions

set "PG_BIN=C:\DarkJutsu\PostgreSQL\pgsql\bin"
set "PGDATA=C:\DarkJutsu\postgres-data"
set "PGPORT=5433"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\postgres_shutdown.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Solicitando parada do PostgreSQL Dark-Jutsu... >> "%LOGFILE%"

if not exist "%PG_BIN%\pg_ctl.exe" (
    echo [%date% %time%] ERRO: pg_ctl.exe nao encontrado em %PG_BIN%. >> "%LOGFILE%"
    exit /b 1
)

if not exist "%PGDATA%\postgresql.conf" (
    echo [%date% %time%] ERRO: PGDATA invalido ou nao inicializado em %PGDATA%. >> "%LOGFILE%"
    exit /b 1
)

netstat -ano -p tcp | findstr /R /C:":%PGPORT% .*LISTENING" >nul
if not %errorlevel%==0 (
    echo [%date% %time%] PostgreSQL ja esta parado na porta %PGPORT%. >> "%LOGFILE%"
    exit /b 0
)

"%PG_BIN%\pg_ctl.exe" -D "%PGDATA%" stop -m fast >> "%LOGFILE%" 2>&1

echo [%date% %time%] Comando de parada executado. >> "%LOGFILE%"
exit /b 0
