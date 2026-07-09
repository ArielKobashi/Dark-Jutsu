@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "LOGDIR=C:\DarkJutsu\logs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] ACAO MANUAL: tornar esta maquina o servidor Dark-Jutsu. Usuario=%USERNAME% Maquina=%COMPUTERNAME% >> "%LOGFILE%"

C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
if errorlevel 1 (
    call "%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
    if errorlevel 1 (
        echo [%date% %time%] ERRO: PostgreSQL nao iniciou e nao esta pronto. >> "%LOGFILE%"
        exit /b 1
    )
)

wscript.exe //B "%SHARE_ROOT%\scripts\iniciar_api_darkjutsu_service.vbs"
echo [%date% %time%] API solicitada em segundo plano. >> "%LOGFILE%"
exit /b 0
