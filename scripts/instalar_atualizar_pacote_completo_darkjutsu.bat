@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SHARE_SCRIPTS=%SHARE_ROOT%\scripts"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\instalador_pacote_completo.log"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "LOCAL_IP="
set "ROLE=DESCONHECIDO"
set "FAILS=0"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul

echo ==================================================
echo Dark-Jutsu - Instalador pacote completo
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.
call :log "==== inicio pacote completo usuario=%USERNAME% maquina=%COMPUTERNAME% ===="

echo [1. Detectando papel pelo IP]
ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if !errorlevel!==0 (
  set "LOCAL_IP=%PRIMARY_IP%"
  set "ROLE=PRINCIPAL"
)
if "%LOCAL_IP%"=="" (
  ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
  if !errorlevel!==0 (
    set "LOCAL_IP=%RESERVE_IP%"
    set "ROLE=RESERVA"
  )
)
if "%LOCAL_IP%"=="" (
  call :fail "Esta maquina nao e principal nem reserva. IP local nao bate com %PRIMARY_IP% ou %RESERVE_IP%."
  goto finish
)
call :ok "IP=%LOCAL_IP%; papel=%ROLE%."

echo.
echo [2. Acesso ao servidor de arquivos]
if not exist "%SHARE_SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat" (
  call :fail "Nao achei instalador no fileserver: %SHARE_SCRIPTS%"
  goto finish
)
call :ok "Fileserver acessivel."

echo.
echo [3. Instalando/atualizando guardiao, monitor, inicializadores e API local]
call "%SHARE_SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat"
if errorlevel 1 (
  call :fail "Instalador guardiao/monitor/API retornou erro."
  goto finish
)
call :ok "Guardiao, monitor, inicializadores e API local atualizados."

echo.
echo [4. Autoatualizador local]
if exist "%SHARE_SCRIPTS%\verificar_atualizar_instalacao_local_darkjutsu.bat" (
  call "%SHARE_SCRIPTS%\verificar_atualizar_instalacao_local_darkjutsu.bat" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :warn "Autoatualizador local retornou aviso/erro. Veja %LOGFILE%."
  ) else (
    call :ok "Autoatualizador local verificado."
  )
) else (
  call :warn "Script de autoatualizacao local nao encontrado."
)

echo.
echo [5. Rotina de banco conforme papel]
if "%ROLE%"=="PRINCIPAL" (
  if exist "%SHARE_SCRIPTS%\backup_postgres_darkjutsu.bat" (
    call "%SHARE_SCRIPTS%\backup_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
      call :warn "Backup imediato nao concluiu agora. Se a API ainda estiver subindo, o guardiao tentara depois."
    ) else (
      call :ok "Backup seguro validado/verificado no principal."
    )
  )
) else (
  if exist "%SHARE_SCRIPTS%\restaurar_backup_reserva_darkjutsu.bat" (
    call "%SHARE_SCRIPTS%\restaurar_backup_reserva_darkjutsu.bat" >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
      call :warn "Restore preventivo do reserva retornou aviso/erro. Veja %LOGFILE%."
    ) else (
      call :ok "Reserva verificada com backup valido quando aplicavel."
    )
  )
)

echo.
echo [6. Status final compartilhado]
set "PYDIR=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python"
if exist "%PYDIR%\python.exe" if exist "%SHARE_SCRIPTS%\status_compartilhado_servidores_darkjutsu.py" (
  "%PYDIR%\python.exe" "%SHARE_SCRIPTS%\status_compartilhado_servidores_darkjutsu.py"
) else (
  call :warn "Nao consegui abrir status compartilhado por falta de Python local ou script."
)

:finish
echo.
echo ==================================================
if "%FAILS%"=="0" (
  echo RESULTADO: OK
  call :log "RESULTADO OK pacote completo papel=%ROLE% ip=%LOCAL_IP%"
) else (
  echo RESULTADO: FALHOU com %FAILS% erro(s)
  call :log "RESULTADO FALHOU fails=%FAILS% papel=%ROLE% ip=%LOCAL_IP%"
)
echo Log: %LOGFILE%
echo Papel: %ROLE% - %LOCAL_IP%
echo ==================================================
exit /b %FAILS%

:ok
echo OK: %~1
call :log "OK: %~1"
exit /b 0

:warn
echo AVISO: %~1
call :log "AVISO: %~1"
exit /b 0

:fail
set /a FAILS+=1
echo FALHOU: %~1
call :log "FALHOU: %~1"
exit /b 0

:log
echo [%date% %time%] %~1 >> "%LOGFILE%" 2>nul
exit /b 0
