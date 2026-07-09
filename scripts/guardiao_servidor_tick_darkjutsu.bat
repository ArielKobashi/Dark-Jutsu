@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "BLACKOUT_FILE=%SHARE_ROOT%\servidor-preto-contador.txt"
set "PRIMARY_REQUEST_FILE=%SHARE_ROOT%\solicitar-principal.txt"
set "OLD_PAUSE_FILE=%SHARE_ROOT%\principal-pausado-ate.txt"
set "LOGDIR=C:\DarkJutsu\logs"
set "EVENT_LOGGER=%SHARE_ROOT%\scripts\registrar_evento_servidor_darkjutsu.bat"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

echo ==================================================
echo Dark-Jutsu - Verificacao do guardiao
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.

set "LOCAL_IP="
ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if %errorlevel%==0 set "LOCAL_IP=%PRIMARY_IP%"
if "%LOCAL_IP%"=="" (
    ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
    if !errorlevel!==0 set "LOCAL_IP=%RESERVE_IP%"
)

if "%LOCAL_IP%"=="" (
    echo FALHOU: esta maquina nao tem IP de principal/reserva.
    echo [%date% %time%] Esta maquina nao tem IP de principal/reserva. Guardiao nao vai iniciar servidor. >> "%LOGFILE%"
    call :event AVISO GUARDIAO "Maquina sem IP de principal/reserva; guardiao nao age."
    exit /b 0
)

call :health "%PRIMARY_IP%"
set "PRIMARY_OK=%errorlevel%"
call :health "%RESERVE_IP%"
set "RESERVE_OK=%errorlevel%"

echo [%date% %time%] Tick guardiao CMD. Local=%LOCAL_IP% principal=%PRIMARY_OK% reserva=%RESERVE_OK%. >> "%LOGFILE%"
echo IP local: %LOCAL_IP%
echo Principal %PRIMARY_IP%: %PRIMARY_OK%
echo Reserva   %RESERVE_IP%: %RESERVE_OK%
echo.
call :event INFO GUARDIAO "Tick. Local=%LOCAL_IP%; principal=%PRIMARY_OK%; reserva=%RESERVE_OK%."

if "%PRIMARY_OK%"=="0" (
    echo OK: principal respondeu. Nao precisa assumir.
    del "%BLACKOUT_FILE%" >nul 2>&1
    del "%PRIMARY_REQUEST_FILE%" >nul 2>&1
    if not "%LOCAL_IP%"=="%PRIMARY_IP%" (
        call :event INFO GUARDIAO "Principal respondeu; reserva deve parar API local se estiver ativa."
        call "%SHARE_ROOT%\scripts\parar_api_darkjutsu.bat" >nul 2>&1
    )
    echo [%date% %time%] Principal ativa; reserva deve ficar sem API local. >> "%LOGFILE%"
    call :event OK GUARDIAO "Principal ativa. Nenhuma assuncao necessaria."
    exit /b 0
)

if "%RESERVE_OK%"=="0" (
    echo OK: reserva respondeu.
    del "%BLACKOUT_FILE%" >nul 2>&1
    del "%PRIMARY_REQUEST_FILE%" >nul 2>&1
    if "%LOCAL_IP%"=="%PRIMARY_IP%" (
        del "%OLD_PAUSE_FILE%" >nul 2>&1
        echo [%date% %time%] Reserva ativa e principal livre; principal vai reassumir agora. >> "%LOGFILE%"
        call :event INFO FAILBACK "Reserva respondeu e principal esta livre; principal vai reassumir."
        call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
        set "RC=%errorlevel%"
        if not "!RC!"=="0" call :event ERRO FAILBACK "Principal tentou reassumir, mas falhou. Codigo=!RC!."
        exit /b !RC!
    ) else (
        echo [%date% %time%] Reserva ativa nesta maquina. Aguardando principal voltar. >> "%LOGFILE%"
        call :event OK GUARDIAO "Reserva ativa nesta maquina. Aguardando principal voltar."
        exit /b 0
    )
)

call :blackout_minutes
set "BLACKOUT_MINUTES=%errorlevel%"

if "%LOCAL_IP%"=="%PRIMARY_IP%" (
    echo ACAO: nenhum servidor respondeu; principal vai iniciar agora.
    echo [%date% %time%] Nenhum servidor ativo; principal vai iniciar imediatamente. >> "%LOGFILE%"
    call :event INFO ASSUMIR "Nenhum servidor respondeu; principal vai iniciar imediatamente."
    call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    set "RC=%errorlevel%"
    if not "!RC!"=="0" call :event ERRO ASSUMIR "Principal falhou ao iniciar. Codigo=!RC!."
    exit /b !RC!
)

if "%LOCAL_IP%"=="%RESERVE_IP%" (
    echo ACAO: nenhum servidor respondeu; reserva vai iniciar agora.
    echo [%date% %time%] Preto ha %BLACKOUT_MINUTES% ciclo(s); reserva vai assumir agora para manter o sistema online. >> "%LOGFILE%"
    call :event INFO ASSUMIR "Nenhum servidor respondeu; reserva vai assumir agora. Ciclos pretos=%BLACKOUT_MINUTES%."
    call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    set "RC=%errorlevel%"
    if not "!RC!"=="0" call :event ERRO ASSUMIR "Reserva falhou ao iniciar. Codigo=!RC!."
    exit /b !RC!
)

exit /b 0

:health
curl -fsS --max-time 3 "http://%~1:%API_PORT%/health" >nul 2>&1
exit /b %errorlevel%

:blackout_minutes
set "BLACKOUT_COUNT=0"
if exist "%BLACKOUT_FILE%" set /p BLACKOUT_COUNT=<"%BLACKOUT_FILE%"
set /a BLACKOUT_COUNT=BLACKOUT_COUNT+1
if %BLACKOUT_COUNT% GTR 120 set "BLACKOUT_COUNT=1"
>"%BLACKOUT_FILE%" echo %BLACKOUT_COUNT%
exit /b %BLACKOUT_COUNT%

:request_primary_start
echo %COMPUTERNAME% %USERNAME% %date% %time% > "%PRIMARY_REQUEST_FILE%" 2>nul
schtasks /Run /S %PRIMARY_IP% /TN "Dark-Jutsu Guardiao Servidor" >> "%LOGFILE%" 2>&1
if %errorlevel%==0 (
    echo [%date% %time%] Pedido remoto enviado para tarefa da principal. >> "%LOGFILE%"
) else (
    echo [%date% %time%] AVISO: nao conseguiu acionar tarefa remota da principal; pedido ficou registrado em %PRIMARY_REQUEST_FILE%. >> "%LOGFILE%"
)
exit /b 0

:event
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "%~1" "%~2" "%~3"
exit /b 0


