@echo off
setlocal

set "API_BASE=http://192.168.5.41:8765"
set "APP_DIR=%~dp0"
set "SCRIPT=%APP_DIR%_internal\scripts\automus_update.py"
set "CONFIG=%APP_DIR%_internal\scripts\atualizacao\automus_config.json"
set "PROJECT_ROOT=%APPDATA%\Automus\complemento"
set "LOG_DIR=%PROJECT_ROOT%\logs"
set "LOG_FILE=%LOG_DIR%\reenvio_automus.log"
set "SESSION_CONFIG=%PROJECT_ROOT%\controlador_config.json"
set "PYTHON_EXE=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu\instaladores\WPy64-3.13.12.0\python\python.exe"
set "PYTHON_LIBS=%APP_DIR%_internal\python_libs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo [%date% %time%] Iniciando reenvio Automus.>> "%LOG_FILE%"
echo VERSAO_DIR=%APP_DIR%>> "%LOG_FILE%"
echo API=%API_BASE%>> "%LOG_FILE%"
echo PROJECT_ROOT=%PROJECT_ROOT%>> "%LOG_FILE%"

if not exist "%PYTHON_EXE%" (
  echo ERRO: Python portatil nao encontrado: %PYTHON_EXE%
  echo [%date% %time%] ERRO: Python portatil nao encontrado: %PYTHON_EXE%>> "%LOG_FILE%"
  pause
  exit /b 1
)

if not exist "%SCRIPT%" (
  echo ERRO: Script nao encontrado: %SCRIPT%
  echo [%date% %time%] ERRO: Script nao encontrado: %SCRIPT%>> "%LOG_FILE%"
  pause
  exit /b 1
)

set "DARK_JUTSU_API_BASE_URL=%API_BASE%"
set "PYTHONPATH=%PYTHON_LIBS%;%PYTHONPATH%"

if not exist "%PYTHON_LIBS%\openpyxl\__init__.py" (
  echo ERRO: biblioteca openpyxl nao encontrada em %PYTHON_LIBS%.
  echo [%date% %time%] ERRO: biblioteca openpyxl nao encontrada em %PYTHON_LIBS%.>> "%LOG_FILE%"
  pause
  exit /b 1
)

if not defined DARK_JUTSU_API_TOKEN (
  for /f "usebackq delims=" %%T in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%SESSION_CONFIG%'; if(Test-Path -LiteralPath $p){ $cfg=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json; $token=[string]$cfg.adminSession.idToken; if($token){ [Console]::WriteLine($token) } }"`) do set "DARK_JUTSU_API_TOKEN=%%T"
)

if not defined DARK_JUTSU_API_TOKEN (
  echo ERRO: token do Automus nao encontrado. Abra o Automus, faca login admin/mod e rode este reenvio de novo.
  echo [%date% %time%] ERRO: token do Automus nao encontrado em %SESSION_CONFIG%.>> "%LOG_FILE%"
  pause
  exit /b 1
)

echo Testando API...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Invoke-RestMethod '%API_BASE%/health' | Out-String" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo ERRO: API nao respondeu em %API_BASE%. Veja o log: %LOG_FILE%
  pause
  exit /b 1
)

echo Reenviando ultimos dados do Automus...
"%PYTHON_EXE%" "%SCRIPT%" --config "%CONFIG%" --project-root "%PROJECT_ROOT%" >> "%LOG_FILE%" 2>&1
set "RESULT=%ERRORLEVEL%"

if not "%RESULT%"=="0" (
  echo ERRO: reenvio falhou. Veja o log:
  echo %LOG_FILE%
  pause
  exit /b %RESULT%
)

echo OK: reenvio concluido.
echo Log:
echo %LOG_FILE%
echo [%date% %time%] Reenvio Automus concluido.>> "%LOG_FILE%"
pause
exit /b 0
