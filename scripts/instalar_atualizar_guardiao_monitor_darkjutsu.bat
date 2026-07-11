@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SHARE_SCRIPTS=%SHARE_ROOT%\scripts"
set "PY_SOURCE=%SHARE_ROOT%\instaladores\WPy64-3.13.12.0"
set "PY_TARGET=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0"
set "MACHINE_APP_ROOT=C:\DarkJutsu\Dark-Jutsu"
set "LOCAL_SCRIPTS=%LOCALAPPDATA%\DarkJutsu\monitor"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "DESKTOP=%USERPROFILE%\Desktop"
set "LOGDIR=C:\DarkJutsu\logs"
set "INSTALL_LOG=%LOGDIR%\instalador_guardiao_monitor.log"
set "SUMMARY=%TEMP%\darkjutsu_instalador_%RANDOM%_%RANDOM%.txt"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "FAIL_COUNT=0"
set "WARN_COUNT=0"
set "LOCAL_IP="
set "ROLE="
set "MONITOR_KIND="
set "MONITOR_CMD="
set "MONITOR_MATCH="

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%LOGDIR%" (
  echo FALHOU: nao consegui criar %LOGDIR%
  pause
  exit /b 1
)
>"%SUMMARY%" echo.

echo ==================================================
echo Dark-Jutsu - Instalador Guardiao + Monitor
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.
call :log "==== inicio instalador usuario=%USERNAME% maquina=%COMPUTERNAME% ===="

echo [0. Detectar papel pelo IP]
ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if !errorlevel!==0 (
  set "LOCAL_IP=%PRIMARY_IP%"
  set "ROLE=PRINCIPAL"
  set "MONITOR_KIND=POWERSHELL"
  set "MONITOR_CMD=wscript.exe //B %SHARE_SCRIPTS%\iniciar_monitor_principal_powershell_oculto.vbs"
  set "MONITOR_MATCH=monitor_principal_powershell_darkjutsu.ps1"
)
if "%LOCAL_IP%"=="" (
  ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
  if !errorlevel!==0 (
    set "LOCAL_IP=%RESERVE_IP%"
    set "ROLE=RESERVA"
    set "MONITOR_KIND=PYTHON"
    set "MONITOR_CMD=%LOCAL_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat"
    set "MONITOR_MATCH=monitor_reserva_python_darkjutsu.py"
  )
)
if "%LOCAL_IP%"=="" (
  call :fail "Esta maquina nao tem IP %PRIMARY_IP% nem %RESERVE_IP%. Nada instalado."
  goto finish
) else (
  call :ok "IP=%LOCAL_IP%; papel=%ROLE%; monitor=%MONITOR_KIND%."
)

echo.
echo [1. Acesso ao servidor de arquivos]
if exist "%SHARE_SCRIPTS%\guardiao_servidor_tick_darkjutsu.bat" (
  call :ok "Servidor de arquivos acessivel."
) else (
  call :fail "Nao achei scripts em %SHARE_SCRIPTS%."
  goto finish
)

echo.
echo [2. Arquivos obrigatorios]
set "REQUIRED=guardiao_servidor_tick_darkjutsu.bat registrar_evento_servidor_darkjutsu.bat limpar_log_72h_darkjutsu.py assumir_servidor_darkjutsu.bat parar_api_darkjutsu.bat abrir_painel_servidor_darkjutsu.bat painel_servidor_darkjutsu.py"
if "%MONITOR_KIND%"=="PYTHON" (
  set "REQUIRED=%REQUIRED% monitor_reserva_python_darkjutsu.py iniciar_monitor_reserva_python_darkjutsu.bat diagnosticar_monitor_reserva_python_darkjutsu.bat"
) else (
  set "REQUIRED=%REQUIRED% monitor_principal_powershell_darkjutsu.ps1 iniciar_monitor_principal_powershell_oculto.vbs"
)
for %%F in (%REQUIRED%) do (
  if exist "%SHARE_SCRIPTS%\%%F" (
    call :ok "Arquivo presente: %%F"
  ) else (
    call :fail "Arquivo ausente: %%F"
  )
)
if not "%FAIL_COUNT%"=="0" goto finish

echo.
echo [3. Pastas locais]
if not exist "%LOCAL_SCRIPTS%" mkdir "%LOCAL_SCRIPTS%" 2>nul
if exist "%LOCAL_SCRIPTS%" (
  call :ok "Pasta local pronta: %LOCAL_SCRIPTS%"
) else (
  call :fail "Nao consegui criar %LOCAL_SCRIPTS%."
  goto finish
)

echo.
echo [4. Python portable, se reserva]
if "%MONITOR_KIND%"=="PYTHON" (
  if exist "%PY_TARGET%\python\python.exe" (
    call :ok "Python portatil ja existe."
  ) else (
    call :warn "Python portatil nao existe neste usuario. Copiando da rede."
    if not exist "%USERPROFILE%\Desktop\aplicacoes code" mkdir "%USERPROFILE%\Desktop\aplicacoes code" 2>nul
    robocopy "%PY_SOURCE%" "%PY_TARGET%" /E /R:2 /W:2 /NFL /NDL /NP >> "%INSTALL_LOG%" 2>&1
    if errorlevel 8 (
      call :fail "Falha ao copiar Python portatil."
      goto finish
    )
    if exist "%PY_TARGET%\python\python.exe" (
      call :ok "Python portatil copiado."
    ) else (
      call :fail "Python copiado mas python.exe nao apareceu."
      goto finish
    )
  )
) else (
  call :ok "Principal nao precisa instalar Python para o monitor."
)

echo.
echo [5. Copia estavel da API]
if exist "%SHARE_ROOT%\pacote\Dark-Jutsu\api\iniciar_api_servidor.bat" (
  if not exist "%MACHINE_APP_ROOT%" mkdir "%MACHINE_APP_ROOT%" 2>nul
  robocopy "%SHARE_ROOT%\pacote\Dark-Jutsu\api" "%MACHINE_APP_ROOT%\api" /E /R:2 /W:2 /NFL /NDL /NP >> "%INSTALL_LOG%" 2>&1
  if errorlevel 8 (
    call :fail "Falha ao copiar API para %MACHINE_APP_ROOT%\api."
    goto finish
  )
  call :ok "API estavel pronta em %MACHINE_APP_ROOT%\api."
) else (
  call :fail "Pacote da API nao encontrado na rede."
  goto finish
)

echo.
echo [6. Copia do monitor e painel]
copy /Y "%SHARE_SCRIPTS%\abrir_painel_servidor_darkjutsu.bat" "%LOCAL_SCRIPTS%\abrir_painel_servidor_darkjutsu.bat" >> "%INSTALL_LOG%" 2>&1
copy /Y "%SHARE_SCRIPTS%\painel_servidor_darkjutsu.py" "%LOCAL_SCRIPTS%\painel_servidor_darkjutsu.py" >> "%INSTALL_LOG%" 2>&1
if "%MONITOR_KIND%"=="PYTHON" (
  copy /Y "%SHARE_SCRIPTS%\monitor_reserva_python_darkjutsu.py" "%LOCAL_SCRIPTS%\monitor_reserva_python_darkjutsu.py" >> "%INSTALL_LOG%" 2>&1
  copy /Y "%SHARE_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat" "%LOCAL_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat" >> "%INSTALL_LOG%" 2>&1
  copy /Y "%SHARE_SCRIPTS%\diagnosticar_monitor_reserva_python_darkjutsu.bat" "%LOCAL_SCRIPTS%\diagnosticar_monitor_reserva_python_darkjutsu.bat" >> "%INSTALL_LOG%" 2>&1
  if exist "%SHARE_SCRIPTS%\icons" robocopy "%SHARE_SCRIPTS%\icons" "%LOCAL_SCRIPTS%\icons" /E /NFL /NDL /NP /R:1 /W:1 >> "%INSTALL_LOG%" 2>&1
  call :ok "Monitor Python e painel copiados."
) else (
  call :ok "Painel local copiado. Monitor principal usa PowerShell da rede."
)

echo.
echo [7. Comandos locais dos botoes]
call :wrapper "abrir_painel_servidor_darkjutsu.bat" "run_painel_servidor_darkjutsu.cmd" 0
call :wrapper "guardiao_servidor_tick_darkjutsu.bat" "run_guardiao_servidor_tick_darkjutsu.cmd" 1
call :wrapper "tornar_reserva_operacional_darkjutsu.bat" "run_tornar_reserva_operacional_darkjutsu.cmd" 0
call :wrapper "tornar_principal_operacional_darkjutsu.bat" "run_tornar_principal_operacional_darkjutsu.cmd" 0
call :wrapper "assumir_servidor_darkjutsu.bat" "run_assumir_servidor_darkjutsu.cmd" 0
call :wrapper "parar_api_darkjutsu.bat" "run_parar_api_darkjutsu.cmd" 0

echo.
echo [8. Guardiao local]
(
  echo Set shell = CreateObject("WScript.Shell"^)
  echo Do
  echo   shell.Run "cmd /c ""%SHARE_SCRIPTS%\guardiao_servidor_tick_darkjutsu.bat""", 0, True
  echo   WScript.Sleep 60000
  echo Loop
) > "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs"
if exist "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" (
  call :ok "Guardiao local criado."
) else (
  call :fail "Nao consegui criar guardiao local."
  goto finish
)

echo.
echo [9. Inicializacao automatica]
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Dark-Jutsu Monitor Servidor" /t REG_SZ /d "%MONITOR_CMD%" /f >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (call :warn "Registro bloqueou monitor.") else (call :ok "Monitor no Registro HKCU Run.")
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Run" /v "Dark-Jutsu Guardiao Servidor" /t REG_SZ /d "wscript.exe //B %LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs" /f >> "%INSTALL_LOG%" 2>&1
if errorlevel 1 (call :warn "Registro bloqueou guardiao.") else (call :ok "Guardiao no Registro HKCU Run.")
(
  echo @echo off
  echo %MONITOR_CMD%
  echo wscript.exe //B "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs"
) > "%DESKTOP%\Iniciar Dark-Jutsu Monitor.cmd" 2>nul
if exist "%DESKTOP%\Iniciar Dark-Jutsu Monitor.cmd" call :ok "Iniciador manual criado na Area de Trabalho."

echo.
echo [10. Iniciar monitor e guardiao]
wmic process where "CommandLine like '%%monitor_reserva_python_darkjutsu%%' or CommandLine like '%%monitor_servidor_darkjutsu_py%%' or CommandLine like '%%monitor_principal_powershell_darkjutsu%%'" call terminate >> "%INSTALL_LOG%" 2>&1
start "" wscript.exe //B "%LOCAL_SCRIPTS%\guardiao_loop_darkjutsu.vbs"
if "%MONITOR_KIND%"=="PYTHON" (
  call "%LOCAL_SCRIPTS%\iniciar_monitor_reserva_python_darkjutsu.bat"
) else (
  wscript.exe //B "%SHARE_SCRIPTS%\iniciar_monitor_principal_powershell_oculto.vbs"
)
call :ok "Solicitei inicio do monitor e do guardiao. Se o icone ja estava aberto, ele pode permanecer como estava ate o proximo login."

goto finish

:wrapper
set "TARGET=%~1"
set "WRAPPER=%~2"
set "PAUSE_END=%~3"
(
  echo @echo off
  echo setlocal EnableExtensions
  echo pushd "%SHARE_SCRIPTS%" 2^>nul
  echo if errorlevel 1 ^(
  echo   echo FALHOU: nao consegui acessar "%SHARE_SCRIPTS%".
  echo   pause
  echo   exit /b 1
  echo ^)
  echo call "%TARGET%"
  echo set "EC=%%ERRORLEVEL%%"
  echo popd
  if "%PAUSE_END%"=="1" echo echo.
  if "%PAUSE_END%"=="1" echo echo Finalizado. Codigo=%%EC%%
  if "%PAUSE_END%"=="1" echo pause
  echo exit /b %%EC%%
) > "%LOCAL_SCRIPTS%\%WRAPPER%"
if exist "%LOCAL_SCRIPTS%\%WRAPPER%" (call :ok "Comando criado: %WRAPPER%") else (call :fail "Falha ao criar %WRAPPER%")
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

:finish
echo.
echo ==================================================
echo RESUMO FINAL
echo ==================================================
type "%SUMMARY%" 2>nul
echo.
if not "%FAIL_COUNT%"=="0" goto finish_failed
echo RESULTADO: OK
echo Avisos: %WARN_COUNT%
echo Log completo: %INSTALL_LOG%
echo Papel: %ROLE% - %MONITOR_KIND% - %LOCAL_IP%
echo ==================================================
del "%SUMMARY%" >nul 2>&1
call :log "RESULTADO FINAL OK"
exit /b 0

:finish_failed
echo RESULTADO: FALHOU em %FAIL_COUNT% parte(s).
echo Avisos: %WARN_COUNT%
echo Log completo: %INSTALL_LOG%
echo Papel: %ROLE% - %MONITOR_KIND% - %LOCAL_IP%
echo ==================================================
del "%SUMMARY%" >nul 2>&1
call :log "RESULTADO FINAL FALHOU"
exit /b 1

