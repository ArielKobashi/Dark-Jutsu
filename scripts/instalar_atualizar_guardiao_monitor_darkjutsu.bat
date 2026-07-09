@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SHARE_SCRIPTS=%SHARE_ROOT%\scripts"
set "PY_SOURCE=%SHARE_ROOT%\instaladores\WPy64-3.13.12.0"
set "PY_TARGET=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0"
set "MACHINE_APP_ROOT=C:\DarkJutsu\Dark-Jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "LOCAL_SCRIPTS=%LOCALAPPDATA%\DarkJutsu\monitor"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "DESKTOP=%USERPROFILE%\Desktop"
set "LOGDIR=C:\DarkJutsu\logs"
set "INSTALL_LOG=%LOGDIR%\instalador_guardiao_monitor.log"
set "SUMMARY=%TEMP%\darkjutsu_instalador_%RANDOM%_%RANDOM%.txt"
set "MONITOR_RUN_NAME=Dark-Jutsu Monitor Servidor"
set "GUARDIAN_RUN_NAME=Dark-Jutsu Guardiao Servidor"
set "MONITOR_TASK_NAME=Dark-Jutsu Monitor Servidor"
set "GUARDIAN_TASK_NAME=Dark-Jutsu Guardiao Servidor"
set "FAIL_COUNT=0"
set "WARN_COUNT=0"
set "MONITOR_AUTOSTART=0"
set "GUARDIAN_AUTOSTART=0"
set "LOCAL_IP="
set "SERVER_ROLE="
set "MONITOR_KIND="
set "MONITOR_START_CMD="
set "MONITOR_PROCESS_MATCH="

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%LOGDIR%" (
  echo FALHOU: nao consegui criar C:\DarkJutsu\logs
  pause
  exit /b 1
)

>"%SUMMARY%" echo.
call :log "=================================================="
call :log "Instalador unico Guardiao + Monitor Dark-Jutsu"
call :log "Usuario=%USERNAME% Maquina=%COMPUTERNAME%"
call :log "=================================================="

echo ==================================================
echo Dark-Jutsu - Guardiao + Monitor
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.

call :step "0. Detectar papel pelo IP"
call :detect_role
if "%SERVER_ROLE%"=="" goto finish
call :ok "IP=%LOCAL_IP%; papel=%SERVER_ROLE%; monitor=%MONITOR_KIND%."

call :step "1. Acesso ao servidor de arquivos"
if exist "%SHARE_SCRIPTS%\guardiao_servidor_tick_darkjutsu.bat" (
  call :ok "Servidor de arquivos acessivel."
) else (
  call :fail "Nao achei os scripts em %SHARE_SCRIPTS%."
  goto finish
)

call :step "2. Arquivos obrigatorios"
call :require_source "guardiao_servidor_tick_darkjutsu.bat"
call :require_source "registrar_evento_servidor_darkjutsu.bat"
call :require_source "limpar_log_72h_darkjutsu.py"
call :require_source "testar_servidor_darkjutsu.bat"
call :require_source "assumir_servidor_darkjutsu.bat"
call :require_source "tornar_principal_operacional_darkjutsu.bat"
call :require_source "tornar_reserva_operacional_darkjutsu.bat"
call :require_source "parar_api_darkjutsu.bat"
if "%MONITOR_KIND%"=="POWERSHELL" (
  call :require_source "monitor_principal_powershell_darkjutsu.ps1"
  call :require_source "iniciar_monitor_principal_powershell_oculto.vbs"
) else (
  call :require_source "monitor_reserva_python_darkjutsu.py"
  call :require_source "iniciar_monitor_reserva_python_darkjutsu.bat"
  call :require_source "diagnosticar_monitor_reserva_python_darkjutsu.bat"
  if exist "%PY_SOURCE%\python\python.exe" (
    call :log "Encontrado: Python portatil na rede."
  ) else (
    call :fail "Python portatil ausente na rede: %PY_SOURCE%"
  )
)
if not "%FAIL_COUNT%"=="0" goto finish
call :ok "Arquivos obrigatorios encontrados."

call :step "3. Pasta local do usuario"
if not exist "%LOCAL_SCRIPTS%" mkdir "%LOCAL_SCRIPTS%" 2>nul
if exist "%LOCAL_SCRIPTS%" (
  call :ok "Pasta local pronta: %LOCAL_SCRIPTS%"
) else (
  call :fail "Nao consegui criar a pasta local: %LOCAL_SCRIPTS%"
  goto finish
)

if "%MONITOR_KIND%"=="PYTHON" (
  call :step "3b. Python portatil do usuario reserva"
  call :ensure_python_reserve
  if not "%FAIL_COUNT%"=="0" goto finish
)

call :step "3c. Copia estavel da API para todos os usuarios"
call :ensure_machine_api_copy
if not "%FAIL_COUNT%"=="0" goto finish

call :step "4. Instalar arquivos do monitor correto"
if "%MONITOR_KIND%"=="PYTHON" (
  call :copy_file "monitor_reserva_python_darkjutsu.py"
  call :copy_file "iniciar_monitor_reserva_python_darkjutsu.bat"
  call :copy_file "diagnosticar_monitor_reserva_python_darkjutsu.bat"
  if exist "%SHARE_SCRIPTS%\icons" (
    robocopy "%SHARE_SCRIPTS%\icons" "%LOCAL_SCRIPTS%\icons" /E /NFL /NDL /NP /R:1 /W:1 >> "%INSTALL_LOG%" 2>&1
    if errorlevel 8 (
      call :warn "Robocopy dos icones retornou erro. O monitor ainda pode usar icone gerado."
    ) else (
      call :ok "Icones atualizados."
    )
  ) else (
    call :warn "Pasta de icones nao encontrada. O monitor Python vai gerar icone padrao."
  )
  set "MONITOR_START_CMD=%LOCAL_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat"
  set "MONITOR_PROCESS_MATCH=monitor_reserva_python_darkjutsu.py"
) else (
  call :ok "Principal usa monitor PowerShell direto da rede."
  set "MONITOR_START_CMD=wscript.exe //B %SHARE_SCRIPTS%\iniciar_monitor_principal_powershell_oculto.vbs"
  set "MONITOR_PROCESS_MATCH=monitor_principal_powershell_darkjutsu.ps1"
)
if not "%FAIL_COUNT%"=="0" goto finish

call :step "5. Comandos locais dos botoes"
if "%MONITOR_KIND%"=="PYTHON" (
  call :make_wrapper "testar_servidor_darkjutsu.bat" 1
  call :make_wrapper "guardiao_servidor_tick_darkjutsu.bat" 1
  call :make_wrapper "tornar_reserva_operacional_darkjutsu.bat" 0
  call :make_wrapper "tornar_principal_operacional_darkjutsu.bat" 0
  call :make_wrapper "assumir_servidor_darkjutsu.bat" 0
  call :make_wrapper "parar_api_darkjutsu.bat" 0
  call :check_file "%LOCAL_SCRIPTS%\run_testar_servidor_darkjutsu.cmd" "Wrapper Testar servidor"
  call :check_file "%LOCAL_SCRIPTS%\run_guardiao_servidor_tick_darkjutsu.cmd" "Wrapper Verificar/iniciar agora"
) else (
  call :ok "Principal usa botoes internos do monitor PowerShell."
)
if not "%FAIL_COUNT%"=="0" goto finish

call :step "6. Guardiao local em loop escondido"
call :make_guardian_loop
call :check_file "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" "Guardiao local em loop"
if not "%FAIL_COUNT%"=="0" goto finish

call :step "7. Encerrar versao antiga deste papel"
if "%MONITOR_KIND%"=="PYTHON" (
  wmic process where "CommandLine like '%%monitor%%darkjutsu%%py%%'" call terminate >> "%INSTALL_LOG%" 2>&1
) else (
  wmic process where "CommandLine like '%%monitor_principal_powershell_darkjutsu.ps1%%'" call terminate >> "%INSTALL_LOG%" 2>&1
)
wmic process where "CommandLine like '%%guardiao_loop_darkjutsu%%'" call terminate >> "%INSTALL_LOG%" 2>&1
call :ok "Tentativa de encerramento concluida."

call :step "8. Inicializacao automatica"
call :install_autostart

call :step "9. Iniciar guardiao agora"
wscript.exe //B "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" >> "%INSTALL_LOG%" 2>&1
timeout /t 2 /nobreak >nul
call :process_check "guardiao_loop_darkjutsu" "Guardiao em loop"

call :step "10. Iniciar monitor correto agora"
if "%MONITOR_KIND%"=="PYTHON" (
  call "%LOCAL_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat" >> "%INSTALL_LOG%" 2>&1
) else (
  wscript.exe //B "%SHARE_SCRIPTS%\iniciar_monitor_principal_powershell_oculto.vbs" >> "%INSTALL_LOG%" 2>&1
)
timeout /t 4 /nobreak >nul
call :process_check "%MONITOR_PROCESS_MATCH%" "Monitor %MONITOR_KIND%"

call :step "11. Checks finais"
if "%MONITOR_KIND%"=="PYTHON" (
  call :check_file "%LOCAL_SCRIPTS%\monitor_reserva_python_darkjutsu.py" "Script Python local"
  call :check_file "%LOCAL_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat" "Launcher Python local"
  call :check_file "%LOCAL_SCRIPTS%\run_testar_servidor_darkjutsu.cmd" "Botao Testar local"
) else (
  call :check_file "%SHARE_SCRIPTS%\monitor_principal_powershell_darkjutsu.ps1" "Script PowerShell da principal"
  call :check_file "%SHARE_SCRIPTS%\iniciar_monitor_principal_powershell_oculto.vbs" "Launcher oculto PowerShell"
)
call :check_file "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" "Loop local"
call :check_autostart_summary

goto finish

:detect_role
ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if %errorlevel%==0 (
  set "LOCAL_IP=%PRIMARY_IP%"
  set "SERVER_ROLE=PRINCIPAL"
  set "MONITOR_KIND=POWERSHELL"
  exit /b 0
)
ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
if %errorlevel%==0 (
  set "LOCAL_IP=%RESERVE_IP%"
  set "SERVER_ROLE=RESERVA"
  set "MONITOR_KIND=PYTHON"
  exit /b 0
)
call :fail "Esta maquina nao tem IP de principal (%PRIMARY_IP%) nem reserva (%RESERVE_IP%). Nada foi instalado para evitar versao errada."
exit /b 0

:step
echo.
echo [%~1]
call :log "[%~1]"
exit /b 0

:log
>>"%INSTALL_LOG%" echo [%date% %time%] %~1
exit /b 0

:summary
>>"%SUMMARY%" echo %~1
exit /b 0

:ok
echo OK: %~1
call :log "OK: %~1"
call :summary "OK: %~1"
exit /b 0

:warn
set /a WARN_COUNT+=1
echo AVISO: %~1
call :log "AVISO: %~1"
call :summary "AVISO: %~1"
exit /b 0

:fail
set /a FAIL_COUNT+=1
echo FALHOU: %~1
call :log "FALHOU: %~1"
call :summary "FALHOU: %~1"
exit /b 0

:require_source
if exist "%SHARE_SCRIPTS%\%~1" (
  call :log "Encontrado: %~1"
) else (
  call :fail "Arquivo ausente na rede: %~1"
)
exit /b 0

:copy_file
attrib -R "%LOCAL_SCRIPTS%\%~1" 2>nul
copy /Y "%SHARE_SCRIPTS%\%~1" "%LOCAL_SCRIPTS%\%~1" >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (
  call :fail "Nao consegui copiar %~1 para %LOCAL_SCRIPTS%."
) else (
  call :ok "Copiado/atualizado: %~1"
)
exit /b 0

:ensure_python_reserve
if exist "%PY_TARGET%\python\python.exe" (
  call :ok "Python portatil ja existe neste usuario."
  exit /b 0
)
if not exist "%USERPROFILE%\Desktop\aplicacoes code" mkdir "%USERPROFILE%\Desktop\aplicacoes code" 2>nul
if not exist "%USERPROFILE%\Desktop\aplicacoes code" (
  call :fail "Nao consegui criar a pasta: %USERPROFILE%\Desktop\aplicacoes code"
  exit /b 0
)
call :warn "Python portatil nao existia neste usuario. Copiando da rede, pode demorar."
robocopy "%PY_SOURCE%" "%PY_TARGET%" /E /R:2 /W:2 /NFL /NDL /NP >> "%INSTALL_LOG%" 2>&1
if errorlevel 8 (
  call :fail "Falha ao copiar Python portatil para %PY_TARGET%."
  exit /b 0
)
if exist "%PY_TARGET%\python\python.exe" (
  call :ok "Python portatil copiado para este usuario."
) else (
  call :fail "Copia do Python terminou, mas python.exe nao apareceu em %PY_TARGET%."
)
exit /b 0

:ensure_machine_api_copy
if not exist "%SHARE_ROOT%\pacote\Dark-Jutsu\api\iniciar_api_servidor.bat" (
  call :fail "API nao encontrada no pacote da rede: %SHARE_ROOT%\pacote\Dark-Jutsu\api"
  exit /b 0
)
if not exist "%MACHINE_APP_ROOT%" mkdir "%MACHINE_APP_ROOT%" 2>nul
if not exist "%MACHINE_APP_ROOT%" (
  call :fail "Nao consegui criar %MACHINE_APP_ROOT%."
  exit /b 0
)
robocopy "%SHARE_ROOT%\pacote\Dark-Jutsu\api" "%MACHINE_APP_ROOT%\api" /E /R:2 /W:2 /NFL /NDL /NP >> "%INSTALL_LOG%" 2>&1
if errorlevel 8 (
  call :fail "Falha ao copiar API para %MACHINE_APP_ROOT%\api."
  exit /b 0
)
if exist "%MACHINE_APP_ROOT%\api\iniciar_api_servidor.bat" (
  call :ok "API estavel pronta em %MACHINE_APP_ROOT%\api."
) else (
  call :fail "Copia da API terminou, mas iniciar_api_servidor.bat nao apareceu."
)
exit /b 0

:check_file
if exist "%~1" (
  call :ok "%~2 pronto."
) else (
  call :fail "%~2 nao encontrado em %~1."
)
exit /b 0

:make_wrapper
set "BAT_NAME=%~1"
set "PAUSE_ON_FINISH=%~2"
set "WRAP_NAME=run_%BAT_NAME:.bat=.cmd%"
(
  echo @echo off
  echo setlocal EnableExtensions
  echo echo Dark-Jutsu - %%~n0
  echo echo Pasta da rede: "%SHARE_SCRIPTS%"
  echo pushd "%SHARE_SCRIPTS%" 2^>nul
  echo if errorlevel 1 ^(
  echo   echo FALHOU: nao consegui acessar a pasta de scripts da rede.
  echo   echo "%SHARE_SCRIPTS%"
  echo   pause
  echo   exit /b 1
  echo ^)
  echo call "%BAT_NAME%"
  echo set "EC=%%ERRORLEVEL%%"
  echo popd
  if "%PAUSE_ON_FINISH%"=="1" echo echo.
  if "%PAUSE_ON_FINISH%"=="1" echo echo Comando finalizado. Codigo=%%EC%%
  if "%PAUSE_ON_FINISH%"=="1" echo pause
  echo exit /b %%EC%%
) > "%LOCAL_SCRIPTS%\%WRAP_NAME%" 2>> "%INSTALL_LOG%"
if exist "%LOCAL_SCRIPTS%\%WRAP_NAME%" (
  call :ok "Comando local criado: %WRAP_NAME%"
) else (
  call :fail "Nao consegui criar comando local: %WRAP_NAME%"
)
exit /b 0

:make_guardian_loop
(
  echo Set shell = CreateObject("WScript.Shell"^)
  echo Do
  echo   shell.Run "cmd /c ""%SHARE_SCRIPTS%\guardiao_servidor_tick_darkjutsu.bat""", 0, True
  echo   WScript.Sleep 60000
  echo Loop
) > "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" 2>> "%INSTALL_LOG%"
if exist "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" (
  call :ok "Guardiao local em loop criado."
) else (
  call :fail "Nao consegui criar o guardiao local em loop."
)
exit /b 0

:install_autostart
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%MONITOR_RUN_NAME%" /f >> "%INSTALL_LOG%" 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%GUARDIAN_RUN_NAME%" /f >> "%INSTALL_LOG%" 2>&1
del "%STARTUP%\Dark-Jutsu Monitor Servidor.cmd" >nul 2>&1
del "%STARTUP%\Dark-Jutsu Guardiao Servidor.cmd" >nul 2>&1
del "%STARTUP%\Dark-Jutsu monitor.cmd" >nul 2>&1
del "%STARTUP%\Dark-Jutsu guardiao.cmd" >nul 2>&1
schtasks /Delete /F /TN "%MONITOR_TASK_NAME%" >> "%INSTALL_LOG%" 2>&1
schtasks /Delete /F /TN "%GUARDIAN_TASK_NAME%" >> "%INSTALL_LOG%" 2>&1

call :install_one_autostart "%MONITOR_RUN_NAME%" "%MONITOR_TASK_NAME%" "%MONITOR_START_CMD%" "monitor"
call :install_one_autostart "%GUARDIAN_RUN_NAME%" "%GUARDIAN_TASK_NAME%" "wscript.exe //B %LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" "guardiao"

(
  echo @echo off
  echo %MONITOR_START_CMD%
  echo wscript.exe //B "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs"
) > "%DESKTOP%\Iniciar Dark-Jutsu Monitor.cmd" 2>> "%INSTALL_LOG%"
if exist "%DESKTOP%\Iniciar Dark-Jutsu Monitor.cmd" (
  call :ok "Iniciador manual criado na Area de Trabalho."
) else (
  call :warn "Nao consegui criar iniciador manual na Area de Trabalho."
)
exit /b 0

:install_one_autostart
set "RUN_NAME=%~1"
set "TASK_NAME=%~2"
set "RUN_CMD=%~3"
set "KIND=%~4"

reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "%RUN_NAME%" /t REG_SZ /d "%RUN_CMD%" /f >> "%INSTALL_LOG%" 2>&1
if not errorlevel 1 (
  if /I "%KIND%"=="monitor" set "MONITOR_AUTOSTART=1"
  if /I "%KIND%"=="guardiao" set "GUARDIAN_AUTOSTART=1"
  call :ok "%KIND% instalado no Registro HKCU Run."
  exit /b 0
)
call :warn "Registro HKCU Run bloqueou %KIND%."

(
  echo @echo off
  echo %RUN_CMD%
) > "%STARTUP%\Dark-Jutsu %KIND%.cmd" 2>> "%INSTALL_LOG%"
if exist "%STARTUP%\Dark-Jutsu %KIND%.cmd" (
  if /I "%KIND%"=="monitor" set "MONITOR_AUTOSTART=1"
  if /I "%KIND%"=="guardiao" set "GUARDIAN_AUTOSTART=1"
  call :ok "%KIND% instalado na pasta Inicializar."
  exit /b 0
)
call :warn "Pasta Inicializar bloqueou %KIND%."

schtasks /Create /F /TN "%TASK_NAME%" /SC ONLOGON /TR "%RUN_CMD%" >> "%INSTALL_LOG%" 2>&1
if not errorlevel 1 (
  if /I "%KIND%"=="monitor" set "MONITOR_AUTOSTART=1"
  if /I "%KIND%"=="guardiao" set "GUARDIAN_AUTOSTART=1"
  call :ok "%KIND% instalado como tarefa ao logon."
  exit /b 0
)
call :warn "Tarefa agendada ao logon bloqueou %KIND%."
exit /b 0

:process_check
wmic process where "CommandLine like '%%%~1%%'" get ProcessId 2>nul | findstr /R "[0-9]" >nul 2>&1
if errorlevel 1 (
  call :fail "%~2 nao apareceu como processo ativo."
) else (
  call :ok "%~2 esta rodando."
)
exit /b 0

:check_autostart_summary
if "%MONITOR_AUTOSTART%"=="1" (
  call :ok "Monitor tem pelo menos um caminho de inicializacao automatica."
) else (
  call :fail "Monitor nao conseguiu nenhum caminho de inicializacao automatica."
)
if "%GUARDIAN_AUTOSTART%"=="1" (
  call :ok "Guardiao tem pelo menos um caminho de inicializacao automatica."
) else (
  call :fail "Guardiao nao conseguiu nenhum caminho de inicializacao automatica."
)
exit /b 0

:finish
echo.
echo ==================================================
echo RESUMO FINAL
echo ==================================================
type "%SUMMARY%" 2>nul
echo.
if "%FAIL_COUNT%"=="0" (
  echo RESULTADO: OK
  call :log "RESULTADO: OK com %WARN_COUNT% aviso(s)."
) else (
  echo RESULTADO: FALHOU em %FAIL_COUNT% parte(s), com %WARN_COUNT% aviso(s).
  call :log "RESULTADO: FALHOU em %FAIL_COUNT% parte(s), com %WARN_COUNT% aviso(s)."
)
echo.
echo Log completo:
echo %INSTALL_LOG%
echo.
echo Papel detectado:
echo %SERVER_ROLE% - %MONITOR_KIND% - %LOCAL_IP%
echo.
echo Pasta local:
echo %LOCAL_SCRIPTS%
echo ==================================================
del "%SUMMARY%" >nul 2>&1
pause
if "%FAIL_COUNT%"=="0" exit /b 0
exit /b 1

