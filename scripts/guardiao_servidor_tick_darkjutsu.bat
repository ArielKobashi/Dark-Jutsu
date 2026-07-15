@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "HEALTH_TIMEOUT=8"
set "BLACKOUT_PRIMARY_MIN_CYCLES=4"
set "BLACKOUT_RESERVE_MIN_CYCLES=5"
set "BLACKOUT_FILE=%SHARE_ROOT%\servidor-preto-contador.txt"
set "PRIMARY_REQUEST_FILE=%SHARE_ROOT%\solicitar-principal.txt"
set "OLD_PAUSE_FILE=%SHARE_ROOT%\principal-pausado-ate.txt"
set "LOGDIR=C:\DarkJutsu\logs"
set "EVENT_LOGGER=%SHARE_ROOT%\scripts\registrar_evento_servidor_darkjutsu.bat"
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"
set "LOCKFILE=%LOGDIR%\guardiao_tick.lock"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if exist "%LOCKFILE%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Get-Item -LiteralPath '%LOCKFILE%' -ErrorAction SilentlyContinue).LastWriteTime -lt (Get-Date).AddMinutes(-2)){ exit 0 } else { exit 1 }" >nul 2>&1
  if errorlevel 1 (
    >> "%LOGFILE%" echo [%date% %time%] AVISO: tick anterior ainda em andamento; evitando execucao sobreposta.
    exit /b 0
  )
  del "%LOCKFILE%" >nul 2>&1
)
>"%LOCKFILE%" echo %COMPUTERNAME% %USERNAME% %date% %time%

echo ==================================================
echo Dark-Jutsu - Verificacao do guardiao
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.
>> "%LOGFILE%" echo [%date% %time%] INICIO tick guardiao. Usuario=%USERNAME% Maquina=%COMPUTERNAME%.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "GUARDIAO" "Inicio do tick do guardiao."

set "LOCAL_IP="
ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if %errorlevel%==0 set "LOCAL_IP=%PRIMARY_IP%"
if "%LOCAL_IP%"=="" (
    ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
    if !errorlevel!==0 set "LOCAL_IP=%RESERVE_IP%"
)

if "%LOCAL_IP%"=="" (
    echo FALHOU: esta maquina nao tem IP de principal/reserva.
    >> "%LOGFILE%" echo [%date% %time%] FALHOU: maquina sem IP de principal/reserva. Guardiao nao vai agir.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "GUARDIAO" "Maquina sem IP de principal/reserva; guardiao nao age."
    del "%LOCKFILE%" >nul 2>&1
    exit /b 0
)
if "%LOCAL_IP%"=="%PRIMARY_IP%" (set "LOCAL_ROLE=PRINCIPAL") else (set "LOCAL_ROLE=RESERVA")
>> "%LOGFILE%" echo [%date% %time%] Papel detectado: %LOCAL_ROLE%; IP local=%LOCAL_IP%.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "GUARDIAO" "Papel detectado=%LOCAL_ROLE%; IP=%LOCAL_IP%."

>> "%LOGFILE%" echo [%date% %time%] Health principal: http://%PRIMARY_IP%:%API_PORT%/health timeout=%HEALTH_TIMEOUT%s
curl -fsS --max-time %HEALTH_TIMEOUT% "http://%PRIMARY_IP%:%API_PORT%/health" >nul 2>&1
set "PRIMARY_OK=%errorlevel%"
>> "%LOGFILE%" echo [%date% %time%] Resultado health principal=%PRIMARY_OK%.
set "PRIMARY_HEALTH=%PRIMARY_OK%"
curl -fsS --max-time 2 "http://%PRIMARY_IP%:%API_PORT%/live" >nul 2>&1
set "PRIMARY_LIVE=%errorlevel%"
>> "%LOGFILE%" echo [%date% %time%] Resultado live principal=%PRIMARY_LIVE%.
if not "%PRIMARY_HEALTH%"=="0" if "%PRIMARY_LIVE%"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] AVISO: principal respondeu /live mas /health falhou; API viva, banco/health degradado. Health original=%PRIMARY_HEALTH%.
    set "PRIMARY_OK=0"
)
if not "%PRIMARY_OK%"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] DETALHE health principal falhou; curl verbose inicio.
    curl -v --max-time %HEALTH_TIMEOUT% "http://%PRIMARY_IP%:%API_PORT%/health" >> "%LOGFILE%" 2>&1
    >> "%LOGFILE%" echo [%date% %time%] DETALHE health principal falhou; curl verbose fim.
)
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "HEALTH" "Principal %PRIMARY_IP% respondeu codigo curl=%PRIMARY_OK%."

if "%PRIMARY_OK%"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] Tick guardiao CMD. Local=%LOCAL_IP% papel=%LOCAL_ROLE% principal=%PRIMARY_OK% principal_live=%PRIMARY_LIVE% reserva=SKIP.
    echo OK: principal respondeu. Nao precisa testar reserva nem assumir.
    >> "%LOGFILE%" echo [%date% %time%] DECISAO: principal online. Limpando estado preto e pedido remoto.
    del "%BLACKOUT_FILE%" >nul 2>&1
    del "%PRIMARY_REQUEST_FILE%" >nul 2>&1
    if not "%LOCAL_IP%"=="%PRIMARY_IP%" (
        >> "%LOGFILE%" echo [%date% %time%] DECISAO: este PC e reserva; garantindo API local parada.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "GUARDIAO" "Principal respondeu; reserva deve parar API local se estiver ativa."
        call "%SHARE_ROOT%\scripts\parar_api_darkjutsu.bat" "guardiao_principal_online" >nul 2>&1
        >> "%LOGFILE%" echo [%date% %time%] parar_api_darkjutsu retornou codigo !errorlevel!.
    )
    >> "%LOGFILE%" echo [%date% %time%] FIM tick: principal ativa; nenhuma assuncao.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "GUARDIAO" "Principal ativa. Nenhuma assuncao necessaria."
    del "%LOCKFILE%" >nul 2>&1
    exit /b 0
)

>> "%LOGFILE%" echo [%date% %time%] Health reserva: http://%RESERVE_IP%:%API_PORT%/health timeout=%HEALTH_TIMEOUT%s
curl -fsS --max-time %HEALTH_TIMEOUT% "http://%RESERVE_IP%:%API_PORT%/health" >nul 2>&1
set "RESERVE_OK=%errorlevel%"
>> "%LOGFILE%" echo [%date% %time%] Resultado health reserva=%RESERVE_OK%.
set "RESERVE_HEALTH=%RESERVE_OK%"
curl -fsS --max-time 2 "http://%RESERVE_IP%:%API_PORT%/live" >nul 2>&1
set "RESERVE_LIVE=%errorlevel%"
>> "%LOGFILE%" echo [%date% %time%] Resultado live reserva=%RESERVE_LIVE%.
if not "%RESERVE_HEALTH%"=="0" if "%RESERVE_LIVE%"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] AVISO: reserva respondeu /live mas /health falhou; API viva, banco/health degradado. Health original=%RESERVE_HEALTH%.
    set "RESERVE_OK=0"
)
if not "%RESERVE_OK%"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] DETALHE health reserva falhou; curl verbose inicio.
    curl -v --max-time %HEALTH_TIMEOUT% "http://%RESERVE_IP%:%API_PORT%/health" >> "%LOGFILE%" 2>&1
    >> "%LOGFILE%" echo [%date% %time%] DETALHE health reserva falhou; curl verbose fim.
)
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "HEALTH" "Reserva %RESERVE_IP% respondeu codigo curl=%RESERVE_OK%."

>> "%LOGFILE%" echo [%date% %time%] Tick guardiao CMD. Local=%LOCAL_IP% papel=%LOCAL_ROLE% principal=%PRIMARY_OK% principal_live=%PRIMARY_LIVE% reserva=%RESERVE_OK% reserva_live=%RESERVE_LIVE%.
echo IP local: %LOCAL_IP%
echo Principal %PRIMARY_IP%: %PRIMARY_OK%
echo Reserva   %RESERVE_IP%: %RESERVE_OK%
echo.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "GUARDIAO" "Tick. Local=%LOCAL_IP%; principal=%PRIMARY_OK%; reserva=%RESERVE_OK%."

if "%PRIMARY_OK%"=="0" (
    echo OK: principal respondeu. Nao precisa assumir.
    >> "%LOGFILE%" echo [%date% %time%] DECISAO: principal online. Limpando estado preto e pedido remoto.
    del "%BLACKOUT_FILE%" >nul 2>&1
    del "%PRIMARY_REQUEST_FILE%" >nul 2>&1
    if not "%LOCAL_IP%"=="%PRIMARY_IP%" (
        >> "%LOGFILE%" echo [%date% %time%] DECISAO: este PC e reserva; garantindo API local parada.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "GUARDIAO" "Principal respondeu; reserva deve parar API local se estiver ativa."
        call "%SHARE_ROOT%\scripts\parar_api_darkjutsu.bat" "guardiao_principal_online" >nul 2>&1
        >> "%LOGFILE%" echo [%date% %time%] parar_api_darkjutsu retornou codigo !errorlevel!.
    )
    >> "%LOGFILE%" echo [%date% %time%] FIM tick: principal ativa; nenhuma assuncao.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "GUARDIAO" "Principal ativa. Nenhuma assuncao necessaria."
    del "%LOCKFILE%" >nul 2>&1
    exit /b 0
)

if "%RESERVE_OK%"=="0" (
    echo OK: reserva respondeu.
    >> "%LOGFILE%" echo [%date% %time%] DECISAO: reserva online e principal offline.
    del "%BLACKOUT_FILE%" >nul 2>&1
    del "%PRIMARY_REQUEST_FILE%" >nul 2>&1
    if "%LOCAL_IP%"=="%PRIMARY_IP%" (
        del "%OLD_PAUSE_FILE%" >nul 2>&1
        >> "%LOGFILE%" echo [%date% %time%] FAILBACK: este PC e principal; tentando reassumir da reserva.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "FAILBACK" "Reserva respondeu e principal esta livre; principal vai reassumir."
        call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
        set "RC=!errorlevel!"
        >> "%LOGFILE%" echo [%date% %time%] Resultado failback principal: codigo=!RC!.
        if not "!RC!"=="0" if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "FAILBACK" "Principal tentou reassumir, mas falhou. Codigo=!RC!."
        if "!RC!"=="0" if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "FAILBACK" "Principal reassumiu com sucesso."
        del "%LOCKFILE%" >nul 2>&1
        exit /b !RC!
    ) else (
        >> "%LOGFILE%" echo [%date% %time%] RESERVA: reserva esta ativa; solicitando que o principal tente reassumir se estiver ligado.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "FAILBACK" "Reserva ativa; enviando pedido para principal tentar reassumir."
        echo %COMPUTERNAME% %USERNAME% %date% %time% > "%PRIMARY_REQUEST_FILE%" 2>nul
        schtasks /Run /S %PRIMARY_IP% /TN "Dark-Jutsu Guardiao Servidor" >> "%LOGFILE%" 2>&1
        if !errorlevel!==0 (
            >> "%LOGFILE%" echo [%date% %time%] Pedido remoto enviado para tarefa da principal.
            if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "FAILBACK" "Pedido remoto enviado para tarefa do principal via schtasks."
        ) else (
            >> "%LOGFILE%" echo [%date% %time%] AVISO: nao conseguiu acionar tarefa remota da principal; pedido ficou registrado em %PRIMARY_REQUEST_FILE%.
            if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "FAILBACK" "Nao consegui acionar tarefa remota do principal via schtasks; pedido ficou registrado no fileserver."
        )
        >> "%LOGFILE%" echo [%date% %time%] FIM tick: reserva ativa nesta maquina; aguardando principal voltar.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "GUARDIAO" "Reserva ativa nesta maquina. Aguardando principal voltar."
        del "%LOCKFILE%" >nul 2>&1
        exit /b 0
    )
)

>> "%LOGFILE%" echo [%date% %time%] ALERTA: nenhum health respondeu. Principal=%PRIMARY_OK%; Reserva=%RESERVE_OK%.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "PRETO" "Nenhum servidor respondeu. Local=%LOCAL_IP%; papel=%LOCAL_ROLE%; principal=%PRIMARY_OK%; reserva=%RESERVE_OK%."

set "BLACKOUT_COUNT=0"
if exist "%BLACKOUT_FILE%" set /p BLACKOUT_COUNT=<"%BLACKOUT_FILE%"
set /a BLACKOUT_COUNT=BLACKOUT_COUNT+1
if %BLACKOUT_COUNT% GTR 120 set "BLACKOUT_COUNT=1"
>"%BLACKOUT_FILE%" echo %BLACKOUT_COUNT%
set "BLACKOUT_MINUTES=%BLACKOUT_COUNT%"
>> "%LOGFILE%" echo [%date% %time%] Contador preto=%BLACKOUT_MINUTES% ciclo(s).

if "%LOCAL_IP%"=="%PRIMARY_IP%" (
    if %BLACKOUT_MINUTES% LSS %BLACKOUT_PRIMARY_MIN_CYCLES% (
        >> "%LOGFILE%" echo [%date% %time%] PRINCIPAL: falha isolada ha %BLACKOUT_MINUTES% ciclo(s); aguardando %BLACKOUT_PRIMARY_MIN_CYCLES% ciclos antes de assumir para evitar falso positivo.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "PRETO" "Principal ainda nao vai reiniciar: falha ha %BLACKOUT_MINUTES% ciclo(s), precisa de %BLACKOUT_PRIMARY_MIN_CYCLES%."
        del "%LOCKFILE%" >nul 2>&1
        exit /b 0
    )
    echo ACAO: nenhum servidor respondeu; principal vai iniciar agora.
    >> "%LOGFILE%" echo [%date% %time%] DECISAO: principal vai assumir porque nenhum servidor respondeu.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "ASSUMIR" "Nenhum servidor respondeu; principal vai iniciar imediatamente."
    call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    set "RC=!errorlevel!"
    >> "%LOGFILE%" echo [%date% %time%] Resultado assumir principal: codigo=!RC!.
    if not "!RC!"=="0" if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "ASSUMIR" "Principal falhou ao iniciar. Codigo=!RC!."
    if "!RC!"=="0" if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "ASSUMIR" "Principal iniciou com sucesso apos tela preta."
    del "%LOCKFILE%" >nul 2>&1
    exit /b !RC!
)

if "%LOCAL_IP%"=="%RESERVE_IP%" (
    echo ACAO: nenhum servidor respondeu; reserva vai aguardar confirmacao antes de assumir.
    >> "%LOGFILE%" echo [%date% %time%] RESERVA: antes de assumir, enviando pedido para principal tentar iniciar/reassumir.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "FAILBACK" "Nenhum servidor respondeu; reserva vai pedir principal e aguardar confirmacao para evitar falso positivo."
    echo %COMPUTERNAME% %USERNAME% %date% %time% > "%PRIMARY_REQUEST_FILE%" 2>nul
    schtasks /Run /S %PRIMARY_IP% /TN "Dark-Jutsu Guardiao Servidor" >> "%LOGFILE%" 2>&1
    if !errorlevel!==0 (
        >> "%LOGFILE%" echo [%date% %time%] Pedido remoto enviado para tarefa da principal.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "FAILBACK" "Pedido remoto enviado para tarefa do principal via schtasks."
    ) else (
        >> "%LOGFILE%" echo [%date% %time%] AVISO: nao conseguiu acionar tarefa remota da principal; pedido ficou registrado em %PRIMARY_REQUEST_FILE%.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "FAILBACK" "Nao consegui acionar tarefa remota do principal via schtasks; pedido ficou registrado no fileserver."
    )
    if %BLACKOUT_MINUTES% LSS %BLACKOUT_RESERVE_MIN_CYCLES% (
        >> "%LOGFILE%" echo [%date% %time%] RESERVA: tela preta ha %BLACKOUT_MINUTES% ciclo(s). Aguardando %BLACKOUT_RESERVE_MIN_CYCLES% ciclos antes de assumir.
        if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "PRETO" "Reserva ainda nao vai assumir: tela preta ha %BLACKOUT_MINUTES% ciclo(s), precisa de %BLACKOUT_RESERVE_MIN_CYCLES%."
        del "%LOCKFILE%" >nul 2>&1
        exit /b 0
    )
    >> "%LOGFILE%" echo [%date% %time%] DECISAO: reserva vai assumir porque nenhum servidor respondeu.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "ASSUMIR" "Nenhum servidor respondeu; reserva vai assumir agora. Ciclos pretos=%BLACKOUT_MINUTES%."
    call "%SHARE_ROOT%\scripts\assumir_servidor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    set "RC=!errorlevel!"
    >> "%LOGFILE%" echo [%date% %time%] Resultado assumir reserva: codigo=!RC!.
    if not "!RC!"=="0" if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "ASSUMIR" "Reserva falhou ao iniciar. Codigo=!RC!."
    if "!RC!"=="0" if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "ASSUMIR" "Reserva iniciou com sucesso apos tela preta."
    del "%LOCKFILE%" >nul 2>&1
    exit /b !RC!
)

>> "%LOGFILE%" echo [%date% %time%] FIM tick sem acao: IP local nao casou com principal/reserva apos health.
del "%LOCKFILE%" >nul 2>&1
exit /b 0
