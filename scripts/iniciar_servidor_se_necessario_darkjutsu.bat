@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "LOCKDIR=%SHARE_ROOT%\server-start.lock"
set "LOGDIR=C:\DarkJutsu\logs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] Guardiao Dark-Jutsu iniciado. >> "%LOGFILE%"

for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -in @('%PRIMARY_IP%','%RESERVE_IP%') } | Select-Object -First 1 -ExpandProperty IPAddress)"`) do set "LOCAL_IP=%%I"

if "%LOCAL_IP%"=="" (
    echo [%date% %time%] Esta maquina nao e principal nem reserva. Encerrando. >> "%LOGFILE%"
    exit /b 0
)

call :health "%PRIMARY_IP%"
set "PRIMARY_OK=%errorlevel%"
call :health "%RESERVE_IP%"
set "RESERVE_OK=%errorlevel%"

echo [%date% %time%] IP local=%LOCAL_IP% principal=%PRIMARY_OK% reserva=%RESERVE_OK%. >> "%LOGFILE%"

if "%PRIMARY_OK%"=="0" (
    if not "%LOCAL_IP%"=="%PRIMARY_IP%" (
        call :stop_local_api "principal ativa"
        call :restore_if_inactive
    )
    echo [%date% %time%] Servidor principal ja esta ativo. Encerrando guardiao. >> "%LOGFILE%"
    exit /b 0
)

if "%RESERVE_OK%"=="0" (
    echo [%date% %time%] Servidor reserva ja esta ativo. Nao inicia outro servidor automaticamente. >> "%LOGFILE%"
    echo [%date% %time%] Servidor reserva ja esta ativo. Encerrando guardiao. >> "%LOGFILE%"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%LOCKDIR%'; if (Test-Path -LiteralPath $p) { $age=(Get-Date)-(Get-Item -LiteralPath $p).LastWriteTime; if ($age.TotalMinutes -gt 2) { Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue } }" >nul 2>&1
mkdir "%LOCKDIR%" 2>nul
if not %errorlevel%==0 (
    echo [%date% %time%] Outra maquina esta tentando iniciar. Aguardando. >> "%LOGFILE%"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 20" >nul 2>&1
    call :health "%PRIMARY_IP%"
    if "!errorlevel!"=="0" exit /b 0
    call :health "%RESERVE_IP%"
    if "!errorlevel!"=="0" exit /b 0
    echo [%date% %time%] Lock ainda existe e nenhum servidor respondeu. Encerrando para evitar duplicidade. >> "%LOGFILE%"
    exit /b 0
)

echo %COMPUTERNAME% %USERNAME% %date% %time%>"%LOCKDIR%\owner.txt"

call :health "%PRIMARY_IP%"
if "%errorlevel%"=="0" goto cleanup
call :health "%RESERVE_IP%"
if "%errorlevel%"=="0" goto cleanup

echo [%date% %time%] Nenhum servidor ativo. Esta maquina (%LOCAL_IP%) vai iniciar. >> "%LOGFILE%"

call "%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    echo [%date% %time%] ERRO ao iniciar PostgreSQL. >> "%LOGFILE%"
    goto cleanup_fail
)

wscript.exe //B "%SHARE_ROOT%\scripts\iniciar_api_darkjutsu_hidden.vbs"

for /L %%N in (1,1,20) do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 1" >nul 2>&1
    call :health "%LOCAL_IP%"
    if "!errorlevel!"=="0" (
        echo [%date% %time%] API ativa em %LOCAL_IP%:%API_PORT%. >> "%LOGFILE%"
        goto cleanup
    )
)

echo [%date% %time%] AVISO: API nao respondeu no tempo esperado. >> "%LOGFILE%"

:cleanup
rmdir "%LOCKDIR%" 2>nul
exit /b 0

:cleanup_fail
rmdir "%LOCKDIR%" 2>nul
exit /b 1

:health
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-RestMethod -Uri 'http://%~1:%API_PORT%/health' -TimeoutSec 3; if ($r.ok -eq $true) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
exit /b %errorlevel%

:stop_local_api
netstat -ano -p tcp | findstr /R /C:":%API_PORT% .*LISTENING" >nul
if %errorlevel%==0 (
    echo [%date% %time%] API local ativa mas %~1. Encerrando API local. >> "%LOGFILE%"
    call "%SHARE_ROOT%\scripts\parar_api_darkjutsu.bat" >> "%LOGFILE%" 2>&1
)
exit /b 0

:restore_if_inactive
if exist "%SHARE_ROOT%\scripts\restaurar_backup_reserva_darkjutsu.bat" (
    echo [%date% %time%] Atualizando banco local a partir do backup mais recente. >> "%LOGFILE%"
    call "%SHARE_ROOT%\scripts\restaurar_backup_reserva_darkjutsu.bat" >> "%LOGFILE%" 2>&1
)
exit /b 0
