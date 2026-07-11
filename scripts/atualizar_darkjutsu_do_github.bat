@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "REPO_URL=https://github.com/ArielKobashi/Dark-Jutsu.git"
set "BRANCH=main"
set "SHARE_ROOT=\\fileserver\Almoxarifado\0800\servidor\dark-jutsu"
set "SHARE_SCRIPTS=%SHARE_ROOT%\scripts"
set "WORK_ROOT=C:\DarkJutsu\github-sync"
set "REPO_DIR=%WORK_ROOT%\Dark-Jutsu"
set "LOGDIR=C:\DarkJutsu\logs"
set "LOGFILE=%LOGDIR%\atualizacao_github.log"
set "LOCKDIR=%SHARE_ROOT%\atualizacao-github.lock"
set "VERSION_FILE=%SHARE_ROOT%\versao_github_atual.txt"
set "NEW_COMMIT="
set "OLD_COMMIT="
set "FORCE_UPDATE=0"

if /I "%~1"=="--force" set "FORCE_UPDATE=1"

if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
if not exist "%WORK_ROOT%" mkdir "%WORK_ROOT%" 2>nul

call :log "=================================================="
call :log "Inicio atualizacao GitHub. Usuario=%USERNAME% Maquina=%COMPUTERNAME%"

if not exist "%SHARE_ROOT%\app" (
  call :log "FALHOU: servidor de arquivos nao acessivel: %SHARE_ROOT%"
  exit /b 1
)

mkdir "%LOCKDIR%" >nul 2>&1
if errorlevel 1 (
  call :log "Outro atualizador ja esta rodando. Saindo."
  exit /b 0
)

where git.exe >nul 2>&1
if errorlevel 1 (
  call :log "FALHOU: git.exe nao encontrado nesta maquina."
  call :unlock
  exit /b 1
)

if not exist "%REPO_DIR%\.git" (
  call :log "Clone inicial em %REPO_DIR%"
  if exist "%REPO_DIR%" rmdir /S /Q "%REPO_DIR%" >nul 2>&1
  git clone --branch "%BRANCH%" "%REPO_URL%" "%REPO_DIR%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "FALHOU: git clone nao concluiu."
    call :unlock
    exit /b 1
  )
) else (
  call :log "Atualizando clone local."
  git -C "%REPO_DIR%" remote set-url origin "%REPO_URL%" >> "%LOGFILE%" 2>&1
  git -C "%REPO_DIR%" fetch origin "%BRANCH%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "FALHOU: git fetch nao concluiu."
    call :unlock
    exit /b 1
  )
  git -C "%REPO_DIR%" reset --hard "origin/%BRANCH%" >> "%LOGFILE%" 2>&1
  if errorlevel 1 (
    call :log "FALHOU: git reset nao concluiu."
    call :unlock
    exit /b 1
  )
)

for /f %%C in ('git -C "%REPO_DIR%" rev-parse HEAD') do set "NEW_COMMIT=%%C"
if exist "%VERSION_FILE%" set /p OLD_COMMIT=<"%VERSION_FILE%"

if /I "%NEW_COMMIT%"=="%OLD_COMMIT%" (
  call :log "Sem mudanca. Versao ja aplicada: %NEW_COMMIT%"
  call :unlock
  exit /b 0
)

if "%OLD_COMMIT%"=="" if not "%FORCE_UPDATE%"=="1" (
  >"%VERSION_FILE%" echo %NEW_COMMIT%
  call :log "Primeira execucao: versao GitHub registrada sem publicar para nao sobrescrever o servidor atual. Use --force se quiser publicar agora."
  call :unlock
  exit /b 0
)

call :log "Nova versao detectada: %NEW_COMMIT%"
call :publish
set "RC=%errorlevel%"
if not "%RC%"=="0" (
  call :log "FALHOU: publicacao retornou codigo %RC%."
  call :unlock
  exit /b %RC%
)

>"%VERSION_FILE%" echo %NEW_COMMIT%
call :log "Versao publicada no servidor de arquivos: %NEW_COMMIT%"

if exist "%SHARE_SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat" (
  call :log "Reinstalando guardiao/monitor nesta maquina para pegar scripts novos."
  call "%SHARE_SCRIPTS%\instalar_atualizar_guardiao_monitor_darkjutsu.bat" >> "%LOGFILE%" 2>&1
)

call :unlock
exit /b 0

:publish
call :log "Publicando app web."
robocopy "%REPO_DIR%" "%SHARE_ROOT%\app" dashboard-nav.js dashboard.html index.html label-editor.html logo-tab.png logo.png medidores.html mobile.css style.css /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if %errorlevel% GEQ 8 exit /b %errorlevel%
if exist "%REPO_DIR%\assets" robocopy "%REPO_DIR%\assets" "%SHARE_ROOT%\app\assets" /E /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if %errorlevel% GEQ 8 exit /b %errorlevel%

call :log "Publicando scripts."
robocopy "%REPO_DIR%\scripts" "%SHARE_ROOT%\scripts" /E /XD __pycache__ /XF *.pyc /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if %errorlevel% GEQ 8 exit /b %errorlevel%

call :log "Publicando API do pacote."
robocopy "%REPO_DIR%\api" "%SHARE_ROOT%\pacote\Dark-Jutsu\api" /E /XD __pycache__ /XF *.pyc /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if %errorlevel% GEQ 8 exit /b %errorlevel%

call :log "Publicando scripts do banco, sem dados PostgreSQL."
robocopy "%REPO_DIR%\db" "%SHARE_ROOT%\pacote\Dark-Jutsu\db" /E /XD data __pycache__ /XF *.pyc postgres.log /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if %errorlevel% GEQ 8 exit /b %errorlevel%

call :log "Publicando docs."
if exist "%REPO_DIR%\docs" robocopy "%REPO_DIR%\docs" "%SHARE_ROOT%\docs" /E /R:2 /W:2 /NFL /NDL /NP >> "%LOGFILE%" 2>&1
if %errorlevel% GEQ 8 exit /b %errorlevel%
exit /b 0

:unlock
rmdir "%LOCKDIR%" >nul 2>&1
exit /b 0

:log
echo [%date% %time%] %~1
>>"%LOGFILE%" echo [%date% %time%] %~1
exit /b 0
