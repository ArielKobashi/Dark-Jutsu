@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SCRIPTS=%SHARE_ROOT%\scripts"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "LOCAL_DIR=%LOCALAPPDATA%\DarkJutsu\monitor"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\reiniciar_monitor_python.log"
set "ROLE=DESCONHECIDO"
set "LOCAL_SCRIPT=monitor_servidor_python_darkjutsu.py"
set "LOCAL_GUARDIAO=guardiao_loop_darkjutsu.vbs"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%LOCAL_DIR%" mkdir "%LOCAL_DIR%" 2>nul

>>"%LOGFILE%" echo ==================================================
>>"%LOGFILE%" echo [%date% %time%] Reiniciando monitor Python. Usuario=%USERNAME% Maquina=%COMPUTERNAME%.

ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if "%errorlevel%"=="0" (
  set "ROLE=PRINCIPAL"
  set "LOCAL_SCRIPT=monitor_servidor_python_darkjutsu.py"
)
if "%ROLE%"=="DESCONHECIDO" (
  ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
  if "!errorlevel!"=="0" (
    set "ROLE=RESERVA"
    set "LOCAL_SCRIPT=monitor_reserva_python_darkjutsu.py"
  )
)

>>"%LOGFILE%" echo [%date% %time%] Papel detectado: !ROLE!. Script local: !LOCAL_SCRIPT!.

>>"%LOGFILE%" echo [%date% %time%] Encerrando monitores antigos antes de copiar.
wmic process where "CommandLine like '%%monitor_servidor_python_darkjutsu.py%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%monitor_reserva_python_darkjutsu.py%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%monitor_reserva_python_darkjutsu_%%.py%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%monitor_servidor_python_darkjutsu_%%.py%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%guardiao_loop_darkjutsu%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%guardiao_loop_principal_darkjutsu%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%guardiao_loop_compartilhado_darkjutsu%%'" call terminate >>"%LOGFILE%" 2>&1
wmic process where "CommandLine like '%%guardiao_loop_python_darkjutsu%%'" call terminate >>"%LOGFILE%" 2>&1
timeout /t 2 /nobreak >nul

copy /Y "%SCRIPTS%\monitor_reserva_python_darkjutsu.py" "%LOCAL_DIR%\!LOCAL_SCRIPT!" >>"%LOGFILE%" 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [%date% %time%] AVISO: falha ao sobrescrever !LOCAL_SCRIPT!. Tentando arquivo versionado.
  set "STAMP=%date:~-4%%date:~3,2%%date:~0,2%_%time:~0,2%%time:~3,2%%time:~6,2%"
  set "STAMP=!STAMP: =0!"
  if "!ROLE!"=="RESERVA" (
    set "LOCAL_SCRIPT=monitor_reserva_python_darkjutsu_!STAMP!.py"
  ) else (
    set "LOCAL_SCRIPT=monitor_servidor_python_darkjutsu_!STAMP!.py"
  )
  copy /Y "%SCRIPTS%\monitor_reserva_python_darkjutsu.py" "%LOCAL_DIR%\!LOCAL_SCRIPT!" >>"%LOGFILE%" 2>&1
  if errorlevel 1 (
    echo ERRO: nao consegui copiar monitor atualizado nem em arquivo versionado.
    >>"%LOGFILE%" echo [%date% %time%] ERRO: falha ao copiar monitor tambem em arquivo versionado.
    exit /b 1
  )
)

copy /Y "%SCRIPTS%\guardiao_loop_compartilhado_darkjutsu.vbs" "%LOCAL_DIR%\%LOCAL_GUARDIAO%" >>"%LOGFILE%" 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [%date% %time%] AVISO: nao consegui copiar guardiao_loop_compartilhado para pasta local. Vou tentar executar direto do fileserver.
)

copy /Y "%SCRIPTS%\guardiao_loop_python_darkjutsu.py" "%LOCAL_DIR%\guardiao_loop_python_darkjutsu.py" >>"%LOGFILE%" 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [%date% %time%] AVISO: nao consegui copiar guardiao_loop_python para pasta local.
)

copy /Y "%SCRIPTS%\status_compartilhado_servidores_darkjutsu.py" "%LOCAL_DIR%\status_compartilhado_servidores_darkjutsu.py" >>"%LOGFILE%" 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [%date% %time%] AVISO: nao consegui copiar status_compartilhado para pasta local; monitor tentara usar fileserver.
)

copy /Y "%SCRIPTS%\abrir_status_darkjutsu.py" "%LOCAL_DIR%\abrir_status_darkjutsu.py" >>"%LOGFILE%" 2>&1
if errorlevel 1 (
  >>"%LOGFILE%" echo [%date% %time%] AVISO: nao consegui copiar abrir_status para pasta local; monitor tentara usar fileserver.
)

>"%LOCAL_DIR%\run_testar_integridade_servidor_darkjutsu.cmd" echo @echo off
>>"%LOCAL_DIR%\run_testar_integridade_servidor_darkjutsu.cmd" echo pushd "%SCRIPTS%"
>>"%LOCAL_DIR%\run_testar_integridade_servidor_darkjutsu.cmd" echo call "testar_integridade_servidor_darkjutsu.bat" %%*
>>"%LOCAL_DIR%\run_testar_integridade_servidor_darkjutsu.cmd" echo popd
>>"%LOCAL_DIR%\run_testar_integridade_servidor_darkjutsu.cmd" echo pause

>"%LOCAL_DIR%\run_guardiao_servidor_tick_darkjutsu.cmd" echo @echo off
>>"%LOCAL_DIR%\run_guardiao_servidor_tick_darkjutsu.cmd" echo pushd "%SCRIPTS%"
>>"%LOCAL_DIR%\run_guardiao_servidor_tick_darkjutsu.cmd" echo call "guardiao_servidor_tick_darkjutsu.bat" %%*
>>"%LOCAL_DIR%\run_guardiao_servidor_tick_darkjutsu.cmd" echo popd
>>"%LOCAL_DIR%\run_guardiao_servidor_tick_darkjutsu.cmd" echo pause

set "PYDIR=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python"
if not exist "%PYDIR%\pythonw.exe" set "PYDIR=%USERPROFILE%\Desktop\aplica????es code\WPy64-3.13.12.0\python"
if not exist "%PYDIR%\pythonw.exe" set "PYDIR=%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python"

if not exist "%PYDIR%\pythonw.exe" (
  echo ERRO: pythonw.exe nao encontrado.
  echo Esperado em: "%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\pythonw.exe"
  >>"%LOGFILE%" echo [%date% %time%] ERRO: pythonw.exe nao encontrado.
  exit /b 1
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
if exist "%STARTUP%" (
  del "%STARTUP%\Monitor Servidor Dark-Jutsu.cmd" >nul 2>&1
  del "%STARTUP%\Guardiao Servidor Dark-Jutsu.cmd" >nul 2>&1
  >"%STARTUP%\Monitor Servidor Dark-Jutsu.vbs" echo Set shell = CreateObject("WScript.Shell")
  >>"%STARTUP%\Monitor Servidor Dark-Jutsu.vbs" echo shell.Run """" ^& "%PYDIR%\pythonw.exe" ^& """ """ ^& "%LOCAL_DIR%\!LOCAL_SCRIPT!" ^& """", 0, False
  >"%STARTUP%\Guardiao Servidor Dark-Jutsu.vbs" echo Set shell = CreateObject("WScript.Shell")
  if exist "%LOCAL_DIR%\guardiao_loop_python_darkjutsu.py" (
    >>"%STARTUP%\Guardiao Servidor Dark-Jutsu.vbs" echo shell.Run """" ^& "%PYDIR%\pythonw.exe" ^& """ """ ^& "%LOCAL_DIR%\guardiao_loop_python_darkjutsu.py" ^& """", 0, False
  ) else if exist "%LOCAL_DIR%\%LOCAL_GUARDIAO%" (
    >>"%STARTUP%\Guardiao Servidor Dark-Jutsu.vbs" echo shell.Run "wscript.exe //B ""%LOCAL_DIR%\%LOCAL_GUARDIAO%""", 0, False
  ) else (
    >>"%STARTUP%\Guardiao Servidor Dark-Jutsu.vbs" echo shell.Run "wscript.exe //B ""%SCRIPTS%\guardiao_loop_compartilhado_darkjutsu.vbs""", 0, False
  )
)

"%PYDIR%\pythonw.exe" "%LOCAL_DIR%\!LOCAL_SCRIPT!"
if errorlevel 1 (
  echo ERRO: falha ao iniciar monitor.
  >>"%LOGFILE%" echo [%date% %time%] ERRO: pythonw retornou falha ao iniciar monitor.
  exit /b 1
)

if exist "%LOCAL_DIR%\guardiao_loop_python_darkjutsu.py" (
  "%PYDIR%\pythonw.exe" "%LOCAL_DIR%\guardiao_loop_python_darkjutsu.py"
) else if exist "%LOCAL_DIR%\%LOCAL_GUARDIAO%" (
  wscript.exe //B "%LOCAL_DIR%\%LOCAL_GUARDIAO%"
) else (
  wscript.exe //B "%SCRIPTS%\guardiao_loop_compartilhado_darkjutsu.vbs"
)

call "%SCRIPTS%\publicar_status_servidor_darkjutsu.bat" >>"%LOGFILE%" 2>&1

echo OK: monitor atualizado e reiniciado. Papel=!ROLE!
>>"%LOGFILE%" echo [%date% %time%] OK: monitor, guardiao e status compartilhado atualizados. Papel=!ROLE!
exit /b 0
