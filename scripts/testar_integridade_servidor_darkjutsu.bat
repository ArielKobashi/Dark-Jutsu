@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SCRIPTS=%SHARE_ROOT%\scripts"
set "LOGGER=%SCRIPTS%\registrar_evento_servidor_darkjutsu.bat"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "FAILS=0"
set "WARNS=0"

echo ==================================================
echo Dark-Jutsu - Teste de integridade sensivel
echo Usuario: %USERNAME%
echo Maquina: %COMPUTERNAME%
echo ==================================================
echo.

call :event INFO TESTE "Inicio do teste de integridade sensivel."

call :step "Acesso ao compartilhamento"
if exist "%SHARE_ROOT%\app\index.html" (
  call :ok "App encontrado no compartilhamento."
) else (
  call :fail "App nao encontrado em %SHARE_ROOT%\app\index.html."
)

call :step "Arquivos criticos"
call :need "%SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat"
call :need "%SCRIPTS%\guardiao_servidor_tick_darkjutsu.bat"
call :need "%SCRIPTS%\assumir_servidor_darkjutsu.bat"
call :need "%SCRIPTS%\registrar_evento_servidor_darkjutsu.bat"
call :need "%SCRIPTS%\limpar_log_72h_darkjutsu.py"
call :need "%SCRIPTS%\monitor_principal_powershell_darkjutsu.ps1"
call :need "%SCRIPTS%\monitor_reserva_python_darkjutsu.py"
call :need "%SCRIPTS%\iniciar_api_darkjutsu_service.vbs"

call :step "Health das APIs"
call :health "%PRIMARY_IP%" "Principal"
call :health "%RESERVE_IP%" "Reserva"
call :health "127.0.0.1" "Local"

call :step "Portas locais"
netstat -ano -p tcp | findstr /R /C:":%API_PORT% .*LISTENING" >nul 2>&1
if errorlevel 1 (
  call :warn "Porta local %API_PORT% nao esta ouvindo neste PC."
) else (
  call :ok "Porta local %API_PORT% esta ouvindo."
)

netstat -ano -p tcp | findstr /R /C:":5433 .*LISTENING" >nul 2>&1
if errorlevel 1 (
  call :warn "Porta local PostgreSQL 5433 nao esta ouvindo neste PC."
) else (
  call :ok "Porta local PostgreSQL 5433 esta ouvindo."
)

call :step "PostgreSQL local"
if exist "C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe" (
  C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
  if errorlevel 1 (
    call :warn "pg_isready nao confirmou PostgreSQL local."
  ) else (
    call :ok "PostgreSQL local aceitando conexoes."
  )
) else (
  call :warn "pg_isready.exe nao encontrado neste PC."
)

call :step "Logs"
if exist "%SHARE_ROOT%\logs\servidor_eventos_darkjutsu.txt" (
  call :ok "Log compartilhado existe."
) else (
  call :warn "Log compartilhado ainda nao existe."
)
if exist "C:\DarkJutsu\logs\servidor_guardiao.log" (
  call :ok "Log local do guardiao existe."
) else (
  call :warn "Log local do guardiao ainda nao existe."
)

call :step "Processos de monitor/guardiao"
wmic process where "CommandLine like '%%monitor_principal_powershell_darkjutsu%%' or CommandLine like '%%monitor_reserva_python_darkjutsu%%' or CommandLine like '%%guardiao_loop_darkjutsu%%'" get ProcessId,CommandLine 2>nul | findstr /R "[0-9]" >nul 2>&1
if errorlevel 1 (
  call :warn "Nao encontrei monitor/guardiao rodando neste usuario."
) else (
  call :ok "Encontrei monitor ou guardiao rodando neste usuario."
)

echo.
echo ==================================================
echo RESULTADO DO TESTE
echo Falhas: %FAILS%
echo Avisos: %WARNS%
echo ==================================================
call :event INFO TESTE "Fim do teste de integridade. Falhas=%FAILS%; Avisos=%WARNS%."

if "%FAILS%"=="0" exit /b 0
exit /b 1

:step
echo.
echo [%~1]
call :event INFO TESTE "%~1"
exit /b 0

:ok
echo OK: %~1
call :event OK TESTE "%~1"
exit /b 0

:warn
set /a WARNS+=1
echo AVISO: %~1
call :event AVISO TESTE "%~1"
exit /b 0

:fail
set /a FAILS+=1
echo ERRO: %~1
call :event ERRO TESTE "%~1"
exit /b 0

:need
if exist "%~1" (
  call :ok "Arquivo presente: %~nx1"
) else (
  call :fail "Arquivo ausente: %~1"
)
exit /b 0

:health
curl -fsS --max-time 5 "http://%~1:%API_PORT%/health" >nul 2>&1
set "RC=!errorlevel!"
if "!RC!"=="0" (
  call :ok "%~2 respondeu em http://%~1:%API_PORT%/health."
) else (
  call :warn "%~2 nao respondeu em http://%~1:%API_PORT%/health. Codigo curl=!RC!."
)
exit /b 0

:event
if exist "%LOGGER%" call "%LOGGER%" "%~1" "%~2" "%~3" >nul 2>nul
exit /b 0
