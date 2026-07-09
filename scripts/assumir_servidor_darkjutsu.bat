@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "LOGDIR=C:\DarkJutsu\logs"
set "EVENT_LOGGER=%SHARE_ROOT%\scripts\registrar_evento_servidor_darkjutsu.bat"
set "LOCAL_IP="

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not %errorlevel%==0 set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if %errorlevel%==0 set "LOCAL_IP=%PRIMARY_IP%"
if "%LOCAL_IP%"=="" (
  ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
  if !errorlevel!==0 set "LOCAL_IP=%RESERVE_IP%"
)
if "%LOCAL_IP%"=="" set "LOCAL_IP=127.0.0.1"

echo ================================================== >> "%LOGFILE%"
echo [%date% %time%] ACAO: esta maquina vai assumir servidor Dark-Jutsu. Usuario=%USERNAME% Maquina=%COMPUTERNAME% IP=%LOCAL_IP% >> "%LOGFILE%"
call :event INFO ASSUMIR "Inicio da tentativa de assumir servidor. IP=%LOCAL_IP%"

call :health "127.0.0.1"
if "%errorlevel%"=="0" (
  call :event OK ASSUMIR "API local ja respondia antes de iniciar."
  exit /b 0
)

C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
if errorlevel 1 (
  call :event INFO POSTGRES "PostgreSQL local nao respondeu; tentando iniciar."
  call "%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat" >> "%LOGFILE%" 2>&1
  C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
  if errorlevel 1 (
    echo [%date% %time%] ERRO: PostgreSQL nao iniciou e nao esta pronto. >> "%LOGFILE%"
    call :event ERRO POSTGRES "PostgreSQL nao iniciou; servidor nao pode assumir."
    exit /b 1
  )
)
call :event OK POSTGRES "PostgreSQL local pronto."

call :event INFO API "Solicitando inicio da API em segundo plano."
wscript.exe //B "%SHARE_ROOT%\scripts\iniciar_api_darkjutsu_service.vbs"

for /L %%N in (1,1,30) do (
  call :health "127.0.0.1"
  if "!errorlevel!"=="0" (
    call :event OK API "API respondeu em http://127.0.0.1:%API_PORT%/health apos %%N tentativa(s)."
    call :health "%LOCAL_IP%"
    if "!errorlevel!"=="0" (
      call :event OK API_REDE "API respondeu pela rede em http://%LOCAL_IP%:%API_PORT%/health."
    ) else (
      call :event AVISO API_REDE "API local respondeu, mas ainda nao respondeu pelo IP %LOCAL_IP%."
    )
    exit /b 0
  )
  timeout /t 1 /nobreak >nul
)

echo [%date% %time%] ERRO: API nao respondeu depois de 30 segundos. >> "%LOGFILE%"
call :event ERRO API "API nao respondeu em 30 segundos apos solicitacao de inicio."
exit /b 1

:health
curl -fsS --max-time 3 "http://%~1:%API_PORT%/health" >nul 2>&1
exit /b %errorlevel%

:event
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "%~1" "%~2" "%~3"
exit /b 0
