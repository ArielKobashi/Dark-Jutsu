@echo off
setlocal EnableExtensions

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SCRIPTS=%SHARE_ROOT%\scripts"
set "LOGDIR=%LOCALAPPDATA%\DarkJutsu\logs"
set "LOGSESSION=%RANDOM%_%RANDOM%"
set "LOGFILE=%LOGDIR%\corrigir_darkjutsu_epi_%LOGSESSION%.log"
set "LASTLOG=%LOGDIR%\corrigir_darkjutsu_epi_ultimo.log"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
> "%LOGFILE%" echo [%date% %time%] Iniciando reparo. Maquina=%COMPUTERNAME% Usuario=%USERNAME%
if errorlevel 1 (
  set "LOGDIR=%TEMP%"
  set "LOGFILE=%TEMP%\corrigir_darkjutsu_epi_%LOGSESSION%.log"
  set "LASTLOG=%TEMP%\corrigir_darkjutsu_epi_ultimo.log"
  > "%LOGFILE%" echo [%date% %time%] Iniciando reparo. Maquina=%COMPUTERNAME% Usuario=%USERNAME%
)

echo ==================================================
echo Dark-Jutsu - reparo do candidato EPI/usuario
echo Maquina: %COMPUTERNAME%
echo Usuario: %USERNAME%
echo Log: %LOGFILE%
echo ==================================================
echo.
>>"%LOGFILE%" echo Fileserver: %SHARE_ROOT%

if not exist "%SCRIPTS%\configurar_servidor_usuario_darkjutsu.bat" (
  echo ERRO: nao achei configurar_servidor_usuario_darkjutsu.bat no fileserver.
  >>"%LOGFILE%" echo [%date% %time%] ERRO: configurador ausente.
  pause
  exit /b 1
)

echo [1/3] Preparando PostgreSQL local, API e backup mais recente...
call "%SCRIPTS%\configurar_servidor_usuario_darkjutsu.bat" >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo ERRO: falha ao preparar servidor local. Veja o log acima.
  type "%LOGFILE%"
  pause
  exit /b 1
)

echo.
echo [2/3] Reinstalando guardiao, monitor e watchdog deste usuario...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPTS%\atualizar_usuario_guardiao_monitor_darkjutsu.ps1" -NoStatus >> "%LOGFILE%" 2>&1
if errorlevel 1 (
  echo ERRO: falha ao reinstalar guardiao/monitor. Veja o log acima.
  type "%LOGFILE%"
  pause
  exit /b 1
)

echo.
echo [3/3] Abrindo status final...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 8; & '%USERPROFILE%\Desktop\aplicacoes code\WPy64-3.13.12.0\python\python.exe' '%SCRIPTS%\status_compartilhado_servidores_darkjutsu.py'" >> "%LOGFILE%" 2>&1

copy /Y "%LOGFILE%" "%LASTLOG%" >nul 2>&1

echo.
echo OK: reparo solicitado. Se aparecer ALMOX-EPI como PRONTO no status, ele ja entra como terceiro candidato.
echo Log completo:
echo %LOGFILE%
echo Ultimo log:
echo %LASTLOG%
echo.
type "%LOGFILE%"
pause
