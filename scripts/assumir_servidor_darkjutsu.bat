@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "PRIMARY_IP=192.168.5.44"
set "RESERVE_IP=192.168.5.38"
set "API_PORT=8765"
set "LOGDIR=C:\DarkJutsu\logs"
set "EVENT_LOGGER=%SHARE_ROOT%\scripts\registrar_evento_servidor_darkjutsu.bat"
set "PG_ISREADY=C:\DarkJutsu\PostgreSQL\pgsql\bin\pg_isready.exe"
set "START_PG=%SHARE_ROOT%\scripts\iniciar_postgres_darkjutsu.bat"
set "START_API=%SHARE_ROOT%\scripts\iniciar_api_darkjutsu_service.vbs"
set "LOCAL_IP="

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
copy /Y NUL "%LOGDIR%\.write_test" >nul 2>&1
if not "%errorlevel%"=="0" set "LOGDIR=%TEMP%\DarkJutsu\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
del "%LOGDIR%\.write_test" >nul 2>&1
set "LOGFILE=%LOGDIR%\servidor_guardiao.log"

ipconfig | findstr /C:"%PRIMARY_IP%" >nul 2>&1
if "%errorlevel%"=="0" set "LOCAL_IP=%PRIMARY_IP%"
if "%LOCAL_IP%"=="" (
  ipconfig | findstr /C:"%RESERVE_IP%" >nul 2>&1
  if "!errorlevel!"=="0" set "LOCAL_IP=%RESERVE_IP%"
)
if "%LOCAL_IP%"=="" set "LOCAL_IP=127.0.0.1"

>> "%LOGFILE%" echo ==================================================
>> "%LOGFILE%" echo [%date% %time%] ASSUMIR: inicio. Usuario=%USERNAME% Maquina=%COMPUTERNAME% IP=%LOCAL_IP%.
>> "%LOGFILE%" echo [%date% %time%] ASSUMIR: PG_ISREADY=%PG_ISREADY%.
>> "%LOGFILE%" echo [%date% %time%] ASSUMIR: START_PG=%START_PG%.
>> "%LOGFILE%" echo [%date% %time%] ASSUMIR: START_API=%START_API%.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "ASSUMIR" "Inicio da tentativa de assumir servidor. IP=%LOCAL_IP%"

if not exist "%PG_ISREADY%" (
  >> "%LOGFILE%" echo [%date% %time%] ERRO: pg_isready nao encontrado.
  if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "POSTGRES" "pg_isready nao encontrado em %PG_ISREADY%."
  exit /b 1
)
if not exist "%START_PG%" (
  >> "%LOGFILE%" echo [%date% %time%] ERRO: iniciar_postgres nao encontrado.
  if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "POSTGRES" "Script de iniciar PostgreSQL nao encontrado."
  exit /b 1
)
if not exist "%START_API%" (
  >> "%LOGFILE%" echo [%date% %time%] ERRO: iniciar_api service nao encontrado.
  if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "API" "Script de iniciar API em segundo plano nao encontrado."
  exit /b 1
)

>> "%LOGFILE%" echo [%date% %time%] ASSUMIR: testando API local antes de iniciar.
curl -fsS --max-time 3 "http://127.0.0.1:%API_PORT%/health" >nul 2>&1
if "%errorlevel%"=="0" (
  >> "%LOGFILE%" echo [%date% %time%] ASSUMIR: API local ja respondia. Nada a iniciar.
  if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "ASSUMIR" "API local ja respondia antes de iniciar."
  exit /b 0
)
>> "%LOGFILE%" echo [%date% %time%] ASSUMIR: API local nao respondeu antes de iniciar. Codigo curl=%errorlevel%.

"%PG_ISREADY%" -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
if not "%errorlevel%"=="0" (
  >> "%LOGFILE%" echo [%date% %time%] POSTGRES: pg_isready falhou; tentando iniciar PostgreSQL.
  if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "POSTGRES" "PostgreSQL local nao respondeu; tentando iniciar."
  call "%START_PG%" >> "%LOGFILE%" 2>&1
  set "PG_START_RC=!errorlevel!"
  >> "%LOGFILE%" echo [%date% %time%] POSTGRES: iniciar_postgres retornou codigo !PG_START_RC!.
  "%PG_ISREADY%" -h 127.0.0.1 -p 5433 -U dark_jutsu -d dark_jutsu >nul 2>&1
  if not "!errorlevel!"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] ERRO: PostgreSQL continuou indisponivel depois da tentativa de inicio.
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "POSTGRES" "PostgreSQL nao iniciou; servidor nao pode assumir. iniciar_postgres_codigo=!PG_START_RC!."
    exit /b 1
  )
  >> "%LOGFILE%" echo [%date% %time%] POSTGRES: pronto apos tentativa de inicio.
) else (
  >> "%LOGFILE%" echo [%date% %time%] POSTGRES: ja estava pronto.
)
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "POSTGRES" "PostgreSQL local pronto."

>> "%LOGFILE%" echo [%date% %time%] API: chamando wscript para iniciar API oculta.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "INFO" "API" "Solicitando inicio da API em segundo plano."
wscript.exe //B "%START_API%"
set "API_START_RC=%errorlevel%"
>> "%LOGFILE%" echo [%date% %time%] API: wscript retornou codigo %API_START_RC%.

for /L %%N in (1,1,30) do (
  curl -fsS --max-time 3 "http://127.0.0.1:%API_PORT%/health" >nul 2>&1
  if "!errorlevel!"=="0" (
    >> "%LOGFILE%" echo [%date% %time%] API: local respondeu apos %%N tentativa(s).
    if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "API" "API respondeu em http://127.0.0.1:%API_PORT%/health apos %%N tentativa(s)."
    curl -fsS --max-time 3 "http://%LOCAL_IP%:%API_PORT%/health" >nul 2>&1
    if "!errorlevel!"=="0" (
      >> "%LOGFILE%" echo [%date% %time%] API_REDE: respondeu pelo IP %LOCAL_IP%.
      if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "OK" "API_REDE" "API respondeu pela rede em http://%LOCAL_IP%:%API_PORT%/health."
    ) else (
      >> "%LOGFILE%" echo [%date% %time%] AVISO: API local respondeu, mas rede %LOCAL_IP% falhou com codigo !errorlevel!.
      if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "AVISO" "API_REDE" "API local respondeu, mas ainda nao respondeu pelo IP %LOCAL_IP%."
    )
    >> "%LOGFILE%" echo [%date% %time%] ASSUMIR: finalizado com sucesso.
    exit /b 0
  )
  >> "%LOGFILE%" echo [%date% %time%] API: aguardando resposta local. Tentativa %%N/30 codigo=!errorlevel!.
  timeout /t 1 /nobreak >nul
)

>> "%LOGFILE%" echo [%date% %time%] ERRO: API nao respondeu depois de 30 segundos. wscript_codigo=%API_START_RC%.
if exist "%EVENT_LOGGER%" call "%EVENT_LOGGER%" "ERRO" "API" "API nao respondeu em 30 segundos apos solicitacao de inicio. wscript_codigo=%API_START_RC%."
exit /b 1
